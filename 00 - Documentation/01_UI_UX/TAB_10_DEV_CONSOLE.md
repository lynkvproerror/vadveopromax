# 🔧 Tab: Dev Console (Developer Mode)

> **Framework**: PySide6 (Qt6)  
> **Reference**: [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md)  
> **Version**: 3.0 - PySide6 Migration

---

## 🗂️ Tab Menu

| Tab | Display Name | Key |
|-----|--------------|-----|
| 01-09 | [Previous tabs...] | |
| **→ 10** | **Dev Console** | `dev` (hidden by default) |

---

## 🔓 Activation Methods

**Method 1**: Settings → Enable Developer Mode  
**Method 2**: License → Show dev banner when license expired  
**Method 3**: Keyboard shortcut `Ctrl+Shift+D`

When enabled:
- Tab 10 becomes visible
- JSON preview before queue submission
- Verbose logging enabled
- Performance metrics shown

---

## 🎨 Layout (Sidebar + Multi-Panel)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │ Text to Video │ Image to Video │ Ingredients │ Text to Image │ Image to Image │ Queue │ Settings │ License │ About │[Dev]│
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 📋 SECTIONS   │ 📝 LOG VIEWER                                                                   │
├───────────────┼──────────────────────────────────────────────────────────────────────────────────┤
│ [📝] Logs     │ 17:35:21 [INFO] Worker started for prompt_001                                   │
│ [📦] Queue    │ 17:35:22 [DEBUG] Uploading image: char_hero.png (512KB)                         │
│ [📊] Perf     │ 17:35:25 [DEBUG] Selector: MODE_DROPDOWN found in 0.3s                          │
│ [🔗] Select.  │ 17:35:26 [WARN] Prompt #2: Image [ocean] not found                              │
│ [🍪] Cookies  │ 17:35:28 [ERROR] Worker: TimeoutException at CREATE_BTN                         │
│               │ 17:35:28 [INFO] Retry: Attempt 2/3 for prompt_002                               │
│               ├──────────────────────────────────────────────────────────────────────────────────┤
│               │ Filter: [🔴 Err] [🟡 Warn] [🔵 Info] [⚪ Log]  │ [🗑️ Clear] [💾 Export]         │
├───────────────┴──────────────────────────────────────────────────────────────────────────────────┤
│ 📦 QUEUE INSPECTOR                                                                              │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ JOB: job_001 (T2V-Batch)                                             Status: 🔄 Running        │
│ Tasks:                                                                                          │
│ ├─ ✅ task_001: "A sunset scene..." (completed in 45s)                                         │
│ ├─ ✅ task_002: "Camera pans..." (completed in 52s)                                            │
│ ├─ 🔄 task_003: "Birds flying..." (generating 45%)                                             │
│ └─ ⏳ task_004: "Mountain view..." (queued)                                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 📊 PERFORMANCE METRICS                                                                          │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Average Times:                                                                                  │
│ │ Phase         │ Time  │ Bar                                        │                         │
│ │ Image Upload  │ 3.5s  │ ████████░░░░░░░░░░░░                       │                         │
│ │ Navigation    │ 1.2s  │ ███░░░░░░░░░░░░░░░░░                       │                         │
│ │ Generation    │ 45s   │ ████████████████████████████████████████   │                         │
│ │ Download      │ 2.1s  │ █████░░░░░░░░░░░░░░░                       │                         │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ QStatusBar                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Widget Specifications

### Section Navigation (Sidebar)

| Widget | Type | Section |
|--------|------|---------|
| `logs_btn` | `QPushButton` | Log Viewer |
| `queue_btn` | `QPushButton` | Queue Inspector |
| `perf_btn` | `QPushButton` | Performance |
| `selectors_btn` | `QPushButton` | Selectors |
| `cookies_btn` | `QPushButton` | Cookie Manager |

### Log Viewer Section

| Widget | Type | Description |
|--------|------|-------------|
| `log_viewer` | `QTextEdit` (read-only) | Log output |
| `filter_errors` | `QPushButton` (toggle) | 🔴 Errors |
| `filter_warnings` | `QPushButton` (toggle) | 🟡 Warnings |
| `filter_info` | `QPushButton` (toggle) | 🔵 Info |
| `filter_log` | `QPushButton` (toggle) | ⚪ Log |
| `clear_btn` | `QPushButton` | Clear logs |
| `export_btn` | `QPushButton` | Export to file |

