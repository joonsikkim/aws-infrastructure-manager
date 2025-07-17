"""
Unit tests for Change Plan Engine
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock
from typing import List, Optional

from src.services.change_plan_engine import DefaultChangePlanEngine
from src.services.interfaces import StateManagementService
from src.models.data_models import (
    InfrastructureState, Resource, ResourceConfig, StateMetadata,
    Change, ChangeAction, RiskLevel, ChangePlan, ChangePlanStatus,
    DependencyGraph, CostEstimate, ValidationResult
)
from src.models.enums import ResourceStatus
from src.models.exceptions import InfrastructureException, ErrorCodes


class MockStateManagementService(StateManagementService):
    """Mock state management service for testing"""
    
    def __init__(self):
        self.current_state: Optional[InfrastructureState] = None
    
    async def get_current_state(self, project_id: str) -> Optional[InfrastructureState]:
        return self.current_state
    
    async def save_state(self, project_id: str, state: InfrastructureState) -> None:
        pass
    
    async def get_state_history(self, project_id: str, limit: Optional[int] = None) -> List:
        return []
    
    def compare_states(self, current_state: InfrastructureState, desired_state: InfrastructureState) -> ChangePlan:
        pass

    async def get_change_plan(self, project_id: str, plan_id: str) -> Optional[ChangePlan]:
        pass

    async def list_change_plans(self, project_id: str) -> List[ChangePlan]:
        return []

    async def save_change_plan(self, project_id: str, plan: ChangePlan) -> None:
        pass


@pytest.fixture
def mock_state_service():
    """Create mock state management service"""
    return MockStateManagementService()


@pytest.fixture
def change_plan_engine(mock_state_service):
    """Create change plan engine with mock dependencies"""
    return DefaultChangePlanEngine(mock_state_service)


@pytest.fixture
def sample_resource():
    """Create sample resource for testing"""
    return Resource(
        id="i-1234567890abcdef0",
        project_id="test-project",
        type="EC2::Instance",
        name="test-instance",
        region="us-east-1",
        properties={
            "instanceType": "t3.micro",
            "imageId": "ami-12345678",
            "subnetId": "subnet-12345678"
        },
        tags={"Environment": "test"},
        status=ResourceStatus.ACTIVE,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    )


@pytest.fixture
def sample_infrastructure_state(sample_resource):
    """Create sample infrastructure state"""
    return InfrastructureState(
        project_id="test-project",
        version="1.0.0",
        timestamp=datetime.now(),
        resources=[sample_resource],
        metadata=StateMetadata(
            last_modified_by="test@example.com",
            change_description="Test state"
        )
    )


class TestChangePlanEngine:
    """Test cases for ChangePlanEngine"""
    
    @pytest.mark.asyncio
    async def test_generate_plan_no_current_state(self, change_plan_engine, mock_state_service, sample_infrastructure_state):
        """Test generating plan when no current state exists"""
        # Setup - no current state
        mock_state_service.current_state = None
        
        # Execute
        plan = await change_plan_engine.generate_plan("test-project", sample_infrastructure_state)
        
        # Verify
        assert plan.project_id == "test-project"
        assert plan.status == ChangePlanStatus.PENDING
        assert plan.summary.total_changes == 1
        assert plan.summary.creates == 1
        assert plan.summary.updates == 0
        assert plan.summary.deletes == 0
        assert len(plan.changes) == 1
        assert plan.changes[0].action == ChangeAction.CREATE
        assert plan.changes[0].resource_type == "EC2::Instance"
        assert plan.changes[0].resource_id == "i-1234567890abcdef0"
    
    @pytest.mark.asyncio
    async def test_generate_plan_with_updates(self, change_plan_engine, mock_state_service, sample_resource):
        """Test generating plan with resource updates"""
        # Setup current state
        current_state = InfrastructureState(
            project_id="test-project",
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[sample_resource],
            metadata=StateMetadata(
                last_modified_by="test@example.com",
                change_description="Current state"
            )
        )
        mock_state_service.current_state = current_state
        
        # Setup desired state with modified resource
        modified_resource = Resource(
            id=sample_resource.id,
            project_id=sample_resource.project_id,
            type=sample_resource.type,
            name=sample_resource.name,
            region=sample_resource.region,
            properties={
                **sample_resource.properties,
                "instanceType": "t3.small"  # Changed instance type
            },
            tags=sample_resource.tags,
            status=sample_resource.status,
            created_at=sample_resource.created_at,
            updated_at=datetime.now(),
            arn=sample_resource.arn
        )
        
        desired_state = InfrastructureState(
            project_id="test-project",
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[modified_resource],
            metadata=StateMetadata(
                last_modified_by="test@example.com",
                change_description="Updated state"
            )
        )
        
        # Execute
        plan = await change_plan_engine.generate_plan("test-project", desired_state)
        
        # Verify
        assert plan.summary.total_changes == 1
        assert plan.summary.creates == 0
        assert plan.summary.updates == 1
        assert plan.summary.deletes == 0
        assert len(plan.changes) == 1
        assert plan.changes[0].action == ChangeAction.UPDATE
        assert plan.changes[0].resource_type == "EC2::Instance"
        assert plan.changes[0].current_config.properties["instanceType"] == "t3.micro"
        assert plan.changes[0].desired_config.properties["instanceType"] == "t3.small"
    
    @pytest.mark.asyncio
    async def test_generate_plan_with_deletions(self, change_plan_engine, mock_state_service, sample_resource):
        """Test generating plan with resource deletions"""
        # Setup current state with resource
        current_state = InfrastructureState(
            project_id="test-project",
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[sample_resource],
            metadata=StateMetadata(
                last_modified_by="test@example.com",
                change_description="Current state"
            )
        )
        mock_state_service.current_state = current_state
        
        # Setup desired state with no resources (deletion)
        desired_state = InfrastructureState(
            project_id="test-project",
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[],  # No resources - should delete existing
            metadata=StateMetadata(
                last_modified_by="test@example.com",
                change_description="Empty state"
            )
        )
        
        # Execute
        plan = await change_plan_engine.generate_plan("test-project", desired_state)
        
        # Verify
        assert plan.summary.total_changes == 1
        assert plan.summary.creates == 0
        assert plan.summary.updates == 0
        assert plan.summary.deletes == 1
        assert len(plan.changes) == 1
        assert plan.changes[0].action == ChangeAction.DELETE
        assert plan.changes[0].resource_type == "EC2::Instance"
        assert plan.changes[0].risk_level == RiskLevel.HIGH  # Deletions are high risk
    
    @pytest.mark.asyncio
    async def test_analyze_dependencies_simple(self, change_plan_engine):
        """Test dependency analysis with simple dependencies"""
        # Create changes with dependencies
        vpc_change = Change(
            action=ChangeAction.CREATE,
            resource_type="VPC::VPC",
            resource_id="vpc-12345678"
        )
        
        subnet_change = Change(
            action=ChangeAction.CREATE,
            resource_type="VPC::Subnet",
            resource_id="subnet-12345678"
        )
        
        instance_change = Change(
            action=ChangeAction.CREATE,
            resource_type="EC2::Instance",
            resource_id="i-1234567890abcdef0"
        )
        
        changes = [instance_change, subnet_change, vpc_change]  # Intentionally out of order
        
        # Execute
        dependency_graph = await change_plan_engine.analyze_dependencies(changes)
        
        # Verify
        assert len(dependency_graph.nodes) == 3
        assert len(dependency_graph.edges) > 0
        
        # Check that instance depends on subnet
        instance_deps = instance_change.dependencies
        assert "subnet-12345678" in instance_deps
    
    @pytest.mark.asyncio
    async def test_analyze_dependencies_circular(self, change_plan_engine):
        """Test detection of circular dependencies"""
        # Create changes that would create circular dependency
        change1 = Change(
            action=ChangeAction.CREATE,
            resource_type="TestType::A",
            resource_id="resource-a"
        )
        
        change2 = Change(
            action=ChangeAction.CREATE,
            resource_type="TestType::B",
            resource_id="resource-b"
        )
        
        # Manually set circular dependencies for testing
        change1.dependencies = ["resource-b"]
        change2.dependencies = ["resource-a"]
        
        changes = [change1, change2]
        
        # Execute
        dependency_graph = await change_plan_engine.analyze_dependencies(changes)
        
        # Verify graph is created despite circular dependency
        assert len(dependency_graph.nodes) == 2
        assert len(dependency_graph.edges) == 2
    
    @pytest.mark.asyncio
    async def test_estimate_cost(self, change_plan_engine):
        """Test cost estimation for change plan"""
        # Create change plan with known resource types
        ec2_change = Change(
            action=ChangeAction.CREATE,
            resource_type="EC2::Instance",
            resource_id="i-1234567890abcdef0",
            desired_config=ResourceConfig(
                type="EC2::Instance",
                name="test-instance",
                properties={"instanceType": "t3.micro"}
            )
        )
        
        rds_change = Change(
            action=ChangeAction.CREATE,
            resource_type="RDS::DBInstance",
            resource_id="db-1234567890abcdef0",
            desired_config=ResourceConfig(
                type="RDS::DBInstance",
                name="test-db",
                properties={"dbInstanceClass": "db.t3.micro"}
            )
        )
        
        plan = ChangePlan(
            id="test-plan",
            project_id="test-project",
            summary=Mock(),
            changes=[ec2_change, rds_change],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING
        )
        
        # Execute
        cost_estimate = await change_plan_engine.estimate_cost(plan)
        
        # Verify
        assert cost_estimate.total_monthly_cost > 0
        assert cost_estimate.currency == "USD"
        assert len(cost_estimate.cost_breakdown) == 2
        assert "EC2::Instance:i-1234567890abcdef0" in cost_estimate.cost_breakdown
        assert "RDS::DBInstance:db-1234567890abcdef0" in cost_estimate.cost_breakdown
    
    @pytest.mark.asyncio
    async def test_validate_plan_valid(self, change_plan_engine):
        """Test validation of a valid change plan"""
        # Create valid change
        change = Change(
            action=ChangeAction.CREATE,
            resource_type="EC2::Instance",
            resource_id="i-1234567890abcdef0",
            desired_config=ResourceConfig(
                type="EC2::Instance",
                name="test-instance",
                properties={
                    "instanceType": "t3.micro",
                    "imageId": "ami-12345678"
                }
            )
        )
        
        plan = ChangePlan(
            id="test-plan",
            project_id="test-project",
            summary=Mock(),
            changes=[change],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING
        )
        
        # Execute
        validation_result = await change_plan_engine.validate_plan(plan)
        
        # Verify
        assert validation_result.is_valid
        assert len(validation_result.errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_plan_invalid(self, change_plan_engine):
        """Test validation of an invalid change plan"""
        # Create invalid change (missing required properties)
        change = Change(
            action=ChangeAction.CREATE,
            resource_type="EC2::Instance",
            resource_id="i-1234567890abcdef0",
            desired_config=ResourceConfig(
                type="EC2::Instance",
                name="test-instance",
                properties={}  # Missing required properties
            )
        )
        
        plan = ChangePlan(
            id="test-plan",
            project_id="test-project",
            summary=Mock(),
            changes=[change],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING
        )
        
        # Execute
        validation_result = await change_plan_engine.validate_plan(plan)
        
        # Verify
        assert not validation_result.is_valid
        assert len(validation_result.errors) > 0
        assert any("instanceType" in error for error in validation_result.errors)
        assert any("imageId" in error for error in validation_result.errors)
    
    @pytest.mark.asyncio
    async def test_validate_plan_high_risk_warnings(self, change_plan_engine):
        """Test validation warnings for high-risk changes"""
        # Create high-risk change (deletion)
        change = Change(
            action=ChangeAction.DELETE,
            resource_type="RDS::DBInstance",
            resource_id="db-1234567890abcdef0",
            current_config=ResourceConfig(
                type="RDS::DBInstance",
                name="test-db",
                properties={"dbInstanceClass": "db.t3.micro"}
            ),
            risk_level=RiskLevel.HIGH
        )
        
        plan = ChangePlan(
            id="test-plan",
            project_id="test-project",
            summary=Mock(),
            changes=[change],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING
        )
        
        # Execute
        validation_result = await change_plan_engine.validate_plan(plan)
        
        # Verify
        assert validation_result.is_valid  # Should be valid but with warnings
        assert len(validation_result.warnings) > 0
        assert any("high-risk" in warning.lower() for warning in validation_result.warnings)
        assert any("data loss" in warning.lower() for warning in validation_result.warnings)
    
    def test_resource_to_config(self, change_plan_engine, sample_resource):
        """Test conversion of Resource to ResourceConfig"""
        config = change_plan_engine._resource_to_config(sample_resource)
        
        assert config.type == sample_resource.type
        assert config.name == sample_resource.name
        assert config.properties == sample_resource.properties
        assert config.tags == sample_resource.tags
    
    def test_resources_differ_same(self, change_plan_engine, sample_resource):
        """Test resource comparison with identical resources"""
        result = change_plan_engine._resources_differ(sample_resource, sample_resource)
        assert not result
    
    def test_resources_differ_different_properties(self, change_plan_engine, sample_resource):
        """Test resource comparison with different properties"""
        modified_resource = Resource(
            id=sample_resource.id,
            project_id=sample_resource.project_id,
            type=sample_resource.type,
            name=sample_resource.name,
            region=sample_resource.region,
            properties={
                **sample_resource.properties,
                "instanceType": "t3.small"  # Different
            },
            tags=sample_resource.tags,
            status=sample_resource.status,
            created_at=sample_resource.created_at,
            updated_at=sample_resource.updated_at,
            arn=sample_resource.arn
        )
        
        result = change_plan_engine._resources_differ(sample_resource, modified_resource)
        assert result
    
    def test_resources_differ_different_tags(self, change_plan_engine, sample_resource):
        """Test resource comparison with different tags"""
        modified_resource = Resource(
            id=sample_resource.id,
            project_id=sample_resource.project_id,
            type=sample_resource.type,
            name=sample_resource.name,
            region=sample_resource.region,
            properties=sample_resource.properties,
            tags={"Environment": "production"},  # Different tags
            status=sample_resource.status,
            created_at=sample_resource.created_at,
            updated_at=sample_resource.updated_at,
            arn=sample_resource.arn
        )
        
        result = change_plan_engine._resources_differ(sample_resource, modified_resource)
        assert result
    
    def test_assess_change_risk_create_low_risk(self, change_plan_engine):
        """Test risk assessment for low-risk CREATE operation"""
        change = Change(
            action=ChangeAction.CREATE,
            resource_type="CloudWatch::Alarm",  # Not in high-risk types for CREATE
            resource_id="test-alarm"
        )
        
        risk = change_plan_engine._assess_change_risk(change)
        assert risk == RiskLevel.LOW
    
    def test_assess_change_risk_create_medium_risk(self, change_plan_engine):
        """Test risk assessment for medium-risk CREATE operation"""
        change = Change(
            action=ChangeAction.CREATE,
            resource_type="RDS::DBInstance",  # High-risk type
            resource_id="test-db"
        )
        
        risk = change_plan_engine._assess_change_risk(change)
        assert risk == RiskLevel.MEDIUM
    
    def test_assess_change_risk_delete_high_risk(self, change_plan_engine):
        """Test risk assessment for DELETE operation (always high risk)"""
        change = Change(
            action=ChangeAction.DELETE,
            resource_type="S3::Bucket",
            resource_id="test-bucket"
        )
        
        risk = change_plan_engine._assess_change_risk(change)
        assert risk == RiskLevel.HIGH
    
    def test_assess_change_risk_update_high_risk_properties(self, change_plan_engine):
        """Test risk assessment for UPDATE with high-risk property changes"""
        change = Change(
            action=ChangeAction.UPDATE,
            resource_type="EC2::Instance",
            resource_id="i-1234567890abcdef0",
            current_config=ResourceConfig(
                type="EC2::Instance",
                name="test",
                properties={"instanceType": "t3.micro"}
            ),
            desired_config=ResourceConfig(
                type="EC2::Instance",
                name="test",
                properties={"instanceType": "t3.large"}  # High-risk change
            )
        )
        
        risk = change_plan_engine._assess_change_risk(change)
        assert risk == RiskLevel.HIGH
    
    def test_topological_sort_simple(self, change_plan_engine):
        """Test topological sort with simple dependency chain"""
        nodes = ["A", "B", "C"]
        edges = [("A", "B"), ("B", "C")]  # A -> B -> C
        
        result = change_plan_engine._topological_sort(nodes, edges)
        
        # A should come before B, B should come before C
        assert result.index("A") < result.index("B")
        assert result.index("B") < result.index("C")
    
    def test_topological_sort_no_dependencies(self, change_plan_engine):
        """Test topological sort with no dependencies"""
        nodes = ["A", "B", "C"]
        edges = []
        
        result = change_plan_engine._topological_sort(nodes, edges)
        
        # All nodes should be present
        assert set(result) == set(nodes)
        assert len(result) == 3
    
    def test_detect_circular_dependencies_none(self, change_plan_engine):
        """Test circular dependency detection with no cycles"""
        nodes = ["A", "B", "C"]
        edges = [("A", "B"), ("B", "C")]
        
        cycles = change_plan_engine._detect_circular_dependencies(nodes, edges)
        assert len(cycles) == 0
    
    def test_detect_circular_dependencies_simple_cycle(self, change_plan_engine):
        """Test circular dependency detection with simple cycle"""
        nodes = ["A", "B"]
        edges = [("A", "B"), ("B", "A")]  # A -> B -> A
        
        cycles = change_plan_engine._detect_circular_dependencies(nodes, edges)
        assert len(cycles) > 0
    
    def test_extract_resource_id_from_arn(self, change_plan_engine):
        """Test resource ID extraction from ARN"""
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        result = change_plan_engine._extract_resource_id_from_value(arn)
        assert result == "i-1234567890abcdef0"
    
    def test_extract_resource_id_from_direct_id(self, change_plan_engine):
        """Test resource ID extraction from direct resource ID"""
        resource_id = "subnet-12345678"
        result = change_plan_engine._extract_resource_id_from_value(resource_id)
        assert result == "subnet-12345678"
    
    def test_extract_resource_id_invalid(self, change_plan_engine):
        """Test resource ID extraction from invalid value"""
        invalid_value = "not-a-resource-id"
        result = change_plan_engine._extract_resource_id_from_value(invalid_value)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_generate_plan_error_handling(self, change_plan_engine, mock_state_service):
        """Test error handling in plan generation"""
        # Setup mock to raise exception
        mock_state_service.get_current_state = AsyncMock(side_effect=Exception("Test error"))
        
        desired_state = InfrastructureState(
            project_id="test-project",
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[],
            metadata=StateMetadata(
                last_modified_by="test@example.com",
                change_description="Test"
            )
        )
        
        # Execute and verify exception
        with pytest.raises(InfrastructureException) as exc_info:
            await change_plan_engine.generate_plan("test-project", desired_state)
        
        assert exc_info.value.code == ErrorCodes.VALIDATION_FAILED
        assert "Failed to generate change plan" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__])