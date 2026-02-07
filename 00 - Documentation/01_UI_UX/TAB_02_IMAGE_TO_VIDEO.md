# 🎬 Tab: Image-to-Video (Unified I2V/F2V)

> **Framework**: PySide6 (Qt6)  
> **Reference**: [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md)  
> **Version**: 3.0 - PySide6 Migration

---

## 🗂️ Tab Menu

> **UI Update**: Uses `QTabWidget` with full names, no emojis.

| Tab | Display Name | Key |
|-----|--------------|-----|
| 01 | [Text to Video](./TAB_01_TEXT_TO_VIDEO.md) | `t2v` |
| **→ 02** | **Image to Video** | `i2v` |
| 03 | [Ingredients to Video](./TAB_03_INGREDIENTS.md) | `r2v` |
| 04 | [Text to Image](./TAB_04_TEXT_TO_IMAGE.md) | `t2i` |
| 05 | [Image to Image](./TAB_05_IMAGE_TO_IMAGE.md) | `i2i` |
| 06 | [Queue](./TAB_06_QUEUE_MANAGER.md) | `queue` |
| 07 | [Settings](./TAB_07_SETTINGS.md) | `settings` |
| 08 | [License](./TAB_08_LICENSE.md) | `license` |
| 09 | [About](./TAB_09_ABOUT.md) | `about` |
| 10 | [Dev Console](./TAB_10_DEV_CONSOLE.md) | `dev` (hidden, Ctrl+Shift+D) |

---

## 🎯 Overview

**Unified Design**: Consolidates I2V (single frame) and F2V (dual frames) into single interface.

**Supported Workflows**:
- **I2V (Image-to-Video)**: Single start frame → animated video
- **F2V (Frames-to-Video)**: Start + end frames → transition video

**Frame Modes**:
1. ○ **Start Frame Only** (I2V) - Default
2. ○ **End Frame Only** (Conceptual I2V)
3. ○ **Start to End Frame** (F2V)

---

## 🎨 Layout

