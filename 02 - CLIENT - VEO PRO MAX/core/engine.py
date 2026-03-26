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
import collections
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
from core.error_classifier import classify_error, ERROR_CREDIT_COST, ErrorType

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
            # Trigger header refresh + quick xcd poll (gate handles full validation per-task)
            bridge = getattr(self.account, 'extension_bridge', None)
            if bridge and bridge.is_connected(self.account.email):
                log.info(f"[Supervisor:{self.email}] Refreshing browser headers...")
                try:
                    await bridge.refresh_headers_lightweight(self.account.email, timeout=10.0)
                except Exception:
                    pass
                # Quick poll — up to 15s for xcd to appear
                import time as _time
                from config.constants import MIN_VALID_XCD
                _start = _time.monotonic()
                while _time.monotonic() - _start < 15.0:
                    hdrs = self.account.get_browser_headers() if hasattr(self.account, 'get_browser_headers') else {}
                    if len((hdrs.get('x-client-data', '') or '')) >= MIN_VALID_XCD:
                        log.info(f"[Supervisor:{self.email}] ✅ x-client-data ready ({len(hdrs.get('x-client-data',''))} chars)")
                        break
                    await asyncio.sleep(1.0)
            
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
            
            await self.engine._pre_upload_all_images(self.account)
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
        1. Try to reuse existing project (TRPC or Extension bridge)
        2. Create new project (TRPC or Extension bridge)
        3. Retry once on failure
        """
        account = self.account
        email = self.email
        
        # Create project if not exists
        if not account.project_id:
            trpc_client = None
            if account._browser_session and account._browser_session.is_ready:
                trpc_client = TRPCClient(account._browser_session._page)
            
            # Extension bridge fallback for extension-only accounts
            bridge = getattr(account, 'extension_bridge', None)
            use_bridge = (
                not trpc_client and bridge
                and bridge.is_connected(email)
            )
            
            project_id = None
            
            # NOTE: project.getProjects endpoint was REMOVED from the API.
            # Per HAR reference, only project.getProject (singular, requires projectId)
            # and project.createProject exist now. Skip directly to create.
            
            # Step 2: Create new project if no existing one
            if not project_id:
                for attempt in range(2):
                    try:
                        if trpc_client:
                            project_id = await account.project_manager.get_or_create_project(
                                email=email,
                                access_token=account.get_access_token(),
                                api_client=self.engine._api_client,
                                trpc_client=trpc_client,
                                title="My Video Project",
                            )
                        elif use_bridge:
                            # Extension bridge path: create project via TRPC relay
                            result = await bridge.relay_fetch(
                                email=email,
                                url="https://labs.google/fx/api/trpc/project.createProject",
                                method="POST",
                                body={
                                    "json": {
                                        "projectTitle": "My Video Project",
                                        "toolName": "PINHOLE",
                                    }
                                },
                                headers={"Content-Type": "application/json"},
                                timeout=10.0,
                            )
                            if result and result.get("success") and result.get("data"):
                                data = result["data"]
                                project_id = (
                                    data.get("result", {})
                                    .get("data", {})
                                    .get("json", {})
                                    .get("result", {})
                                    .get("projectId")
                                )
                                if project_id:
                                    # Cache in ProjectManager
                                    account.project_manager._project_cache[
                                        f"{email}|My Video Project"
                                    ] = project_id
                        
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
        
        # Project ready — tab stays on main flow page.
        # submit_prompt uses executeScript with absolute API URLs,
        # so page URL is irrelevant (reCAPTCHA + fetch work from any VEO page).


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
                await engine._wait_for_recaptcha_ready(account, max_wait=30.0)
            elif count <= 2:
                if account.extension_bridge:
                    try:
                        await account.extension_bridge._trigger_refresh(
                            self.email, "Supervisor Phase 0", level="full"
                        )
                    except Exception:
                        pass
                if await engine._interruptible_sleep(15): return  # Stop-aware
                await engine._wait_for_recaptcha_ready(account, max_wait=30.0)
        
        elif phase == 1:
            # Soft recovery
            if count <= 2:
                await engine._do_browser_recovery(account, "supervisor", "soft")
                if await engine._interruptible_sleep(8): return  # Stop-aware
                await engine._wait_for_recaptcha_ready(account, max_wait=20.0)
        
        elif phase == 2:
            # Extended soft recovery (NO browser kill — preserves in-flight tasks)
            log.warning(f"🔄 [Supervisor:{self.email}] Phase 2 → extended soft recovery (no kill)")
            await engine._do_browser_recovery(account, "supervisor", "soft")
            if await engine._interruptible_sleep(15): return  # Stop-aware
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
            if await engine._interruptible_sleep(20): return  # Stop-aware
        elif freeze_count <= 5:
            # Escalation 3-5: Soft browser recovery
            await engine._do_browser_recovery(account, "supervisor", "soft")
            if await engine._interruptible_sleep(10): return  # Stop-aware
        else:
            # Escalation 6+: Extended soft recovery (no kill — preserves in-flight tasks)
            log.warning(f"🔄 [Supervisor:{self.email}] Tab freeze #{freeze_count} → extended soft recovery")
            await engine._do_browser_recovery(account, "supervisor", "soft")
            if await engine._interruptible_sleep(20): return  # Stop-aware
        
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
            # ★ Fix 3: Check stop event each iteration
            if self.engine._stop_event.is_set() or not self._running:
                log.info(f"[Supervisor:{self.email}] reCAPTCHA gate interrupted by stop")
                return
            try:
                ready = await bridge.check_recaptcha_ready(self.email)
                if ready:
                    log.info(f"[Supervisor:{self.email}] ✅ reCAPTCHA gate OPEN")
                    return
                log.info(f"[Supervisor:{self.email}] ⏳ reCAPTCHA gate CLOSED (attempt {attempt+1})")
            except Exception as e:
                log.warning(f"[Supervisor:{self.email}] reCAPTCHA check error: {e}")
            if await self.engine._interruptible_sleep(3): return  # Stop-aware
        
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
        self._foreman_count: Dict[str, int] = {}  # email → current foreman count
        self._scale_pending = asyncio.Event()  # Signal to check if more foremen needed
        self._running = False
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()  # Set = running, Clear = paused
        self._pause_event.set()  # Start unpaused
        self._task_available = asyncio.Event()  # Bug 14: signal workers when new task arrives
        self._upscale_wake_event = asyncio.Event()  # T1: wake UpscaleQueue when last prompt completes
        
        # ★ CONTINUATION FIX: Register callback so foremen wake INSTANTLY
        # when _resolve_dependencies activates continuation children.
        # Without this, children stay READY until 2s polling timeout expires.
        def _wake_foremen_on_ready(task):
            self._task_available.set()
        dispatcher.set_on_task_ready(_wake_foremen_on_ready)
        self._workers_available: Dict[str, asyncio.Event] = {}  # T2: wake foremen when workers released
        self._browser_recovery_locks: Dict[str, asyncio.Lock] = {}   # Per-account browser recovery dedup
        self._browser_recovery_epoch: Dict[str, int] = {}             # Tracks recovery generation
        self._account_rate_locks: Dict[str, asyncio.Semaphore] = {}  # RC4: Semaphore(1) — serialize submit pipeline per account
        # ── RC2 fix: Per-account submit throttle ──
        # Anti-detect: minimum gap between submits on the SAME account.
        # Different accounts submit independently (no cross-account gate).
        # Google's rate limiting is per-account/per-cookie, not per-IP.
        self._per_account_submit_locks: Dict[str, asyncio.Lock] = {}
        self._per_account_last_submit_ts: Dict[str, float] = {}      # Fast models: timestamp tracking
        self._per_account_last_submit_ts_lp: Dict[str, float] = {}   # LP models: separate timestamp tracking
        self._GLOBAL_MIN_SUBMIT_GAP: float = 45.0  # LP models: 45s between submits (prevents 429 storms)
        self._GLOBAL_MIN_SUBMIT_GAP_FAST: float = 3.0  # Fast models: 3s gap (no 429 observed at high concurrency)
        self._GLOBAL_MIN_SUBMIT_GAP_T2I: float = 3.0  # T2I images are lighter — smaller gap OK
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
        
        # Fix B: Per-account lock for reCAPTCHA recovery serialization
        # Prevents N foremen from ALL doing the expensive recovery cycle simultaneously
        self._recaptcha_recovery_locks: Dict[str, asyncio.Lock] = {}
        
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
        self._on_account_error: Optional[Callable] = None  # RC4: (email, message) for UI status
        
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
            should_wait_fn=lambda: False,  # UpscaleQueue runs independently (no pause gate)
            # Fix C: CircuitBreaker gate — wait for circuit CLOSED before submit
            wait_for_circuit_fn=self._wait_for_circuit,
            # V6: Report upscale 403 to engine's circuit breaker
            record_circuit_403_fn=self.record_circuit_403,
            on_completed=lambda task: self._on_task_completed(task) if self._on_task_completed else None,
            profiles_controller=self._profiles_controller,
            extension_bridge=self._extension_bridge,
            wake_event=self._upscale_wake_event,  # T1: event-driven wake
            pre_submit_gate_fn=self._pre_submit_gate,  # Centralized xcd + reCAPTCHA gate
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
        # ★ T2I-specific burst controller — lower delays for image generation
        _ad_min_t2i = getattr(self._settings, 'anti_detect_delay_min_t2i', 1.5)
        _ad_max_t2i = getattr(self._settings, 'anti_detect_delay_max_t2i', 5.0)
        self._burst_controller_t2i = AdaptiveBurstController(
            min_delay=_ad_min_t2i,
            max_delay=_ad_max_t2i,
            initial_delay=(_ad_min_t2i + _ad_max_t2i) / 2,  # 3.25s
        )
        
        # Fix G6: Inject burst_controller into upscale queue for anti-detect delay
        self._upscale_queue._burst_controller = self._burst_controller
        
        # Fix #4: Inject reCAPTCHA health check for upscale failover
        def _uq_recaptcha_health(email: str) -> bool:
            bridge = self._extension_bridge
            if bridge:
                return bridge.is_recaptcha_healthy(email)
            return True
        self._upscale_queue._is_recaptcha_healthy_fn = _uq_recaptcha_health
        
        # Wire force-retry → cancel upscale queue jobs (prevent orphan corruption)
        self._dispatcher._on_cancel_upscale = self._upscale_queue.cancel_task_jobs
        
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
        
        # ★ T2I output concurrency cap: max 12 outputs active per account
        # Each account independently limits to 12 concurrent image outputs.
        # When an account's 12 slots are full, its T2I tasks queue at semaphore.acquire()
        self._t2i_output_semaphores: Dict[str, asyncio.Semaphore] = {}  # email → Semaphore(12)
        self._t2i_slot_locks: Dict[str, asyncio.Lock] = {}              # email → Lock
        self._t2i_active_outputs: Dict[str, int] = {}                   # email → count
        
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
        
        # ★ Sick account detection: account marked "sick" after repeated circuit trips
        # Sick accounts skip task dispatch — tasks requeue to healthy accounts
        self._sick_accounts: Dict[str, float] = {}           # email → time.time() when marked sick
        self._circuit_trip_count: Dict[str, int] = {}        # email → consecutive trip count (reset on close)
        
        # (workload_priority removed — upscale always delegates to UpscaleQueue)
        
        # Pre-warm: proactive reCAPTCHA soft recovery after idle period
        # Prevents 403 cascade by resetting reCAPTCHA context before first submit
        self._last_successful_submit: Dict[str, float] = {}  # email → timestamp
        self._prewarm_stats: Dict[str, dict] = {}  # email → {count, last_idle_secs, last_time}
        self._prewarm_locks: Dict[str, asyncio.Lock] = {}  # email → Lock (coordinate foremen)
        
        # Gemini AI: Prompt enhancement + policy fix
        from core.prompt_enhancer import PromptEnhancer
        from services.gemini_key_manager import GeminiKeyManager
        self._prompt_enhancer = PromptEnhancer()
        self._gemini_key_mgr = GeminiKeyManager()
        
        # Tab Keepalive tracking (read by get_dashboard_stats)
        self._keepalive_last_ping_count: int = 0
        self._keepalive_last_ping_time: float = 0.0
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()
    
    # ── Gemini AI: Prompt Enhancement + Policy Fix ──────────────
    
    async def _enhance_prompt(self, task, account) -> Optional[str]:
        """Auto-enhance prompt via Gemini API before VEO submit.
        
        Uses per-profile key with rotation fallback.
        Falls back to custom API key from Settings when no profile key.
        Returns enhanced prompt or None (original prompt used).
        """
        email = account.email
        api_key = self._gemini_key_mgr.get_key(email)
        if not api_key:
            api_key = self._gemini_key_mgr.get_rotation_key(email)
        if not api_key:
            # ★ Fallback to custom key from Settings (source="custom")
            # Without this, users who add keys ONLY in Settings → Custom Key
            # would never get enhance/fix prompt functionality.
            try:
                from services.ai_client_factory import get_ai_config
                cfg = get_ai_config()
                if cfg.get("api_key"):
                    api_key = cfg["api_key"]
                    log.debug(f"[Enhance] Using custom API key from Settings for {email}")
            except Exception:
                pass
        if not api_key:
            log.debug(f"[Enhance] No Gemini API key for {email} — skipping")
            return None
        
        try:
            # ★ Always output JSON format for auto enhance/fix
            _prompt = task.prompt or ""
            _fmt = "json"
            enhanced = await self._prompt_enhancer.enhance(
                prompt=_prompt,
                api_key=api_key,
                profile_email=email,
                output_format=_fmt,
            )
            if enhanced:
                log.info(
                    f"[Enhance] {email}: '{_prompt[:40]}...' "
                    f"→ '{enhanced[:40]}...'"
                )
            return enhanced
        except Exception as e:
            # Key invalid → try rotation
            if '429' in str(e) or '403' in str(e) or '401' in str(e):
                rotation_key = self._gemini_key_mgr.get_rotation_key(email)
                if rotation_key:
                    try:
                        return await self._prompt_enhancer.enhance(
                            prompt=task.prompt or "",
                            api_key=rotation_key,
                            profile_email=email,
                            output_format=_fmt,
                        )
                    except Exception:
                        pass
            log.warning(f"[Enhance] Failed for {email}: {e}")
            return None
    
    async def _fix_policy_prompt(
        self, task, error_msg: str, account, attempt: int = 1
    ) -> Optional[str]:
        """Auto-fix a policy-blocked prompt — 3-step escalation.
        
        Attempt 1: LOCAL sanitizer (instant, no API)
        Attempt 2: Gemini API fix_policy (paraphrase rewrite)
        Attempt 3: Gemini API regenerate (completely new prompt, keep characters)
        
        Returns fixed prompt or None.
        """
        email = account.email
        _prompt = task.prompt or ""
        # Store original prompt for attempt 3 reference
        if not hasattr(task, '_original_prompt'):
            task._original_prompt = _prompt
        
        log.info(f"[Fix] {email}: attempt {attempt}/3 — strategy: "
                 f"{'LOCAL' if attempt == 1 else 'API_FIX' if attempt == 2 else 'API_REGENERATE'}")
        
        # ══════════════════════════════════════════════════════════════
        # Attempt 1: LOCAL sanitizer only (instant, no API)
        # ══════════════════════════════════════════════════════════════
        if attempt == 1:
            try:
                from core.prompt_sanitizer import get_sanitizer
                sanitizer = get_sanitizer()
                if sanitizer.has_rules():
                    sanitized, changes = sanitizer.sanitize(_prompt)
                    if changes:
                        log.info(
                            f"[Fix] {email}: LOCAL fix applied ({len(changes)} changes) — "
                            f"'{_prompt[:40]}...' → '{sanitized[:40]}...'"
                        )
                        for c in changes:
                            log.info(f"[Fix]   {c}")
                        return sanitized
            except Exception as e:
                log.debug(f"[Fix] Local sanitizer error: {e}")
            
            # Local didn't match anything — still return None to proceed to attempt 2
            log.info(f"[Fix] {email}: LOCAL fix found no matches — will proceed to API fix")
            return None
        
        # ══════════════════════════════════════════════════════════════
        # Common: resolve API key (used by attempts 2 & 3)
        # ══════════════════════════════════════════════════════════════
        api_key = self._gemini_key_mgr.get_key(email)
        if not api_key:
            api_key = self._gemini_key_mgr.get_rotation_key(email)
        if not api_key:
            bridge = getattr(self, '_extension_bridge', None)
            if bridge and bridge.is_connected(email):
                try:
                    api_key = await self._gemini_key_mgr.auto_provision_via_extension(
                        email, bridge
                    )
                except Exception:
                    pass
        if not api_key:
            try:
                from services.ai_client_factory import get_ai_config
                cfg = get_ai_config()
                if cfg.get("api_key"):
                    api_key = cfg["api_key"]
            except Exception:
                pass
        if not api_key:
            log.warning(f"[Fix] No API key for {email} — cannot run attempt {attempt}")
            return None
        
        # ══════════════════════════════════════════════════════════════
        # Attempt 2: API fix_policy (paraphrase rewrite, 85-95% similar)
        # ══════════════════════════════════════════════════════════════
        if attempt == 2:
            try:
                _fmt = "json"
                fixed = await self._prompt_enhancer.fix_policy(
                    prompt=_prompt,
                    error_message=error_msg,
                    api_key=api_key,
                    profile_email=email,
                    output_format=_fmt,
                )
                if fixed:
                    log.info(
                        f"[Fix] {email}: API FIX applied — "
                        f"'{_prompt[:40]}...' → '{fixed[:40]}...'"
                    )
                return fixed
            except Exception as e:
                if '429' in str(e) or '403' in str(e) or '401' in str(e):
                    rotation_key = self._gemini_key_mgr.get_rotation_key(email)
                    if rotation_key:
                        try:
                            return await self._prompt_enhancer.fix_policy(
                                prompt=_prompt,
                                error_message=error_msg,
                                api_key=rotation_key,
                                profile_email=email,
                                output_format=_fmt,
                            )
                        except Exception:
                            pass
                log.warning(f"[Fix] API FIX failed for {email}: {e}")
                return None
        
        # ══════════════════════════════════════════════════════════════
        # Attempt 3: API regenerate (completely new prompt, keep characters)
        # ══════════════════════════════════════════════════════════════
        if attempt == 3:
            # Use the ORIGINAL prompt (before any fixes) as reference
            original = getattr(task, '_original_prompt', _prompt)
            try:
                _fmt = "json"
                regenerated = await self._prompt_enhancer.regenerate_prompt(
                    original_prompt=original,
                    error_message=error_msg,
                    api_key=api_key,
                    profile_email=email,
                    output_format=_fmt,
                )
                if regenerated:
                    log.info(
                        f"[Fix] {email}: API REGENERATE applied — "
                        f"completely new prompt '{regenerated[:40]}...'"
                    )
                return regenerated
            except Exception as e:
                if '429' in str(e) or '403' in str(e) or '401' in str(e):
                    rotation_key = self._gemini_key_mgr.get_rotation_key(email)
                    if rotation_key:
                        try:
                            return await self._prompt_enhancer.regenerate_prompt(
                                original_prompt=original,
                                error_message=error_msg,
                                api_key=rotation_key,
                                profile_email=email,
                                output_format=_fmt,
                            )
                        except Exception:
                            pass
                log.warning(f"[Fix] API REGENERATE failed for {email}: {e}")
                return None
        
        return None
    
    def _is_policy_error(self, error_msg: str) -> bool:
        """Check if error indicates a prompt policy violation."""
        return classify_error(error_msg) == ErrorType.POLICY_VIOLATION
    
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
        # RC4: Notify UI status bar
        if self._on_account_error:
            icon = "⏳" if "429" in reason else "⛔"
            self._on_account_error(email, f"{icon} {reason} ({delay}s)")
    
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
                # RC4: Update Queue Status with countdown for PRE-SUBMIT tasks only.
                # Tasks with operation_name are already submitted and polling/downloading
                # — they aren't blocked by cooldown and shouldn't show "⏳ Wait".
                cd_left = 0
                u = self._account_cooldowns.get(email)
                if u:
                    cd_left = max(0, (u - datetime.now()).total_seconds())
                if hasattr(self, '_dispatcher') and self._dispatcher:
                    for t in self._dispatcher.get_running_tasks_for_account(email):
                        if not t.operation_name and not t.operation_names:
                            self._dispatcher.update_progress(
                                t.id, t.progress,
                                f"⏳ Wait {int(cd_left)}s"
                            )
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
        # ★ Slow reset: decay 1 oldest 429 entry per success (gradual recovery)
        # Instead of clearing all 429 history on first success, we remove only
        # the oldest entry. This means 3 recent 429s need 3 successes to clear,
        # preventing the "success → reset → immediate 429" cycle.
        if hasattr(self, '_account_429_window'):
            window = self._account_429_window.get(email, [])
            if window:
                window.pop(0)  # Remove oldest entry
                if not window:
                    self._account_429_window.pop(email, None)
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
    
    # ── Progressive Timeout Tiers ──
    # Slow/unstable networks get escalating timeouts per retry attempt.
    # Fast networks still pass quickly via early-exit logic.
    _TIMEOUT_TIERS = [
        # Attempt 0 (first try) — normal network
        {'xcd_poll': 20.0, 'rc_wait': 25.0, 'bridge_timeout': 35.0,
         'rc_execute_ms': 15000, 'fetch_ms': 20000},
        # Attempt 1 (retry) — slow network tolerance
        {'xcd_poll': 30.0, 'rc_wait': 35.0, 'bridge_timeout': 45.0,
         'rc_execute_ms': 25000, 'fetch_ms': 30000},
        # Attempt 2+ (final retries) — maximum patience
        {'xcd_poll': 40.0, 'rc_wait': 45.0, 'bridge_timeout': 55.0,
         'rc_execute_ms': 35000, 'fetch_ms': 40000},
    ]
    
    @classmethod
    def _get_timeout_tier(cls, attempt: int = 0) -> dict:
        """Get timeout configuration for a given retry attempt.
        
        Delegates to config.constants.get_timeout_tier() — single source of truth.
        """
        from config.constants import get_timeout_tier
        return get_timeout_tier(attempt)
    
    async def _pre_submit_gate(self, account, task, attempt: int = 0) -> bool:
        """Centralized pre-submit gate. ALL modes, ALL attempts.
        
        THE SINGLE SOURCE OF TRUTH for xcd + reCAPTCHA readiness.
        Replaces old _wait_for_account_ready + scattered checks.
        
        ★ Progressive timeout escalation:
          attempt 0 → Tier 0 (xcd=20s, reCAPTCHA=25s — normal network)
          attempt 1 → Tier 1 (xcd=30s, reCAPTCHA=35s — slow network)
          attempt 2+ → Tier 2 (xcd=40s, reCAPTCHA=45s — maximum patience)
        
        Flow:
        1. Fast path: instant check via cached real-time data (0ms)
        2. Slow path (under per-account lock):
           a. Trigger page reload → extension captures fresh headers
           b. Poll xcd from 3 sources (AM → bridge → session) — tier-based timeout
           c. If fail → borrow from other accounts
           d. Post-borrow recovery poll — tier-based timeout
           e. Still fail → SOFT gate (warn + proceed)
        3. reCAPTCHA: HARD gate (block — no token = guaranteed failure)
        
        Returns True = OK to submit, False = should requeue task.
        """
        import time
        email = account.email
        bridge = getattr(account, 'extension_bridge', None)
        from config.constants import MIN_VALID_XCD, MIN_VALID_XCD_IMAGE, MIN_VALID_XCD_I2I
        
        # ── Get timeout tier based on attempt ──
        tier = self._get_timeout_tier(attempt)
        tier_idx = min(attempt, len(self._TIMEOUT_TIERS) - 1)
        xcd_poll_timeout = tier['xcd_poll']
        rc_wait_timeout = tier['rc_wait']
        
        if attempt > 0:
            log.info(
                f"[PreSubmitGate:{email}] ⏱️ Timeout Tier {tier_idx} "
                f"(attempt {attempt}) → xcd={xcd_poll_timeout:.0f}s, "
                f"reCAPTCHA={rc_wait_timeout:.0f}s"
            )
        
        # Skip gate during stop
        if self._stop_event.is_set():
            return False
        
        # ── Gate 1: x-client-data check ──
        # When Extension bridge is connected, submit uses page-context fetch()
        # where Chrome auto-adds the REAL x-client-data (72 chars).
        # The bridge cache only has 8-char stub (webRequest API limitation).
        # → Skip xcd gate for Extension-based submissions.
        _bridge_connected = bridge and bridge.is_connected(email)
        
        if _bridge_connected:
            # Extension submit path: Chrome auto-injects real xcd into fetch()
            # Log cached xcd for diagnostics only (doesn't affect actual submit)
            xcd_cached = ''
            if hasattr(account, 'get_browser_headers'):
                xcd_cached = (account.get_browser_headers().get('x-client-data', '') or '')
            if len(xcd_cached) < MIN_VALID_XCD:
                log.debug(
                    f"[PreSubmitGate:{email}] xcd cache={len(xcd_cached)} chars "
                    f"(OK — Extension fetch auto-injects real xcd)"
                )
        else:
            # Direct API path (no extension): must have valid cached xcd
            MIN_GOOD = MIN_VALID_XCD  # 40 — require full enrollment
            
            # ── Helper: read xcd from 3 sources ──
            def _get_xcd() -> str:
                """Read x-client-data: AM headers → bridge cache → session fallback."""
                # Path 1: AccountManager.get_browser_headers() (reads bridge cache)
                if hasattr(account, 'get_browser_headers'):
                    headers = account.get_browser_headers()
                    xcd = (headers.get('x-client-data', '') or '')
                    if len(xcd) >= MIN_GOOD:
                        return xcd
                else:
                    xcd = ''
                
                # Path 2: Direct bridge cache query
                b = getattr(account, '_extension_bridge', None) or bridge
                if b:
                    cached = b.get_cached_headers(email, max_age_seconds=120)
                    if cached:
                        xcd2 = (cached.get('x-client-data', '') or '')
                        if len(xcd2) >= MIN_GOOD:
                            return xcd2
                        if len(xcd2) > len(xcd):
                            xcd = xcd2
                
                # Path 3: Session fallback (debounced value)
                xcd3 = getattr(getattr(account, 'session', None), 'client_data', '') or ''
                return xcd3 if len(xcd3) > len(xcd) else xcd
            
            xcd = _get_xcd()
            if len(xcd) >= MIN_GOOD:
                pass  # xcd OK — fall through to reCAPTCHA check
            else:
                # xcd short — must wait
                log.info(
                    f"[PreSubmitGate:{email}] xcd={len(xcd)} chars (need ≥{MIN_GOOD}) "
                    f"— entering slow path to wait for valid x-client-data"
                )
                
                # ── Slow Path: active reload + monitor (under per-account lock) ──
                if not hasattr(self, '_gate_locks'):
                    self._gate_locks = {}
                if email not in self._gate_locks:
                    self._gate_locks[email] = asyncio.Lock()
                
                gate_lock = self._gate_locks[email]
                
                if gate_lock.locked():
                    log.debug(f"[PreSubmitGate:{email}] Another foreman in slow path — waiting")
                    async with gate_lock:
                        pass
                    xcd = _get_xcd()
                    if len(xcd) >= MIN_GOOD:
                        log.info(f"[PreSubmitGate:{email}] ✅ xcd={len(xcd)} chars (from peer)")
                    else:
                        log.warning(
                            f"[PreSubmitGate:{email}] ❌ xcd={len(xcd)} chars "
                            f"(need ≥{MIN_GOOD}) after peer wait — BLOCKING submit"
                        )
                        return False
                else:
                    async with gate_lock:
                        # Step 1: Trigger page reload for fresh headers
                        if bridge and bridge.is_connected(email):
                            log.info(
                                f"[PreSubmitGate:{email}] Triggering header refresh "
                                f"(task {task.id}, attempt {attempt})"
                            )
                            try:
                                await bridge.refresh_headers_lightweight(email, timeout=10.0)
                            except Exception as e:
                                log.debug(f"[PreSubmitGate:{email}] Refresh failed: {e}")
                        
                        # Step 2: Poll xcd — tier-based timeout
                        start = time.monotonic()
                        while time.monotonic() - start < xcd_poll_timeout:
                            if self._stop_event.is_set():
                                return False
                            xcd = _get_xcd()
                            if len(xcd) >= MIN_GOOD:
                                log.info(
                                    f"[PreSubmitGate:{email}] ✅ xcd={len(xcd)} chars "
                                    f"after {time.monotonic()-start:.1f}s"
                                )
                                break
                            await self._interruptible_sleep(1.0)
                        else:
                            # Step 3: Borrow from other accounts
                            log.warning(
                                f"[PreSubmitGate:{email}] ⚠️ xcd={len(_get_xcd())} chars "
                                f"after {xcd_poll_timeout:.0f}s (tier {tier_idx}) "
                                f"— trying borrow from other accounts..."
                            )
                            try:
                                self._account_manager.fix_short_client_data()
                                xcd = _get_xcd()
                                if len(xcd) >= MIN_GOOD:
                                    log.info(
                                        f"[PreSubmitGate:{email}] ✅ Borrowed xcd="
                                        f"{len(xcd)} chars from another account"
                                    )
                            except Exception as e:
                                log.debug(f"[PreSubmitGate:{email}] Borrow failed: {e}")
                            
                            # Step 4: Post-borrow recovery poll
                            if len(_get_xcd()) < MIN_GOOD:
                                start2 = time.monotonic()
                                while time.monotonic() - start2 < xcd_poll_timeout:
                                    if self._stop_event.is_set():
                                        return False
                                    xcd = _get_xcd()
                                    if len(xcd) >= MIN_GOOD:
                                        log.info(
                                            f"[PreSubmitGate:{email}] ✅ xcd recovered "
                                            f"{len(xcd)} chars after borrow+{time.monotonic()-start2:.1f}s"
                                        )
                                        break
                                    await self._interruptible_sleep(1.0)
                                else:
                                    xcd_len = len(_get_xcd())
                                    log.warning(
                                        f"[PreSubmitGate:{email}] ❌ xcd={xcd_len} chars "
                                        f"(need ≥{MIN_GOOD}) — BLOCKING submit (hard gate)"
                                    )
                                    return False
        
        # ── Gate 2: reCAPTCHA readiness (HARD — always required) ──
        if self._stop_event.is_set():
            return False
        
        rc_ok = await self._wait_for_recaptcha_ready(account, max_wait=rc_wait_timeout)
        if not rc_ok:
            log.warning(
                f"[PreSubmitGate:{email}] ❌ reCAPTCHA not ready "
                f"(tier {tier_idx}, waited {rc_wait_timeout:.0f}s) "
                f"— requeue task {task.id}"
            )
            return False
        
        log.info(f"[PreSubmitGate:{email}] ✅ Gate passed — submitting (tier {tier_idx})")
        return True
    
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
        1. Try to reuse existing project via get_projects() (TRPC or Extension bridge)
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
        
        # Extension bridge fallback for extension-only accounts
        bridge = getattr(account, 'extension_bridge', None)
        use_bridge = (
            not trpc_client and bridge
            and bridge.is_connected(email)
        )
        
        project_id = None
        
        # NOTE: project.getProjects endpoint was REMOVED from the API.
        # Per HAR reference, only project.getProject (singular, requires projectId)
        # and project.createProject exist. Skip directly to create.
        
        # Step 2: Create new with retry
        if not project_id:
            for attempt in range(2):
                # BUG-36: Skip project creation during stop
                if self._stop_event.is_set():
                    break
                try:
                    if trpc_client:
                        project_id = await account.project_manager.get_or_create_project(
                            email=email,
                            access_token=account.get_access_token(),
                            api_client=self._api_client,
                            trpc_client=trpc_client,
                            title=title,
                        )
                    elif use_bridge:
                        # Extension bridge path: create project via TRPC relay
                        result = await bridge.relay_fetch(
                            email=email,
                            url="https://labs.google/fx/api/trpc/project.createProject",
                            method="POST",
                            body={
                                "json": {
                                    "projectTitle": title,
                                    "toolName": "PINHOLE",
                                }
                            },
                            headers={"Content-Type": "application/json"},
                            timeout=10.0,
                        )
                        if result and result.get("success") and result.get("data"):
                            data = result["data"]
                            project_id = (
                                data.get("result", {})
                                .get("data", {})
                                .get("json", {})
                                .get("result", {})
                                .get("projectId")
                            )
                            if project_id:
                                # Cache in ProjectManager
                                account.project_manager._project_cache[
                                    f"{email}|{title}"
                                ] = project_id
                    
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
        
        Extension bridge fallback: If no browser page (extension-only mode),
        uses relay_fetch to call the same endpoint from the VEO tab.
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
                # Fallback: try via Extension bridge relay_fetch
                bridge = getattr(account, 'extension_bridge', None)
                if bridge and bridge.is_connected(email):
                    log.info(f"[Foreman:{email}] checkAppAvailability: trying via Extension bridge")
                    relay_result = await bridge.relay_fetch(
                        email=email,
                        url="https://aisandbox-pa.googleapis.com/v1:checkAppAvailability",
                        method="POST",
                        body={"clientContext": {"tool": "PINHOLE"}},
                        headers={
                            "Content-Type": "text/plain;charset=UTF-8",
                            "x-goog-api-key": "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY",
                        },
                        credentials="omit",  # cross-site → no credentials
                        timeout=10.0,
                    )
                    if relay_result and relay_result.get("success"):
                        data = relay_result.get("data", {})
                        state = data.get("availabilityState", "UNKNOWN") if isinstance(data, dict) else "UNKNOWN"
                        if state == "AVAILABLE":
                            log.info(f"[Foreman:{email}] ✅ checkAppAvailability via Extension: AVAILABLE")
                        else:
                            log.warning(f"[Foreman:{email}] checkAppAvailability via Extension: {data}")
                    else:
                        log.warning(f"[Foreman:{email}] checkAppAvailability via Extension failed")
                else:
                    log.warning(f"[Foreman:{email}] checkAppAvailability: no browser page available")
                return
            state = result.get('availabilityState', 'UNKNOWN') if isinstance(result, dict) else 'UNKNOWN'
            if state == 'AVAILABLE':
                log.info(f"[Foreman:{email}] ✅ checkAppAvailability: AVAILABLE")
            else:
                log.warning(f"[Foreman:{email}] checkAppAvailability: {result}")
        except Exception as e:
            log.warning(f"[Foreman:{email}] checkAppAvailability failed: {e}")

    # NOTE: _navigate_to_project_page() removed — submit_prompt uses
    # executeScript with absolute API URLs (project_id in payload body),
    # so page URL is irrelevant. Tab stays on main flow page, avoiding:
    # - 4-8s navigation blocking workers
    # - Cache stale bugs (_navigated_project)
    # - Race conditions between workers needing different projects
    
    CIRCUIT_TRIP_THRESHOLD = 5    # consecutive 403s to trip breaker
    CIRCUIT_MONITOR_INTERVAL = 10  # seconds between health checks
    SICK_TRIP_THRESHOLD = 3        # consecutive circuit trips → mark account "sick"
    
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
            # Count consecutive trips (only on fresh trip, not re-trip from half-open)
            trip_count = self._circuit_trip_count.get(email, 0) + 1
            self._circuit_trip_count[email] = trip_count
        else:
            trip_count = self._circuit_trip_count.get(email, 1)
        
        # Block all waiters
        evt = self._get_circuit_event(email)
        evt.clear()
        
        log.warning(
            f"⚡ [CircuitBreaker] {email}: OPEN — {reason}. "
            f"Trip #{trip_count}/{self.SICK_TRIP_THRESHOLD}. "
            f"All workers for this account will sleep until extension reconnects."
        )
        
        # DD4: Signal supervisor to abort foreman → tasks requeued
        supervisor = self._supervisors.get(email)
        if supervisor:
            supervisor.abort_foreman()
            log.info(f"[DD4] {email}: Foreman abort signal sent")
        
        # ★ Sick detection: N consecutive trips → mark account sick
        if trip_count >= self.SICK_TRIP_THRESHOLD and email not in self._sick_accounts:
            self._mark_account_sick(email)
    
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
        self._circuit_trip_count[email] = 0  # Reset trip counter on success
        
        # ★ Clear sick status if account was marked sick
        if email in self._sick_accounts:
            self._sick_accounts.pop(email, None)
            log.info(
                f"✅ [SickAccount] {email}: RECOVERED — "
                f"circuit closed, account available for dispatch again"
            )
        
        # Wake all waiters
        evt = self._get_circuit_event(email)
        evt.set()
        
        log.info(f"✅ [CircuitBreaker] {email}: CLOSED — extension healthy, workers resuming.")
        
        # ★ Reset AccountManager reCAPTCHA circuit-breaker too
        # Without this, stale _recaptcha_consecutive_failures (up to 8)
        # causes 120s backoff in refresh_recaptcha() even with healthy Chrome.
        account = next(
            (a for a in self._account_manager._accounts if a.email == email),
            None,
        )
        if account:
            old_rc_fails = getattr(account, '_recaptcha_consecutive_failures', 0)
            if old_rc_fails > 0:
                account._recaptcha_consecutive_failures = 0
                log.info(
                    f"✅ [CircuitBreaker] {email}: Reset reCAPTCHA "
                    f"consecutive failures {old_rc_fails} → 0"
                )
        
        # ★ Reset cooldown backoff — fresh Chrome should start from 30s, not 180s
        self.clear_account_cooldown(email)
        
        # ★ Reset recovery phase state machine — fresh Chrome = phase 0
        self._account_recovery_phase[email] = 0
        self._account_phase_403_count[email] = 0
        self._account_403_last_epoch[email] = -1
        
        # ★ Bug #2 fix: Immediate CreditWindow reactivation after CB close
        # Without this, CB closes → foremen resume → but can_accept_task()
        # returns False (still suspended) → foremen idle-poll for ~10 min
        # waiting for passive credit recovery. Since soft recovery already
        # proved the account is healthy, reactivate immediately.
        if self._credit_window and self._credit_window.is_suspended(email):
            self._credit_window.reactivate(email)
            cleared = self._dispatcher.clear_exclusion_for_account(email)
            log.info(
                f"✅ [CircuitBreaker] {email}: CreditWindow reactivated "
                f"immediately (bypassed passive recovery)"
                f"{f', un-excluded {cleared} task(s)' if cleared else ''}"
            )
        
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
    
    def is_account_sick(self, email: str) -> bool:
        """Check if account is marked sick (repeated circuit breaker trips).
        
        Sick accounts are excluded from task dispatch — foreman idles,
        and all running tasks have been requeued to healthy accounts.
        """
        return email in self._sick_accounts
    
    def _mark_account_sick(self, email: str):
        """Mark account as sick — requeue all running tasks to healthy accounts.
        
        Called when circuit breaker trips SICK_TRIP_THRESHOLD consecutive times
        without successful recovery. This means reCAPTCHA or extension is
        fundamentally broken for this account.
        
        Effects:
        1. Account added to _sick_accounts (foreman will idle)
        2. All RUNNING/WAITING_POLL tasks requeued (high priority, any account)
        3. ★ Auto-close browser + set 5-min cooldown to prevent infinite restart loops
        """
        import time as _time
        self._sick_accounts[email] = _time.time()
        
        # Requeue all running tasks from this account
        requeued = 0
        if self._dispatcher:
            from core.dispatcher import TaskState
            for task in list(self._dispatcher._all_tasks.values()):
                if (task.assigned_account == email and 
                        task.state in (TaskState.RUNNING, TaskState.WAITING_POLL)):
                    if self._dispatcher.requeue_task(task):
                        requeued += 1
        
        log.warning(
            f"🤒 [SickAccount] {email}: MARKED SICK — "
            f"{self._circuit_trip_count.get(email, 0)} consecutive circuit trips. "
            f"Requeued {requeued} task(s) to healthy accounts. "
            f"Account will idle until circuit breaker closes."
        )
        
        # ★ Fix 4b: Auto-close browser on persistent failures
        # Browser state is broken (reCAPTCHA cascade, zombie cleanup loop).
        # Close browser + set 5-min cooldown to prevent infinite restart loop.
        try:
            bridge = self._extension_bridge
            if bridge:
                bridge.set_browser_cooldown(email)
            
            # Close browser for this account
            for acc in self._account_manager._accounts:
                if acc.email == email:
                    asyncio.ensure_future(acc.close_browser())
                    log.warning(
                        f"[SickAccount] 🔒 Auto-closed browser for {email} "
                        f"— cooldown {bridge.BROWSER_CLOSE_COOLDOWN_SECONDS if bridge else 300}s"
                    )
                    break
        except Exception as e:
            log.error(f"[SickAccount] Auto-close error for {email}: {e}")
    
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
        
        Enhancement: When breaker trips due to 5+ consecutive 403s,
        triggers browser restart (clear auth, keep profile) to recover
        from reCAPTCHA failures.
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
                    consecutive = self._circuit_consecutive_403.get(email, 0)
                    
                    # ★ Soft recovery: 5+ consecutive 403s → soft recover (no browser kill)
                    if state == "open" and consecutive >= self.CIRCUIT_TRIP_THRESHOLD:
                        # Prevent re-trigger during recovery
                        if not getattr(self, '_circuit_restart_pending', {}).get(email):
                            if not hasattr(self, '_circuit_restart_pending'):
                                self._circuit_restart_pending = {}
                            self._circuit_restart_pending[email] = True
                            
                            log.warning(
                                f"🔄 [CircuitBreaker] {email}: {consecutive}× consecutive 403 "
                                f"→ soft recovery (no browser kill, preserving sessions)"
                            )
                            try:
                                ok = await account.soft_recover_browser()
                                if ok:
                                    log.info(
                                        f"✅ [CircuitBreaker] {email}: soft recovery OK "
                                        f"— resetting counter, closing breaker"
                                    )
                                    self._circuit_consecutive_403[email] = 0
                                    self._close_circuit_breaker(email)
                                else:
                                    log.warning(
                                        f"⚠️ [CircuitBreaker] {email}: soft recovery returned False "
                                        f"— keeping circuit open, will retry next cycle"
                                    )
                            except Exception as e:
                                log.error(
                                    f"❌ [CircuitBreaker] {email}: soft recovery error: {e}"
                                )
                            finally:
                                self._circuit_restart_pending[email] = False
                            continue  # Skip normal health check for this account
                    
                    if healthy and state == "open":
                        # Exponential backoff: wait longer before probing
                        # as consecutive 403 count increases
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
                    
                    # ★ reCAPTCHA health monitor: detect stuck widget on connected extension
                    # Scenario: extension alive & breaker closed, but reCAPTCHA generates
                    # garbage 538-char tokens → extension is "connected" but functionally dead.
                    if healthy and state == "closed":
                        bridge = getattr(account, 'extension_bridge', None) or self._extension_bridge
                        if bridge and not bridge.is_recaptcha_healthy(email):
                            if not hasattr(self, '_recaptcha_unhealthy_since'):
                                self._recaptcha_unhealthy_since = {}
                            
                            if email not in self._recaptcha_unhealthy_since:
                                self._recaptcha_unhealthy_since[email] = time.time()
                                log.warning(
                                    f"[CircuitBreaker] {email}: reCAPTCHA unhealthy detected "
                                    f"(consecutive failures={bridge.get_consecutive_recaptcha_failures(email)}) "
                                    f"— monitoring for 60s before intervention"
                                )
                            else:
                                unhealthy_duration = time.time() - self._recaptcha_unhealthy_since[email]
                                if unhealthy_duration >= 60:
                                    # Check cooldown: don't trigger more than once per 120s
                                    last_nav = getattr(self, '_last_hard_nav_time', {}).get(email, 0)
                                    if time.time() - last_nav >= 120:
                                        log.warning(
                                            f"🔄 [CircuitBreaker] {email}: reCAPTCHA unhealthy for "
                                            f"{unhealthy_duration:.0f}s — triggering hard navigation"
                                        )
                                        if not hasattr(self, '_last_hard_nav_time'):
                                            self._last_hard_nav_time = {}
                                        self._last_hard_nav_time[email] = time.time()
                                        try:
                                            nav_ok = await bridge.trigger_hard_navigation(email)
                                            if nav_ok:
                                                log.info(
                                                    f"✅ [CircuitBreaker] {email}: hard navigation sent, "
                                                    f"waiting 25s for reCAPTCHA widget..."
                                                )
                                                if await self._interruptible_sleep(25):
                                                    return  # Stop-aware
                                                self._recaptcha_unhealthy_since.pop(email, None)
                                        except Exception as e:
                                            log.error(
                                                f"❌ [CircuitBreaker] {email}: hard navigation error: {e}"
                                            )
                        else:
                            # reCAPTCHA healthy — clear tracker
                            if hasattr(self, '_recaptcha_unhealthy_since'):
                                self._recaptcha_unhealthy_since.pop(email, None)
                    
                    # ★ Fix 4d: Auto-restart browser after cooldown expires for sick accounts
                    # When _mark_account_sick auto-closes browser + sets 5-min cooldown,
                    # this section detects cooldown expiry and attempts browser restart.
                    if email in self._sick_accounts:
                        bridge = self._extension_bridge
                        if bridge and not bridge.is_browser_on_cooldown(email):
                            # Cooldown expired — try to restart browser
                            log.info(
                                f"[CircuitBreaker] {email}: cooldown expired "
                                f"— auto-restarting browser"
                            )
                            try:
                                ok = await self._do_browser_recovery(
                                    account, "circuit-monitor", "hard"
                                )
                                if ok:
                                    self._sick_accounts.pop(email, None)
                                    self._close_circuit_breaker(email)
                                    if bridge:
                                        bridge.clear_browser_cooldown(email)
                                    log.info(
                                        f"✅ [CircuitBreaker] {email}: browser restarted, "
                                        f"account recovered from sick state"
                                    )
                            except Exception as e:
                                log.error(
                                    f"[CircuitBreaker] {email}: auto-restart failed: {e}"
                                )
                                # Re-set cooldown to prevent rapid retry
                                if bridge:
                                    bridge.set_browser_cooldown(email)
                    
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
                        # Clear task exclusions so foreman can pick them up again
                        cleared = self._dispatcher.clear_exclusion_for_account(email)
                        # Reset circuit breaker state
                        self.record_circuit_success(email)
                        self.clear_account_cooldown(email)
                        self._account_recovery_phase[email] = 0
                        self._account_phase_403_count[email] = 0
                        log.info(
                            f"[CreditWindow] {email}: ✅ probe OK — "
                            f"reactivated with slow start"
                            f"{f', un-excluded {cleared} task(s)' if cleared else ''}"
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
        KEEPALIVE_INTERVAL_MIN = 18  # seconds — min cycle interval
        KEEPALIVE_INTERVAL_MAX = 30  # seconds — max (under Chrome 60s freeze)
        HEARTBEAT_EVERY_N_CYCLES = 5  # API heartbeat every 5th cycle
        
        log.info("[TabKeepalive] App-level service started (2-tier: JS + API heartbeat, randomized)")
        
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
                
                # Tier 1: Randomized simulate_activity per account
                # Random 1-3 pings per account, 2-5s between pings
                # Avoids deterministic pattern that Google can detect as automation
                import random
                pinged = 0
                for account in self._account_manager._accounts:
                    if not account.is_enabled:
                        continue
                    if stop_event.is_set() or not yield_event.is_set():
                        break  # Stop or engine just started
                    
                    bridge = getattr(account, 'extension_bridge', None)
                    if not bridge or not bridge.is_connected(account.email):
                        continue
                    
                    activity_count = random.randint(1, 3)
                    for i in range(activity_count):
                        if stop_event.is_set() or not yield_event.is_set():
                            break
                        try:
                            ok = await bridge.simulate_activity(
                                account.email, timeout=3.0
                            )
                            if ok:
                                pinged += 1
                        except Exception:
                            pass  # Best-effort
                        # Random pause between activity calls (skip after last)
                        if i < activity_count - 1:
                            await asyncio.sleep(random.uniform(2.0, 5.0))
                
                # Track stats for DevConsole dashboard
                self._keepalive_last_ping_count = pinged
                self._keepalive_last_ping_time = time.time()
                
                if pinged > 0:
                    log.debug(
                        f"[TabKeepalive] Pinged {pinged} tab(s) — "
                        f"Chrome freeze prevention OK"
                    )
                
                # ★ Fix 5 — Tier 2: API heartbeat every ~N cycles
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
            
            # Randomized sleep interval (18-30s, under Chrome's freeze threshold)
            cycle_interval = random.uniform(KEEPALIVE_INTERVAL_MIN, KEEPALIVE_INTERVAL_MAX)
            for _ in range(int(cycle_interval)):
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
            pass  # Deprecated: upscale always delegates to UpscaleQueue
        elif key == "prewarm_enabled":
            pass  # Read from settings at runtime
        elif key == "prewarm_idle_threshold":
            pass  # Stored in minutes, read at runtime
        else:
            return False
        return True
    
    # (should_upscale_wait removed — UpscaleQueue now runs independently)
    
    # ── Pre-warm: Proactive reCAPTCHA Recovery ──
    
    async def _maybe_prewarm(self, account) -> None:
        """Pre-warm reCAPTCHA if idle > threshold.
        
        Called before the first submit attempt after an idle period.
        Performs soft recovery (navigate away + back) to reset reCAPTCHA
        scoring context, preventing 403 cascade from stale sessions.
        
        BUG-36: Uses per-account lock so only ONE foreman runs prewarm.
        Other foremen wait for the lock, then re-check idle time and skip
        (because the first foreman already updated _last_successful_submit).
        
        Steps:
          1. Simulate activity (wake tab)
          2. Soft recovery (navigate about:blank → VEO → re-init reCAPTCHA)
          3. Wait for reCAPTCHA readiness
          4. Validate token (pre-fetch for first submit)
          5. Reset AdaptiveBurst delay
        """
        email = account.email
        
        # Check setting toggle
        if self._settings and not getattr(self._settings, 'prewarm_enabled', True):
            return
        
        # Threshold in minutes from settings, convert to seconds
        threshold_min = getattr(self._settings, 'prewarm_idle_threshold', 10) if self._settings else 10
        threshold_secs = threshold_min * 60
        
        # ── Quick check BEFORE lock (avoid lock contention if not needed) ──
        last = self._last_successful_submit.get(email, 0)
        idle_secs = time.time() - last if last else 0
        if idle_secs < threshold_secs:
            return  # Not idle enough
    
        # BUG-32: Skip prewarm during stop (soft recovery + reCAPTCHA = 20+s)
        if self._stop_event.is_set():
            return
        
        # ── BUG-36: Per-account lock — only 1 foreman runs prewarm ──
        if email not in self._prewarm_locks:
            self._prewarm_locks[email] = asyncio.Lock()
        lock = self._prewarm_locks[email]
        
        if lock.locked():
            # Another foreman is already doing prewarm — just wait for it
            log.info(f"[PreWarm] {email}: another foreman is warming up — waiting...")
            async with lock:
                # Lock released = prewarm done, _last_successful_submit updated
                log.info(f"[PreWarm] {email}: ✅ piggyback — warm-up done by another foreman")
                return
        
        async with lock:
            # ── Re-check idle after acquiring lock ──
            last = self._last_successful_submit.get(email, 0)
            idle_secs = time.time() - last if last else 0
            if idle_secs < threshold_secs:
                return  # Another foreman already prewarmed
            
            if self._stop_event.is_set():
                return
        
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
            # BUG-32: Check stop before expensive recovery
            if self._stop_event.is_set():
                return
            try:
                recovered = await account.soft_recover_browser()
            except Exception as e:
                log.warning(f"[PreWarm] {email}: soft recovery failed: {e}")
                recovered = False
            
            if recovered:
                # BUG-32: Check stop before reCAPTCHA wait
                if self._stop_event.is_set():
                    return
                # ── Step 3: Wait for reCAPTCHA readiness ──
                await self._wait_for_recaptcha_ready(account, max_wait=20.0)
                
                # ── Step 4: Validate token ──
                # BUG-32: Check stop before token validation
                if self._stop_event.is_set():
                    return
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
            
            # ★ Update timestamp INSIDE lock so waiting foremen see it
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
        
        BUG-01/02/03/07/11 fix: Cooperative stop.
        1. Signal all loops to exit (_stop_event)
        2. Unpause workers so they can exit (_pause_event.set)
        3. Stop UpscaleQueue
        4. Do NOT requeue tasks here — start()'s finally block does
           that AFTER all pipelines have actually finished.
        """
        if not self._running:
            return
        
        log.info("Engine stop requested — signaling workers to exit")
        self._stop_event.set()
        self._task_available.set()  # Wake up any waiting workers
        
        # BUG-09: Unpause so paused foremen/workers can exit their loops
        self._pause_event.set()
        
        # BUG-07: Stop UpscaleQueue (cancels its background tasks)
        if hasattr(self, '_upscale_queue') and self._upscale_queue:
            try:
                self._upscale_queue.stop()
                log.info("UpscaleQueue stopped")
            except Exception as e:
                log.warning(f"UpscaleQueue stop error: {e}")
        
        # NOTE: Do NOT requeue tasks or clear tracking here.
        # Pipelines (poll/download/upscale) may still be running.
        # start()'s finally block handles requeue + cleanup AFTER
        # the TaskGroup completes (all pipelines finished/cancelled).
        
        # RC4: Shutdown ProcessPoolExecutor — prevents SpawnProcess-1 hang
        # on call_queue.get() that blocks clean exit
        if hasattr(self, '_process_pool') and self._process_pool:
            try:
                self._process_pool.shutdown(wait=False, cancel_futures=True)
                log.info("ProcessPoolExecutor shut down")
            except Exception as e:
                log.warning(f"ProcessPoolExecutor shutdown error: {e}")
        
        log.info("Engine stop signal sent — waiting for pipelines to finish")
    
    def stop_account_workers(self, email: str):
        """Stop all workers (foremen + supervisor) for a specific account.
        
        Called during profile deletion (hot-remove) to cleanly shut down
        an account's workers without stopping the entire engine.
        
        Steps:
        1. Abort supervisor's foreman gate → foremen exit their loops
        2. Stop supervisor's running flag
        3. Remove workers from self._workers list
        4. Remove from self._active_account_emails
        5. Clean up supervisor reference
        6. Requeue orphaned tasks for other accounts to pick up
        """
        # Step 1: Abort supervisor → foremen exit
        supervisor = self._supervisors.get(email)
        if supervisor:
            supervisor.abort_foreman()   # Sets _foreman_abort event
            supervisor._running = False  # Stop supervisor loop
            log.info(f"[Engine] 🛑 Aborted supervisor for {email}")
        
        # Step 2: Remove workers (foremen) for this account from tracking
        email_prefix = f"foreman-{email[:8]}-"
        before = len(self._workers)
        self._workers = [
            w for w in self._workers
            if not w.worker_id.startswith(email_prefix)
        ]
        removed_count = before - len(self._workers)
        
        # Step 3: Remove from active emails
        self._active_account_emails.discard(email)
        
        # Step 4: Clean up supervisor reference
        self._supervisors.pop(email, None)
        
        # Step 5: Clean up per-account state
        self._smart_hide_rehide_countdown.pop(email, None)
        self._foreman_count.pop(email, None)  # Dynamic scaling tracker
        
        # Step 6: Requeue orphaned tasks assigned to this account
        # Tasks in RUNNING/WAITING_POLL state assigned to deleted account
        # need to be returned to the global queue for other accounts.
        requeued = 0
        try:
            from core.dispatcher import TaskState
            for task in self._dispatcher._tasks:
                if (task.assigned_account == email and 
                    task.state in (TaskState.RUNNING, TaskState.WAITING_POLL, TaskState.READY)):
                    # Clear account affinity so any account can pick it up
                    task.required_account = None
                    self._dispatcher.requeue_task(task)
                    requeued += 1
        except Exception as e:
            log.warning(f"[Engine] Task requeue error: {e}")
        
        # Wake up remaining foremen to pick up requeued tasks
        if requeued > 0:
            self._task_available.set()
        
        log.info(
            f"[Engine] ✅ Stopped account {email}: "
            f"removed {removed_count} foremen, requeued {requeued} tasks"
        )


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
        
        # RC4: Re-create ProcessPoolExecutor if it was shut down by stop()
        try:
            self._process_pool.submit(lambda: None)  # probe: is pool still alive?
        except (RuntimeError, BrokenPipeError):
            self._process_pool = ProcessPoolExecutor(
                max_workers=os.cpu_count() or 4
            )
        
        # Bug 14: Wire dispatcher's on_task_ready to wake up waiting workers
        # + Dynamic scaling: signal _scale_foremen_loop when new tasks arrive
        def _on_task_ready_scale(task):
            self._task_available.set()
            self._scale_pending.set()  # Check if more foremen needed
        self._dispatcher.set_on_task_ready(_on_task_ready_scale)
        
        # Smart Recovery: Wire CreditWindow to dispatcher for credit-based routing
        self._dispatcher.set_credit_window(self._credit_window)
        
        # Fix #2: Wire reCAPTCHA health check to dispatcher for PA3 fair-share
        # PA3 needs to exclude accounts with dead reCAPTCHA from average calculation
        def _check_recaptcha_health(email: str) -> bool:
            bridge = self._extension_bridge
            if bridge:
                return bridge.is_recaptcha_healthy(email)
            return True  # Assume healthy if no bridge
        self._dispatcher.set_recaptcha_health_fn(_check_recaptcha_health)
        
        # Hard cap: Wire max_workers lookup so dispatcher can cap _per_account_running
        # Without this, T2I fire-and-forget releases session workers immediately,
        # allowing unbounded task dispatch (e.g., 54 tasks for max_workers=20)
        def _get_max_workers(email: str) -> int:
            for acc in self._account_manager._accounts:
                if acc.email == email:
                    return acc.session.max_workers
            return 20  # Fallback default
        self._dispatcher.set_max_workers_fn(_get_max_workers)
        
        # Inject profiles_controller into accounts for debug browser sharing
        if self._profiles_controller:
            for acc in self._account_manager._accounts:
                acc.set_profiles_controller(self._profiles_controller)
        
        # Start persistent browsers for reCAPTCHA refresh
        # If debug browsers are already open, ensure_browser() will ATTACH to them
        try:
            from config.settings import get_settings as _get_settings
            _s = _get_settings()
            _headless = getattr(_s, 'smart_hide_enabled', True) or getattr(_s, 'hide_all_browsers', False)
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
                
                # Dynamic foreman scaling: spawn more foremen when tasks grow
                tg.create_task(self._scale_foremen_loop(tg))
                
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
            # ── BUG-01/11 fix: Requeue tasks AFTER all pipelines finished ──
            # At this point, TaskGroup is done — no pipeline can mutate tasks.
            requeued = 0
            for task in self._dispatcher.get_all_tasks():
                if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                    # BUG-12: Clear stale retry metadata before requeue
                    if hasattr(task, 'retry_original_indices'):
                        task.retry_original_indices = []
                    task.state = TaskState.READY
                    self._dispatcher.requeue_running_task(task)
                    requeued += 1
            if requeued:
                log.info(f"Re-queued {requeued} tasks that were RUNNING/WAITING_POLL")
            
            # Cancel pending extension requests (server + connections stay alive)
            for acc in self._account_manager._accounts:
                bridge = getattr(acc, 'extension_bridge', None)
                if bridge:
                    bridge.cancel_pending_requests()
            # Also cancel on engine-level bridge reference
            if hasattr(self, '_extension_bridge') and self._extension_bridge:
                self._extension_bridge.cancel_pending_requests()
            
            # BUG-03 fix: Clear tracking AFTER pipelines done (not in stop())
            self._running = False
            self._workers.clear()
            self._active_account_emails.clear()
            self._supervisors.clear()
            self._foreman_count.clear()  # Dynamic scaling tracker
            self._task_group = None
            log.info("Engine stopped — worker/foreman tracking reset")
    
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
    
    def _is_image_only_workload(self) -> bool:
        """Check if all READY queued tasks are T2I/I2I (image generation).
        
        Used by foreman stagger to apply minimal delays for image-only
        workloads, since batchGenerateImages is a lightweight sync endpoint
        that doesn't need heavy anti-detect spacing.
        """
        try:
            has_ready = False
            for task in self._dispatcher.get_all_tasks():
                if task.state == TaskState.READY:
                    has_ready = True
                    wf = (getattr(task, 'workflow_type', '') or '').upper()
                    if wf not in ('T2I', 'I2I', ''):
                        return False
            return has_ready  # True only if there ARE ready tasks and all are T2I/I2I
        except Exception:
            return False
    
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
        
        # RC4: Calculate foreman count from max_workers / typical_output.
        # Multiple foremen allow parallel polling (20/20 workers active).
        # 429 prevention relies on _GLOBAL_MIN_SUBMIT_GAP (45s) + SubmitGate,
        # NOT on limiting foremen count.
        import math
        typical_output = self._get_typical_output_count()
        raw_foreman_count = max(1, math.ceil(account.max_workers / typical_output))
        
        # G1: License gate — GLOBAL cap by permissions.limits.max_foremen
        # This caps total foremen across ALL accounts (not per-account)
        # to prevent multi-account bypass of foremen limits.
        foreman_count = raw_foreman_count
        try:
            ctrl = getattr(self, '_app_controller', None)
            if ctrl and hasattr(ctrl, '_permissions'):
                max_foremen = ctrl._permissions.limits.max_foremen
                log.info(
                    f"[G1:{account.email}] max_foremen={max_foremen}, "
                    f"raw_foreman={raw_foreman_count}, existing={len(self._workers)}"
                )
                if max_foremen > 0:
                    # Count active foremen (list cleared on engine stop)
                    total_existing = len(self._workers)
                    remaining_slots = max(0, max_foremen - total_existing)
                    if remaining_slots == 0:
                        log.warning(
                            f"[G1:{account.email}] BLOCKED — global foreman limit "
                            f"reached: {total_existing}/{max_foremen}"
                        )
                        return  # Don't spawn any foremen for this account
                    if raw_foreman_count > remaining_slots:
                        foreman_count = remaining_slots
                        log.info(
                            f"[G1:{account.email}] Global foreman cap: "
                            f"{raw_foreman_count} → {foreman_count} "
                            f"(existing={total_existing}, limit={max_foremen})"
                        )
            else:
                log.warning(
                    f"[G1:{account.email}] No permissions available — "
                    f"ctrl={'set' if ctrl else 'None'}, "
                    f"has_perm={hasattr(ctrl, '_permissions') if ctrl else 'N/A'}"
                )
        except Exception as e:
            log.error(f"[G1:{account.email}] Permission check error: {e}")
        
        # Cap foremen at ready_count — don't spawn 8 foremen for 1 retry task
        ready = self._dispatcher.ready_count
        if ready > 0 and foreman_count > ready:
            log.info(
                f"[Foreman:{account.email}] Capped foremen {foreman_count} → {ready} "
                f"(only {ready} task(s) in queue)"
            )
            foreman_count = ready
        
        # Track starting index to avoid ID collision with existing foremen
        existing_count = self._foreman_count.get(account.email, 0)
        start_idx = existing_count
        
        for i in range(foreman_count):
            foreman_worker = Worker(
                worker_id=f"foreman-{account.email[:8]}-{start_idx + i}",
                api_client=self._api_client,
                on_progress=self._on_progress,
            )
            self._workers.append(foreman_worker)
            tg.create_task(self._foreman_loop(foreman_worker, account))
        
        self._foreman_count[account.email] = existing_count + foreman_count
        self._active_account_emails.add(account.email)
        log.info(
            f"[Supervisor:{account.email}] Spawned CHỦ + {foreman_count} Foremen "
            f"(max_workers={account.max_workers}, output={typical_output}, "
            f"retry={account.retry_count}, timeout={account.request_timeout}s)"
        )
    
    def _get_foreman_count(self, email: str) -> int:
        """Count current foremen for a specific account."""
        prefix = f"foreman-{email[:8]}-"
        return sum(1 for w in self._workers if w.worker_id.startswith(prefix))
    
    async def _scale_foremen_loop(self, tg: asyncio.TaskGroup):
        """Dynamic foreman scaling — each account scales independently.
        
        Runs inside the TaskGroup. When pipeline adds tasks to an already-running
        engine, this detects the deficit and spawns additional foremen.
        
        Each account operates independently: it scales up to its own optimal
        foreman count based on total pending tasks (READY + RUNNING + WAITING_POLL),
        not just ready_count. This prevents the race where foremen consume tasks
        faster than the scaling loop can react.
        """
        while not self._stop_event.is_set():
            try:
                # Wait for signal or poll every 5s
                try:
                    await asyncio.wait_for(self._scale_pending.wait(), timeout=5.0)
                    self._scale_pending.clear()
                except asyncio.TimeoutError:
                    pass
                
                if self._stop_event.is_set():
                    break
                
                # Count total pending tasks (READY + RUNNING + WAITING_POLL)
                # Using total_pending instead of ready_count prevents the race
                # where foremen pick tasks (READY→RUNNING) before scaling detects them
                from core.dispatcher import TaskState
                total_pending = sum(
                    1 for t in self._dispatcher.get_all_tasks_dict().values()
                    if t.state in (TaskState.READY, TaskState.RUNNING, TaskState.WAITING_POLL)
                )
                if total_pending <= 0:
                    continue
                
                # Each account scales independently — no splitting across accounts
                for account in self._account_manager._accounts:
                    if not account.is_enabled:
                        continue
                    if account.email not in self._active_account_emails:
                        continue
                    
                    current = self._foreman_count.get(account.email, 0)
                    
                    # Calculate optimal foreman count per account
                    import math
                    typical_output = self._get_typical_output_count()
                    foreman_cap = 12 if self._is_image_only_workload() else account.max_workers
                    optimal = max(1, min(
                        math.ceil(account.max_workers / typical_output),
                        foreman_cap,
                    ))
                    
                    # Target = optimal (each account independently scales to its max)
                    # No per_account_ready splitting — accounts pick from global queue
                    target = optimal
                    
                    if target <= current:
                        continue
                    
                    # G1: License gate check
                    to_add = target - current
                    try:
                        ctrl = getattr(self, '_app_controller', None)
                        if ctrl and hasattr(ctrl, '_permissions'):
                            max_foremen = ctrl._permissions.limits.max_foremen
                            if max_foremen > 0:
                                total_existing = len(self._workers)
                                remaining_slots = max(0, max_foremen - total_existing)
                                to_add = min(to_add, remaining_slots)
                    except Exception:
                        pass
                    
                    if to_add <= 0:
                        continue
                    
                    log.info(
                        f"[ScaleForemen:{account.email}] Scaling {current} → "
                        f"{current + to_add} foremen (pending={total_pending}, "
                        f"optimal={optimal}, max_workers={account.max_workers})"
                    )
                    
                    start_idx = current
                    for i in range(to_add):
                        foreman_worker = Worker(
                            worker_id=f"foreman-{account.email[:8]}-{start_idx + i}",
                            api_client=self._api_client,
                            on_progress=self._on_progress,
                        )
                        self._workers.append(foreman_worker)
                        tg.create_task(self._foreman_loop(foreman_worker, account))
                    
                    self._foreman_count[account.email] = current + to_add
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[ScaleForemen] Error: {e}")
                await asyncio.sleep(3)
    
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
                
                # Start browser for new account (skip if already ready from hot-add)
                if not (account._browser_session and account._browser_session.is_ready):
                    try:
                        if self._profiles_controller:
                            account.set_profiles_controller(self._profiles_controller)
                        from config.settings import get_settings as _get_settings
                        _headless = getattr(_get_settings(), 'smart_hide_enabled', True) or getattr(_get_settings(), 'hide_all_browsers', False)
                        await account.ensure_browser(headless=_headless)
                    except Exception as e:
                        log.warning(f"Hot-reload: browser start failed for {account.email}: {e}")
                else:
                    log.info(f"Hot-reload: {account.email} browser already ready (hot-add)")
                
                # Wait for extension bridge connection (critical for tokens + reCAPTCHA)
                if self._extension_bridge:
                    if not self._extension_bridge.is_connected(account.email):
                        log.info(f"Hot-reload: waiting for extension connection: {account.email}")
                        connected = await self._extension_bridge.wait_for_extension(
                            account.email, timeout=15.0
                        )
                        if connected:
                            log.info(f"Hot-reload: ✅ extension connected: {account.email}")
                        else:
                            log.warning(f"Hot-reload: ⚠️ extension not connected after 15s: {account.email}")
                    
                    # Populate session from bridge cache (tokens, headers)
                    cached = self._extension_bridge.get_cached_headers(
                        account.email, max_age_seconds=0
                    )
                    if cached:
                        account._session.update_browser_headers(
                            browser_validation=cached.get('x-browser-validation', ''),
                            client_data=cached.get('x-client-data', ''),
                            browser_channel=cached.get('x-browser-channel', 'stable'),
                            browser_copyright=cached.get('x-browser-copyright', ''),
                            browser_year=cached.get('x-browser-year', ''),
                        )
                        xcd = cached.get('x-client-data', '')
                        if len(xcd) >= 20:
                            log.info(f"Hot-reload: {account.email} headers populated (xcd={len(xcd)})")
                    
                    # Ensure bridge ref is set on account
                    if not account.extension_bridge:
                        account.extension_bridge = self._extension_bridge
                
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
        
        # ★ Fix 4c: Respect browser close cooldown (prevents infinite restart loops)
        if self._extension_bridge:
            remaining = self._extension_bridge.get_cooldown_remaining(account.email)
            if remaining > 0:
                log.info(
                    f"[{worker_id}] Browser on cooldown ({remaining:.0f}s remaining) "
                    f"— skipping {tier} recovery"
                )
                return False
        
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
            # Stagger: always use Settings tab anti-detect delay
            from config.settings import get_settings as _get_stagger_settings
            _s = _get_stagger_settings()
            if getattr(_s, 'anti_detect_enabled', True):
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
                # T3: Event-driven pause — instantly wake on resume instead of 0.5s poll
                if not self._pause_event.is_set():
                    log.debug(f"[{fid}] Paused, waiting for resume")
                    while not self._stop_event.is_set() and not self._pause_event.is_set():
                        try:
                            await asyncio.wait_for(self._pause_event.wait(), timeout=2.0)
                        except asyncio.TimeoutError:
                            pass  # Re-check stop_event
                    if self._stop_event.is_set():
                        break
                
                # ★ Hot-disable: idle foreman when account is disabled
                # Running pipelines complete normally, but no NEW tasks picked.
                # When re-enabled, foreman resumes instantly (next loop).
                if not account.is_enabled:
                    await asyncio.sleep(2.0)
                    continue
                
                # ★ Sick account: idle foreman when account is marked sick
                # Sick = repeated circuit breaker trips (reCAPTCHA failure cascade)
                # Tasks already requeued to healthy accounts. Wait for recovery.
                if self.is_account_sick(account.email):
                    await asyncio.sleep(3.0)
                    continue
                
                # DD4: Check supervisor abort signal (circuit breaker OR account deleted)
                if supervisor and supervisor.is_aborted:
                    # Account deleted: supervisor._running is False → exit loop
                    if not supervisor._running:
                        log.info(
                            f"[{fid}] 🛑 Account removed — exiting foreman loop"
                        )
                        break
                    
                    # Circuit breaker: wait for abort to clear
                    log.warning(
                        f"[{fid}] ⚡ Supervisor ABORT — "
                        f"circuit breaker tripped, pausing foreman"
                    )
                    while (supervisor.is_aborted 
                           and supervisor._running
                           and not self._stop_event.is_set()):
                        await asyncio.sleep(1.0)
                    if self._stop_event.is_set() or not supervisor._running:
                        break
                    log.info(f"[{fid}] ✅ Abort cleared, resuming")
                    # Fix #2: Staggered resume — random delay per foreman
                    # to prevent thundering herd (all 8 foremen submitting
                    # simultaneously after circuit breaker closes → burst → 429/403).
                    stagger = random.uniform(1.0, 5.0)
                    log.info(f"[{fid}] Stagger {stagger:.1f}s before resume")
                    await asyncio.sleep(stagger)
                    # ★ Fix 4: Reset T2I active count after circuit breaker recovery
                    # Without this, stale _t2i_active_count blocks all foremen
                    # from picking tasks (counter never decremented after mass requeue).
                    if hasattr(self, '_t2i_active_count'):
                        old = self._t2i_active_count.get(account.email, 0)
                        if old > 0:
                            self._t2i_active_count[account.email] = 0
                            log.info(
                                f"[{fid}] ★ Reset T2I active count "
                                f"{old} → 0 after abort recovery"
                            )
                    self._task_available.set()  # Wake all foremen
                
                # Step 1: Two-phase admission — acquire 1 worker first
                worker_count = 0
                upscale_worker_held = False
                if not account.acquire_workers(1):
                    # T2: Event-driven worker wake — instant instead of 0.5s poll
                    _cap_evt = self._workers_available.setdefault(
                        account.email, asyncio.Event()
                    )
                    _cap_evt.clear()
                    try:
                        await asyncio.wait_for(_cap_evt.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass  # Re-check stop_event/capacity
                    continue
                worker_count = 1
                
                # (T2I pipeline gates removed — worker model: foreman IS the concurrency limit)
                
                # H4 fix: Check account cooldown BEFORE wasting reCAPTCHA tokens
                if self.is_account_on_cooldown(account.email):
                    account.release_workers(worker_count)
                    worker_count = 0
                    await self.wait_for_cooldown(account.email)
                    # ★ Staggered resume: random jitter to avoid thundering herd
                    # After cooldown, all foremen wake simultaneously → 429 again.
                    # Adding 0.5-5s random delay spreads out resume.
                    jitter = random.uniform(0.5, 5.0)
                    log.debug(f"[{fid}] Post-cooldown jitter: {jitter:.1f}s")
                    await asyncio.sleep(jitter)
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
                        
                        # ★ Orphan rescue: if queue empty but READY tasks
                        # exist in _all_tasks, re-enqueue them. Prevents
                        # starvation after 429 requeue storms drain the
                        # PriorityQueue with stale entries.
                        if (self._dispatcher.ready_count == 0
                                and self._dispatcher.running_count == 0):
                            rescued = self._dispatcher.rescue_orphaned_tasks()
                            if rescued > 0:
                                self._task_available.set()
                                continue  # Immediately retry
                        
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
                    
                    # ═══ LICENSE GATES G2/G3/G4 ═══
                    _ctrl = getattr(self, '_app_controller', None)
                    _perm = getattr(_ctrl, '_permissions', None) if _ctrl else None
                    _lc = getattr(_ctrl, '_license_client', None) if _ctrl else None
                    
                    # G2: Daily generation limit
                    if _perm and _lc:
                        try:
                            daily_limit = _perm.limits.daily_generation_limit
                            if daily_limit > 0:
                                today = _lc.usage.today_generations
                                if today >= daily_limit:
                                    log.warning(
                                        f"[G2:{fid}] Daily limit reached: "
                                        f"{today}/{daily_limit} — rejecting task {task.id}"
                                    )
                                    self._dispatcher.fail_task(
                                        task.id, 
                                        f"Daily limit reached ({today}/{daily_limit}). Upgrade license."
                                    )
                                    account.release_workers(worker_count)
                                    worker_count = 0
                                    if self._on_task_failed:
                                        self._on_task_failed(task, f"Daily limit ({today}/{daily_limit})")
                                    await asyncio.sleep(5)  # Avoid rapid-fire rejections
                                    continue
                        except Exception:
                            pass
                    
                    # G4: Feature gate (Continuation / Batch)
                    if _perm:
                        try:
                            from services.permissions import Feature
                            wf = getattr(task, 'workflow_type', None)
                            # Block Continuation for TRIAL
                            if wf and 'continuation' in str(wf).lower():
                                if not _perm.has_feature(Feature.CONTINUATION):
                                    log.warning(f"[G4:{fid}] Continuation blocked for TRIAL — task {task.id}")
                                    self._dispatcher.fail_task(task.id, "Continuation requires Premium license")
                                    account.release_workers(worker_count)
                                    worker_count = 0
                                    continue
                        except Exception:
                            pass
                    
                    # Phase 2 admission: acquire extra workers for output_count > 1
                    output_count = getattr(task, 'output_count', 1) or 1
                    
                    # G3: Cap output_count by license limit
                    if _perm:
                        try:
                            max_outputs = _perm.limits.max_outputs_per_prompt
                            if max_outputs > 0 and output_count > max_outputs:
                                log.info(
                                    f"[G3:{fid}] output_count capped: "
                                    f"{output_count} → {max_outputs} (license limit)"
                                )
                                output_count = max_outputs
                                task.output_count = output_count
                        except Exception:
                            pass
                    
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
                            # Not enough capacity — requeue task, wait with backoff
                            # ★ BUG-B19 fix: notify=False prevents thundering herd.
                            # Without this, requeue_task() wakes ALL idle foremen
                            # who each grab the same task, fail capacity, requeue
                            # → infinite READY→RUNNING loop at ~10x/sec.
                            # Throttle log: only emit once per 30s per task to avoid spam
                            _cap_key = f"_cap_log_{task.id}"
                            _now = time.monotonic()
                            _last = getattr(self, _cap_key, 0.0)
                            if _now - _last > 30.0:
                                setattr(self, _cap_key, _now)
                                log.debug(
                                    f"[{fid}] Waiting for capacity: "
                                    f"output_count={output_count} "
                                    f"(need {output_count}, have {account.session.available_workers + 1})"
                                )
                            self._dispatcher.requeue_task(task, notify=False)
                            account.release_workers(worker_count)
                            worker_count = 0
                            # 15s base + random jitter prevents all workers retrying simultaneously
                            if await self._interruptible_sleep(15.0 + random.uniform(0, 5.0)):
                                continue  # Stop-aware — re-check loop condition
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
                            _headless = getattr(_get_settings(), 'smart_hide_enabled', True) or getattr(_get_settings(), 'hide_all_browsers', False)
                            await account.ensure_browser(headless=_headless)
                        except Exception as e:
                            log.warning(f"Browser start failed for {account.email}: {e} (continuing without persistent browser)")
                    
                    # Bug 11 fix: Removed redundant reCAPTCHA refresh here.
                    # Worker.execute() already handles reCAPTCHA refresh (step B5).
                    # Having it in both places caused double-refresh and wasted 200-500ms.
                    
                    # Step 5: Ensure project exists (shared logic)
                    # BUG-35: Check stop between pre-submit steps
                    if self._stop_event.is_set():
                        break
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
                        # ★ Partial worker release: free extra slots, keep 1 as pipeline slot
                        # Each task acquired output_count workers (e.g. 4). Pipeline only needs
                        # 1 slot to track concurrency. Release (output_count-1) so foremen
                        # can pick new tasks. Pipeline finally releases the remaining 1.
                        # max_workers=20 → max 20 concurrent pipelines (not 5).
                        _release = worker_count - 1
                        if _release > 0:
                            account.release_workers(_release)
                            _cap_evt = self._workers_available.get(account.email)
                            if _cap_evt:
                                _cap_evt.set()  # Wake foremen waiting for capacity
                        t = asyncio.create_task(
                            self._foreman_dispatch_workers(task, account, 1,
                                                          supervisor=supervisor)
                        )
                        active_pipelines.add(t)
                        t.add_done_callback(active_pipelines.discard)
                        worker_count = 0
                        continue
                    
                    # RC4: Per-account rate limiter — serialize submit pipeline
                    # Semaphore(1): only 1 foreman in rate lock at a time (prevents 429 race)
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Semaphore(1)
                    
                    # Step 7: Execute with RETRY + TIMEOUT
                    # Rate lock held ONLY during anti-detect delay + API call,
                    # released between retries so other workers can proceed.
                    
                    # Step 6.5: Upload local image_paths → image_uris
                    # Risk 4 fix: Upload through rate lock to prevent 4 concurrent uploads
                    # I2V image loss fix: Always re-upload when image_paths available.
                    # MediaIds expire between retries/sessions — stale IDs cause silent
                    # failures. Fresh upload from local files is always preferred.
                    if task.image_paths:
                        # BUG-35: Check stop before image upload sequence
                        if self._stop_event.is_set():
                            break
                        # Smart reuse: skip upload if same account already uploaded
                        if task.image_uris and task.image_uris_account == account.email:
                            log.debug(
                                f"[Foreman:{account.email}] Task {task.id}: reusing "
                                f"{len(task.image_uris)} existing image_uris "
                                f"(uploaded by same account)"
                            )
                        else:
                            # Different account or no image_uris → upload fresh
                            if task.image_uris:
                                log.info(
                                    f"[Foreman:{account.email}] Task {task.id}: account changed "
                                    f"({task.image_uris_account} → {account.email}) — "
                                    f"re-uploading {len(task.image_paths)} image(s)"
                                )
                                task.image_uris.clear()
                                task.image_uris_account = None
                            else:
                                log.info(
                                    f"[Foreman:{account.email}] Task {task.id}: uploading "
                                    f"{len(task.image_paths)} image(s) "
                                    f"[{task.stage.value}] progress={task.progress}%"
                                )
                            # ★ Cache-hit bypass: skip rate lock if all images are
                            # already cached (no API upload needed → no rate limiting)
                            _all_cached = await self._check_all_images_cached(task, account)
                            if _all_cached:
                                log.info(
                                    f"[Foreman:{account.email}] Task {task.id}: all "
                                    f"{len(task.image_paths)} image(s) cached — "
                                    f"resolving without rate lock"
                                )
                                await self._resolve_image_paths(task, account)
                            else:
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
                    timeout = 120  # Fixed: 120s for all workflow types
                    result = None
                    
                    # ★ Pre-warm: detect idle and trigger soft recovery BEFORE first attempt
                    # This prevents 403 cascade — cheaper than recovering after failure
                    # BUG-35: Check stop before prewarm (20+s)
                    if not self._stop_event.is_set():
                        await self._maybe_prewarm(account)
                    
                    # ═══ T2I/I2I FIRE-AND-FORGET DISPATCH ═══
                    # T2I API is synchronous (~30-60s per submit).
                    # Two gates before fire-and-forget:
                    # ★ T2I/I2I Worker Model (synchronous — like VEO video)
                    # Foreman blocks until task completes. No pipeline sem, no
                    # fire-and-forget, no dispatch lock. Workers ARE the
                    # concurrency limit — simple and race-free.
                    _wt_dispatch = (task.workflow_type or "").upper()
                    if _wt_dispatch in ("T2I", "I2I"):
                        log.info(
                            f"[Foreman:{account.email}] Task {task.id}: "
                            f"🎨 T2I worker dispatch ({worker_count} workers)"
                        )
                        try:
                            await self._run_t2i_submit_pipeline_bg(
                                task, account, worker_count, supervisor,
                                max_retries, timeout,
                            )
                        except Exception as t2i_err:
                            log.error(
                                f"[Foreman:{account.email}] Task {task.id}: "
                                f"T2I worker error: {t2i_err}",
                                exc_info=True,
                            )
                        worker_count = 0  # Released inside _run_t2i_submit_pipeline_bg
                        continue  # ← Foreman picks next task
                    
                    for attempt in range(max_retries + 1):
                        # BUG-13: Exit retry loop on stop (prevents 900s block)
                        if self._stop_event.is_set():
                            log.info(f"[{fid}] Stop signal — aborting submit retry")
                            break
                        # ★ Per-task cancellation: Del/Del All sets CANCELLED
                        if task.state in (TaskState.CANCELLED, TaskState.FAILED):
                            log.info(
                                f"[{fid}] Task {task.id}: {task.state.value} "
                                f"— aborting submit retry"
                            )
                            break

                        
                        # ★ Layer 4+5 gate: check BEFORE each retry (skip attempt 0)
                        # Both apply to ALL workers on this account (per-email key)
                        # → 1 worker hits 403 → all workers on same account must wait
                        if attempt > 0:
                            # Layer 4: Cooldown — exponential backoff (30→180s)
                            # set_account_cooldown() was triggered by 403 handler below
                            await self.wait_for_cooldown(account.email)
                            # ★ Staggered resume after cooldown
                            jitter = random.uniform(0.5, 5.0)
                            log.debug(f"[{fid}] Post-cooldown jitter: {jitter:.1f}s")
                            await asyncio.sleep(jitter)
                            # Layer 5: Circuit Breaker — extension health
                            await self._wait_for_circuit(account.email)
                            # Re-check cooldown AFTER circuit wake — CircuitBreaker
                            # HALF-OPEN probe may have reset cooldown timer
                            await self.wait_for_cooldown(account.email)
                            # (reCAPTCHA + xcd readiness now handled by _pre_submit_gate below)
                        
                        # ── NEW: Extract frame from _pending_frame_source (set by retry_task) ──
                        # When dispatcher retries a continuation child whose parent is COMPLETED,
                        # it sets _pending_frame_source = parent's best video path.
                        # We extract the last frame here before the first submit.
                        _pfs = getattr(task, '_pending_frame_source', None)
                        if (_pfs and not task.image_uris
                                and not task.continuation_frame_uri):
                            log.info(
                                f"[Foreman:{account.email}] Task {task.id}: "
                                f"extracting continuation frame from _pending_frame_source"
                            )
                            try:
                                re_extracted = await self._re_extract_frame_from_parent(task)
                                if not re_extracted and Path(_pfs).exists():
                                    # Fallback: direct extract from the source path
                                    loop = asyncio.get_running_loop()
                                    re_extracted = await loop.run_in_executor(
                                        self._process_pool,
                                        self._frame_extractor.extract_frame,
                                        _pfs, None,
                                        getattr(task, 'extract_point_ms', None),
                                        True,
                                    )
                                if re_extracted:
                                    task.continuation_frame_local_path = re_extracted
                                    async with self._account_rate_locks[account.email]:
                                        if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else True:
                                            await self._burst_controller.wait(account.email)
                                        fresh_uri = await self._re_upload_continuation_frame(task, account)
                                        if fresh_uri:
                                            task.image_uris = [fresh_uri]
                                            task.continuation_frame_uri = fresh_uri
                                            log.info(
                                                f"[Foreman:{account.email}] Task {task.id}: "
                                                f"frame extracted + uploaded from retry source"
                                            )
                                # Clean up the marker
                                if hasattr(task, '_pending_frame_source'):
                                    del task._pending_frame_source
                            except Exception as pfs_err:
                                log.warning(
                                    f"[Foreman:{account.email}] Task {task.id}: "
                                    f"_pending_frame_source extraction failed: {pfs_err}"
                                )
                        
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
                        
                        # ── Pre-Submit Gate: validate xcd + reCAPTCHA ──
                        gate_ok = await self._pre_submit_gate(account, task, attempt)
                        if not gate_ok:
                            self._dispatcher.requeue_task(task)
                            account.release_workers(worker_count)
                            worker_count = 0
                            result = None
                            break
                        
                        # ═══ PHASE 1: Gap reservation + sleep (OUTSIDE rate lock) ═══
                        # Foremen sleep in PARALLEL — only timestamp reservation is serialized.
                        # This allows N foremen to overlap their wait times instead of
                        # serializing on Semaphore(1) for 45s each.
                        _acct_lock = self._per_account_submit_locks.setdefault(
                            account.email, asyncio.Lock()
                        )
                        _gap_wait_time = 0.0
                        _gap_cooldown_break = False
                        async with _acct_lock:
                            # ── Model-tier-aware gap selection ──
                            from config.constants import is_relaxed_model
                            _task_model = getattr(task, 'model', '') or ''
                            _is_lp = is_relaxed_model(_task_model)
                            if _is_lp:
                                gap = self._GLOBAL_MIN_SUBMIT_GAP        # 45s for LP
                                _ts_dict = self._per_account_last_submit_ts_lp
                            else:
                                gap = self._GLOBAL_MIN_SUBMIT_GAP_FAST   # 3s for Fast
                                _ts_dict = self._per_account_last_submit_ts
                            
                            now = time.time()
                            elapsed = now - _ts_dict.get(account.email, 0)
                            if elapsed < gap:
                                _gap_wait_time = gap - elapsed
                            
                            # ── Reserve timestamp NOW (inside lock) ──
                            # This "claims" the next slot so the NEXT foreman entering
                            # this lock will see the correct future timestamp and calculate
                            # its own gap relative to our reserved time.
                            _ts_dict[account.email] = now + _gap_wait_time
                        # Lock released — other foremen can now reserve their own slots
                        
                        # ── Sleep the gap OUTSIDE all locks (parallel) ──
                        if _gap_wait_time > 0:
                            _tier_label = "LP" if _is_lp else "Fast"
                            log.info(
                                f"[SubmitGate:{account.email}] Task {task.id}: "
                                f"waiting {_gap_wait_time:.1f}s "
                                f"(parallel gap sleep, model={_tier_label})"
                            )
                            for _w in range(int(_gap_wait_time), 0, -1):
                                self._dispatcher.update_progress(
                                    task.id, task.progress,
                                    f"⏳ gate {_w}s"
                                )
                                if await self._interruptible_sleep(1):
                                    break
                            frac = _gap_wait_time - int(_gap_wait_time)
                            if frac > 0:
                                await asyncio.sleep(frac)
                        
                        # Re-check cooldown after gap sleep
                        if self.is_account_on_cooldown(account.email):
                            log.info(
                                f"[Foreman:{account.email}] Task {task.id}: cooldown detected "
                                f"after submit gate — requeueing"
                            )
                            self._dispatcher.requeue_task(task)
                            account.release_workers(worker_count)
                            worker_count = 0
                            result = None
                            break
                        
                        # ═══ PHASE 2: API call (INSIDE rate lock) ═══
                        # Rate lock serializes ONLY the actual API call to prevent
                        # burst-firing multiple requests in <100ms on same account.
                        async with self._account_rate_locks[account.email]:
                            # Fix F: Re-check cooldown INSIDE rate lock.
                            if self.is_account_on_cooldown(account.email):
                                log.info(
                                    f"[Foreman:{account.email}] Task {task.id}: cooldown detected INSIDE "
                                    f"rate lock — waiting for cooldown to expire"
                                )
                                _cd_until = self._account_cooldowns.get(account.email)
                                if _cd_until:
                                    _cd_secs = max(0, (_cd_until - datetime.now()).total_seconds())
                                    for _w in range(int(_cd_secs), 0, -1):
                                        self._dispatcher.update_progress(
                                            task.id, task.progress,
                                            f"⏳ cooldown {_w}s"
                                        )
                                        if await self._interruptible_sleep(1):
                                            break
                                continue  # Re-enter retry loop → re-acquire rate lock
                            
                            # Anti-Detect burst delay (short, inside rate lock)
                            if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else getattr(self, '_anti_detect_enabled', True):
                                _wt = (task.workflow_type or "").upper()
                                _delay_s = self._burst_controller.get_delay(account.email)
                                
                                _t2i_first_done_key = f"_t2i_burst_done_{account.email}"
                                _is_first_t2i = (
                                    _wt in ("T2I", "I2I")
                                    and attempt == 0
                                    and not getattr(self, _t2i_first_done_key, False)
                                )
                                
                                if _wt in ("T2I", "I2I"):
                                    self._dispatcher.update_progress(
                                        task.id, 15,
                                        f"⏳ Waiting ({_delay_s:.0f}s)" if not _is_first_t2i else "🚀 First submit"
                                    )
                                else:
                                    self._dispatcher.update_progress(
                                        task.id, 5,
                                        f"⏳ Waiting ({_delay_s:.0f}s)"
                                    )
                                
                                if _is_first_t2i:
                                    log.info(
                                        f"[Foreman:{account.email}] Task {task.id}: T2I cold start "
                                        f"— skipping burst delay → submit attempt {attempt+1}/{max_retries+1}"
                                    )
                                    setattr(self, _t2i_first_done_key, True)
                                else:
                                    log.info(
                                        f"[Foreman:{account.email}] Task {task.id}: adaptive delay "
                                        f"({self._burst_controller.get_delay(account.email):.1f}s base) → submit "
                                        f"attempt {attempt+1}/{max_retries+1} [{task.stage.value}] "
                                        f"progress={task.progress}%"
                                    )
                                    await self._burst_controller.wait(account.email)
                            
                            # Update actual submit timestamp (inside rate lock)
                            if _is_lp:
                                self._per_account_last_submit_ts_lp[account.email] = time.time()
                            else:
                                self._per_account_last_submit_ts[account.email] = time.time()

                            try:
                                # ★ PRIMARY PATH: Extension-based submission
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
                                            f"📤 Submitting..."
                                        )
                                    else:
                                        self._dispatcher.update_progress(
                                            task.id, 10,
                                            f"📤 Submitting..."
                                        )
                                    # ★ Gemini AI: Auto-enhance prompt (if enabled)
                                    if (getattr(self._settings, 'prompt_enhance_enabled', False)
                                            and getattr(self._settings, 'prompt_auto_enhance', False)):
                                        try:
                                            enhanced = await self._enhance_prompt(task, account)
                                            if enhanced and enhanced != task.prompt:
                                                task._original_prompt = task.prompt  # Keep original
                                                task.prompt = enhanced
                                                # ★ Notify UI of prompt change
                                                self._dispatcher.update_progress(
                                                    task.id, task.progress,
                                                    "✨ Prompt enhanced"
                                                )
                                        except Exception as e:
                                            log.debug(f"[Enhance] Skip: {e}")
                                    
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
                                        batch_id=getattr(task, '_batch_id', ''),        # F12: same batchId across batch
                                        session_id=getattr(task, '_session_id', ''),    # F12: same sessionId across batch
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
                                    
                                    # ★ Progressive timeout: use tier-based bridge timeout
                                    from config.constants import get_timeout_tier
                                    tier = get_timeout_tier(attempt)
                                    bridge_timeout = tier['bridge_timeout']
                                    
                                    ext_result = await asyncio.wait_for(
                                        ext_bridge.submit_prompt(
                                            email=account.email,
                                            endpoint=endpoint_key,
                                            body=body,
                                            needs_recaptcha=True,
                                            attempt=attempt,
                                        ),
                                        timeout=bridge_timeout + 5,  # outer guard
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
                            
                            # M2: Defense-in-depth
                            account.invalidate_recaptcha()
                        # Rate lock released here — other workers can now submit
                        
                        if result.success:
                            # M1 fix: Record success for adaptive delay tightening
                            self._burst_controller.record_success(account.email)
                            self._credit_window.record_success(account.email)
                            # RC4: Adaptive gap decay — reduce gap on success (min 20s)
                            if self._GLOBAL_MIN_SUBMIT_GAP > 45:
                                self._GLOBAL_MIN_SUBMIT_GAP = max(
                                    self._GLOBAL_MIN_SUBMIT_GAP - 1, 45
                                )
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
                        
                        # ★ Gemini AI: Auto-fix policy-blocked prompts (max 3 attempts)
                        _fix_attempts = getattr(task, '_policy_fix_attempts', 0)
                        if (self._is_policy_error(result.error or "")
                                and getattr(self._settings, 'prompt_enhance_enabled', False)
                                and getattr(self._settings, 'prompt_auto_fix', False)
                                and _fix_attempts < 3):
                            task._policy_fix_attempts = _fix_attempts + 1
                            log.warning(
                                f"[Foreman:{account.email}] Task {task.id}: "
                                f"POLICY VIOLATION (fix attempt {_fix_attempts + 1}/3): "
                                f"{result.error} — attempting auto-fix..."
                            )
                            try:
                                fixed = await self._fix_policy_prompt(
                                    task, result.error or "", account
                                )
                                if fixed:
                                    task.prompt = fixed
                                    # ★ Notify UI of prompt change
                                    self._dispatcher.update_progress(
                                        task.id, task.progress,
                                        f"🔧 Auto-fixed ({_fix_attempts + 1}/3)"
                                    )
                                    log.info(
                                        f"[Foreman:{account.email}] Task {task.id}: "
                                        f"prompt auto-fixed (attempt {_fix_attempts + 1}/3) → retrying"
                                    )
                                    continue  # Retry with fixed prompt (no backoff)
                                else:
                                    log.warning(
                                        f"[Foreman:{account.email}] Task {task.id}: "
                                        f"auto-fix returned None — prompt unfixable"
                                    )
                            except Exception as fix_err:
                                log.warning(f"[Fix] Error (attempt {_fix_attempts + 1}/3): {fix_err}")
                            # If fix failed/returned None, fall through to normal retry/fail
                        elif (self._is_policy_error(result.error or "")
                              and _fix_attempts >= 3):
                            log.error(
                                f"[Foreman:{account.email}] Task {task.id}: "
                                f"POLICY FIX EXHAUSTED (3/3 attempts) — marking as error"
                            )
                            break  # Exit retry loop → task marked as error
                        
                        # Auth errors → special handling, no retry
                        if self._is_auth_error(result.error or ""):
                            break
                        
                        # Non-auth error — retry with backoff (OUTSIDE rate lock)
                        task.retry_attempts = attempt + 1
                        if attempt < max_retries:
                            # ★ FIX: Early-abort if extension disconnected
                            # Prevents wasting 10+ retries on a dead connection
                            ext_bridge = getattr(account, 'extension_bridge', None)
                            if ext_bridge and not ext_bridge.is_connected(account.email):
                                log.warning(
                                    f"[Foreman:{account.email}] Task {task.id}: "
                                    f"extension disconnected — requeuing task"
                                )
                                self._dispatcher.requeue_task(task)
                                account.release_workers(worker_count)
                                worker_count = 0
                                result = None
                                break
                            
                            # Risk 3 fix: Higher initial backoff for 403 cooldown
                            # Old: 2, 4, 8, 16, 30  →  New: 5, 10, 20, 40, 60
                            backoff = min(5 * (2 ** attempt), 60)
                            
                            # ★ Fix 2B: Sliding window 429 tracking (quota exhaustion)
                            # Tracks ALL 429 timestamps in a 60s window per account.
                            # Unlike the old consecutive counter, this catches 429s from
                            # different tasks and doesn't reset on a single success.
                            error_str = result.error or ""
                            if "429" in error_str or "exhausted" in error_str.lower():
                                import time as _time
                                if not hasattr(self, '_account_429_window'):
                                    self._account_429_window = {}
                                now = _time.monotonic()
                                window = self._account_429_window.setdefault(account.email, [])
                                window.append(now)
                                # Prune entries older than 60s
                                window[:] = [t for t in window if now - t < 60]
                                recent_429_count = len(window)
                                
                                # RC4: Credit-based 429 tracking
                                low_health = self._credit_window.record_429(account.email)
                                if low_health:
                                    # Adaptive gap: increase submit spacing on low credits
                                    old_gap = self._GLOBAL_MIN_SUBMIT_GAP
                                    self._GLOBAL_MIN_SUBMIT_GAP = min(
                                        self._GLOBAL_MIN_SUBMIT_GAP + 10, 90
                                    )
                                    log.info(
                                        f"[AdaptiveGap] {account.email}: gap "
                                        f"{old_gap:.0f}→{self._GLOBAL_MIN_SUBMIT_GAP:.0f}s "
                                        f"(429 low credits)"
                                    )
                                
                                # ★ Tiered response based on 429 density in 60s window:
                                # 1 hit  → soft per-task backoff (10s), others can try
                                # 2 hits → account cooldown (60s)
                                # 3+ hits → hard cooldown + requeue + extended pause
                                if recent_429_count >= 3:
                                    # Quota severely exhausted — requeue + extended pause
                                    cooldown_secs = min(30 * recent_429_count, 120)
                                    self.set_account_cooldown(
                                        account.email,
                                        f"429/quota_exhausted (window={recent_429_count}/60s)"
                                    )
                                    log.warning(
                                        f"[Foreman:{account.email}] Task {task.id}: "
                                        f"429 x{recent_429_count} in 60s → account cooldown {cooldown_secs}s"
                                    )
                                    backoff = 120  # 2min for quota reset
                                    # RC4: Queue Status — requeue notification
                                    self._dispatcher.update_progress(
                                        task.id, task.progress,
                                        f"🔄 429 ×{recent_429_count} requeue"
                                    )
                                    # ★ BUG-B19 fix: Release workers during extended 429 pause.
                                    if worker_count > 0:
                                        log.info(
                                            f"[Foreman:{account.email}] Task {task.id}: "
                                            f"releasing {worker_count} worker(s) for 429 extended pause"
                                        )
                                        account.release_workers(worker_count)
                                        worker_count = 0
                                    # Requeue task so another foreman can try after quota resets
                                    self._dispatcher.requeue_task(task, notify=False)
                                    log.warning(
                                        f"[Foreman:{account.email}] Task {task.id}: "
                                        f"{recent_429_count}x 429 in window → requeued + pause {backoff}s"
                                    )
                                    await self._interruptible_sleep(backoff)
                                    result = None  # Signal: task was requeued
                                    break  # Exit retry loop — task is back in queue
                                elif recent_429_count >= 2:
                                    # Quota likely exhausted — account cooldown
                                    cooldown_secs = min(30 * recent_429_count, 120)
                                    self.set_account_cooldown(
                                        account.email,
                                        f"429/quota_exhausted (window={recent_429_count}/60s)"
                                    )
                                    log.warning(
                                        f"[Foreman:{account.email}] Task {task.id}: "
                                        f"429 x{recent_429_count} in 60s → account cooldown {cooldown_secs}s"
                                    )
                                    # RC4: Queue Status — cooldown notification
                                    self._dispatcher.update_progress(
                                        task.id, task.progress,
                                        f"⛔ 429 ×{recent_429_count} wait {cooldown_secs}s"
                                    )
                                else:
                                    # First 429 in window — soft per-task backoff only
                                    backoff = 10
                                    log.info(
                                        f"[Foreman:{account.email}] Task {task.id}: "
                                        f"429 (first in 60s window) → per-task backoff {backoff}s, "
                                        f"other prompts can still submit"
                                    )
                                    # RC4: Queue Status — retry notification
                                    self._dispatcher.update_progress(
                                        task.id, task.progress,
                                        f"⏳ 429 retry {backoff}s"
                                    )
                            else:
                                # Non-429 error → no window changes (timestamps auto-expire)
                                pass
                            
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
                                # RC4: Queue Status — 403 notification
                                self._dispatcher.update_progress(
                                    task.id, task.progress,
                                    f"⛔ 403 recover"
                                )
                                
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
                                # Non-reCAPTCHA, non-403 errors: refresh headers (lightweight — no tab reload)
                                if account.extension_bridge:
                                    try:
                                        await account.extension_bridge.refresh_headers_lightweight(
                                            account.email, timeout=10
                                        )
                                        log.info(f"[Recovery] {acct_email}: Extension headers refreshed (lightweight)")
                                    except Exception as e:
                                        log.debug(f"[Recovery] Extension header refresh failed: {e}")
                                    backoff = max(backoff, 10)
                            
                            log.warning(
                                f"[Foreman:{account.email}] Task {task.id} failed "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {result.error}. "
                                f"Retrying in {backoff}s..."
                            )
                            # RC4: Countdown loop — update Queue Status every second
                            _interrupted = False
                            for _cd in range(int(backoff), 0, -1):
                                self._dispatcher.update_progress(
                                    task.id, task.progress,
                                    f"⏳ retry {_cd}s"
                                )
                                if await self._interruptible_sleep(1):
                                    _interrupted = True
                                    break
                            if _interrupted: break
                    
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
                                if getattr(_get_sh_settings2(), 'smart_hide_enabled', True) or getattr(_get_sh_settings2(), 'hide_all_browsers', False):
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
                            self._dispatcher.update_progress(
                                task.id, 20,
                                f"✅ Submitted, polling..."
                            )
                            
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
                            # ★ Partial worker release: keep 1 slot, release the rest
                            # Submit done — pipeline only polls/downloads/upscales.
                            # Release (output_count-1) workers so foreman can pick new tasks.
                            # Pipeline finally releases the remaining 1 worker.
                            # max_workers=20 → max 20 concurrent pipelines (not 5).
                            _release = worker_count - 1
                            if _release > 0:
                                account.release_workers(_release)
                                _cap_evt = self._workers_available.get(account.email)
                                if _cap_evt:
                                    _cap_evt.set()  # Wake foremen waiting for capacity
                            t = asyncio.create_task(
                                self._foreman_dispatch_workers(task, account, 1,
                                                              supervisor=supervisor)
                            )
                            active_pipelines.add(t)
                            t.add_done_callback(active_pipelines.discard)
                            worker_count = 0
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
                                self._dispatcher.decrement_running(account.email)
                                task._counter_decremented = True  # Prevent double-decrement in complete_task/fail_task
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
                        # T2: Wake foremen waiting for worker capacity
                        _cap_evt = self._workers_available.get(account.email)
                        if _cap_evt:
                            _cap_evt.set()
                    # ★ Pool Separation: release upscale slot if still held
                    if upscale_worker_held:
                        account.release_upscale_worker()
                        upscale_worker_held = False
                        log.warning(
                            f"[Engine] Cleanup: released leaked upscale worker "
                            f"for {account.email}"
                        )
                
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
            # BUG-17: Don't finalize if stop was signaled (leave for requeue)
            if self._stop_event.is_set():
                log.info(
                    f"[Foreman:{account.email}] Task {task.id}: "
                    f"stop signal — skipping finalize (will be requeued)"
                )
                return
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
                # T2: Wake foremen waiting for worker capacity
                _cap_evt = self._workers_available.get(account.email)
                if _cap_evt:
                    _cap_evt.set()
            # ★ Fix M1: Force prewarm for NEXT task by backdating last_submit.
            # Video pipeline took minutes — session context (reCAPTCHA,
            # headers, cookies) has gone stale. Setting to 0 guarantees
            # _maybe_prewarm() triggers before the next submit.
            self._last_successful_submit[account.email] = 0
            log.info(
                f"[Fix-M1:{account.email}] Task {task.id}: pipeline done "
                f"— forced prewarm for next task"
            )

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
            # Map worker index → original video index for correct variant letter naming
            # e.g., retry_original_indices=[2,3] → worker 0 maps to index 2, worker 1 to index 3
            ori = getattr(task, 'retry_original_indices', [])
            effective_video_index = ori[video_index] if video_index < len(ori) else video_index
            
            # ── Phase 1: Self-poll op ──
            task.video_outputs[video_index].quality = "polling"
            fife_url, media_id, poll_error = await self._worker_poll_op(
                task, account, op_name, scene_id, video_index
            )

            if not fife_url:
                error_msg = poll_error or "Poll failed or timeout"
                
                # ★ Fix 2A: Auto-retry for server-side VIDEO_GENERATION_TIMED_OUT
                # Re-submit via force_retry_video instead of marking FAILED immediately
                timeout_retry_key = f'_timeout_retry_{video_index}'
                timeout_retries = getattr(task, timeout_retry_key, 0)
                if (error_msg.startswith("RETRYABLE_TIMEOUT:") 
                        and timeout_retries < 2
                        and not self._stop_event.is_set()):
                    actual_error = error_msg.split(":", 1)[1]
                    setattr(task, timeout_retry_key, timeout_retries + 1)
                    log.warning(
                        f"{log_prefix} ⏱️ SERVER TIMEOUT → auto-retry "
                        f"#{timeout_retries + 1}/2: {actual_error}"
                    )
                    # Wait 30s before re-submit (server cooldown)
                    await asyncio.sleep(30)
                    if self._stop_event.is_set():
                        error_msg = "Stopped during timeout retry wait"
                    else:
                        retried = self._dispatcher.force_retry_video(task.id, video_index)
                        if retried:
                            # ★ BUG-2 FIX: Propagate timeout retry counter to replacement task
                            # Without this, each new task starts with timeout_retries=0
                            # → infinite retry chain (2 retries × N levels = unlimited)
                            for rep_id, (oid, vidx) in self._dispatcher._replace_target_map.items():
                                if oid == task.id and vidx == video_index:
                                    rep_task = self._dispatcher._all_tasks.get(rep_id)
                                    if rep_task:
                                        setattr(rep_task, '_timeout_retry_0', timeout_retries + 1)
                                    break
                            log.info(
                                f"{log_prefix} ♻️ force_retry_video issued for timeout retry "
                                f"#{timeout_retries + 1}/2"
                            )
                            # Signal result as timeout_retry — finalize will handle
                            results_dict[video_index] = WorkerVideoResult(
                                index=video_index, op_name=op_name,
                                quality="timeout_retry",
                                error=f"auto-retry #{timeout_retries + 1}/2 → re-queued",
                            )
                            return
                        else:
                            log.warning(f"{log_prefix} force_retry_video failed — marking as failed")
                            error_msg = actual_error  # Use original error
                elif error_msg.startswith("RETRYABLE_TIMEOUT:"):
                    # Strip prefix for final error message (retries exhausted)
                    error_msg = error_msg.split(":", 1)[1]
                    if timeout_retries >= 2:
                        error_msg += f" (after {timeout_retries} auto-retries)"
                
                log.warning(f"{log_prefix} Poll returned no result (failed/timeout): {error_msg}")
                task.video_outputs[video_index].quality = "failed"
                results_dict[video_index] = WorkerVideoResult(
                    index=video_index, op_name=op_name,
                    quality="failed", error=error_msg,
                )
                return

            # BUG-09: Stop check between poll → download
            if self._stop_event.is_set():
                log.info(f"{log_prefix} Stop signal — aborting after poll")
                results_dict[video_index] = WorkerVideoResult(
                    index=video_index, op_name=op_name,
                    media_id=media_id, fife_url=fife_url,
                    quality="failed", error="Stopped by user",
                )
                return

            # Update VideoOutputInfo with poll result
            task.video_outputs[video_index].media_id = media_id
            task.video_outputs[video_index].quality = "downloading"
            log.info(f"{log_prefix} ✅ SUCCESSFUL → downloading")

            # ★ Fix M2: Session health check between poll → download
            await self._ensure_session_health(account, "post-poll")

            # ── Phase 2: Download 720p ──
            local_720p = await self._download_single(
                task, account, fife_url, effective_video_index, "720p"
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

            # ★ Fix M2: Session health check between download → upscale
            await self._ensure_session_health(account, "post-download")

            # ── Phase 3: Upscale (if needed) ──
            local_final = local_720p
            final_quality = "720p"

            # BUG-08/09: Stop check between download → upscale
            if self._stop_event.is_set():
                log.info(f"{log_prefix} Stop signal — skipping upscale")
                results_dict[video_index] = WorkerVideoResult(
                    index=video_index, op_name=op_name,
                    media_id=media_id, fife_url=fife_url,
                    file_720p=local_720p, file_final=local_720p,
                    quality="720p", thumbnail_path=thumb_path or "",
                )
                return

            if task.download_quality != "720p" and media_id:
                # Always delegate upscale to background UpscaleQueue (decoupled)
                # Submit workers release immediately after 720p download
                #
                # ★ BUG-FIX: Pass retry_indices=[video_index] so _process_job
                # maps this single media_id to the correct task.video_outputs
                # slot. Without this, all per-worker jobs write to index 0.
                from core.upscale_queue import UpscaleJob
                self._upscale_queue.enqueue(UpscaleJob(
                    task_id=task.id,
                    account_email=email,
                    original_account=email,  # DD6: track original for failover tracing
                    media_ids=[media_id],
                    output_uris=[fife_url],
                    target_quality=task.download_quality,
                    aspect_ratio=task.aspect_ratio,
                    retry_indices=[video_index],
                ))
                log.info(f"{log_prefix} Delegated upscale → UpscaleQueue")

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

    async def _ensure_session_health(self, account, phase: str):
        """Fix M2: Lightweight session health check between video pipeline phases.
        
        Verifies extension bridge connectivity and refreshes stale headers.
        Called at poll→download and download→upscale boundaries to prevent
        session rot during long-running video tasks.
        """
        email = account.email
        bridge = getattr(account, 'extension_bridge', None)
        
        # 1. Check extension bridge alive
        if bridge and not bridge.is_connected(email):
            log.warning(f"[SessionHealth:{email}] Bridge disconnected at {phase}")
            for _ in range(3):
                await asyncio.sleep(2)
                if bridge.is_connected(email):
                    log.info(f"[SessionHealth:{email}] Bridge reconnected at {phase}")
                    break
            else:
                log.warning(f"[SessionHealth:{email}] Bridge still disconnected after 6s")
                return  # Can't do more without bridge
        
        # 2. Refresh headers if stale (>5min since last refresh)
        if bridge and bridge.is_connected(email):
            last_hdr = getattr(bridge, f'_last_header_ts_{email}', 0)
            if time.time() - last_hdr > 300:  # 5 min
                try:
                    await bridge.refresh_headers_lightweight(email, timeout=5)
                    setattr(bridge, f'_last_header_ts_{email}', time.time())
                    log.info(f"[SessionHealth:{email}] Headers refreshed at {phase}")
                except Exception as e:
                    log.debug(f"[SessionHealth:{email}] Header refresh failed: {e}")
        
        # 3. Refresh access token if expired or close to expiry
        if account.session.is_token_expired:
            try:
                await account.refresh_access_token()
                log.info(f"[SessionHealth:{email}] Token refreshed at {phase}")
            except Exception as e:
                log.debug(f"[SessionHealth:{email}] Token refresh failed: {e}")

    async def _worker_poll_op(
        self, task: Task, account: AccountManager,
        op_name: str, scene_id: str, video_index: int,
    ) -> tuple:
        """Worker self-polls its own op until DONE.
        
        Returns: (fife_url, media_id, error) — error is populated on FAILED.
        Returns (None, None, error_msg) if FAILED, (None, None, None) if timeout.
        1 op per API call — fully isolated from other workers.
        """
        from config.constants import AppConstants
        log_prefix = f"[Worker:{account.email}:#{video_index}]"
        
        elapsed = 0
        max_poll_time = AppConstants.MAX_POLL_TIME
        status = "MEDIA_GENERATION_STATUS_PENDING"
        poll_count = 0
        poll_403_count = 0  # Fix M3: Track consecutive 403 during poll

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
                    elif response.response_code == 403:
                        # ★ Fix M3: 403 during poll = session corruption
                        poll_403_count += 1
                        log.warning(
                            f"{log_prefix} Poll 403 #{poll_403_count}: {response.error}"
                        )
                        if poll_403_count >= 3:
                            log.error(
                                f"{log_prefix} 3x consecutive 403 during poll "
                                f"— session degraded, aborting"
                            )
                            return None, None, "Session degraded (3x 403 during poll)"
                        # Try lightweight session recovery
                        await self._ensure_session_health(account, "poll-403")
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
                        return details[0]["fifeUrl"], details[0]["mediaId"], None
                    return None, None, "No output details in response"

                elif op_status == "MEDIA_GENERATION_STATUS_FAILED":
                    error = op.get("operation", {}).get("error", {}).get("message", "unknown")
                    log.warning(f"{log_prefix} Op FAILED: {error}")
                    # Signal retryable server-side timeout with prefix
                    if "TIMED_OUT" in error.upper():
                        return None, None, f"RETRYABLE_TIMEOUT:{error}"
                    return None, None, error

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
        return None, None, None  # Timeout

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
                video_index=video_index,
            )
            if paths and paths[0]:
                log.info(f"{log_prefix} Downloaded {quality_subfolder}")
                return paths[0]
            log.warning(f"{log_prefix} Download returned empty")
            return ""
        except asyncio.CancelledError:
            # BUG-05: Re-raise CancelledError instead of swallowing
            log.info(f"{log_prefix} Download cancelled")
            raise
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
        
        # BUG-08: Early exit on stop (upscale can take 3-5 minutes)
        if self._stop_event.is_set():
            log.info(f"{log_prefix} Stop signal — skipping upscale")
            return ""
        
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
                    video_index=video_index,
                )
                if dl_paths and dl_paths[0]:
                    task.video_outputs[video_index].upscale_status = "success"
                    return dl_paths[0]
            
            task.video_outputs[video_index].upscale_status = "failed"
            log.warning(f"{log_prefix} Upscale failed, keeping 720p")
            return ""
        except asyncio.CancelledError:
            log.info(f"{log_prefix} Upscale cancelled")
            task.video_outputs[video_index].upscale_status = "failed"
            raise
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
            thumb_path = str(thumb_dir / f"thumb_{task.id}_{video_index:02d}.jpg")
            
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
        # BUG-15: Don't complete task during stop (leave in RUNNING for requeue)
        if self._stop_event.is_set():
            log.info(
                f"[Finalizer] Task {task.id}: stop active — "
                f"skipping completion (task stays RUNNING for requeue)"
            )
            return
        
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
            # ★ Check if failures are policy errors → auto-fix prompt + retry
            all_errors = [r.error for r in failures if r.error]
            is_policy = any(self._is_policy_error(e) for e in all_errors)
            _fix_attempts = getattr(task, '_policy_fix_attempts', 0)
            
            if (is_policy
                    and getattr(self._settings, 'prompt_enhance_enabled', False)
                    and getattr(self._settings, 'prompt_auto_fix', False)
                    and _fix_attempts < 3):
                task._policy_fix_attempts = _fix_attempts + 1
                log.warning(
                    f"[Finalizer:{email}] Task {task.id}: "
                    f"ALL {failed_count} ops POLICY VIOLATION (fix attempt {_fix_attempts + 1}/3): "
                    f"{all_errors[0]} — attempting auto-fix..."
                )
                try:
                    fixed = await self._fix_policy_prompt(
                        task, all_errors[0], account,
                        attempt=_fix_attempts + 1
                    )
                    if fixed:
                        task.prompt = fixed
                        # ★ Notify UI of prompt change
                        self._dispatcher.update_progress(
                            task.id, task.progress,
                            f"🔧 Auto-fixed ({_fix_attempts + 1}/3)"
                        )
                        log.info(
                            f"[Finalizer:{email}] Task {task.id}: "
                            f"prompt auto-fixed (attempt {_fix_attempts + 1}/3) → requeueing"
                        )
                        # Requeue task for retry with fixed prompt
                        self._dispatcher.requeue_task(task)
                        self._task_available.set()  # Wake foremen for requeued task
                        return  # Don't fail — task will be retried
                    else:
                        log.warning(
                            f"[Finalizer:{email}] Task {task.id}: "
                            f"auto-fix returned None — prompt unfixable"
                        )
                except Exception as fix_err:
                    log.warning(
                        f"[Finalizer:{email}] Task {task.id}: "
                        f"auto-fix error (attempt {_fix_attempts + 1}/3): {fix_err}"
                    )
            
            # ★ Transient server error retry (HIGH_TRAFFIC, timeout, rate limit, etc.)
            is_transient = any(self._is_transient_error(e) for e in all_errors)
            _transient_attempts = getattr(task, '_transient_retry_attempts', 0)
            FINALIZER_MAX_TRANSIENT_RETRIES = 3
            
            if is_transient and not is_policy and _transient_attempts < FINALIZER_MAX_TRANSIENT_RETRIES:
                task._transient_retry_attempts = _transient_attempts + 1
                delay = min(15 * (2 ** _transient_attempts), 120)  # 15s, 30s, 60s
                log.warning(
                    f"🔄 [Finalizer:{email}] Task {task.id}: "
                    f"transient error '{all_errors[0][:60]}' — "
                    f"auto-retry {_transient_attempts + 1}/{FINALIZER_MAX_TRANSIENT_RETRIES} "
                    f"in {delay}s"
                )
                await asyncio.sleep(delay)
                # ★ Fix 3: Exit if engine stopping during retry delay
                if self._stop_event.is_set():
                    return
                # Reset operation state for fresh submit
                task.operation_names.clear()
                task.stage = TaskStage.INIT
                task.state = TaskState.RUNNING
                self._dispatcher.requeue_task(task)
                self._task_available.set()
                return  # Don't fail — task will be retried
            
            # Fall through: fail the task
            error_detail = all_errors[0] if all_errors else "All video operations failed"
            if is_policy:
                error_detail = (
                    f"⛔ Prompt Policy Violation — unfixable after "
                    f"{_fix_attempts}/3 auto-fix attempts. "
                    f"Original error: {all_errors[0][:80] if all_errors else 'unknown'}"
                )
            elif is_transient:
                error_detail = (
                    f"⚠️ Transient error after {_transient_attempts}/{FINALIZER_MAX_TRANSIENT_RETRIES} retries: "
                    f"{all_errors[0][:80] if all_errors else 'unknown'}"
                )
            self._dispatcher.fail_task(task.id, error_detail)
            self._error_count += 1
            emit_event(EventType.TASK_FAILED, {
                "task_id": task.id, "error": error_detail,
                "reason": "all_ops_failed",
            }, source="engine")
            if self._on_task_failed:
                self._on_task_failed(task, error_detail)
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
        
        # G5: License usage — count on successful 720p download (not submit)
        try:
            ctrl = getattr(self, '_app_controller', None)
            if ctrl and hasattr(ctrl, '_license_client'):
                ctrl._license_client.log_generation()
                # Count downloads per actual video file, not per prompt
                for _ in final_paths:
                    ctrl._license_client.log_download()
        except Exception:
            pass

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
                # ★ SPEED OPT: Activate children FIRST, then reCAPTCHA wait
                # Children will self-wait for reCAPTCHA when their foreman picks them
                self._dispatcher.activate_children_early(
                    task.id,
                    continuation_frame_uri,
                    continuation_frame_local,
                )
                # ★ CONTINUATION FIX: Wake sleeping foremen immediately
                # so they pick up newly-READY children without 2s delay
                self._task_available.set()

        # ── Complete task ──
        # ★ FIX: Defer completion if upscale is pending in UpscaleQueue.
        # _poll_operation sets task.stage=UPSCALING at L6914 before enqueue.
        # UpscaleQueue._process_job will call complete_task() when upscale finishes.
        # Also check upscale_media_ids as a safety net (set at L6913).
        has_pending_upscale = (
            task.stage == TaskStage.UPSCALING
            or (
                getattr(task, 'download_quality', '720p') != '720p'
                and getattr(task, 'upscale_media_ids', None)
                and any(
                    getattr(vo, 'upscale_status', '') in ('submitting', 'polling', 'pending', '')
                    for vo in (task.video_outputs or [])
                    if getattr(vo, 'upscale_status', '') not in ('success', 'failed', 'skipped')
                )
            )
        )
        
        if has_pending_upscale:
            # Don't call complete_task — UpscaleQueue owns completion.
            # Keep stage as UPSCALING (already set by _poll_operation).
            self._dispatcher.update_progress(
                task.id, 88, f"⬆️ Upscaling {getattr(task, 'download_quality', '?')}..."
            )
            log.info(
                f"[Finalizer] Task {task.id}: upscale pending — "
                f"deferring complete_task to UpscaleQueue"
            )
        else:
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
        
        # T1: Wake UpscaleQueue instantly when all prompts are done
        if (self._dispatcher.ready_count <= 0 
                and self._dispatcher.running_count <= 0):
            self._upscale_wake_event.set()
        
        # G5: License usage tracking — moved to DOWNLOADED_720 checkpoint
        # (counts actual completed downloads, not submit attempts)

    async def _resume_from_checkpoint(self, task: Task, account: AccountManager):
        """Resume task from saved checkpoint stage (skip completed phases).
        
        Delegates to the existing _poll_operation for checkpoint resume logic,
        since the resume paths are complex and already well-tested.
        """
        # Reuse existing checkpoint resume code in _poll_operation
        # (L2909-3011 handles GENERATED, DOWNLOADED_720, UPSCALING, UPSCALED)
        await self._poll_operation(task, account)


    
    def _get_t2i_resources(self, email: str):
        """Lazily create per-account T2I semaphore + lock.
        
        Returns (Semaphore(12), Lock) for the given account.
        Thread-safe: dict.setdefault is atomic in CPython.
        """
        if email not in self._t2i_output_semaphores:
            self._t2i_output_semaphores[email] = asyncio.Semaphore(12)
            self._t2i_slot_locks[email] = asyncio.Lock()
            self._t2i_active_outputs[email] = 0
        return (self._t2i_output_semaphores[email],
                self._t2i_slot_locks[email])
    
    async def _acquire_t2i_slots(self, count: int, email: str):
        """Acquire exactly `count` T2I output slots atomically for one account.
        
        Prevents partial-allocation deadlock: either acquire ALL
        slots at once or wait and retry. A lock serializes attempts
        so two tasks don't race for the same partial pool.
        Each account has its own Semaphore(12) — independent limits.
        """
        sem, lock = self._get_t2i_resources(email)
        while True:
            async with lock:
                # Check if enough slots are available (non-blocking peek)
                if sem._value >= count:
                    # Grab all slots while holding the lock
                    for _ in range(count):
                        await sem.acquire()
                    return  # All slots acquired atomically
            # Not enough slots — wait for one to free up, then retry
            await sem.acquire()
            sem.release()
            await asyncio.sleep(0.5)
    
    # ═══════════════════════════════════════════════════════════════
    # T2I WORKER SUBMIT PIPELINE (synchronous — foreman awaits)
    # ═══════════════════════════════════════════════════════════════
    async def _run_t2i_submit_pipeline_bg(
        self, task: Task, account: AccountManager,
        worker_count: int, supervisor=None,
        max_retries: int = 10, timeout: int = 120,
    ):
        """T2I worker pipeline — called synchronously by foreman.
        
        Encapsulates the ENTIRE T2I lifecycle:
        1. Rate lock + burst delay (anti-detect)
        2. Submit via extension bridge — 1 API call per image × output_count
           (F12 verified: website sends 1 request per image, NOT all in batch)
        3. Parse response → extract fife_urls + media_ids 
        4. Download 1K images → complete task
        5. Enqueue UpscaleQueue for 4K upscale (if needed)
        
        Worker model: foreman blocks until this returns.
        No pipeline sem, no submit ordering — natural serialization.
        """
        import time
        import uuid as _uuid_batch
        from core.remedy_registry import execute_recovery
        
        _t2i_slots_held = 0
        try:
            # ★ T2I Concurrency Cap: max 12 active outputs per account
            # Uses atomic acquisition to prevent partial-allocation deadlock
            _oc = task.output_count or 4
            await self._acquire_t2i_slots(_oc, account.email)
            _t2i_slots_held = _oc
            self._t2i_active_outputs[account.email] = self._t2i_active_outputs.get(account.email, 0) + _oc
            log.info(
                f"[T2I-Worker:{account.email}] Task {task.id}: "
                f"acquired {_oc} output slots "
                f"(active={self._t2i_active_outputs.get(account.email, 0)})"
            )
            
            # ★ Fix G: CONCURRENT T2I submission
            # F12 verified: website fires all 4 requests simultaneously (~0ms apart).
            # Each HTTP request takes ~30s for server response.
            # Sequential: 4 × 30s = 120s. Concurrent: max(30s) = 30s.
            all_output_uris = []
            all_media_ids = []
            
            # Generate shared batch_id + session_id for all images in this task
            shared_batch_id = getattr(task, '_batch_id', '') or str(_uuid_batch.uuid4())
            shared_session_id = getattr(task, '_session_id', '') or f";{int(time.time() * 1000)}"
            task._batch_id = shared_batch_id
            task._session_id = shared_session_id
            
            base_seed = task.seed if task.seed is not None else None
            
            # ── Phase 1: Gate + Lock (ONCE for entire batch) ──
            gate_ok = await self._pre_submit_gate(account, task, 0)
            if not gate_ok:
                self._dispatcher.requeue_task(task)
                account.release_workers(worker_count)
                worker_count = 0
                return
            
            async with self._account_rate_locks[account.email]:
                if self.is_account_on_cooldown(account.email):
                    log.info(
                        f"[T2I-BG:{account.email}] Task {task.id}: "
                        f"cooldown inside rate lock — requeuing"
                    )
                    self._dispatcher.requeue_task(task)
                    account.release_workers(worker_count)
                    worker_count = 0
                    return
                _acct_lock = self._per_account_submit_locks.setdefault(
                    account.email, asyncio.Lock()
                )
                async with _acct_lock:
                    now = time.time()
                    elapsed = now - self._per_account_last_submit_ts.get(account.email, 0)
                    gap = self._GLOBAL_MIN_SUBMIT_GAP_T2I
                    if elapsed < gap:
                        await asyncio.sleep(gap - elapsed)
                    if self.is_account_on_cooldown(account.email):
                        self._dispatcher.requeue_task(task)
                        account.release_workers(worker_count)
                        worker_count = 0
                        return
                    
                    # Burst delay INSIDE lock (RC3: prevents Semaphore(3) race)
                    _settings = self._settings
                    _anti_detect = getattr(_settings, 'anti_detect_enabled', True) if _settings else True
                    if _anti_detect:
                        log.info(
                            f"[T2I-BG:{account.email}] Task {task.id}: "
                            f"adaptive delay before batch submit ({_oc} images)"
                        )
                        await self._burst_controller_t2i.wait(account.email)
                    
                    # RC3: Timestamp INSIDE lock
                    self._per_account_last_submit_ts[account.email] = time.time()
            
            # ── Phase 2: Build all request bodies upfront ──
            ext_bridge = getattr(account, 'extension_bridge', None)
            if not ext_bridge or not ext_bridge.is_connected(account.email):
                log.warning(
                    f"[T2I-BG:{account.email}] Task {task.id}: "
                    f"extension not connected — requeuing"
                )
                self._dispatcher.requeue_task(task)
                account.release_workers(worker_count)
                worker_count = 0
                return
            
            from config.constants import get_timeout_tier
            tier = get_timeout_tier(0)
            bridge_timeout = tier.get('t2i_bridge_timeout', tier['bridge_timeout'])
            
            request_bodies = []
            for img_idx in range(_oc):
                img_seed = (base_seed + img_idx) if base_seed is not None else None
                endpoint_key, body = self._api_client.build_request_body(
                    workflow_type=task.workflow_type,
                    prompt=task.prompt or "",
                    project_id=account.project_id or "",
                    aspect_ratio=task.aspect_ratio or "IMAGE_ASPECT_RATIO_LANDSCAPE",
                    model=task.model or "GEM_PIX_2",
                    output_count=1,
                    seed=img_seed,
                    paygate_tier=account.paygate_tier or "PAYGATE_TIER_TWO",
                    image_uris=task.image_uris,
                    batch_id=shared_batch_id,
                    session_id=shared_session_id,
                )
                request_bodies.append((img_idx, endpoint_key, body))
            
            # ── Phase 3: Fire ALL requests concurrently ──
            # ★ Fix H2: simulate_activity ONCE for entire batch (not per-image)
            try:
                await ext_bridge.simulate_activity(account.email, timeout=3.0)
                await asyncio.sleep(0.3)
            except Exception:
                pass
            
            self._dispatcher.update_progress(
                task.id, 30,
                f"📤 Submitting {_oc} images concurrently..."
            )
            
            async def _submit_one(img_idx: int, endpoint_key: str, body: dict):
                """Submit a single image and return (img_idx, result_or_error)."""
                try:
                    log.info(
                        f"[T2I-BG:{account.email}] Task {task.id}: "
                        f"📦 submitting T2I (image {img_idx+1}/{_oc})"
                    )
                    result = await asyncio.wait_for(
                        ext_bridge.submit_prompt(
                            email=account.email,
                            endpoint=endpoint_key,
                            body=body,
                            needs_recaptcha=True,
                            attempt=0,
                            timeout=bridge_timeout,
                            lock_free=True,  # ★ Fix H2: batch already gated
                        ),
                        timeout=bridge_timeout + 10,
                    )
                    return (img_idx, result, None)
                except Exception as exc:
                    return (img_idx, None, exc)
            
            log.info(
                f"[T2I-BG:{account.email}] Task {task.id}: "
                f"🚀 firing {_oc} concurrent submit requests"
            )
            
            concurrent_results = await asyncio.gather(
                *[_submit_one(idx, ep, bd) for idx, ep, bd in request_bodies],
                return_exceptions=False,
            )
            
            # ★ Fix N4: Yield to event loop after heavy gather completes —
            # lets UI updates process before download phase starts.
            await asyncio.sleep(0)
            
            # ── Phase 4: Parse all results ──
            failed_indices = []  # Images that need retry
            consecutive_400_count = 0  # ★ Fix I: track transient 400s
            for img_idx, ext_result, exc in concurrent_results:
                if exc:
                    log.warning(
                        f"[T2I-BG:{account.email}] Task {task.id}: "
                        f"image {img_idx+1}/{_oc} exception: "
                        f"{type(exc).__name__}: {exc}"  # ★ Fix H3
                    )
                    failed_indices.append(img_idx)
                    continue
                
                if ext_result and ext_result.get('success'):
                    data = ext_result.get('data', {})
                    img_uris = []
                    img_mids = []
                    
                    if 'media' in data:
                        for item in data['media']:
                            gen_img = (item.get('image') or {}).get('generatedImage', {})
                            fife_url = gen_img.get('fifeUrl', '')
                            mid = item.get('mediaId', '') or item.get('name', '')
                            if fife_url:
                                img_uris.append(fife_url)
                                img_mids.append(mid)
                        log.info(
                            f"[T2I-BG:{account.email}] "
                            f"[T2I-Parse] image {img_idx+1}/{_oc}: "
                            f"{len(img_uris)} image(s), "
                            f"mediaIds={[m[:20] for m in img_mids]}"
                        )
                    
                    self._burst_controller_t2i.record_success(account.email)
                    self.record_circuit_success(account.email)
                    
                    if img_uris:
                        all_output_uris.extend(img_uris)
                        all_media_ids.extend(img_mids)
                    else:
                        log.warning(
                            f"[T2I-BG:{account.email}] Task {task.id}: "
                            f"0 output URIs in response (image {img_idx+1}/{_oc})"
                        )
                
                elif ext_result:
                    error = ext_result.get('error', 'unknown')
                    status_code = ext_result.get('status', 0)
                    error_lower = (error or "").lower()
                    
                    log.warning(
                        f"[T2I-BG:{account.email}] Task {task.id}: "
                        f"image {img_idx+1}/{_oc} failed: {error}"
                    )
                    
                    if "403" in str(error) or "recaptcha" in error_lower:
                        self._burst_controller_t2i.record_error(
                            account.email, status_code or 403
                        )
                        self.record_circuit_403(account.email)
                        self.set_account_cooldown(
                            account.email, f"403/{error}"
                        )
                    
                    if status_code == 400 or "invalid argument" in error_lower:
                        consecutive_400_count += 1  # ★ Fix I
                        log.warning(
                            f"[T2I-BG:{account.email}] Task {task.id}: "
                            f"HTTP 400 — will retry "
                            f"(count={consecutive_400_count}/3, "
                            f"model={task.model}, ar={task.aspect_ratio})"
                        )
                        if consecutive_400_count >= 3:
                            log.error(
                                f"[T2I-BG:{account.email}] Task {task.id}: "
                                f"3+ consecutive 400s — failing task "
                                f"(model={task.model}, ar={task.aspect_ratio})"
                            )
                            self._dispatcher.fail_task(
                                task.id, f"Invalid request: {error[:120]}"
                            )
                            return
                        failed_indices.append(img_idx)
                        continue
                    
                    failed_indices.append(img_idx)
                else:
                    log.warning(
                        f"[T2I-BG:{account.email}] Task {task.id}: "
                        f"no response from extension (image {img_idx+1}/{_oc})"
                    )
                    failed_indices.append(img_idx)
            
            # ── Phase 5: Sequential retry for failed images ──
            if failed_indices:
                log.info(
                    f"[T2I-BG:{account.email}] Task {task.id}: "
                    f"{len(failed_indices)}/{_oc} images failed — retrying sequentially"
                )
                for img_idx in failed_indices:
                    if self._stop_event.is_set():
                        break
                    if task.state in (TaskState.CANCELLED, TaskState.FAILED):
                        break
                    
                    img_seed = (base_seed + img_idx) if base_seed is not None else None
                    _retry_success = False
                    
                    for attempt in range(1, max_retries + 1):
                        if self._stop_event.is_set():
                            break
                        
                        await self.wait_for_cooldown(account.email)
                        await self._wait_for_circuit(account.email)
                        
                        gate_ok = await self._pre_submit_gate(account, task, attempt)
                        if not gate_ok:
                            self._dispatcher.requeue_task(task)
                            account.release_workers(worker_count)
                            worker_count = 0
                            return
                        
                        async with self._account_rate_locks[account.email]:
                            if self.is_account_on_cooldown(account.email):
                                self._dispatcher.requeue_task(task)
                                account.release_workers(worker_count)
                                worker_count = 0
                                return
                            _acct_lock = self._per_account_submit_locks.setdefault(
                                account.email, asyncio.Lock()
                            )
                            async with _acct_lock:
                                now = time.time()
                                elapsed = now - self._per_account_last_submit_ts.get(account.email, 0)
                                gap = self._GLOBAL_MIN_SUBMIT_GAP_T2I
                                if elapsed < gap:
                                    await asyncio.sleep(gap - elapsed)
                                # RC3: Burst delay + timestamp INSIDE lock
                                await self._burst_controller_t2i.wait(account.email)
                                self._per_account_last_submit_ts[account.email] = time.time()
                        
                        try:
                            endpoint_key_r, body_r = self._api_client.build_request_body(
                                workflow_type=task.workflow_type,
                                prompt=task.prompt or "",
                                project_id=account.project_id or "",
                                aspect_ratio=task.aspect_ratio or "IMAGE_ASPECT_RATIO_LANDSCAPE",
                                model=task.model or "GEM_PIX_2",
                                output_count=1,
                                seed=img_seed,
                                paygate_tier=account.paygate_tier or "PAYGATE_TIER_TWO",
                                image_uris=task.image_uris,
                                batch_id=shared_batch_id,
                                session_id=shared_session_id,
                            )
                            
                            tier_r = get_timeout_tier(attempt)
                            bt_r = tier_r.get('t2i_bridge_timeout', tier_r['bridge_timeout'])
                            
                            log.info(
                                f"[T2I-BG:{account.email}] Task {task.id}: "
                                f"📦 retry #{attempt} image {img_idx+1}/{_oc}"
                            )
                            
                            ext_result_r = await asyncio.wait_for(
                                ext_bridge.submit_prompt(
                                    email=account.email,
                                    endpoint=endpoint_key_r,
                                    body=body_r,
                                    needs_recaptcha=True,
                                    attempt=attempt,
                                    timeout=bt_r,
                                ),
                                timeout=bt_r + 10,
                            )
                            
                            if ext_result_r and ext_result_r.get('success'):
                                data_r = ext_result_r.get('data', {})
                                if 'media' in data_r:
                                    for item in data_r['media']:
                                        gen_img = (item.get('image') or {}).get('generatedImage', {})
                                        fife_url = gen_img.get('fifeUrl', '')
                                        mid = item.get('mediaId', '') or item.get('name', '')
                                        if fife_url:
                                            all_output_uris.append(fife_url)
                                            all_media_ids.append(mid)
                                    log.info(
                                        f"[T2I-BG:{account.email}] "
                                        f"[T2I-Retry] image {img_idx+1}/{_oc}: OK"
                                    )
                                self._burst_controller_t2i.record_success(account.email)
                                self.record_circuit_success(account.email)
                                _retry_success = True
                                break
                            elif ext_result_r:
                                err_r = ext_result_r.get('error', 'unknown')
                                sc_r = ext_result_r.get('status', 0)
                                err_r_lower = (err_r or "").lower()
                                log.warning(
                                    f"[T2I-BG:{account.email}] Task {task.id}: "
                                    f"retry #{attempt} image {img_idx+1}/{_oc} failed: {err_r}"
                                )
                                # ★ Fix I: 400 in retry → transient, just delay and retry
                                if sc_r == 400 or "invalid argument" in err_r_lower:
                                    log.info(
                                        f"[T2I-BG:{account.email}] Task {task.id}: "
                                        f"retry #{attempt} got 400 — treating as transient"
                                    )
                                    if attempt < max_retries:
                                        await asyncio.sleep(8)
                                        continue
                                elif "403" in str(err_r) or "recaptcha" in err_r_lower:
                                    self._burst_controller_t2i.record_error(account.email, sc_r or 403)
                                    self.record_circuit_403(account.email)
                                    self.set_account_cooldown(account.email, f"403/{err_r}")
                                    
                                    ext_br = getattr(account, 'extension_bridge', None)
                                    recovery_ctx = {
                                        "consecutive_403": self._circuit_consecutive_403.get(account.email, 0),
                                    }
                                    recovery_result = await execute_recovery(
                                        account=account, error_msg=err_r or "",
                                        context=recovery_ctx, ext_bridge=ext_br,
                                        dispatcher=self._dispatcher,
                                        credit_window=self._credit_window,
                                        multi_account=self._account_manager,
                                    )
                                    if recovery_result.failover:
                                        self._dispatcher.requeue_task(task)
                                        account.release_workers(worker_count)
                                        worker_count = 0
                                        return
                                if attempt < max_retries:
                                    await asyncio.sleep(5)
                                    continue
                        except asyncio.TimeoutError:
                            log.warning(
                                f"[T2I-BG:{account.email}] Task {task.id}: "
                                f"retry timeout image {img_idx+1}/{_oc}"
                            )
                            if attempt < max_retries:
                                await asyncio.sleep(min(10 * (2 ** attempt), 60))
                                continue
                        except Exception as e:
                            log.error(
                                f"[T2I-BG:{account.email}] Task {task.id}: "
                                f"retry error image {img_idx+1}/{_oc}: {e}",
                                exc_info=True,
                            )
                            if attempt < max_retries:
                                await asyncio.sleep(min(10 * (2 ** attempt), 60))
                                continue
                    
                    if not _retry_success:
                        log.warning(
                            f"[T2I-BG:{account.email}] Task {task.id}: "
                            f"image {img_idx+1}/{_oc} failed all retries — skipping"
                        )
            
            # ═══ After multi-image loop: download + upscale pipeline ═══
            log.info(
                f"[T2I-BG:{account.email}] Task {task.id}: "
                f"multi-image loop complete: {len(all_output_uris)}/{_oc} images"
            )
            
            if all_output_uris:
                log.info(
                    f"[T2I-BG:{account.email}] Task {task.id}: "
                    f"🚀 fire-and-forget → download {len(all_output_uris)} images"
                )
                asyncio.create_task(
                    self._run_t2i_pipeline_bg(
                        task, account,
                        all_output_uris, all_media_ids,
                        worker_count,
                        t2i_slots_held=_t2i_slots_held,
                    )
                )
                # Ownership transferred to background task
                worker_count = 0
                _t2i_slots_held = 0
                return
            
            # No images at all — requeue
            log.warning(
                f"[T2I-BG:{account.email}] Task {task.id}: "
                f"0/{_oc} images succeeded — requeuing task"
            )
            self._dispatcher.requeue_task(task)
            account.release_workers(worker_count)
            worker_count = 0
            return
        
        except Exception as e:
            log.error(
                f"[T2I-BG:{account.email}] Task {task.id}: "
                f"pipeline error: {e}",
                exc_info=True,
            )
            try:
                self._dispatcher.fail_task(task.id, f"T2I pipeline error: {e}")
            except Exception:
                pass
        
        finally:
            # ★ Release T2I output slots (only if NOT transferred to background)
            if _t2i_slots_held > 0:
                sem = self._t2i_output_semaphores.get(account.email)
                for _ in range(_t2i_slots_held):
                    if sem: sem.release()
                self._t2i_active_outputs[account.email] = max(
                    0, self._t2i_active_outputs.get(account.email, 0) - _t2i_slots_held
                )
                log.info(
                    f"[T2I-Worker:{account.email}] Task {task.id}: "
                    f"released {_t2i_slots_held} output slots "
                    f"(active={self._t2i_active_outputs.get(account.email, 0)})"
                )
            # ★ Release workers if still held (only if NOT transferred)
            if worker_count > 0:
                try:
                    account.release_workers(worker_count)
                except Exception:
                    pass

    async def _run_t2i_pipeline_bg(
        self, task: Task, account: AccountManager,
        fife_urls: list, media_ids: list,
        worker_count: int,
        t2i_slots_held: int = 0,
    ):
        """T2I pipeline: download 1K images → complete task → background upscale.
        
        Architecture (fire-and-forget — mirrors video pipeline):
        1. Wait for server to generate high-quality images
        2. Download 1K images → complete task
        3. Enqueue UpscaleQueue for 4K upscale
        4. Release workers + semaphore slots in finally
        
        Called as background task via asyncio.create_task() — foreman
        is NOT blocked. Worker and semaphore ownership transferred here.
        
        Args:
            fife_urls: Remote FIFE URLs for generated images (1K resolution)
            media_ids: mediaId per image (needed for upscale API)
            worker_count: Worker slots to release on exit
            t2i_slots_held: T2I output semaphore slots to release on exit
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
            if not task.video_outputs:
                from core.dispatcher import VideoOutputInfo
                for idx in range(total):
                    mid = media_ids[idx] if idx < len(media_ids) else ""
                    task.video_outputs.append(VideoOutputInfo(
                        index=idx,
                        media_id=mid,
                        quality="pending",
                    ))
            
            # BUG-16: Skip download if stop is active or task cancelled
            if self._stop_event.is_set():
                log.info(f"[T2I-Pipeline] Task {task.id}: stop signal — skipping download")
                return
            if task.state in (TaskState.CANCELLED, TaskState.FAILED):
                log.info(
                    f"[T2I-Pipeline] Task {task.id}: task {task.state.value} "
                    f"— skipping download"
                )
                return
            
            # === Stage 1: Download 1K images ===
            # ★ Wait 45s after submit for server to generate high-quality images
            self._dispatcher.update_progress(
                task.id, 75, f"🎨 Generating..."
            )
            # ★ Fix B: T2I images generate much faster than videos
            # Old: 45s (copied from video pipeline — too long for images)
            # New: 15s + download retry handles slow generation
            _t2i_generation_wait = 15
            log.info(f"[T2I-Pipeline] Task {task.id}: waiting {_t2i_generation_wait}s before download")
            await asyncio.sleep(_t2i_generation_wait)
            
            # ★ Download with retry: 3 attempts, 20s apart
            local_paths = []
            _T2I_DL_MAX_RETRIES = 3
            _T2I_DL_RETRY_INTERVAL = 10  # ★ Fix C: reduced from 20s
            for dl_attempt in range(1, _T2I_DL_MAX_RETRIES + 1):
                if self._stop_event.is_set():
                    break
                if task.state in (TaskState.CANCELLED, TaskState.FAILED):
                    break
                self._dispatcher.update_progress(
                    task.id, 80 + dl_attempt * 3,
                    f"📥 Download attempt {dl_attempt}/{_T2I_DL_MAX_RETRIES} ({total} images)"
                )
                local_paths = await self._download_outputs(
                    task, fife_urls,
                    quality_subfolder="1K",
                    generate_thumbnails=True,
                )
                if local_paths:
                    log.info(
                        f"[T2I-Pipeline] Task {task.id}: download OK "
                        f"(attempt {dl_attempt}, {len(local_paths)} files)"
                    )
                    break
                # Not ready yet — retry after interval
                if dl_attempt < _T2I_DL_MAX_RETRIES:
                    log.warning(
                        f"[T2I-Pipeline] Task {task.id}: download empty "
                        f"(attempt {dl_attempt}), retrying in {_T2I_DL_RETRY_INTERVAL}s..."
                    )
                    self._dispatcher.update_progress(
                        task.id, 80 + dl_attempt * 3,
                        f"⏳ Retry in {_T2I_DL_RETRY_INTERVAL}s..."
                    )
                    await asyncio.sleep(_T2I_DL_RETRY_INTERVAL)
            
            if not local_paths:
                log.warning(
                    f"[T2I-Pipeline] Task {task.id}: download returned 0 files "
                    f"after {_T2I_DL_MAX_RETRIES} attempts"
                )
                self._dispatcher.fail_task(
                    task.id, f"Image download failed after {_T2I_DL_MAX_RETRIES} attempts"
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
            
            # === Stage 2: Check if upscale needed ===
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
            
            if not should_upscale:
                # No upscale needed — 1K is final
                task.output_uris = local_paths
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
                # Complete with 1K
                self._dispatcher.update_progress(task.id, 100, "✅ Complete")
                self._dispatcher.complete_task(
                    task.id, output_uris=task.output_uris,
                )
                log.info(
                    f"[T2I-Pipeline] Task {task.id}: ✅ DONE "
                    f"({len(local_paths)} files, quality=1K)"
                )
                return
            
            # === Stage 2b: Complete task with 1K NOW (like video 720p) ===
            # Workers released → foreman unblocked → can pick next task
            task.output_uris = local_paths
            self._dispatcher.update_progress(
                task.id, 90,
                f"⬆️ Upscaling to {upscale_quality} ({total} images)"
            )
            log.info(
                f"[T2I-Pipeline] Task {task.id}: 1K download complete, "
                f"enqueueing UpscaleQueue → {upscale_quality}"
            )
            
            # === Stage 3: Enqueue UpscaleQueue for image upscale ===
            # ★ Skip upscale if task was cancelled during download
            if task.state in (TaskState.CANCELLED, TaskState.FAILED):
                log.info(
                    f"[T2I-Pipeline] Task {task.id}: task {task.state.value} "
                    f"— skipping upscale enqueue"
                )
                return
            # Uses same infrastructure as video upscale (cooldown, reCAPTCHA, bridge)
            from core.upscale_queue import UpscaleJob
            upscale_queue = getattr(self, '_upscale_queue', None)
            if upscale_queue:
                upscale_job = UpscaleJob(
                    task_id=task.id,
                    account_email=account.email,
                    media_ids=media_ids,
                    output_uris=fife_urls,
                    target_quality=upscale_quality,
                    aspect_ratio=getattr(task, 'aspect_ratio', ''),
                    job_type="image",
                    local_paths=local_paths,
                    upscale_quality=upscale_quality,
                    original_account=account.email,
                )
                upscale_queue.enqueue(upscale_job)
                log.info(
                    f"[T2I-Pipeline] Task {task.id}: "
                    f"enqueued {len(media_ids)} images to UpscaleQueue"
                )
            else:
                # Fallback if upscale_queue not initialized
                log.warning(
                    f"[T2I-Pipeline] Task {task.id}: "
                    f"UpscaleQueue not available, using legacy _t2i_upscale_bg"
                )
                asyncio.create_task(
                    self._t2i_upscale_bg(
                        task, account, media_ids, local_paths,
                        upscale_quality, total,
                    )
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
            # ★ Release T2I output semaphore slots (transferred from submit pipeline)
            if t2i_slots_held > 0:
                sem = self._t2i_output_semaphores.get(account.email)
                for _ in range(t2i_slots_held):
                    if sem: sem.release()
                self._t2i_active_outputs[account.email] = max(
                    0, self._t2i_active_outputs.get(account.email, 0) - t2i_slots_held
                )
                log.info(
                    f"[T2I-Pipeline:{account.email}] Task {task.id}: "
                    f"released {t2i_slots_held} output slots "
                    f"(active={self._t2i_active_outputs.get(account.email, 0)})"
                )

    async def _t2i_upscale_bg(
        self, task: Task, account: AccountManager,
        media_ids: list, local_paths: list,
        upscale_quality: str, total: int,
    ):
        """Background T2I image upscale — fully decoupled from foreman.
        
        Architecture (mirrors video UpscaleQueue):
        - No account_rate_locks (upsampleImage is a different API endpoint)
        - No global_submit_lock (no cross-account contention needed)
        - Per-account semaphore limits concurrent upscale requests to 2
        - Each image upscale is fire-and-forget via asyncio.gather
        
        This eliminates the rate lock contention that previously caused
        foreman to block while waiting for image upscales to complete.
        """
        from pathlib import Path
        import base64
        
        resolution_map = {
            '4K': 'UPSAMPLE_IMAGE_RESOLUTION_4K',
            '2K': 'UPSAMPLE_IMAGE_RESOLUTION_2K',
        }
        target_resolution = resolution_map.get(
            upscale_quality.upper(),
            'UPSAMPLE_IMAGE_RESOLUTION_4K'
        )
        
        # Per-account semaphore: limit concurrent upscale requests to 2
        # (separate from foreman's rate locks — no contention)
        if not hasattr(self, '_t2i_upscale_semaphores'):
            self._t2i_upscale_semaphores = {}
        if account.email not in self._t2i_upscale_semaphores:
            self._t2i_upscale_semaphores[account.email] = asyncio.Semaphore(4)
        sem = self._t2i_upscale_semaphores[account.email]
        
        max_upscale_retries = 3
        
        async def _upscale_one(idx: int, mid: str, local_1k: str):
            """Upscale a single image with retry, protected by semaphore."""
            vo = task.video_outputs[idx] if idx < len(task.video_outputs) else None
            
            if not mid:
                log.warning(
                    f"[T2I-Upscale] {idx+1}/{total}: no mediaId, keeping 1K"
                )
                if vo:
                    vo.upscale_status = "skipped"
                    vo.quality = "1K"
                return local_1k
            
            for attempt in range(max_upscale_retries):
                if self._stop_event.is_set():
                    break
                
                try:
                    # ── Pre-Submit Gate: validate before T2I upscale ──
                    _gate_ok = await self._pre_submit_gate(account, task, attempt)
                    if not _gate_ok:
                        log.warning(
                            f"[T2I-Upscale] {idx+1}/{total}: "
                            f"PreSubmitGate failed — skipping attempt {attempt+1}"
                        )
                        continue
                    
                    async with sem:  # Limit concurrent upscale requests
                        log.info(
                            f"[T2I-Upscale] {idx+1}/{total}: "
                            f"upscaling mediaId={mid[:30]}... → {upscale_quality}"
                            f"{f' (attempt {attempt+1})' if attempt > 0 else ''}"
                        )
                        
                        if vo:
                            vo.upscale_status = "submitting"
                        
                        # Cooldown check (lightweight — no lock contention)
                        if self.is_account_on_cooldown(account.email):
                            log.info(
                                f"[T2I-Upscale] {idx+1}/{total}: "
                                f"account on cooldown, waiting..."
                            )
                            await self.wait_for_cooldown(account.email)
                            if self._stop_event.is_set():
                                break
                        
                        # Wait for extension bridge (may be reconnecting after app restart)
                        ext_bridge = getattr(account, 'extension_bridge', None)
                        if not ext_bridge or not ext_bridge.is_connected(account.email):
                            # Auto-inject bridge from engine's global reference
                            if not ext_bridge:
                                global_bridge = getattr(self, '_extension_bridge', None)
                                if global_bridge:
                                    account.extension_bridge = global_bridge
                                    ext_bridge = global_bridge
                                    log.info(
                                        f"[T2I-Upscale] {idx+1}/{total}: "
                                        f"injected global extension bridge"
                                    )
                            
                            # Wait up to 30s for bridge to reconnect
                            if ext_bridge and not ext_bridge.is_connected(account.email):
                                log.info(
                                    f"[T2I-Upscale] {idx+1}/{total}: "
                                    f"extension bridge not connected, waiting up to 30s..."
                                )
                                for _wait in range(15):
                                    await asyncio.sleep(2.0)
                                    if ext_bridge.is_connected(account.email):
                                        log.info(
                                            f"[T2I-Upscale] {idx+1}/{total}: "
                                            f"extension bridge reconnected"
                                        )
                                        break
                                else:
                                    log.warning(
                                        f"[T2I-Upscale] {idx+1}/{total}: "
                                        f"extension bridge timeout, keeping 1K"
                                    )
                                    if vo:
                                        vo.upscale_status = "skipped"
                                        vo.quality = "1K"
                                    return local_1k
                            elif not ext_bridge:
                                log.warning(
                                    f"[T2I-Upscale] {idx+1}/{total}: "
                                    f"no extension bridge available, keeping 1K"
                                )
                                if vo:
                                    vo.upscale_status = "skipped"
                                    vo.quality = "1K"
                                return local_1k
                        
                        # Wait for reCAPTCHA readiness (prevents submit during page recovery)
                        # Without this gate, upscale retries fire during soft recovery
                        # → "Could not extract reCAPTCHA site key" → all attempts wasted
                        try:
                            if hasattr(ext_bridge, 'check_recaptcha_ready'):
                                rc_ready = await asyncio.wait_for(
                                    ext_bridge.check_recaptcha_ready(account.email),
                                    timeout=10.0,
                                )
                                if not rc_ready:
                                    log.info(
                                        f"[T2I-Upscale] {idx+1}/{total}: "
                                        f"reCAPTCHA not ready, waiting up to 30s..."
                                    )
                                    for _rc_wait in range(15):
                                        await asyncio.sleep(2.0)
                                        if self._stop_event.is_set():
                                            break
                                        try:
                                            rc_ok = await asyncio.wait_for(
                                                ext_bridge.check_recaptcha_ready(account.email),
                                                timeout=5.0,
                                            )
                                            if rc_ok:
                                                log.info(
                                                    f"[T2I-Upscale] {idx+1}/{total}: "
                                                    f"reCAPTCHA now ready"
                                                )
                                                break
                                        except Exception:
                                            pass
                                    else:
                                        log.warning(
                                            f"[T2I-Upscale] {idx+1}/{total}: "
                                            f"reCAPTCHA still not ready after 30s — "
                                            f"attempting submit anyway"
                                        )
                        except asyncio.TimeoutError:
                            log.warning(
                                f"[T2I-Upscale] {idx+1}/{total}: "
                                f"reCAPTCHA readiness check timed out, "
                                f"waiting 10s for page recovery..."
                            )
                            await asyncio.sleep(10)
                        except Exception as e:
                            log.debug(
                                f"[T2I-Upscale] {idx+1}/{total}: "
                                f"reCAPTCHA check error: {e}"
                            )
                        
                        upscale_body = self._api_client.build_upscale_image_body(
                            media_id=mid,
                            project_id=account.project_id or "",
                            target_resolution=target_resolution,
                            paygate_tier=account.paygate_tier or "PAYGATE_TIER_TWO",
                        )
                        
                        timeout = getattr(account, 'request_timeout', 120)
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
                        self._burst_controller.record_success(account.email)
                        
                        upscale_data = ext_result.get('data', {})
                        encoded_image = upscale_data.get('encodedImage', '')
                        if encoded_image:
                            # Save upscaled image
                            from config.settings import get_settings
                            settings = get_settings()
                            output_folder = (
                                getattr(task, 'output_folder', '')
                                or settings.output_folder or ''
                            ).strip()
                            project_name = (
                                getattr(task, 'project_name', '') or "Untitled"
                            ).strip()
                            upscale_dir = (
                                Path(output_folder) / project_name / upscale_quality.strip()
                            )
                            upscale_dir.mkdir(parents=True, exist_ok=True)
                            
                            raw_name = Path(local_1k).name
                            filename = raw_name.replace('_1K', f'_{upscale_quality}')
                            upscale_path = upscale_dir / filename
                            img_bytes = base64.b64decode(encoded_image)
                            upscale_path.write_bytes(img_bytes)
                            
                            log.info(
                                f"[T2I-Upscale] {idx+1}/{total}: "
                                f"✅ {upscale_quality} saved "
                                f"({len(img_bytes)//1024}KB): "
                                f"{upscale_path.name}"
                            )
                            if vo:
                                vo.file_upscaled = str(upscale_path)
                                vo.quality = upscale_quality
                                vo.upscale_status = "success"
                            return str(upscale_path)
                        else:
                            log.warning(
                                f"[T2I-Upscale] {idx+1}/{total}: "
                                f"no encodedImage in response, keeping 1K"
                            )
                            if vo:
                                vo.upscale_status = "failed"
                                vo.upscale_error = "no encodedImage in response"
                                vo.quality = "1K"
                            return local_1k
                    else:
                        error = (
                            ext_result.get('error', 'unknown')
                            if ext_result else 'no response'
                        )
                        error_lower = error.lower()
                        status_code = ext_result.get('status', 0) if ext_result else 0
                        is_403 = status_code == 403 or "403" in error_lower
                        
                        log.warning(
                            f"[T2I-Upscale] {idx+1}/{total}: "
                            f"failed (attempt {attempt+1}/{max_upscale_retries}): "
                            f"{error}"
                        )
                        
                        if is_403:
                            self._burst_controller.record_error(
                                account.email, status_code or 403
                            )
                            self.set_account_cooldown(
                                account.email,
                                f"T2I upscale 403 (img {idx+1}/{total})"
                            )
                            if attempt < max_upscale_retries - 1:
                                await self.wait_for_cooldown(account.email)
                                continue
                        
                        if attempt >= max_upscale_retries - 1:
                            if vo:
                                vo.upscale_status = "failed"
                                vo.upscale_error = str(error)
                                vo.quality = "1K"
                            return local_1k
                        # Recovery delay before retry (reCAPTCHA key extraction may need time)
                        log.info(
                            f"[T2I-Upscale] {idx+1}/{total}: "
                            f"waiting 10s before retry..."
                        )
                        await asyncio.sleep(10)
                
                except asyncio.TimeoutError:
                    log.warning(
                        f"[T2I-Upscale] {idx+1}/{total}: timeout "
                        f"(attempt {attempt+1}/{max_upscale_retries})"
                    )
                    if attempt >= max_upscale_retries - 1:
                        if vo:
                            vo.upscale_status = "failed"
                            vo.upscale_error = "timeout"
                            vo.quality = "1K"
                        return local_1k
                    await asyncio.sleep(5)  # Brief delay before timeout retry
                except Exception as e:
                    log.warning(
                        f"[T2I-Upscale] {idx+1}/{total}: "
                        f"error ({e}) "
                        f"(attempt {attempt+1}/{max_upscale_retries})"
                    )
                    if attempt >= max_upscale_retries - 1:
                        if vo:
                            vo.upscale_status = "failed"
                            vo.upscale_error = str(e)
                            vo.quality = "1K"
                        return local_1k
                    await asyncio.sleep(10)  # Recovery delay before retry
            
            # Safety fallback
            if vo:
                vo.upscale_status = "failed"
                vo.upscale_error = "retry exhausted"
                vo.quality = "1K"
            return local_1k
        
        # === Launch all image upscales concurrently (limited by semaphore) ===
        try:
            upscale_tasks = [
                _upscale_one(idx, mid, local_1k)
                for idx, (mid, local_1k) in enumerate(zip(media_ids, local_paths))
            ]
            upscaled_paths = await asyncio.gather(*upscale_tasks)
            
            # Update task output_uris with upscaled paths
            task.output_uris = list(upscaled_paths)
            
            # Log quality breakdown
            actual_upscaled = sum(
                1 for vo in task.video_outputs if vo.upscale_status == "success"
            )
            actual_1k = sum(
                1 for vo in task.video_outputs
                if vo.upscale_status in ("failed", "skipped")
            )
            
            if actual_upscaled == total:
                self._dispatcher.update_progress(
                    task.id, 100,
                    f"✅ {upscale_quality} ({total} images)"
                )
                log.info(
                    f"[T2I-Upscale] Task {task.id}: ✅ ALL {total} images "
                    f"upscaled to {upscale_quality}"
                )
            else:
                self._dispatcher.update_progress(
                    task.id, 100,
                    f"⚠️ {actual_upscaled}/{total} → {upscale_quality}"
                )
                log.warning(
                    f"[T2I-Upscale] Task {task.id}: ⚠️ PARTIAL: "
                    f"{actual_upscaled}/{total} → {upscale_quality}, "
                    f"{actual_1k}/{total} kept at 1K"
                )
            
            # Trigger UI refresh for upscale completion
            if self._on_task_completed:
                try:
                    self._on_task_completed(task)
                except Exception:
                    pass
        
        except asyncio.CancelledError:
            log.warning(
                f"[T2I-Upscale] Task {task.id} cancelled"
            )
        except Exception as e:
            log.error(
                f"[T2I-Upscale] Task {task.id} error: {e}",
                exc_info=True,
            )
    
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
                    self._dispatcher.decrement_running(account.email)
                    task._counter_decremented = True  # Prevent double-decrement in complete_task
                    return
                elif task.stage == TaskStage.DOWNLOADED_720 and task.download_quality != "720p" and media_ids:
                    # BUG-18: Skip inline upscale if stop is active
                    if self._stop_event.is_set():
                        log.info(f"[Poll] Task {task.id}: stop signal — skipping resume upscale")
                        return
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
                    # ★ SPEED OPT: No fixed cooldown — children will self-wait for
                    # reCAPTCHA readiness when their foreman submits the I2V request
                    if frame_result:
                        continuation_frame_uri, continuation_frame_local = frame_result
                
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
                        error = op.get("operation", {}).get("error", {}).get("message", "Server generation failed")
                        log.warning(f"[Poll] Op {op_name[:12]}... FAILED: {error}")
                        # Track failed error for policy detection
                        if not hasattr(task, '_poll_failed_errors'):
                            task._poll_failed_errors = []
                        task._poll_failed_errors.append(error)
                    elif op_name in pending_ops:
                        # Update status for next poll
                        pending_ops[op_name]["status"] = op_status
                
                # Get current server status for progress
                server_status = response_ops[0].get("status", "") if response_ops else ""
                
                if not pending_ops:
                    # ALL operations resolved
                    if not completed_results:
                        # All failed — check for policy errors → auto-fix prompt
                        poll_errors = getattr(task, '_poll_failed_errors', [])
                        is_policy = any(self._is_policy_error(e) for e in poll_errors)
                        _fix_attempts = getattr(task, '_policy_fix_attempts', 0)
                        
                        if (is_policy
                                and getattr(self._settings, 'prompt_enhance_enabled', False)
                                and getattr(self._settings, 'prompt_auto_fix', False)
                                and _fix_attempts < 3):
                            task._policy_fix_attempts = _fix_attempts + 1
                            log.warning(
                                f"[Poll] Task {task.id}: ALL ops POLICY VIOLATION "
                                f"(fix attempt {_fix_attempts + 1}/3): {poll_errors[0]} "
                                f"— attempting auto-fix..."
                            )
                            try:
                                fixed = await self._fix_policy_prompt(
                                    task, poll_errors[0], account,
                                    attempt=_fix_attempts + 1
                                )
                                if fixed:
                                    task.prompt = fixed
                                    task._poll_failed_errors = []
                                    # ★ Strategy label for UI
                                    strategy = (
                                        "LOCAL" if _fix_attempts == 0
                                        else "API_FIX" if _fix_attempts == 1
                                        else "REGENERATE"
                                    )
                                    self._dispatcher.update_progress(
                                        task.id, task.progress,
                                        f"🔧 Auto-fixed ({_fix_attempts + 1}/3 — {strategy})"
                                    )
                                    log.info(
                                        f"[Poll] Task {task.id}: prompt auto-fixed "
                                        f"(attempt {_fix_attempts + 1}/3 — {strategy}) → requeueing"
                                    )
                                    self._dispatcher.requeue_task(task)
                                    return  # Will be retried with fixed prompt
                                else:
                                    log.warning(
                                        f"[Poll] Task {task.id}: auto-fix returned None"
                                    )
                            except Exception as fix_err:
                                log.warning(
                                    f"[Poll] Task {task.id}: auto-fix error: {fix_err}"
                                )
                        
                        error_detail = poll_errors[0] if poll_errors else "All video operations failed"
                        self._dispatcher.fail_task(task.id, error_detail)
                        emit_event(EventType.TASK_FAILED, {
                            "task_id": task.id, "error": error_detail,
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
                    
                    # G5: License usage — count on successful 720p download
                    try:
                        ctrl = getattr(self, '_app_controller', None)
                        if ctrl and hasattr(ctrl, '_license_client'):
                            ctrl._license_client.log_generation()
                            # Count downloads per actual video file, not per prompt
                            dl_count = sum(1 for p in local_720p if p)
                            for _ in range(dl_count):
                                ctrl._license_client.log_download()
                    except Exception:
                        pass
                    
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
                        
                        # Phase 3A: Always delegate upscale to background UpscaleQueue
                        if not skip_upscale:  # Bug #8: check flag instead of testing media_ids
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
                            task.stage = TaskStage.UPSCALING
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
                                    self._dispatcher.activate_children_early(
                                        task.id,
                                        frame_result[0],   # continuation_frame_uri
                                        frame_result[1],   # continuation_frame_local_path
                                    )
                            
                            # Worker exits — UpscaleQueue will call complete_task()
                            self._dispatcher.decrement_running(account.email)
                            task._counter_decremented = True  # Prevent double-decrement in complete_task
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
        # BUG-28: Skip frame extraction during stop (FFmpeg + upload = 30-60s)
        if self._stop_event.is_set():
            log.info(f"[ContinuationFrame] Task {task.id}: stop signal — skipping extraction")
            return None
        
        try:
            if not self._frame_extractor.is_available:
                log.warning("FFmpeg not available, skipping continuation frame extraction")
                return None
            
            # Update status: extracting
            task.image_upload_status = "extracting"
            self._dispatcher.update_progress(task.id, task.progress, "📸 Extracting frame...")
            
            # 1. Get video bytes: either from local file or remote FIFE URL
            import tempfile
            
            # Detect local file path vs remote URL
            # BUG FIX: After inline upscale, output_uris may contain local paths
            # (e.g. d:\Downloads\...\1080p.mp4) instead of FIFE URLs. Trying to
            # HTTP GET a local path causes aiohttp to fail → cascade-fail children.
            is_local = (
                Path(video_uri).exists()
                or video_uri.startswith('/')
                or (len(video_uri) >= 2 and video_uri[1] == ':')  # Windows drive
            )
            
            if is_local and Path(video_uri).exists():
                # Local file — read directly from disk (no HTTP download needed)
                log.info(f"[ContinuationFrame] Reading local video: {Path(video_uri).name}")
                video_path = video_uri  # Use directly, no temp file needed
            else:
                # Remote FIFE URL — download via HTTP
                import aiohttp
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
            
            # Cleanup temp video (only if we created a temp file — NOT the user's local video)
            if not is_local:
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
            
            # Fix 401: ensure valid access token before upload
            access_token = await account.ensure_valid_token()
            if not access_token:
                log.error(f"[ContinuationFrame] Token refresh failed for {account.email}")
                task.image_upload_status = "error"
                return None
            
            upload_resp = await self._api_client.upload_image(
                access_token=access_token,
                recaptcha_token="",  # HAR: upload does NOT send recaptcha
                image_base64=frame_b64,
                mime_type=frame_mime,
                account_headers=account.get_api_headers(),  # Issue 10: per-account headers
            )
            
            if upload_resp.success:
                # Multi-format mediaId extraction (API changed 2026-03)
                media_id = ""
                # Format 1: Old {mediaGenerationId: {mediaGenerationId: "..."}}
                mgid = upload_resp.data.get("mediaGenerationId")
                if mgid:
                    if isinstance(mgid, dict):
                        media_id = mgid.get("mediaGenerationId", "")
                    elif isinstance(mgid, str):
                        media_id = mgid
                # Format 2: New {media: {name: "uuid", ...}, workflow: ...}
                if not media_id:
                    media = upload_resp.data.get("media")
                    if isinstance(media, dict):
                        media_id = media.get("name", "") or media.get("mediaGenerationId", "") or media.get("mediaId", "")
                    elif isinstance(media, list) and media:
                        first = media[0]
                        if isinstance(first, dict):
                            media_id = first.get("name", "") or first.get("mediaGenerationId", "") or first.get("mediaId", "")
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
                # Multi-format mediaId extraction (API changed 2026-03)
                media_id = ""
                mgid = upload_resp.data.get("mediaGenerationId")
                if mgid:
                    media_id = mgid.get("mediaGenerationId", "") if isinstance(mgid, dict) else mgid
                if not media_id:
                    media = upload_resp.data.get("media")
                    if isinstance(media, dict):
                        media_id = media.get("name", "") or media.get("mediaGenerationId", "") or media.get("mediaId", "")
                    elif isinstance(media, list) and media:
                        first = media[0]
                        if isinstance(first, dict):
                            media_id = first.get("name", "") or first.get("mediaGenerationId", "") or first.get("mediaId", "")
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
    
    def clear_upload_cache(self, max_size: int = 0):
        """Clear the upload cache, or prune if max_size > 0.
        
        Args:
            max_size: If > 0, only prune when cache exceeds this size (keeps newest half).
                      If 0, clear everything.
        """
        if max_size > 0:
            if len(self._upload_cache) <= max_size:
                return  # Within limits
            # Evict oldest half (dict preserves insertion order in Python 3.7+)
            keys = list(self._upload_cache.keys())
            for k in keys[:len(keys) // 2]:
                del self._upload_cache[k]
            log.debug(f"[Engine] Upload cache pruned to {len(self._upload_cache)} entries")
        else:
            self._upload_cache.clear()
            log.debug("[Engine] Upload cache cleared")
    
    async def _wait_for_recaptcha_ready(
        self, account: AccountManager, max_wait: float = 30.0
    ) -> bool:
        """Layer 2: Wait until Extension confirms grecaptcha is ready.
        
        Serialized per account: only one foreman does recovery at a time.
        Others wait for the lock, then benefit from the 3s dedup cache.
        """
        email = account.email
        if email not in self._recaptcha_recovery_locks:
            self._recaptcha_recovery_locks[email] = asyncio.Lock()
        
        lock = self._recaptcha_recovery_locks[email]
        if lock.locked():
            # Another foreman is already recovering — wait for it
            log.info(
                f"[Foreman:{email}] reCAPTCHA recovery already in progress "
                f"by another foreman — waiting for lock..."
            )
            async with lock:
                # Recovery done — check if recaptcha is now ready via cache
                bridge = account.extension_bridge
                if bridge:
                    try:
                        return await bridge.check_recaptcha_ready(email, timeout=5.0)
                    except Exception:
                        return False
                return False
        
        async with lock:
            return await self._do_wait_for_recaptcha_ready(account, max_wait)
    
    async def _do_wait_for_recaptcha_ready(
        self, account: AccountManager, max_wait: float = 30.0
    ) -> bool:
        """Internal: actual reCAPTCHA readiness wait + recovery logic."""
        bridge = account.extension_bridge
        if not bridge:
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

        # ★ Tab-dead bail-out: if tab was declared dead, don't even start recovery
        if bridge.is_tab_dead(account.email):
            log.warning(
                f"[Foreman:{account.email}] 💀 Tab declared dead — skipping reCAPTCHA recovery "
                f"(waiting for browser restart from AppController)"
            )
            return False
        
        start = asyncio.get_event_loop().time()
        interval = 2.0
        attempt = 0
        
        while (asyncio.get_event_loop().time() - start) < max_wait:
            # BUG-34: Exit immediately on stop
            if self._stop_event.is_set():
                return False
            
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
                # ★ Tab-dead check inside loop — bail immediately if declared dead mid-wait
                if bridge.is_tab_dead(account.email):
                    log.warning(
                        f"[Foreman:{account.email}] 💀 Tab declared dead during reCAPTCHA wait — aborting recovery"
                    )
                    return False
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
        # BUG-34: Skip reload + 25s wait during stop
        if self._stop_event.is_set():
            return False
        
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
                
                # ★ ESCALATION: Hard navigate to VEO URL (nuclear recovery)
                # refresh_headers() only refreshes XHR — doesn't reload the page.
                # When reCAPTCHA widget is stuck (538-char garbage token),
                # only a FULL PAGE NAVIGATION forces Chrome to re-download
                # and re-initialize grecaptcha Enterprise.
                if not self._stop_event.is_set():
                    log.warning(
                        f"[Foreman:{account.email}] 🔄 Escalating to HARD NAVIGATION "
                        f"(full page reload failed — forcing VEO URL navigation)"
                    )
                    try:
                        nav_ok = await bridge.trigger_hard_navigation(account.email)
                        if nav_ok:
                            # Wait for reCAPTCHA widget to initialize after navigation
                            nav_wait = 20.0
                            log.info(
                                f"[Foreman:{account.email}] ⏳ Waiting {nav_wait:.0f}s "
                                f"for reCAPTCHA widget after hard navigation..."
                            )
                            await asyncio.sleep(nav_wait)
                            
                            # Verify widget is ready after navigation
                            for nav_verify in range(3):
                                try:
                                    nav_ready = await bridge.check_recaptcha_ready(
                                        account.email, timeout=8.0
                                    )
                                    if nav_ready:
                                        log.info(
                                            f"[Foreman:{account.email}] ✅ reCAPTCHA recovered "
                                            f"after hard navigation (verify #{nav_verify + 1})"
                                        )
                                        self._account_recovery_phase[account.email] = 0
                                        self._account_phase_403_count[account.email] = 0
                                        return True
                                except Exception:
                                    pass
                                if nav_verify < 2:
                                    await asyncio.sleep(3.0)
                            
                            log.warning(
                                f"[Foreman:{account.email}] ⚠️ reCAPTCHA still dead "
                                f"after hard navigation + {nav_wait:.0f}s + 3 verify attempts"
                            )
                        
                        # ★ Tab-dead bail-out after hard navigation fails
                        # AppController._on_tab_dead handles browser restart.
                        if bridge.is_tab_dead(account.email):
                            log.error(
                                f"[Foreman:{account.email}] 💀 Tab confirmed dead after hard nav failure — "
                                f"aborting recovery (AppController will restart browser)"
                            )
                            return False
                    except Exception as e:
                        log.error(
                            f"[Foreman:{account.email}] Hard navigation error: {e}"
                        )
            except Exception as e:
                log.debug(f"[Foreman:{account.email}] Recovery reload failed: {e}")
        
        return False
    
    async def _pre_upload_all_images(self, account: AccountManager):
        """Pre-upload ALL unique images for this account before task processing.
        
        ★ Fix A: Expanded from R2V-only to ALL image workflows (I2V + R2V).
        Google upload API has no rate limit → uploads run fully parallel
        via asyncio.gather() for maximum throughput.
        
        Scans all pending tasks with image_paths, collects unique paths
        not yet in upload_cache or ImageLibrary, and uploads them once.
        
        Cache key = {path}:{email} — each account uploads its own copy.
        Cross-account mediaIds are never shared (asset permission isolation).
        Results stored in BOTH _upload_cache (in-memory) AND ImageLibrary
        media_ids (persistent across sessions).
        
        Called once per supervisor after readiness gate, before foremen start.
        Subsequent tasks will hit cache → skip upload → save ~5-10s/image/task.
        """
        import time as _time
        import hashlib as _hashlib
        
        # ── Phase 1: Collect unique image paths from ALL pending tasks ──
        unique_paths = set()
        all_tasks = self._dispatcher.get_all_tasks_dict()
        
        # Check ImageLibrary persistent cache too
        try:
            from services.image_library import get_image_library
            lib = get_image_library()
        except Exception:
            lib = None
        
        for task in all_tasks.values():
            if (task.image_paths
                    and task.state.value in ('ready', 'pending')):
                for p in task.image_paths:
                    cache_key = f"{p}:{account.email}"
                    if cache_key in self._upload_cache:
                        continue  # Already in in-memory cache
                    # Check ImageLibrary persistent cache
                    if lib:
                        lib_id = await asyncio.to_thread(lib.get_media_id, p, account.email)
                        if lib_id:
                            # Populate in-memory cache from ImageLibrary
                            self._upload_cache[cache_key] = lib_id
                            continue
                    unique_paths.add(p)
        
        if not unique_paths:
            return
        
        log.info(
            f"[PreUpload:{account.email}] "
            f"Uploading {len(unique_paths)} unique image(s) for all workflows (parallel)"
        )
        t0 = _time.monotonic()
        uploaded = 0
        
        # ── Phase 2: Upload images with bounded concurrency ──
        # Semaphore prevents loading ALL images into RAM at once (OOM/not-responding)
        _sem = asyncio.Semaphore(10)  # Max 10 parallel uploads
        
        async def _upload_one(path: str) -> bool:
            """Upload a single image, return True on success."""
            nonlocal uploaded
            if self._stop_event.is_set():
                return False
            try:
                async with _sem:
                    # Fresh token for each upload (catches mid-batch refreshes)
                    access_token = await account.ensure_valid_token()
                    if not access_token:
                        log.error(f"[PreUpload:{account.email}] Token failed — skipping {Path(path).name}")
                        return False
                    
                    # Encode image — run in thread to avoid blocking event loop
                    from core.media_handler import MediaHandler
                    result = await asyncio.to_thread(MediaHandler.image_to_base64, path)
                    if not result:
                        log.error(f"[PreUpload] Failed to encode: {path}")
                        return False
                    img_b64, mime_type = result
                
                    # Compute content hash in thread (avoid blocking event loop)
                    try:
                        def _hash_file(p):
                            h = _hashlib.md5()
                            with open(p, 'rb') as f:
                                for chunk in iter(lambda: f.read(8192), b''):
                                    h.update(chunk)
                            return h.hexdigest()
                        content_hash = await asyncio.to_thread(_hash_file, path)
                    except Exception:
                        content_hash = ""
                
                    # Upload with 429 retry + exponential backoff
                    for _attempt in range(3):
                        if self._stop_event.is_set():
                            return False
                        
                        upload_resp = await self._api_client.upload_image(
                            access_token=access_token,
                            recaptcha_token="",
                            image_base64=img_b64,
                            mime_type=mime_type,
                            account_headers=account.get_api_headers(),
                        )
                    
                        if upload_resp.success:
                            # Multi-format mediaId extraction (API changed 2026-03)
                            media_id = ""
                            mgid = upload_resp.data.get("mediaGenerationId")
                            if mgid:
                                media_id = mgid.get("mediaGenerationId", "") if isinstance(mgid, dict) else mgid
                            if not media_id:
                                media = upload_resp.data.get("media")
                                if isinstance(media, dict):
                                    media_id = media.get("name", "") or media.get("mediaGenerationId", "") or media.get("mediaId", "")
                                elif isinstance(media, list) and media:
                                    first = media[0]
                                    if isinstance(first, dict):
                                        media_id = first.get("name", "") or first.get("mediaGenerationId", "") or first.get("mediaId", "")
                            if media_id:
                                # Store in in-memory cache (path + hash keys)
                                cache_key = f"{path}:{account.email}"
                                async with self._upload_cache_lock:
                                    self._upload_cache[cache_key] = media_id
                                    if content_hash:
                                        self._upload_cache[f"hash:{content_hash}:{account.email}"] = media_id
                                # Store in ImageLibrary — use path-only match to avoid
                                # _compute_hash re-reading the file (we already have the hash)
                                if lib:
                                    try:
                                        for img in lib._images:
                                            if img.path == path or (content_hash and img.content_hash == content_hash):
                                                img.media_ids[account.email] = media_id
                                                break
                                    except Exception:
                                        pass
                                uploaded += 1
                                log.info(f"[PreUpload]   {Path(path).name} → {media_id[:40]}...")
                                return True
                            else:
                                log.warning(f"[PreUpload]   Upload OK but no mediaId: {path}")
                                break  # Success but no ID — don't retry
                        else:
                            err_str = str(upload_resp.error)
                            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                wait = (2 ** _attempt) * 5  # 5s, 10s, 20s
                                log.warning(
                                    f"[PreUpload] 429 on {Path(path).name} → "
                                    f"retry {_attempt+1}/3 in {wait}s"
                                )
                                await asyncio.sleep(wait)
                                continue
                            else:
                                log.error(f"[PreUpload]   Upload failed: {path}: {upload_resp.error}")
                                break  # Non-429 error — don't retry
            except Exception as e:
                log.error(f"[PreUpload]   Error uploading {path}: {e}")
            return False
        
        # Launch all uploads in parallel — no limit
        await asyncio.gather(
            *[_upload_one(p) for p in sorted(unique_paths)],
            return_exceptions=True,
        )
        
        elapsed = _time.monotonic() - t0
        log.info(
            f"[PreUpload:{account.email}] "
            f"Done: {uploaded}/{len(unique_paths)} uploaded in {elapsed:.1f}s (parallel)"
        )
        
        # Persist ImageLibrary index so mediaIds survive restart
        # (engine writes directly to img.media_ids but never called _save_index)
        if lib and uploaded > 0:
            try:
                lib._save_index()
                log.info(f"[PreUpload:{account.email}] ImageLibrary index saved ({uploaded} new mediaIds)")
            except Exception as _e:
                log.warning(f"[PreUpload:{account.email}] ImageLibrary save failed: {_e}")
    
    async def _check_all_images_cached(self, task: 'Task', account: 'AccountManager') -> bool:
        """Pre-check if ALL image paths for a task have cache hits.
        
        Checks 3 layers (same as _resolve_image_paths._upload_single):
        1. In-memory path cache: {path}:{email}
        2. In-memory hash cache: hash:{md5}:{email}  
        3. ImageLibrary persistent cache
        
        Returns True if no API upload is needed → caller can skip rate lock.
        This is a LIGHTWEIGHT check — no actual uploads happen.
        """
        import hashlib
        
        for path in (task.image_paths or []):
            # Layer 1: path-based cache (instant)
            path_key = f"{path}:{account.email}"
            async with self._upload_cache_lock:
                if self._upload_cache.get(path_key):
                    continue
            
            # Layer 2: content-hash cache (needs file read)
            try:
                loop = asyncio.get_running_loop()
                def _compute_md5(p):
                    try:
                        h = hashlib.md5()
                        with open(p, 'rb') as f:
                            for chunk in iter(lambda: f.read(8192), b''):
                                h.update(chunk)
                        return h.hexdigest()
                    except Exception:
                        return ""
                content_hash = await loop.run_in_executor(None, _compute_md5, path)
                if content_hash:
                    cache_key = f"hash:{content_hash}:{account.email}"
                    async with self._upload_cache_lock:
                        if self._upload_cache.get(cache_key):
                            continue
            except Exception:
                pass
            
            # Layer 3: ImageLibrary persistent cache
            try:
                from services.image_library import get_image_library
                _lib = get_image_library()
                lib_id = await asyncio.to_thread(_lib.get_media_id, path, account.email)
                if lib_id:
                    # Populate in-memory cache for faster subsequent lookups
                    async with self._upload_cache_lock:
                        self._upload_cache[path_key] = lib_id
                    continue
            except Exception:
                pass
            
            # No cache hit found for this image → real upload needed
            return False
        
        return True  # All images cached
    
    async def _resolve_image_paths(self, task: Task, account: AccountManager):
        """Upload local image files to get mediaGenerationIds.
        
        Called when task.image_paths has been populated by tag resolution
        in AppController but task.image_uris is still empty.
        
        ★ V2 UPGRADE:
        - Per-image slots (ImageUploadSlot) with individual status/retry
        - Content hash dedup (MD5) — different paths, same content → skip upload
        - Per-image retry (3 attempts with exponential backoff)
        - Parallel upload via asyncio.gather()
        """
        import hashlib
        from core.dispatcher import ImageUploadSlot
        
        MAX_RETRIES = 3
        n_images = len(task.image_paths)
        log.info(f"Uploading {n_images} image(s) for task {task.id} (parallel, v2)")
        task.image_upload_status = "uploading"
        self._dispatcher.update_progress(task.id, task.progress, "📤 Uploading images...")
        
        # Initialize per-image slots
        slots = []
        for path in task.image_paths:
            slots.append(ImageUploadSlot(path=path))
        task.image_slots = slots
        
        def _compute_hash(path: str) -> str:
            """Compute MD5 hash of file content for dedup."""
            try:
                h = hashlib.md5()
                with open(path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        h.update(chunk)
                return h.hexdigest()
            except Exception:
                return ""
        
        async def _upload_single(slot: ImageUploadSlot) -> str:
            """Upload a single image with retry, returning mediaId or empty string."""
            # BUG-33: Skip during stop
            if self._stop_event.is_set():
                slot.status = "error"
                slot.error = "stopped"
                return ""
            
            slot.status = "uploading"
            
            # Compute content hash for dedup (CPU-bound, run in thread)
            if not slot.content_hash:
                loop = asyncio.get_running_loop()
                slot.content_hash = await loop.run_in_executor(
                    None, _compute_hash, slot.path
                )
            
            # Content hash cache check — same content + same account = reuse mediaId
            if slot.content_hash:
                cache_key = f"hash:{slot.content_hash}:{account.email}"
                async with self._upload_cache_lock:
                    cached_id = self._upload_cache.get(cache_key)
                if cached_id:
                    slot.media_id = cached_id
                    slot.status = "ready"
                    log.info(f"  Hash match: {Path(slot.path).name} → {cached_id} (skip upload)")
                    return cached_id
            
            # Also check path-based cache (backward compat)
            path_cache_key = f"{slot.path}:{account.email}"
            async with self._upload_cache_lock:
                cached_id = self._upload_cache.get(path_cache_key)
            if cached_id:
                slot.media_id = cached_id
                slot.status = "ready"
                log.info(f"  Path hit: {Path(slot.path).name} → {cached_id} (skip upload)")
                return cached_id
            
            # ★ Fix B: Check ImageLibrary persistent cache
            try:
                from services.image_library import get_image_library
                _lib = get_image_library()
                lib_id = await asyncio.to_thread(_lib.get_media_id, slot.path, account.email)
                if lib_id:
                    slot.media_id = lib_id
                    slot.status = "ready"
                    # Populate in-memory cache for subsequent lookups
                    async with self._upload_cache_lock:
                        self._upload_cache[path_cache_key] = lib_id
                        if slot.content_hash:
                            self._upload_cache[f"hash:{slot.content_hash}:{account.email}"] = lib_id
                    log.info(f"  Library hit: {Path(slot.path).name} → {lib_id} (skip upload)")
                    return lib_id
            except Exception:
                pass
            
            # Encode image in thread (once, reuse across retries)
            from core.media_handler import MediaHandler
            result = await asyncio.to_thread(MediaHandler.image_to_base64, slot.path)
            if not result:
                slot.status = "error"
                slot.error = "encode_failed"
                log.error(f"  Failed to encode image: {slot.path}")
                return ""
            img_b64, mime_type = result
            
            # Retry loop for upload
            for attempt in range(1, MAX_RETRIES + 1):
                if self._stop_event.is_set():
                    slot.status = "error"
                    slot.error = "stopped"
                    return ""
                
                # ★ FIX: Re-fetch token on EACH retry (catches mid-retry refreshes)
                # Previously fetched once before loop → stale token on retry 2/3
                access_token = await account.ensure_valid_token()
                if not access_token:
                    slot.status = "error"
                    slot.error = "auth_failed"
                    log.error(f"  Token refresh failed for {account.email} — skipping {Path(slot.path).name}")
                    return ""
                
                slot.retry_count = attempt
                try:
                    upload_resp = await self._api_client.upload_image(
                        access_token=access_token,
                        recaptcha_token="",
                        image_base64=img_b64,
                        mime_type=mime_type,
                        account_headers=account.get_api_headers(),
                    )
                    
                    if upload_resp.success:
                        # Multi-format mediaId extraction (API changed 2026-03)
                        media_id = ""
                        mgid = upload_resp.data.get("mediaGenerationId")
                        if mgid:
                            media_id = mgid.get("mediaGenerationId", "") if isinstance(mgid, dict) else mgid
                        if not media_id:
                            media = upload_resp.data.get("media")
                            if isinstance(media, dict):
                                media_id = media.get("name", "") or media.get("mediaGenerationId", "") or media.get("mediaId", "")
                            elif isinstance(media, list) and media:
                                first = media[0]
                                if isinstance(first, dict):
                                    media_id = first.get("name", "") or first.get("mediaGenerationId", "") or first.get("mediaId", "")
                        if media_id:
                            slot.media_id = media_id
                            slot.status = "ready"
                            # Cache by both content hash and path
                            async with self._upload_cache_lock:
                                if slot.content_hash:
                                    self._upload_cache[f"hash:{slot.content_hash}:{account.email}"] = media_id
                                self._upload_cache[path_cache_key] = media_id
                            log.info(f"  Uploaded: {Path(slot.path).name} → {media_id} (attempt {attempt})")
                            return media_id
                        else:
                            slot.error = "no_media_id"
                            log.warning(f"  Upload OK but no mediaId for {slot.path} (attempt {attempt})")
                    else:
                        slot.error = upload_resp.error or "upload_failed"
                        log.warning(f"  Upload failed for {Path(slot.path).name}: {slot.error} (attempt {attempt}/{MAX_RETRIES})")
                        # ★ FIX 401: Force token refresh by invalidating local TTL
                        # ensure_valid_token() uses is_token_expired which checks local datetime.
                        # If server rejects token (expired/revoked early), local TTL is still valid
                        # → same stale token returned on retry. Invalidating forces refresh.
                        if upload_resp.response_code == 401:
                            log.warning(f"  🔑 401 UNAUTHENTICATED — invalidating token for {account.email}")
                            account._session.token_expires = None
                except Exception as e:
                    slot.error = str(e)
                    log.warning(f"  Upload error for {Path(slot.path).name}: {e} (attempt {attempt}/{MAX_RETRIES})")
                
                # Exponential backoff before next retry
                if attempt < MAX_RETRIES:
                    backoff = 2 ** (attempt - 1)  # 1s, 2s
                    await asyncio.sleep(backoff)
            
            # All retries exhausted
            slot.status = "error"
            log.error(f"  Upload FAILED after {MAX_RETRIES} attempts: {Path(slot.path).name} — {slot.error}")
            return ""
        
        # ★ Launch all uploads in parallel
        results = await asyncio.gather(
            *[_upload_single(s) for s in slots],
            return_exceptions=True,
        )
        
        # Collect successful mediaIds (preserve order)
        uploaded_uris = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                slots[i].status = "error"
                slots[i].error = str(r)
                log.error(f"  Image upload exception for {slots[i].path}: {r}")
            elif r:
                uploaded_uris.append(r)
        
        ok = sum(1 for s in slots if s.status == "ready")
        fail = sum(1 for s in slots if s.status == "error")
        
        if uploaded_uris:
            task.image_uris = uploaded_uris
            task.image_uris_account = account.email  # Track which account owns these mediaIds
            task.image_upload_status = "ready"
            log.info(f"  ✅ {ok}/{n_images} uploaded, {fail} failed (parallel v2)")
        else:
            task.image_upload_status = "error"
            log.error(f"  ❌ All {n_images} image(s) failed to upload")
    
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
        # BUG-29: Don't create retry tasks during stop (zombie tasks)
        if self._stop_event.is_set():
            log.info(f"[AutoRetry] Task {original_task.id}: stop active — skipping partial retry")
            return
        
        import uuid
        
        # Extract original failed video indices from results
        failed_indices = []
        for r in [r for r in (getattr(original_task, '_last_results_dict', {}) or {}).values() if r.quality == 'failed']:
            failed_indices.append(r.index)
        if not failed_indices:
            # Fallback: compute from total - success count
            total = getattr(original_task, 'output_count', 4) or 4
            success_indices = set()
            for vo in original_task.video_outputs:
                if vo.quality != 'failed':
                    success_indices.add(vo.index)
            failed_indices = [i for i in range(total) if i not in success_indices]
        
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
            retry_original_indices=failed_indices,  # Preserve original indices for variant letter naming
        )
        # Pin to same account — reuse project_id, same image_uris (account-bound)
        retry_task.required_account = original_task.assigned_account
        
        submitted = self._dispatcher.submit_task(retry_task)
        if submitted:
            log.info(
                f"🔄 Auto-retry submitted: {retry_id} "
                f"(output_count={failed_count}, "
                f"original_indices={failed_indices}, "
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
        # BUG-30: Don't create retry tasks during stop
        if self._stop_event.is_set():
            log.info(f"[AutoRetry] Task {original_task.id}: stop active — skipping download retry")
            return
        
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
            # BUG-14: Exit loop immediately on stop (upscale can take minutes)
            if self._stop_event.is_set():
                log.info(f"Upscale: stop signal — aborting at video {idx+1}/{total}")
                break
            
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
                    # BUG-14: Stop check in inner retry loop
                    if self._stop_event.is_set():
                        break
                    # BUG-A: Circuit breaker check — skip upscale retries
                    # when account is suspended (guaranteed 403)
                    if self._circuit_state.get(account.email, 'closed') == 'open':
                        log.warning(
                            f"Upscale {video_label}: circuit breaker OPEN "
                            f"for {account.email} — skipping retries"
                        )
                        break
                    # Risk 5 fix: Rate-limit upscale submits per account (prevents burst)
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Semaphore(3)
                    # ── Pre-Submit Gate: validate before standalone upscale ──
                    _gate_ok = await self._pre_submit_gate(account, task, attempt)
                    if not _gate_ok:
                        log.warning(
                            f"Upscale {video_label}: PreSubmitGate failed — skipping"
                        )
                        break
                    async with self._account_rate_locks[account.email]:
                        # Fix G7: Skip burst controller for upscale submits —
                        # upscale is a follow-up action, not a new generation.
                        # Only apply a short 1s cooldown to avoid API spam.
                        await asyncio.sleep(1.0)
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
                                project_id=getattr(account, 'project_id', '') or task.project_id or "",
                                paygate_tier=getattr(account, 'paygate_tier', '') or "PAYGATE_TIER_TWO",
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
                                    project_id=getattr(account, 'project_id', '') or task.project_id or "",
                                    target_resolution=resolution,
                                    aspect_ratio=task.aspect_ratio,
                                    seed=generate_random_seed(),
                                    paygate_tier=getattr(account, 'paygate_tier', '') or "PAYGATE_TIER_TWO",
                                    account_headers=account.get_api_headers(),
                                )
                        
                        # Risk 6 fix: reCAPTCHA cooldown after submit
                        # For Extension path: no-op (Extension manages its own reCAPTCHA)
                        account.invalidate_recaptcha()
                        await asyncio.sleep(1.0)
                    # Rate lock released
                    
                    if resp.success:
                        break
                    
                    error_msg_raw = resp.error or ""
                    error_lower = error_msg_raw.lower()
                    
                    # ★ FIX: HTTP 409 "entity already exists" = server already accepted
                    # the upscale. Don't retry — skip to poll phase directly.
                    if "already exists" in error_lower or "409" in error_msg_raw:
                        log.info(
                            f"Upscale {video_label}: HTTP 409 — entity already exists. "
                            f"Server accepted upscale, skipping to poll."
                        )
                        # Mark resp as "success" so we fall through to poll
                        resp.success = True
                        break
                    
                    log.warning(
                        f"Upscale {video_label} submit attempt {attempt + 1}/{max_submit_retries} "
                        f"failed: {error_msg_raw}"
                    )
                    
                    # ★ FIX: Check circuit breaker + extension health before retry
                    # Prevents wasting retries when extension is disconnected
                    ext_bridge = getattr(account, 'extension_bridge', None)
                    if ext_bridge and not ext_bridge.is_connected(account.email):
                        log.warning(
                            f"Upscale {video_label}: extension disconnected — "
                            f"aborting retries (keeping 720p)"
                        )
                        break
                    
                    # Tiered browser recovery on reCAPTCHA failures (same as worker)
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
                                    # BUG-D: Extension-only accounts have no browser
                                    # → reload VEO tab via Extension bridge instead
                                    _ext = getattr(account, 'extension_bridge', None)
                                    if _ext and _ext.is_connected(account.email):
                                        log.info(f"🔄 Upscale: Trying Extension tab reload for {account.email}")
                                        try:
                                            await _ext.send_and_wait(
                                                {'action': 'reload_tab', 'email': account.email},
                                                timeout=15.0,
                                            )
                                            await asyncio.sleep(3.0)  # Wait for page reload
                                            log.info(f"✅ Upscale: Extension tab reloaded")
                                        except Exception:
                                            log.warning(f"⚠️ Upscale: Extension tab reload failed")
                                    else:
                                        log.warning(f"⚠️ Upscale: No recovery path available")
                            except Exception as soft_err:
                                log.error(f"❌ Upscale soft recovery failed: {soft_err}")
                                
                        elif attempt >= 2:
                            # Tier 2: Extended soft recovery (no browser kill — preserves sessions)
                            log.warning(
                                f"🔄 Upscale {video_label}: reCAPTCHA failed {attempt + 1}x. "
                                f"Extended soft recovery (no kill)..."
                            )
                            try:
                                soft_ok = await account.soft_recover_browser()
                                if soft_ok:
                                    log.info(f"✅ Upscale: Soft recovery OK for {account.email}. Retrying...")
                                else:
                                    log.warning(f"⚠️ Upscale: Soft recovery returned False for {account.email}")
                                # Simulate activity to rebuild trust score
                                _ext = getattr(account, 'extension_bridge', None)
                                if _ext and _ext.is_connected(account.email):
                                    try:
                                        await _ext.simulate_activity(account.email, timeout=3.0)
                                    except Exception:
                                        pass
                                # Longer cooldown to let reCAPTCHA reset
                                await asyncio.sleep(15)
                            except Exception as soft_err:
                                log.error(f"❌ Upscale soft recovery failed: {soft_err}")
                    
                    if attempt < max_submit_retries - 1:
                        # ★ FIX: Check stop event before delay
                        if self._stop_event.is_set():
                            break
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
                    # Risk 5+6 fix: Rate semaphore + cooldown for re-submit
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Semaphore(3)
                    # ── Pre-Submit Gate: validate before standalone upscale re-submit ──
                    _gate_ok = await self._pre_submit_gate(account, task)
                    if not _gate_ok:
                        log.warning(f"Upscale re-submit: PreSubmitGate failed — skipping")
                        break
                    async with self._account_rate_locks[account.email]:
                        # Fix G7: Skip burst controller for upscale re-submit
                        await asyncio.sleep(1.0)
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
                                project_id=getattr(account, 'project_id', '') or task.project_id or "",
                                paygate_tier=getattr(account, 'paygate_tier', '') or "PAYGATE_TIER_TWO",
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
                                    project_id=getattr(account, 'project_id', '') or task.project_id or "",
                                    target_resolution=resolution,
                                    aspect_ratio=task.aspect_ratio,
                                    seed=generate_random_seed(),
                                    paygate_tier=getattr(account, 'paygate_tier', '') or "PAYGATE_TIER_TWO",
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
                        # ★ FIX: Handle 409 on re-submit (entity already exists)
                        resp2_err = (resp2.error or "").lower()
                        if "already exists" in resp2_err or "409" in (resp2.error or ""):
                            log.info(
                                f"Upscale {video_label}: re-submit got 409 — "
                                f"entity already exists (original upscale may have succeeded)"
                            )
                            # Can't poll without op_name — mark as needs-check
                            if idx < len(task.video_outputs):
                                task.video_outputs[idx].upscale_status = "409_conflict"
                        elif idx < len(task.video_outputs):
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
            # BUG-21: Exit poll loop on stop (prevents 30-min block)
            if self._stop_event.is_set():
                log.info(f"Upscale {video_label}: stop signal — aborting poll")
                return []
            
            # Risk 2 fix: Progressive poll interval for upscale
            # Poll 0: wait 30s — server needs processing time
            # Poll 1+: 5-8s — quickly catch completion
            jitter = random.uniform(0, 2.0)
            if poll_num == 0:
                await asyncio.sleep(30 + jitter)
            else:
                await asyncio.sleep(5 + jitter)
            
            # Progress: map to 88-90% range
            progress = min(90, 88 + int(poll_num * 0.5))
            self._dispatcher.update_progress(
                task.id, progress,
                f"⬆️ Upscaling {video_label}"
            )
            
            # ★ Proactive token refresh: every 10 polls (~50-80s) to prevent
            # token expiry during long polling (access tokens valid ~60min).
            if poll_num > 0 and poll_num % 10 == 0:
                try:
                    await account.ensure_valid_token()
                except Exception:
                    pass  # Best-effort — poll will continue with current token
            
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
                # ★ Token might have expired — refresh and retry
                try:
                    await account.ensure_valid_token()
                except Exception:
                    pass
                continue  # Retry next poll with (possibly) refreshed token
            
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
        
        # Fallback: rebuild upscale_media_ids from video_outputs if missing/all-empty
        if (not task.upscale_media_ids or not any(task.upscale_media_ids)) and task.video_outputs:
            rebuilt = [vo.media_id or "" for vo in task.video_outputs]
            if any(rebuilt):
                task.upscale_media_ids = rebuilt
                valid_count = sum(1 for m in rebuilt if m)
                log.info(f"Re-upscale {task_id}: rebuilt media_ids from video_outputs ({valid_count}/{len(rebuilt)} valid)")
        
        # Diagnostic: log upscale_media_ids state for debugging
        if task.upscale_media_ids:
            _diag = [(i, bool(mid)) for i, mid in enumerate(task.upscale_media_ids)]
            log.info(f"Re-upscale {task_id}: upscale_media_ids state = {_diag}")
        if task.video_outputs:
            _vo_diag = [(vo.index, vo.quality, vo.upscale_status, bool(vo.media_id), bool(vo.file_upscaled)) for vo in task.video_outputs]
            log.info(f"Re-upscale {task_id}: video_outputs state = {_vo_diag}")
        
        if not task.upscale_media_ids and not any(vo.media_id for vo in (task.video_outputs or [])):
            log.warning(f"Re-upscale {task_id}: no media_ids (upscale_media_ids and video_outputs both empty)")
            return False
        
        # Determine which videos need re-upscale
        failed_indices = []
        if task.video_outputs:
            if failed_only:
                failed_indices = [
                    vo.index for vo in task.video_outputs
                    if (
                        vo.upscale_status in ("failed", "skipped", "", "pending")
                        and not vo.file_upscaled
                    )
                ]
                log.info(f"Re-upscale {task_id}: failed_indices = {failed_indices}")
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
        media_ids = []
        for i in failed_indices:
            mid = ""
            # Primary: from upscale_media_ids
            if task.upscale_media_ids and i < len(task.upscale_media_ids):
                mid = task.upscale_media_ids[i] or ""
            # Fallback: from video_outputs[i].media_id
            if not mid and task.video_outputs and i < len(task.video_outputs):
                mid = task.video_outputs[i].media_id or ""
                if mid:
                    log.info(f"Re-upscale {task_id}: V{i} using fallback media_id from video_outputs")
            media_ids.append(mid)
        
        log.info(f"Re-upscale {task_id}: media_ids validity = {[(i, bool(m)) for i, m in zip(failed_indices, media_ids)]}")
        
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
        video_index: int = -1,
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
                generate_thumbnails, overwrite_paths,
                video_index=video_index,
            )
    
    async def _download_outputs_inner(
        self, task: Task, output_uris: list,
        quality_subfolder: str = "",
        generate_thumbnails: bool = True,
        overwrite_paths: list = None,
        video_index: int = -1,
    ) -> list:
        """Actual download implementation (called under per-task lock)."""
        from config.settings import get_settings
        settings = get_settings()
        
        # Prefer task-level output_folder (from sidebar), fallback to global settings
        output_folder = (getattr(task, 'output_folder', '') or settings.output_folder or '').strip()
        if not output_folder:
            log.debug("No output_folder configured, skipping download")
            return []
        
        # Create project subfolder + quality subfolder
        # Strip trailing/leading spaces — Windows cannot handle trailing-space dirs
        project_name = (getattr(task, 'project_name', '') or "Untitled").strip()
        if quality_subfolder:
            output_path = Path(output_folder) / project_name / quality_subfolder.strip()
        else:
            output_path = Path(output_folder) / project_name
        
        # Ensure directory exists (explicit str() for Windows Unicode path safety)
        import os
        os.makedirs(str(output_path), exist_ok=True)
        
        local_paths = []
        import aiohttp
        from datetime import datetime
        
        # Global prompt index (1-based, 3-digit padded)
        prompt_num = getattr(task, 'prompt_index', 0) + 1
        idx_str = str(prompt_num).zfill(3)
        
        # Variant suffixes for multi-output
        variant_letters = "abcdefghijklmnopqrstuvwxyz"
        # Multi-output: either batch download (len>1) or single worker with output_count>1
        task_output_count = getattr(task, 'output_count', 1) or 1
        is_multi = len(output_uris) > 1 or task_output_count > 1
        
        # ★ DEBUG: Trace naming logic
        log.debug(
            f"[Download-Naming] Task {task.id}: "
            f"prompt_idx={idx_str}, output_count={task_output_count}, "
            f"uris={len(output_uris)}, is_multi={is_multi}, "
            f"video_index={video_index}"
        )
        
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
                        # Use video_index (from worker) if provided, otherwise loop index
                        variant_idx = video_index if video_index >= 0 else i
                        if is_multi and variant_idx < len(variant_letters):
                            parts.append(f"{idx_str}{variant_letters[variant_idx]}")
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
                        
                        # ★ DEBUG: Trace per-file naming
                        log.debug(
                            f"[Download-Naming] Task {task.id} uri[{i}]: "
                            f"variant_idx={variant_idx}, is_multi={is_multi}, "
                            f"parts={parts} → {filename}"
                        )
                        
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
                        # BUG-04: Exit retry loop immediately on engine stop
                        if self._stop_event.is_set():
                            log.info(f"Download aborted (engine stopping): {filepath.name}")
                            break
                        
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
                            
                            # ★ Fix K: Non-blocking download — read into memory,
                            # then write to disk on thread pool (avoids blocking event loop)
                            data = await resp.read()
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, filepath.write_bytes, data)
                        
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
                        
                        # ★ Non-Watermark: zoom+crop to remove watermark
                        if is_video and settings.download_non_watermark:
                            try:
                                await self._remove_watermark_zoom_crop(
                                    filepath, task.aspect_ratio
                                )
                            except Exception as wm_err:
                                log.warning(f"[Non-Watermark] Failed for {filepath.name}: {wm_err}")
                        
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
                                    # ★ Fix K: Offload PIL thumbnail to thread pool
                                    def _gen_image_thumb(_src, _dst):
                                        from PIL import Image
                                        with Image.open(str(_src)) as img:
                                            ratio = 80 / img.width
                                            new_size = (80, max(1, int(img.height * ratio)))
                                            thumb = img.resize(new_size, Image.LANCZOS)
                                            if thumb.mode in ('RGBA', 'P'):
                                                thumb = thumb.convert('RGB')
                                            thumb.save(str(_dst), 'JPEG', quality=85)
                                    loop = asyncio.get_event_loop()
                                    await loop.run_in_executor(None, _gen_image_thumb, filepath, thumb_path)
                                    log.info(f"Thumbnail (image): {thumb_path.name}")
                                else:
                                    # Video: extract first frame using ffmpeg (with fallback)
                                    import subprocess
                                    from core.frame_extractor import get_ffmpeg_path
                                    ffmpeg_ok = False
                                    _ffmpeg_bin = get_ffmpeg_path()
                                    
                                    if _ffmpeg_bin:
                                        # ★ Fix K: Offload ffmpeg to thread pool
                                        loop = asyncio.get_event_loop()
                                        for ss_val in ['1', '0']:
                                            try:
                                                def _run_ffmpeg(_ss=ss_val):
                                                    return subprocess.run(
                                                        [_ffmpeg_bin, '-y', '-ss', _ss, '-i', str(filepath),
                                                         '-vframes', '1', '-vf', 'scale=80:-1', '-q:v', '5',
                                                         str(thumb_path)],
                                                        capture_output=True, timeout=10,
                                                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                                                    )
                                                result = await loop.run_in_executor(None, _run_ffmpeg)
                                                if thumb_path.exists() and thumb_path.stat().st_size > 100:
                                                    ffmpeg_ok = True
                                                    log.info(f"Thumbnail (ffmpeg -ss {ss_val}): {thumb_path.name}")
                                                    break
                                            except Exception as ff_err:
                                                log.debug(f"ffmpeg -ss {ss_val} failed: {ff_err}")
                                    else:
                                        log.warning(
                                            f"ffmpeg not available — trying PIL fallback for thumbnail"
                                        )
                                    
                                    # PIL fallback: decode first frame from video container
                                    if not ffmpeg_ok:
                                        # ★ Fix K: Offload cv2 fallback to thread pool
                                        def _gen_cv2_thumb(_src, _dst):
                                            import cv2
                                            from PIL import Image
                                            cap = cv2.VideoCapture(str(_src))
                                            ret, frame = cap.read()
                                            cap.release()
                                            if ret and frame is not None:
                                                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                                                ratio = 80 / img.width
                                                new_size = (80, max(1, int(img.height * ratio)))
                                                thumb = img.resize(new_size, Image.LANCZOS)
                                                thumb.save(str(_dst), 'JPEG', quality=85)
                                                return True
                                            return False
                                        try:
                                            ok = await loop.run_in_executor(None, _gen_cv2_thumb, filepath, thumb_path)
                                            if ok:
                                                log.info(f"Thumbnail (cv2 fallback): {thumb_path.name}")
                                        except ImportError:
                                            log.warning(
                                                f"Neither ffmpeg nor opencv-python available — "
                                                f"cannot generate video thumbnail for {filepath.name}"
                                            )
                                        except Exception as cv_err:
                                            log.warning(f"cv2 thumbnail fallback failed: {cv_err}")
                                
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
    
    # ── Non-Watermark: zoom+crop helper ────────────────────────────

    async def _remove_watermark_zoom_crop(self, filepath: Path, aspect_ratio: str):
        """Zoom in and center-crop video to remove edge watermark.
        
        Zoom factors:
            - 9:16 (Portrait): 109% zoom
            - 16:9 (Landscape): 115% zoom
        
        Process: original → scale up → center-crop to original size → overwrite
        """
        # Determine zoom factor
        is_portrait = "PORTRAIT" in (aspect_ratio or "").upper() or "9:16" in (aspect_ratio or "")
        zoom = 1.09 if is_portrait else 1.15
        
        # Find FFmpeg
        from core.frame_extractor import FrameExtractor
        ffmpeg = FrameExtractor._find_ffmpeg()
        if not ffmpeg:
            log.warning("[Non-Watermark] FFmpeg not available — skipping")
            return
        
        # Probe original resolution
        import subprocess
        # Use Path-based replacement to only change filename, not directory
        _ffmpeg_p = Path(ffmpeg)
        ffprobe = str(_ffmpeg_p.parent / _ffmpeg_p.name.replace("ffmpeg", "ffprobe"))
        try:
            probe_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [ffprobe, "-v", "quiet", "-print_format", "json",
                     "-show_streams", str(filepath)],
                    capture_output=True, text=True, timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                )
            )
            import json
            probe_data = json.loads(probe_result.stdout)
            stream = next(
                (s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"),
                None
            )
            if not stream:
                log.warning(f"[Non-Watermark] No video stream in {filepath.name}")
                return
            
            orig_w = int(stream["width"])
            orig_h = int(stream["height"])
        except Exception as e:
            log.warning(f"[Non-Watermark] ffprobe failed: {e}")
            return
        
        # Calculate zoomed dimensions (must be even for H.264)
        zoomed_w = int(orig_w * zoom) // 2 * 2
        zoomed_h = int(orig_h * zoom) // 2 * 2
        
        # FFmpeg: scale up → center-crop → overwrite
        tmp_path = filepath.with_suffix(".tmp.mp4")
        cmd = [
            ffmpeg, "-y", "-i", str(filepath),
            "-vf", f"scale={zoomed_w}:{zoomed_h},crop={orig_w}:{orig_h}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",  # Pass-through audio
            "-movflags", "+faststart",
            str(tmp_path),
        ]
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}),
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            
            if process.returncode != 0:
                err_msg = (stderr or b"").decode(errors="replace")[-200:]
                log.warning(f"[Non-Watermark] FFmpeg failed (rc={process.returncode}): {err_msg}")
                # Clean up temp file
                if tmp_path.exists():
                    tmp_path.unlink()
                return
            
            # Verify output file is reasonable size
            if tmp_path.exists() and tmp_path.stat().st_size > 100_000:
                # Replace original with processed version
                import shutil
                shutil.move(str(tmp_path), str(filepath))
                log.info(
                    f"[Non-Watermark] ✅ {filepath.name}: "
                    f"zoom {zoom:.0%} → crop {orig_w}x{orig_h}"
                )
            else:
                log.warning(f"[Non-Watermark] Output too small, keeping original")
                if tmp_path.exists():
                    tmp_path.unlink()
                    
        except asyncio.TimeoutError:
            log.warning(f"[Non-Watermark] FFmpeg timed out for {filepath.name}")
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception as e:
            log.warning(f"[Non-Watermark] Error: {e}")
            if tmp_path.exists():
                tmp_path.unlink()

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
                # Video: extract first frame using ffmpeg (with fallback)
                import subprocess
                from core.frame_extractor import get_ffmpeg_path
                ffmpeg_ok = False
                _ffmpeg_bin = get_ffmpeg_path()
                
                if _ffmpeg_bin:
                    for ss_val in ['1', '0']:
                        try:
                            subprocess.run(
                                [_ffmpeg_bin, '-y', '-ss', ss_val, '-i', str(source),
                                 '-vframes', '1', '-vf', 'scale=80:-1', '-q:v', '5',
                                 str(thumb_path)],
                                capture_output=True, timeout=10,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                            )
                            if thumb_path.exists() and thumb_path.stat().st_size > 100:
                                ffmpeg_ok = True
                                break
                        except Exception:
                            pass
                
                # cv2 fallback if ffmpeg unavailable/failed
                if not ffmpeg_ok:
                    try:
                        import cv2
                        cap = cv2.VideoCapture(str(source))
                        ret, frame = cap.read()
                        cap.release()
                        if ret and frame is not None:
                            from PIL import Image
                            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                            ratio = 80 / img.width
                            new_size = (80, max(1, int(img.height * ratio)))
                            thumb_img = img.resize(new_size, Image.LANCZOS)
                            thumb_img.save(str(thumb_path), 'JPEG', quality=85)
                    except (ImportError, Exception) as e:
                        log.warning(f"[Thumbnail] Regen fallback failed: {e}")
            
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
            "high_traffic", "high traffic",
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
