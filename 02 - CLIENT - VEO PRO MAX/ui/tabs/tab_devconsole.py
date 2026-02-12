"""
VEO Pro Max - Tab 10: Dev Console - PySide6 Version

Reference: TAB_10_DEV_CONSOLE.md
Hidden by default (Ctrl+Shift+D to show)
Now hooks into Python logging for real-time log capture.
"""

from typing import Optional
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QComboBox, QGridLayout, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QObject, Slot
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
    """
    
    # Signals
    export_logs = Signal()
    clear_logs = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self._min_level = "DEBUG"
        self._log_count = 0
        self._max_log_lines = 5000
        self._log_buffer = []  # Store all (message, level) for re-filtering
        
        self._setup_ui()
        self._attach_logging()
    
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
        
        layout.addStretch()
        
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
        """Create console panels in 2x3 grid."""
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)
        
        # Row 0: Logs (wide) + Queue State
        self.log_text = self._create_text_panel("Waiting for log output...\n")
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
        """Handle incoming log message from Python logging."""
        # Always store in buffer (unfiltered)
        self._log_buffer.append((message, level))
        if len(self._log_buffer) > self._max_log_lines:
            self._log_buffer = self._log_buffer[-self._max_log_lines:]
        
        # Level filter for display
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        if level_order.get(level, 0) < level_order.get(self._min_level, 0):
            return
        
        # Color by level
        color = LEVEL_COLORS.get(level, Theme.SUBTEXT0)
        
        # Append with color
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.setTextColor(QColor(color))
        self.log_text.insertPlainText(message + "\n")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        
        # Update count
        self._log_count += 1
        self.log_count_label.setText(f"{self._log_count} logs")
    
    # === Public API (called by app_controller / other modules) ===
    
    def append_log(self, message: str, level: str = "INFO"):
        """Append a log message directly (backward-compatible)."""
        color = LEVEL_COLORS.get(level, Theme.SUBTEXT0)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.setTextColor(QColor(color))
        self.log_text.insertPlainText(f"[{level}] {message}\n")
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self._log_count += 1
        self.log_count_label.setText(f"{self._log_count} logs")
    
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
            
            # Browser session (runtime headless browser)
            browser_alive = acc.get("browser_alive", False)
            ba_icon = "🟢 Alive" if browser_alive else "⚪ Off"
            lines.append(f"  Browser Session: {ba_icon}")
            
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
            
            # Debug browser state
            browser_map = {
                "visible": "🟢 Visible",
                "hidden": "🟡 Hidden",
                "closed": "⚪ Off",
            }
            bs = browser_map.get(acc.get("browser_state", "closed"), "⚪ Off")
            enabled = "✅" if acc.get("is_enabled") else "❌"
            lines.append(f"  Debug Browser: {bs} | Enabled: {enabled}")
            lines.append("")
        
        lines.append(f"  Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        self.session_text.setPlainText("\n".join(lines))
    
    @Slot()
    def update_session_data_safe(self):
        """Thread-safe slot: re-gather session data from controller and update."""
        if hasattr(self, 'controller') and self.controller:
            data = self.controller.get_session_data()
            self.update_session_data(data)
    
    # === Actions ===
    
    def _on_level_changed(self, level: str):
        """Handle log level filter change — re-render all stored logs."""
        self._min_level = level
        self._rerender_logs()
    
    def _rerender_logs(self):
        """Re-render log display from buffer using current level filter."""
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        min_ord = level_order.get(self._min_level, 0)
        
        self.log_text.clear()
        count = 0
        for message, level in self._log_buffer:
            if level_order.get(level, 0) < min_ord:
                continue
            color = LEVEL_COLORS.get(level, Theme.SUBTEXT0)
            self.log_text.moveCursor(QTextCursor.MoveOperation.End)
            self.log_text.setTextColor(QColor(color))
            self.log_text.insertPlainText(message + "\n")
            count += 1
        
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self._log_count = count
        self.log_count_label.setText(f"{self._log_count} logs")
    
    def _on_clear(self):
        """Clear all log panels."""
        self.log_text.clear()
        self._log_buffer.clear()
        self._log_count = 0
        self.log_count_label.setText("0 logs")
        self.clear_logs.emit()
    
    def _on_export(self):
        """Export logs to file."""
        try:
            # Snapshot text BEFORE opening dialog (avoid race with logging threads)
            logs = self.log_text.toPlainText()
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
                f.write("=== LOGS ===\n")
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
            self.append_log(f"Logs exported to {path}", "INFO")
            self.export_logs.emit()
        except Exception as e:
            self.append_log(f"Export failed: {e}", "ERROR")