> **📐 Spacing**: See [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md#3-spacing-system-8px-grid)
> Uses `QSplitter` with fixed sidebar (260px) and flex workspace.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │ Text to Video │[Image to Video]│ Ingredients │ Text to Image │ Image to Image │ Queue │ Settings │ License │ About │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│   SIDEBAR (260px)          │   WORKSPACE (QSplitter flex)                                       │
├────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 📁 Project Name            │ ┌─────────────────────────────────────────────────────────────────┐ │
│ ┌────────────────────────┐ │ │ 📝 PROMPT INPUT (QGroupBox)                                     │ │
│ │ QLineEdit              │ │ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ └────────────────────────┘ │ │ │ QTextEdit - multi-line prompt input                         │ │ │
│ 📂 Output Folder           │ │ └─────────────────────────────────────────────────────────────┘ │ │
│ ┌────────────────────────┐ │ │ [QPushButton Import] [QPushButton Clear]                       │ │
│ │ QLineEdit + Browse     │ │ └─────────────────────────────────────────────────────────────────┘ │
│ └────────────────────────┘ │ ┌─────────────────────────────────────────────────────────────────┐ │
│ [QPushButton Browse...]    │ │ 📊 PARSED PROMPTS (QGroupBox)                      [❓ Help]   │ │
│ 🎯 Frame Mode              │ │ ┌───────────────────────────────────────────────────────────┐   │ │
│ ○ Start Frame Only (I2V)   │ │ │ QTableWidget columns:                                     │   │ │
│ ○ End Frame Only           │ │ │ # │ Start Frm │ End Frm │ Prompt │ CONT │ Actions         │   │ │
│ ● Start+End Frame (F2V)    │ │ │ 1 │ [hero] ✅ │ -       │ Camera...│ ☐   │ [✏][🗑]        │   │ │
│ 📐 Aspect Ratio            │ │ │ 2 │ 🔗←#1    │ -       │ Hero...  │ ✓   │ [✏][🗑]        │   │ │
│ [QComboBox          ▼   ]  │ │ └───────────────────────────────────────────────────────────┘   │ │
│ 🎬 Outputs/Prompt          │ └─────────────────────────────────────────────────────────────────┘ │
│ [QComboBox          ▼   ]  │                                                                    │
│ 🤖 AI Model                │                                                                    │
│ [QComboBox          ▼   ]  │                                                                    │
│ 📹 Download Quality        │                                                                    │
│ [QComboBox          ▼   ]  │                                                                    │
│ ─────────────────────────  │                                                                    │
│ [📂 Manage Library]        │                                                                    │
│ 📊 Queue: 2 pending        │                                                                    │
│ [QPushButton Add to Queue] │                                                                    │
├────────────────────────────┴────────────────────────────────────────────────────────────────────┤
│ QStatusBar: CPU: 8% │ RAM: 2.1GB │ Queue: 0 │ Workers: 0/0 │ License: N/A │ v1.0.0            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Frame Mode Specifications

### Mode 1: Start Frame Only (I2V) ⭐ Default
- **API**: `/v1/video:batchAsyncGenerateVideoStartImage`
- **Model**: `veo_3_1_i2v_s_fast_ultra_relaxed`
- **Input**: 1 image (start frame)
- **UI**: Start Frm column ACTIVE, End Frm column LOCKED

### Mode 2: End Frame Only
- **API**: Same as I2V
- **UI**: Start Frm column LOCKED, End Frm column ACTIVE

### Mode 3: Start to End Frame (F2V)
- **API**: `/v1/video:batchAsyncGenerateVideoStartAndEndImage`
- **Model**: `veo_3_1_i2v_s_fast_fl_ultra_relaxed`
- **UI**: Both columns ACTIVE

---

## 🧩 Widget Specifications

### Sidebar Layout (260px fixed)

| Widget | Type | Properties |
|--------|------|------------|
| `project_name` | `QLineEdit` | Placeholder: "I2V-Project-{N}" |
| `output_folder` | `QLineEdit` + `QPushButton` | Folder picker |
| `frame_mode_group` | `QButtonGroup` + 3× `QRadioButton` | Frame mode selector |
| `aspect_ratio` | `QComboBox` | Items: ["16:9 (Landscape)", "9:16 (Portrait)"] |
| `outputs_per_prompt` | `QComboBox` | Items: ["1 video", "2 videos", "3 videos", "4 videos"] |
| `model` | `QComboBox` | Veo 3.1 / Veo 2 models |
| `download_quality` | `QComboBox` | Items: ["720p", "1080p", "4K"] |
| `manage_library_btn` | `QPushButton` | Opens Library Manager |
| `add_queue_btn` | `QPushButton` | "📋 Add to Queue" |

### Frame Mode Selector

```python
# Radio button group for frame mode
self.frame_mode_group = QButtonGroup(self)

self.radio_start_only = QRadioButton("Start Frame Only (I2V)")
self.radio_end_only = QRadioButton("End Frame Only")
self.radio_start_to_end = QRadioButton("Start to End Frame (F2V)")

self.radio_start_only.setChecked(True)  # Default

self.frame_mode_group.addButton(self.radio_start_only, id=0)
self.frame_mode_group.addButton(self.radio_end_only, id=1)
self.frame_mode_group.addButton(self.radio_start_to_end, id=2)

self.frame_mode_group.buttonClicked.connect(self.on_frame_mode_changed)
```

### Table Column Visibility

| Frame Mode | Start Frm | End Frm |
|------------|-----------|---------|
| Start Only | ✅ Active | 🔒 Locked |
| End Only | 🔒 Locked | ✅ Active |
| Start+End | ✅ Active | ✅ Active |

---

## 🔧 Code Implementation

### Tab Class

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QLineEdit, QComboBox, QTextEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QRadioButton, QButtonGroup,
    QFileDialog, QCheckBox
)
from PySide6.QtCore import Qt

