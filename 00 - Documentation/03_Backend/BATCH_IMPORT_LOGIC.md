# 📋 Batch Import Logic

**Location**: `03_Backend/BATCH_IMPORT_LOGIC.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-03

---

## 1. Overview

Batch Import cho phép import prompts từ file TXT/CSV vào các TAB generation.

---

## 2. Supported Formats

### 2.1 Plain TXT

**Format:** Một prompt mỗi dòng

```txt
A cat playing piano in a jazz club
A dog surfing on ocean waves at sunset
A robot dancing in the rain
```

### 2.2 TXT with Image Tags

**Format:** `prompt [tag1] [tag2]`

```txt
A hero storms the castle [char_hero] [bg_castle]
Walking through forest at dusk [char_hero] [bg_forest]
The villain watches from tower [char_villain] [bg_city]
```

### 2.3 TXT with Continuation Markers

**Format:** `>>` prefix for continuation

```txt
Girl dancing in the rain [img_girl]
>> She spins around gracefully
>> Camera zooms out to show city
New scene at sunset [img_sunset]
>> Stars begin to appear
```

### 2.4 CSV Format

**Columns:** `prompt`, `image1`, `image2`, `image3`, `continuation`

```csv
prompt,image1,image2,image3,continuation
"Hero storms the castle",char_hero,bg_castle,,false
"Walking through forest",char_hero,bg_forest,,true
"Villain watches",char_villain,bg_city,,false
```

---

## 3. Parsing Rules

### 3.1 Image Tag Detection

| Pattern | Description | Example |
|---------|-------------|---------|
| `[tag_name]` | Square brackets | `[char_hero]` |
| `{tag_name}` | Curly brackets | `{bg_forest}` |
| `@tag_name` | At symbol | `@style_anime` |

### 3.2 Continuation Detection

| Pattern | Meaning | Example |
|---------|---------|---------|
| `>>` prefix | Continue from previous | `>> She spins` |
| `→` prefix | Continue from previous | `→ Camera zooms` |
| `CONT:` prefix | Continue from previous | `CONT: Next scene` |
| `[CONT]` tag | Enable continuation | `Dancing [CONT]` |

### 3.3 Comment Lines

| Pattern | Meaning |
|---------|---------|
| `#` prefix | Comment, skip line |
| `//` prefix | Comment, skip line |
| Empty line | Skip |

---

## 4. Implementation

### 4.1 Batch Parser

```python
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class ParsedPrompt:
    text: str
    images: list[str]
    continuation: bool
    line_number: int

class BatchParser:
    """Parse batch import files."""
    
    # Patterns
    IMAGE_PATTERN = re.compile(r'\[([^\]]+)\]|\{([^\}]+)\}|@(\w+)')
    CONTINUATION_MARKERS = ['>> ', '→ ', 'CONT: ']
    COMMENT_MARKERS = ['#', '//']
    
    def parse_txt(self, file_path: str) -> list[ParsedPrompt]:
        """Parse TXT file into prompts."""
        prompts = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or self._is_comment(line):
                    continue
                
                # Check for continuation
                is_continuation = self._is_continuation(line)
                if is_continuation:
                    line = self._strip_continuation_marker(line)
                
                # Extract image tags
                images = self._extract_images(line)
                prompt_text = self._clean_prompt(line)
                
                prompts.append(ParsedPrompt(
                    text=prompt_text,
                    images=images,
                    continuation=is_continuation,
                    line_number=line_num
                ))
        
        return prompts
    
    def parse_csv(self, file_path: str) -> list[ParsedPrompt]:
        """Parse CSV file into prompts."""
        import csv
        prompts = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for line_num, row in enumerate(reader, 2):  # Start at 2 (header is 1)
                # Get images from columns
                images = []
                for col in ['image1', 'image2', 'image3']:
                    if col in row and row[col]:
                        images.append(row[col])
                
                # Check continuation
                cont = row.get('continuation', '').lower() in ['true', '1', 'yes']
                
                prompts.append(ParsedPrompt(
                    text=row['prompt'],
                    images=images,
                    continuation=cont,
                    line_number=line_num
                ))
        
        return prompts
    
    def _is_comment(self, line: str) -> bool:
        return any(line.startswith(m) for m in self.COMMENT_MARKERS)
    
    def _is_continuation(self, line: str) -> bool:
        # Check for [CONT] tag
        if '[CONT]' in line.upper():
            return True
        return any(line.startswith(m) for m in self.CONTINUATION_MARKERS)
    
    def _strip_continuation_marker(self, line: str) -> str:
        for marker in self.CONTINUATION_MARKERS:
            if line.startswith(marker):
                return line[len(marker):]
        return line.replace('[CONT]', '').replace('[cont]', '')
    
    def _extract_images(self, line: str) -> list[str]:
        """Extract image tags from line."""
        images = []
        for match in self.IMAGE_PATTERN.finditer(line):
            # Get whichever group matched
            tag = match.group(1) or match.group(2) or match.group(3)
            if tag:
                images.append(tag)
        return images
    
    def _clean_prompt(self, line: str) -> str:
        """Remove image tags from prompt text."""
        clean = self.IMAGE_PATTERN.sub('', line)
        # Clean up extra spaces
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
```

