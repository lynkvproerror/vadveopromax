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
_UNSUPPORTED_REUPSCALE_ERROR = "Re-upscale requires debug browser (TRPC unavailable)"


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
    reupscale_signature: str = ""   # Active dedupe for force=True re-upscale
    outcome_applied: bool = False   # Ensure AIMD is updated at most once per job


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
        pre_submit_gate_fn: Optional[Callable] = None,  # engine._pre_submit_gate
        zoom_crop_fn: Optional[Callable] = None,  # engine._remove_watermark_zoom_crop
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
            should_wait_fn: fn() → bool (deprecated — always returns False)
            wait_for_circuit_fn: async fn(email) → None — wait for CB CLOSED
            record_circuit_403_fn: optional fn(email) → None — report 403 to engine CB
            on_completed: optional callback fn(task) for UI refresh
            profiles_controller: optional profiles controller for reset
            extension_bridge: optional extension bridge for reCAPTCHA
            zoom_crop_fn: optional async fn(filepath, aspect_ratio) — zoom+crop watermark removal
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
        self._pre_submit_gate_fn = pre_submit_gate_fn  # Centralized xcd + reCAPTCHA gate
        self._zoom_crop_fn = zoom_crop_fn  # Non-watermark zoom+crop for TRPC downloads
        
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
        
        # TRPC download stats
        self._trpc_attempts = 0
        self._trpc_success = 0
        self._trpc_fail = 0
        self._fife_attempts = 0
        self._fife_success = 0
        self._fife_fail = 0
        self._xcd_bypass_count = 0  # PreSubmitGate xcd-bypass via trial token
        
        # Bug 3: Dedup set — prevent duplicate upscale submissions
        self._enqueued_ids: set = set()  # "task_id:media_id" strings
        self._active_reupscale_signatures: set = set()  # Force re-upscale dedupe while queued/running
        
        # Processing-level dedup — prevents concurrent _process_job calls
        # from submitting same media_id (happens during continuation when
        # multiple enqueue paths fire for same task)
        self._processing_ids: set = set()  # "task_id:media_id" strings
        
        # Force-retry cancellation: task_ids whose upscale jobs should be
        # discarded. Populated by cancel_task_jobs(), checked by _process_job.
        self._cancelled_task_ids: set = set()  # task_id strings
        
        # Counter for active image upscale jobs
        self._active_image_jobs: int = 0
        
        # Fix #4: reCAPTCHA health check for account failover
        # Injected by engine after construction (same pattern as _burst_controller)
        # fn(email) -> bool: True if reCAPTCHA is healthy
        self._is_recaptcha_healthy_fn: Optional[Callable] = None
        
        # Dead-tab pause: accounts whose tabs are dead → stop picking up new jobs
        self._paused_accounts: set = set()  # email strings
        
        # ★ FIX #429: Per-account consecutive 429 counter for escalating backoff.
        # Cooldown is only triggered after _429_COOLDOWN_THRESHOLD consecutive 429s
        # (not on first occurrence, unlike 403 which is immediate).
        self._consecutive_429s: Dict[str, int] = {}  # email → count
        self._429_COOLDOWN_THRESHOLD = 3  # escalate to _set_cooldown after 3 consecutive 429s
    
    def start(self):
        """Mark queue as running."""
        self._running = True
        log.info("[UpscaleQueue] Started — background upscale decoupled from workers")
    
    def get_stats(self) -> dict:
        """Return stats dict for Engine Dashboard."""
        return {
            "pending_jobs": sum(q.qsize() for q in self._queues.values()),
            "total_enqueued": self._total_enqueued,
            "total_completed": self._total_completed,
            "total_failed": self._total_failed,
            "trpc": {
                "attempts": self._trpc_attempts,
                "success": self._trpc_success,
                "fail": self._trpc_fail,
            },
            "fife": {
                "attempts": self._fife_attempts,
                "success": self._fife_success,
                "fail": self._fife_fail,
            },
            "xcd_bypass": self._xcd_bypass_count,
        }
    
    def stop(self):
        """Stop all background workers gracefully."""
        self._running = False
        # Cancel all worker tasks
        for email, task in self._upscale_processors.items():
            if not task.done():
                task.cancel()
                log.info(f"[UpscaleQueue] Cancelled worker for {email}")
        self._upscale_processors.clear()
        self._paused_accounts.clear()
        self._active_reupscale_signatures.clear()
        log.info(
            f"[UpscaleQueue] Stopped — "
            f"completed={self._total_completed}, failed={self._total_failed}"
        )

    def _build_reupscale_signature(self, job: UpscaleJob) -> str:
        """Build a stable signature for duplicate force=True re-upscale jobs."""
        media_ids = [mid for mid in job.media_ids if mid]
        if not media_ids:
            return ""
        return f"{job.task_id}:{'|'.join(media_ids)}"

    def _apply_job_outcome(self, job: UpscaleJob, reason: str, detail: str = ""):
        """Apply AIMD outcome once per job and emit a diagnostic log."""
        if getattr(job, 'outcome_applied', False):
            return
        job.outcome_applied = True

        before = self._job_controller.get_limit(job.account_email)
        if reason == "success":
            self._job_controller.record_success(job.account_email)
        elif reason == "failure":
            self._job_controller.record_failure(job.account_email)
        after = self._job_controller.get_limit(job.account_email)

        suffix = f", detail={detail}" if detail else ""
        log.info(
            f"[UpscaleQueue] Job outcome: task={job.task_id[:12]} "
            f"account={job.account_email} reason={reason} "
            f"limit={before}->{after}{suffix}"
        )

    @staticmethod
    def _is_unsupported_reupscale_output(video_output) -> bool:
        return (
            str(getattr(video_output, 'upscale_status', '') or '').lower() == "skipped"
            and str(getattr(video_output, 'upscale_error', '') or '') == _UNSUPPORTED_REUPSCALE_ERROR
        )

    def _get_job_output_indices(self, task, job: UpscaleJob) -> List[int]:
        """Map job-local media_ids back to authoritative task.video_outputs indices."""
        outputs = getattr(task, 'video_outputs', None) or []
        indices: List[int] = []
        for local_idx, _ in enumerate(job.media_ids or [None]):
            orig_idx = job.retry_indices[local_idx] if job.retry_indices else local_idx
            if 0 <= orig_idx < len(outputs):
                indices.append(orig_idx)
        return indices

    def _classify_job_outcome(self, task, job: UpscaleJob) -> tuple[str, str]:
        """Classify the finished job for AIMD purposes."""
        indices = self._get_job_output_indices(task, job)
        if not indices:
            return ("neutral", "no-owned-outputs")

        success = 0
        unsupported = 0
        pending = 0
        failed = 0
        for idx in indices:
            video_output = task.video_outputs[idx]
            status = str(getattr(video_output, 'upscale_status', '') or '').lower()
            if status in ("success", "completed"):
                success += 1
            elif self._is_unsupported_reupscale_output(video_output):
                unsupported += 1
            elif status in ("pending", "polling", "submitting", "retrying", ""):
                pending += 1
            elif status in ("failed", "skipped"):
                failed += 1
            else:
                pending += 1

        detail = (
            f"success={success}, unsupported={unsupported}, "
            f"pending={pending}, failed={failed}"
        )
        if success > 0:
            return ("success", detail)
        if unsupported == len(indices):
            return ("neutral", f"unsupported-re-upscale, {detail}")
        if pending > 0 and failed == 0:
            return ("neutral", f"pending-retry, {detail}")
        if failed > 0:
            return ("failure", detail)
        return ("neutral", detail)

    def _task_all_outputs_unsupported(self, task) -> bool:
        outputs = getattr(task, 'video_outputs', None) or []
        return bool(outputs) and all(
            self._is_unsupported_reupscale_output(video_output)
            for video_output in outputs
        )
    
    def pause_account(self, email: str):
        """Pause upscale processing for a dead-tab account.
        
        Worker loop exits (email in _paused_accounts breaks while condition).
        In-flight jobs for this account will also exit early (_process_job guard).
        """
        self._paused_accounts.add(email)
        # Cancel worker task if running
        worker = self._upscale_processors.get(email)
        if worker and not worker.done():
            worker.cancel()
            log.info(f"[UpscaleQueue] ⏸️ Worker cancelled for {email} (tab dead)")
        log.warning(
            f"[UpscaleQueue] ⏸️ Account {email} paused — "
            f"pending={self._queues.get(email, asyncio.Queue()).qsize()} jobs frozen"
        )
    
    def unpause_account(self, email: str):
        """Unpause account after tab reconnects.
        
        Pending jobs remain in the queue — worker will restart on next enqueue
        or can be triggered manually.
        """
        if email not in self._paused_accounts:
            return
        self._paused_accounts.discard(email)
        log.info(f"[UpscaleQueue] ▶️ Account {email} unpaused")
        
        # If there are pending jobs, restart the worker
        q = self._queues.get(email)
        if q and not q.empty() and self._running:
            existing = self._upscale_processors.get(email)
            if not existing or existing.done():
                self._upscale_processors[email] = asyncio.ensure_future(
                    self._worker_loop(email)
                )
                log.info(
                    f"[UpscaleQueue] ▶️ Worker restarted for {email} — "
                    f"{q.qsize()} pending jobs"
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
            reupscale_signature = self._build_reupscale_signature(job)
            if reupscale_signature and reupscale_signature in self._active_reupscale_signatures:
                _item_type = "images" if getattr(job, 'job_type', 'video') == 'image' else "videos"
                log.warning(
                    f"[UpscaleQueue] Skipped duplicate re-upscale for task {job.task_id} "
                    f"({len(dedup_keys)} {_item_type} already queued/running)"
                )
                return
            if reupscale_signature:
                job.reupscale_signature = reupscale_signature
                self._active_reupscale_signatures.add(reupscale_signature)
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
        stale_reupscale = {
            sig for sig in self._active_reupscale_signatures
            if sig.startswith(f"{task_id}:")
        }
        self._active_reupscale_signatures -= stale_reupscale
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
                        if getattr(job, 'reupscale_signature', ''):
                            self._active_reupscale_signatures.discard(job.reupscale_signature)
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
    
    def has_pending_work(self) -> bool:
        """Check if ANY upscale work is pending or actively processing.
        
        Used by _check_auto_stop() to prevent engine shutdown while
        upscales are still in flight. Returns True if:
        - Any per-account queue has pending jobs, OR
        - Any per-account worker task is still running
        """
        if not self._running:
            return False
        # Check queues for pending jobs
        for email, q in self._queues.items():
            if not q.empty():
                return True
        # Check worker tasks for active processing
        for email, proc in self._upscale_processors.items():
            if not proc.done():
                return True
        return False
    
    def _all_outputs_terminal(self, task) -> bool:
        """★ RC2: Check if ALL video outputs have reached a terminal upscale state.
        
        With multi-output prompts, each video is processed by a separate job.
        Only the LAST job to finish should call complete_task(). This method
        is the gate: returns True iff every slot is success/failed/skipped.
        """
        terminal = {"success", "failed", "skipped", "completed"}
        for vo in task.video_outputs:
            status = getattr(vo, 'upscale_status', '')
            if status not in terminal:
                return False
        return len(task.video_outputs) > 0
    
    async def _worker_loop(self, email: str):
        """Background worker: processes upscale jobs for one account.
        
        Concurrent model: launches jobs as fire-and-forget tasks,
        allowing multiple tasks to poll in parallel. The global
        AdaptiveBurstController limits total concurrent polls.
        """
        q = self._queues[email]
        active_jobs: List[asyncio.Task] = []
        
        while self._running and email not in self._paused_accounts:
            try:
                # Clean up completed job tasks
                done_count = sum(1 for t in active_jobs if t.done())
                active_jobs = [t for t in active_jobs if not t.done()]
                
                # (720p_priority pause logic removed — UpscaleQueue runs independently)
                
                # Adaptive job concurrency (AIMD): starts at 4, max 8
                # record_success/record_failure called at end of _process_job
                max_jobs = self._job_controller.get_limit(email)
                
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
                    self._process_job_tracked(job),
                    name=f"upscale-{job.task_id[:8]}"
                )
                active_jobs.append(task)
                log.info(
                    f"[UpscaleQueue] {email}: launched job {job.task_id[:8]} "
                    f"(active={len(active_jobs)}, limit={max_jobs}, "
                    f"burst={self._burst.active_polls}/{self._burst.max_polls})"
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
    
    async def _process_job_tracked(self, job: UpscaleJob):
        """Wrapper that tracks active_bg_upscale counter on session.
        
        Uses active_bg_upscale (display only) instead of active_upscale_workers
        (which affects ops capacity). This makes status bar ⬆️ N/M accurately
        reflect real upscale activity without starving engine workers.
        """
        upscale_count = len(job.media_ids) if job.media_ids else 1
        account = self._get_account(job.account_email)
        if account and hasattr(account, 'session'):
            account.session.active_bg_upscale += upscale_count
        try:
            await self._process_job(job)
        except Exception as e:
            self._apply_job_outcome(job, "failure", f"unhandled-exception: {e}")
            raise
        finally:
            if getattr(job, 'reupscale_signature', ''):
                self._active_reupscale_signatures.discard(job.reupscale_signature)
            if account and hasattr(account, 'session'):
                account.session.active_bg_upscale = max(
                    0, account.session.active_bg_upscale - upscale_count
                )
    
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
        
        # Dead-tab guard: skip job if account paused
        if job.account_email in self._paused_accounts:
            log.info(f"[UpscaleQueue] Skipping job {job.task_id[:12]} — account {job.account_email} paused (tab dead)")
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
            self._apply_job_outcome(job, "neutral", "cancelled-stale-job")
            return
        
        task = self._dispatcher.get_task(job.task_id)
        if not task:
            log.warning(f"[UpscaleQueue] Task {job.task_id} not found, skipping")
            self._total_failed += 1
            self._apply_job_outcome(job, "neutral", "task-not-found")
            return
        
        # Guard: if task was reset (video_outputs cleared by force retry)
        # but cancel_task_jobs wasn't called yet (race), detect via empty outputs
        if not task.video_outputs and not job.retry_indices:
            log.warning(
                f"[UpscaleQueue] Task {job.task_id[:12]} has empty video_outputs "
                f"(likely force-retried), skipping stale upscale job"
            )
            self._apply_job_outcome(job, "neutral", "empty-video-outputs")
            return
        
        # Get the account
        account = self._get_account(job.account_email)
        if not account:
            log.warning(f"[UpscaleQueue] Account {job.account_email} not found, skipping")
            self._total_failed += 1
            self._apply_job_outcome(job, "neutral", "account-not-found")
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
            self._apply_job_outcome(job, "failure", "auth-expired")
            return
        
        # ★ RC1 FIX: Per-slot media ID update (not task-level overwrite).
        # With multi-output, multiple concurrent jobs each have 1 media_id.
        # Overwriting task.upscale_media_ids would erase other jobs' IDs.
        for _rc1_local, _rc1_mid in enumerate(job.media_ids):
            _rc1_orig = job.retry_indices[_rc1_local] if job.retry_indices else _rc1_local
            if _rc1_orig < len(task.video_outputs):
                task.video_outputs[_rc1_orig].upscale_media_id = _rc1_mid
        # Rebuild full list from authoritative per-slot data
        task.upscale_media_ids = [
            getattr(vo, 'upscale_media_id', vo.media_id)
            for vo in task.video_outputs
        ]
        
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
            self._apply_job_outcome(job, "neutral", f"unsupported-resolution:{job.target_quality}")
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
        else:  # Fresh (< 2 min) — engine foreman already pre-warmed reCAPTCHA
            warmup_wait = 3   # ★ FIX: was 10s, engine already warmed up the tab
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
                    
                    # ── Pre-Submit Gate: validate xcd + reCAPTCHA before upscale ──
                    if self._pre_submit_gate_fn:
                        try:
                            _gate_ok = await self._pre_submit_gate_fn(account, task, attempt)
                            if not _gate_ok:
                                log.warning(
                                    f"Upscale {video_label}: PreSubmitGate failed "
                                    f"(attempt {attempt+1}) — waiting 8s before retry"
                                )
                                # ★ FIX: Sleep before retry — tab reload takes 10-15s.
                                # Without sleep, all 5 retries fire instantly and all
                                # fail before tab finishes reloading → upscale abandoned.
                                await asyncio.sleep(8)
                                continue
                        except Exception as _ge:
                            log.debug(f"Upscale {video_label}: gate check error: {_ge}")
                    
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
                        if recaptcha_token and len(recaptcha_token) < 1500:
                            log.warning(
                                f"Upscale {video_label}: garbage reCAPTCHA token "
                                f"({len(recaptcha_token)} chars < 1500), skipping submit"
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
                            project_id=getattr(account, 'project_id', '') or task.project_id or "",
                            paygate_tier=getattr(account, 'paygate_tier', '') or "PAYGATE_TIER_TWO",
                        )
                        ext_r = await ext_bridge.submit_upscale(
                            email=account.email, body=upscale_body,
                        )
                        from core.api_client import APIResponse
                        if ext_r and ext_r.get('success'):
                            resp = APIResponse(
                                success=True, data=ext_r.get('data', {}),
                                response_code=ext_r.get('status', 200),
                            )
                        elif ext_r:
                            resp = APIResponse(
                                success=False,
                                error=ext_r.get('error', '') or f"HTTP {ext_r.get('status', 0)}",
                                response_code=ext_r.get('status', 0),
                            )
                        else:
                            resp = APIResponse(success=False, error="Extension timeout")
                    else:
                        # ★ FALLBACK: Traditional aiohttp path
                        sem = self._semaphore_fn(account.email)
                        async with sem:
                            resp = await self._api_client.upscale_video(
                                access_token=await account.ensure_valid_token() or "",
                                recaptcha_token=recaptcha_token,
                                video_media_id=media_id,
                                project_id=getattr(account, 'project_id', '') or task.project_id or "",
                                target_resolution=resolution,
                                aspect_ratio=task.aspect_ratio,
                                seed=stable_seed,
                                paygate_tier=getattr(account, 'paygate_tier', '') or "PAYGATE_TIER_TWO",
                                account_headers=account.get_api_headers(),
                            )
                    account.invalidate_recaptcha()
                    await asyncio.sleep(1.0)
                    
                    if resp.success:
                        self._clear_cooldown(job.account_email)
                        self._consecutive_429s[job.account_email] = 0  # Reset on success
                        break
                    
                    error_lower = (resp.error or "").lower()
                    
                    # ★ RC3/409 FIX: HTTP 409 "already exists" = server already accepted.
                    # Don't retry. resp.data is usually None for 409 from extension.
                    if "already exists" in error_lower or "409" in str(resp.error):
                        log.info(
                            f"Upscale {video_label}: HTTP 409 — entity already exists. "
                            f"Treating as idempotent (data may be None)."
                        )
                        resp.success = True
                        # Ensure resp.data is safe for downstream .get() calls
                        if resp.data is None:
                            resp.data = {"operations": []}
                        break
                    
                    log.warning(
                        f"Upscale {video_label} submit attempt {attempt + 1}/{max_submit_retries} "
                        f"failed: {resp.error}"
                    )
                    
                    # ★ FIX #429: Dedicated 429 rate-limit handling
                    # Distinct from 403 path: uses Retry-After + exp backoff + jitter,
                    # only escalates to _set_cooldown after repeated 429s (not first hit).
                    is_429 = (
                        getattr(resp, 'response_code', 0) == 429
                        or "429" in error_lower
                        or "quota" in error_lower
                        or "rate" in error_lower
                    )
                    if is_429:
                        import re as _re
                        # Track consecutive 429s per account
                        prev_count = self._consecutive_429s.get(job.account_email, 0)
                        self._consecutive_429s[job.account_email] = prev_count + 1
                        n429 = self._consecutive_429s[job.account_email]
                        
                        # Parse Retry-After from error body (server may embed it)
                        retry_after = 0
                        ra_match = _re.search(r'retry[\-_ ]?after[":\s]+(\d+)', error_lower)
                        if ra_match:
                            retry_after = min(int(ra_match.group(1)), 120)  # Cap at 2 min
                        
                        # Exponential backoff + jitter (base: 5s × 2^attempt, max 60s)
                        import random as _rng
                        backoff = min(5 * (2 ** attempt), 60)
                        jitter = _rng.uniform(0, backoff * 0.3)  # ±30% jitter
                        wait_time = max(retry_after, backoff) + jitter
                        
                        log.warning(
                            f"Upscale {video_label}: HTTP 429 (consecutive #{n429}) — "
                            f"backoff {wait_time:.1f}s "
                            f"(retry_after={retry_after}, base_backoff={backoff})"
                        )
                        
                        # Escalate to cooldown only after threshold consecutive 429s
                        if n429 >= self._429_COOLDOWN_THRESHOLD:
                            log.warning(
                                f"Upscale {video_label}: {n429} consecutive 429s — "
                                f"escalating to account cooldown for {job.account_email}"
                            )
                            self._set_cooldown(
                                job.account_email,
                                f"upscale 429 x{n429} (quota exhausted)",
                            )
                            # Report to AIMD controller (halve concurrency)
                            self._job_controller.record_failure(job.account_email)
                            await self._wait_cooldown(job.account_email)
                        else:
                            await asyncio.sleep(wait_time)
                        continue  # Skip generic delay at bottom of loop
                    
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
                                # M3 Phase 2: Extended soft recovery (no browser kill)
                                try:
                                    await account.soft_recover_browser()
                                    # Simulate activity to rebuild trust score
                                    _eb = getattr(account, 'extension_bridge', None)
                                    if _eb and _eb.is_connected(account.email):
                                        try:
                                            await _eb.simulate_activity(account.email, timeout=3.0)
                                        except Exception:
                                            pass
                                    self._fix_client_data()
                                    await asyncio.sleep(15)
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
                                        await account.soft_recover_browser()
                                        self._fix_client_data()
                                        await asyncio.sleep(20)
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
                
                # Extract operation ID — null-safe (RC3: 409 responses may have None data)
                if resp.data is None:
                    log.warning(
                        f"Upscale {video_label}: resp.data is None — "
                        f"likely 409 without payload, skipping"
                    )
                    if orig_idx < len(task.video_outputs):
                        task.video_outputs[orig_idx].upscale_status = "skipped"
                        task.video_outputs[orig_idx].upscale_error = "409 already exists — no op_name"
                    continue
                ops = resp.data.get("operations", [])
                if not ops:
                    # ★ Debug: log actual response data to diagnose silent API rejection
                    import json as _json
                    _data_keys = list(resp.data.keys()) if isinstance(resp.data, dict) else type(resp.data).__name__
                    _data_preview = _json.dumps(resp.data, default=str, ensure_ascii=False)[:500] if resp.data else "None"
                    log.warning(
                        f"Upscale {video_label}: HTTP 200 OK but NO operations returned! "
                        f"data_keys={_data_keys}, preview={_data_preview}"
                    )
                    if orig_idx < len(task.video_outputs):
                        task.video_outputs[orig_idx].upscale_status = "failed"
                        task.video_outputs[orig_idx].upscale_error = "No operation returned"
                    continue
                
                op_name = ops[0].get("operation", {}).get("name", "")
                scene_id = ops[0].get("sceneId", "")
                raw_bytes = ops[0].get("rawBytes")
                re_upscale_mgid = ops[0].get("mediaGenerationId", "")
                re_upscale_status = ops[0].get("status", "")
                
                if not op_name and raw_bytes is not None:
                    # ★ Re-Upscale fast path: video already upscaled on server
                    # Response: {'mediaGenerationId': '<b64 protobuf>', 'rawBytes': '<small ID>', 'status': '...'}
                    # rawBytes is just a small binary ID (15 bytes), NOT video data.
                    # The actual download ID is in mediaGenerationId (protobuf containing UUIDs).
                    # Protobuf structure: field1=version(5), field2=project_UUID, field3=video_UUID
                    # TRPC download: media.getMediaUrlRedirect?name=video_UUID_upsampled
                    log.info(
                        f"Upscale {video_label}: ✅ Re-Upscale detected — "
                        f"video already upscaled (status={re_upscale_status})"
                    )
                    
                    # Decode mediaGenerationId protobuf to extract per-video UUID
                    re_op_name = ""
                    if re_upscale_mgid:
                        try:
                            import base64 as _b64
                            _mgid = re_upscale_mgid
                            _pad = len(_mgid) % 4
                            if _pad:
                                _mgid += '=' * (4 - _pad)
                            _pb_data = _b64.b64decode(_mgid)
                            
                            # Minimal protobuf parser: extract string fields (UUID-like)
                            _pb_strings = []
                            _pos = 0
                            while _pos < len(_pb_data):
                                _tb = _pb_data[_pos]
                                _fn = _tb >> 3
                                _wt = _tb & 7
                                _pos += 1
                                if _wt == 0:  # varint
                                    while _pos < len(_pb_data) and _pb_data[_pos] & 0x80:
                                        _pos += 1
                                    _pos += 1
                                elif _wt == 2:  # length-delimited (string)
                                    _ln = _pb_data[_pos]
                                    _pos += 1
                                    _val = _pb_data[_pos:_pos+_ln]
                                    _pos += _ln
                                    try:
                                        _s = _val.decode('utf-8')
                                        _pb_strings.append((_fn, _s))
                                    except Exception:
                                        pass
                                else:
                                    break
                            
                            log.debug(
                                f"Upscale {video_label}: mediaGenerationId decoded — "
                                f"fields: {[f'f{fn}={s}' for fn, s in _pb_strings]}"
                            )
                            
                            # Priority 1: Find field that already contains '_upsampled'
                            # (field 5 typically has the exact TRPC download op_name)
                            _upsampled_fields = [
                                s for _, s in _pb_strings
                                if '_upsampled' in s
                            ]
                            
                            if _upsampled_fields:
                                re_op_name = _upsampled_fields[0]
                                log.info(
                                    f"Upscale {video_label}: found _upsampled field "
                                    f"→ {re_op_name}"
                                )
                            else:
                                # Priority 2: Extract UUID and append _upsampled
                                import re as _re
                                _uuid_pattern = _re.compile(
                                    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-'
                                    r'[0-9a-f]{4}-[0-9a-f]{12}$'
                                )
                                _video_uuids = [
                                    s for _, s in _pb_strings
                                    if _uuid_pattern.match(s)
                                ]
                                if len(_video_uuids) >= 2:
                                    re_op_name = f"{_video_uuids[-1]}_upsampled"
                                elif _video_uuids:
                                    re_op_name = f"{_video_uuids[0]}_upsampled"
                                
                                log.info(
                                    f"Upscale {video_label}: UUIDs={_video_uuids}, "
                                    f"op_name={re_op_name}"
                                )
                        except Exception as e:
                            log.warning(
                                f"Upscale {video_label}: Failed to decode mediaGenerationId: {e}"
                            )
                    
                    if re_op_name:
                        log.info(
                            f"[UpscaleQueue] Re-Upscale {video_label}: "
                            f"fast path → {re_op_name} (skip polling, TRPC download)"
                        )
                        if orig_idx < len(task.video_outputs):
                            task.video_outputs[orig_idx].upscale_status = "completed"
                        # Add to pending_ops — skip polling, go to TRPC download in Phase 3
                        pending_ops.append((orig_idx, re_op_name, scene_id, media_id))
                        # ★ RC5 FIX: Per-task dict instead of global set
                        # Prevents concurrent jobs from clearing each other's entries
                        if not hasattr(self, '_re_upscale_ready'):
                            self._re_upscale_ready = {}  # task_id → set(op_names)
                        self._re_upscale_ready.setdefault(task.id, set()).add(re_op_name)
                    else:
                        log.warning(
                            f"Upscale {video_label}: Re-Upscale detected but could not "
                            f"extract download UUID from mediaGenerationId"
                        )
                        if orig_idx < len(task.video_outputs):
                            task.video_outputs[orig_idx].upscale_status = "failed"
                            task.video_outputs[orig_idx].upscale_error = "No UUID in mediaGenerationId"
                        continue
                    
                elif not op_name:
                    log.warning(
                        f"Upscale {video_label}: operations present but no op_name! "
                        f"ops[0]_keys={list(ops[0].keys()) if ops else 'N/A'}"
                    )
                    if orig_idx < len(task.video_outputs):
                        task.video_outputs[orig_idx].upscale_status = "failed"
                    continue
                else:
                    # Normal upscale: op_name present → will need polling
                    pass
                
                if op_name:
                    log.info(f"[UpscaleQueue] Upscale {video_label} submitted: op={op_name}")
                    if orig_idx < len(task.video_outputs):
                        task.video_outputs[orig_idx].upscale_status = "polling"
                        task.video_outputs[orig_idx].upscale_poll_count = 0
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
            # Mark this job's outputs as failed
            for local_idx, media_id in enumerate(job.media_ids):
                _exh_orig = job.retry_indices[local_idx] if job.retry_indices else local_idx
                if _exh_orig < len(task.video_outputs):
                    task.video_outputs[_exh_orig].upscale_status = "failed"
                    task.video_outputs[_exh_orig].upscale_error = "All retries exhausted"
            self._sync_status_fn(task)
            self._total_failed += 1
            
            # ★ RC2: Only complete task if ALL outputs terminal
            if self._all_outputs_terminal(task):
                from core.dispatcher import TaskStage
                task.stage = TaskStage.COMPLETED
                self._dispatcher.update_progress(task.id, 100, "⚠️ Upscale failed — 720p saved")
                self._dispatcher.complete_task(
                    task.id, output_uris=task.output_uris or [],
                )
            else:
                log.info(
                    f"[UpscaleQueue] Retries exhausted for job but other outputs "
                    f"still pending — deferring completion"
                )
            self._apply_job_outcome(job, "failure", "retries-exhausted")
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
            # ★ RC6 FIX: Safe index mapping — failed_indices are original indices
            # but job.media_ids is indexed by local position. Map through retry_indices.
            retry_media_ids = []
            for _fi in failed_indices:
                if job.retry_indices:
                    _local_pos = job.retry_indices.index(_fi) if _fi in job.retry_indices else -1
                else:
                    _local_pos = _fi
                if 0 <= _local_pos < len(job.media_ids):
                    retry_media_ids.append(job.media_ids[_local_pos])
                else:
                    log.warning(
                        f"[UpscaleQueue] Partial retry: orig_idx {_fi} not mappable "
                        f"to job.media_ids (len={len(job.media_ids)}) — skipping"
                    )
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
            # ★ RC4 FIX: Use task-level total, not job-level (which is 1 for single-video jobs)
            video_label = f"{idx + 1}/{len(task.video_outputs)}"
            
            # ★ Re-Upscale fast path: skip polling for already-completed ops
            # RC5: per-task dict lookup
            _re_ready = getattr(self, '_re_upscale_ready', {}).get(task.id, set())
            if op_name in _re_ready:
                log.info(
                    f"[UpscaleQueue] Poll {video_label}: Re-Upscale fast path — "
                    f"skip polling (already upscaled)"
                )
                if idx < len(task.video_outputs):
                    task.video_outputs[idx].upscale_status = "success"
                # Return None URI — Phase 3 will use TRPC download with op_name
                return (idx, None, op_name)
            
            # BUG-23: Exit immediately if stopped
            if not self._running:
                return (idx, None, op_name)
            
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
                    return (idx, result[0], op_name)
                
                # Poll failed — record failure for adaptive scaling
                error_text = getattr(task, 'upscale_error', '') or ''
                if '403' in error_text or 'rate' in error_text.lower():
                    await self._burst.record_failure()
                
                # Try re-submit once for 1080p (free)
                # BUG-23: Skip re-submit if stopped
                if is_free_upscale and self._running:
                    log.info(f"Upscale {video_label}: 1080p poll failed, re-submitting (free)")
                    try:
                        # ── Pre-Submit Gate: validate before re-submit ──
                        if self._pre_submit_gate_fn:
                            try:
                                _gate_ok = await self._pre_submit_gate_fn(account, task)
                                if not _gate_ok:
                                    log.warning(f"Upscale {video_label}: PreSubmitGate failed for re-submit")
                                    return (idx, None)
                            except Exception:
                                pass
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
                                # ★ FALLBACK: Traditional aiohttp path
                                recaptcha_token = await account.refresh_recaptcha() or ""
                                sem = self._semaphore_fn(account.email)
                                async with sem:
                                    resp2 = await self._api_client.upscale_video(
                                        access_token=await account.ensure_valid_token() or "",
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
                                    result2 = await self._poll_fn(
                                        task, account, video_label, op2, sid2
                                    )
                                    if result2:
                                        if idx < len(task.video_outputs):
                                            task.video_outputs[idx].upscale_status = "success"
                                        await self._burst.record_success()
                                        return (idx, result2[0], op2)
                    except Exception as e:
                        log.error(f"Upscale {video_label} re-submit error: {e}")
                        await self._burst.record_failure()
                
                # Failed
                if idx < len(task.video_outputs):
                    task.video_outputs[idx].upscale_status = "failed"
                    task.video_outputs[idx].upscale_error = task._upscale_error or "Poll failed"
                return (idx, None, op_name)
            finally:
                self._burst.release()
        
        # Fire all polls in parallel
        poll_tasks = [
            _poll_one(idx, op_name, scene_id, media_id)
            for idx, op_name, scene_id, media_id in pending_ops
        ]
        poll_results = await asyncio.gather(*poll_tasks, return_exceptions=True)
        
        # Collect upscaled URIs + op_names (for TRPC ZIP download)
        # ★ BUG-FIX: Use dicts instead of fixed-size lists to support
        # retry_indices mapping where orig_idx can exceed total
        # (e.g., per-worker jobs with media_ids=[mid], retry_indices=[3])
        upscaled_uris = {}   # orig_idx → fife_uri
        upscale_op_names = {}  # orig_idx → op_name for TRPC download
        for result in poll_results:
            if isinstance(result, Exception):
                log.error(f"[UpscaleQueue] Poll task exception: {result}")
                continue
            idx, uri, result_op_name = result
            upscaled_uris[idx] = uri
            upscale_op_names[idx] = result_op_name
            log.debug(
                f"[UpscaleQueue] Poll result: idx={idx}, "
                f"uri={'yes' if uri else 'None'}, "
                f"op_name={result_op_name[:50] if result_op_name else 'None'}"
            )
        
        # =====================================================
        # PHASE 3: Batch Download (TRPC-first for 1080p)
        # =====================================================
        upscale_paths = {}   # orig_idx → downloaded path
        uris_to_download = [(i, u) for i, u in upscaled_uris.items() if u]
        
        # ★ Re-Upscale fast path: add entries with TRPC op_name for download
        # ★ RC5 FIX: per-task dict — only pop OWN task's entries
        _re_ready = getattr(self, '_re_upscale_ready', {}).pop(task.id, set())
        if _re_ready:
            for i, op_n in upscale_op_names.items():
                if op_n and op_n in _re_ready and i not in [x[0] for x in uris_to_download]:
                    uris_to_download.append((i, None))  # None URI = TRPC-only
                    log.info(
                        f"[UpscaleQueue] Phase 3: Re-upscale video {i+1} "
                        f"→ TRPC download (op={op_n[:50]})"
                    )
        
        # Debug: summary of collected op_names for TRPC
        log.debug(
            f"[UpscaleQueue] Phase 3 start: "
            f"uris={len(uris_to_download)}/{total}, "
            f"op_names=[{', '.join(str(n[:30] if n else 'None') for n in upscale_op_names.values())}], "
            f"is_free_upscale={is_free_upscale}"
        )
        
        if uris_to_download:
            # BUG-24: Skip download if stopped
            if not self._running:
                log.info(f"[UpscaleQueue] Stopped — skipping upscale download")
            elif is_free_upscale:
                # ★ 1080p download strategy:
                # - Normal tasks: FIFE-only (reliable, no extra deps)
                # - Re-upscale (right-click): TRPC ZIP first → FIFE fallback
                #   (re-upscale has no FIFE URI, must use TRPC)
                # Better detection: check if ANY entry has None URI (re-upscale signature)
                _has_re_upscale_entries = any(u is None for _, u in uris_to_download)
                
                if _has_re_upscale_entries:
                    # Re-upscale path: TRPC ZIP first → FIFE fallback
                    self._dispatcher.update_progress(
                        task.id, 95, f"⬇️ Re-upscale: downloading {len(uris_to_download)} videos (TRPC→FIFE)"
                    )
                else:
                    # Normal task: FIFE-only
                    self._dispatcher.update_progress(
                        task.id, 95, f"⬇️ Downloading {len(uris_to_download)} upscaled videos (FIFE)"
                    )
                
                for dl_idx, (orig_idx, fife_uri) in enumerate(uris_to_download):
                    if not self._running:
                        break
                    op_name_for_dl = upscale_op_names.get(orig_idx)
                    downloaded = False
                    # Determine if THIS specific entry is a re-upscale
                    is_re_upscale_entry = fife_uri is None
                    log.debug(
                        f"[UpscaleQueue] DL video {orig_idx+1}/{total}: "
                        f"re_upscale={is_re_upscale_entry}, "
                        f"op_name={'yes('+op_name_for_dl[:40]+')' if op_name_for_dl else 'None'}, "
                        f"fife_uri={fife_uri[:60] if fife_uri else 'None'}..."
                    )
                    
                    if is_re_upscale_entry:
                        # ★ TRPC capability gate: extension-only accounts can't use TRPC
                        _has_trpc = False
                        _trpc = getattr(account, 'trpc_client', None)
                        if _trpc and hasattr(_trpc, '_page') and _trpc._page:
                            _has_trpc = True
                        if not _has_trpc:
                            log.warning(
                                f"[UpscaleQueue] Re-upscale video {orig_idx+1}/{total}: "
                                f"TRPC unavailable (extension-only) — keeping 720p"
                            )
                            if orig_idx < len(task.video_outputs):
                                task.video_outputs[orig_idx].upscale_status = "skipped"
                                task.video_outputs[orig_idx].upscale_error = _UNSUPPORTED_REUPSCALE_ERROR
                            continue
                        # ★ Re-upscale: TRPC ZIP first → FIFE fallback (4 attempts)
                        for attempt in range(4):
                            if not self._running:
                                break
                            use_trpc = (attempt % 2 == 0)  # 0,2 = TRPC; 1,3 = FIFE
                            method = "TRPC ZIP" if use_trpc else "FIFE"
                            
                            log.info(
                                f"[UpscaleQueue] Re-upscale video {orig_idx+1}/{total}: "
                                f"attempt {attempt+1}/4 via {method}"
                            )
                            
                            if use_trpc and op_name_for_dl:
                                # TRPC ZIP download
                                self._trpc_attempts += 1
                                try:
                                    path = await self._download_via_trpc_zip(
                                        task, account, orig_idx, op_name_for_dl,
                                        job.target_quality, total,
                                    )
                                    if path:
                                        upscale_paths[orig_idx] = path
                                        downloaded = True
                                        self._trpc_success += 1
                                        log.info(
                                            f"[UpscaleQueue] ✅ TRPC ZIP download success: "
                                            f"video {orig_idx+1}/{total} (re-upscale)"
                                        )
                                        break
                                    self._trpc_fail += 1
                                    log.warning(
                                        f"[UpscaleQueue] TRPC ZIP attempt {attempt+1} failed "
                                        f"for video {orig_idx+1}/{total}"
                                    )
                                except Exception as e:
                                    self._trpc_fail += 1
                                    log.warning(
                                        f"[UpscaleQueue] TRPC ZIP error (attempt {attempt+1}): {e}"
                                    )
                            elif use_trpc and not op_name_for_dl:
                                # No op_name — skip TRPC attempt
                                log.info(
                                    f"[UpscaleQueue] No op_name for video {orig_idx+1} — "
                                    f"skipping TRPC, trying FIFE"
                                )
                                continue
                            else:
                                # FIFE fallback (for re-upscale, URI is None → skip)
                                if not fife_uri:
                                    log.warning(
                                        f"[UpscaleQueue] FIFE skipped for video {orig_idx+1} — "
                                        f"no FIFE URI (re-upscale)"
                                    )
                                    continue
                                self._fife_attempts += 1
                                try:
                                    dl_paths = await self._download_fn(
                                        task, [fife_uri],
                                        quality_subfolder=job.target_quality,
                                        generate_thumbnails=False,
                                        video_index=orig_idx,
                                    )
                                    if dl_paths and dl_paths[0]:
                                        upscale_paths[orig_idx] = dl_paths[0]
                                        downloaded = True
                                        self._fife_success += 1
                                        log.info(
                                            f"[UpscaleQueue] ✅ FIFE download success: "
                                            f"video {orig_idx+1}/{total} (re-upscale fallback)"
                                        )
                                        break
                                    self._fife_fail += 1
                                except Exception as e:
                                    self._fife_fail += 1
                                    log.warning(
                                        f"[UpscaleQueue] FIFE error (attempt {attempt+1}): {e}"
                                    )
                            
                            if attempt < 3:
                                await asyncio.sleep(3)
                        
                        if not downloaded:
                            log.error(
                                f"[UpscaleQueue] ❌ Re-upscale download failed for "
                                f"video {orig_idx+1}/{total} (4 tries: TRPC→FIFE→TRPC→FIFE)"
                            )
                    else:
                        # ★ Normal task: FIFE-only (up to 4 attempts)
                        for attempt in range(4):
                            if not self._running:
                                break
                            log.info(
                                f"[UpscaleQueue] Download video {orig_idx+1}/{total}: "
                                f"attempt {attempt+1}/4 via FIFE"
                            )
                            self._fife_attempts += 1
                            try:
                                dl_paths = await self._download_fn(
                                    task, [fife_uri],
                                    quality_subfolder=job.target_quality,
                                    generate_thumbnails=False,
                                    video_index=orig_idx,
                                )
                                if dl_paths and dl_paths[0]:
                                    upscale_paths[orig_idx] = dl_paths[0]
                                    downloaded = True
                                    self._fife_success += 1
                                    log.info(
                                        f"[UpscaleQueue] ✅ FIFE download success: "
                                        f"video {orig_idx+1}/{total}"
                                    )
                                    break
                                self._fife_fail += 1
                                log.warning(
                                    f"[UpscaleQueue] FIFE attempt {attempt+1} failed "
                                    f"for video {orig_idx+1}/{total}"
                                )
                            except Exception as e:
                                self._fife_fail += 1
                                log.warning(
                                    f"[UpscaleQueue] FIFE error (attempt {attempt+1}): {e}"
                                )
                            
                            if attempt < 3:
                                await asyncio.sleep(3)
                        
                        if not downloaded:
                            log.error(
                                f"[UpscaleQueue] ❌ All FIFE download attempts failed for "
                                f"video {orig_idx+1}/{total}"
                            )
            else:
                # 4K: FIFE download only (no TRPC)
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
        
        # Merge upscaled paths with existing 720p paths — only touch THIS job's slots
        for local_idx, media_id in enumerate(job.media_ids):
            _merge_orig = job.retry_indices[local_idx] if job.retry_indices else local_idx
            _up_path = upscale_paths.get(_merge_orig)
            if _up_path and _merge_orig < len(task.video_outputs):
                task.video_outputs[_merge_orig].file_upscaled = _up_path
                task.video_outputs[_merge_orig].quality = job.target_quality
        
        # ★ RC2 FIX: Mark THIS job's outputs as terminal
        for local_idx, media_id in enumerate(job.media_ids):
            _rc2_orig = job.retry_indices[local_idx] if job.retry_indices else local_idx
            if _rc2_orig < len(task.video_outputs):
                vo = task.video_outputs[_rc2_orig]
                if upscale_paths.get(_rc2_orig):
                    if vo.upscale_status not in ("success", "completed"):
                        vo.upscale_status = "success"
                elif vo.upscale_status not in ("success", "completed", "skipped"):
                    vo.upscale_status = "failed"
        
        # Rebuild final output_uris from ALL video_outputs (not just this job's)
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
        
        # === RC2 FIX: Only complete task when ALL outputs are terminal ===
        # With multi-output, each video runs as a separate job.
        # Only the LAST job to finish should call complete_task().
        if not self._all_outputs_terminal(task):
            _terminal = sum(
                1 for vo in task.video_outputs
                if getattr(vo, 'upscale_status', '') in ("success", "failed", "skipped", "completed")
            )
            job_outcome_reason, job_outcome_detail = self._classify_job_outcome(task, job)
            log.info(
                f"[UpscaleQueue] Job for task {job.task_id[:12]} finished "
                f"({_terminal}/{len(task.video_outputs)} terminal) — "
                f"deferring completion until all outputs done"
            )
            self._apply_job_outcome(job, job_outcome_reason, job_outcome_detail)
            # Notify UI of partial progress
            if self._on_completed:
                try:
                    self._on_completed(task)
                except Exception:
                    pass
            return
        
        # === All outputs terminal — this job is the last finisher ===
        # BUG-31: Skip completion if stopped (task stays in current state for requeue)
        if not self._running:
            log.info(
                f"[UpscaleQueue] Stopped — skipping completion for task {job.task_id} "
                f"(task stays in current state for requeue)"
            )
            self._sync_status_fn(task)
            return
        
        from core.dispatcher import TaskStage
        any_success = any(
            getattr(vo, 'upscale_status', '') in ("success", "completed")
            for vo in task.video_outputs
        )
        task_all_unsupported = self._task_all_outputs_unsupported(task)
        job_outcome_reason, job_outcome_detail = self._classify_job_outcome(task, job)
        task.stage = TaskStage.COMPLETED
        
        if any_success:
            self._dispatcher.update_progress(
                task.id, 100, f"✅ Upscaled to {job.target_quality}"
            )
            self._total_completed += 1
        elif task_all_unsupported:
            self._dispatcher.update_progress(
                task.id, 100, "⚠️ Re-upscale unsupported — keeping 720p"
            )
        else:
            self._dispatcher.update_progress(
                task.id, 100, f"⚠️ Upscale failed — 720p saved"
            )
            self._total_failed += 1
        self._apply_job_outcome(job, job_outcome_reason, job_outcome_detail)
        
        # Call complete_task() — transitions task state to COMPLETED
        # NOTE: Continuation children were already activated early by engine
        # (via activate_children_early after 720p download), so we don't pass
        # continuation_frame args here — _parent_to_children already popped.
        self._dispatcher.complete_task(
            task.id,
            output_uris=task.output_uris or [],
        )
        
        log.info(
            f"[UpscaleQueue] ✅ Task {job.task_id[:12]} COMPLETED — "
            f"all {len(task.video_outputs)} outputs terminal"
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
    
    async def _download_via_trpc_zip(
        self,
        task,
        account,
        video_idx: int,
        op_name: str,
        target_quality: str,
        total_videos: int,
    ) -> Optional[str]:
        """Download upscaled video via TRPC ZIP endpoint.
        
        Flow:
        1. Get GCS signed URL via TRPCClient.get_media_download_url(op_name)
        2. Download ZIP file via aiohttp
        3. Extract MP4 from ZIP
        4. Rename to match naming convention
        5. Apply zoom+crop if settings.download_non_watermark
        6. Clean up ZIP
        
        Args:
            task: Task object (for naming, output folder)
            account: Account with browser session for TRPC cookies
            video_idx: Original video index (0-based)
            op_name: Operation name from poll result
            target_quality: "1080p" or "4K"
            total_videos: Total number of videos in this task
            
        Returns:
            Local file path string, or None if failed
        """
        import aiohttp
        import zipfile
        import tempfile
        from pathlib import Path
        
        video_label = f"{video_idx + 1}/{total_videos}"
        
        # Step 1: Get TRPCClient from account's browser session
        log.debug(
            f"[TRPC-DL] {video_label}: Starting — op_name={op_name[:60]}, "
            f"quality={target_quality}, account={getattr(account, 'email', 'unknown')[:30]}"
        )
        
        page = None
        browser_session = getattr(account, '_browser_session', None)
        log.debug(f"[TRPC-DL] {video_label}: _browser_session={'exists' if browser_session else 'None'}")
        if browser_session:
            page = getattr(browser_session, '_page', None)
            log.debug(f"[TRPC-DL] {video_label}: _browser_session._page={'exists' if page else 'None'}")
        if not page:
            # Fallback: try account.session
            session = getattr(account, 'session', None)
            log.debug(f"[TRPC-DL] {video_label}: account.session={'exists' if session else 'None'}")
            if session:
                page = getattr(session, '_page', None) or getattr(session, 'page', None)
                log.debug(f"[TRPC-DL] {video_label}: session page={'exists' if page else 'None'}")
        
        if not page:
            log.warning(f"[TRPC-DL] {video_label}: No browser page available for TRPC call")
            return None
        
        log.debug(f"[TRPC-DL] {video_label}: ✅ Got browser page — creating TRPCClient")
        from core.trpc_client import TRPCClient
        trpc_client = TRPCClient(page)
        
        # Step 2: Get GCS signed URL
        # Warm-up: ensure browser page session is ready for TRPC fetch
        # (first attempt can fail if page cookies/auth state not yet initialized)
        try:
            ready_state = await page.evaluate("document.readyState")
            if ready_state != "complete":
                log.debug(f"[TRPC-DL] {video_label}: Page readyState={ready_state}, waiting...")
                await asyncio.sleep(2.0)
        except Exception:
            pass
        
        log.info(f"[TRPC-DL] {video_label}: Getting download URL for {op_name[:50]}...")
        download_url = await trpc_client.get_media_download_url(op_name)
        
        if not download_url:
            log.warning(f"[TRPC-DL] {video_label}: Failed to get download URL")
            return None
        
        # Step 3: Determine output path
        from config.settings import get_settings
        settings = get_settings()
        
        output_folder = (getattr(task, 'output_folder', '') or settings.output_folder or '').strip()
        if not output_folder:
            log.warning(f"[TRPC-DL] {video_label}: No output_folder configured")
            return None
        
        project_name = (getattr(task, 'project_name', '') or "Untitled").strip()
        output_path = Path(output_folder) / project_name / target_quality.strip()
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Build filename (same convention as _download_outputs_inner)
        prompt_num = getattr(task, 'prompt_index', 0) + 1
        idx_str = str(prompt_num).zfill(3)
        variant_letters = "abcdefghijklmnopqrstuvwxyz"
        task_output_count = getattr(task, 'output_count', 1) or 1
        is_multi = total_videos > 1 or task_output_count > 1
        
        parts = []
        if is_multi and video_idx < len(variant_letters):
            parts.append(f"{idx_str}{variant_letters[video_idx]}")
        else:
            parts.append(idx_str)
        
        if settings.include_quality:
            parts.append(target_quality)
        if settings.include_model:
            model_short = task.model.replace("veo_3_1_", "v31_").replace("_fast_", "_")
            parts.append(model_short)
        
        sep = settings.separator
        filename = sep.join(parts) + ".mp4"
        filepath = output_path / filename
        
        # Avoid overwrite
        counter = 1
        while filepath.exists():
            filepath = output_path / f"{sep.join(parts)}_{counter}.mp4"
            counter += 1
        
        # Step 4: Download file from GCS (may be MP4 directly or ZIP)
        dl_path = None
        try:
            dl_timeout = aiohttp.ClientTimeout(total=180, sock_read=90)
            async with aiohttp.ClientSession(timeout=dl_timeout) as session:
                log.info(f"[TRPC-DL] {video_label}: Downloading from GCS...")
                async with session.get(download_url) as resp:
                    if resp.status != 200:
                        log.warning(
                            f"[TRPC-DL] {video_label}: GCS download failed — "
                            f"HTTP {resp.status}"
                        )
                        return None
                    
                    content_type = resp.headers.get("Content-Type", "")
                    log.debug(
                        f"[TRPC-DL] {video_label}: Content-Type={content_type}, "
                        f"Content-Length={resp.headers.get('Content-Length', '?')}"
                    )
                    
                    # Save to temp file first
                    dl_path = Path(tempfile.mktemp(suffix=".tmp", prefix="veo_trpc_"))
                    with open(dl_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
            
            dl_size = dl_path.stat().st_size
            if dl_size < 100_000:  # < 100KB = probably an error response
                log.warning(
                    f"[TRPC-DL] {video_label}: Download too small ({dl_size:,} bytes) — "
                    f"likely error response"
                )
                return None
            
            log.info(f"[TRPC-DL] {video_label}: Downloaded ({dl_size:,} bytes)")
            
            # Step 5: Detect file type — check magic bytes
            with open(dl_path, "rb") as f:
                magic = f.read(4)
            
            is_zip = (magic[:2] == b'PK')  # ZIP magic: PK\x03\x04
            is_mp4 = (magic[:4] in (b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c', b'\x00\x00\x00\x20'))
            # ftyp box detection — more robust MP4 check
            if not is_mp4 and not is_zip:
                with open(dl_path, "rb") as f:
                    header = f.read(12)
                    is_mp4 = b'ftyp' in header
            
            if is_zip:
                # ZIP archive — extract MP4
                log.info(f"[TRPC-DL] {video_label}: File is ZIP — extracting...")
                with zipfile.ZipFile(dl_path, 'r') as zf:
                    mp4_files = [fn for fn in zf.namelist() if fn.lower().endswith('.mp4')]
                    if not mp4_files:
                        mp4_files = [
                            fn for fn in zf.namelist()
                            if fn.lower().endswith(('.mp4', '.webm', '.mov'))
                        ]
                    
                    if not mp4_files:
                        log.warning(
                            f"[TRPC-DL] {video_label}: No video files found in ZIP "
                            f"(contents: {zf.namelist()[:5]})"
                        )
                        return None
                    
                    source_name = mp4_files[0]
                    temp_extract = Path(tempfile.mktemp(suffix=".mp4", prefix="veo_extract_"))
                    with zf.open(source_name) as src, open(temp_extract, 'wb') as dst:
                        import shutil
                        shutil.copyfileobj(src, dst)
                
                extract_size = temp_extract.stat().st_size
                if extract_size < 500_000:  # < 500KB = suspicious
                    log.warning(
                        f"[TRPC-DL] {video_label}: Extracted MP4 too small "
                        f"({extract_size:,} bytes)"
                    )
                    temp_extract.unlink(missing_ok=True)
                    return None
                
                import shutil
                shutil.move(str(temp_extract), str(filepath))
                log.info(
                    f"[TRPC-DL] {video_label}: ✅ Extracted {source_name} → "
                    f"{filepath.name} ({extract_size:,} bytes)"
                )
            else:
                # Direct MP4 file — rename to final path
                log.info(f"[TRPC-DL] {video_label}: File is direct MP4 — saving...")
                import shutil
                shutil.move(str(dl_path), str(filepath))
                dl_path = None  # Prevent cleanup
                log.info(
                    f"[TRPC-DL] {video_label}: ✅ Saved direct MP4 → "
                    f"{filepath.name} ({dl_size:,} bytes)"
                )
            
            # Step 6: Apply zoom+crop if enabled
            if self._zoom_crop_fn and settings.download_non_watermark:
                try:
                    await self._zoom_crop_fn(filepath, task.aspect_ratio)
                except Exception as wm_err:
                    log.warning(
                        f"[TRPC-DL] {video_label}: zoom+crop failed: {wm_err}"
                    )
            
            return str(filepath)
            
        except Exception as e:
            log.error(f"[TRPC-DL] {video_label}: Error: {e}")
            # Clean up partial file
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError:
                    pass
            return None
        finally:
            # Clean up temp download
            if dl_path and dl_path.exists():
                try:
                    dl_path.unlink()
                except OSError:
                    pass
    
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
                
                # ★ FIX H3: Check reCAPTCHA readiness (image upscale was bypassing this)
                # Wait up to 15s for reCAPTCHA to warm up — same as video submit path
                if ext_bridge and ext_bridge.is_connected(account.email):
                    rc_ready = ext_bridge._recaptcha_readiness.get(account.email, False)
                    if not rc_ready:
                        log.info(
                            f"[UpscaleQ-Image] {idx+1}/{total}: "
                            f"reCAPTCHA cold — waiting up to 15s for warm-up"
                        )
                        for _rc_w in range(15):
                            await asyncio.sleep(1.0)
                            if ext_bridge._recaptcha_readiness.get(account.email, False):
                                log.info(
                                    f"[UpscaleQ-Image] {idx+1}/{total}: "
                                    f"reCAPTCHA warmed up after {_rc_w+1}s"
                                )
                                break
                        else:
                            log.warning(
                                f"[UpscaleQ-Image] {idx+1}/{total}: "
                                f"reCAPTCHA still cold after 15s — proceeding anyway"
                            )
                
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
                                # ★ Regenerate thumbnail from upscaled image
                                try:
                                    from PIL import Image as _Img
                                    thumb_dir = Path.home() / ".veoauto" / "cache" / "thumbnails"
                                    thumb_dir.mkdir(parents=True, exist_ok=True)
                                    _tpath = thumb_dir / f"{task.id}_{idx}.jpg"
                                    with _Img.open(str(upscale_path)) as _im:
                                        _r = 200 / _im.width
                                        _ns = (200, max(1, int(_im.height * _r)))
                                        _th = _im.resize(_ns, _Img.LANCZOS)
                                        if _th.mode in ('RGBA', 'P'):
                                            _th = _th.convert('RGB')
                                        _th.save(str(_tpath), 'JPEG', quality=90)
                                    vo.thumbnail_path = str(_tpath)
                                    log.debug(f"[UpscaleQ-Image] Thumbnail regenerated: {_tpath.name}")
                                except Exception as _te:
                                    log.debug(f"[UpscaleQ-Image] Thumb regen skipped: {_te}")
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
