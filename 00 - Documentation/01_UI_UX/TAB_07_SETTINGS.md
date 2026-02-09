# ⚙️ Tab: Settings

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
| 06 | [Queue](./TAB_06_QUEUE_MANAGER.md) | `queue` |
| **→ 07** | **Settings** | `settings` |
| 08 | [License](./TAB_08_LICENSE.md) | `license` |
| 09 | [About](./TAB_09_ABOUT.md) | `about` |
| 10 | [Dev Console](./TAB_10_DEV_CONSOLE.md) | `dev` (hidden) |

---

## 🎨 Layout (Full Width - Scrollable)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │ Text to Video │ Image to Video │ Ingredients │ Text to Image │ Image to Image │ Queue │[Settings]│ License │ About │
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🌐 CHROME PROFILES (Account Manager)                                                        │ │
│ │ ┌───┬───┬────────────────────────────┬──────┬──────────┬─────────┬────────┬─────────────────┐│ │
│ │ │ ✓ │ # │ Email                      │ Type │ Plan     │ Credits │ Status │ Actions         ││ │
│ │ ├───┼───┼────────────────────────────┼──────┼──────────┼─────────┼────────┼─────────────────┤│ │
│ │ │ ✓ │ 1 │ free@gmail.com             │ 🔑   │ ⏳ Wait  │ N/A     │ 🟢 Ready│ [🔄][🗑️]       ││ │
│ │ │ ✓ │ 2 │ studio@company.com         │ 🌐   │ 🚀 Ultra │ 43,930  │ 🟢 Ready│ [🔄][🗑️]       ││ │
│ │ └───┴───┴────────────────────────────┴──────┴──────────┴─────────┴────────┴─────────────────┘│ │
│ │ [🔑 OAuth]  [🌐 Browser]                                                                     │ │
│ └─────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🔗 CONTINUATION FRAME EXTRACTION                                                            │ │
│ │ ☑️ Enable continuation auto-extraction                                                      │ │
│ │ Extract Point: [○ 500ms] [● 750ms] [○ 1000ms] [○ Custom: [____]ms]                          │ │
│ │                                                                                              │ │
│ │ Frame Source: [● Last Frame 🔒] [○ First Frame]   ← 🔒 Disabled for normal users            │ │
│ │ ⚠️ Tester only: enable via Settings > Access Level                                          │ │
│ └─────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🎯 WORKER SETTINGS                                                                          │ │
│ │ Max Concurrent Workers: [QSpinBox 1-8, default 2]                                           │ │
│ │ Retry on Error: [QSpinBox 0-5, default 3]                                                   │ │
│ │ Request Timeout: [QSpinBox 30-300s, default 120]                                            │ │
│ └─────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🎨 UI PREFERENCES                                                                           │ │
│ │ Theme: [● Dark] [○ Light]   Language: [QComboBox ▼]   Font Size: [QComboBox ▼]             │ │
│ └─────────────────────────────────────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ QStatusBar                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Widget Specifications

### Chrome Profiles Section

| Widget | Type | Properties |
|--------|------|------------|
| `profiles_table` | `QTableWidget` | Columns: ✓, #, Email, Type, Plan, Credits, Status, Actions |
| `oauth_btn` | `QPushButton` | "🔑 OAuth" - Quick login |
| `browser_btn` | `QPushButton` | "🌐 Browser" - Full session |

### Profile Table Columns (8 columns)

| Column | Content | Width | Notes |
|--------|---------|-------|-------|
| **✓** | `QCheckBox` enabled | 30px | |
| **#** | Row number | 30px | |
| **Email** | Account email | Flex | |
| **Type** | 🔑/🌐 emoji only | 40px | Hover for tooltip |
| **Plan** | ⏳Wait/👤Free/🚀Ultra | 80px | OAuth shows Wait until first video |
| **Credits** | Remaining credits | 80px | OAuth shows N/A until first video |
| **Status** | 🟢/🟡/🔴 | 110px | |
| **Actions** | [🔄][🗑️] | 120px | |

### Type Column Display (Updated 2026-02-07)

| Login Method | Emoji | Tooltip |
|--------------|-------|---------|
| OAuth | 🔑 | OAuth Login - Token based |
| Browser | 🌐 | Browser Login - Full session |

### Profile Status (Updated 2026-02-07)

