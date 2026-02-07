# 🧪 Tab: Ingredients-to-Video

> **Framework**: PySide6 (Qt6)  
> **Reference**: [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md)  
> **Version**: 3.0 - PySide6 Migration

---

## 🗂️ Tab Menu

| Tab | Display Name | Key |
|-----|--------------|-----|
| 01 | [Text to Video](./TAB_01_TEXT_TO_VIDEO.md) | `t2v` |
| 02 | [Image to Video](./TAB_02_IMAGE_TO_VIDEO.md) | `i2v` |
| **→ 03** | **Ingredients to Video** | `r2v` |
| 04 | [Text to Image](./TAB_04_TEXT_TO_IMAGE.md) | `t2i` |
| 05 | [Image to Image](./TAB_05_IMAGE_TO_IMAGE.md) | `i2i` |
| 06 | [Queue](./TAB_06_QUEUE_MANAGER.md) | `queue` |
| 07 | [Settings](./TAB_07_SETTINGS.md) | `settings` |
| 08 | [License](./TAB_08_LICENSE.md) | `license` |
| 09 | [About](./TAB_09_ABOUT.md) | `about` |
| 10 | [Dev Console](./TAB_10_DEV_CONSOLE.md) | `dev` (hidden) |

---

**Mode Index**: `2` (`componentsToVideo`)  
**IMAGE SETUP**: ✅ From Global Library (max 3 per prompt)  
**USE continuation**: ✅ Available (per-prompt toggle)  
**Model**: Veo 3.1 / Veo 2

---

## 🎨 Layout

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │ Text to Video │ Image to Video │[Ingredients]│ Text to Image │ Image to Image │ Queue │ Settings │ License │ About │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│   SIDEBAR (260px)          │   WORKSPACE (QSplitter flex)                                       │
├────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 📁 Project Name            │ ┌─────────────────────────────────────────────────────────────────┐ │
│ [QLineEdit              ]  │ │ 📝 PROMPT INPUT (QGroupBox)                                     │ │
│ 📂 Output Folder           │ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ [QLineEdit] [Browse]       │ │ │ QTextEdit with [tag] support                                │ │ │
│ 📐 Aspect Ratio            │ │ │ [char_hero] [bg_castle] Hero storms the castle              │ │ │
│ [QComboBox          ▼   ]  │ │ └─────────────────────────────────────────────────────────────┘ │ │
│ 🎬 Outputs/Prompt          │ │ [QPushButton Import] [QPushButton Clear]                       │ │
│ [QComboBox          ▼   ]  │ └─────────────────────────────────────────────────────────────────┘ │
│ 🤖 AI Model                │ ┌─────────────────────────────────────────────────────────────────┐ │
│ [QComboBox          ▼   ]  │ │ 📊 PARSED PROMPTS (QGroupBox)                                  │ │
│ 📹 Download Quality        │ │ QTableWidget: # │ Images (max 3) │ Prompt │ CONT │ Actions     │ │
│ [QComboBox          ▼   ]  │ └─────────────────────────────────────────────────────────────────┘ │
│ ─────────────────────────  │                                                                    │
│ [📂 Manage Library]        │                                                                    │
│ 📊 Queue: 0 pending        │                                                                    │
│ [QPushButton Add to Queue] │                                                                    │
├────────────────────────────┴────────────────────────────────────────────────────────────────────┤
│ QStatusBar: CPU │ RAM │ Queue │ Workers │ License                                               │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Widget Specifications

### Sidebar (260px fixed)

| Widget | Type | Properties |
|--------|------|------------|
| `project_name` | `QLineEdit` | Placeholder: "R2V-Project-{N}" |
| `output_folder` | `QLineEdit` + `QPushButton` | Folder picker |
| `aspect_ratio` | `QComboBox` | ["16:9 (Landscape)", "9:16 (Portrait)"] |
| `outputs_per_prompt` | `QComboBox` | ["1 video" - "4 videos"] |
| `model` | `QComboBox` | Veo 3.1 / Veo 2 models |
| `download_quality` | `QComboBox` | ["720p", "1080p", "4K"] |
| `manage_library_btn` | `QPushButton` | Opens Library Manager |
| `add_queue_btn` | `QPushButton` | "📋 Add to Queue" |

