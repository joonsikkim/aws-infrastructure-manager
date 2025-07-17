"""
Unit tests for AWS MCP Client
"""
import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
import httpx

from src.services.aws_mcp_client import (
    AWSMCPClient, CircuitBreaker, RetryHandler, CircuitBreakerState,
    CircuitBreakerConfig, RetryConfig, MCPRequest, MCPResponse,
    create_aws_mcp_client
)
from src.models.data_models import Resource, ResourceConfig, ResourceFilter
from src.models.enums import ResourceStatus
from src.models.exceptions import InfrastructureException, ErrorCodes


class TestCircuitBreaker:
    """Test circuit breaker functionality"""
    
    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in CLOSED state"""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(config)
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_success(self):
        """Test circuit breaker handles successful calls"""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(config)
        
        async def success_func():
            return "success"
        
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self):
        """Test circuit breaker opens after threshold failures"""
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker(config)
        
        async def failing_func():
            raise Exception("Test failure")
        
        # First failure
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 1
        
        # Second failure - should open circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.failure_count == 2
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(self):
        """Test circuit breaker blocks calls when open"""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=3600)
        cb = CircuitBreaker(config)
        
        async def failing_func():
            raise Exception("Test failure")
        
        # Trigger circuit breaker to open
        with pytest.raises(Exception):
            await cb.call(failing_func)
        
        # Should now block calls
        with pytest.raises(InfrastructureException) as exc_info:
            await cb.call(failing_func)
        
        assert exc_info.value.code == ErrorCodes.AWS_MCP_CONNECTION_FAILED
        assert "Circuit breaker is OPEN" in str(exc_info.value)


class TestRetryHandler:
    """Test retry handler functionality"""
    
    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """Test retry handler succeeds on first attempt"""
        config = RetryConfig(max_retries=3)
        retry_handler = RetryHandler(config)
        
        async def success_func():
            return "success"
        
        result = await retry_handler.execute_with_retry(success_func)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test retry handler succeeds after some failures"""
        config = RetryConfig(max_retries=3, base_delay=0.01)
        retry_handler = RetryHandler(config)
        
        call_count = 0
        
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"
        
        result = await retry_handler.execute_with_retry(flaky_func)
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhausts_attempts(self):
        """Test retry handler exhausts all attempts"""
        config = RetryConfig(max_retries=2, base_delay=0.01)
        retry_handler = RetryHandler(config)
        
        call_count = 0
        
        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Always fails")
        
        with pytest.raises(Exception, match="Always fails"):
            await retry_handler.execute_with_retry(always_failing_func)
        
        assert call_count == 3  # Initial attempt + 2 retries


