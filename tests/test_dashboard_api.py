
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timedelta

from src.app import app
from src.services.interfaces import InfrastructureService, StateManagementService, ProjectManagementService
from src.models.data_models import Resource, ChangePlan, ChangeSummary, StateSnapshot, Project, ProjectSettings, ProjectMember
from src.models.enums import ResourceStatus, ChangePlanStatus
from src.api.dependencies import get_current_user_id, validate_project_access, get_project_service

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_infra_service():
    return MagicMock(spec=InfrastructureService)

@pytest.fixture
def mock_state_service():
    return MagicMock(spec=StateManagementService)

@pytest.fixture
def mock_project_service():
    return MagicMock(spec=ProjectManagementService)

@pytest.fixture(autouse=True)
def override_dependencies(mock_infra_service, mock_state_service, mock_project_service):
    app.dependency_overrides[get_infrastructure_service] = lambda: mock_infra_service
    app.dependency_overrides[get_state_service] = lambda: mock_state_service
    app.dependency_overrides[get_project_service] = lambda: mock_project_service
    app.dependency_overrides[get_current_user_id] = lambda: "test-user"
    app.dependency_overrides[validate_project_access] = lambda project_id, user_id, project_service: project_id
    yield
    app.dependency_overrides = {}

@pytest.fixture
def sample_resources():
    return [
        Resource(id="res1", project_id="proj1", type="EC2::Instance", name="web1", region="us-east-1", properties={}, tags={"Environment": "Production"}, status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()),
        Resource(id="res2", project_id="proj1", type="S3::Bucket", name="my-bucket", region="us-east-1", properties={}, tags={"Environment": "Production"}, status=ResourceStatus.ACTIVE, created_at=datetime.now(), updated_at=datetime.now()),
        Resource(id="res3", project_id="proj1", type="EC2::Instance", name="web2", region="us-west-1", properties={}, tags={"Environment": "Staging"}, status=ResourceStatus.STOPPED, created_at=datetime.now(), updated_at=datetime.now()),
    ]

@pytest.fixture
def sample_plans():
    return [
        ChangePlan(id="plan1", project_id="proj1", summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0), changes=[], created_at=datetime.now(), status=ChangePlanStatus.APPROVED),
        ChangePlan(id="plan2", project_id="proj1", summary=ChangeSummary(total_changes=2, creates=0, updates=1, deletes=1), changes=[], created_at=datetime.now(), status=ChangePlanStatus.PENDING),
    ]

@pytest.fixture
def sample_history():
    now = datetime.now()
    return [
        StateSnapshot(version="v1", timestamp=now - timedelta(days=2), change_description="Initial state", s3_location="s3://.../v1.json"),
        StateSnapshot(version="v2", timestamp=now - timedelta(days=1), change_description="Added web server", s3_location="s3://.../v2.json"),
        StateSnapshot(version="v3", timestamp=now, change_description="Updated security groups", s3_location="s3://.../v3.json"),
    ]

@pytest.fixture
def sample_projects():
    now = datetime.now()
    return [
        Project(
            id="proj1", 
            name="Project 1", 
            description="Main project", 
            owner="test-user",
            members=[ProjectMember(user_id="test-user", role="owner", added_at=now)],
            settings=ProjectSettings(s3_bucket_path="s3://bucket/proj1", default_region="us-east-1"),
            created_at=now,
            updated_at=now
        ),
        Project(
            id="proj2", 
            name="Project 2", 
            description="Secondary project", 
            owner="test-user",
            members=[ProjectMember(user_id="test-user", role="owner", added_at=now)],
            settings=ProjectSettings(s3_bucket_path="s3://bucket/proj2", default_region="us-west-1"),
            created_at=now,
            updated_at=now
        ),
    ]

def test_get_project_dashboard(client, mock_infra_service, mock_state_service, sample_resources, sample_plans):
    mock_infra_service.get_resources = AsyncMock(return_value=sample_resources)
    mock_state_service.list_change_plans = AsyncMock(return_value=sample_plans)

    response = client.get("/projects/proj1/dashboard", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert data["projectId"] == "proj1"
    assert data["resourceSummary"]["totalResources"] == 3
    assert data["resourceSummary"]["statusCounts"] == {"active": 2, "stopped": 1}
    assert data["resourceSummary"]["typeCounts"] == {"EC2::Instance": 2, "S3::Bucket": 1}
    assert data["resourceSummary"]["regionCounts"] == {"us-east-1": 2, "us-west-1": 1}
    assert len(data["recentChangePlans"]) == 2
    mock_infra_service.get_resources.assert_called_once()
    mock_state_service.list_change_plans.assert_called_once_with("proj1")

def test_get_project_dashboard_with_grouping(client, mock_infra_service, mock_state_service, sample_resources, sample_plans):
    mock_infra_service.get_resources = AsyncMock(return_value=sample_resources)
    mock_state_service.list_change_plans = AsyncMock(return_value=sample_plans)

    response = client.get("/projects/proj1/dashboard?group_by=type", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert "groupedResources" in data
    assert len(data["groupedResources"]["EC2::Instance"]) == 2
    assert len(data["groupedResources"]["S3::Bucket"]) == 1

    # Test tag grouping
    response = client.get("/projects/proj1/dashboard?group_by=tag:Environment", headers={"x-user-id": "test-user"})
    
    assert response.status_code == 200
    data = response.json()
    assert "groupedResources" in data
    assert len(data["groupedResources"]["Production"]) == 2
    assert len(data["groupedResources"]["Staging"]) == 1

def test_get_project_dashboard_with_filtering(client, mock_infra_service, mock_state_service, sample_resources, sample_plans):
    mock_infra_service.get_resources = AsyncMock(return_value=[r for r in sample_resources if r.type == "EC2::Instance"])
    mock_state_service.list_change_plans = AsyncMock(return_value=sample_plans)

    response = client.get("/projects/proj1/dashboard?filter_type=EC2::Instance", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert data["resourceSummary"]["totalResources"] == 2
    assert data["resourceSummary"]["typeCounts"] == {"EC2::Instance": 2}
    
    # Verify filter was passed to get_resources
    mock_infra_service.get_resources.assert_called_once()
    filter_arg = mock_infra_service.get_resources.call_args[0][1]
    assert filter_arg.resource_type == "EC2::Instance"

def test_get_project_history(client, mock_state_service, sample_history):
    mock_state_service.get_state_history = AsyncMock(return_value=sample_history)

    response = client.get("/projects/proj1/history?limit=2", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    mock_state_service.get_state_history.assert_called_once_with("proj1")

def test_get_project_history_with_filters(client, mock_state_service, sample_history):
    mock_state_service.get_state_history = AsyncMock(return_value=sample_history)

    # Test filtering by description
    response = client.get("/projects/proj1/history?change_description=web", headers={"x-user-id": "test-user"})
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "web" in data[0]["change_description"].lower()
    
    # Test date filtering
    today = datetime.now().date().isoformat()
    response = client.get(f"/projects/proj1/history?from_date={today}T00:00:00", headers={"x-user-id": "test-user"})
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["version"] == "v3"

def test_get_accessible_projects(client, mock_project_service, sample_projects):
    mock_project_service.list_projects = AsyncMock(return_value=sample_projects)

    response = client.get("/projects/proj1/projects-access", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert data["currentProjectId"] == "proj1"
    assert len(data["accessibleProjects"]) == 2
    assert data["accessibleProjects"][0]["isCurrentProject"] is True
    assert data["accessibleProjects"][1]["isCurrentProject"] is False
    mock_project_service.list_projects.assert_called_once_with("test-user")
