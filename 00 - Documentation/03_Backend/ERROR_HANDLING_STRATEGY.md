# ⚠️ Error Handling Strategy

**Location**: `03_Backend/ERROR_HANDLING_STRATEGY.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-03

---

## 1. Error Categories

### 1.1 Error Classification

| Category | Code Range | Auto-Retry | User Action |
|----------|------------|------------|-------------|
| **Network** | 1xxx | ✅ 3x | Retry button |
| **Authentication** | 2xxx | ❌ | Re-login |
| **API** | 3xxx | ⚠️ Depends | View log |
| **Rate Limit** | 4xxx | ✅ After delay | Wait/Retry |
| **Validation** | 5xxx | ❌ | Edit prompt |
| **Processing** | 6xxx | ❌ | Report bug |
| **File System** | 7xxx | ❌ | Check path |

---

## 2. Error Codes

### 2.1 Network Errors (1xxx)

| Code | Name | Description | Retry |
|------|------|-------------|-------|
| 1001 | `NETWORK_TIMEOUT` | Request timeout | ✅ 3x |
| 1002 | `CONNECTION_REFUSED` | Server unreachable | ✅ 3x |
| 1003 | `DNS_RESOLUTION_FAILED` | Cannot resolve host | ✅ 3x |
| 1004 | `SSL_ERROR` | Certificate issue | ❌ |

### 2.2 Authentication Errors (2xxx)

| Code | Name | Description | Retry |
|------|------|-------------|-------|
| 2001 | `TOKEN_EXPIRED` | OAuth token expired | ❌ Re-login |
| 2002 | `RECAPTCHA_EXPIRED` | reCAPTCHA > 2min | ✅ Get new |
| 2003 | `RECAPTCHA_CHALLENGE` | Manual solve needed | ❌ Show browser |
| 2004 | `SESSION_INVALID` | Cookie invalid | ❌ Re-login |
| 2005 | `PROFILE_NOT_FOUND` | Chrome profile missing | ❌ Configure |

### 2.3 API Errors (3xxx)

| Code | Name | Description | Retry |
|------|------|-------------|-------|
| 3001 | `API_ERROR` | Generic API failure | ⚠️ 1x |
| 3002 | `OPERATION_NOT_FOUND` | Poll ID invalid | ❌ |
| 3003 | `GENERATION_FAILED` | Video gen failed | ⚠️ 1x |
| 3004 | `UPSCALE_FAILED` | Upscale failed | ⚠️ 1x |
| 3005 | `UPLOAD_FAILED` | Image upload failed | ✅ 3x |

### 2.4 Rate Limit Errors (4xxx)

| Code | Name | Description | Retry |
|------|------|-------------|-------|
| 4001 | `RATE_LIMIT_EXCEEDED` | Too many requests | ✅ After 60s |
| 4002 | `QUOTA_EXCEEDED` | Daily quota hit | ❌ Wait 24h |
| 4003 | `CONCURRENT_LIMIT` | Too many parallel | ✅ Queue |

### 2.5 Validation Errors (5xxx)

| Code | Name | Description | Retry |
|------|------|-------------|-------|
| 5001 | `INVALID_PROMPT` | Prompt rejected | ❌ Edit |
| 5002 | `PROMPT_TOO_LONG` | Exceeds limit | ❌ Shorten |
| 5003 | `NSFW_DETECTED` | Content policy | ❌ Edit |
| 5004 | `INVALID_IMAGE` | Image format bad | ❌ Replace |
| 5005 | `IMAGE_TOO_LARGE` | File size exceeded | ❌ Compress |

### 2.6 Processing Errors (6xxx)

| Code | Name | Description | Retry |
|------|------|-------------|-------|
| 6001 | `FRAME_EXTRACTION_FAILED` | Can't extract frame | ❌ Manual |
| 6002 | `VIDEO_CORRUPT` | Downloaded video bad | ✅ Redownload |
| 6003 | `THUMBNAIL_FAILED` | Can't generate thumb | ❌ Ignore |

### 2.7 File System Errors (7xxx)

| Code | Name | Description | Retry |
|------|------|-------------|-------|
| 7001 | `OUTPUT_DIR_NOT_FOUND` | Path doesn't exist | ❌ Configure |
| 7002 | `PERMISSION_DENIED` | Can't write file | ❌ Fix perms |
| 7003 | `DISK_FULL` | No space left | ❌ Free space |
| 7004 | `FILE_EXISTS` | Would overwrite | ⚠️ Ask user |

---

## 3. Retry Strategy

### 3.1 Retry Configuration

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

RETRY_CONFIG = {
    "network": {
        "max_attempts": 3,
        "wait_min": 1,
        "wait_max": 10,
        "exponential_base": 2
    },
    "rate_limit": {
        "max_attempts": 5,
        "wait_fixed": 60  # seconds
    },
    "api": {
        "max_attempts": 2,
        "wait_min": 2,
        "wait_max": 5
    }
}
```

### 3.2 Retry Decorator

