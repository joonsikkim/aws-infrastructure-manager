"""
Tests for Project Management Service
"""
import pytest
from datetime import datetime
from src.services.project_management import ProjectManagementServiceImpl
from src.models.data_models import (
    ProjectConfig, ProjectSettings, ProjectUpdate, NotificationConfig
)
from src.models.exceptions import ProjectNotFoundError


@pytest.fixture
def project_service():
    """Create a project management service instance"""
    return ProjectManagementServiceImpl()


@pytest.fixture
def sample_project_config():
    """Create a sample project configuration"""
    settings = ProjectSettings(
        s3_bucket_path="s3://test-bucket/projects",
        default_region="us-east-1",
        notification_settings=NotificationConfig(
            email_notifications=True,
            notification_events=["approval_required"]
        )
    )
    
    return ProjectConfig(
        name="Test Project",
        description="A test project for infrastructure management",
        owner="user123",
        settings=settings
    )


@pytest.mark.asyncio
async def test_create_project(project_service, sample_project_config):
    """Test creating a new project"""
    project = await project_service.create_project(sample_project_config)
    
    assert project.id is not None
    assert project.name == "Test Project"
    assert project.description == "A test project for infrastructure management"
    assert project.owner == "user123"
    assert len(project.members) == 1
    assert project.members[0].user_id == "user123"
    assert project.members[0].role == "owner"
    assert project.created_at is not None
    assert project.updated_at is not None


@pytest.mark.asyncio
async def test_get_project(project_service, sample_project_config):
    """Test retrieving a project by ID"""
    created_project = await project_service.create_project(sample_project_config)
    retrieved_project = await project_service.get_project(created_project.id)
    
    assert retrieved_project.id == created_project.id
    assert retrieved_project.name == created_project.name


@pytest.mark.asyncio
async def test_get_nonexistent_project(project_service):
    """Test retrieving a non-existent project"""
    with pytest.raises(ProjectNotFoundError):
        await project_service.get_project("nonexistent-id")


@pytest.mark.asyncio
async def test_list_projects(project_service, sample_project_config):
    """Test listing projects for a user"""
    # Create multiple projects
    project1 = await project_service.create_project(sample_project_config)
    
    config2 = ProjectConfig(
        name="Second Project",
        description="Another test project",
        owner="user456",
        settings=sample_project_config.settings
    )
    project2 = await project_service.create_project(config2)
    
    # List projects for user123 (should see only project1)
    user123_projects = await project_service.list_projects("user123")
    assert len(user123_projects) == 1
    assert user123_projects[0].id == project1.id
    
    # List projects for user456 (should see only project2)
    user456_projects = await project_service.list_projects("user456")
    assert len(user456_projects) == 1
    assert user456_projects[0].id == project2.id


@pytest.mark.asyncio
async def test_update_project(project_service, sample_project_config):
    """Test updating a project"""
    project = await project_service.create_project(sample_project_config)
    
    updates = ProjectUpdate(
        name="Updated Project Name",
        description="Updated description"
    )
    
    updated_project = await project_service.update_project(project.id, updates)
    
    assert updated_project.name == "Updated Project Name"
    assert updated_project.description == "Updated description"
    assert updated_project.updated_at > updated_project.created_at


@pytest.mark.asyncio
async def test_update_nonexistent_project(project_service):
    """Test updating a non-existent project"""
    updates = ProjectUpdate(name="New Name")
    
    with pytest.raises(ProjectNotFoundError):
        await project_service.update_project("nonexistent-id", updates)


@pytest.mark.asyncio
async def test_delete_project(project_service, sample_project_config):
    """Test deleting a project"""
    project = await project_service.create_project(sample_project_config)
    
    await project_service.delete_project(project.id)
    
    with pytest.raises(ProjectNotFoundError):
        await project_service.get_project(project.id)


@pytest.mark.asyncio
async def test_validate_project_access(project_service, sample_project_config):
    """Test validating project access"""
    project = await project_service.create_project(sample_project_config)
    
    # Owner should have access
    assert await project_service.validate_project_access("user123", project.id) is True
    
    # Non-member should not have access
    assert await project_service.validate_project_access("user456", project.id) is False
    
    # Non-existent project should return False
    assert await project_service.validate_project_access("user123", "nonexistent-id") is False


@pytest.mark.asyncio
async def test_add_project_member(project_service, sample_project_config):
    """Test adding a member to a project"""
    project = await project_service.create_project(sample_project_config)
    
    updated_project = await project_service.add_project_member(
        project.id, "user456", "developer"
    )
    
    assert len(updated_project.members) == 2
    new_member = next(m for m in updated_project.members if m.user_id == "user456")
    assert new_member.role == "developer"
    assert new_member.added_at is not None


@pytest.mark.asyncio
async def test_add_duplicate_member(project_service, sample_project_config):
    """Test adding a duplicate member"""
    project = await project_service.create_project(sample_project_config)
    
    with pytest.raises(ValueError, match="already a member"):
        await project_service.add_project_member(project.id, "user123", "developer")


@pytest.mark.asyncio
async def test_remove_project_member(project_service, sample_project_config):
    """Test removing a member from a project"""
    project = await project_service.create_project(sample_project_config)
    
    # Add a member first
    await project_service.add_project_member(project.id, "user456", "developer")
    
    # Remove the member
    updated_project = await project_service.remove_project_member(project.id, "user456")
    
    assert len(updated_project.members) == 1
    assert all(m.user_id != "user456" for m in updated_project.members)


@pytest.mark.asyncio
async def test_remove_project_owner(project_service, sample_project_config):
    """Test that owner cannot be removed"""
    project = await project_service.create_project(sample_project_config)
    
    with pytest.raises(ValueError, match="Cannot remove project owner"):
        await project_service.remove_project_member(project.id, "user123")


@pytest.mark.asyncio
async def test_remove_nonexistent_member(project_service, sample_project_config):
    """Test removing a non-existent member"""
    project = await project_service.create_project(sample_project_config)
    
    with pytest.raises(ValueError, match="not a member"):
        await project_service.remove_project_member(project.id, "user456")