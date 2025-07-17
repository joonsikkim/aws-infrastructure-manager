"""
AWS MCP Client for communicating with AWS MCP Server
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import httpx
from contextlib import asynccontextmanager

from ..models.data_models import Resource, ResourceConfig, ResourceFilter
from ..models.enums import ResourceStatus
from ..models.exceptions import InfrastructureException, ErrorCodes


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    success_threshold: int = 3  # for half-open state


@dataclass
class RetryConfig:
    """Configuration for retry logic"""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class MCPRequest:
    """MCP protocol request structure"""
    jsonrpc: str = "2.0"
    id: str = field(default_factory=lambda: str(datetime.now().timestamp()))
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPResponse:
    """MCP protocol response structure"""
    jsonrpc: str
    id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class CircuitBreaker:
    """Circuit breaker implementation for AWS MCP client"""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.logger = logging.getLogger(__name__)
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                self.logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise InfrastructureException(
                    ErrorCodes.AWS_MCP_CONNECTION_FAILED,
                    "Circuit breaker is OPEN - too many failures"
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset"""
        if self.last_failure_time is None:
            return True
        
        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure.total_seconds() >= self.config.recovery_timeout
    
    def _on_success(self):
        """Handle successful operation"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.logger.info("Circuit breaker reset to CLOSED")
        else:
            self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.success_count = 0
            self.logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class RetryHandler:
    """Retry logic handler with exponential backoff"""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    async def execute_with_retry(self, func, *args, **kwargs):
        """Execute function with retry logic"""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt == self.config.max_retries:
                    self.logger.error(f"All retry attempts failed: {e}")
                    break
                
                delay = self._calculate_delay(attempt)
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s")
                await asyncio.sleep(delay)
        
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for exponential backoff"""
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)
        
        if self.config.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
        
        return delay


