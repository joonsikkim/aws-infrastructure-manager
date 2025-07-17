"""
Unit tests for View Service
"""
import pytest
import time
from datetime import datetime
from typing import List, Dict

from src.services.view_service import ViewService
from src.models.data_models import View, Dashboard, ResourceFilter
from src.models.enums import ResourceStatus


@pytest.fixture
def view_service():
    """Create view service instance for testing"""
    return ViewService()


@pytest.fixture
def sample_filter():
    """Create a sample resource filter"""
    return ResourceFilter(
        resource_type="EC2::Instance",
        status=ResourceStatus.ACTIVE,
        tags={"Environment": "test"}
    )


@pytest.fixture
async def sample_view(view_service, sample_filter):
    """Create a sample view"""
    return await view_service.create_view(
        project_id="project-123",
        name="Test View",
        filters=sample_filter,
        user_id="user-456"
    )


@pytest.fixture
async def sample_views(view_service, sample_filter):
    """Create multiple sample views"""
    views = []
    views.append(await view_service.create_view(
        project_id="project-123",
        name="Test View 1",
        filters=sample_filter,
        user_id="user-456"
    ))
    views.append(await view_service.create_view(
        project_id="project-123",
        name="Test View 2",
        filters=sample_filter,
        user_id="user-456"
    ))
    views.append(await view_service.create_view(
        project_id="project-456",
        name="Other Project View",
        filters=sample_filter,
        user_id="user-456"
    ))
    return views


@pytest.fixture
async def sample_dashboard(view_service, sample_views):
    """Create a sample dashboard"""
    return await view_service.create_dashboard(
        project_id="project-123",
        name="Test Dashboard",
        description="Test dashboard description",
        view_ids=[sample_views[0].id, sample_views[1].id],
        user_id="user-456"
    )


