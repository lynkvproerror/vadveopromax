# ✏️ TAB_03: Ingredients-to-Video Workflow

## Tổng quan

Ingredients workflow cho phép kết hợp tối đa **3 hình ảnh** (character, background, style) với prompt để tạo video. Đây là chế độ nâng cao của I2V.

---

## 🎯 Main Workflow Diagram

```mermaid
flowchart TD
    subgraph UI["🖥️ UI LAYER"]
        A[📂 Import images với prefix] --> B[Auto-categorize by prefix]
        B --> C1[👤 char_* → Character]
        B --> C2[🏞️ bg_* → Background]
        B --> C3[🎨 style_* → Style]
        C1 --> D[Nhập prompts với multiple [tags]]
        C2 --> D
        C3 --> D
        D --> E[Click 📋 Parse]
        E --> F[Match up to 3 images/prompt]
        F --> G[Click 📋 Add to Queue]
    end

    subgraph Playwright["🔌 Playwright LAYER"]
        G --> H[For each prompt]
        H --> I[Upload image 1]
        I --> J[Upload image 2]
        J --> K[Upload image 3 - optional]
        K --> L[Set prompt]
        L --> M[Click Generate]
        M --> N{More prompts?}
        N -->|Yes| H
        N -->|No| O[Scan & Download]
    end

    style UI fill:#fff8e1
    style Playwright fill:#f3e5f5
```

---

## 📂 Auto-Categorization Rules

```mermaid
flowchart TD
    A[Scan library folder] --> B{Check filename prefix}
    B -->|char_*| C[👤 Character Category]
    B -->|bg_*| D[🏞️ Background Category]
    B -->|style_*| E[🎨 Style Category]
    B -->|other| F[📷 Uncategorized]
    
    C --> G[Display in category section]
    D --> G
    E --> G
    F --> G
```

| Prefix | Category | Icon | Example |
|--------|----------|------|---------|
| `char_` | Character | 👤 | `[char_hero].png` |
| `bg_` | Background | 🏞️ | `[bg_castle].jpg` |
| `style_` | Style | 🎨 | `[style_anime].webp` |
| (other) | Uncategorized | 📷 | `[random].png` |

---

## 📝 Multi-Tag Parsing

### Parse Logic

```mermaid
flowchart LR
    A["[char_hero] [bg_forest] [style_anime] Text..."] --> B[Extract all [tags]]
    B --> C[Take first 3 only]
    C --> D[Match each with library]
    D --> E[Create image list]
    E --> F[Store in ParsedPrompt]
```

**Code:**
```python
def parse_ingredients_prompt(prompt: str, library: dict) -> ParsedPrompt:
    tags = TAG_PATTERN.findall(prompt)
    clean = TAG_PATTERN.sub('', prompt).strip()
    
    matched = []
    missing = []
    
    # Max 3 images for Ingredients mode
    for tag in tags[:3]:
        key = tag.lower()
        if key in library:
            matched.append({
                "tag": tag,
                "path": library[key],
                "category": get_category(tag)  # char/bg/style/other
            })
        else:
            missing.append(f"[{tag}]")
    
    if len(tags) > 3:
        warnings = [f"[{t}]" for t in tags[3:]]
        # Log: "Extra tags ignored: {warnings}"
    
    return ParsedPrompt(
        raw=prompt,
        clean=clean,
        images=matched,
        missing=missing
    )
```

---

## 🔌 Playwright Multi-Image Upload

### Sequential Upload Flow

```mermaid
sequenceDiagram
    participant App as VEO App
    participant Slot1 as Image Slot 1
    participant Slot2 as Image Slot 2
    participant Slot3 as Image Slot 3
    participant Prompt as Prompt Input
    
    Note over App: Upload Image 1 (Character)
    App->>Slot1: processImageAndPromptOnPage(img1, "")
    Note right of Slot1: Empty prompt for intermediate uploads
    App->>App: Wait for upload complete
    
    Note over App: Upload Image 2 (Background)
    App->>Slot2: Find next Add Button
    App->>Slot2: processImageUpload(img2)
    App->>App: Wait for upload complete
    
    Note over App: Upload Image 3 (Style) - Optional
    alt Has 3rd image
        App->>Slot3: Find next Add Button
        App->>Slot3: processImageUpload(img3)
        App->>App: Wait for upload complete
    end
    
    Note over App: Set prompt and generate
    App->>Prompt: Set prompt text
    App->>Prompt: Click Generate
```

