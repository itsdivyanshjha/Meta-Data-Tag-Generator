from fastapi import APIRouter
from app.models import HealthCheckResponse

router = APIRouter()


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    return HealthCheckResponse(
        status="healthy",
        version="1.0.0",
        message="Document Meta-Tagging API is running"
    )


@router.get("/status")
async def status():
    """Simple status endpoint"""
    return {"status": "ok", "service": "document-meta-tagging-api"}