class TestViewService:
    """Test cases for ViewService"""
    
    @pytest.mark.asyncio
    async def test_create_view(self, view_service, sample_filter):
        """Test creating a view"""
        view = await view_service.create_view(
            project_id="project-123",
            name="Test View",
            filters=sample_filter,
            user_id="user-456"
        )
        
        assert view is not None
        assert view.id is not None
        assert view.project_id == "project-123"
        assert view.name == "Test View"
        assert view.filters == sample_filter
        assert view.created_by == "user-456"
        assert isinstance(view.created_at, datetime)
        assert isinstance(view.updated_at, datetime)
    
    @pytest.mark.asyncio
    async def test_get_view(self, view_service, sample_view):
        """Test getting a view by ID"""
        view = await view_service.get_view(sample_view.id)
        
        assert view is not None
        assert view.id == sample_view.id
        assert view.name == sample_view.name
    
    @pytest.mark.asyncio
    async def test_get_view_not_found(self, view_service):
        """Test getting a non-existent view"""
        view = await view_service.get_view("nonexistent-id")
        assert view is None
    
    @pytest.mark.asyncio
    async def test_get_views_by_project(self, view_service, sample_views):
        """Test getting views by project"""
        views = await view_service.get_views_by_project("project-123")
        
        assert len(views) == 2
        assert all(view.project_id == "project-123" for view in views)
        
        # Check other project
        other_views = await view_service.get_views_by_project("project-456")
        assert len(other_views) == 1
        assert other_views[0].project_id == "project-456"
        
        # Check non-existent project
        empty_views = await view_service.get_views_by_project("nonexistent")
        assert len(empty_views) == 0
    
    @pytest.mark.asyncio
    async def test_update_view(self, view_service, sample_view, sample_filter):
        """Test updating a view"""
        # Create updated filter
        updated_filter = ResourceFilter(
            resource_type="S3::Bucket",
            status=ResourceStatus.ACTIVE,
            tags={"Environment": "production"}
        )
        
        updated_view = await view_service.update_view(
            view_id=sample_view.id,
            name="Updated View",
            filters=updated_filter
        )
        
        assert updated_view is not None
        assert updated_view.id == sample_view.id
        assert updated_view.name == "Updated View"
        assert updated_view.filters.resource_type == "S3::Bucket"
        assert updated_view.filters.tags["Environment"] == "production"
        # Add a small sleep to ensure updated_at is different
        import time
        time.sleep(0.001)
        assert updated_view.updated_at >= sample_view.updated_at
        
        # Verify changes were persisted
        retrieved_view = await view_service.get_view(sample_view.id)
        assert retrieved_view.name == "Updated View"
    
    @pytest.mark.asyncio
    async def test_update_view_not_found(self, view_service, sample_filter):
        """Test updating a non-existent view"""
        result = await view_service.update_view(
            view_id="nonexistent-id",
            name="Updated View",
            filters=sample_filter
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_view(self, view_service, sample_view):
        """Test deleting a view"""
        result = await view_service.delete_view(sample_view.id)
        
        assert result is True
        
        # Verify view was deleted
        deleted_view = await view_service.get_view(sample_view.id)
        assert deleted_view is None
    
    @pytest.mark.asyncio
    async def test_delete_view_not_found(self, view_service):
        """Test deleting a non-existent view"""
        result = await view_service.delete_view("nonexistent-id")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_create_dashboard(self, view_service, sample_views):
        """Test creating a dashboard"""
        dashboard = await view_service.create_dashboard(
            project_id="project-123",
            name="Test Dashboard",
            description="Test dashboard description",
            view_ids=[sample_views[0].id, sample_views[1].id],
            user_id="user-456"
        )
        
        assert dashboard is not None
        assert dashboard.id is not None
        assert dashboard.project_id == "project-123"
        assert dashboard.name == "Test Dashboard"
        assert dashboard.description == "Test dashboard description"
        assert len(dashboard.views) == 2
        assert sample_views[0].id in dashboard.views
        assert sample_views[1].id in dashboard.views
        assert dashboard.created_by == "user-456"
        assert isinstance(dashboard.created_at, datetime)
        assert isinstance(dashboard.updated_at, datetime)
    
    @pytest.mark.asyncio
    async def test_get_dashboard(self, view_service, sample_dashboard):
        """Test getting a dashboard by ID"""
        dashboard = await view_service.get_dashboard(sample_dashboard.id)
        
        assert dashboard is not None
        assert dashboard.id == sample_dashboard.id
        assert dashboard.name == sample_dashboard.name
    
    @pytest.mark.asyncio
    async def test_get_dashboard_not_found(self, view_service):
        """Test getting a non-existent dashboard"""
        dashboard = await view_service.get_dashboard("nonexistent-id")
        assert dashboard is None
    
    @pytest.mark.asyncio
    async def test_get_dashboards_by_project(self, view_service, sample_dashboard):
        """Test getting dashboards by project"""
        # Create another dashboard for a different project
        await view_service.create_dashboard(
            project_id="project-456",
            name="Other Dashboard",
            description="Other dashboard description",
            view_ids=[],
            user_id="user-456"
        )
        
        # Get dashboards for first project
        dashboards = await view_service.get_dashboards_by_project("project-123")
        
        assert len(dashboards) == 1
        assert dashboards[0].id == sample_dashboard.id
        
        # Get dashboards for second project
        other_dashboards = await view_service.get_dashboards_by_project("project-456")
        assert len(other_dashboards) == 1
        assert other_dashboards[0].project_id == "project-456"
        
        # Get dashboards for non-existent project
        empty_dashboards = await view_service.get_dashboards_by_project("nonexistent")
        assert len(empty_dashboards) == 0
    
    @pytest.mark.asyncio
    async def test_update_dashboard(self, view_service, sample_dashboard, sample_views):
        """Test updating a dashboard"""
        updated_dashboard = await view_service.update_dashboard(
            dashboard_id=sample_dashboard.id,
            name="Updated Dashboard",
            description="Updated description",
            view_ids=[sample_views[0].id]  # Remove one view
        )
        
        assert updated_dashboard is not None
        assert updated_dashboard.id == sample_dashboard.id
        assert updated_dashboard.name == "Updated Dashboard"
        assert updated_dashboard.description == "Updated description"
        assert len(updated_dashboard.views) == 1
        assert updated_dashboard.views[0] == sample_views[0].id
        # Add a small sleep to ensure updated_at is different
        import time
        time.sleep(0.001)
        assert updated_dashboard.updated_at >= sample_dashboard.updated_at
        
        # Verify changes were persisted
        retrieved_dashboard = await view_service.get_dashboard(sample_dashboard.id)
        assert retrieved_dashboard.name == "Updated Dashboard"
        assert len(retrieved_dashboard.views) == 1
    
    @pytest.mark.asyncio
    async def test_update_dashboard_not_found(self, view_service):
        """Test updating a non-existent dashboard"""
        result = await view_service.update_dashboard(
            dashboard_id="nonexistent-id",
            name="Updated Dashboard",
            description="Updated description",
            view_ids=[]
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_dashboard(self, view_service, sample_dashboard):
        """Test deleting a dashboard"""
        result = await view_service.delete_dashboard(sample_dashboard.id)
        
        assert result is True
        
        # Verify dashboard was deleted
        deleted_dashboard = await view_service.get_dashboard(sample_dashboard.id)
        assert deleted_dashboard is None
    
    @pytest.mark.asyncio
    async def test_delete_dashboard_not_found(self, view_service):
        """Test deleting a non-existent dashboard"""
        result = await view_service.delete_dashboard("nonexistent-id")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_view_removes_from_dashboards(self, view_service, sample_views, sample_dashboard):
        """Test that deleting a view removes it from dashboards"""
        # Delete the first view
        await view_service.delete_view(sample_views[0].id)
        
        # Check that the view was removed from the dashboard
        dashboard = await view_service.get_dashboard(sample_dashboard.id)
        assert len(dashboard.views) == 1
        assert sample_views[0].id not in dashboard.views
        assert sample_views[1].id in dashboard.views