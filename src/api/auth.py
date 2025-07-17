"""
Authentication API endpoints
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from config.logging import get_logger
from src.models.data_models import User, UserCreate, UserUpdate, Token
from src.models.enums import UserRole
from src.services.auth_service import JWTAuthService
from src.services.service_container import get_auth_service
from .dependencies import get_current_user

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    responses={401: {"description": "Unauthorized"}},
)

logger = get_logger(__name__)


@router.post("/register", response_model=User)
async def register_user(
    user_create: UserCreate,
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)]
) -> User:
    """Register a new user"""
    try:
        user = await auth_service.register_user(user_create)
        # Remove sensitive data
        user_dict = user.__dict__.copy()
        user_dict.pop("hashed_password", None)
        return user
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)]
) -> Token:
    """Get access token using username and password"""
    try:
        user = await auth_service.authenticate_user(form_data.username, form_data.password)
        return await auth_service.create_access_token(user)
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_token: str,
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)]
) -> Token:
    """Get new access token using refresh token"""
    try:
        return await auth_service.refresh_token(refresh_token)
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Get current authenticated user information"""
    # Remove sensitive data
    user_dict = current_user.__dict__.copy()
    user_dict.pop("hashed_password", None)
    return current_user


@router.put("/me", response_model=User)
async def update_current_user(
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)]
) -> User:
    """Update current user information"""
    try:
        # Prevent users from changing their own role to admin
        if user_update.role == UserRole.ADMIN and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change role to admin"
            )
        
        updated_user = await auth_service.update_user(current_user.id, user_update)
        
        # Remove sensitive data
        user_dict = updated_user.__dict__.copy()
        user_dict.pop("hashed_password", None)
        return updated_user
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/project-role/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def set_project_role(
    project_id: str,
    user_id: str,
    role: str,
    current_user: Annotated[User, Depends(get_current_user)],
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)]
) -> None:
    """Set user role in a project (admin only)"""
    # Only admins can set project roles
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can set project roles"
        )
    
    try:
        await auth_service.set_project_role(user_id, project_id, role)
    except Exception as e:
        logger.error(f"Error setting project role: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/project-role/{project_id}")
async def get_project_role(
    project_id: str,
    user_id: str = None,
    current_user: Annotated[User, Depends(get_current_user)] = None,
    auth_service: Annotated[JWTAuthService, Depends(get_auth_service)] = None
) -> dict:
    """Get user role in a project"""
    # If no user_id is provided, use current user
    if not user_id:
        user_id = current_user.id
    
    # Only admins can check other users' roles
    if user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can check other users' roles"
        )
    
    try:
        role = await auth_service.get_project_role(user_id, project_id)
        return {"user_id": user_id, "project_id": project_id, "role": role}
    except Exception as e:
        logger.error(f"Error getting project role: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )