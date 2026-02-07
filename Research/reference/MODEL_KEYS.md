# VEO Model Keys Reference

Complete list of all VEO models with technical specifications.

---

## Video Generation Models

### Text-to-Video (T2V)

| Model Key | Aspect Ratio | Speed | Quality | Priority | Use Case |
|-----------|--------------|-------|---------|----------|----------|
| `veo_3_1_t2v_fast_landscape_ultra` | 16:9 | Fast | Ultra | Normal | **Recommended** default |
| `veo_3_1_t2v_fast_landscape_ultra_relaxed` | 16:9 | Fast | Ultra | **Lower** | Cheaper, slower queue |
| `veo_3_1_t2v_fast_portrait` | 9:16 | Fast | Standard | Normal | Portrait videos |
| `veo_3_1_t2v_fast_portrait_relaxed` | 9:16 | Fast | Standard | **Lower** | Portrait, lower priority |
| `veo_3_1_t2v_quality_landscape` | 16:9 | Slow | Higher | Normal | Quality > speed |
| `veo_3_1_t2v_quality_landscape_relaxed` | 16:9 | Slow | Higher | **Lower** | Quality, lower priority |
| `veo_2_t2v_fast` | 16:9 | Fast | Legacy | Normal | VEO 2.0 (deprecated) |
| `veo_2_t2v_quality` | 16:9 | Slow | Legacy+ | Normal | VEO 2.0 quality mode |

**Priority Notes**:
- **Normal**: Standard queue processing
- **Lower** (`_relaxed`): Reduced priority, may cost fewer credits, longer wait times

**Endpoint**: `/v1/video:batchAsyncGenerateVideoText`

---

### Image-to-Video (I2V) - Single Frame

| Model Key | Aspect Ratio | Speed | Quality | Priority | Frame Control |
|-----------|--------------|-------|---------|----------|---------------|
| `veo_3_1_i2v_s_fast_ultra` | Dynamic | Fast | Ultra | Normal | Start frame only |
| `veo_3_1_i2v_s_fast_ultra_relaxed` | Dynamic | Fast | Ultra | **Lower** | Start frame, lower priority |

**Endpoint**: `/v1/video:batchAsyncGenerateVideoStartImage`  
**Note**: AI generates end frame automatically

---

### Image-to-Video (I2V) - Dual Frame

