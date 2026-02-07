# ℹ️ Tab: About

> **Framework**: PySide6 (Qt6)  
> **Reference**: [00_DESIGN_SYSTEM.md](./00_DESIGN_SYSTEM.md)  
> **Version**: 3.0 - PySide6 Migration

---

## 🗂️ Tab Menu

| Tab | Display Name | Key |
|-----|--------------|-----|
| 01-08 | [Previous tabs...] | |
| **→ 09** | **About** | `about` |
| 10 | [Dev Console](./TAB_10_DEV_CONSOLE.md) | `dev` (hidden) |

---

## 🎨 Layout (Full Width - Centered)

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ VEO Pro Max │ Text to Video │ Image to Video │ Ingredients │ Text to Image │ Image to Image │ Queue │ Settings │ License │[About]│
├────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│                    ██╗   ██╗███████╗ ██████╗      █████╗ ██╗   ██╗████████╗ ██████╗             │
│                    ██║   ██║██╔════╝██╔═══██╗    ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗            │
│                    ██║   ██║█████╗  ██║   ██║    ███████║██║   ██║   ██║   ██║   ██║            │
│                    ╚██╗ ██╔╝██╔══╝  ██║   ██║    ██╔══██║██║   ██║   ██║   ██║   ██║            │
│                     ╚████╔╝ ███████╗╚██████╔╝    ██║  ██║╚██████╔╝   ██║   ╚██████╔╝            │
│                      ╚═══╝  ╚══════╝ ╚═════╝     ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝             │
│                                                                                                  │
│                              VEO Automation Tool                                                 │
│                              Version 2.0.0                                                       │
│                              Build: 2026.01.19.001                                               │
│                                                                                                  │
│     ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐              │
│     │ 📖 Docs         │ │ 🐛 Report Bug   │ │ ⭐ Rate App     │ │ 💬 Discord      │              │
│     │ [QPushButton]   │ │ [QPushButton]   │ │ [QPushButton]   │ │ [QPushButton]   │              │
│     └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘              │
│                                                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🆕 WHAT'S NEW IN 2.0                                                                        │ │
│ │ • PySide6-based modern UI with Catppuccin Mocha theme                                       │ │
│ │ • Multi-profile cookie management                                                           │ │
│ │ • Tag-based image library                                                                   │ │
│ │ • Frame continuation for seamless video chaining                                            │ │
│ │ • Developer console                                                                         │ │
│ │ • Enhanced license protection                                                               │ │
│ └─────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🖥️ SYSTEM INFORMATION                                                                       │ │
│ │  OS:            Windows 11 22H2                                                             │ │
│ │  Python:        3.11.5                                                                      │ │
│ │  PySide6:       6.6.0                                                                       │ │
│ │  Config Path:   C:/Users/.../veo_config                                                     │ │
│ │                                                                                              │ │
│ │  [📂 Open Config Folder]  [📋 Open Logs]                                                    │ │
│ └─────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│                      © 2026 VEO Auto Team. All rights reserved.                                 │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ QStatusBar                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Widget Specifications

### Header Section

| Widget | Type | Description |
|--------|------|-------------|
| `logo_label` | `QLabel` | ASCII art logo |
| `app_name` | `QLabel` | "VEO Automation Tool" |
| `version_label` | `QLabel` | Version + Build |

### Link Buttons

| Widget | Type | URL |
|--------|------|-----|
| `docs_btn` | `QPushButton` | https://docs.veoauto.com |
| `bug_btn` | `QPushButton` | https://github.com/.../issues |
| `rate_btn` | `QPushButton` | App store rating |
| `discord_btn` | `QPushButton` | Discord invite |

### What's New Section

| Widget | Type | Description |
|--------|------|-------------|
| `changelog_group` | `QGroupBox` | "🆕 WHAT'S NEW" |
| `changelog_text` | `QTextEdit` (read-only) | Feature list |
| `full_changelog_btn` | `QPushButton` | Open full changelog |

