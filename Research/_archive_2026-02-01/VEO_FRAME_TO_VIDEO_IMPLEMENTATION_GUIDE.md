# VEO Start-Image (First Frame) Implementation

**Workflow**: Upload image → Generate video  
**Model**: `veo_3_1_i2v_s_fast_ultra_relaxed`

---

## Step 1: Upload Image

**Endpoint**: `POST /v1:uploadUserImage`  
**Requirements**: JPEG format, Base64 encoded, `mimeType: "image/jpeg"`

```python
import base64

def upload_image(image_path, project_id, auth_token):
    with open(image_path, "rb") as img_file:
        jpeg_bytes = convert_to_jpeg_bytes(img_file.read())
        base64_string = base64.b64encode(jpeg_bytes).decode('utf-8')

    payload = {
        "imageInput": {
            "rawImageBytes": base64_string,
            "mimeType": "image/jpeg",
            "isUserUploaded": True,
            "aspectRatio": "IMAGE_ASPECT_RATIO_PORTRAIT"  // or LANDSCAPE
        },
        "clientContext": {"tool": "ASSET_MANAGER"}
    }
    
    response = requests.post(UPLOAD_URL, json=payload, headers={"Authorization": f"Bearer {auth_token}"})
    return response.json()['imageOutput']['mediaGenerationId']
```

---

## Step 2: Generate Video

**Endpoint**: `POST /v1/video:batchAsyncGenerateVideoStartImage`  
**Model**: `veo_3_1_i2v_s_fast_ultra_relaxed`

**Payload**:
```json
{
  "clientContext": {
    "tool": "PINHOLE",
    "projectId": "YOUR_PROJECT_ID",
    "recaptchaContext": {"token": "RECAPTCHA_TOKEN"}
  },
  "requests": [{
    "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
    "videoModelKey": "veo_3_1_i2v_s_fast_ultra_relaxed",
    "textInput": {"prompt": "Your motion prompt"},
    "startImage": {"mediaId": "MEDIA_GENERATION_ID_FROM_STEP_1"},
    "metadata": {"sceneId": "GENERATE_NEW_UUID"}
  }]
}
```

---

## Step 3: Check Status

**Endpoint**: `POST /v1/video:batchCheckAsyncVideoGenerationStatus`

```json
{
  "operations": [{
    "operation": {"name": "operation_name_from_step_2_response"},
    "sceneId": "UUID_from_step_2"
  }]
}
```

---

**Related**: [VEO_DUAL_FRAME_IMPLEMENTATION_GUIDE.md](./VEO_DUAL_FRAME_IMPLEMENTATION_GUIDE.md)
