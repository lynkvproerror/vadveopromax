# 📋 Tab: Queue Manager

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
| 05 | [Image to Image](./TAB_05_IMAGE_TO_IMAGE.md) | `i2i` |
| **→ 06** | **Queue** | `queue` |
| 07 | [Settings](./TAB_07_SETTINGS.md) | `settings` |
| 08 | [License](./TAB_08_LICENSE.md) | `license` |
| 09 | [About](./TAB_09_ABOUT.md) | `about` |
| 10 | [Dev Console](./TAB_10_DEV_CONSOLE.md) | `dev` (hidden) |

---

## 🎨 Layout (Full Width)

> Queue Manager uses **full-width layout** (no sidebar).
> Videos auto-save to project folder.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │ Text to Video │ Image to Video │ Ingredients │ Text to Image │ Image to Image │[Queue]│ Settings │ License │ About │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Filter: [QComboBox Project] [QComboBox Status] [QComboBox Mode]    Search: [QLineEdit     ] 🔍  │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ▼ 📁 MV-Hero-Project                          🔄 3/5 (60%)    📹T2V    Veo 3.1                   │
│   Output: D:/Projects/MV_Hero/   [⚙️ Bulk Settings] [▶️ Start] [⏸️ Pause] [🗑️ Delete]           │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ # │ Mode │ Images │ Prompt                               │ Cont │ Progress  │ Status │ Actions  │
├───┼──────┼────────┼──────────────────────────────────────┼──────┼───────────┼────────┼──────────┤
│ 1 │ 🎬   │ [🖼️]   │ Hero stands at cliff edge...         │ ⚪   │ [▶️]      │ ✅Done │ [📝]     │
│ 2 │ 🎬   │ [🔗←#1]│ Camera pans valley ruins...          │ ✓    │ [▶️]      │ ✅Done │ [📝]     │
│ 3 │ 🎬   │ [🔗←#2]│ Birds flying morning mist...         │ ✓    │ [🔄45%]   │ 🔄 45% │ [📝]     │
│ 4 │ 🎬   │ [🔗←#3]│ Final sunset scene...                │ ✓    │ [⏳]      │ ⏳Queue │ [📝]     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ QStatusBar: CPU: 8% │ RAM: 2.1GB │ Queue: 2 │ Workers: 1/2 │ License: Active                    │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Widget Specifications

### Filter Bar

| Widget | Type | Options |
|--------|------|---------|
| `project_filter` | `QComboBox` | ["All Projects", project names...] |
| `status_filter` | `QComboBox` | ["All Status", "Pending", "Running", "Done", "Failed"] |
| `mode_filter` | `QComboBox` | ["All Modes", "T2V", "I2V", "T2I", "I2I", "Ingredients"] |
| `search_input` | `QLineEdit` | Placeholder: "Search prompts..." |
| `search_btn` | `QPushButton` | "🔍" |

### Task Header (Collapsible)

| Element | Description |
|---------|-------------|
| **▼/▶** | Toggle expand/collapse (`QTreeWidget`) |
| **📁 Task Name** | Project identifier |
| **Progress** | 🔄 3/5 (60%) |
| **Mode** | 📹T2V, 🎬I2V, 🧪Ingr, 🎯T2I, ✨I2I |
| **Model** | Veo 3.1, Veo 3.0, etc. |

### Prompt Row (QTableWidget)

| Column | Content | Width |
|--------|---------|-------|
| **#** | Row number | Fixed 40px |
| **Mode** | Icon (📹🎬🧪🎯✨) | Fixed 50px |
| **Images** | Thumbnail or `[🔗←#N]` | Fixed 100px |
| **Prompt** | Text (truncated) | Flex |
| **Cont** | ⚪/✓ checkbox | Fixed 50px |
| **Progress** | [▶️]/[🔄45%]/[⏳] | Fixed 80px |
| **Status** | ✅/🔄/⏳/❌ | Fixed 80px |
| **Actions** | [📝][🔄][🗑️] | Fixed 100px |

---

## 🔧 Code Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLineEdit, QComboBox, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QProgressBar, QHeaderView
)
from PySide6.QtCore import Qt

class QueueManagerTab(QWidget):
    """Tab 6: Queue Manager - Full width layout"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Title
        layout.addWidget(QLabel("📋 QUEUE MANAGER"))
        
        # Filter Bar
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Filter:"))
        self.project_filter = QComboBox()
        self.project_filter.addItems(["All Projects"])
        filter_layout.addWidget(self.project_filter)
        
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Status", "Pending", "Running", "Done", "Failed"])
        filter_layout.addWidget(self.status_filter)
        
        self.mode_filter = QComboBox()
        self.mode_filter.addItems(["All Modes", "T2V", "I2V", "T2I", "I2I", "Ingredients"])
        filter_layout.addWidget(self.mode_filter)
        
        filter_layout.addStretch()
        filter_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search prompts...")
        self.search_input.setMaximumWidth(200)
        filter_layout.addWidget(self.search_input)
        
        self.search_btn = QPushButton("🔍")
        self.search_btn.setMaximumWidth(40)
        filter_layout.addWidget(self.search_btn)
        
        layout.addLayout(filter_layout)
        
        # Queue Tree (hierarchical view)
        self.queue_tree = QTreeWidget()
        self.queue_tree.setHeaderLabels([
            "#", "Mode", "Images", "Prompt", "Cont", "Progress", "Status", "Actions"
        ])
        self.queue_tree.header().setSectionResizeMode(3, QHeaderView.Stretch)
        layout.addWidget(self.queue_tree)
        
        # Control buttons
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶️ Start All")
        self.pause_btn = QPushButton("⏸️ Pause All")
        self.clear_done_btn = QPushButton("🗑️ Clear Done")
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.pause_btn)
        control_layout.addWidget(self.clear_done_btn)
        control_layout.addStretch()
        layout.addLayout(control_layout)
```

---

## 🔄 Status States

| Status | Icon | Description |
|--------|------|-------------|
| Pending | ⏳ | In queue, waiting |
| Running | 🔄 | Currently processing |
| Done | ✅ | Completed successfully |
| Failed | ❌ | Error occurred |
| Paused | ⏸️ | Manually paused |

### Error Types

| Error | Auto-Retry | Action |
|-------|------------|--------|
| `Rate Limit` | ✅ 3x | Wait → Retry |
| `Auth Expired` | ❌ | [🔑 Re-login] |
| `Upload Failed` | ✅ 3x | [🔄 Retry] |
| `Generation Failed` | ❌ | [🔄 Retry] [📋 Log] |
| `Download Failed` | ✅ 3x | [🔄 Retry] |

---

## 🔗 Continuation Frame States

| State | Display | Description |
|-------|---------|-------------|
| Waiting | `[🔗←#N]` | Previous video not done |
| Extracting | `[🔄←#N]` | Extracting frame |
| Ready | `[🖼️ cont.png]` | Frame extracted |
| Error | `[⚠️←#N]` | Extraction failed |

---

## 🪟 Popups

| Popup | Trigger | PySide6 Widget |
|-------|---------|----------------|
| Edit Prompt | Click `[📝]` | `QDialog` |
| Error Log | Click `[📋]` | `QDialog` with `QTextEdit` |
| Confirm Delete | Click `[🗑️]` | `QMessageBox.question()` |
| Bulk Settings | Click `[⚙️]` | `QDialog` |

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system |
| [MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md) | Queue logic |

---

**Status**: ✅ Migrated to PySide6
