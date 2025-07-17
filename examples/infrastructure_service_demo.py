"""
Demo script for Infrastructure Service functionality
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from src.services.infrastructure_service import AWSInfrastructureService, create_infrastructure_service
from src.services.aws_mcp_client import create_aws_mcp_client
from src.models.data_models import (
    ResourceConfig, ResourceFilter, ResourceUpdate,
    InfrastructureState, StateMetadata
)
from src.models.enums import ResourceStatus
# from config.settings import get_settings  # Commented out for demo


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockStateService:
    """Mock state service for demo purposes"""
    
    def __init__(self):
        self.states: Dict[str, InfrastructureState] = {}
    
    async def get_current_state(self, project_id: str):
        return self.states.get(project_id)
    
    async def save_state(self, project_id: str, state: InfrastructureState):
        self.states[project_id] = state
        logger.info(f"Saved state for project {project_id} with {len(state.resources)} resources")
    
    async def get_state_history(self, project_id: str, limit=None):
        return []
    
    def compare_states(self, current_state, desired_state):
        return None


class MockChangePlanEngine:
    """Mock change plan engine for demo purposes"""
    
    async def generate_plan(self, project_id: str, desired_state: InfrastructureState):
        from src.models.data_models import ChangePlan, ChangeSummary
        from src.models.enums import ChangePlanStatus
        
        return ChangePlan(
            id=f"plan-{datetime.now().timestamp()}",
            project_id=project_id,
            summary=ChangeSummary(
                total_changes=len(desired_state.resources),
                creates=len(desired_state.resources),
                updates=0,
                deletes=0
            ),
            changes=[],
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING
        )
    
    async def analyze_dependencies(self, changes):
        return None
    
    async def estimate_cost(self, change_plan):
        return None
    
    async def validate_plan(self, change_plan):
        return None


async def demo_infrastructure_service():
    """Demonstrate infrastructure service functionality"""
    
    logger.info("=== Infrastructure Service Demo ===")
    
    # Create mock dependencies (in real usage, these would be actual implementations)
    mock_state_service = MockStateService()
    mock_change_plan_engine = MockChangePlanEngine()
    
    # Create AWS MCP client (this would connect to actual MCP server in production)
    aws_mcp_client = create_aws_mcp_client(
        server_url="http://localhost:8000",  # Mock URL for demo
        timeout=30,
        max_retries=3
    )
    
    # Create infrastructure service
    infrastructure_service = create_infrastructure_service(
        aws_mcp_client=aws_mcp_client,
        state_service=mock_state_service,
        change_plan_engine=mock_change_plan_engine
    )
    
    project_id = "demo-project"
    
    try:
        # Demo 1: Create a resource
        logger.info("\n--- Demo 1: Creating a resource ---")
        
        resource_config = ResourceConfig(
            type="EC2::Instance",
            name="demo-web-server",
            properties={
                "InstanceType": "t3.micro",
                "ImageId": "ami-12345678",
                "SubnetId": "subnet-12345678"
            },
            tags={
                "Environment": "demo",
                "Application": "web-server"
            }
        )
        
        logger.info(f"Creating resource: {resource_config.name}")
        logger.info(f"Resource type: {resource_config.type}")
        logger.info(f"Properties: {resource_config.properties}")
        
        # Note: This would fail in demo since we don't have actual MCP server
        # but shows the interface usage
        try:
            resource = await infrastructure_service.create_resource(project_id, resource_config)
            logger.info(f"Created resource: {resource.id}")
        except Exception as e:
            logger.info(f"Expected error (no real MCP server): {e}")
        
        # Demo 2: Get resources with filters
        logger.info("\n--- Demo 2: Getting resources with filters ---")
        
        resource_filter = ResourceFilter(
            resource_type="EC2::Instance",
            status=ResourceStatus.ACTIVE,
            tags={"Environment": "demo"}
        )
        
        logger.info(f"Filter - Type: {resource_filter.resource_type}")
        logger.info(f"Filter - Status: {resource_filter.status}")
        logger.info(f"Filter - Tags: {resource_filter.tags}")
        
        try:
            resources = await infrastructure_service.get_resources(project_id, resource_filter)
            logger.info(f"Found {len(resources)} resources")
        except Exception as e:
            logger.info(f"Expected error (no real MCP server): {e}")
        
        # Demo 3: Update a resource
        logger.info("\n--- Demo 3: Updating a resource ---")
        
        resource_update = ResourceUpdate(
            properties={"InstanceType": "t3.small"},
            tags={"Environment": "production"}
        )
        
        logger.info(f"Update - Properties: {resource_update.properties}")
        logger.info(f"Update - Tags: {resource_update.tags}")
        
        try:
            updated_resource = await infrastructure_service.update_resource(
                project_id, "demo-resource-id", resource_update
            )
            logger.info(f"Updated resource: {updated_resource.id}")
        except Exception as e:
            logger.info(f"Expected error (no real MCP server): {e}")
        
        # Demo 4: Generate change plan
        logger.info("\n--- Demo 4: Generating change plan ---")
        
        # Create a desired infrastructure state
        desired_state = InfrastructureState(
            project_id=project_id,
            version="2.0.0",
            timestamp=datetime.now(),
            resources=[],  # Empty for demo
            metadata=StateMetadata(
                last_modified_by="demo-user",
                change_description="Demo infrastructure state"
            )
        )
        
        logger.info(f"Desired state version: {desired_state.version}")
        logger.info(f"Desired state resources: {len(desired_state.resources)}")
        
        try:
            change_plan = await infrastructure_service.generate_change_plan(project_id, desired_state)
            logger.info(f"Generated change plan: {change_plan.id}")
            logger.info(f"Plan status: {change_plan.status}")
            logger.info(f"Total changes: {change_plan.summary.total_changes}")
        except Exception as e:
            logger.info(f"Error generating change plan: {e}")
        
        # Demo 5: Delete a resource
        logger.info("\n--- Demo 5: Deleting a resource ---")
        
        try:
            await infrastructure_service.delete_resource(project_id, "demo-resource-id")
            logger.info("Resource deleted successfully")
        except Exception as e:
            logger.info(f"Expected error (no real MCP server): {e}")
        
        # Demo 6: Project isolation demonstration
        logger.info("\n--- Demo 6: Project isolation ---")
        
        logger.info("Infrastructure service ensures project isolation by:")
        logger.info("1. Adding ProjectId tags to all resources")
        logger.info("2. Filtering resources by project context")
        logger.info("3. Validating resource ownership before operations")
        logger.info("4. Maintaining separate state files per project")
        
        # Show enhanced resource configuration
        enhanced_config = infrastructure_service._enhance_resource_config(project_id, resource_config)
        logger.info(f"Original tags: {resource_config.tags}")
        logger.info(f"Enhanced tags: {enhanced_config.tags}")
        
        # Show enhanced resource filter
        enhanced_filter = infrastructure_service._enhance_resource_filter(project_id, resource_filter)
        logger.info(f"Original filter tags: {resource_filter.tags}")
        logger.info(f"Enhanced filter tags: {enhanced_filter.tags}")
        
    except Exception as e:
        logger.error(f"Demo error: {e}")
    
    finally:
        # Clean up
        if hasattr(aws_mcp_client, 'disconnect'):
            await aws_mcp_client.disconnect()
    
    logger.info("\n=== Demo completed ===")


async def demo_helper_methods():
    """Demonstrate helper methods functionality"""
    
    logger.info("\n=== Helper Methods Demo ===")
    
    # Create a minimal infrastructure service for helper method demos
    from unittest.mock import AsyncMock
    
    infrastructure_service = AWSInfrastructureService(
        aws_mcp_client=AsyncMock(),
        state_service=AsyncMock(),
        change_plan_engine=AsyncMock()
    )
    
    project_id = "helper-demo-project"
    
    # Demo resource tag enhancement
    logger.info("\n--- Resource Tag Enhancement ---")
    original_tags = {"Environment": "test", "Owner": "team-alpha"}
    enhanced_tags = infrastructure_service._enhance_resource_tags(project_id, original_tags)
    
    logger.info(f"Original tags: {original_tags}")
    logger.info(f"Enhanced tags: {enhanced_tags}")
    
    # Demo resource filter enhancement
    logger.info("\n--- Resource Filter Enhancement ---")
    original_filter = ResourceFilter(
        resource_type="EC2::Instance",
        status=ResourceStatus.ACTIVE,
        tags={"Environment": "production"}
    )
    enhanced_filter = infrastructure_service._enhance_resource_filter(project_id, original_filter)
    
    logger.info(f"Original filter tags: {original_filter.tags}")
    logger.info(f"Enhanced filter tags: {enhanced_filter.tags}")
    
    # Demo project-based resource filtering
    logger.info("\n--- Project-based Resource Filtering ---")
    
    from src.models.data_models import Resource
    
    # Create sample resources from different projects
    resources = [
        Resource(
            id="r1", project_id=project_id, type="EC2::Instance", name="r1",
            region="us-east-1", properties={}, tags={"ProjectId": project_id},
            status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
        ),
        Resource(
            id="r2", project_id="other-project", type="EC2::Instance", name="r2",
            region="us-east-1", properties={}, tags={"ProjectId": "other-project"},
            status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
        ),
        Resource(
            id="r3", project_id=project_id, type="RDS::Instance", name="r3",
            region="us-east-1", properties={}, tags={"ProjectId": project_id},
            status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()
        )
    ]
    
    filtered_resources = infrastructure_service._filter_resources_by_project(project_id, resources)
    
    logger.info(f"Total resources: {len(resources)}")
    logger.info(f"Filtered resources for {project_id}: {len(filtered_resources)}")
    logger.info(f"Filtered resource IDs: {[r.id for r in filtered_resources]}")


if __name__ == "__main__":
    # Run the demos
    asyncio.run(demo_infrastructure_service())
    asyncio.run(demo_helper_methods())