class ImageToVideoTab(QWidget):
    """Tab 2: Image-to-Video / Frames-to-Video generation"""
    
    FRAME_MODES = {
        0: "START_ONLY",
        1: "END_ONLY",
        2: "START_TO_END"
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mode = "START_ONLY"
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Sidebar + Workspace
        splitter.addWidget(self.create_sidebar())
        splitter.addWidget(self.create_workspace())
        splitter.setSizes([260, 800])
    
    def create_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setSpacing(12)
        
        # Project Name
        layout.addWidget(QLabel("📁 Project Name"))
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("I2V-Project-01")
        layout.addWidget(self.project_name)
        
        # Output Folder
        layout.addWidget(QLabel("📂 Output Folder"))
        folder_layout = QHBoxLayout()
        self.output_folder = QLineEdit()
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.output_folder)
        folder_layout.addWidget(self.browse_btn)
        layout.addLayout(folder_layout)
        
        # Frame Mode Group
        layout.addWidget(QLabel("🎯 Frame Mode"))
        self.frame_mode_group = QButtonGroup(self)
        
        self.radio_start_only = QRadioButton("Start Frame Only (I2V)")
        self.radio_end_only = QRadioButton("End Frame Only")
        self.radio_start_to_end = QRadioButton("Start to End Frame (F2V)")
        self.radio_start_only.setChecked(True)
        
        for i, radio in enumerate([self.radio_start_only, self.radio_end_only, self.radio_start_to_end]):
            self.frame_mode_group.addButton(radio, id=i)
            layout.addWidget(radio)
        
        self.frame_mode_group.buttonClicked.connect(self.on_frame_mode_changed)
        
        # Dropdowns
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
        
        # Separator + Library button
        layout.addWidget(self.create_separator())
        self.library_btn = QPushButton("📂 Manage Library")
        layout.addWidget(self.library_btn)
        
        # Queue status + button
        self.queue_status = QLabel("📊 Queue: 0 pending")
        layout.addWidget(self.queue_status)
        
        self.add_queue_btn = QPushButton("📋 Add to Queue")
        self.add_queue_btn.clicked.connect(self.add_to_queue)
        layout.addWidget(self.add_queue_btn)
        
        layout.addStretch()
        return sidebar
    
    def create_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setSpacing(12)
        
        # Prompt Input
        prompt_group = QGroupBox("📝 PROMPT INPUT")
        prompt_layout = QVBoxLayout(prompt_group)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Describe the video motion with [image_tag]...")
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
        
        # Parsed Prompts with Help button
        parsed_header = QHBoxLayout()
        parsed_header.addWidget(QLabel("📊 PARSED PROMPTS"))
        parsed_header.addStretch()
        self.help_btn = QPushButton("❓ Help")
        self.help_btn.setMaximumWidth(80)
        parsed_header.addWidget(self.help_btn)
        
        parsed_group = QGroupBox()
        parsed_group.setLayout(QVBoxLayout())
        parsed_group.layout().addLayout(parsed_header)
        
        # Table
        self.prompts_table = QTableWidget()
        self.prompts_table.setColumnCount(6)
        self.prompts_table.setHorizontalHeaderLabels(["#", "Start Frm", "End Frm", "Prompt", "CONT", "Actions"])
        self.prompts_table.horizontalHeader().setStretchLastSection(True)
        self.prompts_table.setSelectionBehavior(QTableWidget.SelectRows)
        parsed_group.layout().addWidget(self.prompts_table)
        
        layout.addWidget(parsed_group, stretch=1)
        
        return workspace
    
    def on_frame_mode_changed(self, button):
        """Handle frame mode radio button change"""
        mode_id = self.frame_mode_group.id(button)
        self.current_mode = self.FRAME_MODES[mode_id]
        self.update_table_columns()
        self.validate_state()
    
    def update_table_columns(self):
        """Update table column visibility based on frame mode"""
        if self.current_mode == "START_ONLY":
            self.prompts_table.setColumnHidden(1, False)  # Start visible
            self.prompts_table.setColumnHidden(2, True)   # End hidden
        elif self.current_mode == "END_ONLY":
            self.prompts_table.setColumnHidden(1, True)   # Start hidden
            self.prompts_table.setColumnHidden(2, False)  # End visible
        else:  # START_TO_END
            self.prompts_table.setColumnHidden(1, False)  # Both visible
            self.prompts_table.setColumnHidden(2, False)
    
    def create_separator(self) -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #45475a;")
        return sep
    
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)
    
    def validate_state(self):
        """Validate and enable/disable queue button"""
        # Implementation
        pass
    
    def add_to_queue(self):
        """Add prompts to queue"""
        # Implementation
        pass
```

---

## 🔗 Continuation Feature

### Source Priority

| Priority | Source | Condition |
|----------|--------|-----------|
| 1 | **Continuation** | CONT enabled → Auto-extract frame |
| 2 | **Library Tag** | `[tag]` in prompt → Auto-match |

### Table Cell Status

| Cell Content | Meaning |
|--------------|---------|
| `[hero]` ✅ | Tag matched in library |
| `[hero]` ❌ | Tag missing, cannot queue |
| 🔗 CONT | Will use Continuation |
| 🔒 N/A | Not required |

### Frame Mode × Continuation Matrix

| Frame Mode | CONT Off | CONT On (First) | CONT On (Last) |
|------------|----------|-----------------|----------------|
| Start Only | `[tag]` Start | 🔗 Auto Start | ❌ Invalid |
| End Only | `[tag]` End | ❌ Invalid | 🔗 Auto End |
| Start+End | Both `[tag]` | 🔗 Start + `[tag]` End | `[tag]` Start + 🔗 End |

---

## 🪟 Popups

| Popup | Trigger | PySide6 Widget |
|-------|---------|----------------|
| Edit Prompt | Click `[✏]` | `QDialog` |
| Image Library | Click `[Manage Library]` | `QDialog` with grid |
| Folder Picker | Click `[Browse]` | `QFileDialog.getExistingDirectory()` |
| Help Tooltip | Click `[❓]` | `QMessageBox.information()` |
| Confirm Dialog | Delete | `QMessageBox.question()` |

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system, colors, spacing |
| [PYSIDE6_STYLE_GUIDE.md](./PYSIDE6_STYLE_GUIDE.md) | Widget styling |
| [IMAGE_LIBRARY_SYSTEM.md](IMAGE_LIBRARY_SYSTEM.md) | Tag detection & library |
| [SOURCE_COLUMN_DISPLAY.md](SOURCE_COLUMN_DISPLAY.md) | Source column display |
| [FRAME_CONTINUATION_WORKFLOW.md](../02_Architecture/FRAME_CONTINUATION_WORKFLOW.md) | Continuation feature |

---

**Status**: ✅ Migrated to PySide6
