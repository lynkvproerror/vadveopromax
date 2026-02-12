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
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtGui import QFont, QShortcut, QKeySequence

# Add project root to path if needed
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.theme import Theme
from ui.components.toast import ToastManager

# Import PySide6 tabs
from ui.tabs.tab_t2v import TabT2V
from ui.tabs.tab_i2v import TabI2V
from ui.tabs.tab_r2v import TabR2V
from ui.tabs.tab_t2i import TabT2I
from ui.tabs.tab_i2i import TabI2I
from ui.tabs.tab_queue import TabQueue
from ui.tabs.tab_settings import TabSettings
from ui.tabs.tab_license import TabLicense
from ui.tabs.tab_about import TabAbout
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
    
    # Thread-safe toast signal: (message, level, duration)
    _toast_signal = Signal(str, str, int)
    
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
            ("About", "about", TabAbout),
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
        self._toast_signal.connect(self._show_toast_on_main_thread)
    
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
        
        # Left side: status message
        self.status_label = QLabel("Ready")
        status_bar.addWidget(self.status_label, stretch=1)
        
        # Right side: permanent widgets
        items = [
            ("version", "v2.0.0"),
            ("license", "🔑 N/A"),
            ("accounts", "🔄 0/0"),
            ("queue", "📋 0"),
            ("memory", "💾 0 MB"),
            ("progress", "📊 0%"),
        ]
        
        for key, text in items:
            label = QLabel(text)
            label.setStyleSheet(f"color: {Theme.SUBTEXT0}; margin-right: 8px;")
            status_bar.addPermanentWidget(label)
            self._status_widgets[key] = label
    
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
            # Disconnect from controller
            if self.controller and hasattr(self.controller, '_dev_console'):
                self.controller._dev_console = None
            self.set_status("DevConsole hidden")
        else:
            # Add dev console tab (use actual migrated TabDevConsole)
            dev_widget = TabDevConsole(controller=self.controller)
            
            self.tabview.addTab(dev_widget, "🛠️ Dev Console")
            self.tabview.setCurrentWidget(dev_widget)
            self.tab_instances['devconsole'] = dev_widget
            
            # Wire to controller so it can push JSON/queue data
            if self.controller and hasattr(self.controller, '_dev_console'):
                self.controller._dev_console = dev_widget
                # Immediately push current browser status + session data
                self.controller._push_browser_status()
                self.controller._push_session_data()
            
            self._dev_console_visible = True
            self.show_toast("DevConsole visible (Ctrl+Shift+D to hide)", "info")
    
    def _connect_controller(self):
        """Connect controller callbacks for UI updates."""
        if not self.controller:
            return
        
        # === CONTROLLER → UI CALLBACKS ===
        # Status updates
        self.controller.set_status_callback(self.set_status)
        
        # Queue updates
        self.controller.set_queue_updated_callback(self._update_queue_status)
        
        # Task progress
        self.controller.set_progress_callback(self._on_progress)
        
        # Task completed/failed
        self.controller.set_task_completed_callback(self._on_task_completed)
        self.controller.set_task_failed_callback(self._on_task_failed)
        
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
            if hasattr(queue_tab, 'clear_failed'):
                queue_tab.clear_failed.connect(self._on_clear_failed)
        
        # Settings Tab
        if 'settings' in self.tab_instances and hasattr(self.tab_instances['settings'], 'settings_changed'):
            self.tab_instances['settings'].settings_changed.connect(self._on_settings_changed)
    
    @Slot(str, int)
    def _on_progress(self, task_id: str, progress: int, status_text: str = ""):
        """Handle task progress update — status bar + forward to queue tab."""
        if "progress" in self._status_widgets:
            if status_text:
                self._status_widgets["progress"].setText(f"📊 {status_text} {progress}%")
            else:
                self._status_widgets["progress"].setText(f"📊 {progress}%")
        
        # Forward to queue tab for thumbnail slot gradient updates
        queue_tab = self.tab_instances.get('queue')
        if queue_tab and hasattr(queue_tab, '_on_progress_update_from_thread'):
            queue_tab._on_progress_update_from_thread(task_id, progress, status_text)
    
    @Slot(object)
    def _on_task_completed(self, task):
        """Handle task completion."""
        self.set_status(f"✅ Task completed: {task.id if hasattr(task, 'id') else task}")
        self.show_toast(f"Task completed: {task.id if hasattr(task, 'id') else task}", "success")
    
    @Slot(object, str)
    def _on_task_failed(self, task, error: str):
        """Handle task failure."""
        self.set_status(f"❌ Task failed: {error}")
        self.show_toast(f"Task failed: {error[:60]}", "error")
    
    @Slot()
    def _on_clear_failed(self):
        """Handle clear failed tasks."""
        self.show_toast("Cleared failed tasks", "info")
    
    @Slot(dict)
    def _on_settings_changed(self, settings: dict):
        """Handle settings changed."""
        if self.settings:
            # Update settings attributes from dict
            for key, value in settings.items():
                if hasattr(self.settings, key):
                    setattr(self.settings, key, value)
            self.settings.save()
            self.show_toast("Settings updated", "success")
    
    @Slot(dict)
    def _update_queue_status(self, status: dict):
        """Update status bar with queue info."""
        if "queue" in self._status_widgets:
            total = status.get("total", 0)
            self._status_widgets["queue"].setText(f"📋 {total}")
        
        if "progress" in self._status_widgets:
            completed = status.get("completed", 0)
            total = status.get("total", 1) or 1
            pct = int((completed / total) * 100) if total > 0 else 0
            self._status_widgets["progress"].setText(f"📊 {pct}%")
    
    def update_account_status(self, active: int, total: int):
        """Update account status in status bar."""
        if "accounts" in self._status_widgets:
            self._status_widgets["accounts"].setText(f"🔄 {active}/{total}")
    
    def update_license_status(self, status: str):
        """Update license status in status bar."""
        if "license" in self._status_widgets:
            self._status_widgets["license"].setText(f"🔑 {status}")
    
    def set_status(self, message: str):
        """Update status bar message."""
        try:
            self.status_label.setText(message)
        except RuntimeError:
            pass
    
    def show_toast(self, message: str, level: str = "info", duration: int = 4000):
        """Show a floating toast notification (thread-safe).
        
        Emits signal to ensure toast is always created on the main thread.
        QTimer and QPropertyAnimation require the main event loop.
        """
        try:
            self._toast_signal.emit(message, level, duration)
        except Exception as e:
            print(f"[Toast] Failed to emit signal: {e}")
    
    @Slot(str, str, int)
    def _show_toast_on_main_thread(self, message: str, level: str, duration: int):
        """Actually create and show the toast (runs on main thread via signal)."""
        try:
            self._toast_manager.show_toast(message, level, duration)
        except Exception as e:
            print(f"[Toast] Failed: {e}")
    
    # ── Session Persistence ─────────────────────────────────────
    
    def closeEvent(self, event):
        """Save session state before closing."""
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
        
        super().closeEvent(event)
    
    def _restore_session(self):
        """Restore session state on startup."""
        if not self.controller:
            return
        
        try:
            data = self.controller.restore_session()
            if not data:
                return
            
            tabs_data = data.get("tabs", {})
            for key, tab_data in tabs_data.items():
                tab = self.tab_instances.get(key)
                if tab and hasattr(tab, 'restore_state'):
                    tab.restore_state(tab_data)
            
            queue_count = data.get("queue", {}).get("task_count", 0)
            saved_at = data.get("saved_at", "unknown")
            print(f"[App] Session restored: {len(tabs_data)} tabs, {queue_count} queue tasks (from {saved_at})")
        except Exception as e:
            print(f"[App] Session restore failed: {e}")


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
