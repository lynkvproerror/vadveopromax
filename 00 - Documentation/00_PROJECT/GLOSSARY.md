# VEO Pro Max - Terminology Glossary

**Purpose**: Định nghĩa chính xác các thuật ngữ được sử dụng trong VEO Pro Max để đảm bảo tính nhất quán trong documentation và code.

---

## 📹 Video Generation Workflows

| Term | Full Name | API Endpoint | Model Pattern | Description |
|------|-----------|--------------|---------------|-------------|
| **T2V** | Text-to-Video | `/video:batchAsyncGenerateVideoText` | `veo_3_1_t2v_*` | Tạo video từ prompt text thuần túy |
| **I2V** | Image-to-Video | `/video:batchAsyncGenerateVideoStartImage` | `veo_3_1_i2v_s_*` (no `_fl_`) | Tạo video từ **1 ảnh** + prompt |
| **F2V** | Frames-to-Video | `/video:batchAsyncGenerateVideoStartAndEndImage` | `veo_3_1_i2v_s_*_fl_*` | Tạo video từ **2 ảnh** (start + end) + prompt |
| **R2V** | References-to-Video | `/video:batchAsyncGenerateVideoReferenceImages` | `veo_3_1_r2v_*` | Tạo video sử dụng 1-3 ảnh tham khảo (character, background, style) |

---

## 🎨 Image Generation Workflows

| Term | Full Name | API Endpoint | Description |
|------|-----------|--------------|-------------|
| **T2I** | Text-to-Image | `/projects/{id}/flowMedia:batchGenerateImages` | Tạo ảnh từ prompt text |
| **I2I** | Image-to-Image | `/projects/{id}/flowMedia:batchGenerateImages` + `imageInputs` | Chỉnh sửa/biến đổi ảnh có sẵn |

---

## 📐 Upscaling

| Term | Full Name | Endpoint | Description |
|------|-----------|----------|-------------|
| **Video Upscale** | - | `/video:batchAsyncGenerateVideoUpsampleVideo` | Nâng cấp video lên 1080p/4K |
| **Image Upscale** | - | `/flow/upsampleImage` | Nâng cấp ảnh lên 2K/4K |

---

## 🔑 Model Key Naming Convention

Model keys follow the pattern `veo_{version}_{workflow}_{variant}_{speed}_{quality}_{priority}`.

> **Detailed pattern analysis and key identifiers**: See [API_MAPPING.md](../02_Architecture/API_MAPPING.md) and [UI_TO_API_PARAMETER_MAPPING.md](../02_Architecture/UI_TO_API_PARAMETER_MAPPING.md)

---

## ⚠️ Common Confusion

### I2V vs F2V

> **QUAN TRỌNG**: Model key vẫn chứa `i2v` nhưng thực chất là F2V workflow!

| Model Key | Workflow Name | Reason |
|-----------|---------------|--------|
| `veo_3_1_i2v_s_fast_ultra_relaxed` | **I2V** | No `_fl_`, single frame |
| `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | **F2V** | Has `_fl_`, dual frames |

**Cách nhận biết**:
- Xem suffix `_fl_` (First+Last) → F2V
- Không có `_fl_` → I2V
- Kiểm tra endpoint: `StartImage` = I2V, `StartAndEndImage` = F2V

---

## 🏷️ UI Display Names

### Recommended Naming

| Internal Code | UI Display Name (EN) | UI Display Name (VN) |
|---------------|---------------------|---------------------|
| `T2V` | Text to Video | Tạo video từ văn bản |
| `I2V` | Image to Video | Ảnh thành Video |
| `F2V` | Frames to Video | Multi-frame tới Video |
| `R2V` | Ingredients | Nguyên liệu tới Video |
| `T2I` | Text to Image | Tạo ảnh từ văn bản |
| `I2I` | Image Editing | Chỉnh sửa ảnh |

---

## 📊 Aspect Ratio Terms

| Term | Meaning | API Value |
|------|---------|-----------|
| **Landscape** | 16:9 (horizontal) | `VIDEO_ASPECT_RATIO_LANDSCAPE` |
| **Portrait** | 9:16 (vertical) | `VIDEO_ASPECT_RATIO_PORTRAIT` |
| **Square** | 1:1 (image only) | `IMAGE_ASPECT_RATIO_SQUARE` |

---

## 🔐 Account & Subscription Terms

| Term | Meaning | API Value |
|------|---------|-----------|
| **Freemium** | Free tier | `PAYGATE_TIER_NOT_PAID`, `WS_FREEMIUM` |
| **Pro** | Paid tier 1 | `PAYGATE_TIER_ONE` |
| **Ultra** | Paid tier 2 | `PAYGATE_TIER_TWO`, `WS_ULTRA` |

---

## 📝 Code Naming Conventions

### File Naming

| Component | Pattern | Example |
|-----------|---------|---------|
| Tab modules | `tab_{workflow}.py` | `tab_i2v.py`, `tab_f2v.py` |
| UI Components | `{component_name}.py` | `image_upload_box.py` |
| Core modules | `{function}.py` | `api_client.py`, `queue_manager.py` |

### Variable Naming

| Pattern | Usage | Example |
|---------|-------|---------|
| `{workflow}_*` | Workflow-specific | `i2v_model`, `f2v_endpoint` |
| `*_id` | Identifiers | `media_id`, `scene_id` |
| `*_path` | File paths | `image_path`, `video_path` |

---

## 🔗 Related Documentation

- [API_MAPPING.md](../02_Architecture/API_MAPPING.md) - Endpoint mapping
- [UI_TO_API_PARAMETER_MAPPING.md](../02_Architecture/UI_TO_API_PARAMETER_MAPPING.md) - Parameter conversion
- [CHEATSHEET.md](../CHEATSHEET.md) - Quick reference for model keys

---

**Last Updated**: 2026-02-02