### Queue Inspector Section

| Widget | Type | Description |
|--------|------|-------------|
| `job_tree` | `QTreeWidget` | Job → Task hierarchy |
| `json_preview` | `QTextEdit` (read-only) | JSON config preview |
| `copy_btn` | `QPushButton` | Copy JSON |
| `validate_btn` | `QPushButton` | Validate schema |
| `test_send_btn` | `QPushButton` | Send to queue (test) |

### Performance Section

| Widget | Type | Description |
|--------|------|-------------|
| `metrics_table` | `QTableWidget` | Phase timing |
| `phase_bars` | `QProgressBar` per phase | Visual timing |
| `bottleneck_label` | `QLabel` | Optimization hints |

### Selectors Section

| Widget | Type | Description |
|--------|------|-------------|
| `selectors_table` | `QTableWidget` | CSS selectors status |
| `screenshot_btn` | `QPushButton` | Take screenshot |
| `inspect_btn` | `QPushButton` | Inspect element |
| `retry_btn` | `QPushButton` | Retry failed selector |
| `export_btn` | `QPushButton` | Export selectors |

---

## 🔧 Code Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QPushButton, QLabel, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QProgressBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class DevConsoleTab(QWidget):
    """Tab 10: Developer Console - Debug and monitoring"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Splitter for sidebar + content
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Sidebar navigation
        sidebar = QWidget()
        sidebar.setFixedWidth(120)
        nav_layout = QVBoxLayout(sidebar)
        
        sections = [
            ("📝 Logs", "logs"),
            ("📦 Queue", "queue"),
            ("📊 Perf", "perf"),
            ("🔗 Selectors", "selectors"),
            ("🍪 Cookies", "cookies"),
        ]
        for text, section_id in sections:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, s=section_id: self.show_section(s))
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        
        splitter.addWidget(sidebar)
        
        # Content area
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        
        # Log Viewer (default)
        self.setup_log_viewer()
        
        splitter.addWidget(content)
        splitter.setSizes([120, 800])
    
    def setup_log_viewer(self):
        group = QGroupBox("📝 LOG VIEWER")
        layout = QVBoxLayout(group)
        
        # Log text area
        self.log_viewer = QTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setFont(QFont("Consolas", 10))
        layout.addWidget(self.log_viewer)
        
        # Filters
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        
        filters = [("🔴 Errors", True), ("🟡 Warnings", True), 
                   ("🔵 Info", True), ("⚪ Log", False)]
        for text, checked in filters:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(checked)
            filter_layout.addWidget(btn)
        
        filter_layout.addStretch()
        self.clear_logs_btn = QPushButton("🗑️ Clear")
        self.export_logs_btn = QPushButton("💾 Export")
        filter_layout.addWidget(self.clear_logs_btn)
        filter_layout.addWidget(self.export_logs_btn)
        layout.addLayout(filter_layout)
        
        self.content_layout.addWidget(group)
    
    def show_section(self, section_id: str):
        """Switch to different section"""
        # Clear current content and show selected section
        pass
    
    def append_log(self, level: str, message: str):
        """Append log entry with color coding"""
        colors = {
            "ERROR": "#f38ba8",
            "WARN": "#f9e2af",
            "INFO": "#89b4fa",
            "DEBUG": "#a6adc8",
        }
        color = colors.get(level, "#cdd6f4")
        
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        html = f'<span style="color:{color}">{timestamp} [{level}] {message}</span><br>'
        self.log_viewer.insertHtml(html)
```

---

## 📊 Log Entry Format

```python
@dataclass
class LogEntry:
    timestamp: str
    level: str  # ERROR, WARN, INFO, DEBUG
    message: str
    source: str = ""
```

### Log Level Colors

| Level | Color | Hex |
|-------|-------|-----|
| ERROR | Pink | `#f38ba8` |
| WARN | Yellow | `#f9e2af` |
| INFO | Blue | `#89b4fa` |
| DEBUG | Subtext | `#a6adc8` |

---

## 🪟 Popups

| Popup | Trigger | PySide6 Widget |
|-------|---------|----------------|
| JSON Preview | Click task | `QDialog` with `QTextEdit` |
| Screenshot | Click `[📸]` | Save file dialog |
| Error Details | Click error row | `QMessageBox.information()` |

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system |
| [MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md) | Queue logic |

---

**Status**: ✅ Migrated to PySide6
