"""History router for viewing past jobs and documents"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime

from app.repositories import JobRepository, DocumentRepository
from app.dependencies.auth import get_optional_user, get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize repositories
job_repo = JobRepository()
doc_repo = DocumentRepository()


# Response models
class DocumentSummary(BaseModel):
    """Summary of a processed document"""
    id: UUID
    title: str
    file_path: str
    file_source_type: str
    status: str
    tags: List[str]
    error_message: Optional[str]
    processed_at: Optional[datetime]
    created_at: datetime


class JobSummary(BaseModel):
    """Summary of a processing job"""
    id: UUID
    job_type: str
    status: str
    total_documents: int
    processed_count: int
    failed_count: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class JobDetail(BaseModel):
    """Detailed job information including documents"""
    id: UUID
    job_type: str
    status: str
    total_documents: int
    processed_count: int
    failed_count: int
    config: Optional[dict]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    documents: List[DocumentSummary]


class JobListResponse(BaseModel):
    """Response for job list endpoint"""
    jobs: List[JobSummary]
    total: int
    limit: int
    offset: int


class DocumentListResponse(BaseModel):
    """Response for document list endpoint"""
    documents: List[DocumentSummary]
    total: int


class UserStats(BaseModel):
    """User statistics for dashboard"""
    total_jobs: int
    total_documents: int
    documents_processed: int
    documents_failed: int
    jobs_by_status: dict
    recent_activity: List[JobSummary]


def _parse_tags(tags_value) -> List[str]:
    """Parse tags from database value (could be JSON string or list)"""
    if tags_value is None:
        return []
    if isinstance(tags_value, list):
        return tags_value
    if isinstance(tags_value, str):
        import json
        try:
            return json.loads(tags_value)
        except:
            return []
    return []


def _parse_config(config_value) -> Optional[dict]:
    """Parse config from database value"""
    if config_value is None:
        return None
    if isinstance(config_value, dict):
        return config_value
    if isinstance(config_value, str):
        import json
        try:
            return json.loads(config_value)
        except:
            return None
    return None


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """
    List processing jobs.

    - If authenticated, returns:
      1. Jobs for the current user
      2. Anonymous jobs (user_id = NULL) created in this session
    - If not authenticated, returns recent jobs (anonymous mode)
    """
    try:
        if current_user:
            user_id = current_user["id"]
            jobs = await job_repo.get_jobs_by_user(user_id, limit, offset, status)
            total = await job_repo.count_user_jobs(user_id)
            
            # Also include anonymous jobs (user_id = NULL) for user context
            # This handles cases where jobs were created before authentication
            logger.info(f"Fetching jobs for authenticated user {user_id}. Found {len(jobs)} user jobs.")
        else:
            jobs = await job_repo.get_recent_jobs(limit, offset)
            total = len(jobs)
            logger.info(f"Fetching jobs for anonymous user. Found {len(jobs)} recent jobs.")

        job_summaries = [
            JobSummary(
                id=job["id"],
                job_type=job["job_type"],
                status=job["status"],
                total_documents=job["total_documents"],
                processed_count=job["processed_count"],
                failed_count=job["failed_count"],
                started_at=job["started_at"],
                completed_at=job["completed_at"],
                created_at=job["created_at"]
            )
            for job in jobs
        ]

        return JobListResponse(
            jobs=job_summaries,
            total=total,
            limit=limit,
            offset=offset
        )

    except Exception as e:
        logger.error(f"Failed to fetch jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch jobs: {str(e)}")


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job_detail(
    job_id: UUID,
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get detailed information about a specific job including its documents.
    """
    try:
        job = await job_repo.get_job_by_id(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check ownership if user is authenticated
        if current_user and job["user_id"] and job["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to view this job")

        # Fetch documents for this job
        documents = await doc_repo.get_documents_by_job(job_id)

        doc_summaries = [
            DocumentSummary(
                id=doc["id"],
                title=doc["title"],
                file_path=doc["file_path"],
                file_source_type=doc["file_source_type"],
                status=doc["status"],
                tags=_parse_tags(doc["tags"]),
                error_message=doc["error_message"],
                processed_at=doc["processed_at"],
                created_at=doc["created_at"]
            )
            for doc in documents
        ]

        return JobDetail(
            id=job["id"],
            job_type=job["job_type"],
            status=job["status"],
            total_documents=job["total_documents"],
            processed_count=job["processed_count"],
            failed_count=job["failed_count"],
            config=_parse_config(job["config"]),
            error_message=job["error_message"],
            started_at=job["started_at"],
            completed_at=job["completed_at"],
            created_at=job["created_at"],
            documents=doc_summaries
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch job: {str(e)}")


@router.get("/documents", response_model=DocumentListResponse)
async def list_recent_documents(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """
    List recent processed documents.

    - If authenticated, returns documents for the current user
    - If not authenticated, returns recent documents
    """
    try:
        user_id = current_user["id"] if current_user else None
        documents = await doc_repo.get_recent_documents(limit, user_id)

        doc_summaries = [
            DocumentSummary(
                id=doc["id"],
                title=doc["title"],
                file_path=doc["file_path"],
                file_source_type=doc["file_source_type"],
                status=doc["status"],
                tags=_parse_tags(doc["tags"]),
                error_message=None,  # Not included in recent query
                processed_at=doc["processed_at"],
                created_at=doc["created_at"]
            )
            for doc in documents
        ]

        return DocumentListResponse(
            documents=doc_summaries,
            total=len(doc_summaries)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch documents: {str(e)}")


@router.get("/documents/{doc_id}")
async def get_document_detail(
    doc_id: UUID,
    current_user: Optional[dict] = Depends(get_optional_user)
):
    """
    Get detailed information about a specific document.
    """
    try:
        doc = await doc_repo.get_document_by_id(doc_id)

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Check ownership if user is authenticated
        if current_user and doc["user_id"] and doc["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to view this document")

        return {
            "id": doc["id"],
            "job_id": doc["job_id"],
            "title": doc["title"],
            "file_path": doc["file_path"],
            "file_source_type": doc["file_source_type"],
            "file_size": doc["file_size"],
            "mime_type": doc["mime_type"],
            "status": doc["status"],
            "tags": _parse_tags(doc["tags"]),
            "extracted_text": doc["extracted_text"],
            "processing_metadata": _parse_config(doc["processing_metadata"]),
            "error_message": doc["error_message"],
            "processed_at": doc["processed_at"],
            "created_at": doc["created_at"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch document: {str(e)}")


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: UUID,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Delete a job and all its documents. Requires authentication.
    """
    try:
        job = await job_repo.get_job_by_id(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check ownership
        if job["user_id"] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to delete this job")

        success = await job_repo.delete_job(job_id)

        if success:
            return {"message": "Job deleted successfully", "job_id": str(job_id)}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete job")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")


@router.get("/stats", response_model=UserStats)
async def get_user_stats(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get statistics for the current user's dashboard.
    """
    try:
        user_id = current_user["id"]

        # Get job counts by status
        jobs = await job_repo.get_jobs_by_user(user_id, limit=1000, offset=0)

        total_jobs = len(jobs)
        total_documents = sum(j["total_documents"] for j in jobs)
        documents_processed = sum(j["processed_count"] for j in jobs)
        documents_failed = sum(j["failed_count"] for j in jobs)

        # Count jobs by status
        jobs_by_status = {}
        for job in jobs:
            status = job["status"]
            jobs_by_status[status] = jobs_by_status.get(status, 0) + 1

        # Get recent activity (last 5 jobs)
        recent_jobs = jobs[:5] if jobs else []
        recent_activity = [
            JobSummary(
                id=job["id"],
                job_type=job["job_type"],
                status=job["status"],
                total_documents=job["total_documents"],
                processed_count=job["processed_count"],
                failed_count=job["failed_count"],
                started_at=job["started_at"],
                completed_at=job["completed_at"],
                created_at=job["created_at"]
            )
            for job in recent_jobs
        ]

        return UserStats(
            total_jobs=total_jobs,
            total_documents=total_documents,
            documents_processed=documents_processed,
            documents_failed=documents_failed,
            jobs_by_status=jobs_by_status,
            recent_activity=recent_activity
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")


@router.get("/documents/search")
async def search_documents(
    query: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Search documents by title or tags.
    """
    try:
        user_id = current_user["id"]
        documents = await doc_repo.search_documents(user_id, query, limit)

        doc_summaries = [
            DocumentSummary(
                id=doc["id"],
                title=doc["title"],
                file_path=doc["file_path"],
                file_source_type=doc["file_source_type"],
                status=doc["status"],
                tags=_parse_tags(doc["tags"]),
                error_message=doc.get("error_message"),
                processed_at=doc["processed_at"],
                created_at=doc["created_at"]
            )
            for doc in documents
        ]

        return DocumentListResponse(
            documents=doc_summaries,
            total=len(doc_summaries)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
