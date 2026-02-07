# 🚀 VEO API Quick Reference

**Developer Cheat Sheet** | Last Updated: 2026-01-31

> [!TIP]
> This is your **go-to reference** for rapid development. For detailed analysis, see [VEO_FLOW_ANALYSIS_REPORT.md](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/Documentation/VEO_FLOW_ANALYSIS_REPORT.md)

---

## 📌 Base Configuration

```python
BASE_URL = "https://aisandbox-pa.googleapis.com"
API_KEY = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"

REQUIRED_HEADERS = {
    "x-browser-channel": "stable",
    "x-browser-copyright": "Copyright 2026 Google LLC. All Rights reserved.",
    "x-browser-validation": "<HASH>",  # Extract from HAR
    "x-browser-year": "2026",
    "x-client-data": "<CLIENT_DATA>",  # Extract from HAR
}
```

---

## 🎬 Core API Endpoints

### 1️⃣ Upload Image (First Frame)

```http
POST /v1:uploadUserImage?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "imageInput": {
    "rawImageBytes": "/9j/4AAQSkZJRg...",  // Base64 JPEG
    "mimeType": "image/jpeg",
    "isUserUploaded": true,
    "aspectRatio": "IMAGE_ASPECT_RATIO_PORTRAIT"
  },
  "clientContext": {"tool": "ASSET_MANAGER"}
}
```

**Response:**
```json
{
  "userUploadedImage": {
    "name": "...",
    "mediaGenerationId": "CAM..."  // ⭐ Save this!
  }
}
```

---

### 2️⃣ Generate Video (Image-to-Video)

```http
POST /v1/video:batchAsyncGenerateVideoStartImage?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "requests": [{
    "videoInput": {
      "prompt": "Your prompt here",
      "videoModelKey": "veo_3_1_i2v_s_portrait",
      "startImage": {
        "mediaId": "CAM..."  // From Upload response
      },
      "seed": 12345,
      "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT"
    },
    "sceneId": "UUID"
  }]
}
```

**Response:**
```json
{
  "videoGenerationResults": [{
    "operation": {
      "name": "operations/..."  // ⭐ For status check
    }
  }]
}
```

---

### 2️⃣A Generate Video (Start + End Image)

```http
POST /v1/video:batchAsyncGenerateVideoStartAndEndImage?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "seed": 24060,
    "textInput": { "prompt": "Your prompt here" },
    "videoModelKey": "veo_3_1_i2v_s_fast_fl_ultra_relaxed",
    "startImage": {
      "mediaId": "CAM..."  // From Upload response (First Frame)
    },
    "endImage": {
      "mediaId": "CAM..."  // From Upload response (Last Frame)
    },
    "metadata": {
      "sceneId": "UUID"
    }
  }]
}
```

> [!NOTE]
> Both start and end images must be uploaded separately using the Upload Image endpoint.

---

### 2️⃣B Generate Video (Reference Images / Ingredients - R2V)

```http
POST /v1/video:batchAsyncGenerateVideoReferenceImages?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "seed": 12345,
    "textInput": { "prompt": "A hero [char_hero] walks through [bg_castle]" },
    "videoModelKey": "veo_3_1_i2v_s_fast_ultra_relaxed",
    "referenceImages": [
      { "mediaId": "CAM...", "tag": "char_hero" },
      { "mediaId": "CAM...", "tag": "bg_castle" }
    ],
    "metadata": { "sceneId": "UUID" }
  }]
}
```

> [!NOTE]
> Upload each reference image first using Upload Image endpoint. Tags in prompt must match `tag` field.

---

### 2️⃣C Generate Video (Text-to-Video - T2V)

```http
POST /v1/video:batchAsyncGenerateVideoText?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "seed": 12345,
    "textInput": { "prompt": "A beautiful sunset over mountains" },
    "videoModelKey": "veo_3_1_t2v_fast",
    "metadata": { "sceneId": "UUID" }
  }]
}
```

**Response:** Same as I2V - returns `operationName` for status polling.

---

### 3️⃣ Check Status (Polling)

```http
POST /v1/video:batchCheckAsyncVideoGenerationStatus?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "requests": [{
    "operationName": "operations/..."
  }]
}
```

**Response (Success):**
```json
{
  "results": [{
    "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
    "video": {
      "url": "https://storage.googleapis.com/..."  // ⭐ Download URL
    }
  }]
}
```

---

### 4️⃣ Generate GIF Preview

```http
POST /v1/video:generatePinholeGif?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "mediaGenerationId": "CAM..."
}
```

**Response:**
```json
{
  "pinholeGif": "R0lGODlh..."  // Base64 GIF (>10MB)
}
```

---

### 5️⃣ Download Video (720p)

```http
GET https://storage.googleapis.com/ai-sandbox-videofx/video/{UUID}?GoogleAccessId=...&Signature=...
```

**Critical Headers:**
```http
x-browser-channel: stable
x-browser-copyright: Copyright 2026 Google LLC. All Rights reserved.
x-browser-validation: <HASH>
x-browser-year: 2026
x-client-data: <CLIENT_DATA>
```

> [!WARNING]
> Video download **will fail with 403** if headers are missing!

---

### 5️⃣A Upscale Video (1080p / 4K)

```http
POST /v1/video:batchAsyncGenerateVideoUpsampleVideo?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "requests": [{
    "mediaGenerationId": "CAU...",
    "videoResolution": "VIDEO_RESOLUTION_1080P",
    "metadata": { "sceneId": "UUID" }
  }]
}
```

