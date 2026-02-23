"""
VEO Pro Max - Orchestration Engine

Reference: ARCHITECTURE_OVERVIEW.md (lines 94-120)
Role: Connects ĐẠI CHỦ ↔ THẦU ↔ THỢ into a working pipeline

Architecture: Hybrid Asyncio + ProcessPoolExecutor
- asyncio Event Loop (Main): ĐẠI CHỦ, THẦU, TaskGroup
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

log = logging.getLogger(__name__)


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
        # THẦU→THỢ handoff queue: foreman submits prompt, puts (task, worker_count)
        # into queue. Worker picks up, monitors lifecycle (poll→download→upscale).
        # maxsize=0 means unlimited — THẦU controls submission rate naturally.
        self._submitted_tasks: Dict[str, asyncio.Queue] = {}  # email → Queue of (task, worker_count)
        # Risk 7 fix: Max 2 concurrent API calls per account (any type: submit, poll, upload, upscale)
        # Prevents burst traffic when 4 workers poll/submit simultaneously
        self._account_api_semaphores: Dict[str, asyncio.Semaphore] = {}
        
        # Unified recovery state machine per account (soft-first, hard-last)
        # Phase 0: wait for readiness / reload tabs (NO Chrome kill)
        # Phase 1: soft recovery — navigate away/back (NO Chrome kill)
        # Phase 2: hard browser restart (last resort)
        # Phase 3: give up (all recovery tiers exhausted)
        self._account_recovery_phase: Dict[str, int] = {}    # email → 0-3
        self._account_phase_403_count: Dict[str, int] = {}   # email → count within current phase
        self._account_403_last_epoch: Dict[str, int] = {}    # email → last epoch when 403 was counted
        self._account_resetting: Dict[str, bool] = {}        # email → True if recovery in progress
        
        # Hot-reload: queue for accounts added while engine is running
        self._pending_accounts: asyncio.Queue = asyncio.Queue()
        self._active_account_emails: set = set()  # Track which accounts have workers
        self._task_group = None  # Reference to active TaskGroup for hot-reload
        
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
        self._burst_controller = AdaptiveBurstController()
        
        # Fix G6: Inject burst_controller into upscale queue for anti-detect delay
        self._upscale_queue._burst_controller = self._burst_controller
        
        # Wire burst controller into account manager for health-score 403 penalty
        if hasattr(self._account_manager, 'set_burst_controller'):
            self._account_manager.set_burst_controller(self._burst_controller)
        
        # Performance counters (read by AppController._push_performance)
        self._download_count = 0   # Total successful downloads
        self._error_count = 0      # Total task failures
        
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
        # 'prompts_first' = upscale queue pauses while prompts are queued (default)
        # 'upscale_first' = worker does inline upscale before freeing slot
        # Fix G1: Default 'prompts_first' — generate completes before upscale,
        # preventing reCAPTCHA token contention between UpscaleQueue and workers
        self._workload_priority = 'prompts_first'
    
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
        
        Issue #3: Uses asyncio.Event — multiple waiters share one timer.
        If cooldown is extended mid-wait, waiters stay blocked until
        the NEW expiry (no early wake-up race).
        """
        if not self.is_account_on_cooldown(email):
            return
        
        remaining = 0
        until = self._account_cooldowns.get(email)
        if until:
            remaining = max(0, (until - datetime.now()).total_seconds())
        log.info(f"[Cooldown] {email}: waiting {remaining:.0f}s...")
        
        evt = self._get_cooldown_event(email)
        try:
            # Wait with timeout as safety net (event should fire via timer)
            await asyncio.wait_for(evt.wait(), timeout=remaining + 5)
        except asyncio.TimeoutError:
            # Safety: clear cooldown if timer somehow didn't fire
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
    
    # ── Circuit Breaker (cầu dao): Extension Health Gate ──
    
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
        
        Like cutting power to a production line: all THỢ on this line stop
        until the CHỦ verifies power (extension) is back.
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
    
    def _close_circuit_breaker(self, email: str):
        """CLOSE breaker — wake all sleeping workers.
        
        Power restored: all THỢ resume work.
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
        
        All THỢ call this before each retry attempt. If breaker is OPEN,
        they sleep here. When extension reconnects, monitor wakes them.
        
        In HALF-OPEN state, only 1 THỢ gets through (probe), rest wait.
        """
        state = self._circuit_state.get(email, "closed")
        if state == "closed":
            return  # Fast path: healthy
        
        if state == "open":
            log.info(f"⏸️ [CircuitBreaker] Worker waiting — {email} breaker is OPEN")
            evt = self._get_circuit_event(email)
            await evt.wait()  # Sleep until breaker closes or half-opens
            # Re-check state after waking
            state = self._circuit_state.get(email, "closed")
        
        if state == "half_open":
            # Only 1 worker gets through as probe
            lock = self._get_half_open_lock(email)
            if lock.locked():
                # Another worker is already probing — wait for result
                log.debug(f"[CircuitBreaker] {email}: probe in progress, waiting...")
                evt = self._get_circuit_event(email)
                evt.clear()  # Re-block
                await evt.wait()
    
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
            log.info(f"[Pipeline] Workload priority → {value}")
        else:
            return False
        return True
    
    # ── Workload Priority ──
    
    def should_upscale_wait(self) -> bool:
        """Check if upscale queue should pause (prompts_first mode).
        
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
        if self._workload_priority != 'prompts_first':
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
                task.assigned_account = None
                self._dispatcher.requeue_task(task)
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
           where N = account.max_slots (0-4, configurable per-account)
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
        
        # Inject profiles_controller into accounts for debug browser sharing
        if self._profiles_controller:
            for acc in self._account_manager._accounts:
                acc.set_profiles_controller(self._profiles_controller)
        
        # Start persistent browsers for reCAPTCHA refresh
        # If debug browsers are already open, ensure_browser() will ATTACH to them
        try:
            from config.settings import get_settings as _get_settings
            _s = _get_settings()
            _headless = _s.auto_hide_enabled and _s.auto_hide_on_worker_start
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
                    
                    num_coroutines = account.max_workers  # C1: dynamic, not hardcoded 5
                    self._spawn_workers_for_account(tg, account, num_coroutines)
                
                # Hot-reload watcher: listens for new accounts added at runtime
                tg.create_task(self._account_watcher(tg))
                
                # Circuit breaker monitor: checks extension health every 10s
                tg.create_task(self._circuit_breaker_monitor())
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
    
    def _spawn_workers_for_account(
        self, tg: asyncio.TaskGroup, account: AccountManager, max_workers: int = 4,
    ):
        """Create 1 THẦU (foreman) + N THỢ (workers) for a single account.
        
        Architecture (revised):
        - THẦU: 1 coroutine per account — serializes prompt submission.
          Pulls tasks from global queue, submits to API, puts submitted
          tasks into per-account _submitted_tasks queue.
        - THỢ: N coroutines per account — monitors submitted prompts.
          Picks up tasks from _submitted_tasks queue, handles poll →
          download → upscale → download upscaled lifecycle.
        
        This ensures max 1 concurrent submit per account (anti-spam)
        while allowing N parallel monitor/download/upscale operations.
        """
        if account.email in self._active_account_emails:
            log.debug(f"Account {account.email}: workers already exist, skipping")
            return
        
        # Create per-account handoff queue (THẦU → THỢ)
        if account.email not in self._submitted_tasks:
            self._submitted_tasks[account.email] = asyncio.Queue()
        
        # 1 THẦU (Foreman) — serialized submit
        foreman_worker = Worker(
            worker_id=f"foreman-{account.email[:8]}",
            api_client=self._api_client,
            on_progress=self._on_progress,
        )
        self._workers.append(foreman_worker)
        tg.create_task(self._account_foreman_loop(foreman_worker, account))
        
        # N THỢ (Workers) — parallel monitor
        for i in range(max_workers):
            worker = Worker(
                worker_id=f"worker-{account.email[:8]}-{i}",
                api_client=self._api_client,
                on_progress=self._on_progress,
            )
            self._workers.append(worker)
            tg.create_task(self._account_worker_loop(worker, account))
        
        self._active_account_emails.add(account.email)
        log.info(
            f"Account {account.email}: 1 foreman + {max_workers} workers created "
            f"(max_slots={account.max_slots}, retry={account.retry_count}, "
            f"timeout={account.request_timeout}s)"
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
                    _headless = _get_settings().auto_hide_enabled and _get_settings().auto_hide_on_worker_start
                    await account.ensure_browser(headless=_headless)
                except Exception as e:
                    log.warning(f"Hot-reload: browser start failed for {account.email}: {e}")
                
                # Spawn workers
                num_coroutines = account.max_workers  # C1: dynamic
                self._spawn_workers_for_account(tg, account, num_coroutines)
                log.info(f"🔥 Hot-reload: {account.email} workers spawned — processing starts immediately")
                
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
    
    async def _account_foreman_loop(self, worker: Worker, account: AccountManager):
        """THẦU (Foreman) loop — serialized prompt submission per account.
        
        Responsibilities:
        - Pull tasks from GLOBAL queue (Dispatcher)
        - Validate tokens, refresh reCAPTCHA
        - Submit prompt to API (1 at a time per account → anti-spam)
        - Put submitted tasks into _submitted_tasks queue for THỢ
        
        DOES NOT: poll, download, upscale. That's THỢ's job.
        
        This is the anti-spam mechanism: only 1 foreman per account can
        submit prompts, ensuring we never exceed the 20-video limit
        through uncontrolled parallel submission.
        """
        while not self._stop_event.is_set():
            try:
                # Pause check — block until resumed (or stop signaled)
                if not self._pause_event.is_set():
                    log.debug(f"Worker {worker.worker_id}: paused, waiting for resume")
                    # Wait for either resume or stop
                    while not self._stop_event.is_set() and not self._pause_event.is_set():
                        await asyncio.sleep(0.5)
                    if self._stop_event.is_set():
                        break
                
                # Step 0.5: Staggered startup delay — prevents all workers
                # from requesting reCAPTCHA simultaneously at launch.
                if not hasattr(worker, '_startup_done'):
                    worker._startup_done = True
                    try:
                        worker_idx = int(worker.worker_id.rsplit('-', 1)[-1])
                    except (ValueError, IndexError):
                        worker_idx = 0
                    if worker_idx > 0:
                        startup_delay = worker_idx * 1.5  # 0s, 1.5s, 3s, 4.5s, 6s
                        await asyncio.sleep(startup_delay)
                
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
                    log.debug(f"Worker {worker.worker_id}: account {account.email} resetting, waiting...")
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
                    if output_count > 1:
                        extra = output_count - 1
                        if account.acquire_workers(extra):
                            worker_count += extra
                        else:
                            # Not enough capacity — requeue task, release held worker
                            log.debug(
                                f"Worker {worker.worker_id}: insufficient capacity for "
                                f"output_count={output_count} on {account.email} "
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
                        f"[Pipeline] Worker {worker.worker_id} picked task {task.id} "
                        f"[{task.state.value}/{task.stage.value}] "
                        f"progress={task.progress}% prompt_idx={task.prompt_index} "
                        f"workflow={task.workflow_type} account={account.email}"
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
                        log.info(f"Worker {worker.worker_id}: task {task.id} was cancelled, skipping")
                        account.release_workers(worker_count)
                        worker_count = 0
                        continue
                    
                    # Step 3: Lazy browser start if not yet initialized
                    if not account._browser_session or not account._browser_session.is_ready:
                        try:
                            from config.settings import get_settings as _get_settings
                            _headless = _get_settings().auto_hide_enabled and _get_settings().auto_hide_on_worker_start
                            await account.ensure_browser(headless=_headless)
                        except Exception as e:
                            log.warning(f"Browser start failed for {account.email}: {e} (continuing without persistent browser)")
                    
                    # Bug 11 fix: Removed redundant reCAPTCHA refresh here.
                    # Worker.execute() already handles reCAPTCHA refresh (step B5).
                    # Having it in both places caused double-refresh and wasted 200-500ms.
                    
                    # Step 5: Ensure project exists (CHỦ's ProjectManager)
                    if not account.project_id:
                        try:
                            trpc_client = None
                            if account._browser_session and account._browser_session.is_ready:
                                trpc_client = TRPCClient(account._browser_session._page)
                            
                            project_id = await account.project_manager.get_or_create_project(
                                email=account.email,
                                access_token=account.get_access_token(),
                                api_client=self._api_client,
                                trpc_client=trpc_client,
                                title=task.project_name or "VEO Pro Max",
                            )
                            if project_id:
                                account.set_project_id(project_id)
                            else:
                                log.warning(f"⚠️ No projectId for {account.email} — generation requests may fail (TRPC createProject returned None)")
                        except Exception as e:
                            log.warning(f"⚠️ TRPC project creation failed for {account.email}: {e} — continuing without projectId")
                    
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
                    
                    # ★ STAGE ROUTER — skip completed stages on retry
                    # If retrying from a checkpoint, jump directly to the right stage
                    if task.stage in (TaskStage.SUBMITTED, TaskStage.GENERATED,
                                      TaskStage.DOWNLOADED_720, TaskStage.UPSCALING,
                                      TaskStage.UPSCALED):
                        log.info(
                            f"[THẦU] Task {task.id}: RESUMING from stage "
                            f"{task.stage.value} → handing to THỢ (skip generate)"
                        )
                        task.state = TaskState.WAITING_POLL
                        # Handoff to THỢ — foreman doesn't monitor
                        submitted_q = self._submitted_tasks.get(account.email)
                        if submitted_q:
                            await submitted_q.put((task, worker_count, account))
                            worker_count = 0  # THỢ owns the workers now
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
                                f"[Pipeline] Task {task.id}: clearing {len(task.image_uris)} "
                                f"stale image_uris — will re-upload from image_paths"
                            )
                            task.image_uris.clear()
                        log.info(
                            f"[Pipeline] Task {task.id}: uploading {len(task.image_paths)} image(s) "
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
                            f"[Pipeline] Task {task.id}: re-uploading continuation frame "
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
                    result = None
                    
                    for attempt in range(max_retries + 1):
                        # ★ Lớp 4+5 gate: check BEFORE each retry (skip attempt 0)
                        # Both apply to ALL workers on this account (per-email key)
                        # → 1 worker bị 403 → toàn bộ nhóm thợ cùng account phải đợi
                        if attempt > 0:
                            # Lớp 4: Cooldown — exponential backoff (30→180s)
                            # set_account_cooldown() was triggered by 403 handler below
                            await self.wait_for_cooldown(account.email)
                            # Lớp 5: Circuit Breaker — extension health
                            await self._wait_for_circuit(account.email)
                            # Re-check cooldown AFTER circuit wake — CircuitBreaker
                            # HALF-OPEN probe may have reset cooldown timer
                            await self.wait_for_cooldown(account.email)
                        
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
                                    f"[Pipeline] Task {task.id}: cooldown detected INSIDE "
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
                            
                            # Step 6: Anti-Detect Spam — adaptive delay (SERIALIZED per account)
                            if getattr(self._settings, 'anti_detect_enabled', True) if self._settings else getattr(self, '_anti_detect_enabled', True):
                                # M1 fix: Use AdaptiveBurstController for intelligent pacing
                                # Tightens delay after 10 successes, backs off on 403s
                                log.info(
                                    f"[Pipeline] Task {task.id}: adaptive delay "
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
                                    log.info(
                                        f"[THẦU] Task {task.id}: submitting via Extension "
                                        f"(page context fetch) for {account.email}"
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
                                    
                                    ext_result = await asyncio.wait_for(
                                        ext_bridge.submit_prompt(
                                            email=account.email,
                                            endpoint=endpoint_key,
                                            body=body,
                                            needs_recaptcha=True,
                                        ),
                                        timeout=timeout,
                                    )
                                    
                                    # Convert Extension response → WorkerResult
                                    if ext_result and ext_result.get('success'):
                                        data = ext_result.get('data', {})
                                        op_names = []
                                        sc_ids = []
                                        output_uris = []
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
                                                if fife_url:
                                                    output_uris.append(fife_url)
                                        
                                        result = WorkerResult(
                                            success=True,
                                            operation_name=op_names[0] if op_names else None,
                                            scene_id=sc_ids[0] if sc_ids else None,
                                            operation_names=op_names,
                                            scene_ids=sc_ids,
                                            output_uris=output_uris,
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
                                        f"[THẦU] Task {task.id}: submitting via worker.execute() "
                                        f"(Extension unavailable for {account.email})"
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
                            
                            # ═══════════════════════════════════════════════
                            # TIERED 403 RECOVERY STATE MACHINE
                            # Phase 0: 3x 403 → kill browser + restart
                            # Phase 1: 3x 403 → copy Variations + warmup tabs
                            # Phase 2: give up (all tiers exhausted)
                            # Backoff within each phase: 3s, 5s, 8s
                            # ═══════════════════════════════════════════════
                            
                            # ═══════════════════════════════════════════════
                            # UNIFIED RECOVERY STATE MACHINE
                            # Merges reCAPTCHA + 403 errors into one soft-first
                            # escalation path. Chrome kill only at Phase 2.
                            #
                            # Phase 0: wait readiness → reload tabs (NO kill)
                            # Phase 1: soft recovery — navigate away/back (NO kill)
                            # Phase 2: hard browser restart (LAST RESORT)
                            # Phase 3: give up (all tiers exhausted)
                            # ═══════════════════════════════════════════════
                            error_lower = (result.error or "").lower()
                            recaptcha_fail = "recaptcha" in error_lower
                            acct_email = account.email
                            
                            # Pre-retry: reCAPTCHA already invalidated at L791
                            # Bug #2 fix: removed duplicate invalidation here
                            
                            if recaptcha_fail or "403" in (result.error or ""):
                                # M1 fix: Record error for adaptive delay backoff
                                status = 403 if "403" in (result.error or "") else 500
                                self._burst_controller.record_error(account.email, status)
                                
                                # Circuit breaker: track consecutive 403 for this account
                                self.record_circuit_403(account.email)
                                
                                # Lớp 4: Cooldown — apply to ALL workers on this account
                                # Uses Event-based multi-waiter: 1 worker bị 403
                                # → set_cooldown → ALL workers cùng email đợi (30→180s)
                                self.set_account_cooldown(account.email, f"403/{result.error}")
                                
                                # ═══════════════════════════════════════════════
                                # Recovery escalation — driven by consecutive 403 count
                                # Old approach used epoch dedup which blocked escalation
                                # entirely (epoch only changed on browser restart, but
                                # browser restart never triggered because escalation
                                # was blocked — circular deadlock).
                                #
                                # New: use circuit_consecutive_403 counter (already
                                # deduped by CircuitBreaker backoff) to drive phases.
                                # Every 3 consecutive 403s → advance one phase.
                                # ═══════════════════════════════════════════════
                                consecutive_403 = self._circuit_consecutive_403.get(acct_email, 0)
                                current_epoch = self._browser_recovery_epoch.get(acct_email, 0)
                                
                                # Determine phase from consecutive count
                                # 1-3: Phase 0 (gentle)
                                # 4-6: Phase 1 (soft recovery) 
                                # 7-9: Phase 2 (hard restart)
                                # 10+: Phase 3 (give up)
                                if consecutive_403 <= 3:
                                    phase = 0
                                    count = consecutive_403
                                elif consecutive_403 <= 6:
                                    phase = 1
                                    count = consecutive_403 - 3
                                elif consecutive_403 <= 9:
                                    phase = 2
                                    count = consecutive_403 - 6
                                else:
                                    phase = 3
                                    count = consecutive_403 - 9
                                
                                log.info(
                                    f"[Recovery] {acct_email}: phase={phase}, "
                                    f"fail count={count}/3 (consecutive_403={consecutive_403})"
                                )
                                
                                if phase == 0:
                                    # ── Phase 0: Gentle — NO Chrome kill ──
                                    if count == 1:
                                        log.info(f"[Recovery] {acct_email}: fail #{count} → wait for readiness")
                                        await self._wait_for_recaptcha_ready(account, max_wait=15.0)
                                        backoff = 3
                                    elif count == 2:
                                        log.info(f"[Recovery] {acct_email}: fail #{count} → reload tabs + wait")
                                        # ★ Route through _trigger_refresh (respects 30s cooldown)
                                        # instead of calling refresh_headers directly.
                                        # Prevents cascade: engine reload + tab_frozen recovery
                                        # + heartbeat recovery all firing simultaneously.
                                        if account.extension_bridge:
                                            try:
                                                await account.extension_bridge._trigger_refresh(
                                                    account.email,
                                                    "engine Phase 0 fail #2",
                                                    level="full"
                                                )
                                            except Exception:
                                                pass
                                        # ★ Wait 15s (was 8s) — reCAPTCHA needs ~15-20s to
                                        # warm up after tab reload
                                        await asyncio.sleep(15)
                                        await self._wait_for_recaptcha_ready(account, max_wait=30.0)
                                        backoff = 5
                                    else:
                                        log.warning(f"🟡 [{acct_email}] Phase 0 exhausted → escalating to Phase 1")
                                        backoff = 8
                                
                                elif phase == 1:
                                    # ── Phase 1: Soft recovery — NO Chrome kill ──
                                    if count <= 2:
                                        log.warning(f"[Recovery] {acct_email}: Phase 1 fail #{count} → soft recovery")
                                        await self._do_browser_recovery(
                                            account, worker.worker_id, "soft"
                                        )
                                        await asyncio.sleep(8)
                                        await self._wait_for_recaptcha_ready(account, max_wait=20.0)
                                        backoff = 10
                                    else:
                                        log.warning(f"🟠 [{acct_email}] Phase 1 exhausted → escalating to Phase 2")
                                        backoff = 10
                                
                                elif phase == 2:
                                    # ── Phase 2: Hard restart — LAST RESORT ──
                                    log.error(f"🔴 [{acct_email}] Phase 2 fail #{count} → HARD browser restart")
                                    # Bug #5 fix: check upscale queue before hard restart
                                    if self._upscale_queue and self._upscale_queue.has_active_jobs(acct_email):
                                        log.warning(
                                            f"🔴 [{acct_email}] Deferring hard restart — "
                                            f"upscale queue has active polls. Waiting 15s..."
                                        )
                                        await asyncio.sleep(15)
                                    else:
                                        await self._do_browser_recovery(
                                            account, worker.worker_id, "hard"
                                        )
                                    await asyncio.sleep(10)
                                    await self._wait_for_recaptcha_ready(account, max_wait=30.0)
                                    
                                    if count >= 3 and self._profiles_controller:
                                        # Also try Variations copy before giving up
                                        log.warning(
                                            f"🟠 [{acct_email}] Phase 2 exhausted: "
                                            f"Copy Variations + warmup tabs"
                                        )
                                        self._account_resetting[acct_email] = True
                                        try:
                                            loop = asyncio.get_running_loop()
                                            await loop.run_in_executor(
                                                None,
                                                self._profiles_controller.copy_variations_and_warmup,
                                                acct_email
                                            )
                                            await account.restart_browser()
                                            self._browser_recovery_epoch[acct_email] = current_epoch + 1
                                        except Exception as e:
                                            log.error(f"Variations copy error for {acct_email}: {e}")
                                        finally:
                                            self._account_resetting[acct_email] = False
                                    backoff = 15
                                
                                else:  # phase >= 3
                                    log.error(
                                        f"⛔ [{acct_email}] All recovery phases exhausted "
                                        f"(consecutive_403={consecutive_403}). Giving up."
                                    )
                                    backoff = 60
                            else:
                                # Non-reCAPTCHA, non-403 errors: refresh headers
                                if account.extension_bridge:
                                    try:
                                        await account.extension_bridge.refresh_headers(
                                            account.email, timeout=10
                                        )
                                        log.info(f"[Recovery] {acct_email}: Extension headers refreshed")
                                    except Exception as e:
                                        log.debug(f"[Recovery] Extension header refresh failed: {e}")
                            
                            log.warning(
                                f"Worker {worker.worker_id}: task {task.id} failed "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {result.error}. "
                                f"Retrying in {backoff}s..."
                            )
                            await asyncio.sleep(backoff)
                    
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
                                f"[THẦU] Task {task.id}: submitted {len(result.operation_names)} ops "
                                f"→ handing to THỢ (first={result.operation_name[:12]}...)"
                            )
                            # ★ HANDOFF: THẦU → THỢ — put task into per-account queue
                            # THỢ will monitor lifecycle: poll → download → upscale
                            submitted_q = self._submitted_tasks.get(account.email)
                            if submitted_q:
                                await submitted_q.put((task, worker_count, account))
                                worker_count = 0  # THỢ owns the workers now
                            else:
                                log.error(f"No submitted_tasks queue for {account.email}!")
                                await self._poll_operation(task, account)  # Fallback
                        else:
                            # Sync operation (T2I) - already complete
                            if result.output_uris:
                                log.info(
                                    f"[Engine] Task {task.id}: → SYNC COMPLETE "
                                    f"({len(result.output_uris)} outputs)"
                                )
                            else:
                                log.warning(
                                    f"[Engine] Task {task.id}: → SYNC returned 0 outputs. "
                                    f"Response data keys: {list(result.data.keys()) if result.data else 'None'}. "
                                    f"This may indicate a T2I/I2I API issue."
                                )
                            self._dispatcher.complete_task(
                                task.id,
                                output_uris=result.output_uris,
                            )
                            self._download_count += len(result.output_uris or [])
                            # Workers released by finally block
                            if self._on_task_completed:
                                self._on_task_completed(task)
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
                                await asyncio.sleep(delay)
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
                log.error(f"Worker {worker.worker_id} unexpected error: {e}")
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
    
    async def _account_worker_loop(self, worker: Worker, account: AccountManager):
        """THỢ (Worker) loop — monitors submitted prompts lifecycle.
        
        Responsibilities:
        - Wait for submitted tasks from THẦU (via _submitted_tasks queue)  
        - Poll for generation completion
        - Download 720p videos
        - Submit + poll upscale requests
        - Download upscaled videos
        
        DOES NOT: submit prompts. That's THẦU's job.
        
        Multiple THỢ run in parallel per account, enabling concurrent
        monitoring of different prompts (e.g., prompt #1 downloading
        while prompt #2 still polling).
        """
        submitted_q = self._submitted_tasks.get(account.email)
        if not submitted_q:
            log.error(f"THỢ {worker.worker_id}: no submitted_tasks queue for {account.email}")
            return
        
        while not self._stop_event.is_set():
            task = None
            worker_count = 0
            try:
                # Wait for THẦU to hand off a submitted task
                try:
                    item = await asyncio.wait_for(
                        submitted_q.get(), timeout=2.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                task, worker_count, acct = item
                log.info(
                    f"[THỢ] {worker.worker_id} picked up task {task.id} "
                    f"stage={task.stage.value} ops={len(task.operation_names or [])} "
                    f"from THẦU"
                )
                
                try:
                    # Monitor the full lifecycle: poll → download → upscale
                    await self._poll_operation(task, acct)
                except Exception as e:
                    log.error(f"[THỢ] {worker.worker_id} task {task.id} monitoring error: {e}")
                    # Fail the task if monitoring crashed
                    if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                        self._dispatcher.fail_task(
                            task.id, f"Monitoring error: {e}"
                        )
                        self._error_count += 1
                        emit_event(EventType.TASK_FAILED, {
                            "task_id": task.id, "error": str(e),
                            "reason": "monitor_exception",
                        }, source="engine")
                        if self._on_task_failed:
                            self._on_task_failed(task, str(e))
                finally:
                    # Release worker slots — THỢ owns them after THẦU handoff
                    if worker_count > 0:
                        account.release_workers(worker_count)
                        worker_count = 0
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"THỢ {worker.worker_id} unexpected error: {e}")
                # Fail task if acquired
                try:
                    if task and task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                        self._dispatcher.fail_task(
                            task.id, f"THỢ unexpected error: {e}"
                        )
                        self._error_count += 1
                        if self._on_task_failed:
                            self._on_task_failed(task, str(e))
                except Exception:
                    pass
                # Ensure workers released
                if worker_count > 0:
                    account.release_workers(worker_count)
                    worker_count = 0
                await asyncio.sleep(1.0)
    
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
        
        poll_interval = AppConstants.POLL_INTERVAL
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
                if self._on_task_completed:
                    self._on_task_completed(task)
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
            # Risk 2 fix: Jitter prevents all workers from polling simultaneously
            # 4 workers polling at exactly 15s intervals → burst of 4 requests
            # Jitter spreads them across 15-19.5s window
            jitter = random.uniform(0, poll_interval * 0.3)
            actual_interval = poll_interval + jitter
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
                    # Trigger UI refresh so thumbnails generated from 720p show immediately
                    self._dispatcher.update_progress(
                        task.id, 87, f"📥 720p downloaded ({len(local_720p)} videos)"
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
                            if self._workload_priority == 'upscale_first':
                                # Issue #5: INLINE upscale — worker holds slot
                                # Video is upscaled immediately, no queue delay
                                log.info(
                                    f"[Engine] Task {task.id}: upscale_first mode → "
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
                                # BACKGROUND upscale (balanced / prompts_first)
                                from core.upscale_queue import UpscaleJob
                                self._upscale_queue.enqueue(UpscaleJob(
                                    task_id=task.id,
                                    account_email=account.email,
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
                    if self._on_task_completed:
                        self._on_task_completed(task)
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
            log.info(f"[Pipeline] No extension bridge for {account.email}, using 5s fixed cooldown")
            await asyncio.sleep(5.0)
            return False
        
        # Pre-check: is extension even connected?
        if not bridge.is_connected(account.email):
            log.warning(
                f"[Pipeline] Extension NOT connected for {account.email} — "
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
                    f"[Pipeline] reCAPTCHA ready check #{attempt} EXCEPTION for "
                    f"{account.email}: {e}"
                )
                ready = False
            
            elapsed = asyncio.get_event_loop().time() - start
            
            if ready:
                log.info(
                    f"[Pipeline] ✅ grecaptcha ready for {account.email} "
                    f"(attempt #{attempt}, waited {elapsed:.1f}s)"
                )
                
                # Layer 3: Pre-fetch tokens while grecaptcha is confirmed ready
                if self._recaptcha_pool:
                    try:
                        fetched = await self._recaptcha_pool.priority_prefetch(
                            account.email, count=2
                        )
                        log.info(
                            f"[Pipeline] Priority prefetch: {fetched} token(s) "
                            f"cached for continuation"
                        )
                    except Exception as e:
                        log.debug(f"[Pipeline] Priority prefetch failed: {e}")
                
                # Reset unified recovery state on success
                self._account_recovery_phase[account.email] = 0
                self._account_phase_403_count[account.email] = 0
                return True
            else:
                log.info(
                    f"[Pipeline] ⏳ reCAPTCHA not ready for {account.email} "
                    f"(attempt #{attempt}, {elapsed:.1f}/{max_wait:.0f}s) — "
                    f"retry in {interval:.1f}s"
                )
            
            await asyncio.sleep(interval)
            interval = min(interval * 1.3, 5.0)  # Gentle backoff: 2→2.6→3.4→4.4→5
        
        elapsed = asyncio.get_event_loop().time() - start
        log.warning(
            f"[Pipeline] ⏳ grecaptcha not ready after {elapsed:.1f}s / {attempt} attempts — "
            f"proceeding anyway for {account.email}"
        )
        return False
    
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
                
                # NOTE: upload_image() does NOT use reCAPTCHA (HAR verified).
                # Do NOT get/refresh/invalidate reCAPTCHA here — it would waste
                # single-use tokens needed by the subsequent generation API call.
                upload_resp = await self._api_client.upload_image(
                    access_token=account.get_access_token(),
                    recaptcha_token="",  # Not used by upload endpoint
                    image_base64=img_b64,
                    mime_type=mime_type,
                    aspect_ratio=task.aspect_ratio or "IMAGE_ASPECT_RATIO_LANDSCAPE",
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
                            upscale_body = self._api_client.build_upscale_body(
                                video_media_id=media_id,
                                target_resolution=resolution,
                                aspect_ratio=task.aspect_ratio,
                                seed=generate_random_seed(),
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
                            upscale_body = self._api_client.build_upscale_body(
                                video_media_id=media_id,
                                target_resolution=resolution,
                                aspect_ratio=task.aspect_ratio,
                                seed=generate_random_seed(),
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
                error = poll_ops[0].get("error", {}).get("message", "unknown")
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
        """Re-upscale videos in a completed task.
        
        Args:
            failed_only: If True, only retry videos with upscale_status='failed'.
                        If False, re-upscale ALL videos regardless of status.
        """
        task = self._dispatcher.get_task(task_id)
        if not task:
            log.warning(f"Re-upscale {task_id}: task not found")
            return False
        
        # Fallback: rebuild upscale_media_ids from video_outputs if missing
        # MUST keep positional alignment: index in upscale_media_ids == index in video_outputs
        if not task.upscale_media_ids and task.video_outputs:
            rebuilt = [vo.media_id or "" for vo in task.video_outputs]  # "" placeholder for failed
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
                # Re-upscale ALL videos — reset their status first
                for vo in task.video_outputs:
                    vo.upscale_status = ""
                    vo.upscale_error = ""
                    vo.file_upscaled = ""
                failed_indices = list(range(len(task.video_outputs)))
        else:
            # Backward compat: no video_outputs → retry all
            failed_indices = list(range(len(task.upscale_media_ids)))
        
        if not failed_indices:
            log.info(f"Re-upscale {task_id}: no videos to upscale")
            return True
        
        label = "failed" if failed_only else "all"
        self._dispatcher.update_progress(task.id, 88, f"⬆️ Re-upscaling {label} videos...")
        
        any_success = False
        for idx in failed_indices:
            success = await self._re_upscale_single(task, account, idx)
            if success:
                any_success = True
        
        # Sync overall status
        self._sync_overall_upscale_status(task)
        
        if any_success:
            self._dispatcher.update_progress(task.id, 100, "✅ Re-upscale done")
            if self._on_task_completed:
                self._on_task_completed(task)
            self._save_manifest(task)
            return True
        else:
            self._dispatcher.update_progress(task.id, 100, "⚠️ Re-upscale failed")
            return False
    
    async def re_upscale_single_video(
        self, task_id: str, video_index: int, account: AccountManager,
    ) -> bool:
        """Re-upscale a SINGLE video by index.
        
        Called from UI when user right-clicks a red thumbnail.
        """
        task = self._dispatcher.get_task(task_id)
        if not task:
            log.warning(f"Re-upscale single {task_id}[{video_index}]: task not found")
            return False
        
        # Fallback: rebuild upscale_media_ids from video_outputs if missing
        # MUST keep positional alignment: index in upscale_media_ids == index in video_outputs
        if not task.upscale_media_ids and task.video_outputs:
            rebuilt = [vo.media_id or "" for vo in task.video_outputs]  # "" placeholder for failed
            if any(rebuilt):
                task.upscale_media_ids = rebuilt
                valid_count = sum(1 for m in rebuilt if m)
                log.info(f"Re-upscale single {task_id}[{video_index}]: rebuilt media_ids from video_outputs ({valid_count}/{len(rebuilt)} valid)")
        
        if not task.upscale_media_ids:
            log.warning(f"Re-upscale single {task_id}[{video_index}]: no media_ids (video_outputs also empty)")
            return False
        
        if video_index >= len(task.upscale_media_ids):
            log.warning(f"Re-upscale single {task_id}[{video_index}]: index out of range ({len(task.upscale_media_ids)} media_ids)")
            return False
        
        if not task.upscale_media_ids[video_index]:
            log.warning(f"Re-upscale single {task_id}[{video_index}]: no media_id for this video (operation may have failed)")
            return False
        
        self._dispatcher.update_progress(
            task.id, 88, f"⬆️ Re-upscaling video {video_index + 1}..."
        )
        
        success = await self._re_upscale_single(task, account, video_index)
        
        # Sync overall status
        self._sync_overall_upscale_status(task)
        
        if success:
            self._dispatcher.update_progress(task.id, 100, "✅ Re-upscale done")
            if self._on_task_completed:
                self._on_task_completed(task)
            self._save_manifest(task)
        else:
            self._dispatcher.update_progress(task.id, 100, "⚠️ Re-upscale failed")
        
        return success
    
    async def _re_upscale_single(
        self, task: Task, account: AccountManager, video_index: int,
    ) -> bool:
        """Internal: re-upscale one video by index."""
        from core.api_client import generate_random_seed
        
        quality_map = {
            "1080p": "VIDEO_RESOLUTION_1080P",
            "4K": "VIDEO_RESOLUTION_4K",
        }
        resolution = quality_map.get(task.download_quality)
        if not resolution:
            return False
        
        media_id = task.upscale_media_ids[video_index]
        if not media_id:
            return False
        
        video_label = f"{video_index + 1}/{len(task.upscale_media_ids)}"
        
        # Clear per-video error
        if video_index < len(task.video_outputs):
            task.video_outputs[video_index].upscale_status = ""
            task.video_outputs[video_index].upscale_error = ""
        
        # Submit upscale — Extension primary, aiohttp fallback
        ext_bridge = getattr(account, 'extension_bridge', None)
        use_ext = (ext_bridge and ext_bridge.is_connected(account.email))
        
        if use_ext:
            upscale_body = self._api_client.build_upscale_body(
                video_media_id=media_id,
                target_resolution=resolution,
                aspect_ratio=task.aspect_ratio,
                seed=generate_random_seed(),
            )
            ext_r = await ext_bridge.submit_upscale(
                email=account.email, body=upscale_body,
            )
            from core.api_client import APIResponse
            if ext_r and ext_r.get('success'):
                resp = APIResponse(success=True, data=ext_r.get('data', {}))
            elif ext_r:
                resp = APIResponse(
                    success=False,
                    error=ext_r.get('error', '') or f"HTTP {ext_r.get('status', 0)}",
                )
            else:
                resp = APIResponse(success=False, error="Extension timeout")
        else:
            recaptcha_token = await account.refresh_recaptcha() or ""
            if not recaptcha_token:
                recaptcha_token = account.get_recaptcha_token() or ""
            resp = await self._api_client.upscale_video(
                access_token=account.get_access_token() or "",
                recaptcha_token=recaptcha_token,
                video_media_id=media_id,
                target_resolution=resolution,
                aspect_ratio=task.aspect_ratio,
                seed=generate_random_seed(),
                account_headers=account.get_api_headers(),
            )
        
        if not resp.success:
            if video_index < len(task.video_outputs):
                task.video_outputs[video_index].upscale_status = "failed"
                task.video_outputs[video_index].upscale_error = resp.error or "Submit failed"
            return False
        
        ops = resp.data.get("operations", [])
        if not ops:
            if video_index < len(task.video_outputs):
                task.video_outputs[video_index].upscale_status = "failed"
                task.video_outputs[video_index].upscale_error = "No operation returned"
            return False
        
        op_name = ops[0].get("operation", {}).get("name", "")
        scene_id = ops[0].get("sceneId", "")
        
        result = await self._poll_upscale(task, account, video_label, op_name, scene_id)
        
        if result:
            # Download upscaled file
            dl_paths = await self._download_outputs(
                task, result,
                quality_subfolder=task.download_quality,
                generate_thumbnails=False,
            )
            if dl_paths:
                # Update per-video info
                if video_index < len(task.video_outputs):
                    task.video_outputs[video_index].file_upscaled = dl_paths[0]
                    task.video_outputs[video_index].quality = task.download_quality
                    task.video_outputs[video_index].upscale_status = "success"
                    task.video_outputs[video_index].upscale_error = ""
                # Update output_uris (prefer upscaled)
                if video_index < len(task.output_uris):
                    task.output_uris[video_index] = dl_paths[0]
                log.info(f"Re-upscale video {video_label} done ✅")
                return True
        
        if video_index < len(task.video_outputs):
            task.video_outputs[video_index].upscale_status = "failed"
            task.video_outputs[video_index].upscale_error = task._upscale_error or "Poll failed"
        return False
    
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
        
        Folder structure (Option A):
          output_folder/project_name/720p/001a_..._720p.mp4
          output_folder/project_name/4K/001a_..._4K.mp4
        
        Naming convention:
        - Single output:   {NNN}_{timestamp}_{quality}.mp4
        - Multi output:    {NNN}{variant}_{timestamp}_{quality}.mp4
        
        Args:
            overwrite_paths: If provided, download to these paths instead of
                generating new filenames. Used by re-download to replace
                existing broken/incomplete files. Length must match output_uris.
        """
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
        
        async with aiohttp.ClientSession() as session:
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
                        filename = sep.join(parts) + ".mp4"
                        filepath = output_path / filename
                        
                        # Avoid overwrite — add numeric suffix if exists
                        counter = 1
                        while filepath.exists():
                            filepath = output_path / f"{sep.join(parts)}_{counter}.mp4"
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
                        
                        # Update per-video file_720p
                        if i < len(task.video_outputs):
                            task.video_outputs[i].file_720p = str(filepath)
                            if task.video_outputs[i].quality == "pending":
                                task.video_outputs[i].quality = "720p"
                        
                        # Generate thumbnail (first frame, keep aspect ratio)
                        if generate_thumbnails:
                            try:
                                import subprocess
                                thumb_dir = Path.home() / ".veoauto" / "cache" / "thumbnails"
                                thumb_dir.mkdir(parents=True, exist_ok=True)
                                thumb_path = thumb_dir / f"{task.id}_{i}.jpg"
                                subprocess.run(
                                    ['ffmpeg', '-y', '-ss', '1', '-i', str(filepath),
                                     '-vframes', '1', '-vf', 'scale=80:-1', '-q:v', '5',
                                     str(thumb_path)],
                                    capture_output=True, timeout=10
                                )
                                if thumb_path.exists():
                                    task.thumbnail_paths.append(str(thumb_path))
                                    # Update per-video thumbnail
                                    if i < len(task.video_outputs):
                                        task.video_outputs[i].thumbnail_path = str(thumb_path)
                                    log.info(f"Thumbnail: {thumb_path.name}")
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
        """Auto-regenerate missing thumbnail from video file.
        
        Called when UI requests a thumbnail that no longer exists on disk.
        
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
            import subprocess
            thumb_dir = Path.home() / ".veoauto" / "cache" / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = thumb_dir / f"{task.id}_{video_index}.jpg"
            
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