```python
from tenacity import retry, stop_after_attempt, wait_exponential

class RetryableError(Exception):
    """Base class for errors that can be retried."""
    pass

class NetworkError(RetryableError):
    pass

class RateLimitError(RetryableError):
    pass

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(NetworkError)
)
async def make_api_request(endpoint: str, payload: dict):
    """API request with automatic retry on network errors."""
    try:
        response = await api_client.post(endpoint, json=payload)
        return response
    except ConnectionError:
        raise NetworkError("Connection failed")
```

---

## 4. Error Handling Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      ERROR HANDLING FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐                                                │
│  │ Exception    │                                                │
│  │ Occurred     │                                                │
│  └──────┬───────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐     ┌──────────────┐                          │
│  │ Classify     │────►│ Get Error    │                          │
│  │ Error        │     │ Code         │                          │
│  └──────────────┘     └──────┬───────┘                          │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │ Retryable?   │     │ Retryable?   │     │ Not Retry    │     │
│  │ (Network)    │     │ (Rate Limit) │     │              │     │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘     │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │ Retry with   │     │ Wait 60s     │     │ Update UI    │     │
│  │ Backoff      │     │ Then Retry   │     │ Show Error   │     │
│  └──────┬───────┘     └──────────────┘     └──────┬───────┘     │
│         │                                         │             │
│         ▼                                         ▼             │
│  ┌──────────────┐                         ┌──────────────┐     │
│  │ Max Retries? │                         │ User Action  │     │
│  └──────┬───────┘                         │ Required     │     │
│         │ Yes                             └──────────────┘     │
│         ▼                                                       │
│  ┌──────────────┐                                               │
│  │ Mark Failed  │                                               │
│  │ Enable [🔄]  │                                               │
│  └──────────────┘                                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. UI Error Display

### 5.1 Status Column Format

| Status | Display | Tooltip |
|--------|---------|---------|
| Network Error | `❌ Network` | "Connection failed, click retry" |
| Auth Error | `❌ Auth` | "Session expired, please login" |
| Rate Limit | `⏳ Rate Limit` | "Waiting 60s before retry" |
| Validation | `❌ Invalid` | "Prompt rejected by API" |
| Failed | `❌ Failed` | Click [📋] for details |

### 5.2 Error Log Popup

```
┌─────────────────────────────────────────────────────────────────┐
│ 📋 ERROR LOG - Row #5                                       [X] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Error Code: 5001 - INVALID_PROMPT                                │
│ Time: 2026-02-03 15:30:45                                        │
│                                                                  │
│ Message:                                                         │
│ "The prompt contains content that violates our usage policies."  │
│                                                                  │
│ Prompt:                                                          │
│ "A warrior with a [REDACTED] weapon..."                          │
│                                                                  │
│ Suggestion:                                                      │
│ • Remove or modify flagged content                               │
│ • Use alternative wording                                        │
│                                                                  │
│ [📝 Edit Prompt] [🔄 Retry] [📋 Copy Log]                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Error Handler Implementation

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable

class ErrorCategory(Enum):
    NETWORK = "network"
    AUTH = "auth"
    API = "api"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    PROCESSING = "processing"
    FILE_SYSTEM = "file_system"

@dataclass
class VEOError:
    code: int
    name: str
    message: str
    category: ErrorCategory
    retryable: bool
    user_action: Optional[str] = None

class ErrorHandler:
    """Centralized error handling for VEO operations."""
    
    ERROR_MAP = {
        1001: VEOError(1001, "NETWORK_TIMEOUT", "Request timeout", 
                       ErrorCategory.NETWORK, True),
        2002: VEOError(2002, "RECAPTCHA_EXPIRED", "Token expired", 
                       ErrorCategory.AUTH, True, "Get new token"),
        4001: VEOError(4001, "RATE_LIMIT_EXCEEDED", "Too many requests", 
                       ErrorCategory.RATE_LIMIT, True, "Wait 60s"),
        5001: VEOError(5001, "INVALID_PROMPT", "Prompt rejected", 
                       ErrorCategory.VALIDATION, False, "Edit prompt"),
    }
    
    @classmethod
    def handle(cls, exception: Exception, row_id: int, 
               callback: Callable[[int, VEOError], None]):
        """
        Handle exception and notify UI.
        
        Args:
            exception: The caught exception
            row_id: Row that failed
            callback: UI update callback
        """
        error = cls.classify(exception)
        callback(row_id, error)
        
        if error.retryable:
            return True  # Should retry
        return False
    
    @classmethod
    def classify(cls, exception: Exception) -> VEOError:
        """Classify exception into VEOError."""
        # Match exception to error code
        if isinstance(exception, TimeoutError):
            return cls.ERROR_MAP[1001]
        if "rate limit" in str(exception).lower():
            return cls.ERROR_MAP[4001]
        # ... more classification
        
        # Default unknown error
        return VEOError(9999, "UNKNOWN", str(exception),
                       ErrorCategory.API, False)
```

---

## Cross-References

- [MULTITHREADING_ARCHITECTURE.md](./MULTITHREADING_ARCHITECTURE.md) - Worker retry logic
- [TAB_06_QUEUE_MANAGER.md](../01_UI_UX/TAB_06_QUEUE_MANAGER.md) - Error display UI
- [API_ENDPOINTS.md](../../Research/reference/API_ENDPOINTS.md) - API error responses
