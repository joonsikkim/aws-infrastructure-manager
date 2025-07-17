# AWS MCP Client Documentation

## Overview

The AWS MCP Client is a robust, production-ready client for communicating with AWS MCP (Model Context Protocol) servers. It provides comprehensive AWS resource management capabilities with built-in resilience patterns including circuit breakers, retry logic, and connection management.

## Features

- **Resilient Communication**: Built-in circuit breaker and exponential backoff retry logic
- **Connection Management**: Efficient HTTP connection pooling and lifecycle management
- **Comprehensive CRUD Operations**: Full support for AWS resource creation, reading, updating, and deletion
- **Type Safety**: Full type annotations and dataclass-based request/response handling
- **Async/Await Support**: Modern Python async/await patterns throughout
- **Configurable**: Extensive configuration options for different deployment scenarios
- **Monitoring**: Built-in health checks and server information retrieval

## Architecture

### Core Components

1. **AWSMCPClient**: Main client class for AWS MCP server communication
2. **CircuitBreaker**: Implements circuit breaker pattern for fault tolerance
3. **RetryHandler**: Handles exponential backoff retry logic with jitter
4. **MCPRequest/MCPResponse**: Type-safe MCP protocol message structures

### Resilience Patterns

#### Circuit Breaker
- **States**: CLOSED, OPEN, HALF_OPEN
- **Failure Threshold**: Configurable number of failures before opening
- **Recovery Timeout**: Time to wait before attempting recovery
- **Success Threshold**: Number of successes needed to close circuit

#### Retry Logic
- **Exponential Backoff**: Configurable base delay and multiplier
- **Jitter**: Optional randomization to prevent thundering herd
- **Max Delay**: Configurable maximum delay between retries
- **Max Retries**: Configurable maximum number of retry attempts

## Usage

### Basic Usage

```python
import asyncio
from src.services.aws_mcp_client import create_aws_mcp_client
from src.models.data_models import ResourceConfig

async def main():
    # Create client with default configuration
    client = create_aws_mcp_client("http://localhost:8000")
    
    async with client:
        # Create a resource
        config = ResourceConfig(
            type="EC2::Instance",
            name="my-instance",
            properties={"instanceType": "t3.micro"},
            tags={"Environment": "dev"}
        )
        
        resource = await client.create_resource("project-123", config)
        print(f"Created: {resource.id}")

asyncio.run(main())
```

### Advanced Configuration

```python
from src.services.aws_mcp_client import (
    AWSMCPClient, CircuitBreakerConfig, RetryConfig
)

# Custom circuit breaker configuration
cb_config = CircuitBreakerConfig(
    failure_threshold=10,
    recovery_timeout=120,
    success_threshold=5
)

# Custom retry configuration
retry_config = RetryConfig(
    max_retries=5,
    base_delay=2.0,
    max_delay=120.0,
    exponential_base=2.5,
    jitter=True
)

# Create client with custom configuration
client = AWSMCPClient(
    server_url="https://aws-mcp.example.com",
    timeout=60,
    circuit_breaker_config=cb_config,
    retry_config=retry_config
)
```

### Environment-Based Configuration

```python
from config.aws_mcp_config import get_aws_mcp_config
from src.services.aws_mcp_client import AWSMCPClient

# Load configuration from environment variables
config = get_aws_mcp_config()

client = AWSMCPClient(
    server_url=config.server_url,
    timeout=config.timeout
)
```

## API Reference

### AWSMCPClient

#### Constructor Parameters

- `server_url` (str): URL of the AWS MCP server
- `timeout` (int): Request timeout in seconds (default: 30)
- `circuit_breaker_config` (CircuitBreakerConfig, optional): Circuit breaker configuration
- `retry_config` (RetryConfig, optional): Retry logic configuration

#### Methods

##### Resource Management

```python
async def create_resource(
    self, 
    project_id: str, 
    resource_config: ResourceConfig
) -> Resource
```
Create a new AWS resource.

```python
async def get_resource(
    self, 
    project_id: str, 
    resource_id: str
) -> Optional[Resource]
```
Retrieve a specific AWS resource.

```python
async def list_resources(
    self, 
    project_id: str, 
    filters: Optional[ResourceFilter] = None
) -> List[Resource]
```
List AWS resources with optional filtering.

```python
async def update_resource(
    self, 
    project_id: str, 
    resource_id: str, 
    updates: Dict[str, Any]
) -> Resource
```
Update an existing AWS resource.

