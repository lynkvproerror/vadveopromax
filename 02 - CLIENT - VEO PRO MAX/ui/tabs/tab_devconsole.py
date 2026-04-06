"""
VEO Pro Max - Tab 10: Dev Console - PySide6 Version

Reference: TAB_10_DEV_CONSOLE.md
Hidden by default (Ctrl+Shift+D to show)
Now hooks into Python logging for real-time log capture.

Performance fixes:
- Logs are batched via QTimer (flush every 50ms) — see page_logs.py
- QTextEdit auto-trims to MAX_DISPLAY_LINES
- Buffer stores last MAX_BUFFER for export/re-filter

Architecture:
- Sidebar navigation (QListWidget) selects content pages
- QStackedWidget holds 5 page widgets:
  0: DashboardPage  — engine metrics cards
  1: QueuePerfPage  — queue state + performance
  2: AccountsPage   — session + browser + extension per account
  3: LogsPage        — live logs + JSON preview
  4: NetworkPage     — extension bridge + API activity
  5: GeminiApiPage   — Gemini API debug for Project Builder
"""

import sys
import logging
import threading
from pathlib import Path
from typing import Optional, List, Tuple
from collections import deque
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QListWidget, QListWidgetItem, QStackedWidget,
    QLabel, QSplitter,
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor, QIcon

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


# === Logging bridge: Python logging → Qt Signal ===

from PySide6.QtCore import QObject


class _LogSignalBridge(QObject):
    """Bridge object that holds the signal (must be QObject subclass)."""
    log_received = Signal(str, str, str)  # (message, level, source)


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
            level = record.levelname
            source = record.name  # e.g. 'core.engine', 'core.extension_bridge'
            # Emit signal — will be received on GUI thread
            self.bridge.log_received.emit(msg, level, source)
        except RuntimeError:
            # Signal source has been deleted (Qt cleanup during shutdown)
            # Silently ignore — app is exiting
            pass
        except Exception:
            self.handleError(record)


# === Stdout/Stderr capture → logging ===

class _StreamToLogger:
    """Redirect stdout/stderr to a Python logger.
    
    This ensures print() statements from any module are also
    visible in the Dev Console (which hooks into logging).
    
    Thread-safe: uses a Lock to prevent concurrent write() calls
    from multiple threads (e.g., asyncio workers + Python's internal
    unhandled-exception printer) from corrupting the shared _buffer.
    """
    def __init__(self, logger: logging.Logger, level: int, original_stream):
        self._logger = logger
        self._level = level
        self._original = original_stream
        self._buffer = ""
        self._in_log = False  # Recursion guard
        self._lock = threading.Lock()  # ★ Thread-safety fix

    def write(self, text: str):
        # ★ FIX: Use lock to prevent concurrent writes from multiple threads
        # corrupting _buffer (e.g., Python 3.13's per-thread exception printer
        # can call write() from many threads simultaneously).
        # Use non-blocking acquire for recursion guard (same thread re-entering).
        acquired = self._lock.acquire(blocking=True, timeout=0.05)
        if not acquired:
            # Fallback: write directly to original stream to avoid deadlock
            if self._original:
                try:
                    self._original.write(text)
                except Exception:
                    pass
            return
        
        try:
            if self._in_log:
                # Already processing a log call from THIS thread — write to original only
                if self._original:
                    try:
                        self._original.write(text)
                    except Exception:
                        pass
                return
            
            if self._original:
                try:
                    self._original.write(text)
                except Exception:
                    pass
            
            if not text or text.isspace():
                return
            
            self._in_log = True
            try:
                self._buffer += text
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    if line.strip():
                        try:
                            self._logger.log(self._level, line.rstrip())
                        except Exception:
                            pass
            finally:
                self._in_log = False
        finally:
            self._lock.release()

    def flush(self):
        acquired = self._lock.acquire(blocking=True, timeout=0.05)
        if not acquired:
            if self._original:
                try:
                    self._original.flush()
                except Exception:
                    pass
            return
        
        try:
            if self._in_log:
                if self._original:
                    try:
                        self._original.flush()
                    except Exception:
                        pass
                return
            
            if self._original:
                try:
                    self._original.flush()
                except Exception:
                    pass
            
            if self._buffer and self._buffer.strip():
                self._in_log = True
                try:
                    self._logger.log(self._level, self._buffer.rstrip())
                    self._buffer = ""
                except Exception:
                    pass
                finally:
                    self._in_log = False
        finally:
            self._lock.release()

    def isatty(self):
        return False
    
    def fileno(self):
        if self._original:
            return self._original.fileno()
        raise AttributeError("No fileno")



