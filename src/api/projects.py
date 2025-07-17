"""
Project management API endpoints
"""
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime

from config.logging import get_logger
from src.models.data_models import Project, ProjectConfig, ProjectUpdate, ProjectSettings
from src.services.interfaces import ProjectManagementService
from .dependencies import (
    get_project_service, 
    get_current_user_id,
    get_correlation_id
)

logger = get_logger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


# Pydantic models for API requests/responses
class ProjectSettingsRequest(BaseModel):
    s3_bucket_path: str = Field(..., description="S3 bucket path for state storage")
    default_region: str = Field(..., description="Default AWS region")


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    description: str = Field(..., max_length=500, description="Project description")
    settings: ProjectSettingsRequest


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100, description="Project name")
    description: str | None = Field(None, max_length=500, description="Project description")
    settings: ProjectSettingsRequest | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    owner: str
    created_at: datetime
    updated_at: datetime
    settings: dict

    @classmethod
    def from_project(cls, project: Project) -> "ProjectResponse":
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            owner=project.owner,
            created_at=project.created_at,
            updated_at=project.updated_at,
            settings={
                "s3_bucket_path": project.settings.s3_bucket_path,
                "default_region": project.settings.default_region
            }
        )


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    project_service: Annotated[ProjectManagementService, Depends(get_project_service)]
):
    """Create a new project"""
    logger.info(
        "Creating new project",
        project_name=request.name,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Convert request to domain model
        project_config = ProjectConfig(
            name=request.name,
            description=request.description,
            owner=user_id,
            settings=ProjectSettings(
                s3_bucket_path=request.settings.s3_bucket_path,
                default_region=request.settings.default_region
            )
        )
        
        # Create project
        project = await project_service.create_project(project_config)
        
        logger.info(
            "Project created successfully",
            project_id=project.id,
            project_name=project.name,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return ProjectResponse.from_project(project)
        
    except Exception as e:
        logger.error(
            "Failed to create project",
            project_name=request.name,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}"
        )


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    project_service: Annotated[ProjectManagementService, Depends(get_project_service)]
):
    """List all projects accessible to the current user"""
    logger.info(
        "Listing projects for user",
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        projects = await project_service.list_projects(user_id)
        
        logger.info(
            "Projects retrieved successfully",
            user_id=user_id,
            project_count=len(projects),
            correlation_id=correlation_id
        )
        
        return [ProjectResponse.from_project(project) for project in projects]
        
    except Exception as e:
        logger.error(
            "Failed to list projects",
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list projects: {str(e)}"
        )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    project_service: Annotated[ProjectManagementService, Depends(get_project_service)]
):
    """Get a specific project by ID"""
    logger.info(
        "Getting project details",
        project_id=project_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Validate access
        has_access = await project_service.validate_project_access(user_id, project_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to project {project_id}"
            )
        
        # Get project
        project = await project_service.get_project(project_id)
        
        logger.info(
            "Project retrieved successfully",
            project_id=project_id,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return ProjectResponse.from_project(project)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get project",
            project_id=project_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get project: {str(e)}"
        )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    project_service: Annotated[ProjectManagementService, Depends(get_project_service)]
):
    """Update an existing project"""
    logger.info(
        "Updating project",
        project_id=project_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Validate access
        has_access = await project_service.validate_project_access(user_id, project_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to project {project_id}"
            )
        
        # Convert request to domain model
        updates = ProjectUpdate(
            name=request.name,
            description=request.description,
            settings=ProjectSettings(
                s3_bucket_path=request.settings.s3_bucket_path,
                default_region=request.settings.default_region
            ) if request.settings else None
        )
        
        # Update project
        project = await project_service.update_project(project_id, updates)
        
        logger.info(
            "Project updated successfully",
            project_id=project_id,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return ProjectResponse.from_project(project)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update project",
            project_id=project_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update project: {str(e)}"
        )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    project_service: Annotated[ProjectManagementService, Depends(get_project_service)]
):
    """Delete a project"""
    logger.info(
        "Deleting project",
        project_id=project_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Validate access
        has_access = await project_service.validate_project_access(user_id, project_id)
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to project {project_id}"
            )
        
        # Delete project
        await project_service.delete_project(project_id)
        
        logger.info(
            "Project deleted successfully",
            project_id=project_id,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete project",
            project_id=project_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete project: {str(e)}"
        )