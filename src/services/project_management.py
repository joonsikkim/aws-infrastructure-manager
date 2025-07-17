"""
Project Management Service Implementation
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging
from ..models.data_models import (
    Project, ProjectConfig, ProjectUpdate, ProjectMember,
    ErrorResponse
)
from ..models.exceptions import ProjectNotFoundError, AccessDeniedError, InfrastructureException
from ..models.enums import ErrorCodes
from .interfaces import ProjectManagementService

logger = logging.getLogger(__name__)


class ProjectManagementServiceImpl(ProjectManagementService):
    """Implementation of project management operations"""
    
    def __init__(self):
        # In-memory storage for demo purposes
        # In production, this would use a database
        self._projects: Dict[str, Project] = {}
        logger.info("ProjectManagementService initialized")
    
    async def create_project(self, project_config: ProjectConfig) -> Project:
        """Create a new project"""
        project_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Create owner as first member
        owner_member = ProjectMember(
            user_id=project_config.owner,
            role="owner",
            added_at=now
        )
        
        project = Project(
            id=project_id,
            name=project_config.name,
            description=project_config.description,
            owner=project_config.owner,
            members=[owner_member],
            settings=project_config.settings,
            created_at=now,
            updated_at=now
        )
        
        self._projects[project_id] = project
        return project
    
    async def get_project(self, project_id: str) -> Project:
        """Get a project by ID"""
        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        
        return self._projects[project_id]
    
    async def list_projects(self, user_id: str) -> List[Project]:
        """List projects accessible to a user"""
        accessible_projects = []
        
        for project in self._projects.values():
            # Check if user is owner or member
            if project.owner == user_id:
                accessible_projects.append(project)
            elif any(member.user_id == user_id for member in project.members):
                accessible_projects.append(project)
        
        return accessible_projects
    
    async def update_project(self, project_id: str, updates: ProjectUpdate) -> Project:
        """Update an existing project"""
        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        
        project = self._projects[project_id]
        
        # Apply updates
        if updates.name is not None:
            project.name = updates.name
        if updates.description is not None:
            project.description = updates.description
        if updates.settings is not None:
            project.settings = updates.settings
        
        project.updated_at = datetime.now(timezone.utc)
        
        return project
    
    async def delete_project(self, project_id: str) -> None:
        """Delete a project"""
        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        
        del self._projects[project_id]
    
    async def validate_project_access(self, user_id: str, project_id: str) -> bool:
        """Validate if a user has access to a project"""
        if project_id not in self._projects:
            return False
        
        project = self._projects[project_id]
        
        # Check if user is owner
        if project.owner == user_id:
            return True
        
        # Check if user is a member
        return any(member.user_id == user_id for member in project.members)
    
    async def add_project_member(self, project_id: str, user_id: str, role: str) -> Project:
        """Add a member to a project"""
        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        
        project = self._projects[project_id]
        
        # Check if user is already a member
        if any(member.user_id == user_id for member in project.members):
            raise ValueError(f"User {user_id} is already a member of project {project_id}")
        
        new_member = ProjectMember(
            user_id=user_id,
            role=role,
            added_at=datetime.now(timezone.utc)
        )
        
        project.members.append(new_member)
        project.updated_at = datetime.now(timezone.utc)
        
        return project
    
    async def remove_project_member(self, project_id: str, user_id: str) -> Project:
        """Remove a member from a project"""
        if project_id not in self._projects:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        
        project = self._projects[project_id]
        
        # Cannot remove owner
        if project.owner == user_id:
            raise ValueError("Cannot remove project owner")
        
        # Find and remove member
        original_count = len(project.members)
        project.members = [m for m in project.members if m.user_id != user_id]
        
        if len(project.members) == original_count:
            raise ValueError(f"User {user_id} is not a member of project {project_id}")
        
        project.updated_at = datetime.now(timezone.utc)
        
        return project