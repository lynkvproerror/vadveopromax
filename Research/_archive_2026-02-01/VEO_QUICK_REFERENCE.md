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

- 📊 [Full Flow Analysis](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/Documentation/VEO_FLOW_ANALYSIS_REPORT.md) - Detailed technical analysis
- 📘 [Command Reference](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/Documentation/VEO_API_COMMANDS_REFERENCE.md) - Standard execution logic
- 🛠️ [Implementation Guide](file:///D:/Music/Ruby/Produce%20for%20Customer/%23%23Tools/VEO%20Tool/Documentation/VEO_FRAME_TO_VIDEO_IMPLEMENTATION_GUIDE.md) - Step-by-step guide
- 📈 [HAR Coverage Report](file:///C:/Users/Linh/.gemini/antigravity/brain/6cd63aa5-8a11-4269-839f-2ab155dcf9ca/HAR_COVERAGE_REPORT.md) - Analysis coverage

---

**Quick Start:** Copy the Python snippets above → Add your headers → Start generating! 🎥
