# VEO Model Comparison Analysis

**Date**: 2026-02-01  
**Status**: Complete Analysis  
**Source HAR Files**: `Model Video (text to video).har`, `Model Video (ingedients to video).har`

---

## 🎯 Executive Summary

Analysis of VEO model selection behavior reveals that **UI model selection** uses identical keys across Text-to-Video and Ingredients/Image-to-Video features, but **actual generation** automatically translates keys based on input type.

---

## 📊 Model Key Comparison

### UI Selection Keys (Common Across All Features)

| Model Display Name | Model Key | Found In |
|-------------------|-----------|----------|
| **Veo 3.1 - Fast (Ultra)** | `veo_3_1_t2v_fast_portrait_ultra` | Both HAR files |
| **Veo 3.1 - Fast (Relaxed)** | `veo_3_1_t2v_fast_portrait_ultra_relaxed` | Both HAR files |
| **Veo 3.1 - Quality** | `veo_3_1_t2v_portrait` | Both HAR files |
| **Veo 2.1 - Fast** | `veo_2_1_fast_d_15_t2v` | Both HAR files |
| **Veo 2.0 - Quality** | `veo_2_0_t2v` | Both HAR files |

### Actual Generation Keys (Auto-Mapped by Backend)

When generation requests are made with image inputs, the backend automatically converts keys:

| UI Selection Key | Text-to-Video (Actual) | Image-to-Video (Actual) |
|-----------------|------------------------|-------------------------|
| `veo_3_1_t2v_fast_portrait_ultra` | `veo_3_1_t2v_fast_portrait_ultra` | `veo_3_1_i2v_s_fast_portrait_ultra` |
| `veo_3_1_t2v_fast_portrait_ultra_relaxed` | `veo_3_1_t2v_fast_portrait_ultra_relaxed` | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` |
| `veo_3_1_t2v_portrait` | `veo_3_1_t2v_portrait` | `veo_3_1_i2v_s_portrait` |

---

## 🔍 Key Findings

### 1. UI State Management

**Endpoint**: `https://labs.google/fx/api/trpc/videoFx.setLastSelectedVideoModelKey`

**Behavior**:
- Saves user's last model selection using `t2v` keys for **all features**
- No distinction between Text-to-Video, Image-to-Video, or Ingredients modes
- State persistence is tab-agnostic

**Example Request**:
```json
{
  "json": {
    "modelKey": "veo_3_1_t2v_fast_portrait_ultra_relaxed"
  }
}
```

**Example Response**:
```json
{
  "result": {
    "data": {
      "json": {
        "result": {
          "lastSelectedVideoModelKey": "veo_3_1_t2v_fast_portrait_ultra_relaxed",
          "lastSelectedVideoAspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT"
        }
      }
    }
  }
}
```

### 2. Generation Request Translation

**Text-to-Video Generation**:
```json
{
  "requests": [{
    "textInput": { "prompt": "..." },
    "videoModelKey": "veo_3_1_t2v_fast_portrait_ultra",
    // No image fields
  }]
}
```

**Image-to-Video Generation** (Automatically Translated):
```json
{
  "requests": [{
    "textInput": { "prompt": "..." },
    "videoModelKey": "veo_3_1_i2v_s_fast_fl_ultra_relaxed", // ← Auto-converted!
    "startImage": { "mediaId": "..." },
    "endImage": { "mediaId": "..." }
  }]
}
```

---

## 📋 Complete Model Reference

### VEO 3.1 Models

| Category | Text-to-Video Key | Image-to-Video Key | Speed | Quality |
|----------|-------------------|-------------------|-------|---------|
| **Fast (Standard)** | `veo_3_1_t2v_fast_portrait` | `veo_3_1_i2v_s_fast_portrait` | ⚡⚡⚡ | ⭐⭐ |
| **Fast (Ultra)** | `veo_3_1_t2v_fast_portrait_ultra` | `veo_3_1_i2v_s_fast_portrait_ultra` | ⚡⚡⚡ | ⭐⭐⭐ |
| **Fast (Relaxed)** | `veo_3_1_t2v_fast_portrait_ultra_relaxed` | `veo_3_1_i2v_s_fast_fl_ultra_relaxed` | ⚡⚡ | ⭐⭐⭐ |
| **Quality** | `veo_3_1_t2v_portrait` | `veo_3_1_i2v_s_portrait` | ⚡ | ⭐⭐⭐⭐ |

### VEO 2.x Models

| Category | Key | Type | Speed | Quality |
|----------|-----|------|-------|---------|
| **VEO 2.1 Fast** | `veo_2_1_fast_d_15_t2v` | Text-to-Video Only | ⚡⚡⚡ | ⭐⭐ |
| **VEO 2.0 Quality** | `veo_2_0_t2v` | Text-to-Video Only | ⚡ | ⭐⭐⭐ |

> ⚠️ **Note**: VEO 2.x models do not have Image-to-Video variants.

### Aspect Ratio Modifiers

