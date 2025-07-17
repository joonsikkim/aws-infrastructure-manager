"""
Tests for S3 State Management Service
"""
import json
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from moto import mock_aws
import os
import boto3
from botocore.exceptions import ClientError

# Mock settings before importing the service
with patch.dict('os.environ', {
    'SECRET_KEY': 'test-secret-key',
    'AWS_ACCESS_KEY_ID': 'test-key',
    'AWS_SECRET_ACCESS_KEY': 'test-secret',
    'AWS_REGION': 'us-east-1',
    'AWS_STATE_BUCKET': 'test-bucket',
    'AWS_STATE_BUCKET_PREFIX': 'projects'
}):
    from src.services.s3_state_management import S3StateManagementService
from src.models.data_models import (
    InfrastructureState, StateMetadata, Resource, StateSnapshot,
    ChangePlan, Change, ChangeAction, RiskLevel
)
from src.models.enums import ResourceStatus, ChangePlanStatus
from src.models.exceptions import InfrastructureException, ErrorCodes


@pytest.fixture
def mock_settings():
    """Mock settings for testing"""
    with patch('src.services.s3_state_management.settings') as mock_settings:
        mock_settings.aws.access_key_id = 'testing'
        mock_settings.aws.secret_access_key = 'testing'
        mock_settings.aws.session_token = 'testing'
        mock_settings.aws.region = "us-east-1"
        mock_settings.aws.profile = "" # Explicitly set to empty string
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        yield mock_settings


@pytest.fixture
def sample_resource():
    """Sample resource for testing"""
    return Resource(
        id="i-1234567890abcdef0",
        project_id="test-project",
        type="EC2::Instance",
        name="test-instance",
        region="us-east-1",
        properties={
            "instanceType": "t3.micro",
            "imageId": "ami-12345678"
        },
        tags={"Environment": "test"},
        status=ResourceStatus.ACTIVE,
        created_at=datetime(2024, 1, 1, 10, 0, 0),
        updated_at=datetime(2024, 1, 1, 10, 0, 0),
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    )


@pytest.fixture
def sample_state(sample_resource):
    """Sample infrastructure state for testing"""
    metadata = StateMetadata(
        last_modified_by="test-user",
        change_description="Initial state",
        change_plan_id="plan-123"
    )
    
    return InfrastructureState(
        project_id="test-project",
        version="1.0.0",
        timestamp=datetime(2024, 1, 1, 10, 0, 0),
        resources=[sample_resource],
        metadata=metadata
    )


