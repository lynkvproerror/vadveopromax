# VEO Video Upscaling Guide

Upscale generated videos to 1080p or 4K resolution using dedicated VEO upsampler models.

---

## ⚡ Quick Scan

| Feature | Details |
|---------|---------|
| **Endpoint** | `POST .../video:batchAsyncGenerateVideoUpsampleVideo` |
| **Method** | Asynchronous (requires polling) |
| **Levels** | 1080p, 4K |
| **Source** | Generated videos (from T2V, I2V, R2V) |
| **Models** | `veo_3_1_upsampler_1080p`, `veo_3_1_upsampler_4k` |

---

## 🛠️ Step-by-Step Implementation

### Step 1: Select Upscale Model

| Model Key | Input Resolution | Output | Processing Time |
|-----------|------------------|--------|-----------------|
| `veo_3_1_upsampler_1080p` | 720p | 1080p | ~30 seconds |
| `veo_3_1_upsampler_4k` | 720p/1080p | 4K | ~60 seconds |

### Step 2: Request Upscale

Use the `batchAsyncGenerateVideoUpsampleVideo` endpoint. Note that you provide the `video` (Base64 or FifeURL) or `mediaGenerationId` depending on provider capability. For VEO 3.1, usually source ID is used.

**Endpoint**:
```
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoUpsampleVideo
```

**Payload**:
```json
{
  "clientContext": {
    "sessionId": ";1769880165773",
    "projectId": "YOUR_PROJECT_ID",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [
    {
      "videoUpsampleInput": {
        "videoModelKey": "veo_3_1_upsampler_4k",
        "videoInput": {
          "userVideo": {
            "fifeUrl": "https://storage.googleapis.com/..."  // URL of video to upscale
          }
        }
      },
      "metadata": {
        "sceneId": "UNIQUE_UUID"
      }
    }
  ]
}
```

### Step 3: Poll for Completion

Poling logic is identical to video generation.

```python
STATUS_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus"

# Poll until MEDIA_GENERATION_STATUS_SUCCESSFUL
```

See [Text-to-Video Guide](./02_TEXT_TO_VIDEO.md) for detailed polling code.

---

## 💻 Python Example

```python
import requests
import time
import uuid

UPSCALE_ENDPOINT = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoUpsampleVideo"
STATUS_ENDPOINT = "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus"

def upscale_video(video_url, project_id, auth_token, target_4k=True):
    model = "veo_3_1_upsampler_4k" if target_4k else "veo_3_1_upsampler_1080p"
    scene_id = str(uuid.uuid4())
    
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # 1. Start Upscale
    payload = {
        "clientContext": {
            "projectId": project_id,
            "tool": "PINHOLE",
            "userPaygateTier": "PAYGATE_TIER_TWO"  # Upscaling often requires Tier 2+
        },
        "requests": [{
            "videoUpsampleInput": {
                "videoModelKey": model,
                "videoInput": {
                    "userVideo": {"fifeUrl": video_url}
                }
            },
            "metadata": {"sceneId": scene_id}
        }]
    }
    
    print(f"🚀 Starting {model} upscale for {video_url[:30]}...")
    resp = requests.post(UPSCALE_ENDPOINT, json=payload, headers=headers)
    
    if resp.status_code != 200:
        raise Exception(f"Upscale Request Failed: {resp.text}")
        
    data = resp.json()
    operation_name = data["operations"][0]["operation"]["name"]
    
    # 2. Poll Status
    while True:
        time.sleep(5)
        status_resp = requests.post(STATUS_ENDPOINT, json={
            "operations": [{"operation": {"name": operation_name}, "sceneId": scene_id}]
        }, headers=headers)
        
        status_data = status_resp.json()
        status = status_data["operations"][0]["status"]
        print(f"Status: {status}")
        
        if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
            return status_data["operations"][0]["operation"]["metadata"]["video"]["fifeUrl"]
        elif status == "MEDIA_GENERATION_STATUS_FAILED":
            raise Exception("Upscale Failed")
    
# Usage
# upscaled_url = upscale_video(original_url, PROJECT_ID, TOKEN, target_4k=True)
```

---

## ⚠️ Limitations & Best Practices

1. **Input Quality**: Garbage in, garbage out. Upscaling works best on clean 720p inputs.
2. **Timeouts**: 4K upscaling can take >60s. Adjust your timeout logic.
3. **Artifacts**: AI upscaling can sometimes smooth out details too much or add "shimmering" textures. Always review availability of `_relaxed` queues if cost is verified to be lower (though upsamplers usually have fixed cost).
4. **Retry Logic**: If 4K fails, fall back to 1080p upscaling.

---

**Last Updated**: 2026-02-01
**Source**: API Knowledge Base
