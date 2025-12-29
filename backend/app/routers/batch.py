"""
Batch Processing Router

Provides endpoints for:
- WebSocket-based real-time batch processing
- Path validation before processing
- CSV template download
- Legacy CSV upload processing
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from app.models import (
    BatchProcessResponse, 
    TaggingConfig,
    PathValidationRequest,
    PathValidationResponse,
    PathValidationResult,
    BatchStartRequest,
    BatchStartResponse,
    DocumentStatus
)
from app.services.csv_processor import CSVProcessor
from app.services.async_batch_processor import batch_processor, AsyncBatchProcessor
from app.services.exclusion_parser import ExclusionListParser
from app.services.file_handler import FileHandler
from typing import Optional, List, Dict, Any
import time
import json
import base64
import logging
import requests
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== WEBSOCKET BATCH PROCESSING =====

@router.websocket("/ws/{job_id}")
async def batch_progress_websocket(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time batch processing progress
    
    Flow:
    1. Client connects with a job_id
    2. Client sends BatchStartRequest JSON
    3. Server processes documents and sends progress updates
    4. Server sends final completion message
    
    Message format (client → server):
    {
        "documents": [...],
        "config": {...},
        "column_mapping": {...}
    }
    
    Message format (server → client):
    {
        "job_id": "...",
        "row_id": 0,
        "row_number": 1,
        "title": "...",
        "status": "processing|success|failed",
        "progress": 0.5,
        "tags": [...],
        "error": null,
        "metadata": {...}
    }
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for job {job_id}")
    
    try:
        # Wait for the batch start request
        data = await websocket.receive_json()
        
        # Parse the request
        documents = data.get("documents", [])
        config_data = data.get("config", {})
        column_mapping = data.get("column_mapping", {})
        
        if not documents:
            await websocket.send_json({
                "error": "No documents provided",
                "job_id": job_id
            })
            await websocket.close()
            return
        
        if not config_data.get("api_key"):
            await websocket.send_json({
                "error": "API key is required",
                "job_id": job_id
            })
            await websocket.close()
            return
        
        # Create config
        config = TaggingConfig(**config_data)
        
        # Send acknowledgment
        await websocket.send_json({
            "type": "started",
            "job_id": job_id,
            "total_documents": len(documents),
            "message": f"Starting processing of {len(documents)} documents"
        })
        
        # Create and process the batch job
        processor = AsyncBatchProcessor()
        job = await processor.start_job(documents, config, column_mapping)
        
        # Override job_id to match the one from URL
        job.job_id = job_id
        
        # Process the batch (this sends progress updates via websocket)
        await processor.process_batch(job, websocket)
        
        # Check if job was cancelled
        if job.cancelled:
            logger.info(f"Job {job_id} was cancelled. Skipping final message.")
            # Try to send cancellation message if WebSocket still open
            try:
                await websocket.send_json({
                    "type": "cancelled",
                    "job_id": job_id,
                    "processed_count": job.processed_count,
                    "failed_count": job.failed_count,
                    "message": f"Processing cancelled: {job.processed_count} documents processed before cancellation"
                })
            except:
                pass
        else:
            # Send final completion message
            try:
                await websocket.send_json({
                    "type": "completed",
                    "job_id": job_id,
                    "total_documents": len(documents),
                    "processed_count": job.processed_count,
                    "failed_count": job.failed_count,
                    "processing_time": round(job.end_time - job.start_time, 2) if job.end_time else 0,
                    "message": f"Completed: {job.processed_count} succeeded, {job.failed_count} failed"
                })
            except:
                logger.debug(f"Could not send completion message for job {job_id} (WebSocket likely closed)")
        
        # Cleanup
        processor.cleanup_job(job_id)
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}. Cancelling processing.")
        # Cancel the job immediately when WebSocket disconnects
        if job_id in processor.active_jobs:
            processor.active_jobs[job_id].cancelled = True
            logger.info(f"Job {job_id} cancelled due to WebSocket disconnect")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in WebSocket message: {str(e)}")
        try:
            await websocket.send_json({
                "error": "Invalid JSON format",
                "job_id": job_id
            })
        except:
            pass
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({
                "error": str(e),
                "job_id": job_id
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass


# ===== PATH VALIDATION =====

@router.post("/validate-paths", response_model=PathValidationResponse)
async def validate_paths(request: PathValidationRequest):
    """
    Validate file paths before processing
    
    Performs quick checks to verify paths are accessible:
    - URL: HTTP HEAD request
    - S3: Check object exists (if configured)
    - Local: Check file exists
    
    Request body:
    {
        "paths": [
            {"path": "https://example.com/doc.pdf", "type": "url"},
            {"path": "s3://bucket/key.pdf", "type": "s3"},
            {"path": "/path/to/file.pdf", "type": "local"}
        ]
    }
    """
    logger.info(f"Starting path validation for {len(request.paths)} paths")
    start_time = time.time()
    
    results: List[PathValidationResult] = []
    valid_count = 0
    invalid_count = 0
    
    handler = FileHandler()
    
    for item in request.paths:
        path = item.get("path", "").strip()
        path_type = item.get("type", "url").lower().strip()
        
        result = PathValidationResult(
            path=path,
            valid=False,
            error=None
        )
        
        if not path:
            result.error = "Empty path"
            invalid_count += 1
            results.append(result)
            continue
        
        try:
            if path_type == "url":
                result = await _validate_url(path)
            elif path_type == "s3":
                result = _validate_s3(path, handler)
            elif path_type == "local":
                result = _validate_local(path)
            else:
                result.error = f"Unknown path type: {path_type}"
            
            if result.valid:
                valid_count += 1
            else:
                invalid_count += 1
                
        except Exception as e:
            result.error = str(e)
            invalid_count += 1
        
        results.append(result)
    
    elapsed_time = time.time() - start_time
    logger.info(f"Path validation completed in {elapsed_time:.2f}s: {valid_count} valid, {invalid_count} invalid out of {len(results)} total")
    
    return PathValidationResponse(
        results=results,
        total=len(results),
        valid_count=valid_count,
        invalid_count=invalid_count
    )


async def _validate_url(url: str) -> PathValidationResult:
    """Validate URL with HEAD request"""
    result = PathValidationResult(path=url, valid=False)
    
    if not url.startswith(('http://', 'https://')):
        result.error = "URL must start with http:// or https://"
        return result
    
    try:
        # Use HEAD request to check without downloading
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Run in thread pool to not block
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: requests.head(url, timeout=10, headers=headers, allow_redirects=True)
        )
        
        if response.status_code == 200:
            result.valid = True
            result.content_type = response.headers.get('Content-Type', '')
            
            # Try to get file size
            content_length = response.headers.get('Content-Length')
            if content_length:
                result.size = int(content_length)
        elif response.status_code == 405:
            # HEAD not allowed, try GET with stream
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=10, headers=headers, stream=True)
            )
            if response.status_code == 200:
                result.valid = True
                result.content_type = response.headers.get('Content-Type', '')
            else:
                result.error = f"HTTP {response.status_code}"
            response.close()
        else:
            result.error = f"HTTP {response.status_code}"
            
    except requests.Timeout:
        result.error = "Request timed out"
    except requests.RequestException as e:
        result.error = f"Request failed: {str(e)}"
    except Exception as e:
        result.error = str(e)
    
    return result


def _validate_s3(path: str, handler: FileHandler) -> PathValidationResult:
    """Validate S3 path"""
    result = PathValidationResult(path=path, valid=False)
    
    # If it's actually a URL, validate as URL
    if path.startswith('http'):
        # Can't validate async here, so just check format
        result.valid = True
        result.error = None
        return result
    
    if not handler.s3_client:
        result.error = "S3 client not configured"
        return result
    
    try:
        # Parse s3://bucket/key format
        if path.startswith('s3://'):
            parts = path[5:].split('/', 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ''
        else:
            parts = path.split('/', 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ''
        
        if not key:
            result.error = "Invalid S3 path format"
            return result
        
        # Check if object exists
        response = handler.s3_client.head_object(Bucket=bucket, Key=key)
        result.valid = True
        result.size = response.get('ContentLength')
        result.content_type = response.get('ContentType', '')
        
    except handler.s3_client.exceptions.NoSuchKey:
        result.error = "Object not found"
    except handler.s3_client.exceptions.NoSuchBucket:
        result.error = "Bucket not found"
    except Exception as e:
        result.error = f"S3 error: {str(e)}"
    
    return result


def _validate_local(path: str) -> PathValidationResult:
    """Validate local file path"""
    from pathlib import Path
    
    result = PathValidationResult(path=path, valid=False)
    
    try:
        file_path = Path(path)
        
        if not file_path.exists():
            result.error = "File not found"
        elif not file_path.is_file():
            result.error = "Not a file"
        else:
            result.valid = True
            result.size = file_path.stat().st_size
            
    except Exception as e:
        result.error = str(e)
    
    return result


# ===== LEGACY CSV PROCESSING =====

@router.post("/process", response_model=BatchProcessResponse)
async def process_batch_csv(
    csv_file: UploadFile = File(...),
    config: str = Form(...),
    exclusion_file: Optional[UploadFile] = File(None)
):
    """
    Process batch CSV with multiple documents and optional exclusion list
    
    This is the legacy endpoint that processes synchronously.
    For real-time progress, use the WebSocket endpoint instead.
    
    Args:
        csv_file: Uploaded CSV file
        config: JSON string of TaggingConfig
        exclusion_file: Optional file containing words/phrases to exclude from tags (.txt or .pdf)
    """
    start_time = time.time()
    
    try:
        # Parse config
        config_dict = json.loads(config)
        tagging_config = TaggingConfig(**config_dict)
        
        # Parse exclusion file if provided
        if exclusion_file and exclusion_file.filename:
            logger.info(f"Processing exclusion file for batch: {exclusion_file.filename}")
            exclusion_bytes = await exclusion_file.read()
            
            try:
                parser = ExclusionListParser()
                exclusion_words = parser.parse_from_file(exclusion_bytes, exclusion_file.filename)
                tagging_config.exclusion_words = list(exclusion_words)
                logger.info(f"Loaded {len(exclusion_words)} exclusion words for batch processing")
            except Exception as e:
                logger.error(f"Failed to parse exclusion file: {str(e)}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Failed to parse exclusion file: {str(e)}"
                )
        
        # Validate file type
        if not csv_file.filename or not csv_file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV file.")
        
        # Read CSV
        csv_content = await csv_file.read()
        
        if not csv_content:
            raise HTTPException(status_code=400, detail="Empty CSV file")
        
        # Process batch
        processor = CSVProcessor(tagging_config)
        result = processor.process_csv(csv_content)
        
        processing_time = time.time() - start_time
        
        return BatchProcessResponse(
            success=result["success"],
            total_documents=result["total_documents"],
            processed_count=result["processed_count"],
            failed_count=result["failed_count"],
            output_csv_url=result["output_csv_url"],
            summary_report=result["summary"],
            processing_time=round(processing_time, 2)
        )
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid config JSON format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ===== CSV TEMPLATE =====

@router.get("/template")
async def get_csv_template():
    """
    Get a sample CSV template for batch processing
    """
    template = """title,description,file_source_type,file_path,publishing_date,file_size
"Training Manual","PMSPECIAL training document",url,https://example.com/doc1.pdf,2025-01-15,1.2MB
"Annual Report 2024","Financial report",url,https://example.com/doc2.pdf,2024-12-31,2.5MB
"Policy Guidelines","New policy document",url,https://example.com/policy.pdf,2025-02-01,850KB"""
    
    return JSONResponse(
        content={
            "template": template,
            "columns": [
                {"name": "title", "required": True, "description": "Document title"},
                {"name": "description", "required": False, "description": "Document description"},
                {"name": "file_source_type", "required": True, "description": "Source type: url, s3, or local"},
                {"name": "file_path", "required": True, "description": "Path or URL to the file"},
                {"name": "publishing_date", "required": False, "description": "Publication date"},
                {"name": "file_size", "required": False, "description": "File size"}
            ],
            "note": "For real-time processing with progress updates, use the WebSocket endpoint at /api/batch/ws/{job_id}"
        }
    )
