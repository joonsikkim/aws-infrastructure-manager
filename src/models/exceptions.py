"""
Custom exceptions for AWS Infrastructure Manager
"""
from datetime import datetime
from typing import Dict, Any, Optional
from .enums import ErrorCodes


class InfrastructureException(Exception):
    """Base exception for infrastructure management operations"""
    
    def __init__(self, code: ErrorCodes, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses"""
        return {
            "code": self.code.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }


class ProjectNotFoundError(InfrastructureException):
    """Exception raised when a project is not found"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCodes.RESOURCE_NOT_FOUND, message, details)


class AccessDeniedError(InfrastructureException):
    """Exception raised when access is denied to a resource"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCodes.INSUFFICIENT_PERMISSIONS, message, details)