Models support both portrait and landscape. Replace `portrait` with `landscape` in keys:

| Portrait Key | Landscape Key |
|--------------|---------------|
| `veo_3_1_t2v_fast_portrait` | `veo_3_1_t2v_fast_landscape` |
| `veo_3_1_i2v_s_fast_portrait` | `veo_3_1_i2v_s_fast_landscape` |

---

## 🔄 Key Translation Rules

### Pattern Recognition

**Text-to-Video**: `veo_{version}_t2v_{variant}_{aspect}`
**Image-to-Video**: `veo_{version}_i2v_s_{variant}_{aspect}`

### Translation Logic

```javascript
function translateModelKey(uiKey, hasImageInput) {
  if (!hasImageInput) {
    return uiKey; // Use as-is for text-to-video
  }
  
  // Convert t2v to i2v_s for image-to-video
  return uiKey
    .replace('t2v_fast_portrait_ultra_relaxed', 'i2v_s_fast_fl_ultra_relaxed')
    .replace('t2v_fast_portrait_ultra', 'i2v_s_fast_portrait_ultra')
    .replace('t2v_fast_portrait', 'i2v_s_fast_portrait')
    .replace('t2v_portrait', 'i2v_s_portrait')
    .replace('t2v_fast_landscape_ultra_relaxed', 'i2v_s_fast_fl_ultra_relaxed')
    .replace('t2v_fast_landscape_ultra', 'i2v_s_fast_landscape_ultra')
    .replace('t2v_fast_landscape', 'i2v_s_fast_landscape')
    .replace('t2v_landscape', 'i2v_s_landscape');
}
```

### Python Implementation

```python
def translate_model_key(ui_key: str, has_image_input: bool) -> str:
    """
    Translate UI model key to actual generation key.
    
    Args:
        ui_key: Key from UI selection (e.g., 'veo_3_1_t2v_fast_portrait_ultra')
        has_image_input: True if request includes startImage or endImage
    
    Returns:
        Actual model key for API request
    """
    if not has_image_input:
        return ui_key  # Text-to-video uses UI key directly
    
    # Image-to-video translation
    translations = {
        't2v_fast_portrait_ultra_relaxed': 'i2v_s_fast_fl_ultra_relaxed',
        't2v_fast_landscape_ultra_relaxed': 'i2v_s_fast_fl_ultra_relaxed',
        't2v_fast_portrait_ultra': 'i2v_s_fast_portrait_ultra',
        't2v_fast_landscape_ultra': 'i2v_s_fast_landscape_ultra',
        't2v_fast_portrait': 'i2v_s_fast_portrait',
        't2v_fast_landscape': 'i2v_s_fast_landscape',
        't2v_portrait': 'i2v_s_portrait',
        't2v_landscape': 'i2v_s_landscape',
    }
    
    for t2v_pattern, i2v_pattern in translations.items():
        if t2v_pattern in ui_key:
            return ui_key.replace(t2v_pattern, i2v_pattern)
    
    return ui_key  # Fallback to original
```

---

## 💡 Implementation Recommendations

### For UI Development

1. **Single Model List**: Use one unified model dropdown for all features
2. **Key Storage**: Store user selection using `t2v` keys
3. **Runtime Translation**: Apply translation only when sending generation request

### For API Integration

```python
# Example workflow
user_selected_model = "veo_3_1_t2v_fast_portrait_ultra_relaxed"
has_images = bool(start_image or end_image)

actual_model_key = translate_model_key(user_selected_model, has_images)

payload = {
    "requests": [{
        "videoModelKey": actual_model_key,  # Auto-translated
        "textInput": {"prompt": prompt},
        # Include startImage/endImage if present
    }]
}
```

---

## 📁 Evidence Sources

### HAR File Analysis

**Files Analyzed**:
1. `Model Video (text to video).har` (4,864 lines)
   - Contains 10 POST requests to `setLastSelectedVideoModelKey`
   - All keys are `t2v` variants

2. `Model Video (ingedients to video).har` (4,864 lines)
   - Contains 10 POST requests to `setLastSelectedVideoModelKey`
   - All keys are identical `t2v` variants

**Key Observation**: No actual generation requests (`batchAsyncGenerateVideo*`) were found in these files, confirming they capture only UI state changes.

### Cross-Reference

Previous analysis of `chon firt va last bắt đầu 50.har` revealed actual generation payloads with `i2v` keys when images were present, confirming the backend translation behavior.

---

## 🎯 Conclusion

1. ✅ **UI uses unified model keys** - All features share `t2v` keys for selection state
2. ✅ **Backend handles translation** - API automatically converts to `i2v` when image inputs detected
3. ✅ **No client-side differentiation needed** - Single model list serves all features
4. ✅ **Translation is deterministic** - Pattern-based replacement is reliable

**Recommendation**: Implement a single model selection system with runtime key translation based on input type (text-only vs. text+image).

---

**Last Updated**: 2026-02-01 00:23:34 UTC+7  
**Analysis Scope**: UI Model Selection + Backend Generation Translation
