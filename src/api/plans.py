"""
Change plan management API endpoints
"""
from typing import Annotated, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime

from config.logging import get_logger
from src.models.data_models import (
    ChangePlan, InfrastructureState, StateMetadata, 
    Resource, ChangeSummary, Change
)
from src.models.enums import ChangePlanStatus, ChangeAction, RiskLevel, ResourceStatus
from src.services.interfaces import (
    ChangePlanEngine, 
    ApprovalWorkflowService,
    StateManagementService
)
from .dependencies import (
    get_change_plan_engine,
    get_approval_service,
    get_state_service,
    get_current_user_id,
    get_correlation_id,
    validate_project_access
)

logger = get_logger(__name__)
router = APIRouter(prefix="/projects/{project_id}/plans", tags=["change-plans"])


# Pydantic models for API requests/responses
class ResourceStateRequest(BaseModel):
    id: str
    type: str
    name: str
    region: str
    properties: Dict[str, Any]
    tags: Dict[str, str]


class InfrastructureStateRequest(BaseModel):
    resources: List[ResourceStateRequest]
    change_description: str = Field(..., description="Description of the changes")


class ChangeResponse(BaseModel):
    action: str
    resource_type: str
    resource_id: str
    risk_level: str
    current_config: Dict[str, Any] | None = None
    desired_config: Dict[str, Any] | None = None
    dependencies: List[str]

    @classmethod
    def from_change(cls, change: Change) -> "ChangeResponse":
        return cls(
            action=change.action.value,
            resource_type=change.resource_type,
            resource_id=change.resource_id,
            risk_level=change.risk_level.value,
            current_config=change.current_config.__dict__ if change.current_config else None,
            desired_config=change.desired_config.__dict__ if change.desired_config else None,
            dependencies=change.dependencies
        )


class ChangeSummaryResponse(BaseModel):
    total_changes: int
    creates: int
    updates: int
    deletes: int
    estimated_cost: float | None = None
    estimated_duration: int | None = None

    @classmethod
    def from_summary(cls, summary: ChangeSummary) -> "ChangeSummaryResponse":
        return cls(
            total_changes=summary.total_changes,
            creates=summary.creates,
            updates=summary.updates,
            deletes=summary.deletes,
            estimated_cost=summary.estimated_cost,
            estimated_duration=summary.estimated_duration
        )


class ChangePlanResponse(BaseModel):
    id: str
    project_id: str
    summary: ChangeSummaryResponse
    changes: List[ChangeResponse]
    created_at: datetime
    status: str
    created_by: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None

    @classmethod
    def from_change_plan(cls, plan: ChangePlan) -> "ChangePlanResponse":
        return cls(
            id=plan.id,
            project_id=plan.project_id,
            summary=ChangeSummaryResponse.from_summary(plan.summary),
            changes=[ChangeResponse.from_change(change) for change in plan.changes],
            created_at=plan.created_at,
            status=plan.status.value,
            created_by=plan.created_by,
            approved_by=plan.approved_by,
            approved_at=plan.approved_at
        )


class ApprovalRequest(BaseModel):
    action: str = Field(..., description="Action to take: 'approve' or 'reject'")
    reason: str | None = Field(None, description="Reason for rejection (required if rejecting)")


