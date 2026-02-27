"""
VEO Pro Max - Orchestration Engine

Reference: ARCHITECTURE_OVERVIEW.md (lines 94-120)
Role: Connects Orchestrator ↔ Account Scheduler ↔ Prompt Pipeline into a working pipeline

Architecture: Hybrid Asyncio + ProcessPoolExecutor
- asyncio Event Loop (Main): Orchestrator, Scheduler, TaskGroup
- asyncio.TaskGroup: manages Worker coroutines
- ProcessPoolExecutor: CPU-bound tasks (ffmpeg, image processing)
"""

from typing import Optional, List, Dict, Callable
from concurrent.futures import ProcessPoolExecutor
import asyncio
import base64
import os
import random
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.multi_account import MultiAccountManager
from core.account_manager import AccountManager
from core.dispatcher import Dispatcher, Task, TaskState, TaskStage, VideoOutputInfo
from core.worker import Worker, WorkerResult
from core.api_client import VEOApiClient
from core.frame_extractor import FrameExtractor
from core.trpc_client import TRPCClient
from core.event_manager import emit_event, EventType
from core.manifest_manager import ManifestManager
from core.account_health import CreditWindow
from core.remedy_registry import execute_recovery
from core.error_classifier import classify_error, ERROR_CREDIT_COST

log = logging.getLogger(__name__)


from dataclasses import dataclass as _dc

@_dc
class WorkerVideoResult:
    """Per-worker output — written to results_dict[video_index] by _video_worker."""
    index: int
    op_name: str
    media_id: str = ""
    fife_url: str = ""
    file_720p: str = ""
    file_final: str = ""        # Upscaled path or 720p if no-upscale
    quality: str = "pending"    # pending → polling → downloading → 720p → 1080p/4K → failed
    thumbnail_path: str = ""
    error: str = ""


