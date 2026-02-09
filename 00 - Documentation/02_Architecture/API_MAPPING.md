# VEO Pro Max - API Mapping

**Purpose**: Link VEO Documentation guides to Pro Max implementation modules

---

## Endpoint Mapping

| Workflow | Endpoint | Pro Max Module | Method |
|----------|----------|----------------|--------|
| [Text-to-Video](../04_Workflows/WORKFLOW_TAB_01_TEXT_TO_VIDEO.md) | `/v1/video:batchAsyncGenerateVideoText` | `api_client.py` | `generate_video_t2v()` |
| [Image-to-Video](../04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md) | `/v1/video:batchAsyncGenerateVideoStartImage` | `api_client.py` | `generate_video_i2v_single()` |
| [Frames-to-Video](../04_Workflows/WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md) | `/v1/video:batchAsyncGenerateVideoStartAndEndImage` | `api_client.py` | `generate_video_f2v()` |
| [Ingredients](../04_Workflows/WORKFLOW_TAB_03_INGREDIENTS.md) | `/v1/video:batchAsyncGenerateVideoReferenceImages` | `api_client.py` | `generate_video_r2v()` |
| [Text-to-Image](../04_Workflows/WORKFLOW_TAB_04_TEXT_TO_IMAGE.md) | `/v1/projects/{id}/flowMedia:batchGenerateImages` | `api_client.py` | `generate_image()` |
| [Image-to-Image](../04_Workflows/WORKFLOW_TAB_05_IMAGE_TO_IMAGE.md) | `/v1/flow/upsampleImage` | `api_client.py` | `upscale_image()` |
| Authentication | N/A (Browser) | `auth_manager.py` | `extract_token_playwright()` |
| Error Handling | All | `api_client.py` | Exception classes |

---

## Model Key Mapping

> [!IMPORTANT]
> Model keys below verified against F12 HAR captures (2026-02-07). Keys with `⚠️` were NOT directly observed but documented from code.

| UI Display | VEO Model Key | Aspect Ratio | HAR Verified |
|------------|---------------|--------------|:-----------:|
| Veo 3.1 Fast (Landscape) | `veo_3_1_t2v_fast_landscape_ultra` | 16:9 | ⚠️ |
| Veo 3.1 Fast (Portrait) | `veo_3_1_t2v_fast_portrait` | 9:16 | ⚠️ |
| Veo 3.1 Fast [Relaxed] | `veo_3_1_t2v_fast_landscape_ultra_relaxed` | 16:9 | ⚠️ |
| I2V Single (Landscape) | `veo_3_1_i2v_s_fast_ultra_relaxed` | 16:9 | ✅ |
| F2V Start+End (Portrait) | `veo_3_1_i2v_s_fast_portrait_fl_ultra_relaxed` | 9:16 | ✅ |
| F2V Start+End (Landscape) | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | 16:9 | ⚠️ |
| R2V Ingredients (Portrait) | `veo_3_1_r2v_fast_portrait_ultra_relaxed` | 9:16 | ✅ |
| R2V Ingredients (Landscape) | `veo_3_1_r2v_fast_landscape_ultra_relaxed` | 16:9 | ⚠️ |
| Upscale 1080p | `veo_3_1_upsampler_1080p` | Same | ✅ |
| Upscale 4K | `veo_3_1_upsampler_4k` | Same | ✅ |
| Image: IMAGEN_3_5 | `IMAGEN_3_5` | Varies | ✅ |
| Image: Nanobanana Pro | `GEM_PIX_2` | Varies | ✅ |

---

## Workflow → UI Tab Mapping

| Workflow | UI Tab (01_UI_UX/) | API Flow |
|----------|-------------------|----------|
| Text-to-Video | TAB_01_TEXT_TO_VIDEO.md | generate_video_t2v → poll → download |
| Image-to-Video | TAB_02_IMAGE_TO_VIDEO.md | upload_image → generate_video_i2v → poll → download |
| Ingredients | TAB_03_INGREDIENTS.md | upload_images × 3 → generate_video_r2v → poll → download |
| Text-to-Image | TAB_04_TEXT_TO_IMAGE.md | generate_image (sync) → download |
| Image-to-Image | TAB_05_IMAGE_TO_IMAGE.md | upload_image → upscale_image → poll → download |

---

## Reference Links

- [CHEATSHEET](../CHEATSHEET.md) - Quick API reference
- [VEO Production Workflows](../04_Workflows/VEO_PRODUCTION_WORKFLOWS.md) - Full workflows
- [Error Handling](../03_Backend/ERROR_HANDLING_STRATEGY.md) - Error codes

---

**Last Updated**: 2026-02-07 (HAR audit verified)
