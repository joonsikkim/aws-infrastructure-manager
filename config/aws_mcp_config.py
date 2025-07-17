"""
AWS MCP Client configuration settings.
"""
from typing import Optional, Dict, Any, List
from pydantic import Field, validator
from pydantic_settings import BaseSettings


class MCPRetrySettings(BaseSettings):
    """MCP retry configuration settings."""
    
    max_retries: int = Field(default=3, env="AWS_MCP_MAX_RETRIES")
    base_delay: float = Field(default=1.0, env="AWS_MCP_BASE_DELAY")
    max_delay: float = Field(default=60.0, env="AWS_MCP_MAX_DELAY")
    exponential_base: float = Field(default=2.0, env="AWS_MCP_EXPONENTIAL_BASE")
    enable_jitter: bool = Field(default=True, env="AWS_MCP_ENABLE_JITTER")
    
    class Config:
        env_prefix = "AWS_MCP_"


class MCPCircuitBreakerSettings(BaseSettings):
    """MCP circuit breaker configuration settings."""
    
    failure_threshold: int = Field(default=5, env="AWS_MCP_CB_FAILURE_THRESHOLD")
    recovery_timeout: int = Field(default=60, env="AWS_MCP_CB_RECOVERY_TIMEOUT")
    success_threshold: int = Field(default=3, env="AWS_MCP_CB_SUCCESS_THRESHOLD")
    
    class Config:
        env_prefix = "AWS_MCP_CB_"


class MCPLoggingSettings(BaseSettings):
    """MCP logging configuration settings."""
    
    debug_logging: bool = Field(default=False, env="AWS_MCP_DEBUG_LOGGING")
    log_requests: bool = Field(default=False, env="AWS_MCP_LOG_REQUESTS")
    log_responses: bool = Field(default=False, env="AWS_MCP_LOG_RESPONSES")
    
    class Config:
        env_prefix = "AWS_MCP_"


class MCPPoolSettings(BaseSettings):
    """MCP connection pool configuration settings."""
    
    pool_size: int = Field(default=10, env="AWS_MCP_POOL_SIZE")
    max_connections: int = Field(default=100, env="AWS_MCP_MAX_CONNECTIONS")
    keep_alive: bool = Field(default=True, env="AWS_MCP_KEEP_ALIVE")
    
    class Config:
        env_prefix = "AWS_MCP_"


class AWSMCPSettings(BaseSettings):
    """AWS MCP Client configuration settings."""
    
    server_url: str = Field(default="http://localhost:8080", env="AWS_MCP_SERVER_URL")
    timeout: int = Field(default=30, env="AWS_MCP_TIMEOUT")
    
    # Allowed AWS services
    allowed_services: List[str] = Field(
        default=[
            "ec2", "s3", "dynamodb", "lambda", "iam", "cloudformation",
            "cloudwatch", "sns", "sqs", "rds", "vpc"
        ],
        env="AWS_MCP_ALLOWED_SERVICES"
    )
    
    # Sub-settings
    retry: MCPRetrySettings = MCPRetrySettings()
    circuit_breaker: MCPCircuitBreakerSettings = MCPCircuitBreakerSettings()
    logging: MCPLoggingSettings = MCPLoggingSettings()
    pool: MCPPoolSettings = MCPPoolSettings()
    
    @validator("server_url")
    def validate_server_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("AWS_MCP_SERVER_URL must start with http:// or https://")
        return v
    
    @validator("allowed_services", pre=True)
    def parse_allowed_services(cls, v):
        if isinstance(v, str):
            return [service.strip() for service in v.split(",")]
        return v
    
    class Config:
        env_prefix = "AWS_MCP_"
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global MCP settings instance
aws_mcp_settings = AWSMCPSettings()


def get_mcp_config() -> AWSMCPSettings:
    """Get AWS MCP Client configuration."""
    return aws_mcp_settings