# VEO Documentation

**Last Updated**: 2026-02-01  
**Coverage**: 8 workflows, 18+ endpoints, 6 models

---

## Core References

- **VEO_FLOW_ANALYSIS_REPORT.md** - Complete API workflows (T2V, I2V, R2V, upscale, GIF)
- **VEO_API_COMMANDS_REFERENCE.md** - Developer command index
- **VEO_QUICK_REFERENCE.md** - One-page cheat sheet

## Implementation Guides

- **VEO_FRAME_TO_VIDEO_IMPLEMENTATION_GUIDE.md** - Single frame (start image)
- **VEO_DUAL_FRAME_IMPLEMENTATION_GUIDE.md** - Dual frame (start + end)
- **VEO_INGREDIENTS_IMPLEMENTATION_GUIDE.md** - Multi-image R2V (up to 3 images) **[NEW]**
- **VEO_COMPLETE_SEED_GUIDE.md** - Seed management & client control **[NEW]**

## Advanced Topics

- **VEO_ERROR_HANDLING_GUIDE.md** - Error codes & troubleshooting
- **AUTHENTICATION_GUIDE.md** - Authorization vs reCAPTCHA modes
- **IMAGE_GENERATION_ANALYSIS.md** - Image API (IMAGEN_3_5)
- **ADVANCED_IMAGE_ANALYSIS.md** - Nanobanana models & upscaling

---

## Model Keys

| Model | Key | Use Case |
|-------|-----|----------|
| **Text-to-Video** | `veo_3_1_t2v_fast_landscape_ultra` | Default generation |
| **Image-to-Video (Single)** | `veo_3_1_i2v_s_fast_ultra_relaxed` | Start frame only |
| **Image-to-Video (Dual)** | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | Start + End frames |
| **Reference-to-Video** | `veo_3_1_r2v_fast_landscape_ultra` | Multi-image (up to 3) |
| **1080p Upsampler** | `veo_3_1_upsampler_1080p` | Video upscaling |
| **4K Upsampler** | `veo_3_1_upsampler_4k` | Video upscaling |

---

## Quick Stats

- **Endpoints Documented**: 18+
- **Workflows Covered**: 8 (T2V, I2V, R2V, GIF, Upload, Upscale, Image Gen, Status Check)
- **Models Cataloged**: 6 video models + 2 image models
- **Verification Accuracy**: 98%

---

## Recent Updates (2026-02-01)

- ✅ Added R2V (Reference-to-Video) multi-image workflow
- ✅ Documented seed management (client-side control)
- ✅ Completed model inventory (6 video models)
- ✅ Verified all endpoints against HAR files
- ✅ Added dual-frame implementation guide

---

**All documentation based on real HAR file analysis and working implementations.**
