import re
from typing import Tuple, Optional


def validate_api_key(api_key: str) -> Tuple[bool, Optional[str]]:
    """
    Validate OpenRouter API key format
    
    Args:
        api_key: The API key to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key:
        return False, "API key is required"
    
    if not isinstance(api_key, str):
        return False, "API key must be a string"
    
    api_key = api_key.strip()
    
    if len(api_key) < 10:
        return False, "API key is too short"
    
    # OpenRouter keys typically start with sk-or-
    if not api_key.startswith("sk-"):
        return False, "Invalid API key format. OpenRouter keys typically start with 'sk-'"
    
    return True, None


def validate_model_name(model_name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate AI model name format
    
    Args:
        model_name: The model name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not model_name:
        return False, "Model name is required"
    
    if not isinstance(model_name, str):
        return False, "Model name must be a string"
    
    model_name = model_name.strip()
    
    # Model names are typically in format: provider/model-name
    if '/' not in model_name:
        return False, "Model name should be in format: provider/model-name"
    
    return True, None


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL format
    
    Args:
        url: The URL to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is required"
    
    if not isinstance(url, str):
        return False, "URL must be a string"
    
    url = url.strip()
    
    # Basic URL validation
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )
    
    if not url_pattern.match(url):
        return False, "Invalid URL format"
    
    return True, None


def validate_file_size(size_bytes: int, max_size_mb: int = 50) -> Tuple[bool, Optional[str]]:
    """
    Validate file size
    
    Args:
        size_bytes: File size in bytes
        max_size_mb: Maximum allowed size in megabytes
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if size_bytes <= 0:
        return False, "File is empty"
    
    if size_bytes > max_size_bytes:
        return False, f"File too large. Maximum size is {max_size_mb}MB"
    
    return True, None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing potentially dangerous characters
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed"
    
    # Remove path separators
    filename = filename.replace('/', '_').replace('\\', '_')
    
    # Remove other potentially dangerous characters
    filename = re.sub(r'[<>:"|?*]', '', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        max_name_len = 255 - len(ext) - 1
        filename = f"{name[:max_name_len]}.{ext}" if ext else name[:255]
    
    return filename or "unnamed"

