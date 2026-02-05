"""
Async Batch Processor with WebSocket Progress Updates

Processes documents asynchronously and sends real-time updates via WebSocket.
Now with database persistence for jobs and documents.
"""

import asyncio
import uuid
import time
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from uuid import UUID
from fastapi import WebSocket

from app.models import (
    TaggingConfig,
    DocumentStatus,
    WebSocketProgressUpdate
)
from app.services.pdf_extractor import PDFExtractor
from app.services.ai_tagger import AITagger
from app.services.file_handler import FileHandler
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
    cancelled: bool = False  # Flag to indicate if job was cancelled
    # Database persistence fields
    db_job_id: Optional[UUID] = None  # UUID from database
    user_id: Optional[UUID] = None  # User who initiated the job
    document_ids: List[UUID] = field(default_factory=list)  # Document UUIDs from database


class AsyncBatchProcessor:
    """
    Async batch processor that sends real-time updates via WebSocket

    Usage:
        processor = AsyncBatchProcessor()
        job = await processor.start_job(documents, config, column_mapping, user_id)
        await processor.process_batch(job, websocket)
    """

    # Store active jobs (in production, use Redis or database)
    active_jobs: Dict[str, BatchJob] = {}

    # Rate limiting: delay between documents (seconds)
    # Increased to reduce rate limit hits from OpenRouter API
    RATE_LIMIT_DELAY = 2.0

    def __init__(self):
        self.extractor = PDFExtractor()
        self.file_handler = FileHandler()
        self.job_repo = JobRepository()
        self.doc_repo = DocumentRepository()
        self._db_available = True  # Flag to track if DB is available
    
    async def start_job(
        self,
        documents: List[Dict[str, Any]],
        config: TaggingConfig,
        column_mapping: Dict[str, str],
        user_id: Optional[UUID] = None
    ) -> BatchJob:
        """
        Initialize a new batch job

        Args:
            documents: List of document data (from spreadsheet rows)
            config: Tagging configuration
            column_mapping: Maps column IDs to system fields
            user_id: Optional user ID for authenticated users

        Returns:
            BatchJob instance
        """
        job_id = str(uuid.uuid4())
        db_job_id = None
        document_ids = []

        # Try to persist to database
        try:
            # Create job in database
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

            # Create document records in database
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

        self.active_jobs[job_id] = job
        logger.info(f"Created batch job {job_id} with {len(documents)} documents")

        return job
    
    async def _update_job_status_db(self, job: BatchJob, status: str, error: Optional[str] = None):
        """Update job status in database with retry logic"""
        if not job.db_job_id:
            logger.warning(f"Job {job.job_id} has no db_job_id, skipping status update to DB")
            return False
        if not self._db_available:
            logger.warning(f"Database not available for job {job.job_id}, skipping status update")
            return False
        
        # Retry logic for database updates
        max_retries = 3
        retry_delay = 0.5  # seconds
        
        for attempt in range(max_retries):
            try:
                result = await self.job_repo.update_job_status(job.db_job_id, status, error)
                if result:
                    logger.info(f"✅ Updated job {job.db_job_id} status to '{status}' in database (attempt {attempt + 1})")
                    return True
                else:
                    logger.warning(f"Job {job.db_job_id} not found in database for status update")
                    return False
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to update job status (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"❌ Failed to update job status after {max_retries} attempts: {e}")
                    return False
        
        return False

    async def _update_document_result_db(
        self,
        job: BatchJob,
        doc_idx: int,
        status: str,
        tags: Optional[List[str]] = None,
        extracted_text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        """Update document result in database with retry logic"""
        if not job.db_job_id or not self._db_available or doc_idx >= len(job.document_ids):
            return False
        
        max_retries = 2
        retry_delay = 0.3
        
        for attempt in range(max_retries):
            try:
                doc_id = job.document_ids[doc_idx]
                await self.doc_repo.update_document_result(
                    doc_id=doc_id,
                    status=status,
                    tags=tags,
                    extracted_text=extracted_text,
                    processing_metadata=metadata,
                    error_message=error
                )
                # Update job progress counters
                await self.job_repo.increment_job_counts(job.db_job_id, success=(status == "success"))
                logger.debug(f"Updated document {doc_id} with status '{status}'")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"Failed to update document result (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.warning(f"Failed to update document result after {max_retries} attempts: {e}")
                    return False
        
        return False

    async def process_batch(
        self,
        job: BatchJob,
        websocket: WebSocket
    ) -> BatchJob:
        """
        Process all documents in the batch and send WebSocket updates

        Args:
            job: The batch job to process
            websocket: WebSocket connection for sending updates

        Returns:
            Updated BatchJob with results
        """
        try:
            job.status = "processing"
            await self._update_job_status_db(job, "processing")
            total = len(job.documents)
            
            # Create AI tagger instance
            tagger = AITagger(
                job.config.api_key, 
                job.config.model_name,
                exclusion_words=job.config.exclusion_words
            )
            
            for idx, doc_data in enumerate(job.documents):
                # CHECK FOR CANCELLATION BEFORE EACH DOCUMENT
                if job.cancelled:
                    logger.info(f"Job {job.job_id} cancelled. Stopping at document {idx + 1}/{total}")
                    job.status = "cancelled"
                    job.end_time = time.time()
                    return job
                
                # Check if WebSocket is still connected before processing
                websocket_closed = False
                try:
                    state = websocket.client_state
                    state_name = state.name if hasattr(state, 'name') else str(state)
                    if state_name != "CONNECTED":
                        logger.info(f"WebSocket disconnected for job {job.job_id} (state: {state_name}). Cancelling job.")
                        websocket_closed = True
                except (AttributeError, TypeError, Exception) as e:
                    # If we can't check state, try to detect disconnect during send
                    logger.debug(f"Could not check WebSocket state: {e}")
                
                if websocket_closed:
                    job.cancelled = True
                    job.status = "cancelled"
                    job.end_time = time.time()
                    return job
                
                try:
                    # Extract document info using column mapping
                    doc_info = self._extract_document_info(doc_data, job.column_mapping)
                    
                    # Send "processing" update (will fail and set cancelled if WebSocket closed)
                    try:
                        await self._send_update(
                            websocket,
                            job_id=job.job_id,
                            row_id=idx,
                            row_number=idx + 1,
                            title=doc_info.get("title", f"Document {idx + 1}"),
                            status=DocumentStatus.PROCESSING,
                            progress=idx / total
                        )
                    except Exception as send_error:
                        # If send fails, check if it's a disconnect
                        error_msg = str(send_error).lower()
                        if "close" in error_msg or "disconnect" in error_msg or "send" in error_msg:
                            logger.info(f"WebSocket send failed for job {job.job_id}. Cancelling job.")
                            job.cancelled = True
                            job.status = "cancelled"
                            job.end_time = time.time()
                            return job
                        # Re-raise if it's a different error
                        raise
                    
                    # CHECK AGAIN AFTER SEND UPDATE (in case it detected disconnect)
                    if job.cancelled:
                        logger.info(f"Job {job.job_id} cancelled during update. Stopping.")
                        job.status = "cancelled"
                        job.end_time = time.time()
                        return job
                    
                    # Process the document
                    result = await self._process_single_document(
                        doc_info, 
                        job.config, 
                        tagger
                    )
                    
                    # CHECK FOR CANCELLATION AFTER PROCESSING
                    if job.cancelled:
                        logger.info(f"Job {job.job_id} cancelled. Stopping after document {idx + 1}.")
                        job.status = "cancelled"
                        job.end_time = time.time()
                        return job
                    
                    # Update job stats
                    if result["success"]:
                        job.processed_count += 1
                    else:
                        job.failed_count += 1

                    job.results.append(result)

                    # Persist result to database
                    await self._update_document_result_db(
                        job=job,
                        doc_idx=idx,
                        status="success" if result["success"] else "failed",
                        tags=result.get("tags", []),
                        extracted_text=result.get("metadata", {}).get("text_preview"),
                        metadata=result.get("metadata"),
                        error=result.get("error")
                    )
                    
                    # Send completion update with tags
                    await self._send_update(
                        websocket,
                        job_id=job.job_id,
                        row_id=idx,
                        row_number=idx + 1,
                        title=doc_info.get("title", f"Document {idx + 1}"),
                        status=DocumentStatus.SUCCESS if result["success"] else DocumentStatus.FAILED,
                        progress=(idx + 1) / total,
                        tags=result.get("tags", []),
                        error=result.get("error"),
                        model_name=job.config.model_name,
                        metadata=result.get("metadata")
                    )
                    
                    # Final cancellation check before rate limit sleep
                    if job.cancelled:
                        logger.info(f"Job {job.job_id} cancelled. Stopping.")
                        job.status = "cancelled"
                        job.end_time = time.time()
                        return job
                    
                    # Rate limiting to avoid API overload
                    if idx < total - 1:
                        # Use asyncio.sleep which can be interrupted
                        try:
                            await asyncio.sleep(self.RATE_LIMIT_DELAY)
                        except asyncio.CancelledError:
                            logger.info(f"Job {job.job_id} cancelled during rate limit delay.")
                            job.cancelled = True
                            job.status = "cancelled"
                            job.end_time = time.time()
                            return job
                    
                except asyncio.CancelledError:
                    logger.info(f"Job {job.job_id} cancelled (CancelledError). Stopping.")
                    job.cancelled = True
                    job.status = "cancelled"
                    job.end_time = time.time()
                    return job
                except Exception as e:
                    # Check if this is a WebSocket disconnect error
                    error_msg = str(e).lower()
                    if "close" in error_msg or "disconnect" in error_msg or "send" in error_msg:
                        logger.info(f"WebSocket error detected for job {job.job_id}. Cancelling job.")
                        job.cancelled = True
                        job.status = "cancelled"
                        job.end_time = time.time()
                        return job
                    
                    # Determine error type for frontend notification
                    error_type = "unknown"
                    retry_after_ms = None
                    retry_count = None
                    
                    error_str = str(e)
                    if "429" in error_str or "rate" in error_msg:
                        error_type = "rate-limit"
                        retry_after_ms = 2000  # Default retry after 2 seconds
                        retry_count = 1  # Could track this in the future
                    elif "400" in error_str or "bad request" in error_msg:
                        error_type = "model-error"
                    elif "connection" in error_msg or "network" in error_msg or "timeout" in error_msg:
                        error_type = "network"
                    
                    logger.error(f"❌ Document {idx + 1}/{total} failed: {str(e)}")
                    if error_type == "rate-limit":
                        logger.warning(f"   ⏱️ Rate limited. Waiting before next attempt...")
                    job.failed_count += 1
                    
                    # Try to send error update with error type (may fail if WebSocket closed)
                    try:
                        await self._send_update(
                            websocket,
                            job_id=job.job_id,
                            row_id=idx,
                            row_number=idx + 1,
                            title=doc_data.get("title", f"Document {idx + 1}"),
                            status=DocumentStatus.FAILED,
                            progress=(idx + 1) / total,
                            error=str(e),
                            error_type=error_type,
                            retry_after_ms=retry_after_ms,
                            retry_count=retry_count,
                            model_name=job.config.model_name
                        )
                    except:
                        # WebSocket probably closed, cancel job
                        job.cancelled = True
                        job.status = "cancelled"
                        job.end_time = time.time()
                        return job
            
            # Only mark as completed if not cancelled
            if not job.cancelled:
                job.status = "completed"
                job.end_time = time.time()
                job.progress = 1.0
                
                # Ensure database update succeeds before marking job complete
                db_updated = await self._update_job_status_db(job, "completed")
                if db_updated:
                    logger.info(
                        f"✅ Batch job {job.job_id} COMPLETED AND SAVED: "
                        f"{job.processed_count} succeeded, {job.failed_count} failed, {total - job.processed_count - job.failed_count} skipped"
                    )
                else:
                    logger.error(f"⚠️ Batch job {job.job_id} completed but FAILED TO SAVE to database!")
                    # Still mark as completed in memory even if DB failed
            else:
                await self._update_job_status_db(job, "cancelled")
                logger.info(f"Job {job.job_id} was marked as cancelled in database")

            return job

        except asyncio.CancelledError:
            logger.info(f"Job {job.job_id} cancelled (outer CancelledError).")
            job.cancelled = True
            job.status = "cancelled"
            job.end_time = time.time()
            await self._update_job_status_db(job, "cancelled")
            return job
        except Exception as e:
            job.status = "failed"
            job.end_time = time.time()
            await self._update_job_status_db(job, "failed", str(e))
            logger.error(f"Batch job {job.job_id} failed: {str(e)}")
            raise
    
    def _extract_document_info(
        self, 
        doc_data: Dict[str, Any], 
        column_mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Extract document info from row data using column mapping
        
        Args:
            doc_data: The row data (system_field → value from frontend)
            column_mapping: Not used anymore - frontend sends mapped data
            
        Returns:
            Dict with title, file_path, file_source_type, description
        """
        # Default values
        result = {
            "title": doc_data.get("title") or "Untitled Document",
            "file_path": doc_data.get("file_path", "").strip(),
            "file_source_type": doc_data.get("file_source_type", "url").strip().lower(),
            "description": doc_data.get("description", "").strip()
        }
        
        # Validate file_path is provided
        if not result["file_path"]:
            raise ValueError("file_path is required")
        
        # Validate file_source_type
        if result["file_source_type"] not in ["url", "s3", "local"]:
            result["file_source_type"] = "url"
        
        return result
    
    async def _process_single_document(
        self,
        doc_info: Dict[str, str],
        config: TaggingConfig,
        tagger: AITagger
    ) -> Dict[str, Any]:
        """
        Process a single document and generate tags
        
        Args:
            doc_info: Document info (title, file_path, file_source_type, description)
            config: Tagging configuration
            tagger: AITagger instance
            
        Returns:
            Dict with success, tags, error, metadata
        """
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
            
            # Download file
            download_result = self.file_handler.download_file(source_type, file_path)
            
            if not download_result["success"]:
                result["error"] = f"Download failed: {download_result.get('error', 'Unknown error')}"
                return result
            
            # Extract text from PDF
            pdf_bytes = download_result["file_bytes"]
            extraction_result = self.extractor.extract_text(pdf_bytes, config.num_pages)
            
            if not extraction_result["success"]:
                result["error"] = f"Text extraction failed: {extraction_result.get('error', 'Unknown error')}"
                return result
            
            extracted_text = extraction_result.get("extracted_text", "").strip()
            
            if len(extracted_text) < 50:
                result["error"] = "Insufficient text extracted from document"
                return result
            
            # Store extraction metadata
            result["metadata"] = {
                "is_scanned": extraction_result.get("is_scanned"),
                "extraction_method": extraction_result.get("extraction_method"),
                "ocr_confidence": extraction_result.get("ocr_confidence"),
                "page_count": extraction_result.get("page_count"),
                "text_length": len(extracted_text)
            }
            
            # Generate tags with language awareness
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
                return result
            
            result["success"] = True
            result["tags"] = tagging_result.get("tags", [])
            result["metadata"]["tokens_used"] = tagging_result.get("tokens_used")
            
            return result
            
        except Exception as e:
            result["error"] = f"Processing error: {str(e)}"
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            return result
    
    async def _send_update(
        self,
        websocket: WebSocket,
        job_id: str,
        row_id: int,
        row_number: int,
        title: str,
        status: DocumentStatus,
        progress: float,
        tags: Optional[List[str]] = None,
        error: Optional[str] = None,
        error_type: Optional[str] = None,
        retry_after_ms: Optional[int] = None,
        retry_count: Optional[int] = None,
        model_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Send progress update via WebSocket. Raises exception if connection closed."""
        # Check WebSocket connection state (handle both enum and string states)
        try:
            state = websocket.client_state
            state_name = state.name if hasattr(state, 'name') else str(state)
            if state_name != "CONNECTED":
                logger.info(f"WebSocket for job {job_id} is not connected (state: {state_name}). Marking as cancelled.")
                # Mark job as cancelled if it exists
                if job_id in self.active_jobs:
                    self.active_jobs[job_id].cancelled = True
                raise ConnectionError(f"WebSocket not connected (state: {state_name})")
        except (AttributeError, TypeError):
            # Fallback: Try to send anyway, exception handling below will catch it
            pass
        
        update = WebSocketProgressUpdate(
            job_id=job_id,
            row_id=row_id,
            row_number=row_number,
            title=title,
            status=status,
            progress=progress,
            tags=tags,
            error=error,
            error_type=error_type,
            retry_after_ms=retry_after_ms,
            retry_count=retry_count,
            model_name=model_name,
            metadata=metadata
        )
        
        try:
            await websocket.send_json(update.model_dump())
        except Exception as e:
            # Mark job as cancelled if connection closed
            error_msg = str(e).lower()
            if "close" in error_msg or "disconnect" in error_msg or "send" in error_msg:
                logger.info(f"WebSocket send failed for job {job_id} (connection closed). Marking as cancelled.")
                # Mark job as cancelled
                if job_id in self.active_jobs:
                    self.active_jobs[job_id].cancelled = True
                raise  # Re-raise so caller knows to stop
            else:
                logger.error(f"Error sending WebSocket update for job {job_id}: {str(e)}")
                raise  # Re-raise non-connection errors
    
    def get_job(self, job_id: str) -> Optional[BatchJob]:
        """Get a job by ID"""
        return self.active_jobs.get(job_id)
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            job.cancelled = True
            logger.info(f"Job {job_id} marked for cancellation")
            return True
        return False
    
    def cleanup_job(self, job_id: str):
        """Remove a completed job from memory"""
        if job_id in self.active_jobs:
            del self.active_jobs[job_id]
            logger.info(f"Cleaned up job {job_id}")


# Global processor instance
batch_processor = AsyncBatchProcessor()

