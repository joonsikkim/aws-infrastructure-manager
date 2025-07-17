"""
Integration tests for AWS MCP Client

These tests validate the integration between the AWS MCP Client and the AWS MCP Server.
They require a running AWS MCP Server instance to execute successfully.

Environment variables:
- AWS_MCP_SERVER_URL: URL of the AWS MCP Server (default: http://localhost:8080)
- AWS_MCP_TEST_PROJECT: Project ID to use for testing (default: test-project)
"""
import os
import pytest
import asyncio
import uuid
from datetime import datetime

from src.services.aws_mcp_client import AWSMCPClient, create_aws_mcp_client
from src.models.data_models import ResourceConfig, ResourceFilter
from src.models.enums import ResourceStatus
from src.models.exceptions import InfrastructureException

# Get configuration from environment variables
MCP_SERVER_URL = os.environ.get("AWS_MCP_SERVER_URL", "http://localhost:8080")
TEST_PROJECT_ID = os.environ.get("AWS_MCP_TEST_PROJECT", "test-project")


@pytest.fixture
async def mcp_client():
    """Create and configure AWS MCP client for testing"""
    client = create_aws_mcp_client(
        server_url=MCP_SERVER_URL,
        timeout=30,
        max_retries=2,
        circuit_breaker_threshold=3
    )
    
    await client.connect()
    yield client
    await client.disconnect()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_server_connection(mcp_client):
    """Test connection to AWS MCP Server"""
    is_healthy = await mcp_client.health_check()
    assert is_healthy is True, "AWS MCP Server health check failed"
    
    server_info = await mcp_client.get_server_info()
    assert "version" in server_info, "Server info should contain version"
    assert "name" in server_info, "Server info should contain name"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resource_lifecycle(mcp_client):
    """Test complete resource lifecycle: create, get, update, delete"""
    # Generate unique resource name for this test run
    resource_name = f"test-instance-{uuid.uuid4().hex[:8]}"
    
    # 1. Create resource
    resource_config = ResourceConfig(
        type="EC2::Instance",
        name=resource_name,
        properties={
            "instanceType": "t3.micro",
            "imageId": "ami-12345678",
            "subnetId": "subnet-12345678"
        },
        tags={
            "Environment": "test",
            "CreatedBy": "integration-test"
        }
    )
    
    created_resource = await mcp_client.create_resource(TEST_PROJECT_ID, resource_config)
    assert created_resource.id is not None, "Created resource should have an ID"
    assert created_resource.name == resource_name, "Resource name should match"
    assert created_resource.type == "EC2::Instance", "Resource type should match"
    
    resource_id = created_resource.id
    print(f"Created resource with ID: {resource_id}")
    
    try:
        # 2. Get resource
        retrieved_resource = await mcp_client.get_resource(TEST_PROJECT_ID, resource_id)
        assert retrieved_resource is not None, "Resource should be retrievable"
        assert retrieved_resource.id == resource_id, "Resource ID should match"
        assert retrieved_resource.properties["instanceType"] == "t3.micro", "Resource properties should match"
        
        # 3. Update resource
        updates = {"instanceType": "t3.small"}
        updated_resource = await mcp_client.update_resource(TEST_PROJECT_ID, resource_id, updates)
        assert updated_resource.properties["instanceType"] == "t3.small", "Resource should be updated"
        
        # 4. List resources with filter
        filters = ResourceFilter(
            resource_type="EC2::Instance",
            tags={"CreatedBy": "integration-test"}
        )
        resources = await mcp_client.list_resources(TEST_PROJECT_ID, filters)
        assert len(resources) > 0, "Should find resources with filter"
        assert any(r.id == resource_id for r in resources), "Created resource should be in the list"
        
        # 5. Get resource status
        status = await mcp_client.get_resource_status(TEST_PROJECT_ID, resource_id)
        assert status in [ResourceStatus.ACTIVE, ResourceStatus.UPDATING], "Resource should have valid status"
        
    finally:
        # 6. Delete resource (cleanup)
        success = await mcp_client.delete_resource(TEST_PROJECT_ID, resource_id)
        assert success is True, "Resource deletion should succeed"
        
        # Verify deletion
        deleted_resource = await mcp_client.get_resource(TEST_PROJECT_ID, resource_id)
        assert deleted_resource is None, "Resource should be deleted"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_error_handling(mcp_client):
    """Test error handling for invalid operations"""
    # Try to get non-existent resource
    non_existent_id = f"non-existent-{uuid.uuid4().hex}"
    resource = await mcp_client.get_resource(TEST_PROJECT_ID, non_existent_id)
    assert resource is None, "Non-existent resource should return None"
    
    # Try to update non-existent resource
    with pytest.raises(InfrastructureException) as excinfo:
        await mcp_client.update_resource(TEST_PROJECT_ID, non_existent_id, {"instanceType": "t3.small"})
    assert "resource not found" in str(excinfo.value).lower() or "not found" in str(excinfo.value).lower()
    
    # Try to create resource with invalid configuration
    invalid_config = ResourceConfig(
        type="InvalidType",
        name="invalid-resource",
        properties={},
        tags={}
    )
    
    with pytest.raises(InfrastructureException) as excinfo:
        await mcp_client.create_resource(TEST_PROJECT_ID, invalid_config)
    assert "invalid" in str(excinfo.value).lower() or "error" in str(excinfo.value).lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_operations(mcp_client):
    """Test concurrent operations with AWS MCP Server"""
    # Create multiple resources concurrently
    resource_configs = [
        ResourceConfig(
            type="EC2::Instance",
            name=f"concurrent-test-{i}",
            properties={
                "instanceType": "t3.micro",
                "imageId": "ami-12345678"
            },
            tags={"ConcurrentTest": "true"}
        )
        for i in range(5)
    ]
    
    # Create resources concurrently
    create_tasks = [
        mcp_client.create_resource(TEST_PROJECT_ID, config)
        for config in resource_configs
    ]
    
    created_resources = await asyncio.gather(*create_tasks)
    resource_ids = [r.id for r in created_resources]
    
    try:
        # Verify all resources were created
        assert len(created_resources) == 5, "All resources should be created"
        assert all(r.id is not None for r in created_resources), "All resources should have IDs"
        
        # Get all resources concurrently
        get_tasks = [
            mcp_client.get_resource(TEST_PROJECT_ID, resource_id)
            for resource_id in resource_ids
        ]
        
        retrieved_resources = await asyncio.gather(*get_tasks)
        assert all(r is not None for r in retrieved_resources), "All resources should be retrievable"
        
    finally:
        # Clean up - delete all resources concurrently
        delete_tasks = [
            mcp_client.delete_resource(TEST_PROJECT_ID, resource_id)
            for resource_id in resource_ids
        ]
        
        delete_results = await asyncio.gather(*delete_tasks)
        assert all(delete_results), "All resources should be deleted successfully"


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])