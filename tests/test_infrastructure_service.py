"""
Unit tests for Infrastructure Service
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from typing import List, Optional

from src.services.infrastructure_service import AWSInfrastructureService, create_infrastructure_service
from src.services.aws_mcp_client import AWSMCPClient
from src.services.interfaces import StateManagementService, ChangePlanEngine
from src.models.data_models import (
    Resource, ResourceConfig, ResourceFilter, ResourceUpdate,
    InfrastructureState, ChangePlan, StateMetadata
)
from src.models.enums import ResourceStatus, ChangePlanStatus
from src.models.exceptions import InfrastructureException, ErrorCodes


# Global fixtures
@pytest.fixture
def mock_aws_mcp_client():
    """Mock AWS MCP client"""
    return AsyncMock(spec=AWSMCPClient)

@pytest.fixture
def mock_state_service():
    """Mock state management service"""
    return AsyncMock(spec=StateManagementService)

@pytest.fixture
def mock_change_plan_engine():
    """Mock change plan engine"""
    return AsyncMock(spec=ChangePlanEngine)

@pytest.fixture
def infrastructure_service(mock_aws_mcp_client, mock_state_service, mock_change_plan_engine):
    """Infrastructure service instance with mocked dependencies"""
    return AWSInfrastructureService(
        aws_mcp_client=mock_aws_mcp_client,
        state_service=mock_state_service,
        change_plan_engine=mock_change_plan_engine
    )

@pytest.fixture
def sample_resource_config():
    """Sample resource configuration"""
    return ResourceConfig(
        type="EC2::Instance",
        name="test-instance",
        properties={
            "InstanceType": "t3.micro",
            "ImageId": "ami-12345678"
        },
        tags={"Environment": "test"}
    )

@pytest.fixture
def sample_resource():
    """Sample resource"""
    return Resource(
        id="i-1234567890abcdef0",
        project_id="test-project",
        type="EC2::Instance",
        name="test-instance",
        region="us-east-1",
        properties={"InstanceType": "t3.micro"},
        tags={"ProjectId": "test-project", "Environment": "test"},
        status=ResourceStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    )

@pytest.fixture
def sample_infrastructure_state(sample_resource):
    """Sample infrastructure state"""
    return InfrastructureState(
        project_id="test-project",
        version="1.0.0",
        timestamp=datetime.now(),
        resources=[sample_resource],
        metadata=StateMetadata(
            last_modified_by="test-user",
            change_description="Test state"
        )
    )


class TestAWSInfrastructureService:
    """Test cases for AWSInfrastructureService"""


class TestCreateResource:
    """Test cases for create_resource method"""
    
    @pytest.mark.asyncio
    async def test_create_resource_success(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        mock_state_service,
        sample_resource_config,
        sample_resource
    ):
        """Test successful resource creation"""
        # Setup mocks
        mock_aws_mcp_client.create_resource.return_value = sample_resource
        mock_state_service.get_current_state.return_value = None
        mock_state_service.save_state.return_value = None
        
        # Execute
        result = await infrastructure_service.create_resource("test-project", sample_resource_config)
        
        # Verify
        assert result == sample_resource
        mock_aws_mcp_client.create_resource.assert_called_once()
        
        # Verify enhanced config was passed
        call_args = mock_aws_mcp_client.create_resource.call_args
        assert call_args[1]["project_id"] == "test-project"
        
        # Verify enhanced resource config has project tags
        enhanced_config = call_args[1]["resource_config"]
        assert "ProjectId" in enhanced_config.tags
        assert enhanced_config.tags["ProjectId"] == "test-project"
        assert "ManagedBy" in enhanced_config.tags
    
    @pytest.mark.asyncio
    async def test_create_resource_invalid_project(
        self,
        infrastructure_service,
        sample_resource_config
    ):
        """Test resource creation with invalid project ID"""
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.create_resource("", sample_resource_config)
        
        assert exc_info.value.code == ErrorCodes.VALIDATION_FAILED
    
    @pytest.mark.asyncio
    async def test_create_resource_mcp_failure(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        sample_resource_config
    ):
        """Test resource creation when MCP client fails"""
        # Setup mock to raise exception
        mock_aws_mcp_client.create_resource.side_effect = Exception("MCP error")
        
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.create_resource("test-project", sample_resource_config)
        
        assert exc_info.value.code == ErrorCodes.AWS_MCP_CONNECTION_FAILED


class TestGetResources:
    """Test cases for get_resources method"""
    
    @pytest.mark.asyncio
    async def test_get_resources_success(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        sample_resource
    ):
        """Test successful resource retrieval"""
        # Setup mocks
        mock_aws_mcp_client.list_resources.return_value = [sample_resource]
        
        # Execute
        result = await infrastructure_service.get_resources("test-project")
        
        # Verify
        assert len(result) == 1
        assert result[0] == sample_resource
        mock_aws_mcp_client.list_resources.assert_called_once()
        
        # Verify enhanced filter was passed
        call_args = mock_aws_mcp_client.list_resources.call_args
        assert call_args[1]["project_id"] == "test-project"
        
        # Verify filter includes project tags
        enhanced_filter = call_args[1]["filters"]
        assert "ProjectId" in enhanced_filter.tags
        assert enhanced_filter.tags["ProjectId"] == "test-project"
    
    @pytest.mark.asyncio
    async def test_get_resources_with_filters(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        sample_resource
    ):
        """Test resource retrieval with filters"""
        # Setup mocks
        mock_aws_mcp_client.list_resources.return_value = [sample_resource]
        
        # Create filter
        resource_filter = ResourceFilter(
            resource_type="EC2::Instance",
            status=ResourceStatus.ACTIVE,
            tags={"Environment": "test"}
        )
        
        # Execute
        result = await infrastructure_service.get_resources("test-project", resource_filter)
        
        # Verify
        assert len(result) == 1
        mock_aws_mcp_client.list_resources.assert_called_once()
        
        # Verify enhanced filter includes both original and project tags
        call_args = mock_aws_mcp_client.list_resources.call_args
        enhanced_filter = call_args[1]["filters"]
        assert enhanced_filter.resource_type == "EC2::Instance"
        assert enhanced_filter.status == ResourceStatus.ACTIVE
        assert "Environment" in enhanced_filter.tags
        assert "ProjectId" in enhanced_filter.tags
    
    @pytest.mark.asyncio
    async def test_get_resources_project_isolation(
        self,
        infrastructure_service,
        mock_aws_mcp_client
    ):
        """Test that resources are filtered by project"""
        # Create resources for different projects
        resource1 = Resource(
            id="r1", project_id="test-project", type="EC2::Instance", name="r1",
            region="us-east-1", properties={}, tags={"ProjectId": "test-project"},
            status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
        )
        resource2 = Resource(
            id="r2", project_id="other-project", type="EC2::Instance", name="r2",
            region="us-east-1", properties={}, tags={"ProjectId": "other-project"},
            status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
        )
        
        # Setup mock to return both resources
        mock_aws_mcp_client.list_resources.return_value = [resource1, resource2]
        
        # Execute
        result = await infrastructure_service.get_resources("test-project")
        
        # Verify only project resources are returned
        assert len(result) == 1
        assert result[0].id == "r1"
    
    @pytest.mark.asyncio
    async def test_get_resources_mcp_failure(
        self,
        infrastructure_service,
        mock_aws_mcp_client
    ):
        """Test resource retrieval when MCP client fails"""
        # Setup mock to raise exception
        mock_aws_mcp_client.list_resources.side_effect = Exception("MCP error")
        
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.get_resources("test-project")
        
        assert exc_info.value.code == ErrorCodes.RESOURCE_NOT_FOUND


class TestUpdateResource:
    """Test cases for update_resource method"""
    
    @pytest.mark.asyncio
    async def test_update_resource_success(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        mock_state_service,
        sample_resource
    ):
        """Test successful resource update"""
        # Setup mocks
        mock_aws_mcp_client.get_resource.return_value = sample_resource
        mock_aws_mcp_client.update_resource.return_value = sample_resource
        mock_state_service.get_current_state.return_value = None
        mock_state_service.save_state.return_value = None
        
        # Create update
        updates = ResourceUpdate(
            properties={"InstanceType": "t3.small"},
            tags={"Environment": "production"}
        )
        
        # Execute
        result = await infrastructure_service.update_resource("test-project", "resource-id", updates)
        
        # Verify
        assert result == sample_resource
        mock_aws_mcp_client.update_resource.assert_called_once()
        
        # Verify enhanced tags were passed
        call_args = mock_aws_mcp_client.update_resource.call_args
        update_params = call_args[1]["updates"]
        assert "tags" in update_params
        assert "ProjectId" in update_params["tags"]
        assert "Environment" in update_params["tags"]
    
    @pytest.mark.asyncio
    async def test_update_resource_not_found(
        self,
        infrastructure_service,
        mock_aws_mcp_client
    ):
        """Test updating non-existent resource"""
        # Setup mock to return None
        mock_aws_mcp_client.get_resource.return_value = None
        
        updates = ResourceUpdate(properties={"InstanceType": "t3.small"})
        
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.update_resource("test-project", "resource-id", updates)
        
        assert exc_info.value.code == ErrorCodes.RESOURCE_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_update_resource_wrong_project(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        sample_resource
    ):
        """Test updating resource from different project"""
        # Create resource with different project ID
        other_resource = Resource(
            id="resource-id", project_id="other-project", type="EC2::Instance", name="test",
            region="us-east-1", properties={}, tags={}, status=ResourceStatus.ACTIVE,
            created_at=datetime.now(), updated_at=datetime.now()
        )
        
        mock_aws_mcp_client.get_resource.return_value = other_resource
        
        updates = ResourceUpdate(properties={"InstanceType": "t3.small"})
        
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.update_resource("test-project", "resource-id", updates)
        
        assert exc_info.value.code == ErrorCodes.INSUFFICIENT_PERMISSIONS


class TestDeleteResource:
    """Test cases for delete_resource method"""
    
    @pytest.mark.asyncio
    async def test_delete_resource_success(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        mock_state_service,
        sample_resource
    ):
        """Test successful resource deletion"""
        # Setup mocks
        mock_aws_mcp_client.get_resource.return_value = sample_resource
        mock_aws_mcp_client.delete_resource.return_value = True
        mock_state_service.get_current_state.return_value = None
        mock_state_service.save_state.return_value = None
        
        # Execute
        await infrastructure_service.delete_resource("test-project", "resource-id")
        
        # Verify
        mock_aws_mcp_client.delete_resource.assert_called_once_with(
            project_id="test-project",
            resource_id="resource-id"
        )
    
    @pytest.mark.asyncio
    async def test_delete_resource_not_found(
        self,
        infrastructure_service,
        mock_aws_mcp_client
    ):
        """Test deleting non-existent resource"""
        # Setup mock to return None
        mock_aws_mcp_client.get_resource.return_value = None
        
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.delete_resource("test-project", "resource-id")
        
        assert exc_info.value.code == ErrorCodes.RESOURCE_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_delete_resource_mcp_failure(
        self,
        infrastructure_service,
        mock_aws_mcp_client,
        sample_resource
    ):
        """Test resource deletion when MCP delete fails"""
        # Setup mocks
        mock_aws_mcp_client.get_resource.return_value = sample_resource
        mock_aws_mcp_client.delete_resource.return_value = False
        
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.delete_resource("test-project", "resource-id")
        
        assert exc_info.value.code == ErrorCodes.AWS_MCP_CONNECTION_FAILED


class TestGenerateChangePlan:
    """Test cases for generate_change_plan method"""
    
    @pytest.mark.asyncio
    async def test_generate_change_plan_success(
        self,
        infrastructure_service,
        mock_change_plan_engine,
        sample_infrastructure_state
    ):
        """Test successful change plan generation"""
        # Create mock change plan
        mock_change_plan = ChangePlan(
            id="plan-123",
            project_id="test-project",
            summary=MagicMock(),
            changes=[],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING
        )
        
        # Setup mock
        mock_change_plan_engine.generate_plan.return_value = mock_change_plan
        
        # Execute
        result = await infrastructure_service.generate_change_plan(
            "test-project", sample_infrastructure_state
        )
        
        # Verify
        assert result == mock_change_plan
        mock_change_plan_engine.generate_plan.assert_called_once_with(
            "test-project", sample_infrastructure_state
        )
    
    @pytest.mark.asyncio
    async def test_generate_change_plan_project_mismatch(
        self,
        infrastructure_service,
        sample_infrastructure_state
    ):
        """Test change plan generation with project ID mismatch"""
        # Change the project ID in desired state
        sample_infrastructure_state.project_id = "other-project"
        
        with pytest.raises(InfrastructureException) as exc_info:
            await infrastructure_service.generate_change_plan(
                "test-project", sample_infrastructure_state
            )
        
        assert exc_info.value.code == ErrorCodes.VALIDATION_FAILED


class TestHelperMethods:
    """Test cases for helper methods"""
    
    @pytest.mark.asyncio
    async def test_validate_project_context_valid(self, infrastructure_service):
        """Test project context validation with valid project ID"""
        # Should not raise exception
        await infrastructure_service._validate_project_context("valid-project")
    
    @pytest.mark.asyncio
    async def test_validate_project_context_invalid(self, infrastructure_service):
        """Test project context validation with invalid project ID"""
        with pytest.raises(InfrastructureException):
            await infrastructure_service._validate_project_context("")
        
        with pytest.raises(InfrastructureException):
            await infrastructure_service._validate_project_context("   ")
    
    def test_enhance_resource_config(self, infrastructure_service, sample_resource_config):
        """Test resource configuration enhancement"""
        enhanced = infrastructure_service._enhance_resource_config("test-project", sample_resource_config)
        
        assert enhanced.type == sample_resource_config.type
        assert enhanced.name == sample_resource_config.name
        assert enhanced.properties == sample_resource_config.properties
        
        # Check enhanced tags
        assert "ProjectId" in enhanced.tags
        assert enhanced.tags["ProjectId"] == "test-project"
        assert "ManagedBy" in enhanced.tags
        assert "Environment" in enhanced.tags  # Original tag preserved
    
    def test_enhance_resource_tags(self, infrastructure_service):
        """Test resource tags enhancement"""
        original_tags = {"Environment": "test", "Owner": "team"}
        enhanced = infrastructure_service._enhance_resource_tags("test-project", original_tags)
        
        # Original tags preserved
        assert enhanced["Environment"] == "test"
        assert enhanced["Owner"] == "team"
        
        # Project tags added
        assert enhanced["ProjectId"] == "test-project"
        assert enhanced["ManagedBy"] == "aws-infrastructure-manager"
        assert "CreatedAt" in enhanced
    
    def test_enhance_resource_filter(self, infrastructure_service):
        """Test resource filter enhancement"""
        original_filter = ResourceFilter(
            resource_type="EC2::Instance",
            status=ResourceStatus.ACTIVE,
            tags={"Environment": "test"}
        )
        
        enhanced = infrastructure_service._enhance_resource_filter("test-project", original_filter)
        
        # Original filter properties preserved
        assert enhanced.resource_type == "EC2::Instance"
        assert enhanced.status == ResourceStatus.ACTIVE
        
        # Tags enhanced with project context
        assert enhanced.tags["Environment"] == "test"
        assert enhanced.tags["ProjectId"] == "test-project"
    
    def test_filter_resources_by_project(self, infrastructure_service):
        """Test project-based resource filtering"""
        resources = [
            Resource(
                id="r1", project_id="test-project", type="EC2::Instance", name="r1",
                region="us-east-1", properties={}, tags={"ProjectId": "test-project"},
                status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
            ),
            Resource(
                id="r2", project_id="other-project", type="EC2::Instance", name="r2",
                region="us-east-1", properties={}, tags={"ProjectId": "other-project"},
                status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
            ),
            Resource(
                id="r3", project_id="test-project", type="EC2::Instance", name="r3",
                region="us-east-1", properties={}, tags={"ProjectId": "test-project"},
                status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
            )
        ]
        
        filtered = infrastructure_service._filter_resources_by_project("test-project", resources)
        
        assert len(filtered) == 2
        assert all(r.project_id == "test-project" for r in filtered)
        assert {r.id for r in filtered} == {"r1", "r3"}


class TestFactoryFunction:
    """Test cases for factory function"""
    
    def test_create_infrastructure_service(self):
        """Test infrastructure service factory function"""
        mock_mcp_client = MagicMock(spec=AWSMCPClient)
        mock_state_service = MagicMock(spec=StateManagementService)
        mock_change_plan_engine = MagicMock(spec=ChangePlanEngine)
        
        service = create_infrastructure_service(
            mock_mcp_client,
            mock_state_service,
            mock_change_plan_engine
        )
        
        assert isinstance(service, AWSInfrastructureService)
        assert service.aws_mcp_client == mock_mcp_client
        assert service.state_service == mock_state_service
        assert service.change_plan_engine == mock_change_plan_engine


if __name__ == "__main__":
    pytest.main([__file__])