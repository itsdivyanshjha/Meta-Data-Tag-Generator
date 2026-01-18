"""Authentication service for JWT token management and password hashing"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID
import hashlib
import secrets

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings
from app.repositories import UserRepository, TokenRepository

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication operations"""

    def __init__(self):
        self.user_repo = UserRepository()
        self.token_repo = TokenRepository()

    # ==================== Password Methods ====================

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    # ==================== Token Methods ====================

    def create_access_token(
        self,
        user_id: UUID,
        email: str,
        expires_delta: Optional[timedelta] = None
    ) -> Tuple[str, datetime]:
        """Create a JWT access token"""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.jwt_access_token_expire_minutes
            )

        payload = {
            "sub": str(user_id),
            "email": email,
            "type": "access",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }

        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
        return token, expire

    def create_refresh_token(self) -> Tuple[str, str]:
        """Create a refresh token and its hash"""
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return token, token_hash

    def verify_access_token(self, token: str) -> Optional[dict]:
        """Verify and decode an access token"""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        """Hash a refresh token"""
        return hashlib.sha256(token.encode()).hexdigest()

    # ==================== User Methods ====================

    async def register_user(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None
    ) -> dict:
        """Register a new user"""
        if await self.user_repo.email_exists(email):
            raise ValueError("Email already registered")

        password_hash = self.hash_password(password)
        user = await self.user_repo.create_user(email, password_hash, full_name)

        return {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "is_active": user["is_active"],
            "is_verified": user["is_verified"],
            "created_at": user["created_at"],
        }

    async def authenticate_user(
        self,
        email: str,
        password: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Optional[dict]:
        """Authenticate a user and return tokens"""
        user = await self.user_repo.get_user_by_email(email)

        if not user:
            return None

        if not self.verify_password(password, user["password_hash"]):
            return None

        if not user["is_active"]:
            raise ValueError("User account is disabled")

        # Create tokens
        access_token, access_expires = self.create_access_token(
            user["id"], user["email"]
        )
        refresh_token, refresh_hash = self.create_refresh_token()

        # Store refresh token
        refresh_expires = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        await self.token_repo.create_refresh_token(
            user["id"],
            refresh_hash,
            refresh_expires,
            device_info,
            ip_address
        )

        return {
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user["full_name"],
                "is_active": user["is_active"],
                "is_verified": user["is_verified"],
                "created_at": user["created_at"],
            },
            "tokens": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.jwt_access_token_expire_minutes * 60,
            }
        }

    async def refresh_tokens(
        self,
        refresh_token: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Optional[dict]:
        """Refresh access token using refresh token"""
        token_hash = self.hash_refresh_token(refresh_token)
        token_record = await self.token_repo.get_valid_token(token_hash)

        if not token_record:
            return None

        # Get user
        user = await self.user_repo.get_user_by_id(token_record["user_id"])
        if not user or not user["is_active"]:
            return None

        # Revoke old refresh token
        await self.token_repo.revoke_token(token_hash)

        # Create new tokens
        access_token, access_expires = self.create_access_token(
            user["id"], user["email"]
        )
        new_refresh_token, new_refresh_hash = self.create_refresh_token()

        # Store new refresh token
        refresh_expires = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        await self.token_repo.create_refresh_token(
            user["id"],
            new_refresh_hash,
            refresh_expires,
            device_info,
            ip_address
        )

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.jwt_access_token_expire_minutes * 60,
        }

    async def logout(self, refresh_token: str) -> bool:
        """Logout by revoking refresh token"""
        token_hash = self.hash_refresh_token(refresh_token)
        return await self.token_repo.revoke_token(token_hash)

    async def logout_all(self, user_id: UUID) -> int:
        """Logout from all devices by revoking all refresh tokens"""
        return await self.token_repo.revoke_all_user_tokens(user_id)

    async def get_user_by_id(self, user_id: UUID) -> Optional[dict]:
        """Get user by ID"""
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            return None

        return {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "is_active": user["is_active"],
            "is_verified": user["is_verified"],
            "created_at": user["created_at"],
        }
