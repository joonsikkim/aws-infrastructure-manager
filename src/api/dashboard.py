
from typing import Annotated, List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from collections import Counter
from datetime import datetime, timedelta

from config.logging import get_logger
from src.services.interfaces import InfrastructureService, StateManagementService, ProjectManagementService
from src.models.data_models import StateSnapshot, ResourceFilter
from .dependencies import (
    get_infrastructure_service,
    get_state_service,
    get_project_service,
    get_current_user_id,
    get_correlation_id,
    validate_project_access
)

logger = get_logger(__name__)
router = APIRouter(prefix="/projects/{project_id}", tags=["dashboard"])


@router.get("/dashboard")
async def get_project_dashboard(
    project_id: Annotated[str, Depends(validate_project_access)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    infra_service: Annotated[InfrastructureService, Depends(get_infrastructure_service)],
    state_service: Annotated[StateManagementService, Depends(get_state_service)],
    group_by: Annotated[str | None, Query(description="Group resources by: 'type', 'status', 'region', or 'tag:{tag_name}'")] = None,
    filter_type: Annotated[str | None, Query(description="Filter resources by type")] = None,
    filter_status: Annotated[str | None, Query(description="Filter resources by status")] = None,
    filter_region: Annotated[str | None, Query(description="Filter resources by region")] = None,
    filter_tag: Annotated[str | None, Query(description="Filter resources by tag (format: key=value)")] = None
) -> Dict[str, Any]:
    """Get a dashboard summary for the project."""
    logger.info(
        "Fetching project dashboard",
        project_id=project_id, user_id=user_id, correlation_id=correlation_id,
        group_by=group_by
    )

    # Build resource filter
    resource_filter = ResourceFilter()
    if filter_type:
        resource_filter.resource_type = filter_type
    if filter_status:
        from src.models.enums import ResourceStatus
        try:
            resource_filter.status = ResourceStatus(filter_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status value: {filter_status}"
            )
    if filter_region:
        resource_filter.region = filter_region
    if filter_tag and "=" in filter_tag:
        key, value = filter_tag.split("=", 1)
        resource_filter.tags = {key: value}

    # Get resources with filters
    resources = await infra_service.get_resources(project_id, resource_filter)
    resource_count = len(resources)
    
    # Basic counts
    count_by_status = dict(Counter(r.status.value for r in resources))
    count_by_type = dict(Counter(r.type for r in resources))
    count_by_region = dict(Counter(r.region for r in resources))
    
    # Group resources based on the group_by parameter
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

    # Get recent change plans summary
    plans = await state_service.list_change_plans(project_id)
    plans.sort(key=lambda p: p.created_at, reverse=True)
    recent_plans = plans[:5]
    plan_summary = [
        {
            "id": p.id,
            "status": p.status.value,
            "created_at": p.created_at,
            "total_changes": p.summary.total_changes,
            "creates": p.summary.creates,
            "updates": p.summary.updates,
            "deletes": p.summary.deletes
        }
        for p in recent_plans
    ]

    # Build response
    response = {
        "projectId": project_id,
        "resourceSummary": {
            "totalResources": resource_count,
            "statusCounts": count_by_status,
            "typeCounts": count_by_type,
            "regionCounts": count_by_region
        },
        "recentChangePlans": plan_summary
    }
    
    # Add grouped resources if grouping was requested
    if group_by:
        response["groupedResources"] = grouped_resources
    
    return response


@router.get("/history", response_model=List[StateSnapshot])
async def get_project_history(
    project_id: Annotated[str, Depends(validate_project_access)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    state_service: Annotated[StateManagementService, Depends(get_state_service)],
    limit: Annotated[int | None, Query(description="Limit the number of history records to return")] = 10,
    from_date: Annotated[str | None, Query(description="Filter history from this date (ISO format)")] = None,
    to_date: Annotated[str | None, Query(description="Filter history to this date (ISO format)")] = None,
    change_description: Annotated[str | None, Query(description="Filter by change description (substring match)")] = None
):
    """Get the state change history for the project."""
    logger.info(
        "Fetching project history",
        project_id=project_id, limit=limit, user_id=user_id, correlation_id=correlation_id,
        from_date=from_date, to_date=to_date, change_description=change_description
    )
    
    # Get all history first
    history = await state_service.get_state_history(project_id)
    
    # Apply filters
    if from_date:
        try:
            from_datetime = datetime.fromisoformat(from_date)
            history = [h for h in history if h.timestamp >= from_datetime]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid from_date format: {from_date}. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
            )
    
    if to_date:
        try:
            to_datetime = datetime.fromisoformat(to_date)
            history = [h for h in history if h.timestamp <= to_datetime]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid to_date format: {to_date}. Use ISO format (YYYY-MM-DDTHH:MM:SS)."
            )
    
    if change_description:
        history = [h for h in history if change_description.lower() in h.change_description.lower()]
    
    # Apply limit after filtering
    if limit:
        history = history[:limit]
    
    return history


@router.get("/projects-access")
async def get_accessible_projects(
    project_id: Annotated[str, Depends(validate_project_access)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    project_service: Annotated[ProjectManagementService, Depends(get_project_service)]
):
    """Get all projects accessible to the current user for project switching."""
    logger.info(
        "Fetching accessible projects for user",
        user_id=user_id, correlation_id=correlation_id
    )
    
    projects = await project_service.list_projects(user_id)
    
    # Format response to include minimal project info
    project_list = [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "isCurrentProject": p.id == project_id
        }
        for p in projects
    ]
    
    return {
        "currentProjectId": project_id,
        "accessibleProjects": project_list
    }
