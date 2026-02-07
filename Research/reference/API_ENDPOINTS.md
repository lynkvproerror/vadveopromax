# 🔗 VEO API Endpoints & Workflows

**Source**: Reverse Engineering of `VEO Automation (2.1.4.0)` Chrome Extension & Playwright Scripts.
**Status**: ACTIVE
**Last Updated**: 2026-02-02

---

## 🎯 Execution Flow

**Summary**: The VEO API uses a mix of synchronous and asynchronous calls. Video generation is async (polling required), while image generation and upscaling operations can be synchronous or async depending on the endpoint variant found (e.g., `batchGenerateImages` returns media immediately in some HARs, but large tasks might poll). **Current analysis shows Image Gen is synchronous.**

```mermaid
graph TD
    A[Start] --> B{Task Type?}
    
    subgraph "Video Workflows"
        %% 1. Text-to-Video (T2V)
        B -->|1. Text-to-Video| T2V1[Prepare Headers<br/>x-browser-*]
        T2V1 --> T2V2[Get reCAPTCHA Token]
        T2V2 --> T2V3[CMD_GENERATE_VIDEO<br/>model: veo_3_1_t2v_*<br/>+ Auth + reCAPTCHA + Headers]
        T2V3 --> POLL
        
        %% 2. Image-to-Video Single Frame (I2V)
        B -->|2. Image-to-Video<br/>Single Frame| I2V1[CMD_UPLOAD_IMAGE<br/>+ Headers Only]
        I2V1 --> I2V2[Get reCAPTCHA Token]
        I2V2 --> I2V3[CMD_GENERATE_VIDEO<br/>model: veo_3_1_i2v_s_*<br/>+ imageInputMediaId]
        I2V3 --> POLL
        
        %% 3. Frames-to-Video (Start + End Image)
        B -->|3. Frames-to-Video<br/>Start + End| F2V1[CMD_UPLOAD_IMAGE x2<br/>+ Headers Only]
        F2V1 --> F2V2[Get reCAPTCHA Token]
        F2V2 --> F2V3[CMD_GENERATE_VIDEO_START_END<br/>model: veo_3_1_i2v_s_fast_fl_*<br/>+ startImageId + endImageId]
        F2V3 --> POLL
        
        %% 4. Ingredients-to-Video (R2V)
        B -->|4. Ingredients<br/>1-3 Reference Images| R2V1[CMD_UPLOAD_IMAGE x1-3<br/>+ Headers Only]
        R2V1 --> R2V2[Get reCAPTCHA Token]
        R2V2 --> R2V3[CMD_GENERATE_VIDEO<br/>model: veo_3_1_r2v_*<br/>+ referenceImageIds array]
        R2V3 --> POLL
    end
    
    subgraph "Image Workflows"
        %% 5. Text-to-Image (T2I)
        B -->|5. Text-to-Image| T2I1[Prepare Headers]
        T2I1 --> T2I2[Get reCAPTCHA Token]
        T2I2 --> T2I3[CMD_GENERATE_IMAGE<br/>batchGenerateImages<br/>+ prompt<br/>+ reCAPTCHA + Headers]
        T2I3 --> IMG_READY[Base Image Ready]
        
        %% 6. Image-to-Image (I2I)
        B -->|6. Image-to-Image<br/>(Style/Variation)| I2I1[CMD_UPLOAD_IMAGE<br/>Source Image<br/>+ Headers Only]
        I2I1 --> I2I2[Get reCAPTCHA Token]
        I2I2 --> I2I3[CMD_GENERATE_IMAGE<br/>batchGenerateImages<br/>+ prompt + imageInputs<br/>+ reCAPTCHA + Headers]
        I2I3 --> IMG_READY
    end

    subgraph "Video Post-Processing"
        POLL[Poll Status<br/>CMD_CHECK_STATUS<br/>+ Headers Only, NO reCAPTCHA]
        POLL --> DONE{Success?}
        DONE -->|No| POLL
        DONE -->|Yes| VIDEO_READY[Base Video Ready]
        
        VIDEO_READY --> VID_UPSCALE{Want<br/>Upscale?}
        VID_UPSCALE -->|Yes 1080p/4K| VUP1[Get reCAPTCHA Token]
        VUP1 --> VUP2[CMD_UPSCALE_VIDEO<br/>+ resolution enum<br/>+ reCAPTCHA + Headers]
        VUP2 --> VUP_POLL[Poll Upscale Status]
        VUP_POLL --> VUP_CHECK{Success?}
        VUP_CHECK -->|No| VUP_POLL
        VUP_CHECK -->|Yes| VIDEO_UPSCALED[Upscaled Video]
        VID_UPSCALE -->|No| VID_DL
    end

    subgraph "Image Post-Processing"
        IMG_READY --> IMG_UPSCALE{Want<br/>Upscale?}
        IMG_UPSCALE -->|Yes 2K/4K| IUP1[Get reCAPTCHA Token]
        IUP1 --> IUP2[CMD_UPSCALE_IMAGE<br/>upsampleImage<br/>+ resolution enum<br/>+ reCAPTCHA + Headers]
        IUP2 --> IUP_POLL[Poll Upscale Status]
        IUP_POLL --> IUP_CHECK{Success?}
        IUP_CHECK -->|No| IUP_POLL
        IUP_CHECK -->|Yes| IMG_UPSCALED[Upscaled Image]
        IMG_UPSCALE -->|No| IMG_DL
    end

    subgraph "Download"
        VIDEO_UPSCALED --> VID_DL[CMD_DOWNLOAD_VIDEO<br/>GET /v1/media/ID<br/>+ API Key + Headers]
        VID_DL --> END[End]
        
        IMG_UPSCALED --> IMG_DL[CMD_DOWNLOAD_IMAGE<br/>Direct URL]
        IMG_DL --> END
    end
```

