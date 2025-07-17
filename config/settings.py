"""
Configuration settings for AWS Infrastructure Manager.
"""
from typing import Optional, List, Dict, Any
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from pathlib import Path
import os


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""
    
    url: str = Field(default="sqlite:///./aws_infra_manager.db", env="DATABASE_URL")
    echo: bool = Field(default=False, env="DATABASE_ECHO")
    
    class Config:
        env_prefix = "DB_"


class AWSSettings(BaseSettings):
    """AWS configuration settings."""
    
    region: str = Field(default="us-east-1", env="AWS_DEFAULT_REGION")
    access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    session_token: Optional[str] = Field(default=None, env="AWS_SESSION_TOKEN")
    profile: Optional[str] = Field(default=None, env="AWS_PROFILE")
    
    # S3 State Management
    state_bucket: str = Field(default="aws-infra-manager-state", env="AWS_STATE_BUCKET")
    state_bucket_prefix: str = Field(default="projects", env="AWS_STATE_BUCKET_PREFIX")
    
    class Config:
        env_prefix = "AWS_"


class MCPSettings(BaseSettings):
    """MCP Server configuration settings."""
    
    server_url: str = Field(default="http://localhost:8080", env="MCP_SERVER_URL")
    timeout: int = Field(default=30, env="MCP_TIMEOUT")
    max_retries: int = Field(default=3, env="MCP_MAX_RETRIES")
    retry_delay: float = Field(default=1.0, env="MCP_RETRY_DELAY")
    
    class Config:
        env_prefix = "MCP_"


class SecuritySettings(BaseSettings):
    """Security configuration settings."""
    
    secret_key: str = Field(default="your-super-secret-key-here-at-least-32-characters-long", env="SECRET_KEY")
    algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")
    
    @validator("secret_key")
    def validate_secret_key(cls, v):
        if not v or len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v
    
    class Config:
        env_prefix = "SECURITY_"


class LoggingSettings(BaseSettings):
    """Logging configuration settings."""
    
    level: str = Field(default="INFO", env="LOG_LEVEL")
    format: str = Field(default="json", env="LOG_FORMAT")  # json or text
    file_path: Optional[str] = Field(default=None, env="LOG_FILE_PATH")
    max_file_size: int = Field(default=10485760, env="LOG_MAX_FILE_SIZE")  # 10MB
    backup_count: int = Field(default=5, env="LOG_BACKUP_COUNT")
    
    # AWS Lambda Powertools specific settings
    sample_rate: float = Field(default=0.1, env="POWERTOOLS_LOGGER_SAMPLE_RATE")
    log_event: bool = Field(default=True, env="POWERTOOLS_LOGGER_LOG_EVENT")
    
    @validator("level")
    def validate_log_level(cls, v):
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()
    
    @validator("sample_rate")
    def validate_sample_rate(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("POWERTOOLS_LOGGER_SAMPLE_RATE must be between 0.0 and 1.0")
        return v
    
    class Config:
        env_prefix = "LOG_"


class APISettings(BaseSettings):
    """API configuration settings."""
    
    host: str = Field(default="0.0.0.0", env="API_HOST")
    port: int = Field(default=8000, env="API_PORT")
    debug: bool = Field(default=False, env="API_DEBUG")
    reload: bool = Field(default=False, env="API_RELOAD")
    workers: int = Field(default=1, env="API_WORKERS")
    
    # CORS settings
    cors_origins: List[str] = Field(default=["*"], env="CORS_ORIGINS")
    cors_methods: List[str] = Field(default=["*"], env="CORS_METHODS")
    cors_headers: List[str] = Field(default=["*"], env="CORS_HEADERS")
    
    @validator("cors_origins", "cors_methods", "cors_headers", pre=True)
    def parse_cors_list(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        return v
    
    class Config:
        env_prefix = "API_"


class Settings(BaseSettings):
    """Main application settings."""
    
    app_name: str = Field(default="AWS Infrastructure Manager", env="APP_NAME")
    app_version: str = Field(default="0.1.0", env="APP_VERSION")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Sub-settings
    database: DatabaseSettings = DatabaseSettings()
    aws: AWSSettings = AWSSettings()
    mcp: MCPSettings = MCPSettings()
    security: SecuritySettings = SecuritySettings()
    logging: LoggingSettings = LoggingSettings()
    api: APISettings = APISettings()
    
    @validator("environment")
    def validate_environment(cls, v):
        valid_envs = ["development", "testing", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"ENVIRONMENT must be one of {valid_envs}")
        return v.lower()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
settings = Settings()