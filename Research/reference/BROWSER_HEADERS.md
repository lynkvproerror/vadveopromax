# VEO API - Browser Headers Specification
> **Source:** Extracted from HAR files
> **Last Updated:** 2026-02-02

---

## Overview

All VEO API requests must include specific browser-fingerprint headers to avoid `403 Forbidden` errors. These headers verify "Device Integrity" as part of the multi-layered security model.

---

## Required Headers

| Header | Static/Dynamic | Example Value |
|--------|----------------|---------------|
| `x-browser-channel` | Static | `stable` |
| `x-browser-copyright` | Static | `Copyright 2026 Google LLC. All Rights reserved.` |
| `x-browser-year` | Static | `2026` |
| `x-browser-validation` | Dynamic | `WVxyJFF0uIgXSTejJocZmmZTO+I=` |
| `x-client-data` | Dynamic | `CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE=` |

---

## Header Details

### 1. `x-browser-channel`
- **Type:** Static
- **Value:** `stable`
- **Purpose:** Identifies Chrome release channel
- **Implementation:** Hardcode in all requests

### 2. `x-browser-copyright`
- **Type:** Static
- **Value:** `Copyright 2026 Google LLC. All Rights reserved.`
- **Purpose:** Legal/fingerprint marker
- **Implementation:** Hardcode in all requests

### 3. `x-browser-year`
- **Type:** Static
- **Value:** `2026`
- **Purpose:** Year marker for version tracking
- **Implementation:** Hardcode (or dynamic based on current year)

### 4. `x-browser-validation` ⚠️ CRITICAL
- **Type:** Dynamic
- **Sample Values:**
  - `WVxyJFF0uIgXSTejJocZmmZTO+I=`
  - `m1p/flp8o0rsqq649T7rsY5vgtE=`
- **Purpose:** Anti-bot verification token
- **Implementation:** 
  - Option A: Extract from browser session (HAR or Playwright)
  - Option B: Replay captured value (may expire)
- **Note:** This is the most critical header for avoiding 403

### 5. `x-client-data`
- **Type:** Dynamic
- **Sample Values:**
  - `CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE=`
  - `CI+2yQEIo7bJAQipncoBCM7aygEIkqHLAQiFoM0BCNmqzwE=`
- **Purpose:** Chrome Variations identifier (A/B test groups)
- **Implementation:** Extract from browser session

---

## Endpoint Header Requirements

| Endpoint | x-browser-* | Notes |
|----------|-------------|-------|
| `POST /v1:uploadUserImage` | ✅ Required | All headers |
| `POST /video:batchAsyncGenerateVideo*` | ✅ Required | All headers |
| `POST /video:batchCheckAsync*` | ✅ Required | All headers |
| `POST /video:batchAsyncGenerateVideoUpsampleVideo` | ✅ Required | All headers |
| `POST /v1/flow/upsampleImage` | ✅ Required | All headers |
| `GET /v1/media/{ID}` | ✅ Required | All headers |

---

## Implementation Code

```python
# browser_headers.py

class BrowserHeaders:
    """Static and dynamic browser headers for VEO API"""
    
    # Static headers (hardcoded)
    STATIC = {
        "x-browser-channel": "stable",
        "x-browser-copyright": "Copyright 2026 Google LLC. All Rights reserved.",
        "x-browser-year": "2026"
    }
    
    def __init__(self):
        self._validation = None
        self._client_data = None
    
    def set_dynamic_headers(self, validation: str, client_data: str):
        """Set dynamic headers from HAR extraction or Playwright capture"""
        self._validation = validation
        self._client_data = client_data
    
    def get_all_headers(self) -> dict:
        """Return complete headers dict for API requests"""
        headers = self.STATIC.copy()
        if self._validation:
            headers["x-browser-validation"] = self._validation
        if self._client_data:
            headers["x-client-data"] = self._client_data
        return headers
    
    def extract_from_har(self, har_path: str) -> bool:
        """Extract dynamic headers from HAR file"""
        import json
        try:
            with open(har_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for entry in data.get('log', {}).get('entries', []):
                req = entry.get('request', {})
                if 'googleapis.com' not in req.get('url', ''):
                    continue
                
                for h in req.get('headers', []):
                    name = h['name'].lower()
                    if name == 'x-browser-validation':
                        self._validation = h['value']
                    elif name == 'x-client-data':
                        self._client_data = h['value']
                
                if self._validation and self._client_data:
                    return True
            
            return False
        except:
            return False
```

---

## Fallback Strategy

If dynamic headers cannot be extracted:

1. **Try HAR extraction** → Most reliable
2. **Try Playwright capture** → Real-time but requires browser
3. **Use cached values** → May work temporarily
4. **Prompt user for manual input** → Last resort

---

## Known Values (for Testing)

```python
# Sample values from HAR files
TEST_HEADERS = {
    "x-browser-channel": "stable",
    "x-browser-copyright": "Copyright 2026 Google LLC. All Rights reserved.",
    "x-browser-year": "2026",
    "x-browser-validation": "WVxyJFF0uIgXSTejJocZmmZTO+I=",
    "x-client-data": "CI+2yQEIo7bJAQipncoBCM7aygEIlqHLAQiFoM0BCNmqzwE="
}
```
