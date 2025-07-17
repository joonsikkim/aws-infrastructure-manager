"""
FastAPI application factory and configuration.
"""
import os
import time
from typing import Callable
from datetime import datetime
from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit
from config.settings import settings
from config.environments import get_config
from config.logging import (
    configure_logging, 
    get_logger, 
    get_tracer, 
    get_metrics,
    log_api_request,
    log_api_response,
    add_metric
)

# Get environment-specific configuration
environment = os.environ.get("ENVIRONMENT", "development")
config = get_config(environment)

# Configure logging
configure_logging()
logger = get_logger(__name__)
tracer = get_tracer(__name__)
metrics = get_metrics()


@tracer.capture_method
def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title=config.app_name,
        version=config.app_version,
        description="AWS Infrastructure Management Service using MCP Server",
        docs_url="/docs" if config.api.debug else None,
        redoc_url="/redoc" if config.api.debug else None,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_credentials=True,
        allow_methods=config.api.cors_methods,
        allow_headers=config.api.cors_headers,
    )
    
    # Add request logging and tracing middleware
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next: Callable) -> Response:
        """Middleware for request logging and tracing."""
        start_time = time.time()
        
        # Extract correlation ID from headers
        correlation_id = request.headers.get("x-correlation-id")
        if correlation_id:
            logger.append_keys(correlation_id=correlation_id)
        
        # Log incoming request
        log_api_request(
            endpoint=str(request.url.path),
            method=request.method,
            user_id=request.headers.get("x-user-id")
        )
        
        # Add tracing annotations
        tracer.put_annotation(key="method", value=request.method)
        tracer.put_annotation(key="path", value=str(request.url.path))
        tracer.put_metadata(key="request_headers", value=dict(request.headers))
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log response
            log_api_response(
                endpoint=str(request.url.path),
                method=request.method,
                status_code=response.status_code,
                duration_ms=duration_ms
            )
            
            # Add metrics
            add_metric(
                name="APIRequest",
                value=1,
                unit=MetricUnit.Count,
                method=request.method,
                endpoint=str(request.url.path),
                status_code=str(response.status_code)
            )
            
            add_metric(
                name="APILatency",
                value=duration_ms,
                unit=MetricUnit.Milliseconds,
                method=request.method,
                endpoint=str(request.url.path)
            )
            
            # Add tracing metadata
            tracer.put_annotation(key="status_code", value=response.status_code)
            tracer.put_metadata(key="duration_ms", value=duration_ms)
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            logger.exception(
                "Request processing failed",
                endpoint=str(request.url.path),
                method=request.method,
                duration_ms=duration_ms,
                error=str(e)
            )
            
            # Add error metrics
            add_metric(
                name="APIError",
                value=1,
                unit=MetricUnit.Count,
                method=request.method,
                endpoint=str(request.url.path),
                error_type=type(e).__name__
            )
            
            # Add tracing error info
            tracer.put_annotation(key="error", value=True)
            tracer.put_metadata(key="error_message", value=str(e))
            
            raise
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        logger.info("Health check requested")
        
        health_data = {
            "status": "healthy",
            "app_name": config.app_name,
            "version": config.app_version,
            "environment": config.environment,
            "timestamp": time.time()
        }
        
        # Add health check metric
        add_metric(
            name="HealthCheck",
            value=1,
            unit=MetricUnit.Count,
            status="healthy"
        )
        
        return health_data
    
    # Metrics endpoint for CloudWatch integration
    @app.get("/metrics")
    async def get_metrics():
        """Get application metrics."""
        logger.info("Metrics requested")
        
        # This would typically return metrics in Prometheus format
        # For now, return basic application info
        return {
            "service": config.app_name,
            "version": config.app_version,
            "environment": config.environment,
            "metrics_namespace": "AWSInfrastructureManager"
        }
    
    # Global exception handler
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from src.models.exceptions import InfrastructureException
    from src.models.data_models import ErrorResponse
    import uuid
    
    @app.exception_handler(InfrastructureException)
    async def infrastructure_exception_handler(request: Request, exc: InfrastructureException):
        """Handle custom infrastructure exceptions"""
        request_id = str(uuid.uuid4())
        
        logger.error(
            "Infrastructure exception occurred",
            error_code=exc.code.value,
            error_message=exc.message,
            request_id=request_id,
            endpoint=str(request.url.path),
            method=request.method
        )
        
        error_response = ErrorResponse(
            code=exc.code.value,
            message=exc.message,
            timestamp=exc.timestamp,
            request_id=request_id,
            details=exc.details
        )
        
        # Convert datetime to string for JSON serialization
        response_dict = error_response.__dict__.copy()
        response_dict['timestamp'] = response_dict['timestamp'].isoformat()
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_dict
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions"""
        request_id = str(uuid.uuid4())
        
        logger.exception(
            "Unhandled exception occurred",
            error_type=type(exc).__name__,
            error_message=str(exc),
            request_id=request_id,
            endpoint=str(request.url.path),
            method=request.method
        )
        
        error_response = ErrorResponse(
            code="INTERNAL_SERVER_ERROR",
            message="An internal server error occurred",
            timestamp=datetime.now(),
            request_id=request_id
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.__dict__.copy()
        )
        response_dict['timestamp'] = response_dict['timestamp'].isoformat()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_dict
        )

    # Include API routers
    from src.api.auth import router as auth_router
    from src.api.projects import router as projects_router
    from src.api.resources import router as resources_router
    from src.api.plans import router as plans_router
    from src.api.dashboard import router as dashboard_router
    from src.api.views import router as views_router
    
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(resources_router)
    app.include_router(plans_router)
    app.include_router(dashboard_router)
    app.include_router(views_router)
    
    logger.info("FastAPI application created successfully")
    return app


# Create the application instance
app = create_app()