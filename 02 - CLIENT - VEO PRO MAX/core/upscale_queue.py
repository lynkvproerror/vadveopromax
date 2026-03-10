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
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable, TYPE_CHECKING

from core.event_manager import emit_event, EventType

if TYPE_CHECKING:
    from core.dispatcher import Dispatcher, Task
    from core.account_manager import AccountManager

log = logging.getLogger(__name__)

# Debug flag: set UPSCALE_DEBUG=1 for verbose reCAPTCHA timing logs
_UPSCALE_DEBUG = os.environ.get('UPSCALE_DEBUG', '').strip() in ('1', 'true', 'yes')


class AdaptiveBurstController:
    """Adaptive concurrency controller for upscale polling.
    
    Controls how many upscale poll operations can run globally at once.
    Scales up on sustained success, backs off immediately on errors.
    
    Scale ladder: 2 → 4 → 6 → 8 (step=2)
    Scale up: 8 consecutive poll successes → +2
    Back off: any 403/error → -2 (floor=2)
    """
    
    INITIAL = 2
    STEP = 2
    MAX = 8
    MIN = 2
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
    MIN = 1
    MAX = 6
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
    """A pending upscale job, created when worker finishes 720p/1K download."""
    task_id: str
    account_email: str
    media_ids: List[str]            # Base64 media IDs for upscale API
    output_uris: List[str]          # Original 720p fifeUrls (for logging)
    target_quality: str             # "1080p" or "4K"
    aspect_ratio: str
    job_type: str = "video"         # "video" or "image"
    local_paths: List[str] = field(default_factory=list)   # For image: 1K file paths
    upscale_quality: str = "4K"     # Image upscale resolution key
    original_account: str = ""      # DD6: Who generated the video (for failover tracing)
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0            # Job-level retry counter
    max_retries: int = 3            # Max job-level retries before permanent fail
    retry_indices: List[int] = field(default_factory=list)  # Which video indices to retry (empty = all)
    enqueue_after: float = 0.0      # Bug 2 fix: monotonic time to delay processing until (0 = no delay)


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
        record_circuit_403_fn: Optional[Callable] = None,  # engine.record_circuit_403
        burst_controller=None,           # engine._burst_controller (anti-detect delay)
        on_completed: Optional[Callable] = None,   # engine._on_task_completed
        profiles_controller=None,        # engine._profiles_controller
        extension_bridge=None,           # engine._extension_bridge
        wake_event: asyncio.Event = None, # T1: event-driven wake from engine
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
            record_circuit_403_fn: optional fn(email) → None — report 403 to engine CB
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
        self._record_circuit_403 = record_circuit_403_fn  # V6: report upscale 403 to engine
        self._burst_controller = burst_controller     # Anti-detect delay
        self._on_completed = on_completed
        self._profiles_controller = profiles_controller
        self._extension_bridge = extension_bridge
        self._wake_event = wake_event  # T1: event-driven wake from engine
        
        self._queues: Dict[str, asyncio.Queue] = {}      # email → Queue[UpscaleJob]
        self._upscale_processors: Dict[str, asyncio.Task] = {}       # email → background task
        self._running = False
        
        # Adaptive burst controller (global across all accounts)
        self._burst = AdaptiveBurstController()
        
        # Per-account adaptive job concurrency (AIMD)
        self._job_controller = AdaptiveJobController()
        
        # Per-account shared upscale API semaphore
        # Serializes ALL upscale API calls across all jobs per account
        # Prevents 429 cascade from concurrent upscale submissions
        self._upscale_api_sems: Dict[str, asyncio.Semaphore] = {}
        
        # Stats
        self._total_enqueued = 0
        self._total_completed = 0
        self._total_failed = 0
        
        # Bug 3: Dedup set — prevent duplicate upscale submissions
        self._enqueued_ids: set = set()  # "task_id:media_id" strings
        
        # Processing-level dedup — prevents concurrent _process_job calls
        # from submitting same media_id (happens during continuation when
        # multiple enqueue paths fire for same task)
        self._processing_ids: set = set()  # "task_id:media_id" strings
        
        # Force-retry cancellation: task_ids whose upscale jobs should be
        # discarded. Populated by cancel_task_jobs(), checked by _process_job.
        self._cancelled_task_ids: set = set()  # task_id strings
        
        # Counter for active image upscale jobs (bypass 720p_priority pause)
        self._active_image_jobs: int = 0
        
        # Fix #4: reCAPTCHA health check for account failover
        # Injected by engine after construction (same pattern as _burst_controller)
        # fn(email) -> bool: True if reCAPTCHA is healthy
        self._is_recaptcha_healthy_fn: Optional[Callable] = None
    
    def start(self):
        """Mark queue as running."""
        self._running = True
        log.info("[UpscaleQueue] Started — background upscale decoupled from workers")
    
    def stop(self):
        """Stop all background workers gracefully."""
        self._running = False
        # Cancel all worker tasks
        for email, task in self._upscale_processors.items():
            if not task.done():
                task.cancel()
                log.info(f"[UpscaleQueue] Cancelled worker for {email}")
        self._upscale_processors.clear()
        log.info(
            f"[UpscaleQueue] Stopped — "
            f"completed={self._total_completed}, failed={self._total_failed}"
        )
    
    def enqueue(self, job: UpscaleJob, *, force: bool = False):
        """Add an upscale job for background processing.
        
        Creates per-account worker if not already running.
        
        Args:
            force: If True, bypass dedup check (used for re-upscale).
        """
        email = job.account_email
        
        # Clear cancelled flag if task is being re-enqueued (post-force-retry re-generation)
        self._cancelled_task_ids.discard(job.task_id)
        
        # Bug 3: Dedup — skip if already enqueued
        dedup_keys = [f"{job.task_id}:{mid}" for mid in job.media_ids if mid]
        if force:
            # Re-upscale: clear old dedup keys so job can be re-enqueued
            self._enqueued_ids -= set(dedup_keys)
        if all(k in self._enqueued_ids for k in dedup_keys) and dedup_keys:
            _item_type = "images" if getattr(job, 'job_type', 'video') == 'image' else "videos"
            log.warning(
                f"[UpscaleQueue] Skipped duplicate enqueue for task {job.task_id} "
                f"({len(dedup_keys)} {_item_type} already queued)"
            )
            return
        self._enqueued_ids.update(dedup_keys)
        
        # Ensure queue is running (re-upscale may happen when engine is stopped)
        if not self._running:
            self._running = True
            log.info("[UpscaleQueue] Auto-started for re-upscale job")
        
        # Create per-account queue if needed
        if email not in self._queues:
            self._queues[email] = asyncio.Queue()
        
        self._queues[email].put_nowait(job)
        self._total_enqueued += 1
        
        # Start per-account worker if not already running
        if email not in self._upscale_processors or self._upscale_processors[email].done():
            self._upscale_processors[email] = asyncio.create_task(
                self._worker_loop(email)
            )
            log.info(f"[UpscaleQueue] Started worker for {email}")
        
        source = "re-upscale" if force else "upscale"
        _item_type = "images" if getattr(job, 'job_type', 'video') == 'image' else "videos"
        log.info(
            f"[UpscaleQueue] Enqueued {source} for task {job.task_id} "
            f"({len(job.media_ids)} {_item_type}, {job.target_quality}) → {email}"
        )
    
    def cancel_task_jobs(self, task_id: str) -> int:
        """Cancel all pending/in-flight upscale jobs for a task.
        
        Called by _force_reset_and_retry to prevent orphan upscale jobs
        from corrupting the task's cleared video_outputs.
        
        Actions:
          1. Mark task_id as cancelled → _process_job skips it immediately
          2. Drain matching jobs from per-account queues
          3. Clean dedup keys so re-generated results can enqueue normally
        
        Returns: number of queued jobs evicted.
        """
        self._cancelled_task_ids.add(task_id)
        
        # Clean dedup keys containing this task_id
        stale_keys = {k for k in self._enqueued_ids if k.startswith(f"{task_id}:")}
        self._enqueued_ids -= stale_keys
        stale_proc = {k for k in self._processing_ids if k.startswith(f"{task_id}:")}
        self._processing_ids -= stale_proc
        
        # Evict pending jobs from per-account queues
        evicted = 0
        for email, q in self._queues.items():
            keep = []
            try:
                while not q.empty():
                    job = q.get_nowait()
                    if job.task_id == task_id:
                        evicted += 1
                    else:
                        keep.append(job)
            except Exception:
                pass
            for job in keep:
                q.put_nowait(job)
        
        if evicted > 0 or stale_keys:
            log.info(
                f"[UpscaleQueue] cancel_task_jobs({task_id[:12]}): "
                f"evicted {evicted} queued jobs, cleared {len(stale_keys)} dedup keys"
            )
        return evicted
    
    def has_active_jobs(self, email: str) -> bool:
        """Check if any upscale jobs are actively processing for this account.
        
        Used by engine to defer browser restart during upscale polling (Bug #5).
        """
        if email not in self._upscale_processors:
            return False
        worker_task = self._upscale_processors[email]
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
        
        _was_paused = False  # Transition flag: log only on state change
        _ramp_up_remaining = 0  # Post-pause ramp-up: run N jobs serially before normal concurrency
        
        while self._running:
            try:
                # Clean up completed job tasks
                done_count = sum(1 for t in active_jobs if t.done())
                active_jobs = [t for t in active_jobs if not t.done()]
                
                # Decrement ramp-up counter based on completed jobs
                if _ramp_up_remaining > 0 and done_count > 0:
                    _ramp_up_remaining = max(0, _ramp_up_remaining - done_count)
                    if _ramp_up_remaining == 0:
                        log.info(f"[UpscaleQueue] {email}: ramp-up complete → normal concurrency")
                
                # Workload priority: pause if 720p_priority mode active
                # Skip pause when image upscale jobs are active or pending
                _has_image_work = self._active_image_jobs > 0
                if not _has_image_work:
                    try:
                        if not q.empty():
                            _peek = q._queue[0]
                            if getattr(_peek, 'job_type', 'video') == 'image':
                                _has_image_work = True
                    except Exception:
                        pass
                
                if self._should_wait() and not _has_image_work:
                    if not _was_paused:
                        log.info(f"[UpscaleQueue] {email}: pausing — 720p_priority mode")
                        _was_paused = True
                    # T1: Event-driven wake — instant instead of 5s poll
                    if self._wake_event:
                        try:
                            await asyncio.wait_for(
                                self._wake_event.wait(), timeout=5.0
                            )
                        except asyncio.TimeoutError:
                            pass
                        self._wake_event.clear()
                    else:
                        await asyncio.sleep(5)
                    continue
                if _was_paused:
                    log.info(f"[UpscaleQueue] {email}: resuming — all 720p downloads complete")
                    _was_paused = False
                    _ramp_up_remaining = 3  # First 3 jobs: serial (one at a time)
                    log.info(f"[UpscaleQueue] {email}: ramp-up mode — next 3 jobs run serially")
                    # V2 Fix: Warmup after extended idle during 720p_priority pause
                    _acct = self._get_account(email)
                    if _acct:
                        _eb = getattr(_acct, 'extension_bridge', None)
                        if _eb and _eb.is_connected(email):
                            try:
                                await _eb.simulate_activity(email, timeout=3.0)
                                log.info(f"[UpscaleQueue] {email}: post-pause warmup — waiting 8s for trust score")
                                await asyncio.sleep(8)
                            except Exception:
                                pass
                        try:
                            await self._wait_recaptcha_fn(_acct, max_wait=20.0)
                        except Exception:
                            pass
                
                # Adaptive job concurrency (AIMD): starts at 4, scales 2-8
                # record_success/record_failure called at end of _process_job
                max_jobs = self._job_controller.get_limit(email)
                
                # Post-pause ramp-up: force serial mode for first N jobs
                if _ramp_up_remaining > 0:
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
                # Bug 2 fix: if job has a delay, sleep BEFORE launching
                if job.enqueue_after > 0:
                    delay_remaining = job.enqueue_after - time.monotonic()
                    if delay_remaining > 0:
                        log.info(
                            f"[UpscaleQueue] {email}: delaying job {job.task_id[:8]} "
                            f"for {delay_remaining:.0f}s (scheduled retry)"
                        )
                        await asyncio.sleep(delay_remaining)
                
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
        
        # Wait for remaining active jobs (with timeout — don't block forever)
        if active_jobs:
            log.info(f"[UpscaleQueue] Worker {email}: waiting for {len(active_jobs)} active jobs")
            # BUG-25: Add timeout to prevent indefinite wait (jobs may be in 30-min poll loops)
            try:
                await asyncio.wait_for(
                    asyncio.gather(*active_jobs, return_exceptions=True),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                log.warning(
                    f"[UpscaleQueue] Worker {email}: {len(active_jobs)} jobs "
                    f"timed out after 60s — cancelling"
                )
                for t in active_jobs:
                    t.cancel()
                await asyncio.gather(*active_jobs, return_exceptions=True)
        
        log.info(f"[UpscaleQueue] Worker {email} exiting")
    
    async def _process_job(self, job: UpscaleJob):
        """Process a single upscale job.
        
        Dispatches to image or video processing based on job_type.
        Image: synchronous (submit → decode → save)
        Video: 3-phase pipeline (submit-seq → poll-parallel → batch-download)
        """
        # BUG-06: Early exit if queue was stopped (fire-and-forget tasks survive stop)
        if not self._running:
            log.info(f"[UpscaleQueue] Skipping job {job.task_id[:12]} — queue stopped")
            return
        
        # Route image upscale to dedicated handler
        if job.job_type == "image":
            self._active_image_jobs += 1
            try:
                await self._process_image_upscale(job)
            finally:
                self._active_image_jobs = max(0, self._active_image_jobs - 1)
            return
        
        # ── Staleness guard: skip if task was force-retried ──
        if job.task_id in self._cancelled_task_ids:
            log.info(
                f"[UpscaleQueue] Skipping stale job for force-retried task "
                f"{job.task_id[:12]} (cancelled)"
            )
            self._job_controller.record_failure(job.account_email)
            return
        
        task = self._dispatcher.get_task(job.task_id)
        if not task:
            log.warning(f"[UpscaleQueue] Task {job.task_id} not found, skipping")
            self._total_failed += 1
            self._job_controller.record_failure(job.account_email)
            return
        
        # Guard: if task was reset (video_outputs cleared by force retry)
        # but cancel_task_jobs wasn't called yet (race), detect via empty outputs
        if not task.video_outputs and not job.retry_indices:
            log.warning(
                f"[UpscaleQueue] Task {job.task_id[:12]} has empty video_outputs "
                f"(likely force-retried), skipping stale upscale job"
            )
            self._job_controller.record_failure(job.account_email)
            return
        
        # Get the account
        account = self._get_account(job.account_email)
        if not account:
            log.warning(f"[UpscaleQueue] Account {job.account_email} not found, skipping")
            self._total_failed += 1
            self._job_controller.record_failure(job.account_email)
            return
        
        # DD6: Failover — if primary account unhealthy (cooldown OR reCAPTCHA dead), try others
        original_email = job.original_account or job.account_email
        _needs_failover = self._is_on_cooldown(job.account_email)
        # ★ Fix #4: Also failover when reCAPTCHA is dead (extension connected but widget stuck)
        if not _needs_failover and self._is_recaptcha_healthy_fn:
            if not self._is_recaptcha_healthy_fn(job.account_email):
                _needs_failover = True
                log.warning(
                    f"[UpscaleQueue] DD6: {job.account_email} reCAPTCHA unhealthy "
                    f"— attempting failover to healthy account"
                )
        if _needs_failover:
            failover_found = False
            for alt in self._get_all_accounts():
                if (alt.email != job.account_email 
                    and not self._is_on_cooldown(alt.email)
                    and (not self._is_recaptcha_healthy_fn or self._is_recaptcha_healthy_fn(alt.email))):
                    log.warning(
                        f"[UpscaleQueue] DD6 Failover: {job.account_email} → {alt.email} "
                        f"(original: {original_email}, reason: cooldown)"
                    )
                    account = alt
                    job.account_email = alt.email  # Rebind for this attempt
                    failover_found = True
                    break
            if not failover_found:
                # All accounts on cooldown — wait on original
                log.info(
                    f"[UpscaleQueue] {job.account_email}: all accounts on cooldown, "
                    f"waiting before upscale (task {job.task_id})"
                )
                await self._wait_cooldown(job.account_email)
        
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
            self._job_controller.record_failure(job.account_email)
            return
        
        # Store media IDs on task for re-upscale support
        task.upscale_media_ids = list(job.media_ids)
        
        # Bug 2 fix: Wait for extension bridge to be connected before submit
        # At cold start, extension reconnects after browser launch — upscale from
        # journal restore may fire before bridge is ready → 403 reCAPTCHA fail.
        ext_bridge = getattr(account, 'extension_bridge', None)
        if ext_bridge and not ext_bridge.is_connected(account.email):
            log.info(
                f"[UpscaleQueue] {account.email}: extension bridge not connected, "
                f"waiting up to 30s for readiness..."
            )
            for _ in range(15):  # 15 × 2s = 30s max wait
                await asyncio.sleep(2.0)
                if ext_bridge.is_connected(account.email):
                    log.info(f"[UpscaleQueue] {account.email}: extension bridge now connected")
                    break
            else:
                log.warning(f"[UpscaleQueue] {account.email}: extension bridge timeout — proceeding anyway")
        
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
        
        # ★ Proactive grecaptcha warmup gate (prevents 330-char garbage tokens)
        # After app restart, the browser's grecaptcha widget takes time to initialize.
        # Without this gate, the first 2-3 submit attempts waste ~2min on short tokens.
        try:
            await self._wait_recaptcha_fn(account, max_wait=30.0)
        except Exception as e:
            log.debug(f"[UpscaleQueue] grecaptcha warmup check failed: {e}")
        
        # ★ Cold-start pre-warm: simulate user activity to build reCAPTCHA trust score.
        # On fresh browser tabs, reCAPTCHA v3 Enterprise gives low trust scores
        # (no mouse/scroll/click history) → 403 "reCAPTCHA evaluation failed".
        # Scale warmup based on queue age — longer idle → more warmup needed.
        queue_age_s = (datetime.now() - job.created_at).total_seconds()
        if queue_age_s > 600:  # 10+ min stale
            warmup_wait = 20
            warmup_rounds = 2
        elif queue_age_s > 120:  # 2-10 min
            warmup_wait = 15
            warmup_rounds = 1
        else:  # Fresh (< 2 min)
            warmup_wait = 10
            warmup_rounds = 1
        
        ext_bridge = getattr(account, 'extension_bridge', None)
        if ext_bridge and ext_bridge.is_connected(account.email):
            try:
                for _round in range(warmup_rounds):
                    await ext_bridge.simulate_activity(account.email, timeout=3.0)
                    if warmup_rounds > 1 and _round < warmup_rounds - 1:
                        await asyncio.sleep(5)  # Gap between rounds
                log.info(
                    f"[UpscaleQueue] {account.email}: pre-warm activity simulated "
                    f"(age={queue_age_s:.0f}s, rounds={warmup_rounds}), "
                    f"waiting {warmup_wait}s for reCAPTCHA trust score..."
                )
                await asyncio.sleep(warmup_wait)
                # BUG-27: Check if stopped during warmup sleep
                if not self._running:
                    log.info(f"[UpscaleQueue] {account.email}: stopped during warmup")
                    return
            except Exception as e:
                log.debug(f"[UpscaleQueue] pre-warm activity failed: {e}")
        
        for local_idx, media_id in enumerate(job.media_ids):
            # BUG-22: Exit submit loop on stop
            if not self._running:
                log.info(f"[UpscaleQueue] Stopped — aborting submit at video {local_idx+1}/{total}")
                break
            
            # Map local index back to original video_outputs position
            orig_idx = job.retry_indices[local_idx] if job.retry_indices else local_idx
            video_label = f"{orig_idx + 1}/{len(task.video_outputs)}"
            if not media_id:
                log.warning(f"Upscale {video_label}: no mediaId, skipping")
                if orig_idx < len(task.video_outputs):
                    task.video_outputs[orig_idx].upscale_status = "skipped"
                continue
            
            # Processing-level dedup: skip if another concurrent job is
            # already submitting this exact media_id (continuation double-enqueue)
            proc_key = f"{job.task_id}:{media_id}"
            if proc_key in self._processing_ids:
                log.warning(
                    f"Upscale {video_label}: already being processed by another job, skipping"
                )
                continue
            self._processing_ids.add(proc_key)
            
            try:
                # Submit with retry
                resp = None
                for attempt in range(max_submit_retries):
                    # BUG-22: Stop check in inner retry loop
                    if not self._running:
                        break
                    
                    # BUG 1 FIX: Check cooldown before each retry attempt
                    if attempt > 0 and self._is_on_cooldown(job.account_email):
                        await self._wait_cooldown(job.account_email)
                    
                    # V1+V5 Fix: Inter-video simulate_activity to maintain trust score
                    # Skip first video (already pre-warmed above) and first attempt retries
                    if local_idx > 0 and attempt == 0:
                        _eb = getattr(account, 'extension_bridge', None)
                        if _eb and _eb.is_connected(account.email):
                            _t0 = time.monotonic() if _UPSCALE_DEBUG else 0
                            try:
                                await _eb.simulate_activity(account.email, timeout=2.0)
                                await asyncio.sleep(3)  # Let trust score build
                                if _UPSCALE_DEBUG:
                                    log.info(
                                        f"[UpscaleDebug] {account.email}: inter-video warmup "
                                        f"for video {video_label} took {time.monotonic()-_t0:.1f}s"
                                    )
                            except Exception:
                                pass
                    
                    # Fix G6: Acquire per-account rate lock + anti-detect delay
                    # Same mechanism as engine — serialize API calls with adaptive delay
                    rate_lock = self._rate_locks.setdefault(
                        job.account_email,
                        asyncio.Lock(),
                    )
                    async with rate_lock:
                        # Re-check cooldown inside lock (another worker may have set it)
                        if self._is_on_cooldown(job.account_email):
                            log.info(f"Upscale {video_label}: cooldown detected inside rate lock")
                            await self._wait_cooldown(job.account_email)
                        
                        # Anti-detect delay (adaptive burst controller)
                        if self._burst_controller:
                            bc_delay = self._burst_controller.get_delay(job.account_email)
                            log.info(
                                f"Upscale {video_label}: anti-detect delay "
                                f"({bc_delay:.1f}s) → attempt {attempt+1}/{max_submit_retries}"
                            )
                            await self._burst_controller.wait(job.account_email)
                    
                    # Check if extension bridge is available — determines reCAPTCHA strategy
                    ext_bridge = getattr(account, 'extension_bridge', None)
                    use_ext = (ext_bridge and ext_bridge.is_connected(account.email))
                    
                    # ★ FIX: Only refresh reCAPTCHA for FALLBACK (aiohttp) path.
                    # Extension path generates its own fresh token via
                    # grecaptcha.enterprise.execute() in page context.
                    # Double-execution (Python + Extension) triggers reCAPTCHA
                    # rate-limiting → 403 "evaluation failed".
                    # Generation flow (engine.py) does NOT pre-refresh — matches this fix.
                    recaptcha_token = ""
                    if not use_ext:
                        _t_rc = time.monotonic() if _UPSCALE_DEBUG else 0
                        async with account.recaptcha_lock:
                            recaptcha_token = await account.refresh_recaptcha() or ""
                        if not recaptcha_token:
                            recaptcha_token = account.get_recaptcha_token() or ""
                        if _UPSCALE_DEBUG:
                            log.info(
                                f"[UpscaleDebug] {account.email}: reCAPTCHA refresh "
                                f"for {video_label} took {time.monotonic()-_t_rc:.1f}s, "
                                f"token_len={len(recaptcha_token) if recaptcha_token else 0}"
                            )
                        
                        # Validate token quality — short tokens from
                        # uninitialized grecaptcha widget after browser restart
                        # HAR verified: valid tokens are 1742-2169 chars
                        if recaptcha_token and len(recaptcha_token) < 1000:
                            log.warning(
                                f"Upscale {video_label}: garbage reCAPTCHA token "
                                f"({len(recaptcha_token)} chars < 1000), skipping submit"
                            )
                            account.invalidate_recaptcha()
                            if attempt < max_submit_retries - 1:
                                delay = min(5 * (attempt + 1), 15)
                                await asyncio.sleep(delay)
                            continue
                    elif _UPSCALE_DEBUG:
                        log.info(
                            f"[UpscaleDebug] {account.email}: extension connected, "
                            f"skipping Python reCAPTCHA (extension generates its own)"
                        )
                    
                    # Gap #5: Stable seed per (task, media, attempt) to prevent duplicate jobs
                    idem_hash = hashlib.sha256(
                        f"{task.id}:{media_id}:{attempt}".encode()
                    ).hexdigest()
                    stable_seed = int(idem_hash[:8], 16) % (2**31)
                    
                    # ★ PRIMARY PATH: Extension-based upscale
                    # (use_ext already computed above for reCAPTCHA strategy)
                    if use_ext:
                        # Reuse original sceneId — keeps upscale in same VEO project
                        orig_scene_id = (
                            task.scene_ids[orig_idx]
                            if orig_idx < len(task.scene_ids)
                            else None
                        )
                        upscale_body = self._api_client.build_upscale_body(
                            video_media_id=media_id,
                            target_resolution=resolution,
                            aspect_ratio=task.aspect_ratio,
                            seed=stable_seed,
                            scene_id=orig_scene_id,
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
                    
                    error_lower = (resp.error or "").lower()
                    
                    # ★ Extension disconnect recovery: wait for reconnection
                    # before retrying (prevents fallback to aiohttp → guaranteed 403)
                    if "disconnected" in error_lower or "extension timeout" in error_lower:
                        ext_bridge = getattr(account, 'extension_bridge', None)
                        if ext_bridge:
                            log.info(
                                f"Upscale {video_label}: extension disconnected — "
                                f"waiting for reconnection (30s)..."
                            )
                            reconnected = await ext_bridge.wait_for_extension(
                                account.email, timeout=30.0
                            )
                            if reconnected:
                                log.info(f"Upscale {video_label}: extension reconnected ✅")
                                # Wait for grecaptcha to re-initialize after reconnect
                                try:
                                    await self._wait_recaptcha_fn(account, max_wait=20.0)
                                except Exception:
                                    pass
                            else:
                                log.warning(f"Upscale {video_label}: extension did not reconnect")
                        continue
                    
                    # Fix 1+2: Browser recovery on reCAPTCHA/403 failures
                    # Widened detection: HTTP 403 may not mention 'recaptcha'
                    is_403 = "403" in error_lower
                    if "recaptcha" in error_lower or is_403:
                        # V6 Fix: Report upscale 403 to engine circuit breaker
                        if is_403 and self._record_circuit_403:
                            try:
                                self._record_circuit_403(job.account_email)
                                if _UPSCALE_DEBUG:
                                    log.info(f"[UpscaleDebug] {job.account_email}: reported 403 to circuit breaker")
                            except Exception:
                                pass
                        
                        # Set account cooldown on 403
                        if is_403:
                            self._set_cooldown(
                                job.account_email, f"upscale submit 403"
                            )
                            # Wait for cooldown before next attempt
                            await self._wait_cooldown(job.account_email)
                        
                        # Recovery: full if no pending, lightweight if pending
                        if not pending_ops:
                            # Full recovery — no submitted videos to protect
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
                            # V3 Fix: Lightweight recovery — videos already submitted,
                            # can't restart browser but CAN refresh trust score
                            log.warning(
                                f"Upscale {video_label}: 403 with {len(pending_ops)} pending — "
                                f"lightweight recovery (simulate + wait)"
                            )
                            _eb = getattr(account, 'extension_bridge', None)
                            if _eb and _eb.is_connected(account.email):
                                try:
                                    await _eb.simulate_activity(account.email, timeout=3.0)
                                    await asyncio.sleep(5)
                                    await self._wait_recaptcha_fn(account, max_wait=15.0)
                                    if _UPSCALE_DEBUG:
                                        log.info(
                                            f"[UpscaleDebug] {account.email}: lightweight recovery done "
                                            f"for {video_label}"
                                        )
                                except Exception:
                                    pass
                            # Continue retry loop (don't break — give this video another chance)
                    
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
                    task.video_outputs[orig_idx].upscale_poll_count = 0  # Reset for fresh poll
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
        
        # Clean up processing-level dedup keys — submit phase done,
        # these keys only block duplicate concurrent submits
        for mid in job.media_ids:
            self._processing_ids.discard(f"{job.task_id}:{mid}")
        
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
            # BUG-26: Don't re-enqueue if stopped
            if not self._running:
                log.info(f"[UpscaleQueue] Stopped — skipping retry for {job.task_id}")
                return
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
            self._job_controller.record_failure(job.account_email)
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
        # BUG-26: Don't re-enqueue partial retry if stopped
        if failed_indices and job.retry_count < job.max_retries and self._running:
            retry_media_ids = [job.media_ids[i] for i in failed_indices]
            retry_job = UpscaleJob(
                task_id=job.task_id,
                account_email=job.account_email,
                original_account=job.original_account or job.account_email,  # DD6: preserve original
                media_ids=retry_media_ids,
                output_uris=job.output_uris,
                target_quality=job.target_quality,
                aspect_ratio=job.aspect_ratio,
                retry_count=job.retry_count + 1,
                max_retries=job.max_retries,
                retry_indices=failed_indices,  # Map back to original positions
            )
            # Bug 2 fix: Use enqueue_after instead of fire-and-forget asyncio.create_task.
            # _delayed_retry() would create a ghost task outside active_jobs tracking.
            # Instead, set a delay on the retry job and enqueue directly — the worker loop
            # handles the delay inline, keeping the job within active_jobs tracking.
            retry_delay = 30 * (2 ** job.retry_count)
            retry_job.enqueue_after = time.monotonic() + retry_delay
            log.info(
                f"[UpscaleQueue] Partial retry: {len(failed_indices)} failed videos "
                f"(indices {failed_indices}) will retry in {retry_delay}s. "
                f"{len(pending_ops)} videos proceeding to poll now."
            )
            # Reset failed statuses for upcoming retry
            for i in failed_indices:
                task.video_outputs[i].upscale_status = "pending"
                task.video_outputs[i].upscale_error = ""
            self.enqueue(retry_job)
        
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
            
            # BUG-23: Exit immediately if stopped
            if not self._running:
                return (idx, None)
            
            # Acquire burst-controlled poll slot
            await self._burst.acquire()
            try:
                # Track poll attempts for progressive UI progress
                if idx < len(task.video_outputs):
                    task.video_outputs[idx].upscale_poll_count += 1
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
                # BUG-23: Skip re-submit if stopped
                if is_free_upscale and self._running:
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
            # BUG-24: Skip download if stopped
            if not self._running:
                log.info(f"[UpscaleQueue] Stopped — skipping upscale download")
            else:
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
        # BUG-31: Skip completion if stopped (task stays in current state for requeue)
        if not self._running:
            log.info(
                f"[UpscaleQueue] Stopped — skipping completion for task {job.task_id} "
                f"(task stays in current state for requeue)"
            )
            self._sync_status_fn(task)
            return
        
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
    
    async def _process_image_upscale(self, job: UpscaleJob):
        """Process image upscale job — synchronous API (no poll phase).
        
        For each image:
        1. Submit upsampleImage API (synchronous — returns encodedImage inline)
        2. Decode base64 → save to upscale_quality subfolder
        
        Uses same cooldown/reCAPTCHA/bridge infrastructure as video upscale.
        """
        import base64
        from pathlib import Path
        
        task = self._dispatcher.get_task(job.task_id)
        if not task:
            log.warning(f"[UpscaleQ-Image] Task {job.task_id} not found")
            self._total_failed += 1
            return
        
        account = self._get_account(job.account_email)
        if not account:
            log.warning(f"[UpscaleQ-Image] Account {job.account_email} not found")
            self._total_failed += 1
            return
        
        # ★ Fix #4: Account failover for image upscale when reCAPTCHA is dead
        if self._is_recaptcha_healthy_fn and not self._is_recaptcha_healthy_fn(job.account_email):
            for alt in self._get_all_accounts():
                if (alt.email != job.account_email
                    and not self._is_on_cooldown(alt.email)
                    and (self._is_recaptcha_healthy_fn(alt.email))):
                    log.warning(
                        f"[UpscaleQ-Image] Failover: {job.account_email} → {alt.email} "
                        f"(reCAPTCHA unhealthy on primary)"
                    )
                    account = alt
                    job.account_email = alt.email
                    break
        
        # Auto-inject extension bridge
        if not account.extension_bridge:
            bridge = self._extension_bridge
            if not bridge:
                for acc in self._get_all_accounts():
                    if acc.extension_bridge:
                        bridge = acc.extension_bridge
                        break
            if bridge:
                account.extension_bridge = bridge
        
        resolution_map = {
            '4K': 'UPSAMPLE_IMAGE_RESOLUTION_4K',
            '2K': 'UPSAMPLE_IMAGE_RESOLUTION_2K',
        }
        target_resolution = resolution_map.get(
            job.upscale_quality.upper(),
            'UPSAMPLE_IMAGE_RESOLUTION_4K'
        )
        
        total = len(job.media_ids)
        success_count = 0
        max_retries = 3
        # Shared per-account semaphore: 1 concurrent upscale API call
        # Prevents 429 cascade (was: per-job Semaphore(4) → 12+ concurrent)
        if job.account_email not in self._upscale_api_sems:
            self._upscale_api_sems[job.account_email] = asyncio.Semaphore(1)
        upscale_sem = self._upscale_api_sems[job.account_email]
        
        log.info(
            f"[UpscaleQ-Image] Task {job.task_id}: "
            f"{total} images → {job.upscale_quality}"
        )
        self._dispatcher.update_progress(
            job.task_id, 92,
            f"⬆️ Upscaling {total} image(s) to {job.upscale_quality}"
        )
        
        async def _upscale_single(idx: int) -> bool:
            """Upscale a single image with retry, protected by semaphore."""
            mid = job.media_ids[idx] if idx < len(job.media_ids) else ""
            local_1k = job.local_paths[idx] if idx < len(job.local_paths) else ""
            vo = task.video_outputs[idx] if idx < len(task.video_outputs) else None
            
            if not mid:
                log.warning(f"[UpscaleQ-Image] {idx+1}/{total}: no mediaId, skipping")
                return False
            
            success = False
            for attempt in range(max_retries):
                if not self._running:
                    break
                
                # Cooldown gate
                if self._is_on_cooldown(job.account_email):
                    log.info(
                        f"[UpscaleQ-Image] {idx+1}/{total}: "
                        f"cooldown, waiting..."
                    )
                    await self._wait_cooldown(job.account_email)
                
                # reCAPTCHA readiness gate
                ext_bridge = getattr(account, 'extension_bridge', None)
                if not ext_bridge or not ext_bridge.is_connected(account.email):
                    log.warning(
                        f"[UpscaleQ-Image] {idx+1}/{total}: "
                        f"extension not connected, waiting 30s..."
                    )
                    for _w in range(15):
                        await asyncio.sleep(2.0)
                        ext_bridge = getattr(account, 'extension_bridge', None)
                        if ext_bridge and ext_bridge.is_connected(account.email):
                            break
                    else:
                        log.warning(
                            f"[UpscaleQ-Image] {idx+1}/{total}: "
                            f"bridge timeout — skipping"
                        )
                        break
                
                try:
                    log.info(
                        f"[UpscaleQ-Image] {idx+1}/{total}: "
                        f"upscaling mediaId={mid[:30]}... → {job.upscale_quality}"
                        f"{f' (attempt {attempt+1})' if attempt > 0 else ''}"
                    )
                    
                    if vo:
                        vo.upscale_status = "submitting"
                    
                    upscale_body = self._api_client.build_upscale_image_body(
                        media_id=mid,
                        project_id=account.project_id or "",
                        target_resolution=target_resolution,
                        paygate_tier=account.paygate_tier or "PAYGATE_TIER_TWO",
                    )
                    
                    ext_result = await asyncio.wait_for(
                        ext_bridge.submit_prompt(
                            email=account.email,
                            endpoint="UPSCALE_IMAGE",
                            body=upscale_body,
                            needs_recaptcha=True,
                            timeout=120,
                        ),
                        timeout=125,
                    )
                    
                    if ext_result and ext_result.get('success'):
                        data = ext_result.get('data', {})
                        encoded_image = data.get('encodedImage', '')
                        
                        if encoded_image:
                            # Save upscaled image
                            output_folder = (
                                getattr(task, 'output_folder', '') 
                                or '.'
                            )
                            project_name = (
                                getattr(task, 'project_name', '') or "Untitled"
                            )
                            upscale_dir = (
                                Path(output_folder) / project_name / job.upscale_quality
                            )
                            upscale_dir.mkdir(parents=True, exist_ok=True)
                            
                            # Replace _1K suffix with actual quality tag
                            raw_name = Path(local_1k).name if local_1k else f"image_{idx+1}.png"
                            filename = raw_name.replace('_1K', f'_{job.upscale_quality}')
                            upscale_path = upscale_dir / filename
                            img_bytes = base64.b64decode(encoded_image)
                            upscale_path.write_bytes(img_bytes)
                            
                            log.info(
                                f"[UpscaleQ-Image] {idx+1}/{total}: "
                                f"✅ {job.upscale_quality} saved "
                                f"({len(img_bytes)//1024}KB): "
                                f"{upscale_path.name}"
                            )
                            if vo:
                                vo.file_upscaled = str(upscale_path)
                                vo.quality = job.upscale_quality
                                vo.upscale_status = "success"
                            success = True
                            return True  # Success
                        else:
                            log.warning(
                                f"[UpscaleQ-Image] {idx+1}/{total}: "
                                f"no encodedImage in response"
                            )
                    else:
                        error = (ext_result or {}).get('error', 'unknown')
                        status_code = (ext_result or {}).get('status', 0)
                        log.warning(
                            f"[UpscaleQ-Image] {idx+1}/{total}: "
                            f"failed (attempt {attempt+1}/{max_retries}): {error}"
                        )
                        
                        if status_code == 403 or "403" in str(error):
                            # Do NOT call _set_cooldown() — same poisoning
                            # issue as 429. Upscale errors must not block T2I.
                            await asyncio.sleep(30)
                        elif status_code == 429 or "429" in str(error) or "exhausted" in str(error).lower():
                            # Exponential backoff for quota exhaustion
                            # NOTE: Do NOT call _set_cooldown() here!
                            # That sets ACCOUNT-LEVEL cooldown which blocks
                            # ALL T2I submissions (not just upscale).
                            # Use only local sleep for upscale-specific backoff.
                            _backoff = min(30 * (2 ** attempt), 120)
                            import random as _rng
                            _jitter = _rng.uniform(0, _backoff * 0.3)
                            log.info(
                                f"[UpscaleQ-Image] {idx+1}/{total}: "
                                f"429 backoff {_backoff+_jitter:.0f}s "
                                f"(attempt {attempt+1}/{max_retries})"
                            )
                            await asyncio.sleep(_backoff + _jitter)
                        else:
                            await asyncio.sleep(10)
                        continue
                
                except asyncio.TimeoutError:
                    log.warning(
                        f"[UpscaleQ-Image] {idx+1}/{total}: "
                        f"timeout (attempt {attempt+1}/{max_retries})"
                    )
                    await asyncio.sleep(5)
                    continue
                except Exception as e:
                    log.warning(
                        f"[UpscaleQ-Image] {idx+1}/{total}: "
                        f"error: {e} (attempt {attempt+1}/{max_retries})"
                    )
                    await asyncio.sleep(10)
                    continue
            
            if not success and vo:
                vo.upscale_status = "failed"
                vo.quality = "1K"
            return False
        
        # Launch all upscales concurrently (semaphore limits to 4)
        # Anti-detect: stagger launch with random delays
        import random
        tasks_to_run = []
        for idx in range(total):
            async def _staggered_upscale(i=idx):
                if i > 0:
                    delay = random.uniform(2.0, 5.0)
                    await asyncio.sleep(delay)
                async with upscale_sem:
                    return await _upscale_single(i)
            tasks_to_run.append(_staggered_upscale())
        
        results = await asyncio.gather(*tasks_to_run, return_exceptions=True)
        success_count = sum(1 for r in results if r is True)
        
        # Summary + update progress + complete task
        if success_count > 0:
            log.info(
                f"[UpscaleQ-Image] Task {job.task_id}: "
                f"✅ {success_count}/{total} → {job.upscale_quality}"
            )
            self._dispatcher.update_progress(
                job.task_id, 100,
                f"✅ {job.upscale_quality} complete ({success_count}/{total})"
            )
            self._dispatcher.complete_task(
                job.task_id,
                output_uris=task.output_uris if task else [],
            )
            self._total_completed += 1
        else:
            log.warning(
                f"[UpscaleQ-Image] Task {job.task_id}: "
                f"⚠️ 0/{total} upscaled"
            )
            self._dispatcher.update_progress(
                job.task_id, 100,
                f"⚠️ Upscale failed — 1K saved"
            )
            self._dispatcher.complete_task(
                job.task_id,
                output_uris=task.output_uris if task else [],
            )
            self._total_failed += 1

    def get_stats(self) -> dict:
        """Return queue stats for StatusAggregator."""
        pending = sum(q.qsize() for q in self._queues.values())
        active_workers = sum(1 for t in self._upscale_processors.values() if not t.done())
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
