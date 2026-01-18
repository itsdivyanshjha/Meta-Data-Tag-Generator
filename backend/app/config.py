from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application configuration settings"""

    # API Settings
    app_name: str = "Document Meta-Tagging API"
    debug: bool = False

    # OpenRouter Settings
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    default_model: str = "openai/gpt-4o-mini"

    # AWS Settings (optional, for S3)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"

    # Processing Limits
    max_pdf_size_mb: int = 50
    max_pages_to_extract: int = 10
    max_tags: int = 15
    min_tags: int = 3

    # Text Processing
    max_words_for_ai: int = 2000

    # Database Settings (Phase 2)
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "metatag"
    db_password: str = "metatag_secret"
    db_name: str = "metatag_db"
    database_url: Optional[str] = None

    # MinIO Settings (Phase 2)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket: str = "metatag-files"
    minio_secure: bool = False

    # JWT Settings (Phase 2)
    jwt_secret_key: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

