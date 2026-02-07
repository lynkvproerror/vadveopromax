# Text-to-Video Generation

Generate videos from text prompts using VEO's Text-to-Video (T2V) models.

**Model**: `veo_3_1_t2v_fast_landscape_ultra` or `veo_3_1_t2v_fast_portrait`

---

## Basic Workflow

### 1. Generate Video

```
POST /v1/video:batchAsyncGenerateVideoText
```

**Request**:
```python
import requests
import time
import random

payload = {
    "clientContext": {
        "sessionId": f";{int(time.time() * 1000)}",
        "projectId": "your-project-id",
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_ONE"
    },
    "requests": [{
        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",  # or PORTRAIT
        "seed": random.randint(0, 32767),
        "textInput": {"prompt": "A serene lake at sunset with mountains in the background"},
        "videoModelKey": "veo_3_1_t2v_fast_landscape_ultra",
        "metadata": {"sceneId": str(uuid.uuid4())}
    }]
}

headers = {"Authorization": f"Bearer {auth_token}"}
response = requests.post(T2V_URL, json=payload, headers=headers)
data = response.json()

operation_name = data["operations"][0]["operation"]["name"]
scene_id = data["operations"][0]["sceneId"]
```

### 2. Poll Status

```
POST /v1/video:batchCheckAsyncVideoGenerationStatus
```

```python
STATUS_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus"

while True:
    time.sleep(5)  # Poll every 5 seconds
    
    status_response = requests.post(
        STATUS_URL,
        json={
            "operations": [{
                "operation": {"name": operation_name},
                "sceneId": scene_id
            }]
        },
        headers=headers
    )
    
    status_data = status_response.json()
    status = status_data["operations"][0]["status"]
    
    if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
        video_url = status_data["operations"][0]["operation"]["metadata"]["video"]["fifeUrl"]
        break
    elif status == "MEDIA_GENERATION_STATUS_FAILED":
        print("Generation failed!")
        break
```

### 3. Download Video

```python
video_data = requests.get(video_url).content
with open("generated_video.mp4", "wb") as f:
    f.write(video_data)
```

---

## Batch Generation

Generate multiple variations with different seeds:

```python
seeds = [random.randint(0, 32767) for _ in range(4)]

payload = {
    "clientContext": {...},
    "requests": [
        {
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "seed": seed,
            "textInput": {"prompt": "Your prompt here"},
            "videoModelKey": "veo_3_1_t2v_fast_landscape_ultra",
            "metadata": {"sceneId": str(uuid.uuid4())}
        }
        for seed in seeds
    ]
}

# Returns 4 operation names to poll
```

---

## Model Keys

| Model | Aspect Ratio | Speed | Quality |
|-------|--------------|-------|---------|
| `veo_3_1_t2v_fast_landscape_ultra` | 16:9 | Fast | Ultra |
| `veo_3_1_t2v_fast_portrait` | 9:16 | Fast | Standard |
| `veo_3_1_t2v_quality_landscape` | 16:9 | Slow | Higher |
| `veo_2_t2v_fast` | 16:9 | Fast | Legacy |

**Recommended**: Use `veo_3_1_t2v_fast_landscape_ultra` for best quality/speed balance

---

## Status Values

| Status | Meaning | Action |
|--------|---------|--------|
| `MEDIA_GENERATION_STATUS_PENDING` | Queued | Continue polling |
| `MEDIA_GENERATION_STATUS_ACTIVE` | Processing | Continue polling |
| `MEDIA_GENERATION_STATUS_SUCCESSFUL` | Complete | Extract video URL |
| `MEDIA_GENERATION_STATUS_FAILED` | Failed | Handle error |

---

## Processing Time

- **Typical**: 10-20 seconds
- **Heavy load**: 30-60 seconds
- **Batch (4 videos)**: Same as single (parallel processing)

---

## Best Practices

1. **Seed Management**: Save seeds for reproducibility
2. **Credits**: Check `remainingCredits` in response
3. **Polling Interval**: 3-5 seconds optimal
4. **Error Handling**: Implement exponential backoff for 429 errors
5. **Prompt Quality**: Specific, descriptive prompts yield better results

---

**Related**:
- [Image-to-Video](./03_IMAGE_TO_VIDEO.md)
- [Ingredients-to-Video](./04_INGREDIENTS_TO_VIDEO.md)
- [Seed Management](../reference/SEED_GUIDE.md)