class AccountSupervisor:
    """CHỦ — Per-account supervisor.
    
    Owns: error queue, clearance gate, abort signal.
    Foreman reports errors → supervisor decides recovery strategy
    → clears gate when ready to proceed.
    """

    def __init__(self, account: AccountManager, engine: 'Engine'):
        self.account = account
        self.engine = engine
        self.email = account.email
        
        # Clearance gate: foreman calls wait_for_clearance() before submit
        self._allow_submit = asyncio.Event()
        self._allow_submit.set()  # Start open (foreman can proceed)
        
        # Error queue: foreman pushes errors here
        self._error_queue: asyncio.Queue = asyncio.Queue()
        
        # DD4: Abort signal — circuit breaker trip → foreman must exit
        self._foreman_abort = asyncio.Event()
        
        # Startup gate: set after one-time startup tasks complete.
        # All foremen wait on this before entering their main loop.
        self._startup_done = asyncio.Event()
        
        # Progressive unlock: set after first foreman submits successfully.
        # Foremen idx>0 wait on this before entering main loop.
        # Prevents 8 foremen burst-submitting when reCAPTCHA is broken.
        self._first_submit_ok = asyncio.Event()
        
        self._running = False

    async def report_error(self, error_type: str, details: str = ""):
        """Foreman reports an error (403, tab_frozen, etc).
        
        Blocks foreman gate → pushes error → supervisor processes → reopens gate.
        """
        self._allow_submit.clear()  # Block foreman
        await self._error_queue.put({"type": error_type, "details": details})

    async def wait_for_clearance(self):
        """Foreman waits here before each submit."""
        await self._allow_submit.wait()

    def abort_foreman(self):
        """DD4: Signal foreman to exit (circuit breaker tripped)."""
        self._foreman_abort.set()
        self._allow_submit.set()  # Unblock so foreman can see abort

    def clear_abort(self):
        """DD4: Clear abort signal (circuit breaker recovered)."""
        self._foreman_abort.clear()

    @property
    def is_aborted(self) -> bool:
        """DD4: Check if foreman should exit."""
        return self._foreman_abort.is_set()

    async def run(self):
        """Supervisor loop — one-time startup + error processing.
        
        Phase 1 (startup): readiness checks, reCAPTCHA warm, pre-upload.
                           Sets _startup_done when complete → foremen unblocked.
        Phase 2 (loop):    processes errors from foremen.
        """
        self._running = True
        log.info(f"[Supervisor:{self.email}] Started")
        
        # ── Phase 1: One-time startup (shared by all foremen) ────────
        try:
            await self.engine._wait_for_account_ready(self.account, timeout=30.0)
            await self.engine._check_app_availability(self.account)
            
            # Create project + navigate browser BEFORE reCAPTCHA init.
            # This ensures reCAPTCHA widget initializes on the correct
            # project page context (avoids token rejection).
            await self._ensure_project_page()
            
            log.info(f"[Supervisor:{self.email}] Pre-warming reCAPTCHA...")
            rc_ready = await self.engine._wait_for_recaptcha_ready(
                self.account, max_wait=30.0,
            )
            if not rc_ready:
                log.warning(
                    f"[Supervisor:{self.email}] ⚠️ reCAPTCHA not ready — "
                    f"foremen will retry before first submit"
                )
            
            # Probe submit: test reCAPTCHA pipeline with real token
            # before unblocking foremen. This catches the case where
            # grecaptcha.execute works but server rejects the token.
            probe_ok = await self._probe_submit()
            if not probe_ok:
                log.warning(
                    f"[Supervisor:{self.email}] ⚠️ Probe submit failed — "
                    f"foreman-0 will proceed cautiously, others wait"
                )
            
            await self.engine._pre_upload_r2v_images(self.account)
            log.info(f"[Supervisor:{self.email}] ✅ Startup complete — unblocking foremen")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error(f"[Supervisor:{self.email}] Startup error (continuing): {e}")
        finally:
            self._startup_done.set()  # Always unblock foremen
        
        # ── Phase 2: Error processing loop ────────
        
        try:
            while self._running and not self.engine._stop_event.is_set():
                try:
                    # Wait for error with timeout (allows clean shutdown)
                    error = await asyncio.wait_for(
                        self._error_queue.get(), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

                error_type = error.get("type", "")
                details = error.get("details", "")
                log.info(
                    f"[Supervisor:{self.email}] Received error: "
                    f"type={error_type}, details={details[:100]}"
                )

                try:
                    if error_type == "403":
                        await self._handle_403(details)
                    elif error_type == "tab_frozen":
                        await self._handle_tab_freeze(details)
                    else:
                        log.warning(
                            f"[Supervisor:{self.email}] Unknown error type: {error_type}"
                        )
                except Exception as e:
                    log.error(f"[Supervisor:{self.email}] Recovery error: {e}")

                # Reopen gate — foreman can proceed
                self._allow_submit.set()
                log.info(f"[Supervisor:{self.email}] ✅ Gate reopened")

        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._allow_submit.set()  # Don't leave foreman blocked
            log.info(f"[Supervisor:{self.email}] Stopped")

    async def _ensure_project_page(self):
        """Create project if needed and navigate browser to project page.
        
        Called during startup BEFORE reCAPTCHA init so the widget
        initializes on the correct project page context.
        
        Escalation:
        1. Try to reuse existing project
        2. Create new project via TRPC
        3. Retry once on failure
        """
        account = self.account
        email = self.email
        
        # Create project if not exists
        if not account.project_id:
            trpc_client = None
            if account._browser_session and account._browser_session.is_ready:
                trpc_client = TRPCClient(account._browser_session._page)
            
            project_id = None
            
            # Step 1: Try to reuse existing project
            if trpc_client:
                try:
                    projects = await trpc_client.get_projects()
                    if projects:
                        project_id = projects[0].get("projectId")
                        if project_id:
                            log.info(
                                f"[Supervisor:{email}] ♻️ Reusing existing project: "
                                f"{project_id}"
                            )
                except Exception:
                    pass  # Fall through to create
            
            # Step 2: Create new project if no existing one
            if not project_id:
                for attempt in range(2):
                    try:
                        project_id = await account.project_manager.get_or_create_project(
                            email=email,
                            access_token=account.get_access_token(),
                            api_client=self.engine._api_client,
                            trpc_client=trpc_client,
                            title="My Video Project",
                        )
                        if project_id:
                            break
                        
                        if attempt == 0:
                            log.warning(
                                f"[Supervisor:{email}] ⚠️ Project creation failed — "
                                f"retrying in 3s..."
                            )
                            await asyncio.sleep(3)
                    except Exception as e:
                        if attempt == 0:
                            log.warning(
                                f"[Supervisor:{email}] ⚠️ Project creation error: {e} — "
                                f"retrying in 3s..."
                            )
                            await asyncio.sleep(3)
                        else:
                            log.error(
                                f"[Supervisor:{email}] ❌ Project creation failed after "
                                f"2 attempts: {e}"
                            )
            
            if project_id:
                account.set_project_id(project_id)
                log.info(f"[Supervisor:{email}] ✅ Project ready: {project_id}")
            else:
                log.error(
                    f"[Supervisor:{email}] ❌ No projectId after 2 attempts — "
                    f"account may not function correctly"
                )
                return
        
        # Navigate to project page
        project_id = account.project_id
        if project_id:
            log.info(f"[Supervisor:{email}] 📍 Navigating to project page...")
            await self.engine._navigate_to_project_page(account, project_id)

    async def _probe_submit(self) -> bool:
        """Probe: verify reCAPTCHA pipeline is functional before unblocking foremen.
        
        Validates that the extension can produce a valid reCAPTCHA token.
        Does NOT make server-side HTTP calls (those require browser cookies
        which are unavailable from Python). The actual submit by foreman-0
        will verify end-to-end acceptance.
        
        Returns:
            True if probe succeeded (valid token obtained), False otherwise.
        """
        account = self.account
        bridge = account.extension_bridge
        if not bridge:
            log.info(f"[Supervisor:{self.email}] No extension bridge — skipping probe")
            return True  # Can't probe without bridge
        
        for attempt in range(2):
            try:
                log.info(
                    f"[Supervisor:{self.email}] 🧪 Probe "
                    f"(attempt {attempt + 1}/2) — validating reCAPTCHA token..."
                )
                
                # Get a real reCAPTCHA token from extension
                token = await bridge.request_recaptcha(
                    self.email, timeout=15
                )
                if not token or len(token) < 1000:
                    log.warning(
                        f"[Supervisor:{self.email}] 🧪 Probe: reCAPTCHA token "
                        f"too short ({len(token) if token else 0} chars)"
                    )
                    if attempt < 1:
                        await asyncio.sleep(10)
                    continue
                
                # Token is valid (>1000 chars) — pipeline is functional
                log.info(
                    f"[Supervisor:{self.email}] 🧪 ✅ Probe OK — "
                    f"reCAPTCHA token valid ({len(token)} chars)"
                )
                self._first_submit_ok.set()  # Pipeline verified
                return True
                        
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning(
                    f"[Supervisor:{self.email}] 🧪 Probe exception: {e}"
                )
                if attempt < 1:
                    await asyncio.sleep(10)
        
        return False

    async def _handle_403(self, details: str):
        """Handle 403/reCAPTCHA errors — multi-phase recovery.
        
        Delegates to engine's existing cooldown + circuit breaker
        infrastructure, then waits for reCAPTCHA readiness.
        """
        account = self.account
        engine = self.engine
        
        # Record error for adaptive delay
        status = 403 if "403" in details else 500
        engine._burst_controller.record_error(self.email, status)
        
        # Circuit breaker tracking
        engine.record_circuit_403(self.email)
        
        # Cooldown — all workers on this account wait
        engine.set_account_cooldown(self.email, f"403/{details}")
        
        # Phase-based recovery (reuses engine methods)
        consecutive_403 = engine._circuit_consecutive_403.get(self.email, 0)
        
        if consecutive_403 <= 3:
            phase, count = 0, consecutive_403
        elif consecutive_403 <= 6:
            phase, count = 1, consecutive_403 - 3
        elif consecutive_403 <= 9:
            phase, count = 2, consecutive_403 - 6
        else:
            phase, count = 3, consecutive_403 - 9
        
        log.info(
            f"[Supervisor:{self.email}] 403 recovery: phase={phase}, "
            f"count={count}/3 (total={consecutive_403})"
        )
        
        if phase == 0:
            # Gentle: wait readiness + reload tabs
            if count <= 1:
                await engine._wait_for_recaptcha_ready(account, max_wait=15.0)
            elif count <= 2:
                if account.extension_bridge:
                    try:
                        await account.extension_bridge._trigger_refresh(
                            self.email, "Supervisor Phase 0", level="full"
                        )
                    except Exception:
                        pass
                await asyncio.sleep(15)
                await engine._wait_for_recaptcha_ready(account, max_wait=30.0)
        
        elif phase == 1:
            # Soft recovery
            if count <= 2:
                await engine._do_browser_recovery(account, "supervisor", "soft")
                await asyncio.sleep(8)
                await engine._wait_for_recaptcha_ready(account, max_wait=20.0)
        
        elif phase == 2:
            # Hard restart
            log.error(f"🔴 [Supervisor:{self.email}] Phase 2 → HARD browser restart")
            await engine._do_browser_recovery(account, "supervisor", "hard")
            await asyncio.sleep(10)
            await engine._wait_for_recaptcha_ready(account, max_wait=30.0)
        
        else:  # phase >= 3
            log.error(
                f"⛔ [Supervisor:{self.email}] All recovery phases exhausted "
                f"(consecutive_403={consecutive_403})"
            )
        
        # reCAPTCHA gate: wait for token readiness
        await self._recaptcha_gate()

    async def _handle_tab_freeze(self, details: str):
        """Handle tab freeze — escalating recovery."""
        account = self.account
        engine = self.engine
        
        freeze_count = getattr(self, '_freeze_count', 0) + 1
        self._freeze_count = freeze_count
        
        log.info(
            f"[Supervisor:{self.email}] Tab freeze recovery "
            f"(count={freeze_count})"
        )
        
        if freeze_count <= 2:
            # Escalation 1-2: Reload tabs
            if account.extension_bridge:
                try:
                    await account.extension_bridge._trigger_refresh(
                        self.email, "Supervisor tab_freeze", level="full"
                    )
                except Exception:
                    pass
            await asyncio.sleep(20)
        elif freeze_count <= 5:
            # Escalation 3-5: Soft browser recovery
            await engine._do_browser_recovery(account, "supervisor", "soft")
            await asyncio.sleep(10)
        else:
            # Escalation 6+: Hard browser restart
            log.error(f"🔴 [Supervisor:{self.email}] Tab freeze #{freeze_count} → HARD restart")
            await engine._do_browser_recovery(account, "supervisor", "hard")
            await asyncio.sleep(15)
        
        await self._recaptcha_gate()
    
    async def _recaptcha_gate(self):
        """Wait for reCAPTCHA readiness (token ≥ 1500).
        
        Blocks until extension reports ready. Retry every 3s.
        """
        account = self.account
        bridge = getattr(account, 'extension_bridge', None)
        
        if not bridge or not bridge.is_connected(self.email):
            log.warning(f"[Supervisor:{self.email}] No bridge, skipping reCAPTCHA gate")
            return
        
        for attempt in range(20):  # Max 60s
            try:
                ready = await bridge.check_recaptcha_ready(self.email)
                if ready:
                    log.info(f"[Supervisor:{self.email}] ✅ reCAPTCHA gate OPEN")
                    return
                log.info(f"[Supervisor:{self.email}] ⏳ reCAPTCHA gate CLOSED (attempt {attempt+1})")
            except Exception as e:
                log.warning(f"[Supervisor:{self.email}] reCAPTCHA check error: {e}")
            await asyncio.sleep(3)
        
        log.warning(f"[Supervisor:{self.email}] reCAPTCHA gate timeout (60s)")


class Engine:
    """Orchestration Engine - Connects all layers.
    
    Pipeline flow:
    1. Dispatcher.get_next_task()  →  get ready task from queue
    2. AccountManager.acquire_workers(n)  →  reserve worker capacity
    3. ProjectManager.get_or_create_project()  →  ensure project exists
    4. Worker.execute(task, account)  →  run API calls
    5. AccountManager.release_workers(n)  →  return workers to pool
    6. Dispatcher.complete_task() / fail_task()  →  update state
    """
    
    def __init__(
        self,
        account_manager: MultiAccountManager,
        dispatcher: Dispatcher,
        api_client: VEOApiClient,
        max_cpu_workers: Optional[int] = None,
        profiles_controller=None,
    ):
        self._account_manager = account_manager
        self._dispatcher = dispatcher
        self._api_client = api_client
        # Extension bridge — injected by AppController after creation (deferred due to init order)
        self._extension_bridge = None
        # A1/A2: ProjectManager is now per-account (CHỦ owns it)
        # No longer a shared singleton here
        self._frame_extractor = FrameExtractor()
        self._profiles_controller = profiles_controller  # For Variations copy recovery
        self._app_controller = None  # Set by AppController after creation (Fix A: remove chain)
        
        # Workers are now created per-account in start() — no global max_workers
        self._process_pool = ProcessPoolExecutor(
            max_workers=max_cpu_workers or os.cpu_count() or 4
        )
        
        self._workers: List[Worker] = []
        self._running = False
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()  # Set = running, Clear = paused
        self._pause_event.set()  # Start unpaused
        self._task_available = asyncio.Event()  # Bug 14: signal workers when new task arrives
        self._browser_recovery_locks: Dict[str, asyncio.Lock] = {}   # Per-account browser recovery dedup
        self._browser_recovery_epoch: Dict[str, int] = {}             # Tracks recovery generation
        self._account_rate_locks: Dict[str, asyncio.Lock] = {}  # Bug 13: per-account rate limiter
        # ── RC2 fix: Global cross-account submit throttle ──
        # Google detects coordinated submissions from same IP across accounts.
        # This lock ensures minimum 10s gap between ANY two submits.
        self._global_submit_lock = asyncio.Lock()
        self._global_last_submit_ts: float = 0.0
        self._GLOBAL_MIN_SUBMIT_GAP: float = 10.0  # seconds between any two submits
        # (Removed: _submitted_tasks queue — scheduler now owns full lifecycle directly)
        # Risk 7 fix: Max 2 concurrent API calls per account (any type: submit, poll, upload, upscale)
        # Prevents burst traffic when 4 workers poll/submit simultaneously
        self._account_api_semaphores: Dict[str, asyncio.Semaphore] = {}
        
        # Unified recovery state machine per account (soft-first, hard-last)
        # Phase 0: wait for readiness / reload tabs (NO Chrome kill)
        # Phase 1: soft recovery — navigate away/back (NO Chrome kill)
        # Phase 2: hard browser restart (last resort)
        # Phase 3: give up (all recovery tiers exhausted)
        # NOTE: Phase 0-3 logic is now handled by Smart Recovery (remedy_registry.py)
        # These dicts are kept for backward compat but no longer drive escalation.
        self._account_recovery_phase: Dict[str, int] = {}    # email → 0-3
        self._account_phase_403_count: Dict[str, int] = {}   # email → count within current phase
        self._account_403_last_epoch: Dict[str, int] = {}    # email → last epoch when 403 was counted
        self._account_resetting: Dict[str, bool] = {}        # email → True if recovery in progress
        
        # Smart Recovery: Credit Window for account health tracking
        from config.settings import get_settings as _get_recovery_settings
        _rs = _get_recovery_settings()
        self._credit_window = CreditWindow(
            passive_interval=getattr(_rs, 'credit_passive_interval', 5) * 60,  # min → sec
            probe_threshold=getattr(_rs, 'credit_probe_after', 3),
        )
        # Wire to dispatcher for credit-based task routing
        # (set_credit_window called after dispatcher is assigned in run())
        
        # Smart-Hide: per-account countdown to re-hide browser after 403 recovery
        # Set to 3 when Phase 2 shows browser; decremented on each success.
        # When reaches 0 → hide browser again.
        self._smart_hide_rehide_countdown: Dict[str, int] = {}
        
        # Hot-reload: queue for accounts added while engine is running
        self._pending_accounts: asyncio.Queue = asyncio.Queue()
        self._active_account_emails: set = set()  # Track which accounts have workers
        self._task_group = None  # Reference to active TaskGroup for hot-reload
        
        # Phase 2: Per-account supervisors (CHỦ layer)
        self._supervisors: Dict[str, AccountSupervisor] = {}  # email → supervisor
        
        # Settings reference (hot-apply from AppController)
        self._settings = None  # Set by AppController.start_processing()
        
        # Continuation settings (read from _settings at runtime, fallback to defaults)
        # These properties are accessed via getattr(self._settings, ...) for hot-apply
        
        # Callbacks for UI updates
        self._on_task_started: Optional[Callable] = None
        self._on_task_completed: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None
        self._on_connectivity_changed: Optional[Callable] = None  # (online: bool, latency_ms: int)
        
        # Bug 2 fix: Upload cache to prevent redundant image uploads
        # Key: (file_path, account_email) → mediaId
        # Same image used by multiple tasks only uploads once per account
        self._upload_cache: Dict[str, str] = {}
        self._upload_cache_lock = asyncio.Lock()
        
        # Phase 3A: Decoupled upscale queue (background processing)
        # Full DI: no engine reference passed — all dependencies injected explicitly
        from core.upscale_queue import UpscaleQueue
        self._upscale_queue = UpscaleQueue(
            dispatcher=self._dispatcher,
            api_client=self._api_client,
            poll_fn=self._poll_upscale,               # async method
            download_fn=self._download_outputs,       # async method
            wait_recaptcha_fn=self._wait_for_recaptcha_ready,
            sync_status_fn=self._sync_overall_upscale_status,
            semaphore_fn=self._get_upscale_api_semaphore,
            rate_locks=self._account_rate_locks,       # shared dict ref
            # Account & cooldown (replaces engine public API)
            get_account_fn=self.get_account,
            get_all_accounts_fn=self.get_all_accounts,
            is_on_cooldown_fn=self.is_account_on_cooldown,
            wait_cooldown_fn=self.wait_for_cooldown,
            set_cooldown_fn=self.set_account_cooldown,
            clear_cooldown_fn=self.clear_account_cooldown,
            fix_client_data_fn=self.fix_client_data,
            should_wait_fn=self.should_upscale_wait,
            # Fix C: CircuitBreaker gate — wait for circuit CLOSED before submit
            wait_for_circuit_fn=self._wait_for_circuit,
            # V6: Report upscale 403 to engine's circuit breaker
            record_circuit_403_fn=self.record_circuit_403,
            on_completed=lambda task: self._on_task_completed(task) if self._on_task_completed else None,
            profiles_controller=self._profiles_controller,
            extension_bridge=self._extension_bridge,
        )
        
        # Manifest manager: portable project data alongside output videos
        self._manifest = ManifestManager()
        
        # Phase 4A: reCAPTCHA token pre-fetch pool
        from core.recaptcha_pool import RecaptchaPool
        self._recaptcha_pool = RecaptchaPool()
        # Wire skip check: don't pre-fetch tokens for accounts on cooldown or circuit OPEN
        self._recaptcha_pool.set_skip_check(
            lambda email: (
                self.is_account_on_cooldown(email) or 
                self._circuit_state.get(email, "closed") != "closed"
            )
        )
        
        # Phase 4B: Adaptive anti-detect delay
        from core.adaptive_burst import AdaptiveBurstController
        _ad_min = getattr(self._settings, 'anti_detect_delay_min', 3.0)
        _ad_max = getattr(self._settings, 'anti_detect_delay_max', 8.0)
        self._burst_controller = AdaptiveBurstController(
            min_delay=_ad_min,
            max_delay=_ad_max,
            initial_delay=(_ad_min + _ad_max) / 2,
        )
        
        # Fix G6: Inject burst_controller into upscale queue for anti-detect delay
        self._upscale_queue._burst_controller = self._burst_controller
        
        # Wire burst controller into account manager for health-score 403 penalty
        if hasattr(self._account_manager, 'set_burst_controller'):
            self._account_manager.set_burst_controller(self._burst_controller)
        
        # NOTE: Per-account submit serialization is handled by _account_rate_locks
        # (Dict[str, asyncio.Lock], initialized in _create_internal_state L367).
        # Each foreman acquires the lock, waits burst_controller.wait() delay INSIDE
        # the lock, then submits — ensuring only 1 submit at a time per account.
        # Different accounts have separate locks → fully independent timing.
        
        # Performance counters (read by AppController._push_performance)
        self._download_count = 0   # Total successful downloads
        self._error_count = 0      # Total task failures
        
        # Bug 4 fix: Per-task download lock — prevents concurrent duplicate downloads
        self._download_locks: Dict[str, asyncio.Lock] = {}
        
        # Account-level cooldown: shared between engine workers + upscale queue
        # When ANY 403 hits, the account enters cooldown. Both prompt submission
        # and upscale submit check this before calling API.
        # Issue #3: asyncio.Event for efficient multi-waiter support —
        # all waiters wake simultaneously when cooldown expires.
        self._account_cooldowns: Dict[str, datetime] = {}       # email → cooldown_until
        self._account_cooldown_backoff: Dict[str, int] = {}     # email → consecutive 403 count
        self._cooldown_events: Dict[str, asyncio.Event] = {}    # email → Event (set=clear)
        self._cooldown_timers: Dict[str, asyncio.TimerHandle] = {}  # email → scheduled clear
        
        # Circuit breaker (cầu dao): per-account extension health gate
        # CLOSED = extension healthy → workers run normally
        # OPEN   = extension dead / 5+ consecutive 403 → ALL workers sleep
        # HALF_OPEN = extension just reconnected → 1 worker tries, rest wait
        self._circuit_state: Dict[str, str] = {}            # email → "closed"|"open"|"half_open"
        self._circuit_open_since: Dict[str, float] = {}     # email → time.time() when opened
        self._circuit_consecutive_403: Dict[str, int] = {}  # email → count without success
        self._circuit_events: Dict[str, asyncio.Event] = {} # email → Event (set=closed/healthy)
        self._circuit_half_open_lock: Dict[str, asyncio.Lock] = {}  # email → only 1 probe worker
        
        # Workload priority: controls resource allocation between prompt and upscale
        # '720p_priority' = upscale queue pauses until ALL prompts submitted + downloaded (default)
        # 'upscale_priority' = worker does inline upscale before freeing slot
        # Fix G1: Default '720p_priority' — all 720p downloads complete before upscale,
        # preventing reCAPTCHA token contention between UpscaleQueue and workers
        self._workload_priority = '720p_priority'
        
        # Pre-warm: proactive reCAPTCHA soft recovery after idle period
        # Prevents 403 cascade by resetting reCAPTCHA context before first submit
        self._last_successful_submit: Dict[str, float] = {}  # email → timestamp
        self._prewarm_stats: Dict[str, dict] = {}  # email → {count, last_idle_secs, last_time}
        
        # Tab Keepalive tracking (read by get_dashboard_stats)
        self._keepalive_last_ping_count: int = 0
        self._keepalive_last_ping_time: float = 0.0
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()
    
    def _get_api_semaphore(self, email: str) -> asyncio.Semaphore:
        """Get or create per-account API semaphore (for main pipeline).
        
        Limits max concurrent API calls (submit, poll, upload)
        to 2 per account, preventing burst traffic that triggers 403.
        """
        if email not in self._account_api_semaphores:
            self._account_api_semaphores[email] = asyncio.Semaphore(2)
        return self._account_api_semaphores[email]
    
    def _get_upscale_api_semaphore(self, email: str) -> asyncio.Semaphore:
        """Get or create per-account API semaphore for upscale operations.
        
        Bug #14 fix: Separate from main semaphore so upscale polls don't
        compete with main pipeline polls for the same 2 permits.
        Limit: 3 concurrent upscale API calls per account.
        """
        if not hasattr(self, '_account_upscale_semaphores'):
            self._account_upscale_semaphores = {}
        if email not in self._account_upscale_semaphores:
            self._account_upscale_semaphores[email] = asyncio.Semaphore(3)
        return self._account_upscale_semaphores[email]
    
    # ── Account Cooldown: shared 403 backoff (Issue #3: Event-based) ──
    
    def _get_cooldown_event(self, email: str) -> asyncio.Event:
        """Get or create per-account cooldown Event."""
        if email not in self._cooldown_events:
            evt = asyncio.Event()
            evt.set()  # Default: no cooldown → event set (waiters pass through)
            self._cooldown_events[email] = evt
        return self._cooldown_events[email]
    
    def set_account_cooldown(self, email: str, reason: str = "403"):
        """Set cooldown for an account after 403 error.
        
        Exponential backoff: 30s → 60s → 120s → 180s max.
        Called by both engine workers and upscale queue.
        Event-based: all waiters re-block when cooldown is extended.
        """
        count = self._account_cooldown_backoff.get(email, 0) + 1
        self._account_cooldown_backoff[email] = count
        
        delay = min(30 * (2 ** (count - 1)), 180)  # 30, 60, 120, 180 cap
        self._account_cooldowns[email] = datetime.now() + timedelta(seconds=delay)
        
        # Block all waiters (clear event)
        evt = self._get_cooldown_event(email)
        evt.clear()
        
        # Cancel any previous timer, schedule auto-clear
        old_timer = self._cooldown_timers.pop(email, None)
        if old_timer:
            old_timer.cancel()
        
        try:
            loop = asyncio.get_event_loop()
            timer = loop.call_later(delay, self._auto_clear_cooldown, email)
            self._cooldown_timers[email] = timer
        except RuntimeError:
            pass  # No event loop — fallback to poll-based in wait_for_cooldown
        
        log.warning(
            f"[Cooldown] {email}: {reason} → cooldown {delay}s "
            f"(consecutive #{count})"
        )
    
    def _auto_clear_cooldown(self, email: str):
        """Auto-clear cooldown and wake all waiters when timer expires."""
        self._account_cooldowns.pop(email, None)
        self._cooldown_timers.pop(email, None)
        # Fix #1: Decay backoff by 1 on timer expiry (not full reset).
        # Full reset happens on success (clear_account_cooldown).
        # Without this, consecutive failures escalate 30→60→120→180s
        # and only a success can break the spiral.
        current = self._account_cooldown_backoff.get(email, 0)
        if current > 0:
            self._account_cooldown_backoff[email] = max(0, current - 1)
        evt = self._cooldown_events.get(email)
        if evt:
            evt.set()  # Wake all waiters simultaneously
    
    def is_account_on_cooldown(self, email: str) -> bool:
        """Check if account is on cooldown. Returns False if expired."""
        until = self._account_cooldowns.get(email)
        if not until:
            return False
        if datetime.now() >= until:
            # Expired — clean up
            self._auto_clear_cooldown(email)
            return False
        return True
    
    async def wait_for_cooldown(self, email: str):
        """Wait until account cooldown expires. No-op if not on cooldown.
        
        Wakes immediately if _stop_event is set (engine stopping).
        
        ★ TAB KEEPALIVE: During long cooldowns (60-120s), Chrome freezes
        inactive tabs. This kills the reCAPTCHA widget → 538-char tokens
        → 403 → longer cooldown (death spiral). We prevent this by
        sending simulate_activity every 20s to keep the tab alive.
        """
        if not self.is_account_on_cooldown(email):
            return
        
        remaining = 0
        until = self._account_cooldowns.get(email)
        if until:
            remaining = max(0, (until - datetime.now()).total_seconds())
        log.info(f"[Cooldown] {email}: waiting {remaining:.0f}s (with tab keepalive)...")
        
        # ★ Keepalive loop: wait in 20s chunks, pinging tab each iteration
        KEEPALIVE_INTERVAL = 20  # seconds between tab pings
        
        while self.is_account_on_cooldown(email) and not self._stop_event.is_set():
            until = self._account_cooldowns.get(email)
            if not until:
                break
            chunk = min(KEEPALIVE_INTERVAL, max(0, (until - datetime.now()).total_seconds()) + 1)
            
            evt = self._get_cooldown_event(email)
            stop_task = asyncio.create_task(self._stop_event.wait())
            cooldown_task = asyncio.create_task(evt.wait())
            try:
                done, pending = await asyncio.wait(
                    {stop_task, cooldown_task},
                    timeout=chunk,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                if self._stop_event.is_set():
                    log.info(f"[Cooldown] {email}: interrupted by stop signal")
                    return
                if cooldown_task in done:
                    break  # Cooldown cleared early
            except asyncio.TimeoutError:
                pass
            finally:
                for t in (stop_task, cooldown_task):
                    if not t.done():
                        t.cancel()
            
            # ★ Tab keepalive: prevent Chrome from freezing the VEO tab
            if self.is_account_on_cooldown(email) and not self._stop_event.is_set():
                account = next(
                    (a for a in self._account_manager._accounts if a.email == email),
                    None
                )
                bridge = getattr(account, 'extension_bridge', None) if account else None
                if bridge and bridge.is_connected(email):
                    try:
                        await bridge.simulate_activity(email, timeout=3.0)
                        cd_left = 0
                        u = self._account_cooldowns.get(email)
                        if u:
                            cd_left = max(0, (u - datetime.now()).total_seconds())
                        log.debug(
                            f"[Cooldown] {email}: tab keepalive ping OK "
                            f"({cd_left:.0f}s remaining)"
                        )
                    except Exception:
                        pass  # Best-effort — tab may still be alive via heartbeat
        
        if not self.is_account_on_cooldown(email):
            self._auto_clear_cooldown(email)
    
    def clear_account_cooldown(self, email: str):
        """Clear cooldown on successful API call (reset backoff counter)."""
        self._account_cooldowns.pop(email, None)
        self._account_cooldown_backoff.pop(email, None)
        # Cancel timer and wake waiters
        old_timer = self._cooldown_timers.pop(email, None)
        if old_timer:
            old_timer.cancel()
        evt = self._cooldown_events.get(email)
        if evt:
            evt.set()
    
    async def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep for `seconds`, but wake immediately if engine is stopping.
        
        Returns True if interrupted by stop signal, False if slept fully.
        """
        if self._stop_event.is_set():
            return True
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True  # Stop event fired
        except asyncio.TimeoutError:
            return False  # Slept fully
    
    # ── Circuit Breaker: Extension Health Gate ──
    
    # ── Account Readiness Gate ──
    
    async def _wait_for_account_ready(self, account, timeout: float = 30.0):
        """Block until account has valid x-client-data from extension.
        
        Chrome's Variations Service needs ~5-15s after launch to generate
        x-client-data. Submitting before this causes guaranteed 403.
        
        Uses get_browser_headers() which reads from ExtensionBridge cache
        (zero lag) instead of session.client_data (2s debounce delay).
        """
        import time
        start = time.monotonic()
        from config.constants import MIN_VALID_XCD
        MIN_GOOD = MIN_VALID_XCD  # Shared constant (50)
        email = account.email
        
        # Throttle: avoid 30+ identical debug lines during readiness wait
        _xcd_last_log = [0.0]  # mutable for closure
        
        def _get_xcd() -> str:
            """Read x-client-data: bridge cache → direct bridge query → session fallback."""
            has_method = hasattr(account, 'get_browser_headers')
            has_bridge = bool(getattr(account, '_extension_bridge', None))
            
            # Path 1: AccountManager.get_browser_headers() (reads bridge cache)
            headers = account.get_browser_headers() if has_method else {}
            xcd = headers.get('x-client-data', '') or ''
            if xcd and len(xcd) >= MIN_GOOD:
                return xcd
            
            # Path 2: Direct bridge cache query (failsafe if AM bridge ref lost)
            bridge = getattr(account, '_extension_bridge', None)
            if bridge:
                cached = bridge.get_cached_headers(email, max_age_seconds=0)  # any age OK
                if cached:
                    xcd2 = cached.get('x-client-data', '') or ''
                    if xcd2 and len(xcd2) >= MIN_GOOD:
                        log.debug(f"[Foreman:{email}] _get_xcd: direct bridge→{len(xcd2)} chars (AM path returned {len(xcd)} chars)")
                        return xcd2
            
            # Path 3: Session fallback (debounced value)
            xcd3 = getattr(account.session, 'client_data', '') or ''
            # Throttle debug log: once per 5s to reduce noise
            now = time.monotonic()
            if now - _xcd_last_log[0] >= 5.0:
                _xcd_last_log[0] = now
                log.debug(f"[Foreman:{email}] _get_xcd: session fallback→{len(xcd3)} chars (bridge={has_bridge}, AM→{len(xcd)} chars)")
            return xcd3 if len(xcd3) > len(xcd) else (xcd or xcd3)
        
        # Fast path: already have good data
        xcd = _get_xcd()
        if len(xcd) >= MIN_GOOD:
            return
        
        log.info(f"[Foreman:{email}] Waiting for x-client-data (current: {len(xcd)} chars)...")
        
        while time.monotonic() - start < timeout:
            if self._stop_event.is_set():
                return
            xcd = _get_xcd()
            if len(xcd) >= MIN_GOOD:
                elapsed = time.monotonic() - start
                log.info(f"[Foreman:{email}] ✅ Account ready (x-client-data: {len(xcd)} chars, waited {elapsed:.1f}s)")
                return
            await self._interruptible_sleep(1.0)
        
        xcd = _get_xcd()
        log.warning(
            f"[Foreman:{email}] ⚠️ Readiness timeout ({timeout:.0f}s) — "
            f"x-client-data still {len(xcd)} chars. First submit may 403."
        )
    
    def _execute_js_on_account(self, account, js_expression: str, timeout: float = 10.0):
        """Execute JS on account's debug browser page (thread-safe).
        
        Uses profiles_controller.execute_js_on_debug_browser() which marshals
        the call through the command queue to the correct Playwright thread.
        Falls back to browser_session._page if profiles_controller unavailable.
        
        Returns result or None on failure. This is SYNCHRONOUS.
        """
        email = account.email
        pc = getattr(account, '_profiles_controller', None)
        if pc:
            return pc.execute_js_on_debug_browser(email, js_expression, timeout=timeout)
        # Fallback: direct page.evaluate (only works if called from same thread)
        session = getattr(account, '_browser_session', None)
        if session and session.is_ready:
            page = getattr(session, '_page', None)
            if page:
                return page.evaluate(js_expression)
        return None
    
    async def _execute_js_on_account_async(self, account, js_expression: str, timeout: float = 10.0):
        """Async wrapper for _execute_js_on_account (runs in executor to avoid blocking)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._execute_js_on_account, account, js_expression, timeout
        )
    
    async def _ensure_runtime_project(self, account, title: str = "My Video Project"):
        """Ensure account has a project — shared by Supervisor startup + foreman runtime.
        
        Steps:
        1. Try to reuse existing project via get_projects()
        2. Create new project with retry if no existing one
        3. Navigate to project page if newly created
        
        Args:
            account: AccountManager instance
            title: Project title (use task.project_name or generic default)
        """
        email = account.email
        trpc_client = None
        if account._browser_session and account._browser_session.is_ready:
            trpc_client = TRPCClient(account._browser_session._page)
        
        project_id = None
        
        # Step 1: Reuse existing project
        if trpc_client:
            try:
                projects = await trpc_client.get_projects()
                if projects:
                    project_id = projects[0].get("projectId")
                    if project_id:
                        log.info(f"[Engine:{email}] ♻️ Reusing existing project: {project_id}")
            except Exception:
                pass
        
        # Step 2: Create new with retry
        if not project_id:
            for attempt in range(2):
                try:
                    project_id = await account.project_manager.get_or_create_project(
                        email=email,
                        access_token=account.get_access_token(),
                        api_client=self._api_client,
                        trpc_client=trpc_client,
                        title=title,
                    )
                    if project_id:
                        break
                    if attempt == 0:
                        log.warning(f"[Engine:{email}] ⚠️ Project creation failed — retrying in 3s...")
                        await asyncio.sleep(3)
                except Exception as e:
                    if attempt == 0:
                        log.warning(f"[Engine:{email}] ⚠️ Project error: {e} — retrying in 3s...")
                        await asyncio.sleep(3)
                    else:
                        log.error(f"[Engine:{email}] ❌ Project creation failed after 2 attempts: {e}")
        
        if project_id:
            account.set_project_id(project_id)
            # Navigate if not already on this project page
            if self._navigated_project.get(email) != project_id:
                await self._navigate_to_project_page(account, project_id)
        else:
            log.warning(
                f"⚠️ No projectId for {email} — generation requests may fail"
            )
    
    async def _check_app_availability(self, account):
        """Fix 3: checkAppAvailability — HAR-verified startup signal.
        
        HAR evidence: Real browsers call POST aisandbox-pa/v1:checkAppAvailability
        immediately on page load, before any submit.
        Body: {"clientContext": {"tool": "PINHOLE"}}
        Response: {"availabilityState": "AVAILABLE"}
        
        HAR-verified corrections:
        - Content-Type: 'text/plain;charset=UTF-8' (NOT application/json)
        - x-goog-api-key header required (NOT in URL)
        - NO credentials:'include' (cross-site → CORS error)
        - Only called once on page load, NOT in heartbeat
        """
        email = account.email
        try:
            result = await self._execute_js_on_account_async(account, """
                fetch('https://aisandbox-pa.googleapis.com/v1:checkAppAvailability', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'text/plain;charset=UTF-8',
                        'x-goog-api-key': 'AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY'
                    },
                    body: JSON.stringify({clientContext: {tool: 'PINHOLE'}})
                }).then(r => r.json()).catch(e => ({error: e.message}))
            """)
            if result is None:
                log.warning(f"[Foreman:{email}] checkAppAvailability: no browser page available")
                return
            state = result.get('availabilityState', 'UNKNOWN') if isinstance(result, dict) else 'UNKNOWN'
            if state == 'AVAILABLE':
                log.info(f"[Foreman:{email}] ✅ checkAppAvailability: AVAILABLE")
            else:
                log.warning(f"[Foreman:{email}] checkAppAvailability: {result}")
        except Exception as e:
            log.warning(f"[Foreman:{email}] checkAppAvailability failed: {e}")

    # Track which project page each account is currently on
    _navigated_project: dict = {}  # email → project_id

    async def _navigate_to_project_page(self, account, project_id: str):
        """Navigate the browser tab to the specific project page.

        Skips if browser is already on the correct project page.
        Detects locale prefix (e.g. /vi/) from the current browser URL
        and includes it in the target URL.

        HAR evidence: Real browsers navigate to /tools/flow/project/{id}
        before submitting. This ensures:
        1. flow.projectInitialData loads (4.2s server load)
        2. auth/session recheck
        3. reCAPTCHA context is tied to the correct project page
        """
        email = account.email

        # Skip if already on this project page
        if self._navigated_project.get(email) == project_id:
            log.debug(f"[Foreman:{email}] Already on project page {project_id} — skipping navigation")
            return

        # Detect locale prefix from current browser URL
        # e.g. labs.google/fx/vi/tools/flow → locale = "vi/"
        locale_prefix = ""
        bridge = getattr(account, 'extension_bridge', None)
        if bridge and bridge.is_connected(email):
            try:
                import re
                # Get current tab URL from the extension's tabState
                conn = bridge._find_connection(email)
                if conn and hasattr(conn, '_registered_email'):
                    # Check cached tab URL from bridge
                    for cid, c in bridge._connections.items():
                        if getattr(c, '_registered_email', None) == email:
                            tab_url = getattr(c, '_tab_url', '') or ''
                            match = re.search(r'labs\.google/fx/([a-z]{2}(?:-[a-z]{2})?)/tools', tab_url)
                            if match:
                                locale_prefix = f"{match.group(1)}/"
                                log.debug(f"[Foreman:{email}] Detected locale: {locale_prefix}")
                            break
            except Exception:
                pass

        # If we couldn't detect locale from bridge, try from profiles_controller
        if not locale_prefix:
            import re
            pc = getattr(account, '_profiles_controller', None) or \
                 getattr(self, '_profiles_controller', None)
            if pc:
                try:
                    current_url = getattr(pc, '_last_url', {}).get(email, '')
                    if current_url:
                        match = re.search(r'labs\.google/fx/([a-z]{2}(?:-[a-z]{2})?)/tools', current_url)
                        if match:
                            locale_prefix = f"{match.group(1)}/"
                except Exception:
                    pass

        # Fallback: use "vi/" as default locale (most common for this user)
        if not locale_prefix:
            locale_prefix = "vi/"
            log.debug(f"[Foreman:{email}] Using default locale: {locale_prefix}")

        project_url = f"https://labs.google/fx/{locale_prefix}tools/flow/project/{project_id}"

        nav_success = False

        if bridge and bridge.is_connected(email):
            try:
                log.info(f"[Foreman:{email}] 📍 Navigating to project page: {project_url}")
                result = await bridge.navigate_to_url(email, project_url, timeout=35.0)
                
                # Level 1-2: Retry bridge navigation once on failure
                if not result or not result.get('success'):
                    error = result.get('error', 'unknown') if result else 'no_result'
                    log.warning(
                        f"[Foreman:{email}] ⚠️ Navigation failed ({error}) — retrying in 3s..."
                    )
                    await asyncio.sleep(3)
                    result = await bridge.navigate_to_url(email, project_url, timeout=35.0)
                
                if result and result.get('success'):
                    nav_success = True
                else:
                    error = result.get('error', 'unknown') if result else 'no_result'
                    log.warning(
                        f"[Foreman:{email}] ⚠️ Bridge navigation failed 2x ({error})"
                    )
                    
                    # Level 3: JS fallback — window.location.href
                    try:
                        log.info(f"[Foreman:{email}] 📍 Trying JS fallback navigation...")
                        await self._execute_js_on_account_async(
                            account, f"window.location.href = '{project_url}'"
                        )
                        await asyncio.sleep(8)
                        nav_success = True
                        log.info(f"[Foreman:{email}] ✅ JS fallback navigation OK")
                    except Exception as js_err:
                        log.warning(f"[Foreman:{email}] JS fallback also failed: {js_err}")
                    
                    # Level 4: Browser restart + re-navigate
                    if not nav_success:
                        try:
                            log.warning(
                                f"[Foreman:{email}] 🔄 Escalating to browser restart "
                                f"after 3 navigation failures..."
                            )
                            ok = await account.restart_browser()
                            if ok:
                                log.info(f"[Foreman:{email}] ✅ Browser restarted — re-navigating...")
                                await asyncio.sleep(5)
                                # Re-check bridge after restart
                                if bridge and bridge.is_connected(email):
                                    result = await bridge.navigate_to_url(
                                        email, project_url, timeout=35.0
                                    )
                                    if result and result.get('success'):
                                        nav_success = True
                                        log.info(
                                            f"[Foreman:{email}] ✅ Post-restart navigation OK"
                                        )
                            else:
                                log.error(f"[Foreman:{email}] ❌ Browser restart failed")
                        except Exception as restart_err:
                            log.error(
                                f"[Foreman:{email}] Browser restart escalation failed: {restart_err}"
                            )
                
            except Exception as e:
                log.warning(f"[Foreman:{email}] Project page navigation failed: {e}")
        else:
            # No extension: use execute_js directly
            try:
                log.info(f"[Foreman:{email}] 📍 Navigating via JS: {project_url}")
                await self._execute_js_on_account_async(
                    account, f"window.location.href = '{project_url}'"
                )
                await asyncio.sleep(8)
                nav_success = True
                log.info(f"[Foreman:{email}] ✅ Project page loaded (JS fallback)")
            except Exception as e:
                log.warning(f"[Foreman:{email}] Project page navigation failed (JS): {e}")

        if nav_success:
            self._navigated_project[email] = project_id
            
            # Wait for content script re-inject + reCAPTCHA widget init
            import time as _time
            wait_start = _time.monotonic()
            max_wait = 15  # seconds
            recaptcha_ready = False
            
            if bridge and bridge.is_connected(email):
                for attempt in range(max_wait // 2):
                    await asyncio.sleep(2)
                    try:
                        ready_result = await bridge.check_recaptcha_ready(email, timeout=5.0)
                        if ready_result and ready_result.get('ready'):
                            elapsed = _time.monotonic() - wait_start
                            log.info(
                                f"[Foreman:{email}] ✅ reCAPTCHA ready on project page "
                                f"({elapsed:.1f}s after navigation)"
                            )
                            recaptcha_ready = True
                            break
                    except Exception:
                        pass
            
            if not recaptcha_ready:
                elapsed = _time.monotonic() - wait_start
                log.warning(
                    f"[Foreman:{email}] ⚠️ reCAPTCHA not ready after {elapsed:.1f}s "
                    f"post-navigation — foreman will handle via pre-submit check"
                )
        else:
            log.error(
                f"[Foreman:{email}] ❌ All 4 navigation levels failed — "
                f"account may not function correctly"
            )
    
    CIRCUIT_TRIP_THRESHOLD = 5    # consecutive 403s to trip breaker
    CIRCUIT_MONITOR_INTERVAL = 10  # seconds between health checks
    
    def _get_circuit_event(self, email: str) -> asyncio.Event:
        """Get or create circuit breaker event (set=healthy, clear=tripped)."""
        if email not in self._circuit_events:
            evt = asyncio.Event()
            evt.set()  # Default: healthy → workers pass through
            self._circuit_events[email] = evt
        return self._circuit_events[email]
    
    def _get_half_open_lock(self, email: str) -> asyncio.Lock:
        """Get or create half-open probe lock."""
        if email not in self._circuit_half_open_lock:
            self._circuit_half_open_lock[email] = asyncio.Lock()
        return self._circuit_half_open_lock[email]
    
    def _trip_circuit_breaker(self, email: str, reason: str):
        """OPEN breaker — all workers for this account sleep.
        
        Like cutting power to a production line: all workers stop
        until the scheduler verifies power (extension) is back.
        """
        import time
        current = self._circuit_state.get(email, "closed")
        if current == "open":
            return  # Already tripped
        
        self._circuit_state[email] = "open"
        # Only reset open_since when tripping from closed state.
        # When re-tripping from half_open (probe failed), preserve the original
        # timestamp so exponential backoff counts from the FIRST trip, not each probe.
        if current != "half_open":
            self._circuit_open_since[email] = time.time()
        
        # Block all waiters
        evt = self._get_circuit_event(email)
        evt.clear()
        
        log.warning(
            f"⚡ [CircuitBreaker] {email}: OPEN — {reason}. "
            f"All workers for this account will sleep until extension reconnects."
        )
        
        # DD4: Signal supervisor to abort foreman → tasks requeued
        supervisor = self._supervisors.get(email)
        if supervisor:
            supervisor.abort_foreman()
            log.info(f"[DD4] {email}: Foreman abort signal sent")
    
    def _close_circuit_breaker(self, email: str):
        """CLOSE breaker — wake all sleeping workers.
        
        Power restored: all workers resume.
        """
        current = self._circuit_state.get(email, "closed")
        if current == "closed":
            return  # Already closed
        
        self._circuit_state[email] = "closed"
        self._circuit_open_since.pop(email, None)
        self._circuit_consecutive_403[email] = 0
        
        # Wake all waiters
        evt = self._get_circuit_event(email)
        evt.set()
        
        log.info(f"✅ [CircuitBreaker] {email}: CLOSED — extension healthy, workers resuming.")
        
        # DD4: Clear abort signal → foreman can resume
        supervisor = self._supervisors.get(email)
        if supervisor:
            supervisor.clear_abort()
            log.info(f"[DD4] {email}: Foreman abort cleared")
    
    def _half_open_circuit_breaker(self, email: str):
        """HALF-OPEN: extension reconnected, allow 1 probe request."""
        current = self._circuit_state.get(email, "closed")
        if current != "open":
            return
        
        self._circuit_state[email] = "half_open"
        # Wake waiters — but half_open_lock ensures only 1 gets through
        evt = self._get_circuit_event(email)
        evt.set()
        
        log.info(f"🟡 [CircuitBreaker] {email}: HALF-OPEN — allowing 1 probe request.")
    
    def record_circuit_403(self, email: str):
        """Record a 403 error. Trips breaker after CIRCUIT_TRIP_THRESHOLD consecutive failures."""
        count = self._circuit_consecutive_403.get(email, 0) + 1
        self._circuit_consecutive_403[email] = count
        
        if count >= self.CIRCUIT_TRIP_THRESHOLD:
            self._trip_circuit_breaker(
                email,
                f"{count} consecutive 403 errors (threshold={self.CIRCUIT_TRIP_THRESHOLD})"
            )
    
    def record_circuit_success(self, email: str):
        """Record a success. Closes breaker and resets 403 counter."""
        self._circuit_consecutive_403[email] = 0
        state = self._circuit_state.get(email, "closed")
        if state in ("open", "half_open"):
            self._close_circuit_breaker(email)
    
    async def _wait_for_circuit(self, email: str):
        """Block until circuit breaker closes (extension healthy).
        
        All workers call this before each retry attempt. If breaker is OPEN,
        they sleep here. When extension reconnects, monitor wakes them.
        
        In HALF-OPEN state, only 1 worker gets through (probe), rest wait.
        """
        state = self._circuit_state.get(email, "closed")
        if state == "closed":
            return  # Fast path: healthy
        
        if state == "open":
            log.info(f"⏸️ [CircuitBreaker] Worker waiting — {email} breaker is OPEN")
            evt = self._get_circuit_event(email)
            # Wait for breaker OR stop signal
            stop_task = asyncio.create_task(self._stop_event.wait())
            breaker_task = asyncio.create_task(evt.wait())
            try:
                await asyncio.wait(
                    {stop_task, breaker_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                for t in (stop_task, breaker_task):
                    if not t.done():
                        t.cancel()
            if self._stop_event.is_set():
                return
            state = self._circuit_state.get(email, "closed")
        
        if state == "half_open":
            # Only 1 worker gets through as probe
            lock = self._get_half_open_lock(email)
            if lock.locked():
                log.debug(f"[CircuitBreaker] {email}: probe in progress, waiting...")
                evt = self._get_circuit_event(email)
                evt.clear()
                # Wait for breaker OR stop signal
                stop_task = asyncio.create_task(self._stop_event.wait())
                breaker_task = asyncio.create_task(evt.wait())
                try:
                    await asyncio.wait(
                        {stop_task, breaker_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    for t in (stop_task, breaker_task):
                        if not t.done():
                            t.cancel()
    
    def _check_extension_health(self, account) -> bool:
        """Check if extension is connected for this account.
        
        Used by background monitor to detect extension disconnect.
        """
        bridge = getattr(account, 'extension_bridge', None) or self._extension_bridge
        if not bridge:
            return False
        try:
            return bridge.is_connected(account.email)
        except Exception:
            return False
    
    async def _circuit_breaker_monitor(self):
        """Background task: check extension health, auto-trip/close breaker.
        
        Runs alongside workers in the TaskGroup. Every 10s, checks each
        account's extension connectivity. If disconnected for >30s, trips
        breaker. If reconnected while open, transitions to half-open
        WITH exponential backoff — waits longer before probing as
        consecutive 403 count increases.
        """
        import time
        log.info("[CircuitBreaker] Monitor started")
        while self._running and not self._stop_event.is_set():
            try:
                for account in self._account_manager._accounts:
                    if not account.is_enabled:
                        continue
                    
                    email = account.email
                    healthy = self._check_extension_health(account)
                    state = self._circuit_state.get(email, "closed")
                    
                    if healthy and state == "open":
                        # Exponential backoff: wait longer before probing
                        # as consecutive 403 count increases
                        consecutive = self._circuit_consecutive_403.get(email, 0)
                        open_since = self._circuit_open_since.get(email, 0)
                        elapsed = time.time() - open_since if open_since else 999
                        
                        # Backoff: 30s base, doubles per 5 failures, max 600s (10min)
                        backoff_tier = min(consecutive // 5, 5)  # 0-5 tiers
                        min_open_secs = 30 * (2 ** backoff_tier)  # 30, 60, 120, 240, 480, 600
                        min_open_secs = min(min_open_secs, 600)
                        
                        if elapsed < min_open_secs:
                            remaining = int(min_open_secs - elapsed)
                            log.debug(
                                f"[CircuitBreaker] {email}: waiting {remaining}s more "
                                f"before probe (consecutive={consecutive}, backoff={min_open_secs}s)"
                            )
                            continue  # Don't transition yet
                        
                        # Extension reconnected & backoff expired → half-open
                        log.info(
                            f"[CircuitBreaker] {email}: backoff expired "
                            f"(waited {int(elapsed)}s, required {min_open_secs}s, "
                            f"consecutive_403={consecutive})"
                        )
                        self._half_open_circuit_breaker(email)
                    elif healthy and state == "half_open":
                        # Probe period — check if a probe succeeded
                        # (record_circuit_success handles closing)
                        pass
                    elif not healthy and state == "closed":
                        # Extension just disconnected — trip immediately
                        self._trip_circuit_breaker(email, "extension disconnected")
            except Exception as e:
                log.debug(f"[CircuitBreaker] Monitor error: {e}")
            
            await asyncio.sleep(10)  # Check every 10s
        
        log.info("[CircuitBreaker] Monitor stopped")
    
    async def _credit_recovery_timer(self):
        """Background task: passive credit recovery for suspended accounts.
        
        Every 60s, calls CreditWindow.tick() which:
        1. Grants +1 credit per 5min to suspended accounts
        2. Returns accounts that became probe-ready (credits > threshold)
        
        For probe-ready accounts, runs a lightweight health check.
        If healthy → reactivate with slow start.
        """
        log.info("[CreditWindow] Recovery timer started")
        from core.remedy_registry import verify_account_health
        
        while self._running and not self._stop_event.is_set():
            try:
                await asyncio.sleep(60)  # Check every 60s
                
                if not self._running:
                    break
                
                # Passive credit recovery
                probe_ready = self._credit_window.tick()
                
                # Attempt to probe any accounts that became ready
                for email in probe_ready:
                    account = self.get_account(email)
                    if not account:
                        continue
                    
                    log.info(
                        f"[CreditWindow] {email}: probe-ready — "
                        f"running health check..."
                    )
                    
                    ext_bridge = getattr(account, 'extension_bridge', None)
                    health = await verify_account_health(
                        account, ext_bridge, skip_probe=False
                    )
                    
                    if health.healthy:
                        self._credit_window.reactivate(email)
                        # Reset circuit breaker state
                        self.record_circuit_success(email)
                        self.clear_account_cooldown(email)
                        self._account_recovery_phase[email] = 0
                        self._account_phase_403_count[email] = 0
                        log.info(
                            f"[CreditWindow] {email}: ✅ probe OK — "
                            f"reactivated with slow start"
                        )
                        # Wake foremen so they can pick up tasks
                        self._task_available.set()
                    else:
                        self._credit_window.probe_failed(email)
                        log.warning(
                            f"[CreditWindow] {email}: probe FAILED "
                            f"(failed checks: {health.failed})"
                        )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.debug(f"[CreditWindow] Timer error: {e}")
        
        log.info("[CreditWindow] Recovery timer stopped")
    
    async def _tab_keepalive_loop(self):
        """App-level background service: prevent Chrome from freezing VEO tabs.
        
        ARCHITECTURE: This coroutine is managed by AppController, NOT by Engine.
        It runs independently of the task processing pipeline.
        
        Two control events (created by AppController, passed to engine):
          _keepalive_yield: asyncio.Event
            SET   = keepalive ACTIVE (engine idle → keepalive pings tabs)
            CLEAR = keepalive PAUSED (engine processing → yield to engine)
          _keepalive_stop: asyncio.Event
            SET   = stop the loop entirely (app shutdown)
        
        Lifecycle:
          App start     → keepalive starts (yield=SET, engine not running)
          Start All     → yield CLEARED (engine takes over tab management)
          Stop/Pause    → yield SET (keepalive resumes tab pinging)
          App exit      → stop SET (loop exits)
        
        WHY separate from Engine:
          Both keepalive and engine use simulate_activity/executeScript on
          the same tabs. Chrome serializes executeScript per tab, so
          concurrent calls would delay reCAPTCHA token generation.
          Mutual exclusion via yield event eliminates this conflict.
        
        ★ Fix 5 (HAR-verified): 2-tier keepalive pattern:
          Tier 1: simulate_activity every 25s (JS mouse/scroll — Chrome freeze prevention)
          Tier 2: API heartbeat every ~125s (auth/session + credits — trust building)
        """
        KEEPALIVE_INTERVAL = 25  # seconds — under Chrome's 30-60s freeze threshold
        HEARTBEAT_EVERY_N_CYCLES = 5  # API heartbeat every 5th cycle (5 × 25s = 125s ≈ 2min)
        
        log.info("[TabKeepalive] App-level service started (2-tier: JS + API heartbeat)")
        
        # Small initial delay to let everything initialize
        await asyncio.sleep(5)
        
        yield_event = getattr(self, '_keepalive_yield', None)
        stop_event = getattr(self, '_keepalive_stop', None)
        
        if not yield_event or not stop_event:
            log.warning("[TabKeepalive] No control events set — exiting")
            return
        
        heartbeat_counter = 0  # Fix 5: track cycles for API heartbeat
        
        while not stop_event.is_set():
            try:
                # Wait for yield permission (engine idle) or stop signal
                if not yield_event.is_set():
                    log.debug("[TabKeepalive] Engine processing — yielding...")
                    # Wait until engine finishes OR stop signal
                    wait_yield = asyncio.create_task(yield_event.wait())
                    wait_stop = asyncio.create_task(stop_event.wait())
                    try:
                        done, pending = await asyncio.wait(
                            {wait_yield, wait_stop},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for t in pending:
                            t.cancel()
                        if stop_event.is_set():
                            break
                    finally:
                        for t in (wait_yield, wait_stop):
                            if not t.done():
                                t.cancel()
                    log.info("[TabKeepalive] Engine idle — resuming tab keepalive")
                    heartbeat_counter = 0  # Reset counter when resuming from yield
                
                # Tier 1: Ping all connected tabs (JS simulate_activity)
                pinged = 0
                for account in self._account_manager._accounts:
                    if not account.is_enabled:
                        continue
                    if stop_event.is_set() or not yield_event.is_set():
                        break  # Stop or engine just started
                    
                    bridge = getattr(account, 'extension_bridge', None)
                    if not bridge or not bridge.is_connected(account.email):
                        continue
                    
                    try:
                        ok = await bridge.simulate_activity(
                            account.email, timeout=3.0
                        )
                        if ok:
                            pinged += 1
                    except Exception:
                        pass  # Best-effort
                
                # Track stats for DevConsole dashboard
                self._keepalive_last_ping_count = pinged
                self._keepalive_last_ping_time = time.time()
                
                if pinged > 0:
                    log.debug(
                        f"[TabKeepalive] Pinged {pinged} tab(s) — "
                        f"Chrome freeze prevention OK"
                    )
                
                # ★ Fix 5 — Tier 2: API heartbeat every ~125s
                heartbeat_counter += 1
                if heartbeat_counter >= HEARTBEAT_EVERY_N_CYCLES:
                    heartbeat_counter = 0
                    for account in self._account_manager._accounts:
                        if not account.is_enabled:
                            continue
                        if stop_event.is_set() or not yield_event.is_set():
                            break
                        await self._api_heartbeat(account)
                
            except Exception as e:
                log.debug(f"[TabKeepalive] Loop error: {e}")
            
            # Sleep in small chunks to respond quickly to stop/yield changes
            for _ in range(KEEPALIVE_INTERVAL):
                if stop_event.is_set() or not yield_event.is_set():
                    break
                await asyncio.sleep(1.0)
        
        log.info("[TabKeepalive] App-level service stopped")
    
    async def _api_heartbeat(self, account):
        """Fix 5: Fire API-level heartbeat to match real browser keepalive pattern.
        
        HAR 05 evidence: Real VEO app fires these every ~2 min while idle:
        1. auth/session → refresh OAuth token (same-origin, credentials OK)
        2. fetchUserAcknowledgement(FLOW_IMAGE_UPLOAD_TOS) → signals active user
        3. credits?key=... → credit balance (cross-site, API key in URL, NO credentials)
        
        HAR-verified corrections:
        - ack version = FLOW_IMAGE_UPLOAD_TOS (NOT CREATIVE_PARTNER_PROGRAM_TOS)
        - credits: API key in URL query param, NO credentials (cross-site CORS)
        - Browser does NOT call checkAppAvailability in heartbeat
        """
        email = account.email
        try:
            # Batch all 3 API calls into a single JS evaluate to minimize
            # command-queue round-trips (each goes through threading.Event wait)
            result = await self._execute_js_on_account_async(account, """
                (async () => {
                    const results = {};
                    try {
                        // 1. auth/session — refresh OAuth token
                        const r1 = await fetch('/fx/api/auth/session', {credentials: 'include'});
                        results.auth = r1.status;
                    } catch { results.auth = 'error'; }
                    try {
                        // 2. fetchUserAcknowledgement — FLOW_IMAGE_UPLOAD_TOS (same-origin)
                        const r2 = await fetch('/fx/api/trpc/general.fetchUserAcknowledgement?input=' +
                            encodeURIComponent(JSON.stringify({
                                json: {acknowledgementVersion: 'FLOW_IMAGE_UPLOAD_TOS'}
                            })), {
                            headers: {'content-type': 'application/json'},
                            credentials: 'include'
                        });
                        results.ack = r2.status;
                    } catch { results.ack = 'error'; }
                    try {
                        // 3. credits — cross-site, API key in URL (NO credentials)
                        const r3 = await fetch(
                            'https://aisandbox-pa.googleapis.com/v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY'
                        );
                        results.credits = r3.status;
                    } catch { results.credits = 'error'; }
                    return results;
                })()
            """, timeout=15.0)
            
            if result is None:
                log.debug(f"[TabKeepalive] {email}: API heartbeat skipped (no browser page)")
                return
            
            log.info(
                f"[TabKeepalive] {email}: API heartbeat OK "
                f"(auth={result.get('auth')}, ack={result.get('ack')}, credits={result.get('credits')})"
            )
        except Exception as e:
            log.debug(f"[TabKeepalive] {email}: API heartbeat failed: {e}")
    
    # ── Public Facades (Issue #1: encapsulate AccountManager access) ──
    
    def get_account(self, email: str):
        """Public facade — get account by email."""
        return self._account_manager.get_account(email)
    
    def get_all_accounts(self):
        """Public facade — iterate all accounts (returns copy)."""
        return list(self._account_manager._accounts)
    
    def fix_client_data(self):
        """Public facade — fix short x-client-data headers after browser restart."""
        self._account_manager.fix_short_client_data()
    
    # ── Public Facades (Cluster #3: encapsulate subsystem access) ──
    
    def _get_keepalive_state(self) -> str:
        """Return current keepalive state for DevConsole monitoring."""
        stop = getattr(self, '_keepalive_stop', None)
        yield_ev = getattr(self, '_keepalive_yield', None)
        if not stop or not yield_ev:
            return "NOT_STARTED"
        if stop.is_set():
            return "STOPPED"
        return "ACTIVE" if yield_ev.is_set() else "PAUSED"
    
    def get_dashboard_stats(self) -> dict:
        """Aggregate all subsystem stats for DevConsole dashboard.
        
        Replaces 6+ direct `engine._X.get_stats()` accesses in app_controller.
        """
        stats = {}
        if getattr(self, '_recaptcha_pool', None):
            stats["recaptcha_pool"] = self._recaptcha_pool.get_stats()
        if getattr(self, '_upscale_queue', None):
            stats["upscale_queue"] = self._upscale_queue.get_stats()
        if getattr(self, '_burst_controller', None):
            stats["burst_controller"] = self._burst_controller.get_stats()
        
        # Pre-warm stats
        stats["prewarm"] = {
            "enabled": getattr(self._settings, 'prewarm_enabled', True) if self._settings else True,
            "threshold_sec": (getattr(self._settings, 'prewarm_idle_threshold', 10) * 60) if self._settings else 600,
            "accounts": {}
        }
        for email, ps in self._prewarm_stats.items():
            last = self._last_successful_submit.get(email, 0)
            current_idle = time.time() - last if last else 0
            stats["prewarm"]["accounts"][email] = {
                "total_prewarms": ps.get('count', 0),
                "last_idle_secs": ps.get('last_idle_secs', 0),
                "current_idle_secs": round(current_idle),
                "last_prewarm": ps.get('last_time', 0),
            }
        
        # ── Tab Keepalive status ──
        ka_state = self._get_keepalive_state()
        yield_ev = getattr(self, '_keepalive_yield', None)
        stats["keepalive"] = {
            "state": ka_state,
            "last_ping_count": self._keepalive_last_ping_count,
            "last_ping_time": self._keepalive_last_ping_time,
            "controller": "keepalive" if (yield_ev and yield_ev.is_set()) else "engine",
        }
        
        # ── Circuit Breaker status per-account ──
        stats["circuit_breaker_status"] = {}
        for email in self._circuit_state:
            state = self._circuit_state.get(email, "closed")
            open_since = self._circuit_open_since.get(email, 0)
            duration = round(time.time() - open_since) if open_since and state != "closed" else 0
            stats["circuit_breaker_status"][email] = {
                "state": state,
                "consecutive_403": self._circuit_consecutive_403.get(email, 0),
                "open_duration_sec": duration,
            }
        
        # ── Account Cooldown status ──
        stats["cooldowns"] = {}
        now = datetime.now()
        for email, until in self._account_cooldowns.items():
            remaining = max(0, (until - now).total_seconds())
            if remaining > 0:
                stats["cooldowns"][email] = {
                    "remaining_sec": round(remaining),
                    "backoff_level": self._account_cooldown_backoff.get(email, 0),
                    "until": until.strftime("%H:%M:%S"),
                }
        
        # ── Workload Priority mode ──
        stats["workload_priority"] = self._workload_priority
        
        # ── Rate Lock contention ──
        stats["rate_locks"] = {}
        for email, lock in getattr(self, '_account_rate_locks', {}).items():
            stats["rate_locks"][email] = {"locked": lock.locked()}
        
        return stats
    
    def get_pipeline_settings(self) -> dict:
        """Read current pipeline optimization settings.
        
        Replaces direct reads of `engine._burst_controller._min` etc.
        """
        settings = {}
        bc = getattr(self, '_burst_controller', None)
        if bc:
            settings["burst_min_delay"] = bc._min
            settings["burst_max_delay"] = bc._max
            settings["adaptive_burst_enabled"] = True
        rp = getattr(self, '_recaptcha_pool', None)
        if rp:
            settings["pool_size"] = rp.POOL_SIZE
        return settings
    
    def update_pipeline_setting(self, key: str, value):
        """Single entry point for pipeline setting mutations.
        
        Replaces double-chain `engine._burst_controller._min = value`.
        Handles: burst_min/max_delay, pool_size, recaptcha_pool_enabled,
        workload_priority. Non-engine keys (watchdog, journal) stay in
        AppController since they're AppController-owned objects.
        
        Returns True if handled, False if key not recognized.
        """
        bc = getattr(self, '_burst_controller', None)
        rp = getattr(self, '_recaptcha_pool', None)
        
        if key == "burst_min_delay" and bc:
            bc._min = float(value)
        elif key == "burst_max_delay" and bc:
            bc._max = float(value)
        elif key == "adaptive_burst_enabled":
            pass  # Informational — burst controller always active
        elif key == "pool_size" and rp:
            rp.POOL_SIZE = int(value)
        elif key == "recaptcha_pool_enabled" and rp:
            if value and not rp._running:
                rp.start()
            elif not value and rp._running:
                rp.stop()
        elif key == "workload_priority":
            self._workload_priority = str(value)
            log.info(f"[Engine] Workload priority → {value}")
        elif key == "prewarm_enabled":
            pass  # Read from settings at runtime
        elif key == "prewarm_idle_threshold":
            pass  # Stored in minutes, read at runtime
        else:
            return False
        return True
    
    # ── Workload Priority ──
    
    def should_upscale_wait(self) -> bool:
        """Check if upscale queue should pause (720p_priority mode).
        
        Fix G2+G4: Pause upscale while ANY prompt is still active —
        either waiting in queue (ready_count) OR currently generating
        (running_count). Previous logic only checked ready_count, which
        dropped to 0 as soon as workers picked up all tasks, causing
        upscale to start while prompts were still generating.
        
        Fix G3+G5: Don't pause when ONLY ready tasks exist and all
        accounts are on cooldown (true deadlock). But DO pause when
        workers are running (even in cooldown) — they'll resume and
        upscale would just compete for the same reCAPTCHA tokens.
        """
        if self._workload_priority != '720p_priority':
            return False
        
        ready = self._dispatcher.ready_count
        running = self._dispatcher.running_count
        
        # No active prompts at all → upscale can proceed
        if ready <= 0 and running <= 0:
            return False
        
        # Fix G5: Workers still running (even if in cooldown) →
        # always wait. They'll finish/retry and upscale would only
        # compete for the same reCAPTCHA tokens causing double-403.
        if running > 0:
            return True
        
        # Fix G3: Only ready tasks remain (no running workers).
        # If all accounts are on cooldown, those tasks can't be picked up
        # → allow upscale to avoid deadlock.
        accounts = self.get_all_accounts()
        if accounts and all(
            self.is_account_on_cooldown(acc.email) for acc in accounts
        ):
            return False
        
        return True
    
    # ── Pre-warm: Proactive reCAPTCHA Recovery ──
    
    async def _maybe_prewarm(self, account) -> None:
        """Pre-warm reCAPTCHA if idle > threshold.
        
        Called before the first submit attempt after an idle period.
        Performs soft recovery (navigate away + back) to reset reCAPTCHA
        scoring context, preventing 403 cascade from stale sessions.
        
        Steps:
          1. Simulate activity (wake tab)
          2. Soft recovery (navigate about:blank → VEO → re-init reCAPTCHA)
          3. Wait for reCAPTCHA readiness
          4. Validate token (pre-fetch for first submit)
          5. Reset AdaptiveBurst delay
        """
        email = account.email
        last = self._last_successful_submit.get(email, 0)
        idle_secs = time.time() - last if last else 0
        
        # Check setting toggle
        if self._settings and not getattr(self._settings, 'prewarm_enabled', True):
            return
        
        # Threshold in minutes from settings, convert to seconds
        threshold_min = getattr(self._settings, 'prewarm_idle_threshold', 10) if self._settings else 10
        threshold_secs = threshold_min * 60
        
        if idle_secs < threshold_secs:
            return  # Not idle enough
        
        log.info(
            f"[PreWarm] {email}: idle {idle_secs:.0f}s > {threshold_secs}s "
            f"— triggering soft recovery before submit"
        )
        
        # Update stats for DevConsole
        stats = self._prewarm_stats.setdefault(email, {
            'count': 0, 'last_idle_secs': 0, 'last_time': 0,
        })
        stats['count'] += 1
        stats['last_idle_secs'] = idle_secs
        stats['last_time'] = time.time()
        
        # ── Step 1: Simulate activity first (wake tab) ──
        bridge = account.extension_bridge
        if bridge and bridge.is_connected(email):
            try:
                await bridge.simulate_activity(email, timeout=3.0)
                await asyncio.sleep(1.0)
            except Exception:
                pass
        
        # ── Step 2: Soft recovery ──
        try:
            recovered = await account.soft_recover_browser()
        except Exception as e:
            log.warning(f"[PreWarm] {email}: soft recovery failed: {e}")
            recovered = False
        
        if recovered:
            # ── Step 3: Wait for reCAPTCHA readiness ──
            await self._wait_for_recaptcha_ready(account, max_wait=20.0)
            
            # ── Step 4: Validate token ──
            try:
                test_token = await account.refresh_recaptcha()
                if test_token and len(test_token) > 100:
                    log.info(f"[PreWarm] {email}: ✅ reCAPTCHA token validated ({len(test_token)} chars)")
                else:
                    log.warning(f"[PreWarm] {email}: ⚠️ reCAPTCHA token weak/missing after pre-warm")
            except Exception as e:
                log.warning(f"[PreWarm] {email}: reCAPTCHA validation failed: {e}")
        
        # ── Step 5: Reset AdaptiveBurst delay for fresh start ──
        if getattr(self, '_burst_controller', None):
            self._burst_controller.record_success(email)
        
        self._last_successful_submit[email] = time.time()
        log.info(f"[PreWarm] {email}: ✅ pre-warm complete (idle was {idle_secs:.0f}s)")
    
    async def pause(self):
        """Pause: workers sleep at next loop iteration without exiting.
        
        Browsers and worker coroutines stay alive — only task pickup stops.
        Much faster resume vs stop/start cycle.
        """
        if not self._running:
            return
        self._pause_event.clear()
        log.info("Engine paused — workers will sleep at next iteration")
    
    async def resume(self):
        """Resume: wake up all sleeping workers."""
        if not self._running:
            return
        self._pause_event.set()
        self._task_available.set()  # Wake workers waiting for tasks too
        log.info("Engine resumed — workers waking up")
    
    async def stop(self):
        """Stop the engine gracefully.
        
        Bug 7 fix: Re-queue tasks in RUNNING/WAITING_POLL state so they
        can be picked up when engine restarts (Resume).
        Sets the stop event, causing all worker loops to exit.
        The start() method's finally block handles browser cleanup.
        """
        if not self._running:
            return
        
        log.info("Engine stop requested — signaling workers to exit")
        self._stop_event.set()
        self._task_available.set()  # Wake up any waiting workers
        
        # Bug 7: Re-queue tasks stuck in RUNNING or WAITING_POLL
        requeued = 0
        for task in self._dispatcher.get_all_tasks():
            if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                task.state = TaskState.READY
                self._dispatcher.requeue_running_task(task)
                requeued += 1
        if requeued:
            log.info(f"Re-queued {requeued} tasks that were RUNNING/WAITING_POLL")
        
        # Give workers a moment to finish current iteration
        await asyncio.sleep(0.5)
    
    async def start(self):
        """Start the engine main loop.
        
        Per-Account Worker Architecture:
        1. Start persistent browsers for all accounts (reCAPTCHA refresh)
        2. For each enabled account (CHỦ), create N worker coroutines
           where N = account.max_workers (0-20, configurable per-account)
        3. All workers pull from the SAME global task queue (THẦU)
           → cross-project, cross-account work distribution
        """
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._task_available.clear()
        
        # Bug 14: Wire dispatcher's on_task_ready to wake up waiting workers
        self._dispatcher.set_on_task_ready(lambda task: self._task_available.set())
        
        # Smart Recovery: Wire CreditWindow to dispatcher for credit-based routing
        self._dispatcher.set_credit_window(self._credit_window)
        
        # Inject profiles_controller into accounts for debug browser sharing
        if self._profiles_controller:
            for acc in self._account_manager._accounts:
                acc.set_profiles_controller(self._profiles_controller)
        
        # Start persistent browsers for reCAPTCHA refresh
        # If debug browsers are already open, ensure_browser() will ATTACH to them
        try:
            from config.settings import get_settings as _get_settings
            _s = _get_settings()
            _headless = getattr(_s, 'smart_hide_enabled', True)
            await self._account_manager.startup_browsers(headless=_headless)
        except Exception as e:
            log.error(f"Failed to start browsers: {e}")
        
        # Diagnostic logging
        total_accounts = len(self._account_manager._accounts)
        ready_tasks = self._dispatcher.ready_count
        log.info(f"Engine starting: {total_accounts} accounts, {ready_tasks} ready tasks in queue")
        
        if total_accounts == 0:
            log.error("No accounts in pool — did sync_profiles_to_runtime() succeed?")
            self._running = False
            return
        
        # Register accounts in RecaptchaPool so background refill loop works.
        # Without this, pool._fetchers is empty → no tokens ever pre-fetched.
        if self._recaptcha_pool:
            for account in self._account_manager._accounts:
                if account.is_enabled:
                    self._recaptcha_pool.register_account(
                        account.email,
                        fetch_fn=lambda email, acc=account: acc.refresh_recaptcha(),
                    )
            log.info(
                f"[RecaptchaPool] Registered {len(self._recaptcha_pool._fetchers)} "
                f"accounts for background token pre-fetch"
            )
        
        if ready_tasks == 0:
            log.warning("Ready queue is EMPTY — workers will idle until tasks are submitted")
        
        # Fix G8: Pre-filter UPSCALING tasks from ready queue → UpscaleQueue
        # On session restore, tasks saved with stage=UPSCALING are in the ready queue.
        # Without this, 12 workers grab them simultaneously, each enqueues to UpscaleQueue
        # in <1s — a burst. Instead, route them directly here before workers start.
        if ready_tasks > 0:
            from core.upscale_queue import UpscaleJob
            
            # Drain entire ready queue
            drained = []
            while not self._dispatcher._ready_queue.empty():
                try:
                    item = self._dispatcher._ready_queue.get_nowait()
                    drained.append(item)
                except Exception:
                    break
            
            upscale_routed = 0
            for priority, counter, task in drained:
                if (task.stage == TaskStage.UPSCALING
                        and task.download_quality != "720p"):
                    # Collect media_ids from saved video_outputs
                    media_ids = [vo.media_id for vo in task.video_outputs if vo.media_id]
                    output_uris = [vo.file_720p for vo in task.video_outputs if vo.file_720p]
                    
                    if media_ids:
                        # Determine account email from task
                        acct_email = task.assigned_account or ""
                        if not acct_email and self._account_manager._accounts:
                            acct_email = self._account_manager._accounts[0].email
                        
                        self._upscale_queue.enqueue(UpscaleJob(
                            task_id=task.id,
                            account_email=acct_email,
                            original_account=acct_email,  # DD6
                            media_ids=list(media_ids),
                            output_uris=list(output_uris),
                            target_quality=task.download_quality,
                            aspect_ratio=task.aspect_ratio,
                        ))
                        task.upscale_media_ids = list(media_ids)
                        self._dispatcher.update_progress(
                            task.id, 88,
                            f"⬆️ Resuming upscale {task.download_quality} (queued)"
                        )
                        upscale_routed += 1
                        continue  # Don't put back in ready queue
                
                # Non-upscaling task → put back
                self._dispatcher._ready_queue.put_nowait((priority, counter, task))
            
            if upscale_routed > 0:
                log.info(
                    f"[Engine] Pre-filter: {upscale_routed} UPSCALING tasks → UpscaleQueue "
                    f"(bypassed worker pipeline), {self._dispatcher.ready_count} tasks remain in queue"
                )
        
        try:
            async with asyncio.TaskGroup() as tg:
                self._task_group = tg  # Store reference for hot-reload
                
                # C1 fix: Dynamic Worker Scaling — spawn coroutines matching max_workers.
                # acquire_workers() checks capacity EVERY call, so changing
                # max_workers mid-run takes effect immediately:
                #   - Increase: idle coroutines start acquiring workers → process tasks
                #   - Decrease: excess coroutines fail acquire_workers() → idle safely
                
                for account in self._account_manager._accounts:
                    if not account.is_enabled:
                        log.info(f"Account {account.email}: skipped (disabled)")
                        continue
                    
                    self._spawn_account_supervisor(tg, account)
                
                # Hot-reload watcher: listens for new accounts added at runtime
                tg.create_task(self._account_watcher(tg))
                
                # Circuit breaker monitor: checks extension health every 10s
                tg.create_task(self._circuit_breaker_monitor())
                
                # Smart Recovery: Credit recovery timer
                tg.create_task(self._credit_recovery_timer())
                
                # NOTE: Tab keepalive is managed by AppController (app-level service)
                # to avoid conflicts with engine's task processing pipeline.
                # Engine signals keepalive to pause/resume via _keepalive_yield event.
        except* Exception as eg:
            for exc in eg.exceptions:
                if not isinstance(exc, asyncio.CancelledError):
                    log.error(f"Worker error: {exc}")
        finally:
            # Disconnect Playwright from persistent Chrome (Chrome keeps running)
            try:
                await self._account_manager.shutdown_browsers()
            except Exception as e:
                log.error(f"Browser disconnect error: {e}")
            self._running = False
            self._workers.clear()
            self._active_account_emails.clear()
            self._task_group = None
    
    def _get_typical_output_count(self) -> int:
        """Peek at queue to determine typical output_count for foreman sizing.
        
        Returns: most common output_count in ready queue, or 2 as default.
        """
        try:
            # Peek up to 10 items from ready queue without consuming them
            items = []
            while not self._dispatcher._ready_queue.empty() and len(items) < 10:
                try:
                    items.append(self._dispatcher._ready_queue.get_nowait())
                except Exception:
                    break
            
            if items:
                counts = [getattr(item[2], 'output_count', 2) or 2 for item in items]
                # Put items back
                for item in items:
                    self._dispatcher._ready_queue.put_nowait(item)
                # Return most common
                from collections import Counter
                return Counter(counts).most_common(1)[0][0]
        except Exception:
            pass
        return 2  # Safe default: most T2V projects use output_count=2
    
    def _spawn_account_supervisor(
        self, tg: asyncio.TaskGroup, account: AccountManager,
    ):
        """Spawn N Foremen + 1 Supervisor for a single account.
        
        Architecture:
          1 Account  = M Foremen  (M = ceil(max_workers / output_count))
          1 Foreman  = 1 Prompt   (each manages exactly 1 prompt lifecycle)
          1 Prompt   = N Workers  (N = output_count, 1-4 videos)
        
        - Supervisor (CHỦ): startup tasks, error queue, clearance gate
        - Foremen: independent coroutines — pick task, submit (serialized by
          rate lock), dispatch pipeline workers (fire-and-forget)
        - Rate lock ensures only 1 submit at a time per account (anti-detect)
        """
        if account.email in self._active_account_emails:
            log.debug(f"[Foreman:{account.email}] Already active, skipping")
            return
        
        # Supervisor (CHỦ) — one-time startup + error handling
        supervisor = AccountSupervisor(account, self)
        self._supervisors[account.email] = supervisor
        tg.create_task(supervisor.run())
        
        # Foreman count: ceil(max_workers / output_count), capped at 8
        import math
        typical_output = self._get_typical_output_count()
        foreman_count = max(1, min(
            math.ceil(account.max_workers / typical_output),
            8,  # Cap: beyond 8, foremen just queue on rate lock
        ))
        
        for i in range(foreman_count):
            foreman_worker = Worker(
                worker_id=f"foreman-{account.email[:8]}-{i}",
                api_client=self._api_client,
                on_progress=self._on_progress,
            )
            self._workers.append(foreman_worker)
            tg.create_task(self._foreman_loop(foreman_worker, account))
        
        self._active_account_emails.add(account.email)
        log.info(
            f"[Supervisor:{account.email}] Spawned CHỦ + {foreman_count} Foremen "
            f"(max_workers={account.max_workers}, output={typical_output}, "
            f"retry={account.retry_count}, timeout={account.request_timeout}s)"
        )
    
    async def _account_watcher(self, tg: asyncio.TaskGroup):
        """Watch for new accounts added at runtime and spawn workers.
        
        Runs inside the TaskGroup — uses tg.create_task() to add
        new worker coroutines dynamically without engine restart.
        """
        # C1 fix: dynamic coroutine count per account
        
        while not self._stop_event.is_set():
            try:
                # Wait for a new account with timeout (check stop_event periodically)
                try:
                    account = await asyncio.wait_for(
                        self._pending_accounts.get(), timeout=2.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                if account.email in self._active_account_emails:
                    log.debug(f"Hot-reload: {account.email} already has workers")
                    continue
                
                # Start browser for new account
                try:
                    if self._profiles_controller:
                        account.set_profiles_controller(self._profiles_controller)
                    from config.settings import get_settings as _get_settings
                    _headless = getattr(_get_settings(), 'smart_hide_enabled', True)
                    await account.ensure_browser(headless=_headless)
                except Exception as e:
                    log.warning(f"Hot-reload: browser start failed for {account.email}: {e}")
                
                # Spawn foreman
                self._spawn_account_supervisor(tg, account)
                log.info(f"[Foreman:{account.email}] Hot-reload: spawned — processing starts immediately")
                
                # Wake up idle workers to check for tasks
                self._task_available.set()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Account watcher error: {e}")
                await asyncio.sleep(1)
    
    def add_account_hot(self, account: AccountManager):
        """Add an account to the engine while it is running.
        
        Thread-safe: can be called from the UI/main thread.
        The _account_watcher coroutine will pick it up and spawn workers.
        
        Args:
            account: AccountManager to add workers for
        """
        if not self._running:
            log.debug(f"Engine not running, skip hot-add for {account.email}")
            return
        
        if account.email in self._active_account_emails:
            log.debug(f"Account {account.email} already has workers")
            return
        
        # Thread-safe put into asyncio queue
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(self._pending_accounts.put_nowait, account)
                log.info(f"Hot-reload queued: {account.email}")
            else:
                self._pending_accounts.put_nowait(account)
        except Exception as e:
            log.error(f"Failed to queue hot-reload for {account.email}: {e}")
    
    async def _do_browser_recovery(self, account, worker_id: str, tier: str) -> bool:
        """Deduped browser recovery.
        
        All workers sharing the same account use one recovery key.
        Lock ensures only one recovery attempt runs at a time.
        
        Args:
            account: AccountManager for the target account
            worker_id: Worker ID for logging
            tier: "soft" (navigate away+back) or "hard" (kill+relaunch Chrome)
        
        Returns:
            True if recovery succeeded (either by this worker or another)
        """
        recovery_key = account.email
        
        lock = self._browser_recovery_locks.setdefault(recovery_key, asyncio.Lock())
        epoch_before = self._browser_recovery_epoch.get(recovery_key, 0)
        
        async with lock:
            epoch_now = self._browser_recovery_epoch.get(recovery_key, 0)
            if epoch_now > epoch_before:
                # Another worker already recovered while we waited for the lock
                log.info(
                    f"✅ Worker {worker_id}: browser already recovered "
                    f"(epoch {epoch_before}→{epoch_now}), skipping {tier} recovery"
                )
                return True
            
            # We are the first worker — perform actual recovery
            try:
                if tier == "soft":
                    log.warning(f"🔄 Worker {worker_id}: soft browser recovery for {recovery_key}...")
                    ok = await account.soft_recover_browser()
                else:
                    log.warning(f"🔄 Worker {worker_id}: HARD browser restart for {recovery_key}...")
                    ok = await account.restart_browser()
                
                if ok:
                    self._browser_recovery_epoch[recovery_key] = epoch_now + 1
                    log.info(
                        f"✅ Worker {worker_id}: {tier} browser recovery complete "
                        f"(epoch→{epoch_now + 1})"
                    )
                    # After restart, borrow x-client-data from other accounts
                    # if ours is still short (Variations Service not enrolled)
                    self._account_manager.fix_short_client_data()
                else:
                    log.error(f"❌ Worker {worker_id}: {tier} browser recovery returned False")
                return ok
            except Exception as e:
                log.error(f"❌ Worker {worker_id}: {tier} browser recovery failed: {e}")
                return False
    
    async def _foreman_loop(self, worker: Worker, account: AccountManager):
        """Foreman loop — 1 Foreman = 1 Prompt = N Workers.
        
        Multiple foremen run concurrently per account.
        Submit path serialized by _account_rate_locks (anti-detect).
        Pipeline path concurrent (fire-and-forget).
        
        Lifecycle per iteration:
          wait for workers → pick task → validate → upload →
          [rate lock] delay → submit → dispatch pipeline → loop
        """
        fid = worker.worker_id  # e.g. "foreman-abc14-2"
        
        # ── Wait for supervisor startup (shared one-time tasks) ────────
        supervisor = self._supervisors.get(account.email)
        if supervisor:
            log.debug(f"[{fid}] Waiting for supervisor startup...")
            await supervisor._startup_done.wait()
            log.debug(f"[{fid}] Supervisor startup done — entering main loop")
        
        # ── Progressive startup: foreman-0 starts first, ────────
        # foremen 1+ wait for first successful submit.
        # Prevents 8 foremen burst-submitting when reCAPTCHA is broken.
        try:
            foreman_idx = int(fid.rsplit('-', 1)[-1])
        except (ValueError, IndexError):
            foreman_idx = 0
        
        if foreman_idx > 0:
            # Wait for first submit to succeed (max 90s)
            if supervisor and not supervisor._first_submit_ok.is_set():
                log.info(f"[{fid}] ⏳ Waiting for foreman-0 first submit success...")
                try:
                    await asyncio.wait_for(
                        supervisor._first_submit_ok.wait(), timeout=90.0
                    )
                    log.info(f"[{fid}] ✅ First submit verified — starting")
                except asyncio.TimeoutError:
                    log.warning(f"[{fid}] ⚠️ First submit timeout (90s) — starting anyway")
            # Stagger: use anti-detect delay from settings (respects Settings tab)
            from config.settings import get_settings as _get_stagger_settings
            _s = _get_stagger_settings()
            if getattr(_s, 'anti_detect_enabled', True):
                import random
                startup_delay = random.uniform(
                    _s.anti_detect_delay_min, _s.anti_detect_delay_max
                )
            else:
                startup_delay = foreman_idx * 1.5  # Fallback if anti-detect disabled
            log.debug(f"[{fid}] Stagger delay: {startup_delay:.1f}s (anti-detect={'on' if getattr(_s, 'anti_detect_enabled', True) else 'off'})")
            await asyncio.sleep(startup_delay)
        
        # Track active pipeline tasks for this foreman
        active_pipelines: set = set()
        
        while not self._stop_event.is_set():
            try:
                # Pause check — block until resumed (or stop signaled)
                if not self._pause_event.is_set():
                    log.debug(f"[{fid}] Paused, waiting for resume")
                    while not self._stop_event.is_set() and not self._pause_event.is_set():
                        await asyncio.sleep(0.5)
                    if self._stop_event.is_set():
                        break
                
                # DD4: Check supervisor abort signal (circuit breaker tripped)
                if supervisor and supervisor.is_aborted:
                    log.warning(
                        f"[{fid}] ⚡ Supervisor ABORT — "
                        f"circuit breaker tripped, pausing foreman"
                    )
                    while (supervisor.is_aborted 
                           and not self._stop_event.is_set()):
                        await asyncio.sleep(1.0)
                    if self._stop_event.is_set():
                        break
                    log.info(f"[{fid}] ✅ Abort cleared, resuming")
                    # Fix #2: Staggered resume — random delay per foreman
                    # to prevent thundering herd (all 8 foremen submitting
                    # simultaneously after circuit breaker closes → burst → 429/403).
                    import random as _rng
                    stagger = _rng.uniform(1.0, 5.0)
                    log.info(f"[{fid}] Stagger {stagger:.1f}s before resume")
                    await asyncio.sleep(stagger)
                
                # Step 1: Two-phase admission — acquire 1 worker first
                worker_count = 0
                if not account.acquire_workers(1):
                    await asyncio.sleep(0.5)
                    continue
                worker_count = 1
                
                # H4 fix: Check account cooldown BEFORE wasting reCAPTCHA tokens
                if self.is_account_on_cooldown(account.email):
                    account.release_workers(worker_count)
                    worker_count = 0
                    await self.wait_for_cooldown(account.email)
                    continue
                
                # Bug 2 fix: Pause if profile reset in progress for this account
                if self._account_resetting.get(account.email, False):
                    account.release_workers(worker_count)
                    worker_count = 0
                    log.debug(f"[{fid}] Account resetting, waiting...")
                    while self._account_resetting.get(account.email, False) and not self._stop_event.is_set():
                        await asyncio.sleep(2)
                    continue  # Re-acquire after reset
                
                try:
                    # Step 2: Get next task from GLOBAL queue (THẦU)
                    # PA3: Pass account email for fair-share balancing
                    task = self._dispatcher.get_next_task(account_email=account.email)
                    if not task:
                        account.release_workers(worker_count)
                        worker_count = 0
                        # Bug 14: Wait for task notification instead of busy-polling
                        self._task_available.clear()
                        try:
                            await asyncio.wait_for(
                                self._task_available.wait(),
                                timeout=2.0,  # Check stop_event every 2s
                            )
                        except asyncio.TimeoutError:
                            pass
                        continue
                    
                    # Phase 2 admission: acquire extra workers for output_count > 1
                    output_count = getattr(task, 'output_count', 1) or 1
                    # Edge case: if max_workers < output_count, clamp to max_workers
                    # Otherwise acquire_workers(output_count) would ALWAYS fail
                    if output_count > account.max_workers:
                        log.warning(
                            f"[{fid}] output_count={output_count} > "
                            f"max_workers={account.max_workers} — clamping"
                        )
                        output_count = account.max_workers
                    if output_count > 1:
                        extra = output_count - 1
                        if account.acquire_workers(extra):
                            worker_count += extra
                        else:
                            # Not enough capacity — requeue task, release held worker
                            log.debug(
                                f"[{fid}] Insufficient capacity for "
                                f"output_count={output_count} "
                                f"(need {output_count}, have {account.session.available_workers + 1})"
                            )
                            self._dispatcher.requeue_task(task)
                            account.release_workers(worker_count)
                            worker_count = 0
                            await asyncio.sleep(2.0)
                            continue
                    
                    # H3 fix: Store worker_count on task for proper cleanup
                    # Set ASAP after Phase 2 admission so watchdog can recover correctly
                    task._worker_count = worker_count
                    
                    log.info(
                        f"[{fid}] Picked task {task.id} "
                        f"[{task.state.value}/{task.stage.value}] "
                        f"progress={task.progress}% prompt_idx={task.prompt_index} "
                        f"workflow={task.workflow_type}"
                    )
                    
                    # D2: Account affinity check — continuation tasks must run on same account
                    if task.required_account and task.required_account != account.email:
                        # Re-queue for correct account, release our workers
                        # BUG FIX: Use requeue_task (decrements _running_count)
                        # instead of submit_task (which leaked +1)
                        task.state = TaskState.READY
                        self._dispatcher.requeue_task(task)
                        account.release_workers(worker_count)
                        worker_count = 0
                        await asyncio.sleep(0.1)
                        continue
                    
                    # Cancellation check: task may have been cancelled between
                    # get_next_task and now (e.g., user deleted from queue)
                    if task.state == TaskState.CANCELLED:
                        log.info(f"[Foreman:{account.email}] Task {task.id} was cancelled, skipping")
                        account.release_workers(worker_count)
                        worker_count = 0
                        continue
                    
                    # Step 3: Lazy browser start if not yet initialized
                    if not account._browser_session or not account._browser_session.is_ready:
                        try:
                            from config.settings import get_settings as _get_settings
                            _headless = getattr(_get_settings(), 'smart_hide_enabled', True)
                            await account.ensure_browser(headless=_headless)
                        except Exception as e:
                            log.warning(f"Browser start failed for {account.email}: {e} (continuing without persistent browser)")
                    
                    # Bug 11 fix: Removed redundant reCAPTCHA refresh here.
                    # Worker.execute() already handles reCAPTCHA refresh (step B5).
                    # Having it in both places caused double-refresh and wasted 200-500ms.
                    
                    # Step 5: Ensure project exists (shared logic)
                    if not account.project_id:
                        await self._ensure_runtime_project(
                            account, title=task.project_name or "My Video Project"
                        )
                    
                    # Step 5.5: Auto-detect paygate tier (once per account)
                    if account.paygate_tier == "PAYGATE_TIER_TWO":
                        await account.fetch_paygate_tier(self._api_client)
                    
                    # Notify UI
                    task.assigned_account = account.email
                    task.project_id = account.project_id
                    emit_event(EventType.TASK_STARTED, {
                        "task_id": task.id, "account": account.email,
                        "workflow": task.workflow_type,
                        "prompt": (task.prompt or "")[:80],
                    }, source="engine")
                    if self._on_task_started:
                        self._on_task_started(task)
                    
                    # ★ STAGE ROUTER — skip completed stages on retry/resume
                    # If resuming from a checkpoint, jump directly to poll pipeline
                    if task.stage in (TaskStage.SUBMITTED, TaskStage.GENERATED,
                                      TaskStage.DOWNLOADED_720, TaskStage.UPSCALING,
                                      TaskStage.UPSCALED):
                        log.info(
                            f"[Foreman:{account.email}] Task {task.id}: "
                            f"RESUMING from stage {task.stage.value} → concurrent pipeline"
                        )
                        task.state = TaskState.WAITING_POLL
                        # ★ Fire-and-forget: pipeline runs concurrently
                        t = asyncio.create_task(
                            self._foreman_dispatch_workers(task, account, worker_count,
                                                          supervisor=supervisor)
                        )
                        active_pipelines.add(t)
                        t.add_done_callback(active_pipelines.discard)
                        worker_count = 0  # Ownership transferred to pipeline
                        continue
                    
                    # Bug 13: Per-account rate limiter — serialize requests per account
                    # Ensures 4 workers on same account don't submit simultaneously
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Lock()
                    
                    # Step 7: Execute with RETRY + TIMEOUT
                    # Rate lock held ONLY during anti-detect delay + API call,
                    # released between retries so other workers can proceed.
                    
                    # Step 6.5: Upload local image_paths → image_uris
                    # Risk 4 fix: Upload through rate lock to prevent 4 concurrent uploads
                    # I2V image loss fix: Always re-upload when image_paths available.
                    # MediaIds expire between retries/sessions — stale IDs cause silent
                    # failures. Fresh upload from local files is always preferred.
                    if task.image_paths:
                        if task.image_uris:
                            log.info(
                                f"[Foreman:{account.email}] Task {task.id}: clearing {len(task.image_uris)} "
                                f"stale image_uris — will re-upload from image_paths"
                            )
                            task.image_uris.clear()
                        log.info(
                            f"[Foreman:{account.email}] Task {task.id}: uploading {len(task.image_paths)} image(s) "
                            f"[{task.stage.value}] progress={task.progress}%"
                        )
                        async with self._account_rate_locks[account.email]:
                            # Fix G7: Anti-detect delay before image upload
                            if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else True:
                                await self._burst_controller.wait(account.email)
                            await self._resolve_image_paths(task, account)
                    
                    # Guard: I2V/R2V/F2V must have images after upload step
                    # If image_uris is still empty here, the task can never succeed.
                    # Fail fast instead of wasting retry cycles.
                    if (task.workflow_type in ('I2V', 'R2V', 'F2V')
                            and not task.image_uris
                            and not task.parent_task_id):  # Continuations handled by step 6.6
                        self._dispatcher.fail_task(
                            task.id,
                            f"{task.workflow_type} has no images "
                            f"(upload failed or image_paths empty)"
                        )
                        # Workers released by finally block
                        continue
                    
                    # Step 6.6: Re-upload continuation frame for child tasks
                    # MediaIds expire — always get a fresh one before submit
                    # Tier 1: re-upload existing frame / Tier 2: re-extract from parent video
                    if task.parent_task_id and (task.continuation_frame_local_path or task.image_uris):
                        log.info(
                            f"[Foreman:{account.email}] Task {task.id}: re-uploading continuation frame "
                            f"[{task.stage.value}] progress={task.progress}% "
                            f"parent={task.parent_task_id}"
                        )
                        async with self._account_rate_locks[account.email]:
                            fresh_uri = await self._re_upload_continuation_frame(task, account)
                            if fresh_uri:
                                task.image_uris = [fresh_uri]
                            elif not task.image_uris:
                                self._dispatcher.fail_task(
                                    task.id, "Continuation frame re-upload failed"
                                )
                                # Workers released by finally block
                                continue
                    
                    # Adaptive retry: more retries for transient errors.
                    # Chain tasks get even more — losing 1 root = losing N children
                    base_retries = account.retry_count
                    is_chain = (self._dispatcher.has_children(task.id) or 
                                task.parent_task_id is not None)
                    if is_chain:
                        max_retries = max(base_retries, 15)  # Chain: up to 15
                    else:
                        max_retries = max(base_retries, 10)  # Normal: up to 10
                    timeout = account.request_timeout
                    # T2I/I2I is synchronous — server generates images before
                    # responding (~37s per HAR). Ensure enough time.
                    wt_upper = task.workflow_type.upper() if task.workflow_type else ""
                    if wt_upper in ("T2I", "I2I"):
                        timeout = max(timeout, 120)
                    result = None
                    
                    # ★ Pre-warm: detect idle and trigger soft recovery BEFORE first attempt
                    # This prevents 403 cascade — cheaper than recovering after failure
                    await self._maybe_prewarm(account)
                    
                    for attempt in range(max_retries + 1):
                        # ★ Layer 4+5 gate: check BEFORE each retry (skip attempt 0)
                        # Both apply to ALL workers on this account (per-email key)
                        # → 1 worker hits 403 → all workers on same account must wait
                        if attempt > 0:
                            # Layer 4: Cooldown — exponential backoff (30→180s)
                            # set_account_cooldown() was triggered by 403 handler below
                            await self.wait_for_cooldown(account.email)
                            # Layer 5: Circuit Breaker — extension health
                            await self._wait_for_circuit(account.email)
                            # Re-check cooldown AFTER circuit wake — CircuitBreaker
                            # HALF-OPEN probe may have reset cooldown timer
                            await self.wait_for_cooldown(account.email)
                            
                            # ★ reCAPTCHA readiness gate: after cooldown, tab may have
                            # been kept alive via keepalive but reCAPTCHA still needs
                            # verification. If not ready → requeue instead of wasting
                            # a submit attempt on a guaranteed 403.
                            rc_ok = await self._wait_for_recaptcha_ready(
                                account, max_wait=30.0
                            )
                            if not rc_ok:
                                log.warning(
                                    f"[Foreman:{account.email}] Task {task.id}: "
                                    f"reCAPTCHA NOT ready after cooldown (attempt {attempt+1}) "
                                    f"— requeuing task"
                                )
                                self._dispatcher.requeue_task(task)
                                account.release_workers(worker_count)
                                worker_count = 0
                                result = None
                                break
                        
                        # Re-upload continuation frame on retry (mediaId may have expired)
                        if (attempt > 0 and task.parent_task_id
                                and (task.continuation_frame_local_path or task.image_uris)):
                            async with self._account_rate_locks[account.email]:
                                # Fix G7: Anti-detect delay before frame re-upload
                                if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else True:
                                    await self._burst_controller.wait(account.email)
                                fresh_uri = await self._re_upload_continuation_frame(task, account)
                                if fresh_uri:
                                    task.image_uris = [fresh_uri]
                        
                        # Lock: covers anti-detect delay + single API call only
                        async with self._account_rate_locks[account.email]:
                            # Fix F: Re-check cooldown INSIDE rate lock.
                            # While this worker waited for the lock, another worker on
                            # the same account may have hit 403 → set_cooldown().
                            # Without this check, we'd waste a reCAPTCHA token + get 403.
                            if self.is_account_on_cooldown(account.email):
                                log.info(
                                    f"[Foreman:{account.email}] Task {task.id}: cooldown detected INSIDE "
                                    f"rate lock — requeueing task, will retry after cooldown"
                                )
                                # Fix F2: Requeue task instead of breaking out of retry loop.
                                # Old code used `break` which exited the for-loop entirely,
                                # causing the task to be PERMANENTLY FAILED even though it
                                # never actually ran. Now we requeue and let another worker
                                # pick it up after cooldown expires.
                                self._dispatcher.requeue_task(task)
                                account.release_workers(worker_count)
                                worker_count = 0
                                result = None  # No result — task was never attempted
                                break  # Exit retry loop — task is safely back in queue
                            
                            # ── RC2: Global cross-account submit gate ──
                            # Wait for minimum gap since LAST submit (any account).
                            # Prevents coordinated bot detection across accounts on same IP.
                            async with self._global_submit_lock:
                                now = time.time()
                                elapsed = now - self._global_last_submit_ts
                                gap = self._GLOBAL_MIN_SUBMIT_GAP
                                if elapsed < gap:
                                    wait_time = gap - elapsed
                                    log.info(
                                        f"[GlobalGate:{account.email}] Waiting {wait_time:.1f}s "
                                        f"(global inter-submit spacing)"
                                    )
                                    await asyncio.sleep(wait_time)
                                # Re-check cooldown after global wait
                                if self.is_account_on_cooldown(account.email):
                                    log.info(
                                        f"[Foreman:{account.email}] Task {task.id}: cooldown detected "
                                        f"after global gate — requeueing"
                                    )
                                    self._dispatcher.requeue_task(task)
                                    account.release_workers(worker_count)
                                    worker_count = 0
                                    result = None
                                    break
                                self._global_last_submit_ts = time.time()
                            
                            # Step 6: Anti-Detect Spam — adaptive delay (SERIALIZED per account)
                            if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else getattr(self, '_anti_detect_enabled', True):
                                # M1 fix: Use AdaptiveBurstController for intelligent pacing
                                # Tightens delay after 10 successes, backs off on 403s
                                _wt = (task.workflow_type or "").upper()
                                if _wt in ("T2I", "I2I"):
                                    self._dispatcher.update_progress(
                                        task.id, 15,
                                        f"⏳ Waiting ({self._burst_controller.get_delay(account.email):.0f}s)"
                                    )
                                log.info(
                                    f"[Foreman:{account.email}] Task {task.id}: adaptive delay "
                                    f"({self._burst_controller.get_delay(account.email):.1f}s base) → submit "
                                    f"attempt {attempt+1}/{max_retries+1} [{task.stage.value}] "
                                    f"progress={task.progress}%"
                                )
                                await self._burst_controller.wait(account.email)
                        
                            try:
                                # ★ PRIMARY PATH: Extension-based submission
                                # Token generated + used atomically in page context (<100ms)
                                # Eliminates reCAPTCHA token expiry + header mismatch issues
                                ext_bridge = getattr(account, 'extension_bridge', None)
                                use_extension = (
                                    ext_bridge is not None
                                    and ext_bridge.is_connected(account.email)
                                )
                                
                                if use_extension:
                                    _wt_sub = (task.workflow_type or "").upper()
                                    if _wt_sub in ("T2I", "I2I"):
                                        self._dispatcher.update_progress(
                                            task.id, 30,
                                            f"🎨 Submitting {_wt_sub}..."
                                        )
                                    log.info(
                                        f"[Foreman:{account.email}] Task {task.id}: submitting via Extension "
                                        f"(page context fetch)"
                                    )
                                    endpoint_key, body = self._api_client.build_request_body(
                                        workflow_type=task.workflow_type,
                                        prompt=task.prompt or "",
                                        project_id=account.project_id or "",
                                        aspect_ratio=task.aspect_ratio or "VIDEO_ASPECT_RATIO_LANDSCAPE",
                                        model=task.model or "veo_3_1_t2v_fast_ultra",
                                        output_count=task.output_count or 4,
                                        seed=task.seed,
                                        paygate_tier=account.paygate_tier or "PAYGATE_TIER_TWO",
                                        image_uris=task.image_uris,
                                    )
                                    
                                    # ── Debug: log request body structure ──
                                    import json as _json
                                    wt_label = (task.workflow_type or "").upper()
                                    log.info(
                                        f"[Foreman:{account.email}] 📦 Request body for {wt_label}:\n"
                                        f"  endpoint = {endpoint_key}\n"
                                        f"  body keys = {list(body.keys())}\n"
                                        f"  timeout = {timeout}s"
                                    )
                                    if wt_label in ("T2I", "I2I"):
                                        # Show full nested structure for image endpoints (no truncation)
                                        body_preview = _json.dumps(body, indent=2, ensure_ascii=False)
                                        log.debug(f"[Foreman:{account.email}] Full {wt_label} body:\n{body_preview}")
                                    else:
                                        # Show compact summary for video endpoints
                                        log.debug(
                                            f"[Foreman:{account.email}] body summary: "
                                            f"prompt={str(task.prompt)[:60]!r}, "
                                            f"model={task.model}, "
                                            f"outputs={task.output_count}"
                                        )
                                    
                                    ext_result = await asyncio.wait_for(
                                        ext_bridge.submit_prompt(
                                            email=account.email,
                                            endpoint=endpoint_key,
                                            body=body,
                                            needs_recaptcha=True,
                                            timeout=timeout,
                                        ),
                                        timeout=timeout + 5,  # outer guard
                                    )
                                    
                                    # Convert Extension response → WorkerResult
                                    if ext_result and ext_result.get('success'):
                                        _wt_ok = (task.workflow_type or "").upper()
                                        if _wt_ok in ("T2I", "I2I"):
                                            self._dispatcher.update_progress(
                                                task.id, 60,
                                                f"✅ {_wt_ok} response received"
                                            )
                                        data = ext_result.get('data', {})
                                        op_names = []
                                        sc_ids = []
                                        output_uris = []
                                        t2i_media_ids = []
                                        if 'operations' in data:
                                            for op in data['operations']:
                                                op_obj = op.get('operation', {})
                                                name = op_obj.get('name') if isinstance(op_obj, dict) else None
                                                if name:
                                                    op_names.append(name)
                                                sc_ids.append(op.get('sceneId', ''))
                                        if 'media' in data:
                                            for item in data['media']:
                                                gen_img = (item.get('image') or {}).get('generatedImage', {})
                                                fife_url = gen_img.get('fifeUrl', '')
                                                # HAR verified: mediaId is empty, actual ID is in 'name'
                                                mid = item.get('mediaId', '') or item.get('name', '')
                                                if fife_url:
                                                    output_uris.append(fife_url)
                                                    t2i_media_ids.append(mid)
                                            # Debug: log mediaId extraction result
                                            log.info(
                                                f"[T2I-Parse] {len(output_uris)} image(s), "
                                                f"mediaIds={t2i_media_ids}, "
                                                f"media keys={[list(m.keys()) for m in data.get('media', [])[:2]]}"
                                            )
                                        
                                        result = WorkerResult(
                                            success=True,
                                            operation_name=op_names[0] if op_names else None,
                                            scene_id=sc_ids[0] if sc_ids else None,
                                            operation_names=op_names,
                                            scene_ids=sc_ids,
                                            output_uris=output_uris,
                                            media_ids=t2i_media_ids,
                                            data=data,
                                        )
                                    elif ext_result:
                                        # Extension submission failed
                                        error_msg = ext_result.get('error', '')
                                        status_code = ext_result.get('status', 0)
                                        resp_data = ext_result.get('data', {})
                                        
                                        # Extract detailed error from API response body
                                        if not error_msg and isinstance(resp_data, dict):
                                            api_err = resp_data.get('error', {})
                                            if isinstance(api_err, dict):
                                                error_msg = api_err.get('message', '') or api_err.get('status', '')
                                            elif isinstance(api_err, str):
                                                error_msg = api_err
                                        
                                        if status_code == 403:
                                            # Log full 403 response for debugging
                                            log.warning(
                                                f"[Extension] 403 response data for {account.email}: "
                                                f"{str(resp_data)[:500]}"
                                            )
                                            error_msg = f"403 Forbidden: {error_msg}"
                                        result = WorkerResult(
                                            success=False,
                                            error=error_msg or f"Extension submission failed (HTTP {status_code})",
                                        )
                                    else:
                                        # ext_result is None (timeout or connection lost)
                                        result = WorkerResult(
                                            success=False,
                                            error="Extension submission returned None (timeout or disconnected)",
                                        )
                                else:
                                    # ★ FALLBACK: Traditional worker.execute() path
                                    log.info(
                                        f"[Foreman:{account.email}] Task {task.id}: submitting via worker.execute() "
                                        f"(Extension unavailable)"
                                    )
                                    result = await asyncio.wait_for(
                                        worker.execute(task, account, paygate_tier=account.paygate_tier),
                                        timeout=timeout,
                                    )
                            except asyncio.TimeoutError:
                                result = WorkerResult(
                                    success=False,
                                    error=f"Request timed out after {timeout}s"
                                )
                            
                            # M2: Defense-in-depth — Worker.execute() handles primary
                            # invalidation, but this covers TimeoutError (L833) where
                            # Worker.execute may not have finished its cleanup.
                            # invalidate_recaptcha() is idempotent — safe to double-call.
                            # For Extension path: no-op (Extension manages its own reCAPTCHA).
                            account.invalidate_recaptcha()
                        # Rate lock released here — other workers can now submit
                        
                        if result.success:
                            # M1 fix: Record success for adaptive delay tightening
                            self._burst_controller.record_success(account.email)
                            break  # Success — exit retry loop
                        
                        # Layer 1: Network error → INSTANT pause, re-queue task
                        if self._is_network_error(result.error or ""):
                            log.warning(f"🌐 Network error → auto-pausing: {result.error}")
                            await self.pause()
                            if self._on_connectivity_changed:
                                self._on_connectivity_changed(False, 9999)
                            self._dispatcher.requeue_task(task)
                            # Workers released by finally block
                            return  # Exit worker loop — task preserved in queue
                        
                        # Auth errors → special handling, no retry
                        if self._is_auth_error(result.error or ""):
                            break
                        
                        # Non-auth error — retry with backoff (OUTSIDE rate lock)
                        task.retry_attempts = attempt + 1
                        if attempt < max_retries:
                            # Risk 3 fix: Higher initial backoff for 403 cooldown
                            # Old: 2, 4, 8, 16, 30  →  New: 5, 10, 20, 40, 60
                            backoff = min(5 * (2 ** attempt), 60)
                            
                            # ╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝
                            # TIERED 403 RECOVERY STATE MACHINE
                            # Phase 0: 3x 403 → kill browser + restart
                            # Phase 1: 3x 403 → copy Variations + warmup tabs
                            # Phase 2: give up (all tiers exhausted)
                            # Backoff within each phase: 3s, 5s, 8s
                            # ╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝
                            
                            # ╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝
                            # UNIFIED RECOVERY STATE MACHINE
                            # Merges reCAPTCHA + 403 errors into one soft-first
                            # escalation path. Chrome kill only at Phase 2.
                            #
                            # Phase 0: wait readiness → reload tabs (NO kill)
                            # Phase 1: soft recovery — navigate away/back (NO kill)
                            # Phase 2: hard browser restart (LAST RESORT)
                            # Phase 3: give up (all tiers exhausted)
                            # ╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝╝
                            error_lower = (result.error or "").lower()
                            recaptcha_fail = "recaptcha" in error_lower
                            acct_email = account.email
                            
                            if recaptcha_fail or "403" in (result.error or ""):
                                # M1 fix: Record error for adaptive delay backoff
                                status = 403 if "403" in (result.error or "") else 500
                                self._burst_controller.record_error(account.email, status)
                                
                                # Circuit breaker: track consecutive 403 for this account
                                self.record_circuit_403(account.email)
                                
                                # Layer 4: Cooldown — apply to ALL workers on this account
                                self.set_account_cooldown(account.email, f"403/{result.error}")
                                
                                # ═══ SMART RECOVERY — replaces Phase 0-3 state machine ═══
                                # Diagnose error → try targeted remedies → verify health
                                # If all remedies fail → suspend account + migrate tasks
                                consecutive_403 = self._circuit_consecutive_403.get(acct_email, 0)
                                
                                # Build context for error classifier
                                recovery_context = {
                                    "consecutive_403": consecutive_403,
                                    "token_len": getattr(result, '_token_len', 9999),
                                }
                                # Get x-client-data length if available
                                ext_bridge = getattr(account, 'extension_bridge', None)
                                if ext_bridge and hasattr(ext_bridge, '_header_cache'):
                                    cache = ext_bridge._header_cache.get(acct_email, {})
                                    recovery_context["xcd_len"] = len(cache.get("x-client-data", ""))
                                
                                recovery_result = await execute_recovery(
                                    account=account,
                                    error_msg=result.error or "",
                                    context=recovery_context,
                                    ext_bridge=ext_bridge,
                                    dispatcher=self._dispatcher,
                                    credit_window=self._credit_window,
                                    multi_account=self._account_manager,
                                )
                                
                                if recovery_result.failover:
                                    # Account suspended, tasks migrated — requeue this task too
                                    log.warning(
                                        f"[⚡Recovery] {acct_email}: FAILOVER — "
                                        f"account suspended, requeuing task {task.id}"
                                    )
                                    self._dispatcher.requeue_task(task)
                                    # Add to excluded so it won't come back
                                    if not hasattr(task, 'excluded_accounts'):
                                        task.excluded_accounts = set()
                                    task.excluded_accounts.add(acct_email)
                                    account.release_workers(worker_count)
                                    worker_count = 0
                                    result = None
                                    break  # Exit retry loop
                                
                                backoff = recovery_result.backoff or 5
                                
                                # Fix ⑧: Exponential backoff — scale with attempt
                                # attempt 0 → base, 1 → 1.5x, 2 → 2.25x, ...
                                # Prevents rapid-fire failures burning credits
                                backoff = min(int(backoff * (1.5 ** attempt)), 60)
                                
                                log.info(
                                    f"[Recovery] {acct_email}: recovery "
                                    f"{'OK' if recovery_result.success else 'tried'} "
                                    f"(remedy={recovery_result.remedy_used}, "
                                    f"backoff={backoff}s)"
                                )
                            else:
                                # Non-reCAPTCHA, non-403 errors: refresh headers
                                if account.extension_bridge:
                                    try:
                                        await account.extension_bridge.refresh_headers(
                                            account.email, timeout=10
                                        )
                                        log.info(f"[Recovery] {acct_email}: Extension headers refreshed")
                                        await self._wait_for_recaptcha_ready(account, max_wait=20.0)
                                    except Exception as e:
                                        log.debug(f"[Recovery] Extension header refresh failed: {e}")
                                    backoff = max(backoff, 10)
                            
                            log.warning(
                                f"[Foreman:{account.email}] Task {task.id} failed "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {result.error}. "
                                f"Retrying in {backoff}s..."
                            )
                            if await self._interruptible_sleep(backoff): break
                    
                    # Worker stays held until task fully completes (poll + download).
                    # This ensures max_workers limits actual concurrent tasks.
                    
                    # Fix F2: If task was requeued (cooldown inside rate lock),
                    # workers are already released and result is None.
                    # Skip result processing — task is back in queue.
                    if result is None and worker_count == 0:
                        continue
                    
                    # Step 8: Process final result
                    log.info(f"[Engine] Task {task.id}: result.success={result.success if result else 'NO_RESULT'}, "
                             f"operation_name={result.operation_name if result else 'N/A'}")
                    if result and result.success:
                        # Reset ALL recovery state on success — account is healthy
                        self._account_recovery_phase[account.email] = 0
                        self._account_phase_403_count[account.email] = 0
                        self._account_403_last_epoch[account.email] = -1
                        # Circuit breaker: success → close breaker, reset 403 counter
                        self.record_circuit_success(account.email)
                        # Lớp 4: Clear cooldown — account is healthy again
                        self.clear_account_cooldown(account.email)
                        # Pre-warm: record successful submit timestamp
                        self._last_successful_submit[account.email] = time.time()
                        # Smart Recovery: +1 credit on success
                        self._credit_window.record_success(account.email)
                        # Progressive unlock: signal other foremen to start
                        supervisor = self._supervisors.get(account.email)
                        if supervisor and not supervisor._first_submit_ok.is_set():
                            supervisor._first_submit_ok.set()
                            log.info(f"[{fid}] 🚀 First submit success → unlocking remaining foremen")
                        # Smart-Hide: countdown to re-hide browser after 403 recovery
                        _sh_remaining = self._smart_hide_rehide_countdown.get(account.email, 0)
                        if _sh_remaining > 0:
                            _sh_remaining -= 1
                            self._smart_hide_rehide_countdown[account.email] = _sh_remaining
                            if _sh_remaining <= 0:
                                # 3 successful prompts → re-hide browser
                                from config.settings import get_settings as _get_sh_settings2
                                if getattr(_get_sh_settings2(), 'smart_hide_enabled', True):
                                    if self._profiles_controller:
                                        self._profiles_controller.hide_debug_browser(account.email)
                                        log.info(f"[SmartHide] {account.email}: browser re-hidden after 3 successful prompts")
                            else:
                                log.info(f"[SmartHide] {account.email}: {_sh_remaining} more success(es) before re-hide")
                        # For async operations, start polling (slot held during poll)
                        if result.operation_name:
                            task.operation_name = result.operation_name
                            task.operation_names = list(result.operation_names)
                            task.scene_ids = list(result.scene_ids)
                            task.stage = TaskStage.SUBMITTED  # ★ Checkpoint: prompt submitted
                            task.state = TaskState.WAITING_POLL
                            
                            # ★ PARTIAL RESPONSE DETECTION: server returned fewer ops
                            expected = getattr(task, 'output_count', 0) or 0
                            actual = len(result.operation_names)
                            if expected > 0 and actual < expected:
                                variant_letters = "abcdefghijklmnopqrstuvwxyz"
                                prompt_num = getattr(task, 'prompt_index', 0) + 1
                                idx_str = str(prompt_num).zfill(3)
                                # Identify missing variants by letter
                                present = set(range(actual))
                                missing = [i for i in range(expected) if i not in present]
                                missing_labels = [
                                    f"{idx_str}{variant_letters[i]}" if i < len(variant_letters) else f"{idx_str}?"
                                    for i in missing
                                ]
                                log.warning(
                                    f"⚠️ PARTIAL SUBMIT: Task {task.id} requested {expected} variants "
                                    f"but server returned only {actual} operation IDs. "
                                    f"Missing variants: {', '.join(missing_labels)}. "
                                    f"These will appear as FAILED in the queue."
                                )
                            
                            log.info(
                                f"[Foreman:{account.email}] Submitted {len(result.operation_names)} ops "
                                f"→ concurrent pipeline (first={result.operation_name[:12]}...)"
                            )
                            # ★ CONCURRENT PIPELINE: fire-and-forget
                            # Foreman immediately loops back to pick next task
                            t = asyncio.create_task(
                                self._foreman_dispatch_workers(task, account, worker_count,
                                                              supervisor=supervisor)
                            )
                            active_pipelines.add(t)
                            t.add_done_callback(active_pipelines.discard)
                            worker_count = 0  # Ownership transferred to pipeline
                        else:
                            # Sync operation (T2I/I2I) — launch download+upscale pipeline
                            if result.output_uris:
                                log.info(
                                    f"[Engine] Task {task.id}: → T2I SYNC "
                                    f"({len(result.output_uris)} images, "
                                    f"{len(result.media_ids)} mediaIds) → pipeline"
                                )
                                # ★ Fire-and-forget pipeline: download → upscale → complete
                                t = asyncio.create_task(
                                    self._run_t2i_pipeline_bg(
                                        task, account,
                                        result.output_uris,
                                        result.media_ids,
                                        worker_count,
                                    )
                                )
                                active_pipelines.add(t)
                                t.add_done_callback(active_pipelines.discard)
                                worker_count = 0  # Ownership transferred
                            else:
                                log.warning(
                                    f"[Engine] Task {task.id}: → SYNC returned 0 outputs. "
                                    f"Response data keys: {list(result.data.keys()) if result.data else 'None'}. "
                                    f"This may indicate a T2I/I2I API issue."
                                )
                                self._dispatcher.complete_task(
                                    task.id,
                                    output_uris=[],
                                )
                    elif result:
                        error_msg = result.error or "Unknown error"
                        
                        if self._is_auth_error(error_msg):
                            # Auth error → fail task, manual re-login required
                            log.warning(f"Auth error for {account.email}: {error_msg} — manual re-login required")
                            self._dispatcher.fail_task(
                                task.id,
                                f"{error_msg} (auth error — please re-login manually via Browser button)"
                            )
                            self._error_count += 1
                            emit_event(EventType.TASK_FAILED, {
                                "task_id": task.id, "error": error_msg,
                                "reason": "auth_error",
                            }, source="engine")
                            if self._on_task_failed:
                                self._on_task_failed(task, error_msg)
                        else:
                            # Non-auth error after all retries exhausted
                            retry_info = f" (after {task.retry_attempts} retries)" if task.retry_attempts > 0 else ""
                            final_error = f"{error_msg}{retry_info}"
                            
                            # Auto-retry chain roots on transient errors
                            if self._should_auto_retry_chain(task, error_msg):
                                delay = random.uniform(30, 60)
                                task.chain_retry_count += 1
                                log.warning(
                                    f"🔄 [ChainRetry] Root {task.id} failed but has chain → "
                                    f"auto-retry #{task.chain_retry_count}/3 in {delay:.0f}s"
                                )
                                # Release workers before sleep
                                account.release_workers(worker_count)
                                worker_count = 0
                                # Set task to FAILED first — retry_chain() requires FAILED state
                                task.state = TaskState.FAILED
                                task.error = final_error
                                self._dispatcher.decrement_running()
                                if await self._interruptible_sleep(delay): break
                                # Use retry_chain to properly restore dependency tree
                                self._dispatcher.retry_chain(task.id)
                                continue  # Back to worker loop, task is re-queued
                            
                            log.error(f"Task {task.id} PERMANENTLY FAILED: {final_error}")
                            self._dispatcher.fail_task(task.id, final_error)
                            self._error_count += 1
                            emit_event(EventType.TASK_FAILED, {
                                "task_id": task.id, "error": final_error,
                                "reason": "retries_exhausted",
                            }, source="engine")
                            if self._on_task_failed:
                                self._on_task_failed(task, final_error)
                    else:
                        # No result at all — fail task to cascade-fail children
                        # and keep _running_count accurate
                        self._dispatcher.fail_task(
                            task.id, "Worker returned no result"
                        )
                        self._error_count += 1
                        if self._on_task_failed:
                            self._on_task_failed(task, "Worker returned no result")
                        # Workers released by finally block
                
                except Exception as inner_e:
                    raise inner_e
                finally:
                    # ★ Bug #4 fix: Centralized cleanup — guarantees workers released
                    # regardless of which code path was taken (success, error, exception)
                    if worker_count > 0:
                        account.release_workers(worker_count)
                        worker_count = 0
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[Foreman:{account.email}] Unexpected error: {e}")
                # Fail the task if one was acquired — prevents stuck RUNNING
                # state and cascade-fails any WAITING children
                try:
                    if task and task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                        self._dispatcher.fail_task(
                            task.id, f"Unexpected error: {e}"
                        )
                        self._error_count += 1
                        emit_event(EventType.TASK_FAILED, {
                            "task_id": task.id, "error": str(e),
                            "reason": "unexpected_exception",
                        }, source="engine")
                        if self._on_task_failed:
                            self._on_task_failed(task, str(e))
                except Exception:
                    pass
                await asyncio.sleep(1.0)
    
        # ── Foreman loop exited: wait for remaining pipelines ──
        if active_pipelines:
            log.info(
                f"[Foreman:{account.email}] Stopping — waiting for "
                f"{len(active_pipelines)} active pipeline(s)..."
            )
            await asyncio.gather(*active_pipelines, return_exceptions=True)
    
    async def _run_pipeline_bg(
        self, task: Task, account: AccountManager, worker_count: int
    ):
        """Background wrapper: runs poll→download→upscale, releases workers on exit."""
        try:
            await self._poll_operation(task, account)
        except asyncio.CancelledError:
            log.warning(f"[Pipeline:{account.email}] Task {task.id} cancelled")
        except Exception as e:
            log.error(f"[Pipeline:{account.email}] Task {task.id} error: {e}")
            if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                self._dispatcher.fail_task(task.id, f"Pipeline error: {e}")
                self._error_count += 1
                if self._on_task_failed:
                    self._on_task_failed(task, str(e))
        finally:
            if worker_count > 0:
                account.release_workers(worker_count)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Phase 1: Per-Video Worker Architecture (NEW)
    # ═══════════════════════════════════════════════════════════════════════

    async def _foreman_dispatch_workers(
        self, task: Task, account: AccountManager, worker_count: int,
        supervisor: 'AccountSupervisor' = None,
    ):
        """Foreman dispatches N autonomous workers (1 per video op).
        
        Replaces _run_pipeline_bg → _poll_operation monolithic flow.
        Each worker independently: poll → download → upscale → report.
        Finalizer merges results after all workers complete.
        """
        try:
            # ── Checkpoint resume: skip poll if already past GENERATED ──
            if task.stage in (TaskStage.GENERATED, TaskStage.DOWNLOADED_720,
                              TaskStage.UPSCALING, TaskStage.UPSCALED):
                log.info(
                    f"[Foreman:{account.email}] Task {task.id}: "
                    f"resuming from {task.stage.value} (skip poll)"
                )
                await self._resume_from_checkpoint(task, account)
                return

            ops = task.operation_names
            scene_ids = task.scene_ids
            total = len(ops)

            if total == 0:
                log.warning(f"[Foreman:{account.email}] Task {task.id}: 0 ops, nothing to dispatch")
                return

            # ── G9: Pre-allocate VideoOutputInfo slots ──
            task.video_outputs = []
            for i, op in enumerate(ops):
                sid = scene_ids[i] if i < len(scene_ids) else ""
                vo = VideoOutputInfo(
                    index=i,
                    operation_name=op,
                    scene_id=sid,
                    media_id="",
                    quality="polling",
                )
                task.video_outputs.append(vo)
                # G10: Worker identity logging
                log.info(
                    f"[Foreman:{account.email}] Task {task.id}: "
                    f"Slot #{i} ← Worker #{i+1} ← op {op[:16]}..."
                )

            # ── Dispatch N workers (1 per op) ──
            results_dict: Dict[int, WorkerVideoResult] = {}
            self._dispatcher.update_progress(task.id, 25, "⏳ Waiting in queue")

            async with asyncio.TaskGroup() as tg:
                for i, op in enumerate(ops):
                    sid = scene_ids[i] if i < len(scene_ids) else ""
                    tg.create_task(
                        self._video_worker(
                            task, account, op, sid, i, results_dict,
                            supervisor=supervisor,
                        )
                    )

            # ── All workers done → finalize ──
            await self._finalize_task_v2(task, account, results_dict)

        except* asyncio.CancelledError:
            log.warning(f"[Foreman:{account.email}] Task {task.id} cancelled")
        except* Exception as eg:
            errors = [str(e) for e in eg.exceptions]
            log.error(
                f"[Foreman:{account.email}] Task {task.id} worker errors: "
                f"{errors[:3]}..."
            )
            if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                self._dispatcher.fail_task(task.id, f"Worker errors: {errors[0]}")
                self._error_count += 1
                if self._on_task_failed:
                    self._on_task_failed(task, errors[0])
        finally:
            if worker_count > 0:
                account.release_workers(worker_count)

    async def _video_worker(
        self, task: Task, account: AccountManager,
        op_name: str, scene_id: str, video_index: int,
        results_dict: Dict[int, 'WorkerVideoResult'],
        supervisor: 'AccountSupervisor' = None,
    ):
        """1 Worker = 1 Video: self-poll → download → upscale → report.
        
        Autonomous — no coordinator. Each worker writes to its own
        results_dict[video_index] slot (no race condition).
        
        DD5: supervisor back-reference enables ownership tracing:
        Worker → Foreman → CHỦ (AccountSupervisor) → Account
        """
        email = account.email
        log_prefix = f"[Worker:{email[:12]}:V{video_index}]"
        
        try:
            # ── Phase 1: Self-poll op ──
            task.video_outputs[video_index].quality = "polling"
            fife_url, media_id = await self._worker_poll_op(
                task, account, op_name, scene_id, video_index
            )

            if not fife_url:
                log.warning(f"{log_prefix} Poll returned no result (failed/timeout)")
                task.video_outputs[video_index].quality = "failed"
                results_dict[video_index] = WorkerVideoResult(
                    index=video_index, op_name=op_name,
                    quality="failed", error="Poll failed or timeout",
                )
                return

            # Update VideoOutputInfo with poll result
            task.video_outputs[video_index].media_id = media_id
            task.video_outputs[video_index].quality = "downloading"
            log.info(f"{log_prefix} ✅ SUCCESSFUL → downloading")

            # ── Phase 2: Download 720p ──
            local_720p = await self._download_single(
                task, account, fife_url, video_index, "720p"
            )

            if not local_720p:
                log.warning(f"{log_prefix} Download failed")
                task.video_outputs[video_index].quality = "failed"
                results_dict[video_index] = WorkerVideoResult(
                    index=video_index, op_name=op_name,
                    media_id=media_id, fife_url=fife_url,
                    quality="failed", error="Download failed",
                )
                return

            task.video_outputs[video_index].file_720p = local_720p
            task.video_outputs[video_index].quality = "720p"

            # ── Phase 2.5: Generate thumbnail ──
            thumb_path = await self._generate_thumbnail_for_worker(
                task, local_720p, video_index
            )
            if thumb_path:
                task.video_outputs[video_index].thumbnail_path = thumb_path

            # ── Phase 3: Upscale (if needed) ──
            local_final = local_720p
            final_quality = "720p"

            if task.download_quality != "720p" and media_id:
                # Check workload priority mode
                if self._workload_priority == 'prompts_first':
                    # G7: Delegate to background UpscaleQueue
                    from core.upscale_queue import UpscaleJob
                    self._upscale_queue.enqueue(UpscaleJob(
                        task_id=task.id,
                        account_email=email,
                        original_account=email,  # DD6: track original for failover tracing
                        media_ids=[media_id],
                        output_uris=[fife_url],
                        target_quality=task.download_quality,
                        aspect_ratio=task.aspect_ratio,
                    ))
                    # G4: CRITICAL — decrement running to unblock UpscaleQueue
                    self._dispatcher.decrement_running()
                    log.info(f"{log_prefix} Delegated upscale → UpscaleQueue")
                    # Worker returns early with 720p quality
                else:
                    # Inline upscale (upscale_priority mode)
                    upscaled = await self._upscale_single(
                        task, account, fife_url, media_id, video_index
                    )
                    if upscaled:
                        local_final = upscaled
                        final_quality = task.download_quality
                        task.video_outputs[video_index].file_upscaled = upscaled
                        task.video_outputs[video_index].quality = final_quality
                        log.info(f"{log_prefix} ✅ Upscaled to {final_quality}")

            # ── Report result ──
            results_dict[video_index] = WorkerVideoResult(
                index=video_index, op_name=op_name,
                media_id=media_id, fife_url=fife_url,
                file_720p=local_720p, file_final=local_final,
                quality=final_quality, thumbnail_path=thumb_path or "",
            )

        except asyncio.CancelledError:
            # G6: Worker must be cancellable
            log.info(f"{log_prefix} Cancelled")
            results_dict[video_index] = WorkerVideoResult(
                index=video_index, op_name=op_name,
                quality="failed", error="Cancelled",
            )
            raise
        except Exception as e:
            log.error(f"{log_prefix} Error: {e}")
            task.video_outputs[video_index].quality = "failed"
            results_dict[video_index] = WorkerVideoResult(
                index=video_index, op_name=op_name,
                quality="failed", error=str(e),
            )

    async def _worker_poll_op(
        self, task: Task, account: AccountManager,
        op_name: str, scene_id: str, video_index: int,
    ) -> tuple:
        """Worker self-polls its own op until DONE.
        
        Returns: (fife_url, media_id) or (None, None) if FAILED/timeout.
        1 op per API call — fully isolated from other workers.
        """
        from config.constants import AppConstants
        log_prefix = f"[Worker:{account.email}:#{video_index}]"
        
        elapsed = 0
        max_poll_time = AppConstants.MAX_POLL_TIME
        status = "MEDIA_GENERATION_STATUS_PENDING"
        poll_count = 0

        while elapsed < max_poll_time and not self._stop_event.is_set():
            # 2-phase poll interval
            base = (AppConstants.POLL_PHASE1_INTERVAL
                    if elapsed < AppConstants.POLL_PHASE1_DURATION
                    else AppConstants.POLL_PHASE2_INTERVAL)
            jitter = random.uniform(0, base * 0.3)
            await asyncio.sleep(base + jitter)
            elapsed += base + jitter

            # Cancellation check
            if task.state == TaskState.CANCELLED:
                log.info(f"{log_prefix} Task cancelled during poll")
                return None, None

            try:
                token = await account.ensure_valid_token()
                if not token:
                    log.warning(f"{log_prefix} No valid token, retrying...")
                    continue

                # Per-worker poll: 1 op per API call
                sem = self._get_api_semaphore(account.email)
                async with sem:
                    response = await self._api_client.check_status(
                        access_token=token,
                        recaptcha_token="",
                        operations=[{
                            "operation": {"name": op_name},
                            "sceneId": scene_id,
                            "status": status,
                        }],
                        account_headers=account.get_api_headers(),
                    )

                if not response.success:
                    if response.response_code == 401:
                        await account.refresh_access_token()
                    else:
                        log.warning(f"{log_prefix} Poll failed: {response.error}")
                    continue

                ops = response.data.get("operations", [])
                if not ops:
                    continue

                op = ops[0]
                op_status = op.get("status", "")
                poll_count += 1

                if op_status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                    details = self._extract_output_details({"operations": [op]})
                    if details:
                        return details[0]["fifeUrl"], details[0]["mediaId"]
                    return None, None

                elif op_status == "MEDIA_GENERATION_STATUS_FAILED":
                    error = op.get("error", {}).get("message", "")
                    log.warning(f"{log_prefix} Op FAILED: {error}")
                    return None, None

                else:
                    # Update status for next poll + progress
                    old_status = status
                    status = op_status
                    if status != old_status:
                        log.info(f"{log_prefix} {old_status} → {status}")
                    
                    # G1: Per-worker progress (25-80% range, proportional)
                    if "ACTIVE" in status:
                        progress = min(80, 40 + int(poll_count * 5))
                        status_label = "🔥 Processing"
                    elif "PENDING" in status:
                        progress = min(35, 25 + poll_count * 2)
                        status_label = "⏳ Queued on server"
                    else:
                        progress = min(80, 25 + int(elapsed / max_poll_time * 55))
                        status_label = "⏳ Working"
                    task.video_outputs[video_index].quality = "polling"
                    
                    # Push progress to dispatcher → UI (was missing!)
                    self._dispatcher.update_progress(task.id, progress, status_label)

            except Exception as e:
                log.warning(f"{log_prefix} Poll error: {e}")
                continue

        log.warning(f"{log_prefix} Poll timeout ({max_poll_time}s)")
        return None, None  # Timeout

    async def _download_single(
        self, task: Task, account: AccountManager,
        fife_url: str, video_index: int,
        quality_subfolder: str = "720p",
    ) -> str:
        """Download a single video. Returns local file path or empty string."""
        log_prefix = f"[Worker:{account.email}:#{video_index}]"
        try:
            paths = await self._download_outputs(
                task, [fife_url],
                quality_subfolder=quality_subfolder,
                generate_thumbnails=False,
            )
            if paths and paths[0]:
                log.info(f"{log_prefix} Downloaded {quality_subfolder}")
                return paths[0]
            log.warning(f"{log_prefix} Download returned empty")
            return ""
        except Exception as e:
            log.error(f"{log_prefix} Download error: {e}")
            return ""

    async def _upscale_single(
        self, task: Task, account: AccountManager,
        fife_url: str, media_id: str, video_index: int,
    ) -> str:
        """Upscale a single video (inline). Returns upscaled local path or empty.
        
        Wraps _auto_upscale for a single video — the heavy lifting is
        handled by the existing upscale infrastructure.
        """
        log_prefix = f"[Worker:{account.email}:#{video_index}]"
        try:
            task.video_outputs[video_index].upscale_status = "submitting"
            upscale_results = await self._auto_upscale(
                task, account, [fife_url], [media_id]
            )
            if upscale_results and upscale_results[0]:
                # Download the upscaled video
                upscaled_uri = upscale_results[0]
                dl_paths = await self._download_outputs(
                    task, [upscaled_uri],
                    quality_subfolder=task.download_quality,
                    generate_thumbnails=False,
                )
                if dl_paths and dl_paths[0]:
                    task.video_outputs[video_index].upscale_status = "success"
                    return dl_paths[0]
            
            task.video_outputs[video_index].upscale_status = "failed"
            log.warning(f"{log_prefix} Upscale failed, keeping 720p")
            return ""
        except Exception as e:
            log.error(f"{log_prefix} Upscale error: {e}")
            task.video_outputs[video_index].upscale_status = "failed"
            task.video_outputs[video_index].upscale_error = str(e)
            return ""

    async def _generate_thumbnail_for_worker(
        self, task: Task, video_path: str, video_index: int,
    ) -> str:
        """Generate thumbnail for a single video. Returns path or empty."""
        try:
            if not self._frame_extractor.is_available:
                return ""
            
            from pathlib import Path as _Path
            thumb_dir = _Path(video_path).parent / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = str(thumb_dir / f"thumb_{video_index:02d}.jpg")
            
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                self._process_pool,
                self._frame_extractor.extract_frame,
                video_path,
                thumb_path,
                0,     # Start of video
                False, # from_end=False
            )
            return thumb_path if result else ""
        except Exception as e:
            log.warning(f"[Worker:#{video_index}] Thumbnail error: {e}")
            return ""

    async def _finalize_task_v2(
        self, task: Task, account: AccountManager,
        results_dict: Dict[int, 'WorkerVideoResult'],
    ):
        """Finalizer: merge all worker results → complete task.
        
        Runs after ALL workers have finished (success or fail).
        Handles: partial failure retry, continuation frame, completion.
        """
        email = account.email
        total = len(task.operation_names)
        successes = [r for r in results_dict.values() if r.quality != "failed"]
        failures = [r for r in results_dict.values() if r.quality == "failed"]
        success_count = len(successes)
        failed_count = len(failures)

        log.info(
            f"[Finalizer:{email}] Task {task.id}: "
            f"{success_count}/{total} succeeded, {failed_count} failed"
        )

        # ── G3: Handle all-failed ──
        if success_count == 0:
            self._dispatcher.fail_task(task.id, "All video operations failed")
            self._error_count += 1
            emit_event(EventType.TASK_FAILED, {
                "task_id": task.id, "error": "All video operations failed",
                "reason": "all_ops_failed",
            }, source="engine")
            if self._on_task_failed:
                self._on_task_failed(task, "All video operations failed")
            return

        # ── G3: Partial failure auto-retry ──
        if failed_count > 0:
            variant_letters = "abcdefghijklmnopqrstuvwxyz"
            prompt_num = getattr(task, 'prompt_index', 0) + 1
            failed_labels = []
            for r in failures:
                idx = r.index
                label = f"{str(prompt_num).zfill(3)}{variant_letters[idx] if idx < len(variant_letters) else '?'}"
                failed_labels.append(label)
            
            log.warning(
                f"⚠️ Task {task.id}: PARTIAL FAILURE — "
                f"{success_count}/{total} succeeded, {failed_count} failed. "
                f"Missing: {', '.join(failed_labels)}"
            )
            self._auto_retry_partial_failure(task, failed_count, failed_labels)
            self._dispatcher.update_progress(
                task.id, 85,
                f"⚠️ {success_count}/{total} done, {failed_count} retrying"
            )
        else:
            self._dispatcher.update_progress(task.id, 85, "✅ Generation complete")

        # ── Merge results by submit order ──
        task.stage = TaskStage.GENERATED
        task.upscale_media_ids = [r.media_id for r in successes]

        # Build final paths
        final_paths = []
        for i in sorted(results_dict.keys()):
            r = results_dict[i]
            if r.file_final:
                final_paths.append(r.file_final)
        
        if final_paths:
            task.output_uris = final_paths

        # ── G8: Continuation frame (from video[0] only, 1 location) ──
        task.stage = TaskStage.DOWNLOADED_720
        self._sync_overall_upscale_status(task)

        continuation_frame_uri = None
        continuation_frame_local = None
        if (
            (getattr(self._settings, 'continuation_enabled', True) if self._settings else True)
            and self._dispatcher.has_children(task.id)
            and task.output_uris
        ):
            self._dispatcher.update_progress(task.id, 95, "📸 Extracting continuation frame")
            frame_result = await self._extract_continuation_frame(
                task, account, task.output_uris[0]
            )
            if frame_result:
                continuation_frame_uri, continuation_frame_local = frame_result
                # Smart cooldown
                await self._wait_for_recaptcha_ready(account, max_wait=30.0)

        # ── Complete task ──
        task.stage = TaskStage.COMPLETED
        self._dispatcher.update_progress(task.id, 100, "✅ Done")
        self._dispatcher.complete_task(
            task.id,
            output_uris=task.output_uris,
            continuation_frame_uri=continuation_frame_uri,
            continuation_frame_local_path=continuation_frame_local,
        )
        self._download_count += len(task.output_uris or [])
        emit_event(EventType.TASK_COMPLETED, {
            "task_id": task.id,
            "outputs": len(task.output_uris or []),
            "account": task.assigned_account,
        }, source="engine")
        self._save_manifest(task)

    async def _resume_from_checkpoint(self, task: Task, account: AccountManager):
        """Resume task from saved checkpoint stage (skip completed phases).
        
        Delegates to the existing _poll_operation for checkpoint resume logic,
        since the resume paths are complex and already well-tested.
        """
        # Reuse existing checkpoint resume code in _poll_operation
        # (L2909-3011 handles GENERATED, DOWNLOADED_720, UPSCALING, UPSCALED)
        await self._poll_operation(task, account)


    async def _run_t2i_pipeline_bg(
        self, task: Task, account: AccountManager,
        fife_urls: list, media_ids: list,
        worker_count: int,
    ):
        """T2I pipeline: download 1K images → upscale to 4K → complete task.
        
        Args:
            fife_urls: Remote FIFE URLs for generated images (1K resolution)
            media_ids: mediaId per image (needed for upscale API)
            worker_count: Worker slots to release on exit
        """
        try:
            from pathlib import Path
            import base64
            
            total = len(fife_urls)
            log.info(
                f"[T2I-Pipeline:{account.email}] Task {task.id}: "
                f"downloading {total} image(s)"
            )
            
            # Initialize video_outputs for T2I (mirrors video pipeline)
            # Without this, thumbnail_path won't be stored on VideoOutputInfo
            if not task.video_outputs:
                from core.dispatcher import VideoOutputInfo
                for idx in range(total):
                    mid = media_ids[idx] if idx < len(media_ids) else ""
                    task.video_outputs.append(VideoOutputInfo(
                        index=idx,
                        media_id=mid,
                        quality="pending",
                    ))
            
            # === Stage 1: Download 1K images ===
            self._dispatcher.update_progress(
                task.id, 85, f"📥 Downloading {total} image(s) (1K)"
            )
            local_paths = await self._download_outputs(
                task, fife_urls,
                quality_subfolder="1K",
                generate_thumbnails=True,
            )
            
            if not local_paths:
                log.warning(
                    f"[T2I-Pipeline] Task {task.id}: download returned 0 files"
                )
                self._dispatcher.fail_task(
                    task.id, "Image download failed (0 files saved)"
                )
                self._error_count += 1
                if self._on_task_failed:
                    self._on_task_failed(task, "Image download failed")
                return
            
            self._download_count += len(local_paths)
            log.info(
                f"[T2I-Pipeline] Task {task.id}: downloaded {len(local_paths)} "
                f"image(s) to 1K/"
            )
            
            # === Stage 2: Upscale to 4K (if mediaIds available) ===
            has_media_ids = any(mid for mid in media_ids)
            upscale_quality = getattr(task, 'download_quality', '1K') or '1K'
            should_upscale = (
                has_media_ids
                and upscale_quality.upper() in ('4K', '2K')
            )
            log.info(
                f"[T2I-Pipeline] Task {task.id}: "
                f"has_media_ids={has_media_ids}, "
                f"download_quality='{upscale_quality}', "
                f"should_upscale={should_upscale}, "
                f"media_ids={media_ids[:3]}"
            )
            
            if should_upscale:
                resolution_map = {
                    '4K': 'UPSAMPLE_IMAGE_RESOLUTION_4K',
                    '2K': 'UPSAMPLE_IMAGE_RESOLUTION_2K',
                }
                target_resolution = resolution_map.get(
                    upscale_quality.upper(),
                    'UPSAMPLE_IMAGE_RESOLUTION_4K'
                )
                
                self._dispatcher.update_progress(
                    task.id, 90,
                    f"⬆️ Upscaling to {upscale_quality} ({total} images)"
                )
                
                upscaled_paths = []
                max_upscale_retries = 2  # P1 fix: retry up to 2 attempts
                
                for idx, (mid, local_1k) in enumerate(
                    zip(media_ids, local_paths)
                ):
                    vo = task.video_outputs[idx] if idx < len(task.video_outputs) else None
                    
                    if not mid:
                        log.warning(
                            f"[T2I-Upscale] {idx+1}/{total}: no mediaId, "
                            f"keeping 1K"
                        )
                        upscaled_paths.append(local_1k)
                        if vo:
                            vo.upscale_status = "skipped"
                            vo.quality = "1K"
                        continue
                    
                    # ── Retry loop for this image ──
                    upscale_succeeded = False
                    for attempt in range(max_upscale_retries):
                        if self._stop_event.is_set():
                            break
                        
                        try:
                            log.info(
                                f"[T2I-Upscale] {idx+1}/{total}: "
                                f"upscaling mediaId={mid[:30]}... "
                                f"→ {upscale_quality}"
                                f"{f' (attempt {attempt+1})' if attempt > 0 else ''}"
                            )
                            
                            # Mark as submitting (purple border)
                            if vo:
                                vo.upscale_status = "submitting"
                            
                            # P0 FIX: Event-based cooldown wait (replaces poll-based race condition)
                            # Uses engine.wait_for_cooldown() which also keeps tab alive during wait
                            if self.is_account_on_cooldown(account.email):
                                log.info(
                                    f"[T2I-Upscale] {idx+1}/{total}: "
                                    f"account on cooldown, waiting..."
                                )
                                await self.wait_for_cooldown(account.email)
                                if self._stop_event.is_set():
                                    break
                            
                            # Rate-limit upscale requests
                            if account.email not in self._account_rate_locks:
                                self._account_rate_locks[account.email] = (
                                    asyncio.Lock()
                                )
                            
                            # Phase 6: Wait for supervisor clearance before submit
                            supervisor = self._supervisors.get(account.email)
                            if supervisor:
                                await supervisor.wait_for_clearance()
                                if supervisor.is_aborted:
                                    log.warning(f"[T2I-Upscale] {idx+1}/{total}: supervisor aborted")
                                    break
                            
                            async with self._account_rate_locks[account.email]:
                                # P0 FIX: Re-check cooldown inside lock
                                # (another task may have set cooldown while we waited for lock)
                                if self.is_account_on_cooldown(account.email):
                                    log.info(
                                        f"[T2I-Upscale] {idx+1}/{total}: "
                                        f"cooldown detected inside rate lock, waiting..."
                                    )
                                    await self.wait_for_cooldown(account.email)
                                
                                # ── RC2: Global cross-account submit gate ──
                                async with self._global_submit_lock:
                                    now = time.time()
                                    elapsed = now - self._global_last_submit_ts
                                    gap = self._GLOBAL_MIN_SUBMIT_GAP
                                    if elapsed < gap:
                                        wait_time = gap - elapsed
                                        log.info(
                                            f"[GlobalGate:{account.email}] Waiting {wait_time:.1f}s "
                                            f"(global inter-submit spacing, upscale)"
                                        )
                                        await asyncio.sleep(wait_time)
                                    self._global_last_submit_ts = time.time()
                                
                                # Anti-detect delay
                                if (
                                    getattr(self._settings, 'anti_detect_enabled', True)
                                    if self._settings else True
                                ):
                                    await self._burst_controller.wait(account.email)
                                
                                # Submit via extension
                                ext_bridge = getattr(
                                    account, 'extension_bridge', None
                                )
                                if not ext_bridge or not ext_bridge.is_connected(
                                    account.email
                                ):
                                    log.warning(
                                        f"[T2I-Upscale] Extension not connected "
                                        f"for {account.email}, keeping 1K"
                                    )
                                    upscaled_paths.append(local_1k)
                                    if vo:
                                        vo.upscale_status = "skipped"
                                        vo.quality = "1K"
                                    upscale_succeeded = True  # Skip retry
                                    break
                                
                                upscale_body = (
                                    self._api_client.build_upscale_image_body(
                                        media_id=mid,
                                        project_id=account.project_id or "",
                                        target_resolution=target_resolution,
                                        paygate_tier=(
                                            account.paygate_tier
                                            or "PAYGATE_TIER_TWO"
                                        ),
                                    )
                                )
                                
                                timeout = getattr(
                                    account, 'request_timeout', 120
                                )
                                ext_result = await asyncio.wait_for(
                                    ext_bridge.submit_prompt(
                                        email=account.email,
                                        endpoint="UPSCALE_IMAGE",
                                        body=upscale_body,
                                        needs_recaptcha=True,
                                        timeout=timeout,
                                    ),
                                    timeout=timeout + 5,
                                )
                            
                            if ext_result and ext_result.get('success'):
                                # P0 FIX: Record success to burst controller
                                self._burst_controller.record_success(account.email)
                                
                                upscale_data = ext_result.get('data', {})
                                encoded_image = upscale_data.get(
                                    'encodedImage', ''
                                )
                                if encoded_image:
                                    # Save upscaled image
                                    from config.settings import get_settings
                                    settings = get_settings()
                                    output_folder = (
                                        getattr(task, 'output_folder', '')
                                        or settings.output_folder
                                    )
                                    project_name = (
                                        getattr(task, 'project_name', '')
                                        or "Untitled"
                                    )
                                    upscale_dir = (
                                        Path(output_folder)
                                        / project_name
                                        / upscale_quality
                                    )
                                    upscale_dir.mkdir(
                                        parents=True, exist_ok=True
                                    )
                                    
                                    # Use same filename as 1K
                                    upscale_path = (
                                        upscale_dir
                                        / Path(local_1k).name
                                    )
                                    img_bytes = base64.b64decode(
                                        encoded_image
                                    )
                                    upscale_path.write_bytes(img_bytes)
                                    
                                    log.info(
                                        f"[T2I-Upscale] {idx+1}/{total}: "
                                        f"✅ {upscale_quality} saved "
                                        f"({len(img_bytes)//1024}KB): "
                                        f"{upscale_path.name}"
                                    )
                                    upscaled_paths.append(str(upscale_path))
                                    # ✅ Update video_outputs — upscale success
                                    if vo:
                                        vo.file_upscaled = str(upscale_path)
                                        vo.quality = upscale_quality
                                        vo.upscale_status = "success"
                                    upscale_succeeded = True
                                    break  # Success — exit retry loop
                                else:
                                    log.warning(
                                        f"[T2I-Upscale] {idx+1}/{total}: "
                                        f"no encodedImage in response, "
                                        f"keeping 1K"
                                    )
                                    upscaled_paths.append(local_1k)
                                    if vo:
                                        vo.upscale_status = "failed"
                                        vo.upscale_error = "no encodedImage in response"
                                        vo.quality = "1K"
                                    upscale_succeeded = True  # Don't retry (server issue, not transient)
                                    break
                            else:
                                # ── Submit failed — check error type ──
                                error = (
                                    ext_result.get('error', 'unknown')
                                    if ext_result else 'no response'
                                )
                                error_lower = error.lower()
                                status_code = (
                                    ext_result.get('status', 0)
                                    if ext_result else 0
                                )
                                is_403 = status_code == 403 or "403" in error_lower
                                is_recaptcha = "recaptcha" in error_lower
                                
                                log.warning(
                                    f"[T2I-Upscale] {idx+1}/{total}: "
                                    f"failed (attempt {attempt+1}/{max_upscale_retries}): "
                                    f"{error}"
                                )
                                
                                # P0 FIX: Report 403/reCAPTCHA to supervisor
                                if is_403 or is_recaptcha:
                                    # Phase 6: Delegate to supervisor recovery
                                    supervisor = self._supervisors.get(account.email)
                                    if supervisor:
                                        await supervisor.report_error(
                                            "403",
                                            f"T2I upscale 403 (img {idx+1}/{total}): {error}",
                                        )
                                        # Supervisor blocks → recovers → reopens gate
                                        # wait_for_clearance at top of retry will block
                                    else:
                                        # Fallback: direct cooldown (no supervisor)
                                        self.record_circuit_403(account.email)
                                        self._burst_controller.record_error(
                                            account.email, status_code or 403
                                        )
                                        if is_403:
                                            self.set_account_cooldown(
                                                account.email,
                                                f"T2I upscale 403 (img {idx+1}/{total})"
                                            )
                                    
                                    # P1 FIX: Recovery before retry
                                    if attempt < max_upscale_retries - 1:
                                        log.info(
                                            f"[T2I-Upscale] {idx+1}/{total}: "
                                            f"waiting recovery before retry..."
                                        )
                                        if not supervisor:
                                            await self.wait_for_cooldown(account.email)
                                        continue  # Retry
                                
                                # Non-403 error or last attempt
                                if attempt >= max_upscale_retries - 1:
                                    upscaled_paths.append(local_1k)
                                    if vo:
                                        vo.upscale_status = "failed"
                                        vo.upscale_error = str(error)
                                        vo.quality = "1K"
                                    upscale_succeeded = True  # Mark as handled
                        
                        except asyncio.TimeoutError:
                            log.warning(
                                f"[T2I-Upscale] {idx+1}/{total}: timeout "
                                f"(attempt {attempt+1}/{max_upscale_retries})"
                            )
                            if attempt >= max_upscale_retries - 1:
                                upscaled_paths.append(local_1k)
                                if vo:
                                    vo.upscale_status = "failed"
                                    vo.upscale_error = "timeout"
                                    vo.quality = "1K"
                                upscale_succeeded = True
                        except Exception as e:
                            log.warning(
                                f"[T2I-Upscale] {idx+1}/{total}: "
                                f"error ({e})"
                                f"(attempt {attempt+1}/{max_upscale_retries})"
                            )
                            if attempt >= max_upscale_retries - 1:
                                upscaled_paths.append(local_1k)
                                if vo:
                                    vo.upscale_status = "failed"
                                    vo.upscale_error = str(e)
                                    vo.quality = "1K"
                                upscale_succeeded = True
                    
                    # Safety: if retry loop exhausted without appending
                    if not upscale_succeeded:
                        upscaled_paths.append(local_1k)
                        if vo:
                            vo.upscale_status = "failed"
                            vo.upscale_error = "retry exhausted"
                            vo.quality = "1K"
                
                # Use upscaled paths as final output
                task.output_uris = upscaled_paths
            else:
                # No upscale needed — 1K is final
                task.output_uris = local_paths
                # Update video_outputs quality to "1K"
                for idx, vo in enumerate(task.video_outputs):
                    if vo.quality in ("pending", "720p"):
                        vo.quality = "1K"
                    vo.upscale_status = "skipped"
                if has_media_ids:
                    log.info(
                        f"[T2I-Pipeline] Task {task.id}: "
                        f"download_quality={upscale_quality}, "
                        f"no upscale needed"
                    )
            
            # === Stage 3: Complete task ===
            # NOTE: dispatcher.complete_task() fires _on_task_completed internally
            #       — do NOT call it again here or toast will fire twice
            self._dispatcher.update_progress(task.id, 100, "✅ Complete")
            self._dispatcher.complete_task(
                task.id,
                output_uris=task.output_uris,
            )
            
            log.info(
                f"[T2I-Pipeline] Task {task.id}: ✅ DONE "
                f"({len(task.output_uris)} files, "
                f"quality={upscale_quality})"
            )
            
            # P2 FIX: Log accurate quality breakdown
            if should_upscale:
                actual_4k = sum(1 for vo in task.video_outputs if vo.upscale_status == "success")
                actual_1k = sum(1 for vo in task.video_outputs if vo.upscale_status in ("failed", "skipped"))
                if actual_1k > 0:
                    log.warning(
                        f"[T2I-Pipeline] Task {task.id}: ⚠️ ACTUAL quality: "
                        f"{actual_4k}/{total} upscaled to {upscale_quality}, "
                        f"{actual_1k}/{total} kept at 1K"
                    )
        
        except asyncio.CancelledError:
            log.warning(
                f"[T2I-Pipeline:{account.email}] Task {task.id} cancelled"
            )
        except Exception as e:
            log.error(
                f"[T2I-Pipeline:{account.email}] Task {task.id} error: {e}",
                exc_info=True,
            )
            if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                self._dispatcher.fail_task(
                    task.id, f"T2I pipeline error: {e}"
                )
                self._error_count += 1
                if self._on_task_failed:
                    self._on_task_failed(task, str(e))
        finally:
            if worker_count > 0:
                account.release_workers(worker_count)
    
    async def _poll_operation(self, task: Task, account: AccountManager):
        """Poll for async operation completion.
        
        Progress stages (status-based, not time-based):
          5%  - Token validation (worker)
         10%  - reCAPTCHA refresh (worker)
         15%  - Submitting to API (worker)
         20%  - API accepted request (worker)
         25%  - Polling started (PENDING)
         30%  - Server queued (PENDING, 2nd+ poll)
         40%  - Server processing (ACTIVE, 1st seen)
         45-80% - Server processing (ACTIVE, ramping with polls)
         85%  - All operations SUCCESSFUL
         90%  - Downloading outputs
         95%  - Download complete / upscaling
        100%  - Fully done
        """
        from config.constants import AppConstants
        
        poll_phase1_interval = AppConstants.POLL_PHASE1_INTERVAL
        poll_phase1_duration = AppConstants.POLL_PHASE1_DURATION
        poll_phase2_interval = AppConstants.POLL_PHASE2_INTERVAL
        max_poll_time = AppConstants.MAX_POLL_TIME
        elapsed = 0
        
        # Track status transitions for progress
        active_poll_count = 0   # How many polls returned ACTIVE
        pending_poll_count = 0  # How many polls returned PENDING
        last_status = "MEDIA_GENERATION_STATUS_PENDING"
        
        # ★ STAGE SKIP: resume from checkpoint without re-polling
        if task.stage in (TaskStage.GENERATED, TaskStage.DOWNLOADED_720,
                          TaskStage.UPSCALING, TaskStage.UPSCALED):
            log.info(f"[Poll] Task {task.id}: skipping poll, resuming from {task.stage.value}")
            # Reconstruct output_uris + media_ids from saved video_outputs
            output_uris = []
            media_ids = []
            for vo in task.video_outputs:
                # For GENERATED: use operation_name to reconstruct fifeUrl isn't possible,
                # but we have the data stored already. For DOWNLOADED_720+, we have file paths.
                if vo.media_id:
                    media_ids.append(vo.media_id)
            
            if task.stage == TaskStage.GENERATED:
                # Need to download 720p — we have video_outputs but no files yet
                # Cannot reconstruct fifeUrls from saved data, so re-poll once to get URLs
                log.info(f"[Poll] Task {task.id}: GENERATED stage needs re-poll for download URLs")
                # Fall through to normal polling (but ops should complete quickly)
            elif task.stage in (TaskStage.DOWNLOADED_720, TaskStage.UPSCALING, TaskStage.UPSCALED):
                # Already have 720p files. Just need upscale or completion.
                if task.stage == TaskStage.UPSCALING and task.download_quality != "720p" and media_ids:
                    # Resume UPSCALING → re-enqueue to background UpscaleQueue
                    # (don't use inline _auto_upscale — that blocks worker slots)
                    from core.upscale_queue import UpscaleJob
                    output_uris_for_upscale = [vo.file_720p for vo in task.video_outputs if vo.file_720p]
                    self._upscale_queue.enqueue(UpscaleJob(
                        task_id=task.id,
                        account_email=account.email,
                        original_account=account.email,  # DD6
                        media_ids=list(media_ids),
                        output_uris=list(output_uris_for_upscale),
                        target_quality=task.download_quality,
                        aspect_ratio=task.aspect_ratio,
                    ))
                    task.upscale_media_ids = list(media_ids)
                    self._dispatcher.update_progress(
                        task.id, 88, f"⬆️ Resuming upscale {task.download_quality} (queued)"
                    )
                    log.info(
                        f"[Engine] Task {task.id}: UPSCALING resume → "
                        f"re-enqueued to UpscaleQueue, worker releasing slot"
                    )
                    # Release worker slot — upscale continues in background
                    self._dispatcher.decrement_running()
                    return
                elif task.stage == TaskStage.DOWNLOADED_720 and task.download_quality != "720p" and media_ids:
                    # Resume upscale from DOWNLOADED_720 — inline path
                    self._dispatcher.update_progress(task.id, 88, "⬆️ Resuming upscale")
                    task.upscale_media_ids = list(media_ids)
                    # Need output_uris for upscale — reconstruct from video_outputs
                    output_uris_for_upscale = [vo.file_720p for vo in task.video_outputs if vo.file_720p]
                    upscale_results = await self._auto_upscale(
                        task, account, output_uris_for_upscale, media_ids
                    )
                    if upscale_results:
                        uris_to_download = [u for u in upscale_results if u]
                        if uris_to_download:
                            self._dispatcher.update_progress(
                                task.id, 92, f"⬇️ Downloading {task.download_quality}"
                            )
                            dl_paths = await self._download_outputs(
                                task, uris_to_download,
                                quality_subfolder=task.download_quality,
                                generate_thumbnails=False,
                            )
                            dl_idx = 0
                            for i, uri in enumerate(upscale_results):
                                if uri and dl_idx < len(dl_paths):
                                    if i < len(task.video_outputs):
                                        task.video_outputs[i].file_upscaled = dl_paths[dl_idx]
                                        task.video_outputs[i].quality = task.download_quality
                                    dl_idx += 1
                
                # Update final paths
                final_paths = []
                for vo in task.video_outputs:
                    final_paths.append(vo.file_upscaled or vo.file_720p)
                if final_paths:
                    task.output_uris = final_paths
                
                self._sync_overall_upscale_status(task)
                
                # Post-processing + complete
                self._dispatcher.update_progress(task.id, 95, "🎬 Post-processing")
                continuation_frame_uri = None
                continuation_frame_local = None
                if ((getattr(self._settings, 'continuation_enabled', True) if self._settings else True)
                        and self._dispatcher.has_children(task.id)
                        and task.output_uris):
                    frame_result = await self._extract_continuation_frame(
                        task, account, task.output_uris[0]
                    )
                    # Fix 3: Cooldown between parent's API burst and child's I2V submit
                    # Parent just finished polling + downloading + possibly upscaling —
                    # adding delay prevents rate limit cascade on the same account.
                    if frame_result:
                        continuation_frame_uri, continuation_frame_local = frame_result
                        cooldown = random.uniform(3.0, 5.0)
                        log.info(f"Continuation cooldown: {cooldown:.1f}s before releasing child")
                        await asyncio.sleep(cooldown)
                
                task.stage = TaskStage.COMPLETED
                self._dispatcher.update_progress(task.id, 100, "✅ Done")
                self._dispatcher.complete_task(
                    task.id,
                    output_uris=task.output_uris,
                    continuation_frame_uri=continuation_frame_uri,
                    continuation_frame_local_path=continuation_frame_local,
                )
                self._download_count += len(task.output_uris or [])
                emit_event(EventType.TASK_COMPLETED, {
                    "task_id": task.id,
                    "outputs": len(task.output_uris or []),
                    "account": task.assigned_account,
                    "resumed": True,
                }, source="engine")
                # NOTE: dispatcher.complete_task() already fires _on_task_completed
                #       — do NOT call it again here or toast will fire twice
                return
        
        # Initial: polling started
        self._dispatcher.update_progress(task.id, 25, "⏳ Waiting in queue")
        
        # Multi-op tracking
        pending_ops = {}
        completed_results = {}  # op_name -> {fifeUrl, mediaId}
        for idx, op_name in enumerate(task.operation_names):
            sid = task.scene_ids[idx] if idx < len(task.scene_ids) else ""
            pending_ops[op_name] = {"sceneId": sid, "status": "MEDIA_GENERATION_STATUS_PENDING"}
        
        while elapsed < max_poll_time and not self._stop_event.is_set():
            # 2-phase polling: slow at start (video never ready <30s), fast later
            base_interval = poll_phase1_interval if elapsed < poll_phase1_duration else poll_phase2_interval
            # Risk 2 fix: Jitter prevents all workers from polling simultaneously
            jitter = random.uniform(0, base_interval * 0.3)
            actual_interval = base_interval + jitter
            await asyncio.sleep(actual_interval)
            elapsed += actual_interval
            
            # Cancellation check: user may have deleted task during poll
            if task.state == TaskState.CANCELLED:
                log.info(f"[Engine] Task {task.id}: cancelled during poll, aborting")
                return
            
            try:
                # Build poll list from ALL pending operations
                ops_to_poll = []
                for op_name, info in pending_ops.items():
                    ops_to_poll.append({
                        "operation": {"name": op_name},
                        "sceneId": info["sceneId"],
                        "status": info["status"],
                    })
                # HAR verified: website only polls PENDING/ACTIVE ops,
                # completed ops are removed from subsequent poll batches
                
                # ★ Ensure valid access token before poll (Bug fix: 401 CREDENTIALS_MISSING)
                # Submit goes through Extension Bridge (browser handles auth internally),
                # but polling uses direct HTTP and NEEDS an access_token in the session.
                # ensure_valid_token() will refresh via extension if expired.
                token = await account.ensure_valid_token()
                if not token:
                    log.warning(
                        f"[Poll] Task {task.id}: no valid access token — "
                        f"refresh failed, retrying next cycle"
                    )
                    continue
                
                # Risk 7 fix: Limit concurrent API calls per account
                sem = self._get_api_semaphore(account.email)
                async with sem:
                    response = await self._api_client.check_status(
                        access_token=token,
                        recaptcha_token="",
                        operations=ops_to_poll,
                        account_headers=account.get_api_headers(),
                    )
                
                if not response.success:
                    # Auto-refresh token on 401 and retry next cycle
                    if response.response_code == 401:
                        log.warning(
                            f"[Poll] Task {task.id}: HTTP 401 — refreshing access token"
                        )
                        await account.refresh_access_token()
                    else:
                        log.warning(
                            f"[Poll] Task {task.id}: check_status failed — {response.error}"
                        )
                    continue
                
                response_ops = response.data.get("operations", [])
                if not response_ops:
                    log.debug(
                        f"[Poll] Task {task.id}: empty operations in response "
                        f"(keys={list(response.data.keys()) if response.data else 'None'})"
                    )
                    continue
                
                # Process each operation in response
                any_failed = False
                for op in response_ops:
                    op_name = op.get("operation", {}).get("name", "")
                    op_status = op.get("status", "")
                    
                    if op_status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                        if op_name in pending_ops:
                            # Collect result, remove from pending
                            details = self._extract_output_details({"operations": [op]})
                            if details:
                                completed_results[op_name] = details[0]
                            pending_ops.pop(op_name, None)
                            log.info(f"[Poll] Op {op_name[:12]}... DONE ({len(completed_results)}/{len(task.operation_names)})")
                    elif op_status == "MEDIA_GENERATION_STATUS_FAILED":
                        any_failed = True
                        pending_ops.pop(op_name, None)
                        error = op.get("error", {}).get("message", "Server generation failed")
                        log.warning(f"[Poll] Op {op_name[:12]}... FAILED: {error}")
                    elif op_name in pending_ops:
                        # Update status for next poll
                        pending_ops[op_name]["status"] = op_status
                
                # Get current server status for progress
                server_status = response_ops[0].get("status", "") if response_ops else ""
                
                if not pending_ops:
                    # ALL operations resolved
                    if not completed_results:
                        # All failed
                        self._dispatcher.fail_task(task.id, "All video operations failed")
                        emit_event(EventType.TASK_FAILED, {
                            "task_id": task.id, "error": "All video operations failed",
                            "reason": "all_ops_failed",
                        }, source="engine")
                        return
                    
                    # ★ Solution 1: Log partial failures clearly
                    total_ops = len(task.operation_names)
                    success_count = len(completed_results)
                    failed_count = total_ops - success_count
                    
                    if any_failed and success_count > 0:
                        failed_ops = [
                            op for op in task.operation_names
                            if op not in completed_results
                        ]
                        variant_letters = "abcdefghijklmnopqrstuvwxyz"
                        prompt_num = getattr(task, 'prompt_index', 0) + 1
                        failed_labels = []
                        for op in failed_ops:
                            idx = task.operation_names.index(op)
                            label = f"{str(prompt_num).zfill(3)}{variant_letters[idx] if idx < len(variant_letters) else '?'}"
                            failed_labels.append(label)
                        
                        log.warning(
                            f"⚠️ Task {task.id}: PARTIAL FAILURE — "
                            f"{success_count}/{total_ops} variants succeeded, "
                            f"{failed_count} failed. "
                            f"Missing: {', '.join(failed_labels)}. "
                            f"Prompt: {task.prompt[:60]}..."
                        )
                        
                        # ★ Solution 2: Auto-retry failed variants
                        self._auto_retry_partial_failure(
                            task, failed_count, failed_labels
                        )
                    
                    # ★ CRITICAL: Sort results by SUBMIT ORDER
                    if any_failed:
                        self._dispatcher.update_progress(
                            task.id, 85,
                            f"⚠️ {success_count}/{total_ops} done, {failed_count} retrying"
                        )
                    else:
                        self._dispatcher.update_progress(task.id, 85, "✅ Generation complete")
                    ordered_uris = []
                    ordered_media_ids = []
                    for op_name in task.operation_names:
                        if op_name in completed_results:
                            detail = completed_results[op_name]
                            ordered_uris.append(detail["fifeUrl"])
                            ordered_media_ids.append(detail["mediaId"])
                    
                    output_uris = ordered_uris
                    media_ids = ordered_media_ids
                    
                    # ★ Phase 6: Create VideoOutputInfo per video
                    # H1 fix: Always create entries for ALL ops (including failed)
                    # to preserve index alignment: video_outputs[i] ↔ operation_names[i]
                    task.video_outputs = []
                    for i, op_name in enumerate(task.operation_names):
                        if op_name in completed_results:
                            detail = completed_results[op_name]
                            vo = VideoOutputInfo(
                                index=i,
                                operation_name=op_name,
                                scene_id=task.scene_ids[i] if i < len(task.scene_ids) else "",
                                media_id=detail["mediaId"],
                                quality="pending",
                            )
                        else:
                            # H1: Failed op gets a placeholder entry — preserves index
                            vo = VideoOutputInfo(
                                index=i,
                                operation_name=op_name,
                                scene_id=task.scene_ids[i] if i < len(task.scene_ids) else "",
                                media_id="",  # No mediaId for failed ops
                                quality="failed",
                            )
                        task.video_outputs.append(vo)
                    
                    task.stage = TaskStage.GENERATED  # ★ Checkpoint: poll complete
                    
                    # Always save media_ids early — needed for re-upscale
                    # even if upscale block is skipped (720p or token failure)
                    task.upscale_media_ids = list(media_ids)
                    
                    emit_event(EventType.TASK_PROGRESS, {
                        "task_id": task.id, "stage": "generated",
                        "progress": 85, "outputs": len(completed_results),
                    }, source="engine")
                    
                    # === Stage: Download 720p originals (86%) ===
                    self._dispatcher.update_progress(task.id, 86, "⬇️ Downloading 720p")
                    local_720p = await self._download_outputs(
                        task, output_uris, quality_subfolder="720p",
                        generate_thumbnails=True,
                    )
                    
                    task.stage = TaskStage.DOWNLOADED_720  # ★ Checkpoint: 720p saved
                    
                    # ★ Bug 4C: Handle failed downloads (toggle + max retry logic)
                    dl_success = sum(1 for p in local_720p if p)
                    dl_total = len(local_720p)
                    if dl_success < dl_total:
                        dl_failed = dl_total - dl_success
                        failed_indices = [i for i, p in enumerate(local_720p) if not p]
                        variant_letters = "abcdefghijklmnopqrstuvwxyz"
                        prompt_num = getattr(task, 'prompt_index', 0) + 1
                        failed_labels = [
                            f"{str(prompt_num).zfill(3)}{variant_letters[i] if i < len(variant_letters) else '?'}"
                            for i in failed_indices
                        ]
                        
                        # Check auto_retry_download toggle from settings
                        from config.settings import get_settings as _gs
                        _s = _gs()
                        auto_retry_enabled = getattr(_s, 'auto_retry_download', True)
                        
                        if not auto_retry_enabled:
                            # Toggle OFF → immediately fail task (cascade children)
                            error_msg = (
                                f"Download failed ({dl_failed}/{dl_total} missing), "
                                f"auto re-generation disabled"
                            )
                            log.warning(
                                f"⚠️ [{task.id}] {error_msg} — "
                                f"missing: {', '.join(failed_labels)}"
                            )
                            self._dispatcher.update_progress(
                                task.id, 87,
                                f"❌ {dl_success}/{dl_total} downloaded — FAILED (auto-retry OFF)"
                            )
                            self._dispatcher.fail_task(
                                task.id, error_msg
                            )
                        else:
                            # Toggle ON → attempt re-generation (with max limit)
                            self._dispatcher.update_progress(
                                task.id, 87,
                                f"⚠️ {dl_success}/{dl_total} downloaded, {dl_failed} queued for re-generation"
                            )
                            self._auto_retry_download_failure(
                                task, dl_failed, failed_labels
                            )
                    else:
                        # Trigger UI refresh so thumbnails generated from 720p show immediately
                        self._dispatcher.update_progress(
                            task.id, 87, f"📥 720p downloaded ({dl_success} videos)"
                        )
                    emit_event(EventType.TASK_PROGRESS, {
                        "task_id": task.id, "stage": "downloaded_720",
                        "progress": 87,
                    }, source="engine")
                    
                    # === Stage: Auto-upscale if needed (88-92%) ===
                    upscale_paths = [None] * len(media_ids)  # None placeholders
                    skip_upscale = False  # Bug #8 fix: use flag instead of clearing media_ids
                    if task.download_quality != "720p" and media_ids:
                        # Gap #2: Centralized token validation before upscale enqueue
                        valid_token = await account.ensure_valid_token()
                        if not valid_token:
                            log.error(f"[Upscale] Token refresh failed for {account.email} — keeping 720p")
                            # Mark all videos as upscale-skipped
                            for vo in task.video_outputs:
                                vo.upscale_status = "failed"
                                vo.upscale_error = "Access token expired, refresh failed"
                            task.upscale_error = "Access token expired"
                            self._dispatcher.update_progress(task.id, 90, "⚠️ Upscale skipped (auth expired)")
                            # Skip upscale, continue to completion with 720p
                            upscale_paths = [None] * len(media_ids)
                            skip_upscale = True  # Bug #8: preserve media_ids for re-upscale
                        
                        # Phase 3A: Upscale — mode determines inline vs background
                        if not skip_upscale:  # Bug #8: check flag instead of testing media_ids
                            if self._workload_priority == 'upscale_priority':
                                # Issue #5: INLINE upscale — worker holds slot
                                # Video is upscaled immediately, no queue delay
                                log.info(
                                    f"[Engine] Task {task.id}: upscale_priority mode → "
                                    f"inline upscale ({task.download_quality})"
                                )
                                task.stage = TaskStage.UPSCALING
                                self._dispatcher.update_progress(
                                    task.id, 88, f"⬆️ Upscaling {task.download_quality} (inline)"
                                )
                                upscale_results = await self._auto_upscale(
                                    task, account, output_uris, media_ids
                                )
                                # Populate upscale_paths for merge at L1642+
                                for i, uri in enumerate(upscale_results):
                                    if uri and i < len(upscale_paths):
                                        upscale_paths[i] = uri
                                
                                # Handle continuation frame (same as background path)
                                if (
                                    (getattr(self._settings, 'continuation_enabled', True) if self._settings else True)
                                    and self._dispatcher.has_children(task.id)
                                    and output_uris
                                ):
                                    frame_result = await self._extract_continuation_frame(
                                        task, account, output_uris[0]
                                    )
                                    if frame_result:
                                        await self._wait_for_recaptcha_ready(account, max_wait=30.0)
                                        self._dispatcher.activate_children_early(
                                            task.id,
                                            frame_result[0],
                                            frame_result[1],
                                        )
                                # Fall through to merge at L1642+ (don't return)
                            else:
                                # BACKGROUND upscale (720p_priority mode)
                                from core.upscale_queue import UpscaleJob
                                self._upscale_queue.enqueue(UpscaleJob(
                                    task_id=task.id,
                                    account_email=account.email,
                                    original_account=account.email,  # DD6
                                    media_ids=list(media_ids),
                                    output_uris=list(output_uris),
                                    target_quality=task.download_quality,
                                    aspect_ratio=task.aspect_ratio,
                                ))
                                task.upscale_media_ids = list(media_ids)
                                task.stage = TaskStage.UPSCALING  # ★ Stay in upscaling
                                self._dispatcher.update_progress(
                                    task.id, 88, f"⬆️ Upscaling {task.download_quality} (queued)"
                                )
                                
                                # Handle continuation frame before worker exits
                                # EARLY ACTIVATION: Children start immediately after 720p,
                                # not after upscale completes (~3-5min savings per chain link)
                                if (
                                    (getattr(self._settings, 'continuation_enabled', True) if self._settings else True)
                                    and self._dispatcher.has_children(task.id)
                                    and output_uris
                                ):
                                    frame_result = await self._extract_continuation_frame(
                                        task, account, output_uris[0]
                                    )
                                    if frame_result:
                                        # Note: Don't set continuation_frame on parent task —
                                        # only children should have it (for Queue UI display).
                                        # Parent is T2V and should NOT show "Frame" thumbnail.
                                        
                                        # Layer 2: Smart cooldown — wait for grecaptcha readiness
                                        # instead of fixed sleep(3-5s).
                                        await self._wait_for_recaptcha_ready(account, max_wait=30.0)
                                        
                                        # ★ Activate children NOW — don't wait for upscale
                                        # _resolve_dependencies pops _parent_to_children,
                                        # so UpscaleQueue's complete_task() won't double-activate
                                        self._dispatcher.activate_children_early(
                                            task.id,
                                            frame_result[0],   # continuation_frame_uri
                                            frame_result[1],   # continuation_frame_local_path
                                        )
                                
                                # Worker exits — UpscaleQueue will call complete_task()
                                # ★ CRITICAL: Decrement running_count so should_upscale_wait()
                                # returns False when all prompts are done. Without this,
                                # running_count stays >0 forever → upscale deadlock.
                                self._dispatcher.decrement_running()
                                log.info(
                                    f"[Engine] Task {task.id}: worker releasing slot → "
                                    f"upscale continues in background"
                                )
                                return
                    
                    # Per-video quality merge: prefer upscale, fallback 720p
                    # NOTE: local_720p has same length as output_uris, with "" for failed downloads
                    final_paths = []
                    for i in range(len(local_720p)):
                        if i < len(upscale_paths) and upscale_paths[i]:
                            final_paths.append(upscale_paths[i])
                            # Update per-video info
                            if i < len(task.video_outputs):
                                task.video_outputs[i].file_upscaled = upscale_paths[i]
                                task.video_outputs[i].quality = task.download_quality
                        elif local_720p[i]:
                            final_paths.append(local_720p[i])
                        else:
                            # Download failed for this video — mark video_output as failed
                            if i < len(task.video_outputs):
                                task.video_outputs[i].quality = "failed"
                                task.video_outputs[i].upscale_status = "skipped"
                            log.warning(f"⚠️ Video {i+1}: no local file (download failed)")
                    
                    if final_paths:
                        task.output_uris = final_paths
                    
                    # Log partial download warning
                    expected_count = len(local_720p)
                    actual_count = len(final_paths)
                    if actual_count < expected_count:
                        log.warning(
                            f"⚠️ Task {task.id}: only {actual_count}/{expected_count} "
                            f"videos have local files. Missing videos cannot be retried "
                            f"automatically — use Force Retry to re-generate."
                        )
                    
                    # Sync overall upscale status from per-video
                    self._sync_overall_upscale_status(task)
                    
                    # === Stage: Post-processing (95%) ===
                    self._dispatcher.update_progress(task.id, 95, "🎬 Post-processing")
                    continuation_frame_uri = None
                    continuation_frame_local = None
                    if (
                        (getattr(self._settings, 'continuation_enabled', True) if self._settings else True)
                        and self._dispatcher.has_children(task.id)
                        and output_uris
                    ):
                        frame_result = await self._extract_continuation_frame(
                            task, account, output_uris[0]
                        )
                        # Layer 2: Smart cooldown — readiness-based instead of fixed delay
                        if frame_result:
                            continuation_frame_uri, continuation_frame_local = frame_result
                            await self._wait_for_recaptcha_ready(account, max_wait=30.0)
                    
                    # === Stage: Complete (100%) — only for non-upscale tasks ===
                    task.stage = TaskStage.COMPLETED  # ★ Checkpoint: all done
                    self._dispatcher.update_progress(task.id, 100, "✅ Done")
                    # Bug #4 fix: pass LOCAL file paths, not FIFE URLs.
                    # output_uris = FIFE download URLs (remote)
                    # task.output_uris = local file paths (set at line ~1372)
                    self._dispatcher.complete_task(
                        task.id,
                        output_uris=task.output_uris or output_uris,
                        continuation_frame_uri=continuation_frame_uri,
                        continuation_frame_local_path=continuation_frame_local,
                    )
                    emit_event(EventType.TASK_COMPLETED, {
                        "task_id": task.id,
                        "outputs": len(output_uris),
                        "account": task.assigned_account,
                    }, source="engine")
                    # NOTE: dispatcher.complete_task() already fires _on_task_completed
                    #       — do NOT call it again here or toast will fire twice
                    # Save manifest alongside output videos
                    self._save_manifest(task)
                    return
                
                else:
                    # === Status-based progress mapping ===
                    if server_status == "MEDIA_GENERATION_STATUS_PENDING":
                        pending_poll_count += 1
                        progress = min(35, 25 + pending_poll_count * 2)
                        status_label = "⏳ Queued on server"
                    elif server_status == "MEDIA_GENERATION_STATUS_ACTIVE":
                        active_poll_count += 1
                        progress = min(80, 40 + int(active_poll_count * 5))
                        status_label = "🔥 Processing"
                    else:
                        progress = min(80, 25 + int(elapsed / max_poll_time * 55))
                        status_label = "⏳ Working"
                    
                    self._dispatcher.update_progress(task.id, progress, status_label)
                    
                    # Log status transition
                    if server_status != last_status:
                        log.info(f"Task {task.id}: {last_status} → {server_status} ({progress}%)")
                        last_status = server_status
                    
            except Exception as poll_err:
                log.warning(
                    f"[Poll] Task {task.id}: poll error — "
                    f"{type(poll_err).__name__}: {poll_err}"
                )
                continue
        
        # Timeout
        self._dispatcher.fail_task(task.id, f"Polling timeout ({max_poll_time}s)")
        emit_event(EventType.TASK_FAILED, {
            "task_id": task.id, "error": f"Polling timeout ({max_poll_time}s)",
            "reason": "poll_timeout",
        }, source="engine")
    
    def _extract_output_details(self, data: dict) -> list:
        """Extract output details from poll response.
        
        Returns list of {fifeUrl, mediaId} dicts.
        - fifeUrl: download URL for the video/image
        - mediaId: metadata.name (protobuf Base64), needed for upscale API
        
        HAR-verified paths:
          operations[].operation.metadata.name           → mediaId for upscale
          operations[].operation.metadata.video.fifeUrl  → download URL
        """
        results = []
        for op in data.get("operations", []):
            metadata = op.get("operation", {}).get("metadata", {})
            media_id = metadata.get("name", "")  # protobuf Base64
            
            # Video result
            video = metadata.get("video", {})
            if video:
                uri = video.get("fifeUrl") or video.get("servingBaseUri", "")
                if uri:
                    results.append({"fifeUrl": uri, "mediaId": media_id})
                    continue
            # Image result
            image = metadata.get("image", {}).get("generatedImage", {})
            if image:
                uri = image.get("fifeUrl", "")
                if uri:
                    results.append({"fifeUrl": uri, "mediaId": media_id})
        return results
    
    def _extract_output_uris(self, data: dict) -> list:
        """Backward-compatible wrapper: extract fifeUrls only."""
        return [d["fifeUrl"] for d in self._extract_output_details(data)]
    
    async def _extract_continuation_frame(
        self, task: Task, account: AccountManager, video_uri: str
    ) -> Optional[tuple]:
        """FFmpeg pipeline: download → extract → base64 → upload → mediaId.
        
        Returns (mediaId, frame_local_path) tuple or None on error.
        Frame file is preserved for UI thumbnail display.
        """
        try:
            if not self._frame_extractor.is_available:
                log.warning("FFmpeg not available, skipping continuation frame extraction")
                return None
            
            # Update status: extracting
            task.image_upload_status = "extracting"
            self._dispatcher.update_progress(task.id, task.progress, "📸 Extracting frame...")
            
            # 1. Download video to temp file
            import aiohttp
            import tempfile
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_uri) as resp:
                    if resp.status != 200:
                        log.error(f"Failed to download video: HTTP {resp.status}")
                        task.image_upload_status = "error"
                        return None
                    video_bytes = await resp.read()
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(
                suffix=".mp4", delete=False, dir=str(self._frame_extractor.get_temp_dir())
            ) as tmp:
                tmp.write(video_bytes)
                video_path = tmp.name
            
            # 2. Extract frame via FFmpeg (CPU-bound, run in process pool)
            # C3: VEO only uses start frame input → always extract from END
            loop = asyncio.get_running_loop()
            frame_path = await loop.run_in_executor(
                self._process_pool,
                self._frame_extractor.extract_frame,
                video_path,
                None,  # auto-generate output path
                task.extract_point_ms,  # C4: use Task field directly
                True   # C3: always from_end=True (VEO start frame)
            )
            
            # Cleanup temp video
            Path(video_path).unlink(missing_ok=True)
            
            if not frame_path:
                log.error("Frame extraction failed")
                task.image_upload_status = "error"
                return None
            
            # ★ Auto-enhance: upscale continuation frame if feature is enabled
            try:
                ctrl = self._app_controller
                if ctrl:
                    settings = getattr(ctrl, 'settings', None)
                    enhancer = getattr(ctrl, '_image_enhancer', None)
                    if (settings and enhancer and enhancer.available and
                        getattr(settings, 'enhance_auto_continuation', False)):
                        log.info(f"[AutoEnhance] Upscaling continuation frame: {frame_path}")
                        self._dispatcher.update_progress(
                            task.id, task.progress, "✨ Enhancing frame..."
                        )
                        from core.image_enhancer import EnhanceMode
                        result = enhancer.enhance_sync(
                            frame_path,
                            mode=EnhanceMode.UPSCALE_4X,
                            timeout=60,
                        )
                        if result.success:
                            frame_path = result.output_path
                            log.info(f"[AutoEnhance] Frame enhanced: {frame_path}")
                        else:
                            log.warning(f"[AutoEnhance] Enhancement failed: {result.error}")
            except Exception as enhance_err:
                log.warning(f"[AutoEnhance] Skipped: {enhance_err}")
            
            # ★ Early display: set frame path on children BEFORE upload
            # so Queue tab can show thumbnail immediately
            self._dispatcher.set_children_frame_preview(task.id, frame_path)
            
            # 3. Base64 encode via MediaHandler for quality + format
            from core.media_handler import MediaHandler
            frame_result = MediaHandler.image_to_base64(frame_path)
            if not frame_result:
                log.error("Frame base64 encoding failed")
                task.image_upload_status = "error"
                Path(frame_path).unlink(missing_ok=True)
                return None
            frame_b64, frame_mime = frame_result
            
            # Keep frame file for UI thumbnail display (not deleted)
            
            # 4. Upload image to VEO API
            # Fix 2: Upload does NOT need reCAPTCHA (HAR verified).
            task.image_upload_status = "uploading"
            self._dispatcher.update_progress(task.id, task.progress, "📤 Uploading frame...")
            upload_resp = await self._api_client.upload_image(
                access_token=account.get_access_token(),
                recaptcha_token="",  # HAR: upload does NOT send recaptcha
                image_base64=frame_b64,
                mime_type=frame_mime,
                account_headers=account.get_api_headers(),  # Issue 10: per-account headers
            )
            
            if upload_resp.success:
                # HAR verified: response is {"mediaGenerationId": {"mediaGenerationId": "..."}}
                mgid = upload_resp.data.get("mediaGenerationId", {})
                if isinstance(mgid, dict):
                    media_id = mgid.get("mediaGenerationId")
                else:
                    media_id = mgid  # Fallback if flat string
                task.image_upload_status = "ready"
                log.info(f"Continuation frame uploaded: {media_id}")
                return (media_id, frame_path)
            else:
                task.image_upload_status = "error"
                log.error(f"Frame upload failed: {upload_resp.error}")
                return None
            
        except Exception as e:
            task.image_upload_status = "error"
            log.error(f"Continuation frame pipeline error: {e}")
            return None
    
    async def _re_upload_continuation_frame(
        self, task: Task, account: AccountManager
    ) -> Optional[str]:
        """Re-upload continuation frame to get fresh mediaId.
        
        Two-tier strategy:
        1. If local frame file exists → encode + upload (fast)
        2. If frame file missing → re-extract from parent's local video via
           FFmpeg → upload (slower, but recovers from deleted frames)
        
        Returns:
            Fresh mediaId string, or None on failure.
        """
        frame_path = task.continuation_frame_local_path
        
        # ── Tier 1: Re-upload existing frame file ──
        if frame_path and Path(frame_path).exists():
            result = await self._upload_frame_file(task, account, frame_path)
            if result:
                return result
        
        # ── Tier 2: Re-extract from parent's downloaded video ──
        log.info(f"[ReUpload] Frame file missing/failed, attempting re-extract from parent video")
        re_extracted_path = await self._re_extract_frame_from_parent(task)
        if re_extracted_path:
            task.continuation_frame_local_path = re_extracted_path
            # Update children preview with new frame
            self._dispatcher.set_children_frame_preview(task.id, re_extracted_path)
            result = await self._upload_frame_file(task, account, re_extracted_path)
            if result:
                return result
        
        log.error(f"[ReUpload] All re-upload strategies failed for task {task.id}")
        task.image_upload_status = "error"
        return None
    
    async def _upload_frame_file(
        self, task: Task, account: AccountManager, frame_path: str
    ) -> Optional[str]:
        """Encode a local frame file and upload to get a mediaId."""
        try:
            from core.media_handler import MediaHandler
            frame_result = MediaHandler.image_to_base64(frame_path)
            if not frame_result:
                log.error(f"[ReUpload] Failed to encode frame: {frame_path}")
                return None
            frame_b64, frame_mime = frame_result
            
            task.image_upload_status = "uploading"
            self._dispatcher.update_progress(
                task.id, task.progress, "📤 Re-uploading frame..."
            )
            
            # Bug 1 fix: Proactive token refresh before upload
            # Access token may have expired during long poll or between
            # force retry and re-upload — same pattern as upscale path (line 1294)
            fresh_token = None
            if account.session.is_token_expired:
                log.info(f"[ReUpload] Access token expired for {account.email}, refreshing...")
                fresh_token = await account.refresh_access_token()
                if not fresh_token:
                    log.error(f"[ReUpload] Token refresh failed for {account.email}")
                    task.image_upload_status = "error"
                    return None
            
            # Resolve access token: prefer fresh_token from refresh, fallback to session
            access_token = fresh_token or account.get_access_token()
            
            # Guard: force refresh if token is still empty (e.g. empty token from profile sync)
            if not access_token:
                log.warning(f"[ReUpload] access_token empty for {account.email}, forcing refresh...")
                access_token = await account.refresh_access_token()
                if not access_token:
                    log.error(f"[ReUpload] Token refresh failed for {account.email}")
                    task.image_upload_status = "error"
                    return None
            
            upload_resp = await self._api_client.upload_image(
                access_token=access_token,
                recaptcha_token="",  # Upload does NOT need reCAPTCHA
                image_base64=frame_b64,
                mime_type=frame_mime,
                account_headers=account.get_api_headers(),
            )
            
            if upload_resp.success:
                mgid = upload_resp.data.get("mediaGenerationId", {})
                media_id = mgid.get("mediaGenerationId") if isinstance(mgid, dict) else mgid
                if media_id:
                    task.image_upload_status = "ready"
                    log.info(f"[ReUpload] Fresh mediaId for task {task.id}: {media_id}")
                    return media_id
            
            log.error(f"[ReUpload] Upload failed: {upload_resp.error if upload_resp else 'no response'}")
            return None
            
        except Exception as e:
            log.error(f"[ReUpload] Upload error: {e}")
            return None
    
    async def _re_extract_frame_from_parent(self, task: Task) -> Optional[str]:
        """Re-extract continuation frame from parent's local video file.
        
        Finds the parent task's first downloaded video (output_uris),
        runs FFmpeg to extract the last frame, and returns the new frame path.
        
        Returns:
            Path to newly extracted frame file, or None on failure.
        """
        if not task.parent_task_id:
            return None
        
        parent = self._dispatcher.get_all_tasks_dict().get(task.parent_task_id)
        if not parent or not parent.output_uris:
            log.warning(f"[ReExtract] Parent task {task.parent_task_id} not found or has no outputs")
            return None
        
        # Find first existing local video from parent
        parent_video = None
        for uri in parent.output_uris:
            if uri and Path(uri).exists() and uri.lower().endswith('.mp4'):
                parent_video = uri
                break
        
        # Bug #4 fix: fallback to video_outputs[].file_720p
        # (output_uris may contain FIFE URLs if complete_task overwrote them)
        if not parent_video and parent.video_outputs:
            for vo in parent.video_outputs:
                if vo.file_720p and Path(vo.file_720p).exists():
                    parent_video = vo.file_720p
                    log.info(f"[ReExtract] Found parent video via video_outputs: {Path(parent_video).name}")
                    break
        
        if not parent_video:
            log.warning(f"[ReExtract] No local video found in parent outputs: {parent.output_uris[:2]}")
            return None
        
        if not self._frame_extractor.is_available:
            log.warning("[ReExtract] FFmpeg not available, cannot re-extract")
            return None
        
        try:
            task.image_upload_status = "extracting"
            self._dispatcher.update_progress(
                task.id, task.progress, "📸 Re-extracting frame..."
            )
            
            loop = asyncio.get_running_loop()
            frame_path = await loop.run_in_executor(
                self._process_pool,
                self._frame_extractor.extract_frame,
                parent_video,
                None,   # auto-generate output path
                task.extract_point_ms,
                True    # from_end=True (VEO start frame = end of previous video)
            )
            
            if frame_path and Path(frame_path).exists():
                log.info(f"[ReExtract] Frame re-extracted: {frame_path} (from {Path(parent_video).name})")
                return frame_path
            
            log.error("[ReExtract] FFmpeg extraction returned no output")
            return None
            
        except Exception as e:
            log.error(f"[ReExtract] Error: {e}")
            return None
    
    def clear_upload_cache(self):
        """Clear the upload cache. Call between sessions/batches if needed."""
        self._upload_cache.clear()
        log.debug("[Engine] Upload cache cleared")
    
    async def _wait_for_recaptcha_ready(
        self, account: AccountManager, max_wait: float = 30.0
    ) -> bool:
        """Layer 2: Wait until Extension confirms grecaptcha is ready.
        
        Polls Extension via check_recaptcha_ready() every 2s with gentle backoff.
        Once ready, pre-fetches tokens via RecaptchaPool.priority_prefetch().
        
        This replaces fixed sleep(3-5s) with deterministic readiness checking.
        If Extension doesn't support check_recaptcha_ready (old version),
        falls back to a 5s fixed delay.
        
        Args:
            account: AccountManager with extension bridge reference.
            max_wait: Maximum seconds to wait before proceeding anyway.
            
        Returns:
            True if grecaptcha confirmed ready, False if timed out.
        """
        bridge = account.extension_bridge
        if not bridge:
            # No extension bridge — fallback to fixed delay
            log.info(f"[Foreman:{account.email}] No extension bridge, using 5s fixed cooldown")
            await asyncio.sleep(5.0)
            return False
        
        # Pre-check: is extension even connected?
        if not bridge.is_connected(account.email):
            log.warning(
                f"[Foreman:{account.email}] Extension NOT connected — "
                f"cannot check reCAPTCHA ready, using 5s fallback"
            )
            await asyncio.sleep(5.0)
            return False
        
        start = asyncio.get_event_loop().time()
        interval = 2.0
        attempt = 0
        
        while (asyncio.get_event_loop().time() - start) < max_wait:
            attempt += 1
            try:
                ready = await bridge.check_recaptcha_ready(account.email, timeout=5.0)
            except Exception as e:
                log.warning(
                    f"[Foreman:{account.email}] reCAPTCHA ready check #{attempt} EXCEPTION: "
                    f"{account.email}: {e}"
                )
                ready = False
            
            elapsed = asyncio.get_event_loop().time() - start
            
            if ready:
                log.info(
                    f"[Foreman:{account.email}] ✅ grecaptcha ready "
                    f"(attempt #{attempt}, waited {elapsed:.1f}s)"
                )
                
                # Layer 3: Pre-fetch tokens while grecaptcha is confirmed ready
                if self._recaptcha_pool:
                    try:
                        fetched = await self._recaptcha_pool.priority_prefetch(
                            account.email, count=2
                        )
                        log.info(
                            f"[Foreman:{account.email}] Priority prefetch: {fetched} token(s) "
                            f"cached for continuation"
                        )
                    except Exception as e:
                        log.debug(f"[Foreman:{account.email}] Priority prefetch failed: {e}")
                
                # Reset unified recovery state on success
                self._account_recovery_phase[account.email] = 0
                self._account_phase_403_count[account.email] = 0
                return True
            else:
                log.info(
                    f"[Foreman:{account.email}] ⏳ reCAPTCHA not ready "
                    f"(attempt #{attempt}, {elapsed:.1f}/{max_wait:.0f}s) — "
                    f"retry in {interval:.1f}s"
                )
            
            await asyncio.sleep(interval)
            interval = min(interval * 1.3, 5.0)  # Gentle backoff: 2→2.6→3.4→4.4→5
        
        elapsed = asyncio.get_event_loop().time() - start
        log.warning(
            f"[Foreman:{account.email}] ⏳ grecaptcha not ready after {elapsed:.1f}s / {attempt} attempts — "
            f"triggering full page reload for recovery"
        )
        
        # Fix #3: Full page reload when reCAPTCHA ready check keeps timing out
        # This recovers the tab from frozen/suspended state where the reCAPTCHA
        # widget is dead. Without this, we'd submit with broken reCAPTCHA → 403.
        if bridge:
            try:
                await bridge._trigger_refresh(
                    account.email,
                    f"reCAPTCHA ready timeout after {attempt} attempts",
                    level="full"
                )
                # Fix #2: Wait for reCAPTCHA widget to re-initialize after reload
                # VEO page takes 13+ seconds to fully load (verified via HAR).
                # Additional time needed for reCAPTCHA Enterprise widget init.
                # Old value 15s was insufficient → widget still dead → 403 cascade.
                post_reload_wait = 25.0
                log.info(
                    f"[Foreman:{account.email}] ⏳ Waiting {post_reload_wait:.0f}s for reCAPTCHA "
                    f"widget to re-initialize after full reload..."
                )
                await asyncio.sleep(post_reload_wait)
                
                # Fix #3: Verify widget is actually ready before returning
                # Don't blindly trust the timer — confirm with real readiness checks
                verify_interval = 3.0
                for verify_attempt in range(3):
                    try:
                        verify_ready = await bridge.check_recaptcha_ready(
                            account.email, timeout=8.0
                        )
                        if verify_ready:
                            log.info(
                                f"[Foreman:{account.email}] ✅ reCAPTCHA confirmed ready "
                                f"after reload (verify attempt #{verify_attempt + 1})"
                            )
                            # Pre-fetch tokens while widget is fresh
                            if self._recaptcha_pool:
                                try:
                                    fetched = await self._recaptcha_pool.priority_prefetch(
                                        account.email, count=2
                                    )
                                    log.info(
                                        f"[Foreman:{account.email}] Post-reload prefetch: "
                                        f"{fetched} token(s) cached"
                                    )
                                except Exception:
                                    pass
                            return True  # Widget recovered!
                    except Exception:
                        pass
                    if verify_attempt < 2:
                        await asyncio.sleep(verify_interval)
                
                log.warning(
                    f"[Foreman:{account.email}] ⚠️ reCAPTCHA still not ready "
                    f"after reload + {post_reload_wait:.0f}s wait + 3 verify attempts"
                )
            except Exception as e:
                log.debug(f"[Foreman:{account.email}] Recovery reload failed: {e}")
        
        return False
    
    async def _pre_upload_r2v_images(self, account: AccountManager):
        """Pre-upload all unique R2V images for this account before task processing.
        
        Scans all pending R2V tasks, collects unique image_paths not yet in
        upload_cache for this account, and uploads them once.
        
        Cache key = {path}:{email} — each account uploads its own copy.
        Cross-account mediaIds are never shared (asset permission isolation).
        
        Called once per foreman after readiness gate, before the main loop.
        Subsequent tasks will hit cache → skip upload → save ~10s/image/task.
        """
        import time as _time
        
        # Collect unique image paths from all pending R2V tasks
        unique_paths = set()
        all_tasks = self._dispatcher.get_all_tasks_dict()
        for task in all_tasks.values():
            if (task.workflow_type == 'R2V'
                    and task.image_paths
                    and task.state.value in ('ready', 'pending')):
                for p in task.image_paths:
                    cache_key = f"{p}:{account.email}"
                    if cache_key not in self._upload_cache:
                        unique_paths.add(p)
        
        if not unique_paths:
            return
        
        log.info(
            f"[PreUpload:{account.email}] "
            f"Uploading {len(unique_paths)} unique image(s) for R2V batch"
        )
        t0 = _time.monotonic()
        uploaded = 0
        
        for path in sorted(unique_paths):
            if self._stop_event.is_set():
                break
            
            try:
                # Anti-detect delay between uploads
                if uploaded > 0:
                    if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else True:
                        await self._burst_controller.wait(account.email)
                
                # Encode image
                from core.media_handler import MediaHandler
                result = MediaHandler.image_to_base64(path)
                if not result:
                    log.error(f"[PreUpload] Failed to encode: {path}")
                    continue
                img_b64, mime_type = result
                
                # Upload (HAR verified: always IMAGE_ASPECT_RATIO_LANDSCAPE)
                upload_resp = await self._api_client.upload_image(
                    access_token=account.get_access_token(),
                    recaptcha_token="",
                    image_base64=img_b64,
                    mime_type=mime_type,
                    aspect_ratio="IMAGE_ASPECT_RATIO_LANDSCAPE",
                    account_headers=account.get_api_headers(),
                )
                
                if upload_resp.success:
                    mgid = upload_resp.data.get("mediaGenerationId", {})
                    media_id = mgid.get("mediaGenerationId") if isinstance(mgid, dict) else mgid
                    if media_id:
                        cache_key = f"{path}:{account.email}"
                        async with self._upload_cache_lock:
                            self._upload_cache[cache_key] = media_id
                        uploaded += 1
                        log.info(f"[PreUpload]   {Path(path).name} → {media_id[:40]}...")
                    else:
                        log.warning(f"[PreUpload]   Upload OK but no mediaId: {path}")
                else:
                    log.error(f"[PreUpload]   Upload failed: {path}: {upload_resp.error}")
            except Exception as e:
                log.error(f"[PreUpload]   Error uploading {path}: {e}")
        
        elapsed = _time.monotonic() - t0
        log.info(
            f"[PreUpload:{account.email}] "
            f"Done: {uploaded}/{len(unique_paths)} uploaded in {elapsed:.1f}s"
        )
    
    async def _resolve_image_paths(self, task: Task, account: AccountManager):
        """Upload local image files to get mediaGenerationIds.
        
        Called when task.image_paths has been populated by tag resolution
        in AppController but task.image_uris is still empty.
        Each local file is base64-encoded and uploaded via the API.
        
        Bug 2 fix: Uses _upload_cache to avoid re-uploading the same file
        for the same account within a session. Key = (path, email).
        """
        log.info(f"Uploading {len(task.image_paths)} image(s) for task {task.id}")
        uploaded_uris = []
        task.image_upload_status = "uploading"
        self._dispatcher.update_progress(task.id, task.progress, "📤 Uploading images...")
        
        for path in task.image_paths:
            try:
                # Bug 2 fix: Check cache first — same file + same account = reuse mediaId
                cache_key = f"{path}:{account.email}"
                async with self._upload_cache_lock:
                    cached_id = self._upload_cache.get(cache_key)
                if cached_id:
                    uploaded_uris.append(cached_id)
                    log.info(f"  Cache hit: {Path(path).name} → {cached_id} (skipped upload)")
                    continue
                
                # Use MediaHandler for proper format conversion + quality
                from core.media_handler import MediaHandler
                result = MediaHandler.image_to_base64(path)
                if not result:
                    log.error(f"  Failed to encode image: {path}")
                    continue
                img_b64, mime_type = result
                
                # HAR verified: upload endpoint always uses IMAGE_ASPECT_RATIO_LANDSCAPE
                # regardless of the video's aspect ratio. Do NOT pass task.aspect_ratio
                # (which is VIDEO_ASPECT_RATIO_*) — causes HTTP 400.
                upload_resp = await self._api_client.upload_image(
                    access_token=account.get_access_token(),
                    recaptcha_token="",  # Not used by upload endpoint
                    image_base64=img_b64,
                    mime_type=mime_type,
                    aspect_ratio="IMAGE_ASPECT_RATIO_LANDSCAPE",
                    account_headers=account.get_api_headers(),
                )

                
                if upload_resp.success:
                    mgid = upload_resp.data.get("mediaGenerationId", {})
                    if isinstance(mgid, dict):
                        media_id = mgid.get("mediaGenerationId")
                    else:
                        media_id = mgid
                    if media_id:
                        uploaded_uris.append(media_id)
                        # Bug 2 fix: Cache the mediaId for reuse
                        async with self._upload_cache_lock:
                            self._upload_cache[cache_key] = media_id
                        log.info(f"  Uploaded: {Path(path).name} → {media_id}")
                    else:
                        log.warning(f"  Upload OK but no mediaId for {path}")
                else:
                    log.error(f"  Upload failed for {path}: {upload_resp.error}")
            except Exception as e:
                log.error(f"  Image upload error for {path}: {e}")
        
        if uploaded_uris:
            task.image_uris = uploaded_uris
            task.image_upload_status = "ready"
            log.info(f"  {len(uploaded_uris)} image(s) uploaded successfully")
        else:
            task.image_upload_status = "error"
    
    def _auto_retry_partial_failure(
        self, original_task: Task, failed_count: int, failed_labels: list
    ):
        """Auto-retry failed variants by creating a new task.
        
        When a generation produces N of M variants (partial failure),
        create a new task with the same prompt/settings but output_count
        set to the number of failed variants. The retry task goes through
        the full pipeline: generate → download → upscale.
        
        This is FREE for both T2V and I2V — no additional credits.
        """
        import uuid
        
        retry_id = f"retry-{str(uuid.uuid4())[:8]}"
        
        retry_task = Task(
            id=retry_id,
            workflow_type=original_task.workflow_type,
            prompt=original_task.prompt,
            aspect_ratio=original_task.aspect_ratio,
            model=original_task.model,
            output_count=failed_count,
            duration_seconds=original_task.duration_seconds,
            seed=original_task.seed,
            image_uris=list(original_task.image_uris),
            image_paths=list(original_task.image_paths),
            download_quality=original_task.download_quality,
            output_folder=original_task.output_folder,
            project_name=original_task.project_name,
            prompt_index=original_task.prompt_index,  # Same index → naming collision handled by dedup
            # H2 fix: Copy continuation fields for F2V/I2V workflows
            continuation_frame_uri=original_task.continuation_frame_uri,
            continuation_frame_local_path=original_task.continuation_frame_local_path,
            extract_point_ms=original_task.extract_point_ms,
        )
        # Pin to same account — reuse project_id, same image_uris (account-bound)
        retry_task.required_account = original_task.assigned_account
        
        submitted = self._dispatcher.submit_task(retry_task)
        if submitted:
            log.info(
                f"🔄 Auto-retry submitted: {retry_id} "
                f"(output_count={failed_count}, "
                f"replacing {', '.join(failed_labels)})"
            )
        else:
            log.error(
                f"❌ Auto-retry submit failed for {retry_id} "
                f"(missing: {', '.join(failed_labels)})"
            )
    
    def _auto_retry_download_failure(
        self, original_task: Task, failed_count: int, failed_labels: list
    ):
        """Auto-retry failed downloads by creating a new generation task.
        
        Checks dl_retry_generation_count against max limit from settings.
        If max retries exhausted → fail_task (cascade-fails continuation children).
        Otherwise → create retry task with incremented counter.
        """
        import uuid
        from config.settings import get_settings as _gs
        _s = _gs()
        max_retries = getattr(_s, 'auto_retry_download_max', 3)
        
        current_count = getattr(original_task, 'dl_retry_generation_count', 0)
        
        if current_count >= max_retries:
            # Max retries exhausted → fail task + cascade-fail children
            error_msg = (
                f"Download re-generation exhausted ({current_count}/{max_retries}), "
                f"missing: {', '.join(failed_labels)}"
            )
            log.error(
                f"❌ [{original_task.id}] {error_msg}"
            )
            self._dispatcher.update_progress(
                original_task.id, 87,
                f"❌ Download retry {current_count}/{max_retries} exhausted — FAILED"
            )
            self._dispatcher.fail_task(
                original_task.id, error_msg
            )
            return
        
        retry_id = f"dl-retry-{str(uuid.uuid4())[:8]}"
        
        retry_task = Task(
            id=retry_id,
            workflow_type=original_task.workflow_type,
            prompt=original_task.prompt,
            aspect_ratio=original_task.aspect_ratio,
            model=original_task.model,
            output_count=failed_count,
            duration_seconds=original_task.duration_seconds,
            seed=original_task.seed,
            image_uris=list(original_task.image_uris),
            image_paths=list(original_task.image_paths),
            download_quality=original_task.download_quality,
            output_folder=original_task.output_folder,
            project_name=original_task.project_name,
            prompt_index=original_task.prompt_index,
            continuation_frame_uri=original_task.continuation_frame_uri,
            continuation_frame_local_path=original_task.continuation_frame_local_path,
            extract_point_ms=original_task.extract_point_ms,
            dl_retry_generation_count=current_count + 1,
        )
        # Pin to same account — reuse project_id, same image_uris (account-bound)
        retry_task.required_account = original_task.assigned_account
        
        submitted = self._dispatcher.submit_task(retry_task)
        if submitted:
            log.info(
                f"🔄 Auto-retry (download failure): {retry_id} "
                f"(attempt {current_count + 1}/{max_retries}, "
                f"output_count={failed_count}, "
                f"replacing {', '.join(failed_labels)})"
            )
        else:
            log.error(
                f"❌ Auto-retry (download failure) submit failed for {retry_id} "
                f"(missing: {', '.join(failed_labels)})"
            )
    
    async def _auto_upscale(
        self, task: Task, account: AccountManager,
        output_uris: list, media_ids: list,
    ) -> list:
        """Auto-upscale videos if download_quality > 720p.
        
        Retry strategy (cost-aware):
        - Submit retry: 3 attempts with reCAPTCHA refresh (free for both 1080p/4K)
        - Poll FAILED re-submit: 1 attempt for 1080p only (free), skip for 4K (costs credits)
        - Poll network error: continues within existing 60-poll loop
        
        Args:
            output_uris: fifeUrls (720p download URLs) — for fallback logging only
            media_ids: metadata.name values (protobuf Base64) — for upscale API
        
        Returns:
            List of upscaled fifeUrls, empty list if all fail.
        """
        quality_map = {
            "1080p": "VIDEO_RESOLUTION_1080P",
            "4K": "VIDEO_RESOLUTION_4K",
        }
        resolution = quality_map.get(task.download_quality)
        if not resolution:
            return []  # 720p or unknown → no upscale needed
        
        is_free_upscale = (resolution == "VIDEO_RESOLUTION_1080P")
        from core.api_client import generate_random_seed
        total = len(media_ids)
        upscaled_uris = [None] * total  # ★ None placeholders — index stability
        max_submit_retries = 5
        
        for idx, media_id in enumerate(media_ids):
            video_label = f"{idx + 1}/{total}"
            if not media_id:
                log.warning(f"Upscale {video_label}: no mediaId, skipping")
                if idx < len(task.video_outputs):
                    task.video_outputs[idx].upscale_status = "skipped"
                continue
            
            try:
                # === Submit with retry (5 attempts, browser restart on 3x reCAPTCHA fail) ===
                resp = None
                for attempt in range(max_submit_retries):
                    # Risk 5 fix: Serialize upscale submits per account (prevents burst)
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Lock()
                    async with self._account_rate_locks[account.email]:
                        # Fix G7: Anti-detect delay before inline upscale submit
                        if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else True:
                            await self._burst_controller.wait(account.email)
                        # ★ PRIMARY PATH: Extension-based upscale
                        ext_bridge = getattr(account, 'extension_bridge', None)
                        use_extension = (
                            ext_bridge is not None
                            and ext_bridge.is_connected(account.email)
                        )
                        
                        if use_extension:
                            log.info(
                                f"Upscale {video_label}: submitting via Extension "
                                f"(attempt {attempt + 1}/{max_submit_retries})"
                            )
                            # Reuse original sceneId
                            orig_scene_id = (
                                task.scene_ids[idx]
                                if idx < len(task.scene_ids)
                                else None
                            )
                            upscale_body = self._api_client.build_upscale_body(
                                video_media_id=media_id,
                                target_resolution=resolution,
                                aspect_ratio=task.aspect_ratio,
                                seed=generate_random_seed(),
                                scene_id=orig_scene_id,
                            )
                            ext_result = await ext_bridge.submit_upscale(
                                email=account.email,
                                body=upscale_body,
                            )
                            
                            # Convert Extension result → APIResponse-compatible
                            from core.api_client import APIResponse
                            if ext_result and ext_result.get('success'):
                                resp = APIResponse(
                                    success=True,
                                    data=ext_result.get('data', {}),
                                )
                            elif ext_result:
                                error_msg = ext_result.get('error', '')
                                status_code = ext_result.get('status', 0)
                                if status_code == 403:
                                    error_msg = f"403 Forbidden: {error_msg}"
                                resp = APIResponse(
                                    success=False,
                                    error=error_msg or f"Extension upscale failed (HTTP {status_code})",
                                )
                            else:
                                resp = APIResponse(
                                    success=False,
                                    error="Extension upscale returned None (timeout/disconnected)",
                                )
                        else:
                            # ★ FALLBACK: Traditional aiohttp path
                            recaptcha_token = await account.refresh_recaptcha() or ""
                            if not recaptcha_token:
                                recaptcha_token = account.get_recaptcha_token() or ""
                            
                            # Risk 7 fix: Also go through API semaphore
                            sem = self._get_api_semaphore(account.email)
                            async with sem:
                                resp = await self._api_client.upscale_video(
                                    access_token=account.get_access_token() or "",
                                    recaptcha_token=recaptcha_token,
                                    video_media_id=media_id,
                                    target_resolution=resolution,
                                    aspect_ratio=task.aspect_ratio,
                                    seed=generate_random_seed(),
                                    account_headers=account.get_api_headers(),
                                )
                        
                        # Risk 6 fix: reCAPTCHA cooldown after submit
                        # For Extension path: no-op (Extension manages its own reCAPTCHA)
                        account.invalidate_recaptcha()
                        await asyncio.sleep(1.0)
                    # Rate lock released
                    
                    if resp.success:
                        break
                    
                    log.warning(
                        f"Upscale {video_label} submit attempt {attempt + 1}/{max_submit_retries} "
                        f"failed: {resp.error}"
                    )
                    
                    # Tiered browser recovery on reCAPTCHA failures (same as worker)
                    error_lower = (resp.error or "").lower()
                    if "recaptcha" in error_lower:
                        if attempt == 1:
                            # Tier 1: Soft recovery (keep browser alive)
                            log.warning(
                                f"🔄 Upscale {video_label}: reCAPTCHA failed {attempt + 1}x. "
                                f"Soft recovery (no kill)..."
                            )
                            try:
                                soft_ok = await account.soft_recover_browser()
                                if soft_ok:
                                    log.info(f"✅ Upscale: Soft recovery OK for {account.email}")
                                else:
                                    log.warning(f"⚠️ Upscale: Soft recovery returned False")
                            except Exception as soft_err:
                                log.error(f"❌ Upscale soft recovery failed: {soft_err}")
                                
                        elif attempt == 2:
                            # Tier 2: Hard restart (kill + relaunch) as fallback
                            log.warning(
                                f"🔄 Upscale {video_label}: reCAPTCHA failed 3x. "
                                f"Full browser restart (kill + relaunch)..."
                            )
                            try:
                                restart_ok = await account.restart_browser()
                                if restart_ok:
                                    log.info(f"✅ Upscale: Browser restarted for {account.email}. Retrying...")
                                    # Fix: borrow x-client-data from other accounts
                                    # after restart (new browser may have short value)
                                    self._account_manager.fix_short_client_data()
                                    # Fix #3: Wait for x-client-data recovery after restart
                                    # Chrome Variations Service needs 15-30s to generate
                                    # full x-client-data. Without this gate, attempts 4-5
                                    # fire with 8-char stale value → guaranteed 403.
                                    log.info(f"⏳ Upscale: Waiting for x-client-data recovery...")
                                    await self._wait_for_account_ready(account, timeout=30.0)
                                    await self._wait_for_recaptcha_ready(account, max_wait=15.0)
                                else:
                                    log.error(f"❌ Upscale: Browser restart returned False")
                            except Exception as restart_err:
                                log.error(f"❌ Upscale browser restart failed: {restart_err}")
                    
                    if attempt < max_submit_retries - 1:
                        delay = min(5 * (attempt + 1), 15)
                        await asyncio.sleep(delay)
                else:
                    # All submit attempts exhausted
                    error_msg = f"Submit failed after {max_submit_retries} retries: {resp.error if resp else 'unknown'}"
                    if idx < len(task.video_outputs):
                        task.video_outputs[idx].upscale_status = "failed"
                        task.video_outputs[idx].upscale_error = error_msg
                    task.upscale_error = error_msg
                    log.error(f"Upscale {video_label}: {error_msg}")
                    continue
                
                # === Extract operation ID ===
                ops = resp.data.get("operations", [])
                if not ops:
                    if idx < len(task.video_outputs):
                        task.video_outputs[idx].upscale_status = "failed"
                        task.video_outputs[idx].upscale_error = "No operation returned"
                    continue
                
                op_name = ops[0].get("operation", {}).get("name", "")
                scene_id = ops[0].get("sceneId", "")
                if not op_name:
                    if idx < len(task.video_outputs):
                        task.video_outputs[idx].upscale_status = "failed"
                        task.video_outputs[idx].upscale_error = "No operation name in response"
                    continue
                
                log.info(f"Upscale {video_label} started: op={op_name}")
                
                # === Poll with status tracking ===
                upscale_result = await self._poll_upscale(
                    task, account, video_label, op_name, scene_id
                )
                
                if upscale_result:
                    upscaled_uris[idx] = upscale_result[0]  # ★ Index preserved
                    if idx < len(task.video_outputs):
                        task.video_outputs[idx].upscale_status = "success"
                    log.info(f"Upscale {video_label} done ✅")
                elif is_free_upscale:
                    # 1080p poll FAILED → re-submit once (free, no credit cost)
                    log.info(f"Upscale {video_label}: 1080p failed, re-submitting (free)")
                    # Risk 5+6 fix: Rate lock + cooldown for re-submit
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Lock()
                    async with self._account_rate_locks[account.email]:
                        # Fix G7: Anti-detect delay before inline upscale re-submit
                        if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else True:
                            await self._burst_controller.wait(account.email)
                        # ★ PRIMARY PATH: Extension-based re-submit
                        ext_bridge = getattr(account, 'extension_bridge', None)
                        use_ext = (ext_bridge and ext_bridge.is_connected(account.email))
                        
                        if use_ext:
                            # Reuse original sceneId
                            orig_scene_id = (
                                task.scene_ids[idx]
                                if idx < len(task.scene_ids)
                                else None
                            )
                            upscale_body = self._api_client.build_upscale_body(
                                video_media_id=media_id,
                                target_resolution=resolution,
                                aspect_ratio=task.aspect_ratio,
                                seed=generate_random_seed(),
                                scene_id=orig_scene_id,
                            )
                            ext_r = await ext_bridge.submit_upscale(
                                email=account.email, body=upscale_body,
                            )
                            from core.api_client import APIResponse
                            if ext_r and ext_r.get('success'):
                                resp2 = APIResponse(success=True, data=ext_r.get('data', {}))
                            elif ext_r:
                                resp2 = APIResponse(
                                    success=False,
                                    error=ext_r.get('error', '') or f"HTTP {ext_r.get('status', 0)}",
                                )
                            else:
                                resp2 = APIResponse(success=False, error="Extension timeout")
                        else:
                            # ★ FALLBACK: aiohttp
                            recaptcha_token = await account.refresh_recaptcha() or ""
                            sem = self._get_api_semaphore(account.email)
                            async with sem:
                                resp2 = await self._api_client.upscale_video(
                                    access_token=account.get_access_token() or "",
                                    recaptcha_token=recaptcha_token,
                                    video_media_id=media_id,
                                    target_resolution=resolution,
                                    aspect_ratio=task.aspect_ratio,
                                    seed=generate_random_seed(),
                                    account_headers=account.get_api_headers(),
                                )
                        account.invalidate_recaptcha()
                        await asyncio.sleep(1.0)
                    if resp2.success:
                        ops2 = resp2.data.get("operations", [])
                        if ops2:
                            op2 = ops2[0].get("operation", {}).get("name", "")
                            sid2 = ops2[0].get("sceneId", "")
                            if op2:
                                result2 = await self._poll_upscale(
                                    task, account, video_label, op2, sid2
                                )
                                if result2:
                                    upscaled_uris[idx] = result2[0]  # ★ Index preserved
                                    if idx < len(task.video_outputs):
                                        task.video_outputs[idx].upscale_status = "success"
                                        task.video_outputs[idx].upscale_error = ""
                                    log.info(f"Upscale {video_label} re-submit done ✅")
                                else:
                                    if idx < len(task.video_outputs):
                                        task.video_outputs[idx].upscale_status = "failed"
                                        task.video_outputs[idx].upscale_error = task._upscale_error
                    else:
                        if idx < len(task.video_outputs):
                            task.video_outputs[idx].upscale_status = "failed"
                            task.video_outputs[idx].upscale_error = task._upscale_error
                else:
                    # 4K poll FAILED → do NOT re-submit (costs credits)
                    if idx < len(task.video_outputs):
                        task.video_outputs[idx].upscale_status = "failed"
                        task.video_outputs[idx].upscale_error = task._upscale_error or "4K upscale failed"
                    log.warning(
                        f"Upscale {video_label}: 4K failed, keeping 720p to save credits"
                    )
            
            except Exception as e:
                if idx < len(task.video_outputs):
                    task.video_outputs[idx].upscale_status = "failed"
                    task.video_outputs[idx].upscale_error = str(e)
                task.upscale_error = str(e)
                log.error(f"Upscale {video_label} error: {e}")
        
        return upscaled_uris
    
    async def _poll_upscale(
        self, task: Task, account: AccountManager,
        video_label: str, op_name: str, scene_id: str,
    ) -> list:
        """Poll upscale operation until complete/failed/timeout.
        
        Returns:
            List of upscaled fifeUrls on success, empty list on failure.
        """
        poll_status = "MEDIA_GENERATION_STATUS_PENDING"
        max_polls = 60  # 60 × 5s = max 5 min
        
        for poll_num in range(max_polls):
            # Risk 2 fix: Jitter for upscale polls (prevents 4 workers polling at t=0,5,10...)
            jitter = random.uniform(0, 2.0)
            await asyncio.sleep(30 + jitter)
            
            # Progress: map to 88-90% range
            progress = min(90, 88 + int(poll_num * 0.5))
            self._dispatcher.update_progress(
                task.id, progress,
                f"⬆️ Upscaling {video_label}"
            )
            
            # Risk 7 fix: Limit concurrent API calls per account
            sem = self._get_api_semaphore(account.email)
            async with sem:
                poll_resp = await self._api_client.check_status(
                    access_token=account.get_access_token() or "",
                    recaptcha_token="",
                    operations=[{
                        "operation": {"name": op_name},
                        "sceneId": scene_id,
                        "status": poll_status,
                    }],
                    account_headers=account.get_api_headers(),
                )
            
            if not poll_resp.success:
                continue  # Network error → retry next poll
            
            poll_ops = poll_resp.data.get("operations", [])
            if not poll_ops:
                continue
            
            server_status = poll_ops[0].get("status", "")
            
            if server_status != poll_status:
                log.info(f"Upscale {video_label}: {poll_status} → {server_status}")
                poll_status = server_status
            
            if server_status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                return self._extract_output_uris(poll_resp.data)
            
            elif server_status == "MEDIA_GENERATION_STATUS_FAILED":
                # Error can be at operation.error or top-level error
                op_error = poll_ops[0].get("operation", {}).get("error", {})
                top_error = poll_ops[0].get("error", {})
                error = (
                    op_error.get("message")
                    or top_error.get("message")
                    or "unknown"
                )
                task.upscale_error = f"Server failed: {error}"
                log.error(f"Upscale {video_label} failed: {error}")
                return []
        
        # Timeout
        task.upscale_error = "Timeout (5 min)"
        log.warning(f"Upscale {video_label} timeout (5 min), 720p already saved")
        return []
    
    async def re_upscale_task(
        self, task_id: str, account: AccountManager,
        failed_only: bool = True,
    ) -> bool:
        """Re-upscale videos in a completed task via UpscaleQueue.
        
        Routes the re-upscale through the same UpscaleQueue pipeline as normal
        upscale, giving it the same warm-up, 5-retry recovery, cooldown gating,
        and circuit breaker protections.
        
        Args:
            failed_only: If True, only retry videos with upscale_status='failed'.
                        If False, re-upscale ALL videos regardless of status.
        """
        task = self._dispatcher.get_task(task_id)
        if not task:
            log.warning(f"Re-upscale {task_id}: task not found")
            return False
        
        # Fallback: rebuild upscale_media_ids from video_outputs if missing
        if not task.upscale_media_ids and task.video_outputs:
            rebuilt = [vo.media_id or "" for vo in task.video_outputs]
            if any(rebuilt):
                task.upscale_media_ids = rebuilt
                valid_count = sum(1 for m in rebuilt if m)
                log.info(f"Re-upscale {task_id}: rebuilt media_ids from video_outputs ({valid_count}/{len(rebuilt)} valid)")
        
        if not task.upscale_media_ids:
            log.warning(f"Re-upscale {task_id}: no media_ids (video_outputs also empty)")
            return False
        
        # Determine which videos need re-upscale
        failed_indices = []
        if task.video_outputs:
            if failed_only:
                failed_indices = [
                    vo.index for vo in task.video_outputs
                    if vo.upscale_status == "failed"
                ]
            else:
                for vo in task.video_outputs:
                    vo.upscale_status = ""
                    vo.upscale_error = ""
                    vo.file_upscaled = ""
                failed_indices = list(range(len(task.video_outputs)))
        else:
            failed_indices = list(range(len(task.upscale_media_ids)))
        
        if not failed_indices:
            log.info(f"Re-upscale {task_id}: no videos to upscale")
            return True
        
        # Build UpscaleJob with retry_indices pointing to specific videos
        from core.upscale_queue import UpscaleJob
        media_ids = [
            task.upscale_media_ids[i] if i < len(task.upscale_media_ids) else ""
            for i in failed_indices
        ]
        
        job = UpscaleJob(
            task_id=task_id,
            account_email=account.email,
            original_account=account.email,  # DD6
            media_ids=media_ids,
            output_uris=task.output_uris or [],
            target_quality=task.download_quality or "1080p",
            aspect_ratio=task.aspect_ratio or "VIDEO_ASPECT_RATIO_LANDSCAPE",
            retry_indices=failed_indices,
        )
        
        label = "failed" if failed_only else "all"
        self._dispatcher.update_progress(
            task.id, 88, f"⬆️ Re-upscaling {label} videos..."
        )
        
        self._upscale_queue.enqueue(job, force=True)
        log.info(
            f"Re-upscale {task_id}: enqueued {len(failed_indices)} videos "
            f"to UpscaleQueue ({label})"
        )
        return True
    
    async def re_upscale_single_video(
        self, task_id: str, video_index: int, account: AccountManager,
    ) -> bool:
        """Re-upscale a SINGLE video by index via UpscaleQueue.
        
        Called from UI when user right-clicks a red thumbnail.
        Routes through the same UpscaleQueue pipeline as normal upscale.
        """
        task = self._dispatcher.get_task(task_id)
        if not task:
            log.warning(f"Re-upscale single {task_id}[{video_index}]: task not found")
            return False
        
        # Fallback: rebuild upscale_media_ids from video_outputs if missing
        if not task.upscale_media_ids and task.video_outputs:
            rebuilt = [vo.media_id or "" for vo in task.video_outputs]
            if any(rebuilt):
                task.upscale_media_ids = rebuilt
                valid_count = sum(1 for m in rebuilt if m)
                log.info(
                    f"Re-upscale single {task_id}[{video_index}]: "
                    f"rebuilt media_ids ({valid_count}/{len(rebuilt)} valid)"
                )
        
        if not task.upscale_media_ids:
            log.warning(f"Re-upscale single {task_id}[{video_index}]: no media_ids")
            return False
        
        if video_index >= len(task.upscale_media_ids):
            log.warning(
                f"Re-upscale single {task_id}[{video_index}]: index out of range "
                f"({len(task.upscale_media_ids)} media_ids)"
            )
            return False
        
        media_id = task.upscale_media_ids[video_index]
        if not media_id:
            log.warning(
                f"Re-upscale single {task_id}[{video_index}]: "
                f"no media_id for this video"
            )
            return False
        
        # Build UpscaleJob with single video
        from core.upscale_queue import UpscaleJob
        job = UpscaleJob(
            task_id=task_id,
            account_email=account.email,
            original_account=account.email,  # DD6
            media_ids=[media_id],
            output_uris=task.output_uris or [],
            target_quality=task.download_quality or "1080p",
            aspect_ratio=task.aspect_ratio or "VIDEO_ASPECT_RATIO_LANDSCAPE",
            retry_indices=[video_index],
        )
        
        self._dispatcher.update_progress(
            task.id, 88, f"⬆️ Re-upscaling video {video_index + 1}..."
        )
        
        self._upscale_queue.enqueue(job, force=True)
        log.info(
            f"Re-upscale single {task_id}[{video_index}]: "
            f"enqueued to UpscaleQueue"
        )
        return True
    
    async def re_download_720p(
        self, task_id: str, account: 'AccountManager',
    ) -> bool:
        """Re-download 720p videos by re-polling completed operations.
        
        Workflow:
        1. Get task's operation_names (from video_outputs if needed)
        2. Re-poll via check_status() to obtain fresh fifeUrls
        3. Download 720p using existing _download_outputs()
        
        Bug #7 fix: If provided account is unavailable, falls back to any
        available account (operation_names are not account-scoped for polling).
        
        Use case: 720p files were deleted, corrupted, or download partially failed.
        """
        task = self._dispatcher.get_task(task_id)
        if not task:
            log.warning(f"Re-download {task_id}: task not found")
            return False
        
        # Bug #7: Fallback account if provided one is unavailable
        if not account or not account.is_enabled:
            log.warning(f"Re-download {task_id}: assigned account unavailable, trying fallback")
            fallback = await self._account_manager.get_available_account()
            if fallback:
                log.info(f"Re-download {task_id}: using fallback account {fallback.email}")
                account = fallback
            else:
                log.error(f"Re-download {task_id}: no available accounts for fallback")
                self._dispatcher.update_progress(
                    task_id, 100, "⚠️ Re-download failed: no available accounts"
                )
                return False
        
        # Collect operation_names — prefer task-level, fallback to video_outputs
        op_names = list(task.operation_names) if task.operation_names else []
        scene_ids = list(task.scene_ids) if task.scene_ids else []
        
        if not op_names and task.video_outputs:
            op_names = [vo.operation_name for vo in task.video_outputs if vo.operation_name]
            scene_ids = [vo.scene_id for vo in task.video_outputs if vo.operation_name]
            if op_names:
                log.info(f"Re-download {task_id}: rebuilt operation_names from video_outputs ({len(op_names)})")
        
        if not op_names:
            log.warning(f"Re-download {task_id}: no operation_names — cannot re-poll")
            return False
        
        self._dispatcher.update_progress(task.id, 50, "🔄 Re-polling for download URLs...")
        
        # Build poll request (mark all as SUCCESSFUL since they completed before)
        ops_to_poll = []
        for i, op_name in enumerate(op_names):
            sid = scene_ids[i] if i < len(scene_ids) else ""
            ops_to_poll.append({
                "operation": {"name": op_name},
                "sceneId": sid,
                "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
            })
        
        # Proactive token refresh — token may have expired since original generation
        fresh_token = None
        if account.session.is_token_expired:
            log.info(f"[ReDownload] Access token expired for {account.email}, refreshing...")
            fresh_token = await account.refresh_access_token()
            if not fresh_token:
                log.error(f"[ReDownload] Token refresh failed for {account.email}")
                self._dispatcher.update_progress(
                    task.id, 100, "⚠️ Re-download failed: auth expired, please re-login"
                )
                return False
        
        # Resolve access token: prefer fresh_token from refresh, fallback to session
        access_token = fresh_token or account.get_access_token()
        
        # Guard: force refresh if token is still empty (e.g. empty token from profile sync)
        if not access_token:
            log.warning(f"[ReDownload] access_token empty for {account.email}, forcing refresh...")
            access_token = await account.refresh_access_token()
            if not access_token:
                log.error(f"[ReDownload] Token refresh failed for {account.email}")
                self._dispatcher.update_progress(
                    task.id, 100, "⚠️ Re-download failed: auth expired, please re-login"
                )
                return False
        
        # Re-poll to get fresh fifeUrls
        sem = self._get_api_semaphore(account.email)
        async with sem:
            response = await self._api_client.check_status(
                access_token=access_token,
                recaptcha_token="",
                operations=ops_to_poll,
                account_headers=account.get_api_headers(),
            )
        
        if not response.success:
            log.error(f"Re-download {task_id}: poll failed — {response.error}")
            self._dispatcher.update_progress(task.id, 100, f"⚠️ Re-download failed: {response.error}")
            return False
        
        # Extract fifeUrls from poll response
        details = self._extract_output_details(response.data)
        if not details:
            log.warning(f"Re-download {task_id}: no fifeUrls in poll response")
            self._dispatcher.update_progress(task.id, 100, "⚠️ Re-download failed: no URLs in response")
            return False
        
        fife_urls = [d["fifeUrl"] for d in details]
        log.info(f"Re-download {task_id}: got {len(fife_urls)} fresh fifeUrls — downloading 720p")
        
        self._dispatcher.update_progress(
            task.id, 70, f"⬇️ Re-downloading {len(fife_urls)} videos (720p)..."
        )
        
        # Collect existing 720p paths for overwrite (replace broken/incomplete files)
        existing_720p = []
        for vo in task.video_outputs:
            existing_720p.append(vo.file_720p if vo.file_720p else None)
        
        # Download 720p — overwrite existing broken files
        local_paths = await self._download_outputs(
            task, fife_urls,
            quality_subfolder="720p",
            generate_thumbnails=True,
            overwrite_paths=existing_720p,
        )
        
        if not local_paths:
            log.error(f"Re-download {task_id}: download returned no files")
            self._dispatcher.update_progress(task.id, 100, "⚠️ Re-download failed")
            return False
        
        # Update video_outputs with new 720p paths
        for i, path in enumerate(local_paths):
            if path and i < len(task.video_outputs):
                task.video_outputs[i].file_720p = path
                if not task.video_outputs[i].file_upscaled:
                    task.video_outputs[i].quality = "720p"
        
        # Update output_uris
        final_paths = []
        for vo in task.video_outputs:
            if vo.file_upscaled:
                final_paths.append(vo.file_upscaled)
            elif vo.file_720p:
                final_paths.append(vo.file_720p)
        if final_paths:
            task.output_uris = final_paths
        
        # Also rebuild upscale_media_ids from response if available
        media_ids_from_response = [d.get("mediaId", "") for d in details if d.get("mediaId")]
        if media_ids_from_response and not task.upscale_media_ids:
            task.upscale_media_ids = media_ids_from_response
        
        self._dispatcher.update_progress(
            task.id, 100, f"✅ Re-downloaded {len(local_paths)} videos (720p)"
        )
        
        if self._on_task_completed:
            self._on_task_completed(task)
        self._save_manifest(task)
        
        log.info(f"Re-download {task_id}: done — {len(local_paths)} files saved")
        return True
    
    async def re_download_single_720p(
        self, task_id: str, video_index: int, account: 'AccountManager',
    ) -> bool:
        """Re-download a single 720p video by index.
        
        Workflow:
        1. Get operation_name from video_outputs[video_index]
        2. Re-poll single operation via check_status()
        3. Download the specific fifeUrl
        4. Update video_outputs[video_index].file_720p
        """
        task = self._dispatcher.get_task(task_id)
        if not task:
            log.warning(f"Re-download single {task_id}[{video_index}]: task not found")
            return False
        
        if video_index >= len(task.video_outputs):
            log.warning(f"Re-download single {task_id}[{video_index}]: index out of range ({len(task.video_outputs)} videos)")
            return False
        
        vo = task.video_outputs[video_index]
        op_name = vo.operation_name
        if not op_name:
            # Fallback: try task-level operation_names
            if video_index < len(task.operation_names):
                op_name = task.operation_names[video_index]
        
        if not op_name:
            log.warning(f"Re-download single {task_id}[{video_index}]: no operation_name")
            return False
        
        scene_id = vo.scene_id or ""
        if not scene_id and video_index < len(task.scene_ids):
            scene_id = task.scene_ids[video_index]
        
        self._dispatcher.update_progress(
            task.id, 50, f"🔄 Re-polling video {video_index + 1} for download URL..."
        )
        
        # Re-poll single operation
        ops_to_poll = [{
            "operation": {"name": op_name},
            "sceneId": scene_id,
            "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
        }]
        
        # Proactive token refresh — token may have expired since original generation
        fresh_token = None
        if account.session.is_token_expired:
            log.info(f"[ReDownload] Access token expired for {account.email}, refreshing...")
            fresh_token = await account.refresh_access_token()
            if not fresh_token:
                log.error(f"[ReDownload] Token refresh failed for {account.email}")
                self._dispatcher.update_progress(
                    task.id, 100, f"⚠️ Re-download failed: auth expired, please re-login"
                )
                return False
        
        # Resolve access token: prefer fresh_token from refresh, fallback to session
        access_token = fresh_token or account.get_access_token()
        
        # Guard: force refresh if token is still empty (e.g. empty token from profile sync)
        if not access_token:
            log.warning(f"[ReDownload] access_token empty for {account.email}, forcing refresh...")
            access_token = await account.refresh_access_token()
            if not access_token:
                log.error(f"[ReDownload] Token refresh failed for {account.email}")
                self._dispatcher.update_progress(
                    task.id, 100, f"⚠️ Re-download failed: auth expired, please re-login"
                )
                return False
        
        sem = self._get_api_semaphore(account.email)
        async with sem:
            response = await self._api_client.check_status(
                access_token=access_token,
                recaptcha_token="",
                operations=ops_to_poll,
                account_headers=account.get_api_headers(),
            )
        
        if not response.success:
            log.error(f"Re-download single {task_id}[{video_index}]: poll failed — {response.error}")
            self._dispatcher.update_progress(
                task.id, 100, f"⚠️ Re-download video {video_index + 1} failed: {response.error}"
            )
            return False
        
        # Extract fifeUrl from response
        details = self._extract_output_details(response.data)
        if not details:
            log.warning(f"Re-download single {task_id}[{video_index}]: no fifeUrl in response")
            self._dispatcher.update_progress(
                task.id, 100, f"⚠️ Re-download video {video_index + 1}: no URL in response"
            )
            return False
        
        # Use the first URL from the polled operation
        fife_url = details[0]["fifeUrl"]
        log.info(f"Re-download single {task_id}[{video_index}]: got fresh fifeUrl — downloading 720p")
        
        self._dispatcher.update_progress(
            task.id, 70, f"⬇️ Re-downloading video {video_index + 1} (720p)..."
        )
        
        # Download single file — overwrite existing broken file
        existing_path = vo.file_720p if vo.file_720p else None
        local_paths = await self._download_outputs(
            task, [fife_url],
            quality_subfolder="720p",
            generate_thumbnails=True,
            overwrite_paths=[existing_path],
        )
        
        if not local_paths or not local_paths[0]:
            log.error(f"Re-download single {task_id}[{video_index}]: download failed")
            self._dispatcher.update_progress(
                task.id, 100, f"⚠️ Re-download video {video_index + 1} failed"
            )
            return False
        
        # Update the specific video output
        vo.file_720p = local_paths[0]
        if not vo.file_upscaled:
            vo.quality = "720p"
        
        # Rebuild output_uris
        final_paths = []
        for v in task.video_outputs:
            if v.file_upscaled:
                final_paths.append(v.file_upscaled)
            elif v.file_720p:
                final_paths.append(v.file_720p)
        if final_paths:
            task.output_uris = final_paths
        
        # Rebuild upscale media ID from response if available
        media_id = details[0].get("mediaId", "")
        if media_id and video_index < len(task.upscale_media_ids):
            task.upscale_media_ids[video_index] = media_id
        elif media_id and not task.upscale_media_ids:
            # Initialize list with empty strings, fill this one
            task.upscale_media_ids = [""] * len(task.video_outputs)
            task.upscale_media_ids[video_index] = media_id
        
        self._dispatcher.update_progress(
            task.id, 100, f"✅ Re-downloaded video {video_index + 1} (720p)"
        )
        
        if self._on_task_completed:
            self._on_task_completed(task)
        self._save_manifest(task)
        
        log.info(f"Re-download single {task_id}[{video_index}]: done — {local_paths[0]}")
        return True
    
    def _sync_overall_upscale_status(self, task: Task):
        """Sync per-video statuses → task-level upscale_status (backward compat)."""
        if not task.video_outputs:
            return
        statuses = [vo.upscale_status for vo in task.video_outputs]
        if all(s == "success" for s in statuses):
            task.upscale_status = "success"
            task.upscale_error = ""
        elif any(s == "failed" for s in statuses):
            task.upscale_status = "failed"
            failed_vo = next(vo for vo in task.video_outputs if vo.upscale_status == "failed")
            task.upscale_error = f"Video {failed_vo.index + 1}: {failed_vo.upscale_error}"
        elif all(s in ("", "skipped") for s in statuses):
            task.upscale_status = ""
        else:
            task.upscale_status = "success"  # mix of success + skipped
    
    async def _download_outputs(
        self, task: Task, output_uris: list,
        quality_subfolder: str = "",
        generate_thumbnails: bool = True,
        overwrite_paths: list = None,
    ) -> list:
        """Download output URIs to output_folder/project_name/quality_subfolder/.
        
        Bug 4 fix: Per-task lock prevents concurrent duplicate downloads
        when multiple poll workers detect SUCCESSFUL simultaneously.
        """
        # Bug 4: Acquire per-task download lock — serialize concurrent downloads
        task_id = str(task.id)
        if task_id not in self._download_locks:
            self._download_locks[task_id] = asyncio.Lock()
        
        if self._download_locks[task_id].locked():
            log.info(f"[Download] Task {task_id}: download already in progress, waiting...")
        
        async with self._download_locks[task_id]:
            return await self._download_outputs_inner(
                task, output_uris, quality_subfolder,
                generate_thumbnails, overwrite_paths
            )
    
    async def _download_outputs_inner(
        self, task: Task, output_uris: list,
        quality_subfolder: str = "",
        generate_thumbnails: bool = True,
        overwrite_paths: list = None,
    ) -> list:
        """Actual download implementation (called under per-task lock)."""
        from config.settings import get_settings
        settings = get_settings()
        
        # Prefer task-level output_folder (from sidebar), fallback to global settings
        output_folder = getattr(task, 'output_folder', '') or settings.output_folder
        if not output_folder:
            log.debug("No output_folder configured, skipping download")
            return []
        
        # Create project subfolder + quality subfolder
        project_name = getattr(task, 'project_name', '') or "Untitled"
        if quality_subfolder:
            output_path = Path(output_folder) / project_name / quality_subfolder
        else:
            output_path = Path(output_folder) / project_name
        output_path.mkdir(parents=True, exist_ok=True)
        
        local_paths = []
        import aiohttp
        from datetime import datetime
        
        # Global prompt index (1-based, 3-digit padded)
        prompt_num = getattr(task, 'prompt_index', 0) + 1
        idx_str = str(prompt_num).zfill(3)
        
        # Variant suffixes for multi-output
        variant_letters = "abcdefghijklmnopqrstuvwxyz"
        is_multi = len(output_uris) > 1
        
        # Bug 4A: Timeout prevents infinite hang on unresponsive FIFE server
        dl_timeout = aiohttp.ClientTimeout(total=120, sock_read=60)
        async with aiohttp.ClientSession(timeout=dl_timeout) as session:
            for i, uri in enumerate(output_uris):
                try:
                    # Use overwrite path if provided, else generate new filename
                    if overwrite_paths and i < len(overwrite_paths) and overwrite_paths[i]:
                        filepath = Path(overwrite_paths[i])
                        # Ensure parent dir exists
                        filepath.parent.mkdir(parents=True, exist_ok=True)
                        # Delete old broken/incomplete file before re-download
                        if filepath.exists():
                            filepath.unlink()
                            log.info(f"[Download] Removed old file for overwrite: {filepath.name}")
                    else:
                        # Build filename parts
                        parts = []
                        
                        # Index + variant suffix
                        if is_multi and i < len(variant_letters):
                            parts.append(f"{idx_str}{variant_letters[i]}")
                        else:
                            parts.append(idx_str)
                        
                        if settings.include_timestamp:
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            parts.append(ts)
                        
                        if settings.include_quality:
                            # Use actual quality (subfolder name), not target quality
                            file_quality = quality_subfolder or task.download_quality
                            parts.append(file_quality)
                        
                        if settings.include_model:
                            model_short = task.model.replace("veo_3_1_", "v31_").replace("_fast_", "_")
                            parts.append(model_short)
                        
                        sep = settings.separator
                        # Detect file type from task workflow
                        wf = getattr(task, 'workflow_type', '') or ''
                        is_image_task = wf.upper() in ('T2I', 'I2I', 'TEXT_TO_IMAGE', 'IMAGE_TO_IMAGE')
                        file_ext = '.png' if is_image_task else '.mp4'
                        filename = sep.join(parts) + file_ext
                        filepath = output_path / filename
                        
                        # Avoid overwrite — add numeric suffix if exists
                        counter = 1
                        while filepath.exists():
                            filepath = output_path / f"{sep.join(parts)}_{counter}{file_ext}"
                            counter += 1
                    
                    # Download with retry for suspiciously small files
                    # Google FIFE can serve HTTP 200 with black/incomplete MP4
                    # when video encoding hasn't finished server-side.
                    # Use exponential backoff up to ~120s total wait.
                    MIN_VIDEO_SIZE = 500_000    # 500 KB - normal 720p is 2-4 MB
                    MIN_IMAGE_SIZE = 50_000     # 50 KB
                    MAX_DOWNLOAD_RETRIES = 8
                    RETRY_DELAYS = [3, 5, 8, 12, 15, 20, 25, 30]  # total ~118s
                    
                    is_video = filepath.suffix.lower() in ('.mp4', '.webm', '.mov')
                    min_size = MIN_VIDEO_SIZE if is_video else MIN_IMAGE_SIZE
                    
                    downloaded_ok = False
                    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
                        delay = RETRY_DELAYS[attempt - 1] if attempt <= len(RETRY_DELAYS) else RETRY_DELAYS[-1]
                        
                        # Check Content-Length header first (if available)
                        async with session.get(uri) as resp:
                            if resp.status != 200:
                                # Retry on transient HTTP errors (403=URL expired, 5xx=server)
                                if resp.status in (403, 500, 502, 503) and attempt < MAX_DOWNLOAD_RETRIES:
                                    log.warning(
                                        f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}: "
                                        f"HTTP {resp.status} for {uri[:60]}... "
                                        f"Retrying in {delay}s..."
                                    )
                                    await asyncio.sleep(delay)
                                    continue
                                log.error(f"Download failed: HTTP {resp.status} for {uri[:80]}")
                                break
                            
                            content_length = resp.headers.get('Content-Length')
                            if content_length and int(content_length) < min_size and attempt < MAX_DOWNLOAD_RETRIES:
                                log.warning(
                                    f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}: "
                                    f"Content-Length {content_length} too small (min={min_size}), "
                                    f"server may still be encoding. Retrying in {delay}s..."
                                )
                                await asyncio.sleep(delay)
                                continue
                            
                            # Download the content
                            with open(filepath, "wb") as f:
                                async for chunk in resp.content.iter_chunked(8192):
                                    f.write(chunk)
                        
                        # Validate downloaded file size
                        file_size = filepath.stat().st_size
                        if file_size < min_size and attempt < MAX_DOWNLOAD_RETRIES:
                            log.warning(
                                f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}: "
                                f"{filepath.name} is only {file_size:,} bytes (min={min_size:,}), "
                                f"server encoding not ready. Retrying in {delay}s..."
                            )
                            await asyncio.sleep(delay)
                            continue
                        
                        if file_size < min_size:
                            # All retries exhausted, file is still black/incomplete
                            # DELETE the black file — don't save garbage
                            try:
                                filepath.unlink()
                                log.warning(
                                    f"🗑️ Deleted black/incomplete file {filepath.name}: "
                                    f"{file_size:,} bytes (below {min_size:,} threshold "
                                    f"after {MAX_DOWNLOAD_RETRIES} attempts, ~{sum(RETRY_DELAYS)}s total wait)"
                                )
                            except OSError as del_err:
                                log.error(f"Failed to delete black file {filepath.name}: {del_err}")
                            # downloaded_ok stays False → skip thumbnail, add "" to local_paths
                            break
                        
                        # Phase 2A: Verify content-length vs actual bytes written
                        if content_length:
                            expected = int(content_length)
                            if expected > 0 and file_size != expected and attempt < MAX_DOWNLOAD_RETRIES:
                                log.warning(
                                    f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}: "
                                    f"size mismatch {file_size:,} vs expected {expected:,} bytes "
                                    f"(truncated download). Retrying in {delay}s..."
                                )
                                await asyncio.sleep(delay)
                                continue
                        
                        downloaded_ok = True
                        break
                    
                    if downloaded_ok:
                        local_paths.append(str(filepath))
                        log.info(f"Downloaded: {filepath.name} → {output_path}")
                        
                        # Update per-video file_720p (base quality slot)
                        if i < len(task.video_outputs):
                            task.video_outputs[i].file_720p = str(filepath)
                            if task.video_outputs[i].quality == "pending":
                                # Use image-appropriate quality label for T2I/I2I
                                wf_type = getattr(task, 'workflow_type', '') or ''
                                is_img_task = wf_type.upper() in ('T2I', 'I2I', 'TEXT_TO_IMAGE', 'IMAGE_TO_IMAGE')
                                task.video_outputs[i].quality = "1K" if is_img_task else "720p"
                        
                        # Generate thumbnail (first frame for video, resize for image)
                        if generate_thumbnails:
                            try:
                                thumb_dir = Path.home() / ".veoauto" / "cache" / "thumbnails"
                                thumb_dir.mkdir(parents=True, exist_ok=True)
                                thumb_path = thumb_dir / f"{task.id}_{i}.jpg"
                                
                                # Detect if this is an image or video
                                wf = getattr(task, 'workflow_type', '') or ''
                                is_image = wf.upper() in ('T2I', 'I2I', 'TEXT_TO_IMAGE', 'IMAGE_TO_IMAGE') \
                                           or filepath.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
                                
                                if is_image:
                                    # Image: resize using PIL (no ffmpeg needed)
                                    from PIL import Image
                                    with Image.open(str(filepath)) as img:
                                        # Resize to 80px width, maintain aspect ratio
                                        ratio = 80 / img.width
                                        new_size = (80, max(1, int(img.height * ratio)))
                                        thumb_img = img.resize(new_size, Image.LANCZOS)
                                        # Convert RGBA → RGB for JPEG
                                        if thumb_img.mode in ('RGBA', 'P'):
                                            thumb_img = thumb_img.convert('RGB')
                                        thumb_img.save(str(thumb_path), 'JPEG', quality=85)
                                    log.info(f"Thumbnail (image): {thumb_path.name}")
                                else:
                                    # Video: extract first frame using ffmpeg
                                    import subprocess
                                    subprocess.run(
                                        ['ffmpeg', '-y', '-ss', '1', '-i', str(filepath),
                                         '-vframes', '1', '-vf', 'scale=80:-1', '-q:v', '5',
                                         str(thumb_path)],
                                        capture_output=True, timeout=10
                                    )
                                    if thumb_path.exists():
                                        log.info(f"Thumbnail (video): {thumb_path.name}")
                                
                                if thumb_path.exists():
                                    task.thumbnail_paths.append(str(thumb_path))
                                    # Update per-video thumbnail
                                    if i < len(task.video_outputs):
                                        task.video_outputs[i].thumbnail_path = str(thumb_path)
                            except Exception as te:
                                log.warning(f"Thumbnail gen failed: {te}")
                    else:
                        # ★ FIX: Preserve index alignment — add empty string for failed downloads
                        # so local_paths[i] always maps to video_outputs[i]
                        local_paths.append("")
                        log.warning(
                            f"⚠️ Download FAILED for video {i+1}/{len(output_uris)} "
                            f"(uri={uri[:60]}...) — slot kept empty for alignment"
                        )
                        
                except Exception as e:
                    log.error(f"Download error: {e}")
                    # ★ FIX: Also preserve alignment on exceptions
                    local_paths.append("")
        
        # Log download summary
        success_count = sum(1 for p in local_paths if p)
        if success_count < len(output_uris):
            log.warning(
                f"⚠️ Download partial: {success_count}/{len(output_uris)} videos downloaded. "
                f"Missing indices: {[i for i, p in enumerate(local_paths) if not p]}"
            )
        
        return local_paths
    
    # ── Manifest & Thumbnail Helpers ─────────────────────────────
    
    def _save_manifest(self, task: Task):
        """Save/update project manifest alongside output videos.
        
        Non-blocking, fire-and-forget — manifest is a bonus, not critical path.
        """
        try:
            self._manifest.save_task_to_manifest(task)
        except Exception as e:
            log.debug(f"[Manifest] Save skipped: {e}")
    
    def _regenerate_thumbnail(self, task: Task, video_index: int) -> str:
        """Auto-regenerate missing thumbnail from video/image file.
        
        Called when UI requests a thumbnail that no longer exists on disk.
        Supports both video (ffmpeg) and image (PIL) source files.
        
        Returns:
            Path to the regenerated thumbnail, or "" if failed.
        """
        if video_index >= len(task.video_outputs):
            return ""
        
        vo = task.video_outputs[video_index]
        source = vo.file_upscaled or vo.file_720p
        if not source or not Path(source).exists():
            return ""
        
        try:
            thumb_dir = Path.home() / ".veoauto" / "cache" / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = thumb_dir / f"{task.id}_{video_index}.jpg"
            
            source_ext = Path(source).suffix.lower()
            is_image = source_ext in ('.png', '.jpg', '.jpeg', '.webp')
            
            if is_image:
                # Image: resize using PIL
                from PIL import Image
                with Image.open(source) as img:
                    ratio = 80 / img.width
                    new_size = (80, max(1, int(img.height * ratio)))
                    thumb_img = img.resize(new_size, Image.LANCZOS)
                    if thumb_img.mode in ('RGBA', 'P'):
                        thumb_img = thumb_img.convert('RGB')
                    thumb_img.save(str(thumb_path), 'JPEG', quality=85)
            else:
                # Video: extract first frame using ffmpeg
                import subprocess
                subprocess.run(
                    ['ffmpeg', '-y', '-i', str(source),
                     '-vframes', '1', '-vf', 'scale=80:-1', '-q:v', '5',
                     str(thumb_path)],
                    capture_output=True, timeout=10,
                )
            
            if thumb_path.exists():
                vo.thumbnail_path = str(thumb_path)
                # Update task-level list too
                while len(task.thumbnail_paths) <= video_index:
                    task.thumbnail_paths.append("")
                task.thumbnail_paths[video_index] = str(thumb_path)
                log.info(f"[Thumbnail] Regenerated: {thumb_path.name}")
                return str(thumb_path)
        except Exception as e:
            log.warning(f"[Thumbnail] Regen failed: {e}")
        
        return ""
    
    def _is_auth_error(self, error_msg: str) -> bool:
        """Check if error indicates authentication failure.
        
        Only matches REAL auth errors that can be fixed by re-login:
        - HTTP 401 / UNAUTHENTICATED
        - Token expired/invalid
        
        Does NOT match:
        - HTTP 403 reCAPTCHA failures (re-login won't fix these)
        - Generic 403 permission errors
        """
        if not error_msg:
            return False
        lower = error_msg.lower()
        
        # Exclude reCAPTCHA errors — re-login won't help
        if "recaptcha" in lower:
            return False
        
        auth_keywords = [
            "401", "unauthorized", "unauthenticated",
            "token expired", "token invalid", "invalid credentials",
            "session expired", "authentication failed",
            "credentials_missing",
        ]
        return any(kw in lower for kw in auth_keywords)
    
    def _is_transient_error(self, error_msg: str) -> bool:
        """Check if error is transient and may resolve with time.
        
        reCAPTCHA failures, rate limits, network issues, timeouts —
        these may succeed if retried after a cooldown.
        """
        if not error_msg:
            return False
        lower = error_msg.lower()
        transient_keywords = [
            "recaptcha", "403", "429", "rate limit",
            "timeout", "timed out", "network", "connection",
            "temporarily", "unavailable", "overloaded",
            "token too short", "captcha",
        ]
        return any(kw in lower for kw in transient_keywords)
    
    CHAIN_MAX_AUTO_RETRIES = 8  # Max auto-retries for chain roots (transient errors only)
    
    def _should_auto_retry_chain(self, task: 'Task', error_msg: str) -> bool:
        """Decide if a chain root task should auto-retry.
        
        Conditions:
        1. Error is transient (reCAPTCHA, 403, timeout, network)
        2. Task is a chain root (has children, or had children)
        3. Haven't exceeded CHAIN_MAX_AUTO_RETRIES
        4. NOT an auth error (those require manual re-login)
        """
        if self._is_auth_error(error_msg):
            return False
        if not self._is_transient_error(error_msg):
            return False
        if task.chain_retry_count >= self.CHAIN_MAX_AUTO_RETRIES:
            return False
        
        # Check if task is a chain root (has or had descendants)
        descendants = self._dispatcher.collect_chain_descendants(task.id)
        if not descendants:
            # Also check: task might be a chain root whose children were
            # cascade-failed (parent_to_children already popped)
            # In that case, check if any task in _all_tasks references this as parent
            for t in self._dispatcher.get_all_tasks_dict().values():
                if t.parent_task_id == task.id:
                    return True
            return False
        return True
    
    def _is_network_error(self, error_msg: str) -> bool:
        """Check if error indicates a network connectivity failure.
        
        Layer 1 (Reactive): catches connection errors at the point of API call,
        triggers instant pause before other workers send more requests.
        """
        if not error_msg:
            return False
        lower = error_msg.lower()
        network_keywords = [
            "connectionerror", "connection refused", "connection reset",
            "network unreachable", "name resolution", "dns",
            "no route to host", "socket", "errno 11001",
            "getaddrinfo failed", "remotedisconnected",
            "connectionreseterror", "oserror", "ssl: unexpected eof",
        ]
        return any(kw in lower for kw in network_keywords)
    
    
    def set_callbacks(
        self,
        on_started: Optional[Callable] = None,
        on_completed: Optional[Callable] = None,
        on_failed: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
    ):
        """Set UI callbacks."""
        self._on_task_started = on_started
        self._on_task_completed = on_completed
        self._on_task_failed = on_failed
        self._on_progress = on_progress
    
    def get_status(self) -> dict:
        """Get engine status summary."""
        return {
            "running": self._running,
            "workers": [w.get_status() for w in self._workers],
            "accounts": self._account_manager.get_status_summary(),
            "queue": self._dispatcher.get_status_summary(),
        }
