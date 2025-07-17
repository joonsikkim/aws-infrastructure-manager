"""
AWS Lambda Powertools utilities and decorators for the AWS Infrastructure Manager.
"""
import functools
import time
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from config.logging import get_logger, get_tracer, get_metrics, log_error, add_metric

F = TypeVar('F', bound=Callable[..., Any])

# Global instances
logger = get_logger(__name__)
tracer = get_tracer(__name__)
metrics = get_metrics()


def trace_aws_operation(operation_name: str, resource_type: str = None):
    """
    Decorator to trace AWS operations with structured logging and metrics.
    
    Args:
        operation_name: Name of the AWS operation (e.g., 'create_ec2_instance')
        resource_type: Type of AWS resource (e.g., 'EC2::Instance')
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Extract project_id and resource_id from kwargs if available
            project_id = kwargs.get('project_id', 'unknown')
            resource_id = kwargs.get('resource_id', 'unknown')
            
            # Start tracing
            with tracer.provider.get_tracer(__name__).start_as_current_span(operation_name) as span:
                span.set_attribute("operation.name", operation_name)
                span.set_attribute("project.id", project_id)
                if resource_type:
                    span.set_attribute("resource.type", resource_type)
                if resource_id != 'unknown':
                    span.set_attribute("resource.id", resource_id)
                
                logger.info(
                    f"Starting AWS operation: {operation_name}",
                    operation=operation_name,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    project_id=project_id
                )
                
                try:
                    result = await func(*args, **kwargs)
                    
                    duration_ms = (time.time() - start_time) * 1000
                    
                    logger.info(
                        f"AWS operation completed: {operation_name}",
                        operation=operation_name,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        project_id=project_id,
                        duration_ms=duration_ms,
                        success=True
                    )
                    
                    # Add success metrics
                    add_metric(
                        name="AWSOperationSuccess",
                        value=1,
                        unit=MetricUnit.Count,
                        operation=operation_name,
                        resource_type=resource_type or "unknown",
                        project_id=project_id
                    )
                    
                    add_metric(
                        name="AWSOperationDuration",
                        value=duration_ms,
                        unit=MetricUnit.Milliseconds,
                        operation=operation_name,
                        resource_type=resource_type or "unknown"
                    )
                    
                    span.set_attribute("operation.success", True)
                    span.set_attribute("operation.duration_ms", duration_ms)
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    
                    log_error(
                        e,
                        context={
                            "operation": operation_name,
                            "resource_type": resource_type,
                            "resource_id": resource_id,
                            "project_id": project_id,
                            "duration_ms": duration_ms
                        }
                    )
                    
                    # Add error metrics
                    add_metric(
                        name="AWSOperationError",
                        value=1,
                        unit=MetricUnit.Count,
                        operation=operation_name,
                        resource_type=resource_type or "unknown",
                        error_type=type(e).__name__,
                        project_id=project_id
                    )
                    
                    span.set_attribute("operation.success", False)
                    span.set_attribute("operation.error", str(e))
                    span.set_attribute("operation.error_type", type(e).__name__)
                    
                    raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Extract project_id and resource_id from kwargs if available
            project_id = kwargs.get('project_id', 'unknown')
            resource_id = kwargs.get('resource_id', 'unknown')
            
            # Start tracing
            with tracer.provider.get_tracer(__name__).start_as_current_span(operation_name) as span:
                span.set_attribute("operation.name", operation_name)
                span.set_attribute("project.id", project_id)
                if resource_type:
                    span.set_attribute("resource.type", resource_type)
                if resource_id != 'unknown':
                    span.set_attribute("resource.id", resource_id)
                
                logger.info(
                    f"Starting AWS operation: {operation_name}",
                    operation=operation_name,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    project_id=project_id
                )
                
                try:
                    result = func(*args, **kwargs)
                    
                    duration_ms = (time.time() - start_time) * 1000
                    
                    logger.info(
                        f"AWS operation completed: {operation_name}",
                        operation=operation_name,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        project_id=project_id,
                        duration_ms=duration_ms,
                        success=True
                    )
                    
                    # Add success metrics
                    add_metric(
                        name="AWSOperationSuccess",
                        value=1,
                        unit=MetricUnit.Count,
                        operation=operation_name,
                        resource_type=resource_type or "unknown",
                        project_id=project_id
                    )
                    
                    add_metric(
                        name="AWSOperationDuration",
                        value=duration_ms,
                        unit=MetricUnit.Milliseconds,
                        operation=operation_name,
                        resource_type=resource_type or "unknown"
                    )
                    
                    span.set_attribute("operation.success", True)
                    span.set_attribute("operation.duration_ms", duration_ms)
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    
                    log_error(
                        e,
                        context={
                            "operation": operation_name,
                            "resource_type": resource_type,
                            "resource_id": resource_id,
                            "project_id": project_id,
                            "duration_ms": duration_ms
                        }
                    )
                    
                    # Add error metrics
                    add_metric(
                        name="AWSOperationError",
                        value=1,
                        unit=MetricUnit.Count,
                        operation=operation_name,
                        resource_type=resource_type or "unknown",
                        error_type=type(e).__name__,
                        project_id=project_id
                    )
                    
                    span.set_attribute("operation.success", False)
                    span.set_attribute("operation.error", str(e))
                    span.set_attribute("operation.error_type", type(e).__name__)
                    
                    raise
        
        # Return appropriate wrapper based on function type
        if hasattr(func, '__code__') and 'async' in str(func.__code__.co_flags):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def trace_service_method(service_name: str, method_name: str = None):
    """
    Decorator to trace service methods with structured logging and metrics.
    
    Args:
        service_name: Name of the service (e.g., 'InfrastructureService')
        method_name: Name of the method (optional, will use function name if not provided)
    """
    def decorator(func: F) -> F:
        operation_name = method_name or func.__name__
        full_operation_name = f"{service_name}.{operation_name}"
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            
            with tracer.provider.get_tracer(__name__).start_as_current_span(full_operation_name) as span:
                span.set_attribute("service.name", service_name)
                span.set_attribute("method.name", operation_name)
                
                logger.info(
                    f"Starting service method: {full_operation_name}",
                    service=service_name,
                    method=operation_name
                )
                
                try:
                    result = await func(*args, **kwargs)
                    
                    duration_ms = (time.time() - start_time) * 1000
                    
                    logger.info(
                        f"Service method completed: {full_operation_name}",
                        service=service_name,
                        method=operation_name,
                        duration_ms=duration_ms,
                        success=True
                    )
                    
                    # Add success metrics
                    add_metric(
                        name="ServiceMethodSuccess",
                        value=1,
                        unit=MetricUnit.Count,
                        service=service_name,
                        method=operation_name
                    )
                    
                    add_metric(
                        name="ServiceMethodDuration",
                        value=duration_ms,
                        unit=MetricUnit.Milliseconds,
                        service=service_name,
                        method=operation_name
                    )
                    
                    span.set_attribute("method.success", True)
                    span.set_attribute("method.duration_ms", duration_ms)
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    
                    log_error(
                        e,
                        context={
                            "service": service_name,
                            "method": operation_name,
                            "duration_ms": duration_ms
                        }
                    )
                    
                    # Add error metrics
                    add_metric(
                        name="ServiceMethodError",
                        value=1,
                        unit=MetricUnit.Count,
                        service=service_name,
                        method=operation_name,
                        error_type=type(e).__name__
                    )
                    
                    span.set_attribute("method.success", False)
                    span.set_attribute("method.error", str(e))
                    span.set_attribute("method.error_type", type(e).__name__)
                    
                    raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            
            with tracer.provider.get_tracer(__name__).start_as_current_span(full_operation_name) as span:
                span.set_attribute("service.name", service_name)
                span.set_attribute("method.name", operation_name)
                
                logger.info(
                    f"Starting service method: {full_operation_name}",
                    service=service_name,
                    method=operation_name
                )
                
                try:
                    result = func(*args, **kwargs)
                    
                    duration_ms = (time.time() - start_time) * 1000
                    
                    logger.info(
                        f"Service method completed: {full_operation_name}",
                        service=service_name,
                        method=operation_name,
                        duration_ms=duration_ms,
                        success=True
                    )
                    
                    # Add success metrics
                    add_metric(
                        name="ServiceMethodSuccess",
                        value=1,
                        unit=MetricUnit.Count,
                        service=service_name,
                        method=operation_name
                    )
                    
                    add_metric(
                        name="ServiceMethodDuration",
                        value=duration_ms,
                        unit=MetricUnit.Milliseconds,
                        service=service_name,
                        method=operation_name
                    )
                    
                    span.set_attribute("method.success", True)
                    span.set_attribute("method.duration_ms", duration_ms)
                    
                    return result
                    
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    
                    log_error(
                        e,
                        context={
                            "service": service_name,
                            "method": operation_name,
                            "duration_ms": duration_ms
                        }
                    )
                    
                    # Add error metrics
                    add_metric(
                        name="ServiceMethodError",
                        value=1,
                        unit=MetricUnit.Count,
                        service=service_name,
                        method=operation_name,
                        error_type=type(e).__name__
                    )
                    
                    span.set_attribute("method.success", False)
                    span.set_attribute("method.error", str(e))
                    span.set_attribute("method.error_type", type(e).__name__)
                    
                    raise
        
        # Return appropriate wrapper based on function type
        if hasattr(func, '__code__') and 'async' in str(func.__code__.co_flags):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def lambda_handler_with_powertools(
    logger_instance: Logger = None,
    tracer_instance: Tracer = None,
    metrics_instance: Metrics = None
):
    """
    Decorator for Lambda handlers that automatically applies Powertools decorators.
    
    Args:
        logger_instance: Custom logger instance
        tracer_instance: Custom tracer instance  
        metrics_instance: Custom metrics instance
    """
    def decorator(func: F) -> F:
        # Use provided instances or defaults
        _logger = logger_instance or logger
        _tracer = tracer_instance or tracer
        _metrics = metrics_instance or metrics
        
        # Apply Powertools decorators
        decorated_func = _logger.inject_lambda_context(
            _tracer.capture_lambda_handler(
                _metrics.log_metrics(func)
            )
        )
        
        return decorated_func
    
    return decorator


class PowertoolsContext:
    """Context manager for Powertools operations."""
    
    def __init__(self, operation_name: str, **metadata):
        self.operation_name = operation_name
        self.metadata = metadata
        self.start_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"Starting operation: {self.operation_name}", **self.metadata)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        
        if exc_type is None:
            logger.info(
                f"Operation completed: {self.operation_name}",
                duration_ms=duration_ms,
                success=True,
                **self.metadata
            )
            add_metric(
                name="OperationSuccess",
                value=1,
                unit=MetricUnit.Count,
                operation=self.operation_name
            )
        else:
            logger.exception(
                f"Operation failed: {self.operation_name}",
                duration_ms=duration_ms,
                success=False,
                error_type=exc_type.__name__,
                error_message=str(exc_val),
                **self.metadata
            )
            add_metric(
                name="OperationError",
                value=1,
                unit=MetricUnit.Count,
                operation=self.operation_name,
                error_type=exc_type.__name__
            )