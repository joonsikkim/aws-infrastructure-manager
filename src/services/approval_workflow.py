"""
Approval Workflow Service Implementation
Handles change plan approval processes, timeouts, and automatic cancellation
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from aws_lambda_powertools import Logger

from .interfaces import ApprovalWorkflowService
from ..models.data_models import (
    ChangePlan, ApprovalRequest, ApprovalWorkflowConfig, ApprovalRule
)
from ..models.enums import ApprovalStatus, ChangePlanStatus, RiskLevel, ErrorCodes
from ..models.exceptions import InfrastructureException

logger = Logger()


class ApprovalWorkflowServiceImpl(ApprovalWorkflowService):
    """Implementation of approval workflow service"""
    
    def __init__(self, config: Optional[ApprovalWorkflowConfig] = None):
        """Initialize the approval workflow service
        
        Args:
            config: Configuration for approval workflow behavior
        """
        self.config = config or ApprovalWorkflowConfig()
        # In-memory storage for demo - in production this would be a database
        self._approval_requests: Dict[str, ApprovalRequest] = {}
        self._change_plans: Dict[str, ChangePlan] = {}
        self._timeout_tasks: Dict[str, asyncio.Task] = {}
        
    async def submit_for_approval(self, change_plan: ChangePlan) -> str:
        """Submit a change plan for approval
        
        Args:
            change_plan: The change plan to submit for approval
            
        Returns:
            str: The approval request ID
            
        Raises:
            InfrastructureException: If submission fails
        """
        try:
            logger.info(f"Submitting change plan {change_plan.id} for approval")
            
            # Check if auto-approval applies
            if await self._should_auto_approve(change_plan):
                logger.info(f"Auto-approving change plan {change_plan.id}")
                change_plan.status = ChangePlanStatus.APPROVED
                change_plan.approved_at = datetime.now()
                change_plan.approved_by = "system"
                self._change_plans[change_plan.id] = change_plan
                return f"auto-approved-{change_plan.id}"
            
            # Create approval request
            approval_id = str(uuid.uuid4())
            expires_at = datetime.now() + timedelta(minutes=self.config.default_timeout_minutes)
            
            approval_request = ApprovalRequest(
                id=approval_id,
                change_plan_id=change_plan.id,
                project_id=change_plan.project_id,
                requester_id=change_plan.created_by or "unknown",
                approver_id=None,
                status=ApprovalStatus.PENDING,
                created_at=datetime.now(),
                expires_at=expires_at,
                timeout_minutes=self.config.default_timeout_minutes
            )
            
            # Store the approval request and change plan
            self._approval_requests[approval_id] = approval_request
            change_plan.status = ChangePlanStatus.PENDING
            self._change_plans[change_plan.id] = change_plan
            
            # Start timeout task
            await self._start_timeout_task(approval_id)
            
            logger.info(f"Created approval request {approval_id} for change plan {change_plan.id}")
            return approval_id
            
        except Exception as e:
            logger.error(f"Failed to submit change plan for approval: {str(e)}")
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Failed to submit change plan for approval: {str(e)}"
            )
    
    async def approve_plan(self, plan_id: str, approver_id: str) -> ChangePlan:
        """Approve a change plan
        
        Args:
            plan_id: The change plan ID to approve
            approver_id: ID of the user approving the plan
            
        Returns:
            ChangePlan: The approved change plan
            
        Raises:
            InfrastructureException: If approval fails
        """
        try:
            logger.info(f"Approving change plan {plan_id} by user {approver_id}")
            
            # Find the approval request
            approval_request = await self._find_approval_by_plan_id(plan_id)
            if not approval_request:
                raise InfrastructureException(
                    ErrorCodes.APPROVAL_NOT_FOUND,
                    f"No pending approval found for change plan {plan_id}"
                )
            
            # Check if already processed
            if approval_request.status != ApprovalStatus.PENDING:
                raise InfrastructureException(
                    ErrorCodes.APPROVAL_ALREADY_PROCESSED,
                    f"Approval request {approval_request.id} has already been processed"
                )
            
            # Check if expired
            if datetime.now() > approval_request.expires_at:
                await self._expire_approval(approval_request.id)
                raise InfrastructureException(
                    ErrorCodes.APPROVAL_TIMEOUT,
                    f"Approval request {approval_request.id} has expired"
                )
            
            # Update approval request
            approval_request.status = ApprovalStatus.APPROVED
            approval_request.approver_id = approver_id
            approval_request.approved_at = datetime.now()
            
            # Update change plan
            change_plan = self._change_plans.get(plan_id)
            if change_plan:
                change_plan.status = ChangePlanStatus.APPROVED
                change_plan.approved_by = approver_id
                change_plan.approved_at = datetime.now()
            
            # Cancel timeout task
            await self._cancel_timeout_task(approval_request.id)
            
            logger.info(f"Successfully approved change plan {plan_id}")
            return change_plan
            
        except InfrastructureException:
            raise
        except Exception as e:
            logger.error(f"Failed to approve change plan {plan_id}: {str(e)}")
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Failed to approve change plan: {str(e)}"
            )
    
    async def reject_plan(self, plan_id: str, approver_id: str, reason: str) -> ChangePlan:
        """Reject a change plan
        
        Args:
            plan_id: The change plan ID to reject
            approver_id: ID of the user rejecting the plan
            reason: Reason for rejection
            
        Returns:
            ChangePlan: The rejected change plan
            
        Raises:
            InfrastructureException: If rejection fails
        """
        try:
            logger.info(f"Rejecting change plan {plan_id} by user {approver_id}")
            
            # Find the approval request
            approval_request = await self._find_approval_by_plan_id(plan_id)
            if not approval_request:
                raise InfrastructureException(
                    ErrorCodes.APPROVAL_NOT_FOUND,
                    f"No pending approval found for change plan {plan_id}"
                )
            
            # Check if already processed
            if approval_request.status != ApprovalStatus.PENDING:
                raise InfrastructureException(
                    ErrorCodes.APPROVAL_ALREADY_PROCESSED,
                    f"Approval request {approval_request.id} has already been processed"
                )
            
            # Update approval request
            approval_request.status = ApprovalStatus.REJECTED
            approval_request.approver_id = approver_id
            approval_request.rejected_at = datetime.now()
            approval_request.rejection_reason = reason
            
            # Update change plan
            change_plan = self._change_plans.get(plan_id)
            if change_plan:
                change_plan.status = ChangePlanStatus.REJECTED
            
            # Cancel timeout task
            await self._cancel_timeout_task(approval_request.id)
            
            logger.info(f"Successfully rejected change plan {plan_id}")
            return change_plan
            
        except InfrastructureException:
            raise
        except Exception as e:
            logger.error(f"Failed to reject change plan {plan_id}: {str(e)}")
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Failed to reject change plan: {str(e)}"
            )
    
    async def get_pending_approvals(self, user_id: str) -> List[ChangePlan]:
        """Get change plans pending approval for a user
        
        Args:
            user_id: ID of the user to get pending approvals for
            
        Returns:
            List[ChangePlan]: List of change plans pending approval
        """
        try:
            logger.info(f"Getting pending approvals for user {user_id}")
            
            pending_plans = []
            current_time = datetime.now()
            
            for approval_request in self._approval_requests.values():
                # Skip if not pending or expired
                if approval_request.status != ApprovalStatus.PENDING:
                    continue
                if current_time > approval_request.expires_at:
                    continue
                
                # Check if user can approve (simplified logic)
                # In production, this would check project permissions and approval rules
                change_plan = self._change_plans.get(approval_request.change_plan_id)
                if change_plan and self._can_user_approve(user_id, change_plan):
                    pending_plans.append(change_plan)
            
            logger.info(f"Found {len(pending_plans)} pending approvals for user {user_id}")
            return pending_plans
            
        except Exception as e:
            logger.error(f"Failed to get pending approvals for user {user_id}: {str(e)}")
            return []
    
    async def check_approval_timeout(self, plan_id: str) -> bool:
        """Check if a plan has exceeded approval timeout
        
        Args:
            plan_id: The change plan ID to check
            
        Returns:
            bool: True if the plan has timed out, False otherwise
        """
        try:
            approval_request = await self._find_approval_by_plan_id(plan_id)
            if not approval_request:
                return False
            
            if approval_request.status != ApprovalStatus.PENDING:
                return False
            
            has_timed_out = datetime.now() > approval_request.expires_at
            
            if has_timed_out:
                logger.info(f"Change plan {plan_id} has timed out")
                await self._expire_approval(approval_request.id)
            
            return has_timed_out
            
        except Exception as e:
            logger.error(f"Failed to check timeout for plan {plan_id}: {str(e)}")
            return False
    
    async def _should_auto_approve(self, change_plan: ChangePlan) -> bool:
        """Check if a change plan should be auto-approved
        
        Args:
            change_plan: The change plan to check
            
        Returns:
            bool: True if should be auto-approved, False otherwise
        """
        if not self.config.auto_approval_enabled:
            return False
        
        # Check approval rules
        for rule in self.config.approval_rules:
            if await self._matches_approval_rule(change_plan, rule):
                logger.info(f"Change plan {change_plan.id} matches auto-approval rule")
                return True
        
        return False
    
    async def _matches_approval_rule(self, change_plan: ChangePlan, rule: ApprovalRule) -> bool:
        """Check if a change plan matches an approval rule
        
        Args:
            change_plan: The change plan to check
            rule: The approval rule to match against
            
        Returns:
            bool: True if the plan matches the rule, False otherwise
        """
        # Check risk level - all changes must be at or below the max allowed risk level
        for change in change_plan.changes:
            if change.risk_level > rule.max_risk_level:
                return False
        
        # Check resource types - all resource types must be in the allowed list
        if rule.resource_types:
            plan_resource_types = {change.resource_type for change in change_plan.changes}
            if not plan_resource_types.issubset(set(rule.resource_types)):
                return False
        
        # Additional condition checking could be implemented here
        # For now, we'll consider it a match if risk level and resource types are satisfied
        return True
    
    async def _find_approval_by_plan_id(self, plan_id: str) -> Optional[ApprovalRequest]:
        """Find an approval request by change plan ID
        
        Args:
            plan_id: The change plan ID to search for
            
        Returns:
            Optional[ApprovalRequest]: The approval request if found, None otherwise
        """
        for approval_request in self._approval_requests.values():
            if approval_request.change_plan_id == plan_id:
                return approval_request
        return None
    
    def _can_user_approve(self, user_id: str, change_plan: ChangePlan) -> bool:
        """Check if a user can approve a change plan
        
        Args:
            user_id: ID of the user
            change_plan: The change plan to check
            
        Returns:
            bool: True if user can approve, False otherwise
        """
        # Simplified logic - in production this would check:
        # - Project membership and roles
        # - Approval permissions
        # - Conflict of interest (user shouldn't approve their own changes)
        
        if change_plan.created_by == user_id:
            return False  # Users can't approve their own changes
        
        # For demo purposes, assume any other user can approve
        return True
    
    async def _start_timeout_task(self, approval_id: str) -> None:
        """Start a timeout task for an approval request
        
        Args:
            approval_id: The approval request ID
        """
        approval_request = self._approval_requests.get(approval_id)
        if not approval_request:
            return
        
        timeout_seconds = (approval_request.expires_at - datetime.now()).total_seconds()
        if timeout_seconds <= 0:
            await self._expire_approval(approval_id)
            return
        
        async def timeout_handler():
            await asyncio.sleep(timeout_seconds)
            await self._expire_approval(approval_id)
        
        task = asyncio.create_task(timeout_handler())
        self._timeout_tasks[approval_id] = task
    
    async def _cancel_timeout_task(self, approval_id: str) -> None:
        """Cancel a timeout task for an approval request
        
        Args:
            approval_id: The approval request ID
        """
        task = self._timeout_tasks.get(approval_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._timeout_tasks.pop(approval_id, None)
    
    async def _expire_approval(self, approval_id: str) -> None:
        """Expire an approval request due to timeout
        
        Args:
            approval_id: The approval request ID to expire
        """
        try:
            approval_request = self._approval_requests.get(approval_id)
            if not approval_request or approval_request.status != ApprovalStatus.PENDING:
                return
            
            logger.info(f"Expiring approval request {approval_id} due to timeout")
            
            # Update approval request status
            approval_request.status = ApprovalStatus.EXPIRED
            
            # Update change plan status
            change_plan = self._change_plans.get(approval_request.change_plan_id)
            if change_plan:
                change_plan.status = ChangePlanStatus.REJECTED
            
            # Clean up timeout task
            self._timeout_tasks.pop(approval_id, None)
            
        except Exception as e:
            logger.error(f"Failed to expire approval {approval_id}: {str(e)}")