### Library Categorization

| Prefix | Category | Icon |
|--------|----------|------|
| `char_*` | Character | 👤 |
| `bg_*` | Background | 🏞️ |
| `style_*` | Style | 🎨 |
| (other) | Uncategorized | 📷 |

---

## 🔧 Code Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QFileDialog, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt

class IngredientsTab(QWidget):
    """Tab 3: Ingredients-to-Video (multiple component images)"""
    
    MAX_IMAGES = 3  # VEO supports max 3 component images
    
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
        
        # Standard dropdowns (same as T2V/I2V)
        layout.addWidget(QLabel("📁 Project Name"))
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("R2V-Project-01")
        layout.addWidget(self.project_name)
        
        layout.addWidget(QLabel("📂 Output Folder"))
        folder_layout = QHBoxLayout()
        self.output_folder = QLineEdit()
        self.browse_btn = QPushButton("Browse...")
        folder_layout.addWidget(self.output_folder)
        folder_layout.addWidget(self.browse_btn)
        layout.addLayout(folder_layout)
        
        for label, widget_name, items in [
            ("📐 Aspect Ratio", "aspect_ratio", ["16:9 (Landscape)", "9:16 (Portrait)"]),
            ("🎬 Outputs/Prompt", "outputs_per_prompt", ["1 video", "2 videos", "3 videos", "4 videos"]),
            ("🤖 AI Model", "model", ["Veo 3.1 - Fast", "Veo 3.1 - Quality", "Veo 2 - Fast"]),
            ("📹 Download Quality", "download_quality", ["720p", "1080p", "4K"]),
        ]:
            layout.addWidget(QLabel(label))
            combo = QComboBox()
            combo.addItems(items)
            setattr(self, widget_name, combo)
            layout.addWidget(combo)
        
        # Library button
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
        
        # Prompt Input
        prompt_group = QGroupBox("📝 PROMPT INPUT (with [ingredient] tags)")
        prompt_layout = QVBoxLayout(prompt_group)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText(
            "[char_hero] [bg_castle] Hero storms the castle\n"
            "[char_hero] [bg_forest] Walking through the forest"
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
        
        # Parsed Prompts Table
        parsed_group = QGroupBox("📊 PARSED PROMPTS")
        parsed_layout = QVBoxLayout(parsed_group)
        
        self.prompts_table = QTableWidget()
        self.prompts_table.setColumnCount(5)
        self.prompts_table.setHorizontalHeaderLabels(["#", "Images (max 3)", "Prompt", "CONT", "Actions"])
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

### Slot Logic (Max 3 images)

| User's Tags | CONT Enabled | Final Images |
|-------------|--------------|--------------|
| `[hero]` | ✅ | `[🔗cont] + [hero]` (2 images) |
| `[hero] + [castle]` | ✅ | `[🔗cont] + [hero] + [castle]` (3 images) |
| `[char] + [bg] + [style]` | ✅ | `[🔗cont] + [bg] + [style]` (replaces first) |

### Table Cell Status

| State | Symbol | Description |
|-------|--------|-------------|
| Disabled | `⚪ Start` | First prompt |
| Enabled | `🔗 ← #N` | Uses frame from video #N |
| Processing | `🔄 Extracting...` | Frame extraction in progress |
| Error | `⚠️ No video` | Previous video not ready |

---

## 🪟 Popups

| Popup | Trigger | PySide6 Widget |
|-------|---------|----------------|
| Edit Prompt | Click `[✏]` | `QDialog` |
| Image Library | Click `[Manage Library]` | `QDialog` with `QTreeWidget` |
| Folder Picker | Click `[Browse]` | `QFileDialog.getExistingDirectory()` |
| Confirm Dialog | Delete | `QMessageBox.question()` |

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system |
| [IMAGE_LIBRARY_SYSTEM.md](IMAGE_LIBRARY_SYSTEM.md) | Library specs |
| [FRAME_CONTINUATION_WORKFLOW.md](../02_Architecture/FRAME_CONTINUATION_WORKFLOW.md) | Continuation |

---

**Status**: ✅ Migrated to PySide6
