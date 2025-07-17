"""
Example usage of AWS MCP Client
"""
import asyncio
from datetime import datetime

from src.services.aws_mcp_client import create_aws_mcp_client
from src.models.data_models import ResourceConfig, ResourceFilter
from src.models.enums import ResourceStatus


async def main():
    """Example usage of AWS MCP Client"""
    
    # Create MCP client with custom configuration
    client = create_aws_mcp_client(
        server_url="http://localhost:8000",
        timeout=30,
        max_retries=3,
        circuit_breaker_threshold=5
    )
    
    try:
        # Use client as async context manager
        async with client:
            # Check server health
            print("Checking server health...")
            is_healthy = await client.health_check()
            print(f"Server healthy: {is_healthy}")
            
            if not is_healthy:
                print("Server is not healthy, skipping operations")
                return
            
            project_id = "example-project-123"
            
            # Create a new EC2 instance
            print("\nCreating EC2 instance...")
            resource_config = ResourceConfig(
                type="EC2::Instance",
                name="example-web-server",
                properties={
                    "instanceType": "t3.micro",
                    "imageId": "ami-12345678",
                    "subnetId": "subnet-12345678",
                    "securityGroupIds": ["sg-12345678"]
                },
                tags={
                    "Environment": "development",
                    "Project": "web-app",
                    "Owner": "example-user"
                }
            )
            
            try:
                new_resource = await client.create_resource(project_id, resource_config)
                print(f"Created resource: {new_resource.id} ({new_resource.name})")
                print(f"Status: {new_resource.status}")
                print(f"ARN: {new_resource.arn}")
                
                # Get resource details
                print(f"\nRetrieving resource details...")
                resource = await client.get_resource(project_id, new_resource.id)
                if resource:
                    print(f"Retrieved resource: {resource.name}")
                    print(f"Type: {resource.type}")
                    print(f"Region: {resource.region}")
                    print(f"Properties: {resource.properties}")
                
                # List all resources in project
                print(f"\nListing all resources in project...")
                all_resources = await client.list_resources(project_id)
                print(f"Found {len(all_resources)} resources:")
                for res in all_resources:
                    print(f"  - {res.name} ({res.type}) - {res.status}")
                
                # List resources with filters
                print(f"\nListing EC2 instances only...")
                ec2_filter = ResourceFilter(
                    resource_type="EC2::Instance",
                    status=ResourceStatus.ACTIVE
                )
                ec2_resources = await client.list_resources(project_id, ec2_filter)
                print(f"Found {len(ec2_resources)} EC2 instances:")
                for res in ec2_resources:
                    print(f"  - {res.name} - {res.status}")
                
                # Update resource
                print(f"\nUpdating resource...")
                updates = {
                    "instanceType": "t3.small",
                    "tags": {
                        "Environment": "development",
                        "Project": "web-app",
                        "Owner": "example-user",
                        "Updated": datetime.now().isoformat()
                    }
                }
                updated_resource = await client.update_resource(
                    project_id, new_resource.id, updates
                )
                print(f"Updated resource: {updated_resource.name}")
                print(f"New instance type: {updated_resource.properties.get('instanceType')}")
                
                # Check resource status
                print(f"\nChecking resource status...")
                status = await client.get_resource_status(project_id, new_resource.id)
                print(f"Current status: {status}")
                
                # Delete resource (commented out for safety)
                # print(f"\nDeleting resource...")
                # success = await client.delete_resource(project_id, new_resource.id)
                # print(f"Deletion successful: {success}")
                
            except Exception as e:
                print(f"Error during resource operations: {e}")
            
            # Get server information
            print(f"\nGetting server information...")
            server_info = await client.get_server_info()
            print(f"Server info: {server_info}")
            
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())