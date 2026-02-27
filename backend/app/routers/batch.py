"""
Batch Processing Router

Provides endpoints for:
- REST-based job start (POST /start)
- WebSocket-based progress observation (ws/{job_id})
- Job control (cancel, pause, resume, status)
- Path validation before processing
- CSV template download
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends
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
from app.services.auth_service import AuthService
from app.services import redis_client
from app.dependencies.auth import get_current_active_user
from typing import Optional, List, Dict, Any
from uuid import UUID
import time
import json
import logging
import requests
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== AUTHENTICATION HELPERS =====

async def get_user_from_websocket(websocket: WebSocket) -> Optional[UUID]:
    """Extract and verify user from WebSocket query parameters or headers"""
    try:
        query_params = dict(websocket.query_params)
        token = query_params.get("token")
        if not token:
            headers = dict(websocket.headers)
            auth_header = headers.get("authorization") or headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        if not token:
            return None
        auth_service = AuthService()
        payload = auth_service.verify_access_token(token)
        if payload is None:
            return None
        return UUID(payload["sub"])
    except Exception as e:
        logger.debug(f"Failed to extract user from WebSocket: {e}")
        return None


# ===== REST-BASED JOB START =====

@router.post("/start", response_model=BatchStartResponse)
async def start_batch_job(
    request: BatchStartRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Start a new batch processing job.

    Processing runs in the background. Use the WebSocket endpoint
    /ws/{job_id} to observe real-time progress, or poll
    /jobs/{job_id}/status for current state.
    """
    documents = request.documents
    config = request.config
    column_mapping = request.column_mapping

    if not documents:
        raise HTTPException(status_code=400, detail="No documents provided")
    if not config.api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    user_id = UUID(current_user["id"]) if isinstance(current_user.get("id"), str) else current_user.get("id")

    # Generate job_id server-side (or accept from client via request body if provided)
    job_id = request.job_id if request.job_id else str(__import__('uuid').uuid4())

    job = await batch_processor.start_job(
        job_id=job_id,
        documents=documents,
        config=config,
        column_mapping=column_mapping,
        user_id=user_id
    )

    return BatchStartResponse(
        job_id=job.job_id,
        total_documents=len(documents),
        message=f"Started processing of {len(documents)} documents"
    )


# ===== WEBSOCKET PROGRESS OBSERVER =====