class TestAWSMCPClient:
    """Test AWS MCP Client functionality"""
    
    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx client"""
        mock_client = AsyncMock()
        return mock_client
    
    @pytest.fixture
    def mcp_client(self):
        """Create MCP client for testing"""
        return AWSMCPClient(
            server_url="http://localhost:8000",
            timeout=10
        )
    
    @pytest.mark.asyncio
    async def test_client_connection(self, mcp_client):
        """Test client connection management"""
        assert mcp_client._client is None
        
        await mcp_client.connect()
        assert mcp_client._client is not None
        
        await mcp_client.disconnect()
        assert mcp_client._client is None
    
    @pytest.mark.asyncio
    async def test_context_manager(self, mcp_client):
        """Test client as async context manager"""
        async with mcp_client as client:
            assert client._client is not None
        
        assert mcp_client._client is None
    
    @pytest.mark.asyncio
    async def test_send_request_success(self, mcp_client, mock_httpx_client):
        """Test successful MCP request"""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {"status": "success"}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        request = MCPRequest(method="test.method", params={"key": "value"})
        response = await mcp_client._send_request(request)
        
        assert response.jsonrpc == "2.0"
        assert response.id == "test-id"
        assert response.result == {"status": "success"}
        assert response.error is None
    
    @pytest.mark.asyncio
    async def test_send_request_mcp_error(self, mcp_client, mock_httpx_client):
        """Test MCP request with server error"""
        # Mock response with error
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "error": {"code": -1, "message": "Server error"}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        request = MCPRequest(method="test.method")
        
        with pytest.raises(InfrastructureException) as exc_info:
            await mcp_client._send_request(request)
        
        assert exc_info.value.code == ErrorCodes.AWS_MCP_CONNECTION_FAILED
        assert "MCP Server error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_send_request_http_error(self, mcp_client, mock_httpx_client):
        """Test MCP request with HTTP error"""
        mock_httpx_client.post.side_effect = httpx.HTTPError("Connection failed")
        mcp_client._client = mock_httpx_client
        
        request = MCPRequest(method="test.method")
        
        with pytest.raises(InfrastructureException) as exc_info:
            await mcp_client._send_request(request)
        
        assert exc_info.value.code == ErrorCodes.AWS_MCP_CONNECTION_FAILED
        assert "HTTP error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_resource(self, mcp_client, mock_httpx_client):
        """Test resource creation"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {
                "id": "i-1234567890abcdef0",
                "type": "EC2::Instance",
                "name": "test-instance",
                "region": "us-east-1",
                "properties": {"instanceType": "t3.micro"},
                "tags": {"Environment": "test"},
                "status": "creating",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        resource_config = ResourceConfig(
            type="EC2::Instance",
            name="test-instance",
            properties={"instanceType": "t3.micro"},
            tags={"Environment": "test"}
        )
        
        resource = await mcp_client.create_resource("project-123", resource_config)
        
        assert resource.id == "i-1234567890abcdef0"
        assert resource.project_id == "project-123"
        assert resource.type == "EC2::Instance"
        assert resource.name == "test-instance"
        assert resource.status == ResourceStatus.CREATING
    
    @pytest.mark.asyncio
    async def test_get_resource(self, mcp_client, mock_httpx_client):
        """Test resource retrieval"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {
                "id": "i-1234567890abcdef0",
                "type": "EC2::Instance",
                "name": "test-instance",
                "region": "us-east-1",
                "properties": {"instanceType": "t3.micro"},
                "tags": {"Environment": "test"},
                "status": "active",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:00:00Z"
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        resource = await mcp_client.get_resource("project-123", "i-1234567890abcdef0")
        
        assert resource is not None
        assert resource.id == "i-1234567890abcdef0"
        assert resource.status == ResourceStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_get_resource_not_found(self, mcp_client, mock_httpx_client):
        """Test resource retrieval when not found"""
        # Mock empty response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": None
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        resource = await mcp_client.get_resource("project-123", "nonexistent")
        assert resource is None
    
    @pytest.mark.asyncio
    async def test_list_resources(self, mcp_client, mock_httpx_client):
        """Test resource listing"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {
                "resources": [
                    {
                        "id": "i-1234567890abcdef0",
                        "type": "EC2::Instance",
                        "name": "test-instance-1",
                        "region": "us-east-1",
                        "properties": {"instanceType": "t3.micro"},
                        "tags": {"Environment": "test"},
                        "status": "active",
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-01-15T10:00:00Z"
                    },
                    {
                        "id": "i-0987654321fedcba0",
                        "type": "EC2::Instance",
                        "name": "test-instance-2",
                        "region": "us-east-1",
                        "properties": {"instanceType": "t3.small"},
                        "tags": {"Environment": "test"},
                        "status": "active",
                        "created_at": "2024-01-15T10:00:00Z",
                        "updated_at": "2024-01-15T10:00:00Z"
                    }
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        resources = await mcp_client.list_resources("project-123")
        
        assert len(resources) == 2
        assert resources[0].id == "i-1234567890abcdef0"
        assert resources[1].id == "i-0987654321fedcba0"
    
    @pytest.mark.asyncio
    async def test_list_resources_with_filters(self, mcp_client, mock_httpx_client):
        """Test resource listing with filters"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {"resources": []}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        filters = ResourceFilter(
            resource_type="EC2::Instance",
            status=ResourceStatus.ACTIVE,
            region="us-east-1",
            tags={"Environment": "production"}
        )
        
        await mcp_client.list_resources("project-123", filters)
        
        # Verify the request was made with correct parameters
        call_args = mock_httpx_client.post.call_args
        request_data = call_args[1]["json"]
        
        assert request_data["method"] == "aws.list_resources"
        assert request_data["params"]["project_id"] == "project-123"
        assert request_data["params"]["resource_type"] == "EC2::Instance"
        assert request_data["params"]["status"] == "active"
        assert request_data["params"]["region"] == "us-east-1"
        assert request_data["params"]["tags"] == {"Environment": "production"}
    
    @pytest.mark.asyncio
    async def test_update_resource(self, mcp_client, mock_httpx_client):
        """Test resource update"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {
                "id": "i-1234567890abcdef0",
                "type": "EC2::Instance",
                "name": "test-instance",
                "region": "us-east-1",
                "properties": {"instanceType": "t3.small"},  # Updated
                "tags": {"Environment": "test"},
                "status": "updating",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        updates = {"instanceType": "t3.small"}
        resource = await mcp_client.update_resource("project-123", "i-1234567890abcdef0", updates)
        
        assert resource.properties["instanceType"] == "t3.small"
        assert resource.status == ResourceStatus.UPDATING
    
    @pytest.mark.asyncio
    async def test_delete_resource(self, mcp_client, mock_httpx_client):
        """Test resource deletion"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {"success": True}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        result = await mcp_client.delete_resource("project-123", "i-1234567890abcdef0")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_resource_status(self, mcp_client, mock_httpx_client):
        """Test resource status retrieval"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {"status": "active"}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        status = await mcp_client.get_resource_status("project-123", "i-1234567890abcdef0")
        assert status == ResourceStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_health_check(self, mcp_client, mock_httpx_client):
        """Test health check"""
        # Mock successful response
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "test-id",
            "result": {"status": "healthy"}
        }
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response
        
        mcp_client._client = mock_httpx_client
        
        is_healthy = await mcp_client.health_check()
        assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, mcp_client, mock_httpx_client):
        """Test health check failure"""
        mock_httpx_client.post.side_effect = Exception("Connection failed")
        mcp_client._client = mock_httpx_client
        
        is_healthy = await mcp_client.health_check()
        assert is_healthy is False


def test_create_aws_mcp_client():
    """Test factory function for creating MCP client"""
    client = create_aws_mcp_client(
        server_url="http://localhost:8000",
        timeout=60,
        max_retries=5,
        circuit_breaker_threshold=10
    )
    
    assert client.server_url == "http://localhost:8000"
    assert client.timeout == 60
    assert client.retry_handler.config.max_retries == 5
    assert client.circuit_breaker.config.failure_threshold == 10


def test_mcp_request_dataclass():
    """Test MCP request dataclass"""
    request = MCPRequest(method="test.method", params={"key": "value"})
    
    assert request.jsonrpc == "2.0"
    assert request.method == "test.method"
    assert request.params == {"key": "value"}
    assert request.id is not None


def test_mcp_response_dataclass():
    """Test MCP response dataclass"""
    response = MCPResponse(
        jsonrpc="2.0",
        id="test-id",
        result={"status": "success"}
    )
    
    assert response.jsonrpc == "2.0"
    assert response.id == "test-id"
    assert response.result == {"status": "success"}
    assert response.error is None