"""
DevConsole — Logs Page

Full-height workspace for live log viewing and JSON preview:
- Top (~70%): Live Logs with level filter, search, auto-scroll
- Bottom (~30%): Last submitted task JSON preview

Log toolbar controls (search, level filter, line count, auto-scroll, clear, export)
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
from PySide6.QtCore import Qt, Signal, Slot, QEvent
from PySide6.QtGui import QFont, QTextCursor, QKeySequence, QGuiApplication

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

# Cap log buffer to prevent unbounded memory growth
MAX_BUFFER = 50000
# Batch flush interval (ms)
FLUSH_INTERVAL_MS = 200

# Line count filter options
LINE_COUNT_OPTIONS = {
    "1K": 1000,
    "2K": 2000,
    "5K": 5000,
    "10K": 10000,
    "20K": 20000,
    "All": 0,  # 0 = show all
}

# Layer/source categories for filtering
SOURCE_CATEGORIES = [
    "All",
    "Extension",   # core.extension_bridge, core.extension_manager
    "Engine",      # core.engine (includes [Foreman:] [Supervisor:])
    "Dispatcher",  # core.dispatcher
    "API",         # core.api_client
    "Account",     # core.account_manager, core.multi_account
    "Controller",  # core.app_controller
    "Browser",     # core.chrome_manager, core.profiles_controller, core.recaptcha_session
    "WebSocket",   # websockets.*
    "Other",       # everything else
]

# Map logger name → category
_SOURCE_MAP = {
    "core.extension_bridge": "Extension",
    "core.extension_manager": "Extension",
    "core.engine": "Engine",
    "core.dispatcher": "Dispatcher",
    "core.api_client": "API",
    "core.account_manager": "Account",
    "core.multi_account": "Account",
    "core.app_controller": "Controller",
    "core.chrome_manager": "Browser",
    "core.profiles_controller": "Browser",
    "core.recaptcha_session": "Browser",
    "core.recaptcha_pool": "Browser",
    "core.adaptive_burst": "Engine",
    "core.worker": "Engine",
    "core.upscale_queue": "Engine",
}

def _classify_source(logger_name: str) -> str:
    """Map logger name to display category."""
    if not logger_name:
        return "Other"
    if logger_name in _SOURCE_MAP:
        return _SOURCE_MAP[logger_name]
    if logger_name.startswith("websockets"):
        return "WebSocket"
    if logger_name.startswith("core."):
        return "Other"
    return "Other"


class LogsPage(QWidget):
    """Live logs + JSON preview with integrated toolbar."""

    # Signal emitted when export is requested (connected by TabDevConsole)
    export_logs = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_buffer = deque(maxlen=MAX_BUFFER)  # Capped buffer: (level, msg, source_category)
        self._pending_logs: list = []
        self._auto_scroll = True
        self._api_debug = True
        self._search_filter = ""
        self._level_filter = "DEBUG"
        self._source_filter = "All"  # Layer/source filter
        self._line_count_limit = 5000  # Default: show last 5K lines
        self._flush_paused = False  # Pause flush during copy
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
        self._search_input.textChanged.connect(self._on_search_changed)
        tb_layout.addWidget(self._search_input)

        tb_layout.addStretch()

        # Line count filter
        lines_label = QLabel("Lines:")
        lines_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        tb_layout.addWidget(lines_label)

        self._lines_combo = QComboBox()
        self._lines_combo.addItems(list(LINE_COUNT_OPTIONS.keys()))
        self._lines_combo.setCurrentText("5K")  # Default
        self._lines_combo.setFixedWidth(70)
        self._lines_combo.currentTextChanged.connect(self._on_lines_changed)
        tb_layout.addWidget(self._lines_combo)

        # Source/Layer filter
        source_label = QLabel("Source:")
        source_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        tb_layout.addWidget(source_label)

        self._source_combo = QComboBox()
        self._source_combo.addItems(SOURCE_CATEGORIES)
        self._source_combo.setCurrentText("All")
        self._source_combo.setFixedWidth(100)
        self._source_combo.currentTextChanged.connect(self._on_source_changed)
        tb_layout.addWidget(self._source_combo)

        # API Debug toggle
        self._api_btn = QPushButton("📡 API Debug: ON")
        self._api_btn.setStyleSheet(Theme.btn_style("secondary", "sm"))
        self._api_btn.setCheckable(True)
        self._api_btn.setChecked(True)
        self._api_btn.clicked.connect(self._on_toggle_api_debug)
        tb_layout.addWidget(self._api_btn)

        # Auto-scroll
        self._scroll_btn = QPushButton("📌 Auto-scroll: ON")
        self._scroll_btn.setStyleSheet(Theme.btn_style("secondary", "sm"))
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
        clear_btn.setStyleSheet(Theme.btn_style("secondary", "sm"))
        clear_btn.clicked.connect(self._on_clear)
        tb_layout.addWidget(clear_btn)

        export_btn = QPushButton("📤 Export")
        export_btn.setStyleSheet(Theme.btn_style("secondary", "sm"))
        export_btn.clicked.connect(self._on_export)
        tb_layout.addWidget(export_btn)

        layout.addWidget(toolbar)

        # ── Content: Logs + JSON ─────────────────────────────
        splitter = QSplitter(Qt.Vertical)

        # Log text — trimming handled by setMaximumBlockCount (O(1) vs cursor loop)
        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(QFont(Theme.FONT_FAMILY_MONO, 10))
        self._log_text.setStyleSheet(
            f"background-color: {Theme.CRUST}; color: {Theme.TEXT}; "
            f"border: none; padding: 4px;"
        )
        self._log_text.setPlainText("Waiting for log output...\n")
        # Set initial display line limit (matches default 5K)
        self._log_text.document().setMaximumBlockCount(self._line_count_limit or 0)
        # Intercept Ctrl+C to prevent freeze from concurrent flush
        self._log_text.installEventFilter(self)
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
        json_frame.setMinimumHeight(120)
        splitter.addWidget(json_frame)

        # Use stretch factors instead of fixed pixel sizes to prevent black gap
        splitter.setStretchFactor(0, 7)  # Log area: 70%
        splitter.setStretchFactor(1, 3)  # JSON preview: 30%
        layout.addWidget(splitter, stretch=1)

    def _setup_flush_timer(self):
        """Timer to batch-flush pending logs every FLUSH_INTERVAL_MS."""
        from PySide6.QtCore import QTimer
        self._flush_timer = QTimer(self)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._flush_timer.start(FLUSH_INTERVAL_MS)

    # ── Public API ────────────────────────────────────────────

    def append_log(self, message: str, level: str = "INFO", source: str = ""):
        """Queue a log message for batch rendering."""
        cat = _classify_source(source)
        self._log_buffer.append((level, message, cat))
        self._pending_logs.append((level, message, cat))

    def update_json_preview(self, data: dict):
        """Update JSON preview panel."""
        import json
        try:
            formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        except Exception:
            formatted = str(data)
        self._json_text.setPlainText(formatted)

    # ── Flush / Render ────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Intercept Ctrl+C on log text to copy safely without freeze."""
        if obj is self._log_text and event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.Copy):
                self._safe_copy()
                return True  # Consumed
        return super().eventFilter(obj, event)

    def _safe_copy(self):
        """Copy selected text with flush paused to prevent deadlock."""
        self._flush_paused = True
        try:
            cursor = self._log_text.textCursor()
            selected = cursor.selectedText()
            if selected:
                # QPlainTextEdit uses \u2029 as paragraph separator
                selected = selected.replace('\u2029', '\n')
                QGuiApplication.clipboard().setText(selected)
        finally:
            self._flush_paused = False

    def _flush_pending(self):
        """Batch-flush all pending logs to display."""
        if not self._pending_logs:
            return
        # Pause flush while user is copying text
        if self._flush_paused:
            return
        # Skip flush if user has active text selection (avoids cursor conflicts)
        if self._log_text.textCursor().hasSelection():
            return

        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_level = level_order.get(self._level_filter, 0)
        search = self._search_filter.lower()

        lines_to_add = []
        for level, msg, cat in self._pending_logs:
            # Level filter
            if level_order.get(level, 0) < min_level:
                continue
            # Source/layer filter
            if self._source_filter != "All" and cat != self._source_filter:
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

        # Batch append — trimming handled by Qt's setMaximumBlockCount
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText("\n".join(lines_to_add) + "\n")

        # Update count (total buffer, not just displayed)
        total = len(self._log_buffer)
        displayed = self._log_text.document().blockCount()
        if self._line_count_limit > 0 and displayed < total:
            self._log_count.setText(f"{displayed:,}/{total:,} logs")
        else:
            self._log_count.setText(f"{total:,} logs")

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
        for level, msg, cat in self._log_buffer:
            if level_order.get(level, 0) < min_level:
                continue
            if self._source_filter != "All" and cat != self._source_filter:
                continue
            if not self._api_debug and "api" in msg.lower():
                continue
            if search and search not in msg.lower():
                continue
            filtered.append(msg)

        # Apply line count limit
        if self._line_count_limit > 0:
            display = filtered[-self._line_count_limit:]
        else:
            display = filtered

        self._log_text.setPlainText("\n".join(display))

        # Update count
        total = len(self._log_buffer)
        shown = len(display)
        if self._line_count_limit > 0 and shown < len(filtered):
            self._log_count.setText(f"{shown:,}/{total:,} logs")
        else:
            self._log_count.setText(f"{total:,} logs")

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

    def _on_lines_changed(self, label: str):
        self._line_count_limit = LINE_COUNT_OPTIONS.get(label, 5000)
        # Update Qt's built-in block limiter
        if self._line_count_limit > 0:
            self._log_text.document().setMaximumBlockCount(self._line_count_limit)
        else:
            self._log_text.document().setMaximumBlockCount(0)  # 0 = unlimited
        self._rerender_logs()

    def _on_source_changed(self, source: str):
        self._source_filter = source
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
                for _lvl, msg, _cat in self._log_buffer:
                    f.write(msg + "\n")

                # JSON
                f.write("\n--- LAST SUBMITTED TASK ---\n")
                f.write(self._json_text.toPlainText())

        except Exception as e:
            logging.getLogger(__name__).error(f"Export failed: {e}")

    def get_export_data(self) -> dict:
        """Return all log data for auto-export.
        
        Returns dict with 'logs' (list of messages) and 
        'json_preview' (last submitted task text).
        """
        logs = [msg for _lvl, msg, _cat in self._log_buffer]
        return {
            "logs": logs,
            "total_count": len(self._log_buffer),
            "json_preview": self._json_text.toPlainText(),
        }
