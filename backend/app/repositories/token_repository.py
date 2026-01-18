"""Token repository for database operations"""

from typing import Optional
from uuid import UUID
from datetime import datetime
import asyncpg

from app.database import get_database


class TokenRepository:
    """Repository for refresh token-related database operations"""

    def __init__(self):
        self.db = get_database()

    async def create_refresh_token(
        self,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> asyncpg.Record:
        """Create a new refresh token"""
        query = """
            INSERT INTO refresh_tokens (user_id, token_hash, expires_at, device_info, ip_address)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, user_id, token_hash, expires_at, created_at, device_info, ip_address
        """
        return await self.db.fetchrow(
            query, user_id, token_hash, expires_at, device_info, ip_address
        )

    async def get_token_by_hash(self, token_hash: str) -> Optional[asyncpg.Record]:
        """Get refresh token by hash"""
        query = """
            SELECT id, user_id, token_hash, expires_at, created_at, revoked_at, device_info, ip_address
            FROM refresh_tokens
            WHERE token_hash = $1 AND revoked_at IS NULL
        """
        return await self.db.fetchrow(query, token_hash)

    async def get_valid_token(self, token_hash: str) -> Optional[asyncpg.Record]:
        """Get a valid (not expired, not revoked) refresh token"""
        query = """
            SELECT id, user_id, token_hash, expires_at, created_at, device_info, ip_address
            FROM refresh_tokens
            WHERE token_hash = $1
            AND revoked_at IS NULL
            AND expires_at > CURRENT_TIMESTAMP
        """
        return await self.db.fetchrow(query, token_hash)

    async def revoke_token(self, token_hash: str) -> bool:
        """Revoke a refresh token"""
        query = """
            UPDATE refresh_tokens
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE token_hash = $1 AND revoked_at IS NULL
        """
        result = await self.db.execute(query, token_hash)
        return result == "UPDATE 1"

    async def revoke_all_user_tokens(self, user_id: UUID) -> int:
        """Revoke all refresh tokens for a user"""
        query = """
            UPDATE refresh_tokens
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE user_id = $1 AND revoked_at IS NULL
        """
        result = await self.db.execute(query, user_id)
        count = int(result.split()[1]) if result.startswith("UPDATE") else 0
        return count

    async def get_user_active_tokens(self, user_id: UUID) -> list:
        """Get all active tokens for a user"""
        query = """
            SELECT id, token_hash, expires_at, created_at, device_info, ip_address
            FROM refresh_tokens
            WHERE user_id = $1
            AND revoked_at IS NULL
            AND expires_at > CURRENT_TIMESTAMP
            ORDER BY created_at DESC
        """
        return await self.db.fetch(query, user_id)

    async def cleanup_expired_tokens(self) -> int:
        """Remove expired and revoked tokens"""
        query = "SELECT cleanup_expired_tokens()"
        return await self.db.fetchval(query)