@mock_aws
class TestS3StateManagementService:
    """Test cases for S3StateManagementService"""
    
    def setup_method(self, method):
        """Set up test environment"""
        # Set dummy AWS credentials for moto
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_SECURITY_TOKEN"] = "testing"
        os.environ["AWS_SESSION_TOKEN"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        # Create mock S3 bucket
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        self.s3_client.create_bucket(Bucket='test-bucket')
    
    @patch('src.services.s3_state_management.settings')
    def test_init_creates_service(self, mock_settings):
        """Test service initialization"""
        mock_settings.aws.access_key_id = 'test-key'
        mock_settings.aws.secret_access_key = 'test-secret'
        mock_settings.aws.session_token = None
        mock_settings.aws.region = "us-east-1"
        mock_settings.aws.profile = None
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        assert service.bucket_name == 'test-bucket'
        assert service.bucket_prefix == 'projects'
    
    @patch('src.services.s3_state_management.settings')
    def test_get_state_key(self, mock_settings):
        """Test S3 key generation"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        
        # Test current state key
        key = service._get_state_key("test-project")
        assert key == "projects/test-project/state/current.json"
        
        # Test versioned state key
        key = service._get_state_key("test-project", "v1.0.0")
        assert key == "projects/test-project/state/v1.0.0.json"
    
    @patch('src.services.s3_state_management.settings')
    def test_get_history_key(self, mock_settings):
        """Test historical state key generation"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        timestamp = datetime(2024, 1, 1, 10, 30, 45, 123456)
        
        key = service._get_history_key("test-project", timestamp)
        assert key == "projects/test-project/history/20240101_103045_123456.json"
    
    @patch('src.services.s3_state_management.settings')
    @patch('src.services.s3_state_management.boto3')
    async def test_get_current_state_success(self, mock_boto3, mock_settings, sample_state):
        """Test successful retrieval of current state"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        # Mock S3 response
        mock_s3_client = Mock()
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        state_data = {
            "version": "1.0.0",
            "projectId": "test-project",
            "timestamp": "2024-01-01T10:00:00",
            "metadata": {
                "lastModifiedBy": "test-user",
                "changeDescription": "Initial state",
                "changePlanId": "plan-123"
            },
            "resources": [{
                "id": "i-1234567890abcdef0",
                "type": "EC2::Instance",
                "name": "test-instance",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                "region": "us-east-1",
                "properties": {"instanceType": "t3.micro", "imageId": "ami-12345678"},
                "tags": {"Environment": "test"},
                "status": "active",
                "createdAt": "2024-01-01T10:00:00",
                "updatedAt": "2024-01-01T10:00:00"
            }]
        }
        
        mock_s3_client.get_object.return_value = {'Body': Mock(read=Mock(return_value=json.dumps(state_data).encode('utf-8')))}
        
        service = S3StateManagementService()
        result = await service.get_current_state("test-project")
        
        assert result is not None
        assert result.project_id == "test-project"
        assert result.version == "1.0.0"
        assert len(result.resources) == 1
        assert result.resources[0].id == "i-1234567890abcdef0"
    
    @patch('src.services.s3_state_management.settings')
    @patch('src.services.s3_state_management.boto3')
    async def test_get_current_state_not_found(self, mock_boto3, mock_settings):
        """Test retrieval when state doesn't exist"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        # Mock S3 client to raise NoSuchKey error
        mock_s3_client = Mock()
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        error_response = {'Error': {'Code': 'NoSuchKey'}}
        mock_s3_client.get_object.side_effect = ClientError(error_response, 'GetObject')
        
        service = S3StateManagementService()
        result = await service.get_current_state("test-project")
        
        assert result is None
    
    @patch('src.services.s3_state_management.settings')
    @patch('src.services.s3_state_management.boto3')
    async def test_save_state_success(self, mock_boto3, mock_settings, sample_state):
        """Test successful state saving"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        # Mock S3 client
        mock_s3_client = Mock()
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        # Mock get_current_state to return None (no existing state)
        mock_s3_client.get_object.side_effect = [
            # First call for get_current_state
            ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')
        ]
        
        service = S3StateManagementService()
        await service.save_state("test-project", sample_state)
        
        # Verify put_object was called
        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args
        
        assert call_args[1]['Bucket'] == 'test-bucket'
        assert call_args[1]['Key'] == 'projects/test-project/state/current.json'
        assert call_args[1]['ContentType'] == 'application/json'
        
        # Verify metadata
        metadata = call_args[1]['Metadata']
        assert metadata['project-id'] == 'test-project'
        assert metadata['version'] == '1.0.0'
        assert metadata['last-modified-by'] == 'test-user'
    
    @patch('src.services.s3_state_management.settings')
    @patch('src.services.s3_state_management.boto3')
    async def test_get_state_history_success(self, mock_boto3, mock_settings):
        """Test successful retrieval of state history"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        # Mock S3 client
        mock_s3_client = Mock()
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        # Mock list_objects_v2 response
        mock_s3_client.list_objects_v2.return_value = {
            'Contents': [
                {
                    'Key': 'projects/test-project/history/20240101_100000_000000.json',
                    'LastModified': datetime(2024, 1, 1, 10, 0, 0)
                },
                {
                    'Key': 'projects/test-project/history/20240101_110000_000000.json',
                    'LastModified': datetime(2024, 1, 1, 11, 0, 0)
                }
            ]
        }
        
        # Mock head_object responses for metadata
        mock_s3_client.head_object.return_value = {
            'Metadata': {
                'version': '1.0.0',
                'change-description': 'Test change'
            }
        }
        
        service = S3StateManagementService()
        history = await service.get_state_history("test-project")
        
        assert len(history) == 2
        assert all(isinstance(snapshot, StateSnapshot) for snapshot in history)
        assert history[0].timestamp > history[1].timestamp  # Newest first
    
    @patch('src.services.s3_state_management.settings')
    def test_compare_states_create_resource(self, mock_settings, sample_resource):
        """Test state comparison with resource creation"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        
        # Current state with no resources
        current_metadata = StateMetadata(
            last_modified_by="test-user",
            change_description="Empty state"
        )
        current_state = InfrastructureState(
            project_id="test-project",
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[],
            metadata=current_metadata
        )
        
        # Desired state with one resource
        desired_metadata = StateMetadata(
            last_modified_by="test-user",
            change_description="Add resource"
        )
        desired_state = InfrastructureState(
            project_id="test-project",
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[sample_resource],
            metadata=desired_metadata
        )
        
        plan = service.compare_states(current_state, desired_state)
        
        assert len(plan.changes) == 1
        assert plan.changes[0].action == ChangeAction.CREATE
        assert plan.changes[0].resource_id == sample_resource.id
        assert plan.summary.creates == 1
        assert plan.summary.updates == 0
        assert plan.summary.deletes == 0
    
    @patch('src.services.s3_state_management.settings')
    def test_compare_states_delete_resource(self, mock_settings, sample_resource):
        """Test state comparison with resource deletion"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        
        # Current state with one resource
        current_metadata = StateMetadata(
            last_modified_by="test-user",
            change_description="Has resource"
        )
        current_state = InfrastructureState(
            project_id="test-project",
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[sample_resource],
            metadata=current_metadata
        )
        
        # Desired state with no resources
        desired_metadata = StateMetadata(
            last_modified_by="test-user",
            change_description="Remove resource"
        )
        desired_state = InfrastructureState(
            project_id="test-project",
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[],
            metadata=desired_metadata
        )
        
        plan = service.compare_states(current_state, desired_state)
        
        assert len(plan.changes) == 1
        assert plan.changes[0].action == ChangeAction.DELETE
        assert plan.changes[0].resource_id == sample_resource.id
        assert plan.changes[0].risk_level == RiskLevel.HIGH  # Deletions are high risk
        assert plan.summary.creates == 0
        assert plan.summary.updates == 0
        assert plan.summary.deletes == 1
    
    @patch('src.services.s3_state_management.settings')
    def test_compare_states_update_resource(self, mock_settings, sample_resource):
        """Test state comparison with resource update"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        
        # Current state
        current_metadata = StateMetadata(
            last_modified_by="test-user",
            change_description="Current state"
        )
        current_state = InfrastructureState(
            project_id="test-project",
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[sample_resource],
            metadata=current_metadata
        )
        
        # Desired state with updated resource
        updated_resource = Resource(
            id=sample_resource.id,
            project_id=sample_resource.project_id,
            type=sample_resource.type,
            name=sample_resource.name,
            region=sample_resource.region,
            properties={
                "instanceType": "t3.small",  # Changed from t3.micro
                "imageId": "ami-12345678"
            },
            tags=sample_resource.tags,
            status=sample_resource.status,
            created_at=sample_resource.created_at,
            updated_at=datetime.now(),
            arn=sample_resource.arn
        )
        
        desired_metadata = StateMetadata(
            last_modified_by="test-user",
            change_description="Update resource"
        )
        desired_state = InfrastructureState(
            project_id="test-project",
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[updated_resource],
            metadata=desired_metadata
        )
        
        plan = service.compare_states(current_state, desired_state)
        
        assert len(plan.changes) == 1
        assert plan.changes[0].action == ChangeAction.UPDATE
        assert plan.changes[0].resource_id == sample_resource.id
        assert plan.summary.creates == 0
        assert plan.summary.updates == 1
        assert plan.summary.deletes == 0
    
    @patch('src.services.s3_state_management.settings')
    def test_assess_update_risk_high_risk_resource(self, mock_settings):
        """Test risk assessment for high-risk resource updates"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        
        # Create RDS instance (high-risk type)
        current_resource = Resource(
            id="db-instance-1",
            project_id="test-project",
            type="RDS::DBInstance",
            name="test-db",
            region="us-east-1",
            properties={"dbInstanceClass": "db.t3.micro"},
            tags={},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        desired_resource = Resource(
            id="db-instance-1",
            project_id="test-project",
            type="RDS::DBInstance",
            name="test-db",
            region="us-east-1",
            properties={"dbInstanceClass": "db.t3.small"},  # High-risk change
            tags={},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        risk = service._assess_update_risk(current_resource, desired_resource)
        assert risk == RiskLevel.HIGH
    
    @patch('src.services.s3_state_management.settings')
    def test_validate_state_structure_valid(self, mock_settings, sample_state):
        """Test state structure validation with valid state"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        assert service._validate_state_structure(sample_state) is True
    
    @patch('src.services.s3_state_management.settings')
    def test_validate_state_structure_invalid(self, mock_settings):
        """Test state structure validation with invalid state"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        
        # Create invalid state (missing project_id)
        invalid_metadata = StateMetadata(
            last_modified_by="test-user",
            change_description="Invalid state"
        )
        invalid_state = InfrastructureState(
            project_id="",  # Invalid empty project_id
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[],
            metadata=invalid_metadata
        )
        
        assert service._validate_state_structure(invalid_state) is False
    
    @patch('src.services.s3_state_management.settings')
    def test_serialize_deserialize_state(self, mock_settings, sample_state):
        """Test state serialization and deserialization"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        service = S3StateManagementService()
        
        # Serialize
        serialized = service._serialize_state(sample_state)
        
        # Verify serialized structure
        assert serialized["projectId"] == sample_state.project_id
        assert serialized["version"] == "1.0.0"
        assert len(serialized["resources"]) == 1
        
        # Deserialize
        deserialized = service._deserialize_state(serialized)
        
        # Verify deserialized state
        assert deserialized.project_id == sample_state.project_id
        assert deserialized.version == sample_state.version
        assert len(deserialized.resources) == 1
        assert deserialized.resources[0].id == sample_state.resources[0].id


@pytest.mark.asyncio
class TestS3StateManagementServiceIntegration:
    """Integration tests for S3StateManagementService"""
    
    @patch('src.services.s3_state_management.settings')
    @patch('src.services.s3_state_management.boto3')
    async def test_full_workflow(self, mock_boto3, mock_settings, sample_state):
        """Test complete workflow: save -> get -> history"""
        mock_settings.aws.state_bucket = 'test-bucket'
        mock_settings.aws.state_bucket_prefix = 'projects'
        
        # Mock S3 client
        mock_s3_client = Mock()
        mock_boto3.Session.return_value.client.return_value = mock_s3_client
        
        # Mock responses for the workflow
        mock_s3_client.get_object.side_effect = [
            # First call: get_current_state in save_state (no existing state)
            ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject'),
            # Second call: get_current_state after save
            Mock(Body=Mock(read=Mock(return_value=json.dumps({
                "version": "1.0.0",
                "projectId": "test-project",
                "timestamp": "2024-01-01T10:00:00",
                "metadata": {
                    "lastModifiedBy": "test-user",
                    "changeDescription": "Initial state",
                    "changePlanId": "plan-123"
                },
                "resources": [{
                    "id": "i-1234567890abcdef0",
                    "type": "EC2::Instance",
                    "name": "test-instance",
                    "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                    "region": "us-east-1",
                    "properties": {"instanceType": "t3.micro", "imageId": "ami-12345678"},
                    "tags": {"Environment": "test"},
                    "status": "active",
                    "createdAt": "2024-01-01T10:00:00",
                    "updatedAt": "2024-01-01T10:00:00"
                }]
            }).encode('utf-8'))),
            # Mock for get_object in get_state_history
            Mock(Body=Mock(read=Mock(return_value=json.dumps({
                "version": "1.0.0",
                "projectId": "test-project",
                "timestamp": "2024-01-01T10:00:00",
                "metadata": {
                    "lastModifiedBy": "test-user",
                    "changeDescription": "Initial state",
                    "changePlanId": "plan-123"
                },
                "resources": [{
                    "id": "i-1234567890abcdef0",
                    "type": "EC2::Instance",
                    "name": "test-instance",
                    "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                    "region": "us-east-1",
                    "properties": {"instanceType": "t3.micro", "imageId": "ami-12345678"},
                    "tags": {"Environment": "test"},
                    "status": "active",
                    "createdAt": "2024-01-01T10:00:00",
                    "updatedAt": "2024-01-01T10:00:00"
                }]
            }).encode('utf-8'))).configure_mock(Body=Mock(read=Mock(return_value=json.dumps({
                "version": "1.0.0",
                "projectId": "test-project",
                "timestamp": "2024-01-01T10:00:00",
                "metadata": {
                    "lastModifiedBy": "test-user",
                    "changeDescription": "Initial state",
                    "changePlanId": "plan-123"
                },
                "resources": [{
                    "id": "i-1234567890abcdef0",
                    "type": "EC2::Instance",
                    "name": "test-instance",
                    "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                    "region": "us-east-1",
                    "properties": {"instanceType": "t3.micro", "imageId": "ami-12345678"},
                    "tags": {"Environment": "test"},
                    "status": "active",
                    "createdAt": "2024-01-01T10:00:00",
                    "updatedAt": "2024-01-01T10:00:00"
                }]
            }).encode('utf-8'))))
        ]
        
        service = S3StateManagementService()
        
        # Save state
        await service.save_state("test-project", sample_state)
        
        # Get current state
        retrieved_state = await service.get_current_state("test-project")
        
        # Verify
        assert retrieved_state is not None
        assert retrieved_state.project_id == "test-project"
        assert len(retrieved_state.resources) == 1