### System Information

| Widget | Type | Description |
|--------|------|-------------|
| `system_group` | `QGroupBox` | "🖥️ SYSTEM INFO" |
| `system_table` | `QFormLayout` | Key-value pairs |
| `open_config_btn` | `QPushButton` | Open config folder |
| `open_logs_btn` | `QPushButton` | Open logs folder |

---

## 🔧 Code Implementation

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QTextEdit
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
import platform

class AboutTab(QWidget):
    """Tab 9: About - Application info and links"""
    
    VERSION = "2.0.0"
    BUILD = "2026.01.19.001"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # Logo
        logo = QLabel(self.get_ascii_logo())
        logo.setStyleSheet("font-family: monospace; color: #89b4fa;")
        layout.addWidget(logo, alignment=Qt.AlignCenter)
        
        # App name and version
        name = QLabel("VEO Automation Tool")
        name.setStyleSheet("font-size: 24px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(name, alignment=Qt.AlignCenter)
        
        version = QLabel(f"Version {self.VERSION} • Build {self.BUILD}")
        version.setStyleSheet("color: #a6adc8;")
        layout.addWidget(version, alignment=Qt.AlignCenter)
        
        # Link buttons
        links_layout = QHBoxLayout()
        for text, url in [
            ("📖 Docs", "https://docs.veoauto.com"),
            ("🐛 Report Bug", "https://github.com/issues"),
            ("⭐ Rate App", "#"),
            ("💬 Discord", "https://discord.gg/invite"),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            links_layout.addWidget(btn)
        layout.addLayout(links_layout)
        
        # What's New
        whatsnew = QGroupBox("🆕 WHAT'S NEW IN 2.0")
        whatsnew_layout = QVBoxLayout(whatsnew)
        changelog = QTextEdit()
        changelog.setReadOnly(True)
        changelog.setPlainText(
            "• PySide6-based modern UI with Catppuccin Mocha theme\n"
            "• Multi-profile cookie management\n"
            "• Tag-based image library\n"
            "• Frame continuation for seamless video chaining\n"
            "• Developer console\n"
            "• Enhanced license protection"
        )
        changelog.setMaximumHeight(120)
        whatsnew_layout.addWidget(changelog)
        layout.addWidget(whatsnew)
        
        # System Info
        sysinfo = QGroupBox("🖥️ SYSTEM INFORMATION")
        sysinfo_layout = QVBoxLayout(sysinfo)
        
        info_text = f"OS: {platform.system()} {platform.release()}\n"
        info_text += f"Python: {platform.python_version()}\n"
        info_text += "PySide6: 6.6.0"
        
        info_label = QLabel(info_text)
        sysinfo_layout.addWidget(info_label)
        
        btn_layout = QHBoxLayout()
        self.open_config_btn = QPushButton("📂 Open Config Folder")
        self.open_logs_btn = QPushButton("📋 Open Logs")
        btn_layout.addWidget(self.open_config_btn)
        btn_layout.addWidget(self.open_logs_btn)
        sysinfo_layout.addLayout(btn_layout)
        
        layout.addWidget(sysinfo)
        
        # Copyright
        copyright_label = QLabel("© 2026 VEO Auto Team. All rights reserved.")
        copyright_label.setStyleSheet("color: #585b70;")
        layout.addWidget(copyright_label, alignment=Qt.AlignCenter)
    
    def get_ascii_logo(self):
        return """██╗   ██╗███████╗ ██████╗ 
██║   ██║██╔════╝██╔═══██╗
██║   ██║█████╗  ██║   ██║
╚██╗ ██╔╝██╔══╝  ██║   ██║
 ╚████╔╝ ███████╗╚██████╔╝
  ╚═══╝  ╚══════╝ ╚═════╝ """
```

---

**Status**: ✅ Migrated to PySide6
