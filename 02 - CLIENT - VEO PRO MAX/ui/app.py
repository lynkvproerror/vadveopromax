"""
VEO Pro Max - Main Application Window (PySide6)

Reference: 00_DESIGN_SYSTEM.md, TAB_xx specs
Migrated from CustomTkinter to PySide6.
"""

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QFrame, QStatusBar, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer
from PySide6.QtGui import QFont, QShortcut, QKeySequence

# Add project root to path if needed
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.theme import Theme
from ui.components.toast import ToastManager
from core.notification_manager import NotificationManager

# Import PySide6 tabs
from ui.tabs.tab_t2v import TabT2V
from ui.tabs.tab_i2v import TabI2V
from ui.tabs.tab_r2v import TabR2V
from ui.tabs.tab_t2i import TabT2I
from ui.tabs.tab_i2i import TabI2I
from ui.tabs.tab_queue import TabQueue
from ui.tabs.tab_settings import TabSettings
from ui.tabs.tab_license import TabLicense
from ui.tabs.tab_devconsole import TabDevConsole

if TYPE_CHECKING:
    from core.app_controller import AppController
    from config.settings import AppSettings


class MainWindow(QMainWindow):
    """Main VEO Pro Max application window (PySide6).
    
    Layout:
    ┌──────────────────────────────────────────────────────────────────────────────┐
    │ VEO Pro Max  │ [📹 T2V] │ 🎬 I2V │ ✏️ R2V │ 🎯 T2I │ ✨ I2I │ ...           │
    ├──────────────────────────────────────────────────────────────────────────────┤
    │ ⚙️ SIDEBAR (200px)  │ 📝 WORKSPACE (remaining width)                        │
    │                     │                                                        │
    │                     │                                                        │
    ├─────────────────────┴────────────────────────────────────────────────────────┤
    │ 📊 STATUS BAR (30px height)                                                  │
    └──────────────────────────────────────────────────────────────────────────────┘
    """
    
    # Thread-safe toast signal: (message, level, duration, audience)
    _toast_signal = Signal(str, str, int, str)
    
    # Thread-safe network status signal: (latency_ms, online)
    _net_signal = Signal(int, bool)
    
    def __init__(
        self,
        controller: Optional["AppController"] = None,
        settings: Optional["AppSettings"] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        
        # Store controller and settings
        self.controller = controller
        self.settings = settings
        
        # Track DevConsole visibility
        self._dev_console_visible = False
        
        # Status bar widgets for dynamic updates
        self._status_widgets = {}
        
        # Tab instances
        self.tab_instances = {}
        
        # Notification manager (sound playback)
        self._notification_manager = NotificationManager()
        
        # Setup UI
        self._setup_window()
        self._create_widgets()
        self._bind_hotkeys()
        self._connect_controller()
        
        # Restore previous session
        self._restore_session()
    
    def _setup_window(self):
        """Configure window properties."""
        self.setWindowTitle(f"{Theme.TAB_ICONS['T2V']} VEO Pro Max")
        
        # Window size
        self.resize(Theme.WINDOW_DEFAULT_WIDTH, Theme.WINDOW_DEFAULT_HEIGHT)
        self.setMinimumSize(Theme.WINDOW_MIN_WIDTH, Theme.WINDOW_MIN_HEIGHT)
    
    def _create_widgets(self):
        """Create main UI components."""
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Tab widget
        self.tabview = QTabWidget()
        self.tabview.setDocumentMode(True)
        self.tabview.tabBar().setExpanding(True)
        # Force tab bar to stretch full width
        from PySide6.QtWidgets import QSizePolicy
        self.tabview.tabBar().setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.tabview, stretch=1)
        
        # Define tabs with their actual PySide6 classes
        self.tab_defs = [
            ("Text to Video", "t2v", TabT2V),
            ("Image to Video", "i2v", TabI2V),
            ("Ingredients", "r2v", TabR2V),
            ("Text to Image", "t2i", TabT2I),
            ("Image to Image", "i2i", TabI2I),
            ("Queue", "queue", TabQueue),
            ("Settings", "settings", TabSettings),
            ("License", "license", TabLicense),
        ]
        
        # Create actual migrated tabs
        for tab_label, tab_key, tab_class in self.tab_defs:
            if tab_class:
                # Use migrated PySide6 tab
                tab_widget = tab_class(controller=self.controller)
            else:
                # Placeholder for tabs not yet migrated
                tab_widget = QWidget()
                tab_layout = QVBoxLayout(tab_widget)
                placeholder = QLabel(f"🚧 {tab_label} Tab\n\nMigration in progress...")
                placeholder.setAlignment(Qt.AlignCenter)
                placeholder.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 16px;")
                tab_layout.addWidget(placeholder)
            
            # Add tab
            icon = Theme.TAB_ICONS.get(tab_key.upper(), Theme.TAB_ICONS.get(tab_key.capitalize(), "📄"))
            self.tabview.addTab(tab_widget, f"{icon} {tab_label}")
            self.tab_instances[tab_key] = tab_widget
        
        # Status bar
        self._create_status_bar()
        
        # Toast notification manager
        self._toast_manager = ToastManager(self)
        self._toast_signal.connect(
            self._show_toast_on_main_thread,
            Qt.ConnectionType.UniqueConnection,
        )
        self._net_signal.connect(self._update_network_signal)
        
        # Wire tester mode from license (if controller available)
        self._sync_tester_mode()
    
    def _create_status_bar(self):
        """Create status bar at bottom."""
        status_bar = QStatusBar()
        status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {Theme.SURFACE0};
                color: {Theme.SUBTEXT0};
                min-height: 30px;
            }}
        """)
        self.setStatusBar(status_bar)
        
        # Left side: license status
        license_label = QLabel("🔑 N/A")
        license_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; margin-right: 8px;")
        status_bar.addWidget(license_label, stretch=1)
        self._status_widgets["license"] = license_label
        
        # Right side: permanent widgets
        items = [
            ("network", "📶 --"),
            ("version", f"v{self._get_version()}"),
            ("accounts", "🔄 0/0"),
            ("queue", "📋 0"),
            ("memory", "💾 0 MB"),
        ]
        
        for key, text in items:
            label = QLabel(text)
            label.setStyleSheet(f"color: {Theme.SUBTEXT0}; margin-right: 8px;")
            status_bar.addPermanentWidget(label)
            self._status_widgets[key] = label
    
    def _update_network_signal(self, latency_ms: int, online: bool):
        """Update network signal widget based on latency."""
        label = self._status_widgets.get("network")
        if not label:
            return
        if not online:
            label.setText("❌ Offline")
            label.setStyleSheet(f"color: {Theme.RED}; margin-right: 8px;")
        elif latency_ms < 100:
            label.setText(f"📶 {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.GREEN}; margin-right: 8px;")
        elif latency_ms < 300:
            label.setText(f"📶 {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.YELLOW}; margin-right: 8px;")
        elif latency_ms < 1000:
            label.setText(f"⚠️ {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.PEACH}; margin-right: 8px;")
        else:
            label.setText(f"❌ {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.RED}; margin-right: 8px;")
    
    def _check_connectivity_async(self):
        """Check internet connectivity in a background thread (non-blocking)."""
        import socket
        import time
        from concurrent.futures import ThreadPoolExecutor
        
        def _tcp_check():
            try:
                start = time.monotonic()
                sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
                sock.close()
                return int((time.monotonic() - start) * 1000), True
            except Exception:
                return 9999, False
        
        def _on_done(future):
            try:
                latency_ms, online = future.result()
            except Exception:
                latency_ms, online = 9999, False
            # Emit signal — safe from any thread, delivers to Qt main thread
            self._net_signal.emit(latency_ms, online)
        
        if not hasattr(self, '_net_executor'):
            self._net_executor = ThreadPoolExecutor(max_workers=1)
        
        future = self._net_executor.submit(_tcp_check)
        future.add_done_callback(_on_done)
    
    def _bind_hotkeys(self):
        """Bind keyboard shortcuts."""
        # Ctrl+Shift+D to toggle DevConsole
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        shortcut.activated.connect(self._toggle_dev_console)
    
    @Slot()
    def _toggle_dev_console(self):
        """Toggle DevConsole tab visibility."""
        if self._dev_console_visible:
            # Find and remove dev console tab
            for i in range(self.tabview.count()):
                if "Dev Console" in self.tabview.tabText(i):
                    self.tabview.removeTab(i)
                    break
            self._dev_console_visible = False
            # Stop performance timer + disconnect from controller
            if self.controller:
                if hasattr(self.controller, 'stop_perf_timer'):
                    self.controller.stop_perf_timer()
                if hasattr(self.controller, 'dev_console'):
                    self.controller.dev_console = None
            self.show_toast("DevConsole hidden", "info", audience="tester")
        else:
            # Add dev console tab (use actual migrated TabDevConsole)
            dev_widget = TabDevConsole(controller=self.controller)
            
            self.tabview.addTab(dev_widget, "🛠️ Dev Console")
            self.tabview.setCurrentWidget(dev_widget)
            self.tab_instances['devconsole'] = dev_widget
            
            # Wire to controller so it can push JSON/queue data
            if self.controller and hasattr(self.controller, 'dev_console'):
                self.controller.dev_console = dev_widget
                # Immediately push current status to DevConsole
                self.controller.push_status_updates()
                self.controller.start_perf_timer()
            
            self._dev_console_visible = True
            self.show_toast("DevConsole visible (Ctrl+Shift+D to hide)", "info", audience="tester")
    
    def _connect_controller(self):
        """Connect controller callbacks for UI updates."""
        if not self.controller:
            return
        
        # === CONTROLLER → UI CALLBACKS ===
        # Queue updates
        self.controller.set_queue_updated_callback(self._update_queue_status)
        
        # Task progress (forward to queue tab only)
        self.controller.set_progress_callback(self._on_progress)
        
        # Task completed/failed
        self.controller.set_task_completed_callback(self._on_task_completed)
        self.controller.set_task_failed_callback(self._on_task_failed)
        
        # Group completed (notification)
        self.controller.set_group_completed_callback(self._on_group_completed)
        
        # Status changes (controller start/stop, account events, errors)
        self.controller.set_status_callback(self._on_engine_status)
        
        # === INITIAL STATUS BAR DATA ===
        self._update_license_widget()
        self._poll_status_bar()  # Initial populate
        
        # === STATUS BAR POLLING TIMER (5s) ===
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(5000)
        self._status_timer.timeout.connect(self._poll_status_bar)
        self._status_timer.start()
        
        # === UI → CONTROLLER SIGNAL CONNECTIONS ===
        self._connect_tab_signals()
    
    def _connect_tab_signals(self):
        """Connect signals from tabs to controller methods."""
        # NOTE: Generation tabs (T2V, I2V, R2V, T2I, I2I) submit directly 
        # to controller via add_xxx_batch() — no signal wiring needed here.
        
        # Queue Tab
        if 'queue' in self.tab_instances:
            queue_tab = self.tab_instances['queue']
            if hasattr(queue_tab, 'start_all'):
                queue_tab.start_all.connect(self.controller.start_processing)
            if hasattr(queue_tab, 'pause_all'):
                queue_tab.pause_all.connect(self.controller.stop_processing)
            if hasattr(queue_tab, 'stop_all'):
                queue_tab.stop_all.connect(self.controller.stop_processing)
        
        # Settings Tab
        if 'settings' in self.tab_instances and hasattr(self.tab_instances['settings'], 'settings_changed'):
            self.tab_instances['settings'].settings_changed.connect(self._on_settings_changed)
    
    @Slot(str, int)
    def _on_progress(self, task_id: str, progress: int, status_text: str = ""):
        """Handle task progress update — forward to queue tab."""
        # Forward to queue tab for thumbnail slot gradient updates
        queue_tab = self.tab_instances.get('queue')
        if queue_tab and hasattr(queue_tab, '_on_progress_update_from_thread'):
            queue_tab._on_progress_update_from_thread(task_id, progress, status_text)
    
    @Slot(object)
    def _on_task_completed(self, task):
        """Handle task completion."""
        # Build descriptive notification with project name and prompt excerpt
        project = getattr(task, 'project_name', '') or 'Unknown'
        idx = getattr(task, 'prompt_index', 0) + 1  # 0-based → 1-based
        prompt = getattr(task, 'prompt', '')
        prompt_short = prompt[:40] + '...' if len(prompt) > 40 else prompt
        
        # Toast notification only (status_label removed)
        if not self.settings or getattr(self.settings, 'notify_toast_enabled', True):
            self.show_toast(f"✅ [{project}] #{idx}: \"{prompt_short}\"", "success")
    
    @Slot(object, str)
    def _on_task_failed(self, task, error: str):
        """Handle task failure."""
        project = getattr(task, 'project_name', '') or 'Unknown'
        idx = getattr(task, 'prompt_index', 0) + 1
        error_short = error[:50] + '...' if len(error) > 50 else error
        
        # Toast notification only (status_label removed)
        if not self.settings or getattr(self.settings, 'notify_toast_enabled', True):
            self.show_toast(f"❌ [{project}] #{idx}: {error_short}", "error")
    
    def _on_group_completed(self, group):
        """Handle group completion — toast + sound notification."""
        name = getattr(group, 'name', 'Unknown')
        task_count = len(group.tasks) if hasattr(group, 'tasks') else 0
        
        # In-app toast
        if self.settings and getattr(self.settings, 'notify_toast_enabled', True):
            self.show_toast(
                f"🎉 Group '{name}' completed ({task_count} tasks)",
                "success", 4000
            )
        
        # Sound notification
        if self.settings and getattr(self.settings, 'notify_sound_enabled', True):
            sound = getattr(self.settings, 'notify_sound_file', 'default')
            self._notification_manager.play(sound, duration_ms=4000)
    
    def _on_engine_status(self, status: str):
        """Handle status changes from AppController (16+ events).
        
        Events include: controller start/stop, account add/enable/disable,
        processing start/pause/resume/stop, license activation, errors.
        """
        import logging
        logging.getLogger("veo").info(f"[Status] {status}")
        if hasattr(self, 'show_toast'):
            self.show_toast(status, level="info", audience="tester")
    
    @Slot()
    def _on_clear_failed(self):
        """Handle clear failed tasks."""
        self.show_toast("Cleared failed tasks", "info", audience="tester")
    
    @Slot(dict)
    def _on_settings_changed(self, settings: dict):
        """Handle settings changed — propagate to sidebars for live-update."""
        if self.settings:
            # Update settings attributes from dict
            for key, value in settings.items():
                if hasattr(self.settings, key):
                    setattr(self.settings, key, value)
            self.settings.save()
        
        # Live-update all generation tab sidebars
        for tab_key in ("t2v", "i2v", "r2v", "t2i", "i2i"):
            tab = self.tab_instances.get(tab_key)
            if tab and hasattr(tab, 'sidebar') and hasattr(tab.sidebar, 'apply_defaults'):
                tab.sidebar.apply_defaults()
        
        self.show_toast("Settings updated → all tabs synced", "success", audience="tester")
    
    @Slot(dict)
    def _update_queue_status(self, status: dict):
        """Update status bar with queue info."""
        if "queue" in self._status_widgets:
            total = status.get("total", 0)
            self._status_widgets["queue"].setText(f"📋 {total}")
    
    def update_account_status(self, active: int, total: int):
        """Update account status in status bar."""
        if "accounts" in self._status_widgets:
            self._status_widgets["accounts"].setText(f"🔄 {active}/{total}")
    
    def update_license_status(self, status: str):
        """Update license status in status bar."""
        if "license" in self._status_widgets:
            self._status_widgets["license"].setText(f"🔑 {status}")
    
    def _update_license_widget(self):
        """Read license status from controller and update widget."""
        if not self.controller or not hasattr(self.controller, 'get_license_status'):
            return
        try:
            # Priority 1: Check hardcoded role (independent of Firebase)
            if hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                if hasattr(lc, 'can_see_dev_console') and lc.can_see_dev_console():
                    self.update_license_status("Tester")
                    return
            
            # Priority 2: Firebase-based license
            ls = self.controller.get_license_status()
            if ls.get("is_licensed"):
                tier = ls.get("tier", "PRO")
                self.update_license_status(tier)
            elif ls.get("is_trial"):
                days = ls.get("days_remaining", 0)
                self.update_license_status(f"Trial ({days}d)")
            elif ls.get("trial_expired"):
                self.update_license_status("Trial Expired")
            else:
                self.update_license_status("Unlicensed")
        except Exception:
            pass
    
    def _poll_status_bar(self):
        """Poll live data for status bar widgets (called by QTimer every 5s)."""
        if not self.controller:
            return
        
        # Accounts: ready / total
        try:
            acc = self.controller.get_account_summary()
            self.update_account_status(acc["ready"], acc["total"])
        except Exception:
            pass
        
        # Memory
        self._update_memory()
        
        # Network connectivity (threaded to avoid blocking UI)
        self._check_connectivity_async()
        
        # Worker pool status → DevConsole
        if hasattr(self.controller, 'push_status_updates'):
            self.controller.push_pool_status()  # Only pool status on timer, not full push
        
        # License status (may be N/A at init if _license_client not yet ready)
        self._update_license_widget()
    
    def _update_memory(self):
        """Update memory usage in status bar."""
        try:
            import psutil
            process = psutil.Process()
            mb = process.memory_info().rss / (1024 * 1024)
            if "memory" in self._status_widgets:
                self._status_widgets["memory"].setText(f"💾 {mb:.0f} MB")
        except Exception:
            pass
    
    @staticmethod
    def _get_version() -> str:
        """Read version from pyproject.toml."""
        try:
            import tomllib
            toml_path = Path(__file__).parent.parent / "pyproject.toml"
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            return data.get("project", {}).get("version", "?.?.?")
        except Exception:
            return "?.?.?"
    
    def set_status(self, message: str):
        """Update status bar message (no-op, status_label removed)."""
        pass
    
    def show_toast(self, message: str, level: str = "info", duration: int = 4000,
                   audience: str = "user"):
        """Show a floating toast notification (thread-safe).
        
        Args:
            audience: 'user' (visible to all) or 'tester' (system/technical, hidden in User mode)
        
        If called from main thread → direct call (avoids signal double-fire).
        If called from worker thread → emit signal for cross-thread delivery.
        """
        try:
            from PySide6.QtCore import QThread
            if QThread.currentThread() == self.thread():
                # Same thread — call directly, no signal needed
                self._show_toast_on_main_thread(message, level, duration, audience)
            else:
                # Cross-thread — use signal/slot for thread safety
                self._toast_signal.emit(message, level, duration, audience)
        except Exception as e:
            print(f"[Toast] Failed to show toast: {e}")
    
    @Slot(str, str, int, str)
    def _show_toast_on_main_thread(self, message: str, level: str, duration: int,
                                    audience: str = "user"):
        """Actually create and show the toast (runs on main thread via signal)."""
        try:
            self._toast_manager.show_toast(message, level, duration, audience=audience)
        except Exception as e:
            print(f"[Toast] Failed: {e}")
    
    def _sync_tester_mode(self):
        """Sync tester mode from license — call after controller is set."""
        try:
            if self.controller and hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                is_tester = hasattr(lc, 'can_see_dev_console') and lc.can_see_dev_console()
                self._toast_manager.set_tester_mode(is_tester)
        except Exception:
            pass  # Default: User mode (tester toasts hidden)
    
    # ── Session Persistence ─────────────────────────────────────
    
    def closeEvent(self, event):
        """Save session state and kill all Chrome before closing."""
        if self.controller:
            try:
                tabs_data = {}
                gen_tabs = ["t2v", "i2v", "r2v", "t2i", "i2i"]
                for key in gen_tabs:
                    tab = self.tab_instances.get(key)
                    if tab and hasattr(tab, 'save_state'):
                        tabs_data[key] = tab.save_state()
                
                self.controller.save_full_session(tabs_data)
                print(f"[App] Session saved ({len(tabs_data)} tabs)")
            except Exception as e:
                print(f"[App] Session save failed: {e}")
            
            # Kill all managed Chrome browsers on app exit
            try:
                pc = getattr(self.controller, '_profiles_controller', None)
                if pc and hasattr(pc, 'kill_all_debug_browsers'):
                    pc.kill_all_debug_browsers()
                    print("[App] All managed Chrome processes killed")
            except Exception as e:
                print(f"[App] Chrome cleanup failed: {e}")
        
        super().closeEvent(event)
    
    def _restore_session(self):
        """Restore session state on startup."""
        if not self.controller:
            print("[App] Session restore SKIPPED: no controller")
            return
        
        try:
            data = self.controller.restore_session()
            if not data:
                print("[App] Session restore SKIPPED: no session data")
                return
            
            tabs_data = data.get("tabs", {})
            restored_count = 0
            for key, tab_data in tabs_data.items():
                tab = self.tab_instances.get(key)
                if tab and hasattr(tab, 'restore_state'):
                    sidebar_data = tab_data.get("sidebar", {})
                    print(f"[App] Restoring tab '{key}': sidebar keys={list(sidebar_data.keys())}")
                    tab.restore_state(tab_data, restore_options=self.settings)
                    restored_count += 1
                else:
                    print(f"[App] Tab '{key}' not found or no restore_state method")
            
            queue_count = data.get("queue", {}).get("task_count", 0)
            saved_at = data.get("saved_at", "unknown")
            print(f"[App] Session restored: {restored_count}/{len(tabs_data)} tabs, {queue_count} queue tasks (from {saved_at})")
        except Exception as e:
            import traceback
            print(f"[App] Session restore FAILED: {e}")
            traceback.print_exc()


# For testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from config.theme import ThemeManager
    
    app = QApplication(sys.argv)
    
    # Apply theme
    theme_manager = ThemeManager()
    theme_manager.apply_to_app(app)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
