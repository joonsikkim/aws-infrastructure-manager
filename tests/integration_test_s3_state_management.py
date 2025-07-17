"""
Integration tests for S3 State Management Service

These tests validate the integration between the S3 State Management Service and AWS S3.
They require valid AWS credentials with S3 access to execute successfully.

Environment variables:
- AWS_ACCESS_KEY_ID: AWS access key
- AWS_SECRET_ACCESS_KEY: AWS secret key
- AWS_REGION: AWS region (default: us-east-1)
- AWS_STATE_BUCKET: S3 bucket for state files (default: aws-infra-manager-test)
- AWS_STATE_BUCKET_PREFIX: Prefix for state files (default: integration-test)
"""
import os
import pytest
import uuid
import boto3
import json
from datetime import datetime
from botocore.exceptions import ClientError

from src.services.s3_state_management import S3StateManagementService
from src.models.data_models import (
    InfrastructureState, StateMetadata, Resource, ResourceConfig,
    ChangePlan, Change, ChangeAction, ChangeSummary
)
from src.models.enums import ResourceStatus, ChangePlanStatus, RiskLevel
from src.models.exceptions import InfrastructureException

# Get configuration from environment variables
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TEST_BUCKET = os.environ.get("AWS_STATE_BUCKET", "aws-infra-manager-test")
TEST_PREFIX = os.environ.get("AWS_STATE_BUCKET_PREFIX", "integration-test")


@pytest.fixture(scope="module")
def aws_session():
    """Create AWS session for testing"""
    return boto3.Session(region_name=AWS_REGION)


@pytest.fixture(scope="module")
async def ensure_test_bucket(aws_session):
    """Ensure test bucket exists"""
    s3_client = aws_session.client('s3')
    
    try:
        s3_client.head_bucket(Bucket=TEST_BUCKET)
        print(f"Using existing bucket: {TEST_BUCKET}")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            print(f"Creating test bucket: {TEST_BUCKET}")
            if AWS_REGION == 'us-east-1':
                s3_client.create_bucket(Bucket=TEST_BUCKET)
            else:
                s3_client.create_bucket(
                    Bucket=TEST_BUCKET,
                    CreateBucketConfiguration={'LocationConstraint': AWS_REGION}
                )
        else:
            pytest.skip(f"Cannot access S3 bucket: {e}")
    
    yield TEST_BUCKET
    
    # We don't delete the bucket after tests as it might be used by other tests
    # In a real CI/CD pipeline, you might want to clean up resources


@pytest.fixture
def test_project_id():
    """Generate unique project ID for tests"""
    return f"test-project-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def sample_resource(test_project_id):
    """Create sample resource for testing"""
    return Resource(
        id=f"i-{uuid.uuid4().hex[:16]}",
        project_id=test_project_id,
        type="EC2::Instance",
        name="test-instance",
        region="us-east-1",
        properties={
            "instanceType": "t3.micro",
            "imageId": "ami-12345678"
        },
        tags={"Environment": "test", "CreatedBy": "integration-test"},
        status=ResourceStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        arn=f"arn:aws:ec2:us-east-1:123456789012:instance/i-{uuid.uuid4().hex[:16]}"
    )


@pytest.fixture
def sample_state(test_project_id, sample_resource):
    """Create sample infrastructure state for testing"""
    metadata = StateMetadata(
        last_modified_by="integration-test",
        change_description="Initial state",
        change_plan_id=f"plan-{uuid.uuid4().hex[:8]}"
    )
    
    return InfrastructureState(
        project_id=test_project_id,
        version="1.0.0",
        timestamp=datetime.now(),
        resources=[sample_resource],
        metadata=metadata
    )


