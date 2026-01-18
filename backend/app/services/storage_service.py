"""MinIO Storage Service for file upload/download operations"""

import io
import uuid
import logging
from typing import Optional, BinaryIO, Dict, Any
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Service for MinIO object storage operations"""

    def __init__(self):
        self._client: Optional[Minio] = None
        self._bucket = settings.minio_bucket

    @property
    def client(self) -> Minio:
        """Lazy initialization of MinIO client"""
        if self._client is None:
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            self._ensure_bucket()
        return self._client

    def _ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist"""
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info(f"Created MinIO bucket: {self._bucket}")
            else:
                logger.info(f"MinIO bucket exists: {self._bucket}")
        except S3Error as e:
            logger.error(f"Failed to ensure bucket: {e}")
            raise

    def upload_file(
        self,
        file_data: bytes,
        object_name: Optional[str] = None,
        content_type: str = "application/octet-stream",
        prefix: str = ""
    ) -> Dict[str, Any]:
        """
        Upload a file to MinIO storage

        Args:
            file_data: File content as bytes
            object_name: Optional custom object name (auto-generated if not provided)
            content_type: MIME type of the file
            prefix: Optional path prefix (e.g., "documents/", "exports/")

        Returns:
            Dict with success status, object_name, and size
        """
        try:
            if object_name is None:
                object_name = str(uuid.uuid4())

            if prefix:
                object_name = f"{prefix.rstrip('/')}/{object_name}"

            file_stream = io.BytesIO(file_data)
            file_size = len(file_data)

            self.client.put_object(
                self._bucket,
                object_name,
                file_stream,
                file_size,
                content_type=content_type
            )

            logger.info(f"Uploaded file to MinIO: {object_name} ({file_size} bytes)")

            return {
                "success": True,
                "object_name": object_name,
                "bucket": self._bucket,
                "size": file_size
            }

        except S3Error as e:
            logger.error(f"MinIO upload error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def download_file(self, object_name: str) -> Dict[str, Any]:
        """
        Download a file from MinIO storage

        Args:
            object_name: The object name/path in the bucket

        Returns:
            Dict with success status and file_bytes
        """
        try:
            response = self.client.get_object(self._bucket, object_name)
            file_bytes = response.read()
            response.close()
            response.release_conn()

            logger.info(f"Downloaded file from MinIO: {object_name} ({len(file_bytes)} bytes)")

            return {
                "success": True,
                "file_bytes": file_bytes,
                "object_name": object_name,
                "size": len(file_bytes)
            }

        except S3Error as e:
            logger.error(f"MinIO download error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Download error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for downloading a file

        Args:
            object_name: The object name/path in the bucket
            expires: URL expiration time (default 1 hour)

        Returns:
            Dict with success status and url
        """
        try:
            url = self.client.presigned_get_object(
                self._bucket,
                object_name,
                expires=expires
            )

            return {
                "success": True,
                "url": url,
                "expires_in_seconds": int(expires.total_seconds())
            }

        except S3Error as e:
            logger.error(f"MinIO presigned URL error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def delete_file(self, object_name: str) -> Dict[str, Any]:
        """
        Delete a file from MinIO storage

        Args:
            object_name: The object name/path in the bucket

        Returns:
            Dict with success status
        """
        try:
            self.client.remove_object(self._bucket, object_name)
            logger.info(f"Deleted file from MinIO: {object_name}")

            return {
                "success": True,
                "object_name": object_name
            }

        except S3Error as e:
            logger.error(f"MinIO delete error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def file_exists(self, object_name: str) -> bool:
        """Check if a file exists in storage"""
        try:
            self.client.stat_object(self._bucket, object_name)
            return True
        except S3Error:
            return False

    def list_files(self, prefix: str = "", recursive: bool = True) -> Dict[str, Any]:
        """
        List files in storage with optional prefix

        Args:
            prefix: Filter by path prefix
            recursive: Whether to list recursively

        Returns:
            Dict with success status and list of objects
        """
        try:
            objects = self.client.list_objects(
                self._bucket,
                prefix=prefix,
                recursive=recursive
            )

            files = []
            for obj in objects:
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag
                })

            return {
                "success": True,
                "files": files,
                "count": len(files)
            }

        except S3Error as e:
            logger.error(f"MinIO list error: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Global storage service instance
storage_service = StorageService()
