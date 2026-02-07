# VEO API - Model Keys & Enums Mapping
> **Source:** Extracted from HAR files + VEO Studio UI analysis
> **Last Updated:** 2026-02-02

---

## Video Generation Models

### Text-to-Video (T2V)

| UI Name | API Model Key | Aspect Ratio Enum |
|---------|---------------|-------------------|
| Veo 3.1 Fast - Landscape | `veo_3_1_t2v_fast_landscape_ultra` | `VIDEO_ASPECT_RATIO_LANDSCAPE` |
| Veo 3.1 Fast - Portrait | `veo_3_1_t2v_fast_portrait` | `VIDEO_ASPECT_RATIO_PORTRAIT` |

### Image-to-Video Single Frame (I2V)

| UI Name | API Model Key | Aspect Ratio Enum |
|---------|---------------|-------------------|
| Veo 3.1 I2V - Landscape | `veo_3_1_i2v_s_fast_ultra_relaxed` | `VIDEO_ASPECT_RATIO_LANDSCAPE` |
| Veo 3.1 I2V - Portrait | `veo_3_1_i2v_s_fast_portrait_ultra_relaxed` | `VIDEO_ASPECT_RATIO_PORTRAIT` |

### Frames-to-Video (F2V - Start + End)

| UI Name | API Model Key | Aspect Ratio Enum |
|---------|---------------|-------------------|
| Veo 3.1 F2V - Landscape | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | `VIDEO_ASPECT_RATIO_LANDSCAPE` |
| Veo 3.1 F2V - Portrait | `veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed` | `VIDEO_ASPECT_RATIO_PORTRAIT` |

### Ingredients-to-Video (R2V - References)

| UI Name | API Model Key | Aspect Ratio Enum |
|---------|---------------|-------------------|
| Veo 3.1 R2V - Landscape | `veo_3_1_r2v_fast_landscape_ultra` | `VIDEO_ASPECT_RATIO_LANDSCAPE` |
| Veo 3.1 R2V - Portrait | `veo_3_1_r2v_fast_portrait_ultra` | `VIDEO_ASPECT_RATIO_PORTRAIT` |

---

## Video Upscale Models

| Target Resolution | API Model Key | Resolution Enum |
|-------------------|---------------|-----------------|
| 1080p | `veo_3_1_upsampler_1080p` | `VIDEO_RESOLUTION_1080P` |
| 4K | `veo_3_1_upsampler_4k` | `VIDEO_RESOLUTION_4K` |

---

## Image Generation Models

| UI Name | API Endpoint | Notes |
|---------|--------------|-------|
| Image Generator | `/flowMedia:batchGenerateImages` | Synchronous response |

---

## Image Upscale Resolutions

| Target | Resolution Enum | Output Size |
|--------|-----------------|-------------|
| 2K | `UPSAMPLE_IMAGE_RESOLUTION_2K` | 2752×1536 |
| 4K | `UPSAMPLE_IMAGE_RESOLUTION_4K` | 5504×3072 |

---

## Aspect Ratio Enums

### Video Aspect Ratios

| Enum | Description | Dimensions |
|------|-------------|------------|
| `VIDEO_ASPECT_RATIO_LANDSCAPE` | Horizontal 16:9 | 1920×1080 |
| `VIDEO_ASPECT_RATIO_PORTRAIT` | Vertical 9:16 | 1080×1920 |

### Image Aspect Ratios

| Enum | Description | Use Case |
|------|-------------|----------|
| `IMAGE_ASPECT_RATIO_LANDSCAPE` | w > h | Horizontal images |
| `IMAGE_ASPECT_RATIO_PORTRAIT` | h > w | Vertical images |
| `IMAGE_ASPECT_RATIO_SQUARE` | w == h | 1:1 images |

---

## Status Enums

| Status | Description |
|--------|-------------|
| `MEDIA_GENERATION_STATUS_PENDING` | Initial state after submission |
| `MEDIA_GENERATION_STATUS_WORKING` | Processing in progress |
| `MEDIA_GENERATION_STATUS_SUCCESSFUL` | Generation complete |
| `MEDIA_GENERATION_STATUS_FAILED` | Generation failed |

---

## Paygate Tier Enums

| Enum | Description |
|------|-------------|
| `PAYGATE_TIER_ONE` | Free tier |
| `PAYGATE_TIER_TWO` | Paid/Subscriber tier |

---

## Tool Identifiers

| Tool | Usage |
|------|-------|
| `PINHOLE` | Default for all generation requests |
| `ASSET_MANAGER` | For image uploads |

---

## Image Usage Types (R2V)

| Enum | Description |
|------|-------------|
| `IMAGE_USAGE_TYPE_ASSET` | Reference image for R2V |

---

## Constants for Implementation

```python
# constants.py

class ModelKeys:
    # Text-to-Video
    T2V_LANDSCAPE = "veo_3_1_t2v_fast_landscape_ultra"
    T2V_PORTRAIT = "veo_3_1_t2v_fast_portrait"
    
    # Image-to-Video Single
    I2V_LANDSCAPE = "veo_3_1_i2v_s_fast_ultra_relaxed"
    I2V_PORTRAIT = "veo_3_1_i2v_s_fast_portrait_ultra_relaxed"
    
    # Frames-to-Video Dual
    F2V_LANDSCAPE = "veo_3_1_i2v_s_fast_fl_ultra_relaxed"
    F2V_PORTRAIT = "veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed"
    
    # Ingredients-to-Video
    R2V_LANDSCAPE = "veo_3_1_r2v_fast_landscape_ultra"
    R2V_PORTRAIT = "veo_3_1_r2v_fast_portrait_ultra"
    
    # Upscalers
    UPSCALER_1080P = "veo_3_1_upsampler_1080p"
    UPSCALER_4K = "veo_3_1_upsampler_4k"

class AspectRatio:
    VIDEO_LANDSCAPE = "VIDEO_ASPECT_RATIO_LANDSCAPE"
    VIDEO_PORTRAIT = "VIDEO_ASPECT_RATIO_PORTRAIT"
    IMAGE_LANDSCAPE = "IMAGE_ASPECT_RATIO_LANDSCAPE"
    IMAGE_PORTRAIT = "IMAGE_ASPECT_RATIO_PORTRAIT"
    IMAGE_SQUARE = "IMAGE_ASPECT_RATIO_SQUARE"

class Resolution:
    VIDEO_1080P = "VIDEO_RESOLUTION_1080P"
    VIDEO_4K = "VIDEO_RESOLUTION_4K"
    IMAGE_2K = "UPSAMPLE_IMAGE_RESOLUTION_2K"
    IMAGE_4K = "UPSAMPLE_IMAGE_RESOLUTION_4K"

class Status:
    PENDING = "MEDIA_GENERATION_STATUS_PENDING"
    WORKING = "MEDIA_GENERATION_STATUS_WORKING"
    SUCCESSFUL = "MEDIA_GENERATION_STATUS_SUCCESSFUL"
    FAILED = "MEDIA_GENERATION_STATUS_FAILED"

class Tool:
    PINHOLE = "PINHOLE"
    ASSET_MANAGER = "ASSET_MANAGER"
```
