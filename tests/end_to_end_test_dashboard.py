"""
End-to-end tests for AWS Infrastructure Manager Dashboard API

These tests validate the dashboard API endpoints and their integration with the rest of the system.

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


@pytest.fixture
def test_project(client):
    """Create a test project for dashboard testing"""
    project_name = f"Dashboard Test Project {uuid.uuid4().hex[:8]}"
    project_data = {
        "name": project_name,
        "description": "Project for dashboard API testing",
        "settings": {
            "s3_bucket_path": f"s3://aws-infra-manager-test/dashboard-test/{uuid.uuid4().hex}",
            "default_region": "us-east-1"
        }
    }
    
    response = client.post("/projects/", json=project_data)
    assert response.status_code == 201, f"Failed to create project: {response.text}"
    
    project = response.json()
    return project


@pytest.fixture
def test_resources(client, test_project):
    """Create test resources for dashboard testing"""
    project_id = test_project["id"]
    resources = []
    
    # Create EC2 instance
    ec2_data = {
        "type": "EC2::Instance",
        "name": f"dashboard-test-ec2-{uuid.uuid4().hex[:8]}",
        "properties": {
            "instanceType": "t3.micro",
            "imageId": "ami-12345678"
        },
        "tags": {
            "Environment": "test",
            "Service": "web"
        }
    }
    
    response = client.post(f"/projects/{project_id}/resources/", json=ec2_data)
    assert response.status_code == 201, f"Failed to create EC2 resource: {response.text}"
    resources.append(response.json())
    
    # Create S3 bucket
    s3_data = {
        "type": "S3::Bucket",
        "name": f"dashboard-test-s3-{uuid.uuid4().hex[:8]}",
        "properties": {
            "versioning": True,
            "region": "us-east-1"
        },
        "tags": {
            "Environment": "test",
            "Service": "storage"
        }
    }
    
    response = client.post(f"/projects/{project_id}/resources/", json=s3_data)
    assert response.status_code == 201, f"Failed to create S3 resource: {response.text}"
    resources.append(response.json())
    
    # Create RDS instance
    rds_data = {
        "type": "RDS::DBInstance",
        "name": f"dashboard-test-rds-{uuid.uuid4().hex[:8]}",
        "properties": {
            "dbInstanceClass": "db.t3.micro",
            "engine": "mysql",
            "allocatedStorage": 20
        },
        "tags": {
            "Environment": "test",
            "Service": "database"
        }
    }
    
    response = client.post(f"/projects/{project_id}/resources/", json=rds_data)
    assert response.status_code == 201, f"Failed to create RDS resource: {response.text}"
    resources.append(response.json())
    
    return resources


@pytest.mark.end_to_end
def test_dashboard_overview(client, test_project, test_resources):
    """Test dashboard overview endpoint"""
    project_id = test_project["id"]
    
    # Get dashboard overview
    response = client.get(f"/projects/{project_id}/dashboard/overview")
    assert response.status_code == 200, f"Failed to get dashboard overview: {response.text}"
    
    overview = response.json()
    assert "resource_count" in overview, "Overview should include resource count"
    assert "resource_types" in overview, "Overview should include resource types"
    assert "recent_changes" in overview, "Overview should include recent changes"
    
    # Verify resource count
    assert overview["resource_count"] == len(test_resources), "Resource count should match"
    
    # Verify resource types
    resource_types = overview["resource_types"]
    assert "EC2::Instance" in resource_types, "Should include EC2 instance"
    assert "S3::Bucket" in resource_types, "Should include S3 bucket"
    assert "RDS::DBInstance" in resource_types, "Should include RDS instance"
    
    # Verify recent changes
    assert len(overview["recent_changes"]) > 0, "Should have recent changes"


@pytest.mark.end_to_end
def test_dashboard_resource_summary(client, test_project, test_resources):
    """Test dashboard resource summary endpoint"""
    project_id = test_project["id"]
    
    # Get resource summary
    response = client.get(f"/projects/{project_id}/dashboard/resources")
    assert response.status_code == 200, f"Failed to get resource summary: {response.text}"
    
    summary = response.json()
    assert "by_type" in summary, "Summary should include breakdown by type"
    assert "by_region" in summary, "Summary should include breakdown by region"
    assert "by_status" in summary, "Summary should include breakdown by status"
    
    # Verify breakdown by type
    by_type = summary["by_type"]
    assert by_type["EC2::Instance"] == 1, "Should have 1 EC2 instance"
    assert by_type["S3::Bucket"] == 1, "Should have 1 S3 bucket"
    assert by_type["RDS::DBInstance"] == 1, "Should have 1 RDS instance"
    
    # Verify breakdown by region
    by_region = summary["by_region"]
    assert by_region["us-east-1"] == 3, "Should have 3 resources in us-east-1"
    
    # Verify breakdown by status
    by_status = summary["by_status"]
    assert by_status["active"] == 3, "Should have 3 active resources"


@pytest.mark.end_to_end
def test_dashboard_change_history(client, test_project, test_resources):
    """Test dashboard change history endpoint"""
    project_id = test_project["id"]
    
    # Get change history
    response = client.get(f"/projects/{project_id}/dashboard/changes")
    assert response.status_code == 200, f"Failed to get change history: {response.text}"
    
    history = response.json()
    assert "changes" in history, "Response should include changes"
    assert "total" in history, "Response should include total count"
    
    # Verify changes
    changes = history["changes"]
    assert len(changes) > 0, "Should have changes"
    
    # Create a change plan to add to history
    resource = test_resources[0]
    
    # Update the resource properties
    updated_properties = {
        **resource["properties"],
        "instanceType": "t3.medium"  # Changed from t3.micro
    }
    
    # Create desired state for change plan
    change_plan_data = {
        "resources": [
            {
                "id": resource["id"],
                "type": resource["type"],
                "name": resource["name"],
                "region": resource["region"],
                "properties": updated_properties,
                "tags": resource["tags"]
            }
        ],
        "change_description": "Update instance type for dashboard test"
    }
    
    response = client.post(f"/projects/{project_id}/plans/", json=change_plan_data)
    assert response.status_code == 201, f"Failed to create change plan: {response.text}"
    
    # Get updated change history
    response = client.get(f"/projects/{project_id}/dashboard/changes")
    assert response.status_code == 200, f"Failed to get updated change history: {response.text}"
    
    updated_history = response.json()
    assert len(updated_history["changes"]) > len(changes), "Should have more changes after creating plan"


@pytest.mark.end_to_end
def test_dashboard_resource_details(client, test_project, test_resources):
    """Test dashboard resource details endpoint"""
    project_id = test_project["id"]
    resource = test_resources[0]  # Use the EC2 instance
    
    # Get resource details
    response = client.get(f"/projects/{project_id}/dashboard/resources/{resource['id']}")
    assert response.status_code == 200, f"Failed to get resource details: {response.text}"
    
    details = response.json()
    assert "resource" in details, "Response should include resource"
    assert "change_history" in details, "Response should include change history"
    assert "dependencies" in details, "Response should include dependencies"
    
    # Verify resource details
    resource_details = details["resource"]
    assert resource_details["id"] == resource["id"], "Resource ID should match"
    assert resource_details["type"] == resource["type"], "Resource type should match"
    
    # Verify change history
    change_history = details["change_history"]
    assert isinstance(change_history, list), "Change history should be a list"


@pytest.mark.end_to_end
def test_dashboard_pending_approvals(client, test_project, test_resources):
    """Test dashboard pending approvals endpoint"""
    project_id = test_project["id"]
    
    # Get pending approvals
    response = client.get(f"/projects/{project_id}/dashboard/approvals")
    assert response.status_code == 200, f"Failed to get pending approvals: {response.text}"
    
    approvals = response.json()
    assert "pending" in approvals, "Response should include pending approvals"
    assert "recent" in approvals, "Response should include recent approvals"
    
    # Create a change plan that will need approval
    resource = test_resources[0]
    
    # Update the resource properties
    updated_properties = {
        **resource["properties"],
        "instanceType": "t3.large"  # Changed from t3.micro
    }
    
    # Create desired state for change plan
    change_plan_data = {
        "resources": [
            {
                "id": resource["id"],
                "type": resource["type"],
                "name": resource["name"],
                "region": resource["region"],
                "properties": updated_properties,
                "tags": resource["tags"]
            }
        ],
        "change_description": "Update instance type for approval test"
    }
    
    response = client.post(f"/projects/{project_id}/plans/", json=change_plan_data)
    assert response.status_code == 201, f"Failed to create change plan: {response.text}"
    
    # Get updated pending approvals
    response = client.get(f"/projects/{project_id}/dashboard/approvals")
    assert response.status_code == 200, f"Failed to get updated pending approvals: {response.text}"
    
    updated_approvals = response.json()
    assert len(updated_approvals["pending"]) >= len(approvals["pending"]), "Should have at least the same number of pending approvals"


@pytest.mark.end_to_end
def test_cleanup(client, test_project, test_resources):
    """Clean up test resources"""
    project_id = test_project["id"]
    
    # Delete all resources
    for resource in test_resources:
        response = client.delete(f"/projects/{project_id}/resources/{resource['id']}")
        assert response.status_code == 204, f"Failed to delete resource {resource['id']}: {response.text}"
    
    print("All test resources deleted successfully")


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])