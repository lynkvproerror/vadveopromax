# VEO Image Generation API

**Model**: IMAGEN_3_5  
**Type**: Synchronous (returns URLs immediately)  
**Batch**: Up to 4 images per request

---

## API Endpoint

```
POST https://aisandbox-pa.googleapis.com/v1/projects/{projectId}/flowMedia:batchGenerateImages
```

**Response Time**: ~17 seconds for 4 images

---

## Request Payload

```json
{
  "clientContext": {
    "recaptchaContext": {
      "token": "<recaptcha_v3_token>",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769880165773",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE"
  },
  "requests": [
    {
      "seed": 80109,  // Random 0-999999
      "imageModelName": "IMAGEN_3_5",
      "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",  // or PORTRAIT, SQUARE
      "prompt": "Your prompt text",
      "imageInputs": []  // Reference images (if any)
    }
    // ... up to 3 more requests
  ]
}
```

### Aspect Ratios

| Value | Resolution |
|-------|------------|
| `IMAGE_ASPECT_RATIO_LANDSCAPE` | 1408x768 (16:9) |
| `IMAGE_ASPECT_RATIO_PORTRAIT` | 768x1408 (9:16) |
| `IMAGE_ASPECT_RATIO_SQUARE` | 1024x1024 (1:1) |

---

## Response Structure

```json
{
  "media": [
    {
      "name": "BASE64_ENCODED_ID",
      "workflowId": "dbae8451-0eee-47da-af37-ac7a68463437",
      "image": {
        "generatedImage": {
          "seed": 80109,
          "mediaGenerationId": "28f8201d-d54f-4008-9ead-a09be5912254",
          "prompt": "Sweeping",  // Translated to English
          "modelNameType": "IMAGEN_3_5",
          "fifeUrl": "https://storage.googleapis.com/ai-sandbox-videofx/image/28f8201d-d54f-4008-9ead-a09be5912254?GoogleAccessId=...&Expires=1769902103&Signature=...",
          "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"
        },
        "dimensions": {
          "width": 1408,
          "height": 768
        }
      }
    }
    // ... 3 more entries
  ],
  "workflows": [
    {
      "name": "12fa7c94-b852-47f4-8d89-46fd17188445",
      "metadata": {
        "createTime": "2026-01-31T17:28:10.369825Z",
        "primaryMediaId": "28f8201d-d54f-4008-9ead-a09be5912254"
      },
      "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16"
    }
  ]
}
```

**Key Fields**:
- `fifeUrl`: Direct download URL (signed, expires in ~6 hours)
- `seed`: For reproducing same image
- `mediaGenerationId`: Reference for upscaling/editing

---

## Python Implementation

```python
import requests
import random

def generate_images_batch(project_id, prompt, count=4, aspect_ratio="IMAGE_ASPECT_RATIO_LANDSCAPE"):
    url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"
    
    seeds = [random.randint(0, 999999) for _ in range(count)]
    
    payload = {
        "clientContext": {
            "sessionId": f";{int(time.time() * 1000)}",
            "projectId": project_id,
            "tool": "PINHOLE"
        },
        "requests": [
            {
                "seed": seed,
                "imageModelName": "IMAGEN_3_5",
                "imageAspectRatio": aspect_ratio,
                "prompt": prompt,
                "imageInputs": []
            }
            for seed in seeds
        ]
    }
    
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.post(url, json=payload, headers=headers)
    data = response.json()
    
    # Extract download URLs
    image_urls = [
        media["image"]["generatedImage"]["fifeUrl"] 
        for media in data["media"]
    ]
    
    return image_urls

# Usage
urls = generate_images_batch("your-project-id", "A beautiful landscape", count=4)
```

---

## Download Images

```python
import requests
from pathlib import Path

def download_image(url, filename):
    response = requests.get(url)
    Path(filename).write_bytes(response.content)

# Download all generated images
for i, url in enumerate(urls):
    download_image(url, f"image_{i+1}.jpg")
```

---

## Seed Management

Each image uses a unique random seed (0-999999). To reproduce an image:

```python
# Save seed from response
seed = data["media"][0]["image"]["generatedImage"]["seed"]

# Reuse seed for identical output
payload["requests"][0]["seed"] = seed
```

---

**Last Updated**: 2026-02-01  
**Source**: HAR file analysis (`Tao hinh image 4.har`)
