# VEO API - Payload Schemas Reference
> **Source:** Extracted from 46 HAR files (`F12 Dev/New`, `F12 Dev/Old`)
> **Last Updated:** 2026-02-02

---

## Common Structure

All modifying requests share this `clientContext` structure:

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "<RECAPTCHA_TOKEN>",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";<TIMESTAMP>",
    "projectId": "<PROJECT_UUID>",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  }
}
```

| Field | Description | Required |
|-------|-------------|----------|
| `recaptchaContext.token` | reCAPTCHA Enterprise token | Generate/Upscale only |
| `sessionId` | Format: `;timestamp_ms` | All requests |
| `projectId` | VEO project UUID | All requests |
| `tool` | Always `"PINHOLE"` | Most requests |
| `userPaygateTier` | User subscription tier | Optional |

---

## 1. Upload Image

**Endpoint:** `POST /v1:uploadUserImage`
**reCAPTCHA:** ❌ NOT REQUIRED

```json
{
  "imageInput": {
    "rawImageBytes": "<BASE64_JPEG>",
    "mimeType": "image/jpeg",
    "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"
  },
  "clientContext": {
    "sessionId": ";<TIMESTAMP>",
    "projectId": "<PROJECT_UUID>",
    "tool": "ASSET_MANAGER"
  }
}
```

**Response:** Returns `mediaId` for use in generation requests.

---

## 2. Text-to-Video (T2V)

**Endpoint:** `POST /v1/video:batchAsyncGenerateVideoText`
**reCAPTCHA:** ✅ REQUIRED

```json
{
  "clientContext": {
    "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
    "sessionId": ";<TIMESTAMP>",
    "projectId": "<PROJECT_UUID>",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
      "seed": 12345,
      "textInput": {
        "prompt": "Your video description here"
      },
      "videoModelKey": "veo_3_1_t2v_fast_landscape_ultra",
      "metadata": {
        "sceneId": "<UUID>"
      }
    }
  ]
}
```

**Model Keys:**
- Landscape: `veo_3_1_t2v_fast_landscape_ultra`
- Portrait: `veo_3_1_t2v_fast_portrait`

---

## 3. Image-to-Video Single Frame (I2V)

**Endpoint:** `POST /v1/video:batchAsyncGenerateVideoStartImage`
**reCAPTCHA:** ✅ REQUIRED

```json
{
  "clientContext": { /* Same as T2V */ },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
      "seed": 15456,
      "textInput": {
        "prompt": "Motion description"
      },
      "videoModelKey": "veo_3_1_i2v_s_fast_ultra_relaxed",
      "startImage": {
        "mediaId": "<UPLOADED_MEDIA_ID>"
      },
      "metadata": {
        "sceneId": "<UUID>"
      }
    }
  ]
}
```

**Model Keys:**
- Landscape: `veo_3_1_i2v_s_fast_ultra_relaxed`
- Portrait: `veo_3_1_i2v_s_fast_portrait_ultra_relaxed`

---

## 4. Frames-to-Video (F2V - Start + End)

**Endpoint:** `POST /v1/video:batchAsyncGenerateVideoStartAndEndImage`
**reCAPTCHA:** ✅ REQUIRED

```json
{
  "clientContext": { /* Same as T2V */ },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
      "seed": 16913,
      "textInput": {
        "prompt": "Transition description"
      },
      "videoModelKey": "veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed",
      "startImage": {
        "mediaId": "<START_IMAGE_MEDIA_ID>"
      },
      "endImage": {
        "mediaId": "<END_IMAGE_MEDIA_ID>"
      },
      "metadata": {
        "sceneId": "<UUID>"
      }
    }
  ]
}
```

**Model Keys:**
- Landscape: `veo_3_1_i2v_s_fast_fl_ultra_relaxed`
- Portrait: `veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed`

---

## 5. Ingredients-to-Video (R2V - 1-3 References)

**Endpoint:** `POST /v1/video:batchAsyncGenerateVideoReferenceImages`
**reCAPTCHA:** ✅ REQUIRED

```json
{
  "clientContext": { /* Same as T2V */ },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
      "seed": 23788,
      "textInput": {
        "prompt": "Combine into video description"
      },
      "videoModelKey": "veo_3_1_r2v_fast_portrait_ultra",
      "referenceImages": [
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "<IMAGE_1_MEDIA_ID>"
        },
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "<IMAGE_2_MEDIA_ID>"
        },
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "<IMAGE_3_MEDIA_ID>"
        }
      ],
      "metadata": {
        "sceneId": "<UUID>"
      }
    }
  ]
}
```

**Model Keys:**
- Landscape: `veo_3_1_r2v_fast_landscape_ultra`
- Portrait: `veo_3_1_r2v_fast_portrait_ultra`

---

## 6. Text-to-Image (T2I)

**Endpoint:** `POST /v1/projects/{PROJECT_ID}/flowMedia:batchGenerateImages`
**reCAPTCHA:** ✅ REQUIRED

```json
{
  "clientContext": {
    "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
    "sessionId": ";<TIMESTAMP>",
    "projectId": "<PROJECT_UUID>",
    "tool": "PINHOLE"
  },
  "requests": [
    {
      "clientContext": { /* Nested - same as parent */ },
      "prompt": "Image description",
      "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
      "seed": 12345,
      "metadata": {
        "sceneId": "<UUID>"
      }
    }
  ]
}
```

---

## 7. Video Upscale

**Endpoint:** `POST /v1/video:batchAsyncGenerateVideoUpsampleVideo`
**reCAPTCHA:** ✅ REQUIRED

```json
{
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
      "resolution": "VIDEO_RESOLUTION_1080P",
      "seed": 18779,
      "videoInput": {
        "mediaId": "<VIDEO_MEDIA_ID>"
      },
      "videoModelKey": "veo_3_1_upsampler_1080p",
      "metadata": {
        "sceneId": "<UUID>"
      }
    }
  ],
  "clientContext": {
    "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
    "sessionId": ";<TIMESTAMP>"
  }
}
```

**Resolution Enums:**
- `VIDEO_RESOLUTION_1080P` → Model: `veo_3_1_upsampler_1080p`
- `VIDEO_RESOLUTION_4K` → Model: `veo_3_1_upsampler_4k`

---

## 8. Image Upscale

**Endpoint:** `POST /v1/flow/upsampleImage`
**reCAPTCHA:** ✅ REQUIRED

```json
{
  "mediaId": "<IMAGE_MEDIA_ID>",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_2K",
  "clientContext": {
    "recaptchaContext": { "token": "...", "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB" },
    "sessionId": ";<TIMESTAMP>",
    "projectId": "<PROJECT_UUID>",
    "tool": "PINHOLE"
  }
}
```

**Resolution Enums:**
- `UPSAMPLE_IMAGE_RESOLUTION_2K`
- `UPSAMPLE_IMAGE_RESOLUTION_4K`

---

## 9. Status Check (Polling)

**Endpoint:** `POST /v1/video:batchCheckAsyncVideoGenerationStatus`
**reCAPTCHA:** ❌ NOT REQUIRED

```json
{
  "operations": [
    {
      "operation": {
        "name": "<OPERATION_ID>"
      },
      "sceneId": "<SCENE_UUID>",
      "status": "MEDIA_GENERATION_STATUS_PENDING"
    }
  ]
}
```

**Response Status Values:**
- `MEDIA_GENERATION_STATUS_PENDING`
- `MEDIA_GENERATION_STATUS_WORKING`
- `MEDIA_GENERATION_STATUS_SUCCESSFUL`
- `MEDIA_GENERATION_STATUS_FAILED`

---

## 10. Download Media

**Endpoint:** `GET /v1/media/{MEDIA_ID}`
**Query Params:** `key={API_KEY}`
**reCAPTCHA:** ❌ NOT REQUIRED

```
GET /v1/media/CAMaJDcxZDVlMGY4...?key=AIza...
```

**Response:** Binary video/image data with `Content-Type: video/mp4` or `image/jpeg`

---

## Aspect Ratio Enums

| Enum | Description |
|------|-------------|
| `VIDEO_ASPECT_RATIO_LANDSCAPE` | 16:9 horizontal |
| `VIDEO_ASPECT_RATIO_PORTRAIT` | 9:16 vertical |
| `IMAGE_ASPECT_RATIO_LANDSCAPE` | Horizontal |
| `IMAGE_ASPECT_RATIO_PORTRAIT` | Vertical |
| `IMAGE_ASPECT_RATIO_SQUARE` | 1:1 |
