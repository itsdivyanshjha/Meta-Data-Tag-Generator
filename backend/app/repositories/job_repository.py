"""Job repository for database operations"""

from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
import json
import asyncpg

from app.database import get_database


class JobRepository:
    """Repository for job-related database operations"""

    def __init__(self):
        self.db = get_database()

    async def create_job(
        self,
        user_id: Optional[UUID] = None,
        job_type: str = "batch",
        total_documents: int = 0,
        config: Optional[Dict[str, Any]] = None
    ) -> asyncpg.Record:
        """Create a new job"""
        query = """
            INSERT INTO jobs (user_id, job_type, status, total_documents, config)
            VALUES ($1, $2, 'pending', $3, $4)
            RETURNING id, user_id, job_type, status, total_documents, processed_count,
                      failed_count, config, error_message, started_at, completed_at,
                      created_at, updated_at
        """
        config_json = json.dumps(config) if config else None
        return await self.db.fetchrow(query, user_id, job_type, total_documents, config_json)

    async def get_job_by_id(self, job_id: UUID) -> Optional[asyncpg.Record]:
        """Get job by ID"""
        query = """
            SELECT id, user_id, job_type, status, total_documents, processed_count,
                   failed_count, config, error_message, started_at, completed_at,
                   created_at, updated_at
            FROM jobs
            WHERE id = $1
        """
        return await self.db.fetchrow(query, job_id)

    async def get_jobs_by_user(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[asyncpg.Record]:
        """Get jobs for a specific user, including anonymous jobs (for backward compatibility)"""
        if status:
            query = """
                SELECT id, user_id, job_type, status, total_documents, processed_count,
                       failed_count, config, error_message, started_at, completed_at,
                       created_at, updated_at
                FROM jobs
                WHERE (user_id = $1 OR user_id IS NULL) AND status = $2
                ORDER BY created_at DESC
                LIMIT $3 OFFSET $4
            """
            return await self.db.fetch(query, user_id, status, limit, offset)
        else:
            query = """
                SELECT id, user_id, job_type, status, total_documents, processed_count,
                       failed_count, config, error_message, started_at, completed_at,
                       created_at, updated_at
                FROM jobs
                WHERE user_id = $1 OR user_id IS NULL
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """
            return await self.db.fetch(query, user_id, limit, offset)

    async def get_recent_jobs(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[asyncpg.Record]:
        """Get recent jobs (for anonymous users or admin view)"""
        query = """
            SELECT id, user_id, job_type, status, total_documents, processed_count,
                   failed_count, config, error_message, started_at, completed_at,
                   created_at, updated_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """
        return await self.db.fetch(query, limit, offset)

    async def update_job_status(
        self,
        job_id: UUID,
        status: str,
        error_message: Optional[str] = None
    ) -> Optional[asyncpg.Record]:
        """Update job status"""
        if status == "processing":
            query = """
                UPDATE jobs
                SET status = $2, started_at = CURRENT_TIMESTAMP, error_message = $3
                WHERE id = $1
                RETURNING id, status, started_at, completed_at
            """
        elif status in ["completed", "failed", "cancelled"]:
            query = """
                UPDATE jobs
                SET status = $2, completed_at = CURRENT_TIMESTAMP, error_message = $3
                WHERE id = $1
                RETURNING id, status, started_at, completed_at
            """
        else:
            query = """
                UPDATE jobs
                SET status = $2, error_message = $3
                WHERE id = $1
                RETURNING id, status, started_at, completed_at
            """
        return await self.db.fetchrow(query, job_id, status, error_message)

    async def update_job_progress(
        self,
        job_id: UUID,
        processed_count: int,
        failed_count: int
    ) -> Optional[asyncpg.Record]:
        """Update job progress counters"""
        query = """
            UPDATE jobs
            SET processed_count = $2, failed_count = $3
            WHERE id = $1
            RETURNING id, processed_count, failed_count
        """
        return await self.db.fetchrow(query, job_id, processed_count, failed_count)

    async def increment_job_counts(
        self,
        job_id: UUID,
        success: bool
    ) -> Optional[asyncpg.Record]:
        """Increment processed or failed count by 1"""
        if success:
            query = """
                UPDATE jobs
                SET processed_count = processed_count + 1
                WHERE id = $1
                RETURNING id, processed_count, failed_count
            """
        else:
            query = """
                UPDATE jobs
                SET failed_count = failed_count + 1
                WHERE id = $1
                RETURNING id, processed_count, failed_count
            """
        return await self.db.fetchrow(query, job_id)

    async def delete_job(self, job_id: UUID) -> bool:
        """Delete a job (cascades to documents)"""
        query = "DELETE FROM jobs WHERE id = $1"
        result = await self.db.execute(query, job_id)
        return result == "DELETE 1"

    async def count_user_jobs(self, user_id: UUID) -> int:
        """Count total jobs for a user"""
        query = "SELECT COUNT(*) FROM jobs WHERE user_id = $1"
        return await self.db.fetchval(query, user_id)
