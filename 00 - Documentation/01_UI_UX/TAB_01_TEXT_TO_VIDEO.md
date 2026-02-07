# 📝 Tab: Text-to-Video (T2V)

> **Framework**: PySide6 (Qt6)  
> **Reference**: [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md)

## 🗂️ Tab Menu

> **UI Update (2026-02-05)**: Tab bar dùng `QTabWidget` với tên đầy đủ, không emoji.

| Tab | Display Name | Key |
|-----|--------------|-----|
| **→ 01** | **Text to Video** | `t2v` |
| 02 | [Image to Video](./TAB_02_IMAGE_TO_VIDEO.md) | `i2v` |
| 03 | [Ingredients to Video](./TAB_03_INGREDIENTS.md) | `r2v` |
| 04 | [Text to Image](./TAB_04_TEXT_TO_IMAGE.md) | `t2i` |
| 05 | [Image to Image](./TAB_05_IMAGE_TO_IMAGE.md) | `i2i` |
| 06 | [Queue](./TAB_06_QUEUE_MANAGER.md) | `queue` |
| 07 | [Settings](./TAB_07_SETTINGS.md) | `settings` |
| 08 | [License](./TAB_08_LICENSE.md) | `license` |
| 09 | [About](./TAB_09_ABOUT.md) | `about` |
| 10 | [Dev Console](./TAB_10_DEV_CONSOLE.md) | `dev` (hidden, Ctrl+Shift+D) |

---

**Mode Index**: `0` (`textToVideo`)  
**IMAGE SETUP**: ❌ Not shown  
**USE FRAME CONTINUATION**: ✅ Available (per-prompt toggle)  
**Model**: Veo 3.1 / Veo 2

> ⚠️ **MODE IS IMPLICIT**: Derived from Tab selection. When continuation is enabled for 2nd+ prompts, 
> mode auto-switches to `imageToVideo` (VEO Frames to Video) with extracted frame injection.

---

## Layout (Sidebar + Workspace)

