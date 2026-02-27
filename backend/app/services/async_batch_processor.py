"""
Async Batch Processor with Redis-backed State

Processing runs as a background asyncio.Task, completely decoupled from
WebSocket connections. Job state lives in Redis; WebSocket clients are
read-only observers via Redis pub/sub.
"""

import asyncio
import gc
import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from uuid import UUID

from app.models import (
    TaggingConfig,
    DocumentStatus,
)
from app.services.pdf_extractor import PDFExtractor
from app.services.ai_tagger import AITagger
from app.services.file_handler import FileHandler
from app.services import redis_client
from app.repositories import JobRepository, DocumentRepository

logger = logging.getLogger(__name__)


@dataclass
class BatchJob:
    """Represents a batch processing job"""
    job_id: str
    documents: List[Dict[str, Any]]
    config: TaggingConfig
    column_mapping: Dict[str, str]
    status: str = "pending"
    progress: float = 0.0
    processed_count: int = 0
    failed_count: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    cancelled: bool = False
    paused: bool = False
    # Database persistence fields
    db_job_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    document_ids: List[UUID] = field(default_factory=list)


class AdaptiveRateLimiter:
    """Rate limiter that increases delay on 429s and decays after consecutive successes."""

    def __init__(self, base_delay: float = 0.5, max_delay: float = 60.0, decay_factor: float = 0.8):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.decay_factor = decay_factor
        self.current_delay = base_delay
        self.consecutive_successes = 0

    def on_success(self):
        self.consecutive_successes += 1
        if self.consecutive_successes >= 3:
            self.current_delay = max(self.base_delay, self.current_delay * self.decay_factor)
            self.consecutive_successes = 0

    def on_rate_limit(self, retry_after: Optional[float] = None):
        self.consecutive_successes = 0
        if retry_after:
            self.current_delay = min(retry_after, self.max_delay)
        else:
            self.current_delay = min(self.current_delay * 2, self.max_delay)

    async def wait(self):
        await asyncio.sleep(self.current_delay)