class AWSMCPClient:
    """Client for communicating with AWS MCP Server"""
    
    def __init__(
        self,
        server_url: str = "http://localhost:8080",
        timeout: int = 30,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        retry_config: Optional[RetryConfig] = None
    ):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        
        # Initialize circuit breaker and retry handler
        self.circuit_breaker = CircuitBreaker(
            circuit_breaker_config or CircuitBreakerConfig()
        )
        self.retry_handler = RetryHandler(
            retry_config or RetryConfig()
        )
        
        # HTTP client for MCP communication
        self._client: Optional[httpx.AsyncClient] = None
        self._connection_pool_size = 10
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
    
    async def connect(self):
        """Establish connection to AWS MCP Server"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=self._connection_pool_size)
            )
            self.logger.info(f"Connected to AWS MCP Server at {self.server_url}")
    
    async def disconnect(self):
        """Close connection to AWS MCP Server"""
        if self._client:
            await self._client.aclose()
            self._client = None
            self.logger.info("Disconnected from AWS MCP Server")
    
    async def _send_request(self, request: MCPRequest) -> MCPResponse:
        """Send MCP request to server"""
        if not self._client:
            await self.connect()
        
        try:
            response = await self._client.post(
                f"{self.server_url}/mcp",
                json=request.__dict__,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            response_data = response.json()
            mcp_response = MCPResponse(**response_data)
            
            if mcp_response.error:
                raise InfrastructureException(
                    ErrorCodes.AWS_MCP_CONNECTION_FAILED,
                    f"MCP Server error: {mcp_response.error}"
                )
            
            return mcp_response
            
        except httpx.HTTPError as e:
            raise InfrastructureException(
                ErrorCodes.AWS_MCP_CONNECTION_FAILED,
                f"HTTP error communicating with MCP server: {e}"
            )
        except json.JSONDecodeError as e:
            raise InfrastructureException(
                ErrorCodes.AWS_MCP_CONNECTION_FAILED,
                f"Invalid JSON response from MCP server: {e}"
            )
    
    async def _execute_with_resilience(self, func, *args, **kwargs):
        """Execute function with circuit breaker and retry logic"""
        return await self.circuit_breaker.call(
            self.retry_handler.execute_with_retry,
            func, *args, **kwargs
        )
    
    # AWS Resource CRUD Operations
    
    async def create_resource(
        self,
        project_id: str,
        resource_config: ResourceConfig
    ) -> Resource:
        """Create AWS resource via MCP server"""
        
        async def _create():
            request = MCPRequest(
                method="aws.create_resource",
                params={
                    "project_id": project_id,
                    "resource_type": resource_config.type,
                    "resource_name": resource_config.name,
                    "properties": resource_config.properties,
                    "tags": resource_config.tags or {}
                }
            )
            
            response = await self._send_request(request)
            return self._parse_resource_response(response.result, project_id)
        
        return await self._execute_with_resilience(_create)
    
    async def get_resource(
        self,
        project_id: str,
        resource_id: str
    ) -> Optional[Resource]:
        """Get specific AWS resource via MCP server"""
        
        async def _get():
            request = MCPRequest(
                method="aws.get_resource",
                params={
                    "project_id": project_id,
                    "resource_id": resource_id
                }
            )
            
            response = await self._send_request(request)
            if not response.result:
                return None
            
            return self._parse_resource_response(response.result, project_id)
        
        return await self._execute_with_resilience(_get)
    
    async def list_resources(
        self,
        project_id: str,
        filters: Optional[ResourceFilter] = None
    ) -> List[Resource]:
        """List AWS resources via MCP server"""
        
        async def _list():
            params = {"project_id": project_id}
            
            if filters:
                if filters.resource_type:
                    params["resource_type"] = filters.resource_type
                if filters.status:
                    params["status"] = filters.status.value
                if filters.tags:
                    params["tags"] = filters.tags
                if filters.region:
                    params["region"] = filters.region
            
            request = MCPRequest(
                method="aws.list_resources",
                params=params
            )
            
            response = await self._send_request(request)
            resources = []
            
            if response.result and "resources" in response.result:
                for resource_data in response.result["resources"]:
                    resources.append(
                        self._parse_resource_response(resource_data, project_id)
                    )
            
            return resources
        
        return await self._execute_with_resilience(_list)
    
    async def update_resource(
        self,
        project_id: str,
        resource_id: str,
        updates: Dict[str, Any]
    ) -> Resource:
        """Update AWS resource via MCP server"""
        
        async def _update():
            request = MCPRequest(
                method="aws.update_resource",
                params={
                    "project_id": project_id,
                    "resource_id": resource_id,
                    "updates": updates
                }
            )
            
            response = await self._send_request(request)
            return self._parse_resource_response(response.result, project_id)
        
        return await self._execute_with_resilience(_update)
    
    async def delete_resource(
        self,
        project_id: str,
        resource_id: str
    ) -> bool:
        """Delete AWS resource via MCP server"""
        
        async def _delete():
            request = MCPRequest(
                method="aws.delete_resource",
                params={
                    "project_id": project_id,
                    "resource_id": resource_id
                }
            )
            
            response = await self._send_request(request)
            return response.result.get("success", False) if response.result else False
        
        return await self._execute_with_resilience(_delete)
    
    async def get_resource_status(
        self,
        project_id: str,
        resource_id: str
    ) -> ResourceStatus:
        """Get current status of AWS resource"""
        
        async def _get_status():
            request = MCPRequest(
                method="aws.get_resource_status",
                params={
                    "project_id": project_id,
                    "resource_id": resource_id
                }
            )
            
            response = await self._send_request(request)
            status_str = response.result.get("status") if response.result else "ERROR"
            
            try:
                return ResourceStatus(status_str.lower())
            except ValueError:
                return ResourceStatus.ERROR
        
        return await self._execute_with_resilience(_get_status)
    
    def _parse_resource_response(self, data: Dict[str, Any], project_id: str) -> Resource:
        """Parse MCP server response into Resource object"""
        try:
            return Resource(
                id=data["id"],
                project_id=project_id,
                type=data["type"],
                name=data["name"],
                region=data.get("region", "us-east-1"),
                properties=data.get("properties", {}),
                tags=data.get("tags", {}),
                status=ResourceStatus(data.get("status", "error").lower()),
                created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
                updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
                arn=data.get("arn")
            )
        except (KeyError, ValueError) as e:
            raise InfrastructureException(
                ErrorCodes.AWS_MCP_CONNECTION_FAILED,
                f"Invalid resource data from MCP server: {e}"
            )
    
    # Health check and diagnostics
    
    async def health_check(self) -> bool:
        """Check if MCP server is healthy"""
        try:
            request = MCPRequest(method="health.check")
            response = await self._send_request(request)
            return response.result.get("status") == "healthy" if response.result else False
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False
    
    async def get_server_info(self) -> Dict[str, Any]:
        """Get MCP server information"""
        request = MCPRequest(method="server.info")
        response = await self._send_request(request)
        return response.result or {}


# Factory function for creating MCP client
def create_aws_mcp_client(
    server_url: str,
    timeout: int = 30,
    max_retries: int = 3,
    circuit_breaker_threshold: int = 5
) -> AWSMCPClient:
    """Factory function to create AWS MCP client with default configuration"""
    
    circuit_breaker_config = CircuitBreakerConfig(
        failure_threshold=circuit_breaker_threshold,
        recovery_timeout=60,
        success_threshold=3
    )
    
    retry_config = RetryConfig(
        max_retries=max_retries,
        base_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0,
        jitter=True
    )
    
    return AWSMCPClient(
        server_url=server_url,
        timeout=timeout,
        circuit_breaker_config=circuit_breaker_config,
        retry_config=retry_config
    )