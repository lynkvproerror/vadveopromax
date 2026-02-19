"""
VEO Pro Max - App Controller

Central controller connecting UI with core engine.
"""

from typing import Optional, Dict, Any, Callable, List
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
import threading
import logging
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Core imports
from core.session import AccountSession
from core.multi_account import MultiAccountManager
from core.account_manager import AccountManager
from core.dispatcher import Dispatcher, Task, TaskGroup, TaskState
from core.worker import Worker, WorkerResult
from core.api_client import VEOApiClient
from core.auth_manager import AuthManager
from core.error_handler import ErrorHandler
from core.session_monitor import SessionMonitor, SessionEvent
from core.refresh_manager import CookieRefreshManager
from core.batch_parser import BatchParser, ParsedPrompt
from core.import_validator import ImportValidator
from core.download_manager import DownloadManager
from core.engine import Engine
from core.log_exporter import LogExporter

# Services
from services.license_client import LicenseClient
from services.permissions import PermissionsSystem, Role, Feature

# Config
from config.settings import AppSettings
from config.constants import WorkflowType, resolve_model_key

log = logging.getLogger(__name__)


def _wf_display(wt) -> str:
    """Extract clean display name from workflow_type (enum or string)."""
    if hasattr(wt, 'name'):
        return wt.name  # WorkflowType enum → "T2V"
    s = str(wt)
    if '.' in s:
        return s.split('.')[-1]  # "WorkflowType.T2V" → "T2V"
    return s.upper()


class AppState:
    """Application state container."""
    
    def __init__(self):
        self.is_running = False
        self.is_processing = False
        self.current_workflow: Optional[str] = None
        self.active_account: Optional[str] = None
        self.queue_count = 0
        self.completed_count = 0
        self.error_count = 0


