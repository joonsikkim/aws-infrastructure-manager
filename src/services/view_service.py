"""
View and Dashboard Service
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from src.models.data_models import View, Dashboard, ResourceFilter
from src.models.enums import ErrorCodes
from src.models.exceptions import InfrastructureException


class ViewService:
    """
    Service for managing views and dashboards
    """

    def __init__(self):
        """
        Initialize the view service
        """
        # In-memory storage for demo
        self._views: Dict[str, View] = {}
        self._dashboards: Dict[str, Dashboard] = {}

    async def create_view(self, project_id: str, name: str, filters: ResourceFilter, user_id: str) -> View:
        """
        Create a new view
        """
        view_id = str(uuid.uuid4())
        view = View(
            id=view_id,
            project_id=project_id,
            name=name,
            filters=filters,
            created_by=user_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._views[view_id] = view
        return view

    async def get_view(self, view_id: str) -> Optional[View]:
        """
        Get a view by ID
        """
        return self._views.get(view_id)

    async def get_views_by_project(self, project_id: str) -> List[View]:
        """
        Get all views for a project
        """
        return [view for view in self._views.values() if view.project_id == project_id]

    async def update_view(self, view_id: str, name: str, filters: ResourceFilter) -> Optional[View]:
        """
        Update a view
        """
        if view_id not in self._views:
            return None
        view = self._views[view_id]
        view.name = name
        view.filters = filters
        view.updated_at = datetime.now()
        self._views[view_id] = view
        return view

    async def delete_view(self, view_id: str) -> bool:
        """
        Delete a view
        """
        if view_id in self._views:
            del self._views[view_id]
            # Also remove from any dashboards
            for dashboard in self._dashboards.values():
                if view_id in dashboard.views:
                    dashboard.views.remove(view_id)
            return True
        return False

    async def create_dashboard(self, project_id: str, name: str, description: str, view_ids: List[str], user_id: str) -> Dashboard:
        """
        Create a new dashboard
        """
        dashboard_id = str(uuid.uuid4())
        dashboard = Dashboard(
            id=dashboard_id,
            project_id=project_id,
            name=name,
            description=description,
            views=view_ids,
            created_by=user_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._dashboards[dashboard_id] = dashboard
        return dashboard

    async def get_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        """
        Get a dashboard by ID
        """
        return self._dashboards.get(dashboard_id)

    async def get_dashboards_by_project(self, project_id: str) -> List[Dashboard]:
        """
        Get all dashboards for a project
        """
        return [dashboard for dashboard in self._dashboards.values() if dashboard.project_id == project_id]

    async def update_dashboard(self, dashboard_id: str, name: str, description: str, view_ids: List[str]) -> Optional[Dashboard]:
        """
        Update a dashboard
        """
        if dashboard_id not in self._dashboards:
            return None
        dashboard = self._dashboards[dashboard_id]
        dashboard.name = name
        dashboard.description = description
        dashboard.views = view_ids
        dashboard.updated_at = datetime.now()
        self._dashboards[dashboard_id] = dashboard
        return dashboard

    async def delete_dashboard(self, dashboard_id: str) -> bool:
        """
        Delete a dashboard
        """
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]
            return True
        return False
