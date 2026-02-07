# VEO Status Codes Reference

Complete list of all status codes and their meanings.

---

## Video Generation Status Codes

### Primary Status Flow

```
MEDIA_GENERATION_STATUS_PENDING
    ↓
MEDIA_GENERATION_STATUS_ACTIVE (or WORKING)
    ↓
MEDIA_GENERATION_STATUS_SUCCESSFUL → Video ready (fifeUrl available)
```

### Status Codes Table

| Status Code | Meaning | Action Required | Typical Duration |
|-------------|---------|-----------------|------------------|
| `MEDIA_GENERATION_STATUS_PENDING` | Queued, not started yet | Continue polling | 0-5s |
| `MEDIA_GENERATION_STATUS_ACTIVE` | Processing | Continue polling | 10-60s |
| `MEDIA_GENERATION_STATUS_WORKING` | Processing (alt name) | Continue polling | 10-60s |
| `MEDIA_GENERATION_STATUS_SUCCESSFUL` | Complete | Extract video URL | - |
| `MEDIA_GENERATION_STATUS_FAILED` | Failed | Handle error | - |

---

## Image Generation Status

**Note**: Image generation is **synchronous** - no status polling needed.

| Response Code | Meaning |
|---------------|---------|
| `200 OK` | Success, images in response |
| `400 Bad Request` | Invalid parameters |
| `401 Unauthorized` | Invalid/expired token |
| `403 Forbidden` | reCAPTCHA validation failed |
| `429 Too Many Requests` | Rate limit exceeded |

---

## HTTP Status Codes

### Success Codes

| Code | Meaning | Context |
|------|---------|---------|
| `200 OK` | Request successful | All endpoints |
| `201 Created` | Resource created | Upload endpoints |

### Client Error Codes

| Code | Meaning | Common Causes | Solution |
|------|---------|---------------|----------|
| `400 Bad Request` | Invalid payload | Missing required fields, invalid JSON | Check request structure |
| `401 Unauthorized` | Invalid auth | Token expired, invalid bearer token | Refresh authorization token |
| `403 Forbidden` | Access denied | reCAPTCHA failed, insufficient permissions | Use valid reCAPTCHA or Authorization header |
| `404 Not Found` | Resource not found | Invalid mediaId, expired URL | Verify IDs, regenerate if expired |
| `429 Too Many Requests` | Rate limited | Too many requests too fast | Implement exponential backoff |

### Server Error Codes

| Code | Meaning | Action |
|------|---------|--------|
| `500 Internal Server Error` | Server error | Retry after delay |
| `503 Service Unavailable` | Server overload | Retry with exponential backoff |

---

## Polling Best Practices

### Recommended Polling Logic

```python
import time

def poll_until_complete(operation_name, scene_id, max_attempts=60):
    """
    Poll status every 5 seconds for up to 5 minutes.
    """
    for attempt in range(max_attempts):
        response = check_status(operation_name, scene_id)
        status = response["operations"][0]["status"]
        
        if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
            return response  # Success!
        
        elif status == "MEDIA_GENERATION_STATUS_FAILED":
            raise Exception("Generation failed")
        
        elif status in ["MEDIA_GENERATION_STATUS_PENDING", "MEDIA_GENERATION_STATUS_ACTIVE"]:
            time.sleep(5)  # Wait 5 seconds
            continue
        
        else:
            raise Exception(f"Unknown status: {status}")
    
    raise TimeoutError("Generation took too long (>5 minutes)")
```

### Polling Intervals by Workflow

| Workflow | Recommended Interval | Max Wait Time |
|----------|---------------------|---------------|
| T2V | 5 seconds | 3 minutes |
| I2V Single | 5 seconds | 3 minutes |
| I2V Dual | 5 seconds | 4 minutes |
| R2V | 5 seconds | 4 minutes |
| 1080p Upscale | 10 seconds | 5 minutes |
| 4K Upscale | 15 seconds | 10 minutes |

---

## Error Response Structures

### Video Generation Error

```json
{
  "operations": [
    {
      "operation": {
        "name": "operation-id",
        "error": {
          "code": 400,
          "message": "Invalid aspect ratio",
          "details": [...]
        }
      },
      "status": "MEDIA_GENERATION_STATUS_FAILED"
    }
  ]
}
```

### HTTP Error Response

```json
{
  "error": {
    "code": 403,
    "message": "Forbidden",
    "status": "PERMISSION_DENIED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "RECAPTCHA_VALIDATION_FAILED"
      }
    ]
  }
}
```

---

## Common Error Scenarios

### Scenario 1: Token Expired (401)

**Symptoms**: All requests return 401  
**Cause**: Bearer token expired  
**Solution**:
```python
# Extract fresh token from browser
new_token = extract_token_from_browser()
headers = {"Authorization": f"Bearer {new_token}"}
```

### Scenario 2: reCAPTCHA Failed (403)

**Symptoms**: Requests with reCAPTCHA return 403  
**Cause**: Too many requests, invalid token  
**Solution**:
```python
# Add delay between requests
await asyncio.sleep(30 + random.randint(0, 30))

# Or switch to Authorization header mode
```

### Scenario 3: Rate Limited (429)

**Symptoms**: Requests rejected with 429  
**Cause**: Too many concurrent requests  
**Solution**:
```python
# Exponential backoff
def retry_with_backoff(func, max_retries=5):
    for i in range(max_retries):
        try:
            return func()
        except HTTPError as e:
            if e.status_code == 429:
                wait = (2 ** i) + random.random()
                time.sleep(wait)
            else:
                raise
```

### Scenario 4: Invalid Media ID (404)

**Symptoms**: Video generation fails, media not found  
**Cause**: Expired mediaId from image upload  
**Solution**:
```python
# Media IDs expire after ~6 hours
# Re-upload image to get fresh mediaId
fresh_media_id = upload_image(image_path, token)
```

---

## Status Transition Timing

### Expected Durations

| Transition | Typical Time | Max Time |
|------------|--------------|----------|
| Submit → PENDING | Instant | 1s |
| PENDING → ACTIVE | 1-5s | 30s |
| ACTIVE → SUCCESSFUL | 10-60s | 300s |

### Abnormal Durations (Red Flags)

| Situation | Time | Action |
|-----------|------|--------|
| Stuck in PENDING | >30s | Check server status, retry |
| Stuck in ACTIVE | >5 min | Likely failed, check for errors |
| No response | >10s | Network issue, check connection |

---

## Credits & Limits

### Credit Status

Available in response:
```json
{
  "remainingCredits": 43890
}
```

| Remaining Credits | Action |
|-------------------|--------|
| `> 1000` | Normal operation |
| `100-1000` | Monitor usage |
| `< 100` | Plan credit purchase |
| `0` | Cannot generate, purchase needed |

---

## Related Documentation

- [Error Handling Guide](../guides/08_ERROR_HANDLING.md)
- [API Endpoints](./API_ENDPOINTS.md)
- [Authentication Guide](../guides/01_AUTHENTICATION.md)

---

**Last Updated**: 2026-02-01  
**Source**: HAR file analysis + production experience
