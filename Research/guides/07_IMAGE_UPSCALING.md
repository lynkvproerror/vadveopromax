# VEO Image Upscaling Guide

Upscale generated images to 2K or 4K resolution while preserving aspect ratio.

---

## ⚡ Quick Scan

| Feature | Details |
|---------|---------|
| **Endpoint** | `POST .../upsampleImage` |
| **Method** | Asynchronous (polling required) |
| **Levels** | 2K (2752×1536), 4K (5504×3072) |
| **Source** | Images from `batchGenerateImages` |

---

## 📊 Upscale Resolutions

| Original Image | 2K Upscale | 4K Upscale | Multiplier |
|----------------|------------|------------|------------|
| **1408 × 768** (IMAGEN_3_5) | 2752 × 1536 | 5504 × 3072 | 2x / 4x |
| **1344 × 768** (GEM_PIX) | 2688 × 1536 | 5376 × 3072 | 2x / 4x |
| **1376 × 768** (GEM_PIX_2) | 2752 × 1536 | 5504 × 3072 | 2x / 4x |

**Note**: All aspect ratios are preserved during upscaling.

---

## 🛠️ Workflow

### Step 1: Generate Original Image

```python
# First, generate image using batchGenerateImages
response = generate_images(
    project_id="your-project-id",
    auth_token="ya29...",
    prompt="A futuristic city",
    model="IMAGEN_3_5"
)

# Extract media ID for upscaling
media_id = response["media"][0]["name"]  # Base64-encoded ID
```

### Step 2: Request Upscale

**Endpoint**:
```
POST https://aisandbox-pa.googleapis.com/v1/flow/upsampleImage
```

**Payload**:
```json
{
  "mediaId": "CAM...",
  "targetResolution": "UPSAMPLE_IMAGE_RESOLUTION_4K",
  "clientContext": {
    "recaptchaContext": {
      "token": "<recaptcha_v3_token>",
      "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
    },
    "sessionId": ";1769817646087",
    "projectId": "f5db1342-c676-437b-b763-d97ae2d7cd16",
    "tool": "PINHOLE"
  }
}
```

**Target Resolution Options**:
- `UPSAMPLE_IMAGE_RESOLUTION_2K` → 2752 × 1536
- `UPSAMPLE_IMAGE_RESOLUTION_4K` → 5504 × 3072

### Step 3: Poll for Completion

Unlike image generation (synchronous), upscaling is **asynchronous**. You need to poll the status:

```python
import time

def poll_upscale_status(job_id, project_id, auth_token):
    """Poll upscale job until complete"""
    status_url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/jobs/{job_id}"
    
    while True:
        response = requests.get(status_url, headers={
            "Authorization": f"Bearer {auth_token}"
        })
        data = response.json()
        
        status = data["status"]
        
        if status == "MEDIA_GENERATION_STATUS_SUCCEEDED":
            return data["upscaledImageUrl"]
        elif status == "MEDIA_GENERATION_STATUS_FAILED":
            raise Exception(f"Upscale failed: {data.get('error')}")
        elif status in ["MEDIA_GENERATION_STATUS_PENDING", "MEDIA_GENERATION_STATUS_ACTIVE"]:
            time.sleep(2)  # Poll every 2 seconds
            continue
        else:
            raise Exception(f"Unknown status: {status}")
```

### Step 4: Download Upscaled Image

```python
def download_upscaled_image(url, filename):
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)
    print(f"Downloaded: {filename}")
```

---

## 💻 Complete Implementation

```python
import requests
import time

UPSCALE_URL = "https://aisandbox-pa.googleapis.com/v1/flow/upsampleImage"

def upscale_image(media_id, project_id, auth_token, target_resolution="4K"):
    """
    Upscale a generated image to 2K or 4K
    
    Args:
        media_id: Base64-encoded media ID from batchGenerateImages
        project_id: VEO project ID
        auth_token: OAuth2 token
        target_resolution: "2K" or "4K"
    
    Returns:
        URL of upscaled image
    """
    # Map resolution to API key
    resolution_map = {
        "2K": "UPSAMPLE_IMAGE_RESOLUTION_2K",
        "4K": "UPSAMPLE_IMAGE_RESOLUTION_4K"
    }
    
    payload = {
        "mediaId": media_id,
        "targetResolution": resolution_map[target_resolution],
        "clientContext": {
            "projectId": project_id,
            "tool": "PINHOLE",
            "recaptchaContext": {
                "token": "RECAPTCHA_TOKEN_HERE",
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
            }
        }
    }
    
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    
    print(f"Requesting {target_resolution} upscale...")
    response = requests.post(UPSCALE_URL, json=payload, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Upscale request failed: {response.text}")
    
    job_data = response.json()
    job_id = job_data["jobId"]
    
    # Poll for completion
    print(f"Job ID: {job_id}, polling for completion...")
    upscaled_url = poll_upscale_status(job_id, project_id, auth_token)
    
    print(f"Upscale complete: {upscaled_url}")
    return upscaled_url

# Usage
upscaled_url = upscale_image(
    media_id="CAM...",
    project_id="your-project-id",
    auth_token="ya29...",
    target_resolution="4K"
)

# Download
download_upscaled_image(upscaled_url, "upscaled_4k.jpg")
```

---

## 🔍 Technical Details

### Processing Time

| Resolution | Typical Time | Heavy Load |
|------------|--------------|------------|
| 2K | 5-10s | 15-30s |
| 4K | 15-25s | 40-60s |

### File Naming Convention

Downloaded files follow this pattern:
```
{prompt}_{resolution}_{timestamp}.jpeg
```

Examples:
- `Futuristic_city_4k_20260201050123.jpeg`
- `Mountain_landscape_2k_20260201050045.jpeg`

### Analytics Events

- `pinhole_upscale_image`: Triggered when upscale is requested
- `download_upscaled_4k`: Triggered when 4K image is downloaded

---

## 💡 Best Practices

1. **Generate First, Upscale Later**
   - Test prompts with base resolution first
   - Only upscale final selections to save processing time

2. **Choose Resolution Based on Use Case**
   - **2K**: Social media, web display, presentations
   - **4K**: Print, high-res displays, professional use

3. **Aspect Ratio Awareness**
   - Upscaling preserves original aspect ratio
   - Portrait images: 768 × 1408 → 1536 × 2816 (2K) → 3072 × 5632 (4K)
   - Square images: Different multipliers apply

4. **Error Handling**
   - Always check job status for failures
   - Implement retry logic for network errors
   - Set maximum poll duration (e.g., 2 minutes timeout)

---

## ⚠️ Limitations

- ❌ Cannot upscale already-upscaled images (no chaining)
- ❌ Only works with images generated via `batchGenerateImages`
- ❌ Cannot upscale uploaded/external images
- ❌ Maximum 4K resolution (no 8K option)

---

**Last Updated**: 2026-02-01  
**Source**: HAR analysis (`download image 4k.har`, `Download anh 4k hoan thanh.har`)
