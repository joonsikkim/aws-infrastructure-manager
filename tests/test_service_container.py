"""
Unit tests for Service Container
"""
import pytest
from unittest.mock import patch, MagicMock

from src.services.service_container import (
    ServiceContainer, 
    get_project_service,
    get_infrastructure_service,
    get_change_plan_engine,
    get_approval_service,
    get_state_service,
    get_auth_service
)
from src.services.project_management import ProjectManagementServiceImpl
from src.services.infrastructure_service import AWSInfrastructureService
from src.services.change_plan_engine import DefaultChangePlanEngine
from src.services.approval_workflow import ApprovalWorkflowServiceImpl
from src.services.s3_state_management import S3StateManagementService
from src.services.auth_service import JWTAuthService


class TestServiceContainer:
    """Test cases for ServiceContainer"""
    
    def test_singleton_pattern(self):
        """Test that ServiceContainer is a singleton"""
        container1 = ServiceContainer()
        container2 = ServiceContainer()
        
        # Both instances should be the same object
        assert container1 is container2
    
    def test_service_initialization(self):
        """Test that services are initialized correctly"""
        container = ServiceContainer()
        
        # Check that all expected services are initialized
        assert container.get_service("project_service") is not None
        assert container.get_service("state_service") is not None
        assert container.get_service("aws_mcp_client") is not None
        assert container.get_service("change_plan_engine") is not None
        assert container.get_service("infrastructure_service") is not None
        assert container.get_service("approval_service") is not None
        assert container.get_service("auth_service") is not None
    
    def test_service_types(self):
        """Test that services are of the correct type"""
        container = ServiceContainer()
        
        assert isinstance(container.get_service("project_service"), ProjectManagementServiceImpl)
        assert isinstance(container.get_service("state_service"), S3StateManagementService)
        assert isinstance(container.get_service("change_plan_engine"), DefaultChangePlanEngine)
        assert isinstance(container.get_service("infrastructure_service"), AWSInfrastructureService)
        assert isinstance(container.get_service("approval_service"), ApprovalWorkflowServiceImpl)
        assert isinstance(container.get_service("auth_service"), JWTAuthService)
    
    def test_get_nonexistent_service(self):
        """Test getting a service that doesn't exist"""
        container = ServiceContainer()
        
        # Should return None for non-existent service
        assert container.get_service("nonexistent_service") is None
    
    def test_dependency_injection(self):
        """Test that dependencies are properly injected"""
        container = ServiceContainer()
        
        # Check that infrastructure service has its dependencies
        infra_service = container.get_service("infrastructure_service")
        assert infra_service.aws_mcp_client is container.get_service("aws_mcp_client")
        assert infra_service.state_service is container.get_service("state_service")
        assert infra_service.change_plan_engine is container.get_service("change_plan_engine")
        
        # Check that change plan engine has its dependencies
        change_plan_engine = container.get_service("change_plan_engine")
        assert change_plan_engine.state_service is container.get_service("state_service")


class TestServiceAccessors:
    """Test cases for service accessor functions"""
    
    @patch('src.services.service_container.service_container')
    def test_get_project_service(self, mock_container):
        """Test get_project_service function"""
        mock_service = MagicMock(spec=ProjectManagementServiceImpl)
        mock_container.get_service.return_value = mock_service
        
        service = get_project_service()
        
        assert service is mock_service
        mock_container.get_service.assert_called_once_with("project_service")
    
    @patch('src.services.service_container.service_container')
    def test_get_infrastructure_service(self, mock_container):
        """Test get_infrastructure_service function"""
        mock_service = MagicMock(spec=AWSInfrastructureService)
        mock_container.get_service.return_value = mock_service
        
        service = get_infrastructure_service()
        
        assert service is mock_service
        mock_container.get_service.assert_called_once_with("infrastructure_service")
    
    @patch('src.services.service_container.service_container')
    def test_get_change_plan_engine(self, mock_container):
        """Test get_change_plan_engine function"""
        mock_service = MagicMock(spec=DefaultChangePlanEngine)
        mock_container.get_service.return_value = mock_service
        
        service = get_change_plan_engine()
        
        assert service is mock_service
        mock_container.get_service.assert_called_once_with("change_plan_engine")
    
    @patch('src.services.service_container.service_container')
    def test_get_approval_service(self, mock_container):
        """Test get_approval_service function"""
        mock_service = MagicMock(spec=ApprovalWorkflowServiceImpl)
        mock_container.get_service.return_value = mock_service
        
        service = get_approval_service()
        
        assert service is mock_service
        mock_container.get_service.assert_called_once_with("approval_service")
    
    @patch('src.services.service_container.service_container')
    def test_get_state_service(self, mock_container):
        """Test get_state_service function"""
        mock_service = MagicMock(spec=S3StateManagementService)
        mock_container.get_service.return_value = mock_service
        
        service = get_state_service()
        
        assert service is mock_service
        mock_container.get_service.assert_called_once_with("state_service")
    
    @patch('src.services.service_container.service_container')
    def test_get_auth_service(self, mock_container):
        """Test get_auth_service function"""
        mock_service = MagicMock(spec=JWTAuthService)
        mock_container.get_service.return_value = mock_service
        
        service = get_auth_service()
        
        assert service is mock_service
        mock_container.get_service.assert_called_once_with("auth_service")