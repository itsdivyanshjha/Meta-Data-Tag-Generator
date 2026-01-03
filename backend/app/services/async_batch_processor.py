"""
Async Batch Processor with WebSocket Progress Updates

Processes documents asynchronously and sends real-time updates via WebSocket.
"""

import asyncio
import uuid
import time
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from fastapi import WebSocket

from app.models import (
    TaggingConfig, 
    DocumentStatus, 
    WebSocketProgressUpdate
)
from app.services.pdf_extractor import PDFExtractor
from app.services.ai_tagger import AITagger
from app.services.file_handler import FileHandler

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


class AsyncBatchProcessor:
    """
    Async batch processor that sends real-time updates via WebSocket
    
    Usage:
        processor = AsyncBatchProcessor()
        job = await processor.start_job(documents, config, column_mapping)
        await processor.process_batch(job, websocket)
    """
    
    # Store active jobs (in production, use Redis or database)
    active_jobs: Dict[str, BatchJob] = {}
    
    # Rate limiting: delay between documents (seconds)
    RATE_LIMIT_DELAY = 0.5
    
    def __init__(self):
        self.extractor = PDFExtractor()
        self.file_handler = FileHandler()
    
    async def start_job(
        self,
        documents: List[Dict[str, Any]],
        config: TaggingConfig,
        column_mapping: Dict[str, str]
    ) -> BatchJob:
        """
        Initialize a new batch job
        
        Args:
            documents: List of document data (from spreadsheet rows)
            config: Tagging configuration
            column_mapping: Maps column IDs to system fields
            
        Returns:
            BatchJob instance
        """
        job_id = str(uuid.uuid4())
        
        job = BatchJob(
            job_id=job_id,
            documents=documents,
            config=config,
            column_mapping=column_mapping,
            status="pending",
            start_time=time.time()
        )
        
        self.active_jobs[job_id] = job
        logger.info(f"Created batch job {job_id} with {len(documents)} documents")
        
        return job
    
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
                    
                    logger.error(f"Error processing document {idx}: {str(e)}")
                    job.failed_count += 1
                    
                    # Try to send error update (may fail if WebSocket closed)
                    try:
                        await self._send_update(
                            websocket,
                            job_id=job.job_id,
                            row_id=idx,
                            row_number=idx + 1,
                            title=doc_data.get("title", f"Document {idx + 1}"),
                            status=DocumentStatus.FAILED,
                            progress=(idx + 1) / total,
                            error=str(e)
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
                
                logger.info(
                    f"Batch job {job.job_id} completed: "
                    f"{job.processed_count} succeeded, {job.failed_count} failed"
                )
            
            return job
            
        except asyncio.CancelledError:
            logger.info(f"Job {job.job_id} cancelled (outer CancelledError).")
            job.cancelled = True
            job.status = "cancelled"
            job.end_time = time.time()
            return job
        except Exception as e:
            job.status = "failed"
            job.end_time = time.time()
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