def _install_stream_capture():
    """Install stdout/stderr → logging capture (once)."""
    if hasattr(_install_stream_capture, '_done'):
        return
    _install_stream_capture._done = True
    
    stdout_logger = logging.getLogger("stdout")
    stderr_logger = logging.getLogger("stderr")
    
    sys.stdout = _StreamToLogger(stdout_logger, logging.INFO, sys.stdout)
    sys.stderr = _StreamToLogger(stderr_logger, logging.ERROR, sys.stderr)


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


# ═══════════════════════════════════════════════════════════════
# TabDevConsole — Sidebar Navigation + Stacked Pages
# ═══════════════════════════════════════════════════════════════

class TabDevConsole(QWidget):
    """Developer Console tab (PySide6) — Sidebar + Content Pages.
    
    Sidebar sections:
    0: 📊 Dashboard  — Engine metrics, throughput, account health
    1: 📋 Queue      — Queue state + performance
    2: 👥 Accounts   — Session, browser, extension per account
    3: 📝 Logs       — Live logs + JSON preview
    4: 🌐 Network    — Extension bridge + API activity
    5: 🤖 Gemini API — Project Builder debug
    
    All existing public methods (`update_*`) are preserved for
    backward compatibility with AppController callbacks.
    """
    
    # Signals (preserved for compatibility)
    export_logs = Signal()
    clear_logs = Signal()
    
    # Sidebar items: (emoji, label, page_index)
    SIDEBAR_ITEMS = [
        ("📊", "Dashboard", 0),
        ("📋", "Queue", 1),
        ("👥", "Accounts", 2),
        ("📝", "Logs", 3),
        ("🌐", "Network", 4),
        ("🤖", "Gemini API", 5),
        ("🧩", "Extension", 6),
    ]
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        # Import page widgets
        from ui.tabs.devconsole import (
            DashboardPage, QueuePerfPage, AccountsPage, LogsPage, NetworkPage,
            GeminiApiPage, ExtensionDebugPage,
        )
        
        # Create pages
        self._dashboard_page = DashboardPage()
        self._queue_page = QueuePerfPage()
        self._accounts_page = AccountsPage()
        self._logs_page = LogsPage()
        self._network_page = NetworkPage()
        self._gemini_page = GeminiApiPage()
        self._extension_page = ExtensionDebugPage(controller=controller)
        
        self._setup_ui()
        self._attach_logging()
        _install_stream_capture()
    
    # ── UI Setup ──────────────────────────────────────────────
    
    def _setup_ui(self):
        """Setup sidebar + content workspace layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Top toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Sidebar + Content
        splitter = QSplitter(Qt.Horizontal)
        
        # ── Sidebar ──
        sidebar_frame = QFrame()
        sidebar_frame.setFixedWidth(Theme.SIDEBAR_NAV_WIDTH)
        sidebar_frame.setStyleSheet(
            f"QFrame {{ background-color: {Theme.MANTLE}; "
            f"border-right: 1px solid {Theme.BORDER}; }}"
        )
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(0, Theme.SIDEBAR_PADDING, 0, Theme.SIDEBAR_PADDING)
        sidebar_layout.setSpacing(0)
        
        self._sidebar = QListWidget()
        self._sidebar.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
                font-size: 13px;
            }}
            QListWidget::item {{
                color: {Theme.SUBTEXT0};
                padding: 10px 16px;
                border-left: 3px solid transparent;
            }}
            QListWidget::item:selected {{
                background-color: {Theme.SURFACE0};
                color: {Theme.BLUE};
                border-left: 3px solid {Theme.BLUE};
                font-weight: bold;
            }}
            QListWidget::item:hover:!selected {{
                background-color: {Theme.SURFACE0};
                color: {Theme.TEXT};
            }}
        """)
        
        for icon, label, _idx in self.SIDEBAR_ITEMS:
            item = QListWidgetItem(f"  {icon}  {label}")
            item.setSizeHint(item.sizeHint().__class__(180, 42))
            self._sidebar.addItem(item)
        
        self._sidebar.setCurrentRow(0)  # Default: Dashboard
        self._sidebar.currentRowChanged.connect(self._on_sidebar_changed)
        sidebar_layout.addWidget(self._sidebar)
        sidebar_layout.addStretch()
        
        splitter.addWidget(sidebar_frame)
        
        # ── Content Workspace (QStackedWidget) ──
        self._stack = QStackedWidget()
        self._stack.addWidget(self._dashboard_page)  # 0
        self._stack.addWidget(self._queue_page)       # 1
        self._stack.addWidget(self._accounts_page)    # 2
        self._stack.addWidget(self._logs_page)        # 3
        self._stack.addWidget(self._network_page)     # 4
        self._stack.addWidget(self._gemini_page)      # 5
        self._stack.addWidget(self._extension_page)   # 6
        self._stack.setCurrentIndex(0)
        
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)  # Sidebar: fixed
        splitter.setStretchFactor(1, 1)  # Content: stretch
        
        layout.addWidget(splitter, stretch=1)
        
        # Bottom status bar
        status_bar = self._create_status_bar()
        layout.addWidget(status_bar)
    
    def _create_toolbar(self) -> QWidget:
        """Create minimal top toolbar."""
        toolbar = QFrame()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; }}")
        
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 0, 12, 0)
        
        title = QLabel("🛠️ DEVELOPER CONSOLE")
        title.setStyleSheet(
            f"color: {Theme.YELLOW}; font-weight: bold; font-size: 14px;"
        )
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Log count (always visible)
        self.log_count_label = QLabel("0 logs")
        self.log_count_label.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px;"
        )
        layout.addWidget(self.log_count_label)
        
        return toolbar
    
    def _create_status_bar(self) -> QWidget:
        """Create bottom status bar with engine state summary."""
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE0}; "
            f"border-top: 1px solid {Theme.BORDER}; }}"
        )
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        
        self._status_label = QLabel("Engine: Idle")
        self._status_label.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px;"
        )
        layout.addWidget(self._status_label)
        layout.addStretch()
        
        self._time_label = QLabel("")
        self._time_label.setStyleSheet(
            f"color: {Theme.OVERLAY0}; font-size: 11px;"
        )
        layout.addWidget(self._time_label)
        
        return bar
    
    @Slot(int)
    def _on_sidebar_changed(self, index: int):
        """Switch content page when sidebar selection changes."""
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
    
    # ── Logging Hook ──────────────────────────────────────────
    
    def _attach_logging(self):
        """Attach to Python root logger to capture all app logs.
        
        Bug 5 fix: set handler level to INFO (not root to DEBUG).
        Root stays at its current level for other handlers.
        The huge volume of DEBUG logs from websockets/asyncio
        was flooding the main thread via _on_log_received.
        Level is adjusted dynamically when user changes the filter.
        """
        handler = get_qt_log_handler()
        handler.bridge.log_received.connect(self._on_log_received)
        handler.setLevel(logging.INFO)  # Default: INFO+ only
        
        root = logging.getLogger()
        if handler not in root.handlers:
            root.addHandler(handler)
            # Ensure root can pass DEBUG to us when requested,
            # but our handler filters at INFO by default
            if root.level > logging.DEBUG:
                root.setLevel(logging.DEBUG)
    
    def _sync_handler_level(self, ui_level: str):
        """Sync QtLogHandler level with user's UI filter selection."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        handler = get_qt_log_handler()
        handler.setLevel(level_map.get(ui_level, logging.INFO))
    
    @Slot(str, str, str)
    def _on_log_received(self, message: str, level: str, source: str = ""):
        """Route incoming log message to LogsPage + Network API filter.
        
        Bug 4 fix: skip expensive UI updates when DevConsole tab is not visible.
        ★ Fix N5: throttle visible-tab UI updates to max 10/s (100ms gate).
        Logs still buffer in _log_buffer for later viewing.
        """
        # Always buffer (cheap: deque append)
        self._logs_page.append_log(message, level, source)
        
        # Skip expensive UI work when tab is hidden (Bug 4)
        if not self.isVisible():
            return
        
        # ★ Fix N5: Throttle UI updates to max 10/s — reduces GUI thread
        # contention during peak load (50+ log lines from submit/reCAPTCHA).
        import time
        now = time.time()
        if now - getattr(self, '_last_log_ui_update', 0) < 0.1:
            return
        self._last_log_ui_update = now
        
        # Update toolbar log count
        count = len(self._logs_page._log_buffer)
        self.log_count_label.setText(f"{count:,} logs")
        
        # API debug lines → also to Network page
        if "[API " in message or "HTTP" in message.upper():
            self._network_page.append_api_log(message)
    
    # ═══════════════════════════════════════════════════════════
    # PUBLIC API — backward compatible with AppController calls
    # ═══════════════════════════════════════════════════════════
    
    def append_log(self, message: str, level: str = "INFO"):
        """Append a log message (backward-compatible)."""
        self._logs_page.append_log(message, level)
    
    def update_queue_state(self, state: dict):
        """Update Queue State panel with live data."""
        self._queue_page.update_queue_state(state)
        # Update status bar
        total = state.get('total', 0)
        processing = state.get('processing', 0)
        completed = state.get('completed', 0)
        is_active = state.get('is_processing', False)
        status = "🟢 Active" if is_active else "⏸️ Stopped"
        self._status_label.setText(
            f"Engine: {status}  |  {processing} running  |  {completed}/{total} done"
        )
    
    @Slot()
    def update_queue_state_safe(self):
        """Thread-safe slot: re-gather queue state from controller and update."""
        if self.controller:
            state = self.controller.get_queue_status()
            self.update_queue_state(state)
    
    def update_json_preview(self, data: dict):
        """Update JSON Preview panel."""
        self._logs_page.update_json_preview(data)
    
    @Slot()
    def update_json_preview_safe(self):
        """Thread-safe slot: read stashed JSON preview from controller and update."""
        if self.controller and hasattr(self.controller, '_pending_json_preview'):
            data = self.controller._pending_json_preview
            if data:
                self._logs_page.update_json_preview(data)
    
    def update_performance(self, data: dict):
        """Update Performance panel."""
        self._queue_page.update_performance(data)
    
    def update_engine_dashboard(self, data: dict):
        """Update Engine Dashboard with aggregated monitoring data."""
        self._dashboard_page.update_dashboard(data)
        # Bug 11: Batch per-account data into single call (was 3 separate → 3 renders)
        self._accounts_page.update_engine_extras(
            data.get('prewarm'),
            data.get('circuit_breaker_status'),
            data.get('cooldowns'),
        )
    
    def update_browser_status(self, accounts: list):
        """Update browser status for all accounts."""
        self._accounts_page.update_browser_status(accounts)
    
    @Slot()
    def update_browser_status_safe(self):
        """Thread-safe slot: re-gather browser status and update."""
        if self.controller:
            accounts = self.controller.get_browser_status()
            self.update_browser_status(accounts)
    
    def update_pool_status(self, pools: list):
        """No-op — worker pool feature removed."""
        pass
    
    @Slot()
    def update_pool_status_safe(self):
        """No-op — worker pool feature removed."""
        pass
    
    def update_session_data(self, accounts: list):
        """Update Session Data panel with per-account token/cookie info."""
        self._accounts_page.update_session_data(accounts)
    
    @Slot()
    def update_session_data_safe(self):
        """Thread-safe slot: re-gather session data and update."""
        if self.controller:
            accounts = self.controller.get_session_data()
            self.update_session_data(accounts)
    
    def update_extension_status(self, status: dict):
        """Update Extension Bridge status."""
        self._network_page.update_extension_status(status)
        self._accounts_page.update_extension_status(status)
    
    @Slot()
    def update_extension_status_safe(self):
        """Thread-safe slot: re-gather extension status and update."""
        if self.controller:
            status = self.controller.get_extension_status()
            self.update_extension_status(status)

    # ═══════════════════════════════════════════════════════════
    # Per-Session Auto-Export
    # ═══════════════════════════════════════════════════════════

    def auto_export_session(self):
        """Export all Dev Console data to a timestamped session folder.
        
        Called automatically on app shutdown. Creates:
        data/dev_sessions/session_YYYYMMDD_HHMMSS/
        ├── logs.txt
        ├── json_preview.json
        ├── extension_messages.json
        ├── gemini_log.txt
        └── session_info.json
        """
        import json
        
        try:
            # Create session folder
            app_dir = Path(__file__).parent.parent
            session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = app_dir / "data" / "dev_sessions" / f"session_{session_ts}"
            session_dir.mkdir(parents=True, exist_ok=True)
            
            files_written = []
            
            # 1. Logs
            try:
                log_data = self._logs_page.get_export_data()
                if log_data["total_count"] > 0:
                    log_file = session_dir / "logs.txt"
                    with open(log_file, "w", encoding="utf-8") as f:
                        f.write(f"=== VEO Pro Max — Session Logs ===\n")
                        f.write(f"Session: {session_ts}\n")
                        f.write(f"Total: {log_data['total_count']} entries\n")
                        f.write("=" * 60 + "\n\n")
                        for line in log_data["logs"]:
                            f.write(line + "\n")
                    files_written.append("logs.txt")
                    
                    # JSON preview
                    jp = log_data.get("json_preview", "")
                    if jp and jp != "No tasks submitted yet.\n":
                        jp_file = session_dir / "json_preview.json"
                        with open(jp_file, "w", encoding="utf-8") as f:
                            f.write(jp)
                        files_written.append("json_preview.json")
            except Exception as e:
                print(f"[DevConsole] Logs export failed: {e}")
            
            # 2. Extension messages
            try:
                ext_data = self._extension_page.get_export_data()
                if ext_data:
                    ext_file = session_dir / "extension_messages.json"
                    with open(ext_file, "w", encoding="utf-8") as f:
                        json.dump(ext_data, f, indent=2, ensure_ascii=False, default=str)
                    files_written.append("extension_messages.json")
            except Exception as e:
                print(f"[DevConsole] Extension export failed: {e}")
            
            # 3. Gemini API log
            try:
                gemini_text = self._gemini_page.get_export_data()
                if gemini_text and gemini_text.strip():
                    gemini_file = session_dir / "gemini_log.txt"
                    with open(gemini_file, "w", encoding="utf-8") as f:
                        f.write(gemini_text)
                    files_written.append("gemini_log.txt")
            except Exception as e:
                print(f"[DevConsole] Gemini export failed: {e}")
            
            # 4. Session info
            info_file = session_dir / "session_info.json"
            with open(info_file, "w", encoding="utf-8") as f:
                json.dump({
                    "session_start": session_ts,
                    "export_time": datetime.now().isoformat(),
                    "files": files_written,
                }, f, indent=2)
            
            if files_written:
                print(f"[DevConsole] Session exported → {session_dir} ({len(files_written)} files)")
            else:
                # Nothing to export — remove empty folder
                import shutil
                shutil.rmtree(session_dir, ignore_errors=True)
                
        except Exception as e:
            print(f"[DevConsole] Session export error: {e}")