### 4.2 Validation

```python
class ImportValidator:
    """Validate imported prompts before adding to queue."""
    
    MAX_PROMPT_LENGTH = 1000
    
    def __init__(self, image_library):
        self.library = image_library
    
    def validate(self, prompts: list[ParsedPrompt]) -> list[dict]:
        """
        Validate prompts and return issues.
        
        Returns:
            List of {"line": int, "issue": str, "severity": str}
        """
        issues = []
        
        for prompt in prompts:
            # Check prompt length
            if len(prompt.text) > self.MAX_PROMPT_LENGTH:
                issues.append({
                    "line": prompt.line_number,
                    "issue": f"Prompt too long ({len(prompt.text)} chars)",
                    "severity": "error"
                })
            
            # Check image tags exist
            for tag in prompt.images:
                if not self.library.exists(tag):
                    issues.append({
                        "line": prompt.line_number,
                        "issue": f"Image tag not found: [{tag}]",
                        "severity": "warning"
                    })
            
            # Check continuation logic
            if prompt.continuation and prompt.line_number == 1:
                issues.append({
                    "line": prompt.line_number,
                    "issue": "First prompt cannot be continuation",
                    "severity": "error"
                })
        
        return issues
```

---

## 5. UI Import Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      IMPORT FLOW                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐                                                │
│  │ [📥 Import]  │                                                │
│  │ Button Click │                                                │
│  └──────┬───────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐                                                │
│  │ File Picker  │                                                │
│  │ (.txt, .csv) │                                                │
│  └──────┬───────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐     ┌──────────────┐                          │
│  │ Parse File   │────►│ Validate     │                          │
│  │              │     │ Prompts      │                          │
│  └──────────────┘     └──────┬───────┘                          │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│  │ No Issues    │     │ Warnings     │     │ Errors       │     │
│  │ → Import     │     │ → Show List  │     │ → Show List  │     │
│  │              │     │ → Ask Cont.  │     │ → Block      │     │
│  └──────────────┘     └──────────────┘     └──────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.1 Import Preview Dialog

```
┌─────────────────────────────────────────────────────────────────┐
│ 📥 IMPORT PREVIEW                                           [X] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ File: prompts_batch_001.txt                                      │
│ Prompts found: 25                                                │
│ With images: 18                                                  │
│ Continuations: 7                                                 │
│                                                                  │
│ ┌── Issues (2) ──────────────────────────────────────────────┐  │
│ │ ⚠️ Line 5: Image tag not found [bg_mountains]              │  │
│ │ ⚠️ Line 12: Image tag not found [char_old]                 │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌── Preview ─────────────────────────────────────────────────┐  │
│ │ 1. A hero storms the castle [char_hero] [bg_castle]        │  │
│ │ 2. >> Walking through forest [char_hero]                   │  │
│ │ 3. >> Camera zooms out to show valley                      │  │
│ │ ...                                                        │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ [ ] Replace existing prompts                                     │
│ [✓] Auto-detect continuations                                    │
│                                                                  │
│ [Cancel]                            [Import 25 Prompts]          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. TAB-Specific Import Rules

| TAB | Image Columns | Max Images | Continuation |
|-----|---------------|------------|--------------|
| TAB_01 (T2V) | None | 0 | ✅ Yes |
| TAB_02 (I2V) | START, END | 2 | ✅ Yes |
| TAB_03 (R2V) | SLOT 1-3 | 3 | ✅ Yes |
| TAB_04 (T2I) | None | 0 | ❌ No |
| TAB_05 (I2I) | SOURCE | 1 | ❌ No |

---

## Cross-References

- [SOURCE_COLUMN_DISPLAY.md](../01_UI_UX/SOURCE_COLUMN_DISPLAY.md) - Image tag display
- [IMAGE_LIBRARY_SYSTEM.md](../01_UI_UX/IMAGE_LIBRARY_SYSTEM.md) - Tag validation
- [TAB_02_IMAGE_TO_VIDEO.md](../01_UI_UX/TAB_02_IMAGE_TO_VIDEO.md) - Import for I2V