---

### Each Image Upload (Same as TAB_02)

| Step | Action | Wait Time |
|------|--------|-----------|
| 1 | Poll for Add Button | 500ms × 360 = 180s max |
| 2 | Click Add Button | 2s |
| 3 | Poll for file input | 250ms × 40 = 10s max |
| 4 | Create File from base64 | - |
| 5 | Inject via DataTransfer | - |
| 6 | Wait spinner gone | 500ms × 360 = 180s max |
| 7 | Select crop ratio | 500ms |
| 8 | Click Crop & Save | 1s |

---

## 📊 Timing Estimation

| Scenario | Images | Est. Time per Prompt |
|----------|--------|---------------------|
| Character only | 1 | ~15-20s |
| Char + Background | 2 | ~25-35s |
| Char + BG + Style | 3 | ~35-50s |

**Total for 10 prompts × 3 images:**
- Upload time: ~350-500s (~6-8 min)
- Generation time: ~2-5 min per prompt
- Total: ~30-60 min

---

## ⚠️ VEO Ingredients Mode Specifics

VEO Flow có chế độ Ingredients riêng với 3 slot:

```
┌─────────────────────────────────────────────┐
│ VEO INGREDIENTS MODE                        │
├─────────────────────────────────────────────┤
│ [SUBJECT] + [SCENE] + [STYLE]               │
│ ┌───────┐   ┌───────┐   ┌───────┐           │
│ │  👤   │ + │  🏞️   │ + │  🎨   │ → 🎬     │
│ │ hero  │   │ forest│   │ anime │           │
│ └───────┘   └───────┘   └───────┘           │
│                                             │
│ [Prompt: The hero walks through forest...] │
└─────────────────────────────────────────────┘
```

**Mode Detection:**
```python
# Check if VEO is in Ingredients mode
INGREDIENTS_MODE_XPATH = "//div[contains(@class, 'ingredients') or .//*[contains(text(), 'Subject')]]"

# Slot identifiers
SLOT_SUBJECT_XPATH = "//div[contains(@class, 'subject-slot')]"
SLOT_SCENE_XPATH = "//div[contains(@class, 'scene-slot')]"
SLOT_STYLE_XPATH = "//div[contains(@class, 'style-slot')]"
```

---

## 🔄 continuation Mode Behavior

Ingredients mode giữ nguyên library images khi dùng continuation:

```mermaid
flowchart TD
    A{continuation enabled?} -->|No| B[Use all 3 user images from library]
    A -->|Yes| C[Extract frame from prev video]
    C --> D[Insert frame as SLOT 1]
    D --> E[Keep up to 2 remaining library images]
    E --> F[Total: max 3 images - 1 cont + 2 library]
```

> ✅ **Behavior**: Khi continuation ON:
> - Extracted frame → Slot 1 (Subject/Character position)
> - Remaining library images (max 2) → Slot 2, 3
> - Tổng: max 3 images = 1 cont frame + 2 library images
> - Ví dụ: `[cont_frame] + [bg_castle] + [style_anime]`

---

## ❌ Error Handling

| Error | Scope | Action |
|-------|-------|--------|
| POLICY_IMAGE (slot 1) | First image | Mark failed, skip entire prompt |
| POLICY_IMAGE (slot 2/3) | Subsequent | Log warning, continue without that image |
| QUEUE_FULL | After generate | Retry loop (30x) |
| TAG_NOT_FOUND | Parse time | Show warning, allow queue with partial |

---

## 🔗 Related Files

| File | Description |
|------|-------------|
| [TAB_03_INGREDIENTS.md](../01_UI_UX/TAB_03_INGREDIENTS.md) | UI Layout & Widgets |
| [WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md](./WORKFLOW_TAB_02_IMAGE_TO_VIDEO.md) | Single image upload flow |
