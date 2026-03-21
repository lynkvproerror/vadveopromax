"""
VEO Pro Max - Error Handler

Reference: SESSION_05_BACKEND_FEATURES.md
Role: Error classification, retry logic, error logging
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Callable, TypeVar
from enum import Enum
from datetime import datetime
from pathlib import Path
import functools
import asyncio
import logging
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class ErrorCategory(str, Enum):
    """Error categories for classification."""
    NETWORK = "network"           # Connection failures, timeouts
    AUTH = "auth"                 # Token expired, invalid credentials
    API = "api"                   # VEO API errors
    RATE_LIMIT = "rate_limit"     # Too many requests
    VALIDATION = "validation"     # Invalid input data
    PROCESSING = "processing"     # Generation/processing errors
    FILE_SYSTEM = "file_system"   # File read/write errors
    POLICY = "policy"  # VEO content policy / safety filter violations


@dataclass
class VEOError:
    """Structured error representation."""
    code: str                          # e.g., "E001", "AUTH_EXPIRED"
    name: str                          # Human-readable name
    message: str                       # Detailed message
    category: ErrorCategory
    retryable: bool = False            # Can be retried automatically
    user_action: Optional[str] = None  # Suggested action for user
    timestamp: datetime = field(default_factory=datetime.now)
    original_error: Optional[Exception] = None
    
    def __str__(self):
        return f"[{self.code}] {self.name}: {self.message}"
    
    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "message": self.message,
            "category": self.category.value,
            "retryable": self.retryable,
            "user_action": self.user_action,
            "timestamp": self.timestamp.isoformat(),
        }


class ErrorHandler:
    """Central error handling and classification.
    
    Features:
    - Error classification by pattern matching
    - Retry decorator with exponential backoff
    - Error logging to file
    """
    
    # Error patterns → VEOError mapping
    ERROR_MAP = {
        # Network errors
        "ECONNREFUSED": VEOError("NET001", "Connection Refused", "Unable to connect to server", ErrorCategory.NETWORK, True, "Check internet connection"),
        "ETIMEDOUT": VEOError("NET002", "Connection Timeout", "Request timed out", ErrorCategory.NETWORK, True, "Try again later"),
        "ENOTFOUND": VEOError("NET003", "DNS Error", "Could not resolve hostname", ErrorCategory.NETWORK, True, "Check internet connection"),
        
        # Auth errors
        "401": VEOError("AUTH001", "Unauthorized", "Authentication failed", ErrorCategory.AUTH, False, "Login again or refresh token"),
        "403": VEOError("AUTH002", "Forbidden", "Access denied", ErrorCategory.AUTH, False, "Check account permissions"),
        "token expired": VEOError("AUTH003", "Token Expired", "Access token has expired", ErrorCategory.AUTH, False, "Refresh token"),
        "invalid token": VEOError("AUTH004", "Invalid Token", "Token is invalid", ErrorCategory.AUTH, False, "Login again"),
        
        # Rate limit
        "429": VEOError("RATE001", "Rate Limited", "Too many requests", ErrorCategory.RATE_LIMIT, True, "Wait and try again"),
        "quota exceeded": VEOError("RATE002", "Quota Exceeded", "Daily quota exceeded", ErrorCategory.RATE_LIMIT, False, "Wait until quota resets"),
        
        # API errors
        "400": VEOError("API001", "Bad Request", "Invalid request format", ErrorCategory.API, False, "Check request parameters"),
        "500": VEOError("API002", "Server Error", "Internal server error", ErrorCategory.API, True, "Try again later"),
        "502": VEOError("API003", "Bad Gateway", "Service temporarily unavailable", ErrorCategory.API, True, "Try again later"),
        "503": VEOError("API004", "Service Unavailable", "Service is down", ErrorCategory.API, True, "Try again later"),
        
        # Processing errors
        "generation failed": VEOError("PROC001", "Generation Failed", "Video generation failed", ErrorCategory.PROCESSING, True, "Try different prompt"),
        "content policy": VEOError("PROC002", "Content Policy", "Content blocked by policy", ErrorCategory.PROCESSING, False, "Modify your prompt"),
        "nsfw": VEOError("PROC003", "NSFW Content", "Inappropriate content detected", ErrorCategory.PROCESSING, False, "Use appropriate content"),
        
        # Validation errors
        "invalid prompt": VEOError("VAL001", "Invalid Prompt", "Prompt validation failed", ErrorCategory.VALIDATION, False, "Fix prompt format"),
        "invalid image": VEOError("VAL002", "Invalid Image", "Image validation failed", ErrorCategory.VALIDATION, False, "Use supported image format"),
        
        # File system errors
        "ENOENT": VEOError("FS001", "File Not Found", "File or directory not found", ErrorCategory.FILE_SYSTEM, False, "Check file path"),
        "EACCES": VEOError("FS002", "Permission Denied", "Cannot access file", ErrorCategory.FILE_SYSTEM, False, "Check file permissions"),
        "ENOSPC": VEOError("FS003", "No Space", "Disk space full", ErrorCategory.FILE_SYSTEM, False, "Free up disk space"),
    }
    
    def __init__(self, log_file: Optional[Path] = None):
        self._log_file = log_file or Path.home() / ".veoauto" / "errors.log"
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup logger
        self._logger = logging.getLogger("veo_errors")
        self._logger.setLevel(logging.ERROR)
        
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(
            self._log_file, maxBytes=5*1024*1024, backupCount=2, encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        self._logger.addHandler(handler)
    
    def classify(self, error: Exception | str, context: Optional[dict] = None) -> VEOError:
        """Classify an error into a VEOError.
        
        Args:
            error: Exception or error message string
            context: Optional context information
        
        Returns:
            Classified VEOError
        """
        error_str = str(error).lower()
        
        # Try to match known patterns
        for pattern, veo_error in self.ERROR_MAP.items():
            if pattern.lower() in error_str:
                result = VEOError(
                    code=veo_error.code,
                    name=veo_error.name,
                    message=f"{veo_error.message}: {str(error)[:200]}",
                    category=veo_error.category,
                    retryable=veo_error.retryable,
                    user_action=veo_error.user_action,
                    original_error=error if isinstance(error, Exception) else None,
                )
                return result
        
        # Default: unknown error
        return VEOError(
            code="UNK001",
            name="Unknown Error",
            message=str(error)[:500],
            category=ErrorCategory.PROCESSING,
            retryable=False,
            user_action="Check logs for details",
            original_error=error if isinstance(error, Exception) else None,
        )
    
    def log_error(self, error: VEOError, context: Optional[dict] = None):
        """Log error to file."""
        log_entry = f"{error.code} | {error.category.value} | {error.name}: {error.message}"
        if context:
            log_entry += f" | Context: {context}"
        
        self._logger.error(log_entry)
    
    def get_recent_errors(self, limit: int = 100) -> list[str]:
        """Get recent errors from log file."""
        if not self._log_file.exists():
            return []
        
        try:
            with open(self._log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            return lines[-limit:]
        except Exception:
            return []


# === RETRY DECORATORS ===

T = TypeVar('T')

def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    retryable_categories: tuple = (ErrorCategory.NETWORK, ErrorCategory.RATE_LIMIT, ErrorCategory.API),
):
    """Decorator for retry with exponential backoff.
    
    Args:
        max_retries: Maximum retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier
        retryable_categories: Error categories to retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            handler = ErrorHandler()
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    veo_error = handler.classify(e)
                    
                    if attempt < max_retries and veo_error.category in retryable_categories:
                        wait_time = delay * (backoff ** attempt)
                        await asyncio.sleep(wait_time)
                    else:
                        handler.log_error(veo_error, {"function": func.__name__})
                        raise
            
            raise last_error
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            handler = ErrorHandler()
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    veo_error = handler.classify(e)
                    
                    if attempt < max_retries and veo_error.category in retryable_categories:
                        import time
                        wait_time = delay * (backoff ** attempt)
                        time.sleep(wait_time)
                    else:
                        handler.log_error(veo_error, {"function": func.__name__})
                        raise
            
            raise last_error
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