| Status | Icon | Meaning | Condition |
|--------|------|---------|-----------|
| **Expired** | 🔴 | Token đã hết hạn | `token_expires_at <= now` |
| **Expiring** | 🟠 | Token sắp hết hạn | `token_expires_at - now < 5 min` |
| **Login Required** | 🟡 | Chưa đăng nhập hoặc chưa có token | `is_ready == False` |
| **Ready** | 🟢 | Session valid, sẵn sàng | `is_ready == True` |

### Profile Actions

| Button | Icon | Action | Browser Mode |
|--------|------|--------|--------------|
| Refresh | 🔄 | For 🔑 OAuth: Refresh token. For 🌐 Browser: Fetch real-time (headless) | 🔑 N/A, 🌐 Headless |
| Delete | 🗑️ | Remove profile | N/A |

### Dual Login Buttons

| Button | Label | Tooltip | Action | Browser |
|--------|-------|---------|--------|---------|
| OAuth | `🔑 OAuth` | Quick login via OAuth | Opens OAuth popup | N/A |
| Browser | `🌐 Browser` | Full session, real-time | Opens **Chrome** (visible) | Chrome thật |
| Auto-Login | `🔐 Auto` | Auto-fill credentials | Opens Chrome, auto-fills | Chrome thật |

> **Note (2026-02-07)**: Sử dụng Chrome thật (`channel="chrome"`) thay vì Chromium để session ổn định hơn. Refresh session chạy headless.

---

### Continuation Settings

| Widget | Type | Properties | `get_settings()` key |
|--------|------|------------|---------------------|
| `cont_enabled` | `QCheckBox` | "Enable continuation auto-extraction" | `continuation_enabled` (bool) |
| `extract_point` | `QButtonGroup` + `QRadioButton` | 500ms/750ms/1000ms/Custom | `extract_point_ms` (int, parsed) |
| `custom_ms` | `QSpinBox` | Range: 100-2000ms | — (part of extract_point) |
| `frame_source` | `QButtonGroup` + `QRadioButton` | Last Frame (default) / First Frame | `frame_source` (`"LAST"` \| `"FIRST"`) |

> [!IMPORTANT]
> **Frame Source** toggle: `Last Frame` = default, `First Frame` = tester only.
> - Normal user: toggle **disabled** (locked to "Last Frame")
> - Tester: toggle **enabled** (can switch)
> 
> "Last/First Frame" = **nguồn trích xuất** (lấy từ cuối/đầu video trước), KHÔNG phải vị trí đặt.

---

### Worker Settings

| Widget | Type | Properties |
|--------|------|------------|
| `max_workers` | `QSpinBox` | Range: 1-8, Default: 2 |
| `retry_count` | `QSpinBox` | Range: 0-5, Default: 3 |
| `request_timeout` | `QSpinBox` | Range: 30-300s, Default: 120 |

---

### UI Preferences

| Widget | Type | Properties |
|--------|------|------------|
| `theme` | `QButtonGroup` + `QRadioButton` | Dark / Light |
| `language` | `QComboBox` | ["English", "Tiếng Việt", ...] |
| `font_size` | `QComboBox` | ["Small", "Medium", "Large"] |

---

## 🔧 Code Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QGroupBox,
    QTableWidget, QTableWidgetItem, QCheckBox, QRadioButton,
    QButtonGroup, QSpinBox, QComboBox, QPushButton, QLabel
)
from PySide6.QtCore import Qt