**Resolution Options:**
| Quality | Value |
|---------|-------|
| 1080p | `VIDEO_RESOLUTION_1080P` |
| 4K | `VIDEO_RESOLUTION_4K` |

**Response:** Returns `operationName` for status polling. When complete, returns upscaled video URL.

---

### 5️⃣B Upscale Image (2K / 4K)

```http
POST /v1/flow/upsampleImage?key={API_KEY}&clientContext.tool=PINHOLE
Content-Type: application/json
```

**Payload:**
```json
{
  "mediaGenerationId": "CAM...",
  "targetResolution": "IMAGE_RESOLUTION_4K"
}
```

---

### 6️⃣ Check Account Credits

```http
GET /v1/credits?key={API_KEY}&clientContext.tool=PINHOLE
```

**Response:**
```json
{
  "credits": {
    "available": 100,
    "used": 50
  },
  "subscription": {
    "tier": "WS_ULTRA"
  }
}
```

**Subscription Tiers:**
| Tier | Code |
|------|------|
| Ultra | `WS_ULTRA` |
| Pro | `WS_PRO` |
| Free | `WS_FREEMIUM` |

---

## 🔄 Typical Workflow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant S as Storage

    C->>A: 1. Upload Image
    A-->>C: mediaGenerationId
    
    C->>A: 2. Generate Video
    A-->>C: operationName
    
    loop Every 20s
        C->>A: 3. Check Status
        A-->>C: WORKING/SUCCESSFUL
    end
    
    C->>S: 4. Download Video (Signed URL)
    S-->>C: MP4 file
    
    Note over C,A: Optional: Generate GIF
    C->>A: 5. Generate GIF
    A-->>C: Base64 GIF
```

---

## 🎨 Model Keys Reference

| Use Case | Model Key | Aspect Ratio |
|----------|-----------|--------------|
| **Text → Video (Portrait)** | `veo_3_1_t2v_fast_portrait` | `VIDEO_ASPECT_RATIO_PORTRAIT` |
| **Text → Video (Portrait/Relaxed)** | `veo_3_1_t2v_fast_portrait_ultra_relaxed` | `VIDEO_ASPECT_RATIO_PORTRAIT` |
| **Text → Video (Landscape)** | `veo_3_1_t2v_fast` | `VIDEO_ASPECT_RATIO_LANDSCAPE` |
| **Image → Video (Portrait)** | `veo_3_1_i2v_s_portrait` | `VIDEO_ASPECT_RATIO_PORTRAIT` |
| **Image → Video (Landscape)** | `veo_3_1_i2v_s_fast_ultra_relaxed` | `VIDEO_ASPECT_RATIO_LANDSCAPE` |
| **Start+End → Video** | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | Both |
| **1080p Upscale** | `veo_3_1_upsampler_1080p` | Original |
| **4K Upscale** | `veo_3_1_upsampler_4k` | Original |

---

## 🐍 Python Implementation Snippets

### Image Upload Helper

```python
import base64
from PIL import Image
from io import BytesIO

def prepare_image_upload(image_path):
    img = Image.open(image_path).convert('RGB')
    
    # Calculate aspect ratio
    w, h = img.size
    if w > h:
        ratio = "IMAGE_ASPECT_RATIO_LANDSCAPE"
    elif h > w:
        ratio = "IMAGE_ASPECT_RATIO_PORTRAIT"
    else:
        ratio = "IMAGE_ASPECT_RATIO_SQUARE"
    
    # Convert to JPEG Base64
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=95)
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    return {
        "imageInput": {
            "rawImageBytes": b64,
            "mimeType": "image/jpeg",
            "isUserUploaded": True,
            "aspectRatio": ratio
        },
        "clientContext": {"tool": "ASSET_MANAGER"}
    }
```

### Status Polling Loop

```python
import time

def wait_for_completion(operation_name, max_wait=300):
    """Poll status every 20s for max_wait seconds"""
    elapsed = 0
    while elapsed < max_wait:
        response = check_status(operation_name)
        status = response['results'][0]['status']
        
        if status == 'MEDIA_GENERATION_STATUS_SUCCESSFUL':
            return response['results'][0]['video']['url']
        elif status == 'MEDIA_GENERATION_STATUS_FAILED':
            raise Exception("Generation failed")
        
        time.sleep(20)
        elapsed += 20
    
    raise TimeoutError("Max wait time exceeded")
```

---

## 📋 Common Gotchas

| Issue | Solution |
|-------|----------|
| **403 on Video Download** | Add all `x-browser-*` headers |
| **Upload fails** | Ensure image is JPEG format (not WebP/PNG) |
| **Invalid mediaId** | Use `mediaGenerationId` from upload response |
| **GIF timeout** | It's synchronous - wait for full response (can be >30s) |
| **Status always WORKING** | Wait at least 20s between polls |
---

## 🔗 Related Documents

- 📊 [VEO Production Workflows](./04_Workflows/VEO_PRODUCTION_WORKFLOWS.md) - Detailed technical analysis
- 📘 [API Mapping](./02_Architecture/API_MAPPING.md) - Standard execution logic
- 🛠️ [Image-to-Video Workflow](./04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md) - Step-by-step guide
- 📈 [Architecture Overview](./00_PROJECT/ARCHITECTURE_OVERVIEW.md) - System diagram

---

**Quick Start:** Copy the Python snippets above → Add your headers → Start generating! 🎥
