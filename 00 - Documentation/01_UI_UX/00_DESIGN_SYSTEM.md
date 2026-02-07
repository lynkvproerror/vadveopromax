# 🎨 VEO Pro Max - UI/UX Design System (v3.0)

**Status**: AUTHORIZED  
**Framework**: PySide6 (Qt6)  
**Theme**: Catppuccin Mocha (Dark Mode)  
**Reference**: `license_manager_gui.py`

---

## 1. 🎯 Design Philosophy

### Product Overview
| Item | Value |
|------|-------|
| **Category** | Video Generation Automation Tool |
| **Style** | Dark Mode + Modern SaaS Dashboard |
| **Target** | Content Creators, Marketers |

### Design Principles
1. **Consistency** - Đồng nhất UI/UX giữa tất cả tabs
2. **Dark-First** - Tối ưu cho làm việc lâu dài
3. **Data-Dense** - Hiển thị nhiều thông tin trong không gian compact
4. **Responsive** - Hỗ trợ nhiều kích thước window

---

## 2. 🎨 Color System (Catppuccin Mocha)

### Core Palette

```python
# core/theme.py

class Colors:
    """VEO Pro Max - Catppuccin Mocha Color Palette"""
    
    # === BACKGROUNDS ===
    BASE = "#1e1e2e"        # Main window background
    SURFACE0 = "#313244"    # Input fields, headers, status bar
    SURFACE1 = "#2d2d3d"    # Table background, scrollbar track
    SURFACE2 = "#45475a"    # Elevated elements, borders
    
    # === TEXT ===
    TEXT = "#cdd6f4"        # Primary text
    SUBTEXT = "#a6adc8"     # Secondary text, placeholders
    
    # === ACCENT (Primary) ===
    BLUE = "#89b4fa"        # Primary buttons, links, active states
    LAVENDER = "#b4befe"    # Hover states
    SAPPHIRE = "#74c7ec"    # Pressed/active states
    
    # === STATUS COLORS ===
    GREEN = "#a6e3a1"       # Success, active, completed
    YELLOW = "#f9e2af"      # Warning, expiring
    PINK = "#f38ba8"        # Error, danger
    ROSEWATER = "#eba0ac"   # Danger hover
    
    # === BORDER ===
    OVERLAY = "#45475a"     # Borders, dividers, gridlines
    OVERLAY2 = "#6c7086"    # Selection background
```

### Color Usage Matrix

| Context | Color Token | Hex |
|---------|-------------|-----|
| **Window Background** | `BASE` | `#1e1e2e` |
| **Panel/Card Background** | `SURFACE0` | `#313244` |
| **Table Background** | `SURFACE1` | `#2d2d3d` |
| **Input Background** | `SURFACE0` | `#313244` |
| **Primary Button** | `BLUE` | `#89b4fa` |
| **Button Hover** | `LAVENDER` | `#b4befe` |
| **Button Pressed** | `SAPPHIRE` | `#74c7ec` |
| **Danger Button** | `PINK` | `#f38ba8` |
| **Primary Text** | `TEXT` | `#cdd6f4` |
| **Muted Text** | `SUBTEXT` | `#a6adc8` |
| **Border/Divider** | `OVERLAY` | `#45475a` |
| **Selection** | `OVERLAY2` | `#6c7086` |
| **Success** | `GREEN` | `#a6e3a1` |
| **Warning** | `YELLOW` | `#f9e2af` |
| **Error** | `PINK` | `#f38ba8` |

---

## 3. 📐 Spacing System (8px Grid)

### Constants

```python
class Spacing:
    XS = 4    # Icon-text gap
    SM = 8    # Item padding, button internal
    MD = 12   # Layout spacing, margins
    LG = 16   # Section gaps, button horizontal padding
    XL = 20   # Major separators
```

### Border Radius

```python
class Radius:
    SM = 4    # Buttons, inputs, cards
    MD = 6    # Scrollbar handles
    LG = 8    # Dialogs, modals
```

---

## 4. 📝 Typography

