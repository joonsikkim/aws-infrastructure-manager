"""
Change Plan Engine Demo

This example demonstrates how to use the ChangePlanEngine to generate
infrastructure change plans by comparing current and desired states.
"""
import asyncio
from datetime import datetime
from typing import Optional

from src.services.change_plan_engine import DefaultChangePlanEngine
from src.services.interfaces import StateManagementService
from src.models.data_models import (
    InfrastructureState, Resource, StateMetadata, ChangePlan
)
from src.models.enums import ResourceStatus


class MockStateService(StateManagementService):
    """Mock state service for demo purposes"""
    
    def __init__(self):
        self.current_state: Optional[InfrastructureState] = None
    
    async def get_current_state(self, project_id: str) -> Optional[InfrastructureState]:
        return self.current_state
    
    async def save_state(self, project_id: str, state: InfrastructureState) -> None:
        self.current_state = state
    
    async def get_state_history(self, project_id: str, limit: Optional[int] = None):
        return []
    
    def compare_states(self, current_state: InfrastructureState, desired_state: InfrastructureState) -> ChangePlan:
        # This method is not used by the engine directly
        pass


def create_sample_current_state() -> InfrastructureState:
    """Create a sample current infrastructure state"""
    resources = [
        Resource(
            id="vpc-12345678",
            project_id="demo-project",
            type="VPC::VPC",
            name="demo-vpc",
            region="us-east-1",
            properties={
                "cidrBlock": "10.0.0.0/16",
                "enableDnsHostnames": True,
                "enableDnsSupport": True
            },
            tags={"Environment": "demo", "Project": "aws-infra-manager"},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-12345678"
        ),
        Resource(
            id="subnet-12345678",
            project_id="demo-project",
            type="VPC::Subnet",
            name="demo-subnet",
            region="us-east-1",
            properties={
                "vpcId": "vpc-12345678",
                "cidrBlock": "10.0.1.0/24",
                "availabilityZone": "us-east-1a"
            },
            tags={"Environment": "demo", "Project": "aws-infra-manager"},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-12345678"
        ),
        Resource(
            id="i-1234567890abcdef0",
            project_id="demo-project",
            type="EC2::Instance",
            name="demo-instance",
            region="us-east-1",
            properties={
                "instanceType": "t3.micro",
                "imageId": "ami-12345678",
                "subnetId": "subnet-12345678"
            },
            tags={"Environment": "demo", "Project": "aws-infra-manager"},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        )
    ]
    
    return InfrastructureState(
        project_id="demo-project",
        version="1.0.0",
        timestamp=datetime.now(),
        resources=resources,
        metadata=StateMetadata(
            last_modified_by="demo@example.com",
            change_description="Initial infrastructure setup"
        )
    )


def create_sample_desired_state() -> InfrastructureState:
    """Create a sample desired infrastructure state with changes"""
    resources = [
        # Keep VPC unchanged
        Resource(
            id="vpc-12345678",
            project_id="demo-project",
            type="VPC::VPC",
            name="demo-vpc",
            region="us-east-1",
            properties={
                "cidrBlock": "10.0.0.0/16",
                "enableDnsHostnames": True,
                "enableDnsSupport": True
            },
            tags={"Environment": "demo", "Project": "aws-infra-manager"},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:ec2:us-east-1:123456789012:vpc/vpc-12345678"
        ),
        # Keep subnet unchanged
        Resource(
            id="subnet-12345678",
            project_id="demo-project",
            type="VPC::Subnet",
            name="demo-subnet",
            region="us-east-1",
            properties={
                "vpcId": "vpc-12345678",
                "cidrBlock": "10.0.1.0/24",
                "availabilityZone": "us-east-1a"
            },
            tags={"Environment": "demo", "Project": "aws-infra-manager"},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:ec2:us-east-1:123456789012:subnet/subnet-12345678"
        ),
        # Update EC2 instance (change instance type)
        Resource(
            id="i-1234567890abcdef0",
            project_id="demo-project",
            type="EC2::Instance",
            name="demo-instance",
            region="us-east-1",
            properties={
                "instanceType": "t3.small",  # Changed from t3.micro
                "imageId": "ami-12345678",
                "subnetId": "subnet-12345678"
            },
            tags={"Environment": "demo", "Project": "aws-infra-manager", "Updated": "true"},  # Added tag
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        ),
        # Add new RDS instance
        Resource(
            id="db-1234567890abcdef0",
            project_id="demo-project",
            type="RDS::DBInstance",
            name="demo-database",
            region="us-east-1",
            properties={
                "dbInstanceClass": "db.t3.micro",
                "engine": "mysql",
                "engineVersion": "8.0",
                "allocatedStorage": 20,
                "dbSubnetGroupName": "demo-db-subnet-group"
            },
            tags={"Environment": "demo", "Project": "aws-infra-manager"},
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:rds:us-east-1:123456789012:db:demo-database"
        )
    ]
    
    return InfrastructureState(
        project_id="demo-project",
        version="1.1.0",
        timestamp=datetime.now(),
        resources=resources,
        metadata=StateMetadata(
            last_modified_by="demo@example.com",
            change_description="Add database and update instance"
        )
    )


