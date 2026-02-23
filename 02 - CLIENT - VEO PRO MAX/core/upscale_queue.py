"""
VEO Pro Max - UpscaleQueue

Decouples upscale processing from worker slots.
Workers release their slot immediately after 720p download,
then enqueue upscale jobs here for background processing.

This enables ~3x throughput: workers can process new prompts
while upscales run in the background (~3-5 min each).

Architecture ref: ENGINE_PIPELINE_ARCHITECTURE.md §11 — Component 3A
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, TYPE_CHECKING

from core.event_manager import emit_event, EventType

if TYPE_CHECKING:
    from core.dispatcher import Dispatcher, Task
    from core.account_manager import AccountManager

log = logging.getLogger(__name__)


class AdaptiveBurstController:
    """Adaptive concurrency controller for upscale polling.
    
    Controls how many upscale poll operations can run globally at once.
    Scales up on sustained success, backs off immediately on errors.
    
    Scale ladder: 4 → 8 → 12 → 16 → 20 (step=4)
    Scale up: 8 consecutive poll successes → +4
    Back off: any 403/error → -4 (floor=4)
    """
    
    INITIAL = 4
    STEP = 4
    MAX = 20
    MIN = 4
    SCALE_UP_THRESHOLD = 8  # consecutive successes before increase
    
    def __init__(self):
        self._max_polls = self.INITIAL
        self._poll_semaphore = asyncio.Semaphore(self._max_polls)
        self._consecutive_success = 0
        self._lock = asyncio.Lock()
        self._active_polls = 0
        log.info(f"[BurstCtrl] Initialized: max_polls={self._max_polls}")
    
    @property
    def max_polls(self) -> int:
        return self._max_polls
    
    @property
    def active_polls(self) -> int:
        return self._active_polls
    
    async def acquire(self):
        """Acquire a poll slot. Blocks if at capacity."""
        await self._poll_semaphore.acquire()
        self._active_polls += 1
    
    def release(self):
        """Release a poll slot."""
        self._active_polls = max(0, self._active_polls - 1)
        self._poll_semaphore.release()
    
    async def record_success(self):
        """Record a successful poll. Scale up after threshold."""
        async with self._lock:
            self._consecutive_success += 1
            if self._consecutive_success >= self.SCALE_UP_THRESHOLD:
                old = self._max_polls
                new = min(old + self.STEP, self.MAX)
                if new > old:
                    # Add new permits to semaphore
                    for _ in range(new - old):
                        self._poll_semaphore.release()
                    self._max_polls = new
                    log.info(
                        f"[BurstCtrl] ⬆️ Scale UP: {old} → {new} polls "
                        f"(after {self._consecutive_success} successes)"
                    )
                self._consecutive_success = 0
    
    async def record_failure(self):
        """Record a poll failure. Back off immediately."""
        async with self._lock:
            self._consecutive_success = 0
            old = self._max_polls
            new = max(old - self.STEP, self.MIN)
            if new < old:
                # Reduce permits by acquiring them (non-blocking best effort)
                reduced = 0
                for _ in range(old - new):
                    # Try to acquire without blocking — if slots are in use,
                    # the reduction takes effect gradually as slots are released
                    try:
                        self._poll_semaphore._value = max(0, self._poll_semaphore._value - 1)
                        reduced += 1
                    except Exception:
                        break
                self._max_polls = new
                log.warning(
                    f"[BurstCtrl] ⬇️ Scale DOWN: {old} → {new} polls "
                    f"(error detected, reduced {reduced} permits)"
                )
    
    def get_stats(self) -> dict:
        return {
            "max_polls": self._max_polls,
            "active_polls": self._active_polls,
            "consecutive_success": self._consecutive_success,
        }


class AdaptiveJobController:
    """Per-account adaptive concurrency for upscale jobs.
    
    AIMD algorithm: Start at INITIAL, increase by 1 after
    SCALE_UP_AFTER consecutive successes per account,
    halve on failure. Floor=MIN, Ceiling=MAX.
    
    This adapts to reCAPTCHA token availability per account:
    - Stable tokens → more concurrent upscale jobs
    - 403 / failures → back off to reduce contention
    """
    
    INITIAL = 4
    MIN = 2
    MAX = 8
    SCALE_UP_AFTER = 3  # consecutive successes before +1
    
    def __init__(self):
        self._limits: Dict[str, int] = {}      # email → current limit
        self._streaks: Dict[str, int] = {}     # email → consecutive successes
    
    def get_limit(self, email: str) -> int:
        """Get current concurrent job limit for account."""
        return self._limits.get(email, self.INITIAL)
    
    def record_success(self, email: str):
        """Record successful job. Scale up after sustained streak."""
        self._streaks[email] = self._streaks.get(email, 0) + 1
        if self._streaks[email] >= self.SCALE_UP_AFTER:
            old = self.get_limit(email)
            new = min(old + 1, self.MAX)
            self._limits[email] = new
            self._streaks[email] = 0
            if new != old:
                log.info(f"[JobCtrl] {email}: ↑ limit {old}→{new} (streak={self.SCALE_UP_AFTER})")
    
    def record_failure(self, email: str):
        """Record failed job. Halve limit immediately."""
        old = self.get_limit(email)
        new = max(old // 2, self.MIN)
        self._limits[email] = new
        self._streaks[email] = 0
        if new != old:
            log.info(f"[JobCtrl] {email}: ↓ limit {old}→{new} (failure)")
    
    def get_stats(self) -> dict:
        return {
            "limits": dict(self._limits),
            "streaks": dict(self._streaks),
        }


@dataclass
class UpscaleJob:
    """A pending upscale job, created when worker finishes 720p download."""
    task_id: str
    account_email: str
    media_ids: List[str]            # Base64 media IDs for upscale API
    output_uris: List[str]          # Original 720p fifeUrls (for logging)
    target_quality: str             # "1080p" or "4K"
    aspect_ratio: str
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0            # Job-level retry counter
    max_retries: int = 3            # Max job-level retries before permanent fail
    retry_indices: List[int] = field(default_factory=list)  # Which video indices to retry (empty = all)


class UpscaleQueue:
    """Per-account background upscale processor.
    
    Design:
    - One async worker per account (created on first job)
    - Sequential submit (needs reCAPTCHA) → parallel poll (no reCAPTCHA)
    - Shares engine's rate locks + API semaphores for safety
    - On completion: updates task.video_outputs, downloads upscaled files,
      syncs overall status, and fires TASK_COMPLETED event
    
    Dependency Injection (Cluster #1 fix):
    - All engine dependencies injected via constructor (full DI)
    - No engine reference stored — fully decoupled
    """
    
    def __init__(
        self,
        dispatcher: 'Dispatcher',
        api_client: 'VEOApiClient',
        poll_fn: Callable,               # engine._poll_upscale
        download_fn: Callable,           # engine._download_outputs
        wait_recaptcha_fn: Callable,     # engine._wait_for_recaptcha_ready
        sync_status_fn: Callable,        # engine._sync_overall_upscale_status
        semaphore_fn: Callable,          # engine._get_upscale_api_semaphore
        rate_locks: Dict,                # engine._account_rate_locks
        # --- Account & cooldown (replaces engine public API) ---
        get_account_fn: Callable,        # engine.get_account
        get_all_accounts_fn: Callable,   # engine.get_all_accounts
        is_on_cooldown_fn: Callable,     # engine.is_account_on_cooldown
        wait_cooldown_fn: Callable,      # engine.wait_for_cooldown
        set_cooldown_fn: Callable,       # engine.set_account_cooldown
        clear_cooldown_fn: Callable,     # engine.clear_account_cooldown
        fix_client_data_fn: Callable,    # engine.fix_client_data
        should_wait_fn: Callable,        # engine.should_upscale_wait
        wait_for_circuit_fn: Callable,   # engine._wait_for_circuit (Fix C)
        burst_controller=None,           # engine._burst_controller (anti-detect delay)
        on_completed: Optional[Callable] = None,   # engine._on_task_completed
        profiles_controller=None,        # engine._profiles_controller
        extension_bridge=None,           # engine._extension_bridge
    ):
        """
        Fully decoupled UpscaleQueue — no engine reference.
        
        Args:
            dispatcher: Task queue manager (progress, complete, get_task)
            api_client: VEO API client (upscale_video)
            poll_fn: async fn(task, account, label, op_name, scene_id) → result
            download_fn: async fn(task, uris, **kw) → paths
            wait_recaptcha_fn: async fn(account, max_wait) → None
            sync_status_fn: fn(task) → None
            semaphore_fn: fn(email) → asyncio.Semaphore
            rate_locks: Dict[str, asyncio.Lock] — per-account rate locks
            get_account_fn: fn(email) → Account or None
            get_all_accounts_fn: fn() → list[Account]
            is_on_cooldown_fn: fn(email) → bool
            wait_cooldown_fn: async fn(email) → None
            set_cooldown_fn: fn(email, reason) → None
            clear_cooldown_fn: fn(email) → None
            fix_client_data_fn: fn() → None
            should_wait_fn: fn() → bool
            wait_for_circuit_fn: async fn(email) → None — wait for CB CLOSED
            on_completed: optional callback fn(task) for UI refresh
            profiles_controller: optional profiles controller for reset
            extension_bridge: optional extension bridge for reCAPTCHA
        """
        # Injected dependencies (full DI — no engine reference)
        self._dispatcher = dispatcher
        self._api_client = api_client
        self._poll_fn = poll_fn
        self._download_fn = download_fn
        self._wait_recaptcha_fn = wait_recaptcha_fn
        self._sync_status_fn = sync_status_fn
        self._semaphore_fn = semaphore_fn
        self._rate_locks = rate_locks
        self._get_account = get_account_fn
        self._get_all_accounts = get_all_accounts_fn
        self._is_on_cooldown = is_on_cooldown_fn
        self._wait_cooldown = wait_cooldown_fn
        self._set_cooldown = set_cooldown_fn
        self._clear_cooldown = clear_cooldown_fn
        self._fix_client_data = fix_client_data_fn
        self._should_wait = should_wait_fn
        self._wait_for_circuit = wait_for_circuit_fn  # Fix C: CB gate
        self._burst_controller = burst_controller     # Anti-detect delay
        self._on_completed = on_completed
        self._profiles_controller = profiles_controller
        self._extension_bridge = extension_bridge
        
        self._queues: Dict[str, asyncio.Queue] = {}      # email → Queue[UpscaleJob]
        self._workers: Dict[str, asyncio.Task] = {}       # email → background task
        self._running = False
        
        # Adaptive burst controller (global across all accounts)
        self._burst = AdaptiveBurstController()
        
        # Per-account adaptive job concurrency (AIMD)
        self._job_controller = AdaptiveJobController()
        
        # Stats
        self._total_enqueued = 0
        self._total_completed = 0
        self._total_failed = 0
    
    def start(self):
        """Mark queue as running."""
        self._running = True
        log.info("[UpscaleQueue] Started — background upscale decoupled from workers")
    
    def stop(self):
        """Stop all background workers gracefully."""
        self._running = False
        # Cancel all worker tasks
        for email, task in self._workers.items():
            if not task.done():
                task.cancel()
                log.info(f"[UpscaleQueue] Cancelled worker for {email}")
        self._workers.clear()
        log.info(
            f"[UpscaleQueue] Stopped — "
            f"completed={self._total_completed}, failed={self._total_failed}"
        )
    
    def enqueue(self, job: UpscaleJob):
        """Add an upscale job for background processing.
        
        Creates per-account worker if not already running.
        """
        email = job.account_email
        
        # Create per-account queue if needed
        if email not in self._queues:
            self._queues[email] = asyncio.Queue()
        
        self._queues[email].put_nowait(job)
        self._total_enqueued += 1
        
        # Start per-account worker if not already running
        if email not in self._workers or self._workers[email].done():
            self._workers[email] = asyncio.create_task(
                self._worker_loop(email)
            )
            log.info(f"[UpscaleQueue] Started worker for {email}")
        
        log.info(
            f"[UpscaleQueue] Enqueued upscale for task {job.task_id} "
            f"({len(job.media_ids)} videos, {job.target_quality}) → {email}"
        )
    
    def has_active_jobs(self, email: str) -> bool:
        """Check if any upscale jobs are actively processing for this account.
        
        Used by engine to defer browser restart during upscale polling (Bug #5).
        """
        if email not in self._workers:
            return False
        worker_task = self._workers[email]
        if worker_task.done():
            return False
        # Worker is running — check if there are queued or in-progress jobs
        q = self._queues.get(email)
        return q is not None and not q.empty()
    
    async def _worker_loop(self, email: str):
        """Background worker: processes upscale jobs for one account.
        
        Concurrent model: launches jobs as fire-and-forget tasks,
        allowing multiple tasks to poll in parallel. The global
        AdaptiveBurstController limits total concurrent polls.
        """
        q = self._queues[email]
        active_jobs: List[asyncio.Task] = []
        
        while self._running:
            try:
                # Clean up completed job tasks
                active_jobs = [t for t in active_jobs if not t.done()]
                
                # Workload priority: pause if prompts_first mode active
                if self._should_wait():
                    log.info(f"[UpscaleQueue] {email}: pausing — prompts_first priority")
                    await asyncio.sleep(5)
                    continue
                
                # Fix G6: Force sequential — only 1 job at a time per account
                # All upscale submits must go through anti-detect delay
                max_jobs = 1
                if len(active_jobs) >= max_jobs:
                    if active_jobs:
                        done, _ = await asyncio.wait(
                            active_jobs, return_when=asyncio.FIRST_COMPLETED
                        )
                        # Log any exceptions from completed jobs
                        for t in done:
                            if t.exception():
                                log.error(f"[UpscaleQueue] Job error: {t.exception()}")
                        active_jobs = [t for t in active_jobs if not t.done()]
                    continue
                
                # Account cooldown: wait if on cooldown before picking up jobs
                if self._is_on_cooldown(email):
                    await self._wait_cooldown(email)
                
                # Wait for next job (with timeout to allow graceful shutdown)
                try:
                    job = await asyncio.wait_for(q.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    if q.empty() and not active_jobs:
                        break  # No more jobs AND no active jobs → worker exits
                    continue
                
                # Launch job concurrently (don't await — fire and forget)
                task = asyncio.create_task(
                    self._process_job(job),
                    name=f"upscale-{job.task_id[:8]}"
                )
                active_jobs.append(task)
                log.info(
                    f"[UpscaleQueue] {email}: launched job {job.task_id[:8]} "
                    f"(active={len(active_jobs)}, burst={self._burst.active_polls}/{self._burst.max_polls})"
                )
                
            except asyncio.CancelledError:
                log.info(f"[UpscaleQueue] Worker {email} cancelled")
                # Cancel all active jobs
                for t in active_jobs:
                    t.cancel()
                break
            except Exception as e:
                log.error(f"[UpscaleQueue] Worker {email} error: {e}")
                await asyncio.sleep(5)
        
        # Wait for remaining active jobs
        if active_jobs:
            log.info(f"[UpscaleQueue] Worker {email}: waiting for {len(active_jobs)} active jobs")
            await asyncio.gather(*active_jobs, return_exceptions=True)
        
        log.info(f"[UpscaleQueue] Worker {email} exiting")
    
    async def _process_job(self, job: UpscaleJob):
        """Process a single upscale job with parallel polling.
        
        3-phase pipeline (submit-seq → poll-parallel → batch-download):
        
        Phase 1 — Sequential Submit (needs reCAPTCHA per video):
          For each video: rate-lock → reCAPTCHA → submit → collect op_name
          
        Phase 2 — Parallel Poll (no reCAPTCHA needed):
          All videos polled simultaneously via asyncio.gather
          
        Phase 3 — Batch Download:
          Download all successfully upscaled videos
        
        Time savings: ~12min (sequential) → ~5min (parallel poll)
        """
        task = self._dispatcher.get_task(job.task_id)
        if not task:
            log.warning(f"[UpscaleQueue] Task {job.task_id} not found, skipping")
            self._total_failed += 1
            return
        
        # Get the account
        account = self._get_account(job.account_email)
        if not account:
            log.warning(f"[UpscaleQueue] Account {job.account_email} not found, skipping")
            self._total_failed += 1
            return
        
        # Auto-inject extension bridge if missing (can happen after browser restart)
        if not account.extension_bridge:
            bridge = self._extension_bridge
            # Fallback: steal from sibling account that has it
            if not bridge:
                for acc in self._get_all_accounts():
                    if acc.extension_bridge:
                        bridge = acc.extension_bridge
                        break
            if bridge:
                account.extension_bridge = bridge
                log.info(f"[UpscaleQueue] Injected extension bridge into {job.account_email}")
            else:
                log.warning(f"[UpscaleQueue] No extension bridge source found — reCAPTCHA will fail")
        
        total = len(job.media_ids)
        
        # BUG 1 FIX: Wait for account cooldown BEFORE submitting
        # Without this, concurrent upscale jobs submit during cooldown → 403 → extend cooldown
        if self._is_on_cooldown(job.account_email):
            log.info(f"[UpscaleQueue] {job.account_email}: on cooldown, waiting before upscale (task {job.task_id})")
            await self._wait_cooldown(job.account_email)
        
        log.info(
            f"[UpscaleQueue] Processing task {job.task_id}: "
            f"{total} videos → {job.target_quality} (parallel poll)"
        )
        
        # Fix C: CircuitBreaker gate — wait for circuit CLOSED before submitting.
        # Without this, upscale submits during a 403 storm would compound the problem:
        # each upscale needs reCAPTCHA → if CB is OPEN, those tokens are wasted.
        try:
            await self._wait_for_circuit(job.account_email)
        except Exception as e:
            log.warning(f"[UpscaleQueue] Circuit wait error for {job.account_email}: {e}")
        
        # Proactive token check
        # Gap #2 fix: Use centralized ensure_valid_token() for refresh
        valid_token = await account.ensure_valid_token()
        if not valid_token:
            log.error(f"[UpscaleQueue] Token refresh failed — skipping upscale")
            for vo in task.video_outputs:
                vo.upscale_status = "failed"
                vo.upscale_error = "Access token expired, refresh failed"
            task.upscale_error = "Access token expired"
            self._dispatcher.update_progress(
                task.id, 90, "⚠️ Upscale skipped (auth expired)"
            )
            self._sync_status_fn(task)
            self._total_failed += 1
            return
        
        # Store media IDs on task for re-upscale support
        task.upscale_media_ids = list(job.media_ids)
        
        # Resolution mapping
        quality_map = {
            "1080p": "VIDEO_RESOLUTION_1080P",
            "4K": "VIDEO_RESOLUTION_4K",
        }
        resolution = quality_map.get(job.target_quality)
        if not resolution:
            return
        is_free_upscale = (resolution == "VIDEO_RESOLUTION_1080P")
        from core.api_client import generate_random_seed
        import hashlib  # Gap #5: idempotency key for upscale
        
        # =====================================================
        # PHASE 1: Sequential Submit (reCAPTCHA per video)
        # =====================================================
        # Mark all target videos as submitting for UI overlay
        # For retry jobs, only mark the retried indices
        target_indices = job.retry_indices if job.retry_indices else list(range(total))
        for vi in target_indices:
            if vi < len(task.video_outputs) and vi < total:
                if not job.retry_indices or job.media_ids[target_indices.index(vi)]:
                    task.video_outputs[vi].upscale_status = "submitting"
        submit_label = f"{len(target_indices)}" if job.retry_indices else f"{total}"
        self._dispatcher.update_progress(
            task.id, 88, f"⬆️ Submitting {submit_label} upscales...")
        if self._on_completed:
            try:
                self._on_completed(task)  # Trigger UI refresh
            except Exception:
                pass
        
        # Collect: (idx, op_name, scene_id) for successful submits
        pending_ops = []  # list of (orig_idx, op_name, scene_id, media_id)
        max_submit_retries = 5
        
        for local_idx, media_id in enumerate(job.media_ids):
            # Map local index back to original video_outputs position
            orig_idx = job.retry_indices[local_idx] if job.retry_indices else local_idx
            video_label = f"{orig_idx + 1}/{len(task.video_outputs)}"
            if not media_id:
                log.warning(f"Upscale {video_label}: no mediaId, skipping")
                if orig_idx < len(task.video_outputs):
                    task.video_outputs[orig_idx].upscale_status = "skipped"
                continue
            
            try:
                # Submit with retry
                resp = None
                for attempt in range(max_submit_retries):
                    # BUG 1 FIX: Check cooldown before each retry attempt
                    if attempt > 0 and self._is_on_cooldown(job.account_email):
                        await self._wait_cooldown(job.account_email)
                    
                    # Fix G6: Acquire per-account rate lock + anti-detect delay
                    # Same mechanism as engine — serialize API calls with adaptive delay
                    email = job.account_email
                    if email not in self._rate_locks:
                        self._rate_locks[email] = asyncio.Lock()
                    
                    async with self._rate_locks[email]:
                        # Re-check cooldown inside lock (another worker may have set it)
                        if self._is_on_cooldown(email):
                            log.info(f"Upscale {video_label}: cooldown detected inside rate lock")
                            await self._wait_cooldown(email)
                        
                        # Anti-detect delay (adaptive burst controller)
                        if self._burst_controller:
                            bc_delay = self._burst_controller.get_delay(email)
                            log.info(
                                f"Upscale {video_label}: anti-detect delay "
                                f"({bc_delay:.1f}s) → attempt {attempt+1}/{max_submit_retries}"
                            )
                            await self._burst_controller.wait(email)
                    
                    # Bug #3 fix: Use recaptcha_lock to serialize with engine workers
                    async with account.recaptcha_lock:
                        recaptcha_token = await account.refresh_recaptcha() or ""
                    if not recaptcha_token:
                        recaptcha_token = account.get_recaptcha_token() or ""
                    
                    # Fix 3: Validate token quality — 330-char tokens are garbage
                    # from uninitialized grecaptcha widget after browser restart
                    if recaptcha_token and len(recaptcha_token) < 500:
                        log.warning(
                            f"Upscale {video_label}: garbage reCAPTCHA token "
                            f"({len(recaptcha_token)} chars < 500), skipping submit"
                        )
                        account.invalidate_recaptcha()
                        if attempt < max_submit_retries - 1:
                            delay = min(5 * (attempt + 1), 15)
                            await asyncio.sleep(delay)
                        continue
                    
                    # Gap #5: Stable seed per (task, media, attempt) to prevent duplicate jobs
                    idem_hash = hashlib.sha256(
                        f"{task.id}:{media_id}:{attempt}".encode()
                    ).hexdigest()
                    stable_seed = int(idem_hash[:8], 16) % (2**31)
                    
                    # ★ PRIMARY PATH: Extension-based upscale
                    ext_bridge = getattr(account, 'extension_bridge', None)
                    use_ext = (ext_bridge and ext_bridge.is_connected(account.email))
                    
                    if use_ext:
                        upscale_body = self._api_client.build_upscale_body(
                            video_media_id=media_id,
                            target_resolution=resolution,
                            aspect_ratio=task.aspect_ratio,
                            seed=stable_seed,
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
                        # ★ FALLBACK: Traditional aiohttp path
                        sem = self._semaphore_fn(account.email)
                        async with sem:
                            resp = await self._api_client.upscale_video(
                                access_token=account.get_access_token() or "",
                                recaptcha_token=recaptcha_token,
                                video_media_id=media_id,
                                target_resolution=resolution,
                                aspect_ratio=task.aspect_ratio,
                                seed=stable_seed,
                                account_headers=account.get_api_headers(),
                            )
                    account.invalidate_recaptcha()
                    await asyncio.sleep(1.0)
                    
                    if resp.success:
                        self._clear_cooldown(job.account_email)
                        break
                    
                    log.warning(
                        f"Upscale {video_label} submit attempt {attempt + 1}/{max_submit_retries} "
                        f"failed: {resp.error}"
                    )
                    
                    # Fix 1+2: Browser recovery on reCAPTCHA/403 failures
                    # Widened detection: HTTP 403 may not mention 'recaptcha'
                    error_lower = (resp.error or "").lower()
                    is_403 = "403" in error_lower
                    if "recaptcha" in error_lower or is_403:
                        # Set account cooldown on 403
                        if is_403:
                            self._set_cooldown(
                                job.account_email, f"upscale submit 403"
                            )
                            # Wait for cooldown before next attempt
                            await self._wait_cooldown(job.account_email)
                        
                        # GUARD: Only do browser recovery if NO videos submitted OK yet.
                        # If pending_ops has successes, recovery would disrupt their polls.
                        if not pending_ops:
                            if attempt == 1:
                                # M3 Phase 1: Gentle recovery — reload pages
                                try:
                                    await account.soft_recover_browser()
                                    await asyncio.sleep(8)
                                    await self._wait_recaptcha_fn(
                                        account, max_wait=20.0
                                    )
                                except Exception:
                                    pass
                            elif attempt == 2:
                                # M3 Phase 2: Hard recovery — full browser restart
                                try:
                                    await account.restart_browser()
                                    self._fix_client_data()
                                    await asyncio.sleep(10)
                                    await self._wait_recaptcha_fn(
                                        account, max_wait=30.0
                                    )
                                except Exception:
                                    pass
                            elif attempt >= 3:
                                # M3 Phase 3: Profile reset — most aggressive
                                # Matches engine's recovery state machine Phase 2
                                try:
                                    log.warning(
                                        f"Upscale {video_label}: attempt {attempt+1} — "
                                        f"escalating to profile reset for {account.email}"
                                    )
                                    profiles_ctrl = self._profiles_controller
                                    if profiles_ctrl and hasattr(profiles_ctrl, 'reset_profile'):
                                        await profiles_ctrl.reset_profile(account)
                                        self._fix_client_data()
                                        await asyncio.sleep(15)
                                        await self._wait_recaptcha_fn(
                                            account, max_wait=40.0
                                        )
                                    else:
                                        # Fallback: restart browser again
                                        await account.restart_browser()
                                        self._fix_client_data()
                                        await asyncio.sleep(10)
                                        await self._wait_recaptcha_fn(
                                            account, max_wait=30.0
                                        )
                                except Exception as e:
                                    log.error(f"Upscale {video_label}: profile reset failed: {e}")
                                    pass
                        else:
                            # Videos already submitted — skip recovery, just mark this one failed
                            log.warning(
                                f"Upscale {video_label}: 403 but {len(pending_ops)} videos already "
                                f"submitted OK — skipping browser recovery to protect them"
                            )
                            if orig_idx < len(task.video_outputs):
                                task.video_outputs[orig_idx].upscale_status = "failed"
                                task.video_outputs[orig_idx].upscale_error = f"403 (skipped recovery — {len(pending_ops)} videos OK)"
                            break  # Exit retry loop for this video, proceed to Phase 2
                    
                    if attempt < max_submit_retries - 1:
                        delay = min(5 * (attempt + 1), 15)
                        await asyncio.sleep(delay)
                else:
                    # All submit retries exhausted for this video
                    if orig_idx < len(task.video_outputs):
                        task.video_outputs[orig_idx].upscale_status = "failed"
                        task.video_outputs[orig_idx].upscale_error = f"Submit failed after {max_submit_retries} retries"
                    continue
                
                # Extract operation ID
                ops = resp.data.get("operations", [])
                if not ops:
                    if orig_idx < len(task.video_outputs):
                        task.video_outputs[orig_idx].upscale_status = "failed"
                        task.video_outputs[orig_idx].upscale_error = "No operation returned"
                    continue
                
                op_name = ops[0].get("operation", {}).get("name", "")
                scene_id = ops[0].get("sceneId", "")
                if not op_name:
                    if orig_idx < len(task.video_outputs):
                        task.video_outputs[orig_idx].upscale_status = "failed"
                    continue
                
                log.info(f"[UpscaleQueue] Upscale {video_label} submitted: op={op_name}")
                if orig_idx < len(task.video_outputs):
                    task.video_outputs[orig_idx].upscale_status = "polling"
                pending_ops.append((orig_idx, op_name, scene_id, media_id))
                # Update progress per-video submit
                submitted = len(pending_ops)
                self._dispatcher.update_progress(
                    task.id, 88, f"⬆️ Submitted {submitted}/{len(target_indices)} upscales"
                )
                
            except Exception as e:
                if orig_idx < len(task.video_outputs):
                    task.video_outputs[orig_idx].upscale_status = "failed"
                    task.video_outputs[orig_idx].upscale_error = str(e)
                log.error(f"Upscale {video_label} submit error: {e}")
        
        # ── Identify failed video indices for potential partial retry ──
        # For retry jobs, check only the target indices; for fresh jobs, check all
        check_indices = target_indices
        failed_indices = [
            i for i in check_indices
            if i < len(task.video_outputs)
            and task.video_outputs[i].upscale_status == "failed"
        ]
        
        if not pending_ops:
            # ALL submits failed — try full job retry
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                retry_delay = 30 * (2 ** (job.retry_count - 1))
                log.warning(
                    f"[UpscaleQueue] No successful submits for task {job.task_id} — "
                    f"re-enqueue attempt {job.retry_count}/{job.max_retries} "
                    f"in {retry_delay}s"
                )
                # Reset ONLY the failed videos for retry
                for i in failed_indices:
                    task.video_outputs[i].upscale_status = "pending"
                    task.video_outputs[i].upscale_error = ""
                self._dispatcher.update_progress(
                    task.id, 87, f"🔁 Upscale retry {job.retry_count}/{job.max_retries} in {retry_delay}s..."
                )
                if self._on_completed:
                    try:
                        self._on_completed(task)
                    except Exception:
                        pass
                await asyncio.sleep(retry_delay)
                self.enqueue(job)
                return
            
            log.warning(f"[UpscaleQueue] All retries exhausted for task {job.task_id}")
            self._sync_status_fn(task)
            self._total_failed += 1
            from core.dispatcher import TaskStage
            task.stage = TaskStage.COMPLETED
            self._dispatcher.update_progress(task.id, 100, "⚠️ Upscale failed — 720p saved")
            self._dispatcher.complete_task(
                task.id, output_uris=task.output_uris or [],
            )
            if self._on_completed:
                try:
                    self._on_completed(task)
                except Exception as e:
                    log.error(f"[UpscaleQueue] UI callback error: {e}")
            return
        
        # ── PARTIAL RETRY: Some submitted OK, some failed ──
        # Schedule retry job for ONLY the failed indices (don't wait for it)
        if failed_indices and job.retry_count < job.max_retries:
            retry_media_ids = [job.media_ids[i] for i in failed_indices]
            retry_job = UpscaleJob(
                task_id=job.task_id,
                account_email=job.account_email,
                media_ids=retry_media_ids,
                output_uris=job.output_uris,
                target_quality=job.target_quality,
                aspect_ratio=job.aspect_ratio,
                retry_count=job.retry_count + 1,
                max_retries=job.max_retries,
                retry_indices=failed_indices,  # Map back to original positions
            )
            retry_delay = 30 * (2 ** job.retry_count)
            log.info(
                f"[UpscaleQueue] Partial retry: {len(failed_indices)} failed videos "
                f"(indices {failed_indices}) will retry in {retry_delay}s. "
                f"{len(pending_ops)} videos proceeding to poll now."
            )
            # Reset failed statuses for upcoming retry
            for i in failed_indices:
                task.video_outputs[i].upscale_status = "pending"
                task.video_outputs[i].upscale_error = ""
            
            async def _delayed_retry():
                await asyncio.sleep(retry_delay)
                self.enqueue(retry_job)
            asyncio.create_task(_delayed_retry())
        
        # =====================================================
        # PHASE 2: Parallel Poll (all videos simultaneously)
        # =====================================================
        self._dispatcher.update_progress(
            task.id, 90, f"🔄 Polling {len(pending_ops)} upscales in parallel..."
        )
        log.info(
            f"[UpscaleQueue] Phase 2: Polling {len(pending_ops)} operations in parallel"
        )
        
        async def _poll_one(idx: int, op_name: str, scene_id: str, media_id: str):
            """Poll a single upscale operation with burst-controlled concurrency.
            
            Acquires global poll semaphore before polling. Reports success/failure
            to AdaptiveBurstController for adaptive scaling.
            """
            video_label = f"{idx + 1}/{total}"
            
            # Acquire burst-controlled poll slot
            await self._burst.acquire()
            try:
                result = await self._poll_fn(
                    task, account, video_label, op_name, scene_id
                )
                
                if result:
                    if idx < len(task.video_outputs):
                        task.video_outputs[idx].upscale_status = "success"
                    await self._burst.record_success()
                    return (idx, result[0])
                
                # Poll failed — record failure for adaptive scaling
                error_text = getattr(task, 'upscale_error', '') or ''
                if '403' in error_text or 'rate' in error_text.lower():
                    await self._burst.record_failure()
                
                # Try re-submit once for 1080p (free)
                if is_free_upscale:
                    log.info(f"Upscale {video_label}: 1080p poll failed, re-submitting (free)")
                    try:
                        if account.email not in self._rate_locks:
                            self._rate_locks[account.email] = asyncio.Lock()
                        async with self._rate_locks[account.email]:
                            # Fix G7: Anti-detect delay before upscale re-submit
                            if self._burst_controller:
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
                                # ★ FALLBACK: Traditional aiohttp path
                                recaptcha_token = await account.refresh_recaptcha() or ""
                                sem = self._semaphore_fn(account.email)
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
                                    result2 = await self._poll_fn(
                                        task, account, video_label, op2, sid2
                                    )
                                    if result2:
                                        if idx < len(task.video_outputs):
                                            task.video_outputs[idx].upscale_status = "success"
                                        await self._burst.record_success()
                                        return (idx, result2[0])
                    except Exception as e:
                        log.error(f"Upscale {video_label} re-submit error: {e}")
                        await self._burst.record_failure()
                
                # Failed
                if idx < len(task.video_outputs):
                    task.video_outputs[idx].upscale_status = "failed"
                    task.video_outputs[idx].upscale_error = task._upscale_error or "Poll failed"
                return (idx, None)
            finally:
                self._burst.release()
        
        # Fire all polls in parallel
        poll_tasks = [
            _poll_one(idx, op_name, scene_id, media_id)
            for idx, op_name, scene_id, media_id in pending_ops
        ]
        poll_results = await asyncio.gather(*poll_tasks, return_exceptions=True)
        
        # Collect upscaled URIs
        upscaled_uris = [None] * total
        for result in poll_results:
            if isinstance(result, Exception):
                log.error(f"[UpscaleQueue] Poll task exception: {result}")
                continue
            idx, uri = result
            upscaled_uris[idx] = uri
        
        # =====================================================
        # PHASE 3: Batch Download
        # =====================================================
        upscale_paths = [None] * total
        uris_to_download = [(i, u) for i, u in enumerate(upscaled_uris) if u]
        
        if uris_to_download:
            self._dispatcher.update_progress(
                task.id, 95, f"⬇️ Downloading {len(uris_to_download)} upscaled videos"
            )
            dl_uris = [u for _, u in uris_to_download]
            dl_paths = await self._download_fn(
                task, dl_uris,
                quality_subfolder=job.target_quality,
                generate_thumbnails=False,
            )
            # Map back to original indices
            for dl_idx, (orig_idx, _) in enumerate(uris_to_download):
                if dl_idx < len(dl_paths):
                    upscale_paths[orig_idx] = dl_paths[dl_idx]
        
        # Merge upscaled paths with existing 720p paths
        for i in range(len(task.video_outputs)):
            if i < len(upscale_paths) and upscale_paths[i]:
                task.video_outputs[i].file_upscaled = upscale_paths[i]
                task.video_outputs[i].quality = job.target_quality
        
        # Update final output_uris (prefer upscaled)
        final_paths = []
        for i, vo in enumerate(task.video_outputs):
            if vo.file_upscaled:
                final_paths.append(vo.file_upscaled)
            elif vo.file_720p:
                final_paths.append(vo.file_720p)
        if final_paths:
            task.output_uris = final_paths
        
        # Sync overall upscale status
        self._sync_status_fn(task)
        
        # === Complete the task (deferred from engine worker) ===
        from core.dispatcher import TaskStage
        any_success = any(p for p in upscale_paths if p)
        task.stage = TaskStage.COMPLETED
        
        if any_success:
            self._dispatcher.update_progress(
                task.id, 100, f"✅ Upscaled to {job.target_quality}"
            )
            self._total_completed += 1
            self._job_controller.record_success(job.account_email)
        else:
            self._dispatcher.update_progress(
                task.id, 100, f"⚠️ Upscale failed — 720p saved"
            )
            self._total_failed += 1
            self._job_controller.record_failure(job.account_email)
        
        # Call complete_task() — transitions task state to COMPLETED
        # NOTE: Continuation children were already activated early by engine
        # (via activate_children_early after 720p download), so we don't pass
        # continuation_frame args here — _parent_to_children already popped.
        self._dispatcher.complete_task(
            task.id,
            output_uris=task.output_uris or [],
        )
        
        # Notify UI of update
        if self._on_completed:
            try:
                self._on_completed(task)
            except Exception as e:
                log.error(f"[UpscaleQueue] UI callback error: {e}")
        
        emit_event(EventType.TASK_COMPLETED, {
            "task_id": task.id,
            "stage": "upscale_complete",
            "quality": job.target_quality,
            "success": any_success,
            "outputs": len(task.output_uris or []),
            "parallel_polls": len(pending_ops),
        }, source="upscale_queue")
    
    def get_stats(self) -> dict:
        """Return queue stats for StatusAggregator."""
        pending = sum(q.qsize() for q in self._queues.values())
        active_workers = sum(1 for t in self._workers.values() if not t.done())
        burst_stats = self._burst.get_stats()
        return {
            "pending_jobs": pending,
            "active_workers": active_workers,
            "total_enqueued": self._total_enqueued,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "burst_max_polls": burst_stats["max_polls"],
            "burst_active_polls": burst_stats["active_polls"],
            "burst_consecutive_success": burst_stats["consecutive_success"],
        }
