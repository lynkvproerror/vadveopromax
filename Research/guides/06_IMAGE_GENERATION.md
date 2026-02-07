# VEO Image Generation Guide

Generate high-quality images using **Imagen 3.5** and **Veo Fast (Nanobanana)** models.

---

## ⚡ Quick Scan

| Feature | Details |
|---------|---------|
| **Endpoint** | `POST .../flowMedia:batchGenerateImages` |
| **Methods** | Synchronous (instant response) |
| **Batch Size** | 1-4 images per request |
| **Models** | `IMAGEN_3_5`, `GEM_PIX`, `GEM_PIX_2` |
| **Format** | JPEG (via signed URL) |

---

## 🎨 Available Models

| Model Key | Display Name | Resolution | Speed | Quality | Best For |
|-----------|--------------|------------|-------|---------|----------|
| `IMAGEN_3_5` | **Imagen 3.5** | 1408 × 768 | Fast | ★★★★★ | Final production, highest detail |
| `GEM_PIX` | **Veo Fast** | 1344 × 768 | Instant | ★★★☆☆ | Rapid drafting, storyboarding |
| `GEM_PIX_2` | **Veo Fast Pro** | 1376 × 768 | Very Fast | ★★★★☆ | Balanced speed & quality |

**Note**: Resolutions shown are for **Landscape (16:9)**.

---

## 🛠️ Workflow

### 1. Generate Images (Synchronous)

Unlike video generation, image generation is **synchronous**. You get the download URLs immediately in the response.

**Endpoint**:
```
POST https://aisandbox-pa.googleapis.com/v1/projects/{projectId}/flowMedia:batchGenerateImages
```

**Payload**:
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
      "seed": 80109,
      "imageModelName": "IMAGEN_3_5",
      "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
      "prompt": "A futuristic city with flying cars, cyberpunk style",
      "imageInputs": [] 
    },
    {
      "seed": 45123,
      "imageModelName": "IMAGEN_3_5",
      "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
      "prompt": "A futuristic city with flying cars, cyberpunk style",
      "imageInputs": [] 
    }
    // ... up to 4 requests total
  ]
}
```

### 2. Parse Response

The response contains the image metadata and download URL immediately.

```json
{
  "media": [
    {
      "image": {
        "generatedImage": {
          "seed": 80109,
          "modelNameType": "IMAGEN_3_5",
          "fifeUrl": "https://storage.googleapis.com/ai-sandbox-videofx/image/UUID?GoogleAccessId=...&Expires=...&Signature=...",
          "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
          "prompt": "A futuristic city with flying cars, cyberpunk style"
        },
        "dimensions": {
          "width": 1408,
          "height": 768
        }
      }
    }
    // ... other images
  ]
}
```

---

## 💻 Implementation Example

```python
import requests
import random
import time

GENERATE_URL = "https://aisandbox-pa.googleapis.com/v1/projects/{}/flowMedia:batchGenerateImages"

def generate_images(project_id, auth_token, prompt, count=4, model="IMAGEN_3_5"):
    """
    Generate images synchronously.
    Models: IMAGEN_3_5, GEM_PIX, GEM_PIX_2
    """
    url = GENERATE_URL.format(project_id)
    
    # Create batch requests
    batch_requests = []
    for _ in range(count):
        batch_requests.append({
            "seed": random.randint(0, 999999), 
            "imageModelName": model,
            "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "prompt": prompt,
            "imageInputs": []
        })
        
    payload = {
        "clientContext": {
            "projectId": project_id,
            "tool": "PINHOLE",
            "recaptchaContext": {
                "token": "RECAPTCHA_TOKEN_HERE",
                "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB"
            }
        },
        "requests": batch_requests
    }
    
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    
    print(f"Generating {count} images with {model}...")
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code != 200:
        print(f"Error: {response.text}")
        return []
        
    data = response.json()
    
    # Extract results
    results = []
    if "media" in data:
        for item in data["media"]:
            img_data = item["image"]["generatedImage"]
            results.append({
                "url": img_data["fifeUrl"],
                "seed": img_data["seed"],
                "width": item["image"]["dimensions"]["width"],
                "height": item["image"]["dimensions"]["height"]
            })
            
    return results

# Usage
images = generate_images(
    project_id="my-project-id",
    auth_token="ya29...",
    prompt="Cinematic shot of a samurai robot",
    count=4,
    model="GEM_PIX_2"  # Try the fast model!
)

for i, img in enumerate(images):
    print(f"Image {i+1}: {img['width']}x{img['height']} - {img['url'][:50]}...")
```

---

## 📐 Aspect Ratios & Resolutions

| Aspect Ratio | Key | IMAGEN_3_5 | GEM_PIX | GEM_PIX_2 |
|--------------|-----|------------|---------|-----------|
| **Landscape** | `IMAGE_ASPECT_RATIO_LANDSCAPE` | 1408 × 768 | 1344 × 768 | 1376 × 768 |
| **Portrait** | `IMAGE_ASPECT_RATIO_PORTRAIT` | 768 × 1408* | 768 × 1344* | 768 × 1376* |
| **Square** | `IMAGE_ASPECT_RATIO_SQUARE` | 1024 × 1024* | 1024 × 1024* | 1024 × 1024* |

*\*Portrait and Square resolutions are predicted based on standard model behaviors, pending HAR verification.*

---

## 💡 Best Practices

1. **Use `GEM_PIX` for Iteration**
   - It's instant and costs less (or zero) credits often.
   - Use it to test prompts quickly.

2. **Use `IMAGEN_3_5` for Final**
   - Switch to Imagen when the prompt allows for high detail.
   - Maximize resolution output.

3. **Parallel Generation**
   - The API accepts up to 4 requests in the `requests` array.
   - Always use `count=4` to get variety for the same credit cost "slot" (if applicable).

4. **Seed Control**
   - Save the `seed` from the response.
   - Re-send the same `seed` + same `prompt` + same `model` to regenerate the **exact same image**.

---

**Last Updated**: 2026-02-01  
**Source**: HAR analysis (`Tao hinh image 4.har`, `Tao hinh nanobanana.har`, `Tao hinh nanobanana pro.har`)
