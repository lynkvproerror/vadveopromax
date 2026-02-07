# NEW DATA FINDINGS REPORT
> **Source:** `F12 Dev/New/` (7 verified HAR files)
> **Status:** Pending User Confirmation

---

## 1. NEW ENUMS DETECTED
These values appear in recent production traffic but are **missing from current documentation**.

| Enum | Context | Found In |
|------|---------|----------|
| `VIDEO_RESOLUTION_4K` | Upscaling payload | `Upscale all done.har` |
| `VIDEO_RESOLUTION_1080P` | Upscaling payload | `Upscale 1080 done.har` |
| `VIDEO_ASPECT_RATIO_PORTRAIT` | Video Gen Payload | `916 frame to video...` |

## 2. UPSCALING PAYLOAD STRUCTURE
**Endpoint:** `/v1/video:batchAsyncGenerateVideoUpsampleVideo`
**Method:** `POST`

**Current Payload Pattern**:
```json
{
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
      "resolution": "VIDEO_RESOLUTION_4K",  <-- NEW FIELD
      "seed": 15175,
      "videoInput": {
        "mediaId": "CAUSJDRm..."
      }
    }
  ]
}
```

## 3. MEDIA DOWNLOAD ENDPOINTS
**Observed Pattern:**
`GET https://aisandbox-pa.googleapis.com/v1/media/{MEDIA_ID}?key={API_KEY}&clientContext.tool=PINHOLE`

- **Purpose:** Direct media access/download
- **Auth:** Uses `key` query param (API Key) rather than just Bearer token? Or mixed?
- **Note:** Current `API_ENDPOINTS.md` mentions "Direct signed URL" but doesn't specify this standard endpoint format.

---

## 4. VERIFIED SECURITY PROTOCOL MATRIX
Based on deep audit of 46 HAR files, strict adherence to these requirements is mandatory to avoid **403 Forbidden**.

### 4.1. Requirements by Endpoint

| Endpoint Type | Enpoint URL | `x-browser-*` | `recaptchaContext` | `apiKey` | `clientContext.tool` |
|---|---|---|---|---|---|
| **Video Gen (T2V/I2V)** | `/video:batchAsyncGenerateVideo...` | ✅ **REQUIRED** | ✅ **REQUIRED** | ❌ | ✅ **REQUIRED** ("PINHOLE") |
| **Video Upscale** | `/video:batchAsyncGenerateVideoUpsampleVideo` | ✅ **REQUIRED** | ✅ **REQUIRED** | ❌ | ❌ |
| **Image Gen** | `/flowMedia:batchGenerateImages` | ✅ **REQUIRED** | ✅ **REQUIRED** | ❌ | ✅ **REQUIRED** |
| **Image Upscale** | `/v1/flow/upsampleImage` | ✅ **REQUIRED** | ✅ **REQUIRED** | ❌ | ✅ **REQUIRED** |
| **Status Check** | `/video:batchCheckAsyncVideoGenerationStatus` | ✅ **REQUIRED** | ❌ | ❌ | ❌ |
| **Upload Image** | `/v1:uploadUserImage` | ✅ **REQUIRED** | ❌ | ❌ | ❌ |
| **Download Media** | `/v1/media/{ID}` | ✅ **REQUIRED** | ❌ | ✅ **REQUIRED** | ❌ (Query Param Only) |

### 4.2. Header Definitions
All endpoints marked with `x-browser-*` MUST include:
```http
x-browser-channel: stable
x-browser-validation: [High-Entropy-String]
x-browser-copyright: [Copyright-String]
x-browser-year: [Year]
x-client-data: [Base64-String]
```

### 4.3. Authentication State
*   **Bearer Token / Cookies**: STRIPPED in HARs. User must provide `ya29...` token or we must implement browser-based harvesting.
*   **API Key**: Found in query params for Media Download only.

## 5. RECAPTCHA CONTEXT
*   **Origin:** Client-side via `Google reCAPTCHA Enterprise`.
*   **Usage:** Validates "Human Intent" for expensive compute tasks (Gen/Upscale).
*   **Critial:** Status Check and Upload do NOT require it.

## 7. RECOMMENDATIONS
