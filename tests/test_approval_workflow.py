"""
Tests for ApprovalWorkflowService
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from src.services.approval_workflow import ApprovalWorkflowServiceImpl
from src.models.data_models import (
    ChangePlan, ChangeSummary, Change, ApprovalWorkflowConfig, ApprovalRule
)
from src.models.enums import (
    ChangePlanStatus, ChangeAction, RiskLevel, ApprovalStatus, ErrorCodes
)
from src.models.exceptions import InfrastructureException


@pytest.fixture
def sample_change_plan():
    """Create a sample change plan for testing"""
    return ChangePlan(
        id="plan-123",
        project_id="project-456",
        summary=ChangeSummary(
            total_changes=2,
            creates=1,
            updates=1,
            deletes=0
        ),
        changes=[
            Change(
                action=ChangeAction.CREATE,
                resource_type="EC2::Instance",
                resource_id="i-123",
                risk_level=RiskLevel.LOW
            ),
            Change(
                action=ChangeAction.UPDATE,
                resource_type="RDS::DBInstance",
                resource_id="db-456",
                risk_level=RiskLevel.MEDIUM
            )
        ],
        created_at=datetime.now(),
        status=ChangePlanStatus.PENDING,
        created_by="user-789"
    )


@pytest.fixture
def approval_config():
    """Create approval workflow configuration for testing"""
    return ApprovalWorkflowConfig(
        default_timeout_minutes=30,
        auto_approval_enabled=True,
        approval_rules=[
            ApprovalRule(
                condition="low_risk_only",
                max_risk_level=RiskLevel.LOW,
                resource_types=["EC2::Instance", "S3::Bucket"]
            )
        ]
    )


@pytest.fixture
def approval_service(approval_config):
    """Create approval workflow service instance"""
    return ApprovalWorkflowServiceImpl(approval_config)


class TestApprovalWorkflowService:
    """Test cases for ApprovalWorkflowService"""
    
    @pytest.mark.asyncio
    async def test_submit_for_approval_manual(self, approval_service, sample_change_plan):
        """Test submitting a change plan for manual approval"""
        # This plan has medium risk, so won't be auto-approved
        approval_id = await approval_service.submit_for_approval(sample_change_plan)
        
        assert approval_id is not None
        assert not approval_id.startswith("auto-approved")
        assert sample_change_plan.status == ChangePlanStatus.PENDING
        
        # Check that approval request was created
        approval_request = await approval_service._find_approval_by_plan_id(sample_change_plan.id)
        assert approval_request is not None
        assert approval_request.status == ApprovalStatus.PENDING
        assert approval_request.change_plan_id == sample_change_plan.id
    
    @pytest.mark.asyncio
    async def test_submit_for_approval_auto_approved(self, approval_service):
        """Test submitting a change plan that gets auto-approved"""
        # Create a low-risk plan that should be auto-approved
        low_risk_plan = ChangePlan(
            id="plan-low-risk",
            project_id="project-456",
            summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0),
            changes=[
                Change(
                    action=ChangeAction.CREATE,
                    resource_type="EC2::Instance",
                    resource_id="i-low-risk",
                    risk_level=RiskLevel.LOW
                )
            ],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING,
            created_by="user-789"
        )
        
        approval_id = await approval_service.submit_for_approval(low_risk_plan)
        
        assert approval_id.startswith("auto-approved")
        assert low_risk_plan.status == ChangePlanStatus.APPROVED
        assert low_risk_plan.approved_by == "system"
        assert low_risk_plan.approved_at is not None
    
    @pytest.mark.asyncio
    async def test_approve_plan_success(self, approval_service, sample_change_plan):
        """Test successfully approving a change plan"""
        # Submit for approval first
        approval_id = await approval_service.submit_for_approval(sample_change_plan)
        
        # Approve the plan
        approved_plan = await approval_service.approve_plan(sample_change_plan.id, "approver-123")
        
        assert approved_plan.status == ChangePlanStatus.APPROVED
        assert approved_plan.approved_by == "approver-123"
        assert approved_plan.approved_at is not None
        
        # Check approval request status
        approval_request = await approval_service._find_approval_by_plan_id(sample_change_plan.id)
        assert approval_request.status == ApprovalStatus.APPROVED
        assert approval_request.approver_id == "approver-123"
    
    @pytest.mark.asyncio
    async def test_approve_plan_not_found(self, approval_service):
        """Test approving a non-existent change plan"""
        with pytest.raises(InfrastructureException) as exc_info:
            await approval_service.approve_plan("non-existent-plan", "approver-123")
        
        assert exc_info.value.code == ErrorCodes.APPROVAL_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_approve_plan_already_processed(self, approval_service, sample_change_plan):
        """Test approving an already processed change plan"""
        # Submit and approve first
        await approval_service.submit_for_approval(sample_change_plan)
        await approval_service.approve_plan(sample_change_plan.id, "approver-123")
        
        # Try to approve again
        with pytest.raises(InfrastructureException) as exc_info:
            await approval_service.approve_plan(sample_change_plan.id, "approver-456")
        
        assert exc_info.value.code == ErrorCodes.APPROVAL_ALREADY_PROCESSED
    
    @pytest.mark.asyncio
    async def test_reject_plan_success(self, approval_service, sample_change_plan):
        """Test successfully rejecting a change plan"""
        # Submit for approval first
        await approval_service.submit_for_approval(sample_change_plan)
        
        # Reject the plan
        rejected_plan = await approval_service.reject_plan(
            sample_change_plan.id, 
            "approver-123", 
            "Security concerns"
        )
        
        assert rejected_plan.status == ChangePlanStatus.REJECTED
        
        # Check approval request status
        approval_request = await approval_service._find_approval_by_plan_id(sample_change_plan.id)
        assert approval_request.status == ApprovalStatus.REJECTED
        assert approval_request.approver_id == "approver-123"
        assert approval_request.rejection_reason == "Security concerns"
        assert approval_request.rejected_at is not None
    
    @pytest.mark.asyncio
    async def test_reject_plan_not_found(self, approval_service):
        """Test rejecting a non-existent change plan"""
        with pytest.raises(InfrastructureException) as exc_info:
            await approval_service.reject_plan("non-existent-plan", "approver-123", "reason")
        
        assert exc_info.value.code == ErrorCodes.APPROVAL_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_get_pending_approvals(self, approval_service, sample_change_plan):
        """Test getting pending approvals for a user"""
        # Submit a plan for approval
        await approval_service.submit_for_approval(sample_change_plan)
        
        # Get pending approvals
        pending_plans = await approval_service.get_pending_approvals("approver-123")
        
        assert len(pending_plans) == 1
        assert pending_plans[0].id == sample_change_plan.id
    
    @pytest.mark.asyncio
    async def test_get_pending_approvals_excludes_own_plans(self, approval_service, sample_change_plan):
        """Test that users don't see their own plans in pending approvals"""
        # Submit a plan for approval
        await approval_service.submit_for_approval(sample_change_plan)
        
        # User who created the plan shouldn't see it in pending approvals
        pending_plans = await approval_service.get_pending_approvals("user-789")
        
        assert len(pending_plans) == 0
    
    @pytest.mark.asyncio
    async def test_check_approval_timeout_not_expired(self, approval_service, sample_change_plan):
        """Test checking timeout for a non-expired approval"""
        await approval_service.submit_for_approval(sample_change_plan)
        
        has_timed_out = await approval_service.check_approval_timeout(sample_change_plan.id)
        
        assert has_timed_out is False
    
    @pytest.mark.asyncio
    async def test_check_approval_timeout_expired(self, approval_service):
        """Test checking timeout for an expired approval"""
        # Create a plan with very short timeout (1 minute, but we'll manually expire it)
        short_timeout_config = ApprovalWorkflowConfig(default_timeout_minutes=1)
        service = ApprovalWorkflowServiceImpl(short_timeout_config)
        
        expired_plan = ChangePlan(
            id="expired-plan",
            project_id="project-456",
            summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0),
            changes=[
                Change(
                    action=ChangeAction.CREATE,
                    resource_type="RDS::DBInstance",  # High risk, won't auto-approve
                    resource_id="db-expired",
                    risk_level=RiskLevel.HIGH
                )
            ],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING,
            created_by="user-789"
        )
        
        await service.submit_for_approval(expired_plan)
        
        # Manually set the expiration time to the past to simulate timeout
        approval_request = await service._find_approval_by_plan_id(expired_plan.id)
        approval_request.expires_at = datetime.now() - timedelta(minutes=1)
        
        has_timed_out = await service.check_approval_timeout(expired_plan.id)
        
        assert has_timed_out is True
        
        # Check that the approval was expired
        approval_request = await service._find_approval_by_plan_id(expired_plan.id)
        assert approval_request.status == ApprovalStatus.EXPIRED
        assert expired_plan.status == ChangePlanStatus.REJECTED
    
    @pytest.mark.asyncio
    async def test_auto_approval_rules_matching(self, approval_service):
        """Test that auto-approval rules work correctly"""
        # Create a plan that matches the approval rule
        matching_plan = ChangePlan(
            id="matching-plan",
            project_id="project-456",
            summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0),
            changes=[
                Change(
                    action=ChangeAction.CREATE,
                    resource_type="EC2::Instance",  # Matches rule
                    resource_id="i-matching",
                    risk_level=RiskLevel.LOW  # Matches rule
                )
            ],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING,
            created_by="user-789"
        )
        
        should_auto_approve = await approval_service._should_auto_approve(matching_plan)
        assert should_auto_approve is True
    
    @pytest.mark.asyncio
    async def test_auto_approval_rules_not_matching_risk(self, approval_service):
        """Test that auto-approval rules reject high-risk changes"""
        # Create a plan with high risk that shouldn't match
        high_risk_plan = ChangePlan(
            id="high-risk-plan",
            project_id="project-456",
            summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0),
            changes=[
                Change(
                    action=ChangeAction.CREATE,
                    resource_type="EC2::Instance",  # Matches rule
                    resource_id="i-high-risk",
                    risk_level=RiskLevel.HIGH  # Doesn't match rule
                )
            ],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING,
            created_by="user-789"
        )
        
        should_auto_approve = await approval_service._should_auto_approve(high_risk_plan)
        assert should_auto_approve is False
    
    @pytest.mark.asyncio
    async def test_auto_approval_rules_not_matching_resource_type(self, approval_service):
        """Test that auto-approval rules reject non-matching resource types"""
        # Create a plan with non-matching resource type
        non_matching_plan = ChangePlan(
            id="non-matching-plan",
            project_id="project-456",
            summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0),
            changes=[
                Change(
                    action=ChangeAction.CREATE,
                    resource_type="RDS::DBInstance",  # Doesn't match rule
                    resource_id="db-non-matching",
                    risk_level=RiskLevel.LOW  # Matches rule
                )
            ],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING,
            created_by="user-789"
        )
        
        should_auto_approve = await approval_service._should_auto_approve(non_matching_plan)
        assert should_auto_approve is False
    
    def test_can_user_approve_own_plan(self, approval_service, sample_change_plan):
        """Test that users cannot approve their own plans"""
        can_approve = approval_service._can_user_approve("user-789", sample_change_plan)
        assert can_approve is False
    
    def test_can_user_approve_other_plan(self, approval_service, sample_change_plan):
        """Test that users can approve other users' plans"""
        can_approve = approval_service._can_user_approve("other-user", sample_change_plan)
        assert can_approve is True
    
    @pytest.mark.asyncio
    async def test_timeout_task_management(self, approval_service, sample_change_plan):
        """Test that timeout tasks are properly managed"""
        # Submit for approval
        approval_id = await approval_service.submit_for_approval(sample_change_plan)
        
        # Check that timeout task was created
        approval_request = await approval_service._find_approval_by_plan_id(sample_change_plan.id)
        assert approval_request.id in approval_service._timeout_tasks
        
        # Approve the plan
        await approval_service.approve_plan(sample_change_plan.id, "approver-123")
        
        # Check that timeout task was cancelled
        assert approval_request.id not in approval_service._timeout_tasks