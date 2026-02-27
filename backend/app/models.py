from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal, Dict, Any
from enum import Enum
from datetime import datetime
from uuid import UUID


class TaggingConfig(BaseModel):
    """Configuration for tagging operation"""
    model_config = ConfigDict(protected_namespaces=())
    
    api_key: str = Field(..., description="OpenRouter API key")
    model_name: str = Field(default="openai/gpt-4o-mini", description="AI model to use")
    num_pages: int = Field(default=3, ge=1, le=10, description="Number of PDF pages to extract")
    num_tags: int = Field(default=8, ge=3, le=15, description="Number of tags to generate")
    exclusion_words: Optional[List[str]] = Field(default=None, description="Words/phrases to exclude from tags")


class SinglePDFRequest(BaseModel):
    """Request for single PDF tagging"""
    config: TaggingConfig


class SinglePDFResponse(BaseModel):
    """Response for single PDF tagging"""
    success: bool
    document_title: str
    tags: List[str]
    extracted_text_preview: str
    processing_time: float
    # OCR metadata
    is_scanned: Optional[bool] = None
    extraction_method: Optional[str] = None
    ocr_confidence: Optional[float] = None
    # Debug field
    raw_ai_response: Optional[str] = None
    error: Optional[str] = None


class BatchDocument(BaseModel):
    """Single document in batch CSV"""
    title: str
    description: Optional[str] = ""
    file_source_type: Literal["s3", "url", "local"]
    file_path: str
    publishing_date: Optional[str] = None
    file_size: Optional[str] = None


class BatchDocumentResult(BaseModel):
    """Result for a single document in batch processing"""
    title: str
    file_path: str
    success: bool
    tags: List[str] = []
    error: Optional[str] = None


class BatchProcessRequest(BaseModel):
    """Request for batch CSV processing"""
    config: TaggingConfig


class BatchProcessResponse(BaseModel):
    """Response for batch processing"""
    success: bool
    total_documents: int
    processed_count: int
    failed_count: int
    output_csv_url: str
    summary_report: Dict[str, Any]
    processing_time: float


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    message: str


# ===== NEW BATCH PROCESSING MODELS =====

class DocumentStatus(str, Enum):
    """Status of document processing"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class PathType(str, Enum):
    """Type of file path"""
    URL = "url"
    S3 = "s3"
    LOCAL = "local"


class PathValidationRequest(BaseModel):
    """Request to validate file paths"""
    paths: List[Dict[str, str]] = Field(..., description="List of {path: string, type: string} objects")


class PathValidationResult(BaseModel):
    """Result of path validation"""
    path: str
    valid: bool
    error: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None


class PathValidationResponse(BaseModel):
    """Response for path validation"""
    results: List[PathValidationResult]
    total: int
    valid_count: int
    invalid_count: int


class WebSocketProgressUpdate(BaseModel):
    """Real-time progress update sent via WebSocket"""
    job_id: str
    row_id: int
    row_number: int  # 1-indexed for display
    title: str
    status: DocumentStatus
    progress: float  # 0.0 to 1.0
    tags: Optional[List[str]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # 'rate-limit', 'model-error', 'network', etc.
    retry_after_ms: Optional[int] = None  # For rate limit errors
    retry_count: Optional[int] = None  # Attempt number
    model_name: Optional[str] = None  # Model being used
    metadata: Optional[Dict[str, Any]] = None


class BatchStartRequest(BaseModel):
    """Request to start batch processing"""
    documents: List[Dict[str, Any]]
    config: TaggingConfig
    column_mapping: Dict[str, str] = Field(
        default={},
        description="Maps column IDs to system field names (title, file_path, file_source_type, description)"
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Optional client-generated job ID. Server generates one if not provided."
    )


class BatchStartResponse(BaseModel):
    """Response when batch processing starts"""
    job_id: str
    total_documents: int
    message: str


# ===== AUTH MODELS (Phase 2) =====

class RegisterRequest(BaseModel):
    """Request for user registration"""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    """Request for user login"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Request to refresh access token"""
    refresh_token: str


class UserResponse(BaseModel):
    """User information response"""
    id: UUID
    email: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime


class LoginResponse(BaseModel):
    """Response for successful login"""
    user: UserResponse
    tokens: TokenResponse


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str
    success: bool = True