> **📐 Spacing Guidelines**: See [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md#3-spacing-system-8px-grid) for standardized spacing.
> Uses `QSplitter` with fixed sidebar (260px) and flex workspace.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │[Text to Video]│ Image to Video │ Ingredients │ Text to Image │ Image to Image │ Queue │ Settings │ License │ About │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│   SIDEBAR (260px)          │   WORKSPACE (QSplitter flex)                                       │
├────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 📁 Project Name            │ ┌─────────────────────────────────────────────────────────────────┐ │
│ ┌────────────────────────┐ │ │ 📝 PROMPT INPUT (QGroupBox)                                     │ │
│ │ QLineEdit              │ │ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ └────────────────────────┘ │ │ │ QTextEdit - multi-line prompt input                         │ │ │
│ 📂 Output Folder           │ │ │ A sunset scene over mountains with golden light             │ │ │
│ ┌────────────────────────┐ │ │ │ Camera pans across the valley revealing a river             │ │ │
│ │ QLineEdit + Browse     │ │ │ └─────────────────────────────────────────────────────────────┘ │ │
│ └────────────────────────┘ │ │ [QPushButton Import] [QPushButton Clear]          5 prompts    │ │
│ [QPushButton Browse...]    │ └─────────────────────────────────────────────────────────────────┘ │
│ 📐 Aspect Ratio            │ ┌─────────────────────────────────────────────────────────────────┐ │
│ ┌────────────────────────┐ │ │ 📊 PARSED PROMPTS (QGroupBox)                                  │ │
│ │ QComboBox          ▼   │ │ │ ┌───────────────────────────────────────────────────────────┐ │ │
│ └────────────────────────┘ │ │ │ QTableWidget with columns:                                 │ │ │
│ 🎬 Outputs/Prompt          │ │ │ # │ Prompt │ Continue │ Status │ Actions                   │ │ │
│ ┌────────────────────────┐ │ │ │ 1 │ Sunset...           │ ⚪ Start │ Pending │ [✏][🗑]     │ │ │
│ │ QComboBox          ▼   │ │ │ │ 2 │ Camera pans...      │ 🔗 ← #1  │ Pending │ [✏][🗑]     │ │ │
│ └────────────────────────┘ │ │ └───────────────────────────────────────────────────────────┘ │ │
│ 🤖 AI Model                │ └─────────────────────────────────────────────────────────────────┘ │
│ ┌────────────────────────┐ │                                                                    │
│ │ QComboBox          ▼   │ │                                                                    │
│ └────────────────────────┘ │                                                                    │
│ 📹 Download Quality        │                                                                    │
│ ┌────────────────────────┐ │                                                                    │
│ │ QComboBox          ▼   │ │                                                                    │
│ └────────────────────────┘ │                                                                    │
│ ─────────────────────────  │                                                                    │
│ 📊 Queue: 2 pending        │                                                                    │
│ [QPushButton Add to Queue] │                                                                    │
├────────────────────────────┴────────────────────────────────────────────────────────────────────┤
│ QStatusBar: CPU: 8% │ RAM: 2.1GB │ Queue: 0 │ Workers: 0/0 │ License: N/A │ v1.0.0            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Widget Specifications

### Sidebar Layout (QVBoxLayout, 260px fixed)

| Widget | Type | Options/Properties |
|--------|------|-------------------|
| `project_name` | `QLineEdit` | Placeholder: "T2V-Project-{N}", auto-increment |
| `output_folder` | `QLineEdit` + `QPushButton` | Folder picker via `QFileDialog.getExistingDirectory()` |
| `aspect_ratio` | `QComboBox` | Items: `["16:9 (Landscape)", "9:16 (Portrait)"]` |
| `outputs_per_prompt` | `QComboBox` | Items: `["1 video", "2 videos", "3 videos", "4 videos"]` |
| `model` | `QComboBox` | Items: `["Veo 3.1 - Fast", "Veo 3.1 - Fast [LP]", "Veo 3.1 - Quality", "Veo 2 - Fast", "Veo 2 - Quality"]` |
| `download_quality` | `QComboBox` | Items: `["720p", "1080p", "4K"]` |
| `queue_status` | `QLabel` | Text: "Queue: N pending" |
| `add_queue_btn` | `QPushButton` | Text: "📋 Add to Queue" |

### Workspace Sections

| Section | Widget | Height | Content |
|---------|--------|--------|---------|
| Prompt Input | `QGroupBox` + `QTextEdit` | 180px | Multi-line prompt entry |
| Parsed Prompts | `QGroupBox` + `QTableWidget` | flex (fill) | Scrollable table with continuation toggles |

### Spacing Guidelines

| Element | Value | Note |
|---------|-------|------|
| Sidebar width | 260px | Fixed via `QSplitter` |
| Section gap | 12px | `layout.setSpacing(12)` |
| Frame padding | 12px | `QGroupBox` margin |
| Button gap | 8px | `QHBoxLayout.setSpacing(8)` |
| Row height | 32px | `QTableWidget` row height |
| Button height | 36px | Action buttons |
| Small button height | 26px | Table row buttons |

---

## Code Implementation

### Tab Class Structure

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QLineEdit, QComboBox, QTextEdit,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QFileDialog
)
from PySide6.QtCore import Qt

