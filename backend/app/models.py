from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


class TaggingConfig(BaseModel):
    """Configuration for tagging operation"""
    api_key: str = Field(..., description="OpenRouter API key")
    model_name: str = Field(default="openai/gpt-4o-mini", description="AI model to use")
    num_pages: int = Field(default=3, ge=1, le=10, description="Number of PDF pages to extract")
    num_tags: int = Field(default=8, ge=3, le=15, description="Number of tags to generate")


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
    raw_ai_response: Optional[str] = None  # Debug field
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
