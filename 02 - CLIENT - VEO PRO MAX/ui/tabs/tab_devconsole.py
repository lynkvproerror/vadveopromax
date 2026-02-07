"""
VEO Pro Max - Tab 10: Dev Console - PySide6 Version

Reference: TAB_10_DEV_CONSOLE.md
Migrated from CustomTkinter to PySide6.
Hidden by default (Ctrl+Shift+D to show)
"""

from typing import Optional
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QComboBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class TabDevConsole(QWidget):
    """Developer Console tab (PySide6).
    
    Layout:
    - 6 sections: Logs, Queue, Performance, Playwright, Browser Console, JSON
    - Log level filter
    - Export buttons
    """
    
    # Signals
    export_logs = Signal()
    clear_logs = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Panels grid
        panels = self._create_panels()
        layout.addWidget(panels, stretch=1)
    
    def _create_toolbar(self) -> QWidget:
        """Create toolbar with controls."""
        toolbar = QFrame()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 0, 12, 0)
        
        # Title
        title = QLabel("🛠️ DEVELOPER CONSOLE")
        title.setStyleSheet(f"color: {Theme.YELLOW}; font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Log level filter
        level_label = QLabel("Level:")
        level_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        layout.addWidget(level_label)
        
        self.level_combo = QComboBox()
        self.level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_combo.setFixedWidth(100)
        layout.addWidget(self.level_combo)
        
        layout.addStretch()
        
        # Actions
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setProperty("variant", "secondary")
        clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(clear_btn)
        
        export_btn = QPushButton("📤 Export")
        export_btn.setProperty("variant", "secondary")
        export_btn.clicked.connect(self._on_export)
        layout.addWidget(export_btn)
        
        return toolbar
    
    def _create_panels(self) -> QWidget:
        """Create the 6 console panels in 2x3 grid."""
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)
        
        panels = [
            ("📋 Logs", self._create_log_content),
            ("📊 Queue State", self._create_queue_content),
            ("⚡ Performance", self._create_perf_content),
            ("🎭 Playwright", self._create_playwright_content),
            ("🌐 Browser Console", self._create_browser_content),
            ("📝 JSON Preview", self._create_json_content),
        ]
        
        for i, (title, content_fn) in enumerate(panels):
            row = i // 2
            col = i % 2
            
            panel = self._create_panel(title, content_fn())
            grid.addWidget(panel, row, col)
        
        return container
    
    def _create_panel(self, title: str, content_widget: QWidget) -> QWidget:
        """Create a panel frame with header."""
        panel = QFrame()
        panel.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(28)
        header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 8, 0)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px;")
        header_layout.addWidget(title_label)
        
        layout.addWidget(header)
        layout.addWidget(content_widget, stretch=1)
        
        return panel
    
    def _create_text_panel(self, initial_text: str, color: str = None) -> QTextEdit:
        """Create a text edit panel."""
        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("JetBrains Mono", 9))
        text_color = color or Theme.SUBTEXT0
        text.setStyleSheet(f"background-color: {Theme.BASE}; color: {text_color};")
        text.setPlainText(initial_text)
        return text
    
    def _create_log_content(self) -> QWidget:
        """Create log output content."""
        self.log_text = self._create_text_panel("""[DEBUG] 11:45:00 - App initialized
[INFO]  11:45:01 - Theme loaded: dark_theme.json
[DEBUG] 11:45:02 - Loading saved settings...
[INFO]  11:45:03 - Settings loaded from ~/.veoauto/settings.json
[DEBUG] 11:45:04 - Creating UI components...
[INFO]  11:45:05 - UI ready
""")
        return self.log_text
    
    def _create_queue_content(self) -> QWidget:
        """Create queue state content."""
        return self._create_text_panel("""Queue State:
  Total: 0
  Pending: 0
  Processing: 0
  Completed: 0
  Failed: 0

Workers: 0/0 active
""")
    
    def _create_perf_content(self) -> QWidget:
        """Create performance content."""
        return self._create_text_panel("""CPU: 5%
RAM: 150 MB / 8 GB
Threads: 1 active
Uptime: 00:05:23

API Calls: 0
Downloads: 0
Errors: 0
""")
    
    def _create_playwright_content(self) -> QWidget:
        """Create Playwright debug content."""
        return self._create_text_panel("""Playwright Status:
  Browser: Not running
  Pages: 0
  Contexts: 0

Last Action: None
""")
    
    def _create_browser_content(self) -> QWidget:
        """Create browser console content."""
        return self._create_text_panel("""Browser console logs will appear here...

[Capture enabled when browser is active]
""")
    
    def _create_json_content(self) -> QWidget:
        """Create JSON preview content."""
        return self._create_text_panel("""{
  "lastRequest": null,
  "lastResponse": null,
  "queueState": {},
  "settings": {}
}
""", Theme.GREEN)
    
    def _on_clear(self):
        """Clear all logs."""
        self.log_text.clear()
        self.clear_logs.emit()
    
    def _on_export(self):
        """Export logs."""
        self.export_logs.emit()
    
    def append_log(self, message: str, level: str = "INFO"):
        """Append a log message."""
        self.log_text.append(f"[{level}] {message}")
