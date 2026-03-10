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
        if settings and getattr(settings, 'auto_update_enabled', True):
            try:
                from core.auto_updater import AutoUpdater
                self._auto_updater = AutoUpdater(self)
                self._auto_updater.update_available.connect(self._on_update_available)
                self._auto_updater.start_periodic_check()
            except Exception as e:
                log.debug(f"Auto-updater init failed: {e}")
        
        # 🔒 Min client version check (3s delay to let UI load)
        QTimer.singleShot(3000, self._check_min_version)
    
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
        
        # Wire tester mode from license (if controller available)
        self._sync_tester_mode()
        
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
        license_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; margin-right: 8px;")
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
        # 3.4: Feature gate — only TESTER role can open DevConsole
        if not self._dev_console_visible and self.controller:
            try:
                from services.permissions import Feature
                if not self.controller._permissions.has_feature(Feature.DEV_CONSOLE):
                    return  # Silently ignore for non-TESTER
            except Exception:
                pass
        
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
        """Update status bar with queue info."""
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
        
        label.setStyleSheet(f"color: {color}; margin-right: 8px;")
    
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
                self._status_widgets["accounts"].setStyleSheet(f"color: {color}; margin-right: 8px;")
        except Exception as e:
            import logging
            logging.getLogger("veo.ui").debug(f"[StatusBar] Accounts poll error: {e}")
        
        # Workers: running_tasks / total_capacity
        # Uses dispatcher._running_count (all tasks in RUNNING state).
        # Safe now that HardCap in get_next_task() prevents _per_account_running
        # from exceeding max_workers — guarantees _running_count ≤ total_capacity.
        # Note: session.active_workers would underreport (e.g., 16/40 vs 23 processing)
        # because T2I fire-and-forget releases workers immediately after submit.
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
                # 👷 = actual worker slots held | 📋 = tasks processing (incl. download/upscale with 0 workers)
                self._status_widgets["workers"].setText(f"👷 {active_workers}/{total_capacity}  📋 {running}")
                color = Theme.GREEN if running > 0 else Theme.SUBTEXT0
                self._status_widgets["workers"].setStyleSheet(f"color: {color}; margin-right: 8px;")
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
                    self._status_widgets["queue"].setStyleSheet(f"color: {color}; margin-right: 8px;")
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
                self._status_widgets["cpu"].setStyleSheet(f"color: {color}; margin-right: 8px;")
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
    
    def _check_min_version(self):
        """Check server-configured min version & maintenance mode.
        
        Fetches from Firebase _config/client_settings:
        - min_client_version: block if current < minimum
        - maintenance_mode: block if server is in maintenance
        """
        def _ver_tuple(v: str):
            """Parse version string to comparable tuple."""
            try:
                return tuple(int(x) for x in str(v).split('.')[:3])
            except (ValueError, AttributeError):
                return (0, 0, 0)
        
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
            
            if _ver_tuple(current) < _ver_tuple(min_ver):
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
            if self._auto_updater:
                self._auto_updater.check_now()
            else:
                import webbrowser
                webbrowser.open("https://github.com/lynkv/veo-pro-max/releases")
        
        # Force quit — version is too old
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
    
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
        
        # Force quit — server maintenance
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
    
    def set_status(self, message: str):
        """Update status bar message (no-op, status_label removed)."""
        pass
    
    def _on_update_available(self, info):
        """Handle auto-update available notification (from startup check)."""
        try:
            from config.i18n import t
            self.show_toast(
                f"🆕 {t('settings.update_sub.new_version')}: v{info.version}",
                "info", duration=8000
            )
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
