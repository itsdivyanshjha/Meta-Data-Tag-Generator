import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "document-tagger",
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Set up and configure a logger
    
    Args:
        name: Logger name
        level: Logging level
        format_string: Custom format string
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    
    # Create formatter
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    formatter = logging.Formatter(format_string)
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


# Default logger instance
default_logger = setup_logger()


def log_info(message: str):
    """Log info message"""
    default_logger.info(message)


def log_error(message: str):
    """Log error message"""
    default_logger.error(message)


def log_warning(message: str):
    """Log warning message"""
    default_logger.warning(message)


def log_debug(message: str):
    """Log debug message"""
    default_logger.debug(message)

