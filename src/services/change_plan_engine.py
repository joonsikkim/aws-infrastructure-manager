"""
Change Plan Engine Implementation
"""
import uuid
from datetime import datetime
from typing import List, Dict, Set, Optional, Any, Tuple
from collections import defaultdict, deque
import re

from aws_lambda_powertools import Logger

from .interfaces import ChangePlanEngine, StateManagementService
from ..models.data_models import (
    ChangePlan, Change, ChangeAction, RiskLevel, ChangeSummary, ChangePlanStatus,
    InfrastructureState, Resource, ResourceConfig, DependencyGraph,
    CostEstimate, ValidationResult
)
from ..models.exceptions import InfrastructureException, ErrorCodes

logger = Logger(service="ChangePlanEngine")


class DefaultChangePlanEngine(ChangePlanEngine):
    """Default implementation of change plan engine"""
    
    def __init__(self, state_service: StateManagementService):
        """Initialize change plan engine
        
        Args:
            state_service: State management service for retrieving current state
        """
        self.state_service = state_service
        
        # Resource dependency rules - defines which resources depend on others
        self.dependency_rules = {
            'EC2::Instance': ['VPC::Subnet', 'EC2::SecurityGroup', 'EC2::KeyPair'],
            'RDS::DBInstance': ['VPC::Subnet', 'RDS::DBSubnetGroup', 'EC2::SecurityGroup'],
            'Lambda::Function': ['IAM::Role', 'VPC::Subnet'],
            'ECS::Service': ['ECS::Cluster', 'ECS::TaskDefinition', 'VPC::Subnet'],
            'ALB::LoadBalancer': ['VPC::Subnet', 'EC2::SecurityGroup'],
            'ALB::TargetGroup': ['VPC::VPC'],
            'RDS::DBSubnetGroup': ['VPC::Subnet'],
            'VPC::Subnet': ['VPC::VPC'],
            'VPC::InternetGateway': ['VPC::VPC'],
            'VPC::RouteTable': ['VPC::VPC'],
            'VPC::Route': ['VPC::RouteTable', 'VPC::InternetGateway'],
            'IAM::InstanceProfile': ['IAM::Role'],
            'S3::BucketPolicy': ['S3::Bucket'],
            'CloudWatch::Alarm': ['Lambda::Function', 'EC2::Instance', 'RDS::DBInstance']
        }
        
        # High-risk resource types that require careful handling
        self.high_risk_types = {
            'RDS::DBInstance',
            'EC2::Instance', 
            'Lambda::Function',
            'ECS::Service',
            'S3::Bucket',
            'IAM::Role',
            'VPC::VPC'
        }
        
        # Properties that are high-risk to change
        self.high_risk_properties = {
            'instanceType', 'dbInstanceClass', 'engine', 'engineVersion',
            'allocatedStorage', 'multiAZ', 'publiclyAccessible',
            'vpcSecurityGroupIds', 'subnetIds', 'availabilityZone'
        }
        
        # Cost estimation data (simplified - in real implementation would use AWS Pricing API)
        self.cost_estimates = {
            'EC2::Instance': {
                't3.micro': 8.76, 't3.small': 17.52, 't3.medium': 35.04,
                't3.large': 70.08, 't3.xlarge': 140.16
            },
            'RDS::DBInstance': {
                'db.t3.micro': 17.52, 'db.t3.small': 35.04, 'db.t3.medium': 70.08,
                'db.t3.large': 140.16, 'db.t3.xlarge': 280.32
            },
            'Lambda::Function': 0.20,  # per 1M requests
            'S3::Bucket': 0.023,  # per GB
            'ALB::LoadBalancer': 22.27  # per month
        }
    
    async def generate_plan(self, project_id: str, desired_state: InfrastructureState) -> ChangePlan:
        """Generate a change plan for desired state
        
        Args:
            project_id: Project identifier
            desired_state: Desired infrastructure state
            
        Returns:
            Generated change plan
        """
        try:
            logger.info(f"Generating change plan for project {project_id}")
            
            # Get current state
            current_state = await self.state_service.get_current_state(project_id)
            
            # Generate changes by comparing states
            if current_state is None:
                # No current state - all resources need to be created
                changes = self._generate_create_all_changes(desired_state)
            else:
                # Compare current and desired states
                changes = self._compare_states(current_state, desired_state)
            
            # Analyze dependencies and sort changes
            dependency_graph = await self.analyze_dependencies(changes)
            sorted_changes = self._sort_changes_by_dependencies(changes, dependency_graph)
            
            # Assess risk levels for each change
            for change in sorted_changes:
                change.risk_level = self._assess_change_risk(change)
            
            # Create summary
            summary = ChangeSummary(
                total_changes=len(sorted_changes),
                creates=len([c for c in sorted_changes if c.action == ChangeAction.CREATE]),
                updates=len([c for c in sorted_changes if c.action == ChangeAction.UPDATE]),
                deletes=len([c for c in sorted_changes if c.action == ChangeAction.DELETE])
            )
            
            # Generate change plan
            plan = ChangePlan(
                id=str(uuid.uuid4()),
                project_id=project_id,
                summary=summary,
                changes=sorted_changes,
                created_at=datetime.now(),
                status=ChangePlanStatus.PENDING
            )
            
            logger.info(f"Generated change plan {plan.id} with {len(sorted_changes)} changes")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate change plan: {e}")
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Failed to generate change plan: {e}",
                {"project_id": project_id}
            )
    
    async def analyze_dependencies(self, changes: List[Change]) -> DependencyGraph:
        """Analyze dependencies between changes
        
        Args:
            changes: List of changes to analyze
            
        Returns:
            Dependency graph showing relationships
        """
        try:
            nodes = []
            edges = []
            
            # Create resource ID to change mapping
            change_map = {change.resource_id: change for change in changes}
            
            # Build nodes list
            for change in changes:
                nodes.append(change.resource_id)
            
            # Analyze dependencies based on resource types and configurations
            for change in changes:
                # Only find dependencies if not already set (for testing flexibility)
                if not change.dependencies:
                    dependencies = self._find_resource_dependencies(change, changes)
                    change.dependencies = dependencies
                else:
                    dependencies = change.dependencies
                
                # Add edges to dependency graph
                for dep_id in dependencies:
                    if dep_id in change_map:
                        edges.append((dep_id, change.resource_id))
            
            # Detect circular dependencies
            circular_deps = self._detect_circular_dependencies(nodes, edges)
            if circular_deps:
                logger.warning(f"Circular dependencies detected: {circular_deps}")
            
            graph = DependencyGraph(nodes=nodes, edges=edges)
            logger.info(f"Analyzed dependencies: {len(nodes)} nodes, {len(edges)} edges")
            
            return graph
            
        except Exception as e:
            logger.error(f"Failed to analyze dependencies: {e}")
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Failed to analyze dependencies: {e}"
            )
    
    async def estimate_cost(self, change_plan: ChangePlan) -> CostEstimate:
        """Estimate cost of executing a change plan
        
        Args:
            change_plan: Change plan to estimate cost for
            
        Returns:
            Cost estimate for the changes
        """
        try:
            total_cost = 0.0
            cost_breakdown = {}
            
            for change in change_plan.changes:
                resource_cost = self._estimate_resource_cost(change)
                total_cost += resource_cost
                
                if resource_cost > 0:
                    cost_breakdown[f"{change.resource_type}:{change.resource_id}"] = resource_cost
            
            estimate = CostEstimate(
                total_monthly_cost=total_cost,
                cost_breakdown=cost_breakdown,
                currency="USD"
            )
            
            logger.info(f"Estimated monthly cost for plan {change_plan.id}: ${total_cost:.2f}")
            return estimate
            
        except Exception as e:
            logger.error(f"Failed to estimate cost: {e}")
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Failed to estimate cost: {e}",
                {"plan_id": change_plan.id}
            )
    
    async def validate_plan(self, change_plan: ChangePlan) -> ValidationResult:
        """Validate a change plan for safety and correctness
        
        Args:
            change_plan: Change plan to validate
            
        Returns:
            Validation result with errors and warnings
        """
        try:
            errors = []
            warnings = []
            
            # Validate basic plan structure
            if not change_plan.changes:
                warnings.append("Change plan contains no changes")
            
            # Validate individual changes
            for change in change_plan.changes:
                change_errors, change_warnings = self._validate_change(change)
                errors.extend(change_errors)
                warnings.extend(change_warnings)
            
            # Validate dependencies
            dependency_errors = self._validate_dependencies(change_plan.changes)
            errors.extend(dependency_errors)
            
            # Check for high-risk operations
            high_risk_changes = [c for c in change_plan.changes if c.risk_level == RiskLevel.HIGH]
            if high_risk_changes:
                warnings.append(f"Plan contains {len(high_risk_changes)} high-risk changes")
            
            # Check for potential data loss
            delete_changes = [c for c in change_plan.changes if c.action == ChangeAction.DELETE]
            if delete_changes:
                data_loss_resources = [c for c in delete_changes if c.resource_type in ['RDS::DBInstance', 'S3::Bucket']]
                if data_loss_resources:
                    warnings.append(f"Plan may cause data loss: {len(data_loss_resources)} resources with data will be deleted")
            
            result = ValidationResult(
                is_valid=len(errors) == 0,
                errors=errors,
                warnings=warnings
            )
            
            logger.info(f"Validated plan {change_plan.id}: {len(errors)} errors, {len(warnings)} warnings")
            return result
            
        except Exception as e:
            logger.error(f"Failed to validate plan: {e}")
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Failed to validate plan: {e}",
                {"plan_id": change_plan.id}
            )
    
    def _generate_create_all_changes(self, desired_state: InfrastructureState) -> List[Change]:
        """Generate changes to create all resources from scratch
        
        Args:
            desired_state: Desired infrastructure state
            
        Returns:
            List of CREATE changes for all resources
        """
        changes = []
        
        for resource in desired_state.resources:
            change = Change(
                action=ChangeAction.CREATE,
                resource_type=resource.type,
                resource_id=resource.id,
                desired_config=self._resource_to_config(resource),
                risk_level=RiskLevel.LOW  # Will be reassessed later
            )
            changes.append(change)
        
        return changes
    
    def _compare_states(self, current_state: InfrastructureState, desired_state: InfrastructureState) -> List[Change]:
        """Compare current and desired states to generate changes
        
        Args:
            current_state: Current infrastructure state
            desired_state: Desired infrastructure state
            
        Returns:
            List of changes needed to reach desired state
        """
        changes = []
        
        # Create resource maps for easier comparison
        current_resources = {r.id: r for r in current_state.resources}
        desired_resources = {r.id: r for r in desired_state.resources}
        
        # Find resources to create (in desired but not in current)
        for resource_id, resource in desired_resources.items():
            if resource_id not in current_resources:
                changes.append(Change(
                    action=ChangeAction.CREATE,
                    resource_type=resource.type,
                    resource_id=resource_id,
                    desired_config=self._resource_to_config(resource),
                    risk_level=RiskLevel.LOW
                ))
        
        # Find resources to update or delete
        for resource_id, current_resource in current_resources.items():
            if resource_id in desired_resources:
                desired_resource = desired_resources[resource_id]
                
                # Check if resource needs updating
                if self._resources_differ(current_resource, desired_resource):
                    changes.append(Change(
                        action=ChangeAction.UPDATE,
                        resource_type=current_resource.type,
                        resource_id=resource_id,
                        current_config=self._resource_to_config(current_resource),
                        desired_config=self._resource_to_config(desired_resource),
                        risk_level=RiskLevel.MEDIUM
                    ))
            else:
                # Resource exists in current but not in desired - delete it
                changes.append(Change(
                    action=ChangeAction.DELETE,
                    resource_type=current_resource.type,
                    resource_id=resource_id,
                    current_config=self._resource_to_config(current_resource),
                    risk_level=RiskLevel.HIGH
                ))
        
        return changes
    
    def _resource_to_config(self, resource: Resource) -> ResourceConfig:
        """Convert Resource to ResourceConfig
        
        Args:
            resource: Resource object
            
        Returns:
            ResourceConfig object
        """
        return ResourceConfig(
            type=resource.type,
            name=resource.name,
            properties=resource.properties,
            tags=resource.tags
        )
    
    def _resources_differ(self, current: Resource, desired: Resource) -> bool:
        """Check if two resources differ in meaningful ways
        
        Args:
            current: Current resource
            desired: Desired resource
            
        Returns:
            True if resources differ and update is needed
        """
        # Compare properties (excluding timestamps and status)
        if current.properties != desired.properties:
            return True
        
        # Compare tags
        if current.tags != desired.tags:
            return True
        
        # Compare name
        if current.name != desired.name:
            return True
        
        return False
    
    def _find_resource_dependencies(self, change: Change, all_changes: List[Change]) -> List[str]:
        """Find dependencies for a specific resource change
        
        Args:
            change: Change to find dependencies for
            all_changes: All changes in the plan
            
        Returns:
            List of resource IDs that this change depends on
        """
        dependencies = []
        
        # Get dependency rules for this resource type
        resource_type = change.resource_type
        if resource_type in self.dependency_rules:
            required_types = self.dependency_rules[resource_type]
            
            # Look for resources of required types in the change plan
            for other_change in all_changes:
                if (other_change.resource_type in required_types and 
                    other_change.resource_id != change.resource_id):
                    dependencies.append(other_change.resource_id)
        
        # Check for explicit dependencies in resource configuration
        if change.desired_config and change.desired_config.properties:
            dependencies.extend(self._extract_property_dependencies(change.desired_config.properties, all_changes))
        
        return dependencies
    
    def _extract_property_dependencies(self, properties: Dict[str, Any], all_changes: List[Change]) -> List[str]:
        """Extract dependencies from resource properties
        
        Args:
            properties: Resource properties to analyze
            all_changes: All changes in the plan
            
        Returns:
            List of resource IDs referenced in properties
        """
        dependencies = []
        change_ids = {change.resource_id for change in all_changes}
        
        # Common property patterns that reference other resources
        dependency_patterns = [
            'subnetId', 'subnetIds', 'vpcId', 'securityGroupId', 'securityGroupIds',
            'roleArn', 'instanceProfileArn', 'targetGroupArn', 'loadBalancerArn',
            'dbSubnetGroupName', 'keyName'
        ]
        
        for key, value in properties.items():
            if key in dependency_patterns:
                if isinstance(value, str):
                    # Extract resource ID from ARN or direct reference
                    resource_id = self._extract_resource_id_from_value(value)
                    if resource_id and resource_id in change_ids:
                        dependencies.append(resource_id)
                elif isinstance(value, list):
                    # Handle lists of references
                    for item in value:
                        if isinstance(item, str):
                            resource_id = self._extract_resource_id_from_value(item)
                            if resource_id and resource_id in change_ids:
                                dependencies.append(resource_id)
        
        return dependencies
    
    def _extract_resource_id_from_value(self, value: str) -> Optional[str]:
        """Extract resource ID from property value (ARN, reference, etc.)
        
        Args:
            value: Property value to extract from
            
        Returns:
            Extracted resource ID or None
        """
        # Handle ARNs
        if value.startswith('arn:aws:'):
            parts = value.split(':')
            if len(parts) >= 6:
                return parts[-1].split('/')[-1]
        
        # Handle direct resource IDs (common patterns)
        resource_id_patterns = [
            r'^(i-[a-f0-9]+)$',  # EC2 instances
            r'^(subnet-[a-f0-9]+)$',  # Subnets
            r'^(vpc-[a-f0-9]+)$',  # VPCs
            r'^(sg-[a-f0-9]+)$',  # Security groups
            r'^(igw-[a-f0-9]+)$',  # Internet gateways
            r'^(rtb-[a-f0-9]+)$',  # Route tables
        ]
        
        for pattern in resource_id_patterns:
            match = re.match(pattern, value)
            if match:
                return match.group(1)
        
        return None
    
    def _sort_changes_by_dependencies(self, changes: List[Change], dependency_graph: DependencyGraph) -> List[Change]:
        """Sort changes based on their dependencies using topological sort
        
        Args:
            changes: List of changes to sort
            dependency_graph: Dependency graph
            
        Returns:
            Sorted list of changes
        """
        # Create change lookup
        change_map = {change.resource_id: change for change in changes}
        
        # Perform topological sort
        sorted_ids = self._topological_sort(dependency_graph.nodes, dependency_graph.edges)
        
        # Build sorted changes list
        sorted_changes = []
        added_ids = set()
        
        # Add changes in dependency order
        for resource_id in sorted_ids:
            if resource_id in change_map and resource_id not in added_ids:
                sorted_changes.append(change_map[resource_id])
                added_ids.add(resource_id)
        
        # Add any remaining changes (shouldn't happen with correct dependency analysis)
        for change in changes:
            if change.resource_id not in added_ids:
                sorted_changes.append(change)
        
        return sorted_changes
    
    def _topological_sort(self, nodes: List[str], edges: List[Tuple[str, str]]) -> List[str]:
        """Perform topological sort on dependency graph
        
        Args:
            nodes: List of node IDs
            edges: List of (from, to) edges
            
        Returns:
            Topologically sorted list of node IDs
        """
        # Build adjacency list and in-degree count
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        
        # Initialize in-degree for all nodes
        for node in nodes:
            in_degree[node] = 0
        
        # Build graph and calculate in-degrees
        for from_node, to_node in edges:
            graph[from_node].append(to_node)
            in_degree[to_node] += 1
        
        # Find nodes with no incoming edges
        queue = deque([node for node in nodes if in_degree[node] == 0])
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            # Remove edges from this node
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        return result
    
    def _detect_circular_dependencies(self, nodes: List[str], edges: List[Tuple[str, str]]) -> List[List[str]]:
        """Detect circular dependencies in the graph
        
        Args:
            nodes: List of node IDs
            edges: List of (from, to) edges
            
        Returns:
            List of circular dependency chains
        """
        # Build adjacency list
        graph = defaultdict(list)
        for from_node, to_node in edges:
            graph[from_node].append(to_node)
        
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph[node]:
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
            
            rec_stack.remove(node)
        
        for node in nodes:
            if node not in visited:
                dfs(node, [])
        
        return cycles
    
    def _assess_change_risk(self, change: Change) -> RiskLevel:
        """Assess the risk level of a change
        
        Args:
            change: Change to assess
            
        Returns:
            Risk level for the change
        """
        # Deletions are always high risk
        if change.action == ChangeAction.DELETE:
            return RiskLevel.HIGH
        
        # Check if resource type is high-risk
        if change.resource_type in self.high_risk_types:
            if change.action == ChangeAction.UPDATE:
                # Check if high-risk properties are changing
                if self._has_high_risk_property_changes(change):
                    return RiskLevel.HIGH
                else:
                    return RiskLevel.MEDIUM
            else:  # CREATE
                return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    def _has_high_risk_property_changes(self, change: Change) -> bool:
        """Check if a change involves high-risk property modifications
        
        Args:
            change: Change to check
            
        Returns:
            True if high-risk properties are being changed
        """
        if (change.action != ChangeAction.UPDATE or 
            not change.current_config or not change.desired_config):
            return False
        
        current_props = change.current_config.properties
        desired_props = change.desired_config.properties
        
        for prop in self.high_risk_properties:
            if (prop in current_props and prop in desired_props and 
                current_props[prop] != desired_props[prop]):
                return True
        
        return False
    
    def _estimate_resource_cost(self, change: Change) -> float:
        """Estimate monthly cost for a resource change
        
        Args:
            change: Change to estimate cost for
            
        Returns:
            Estimated monthly cost in USD
        """
        if change.action == ChangeAction.DELETE:
            return 0.0  # Deletions save money
        
        resource_type = change.resource_type
        config = change.desired_config
        
        if not config or resource_type not in self.cost_estimates:
            return 0.0
        
        cost_data = self.cost_estimates[resource_type]
        
        if isinstance(cost_data, dict):
            # Cost varies by instance type/class
            instance_type = config.properties.get('instanceType') or config.properties.get('dbInstanceClass')
            if instance_type and instance_type in cost_data:
                return cost_data[instance_type]
        else:
            # Fixed cost
            return cost_data
        
        return 0.0
    
    def _validate_change(self, change: Change) -> Tuple[List[str], List[str]]:
        """Validate a single change
        
        Args:
            change: Change to validate
            
        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []
        
        # Validate basic change structure
        if not change.resource_id:
            errors.append(f"Change missing resource ID")
        
        if not change.resource_type:
            errors.append(f"Change missing resource type")
        
        # Validate configurations based on action
        if change.action == ChangeAction.CREATE:
            if not change.desired_config:
                errors.append(f"CREATE change for {change.resource_id} missing desired configuration")
        elif change.action == ChangeAction.UPDATE:
            if not change.current_config or not change.desired_config:
                errors.append(f"UPDATE change for {change.resource_id} missing current or desired configuration")
        elif change.action == ChangeAction.DELETE:
            if not change.current_config:
                errors.append(f"DELETE change for {change.resource_id} missing current configuration")
        
        # Validate resource-specific requirements
        if change.desired_config:
            resource_errors, resource_warnings = self._validate_resource_config(change.desired_config)
            errors.extend([f"{change.resource_id}: {err}" for err in resource_errors])
            warnings.extend([f"{change.resource_id}: {warn}" for warn in resource_warnings])
        
        return errors, warnings
    
    def _validate_resource_config(self, config: ResourceConfig) -> Tuple[List[str], List[str]]:
        """Validate resource configuration
        
        Args:
            config: Resource configuration to validate
            
        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []
        
        # Basic validation
        if not config.name:
            errors.append("Resource name is required")
        
        if not config.properties:
            errors.append("Resource properties are required")
        
        # Resource-type specific validation
        if config.type == 'EC2::Instance':
            if 'instanceType' not in config.properties:
                errors.append("EC2 instance requires instanceType")
            if 'imageId' not in config.properties:
                errors.append("EC2 instance requires imageId")
        elif config.type == 'RDS::DBInstance':
            if 'dbInstanceClass' not in config.properties:
                errors.append("RDS instance requires dbInstanceClass")
            if 'engine' not in config.properties:
                errors.append("RDS instance requires engine")
        
        return errors, warnings
    
    def _validate_dependencies(self, changes: List[Change]) -> List[str]:
        """Validate dependencies across all changes
        
        Args:
            changes: List of changes to validate
            
        Returns:
            List of dependency validation errors
        """
        errors = []
        change_ids = {change.resource_id for change in changes}
        
        for change in changes:
            for dep_id in change.dependencies:
                if dep_id not in change_ids:
                    errors.append(f"Change {change.resource_id} depends on {dep_id} which is not in the plan")
        
        return errors