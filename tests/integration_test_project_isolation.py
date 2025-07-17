"""
Integration tests for project isolation

These tests validate that resources and state are properly isolated between projects.
They test the integration between project management, state management, and AWS MCP client.

Environment variables:
- AWS_MCP_SERVER_URL: URL of the AWS MCP Server (default: http://localhost:8080)
- AWS_STATE_BUCKET: S3 bucket for state files (default: aws-infra-manager-test)
- AWS_STATE_BUCKET_PREFIX: Prefix for state files (default: integration-test)
"""
import os
import pytest
import uuid
import boto3
from datetime import datetime

from src.services.project_management import ProjectManagementServiceImpl
from src.services.s3_state_management import S3StateManagementService
from src.services.aws_mcp_client import create_aws_mcp_client
from src.models.data_models import (
    ProjectConfig, ProjectSettings, NotificationConfig,
    ResourceConfig, InfrastructureState, StateMetadata, Resource
)
from src.models.enums import ResourceStatus

# Get configuration from environment variables
MCP_SERVER_URL = os.environ.get("AWS_MCP_SERVER_URL", "http://localhost:8080")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TEST_BUCKET = os.environ.get("AWS_STATE_BUCKET", "aws-infra-manager-test")
TEST_PREFIX = os.environ.get("AWS_STATE_BUCKET_PREFIX", "integration-test")


@pytest.fixture(scope="module")
def aws_session():
    """Create AWS session for testing"""
    return boto3.Session(region_name=AWS_REGION)


@pytest.fixture
async def project_service():
    """Create project management service for testing"""
    return ProjectManagementServiceImpl()


@pytest.fixture
async def state_service(aws_session):
    """Create S3 state management service for testing"""
    # Override settings with test values
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AWS_STATE_BUCKET", TEST_BUCKET)
        mp.setenv("AWS_STATE_BUCKET_PREFIX", TEST_PREFIX)
        
        # Create service with test session
        service = S3StateManagementService(aws_session=aws_session)
        
        # Ensure bucket exists
        await service._ensure_bucket_exists()
        
        yield service


@pytest.fixture
async def mcp_client():
    """Create AWS MCP client for testing"""
    client = create_aws_mcp_client(
        server_url=MCP_SERVER_URL,
        timeout=30,
        max_retries=2,
        circuit_breaker_threshold=3
    )
    
    await client.connect()
    yield client
    await client.disconnect()


