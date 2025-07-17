"""
Enumeration classes for AWS Infrastructure Manager
"""
from enum import Enum


class ResourceStatus(Enum):
    """Status of AWS resources"""
    CREATING = "creating"
    ACTIVE = "active"
    UPDATING = "updating"
    DELETING = "deleting"
    ERROR = "error"
    STOPPED = "stopped"


class ChangeAction(Enum):
    """Types of changes that can be made to resources"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class RiskLevel(Enum):
    """Risk levels for infrastructure changes"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    
    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented
    
    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented
    
    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented
    
    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented


class ChangePlanStatus(Enum):
    """Status of change plans"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class ApprovalStatus(Enum):
    """Status of approval requests"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class UserRole(Enum):
    """User roles for authorization"""
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class ErrorCodes(Enum):
    """Error codes for infrastructure operations"""
    AWS_MCP_CONNECTION_FAILED = 'AWS_MCP_001'
    RESOURCE_NOT_FOUND = 'RESOURCE_001'
    INSUFFICIENT_PERMISSIONS = 'AUTH_001'
    STATE_FILE_CORRUPTED = 'STATE_001'
    VALIDATION_FAILED = 'VALIDATION_001'
    APPROVAL_TIMEOUT = 'APPROVAL_001'
    APPROVAL_NOT_FOUND = 'APPROVAL_002'
    APPROVAL_ALREADY_PROCESSED = 'APPROVAL_003'
    PROJECT_NOT_FOUND = 'PROJECT_001'
    PROJECT_ACCESS_DENIED = 'PROJECT_002'
    DUPLICATE_PROJECT_MEMBER = 'PROJECT_003'
    INVALID_CREDENTIALS = 'AUTH_002'
    TOKEN_EXPIRED = 'AUTH_003'
    INVALID_TOKEN = 'AUTH_004'
    USER_NOT_FOUND = 'AUTH_005'