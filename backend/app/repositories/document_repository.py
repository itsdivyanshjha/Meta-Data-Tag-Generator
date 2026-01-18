"""Document repository for database operations"""

from typing import Optional, List, Dict, Any
from uuid import UUID
import json
import asyncpg

from app.database import get_database


class DocumentRepository:
    """Repository for document-related database operations"""

    def __init__(self):
        self.db = get_database()

    async def create_document(
        self,
        job_id: Optional[UUID],
        user_id: Optional[UUID],
        title: str,
        file_path: str,
        file_source_type: str,
        file_size: Optional[int] = None,
        mime_type: Optional[str] = None
    ) -> asyncpg.Record:
        """Create a new document record"""
        query = """
            INSERT INTO documents (job_id, user_id, title, file_path, file_source_type,
                                   file_size, mime_type, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
            RETURNING id, job_id, user_id, title, file_path, file_source_type,
                      file_size, mime_type, status, tags, extracted_text,
                      processing_metadata, error_message, processed_at, created_at, updated_at
        """
        return await self.db.fetchrow(
            query, job_id, user_id, title, file_path, file_source_type, file_size, mime_type
        )

    async def create_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        job_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None
    ) -> List[asyncpg.Record]:
        """Create multiple document records in batch"""
        results = []
        for doc in documents:
            record = await self.create_document(
                job_id=job_id,
                user_id=user_id,
                title=doc.get("title", "Untitled"),
                file_path=doc.get("file_path", ""),
                file_source_type=doc.get("file_source_type", "url"),
                file_size=doc.get("file_size"),
                mime_type=doc.get("mime_type", "application/pdf")
            )
            results.append(record)
        return results

    async def get_document_by_id(self, doc_id: UUID) -> Optional[asyncpg.Record]:
        """Get document by ID"""
        query = """
            SELECT id, job_id, user_id, title, file_path, file_source_type,
                   file_size, mime_type, status, tags, extracted_text,
                   processing_metadata, error_message, processed_at, created_at, updated_at
            FROM documents
            WHERE id = $1
        """
        return await self.db.fetchrow(query, doc_id)

    async def get_documents_by_job(
        self,
        job_id: UUID,
        limit: int = 1000,
        offset: int = 0
    ) -> List[asyncpg.Record]:
        """Get all documents for a job"""
        query = """
            SELECT id, job_id, user_id, title, file_path, file_source_type,
                   file_size, mime_type, status, tags, extracted_text,
                   processing_metadata, error_message, processed_at, created_at, updated_at
            FROM documents
            WHERE job_id = $1
            ORDER BY created_at ASC
            LIMIT $2 OFFSET $3
        """
        return await self.db.fetch(query, job_id, limit, offset)

    async def get_documents_by_user(
        self,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[asyncpg.Record]:
        """Get documents for a user (across all jobs)"""
        query = """
            SELECT id, job_id, user_id, title, file_path, file_source_type,
                   file_size, mime_type, status, tags, extracted_text,
                   processing_metadata, error_message, processed_at, created_at, updated_at
            FROM documents
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """
        return await self.db.fetch(query, user_id, limit, offset)

    async def update_document_status(
        self,
        doc_id: UUID,
        status: str,
        error_message: Optional[str] = None
    ) -> Optional[asyncpg.Record]:
        """Update document status"""
        if status in ["success", "failed"]:
            query = """
                UPDATE documents
                SET status = $2, error_message = $3, processed_at = CURRENT_TIMESTAMP
                WHERE id = $1
                RETURNING id, status, processed_at
            """
        else:
            query = """
                UPDATE documents
                SET status = $2, error_message = $3
                WHERE id = $1
                RETURNING id, status, processed_at
            """
        return await self.db.fetchrow(query, doc_id, status, error_message)

    async def update_document_result(
        self,
        doc_id: UUID,
        status: str,
        tags: Optional[List[str]] = None,
        extracted_text: Optional[str] = None,
        processing_metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Optional[asyncpg.Record]:
        """Update document with processing results"""
        tags_json = json.dumps(tags) if tags else "[]"
        metadata_json = json.dumps(processing_metadata) if processing_metadata else None

        query = """
            UPDATE documents
            SET status = $2,
                tags = $3::jsonb,
                extracted_text = $4,
                processing_metadata = $5::jsonb,
                error_message = $6,
                processed_at = CURRENT_TIMESTAMP
            WHERE id = $1
            RETURNING id, job_id, user_id, title, file_path, file_source_type,
                      file_size, mime_type, status, tags, extracted_text,
                      processing_metadata, error_message, processed_at, created_at, updated_at
        """
        return await self.db.fetchrow(
            query, doc_id, status, tags_json, extracted_text, metadata_json, error_message
        )

    async def delete_document(self, doc_id: UUID) -> bool:
        """Delete a document"""
        query = "DELETE FROM documents WHERE id = $1"
        result = await self.db.execute(query, doc_id)
        return result == "DELETE 1"

    async def count_documents_by_job(self, job_id: UUID) -> Dict[str, int]:
        """Count documents by status for a job"""
        query = """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'processing') as processing,
                COUNT(*) FILTER (WHERE status = 'success') as success,
                COUNT(*) FILTER (WHERE status = 'failed') as failed
            FROM documents
            WHERE job_id = $1
        """
        row = await self.db.fetchrow(query, job_id)
        return {
            "total": row["total"],
            "pending": row["pending"],
            "processing": row["processing"],
            "success": row["success"],
            "failed": row["failed"]
        }

    async def get_recent_documents(
        self,
        limit: int = 50,
        user_id: Optional[UUID] = None
    ) -> List[asyncpg.Record]:
        """Get recent processed documents"""
        if user_id:
            query = """
                SELECT id, job_id, user_id, title, file_path, file_source_type,
                       status, tags, processed_at, created_at
                FROM documents
                WHERE user_id = $1 AND status IN ('success', 'failed')
                ORDER BY processed_at DESC NULLS LAST
                LIMIT $2
            """
            return await self.db.fetch(query, user_id, limit)
        else:
            query = """
                SELECT id, job_id, user_id, title, file_path, file_source_type,
                       status, tags, processed_at, created_at
                FROM documents
                WHERE status IN ('success', 'failed')
                ORDER BY processed_at DESC NULLS LAST
                LIMIT $1
            """
            return await self.db.fetch(query, limit)

    async def search_documents(
        self,
        user_id: UUID,
        query_text: str,
        limit: int = 50
    ) -> List[asyncpg.Record]:
        """Search documents by title or tags"""
        search_pattern = f"%{query_text}%"
        query = """
            SELECT id, job_id, user_id, title, file_path, file_source_type,
                   status, tags, error_message, processed_at, created_at
            FROM documents
            WHERE user_id = $1
              AND (
                  title ILIKE $2
                  OR tags::text ILIKE $2
              )
            ORDER BY processed_at DESC NULLS LAST
            LIMIT $3
        """
        return await self.db.fetch(query, user_id, search_pattern, limit)
