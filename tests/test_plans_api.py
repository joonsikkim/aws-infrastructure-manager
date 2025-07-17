
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from src.app import app
from src.services.interfaces import StateManagementService, ChangePlanEngine, ApprovalWorkflowService
from src.models.data_models import ChangePlan, ChangeSummary, Change, Resource
from src.models.enums import ChangeAction, RiskLevel, ChangePlanStatus, ResourceStatus
from datetime import datetime
import uuid
from src.api.dependencies import get_current_user_id, validate_project_access

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_state_service():
    return MagicMock(spec=StateManagementService)

@pytest.fixture
def mock_change_plan_engine():
    return MagicMock(spec=ChangePlanEngine)

@pytest.fixture
def mock_approval_service():
    return MagicMock(spec=ApprovalWorkflowService)

@pytest.fixture(autouse=True)
def override_dependencies(mock_state_service, mock_change_plan_engine, mock_approval_service):
    app.dependency_overrides[StateManagementService] = lambda: mock_state_service
    app.dependency_overrides[ChangePlanEngine] = lambda: mock_change_plan_engine
    app.dependency_overrides[ApprovalWorkflowService] = lambda: mock_approval_service
    app.dependency_overrides[get_current_user_id] = lambda: "test-user"
    app.dependency_overrides[validate_project_access] = lambda project_id, user_id, project_service: project_id
    yield
    app.dependency_overrides = {}

@pytest.fixture
def sample_change_plan():
    plan_id = str(uuid.uuid4())
    project_id = "test-project"
    return ChangePlan(
        id=plan_id,
        project_id=project_id,
        summary=ChangeSummary(total_changes=1, creates=1, updates=0, deletes=0),
        changes=[
            Change(
                action=ChangeAction.CREATE,
                resource_type="EC2::Instance",
                resource_id="i-12345",
                risk_level=RiskLevel.LOW,
                desired_config={"InstanceType": "t2.micro"}
            )
        ],
        created_at=datetime.now(),
        status=ChangePlanStatus.PENDING,
        created_by="test-user"
    )

def test_create_change_plan(client, mock_change_plan_engine, mock_state_service, sample_change_plan):
    mock_change_plan_engine.generate_plan = AsyncMock(return_value=sample_change_plan)
    mock_state_service.save_change_plan = AsyncMock()

    response = client.post(
        f"/projects/{sample_change_plan.project_id}/plans/",
        json={
            "resources": [{
                "id": "i-12345",
                "type": "EC2::Instance",
                "name": "test-instance",
                "region": "us-east-1",
                "properties": {"InstanceType": "t2.micro"},
                "tags": {}
            }],
            "change_description": "Test plan"
        },
        headers={"x-user-id": "test-user"}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == sample_change_plan.id
    assert data["summary"]["total_changes"] == 1
    mock_change_plan_engine.generate_plan.assert_called_once()
    mock_state_service.save_change_plan.assert_called_once_with(sample_change_plan.project_id, sample_change_plan)

def test_list_change_plans(client, mock_state_service, sample_change_plan):
    mock_state_service.list_change_plans = AsyncMock(return_value=[sample_change_plan])

    response = client.get(f"/projects/{sample_change_plan.project_id}/plans/", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == sample_change_plan.id
    mock_state_service.list_change_plans.assert_called_once_with(sample_change_plan.project_id)

def test_get_change_plan(client, mock_state_service, sample_change_plan):
    mock_state_service.get_change_plan = AsyncMock(return_value=sample_change_plan)

    response = client.get(f"/projects/{sample_change_plan.project_id}/plans/{sample_change_plan.id}", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_change_plan.id
    mock_state_service.get_change_plan.assert_called_once_with(sample_change_plan.project_id, sample_change_plan.id)

def test_get_change_plan_not_found(client, mock_state_service, sample_change_plan):
    mock_state_service.get_change_plan = AsyncMock(return_value=None)

    response = client.get(f"/projects/{sample_change_plan.project_id}/plans/{sample_change_plan.id}", headers={"x-user-id": "test-user"})

    assert response.status_code == 404
    mock_state_service.get_change_plan.assert_called_once_with(sample_change_plan.project_id, sample_change_plan.id)

def test_handle_plan_approval(client, mock_approval_service, mock_state_service, sample_change_plan):
    approved_plan = sample_change_plan
    approved_plan.status = ChangePlanStatus.APPROVED
    approved_plan.approved_by = "test-approver"
    approved_plan.approved_at = datetime.now()

    mock_approval_service.approve_plan = AsyncMock(return_value=approved_plan)
    mock_state_service.save_change_plan = AsyncMock()

    response = client.post(
        f"/projects/{sample_change_plan.project_id}/plans/{sample_change_plan.id}/approval",
        json={"action": "approve"},
        headers={"x-user-id": "test-approver"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert data["approved_by"] == "test-approver"
    mock_approval_service.approve_plan.assert_called_once_with(sample_change_plan.id, "test-approver")
    mock_state_service.save_change_plan.assert_called_once_with(sample_change_plan.project_id, approved_plan)

def test_get_plan_status(client, mock_state_service, sample_change_plan):
    mock_state_service.get_change_plan = AsyncMock(return_value=sample_change_plan)

    response = client.get(f"/projects/{sample_change_plan.project_id}/plans/{sample_change_plan.id}/status", headers={"x-user-id": "test-user"})

    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == sample_change_plan.id
    assert data["status"] == "pending"
    mock_state_service.get_change_plan.assert_called_once_with(sample_change_plan.project_id, sample_change_plan.id)
