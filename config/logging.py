"""
Logging configuration for AWS Infrastructure Manager using AWS Lambda Powertools.
"""
import logging
import os
from typing import Optional
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit
from .settings import settings

# Initialize AWS Lambda Powertools
logger = Logger(
    service=settings.app_name,
    level=settings.logging.level,
    log_uncaught_exceptions=True,
    serialize_stacktrace=True,
)

tracer = Tracer(
    service=settings.app_name,
    auto_patch=True,
)

metrics = Metrics(
    service=settings.app_name,
    namespace="AWSInfrastructureManager",
)


def configure_logging() -> None:
    """Configure AWS Lambda Powertools logging."""
    
    # Set log level from settings
    logger.setLevel(settings.logging.level)
    
    # Configure correlation IDs for request tracing
    logger.append_keys(
        environment=settings.environment,
        version=settings.app_version,
    )
    
    # Configure standard library logging to work with Powertools
    logging.basicConfig(
        level=getattr(logging, settings.logging.level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Set environment variables for Powertools
    os.environ.setdefault("POWERTOOLS_SERVICE_NAME", settings.app_name)
    os.environ.setdefault("POWERTOOLS_LOG_LEVEL", settings.logging.level)
    os.environ.setdefault("POWERTOOLS_LOGGER_SAMPLE_RATE", "0.1")
    os.environ.setdefault("POWERTOOLS_LOGGER_LOG_EVENT", "true")
    os.environ.setdefault("POWERTOOLS_TRACE_SAMPLE_RATE", "0.1")
    os.environ.setdefault("POWERTOOLS_METRICS_NAMESPACE", "AWSInfrastructureManager")


def get_logger(name: Optional[str] = None) -> Logger:
    """Get a configured logger instance."""
    if name:
        return Logger(
            service=f"{settings.app_name}.{name}",
            level=settings.logging.level,
        )
    return logger


def get_tracer(name: Optional[str] = None) -> Tracer:
    """Get a configured tracer instance."""
    if name:
        return Tracer(
            service=f"{settings.app_name}.{name}",
            auto_patch=True,
        )
    return tracer


def get_metrics(namespace: Optional[str] = None) -> Metrics:
    """Get a configured metrics instance."""
    if namespace:
        return Metrics(
            service=settings.app_name,
            namespace=namespace,
        )
    return metrics


# Utility functions for common logging patterns
def log_api_request(endpoint: str, method: str, user_id: Optional[str] = None):
    """Log API request with structured data."""
    logger.info(
        "API request received",
        endpoint=endpoint,
        method=method,
        user_id=user_id,
    )


def log_api_response(endpoint: str, method: str, status_code: int, duration_ms: float):
    """Log API response with structured data."""
    logger.info(
        "API response sent",
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        duration_ms=duration_ms,
    )


def log_aws_operation(operation: str, resource_type: str, resource_id: str, project_id: str):
    """Log AWS operation with structured data."""
    logger.info(
        "AWS operation executed",
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
    )


def log_error(error: Exception, context: dict = None):
    """Log error with structured data and stack trace."""
    logger.exception(
        "Error occurred",
        error_type=type(error).__name__,
        error_message=str(error),
        context=context or {},
    )


def add_metric(name: str, value: float, unit: MetricUnit = MetricUnit.Count, **dimensions):
    """Add a custom metric."""
    metrics.add_metric(name=name, value=value, unit=unit)
    for key, val in dimensions.items():
        metrics.add_metadata(key=key, value=val)