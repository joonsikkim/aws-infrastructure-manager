"""
API routes for views and dashboards
"""
from typing import Annotated, List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from pydantic import BaseModel

from config.logging import get_logger
from src.models.data_models import View, Dashboard, ResourceFilter
from src.services.view_service import ViewService
from src.services.interfaces import InfrastructureService, ProjectManagementService
from .dependencies import (
    get_infrastructure_service,
    get_project_service,
    get_current_user_id,
    get_correlation_id,
    validate_project_access
)

logger = get_logger(__name__)
router = APIRouter(
    prefix="/projects/{project_id}/views",
    tags=["views"],
)


class ViewRequest(BaseModel):
    name: str
    resource_type: Optional[str] = None
    status: Optional[str] = None
    region: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


class DashboardRequest(BaseModel):
    name: str
    description: str
    view_ids: List[str]


def get_view_service():
    return ViewService()


@router.post("", response_model=View)
async def create_view(
    project_id: Annotated[str, Depends(validate_project_access)],
    request: ViewRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Create a new view for the project."""
    logger.info(
        "Creating new view",
        project_id=project_id, view_name=request.name, user_id=user_id, correlation_id=correlation_id
    )
    
    # Convert request to ResourceFilter
    filters = ResourceFilter(
        resource_type=request.resource_type,
        region=request.region,
        tags=request.tags
    )
    
    # Convert status string to enum if provided
    if request.status:
        from src.models.enums import ResourceStatus
        try:
            filters.status = ResourceStatus(request.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status value: {request.status}"
            )
    
    view = await service.create_view(project_id, request.name, filters, user_id)
    return view


@router.get("", response_model=List[View])
async def get_views_by_project(
    project_id: Annotated[str, Depends(validate_project_access)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Get all views for the project."""
    logger.info(
        "Fetching views for project",
        project_id=project_id, user_id=user_id, correlation_id=correlation_id
    )
    return await service.get_views_by_project(project_id)


@router.get("/{view_id}", response_model=View)
async def get_view(
    project_id: Annotated[str, Depends(validate_project_access)],
    view_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Get a specific view by ID."""
    logger.info(
        "Fetching view",
        project_id=project_id, view_id=view_id, user_id=user_id, correlation_id=correlation_id
    )
    view = await service.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    
    # Verify view belongs to the project
    if view.project_id != project_id:
        raise HTTPException(status_code=403, detail="View does not belong to this project")
    
    return view


@router.put("/{view_id}", response_model=View)
async def update_view(
    project_id: Annotated[str, Depends(validate_project_access)],
    view_id: str,
    request: ViewRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Update a view."""
    logger.info(
        "Updating view",
        project_id=project_id, view_id=view_id, user_id=user_id, correlation_id=correlation_id
    )
    
    # Verify view belongs to the project
    view = await service.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    if view.project_id != project_id:
        raise HTTPException(status_code=403, detail="View does not belong to this project")
    
    # Convert request to ResourceFilter
    filters = ResourceFilter(
        resource_type=request.resource_type,
        region=request.region,
        tags=request.tags
    )
    
    # Convert status string to enum if provided
    if request.status:
        from src.models.enums import ResourceStatus
        try:
            filters.status = ResourceStatus(request.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status value: {request.status}"
            )
    
    updated_view = await service.update_view(view_id, request.name, filters)
    return updated_view


@router.delete("/{view_id}")
async def delete_view(
    project_id: Annotated[str, Depends(validate_project_access)],
    view_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Delete a view."""
    logger.info(
        "Deleting view",
        project_id=project_id, view_id=view_id, user_id=user_id, correlation_id=correlation_id
    )
    
    # Verify view belongs to the project
    view = await service.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    if view.project_id != project_id:
        raise HTTPException(status_code=403, detail="View does not belong to this project")
    
    if not await service.delete_view(view_id):
        raise HTTPException(status_code=404, detail="View not found")
    return {"message": "View deleted"}


@router.get("/{view_id}/resources")
async def get_view_resources(
    project_id: Annotated[str, Depends(validate_project_access)],
    view_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
    infra_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)],
    group_by: Annotated[str | None, Query(description="Group resources by: 'type', 'status', 'region', or 'tag:{tag_name}'")] = None,
):
    """Get resources based on a view's filters."""
    logger.info(
        "Fetching resources for view",
        project_id=project_id, view_id=view_id, user_id=user_id, correlation_id=correlation_id
    )
    
    # Get the view
    view = await service.get_view(view_id)
    if not view:
        raise HTTPException(status_code=404, detail="View not found")
    if view.project_id != project_id:
        raise HTTPException(status_code=403, detail="View does not belong to this project")
    
    # Get resources using the view's filters
    resources = await infra_service.get_resources(project_id, view.filters)
    
    # Group resources if requested
    grouped_resources = {}
    if group_by:
        if group_by == 'type':
            for r in resources:
                grouped_resources.setdefault(r.type, []).append(r.id)
        elif group_by == 'status':
            for r in resources:
                grouped_resources.setdefault(r.status.value, []).append(r.id)
        elif group_by == 'region':
            for r in resources:
                grouped_resources.setdefault(r.region, []).append(r.id)
        elif group_by.startswith('tag:'):
            tag_key = group_by[4:]  # Remove 'tag:' prefix
            for r in resources:
                tag_value = r.tags.get(tag_key, 'undefined')
                grouped_resources.setdefault(tag_value, []).append(r.id)
    
    # Format response
    response = {
        "viewId": view_id,
        "projectId": project_id,
        "name": view.name,
        "totalResources": len(resources),
        "resources": [
            {
                "id": r.id,
                "type": r.type,
                "name": r.name,
                "region": r.region,
                "status": r.status.value,
                "tags": r.tags
            }
            for r in resources
        ]
    }
    
    # Add grouped resources if grouping was requested
    if group_by:
        response["groupedResources"] = grouped_resources
    
    return response


# Dashboard endpoints
@router.post("/dashboards", response_model=Dashboard)
async def create_dashboard(
    project_id: Annotated[str, Depends(validate_project_access)],
    request: DashboardRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Create a new dashboard for the project."""
    logger.info(
        "Creating new dashboard",
        project_id=project_id, dashboard_name=request.name, user_id=user_id, correlation_id=correlation_id
    )
    
    # Verify all views belong to the project
    for view_id in request.view_ids:
        view = await service.get_view(view_id)
        if not view or view.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"View {view_id} does not exist or does not belong to this project"
            )
    
    dashboard = await service.create_dashboard(
        project_id, request.name, request.description, request.view_ids, user_id
    )
    return dashboard


@router.get("/dashboards", response_model=List[Dashboard])
async def get_dashboards_by_project(
    project_id: Annotated[str, Depends(validate_project_access)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Get all dashboards for the project."""
    logger.info(
        "Fetching dashboards for project",
        project_id=project_id, user_id=user_id, correlation_id=correlation_id
    )
    return await service.get_dashboards_by_project(project_id)


@router.get("/dashboards/{dashboard_id}", response_model=Dashboard)
async def get_dashboard(
    project_id: Annotated[str, Depends(validate_project_access)],
    dashboard_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Get a specific dashboard by ID."""
    logger.info(
        "Fetching dashboard",
        project_id=project_id, dashboard_id=dashboard_id, user_id=user_id, correlation_id=correlation_id
    )
    dashboard = await service.get_dashboard(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    
    # Verify dashboard belongs to the project
    if dashboard.project_id != project_id:
        raise HTTPException(status_code=403, detail="Dashboard does not belong to this project")
    
    return dashboard


@router.put("/dashboards/{dashboard_id}", response_model=Dashboard)
async def update_dashboard(
    project_id: Annotated[str, Depends(validate_project_access)],
    dashboard_id: str,
    request: DashboardRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Update a dashboard."""
    logger.info(
        "Updating dashboard",
        project_id=project_id, dashboard_id=dashboard_id, user_id=user_id, correlation_id=correlation_id
    )
    
    # Verify dashboard belongs to the project
    dashboard = await service.get_dashboard(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if dashboard.project_id != project_id:
        raise HTTPException(status_code=403, detail="Dashboard does not belong to this project")
    
    # Verify all views belong to the project
    for view_id in request.view_ids:
        view = await service.get_view(view_id)
        if not view or view.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"View {view_id} does not exist or does not belong to this project"
            )
    
    updated_dashboard = await service.update_dashboard(
        dashboard_id, request.name, request.description, request.view_ids
    )
    return updated_dashboard


@router.delete("/dashboards/{dashboard_id}")
async def delete_dashboard(
    project_id: Annotated[str, Depends(validate_project_access)],
    dashboard_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
):
    """Delete a dashboard."""
    logger.info(
        "Deleting dashboard",
        project_id=project_id, dashboard_id=dashboard_id, user_id=user_id, correlation_id=correlation_id
    )
    
    # Verify dashboard belongs to the project
    dashboard = await service.get_dashboard(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if dashboard.project_id != project_id:
        raise HTTPException(status_code=403, detail="Dashboard does not belong to this project")
    
    if not await service.delete_dashboard(dashboard_id):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return {"message": "Dashboard deleted"}


@router.get("/dashboards/{dashboard_id}/data")
async def get_dashboard_data(
    project_id: Annotated[str, Depends(validate_project_access)],
    dashboard_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    service: ViewService = Depends(get_view_service),
    infra_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)],
):
    """Get all data for a dashboard including resources from all views."""
    logger.info(
        "Fetching dashboard data",
        project_id=project_id, dashboard_id=dashboard_id, user_id=user_id, correlation_id=correlation_id
    )
    
    # Get the dashboard
    dashboard = await service.get_dashboard(dashboard_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if dashboard.project_id != project_id:
        raise HTTPException(status_code=403, detail="Dashboard does not belong to this project")
    
    # Get all views
    views = []
    for view_id in dashboard.views:
        view = await service.get_view(view_id)
        if view:
            views.append(view)
    
    # Get resources for each view
    view_data = []
    for view in views:
        resources = await infra_service.get_resources(project_id, view.filters)
        view_data.append({
            "viewId": view.id,
            "name": view.name,
            "totalResources": len(resources),
            "resources": [
                {
                    "id": r.id,
                    "type": r.type,
                    "name": r.name,
                    "region": r.region,
                    "status": r.status.value,
                }
                for r in resources
            ]
        })
    
    return {
        "dashboardId": dashboard_id,
        "projectId": project_id,
        "name": dashboard.name,
        "description": dashboard.description,
        "views": view_data
    }
