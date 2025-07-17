"""
Simple validation tests for S3 State Management Service
"""
import os
import sys
from unittest.mock import Mock, patch

# Set test environment variables before any imports
os.environ.update({
    'SECRET_KEY': 'test-secret-key',
    'AWS_ACCESS_KEY_ID': 'test-key',
    'AWS_SECRET_ACCESS_KEY': 'test-secret',
    'AWS_REGION': 'us-east-1',
    'AWS_STATE_BUCKET': 'test-bucket',
    'AWS_STATE_BUCKET_PREFIX': 'projects'
})

def test_s3_service_can_be_imported():
    """Test that S3StateManagementService can be imported successfully"""
    try:
        from src.services.s3_state_management import S3StateManagementService
        assert S3StateManagementService is not None
        print("✓ S3StateManagementService imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import S3StateManagementService: {e}")
        return False

def test_s3_service_initialization():
    """Test that S3StateManagementService can be initialized with mocked dependencies"""
    try:
        with patch('src.services.s3_state_management.boto3') as mock_boto3:
            # Mock boto3 session and client
            mock_session = Mock()
            mock_s3_client = Mock()
            mock_boto3.Session.return_value = mock_session
            mock_session.client.return_value = mock_s3_client
            
            # Mock head_bucket to simulate existing bucket
            mock_s3_client.head_bucket.return_value = {}
            
            from src.services.s3_state_management import S3StateManagementService
            service = S3StateManagementService()
            
            assert service.bucket_name == 'test-bucket'
            assert service.bucket_prefix == 'projects'
            print("✓ S3StateManagementService initialized successfully")
            return True
    except Exception as e:
        print(f"✗ Failed to initialize S3StateManagementService: {e}")
        return False

def test_key_generation_methods():
    """Test S3 key generation methods"""
    try:
        with patch('src.services.s3_state_management.boto3') as mock_boto3:
            mock_session = Mock()
            mock_s3_client = Mock()
            mock_boto3.Session.return_value = mock_session
            mock_session.client.return_value = mock_s3_client
            mock_s3_client.head_bucket.return_value = {}
            
            from src.services.s3_state_management import S3StateManagementService
            from datetime import datetime
            
            service = S3StateManagementService()
            
            # Test state key generation
            state_key = service._get_state_key("test-project")
            assert state_key == "projects/test-project/state/current.json"
            
            versioned_key = service._get_state_key("test-project", "v1.0.0")
            assert versioned_key == "projects/test-project/state/v1.0.0.json"
            
            # Test history key generation
            timestamp = datetime(2024, 1, 1, 10, 30, 45, 123456)
            history_key = service._get_history_key("test-project", timestamp)
            assert history_key == "projects/test-project/history/20240101_103045_123456.json"
            
            print("✓ Key generation methods work correctly")
            return True
    except Exception as e:
        print(f"✗ Key generation test failed: {e}")
        return False

if __name__ == "__main__":
    print("Running S3 State Management Service validation tests...")
    
    tests = [
        test_s3_service_can_be_imported,
        test_s3_service_initialization,
        test_key_generation_methods
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All S3 State Management Service tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)