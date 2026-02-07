# 🔄 Tab: Image-to-Image (I2I)

> **Framework**: PySide6 (Qt6)  
> **Reference**: [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md)  
> **Version**: 3.0 - PySide6 Migration

---

## 🗂️ Tab Menu

| Tab | Display Name | Key |
|-----|--------------|-----|
| 01 | [Text to Video](./TAB_01_TEXT_TO_VIDEO.md) | `t2v` |
| 02 | [Image to Video](./TAB_02_IMAGE_TO_VIDEO.md) | `i2v` |
| 03 | [Ingredients to Video](./TAB_03_INGREDIENTS.md) | `r2v` |
| 04 | [Text to Image](./TAB_04_TEXT_TO_IMAGE.md) | `t2i` |
| **→ 05** | **Image to Image** | `i2i` |
| 06 | [Queue](./TAB_06_QUEUE_MANAGER.md) | `queue` |
| 07 | [Settings](./TAB_07_SETTINGS.md) | `settings` |
| 08 | [License](./TAB_08_LICENSE.md) | `license` |
| 09 | [About](./TAB_09_ABOUT.md) | `about` |
| 10 | [Dev Console](./TAB_10_DEV_CONSOLE.md) | `dev` (hidden) |

---

**Mode Index**: `4` (`imageToImage`)  
**Accent Color**: Purple (`#8B5CF6`) - Image generation tabs  
**IMAGE SOURCE**: From Library `[tag]` or Continuation  
**Model**: Banana Bro / Banana Pro

---

## 🎨 Layout

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │ Text to Video │ Image to Video │ Ingredients │ Text to Image │[Image to Image]│ Queue │ Settings │ License │ About │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│   SIDEBAR (260px)          │   WORKSPACE (QSplitter flex)                                       │
├────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 📁 Project Name            │ ┌─────────────────────────────────────────────────────────────────┐ │
│ [QLineEdit              ]  │ │ 📝 PROMPT INPUT (QGroupBox)                                     │ │
│ 📂 Output Folder           │ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ [QLineEdit] [Browse]       │ │ │ QTextEdit with [source_tag] + modification prompt           │ │ │
│ 📐 Aspect Ratio            │ │ │ [portrait] Add cinematic color grading                      │ │ │
│ [QComboBox          ▼   ]  │ │ │ [landscape] Transform to watercolor painting                │ │ │
│ 🎬 Images/Prompt           │ │ └─────────────────────────────────────────────────────────────┘ │ │
│ [QComboBox          ▼   ]  │ │ [QPushButton Import] [QPushButton Clear]                       │ │
│ 🤖 AI Model                │ └─────────────────────────────────────────────────────────────────┘ │
│ [QComboBox          ▼   ]  │ ┌─────────────────────────────────────────────────────────────────┐ │
│ 🖼️ Quality                 │ │ 📊 PARSED PROMPTS (QGroupBox)                                  │ │
│ [QComboBox          ▼   ]  │ │ QTableWidget: # │ Source │ Modification │ CONT │ Actions       │ │
│ ─────────────────────────  │ └─────────────────────────────────────────────────────────────────┘ │
│ [📂 Manage Library]        │                                                                    │
│ 📊 Queue: 0 pending        │                                                                    │
│ [QPushButton Add to Queue] │                                                                    │
├────────────────────────────┴────────────────────────────────────────────────────────────────────┤
│ QStatusBar                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Widget Specifications

### Sidebar (260px fixed)

| Widget | Type | Properties |
|--------|------|------------|
| `project_name` | `QLineEdit` | Placeholder: "I2I-Project-{N}" |
| `output_folder` | `QLineEdit` + `QPushButton` | Folder picker |
| `aspect_ratio` | `QComboBox` | ["16:9", "9:16", "1:1 (Square)"] |
| `images_per_prompt` | `QComboBox` | ["1 image" - "4 images"] |
| `model` | `QComboBox` | ["Banana Bro", "Banana Pro"] |
| `quality` | `QComboBox` | ["2K", "4K"] |
| `manage_library_btn` | `QPushButton` | Opens Library Manager |
| `add_queue_btn` | `QPushButton` | "📋 Add to Queue" |

---

## 🖼️ Image Source

