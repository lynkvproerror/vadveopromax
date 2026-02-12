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

# Services
from services.license_client import LicenseClient
from services.permissions import PermissionsSystem, Role, Feature

# Config
from config.settings import AppSettings
from config.constants import WorkflowType, resolve_model_key


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
        
        # Event callbacks (set by UI)
        self._on_task_completed: Optional[Callable[[Task], None]] = None
        self._on_task_failed: Optional[Callable[[Task, str], None]] = None
        self._on_progress: Optional[Callable[[str, int], None]] = None
        self._on_queue_updated: List[Callable[[Dict], None]] = []
        self._on_account_changed: Optional[Callable[[str], None]] = None
        self._on_status_changed: Optional[Callable[[str], None]] = None
        
        # DevConsole reference (set by UI via set_dev_console)
        self._dev_console = None
        self._settings = None  # AppSettings, set via set_settings()
        
        # Async event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._engine_future = None  # Track engine.start() Future for clean shutdown
        
        # ProfilesController reference (set by UI via set_profiles_controller)
        self._profiles_controller = None
        
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
        
        # Start session monitoring
        self._session_monitor.start_monitoring()
        
        # Start refresh manager
        self._refresh_manager.start_auto_check()
        
        # Check license
        self._update_permissions()
        
        self._notify_status("Controller started")
    
    def stop(self):
        """Stop the application controller."""
        # Stop processing first (awaits engine shutdown properly)
        if self.state.is_processing:
            self.stop_processing()
        
        self.state.is_running = False
        
        # Stop monitoring
        self._session_monitor.stop_monitoring()
        self._refresh_manager.stop_auto_check()
        
        # Stop async loop (safe now — engine already stopped)
        self._stop_async_loop()
        
        self._notify_status("Controller stopped")
    
    def _auto_launch_browsers(self):
        """Auto-launch browsers for all profiles on app start.
        
        Startup sequence (single browser per profile):
        1. Sync profiles to runtime
        2. Inject ProfilesController ref into each AccountManager
        3. Open debug browsers in hidden mode (the ONLY browser per profile)
        4. startup_browsers() → AccountManager.ensure_browser() attaches
           to the already-running debug browser (no new headless browser)
        5. Token + reCAPTCHA extracted from the shared browser page
        """
        import logging
        import time
        log = logging.getLogger(__name__)
        
        async def _launch():
            try:
                # Step 1: Sync profiles first
                self.sync_profiles_to_runtime()
                log.info("[AutoLaunch] Profiles synced to runtime")
                
                # Step 2: Inject ProfilesController into each AccountManager
                # so ensure_browser() can find debug browser pages
                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                    for acc in self._multi_account._accounts:
                        acc.set_profiles_controller(self._profiles_controller)
                    log.info(f"[AutoLaunch] ProfilesController injected into {len(self._multi_account._accounts)} accounts")
                
                # Step 3: Open debug browsers in hidden mode FIRST
                # This is the SINGLE browser per profile — no separate headless browser
                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                    profiles = self._profiles_controller.get_all_profiles()
                    for p in profiles:
                        email = p.get("email")
                        if email and p.get("is_ready"):
                            log.info(f"[AutoLaunch] 🔇 Starting hidden browser for {email}...")
                            success = self._profiles_controller.open_browser_for_debug(
                                email, 
                                on_state_change=self._on_debug_browser_state_change
                            )
                            if success:
                                # Wait for browser to fully start and page to load
                                time.sleep(5)
                                self._profiles_controller.hide_debug_browser(email)
                                log.info(f"[AutoLaunch] ✅ {email} browser hidden")
                    
                    self._push_browser_status()
                
                # Step 4: startup_browsers → ensure_browser() will ATTACH to debug pages
                # (not launch new headless browsers)
                if self._multi_account._accounts:
                    log.info(f"[AutoLaunch] Connecting {len(self._multi_account._accounts)} accounts to debug browsers...")
                    await self._multi_account.startup_browsers(headless=True)
                    log.info("[AutoLaunch] ✅ All accounts connected to browsers")
                else:
                    log.info("[AutoLaunch] No accounts to connect")
                
                # Push final browser status to DevConsole
                self._push_browser_status()
                    
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
    
    def _on_debug_browser_state_change(self, email: str, state: str):
        """Callback when a debug browser changes state (visible/hidden/closed).
        
        Called from background browser thread. Thread-safe via _push_browser_status.
        """
        self._push_browser_status()
        self._push_session_data()
    
    def get_browser_status(self) -> list:
        """Get browser status for all accounts.
        
        Combines runtime account data with ProfilesController profiles
        and debug browser state so the DevConsole shows accurate info.
        
        Returns list of dicts: [{email, state, enabled, slots, has_browser}, ...]
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
                }
                result.append(info)
        
        return result
    
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
                
                # Session status — consider debug browser as valid session
                if runtime_acc.is_ready:
                    session_status = "🟢 Ready (Production)"
                elif debug_browser_active and profile.is_ready:
                    session_status = "🟢 Session via Debug Browser"
                elif runtime_acc.is_enabled:
                    session_status = "🟡 Enabled (Waiting Token)"
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
                    # No runtime token — fallback to tokens.json for display
                    access_token = token_info.get("access_token", "")
                    if access_token:
                        expires_at = token_info.get("expires_at", 0)
                        now_ts = datetime.now().timestamp()
                        if expires_at and (expires_at - now_ts) <= 0:
                            hours_ago = int(abs(expires_at - now_ts) / 3600)
                            token_expiry = f"🔄 Cached token ({hours_ago}h ago)"
                        elif expires_at:
                            mins = int((expires_at - now_ts) / 60)
                            token_expiry = f"✅ Cached ({mins}m left)"
                        else:
                            token_expiry = "📁 From cache"
                    elif debug_browser_active:
                        token_expiry = "🟢 Will extract on next API call"
                    else:
                        token_expiry = "❌ No token"
                
                # reCAPTCHA
                recaptcha_age = status.get("recaptcha_age", "N/A")
                needs_recaptcha = status.get("needs_recaptcha")
                if recaptcha_age == "infs" or recaptcha_age == "N/A":
                    if debug_browser_active:
                        recaptcha_status = "🟢 Will fetch on demand"
                    else:
                        recaptcha_status = "⚪ Not initialized"
                elif needs_recaptcha:
                    recaptcha_status = f"🔄 Need refresh (age: {recaptcha_age})"
                else:
                    recaptcha_status = f"✅ Valid (age: {recaptcha_age})"
                
                # Browser session (headless)
                browser_alive = status.get("browser_alive", False)
                
                # Slots
                slots_display = status.get("slots", "?")
                
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
    
    def _start_async_loop(self):
        """Start background async event loop."""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
    
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
            tasks.append(task)
        
        group = TaskGroup(id=group_id, name=f"Batch {len(tasks)}", tasks=tasks)
        
        # === DEBUG: Export resolved task structure ===
        log = logging.getLogger(__name__)
        log.info(f"{'='*60}")
        log.info(f"[ADD TO QUEUE] group_id={group_id}")
        log.info(f"  workflow    : {workflow.name}")
        log.info(f"  model      : {model_display!r} → {model}")
        log.info(f"  aspect_ratio: {raw_ar} → {aspect_ratio}")
        log.info(f"  dual_frame : {dual_frame}")
        log.info(f"  output_count: {output_count}")
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
    
    def add_i2v_batch(self, prompts: List, settings: Dict) -> str:
        """Add Image-to-Video batch to queue.
        
        Args:
            prompts: List of PromptRow objects with image_tag
            settings: Sidebar settings dict
        """
        per_prompt_images = {}  # Bug 2 fix: per-prompt image mapping
        prompt_texts = []
        continuation_map = {}
        
        for i, p in enumerate(prompts):
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tag') and p.image_tag:
                # Bug 2 fix: Each prompt gets its OWN image list
                per_prompt_images[i] = [p.image_tag]
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                continuation_map[i] = p.continuation_from - 1
        
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
                all_images.extend(p.image_tags[:3])  # Max 3 images per prompt
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
            prompts: List of PromptRow objects with image_tag
            settings: Sidebar settings dict
        """
        images = []
        prompt_texts = []
        for p in prompts:
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            if hasattr(p, 'image_tag') and p.image_tag:
                images.append(p.image_tag)
        
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
    
    def start_processing(self):
        """Start processing queue via Engine.
        
        Engine uses asyncio.TaskGroup for proper async worker management.
        The Engine.start() coroutine runs in the background async loop.
        """
        if self.state.is_processing:
            return
        
        self.state.is_processing = True
        
        # Issue E: Sync profiles to runtime before starting
        self.sync_profiles_to_runtime()
        
        # Per-account worker settings (max_slots, retry_count, request_timeout)
        # are now read directly from each AccountManager at runtime.
        # No global max_workers needed.
        
        # Anti-Detect Spam settings (global — applies to all accounts)
        self._engine._anti_detect_enabled = getattr(self.settings, 'anti_detect_enabled', True)
        self._engine._anti_detect_delay_min = getattr(self.settings, 'anti_detect_delay_min', 1.0)
        self._engine._anti_detect_delay_max = getattr(self.settings, 'anti_detect_delay_max', 5.0)
        
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
        
        self._notify_status("Processing started")
    
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
        
        self._notify_status("Processing stopped")
    
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
        """Handle task completion."""
        if self._on_task_completed:
            self._on_task_completed(task)
        self._notify_queue_updated()
    
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
        return {
            "total": self.state.queue_count,
            "completed": self.state.completed_count,
            "errors": self.state.error_count,
            "is_processing": self.state.is_processing,
            **self._dispatcher.get_status_summary(),
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
                    }
                    for i, t in enumerate(group.tasks)
                ],
            })
        return result
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a specific task."""
        return self._dispatcher.cancel_task(task_id)
    
    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task."""
        return self._dispatcher.retry_task(task_id)
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks."""
        return self._dispatcher.retry_all_failed()
    
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
        restore_queue = True
        restore_tabs = True
        if self._settings:
            restore_queue = getattr(self._settings, 'restore_queue_on_startup', False)
            restore_tabs = getattr(self._settings, 'restore_tabs_on_startup', True)
        
        if restore_queue:
            queue_data = data.get("queue", {})
            if queue_data:
                count = self._dispatcher.import_state(queue_data)
                if count > 0:
                    self._notify_queue_updated()
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
