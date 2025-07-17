"""
Core data models for AWS Infrastructure Manager
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from .enums import ResourceStatus, ChangeAction, RiskLevel, ChangePlanStatus, ApprovalStatus, UserRole


@dataclass
class ResourceConfig:
    """Configuration for creating or updating a resource"""
    type: str
    name: str
    properties: Dict[str, Any]
    tags: Optional[Dict[str, str]] = None


@dataclass
class ResourceFilter:
    """Filter criteria for resource queries"""
    resource_type: Optional[str] = None
    status: Optional[ResourceStatus] = None
    tags: Optional[Dict[str, str]] = None
    region: Optional[str] = None


@dataclass
class ResourceUpdate:
    """Updates to apply to a resource"""
    properties: Optional[Dict[str, Any]] = None
    tags: Optional[Dict[str, str]] = None


@dataclass
class Resource:
    """AWS resource representation"""
    id: str
    project_id: str
    type: str
    name: str
    region: str
    properties: Dict[str, Any]
    tags: Dict[str, str]
    status: ResourceStatus
    created_at: datetime
    updated_at: datetime
    arn: Optional[str] = None


@dataclass
class Change:
    """Represents a single change in a change plan"""
    action: ChangeAction
    resource_type: str
    resource_id: str
    current_config: Optional[ResourceConfig] = None
    desired_config: Optional[ResourceConfig] = None
    dependencies: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class ChangeSummary:
    """Summary of changes in a change plan"""
    total_changes: int
    creates: int
    updates: int
    deletes: int
    estimated_cost: Optional[float] = None
    estimated_duration: Optional[int] = None  # in minutes


@dataclass
class ChangePlan:
    """Plan for infrastructure changes"""
    id: str
    project_id: str
    summary: ChangeSummary
    changes: List[Change]
    created_at: datetime
    status: ChangePlanStatus
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


@dataclass
class StateMetadata:
    """Metadata for infrastructure state"""
    last_modified_by: str
    change_description: str
    change_plan_id: Optional[str] = None


@dataclass
class InfrastructureState:
    """Complete state of infrastructure for a project"""
    project_id: str
    version: str
    timestamp: datetime
    resources: List[Resource]
    metadata: StateMetadata


@dataclass
class StateSnapshot:
    """Historical snapshot of infrastructure state"""
    version: str
    timestamp: datetime
    change_description: str
    s3_location: str


@dataclass
class ProjectMember:
    """Member of a project with role"""
    user_id: str
    role: str
    added_at: datetime


@dataclass
class ApprovalRule:
    """Rule for automatic approval of changes"""
    condition: str
    max_risk_level: RiskLevel
    resource_types: List[str]


@dataclass
class NotificationConfig:
    """Configuration for project notifications"""
    email_notifications: bool = True
    slack_webhook: Optional[str] = None
    notification_events: List[str] = field(default_factory=lambda: ["approval_required", "change_executed"])


@dataclass
class ProjectSettings:
    """Settings for a project"""
    s3_bucket_path: str
    default_region: str
    auto_approval_rules: Optional[List[ApprovalRule]] = None
    notification_settings: Optional[NotificationConfig] = None


@dataclass
class ProjectConfig:
    """Configuration for creating a project"""
    name: str
    description: str
    owner: str
    settings: ProjectSettings


@dataclass
class ProjectUpdate:
    """Updates to apply to a project"""
    name: Optional[str] = None
    description: Optional[str] = None
    settings: Optional[ProjectSettings] = None


@dataclass
class Project:
    """Project representation"""
    id: str
    name: str
    description: str
    owner: str
    members: List[ProjectMember]
    settings: ProjectSettings
    created_at: datetime
    updated_at: datetime


@dataclass
class DependencyGraph:
    """Graph representing resource dependencies"""
    nodes: List[str]
    edges: List[tuple[str, str]]  # (from, to) relationships


@dataclass
class CostEstimate:
    """Cost estimation for changes"""
    total_monthly_cost: float
    cost_breakdown: Dict[str, float]
    currency: str = "USD"


@dataclass
class ValidationResult:
    """Result of change plan validation"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ApprovalRequest:
    """Request for approval of a change plan"""
    id: str
    change_plan_id: str
    project_id: str
    requester_id: str
    approver_id: Optional[str]
    status: ApprovalStatus
    created_at: datetime
    expires_at: datetime
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    timeout_minutes: int = 60  # Default timeout


@dataclass
class ApprovalWorkflowConfig:
    """Configuration for approval workflow"""
    default_timeout_minutes: int = 60
    auto_approval_enabled: bool = False
    required_approvers: List[str] = field(default_factory=list)
    approval_rules: List[ApprovalRule] = field(default_factory=list)


@dataclass
class ErrorResponse:
    """Standard error response"""
    code: str
    message: str
    timestamp: datetime
    request_id: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class View:
    """Represents a custom view of resources"""
    id: str
    project_id: str
    name: str
    filters: ResourceFilter
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass
class Dashboard:
    """Represents a dashboard of views"""
    id: str
    project_id: str
    name: str
    description: str
    views: List[str]  # List of view IDs
    created_by: str
    created_at: datetime
    updated_at: datetime


@dataclass
class User:
    """User representation"""
    id: str
    username: str
    email: str
    full_name: str
    role: UserRole
    hashed_password: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class UserCreate:
    """Data for creating a new user"""
    username: str
    email: str
    password: str
    full_name: str
    role: UserRole = UserRole.DEVELOPER


@dataclass
class UserUpdate:
    """Data for updating a user"""
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


@dataclass
class Token:
    """JWT token data"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


@dataclass
class TokenData:
    """Data stored in JWT token"""
    user_id: str
    username: str
    role: str
    exp: datetime


@dataclass
class TokenPayload:
    """JWT token payload"""
    sub: str  # user_id
    username: str
    role: str
    exp: int  # expiration timestamp


@dataclass
class ProjectRole:
    """User role in a specific project"""
    project_id: str
    user_id: str
    role: UserRole
    assigned_at: datetime = field(default_factory=datetime.now)
