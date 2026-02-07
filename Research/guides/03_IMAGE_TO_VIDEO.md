# Image-to-Video Generation

Generate videos from images using VEO's Image-to-Video (I2V) models.

**Two modes**:
1. **Single Frame** (Start Image only)
2. **Dual Frame** (Start + End Images)

---

## Single Frame: Start Image Only

**Model**: `veo_3_1_i2v_s_fast_ultra_relaxed`  
**Use case**: Animate from single keyframe, AI generates end naturally

### Workflow

**Step 1: Upload Image**

```
POST /v1:uploadUserImage
```

```python
import base64

def upload_image(image_path, auth_token):
    with open(image_path, "rb") as f:
        jpeg_bytes = convert_to_jpeg(f.read())
        base64_string = base64.b64encode(jpeg_bytes).decode('utf-8')
    
    payload = {
        "imageInput": {
            "rawImageBytes": base64_string,
            "mimeType": "image/jpeg",
            "isUserUploaded": True,
            "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"
        },
        "clientContext": {"tool": "ASSET_MANAGER"}
    }
    
    response = requests.post(UPLOAD_URL, json=payload, headers={"Authorization": f"Bearer {auth_token}"})
    return response.json()['imageOutput']['mediaGenerationId']
```

**Step 2: Generate Video**

```
POST /v1/video:batchAsyncGenerateVideoStartImage
```

```python
media_id = upload_image("start_frame.jpg", token)

payload = {
    "clientContext": {
        "tool": "PINHOLE",
        "projectId": project_id,
        "sessionId": f";{int(time.time() * 1000)}"
    },
    "requests": [{
        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
        "videoModelKey": "veo_3_1_i2v_s_fast_ultra_relaxed",
        "textInput": {"prompt": "Camera slowly zooms in"},
        "startImage": {"mediaId": media_id},
        "seed": random.randint(0, 32767),
        "metadata": {"sceneId": str(uuid.uuid4())}
    }]
}

response = requests.post(I2V_URL, json=payload, headers={"Authorization": f"Bearer {token}"})
```

**Step 3: Poll Status**

Use `/v1/video:batchCheckAsyncVideoGenerationStatus` (same as T2V workflow)

---

## Dual Frame: Start + End Images

**Model**: `veo_3_1_i2v_s_fast_fl_ultra_relaxed` (note `_fl_` = First+Last)  
**Use case**: Precise control over both beginning and ending frames

### Comparison

| Feature | Single-Frame | Dual-Frame |
|---------|--------------|------------|
| **Endpoint** | `batchAsyncGenerateVideoStartImage` | `batchAsyncGenerateVideoStartAndEndImage` |
| **Start Frame** | ✅ Required | ✅ Required |
| **End Frame** | ❌ Not supported | ✅ Required |
| **Model** | `veo_3_1_i2v_s_fast_ultra_relaxed` | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` |

**Generation Logic**:
- Single-frame: `START → [AI generates] → END`
- Dual-frame: `START → [AI interpolates] → END (user-defined)`

### Workflow

**Step 1 & 2: Upload Both Images**

```python
start_id = upload_image("frame_start.jpg", token)
end_id = upload_image("frame_end.jpg", token)
```

**Step 3: Generate Video**

```
POST /v1/video:batchAsyncGenerateVideoStartAndEndImage
```

```python
payload = {
    "clientContext": {
        "recaptchaContext": {
            "token": recaptcha_token,
            "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
        },
        "sessionId": f";{int(time.time() * 1000)}",
        "projectId": project_id,
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_TWO"
    },
    "requests": [{
        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
        "seed": 24060,
        "textInput": {"prompt": "Smooth transition between frames"},
        "videoModelKey": "veo_3_1_i2v_s_fast_fl_ultra_relaxed",
        "startImage": {"mediaId": start_id},
        "endImage": {"mediaId": end_id},
        "metadata": {"sceneId": str(uuid.uuid4())}
    }]
}

response = requests.post(DUAL_FRAME_URL, json=payload, headers={"Authorization": f"Bearer {token}"})
```

**Validation**:
- ✅ Same aspect ratio (both frames)
- ✅ Valid media IDs (not expired)
- ✅ Compatible resolutions

---

## Requirements

**Image Upload**:
- Format: JPEG only
- Encoding: Base64
- Aspect ratio: Calculate from dimensions
  - `width > height`: `IMAGE_ASPECT_RATIO_LANDSCAPE`
  - `height > width`: `IMAGE_ASPECT_RATIO_PORTRAIT`
  - `width == height`: `IMAGE_ASPECT_RATIO_SQUARE`

**Processing Time**:
- Single frame: ~10-15 seconds
- Dual frame: ~12-18 seconds

---

**Related**: 
- [Text-to-Video](./02_TEXT_TO_VIDEO.md)
- [Ingredients-to-Video](./04_INGREDIENTS_TO_VIDEO.md)
- [API Endpoints](../reference/API_ENDPOINTS.md)
