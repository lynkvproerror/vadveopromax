# 🔗 Button → API Action Mapping

**Version**: 1.0  
**Created**: 2026-02-03  
**Source**: Research/reference/ + F12 Dev HAR analysis

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                    VEO PRO MAX CLIENT                               │
├────────────────────────────────────────────────────────────────────┤
│  UI BUTTON → TRIGGER → BUILD PAYLOAD → CALL API → POLL → DOWNLOAD │
│                                                                     │
│  ┌──────────┐   ┌───────────────┐   ┌─────────────────────────────┐│
│  │ TAB_01   │   │               │   │ API Layer                   ││
│  │ TAB_02   │──▶│ Queue Manager │──▶│ • CMD_UPLOAD_IMAGE          ││
│  │ TAB_03   │   │ (Dispatch)    │   │ • CMD_GENERATE_VIDEO/IMAGE  ││
│  │ TAB_04   │   │               │   │ • CMD_CHECK_STATUS (Poll)   ││
│  │ TAB_05   │   └───────────────┘   │ • CMD_UPSCALE               ││
│  └──────────┘                       │ • CMD_DOWNLOAD              ││
│                                     └─────────────────────────────┘│
└────────────────────────────────────────────────────────────────────┘
```

---

## 1. Sidebar → Workspace Interaction

| Sidebar Action | Workspace Effect | Data Flow |
|----------------|------------------|-----------|
| Change Aspect Ratio | Update all prompts' aspect | Sidebar → Table rows |
| Change Model | Update generation model | Sidebar → Queue config |
| Change Output Count | Update batch size | Sidebar → Queue config |
| Import Bulk Prompts | Parse & populate table | File → Prompt Parser → Table |
| Clear All | Reset workspace | N/A |

---

## 2. Generation Tabs - Button → API Mapping

### TAB_01: Text-to-Video

| Button | UI Action | API Flow | Reference |
|--------|-----------|----------|-----------|
| `[📋 Add to Queue]` | Add prompt row to queue | → Queue (no API yet) | - |
| `[▶️ Generate]` | Start T2V generation | → **Flow 1: T2V** | See below |
| `[🗑️ Clear]` | Remove prompt | N/A | - |

**Flow 1: T2V**
```
Collect UI values → Get reCAPTCHA → 
POST /v1/video:batchAsyncGenerateVideoText →
Poll status → Download 720p
```

---

### TAB_02: Image-to-Video

| Button | UI Action | API Flow | Image Source |
|--------|-----------|----------|--------------|
| `[📋 Add to Queue]` | Add I2V prompt | → Queue | - |
| `[▶️ Generate]` | Start I2V/F2V | → **Flow 2/3** | Library `[tag]` |
| `[📂 Manage Images]` | Open Library Manager | N/A | - |

**Flow 2: I2V (Start Only)**
```
Extract [tag] → Get image from Library → 
POST /v1:uploadUserImage → Get mediaId →
Get reCAPTCHA →
POST /v1/video:batchAsyncGenerateVideoStartImage →
Poll → Download
```

**Flow 3: F2V (Start + End)**
```
Extract [tag1], [tag2] → Get images from Library →
POST /v1:uploadUserImage x2 → Get mediaId x2 →
Get reCAPTCHA →
POST /v1/video:batchAsyncGenerateVideoStartAndEndImage →
Poll → Download
```

---

### TAB_03: Ingredients (R2V)

| Button | UI Action | API Flow | Image Source |
|--------|-----------|----------|--------------|
| `[📋 Add to Queue]` | Add R2V prompt | → Queue | - |
| `[▶️ Generate]` | Start R2V | → **Flow 4** | Library `[tag1][tag2][tag3]` |

**Flow 4: R2V (1-3 References)**
```
Extract [tag1], [tag2], [tag3] → Get images from Library →
POST /v1:uploadUserImage x1-3 → Get mediaId array →
Get reCAPTCHA →
POST /v1/video:batchAsyncGenerateVideoReferenceImages →
Poll → Download
```

---

### TAB_04: Text-to-Image

| Button | UI Action | API Flow | Notes |
|--------|-----------|----------|-------|
| `[📋 Add to Queue]` | Add T2I prompt | → Queue | - |
| `[▶️ Generate]` | Start T2I | → **Flow 5** | Sync response |

**Flow 5: T2I (Synchronous)**
```
Collect prompt → Get reCAPTCHA →
POST /v1/projects/{id}/flowMedia:batchGenerateImages →
Immediate response with fifeUrl → Download
```

---

### TAB_05: Image-to-Image

| Button | UI Action | API Flow | Image Source |
|--------|-----------|----------|--------------|
| `[📋 Add to Queue]` | Add I2I prompt | → Queue | - |
| `[▶️ Generate]` | Start I2I | → **Flow 6** | Library `[tag]` |

**Flow 6: I2I (Image Modification)**
```
Extract [tag] → Get image from Library →
POST /v1:uploadUserImage → Get mediaId →
Get reCAPTCHA →
POST /v1/projects/{id}/flowMedia:batchGenerateImages 
  (with imageInputs[].mediaId) →
