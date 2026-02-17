"""
VEO Pro Max - Tab 10: Dev Console - PySide6 Version

Reference: TAB_10_DEV_CONSOLE.md
Hidden by default (Ctrl+Shift+D to show)
Now hooks into Python logging for real-time log capture.

Performance fixes:
- QTextEdit uses maximumBlockCount to auto-trim old lines
- Log appends are batched via QTimer (50ms) to prevent GUI freeze
- Stdout/stderr are also captured and forwarded to logging
"""

from typing import Optional, List, Tuple
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from collections import deque

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QComboBox, QGridLayout, QFileDialog, QLineEdit
)
from PySide6.QtCore import Qt, Signal, QObject, Slot, QTimer
from PySide6.QtGui import QFont, QTextCursor, QColor

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


# === Logging bridge: Python logging → Qt Signal ===

class _LogSignalBridge(QObject):
    """Bridge object that holds the signal (must be QObject subclass)."""
    log_received = Signal(str, str)  # (formatted_message, level_name)


class QtLogHandler(logging.Handler):
    """Custom logging handler that emits Qt signals.
    
    Attach to root logger so ALL app logs are captured and
    forwarded to the DevConsole UI via a signal.
    """
    
    def __init__(self):
        super().__init__()
        self.bridge = _LogSignalBridge()
        self.setFormatter(logging.Formatter(
            "[%(levelname)-5s] %(asctime)s - %(name)s - %(message)s",
            datefmt="%H:%M:%S",
        ))
    
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            # Signal emission is thread-safe in PySide6
            self.bridge.log_received.emit(msg, record.levelname)
        except Exception:
            self.handleError(record)


# === Stdout/Stderr capture → logging ===

class _StreamToLogger:
    """Redirect stdout/stderr to a Python logger.
    
    This ensures print() statements from any module are also
    visible in the Dev Console (which hooks into logging).
    Original stream is preserved for terminal output.
    """
    
    def __init__(self, logger: logging.Logger, level: int, original_stream):
        self._logger = logger
        self._level = level
        self._original = original_stream
        self._buffer = ""
        self._in_log = False  # Recursion guard
    
    def write(self, text: str):
        # Always write to original stream (terminal)
        if self._original:
            try:
                self._original.write(text)
            except Exception:
                pass
        
        # Buffer partial lines, emit on newline
        # Guard against recursion: logging error → stderr.write → logger.log → repeat
        if text and not self._in_log:
            self._in_log = True
            try:
                self._buffer += text
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    if line.strip():  # Skip empty lines
                        self._logger.log(self._level, line.rstrip())
            except Exception:
                pass
            finally:
                self._in_log = False
    
    def flush(self):
        if self._original:
            try:
                self._original.flush()
            except Exception:
                pass
        # Flush any remaining buffer (skip during shutdown to avoid recursion)
        if self._buffer.strip() and not self._in_log:
            self._in_log = True
            try:
                self._logger.log(self._level, self._buffer.rstrip())
                self._buffer = ""
            except Exception:
                pass
            finally:
                self._in_log = False
    
    def isatty(self):
        return False
    
    def fileno(self):
        if self._original:
            return self._original.fileno()
        raise AttributeError("no fileno")


def _install_stream_capture():
    """Install stdout/stderr → logging capture (once)."""
    stdout_logger = logging.getLogger("stdout")
    stderr_logger = logging.getLogger("stderr")
    
    # Only install once
    if not isinstance(sys.stdout, _StreamToLogger):
        sys.stdout = _StreamToLogger(stdout_logger, logging.INFO, sys.stdout)
    if not isinstance(sys.stderr, _StreamToLogger):
        sys.stderr = _StreamToLogger(stderr_logger, logging.WARNING, sys.stderr)


# Singleton handler (one per app)
_qt_log_handler: Optional[QtLogHandler] = None


def get_qt_log_handler() -> QtLogHandler:
    """Get or create the singleton QtLogHandler."""
    global _qt_log_handler
    if _qt_log_handler is None:
        _qt_log_handler = QtLogHandler()
    return _qt_log_handler


# === Level colors ===
LEVEL_COLORS = {
    "DEBUG": "#89B4FA",     # Blue
    "INFO": "#A6E3A1",      # Green
    "WARNING": "#F9E2AF",   # Yellow
    "ERROR": "#F38BA8",     # Red
    "CRITICAL": "#F38BA8",  # Red
}


