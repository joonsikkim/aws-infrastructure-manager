"""
FastAPI dependencies for dependency injection
"""
from typing import Annotated, Optional
from fastapi import Depends, HTTPException, Header, status, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from config.settings import settings
from config.logging import get_logger
from src.services.infrastructure_service import AWSInfrastructureService
from src.services.project_management import ProjectManagementServiceImpl
from src.services.change_plan_engine import DefaultChangePlanEngine
from src.services.approval_workflow import ApprovalWorkflowServiceImpl
from src.services.s3_state_management import S3StateManagementService
from src.services.auth_service import JWTAuthService
from src.models.data_models import User
from src.models.enums import UserRole
from src.services.service_container import (
    get_infrastructure_service,
    get_project_service,
    get_change_plan_engine,
    get_approval_service,
    get_state_service,
    get_auth_service
)

logger = get_logger(__name__)

# OAuth2 scheme for JWT token authentication
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="auth/token",
    scopes={
        "admin": "Full access to all resources",
        "project_manager": "Manage projects and resources",
        "developer": "Create and modify resources",
        "viewer": "Read-only access to resources"
    }
)


# Authentication dependencies
async def get_current_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)]
) -> User:
    """Get current authenticated user from JWT token"""
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value}
    )
    
    user = await auth_service.verify_token(token)
    if not user:
        logger.error("Invalid authentication token")
        raise credentials_exception
    
    # Check if user has required scopes
    if security_scopes.scopes:
        user_role = user.role.value
        if user_role not in security_scopes.scopes:
            logger.error(f"User {user.username} does not have required scope: {security_scopes.scope_str}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions. Required: {security_scopes.scope_str}",
                headers={"WWW-Authenticate": authenticate_value}
            )
    
    return user


async def get_current_user_id(
    user: Annotated[User, Security(get_current_user, scopes=[])]
) -> str:
    """Get current user ID from authenticated user"""
    return user.id


async def get_correlation_id(
    x_correlation_id: Annotated[str | None, Header()] = None
) -> str | None:
    """Extract correlation ID from request headers"""
    return x_correlation_id


# Project access validation
async def validate_project_access(
    project_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    project_service: Annotated[ProjectManagementServiceImpl, Depends(get_project_service)],
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)]
) -> str:
    """Validate user has access to the specified project"""
    try:
        # Admin users have access to all projects
        if current_user.role == UserRole.ADMIN:
            return project_id
        
        # Check project-specific role
        project_role = await auth_service.get_project_role(current_user.id, project_id)
        if project_role:
            return project_id
        
        # Fall back to project service validation
        has_access = await project_service.validate_project_access(current_user.id, project_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to project {project_id}"
            )
        return project_id
    except Exception as e:
        logger.error(f"Error validating project access: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating project access"
        )