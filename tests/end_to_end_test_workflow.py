"""
End-to-end tests for AWS Infrastructure Manager

These tests validate the complete workflow from resource creation to change plan execution.
They test the integration between all services in the system.

Environment variables:
- AWS_MCP_SERVER_URL: URL of the AWS MCP Server (default: http://localhost:8080)
- AWS_STATE_BUCKET: S3 bucket for state files (default: aws-infra-manager-test)
- AWS_STATE_BUCKET_PREFIX: Prefix for state files (default: e2e-test)
"""
import os
import pytest
import uuid
import boto3
import asyncio
from datetime import datetime

from src.services.aws_mcp_client import create_aws_mcp_client
from src.services.s3_state_management import S3StateManagementService
from src.services.project_management import ProjectManagementServiceImpl
from src.services.infrastructure_service import create_infrastructure_service
from src.services.change_plan_engine import DefaultChangePlanEngine
from src.services.approval_workflow import ApprovalWorkflowServiceImpl
from src.models.data_models import (
    ProjectConfig, ProjectSettings, NotificationConfig,
    ResourceConfig, InfrastructureState, StateMetadata, Resource,
    ChangePlan, ResourceUpdate
)
from src.models.enums import ResourceStatus, ChangePlanStatus

# Get configuration from environment variables
MCP_SERVER_URL = os.environ.get("AWS_MCP_SERVER_URL", "http://localhost:8080")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TEST_BUCKET = os.environ.get("AWS_STATE_BUCKET", "aws-infra-manager-test")
TEST_PREFIX = os.environ.get("AWS_STATE_BUCKET_PREFIX", "e2e-test")


@pytest.fixture(scope="module")
def aws_session():
    """Create AWS session for testing"""
    return boto3.Session(region_name=AWS_REGION)


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
async def project_service():
    """Create project management service for testing"""
    return ProjectManagementServiceImpl()


@pytest.fixture
async def change_plan_engine(state_service):
    """Create change plan engine for testing"""
    return DefaultChangePlanEngine(state_service)


@pytest.fixture
async def approval_service():
    """Create approval workflow service for testing"""
    return ApprovalWorkflowServiceImpl()


@pytest.fixture
async def infrastructure_service(mcp_client, state_service, change_plan_engine):
    """Create infrastructure service for testing"""
    return create_infrastructure_service(
        aws_mcp_client=mcp_client,
        state_service=state_service,
        change_plan_engine=change_plan_engine
    )


@pytest.fixture
async def test_project(project_service):
    """Create test project for end-to-end testing"""
    # Create project settings
    settings = ProjectSettings(
        s3_bucket_path=f"s3://{TEST_BUCKET}/{TEST_PREFIX}/e2e-test",
        default_region="us-east-1",
        notification_settings=NotificationConfig(
            email_notifications=True,
            notification_events=["approval_required"]
        )
    )
    
    # Create project config
    config = ProjectConfig(
        name=f"E2E Test Project {uuid.uuid4().hex[:8]}",
        description="End-to-end test project for workflow testing",
        owner="e2e-test-user",
        settings=settings
    )
    
    # Create project
    project = await project_service.create_project(config)
    
    return project


