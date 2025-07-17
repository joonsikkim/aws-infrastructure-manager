"""
Resource management API endpoints
"""
from typing import Annotated, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from datetime import datetime

from config.logging import get_logger
from src.models.data_models import Resource, ResourceConfig, ResourceFilter, ResourceUpdate
from src.models.enums import ResourceStatus
from src.services.interfaces import InfrastructureService
from .dependencies import (
    get_infrastructure_service,
    get_current_user_id,
    get_correlation_id,
    validate_project_access
)

logger = get_logger(__name__)
router = APIRouter(prefix="/projects/{project_id}/resources", tags=["resources"])


# Pydantic models for API requests/responses
class ResourceConfigRequest(BaseModel):
    type: str = Field(..., description="AWS resource type (e.g., EC2::Instance)")
    name: str = Field(..., min_length=1, max_length=100, description="Resource name")
    properties: Dict[str, Any] = Field(..., description="Resource properties")
    tags: Dict[str, str] | None = Field(None, description="Resource tags")


class ResourceUpdateRequest(BaseModel):
    properties: Dict[str, Any] | None = Field(None, description="Properties to update")
    tags: Dict[str, str] | None = Field(None, description="Tags to update")


class ResourceResponse(BaseModel):
    id: str
    project_id: str
    type: str
    name: str
    region: str
    properties: Dict[str, Any]
    tags: Dict[str, str]
    status: str
    created_at: datetime
    updated_at: datetime
    arn: str | None = None

    @classmethod
    def from_resource(cls, resource: Resource) -> "ResourceResponse":
        return cls(
            id=resource.id,
            project_id=resource.project_id,
            type=resource.type,
            name=resource.name,
            region=resource.region,
            properties=resource.properties,
            tags=resource.tags,
            status=resource.status.value,
            created_at=resource.created_at,
            updated_at=resource.updated_at,
            arn=resource.arn
        )


@router.post("/", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    project_id: Annotated[str, Depends(validate_project_access)],
    request: ResourceConfigRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    infrastructure_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)]
):
    """Create a new AWS resource in the specified project"""
    logger.info(
        "Creating new resource",
        project_id=project_id,
        resource_type=request.type,
        resource_name=request.name,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Convert request to domain model
        resource_config = ResourceConfig(
            type=request.type,
            name=request.name,
            properties=request.properties,
            tags=request.tags
        )
        
        # Create resource
        resource = await infrastructure_service.create_resource(project_id, resource_config)
        
        logger.info(
            "Resource created successfully",
            project_id=project_id,
            resource_id=resource.id,
            resource_type=resource.type,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return ResourceResponse.from_resource(resource)
        
    except Exception as e:
        logger.error(
            "Failed to create resource",
            project_id=project_id,
            resource_type=request.type,
            resource_name=request.name,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create resource: {str(e)}"
        )


@router.get("/", response_model=List[ResourceResponse])
async def list_resources(
    project_id: Annotated[str, Depends(validate_project_access)],
    resource_type: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    region: Annotated[str | None, Query()] = None,
    user_id: Annotated[str, Depends(get_current_user_id)] = None,
    correlation_id: Annotated[str | None, Depends(get_correlation_id)] = None,
    infrastructure_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)] = None
):
    """List all resources in the specified project with optional filtering"""
    logger.info(
        "Listing resources",
        project_id=project_id,
        resource_type=resource_type,
        status_filter=status_filter,
        region=region,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Build filter
        filters = ResourceFilter()
        if resource_type:
            filters.resource_type = resource_type
        if status_filter:
            try:
                filters.status = ResourceStatus(status_filter)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status filter: {status_filter}"
                )
        if region:
            filters.region = region
        
        # Get resources
        resources = await infrastructure_service.get_resources(project_id, filters)
        
        logger.info(
            "Resources retrieved successfully",
            project_id=project_id,
            resource_count=len(resources),
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return [ResourceResponse.from_resource(resource) for resource in resources]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to list resources",
            project_id=project_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list resources: {str(e)}"
        )


@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    project_id: Annotated[str, Depends(validate_project_access)],
    resource_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    infrastructure_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)]
):
    """Get a specific resource by ID"""
    logger.info(
        "Getting resource details",
        project_id=project_id,
        resource_id=resource_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Get all resources and find the specific one
        resources = await infrastructure_service.get_resources(project_id)
        resource = next((r for r in resources if r.id == resource_id), None)
        
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resource {resource_id} not found in project {project_id}"
            )
        
        logger.info(
            "Resource retrieved successfully",
            project_id=project_id,
            resource_id=resource_id,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return ResourceResponse.from_resource(resource)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get resource",
            project_id=project_id,
            resource_id=resource_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get resource: {str(e)}"
        )


@router.put("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    project_id: Annotated[str, Depends(validate_project_access)],
    resource_id: str,
    request: ResourceUpdateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    infrastructure_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)]
):
    """Update an existing resource"""
    logger.info(
        "Updating resource",
        project_id=project_id,
        resource_id=resource_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Convert request to domain model
        updates = ResourceUpdate(
            properties=request.properties,
            tags=request.tags
        )
        
        # Update resource
        resource = await infrastructure_service.update_resource(project_id, resource_id, updates)
        
        logger.info(
            "Resource updated successfully",
            project_id=project_id,
            resource_id=resource_id,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return ResourceResponse.from_resource(resource)
        
    except Exception as e:
        logger.error(
            "Failed to update resource",
            project_id=project_id,
            resource_id=resource_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update resource: {str(e)}"
        )


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    project_id: Annotated[str, Depends(validate_project_access)],
    resource_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    infrastructure_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)]
):
    """Delete a resource"""
    logger.info(
        "Deleting resource",
        project_id=project_id,
        resource_id=resource_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Delete resource
        await infrastructure_service.delete_resource(project_id, resource_id)
        
        logger.info(
            "Resource deleted successfully",
            project_id=project_id,
            resource_id=resource_id,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
    except Exception as e:
        logger.error(
            "Failed to delete resource",
            project_id=project_id,
            resource_id=resource_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete resource: {str(e)}"
        )