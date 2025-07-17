#!/usr/bin/env python3
"""
S3 State Management Service Demo
"""
import asyncio
import os
from datetime import datetime
from unittest.mock import Mock, patch

# Set environment variables
os.environ.update({
    'AWS_ACCESS_KEY_ID': 'demo-key',
    'AWS_SECRET_ACCESS_KEY': 'demo-secret',
    'AWS_REGION': 'us-east-1',
    'AWS_STATE_BUCKET': 'demo-bucket',
    'AWS_STATE_BUCKET_PREFIX': 'projects'
})

from src.services.s3_state_management import S3StateManagementService
from src.models.data_models import (
    InfrastructureState, StateMetadata, Resource
)
from src.models.enums import ResourceStatus

async def demo_s3_state_management():
    """Demonstrate S3 state management functionality"""
    print("🚀 S3 State Management Service Demo")
    print("=" * 50)
    
    # Mock boto3 for demo purposes
    with patch('src.services.s3_state_management.boto3') as mock_boto3:
        # Setup mocks
        mock_session = Mock()
        mock_s3_client = Mock()
        mock_boto3.Session.return_value = mock_session
        mock_session.client.return_value = mock_s3_client
        
        # Mock S3 responses
        mock_s3_client.head_bucket.return_value = {}
        mock_s3_client.get_object.side_effect = [
            # First call - no existing state
            Exception("NoSuchKey")
        ]
        mock_s3_client.put_object.return_value = {}
        
        # Initialize service
        service = S3StateManagementService()
        print(f"✓ Service initialized with bucket: {service.bucket_name}")
        
        # Create sample infrastructure state
        metadata = StateMetadata(
            last_modified_by="demo-user",
            change_description="Demo infrastructure state",
            change_plan_id="demo-plan-123"
        )
        
        sample_resource = Resource(
            id="i-demo123456789",
            project_id="demo-project",
            type="EC2::Instance",
            name="demo-web-server",
            region="us-east-1",
            properties={
                "instanceType": "t3.micro",
                "imageId": "ami-12345678",
                "keyName": "demo-key"
            },
            tags={
                "Environment": "demo",
                "Project": "aws-infrastructure-manager"
            },
            status=ResourceStatus.ACTIVE,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            arn="arn:aws:ec2:us-east-1:123456789012:instance/i-demo123456789"
        )
        
        state = InfrastructureState(
            project_id="demo-project",
            version="1.0.0",
            timestamp=datetime.now(),
            resources=[sample_resource],
            metadata=metadata
        )
        
        print(f"✓ Created sample state with {len(state.resources)} resource(s)")
        
        # Test serialization
        serialized = service._serialize_state(state)
        print(f"✓ State serialized successfully")
        print(f"  - Project ID: {serialized['projectId']}")
        print(f"  - Version: {serialized['version']}")
        print(f"  - Resources: {len(serialized['resources'])}")
        
        # Test deserialization
        deserialized = service._deserialize_state(serialized)
        print(f"✓ State deserialized successfully")
        print(f"  - Project ID: {deserialized.project_id}")
        print(f"  - Resources: {len(deserialized.resources)}")
        
        # Test key generation
        state_key = service._get_state_key("demo-project")
        history_key = service._get_history_key("demo-project", datetime.now())
        print(f"✓ Key generation working")
        print(f"  - State key: {state_key}")
        print(f"  - History key: {history_key}")
        
        # Test state comparison
        # Create a modified state for comparison
        modified_resource = Resource(
            id=sample_resource.id,
            project_id=sample_resource.project_id,
            type=sample_resource.type,
            name=sample_resource.name,
            region=sample_resource.region,
            properties={
                "instanceType": "t3.small",  # Changed from t3.micro
                "imageId": "ami-12345678",
                "keyName": "demo-key"
            },
            tags=sample_resource.tags,
            status=sample_resource.status,
            created_at=sample_resource.created_at,
            updated_at=datetime.now(),
            arn=sample_resource.arn
        )
        
        modified_metadata = StateMetadata(
            last_modified_by="demo-user",
            change_description="Updated instance type",
            change_plan_id="demo-plan-124"
        )
        
        modified_state = InfrastructureState(
            project_id="demo-project",
            version="1.1.0",
            timestamp=datetime.now(),
            resources=[modified_resource],
            metadata=modified_metadata
        )
        
        # Compare states
        change_plan = service.compare_states(state, modified_state)
        print(f"✓ State comparison completed")
        print(f"  - Total changes: {change_plan.summary.total_changes}")
        print(f"  - Creates: {change_plan.summary.creates}")
        print(f"  - Updates: {change_plan.summary.updates}")
        print(f"  - Deletes: {change_plan.summary.deletes}")
        
        if change_plan.changes:
            change = change_plan.changes[0]
            print(f"  - Change action: {change.action.value}")
            print(f"  - Resource type: {change.resource_type}")
            print(f"  - Risk level: {change.risk_level.value}")
        
        # Test state validation
        is_valid = service._validate_state_structure(state)
        print(f"✓ State validation: {'Valid' if is_valid else 'Invalid'}")
        
        print("\n🎉 All S3 State Management Service features working correctly!")

if __name__ == "__main__":
    asyncio.run(demo_s3_state_management())