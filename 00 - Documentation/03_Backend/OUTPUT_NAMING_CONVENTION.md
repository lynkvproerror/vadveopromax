# 📝 Output Naming Convention

**Location**: `03_Backend/OUTPUT_NAMING_CONVENTION.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-03

---

## 1. Overview

Quy tắc đặt tên file output để tổ chức và dễ tìm kiếm.

---

## 2. Naming Templates

### 2.1 Video Output

**Template:**
```
{task}_{row}_{output}_{quality}_{timestamp}.mp4
```

**Example:**
```
Nature_Scenes_001_01_1080p_20260203_153045.mp4
Nature_Scenes_001_02_1080p_20260203_153045.mp4
Nature_Scenes_002_01_4K_20260203_153112.mp4
```

### 2.2 Image Output

**Template:**
```
{task}_{row}_{output}_{timestamp}.png
```

**Example:**
```
Logo_Design_001_01_20260203_153045.png
Logo_Design_001_02_20260203_153046.png
```

### 2.3 Continuation Frame

**Template:**
```
cont_{source_row}_{timestamp}.png
```

**Example:**
```
cont_001_20260203_153045.png
cont_002_20260203_153112.png
```

---

## 3. Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{task}` | Task/Project name (sanitized) | `Nature_Scenes` |
| `{row}` | Row number (3 digits) | `001`, `012` |
| `{output}` | Output index (2 digits) | `01`, `02` |
| `{quality}` | Resolution | `720p`, `1080p`, `4K` |
| `{timestamp}` | YYYYMMDD_HHMMSS | `20260203_153045` |
| `{model}` | AI model | `veo3.1`, `imagen` |
| `{mode}` | Generation mode | `t2v`, `i2v`, `r2v` |

---

## 4. Folder Structure

```
Output/
├── Task_Name_1/
│   ├── videos/
│   │   ├── Task_Name_1_001_01_1080p_20260203_153045.mp4
│   │   ├── Task_Name_1_001_02_1080p_20260203_153046.mp4
│   │   └── ...
│   ├── images/
│   │   └── ...
│   └── frames/
│       ├── cont_001_20260203_153045.png
│       └── ...
├── Task_Name_2/
│   └── ...
└── _temp/
    └── (temporary files)
```

---

## 5. Name Sanitization

### 5.1 Rules

| Character | Replacement |
|-----------|-------------|
| Space ` ` | Underscore `_` |
| `/` `\` | Underscore `_` |
| `:` `*` `?` `"` `<` `>` `\|` | Remove |
| Multiple `_` | Single `_` |
| Leading/trailing `_` | Remove |

### 5.2 Implementation

```python
import re
from datetime import datetime

class FileNamer:
    """Generate standardized output filenames."""
    
    ILLEGAL_CHARS = r'[<>:"/\\|?*]'
    
    @staticmethod
    def sanitize(name: str) -> str:
        """Sanitize name for filesystem."""
        # Remove illegal characters
        name = re.sub(FileNamer.ILLEGAL_CHARS, '', name)
        # Replace spaces with underscore
        name = name.replace(' ', '_')
        # Collapse multiple underscores
        name = re.sub(r'_+', '_', name)
        # Remove leading/trailing underscores
        name = name.strip('_')
        return name
    
    @staticmethod
    def get_timestamp() -> str:
        """Get current timestamp string."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    @classmethod
    def video_name(
        cls,
        task: str,
        row: int,
        output_index: int,
        quality: str = "1080p"
    ) -> str:
        """Generate video filename."""
        task_safe = cls.sanitize(task)
        timestamp = cls.get_timestamp()
        return f"{task_safe}_{row:03d}_{output_index:02d}_{quality}_{timestamp}.mp4"
    
    @classmethod
    def image_name(
        cls,
        task: str,
        row: int,
        output_index: int
    ) -> str:
        """Generate image filename."""
        task_safe = cls.sanitize(task)
        timestamp = cls.get_timestamp()
        return f"{task_safe}_{row:03d}_{output_index:02d}_{timestamp}.png"
    
    @classmethod
    def continuation_frame_name(cls, source_row: int) -> str:
        """Generate continuation frame filename."""
        timestamp = cls.get_timestamp()
        return f"cont_{source_row:03d}_{timestamp}.png"
```

---

## 6. Settings (TAB_07)

### 6.1 Naming Options

| Setting | Values | Default |
|---------|--------|---------|
| `include_timestamp` | On/Off | On |
| `include_quality` | On/Off | On |
| `include_model` | On/Off | Off |
| `row_digits` | 2/3/4 | 3 |
| `separator` | `_` / `-` / `.` | `_` |

### 6.2 Custom Template

```
Template: {task}_{row}_{output}_{quality}
Preview:  My_Project_001_01_1080p.mp4
```

---

## 7. Conflict Resolution

| Scenario | Action |
|----------|--------|
| File exists | Append `_v2`, `_v3`, etc. |
| Same timestamp | Add milliseconds |
| Name too long | Truncate task name |

```python
def resolve_conflict(path: Path) -> Path:
    """Resolve filename conflicts."""
    if not path.exists():
        return path
    
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    
    version = 2
    while True:
        new_path = parent / f"{stem}_v{version}{suffix}"
        if not new_path.exists():
            return new_path
        version += 1
```

---

## Cross-References

- [DOWNLOAD_MANAGER.md](./DOWNLOAD_MANAGER.md) - Uses naming for saves
- [TAB_07_SETTINGS.md](../01_UI_UX/TAB_07_SETTINGS.md) - Naming settings UI