@pytest.fixture
async def test_projects(project_service):
    """Create test projects for isolation testing"""
    # Create project settings
    settings1 = ProjectSettings(
        s3_bucket_path=f"s3://{TEST_BUCKET}/{TEST_PREFIX}/project1",
        default_region="us-east-1",
        notification_settings=NotificationConfig(
            email_notifications=True,
            notification_events=["approval_required"]
        )
    )
    
    settings2 = ProjectSettings(
        s3_bucket_path=f"s3://{TEST_BUCKET}/{TEST_PREFIX}/project2",
        default_region="us-east-1",
        notification_settings=NotificationConfig(
            email_notifications=True,
            notification_events=["approval_required"]
        )
    )
    
    # Create project configs
    config1 = ProjectConfig(
        name="Test Project 1",
        description="First test project for isolation testing",
        owner="user1",
        settings=settings1
    )
    
    config2 = ProjectConfig(
        name="Test Project 2",
        description="Second test project for isolation testing",
        owner="user2",
        settings=settings2
    )
    
    # Create projects
    project1 = await project_service.create_project(config1)
    project2 = await project_service.create_project(config2)
    
    return project1, project2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_state_isolation(state_service, test_projects):
    """Test that state is properly isolated between projects"""
    project1, project2 = test_projects
    
    # Create state for project 1
    resource1 = Resource(
        id=f"i-{uuid.uuid4().hex[:16]}",
        project_id=project1.id,
        type="EC2::Instance",
        name="project1-instance",
        region="us-east-1",
        properties={"instanceType": "t3.micro"},
        tags={"Project": "Project1"},
        status=ResourceStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    metadata1 = StateMetadata(
        last_modified_by="user1",
        change_description="Project 1 state",
        change_plan_id=None
    )
    
    state1 = InfrastructureState(
        project_id=project1.id,
        version="1.0.0",
        timestamp=datetime.now(),
        resources=[resource1],
        metadata=metadata1
    )
    
    # Create state for project 2
    resource2 = Resource(
        id=f"i-{uuid.uuid4().hex[:16]}",
        project_id=project2.id,
        type="EC2::Instance",
        name="project2-instance",
        region="us-east-1",
        properties={"instanceType": "t3.large"},
        tags={"Project": "Project2"},
        status=ResourceStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    metadata2 = StateMetadata(
        last_modified_by="user2",
        change_description="Project 2 state",
        change_plan_id=None
    )
    
    state2 = InfrastructureState(
        project_id=project2.id,
        version="1.0.0",
        timestamp=datetime.now(),
        resources=[resource2],
        metadata=metadata2
    )
    
    # Save both states
    await state_service.save_state(project1.id, state1)
    await state_service.save_state(project2.id, state2)
    
    # Retrieve states
    retrieved_state1 = await state_service.get_current_state(project1.id)
    retrieved_state2 = await state_service.get_current_state(project2.id)
    
    # Verify project 1 state
    assert retrieved_state1 is not None, "Project 1 state should be retrievable"
    assert retrieved_state1.project_id == project1.id, "Project 1 ID should match"
    assert len(retrieved_state1.resources) == 1, "Project 1 should have 1 resource"
    assert retrieved_state1.resources[0].name == "project1-instance", "Project 1 resource name should match"
    
    # Verify project 2 state
    assert retrieved_state2 is not None, "Project 2 state should be retrievable"
    assert retrieved_state2.project_id == project2.id, "Project 2 ID should match"
    assert len(retrieved_state2.resources) == 1, "Project 2 should have 1 resource"
    assert retrieved_state2.resources[0].name == "project2-instance", "Project 2 resource name should match"
    
    # Verify cross-project isolation
    assert retrieved_state1.resources[0].id != retrieved_state2.resources[0].id, "Resources should be different"
    assert retrieved_state1.resources[0].name != retrieved_state2.resources[0].name, "Resource names should be different"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_resource_isolation(mcp_client, test_projects):
    """Test that MCP resources are properly isolated between projects"""
    project1, project2 = test_projects
    
    # Create resource in project 1
    resource_config1 = ResourceConfig(
        type="EC2::Instance",
        name=f"project1-instance-{uuid.uuid4().hex[:8]}",
        properties={
            "instanceType": "t3.micro",
            "imageId": "ami-12345678"
        },
        tags={"Project": "Project1", "IsolationTest": "true"}
    )
    
    # Create resource in project 2
    resource_config2 = ResourceConfig(
        type="EC2::Instance",
        name=f"project2-instance-{uuid.uuid4().hex[:8]}",
        properties={
            "instanceType": "t3.large",
            "imageId": "ami-87654321"
        },
        tags={"Project": "Project2", "IsolationTest": "true"}
    )
    
    try:
        # Create resources
        resource1 = await mcp_client.create_resource(project1.id, resource_config1)
        resource2 = await mcp_client.create_resource(project2.id, resource_config2)
        
        # Verify resources were created
        assert resource1.id is not None, "Project 1 resource should be created"
        assert resource2.id is not None, "Project 2 resource should be created"
        
        # List resources for project 1
        project1_resources = await mcp_client.list_resources(project1.id)
        
        # List resources for project 2
        project2_resources = await mcp_client.list_resources(project2.id)
        
        # Verify project 1 resources
        assert any(r.id == resource1.id for r in project1_resources), "Project 1 should contain its resource"
        assert not any(r.id == resource2.id for r in project1_resources), "Project 1 should not contain project 2's resource"
        
        # Verify project 2 resources
        assert any(r.id == resource2.id for r in project2_resources), "Project 2 should contain its resource"
        assert not any(r.id == resource1.id for r in project2_resources), "Project 2 should not contain project 1's resource"
        
        # Try to access project 1's resource from project 2
        cross_project_resource = await mcp_client.get_resource(project2.id, resource1.id)
        assert cross_project_resource is None, "Should not be able to access project 1's resource from project 2"
        
        # Try to access project 2's resource from project 1
        cross_project_resource = await mcp_client.get_resource(project1.id, resource2.id)
        assert cross_project_resource is None, "Should not be able to access project 2's resource from project 1"
        
    finally:
        # Clean up resources
        if 'resource1' in locals():
            await mcp_client.delete_resource(project1.id, resource1.id)
        if 'resource2' in locals():
            await mcp_client.delete_resource(project2.id, resource2.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_change_plan_isolation(state_service, test_projects, mcp_client):
    """Test that change plans are properly isolated between projects"""
    project1, project2 = test_projects
    
    # Create resources in both projects
    resource_config1 = ResourceConfig(
        type="EC2::Instance",
        name=f"cp-test-p1-{uuid.uuid4().hex[:8]}",
        properties={"instanceType": "t3.micro"},
        tags={"Project": "Project1", "PlanTest": "true"}
    )
    
    resource_config2 = ResourceConfig(
        type="EC2::Instance",
        name=f"cp-test-p2-{uuid.uuid4().hex[:8]}",
        properties={"instanceType": "t3.large"},
        tags={"Project": "Project2", "PlanTest": "true"}
    )
    
    try:
        # Create resources
        resource1 = await mcp_client.create_resource(project1.id, resource_config1)
        resource2 = await mcp_client.create_resource(project2.id, resource_config2)
        
        # Create initial states
        metadata1 = StateMetadata(
            last_modified_by="user1",
            change_description="Project 1 initial state",
            change_plan_id=None
        )
        
        state1 = InfrastructureState(
            project_id=project1.id,
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[resource1],
            metadata=metadata1
        )
        
        metadata2 = StateMetadata(
            last_modified_by="user2",
            change_description="Project 2 initial state",
            change_plan_id=None
        )
        
        state2 = InfrastructureState(
            project_id=project2.id,
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[resource2],
            metadata=metadata2
        )
        
        # Save states
        await state_service.save_state(project1.id, state1)
        await state_service.save_state(project2.id, state2)
        
        # Create desired states with changes
        updated_resource1 = Resource(
            id=resource1.id,
            project_id=project1.id,
            type=resource1.type,
            name=resource1.name,
            region=resource1.region,
            properties={"instanceType": "t3.small"},  # Changed
            tags=resource1.tags,
            status=resource1.status,
            created_at=resource1.created_at,
            updated_at=datetime.now(),
            arn=resource1.arn
        )
        
        updated_resource2 = Resource(
            id=resource2.id,
            project_id=project2.id,
            type=resource2.type,
            name=resource2.name,
            region=resource2.region,
            properties={"instanceType": "t3.xlarge"},  # Changed
            tags=resource2.tags,
            status=resource2.status,
            created_at=resource2.created_at,
            updated_at=datetime.now(),
            arn=resource2.arn
        )
        
        desired_state1 = InfrastructureState(
            project_id=project1.id,
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[updated_resource1],
            metadata=StateMetadata(
                last_modified_by="user1",
                change_description="Project 1 desired state",
                change_plan_id=None
            )
        )
        
        desired_state2 = InfrastructureState(
            project_id=project2.id,
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[updated_resource2],
            metadata=StateMetadata(
                last_modified_by="user2",
                change_description="Project 2 desired state",
                change_plan_id=None
            )
        )
        
        # Generate change plans
        plan1 = state_service.compare_states(state1, desired_state1)
        plan2 = state_service.compare_states(state2, desired_state2)
        
        # Save change plans
        await state_service.save_change_plan(project1.id, plan1)
        await state_service.save_change_plan(project2.id, plan2)
        
        # List change plans for each project
        project1_plans = await state_service.list_change_plans(project1.id)
        project2_plans = await state_service.list_change_plans(project2.id)
        
        # Verify project 1 plans
        assert len(project1_plans) >= 1, "Project 1 should have at least one plan"
        assert any(p.id == plan1.id for p in project1_plans), "Project 1 should contain its plan"
        assert not any(p.id == plan2.id for p in project1_plans), "Project 1 should not contain project 2's plan"
        
        # Verify project 2 plans
        assert len(project2_plans) >= 1, "Project 2 should have at least one plan"
        assert any(p.id == plan2.id for p in project2_plans), "Project 2 should contain its plan"
        assert not any(p.id == plan1.id for p in project2_plans), "Project 2 should not contain project 1's plan"
        
        # Get specific plans
        retrieved_plan1 = await state_service.get_change_plan(project1.id, plan1.id)
        retrieved_plan2 = await state_service.get_change_plan(project2.id, plan2.id)
        
        # Verify plans
        assert retrieved_plan1 is not None, "Project 1 plan should be retrievable"
        assert retrieved_plan1.id == plan1.id, "Project 1 plan ID should match"
        
        assert retrieved_plan2 is not None, "Project 2 plan should be retrievable"
        assert retrieved_plan2.id == plan2.id, "Project 2 plan ID should match"
        
        # Try cross-project plan access
        cross_project_plan = await state_service.get_change_plan(project2.id, plan1.id)
        assert cross_project_plan is None, "Should not be able to access project 1's plan from project 2"
        
        cross_project_plan = await state_service.get_change_plan(project1.id, plan2.id)
        assert cross_project_plan is None, "Should not be able to access project 2's plan from project 1"
        
    finally:
        # Clean up resources
        if 'resource1' in locals():
            await mcp_client.delete_resource(project1.id, resource1.id)
        if 'resource2' in locals():
            await mcp_client.delete_resource(project2.id, resource2.id)


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])