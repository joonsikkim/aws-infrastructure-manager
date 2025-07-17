"""
S3-based State Management Service Implementation
"""
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
import asyncio
import tempfile
import os

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from aws_lambda_powertools import Logger

from .interfaces import StateManagementService
from ..models.data_models import (
    InfrastructureState, StateSnapshot, StateMetadata, ChangePlan,
    Change, ChangeAction, RiskLevel, ChangeSummary, ChangePlanStatus
)
from ..models.exceptions import InfrastructureException, ErrorCodes
# Import settings with fallback for testing
try:
    from config.settings import settings
except Exception:
    # Fallback settings for testing
    class MockSettings:
        class AWS:
            access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
            secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            session_token = os.getenv('AWS_SESSION_TOKEN')
            region = os.getenv('AWS_REGION', 'us-east-1')
            profile = os.getenv('AWS_PROFILE')
            state_bucket = os.getenv('AWS_STATE_BUCKET', 'default-bucket')
            state_bucket_prefix = os.getenv('AWS_STATE_BUCKET_PREFIX', 'projects')
        aws = AWS()
    settings = MockSettings()


logger = Logger(service="S3StateManagement")


class S3StateManagementService(StateManagementService):
    """S3-based implementation of state management service"""
    
    def __init__(self, aws_session: Optional[boto3.Session] = None):
        """Initialize S3 state management service
        
        Args:
            aws_session: Optional boto3 session. If None, will create default session.
        """
        if aws_session:
            self.session = aws_session
        else:
            session_kwargs = {
                'aws_access_key_id': settings.aws.access_key_id,
                'aws_secret_access_key': settings.aws.secret_access_key,
                'aws_session_token': settings.aws.session_token,
                'region_name': settings.aws.region,
            }
            if isinstance(settings.aws.profile, str) and settings.aws.profile != '':
                session_kwargs['profile_name'] = settings.aws.profile
            self.session = boto3.Session(**session_kwargs)
        
        self.s3_client = self.session.client('s3')
        self.bucket_name = settings.aws.state_bucket
        self.bucket_prefix = settings.aws.state_bucket_prefix
        
        # Note: Bucket existence will be checked when first operation is performed
    
    async def _ensure_bucket_exists(self) -> None:
        """Ensure the S3 bucket exists, create if it doesn't"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3 bucket {self.bucket_name} exists")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, create it
                try:
                    if settings.aws.region == 'us-east-1':
                        # us-east-1 doesn't need LocationConstraint
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': settings.aws.region}
                        )
                    logger.info(f"Created S3 bucket {self.bucket_name}")
                except ClientError as create_error:
                    logger.error(f"Failed to create S3 bucket: {create_error}")
                    raise InfrastructureException(
                        ErrorCodes.STATE_FILE_CORRUPTED,
                        f"Failed to create S3 bucket: {create_error}",
                        {"bucket": self.bucket_name, "region": settings.aws.region}
                    )
            else:
                logger.error(f"Failed to access S3 bucket: {e}")
                raise InfrastructureException(
                    ErrorCodes.STATE_FILE_CORRUPTED,
                    f"Failed to access S3 bucket: {e}",
                    {"bucket": self.bucket_name}
                )
    
    def _get_state_key(self, project_id: str, version: Optional[str] = None) -> str:
        """Generate S3 key for state file
        
        Args:
            project_id: Project identifier
            version: Optional version string. If None, uses 'current'
            
        Returns:
            S3 key path for the state file
        """
        version = version or "current"
        return f"{self.bucket_prefix}/{project_id}/state/{version}.json"
    
    def _get_history_key(self, project_id: str, timestamp: datetime) -> str:
        """Generate S3 key for historical state file
        
        Args:
            project_id: Project identifier
            timestamp: Timestamp for the historical state
            
        Returns:
            S3 key path for the historical state file
        """
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")
        return f"{self.bucket_prefix}/{project_id}/history/{timestamp_str}.json"
    
    async def get_current_state(self, project_id: str) -> Optional[InfrastructureState]:
        """Get the current infrastructure state for a project
        
        Args:
            project_id: Project identifier
            
        Returns:
            Current infrastructure state or None if not found
        """
        try:
            key = self._get_state_key(project_id)
            
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            content = response['Body'].read().decode('utf-8')
            
            state_data = json.loads(content)
            return self._deserialize_state(state_data)
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.info(f"No current state found for project {project_id}")
                return None
            else:
                logger.error(f"Failed to get current state: {e}")
                raise InfrastructureException(
                    ErrorCodes.STATE_FILE_CORRUPTED,
                    f"Failed to retrieve state from S3: {e}",
                    {"project_id": project_id, "key": key}
                )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse state JSON: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"State file is corrupted: {e}",
                {"project_id": project_id}
            )
        except Exception as e:
            logger.error(f"Unexpected error getting current state: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Unexpected error: {e}",
                {"project_id": project_id}
            )
    
    async def save_state(self, project_id: str, state: InfrastructureState) -> None:
        """Save infrastructure state to S3
        
        Args:
            project_id: Project identifier
            state: Infrastructure state to save
        """
        try:
            # First, backup current state to history if it exists
            current_state = await self.get_current_state(project_id)
            if current_state:
                await self._save_to_history(project_id, current_state)
            
            # Serialize and save new state
            state_data = self._serialize_state(state)
            state_json = json.dumps(state_data, indent=2, default=str)
            
            key = self._get_state_key(project_id)
            
            # Save to S3 with metadata
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=state_json.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'project-id': project_id,
                    'version': state.version,
                    'timestamp': state.timestamp.isoformat(),
                    'last-modified-by': state.metadata.last_modified_by
                }
            )
            
            logger.info(f"Saved state for project {project_id}, version {state.version}")
            
        except ClientError as e:
            logger.error(f"Failed to save state to S3: {e}")
            # Create local backup as fallback
            await self._create_local_backup(project_id, state)
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Failed to save state to S3: {e}",
                {"project_id": project_id}
            )
        except Exception as e:
            logger.error(f"Unexpected error saving state: {e}")
            await self._create_local_backup(project_id, state)
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Unexpected error saving state: {e}",
                {"project_id": project_id}
            )
    
    async def get_state_history(self, project_id: str, limit: Optional[int] = None) -> List[StateSnapshot]:
        """Get historical state snapshots
        
        Args:
            project_id: Project identifier
            limit: Maximum number of snapshots to return
            
        Returns:
            List of historical state snapshots, sorted by timestamp (newest first)
        """
        try:
            prefix = f"{self.bucket_prefix}/{project_id}/history/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            snapshots = []
            
            if 'Contents' in response:
                # Sort by last modified (newest first)
                objects = sorted(
                    response['Contents'],
                    key=lambda x: x['LastModified'],
                    reverse=True
                )
                
                # Apply limit if specified
                if limit:
                    objects = objects[:limit]
                
                for obj in objects:
                    # Extract timestamp from key
                    key_parts = obj['Key'].split('/')
                    filename = key_parts[-1].replace('.json', '')
                    
                    try:
                        # Parse timestamp from filename (format: YYYYMMDD_HHMMSS_microseconds)
                        timestamp = datetime.strptime(filename, "%Y%m%d_%H%M%S_%f")
                        
                        # Get metadata to extract change description
                        head_response = self.s3_client.head_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                        
                        metadata = head_response.get('Metadata', {})
                        change_description = metadata.get('change-description', 'State update')
                        version = metadata.get('version', 'unknown')
                        
                        snapshot = StateSnapshot(
                            version=version,
                            timestamp=timestamp,
                            change_description=change_description,
                            s3_location=f"s3://{self.bucket_name}/{obj['Key']}"
                        )
                        snapshots.append(snapshot)
                        
                    except ValueError as e:
                        logger.warning(f"Failed to parse timestamp from key {obj['Key']}: {e}")
                        continue
            
            logger.info(f"Retrieved {len(snapshots)} historical snapshots for project {project_id}")
            return snapshots
            
        except ClientError as e:
            logger.error(f"Failed to get state history: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Failed to retrieve state history: {e}",
                {"project_id": project_id}
            )
        except Exception as e:
            logger.error(f"Unexpected error getting state history: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Unexpected error: {e}",
                {"project_id": project_id}
            )
    
    def compare_states(self, current_state: InfrastructureState, desired_state: InfrastructureState) -> ChangePlan:
        """Compare two states and generate a change plan
        
        Args:
            current_state: Current infrastructure state
            desired_state: Desired infrastructure state
            
        Returns:
            Change plan describing the differences
        """
        changes = []
        
        # Create resource maps for easier comparison
        current_resources = {r.id: r for r in current_state.resources}
        desired_resources = {r.id: r for r in desired_state.resources}
        
        # Find resources to create (in desired but not in current)
        for resource_id, resource in desired_resources.items():
            if resource_id not in current_resources:
                changes.append(Change(
                    action=ChangeAction.CREATE,
                    resource_type=resource.type,
                    resource_id=resource_id,
                    desired_config=self._resource_to_config(resource),
                    risk_level=RiskLevel.LOW
                ))
        
        # Find resources to update or delete
        for resource_id, current_resource in current_resources.items():
            if resource_id in desired_resources:
                desired_resource = desired_resources[resource_id]
                
                # Check if resource needs updating
                if self._resources_differ(current_resource, desired_resource):
                    changes.append(Change(
                        action=ChangeAction.UPDATE,
                        resource_type=current_resource.type,
                        resource_id=resource_id,
                        current_config=self._resource_to_config(current_resource),
                        desired_config=self._resource_to_config(desired_resource),
                        risk_level=self._assess_update_risk(current_resource, desired_resource)
                    ))
            else:
                # Resource exists in current but not in desired - delete it
                changes.append(Change(
                    action=ChangeAction.DELETE,
                    resource_type=current_resource.type,
                    resource_id=resource_id,
                    current_config=self._resource_to_config(current_resource),
                    risk_level=RiskLevel.HIGH  # Deletions are always high risk
                ))
        
        # Create summary
        summary = ChangeSummary(
            total_changes=len(changes),
            creates=len([c for c in changes if c.action == ChangeAction.CREATE]),
            updates=len([c for c in changes if c.action == ChangeAction.UPDATE]),
            deletes=len([c for c in changes if c.action == ChangeAction.DELETE])
        )
        
        # Generate change plan
        plan = ChangePlan(
            id=str(uuid.uuid4()),
            project_id=desired_state.project_id,
            summary=summary,
            changes=changes,
            created_at=datetime.now(),
            status=ChangePlanStatus.PENDING
        )
        
        logger.info(f"Generated change plan with {len(changes)} changes for project {desired_state.project_id}")
        return plan    

    async def _save_to_history(self, project_id: str, state: InfrastructureState) -> None:
        """Save current state to history before updating
        
        Args:
            project_id: Project identifier
            state: State to save to history
        """
        try:
            history_key = self._get_history_key(project_id, state.timestamp)
            state_data = self._serialize_state(state)
            state_json = json.dumps(state_data, indent=2, default=str)
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=history_key,
                Body=state_json.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'project-id': project_id,
                    'version': state.version,
                    'timestamp': state.timestamp.isoformat(),
                    'change-description': state.metadata.change_description,
                    'last-modified-by': state.metadata.last_modified_by
                }
            )
            
            logger.info(f"Saved historical state for project {project_id} at {state.timestamp}")
            
        except ClientError as e:
            logger.error(f"Failed to save historical state: {e}")
            # Don't raise exception here as this is a backup operation
    
    async def _create_local_backup(self, project_id: str, state: InfrastructureState) -> None:
        """Create local backup when S3 save fails
        
        Args:
            project_id: Project identifier
            state: State to backup locally
        """
        try:
            # Create backup directory
            backup_dir = Path(tempfile.gettempdir()) / "aws-infra-manager-backup"
            backup_dir.mkdir(exist_ok=True)
            
            # Generate backup filename
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"{project_id}_{timestamp_str}.json"
            
            # Save state to local file
            state_data = self._serialize_state(state)
            with open(backup_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
            
            logger.warning(f"Created local backup at {backup_file}")
            
        except Exception as e:
            logger.error(f"Failed to create local backup: {e}")
    
    def _serialize_state(self, state: InfrastructureState) -> Dict[str, Any]:
        """Serialize infrastructure state to dictionary
        
        Args:
            state: Infrastructure state to serialize
            
        Returns:
            Dictionary representation of the state
        """
        return {
            "version": "1.0.0",
            "projectId": state.project_id,
            "timestamp": state.timestamp.isoformat(),
            "metadata": {
                "lastModifiedBy": state.metadata.last_modified_by,
                "changeDescription": state.metadata.change_description,
                "changePlanId": state.metadata.change_plan_id
            },
            "resources": [
                {
                    "id": resource.id,
                    "type": resource.type,
                    "name": resource.name,
                    "arn": resource.arn,
                    "region": resource.region,
                    "properties": resource.properties,
                    "tags": resource.tags,
                    "status": resource.status.value,
                    "createdAt": resource.created_at.isoformat(),
                    "updatedAt": resource.updated_at.isoformat()
                }
                for resource in state.resources
            ]
        }
    
    def _deserialize_state(self, data: Dict[str, Any]) -> InfrastructureState:
        """Deserialize infrastructure state from dictionary
        
        Args:
            data: Dictionary representation of the state
            
        Returns:
            Infrastructure state object
        """
        from ..models.enums import ResourceStatus
        from ..models.data_models import Resource
        
        metadata = StateMetadata(
            last_modified_by=data["metadata"]["lastModifiedBy"],
            change_description=data["metadata"]["changeDescription"],
            change_plan_id=data["metadata"].get("changePlanId")
        )
        
        resources = []
        for resource_data in data["resources"]:
            resource = Resource(
                id=resource_data["id"],
                project_id=data["projectId"],
                type=resource_data["type"],
                name=resource_data["name"],
                region=resource_data["region"],
                properties=resource_data["properties"],
                tags=resource_data["tags"],
                status=ResourceStatus(resource_data["status"]),
                created_at=datetime.fromisoformat(resource_data["createdAt"]),
                updated_at=datetime.fromisoformat(resource_data["updatedAt"]),
                arn=resource_data.get("arn")
            )
            resources.append(resource)
        
        return InfrastructureState(
            project_id=data["projectId"],
            version=data.get("version", "1.0.0"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            resources=resources,
            metadata=metadata
        )
    
    def _resource_to_config(self, resource) -> 'ResourceConfig':
        """Convert Resource to ResourceConfig
        
        Args:
            resource: Resource object
            
        Returns:
            ResourceConfig object
        """
        from ..models.data_models import ResourceConfig
        
        return ResourceConfig(
            type=resource.type,
            name=resource.name,
            properties=resource.properties,
            tags=resource.tags
        )
    
    def _resources_differ(self, current, desired) -> bool:
        """Check if two resources differ in meaningful ways
        
        Args:
            current: Current resource
            desired: Desired resource
            
        Returns:
            True if resources differ and update is needed
        """
        # Compare properties (excluding timestamps and status)
        if current.properties != desired.properties:
            return True
        
        # Compare tags
        if current.tags != desired.tags:
            return True
        
        # Compare name
        if current.name != desired.name:
            return True
        
        return False
    
    def _get_plan_key(self, project_id: str, plan_id: str) -> str:
        """Generate S3 key for change plan file
        
        Args:
            project_id: Project identifier
            plan_id: Change plan identifier
            
        Returns:
            S3 key path for the change plan file
        """
        return f"{self.bucket_prefix}/{project_id}/plans/{plan_id}.json"

    async def save_change_plan(self, project_id: str, plan: ChangePlan) -> None:
        """Save a change plan to S3
        
        Args:
            project_id: Project identifier
            plan: Change plan to save
        """
        try:
            plan_data = self._serialize_plan(plan)
            plan_json = json.dumps(plan_data, indent=2, default=str)
            
            key = self._get_plan_key(project_id, plan.id)
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=plan_json.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'project-id': project_id,
                    'plan-id': plan.id,
                    'status': plan.status.value,
                    'created-at': plan.created_at.isoformat()
                }
            )
            
            logger.info(f"Saved change plan {plan.id} for project {project_id}")
            
        except ClientError as e:
            logger.error(f"Failed to save change plan to S3: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Failed to save change plan to S3: {e}",
                {"project_id": project_id, "plan_id": plan.id}
            )

    async def get_change_plan(self, project_id: str, plan_id: str) -> Optional[ChangePlan]:
        """Get a specific change plan from S3
        
        Args:
            project_id: Project identifier
            plan_id: Change plan identifier
            
        Returns:
            The change plan or None if not found
        """
        try:
            key = self._get_plan_key(project_id, plan_id)
            
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            content = response['Body'].read().decode('utf-8')
            
            plan_data = json.loads(content)
            return self._deserialize_plan(plan_data)
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.info(f"Change plan {plan_id} not found for project {project_id}")
                return None
            else:
                logger.error(f"Failed to get change plan: {e}")
                raise InfrastructureException(
                    ErrorCodes.STATE_FILE_CORRUPTED,
                    f"Failed to retrieve change plan from S3: {e}",
                    {"project_id": project_id, "plan_id": plan_id}
                )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse change plan JSON: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Change plan file is corrupted: {e}",
                {"project_id": project_id, "plan_id": plan_id}
            )

    async def list_change_plans(self, project_id: str) -> List[ChangePlan]:
        """List all change plans for a project from S3
        
        Args:
            project_id: Project identifier
            
        Returns:
            A list of change plans
        """
        plans = []
        try:
            prefix = f"{self.bucket_prefix}/{project_id}/plans/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    try:
                        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                        content = response['Body'].read().decode('utf-8')
                        plan_data = json.loads(content)
                        plans.append(self._deserialize_plan(plan_data))
                    except Exception as e:
                        logger.warning(f"Failed to read or parse plan {key}: {e}")

            logger.info(f"Retrieved {len(plans)} change plans for project {project_id}")
            return plans

        except ClientError as e:
            logger.error(f"Failed to list change plans from S3: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Failed to list change plans from S3: {e}",
                {"project_id": project_id}
            )

    def _serialize_plan(self, plan: ChangePlan) -> Dict[str, Any]:
        """Serialize a ChangePlan to a dictionary
        
        Args:
            plan: The ChangePlan object
            
        Returns:
            A dictionary representation of the change plan
        """
        return {
            "id": plan.id,
            "projectId": plan.project_id,
            "summary": {
                "totalChanges": plan.summary.total_changes,
                "creates": plan.summary.creates,
                "updates": plan.summary.updates,
                "deletes": plan.summary.deletes,
                "estimatedCost": plan.summary.estimated_cost,
                "estimatedDuration": plan.summary.estimated_duration,
            },
            "changes": [
                {
                    "action": change.action.value,
                    "resourceType": change.resource_type,
                    "resourceId": change.resource_id,
                    "riskLevel": change.risk_level.value,
                    "currentConfig": change.current_config.__dict__ if change.current_config else None,
                    "desiredConfig": change.desired_config.__dict__ if change.desired_config else None,
                    "dependencies": change.dependencies,
                }
                for change in plan.changes
            ],
            "createdAt": plan.created_at.isoformat(),
            "status": plan.status.value,
            "createdBy": plan.created_by,
            "approvedBy": plan.approved_by,
            "approvedAt": plan.approved_at.isoformat() if plan.approved_at else None,
        }

    def _deserialize_plan(self, data: Dict[str, Any]) -> ChangePlan:
        """Deserialize a dictionary to a ChangePlan object
        
        Args:
            data: The dictionary representation of the change plan
            
        Returns:
            A ChangePlan object
        """
        summary_data = data["summary"]
        summary = ChangeSummary(
            total_changes=summary_data["totalChanges"],
            creates=summary_data["creates"],
            updates=summary_data["updates"],
            deletes=summary_data["deletes"],
            estimated_cost=summary_data.get("estimatedCost"),
            estimated_duration=summary_data.get("estimatedDuration"),
        )

        changes = []
        for change_data in data["changes"]:
            change = Change(
                action=ChangeAction(change_data["action"]),
                resource_type=change_data["resourceType"],
                resource_id=change_data["resourceId"],
                risk_level=RiskLevel(change_data["riskLevel"]),
                current_config=change_data.get("currentConfig"),
                desired_config=change_data.get("desiredConfig"),
                dependencies=change_data.get("dependencies", []),
            )
            changes.append(change)

        return ChangePlan(
            id=data["id"],
            project_id=data["projectId"],
            summary=summary,
            changes=changes,
            created_at=datetime.fromisoformat(data["createdAt"]),
            status=ChangePlanStatus(data["status"]),
            created_by=data.get("createdBy"),
            approved_by=data.get("approvedBy"),
            approved_at=datetime.fromisoformat(data["approvedAt"]) if data.get("approvedAt") else None,
        )

    
    def _assess_update_risk(self, current, desired) -> RiskLevel:
        """Assess the risk level of updating a resource
        
        Args:
            current: Current resource
            desired: Desired resource
            
        Returns:
            Risk level for the update
        """
        # High-risk resource types
        high_risk_types = {
            'RDS::DBInstance',
            'EC2::Instance',
            'Lambda::Function',
            'ECS::Service'
        }
        
        # High-risk property changes
        high_risk_properties = {
            'instanceType',
            'dbInstanceClass',
            'engine',
            'engineVersion',
            'allocatedStorage'
        }
        
        if current.type in high_risk_types:
            # Check if high-risk properties are changing
            current_props = current.properties
            desired_props = desired.properties
            
            for prop in high_risk_properties:
                if (prop in current_props and prop in desired_props and 
                    current_props[prop] != desired_props[prop]):
                    return RiskLevel.HIGH
        
        # Medium risk for any property changes on important resources
        if current.type in high_risk_types:
            return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    async def get_state_by_version(self, project_id: str, version: str) -> Optional[InfrastructureState]:
        """Get infrastructure state by specific version
        
        Args:
            project_id: Project identifier
            version: Version identifier
            
        Returns:
            Infrastructure state for the specified version or None if not found
        """
        try:
            key = self._get_state_key(project_id, version)
            
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            content = response['Body'].read().decode('utf-8')
            
            state_data = json.loads(content)
            return self._deserialize_state(state_data)
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.info(f"No state found for project {project_id}, version {version}")
                return None
            else:
                logger.error(f"Failed to get state by version: {e}")
                raise InfrastructureException(
                    ErrorCodes.STATE_FILE_CORRUPTED,
                    f"Failed to retrieve state from S3: {e}",
                    {"project_id": project_id, "version": version}
                )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse state JSON: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"State file is corrupted: {e}",
                {"project_id": project_id, "version": version}
            )
    
    async def delete_project_state(self, project_id: str) -> None:
        """Delete all state files for a project
        
        Args:
            project_id: Project identifier
        """
        try:
            prefix = f"{self.bucket_prefix}/{project_id}/"
            
            # List all objects with the project prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' in response:
                # Delete all objects
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects_to_delete}
                )
                
                logger.info(f"Deleted {len(objects_to_delete)} state files for project {project_id}")
            else:
                logger.info(f"No state files found for project {project_id}")
                
        except ClientError as e:
            logger.error(f"Failed to delete project state: {e}")
            raise InfrastructureException(
                ErrorCodes.STATE_FILE_CORRUPTED,
                f"Failed to delete project state: {e}",
                {"project_id": project_id}
            )
    
    async def validate_state_integrity(self, project_id: str) -> bool:
        """Validate the integrity of stored state files
        
        Args:
            project_id: Project identifier
            
        Returns:
            True if state files are valid, False otherwise
        """
        try:
            # Check current state
            current_state = await self.get_current_state(project_id)
            if current_state is None:
                return True  # No state is valid
            
            # Validate current state structure
            if not self._validate_state_structure(current_state):
                return False
            
            # Check a few historical states
            history = await self.get_state_history(project_id, limit=5)
            for snapshot in history:
                try:
                    # Try to load historical state
                    key = snapshot.s3_location.replace(f"s3://{self.bucket_name}/", "")
                    response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                    content = response['Body'].read().decode('utf-8')
                    state_data = json.loads(content)
                    historical_state = self._deserialize_state(state_data)
                    
                    if not self._validate_state_structure(historical_state):
                        return False
                        
                except Exception as e:
                    logger.warning(f"Failed to validate historical state {snapshot.version}: {e}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate state integrity: {e}")
            return False
    
    def _validate_state_structure(self, state: InfrastructureState) -> bool:
        """Validate the structure of a state object
        
        Args:
            state: State object to validate
            
        Returns:
            True if structure is valid
        """
        try:
            # Basic structure validation
            if not state.project_id or not state.version or not state.timestamp:
                return False
            
            if not state.metadata or not state.metadata.last_modified_by:
                return False
            
            # Validate resources
            for resource in state.resources:
                if not resource.id or not resource.type or not resource.name:
                    return False
                
                if not resource.region or not resource.status:
                    return False
            
            return True
            
        except Exception:
            return False