### Font Stack

| Usage | Font | Size | Weight |
|-------|------|------|--------|
| **Heading** | Segoe UI | 16px | Bold |
| **Subheading** | Segoe UI | 14px | Semibold |
| **Body** | Segoe UI | 13px | Regular |
| **Mono/Code** | JetBrains Mono | 12px | Regular |
| **Button** | Segoe UI | 13px | Bold |

### Python Implementation

```python
class Fonts:
    HEADING = QFont("Segoe UI", 16)
    HEADING.setBold(True)
    
    SUBHEADING = QFont("Segoe UI", 14)
    SUBHEADING.setWeight(QFont.Weight.DemiBold)
    
    BODY = QFont("Segoe UI", 13)
    
    MONO = QFont("JetBrains Mono", 12)
    
    BUTTON = QFont("Segoe UI", 13)
    BUTTON.setBold(True)
```

---

## 5. 🏗️ Application Architecture

### 5.1 Window Layout (2-Panel: Sidebar + Workspace)

> **Note**: All generation tabs (T2V, I2V, R2V, T2I, I2I) use a **Sidebar + Workspace** layout via `QSplitter`.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  VEO Pro Max  │[Text to Video]│ Image to Video │ Ingredients │ Text to Image │ Image to Image │ │
│               │ Queue │ Settings │ License │ About │                                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│   SIDEBAR (260px fixed)    │   WORKSPACE (flex: expands with QSplitter)                         │
├────────────────────────────┼─────────────────────────────────────────────────────────────────────┤
│ 📁 Project Name            │ ┌─────────────────────────────────────────────────────────────────┐ │
│ ┌────────────────────────┐ │ │ 📝 SECTION TITLE  ← QGroupBox or styled QLabel                  │ │
│ │ QLineEdit              │ │ │ ┌─────────────────────────────────────────────────────────────┐ │ │
│ └────────────────────────┘ │ │ │ QTextEdit / QTableWidget content                            │ │ │
│                            │ │ └─────────────────────────────────────────────────────────────┘ │ │
│ 📂 Output Folder           │ │ [QPushButton Action 1] [QPushButton Action 2]                   │ │
│ ┌────────────────────────┐ │ └─────────────────────────────────────────────────────────────────┘ │
│ │ QLineEdit + Browse     │ │                                                                    │
│ └────────────────────────┘ │ ┌─────────────────────────────────────────────────────────────────┐ │
│ [QPushButton Browse...]    │ │ 📊 SECTION 2                                                    │ │
│ ────────────────────────── │ │ QTableWidget with data                                          │ │
│ 📐 Dropdown Setting        │ │                                                                 │ │
│ ┌────────────────────────┐ │ └─────────────────────────────────────────────────────────────────┘ │
│ │ QComboBox          ▼   │ │                                                                    │
│ └────────────────────────┘ │                                                                    │
│ ...                        │                                                                    │
│ [📋 Add to Queue]          │                                                                    │
├────────────────────────────┴────────────────────────────────────────────────────────────────────┤
│ QStatusBar: CPU: 8% │ RAM: 2.1GB │ Queue: 0 │ Workers: 0/0 │ License: N/A │ v1.0.0            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Layout Implementation

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 VEO Pro Max")
        self.setMinimumSize(1280, 720)
        self.resize(1400, 900)
        
        self.setup_ui()
    
    def setup_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        
        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
```

### 5.3 Architecture Overview

| Layer | Purpose | Technology |
|-------|---------|------------|
| **Browser Layer** | Authentication, token extraction | Playwright |
| **API Layer** | Video generation, upload, download | HTTP Requests |
| **UI Layer** | User interface | PySide6 (Qt6) |

---

## 6. 🧩 Widget Specifications

### 6.1 QPushButton Styles

#### Primary Button
```css
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #b4befe;
}

QPushButton:pressed {
    background-color: #74c7ec;
}

QPushButton:disabled {
    background-color: #45475a;
    color: #6c7086;
}
```

#### Danger Button
```css
QPushButton#dangerBtn {
    background-color: #f38ba8;
}