@router.websocket("/ws/{job_id}")
async def batch_progress_websocket(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for observing batch processing progress.

    This is a READ-ONLY observer. Processing runs independently in the
    background. Disconnecting the WebSocket does NOT cancel the job.

    On connect, the server sends a "catchup" message with all results so far,
    then streams live updates via Redis pub/sub.

    Authentication: pass token as query parameter ?token=...
    """
    await websocket.accept()
    logger.info(f"WebSocket observer connected for job {job_id}")

    user_id = await get_user_from_websocket(websocket)
    if not user_id:
        await websocket.send_json({"error": "Authentication required", "job_id": job_id})
        await websocket.close(code=1008)
        return

    try:
        # Send catch-up state
        job_state = await redis_client.get_job_state(job_id)
        existing_results = await redis_client.get_results(job_id)

        await websocket.send_json({
            "type": "catchup",
            "job_id": job_id,
            "state": job_state or {},
            "results": existing_results,
        })

        # If job is already done, send completion and close
        if job_state and job_state.get("status") in ("completed", "failed", "cancelled"):
            await websocket.send_json({
                "type": job_state["status"],
                "job_id": job_id,
                "processed_count": job_state.get("processed_count", "0"),
                "failed_count": job_state.get("failed_count", "0"),
                "message": f"Job already {job_state['status']}",
            })
            await websocket.close()
            return

        # Subscribe to live progress updates
        pubsub = await redis_client.subscribe_progress(job_id)

        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        _get_pubsub_message(pubsub),
                        timeout=30.0
                    )
                    if message and message["type"] == "message":
                        data = json.loads(message["data"])
                        await websocket.send_json(data)

                        msg_type = data.get("type", "")
                        if msg_type in ("completed", "cancelled", "error"):
                            break

                except asyncio.TimeoutError:
                    # Send keepalive and check if job finished
                    state = await redis_client.get_job_field(job_id, "status")
                    await websocket.send_json({"type": "keepalive", "job_id": job_id, "status": state})
                    if state in ("completed", "failed", "cancelled"):
                        await websocket.send_json({
                            "type": state,
                            "job_id": job_id,
                            "message": f"Job {state}",
                        })
                        break

        except WebSocketDisconnect:
            logger.info(f"WebSocket observer disconnected for job {job_id}. Job continues running.")

        finally:
            await pubsub.unsubscribe()
            await pubsub.close()

    except WebSocketDisconnect:
        logger.info(f"WebSocket observer disconnected for job {job_id}. Job continues running.")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({"error": str(e), "job_id": job_id})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def _get_pubsub_message(pubsub):
    """Async wrapper to get a message from Redis pub/sub."""
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        if message:
            return message
        await asyncio.sleep(0.1)


# ===== JOB CONTROL ENDPOINTS =====

@router.get("/jobs/{job_id}/status")
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Get current status of a batch job from Redis."""
    state = await redis_client.get_job_state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    results_count = await redis_client.get_results_count(job_id)
    return {
        "job_id": job_id,
        "status": state.get("status", "unknown"),
        "progress": float(state.get("progress", 0)),
        "processed_count": int(state.get("processed_count", 0)),
        "failed_count": int(state.get("failed_count", 0)),
        "total": int(state.get("total", 0)),
        "results_count": results_count,
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Cancel a running batch job."""
    await batch_processor.cancel_job(job_id)
    return {"message": f"Cancel command sent to job {job_id}"}


@router.post("/jobs/{job_id}/pause")
async def pause_job(
    job_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Pause a running batch job."""
    await batch_processor.pause_job(job_id)
    return {"message": f"Pause command sent to job {job_id}"}


@router.post("/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    """Resume a paused batch job."""
    await batch_processor.resume_job(job_id)
    return {"message": f"Resume command sent to job {job_id}"}


@router.get("/active")
async def get_active_jobs(
    current_user: dict = Depends(get_current_active_user)
):
    """List all currently active/processing jobs."""
    active_ids = await redis_client.get_active_job_ids()
    jobs = []
    user_id = str(current_user.get("id", ""))
    for jid in active_ids:
        state = await redis_client.get_job_state(jid)
        if state and (not user_id or state.get("user_id", "") == user_id):
            jobs.append({
                "job_id": jid,
                "status": state.get("status"),
                "progress": float(state.get("progress", 0)),
                "processed_count": int(state.get("processed_count", 0)),
                "failed_count": int(state.get("failed_count", 0)),
                "total": int(state.get("total", 0)),
            })
    return {"jobs": jobs}


# ===== PATH VALIDATION =====

@router.post("/validate-paths", response_model=PathValidationResponse)
async def validate_paths(
    request: PathValidationRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """Validate file paths before processing. Requires authentication."""
    logger.info(f"Starting path validation for {len(request.paths)} paths")
    start_time = time.time()

    results: List[PathValidationResult] = []
    valid_count = 0
    invalid_count = 0

    handler = FileHandler()

    for item in request.paths:
        path = item.get("path", "").strip()
        path_type = item.get("type", "url").lower().strip()

        result = PathValidationResult(path=path, valid=False, error=None)

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
    logger.info(f"Path validation completed in {elapsed_time:.2f}s: {valid_count} valid, {invalid_count} invalid")

    return PathValidationResponse(
        results=results, total=len(results),
        valid_count=valid_count, invalid_count=invalid_count
    )


async def _validate_url(url: str) -> PathValidationResult:
    """Validate URL with HEAD request"""
    result = PathValidationResult(path=url, valid=False)
    if not url.startswith(('http://', 'https://')):
        result.error = "URL must start with http:// or https://"
        return result
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: requests.head(url, timeout=10, headers=headers, allow_redirects=True)
        )
        if response.status_code == 200:
            result.valid = True
            result.content_type = response.headers.get('Content-Type', '')
            content_length = response.headers.get('Content-Length')
            if content_length:
                result.size = int(content_length)
        elif response.status_code == 405:
            response = await loop.run_in_executor(
                None, lambda: requests.get(url, timeout=10, headers=headers, stream=True)
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
    if path.startswith('http'):
        result.valid = True
        return result
    if not handler.s3_client:
        result.error = "S3 client not configured"
        return result
    try:
        if path.startswith('s3://'):
            parts = path[5:].split('/', 1)
            bucket, key = parts[0], parts[1] if len(parts) > 1 else ''
        else:
            parts = path.split('/', 1)
            bucket, key = parts[0], parts[1] if len(parts) > 1 else ''
        if not key:
            result.error = "Invalid S3 path format"
            return result
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
            result.error = f"File not found: {path}"
        elif not file_path.is_file():
            result.error = "Not a file"
        elif not file_path.is_absolute():
            result.error = "Relative paths not supported"
        else:
            result.valid = True
            result.size = file_path.stat().st_size
    except Exception as e:
        result.error = f"Path validation error: {str(e)}"
    return result


# ===== LEGACY CSV PROCESSING =====

@router.post("/process", response_model=BatchProcessResponse)
async def process_batch_csv(
    csv_file: UploadFile = File(...),
    config: str = Form(...),
    exclusion_file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_active_user)
):
    """Legacy endpoint that processes synchronously."""
    start_time = time.time()
    try:
        config_dict = json.loads(config)
        tagging_config = TaggingConfig(**config_dict)

        if exclusion_file and exclusion_file.filename:
            exclusion_bytes = await exclusion_file.read()
            try:
                parser = ExclusionListParser()
                exclusion_words = parser.parse_from_file(exclusion_bytes, exclusion_file.filename)
                tagging_config.exclusion_words = list(exclusion_words)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to parse exclusion file: {str(e)}")

        if not csv_file.filename or not csv_file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="Invalid file type")

        csv_content = await csv_file.read()
        if not csv_content:
            raise HTTPException(status_code=400, detail="Empty CSV file")

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
async def get_csv_template(current_user: dict = Depends(get_current_active_user)):
    """Get a sample CSV template for batch processing."""
    template = """title,description,file_source_type,file_path,publishing_date,file_size
"Training Manual","PMSPECIAL training document",url,https://example.com/doc1.pdf,2025-01-15,1.2MB
"Annual Report 2024","Financial report",url,https://example.com/doc2.pdf,2024-12-31,2.5MB"""

    return JSONResponse(content={
        "template": template,
        "columns": [
            {"name": "title", "required": True, "description": "Document title"},
            {"name": "description", "required": False, "description": "Document description"},
            {"name": "file_source_type", "required": True, "description": "Source type: url, s3, or local"},
            {"name": "file_path", "required": True, "description": "Path or URL to the file"},
            {"name": "publishing_date", "required": False, "description": "Publication date"},
            {"name": "file_size", "required": False, "description": "File size"}
        ]
    })