| Model Key | Aspect Ratio | Speed | Quality | Priority | Frame Control |
|-----------|--------------|-------|---------|----------|---------------|
| `veo_3_1_i2v_s_fast_fl_ultra` | Dynamic | Fast | Ultra | Normal | Start + End frames |
| `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | Dynamic | Fast | Ultra | **Lower** | Start + End, lower priority |

**Endpoint**: `/v1/video:batchAsyncGenerateVideoStartAndEndImage`  
**Note**: `_fl_` indicates "First + Last" frame support

---

### Reference-to-Video (R2V) - Multi-Image

| Model Key | Aspect Ratio | Speed | Quality | Priority | Images |
|-----------|--------------|-------|---------|----------|--------|
| `veo_3_1_r2v_fast_landscape_ultra` | 16:9 | Fast | Ultra | Normal | 1-3 reference images |
| `veo_3_1_r2v_fast_landscape_ultra_relaxed` | 16:9 | Fast | Ultra | **Lower** | 1-3 images, lower priority |
| `veo_3_1_r2v_fast_portrait_ultra` | 9:16 | Fast | Ultra | Normal | 1-3 reference images |
| `veo_3_1_r2v_fast_portrait_ultra_relaxed` | 9:16 | Fast | Ultra | **Lower** | 1-3 images, lower priority |

**Endpoint**: `/v1/video:batchAsyncGenerateVideoReferenceImages`  
**Note**: Also called "Ingredients to Video"

---

### Video Upsampling

| Model Key | Input | Output | Speed | Use Case |
|-----------|-------|--------|-------|----------|
| `veo_3_1_upsampler_1080p` | 720p | 1080p | ~30s | Standard upscale |
| `veo_3_1_upsampler_4k` | 720p/1080p | 4K | ~60s | Maximum quality |

**Endpoint**: `/v1/video:batchAsyncGenerateVideoUpsampleVideo`

---

### Image Generation Models

**Endpoint**: `/v1/projects/{projectId}/flowMedia:batchGenerateImages` (Synchronous)

| Model Key | Display Name | Resolution (Landscape) | Speed | Quality | Use Case |
|-----------|--------------|------------------------|-------|---------|----------|
| `IMAGEN_3_5` | **Imagen 3.5** | 1408 x 768 | Fast | ★★★★★ | Highest quality, default |
| `GEM_PIX` | **Veo Fast** | 1344 x 768 | Instant | ★★★☆☆ | Ultra-fast drafting |
| `GEM_PIX_2` | **Veo Fast Pro** | 1376 x 768 | Very Fast | ★★★★☆ | Balances speed/quality |

**Technical Notes**:
- **Synchronous**: Returns images immediately (no job ID/polling).
- **Batch Size**: 1-4 images per request.
- **Aspect Ratios**:
  - `IMAGE_ASPECT_RATIO_LANDSCAPE` (Verified)
  - `IMAGE_ASPECT_RATIO_PORTRAIT` (Predicted: swap W/H)
  - `IMAGE_ASPECT_RATIO_SQUARE` (Predicted: 1024x1024)

**Inputs**:
- Currently verified for **Text-to-Image** (`imageInputs: []`).

---

### Image Upscaling

**Endpoint**: `/v1/flow/upsampleImage` (Asynchronous - requires polling)

Upscale generated images to higher resolutions while preserving aspect ratio.

| Original Model | Original Res | 2K Upscale | 4K Upscale |
|----------------|--------------|------------|------------|
| IMAGEN_3_5 (Landscape) | 1408 × 768 | 2752 × 1536 | 5504 × 3072 |
| GEM_PIX (Landscape) | 1344 × 768 | 2688 × 1536 | 5376 × 3072 |
| GEM_PIX_2 (Landscape) | 1376 × 768 | 2752 × 1536 | 5504 × 3072 |

**API Keys**:
- `UPSAMPLE_IMAGE_RESOLUTION_2K` (2x upscale)
- `UPSAMPLE_IMAGE_RESOLUTION_4K` (4x upscale)

**Processing Time**: 5-10s (2K), 15-25s (4K)

---

## Model Family Summary

| Family | Total Models | Priority Variants | Async/Sync | Batch Support |
|--------|--------------|-------------------|------------|---------------|
| **Text-to-Video** | 8 (4 normal + 4 relaxed) | ✅ Yes | Async | ✅ Up to 4 |
| **Image-to-Video (Single)** | 2 (1 normal + 1 relaxed) | ✅ Yes | Async | ✅ Up to 4 |
| **Image-to-Video (Dual)** | 2 (1 normal + 1 relaxed) | ✅ Yes | Async | ✅ Up to 4 |
| **Reference-to-Video** | 4 (2 normal + 2 relaxed) | ✅ Yes | Async | ✅ Up to 4 |
| **Upsampling** | 2 | ❌ No | Async | ✅ Up to 4 |
| **Image Generation** | 3 | ❌ No | **Sync** | ✅ Up to 4 |

**Total**: 21 models (18 video + 3 image)
- **Video Models**: 20 (10 normal + 10 relaxed variants)
- **Image Models**: 3

**Priority System**:
- **Normal Priority**: Standard queue, full speed
- **Lower Priority** (`_relaxed`): Reduced queue priority, may cost fewer credits

---

## Model Selection Guide

### Choose by Use Case

| I want to... | Use Model | Lower Priority Option |
|--------------|-----------|----------------------|
| Generate from text (landscape) | `veo_3_1_t2v_fast_landscape_ultra` | `*_ultra_relaxed` |
| Generate from text (portrait) | `veo_3_1_t2v_fast_portrait` | `*_relaxed` |
| Animate a single image | `veo_3_1_i2v_s_fast_ultra` | `*_ultra_relaxed` |
| Control start AND end frames | `veo_3_1_i2v_s_fast_fl_ultra` | `*_fl_ultra_relaxed` |
| Use multiple reference images (landscape) | `veo_3_1_r2v_fast_landscape_ultra` | `*_ultra_relaxed` |
| Use multiple reference images (portrait) | `veo_3_1_r2v_fast_portrait_ultra` | `*_ultra_relaxed` |
| Upscale to 1080p | `veo_3_1_upsampler_1080p` | - |
| Upscale to 4K | `veo_3_1_upsampler_4k` | - |
| Generate static images | `IMAGEN_3_5` | - |
| Fast image generation | `GEM_PIX_2` | - |

**Note**: `_relaxed` suffix = Lower priority queue, may save credits

---

### Choose by Priority

**Speed Priority** (Normal Queue):
1. `IMAGEN_3_5` (sync, instant)
2. `veo_3_1_t2v_fast_*` (async, 10-20s)
3. `veo_3_1_i2v_s_fast_*` (async, 12-18s)

**Cost Priority** (Lower Queue):
1. All `*_relaxed` variants
2. Trade-off: Slightly longer wait times
3. Benefit: Reduced credit cost

**Quality Priority**:
1. `veo_3_1_upsampler_4k` (4K output)
2. `veo_3_1_*_ultra` models
3. `veo_3_1_t2v_quality_landscape`

**Control Priority**:
1. `veo_3_1_i2v_s_fast_fl_ultra` (dual frame)
2. `veo_3_1_r2v_fast_*` (multi-image)
3. `veo_3_1_i2v_s_fast_ultra` (single frame)

---

### Priority Strategy Matrix

| Scenario | Recommended Model | Rationale |
|----------|-------------------|-----------|
| **Production (urgent)** | Normal priority models | Fastest queue |
| **Batch processing** | `_relaxed` variants | Cost savings add up |
| **Testing/experimentation** | `_relaxed` variants | Save credits |
| **Client delivery** | Normal priority | Reliability + speed |
| **Background jobs** | `_relaxed` variants | Non-urgent, save money |

---

## Technical Specifications

### Resolution by Model

| Model Type | Output Resolution | Aspect Ratio |
|------------|-------------------|--------------|
| T2V Landscape | 1280x720 | 16:9 |
| T2V Portrait | 720x1280 | 9:16 |
| I2V (all) | Matches input | Dynamic |
| R2V Landscape | 1280x720 | 16:9 |
| R2V Portrait | 720x1280 | 9:16 |
| 1080p Upsampler | 1920x1080 | Original |
| 4K Upsampler | 3840x2160 | Original |
| Image Gen (IMAGEN) | 1408x768 | 16:9 like |
| Image Gen (Fast) | 1344x768 | 16:9 like |
| Image Gen (Pro) | 1376x768 | 16:9 like |

### Processing Time Estimates

| Model Type | Typical Time | Heavy Load |
|------------|--------------|------------|
| T2V | 10-20s | 30-60s |
| I2V Single | 12-18s | 40-70s |
| I2V Dual | 15-20s | 45-80s |
| R2V | 15-25s | 50-90s |
| 1080p Upscale | 20-30s | 60-120s |
| 4K Upscale | 40-60s | 120-180s |
| Image Gen (Fast) | **< 1s** | 2s |
| Image Gen (HQ) | 2-4s | 8s |

---

## Model Naming Convention

**Pattern**: `veo_VERSION_TYPE_SPEED_ASPECT_QUALITY`

**Examples**:
- `veo_3_1_t2v_fast_landscape_ultra`
  - Version: 3.1
  - Type: T2V (Text-to-Video)
  - Speed: Fast
  - Aspect: Landscape
  - Quality: Ultra

- `veo_3_1_i2v_s_fast_fl_ultra_relaxed`
  - Version: 3.1
  - Type: I2V (Image-to-Video)
  - Subtype: `s` (single model, not dual pipeline)
  - Speed: Fast
  - Mode: `fl` (First + Last frame)
  - Quality: Ultra
  - Scheduler: Relaxed

---

## Related Documentation

- [Text-to-Video Guide](../guides/02_TEXT_TO_VIDEO.md)
- [Image-to-Video Guide](../guides/03_IMAGE_TO_VIDEO.md)
- [Ingredients Guide](../guides/04_INGREDIENTS_TO_VIDEO.md)
- [Video Upscaling Guide](../guides/05_VIDEO_UPSCALING.md)

---

**Last Updated**: 2026-02-01  
**Source**: HAR file analysis + API experimentation
