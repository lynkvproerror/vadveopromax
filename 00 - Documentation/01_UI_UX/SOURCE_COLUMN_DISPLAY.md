# 📋 Source Column Display & Parsed Prompt Rows

**Version**: 1.0  
**Created**: 2026-02-03  
**Applies to**: TAB_02, TAB_03, TAB_05

---

## 1. Tab Applicability Matrix

| Tab | Has Image Source? | Source Column Display | PARSED Rows? |
|-----|-------------------|----------------------|--------------|
| TAB_01 (T2V) | ❌ No | N/A | ✅ Yes |
| TAB_02 (I2V) | ✅ Yes (Start/End) | 🖼️ Thumb / 🔗 Link | ✅ Yes |
| TAB_03 (R2V) | ✅ Yes (1-3 Ingredients) | 🖼️ Thumb / 🔗 Link | ✅ Yes |
| TAB_04 (T2I) | ❌ No | N/A | ✅ Yes |
| TAB_05 (I2I) | ✅ Yes (Source) | 🖼️ Thumb / 🔗 Link | ✅ Yes |

---

## 2. Source Column Display Types

### 2.1 Library Image (Thumbnail)

```
┌─────────────┐
│  [🖼️ img]   │  ← 32x32px thumbnail của ảnh từ Library
│  girl.jpg   │  ← Tag name (optional)
└─────────────┘
```

| Property | Value |
|----------|-------|
| Size | 32x32px (fixed) |
| Source | `Library/{tag}.jpg` |
| Click | → Show full image popup |
| Tooltip | Full path + resolution |

### 2.2 Continuation Frame (Link in Image Column)

```
┌─────────────┐
│   🔗←#3     │  ← Emoji + row reference (displayed in IMAGE column)
└─────────────┘
```

| Property | Value |
|----------|-------|
| Format | `🔗←#N` where N = source row |
| Display Location | **IMAGE column** (not CONT column) |
| Click | → Scroll to row N + highlight |
| Tooltip | "Continuation from Row #N" |
| Frame Source | Last video frame của row N |

#### Extraction State Transitions

| State | Display | Description |
|-------|---------|-------------|
| **Waiting** | `[🔗←#N]` | Previous video not complete |
| **Extracting** | `[🔄←#N]` | Frame extraction in progress |
| **Ready** | `[🖼️ thumbnail]` | Extracted frame thumbnail (32x32) |
| **Error** | `[⚠️←#N]` | Extraction failed |

```
State Flow:
[🔗←#1] → [🔄←#1] → [🖼️ cont_1.png] 
                  ↘ [⚠️←#1] (on error)
```

### 2.3 CONT Column (Checkbox Only)

```
┌─────┐
│  ✓  │  ← Checkbox enabled
└─────┘
┌─────┐
│  ☐  │  ← Checkbox disabled
└─────┘
```

| Property | Value |
|----------|-------|
| Format | `✓` / `☐` checkbox |
| Click | Toggle continuation on/off |
| Purpose | Enable/disable using previous row's output |

---

## 3. Per-Tab Column Specifications

### TAB_02 (Image-to-Video)

| Column | Name | Display |
|--------|------|---------|
| START | Start Frame | 🖼️ Thumb hoặc 🔗←#N |
| END | End Frame | 🖼️ Thumb hoặc 🔗←#N hoặc (none) |

**Display Logic:**
```python
def get_start_display(row):
    if row.continuation_enabled and row.prev_row:
        return f"🔗←#{row.prev_row.index}"
    elif row.start_tag:
        return Thumbnail(library.get_path(row.start_tag))
    else:
        return "(none)"

def get_end_display(row):
    if row.frame_mode in ["Start Only"]:
        return "(locked)"
    elif row.end_tag:
        return Thumbnail(library.get_path(row.end_tag))
    else:
        return "(none)"
```

### TAB_03 (Ingredients)

| Column | Name | Display |
|--------|------|---------|
| SLOT 1 | Ingredient 1 | 🖼️ Thumb hoặc 🔗←#N |
| SLOT 2 | Ingredient 2 | 🖼️ Thumb hoặc (none) |
| SLOT 3 | Ingredient 3 | 🖼️ Thumb hoặc (none) |

**Display Logic:**
```python
def get_slot_display(row, slot_index):
    if slot_index == 0 and row.continuation_enabled and row.prev_row:
        return f"🔗←#{row.prev_row.index}"  # CONT frame in slot 1
    elif row.tags[slot_index]:
        return Thumbnail(library.get_path(row.tags[slot_index]))
    else:
        return "(none)"
```

### TAB_05 (Image-to-Image)

| Column | Name | Display |
|--------|------|---------|
| SOURCE | Source Image | 🖼️ Thumb hoặc 🔗←#N |

**Display Logic:**
```python
def get_source_display(row):
    if row.continuation_enabled and row.prev_row:
        return f"🔗←#{row.prev_row.index}"
    elif row.source_tag:
        return Thumbnail(library.get_path(row.source_tag))
    else:
        return "⚠️ Missing"
```

---

## 4. PARSED Prompts → Separate Rows

### Input (Raw Bulk Prompt)

```
[girl] A beautiful girl dancing in the rain
She continues to dance gracefully
[sunset] The sunset over the ocean
```

### Output (PARSED Table)