class SettingsTab(QWidget):
    """Tab 7: Settings - Full width, scrollable"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        # Main scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        
        # Chrome Profiles Section
        profiles_group = QGroupBox("🌐 CHROME PROFILES (Account Manager)")
        profiles_layout = QVBoxLayout(profiles_group)
        
        self.profiles_table = QTableWidget()
        self.profiles_table.setColumnCount(7)
        self.profiles_table.setHorizontalHeaderLabels([
            "✓", "#", "Email", "Plan", "Credits", "Status", "Actions"
        ])
        profiles_layout.addWidget(self.profiles_table)
        
        self.add_profile_btn = QPushButton("➕ Add Profile")
        profiles_layout.addWidget(self.add_profile_btn)
        
        layout.addWidget(profiles_group)
        
        # Continuation Settings
        cont_group = QGroupBox("🔗 CONTINUATION FRAME EXTRACTION")
        cont_layout = QVBoxLayout(cont_group)
        
        self.cont_enabled = QCheckBox("Enable continuation auto-extraction")
        cont_layout.addWidget(self.cont_enabled)
        
        extract_layout = QHBoxLayout()
        extract_layout.addWidget(QLabel("Extract Point:"))
        self.extract_group = QButtonGroup(self)
        for i, ms in enumerate([500, 750, 1000]):
            radio = QRadioButton(f"{ms}ms")
            if ms == 750:
                radio.setChecked(True)
            self.extract_group.addButton(radio, id=i)
            extract_layout.addWidget(radio)
        
        self.custom_radio = QRadioButton("Custom:")
        self.extract_group.addButton(self.custom_radio, id=3)
        extract_layout.addWidget(self.custom_radio)
        
        self.custom_ms = QSpinBox()
        self.custom_ms.setRange(100, 2000)
        self.custom_ms.setValue(750)
        self.custom_ms.setSuffix("ms")
        extract_layout.addWidget(self.custom_ms)
        extract_layout.addStretch()
        cont_layout.addLayout(extract_layout)
        
        # Frame Source (Last Frame = default, First Frame = tester only)
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Frame Source:"))
        self.frame_source_group = QButtonGroup(self)
        self.last_frame_radio = QRadioButton("Last Frame")
        self.last_frame_radio.setChecked(True)  # Default
        self.first_frame_radio = QRadioButton("First Frame")
        self.frame_source_group.addButton(self.last_frame_radio, id=0)
        self.frame_source_group.addButton(self.first_frame_radio, id=1)
        source_layout.addWidget(self.last_frame_radio)
        source_layout.addWidget(self.first_frame_radio)
        
        # Tester-only access control
        # Normal users: disabled (locked to Last Frame)
        # Testers: enabled
        is_tester = False  # TODO: Check user access level
        self.last_frame_radio.setEnabled(is_tester)
        self.first_frame_radio.setEnabled(is_tester)
        
        source_layout.addStretch()
        cont_layout.addLayout(source_layout)
        
        layout.addWidget(cont_group)
        
        # Worker Settings
        worker_group = QGroupBox("🎯 WORKER SETTINGS")
        worker_layout = QVBoxLayout(worker_group)
        
        for label, widget_name, range_min, range_max, default in [
            ("Max Concurrent Workers:", "max_workers", 1, 8, 2),
            ("Retry on Error:", "retry_count", 0, 5, 3),
            ("Request Timeout (s):", "request_timeout", 30, 300, 120),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            spinbox = QSpinBox()
            spinbox.setRange(range_min, range_max)
            spinbox.setValue(default)
            setattr(self, widget_name, spinbox)
            row.addWidget(spinbox)
            row.addStretch()
            worker_layout.addLayout(row)
        
        layout.addWidget(worker_group)
        
        # UI Preferences
        ui_group = QGroupBox("🎨 UI PREFERENCES")
        ui_layout = QVBoxLayout(ui_group)
        
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_group = QButtonGroup(self)
        self.dark_radio = QRadioButton("Dark")
        self.dark_radio.setChecked(True)
        self.light_radio = QRadioButton("Light")
        self.theme_group.addButton(self.dark_radio, id=0)
        self.theme_group.addButton(self.light_radio, id=1)
        theme_layout.addWidget(self.dark_radio)
        theme_layout.addWidget(self.light_radio)
        
        theme_layout.addWidget(QLabel("  Language:"))
        self.language = QComboBox()
        self.language.addItems(["English", "Tiếng Việt"])
        theme_layout.addWidget(self.language)
        
        theme_layout.addWidget(QLabel("  Font Size:"))
        self.font_size = QComboBox()
        self.font_size.addItems(["Small", "Medium", "Large"])
        self.font_size.setCurrentIndex(1)
        theme_layout.addWidget(self.font_size)
        theme_layout.addStretch()
        ui_layout.addLayout(theme_layout)
        
        layout.addWidget(ui_group)
        
        layout.addStretch()
        
        scroll.setWidget(container)
        
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)
```

---

## 🪟 Popups

| Popup | Trigger | PySide6 Widget |
|-------|---------|----------------|
| Add Profile | Click `[➕]` | `QDialog` |
| Confirm Delete | Click `[🗑️]` | `QMessageBox.question()` |

---

## 🔗 Related Documentation

| Document | Description |
|----------|-------------|
| [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md) | Design system |
| [FRAME_CONTINUATION_WORKFLOW.md](../02_Architecture/FRAME_CONTINUATION_WORKFLOW.md) | Continuation |

---

**Status**: ✅ Migrated to PySide6
