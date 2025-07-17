"""
Abstract service interfaces for AWS Infrastructure Manager
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from ..models.data_models import (
    Resource, ResourceConfig, ResourceFilter, ResourceUpdate,
    InfrastructureState, StateSnapshot, ChangePlan,
    Project, ProjectConfig, ProjectUpdate,
    DependencyGraph, CostEstimate, ValidationResult,
    User, UserCreate, UserUpdate, Token
)


class InfrastructureService(ABC):
    """Abstract interface for infrastructure management operations"""
    
    @abstractmethod
    async def create_resource(self, project_id: str, resource_config: ResourceConfig) -> Resource:
        """Create a new AWS resource"""
        pass
    
    @abstractmethod
    async def get_resources(self, project_id: str, filters: Optional[ResourceFilter] = None) -> List[Resource]:
        """Get resources for a project with optional filtering"""
        pass
    
    @abstractmethod
    async def update_resource(self, project_id: str, resource_id: str, updates: ResourceUpdate) -> Resource:
        """Update an existing resource"""
        pass
    
    @abstractmethod
    async def delete_resource(self, project_id: str, resource_id: str) -> None:
        """Delete a resource"""
        pass
    
    @abstractmethod
    async def generate_change_plan(self, project_id: str, desired_state: InfrastructureState) -> ChangePlan:
        """Generate a change plan for desired infrastructure state"""
        pass


class StateManagementService(ABC):
    """Abstract interface for state management operations"""
    
    @abstractmethod
    async def get_current_state(self, project_id: str) -> Optional[InfrastructureState]:
        """Get the current infrastructure state for a project"""
        pass
    
    @abstractmethod
    async def save_state(self, project_id: str, state: InfrastructureState) -> None:
        """Save infrastructure state to S3"""
        pass
    
    @abstractmethod
    async def get_state_history(self, project_id: str, limit: Optional[int] = None) -> List[StateSnapshot]:
        """Get historical state snapshots"""
        pass
    
    @abstractmethod
    def compare_states(self, current_state: InfrastructureState, desired_state: InfrastructureState) -> ChangePlan:
        """Compare two states and generate a change plan"""
        pass

    @abstractmethod
    async def save_change_plan(self, project_id: str, plan: ChangePlan) -> None:
        """Save a change plan"""
        pass

    @abstractmethod
    async def get_change_plan(self, project_id: str, plan_id: str) -> Optional[ChangePlan]:
        """Get a specific change plan"""
        pass

    @abstractmethod
    async def list_change_plans(self, project_id: str) -> List[ChangePlan]:
        """List all change plans for a project"""
        pass


class ProjectManagementService(ABC):
    """Abstract interface for project management operations"""
    
    @abstractmethod
    async def create_project(self, project: ProjectConfig) -> Project:
        """Create a new project"""
        pass
    
    @abstractmethod
    async def get_project(self, project_id: str) -> Project:
        """Get a project by ID"""
        pass
    
    @abstractmethod
    async def list_projects(self, user_id: str) -> List[Project]:
        """List projects accessible to a user"""
        pass
    
    @abstractmethod
    async def update_project(self, project_id: str, updates: ProjectUpdate) -> Project:
        """Update an existing project"""
        pass
    
    @abstractmethod
    async def delete_project(self, project_id: str) -> None:
        """Delete a project"""
        pass
    
    @abstractmethod
    async def validate_project_access(self, user_id: str, project_id: str) -> bool:
        """Validate if a user has access to a project"""
        pass


class ChangePlanEngine(ABC):
    """Abstract interface for change plan generation and analysis"""
    
    @abstractmethod
    async def generate_plan(self, project_id: str, desired_state: InfrastructureState) -> ChangePlan:
        """Generate a change plan for desired state"""
        pass
    
    @abstractmethod
    async def analyze_dependencies(self, changes: List) -> DependencyGraph:
        """Analyze dependencies between changes"""
        pass
    
    @abstractmethod
    async def estimate_cost(self, change_plan: ChangePlan) -> CostEstimate:
        """Estimate cost of executing a change plan"""
        pass
    
    @abstractmethod
    async def validate_plan(self, change_plan: ChangePlan) -> ValidationResult:
        """Validate a change plan for safety and correctness"""
        pass


class ApprovalWorkflowService(ABC):
    """Abstract interface for approval workflow management"""
    
    @abstractmethod
    async def submit_for_approval(self, change_plan: ChangePlan) -> str:
        """Submit a change plan for approval"""
        pass
    
    @abstractmethod
    async def approve_plan(self, plan_id: str, approver_id: str) -> ChangePlan:
        """Approve a change plan"""
        pass
    
    @abstractmethod
    async def reject_plan(self, plan_id: str, approver_id: str, reason: str) -> ChangePlan:
        """Reject a change plan"""
        pass
    
    @abstractmethod
    async def get_pending_approvals(self, user_id: str) -> List[ChangePlan]:
        """Get change plans pending approval for a user"""
        pass
    
    @abstractmethod
    async def check_approval_timeout(self, plan_id: str) -> bool:
        """Check if a plan has exceeded approval timeout"""
        pass


class AuthService(ABC):
    """Abstract interface for authentication and authorization operations"""
    
    @abstractmethod
    async def register_user(self, user_create: UserCreate) -> User:
        """Register a new user"""
        pass
    
    @abstractmethod
    async def authenticate_user(self, username: str, password: str) -> User:
        """Authenticate a user with username and password"""
        pass
    
    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID"""
        pass
    
    @abstractmethod
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username"""
        pass
    
    @abstractmethod
    async def update_user(self, user_id: str, user_update: UserUpdate) -> User:
        """Update a user"""
        pass
    
    @abstractmethod
    async def create_access_token(self, user: User) -> Token:
        """Create access and refresh tokens for a user"""
        pass
    
    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> Token:
        """Create new access token using refresh token"""
        pass
    
    @abstractmethod
    async def verify_token(self, token: str) -> Optional[User]:
        """Verify a token and return the associated user"""
        pass
    
    @abstractmethod
    async def get_project_role(self, user_id: str, project_id: str) -> Optional[str]:
        """Get user's role in a specific project"""
        pass
    
    @abstractmethod
    async def set_project_role(self, user_id: str, project_id: str, role: str) -> None:
        """Set user's role in a specific project"""
        pass