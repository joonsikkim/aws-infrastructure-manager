"""
End-to-end tests for AWS Infrastructure Manager API endpoints

These tests validate the API endpoints directly using FastAPI TestClient.
They test the complete workflow through the API layer.

Environment variables:
- TEST_USER_ID: User ID for testing (default: test-user)
"""
import os
import pytest
import uuid
import json
from datetime import datetime
from fastapi.testclient import TestClient

from src.app import create_app
from src.models.enums import ResourceStatus, ChangePlanStatus

# Get configuration from environment variables
TEST_USER_ID = os.environ.get("TEST_USER_ID", "test-user")


@pytest.fixture
def client():
    """Create FastAPI test client"""
    app = create_app()
    with TestClient(app) as client:
        # Add test headers
        client.headers.update({
            "x-user-id": TEST_USER_ID,
            "x-correlation-id": f"test-{uuid.uuid4().hex}"
        })
        yield client


@pytest.mark.end_to_end
def test_api_health_check(client):
    """Test API health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.end_to_end
def test_api_complete_workflow(client):
    """Test complete workflow through API endpoints"""
    # Step 1: Create a project
    print("Step 1: Creating a project")
    
    project_name = f"API Test Project {uuid.uuid4().hex[:8]}"
    project_data = {
        "name": project_name,
        "description": "Project for API testing",
        "settings": {
            "s3_bucket_path": f"s3://aws-infra-manager-test/api-test/{uuid.uuid4().hex}",
            "default_region": "us-east-1"
        }
    }
    
    response = client.post("/projects/", json=project_data)
    assert response.status_code == 201, f"Failed to create project: {response.text}"
    
    project = response.json()
    project_id = project["id"]
    print(f"Created project with ID: {project_id}")
    
    # Step 2: Create a resource
    print("Step 2: Creating a resource")
    
    resource_name = f"api-test-instance-{uuid.uuid4().hex[:8]}"
    resource_data = {
        "type": "EC2::Instance",
        "name": resource_name,
        "properties": {
            "instanceType": "t3.micro",
            "imageId": "ami-12345678",
            "subnetId": "subnet-12345678"
        },
        "tags": {
            "Environment": "test",
            "CreatedBy": "api-test"
        }
    }
    
    response = client.post(f"/projects/{project_id}/resources/", json=resource_data)
    assert response.status_code == 201, f"Failed to create resource: {response.text}"
    
    resource = response.json()
    resource_id = resource["id"]
    print(f"Created resource with ID: {resource_id}")
    
    # Step 3: List resources
    print("Step 3: Listing resources")
    
    response = client.get(f"/projects/{project_id}/resources/")
    assert response.status_code == 200, f"Failed to list resources: {response.text}"
    
    resources = response.json()
    assert len(resources) >= 1, "Should have at least one resource"
    assert any(r["id"] == resource_id for r in resources), "Created resource should be in the list"
    
    # Step 4: Create a change plan
    print("Step 4: Creating a change plan")
    
    # Update the resource properties
    updated_properties = {
        "instanceType": "t3.medium",  # Changed from t3.micro
        "imageId": "ami-12345678",
        "subnetId": "subnet-12345678"
    }
    
    # Create desired state for change plan
    change_plan_data = {
        "resources": [
            {
                "id": resource_id,
                "type": "EC2::Instance",
                "name": resource_name,
                "region": "us-east-1",
                "properties": updated_properties,
                "tags": {
                    "Environment": "test",
                    "CreatedBy": "api-test"
                }
            }
        ],
        "change_description": "Update instance type to t3.medium"
    }
    
    response = client.post(f"/projects/{project_id}/plans/", json=change_plan_data)
    assert response.status_code == 201, f"Failed to create change plan: {response.text}"
    
    change_plan = response.json()
    plan_id = change_plan["id"]
    print(f"Created change plan with ID: {plan_id}")
    
    # Step 5: List change plans
    print("Step 5: Listing change plans")
    
    response = client.get(f"/projects/{project_id}/plans/")
    assert response.status_code == 200, f"Failed to list change plans: {response.text}"
    
    plans = response.json()
    assert len(plans) >= 1, "Should have at least one plan"
    assert any(p["id"] == plan_id for p in plans), "Created plan should be in the list"
    
    # Step 6: Get specific change plan
    print("Step 6: Getting specific change plan")
    
    response = client.get(f"/projects/{project_id}/plans/{plan_id}")
    assert response.status_code == 200, f"Failed to get change plan: {response.text}"
    
    retrieved_plan = response.json()
    assert retrieved_plan["id"] == plan_id, "Plan ID should match"
    
    # Step 7: Approve the plan
    print("Step 7: Approving the plan")
    
    approval_data = {
        "action": "approve"
    }
    
    response = client.post(f"/projects/{project_id}/plans/{plan_id}/approval", json=approval_data)
    assert response.status_code == 200, f"Failed to approve plan: {response.text}"
    
    approved_plan = response.json()
    assert approved_plan["status"] == "approved", "Plan should be approved"
    
    # Step 8: Execute the change (update resource)
    print("Step 8: Executing the change")
    
    update_data = {
        "properties": {
            "instanceType": "t3.medium"
        }
    }
    
    response = client.put(f"/projects/{project_id}/resources/{resource_id}", json=update_data)
    assert response.status_code == 200, f"Failed to update resource: {response.text}"
    
    updated_resource = response.json()
    assert updated_resource["properties"]["instanceType"] == "t3.medium", "Instance type should be updated"
    
    # Step 9: Get updated resource
    print("Step 9: Getting updated resource")
    
    response = client.get(f"/projects/{project_id}/resources/{resource_id}")
    assert response.status_code == 200, f"Failed to get resource: {response.text}"
    
    final_resource = response.json()
    assert final_resource["properties"]["instanceType"] == "t3.medium", "Instance type should be updated"
    
    # Step 10: Delete resource
    print("Step 10: Deleting resource")
    
    response = client.delete(f"/projects/{project_id}/resources/{resource_id}")
    assert response.status_code == 204, f"Failed to delete resource: {response.text}"
    
    # Verify resource was deleted
    response = client.get(f"/projects/{project_id}/resources/{resource_id}")
    assert response.status_code == 404, "Resource should be deleted"
    
    print("API workflow test completed successfully")


@pytest.mark.end_to_end
def test_api_project_isolation(client):
    """Test project isolation through API endpoints"""
    # Create two projects
    print("Creating two test projects")
    
    project_data1 = {
        "name": f"API Isolation Test 1 {uuid.uuid4().hex[:8]}",
        "description": "First project for isolation testing",
        "settings": {
            "s3_bucket_path": f"s3://aws-infra-manager-test/api-isolation-test-1/{uuid.uuid4().hex}",
            "default_region": "us-east-1"
        }
    }
    
    project_data2 = {
        "name": f"API Isolation Test 2 {uuid.uuid4().hex[:8]}",
        "description": "Second project for isolation testing",
        "settings": {
            "s3_bucket_path": f"s3://aws-infra-manager-test/api-isolation-test-2/{uuid.uuid4().hex}",
            "default_region": "us-east-1"
        }
    }
    
    response1 = client.post("/projects/", json=project_data1)
    assert response1.status_code == 201, f"Failed to create project 1: {response1.text}"
    project1 = response1.json()
    project_id1 = project1["id"]
    
    response2 = client.post("/projects/", json=project_data2)
    assert response2.status_code == 201, f"Failed to create project 2: {response2.text}"
    project2 = response2.json()
    project_id2 = project2["id"]
    
    print(f"Created projects with IDs: {project_id1} and {project_id2}")
    
    # Create resources in both projects
    resource_data1 = {
        "type": "EC2::Instance",
        "name": f"isolation-test-1-{uuid.uuid4().hex[:8]}",
        "properties": {
            "instanceType": "t3.micro",
            "imageId": "ami-12345678"
        },
        "tags": {
            "Project": "Project1",
            "IsolationTest": "true"
        }
    }
    
    resource_data2 = {
        "type": "EC2::Instance",
        "name": f"isolation-test-2-{uuid.uuid4().hex[:8]}",
        "properties": {
            "instanceType": "t3.large",
            "imageId": "ami-87654321"
        },
        "tags": {
            "Project": "Project2",
            "IsolationTest": "true"
        }
    }
    
    response1 = client.post(f"/projects/{project_id1}/resources/", json=resource_data1)
    assert response1.status_code == 201, f"Failed to create resource in project 1: {response1.text}"
    resource1 = response1.json()
    resource_id1 = resource1["id"]
    
    response2 = client.post(f"/projects/{project_id2}/resources/", json=resource_data2)
    assert response2.status_code == 201, f"Failed to create resource in project 2: {response2.text}"
    resource2 = response2.json()
    resource_id2 = resource2["id"]
    
    print(f"Created resources with IDs: {resource_id1} in project 1, {resource_id2} in project 2")
    
    try:
        # List resources for each project
        response1 = client.get(f"/projects/{project_id1}/resources/")
        assert response1.status_code == 200, f"Failed to list resources for project 1: {response1.text}"
        resources1 = response1.json()
        
        response2 = client.get(f"/projects/{project_id2}/resources/")
        assert response2.status_code == 200, f"Failed to list resources for project 2: {response2.text}"
        resources2 = response2.json()
        
        # Verify project 1 resources
        assert len(resources1) == 1, "Project 1 should have 1 resource"
        assert resources1[0]["id"] == resource_id1, "Project 1 should contain its resource"
        
        # Verify project 2 resources
        assert len(resources2) == 1, "Project 2 should have 1 resource"
        assert resources2[0]["id"] == resource_id2, "Project 2 should contain its resource"
        
        # Try to access project 1's resource from project 2 (should fail)
        response = client.get(f"/projects/{project_id2}/resources/{resource_id1}")
        assert response.status_code == 404, "Should not be able to access project 1's resource from project 2"
        
        # Try to access project 2's resource from project 1 (should fail)
        response = client.get(f"/projects/{project_id1}/resources/{resource_id2}")
        assert response.status_code == 404, "Should not be able to access project 2's resource from project 1"
        
        print("API project isolation test completed successfully")
        
    finally:
        # Clean up resources
        print("Cleaning up resources")
        client.delete(f"/projects/{project_id1}/resources/{resource_id1}")
        client.delete(f"/projects/{project_id2}/resources/{resource_id2}")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])