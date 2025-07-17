"""
Approval Workflow Service Demo
Demonstrates the approval workflow functionality including auto-approval and manual approval processes
"""
import asyncio
from datetime import datetime

from src.services.approval_workflow import ApprovalWorkflowServiceImpl
from src.models.data_models import (
    ChangePlan, ChangeSummary, Change, ApprovalWorkflowConfig, ApprovalRule
)
from src.models.enums import ChangePlanStatus, ChangeAction, RiskLevel


async def demo_approval_workflow():
    """Demonstrate approval workflow functionality"""
    print("=== AWS Infrastructure Manager - Approval Workflow Demo ===\n")
    
    # Configure approval workflow with auto-approval rules
    config = ApprovalWorkflowConfig(
        default_timeout_minutes=30,
        auto_approval_enabled=True,
        approval_rules=[
            ApprovalRule(
                condition="low_risk_ec2_s3",
                max_risk_level=RiskLevel.LOW,
                resource_types=["EC2::Instance", "S3::Bucket"]
            )
        ]
    )
    
    # Create approval service
    approval_service = ApprovalWorkflowServiceImpl(config)
    
    # Demo 1: Auto-approved change plan (low risk)
    print("1. Testing Auto-Approval for Low-Risk Changes")
    print("-" * 50)
    
    low_risk_plan = ChangePlan(
        id="plan-auto-approve",
        project_id="project-demo",
        summary=ChangeSummary(
            total_changes=2,
            creates=2,
            updates=0,
            deletes=0,
            estimated_cost=50.0
        ),
        changes=[
            Change(
                action=ChangeAction.CREATE,
                resource_type="EC2::Instance",
                resource_id="i-demo-001",
                risk_level=RiskLevel.LOW
            ),
            Change(
                action=ChangeAction.CREATE,
                resource_type="S3::Bucket",
                resource_id="bucket-demo-001",
                risk_level=RiskLevel.LOW
            )
        ],
        created_at=datetime.now(),
        status=ChangePlanStatus.PENDING,
        created_by="developer-alice"
    )
    
    approval_id = await approval_service.submit_for_approval(low_risk_plan)
    print(f"✅ Change plan submitted: {low_risk_plan.id}")
    print(f"📋 Approval ID: {approval_id}")
    print(f"🎯 Status: {low_risk_plan.status.value}")
    print(f"👤 Approved by: {low_risk_plan.approved_by}")
    print()
    
    # Demo 2: Manual approval required (high risk)
    print("2. Testing Manual Approval for High-Risk Changes")
    print("-" * 50)
    
    high_risk_plan = ChangePlan(
        id="plan-manual-approve",
        project_id="project-demo",
        summary=ChangeSummary(
            total_changes=1,
            creates=0,
            updates=0,
            deletes=1,
            estimated_cost=0.0
        ),
        changes=[
            Change(
                action=ChangeAction.DELETE,
                resource_type="RDS::DBInstance",
                resource_id="db-production-001",
                risk_level=RiskLevel.HIGH
            )
        ],
        created_at=datetime.now(),
        status=ChangePlanStatus.PENDING,
        created_by="developer-bob"
    )
    
    approval_id = await approval_service.submit_for_approval(high_risk_plan)
    print(f"📝 Change plan submitted: {high_risk_plan.id}")
    print(f"📋 Approval ID: {approval_id}")
    print(f"🎯 Status: {high_risk_plan.status.value}")
    print(f"⏳ Requires manual approval")
    print()
    
    # Demo 3: Get pending approvals
    print("3. Getting Pending Approvals")
    print("-" * 50)
    
    pending_approvals = await approval_service.get_pending_approvals("manager-charlie")
    print(f"📊 Pending approvals for manager-charlie: {len(pending_approvals)}")
    
    for plan in pending_approvals:
        print(f"  - Plan ID: {plan.id}")
        print(f"    Created by: {plan.created_by}")
        print(f"    Changes: {plan.summary.total_changes}")
        print(f"    Risk level: {max([c.risk_level.name for c in plan.changes])}")
    print()
    
    # Demo 4: Approve the high-risk plan
    print("4. Approving High-Risk Change Plan")
    print("-" * 50)
    
    approved_plan = await approval_service.approve_plan(
        high_risk_plan.id, 
        "manager-charlie"
    )
    print(f"✅ Plan approved: {approved_plan.id}")
    print(f"🎯 Status: {approved_plan.status.value}")
    print(f"👤 Approved by: {approved_plan.approved_by}")
    print(f"📅 Approved at: {approved_plan.approved_at}")
    print()
    
    # Demo 5: Create and reject a plan
    print("5. Rejecting a Change Plan")
    print("-" * 50)
    
    reject_plan = ChangePlan(
        id="plan-to-reject",
        project_id="project-demo",
        summary=ChangeSummary(
            total_changes=1,
            creates=1,
            updates=0,
            deletes=0
        ),
        changes=[
            Change(
                action=ChangeAction.CREATE,
                resource_type="Lambda::Function",
                resource_id="lambda-suspicious",
                risk_level=RiskLevel.MEDIUM
            )
        ],
        created_at=datetime.now(),
        status=ChangePlanStatus.PENDING,
        created_by="developer-dave"
    )
    
    await approval_service.submit_for_approval(reject_plan)
    
    rejected_plan = await approval_service.reject_plan(
        reject_plan.id,
        "manager-charlie",
        "Security review required for new Lambda functions"
    )
    print(f"❌ Plan rejected: {rejected_plan.id}")
    print(f"🎯 Status: {rejected_plan.status.value}")
    print(f"👤 Rejected by: manager-charlie")
    print(f"📝 Reason: Security review required for new Lambda functions")
    print()
    
    # Demo 6: Check timeout functionality
    print("6. Testing Timeout Functionality")
    print("-" * 50)
    
    timeout_plan = ChangePlan(
        id="plan-timeout-test",
        project_id="project-demo",
        summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0),
        changes=[
            Change(
                action=ChangeAction.CREATE,
                resource_type="EC2::SecurityGroup",
                resource_id="sg-test",
                risk_level=RiskLevel.MEDIUM
            )
        ],
        created_at=datetime.now(),
        status=ChangePlanStatus.PENDING,
        created_by="developer-eve"
    )
    
    await approval_service.submit_for_approval(timeout_plan)
    
    # Check if timeout occurred (should be False for fresh approval)
    has_timed_out = await approval_service.check_approval_timeout(timeout_plan.id)
    print(f"⏰ Has plan timed out? {has_timed_out}")
    print(f"🎯 Current status: {timeout_plan.status.value}")
    print()
    
    print("=== Demo Complete ===")
    print("The approval workflow service successfully demonstrates:")
    print("✅ Auto-approval for low-risk changes")
    print("✅ Manual approval workflow for high-risk changes")
    print("✅ Approval and rejection processes")
    print("✅ Pending approval management")
    print("✅ Timeout handling")


if __name__ == "__main__":
    asyncio.run(demo_approval_workflow())