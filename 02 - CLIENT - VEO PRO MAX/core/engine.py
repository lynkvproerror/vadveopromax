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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.multi_account import MultiAccountManager
from core.account_manager import AccountManager
from core.dispatcher import Dispatcher, Task, TaskState, TaskStage, VideoOutputInfo
from core.worker import Worker, WorkerResult
from core.api_client import VEOApiClient
from core.frame_extractor import FrameExtractor
from core.trpc_client import TRPCClient

log = logging.getLogger(__name__)


class Engine:
    """Orchestration Engine - Connects all layers.
    
    Pipeline flow:
    1. Dispatcher.get_next_task()  →  get ready task from queue
    2. MultiAccountManager.acquire_slot()  →  get available account
    3. ProjectManager.get_or_create_project()  →  ensure project exists
    4. Worker.execute(task, account)  →  run API calls
    5. AccountManager.release_slot()  →  return slot to pool
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
        # A1/A2: ProjectManager is now per-account (CHỦ owns it)
        # No longer a shared singleton here
        self._frame_extractor = FrameExtractor()
        self._profiles_controller = profiles_controller  # For auto re-login
        
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
        self._relogin_locks: Dict[str, asyncio.Lock] = {}  # Per-account re-login dedup
        self._browser_recovery_locks: Dict[str, asyncio.Lock] = {}   # Per-account browser recovery dedup
        self._browser_recovery_epoch: Dict[str, int] = {}             # Tracks recovery generation
        self._account_rate_locks: Dict[str, asyncio.Lock] = {}  # Bug 13: per-account rate limiter
        # Risk 7 fix: Max 2 concurrent API calls per account (any type: submit, poll, upload, upscale)
        # Prevents burst traffic when 4 workers poll/submit simultaneously
        self._account_api_semaphores: Dict[str, asyncio.Semaphore] = {}
        
        # Tiered 403 recovery state machine per account
        # Phase 0: accumulate 3x 403 → kill browser
        # Phase 1: accumulate 3x 403 → copy Variations + warmup tabs
        # Phase 2: accumulate 3x 403 → delete profile + auto re-login
        # Phase 3: accumulate 3x 403 → STOP (give up)
        self._account_recovery_phase: Dict[str, int] = {}    # email → 0-3
        self._account_phase_403_count: Dict[str, int] = {}   # email → count within current phase
        self._account_403_last_epoch: Dict[str, int] = {}    # email → last epoch when 403 was counted
        self._account_resetting: Dict[str, bool] = {}        # email → True if recovery in progress
        
        # Hot-reload: queue for accounts added while engine is running
        self._pending_accounts: asyncio.Queue = asyncio.Queue()
        self._active_account_emails: set = set()  # Track which accounts have workers
        self._task_group = None  # Reference to active TaskGroup for hot-reload
        
        # Continuation settings (forwarded from AppController.start_processing)
        self._continuation_enabled = True  # C5: global toggle
        self._extract_point_ms = 750       # Default extract point
        
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
        
        # Performance counters (read by AppController._push_performance)
        self._download_count = 0   # Total successful downloads
        self._error_count = 0      # Total task failures
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def is_paused(self) -> bool:
        return not self._pause_event.is_set()
    
    def _get_api_semaphore(self, email: str) -> asyncio.Semaphore:
        """Get or create per-account API semaphore.
        
        Limits max concurrent API calls (submit, poll, upload, upscale)
        to 2 per account, preventing burst traffic that triggers 403.
        """
        if email not in self._account_api_semaphores:
            self._account_api_semaphores[email] = asyncio.Semaphore(2)
        return self._account_api_semaphores[email]
    
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
        self._dispatcher._on_task_ready = lambda task: self._task_available.set()
        
        # Inject profiles_controller into accounts for debug browser sharing
        if self._profiles_controller:
            for acc in self._account_manager._accounts:
                acc.set_profiles_controller(self._profiles_controller)
        
        # Start persistent browsers for reCAPTCHA refresh
        # If debug browsers are already open, ensure_browser() will ATTACH to them
        try:
            await self._account_manager.startup_browsers(headless=True)
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
        
        try:
            async with asyncio.TaskGroup() as tg:
                self._task_group = tg  # Store reference for hot-reload
                
                # Dynamic Worker Scaling: Always create MAX workers per account.
                # acquire_slot() checks max_slots EVERY call, so changing
                # max_slots mid-run takes effect immediately:
                #   - Increase: idle workers start acquiring slots → process tasks
                #   - Decrease: excess workers fail acquire_slot() → idle safely
                MAX_WORKERS_PER_ACCOUNT = 4
                
                for account in self._account_manager._accounts:
                    if not account.is_enabled:
                        log.info(f"Account {account.email}: skipped (disabled)")
                        continue
                    
                    self._spawn_workers_for_account(tg, account, MAX_WORKERS_PER_ACCOUNT)
                
                # Hot-reload watcher: listens for new accounts added at runtime
                tg.create_task(self._account_watcher(tg))
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
        """Create worker coroutines for a single account inside a TaskGroup.
        
        All workers share the master AccountManager and get tokens/headers
        via the Extension bridge (no per-worker Chrome clones needed).
        
        Shared helper used by both start() (initial accounts) and
        _account_watcher() (hot-reloaded accounts).
        """
        if account.email in self._active_account_emails:
            log.debug(f"Account {account.email}: workers already exist, skipping")
            return
        
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
            f"Account {account.email}: {max_workers} workers created "
            f"(max_slots={account.max_slots}, retry={account.retry_count}, "
            f"timeout={account.request_timeout}s)"
        )
    
    async def _account_watcher(self, tg: asyncio.TaskGroup):
        """Watch for new accounts added at runtime and spawn workers.
        
        Runs inside the TaskGroup — uses tg.create_task() to add
        new worker coroutines dynamically without engine restart.
        """
        MAX_WORKERS_PER_ACCOUNT = 4
        
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
                    await account.ensure_browser(headless=True)
                except Exception as e:
                    log.warning(f"Hot-reload: browser start failed for {account.email}: {e}")
                
                # Spawn workers
                self._spawn_workers_for_account(tg, account, MAX_WORKERS_PER_ACCOUNT)
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
            loop = asyncio.get_event_loop()
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
    
    async def _account_worker_loop(self, worker: Worker, account: AccountManager):
        """Worker loop bound to a specific account (CHỦ).
        
        Each worker is dedicated to ONE account but pulls tasks from 
        the GLOBAL task queue (THẦU). This ensures:
        - Per-account slot limit is respected (max_slots)
        - Cross-project work distribution (any worker can take any task)
        - No task duplication (atomic get_next_task)
        - Per-account retry and timeout settings
        
        Retry logic: exponential backoff for non-auth errors.
        Timeout: asyncio.wait_for wraps execute call.
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
                
                # Step 1: Acquire slot from THIS account
                if not account.acquire_slot():
                    await asyncio.sleep(0.5)
                    continue
                
                # Bug 2 fix: Pause if profile reset in progress for this account
                if self._account_resetting.get(account.email, False):
                    account.release_slot()
                    log.debug(f"Worker {worker.worker_id}: account {account.email} resetting, waiting...")
                    while self._account_resetting.get(account.email, False) and not self._stop_event.is_set():
                        await asyncio.sleep(2)
                    continue  # Re-acquire slot after reset
                
                try:
                    # Step 2: Get next task from GLOBAL queue (THẦU)
                    task = self._dispatcher.get_next_task()
                    if not task:
                        account.release_slot()
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
                    
                    # D2: Account affinity check — continuation tasks must run on same account
                    if task.required_account and task.required_account != account.email:
                        # Re-queue for correct account, release our slot
                        self._dispatcher.submit_task(task)
                        account.release_slot()
                        await asyncio.sleep(0.1)
                        continue
                    
                    # Cancellation check: task may have been cancelled between
                    # get_next_task and now (e.g., user deleted from queue)
                    if task.state == TaskState.CANCELLED:
                        log.info(f"Worker {worker.worker_id}: task {task.id} was cancelled, skipping")
                        account.release_slot()
                        continue
                    
                    # Step 3: Lazy browser start if not yet initialized
                    if not account._browser_session or not account._browser_session.is_ready:
                        try:
                            await account.ensure_browser(headless=True)
                        except Exception as e:
                            log.warning(f"Browser start failed for {account.email}: {e} (continuing without persistent browser)")
                    
                    # Bug 11 fix: Removed redundant reCAPTCHA refresh here.
                    # Worker.execute() already handles reCAPTCHA refresh (step B5).
                    # Having it in both places caused double-refresh and wasted 200-500ms.
                    
                    # Step 5: Ensure project exists (CHỦ's ProjectManager)
                    if not account.project_id:
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
                    
                    # Step 5.5: Auto-detect paygate tier (once per account)
                    if account.paygate_tier == "PAYGATE_TIER_TWO":
                        await account.fetch_paygate_tier(self._api_client)
                    
                    # Notify UI
                    task.assigned_account = account.email
                    task.project_id = account.project_id
                    if self._on_task_started:
                        self._on_task_started(task)
                    
                    # ★ STAGE ROUTER — skip completed stages on retry
                    # If retrying from a checkpoint, jump directly to the right stage
                    if task.stage in (TaskStage.SUBMITTED, TaskStage.GENERATED,
                                      TaskStage.DOWNLOADED_720, TaskStage.UPSCALING,
                                      TaskStage.UPSCALED):
                        log.info(
                            f"[Engine] Task {task.id}: RESUMING from stage "
                            f"{task.stage.value} (skip generate)"
                        )
                        task.state = TaskState.WAITING_POLL
                        await self._poll_operation(task, account)
                        account.release_slot()
                        return  # Task completed or failed inside _poll_operation
                    
                    # Bug 13: Per-account rate limiter — serialize requests per account
                    # Ensures 4 workers on same account don't submit simultaneously
                    if account.email not in self._account_rate_locks:
                        self._account_rate_locks[account.email] = asyncio.Lock()
                    
                    # Step 7: Execute with RETRY + TIMEOUT
                    # Rate lock held ONLY during anti-detect delay + API call,
                    # released between retries so other workers can proceed.
                    
                    # Step 6.5: Upload local image_paths → image_uris
                    # Risk 4 fix: Upload through rate lock to prevent 4 concurrent uploads
                    if task.image_paths and not task.image_uris:
                        async with self._account_rate_locks[account.email]:
                            await self._resolve_image_paths(task, account)
                    
                    max_retries = account.retry_count
                    timeout = account.request_timeout
                    result = None
                    
                    for attempt in range(max_retries + 1):
                        # Lock: covers anti-detect delay + single API call only
                        async with self._account_rate_locks[account.email]:
                            # Step 6: Anti-Detect Spam — random delay (SERIALIZED per account)
                            if getattr(self, '_anti_detect_enabled', True):
                                # Risk 1 fix: Increased from 1-5s to 3-8s (avg 5.5s)
                                # With 4 workers: worst-case 4 submit in ~22s instead of ~10s
                                delay_min = getattr(self, '_anti_detect_delay_min', 3.0)
                                delay_max = getattr(self, '_anti_detect_delay_max', 8.0)
                                delay = random.uniform(delay_min, delay_max)
                                log.debug(f"Worker {worker.worker_id}: anti-detect delay {delay:.6f}s before submit")
                                await asyncio.sleep(delay)
                        
                            try:
                                result = await asyncio.wait_for(
                                    worker.execute(task, account, paygate_tier=account.paygate_tier),
                                    timeout=timeout,
                                )
                            except asyncio.TimeoutError:
                                result = WorkerResult(
                                    success=False,
                                    error=f"Request timed out after {timeout}s"
                                )
                            
                            # reCAPTCHA tokens are single-use: consumed by Google
                            # on EVERY request (success OR failure).
                            # Invalidate immediately so next call gets a fresh token.
                            account.invalidate_recaptcha()
                        # Rate lock released here — other workers can now submit
                        
                        if result.success:
                            break  # Success — exit retry loop
                        
                        # Layer 1: Network error → INSTANT pause, re-queue task
                        if self._is_network_error(result.error or ""):
                            log.warning(f"🌐 Network error → auto-pausing: {result.error}")
                            await self.pause()
                            if self._on_connectivity_changed:
                                self._on_connectivity_changed(False, 9999)
                            self._dispatcher.requeue_task(task)
                            account.release_slot()
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
                            # Phase 2: 3x 403 → delete profile + auto re-login
                            # Phase 3: 3x 403 → STOP (all tiers exhausted)
                            # Backoff within each phase: 3s, 5s, 8s
                            # ═══════════════════════════════════════════════
                            
                            # Pre-retry: refresh headers via extension bridge (Fix #7)
                            # Stale x-browser-* headers are a common cause of 403
                            if hasattr(account, '_extension_bridge') and account._extension_bridge:
                                try:
                                    await account._extension_bridge.refresh_headers(
                                        account.email, timeout=10
                                    )
                                    log.info(f"[Recovery] {account.email}: Extension headers refreshed before retry")
                                except Exception as e:
                                    log.debug(f"[Recovery] Extension header refresh failed: {e}")
                            
                            # Pre-retry: invalidate reCAPTCHA (single-use tokens)
                            account.invalidate_recaptcha()
                            
                            error_lower = (result.error or "").lower()
                            if "recaptcha" in error_lower:
                                acct_email = account.email
                                current_epoch = self._browser_recovery_epoch.get(acct_email, 0)
                                last_counted_epoch = self._account_403_last_epoch.get(acct_email, -1)
                                
                                # Deduped by epoch: only count once per real recovery
                                if current_epoch != last_counted_epoch:
                                    self._account_403_last_epoch[acct_email] = current_epoch
                                    phase = self._account_recovery_phase.get(acct_email, 0)
                                    count = self._account_phase_403_count.get(acct_email, 0) + 1
                                    self._account_phase_403_count[acct_email] = count
                                    
                                    # Phase-specific backoff: 3s, 5s, 8s
                                    phase_backoffs = [3, 5, 8]
                                    backoff = phase_backoffs[min(count - 1, 2)]
                                    
                                    log.info(
                                        f"[Recovery] {acct_email}: phase={phase}, "
                                        f"403 count={count}/3 (epoch={current_epoch})"
                                    )
                                    
                                    if count >= 3:
                                        # ── ESCALATE to next phase ──
                                        next_phase = phase + 1
                                        self._account_recovery_phase[acct_email] = next_phase
                                        self._account_phase_403_count[acct_email] = 0
                                        
                                        if next_phase == 1:
                                            # ▶ PHASE 1: Kill browser + hard restart
                                            log.warning(
                                                f"🔴 [{acct_email}] Phase 1: Kill browser "
                                                f"(3x 403 in phase 0)"
                                            )
                                            await self._do_browser_recovery(
                                                account, worker.worker_id, "hard"
                                            )
                                            backoff = 8
                                            
                                        elif next_phase == 2 and self._profiles_controller:
                                            # ▶ PHASE 2: Copy Variations + warmup tabs
                                            log.warning(
                                                f"🟠 [{acct_email}] Phase 2: Copy Variations "
                                                f"+ warmup tabs (3x 403 in phase 1)"
                                            )
                                            self._account_resetting[acct_email] = True
                                            try:
                                                loop = asyncio.get_event_loop()
                                                await loop.run_in_executor(
                                                    None,
                                                    self._profiles_controller.copy_variations_and_warmup,
                                                    acct_email
                                                )
                                                # Restart browser with new Variations
                                                await account.restart_browser()
                                                self._browser_recovery_epoch[acct_email] = current_epoch + 1
                                            except Exception as e:
                                                log.error(f"Phase 2 recovery error for {acct_email}: {e}")
                                            finally:
                                                self._account_resetting[acct_email] = False
                                            backoff = 10
                                            
                                        elif next_phase == 3 and self._profiles_controller:
                                            # ▶ PHASE 3: Delete profile + auto re-login
                                            has_creds = False
                                            try:
                                                from core.credentials_manager import get_credentials_manager
                                                has_creds = get_credentials_manager().has_credentials_for(acct_email)
                                            except Exception:
                                                pass
                                            
                                            if has_creds:
                                                log.warning(
                                                    f"🔴 [{acct_email}] Phase 3: Delete profile "
                                                    f"+ auto re-login (3x 403 in phase 2)"
                                                )
                                                self._account_resetting[acct_email] = True
                                                try:
                                                    loop = asyncio.get_event_loop()
                                                    reset_result = await loop.run_in_executor(
                                                        None,
                                                        self._profiles_controller.reset_profile_and_relogin,
                                                        acct_email
                                                    )
                                                    if reset_result:
                                                        log.info(f"✅ Phase 3 re-login OK: {acct_email}")
                                                        # Sync new profile path
                                                        updated = self._profiles_controller.get_profile(acct_email)
                                                        if updated and updated.browser_profile_path:
                                                            account.browser_profile_path = updated.browser_profile_path
                                                        await account.restart_browser()
                                                        self._browser_recovery_epoch[acct_email] = current_epoch + 1
                                                    else:
                                                        log.error(f"❌ Phase 3 re-login failed: {acct_email}")
                                                except Exception as e:
                                                    log.error(f"Phase 3 recovery error for {acct_email}: {e}")
                                                finally:
                                                    self._account_resetting[acct_email] = False
                                            else:
                                                log.error(
                                                    f"❌ [{acct_email}] No credentials stored — "
                                                    f"cannot do Phase 3 (delete+relogin)"
                                                )
                                            backoff = 15
                                            
                                        elif next_phase >= 4:
                                            # ▶ ALL PHASES EXHAUSTED — give up
                                            log.error(
                                                f"⛔ [{acct_email}] All 3 recovery phases exhausted "
                                                f"(12x 403). Giving up on this account."
                                            )
                                            backoff = 60
                                else:
                                    # Same epoch — another worker already counted this 403
                                    backoff = 10
                            
                            log.warning(
                                f"Worker {worker.worker_id}: task {task.id} failed "
                                f"(attempt {attempt + 1}/{max_retries + 1}): {result.error}. "
                                f"Retrying in {backoff}s..."
                            )
                            await asyncio.sleep(backoff)
                    
                    # Slot stays held until task fully completes (poll + download).
                    # This ensures max_slots limits actual concurrent tasks.
                    
                    # Step 8: Process final result
                    log.info(f"[Engine] Task {task.id}: result.success={result.success if result else 'NO_RESULT'}, "
                             f"operation_name={result.operation_name if result else 'N/A'}")
                    if result and result.success:
                        # Reset ALL recovery state on success — account is healthy
                        self._account_recovery_phase[account.email] = 0
                        self._account_phase_403_count[account.email] = 0
                        self._account_403_last_epoch[account.email] = -1
                        # For async operations, start polling (slot held during poll)
                        if result.operation_name:
                            task.operation_name = result.operation_name
                            task.operation_names = list(result.operation_names)
                            task.scene_ids = list(result.scene_ids)
                            task.stage = TaskStage.SUBMITTED  # ★ Checkpoint: prompt submitted
                            task.state = TaskState.WAITING_POLL
                            log.info(
                                f"[Engine] Task {task.id}: → POLLING {len(result.operation_names)} ops "
                                f"(first={result.operation_name[:12]}...)"
                            )
                            await self._poll_operation(task, account)
                            account.release_slot()
                        else:
                            # Sync operation (T2I) - already complete
                            log.info(f"[Engine] Task {task.id}: → SYNC COMPLETE (no operation_name)")
                            self._dispatcher.complete_task(
                                task.id,
                                output_uris=result.output_uris,
                            )
                            self._download_count += len(result.output_uris or [])
                            account.release_slot()
                            if self._on_task_completed:
                                self._on_task_completed(task)
                    elif result:
                        error_msg = result.error or "Unknown error"
                        account.release_slot()
                        
                        if self._is_auth_error(error_msg):
                            # Auth error → attempt auto re-login
                            log.warning(f"Auth error for {account.email}: {error_msg}")
                            log.info(f"Attempting auto re-login for {account.email}...")
                            
                            relogin_ok = await self._try_auto_relogin(account.email, account)
                            
                            if relogin_ok:
                                log.info(f"✅ Re-login OK for {account.email}, re-queuing task {task.id}")
                                task.state = TaskState.READY
                                task.assigned_account = None
                                self._dispatcher.submit_task(task)
                            else:
                                log.error(f"❌ Re-login failed for {account.email}")
                                self._dispatcher.fail_task(
                                    task.id,
                                    f"{error_msg} (auto re-login failed)"
                                )
                                self._error_count += 1
                                if self._on_task_failed:
                                    self._on_task_failed(task, error_msg)
                        else:
                            # Non-auth error after all retries exhausted
                            retry_info = f" (after {task.retry_attempts} retries)" if task.retry_attempts > 0 else ""
                            final_error = f"{error_msg}{retry_info}"
                            log.error(f"Task {task.id} PERMANENTLY FAILED: {final_error}")
                            self._dispatcher.fail_task(task.id, final_error)
                            self._error_count += 1
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
                        account.release_slot()
                
                except Exception as inner_e:
                    # Release slot if still held due to error before the release point
                    try:
                        account.release_slot()
                    except Exception:
                        pass
                    raise inner_e
                
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
                        if self._on_task_failed:
                            self._on_task_failed(task, str(e))
                except Exception:
                    pass
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
                if task.stage == TaskStage.DOWNLOADED_720 and task.download_quality != "720p" and media_ids:
                    # Resume upscale
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
                if (self._continuation_enabled
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
                # Also include completed ops (some APIs need full list)
                for op_name in completed_results:
                    sid = ""
                    for i, on in enumerate(task.operation_names):
                        if on == op_name:
                            sid = task.scene_ids[i] if i < len(task.scene_ids) else ""
                            break
                    ops_to_poll.append({
                        "operation": {"name": op_name},
                        "sceneId": sid,
                        "status": "MEDIA_GENERATION_STATUS_SUCCESSFUL",
                    })
                
                # Risk 7 fix: Limit concurrent API calls per account
                sem = self._get_api_semaphore(account.email)
                async with sem:
                    response = await self._api_client.check_status(
                        access_token=account.get_access_token(),
                        recaptcha_token="",
                        operations=ops_to_poll,
                        account_headers=account.get_api_headers(),
                    )
                
                if not response.success:
                    continue
                
                response_ops = response.data.get("operations", [])
                if not response_ops:
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
                            task.video_outputs.append(vo)
                    
                    task.stage = TaskStage.GENERATED  # ★ Checkpoint: poll complete
                    
                    # === Stage: Download 720p originals (86%) ===
                    self._dispatcher.update_progress(task.id, 86, "⬇️ Downloading 720p")
                    local_720p = await self._download_outputs(
                        task, output_uris, quality_subfolder="720p",
                        generate_thumbnails=True,
                    )
                    
                    task.stage = TaskStage.DOWNLOADED_720  # ★ Checkpoint: 720p saved
                    
                    # === Stage: Auto-upscale if needed (88-92%) ===
                    upscale_paths = [None] * len(media_ids)  # None placeholders
                    if task.download_quality != "720p" and media_ids:
                        task.upscale_media_ids = list(media_ids)
                        self._dispatcher.update_progress(task.id, 88, "⬆️ Upscaling")
                        upscale_results = await self._auto_upscale(
                            task, account, output_uris, media_ids
                        )
                        if upscale_results:
                            # Download upscaled versions (only non-None)
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
                                # Map downloaded paths back to original indices
                                dl_idx = 0
                                for i, uri in enumerate(upscale_results):
                                    if uri and dl_idx < len(dl_paths):
                                        upscale_paths[i] = dl_paths[dl_idx]
                                        dl_idx += 1
                    
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
                        self._continuation_enabled
                        and self._dispatcher.has_children(task.id)
                        and output_uris
                    ):
                        frame_result = await self._extract_continuation_frame(
                            task, account, output_uris[0]
                        )
                        # Fix 3: Cooldown between parent's API burst and child's I2V submit
                        if frame_result:
                            continuation_frame_uri, continuation_frame_local = frame_result
                            cooldown = random.uniform(3.0, 5.0)
                            log.info(f"Continuation cooldown: {cooldown:.1f}s before releasing child")
                            await asyncio.sleep(cooldown)
                    
                    # === Stage: Complete (100%) ===
                    task.stage = TaskStage.COMPLETED  # ★ Checkpoint: all done
                    self._dispatcher.update_progress(task.id, 100, "✅ Done")
                    self._dispatcher.complete_task(
                        task.id,
                        output_uris=output_uris,
                        continuation_frame_uri=continuation_frame_uri,
                        continuation_frame_local_path=continuation_frame_local,
                    )
                    if self._on_task_completed:
                        self._on_task_completed(task)
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
                    
            except Exception:
                continue
        
        # Timeout
        self._dispatcher.fail_task(task.id, f"Polling timeout ({max_poll_time}s)")
    
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
            
            # 1. Download video to temp file
            import aiohttp
            import tempfile
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_uri) as resp:
                    if resp.status != 200:
                        log.error(f"Failed to download video: HTTP {resp.status}")
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
            loop = asyncio.get_event_loop()
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
                return None
            
            # 3. Base64 encode via MediaHandler for quality + format
            from core.media_handler import MediaHandler
            frame_result = MediaHandler.image_to_base64(frame_path)
            if not frame_result:
                log.error("Frame base64 encoding failed")
                Path(frame_path).unlink(missing_ok=True)
                return None
            frame_b64, frame_mime = frame_result
            
            # Keep frame file for UI thumbnail display (not deleted)
            
            # 4. Upload image to VEO API
            # Fix 2: Upload does NOT need reCAPTCHA (HAR verified).
            # Don't get/refresh reCAPTCHA here — it wastes single-use tokens
            # needed by the subsequent child I2V generation API call.
            # (Matching _resolve_image_paths() at line ~1445 which passes "")
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
                log.info(f"Continuation frame uploaded: {media_id}")
                return (media_id, frame_path)
            else:
                log.error(f"Frame upload failed: {upload_resp.error}")
                return None
            
        except Exception as e:
            log.error(f"Continuation frame pipeline error: {e}")
            return None
    
    def clear_upload_cache(self):
        """Clear the upload cache. Call between sessions/batches if needed."""
        self._upload_cache.clear()
        log.debug("[Engine] Upload cache cleared")
    
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
            log.info(f"  {len(uploaded_uris)} image(s) uploaded successfully")
    
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
        )
        
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
                                        task.video_outputs[idx].upscale_error = task.upscale_error
                    else:
                        if idx < len(task.video_outputs):
                            task.video_outputs[idx].upscale_status = "failed"
                            task.video_outputs[idx].upscale_error = task.upscale_error
                else:
                    # 4K poll FAILED → do NOT re-submit (costs credits)
                    if idx < len(task.video_outputs):
                        task.video_outputs[idx].upscale_status = "failed"
                        task.video_outputs[idx].upscale_error = task.upscale_error or "4K upscale failed"
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
    ) -> bool:
        """Re-upscale ALL failed videos in a completed task.
        
        Called from UI when user clicks the status column re-upscale button.
        Uses stored media_ids — only retries videos with upscale_status='failed'.
        """
        task = self._dispatcher.get_task(task_id)
        if not task or not task.upscale_media_ids:
            log.warning(f"Re-upscale {task_id}: no task or no media_ids")
            return False
        
        # Determine which videos need re-upscale
        failed_indices = []
        if task.video_outputs:
            failed_indices = [
                vo.index for vo in task.video_outputs
                if vo.upscale_status == "failed"
            ]
        else:
            # Backward compat: no video_outputs → retry all
            failed_indices = list(range(len(task.upscale_media_ids)))
        
        if not failed_indices:
            log.info(f"Re-upscale {task_id}: no failed videos")
            return True
        
        self._dispatcher.update_progress(task.id, 88, "⬆️ Re-upscaling failed videos...")
        
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
        if not task or not task.upscale_media_ids:
            log.warning(f"Re-upscale single {task_id}[{video_index}]: no task or no media_ids")
            return False
        
        if video_index >= len(task.upscale_media_ids):
            log.warning(f"Re-upscale single {task_id}[{video_index}]: index out of range")
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
        
        # Submit upscale
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
            task.video_outputs[video_index].upscale_error = task.upscale_error or "Poll failed"
        return False
    
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
    ) -> list:
        """Download output URIs to output_folder/project_name/quality_subfolder/.
        
        Folder structure (Option A):
          output_folder/project_name/720p/001a_..._720p.mp4
          output_folder/project_name/4K/001a_..._4K.mp4
        
        Naming convention:
        - Single output:   {NNN}_{timestamp}_{quality}.mp4
        - Multi output:    {NNN}{variant}_{timestamp}_{quality}.mp4
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
                                    ['ffmpeg', '-y', '-i', str(filepath),
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
    
    async def _try_auto_relogin(self, email: str, account: 'AccountManager') -> bool:
        """Attempt auto re-login via ProfilesController.
        
        Strategy:
        1. If debug browser is open → reload page to refresh session, extract
           fresh access_token from __NEXT_DATA__ (NO new browser needed)
        2. If no debug browser → close headless, launch new browser for re-login
        
        Returns:
            True if re-login succeeded and tokens updated
        """
        if not self._profiles_controller:
            log.warning("No ProfilesController — cannot auto re-login")
            return False
        
        # Per-account lock — only ONE worker attempts re-login at a time
        if email not in self._relogin_locks:
            self._relogin_locks[email] = asyncio.Lock()
        
        lock = self._relogin_locks[email]
        
        if lock.locked():
            log.info(f"Re-login already in progress for {email}, waiting...")
            async with lock:
                if account._browser_session and account._browser_session.is_ready:
                    return True
                return False
        
        async with lock:
            try:
                # ── Strategy 1: Debug browser is open → refresh token from existing page ──
                debug_page = self._profiles_controller.get_debug_browser_page(email)
                if debug_page:
                    log.info(f"[{email}] Debug browser open — refreshing token via page reload...")
                    
                    try:
                        # Send 'refresh_token' command via queue to reload page and re-extract token
                        entry = self._profiles_controller._debug_browsers.get(email) if hasattr(self._profiles_controller, '_debug_browsers') else None
                        if entry and entry.get("cmd_queue"):
                            entry["cmd_queue"].put("refresh_token")
                            
                            # Wait for token to be refreshed (up to 15 seconds)
                            loop = asyncio.get_event_loop()
                            for _ in range(30):
                                await asyncio.sleep(0.5)
                                # Check if fresh token is available
                                profile = self._profiles_controller.get_profile(email)
                                token = getattr(profile, "access_token", None) if profile else None
                                if token and len(token) > 100:
                                    account.update_access_token(token, expires_in=3599)
                                    log.info(f"[{email}] ✅ Access token refreshed from debug browser ({len(token)} chars)")
                                    
                                    # Re-attach to debug browser
                                    await account.ensure_browser(headless=True)
                                    return True
                        
                        # Token refresh via cmd_queue didn't work
                        # The debug browser cmd_queue runs on its own thread,
                        # so we CANNOT call page methods from here (different thread = greenlet crash).
                        # Fall through to Strategy 2 (full re-login).
                        log.warning(f"[{email}] Could not refresh token from debug browser — falling back to full re-login")
                        # DON'T return False — fall through to Strategy 2 below
                        
                    except Exception as e:
                        log.error(f"[{email}] Token refresh from debug browser failed: {e}")
                        # DON'T return False — fall through to Strategy 2 below
                
                # ── Strategy 2: No debug browser → full re-login with credentials ──
                log.info(f"Closing Engine browser for {email} before re-login...")
                await account.close_browser()
                
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self._profiles_controller.auto_relogin,
                    email,
                )
                
                if result:
                    log.info(f"Auto re-login OK for {email}, updating account tokens")
                    profile = self._profiles_controller.get_profile(email)
                    access_token = getattr(profile, "access_token", None) if profile else None
                    if access_token:
                        account.update_access_token(
                            access_token,
                            expires_in=getattr(profile, "expires_in", 3599),
                        )
                    
                    log.info(f"Re-opening headless browser for {email}...")
                    try:
                        await account.ensure_browser(headless=True)
                    except Exception as e:
                        log.warning(f"Browser re-open failed for {email}: {e}")
                    
                    return True
                
                # Re-login failed — still re-open browser for reCAPTCHA attempts
                log.warning(f"Re-login failed for {email}, re-opening browser anyway")
                try:
                    await account.ensure_browser(headless=True)
                except Exception:
                    pass
                return False
                
            except Exception as e:
                log.error(f"Auto re-login error for {email}: {e}")
                try:
                    await account.ensure_browser(headless=True)
                except Exception:
                    pass
                return False
    
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