class AppController:
    """Central controller for VEO Pro Max.
    
    Connects UI components with core engine modules.
    Manages application lifecycle and state.
    """
    
    def __init__(self, settings: Optional[AppSettings] = None):
        # Settings
        self.settings = settings or AppSettings()
        
        # State
        self.state = AppState()
        
        # Core components
        self._multi_account = MultiAccountManager()
        self._dispatcher = Dispatcher()
        self._api_client = VEOApiClient()
        self._auth_manager = AuthManager()
        self._error_handler = ErrorHandler()
        self._session_monitor = SessionMonitor()
        self._refresh_manager = CookieRefreshManager()
        self._download_manager = DownloadManager()
        self._batch_parser = BatchParser()
        self._import_validator = ImportValidator()
        
        # Services
        self._license_client = LicenseClient()
        self._permissions = PermissionsSystem()
        
        # Engine — replaces manual threading.Thread worker management
        # Engine uses asyncio.TaskGroup for proper async worker coroutines
        self._engine = Engine(
            account_manager=self._multi_account,
            dispatcher=self._dispatcher,
            api_client=self._api_client,
        )
        
        # Task persistence (crash recovery) + stuck task detection
        from core.task_journal import TaskJournal
        from core.task_watchdog import TaskWatchdog
        from core.status_aggregator import StatusAggregator
        self._task_journal = TaskJournal(
            dispatcher=self._dispatcher,
            save_dir=Path("sessions"),
            interval_sec=30.0,
        )
        self._task_watchdog = TaskWatchdog(
            dispatcher=self._dispatcher,
            engine=self._engine,
        )
        self._status_aggregator = StatusAggregator()
        
        # Log exporter — auto-exports structured session logs (TESTER only)
        self._log_exporter = LogExporter(
            base_dir=Path("logs")
        )
        
        # Event callbacks (set by UI)
        self._on_task_completed: Optional[Callable[[Task], None]] = None
        self._on_task_failed: Optional[Callable[[Task, str], None]] = None
        self._on_progress: Optional[Callable[[str, int], None]] = None
        self._on_queue_updated: List[Callable[[Dict], None]] = []
        self._on_account_changed: Optional[Callable[[str], None]] = None
        self._on_status_changed: Optional[Callable[[str], None]] = None
        self._on_group_completed: Optional[Callable] = None  # Group completion notification
        self._notified_groups: set = set()  # Track notified group IDs
        
        # DevConsole reference (set by UI via set_dev_console)
        self._dev_console = None
        # NOTE: self.settings is set in __init__ line 78 from constructor arg.
        # self._settings is the PRIVATE alias used by some methods (restore_session, cache).
        # Wire them to avoid the stale-None bug.
        self._settings = self.settings
        
        # Performance tracking
        self._start_time = datetime.now()
        self._perf_timer = None  # QTimer, started when DevConsole opens
        
        # Async event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._engine_future = None  # Track engine.start() Future for clean shutdown
        
        # ProfilesController reference (set by UI via set_profiles_controller)
        self._profiles_controller = None
        
        # Extension bridge — WebSocket server for Chrome Extension tokens
        from core.extension_bridge import ExtensionBridge
        self._extension_bridge = ExtensionBridge(port=8765)
        self._extension_bridge.on_headers_update = self._on_extension_headers_update
        self._extension_bridge.on_extension_connect = self._on_extension_connect
        self._extension_bridge.on_unregistered_connection = self._on_unregistered_extension
        
        # Wire extension bridge into RefreshManager for auto header refresh
        self._refresh_manager.set_extension_bridge(self._extension_bridge)
        
        # Image Enhancer — GPU detection (background) + model management (portable)
        from core.gpu_detector import GPUDetector
        from core.model_manager import ModelManager
        from core.image_enhancer import ImageEnhancer
        self._gpu_detector = GPUDetector(auto_start=True)
        self._model_manager = ModelManager()
        self._image_enhancer = ImageEnhancer(
            gpu_detector=self._gpu_detector,
            model_manager=self._model_manager,
        )
        
        # Splash screen callbacks
        self._splash_progress_cb = None   # fn(int, str) → update progress
        self._splash_finish_cb = None     # fn() → close splash
        
        # Setup callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Setup internal callbacks between components."""
        # Dispatcher callbacks
        self._dispatcher.set_callbacks(
            on_completed=self._handle_task_completed,
            on_failed=self._handle_task_failed,
        )
        
        # Session monitor
        self._session_monitor.set_expired_callback(self._handle_session_expired)
    
    # === LIFECYCLE ===
    
    def start(self):
        """Start the application controller."""
        if self.state.is_running:
            return
        
        self.state.is_running = True
        
        # Start async loop in background
        self._start_async_loop()
        
        # Start Extension bridge WebSocket server
        if self._loop:
            try:
                future = asyncio.run_coroutine_threadsafe(self._extension_bridge.start(), self._loop)
                future.result(timeout=5.0)  # Wait and catch any startup errors
                log.info("[AppController] Extension bridge started on ws://127.0.0.1:8765")
                print("[AppController] ✅ Extension bridge started on ws://127.0.0.1:8765")
            except Exception as e:
                log.error(f"[AppController] ❌ Extension bridge failed to start: {e}")
                print(f"[AppController] ❌ Extension bridge failed: {e}")
        else:
            log.error("[AppController] ❌ Async loop not ready — bridge not started")
            print("[AppController] ❌ Async loop not ready — bridge not started")
        
        # Start session monitoring
        self._session_monitor.start_monitoring()
        
        # Start refresh manager
        self._refresh_manager.start_auto_check()
        
        # Check license
        self._update_permissions()
        
        # Start TaskJournal (event subscriber + periodic save)
        self._task_journal.start(loop=self._loop)
        self._status_aggregator.start()
        
        # Crash recovery: load journal snapshot if available
        snapshot = self._task_journal.load_snapshot()
        if snapshot and snapshot.get("task_count", 0) > 0:
            recovered = self._dispatcher.import_state(snapshot)
            if recovered > 0:
                log.info(f"[AppController] Recovered {recovered} tasks from journal")
                print(f"[AppController] \u2705 Recovered {recovered} tasks from crash journal")
        
        self._notify_status("Controller started")
    
    def set_splash_callback(self, cb):
        """Set splash progress callback: cb(percent: int, status: str)."""
        self._splash_progress_cb = cb
    
    def set_splash_finish_callback(self, cb):
        """Set splash finish callback: cb() → close splash."""
        self._splash_finish_cb = cb
    
    def _splash_update(self, pct: int, msg: str):
        """Thread-safe splash progress update via QTimer."""
        if self._splash_progress_cb:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._splash_progress_cb(pct, msg))
    
    def _splash_done(self):
        """Thread-safe splash finish via QTimer."""
        if self._splash_finish_cb:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._splash_finish_cb)
    
    def stop(self):
        """Stop the application controller."""
        # Stop processing first (awaits engine shutdown properly)
        if self.state.is_processing:
            self.stop_processing()
        
        self.state.is_running = False
        
        # Stop monitoring
        self._session_monitor.stop_monitoring()
        self._refresh_manager.stop_auto_check()
        
        # Stop task journal (final save on shutdown)
        self._task_journal.stop()
        self._task_watchdog.stop()
        self._status_aggregator.stop()
        
        # Stop Extension bridge
        if self._loop and self._extension_bridge:
            asyncio.run_coroutine_threadsafe(self._extension_bridge.stop(), self._loop)
        
        # Stop async loop (safe now — engine already stopped)
        self._stop_async_loop()
        
        self._notify_status("Controller stopped")
    
    def _on_extension_headers_update(self, email: str, headers: Dict[str, str], access_token: str = None):
        """Callback from ExtensionBridge when new headers are received."""
        # Find the account manager for this email and update session headers
        account = self._multi_account.get_account(email)
        if account:
            # Use session.update_browser_headers() — has x-client-data downgrade guard
            account._session.update_browser_headers(
                browser_validation=headers.get("x-browser-validation", account._session.browser_validation),
                client_data=headers.get("x-client-data", account._session.client_data),
                browser_channel=headers.get("x-browser-channel", account._session.browser_channel),
                browser_copyright=headers.get("x-browser-copyright", account._session.browser_copyright),
                browser_year=headers.get("x-browser-year", account._session.browser_year),
            )
            # Extension-only: session stores headers as the authoritative source
            # Store SAPISIDHASH authorization header if provided
            if access_token and access_token.startswith("SAPISIDHASH"):
                account._session._sapisidhash = access_token
                log.debug(f"[ExtensionBridge] SAPISIDHASH stored for {email}")
            log.info(f"[ExtensionBridge] Headers updated for {email}: {list(headers.keys())}")
            
            # Cross-pollinate: if this account now has good x-client-data,
            # share it with other accounts that have short values
            new_cd = headers.get("x-client-data", "")
            if len(new_cd) >= 20:
                self._multi_account.fix_short_client_data()
            
            self._push_session_data()  # Refresh Dev Console instantly
        else:
            log.debug(f"[ExtensionBridge] No account found for {email} (headers ignored)")
    
    def _on_extension_connect(self, email: str):
        """Callback from ExtensionBridge when an extension connects.
        
        Immediately requests fresh headers + access token so the app
        has data right away without waiting for the next auto-check cycle.
        """
        log.info(f"[ExtensionBridge] Extension connected for {email}")
        self._notify_status(f"Extension connected for {email}")
        self._push_session_data()  # Instant DevConsole refresh
        
        # Immediate data refresh — don't wait for auto-check
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(self._refresh_extension_data(email))
        except RuntimeError:
            asyncio.run(self._refresh_extension_data(email))
        except Exception as e:
            log.debug(f"[ExtensionBridge] Startup refresh scheduling failed: {e}")
    
    def _on_unregistered_extension(self):
        """Callback from ExtensionBridge when a connection hasn't registered after 5s.
        
        Iterates known profiles and assigns emails to any unregistered connections.
        This handles late-connecting extensions that missed Step 5's initial assignment.
        """
        import asyncio
        
        async def _assign_pending():
            profiles = (
                self._profiles_controller.get_all_profiles()
                if hasattr(self, '_profiles_controller') and self._profiles_controller
                else []
            )
            for p in profiles:
                email = p.get("email")
                if email and not self._extension_bridge.is_connected(email):
                    log.info(f"[AutoAssign] 📧 Late-assign email: {email}")
                    assigned = await self._extension_bridge.assign_email(email)
                    if assigned:
                        self._push_browser_status()
                        self._push_extension_status()
                        self._push_session_data()
        
        try:
            asyncio.ensure_future(_assign_pending())
        except Exception as e:
            log.error(f"[AutoAssign] Failed: {e}")
    
    async def _refresh_extension_data(self, email: str):
        """Request fresh headers + access token from extension immediately."""
        try:
            # 1. Refresh headers (triggers VEO tab reload → fresh x-browser-*)
            await self._extension_bridge.refresh_headers(email, timeout=10)
            log.info(f"[ExtensionBridge] ✅ Startup headers refreshed for {email}")
        except Exception as e:
            log.debug(f"[ExtensionBridge] Startup header refresh failed: {e}")
        
        try:
            # 2. Get fresh access token
            result = await self._extension_bridge.request_access_token(email, timeout=10)
            if result and result.get('token'):
                account = self._multi_account.get_account(email)
                if account:
                    from datetime import timedelta
                    account._session.access_token = result['token']
                    account._session.token_expires = datetime.now() + timedelta(minutes=55)
                    log.info(f"[ExtensionBridge] ✅ Startup access token set for {email}")
        except Exception as e:
            log.debug(f"[ExtensionBridge] Startup token fetch failed: {e}")
    
    def _auto_launch_browsers(self):
        """Auto-launch browsers for all profiles in background.
        
        Runs AFTER splash is closed and main window is visible.
        Browser status is pushed to DevConsole via _push_browser_status().
        
        Startup sequence (single browser per profile):
        1. Sync profiles to runtime
        2. Inject ProfilesController ref into each AccountManager
        3. Open debug browsers in hidden mode (the ONLY browser per profile)
        4. startup_browsers() → AccountManager.ensure_browser() attaches
           to the already-running debug browser (no new headless browser)
        5. Token + reCAPTCHA extracted from the shared browser page
        """
        import logging
        log = logging.getLogger(__name__)
        
        async def _launch():
            try:
                # Step 1: Sync profiles
                self.sync_profiles_to_runtime()
                log.info("[AutoLaunch] Profiles synced to runtime")
                
                # Step 2: Inject ProfilesController + ExtensionBridge
                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                    for acc in self._multi_account._accounts:
                        acc.set_profiles_controller(self._profiles_controller)
                        acc._extension_bridge = self._extension_bridge
                    log.info(f"[AutoLaunch] ProfilesController + ExtensionBridge injected into {len(self._multi_account._accounts)} accounts")
                
                # Step 3: Open debug browsers
                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                    profiles = self._profiles_controller.get_all_profiles()
                    ready_profiles = [p for p in profiles if p.get("email") and p.get("is_ready")]
                    total = len(ready_profiles)
                    
                    for idx, p in enumerate(ready_profiles):
                        email = p.get("email")
                        log.info(f"[AutoLaunch] 🔇 Starting hidden browser {idx+1}/{total}: {email}...")
                        
                        success = self._profiles_controller.open_browser_for_debug(
                            email, 
                            on_state_change=self._on_debug_browser_state_change
                        )
                        
                        if success:
                            # Brief yield — browser thread starts in background
                            await asyncio.sleep(1)
                            self._profiles_controller.hide_debug_browser(email)
                            log.info(f"[AutoLaunch] ✅ {email} browser hidden")
                        else:
                            log.warning(f"[AutoLaunch] ⚠️ Failed to open browser for {email}")
                    
                    self._push_browser_status()
                
                # Step 4: Connect accounts (ensure_browser polls until page ready)
                if self._multi_account._accounts:
                    log.info(f"[AutoLaunch] Connecting {len(self._multi_account._accounts)} accounts to debug browsers...")
                    await self._multi_account.startup_browsers(headless=True)
                    log.info("[AutoLaunch] ✅ All accounts connected to browsers")
                else:
                    log.info("[AutoLaunch] No accounts to connect")
                
                # Step 5: Assign emails to unregistered extension connections
                # (fallback when content.js email detection fails on VEO page)
                if self._extension_bridge:
                    await asyncio.sleep(3)  # Wait for extensions to connect
                    profiles = self._profiles_controller.get_all_profiles() if hasattr(self, '_profiles_controller') and self._profiles_controller else []
                    for p in profiles:
                        email = p.get("email")
                        if email and not self._extension_bridge.is_connected(email):
                            log.info(f"[AutoLaunch] 📧 Assigning email to unregistered extension: {email}")
                            await self._extension_bridge.assign_email(email)
                    
                    connected = self._extension_bridge.get_connected_emails()
                    log.info(f"[AutoLaunch] Extension status: {len(connected)} emails registered: {connected}")
                
                self._push_browser_status()
                log.info("[AutoLaunch] ✅ Background browser launch complete")
                    
            except Exception as e:
                log.error(f"[AutoLaunch] Failed to launch browsers: {e}")
        
        # Run in background async loop
        if self._loop:
            asyncio.run_coroutine_threadsafe(_launch(), self._loop)
    
    def _push_browser_status(self):
        """Push current browser status to DevConsole (thread-safe).
        
        Can be called from any thread. Uses QMetaObject.invokeMethod
        to ensure the actual Qt widget update runs on the GUI thread.
        """
        if not hasattr(self, '_dev_console') or not self._dev_console:
            return
        
        status = self.get_browser_status()
        
        # Use QMetaObject to safely update from any thread
        from PySide6.QtCore import QMetaObject, Qt, QThread
        from functools import partial
        
        if QThread.currentThread() == self._dev_console.thread():
            # Already on GUI thread — safe to call directly
            self._dev_console.update_browser_status(status)
        else:
            # Background thread — schedule on GUI thread
            QMetaObject.invokeMethod(
                self._dev_console, "update_browser_status_safe",
                Qt.ConnectionType.QueuedConnection
            )
    
    def _push_pool_status(self):
        """Push worker pool status to DevConsole (thread-safe)."""
        if not hasattr(self, '_dev_console') or not self._dev_console:
            return
        
        from PySide6.QtCore import QMetaObject, Qt, QThread
        
        if QThread.currentThread() == self._dev_console.thread():
            pools = self.get_pool_status()
            self._dev_console.update_pool_status(pools)
        else:
            QMetaObject.invokeMethod(
                self._dev_console, "update_pool_status_safe",
                Qt.ConnectionType.QueuedConnection
            )
    
    def get_extension_status(self) -> dict:
        """Get Extension Bridge status for DevConsole."""
        if hasattr(self, '_extension_bridge') and self._extension_bridge:
            return self._extension_bridge.get_status()
        return {}
    
    def _push_extension_status(self):
        """Push extension bridge status to DevConsole (thread-safe)."""
        if not hasattr(self, '_dev_console') or not self._dev_console:
            return
        
        from PySide6.QtCore import QMetaObject, Qt, QThread
        
        if QThread.currentThread() == self._dev_console.thread():
            status = self.get_extension_status()
            self._dev_console.update_extension_status(status)
        else:
            QMetaObject.invokeMethod(
                self._dev_console, "update_extension_status_safe",
                Qt.ConnectionType.QueuedConnection
            )
    
    def _on_debug_browser_state_change(self, email: str, state: str):
        """Callback when a debug browser changes state (visible/hidden/closed).
        
        Called from background browser thread. Thread-safe via _push_browser_status.
        """
        self._push_browser_status()
        self._push_session_data()
        self._push_extension_status()
    
    def restart_browser_for(self, email: str) -> bool:
        """Kill and relaunch Chrome browser for a specific account.
        
        Thread-safe. Called from UI thread via background thread.
        
        Returns:
            True if restart succeeded, False otherwise
        """
        import time
        
        pc = self._profiles_controller
        if not pc:
            log.error("[AppController] No ProfilesController — cannot restart browser")
            return False
        
        log.info(f"[AppController] 🔁 Restarting browser for {email}...")
        print(f"[AppController] 🔁 Restarting browser for {email}...")
        
        # Step 1: Kill existing browser
        try:
            pc.kill_debug_browser(email)
            log.info(f"[AppController] Chrome killed for {email}")
        except Exception as e:
            log.error(f"[AppController] kill_debug_browser error: {e}")
        
        time.sleep(3)
        
        # Step 2: Relaunch browser
        try:
            pc.open_browser_for_debug(
                email,
                on_state_change=self._on_debug_browser_state_change,
            )
            log.info(f"[AppController] ✅ Browser relaunched for {email}")
        except Exception as e:
            log.error(f"[AppController] ❌ open_browser_for_debug error: {e}")
            return False
        
        # Step 3: Push updated status
        self._push_browser_status()
        self._push_extension_status()
        return True
    
    def hot_reload_app(self):
        """Restart the entire Python process.
        
        Gracefully stops engine and event manager, then spawns
        a new `python main.py` process and exits the current one.
        Chrome browsers persist (PID files) and will be reconnected.
        """
        import subprocess as _sp
        
        log.info("[AppController] 🔄 Hot reload: stopping services...")
        print("[AppController] 🔄 Hot reload: stopping services...")
        
        # Step 1: Stop engine gracefully
        try:
            self.stop()
        except Exception as e:
            log.warning(f"[AppController] stop() error during reload: {e}")
        
        # Step 2: Stop event manager
        try:
            from core.event_manager import get_event_manager
            get_event_manager().stop_processor()
        except Exception:
            pass
        
        # Step 3: Spawn new process
        main_py = str(Path(__file__).resolve().parent.parent / "main.py")
        python_exe = sys.executable
        log.info(f"[AppController] Spawning: {python_exe} {main_py}")
        
        creation_flags = _sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP
        _sp.Popen(
            [python_exe, main_py],
            creationflags=creation_flags,
            close_fds=True,
            cwd=str(Path(main_py).parent),
        )
        
        # Step 4: Exit current process
        log.info("[AppController] 🔄 Exiting current process for hot reload...")
        import os
        os._exit(0)
    

    def get_browser_status(self) -> list:
        """Get browser status for all accounts.
        
        Combines runtime account data with ProfilesController profiles
        and debug browser state so the DevConsole shows accurate info.
        
        Returns list of dicts: [{email, state, enabled, slots, has_browser,
                                  isolation, master_profile, worker_details}, ...]
        """
        result = []
        seen_emails = set()
        
        # Try runtime accounts first (have browser session data)
        if self._multi_account._accounts:
            for acc in self._multi_account._accounts:
                seen_emails.add(acc.email)
                # Check debug browser state via ProfilesController
                debug_state = "closed"
                if (hasattr(self, '_profiles_controller') 
                    and self._profiles_controller):
                    debug_state = self._profiles_controller.get_debug_browser_state(acc.email)
                
                has_browser = bool(acc._browser_session and acc._browser_session.is_ready) or debug_state != "closed"
                
                if debug_state == "visible":
                    state = "🟢 Visible"
                elif debug_state == "hidden":
                    state = "🟡 Hidden"
                elif acc._browser_session and acc._browser_session.is_ready:
                    state = "🟢 Ready"
                else:
                    state = "⚪ Off"
                
                info = {
                    "email": acc.email,
                    "enabled": acc.is_enabled,
                    "slots": acc.max_slots,
                    "has_browser": has_browser,
                    "state": state,
                }
                
                result.append(info)
        
        # Also show profiles not yet in runtime (or fallback if no runtime accounts)
        if hasattr(self, '_profiles_controller') and self._profiles_controller:
            profiles = self._profiles_controller.get_all_profiles()
            for p in profiles:
                email = p.get("email", "?")
                if email in seen_emails:
                    continue
                
                debug_state = self._profiles_controller.get_debug_browser_state(email)
                
                if debug_state == "visible":
                    state = "🟢 Visible"
                elif debug_state == "hidden":
                    state = "🟡 Hidden"
                elif p.get("is_ready"):
                    state = "🟡 Profile"
                else:
                    state = "🔴 Not Ready"
                
                info = {
                    "email": email,
                    "enabled": p.get("is_ready", False),
                    "slots": 4,
                    "has_browser": debug_state != "closed",
                    "state": state,
                    "isolation": False,
                }
                result.append(info)
        
        return result
    
    def get_pool_status(self) -> list:
        """Get worker pool status for all accounts.
        
        No longer used — clone profile feature removed.
        Kept for API compatibility with DevConsole.
        """
        return []
    
    def toggle_account(self, email: str, enabled: bool):
        """Enable or disable an account.
        
        Called from Settings UI when user toggles the account switch.
        """
        # Update profile on disk
        if self._profiles_controller:
            self._profiles_controller.update_profile(email, is_enabled=enabled)
        
        # Update runtime AccountManager
        acc = self._multi_account.get_account(email)
        if acc:
            if enabled:
                acc.enable()
            else:
                acc.disable()
        
        log.info(f"[AppController] Account {email} {'enabled' if enabled else 'disabled'}")
    
    def set_account_max_slots(self, email: str, value: int):
        """Set max concurrent workers for an account.
        
        Called from Settings UI when user changes the slots spinner.
        """
        acc = self._multi_account.get_account(email)
        if acc:
            acc.set_max_slots(value)
        
        log.info(f"[AppController] Account {email} max_slots → {value}")
    
    def get_session_data(self) -> list:
        """Get session data (tokens, cookies, profile info) for all accounts.
        
        Prioritizes runtime AccountManager session data (actual production tokens)
        over tokens.json cache. Falls back to tokens.json if runtime not loaded.
        """
        import sqlite3
        import shutil
        import tempfile
        import uuid
        
        result = []
        
        if not hasattr(self, '_profiles_controller') or not self._profiles_controller:
            return result
        
        # Build runtime account lookup: email → AccountManager
        runtime_accounts = {}
        if self._multi_account._accounts:
            for acc in self._multi_account._accounts:
                runtime_accounts[acc.email] = acc
        
        # Fallback: load tokens.json for accounts not in runtime
        tokens_data = {}
        tokens_path = self._profiles_controller.storage_path.parent / "tokens.json"
        if tokens_path.exists():
            try:
                with open(tokens_path, 'r', encoding='utf-8') as f:
                    tokens_data = json.load(f)
            except Exception:
                pass
        
        from datetime import datetime
        
        for profile in self._profiles_controller._profiles:
            email = profile.email
            runtime_acc = runtime_accounts.get(email)
            
            # Check debug browser state early (used by both branches)
            debug_state = self._profiles_controller.get_debug_browser_state(email)
            debug_browser_active = debug_state in ("visible", "hidden")
            
            if runtime_acc:
                # ═══ RUNTIME DATA (actual production state) ═══
                status = runtime_acc.get_status()
                
                # Extension connection status
                ext_connected = (
                    self._extension_bridge and 
                    self._extension_bridge.is_connected(email)
                )
                
                # Session status — extension-only architecture
                if runtime_acc.is_ready:
                    session_status = "🟢 Ready (Production)"
                elif ext_connected:
                    session_status = "🟢 Session via Extension"
                elif runtime_acc.is_enabled:
                    session_status = "🟡 Enabled (Waiting Extension)"
                else:
                    session_status = "🔴 Disabled"
                
                # Access token: runtime first, fallback to tokens.json
                rt_token = runtime_acc._session.access_token or ""
                token_info = tokens_data.get(email, {})
                refresh_token = token_info.get("refresh_token", "")
                updated_at = token_info.get("updated_at", "")
                
                if rt_token:
                    access_token = rt_token
                    # Token freshness from runtime
                    if status.get("token_expired"):
                        token_expiry = "🔄 Expired (auto-refresh on next call)"
                    else:
                        try:
                            expires = runtime_acc._session.token_expires
                            if expires:
                                left = (expires - datetime.now()).total_seconds()
                                mins = max(0, int(left / 60))
                                token_expiry = f"✅ Live ({mins}m left)"
                            else:
                                token_expiry = "✅ Live"
                        except Exception:
                            token_expiry = "✅ Live"
                else:
                    # No runtime token — check tokens.json cache
                    cached_token = token_info.get("access_token", "")
                    expires_at = token_info.get("expires_at", 0)
                    now_ts = datetime.now().timestamp()
                    
                    # Bug fix: ignore stale cached tokens (>24h old)
                    # Showing "259h ago" is confusing — treat as no token
                    cache_age_hours = abs(expires_at - now_ts) / 3600 if expires_at else float('inf')
                    
                    if cached_token and expires_at and cache_age_hours <= 24:
                        # Cached token is recent enough to display
                        access_token = cached_token
                        if (expires_at - now_ts) <= 0:
                            hours_ago = int(cache_age_hours)
                            token_expiry = f"🔄 Cached token ({hours_ago}h ago)"
                        else:
                            mins = int((expires_at - now_ts) / 60)
                            token_expiry = f"✅ Cached ({mins}m left)"
                    elif ext_connected:
                        # Extension connected — token will be extracted on demand
                        access_token = ""
                        token_expiry = "🟢 Will extract via Extension on next call"
                    else:
                        access_token = ""
                        token_expiry = "❌ No token (Extension not connected)"
                
                # reCAPTCHA
                recaptcha_age = status.get("recaptcha_age", "N/A")
                needs_recaptcha = status.get("needs_recaptcha")
                if recaptcha_age == "infs" or recaptcha_age == "N/A":
                    if ext_connected:
                        recaptcha_status = "🟢 Will fetch via Extension on demand"
                    else:
                        recaptcha_status = "❌ Extension not connected"
                elif needs_recaptcha:
                    recaptcha_status = f"🔄 Need refresh (age: {recaptcha_age})"
                else:
                    recaptcha_status = f"✅ Valid (age: {recaptcha_age})"
                
                # Browser session (headless)
                browser_alive = status.get("browser_alive", False)
                
                # Slots
                slots_display = status.get("slots", "?")
                
                # Bug fix: dynamic data_source based on actual runtime state
                if runtime_acc.is_ready:
                    data_source = "🟢 Runtime"
                elif ext_connected or runtime_acc.is_enabled:
                    data_source = "🟡 Runtime"
                else:
                    data_source = "🔴 Runtime"
            else:
                # ═══ FALLBACK: tokens.json cache ═══
                token_info = tokens_data.get(email, {})
                access_token = token_info.get("access_token", "")
                refresh_token = token_info.get("refresh_token", "")
                expires_at = token_info.get("expires_at", 0)
                updated_at = token_info.get("updated_at", "")
                
                # Session status from profile
                if profile.is_ready:
                    session_status = "🟢 Session Active (Offline)"
                else:
                    session_status = "🔴 Not Logged In"
                
                # Token expiry from cache
                now_ts = datetime.now().timestamp()
                if expires_at:
                    time_left = expires_at - now_ts
                    if time_left <= 0:
                        hours_ago = int(abs(time_left) / 3600)
                        token_expiry = f"🔄 Cached ({hours_ago}h ago)"
                    elif time_left < 600:
                        mins = int(time_left / 60)
                        token_expiry = f"🟠 Expiring ({mins}m left)"
                    else:
                        mins = int(time_left / 60)
                        token_expiry = f"✅ Fresh ({mins}m left)"
                else:
                    token_expiry = "❌ No token stored"
                
                recaptcha_status = "⚪ Not loaded"
                browser_alive = False
                slots_display = f"0/{profile.max_slots}"
                data_source = "📁 Cache"
            
            # Cookie count from browser profile
            cookie_count = 0
            cookie_domains = {}
            cookies_locked = False
            browser_path = profile.browser_profile_path or profile.profile_path
            if browser_path:
                cookies_db = Path(browser_path) / "Default" / "Network" / "Cookies"
                if cookies_db.exists():
                    try:
                        temp_db = Path(tempfile.gettempdir()) / f"cookies_{uuid.uuid4().hex[:8]}.db"
                        shutil.copy2(cookies_db, temp_db)
                        conn = sqlite3.connect(str(temp_db))
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM cookies")
                        cookie_count = cursor.fetchone()[0]
                        cursor.execute(
                            "SELECT host_key, COUNT(*) as cnt FROM cookies "
                            "GROUP BY host_key ORDER BY cnt DESC LIMIT 5"
                        )
                        for row in cursor.fetchall():
                            cookie_domains[row[0]] = row[1]
                        conn.close()
                        temp_db.unlink(missing_ok=True)
                    except PermissionError:
                        cookies_locked = True
                    except Exception:
                        if debug_browser_active:
                            cookies_locked = True
            
            info = {
                "email": email,
                "display_name": profile.display_name,
                "sku": profile.tier_display,
                "credits": profile.credits,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "session_status": session_status,
                "token_expiry": token_expiry,
                "recaptcha_status": recaptcha_status,
                "ext_connected": ext_connected if runtime_acc else False,
                "browser_alive": browser_alive,
                "slots_display": slots_display,
                "updated_at": updated_at,
                "cookie_count": cookie_count,
                "cookie_domains": cookie_domains,
                "cookies_locked": cookies_locked,
                "browser_state": debug_state,
                "is_ready": profile.is_ready,
                "is_enabled": profile.is_enabled,
                "data_source": data_source,
            }
            result.append(info)
        
        return result
    
    def _push_session_data(self):
        """Push session data to DevConsole (thread-safe)."""
        if not hasattr(self, '_dev_console') or not self._dev_console:
            return
        
        data = self.get_session_data()
        
        from PySide6.QtCore import QMetaObject, Qt, QThread
        
        if QThread.currentThread() == self._dev_console.thread():
            self._dev_console.update_session_data(data)
        else:
            QMetaObject.invokeMethod(
                self._dev_console, "update_session_data_safe",
                Qt.ConnectionType.QueuedConnection
            )
    
    def _push_performance(self):
        """Push performance metrics to DevConsole.
        
        Called by _perf_timer every 5 seconds while DevConsole is open.
        """
        if not hasattr(self, '_dev_console') or not self._dev_console:
            return
        
        try:
            import psutil
            process = psutil.Process()
            
            # Uptime
            elapsed = datetime.now() - self._start_time
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            
            data = {
                "uptime": uptime_str,
                "cpu": round(process.cpu_percent(interval=0), 1),
                "ram": round(process.memory_info().rss / (1024 * 1024), 1),
                "threads": process.num_threads(),
                "api_calls": getattr(self._api_client, '_call_count', 0),
                "downloads": getattr(self._engine, '_download_count', 0),
                "errors": getattr(self._engine, '_error_count', 0),
            }
        except Exception:
            data = {"uptime": "N/A", "cpu": 0, "ram": 0, "threads": 0}
        
        try:
            self._dev_console.update_performance(data)
        except Exception:
            pass
        
        # Also refresh extension status + session data on each tick
        try:
            self._push_extension_status()
        except Exception:
            pass
        try:
            self._push_session_data()
        except Exception:
            pass
        
        # Push Engine Dashboard (aggregated monitoring data)
        try:
            dashboard = self.get_engine_dashboard()
            if dashboard and hasattr(self._dev_console, 'update_engine_dashboard'):
                self._dev_console.update_engine_dashboard(dashboard)
        except Exception:
            pass
    
    def get_engine_dashboard(self) -> dict:
        """Aggregate all monitoring/optimization data for Engine Dashboard.
        
        Pulls from:
        - StatusAggregator: throughput, success rate, active tasks
        - RecaptchaPool: hit/miss stats
        - UpscaleQueue: pending/completed stats
        - AdaptiveBurstController: per-account delay stats
        - MultiAccountManager: health scores
        
        Returns dict consumed by DevConsole.update_engine_dashboard().
        """
        dashboard = {
            "aggregator": {},
            "recaptcha_pool": {},
            "upscale_queue": {},
            "burst_controller": {},
            "health_scores": {},
            "bottlenecks": [],
        }
        
        # StatusAggregator
        try:
            if hasattr(self, '_status_aggregator') and self._status_aggregator:
                dashboard["aggregator"] = self._status_aggregator.get_dashboard()
                dashboard["bottlenecks"] = self._status_aggregator._detect_bottlenecks()
        except Exception:
            pass
        
        # RecaptchaPool
        try:
            if (hasattr(self, '_engine') and self._engine and
                    hasattr(self._engine, '_recaptcha_pool') and self._engine._recaptcha_pool):
                dashboard["recaptcha_pool"] = self._engine._recaptcha_pool.get_stats()
        except Exception:
            pass
        
        # UpscaleQueue
        try:
            if (hasattr(self, '_engine') and self._engine and
                    hasattr(self._engine, '_upscale_queue') and self._engine._upscale_queue):
                dashboard["upscale_queue"] = self._engine._upscale_queue.get_stats()
        except Exception:
            pass
        
        # AdaptiveBurstController
        try:
            if (hasattr(self, '_engine') and self._engine and
                    hasattr(self._engine, '_burst_controller') and self._engine._burst_controller):
                dashboard["burst_controller"] = self._engine._burst_controller.get_stats()
        except Exception:
            pass
        
        # Health scores
        try:
            if hasattr(self, '_multi_account') and self._multi_account:
                dashboard["health_scores"] = self._multi_account.get_health_scores()
        except Exception:
            pass
        
        return dashboard
    
    def get_pipeline_settings(self) -> dict:
        """Get current pipeline optimization settings for Settings tab.
        
        Returns dict of all tunable parameters.
        """
        settings = {
            "adaptive_burst_enabled": True,
            "burst_min_delay": 2.0,
            "burst_max_delay": 15.0,
            "recaptcha_pool_enabled": True,
            "pool_size": 2,
            "watchdog_timeout_min": 10,
            "journal_save_interval_sec": 30,
        }
        
        try:
            if (hasattr(self, '_engine') and self._engine and
                    hasattr(self._engine, '_burst_controller') and self._engine._burst_controller):
                bc = self._engine._burst_controller
                settings["burst_min_delay"] = bc._min
                settings["burst_max_delay"] = bc._max
                settings["adaptive_burst_enabled"] = True
        except Exception:
            pass
        
        try:
            if (hasattr(self, '_engine') and self._engine and
                    hasattr(self._engine, '_recaptcha_pool') and self._engine._recaptcha_pool):
                rp = self._engine._recaptcha_pool
                settings["pool_size"] = rp.POOL_SIZE
                # Keep default True — pool auto-starts with engine
                # Only report False if user explicitly stopped it
                # (runtime _running is False before first start_processing)
        except Exception:
            pass
        
        try:
            if hasattr(self, '_task_watchdog') and self._task_watchdog:
                settings["watchdog_timeout_min"] = getattr(
                    self._task_watchdog, '_stuck_threshold_min', 10
                )
        except Exception:
            pass
        
        try:
            if hasattr(self, '_task_journal') and self._task_journal:
                settings["journal_save_interval_sec"] = getattr(
                    self._task_journal, '_save_interval', 30
                )
        except Exception:
            pass
        
        return settings
    
    def update_pipeline_settings(self, key: str, value):
        """Update a single pipeline optimization setting.
        
        Args:
            key: Setting key (e.g. 'burst_min_delay')
            value: New value
        """
        log.info(f"[Pipeline] Setting {key} = {value}")
        
        try:
            if key == "burst_min_delay":
                if self._engine and self._engine._burst_controller:
                    self._engine._burst_controller._min = float(value)
            elif key == "burst_max_delay":
                if self._engine and self._engine._burst_controller:
                    self._engine._burst_controller._max = float(value)
            elif key == "adaptive_burst_enabled":
                # Toggle is informational — burst controller is always active
                # but min/max can be set to same value to effectively disable
                pass
            elif key == "pool_size":
                if self._engine and self._engine._recaptcha_pool:
                    self._engine._recaptcha_pool.POOL_SIZE = int(value)
            elif key == "recaptcha_pool_enabled":
                if self._engine and self._engine._recaptcha_pool:
                    if value and not self._engine._recaptcha_pool._running:
                        self._engine._recaptcha_pool.start()
                    elif not value and self._engine._recaptcha_pool._running:
                        self._engine._recaptcha_pool.stop()
            elif key == "watchdog_timeout_min":
                if self._task_watchdog:
                    self._task_watchdog._stuck_threshold_min = int(value)
            elif key == "journal_save_interval_sec":
                if self._task_journal:
                    self._task_journal._save_interval = int(value)
            else:
                log.warning(f"[Pipeline] Unknown setting: {key}")
        except Exception as e:
            log.error(f"[Pipeline] Failed to update {key}: {e}")
    
    def start_perf_timer(self):
        """Start performance timer (called when DevConsole opens)."""
        if self._perf_timer is not None:
            return  # Already running
        
        from PySide6.QtCore import QTimer
        self._perf_timer = QTimer()
        self._perf_timer.timeout.connect(self._push_performance)
        self._perf_timer.start(5000)  # Every 5 seconds
        self._push_performance()  # Immediate first push
    
    def stop_perf_timer(self):
        """Stop performance timer (called when DevConsole closes)."""
        if self._perf_timer:
            self._perf_timer.stop()
            self._perf_timer.deleteLater()
            self._perf_timer = None
    
    def _start_async_loop(self):
        """Start background async event loop."""
        loop_ready = threading.Event()
        
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            loop_ready.set()  # Signal main thread that loop is ready
            self._loop.run_forever()
        
        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
        loop_ready.wait(timeout=5.0)  # Wait for loop to be created
    
    def _stop_async_loop(self):
        """Stop background async event loop."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
    
    def _run_async(self, coro):
        """Run async coroutine in background loop."""
        if self._loop:
            return asyncio.run_coroutine_threadsafe(coro, self._loop)
        return None
    
    # === ACCOUNT MANAGEMENT ===
    
    def add_account(self, session: AccountSession) -> bool:
        """Add an account to the manager.
        
        MultiAccountManager.add_account() accepts AccountSession and
        wraps it in AccountManager internally (per architecture §6.1).
        """
        if not self._permissions.check_limit("max_cookies", len(self._multi_account._accounts)):
            return False
        
        # Correct: pass AccountSession, not AccountManager
        # add_account is async — run via background loop
        future = self._run_async(self._multi_account.add_account(session))
        if future:
            try:
                result = future.result(timeout=5.0)
                if not result:
                    return False
            except Exception:
                return False
        
        self._session_monitor.register_session(session)
        self._refresh_manager.register_session(session)
        
        self._notify_status(f"Account added: {session.email}")
        return True
    
    def remove_account(self, email: str) -> bool:
        """Remove an account."""
        # remove_account is async — run via background loop
        future = self._run_async(self._multi_account.remove_account(email))
        result = False
        if future:
            try:
                result = future.result(timeout=10.0)
            except Exception:
                pass
        
        self._session_monitor.unregister_session(email)
        self._refresh_manager.unregister_session(email)
        return result
    
    def toggle_account(self, email: str, enabled: bool) -> bool:
        """Enable or disable an account without removing it.
        
        Disabled accounts won't be selected for task dispatch.
        """
        account = self._multi_account.get_account(email)
        if not account:
            return False
        
        if enabled:
            account.enable()
            self._notify_status(f"Account enabled: {email}")
        else:
            account.disable()
            self._notify_status(f"Account disabled: {email}")
        return True
    
    def get_accounts(self) -> List[Dict]:
        """Get list of accounts with status."""
        status = self._multi_account.get_status_summary()
        return status.get('accounts', [])
    
    def set_profiles_controller(self, profiles_controller):
        """Set the ProfilesController reference.
        
        Called by UI layer (TabSettings) to bridge persistence → runtime.
        Triggers auto-launch of headless browsers for all profiles.
        """
        self._profiles_controller = profiles_controller
        # Forward to engine so it can auto re-login on auth failures
        if self._engine:
            self._engine._profiles_controller = profiles_controller
        
        # Now that ProfilesController is available, auto-launch browsers
        self._auto_launch_browsers()
    
    def sync_profiles_to_runtime(self):
        """Sync profiles from ProfilesController → MultiAccountManager.
        
        Issue E fix: Called before start_processing() to ensure the runtime
        dispatch pool matches the persisted profiles state.
        
        Logic:
        1. Get all profiles from ProfilesController
        2. For each ready + enabled profile not yet in MultiAccountManager:
           create AccountSession and add_account
        3. For each profile already in MultiAccountManager:
           sync enabled/disabled state
        4. Remove runtime accounts that no longer exist in profiles
        """
        log = logging.getLogger(__name__)
        
        if not self._profiles_controller:
            log.debug("No ProfilesController set, skipping sync")
            return
        
        profiles = self._profiles_controller.get_all_profiles()
        profile_emails = {p['email'] for p in profiles}
        
        for p in profiles:
            email = p.get('email', '')
            is_ready = p.get('is_ready', False)
            is_enabled = p.get('is_enabled', True)
            
            existing = self._multi_account.get_account(email)
            
            if existing:
                # Sync enabled/disabled state
                if is_enabled and not existing.is_enabled:
                    existing.enable()
                elif not is_enabled and existing.is_enabled:
                    existing.disable()
            elif is_ready and is_enabled:
                # Profile is ready but not in runtime pool — add it
                try:
                    profile_obj = self._profiles_controller.get_profile(email)
                    if not profile_obj:
                        continue
                    
                    # Build AccountSession from ChromeProfile
                    from core.session import (
                        AccountSession, SubscriptionType, PaygateTier
                    )
                    
                    # Parse token expiry if available
                    token_expires = datetime.now() + timedelta(hours=1)
                    if profile_obj.token_expires_at:
                        try:
                            token_expires = datetime.fromisoformat(
                                profile_obj.token_expires_at
                            )
                        except (ValueError, TypeError):
                            pass
                    
                    session = AccountSession(
                        email=email,
                        access_token=getattr(profile_obj, 'access_token', '') or '',
                        token_expires=token_expires,
                        profile_path=profile_obj.browser_profile_path or profile_obj.profile_path,
                    )
                    
                    # Set SKU/tier if available
                    try:
                        session.sku = SubscriptionType(profile_obj.sku)
                    except (ValueError, KeyError):
                        pass
                    try:
                        session.paygate_tier = PaygateTier(profile_obj.paygate_tier)
                    except (ValueError, KeyError):
                        pass
                    
                    session.credits = profile_obj.credits
                    session.max_slots = getattr(profile_obj, 'max_slots', 4)
                    
                    # Add to runtime via async
                    future = self._run_async(
                        self._multi_account.add_account(session)
                    )
                    if future:
                        try:
                            future.result(timeout=3.0)
                            log.info(f"Synced profile → runtime: {email}")
                            
                            # Hot-reload: if engine is running, spawn workers immediately
                            if self._engine and self._engine.is_running:
                                acc_mgr = self._multi_account.get_account(email)
                                if acc_mgr:
                                    self._engine.add_account_hot(acc_mgr)
                                    
                        except Exception as e:
                            log.warning(f"Failed to sync {email}: {e}")
                            
                except Exception as e:
                    log.warning(f"Error syncing profile {email}: {e}")
        
        # Remove runtime accounts that no longer exist in profiles
        for acc in list(self._multi_account._accounts):
            if acc.email not in profile_emails:
                future = self._run_async(
                    self._multi_account.remove_account(acc.email)
                )
                if future:
                    try:
                        future.result(timeout=5.0)
                        log.info(f"Removed stale runtime account: {acc.email}")
                    except Exception:
                        pass
        
        log.info(
            f"Profile sync complete: {self._multi_account.account_count} accounts, "
            f"{len(self._multi_account.ready_accounts)} ready"
        )
        
        # Ensure ExtensionBridge + ProfilesController are injected on ALL accounts
        # (covers newly-created accounts from sync AND existing ones)
        for acc in self._multi_account._accounts:
            if hasattr(self, '_extension_bridge') and self._extension_bridge:
                acc._extension_bridge = self._extension_bridge
            if hasattr(self, '_profiles_controller') and self._profiles_controller:
                acc.set_profiles_controller(self._profiles_controller)
    
    def set_account_max_slots(self, email: str, max_slots: int):
        """Set max_slots on runtime AccountManager for a given email.
        
        Called by UI when user changes Slots SpinBox.
        """
        acc = self._multi_account.get_account(email)
        if acc:
            acc.set_max_slots(max_slots)
            logging.getLogger(__name__).info(
                f"Runtime max_slots for {email} → {max_slots}"
            )
    
    # Safe concurrency limit: max concurrent API calls per account
    # e.g. 2 workers × 4 outputs = 8 API calls — safe ceiling
    SAFE_CONCURRENT_API_CALLS = 8
    
    def get_concurrency_warnings(self, output_per_prompt: int = 4) -> list:
        """Check if any account's concurrent load exceeds the safe limit.
        
        Risk = output_per_prompt × max_slots (workers).
        Safe limit: SAFE_CONCURRENT_API_CALLS (8 concurrent operations).
        
        Returns list of (email, current_slots, concurrent_load, safe_limit) tuples
        for accounts that exceed the safe limit. Empty list = all safe.
        """
        warnings = []
        safe = self.SAFE_CONCURRENT_API_CALLS
        for acc in self._multi_account._accounts:
            concurrent_load = acc.max_slots * output_per_prompt
            if acc.is_enabled and concurrent_load > safe:
                warnings.append((acc.email, acc.max_slots, concurrent_load, safe))
        return warnings
    
    @staticmethod
    def _map_aspect_ratio(raw: str, workflow: "WorkflowType") -> str:
        """Map sidebar aspect ratio name to correct API enum.
        
        Video endpoints expect VIDEO_ASPECT_RATIO_* prefix.
        Image endpoints expect IMAGE_ASPECT_RATIO_* prefix.
        """
        is_image = workflow in (WorkflowType.T2I, WorkflowType.I2I)
        prefix = "IMAGE_ASPECT_RATIO" if is_image else "VIDEO_ASPECT_RATIO"
        
        raw_upper = raw.upper()
        if "LANDSCAPE" in raw_upper:
            return f"{prefix}_LANDSCAPE"
        elif "PORTRAIT" in raw_upper:
            return f"{prefix}_PORTRAIT"
        elif "SQUARE" in raw_upper:
            return f"{prefix}_SQUARE"
        # Already in full enum format?
        if raw_upper.startswith(("VIDEO_ASPECT_RATIO", "IMAGE_ASPECT_RATIO")):
            return raw
        return f"{prefix}_LANDSCAPE"  # Safe fallback
    
    @staticmethod
    def _default_model(workflow: "WorkflowType") -> str:
        """Return correct default model for workflow type."""
        if workflow in (WorkflowType.T2I, WorkflowType.I2I):
            return "GEM_PIX_2"
        return "veo_3_1_t2v_fast_ultra"
    
    def submit_prompts(
        self,
        prompts: List[str],
        workflow: WorkflowType,
        images: Optional[List[str]] = None,
        per_prompt_images: Optional[Dict[int, List[str]]] = None,  # Bug 2: per-prompt image mapping
        settings: Optional[Dict] = None,
        continuation_map: Optional[Dict[int, int]] = None,  # index -> parent_index
    ) -> str:
        """Submit prompts for processing.
        
        Args:
            images: Flat list of image URIs (shared by ALL tasks — legacy)
            per_prompt_images: Dict mapping prompt index → list of image URIs for that task.
                              Takes priority over `images` when provided.
        
        Returns group_id.
        """
        # Apply batch size limit from role
        max_batch = self._permissions.limits.max_prompts_per_batch
        if max_batch > 0:
            prompts = prompts[:max_batch]
        
        # Map settings to correct API values
        raw_ar = (settings or {}).get("aspect_ratio", "LANDSCAPE")
        aspect_ratio = self._map_aspect_ratio(raw_ar, workflow)
        
        # Auto-map model display name → API model key
        model_display = (settings or {}).get("model", "")
        dual_frame = (settings or {}).get("frame_mode", "") == "both"
        if model_display and not model_display.startswith("veo_") and model_display not in ("GEM_PIX", "GEM_PIX_2", "IMAGEN_3_5"):
            model = resolve_model_key(model_display, workflow, raw_ar, dual_frame)
        else:
            model = model_display or self._default_model(workflow)
        output_count = (settings or {}).get("outputs_per_prompt", 4)
        
        # Create task group
        group_id = f"group_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        tasks = []
        task_id_map = {}  # index -> task_id for continuation linking
        
        for i, prompt in enumerate(prompts):
            task_id = f"{group_id}_task_{i}"
            task_id_map[i] = task_id
            
            # Check if this prompt is continuation of another
            parent_task_id = None
            if continuation_map and i in continuation_map:
                parent_index = continuation_map[i]
                if parent_index in task_id_map:
                    parent_task_id = task_id_map[parent_index]
            
            task = Task(
                id=task_id,
                workflow_type=workflow.name,  # "T2V" not WorkflowType.T2V
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                model=model,
                output_count=output_count,
                duration_seconds=(settings or {}).get("duration", 8),
                # Bug 2 fix: Per-prompt images take priority, fallback to shared list
                image_uris=(per_prompt_images or {}).get(i, images or []),
                parent_task_id=parent_task_id,
                extract_point_ms=(settings or {}).get("extract_point_ms", 750),
                download_quality=(settings or {}).get("download_quality", "720p"),
                output_folder=(settings or {}).get("output_folder", ""),
                project_name=(settings or {}).get("project_name", ""),
                prompt_index=i,
            )
            
            # Separate local file paths from remote URIs
            # add_i2v_batch / add_r2v_batch / add_i2i_batch resolve tags → local paths
            # and pass them as per_prompt_images/images, which land here in image_uris.
            # Local paths must go to image_paths so Engine._resolve_image_paths() uploads them.
            if task.image_uris:
                from pathlib import Path as _P
                local = [u for u in task.image_uris if _P(u).exists()]
                remote = [u for u in task.image_uris if not _P(u).exists()]
                if local:
                    task.image_paths = local
                    task.image_uris = remote  # Only keep actual remote URIs/mediaIds
            
            # === Tag resolution: [tag] → local image path ===
            # Only resolve if task has no explicit image_uris or image_paths already
            # Bug 1 fix: Also check image_paths — they may have been populated by
            # _resolve_tags_to_paths() in add_i2v_batch() and then moved from
            # image_uris to image_paths by the local/remote split above (line 1031-1037)
            if not task.image_uris and not task.image_paths:
                import re
                tags = re.findall(r'\[([^\]]+)\]', prompt)
                if tags:
                    try:
                        from services.image_library import get_image_library
                        library = get_image_library()
                        resolved_paths = []
                        for tag in tags:
                            img = library.resolve_tag(tag)
                            if img and img.path:
                                resolved_paths.append(img.path)
                                log.info(f"  [TAG] [{tag}] → {img.path}")
                            else:
                                log.warning(f"  [TAG] [{tag}] not found in library")
                        
                        if resolved_paths:
                            task.image_paths = resolved_paths
                            # Auto-switch T2V → I2V when tags detected
                            if task.workflow_type == "T2V":
                                task.workflow_type = "I2V"
                                log.info(f"  [AUTO] T2V → I2V (tags detected)")
                    except ImportError:
                        log.warning("  ImageLibrary not available for tag resolution")
            # === End tag resolution ===
            
            # === Workflow auto-switch ===
            # Per-task: adjust workflow_type + model based on actual conditions
            has_images = bool(task.image_uris or task.image_paths)
            has_continuation = task.parent_task_id is not None
            
            # Downgrade: image workflow → text workflow (no images available)
            if not has_images and not has_continuation and task.workflow_type in ("I2V", "F2V"):
                task.workflow_type = "T2V"
                task.model = resolve_model_key(model_display, WorkflowType.T2V, raw_ar, False)
                log.info(f"  [AUTO] I2V → T2V (no images, task {i})")
            
            elif not has_images and not has_continuation and task.workflow_type == "R2V":
                task.workflow_type = "T2V"
                task.model = resolve_model_key(model_display, WorkflowType.T2V, raw_ar, False)
                log.info(f"  [AUTO] R2V → T2V (no images, task {i})")
            
            elif not has_images and task.workflow_type == "I2I":
                task.workflow_type = "T2I"
                # T2I/I2I both use GEM_PIX_2 — no model change needed
                log.info(f"  [AUTO] I2I → T2I (no images, task {i})")
            
            # Upgrade: T2V/R2V → I2V (continuation needs a start frame)
            elif has_continuation and task.workflow_type in ("T2V", "R2V"):
                old_wf = task.workflow_type
                task.workflow_type = "I2V"
                task.model = resolve_model_key(model_display, WorkflowType.I2V, raw_ar, False)
                log.info(f"  [AUTO] {old_wf} → I2V (continuation, task {i})")
            # === End auto-switch ===
            
            tasks.append(task)
        
        # === Continuation constraint: force output_count=1 for entire group ===
        # When ANY task in the group is a continuation, the whole chain must
        # produce exactly 1 video per prompt (last frame → next prompt's start).
        # Workers: dependency chain already ensures serial execution —
        # only 1 task from the chain is in ready queue at any time.
        has_any_continuation = any(t.parent_task_id is not None for t in tasks)
        if has_any_continuation:
            for t in tasks:
                t.output_count = 1
            log.info(f"  [CONT] Continuation detected → output_count forced to 1 for all {len(tasks)} tasks")
        
        project_name = (settings or {}).get("project_name", "")
        group_display = project_name if project_name else f"Batch {len(tasks)}"
        group = TaskGroup(id=group_id, name=group_display, tasks=tasks)
        
        # === DEBUG: Export resolved task structure ===
        log.info(f"{'='*60}")
        log.info(f"[ADD TO QUEUE] group_id={group_id}")
        log.info(f"  workflow    : {workflow.name}")
        log.info(f"  model      : {model_display!r} → {model}")
        log.info(f"  aspect_ratio: {raw_ar} → {aspect_ratio}")
        log.info(f"  dual_frame : {dual_frame}")
        log.info(f"  output_count: {1 if has_any_continuation else output_count}{' (continuation override)' if has_any_continuation else ''}")
        log.info(f"  tasks      : {len(tasks)}")
        for t in tasks:
            cont = f" (cont→{t.parent_task_id})" if t.parent_task_id else ""
            log.info(f"    [{t.id}] {t.prompt[:60]}...{cont}" if len(t.prompt) > 60 else f"    [{t.id}] {t.prompt}{cont}")
        log.info(f"{'='*60}")
        # === END DEBUG ===
        
        # Push JSON preview to DevConsole if available
        if self._dev_console and hasattr(self._dev_console, 'update_json_preview'):
            preview = {
                "group_id": group_id,
                "workflow": workflow.name,
                "model_display": model_display,
                "model_api_key": model,
                "aspect_ratio_raw": raw_ar,
                "aspect_ratio_api": aspect_ratio,
                "dual_frame": dual_frame,
                "output_count": output_count,
                "tasks": [
                    {
                        "id": t.id,
                        "prompt": t.prompt,
                        "model": t.model,
                        "aspect_ratio": t.aspect_ratio,
                        "duration": t.duration_seconds,
                        "images": t.image_uris,
                        "parent": t.parent_task_id,
                    }
                    for t in tasks
                ],
            }
            try:
                self._dev_console.update_json_preview(preview)
            except Exception:
                pass
        
        self._dispatcher.submit_task_group(group)
        
        self.state.queue_count += len(tasks)
        self._notify_queue_updated()
        
        return group_id
    
    # === BATCH METHODS (called by UI tabs) ===
    
    def add_t2v_batch(self, prompts: List, settings: Dict) -> str:
        """Add Text-to-Video batch to queue.
        
        Args:
            prompts: List of PromptRow objects from UI
            settings: Sidebar settings dict
        """
        # Extract continuation chain
        continuation_map = {}
        for i, p in enumerate(prompts):
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                # continuation_from is 1-indexed, convert to 0-indexed
                continuation_map[i] = p.continuation_from - 1
        
        return self.submit_prompts(
            prompts=[p.text if hasattr(p, 'text') else str(p) for p in prompts],
            workflow=WorkflowType.T2V,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None
        )
    
    def _resolve_tags_to_paths(self, tags: List[str]) -> List[str]:
        """Resolve image tag names to file paths via ImageLibrary.
        
        Tags that cannot be resolved are skipped.
        """
        if not tags:
            return []
        try:
            from services.image_library import get_image_library
            library = get_image_library()
            paths = []
            for tag in tags:
                # If it already looks like a file path, keep it
                if '/' in tag or '\\' in tag or '.' in tag and len(tag) > 5:
                    paths.append(tag)
                    continue
                img = library.resolve_tag(tag)
                if img and img.path:
                    paths.append(img.path)
                    log.info(f"  [TAG→PATH] [{tag}] → {img.path}")
                else:
                    log.warning(f"  [TAG→PATH] [{tag}] not found in library, skipping")
            return paths
        except Exception as e:
            log.error(f"  [TAG→PATH] Error resolving tags: {e}")
            return []
    
    def add_i2v_batch(self, prompts: List, settings: Dict) -> str:
        """Add Image-to-Video batch to queue.
        
        Args:
            prompts: List of PromptRow objects with image_tags
            settings: Sidebar settings dict
        """
        per_prompt_images = {}
        prompt_texts = []
        continuation_map = {}
        
        for i, p in enumerate(prompts):
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tags') and p.image_tags:
                # Resolve tags to actual file paths
                resolved = self._resolve_tags_to_paths(list(p.image_tags))
                if resolved:
                    per_prompt_images[i] = resolved
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                continuation_map[i] = p.continuation_from - 1
        
        # Bug 3: Warn when I2V batch has prompts without images (will auto-convert to T2V)
        no_image_indices = [i for i in range(len(prompts)) if i not in per_prompt_images and i not in continuation_map]
        if no_image_indices and per_prompt_images:
            log.warning(
                f"  [I2V] {len(no_image_indices)} prompt(s) have no images "
                f"(indices: {no_image_indices}) — will auto-convert to T2V"
            )
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.I2V,
            per_prompt_images=per_prompt_images if per_prompt_images else None,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None
        )
    
    def add_r2v_batch(self, prompts: List, settings: Dict) -> str:
        """Add Ingredients/References-to-Video batch to queue.
        
        Args:
            prompts: List of PromptRow objects with image_tags (up to 3)
            settings: Sidebar settings dict
        """
        all_images = []
        prompt_texts = []
        continuation_map = {}
        for i, p in enumerate(prompts):
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tags') and p.image_tags:
                resolved = self._resolve_tags_to_paths(list(p.image_tags[:3]))  # Max 3
                all_images.extend(resolved)
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                continuation_map[i] = p.continuation_from - 1
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.R2V,
            images=all_images if all_images else None,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None
        )
    
    def add_t2i_batch(self, prompts: List, settings: Dict) -> str:
        """Add Text-to-Image batch to queue.
        
        Args:
            prompts: List of PromptRow objects
            settings: Sidebar settings dict
        """
        return self.submit_prompts(
            prompts=[p.text if hasattr(p, 'text') else str(p) for p in prompts],
            workflow=WorkflowType.T2I,
            settings=settings
        )
    
    def add_i2i_batch(self, prompts: List, settings: Dict) -> str:
        """Add Image-to-Image batch to queue.
        
        Args:
            prompts: List of PromptRow objects with image_tags
            settings: Sidebar settings dict
        """
        images = []
        prompt_texts = []
        for p in prompts:
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tags') and p.image_tags:
                resolved = self._resolve_tags_to_paths(list(p.image_tags))
                images.extend(resolved)
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.I2I,
            images=images if images else None,
            settings=settings
        )
    
    def activate_license(self, key: str) -> bool:
        """Activate license key.
        
        Args:
            key: License key string
            
        Returns:
            True if activation successful
        """
        if not hasattr(self, '_license_client') or not self._license_client:
            print(f"[WARN] License client not initialized, key: {key[:8]}...")
            return False
        
        result = self._license_client.activate(key)
        if result and hasattr(result, 'success') and result.success:
            self._update_permissions()
            self._notify_status("License activated successfully")
            return True
        
        self._notify_status("License activation failed")
        return False
    def preflight_check(self) -> dict:
        """Pre-flight readiness check before starting engine.
        
        Validates each account's readiness for production:
        - Extension connected (REQUIRED — sole data source)
        - Access token available
        - reCAPTCHA freshness
        - Account enabled/disabled
        
        Returns:
            {
                "can_start": bool,      # True if at least 1 account is production-ready
                "accounts": [           # Per-account status
                    {
                        "email": str,
                        "ready": bool,
                        "issues": [str],   # List of blockers
                        "warnings": [str], # Non-blocking issues
                    }
                ],
                "summary": str,         # Human-readable summary
            }
        """
        result = {"can_start": False, "accounts": [], "summary": ""}
        
        if not self._multi_account or not self._multi_account._accounts:
            result["summary"] = "❌ Chưa có tài khoản nào được cấu hình"
            return result
        
        ready_count = 0
        total_count = 0
        
        for account in self._multi_account._accounts:
            total_count += 1
            acc_info = {
                "email": account.email,
                "ready": False,
                "issues": [],
                "warnings": [],
            }
            
            # Check 1: Account enabled
            if not account.is_enabled:
                acc_info["issues"].append("🔴 Tài khoản đã tắt")
                result["accounts"].append(acc_info)
                continue
            
            # Check 2: Extension connected (REQUIRED in extension-only architecture)
            ext_connected = (
                self._extension_bridge and
                self._extension_bridge.is_connected(account.email)
            )
            if not ext_connected:
                acc_info["issues"].append("🔴 Extension chưa kết nối — cần mở trình duyệt")
            
            # Check 3: Access token
            has_token = bool(account._session.access_token)
            token_expired = account._session.is_token_expired
            if not has_token:
                if ext_connected:
                    acc_info["warnings"].append("🟡 Token chưa sẵn sàng — sẽ tự lấy khi chạy task đầu tiên")
                else:
                    acc_info["issues"].append("🔴 Không có access token — cần kết nối Extension")
            elif token_expired:
                if ext_connected:
                    acc_info["warnings"].append("🟡 Token hết hạn — Extension sẽ tự refresh")
                else:
                    acc_info["issues"].append("🔴 Token hết hạn — Extension chưa kết nối, không thể refresh")
            
            # Check 4: reCAPTCHA
            needs_recaptcha = account._session.needs_recaptcha_refresh
            if needs_recaptcha:
                if ext_connected:
                    acc_info["warnings"].append("🟡 reCAPTCHA cần refresh — sẽ tự refresh khi chạy task")
                else:
                    acc_info["issues"].append("🔴 reCAPTCHA hết hạn — Extension chưa kết nối")
            
            # Check 5: Browser headers (x-browser-*)
            has_headers = bool(account._session.browser_validation)
            if not has_headers:
                if ext_connected:
                    acc_info["warnings"].append("🟡 Headers chưa capture — sẽ tự có khi Extension gửi request đầu tiên")
                else:
                    acc_info["issues"].append("🔴 Không có headers — cần mở trình duyệt và kết nối Extension")
            
            # Verdict for this account
            if not acc_info["issues"]:
                acc_info["ready"] = True
                ready_count += 1
            
            result["accounts"].append(acc_info)
        
        result["can_start"] = ready_count > 0
        
        # Build summary
        if ready_count == total_count:
            result["summary"] = f"✅ Tất cả {total_count} tài khoản sẵn sàng"
        elif ready_count > 0:
            blocked = total_count - ready_count
            result["summary"] = f"⚠️ {ready_count}/{total_count} sẵn sàng, {blocked} bị chặn"
        else:
            result["summary"] = f"❌ Không có tài khoản nào sẵn sàng ({total_count} tổng)"
        
        return result
    
    def start_processing(self):
        """Start processing queue via Engine.
        
        Runs a pre-flight readiness check first. If no accounts are
        production-ready, blocks the start and shows an error toast.
        
        Engine uses asyncio.TaskGroup for proper async worker management.
        The Engine.start() coroutine runs in the background async loop.
        """
        if self.state.is_processing:
            return
        
        # Pre-flight readiness check
        check = self.preflight_check()
        log.info(f"[Preflight] {check['summary']}")
        for acc in check["accounts"]:
            if acc["issues"]:
                log.warning(f"[Preflight] {acc['email']}: {', '.join(acc['issues'])}")
            if acc["warnings"]:
                log.info(f"[Preflight] {acc['email']}: {', '.join(acc['warnings'])}")
        
        if not check["can_start"]:
            self._notify_status(f"Cannot start: {check['summary']}")
            self.state.is_processing = False
            return
        
        self.state.is_processing = True
        
        # Issue E: Sync profiles to runtime before starting
        self.sync_profiles_to_runtime()
        
        # Per-account worker settings (max_slots, retry_count, request_timeout)
        # are now read directly from each AccountManager at runtime.
        # No global max_workers needed.
        
        # Anti-Detect Spam settings (global — applies to all accounts)
        self._engine._anti_detect_enabled = getattr(self.settings, 'anti_detect_enabled', True)
        self._engine._anti_detect_delay_min = getattr(self.settings, 'anti_detect_delay_min', 3.0)
        self._engine._anti_detect_delay_max = getattr(self.settings, 'anti_detect_delay_max', 8.0)
        
        # D1: Continuation Frame settings (global)
        self._engine._continuation_enabled = getattr(self.settings, 'continuation_enabled', True)
        self._engine._extract_point_ms = getattr(self.settings, 'extract_point_ms', 750)
        
        # Wire engine callbacks
        self._engine._on_progress = self._handle_progress
        self._engine._on_task_completed = lambda task: self._handle_task_completed(task)
        self._engine._on_task_failed = lambda task, err: self._handle_task_failed(task, err)
        
        # Wire dispatcher progress callback → UI
        # Engine calls dispatcher.update_progress() during poll loop,
        # this ensures the UI callback gets triggered
        self._dispatcher.set_progress_callback(self._forward_progress_to_ui)
        
        # Start Engine in the async loop (store Future for clean shutdown)
        self._engine_future = self._run_async(self._engine.start())
        
        # Start Watchdog (background scan for stuck tasks)
        self._run_async(self._task_watchdog.start_async())
        
        # Phase 3A: Start UpscaleQueue (background upscale processing)
        self._engine._upscale_queue.start()
        
        # Phase 4A: Start reCAPTCHA Pool (background token pre-fetch)
        # NOTE: start() uses asyncio.create_task() → must run inside the async loop,
        # not from the GUI thread (which has no running event loop).
        if (self._engine._recaptcha_pool and
                not self._engine._recaptcha_pool._running):
            self._run_async(self._start_recaptcha_pool())
        
        # Start log exporter (captures warnings/errors for auto-export)
        self._log_exporter.start()
        
        self._notify_status("Processing started")
    
    async def _start_recaptcha_pool(self):
        """Start reCAPTCHA pool inside the async event loop.
        
        RecaptchaPool.start() uses asyncio.create_task() internally,
        which requires a running event loop. This wrapper ensures it
        runs in the correct async context.
        """
        self._engine._recaptcha_pool.start()
    
    def stop_processing(self):
        """Stop processing via Engine.
        
        Properly awaits engine shutdown to prevent 'Task was destroyed'
        warnings from orphaned asyncio tasks.
        """
        self.state.is_processing = False
        
        # Signal Engine to stop (sets stop_event → workers exit loops)
        stop_future = self._run_async(self._engine.stop())
        if stop_future:
            try:
                stop_future.result(timeout=5.0)
            except Exception:
                pass
        
        # Wait for engine.start() to fully complete
        # (TaskGroup collects workers → finally block closes browsers)
        if self._engine_future:
            try:
                self._engine_future.result(timeout=15.0)
            except Exception:
                pass
            self._engine_future = None
        
        # Stop Watchdog
        self._task_watchdog.stop()
        
        # Phase 3A: Stop UpscaleQueue
        self._engine._upscale_queue.stop()
        
        # Phase 4A: Stop reCAPTCHA Pool
        if (self._engine._recaptcha_pool and
                self._engine._recaptcha_pool._running):
            self._engine._recaptcha_pool.stop()
        
        # Force-save journal after engine stop
        self._task_journal.force_save()
        
        # Auto-export structured logs (TESTER only)
        self._auto_export_logs()
        
        # Stop log exporter handler
        self._log_exporter.stop()
        
        self._notify_status("Processing stopped")
    
    def _auto_export_logs(self):
        """Auto-export structured session logs (TESTER only)."""
        try:
            if not self._license_client.can_see_dev_console():
                return  # Not a TESTER — skip
            
            filepath = self._log_exporter.export(
                dispatcher=self._dispatcher
            )
            if filepath:
                log.info(f"[AutoExport] Session log report: {filepath}")
        except Exception as e:
            log.warning(f"[AutoExport] Export failed: {e}")
    
    def pause_processing(self):
        """Pause processing — workers sleep, browsers stay alive.
        
        Much faster resume vs stop/start cycle.
        """
        if not self.state.is_processing:
            return
        if self._engine.is_paused:
            return
        
        self._run_async(self._engine.pause())
        self._notify_status("Processing paused")
    
    def resume_processing(self):
        """Resume processing — wake up sleeping workers.
        
        No engine restart needed — workers and browsers are still alive.
        """
        if not self.state.is_processing:
            return
        if not self._engine.is_paused:
            return
        
        self._run_async(self._engine.resume())
        self._notify_status("Processing resumed")
    
    def _process_result(self, task: Task, result: WorkerResult):
        """Process worker result."""
        if result.success:
            self._dispatcher.complete_task(
                task.id,
                result.output_uris,
            )
            self.state.completed_count += 1
        else:
            self._dispatcher.fail_task(task.id, result.error or "Unknown error")
            self.state.error_count += 1
        
        self.state.queue_count = max(0, self.state.queue_count - 1)
        self._notify_queue_updated()
    
    # === EVENT HANDLERS ===
    
    def _handle_task_completed(self, task: Task):
        """Handle task completion + detect group completion."""
        if self._on_task_completed:
            self._on_task_completed(task)
        self._notify_queue_updated()
        
        # Check if this task's group is now fully completed
        self._check_group_completion(task)
    
    def _check_group_completion(self, task: Task):
        """Check if the task's group is fully completed and fire notification."""
        for group_id, group in self._dispatcher._task_groups.items():
            if any(t.id == task.id for t in group.tasks):
                if group.status == "completed" and group_id not in self._notified_groups:
                    self._notified_groups.add(group_id)
                    if self._on_group_completed:
                        self._on_group_completed(group)
                break
    
    def _handle_task_failed(self, task: Task, error: str):
        """Handle task failure."""
        if self._on_task_failed:
            self._on_task_failed(task, error)
        self._notify_queue_updated()
    
    def _handle_progress(self, task_id: str, progress: int, status_text: str = ""):
        """Handle progress update from engine callback.
        Dispatcher.update_progress now fires _forward_progress_to_ui automatically.
        """
        self._dispatcher.update_progress(task_id, progress, status_text)
        # Note: UI callback is now triggered by dispatcher.update_progress → _forward_progress_to_ui
    
    def _forward_progress_to_ui(self, task_id: str, progress: int, status_text: str = ""):
        """Forward dispatcher progress updates to the UI callback."""
        if self._on_progress:
            self._on_progress(task_id, progress, status_text)
    
    def _handle_session_expired(self, email: str, event: SessionEvent):
        """Handle session expiry."""
        self._refresh_manager.request_refresh(email, event.value)
    
    def set_queue_updated_callback(self, callback):
        """Register callback for queue state changes (used by TabQueue)."""
        if callback not in self._on_queue_updated:
            self._on_queue_updated.append(callback)
    
    def set_progress_callback(self, callback):
        """Register callback for per-task progress updates (used by TabQueue)."""
        self._on_progress = callback
    
    def _notify_status(self, status: str):
        """Notify status change."""
        if self._on_status_changed:
            self._on_status_changed(status)
    
    def _notify_queue_updated(self):
        """Notify queue update (thread-safe)."""
        status = self.get_queue_status()
        for cb in self._on_queue_updated:
            try:
                cb(status)
            except Exception:
                pass
        # Push to DevConsole (thread-safe)
        if self._dev_console and hasattr(self._dev_console, 'update_queue_state'):
            from PySide6.QtCore import QMetaObject, Qt, QThread
            if QThread.currentThread() == self._dev_console.thread():
                try:
                    self._dev_console.update_queue_state(status)
                except Exception:
                    pass
            else:
                QMetaObject.invokeMethod(
                    self._dev_console, "update_queue_state_safe",
                    Qt.ConnectionType.QueuedConnection
                )
    
    # === PERMISSIONS ===
    
    def _update_permissions(self):
        """Update permissions from license."""
        if self._license_client.is_licensed:
            info = self._license_client.license_info
            if info:
                from config.constants import LicenseTier
                try:
                    tier = LicenseTier(info.tier.value)
                    self._permissions.set_role_from_tier(tier)
                except ValueError:
                    pass
    
    def has_feature(self, feature: Feature) -> bool:
        """Check if feature is available."""
        return self._permissions.has_feature(feature)
    
    # === GETTERS ===
    
    def get_queue_status(self) -> Dict:
        """Get current queue status."""
        dispatcher_status = self._dispatcher.get_status_summary()
        by_state = dispatcher_status.get("by_state", {})
        
        # AppState counters reset on app restart — fall back to dispatcher's
        # actual task state counts so persisted completed/failed are visible
        completed = self.state.completed_count or by_state.get("completed", 0)
        errors = self.state.error_count or by_state.get("failed", 0) + by_state.get("cancelled", 0)
        
        return {
            "total": self.state.queue_count or dispatcher_status.get("total", 0),
            "completed": completed,
            "errors": errors,
            "is_processing": self.state.is_processing,
            # Map dispatcher keys to Dev Console expected keys
            "pending": dispatcher_status.get("ready", 0) + dispatcher_status.get("waiting", 0),
            "processing": dispatcher_status.get("running", 0),
            **dispatcher_status,
        }
    
    def get_license_status(self) -> Dict:
        """Get license status for status bar display."""
        try:
            info = self._license_client.license_info
            return {
                "is_licensed": self._license_client.is_licensed,
                "is_trial": getattr(self._license_client, 'is_trial', False),
                "tier": info.tier.value if info else None,
                "days_remaining": info.days_remaining if info else 0,
            }
        except Exception:
            return {"is_licensed": False, "is_trial": False, "tier": None, "days_remaining": 0}
    
    def get_account_summary(self) -> Dict:
        """Get account summary for status bar display."""
        return {
            "total": self._multi_account.account_count,
            "ready": len(self._multi_account.ready_accounts),
            "active": self._multi_account.total_active,
        }
    
    def get_queue_items(self) -> List[Dict]:
        """Get all queue items for UI display."""
        items = []
        for task in self._dispatcher.get_all_tasks():
            items.append({
                "id": task.id,
                "prompt": task.prompt,
                "status": task.state.value,
                "progress": task.progress,
                "status_text": getattr(task, 'status_text', ''),
                "mode": _wf_display(task.workflow_type) if task.workflow_type else "T2V",
                "project": task.project_id or "Default",
                "error": task.error,
                "created_at": task.created_at,
            })
        return items
    
    def get_queue_groups(self) -> List[Dict]:
        """Get queue groups with child tasks for hierarchical UI display."""
        groups = self._dispatcher.get_all_groups()
        result = []
        for gid, group in groups.items():
            completed = sum(1 for t in group.tasks if t.state == TaskState.COMPLETED)
            total = len(group.tasks)
            # Detect mode/model from first task
            first = group.tasks[0] if group.tasks else None
            result.append({
                "id": gid,
                "name": group.name,
                "status": group.status,
                "progress": group.progress,
                "completed": completed,
                "total": total,
                "mode": _wf_display(first.workflow_type) if first else "T2V",
                "model": (first.model if first else ""),
                "output_folder": (first.output_folder if first else ""),
                "project_name": (first.project_name if first else ""),
                "aspect_ratio": (first.aspect_ratio if first else ""),
                "output_count": (first.output_count if first else 4),
                "created_at": group.created_at,
                "tasks": [
                    {
                        "id": t.id,
                        "index": i + 1,
                        "prompt": t.prompt,
                        "status": t.state.value,
                        "progress": t.progress,
                        "mode": _wf_display(t.workflow_type) if t.workflow_type else "T2V",
                        "has_continuation": t.parent_task_id is not None,
                        "parent_id": t.parent_task_id,
                        "error": t.error,
                        "output_count": t.output_count,
                        "output_files": list(t.output_uris) if t.output_uris else [],
                        "thumbnails": list(t.thumbnail_paths) if hasattr(t, 'thumbnail_paths') else [],
                        "image_paths": list(t.image_paths) if t.image_paths else [],
                        "continuation_frame": t.continuation_frame_local_path or "",
                        "upscale_status": getattr(t, 'upscale_status', ''),
                        "upscale_error": getattr(t, 'upscale_error', ''),
                        "image_upload_status": getattr(t, 'image_upload_status', ''),
                        "download_quality": getattr(t, 'download_quality', '720p'),
                        "video_outputs": [
                            {
                                "index": vo.index,
                                "quality": vo.quality,
                                "upscale_status": vo.upscale_status,
                                "upscale_error": vo.upscale_error,
                                "best_file": vo.best_file,
                                "border_color": vo.border_color,
                                "task_id": t.id,
                                "target_quality": getattr(t, 'download_quality', '1080p'),
                            }
                            for vo in (t.video_outputs if hasattr(t, 'video_outputs') else [])
                        ],
                    }
                    for i, t in enumerate(group.tasks)
                ],
            })
        return result
    
    def update_group_settings(self, group_id: str, settings: dict) -> bool:
        """Update settings on all tasks in a group.
        
        Args:
            group_id: Group ID
            settings: Dict with keys like 'model', 'aspect_ratio', 'output_folder',
                      'project_name', 'output_count'
        Returns True if group found and updated.
        """
        groups = self._dispatcher.get_all_groups()
        group = groups.get(group_id)
        if not group:
            return False
        
        for task in group.tasks:
            if 'model' in settings:
                task.model = settings['model']
            if 'aspect_ratio' in settings:
                task.aspect_ratio = settings['aspect_ratio']
            if 'output_folder' in settings:
                task.output_folder = settings['output_folder']
            if 'project_name' in settings:
                task.project_name = settings['project_name']
                # Also update group display name
                group.name = settings['project_name'] or group.name
            if 'output_count' in settings:
                task.output_count = settings['output_count']
        return True
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a specific task."""
        return self._dispatcher.cancel_task(task_id)
    
    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task."""
        return self._dispatcher.retry_task(task_id)
    
    def force_retry_task(self, task_id: str) -> bool:
        """Force retry a task regardless of state (including completed)."""
        return self._dispatcher.force_retry_task(task_id)
    
    def _get_account_for_reupscale(self, task_id: str):
        """Get account for re-upscale: MUST use assigned_account.
        
        media_id is account-bound — using a different account will 403.
        Only falls back to first account for legacy tasks with no
        assigned_account recorded.
        
        Returns:
            (account, error_msg) tuple. account is None if unavailable.
        """
        task = self._dispatcher.get_task(task_id)
        if not task:
            return None, f"⚠️ Task {task_id} not found"
        
        # Priority 1: Same account that processed the original prompt (REQUIRED)
        if task.assigned_account:
            account = self._multi_account.get_account(task.assigned_account)
            if account:
                return account, None
            # Account exists in config but not loaded/available
            return None, (
                f"⚠️ Account {task.assigned_account} not available. "
                f"Re-upscale requires the original account (media_id is account-bound)."
            )
        
        # No assigned_account recorded (legacy tasks before account tracking)
        if self._multi_account._accounts:
            return self._multi_account._accounts[0], None
        
        return None, "⚠️ No account available for re-upscale"
    
    def re_upscale_task(self, task_id: str):
        """Re-upscale a completed task using stored media_ids.
        
        Runs async engine method on the background event loop.
        Returns immediately — result is communicated via callbacks.
        """
        if not self._loop:
            return
        
        async def _run():
            account, error = self._get_account_for_reupscale(task_id)
            if not account:
                self._notify_status(error)
                return
            
            result = await self._engine.re_upscale_task(task_id, account)
            # Trigger queue refresh so UI updates status
            for cb in self._on_queue_updated:
                try:
                    cb({})
                except Exception:
                    pass
        
        asyncio.run_coroutine_threadsafe(_run(), self._loop)
    
    def re_upscale_single_video(self, task_id: str, video_index: int):
        """Re-upscale a single video by index.
        
        Called from UI right-click on red thumbnail.
        Runs async engine method on the background event loop.
        """
        if not self._loop:
            return
        
        async def _run():
            account, error = self._get_account_for_reupscale(task_id)
            if not account:
                self._notify_status(error)
                return
            
            result = await self._engine.re_upscale_single_video(
                task_id, video_index, account
            )
            # Trigger queue refresh so UI updates status
            for cb in self._on_queue_updated:
                try:
                    cb({})
                except Exception:
                    pass
        
        asyncio.run_coroutine_threadsafe(_run(), self._loop)
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks."""
        return self._dispatcher.retry_all_failed()
    
    def reset_task(self, task_id: str) -> bool:
        """Reset a task to initial state — delete cache/downloads, re-queue."""
        return self._dispatcher.reset_task(task_id)
    
    def reset_all_tasks(self) -> int:
        """Reset ALL non-running tasks to initial state."""
        return self._dispatcher.reset_all_tasks()
    
    def clear_all_tasks(self) -> int:
        """Clear all non-running tasks."""
        return self._dispatcher.clear_all()
    
    def clear_completed_tasks(self):
        """Clear completed/failed/cancelled tasks."""
        self._dispatcher.clear_completed()
    
    def get_permissions_summary(self) -> Dict:
        """Get permissions summary."""
        return {
            "role": self._permissions.role.value,
            "limits": self._permissions.get_limits_summary(),
            "features": self._permissions.get_feature_status(),
        }
    
    # === UI CALLBACK SETTERS ===
    
    def set_task_completed_callback(self, callback: Callable[[Task], None]):
        self._on_task_completed = callback
    
    def set_group_completed_callback(self, callback):
        """Set callback for group completion notification."""
        self._on_group_completed = callback
    
    def set_task_failed_callback(self, callback: Callable[[Task, str], None]):
        self._on_task_failed = callback
    
    def set_progress_callback(self, callback: Callable[[str, int, str], None]):
        self._on_progress = callback
    
    def set_queue_updated_callback(self, callback: Callable[[Dict], None]):
        if not hasattr(self, '_on_queue_updated') or not isinstance(self._on_queue_updated, list):
            self._on_queue_updated = []
        self._on_queue_updated.append(callback)
    
    def set_status_callback(self, callback: Callable[[str], None]):
        self._on_status_changed = callback
    
    # === SESSION PERSISTENCE ===
    
    def save_full_session(self, tabs_data: dict) -> bool:
        """Save full session: tab states + queue state.
        
        Args:
            tabs_data: {"t2v": {...}, "i2v": {...}, ...} from MainWindow
        
        Returns:
            True if saved successfully
        """
        from core.session_manager import SessionManager
        sm = SessionManager()
        
        # Export queue state from dispatcher
        queue_data = self._dispatcher.export_state()
        
        return sm.save_session({
            "tabs": tabs_data,
            "queue": queue_data,
        })
    
    def restore_session(self) -> dict:
        """Restore session from disk.
        
        Respects settings:
        - restore_queue_on_startup: if False, queue is NOT loaded (prevents stale tasks)
        - restore_tabs_on_startup: if False, tab data is NOT returned
        
        Returns:
            Full session data dict (tabs + queue).
        """
        from core.session_manager import SessionManager
        sm = SessionManager()
        
        data = sm.load_session()
        if not data:
            return {}
        
        # Only restore queue if setting is enabled
        # Default matches settings.py: restore_queue_on_startup=False
        restore_queue = False
        restore_tabs = True
        if self._settings:
            restore_queue = getattr(self._settings, 'restore_queue_on_startup', False)
            restore_tabs = getattr(self._settings, 'restore_tabs_on_startup', True)
        
        if restore_queue:
            queue_data = data.get("queue", {})
            if queue_data:
                count = self._dispatcher.import_state(queue_data)
                if count > 0:
                    # Sync AppState counter so status bar/DevConsole show correct total
                    self.state.queue_count = count
                    self._notify_queue_updated()
                    # Deferred re-notify: DevConsole may not exist yet at restore time
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(2000, self._notify_queue_updated)
                    print(f"[Session] Queue restored: {count} tasks")
        else:
            print("[Session] Queue restore SKIPPED (restore_queue_on_startup=False)")
        
        if not restore_tabs:
            data.pop("tabs", None)
            print("[Session] Tabs restore SKIPPED (restore_tabs_on_startup=False)")
        
        return data
    
    def clear_queue(self) -> int:
        """Clear all queue tasks (in-memory + persisted session).
        
        Returns:
            Number of tasks cleared
        """
        count = self._dispatcher.clear_all()
        self._notify_queue_updated()
        
        # Also delete the session file to prevent stale queue reload
        from core.session_manager import SessionManager
        sm = SessionManager()
        sm.delete_session()
        print(f"[Controller] Queue cleared: {count} tasks, session file deleted")
        return count
    
    def get_cache_stats(self) -> dict:
        """Get cache folder statistics."""
        from core.session_manager import SessionManager
        sm = SessionManager()
        cache_folder = self._settings.cache_folder if self._settings else None
        return sm.get_cache_stats(cache_folder or None)
    
    def clean_cache(self, max_age_days: int = 7) -> dict:
        """Clean old cache files."""
        from core.session_manager import SessionManager
        sm = SessionManager()
        cache_folder = self._settings.cache_folder if self._settings else None
        return sm.clean_cache(max_age_days, cache_folder or None)
    
    def clear_cache(self) -> dict:
        """Clear all cache files."""
        from core.session_manager import SessionManager
        sm = SessionManager()
        cache_folder = self._settings.cache_folder if self._settings else None
        return sm.clear_cache(cache_folder or None)