class TextToVideoTab(QWidget):
    """Tab 1: Text-to-Video generation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Splitter for sidebar + workspace
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Sidebar (fixed 260px)
        sidebar = self.create_sidebar()
        splitter.addWidget(sidebar)
        
        # Workspace (flex)
        workspace = self.create_workspace()
        splitter.addWidget(workspace)
        
        # Set splitter sizes
        splitter.setSizes([260, 800])
        splitter.setStretchFactor(0, 0)  # Sidebar fixed
        splitter.setStretchFactor(1, 1)  # Workspace stretches
    
    def create_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        layout = QVBoxLayout(sidebar)
        layout.setSpacing(12)
        
        # Project Name
        layout.addWidget(QLabel("📁 Project Name"))
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("T2V-Project-01")
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
        
        # Separator
        layout.addWidget(self.create_separator())
        
        # Queue status
        self.queue_status = QLabel("📊 Queue: 0 pending")
        layout.addWidget(self.queue_status)
        
        # Add to Queue button
        self.add_queue_btn = QPushButton("📋 Add to Queue")
        self.add_queue_btn.clicked.connect(self.add_to_queue)
        layout.addWidget(self.add_queue_btn)
        
        layout.addStretch()
        return sidebar
    
    def create_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setSpacing(12)
        
        # Prompt Input Section
        prompt_group = QGroupBox("📝 PROMPT INPUT")
        prompt_layout = QVBoxLayout(prompt_group)
        
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("Enter prompts (one per line or separated by blank lines)...")
        self.prompt_input.setMinimumHeight(150)
        prompt_layout.addWidget(self.prompt_input)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.import_btn = QPushButton("📥 Import TXT")
        self.clear_btn = QPushButton("🗑️ Clear")
        self.prompt_count = QLabel("0 prompts")
        btn_layout.addWidget(self.import_btn)
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.prompt_count)
        prompt_layout.addLayout(btn_layout)
        
        layout.addWidget(prompt_group)
        
        # Parsed Prompts Section
        parsed_group = QGroupBox("📊 PARSED PROMPTS")
        parsed_layout = QVBoxLayout(parsed_group)
        
        self.prompts_table = QTableWidget()
        self.prompts_table.setColumnCount(5)
        self.prompts_table.setHorizontalHeaderLabels(["#", "Prompt", "Continue", "Status", "Actions"])
        self.prompts_table.horizontalHeader().setStretchLastSection(True)
        self.prompts_table.setSelectionBehavior(QTableWidget.SelectRows)
        parsed_layout.addWidget(self.prompts_table)
        
        layout.addWidget(parsed_group, stretch=1)
        
        return workspace
    
    def create_separator(self) -> QWidget:
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #45475a;")
        return sep
    
    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)
    
    def add_to_queue(self):
        """Add current prompts to queue"""
        # Implementation
        pass
```

---

## 🔄 Frame Continuation Mode Support

Tab 1 supports **mixing standalone mode with continuation mode** within the same batch:

```
EXAMPLE BATCH:
  🆕 Prompt 1: "Sunrise..." [standalone]      → Generate fresh (T2V mode)
  🔗 Prompt 2: "Birds..."   [continue]        → Use last frame from #1 (I2V mode)
  🔗 Prompt 3: "Zoom in..." [continue]        → Use last frame from #2 (chain)
  🆕 Prompt 4: "Flower..."  [standalone]      → Generate fresh (new chain)
  🔗 Prompt 5: "Butterfly..." [continue]      → Use last frame from #4

CHAINS CREATED:
  Chain A: 1 → 2 → 3 (seamless sequence)
  Chain B: 4 → 5
```

### UI Indicators

| Widget | Type | Properties |
|--------|------|------------|
| `continuation_indicator` | `QLabel` | Shows chain: "Chain A: 3 prompts" |
| `continuation_checkbox` | `QCheckBox` | Per-prompt in table row |
| `continuation_header` | `QWidget` | "🔗 CONT: [☐ All] [☐ None]" quick select |

---

## Data Flow

```python
def get_config(self) -> dict:
    return {
        "mode": "text-to-video",
        "project_name": self.project_name.text(),
        "output_folder": self.output_folder.text(),
        "aspect_ratio": self.aspect_ratio.currentText().split()[0],  # "16:9"
        "outputs": int(self.outputs_per_prompt.currentText().split()[0]),
        "model": self.model.currentText(),
        "download_quality": self.download_quality.currentText(),
        "prompts": self.export_prompts_for_queue()
    }
```

---

## 🪟 Popups

> **📖 Full specs**: [POPUP_LAYOUTS.md](POPUP_LAYOUTS.md)

| Popup | Trigger | PySide6 Widget |
|-------|---------|----------------|
| Edit Prompt | Click `[✏]` | `QDialog` |
| Folder Picker | Click `[Browse]` | `QFileDialog.getExistingDirectory()` |
| File Import | Click `[Import TXT]` | `QFileDialog.getOpenFileName()` |
| Confirm Dialog | Delete actions | `QMessageBox.question()` |
| Error Dialog | Error conditions | `QMessageBox.critical()` |

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system, colors, spacing |
| [PYSIDE6_STYLE_GUIDE.md](./PYSIDE6_STYLE_GUIDE.md) | Detailed widget styling |
| [POPUP_LAYOUTS.md](POPUP_LAYOUTS.md) | Popup specifications |
| [UI_TO_API_PARAMETER_MAPPING.md](../02_Architecture/UI_TO_API_PARAMETER_MAPPING.md) | API mapping |