class TabDevConsole(QWidget):
    """Developer Console tab (PySide6).
    
    Live panels:
    - Logs: Real Python logging output with level filter
    - Queue State: Live queue stats (refreshed on signal)
    - JSON Preview: Last submitted task payload
    
    Performance:
    - Logs are batched via QTimer (flush every 50ms)
    - QTextEdit auto-trims to MAX_DISPLAY_LINES (10000 blocks)
    - Buffer stores last MAX_BUFFER_LINES for export/re-filter
    """
    
    # Signals
    export_logs = Signal()
    clear_logs = Signal()
    
    # Performance tuning
    MAX_DISPLAY_LINES = 10000   # QTextEdit auto-trim (maximumBlockCount)
    MAX_BUFFER_LINES = 50000    # In-memory buffer for export/re-filter
    FLUSH_INTERVAL_MS = 50      # Batch flush interval
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self._min_level = "DEBUG"
        self._log_count = 0
        self._log_buffer: List[Tuple[str, str]] = []  # Store all (message, level) for re-filtering
        
        # Batch queue: incoming logs are queued here, flushed by timer
        self._pending_logs: deque = deque(maxlen=5000)
        self._auto_scroll = True
        self._show_api_debug = True   # Toggle for [API ...] debug lines
        self._filter_text = ""        # Text search filter (case-insensitive)
        
        self._setup_ui()
        self._setup_flush_timer()
        self._attach_logging()
        _install_stream_capture()  # Capture print() → logging
    
    # === UI Setup ===
    
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
        
        # Log count
        self.log_count_label = QLabel("0 logs")
        self.log_count_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        layout.addWidget(self.log_count_label)
        
        # Text search filter
        search_label = QLabel("🔍")
        search_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 13px;")
        layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter logs...")
        self.search_input.setFixedWidth(160)
        self.search_input.setStyleSheet(
            f"background-color: {Theme.BASE}; color: {Theme.TEXT}; "
            f"border: 1px solid {Theme.SURFACE2}; border-radius: 4px; padding: 2px 6px;"
        )
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input)
        
        layout.addStretch()
        
        # API Debug toggle
        self.api_debug_btn = QPushButton("📡 API Debug: ON")
        self.api_debug_btn.setProperty("variant", "secondary")
        self.api_debug_btn.setCheckable(True)
        self.api_debug_btn.setChecked(True)
        self.api_debug_btn.clicked.connect(self._on_toggle_api_debug)
        layout.addWidget(self.api_debug_btn)
        
        # Auto-scroll toggle
        self.auto_scroll_btn = QPushButton("📌 Auto-scroll: ON")
        self.auto_scroll_btn.setProperty("variant", "secondary")
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)
        self.auto_scroll_btn.clicked.connect(self._on_toggle_auto_scroll)
        layout.addWidget(self.auto_scroll_btn)
        
        # Log level filter
        level_label = QLabel("Min Level:")
        level_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        layout.addWidget(level_label)
        
        self.level_combo = QComboBox()
        self.level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.level_combo.setFixedWidth(100)
        self.level_combo.currentTextChanged.connect(self._on_level_changed)
        layout.addWidget(self.level_combo)
        
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
        """Create console panels in 2x3 grid + pool status row."""
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)
        
        # Row 0: Logs (wide) + Queue State
        self.log_text = self._create_log_panel("Waiting for log output...\n")
        log_panel = self._create_panel("📋 Logs (Live)", self.log_text)
        grid.addWidget(log_panel, 0, 0)
        
        self.queue_text = self._create_text_panel("Queue not started.\n")
        queue_panel = self._create_panel("📊 Queue State", self.queue_text)
        grid.addWidget(queue_panel, 0, 1)
        
        # Row 1: JSON Preview (wide) + Performance
        self.json_text = self._create_text_panel("No tasks submitted yet.\n", Theme.GREEN)
        json_panel = self._create_panel("📝 Last Submitted Task (JSON)", self.json_text)
        grid.addWidget(json_panel, 1, 0)
        
        self.perf_text = self._create_text_panel("Uptime: 00:00:00\nAPI Calls: 0\n")
        perf_panel = self._create_panel("⚡ Performance", self.perf_text)
        grid.addWidget(perf_panel, 1, 1)
        
        # Row 2: Playwright + Browser Console
        self.playwright_text = self._create_text_panel("Browser: Not running\n")
        pw_panel = self._create_panel("🎭 Playwright", self.playwright_text)
        grid.addWidget(pw_panel, 2, 0)
        
        self.session_text = self._create_text_panel("Session data not loaded yet...\n")
        session_panel = self._create_panel("🔐 Session Data", self.session_text)
        grid.addWidget(session_panel, 2, 1)
        
        # Row 3: Extension Bridge (spans both columns)
        self.extension_text = self._create_text_panel("Extension bridge not started.\n")
        ext_panel = self._create_panel("🧩 Extension Bridge", self.extension_text)
        grid.addWidget(ext_panel, 3, 0, 1, 2)  # span both columns
        
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
    
    def _create_log_panel(self, initial_text: str) -> QTextEdit:
        """Create the main log panel with performance optimizations.
        
        Key: maximumBlockCount auto-trims old lines so the QTextEdit
        never grows unbounded (which was causing freezes/log cutoff).
        """
        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("JetBrains Mono", 9))
        text.setStyleSheet(f"background-color: {Theme.BASE}; color: {Theme.SUBTEXT0};")
        text.setPlainText(initial_text)
        
        # ★ KEY FIX: Auto-trim old lines to prevent unbounded growth
        text.document().setMaximumBlockCount(self.MAX_DISPLAY_LINES)
        
        # Disable undo/redo stack to save memory
        text.setUndoRedoEnabled(False)
        
        # Optimize rendering
        text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        return text
    
    def _create_text_panel(self, initial_text: str, color: str = None) -> QTextEdit:
        """Create a text edit panel."""
        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("JetBrains Mono", 9))
        text_color = color or Theme.SUBTEXT0
        text.setStyleSheet(f"background-color: {Theme.BASE}; color: {text_color};")
        text.setPlainText(initial_text)
        return text
    
    # === Batch Flush Timer ===
    
    def _setup_flush_timer(self):
        """Setup timer to batch-flush pending logs every FLUSH_INTERVAL_MS.
        
        Instead of updating QTextEdit on every single log line (which
        causes a repaint each time), we queue logs and flush in batches.
        This dramatically reduces GUI thread load during heavy logging.
        """
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(self.FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._flush_pending_logs)
        self._flush_timer.start()
    
    # === Logging Hook ===
    
    def _attach_logging(self):
        """Attach to Python root logger to capture all app logs."""
        handler = get_qt_log_handler()
        handler.bridge.log_received.connect(self._on_log_received)
        
        # Add handler to root logger if not already added
        root = logging.getLogger()
        if handler not in root.handlers:
            root.addHandler(handler)
            # Ensure root logger level allows DEBUG through
            if root.level > logging.DEBUG:
                root.setLevel(logging.DEBUG)
    
    @Slot(str, str)
    def _on_log_received(self, message: str, level: str):
        """Handle incoming log message — queue for batched flush."""
        # Always store in buffer (unfiltered) for export/re-filter
        self._log_buffer.append((message, level))
        if len(self._log_buffer) > self.MAX_BUFFER_LINES:
            # Trim oldest 20% to avoid constant trimming
            trim_count = self.MAX_BUFFER_LINES // 5
            self._log_buffer = self._log_buffer[trim_count:]
        
        # Queue for display (flush timer will batch-append to QTextEdit)
        self._pending_logs.append((message, level))
    
    def _flush_pending_logs(self):
        """Batch-flush all pending logs to QTextEdit.
        
        Called by QTimer every FLUSH_INTERVAL_MS.
        Appends all queued logs in a single document update,
        then scrolls to bottom once — instead of per-log.
        """
        if not self._pending_logs:
            return
        
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_ord = level_order.get(self._min_level, 0)
        filter_lower = self._filter_text.lower()
        
        # Collect all pending logs that pass all filters
        to_append: List[Tuple[str, str]] = []
        while self._pending_logs:
            message, level = self._pending_logs.popleft()
            # Level filter
            if level_order.get(level, 0) < min_ord:
                continue
            # API Debug filter: hide [API lines when toggled off
            if not self._show_api_debug and "[API " in message:
                continue
            # Text search filter
            if filter_lower and filter_lower not in message.lower():
                continue
            to_append.append((message, level))
        
        if not to_append:
            return
        
        # Batch-append to QTextEdit (single cursor operation)
        try:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            
            for message, level in to_append:
                color = LEVEL_COLORS.get(level, Theme.SUBTEXT0)
                # Use insertText with format for colored output
                fmt = cursor.charFormat()
                fmt.setForeground(QColor(color))
                cursor.setCharFormat(fmt)
                cursor.insertText(message + "\n")
            
            # Update count
            self._log_count += len(to_append)
            self.log_count_label.setText(f"{self._log_count} logs")
            
            # Auto-scroll to bottom (if enabled)
            if self._auto_scroll:
                self.log_text.setTextCursor(cursor)
                self.log_text.ensureCursorVisible()
        except RuntimeError:
            pass  # Widget destroyed
    
    # === Public API (called by app_controller / other modules) ===
    
    def append_log(self, message: str, level: str = "INFO"):
        """Append a log message directly (backward-compatible)."""
        self._on_log_received(f"[{level}] {message}", level)
    
    def update_queue_state(self, state: dict):
        """Update Queue State panel with live data."""
        lines = [
            f"Queue State:",
            f"  Total     : {state.get('total', 0)}",
            f"  Pending   : {state.get('pending', 0)}",
            f"  Processing: {state.get('processing', 0)}",
            f"  Completed : {state.get('completed', 0)}",
            f"  Failed    : {state.get('errors', 0)}",
            f"",
            f"  Processing: {'🟢 Active' if state.get('is_processing') else '⏸️ Stopped'}",
        ]
        self.queue_text.setPlainText("\n".join(lines))
    
    @Slot()
    def update_queue_state_safe(self):
        """Thread-safe slot: re-gather queue state from controller and update."""
        if hasattr(self, 'controller') and self.controller:
            state = self.controller.get_queue_status()
            self.update_queue_state(state)
    
    def update_json_preview(self, data: dict):
        """Update JSON Preview panel with last submitted task structure."""
        try:
            formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            formatted = str(data)
        self.json_text.setPlainText(formatted)
    
    def update_performance(self, data: dict):
        """Update Performance panel."""
        lines = [
            f"Uptime   : {data.get('uptime', '00:00:00')}",
            f"CPU      : {data.get('cpu', '?')}%",
            f"RAM      : {data.get('ram', '?')} MB",
            f"Threads  : {data.get('threads', '?')}",
            f"",
            f"API Calls: {data.get('api_calls', 0)}",
            f"Downloads: {data.get('downloads', 0)}",
            f"Errors   : {data.get('errors', 0)}",
        ]
        self.perf_text.setPlainText("\n".join(lines))
    
    def update_browser_status(self, accounts: list):
        """Update Playwright panel with browser status for all accounts.
        
        Args:
            accounts: List of dicts with keys: email, state, enabled, slots, has_browser
        """
        if not accounts:
            self.playwright_text.setPlainText("No accounts configured.\n")
            return
        
        lines = [f"🎭 Browser Status ({len(accounts)} accounts)", ""]
        
        ready_count = sum(1 for a in accounts if a.get("has_browser"))
        total = len(accounts)
        lines.append(f"  Active: {ready_count}/{total}")
        lines.append("")
        
        for acc in accounts:
            state = acc.get("state", "⚪ Off")
            email = acc.get("email", "?")
            slots = acc.get("slots", 0)
            enabled = "✅" if acc.get("enabled") else "❌"
            lines.append(f"  {state} {email} | Slots: {slots} | Enabled: {enabled}")
        
        lines.append("")
        lines.append(f"  Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        self.playwright_text.setPlainText("\n".join(lines))
    
    @Slot()
    def update_browser_status_safe(self):
        """Thread-safe slot: re-gather status from controller and update.
        
        Called via QMetaObject.invokeMethod from background threads.
        Runs on GUI thread, so it's safe to update Qt widgets.
        """
        if hasattr(self, 'controller') and self.controller:
            status = self.controller.get_browser_status()
            self.update_browser_status(status)
    
    def update_pool_status(self, pools: list):
        """No-op — worker pool feature removed."""
        pass
    
    @Slot()
    def update_pool_status_safe(self):
        """No-op — worker pool feature removed."""
        pass
    
    def update_session_data(self, accounts: list):
        """Update Session Data panel with per-account token/cookie info.
        
        Args:
            accounts: List of dicts from AppController.get_session_data()
        """
        if not accounts:
            self.session_text.setPlainText("No accounts configured.\n")
            return
        
        lines = [f"🔐 Session Data ({len(accounts)} accounts)", ""]
        
        for acc in accounts:
            email = acc.get("email", "?")
            source = acc.get("data_source", "?")
            lines.append(f"━━ {email} [{source}] ━━")
            
            # Plan & Credits
            sku = acc.get("sku", "?")
            credits = acc.get("credits", 0)
            slots = acc.get("slots_display", "?")
            lines.append(f"  Plan: {sku} | Credits: {credits:,} | Slots: {slots}")
            
            # Session status
            lines.append(f"  Session: {acc.get('session_status', '?')}")
            
            # Access Token (truncated + expiry)
            at = acc.get("access_token", "")
            token_exp = acc.get("token_expiry", "")
            if at:
                at_display = f"{at[:12]}...{at[-8:]}"
                lines.append(f"  Access Token: {at_display}")
            else:
                lines.append(f"  Access Token: ❌ Missing")
            lines.append(f"  Token Status: {token_exp}")
            
            # reCAPTCHA
            lines.append(f"  reCAPTCHA: {acc.get('recaptcha_status', '?')}")
            
            # Extension connection (data source)
            ext_connected = acc.get("ext_connected", False)
            ext_icon = "🟢 Connected" if ext_connected else "🔴 Disconnected"
            lines.append(f"  Extension: {ext_icon}")
            
            # Cookies
            cookie_count = acc.get("cookie_count", 0)
            domains = acc.get("cookie_domains", {})
            cookies_locked = acc.get("cookies_locked", False)
            if cookies_locked:
                lines.append(f"  Cookies: 🔒 Locked (browser active)")
            elif cookie_count:
                domain_str = ", ".join(f"{d}: {c}" for d, c in list(domains.items())[:3])
                lines.append(f"  Cookies: {cookie_count} ({domain_str})")
            else:
                lines.append(f"  Cookies: 0")
            
            # Login browser state (Playwright — login only)
            browser_map = {
                "visible": "🟢 Visible",
                "hidden": "🟡 Hidden",
                "closed": "⚪ Off",
            }
            bs = browser_map.get(acc.get("browser_state", "closed"), "⚪ Off")
            enabled = "✅" if acc.get("is_enabled") else "❌"
            lines.append(f"  Login Browser: {bs} | Enabled: {enabled}")
            lines.append("")
        
        lines.append(f"  Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        self.session_text.setPlainText("\n".join(lines))
    
    @Slot()
    def update_session_data_safe(self):
        """Thread-safe slot: re-gather session data from controller and update."""
        if hasattr(self, 'controller') and self.controller:
            data = self.controller.get_session_data()
            self.update_session_data(data)
    
    def update_extension_status(self, status: dict):
        """Update Extension Bridge panel with live extension data.
        
        Args:
            status: Dict from ExtensionBridge.get_status() with keys:
                running, port, connections, emails, cached_headers
        """
        if not status:
            self.extension_text.setPlainText("Extension bridge not started.\n")
            return
        
        running = status.get('running', False)
        port = status.get('port', 8765)
        conn_count = status.get('connections', 0)
        emails = status.get('emails', [])
        cached_headers = status.get('cached_headers', {})
        
        ws_icon = "🟢" if running else "🔴"
        conn_icon = "🔌" if conn_count > 0 else "⚪"
        
        lines = [
            f"  {ws_icon} WebSocket: ws://127.0.0.1:{port}  |  {conn_icon} Connections: {conn_count}",
            "",
        ]
        
        if emails:
            lines.append(f"  📧 Registered Tabs ({len(emails)}):")
            for email in emails:
                headers = cached_headers.get(email, [])
                header_count = len(headers)
                if header_count > 0:
                    header_names = ", ".join(h.replace("x-", "") for h in headers)
                    lines.append(f"    ✅ {email}  →  {header_count} headers ({header_names})")
                else:
                    lines.append(f"    ⏳ {email}  →  waiting for headers...")
        else:
            lines.append("  📧 No tabs registered yet")
            lines.append("  └─ Open a debug browser to connect extension")
        
        lines.append("")
        lines.append(f"  Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        self.extension_text.setPlainText("\n".join(lines))
    
    @Slot()
    def update_extension_status_safe(self):
        """Thread-safe slot: re-gather extension status from controller and update."""
        if hasattr(self, 'controller') and self.controller:
            status = self.controller.get_extension_status()
            self.update_extension_status(status)
    
    # === Actions ===
    
    def _on_toggle_auto_scroll(self):
        """Toggle auto-scroll behavior."""
        self._auto_scroll = self.auto_scroll_btn.isChecked()
        label = "ON" if self._auto_scroll else "OFF"
        self.auto_scroll_btn.setText(f"📌 Auto-scroll: {label}")
    
    def _on_toggle_api_debug(self):
        """Toggle API debug log visibility."""
        self._show_api_debug = self.api_debug_btn.isChecked()
        label = "ON" if self._show_api_debug else "OFF"
        self.api_debug_btn.setText(f"📡 API Debug: {label}")
        self._rerender_logs()
    
    def _on_search_changed(self, text: str):
        """Handle text search filter change — re-render all stored logs."""
        self._filter_text = text
        self._rerender_logs()
    
    def _on_level_changed(self, level: str):
        """Handle log level filter change — re-render all stored logs."""
        self._min_level = level
        self._rerender_logs()
    
    def _rerender_logs(self):
        """Re-render log display from buffer using all active filters."""
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_ord = level_order.get(self._min_level, 0)
        filter_lower = self._filter_text.lower()
        
        self.log_text.clear()
        
        # Apply all filters: level + API debug + text search
        filtered = []
        for msg, lvl in self._log_buffer:
            if level_order.get(lvl, 0) < min_ord:
                continue
            if not self._show_api_debug and "[API " in msg:
                continue
            if filter_lower and filter_lower not in msg.lower():
                continue
            filtered.append((msg, lvl))
        
        # Take only the tail if there are too many
        if len(filtered) > self.MAX_DISPLAY_LINES:
            filtered = filtered[-self.MAX_DISPLAY_LINES:]
        
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        for message, level in filtered:
            color = LEVEL_COLORS.get(level, Theme.SUBTEXT0)
            fmt = cursor.charFormat()
            fmt.setForeground(QColor(color))
            cursor.setCharFormat(fmt)
            cursor.insertText(message + "\n")
        
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()
        
        self._log_count = len(filtered)
        self.log_count_label.setText(f"{self._log_count} logs")
    
    def _on_clear(self):
        """Clear all log panels."""
        self.log_text.clear()
        self._log_buffer.clear()
        self._pending_logs.clear()
        self._log_count = 0
        self.log_count_label.setText("0 logs")
        self.clear_logs.emit()
    
    def _on_export(self):
        """Export logs to file."""
        try:
            # Export from BUFFER (not QTextEdit) to get ALL logs including trimmed ones
            log_lines = []
            for msg, lvl in self._log_buffer:
                log_lines.append(msg)
            logs = "\n".join(log_lines)
            
            queue = self.queue_text.toPlainText()
            json_preview = self.json_text.toPlainText()
            browser = self.playwright_text.toPlainText()
            session = self.session_text.toPlainText() if hasattr(self, 'session_text') else ""
        except RuntimeError:
            return  # Widget destroyed
        
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs",
            f"veo_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return  # User cancelled
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"=== LOGS ({len(self._log_buffer)} entries) ===\n")
                f.write(logs)
                f.write("\n\n=== QUEUE STATE ===\n")
                f.write(queue)
                f.write("\n\n=== JSON PREVIEW ===\n")
                f.write(json_preview)
                f.write("\n\n=== BROWSER STATUS ===\n")
                f.write(browser)
                if session:
                    f.write("\n\n=== SESSION DATA ===\n")
                    f.write(session)
            self.append_log(f"Logs exported to {path} ({len(self._log_buffer)} entries)", "INFO")
            self.export_logs.emit()
        except Exception as e:
            self.append_log(f"Export failed: {e}", "ERROR")