QPushButton#dangerBtn:hover {
    background-color: #eba0ac;
}
```

#### Ghost/Secondary Button
```css
QPushButton#ghostBtn {
    background-color: transparent;
    color: #cdd6f4;
    border: 1px solid #45475a;
}

QPushButton#ghostBtn:hover {
    background-color: #45475a;
}
```

### 6.2 Input Fields

```css
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 8px;
}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border-color: #89b4fa;
}
```

### 6.3 QTableWidget

```css
QTableWidget {
    background-color: #2d2d3d;
    color: #cdd6f4;
    gridline-color: #45475a;
    selection-background-color: #6c7086;
    border: 1px solid #45475a;
    border-radius: 4px;
}

QTableWidget::item {
    padding: 8px;
}

QTableWidget::item:selected {
    background-color: #6c7086;
}

QHeaderView::section {
    background-color: #313244;
    color: #89b4fa;
    padding: 8px;
    border: 1px solid #45475a;
    font-weight: bold;
}
```

### 6.4 QGroupBox

```css
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 12px;
    color: #89b4fa;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
```

### 6.5 QScrollBar

```css
QScrollBar:vertical {
    background-color: #2d2d3d;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #6c7086;
}
```

---

## 7. 📦 Directory Structure

> See [CODE_STRUCTURE.md](../00_PROJECT/CODE_STRUCTURE.md) for the full, maintained project directory tree.

---

## 8. 🖼️ Icon Mapping

| Concept | Icon | Usage |
|---------|------|-------|
| Text to Video | 📹 | Tab, status |
| Image to Video | 🎬 | Tab, status |
| Ingredients | 🧪 | Tab, status |
| Text to Image | 🎯 | Tab, status |
| Image to Image | ✨ | Tab, status |
| Queue Manager | 📋 | Tab, status |
| Settings | ⚙️ | Tab |
| License | 🔑 | Tab |
| About | ℹ️ | Tab |
| Dev Console | 🖥️ | Tab (hidden) |
| Success | ✅ | Status |
| Warning | ⚠️ | Status |
| Error | ❌ | Status |
| Running | 🔄 | Status |
| Pending | ⏳ | Status |
| Add | ➕ | Actions |
| Delete | 🗑️ | Actions |
| Edit | ✏️ | Actions |
| Folder | 📂 | File ops |

---

## 9. 📐 Window Sizing

### Minimum Requirements
| Property | Value |
|----------|-------|
| **Min Width** | 1280px |
| **Min Height** | 720px |
| **Recommended** | 1920 x 1080 |

### Panel Sizing
| Panel | Width | Behavior |
|-------|-------|----------|
| **Sidebar** | 260px | Fixed via QSplitter |
| **Workspace** | Flex | Expands with window |

### Widget Sizing
| Element | Value |
|---------|-------|
| Button height | 36px |
| Small button | 26px |
| Input height | 38px |
| Section padding | 12px |
| Header padding | 8px |

---

## 10. 📦 Dependencies

> See [CODE_STRUCTURE.md](../00_PROJECT/CODE_STRUCTURE.md) for the full, maintained dependency list.

---

## 11. ✅ UX Best Practices

| Guideline | PySide6 Implementation |
|-----------|------------------------|
| **Loading Feedback** | QProgressBar + QThread |
| **Error Dialogs** | QMessageBox with styled buttons |
| **Keyboard Shortcuts** | QShortcut with QKeySequence |
| **Color Contrast** | All text > 4.5:1 ratio (WCAG AAA) |
| **Tooltips** | setToolTip() on interactive elements |
| **Focus Management** | setFocusPolicy() + tab order |

---

## 12. 🎨 Complete QSS Stylesheet

```css
/* === MAIN WINDOW === */
QMainWindow, QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

QLabel {
    color: #cdd6f4;
}

