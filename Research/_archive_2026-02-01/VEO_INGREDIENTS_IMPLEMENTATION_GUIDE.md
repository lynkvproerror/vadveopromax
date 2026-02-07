# VEO Ingredients to Video (R2V - Reference-to-Video)

**Endpoint**: `POST /v1/video:batchAsyncGenerateVideoReferenceImages`  
**Model**: `veo_3_1_r2v_fast_landscape_ultra`  
**Feature**: Multi-image prompting (up to 3 reference images)

---

## Request Payload

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "0cAFcWeA45LAC7BKDC4qkU0n6OdyPXGkWQ0...",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769888782642",
    "projectId": "daba1978-e588-4d76-a4fd-6c3126074187",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_TWO"
  },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
      "metadata": {"sceneId": "1996ea36-2f06-493c-bca1-010816265fe3"},
      "referenceImages": [
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "CAMaJGM3ZTdkODY4LWI2NDgtNGQyMi1hZjUyLTM0M2ZmMjA5YjhhMSIDQ0FFKiRkNzVkZjc4OS1lZDMyLTQyNmYtYjUwYi1mMTg3ODFlOTc2OWI"
        },
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "CAMaJDk4NTVmY2NhLTRkYWEtNDkyMy05MGMzLTNhYTE0YmExYjRkNyIDQ0FFKiQ2MmEyYmVhYy03ODUyLTQ3YmEtYWRkNC00NzExYjdmNzc2YmU"
        },
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "CAMaJDI0YzU0M2EwLTM5MGEtNDJhNi1iNDU1LTFjYTljMmExYzNkNyIDQ0FFKiQ0OTVjYWIxZS1lZWI2LTRmMWMtOTcwYy1mODhlNzViNmExZTI"
        }
      ],
      "seed": 25325,  // Random 0-32767
      "textInput": {"prompt": "Kết hợp khung cảnh u buồn"},
      "videoModelKey": "veo_3_1_r2v_fast_landscape_ultra"
    }
    // ... up to 3 more requests (different seeds for variations)
  ]
}
```

**Key Parameters**:
- `referenceImages`: Array of 1-3 images, each with `IMAGE_USAGE_TYPE_ASSET` + `mediaId`
- `mediaId`: Base64-encoded identifier (from upload step)
- `seed`: Different per request for variations
- `videoModelKey`: Must be `veo_3_1_r2v_fast_landscape_ultra` (or portrait variant)

---

## Response Structure

### Initial Submission Response

```json
{
  "operations": [
    {
      "operation": {"name": "b5d4de86-03f6-4c1c-a722-19c04abae87c"},
      "sceneId": "1996ea36-2f06-493c-bca1-010816265fe3",
      "status": "MEDIA_GENERATION_STATUS_PENDING"
    }
  ],
  "remainingCredits": 43890,
  "workflows": [{
    "name": "48157e9e-ecb7-4639-9e19-072c3c40368e",
    "metadata": {
      "createTime": "2026-01-31T20:16:25.165727Z",
      "primaryMediaId": "b5d4de86-03f6-4c1c-a722-19c04abae87c",
      "batchId": "e11a7f01-8eb1-405b-9087-08444dcbded0"
    }
  }],
  "media": [{
    "name": "b5d4de86-03f6-4c1c-a722-19c04abae87c",
    "workflowId": "48157e9e-ecb7-4639-9e19-072c3c40368e",
    "mediaMetadata": {
      "mediaStatus": {"mediaGenerationStatus": "MEDIA_GENERATION_STATUS_PENDING"}
    }
  }]
}
```

### Completion Response (After Polling)

**Status**: `MEDIA_GENERATION_STATUS_SUCCESSFUL` (not "COMPLETED")

```json
{
  "operations": [
    {
      "operation": {
        "name": "92cea5b7-0bdf-4b66-8d99-442c5cb21108",
        "metadata": {
          "@type": "type.googleapis.com/google.internal.labs.aisandbox.v1.Media",
          "video": {
            "seed": 7393,
            "mediaGenerationId": "CAUSJGRhYmExOTc4...",
            "prompt": "Kết hợp khung cảnh u buồn",
            "fifeUrl": "https://storage.googleapis.com/ai-sandbox-videofx/video/92cea5b7-0bdf-4b66-8d99-442c5cb21108?GoogleAccessId=labs-ai-sandbox-videoserver-prod@system.gserviceaccount.com&Expires=1769911903&Signature=...",
            "mediaVisibility": "PRIVATE",
            "servingBaseUri": "https://storage.googleapis.com/ai-sandbox-videofx/image/92cea5b7-0bdf-4b66-8d99-442c5cb21108?...",
            "model": "veo_3_1_r2v_fast_portrait_ultra_relaxed",
            "isLooped": false,
            "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT"
          }
        }
      },
      "sceneId": "1088d16f-b395-44e0-8aa8-be1df603b0a9",
      "mediaGenerationId": "CAUSJGRhYmExOTc4...",
      "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL"
    }
  ],
  "remainingCredits": 43930
}
```

**Key Fields**:
- `status`: `MEDIA_GENERATION_STATUS_SUCCESSFUL` (final state)
- `fifeUrl`: Video download URL (signed, ~6 hour expiry)
- `servingBaseUri`: Thumbnail/preview image URL
- `model`: Actual model used (may include `_relaxed` suffix)
- `remainingCredits`: Updated after generation

---

## Polling Workflow

**Endpoint**: `POST /v1/video:batchCheckAsyncVideoGenerationStatus`

**Request Payload**:
```json
{
  "operations": [
    {
      "operation": {"name": "b5d4de86-03f6-4c1c-a722-19c04abae87c"},
      "sceneId": "1996ea36-2f06-493c-bca1-010816265fe3"
    }
  ]
}
```

**Polling Strategy**:
1. Submit generation → Get operation names
2. Wait 3-5 seconds
3. Call status check with operation names
4. Check `status` field:
   - `MEDIA_GENERATION_STATUS_PENDING` → Continue polling
   - `MEDIA_GENERATION_STATUS_ACTIVE` → Continue polling (processing)
   - `MEDIA_GENERATION_STATUS_SUCCESSFUL` → Extract `fifeUrl`, download video
   - `MEDIA_GENERATION_STATUS_FAILED` → Handle error

**Processing Time**: Typically 8-15 seconds for R2V generation



---

## Workflow

**Complete Flow**:
1. **Upload Images** → Get `mediaId` for each (1-3 images)
2. **Submit Batch** → Generate 1-4 videos with same images, different seeds
3. **Poll Status** → Check `/batchCheckAsyncVideoGenerationStatus` every 3-5s
4. **Download Videos** → Extract `fifeUrl` from SUCCESSFUL operations

**Status Progression**:
```
PENDING → ACTIVE → SUCCESSFUL (with video URLs)
```

---

## Multi-Variation Strategy

**Common Pattern** (observed in HAR files):
- Same prompt: "Kết hợp khung cảnh u buồn"
- Same 3 reference images (mediaIds repeated)
- Different seeds: `25325`, `7374`, `14108`, `14990`
- Result: 4 variations for user selection

---

## Model Keys

| Model | Aspect Ratio | Speed | Quality |
|-------|--------------|-------|---------|
| `veo_3_1_r2v_fast_landscape_ultra` | 16:9 | Fast | Ultra |
| `veo_3_1_r2v_fast_portrait_ultra` | 9:16 | Fast | Ultra |

**vs T2V (Text-to-Video)**:
- Model prefix: `r2v` (not `t2v`)
- Requires: `referenceImages` array
- Use case: Style/content transfer from images to video

---

## Implementation

```python
import requests
import time
import random

