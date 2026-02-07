# VEO Error Handling Guide

**Date**: 2026-02-01  
**Version**: 1.0  
**Scope**: Complete Error Catalog \u0026 Resolution Strategies

---

## 📋 Overview

This guide catalogs all observed error scenarios from VEO API analysis across 29 HAR files, providing resolution strategies and best practices for error handling.

---

## 1️⃣ Error Categories

### A. reCAPTCHA Errors (403)

#### Error 403: reCAPTCHA Evaluation Failed
**Response**:
```json
{
  "error": {
    "code": 403,
    "message": "reCAPTCHA evaluation failed",
    "status": "PERMISSION_DENIED",
    "details": [{
      "@type": "type.googleapis.com/google.rpc.ErrorInfo",
      "reason": "PUBLIC_ERROR_SOMETHING_WENT_WRONG"
    }]
  }
}
```

**Common Causes**:
- Expired reCAPTCHA token (default TTL: 2 minutes)
- Invalid token format
- Token reuse attempt
- Bot-like behavior detected

**Resolution**:
1. Refresh reCAPTCHA token before request
2. Ensure token is from v3 (not v2)
3. Add human-like delays between actions (500ms-2s recommended)
4. Check `applicationType` is set to `RECAPTCHA_APPLICATION_TYPE_WEB`

---

### B. Authentication Errors (401)

#### Error 401: Unauthorized
**Response**:
```json
{
  "error": {
    "code": 401,
    "message": "Unauthorized",
    "status": "UNAUTHENTICATED"
  }
}
```

**Common Causes**:
- Missing Authorization header
- Expired Bearer token
- Invalid token format

**Resolution**:
1. Verify `Authorization: Bearer ya29...` header is present
2. Refresh OAuth2 token if expired (typical validity: 1 hour)
3. Ensure token has correct scopes

---

### C. Not Found Errors (404)

#### Error 404: Media Not Found
**Scope**: Media download, image upscale

**Response**:
```json
{
  "error": {
    "code": 404,
    "message": "Media not found",
    "status": "NOT_FOUND"
  }
}
```

**Common Causes**:
- Expired `mediaId` (TTL: ~24 hours)
- Incorrect project ID
- Media generation failed but not reflected in status

**Resolution**:
1. Re-upload image to get fresh `mediaId`
2. Verify `projectId` matches current session
3. Check generation status before attempting download

---

### D. Rate Limiting (429)

#### Error 429: Too Many Requests
**Response**:
```json
{
  "error": {
    "code": 429,
    "message": "Quota exceeded",
    "status": "RESOURCE_EXHAUSTED"
  }
}
```

**Headers** (typical):
```http
Retry-After: 60
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1738300800
```

**Tier Limits** (observed):
| Tier | Videos/min | Images/min | Concurrent Batches |
|------|------------|------------|-------------------|
| Free | 2 | 5 | 1 |
| Tier 1 | 5 | 15 | 2 |
| Tier 2 | 10 | 30 | 4 |

**Resolution**:
1. Implement exponential backoff (1s, 2s, 4s, 8s...)
2. Respect `Retry-After` header
3. Use batch generation (4 videos/request) to maximize throughput
4. Upgrade tier if consistent rate limiting

---

### E. Server Errors (500, 503)

#### Error 500: Internal Server Error
**Response**:
```json
{
  "error": {
    "code": 500,
    "message": "Internal error encountered",
    "status": "INTERNAL"
  }
}
```

**Resolution**:
1. Retry with exponential backoff (3 attempts max)
2. Check status page: https://status.google.com
3. If persistent, report via Google Cloud Console

#### Error 503: Service Unavailable
**Common during**: Peak hours, maintenance

**Resolution**:
1. Wait 30-60 seconds before retry
2. Implement circuit breaker pattern
3. Queue requests for later retry

---

### F. Validation Errors (400)

#### Error 400: Invalid Payload
**Scenarios**:
1. **Aspect Ratio Mismatch** (Start + End frames)
```json
{
  "error": {
    "code": 400,
    "message": "Start image and end image must have matching aspect ratios",
    "status": "INVALID_ARGUMENT"
  }
}
```

2. **Invalid Seed**
```json
{
  "error": {
    "code": 400,
    "message": "Seed must be between 0 and 99999",
    "status": "INVALID_ARGUMENT"
  }
}
```

3. **Invalid Model Key**
```json
{
  "error": {
    "code": 400,
    "message": "Unknown model key",
    "status": "INVALID_ARGUMENT"
  }
}
```

