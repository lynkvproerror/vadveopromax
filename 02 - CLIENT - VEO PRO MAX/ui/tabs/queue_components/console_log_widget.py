"""
VEO Pro Max - Console Log Widget

Collapsible log panel for the Queue tab. Displays user-friendly
status messages with color coding, auto-scroll, and line limit.

Architecture:
- Self-contained PySide6 QFrame
- Collapsed: 32px header with last message preview
- Expanded: header + QPlainTextEdit (200px)
- Receives entries via append_entry() slot
- Thread-safe via Qt Signal

Reference: plan_queue_console_log_panel_20260413.md
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QTextCharFormat, QColor, QTextCursor

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


# ── Color map for log levels ──

_LEVEL_COLORS = {
    "info": Theme.TEXT,
    "success": Theme.GREEN,
    "warning": Theme.YELLOW,
    "error": Theme.RED,
}

_CATEGORY_COLORS = {
    "Browser": "#89DCEB",     # Teal
    "Extension": "#CBA6F7",   # Mauve/Purple
    "XCD": "#F9E2AF",         # Yellow
    "Token": "#F9E2AF",       # Yellow
    "reCAPTCHA": "#FAB387",   # Peach
    "Submit": "#89B4FA",      # Blue
    "Upscale": "#A6E3A1",     # Green
    "Download": "#74C7EC",    # Sapphire
    "Queue": "#89B4FA",       # Blue
    "Account": "#CBA6F7",     # Mauve
    "Lỗi": "#F38BA8",        # Red
}

MAX_LINES = 500
EXPANDED_HEIGHT = 200


class ConsoleLogWidget(QFrame):
    """Collapsible console log panel for Queue tab.
    
    States:
    - Collapsed (default): 32px header bar with last message preview
    - Expanded: header + scrollable log area
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._line_count = 0
        self._last_message = ""
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the widget layout."""
        self.setStyleSheet(f"""
            ConsoleLogWidget {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
            }}
        """)
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        
        # ── Header bar ──
        self._header = QFrame()
        self._header.setFixedHeight(32)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE1};
                border: none;
                border-radius: 4px;
            }}
        """)
        self._header.mousePressEvent = self._on_header_click
        
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(10, 0, 8, 0)
        header_layout.setSpacing(8)
        
        # Arrow + title
        self._arrow = QLabel("▶")
        self._arrow.setStyleSheet(f"""
            color: {Theme.OVERLAY0}; font-size: 10px;
            background: transparent; border: none;
        """)
        self._arrow.setFixedWidth(14)
        header_layout.addWidget(self._arrow)
        
        title = QLabel("Console Log")
        title.setStyleSheet(f"""
            color: {Theme.BLUE}; font-weight: bold; font-size: 12px;
            background: transparent; border: none;
        """)
        header_layout.addWidget(title)
        
        # Last message preview (collapsed state)
        self._preview_label = QLabel("")
        self._preview_label.setStyleSheet(f"""
            color: {Theme.OVERLAY0}; font-size: 11px;
            background: transparent; border: none;
        """)
        self._preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._preview_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_layout.addWidget(self._preview_label, stretch=1)
        
        # Line count badge
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(f"""
            color: {Theme.OVERLAY0}; font-size: 10px;
            background: transparent; border: none;
        """)
        header_layout.addWidget(self._count_label)
        
        # Clear button (only visible when expanded)
        self._clear_btn = QPushButton("🗑")
        self._clear_btn.setFixedSize(24, 24)
        self._clear_btn.setToolTip("Xóa log")
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.OVERLAY0};
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {Theme.RED};
            }}
        """)
        self._clear_btn.clicked.connect(self.clear)
        self._clear_btn.setVisible(False)
        header_layout.addWidget(self._clear_btn)
        
        self._main_layout.addWidget(self._header)
        
        # ── Log text area (hidden by default) ──
        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QFont(Theme.FONT_FAMILY_MONO, 10))
        self._log_text.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Theme.BASE};
                color: {Theme.TEXT};
                border: none;
                border-top: 1px solid {Theme.BORDER};
                padding: 6px 10px;
                selection-background-color: {Theme.SURFACE2};
            }}
        """)
        self._log_text.setFixedHeight(EXPANDED_HEIGHT)
        self._log_text.setVisible(False)
        self._main_layout.addWidget(self._log_text)
        
        # Start collapsed
        self.setFixedHeight(32)
    
    # ── Public API ───────────────────────────────────────────
    
    @Slot(str, str, str, str)
    def append_entry(self, timestamp: str, category: str, level: str,
                     user_message: str):
        """Append a translated log entry to the console.
        
        Called from QueueLogTranslator via Qt Signal (thread-safe).
        
        Args:
            timestamp: "HH:MM:SS"
            category: "Browser", "XCD", "Submit", etc.
            level: "info", "success", "warning", "error"
            user_message: Vietnamese user-facing text
        """
        # Build colored line
        time_color = Theme.OVERLAY0
        cat_color = _CATEGORY_COLORS.get(category, Theme.BLUE)
        msg_color = _LEVEL_COLORS.get(level, Theme.TEXT)
        
        # Format: [11:33:21] [Browser] Đã kết nối
        line = (
            f'<span style="color:{time_color}">[{timestamp}]</span> '
            f'<span style="color:{cat_color}">[{category}]</span> '
            f'<span style="color:{msg_color}">{user_message}</span>'
        )
        
        # Append to text area
        self._log_text.appendHtml(line)
        self._line_count += 1
        
        # Trim old lines
        if self._line_count > MAX_LINES:
            self._trim_lines()
        
        # Auto-scroll to bottom
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._log_text.setTextCursor(cursor)
        
        # Update preview (collapsed state)
        preview = f"[{timestamp}] [{category}] {user_message}"
        self._last_message = preview
        self._preview_label.setText(preview)
        self._preview_label.setStyleSheet(f"""
            color: {msg_color}; font-size: 11px;
            background: transparent; border: none;
        """)
        
        # Update count badge
        self._count_label.setText(f"{self._line_count}")
    
    def clear(self):
        """Clear all log entries."""
        self._log_text.clear()
        self._line_count = 0
        self._last_message = ""
        self._preview_label.setText("")
        self._count_label.setText("")
    
    # ── Private ──────────────────────────────────────────────
    
    def _on_header_click(self, event):
        """Toggle expand/collapse."""
        self._expanded = not self._expanded
        if self._expanded:
            self._arrow.setText("▼")
            self._log_text.setVisible(True)
            self._clear_btn.setVisible(True)
            self._preview_label.setVisible(False)
            self.setFixedHeight(32 + EXPANDED_HEIGHT)
        else:
            self._arrow.setText("▶")
            self._log_text.setVisible(False)
            self._clear_btn.setVisible(False)
            self._preview_label.setVisible(True)
            self.setFixedHeight(32)
    
    def _trim_lines(self):
        """Remove oldest lines to stay under MAX_LINES."""
        doc = self._log_text.document()
        while doc.blockCount() > MAX_LINES:
            cursor = QTextCursor(doc.begin())
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            self._line_count = doc.blockCount()