R2V_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoReferenceImages"
STATUS_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus"
UPLOAD_URL = "https://aisandbox-pa.googleapis.com/v1:uploadUserImage"

# Step 1: Upload images
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

# Upload 3 images
image_paths = ["image1.jpg", "image2.jpg", "image3.jpg"]
media_ids = [upload_image(path, token) for path in image_paths]

# Step 2: Generate videos (4 variations)
reference_images = [
    {"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": mid}
    for mid in media_ids
]

seeds = [random.randint(0, 32767) for _ in range(4)]

payload = {
    "clientContext": {
        "sessionId": f";{int(time.time() * 1000)}",
        "projectId": project_id,
        "tool": "PINHOLE",
        "userPaygateTier": "PAYGATE_TIER_TWO"
    },
    "requests": [
        {
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "metadata": {"sceneId": str(uuid.uuid4())},
            "referenceImages": reference_images,
            "seed": seed,
            "textInput": {"prompt": "Your prompt here"},
            "videoModelKey": "veo_3_1_r2v_fast_landscape_ultra"
        }
        for seed in seeds
    ]
}

response = requests.post(R2V_URL, json=payload, headers={"Authorization": f"Bearer {token}"})
initial_data = response.json()

# Step 3: Poll for completion
operations = [
    {"operation": {"name": op["operation"]["name"]}, "sceneId": op["sceneId"]}
    for op in initial_data["operations"]
]

while True:
    time.sleep(5)  # Wait 5 seconds between polls
    
    status_response = requests.post(
        STATUS_URL,
        json={"operations": operations},
        headers={"Authorization": f"Bearer {token}"}
    )
    status_data = status_response.json()
    
    # Check if all completed
    all_done = all(
        op["status"] == "MEDIA_GENERATION_STATUS_SUCCESSFUL"
        for op in status_data["operations"]
    )
    
    if all_done:
        break
    
    # Check for failures
    if any(op["status"] == "MEDIA_GENERATION_STATUS_FAILED" for op in status_data["operations"]):
        print("Generation failed!")
        break

# Step 4: Download videos
video_urls = [
    op["operation"]["metadata"]["video"]["fifeUrl"]
    for op in status_data["operations"]
    if op["status"] == "MEDIA_GENERATION_STATUS_SUCCESSFUL"
]

for i, url in enumerate(video_urls):
    video_data = requests.get(url).content
    with open(f"video_{i+1}.mp4", "wb") as f:
        f.write(video_data)

print(f"Downloaded {len(video_urls)} videos!")
print(f"Remaining credits: {status_data['remainingCredits']}")
```

---

## Requirements

1. **reCAPTCHA v3 Enterprise**: Required for browser-based requests
2. **Image Upload**: Images must be uploaded first to get `mediaId`
3. **UUID Generation**: Client generates `sceneId` for each request
4. **Seed Management**: Use different seeds for variations, same seed for reproducibility

---

## Batch Processing

- **Max batch size**: 4 requests per call (observed)
- **Credit consumption**: Check `remainingCredits` in response
- **Error handling**: Each operation can fail independently

---

**Last Updated**: 2026-02-01  
**Source**: Complete HAR file analysis  
- Submit: `01.3 169 ingedients to video submit 4 video prompt 3 anh.har`
- Completion: `01. ingedients to video hoan thanh 4 video prompt 3 anh.har`