**Resolution**:
- Validate all payload fields before submission
- Use model keys from official documentation
- Ensure aspect ratio consistency across frames

---

## 2️⃣ Retry Strategies

### Exponential Backoff Implementation

```python
import time

def exponential_backoff_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except HTTPError as e:
            if e.status_code in [500, 503]:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait_time)
            elif e.status_code == 429:
                retry_after = e.headers.get('Retry-After', 60)
                time.sleep(int(retry_after))
            else:
                raise  # Don't retry 400, 401, 403, 404
    raise Exception(f"Failed after {max_retries} retries")
```

### Error-Specific Policies

| Error Code | Retry? | Strategy | Max Retries |
|------------|--------|----------|-------------|
| 400 | ❌ No | Fix payload + resubmit | 0 |
| 401 | ⚠️ Once | Refresh token + retry | 1 |
| 403 | ⚠️ Once | Refresh reCAPTCHA + retry | 1 |
| 404 | ❌ No | Re-upload media | 0 |
| 429 | ✅ Yes | Exponential backoff | 5 |
| 500 | ✅ Yes | Exponential backoff | 3 |
| 503 | ✅ Yes | Linear backoff (30s) | 3 |

---

## 3️⃣ Status-Based Errors

### Generation Failures

**Status**: `MEDIA_GENERATION_STATUS_FAILED`  
**Occurs In**: `searchProjectScenes` polling response

```json
{
  "scenes": [{
    "status": "FAILED",
    "failureReason": "CONTENT_POLICY_VIOLATION"
  }]
}
```

**Failure Reasons**:
| Reason | Description | Resolution |
|--------|-------------|------------|
| `CONTENT_POLICY_VIOLATION` | Prompt violates safety policies | Revise prompt to remove prohibited content |
| `INVALID_START_IMAGE` | Start frame format issue | Re-upload as JPEG, ensure valid Base64 |
| `TIMEOUT` | Generation exceeded time limit | Retry with simpler prompt or different seed |
| `QUOTA_EXCEEDED` | Account quota depleted | Wait for quota reset or upgrade tier |

---

## 4️⃣ Best Practices

### 1. Graceful Degradation
```python
def generate_video_with_fallback(prompt, start_image):
    try:
        return generate_video(prompt, start_image, model="veo_3_1_t2v_fast")
    except HTTPError as e:
        if e.status_code == 429:
            # Fallback to queued generation
            return queue_for_later(prompt, start_image)
        raise
```

### 2. Circuit Breaker Pattern
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func()
            self.failures = 0
            self.state = "CLOSED"
            return result
        except Exception:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.threshold:
                self.state = "OPEN"
            raise
```

### 3. Logging \u0026 Monitoring
```python
import logging

logger = logging.getLogger(__name__)

def log_api_error(error, context):
    logger.error(
        f"VEO API Error: {error.status_code} {error.message}",
        extra={
            "error_code": error.status_code,
            "error_status": error.status,
            "request_id": context.get("request_id"),
            "project_id": context.get("project_id"),
            "endpoint": context.get("endpoint")
        }
    )
```

---

## 5️⃣ Error Response Structure

### Standard Format
```json
{
  "error": {
    "code": 403,
    "message": "Human-readable description",
    "status": "GRPC_STATUS_CODE",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "MACHINE_READABLE_REASON",
        "domain": "labs.google.com",
        "metadata": {}
      }
    ]
  }
}
```

### Fields Explanation
- **code**: HTTP status code
- **message**: Human-readable description
- **status**: gRPC status enum (e.g., `PERMISSION_DENIED`)
- **details.reason**: Machine-readable error identifier
- **details.metadata**: Additional context (varies by error)

---

## 6️⃣ Quick Reference

### Common Error \u0026 Fix Pairs
| Symptom | Error Code | Quick Fix |
|---------|------------|-----------|
| "recaptcha failed" | 403 | Refresh token |
| "Unauthorized" | 401 | Refresh auth bearer |
| "Media not found" | 404 | Re-upload image |
| "Quota exceeded" | 429 | Wait \u0026 retry |
| "Internal error" | 500 | Retry 3x with backoff |
| START/END mismatch | 400 | Match aspect ratios |

---

**Related Documentation**:
- [VEO_FLOW_ANALYSIS_REPORT.md](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/Documentation/VEO_FLOW_ANALYSIS_REPORT.md)
- [VEO_QUICK_REFERENCE.md](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/Documentation/VEO_QUICK_REFERENCE.md)
- [AUTHENTICATION_GUIDE.md](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/Documentation/AUTHENTICATION_GUIDE.md)
