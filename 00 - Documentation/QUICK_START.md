# VEO API Quick Start

Generate your first video in 5 minutes.

---

## Prerequisites

1. VEO project ID
2. Authorization token ([How to get](./03_Backend/ACCOUNT_SESSION_MANAGEMENT.md))

---

## Step 1: Install Dependencies

```bash
pip install requests
```

---

## Step 2: Your First Video

```python
import requests
import time
import random
import uuid

# Configuration
PROJECT_ID = "your-project-id-here"
AUTH_TOKEN = "your-bearer-token-here"

T2V_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText"
STATUS_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus"

# 1. Generate video
payload = {
    "clientContext": {
        "sessionId": f";{int(time.time() * 1000)}",
        "projectId": PROJECT_ID,
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_ONE"
    },
    "requests": [{
        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
        "seed": random.randint(5000, 24999),
        "textInput": {"prompt": "A serene lake at sunset"},
        "videoModelKey": "veo_3_1_t2v_fast_landscape_ultra",
        "metadata": {"sceneId": str(uuid.uuid4())}
    }]
}

headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
response = requests.post(T2V_URL, json=payload, headers=headers)
data = response.json()

operation_name = data["operations"][0]["operation"]["name"]
scene_id = data["operations"][0]["sceneId"]

print(f"✅ Video generation started: {operation_name}")

# 2. Wait for completion
while True:
    time.sleep(5)
    
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
    
    print(f"Status: {status}")
    
    if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
        video_url = status_data["operations"][0]["operation"]["metadata"]["video"]["fifeUrl"]
        print(f"✅ Video ready: {video_url}")
        break
    elif status == "MEDIA_GENERATION_STATUS_FAILED":
        print("❌ Generation failed")
        break

# 3. Download video
if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
    video_data = requests.get(video_url).content
    with open("my_first_veo_video.mp4", "wb") as f:
        f.write(video_data)
    print("✅ Downloaded: my_first_veo_video.mp4")
    print(f"Credits remaining: {status_data['remainingCredits']}")
```

---

## Expected Output

```
✅ Video generation started: 92cea5b7-0bdf-4b66-8d99-442c5cb21108
Status: MEDIA_GENERATION_STATUS_PENDING
Status: MEDIA_GENERATION_STATUS_ACTIVE
Status: MEDIA_GENERATION_STATUS_SUCCESSFUL
✅ Video ready: https://storage.googleapis.com/...
✅ Downloaded: my_first_veo_video.mp4
Credits remaining: 43890
```

---

## Next Steps

1. **Learn more workflows**:
   - [Image-to-Video](./04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md) - Animate images
   - [Ingredients-to-Video](./04_Workflows/WORKFLOW_TAB_03_INGREDIENTS.md) - Multi-image prompting
   - [Image Generation](./04_Workflows/WORKFLOW_TAB_04_TEXT_TO_IMAGE.md) - Generate images

2. **Explore advanced features**:
   - [Multi-Account Parallel](./04_Workflows/WORKFLOW_MULTI_ACCOUNT_PARALLEL.md) - Scale generation
   - [Text-to-Video](./04_Workflows/WORKFLOW_TAB_01_TEXT_TO_VIDEO.md) - Advanced T2V options
   - [Queue Persistence](./04_Workflows/WORKFLOW_QUEUE_PERSISTENCE.md) - Save/restore queue

3. **Reference**:
   - [Cheat Sheet](./CHEATSHEET.md) - Quick lookup
   - [API Mapping](./02_Architecture/API_MAPPING.md) - Complete API reference
   - [Error Handling](./03_Backend/ERROR_HANDLING_STRATEGY.md) - Troubleshooting

---

**Stuck?** Check [Error Handling](./03_Backend/ERROR_HANDLING_STRATEGY.md) or [Troubleshooting](./00_PROJECT/TROUBLESHOOTING.md)
