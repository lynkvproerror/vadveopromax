# VEO Dual-Frame Video Generation

**Endpoint**: `POST /v1/video:batchAsyncGenerateVideoStartAndEndImage`  
**Model**: `veo_3_1_i2v_s_fast_fl_ultra_relaxed`  
**Batch**: 1-4 videos  
**Processing**: Asynchronous (requires polling)

---

## Comparison with Single-Frame

| Feature | Single-Frame | Dual-Frame |
|---------|--------------|------------|
| **Endpoint** | `batchAsyncGenerateVideoStartImage` | `batchAsyncGenerateVideoStartAndEndImage` |
| **Start Frame** | ✅ Required | ✅ Required |
| **End Frame** | ❌ Not supported | ✅ Required |
| **Model** | `veo_3_1_i2v_s_fast_ultra_relaxed` | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` |

**Generation Logic**:
- Single-frame: `START → [AI generates] → END`
- Dual-frame: `START → [AI interpolates] → END (user-defined)`

---

## Request Payload

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "<recaptcha_v3_token>",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769822770783",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
      "seed": 24060,  // 0-32767
      "textInput": {"prompt": "khởi đầu một cuộc chiến"},
      "videoModelKey": "veo_3_1_i2v_s_fast_fl_ultra_relaxed",
      "startImage": {"mediaId": "CAMaJDYxNTFmMGFjLTc0..."},
      "endImage": {"mediaId": "CAMaJGQ3N2QyZjRmLTU4..."},
      "metadata": {"sceneId": "e40c2aa4-fe9f-4823-97a1-40c78ad75e91"}
    }
  ]
}
```

**Required Parameters**:
- `aspectRatio`: `VIDEO_ASPECT_RATIO_LANDSCAPE` | `PORTRAIT`
- `seed`: Integer (0-32767)
- `textInput.prompt`: Text guidance
- `videoModelKey`: Must be `veo_3_1_i2v_s_fast_fl_ultra_relaxed`
- `startImage.mediaId`: First frame
- `endImage.mediaId`: Last frame

---

## Implementation

```python
import requests

url = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartAndEndImage"
headers = {"Authorization": f"Bearer {token}"}

payload = {
    "clientContext": {...},
    "requests": [{
        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
        "seed": 24060,
        "textInput": {"prompt": "A smooth transition"},
        "videoModelKey": "veo_3_1_i2v_s_fast_fl_ultra_relaxed",
        "startImage": {"mediaId": start_id},
        "endImage": {"mediaId": end_id},
        "metadata": {"sceneId": str(uuid.uuid4())}
    }]
}

response = requests.post(url, headers=headers, json=payload)
workflow_id = response.json()["workflows"][0]["workflowId"]
```

---

## Validation

**Frame Requirements**:
- ✅ Same aspect ratio (both frames)
- ✅ Valid media IDs (not expired)
- ✅ Compatible resolutions

---

**Related**: [VEO_FRAME_TO_VIDEO_IMPLEMENTATION_GUIDE.md](./VEO_FRAME_TO_VIDEO_IMPLEMENTATION_GUIDE.md)
