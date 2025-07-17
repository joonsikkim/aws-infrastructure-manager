"""
Service container for dependency injection and singleton instances
"""
from typing import Dict, Any, Optional, Type

from .project_management import ProjectManagementServiceImpl
from .infrastructure_service import AWSInfrastructureService
from .change_plan_engine import DefaultChangePlanEngine
from .approval_workflow import ApprovalWorkflowServiceImpl
from .s3_state_management import S3StateManagementService
from .aws_mcp_client import AWSMCPClient
from .auth_service import JWTAuthService


class ServiceContainer:
    """Container for service instances"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceContainer, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize service instances"""
        self._services: Dict[str, Any] = {}
        
        # Create service instances
        self._services["project_service"] = ProjectManagementServiceImpl()
        self._services["state_service"] = S3StateManagementService()
        self._services["aws_mcp_client"] = AWSMCPClient()
        self._services["change_plan_engine"] = DefaultChangePlanEngine(self._services["state_service"])
        self._services["infrastructure_service"] = AWSInfrastructureService(
            self._services["aws_mcp_client"],
            self._services["state_service"],
            self._services["change_plan_engine"]
        )
        self._services["approval_service"] = ApprovalWorkflowServiceImpl()
        self._services["auth_service"] = JWTAuthService()
    
    def get_service(self, service_name: str) -> Any:
        """Get a service instance by name"""
        return self._services.get(service_name)


# Global service container instance
service_container = ServiceContainer()


# Service accessor functions
def get_project_service() -> ProjectManagementServiceImpl:
    """Get project management service instance"""
    return service_container.get_service("project_service")


def get_infrastructure_service() -> AWSInfrastructureService:
    """Get infrastructure service instance"""
    return service_container.get_service("infrastructure_service")


def get_change_plan_engine() -> DefaultChangePlanEngine:
    """Get change plan engine instance"""
    return service_container.get_service("change_plan_engine")


def get_approval_service() -> ApprovalWorkflowServiceImpl:
    """Get approval workflow service instance"""
    return service_container.get_service("approval_service")


def get_state_service() -> S3StateManagementService:
    """Get state management service instance"""
    return service_container.get_service("state_service")


def get_auth_service() -> JWTAuthService:
    """Get authentication service instance"""
    return service_container.get_service("auth_service")