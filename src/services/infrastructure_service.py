"""
Infrastructure Service Implementation for AWS Infrastructure Manager
"""
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from .interfaces import InfrastructureService, StateManagementService, ChangePlanEngine
from .aws_mcp_client import AWSMCPClient
from ..models.data_models import (
    Resource, ResourceConfig, ResourceFilter, ResourceUpdate,
    InfrastructureState, ChangePlan, Change, ChangeSummary,
    StateMetadata
)
from ..models.enums import ResourceStatus, ChangeAction, ChangePlanStatus
from ..models.exceptions import InfrastructureException, ErrorCodes


class AWSInfrastructureService(InfrastructureService):
    """
    Concrete implementation of InfrastructureService using AWS MCP Client
    """
    
    def __init__(
        self,
        aws_mcp_client: AWSMCPClient,
        state_service: StateManagementService,
        change_plan_engine: ChangePlanEngine
    ):
        self.aws_mcp_client = aws_mcp_client
        self.state_service = state_service
        self.change_plan_engine = change_plan_engine
        self.logger = logging.getLogger(__name__)
    
    async def create_resource(
        self,
        project_id: str,
        resource_config: ResourceConfig
    ) -> Resource:
        """
        Create a new AWS resource for the specified project
        
        Args:
            project_id: ID of the project
            resource_config: Configuration for the resource to create
            
        Returns:
            Created Resource object
            
        Raises:
            InfrastructureException: If resource creation fails
        """
        try:
            self.logger.info(f"Creating resource {resource_config.name} for project {project_id}")
            
            # Validate project context
            await self._validate_project_context(project_id)
            
            # Add project-specific tags
            enhanced_config = self._enhance_resource_config(project_id, resource_config)
            
            # Create resource via AWS MCP
            resource = await self.aws_mcp_client.create_resource(
                project_id=project_id,
                resource_config=enhanced_config
            )
            
            # Update project state
            await self._update_project_state_after_create(project_id, resource)
            
            self.logger.info(f"Successfully created resource {resource.id} for project {project_id}")
            return resource
            
        except Exception as e:
            self.logger.error(f"Failed to create resource for project {project_id}: {e}")
            if isinstance(e, InfrastructureException):
                raise
            raise InfrastructureException(
                ErrorCodes.AWS_MCP_CONNECTION_FAILED,
                f"Resource creation failed: {str(e)}"
            )
    
    async def get_resources(
        self,
        project_id: str,
        filters: Optional[ResourceFilter] = None
    ) -> List[Resource]:
        """
        Get resources for a project with optional filtering
        
        Args:
            project_id: ID of the project
            filters: Optional filters to apply
            
        Returns:
            List of resources matching the criteria
        """
        try:
            self.logger.debug(f"Getting resources for project {project_id}")
            
            # Validate project context
            await self._validate_project_context(project_id)
            
            # Enhance filters with project-specific context
            enhanced_filters = self._enhance_resource_filter(project_id, filters)
            
            # Get resources from AWS MCP
            resources = await self.aws_mcp_client.list_resources(
                project_id=project_id,
                filters=enhanced_filters
            )
            
            # Filter resources to ensure project isolation
            filtered_resources = self._filter_resources_by_project(project_id, resources)
            
            self.logger.debug(f"Found {len(filtered_resources)} resources for project {project_id}")
            return filtered_resources
            
        except Exception as e:
            self.logger.error(f"Failed to get resources for project {project_id}: {e}")
            if isinstance(e, InfrastructureException):
                raise
            raise InfrastructureException(
                ErrorCodes.RESOURCE_NOT_FOUND,
                f"Failed to retrieve resources: {str(e)}"
            )
    
    async def update_resource(
        self,
        project_id: str,
        resource_id: str,
        updates: ResourceUpdate
    ) -> Resource:
        """
        Update an existing resource
        
        Args:
            project_id: ID of the project
            resource_id: ID of the resource to update
            updates: Updates to apply
            
        Returns:
            Updated Resource object
            
        Raises:
            InfrastructureException: If resource update fails
        """
        try:
            self.logger.info(f"Updating resource {resource_id} for project {project_id}")
            
            # Validate project context and resource ownership
            await self._validate_resource_ownership(project_id, resource_id)
            
            # Prepare update parameters
            update_params = {}
            if updates.properties:
                update_params.update(updates.properties)
            if updates.tags:
                # Merge with existing project tags
                enhanced_tags = self._enhance_resource_tags(project_id, updates.tags)
                update_params["tags"] = enhanced_tags
            
            # Update resource via AWS MCP
            resource = await self.aws_mcp_client.update_resource(
                project_id=project_id,
                resource_id=resource_id,
                updates=update_params
            )
            
            # Update project state
            await self._update_project_state_after_update(project_id, resource)
            
            self.logger.info(f"Successfully updated resource {resource_id} for project {project_id}")
            return resource
            
        except Exception as e:
            self.logger.error(f"Failed to update resource {resource_id} for project {project_id}: {e}")
            if isinstance(e, InfrastructureException):
                raise
            raise InfrastructureException(
                ErrorCodes.RESOURCE_NOT_FOUND,
                f"Resource update failed: {str(e)}"
            )
    
    async def delete_resource(
        self,
        project_id: str,
        resource_id: str
    ) -> None:
        """
        Delete a resource
        
        Args:
            project_id: ID of the project
            resource_id: ID of the resource to delete
            
        Raises:
            InfrastructureException: If resource deletion fails
        """
        try:
            self.logger.info(f"Deleting resource {resource_id} for project {project_id}")
            
            # Validate project context and resource ownership
            await self._validate_resource_ownership(project_id, resource_id)
            
            # Get resource details before deletion for state update
            resource = await self.aws_mcp_client.get_resource(project_id, resource_id)
            if not resource:
                raise InfrastructureException(
                    ErrorCodes.RESOURCE_NOT_FOUND,
                    f"Resource {resource_id} not found"
                )
            
            # Delete resource via AWS MCP
            success = await self.aws_mcp_client.delete_resource(
                project_id=project_id,
                resource_id=resource_id
            )
            
            if not success:
                raise InfrastructureException(
                    ErrorCodes.AWS_MCP_CONNECTION_FAILED,
                    f"Failed to delete resource {resource_id}"
                )
            
            # Update project state
            await self._update_project_state_after_delete(project_id, resource)
            
            self.logger.info(f"Successfully deleted resource {resource_id} for project {project_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to delete resource {resource_id} for project {project_id}: {e}")
            if isinstance(e, InfrastructureException):
                raise
            raise InfrastructureException(
                ErrorCodes.RESOURCE_NOT_FOUND,
                f"Resource deletion failed: {str(e)}"
            )
    
    async def generate_change_plan(
        self,
        project_id: str,
        desired_state: InfrastructureState
    ) -> ChangePlan:
        """
        Generate a change plan for desired infrastructure state
        
        Args:
            project_id: ID of the project
            desired_state: Desired infrastructure state
            
        Returns:
            Generated ChangePlan
        """
        try:
            self.logger.info(f"Generating change plan for project {project_id}")
            
            # Validate project context
            await self._validate_project_context(project_id)
            
            # Ensure desired state is for the correct project
            if desired_state.project_id != project_id:
                raise InfrastructureException(
                    ErrorCodes.VALIDATION_FAILED,
                    f"Desired state project ID {desired_state.project_id} does not match {project_id}"
                )
            
            # Use change plan engine to generate the plan
            change_plan = await self.change_plan_engine.generate_plan(project_id, desired_state)
            
            self.logger.info(f"Generated change plan {change_plan.id} for project {project_id}")
            return change_plan
            
        except Exception as e:
            self.logger.error(f"Failed to generate change plan for project {project_id}: {e}")
            if isinstance(e, InfrastructureException):
                raise
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                f"Change plan generation failed: {str(e)}"
            )
    
    # Private helper methods
    
    async def _validate_project_context(self, project_id: str) -> None:
        """Validate that the project context is valid"""
        if not project_id or not project_id.strip():
            raise InfrastructureException(
                ErrorCodes.VALIDATION_FAILED,
                "Project ID is required"
            )
    
    async def _validate_resource_ownership(self, project_id: str, resource_id: str) -> None:
        """Validate that a resource belongs to the specified project"""
        await self._validate_project_context(project_id)
        
        # Get the resource to verify ownership
        resource = await self.aws_mcp_client.get_resource(project_id, resource_id)
        if not resource:
            raise InfrastructureException(
                ErrorCodes.RESOURCE_NOT_FOUND,
                f"Resource {resource_id} not found"
            )
        
        if resource.project_id != project_id:
            raise InfrastructureException(
                ErrorCodes.INSUFFICIENT_PERMISSIONS,
                f"Resource {resource_id} does not belong to project {project_id}"
            )
    
    def _enhance_resource_config(
        self,
        project_id: str,
        resource_config: ResourceConfig
    ) -> ResourceConfig:
        """Enhance resource configuration with project-specific settings"""
        enhanced_tags = self._enhance_resource_tags(project_id, resource_config.tags or {})
        
        return ResourceConfig(
            type=resource_config.type,
            name=resource_config.name,
            properties=resource_config.properties,
            tags=enhanced_tags
        )
    
    def _enhance_resource_tags(
        self,
        project_id: str,
        tags: Dict[str, str]
    ) -> Dict[str, str]:
        """Add project-specific tags to resource tags"""
        enhanced_tags = tags.copy()
        enhanced_tags.update({
            "ProjectId": project_id,
            "ManagedBy": "aws-infrastructure-manager",
            "CreatedAt": datetime.now().isoformat()
        })
        return enhanced_tags
    
    def _enhance_resource_filter(
        self,
        project_id: str,
        filters: Optional[ResourceFilter]
    ) -> ResourceFilter:
        """Enhance resource filter with project-specific context"""
        if filters is None:
            filters = ResourceFilter()
        
        # Ensure we only get resources for this project
        project_tags = {"ProjectId": project_id}
        if filters.tags:
            project_tags.update(filters.tags)
        
        return ResourceFilter(
            resource_type=filters.resource_type,
            status=filters.status,
            tags=project_tags,
            region=filters.region
        )
    
    def _filter_resources_by_project(
        self,
        project_id: str,
        resources: List[Resource]
    ) -> List[Resource]:
        """Filter resources to ensure project isolation"""
        filtered_resources = []
        
        for resource in resources:
            # Check if resource belongs to the project
            if (resource.project_id == project_id or 
                resource.tags.get("ProjectId") == project_id):
                filtered_resources.append(resource)
            else:
                self.logger.warning(
                    f"Resource {resource.id} does not belong to project {project_id}, filtering out"
                )
        
        return filtered_resources
    
    async def _update_project_state_after_create(
        self,
        project_id: str,
        resource: Resource
    ) -> None:
        """Update project state after resource creation"""
        try:
            current_state = await self.state_service.get_current_state(project_id)
            
            if current_state is None:
                # Create initial state
                current_state = InfrastructureState(
                    project_id=project_id,
                    version="1.0.0",
                    timestamp=datetime.now(),
                    resources=[],
                    metadata=StateMetadata(
                        last_modified_by="system",
                        change_description="Initial state creation"
                    )
                )
            
            # Add the new resource
            current_state.resources.append(resource)
            current_state.timestamp = datetime.now()
            current_state.metadata.change_description = f"Created resource {resource.name}"
            current_state.metadata.last_modified_by = "system"
            
            # Save updated state
            await self.state_service.save_state(project_id, current_state)
            
        except Exception as e:
            self.logger.warning(f"Failed to update state after resource creation: {e}")
    
    async def _update_project_state_after_update(
        self,
        project_id: str,
        resource: Resource
    ) -> None:
        """Update project state after resource update"""
        try:
            current_state = await self.state_service.get_current_state(project_id)
            
            if current_state:
                # Find and update the resource in state
                for i, existing_resource in enumerate(current_state.resources):
                    if existing_resource.id == resource.id:
                        current_state.resources[i] = resource
                        break
                else:
                    # Resource not found in state, add it
                    current_state.resources.append(resource)
                
                current_state.timestamp = datetime.now()
                current_state.metadata.change_description = f"Updated resource {resource.name}"
                current_state.metadata.last_modified_by = "system"
                
                # Save updated state
                await self.state_service.save_state(project_id, current_state)
            
        except Exception as e:
            self.logger.warning(f"Failed to update state after resource update: {e}")
    
    async def _update_project_state_after_delete(
        self,
        project_id: str,
        resource: Resource
    ) -> None:
        """Update project state after resource deletion"""
        try:
            current_state = await self.state_service.get_current_state(project_id)
            
            if current_state:
                # Remove the resource from state
                current_state.resources = [
                    r for r in current_state.resources if r.id != resource.id
                ]
                
                current_state.timestamp = datetime.now()
                current_state.metadata.change_description = f"Deleted resource {resource.name}"
                current_state.metadata.last_modified_by = "system"
                
                # Save updated state
                await self.state_service.save_state(project_id, current_state)
            
        except Exception as e:
            self.logger.warning(f"Failed to update state after resource deletion: {e}")


# Factory function for creating infrastructure service
def create_infrastructure_service(
    aws_mcp_client: AWSMCPClient,
    state_service: StateManagementService,
    change_plan_engine: ChangePlanEngine
) -> AWSInfrastructureService:
    """
    Factory function to create infrastructure service
    
    Args:
        aws_mcp_client: AWS MCP client instance
        state_service: State management service instance
        change_plan_engine: Change plan engine instance
        
    Returns:
        Configured AWSInfrastructureService instance
    """
    return AWSInfrastructureService(
        aws_mcp_client=aws_mcp_client,
        state_service=state_service,
        change_plan_engine=change_plan_engine
    )