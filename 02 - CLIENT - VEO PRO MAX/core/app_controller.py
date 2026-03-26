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
from core.queue_dto import VideoSlotDTO, TaskDTO, GroupDTO

# Services
from security.license_client import LicenseClient
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
        self._license_valid = False  # G0: Must be validated before any generation
        
        # Engine — replaces manual threading.Thread worker management
        # Engine uses asyncio.TaskGroup for proper async worker coroutines
        self._engine = Engine(
            account_manager=self._multi_account,
            dispatcher=self._dispatcher,
            api_client=self._api_client,
        )
        self._engine._app_controller = self  # Fix A: direct reference (replaces _account_manager._app_controller chain)
        self._engine_gen = 0  # ★ Shutdown race guard: incremented on each start_processing()
        
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
        self._pipeline_awaiting_queue: bool = False  # Pipeline mid-transition (defer auto-stop)
        self._pipeline_mode_active: bool = False  # True while ANY pipeline stage is running
        
        # DevConsole reference (set by UI via set_dev_console)
        self._dev_console = None
        # NOTE: self.settings is set in __init__ line 78 from constructor arg.
        # self._settings is the PRIVATE alias used by some methods (restore_session, cache).
        # Wire them to avoid the stale-None bug.
        self._settings = self.settings
        
        # Performance tracking
        self._start_time = datetime.now()
        self._perf_timer = None  # QTimer, started when DevConsole opens
        self._prune_timer = None  # QTimer: periodic task memory cleanup
        
        # Async event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._engine_future = None  # Track engine.start() Future for clean shutdown
        self._keepalive_future = None  # Track keepalive loop Future
        self._warmup_in_progress: set = set()  # Dedup proactive reCAPTCHA warmups
        self._restart_tracker: Dict[str, dict] = {}  # email → {count, last_time} — anti-loop guard
        
        # ProfilesController — shared singleton (also used by tab_settings)
        from core.profiles_controller import get_profiles_controller
        self._profiles_controller = get_profiles_controller()
        self._profiles_controller._app_controller = self  # G6: backref for license check in add_profile
        
        # Extension bridge — WebSocket server for Chrome Extension tokens
        from core.extension_bridge import ExtensionBridge
        self._extension_bridge = ExtensionBridge(port=8765)
        self._extension_bridge.on_headers_update = self._on_extension_headers_update
        self._extension_bridge.on_extension_connect = self._on_extension_connect
        self._extension_bridge.on_unregistered_connection = self._on_unregistered_extension
        self._extension_bridge.on_readiness_token = self._on_readiness_token
        self._extension_bridge.on_account_logged_out = self._on_account_logged_out
        self._extension_bridge.on_tab_dead = self._on_tab_dead
        self._extension_bridge.on_extension_lost = self._on_extension_lost
        
        # ★ Fix 2: Tab death tracking for auto Chrome kill on repeated failures
        self._tab_death_tracker: dict = {}   # email → last death timestamp
        self._tab_death_count: dict = {}     # email → consecutive count within window
        
        # Wire extension bridge into RefreshManager for auto header refresh
        self._refresh_manager.set_extension_bridge(self._extension_bridge)
        
        # Wire extension bridge into Engine for UpscaleQueue fallback injection
        self._engine._extension_bridge = self._extension_bridge
        
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
        
        # ★ Auto pre-upload debounce state
        self._preupload_pending: list = []  # LibraryImage objects waiting for debounce
        self._preupload_debounce_handle = None  # asyncio.TimerHandle
        
        # Setup callbacks
        self._setup_callbacks()
    
    # ── Public Accessors (Issue #4: encapsulate Dispatcher access) ──
    
    @property
    def ready_count(self) -> int:
        """Number of browser slots ready to accept tasks."""
        return self._dispatcher.ready_count if self._dispatcher else 0
    
    
    @property
    def dispatcher(self):
        """Public accessor for dispatcher (read-only operations from UI)."""
        return self._dispatcher
    
    def _setup_callbacks(self):
        """Setup internal callbacks between components."""
        # Dispatcher callbacks
        self._dispatcher.set_callbacks(
            on_completed=self._handle_task_completed,
            on_failed=self._handle_task_failed,
        )
        
        # Session monitor
        self._session_monitor.set_expired_callback(self._handle_session_expired)
        
        # ★ Image Library: auto pre-upload when images added
        try:
            from services.image_library import get_image_library
            _lib = get_image_library()
            _lib.on_upload_needed(self._on_library_upload_needed)
        except Exception:
            pass
    
    # ── Auto Pre-Upload on Library Change ──
    
    def _on_library_upload_needed(self, images: list):
        """Callback from ImageLibrary when new images need pre-upload.
        
        Debounces 2s to batch multiple rapid add_image() calls,
        then triggers parallel pre-upload to all active accounts.
        """
        self._preupload_pending.extend(images)
        
        # Cancel previous debounce timer
        if self._preupload_debounce_handle is not None:
            try:
                self._preupload_debounce_handle.cancel()
            except Exception:
                pass
        
        # Schedule debounced execution on async loop
        if self._loop and self._loop.is_running():
            self._preupload_debounce_handle = self._loop.call_later(
                2.0, self._fire_library_pre_upload
            )
    
    def _fire_library_pre_upload(self):
        """Fire the debounced pre-upload (runs on async loop thread)."""
        images = list(self._preupload_pending)
        self._preupload_pending.clear()
        self._preupload_debounce_handle = None
        
        if not images:
            return
        
        # Collect enabled accounts with active connections
        enabled = [
            acc for acc in self._multi_account._accounts
            if acc.is_enabled
        ]
        if not enabled:
            log.debug(
                f"[LibPreUpload] {len(images)} image(s) queued but no "
                f"active accounts — will upload on next connect"
            )
            return
        
        log.info(
            f"[LibPreUpload] 📸 Auto pre-uploading {len(images)} new image(s) "
            f"→ {len(enabled)} account(s) (debounced)"
        )
        asyncio.ensure_future(self._do_library_pre_upload(images, enabled))
    
    async def _do_library_pre_upload(self, images: list, accounts: list):
        """Upload new library images to all accounts.
        
        Rate limiting: Semaphore(10) per account — max 10 concurrent uploads.
        Accounts upload in parallel via asyncio.gather().
        """
        import time as _time
        from core.media_handler import MediaHandler
        
        t0 = _time.monotonic()
        total_uploaded = 0
        
        async def _upload_for_account(account):
            """Upload pending images for one account with Semaphore(10).
            
            Uses asyncio.gather() to run up to 10 uploads concurrently.
            """
            nonlocal total_uploaded
            email = account.email
            sem = asyncio.Semaphore(10)
            uploaded = 0
            _stop = False  # Shared flag to stop all tasks on auth failure
            
            async def _upload_one(img):
                """Upload a single image, gated by semaphore."""
                nonlocal uploaded, _stop
                if _stop:
                    return
                
                async with sem:
                    if _stop or not Path(img.path).exists():
                        return
                    
                    try:
                        # Encode image in thread
                        result = await asyncio.to_thread(
                            MediaHandler.image_to_base64, img.path
                        )
                        if not result:
                            log.warning(
                                f"[LibPreUpload] Failed to encode: {img.filename}"
                            )
                            return
                        img_b64, mime_type = result
                        
                        # Fresh token
                        token = await account.ensure_valid_token()
                        if not token:
                            log.warning(
                                f"[LibPreUpload] No token for {email}, "
                                f"stopping pre-upload"
                            )
                            _stop = True
                            return
                        
                        # Upload with retry (429 + 401)
                        for _attempt in range(3):
                            resp = await self._api_client.upload_image(
                                access_token=token,
                                recaptcha_token="",
                                image_base64=img_b64,
                                mime_type=mime_type,
                                file_name=img.filename,
                                account_headers=account.get_api_headers(),
                            )
                            
                            if resp.success:
                                # Extract mediaId (multi-format)
                                media_id = ""
                                mgid = resp.data.get("mediaGenerationId")
                                if mgid:
                                    media_id = (
                                        mgid.get("mediaGenerationId", "")
                                        if isinstance(mgid, dict) else mgid
                                    )
                                if not media_id:
                                    media = resp.data.get("media")
                                    if isinstance(media, dict):
                                        media_id = (
                                            media.get("name", "") or
                                            media.get("mediaGenerationId", "") or
                                            media.get("mediaId", "")
                                        )
                                    elif isinstance(media, list) and media:
                                        first = media[0]
                                        if isinstance(first, dict):
                                            media_id = (
                                                first.get("name", "") or
                                                first.get("mediaGenerationId", "") or
                                                first.get("mediaId", "")
                                            )
                                
                                if media_id:
                                    # Store in library (persistent)
                                    from services.image_library import get_image_library
                                    get_image_library().set_media_id(
                                        img.path, email, media_id
                                    )
                                    # Also populate engine in-memory cache
                                    if hasattr(self._engine, '_upload_cache'):
                                        cache_key = f"{img.path}:{email}"
                                        self._engine._upload_cache[cache_key] = media_id
                                        if img.content_hash:
                                            hash_key = f"hash:{img.content_hash}:{email}"
                                            self._engine._upload_cache[hash_key] = media_id
                                    uploaded += 1
                                    log.info(
                                        f"[LibPreUpload] ✅ {img.filename} → "
                                        f"{media_id[:30]}... ({email})"
                                    )
                                return  # Success
                            else:
                                err_str = str(resp.error)
                                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                    wait = (2 ** _attempt) * 5
                                    log.warning(
                                        f"[LibPreUpload] 429 on {img.filename} → "
                                        f"retry {_attempt+1}/3 in {wait}s"
                                    )
                                    await asyncio.sleep(wait)
                                    continue
                                elif getattr(resp, 'response_code', 0) == 401:
                                    log.warning(
                                        f"[LibPreUpload] 401 → refreshing "
                                        f"token for {email}"
                                    )
                                    account._session.token_expires = None
                                    token = await account.ensure_valid_token()
                                    if not token:
                                        _stop = True
                                        return
                                    continue
                                else:
                                    log.warning(
                                        f"[LibPreUpload] Upload failed: "
                                        f"{img.filename} ({email}): {resp.error}"
                                    )
                                    return
                        
                    except Exception as e:
                        log.warning(
                            f"[LibPreUpload] Error: {img.filename} "
                            f"({email}): {e}"
                        )
            
            # Filter images that need upload, then gather with concurrency limit
            pending = [img for img in images if email not in img.media_ids]
            if pending:
                await asyncio.gather(
                    *[_upload_one(img) for img in pending],
                    return_exceptions=True,
                )
            
            total_uploaded += uploaded
            if uploaded:
                log.info(
                    f"[LibPreUpload] {email}: {uploaded}/{len(images)} uploaded"
                )
        
        # All accounts in parallel
        await asyncio.gather(
            *[_upload_for_account(acc) for acc in accounts],
            return_exceptions=True,
        )
        
        elapsed = _time.monotonic() - t0
        if total_uploaded:
            # Persist library index
            try:
                from services.image_library import get_image_library
                get_image_library()._save_index()
            except Exception:
                pass
            log.info(
                f"[LibPreUpload] ✅ Done: {total_uploaded} upload(s) across "
                f"{len(accounts)} account(s) in {elapsed:.1f}s"
            )
    
    def flush_pending_pre_upload(self, on_done: Callable = None):
        """Flush debounce and run immediate pre-upload. Calls on_done when complete.
        
        Used by Pipeline to ensure all library images are pre-uploaded
        to all accounts BEFORE dispatching the next stage's tasks.
        
        Args:
            on_done: Optional callback invoked (on main thread) after pre-upload finishes.
        """
        # Cancel debounce timer
        if self._preupload_debounce_handle is not None:
            try:
                self._preupload_debounce_handle.cancel()
            except Exception:
                pass
            self._preupload_debounce_handle = None
        
        # Collect ALL library images that need upload (not just pending debounce batch)
        try:
            from services.image_library import get_image_library
            lib = get_image_library()
            all_images = lib.get_images()
        except Exception:
            all_images = list(self._preupload_pending) if self._preupload_pending else []
        
        self._preupload_pending.clear()
        
        # Filter images that need upload for at least one account
        enabled = [
            acc for acc in self._multi_account._accounts
            if acc.is_enabled
        ]
        if not enabled or not all_images:
            log.debug("[LibPreUpload:Flush] No accounts or no images → skip")
            if on_done:
                on_done()
            return
        
        # Filter to only images missing mediaIds for any enabled account
        needs_upload = []
        for img in all_images:
            for acc in enabled:
                if acc.email not in img.media_ids:
                    needs_upload.append(img)
                    break
        
        if not needs_upload:
            log.info("[LibPreUpload:Flush] All library images already uploaded → skip")
            if on_done:
                on_done()
            return
        
        log.info(
            f"[LibPreUpload:Flush] ⚡ Immediate pre-upload: {len(needs_upload)} image(s) "
            f"→ {len(enabled)} account(s)"
        )
        
        async def _flush_and_callback():
            await self._do_library_pre_upload(needs_upload, enabled)
            if on_done:
                # Call on_done on main thread (UI-safe)
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, on_done)
        
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(_flush_and_callback(), self._loop)
    
    # === LIFECYCLE ===
    
    def start(self):
        """Start the application controller."""
        if self.state.is_running:
            return
        
        self.state.is_running = True
        
        # Install per-account structured logging
        from core.account_logger import install_account_logging
        install_account_logging()
        
        # Start async loop in background
        self._start_async_loop()
        
        # Start Extension bridge WebSocket server
        if self._loop:
            try:
                log.info(f"[AppController] Starting bridge... (loop={self._loop}, running={self._loop.is_running()})")
                future = asyncio.run_coroutine_threadsafe(self._extension_bridge.start(), self._loop)
                future.result(timeout=10.0)  # Wait and catch any startup errors
                actual_port = getattr(self._extension_bridge, '_port', '???')
                log.info(f"[AppController] ✅ Extension bridge started on ws://127.0.0.1:{actual_port}")
                
                # Verify port is actually LISTENING
                import socket
                try:
                    test_sock = socket.create_connection(('127.0.0.1', actual_port), timeout=2)
                    test_sock.close()
                    log.info(f"[AppController] ✅ Port {actual_port} verified LISTENING — extension can connect")
                except (ConnectionRefusedError, OSError) as sock_e:
                    log.error(f"[AppController] ❌ Port {actual_port} NOT LISTENING despite start() success: {sock_e}")
            except TimeoutError:
                log.error("[AppController] ❌ Extension bridge start TIMED OUT (10s) — WS server not running!")
            except Exception as e:
                log.error(f"[AppController] ❌ Extension bridge failed to start: {type(e).__name__}: {e}", exc_info=True)
        else:
            log.error("[AppController] ❌ Async loop not ready (self._loop is None) — bridge not started!")
        
        # Start session monitoring
        self._session_monitor.start_monitoring()
        
        # Start refresh manager
        self._refresh_manager.start_auto_check()
        
        # Check license
        self._update_permissions()
        
        # Integrity check (compares critical file hashes — no-op in dev mode)
        try:
            from security.integrity_check import verify_startup_integrity
            integrity = verify_startup_integrity()
            if not integrity['skipped'] and not integrity['passed']:
                log.critical(f"[Security] ❌ Integrity check FAILED: {integrity['failures']}")
        except ImportError:
            pass  # Module not available — dev environment
        
        # Anti-tamper runtime guards (7 layers: monkey-patch, extraction, debugger, process, proxy, VM, sandbox)
        self._tamper_detected = False
        try:
            from security.anti_tamper import register_critical_modules, run_all_guards
            register_critical_modules()
            guards = run_all_guards()
            if not guards['passed']:
                log.critical(f"[Security] ❌ Anti-tamper CRITICAL guards FAILED: {guards['failures']}")
                self._tamper_detected = True
                self._license_valid = False  # Soft-block: disable premium features
                # Propagate tamper flag to PermissionsSystem
                if hasattr(self, '_permissions') and self._permissions:
                    self._permissions._tamper_detected = True
                # Invalidate cached license to force TRIAL limitations
                try:
                    self._license_client.storage.clear()
                    self._license_client._invalidate_validate_cache()
                except Exception:
                    pass
            if guards.get('warnings'):
                log.warning(f"[Security] ⚠️ Anti-tamper warnings: {guards['warnings']}")
        except ImportError:
            pass
        
        # Start TaskJournal (event subscriber + periodic save)
        self._task_journal.start(loop=self._loop)
        self._status_aggregator.start()
        
        # Start periodic task pruning (every 10 min → free RAM from completed tasks)
        self._start_prune_timer()
        
        # Crash recovery: load journal snapshot if available
        snapshot = self._task_journal.load_snapshot()
        if snapshot and snapshot.get("task_count", 0) > 0:
            recovered = self._dispatcher.import_state(snapshot)
            if recovered > 0:
                log.info(f"[AppController] Recovered {recovered} tasks from journal")
        
        self._notify_status("Controller started")
        
        # ★ Start Tab Keepalive service (app-level, independent of engine)
        # Prevents Chrome from freezing VEO tabs when engine is idle.
        # Uses two asyncio events for coordination with engine:
        #   _keepalive_yield: SET=active, CLEAR=yield to engine
        #   _keepalive_stop:  SET=shutdown
        self._start_tab_keepalive()
        
        # Auto-launch Chrome browsers for all ready profiles (runs in background)
        # Must be called AFTER async loop + extension bridge are ready
        self._auto_launch_browsers()
    
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
        
        # Persist settings & profiles to disk before shutdown
        try:
            from config.settings import save_settings
            save_settings()
        except Exception:
            pass
        try:
            if self._profiles_controller:
                self._profiles_controller.save_profiles()
        except Exception:
            pass
        
        # Stop monitoring
        self._session_monitor.stop_monitoring()
        self._refresh_manager.stop_auto_check()
        
        # Stop task journal (final save on shutdown)
        self._task_journal.stop()
        self._task_watchdog.stop()
        self._status_aggregator.stop()
        self._stop_prune_timer()
        
        # Stop Tab Keepalive service
        self._stop_tab_keepalive()
        
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
            # Store authorization header if provided (Bearer or SAPISIDHASH)
            if access_token:
                if access_token.startswith("Bearer "):
                    account._session._sapisidhash = access_token
                    log.debug(f"[ExtensionBridge] Bearer token stored for {email} ({len(access_token)} chars)")
                elif access_token.startswith("SAPISIDHASH"):
                    account._session._sapisidhash = access_token
                    log.debug(f"[ExtensionBridge] SAPISIDHASH stored for {email}")
            log.info(f"[ExtensionBridge] Headers updated for {email}: {list(headers.keys())}")
            
            # Cross-pollinate: if this account now has good x-client-data,
            # share it with other accounts that have short values
            new_cd = headers.get("x-client-data", "")
            if len(new_cd) >= 20:
                self._multi_account.fix_short_client_data()
                self._notify_status(f"🔑 {email}: x-client-data received ({len(new_cd)} chars) — tokens ready")
            
            self._push_all_status_debounced()  # Round 5 Fix G: Debounce instead of direct push from asyncio thread
        else:
            log.debug(f"[ExtensionBridge] No account found for {email} (headers ignored)")
    
    def _on_extension_connect(self, email: str):
        """Callback from ExtensionBridge when an extension connects.
        
        Immediately requests fresh headers + access token so the app
        has data right away without waiting for the next auto-check cycle.
        Also schedules proactive reCAPTCHA warm-up after page settles.
        """
        log.info(f"[ExtensionBridge] Extension connected for {email}")
        self._notify_status(f"Extension connected for {email}")
        
        # ★ Close CircuitBreaker immediately — extension is alive, no need to wait 30s backoff
        if hasattr(self, '_engine') and self._engine:
            state = self._engine._circuit_state.get(email)
            if state in ("open", "half_open"):
                self._engine._close_circuit_breaker(email)
                log.info(f"[AppController] ⚡ CircuitBreaker closed on reconnect for {email}")
            
            # ★ Clear tab-dead cooldown — extension reconnected, account is alive again
            if email in self._engine._account_cooldowns:
                del self._engine._account_cooldowns[email]
                evt = self._engine._get_cooldown_event(email)
                evt.set()  # Unblock engine workers
                log.info(f"[AppController] ✅ Cooldown cleared on reconnect for {email}")
            
            # ★ Unpause upscale queue for this account
            uq = getattr(self._engine, '_upscale_queue', None)
            if uq and hasattr(uq, 'unpause_account'):
                uq.unpause_account(email)
        
        # Defensive: ensure account has bridge reference NOW
        # (startup timing: extension may connect after account created but before
        # sync_profiles_to_runtime injects bridge)
        account = self._multi_account.get_account(email)
        if account:
            self._ensure_account_bridge(account)
        
        self._push_all_status_debounced()  # Round 4 Fix C: Coalesce instead of single push
        
        # Immediate data refresh — don't wait for auto-check
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(self._refresh_extension_data(email))
            # Proactive reCAPTCHA warm-up: schedule after page settles (~10s)
            # This pre-caches a valid token so "Start All" works instantly.
            asyncio.ensure_future(self._proactive_recaptcha_warmup(email))
            
            # ★ Image Library: auto pre-upload for newly connected account
            # So hot-added accounts get all library images uploaded immediately
            if account:
                try:
                    from services.image_library import get_image_library
                    _lib = get_image_library()
                    pending = _lib.get_pending_uploads(email)
                    if pending:
                        log.info(f"[ExtensionBridge] 📸 Image Library: {len(pending)} pending upload(s) for {email}")
                        asyncio.ensure_future(
                            _lib.trigger_pre_upload([account], self._api_client)
                        )
                except Exception as e:
                    log.debug(f"[ExtensionBridge] Image Library pre-upload skipped for {email}: {e}")
        except RuntimeError:
            asyncio.run(self._refresh_extension_data(email))
        except Exception as e:
            log.debug(f"[ExtensionBridge] Startup refresh scheduling failed: {e}")
        
        # Tier check for this account (after data refresh completes)
        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(self._enforce_single_account_tier(email))
        except Exception:
            pass
    
    def _on_readiness_token(self, email: str, token: str):
        """Callback from ExtensionBridge when readiness check yields a valid token.
        
        Caches the trial-execute token on the AccountManager so the next
        API call can use it instantly (no extra round-trip to extension).
        Fix E: Also inject into RecaptchaPool so any worker can benefit.
        """
        # Cache on AccountManager (works even before engine starts)
        account = self._multi_account.get_account(email)
        if account:
            account._token_cache.set(token)
            account._session.update_recaptcha(token)
        
        # Also inject into RecaptchaPool if engine is running
        if hasattr(self, '_engine') and self._engine:
            pool = getattr(self._engine, '_recaptcha_pool', None)
            if pool:
                pool.inject_token(email, token)
        
        log.debug(
            f"[ReadinessToken] Cached trial token for {email} "
            f"({len(token)} chars) → AM + Pool"
        )
    
    async def _proactive_recaptcha_warmup(self, email: str):
        """Proactive reCAPTCHA warm-up — run after extension connects.
        
        Waits for VEO page to settle (~10s), then trial-executes
        grecaptcha to pre-cache a valid token. This eliminates the
        cold-start penalty when user presses "Start All".
        
        The valid trial token gets cached via on_readiness_token callback
        on AccountManager + RecaptchaPool.
        """
        try:
            # Dedup: skip if warmup already running for this email
            if email in self._warmup_in_progress:
                log.debug(f"[ProactiveWarmup] {email}: already in progress, skipping duplicate")
                return
            self._warmup_in_progress.add(email)
            
            # Wait for VEO page to fully load (reCAPTCHA widget needs ~10s)
            log.info(f"[ProactiveWarmup] {email}: waiting 10s for reCAPTCHA widget...")
            await asyncio.sleep(10.0)
            
            if not self._extension_bridge.is_connected(email):
                log.debug(f"[ProactiveWarmup] {email}: extension disconnected, skipping")
                return
            
            # Trial-execute reCAPTCHA (result cached by on_readiness_token)
            ready = await self._extension_bridge.check_recaptcha_ready(
                email, timeout=20.0
            )
            
            if ready:
                log.info(
                    f"[ProactiveWarmup] {email}: ✅ reCAPTCHA pre-warmed — "
                    f"token cached, ready for instant Start All"
                )
                self._notify_status(f"✅ {email}: reCAPTCHA ready — account prepared")
            else:
                log.warning(
                    f"[ProactiveWarmup] {email}: ⚠️ reCAPTCHA not ready yet — "
                    f"will retry on next readiness check"
                )
                # Retry once after additional 10s
                await asyncio.sleep(10.0)
                if self._extension_bridge.is_connected(email):
                    ready2 = await self._extension_bridge.check_recaptcha_ready(
                        email, timeout=20.0
                    )
                    if ready2:
                        log.info(f"[ProactiveWarmup] {email}: ✅ reCAPTCHA ready on retry")
                    else:
                        # ★ Fix 3: Escalate — try full reload + hard navigation
                        # Instead of just logging warning and giving up,
                        # actively recover the reCAPTCHA widget during startup.
                        log.warning(
                            f"[ProactiveWarmup] {email}: ❌ still not ready → "
                            f"escalating to full reload"
                        )
                        try:
                            await self._extension_bridge._trigger_refresh(
                                email, "ProactiveWarmup escalation", level="full"
                            )
                            await asyncio.sleep(25.0)  # VEO page load + reCAPTCHA init
                            
                            if not self._extension_bridge.is_connected(email):
                                log.debug(f"[ProactiveWarmup] {email}: disconnected during reload")
                            else:
                                ready3 = await self._extension_bridge.check_recaptcha_ready(
                                    email, timeout=20.0
                                )
                                if ready3:
                                    log.info(f"[ProactiveWarmup] {email}: ✅ reCAPTCHA ready after reload")
                                    self._notify_status(f"✅ {email}: reCAPTCHA recovered after reload")
                                else:
                                    log.warning(
                                        f"[ProactiveWarmup] {email}: 🔄 reload failed → hard navigation"
                                    )
                                    await self._extension_bridge.trigger_hard_navigation(email)
                                    await asyncio.sleep(20.0)
                                    ready4 = await self._extension_bridge.check_recaptcha_ready(
                                        email, timeout=20.0
                                    )
                                    if ready4:
                                        log.info(f"[ProactiveWarmup] {email}: ✅ reCAPTCHA ready after hard nav")
                                    else:
                                        log.error(
                                            f"[ProactiveWarmup] {email}: ❌ reCAPTCHA dead after "
                                            f"all recovery attempts — engine will handle on Start All"
                                        )
                        except Exception as warmup_err:
                            log.debug(f"[ProactiveWarmup] {email}: escalation error: {warmup_err}")
        except Exception as e:
            log.debug(f"[ProactiveWarmup] {email}: warm-up failed (non-fatal): {e}")
        finally:
            self._warmup_in_progress.discard(email)
    
    def _start_tab_keepalive(self):
        """Start the Tab Keepalive service (app-level).
        
        Creates two asyncio events for engine coordination and launches
        the keepalive coroutine in the background async loop.
        
        Lifecycle:
          App start      → keepalive ACTIVE (yield=SET)
          start_processing → keepalive PAUSED (yield=CLEAR)
          stop_processing  → keepalive ACTIVE (yield=SET)
          App exit        → keepalive STOPPED (stop=SET)
        """
        if not self._loop:
            log.warning("[TabKeepalive] No async loop — cannot start")
            return
        
        # Create control events IN the async loop's context
        # Must be created in the same loop that will use them
        async def _create_and_start():
            yield_event = asyncio.Event()
            yield_event.set()  # Start ACTIVE (engine not running yet)
            
            stop_event = asyncio.Event()
            
            # Inject events into Engine so start_processing/stop_processing can access them
            self._engine._keepalive_yield = yield_event
            self._engine._keepalive_stop = stop_event
            
            log.info("[TabKeepalive] Service starting (app-level, independent of engine)")
        
        # Create events
        future = asyncio.run_coroutine_threadsafe(_create_and_start(), self._loop)
        try:
            future.result(timeout=3.0)
        except Exception as e:
            log.error(f"[TabKeepalive] Failed to create control events: {e}")
            return
        
        # Launch the keepalive coroutine (fire-and-forget)
        self._keepalive_future = asyncio.run_coroutine_threadsafe(
            self._engine._tab_keepalive_loop(), self._loop
        )
        log.info("[TabKeepalive] Service launched in background loop")
    
    def _stop_tab_keepalive(self):
        """Stop the Tab Keepalive service (app shutdown)."""
        stop_event = getattr(self._engine, '_keepalive_stop', None)
        if stop_event:
            # Signal stop from any thread (Event.set is thread-safe for asyncio.Event
            # only if called from the same loop — use call_soon_threadsafe)
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(stop_event.set)
            log.info("[TabKeepalive] Stop signal sent")
        
        # Wait for graceful exit
        if self._keepalive_future:
            try:
                self._keepalive_future.result(timeout=5.0)
            except Exception:
                pass
            self._keepalive_future = None
    
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
                        self._push_all_status_debounced()  # Round 5 Fix F: Coalesce
        
        try:
            asyncio.ensure_future(_assign_pending())
        except Exception as e:
            log.error(f"[AutoAssign] Failed: {e}")
    
    def _on_account_logged_out(self, email: str, reason: str):
        """Callback from ExtensionBridge when logout is detected on a VEO tab.
        
        GAP #7 fix: Also pause account workers via long cooldown (300s)
        to prevent futile 401/403 retry loops on logged-out account.
        """
        log.warning(f"[AppController] 🔴 Account logged out: {email} (reason: {reason})")
        try:
            # Mark profile as not-ready in persistent data
            if hasattr(self, '_profiles_controller') and self._profiles_controller:
                self._profiles_controller.update_profile(email, is_ready=False)
                log.info(f"[AppController] Profile {email} marked is_ready=False after logout")
            
            # GAP #7: Pause workers — set long cooldown so workers stop attempting
            if hasattr(self, '_engine') and self._engine:
                from datetime import datetime, timedelta
                self._engine._account_cooldowns[email] = datetime.now() + timedelta(seconds=300)
                evt = self._engine._get_cooldown_event(email)
                evt.clear()  # Block all workers for this account
                log.warning(f"[AppController] ⏸️ Workers paused for {email} (300s cooldown after logout)")
            
            self._push_all_status_debounced()  # Round 5 Fix F: Coalesce
        except Exception as e:
            log.debug(f"[AppController] Status push failed after logout: {e}")
    
    def _on_tab_dead(self, email: str, reason: str):
        """Callback from ExtensionBridge when a VEO tab is declared dead.
        
        ★ Fix 2: Track consecutive tab deaths per account.
        - 1st death within 10 min: pause workers (existing cooldown behavior)
        - 2nd+ death within 10 min: kill Chrome + restart browser (breaks recovery loop)
        On reconnect → _on_extension_connect will clear cooldown + unpause.
        """
        import time as _time
        now = _time.time()
        
        # ── Track consecutive tab deaths ──
        last_death = self._tab_death_tracker.get(email, 0)
        if now - last_death < 600:  # Within 10 minute window
            deaths = self._tab_death_count.get(email, 0) + 1
        else:
            deaths = 1  # Reset — outside window
        self._tab_death_tracker[email] = now
        self._tab_death_count[email] = deaths
        
        log.warning(
            f"[AppController] 💀 Tab dead #{deaths}: {email} "
            f"(reason: {reason}) — pausing workers"
        )
        
        try:
            # Pause engine workers — set long cooldown so workers stop attempting
            if hasattr(self, '_engine') and self._engine:
                from datetime import datetime, timedelta
                self._engine._account_cooldowns[email] = datetime.now() + timedelta(seconds=300)
                evt = self._engine._get_cooldown_event(email)
                evt.clear()  # Block all engine workers for this account
                log.warning(f"[AppController] ⏸️ Engine workers paused for {email} (300s cooldown after tab death)")
            
            # Pause upscale queue workers
            if hasattr(self, '_engine') and self._engine:
                uq = getattr(self._engine, '_upscale_queue', None)
                if uq and hasattr(uq, 'pause_account'):
                    uq.pause_account(email)
                    log.warning(f"[AppController] ⏸️ UpscaleQueue paused for {email}")
            
            # ★ Fix 2: 2+ deaths in 10 min → Kill Chrome + restart browser
            if deaths >= 2:
                log.warning(
                    f"[AppController] 💀💀 Tab dead #{deaths} for {email} "
                    f"— KILLING Chrome and restarting browser"
                )
                self._force_restart_browser(email)
            
            self._push_all_status_debounced()  # Round 5 Fix F: Coalesce
        except Exception as e:
            log.debug(f"[AppController] Status push failed after tab death: {e}")
    
    def _force_restart_browser(self, email: str):
        """Kill Chrome process + restart browser for an account.
        
        ★ Fix 2: Breaks infinite recovery loop when frozen tab/extension
        cannot self-recover. Runs in background thread to avoid blocking.
        On success, _on_extension_connect will auto-clear cooldown.
        """
        import threading
        def _do_restart():
            import time as _time
            try:
                # 1. Find profile path
                pc = self._profiles_controller
                profile = pc.get_profile(email) if pc else None
                profile_path = getattr(profile, 'browser_profile_path', None) if profile else None
                
                if not profile_path:
                    log.error(f"[AppController] Cannot force-restart: no profile_path for {email}")
                    return
                
                # 2. Kill Chrome
                from core.chrome_manager import kill_chrome
                killed = kill_chrome(profile_path)
                log.info(
                    f"[AppController] Chrome {'killed' if killed else 'already dead'} "
                    f"for {email}"
                )
                
                # 3. Short delay for process cleanup
                _time.sleep(3)
                
                # 4. Relaunch browser via ensure_browser (async)
                account = self._multi_account.get_account(email)
                if account and self._loop and not self._loop.is_closed():
                    async def _relaunch():
                        try:
                            await account.ensure_browser(headless=True)
                            log.info(f"[AppController] ✅ Browser force-restarted for {email}")
                        except Exception as e:
                            log.error(f"[AppController] Browser relaunch failed for {email}: {e}")
                    
                    import asyncio
                    asyncio.run_coroutine_threadsafe(_relaunch(), self._loop)
                else:
                    log.warning(f"[AppController] No account/loop for relaunch: {email}")
                    
            except Exception as e:
                log.error(f"[AppController] Force-restart error for {email}: {e}")
        
        threading.Thread(
            target=_do_restart, name=f"force-restart-{email}", daemon=True
        ).start()
    
    def _on_extension_lost(self):
        """Callback from ExtensionBridge when all connections are lost for >60s.
        
        Auto-reinstall extension if user accidentally removed it from Chrome.
        ★ After reinstall, also ensures a VEO tab exists so the extension's
        offscreen document creates its WebSocket connection.
        Runs in background thread to avoid blocking the async event loop.
        """
        log.warning("[AppController] 🚨 Extension lost — auto-reinstalling...")
        import threading
        def _reinstall():
            try:
                results = self.ensure_all_extensions()
                if results:
                    log.info(f"[AppController] Extension auto-reinstall results: {results}")
                else:
                    log.warning("[AppController] No browsers available for extension reinstall")
                    return
                
                # ★ Post-reinstall: ensure VEO tab exists for each browser
                # Extension offscreen document only creates WebSocket when a
                # VEO tab triggers the content script → register → offscreen WS connect.
                # Without a VEO tab, extension sits idle at conns=0 forever.
                import time as _time
                _time.sleep(3)  # Brief delay for extension to initialize
                
                pc = self._profiles_controller if hasattr(self, '_profiles_controller') else None
                if pc and hasattr(pc, '_debug_browsers'):
                    for email in list(pc._debug_browsers.keys()):
                        try:
                            db = pc._debug_browsers.get(email)
                            cdp_port = getattr(db, 'cdp_port', None) if db else None
                            if not cdp_port:
                                continue
                            
                            # Check if extension connected after reinstall
                            if self._extension_bridge.is_connected(email):
                                log.debug(f"[ExtRecovery] {email}: already connected, skipping tab creation")
                                continue
                            
                            # Navigate to VEO via CDP to trigger extension content script
                            import urllib.request
                            import json as _json
                            
                            VEO_URL = "https://labs.google/fx/vi/tools/flow"
                            
                            # First check if a VEO tab already exists
                            try:
                                _tabs_req = urllib.request.urlopen(
                                    f"http://127.0.0.1:{cdp_port}/json",
                                    timeout=5
                                )
                                _tabs = _json.loads(_tabs_req.read().decode())
                                veo_tab = next(
                                    (t for t in _tabs if 'labs.google' in (t.get('url', ''))),
                                    None
                                )
                                
                                if veo_tab:
                                    # VEO tab exists — reload it to re-inject content script
                                    ws_url = veo_tab.get('webSocketDebuggerUrl')
                                    if ws_url:
                                        log.info(f"[ExtRecovery] {email}: VEO tab exists — reloading to re-inject content script")
                                        import websocket
                                        _ws = websocket.create_connection(ws_url, timeout=5)
                                        _ws.send(_json.dumps({
                                            "id": 1, "method": "Page.reload",
                                            "params": {"ignoreCache": True}
                                        }))
                                        _ws.recv()
                                        _ws.close()
                                    continue
                                
                                # No VEO tab — create one via CDP
                                log.info(f"[ExtRecovery] {email}: no VEO tab — creating via CDP")
                                _new_tab_url = f"http://127.0.0.1:{cdp_port}/json/new?{VEO_URL}"
                                _new_req = urllib.request.urlopen(_new_tab_url, timeout=10)
                                _new_tab = _json.loads(_new_req.read().decode())
                                log.info(
                                    f"[ExtRecovery] ✅ Created VEO tab for {email}: "
                                    f"tabId={_new_tab.get('id', '?')}"
                                )
                            except Exception as tab_err:
                                log.warning(f"[ExtRecovery] VEO tab recovery failed for {email}: {tab_err}")
                                
                        except Exception as e:
                            log.debug(f"[ExtRecovery] Tab recovery error for {email}: {e}")
                
            except Exception as e:
                log.error(f"[AppController] Extension auto-reinstall error: {e}")
        threading.Thread(target=_reinstall, name="extension-lost-reinstall", daemon=True).start()
    
    async def _refresh_extension_data(self, email: str):
        """Request fresh headers + access token from extension immediately."""
        try:
            # 1. Refresh headers (lightweight — avoids full VEO tab reload)
            await self._extension_bridge.refresh_headers_lightweight(email, timeout=10)
            log.info(f"[ExtensionBridge] ✅ Startup headers refreshed for {email}")
            
            # 2. Probe for x-browser-validation (cross-origin fetch triggers Chrome to add it)
            has_validation = await self._extension_bridge.probe_browser_headers(email, timeout=10)
            if has_validation:
                log.info(f"[ExtensionBridge] ✅ x-browser-validation captured for {email}")
            else:
                log.warning(f"[ExtensionBridge] ⚠️ x-browser-validation NOT captured — API requests may get 403")
        except Exception as e:
            log.debug(f"[ExtensionBridge] Startup header refresh failed: {e}")
        
        try:
            # 2. Get fresh access token
            # request_access_token returns Optional[str] (token directly)
            result = await self._extension_bridge.request_access_token(email, timeout=10)
            token = result if isinstance(result, str) else (
                result.get('token') if isinstance(result, dict) else None
            )
            if token:
                account = self._multi_account.get_account(email)
                if account:
                    from datetime import timedelta
                    account._session.access_token = token
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
        # Guard: prevent double launch (called from both start() and set_profiles_controller())
        if getattr(self, '_browsers_launched', False):
            log.debug("[AutoLaunch] Already launched — skipping duplicate call")
            return
        self._browsers_launched = True
        
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
                        acc.extension_bridge = self._extension_bridge
                        acc._parent_manager = self._multi_account  # for bridge auto-recovery
                    log.info(f"[AutoLaunch] ProfilesController + ExtensionBridge injected into {len(self._multi_account._accounts)} accounts")
                
                # Step 2.5: Pre-launch tier check — call /v1/credits via HTTP (no browser)
                # Uses cached access tokens from tokens.json to get real-time tier from server
                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                    try:
                        from core.token_manager import get_token_manager
                        import urllib.request, urllib.error, json as _json
                        
                        _tm = get_token_manager()
                        _API_URL = "https://aisandbox-pa.googleapis.com/v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"
                        _pre_disabled = 0
                        
                        for p_obj in self._profiles_controller._profiles:
                            if not p_obj.is_enabled:
                                continue  # already disabled
                            
                            _token = _tm.get_valid_token(p_obj.email)
                            if not _token:
                                log.debug(f"[PreTierCheck] No valid token for {p_obj.email} — skip (will check after browser)")
                                continue
                            
                            # Call /v1/credits API with Bearer token
                            try:
                                _req = urllib.request.Request(_API_URL, headers={
                                    "Authorization": f"Bearer {_token}"
                                })
                                with urllib.request.urlopen(_req, timeout=10) as _resp:
                                    _data = _json.loads(_resp.read().decode())
                                
                                _tier = _data.get("userPaygateTier", "")
                                _sku = _data.get("sku", "")
                                _credits_val = _data.get("credits", 0)
                                
                                # Update profile with fresh server data
                                p_obj.paygate_tier = _tier or p_obj.paygate_tier
                                p_obj.sku = _sku or p_obj.sku
                                p_obj.credits = _credits_val
                                p_obj.subscription_fetched = True
                                
                                if _tier == "PAYGATE_TIER_NOT_PAID":
                                    p_obj.is_enabled = False
                                    for acc in self._multi_account._accounts:
                                        if acc.email == p_obj.email:
                                            acc.disable()
                                            break
                                    _pre_disabled += 1
                                    log.warning(f"[PreTierCheck] ⛔ {p_obj.email}: Free → disabled (skipping browser)")
                                else:
                                    _label = "Ultra" if _tier == "PAYGATE_TIER_TWO" else "Pro" if _tier == "PAYGATE_TIER_ONE" else _tier
                                    log.info(f"[PreTierCheck] ✅ {p_obj.email}: {_label}")
                            except Exception as _e:
                                log.debug(f"[PreTierCheck] API call failed for {p_obj.email}: {_e} — will recheck after browser")
                        
                        if _pre_disabled > 0:
                            self._profiles_controller.save_profiles()
                            self._notify_profiles_changed()
                            log.warning(f"[PreTierCheck] ⛔ {_pre_disabled} Free account(s) disabled before browser launch")
                    except Exception as _pre_err:
                        log.debug(f"[PreTierCheck] Pre-launch tier check failed: {_pre_err}")
                
                # Step 3: Open debug browsers
                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                    profiles = self._profiles_controller.get_all_profiles()
                    ready_profiles = [p for p in profiles if p.get("email") and p.get("is_enabled", True)]
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
                            from config.settings import get_settings as _get_settings
                            _s = _get_settings()
                            if getattr(_s, 'smart_hide_enabled', True) or getattr(_s, 'hide_all_browsers', False):
                                self._profiles_controller.hide_debug_browser(email)
                                log.info(f"[AutoLaunch] ✅ {email} browser hidden")
                            else:
                                log.info(f"[AutoLaunch] ✅ {email} browser visible (smart-hide disabled)")
                        else:
                            log.warning(f"[AutoLaunch] ⚠️ Failed to open browser for {email}")
                    
                    self._push_browser_status()
                
                # Step 4: Connect accounts (ensure_browser polls until page ready)
                if self._multi_account._accounts:
                    log.info(f"[AutoLaunch] Connecting {len(self._multi_account._accounts)} accounts to debug browsers...")
                    await self._multi_account.startup_browsers(headless=True)
                    log.info("[AutoLaunch] ✅ All accounts connected to browsers")
                    
                    # Defensive sweep: ensure bridge is injected on ALL accounts
                    # (covers startup timing race where accounts created before bridge)
                    for acc in self._multi_account._accounts:
                        self._ensure_account_bridge(acc)
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
                
                # Step 6: Ensure extensions are installed/up-to-date across all profiles
                try:
                    results = self.ensure_all_extensions()
                    if results:
                        log.info(f"[AutoLaunch] Extension check complete: {results}")
                except Exception as e:
                    log.warning(f"[AutoLaunch] Extension batch check failed: {e}")
                
                # Step 7: Proactive reCAPTCHA warm-up for ALL connected emails.
                # _on_extension_connect already schedules warmup for naturally-connecting
                # extensions, but Step 5's assign_email() bypass that callback.
                # Fire warmup for any connected email that didn't get one yet.
                if self._extension_bridge:
                    connected = self._extension_bridge.get_connected_emails()
                    for email in connected:
                        asyncio.ensure_future(self._proactive_recaptcha_warmup(email))
                    if connected:
                        log.info(f"[AutoLaunch] 🔥 Proactive reCAPTCHA warm-up scheduled for {len(connected)} emails")
                
                # Step 7.5: Enforce account tiers — disable Free, sync paygate_tier
                try:
                    await self._enforce_account_tiers()
                    log.info("[AutoLaunch] ✅ Account tier enforcement complete")
                except Exception as e:
                    log.warning(f"[AutoLaunch] Account tier check failed: {e}")
                
                self._push_browser_status()
                
                # ★ Final re-hide sweep: after ALL setup steps complete,
                # re-hide any Chrome windows that appeared during extension
                # install, reCAPTCHA warmup, or late renderer spawns.
                from config.settings import get_settings as _get_launch_s
                _ls = _get_launch_s()
                if getattr(_ls, 'hide_all_browsers', False) or getattr(_ls, 'smart_hide_enabled', True):
                    pc = self._profiles_controller if hasattr(self, '_profiles_controller') else None
                    if pc and hasattr(pc, '_debug_browsers'):
                        for _email in list(pc._debug_browsers.keys()):
                            try:
                                pc.hide_debug_browser(_email)
                            except Exception:
                                pass
                        log.info(f"[AutoLaunch] 🔇 Final re-hide sweep: {len(pc._debug_browsers)} browser(s)")
                
                log.info("[AutoLaunch] ✅ Background browser launch complete")
                self._notify_status("🌐 Browsers launched — waiting for extension connection...")
                
                # Step 8: Auto pre-upload Image Library images
                # Upload all library images immediately so they're cached before Start All
                try:
                    from services.image_library import get_image_library
                    _lib = get_image_library()
                    _enabled = [
                        acc for acc in self._multi_account._accounts
                        if acc.is_enabled
                    ]
                    if _lib.image_count > 0 and _enabled:
                        _pending = sum(
                            len(_lib.get_pending_uploads(acc.email))
                            for acc in _enabled
                        )
                        if _pending > 0:
                            log.info(
                                f"[AutoLaunch] 📸 Image Library pre-upload: "
                                f"{_lib.image_count} images × {len(_enabled)} accounts "
                                f"({_pending} pending)"
                            )
                            asyncio.ensure_future(
                                _lib.trigger_pre_upload(_enabled, self._api_client)
                            )
                        else:
                            log.info(f"[AutoLaunch] 📸 Image Library: {_lib.image_count} images, all already uploaded")
                    elif _lib.image_count == 0:
                        log.debug("[AutoLaunch] 📸 Image Library: empty, skipping pre-upload")
                except Exception as e:
                    log.debug(f"[AutoLaunch] Image Library pre-upload skipped: {e}")
                    
            except Exception as e:
                log.error(f"[AutoLaunch] Failed to launch browsers: {e}")
        
        # Run in background async loop
        if self._loop:
            asyncio.run_coroutine_threadsafe(_launch(), self._loop)
    
    def _hot_add_profile(self, email: str):
        """Hot-add a single profile mid-session (no app restart needed).
        
        Called automatically when a new profile is added via add_profile().
        Performs the same steps as _auto_launch_browsers but for one profile:
        1. Sync profile to runtime (creates AccountManager)
        2. Open debug browser
        3. Inject extension bridge + assign email
        4. Proactive reCAPTCHA warm-up
        """
        if not self._loop or not email:
            return
        
        async def _launch_single():
            try:
                log.info(f"[HotAdd] 🔥 Hot-adding profile: {email}")
                
                # Step 1: Sync profile to runtime
                self.sync_profiles_to_runtime()
                log.info(f"[HotAdd] ✅ Profile synced to runtime: {email}")
                
                # Step 2: Inject bridge into new account
                acc = self._multi_account.get_account(email)
                if acc:
                    self._ensure_account_bridge(acc)
                    acc.set_profiles_controller(self._profiles_controller)
                    acc._parent_manager = self._multi_account
                    log.info(f"[HotAdd] ✅ Bridge + controller injected: {email}")
                
                # Step 3: Open debug browser
                if self._profiles_controller:
                    success = self._profiles_controller.open_browser_for_debug(
                        email,
                        on_state_change=self._on_debug_browser_state_change
                    )
                    if success:
                        await asyncio.sleep(2)  # Brief wait for browser to start
                        from config.settings import get_settings as _gs
                        s = _gs()
                        if getattr(s, 'smart_hide_enabled', True) or getattr(s, 'hide_all_browsers', False):
                            self._profiles_controller.hide_debug_browser(email)
                        log.info(f"[HotAdd] ✅ Debug browser opened: {email}")
                    else:
                        log.warning(f"[HotAdd] ⚠️ Failed to open browser: {email}")
                
                # Step 4: Connect account to browser
                if acc:
                    try:
                        await acc.ensure_browser(headless=True)
                        log.info(f"[HotAdd] ✅ Account connected to browser: {email}")
                    except Exception as e:
                        log.warning(f"[HotAdd] Browser connect error (non-fatal): {e}")
                
                # Step 5: Assign email to extension (wait for it to connect)
                if self._extension_bridge:
                    await asyncio.sleep(3)  # Wait for extension to load
                    if not self._extension_bridge.is_connected(email):
                        await self._extension_bridge.assign_email(email)
                        log.info(f"[HotAdd] 📧 Email assigned to extension: {email}")
                    
                    # Ensure extension is installed
                    try:
                        results = self.ensure_all_extensions()
                        if results:
                            log.info(f"[HotAdd] ✅ Extension verified: {results}")
                    except Exception:
                        pass
                
                # Step 6: Proactive reCAPTCHA warm-up
                if self._extension_bridge and self._extension_bridge.is_connected(email):
                    asyncio.ensure_future(self._proactive_recaptcha_warmup(email))
                    log.info(f"[HotAdd] 🔥 reCAPTCHA warm-up scheduled: {email}")
                
                # Step 6b: NOW notify Engine (browser + extension + reCAPTCHA ready)
                # Must happen AFTER Steps 3-6 to prevent:
                # - _account_watcher calling ensure_browser() while browser already opening
                # - foreman starting without x-client-data/reCAPTCHA
                acc = self._multi_account.get_account(email)  # Re-fetch in case it changed
                if acc and hasattr(self, '_engine') and self._engine:
                    if self._engine.is_running:
                        self._engine.add_account_hot(acc)
                        log.info(f"[HotAdd] ✅ Engine notified — workers will spawn for {email}")
                
                self._push_all_status_debounced()  # Round 5 Fix F: Coalesce
                self._notify_status(f"✅ Profile {email} added and connected!")
                log.info(f"[HotAdd] ✅ Hot-add complete: {email}")
                
                # Step 7: Auto-resume Engine if stopped but tasks pending
                if (hasattr(self, '_engine') and self._engine 
                        and not self._engine.is_running
                        and self._dispatcher 
                        and self._dispatcher.ready_count > 0):
                    pending = self._dispatcher.ready_count
                    log.info(
                        f"[HotAdd] 🔄 Engine stopped but {pending} tasks pending "
                        f"— auto-resuming with {email}"
                    )
                    # Fix: sync stale state — engine may have stopped naturally
                    # without calling stop_processing(), leaving is_processing=True
                    if self.state.is_processing:
                        log.info("[HotAdd] Resetting stale is_processing flag")
                        self.state.is_processing = False
                    try:
                        self.start_processing()
                        log.info(f"[HotAdd] ✅ Engine auto-resumed — {pending} tasks will process")
                    except Exception as e:
                        log.warning(f"[HotAdd] ⚠️ Auto-resume failed: {e}")
                
            except Exception as e:
                log.error(f"[HotAdd] ❌ Failed to hot-add {email}: {e}")
        
        # Run in background async loop
        asyncio.run_coroutine_threadsafe(_launch_single(), self._loop)
    # ── Public API for UI (Fix B: encapsulate private access) ──────
    
    @property
    def extension_bridge(self):
        """Public read-only accessor for extension bridge."""
        return self._extension_bridge
    
    @property
    def dev_console(self):
        """Public accessor for DevConsole widget."""
        return self._dev_console
    
    @dev_console.setter
    def dev_console(self, widget):
        """Set DevConsole widget (called by UI on toggle)."""
        self._dev_console = widget
    
    def push_status_updates(self):
        """Push all status updates to DevConsole — single public entry point."""
        self._push_browser_status()
        self._push_session_data()
        self._push_pool_status()
        self._push_extension_status()
        self._notify_queue_updated()
    
    def push_browser_status(self):
        """Public: Push browser status to DevConsole (used by UI components)."""
        self._push_browser_status()
    
    def push_session_data(self):
        """Public: Push session data to DevConsole (used by UI components)."""
        self._push_session_data()
    
    def push_pool_status(self):
        """Public: Push pool status to DevConsole (used by UI components)."""
        self._push_pool_status()
    
    @property
    def image_enhancer(self):
        """Public: Get ImageEnhancer instance (used by image widgets)."""
        return self._image_enhancer
    
    def _push_browser_status(self):
        """Push current browser status to DevConsole (thread-safe).
        
        Can be called from any thread. Uses QMetaObject.invokeMethod
        to ensure the actual Qt widget update runs on the GUI thread.
        Round 4 Fix D: Don't call get_browser_status() on background thread.
        """
        if not hasattr(self, '_dev_console') or not self._dev_console:
            return
        
        from PySide6.QtCore import QMetaObject, Qt, QThread
        
        if QThread.currentThread() == self._dev_console.thread():
            # Already on GUI thread — safe to call directly
            status = self.get_browser_status()
            self._dev_console.update_browser_status(status)
        else:
            # Background thread — schedule on GUI thread
            # (get_browser_status will be called by update_browser_status_safe on GUI thread)
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
    
    def _push_all_status_debounced(self):
        """Coalesce browser + session + extension status pushes (300ms debounce).
        
        Round 4 Fix C: Prevents triple-push storms when extension connect /
        browser state change fires all three pushes simultaneously.
        
        Thread-safe: if called from non-GUI thread, uses QTimer.singleShot(0)
        to marshal to GUI thread, preventing QObject::startTimer crash.
        """
        from PySide6.QtCore import QThread, QTimer
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app and QThread.currentThread() != app.thread():
                # Non-GUI thread: schedule on GUI thread
                QTimer.singleShot(0, self._push_all_status_debounced_impl)
                return
        except Exception:
            pass
        self._push_all_status_debounced_impl()
    
    def _push_all_status_debounced_impl(self):
        """Internal: create/start QTimer — MUST run on GUI thread."""
        if not hasattr(self, '_status_push_timer') or self._status_push_timer is None:
            from PySide6.QtCore import QTimer
            self._status_push_timer = QTimer()
            self._status_push_timer.setSingleShot(True)
            self._status_push_timer.setInterval(300)
            self._status_push_timer.timeout.connect(self._flush_all_status_push)
        if not self._status_push_timer.isActive():
            self._status_push_timer.start()
    
    def _flush_all_status_push(self):
        """Execute all three status pushes in one batch (on GUI thread via timers)."""
        # R6-C: Skip if DevConsole not attached — nothing to push to
        if not self._dev_console:
            return
        self._push_browser_status()
        self._push_session_data()
        self._push_extension_status()
    
    def _on_debug_browser_state_change(self, email: str, state: str):
        """Callback when a debug browser changes state (visible/hidden/closed/disconnected).
        
        Called from background browser thread. Thread-safe via _push_browser_status.
        Log only — do NOT kill or restart browser automatically.
        Round 4 Fix C: Coalesce triple push into single debounced batch.
        """
        self._push_all_status_debounced()
        
        if state in ("closed", "disconnected"):
            log.info(f"[AppController] Browser {state} for {email} — no auto-restart (by design)")
    
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
        
        log.info(f"[AppController] Restarting browser for {email}...")
        
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

    def reload_extension_for(self, email: str) -> bool:
        """Reload the Chrome extension for a specific account.
        
        Chrome-type-aware strategy:
        1. Try hot-reload via WebSocket (chrome.runtime.reload()) — fastest, both types
        2a. Branded Chrome: CDP-based reinstall via extension_manager
        2b. CfT: restart browser (--load-extension flag reloads automatically)
        
        Thread-safe. Called from UI thread via background thread.
        
        Returns:
            True if extension reloaded/reinstalled and reconnected, False otherwise
        """
        bridge = getattr(self, '_extension_bridge', None)
        
        # Strategy 1: WebSocket hot-reload (if extension is connected)
        if bridge:
            conn = None
            try:
                import asyncio
                loop = getattr(self, '_loop', None) or asyncio.get_event_loop()
                
                # Check if extension is connected for this email
                conn = asyncio.run_coroutine_threadsafe(
                    asyncio.coroutine(lambda: bridge._find_connection(email))(),
                    loop,
                ).result(timeout=3) if hasattr(bridge, '_find_connection') else None
            except Exception:
                conn = None
            
            if conn:
                log.info(f"[AppController] Reloading extension via WebSocket for {email}...")
                import asyncio
                loop = getattr(self, '_loop', None) or asyncio.get_event_loop()
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        bridge.reload_extension(email, timeout=15.0),
                        loop,
                    )
                    result = future.result(timeout=20)
                    
                    if result:
                        log.info(f"[AppController] ✅ Extension reloaded for {email}")
                    else:
                        log.warning(f"[AppController] Extension reload may have failed for {email}")
                    
                    self._push_extension_status()
                    return result
                except Exception as e:
                    log.error(f"[AppController] Extension reload error for {email}: {e}")
        
        # Strategy 2: Chrome-type-aware fallback
        pc = self._profiles_controller
        if not pc:
            log.error("[AppController] No ProfilesController — cannot reload extension")
            return False
        
        # Find the Chrome CDP port and exe from PID file (stored by chrome_manager)
        # NOTE: _debug_browsers stores {cmd_queue, state, context, page} — no cdp_port
        cdp_port = None
        chrome_exe = ""
        profile = pc.get_profile(email)
        if profile and profile.browser_profile_path:
            from core.chrome_manager import _load_pid_file
            pid_data = _load_pid_file(profile.browser_profile_path)
            if pid_data:
                cdp_port = pid_data.get("port")
                chrome_exe = pid_data.get("chrome_exe", "")
        
        if not cdp_port:
            log.error(f"[AppController] No CDP port found for {email} — try restarting browser")
            return False
        
        from core.chrome_manager import is_branded_chrome
        
        if is_branded_chrome(chrome_exe):
            # Strategy 2a: Branded Chrome → CDP-based reinstall
            log.info(f"[AppController] Branded Chrome — using CDP reinstall for {email}...")
            try:
                from core.extension_manager import reinstall_extension
                from pathlib import Path
                
                _client_dir = Path(__file__).resolve().parent.parent
                _extension_dir = _client_dir / "extension"
                
                result = reinstall_extension(cdp_port, str(_extension_dir), show_window=True)
                
                if result:
                    log.info(f"[AppController] ✅ Extension reinstalled via CDP for {email}")
                    # Wait for extension to reconnect via WebSocket before updating status
                    if bridge:
                        try:
                            import asyncio
                            loop = getattr(self, '_loop', None) or asyncio.get_event_loop()
                            connected = asyncio.run_coroutine_threadsafe(
                                bridge.wait_for_extension(email, timeout=15.0),
                                loop,
                            ).result(timeout=20)
                            if connected:
                                log.info(f"[AppController] ✅ Extension reconnected for {email}")
                            else:
                                log.warning(f"[AppController] Extension did not reconnect within 15s for {email}")
                        except Exception as e:
                            log.warning(f"[AppController] Wait for extension reconnect failed: {e}")
                else:
                    log.warning(f"[AppController] ⚠️ Extension CDP reinstall failed for {email}")
                
                self._push_extension_status()
                return result
            except Exception as e:
                log.error(f"[AppController] Extension CDP reinstall error for {email}: {e}")
                return False
        else:
            # Strategy 2b: CfT → restart browser (--load-extension reloads automatically)
            log.info(f"[AppController] CfT — restarting browser to reload extension for {email}...")
            result = self.restart_browser_for(email)
            # Wait for extension to reconnect via WebSocket
            if result and bridge:
                try:
                    import asyncio
                    loop = getattr(self, '_loop', None) or asyncio.get_event_loop()
                    asyncio.run_coroutine_threadsafe(
                        bridge.wait_for_extension(email, timeout=15.0),
                        loop,
                    ).result(timeout=20)
                except Exception:
                    pass
            self._push_extension_status()
            return result
    
    def ensure_all_extensions(self) -> dict:
        """Check and install/update extensions across ALL connected Branded Chrome profiles.
        
        Called on startup after all browsers reconnect, or from UI 'Fix All'.
        Thread-safe, can run in background thread.
        
        Returns:
            Dict mapping email -> result string (e.g. '✅', '⚠️ failed', '❌ error')
        """
        pc = self._profiles_controller
        if not pc or not hasattr(pc, '_debug_browsers'):
            return {}
        
        from core.extension_manager import install_if_needed
        from core.chrome_manager import is_branded_chrome
        from pathlib import Path
        
        _client_dir = Path(__file__).resolve().parent.parent
        _extension_dir = _client_dir / "extension"
        
        if not _extension_dir.exists() or not (_extension_dir / "manifest.json").exists():
            log.warning("[AppController] No extension directory found — skipping batch check")
            return {}
        
        results = {}
        # ★ Snapshot dict — install_if_needed() may trigger browser callbacks
        #   that modify _debug_browsers mid-iteration (→ RuntimeError)
        browser_snapshot = list(pc._debug_browsers.items())
        for email, entry in browser_snapshot:
            # ⚡ FIX: Read CDP port from in-memory entry FIRST (set by open_browser_for_debug),
            # fall back to PID file on disk only if entry doesn't have it.
            # Previously only read from PID file → "no CDP port" when file is stale/missing.
            port = entry.get("cdp_port")
            chrome_exe = ""
            
            if not port:
                # Fallback: read from PID file
                profile = pc.get_profile(email)
                if profile and profile.browser_profile_path:
                    from core.chrome_manager import _load_pid_file
                    pid_data = _load_pid_file(profile.browser_profile_path)
                    if pid_data:
                        port = pid_data.get("port")
                        chrome_exe = pid_data.get("chrome_exe", "")
            else:
                # Have port from entry — still need chrome_exe for branded check
                profile = pc.get_profile(email)
                if profile and profile.browser_profile_path:
                    from core.chrome_manager import _load_pid_file
                    pid_data = _load_pid_file(profile.browser_profile_path)
                    if pid_data:
                        chrome_exe = pid_data.get("chrome_exe", "")
            
            if not port:
                results[email] = "⚠️ no CDP port"
                continue
            
            if not is_branded_chrome(chrome_exe):
                results[email] = "⏭️ CfT (skip)"
                continue  # CfT uses --load-extension, skip
            
            # Fast path: if extension bridge already connected for this email,
            # the extension is provably working — skip CDP service_worker check
            # (MV3 service workers suspend quickly, causing false negatives)
            # BUT still check version to detect outdated extensions
            if (self._extension_bridge 
                    and self._extension_bridge.is_connected(email)):
                from core.extension_manager import get_local_extension_version, _get_installed_extension_version
                local_ver = get_local_extension_version()
                installed_ver = _get_installed_extension_version(port)
                if local_ver and installed_ver and installed_ver == local_ver:
                    # Confirmed same version — skip reinstall
                    results[email] = "✅ bridge connected"
                    log.info(f"[AppController] Extension v{installed_ver} connected via bridge for {email} — up-to-date")
                    continue
                elif local_ver and installed_ver and installed_ver != local_ver:
                    log.warning(f"[AppController] Extension connected but outdated: installed={installed_ver}, local={local_ver} — reinstalling...")
                    # Fall through to install_if_needed below
                else:
                    log.info(f"[AppController] Extension connected but version unknown (installed={installed_ver}, local={local_ver}) — checking...")
                    # Fall through to install_if_needed below
            
            try:
                ok = install_if_needed(port, str(_extension_dir))
                results[email] = "✅" if ok else "⚠️ failed"
            except Exception as e:
                results[email] = f"❌ {e}"
                log.error(f"[AppController] Extension batch install error for {email}: {e}")
        
        if results:
            log.info(f"[AppController] Extension batch check results: {results}")
        
        self._push_extension_status()
        return results
    
    def on_extension_hot_updated(self):
        """★ Post-update handler: reload extension on ALL running browsers.
        
        Called after auto_updater hot-replaces extension/ folder on disk.
        Runs in background thread to avoid blocking UI.
        
        Strategy per Chrome type:
        - Branded Chrome: CDP reinstall (uninstall old → install new from disk)
        - CfT: restart browser (--load-extension only loads at launch time)
        
        After reload, verifies installed version matches local version.
        """
        import threading
        
        def _reload_all():
            import time
            
            pc = self._profiles_controller
            if not pc or not hasattr(pc, '_debug_browsers'):
                log.info("[ExtHotUpdate] No running browsers — skip reload")
                return
            
            from core.chrome_manager import is_branded_chrome, _load_pid_file
            from pathlib import Path
            
            running_emails = list(pc._debug_browsers.keys())
            if not running_emails:
                log.info("[ExtHotUpdate] No running browsers — skip reload")
                return
            
            log.info(
                f"[ExtHotUpdate] Reloading extension on {len(running_emails)} "
                f"browser(s): {running_emails}"
            )
            
            results = {}
            for email in running_emails:
                try:
                    # Determine Chrome type
                    chrome_exe = ""
                    profile = pc.get_profile(email)
                    if profile and profile.browser_profile_path:
                        pid_data = _load_pid_file(profile.browser_profile_path)
                        if pid_data:
                            chrome_exe = pid_data.get("chrome_exe", "")
                    
                    if is_branded_chrome(chrome_exe):
                        # ★ Branded Chrome: reload via existing method
                        # (tries WebSocket hot-reload first, then CDP reinstall)
                        log.info(f"[ExtHotUpdate] {email}: Branded Chrome — reloading extension...")
                        ok = self.reload_extension_for(email)
                        if ok:
                            results[email] = "✅ reloaded"
                        else:
                            # Fallback: full ensure (catches version mismatch)
                            log.warning(f"[ExtHotUpdate] {email}: reload failed — trying ensure_all...")
                            ensure_result = self.ensure_all_extensions()
                            results[email] = ensure_result.get(email, "⚠️ ensure fallback")
                    else:
                        # ★ CfT: must restart browser (--load-extension only loads at launch)
                        log.info(f"[ExtHotUpdate] {email}: CfT — restarting browser for extension reload...")
                        ok = self.restart_browser_for(email)
                        if ok:
                            # Wait for extension to reconnect
                            bridge = getattr(self, '_extension_bridge', None)
                            if bridge:
                                try:
                                    import asyncio
                                    loop = getattr(self, '_loop', None)
                                    if loop:
                                        asyncio.run_coroutine_threadsafe(
                                            bridge.wait_for_extension(email, timeout=15.0),
                                            loop,
                                        ).result(timeout=20)
                                except Exception:
                                    pass
                            results[email] = "✅ restarted"
                        else:
                            results[email] = "❌ restart failed"
                    
                    # ★ Fix 4: Version verify after reload
                    entry = pc._debug_browsers.get(email, {})
                    cdp_port = entry.get("cdp_port")
                    if cdp_port:
                        from core.extension_manager import (
                            get_local_extension_version,
                            _get_installed_version_fast,
                            install_if_needed,
                        )
                        local_ver = get_local_extension_version()
                        installed_ver = _get_installed_version_fast(cdp_port)
                        if local_ver and installed_ver and installed_ver != local_ver:
                            log.warning(
                                f"[ExtHotUpdate] {email}: version mismatch after reload "
                                f"(installed={installed_ver}, local={local_ver}) — reinstalling"
                            )
                            _client_dir = Path(__file__).resolve().parent.parent
                            _extension_dir = _client_dir / "extension"
                            install_if_needed(cdp_port, str(_extension_dir))
                            results[email] = "🔄 reinstalled (version mismatch)"
                        elif local_ver and installed_ver:
                            log.info(f"[ExtHotUpdate] {email}: ✅ verified v{installed_ver}")
                
                except Exception as e:
                    results[email] = f"❌ {e}"
                    log.error(f"[ExtHotUpdate] {email}: error — {e}")
            
            log.info(f"[ExtHotUpdate] Results: {results}")
            self._push_extension_status()
        
        threading.Thread(
            target=_reload_all, daemon=True, name="ext-hot-update-reload"
        ).start()
    
    # NOTE: reload_extension_for() defined above (line ~799) — Chrome-type-aware
    # version with WebSocket hot-reload + Branded/CfT fallback strategies.
    # A simpler duplicate was here previously and has been removed.
    
    def hot_reload_app(self):
        """Restart the entire Python process.
        
        Gracefully stops engine and event manager, then spawns
        a new `python main.py` process and exits the current one.
        Chrome browsers persist (PID files) and will be reconnected.
        """
        import subprocess as _sp
        
        log.info("[AppController] Hot reload: stopping services...")
        
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
                    "slots": acc.max_workers,
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
        - Disable: stops browser + extension for this account
        - Enable: relaunches browser + reconnects extension
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
        
        # ★ Browser lifecycle: close on disable, relaunch on enable
        import threading
        if enabled:
            # Check if extension/browser is already running
            ext_connected = (
                self._extension_bridge and
                self._extension_bridge.is_connected(email)
            )
            if not ext_connected:
                log.info(f"[AppController] Re-enable {email}: launching browser...")
                threading.Thread(
                    target=self._relaunch_account_browser_bg,
                    args=(email,),
                    daemon=True,
                    name=f"relaunch-{email[:8]}",
                ).start()
        else:
            log.info(f"[AppController] Disabling {email}: closing browser...")
            threading.Thread(
                target=self._close_account_browser_bg,
                args=(email,),
                daemon=True,
                name=f"close-{email[:8]}",
            ).start()
        
        log.info(f"[AppController] Account {email} {'enabled' if enabled else 'disabled'}")
    
    def _close_account_browser_bg(self, email: str):
        """Background: close browser + disconnect extension for a disabled account."""
        try:
            pc = self._profiles_controller
            if pc:
                pc.kill_debug_browser(email)
                log.info(f"[AppController] ✅ Browser closed for disabled account {email}")
        except Exception as e:
            log.warning(f"[AppController] ⚠️ Failed to close browser for {email}: {e}")
    
    def _relaunch_account_browser_bg(self, email: str):
        """Background: relaunch browser for a re-enabled account.
        
        Works even if account is not in runtime _multi_account.
        Uses ProfilesController.open_browser_for_debug() directly.
        """
        try:
            pc = self._profiles_controller
            if not pc:
                log.error(f"[Relaunch] {email}: no ProfilesController")
                return
            
            # Check if browser is already running
            state = pc.get_debug_browser_state(email)
            if state in ("visible", "hidden"):
                log.info(f"[Relaunch] {email}: browser already running ({state})")
                return
            
            # Launch browser (hidden by default)
            from config.settings import get_settings
            _s = get_settings()
            headless = getattr(_s, 'smart_hide_enabled', True) or getattr(_s, 'hide_all_browsers', False)
            
            log.info(f"[Relaunch] {email}: launching browser (headless={headless})...")
            pc.open_browser_for_debug(
                email,
                on_state_change=self._on_debug_browser_state_change,
            )
            log.info(f"[Relaunch] {email}: ✅ browser launched")
            
            # If runtime account exists, trigger full reconnect
            acc = self._multi_account.get_account(email)
            if acc:
                self._reconnect_account_bg(email)
                
        except Exception as e:
            log.error(f"[Relaunch] {email}: ❌ failed — {e}")
    
    def _reconnect_account_bg(self, email: str):
        """Background: reconnect browser + extension for a re-enabled account."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._reconnect_account_async(email))
        except Exception as e:
            log.error(f"[Reconnect] {email}: failed — {e}")
        finally:
            loop.close()
    
    async def _reconnect_account_async(self, email: str):
        """Async reconnect: ensure browser + extension for account."""
        acc = self._multi_account.get_account(email)
        if not acc:
            return
        
        # Step 1: Ensure browser is running
        if not (acc._browser_session and acc._browser_session.is_ready):
            log.info(f"[Reconnect] {email}: launching browser...")
            try:
                if self._profiles_controller:
                    acc.set_profiles_controller(self._profiles_controller)
                from config.settings import get_settings
                _s = get_settings()
                _headless = getattr(_s, 'smart_hide_enabled', True) or getattr(_s, 'hide_all_browsers', False)
                await acc.ensure_browser(headless=_headless)
                log.info(f"[Reconnect] {email}: ✅ browser launched")
            except Exception as e:
                log.error(f"[Reconnect] {email}: browser launch failed — {e}")
                return
        
        # Step 2: Wait for extension connection
        if self._extension_bridge:
            if not self._extension_bridge.is_connected(email):
                log.info(f"[Reconnect] {email}: waiting for extension...")
                connected = await self._extension_bridge.wait_for_extension(
                    email, timeout=15.0
                )
                if connected:
                    log.info(f"[Reconnect] {email}: ✅ extension reconnected")
                else:
                    log.warning(f"[Reconnect] {email}: ⚠️ extension timeout (15s)")
            
            # Step 3: Populate session from bridge cache
            cached = self._extension_bridge.get_cached_headers(
                email, max_age_seconds=0
            )
            if cached:
                acc._session.update_browser_headers(
                    browser_validation=cached.get('x-browser-validation', ''),
                    client_data=cached.get('x-client-data', ''),
                    browser_channel=cached.get('x-browser-channel', 'stable'),
                    browser_copyright=cached.get('x-browser-copyright', ''),
                    browser_year=cached.get('x-browser-year', ''),
                )
                log.info(f"[Reconnect] {email}: ✅ headers populated")
        
        log.info(f"[Reconnect] {email}: ✅ account fully reconnected")
    
    def set_account_max_workers(self, email: str, value: int):
        """Set max concurrent workers for an account.
        
        Called from Settings UI when user changes the workers spinner.
        """
        acc = self._multi_account.get_account(email)
        if acc:
            acc.set_max_workers(value)
        
        log.info(f"[AppController] Account {email} max_workers → {value}")
    
    # Backward compat alias
    set_account_max_slots = set_account_max_workers
    
    def set_account_max_workers_lp(self, email: str, value: int):
        """Set max LP concurrent workers for an account.
        
        Called from Settings UI when user changes the LP workers spinner.
        """
        acc = self._multi_account.get_account(email)
        if acc:
            acc.session.max_workers_lp = value
        
        log.info(f"[AppController] Account {email} max_workers_lp → {value}")
    
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
                
                # Session status — check enabled state FIRST
                if not runtime_acc.is_enabled:
                    session_status = "⚫ Disabled"
                elif runtime_acc.is_ready:
                    session_status = "🟢 Ready"
                elif ext_connected:
                    session_status = "🟢 Session via Extension"
                else:
                    session_status = "🟡 Waiting Extension"
                
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
                slots_display = f"0/{profile.max_workers}"
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
        """Push session data to DevConsole (thread-safe).
        
        Round 5 Fix E: Don't call get_session_data() on background thread.
        get_session_data() does SQLite I/O + file reads — must run on GUI thread.
        """
        if not hasattr(self, '_dev_console') or not self._dev_console:
            return
        
        from PySide6.QtCore import QMetaObject, Qt, QThread
        
        if QThread.currentThread() == self._dev_console.thread():
            data = self.get_session_data()
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
        
        # Bug 14: Skip extension status push when DevConsole is hidden
        try:
            if self._dev_console.isVisible():
                self._push_extension_status()
        except Exception:
            pass
        # Bug 6 fix: throttle session data push from every 5s to every 15s
        # get_session_data() copies SQLite cookies per account — expensive I/O
        try:
            if not hasattr(self, '_session_push_tick'):
                self._session_push_tick = 0
            self._session_push_tick += 1
            if self._session_push_tick >= 3:  # 3 × 5s = 15s
                self._session_push_tick = 0
                self._push_session_data()
        except Exception:
            pass
        
        # Push Engine Dashboard (aggregated monitoring data)
        # Bug 14: Throttle to every 10s (2 ticks) — pulls from 5+ subsystems
        try:
            if not hasattr(self, '_dashboard_push_tick'):
                self._dashboard_push_tick = 0
            self._dashboard_push_tick += 1
            if self._dashboard_push_tick >= 2:  # 2 × 5s = 10s
                self._dashboard_push_tick = 0
                if self._dev_console.isVisible():
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
        
        # Subsystem stats via Engine facade (Cluster #3 fix)
        try:
            if hasattr(self, '_engine') and self._engine:
                dashboard.update(self._engine.get_dashboard_stats())
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
        # Load persisted defaults from AppSettings (C2 fix)
        from config.settings import get_settings as _gs
        _s = _gs()
        settings = {
            "adaptive_burst_enabled": getattr(_s, 'adaptive_burst_enabled', True),
            "burst_min_delay": getattr(_s, 'burst_min_delay', 2.0),
            "burst_max_delay": getattr(_s, 'burst_max_delay', 15.0),
            "recaptcha_pool_enabled": getattr(_s, 'recaptcha_pool_enabled', True),
            "pool_size": getattr(_s, 'recaptcha_pool_size', 2),
            "watchdog_timeout_min": getattr(_s, 'watchdog_timeout_min', 10),
            "journal_save_interval_sec": getattr(_s, 'journal_save_interval_sec', 30),
            "workload_priority": getattr(_s, 'workload_priority', '720p_priority'),
        }
        
        # Override with live runtime values if engine is running
        try:
            if hasattr(self, '_engine') and self._engine:
                settings.update(self._engine.get_pipeline_settings())
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
            # Delegate engine-owned settings via facade (Cluster #3 fix)
            if self._engine and self._engine.update_pipeline_setting(key, value):
                pass  # Handled by engine
            # Non-engine settings stay here (AppController-owned)
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
    
    def _start_prune_timer(self):
        """Start periodic task pruning timer (every 10 min → free RAM)."""
        if self._prune_timer is not None:
            return  # Already running
        
        from PySide6.QtCore import QTimer
        self._prune_timer = QTimer()
        self._prune_timer.timeout.connect(self._do_prune)
        self._prune_timer.start(10 * 60 * 1000)  # Every 10 minutes
    
    def _stop_prune_timer(self):
        """Stop periodic task pruning timer."""
        if self._prune_timer:
            self._prune_timer.stop()
            self._prune_timer.deleteLater()
            self._prune_timer = None
    
    def _do_prune(self):
        """Prune completed tasks from dispatcher to free RAM."""
        try:
            from config.settings import get_settings
            settings = get_settings()
            
            # Time-based prune: only if prune_age_minutes > 0
            age = getattr(settings, 'prune_age_minutes', 0)
            if age > 0:
                self._dispatcher.prune_completed_tasks(max_age_minutes=age)
            
            # Count-based cap: if auto_clear_tasks_max > 0, enforce hard limit
            cap = getattr(settings, 'auto_clear_tasks_max', 0)
            if cap > 0:
                self._dispatcher.enforce_task_cap(cap)
        except Exception as e:
            log.debug(f"[AppController] Prune error: {e}")
    
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
        if not self._permissions.check_limit("max_accounts", len(self._multi_account._accounts)):
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
        """Remove an account.
        
        Hot-remove flow:
        1. Stop engine workers (foremen + supervisor) for this email
        2. Remove from runtime pool (MultiAccountManager)
        3. Unregister from session/refresh monitors
        """
        # Step 1: Stop engine workers BEFORE removing account
        if hasattr(self, '_engine') and self._engine and self._engine._running:
            try:
                self._engine.stop_account_workers(email)
            except Exception as e:
                log.warning(f"[AppController] stop_account_workers error: {e}")
        
        # Step 2: Remove from runtime pool
        future = self._run_async(self._multi_account.remove_account(email))
        result = False
        if future:
            try:
                result = future.result(timeout=10.0)
            except Exception:
                pass
        
        # Step 3: Unregister from monitors
        self._session_monitor.unregister_session(email)
        self._refresh_manager.unregister_session(email)
        
        # Step 4: Cleanup per-email state to prevent unbounded growth
        try:
            self._extension_bridge.cleanup_account(email)
        except Exception:
            pass
        try:
            from core.account_logger import cleanup_single_account_handler
            cleanup_single_account_handler(email)
        except Exception:
            pass
        
        return result
    
    # toggle_account defined at L1541 — single source of truth
    # (saves profile + updates runtime AccountManager)
    
    def get_accounts(self) -> List[Dict]:
        """Get list of accounts with status."""
        status = self._multi_account.get_status_summary()
        return status.get('accounts', [])
    
    @property
    def profiles_controller(self):
        """Read-only access to ProfilesController (owned by AppController)."""
        return self._profiles_controller
    
    def set_profiles_controller(self, profiles_controller=None):
        """Set or replace the ProfilesController reference.
        
        Kept for backward compatibility. If called without argument,
        uses the internal instance. Triggers auto-launch of headless
        browsers for all profiles.
        """
        if profiles_controller is not None:
            self._profiles_controller = profiles_controller
        # Forward to engine so it can auto re-login on auth failures
        if self._engine:
            self._engine._profiles_controller = self._profiles_controller
        
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
        
        # G6: License gate — cap number of enabled accounts by max_accounts
        max_accounts = self._permissions.limits.max_accounts
        if max_accounts > 0:
            enabled_profiles = [p for p in profiles if p.get('is_enabled', True)]
            if len(enabled_profiles) > max_accounts:
                log.info(
                    f"[G6] Account limit: {len(enabled_profiles)} enabled, "
                    f"max={max_accounts} — capping"
                )
                # Keep first N enabled, disable rest (in-memory only)
                for p in enabled_profiles[max_accounts:]:
                    p['is_enabled'] = False
        
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
            elif is_enabled:
                # Profile is enabled but not in runtime pool — add it
                # Note: is_ready is NOT required here. The account needs to be
                # in the runtime pool so the engine/extension bridge can make it ready.
                # preflight_check() validates actual readiness (extension, token, etc.).
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
                    session.max_workers = getattr(profile_obj, 'max_workers', 20)
                    session.max_workers_lp = getattr(profile_obj, 'max_workers_lp', 8)
                    
                    # Add to runtime via async
                    future = self._run_async(
                        self._multi_account.add_account(session)
                    )
                    if future:
                        try:
                            future.result(timeout=15.0)
                            log.info(f"Synced profile → runtime: {email}")
                            
                            # Inject bridge IMMEDIATELY after account is created
                            acc_mgr = self._multi_account.get_account(email)
                            if acc_mgr:
                                acc_mgr._parent_manager = self._multi_account
                                if hasattr(self, '_extension_bridge') and self._extension_bridge:
                                    acc_mgr.extension_bridge = self._extension_bridge
                                    # FIX: Bridge may already have cached headers from
                                    # earlier connections. Populate session immediately
                                    # to prevent stale x-client-data (8 chars from disk).
                                    cached = self._extension_bridge.get_cached_headers(email, max_age_seconds=0)
                                    if cached:
                                        acc_mgr._session.update_browser_headers(
                                            browser_validation=cached.get('x-browser-validation', ''),
                                            client_data=cached.get('x-client-data', ''),
                                            browser_channel=cached.get('x-browser-channel', 'stable'),
                                            browser_copyright=cached.get('x-browser-copyright', ''),
                                            browser_year=cached.get('x-browser-year', ''),
                                        )
                                        xcd_len = len(cached.get('x-client-data', ''))
                                        if xcd_len >= 20:
                                            log.info(f"[sync] {email}: populated session from bridge cache (x-client-data={xcd_len} chars)")
                                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                                    acc_mgr.set_profiles_controller(self._profiles_controller)
                            
                            # Hot-reload: if engine is running, spawn workers immediately
                            if self._engine and self._engine.is_running:
                                if acc_mgr:
                                    self._engine.add_account_hot(acc_mgr)
                                    
                        except Exception as e:
                            if isinstance(e, TimeoutError):
                                log.debug(f"Sync {email}: timeout (browser not ready yet)")
                            else:
                                log.warning(f"Failed to sync {email}: {type(e).__name__}: {e}")
                            # Even on timeout, the account may have been added —
                            # inject bridge defensively so it's ready when needed
                            acc_mgr = self._multi_account.get_account(email)
                            if acc_mgr:
                                acc_mgr._parent_manager = self._multi_account
                                if hasattr(self, '_extension_bridge') and self._extension_bridge:
                                    acc_mgr.extension_bridge = self._extension_bridge
                                    # Populate session from bridge cache (same fix as success path)
                                    cached = self._extension_bridge.get_cached_headers(email, max_age_seconds=0)
                                    if cached and len(cached.get('x-client-data', '')) >= 20:
                                        acc_mgr._session.update_browser_headers(
                                            browser_validation=cached.get('x-browser-validation', ''),
                                            client_data=cached.get('x-client-data', ''),
                                            browser_channel=cached.get('x-browser-channel', 'stable'),
                                            browser_copyright=cached.get('x-browser-copyright', ''),
                                            browser_year=cached.get('x-browser-year', ''),
                                        )
                                if hasattr(self, '_profiles_controller') and self._profiles_controller:
                                    acc_mgr.set_profiles_controller(self._profiles_controller)
                            
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
                        # Cleanup per-email state
                        try:
                            self._extension_bridge.cleanup_account(acc.email)
                        except Exception:
                            pass
                        try:
                            from core.account_logger import cleanup_single_account_handler
                            cleanup_single_account_handler(acc.email)
                        except Exception:
                            pass
                    except Exception:
                        pass
        
        log.info(
            f"Profile sync complete: {self._multi_account.account_count} accounts, "
            f"{len(self._multi_account.ready_accounts)} ready"
        )
        
        # Ensure ExtensionBridge + ProfilesController + parent ref are injected on ALL accounts
        # (covers newly-created accounts from sync AND existing ones)
        # Also populate session headers from bridge cache to prevent stale x-client-data
        for acc in self._multi_account._accounts:
            acc._parent_manager = self._multi_account  # for bridge auto-recovery
            if hasattr(self, '_extension_bridge') and self._extension_bridge:
                acc.extension_bridge = self._extension_bridge
                # FIX: ensure session has latest bridge headers
                cached = self._extension_bridge.get_cached_headers(acc.email, max_age_seconds=0)
                if cached:
                    current_xcd = acc._session.client_data or ''
                    bridge_xcd = cached.get('x-client-data', '')
                    if len(bridge_xcd) > len(current_xcd):
                        acc._session.update_browser_headers(
                            browser_validation=cached.get('x-browser-validation', acc._session.browser_validation or ''),
                            client_data=bridge_xcd,
                            browser_channel=cached.get('x-browser-channel', acc._session.browser_channel or 'stable'),
                            browser_copyright=cached.get('x-browser-copyright', acc._session.browser_copyright or ''),
                            browser_year=cached.get('x-browser-year', acc._session.browser_year or ''),
                        )
                        log.info(f"[sync] {acc.email}: bridge cache → session x-client-data ({len(current_xcd)}→{len(bridge_xcd)} chars)")
            if hasattr(self, '_profiles_controller') and self._profiles_controller:
                acc.set_profiles_controller(self._profiles_controller)
    
    def set_account_max_workers(self, email: str, max_workers: int):
        """Set max_workers on runtime AccountManager for a given email.
        
        Called by UI when user changes Workers SpinBox.
        """
        acc = self._multi_account.get_account(email)
        if acc:
            acc.set_max_workers(max_workers)
            logging.getLogger(__name__).info(
                f"Runtime max_workers for {email} → {max_workers}"
            )
    
    # Backward compat alias
    set_account_max_slots = set_account_max_workers
    
    def set_account_max_workers_lp(self, email: str, value: int):
        """Set max LP concurrent workers for an account.
        
        Called from Settings UI when user changes the LP workers spinner.
        """
        acc = self._multi_account.get_account(email)
        if acc:
            acc._session.max_workers_lp = max(0, value)
            logging.getLogger(__name__).info(
                f"Runtime max_workers_lp for {email} → {value}"
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
            return "GEM_PIX_2"  # Sidebar default: 🔥 Nano Banana Pro
        return "veo_3_1_t2v_fast_ultra"
    
    def submit_prompts(
        self,
        prompts: List[str],
        workflow: WorkflowType,
        images: Optional[List[str]] = None,
        per_prompt_images: Optional[Dict[int, List[str]]] = None,  # Bug 2: per-prompt image mapping
        per_prompt_workflows: Optional[Dict[int, str]] = None,  # Per-task workflow override (e.g., I2V/R2V per scene)
        settings: Optional[Dict] = None,
        continuation_map: Optional[Dict[int, int]] = None,  # index -> parent_index
        per_prompt_durations: Optional[Dict[int, int]] = None,  # index -> duration_seconds (from JSON scenes)
    ) -> str:
        """Submit prompts for processing.
        
        Args:
            images: Flat list of image URIs (shared by ALL tasks — legacy)
            per_prompt_images: Dict mapping prompt index → list of image URIs for that task.
                              Takes priority over `images` when provided.
        
        Returns group_id.
        """
        # G0: Block if license expired / invalid — INLINE CHECK (not just flag)
        if not self._check_license_gate():
            log.warning("[License] Generation blocked — license expired or invalid")
            self._notify_status("License expired — please activate a license key")
            return ""
        
        # G1: Warn if no account has valid x-client-data (>= 40 chars)
        # Tasks are ALWAYS created and queued — engine checks x-client-data at execution time.
        # This ensures Add-to-Queue always works and displays tasks in Queue tab.
        has_valid_xcd = False
        for acc in list(self._multi_account._accounts):
            # Path 1: Bridge cache with 120s expiry (detects stale data after idle)
            bridge = getattr(acc, 'extension_bridge', None)
            if bridge:
                cached = bridge.get_cached_headers(acc.email, max_age_seconds=120)
                if cached:
                    xcd = (cached.get('x-client-data', '') or '')
                    if len(xcd) >= 40:
                        has_valid_xcd = True
                        break
            # Path 2: Session memory fallback (may be stale but non-zero = extension was connected)
            xcd = getattr(acc._session, 'client_data', '') or ''
            if len(xcd) >= 40:
                has_valid_xcd = True
                break
        if not has_valid_xcd:
            log.warning("[Submit] x-client-data not ready — tasks queued but may fail until extension provides fresh headers")
            self._notify_status(
                "⚠️ x-client-data not ready — tasks queued, waiting for browser extension."
            )
        
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
        if model_display and not model_display.startswith("veo_") and model_display not in ("NARWHAL", "GEM_PIX_2", "IMAGEN_3_5"):
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
                workflow_type=(per_prompt_workflows or {}).get(i, workflow.name),
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                model=model,
                output_count=output_count,
                duration_seconds=(per_prompt_durations or {}).get(i, (settings or {}).get("duration", 8)),
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
                from urllib.parse import unquote as _unquote
                local = []
                remote = []
                for u in task.image_uris:
                    # Convert file:/// URI to local path
                    if u.startswith('file:///'):
                        u = _unquote(u[8:])
                    if _P(u).exists():
                        local.append(u)
                    else:
                        remote.append(u)
                if local:
                    task.image_paths = local
                    task.image_uris = remote  # Only keep actual remote URIs/mediaIds
            
            # === Tag resolution: [tag] → local image path ===
            # Only for image-based workflows (I2V, R2V, I2I, F2V).
            # T2V NEVER uses Image Library tags — it only receives images
            # from continuation (parent task frame extraction).
            # Bug 1 fix: Also check image_paths — they may have been populated by
            # _resolve_tags_to_paths() in add_i2v_batch() and then moved from
            # image_uris to image_paths by the local/remote split above (line 1031-1037)
            if (not task.image_uris and not task.image_paths
                    and task.workflow_type not in ("T2V", "T2I")):
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
                            log.info(f"  [TAG] Resolved {len(resolved_paths)} image(s) for {task.workflow_type} task {i}")
                    except ImportError:
                        log.warning("  ImageLibrary not available for tag resolution")
            # === End tag resolution ===
            
            # === Workflow auto-switch ===
            # Per-task: adjust workflow_type + model based on actual conditions
            has_images = bool(task.image_uris or task.image_paths)
            has_continuation = task.parent_task_id is not None
            img_count = len(task.image_uris or []) + len(task.image_paths or [])
            
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
                # F12 verified: T2I/I2I both accept GEM_PIX_2, NARWHAL, IMAGEN_3_5
                # — no model change needed on downgrade
                log.info(f"  [AUTO] I2I → T2I (no images, task {i})")
            
            # Upgrade: T2V/R2V → I2V (continuation needs a start frame)
            elif has_continuation and task.workflow_type in ("T2V", "R2V"):
                old_wf = task.workflow_type
                task.workflow_type = "I2V"
                task.model = resolve_model_key(model_display, WorkflowType.I2V, raw_ar, False)
                log.info(f"  [AUTO] {old_wf} → I2V (continuation, task {i})")
            # === End auto-switch ===
            
            # ★ CRITICAL: Dual-frame (_fl_) model guard.
            # frame_mode='both' selects _fl_ model (needs 2 images: start+end).
            # If only 1 image provided → endImage=null → VEO3 crash:
            #   visual_description.is_object() VISUAL_DESCRIPTION is not a JSON object
            if (has_images and img_count < 2
                    and task.workflow_type in ("I2V", "F2V")
                    and "_fl_" in (task.model or "")):
                task.workflow_type = "I2V"
                task.model = resolve_model_key(model_display, WorkflowType.I2V, raw_ar, False)
                log.warning(
                    f"  [AUTO] _fl_ → single-frame I2V (only {img_count} image, task {i}) — "
                    f"dual-frame requires start+end images"
                )
            
            # === Image workflow output_count ===
            # T2I/I2I: generate_image() handles 1-request-per-image loop internally.
            # output_count controls how many images to generate (1-4, from UI sidebar).
            # Do NOT force output_count=1 — it would override user's "4 Images" setting.
            
            tasks.append(task)
        
        # === Continuation constraint: force output_count=1 for chain tasks only ===
        # Only tasks IN a continuation chain must produce exactly 1 video
        # (last frame → next prompt's start). Other tasks in the same group
        # keep the user's configured output_count.
        parent_ids = {t.parent_task_id for t in tasks if t.parent_task_id}
        cont_forced = 0
        for t in tasks:
            # Force output_count=1 if: (a) task IS a continuation, or (b) task is a parent of one
            if t.parent_task_id is not None or t.id in parent_ids:
                t.output_count = 1
                cont_forced += 1
        if cont_forced > 0:
            log.info(
                f"  [CONT] Continuation detected → output_count=1 forced for "
                f"{cont_forced}/{len(tasks)} chain tasks (others keep user setting)"
            )
        
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
        log.info(f"  output_count: {output_count} ({cont_forced} chain tasks forced to 1)")
        log.info(f"  tasks      : {len(tasks)}")
        for t in tasks:
            cont = f" (cont→{t.parent_task_id})" if t.parent_task_id else ""
            log.info(f"    [{t.id}] {t.prompt[:60]}...{cont}" if len(t.prompt) > 60 else f"    [{t.id}] {t.prompt}{cont}")
        log.info(f"{'='*60}")
        # === END DEBUG ===
        
        # Push JSON preview to DevConsole if available (thread-safe)
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
                from PySide6.QtCore import QMetaObject, Qt, QThread
                # Stash data for the safe slot to pick up
                self._pending_json_preview = preview
                if QThread.currentThread() == self._dev_console.thread():
                    self._dev_console.update_json_preview(preview)
                else:
                    QMetaObject.invokeMethod(
                        self._dev_console, "update_json_preview_safe",
                        Qt.ConnectionType.QueuedConnection
                    )
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
        # Extract continuation chain + per-prompt durations
        continuation_map = {}
        per_prompt_durations = {}
        
        for i, p in enumerate(prompts):
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                continuation_map[i] = p.continuation_from - 1
            if hasattr(p, 'duration') and p.duration is not None:
                per_prompt_durations[i] = p.duration
        
        return self.submit_prompts(
            prompts=[p.text if hasattr(p, 'text') else str(p) for p in prompts],
            workflow=WorkflowType.T2V,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None,
            per_prompt_durations=per_prompt_durations if per_prompt_durations else None,
        )
    
    def _resolve_tags_to_paths(self, tags: List[str]) -> List[str]:
        """Resolve image tag names to file paths via ImageLibrary.
        
        Tags that cannot be resolved are skipped.
        Handles file:/// URIs by converting to local paths.
        """
        if not tags:
            return []
        try:
            from services.image_library import get_image_library
            from pathlib import Path as _P
            from urllib.parse import unquote
            library = get_image_library()
            paths = []
            for tag in tags:
                # Strip file:/// URI prefix → convert to local path
                if tag.startswith('file:///'):
                    local_path = unquote(tag[8:])  # Remove 'file:///' and URL-decode
                    if _P(local_path).exists():
                        paths.append(local_path)
                        log.info(f"  [TAG→PATH] [file:///...] → {local_path}")
                        continue
                    else:
                        log.warning(f"  [TAG→PATH] file:/// URI not found on disk: {local_path}")
                        continue
                # If it already looks like a file path, validate it exists
                if '/' in tag or '\\' in tag or '.' in tag and len(tag) > 5:
                    clean = unquote(tag)
                    if _P(clean).exists():
                        paths.append(clean)
                        continue
                    # Path doesn't exist — fall through to library resolution
                    log.debug(f"  [TAG→PATH] Path-like tag not found on disk: {clean}")
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
            resolved = []
            # 1. Try image_tags → library resolution (from [tag] in prompt)
            if hasattr(p, 'image_tags') and p.image_tags:
                resolved = self._resolve_tags_to_paths(list(p.image_tags))
            # 2. Fallback: image_path from drag-drop slot (synced by get_prompts())
            if not resolved and hasattr(p, 'image_path') and p.image_path:
                from pathlib import Path as _P
                if _P(p.image_path).exists():
                    resolved = [p.image_path]
                    log.info(f"  [I2V] Row {i}: using drag-drop image_path → {p.image_path}")
            # 3. Fallback: start_frame / end_frame (I2V-specific fields)
            if not resolved:
                frames = []
                for attr in ('start_frame', 'end_frame'):
                    val = getattr(p, attr, None)
                    if val:
                        from pathlib import Path as _P
                        if _P(val).exists():
                            frames.append(val)
                        else:
                            # start_frame may be a tag name, try library
                            tag_resolved = self._resolve_tags_to_paths([val])
                            frames.extend(tag_resolved)
                if frames:
                    resolved = frames
                    log.info(f"  [I2V] Row {i}: using start/end frames → {frames}")
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
        per_prompt_images = {}
        prompt_texts = []
        continuation_map = {}
        for i, p in enumerate(prompts):
            prompt_texts.append(p.text if hasattr(p, 'text') else str(p))
            resolved = []
            # 1. Try image_tags → library resolution (from [tag] in prompt)
            if hasattr(p, 'image_tags') and p.image_tags:
                resolved = self._resolve_tags_to_paths(list(p.image_tags[:3]))  # Max 3
            # 2. Fallback: image_path from drag-drop slot (synced by get_prompts())
            if not resolved and hasattr(p, 'image_path') and p.image_path:
                from pathlib import Path as _P
                if _P(p.image_path).exists():
                    resolved = [p.image_path]
                    log.info(f"  [R2V] Row {i}: using drag-drop image_path → {p.image_path}")
            if resolved:
                per_prompt_images[i] = resolved
            if hasattr(p, 'continuation_from') and p.continuation_from is not None:
                continuation_map[i] = p.continuation_from - 1
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.R2V,
            per_prompt_images=per_prompt_images if per_prompt_images else None,
            settings=settings,
            continuation_map=continuation_map if continuation_map else None
        )
    
    def get_group_status(self, group_id: str) -> Optional[dict]:
        """Get completion status of a task group for pipeline progress tracking.
        
        Returns dict with total/completed/failed counts and completed task details
        (prompt_index, best_file, thumbnail) — used by Tab Project Builder to
        populate image_path/video_path back into pipeline state.
        
        Returns None if group_id not found.
        """
        from core.dispatcher import TaskState
        groups = self._dispatcher.get_task_groups()
        group = groups.get(group_id)
        if not group:
            return None
        tasks = group.tasks
        completed = [t for t in tasks if t.state == TaskState.COMPLETED]
        failed = [t for t in tasks if t.state == TaskState.FAILED]
        return {
            "group_id": group_id,
            "total": len(tasks),
            "completed": len(completed),
            "failed": len(failed),
            "is_done": len(completed) + len(failed) >= len(tasks),
            "completed_tasks": [
                {
                    "task_id": t.id,
                    "prompt_index": t.prompt_index,
                    "best_file": t.video_outputs[0].best_file if t.video_outputs else "",
                    "thumbnail": t.video_outputs[0].thumbnail_path if t.video_outputs else "",
                }
                for t in completed
            ],
        }
    
    def add_t2i_batch(self, prompts: List, settings: Dict) -> str:
        """Add Text-to-Image batch to queue.
        
        Handles reference_images from pipeline settings:
        - If reference_images provided → per_prompt_images → I2I workflow
        - Otherwise → T2I workflow (text-only)
        
        Args:
            prompts: List of PromptRow objects or plain strings
            settings: Sidebar settings dict (may include 'reference_images')
        """
        prompt_texts = [p.text if hasattr(p, 'text') else str(p) for p in prompts]
        
        # Check for per-prompt images (from pipeline Stage 5 per-scene char matching)
        per_prompt_images_map = settings.pop("per_prompt_images", None) if settings else None
        reference_images = settings.pop("reference_images", None) if settings else None
        per_prompt_images = None
        target_workflow = WorkflowType.T2I
        
        if per_prompt_images_map and isinstance(per_prompt_images_map, dict):
            # Per-scene character images — each scene gets only its matched characters
            resolved_map = {}
            for idx, imgs in per_prompt_images_map.items():
                resolved = self._resolve_tags_to_paths(imgs)
                if resolved:
                    resolved_map[int(idx)] = resolved
            if resolved_map:
                per_prompt_images = resolved_map
                target_workflow = WorkflowType.I2I
                log.info(
                    f"  [T2I→I2I] Per-scene char refs: "
                    f"{len(resolved_map)}/{len(prompt_texts)} scenes with images"
                )
        elif reference_images and isinstance(reference_images, list):
            # Flat list → apply same reference images to ALL prompts (character ref → I2I)
            resolved = self._resolve_tags_to_paths(reference_images)
            if resolved:
                per_prompt_images = {i: resolved for i in range(len(prompt_texts))}
                target_workflow = WorkflowType.I2I
                log.info(
                    f"  [T2I→I2I] {len(resolved)} reference image(s) → "
                    f"applied to {len(prompt_texts)} prompts"
                )
        
        # Also check per-prompt image_tags (from PromptRow objects)
        if not per_prompt_images:
            per_prompt_imgs = {}
            for i, p in enumerate(prompts):
                resolved = []
                if hasattr(p, 'image_tags') and p.image_tags:
                    resolved = self._resolve_tags_to_paths(list(p.image_tags))
                if not resolved and hasattr(p, 'image_path') and p.image_path:
                    from pathlib import Path as _P
                    if _P(p.image_path).exists():
                        resolved = [p.image_path]
                if resolved:
                    per_prompt_imgs[i] = resolved
            if per_prompt_imgs:
                per_prompt_images = per_prompt_imgs
                target_workflow = WorkflowType.I2I
                log.info(f"  [T2I→I2I] Per-prompt images for {len(per_prompt_imgs)} prompts")
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=target_workflow,
            per_prompt_images=per_prompt_images,
            settings=settings,
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
            resolved = []
            if hasattr(p, 'image_tags') and p.image_tags:
                resolved = self._resolve_tags_to_paths(list(p.image_tags))
            # Fallback: image_path from drag-drop slot
            if not resolved and hasattr(p, 'image_path') and p.image_path:
                from pathlib import Path as _P
                if _P(p.image_path).exists():
                    resolved = [p.image_path]
                    log.info(f"  [I2I] using drag-drop image_path → {p.image_path}")
            images.extend(resolved)
        
        return self.submit_prompts(
            prompts=prompt_texts,
            workflow=WorkflowType.I2I,
            images=images if images else None,
            settings=settings
        )
    
    # === TASK ACTIONS (called by context menu) ===
    
    def clone_task(self, task_id: str) -> Optional[str]:
        """Clone a task — delegates to dispatcher."""
        new_id = self._dispatcher.clone_task(task_id)
        if new_id:
            self.state.queue_count += 1
            self._notify_queue_updated()
        return new_id
    
    def export_task_config(self, task_id: str) -> Optional[dict]:
        """Export task config — delegates to dispatcher."""
        return self._dispatcher.export_task_config(task_id)
    
    def fork_continuation(self, task_id: str, video_index: int, new_prompt: str) -> Optional[str]:
        """Fork continuation — create task using completed task's frame + new prompt.
        
        Args:
            task_id: Completed parent task ID
            video_index: Which video's frame to use (usually 0)
            new_prompt: New prompt text for the forked task
        
        Returns new task ID, or None on failure.
        """
        source = self._dispatcher.get_task(task_id)
        if not source:
            log.warning(f"[Fork] Source task {task_id} not found")
            return None
        
        frame_uri = source.continuation_frame_uri
        frame_local = source.continuation_frame_local_path
        if not frame_uri and not frame_local:
            log.warning(f"[Fork] No continuation frame on task {task_id}")
            return None
        
        import uuid
        new_id = f"fork_{uuid.uuid4().hex[:8]}"
        
        from core.dispatcher import Task
        forked = Task(
            id=new_id,
            workflow_type=source.workflow_type,
            prompt=new_prompt,
            aspect_ratio=source.aspect_ratio,
            model=source.model,
            output_count=source.output_count,
            duration_seconds=source.duration_seconds,
            download_quality=source.download_quality,
            output_folder=source.output_folder,
            project_name=source.project_name,
            extract_point_ms=source.extract_point_ms,
            continuation_frame_uri=frame_uri,
            continuation_frame_local_path=frame_local,
            parent_task_id=task_id,
            required_account=source.assigned_account,
        )
        
        # Add to same group as source
        for group in self._dispatcher.get_task_groups().values():
            if any(t.id == task_id for t in group.tasks):
                group.tasks.append(forked)
                break
        
        self._dispatcher.submit_task(forked)
        self.state.queue_count += 1
        self._notify_queue_updated()
        log.info(f"[Fork] {task_id} → {new_id} with prompt: {new_prompt[:50]}...")
        return new_id
    
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
        
        # Ensure runtime accounts are synced from profiles BEFORE checking
        # (preflight_check runs before start_processing, which also syncs)
        try:
            self.sync_profiles_to_runtime()
        except Exception as e:
            log.debug(f"[preflight_check] Profile sync failed: {e}")
        
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
            
            # Check 2: Extension connected + headers ready (REQUIRED)
            # 3-state: not connected → blocker, connected but no headers → blocker (wait), ready → pass
            ext_connected = (
                self._extension_bridge and
                self._extension_bridge.is_connected(account.email)
            )
            ext_has_headers = False
            if ext_connected and self._extension_bridge:
                try:
                    cached = self._extension_bridge.get_cached_headers(
                        account.email, max_age_seconds=300
                    )
                    ext_has_headers = bool(cached)
                except Exception:
                    pass
            
            if not ext_connected:
                acc_info["issues"].append("🔴 Extension chưa kết nối — cần mở trình duyệt")
            elif not ext_has_headers:
                acc_info["issues"].append(
                    "🟡 Extension đang kết nối nhưng chưa có headers — "
                    "vui lòng đợi vài giây hoặc reload trang Veo trong trình duyệt"
                )
            
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
            
            # Verdict for this account
            if not acc_info["issues"]:
                acc_info["ready"] = True
                ready_count += 1
            
            result["accounts"].append(acc_info)
        
        result["can_start"] = ready_count > 0
        
        # Build summary
        has_warnings = any(acc.get("warnings") for acc in result["accounts"])
        if ready_count == total_count:
            if has_warnings:
                result["summary"] = f"⚠️ {total_count} tài khoản sẵn sàng (có cảnh báo — sẽ tự xử lý)"
            else:
                result["summary"] = f"✅ Tất cả {total_count} tài khoản sẵn sàng"
        elif ready_count > 0:
            blocked = total_count - ready_count
            result["summary"] = f"⚠️ {ready_count}/{total_count} sẵn sàng, {blocked} bị chặn"
        else:
            result["summary"] = f"❌ Không có tài khoản nào sẵn sàng ({total_count} tổng)"
        
        return result
    
    def start_processing(self):
        """Start processing queue via Engine.
        
        Pre-flight check is done by the UI (tab_queue._on_toggle_engine)
        which shows toast feedback. This method only handles engine startup.
        
        Engine uses asyncio.TaskGroup for proper async worker management.
        The Engine.start() coroutine runs in the background async loop.
        """
        if self.state.is_processing:
            return
        
        self.state.is_processing = True
        self._engine_gen += 1  # ★ Race guard: old _shutdown_engine_bg will see stale gen
        
        # ★ Pause Tab Keepalive — engine takes over tab management
        # Prevents conflict: both keepalive and engine use executeScript
        # on the same tabs (Chrome serializes → delays reCAPTCHA tokens)
        if hasattr(self._engine, '_keepalive_yield'):
            self._engine._keepalive_yield.clear()  # CLEAR = yield to engine
            log.info("[TabKeepalive] Paused — engine processing")
        
        # Issue E: Sync profiles to runtime before starting
        self.sync_profiles_to_runtime()
        
        # Per-account worker settings (max_slots, retry_count, request_timeout)
        # are now read directly from each AccountManager at runtime.
        # No global max_workers needed.
        
        # Pass settings reference for hot-apply (engine reads live values)
        self._engine._settings = self.settings
        
        # Apply saved pipeline settings to engine at startup
        # Without this, workload_priority stays at default '720p_priority'
        # even if user previously selected 'upscale_priority' in Settings tab.
        # Affects ALL workflows (T2V, I2V, R2V, I2I, T2I).
        for key, value in self.get_pipeline_settings().items():
            self._engine.update_pipeline_setting(key, value)
        
        # Wire engine callbacks
        self._engine._on_progress = self._handle_progress
        self._engine._on_task_completed = lambda task: self._handle_task_completed(task)
        self._engine._on_task_failed = lambda task, err: self._handle_task_failed(task, err)
        # RC4: Account error callback → status bar (429/403 notifications)
        self._engine._on_account_error = lambda email, msg: self._notify_status(f"{email}: {msg}")
        
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
        
        # Verify callback chain integrity before engine starts
        self._verify_callback_chain()
        
        log.info("[Engine] Processing started")
    
    def _verify_callback_chain(self):
        """Verify all critical callbacks are wired before engine runs.
        
        One-time check at engine start. Logs WARNING for each missing callback.
        Would have caught the broken progress callback bug immediately.
        """
        checks = {
            'progress → UI': getattr(self, '_on_progress', None) is not None,
            'dispatcher._on_progress_callback': getattr(self._dispatcher, '_on_progress_callback', None) is not None,
            'queue_updated': bool(getattr(self, '_on_queue_updated', None)),
            'status_changed': getattr(self, '_on_status_changed', None) is not None,
            'engine._on_progress': getattr(self._engine, '_on_progress', None) is not None,
            'engine._on_task_completed': getattr(self._engine, '_on_task_completed', None) is not None,
            'engine._on_task_failed': getattr(self._engine, '_on_task_failed', None) is not None,
        }
        
        all_ok = True
        for name, ok in checks.items():
            if not ok:
                log.warning(f"[CallbackCheck] ⚠️ {name} is NOT wired — updates will NOT reach UI!")
                all_ok = False
        
        if all_ok:
            log.info(f"[CallbackCheck] ✅ All {len(checks)} callbacks verified OK")
        else:
            broken = [n for n, ok in checks.items() if not ok]
            log.error(f"[CallbackCheck] ❌ {len(broken)} callback(s) broken: {', '.join(broken)}")
    
    async def _start_recaptcha_pool(self):
        """Start reCAPTCHA pool inside the async event loop.
        
        RecaptchaPool.start() uses asyncio.create_task() internally,
        which requires a running event loop. This wrapper ensures it
        runs in the correct async context.
        """
        self._engine._recaptcha_pool.start()
    
    def stop_processing(self):
        """Stop processing via Engine.
        
        Non-blocking: signals engine to stop immediately, then runs
        the heavy shutdown (await TaskGroup, close sessions) in a
        background thread to keep the UI responsive.
        """
        if not self.state.is_processing:
            return
        self.state.is_processing = False
        
        # ★ Resume Tab Keepalive — engine no longer managing tabs
        if hasattr(self._engine, '_keepalive_yield'):
            self._engine._keepalive_yield.set()  # SET = keepalive active
            log.info("[TabKeepalive] Resumed — engine stopped")
        
        # Signal Engine to stop (sets stop_event → workers exit loops)
        # This is instant — just sets an asyncio.Event
        self._run_async(self._engine.stop())
        
        self._notify_status("Stopping…")
        
        # Heavy shutdown in background thread (blocks up to 28s)
        import threading
        _shutdown_gen = self._engine_gen  # snapshot for race guard
        threading.Thread(
            target=self._shutdown_engine_bg,
            args=(_shutdown_gen,),
            name="engine-shutdown",
            daemon=True,
        ).start()
    
    def _shutdown_engine_bg(self, shutdown_gen: int = 0):
        """Background shutdown — runs blocking .result() calls off UI thread.
        
        Called by stop_processing() in a daemon thread.
        Uses shutdown_gen to detect if a new engine was started during shutdown.
        """
        try:
            # Wait for engine.start() TaskGroup to fully complete
            # (foremen exit, pipelines drain, browsers disconnect)
            # BUG-19: Increased from 15s to 30s — cooperative stop lets
            # pipelines finish gracefully (download retries, upscale polls)
            if self._engine_future:
                try:
                    self._engine_future.result(timeout=30.0)
                except Exception:
                    pass
                self._engine_future = None
            
            # ★ Race guard: if start_processing() was called during our shutdown,
            # skip teardown — the new engine owns these resources now.
            if self._engine_gen != shutdown_gen:
                log.info(f"[Shutdown] Engine re-started (gen {shutdown_gen}→{self._engine_gen}) — skipping teardown")
                return
            
            # Stop Watchdog
            try:
                self._task_watchdog.stop()
            except Exception:
                pass
            
            # BUG-20: UpscaleQueue.stop() already called by engine.stop()
            # (removed duplicate call that was here)
            
            # Phase 3B: Cancel pending Extension requests (keep bridge alive for restart)
            # bridge.stop() is only called on APP EXIT (AppController.stop, L368)
            bridge = getattr(self, '_extension_bridge', None)
            if bridge:
                bridge.cancel_pending_requests()
            
            # Phase 3C: Close API client session
            if hasattr(self._engine, '_api_client') and self._engine._api_client:
                close_future = self._run_async(self._engine._api_client.close())
                if close_future:
                    try:
                        close_future.result(timeout=3.0)
                    except Exception:
                        pass
            
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
            
            log.info("[AppController] Engine shutdown complete")
            
            # ★ Post-shutdown restart: check if new tasks arrived during shutdown
            # Race condition: Pipeline Stage 4 completes → AutoStop → Stage 5 adds
            # tasks during the ~30s shutdown window → those tasks never get processed.
            # Fix: after full shutdown, re-check ready_count and auto-restart if needed.
            try:
                if self._dispatcher.ready_count > 0:
                    from config.settings import get_settings
                    s = get_settings()
                    if getattr(s, 'auto_start_queue', False):
                        pending = self._dispatcher.ready_count
                        log.info(f"[AutoStop→Restart] {pending} new tasks found after shutdown — scheduling restart")
                        from PySide6.QtCore import QTimer, QThread
                        # ★ Thread-safe: _shutdown_engine_bg runs on daemon thread
                        # QTimer.singleShot from non-Qt thread is unsafe.
                        # Use a lambda that safely schedules on GUI thread.
                        try:
                            from PySide6.QtWidgets import QApplication
                            app = QApplication.instance()
                            if app and QThread.currentThread() != app.thread():
                                # Marshal to GUI thread first, then schedule with delay
                                QTimer.singleShot(0, lambda: QTimer.singleShot(2000, self.start_processing))
                            else:
                                QTimer.singleShot(2000, self.start_processing)
                        except Exception:
                            QTimer.singleShot(2000, self.start_processing)
                    else:
                        log.info(f"[AutoStop] {self._dispatcher.ready_count} new tasks found but auto_start_queue=False — skipping restart")
            except Exception as e:
                log.warning(f"[AutoStop→Restart] Post-shutdown check failed: {e}")
        except Exception as e:
            log.error(f"[AppController] Shutdown error: {e}")
        finally:
            self._notify_status("Processing stopped")
    
    def _auto_export_logs(self):
        """Auto-export structured session logs (TESTER only)."""
        try:
            if not hasattr(self._license_client, 'can_see_dev_console') or \
                    not self._license_client.can_see_dev_console():
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
        
        # ★ Resume keepalive when engine paused (workers sleeping, tabs need keepalive)
        if hasattr(self._engine, '_keepalive_yield'):
            self._loop.call_soon_threadsafe(self._engine._keepalive_yield.set)
            log.info("[TabKeepalive] Resumed — engine paused")
        
        self._notify_status("Processing paused")
    
    def resume_processing(self):
        """Resume processing — wake up sleeping workers.
        
        No engine restart needed — workers and browsers are still alive.
        """
        if not self.state.is_processing:
            return
        if not self._engine.is_paused:
            return
        
        # ★ Pause keepalive when engine resumes (engine takes back tab management)
        if hasattr(self._engine, '_keepalive_yield'):
            self._loop.call_soon_threadsafe(self._engine._keepalive_yield.clear)
            log.info("[TabKeepalive] Paused — engine resumed")
        
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
        """Handle task completion + detect group completion + auto-stop."""
        # Check group completion FIRST — if group just completed,
        # skip per-task toast to avoid duplicate notifications
        group_completed = self._check_group_completion(task)
        
        if not group_completed and self._on_task_completed:
            self._on_task_completed(task)
        self._notify_queue_updated()
        
        # ── Auto-stop: all tasks finished → stop engine ──
        self._check_auto_stop()
    
    def _check_group_completion(self, task: Task) -> bool:
        """Check if the task's group is fully completed and fire notification.
        
        Returns:
            True if a group completion was detected and notified.
        """
        for group_id, group in self._dispatcher.get_task_groups().items():
            if any(t.id == task.id for t in group.tasks):
                if group.status == "completed" and group_id not in self._notified_groups:
                    self._notified_groups.add(group_id)
                    if self._on_group_completed:
                        self._on_group_completed(group)
                    return True
                break
        return False
    
    def _handle_task_failed(self, task: Task, error: str):
        """Handle task failure."""
        if self._on_task_failed:
            self._on_task_failed(task, error)
        self._notify_queue_updated()
        
        # ── Auto-stop: all tasks finished → stop engine ──
        self._check_auto_stop()
    
    def _check_auto_stop(self):
        """Auto-stop engine when ALL tasks reached terminal state.
        
        Prevents engine from running forever after all work is done,
        which would cause reCAPTCHA request accumulation + Chrome tab freeze.
        
        ★ Fix: Pipeline guard checked FIRST to prevent race condition
        where AutoStop fires before pipeline adds next-stage tasks.
        """
        if not self.state.is_processing:
            return  # Already stopped
        
        try:
            # ★ PRIORITY 1: Don't auto-stop if pipeline is mid-transition
            # Race condition: Stage 4 completes → auto-stop fires → Stage 5 adds
            # tasks during shutdown → engine gen 2 gets killed by gen 1's shutdown.
            # This check MUST come first — before any task state inspection.
            if self._pipeline_awaiting_queue or self._pipeline_mode_active:
                log.info("[AutoStop] Deferred — pipeline active "
                         f"(queue_flag={self._pipeline_awaiting_queue}, "
                         f"mode_flag={self._pipeline_mode_active})")
                return
            
            terminal_states = {'completed', 'failed', 'cancelled'}
            
            # Check ready queue first (fast path)
            if self._dispatcher.ready_count > 0:
                return
            
            # Check all tasks for non-terminal state
            for task in self._dispatcher.get_all_tasks():
                if task.state.value not in terminal_states:
                    return  # Still has active/pending work
            
            # ★ FIX: Don't auto-stop if UpscaleQueue has pending work
            # Without this, AutoStop kills in-flight upscales → 'NoneType' errors
            # and workers skip upscale on shared _stop_event
            if hasattr(self, '_engine') and self._engine:
                uq = getattr(self._engine, '_upscale_queue', None)
                if uq and uq.has_pending_work():
                    log.info("[AutoStop] Deferred — UpscaleQueue still has pending work")
                    return
            
            # All tasks in terminal state + ready queue empty + no pending upscales → auto-stop
            log.info("[AutoStop] All tasks finished — stopping engine automatically")
            self.stop_processing()
        except Exception as e:
            log.warning(f"[AutoStop] Check failed: {e}")
    
    def set_pipeline_queue_active(self, active: bool):
        """Called by TabProject when pipeline starts/stops queue polling.
        
        Prevents AutoStop from killing engine during pipeline stage transitions
        (e.g. Stage 4 queue done → Stage 5 adds new tasks).
        """
        was_active = self._pipeline_awaiting_queue
        self._pipeline_awaiting_queue = active
        if active:
            log.info("[AutoStop] Pipeline queue ACTIVE — auto-stop deferred")
        elif was_active:
            log.info("[AutoStop] Pipeline queue INACTIVE — auto-stop allowed")
    
    def set_pipeline_mode_active(self, active: bool):
        """Called by TabProject when pipeline starts/finishes all stages.
        
        Redundant guard: keeps auto-stop deferred while ANY pipeline stage
        is running, not just during queue polling.
        """
        self._pipeline_mode_active = active
        if active:
            log.info("[AutoStop] Pipeline mode ACTIVE — auto-stop deferred")
        else:
            log.info("[AutoStop] Pipeline mode INACTIVE — auto-stop allowed")
    
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
        """Register callback for per-task progress updates (used by TabQueue).
        
        Wires directly into Dispatcher._on_progress_callback so engine's
        update_progress() calls reach the UI in real-time.
        """
        self._on_progress = callback
        # Wire into dispatcher — this is where update_progress() actually fires
        if hasattr(self._dispatcher, '_on_progress_callback'):
            self._dispatcher._on_progress_callback = callback
    
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
    
    def _check_license_gate(self) -> bool:
        """
        Inline license check for generation gate point.
        
        Security: Does NOT rely on cached _license_valid flag.
        Calls validate() directly every time (60s TTL cache in LicenseClient).
        """
        try:
            if not hasattr(self, '_license_client') or not self._license_client:
                return False
            info = self._license_client.validate()
            if not info or not info.valid:
                return False
            # Cross-check: tier must exist (not just valid=True)
            if not info.tier:
                return False
            return True
        except Exception:
            return False
    
    def _update_permissions(self):
        """Update permissions from license."""
        try:
            info = self._license_client.validate()
            if info.valid and info.tier:
                self._license_valid = True
                from config.constants import LicenseTier
                try:
                    self._permissions.set_role_from_tier(info.tier)
                except (ValueError, AttributeError):
                    pass
                
                # 4.3: Override to TESTER if Firebase _role field says TESTER
                try:
                    from security.license_client import UserRole
                    if hasattr(info, 'role') and info.role == UserRole.TESTER:
                        self._permissions.set_role(Role.TESTER)
                        log.info("[License] Role override: TESTER (from Firebase _role)")
                except Exception:
                    pass
                
                # 4.4: Apply dynamic limits from Firebase _lim field
                if hasattr(info, 'limits_override') and info.limits_override:
                    self._permissions.apply_server_limits(info.limits_override)
                    log.info(f"[License] Dynamic limits applied: {info.limits_override}")
                else:
                    # Fallback: read tier template from _config/tier_defaults
                    try:
                        rest_client = getattr(self._license_client, '_rest_client', None)
                        if rest_client and hasattr(rest_client, 'read_tier_defaults'):
                            tier_defaults = rest_client.read_tier_defaults()
                            role_name = self._permissions.role.name  # TRIAL, PREMIUM, TESTER
                            tmpl = tier_defaults.get(role_name, {})
                            if tmpl:
                                lim = {k: v for k, v in tmpl.items() if k in ('ac', 'fm', 'wk', 'op', 'dg', 'pb')}
                                if lim:
                                    self._permissions.apply_server_limits(lim)
                                    log.info(f"[License] Tier template applied ({role_name}): {lim}")
                    except Exception as e:
                        log.debug(f"[License] Tier template fallback skipped: {e}")
                
                # 4.5: Periodic integrity check (Level 3 — anti Cheat Engine)
                if not self._permissions.verify_limits_integrity():
                    log.critical("[License] ⛔ Limits integrity violation — RAM tampered! Resetting.")
                    self._permissions.reset_limits_from_cache()
            else:
                # G0: Trial expired or license invalid → block generation
                self._license_valid = False
                self._permissions.set_role(Role.TRIAL)
                log.warning(f"[License] Invalid: {getattr(info, 'error', 'unknown')}")
        except Exception as e:
            # G0: Any validation error → assume invalid, block app
            self._license_valid = False
            self._permissions.set_role(Role.TRIAL)
            log.warning(f"[License] Validation error — treating as invalid: {e}")
        
        # 4.6: Schedule periodic integrity check (every 5 min after startup)
        if not getattr(self, '_integrity_timer_started', False):
            self._integrity_timer_started = True
            try:
                from PySide6.QtCore import QTimer
                self._integrity_timer = QTimer()
                self._integrity_timer.setInterval(5 * 60 * 1000)  # 5 minutes
                self._integrity_timer.timeout.connect(self._periodic_integrity_check)
                # Start after 30s delay (let app fully init)
                QTimer.singleShot(30_000, self._integrity_timer.start)
                log.info("[License] Integrity timer scheduled (30s delay → every 5min)")
            except Exception:
                pass
    
    def _periodic_integrity_check(self):
        """Periodic RAM integrity check — detect Cheat Engine / memory patches."""
        try:
            if not self._permissions.verify_limits_integrity():
                log.critical("[License] ⛔ Periodic integrity check FAILED — RAM tampered!")
                self._permissions.reset_limits_from_cache()
                # Re-validate from server
                self._update_permissions()
        except Exception as e:
            log.warning(f"[License] Integrity check error: {e}")
    
    def activate_license(self, license_key: str) -> Dict:
        """Activate a license key.
        
        Called by TabLicense UI when user enters a key.
        
        Returns:
            Dict with 'success', 'message', 'tier', 'role' keys.
        """
        try:
            info = self._license_client.activate(license_key)
            if info.valid:
                # Update permissions from tier
                self._license_valid = True
                self._update_permissions()
                log.info(f"[License] Activated: tier={info.tier.name if info.tier else '?'}, role={info.role.name if info.role else '?'}")
                return {
                    "success": True,
                    "message": f"License activated: {info.tier.name if info.tier else 'Unknown'}",
                    "tier": info.tier.value if info.tier else None,
                    "role": info.role.value if info.role else "trial",
                }
            else:
                log.warning(f"[License] Activation failed: {info.error}")
                return {"success": False, "message": info.error or "Invalid license key"}
        except Exception as e:
            log.error(f"[License] Activation error: {e}")
            return {"success": False, "message": f"Activation failed: {str(e)}"}
    
    def deactivate_license(self):
        """Deactivate current license and revert to TRIAL."""
        try:
            self._license_client.deactivate()
            self._permissions.set_role(Role.TRIAL)
            log.info("[License] Deactivated → TRIAL")
        except Exception as e:
            log.error(f"[License] Deactivation error: {e}")
    
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
    
    # Tier code → display name mapping
    _TIER_DISPLAY_NAMES = {
        'TRIA': 'Trial',
        '1M': 'Premium',
        '3M': 'Premium',
        '6M': 'Premium',
        '1Y': 'Premium',
        'LT': 'Vĩnh Viễn',
    }
    
    def get_license_status(self) -> Dict:
        """Get license status for status bar display."""
        try:
            info = self._license_client.validate()
            tier_code = info.tier.value if info.tier else None
            tier_name = self._TIER_DISPLAY_NAMES.get(tier_code, tier_code) if tier_code else None
            return {
                "is_licensed": info.valid and info.tier and info.tier.value != "trial",
                "is_trial": info.tier and info.tier.value == "trial" if info.valid else True,
                "trial_expired": not info.valid and info.error and "expired" in (info.error or "").lower(),
                "tier": tier_code,
                "tier_name": tier_name,
                "days_remaining": (info.expires - __import__('datetime').datetime.now()).days if info.expires else 0,
                "expires": info.expires.strftime('%Y-%m-%d') if info.expires else None,
                "expires_dt": info.expires.isoformat() if info.expires else None,
            }
        except Exception:
            return {"is_licensed": False, "is_trial": True, "trial_expired": False, "tier": None, "tier_name": None, "days_remaining": 0, "expires": None, "expires_dt": None}
    
    def get_account_summary(self) -> Dict:
        """Get account summary for status bar display."""
        return {
            "total": self._multi_account.account_count,
            "ready": len(self._multi_account.ready_accounts),
            "active": self._multi_account.total_active,
            # ★ Fix: dispatcher._running_count tracks ALL tasks in RUNNING state
            # (submit + download + upscale), not just acquired worker slots
            "running_tasks": self._dispatcher.running_count,
            # Actual session worker slots currently held (released at submit for T2I)
            "active_workers": self._multi_account.total_active,
            # ★ Pool Separation: upscale worker counts
            "active_upscale": self._multi_account.total_active_upscale,
            "max_upscale": self._multi_account.total_max_upscale,
            # ★ LP worker counts (Fast Low Priority)
            "active_workers_lp": self._multi_account.total_active_lp,
            "max_workers_lp": self._multi_account.total_capacity_lp,
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
            # Filter out replacement tasks (per-video retries) — they're invisible
            # to the user; their results slot back into original task's video_outputs
            visible_tasks = [t for t in group.tasks if not getattr(t, 'replace_target', None)]
            completed = sum(1 for t in visible_tasks if t.state == TaskState.COMPLETED)
            total = len(visible_tasks)
            # Detect mode/model from first task
            first = visible_tasks[0] if visible_tasks else None
            
            # Compute group elapsed time from task timestamps
            # BUG-T1 fix: Correctly handle completed vs running groups
            from datetime import datetime as _dt
            _now = _dt.now()
            started_tasks = [t for t in visible_tasks if getattr(t, 'started_at', None)]
            
            if started_tasks:
                earliest = min(t.started_at for t in started_tasks)
                
                # Check if any tasks are still running (no completed_at)
                has_running = any(
                    not getattr(t, 'completed_at', None)
                    for t in started_tasks
                )
                
                if has_running:
                    # Live timer: use _now as end point for running tasks
                    end_times = [
                        getattr(t, 'completed_at', None) or _now
                        for t in started_tasks
                    ]
                    latest = max(end_times)
                else:
                    # All started tasks are done: freeze elapsed at completion time
                    latest = max(t.completed_at for t in started_tasks)
                
                _elapsed = (latest - earliest).total_seconds()
            else:
                _elapsed = 0.0
            
            result.append(GroupDTO(
                id=gid,
                name=group.name,
                status=group.status,
                # ⚡ FIX: compute from visible_tasks only (group.progress includes hidden replacement tasks)
                progress=int(sum(getattr(t, 'progress', 0) or 0 for t in visible_tasks) / len(visible_tasks)) if visible_tasks else 0,
                completed=completed,
                total=total,
                mode=_wf_display(first.workflow_type) if first else "T2V",
                model=(first.model if first else ""),
                output_folder=(first.output_folder if first else ""),
                project_name=(first.project_name if first else ""),
                aspect_ratio=(first.aspect_ratio if first else ""),
                output_count=(first.output_count if first else 4),
                download_quality=(first.download_quality if first and hasattr(first, 'download_quality') else "720p"),
                created_at=group.created_at,
                elapsed_seconds=_elapsed,
                tasks=[
                    TaskDTO(
                        id=t.id,
                        index=i + 1,
                        prompt=t.prompt,
                        status=t.state.value,
                        progress=t.progress,
                        mode=_wf_display(t.workflow_type) if t.workflow_type else "T2V",
                        has_continuation=t.parent_task_id is not None,
                        parent_id=t.parent_task_id,
                        error=t.error,
                        output_count=t.output_count,
                        output_files=list(t.output_uris) if t.output_uris else [],
                        # Build thumbnails from video_outputs (per-video, index-safe)
                        # instead of task.thumbnail_paths (flat list that shifts after retry)
                        thumbnails=(
                            [vo.thumbnail_path for vo in t.video_outputs]
                            if hasattr(t, 'video_outputs') and t.video_outputs
                            else list(t.thumbnail_paths) if hasattr(t, 'thumbnail_paths') else []
                        ),
                        image_paths=list(getattr(t, 'image_paths', [])) if t.image_paths else [],
                        continuation_frame=t.continuation_frame_local_path or "",
                        upscale_status=getattr(t, 'upscale_status', ''),
                        upscale_error=getattr(t, 'upscale_error', ''),
                        image_upload_status=getattr(t, 'image_upload_status', ''),
                        download_quality=getattr(t, 'download_quality', '720p'),
                        status_text=getattr(t, 'status_text', ''),
                        started_at=getattr(t, 'started_at', None),
                        completed_at=getattr(t, 'completed_at', None),
                        # BUG-T3: Compute per-task elapsed time
                        elapsed_seconds=(
                            (
                                (getattr(t, 'completed_at', None) or _now) - t.started_at
                            ).total_seconds()
                            if getattr(t, 'started_at', None) else 0.0
                        ),
                        retry_progress=getattr(t, '_retry_progress', -1),
                        retry_status_text=getattr(t, '_retry_status_text', ''),
                        video_outputs=[
                            VideoSlotDTO(
                                index=vo.index,
                                quality=vo.quality,
                                upscale_status=vo.upscale_status,
                                upscale_error=vo.upscale_error,
                                best_file=vo.best_file,
                                border_color=vo.border_color,
                                thumbnail_path=vo.thumbnail_path,
                                task_id=t.id,
                                target_quality=getattr(t, 'download_quality', '1080p'),
                                upscale_poll_count=getattr(vo, 'upscale_poll_count', 0),
                            )
                            for vo in (t.video_outputs if hasattr(t, 'video_outputs') else [])
                        ],
                    )
                    for i, t in enumerate(visible_tasks)
                ],
            ).to_dict())
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
            if 'download_quality' in settings:
                task.download_quality = settings['download_quality']
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
    
    def force_retry_video(self, task_id: str, video_index: int) -> bool:
        """Force retry a SINGLE video by index, preserving all other videos."""
        return self._dispatcher.force_retry_video(task_id, video_index)
    
    def get_replace_target(self, task_id: str):
        """Get (original_task_id, video_index) if task_id is a replacement task."""
        return self._dispatcher.get_replace_target(task_id)
    
    def _ensure_account_bridge(self, account):
        """Defensive injection: ensure account has extension_bridge + profiles_controller.
        
        During startup, accounts may be created before bridge injection completes.
        This ensures the bridge is always available for on-demand operations
        (re-upscale, re-download, manual retry) regardless of startup timing.
        """
        if not account:
            return
        if not account.extension_bridge and hasattr(self, '_extension_bridge') and self._extension_bridge:
            account.extension_bridge = self._extension_bridge
            import logging
            logging.getLogger(__name__).info(
                f"[BridgeInject] Injected extension_bridge into {account.email} (lazy)"
            )
        if not account._profiles_controller and hasattr(self, '_profiles_controller') and self._profiles_controller:
            account.set_profiles_controller(self._profiles_controller)
        if not getattr(account, '_parent_manager', None):
            account._parent_manager = self._multi_account
    
    async def _enforce_account_tiers(self):
        """Check paygate_tier for all accounts — disable Free, sync tier to runtime.
        
        Called after browsers connect and extension data is available.
        Fetches subscription info if not yet cached, then:
        - Disables PAYGATE_TIER_NOT_PAID (Free) accounts
        - Logs tier for each account
        - Pushes updated browser status to UI
        """
        if not self._profiles_controller:
            return
        
        disabled_count = 0
        for acc in list(self._multi_account._accounts):
            email = acc.email
            try:
                profile = self._profiles_controller.get_profile(email)
                if not profile:
                    continue
                
                # Fetch fresh subscription if not yet fetched
                tier = profile.paygate_tier
                if not tier or tier == "UNKNOWN":
                    try:
                        await self._profiles_controller._fetch_subscription_via_browser(email)
                        profile = self._profiles_controller.get_profile(email)
                        tier = profile.paygate_tier if profile else None
                    except Exception as e:
                        log.debug(f"[TierCheck] Subscription fetch failed for {email}: {e}")
                
                # Sync tier from profile → runtime AccountManager
                if tier:
                    acc._paygate_tier = tier
                
                # Disable Free accounts
                if tier == "PAYGATE_TIER_NOT_PAID":
                    acc.disable()
                    profile.is_enabled = False
                    self._profiles_controller.save_profiles()
                    disabled_count += 1
                    log.warning(f"[TierCheck] ⛔ {email}: Free account → auto-disabled")
                else:
                    tier_label = "Ultra" if tier == "PAYGATE_TIER_TWO" else (
                        "Pro" if tier == "PAYGATE_TIER_ONE" else tier or "unknown"
                    )
                    log.info(f"[TierCheck] ✅ {email}: {tier_label}")
            except Exception as e:
                log.debug(f"[TierCheck] Error checking {email}: {e}")
        
        if disabled_count > 0:
            log.warning(f"[TierCheck] ⛔ {disabled_count} Free account(s) auto-disabled")
            self._push_browser_status()
            self._notify_profiles_changed()
        else:
            log.info("[TierCheck] ✅ All accounts are Pro or Ultra")
    
    async def _enforce_single_account_tier(self, email: str):
        """Check tier for a single account — called on extension connect."""
        if not self._profiles_controller:
            return
        
        acc = self._multi_account.get_account(email)
        if not acc:
            return
        
        profile = self._profiles_controller.get_profile(email)
        if not profile:
            return
        
        tier = profile.paygate_tier
        if tier:
            acc._paygate_tier = tier
        
        if tier == "PAYGATE_TIER_NOT_PAID":
            acc.disable()
            profile.is_enabled = False
            self._profiles_controller.save_profiles()
            log.warning(f"[TierCheck] ⛔ {email}: Free account → auto-disabled")
            self._push_browser_status()
            self._notify_profiles_changed()
    
    def _notify_profiles_changed(self):
        """Notify Settings tab to refresh profiles table (thread-safe).
        
        Triggers the profiles_changed callback registered by TabSettings,
        which calls _refresh_profiles_table() to update toggle switches.
        """
        if not (hasattr(self, '_profiles_controller') and self._profiles_controller):
            return
        cb = self._profiles_controller._callbacks.get("profiles_changed")
        if not cb:
            return
        try:
            from PySide6.QtCore import QMetaObject, Qt, QThread
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app and QThread.currentThread() != app.thread():
                QMetaObject.invokeMethod(app, cb, Qt.ConnectionType.QueuedConnection)
            else:
                cb()
        except Exception as e:
            log.debug(f"[NotifyProfiles] Failed to notify UI: {e}")
    
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
                self._ensure_account_bridge(account)
                return account, None
            # Account exists in config but not loaded/available
            return None, (
                f"⚠️ Account {task.assigned_account} not available. "
                f"Re-upscale requires the original account (media_id is account-bound)."
            )
        
        # No assigned_account recorded (legacy tasks before account tracking)
        if self._multi_account._accounts:
            account = self._multi_account._accounts[0]
            self._ensure_account_bridge(account)
            return account, None
        
        return None, "⚠️ No account available for re-upscale"
    
    def re_upscale_task(self, task_id: str, failed_only: bool = True):
        """Re-upscale a completed task using stored media_ids.
        
        Args:
            failed_only: If True, only re-upscale failed videos. If False, re-upscale all.
        
        Runs async engine method on the background event loop.
        Returns immediately — result is communicated via callbacks.
        """
        if not self._loop:
            return
        
        async def _run():
            try:
                log.info(f"[ReUpscale] Starting re-upscale for task {task_id} (failed_only={failed_only})")
                account, error = self._get_account_for_reupscale(task_id)
                if not account:
                    log.warning(f"[ReUpscale] {error}")
                    self._notify_status(error)
                    return
                
                result = await self._engine.re_upscale_task(task_id, account, failed_only=failed_only)
                log.info(f"[ReUpscale] Task {task_id} finished: {'success' if result else 'failed'}")
            except Exception as e:
                log.error(f"[ReUpscale] Task {task_id} crashed: {e}", exc_info=True)
            finally:
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
            try:
                log.info(f"[ReUpscale] Starting re-upscale for {task_id}[{video_index}]")
                account, error = self._get_account_for_reupscale(task_id)
                if not account:
                    log.warning(f"[ReUpscale] {error}")
                    self._notify_status(error)
                    return
                
                result = await self._engine.re_upscale_single_video(
                    task_id, video_index, account
                )
                log.info(f"[ReUpscale] {task_id}[{video_index}] finished: {'success' if result else 'failed'}")
            except Exception as e:
                log.error(f"[ReUpscale] {task_id}[{video_index}] crashed: {e}", exc_info=True)
            finally:
                # Trigger queue refresh so UI updates status
                for cb in self._on_queue_updated:
                    try:
                        cb({})
                    except Exception:
                        pass
        
        asyncio.run_coroutine_threadsafe(_run(), self._loop)
    
    def re_download_720p(self, task_id: str):
        """Re-download 720p videos by re-polling completed operations.
        
        Called from QueueTab context menu.
        Runs async engine method on the background event loop.
        """
        if not self._loop:
            return
        
        async def _run():
            try:
                log.info(f"[ReDownload] Starting re-download 720p for task {task_id}")
                account, error = self._get_account_for_reupscale(task_id)
                if not account:
                    log.warning(f"[ReDownload] {error}")
                    self._notify_status(error)
                    return
                
                result = await self._engine.re_download_720p(task_id, account)
                log.info(f"[ReDownload] Task {task_id} finished: {'success' if result else 'failed'}")
            except Exception as e:
                log.error(f"[ReDownload] Task {task_id} crashed: {e}", exc_info=True)
            finally:
                # Trigger queue refresh so UI updates
                for cb in self._on_queue_updated:
                    try:
                        cb({})
                    except Exception:
                        pass
        
        asyncio.run_coroutine_threadsafe(_run(), self._loop)
    
    def re_download_single_720p(self, task_id: str, video_index: int):
        """Re-download a single 720p video by index.
        
        Called from UI right-click on thumbnail.
        Runs async engine method on the background event loop.
        """
        if not self._loop:
            return
        
        async def _run():
            try:
                log.info(f"[ReDownload] Starting re-download 720p for {task_id}[{video_index}]")
                account, error = self._get_account_for_reupscale(task_id)
                if not account:
                    log.warning(f"[ReDownload] {error}")
                    self._notify_status(error)
                    return
                
                result = await self._engine.re_download_single_720p(
                    task_id, video_index, account
                )
                log.info(f"[ReDownload] {task_id}[{video_index}] finished: {'success' if result else 'failed'}")
            except Exception as e:
                log.error(f"[ReDownload] {task_id}[{video_index}] crashed: {e}", exc_info=True)
            finally:
                # Trigger queue refresh so UI updates
                for cb in self._on_queue_updated:
                    try:
                        cb({})
                    except Exception:
                        pass
        
        asyncio.run_coroutine_threadsafe(_run(), self._loop)
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks."""
        return self._dispatcher.retry_all_failed()
    
    def force_retry_all_failed_videos(self) -> int:
        """Force retry ALL failed video slots across all tasks (including completed)."""
        return self._dispatcher.force_retry_all_failed_videos()
    
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
        # Wire into dispatcher so update_progress() reaches UI
        if hasattr(self._dispatcher, '_on_progress_callback'):
            self._dispatcher._on_progress_callback = callback
    
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
                    log.info(f"[Session] Queue restored: {count} tasks")
        else:
            log.info("[Session] Queue restore SKIPPED (restore_queue_on_startup=False)")
        
        if not restore_tabs:
            data.pop("tabs", None)
            log.info("[Session] Tabs restore SKIPPED (restore_tabs_on_startup=False)")
        
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
        log.info(f"[Controller] Queue cleared: {count} tasks, session file deleted")
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