@router.post("/", response_model=ChangePlanResponse, status_code=status.HTTP_201_CREATED)
async def create_change_plan(
    project_id: Annotated[str, Depends(validate_project_access)],
    request: InfrastructureStateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    change_plan_engine: Annotated[ChangePlanEngine, Depends(get_change_plan_engine)],
    state_service: Annotated[StateManagementService, Depends(get_state_service)]
):
    """Create a new change plan for the desired infrastructure state"""
    logger.info(
        "Creating change plan",
        project_id=project_id,
        resource_count=len(request.resources),
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        # Convert request to domain model
        desired_resources = []
        for res_req in request.resources:
            resource = Resource(
                id=res_req.id,
                project_id=project_id,
                type=res_req.type,
                name=res_req.name,
                region=res_req.region,
                properties=res_req.properties,
                tags=res_req.tags,
                status=ResourceStatus.ACTIVE,  # Default status for desired state
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            desired_resources.append(resource)
        
        desired_state = InfrastructureState(
            project_id=project_id,
            version="1.0.0",
            timestamp=datetime.now(),
            resources=desired_resources,
            metadata=StateMetadata(
                last_modified_by=user_id,
                change_description=request.change_description
            )
        )
        
        # Generate change plan
        change_plan = await change_plan_engine.generate_plan(project_id, desired_state)
        
        # Save the change plan
        await state_service.save_change_plan(project_id, change_plan)
        
        logger.info(
            "Change plan created successfully",
            project_id=project_id,
            plan_id=change_plan.id,
            total_changes=change_plan.summary.total_changes,
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return ChangePlanResponse.from_change_plan(change_plan)
        
    except Exception as e:
        logger.error(
            "Failed to create change plan",
            project_id=project_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create change plan: {str(e)}"
        )


@router.get("/", response_model=List[ChangePlanResponse])
async def list_change_plans(
    project_id: Annotated[str, Depends(validate_project_access)],
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    state_service: Annotated[StateManagementService, Depends(get_state_service)]
):
    """List all change plans for the specified project"""
    logger.info(
        "Listing change plans",
        project_id=project_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        plans = await state_service.list_change_plans(project_id)
        logger.info(
            "Change plans retrieved successfully",
            project_id=project_id,
            plan_count=len(plans),
            user_id=user_id,
            correlation_id=correlation_id
        )
        
        return [ChangePlanResponse.from_change_plan(plan) for plan in plans]
        
    except Exception as e:
        logger.error(
            "Failed to list change plans",
            project_id=project_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list change plans: {str(e)}"
        )


@router.get("/{plan_id}", response_model=ChangePlanResponse)
async def get_change_plan(
    project_id: Annotated[str, Depends(validate_project_access)],
    plan_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)]
):
    """Get a specific change plan by ID"""
    logger.info(
        "Getting change plan details",
        project_id=project_id,
        plan_id=plan_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        plan = await state_service.get_change_plan(project_id, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Change plan {plan_id} not found"
            )
        return ChangePlanResponse.from_change_plan(plan)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get change plan",
            project_id=project_id,
            plan_id=plan_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get change plan: {str(e)}"
        )


@router.post("/{plan_id}/approval", response_model=ChangePlanResponse)
async def handle_plan_approval(
    project_id: Annotated[str, Depends(validate_project_access)],
    plan_id: str,
    request: ApprovalRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    approval_service: Annotated[ApprovalWorkflowService, Depends(get_approval_service)],
    state_service: Annotated[StateManagementService, Depends(get_state_service)]
):
    """Approve or reject a change plan"""
    logger.info(
        "Processing plan approval",
        project_id=project_id,
        plan_id=plan_id,
        action=request.action,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        if request.action.lower() == "approve":
            change_plan = await approval_service.approve_plan(plan_id, user_id)
            logger.info(
                "Change plan approved successfully",
                project_id=project_id,
                plan_id=plan_id,
                user_id=user_id,
                correlation_id=correlation_id
            )
        elif request.action.lower() == "reject":
            if not request.reason:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reason is required when rejecting a plan"
                )
            change_plan = await approval_service.reject_plan(plan_id, user_id, request.reason)
            logger.info(
                "Change plan rejected successfully",
                project_id=project_id,
                plan_id=plan_id,
                reason=request.reason,
                user_id=user_id,
                correlation_id=correlation_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be 'approve' or 'reject'"
            )
        
        await state_service.save_change_plan(project_id, change_plan)

        return ChangePlanResponse.from_change_plan(change_plan)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to process plan approval",
            project_id=project_id,
            plan_id=plan_id,
            action=request.action,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process plan approval: {str(e)}"
        )


@router.get("/{plan_id}/status")
async def get_plan_status(
    project_id: Annotated[str, Depends(validate_project_access)],
    plan_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)],
    state_service: Annotated[StateManagementService, Depends(get_state_service)]
):
    """Get the current status of a change plan"""
    logger.info(
        "Getting plan status",
        project_id=project_id,
        plan_id=plan_id,
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    try:
        plan = await state_service.get_change_plan(project_id, plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Change plan {plan_id} not found"
            )

        return {
            "plan_id": plan.id,
            "status": plan.status.value,
            "created_at": plan.created_at.isoformat(),
            "last_updated": plan.approved_at.isoformat() if plan.approved_at else plan.created_at.isoformat()
        }
        
    except Exception as e:
        logger.error(
            "Failed to get plan status",
            project_id=project_id,
            plan_id=plan_id,
            user_id=user_id,
            error=str(e),
            correlation_id=correlation_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plan status: {str(e)}"
        )