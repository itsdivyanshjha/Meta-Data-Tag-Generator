import requests
from typing import Optional, Dict, Any
from pathlib import Path
import os

# Optional boto3 import for S3 support
try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False


class FileHandler:
    """Handle file downloads from different sources"""
    
    def __init__(
        self, 
        aws_access_key: Optional[str] = None, 
        aws_secret_key: Optional[str] = None, 
        aws_region: str = "us-east-1"
    ):
        self.s3_client = None
        if HAS_BOTO3 and aws_access_key and aws_secret_key:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=aws_region
            )
    
    def download_file(self, source_type: str, file_path: str) -> Dict[str, Any]:
        """
        Download file from various sources
        
        Args:
            source_type: 's3', 'url', or 'local'
            file_path: Path/URL to file
            
        Returns:
            dict with file_bytes and metadata
        """
        try:
            source_type = source_type.lower().strip()
            
            if source_type == "url":
                return self._download_from_url(file_path)
            elif source_type == "s3":
                return self._download_from_s3(file_path)
            elif source_type == "local":
                return self._read_local_file(file_path)
            else:
                return {
                    "success": False, 
                    "error": f"Unknown source type: {source_type}. Use 'url', 's3', or 'local'."
                }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _download_from_url(self, url: str) -> Dict[str, Any]:
        """Download from HTTP/HTTPS URL"""
        try:
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                return {"success": False, "error": "Invalid URL. Must start with http:// or https://"}
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, timeout=60, headers=headers, stream=True)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and not url.lower().endswith('.pdf'):
                # Still try to download, but warn
                pass
            
            file_bytes = response.content
            
            return {
                "success": True,
                "file_bytes": file_bytes,
                "size": len(file_bytes),
                "source": "url",
                "content_type": content_type
            }
            
        except requests.Timeout:
            return {"success": False, "error": "Request timed out"}
        except requests.RequestException as e:
            return {"success": False, "error": f"Failed to download: {str(e)}"}
    
    def _download_from_s3(self, s3_path: str) -> Dict[str, Any]:
        """Download from S3"""
        # If it's actually a URL, use URL download
        if s3_path.startswith('http'):
            return self._download_from_url(s3_path)
        
        if not HAS_BOTO3:
            return {"success": False, "error": "S3 support not available. Install boto3."}
        
        if not self.s3_client:
            return {"success": False, "error": "S3 client not configured. Provide AWS credentials."}
        
        try:
            # Parse s3://bucket/key format
            if s3_path.startswith('s3://'):
                parts = s3_path[5:].split('/', 1)
                bucket = parts[0]
                key = parts[1] if len(parts) > 1 else ''
            else:
                # Assume format: bucket/key
                parts = s3_path.split('/', 1)
                bucket = parts[0]
                key = parts[1] if len(parts) > 1 else ''
            
            if not key:
                return {"success": False, "error": "Invalid S3 path format"}
            
            obj = self.s3_client.get_object(Bucket=bucket, Key=key)
            file_bytes = obj['Body'].read()
            
            return {
                "success": True,
                "file_bytes": file_bytes,
                "size": len(file_bytes),
                "source": "s3"
            }
            
        except Exception as e:
            return {"success": False, "error": f"S3 download failed: {str(e)}"}
    
    def _read_local_file(self, file_path: str) -> Dict[str, Any]:
        """Read local file"""
        try:
            path = Path(file_path)
            
            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}
            
            if not path.is_file():
                return {"success": False, "error": f"Not a file: {file_path}"}
            
            # Check file size (limit to 50MB)
            file_size = path.stat().st_size
            if file_size > 50 * 1024 * 1024:
                return {"success": False, "error": "File too large (max 50MB)"}
            
            with open(path, 'rb') as f:
                file_bytes = f.read()
            
            return {
                "success": True,
                "file_bytes": file_bytes,
                "size": len(file_bytes),
                "source": "local"
            }
            
        except PermissionError:
            return {"success": False, "error": f"Permission denied: {file_path}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {str(e)}"}