| # | CONT | Prompt | START | END |
|---|------|--------|-------|-----|
| 1 | ⚪ | A beautiful girl dancing in the rain | [🖼️ girl] | - |
| 2 | 🔵 | She continues to dance gracefully | [🔗←#1] | - |
| 3 | ⚪ | The sunset over the ocean | [🖼️ sunset] | - |

### Parsing Rules

| Rule | Description |
|------|-------------|
| **1 line = 1 row** | Mỗi dòng prompt → 1 row trong table |
| **`[tag]` extraction** | Tag được trích xuất và hiển thị trong Source column |
| **CONT detection** | Row không có `[tag]` → auto-enable continuation |
| **Tag removal** | Tag được xóa khỏi prompt text trong column Prompt |

### Parse Flow

```python
def parse_bulk_prompts(raw_text: str) -> list[PromptRow]:
    rows = []
    lines = raw_text.strip().split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        
        # Extract tags
        tags = re.findall(r'\[([^\]]+)\]', line)
        
        # Clean prompt (remove tags)
        clean_prompt = re.sub(r'\[[^\]]+\]', '', line).strip()
        
        # Determine continuation
        has_tag = len(tags) > 0
        is_continuation = not has_tag and i > 0
        
        row = PromptRow(
            index=len(rows) + 1,
            prompt=clean_prompt,
            tags=tags,
            continuation_enabled=is_continuation,
            prev_row=rows[-1] if is_continuation else None
        )
        rows.append(row)
    
    return rows
```

---

## 5. Visual Examples

### Column Order (Updated)

```
# → IMAGE COLUMNS → PROMPT → CONT → ACTIONS
```

> **CONT column**: Shows `✓` / `☐` checkbox only  
> **Image column**: Shows `🔗←#N` link when continuation enabled

### Example 1: TAB_02 (I2V) Table

```
┌────┬────────────┬────────────┬─────────────────────────────┬──────┬──────────┐
│ #  │ START      │ END        │ Prompt                      │ CONT │ Actions  │
├────┼────────────┼────────────┼─────────────────────────────┼──────┼──────────┤
│ 1  │ [🖼️ girl]  │ -          │ Girl dancing in rain        │  ☐   │ [📝][🗑️]│
│ 2  │ [🔗←#1]    │ -          │ She spins around            │  ✓   │ [📝][🗑️]│
│ 3  │ [🔗←#2]    │ -          │ Camera zooms out            │  ✓   │ [📝][🗑️]│
│ 4  │ [🖼️sunset] │ [🖼️night]  │ Sunset transition           │  ☐   │ [📝][🗑️]│
│ 5  │ [🔗←#4]    │ -          │ Stars begin to appear       │  ✓   │ [📝][🗑️]│
└────┴────────────┴────────────┴─────────────────────────────┴──────┴──────────┘
```

### Example 2: TAB_03 (R2V) Table

```
┌────┬────────────┬────────────┬────────────┬─────────────────────────────┬──────┬──────────┐
│ #  │ SLOT 1     │ SLOT 2     │ SLOT 3     │ Prompt                      │ CONT │ Actions  │
├────┼────────────┼────────────┼────────────┼─────────────────────────────┼──────┼──────────┤
│ 1  │ [🖼️char]   │ [🖼️bg]     │ [🖼️style]  │ Character walks in scene   │  ☐   │ [📝][🗑️]│
│ 2  │ [🔗←#1]    │ [🖼️bg]     │ [🖼️style]  │ Character starts talking   │  ✓   │ [📝][🗑️]│
│ 3  │ [🖼️char2]  │ [🖼️bg2]    │ -          │ New character appears      │  ☐   │ [📝][🗑️]│
└────┴────────────┴────────────┴────────────┴─────────────────────────────┴──────┴──────────┘
```

### Example 3: TAB_01 (T2V) Table

```
┌────┬─────────────────────────────┬──────┬──────────┐
│ #  │ Prompt                      │ CONT │ Actions  │
├────┼─────────────────────────────┼──────┼──────────┤
│ 1  │ A cat playing piano         │  ☐   │ [📝][🗑️]│
│ 2  │ The cat starts dancing      │  ✓   │ [📝][🗑️]│
│ 3  │ Sunset over the ocean       │  ☐   │ [📝][🗑️]│
└────┴─────────────────────────────┴──────┴──────────┘
```

### Example 4: TAB_06 (Queue Manager) Table

```
┌────┬────────────┬─────────────────────────────┬──────┬──────────┬──────────┐
│ #  │ SOURCE     │ Prompt                      │ CONT │ Status   │ Actions  │
├────┼────────────┼─────────────────────────────┼──────┼──────────┼──────────┤
│ 1  │ [🖼️ hero]  │ Hero storms the castle      │  ☐   │ ✅ Done  │ [▶][🗑️] │
│ 2  │ [🔗←#1]    │ Walking through forest      │  ✓   │ 🔄 50%   │ [⏸][🗑️] │
│ 3  │ [🖼️villain]│ Villain appears             │  ☐   │ ⏳ Queue │ [▶][🗑️] │
└────┴────────────┴─────────────────────────────┴──────┴──────────┴──────────┘
```

---

## 6. Cross-References

| Document | Content |
|----------|---------|
| [IMAGE_LIBRARY_SYSTEM.md](IMAGE_LIBRARY_SYSTEM.md) | Tag detection & library structure |
| [BUTTON_ACTION_MAPPING.md](BUTTON_ACTION_MAPPING.md) | Button → API flow |
| [TAB_02_IMAGE_TO_VIDEO.md](TAB_02_IMAGE_TO_VIDEO.md) | Full TAB_02 spec |
| [TAB_03_INGREDIENTS.md](TAB_03_INGREDIENTS.md) | Full TAB_03 spec |
| [TAB_05_IMAGE_TO_IMAGE.md](TAB_05_IMAGE_TO_IMAGE.md) | Full TAB_05 spec |