/* === TABLES === */
QTableWidget {
    background-color: #2d2d3d;
    color: #cdd6f4;
    gridline-color: #45475a;
    selection-background-color: #6c7086;
    border: 1px solid #45475a;
    border-radius: 4px;
}

QTableWidget::item { padding: 8px; }
QTableWidget::item:selected { background-color: #6c7086; }

QHeaderView::section {
    background-color: #313244;
    color: #89b4fa;
    padding: 8px;
    border: 1px solid #45475a;
    font-weight: bold;
}

/* === BUTTONS === */
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover { background-color: #b4befe; }
QPushButton:pressed { background-color: #74c7ec; }
QPushButton:disabled { background-color: #45475a; color: #6c7086; }

QPushButton#dangerBtn { background-color: #f38ba8; }
QPushButton#dangerBtn:hover { background-color: #eba0ac; }

/* === INPUTS === */
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 8px;
}

QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
    border-color: #89b4fa;
}

/* === GROUPBOX === */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 12px;
    color: #89b4fa;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}

/* === STATUS BAR === */
QStatusBar {
    background-color: #313244;
    color: #a6adc8;
}

/* === COMBO BOX === */
QComboBox::drop-down { border: none; width: 20px; }

QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #6c7086;
}

/* === SCROLLBAR === */
QScrollBar:vertical {
    background-color: #2d2d3d;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #6c7086;
}

/* === TAB WIDGET === */
QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 16px;
    border: 1px solid #45475a;
}

QTabBar::tab:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QTabBar::tab:hover:!selected {
    background-color: #45475a;
}
```

---

## 13. 🆕 Common Layout Patterns

### 13.1 Form Layout

```python
form = QFormLayout()
form.setSpacing(8)

# Input với label
name_input = QLineEdit()
name_input.setPlaceholderText("e.g., Nguyễn Văn A")
form.addRow("Name:", name_input)

# Combo box
tier_combo = QComboBox()
tier_combo.addItems(["Option 1", "Option 2"])
form.addRow("Tier:", tier_combo)
```

### 13.2 Dialog Pattern

```python
class MyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("➕ Dialog Title")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Form
        form = QFormLayout()
        # ... fields ...
        layout.addLayout(form)
        
        # Buttons (standard)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
```

### 13.3 Table Configuration

```python
table = QTableWidget()
table.setColumnCount(6)
table.setHorizontalHeaderLabels([
    "Client", "Key", "MID", "Tier", "Status", "Expires"
])

# Stretch last column
header = table.horizontalHeader()
header.setStretchLastSection(True)

# Selection behavior
table.setSelectionBehavior(QTableWidget.SelectRows)
table.setSelectionMode(QTableWidget.SingleSelection)

# Disable editing
table.setEditTriggers(QTableWidget.NoEditTriggers)

# Column widths
table.setColumnWidth(0, 120)  # Fixed
table.setColumnWidth(1, 200)  # Fixed
```

---

## 14. 🆕 Quick Reference

| Element | Padding | Border | Radius |
|---------|---------|--------|--------|
| Button | 8px 16px | none | 4px |
| Input | 8px | 1px solid | 4px |
| Table item | 8px | - | - |
| Header | 8px | 1px solid | - |
| GroupBox | 12px top | 1px solid | 4px |
| Dialog margin | 12px all | - | - |

| Layout | Spacing | Margins |
|--------|---------|---------|
| Main VBox | 12px | 12,12,12,12 |
| Form | 8px | - |
| Button group | auto | - |
| Separator | - | 20px width |

---

## 📚 Cross-References

| Document | Description |
|----------|-------------|
| [PYSIDE6_STYLE_GUIDE.md](./PYSIDE6_STYLE_GUIDE.md) | Detailed widget styling reference |
| [TAB_01_TEXT_TO_VIDEO.md](./TAB_01_TEXT_TO_VIDEO.md) | T2V tab specification |
| [MULTITHREADING_ARCHITECTURE.md](../03_Backend/MULTITHREADING_ARCHITECTURE.md) | System architecture (ĐẠI CHỦ-CHỦ-THẦU-THỢ) |