@pytest.fixture
async def state_service(ensure_test_bucket, aws_session):
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_get_state(state_service, test_project_id, sample_state):
    """Test saving and retrieving state"""
    # Save state
    await state_service.save_state(test_project_id, sample_state)
    
    # Get state
    retrieved_state = await state_service.get_current_state(test_project_id)
    
    # Verify
    assert retrieved_state is not None, "State should be retrievable"
    assert retrieved_state.project_id == test_project_id, "Project ID should match"
    assert retrieved_state.version == sample_state.version, "Version should match"
    assert len(retrieved_state.resources) == len(sample_state.resources), "Resource count should match"
    assert retrieved_state.resources[0].id == sample_state.resources[0].id, "Resource ID should match"
    assert retrieved_state.metadata.last_modified_by == "integration-test", "Metadata should match"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_state_history(state_service, test_project_id, sample_state):
    """Test state history functionality"""
    # Save initial state
    await state_service.save_state(test_project_id, sample_state)
    
    # Create updated state
    updated_resource = Resource(
        id=sample_state.resources[0].id,
        project_id=test_project_id,
        type=sample_state.resources[0].type,
        name=sample_state.resources[0].name,
        region=sample_state.resources[0].region,
        properties={
            "instanceType": "t3.small",  # Changed from t3.micro
            "imageId": sample_state.resources[0].properties["imageId"]
        },
        tags=sample_state.resources[0].tags,
        status=ResourceStatus.ACTIVE,
        created_at=sample_state.resources[0].created_at,
        updated_at=datetime.now(),
        arn=sample_state.resources[0].arn
    )
    
    updated_metadata = StateMetadata(
        last_modified_by="integration-test",
        change_description="Updated instance type",
        change_plan_id=f"plan-{uuid.uuid4().hex[:8]}"
    )
    
    updated_state = InfrastructureState(
        project_id=test_project_id,
        version="1.1.0",
        timestamp=datetime.now(),
        resources=[updated_resource],
        metadata=updated_metadata
    )
    
    # Save updated state
    await state_service.save_state(test_project_id, updated_state)
    
    # Get history
    history = await state_service.get_state_history(test_project_id)
    
    # Verify
    assert len(history) >= 1, "Should have at least one history entry"
    assert history[0].version in ["1.0.0", "1.1.0"], "Version should match one of the saved states"
    assert "s3://" in history[0].s3_location, "S3 location should be a valid S3 URI"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_compare_states(state_service, test_project_id, sample_state):
    """Test state comparison functionality"""
    # Create current state
    current_state = sample_state
    
    # Create desired state with changes
    new_resource = Resource(
        id=f"i-{uuid.uuid4().hex[:16]}",
        project_id=test_project_id,
        type="EC2::Instance",
        name="new-instance",
        region="us-east-1",
        properties={
            "instanceType": "t3.large",
            "imageId": "ami-87654321"
        },
        tags={"Environment": "test", "CreatedBy": "integration-test"},
        status=ResourceStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        arn=f"arn:aws:ec2:us-east-1:123456789012:instance/i-{uuid.uuid4().hex[:16]}"
    )
    
    # Updated version of existing resource
    updated_resource = Resource(
        id=sample_state.resources[0].id,
        project_id=test_project_id,
        type=sample_state.resources[0].type,
        name=sample_state.resources[0].name,
        region=sample_state.resources[0].region,
        properties={
            "instanceType": "t3.medium",  # Changed
            "imageId": sample_state.resources[0].properties["imageId"]
        },
        tags=sample_state.resources[0].tags,
        status=ResourceStatus.ACTIVE,
        created_at=sample_state.resources[0].created_at,
        updated_at=datetime.now(),
        arn=sample_state.resources[0].arn
    )
    
    desired_metadata = StateMetadata(
        last_modified_by="integration-test",
        change_description="Desired state with changes",
        change_plan_id=None
    )
    
    desired_state = InfrastructureState(
        project_id=test_project_id,
        version="2.0.0",
        timestamp=datetime.now(),
        resources=[updated_resource, new_resource],
        metadata=desired_metadata
    )
    
    # Compare states
    plan = state_service.compare_states(current_state, desired_state)
    
    # Verify
    assert plan.project_id == test_project_id, "Project ID should match"
    assert plan.summary.total_changes == 2, "Should have 2 changes"
    assert plan.summary.creates == 1, "Should have 1 create"
    assert plan.summary.updates == 1, "Should have 1 update"
    assert plan.summary.deletes == 0, "Should have 0 deletes"
    
    # Verify changes
    create_change = next((c for c in plan.changes if c.action == ChangeAction.CREATE), None)
    assert create_change is not None, "Should have a create change"
    assert create_change.resource_id == new_resource.id, "Create change should reference new resource"
    
    update_change = next((c for c in plan.changes if c.action == ChangeAction.UPDATE), None)
    assert update_change is not None, "Should have an update change"
    assert update_change.resource_id == updated_resource.id, "Update change should reference updated resource"
    assert update_change.current_config is not None, "Update change should have current config"
    assert update_change.desired_config is not None, "Update change should have desired config"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_change_plan_save_and_retrieve(state_service, test_project_id):
    """Test saving and retrieving change plans"""
    # Create a change plan
    changes = [
        Change(
            action=ChangeAction.CREATE,
            resource_type="EC2::Instance",
            resource_id=f"i-{uuid.uuid4().hex[:16]}",
            desired_config=ResourceConfig(
                type="EC2::Instance",
                name="new-instance",
                properties={"instanceType": "t3.micro"},
                tags={"Environment": "test"}
            ),
            risk_level=RiskLevel.LOW
        ),
        Change(
            action=ChangeAction.UPDATE,
            resource_type="EC2::Instance",
            resource_id=f"i-{uuid.uuid4().hex[:16]}",
            current_config=ResourceConfig(
                type="EC2::Instance",
                name="existing-instance",
                properties={"instanceType": "t3.micro"},
                tags={"Environment": "test"}
            ),
            desired_config=ResourceConfig(
                type="EC2::Instance",
                name="existing-instance",
                properties={"instanceType": "t3.small"},
                tags={"Environment": "test"}
            ),
            risk_level=RiskLevel.MEDIUM
        )
    ]
    
    summary = ChangeSummary(
        total_changes=2,
        creates=1,
        updates=1,
        deletes=0
    )
    
    plan_id = f"plan-{uuid.uuid4().hex[:8]}"
    plan = ChangePlan(
        id=plan_id,
        project_id=test_project_id,
        summary=summary,
        changes=changes,
        created_at=datetime.now(),
        status=ChangePlanStatus.PENDING,
        created_by="integration-test"
    )
    
    # Save plan
    await state_service.save_change_plan(test_project_id, plan)
    
    # Retrieve plan
    retrieved_plan = await state_service.get_change_plan(test_project_id, plan_id)
    
    # Verify
    assert retrieved_plan is not None, "Plan should be retrievable"
    assert retrieved_plan.id == plan_id, "Plan ID should match"
    assert retrieved_plan.project_id == test_project_id, "Project ID should match"
    assert retrieved_plan.summary.total_changes == 2, "Summary should match"
    assert len(retrieved_plan.changes) == 2, "Changes should match"
    assert retrieved_plan.status == ChangePlanStatus.PENDING, "Status should match"
    
    # List plans
    plans = await state_service.list_change_plans(test_project_id)
    assert len(plans) >= 1, "Should have at least one plan"
    assert any(p.id == plan_id for p in plans), "Created plan should be in the list"


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])