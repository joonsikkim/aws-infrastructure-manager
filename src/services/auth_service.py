"""
Authentication and authorization service implementation
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from config.settings import settings
from config.logging import get_logger
from src.models.data_models import User, UserCreate, UserUpdate, Token, TokenPayload, ProjectRole
from src.models.enums import UserRole, ErrorCodes
from src.models.exceptions import InfrastructureException
from src.services.interfaces import AuthService

logger = get_logger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class JWTAuthService(AuthService):
    """JWT-based authentication and authorization service implementation"""
    
    def __init__(self):
        """Initialize the auth service"""
        self._users: Dict[str, User] = {}  # In-memory user storage (replace with DB in production)
        self._project_roles: Dict[str, ProjectRole] = {}  # In-memory project roles (replace with DB)
        self._refresh_tokens: Dict[str, str] = {}  # In-memory refresh token storage (replace with DB)
        
        # Create a default admin user if no users exist
        if not self._users:
            admin_user = UserCreate(
                username="admin",
                email="admin@example.com",
                password="admin123",  # This should be changed in production
                full_name="Admin User",
                role=UserRole.ADMIN
            )
            self.register_user(admin_user)
            logger.info("Created default admin user")
    
    async def register_user(self, user_create: UserCreate) -> User:
        """Register a new user"""
        # Check if username already exists
        for user in self._users.values():
            if user.username == user_create.username:
                logger.error(f"Username {user_create.username} already exists")
                raise InfrastructureException(
                    code=ErrorCodes.INVALID_CREDENTIALS,
                    message=f"Username {user_create.username} already exists"
                )
        
        # Create new user
        user_id = str(uuid.uuid4())
        hashed_password = self._hash_password(user_create.password)
        
        new_user = User(
            id=user_id,
            username=user_create.username,
            email=user_create.email,
            full_name=user_create.full_name,
            role=user_create.role,
            hashed_password=hashed_password,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self._users[user_id] = new_user
        logger.info(f"Registered new user: {user_create.username}")
        
        # Return user without password
        return new_user
    
    async def authenticate_user(self, username: str, password: str) -> User:
        """Authenticate a user with username and password"""
        user = await self.get_user_by_username(username)
        
        if not user:
            logger.error(f"User not found: {username}")
            raise InfrastructureException(
                code=ErrorCodes.INVALID_CREDENTIALS,
                message="Invalid username or password"
            )
        
        if not user.is_active:
            logger.error(f"User is inactive: {username}")
            raise InfrastructureException(
                code=ErrorCodes.INSUFFICIENT_PERMISSIONS,
                message="User account is inactive"
            )
        
        if not self._verify_password(password, user.hashed_password):
            logger.error(f"Invalid password for user: {username}")
            raise InfrastructureException(
                code=ErrorCodes.INVALID_CREDENTIALS,
                message="Invalid username or password"
            )
        
        logger.info(f"User authenticated: {username}")
        return user
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID"""
        user = self._users.get(user_id)
        if not user:
            logger.error(f"User not found: {user_id}")
            return None
        return user
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username"""
        for user in self._users.values():
            if user.username == username:
                return user
        logger.error(f"User not found by username: {username}")
        return None
    
    async def update_user(self, user_id: str, user_update: UserUpdate) -> User:
        """Update a user"""
        user = await self.get_user(user_id)
        if not user:
            logger.error(f"User not found for update: {user_id}")
            raise InfrastructureException(
                code=ErrorCodes.USER_NOT_FOUND,
                message=f"User with ID {user_id} not found"
            )
        
        # Update user fields
        if user_update.email is not None:
            user.email = user_update.email
        
        if user_update.full_name is not None:
            user.full_name = user_update.full_name
        
        if user_update.role is not None:
            user.role = user_update.role
        
        if user_update.is_active is not None:
            user.is_active = user_update.is_active
        
        user.updated_at = datetime.now()
        self._users[user_id] = user
        
        logger.info(f"Updated user: {user_id}")
        return user
    
    async def create_access_token(self, user: User) -> Token:
        """Create access and refresh tokens for a user"""
        # Create access token
        access_token_expires = datetime.now() + timedelta(minutes=settings.security.access_token_expire_minutes)
        access_token_data = {
            "sub": user.id,
            "username": user.username,
            "role": user.role.value,
            "exp": int(access_token_expires.timestamp())
        }
        
        access_token = jwt.encode(
            access_token_data,
            settings.security.secret_key,
            algorithm=settings.security.algorithm
        )
        
        # Create refresh token
        refresh_token_expires = datetime.now() + timedelta(days=settings.security.refresh_token_expire_days)
        refresh_token_data = {
            "sub": user.id,
            "exp": int(refresh_token_expires.timestamp()),
            "type": "refresh"
        }
        
        refresh_token = jwt.encode(
            refresh_token_data,
            settings.security.secret_key,
            algorithm=settings.security.algorithm
        )
        
        # Store refresh token
        self._refresh_tokens[refresh_token] = user.id
        
        logger.info(f"Created tokens for user: {user.username}")
        return Token(
            access_token=access_token,
            refresh_token=refresh_token
        )
    
    async def refresh_token(self, refresh_token: str) -> Token:
        """Create new access token using refresh token"""
        try:
            # Verify refresh token
            payload = jwt.decode(
                refresh_token,
                settings.security.secret_key,
                algorithms=[settings.security.algorithm]
            )
            
            # Check if token is a refresh token
            if payload.get("type") != "refresh":
                logger.error("Invalid token type for refresh")
                raise InfrastructureException(
                    code=ErrorCodes.INVALID_TOKEN,
                    message="Invalid token type"
                )
            
            # Check if token is in storage
            user_id = self._refresh_tokens.get(refresh_token)
            if not user_id or user_id != payload.get("sub"):
                logger.error("Refresh token not found in storage")
                raise InfrastructureException(
                    code=ErrorCodes.INVALID_TOKEN,
                    message="Invalid refresh token"
                )
            
            # Get user
            user = await self.get_user(user_id)
            if not user:
                logger.error(f"User not found for refresh token: {user_id}")
                raise InfrastructureException(
                    code=ErrorCodes.USER_NOT_FOUND,
                    message="User not found"
                )
            
            # Create new tokens
            new_tokens = await self.create_access_token(user)
            
            # Invalidate old refresh token
            self._refresh_tokens.pop(refresh_token, None)
            
            logger.info(f"Refreshed tokens for user: {user.username}")
            return new_tokens
            
        except jwt.PyJWTError as e:
            logger.error(f"JWT error during token refresh: {str(e)}")
            raise InfrastructureException(
                code=ErrorCodes.INVALID_TOKEN,
                message="Invalid refresh token"
            )
    
    async def verify_token(self, token: str) -> Optional[User]:
        """Verify a token and return the associated user"""
        try:
            # Decode token
            payload = jwt.decode(
                token,
                settings.security.secret_key,
                algorithms=[settings.security.algorithm]
            )
            
            # Extract user ID
            user_id = payload.get("sub")
            if not user_id:
                logger.error("Token missing subject claim")
                return None
            
            # Get user
            user = await self.get_user(user_id)
            if not user:
                logger.error(f"User not found for token: {user_id}")
                return None
            
            # Check if user is active
            if not user.is_active:
                logger.error(f"User is inactive: {user_id}")
                return None
            
            return user
            
        except jwt.ExpiredSignatureError:
            logger.error("Token has expired")
            return None
            
        except jwt.PyJWTError as e:
            logger.error(f"JWT error during token verification: {str(e)}")
            return None
    
    async def get_project_role(self, user_id: str, project_id: str) -> Optional[str]:
        """Get user's role in a specific project"""
        key = f"{user_id}:{project_id}"
        project_role = self._project_roles.get(key)
        
        if project_role:
            return project_role.role.value
        
        # If no specific project role, check if user is admin
        user = await self.get_user(user_id)
        if user and user.role == UserRole.ADMIN:
            return UserRole.ADMIN.value
        
        return None
    
    async def set_project_role(self, user_id: str, project_id: str, role: str) -> None:
        """Set user's role in a specific project"""
        # Validate user exists
        user = await self.get_user(user_id)
        if not user:
            logger.error(f"User not found for setting project role: {user_id}")
            raise InfrastructureException(
                code=ErrorCodes.USER_NOT_FOUND,
                message=f"User with ID {user_id} not found"
            )
        
        # Validate role
        try:
            user_role = UserRole(role)
        except ValueError:
            logger.error(f"Invalid role: {role}")
            raise InfrastructureException(
                code=ErrorCodes.VALIDATION_FAILED,
                message=f"Invalid role: {role}"
            )
        
        # Set project role
        key = f"{user_id}:{project_id}"
        self._project_roles[key] = ProjectRole(
            project_id=project_id,
            user_id=user_id,
            role=user_role
        )
        
        logger.info(f"Set project role for user {user_id} in project {project_id}: {role}")
    
    def _hash_password(self, password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash"""
        return pwd_context.verify(plain_password, hashed_password)