### Source Priority

| Priority | Source | Condition |
|----------|--------|-----------|
| 1 | **Continuation** | CONT enabled → Use previous output |
| 2 | **Library Tag** | First `[tag]` in prompt → Auto-match |

### Per-Row Detection

| Prompt | Source Image |
|--------|--------------|
| `[portrait] Make dramatic` | `[portrait].png` |
| `[landscape] Add storm` | `[landscape].png` |

---

## 🔧 Code Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Qt

class ImageToImageTab(QWidget):
    """Tab 5: Image-to-Image editing/transformation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        splitter.addWidget(self.create_sidebar())
        splitter.addWidget(self.create_workspace())
        splitter.setSizes([260, 800])
    
    def create_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setSpacing(12)
        
        layout.addWidget(QLabel("📁 Project Name"))
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("I2I-Project-01")
        layout.addWidget(self.project_name)
        
        layout.addWidget(QLabel("📂 Output Folder"))
        folder_layout = QHBoxLayout()
        self.output_folder = QLineEdit()
        self.browse_btn = QPushButton("Browse...")
        folder_layout.addWidget(self.output_folder)
        folder_layout.addWidget(self.browse_btn)
        layout.addLayout(folder_layout)
        
        for label, widget_name, items in [
            ("📐 Aspect Ratio", "aspect_ratio", ["16:9", "9:16", "1:1 (Square)"]),
            ("🎬 Images/Prompt", "images_per_prompt", ["1 image", "2 images", "3 images", "4 images"]),
            ("🤖 AI Model", "model", ["Banana Bro", "Banana Pro"]),
            ("🖼️ Quality", "quality", ["2K", "4K"]),
        ]:
            layout.addWidget(QLabel(label))
            combo = QComboBox()
            combo.addItems(items)
            setattr(self, widget_name, combo)
            layout.addWidget(combo)
        
        layout.addWidget(self.create_separator())
        self.library_btn = QPushButton("📂 Manage Library")
        layout.addWidget(self.library_btn)
        
        self.queue_status = QLabel("📊 Queue: 0 pending")
        layout.addWidget(self.queue_status)
        
        self.add_queue_btn = QPushButton("📋 Add to Queue")
        layout.addWidget(self.add_queue_btn)
        
        layout.addStretch()
        return sidebar
    
    def create_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setSpacing(12)
        
        prompt_group = QGroupBox("📝 PROMPT INPUT")
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "[source_tag] Modification prompt\n"
            "[portrait] Add cinematic color grading"
        )
        self.prompt_input.setMinimumHeight(120)
        prompt_layout.addWidget(self.prompt_input)
        
        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("📥 Import TXT")
        self.clear_btn = QPushButton("🗑️ Clear")
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        prompt_layout.addLayout(btn_layout)
        
        layout.addWidget(prompt_group)
        
        parsed_group = QGroupBox("📊 PARSED PROMPTS")
        parsed_layout = QVBoxLayout(parsed_group)
        self.prompts_table = QTableWidget()
        self.prompts_table.setColumnCount(5)
        self.prompts_table.setHorizontalHeaderLabels(["#", "Source", "Modification", "CONT", "Actions"])
        self.prompts_table.horizontalHeader().setStretchLastSection(True)
        parsed_layout.addWidget(self.prompts_table)
        
        layout.addWidget(parsed_group, stretch=1)
        
        return workspace
    
    def create_separator(self) -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #45475a;")
        return sep
```

---

## 🔗 Continuation Mode

When **CONT** enabled:
- Source image = Previous output
- Modification applies to previous result
- Creates iterative editing chains

---

## 🪟 Popups

| Popup | Trigger | PySide6 Widget |
|-------|---------|----------------|
| Edit Prompt | Click `[✏]` | `QDialog` |
| Image Library | Click `[Manage Library]` | `QDialog` |
| Folder Picker | Click `[Browse]` | `QFileDialog.getExistingDirectory()` |
| Confirm Dialog | Delete | `QMessageBox.question()` |

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system |
| [IMAGE_LIBRARY_SYSTEM.md](IMAGE_LIBRARY_SYSTEM.md) | Library specs |

---

**Status**: ✅ Migrated to PySide6
