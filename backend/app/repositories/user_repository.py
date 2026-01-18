"""User repository for database operations"""

from typing import Optional
from uuid import UUID
from datetime import datetime
import asyncpg

from app.database import get_database


class UserRepository:
    """Repository for user-related database operations"""

    def __init__(self):
        self.db = get_database()

    async def create_user(
        self,
        email: str,
        password_hash: str,
        full_name: Optional[str] = None
    ) -> asyncpg.Record:
        """Create a new user"""
        query = """
            INSERT INTO users (email, password_hash, full_name)
            VALUES ($1, $2, $3)
            RETURNING id, email, full_name, is_active, is_verified, created_at, updated_at
        """
        return await self.db.fetchrow(query, email, password_hash, full_name)

    async def get_user_by_id(self, user_id: UUID) -> Optional[asyncpg.Record]:
        """Get user by ID"""
        query = """
            SELECT id, email, password_hash, full_name, is_active, is_verified, created_at, updated_at
            FROM users
            WHERE id = $1
        """
        return await self.db.fetchrow(query, user_id)

    async def get_user_by_email(self, email: str) -> Optional[asyncpg.Record]:
        """Get user by email"""
        query = """
            SELECT id, email, password_hash, full_name, is_active, is_verified, created_at, updated_at
            FROM users
            WHERE email = $1
        """
        return await self.db.fetchrow(query, email)

    async def update_user(
        self,
        user_id: UUID,
        full_name: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_verified: Optional[bool] = None
    ) -> Optional[asyncpg.Record]:
        """Update user information"""
        updates = []
        params = []
        param_count = 1

        if full_name is not None:
            updates.append(f"full_name = ${param_count}")
            params.append(full_name)
            param_count += 1

        if is_active is not None:
            updates.append(f"is_active = ${param_count}")
            params.append(is_active)
            param_count += 1

        if is_verified is not None:
            updates.append(f"is_verified = ${param_count}")
            params.append(is_verified)
            param_count += 1

        if not updates:
            return await self.get_user_by_id(user_id)

        params.append(user_id)
        query = f"""
            UPDATE users
            SET {', '.join(updates)}
            WHERE id = ${param_count}
            RETURNING id, email, full_name, is_active, is_verified, created_at, updated_at
        """
        return await self.db.fetchrow(query, *params)

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete a user"""
        query = "DELETE FROM users WHERE id = $1"
        result = await self.db.execute(query, user_id)
        return result == "DELETE 1"

    async def email_exists(self, email: str) -> bool:
        """Check if email already exists"""
        query = "SELECT EXISTS(SELECT 1 FROM users WHERE email = $1)"
        return await self.db.fetchval(query, email)
