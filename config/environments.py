"""
Environment-specific configuration overrides.
"""
from typing import Dict, Any
from .settings import Settings


class DevelopmentConfig(Settings):
    """Development environment configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api.debug = True
        self.api.reload = True
        self.logging.level = "DEBUG"
        self.database.echo = True


class TestingConfig(Settings):
    """Testing environment configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.database.url = "sqlite:///:memory:"
        self.logging.level = "WARNING"
        self.security.secret_key = "test-secret-key-for-testing-only-32-chars"


class StagingConfig(Settings):
    """Staging environment configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api.debug = False
        self.api.reload = False
        self.logging.level = "INFO"


class ProductionConfig(Settings):
    """Production environment configuration."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api.debug = False
        self.api.reload = False
        self.api.workers = 4
        self.logging.level = "WARNING"


# Configuration factory
CONFIG_MAP: Dict[str, type] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "staging": StagingConfig,
    "production": ProductionConfig,
}


def get_config(environment: str = None) -> Settings:
    """Get configuration for the specified environment."""
    if environment is None:
        from .settings import settings
        environment = settings.environment
    
    config_class = CONFIG_MAP.get(environment.lower(), Settings)
    return config_class()