Immediate response → Download
```

---

## 3. Queue Manager - Button → Dispatch Logic

### Task Header Buttons

| Button | Action | Dispatch Logic |
|--------|--------|----------------|
| `[▶️ Start Task]` | Process all prompts | Loop: Determine mode → Route to Flow 1-6 |
| `[⏸️ Pause Task]` | Pause processing | Stop dispatch loop |
| `[🗑️ Delete Task]` | Remove task | Remove from queue |
| `[🔄 Retry All]` | Retry failed | Re-dispatch failed prompts |

### Per-Prompt Buttons

| Button | Visibility | Action |
|--------|------------|--------|
| `[📝]` | Always | Edit prompt text |
| `[🔄]` | Failed/Edited | Re-dispatch this prompt |
| `[📋]` | Failed | View error log |

### Dispatch Logic

```python
def dispatch_prompt(prompt: PromptRow):
    """Route prompt to correct API flow based on tab/mode."""
    
    mode = prompt.mode
    
    if mode == "T2V":
        return await flow_1_t2v(prompt)
    elif mode == "I2V":
        if prompt.has_end_frame:
            return await flow_3_f2v(prompt)  # Start + End
        else:
            return await flow_2_i2v(prompt)  # Start only
    elif mode == "R2V":
        return await flow_4_r2v(prompt)
    elif mode == "T2I":
        return await flow_5_t2i(prompt)
    elif mode == "I2I":
        return await flow_6_i2i(prompt)
```

---

## 4. Quality Selection (Integrated - No Separate Buttons)

> **Design**: Quality selection trong Sidebar → Upscale tự động khi download.  
> **KHÔNG có button upscale riêng biệt.**

### Video Quality (Sidebar Dropdown)

| Selection | Generation | Post-Process | Download |
|-----------|------------|--------------|----------|
| **720p** | Generate 720p | None | Direct download |
| **1080p** | Generate 720p | Auto-upscale | → Flow 7 → Download |
| **4K** | Generate 720p | Auto-upscale | → Flow 7 → Download |

**Flow 7: Auto Video Upscale (Internal)**
```
If quality > 720p:
  Get video mediaId → Get reCAPTCHA →
  POST /v1/video:batchAsyncGenerateVideoUpsampleVideo →
  Poll → Download upscaled video
Else:
  Direct download 720p
```

### Image Resolution (Sidebar Dropdown)

| Selection | Generation | Post-Process | Download |
|-----------|------------|--------------|----------|
| **1K** | Generate 1K | None | Direct download |
| **2K** | Generate 1K | Auto-upscale | → Flow 8 → Download |
| **4K** | Generate 1K | Auto-upscale | → Flow 8 → Download |

**Flow 8: Auto Image Upscale (Internal)**
```
If resolution > 1K:
  Get image mediaId → Get reCAPTCHA →
  POST /v1/flow/upsampleImage →
  Poll → Download upscaled image
Else:
  Direct download 1K
```

---

## 5. reCAPTCHA Requirement Matrix

| Operation | reCAPTCHA Required |
|-----------|-------------------|
| Upload Image | ❌ NO |
| Generate Video (all) | ✅ YES |
| Generate Image (T2I/I2I) | ✅ YES |
| Auto-Upscale Video (if >720p) | ✅ YES |
| Auto-Upscale Image (if >1K) | ✅ YES |
| Poll Status | ❌ NO |
| Download | ❌ NO |

---

## 6. Error Handling Button Actions

| Error | Button Shown | Action |
|-------|--------------|--------|
| 401 Token Expired | `[🔑 Re-login]` | Refresh token via Playwright |
| 403 reCAPTCHA Fail | Auto-retry | Get new token + retry |
| 404 Media Not Found | `[🔄 Retry]` | Re-upload + retry |
| 429 Rate Limit | Auto-wait | Wait Retry-After + retry |
| 500 Server Error | `[🔄 Retry]` | Wait 30s + retry (max 3) |

---

## Cross-References

| Document | Content |
|----------|---------|
| [UI_TO_API_PARAMETER_MAPPING.md](../02_Architecture/UI_TO_API_PARAMETER_MAPPING.md) | Detailed payload building |
| [IMAGE_LIBRARY_SYSTEM.md](IMAGE_LIBRARY_SYSTEM.md) | `[tag]` detection logic |
