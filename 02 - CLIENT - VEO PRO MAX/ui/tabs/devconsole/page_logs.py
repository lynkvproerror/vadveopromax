"""
DevConsole — Logs Page

Full-height workspace for live log viewing and JSON preview:
- Top (~70%): Live Logs with level filter, search, auto-scroll
- Bottom (~30%): Last submitted task JSON preview

Log toolbar controls (search, level filter, auto-scroll, clear, export)
are embedded in this page's header area.

Data sources:
- Python root logger via QtLogHandler signal
- AppController last-submitted task dict
"""

import sys
import logging
from collections import deque
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QFrame, QSplitter, QPushButton, QLineEdit, QComboBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QTextCursor

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


# Level colors (Catppuccin Mocha)
LEVEL_COLORS = {
    "DEBUG": "#89B4FA",
    "INFO": "#A6E3A1",
    "WARNING": "#F9E2AF",
    "ERROR": "#F38BA8",
    "CRITICAL": "#F38BA8",
}

# Max lines kept in log buffer
MAX_BUFFER = 2000
# Max lines in QPlainTextEdit (auto-trim old lines)
MAX_DISPLAY_LINES = 1500
# Batch flush interval (ms)
FLUSH_INTERVAL_MS = 200


class LogsPage(QWidget):
    """Live logs + JSON preview with integrated toolbar."""

    # Signal emitted when export is requested (connected by TabDevConsole)
    export_logs = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_buffer: deque = deque(maxlen=MAX_BUFFER)
        self._pending_logs: list = []
        self._auto_scroll = True
        self._api_debug = True
        self._search_filter = ""
        self._level_filter = "DEBUG"
        self._setup_ui()
        self._setup_flush_timer()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────
        toolbar = QFrame()
        toolbar.setFixedHeight(38)
        toolbar.setStyleSheet(f"background-color: {Theme.SURFACE0};")

        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("📝 Logs")
        title.setStyleSheet(
            f"color: {Theme.BLUE}; font-weight: bold; font-size: 14px;"
        )
        tb_layout.addWidget(title)

        self._log_count = QLabel("0 logs")
        self._log_count.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        tb_layout.addWidget(self._log_count)

        # Search
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        tb_layout.addWidget(search_icon)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter logs...")
        self._search_input.setFixedWidth(160)
        self._search_input.setStyleSheet(
            f"background-color: {Theme.BASE}; color: {Theme.TEXT}; "
            f"border: 1px solid {Theme.SURFACE2}; border-radius: 4px; padding: 2px 6px;"
        )
        self._search_input.textChanged.connect(self._on_search_changed)
        tb_layout.addWidget(self._search_input)

        tb_layout.addStretch()

        # API Debug toggle
        self._api_btn = QPushButton("📡 API Debug: ON")
        self._api_btn.setProperty("variant", "secondary")
        self._api_btn.setCheckable(True)
        self._api_btn.setChecked(True)
        self._api_btn.clicked.connect(self._on_toggle_api_debug)
        tb_layout.addWidget(self._api_btn)

        # Auto-scroll
        self._scroll_btn = QPushButton("📌 Auto-scroll: ON")
        self._scroll_btn.setProperty("variant", "secondary")
        self._scroll_btn.setCheckable(True)
        self._scroll_btn.setChecked(True)
        self._scroll_btn.clicked.connect(self._on_toggle_auto_scroll)
        tb_layout.addWidget(self._scroll_btn)

        # Level filter
        level_label = QLabel("Min Level:")
        level_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        tb_layout.addWidget(level_label)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._level_combo.setFixedWidth(100)
        self._level_combo.currentTextChanged.connect(self._on_level_changed)
        tb_layout.addWidget(self._level_combo)

        # Actions
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setProperty("variant", "secondary")
        clear_btn.clicked.connect(self._on_clear)
        tb_layout.addWidget(clear_btn)

        export_btn = QPushButton("📤 Export")
        export_btn.setProperty("variant", "secondary")
        export_btn.clicked.connect(self._on_export)
        tb_layout.addWidget(export_btn)

        layout.addWidget(toolbar)

        # ── Content: Logs + JSON ─────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # Log text
        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QFont(Theme.FONT_FAMILY_MONO, 10))
        self._log_text.setMaximumBlockCount(MAX_DISPLAY_LINES)
        self._log_text.setStyleSheet(
            f"background-color: {Theme.CRUST}; color: {Theme.TEXT}; "
            f"border: none; padding: 4px;"
        )
        self._log_text.setPlainText("Waiting for log output...\n")
        splitter.addWidget(self._log_text)

        # JSON Preview
        json_frame = QFrame()
        json_frame.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px; }}"
        )
        jf_layout = QVBoxLayout(json_frame)
        jf_layout.setContentsMargins(10, 8, 10, 8)
        jf_layout.setSpacing(4)

        json_label = QLabel("📝 Last Submitted Task (JSON)")
        json_label.setStyleSheet(
            f"color: {Theme.BLUE}; font-weight: bold; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        jf_layout.addWidget(json_label)

        self._json_text = QPlainTextEdit()
        self._json_text.setReadOnly(True)
        self._json_text.setFont(QFont(Theme.FONT_FAMILY_MONO, 10))
        self._json_text.setStyleSheet(
            f"background-color: transparent; color: {Theme.GREEN}; "
            f"border: none; padding: 0px;"
        )
        self._json_text.setPlainText("No tasks submitted yet.\n")
        jf_layout.addWidget(self._json_text, stretch=1)
        splitter.addWidget(json_frame)

        splitter.setSizes([500, 200])
        layout.addWidget(splitter, stretch=1)

    def _setup_flush_timer(self):
        """Timer to batch-flush pending logs every FLUSH_INTERVAL_MS."""
        from PySide6.QtCore import QTimer
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._flush_timer.start(FLUSH_INTERVAL_MS)

    # ── Public API ────────────────────────────────────────────

    def append_log(self, message: str, level: str = "INFO"):
        """Queue a log message for batch rendering."""
        self._log_buffer.append((level, message))
        self._pending_logs.append((level, message))

    def update_json_preview(self, data: dict):
        """Update JSON preview panel."""
        import json
        try:
            formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        except Exception:
            formatted = str(data)
        self._json_text.setPlainText(formatted)

    # ── Flush / Render ────────────────────────────────────────

    def _flush_pending(self):
        """Batch-flush all pending logs to display."""
        if not self._pending_logs:
            return

        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level = level_order.get(self._level_filter, 0)
        search = self._search_filter.lower()

        lines_to_add = []
        for level, msg in self._pending_logs:
            # Level filter
            if level_order.get(level, 0) < min_level:
                continue
            # API debug filter
            if not self._api_debug and "api" in msg.lower():
                continue
            # Search filter
            if search and search not in msg.lower():
                continue
            lines_to_add.append(msg)

        self._pending_logs.clear()

        if not lines_to_add:
            return

        # Batch append
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("\n".join(lines_to_add) + "\n")

        # Update count
        self._log_count.setText(f"{len(self._log_buffer)} logs")

        # Auto-scroll
        if self._auto_scroll:
            self._log_text.verticalScrollBar().setValue(
                self._log_text.verticalScrollBar().maximum()
            )

    def _rerender_logs(self):
        """Re-render all stored logs with current filters."""
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level = level_order.get(self._level_filter, 0)
        search = self._search_filter.lower()

        filtered = []
        for level, msg in self._log_buffer:
            if level_order.get(level, 0) < min_level:
                continue
            if not self._api_debug and "api" in msg.lower():
                continue
            if search and search not in msg.lower():
                continue
            filtered.append(msg)

        self._log_text.setPlainText("\n".join(filtered[-MAX_DISPLAY_LINES:]))

        if self._auto_scroll:
            self._log_text.verticalScrollBar().setValue(
                self._log_text.verticalScrollBar().maximum()
            )

    # ── Toolbar handlers ──────────────────────────────────────

    def _on_search_changed(self, text: str):
        self._search_filter = text
        self._rerender_logs()

    def _on_level_changed(self, level: str):
        self._level_filter = level
        self._rerender_logs()

    def _on_toggle_auto_scroll(self):
        self._auto_scroll = self._scroll_btn.isChecked()
        label = "ON" if self._auto_scroll else "OFF"
        self._scroll_btn.setText(f"📌 Auto-scroll: {label}")

    def _on_toggle_api_debug(self):
        self._api_debug = self._api_btn.isChecked()
        label = "ON" if self._api_debug else "OFF"
        self._api_btn.setText(f"📡 API Debug: {label}")
        self._rerender_logs()

    def _on_clear(self):
        self._log_buffer.clear()
        self._pending_logs.clear()
        self._log_text.clear()
        self._json_text.setPlainText("No tasks submitted yet.\n")
        self._log_count.setText("0 logs")

    def _on_export(self):
        """Export logs to file."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", f"dev_logs_{datetime.now():%Y%m%d_%H%M%S}.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("=== VEO Pro Max — Dev Console Log Export ===\n")
                f.write(f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write(f"Total: {len(self._log_buffer)} entries\n")
                f.write("=" * 60 + "\n\n")

                # Logs
                f.write("--- LOGS ---\n")
                for _lvl, msg in self._log_buffer:
                    f.write(msg + "\n")

                # JSON
                f.write("\n--- LAST SUBMITTED TASK ---\n")
                f.write(self._json_text.toPlainText())

        except Exception as e:
            logging.getLogger(__name__).error(f"Export failed: {e}")
