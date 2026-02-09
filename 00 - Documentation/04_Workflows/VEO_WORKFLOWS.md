# 📘 VEO API Workflows (Technical Specification)
**Version**: 2.0  
**Updated**: 2026-02-02  
**Purpose**: Definitive "Blueprints" for API-based workflows.

> 🛑 **Instruction**: These workflows map directly to methods in `core/api_client.py`.

---

## 🏗️ 0. Shared Architecture

### Data Models
All workflows use `VEOApiClient` and `AuthManager`.

```python
# Core Method Signature
def generate_video_*(self, prompt, model, aspect_ratio, count, ...):
    pass
```

### Global Pre-requisites
1.  **Auth**: Valid `Bearer` token + `Project ID`.
2.  **Fingerprint**: Valid `x-browser-*` headers.
3.  **reCAPTCHA**: Fresh token for generation.

---

## 📝 Workflow 1: Text-to-Video (T2V)

**Method**: `api_client.generate_video_t2v()`  
**Endpoint**: `/video:batchAsyncGenerateVideoText`

1.  **Prepare Payload**:
    - `clientContext.tool = "PINHOLE"`
    - `recaptchaContext` token
2.  **Send Request**:
    ```json
    { "request": { "prompt": "...", "model": "veo_3_1_t2v_..." } }
    ```
3.  **Handle Response**:
    - Extract `operationId` and `sceneId`.
4.  **Poll Status**: Loop `check_status()` until `MEDIA_GENERATION_STATUS_SUCCESSFUL`.

---

## 🖼️ Workflow 2: Image-to-Video (I2V)

**Method**: `api_client.generate_video_i2v_single()`  
**Endpoint**: `/video:batchAsyncGenerateVideoStartImage`

1.  **Upload Image**:
    - Call `upload_image(bytes, ratio)`.
    - Returns `mediaId`.
2.  **Generate**:
    - Payload includes `videoInput.mediaId`.
    - Model: `veo_3_1_i2v_s_*`.
3.  **Poll Status**: Standard polling loop.

---

## 🎞️ Workflow 3: Frames-to-Video (F2V)

**Method**: `api_client.generate_video_i2v_dual()`  
**Endpoint**: `/video:batchAsyncGenerateVideoStartAndEndImage`

1.  **Upload Images**:
    - Upload Start Frame → `startId`.
    - Upload End Frame → `endId`.
2.  **Generate**:
    - Payload: `{ "startImage": {"mediaId": startId}, "endImage": {"mediaId": endId} }`
    - Model: `veo_3_1_i2v_s_fast_fl_*_relaxed`.
3.  **Poll Status**.

---

## 🧪 Workflow 4: Ingredients-to-Video (R2V)

**Method**: `api_client.generate_video_r2v()`  
**Endpoint**: `/video:batchAsyncGenerateVideoReferenceImages`

1.  **Upload References**:
    - Upload 1-3 images (Character, Style, Background).
    - Collect `mediaIds`.
2.  **Generate**:
    - Payload: `{ "referenceImages": [{"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": id1}, ...] }`.
    - Model: `veo_3_1_r2v_*_relaxed`.
3.  **Poll Status**.

---

## 🖼️ Workflow 5: Text-to-Image (T2I)

**Method**: `api_client.generate_image()`  
**Endpoint**: `/flowMedia:batchGenerateImages`

1.  **Generate**:
    - **Synchronous** response (media returned immediately).
    - No polling required.
    - HAR verified: `clientContext` must appear **both** at top-level AND inside each request item.
    - Payload: `{ "clientContext": {...}, "requests": [{"clientContext": {...}, "seed": N, "imageModelName": "GEM_PIX_2", "promptInputs": [{"textInput": "..."}], "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"}] }`.
    - Model: `GEM_PIX_2` (Veo Fast Pro) | `GEM_PIX` (Veo Fast) | `IMAGEN_3_5` (Imagen 3.5).
2.  **Download** images from response.

---

## 📐 Workflow 6: Upscaling (Video & Image)

**Methods**: `upscale_video()`, `upscale_image()`

### Video Upscale
1.  **Prepare**: Input `mediaId`, resolution: `VIDEO_RESOLUTION_1080P` | `VIDEO_RESOLUTION_4K`.
2.  **Send Request**: Returns `operationId`.
3.  **Poll Status**: Uses `check_status`.

### Image Upscale (HAR Verified)
1.  **Prepare**: Input `mediaId` (⚠️ NOT `mediaGenerationId`).
2.  **Send Request**:
    - Payload: `{ "mediaId": "...", "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_4K", "clientContext": {...} }`.
    - Resolution: `UPSAMPLE_IMAGE_RESOLUTION_2K` | `UPSAMPLE_IMAGE_RESOLUTION_4K`.
3.  **Response**: `{ "encodedImage": "base64..." }` — **Sync**, no polling.

---

## 🎞️ Workflow 7: GIF Preview (HAR Verified)

**Method**: `api_client.generate_gif()`  
**Endpoint**: `/v1/video:generatePinholeGif`

1.  **Request**: `{ "mediaGenerationId": "..." }` — ⚠️ **NO clientContext**.
2.  **Response**: `{ "encodedGif": "base64..." }` — Can be >10MB.
3.  **No polling** required (synchronous).

---

## 📥 Download Workflow

**Method**: `api_client.download_media()`

1.  **Direct Download**:
    - GET `/v1/media/{ID}?key={API_KEY}`.
    - Requires `x-browser-*` headers.
    - Save stream to disk.