---

## 📡 API Commands Dictionary

### 1. `CMD_GENERATE_VIDEO` (T2V / I2V)
**Purpose**: Start asynchronous video generation.
**Endpoint**: `POST /v1/projects/{projectId}/flowMedia:batchAsyncGenerateVideoText` (and variants for I2V/R2V)
**Auth**: `Authorization: Bearer <token>` + `x-browser-*` headers.
**reCAPTCHA**: **REQUIRED**. Included in payload `clientContext.recaptchaContext.token`.
**Payload**:
```json
{
  "clientContext": {
    "recaptchaContext": { "token": "..." },
    "tool": "PINHOLE",
    ...
  },
  "requests": [
    {
      "videoModelKey": "veo_3_1_...",
      "textInput": { "prompt": "..." },
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE"
    }
  ]
}
```

### 2. `CMD_UPLOAD_IMAGE`
**Purpose**: Upload image for I2V, R2V, or I2I.
**Endpoint**: `POST /v1:uploadUserImage`
**Auth**: `Authorization: Bearer <token>` + `x-browser-*` headers.
**reCAPTCHA**: **NO**. Not observed in HAR payloads.
**Payload**: Raw bytes (image data), usually octet-stream or multipart with boundary.
**Returns**: `{"imageOutput": {"mediaGenerationId": "..."}}`

### 3. `CMD_GENERATE_IMAGE` (T2I / I2I)
**Purpose**: Generate images from text or text+image.
**Endpoint**: `POST /v1/projects/{projectId}/flowMedia:batchGenerateImages`
**Auth**: `Authorization: Bearer <token>` + `x-browser-*` headers.
**reCAPTCHA**: **REQUIRED**. Included in payload `clientContext.recaptchaContext.token`.
**Payload (T2I)**:
```json
{
  "clientContext": { ...recaptcha... },
  "requests": [{
    "imageModelName": "IMAGEN_3_5",
    "prompt": "...",
    "imageInputs": []
  }]
}
```
**Payload (I2I)**: Same as T2I but `imageInputs` array contains media IDs from `CMD_UPLOAD_IMAGE`.

### 4. `CMD_UPSCALE_IMAGE`
**Purpose**: Post-processing upscale for images (2K/4K).
**Endpoint**: `POST /v1/flow/upsampleImage`
**Auth**: `Authorization: Bearer <token>` + `x-browser-*` headers.
**reCAPTCHA**: **REQUIRED**. Included in payload `clientContext.recaptchaContext.token`.
**Payload**:
```json
{
  "mediaId": "...",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_4K",
  "clientContext": {
    "recaptchaContext": { "token": "..." },
    "tool": "PINHOLE",
    ...
  }
}
```

### 5. `CMD_CHECK_STATUS` (Poll)
**Purpose**: Check status of async generations (Video).
**Endpoint**: `POST /v1/projects/{projectId}/flowMedia:batchCheckAsyncVideoGenerationStatus`
**Auth**: `Authorization: Bearer <token>` + `x-browser-*` headers.
**reCAPTCHA**: **NO**.
**Payload**:
```json
{
  "operationNames": ["projects/.../operations/..."]
}
```

---

## 🔐 Header & Auth Requirements Matrix

| Workflow Step | Endpoint | Auth Header | x-browser-* Headers | reCAPTCHA Token |
| :--- | :--- | :---: | :---: | :---: |
| **Upload Image** | `/v1:uploadUserImage` | ✅ | ✅ | ❌ |
| **Gen Video (All)** | `...:batchAsyncGenerateVideo...` | ✅ | ✅ | ✅ |
| **Gen Image (T2I/I2I)**| `...:batchGenerateImages` | ✅ | ✅ | ✅ |
| **Upscale Image** | `/v1/flow/upsampleImage` | ✅ | ✅ | ✅ |
| **Upscale Video** | `...:batchAsyncGenerateVideoUpsampleVideo` | ✅ | ✅ | ✅ |
| **Poll Status** | `...:batchCheckAsync...` | ✅ | ✅ | ❌ |
| **Download** | `/v1/media/{id}` | ✅ | ✅ | ❌ |

**Note**: `x-browser-validation`, `x-browser-channel`, `x-browser-year`, `x-browser-copyright` are mandatory for all `POST` requests to `aisandbox-pa.googleapis.com`.