async def demo_change_plan_generation():
    """Demonstrate change plan generation"""
    print("=== Change Plan Engine Demo ===\n")
    
    # Create mock state service and engine
    state_service = MockStateService()
    engine = DefaultChangePlanEngine(state_service)
    
    # Set up current state
    current_state = create_sample_current_state()
    state_service.current_state = current_state
    
    print("Current Infrastructure State:")
    print(f"  Project: {current_state.project_id}")
    print(f"  Version: {current_state.version}")
    print(f"  Resources: {len(current_state.resources)}")
    for resource in current_state.resources:
        print(f"    - {resource.type}: {resource.name} ({resource.id})")
    print()
    
    # Create desired state
    desired_state = create_sample_desired_state()
    
    print("Desired Infrastructure State:")
    print(f"  Project: {desired_state.project_id}")
    print(f"  Version: {desired_state.version}")
    print(f"  Resources: {len(desired_state.resources)}")
    for resource in desired_state.resources:
        print(f"    - {resource.type}: {resource.name} ({resource.id})")
    print()
    
    # Generate change plan
    print("Generating change plan...")
    change_plan = await engine.generate_plan("demo-project", desired_state)
    
    print(f"\nChange Plan Generated:")
    print(f"  Plan ID: {change_plan.id}")
    print(f"  Status: {change_plan.status.value}")
    print(f"  Total Changes: {change_plan.summary.total_changes}")
    print(f"    - Creates: {change_plan.summary.creates}")
    print(f"    - Updates: {change_plan.summary.updates}")
    print(f"    - Deletes: {change_plan.summary.deletes}")
    print()
    
    print("Detailed Changes:")
    for i, change in enumerate(change_plan.changes, 1):
        print(f"  {i}. {change.action.value.upper()} {change.resource_type} ({change.resource_id})")
        print(f"     Risk Level: {change.risk_level.value}")
        if change.dependencies:
            print(f"     Dependencies: {', '.join(change.dependencies)}")
        print()
    
    # Analyze dependencies
    print("Analyzing dependencies...")
    dependency_graph = await engine.analyze_dependencies(change_plan.changes)
    print(f"Dependency Graph: {len(dependency_graph.nodes)} nodes, {len(dependency_graph.edges)} edges")
    if dependency_graph.edges:
        print("Dependencies:")
        for from_node, to_node in dependency_graph.edges:
            print(f"  {from_node} -> {to_node}")
    print()
    
    # Estimate cost
    print("Estimating costs...")
    cost_estimate = await engine.estimate_cost(change_plan)
    print(f"Estimated Monthly Cost: ${cost_estimate.total_monthly_cost:.2f} {cost_estimate.currency}")
    if cost_estimate.cost_breakdown:
        print("Cost Breakdown:")
        for resource, cost in cost_estimate.cost_breakdown.items():
            print(f"  {resource}: ${cost:.2f}")
    print()
    
    # Validate plan
    print("Validating change plan...")
    validation_result = await engine.validate_plan(change_plan)
    print(f"Validation Result: {'VALID' if validation_result.is_valid else 'INVALID'}")
    
    if validation_result.errors:
        print("Errors:")
        for error in validation_result.errors:
            print(f"  - {error}")
    
    if validation_result.warnings:
        print("Warnings:")
        for warning in validation_result.warnings:
            print(f"  - {warning}")
    
    print("\n=== Demo Complete ===")


async def demo_no_current_state():
    """Demonstrate change plan generation with no current state"""
    print("\n=== Demo: No Current State ===\n")
    
    # Create mock state service with no current state
    state_service = MockStateService()
    state_service.current_state = None  # No current state
    engine = DefaultChangePlanEngine(state_service)
    
    # Create desired state
    desired_state = create_sample_desired_state()
    
    print("No current state exists - all resources will be created")
    print(f"Desired resources: {len(desired_state.resources)}")
    
    # Generate change plan
    change_plan = await engine.generate_plan("demo-project", desired_state)
    
    print(f"\nChange Plan:")
    print(f"  Total Changes: {change_plan.summary.total_changes}")
    print(f"  All changes are CREATE operations: {change_plan.summary.creates}")
    
    for change in change_plan.changes:
        print(f"  - CREATE {change.resource_type}: {change.resource_id}")


if __name__ == "__main__":
    # Run the demos
    asyncio.run(demo_change_plan_generation())
    asyncio.run(demo_no_current_state())