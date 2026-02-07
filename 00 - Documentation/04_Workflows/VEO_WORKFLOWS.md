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
    - Payload: `{ "startImageId": startId, "endImageId": endId }`.
    - Model: `veo_3_1_i2v_s_fast_fl_*`.
3.  **Poll Status**.

---

## 🧪 Workflow 4: Ingredients-to-Video (R2V)

**Method**: `api_client.generate_video_r2v()`  
**Endpoint**: `/video:batchAsyncGenerateVideoReferenceImages`

1.  **Upload References**:
    - Upload 1-3 images (Character, Style, Background).
    - Collect `mediaIds`.
2.  **Generate**:
    - Payload: `{ "referenceImageIds": [id1, id2, ...] }`.
    - Model: `veo_3_1_r2v_*`.
3.  **Poll Status**.

---

## 🖼️ Workflow 5: Text-to-Image (T2I)

**Method**: `api_client.generate_image()`  
**Endpoint**: `/flowMedia:batchGenerateImages`

1.  **Generate**:
    - **Synchronous** response (URLs returned immediately).
    - No polling required.

---

## 📐 Workflow 6: Upscaling (Video & Image)

**Methods**: `upscale_video()`, `upscale_image()`

1.  **Prepare**:
    - Input `mediaId` (from generation).
    - Resolution: `VIDEO_RESOLUTION_1080P` or `VIDEO_RESOLUTION_4K`.
2.  **Send Request**:
    - Returns `operationId` (Video) or `jobId` (Image).
3.  **Poll Status**:
    - Video: Uses `check_status`.
    - Image: Uses separate status endpoint (or same, depends on implementation).

---

## 📥 Download Workflow

**Method**: `api_client.download_media()`

1.  **Direct Download**:
    - GET `/v1/media/{ID}?key={API_KEY}`.
    - Requires `x-browser-*` headers.
    - Save stream to disk.


