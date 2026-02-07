# VEO Flow Analysis

## Core Generation Modes

| Mode | Icon | Description |
|------|------|-------------|
| **Text to Video** | `text_analysis` | Generate from text prompts |
| **Image to Video** | `photo_spark` | Generate from image + prompt |
| **Ingredients** | (Unknown) | Multi-image generation (R2V) |
| **Create Image** | `image` | Static image generation |

**Mode Switching** (JavaScript):
```javascript
async function selectMode(targetXPath) {
  dropdown.click();
  await sleep(500);
  option.click();
}
```

---

## Video Models

- `Veo 3.1 - Fast` (Default)
- `Veo 3.1 - Fast [Lower Priority]` (Ultra Relaxed)
- `Veo 3.1 - Quality`
- `Veo 2 - Fast`
- `Veo 2 - Quality`

**Aspect Ratios**: Landscape (16:9), Portrait (9:16)  
**Output Count**: 1-4 videos per generation (Concat mode forces 1)

---

## DOM Selectors

| Feature | XPath/Selector |
|---------|----------------|
| **Prompt Input** | `//textarea[@id='PINHOLE_TEXT_AREA_ELEMENT_ID']` |
| **Generate Button** | `//button[.//i[text()='arrow_forward']]` |
| **Image Upload** | `//input[@type="file"]` |
| **Result Item** | `//div[@data-index and @data-item-index]` |
| **Video Element** | `.//video[starts-with(@src, 'http')]` |
| **Error Toast** | `//li[@data-sonner-toast and .//i[text()='error']]` |

---

## Video Upscale Workflow

**Endpoint**: `POST /v1/video:batchAsyncGenerateVideoUpsampleVideo`

**Payload**:
```json
{
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "resolution": "VIDEO_RESOLUTION_1080P",  // or VIDEO_RESOLUTION_4K
    "seed": 29065,
    "videoInput": {"mediaId": "<SOURCE_VIDEO_ID>"},
    "videoModelKey": "veo_3_1_upsampler_1080p",  // or veo_3_1_upsampler_4k
    "metadata": {"sceneId": "<UUID>"}
  }],
  "clientContext": {...},
  "sessionId": "..."
}
```

**Poll**: `POST /v1/video:batchCheckAsyncVideoGenerationStatus`  
**Status**: `PENDING → ACTIVE → SUCCESSFUL`  
**Result URL**: `response.operations[].result.video.url`

---

## Dual-Frame Generation

**Endpoint**: `POST /v1/video:batchAsyncGenerateVideoStartAndEndImage`  
**Model**: `veo_3_1_i2v_s_fast_fl_ultra_relaxed`

**Payload**:
```json
{
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "seed": 24060,
    "textInput": {"prompt": "..."},
    "videoModelKey": "veo_3_1_i2v_s_fast_fl_ultra_relaxed",
    "startImage": {"mediaId": "<START_ID>"},
    "endImage": {"mediaId": "<END_ID>"},
    "metadata": {"sceneId": "<UUID>"}
  }]
}
```

---

## GIF Generation

**Endpoint**: `POST /v1/video:generatePinholeGif`  
**Type**: Synchronous

**Payload**:
```json
{
  "mediaGenerationId": "<VIDEO_ID>",
  "clientContext": {...}
}
```

**Response**: Base64 GIF data

---

## Image Upload

**Endpoint**: `POST /v1:uploadUserImage`

**Payload**:
```json
{
  "imageInput": {
    "rawImageBytes": "<BASE64_JPEG>",
    "mimeType": "image/jpeg",
    "isUserUploaded": true,
    "aspectRatio": "IMAGE_ASPECT_RATIO_PORTRAIT"
  },
  "clientContext": {"tool": "ASSET_MANAGER"}
}
```

**Returns**: `imageOutput.mediaGenerationId`

---

## Status Polling

**Endpoint**: `POST /v1/video:batchCheckAsyncVideoGenerationStatus`

**Payload**:
```json
{
  "operations": [{
    "operation": {"name": "<OPERATION_NAME>"},
    "sceneId": "<SCENE_ID>"
  }]
}
```

**Status Values**:
- `MEDIA_GENERATION_STATUS_PENDING`
- `MEDIA_GENERATION_STATUS_WORKING` (or `ACTIVE`)
- `MEDIA_GENERATION_STATUS_SUCCESSFUL`

---

## Download Workflow

**720p Download**:
```
GET https://storage.googleapis.com/vn-non-prod-{hash}.mp4?GoogleAccessId=...&Expires=...&Signature=...
```

**4K Image Download**:
```
GET https://storage.googleapis.com/ai-sandbox-videofx/image/{id}?GoogleAccessId=...
```

**Required Headers**: Standard browser headers + `x-browser-*` validation

---

## Error Handling

**Error Toast Detection**: `//li[@data-sonner-toast]//i[text()='error']`

**Common Errors**:
- Token expired (401): Refresh authorization
- Credits depleted: Check `remainingCredits` in response
- Invalid mediaId (404): Verify ID format
- Rate limit (429): Exponential backoff

---

## Model Key Reference

| Workflow | Model Key |
|----------|-----------|
| Text-to-Video (Landscape) | `veo_3_1_t2v_fast_landscape_ultra` |
| Text-to-Video (Portrait) | `veo_3_1_t2v_fast_portrait` |
| Image-to-Video (Start only) | `veo_3_1_i2v_s_fast_ultra_relaxed` |
| Image-to-Video (Start+End) | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` |
| Reference-to-Video (R2V) | `veo_3_1_r2v_fast_landscape_ultra` |
| 1080p Upscale | `veo_3_1_upsampler_1080p` |
| 4K Upscale | `veo_3_1_upsampler_4k` |

---

**Last Updated**: 2026-02-01  
**Source**: HAR files + UI automation code analysis
