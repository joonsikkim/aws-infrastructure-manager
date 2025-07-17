"""
API decorators for authentication and authorization
"""
import functools
from typing import Callable, List, Optional
from fastapi import Depends, HTTPException, status
from src.models.data_models import User
from src.models.enums import UserRole
from src.services.auth_service import JWTAuthService
from src.services.service_container import get_auth_service
from .dependencies import get_current_user


def require_project_role(project_id_param: str, allowed_roles: List[str]):
    """
    Decorator to check if user has required role for a project
    
    Args:
        project_id_param: Name of the path parameter containing project ID
        allowed_roles: List of roles allowed to access the endpoint
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current user
            current_user = kwargs.get("current_user")
            if not current_user:
                raise ValueError("Current user not found in kwargs. Make sure to include Depends(get_current_user)")
            
            # Get project ID from path parameters
            project_id = kwargs.get(project_id_param)
            if not project_id:
                raise ValueError(f"Project ID parameter '{project_id_param}' not found in kwargs")
            
            # Get auth service
            auth_service = kwargs.get("auth_service")
            if not auth_service:
                raise ValueError("Auth service not found in kwargs. Make sure to include Depends(get_auth_service)")
            
            # Admin users bypass role check
            if current_user.role == UserRole.ADMIN:
                return await func(*args, **kwargs)
            
            # Check project role
            project_role = await auth_service.get_project_role(current_user.id, project_id)
            if not project_role or project_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions for project {project_id}. Required roles: {', '.join(allowed_roles)}"
                )
            
            return await func(*args, **kwargs)
        
        # Add dependencies to the wrapper function
        if not hasattr(wrapper, "__dependencies__"):
            wrapper.__dependencies__ = []
        
        # Add current_user dependency if not already present
        current_user_dep = Depends(get_current_user)
        if current_user_dep not in wrapper.__dependencies__:
            wrapper.__dependencies__.append(current_user_dep)
        
        # Add auth_service dependency if not already present
        auth_service_dep = Depends(get_auth_service)
        if auth_service_dep not in wrapper.__dependencies__:
            wrapper.__dependencies__.append(auth_service_dep)
        
        return wrapper
    
    return decorator


def require_role(allowed_roles: List[str]):
    """
    Decorator to check if user has required global role
    
    Args:
        allowed_roles: List of roles allowed to access the endpoint
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current user
            current_user = kwargs.get("current_user")
            if not current_user:
                raise ValueError("Current user not found in kwargs. Make sure to include Depends(get_current_user)")
            
            # Check user role
            if current_user.role.value not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required roles: {', '.join(allowed_roles)}"
                )
            
            return await func(*args, **kwargs)
        
        # Add dependencies to the wrapper function
        if not hasattr(wrapper, "__dependencies__"):
            wrapper.__dependencies__ = []
        
        # Add current_user dependency if not already present
        current_user_dep = Depends(get_current_user)
        if current_user_dep not in wrapper.__dependencies__:
            wrapper.__dependencies__.append(current_user_dep)
        
        return wrapper
    
    return decorator