class AsyncBatchProcessor:
    """
    Async batch processor that stores state in Redis and publishes progress
    via Redis pub/sub. Processing is fully decoupled from WebSocket.
    """

    # In-memory map of running asyncio tasks
    _tasks: Dict[str, asyncio.Task] = {}

    def __init__(self):
        self.extractor = PDFExtractor()
        self.file_handler = FileHandler()
        self.job_repo = JobRepository()
        self.doc_repo = DocumentRepository()
        self._db_available = True

    async def start_job(
        self,
        job_id: str,
        documents: List[Dict[str, Any]],
        config: TaggingConfig,
        column_mapping: Dict[str, str],
        user_id: Optional[UUID] = None
    ) -> BatchJob:
        """Initialize a new batch job, persist to DB + Redis, launch background task."""
        db_job_id = None
        document_ids: List[UUID] = []

        # Persist to database
        try:
            config_dict = {
                "model_name": config.model_name,
                "num_pages": config.num_pages,
                "num_tags": config.num_tags,
                "exclusion_words": config.exclusion_words
            }
            db_job = await self.job_repo.create_job(
                user_id=user_id,
                job_type="batch",
                total_documents=len(documents),
                config=config_dict
            )
            db_job_id = db_job["id"]
            logger.info(f"Persisted job to database: {db_job_id} (user_id: {user_id})")

            for doc_data in documents:
                doc_info = self._extract_document_info(doc_data, column_mapping)
                db_doc = await self.doc_repo.create_document(
                    job_id=db_job_id,
                    user_id=user_id,
                    title=doc_info.get("title", "Untitled"),
                    file_path=doc_info.get("file_path", ""),
                    file_source_type=doc_info.get("file_source_type", "url")
                )
                document_ids.append(db_doc["id"])
            logger.info(f"Persisted {len(document_ids)} documents to database")
        except Exception as e:
            logger.warning(f"Database persistence failed (job will still run): {e}")
            self._db_available = False

        job = BatchJob(
            job_id=job_id,
            documents=documents,
            config=config,
            column_mapping=column_mapping,
            status="pending",
            start_time=time.time(),
            db_job_id=db_job_id,
            user_id=user_id,
            document_ids=document_ids
        )

        # Store initial state in Redis
        await redis_client.set_job_state(job_id, {
            "status": "pending",
            "total": len(documents),
            "processed_count": 0,
            "failed_count": 0,
            "progress": 0.0,
            "user_id": str(user_id) if user_id else "",
            "db_job_id": str(db_job_id) if db_job_id else "",
            "start_time": job.start_time,
            "command": "none",
        })

        # Launch background processing task
        task = asyncio.create_task(self._process_batch(job))
        self._tasks[job_id] = task
        logger.info(f"Launched background task for job {job_id} with {len(documents)} documents")

        return job

    async def _process_batch(self, job: BatchJob):
        """Process all documents in the batch (runs as background task)."""
        rate_limiter = AdaptiveRateLimiter()

        try:
            job.status = "processing"
            await redis_client.update_job_field(job.job_id, "status", "processing")
            await self._update_job_status_db(job, "processing")
            total = len(job.documents)

            tagger = AITagger(
                job.config.api_key,
                job.config.model_name,
                exclusion_words=job.config.exclusion_words
            )

            for idx, doc_data in enumerate(job.documents):
                # Check for commands (cancel/pause)
                cmd = await redis_client.get_job_command(job.job_id)
                if cmd == "cancel":
                    logger.info(f"Job {job.job_id} cancelled via command at document {idx + 1}/{total}")
                    job.cancelled = True
                    break
                while cmd == "pause":
                    job.paused = True
                    await redis_client.update_job_field(job.job_id, "status", "paused")
                    await asyncio.sleep(1)
                    cmd = await redis_client.get_job_command(job.job_id)
                    if cmd == "cancel":
                        job.cancelled = True
                        break
                    if cmd == "resume":
                        job.paused = False
                        await redis_client.update_job_field(job.job_id, "status", "processing")
                        break
                if job.cancelled:
                    break

                try:
                    doc_info = self._extract_document_info(doc_data, job.column_mapping)
                    title = doc_info.get("title", f"Document {idx + 1}")

                    # Publish "processing" update
                    processing_update = {
                        "job_id": job.job_id,
                        "row_id": idx,
                        "row_number": idx + 1,
                        "title": title,
                        "status": DocumentStatus.PROCESSING.value,
                        "progress": idx / total,
                    }
                    await redis_client.publish_progress(job.job_id, processing_update)

                    # Process the document
                    result = await self._process_single_document(doc_info, job.config, tagger)

                    # Update job stats
                    if result["success"]:
                        job.processed_count += 1
                        rate_limiter.on_success()
                    else:
                        job.failed_count += 1
                        # Check if rate limited
                        if result.get("rate_limited"):
                            rate_limiter.on_rate_limit()

                    job.results.append(result)

                    # Persist to DB
                    await self._update_document_result_db(
                        job=job,
                        doc_idx=idx,
                        status="success" if result["success"] else "failed",
                        tags=result.get("tags", []),
                        extracted_text=result.get("metadata", {}).get("text_preview"),
                        metadata=result.get("metadata"),
                        error=result.get("error")
                    )

                    # Store result in Redis
                    await redis_client.append_result(job.job_id, {
                        "row_id": idx,
                        "row_number": idx + 1,
                        "title": title,
                        "success": result["success"],
                        "tags": result.get("tags", []),
                        "error": result.get("error"),
                        "metadata": result.get("metadata"),
                    })

                    # Publish completion update
                    completion_update = {
                        "job_id": job.job_id,
                        "row_id": idx,
                        "row_number": idx + 1,
                        "title": title,
                        "status": DocumentStatus.SUCCESS.value if result["success"] else DocumentStatus.FAILED.value,
                        "progress": (idx + 1) / total,
                        "tags": result.get("tags", []),
                        "error": result.get("error"),
                        "model_name": job.config.model_name,
                        "metadata": result.get("metadata"),
                    }
                    await redis_client.publish_progress(job.job_id, completion_update)

                    # Update Redis state
                    await redis_client.update_job_field(job.job_id, "processed_count", str(job.processed_count))
                    await redis_client.update_job_field(job.job_id, "failed_count", str(job.failed_count))
                    await redis_client.update_job_field(job.job_id, "progress", str((idx + 1) / total))

                    # Free memory
                    if result.get("metadata"):
                        result["metadata"].pop("text_preview", None)
                        result["metadata"].pop("extracted_text", None)
                    if (idx + 1) % 10 == 0:
                        gc.collect()
                        logger.info(f"Memory cleanup after document {idx + 1}/{total}")

                    # Adaptive rate limiting between documents
                    if idx < total - 1:
                        await rate_limiter.wait()

                except asyncio.CancelledError:
                    logger.info(f"Job {job.job_id} cancelled (CancelledError).")
                    job.cancelled = True
                    break
                except Exception as e:
                    logger.error(f"Document {idx + 1}/{total} failed: {str(e)}")
                    job.failed_count += 1

                    error_update = {
                        "job_id": job.job_id,
                        "row_id": idx,
                        "row_number": idx + 1,
                        "title": doc_data.get("title", f"Document {idx + 1}"),
                        "status": DocumentStatus.FAILED.value,
                        "progress": (idx + 1) / total,
                        "error": str(e),
                    }
                    await redis_client.publish_progress(job.job_id, error_update)
                    await redis_client.update_job_field(job.job_id, "failed_count", str(job.failed_count))

            # Finalize job
            if job.cancelled:
                job.status = "cancelled"
                await redis_client.update_job_field(job.job_id, "status", "cancelled")
                await self._update_job_status_db(job, "cancelled")

                cancel_update = {
                    "type": "cancelled",
                    "job_id": job.job_id,
                    "processed_count": job.processed_count,
                    "failed_count": job.failed_count,
                    "message": f"Cancelled: {job.processed_count} processed before cancellation",
                }
                await redis_client.publish_progress(job.job_id, cancel_update)
            else:
                job.status = "completed"
                job.end_time = time.time()
                job.progress = 1.0
                await redis_client.update_job_field(job.job_id, "status", "completed")
                await redis_client.update_job_field(job.job_id, "progress", "1.0")
                await self._update_job_status_db(job, "completed")

                completion_msg = {
                    "type": "completed",
                    "job_id": job.job_id,
                    "total_documents": len(job.documents),
                    "processed_count": job.processed_count,
                    "failed_count": job.failed_count,
                    "processing_time": round(job.end_time - job.start_time, 2) if job.end_time and job.start_time else 0,
                    "message": f"Completed: {job.processed_count} succeeded, {job.failed_count} failed",
                }
                await redis_client.publish_progress(job.job_id, completion_msg)

            logger.info(
                f"Job {job.job_id} finished: status={job.status}, "
                f"processed={job.processed_count}, failed={job.failed_count}"
            )

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.end_time = time.time()
            await redis_client.update_job_field(job.job_id, "status", "cancelled")
            await self._update_job_status_db(job, "cancelled")
        except Exception as e:
            job.status = "failed"
            job.end_time = time.time()
            await redis_client.update_job_field(job.job_id, "status", "failed")
            await self._update_job_status_db(job, "failed", str(e))
            logger.error(f"Batch job {job.job_id} failed: {str(e)}", exc_info=True)

            fail_update = {
                "type": "error",
                "job_id": job.job_id,
                "error": str(e),
            }
            await redis_client.publish_progress(job.job_id, fail_update)
        finally:
            self._tasks.pop(job.job_id, None)

    # ---- Database helpers (unchanged) ----

    async def _update_job_status_db(self, job: BatchJob, status: str, error: Optional[str] = None):
        if not job.db_job_id or not self._db_available:
            return False
        max_retries = 3
        retry_delay = 0.5
        for attempt in range(max_retries):
            try:
                result = await self.job_repo.update_job_status(job.db_job_id, status, error)
                if result:
                    logger.info(f"Updated job {job.db_job_id} status to '{status}' in database")
                    return True
                return False
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Failed to update job status after {max_retries} attempts: {e}")
                    return False
        return False

    async def _update_document_result_db(
        self, job: BatchJob, doc_idx: int, status: str,
        tags: Optional[List[str]] = None, extracted_text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None, error: Optional[str] = None
    ):
        if not job.db_job_id or not self._db_available or doc_idx >= len(job.document_ids):
            return False
        max_retries = 2
        retry_delay = 0.3
        for attempt in range(max_retries):
            try:
                doc_id = job.document_ids[doc_idx]
                await self.doc_repo.update_document_result(
                    doc_id=doc_id, status=status, tags=tags,
                    extracted_text=extracted_text, processing_metadata=metadata,
                    error_message=error
                )
                await self.job_repo.increment_job_counts(job.db_job_id, success=(status == "success"))
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.warning(f"Failed to update document result: {e}")
                    return False
        return False

    def _extract_document_info(self, doc_data: Dict[str, Any], column_mapping: Dict[str, str]) -> Dict[str, Any]:
        result = {
            "title": doc_data.get("title") or "Untitled Document",
            "file_path": doc_data.get("file_path", "").strip(),
            "file_source_type": doc_data.get("file_source_type", "url").strip().lower(),
            "description": doc_data.get("description", "").strip()
        }
        if not result["file_path"]:
            raise ValueError("file_path is required")
        if result["file_source_type"] not in ["url", "s3", "local"]:
            result["file_source_type"] = "url"
        return result

    async def _process_single_document(
        self, doc_info: Dict[str, str], config: TaggingConfig, tagger: AITagger
    ) -> Dict[str, Any]:
        result = {
            "title": doc_info.get("title", ""),
            "file_path": doc_info.get("file_path", ""),
            "success": False,
            "tags": [],
            "error": None,
            "metadata": {}
        }
        try:
            file_path = doc_info.get("file_path", "").strip()
            source_type = doc_info.get("file_source_type", "url").strip()
            if not file_path:
                result["error"] = "Missing file path"
                return result

            download_result = self.file_handler.download_file(source_type, file_path)
            if not download_result["success"]:
                result["error"] = f"Download failed: {download_result.get('error', 'Unknown error')}"
                return result

            pdf_bytes = download_result["file_bytes"]
            extraction_result = self.extractor.extract_text(pdf_bytes, config.num_pages, ocr_dpi=300)
            del pdf_bytes
            download_result.pop("file_bytes", None)

            if not extraction_result["success"]:
                result["error"] = f"Text extraction failed: {extraction_result.get('error', 'Unknown error')}"
                return result

            extracted_text = extraction_result.get("extracted_text", "").strip()
            if len(extracted_text) < 50:
                result["error"] = "Insufficient text extracted from document"
                return result

            result["metadata"] = {
                "is_scanned": extraction_result.get("is_scanned"),
                "extraction_method": extraction_result.get("extraction_method"),
                "ocr_confidence": extraction_result.get("ocr_confidence"),
                "page_count": extraction_result.get("page_count"),
                "text_length": len(extracted_text)
            }

            tagging_result = tagger.generate_tags(
                title=doc_info.get("title", ""),
                description=doc_info.get("description", ""),
                content=extracted_text,
                num_tags=config.num_tags,
                detected_language=extraction_result.get("detected_language"),
                language_name=extraction_result.get("language_name"),
                quality_info=extraction_result.get("quality_info")
            )

            if not tagging_result["success"]:
                result["error"] = f"Tag generation failed: {tagging_result.get('error', 'Unknown error')}"
                result["rate_limited"] = tagging_result.get("rate_limited", False)
                return result

            result["success"] = True
            result["tags"] = tagging_result.get("tags", [])
            result["metadata"]["tokens_used"] = tagging_result.get("tokens_used")
            return result

        except Exception as e:
            result["error"] = f"Processing error: {str(e)}"
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            return result

    # ---- Job control ----

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        await redis_client.set_job_command(job_id, "cancel")
        if job_id in self._tasks:
            logger.info(f"Job {job_id} marked for cancellation")
            return True
        # Even if task isn't tracked locally, set the command in case
        return True

    async def pause_job(self, job_id: str) -> bool:
        await redis_client.set_job_command(job_id, "pause")
        return True

    async def resume_job(self, job_id: str) -> bool:
        await redis_client.set_job_command(job_id, "resume")
        return True

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, str]]:
        return await redis_client.get_job_state(job_id)

    def is_job_running(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()


# Global processor instance
batch_processor = AsyncBatchProcessor()
