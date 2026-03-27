"""
VEO Pro Max - Main Application Window (PySide6)

Reference: 00_DESIGN_SYSTEM.md, TAB_xx specs
Migrated from CustomTkinter to PySide6.
"""

import os
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QFrame, QStatusBar, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer
from PySide6.QtGui import (
    QFont, QShortcut, QKeySequence, QIcon, QPixmap,
    QPainter, QPainterPath, QBrush, QColor
)

# Add project root to path if needed
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.theme import Theme
from config.i18n import t, set_language, get_signal as i18n_signal
from ui.components.toast import ToastManager
from core.notification_manager import NotificationManager

# Import PySide6 tabs
from ui.tabs.tab_project import TabProject
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
        self.setAcceptDrops(True)  # Required: register OLE IDropTarget on Windows for cross-window drag-drop
        
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
        
        # Init i18n from saved settings
        if settings:
            set_language(getattr(settings, 'ui_language', 'Tiếng Việt'))
        
        # Setup UI
        self._setup_window()
        self._create_widgets()
        self._bind_hotkeys()
        self._connect_controller()
        
        # Wire i18n hot-reload
        i18n_signal().connect(self._on_language_changed)
        
        # Restore previous session
        self._restore_session()
        
        # License countdown timer (1s) for status bar
        self._license_expires_dt = None  # cached expiry datetime
        self._license_tier_name = ""     # cached tier name
        self._was_licensed = False       # track revocation
        self._license_countdown_timer = QTimer(self)
        self._license_countdown_timer.setInterval(1000)
        self._license_countdown_timer.timeout.connect(self._update_license_countdown)
        
        # 🔒 Periodic license recheck timer (5 min) — detect mid-session revocation
        self._license_recheck_timer = QTimer(self)
        self._license_recheck_timer.setInterval(5 * 60 * 1000)  # 5 minutes
        self._license_recheck_timer.timeout.connect(self._update_license_widget)
        self._license_recheck_timer.start()
        
        # 🔄 Auto-Update check (if enabled in settings)
        self._auto_updater = None
        self._pending_update_active = False  # ★ R2-4: flag to prevent race
        if settings and getattr(settings, 'auto_update_enabled', True):
            try:
                from core.auto_updater import AutoUpdater
                self._auto_updater = AutoUpdater(self)
                self._auto_updater.update_available.connect(self._on_update_available)
                
                # Check for deferred updates (saved before reboot/exit)
                pending = AutoUpdater.check_pending_update()
                if pending:
                    print(f"[AutoUpdate] Pending update found: v{pending.get('version')}")
                    self._pending_update_active = True
                    QTimer.singleShot(3000, lambda: self._apply_pending_update(pending))
                else:
                    self._auto_updater.start_periodic_check()
            except Exception as e:
                print(f"[AutoUpdate] Auto-updater init failed: {e}")
        
        # 🔒 Min client version check (5s delay — after pending update dialog at 3s)
        QTimer.singleShot(5000, self._check_min_version)
    
    def _setup_window(self):
        """Configure window properties."""
        # Window title: all header info in title bar text
        self._update_window_title()
        
        # Set window icon from LOGO 3.png (rounded)
        logo_path = Path(__file__).parent / "img" / "LOGO 3.png"
        if logo_path.exists():
            icon_pixmap = self._make_rounded_pixmap(str(logo_path), 64)
            if icon_pixmap:
                self.setWindowIcon(QIcon(icon_pixmap))
        
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
            ("app.tabs.project", "project", TabProject),
            ("app.tabs.t2v", "t2v", TabT2V),
            ("app.tabs.i2v", "i2v", TabI2V),
            ("app.tabs.r2v", "r2v", TabR2V),
            ("app.tabs.t2i", "t2i", TabT2I),
            ("app.tabs.i2i", "i2i", TabI2I),
            ("app.tabs.queue", "queue", TabQueue),
            ("app.tabs.settings", "settings", TabSettings),
            ("app.tabs.license", "license", TabLicense),
        ]
        
        # Create actual migrated tabs
        for i18n_key, tab_key, tab_class in self.tab_defs:
            if tab_class:
                # Use migrated PySide6 tab
                tab_widget = tab_class(controller=self.controller)
            else:
                # Placeholder for tabs not yet migrated
                tab_widget = QWidget()
                tab_layout = QVBoxLayout(tab_widget)
                placeholder = QLabel(f"🚧 {t(i18n_key)} Tab\n\nMigration in progress...")
                placeholder.setAlignment(Qt.AlignCenter)
                placeholder.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 16px;")
                tab_layout.addWidget(placeholder)
            
            # Add tab (use i18n key for label)
            icon = Theme.TAB_ICONS.get(tab_key.upper(), Theme.TAB_ICONS.get(tab_key.capitalize(), "📄"))
            tab_label = t(i18n_key)  # Translate tab name
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
        
        
        
        # Update window title with subscriber name
        self._update_window_title()
    
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
        license_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; margin-right: 8px; font-weight: bold;")
        status_bar.addWidget(license_label, stretch=1)
        self._status_widgets["license"] = license_label
        
        # Right side: permanent widgets
        items = [
            ("network", "📶 --"),
            ("version", f"v{self._get_version()}"),
            ("accounts", "👤 0/0"),
            ("workers", "👷 0"),
            ("queue", "📋 0/0"),
            ("cpu", "💻 CPU --%"),
            ("memory", "💾 0 MB"),
        ]
        
        for key, text in items:
            label = QLabel(text)
            label.setStyleSheet(f"color: {Theme.SUBTEXT0}; margin-right: 8px; font-weight: bold;")
            status_bar.addPermanentWidget(label)
            self._status_widgets[key] = label
    
    def _update_network_signal(self, latency_ms: int, online: bool):
        """Update network signal widget based on latency."""
        label = self._status_widgets.get("network")
        if not label:
            return
        if not online:
            label.setText("❌ Offline")
            label.setStyleSheet(f"color: {Theme.RED}; margin-right: 8px; font-weight: bold;")
        elif latency_ms < 100:
            label.setText(f"📶 {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.GREEN}; margin-right: 8px; font-weight: bold;")
        elif latency_ms < 300:
            label.setText(f"📶 {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.YELLOW}; margin-right: 8px; font-weight: bold;")
        elif latency_ms < 1000:
            label.setText(f"⚠️ {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.PEACH}; margin-right: 8px; font-weight: bold;")
        else:
            label.setText(f"❌ {latency_ms}ms")
            label.setStyleSheet(f"color: {Theme.RED}; margin-right: 8px; font-weight: bold;")
    
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
        # Global Search & Replace (Notepad++ style popup)
        from ui.components.search_replace_bar import SearchReplaceBar
        self._search_bar = SearchReplaceBar(self)

        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(lambda: self._toggle_search(replace=False))

        replace_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        replace_shortcut.activated.connect(lambda: self._toggle_search(replace=True))

    def _toggle_search(self, replace: bool = False):
        """Show global Find/Replace dialog for current tab."""
        bar = self._search_bar

        # Get current tab's searchable widgets
        current_tab = self.tabview.currentWidget()
        widgets = []
        if hasattr(current_tab, 'get_searchable_widgets'):
            widgets = current_tab.get_searchable_widgets()

        if not widgets:
            return

        # Find focused widget or default to first
        from PySide6.QtWidgets import QApplication
        focused = QApplication.focusWidget()
        target = widgets[0]
        for w in widgets:
            if w is focused or (focused and w.isAncestorOf(focused)):
                target = w
                break

        bar.attach(target)
        bar.show_bar(replace=replace)
    
    def _show_dev_console(self):
        """Show DevConsole tab (auto-called on startup for Tester role).
        
        DevConsole is always visible for Tester — no toggle, no hide.
        This ensures logs are captured from the very start of the app.
        """
        if self._dev_console_visible:
            return  # Already showing
        
        # Feature gate — only TESTER role can see DevConsole
        if self.controller:
            try:
                from services.permissions import Feature
                if not self.controller._permissions.has_feature(Feature.DEV_CONSOLE):
                    return  # Not a Tester
            except Exception:
                pass
        
        # Add dev console tab
        dev_widget = TabDevConsole(controller=self.controller)
        
        self.tabview.addTab(dev_widget, "🛠️ Dev Console")
        self.tab_instances['devconsole'] = dev_widget
        
        # Wire to controller so it can push JSON/queue data
        if self.controller and hasattr(self.controller, 'dev_console'):
            self.controller.dev_console = dev_widget
            # Immediately push current status to DevConsole
            self.controller.push_status_updates()
            self.controller.start_perf_timer()
        
        self._dev_console_visible = True
    
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
        
        # === AUTO-SHOW DEV CONSOLE FOR TESTER ===
        # Show DevConsole immediately on startup so logs are captured from the beginning
        self._show_dev_console()
        
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
            if hasattr(queue_tab, 'stop_all'):
                queue_tab.stop_all.connect(self.controller.stop_processing)
        
        # Settings Tab
        if 'settings' in self.tab_instances and hasattr(self.tab_instances['settings'], 'settings_changed'):
            self.tab_instances['settings'].settings_changed.connect(self._on_settings_changed)
        
        # License → Settings: refresh role-based UI after license activation
        if 'license' in self.tab_instances and 'settings' in self.tab_instances:
            license_tab = self.tab_instances['license']
            settings_tab = self.tab_instances['settings']
            if hasattr(license_tab, 'license_activated') and hasattr(settings_tab, 'refresh_role_state'):
                license_tab.license_activated.connect(lambda key: settings_tab.refresh_role_state())
    
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
        """Handle group completion — toast + sound notification.
        
        Thread-safe: may be called from async engine thread.
        show_toast is already thread-safe (uses signal/slot).
        _notification_manager.play() creates QMediaPlayer/QTimer so must run on GUI thread.
        """
        name = getattr(group, 'name', 'Unknown')
        task_count = len(group.tasks) if hasattr(group, 'tasks') else 0
        
        # In-app toast (already thread-safe via signal)
        if self.settings and getattr(self.settings, 'notify_toast_enabled', True):
            self.show_toast(
                f"🎉 Group '{name}' completed ({task_count} tasks)",
                "success", 4000
            )
        
        # Sound notification — must run on GUI thread (QMediaPlayer has timers)
        if self.settings and getattr(self.settings, 'notify_sound_enabled', True):
            sound = getattr(self.settings, 'notify_sound_file', 'default')
            from PySide6.QtCore import QThread, QTimer
            if QThread.currentThread() != self.thread():
                QTimer.singleShot(0, lambda: self._notification_manager.play(sound, duration_ms=4000))
            else:
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
    
    def _on_language_changed(self, lang_code: str):
        """Hot-reload UI text when language changes (no restart needed)."""
        # 1. Update tab names
        for idx, (i18n_key, tab_key, _) in enumerate(self.tab_defs):
            icon = Theme.TAB_ICONS.get(tab_key.upper(), Theme.TAB_ICONS.get(tab_key.capitalize(), "📄"))
            self.tabview.setTabText(idx, f"{icon} {t(i18n_key)}")
        
        # 2. Notify tabs that have retranslate support
        for tab_key, tab in self.tab_instances.items():
            if hasattr(tab, 'retranslate_ui'):
                tab.retranslate_ui()
        
        # 3. Refresh window title with new language
        self._update_window_title()
        
        # 4. Refresh license status bar text
        self._update_license_widget()
    
    @Slot(dict)
    def _update_queue_status(self, status: dict):
        """Update status bar with queue info.
        
        Thread-safe: may be called from async engine thread via _notify_queue_updated.
        Defers QLabel.setText() to GUI thread when needed.
        """
        from PySide6.QtCore import QThread, QTimer
        if QThread.currentThread() != self.thread():
            # Marshal to GUI thread — QLabel can only be updated from its thread
            QTimer.singleShot(0, lambda s=status: self._update_queue_status(s))
            return
        if "queue" in self._status_widgets:
            completed = status.get("completed", 0)
            total = status.get("total", 0)
            self._status_widgets["queue"].setText(f"📋 {completed}/{total}")
    
    def update_account_status(self, active: int, total: int):
        """Update account status in status bar."""
        if "accounts" in self._status_widgets:
            self._status_widgets["accounts"].setText(f"👤 {active}/{total}")
    
    def update_license_status(self, status: str):
        """Update license status in status bar."""
        if "license" in self._status_widgets:
            self._status_widgets["license"].setText(f"🔑 {status}")
    
    def _update_license_widget(self):
        """Read license status from controller and cache expiry for countdown."""
        if not self.controller or not hasattr(self.controller, 'get_license_status'):
            return
        try:
            # Priority 1: Check hardcoded role (independent of Firebase)
            if hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                if hasattr(lc, 'can_see_dev_console') and lc.can_see_dev_console():
                    self.update_license_status("Administrator")
                    self._license_countdown_timer.stop()
                    return
            
            # Priority 2: Firebase-based license
            ls = self.controller.get_license_status()
            days = ls.get("days_remaining", 0)
            self._license_tier_name = ls.get("tier_name") or ls.get("tier", "PRO")
            expires_dt_str = ls.get("expires_dt")
            
            # Cache expiry datetime for countdown
            if expires_dt_str:
                try:
                    from datetime import datetime
                    self._license_expires_dt = datetime.fromisoformat(expires_dt_str)
                except Exception:
                    self._license_expires_dt = None
            
            if ls.get("is_licensed") and self._license_expires_dt:
                self._was_licensed = True
                tier_code = ls.get("tier", "")
                if tier_code == "LT":
                    # Lifetime: no countdown, just show ♾️
                    label = self._status_widgets.get("license")
                    if label:
                        label.setText(f"🔑 ♾️ {t('license.lifetime_label')}")
                        label.setStyleSheet(f"color: {Theme.GREEN}; margin-right: 8px; font-weight: bold;")
                    self._license_countdown_timer.stop()
                else:
                    # Normal tiers: start countdown timer
                    self._license_countdown_timer.start()
                    self._update_license_countdown()  # Immediate first update
            elif ls.get("is_licensed"):
                self._was_licensed = True
                self.update_license_status(str(self._license_tier_name))
                self._license_countdown_timer.stop()
            elif ls.get("is_trial"):
                self._was_licensed = True
                self.update_license_status(t("license.trial_remaining").replace("{days}", str(days)))
                self._license_countdown_timer.stop()
            elif ls.get("trial_expired"):
                self.update_license_status("Trial Expired")
                self._license_countdown_timer.stop()
                if self._was_licensed:
                    self._on_license_revoked(t("license.trial_expired_msg"))
            else:
                self.update_license_status("Unlicensed")
                self._license_countdown_timer.stop()
                if self._was_licensed:
                    self._on_license_revoked(t("license.revoked_msg"))
        except Exception:
            pass
        
        # Refresh window title (subscriber name may have loaded)
        self._update_window_title()
    
    def _on_license_revoked(self, reason: str):
        """Show blocking dialog when license is revoked mid-session."""
        self._was_licensed = False
        self._license_countdown_timer.stop()
        
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle(f"⛔ {t('license.revoked_title')}")
        msg.setText(
            f"🚫 {reason}\n\n"
            f"{t('license.revoked_body')}"
        )
        msg.setIcon(QMessageBox.Critical)
        
        activate_btn = msg.addButton(f"🔑 {t('license.enter_new_key')}", QMessageBox.AcceptRole)
        exit_btn = msg.addButton(f"❌ {t('license.exit_app')}", QMessageBox.RejectRole)
        
        msg.exec()
        
        if msg.clickedButton() == activate_btn:
            # Open license tab for re-activation
            tab_count = self.tab_widget.count()
            self.tab_widget.setCurrentIndex(tab_count - 1)  # License = last tab
        else:
            # Exit app
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
    
    def _update_license_countdown(self):
        """Update license status bar with live countdown + color (called every 1s)."""
        if not self._license_expires_dt:
            return
        
        from datetime import datetime
        now = datetime.now()
        remaining = self._license_expires_dt - now
        total_secs = int(remaining.total_seconds())
        
        label = self._status_widgets.get("license")
        if not label:
            return
        
        if total_secs <= 0:
            label.setText(f"🔑 ❌ {t('license.expired_msg')}")
            label.setStyleSheet(f"color: {Theme.RED}; margin-right: 8px; font-weight: bold;")
            self._license_countdown_timer.stop()
            return
        
        days = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins = (total_secs % 3600) // 60
        secs = total_secs % 60
        
        exp_date = self._license_expires_dt.strftime("%d/%m/%Y")
        tier = self._license_tier_name
        
        # Countdown text
        if days > 0:
            countdown = f"{days}d {hours:02d}:{mins:02d}:{secs:02d}"
        else:
            countdown = f"{hours:02d}:{mins:02d}:{secs:02d}"
        
        text = f"🔑 {tier} — {t('license.remaining_time')} {countdown} ({t('license.expires_on')} {exp_date})"
        label.setText(text)
        
        # Color based on urgency
        if days >= 7:
            color = Theme.GREEN
        elif days >= 3:
            color = Theme.YELLOW
        elif days >= 1:
            color = Theme.PEACH
        else:
            color = Theme.RED
        
        label.setStyleSheet(f"color: {color}; margin-right: 8px; font-weight: bold;")
    
    def _poll_status_bar(self):
        """Poll live data for status bar widgets (called by QTimer every 5s)."""
        if not self.controller:
            return
        
        # One-time safety: if runtime pool is empty but profiles exist, trigger sync
        # ⚡ FIX: run sync in background async loop instead of blocking main thread.
        # sync_profiles_to_runtime() has future.result(timeout=15.0) which blocks UI.
        if not getattr(self, '_sync_triggered', False):
            try:
                acc = self.controller.get_account_summary()
                if acc.get("total", 0) == 0:
                    pc = getattr(self.controller, '_profiles_controller', None)
                    if pc and hasattr(pc, 'get_all_profiles'):
                        profiles = pc.get_all_profiles()
                        if profiles:
                            import logging
                            logging.getLogger("veo.ui").info(
                                f"[StatusBar] Runtime pool empty but {len(profiles)} profiles exist — triggering async sync"
                            )
                            # ⚡ FIX: Don't block main thread — schedule in async loop
                            if hasattr(self.controller, '_loop') and self.controller._loop:
                                import asyncio
                                async def _bg_sync():
                                    self.controller.sync_profiles_to_runtime()
                                asyncio.run_coroutine_threadsafe(_bg_sync(), self.controller._loop)
                            else:
                                self.controller.sync_profiles_to_runtime()
                self._sync_triggered = True
            except Exception:
                pass
        
        # Accounts: ready / total
        try:
            acc = self.controller.get_account_summary()
            total = acc["total"]
            ready = acc["ready"]
            
            # Fallback: if runtime pool is empty, read from ProfilesController
            if total == 0:
                pc = getattr(self.controller, '_profiles_controller', None)
                if pc and hasattr(pc, 'get_all_profiles'):
                    try:
                        profiles = pc.get_all_profiles()
                        total = len(profiles)
                        ready = sum(1 for p in profiles if p.get('is_ready', False))
                    except Exception:
                        pass
            
            if "accounts" in self._status_widgets:
                self._status_widgets["accounts"].setText(f"👤 {ready}/{total}")
                if total == 0:
                    color = Theme.SUBTEXT0
                elif ready == 0:
                    color = Theme.YELLOW  # Accounts added but not ready
                else:
                    color = Theme.GREEN
                self._status_widgets["accounts"].setStyleSheet(f"color: {color}; margin-right: 8px; font-weight: bold;")
        except Exception as e:
            import logging
            logging.getLogger("veo.ui").debug(f"[StatusBar] Accounts poll error: {e}")
        
        # Workers: true processing count + worker slots
        try:
            acc = self.controller.get_account_summary()
            running = acc.get("running_tasks", 0)
            active_workers = acc.get("active_workers", 0)
            # Get total capacity from multi_account manager
            total_capacity = 0
            try:
                ma = getattr(self.controller, '_multi_account', None)
                if ma:
                    total_capacity = ma.total_capacity
            except Exception:
                pass
            
            if "workers" in self._status_widgets:
                # ★ Pool Separation: show Fast ops + LP ops + upscale counts
                active_upscale = acc.get("active_upscale", 0)
                max_upscale = acc.get("max_upscale", 4)
                active_lp = acc.get("active_workers_lp", 0)
                max_lp = acc.get("max_workers_lp", 8)
                # Fast workers = total active ops minus LP workers
                active_fast = max(0, active_workers - active_lp)
                self._status_widgets["workers"].setText(
                    f"⚡ {active_fast}/{total_capacity} "
                    f"| 🐢 {active_lp}/{max_lp} "
                    f"| ⬆️ {active_upscale}/{max_upscale} "
                )
                color = Theme.GREEN if active_workers > 0 else Theme.SUBTEXT0
                self._status_widgets["workers"].setStyleSheet(f"color: {color}; margin-right: 8px; font-weight: bold;")
        except Exception as e:
            import logging
            logging.getLogger("veo.ui").debug(f"[StatusBar] Workers poll error: {e}")
        
        # Queue: completed / total prompts
        try:
            if hasattr(self.controller, 'get_queue_groups'):
                groups = self.controller.get_queue_groups()
                total_prompts = 0
                completed_prompts = 0
                for g in groups:
                    for t in g.get('tasks', []):
                        total_prompts += 1
                        if t.get('status') == 'completed' or t.get('progress', 0) >= 100:
                            completed_prompts += 1
                if "queue" in self._status_widgets:
                    self._status_widgets["queue"].setText(f"📋 {completed_prompts}/{total_prompts}")
                    if total_prompts > 0:
                        color = Theme.GREEN if completed_prompts == total_prompts else Theme.BLUE
                    else:
                        color = Theme.SUBTEXT0
                    self._status_widgets["queue"].setStyleSheet(f"color: {color}; margin-right: 8px; font-weight: bold;")
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
        """Update memory and CPU usage in status bar."""
        try:
            import psutil
            process = psutil.Process()
            mb = process.memory_info().rss / (1024 * 1024)
            if "memory" in self._status_widgets:
                self._status_widgets["memory"].setText(f"💾 {mb:.0f} MB")
            
            # CPU usage (system-wide)
            cpu_pct = psutil.cpu_percent(interval=None)  # non-blocking
            if "cpu" in self._status_widgets:
                self._status_widgets["cpu"].setText(f"💻 CPU {cpu_pct:.0f}%")
                if cpu_pct > 80:
                    color = Theme.RED
                elif cpu_pct > 50:
                    color = Theme.YELLOW
                else:
                    color = Theme.SUBTEXT0
                self._status_widgets["cpu"].setStyleSheet(f"color: {color}; margin-right: 8px; font-weight: bold;")
        except Exception:
            pass
    
    @staticmethod
    def _get_version() -> str:
        """Get app version from AppConstants (canonical source, same as auto-updater)."""
        try:
            from config.constants import AppConstants
            return AppConstants.APP_VERSION
        except Exception:
            return "?.?.?"
    
    
    def _apply_pending_update(self, pending: dict):
        """Apply a deferred full update on startup.
        
        Guards against version downgrade (if user manually updated since).
        Shows confirm dialog, then applies or discards.
        """
        try:
            from core.auto_updater import AutoUpdater, compare_versions
            from config.constants import AppConstants
            # ★ R17-1: Import logging at top of try (was inside L855 branch → NameError
            #   when pending version IS newer and code reaches L871/L910/L924)
            import logging
            
            pending_ver = pending.get("version", "0.0.0")
            current_ver = AppConstants.APP_VERSION
            
            # Guard: skip if pending version <= current (already updated or would downgrade)
            if compare_versions(current_ver, pending_ver) >= 0:
                logging.getLogger('veo').info(
                    f"Pending update v{pending_ver} skipped — "
                    f"current v{current_ver} is same or newer"
                )
                AutoUpdater.clear_pending_update()
                self._pending_update_active = False
                if self._auto_updater:
                    self._auto_updater.start_periodic_check()
                return
            
            # ★ R11-5: Verify ZIP still exists before prompting user
            zip_path = pending.get("zip_path", "")
            if not zip_path or not os.path.exists(zip_path):
                logging.getLogger('veo').warning(f"Pending update ZIP missing: {zip_path}")
                self.show_toast(
                    "❌ Pending update file missing — discarded.",
                    "error", duration=5000
                )
                AutoUpdater.clear_pending_update()
                self._pending_update_active = False
                if self._auto_updater:
                    self._auto_updater.start_periodic_check()
                return
            
            from ui.popups import show_confirm
            pending_type = pending.get("update_type", "full")
            if pending_type == "installer":
                pending_title = "🔄 Pending Installer"
                pending_body = (
                    f"Installer v{pending_ver} was downloaded previously.\n\n"
                    f"• Yes — Run installer now\n"
                    f"• No — Skip this update"
                )
            else:
                pending_title = "🔄 Pending Update"
                pending_body = (
                    f"v{pending_ver} was downloaded previously.\n\n"
                    f"• Yes — Install now and restart\n"
                    f"• No — Skip this update"
                )
            answer = show_confirm(self, pending_title, pending_body)
            
            if answer and self._auto_updater:
                # ★ R14-4: Reset flag BEFORE apply (if apply_update fails internally,
                # flag would stay True forever, blocking _check_min_version)
                self._pending_update_active = False
                # ★ R6-2: Re-verify SHA-256 before applying deferred ZIP
                expected_sha = pending.get("sha256", "")
                if expected_sha:
                    import hashlib
                    sha = hashlib.sha256()
                    try:
                        # ★ R12-3: Use verified local zip_path (not raw dict key)
                        with open(zip_path, "rb") as zf:
                            while True:
                                chunk = zf.read(1024 * 1024)
                                if not chunk:
                                    break
                                sha.update(chunk)
                        actual = sha.hexdigest()
                        if actual.lower() != expected_sha.lower():
                            logging.getLogger('veo').warning(
                                f"Pending ZIP SHA mismatch! Expected {expected_sha[:16]}... got {actual[:16]}..."
                            )
                            self.show_toast(
                                "❌ Pending update file corrupted — discarded.",
                                "error", duration=5000
                            )
                            AutoUpdater.clear_pending_update()
                            self._pending_update_active = False
                            if self._auto_updater:
                                self._auto_updater.start_periodic_check()
                            return
                    except Exception as e:
                        # ★ R8-5: SHA verify exception → treat as corrupt, don't fall through
                        logging.getLogger('veo').warning(f"SHA verify failed for pending ZIP: {e}")
                        self.show_toast(
                            "❌ Pending update file inaccessible — discarded.",
                            "error", duration=5000
                        )
                        AutoUpdater.clear_pending_update()
                        self._pending_update_active = False
                        if self._auto_updater:
                            self._auto_updater.start_periodic_check()
                        return
                
                self.show_toast(
                    f"📦 Installing v{pending_ver}...", "info", duration=3000
                )
                # ★ R12-3: Use verified local zip_path consistently
                if pending_type == "installer":
                    self._auto_updater.apply_installer_update(zip_path)
                else:
                    self._auto_updater.apply_update(zip_path)
            elif answer and not self._auto_updater:
                # ★ R17-5: User chose "Install" but updater is gone — show error, keep ZIP
                logging.getLogger('veo').error(
                    "User chose to install pending update but _auto_updater is None"
                )
                self.show_toast(
                    "❌ Update system unavailable — restart app to retry.",
                    "error", duration=5000
                )
                self._pending_update_active = False
            else:
                # User skipped → clear pending + start normal checks
                AutoUpdater.clear_pending_update()
                self._pending_update_active = False
                if self._auto_updater:
                    self._auto_updater.start_periodic_check()
        except Exception as e:
            import logging
            logging.getLogger('veo').error(f"Pending update apply failed: {e}")
            from core.auto_updater import AutoUpdater
            AutoUpdater.clear_pending_update()
            self._pending_update_active = False
            if self._auto_updater:
                self._auto_updater.start_periodic_check()
    
    def _check_min_version(self):
        """Check server-configured min version & maintenance mode.
        
        Fetches from Firebase _config/client_settings:
        - min_client_version: block if current < minimum
        - maintenance_mode: block if server is in maintenance
        """
        # ★ R2-4+R6-3+R7-3: Skip if pending update dialog is active, retry in 5s (max 3 retries)
        if getattr(self, '_pending_update_active', False):
            retries = getattr(self, '_min_version_retries', 0)
            if retries < 3:
                self._min_version_retries = retries + 1
                import logging
                logging.getLogger('veo').debug(
                    f"[VersionCheck] Deferred — pending update active (retry {retries+1}/3)"
                )
                QTimer.singleShot(5000, self._check_min_version)
                return
            # Max retries exhausted — proceed anyway
            import logging
            logging.getLogger('veo').warning(
                "[VersionCheck] Max retries exhausted — running check despite pending flag"
            )
        
        # ★ R8-1: Reset retry counter on successful entry
        self._min_version_retries = 0
        
        # ★ R4-4: Use compare_versions (has E8 safe_int) instead of fragile _ver_tuple
        from core.auto_updater import compare_versions as _cmp_ver
        
        try:
            from security.firebase_rest_client import FirebaseRESTClient
            import logging
            log = logging.getLogger('veo')
            client = FirebaseRESTClient()
            
            # Check maintenance mode (strict bool — string "false" must not trigger)
            raw_maint = client.get_config_value("maintenance_mode", False)
            maintenance = raw_maint is True or str(raw_maint).lower() == "true"
            if maintenance:
                log.warning("[MaintenanceCheck] Server is in maintenance mode — blocking!")
                self._show_maintenance_block()
                return
            
            # Check min version
            min_ver = str(client.get_config_value("min_client_version", "1.0.0"))
            current = self._get_version()
            
            if _cmp_ver(current, min_ver) < 0:
                log.warning(f"[VersionCheck] App {current} < min {min_ver} — blocking!")
                self._show_version_block(current, min_ver)
            else:
                log.debug(f"[VersionCheck] OK: {current} >= {min_ver}")
            
            # Apply server-controlled feature flags (e.g., ai_prompt_trial_enabled)
            if self.controller and hasattr(self.controller, '_permissions'):
                full_config = client.fetch_client_config()
                self.controller._permissions.apply_server_features(full_config)
                log.debug(f"[FeatureFlags] Applied server features (ai_prompt_trial={full_config.get('ai_prompt_trial_enabled', False)})")
        except Exception as e:
            import logging
            logging.getLogger('veo').debug(f"Min version check failed: {e}")
    
    def _show_version_block(self, current: str, minimum: str):
        """Show blocking dialog when app version is below minimum."""
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtCore import Qt
        msg = QMessageBox(self)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(t("app_dialogs.update_required_title"))
        msg.setText(
            f"<b>{t('app_dialogs.version_too_old').replace('{current}', current)}</b><br><br>"
            f"{t('app_dialogs.min_version_required').replace('{minimum}', minimum)}<br><br>"
            f"{t('app_dialogs.update_to_continue')}"
        )
        update_btn = msg.addButton(t("app_dialogs.update_now"), QMessageBox.AcceptRole)
        quit_btn = msg.addButton(t("app_dialogs.exit"), QMessageBox.RejectRole)
        msg.exec()
        
        if msg.clickedButton() == update_btn:
            # ★ R2-1: Open browser to downloads page instead of check_now()+quit race
            import webbrowser
            target_url = "https://github.com/lynkvproerror/vadveopromax/releases"
            try:
                info = getattr(self._auto_updater, "latest_info", None)
                if info and getattr(info, "installer_url", ""):
                    target_url = info.installer_url
            except Exception:
                pass
            webbrowser.open(target_url)
        
        # ★ E2: Hard exit — QApplication.quit() can be bypassed by closeEvent.ignore()
        QTimer.singleShot(100, lambda: self._force_exit_with_cleanup(0))
    
    def _show_maintenance_block(self):
        """Show blocking dialog when server is in maintenance mode."""
        from PySide6.QtWidgets import QMessageBox
        from PySide6.QtCore import Qt
        msg = QMessageBox(self)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle(t("app_dialogs.maintenance_title"))
        msg.setText(
            f"<b>{t('app_dialogs.maintenance_msg')}</b><br><br>"
            f"{t('app_dialogs.maintenance_retry')}<br>"
            f"{t('app_dialogs.maintenance_sorry')}"
        )
        msg.addButton(t("popups.ok"), QMessageBox.AcceptRole)
        msg.exec()
        
        # ★ E2: Hard exit — QApplication.quit() can be bypassed by closeEvent.ignore()
        QTimer.singleShot(100, lambda: self._force_exit_with_cleanup(0))
    
    @staticmethod
    def _force_exit_with_cleanup(code: int = 0):
        """Hard exit that releases SingleInstance mutex first.
        
        os._exit() skips finally blocks, so we must release
        the mutex explicitly to prevent 'already running' errors.
        """
        try:
            from core.single_instance import release_global
            release_global()
        except Exception:
            pass
        os._exit(code)
    
    def set_status(self, message: str):
        """Update status bar message (no-op, status_label removed)."""
        pass
    
    def _on_update_available(self, info):
        """Handle auto-update available notification (from startup check).
        
        ★ R4-1: Single canonical handler for both full and ext_only types.
        """
        try:
            if info.update_type == "full":
                msg = f"🆕 Full Update v{info.version} available!"
            elif info.update_type == "installer":
                msg = f"🆕 Installer Update v{info.version} available!"
            elif info.update_type == "ext_only":
                msg = f"🆕 Extension v{info.ext_version} update available!"
            else:
                return
            self.show_toast(msg, "info", duration=8000)
        except Exception:
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
    
    # ── Window Title & Icon ────────────────────────────────────────
    
    @staticmethod
    def _make_rounded_pixmap(image_path: str, size: int) -> 'QPixmap':
        """Load an image and clip it to a circle (rounded)."""
        try:
            source = QPixmap(image_path)
            if source.isNull():
                return None
            # Scale to square
            source = source.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            # Center crop to exact size
            if source.width() > size or source.height() > size:
                x = (source.width() - size) // 2
                y = (source.height() - size) // 2
                source = source.copy(x, y, size, size)
            # Circle mask
            rounded = QPixmap(size, size)
            rounded.fill(QColor(0, 0, 0, 0))
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.Antialiasing, True)
            path = QPainterPath()
            path.addEllipse(0, 0, size, size)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, source)
            painter.end()
            return rounded
        except Exception:
            return None
    
    def _update_window_title(self):
        """Build and set the window title bar text with all header info.
        
        Greeting is picked ONCE at first call and cached for the session.
        Only changes on app restart.
        """
        import random
        from config.contact_provider import get_contact_info

        # Get subscriber name
        client_name = ""
        try:
            if self.controller and hasattr(self.controller, '_license_client'):
                lc = self.controller._license_client
                if hasattr(lc, 'get_client_name'):
                    client_name = lc.get_client_name() or ""
        except Exception:
            pass
        
        if client_name:
            welcome = t("app.welcome").replace("{name}", client_name)
        else:
            welcome = t("app.welcome_default")
        
        # Pick greeting ONCE per session (cached until restart)
        if not hasattr(self, '_cached_greeting'):
            greetings = t("app.greetings")
            self._cached_greeting = random.choice(greetings) if isinstance(greetings, list) and greetings else ""
        greeting = self._cached_greeting
        
        # Get contact info from secure provider
        contact = get_contact_info()
        phone = contact.get("phone", "N/A")
        zalo = contact.get("zalo", "N/A")
        
        parts = [f"VEO PRO MAX  -  {welcome}"]
        if greeting:
            parts[0] += f", {greeting}"
        parts.append(f"{t('app.contact_support')}:  \u260E: {phone}  |  Zalo: {zalo}")
        
        self.setWindowTitle("  -  ".join(parts))
    
    # ── Session Persistence ─────────────────────────────────────
    
    def closeEvent(self, event):
        """Save session state and kill all Chrome before closing.
        
        Stops all timers FIRST to prevent callbacks accessing destroyed widgets,
        then does session save, then Chrome cleanup in background thread.
        """
        # ── Phase 0: Stop ALL QTimers immediately ──
        # Prevents timer callbacks from accessing destroyed widgets during close
        for timer_attr in ('_status_timer', '_license_countdown_timer', 
                           '_license_recheck_timer', '_integrity_timer'):
            timer = getattr(self, timer_attr, None)
            if timer and hasattr(timer, 'stop'):
                try:
                    timer.stop()
                except Exception:
                    pass
        
        if self.controller:
            # ── Phase 1: Save session (fast, sync) ──
            try:
                tabs_data = {}
                gen_tabs = ["t2v", "i2v", "r2v", "t2i", "i2i", "project"]
                for key in gen_tabs:
                    tab = self.tab_instances.get(key)
                    if tab and hasattr(tab, 'save_state'):
                        tabs_data[key] = tab.save_state()
                
                self.controller.save_full_session(tabs_data)
                print(f"[App] Session saved ({len(tabs_data)} tabs)")
            except Exception as e:
                print(f"[App] Session save failed: {e}")
            
            # Auto-export Dev Console data (per-session)
            try:
                dev_tab = self.tab_instances.get('devconsole')
                if dev_tab and hasattr(dev_tab, 'auto_export_session'):
                    dev_tab.auto_export_session()
            except Exception as e:
                print(f"[App] DevConsole export failed: {e}")
            
            # ── Phase 2: Kill Chrome in background thread (non-blocking) ──
            # Avoids time.sleep(1) blocking the UI thread
            try:
                pc = getattr(self.controller, '_profiles_controller', None)
                if pc and hasattr(pc, 'kill_all_debug_browsers'):
                    import threading
                    def _bg_kill():
                        try:
                            pc.kill_all_debug_browsers()
                            print("[App] All managed Chrome processes killed")
                        except Exception as e:
                            print(f"[App] Chrome cleanup failed: {e}")
                    
                    kill_thread = threading.Thread(target=_bg_kill, daemon=True)
                    kill_thread.start()
                    # Wait up to 3s — but don't block forever
                    kill_thread.join(timeout=3.0)
                    if kill_thread.is_alive():
                        print("[App] Chrome cleanup still running — proceeding with exit")
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