@pytest.mark.end_to_end
@pytest.mark.asyncio
async def test_complete_workflow(
    test_project, 
    infrastructure_service, 
    state_service, 
    change_plan_engine, 
    approval_service
):
    """Test complete workflow from resource creation to change plan execution"""
    project_id = test_project.id
    
    # Step 1: Create initial resources
    print(f"Step 1: Creating initial resources for project {project_id}")
    
    # Create EC2 instance
    ec2_config = ResourceConfig(
        type="EC2::Instance",
        name=f"e2e-test-instance-{uuid.uuid4().hex[:8]}",
        properties={
            "instanceType": "t3.micro",
            "imageId": "ami-12345678",
            "subnetId": "subnet-12345678"
        },
        tags={
            "Environment": "test",
            "CreatedBy": "e2e-test"
        }
    )
    
    ec2_resource = await infrastructure_service.create_resource(project_id, ec2_config)
    assert ec2_resource.id is not None, "EC2 instance should be created"
    assert ec2_resource.type == "EC2::Instance", "Resource type should match"
    
    # Create S3 bucket
    s3_config = ResourceConfig(
        type="S3::Bucket",
        name=f"e2e-test-bucket-{uuid.uuid4().hex[:8]}",
        properties={
            "versioning": True,
            "region": "us-east-1"
        },
        tags={
            "Environment": "test",
            "CreatedBy": "e2e-test"
        }
    )
    
    s3_resource = await infrastructure_service.create_resource(project_id, s3_config)
    assert s3_resource.id is not None, "S3 bucket should be created"
    assert s3_resource.type == "S3::Bucket", "Resource type should match"
    
    # Step 2: Verify resources were created and state was saved
    print("Step 2: Verifying resources and state")
    
    # Get current state
    current_state = await state_service.get_current_state(project_id)
    assert current_state is not None, "State should be saved"
    assert len(current_state.resources) == 2, "State should contain 2 resources"
    
    # Get resources
    resources = await infrastructure_service.get_resources(project_id)
    assert len(resources) == 2, "Should have 2 resources"
    assert any(r.id == ec2_resource.id for r in resources), "EC2 resource should be in the list"
    assert any(r.id == s3_resource.id for r in resources), "S3 resource should be in the list"
    
    # Step 3: Create desired state with changes
    print("Step 3: Creating desired state with changes")
    
    # Update EC2 instance type
    updated_ec2 = Resource(
        id=ec2_resource.id,
        project_id=project_id,
        type=ec2_resource.type,
        name=ec2_resource.name,
        region=ec2_resource.region,
        properties={
            **ec2_resource.properties,
            "instanceType": "t3.small"  # Changed from t3.micro
        },
        tags=ec2_resource.tags,
        status=ec2_resource.status,
        created_at=ec2_resource.created_at,
        updated_at=datetime.now(),
        arn=ec2_resource.arn
    )
    
    # Add a new resource (RDS instance)
    rds_resource = Resource(
        id=f"db-{uuid.uuid4().hex[:16]}",
        project_id=project_id,
        type="RDS::DBInstance",
        name=f"e2e-test-db-{uuid.uuid4().hex[:8]}",
        region="us-east-1",
        properties={
            "dbInstanceClass": "db.t3.micro",
            "engine": "mysql",
            "allocatedStorage": 20,
            "masterUsername": "admin"
        },
        tags={
            "Environment": "test",
            "CreatedBy": "e2e-test"
        },
        status=ResourceStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # Create desired state (update EC2, add RDS, keep S3)
    desired_state = InfrastructureState(
        project_id=project_id,
        version="1.1.0",
        timestamp=datetime.now(),
        resources=[updated_ec2, s3_resource, rds_resource],
        metadata=StateMetadata(
            last_modified_by="e2e-test",
            change_description="Update EC2 instance type and add RDS instance"
        )
    )
    
    # Step 4: Generate change plan
    print("Step 4: Generating change plan")
    
    change_plan = await infrastructure_service.generate_change_plan(project_id, desired_state)
    assert change_plan is not None, "Change plan should be generated"
    assert change_plan.summary.total_changes == 2, "Should have 2 changes"
    assert change_plan.summary.creates == 1, "Should have 1 create"
    assert change_plan.summary.updates == 1, "Should have 1 update"
    
    # Save change plan
    await state_service.save_change_plan(project_id, change_plan)
    
    # Step 5: Submit for approval and approve
    print("Step 5: Submitting for approval and approving")
    
    # Submit for approval
    approval_id = await approval_service.submit_for_approval(change_plan)
    assert approval_id is not None, "Approval request should be created"
    
    # Approve the plan
    approved_plan = await approval_service.approve_plan(change_plan.id, "e2e-test-approver")
    assert approved_plan.status == ChangePlanStatus.APPROVED, "Plan should be approved"
    
    # Save approved plan
    await state_service.save_change_plan(project_id, approved_plan)
    
    # Step 6: Execute approved changes
    print("Step 6: Executing approved changes")
    
    # Update EC2 instance
    update_changes = [c for c in approved_plan.changes if c.action.value == "update"]
    for change in update_changes:
        resource_id = change.resource_id
        updates = ResourceUpdate(
            properties=change.desired_config.properties if change.desired_config else None,
            tags=change.desired_config.tags if change.desired_config else None
        )
        updated_resource = await infrastructure_service.update_resource(project_id, resource_id, updates)
        assert updated_resource is not None, f"Resource {resource_id} should be updated"
    
    # Create new resources
    create_changes = [c for c in approved_plan.changes if c.action.value == "create"]
    for change in create_changes:
        resource_config = change.desired_config
        created_resource = await infrastructure_service.create_resource(project_id, resource_config)
        assert created_resource is not None, f"Resource {resource_config.name} should be created"
    
    # Step 7: Verify final state
    print("Step 7: Verifying final state")
    
    # Get updated resources
    final_resources = await infrastructure_service.get_resources(project_id)
    assert len(final_resources) == 3, "Should have 3 resources"
    
    # Verify EC2 instance was updated
    ec2 = next((r for r in final_resources if r.id == ec2_resource.id), None)
    assert ec2 is not None, "EC2 instance should exist"
    assert ec2.properties["instanceType"] == "t3.small", "EC2 instance type should be updated"
    
    # Verify RDS instance was created
    rds = next((r for r in final_resources if r.type == "RDS::DBInstance"), None)
    assert rds is not None, "RDS instance should be created"
    
    # Verify S3 bucket still exists
    s3 = next((r for r in final_resources if r.id == s3_resource.id), None)
    assert s3 is not None, "S3 bucket should still exist"
    
    # Get final state
    final_state = await state_service.get_current_state(project_id)
    assert final_state is not None, "Final state should be saved"
    assert len(final_state.resources) == 3, "Final state should contain 3 resources"
    
    print("End-to-end workflow test completed successfully")
    
    # Clean up resources
    print("Cleaning up resources")
    for resource in final_resources:
        await infrastructure_service.delete_resource(project_id, resource.id)


@pytest.mark.end_to_end
@pytest.mark.asyncio
async def test_project_isolation_workflow(
    project_service,
    infrastructure_service,
    state_service
):
    """Test that workflows are properly isolated between projects"""
    # Create two test projects
    settings1 = ProjectSettings(
        s3_bucket_path=f"s3://{TEST_BUCKET}/{TEST_PREFIX}/isolation-test-1",
        default_region="us-east-1",
        notification_settings=NotificationConfig(
            email_notifications=True,
            notification_events=["approval_required"]
        )
    )
    
    settings2 = ProjectSettings(
        s3_bucket_path=f"s3://{TEST_BUCKET}/{TEST_PREFIX}/isolation-test-2",
        default_region="us-east-1",
        notification_settings=NotificationConfig(
            email_notifications=True,
            notification_events=["approval_required"]
        )
    )
    
    config1 = ProjectConfig(
        name=f"Isolation Test Project 1 {uuid.uuid4().hex[:8]}",
        description="First project for isolation testing",
        owner="isolation-test-user",
        settings=settings1
    )
    
    config2 = ProjectConfig(
        name=f"Isolation Test Project 2 {uuid.uuid4().hex[:8]}",
        description="Second project for isolation testing",
        owner="isolation-test-user",
        settings=settings2
    )
    
    project1 = await project_service.create_project(config1)
    project2 = await project_service.create_project(config2)
    
    print(f"Created test projects: {project1.id} and {project2.id}")
    
    try:
        # Create resources in both projects
        ec2_config1 = ResourceConfig(
            type="EC2::Instance",
            name=f"isolation-test-instance-1-{uuid.uuid4().hex[:8]}",
            properties={
                "instanceType": "t3.micro",
                "imageId": "ami-12345678"
            },
            tags={"Project": "Project1", "IsolationTest": "true"}
        )
        
        ec2_config2 = ResourceConfig(
            type="EC2::Instance",
            name=f"isolation-test-instance-2-{uuid.uuid4().hex[:8]}",
            properties={
                "instanceType": "t3.large",
                "imageId": "ami-87654321"
            },
            tags={"Project": "Project2", "IsolationTest": "true"}
        )
        
        # Create resources
        resource1 = await infrastructure_service.create_resource(project1.id, ec2_config1)
        resource2 = await infrastructure_service.create_resource(project2.id, ec2_config2)
        
        print(f"Created resources: {resource1.id} in project1, {resource2.id} in project2")
        
        # Verify resources were created
        assert resource1.id is not None, "Project 1 resource should be created"
        assert resource2.id is not None, "Project 2 resource should be created"
        
        # Get resources for each project
        project1_resources = await infrastructure_service.get_resources(project1.id)
        project2_resources = await infrastructure_service.get_resources(project2.id)
        
        # Verify project 1 resources
        assert len(project1_resources) == 1, "Project 1 should have 1 resource"
        assert project1_resources[0].id == resource1.id, "Project 1 should contain its resource"
        
        # Verify project 2 resources
        assert len(project2_resources) == 1, "Project 2 should have 1 resource"
        assert project2_resources[0].id == resource2.id, "Project 2 should contain its resource"
        
        # Verify states are isolated
        state1 = await state_service.get_current_state(project1.id)
        state2 = await state_service.get_current_state(project2.id)
        
        assert state1 is not None, "Project 1 state should exist"
        assert state2 is not None, "Project 2 state should exist"
        assert len(state1.resources) == 1, "Project 1 state should have 1 resource"
        assert len(state2.resources) == 1, "Project 2 state should have 1 resource"
        assert state1.resources[0].id == resource1.id, "Project 1 state should contain its resource"
        assert state2.resources[0].id == resource2.id, "Project 2 state should contain its resource"
        
        # Try to access project 1's resource from project 2 (should not be possible)
        project2_resources = await infrastructure_service.get_resources(project2.id)
        assert not any(r.id == resource1.id for r in project2_resources), "Project 2 should not see project 1's resource"
        
        print("Project isolation test completed successfully")
        
    finally:
        # Clean up resources
        print("Cleaning up resources")
        try:
            await infrastructure_service.delete_resource(project1.id, resource1.id)
        except Exception as e:
            print(f"Error cleaning up resource1: {e}")
        
        try:
            await infrastructure_service.delete_resource(project2.id, resource2.id)
        except Exception as e:
            print(f"Error cleaning up resource2: {e}")


@pytest.mark.end_to_end
@pytest.mark.asyncio
async def test_api_endpoints_integration(
    test_project,
    infrastructure_service,
    state_service,
    change_plan_engine,
    approval_service
):
    """Test integration between API endpoints using service calls"""
    project_id = test_project.id
    
    # Step 1: Create a resource
    print(f"Step 1: Creating resource for project {project_id}")
    
    resource_config = ResourceConfig(
        type="EC2::Instance",
        name=f"api-test-instance-{uuid.uuid4().hex[:8]}",
        properties={
            "instanceType": "t3.micro",
            "imageId": "ami-12345678"
        },
        tags={
            "Environment": "test",
            "CreatedBy": "api-test"
        }
    )
    
    resource = await infrastructure_service.create_resource(project_id, resource_config)
    assert resource.id is not None, "Resource should be created"
    
    # Step 2: List resources
    print("Step 2: Listing resources")
    
    resources = await infrastructure_service.get_resources(project_id)
    assert len(resources) >= 1, "Should have at least one resource"
    assert any(r.id == resource.id for r in resources), "Created resource should be in the list"
    
    # Step 3: Create a change plan
    print("Step 3: Creating change plan")
    
    # Update the resource
    updated_resource = Resource(
        id=resource.id,
        project_id=project_id,
        type=resource.type,
        name=resource.name,
        region=resource.region,
        properties={
            **resource.properties,
            "instanceType": "t3.medium"  # Changed from t3.micro
        },
        tags=resource.tags,
        status=resource.status,
        created_at=resource.created_at,
        updated_at=datetime.now(),
        arn=resource.arn
    )
    
    desired_state = InfrastructureState(
        project_id=project_id,
        version="1.1.0",
        timestamp=datetime.now(),
        resources=[updated_resource],
        metadata=StateMetadata(
            last_modified_by="api-test",
            change_description="Update instance type"
        )
    )
    
    change_plan = await infrastructure_service.generate_change_plan(project_id, desired_state)
    assert change_plan is not None, "Change plan should be generated"
    assert change_plan.summary.total_changes == 1, "Should have 1 change"
    
    # Save change plan
    await state_service.save_change_plan(project_id, change_plan)
    
    # Step 4: List change plans
    print("Step 4: Listing change plans")
    
    plans = await state_service.list_change_plans(project_id)
    assert len(plans) >= 1, "Should have at least one plan"
    assert any(p.id == change_plan.id for p in plans), "Created plan should be in the list"
    
    # Step 5: Get specific change plan
    print("Step 5: Getting specific change plan")
    
    retrieved_plan = await state_service.get_change_plan(project_id, change_plan.id)
    assert retrieved_plan is not None, "Should retrieve the plan"
    assert retrieved_plan.id == change_plan.id, "Plan ID should match"
    
    # Step 6: Submit for approval
    print("Step 6: Submitting for approval")
    
    approval_id = await approval_service.submit_for_approval(change_plan)
    assert approval_id is not None, "Approval request should be created"
    
    # Step 7: Approve the plan
    print("Step 7: Approving the plan")
    
    approved_plan = await approval_service.approve_plan(change_plan.id, "api-test-approver")
    assert approved_plan.status == ChangePlanStatus.APPROVED, "Plan should be approved"
    
    # Save approved plan
    await state_service.save_change_plan(project_id, approved_plan)
    
    # Step 8: Execute the change
    print("Step 8: Executing the change")
    
    updates = ResourceUpdate(
        properties={"instanceType": "t3.medium"},
        tags=None
    )
    
    updated_resource = await infrastructure_service.update_resource(project_id, resource.id, updates)
    assert updated_resource is not None, "Resource should be updated"
    assert updated_resource.properties["instanceType"] == "t3.medium", "Instance type should be updated"
    
    # Step 9: Verify state was updated
    print("Step 9: Verifying state was updated")
    
    final_state = await state_service.get_current_state(project_id)
    assert final_state is not None, "Final state should exist"
    
    final_resource = next((r for r in final_state.resources if r.id == resource.id), None)
    assert final_resource is not None, "Resource should be in final state"
    assert final_resource.properties["instanceType"] == "t3.medium", "Instance type should be updated in state"
    
    print("API endpoints integration test completed successfully")
    
    # Clean up
    print("Cleaning up resources")
    await infrastructure_service.delete_resource(project_id, resource.id)


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])