```python
async def delete_resource(
    self, 
    project_id: str, 
    resource_id: str
) -> bool
```
Delete an AWS resource.

```python
async def get_resource_status(
    self, 
    project_id: str, 
    resource_id: str
) -> ResourceStatus
```
Get the current status of an AWS resource.

##### Health and Diagnostics

```python
async def health_check(self) -> bool
```
Check if the MCP server is healthy.

```python
async def get_server_info(self) -> Dict[str, Any]
```
Get information about the MCP server.

##### Connection Management

```python
async def connect(self) -> None
```
Establish connection to the MCP server.

```python
async def disconnect(self) -> None
```
Close connection to the MCP server.

### Configuration Classes

#### CircuitBreakerConfig

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    success_threshold: int = 3
```

#### RetryConfig

```python
@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
```

## Error Handling

The client raises `InfrastructureException` for various error conditions:

- `AWS_MCP_CONNECTION_FAILED`: Connection or communication errors
- `RESOURCE_NOT_FOUND`: Requested resource doesn't exist
- `VALIDATION_FAILED`: Invalid request parameters

### Example Error Handling

```python
from src.models.exceptions import InfrastructureException, ErrorCodes

try:
    resource = await client.get_resource("project-123", "nonexistent-id")
except InfrastructureException as e:
    if e.code == ErrorCodes.RESOURCE_NOT_FOUND:
        print("Resource not found")
    elif e.code == ErrorCodes.AWS_MCP_CONNECTION_FAILED:
        print("Connection failed")
    else:
        print(f"Unexpected error: {e}")
```

## Environment Variables

Configure the client using environment variables:

```bash
# Server connection
AWS_MCP_SERVER_URL=http://localhost:8000
AWS_MCP_TIMEOUT=30
AWS_MCP_POOL_SIZE=10

# Retry configuration
AWS_MCP_MAX_RETRIES=3
AWS_MCP_BASE_DELAY=1.0
AWS_MCP_MAX_DELAY=60.0
AWS_MCP_EXPONENTIAL_BASE=2.0
AWS_MCP_ENABLE_JITTER=true

# Circuit breaker configuration
AWS_MCP_CB_FAILURE_THRESHOLD=5
AWS_MCP_CB_RECOVERY_TIMEOUT=60
AWS_MCP_CB_SUCCESS_THRESHOLD=3

# Logging configuration
AWS_MCP_DEBUG_LOGGING=false
AWS_MCP_LOG_REQUESTS=false
AWS_MCP_LOG_RESPONSES=false
```

## Testing

The client includes comprehensive unit tests covering:

- Circuit breaker functionality
- Retry logic with exponential backoff
- Resource CRUD operations
- Error handling scenarios
- Connection management

Run tests with:

```bash
python -m pytest tests/test_aws_mcp_client.py -v
```

## Best Practices

### 1. Use Context Manager

Always use the client as an async context manager to ensure proper connection cleanup:

```python
async with client:
    # Perform operations
    pass
```

### 2. Configure Timeouts Appropriately

Set timeouts based on your expected operation duration:

```python
# For long-running operations
client = AWSMCPClient(server_url="...", timeout=300)
```

### 3. Monitor Circuit Breaker State

Log circuit breaker state changes for monitoring:

```python
import logging
logging.basicConfig(level=logging.INFO)

# Circuit breaker state changes will be logged automatically
```

### 4. Handle Specific Exceptions

Handle specific error codes for better user experience:

```python
try:
    await client.create_resource(project_id, config)
except InfrastructureException as e:
    if e.code == ErrorCodes.AWS_MCP_CONNECTION_FAILED:
        # Retry later or use fallback
        pass
    else:
        # Handle other errors
        raise
```

### 5. Use Resource Filters

Use filters to reduce network traffic and improve performance:

```python
filters = ResourceFilter(
    resource_type="EC2::Instance",
    status=ResourceStatus.ACTIVE,
    region="us-east-1"
)
resources = await client.list_resources(project_id, filters)
```

## Performance Considerations

- **Connection Pooling**: The client uses connection pooling to reduce overhead
- **Circuit Breaker**: Prevents cascading failures and reduces load on failing servers
- **Retry Logic**: Exponential backoff with jitter prevents thundering herd problems
- **Async Operations**: All operations are async for better concurrency

## Security Considerations

- **HTTPS**: Always use HTTPS in production environments
- **Authentication**: Implement proper authentication mechanisms
- **Input Validation**: Validate all input parameters before sending requests
- **Error Information**: Be careful not to expose sensitive information in error messages