"""
VEO Pro Max - Dispatcher (THẦU)

Reference: MULTITHREADING_ARCHITECTURE.md
Role: Task queue management, dependency tracking, worker coordination

Architecture: Asyncio (Hybrid with ProcessPoolExecutor for CPU tasks)
"""

from typing import Optional, List, Dict, Set, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio
import threading
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import GenerationStatus
from core.event_manager import emit_event, EventType

log = logging.getLogger(__name__)


class TaskState(str, Enum):
    """Task states for state machine.
    
    Reference: MULTITHREADING_ARCHITECTURE.md
    Flow: PENDING → READY → RUNNING → WAITING_POLL → COMPLETED/FAILED/CANCELLED
    """
    PENDING = "pending"           # New task, not yet processed
    WAITING = "waiting"           # Waiting for dependency
    READY = "ready"               # Ready to execute
    RUNNING = "running"           # Currently executing
    WAITING_POLL = "waiting_poll" # Waiting for async result (polling)
    COMPLETED = "completed"       # Successfully completed
    FAILED = "failed"             # Failed with error
    CANCELLED = "cancelled"       # Cancelled by user


class TaskStage(str, Enum):
    """Pipeline stage checkpoint — Thợ biết resume từ đâu khi retry.
    
    Flow: INIT → SUBMITTED → GENERATED → DOWNLOADED_720 → UPSCALING → UPSCALED → COMPLETED
    Retry preserves stage → worker skips already-completed stages.
    Reset clears stage → worker starts from INIT.
    """
    INIT = "init"                     # Chưa chạy
    SUBMITTED = "submitted"           # Đã gửi prompt → có operation_names
    GENERATED = "generated"           # Poll xong → có video URLs + media_ids
    DOWNLOADED_720 = "downloaded_720" # Đã download 720p → có file_720p
    UPSCALING = "upscaling"           # Đã submit upscale
    UPSCALED = "upscaled"             # Upscale xong → có upscaled URLs
    COMPLETED = "completed"           # Hoàn tất toàn bộ


@dataclass
class VideoOutputInfo:
    """Per-video tracking — unified for 1-video and multi-video prompts."""
    index: int = 0                       # Submit order (0-based)
    
    # IDs — needed for retry/re-upscale
    operation_name: str = ""             # Generation operation UUID
    scene_id: str = ""                   # Scene UUID
    media_id: str = ""                   # Protobuf Base64 — for upscale API
    
    # Files
    file_720p: str = ""                  # Local path to 720p video
    file_upscaled: str = ""              # Local path to upscaled video
    thumbnail_path: str = ""             # Local path to thumbnail JPG
    
    # Quality state
    quality: str = "pending"             # "pending" | "720p" | "1080p" | "4K"
    upscale_status: str = ""             # "" | "success" | "failed" | "skipped"
    upscale_error: str = ""              # Error message if upscale failed
    upscale_poll_count: int = 0          # Number of polling attempts (for progressive UI %)
    
    @property
    def best_file(self) -> str:
        """Highest quality file available."""
        return self.file_upscaled or self.file_720p
    
    @property
    def border_color(self) -> str:
        """Thumbnail border color based on quality state."""
        if self.upscale_status == "failed" or self.quality == "failed":
            return "red"
        if self.upscale_status in ("submitting", "polling"):
            return "purple"
        if self.quality == "retrying":
            return "purple"  # Per-video retry in progress
        if self.upscale_status == "success":
            return "blue"  # Upscale completed (2K/4K/1080p) — distinct from base green
        if self.quality in ("1080p", "4K", "2K"):
            return "blue"
        if self.quality in ("720p", "1K"):
            return "green"  # Downloaded original quality (video 720p / image 1K)
        if self.thumbnail_path:
            return "green"  # Has thumbnail = successfully generated
        return "gray"


@dataclass
class ImageUploadSlot:
    """Per-image upload tracking with retry and content hash."""
    path: str                         # Local file path
    content_hash: str = ""            # MD5 hash for dedup (computed on first upload)
    media_id: str = ""                # Server-returned mediaGenerationId
    status: str = "pending"           # pending | uploading | ready | error
    retry_count: int = 0              # Number of upload attempts
    error: str = ""                   # Last error message


@dataclass
class Task:
    """A single generation task."""
    id: str
    workflow_type: str           # T2V, I2V, R2V, T2I, I2I
    prompt: str
    
    # Configuration
    aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE"
    model: str = "veo_3_1_t2v_fast_ultra"  # Fixed: proper model key
    output_count: int = 4
    duration_seconds: int = 8
    seed: Optional[int] = None  # Seed for reproducibility (0-32767)
    
    # Image references (for I2V, R2V, I2I)
    image_uris: List[str] = field(default_factory=list)
    image_uris_account: Optional[str] = None  # Email of account that uploaded image_uris
    image_paths: List[str] = field(default_factory=list)  # Local paths from [tag] resolution
    
    # Continuation
    parent_task_id: Optional[str] = None
    continuation_frame_uri: Optional[str] = None
    continuation_frame_local_path: Optional[str] = None  # Local file path for UI thumbnail
    extract_point_ms: int = 750  # Milliseconds before video end for frame extraction
    required_account: Optional[str] = None  # D2: Force child to same account as parent
    
    # Output quality — "720p" (no upscale), "1080p", "4K"
    download_quality: str = "720p"
    output_folder: str = ""  # Sidebar output folder for downloads
    project_name: str = ""   # Sidebar project name for subfolder
    prompt_index: int = 0    # Global position in batch (0-based) for sequential naming
    
    # State
    state: TaskState = TaskState.PENDING
    stage: TaskStage = TaskStage.INIT  # Pipeline checkpoint for retry resume
    progress: int = 0              # 0-100
    error: Optional[str] = None
    retry_attempts: int = 0        # Track retries for UI display
    chain_retry_count: int = 0     # Auto-retry count for chain root (engine-level)
    dl_retry_generation_count: int = 0  # Download failure re-generation attempts (max from settings)
    retry_original_indices: List[int] = field(default_factory=list)  # Original video indices for variant letter naming
    
    # Results
    operation_name: Optional[str] = None
    operation_names: List[str] = field(default_factory=list)   # Ordered list of op UUIDs
    scene_ids: List[str] = field(default_factory=list)          # Ordered list of scene UUIDs
    output_uris: List[str] = field(default_factory=list)
    thumbnail_paths: List[str] = field(default_factory=list)  # Local paths to cached thumbnails
    video_outputs: List[VideoOutputInfo] = field(default_factory=list)  # Per-video tracking
    
    # Upscale state — derived from video_outputs (backward-compat setters absorb writes)
    upscale_media_ids: List[str] = field(default_factory=list)  # For re-upscale
    
    # Image upload tracking (for UI thumbnail effects)
    image_upload_status: str = ""      # "" | "extracting" | "uploading" | "ready" | "error"
    image_slots: List['ImageUploadSlot'] = field(default_factory=list)  # Per-image upload state
    
    # Per-video retry link: (original_task_id, video_index) or None
    replace_target: Optional[tuple] = None
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_account: Optional[str] = None
    excluded_accounts: set = field(default_factory=set)  # Smart Recovery: accounts that failed this task
    project_id: Optional[str] = None
    
    @property
    def is_continuation(self) -> bool:
        return self.parent_task_id is not None
    
    @property
    def has_dependency(self) -> bool:
        return self.is_continuation and self.continuation_frame_uri is None
    
    def __post_init__(self):
        # Backing fields for upscale_status/error absorber setters
        self._upscale_status: str = ""
        self._upscale_error: str = ""
    
    # ── Derived upscale_status: computed from video_outputs ──
    @property
    def upscale_status(self) -> str:
        """Overall upscale status derived from per-video statuses."""
        if not self.video_outputs:
            # DEBUG: No video_outputs yet — using backing field fallback
            if self._upscale_status:
                log.debug(f"[UpscaleStatus] Task {self.id}: fallback to _upscale_status='{self._upscale_status}' (no video_outputs)")
            return self._upscale_status
        statuses = [vo.upscale_status for vo in self.video_outputs]
        if all(s == "success" for s in statuses):
            return "success"
        if any(s == "failed" for s in statuses):
            return "failed"
        if any(s in ("submitting", "polling") for s in statuses):
            return "submitting"  # Still in progress
        if all(s in ("", "skipped") for s in statuses):
            return ""
        return "success"  # Mix of success + skipped
    
    @upscale_status.setter
    def upscale_status(self, value: str):
        """Absorb writes for backward compat — actual status derived from video_outputs."""
        self._upscale_status = value
    
    # ── Derived upscale_error: first failed video's error ──
    @property
    def upscale_error(self) -> str:
        """Overall upscale error from first failed video."""
        if not self.video_outputs:
            if self._upscale_error:
                log.debug(f"[UpscaleError] Task {self.id}: fallback to _upscale_error='{self._upscale_error}' (no video_outputs)")
            return self._upscale_error
        failed = [vo for vo in self.video_outputs if vo.upscale_status == "failed"]
        if failed:
            return f"Video {failed[0].index + 1}: {failed[0].upscale_error}"
        return ""
    
    @upscale_error.setter
    def upscale_error(self, value: str):
        """Absorb writes for backward compat — actual error derived from video_outputs."""
        self._upscale_error = value


@dataclass
class TaskGroup:
    """A group of related tasks (e.g., from one prompt input)."""
    id: str
    name: str
    tasks: List[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def progress(self) -> int:
        """Average per-task progress across all tasks in the group.
        
        Uses each task's individual progress (0-100) rather than just
        counting COMPLETED tasks, so the group shows meaningful progress
        even when tasks are at 88% waiting for upscale.
        """
        if not self.tasks:
            return 0
        total_progress = sum(getattr(t, 'progress', 0) or 0 for t in self.tasks)
        return int(total_progress / len(self.tasks))
    
    @property
    def status(self) -> str:
        states = [t.state for t in self.tasks]
        if all(s == TaskState.COMPLETED for s in states):
            return "completed"
        # BUG-T5: WAITING_POLL tasks are actively processing (polling API)
        if any(s in (TaskState.RUNNING, TaskState.WAITING_POLL) for s in states):
            return "running"
        if any(s == TaskState.FAILED for s in states):
            return "partial_failure"
        return "pending"


class Dispatcher:
    """THẦU - Manages task queues and dependency resolution.
    
    Responsibilities:
    - Ready Queue: Tasks ready to execute
    - Waiting Queue: Tasks waiting for dependencies
    - Dependency tracking: parent → children mapping
    - Worker coordination
    """
    
    def __init__(self, max_concurrent: int = 10):
        self._ready_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._queue_counter = 0  # Monotonic counter for FIFO ordering among same priority
        self._queued_task_ids: set = set()  # Dedup guard: task IDs currently in queue
        self._waiting_tasks: Dict[str, Task] = {}  # task_id → Task
        self._all_tasks: Dict[str, Task] = {}      # task_id → Task
        self._task_groups: Dict[str, TaskGroup] = {}
        
        # Dependency tracking: parent_id → [child_ids]
        self._parent_to_children: Dict[str, List[str]] = {}
        
        # Replacement tracking: replacement_task_id → (original_task_id, video_index)
        # Used to propagate progress from hidden replacement tasks to original slots
        self._replace_target_map: Dict[str, tuple] = {}
        
        self._lock = threading.Lock()  # threading.Lock for sync submit_task_group
        self._max_concurrent = max_concurrent
        self._running_count = 0
        
        # PA3: Per-account running task counter for fair-share balancing
        # Prevents accounts with more workers from monopolizing the queue
        self._per_account_running: Dict[str, int] = {}  # email → running count
        
        # Smart Recovery: CreditWindow reference for credit-based routing
        self._credit_window = None  # Set via set_credit_window()
        
        # reCAPTCHA health check callback — set by engine via set_recaptcha_health_fn()
        # fn(email) -> bool: True if reCAPTCHA is healthy for this account
        self._is_recaptcha_healthy_fn: Optional[Callable[[str], bool]] = None
        
        # Max workers per account callback — set by engine
        # fn(email) -> int: returns max_workers for this account (hard cap)
        self._get_max_workers_fn: Optional[Callable[[str], int]] = None
        
        # Callbacks
        self._on_task_ready: Optional[Callable[[Task], None]] = None
        self._on_task_completed: Optional[Callable[[Task], None]] = None
        self._on_task_failed: Optional[Callable[[Task, str], None]] = None
        self._on_progress_callback: Optional[Callable[[str, int, str], None]] = None
        self._on_cancel_upscale: Optional[Callable[[str], None]] = None  # cancel upscale jobs for task_id
    
    @property
    def ready_count(self) -> int:
        return self._ready_queue.qsize()
    
    @property
    def waiting_count(self) -> int:
        return len(self._waiting_tasks)
    
    @property
    def running_count(self) -> int:
        return self._running_count
    
    @property
    def total_count(self) -> int:
        return len(self._all_tasks)
    
    def get_replace_target(self, task_id: str) -> Optional[tuple]:
        """Get (original_task_id, video_index) if task_id is a replacement task."""
        return self._replace_target_map.get(task_id)
    
    # ── Public API (Cluster #2: encapsulate private internals) ──
    
    def get_all_tasks_dict(self) -> Dict[str, 'Task']:
        """Return all tasks as {id: Task} dict (internal use).
        
        Note: The List-returning get_all_tasks() at L872 is for UI display.
        Engine code that needs task-ID lookups should use this dict version.
        """
        return self._all_tasks
    
    def get_task_groups(self) -> Dict[str, 'TaskGroup']:
        """Return all task groups (read-only view).
        
        Replaces external `dispatcher._task_groups` access.
        """
        return self._task_groups
    
    def set_on_task_ready(self, callback: Optional[Callable[['Task'], None]]):
        """Set callback for when a task becomes ready.
        
        Replaces direct `dispatcher._on_task_ready = ...` assignment.
        """
        self._on_task_ready = callback
    
    def decrement_running(self, account_email: str = None):
        """Thread-safe decrement of running count (floor at 0).
        
        Replaces direct `dispatcher._running_count -= 1` mutation.
        Previously a race condition: engine mutated without lock.
        
        Args:
            account_email: If provided, also decrements _per_account_running
                for this account. MUST be provided for accurate hard-cap tracking.
        """
        with self._lock:
            self._running_count = max(0, self._running_count - 1)
        if account_email:
            self._decrement_account_running(account_email)
    
    def _decrement_account_running(self, email: Optional[str]):
        """PA3: Decrement per-account running counter."""
        if email and email in self._per_account_running:
            self._per_account_running[email] = max(
                0, self._per_account_running[email] - 1
            )
            # Clean up zero entries
            if self._per_account_running[email] == 0:
                self._per_account_running.pop(email, None)
    
    def collect_chain_descendants(self, root_id: str) -> list:
        """Public wrapper for chain descendant collection.
        
        Replaces external `dispatcher._collect_chain_descendants()` calls.
        """
        return self._collect_chain_descendants(root_id)
    
    def submit_task(self, task: Task) -> bool:
        """Submit a new task or re-submit an existing task.
        
        If task has dependencies, it goes to waiting queue.
        Otherwise, it goes to ready queue.
        
        C2 FIX: Allow re-submission of already-tracked tasks (e.g., when
        no account is available and engine puts task back in queue).
        
        Returns True if submitted successfully.
        """
        if task.id in self._all_tasks:
            # C2: Task already tracked — re-queue to ready if state allows
            existing = self._all_tasks[task.id]
            if existing.state in (TaskState.READY, TaskState.PENDING):
                # Already ready or pending, don't duplicate in queue
                return True
            # Re-queue: put back in ready queue
            existing.state = TaskState.READY
            self._queued_task_ids.discard(existing.id)  # Allow re-enqueue
            self._enqueue_task(existing, priority=0)  # Re-submit = high priority
            return True
        
        self._all_tasks[task.id] = task
        
        if task.has_dependency:
            # Add to waiting queue
            task.state = TaskState.WAITING
            self._waiting_tasks[task.id] = task
            
            # Track dependency
            parent_id = task.parent_task_id
            if parent_id not in self._parent_to_children:
                self._parent_to_children[parent_id] = []
            self._parent_to_children[parent_id].append(task.id)
        else:
            # Add to ready queue
            task.state = TaskState.READY
            self._enqueue_task(task)
            
            if self._on_task_ready:
                self._on_task_ready(task)
        
        return True
    
    def requeue_running_task(self, task: Task):
        """Re-queue a task that was interrupted (e.g., by engine stop/pause).
        
        Bug 7: Called when engine pauses to re-queue RUNNING/WAITING_POLL tasks.
        Task state should already be set to READY by the caller.
        Decrements _running_count since the task is no longer running.
        Clears assigned_account so any foreman can pick it up.
        """
        if task.state == TaskState.READY:
            self._queued_task_ids.discard(task.id)  # Allow re-enqueue
            self._enqueue_task(task, priority=0)  # Requeue = high priority
            self._running_count = max(0, self._running_count - 1)
            self._decrement_account_running(task.assigned_account)
            prev_account = task.assigned_account
            task.assigned_account = None  # Allow cross-account pickup
            log.info(
                f"[Dispatcher] 🔄 requeue_running_task({task.id}): "
                f"account={prev_account} → None, "
                f"running_count={self._running_count}"
            )
            if self._on_task_ready:
                self._on_task_ready(task)
    
    def submit_task_group(self, group: TaskGroup) -> bool:
        """Submit a group of tasks."""
        with self._lock:
            if group.id in self._task_groups:
                return False
            
            self._task_groups[group.id] = group
        
        for task in group.tasks:
            self.submit_task(task)
        
        return True
    
    def set_credit_window(self, credit_window) -> None:
        """Set CreditWindow reference for credit-based task routing."""
        self._credit_window = credit_window
    
    def set_recaptcha_health_fn(self, fn: Callable[[str], bool]) -> None:
        """Set reCAPTCHA health check callback. Called by Engine at startup."""
        self._is_recaptcha_healthy_fn = fn
    
    def set_max_workers_fn(self, fn: Callable[[str], int]) -> None:
        """Set max-workers-per-account callback. Called by Engine at startup.
        
        Prevents _per_account_running from growing beyond max_workers.
        Critical for T2I fire-and-forget which releases session workers
        immediately, allowing unbounded dispatcher task dispatch without this cap.
        """
        self._get_max_workers_fn = fn
    
    def get_next_task(self, account_email: str = None) -> Optional[Task]:
        """Pop next ready task from queue (non-blocking).
        
        Smart Recovery: Credit check FIRST — suspended accounts get nothing.
        PA3: Fair-share gate with suspended-aware average calculation.
        Excluded accounts: tasks that failed on this account are skipped.
        
        Bug 15 note: _running_count += 1 is safe in CPython because all workers
        run in the SAME event loop thread (asyncio cooperative multitasking).
        The GIL ensures atomicity for single statements in cooperative multitasking.
        
        Dedup guard: Skips tasks that are already RUNNING (stale duplicates
        left in queue from journal restore, force retry, or re-submit).
        """
        # Smart Recovery: Credit check — suspended accounts cannot pick tasks
        if account_email and self._credit_window:
            if not self._credit_window.can_accept_task(account_email):
                return None
            # Slow start check
            my_running = self._per_account_running.get(account_email, 0)
            if not self._credit_window.check_slow_start(account_email, my_running):
                log.debug(
                    f"[Dispatcher] SlowStart: {account_email} at cap "
                    f"(running={my_running}) — yielding"
                )
                return None
        
        # Hard cap: prevent _per_account_running from exceeding max_workers
        # Without this, T2I fire-and-forget releases session workers immediately,
        # allowing unbounded task dispatch (e.g., 54 tasks for max_workers=20)
        if account_email and self._get_max_workers_fn:
            my_running = self._per_account_running.get(account_email, 0)
            max_wk = self._get_max_workers_fn(account_email)
            if max_wk > 0 and my_running >= max_wk:
                log.debug(
                    f"[Dispatcher] HardCap: {account_email} running={my_running} "
                    f">= max_workers={max_wk} — yielding"
                )
                return None
        
        # PA3: Fair-share gate — only when multi-account
        # Smart Recovery: exclude suspended accounts from average calc
        if account_email and len(self._per_account_running) > 1:
            # Count only active (non-suspended) accounts for fair avg
            active_counts = {}
            for email, count in self._per_account_running.items():
                if self._credit_window and self._credit_window.is_suspended(email):
                    continue  # Skip suspended accounts
                # ★ Fix #2: Skip reCAPTCHA-dead accounts from PA3 average
                # When an account's reCAPTCHA is stuck (538-char tokens), its
                # running tasks make no progress — counting them inflates
                # the average and blocks healthy accounts from picking tasks.
                if self._is_recaptcha_healthy_fn and not self._is_recaptcha_healthy_fn(email):
                    continue  # Skip reCAPTCHA-dead accounts
                active_counts[email] = count
            
            if len(active_counts) > 1:
                total = sum(active_counts.values())
                num_active = len(active_counts)
                avg = total / num_active
                my_running = active_counts.get(account_email, 0)
                if my_running > avg + 1:
                    log.debug(
                        f"[Dispatcher] PA3: {account_email} running {my_running} "
                        f"(avg={avg:.1f}, active_accounts={num_active}) — yielding turn"
                    )
                    return None
        
        # Deferred items: tasks that can't go to this account (excluded)
        deferred = []
        # Fix: Batch-count stale entries instead of logging each one individually
        stale_dupe_count = 0
        stale_terminal_count = 0
        
        while True:
            try:
                priority, counter, task = self._ready_queue.get_nowait()
                self._queued_task_ids.discard(task.id)
                
                # Defense-in-depth: skip stale duplicates (batch-counted)
                if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                    stale_dupe_count += 1
                    continue  # Drain stale entry, try next
                if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                    stale_terminal_count += 1
                    continue  # Drain stale entry, try next
                
                # Smart Recovery: skip tasks that excluded this account
                excluded = getattr(task, 'excluded_accounts', set())
                if account_email and account_email in excluded:
                    deferred.append((priority, counter, task))
                    continue  # Try next task
                
                task.state = TaskState.RUNNING
                task._counter_decremented = False  # Reset flag for new run
                task.started_at = datetime.now()
                self._running_count += 1
                
                # PA3: Track per-account running count
                if account_email:
                    task.assigned_account = account_email
                    self._per_account_running[account_email] = \
                        self._per_account_running.get(account_email, 0) + 1
                
                # Emit summary for stale entries drained during this pick
                if stale_dupe_count or stale_terminal_count:
                    log.debug(
                        f"[Dispatcher] Drained {stale_dupe_count + stale_terminal_count} "
                        f"stale queue entries (dupes={stale_dupe_count}, "
                        f"terminal={stale_terminal_count})"
                    )
                
                log.info(
                    f"[Dispatcher] 📋 Task {task.id} READY → RUNNING "
                    f"(account={account_email}, running_count={self._running_count})"
                )
                
                # Put deferred items back before returning
                for item in deferred:
                    self._ready_queue.put_nowait(item)
                    self._queued_task_ids.add(item[2].id)
                if deferred:
                    log.debug(
                        f"[Dispatcher] Deferred {len(deferred)} tasks "
                        f"(excluded {account_email})"
                    )
                
                return task
            except asyncio.QueueEmpty:
                # Emit summary for stale entries drained
                if stale_dupe_count or stale_terminal_count:
                    log.debug(
                        f"[Dispatcher] Drained {stale_dupe_count + stale_terminal_count} "
                        f"stale queue entries (dupes={stale_dupe_count}, "
                        f"terminal={stale_terminal_count})"
                    )
                # Put deferred items back
                for item in deferred:
                    self._ready_queue.put_nowait(item)
                    self._queued_task_ids.add(item[2].id)
                if deferred:
                    log.debug(
                        f"[Dispatcher] Deferred {len(deferred)} tasks "
                        f"(excluded {account_email})"
                    )
                return None
    
    # ── Counter Audit ──────────────────────────────────────────
    
    def audit_counters(self) -> dict:
        """Audit running counters vs actual task states.
        
        Compares tracked _running_count and _per_account_running with
        actual task states. Logs ERROR on mismatch and auto-fixes.
        
        Returns:
            Dict with audit results for DevConsole/StatusAggregator.
        """
        # ★ Tasks with _counter_decremented=True are still RUNNING (doing I/O)
        # but their running_count was already decremented at 30% submit.
        # Exclude them from "actual" to avoid audit reverting the early-decrement.
        actual_running = sum(
            1 for t in self._all_tasks.values()
            if t.state in (TaskState.RUNNING, TaskState.WAITING_POLL)
            and not getattr(t, '_counter_decremented', False)
        )
        
        # Per-account actual counts
        actual_per_account = {}
        for t in self._all_tasks.values():
            if (t.state in (TaskState.RUNNING, TaskState.WAITING_POLL)
                    and t.assigned_account
                    and not getattr(t, '_counter_decremented', False)):
                actual_per_account[t.assigned_account] = \
                    actual_per_account.get(t.assigned_account, 0) + 1
        
        mismatches = []
        
        # Check total running count
        if actual_running != self._running_count:
            mismatches.append(
                f"_running_count: tracked={self._running_count}, actual={actual_running}"
            )
            log.error(
                f"[AUDIT] ❌ _running_count MISMATCH: "
                f"tracked={self._running_count}, actual={actual_running} — auto-fixing"
            )
            self._running_count = actual_running
        
        # Check per-account counts
        all_accounts = set(list(self._per_account_running.keys()) + list(actual_per_account.keys()))
        for email in all_accounts:
            tracked = self._per_account_running.get(email, 0)
            actual = actual_per_account.get(email, 0)
            if tracked != actual:
                mismatches.append(
                    f"_per_account[{email}]: tracked={tracked}, actual={actual}"
                )
                log.error(
                    f"[AUDIT] ❌ _per_account_running[{email}] MISMATCH: "
                    f"tracked={tracked}, actual={actual} — auto-fixing"
                )
                if actual > 0:
                    self._per_account_running[email] = actual
                else:
                    self._per_account_running.pop(email, None)
        
        # Clean up accounts with 0 running (stale entries)
        for email in list(self._per_account_running.keys()):
            if self._per_account_running[email] <= 0:
                self._per_account_running.pop(email, None)
        
        result = {
            'running_count': self._running_count,
            'per_account': dict(self._per_account_running),
            'mismatches': mismatches,
            'ok': len(mismatches) == 0,
        }
        
        if mismatches:
            log.warning(f"[AUDIT] Fixed {len(mismatches)} counter mismatch(es)")
        else:
            log.debug(
                f"[AUDIT] ✅ Counters OK — running={self._running_count}, "
                f"accounts={dict(self._per_account_running)}"
            )
        
        return result

    def complete_task(
        self,
        task_id: str,
        output_uris: List[str],
        continuation_frame_uri: Optional[str] = None,
        continuation_frame_local_path: Optional[str] = None,
    ):
        """Mark a task as completed and resolve dependencies."""
        task = self._all_tasks.get(task_id)
        if not task:
            return
        
        task.state = TaskState.COMPLETED
        task.completed_at = datetime.now()
        task.output_uris = output_uris
        task.progress = 100
        # Guard: skip decrement if engine already called decrement_running()
        # (e.g., when task was delegated to UpscaleQueue). Without this guard,
        # counters get decremented TWICE: once by engine, once here.
        if not getattr(task, '_counter_decremented', False):
            self._running_count = max(0, self._running_count - 1)
            self._decrement_account_running(task.assigned_account)
        else:
            task._counter_decremented = False  # Reset flag
        log.info(
            f"[Dispatcher] ✅ Task {task_id} → COMPLETED "
            f"(account={task.assigned_account}, outputs={len(output_uris)}, "
            f"running_count={self._running_count})"
        )
        
        # ── Result slotting: replacement task → original task's video slot ──
        replace_target = task.replace_target
        if replace_target:
            orig_task_id, orig_video_idx = replace_target
            orig_task = self._all_tasks.get(orig_task_id)
            if not orig_task:
                log.warning(f"[ResultSlot] Original task '{orig_task_id}' NOT FOUND "
                            f"for replacement {task.id} — result-slotting skipped")
            elif orig_video_idx >= len(orig_task.video_outputs):
                log.warning(f"[ResultSlot] Original task '{orig_task_id}' has "
                            f"{len(orig_task.video_outputs)} video_outputs, "
                            f"but replacement targets index {orig_video_idx} — OOB, skipped")
            elif not task.video_outputs:
                log.warning(f"[ResultSlot] Replacement {task.id} completed but "
                            f"has EMPTY video_outputs — slotting skipped")
            else:
                # Copy replacement's first video_output into original slot
                src_vo = task.video_outputs[0]
                dst_vo = orig_task.video_outputs[orig_video_idx]
                dst_vo.file_720p = src_vo.file_720p
                dst_vo.file_upscaled = src_vo.file_upscaled
                dst_vo.thumbnail_path = src_vo.thumbnail_path
                dst_vo.quality = src_vo.quality
                dst_vo.upscale_status = src_vo.upscale_status
                dst_vo.upscale_error = src_vo.upscale_error
                dst_vo.operation_name = src_vo.operation_name
                dst_vo.scene_id = src_vo.scene_id
                dst_vo.media_id = src_vo.media_id
                
                # Add file paths to original task's lists
                best = src_vo.best_file
                if best and best not in orig_task.output_uris:
                    orig_task.output_uris.append(best)
                if src_vo.thumbnail_path and src_vo.thumbnail_path not in orig_task.thumbnail_paths:
                    orig_task.thumbnail_paths.append(src_vo.thumbnail_path)
                
                log.info(f"[ResultSlot] ✅ Replacement {task.id} video[0] → "
                         f"original {orig_task_id} video[{orig_video_idx}] "
                         f"(quality={dst_vo.quality}, file={dst_vo.best_file})")
                
                # Clean replacement mapping
                self._replace_target_map.pop(task_id, None)
                
                # Trigger UI refresh on original task
                if self._on_task_completed:
                    self._on_task_completed(orig_task)
        
        # Resolve dependencies
        if task_id in self._parent_to_children:
            self._resolve_dependencies(task_id, continuation_frame_uri, continuation_frame_local_path)
        
        if self._on_task_completed:
            self._on_task_completed(task)
        emit_event(EventType.TASK_COMPLETED, {
            "task_id": task_id, "outputs": len(output_uris),
        }, source="dispatcher")
    
    def fail_task(self, task_id: str, error: str):
        """Mark a task as failed. C1: Cascade-fail waiting children."""
        task = self._all_tasks.get(task_id)
        if not task:
            return
        
        task.state = TaskState.FAILED
        # Bug #1 fix: include progress in error for diagnostic display
        if task.progress > 0 and task.progress < 100:
            task.error = f"{error} (at {task.progress}%)"
        else:
            task.error = error
        task.completed_at = datetime.now()
        # Guard: skip decrement if engine already called decrement_running()
        if not getattr(task, '_counter_decremented', False):
            self._running_count = max(0, self._running_count - 1)
            self._decrement_account_running(task.assigned_account)
        else:
            task._counter_decremented = False  # Reset flag
        log.warning(
            f"[Dispatcher] ❌ Task {task_id} → FAILED "
            f"(account={task.assigned_account}, error={error[:80]}, "
            f"running_count={self._running_count})"
        )
        
        if self._on_task_failed:
            self._on_task_failed(task, error)
        emit_event(EventType.TASK_FAILED, {
            "task_id": task_id, "error": error,
        }, source="dispatcher")
        
        # BUG-B13 fix: If this is a replacement task, reset parent's video quality
        # AUTO RE-RETRY: If replacement fails with PUBLIC_ERROR_MINOR, auto re-retry
        replace_target = task.replace_target
        if replace_target:
            orig_task_id, orig_video_idx = replace_target
            orig_task = self._all_tasks.get(orig_task_id)
            self._replace_target_map.pop(task_id, None)
            
            # Auto re-retry: if error is PUBLIC_ERROR_MINOR and retry count < 2
            retry_count = getattr(task, '_video_retry_count', 0)
            is_minor_error = 'PUBLIC_ERROR_MINOR' in error or 'MINOR' in error.upper()
            if is_minor_error and retry_count < 2 and orig_task:
                log.info(f"[Dispatcher] PUBLIC_ERROR_MINOR on replacement {task_id} "
                         f"— auto re-retry (attempt {retry_count + 1}/2)")
                # Reset parent video to 'failed' first so force_retry_video picks it up
                if orig_video_idx < len(orig_task.video_outputs):
                    vo = orig_task.video_outputs[orig_video_idx]
                    if vo.quality == 'retrying':
                        vo.quality = 'failed'
                # Schedule auto re-retry
                success = self.force_retry_video(orig_task_id, orig_video_idx)
                if success:
                    # Track retry count on the new replacement task
                    new_rep_id = None
                    for rep_id, (oid, vidx) in self._replace_target_map.items():
                        if oid == orig_task_id and vidx == orig_video_idx:
                            new_rep_id = rep_id
                            break
                    if new_rep_id and new_rep_id in self._all_tasks:
                        self._all_tasks[new_rep_id]._video_retry_count = retry_count + 1
                    log.info(f"[Dispatcher] ♻️ Auto re-retry initiated for {orig_task_id} "
                             f"video[{orig_video_idx}] (attempt {retry_count + 1})")
                    return  # Don't reset to 'failed', re-retry is in progress
            
            # Normal failure: reset parent video quality
            if orig_task and orig_video_idx < len(orig_task.video_outputs):
                vo = orig_task.video_outputs[orig_video_idx]
                if vo.quality == 'retrying':
                    vo.quality = 'failed'
                    vo.upscale_error = f"Retry failed: {error[:80]}"
                    log.info(f"[Dispatcher] Reset parent {orig_task_id} video[{orig_video_idx}] "
                             f"quality retrying→failed (replacement failed)")
        
        # C1: Cascade-fail ALL descendants waiting on this parent (recursive)
        self._cascade_fail_children(task_id, error)
    
    def _cascade_fail_children(self, parent_id: str, root_error: str):
        """Recursively cascade-fail all descendants of a failed parent.
        
        In a continuation chain A→B→C→D, failing A must also fail B, C, D.
        Without recursion, only B (direct child) would be failed, leaving
        C and D orphaned in WAITING state forever.
        """
        if parent_id not in self._parent_to_children:
            return
        
        child_ids = self._parent_to_children.pop(parent_id)
        for child_id in child_ids:
            child = self._waiting_tasks.pop(child_id, None)
            if child:
                child.state = TaskState.FAILED
                child.error = f"Parent task failed: {root_error}"
                child.completed_at = datetime.now()
                if self._on_task_failed:
                    self._on_task_failed(child, child.error)
                # Recurse: fail this child's own children too
                self._cascade_fail_children(child_id, root_error)
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task regardless of its current state.
        
        Handles all states:
        - PENDING/WAITING/READY: direct cancel
        - RUNNING/WAITING_POLL: mark as CANCELLED, engine will detect and abort
        """
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        
        if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
            return False  # Already terminal
        
        prev_state = task.state
        task.state = TaskState.CANCELLED
        
        # Remove from waiting queue
        if task_id in self._waiting_tasks:
            del self._waiting_tasks[task_id]
        
        # If was running, decrement counter so dispatcher counts stay accurate
        # Guard: skip if engine already called decrement_running() (flag=True)
        if prev_state in (TaskState.RUNNING, TaskState.WAITING_POLL):
            if not getattr(task, '_counter_decremented', False):
                self._running_count = max(0, self._running_count - 1)
                self._decrement_account_running(task.assigned_account)
            else:
                task._counter_decremented = False  # Reset flag
        
        log.info(f"[Dispatcher] Cancelled task {task_id} (was {prev_state})")
        
        # BUG-B14 fix: If this is a replacement task, reset parent's video quality
        replace_target = task.replace_target
        if replace_target:
            orig_task_id, orig_video_idx = replace_target
            orig_task = self._all_tasks.get(orig_task_id)
            if orig_task and orig_video_idx < len(orig_task.video_outputs):
                vo = orig_task.video_outputs[orig_video_idx]
                if vo.quality == 'retrying':
                    vo.quality = 'failed'
                    log.info(f"[Dispatcher] Reset parent {orig_task_id} video[{orig_video_idx}] "
                             f"quality retrying→failed (replacement cancelled)")
            self._replace_target_map.pop(task_id, None)
        
        emit_event(EventType.QUEUE_UPDATED, {
            "action": "cancel", "task_id": task_id,
        }, source="dispatcher")
        return True
    
    def remove_task(self, task_id: str) -> bool:
        """Remove a task completely from the queue (cancel + delete).
        
        BUG-B1 fix: Safe API for UI delete — handles all cleanup:
        - Cancels running/polling tasks (decrement counters)
        - Removes from _all_tasks and containing group
        - Cleans up empty groups
        - BUG-B17: Also cancels/removes any replacement tasks targeting this parent
        
        Returns True if task was found and removed.
        """
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        
        # BUG-B17 fix: Cancel orphan replacement tasks targeting this parent
        orphan_ids = [
            rep_id for rep_id, (orig_id, _) in list(self._replace_target_map.items())
            if orig_id == task_id
        ]
        for orphan_id in orphan_ids:
            orphan = self._all_tasks.get(orphan_id)
            if orphan:
                if orphan.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                    self._running_count = max(0, self._running_count - 1)
                    self._decrement_account_running(orphan.assigned_account)
                orphan.state = TaskState.CANCELLED
                self._all_tasks.pop(orphan_id, None)
                for group in self._task_groups.values():
                    group.tasks = [t for t in group.tasks if t.id != orphan_id]
            self._replace_target_map.pop(orphan_id, None)
        
        # Cancel first (handles running_count, per_account, waiting_tasks)
        self.cancel_task(task_id)
        
        # Remove from _all_tasks
        self._all_tasks.pop(task_id, None)
        
        # Remove from containing group
        empty_groups = []
        for gid, group in self._task_groups.items():
            group.tasks = [t for t in group.tasks if t.id != task_id]
            if not group.tasks:
                empty_groups.append(gid)
        
        # Clean up empty groups
        for gid in empty_groups:
            del self._task_groups[gid]
        
        log.info(f"[Dispatcher] Removed task {task_id}")
        emit_event(EventType.QUEUE_UPDATED, {
            "action": "remove", "task_id": task_id,
        }, source="dispatcher")
        return True
    
    def has_children(self, task_id: str) -> bool:
        """Check if a task has pending continuation children."""
        return task_id in self._parent_to_children and bool(self._parent_to_children[task_id])
    
    def activate_children_early(
        self,
        parent_id: str,
        frame_uri: Optional[str],
        frame_local_path: Optional[str] = None,
    ):
        """Activate waiting children BEFORE parent task is fully completed.
        
        Used when upscale is decoupled into UpscaleQueue: children only need
        the 720p continuation frame, not the upscaled output. Calling this
        early lets children start generating while parent upscales in background.
        
        Safety: _resolve_dependencies() pops _parent_to_children mapping,
        so when complete_task() runs later (from UpscaleQueue), it won't
        find any children → no double-activation.
        
        TODO [FUTURE — Frame Enhancement Pipeline]:
            Hiện tại continuation frame được extract trực tiếp từ video 720p.
            Kế hoạch bổ sung: sau khi extract frame 720p, chạy qua một bước
            enhancer (AI upscale / denoise) để nâng chất lượng frame trước khi
            inject vào child task. Flow sẽ thành:
              extract_frame(720p) → enhance_frame() → activate_children()
            Khi implement, cần:
              1. Thêm FrameEnhancer class (có thể dùng Real-ESRGAN hoặc API)
              2. Thay đổi activate_children_early() để nhận enhanced frame URI
              3. Cân nhắc timeout/fallback: nếu enhance fail → dùng frame gốc 720p
        """
        if parent_id not in self._parent_to_children:
            return
        
        import logging
        log = logging.getLogger(__name__)
        child_count = len(self._parent_to_children.get(parent_id, []))
        log.info(
            f"[EarlyActivation] Activating {child_count} children of {parent_id} "
            f"(before upscale, frame={'YES' if frame_uri else 'NO'})"
        )
        self._resolve_dependencies(parent_id, frame_uri, frame_local_path)
    
    def set_children_frame_preview(self, parent_id: str, frame_local_path: str):
        """Set frame thumbnail path on children BEFORE upload completes.
        
        This allows the Queue tab to display the extracted frame immediately
        after FFmpeg extraction, without waiting for the upload/mediaId step.
        Does NOT move children to READY state — that happens in activate_children_early().
        """
        child_ids = self._parent_to_children.get(parent_id, [])
        for child_id in child_ids:
            task = self._waiting_tasks.get(child_id) or self._all_tasks.get(child_id)
            if task:
                task.continuation_frame_local_path = frame_local_path
                task.image_upload_status = "uploading"
        
        # Trigger UI refresh so thumbnails update (safe: _on_queue_updated may not exist on Dispatcher)
        if child_ids and hasattr(self, '_on_queue_updated') and self._on_queue_updated:
            self._on_queue_updated({
                "event": "frame_preview",
                "parent_id": parent_id,
                "children": len(child_ids),
            })
    
    def _resolve_dependencies(self, parent_id: str, frame_uri: Optional[str],
                              frame_local_path: Optional[str] = None):
        """Resolve dependencies when parent completes.
        
        C2: If frame_uri is None (extraction failed), fail children.
        D2: Inject parent's assigned_account as required_account on children.
        """
        child_ids = self._parent_to_children.pop(parent_id, [])
        parent_task = self._all_tasks.get(parent_id)
        parent_account = parent_task.assigned_account if parent_task else None
        
        for child_id in child_ids:
            task = self._waiting_tasks.pop(child_id, None)
            if not task:
                continue
            
            if frame_uri:
                # Inject continuation frame + account affinity
                task.continuation_frame_uri = frame_uri
                task.continuation_frame_local_path = frame_local_path  # For UI thumbnail
                task.image_uris = [frame_uri]
                task.required_account = None  # DD1: Relaxed D2 — cross-account continuation
                
                # Move to ready queue
                task.state = TaskState.READY
                self._enqueue_task(task)
                
                if self._on_task_ready:
                    self._on_task_ready(task)
            else:
                # C2: Frame extraction failed — fail child + all its descendants
                task.state = TaskState.FAILED
                task.error = "Continuation frame extraction failed (FFmpeg unavailable or download error)"
                task.completed_at = datetime.now()
                if self._on_task_failed:
                    self._on_task_failed(task, task.error)
                # Recurse: fail this child's descendants too
                self._cascade_fail_children(child_id, task.error)
    
    def update_progress(self, task_id: str, progress: int, status_text: str = ""):
        """Update task progress and optional status text.
        
        Args:
            task_id: Task identifier
            progress: Progress percentage (0-100)
            status_text: Descriptive stage label (e.g., "🔥 Processing")
        """
        task = self._all_tasks.get(task_id)
        if task:
            new_progress = min(100, max(0, progress))
            # Bug 5 fix: Monotonic progress — never go backward
            # Exception: full reset via force_retry sets stage=INIT + progress=0
            if new_progress < task.progress and task.stage != TaskStage.INIT:
                # Skip BOTH progress decrease AND status_text regression
                # to prevent confusing "backward" text (e.g. "Submitting" → "Waiting")
                pass
            else:
                task.progress = new_progress
                if status_text:
                    task.status_text = status_text
            # ALWAYS notify UI callback — even on skipped progress decrease,
            # so status_text changes (e.g. "⬆️ Re-upscaling...") reach the UI
            if hasattr(self, '_on_progress_callback') and self._on_progress_callback:
                self._on_progress_callback(task_id, task.progress, status_text)
                
                # Forward replacement task progress to PARENT task's UI row.
                # Replacement tasks are hidden from the UI (filtered in get_queue_groups),
                # so their parent row won't refresh unless we notify for the parent ID too.
                if task.replace_target:
                    orig_id, _ = task.replace_target
                    orig_task = self._all_tasks.get(orig_id)
                    if orig_task:
                        # Store replacement progress on parent for UI to read
                        orig_task._retry_progress = task.progress
                        orig_task._retry_status_text = status_text
                        self._on_progress_callback(
                            orig_id, orig_task.progress, status_text
                        )
    
    def set_progress_callback(self, callback):
        """Register callback for progress updates: callback(task_id, progress, status_text)."""
        self._on_progress_callback = callback
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._all_tasks.get(task_id)
    
    def get_group(self, group_id: str) -> Optional[TaskGroup]:
        """Get task group by ID."""
        return self._task_groups.get(group_id)
    
    def remove_group(self, group_id: str) -> bool:
        """Remove a task group and ALL its tasks.
        
        BUG-B6 fix: Also removes tasks from _all_tasks (was leaving orphans).
        Cancels running tasks first so counters stay accurate.
        Returns True if group was found and removed.
        """
        group = self._task_groups.get(group_id)
        if not group:
            return False
        
        # Remove each task properly (cancel + remove from _all_tasks)
        for task in group.tasks:
            self.cancel_task(task.id)  # Handle running counters
            self._all_tasks.pop(task.id, None)
        
        self._task_groups.pop(group_id, None)
        log.info(f"[Dispatcher] Removed group {group_id} with {len(group.tasks)} tasks")
        return True
    
    def get_status_summary(self) -> dict:
        """Get queue status summary."""
        states = {}
        for task in self._all_tasks.values():
            states[task.state.value] = states.get(task.state.value, 0) + 1
        
        return {
            "total": self.total_count,
            "ready": self.ready_count,
            "waiting": self.waiting_count,
            "running": self.running_count,
            "by_state": states,
            "groups": len(self._task_groups),
        }
    
    def clone_task(self, task_id: str) -> Optional[str]:
        """Clone a task — fresh copy with same input data but new state.
        
        Returns new task ID, or None if source task not found.
        """
        source = self._all_tasks.get(task_id)
        if not source:
            return None
        
        import uuid
        new_id = f"clone_{uuid.uuid4().hex[:8]}"
        
        cloned = Task(
            id=new_id,
            workflow_type=source.workflow_type,
            prompt=source.prompt,
            aspect_ratio=source.aspect_ratio,
            model=source.model,
            output_count=source.output_count,
            duration_seconds=source.duration_seconds,
            image_uris=list(source.image_uris),
            image_paths=list(source.image_paths),
            download_quality=source.download_quality,
            output_folder=source.output_folder,
            project_name=source.project_name,
            extract_point_ms=source.extract_point_ms,
        )
        
        # Add to same group as source
        for group in self._task_groups.values():
            if any(t.id == task_id for t in group.tasks):
                group.tasks.append(cloned)
                break
        
        self.submit_task(cloned)
        log.info(f"[Dispatcher] Cloned {task_id} → {new_id}")
        return new_id
    
    def export_task_config(self, task_id: str) -> Optional[dict]:
        """Export a task's configuration as a serializable dict.
        
        Returns config dict, or None if task not found.
        """
        task = self._all_tasks.get(task_id)
        if not task:
            return None
        
        return {
            "workflow_type": task.workflow_type,
            "prompt": task.prompt,
            "aspect_ratio": task.aspect_ratio,
            "model": task.model,
            "output_count": task.output_count,
            "duration_seconds": task.duration_seconds,
            "image_uris": list(task.image_uris),
            "image_uris_account": task.image_uris_account,
            "image_paths": list(task.image_paths),
            "download_quality": task.download_quality,
            "output_folder": task.output_folder,
            "project_name": task.project_name,
            "extract_point_ms": task.extract_point_ms,
            "parent_task_id": task.parent_task_id,
        }
    
    def _enqueue_task(self, task: Task, priority: int = 1):
        """Add task to priority queue.
        
        Dedup guard: If task is already in the queue, skip to prevent
        multiple workers from picking the same task.
        
        Args:
            task: Task to enqueue
            priority: 0 = high (retry/requeue), 1 = normal (new task)
        """
        if task.id in self._queued_task_ids:
            log.debug(
                f"[Dispatcher] Skipped duplicate enqueue for {task.id} "
                f"(already in queue)"
            )
            return
        self._queued_task_ids.add(task.id)
        self._queue_counter += 1
        self._ready_queue.put_nowait((priority, self._queue_counter, task))
    
    def set_callbacks(
        self,
        on_ready: Optional[Callable[[Task], None]] = None,
        on_completed: Optional[Callable[[Task], None]] = None,
        on_failed: Optional[Callable[[Task, str], None]] = None,
        on_progress: Optional[Callable[[str, int, str], None]] = None,
    ):
        """Set event callbacks."""
        self._on_task_ready = on_ready
        self._on_task_completed = on_completed
        self._on_task_failed = on_failed
        if on_progress is not None:
            self._on_progress_callback = on_progress
    
    def clear_completed(self):
        """Clear completed tasks from tracking."""
        completed_ids = [
            tid for tid, task in self._all_tasks.items()
            if task.state in (TaskState.COMPLETED, TaskState.CANCELLED, TaskState.FAILED)
        ]
        for tid in completed_ids:
            del self._all_tasks[tid]
            # BUG-B18 fix: Clean stale _replace_target_map entries
            self._replace_target_map.pop(tid, None)
    
    def get_all_tasks(self) -> List[Task]:
        """Get all tasks for UI display."""
        return list(self._all_tasks.values())
    
    def get_all_groups(self) -> Dict[str, 'TaskGroup']:
        """Get all task groups for hierarchical UI display."""
        return dict(self._task_groups)
    
    def get_completed_tasks(self) -> List[Task]:
        """Get completed tasks only."""
        return [
            t for t in self._all_tasks.values()
            if t.state == TaskState.COMPLETED
        ]
    
    def retry_task(self, task_id: str, force: bool = False) -> bool:
        """Retry a task by resetting state and re-queuing.
        
        Unified entry point for both checkpoint-resume retry and full regeneration.
        
        Args:
            task_id: ID of the task to retry
            force: If False (default), preserves stage checkpoint — foreman resumes
                   from where it left off. If True, fully resets task: deletes all
                   outputs, thumbnails, video_outputs, and re-generates from scratch.
        
        If the task is a chain root with failed descendants,
        automatically uses retry_chain() to preserve continuation identity.
        """
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        
        if force:
            # Full regeneration — delegates to _force_reset_and_retry()
            return self._force_reset_and_retry(task_id)
        
        # Checkpoint-resume retry — only works for FAILED/CANCELLED tasks
        if task.state not in (TaskState.FAILED, TaskState.CANCELLED):
            return False
        
        # Chain-aware: if this task has failed descendants, use retry_chain
        if self._has_failed_descendants(task_id):
            return self.retry_chain(task_id)
        
        # ── Continuation child: special handling ──
        if task.parent_task_id:
            parent = self._all_tasks.get(task.parent_task_id)
            if parent and parent.state == TaskState.COMPLETED:
                # Parent done → need fresh frame from parent's video
                task.continuation_frame_uri = None
                task.continuation_frame_local_path = None
                task.image_uris = []
                task.image_upload_status = ""
                # Find best video from parent for frame extraction
                best_video = None
                for vo in parent.video_outputs:
                    f = vo.best_file
                    if f:
                        best_video = f
                        break
                if not best_video:
                    for uri in parent.output_uris:
                        if uri:
                            best_video = uri
                            break
                if best_video:
                    task._pending_frame_source = best_video
                    log.info(
                        f"[Dispatcher] Retry child {task_id}: "
                        f"frame source set → {best_video}"
                    )
                task.state = TaskState.READY
                task.error = None
                task.progress = 0
                task.stage = TaskStage.INIT
                task.retry_attempts += 1
                task.required_account = None
                self._queued_task_ids.discard(task.id)
                self._enqueue_task(task, priority=0)
                if self._on_task_ready:
                    self._on_task_ready(task)
                return True
            elif not parent or parent.state == TaskState.FAILED:
                # Parent failed → must retry the whole chain from root
                root_id = task.parent_task_id
                # Walk up to find the chain root
                while True:
                    root = self._all_tasks.get(root_id)
                    if root and root.parent_task_id:
                        root_id = root.parent_task_id
                    else:
                        break
                return self.retry_chain(root_id)
            else:
                # Parent still running → put child back to WAITING
                task.state = TaskState.WAITING
                task.error = None
                task.progress = 0
                task.continuation_frame_uri = None
                task.continuation_frame_local_path = None
                task.image_uris = []
                self._waiting_tasks[task.id] = task
                pid = task.parent_task_id
                if pid not in self._parent_to_children:
                    self._parent_to_children[pid] = []
                if task.id not in self._parent_to_children[pid]:
                    self._parent_to_children[pid].append(task.id)
                log.info(
                    f"[Dispatcher] Retry child {task_id}: parent still "
                    f"{parent.state.value} → WAITING"
                )
                return True
        
        # ── Standard (non-continuation) retry ──
        task.state = TaskState.READY
        task.error = None
        task.progress = 0
        task.retry_attempts += 1
        # Clear stale media IDs so engine re-uploads from image_paths.
        # MediaIds are account-bound — cross-account retry needs fresh upload.
        task.image_uris.clear()
        task.image_uris_account = None
        task.image_upload_status = ""
        # DD1: Relaxed D2 — allow cross-account retry
        task.required_account = None
        # Stage preserved — foreman will resume from checkpoint
        self._queued_task_ids.discard(task.id)  # Allow re-enqueue
        self._enqueue_task(task, priority=1)  # Normal priority: runs in FIFO ordery
        # Wake up scheduler waiting for tasks
        if self._on_task_ready:
            self._on_task_ready(task)
        return True
    
    def retry_chain(self, root_task_id: str) -> bool:
        """Retry a chain root and restore ALL descendant dependencies.
        
        Solves the identity loss bug: when retrying a continuation chain,
        children must go back to WAITING state with proper _parent_to_children
        mapping — NOT become independent READY tasks.
        
        Flow:
        1. Root → READY (re-queued with high priority)
        2. All descendants → WAITING with re-registered dependency tracking
        3. continuation_frame_uri cleared on children → has_dependency = True
        4. As root completes → _resolve_dependencies fires → child becomes READY
        """
        root = self._all_tasks.get(root_task_id)
        if not root or root.state not in (TaskState.FAILED, TaskState.CANCELLED):
            return False
        
        # Collect all descendants in the chain
        descendants = self._collect_chain_descendants(root_task_id)
        
        # Reset descendants to WAITING with proper dependency tracking
        for child in descendants:
            if child.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                continue  # Don't touch actively running tasks
            
            child.state = TaskState.WAITING
            child.error = None
            child.progress = 0
            child.stage = TaskStage.INIT
            child.continuation_frame_uri = None  # Force has_dependency = True
            child.continuation_frame_local_path = None
            child.image_uris = []  # Will be injected by _resolve_dependencies
            child.assigned_account = None  # Will be set by D2 affinity
            child.completed_at = None
            child.started_at = None
            child.operation_name = None
            child.operation_names = []
            child.scene_ids = []
            child.output_uris = []
            child.video_outputs = []
            self._waiting_tasks[child.id] = child
            
            # Re-register parent→child dependency mapping
            pid = child.parent_task_id
            if pid not in self._parent_to_children:
                self._parent_to_children[pid] = []
            if child.id not in self._parent_to_children[pid]:
                self._parent_to_children[pid].append(child.id)
        
        # Reset root to READY
        root.state = TaskState.READY
        root.error = None
        root.progress = 0
        root.stage = TaskStage.INIT
        root.retry_attempts += 1
        root.completed_at = None
        root.started_at = None
        root.operation_name = None
        root.operation_names = []
        root.scene_ids = []
        root.output_uris = []
        root.video_outputs = []
        # I2V image loss fix: clear stale media IDs so engine re-uploads
        root.image_uris = []
        root.image_upload_status = ""
        # DD1: Relaxed D2 — allow cross-account retry
        root.required_account = None
        self._queued_task_ids.discard(root.id)  # Allow re-enqueue
        self._enqueue_task(root, priority=0)
        
        if self._on_task_ready:
            self._on_task_ready(root)
        
        import logging
        log = logging.getLogger(__name__)
        log.info(
            f"[ChainRetry] Root {root_task_id} re-queued with "
            f"{len(descendants)} descendants restored to WAITING"
        )
        return True
    
    def _collect_chain_descendants(self, root_id: str) -> List[Task]:
        """Walk the task graph to find ALL descendants of a root task.
        
        Uses parent_task_id links (stored on each Task) rather than
        _parent_to_children map (which may have been pop'd by cascade-fail).
        """
        # Build reverse map: parent_id → [child tasks]
        by_parent: Dict[str, List[Task]] = {}
        for t in self._all_tasks.values():
            if t.parent_task_id:
                by_parent.setdefault(t.parent_task_id, []).append(t)
        
        # BFS from root
        descendants = []
        stack = [root_id]
        while stack:
            pid = stack.pop()
            for child in by_parent.get(pid, []):
                descendants.append(child)
                stack.append(child.id)
        return descendants
    
    def _has_failed_descendants(self, task_id: str) -> bool:
        """Check if a task has any failed/cancelled descendants."""
        descendants = self._collect_chain_descendants(task_id)
        return any(
            d.state in (TaskState.FAILED, TaskState.CANCELLED)
            for d in descendants
        )
    
    def requeue_task(self, task) -> bool:
        """Re-queue a running task without incrementing retry count.
        
        Used by network error handler / cooldown requeue: task goes back to queue
        and will be picked up after engine resumes — potentially by a different account.
        
        Important: Decrements running counters and clears assigned_account
        so the task is eligible for any account's foreman to pick up.
        """
        if not task:
            return False
        prev_state = task.state
        prev_account = task.assigned_account
        task.state = TaskState.READY
        task.error = None
        # Reset progress and status text so UI shows clean "READY" state
        task.progress = 0
        task.status_text = ""
        # Stage: reset to INIT for pre-submit tasks (T2I/I2I)
        # Preserve checkpoint for video tasks that already submitted (SUBMITTED+)
        # so they can resume polling on reconnect instead of re-submitting
        _preserve_stages = {TaskStage.SUBMITTED, TaskStage.GENERATED,
                            TaskStage.DOWNLOADED_720, TaskStage.UPSCALING,
                            TaskStage.UPSCALED}
        if task.stage not in _preserve_stages:
            task.stage = TaskStage.INIT
        # NOTE: Don't increment retry_attempts — this isn't a real failure
        
        # Decrement running counters if task was actually running
        # Guard: skip if engine already called decrement_running() (flag=True)
        if prev_state in (TaskState.RUNNING, TaskState.WAITING_POLL):
            if not getattr(task, '_counter_decremented', False):
                self._running_count = max(0, self._running_count - 1)
                self._decrement_account_running(task.assigned_account)
            else:
                task._counter_decremented = False  # Reset flag
        
        # Clear account binding so any foreman can pick this task
        task.assigned_account = None
        
        self._queued_task_ids.discard(task.id)  # Allow re-enqueue
        self._enqueue_task(task, priority=0)  # High priority: was already running
        log.debug(
            f"[Dispatcher] 🔄 requeue_task({task.id}): "
            f"{prev_state.value if hasattr(prev_state, 'value') else prev_state} → READY, "
            f"account={prev_account} → None, "
            f"running_count={self._running_count}"
        )
        # ★ Fix 3: Wake sleeping foremen so they pick up the requeued task.
        # Without this, foremen blocked on _task_available.wait() never
        # learn that a requeued READY task exists → system stalls.
        if self._on_task_ready:
            self._on_task_ready(task)
        return True
    
    def migrate_tasks(self, from_account: str) -> int:
        """Migrate all READY/queued tasks away from a suspended account.
        
        Smart Recovery: Called when CreditWindow suspends an account.
        Sets excluded_accounts so the task won't come back to this account.
        Wakes other foremen via _on_task_ready callback.
        
        Returns:
            Number of tasks migrated.
        """
        migrated = 0
        for task in self._all_tasks.values():
            if task.state != TaskState.READY:
                continue
            # Migrate tasks that were assigned to this account or have no assignment
            if task.assigned_account == from_account or task.assigned_account is None:
                task.assigned_account = None
                if not hasattr(task, 'excluded_accounts'):
                    task.excluded_accounts = set()
                task.excluded_accounts.add(from_account)
                migrated += 1
        
        if migrated > 0:
            log.info(
                f"[Dispatcher] 🔀 migrate_tasks: moved {migrated} task(s) "
                f"away from {from_account}"
            )
            # Wake other foremen
            if self._on_task_ready:
                self._on_task_ready(None)
        else:
            log.debug(
                f"[Dispatcher] migrate_tasks: no READY tasks to migrate "
                f"from {from_account}"
            )
        
        return migrated
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks. Returns count retried."""
        count = 0
        for task in list(self._all_tasks.values()):
            if task.state == TaskState.FAILED:
                if self.retry_task(task.id):
                    count += 1
        return count
    
    def force_retry_all_failed_videos(self) -> int:
        """Force retry ALL failed video slots across all tasks.
        
        Scans all tasks (including COMPLETED) for video_outputs with
        quality='failed'. Creates replacement tasks for each failed video.
        
        This handles:
        - Tasks that completed with some videos failed
        - Tasks where previous retry attempts failed
        - Replacement tasks that failed with PUBLIC_ERROR_MINOR
        
        Returns:
            Total number of failed videos retried.
        """
        retried = 0
        for task in list(self._all_tasks.values()):
            # Skip replacement tasks (they're children, not originals)
            if task.replace_target:
                continue
            # Skip running/cancelled tasks
            if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL, TaskState.CANCELLED):
                continue
            
            if not task.video_outputs:
                continue
            
            for i, vo in enumerate(task.video_outputs):
                # NOTE: Only retry quality='failed' here (video generation failure).
                # upscale_status='failed' is handled separately by Phase 3 re-upscale
                # in _run_auto_sweep() — force_retry_video would DELETE the good 720p
                # and re-generate from scratch, which is wasteful.
                if vo.quality == 'failed':
                    if self.force_retry_video(task.id, i):
                        retried += 1
        
        if retried > 0:
            log.info(f"[Dispatcher] ♻️ force_retry_all_failed_videos: retried {retried} video(s)")
        return retried
    
    def force_retry_task(self, task_id: str) -> bool:
        """Backward-compatible wrapper. Use retry_task(task_id, force=True) instead."""
        return self.retry_task(task_id, force=True)
    
    def _force_reset_and_retry(self, task_id: str) -> bool:
        """Full reset + retry: deletes all outputs and regenerates from scratch.
        
        Accepts ANY state including COMPLETED and RUNNING.
        
        Continuation-aware:
        - PARENT retry: resets + re-registers all children as WAITING
        - CHILD retry: preserves frame data + account affinity from parent
        - Protects parent video files that children need for frame extraction
        """
        import os
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        
        # ── Decrement running counters if task was actively running ──
        prev_state = task.state
        if prev_state in (TaskState.RUNNING, TaskState.WAITING_POLL):
            # Guard: skip if engine already called decrement_running() (flag=True)
            if not getattr(task, '_counter_decremented', False):
                self._running_count = max(0, self._running_count - 1)
                self._decrement_account_running(task.assigned_account)
                log.info(f"[ForceRetry] Decremented running counters for {task_id} "
                         f"(was {prev_state.value}, running_count={self._running_count})")
            else:
                task._counter_decremented = False  # Reset flag
                log.info(f"[ForceRetry] Skipped decrement for {task_id} "
                         f"(already decremented by engine)")
        
        # ── Cancel in-flight upscale jobs (prevent orphan corruption) ──
        if self._on_cancel_upscale:
            try:
                self._on_cancel_upscale(task_id)
            except Exception as e:
                log.warning(f"[ForceRetry] cancel_upscale error: {e}")
        
        # ── BUG-B10+B11: Cancel all replacement tasks for this parent ──
        # force_retry_video() creates replacement tasks linked via _replace_target_map.
        # If the parent is now force-retried (full re-gen), replacement tasks become
        # orphans that would waste API credits and crash on completion (IndexError
        # when writing to cleared video_outputs).
        orphan_ids = [
            rep_id for rep_id, (orig_id, _) in list(self._replace_target_map.items())
            if orig_id == task_id
        ]
        for orphan_id in orphan_ids:
            orphan = self._all_tasks.get(orphan_id)
            if orphan:
                if orphan.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                    # Guard: skip if engine already decremented
                    if not getattr(orphan, '_counter_decremented', False):
                        self._running_count = max(0, self._running_count - 1)
                        self._decrement_account_running(orphan.assigned_account)
                orphan.state = TaskState.CANCELLED
                self._all_tasks.pop(orphan_id, None)
                # Remove from group
                for group in self._task_groups.values():
                    group.tasks = [t for t in group.tasks if t.id != orphan_id]
                log.info(f"[ForceRetry] Cancelled orphan replacement {orphan_id}")
            self._replace_target_map.pop(orphan_id, None)
        if orphan_ids:
            log.info(f"[ForceRetry] Cleaned {len(orphan_ids)} replacement task(s) for {task_id}")
        
        # ── Identify continuation children (before deleting outputs) ──
        children_ids = [
            t.id for t in self._all_tasks.values()
            if t.parent_task_id == task_id
        ]
        has_children = bool(children_ids)
        log.info(f"[ForceRetry] Task {task_id}: found {len(children_ids)} children: {children_ids}")
        
        # ── DELETE ALL OUTPUT FILES ──
        # Always delete video files — even if children exist.
        # Children will get NEW frames from the newly generated video.
        for path in list(task.output_uris):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    log.debug(f"[ForceRetry] Deleted output: {path}")
            except Exception as e:
                log.warning(f"[ForceRetry] Could not delete {path}: {e}")
        
        # Delete cached thumbnails
        for path in list(task.thumbnail_paths):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    log.debug(f"[ForceRetry] Deleted thumbnail: {path}")
            except Exception as e:
                log.warning(f"[ForceRetry] Could not delete {path}: {e}")
        
        # Delete per-video files from video_outputs (720p, upscaled, thumbnails)
        deleted = set(task.output_uris) | set(task.thumbnail_paths)
        for vo in task.video_outputs:
            for vpath in (vo.file_720p, vo.file_upscaled, vo.thumbnail_path):
                if vpath and vpath not in deleted:
                    try:
                        if os.path.isfile(vpath):
                            os.remove(vpath)
                            log.debug(f"[ForceRetry] Deleted video_output file: {vpath}")
                    except Exception as e:
                        log.warning(f"[ForceRetry] Could not delete {vpath}: {e}")
                    deleted.add(vpath)
        
        # Delete continuation frame file from temp dir
        if task.continuation_frame_local_path:
            try:
                if os.path.isfile(task.continuation_frame_local_path):
                    os.remove(task.continuation_frame_local_path)
                    log.debug(f"[ForceRetry] Deleted continuation frame: {task.continuation_frame_local_path}")
            except Exception as e:
                log.warning(f"[ForceRetry] Could not delete frame: {e}")
        
        # ── FULL DATA RESET (every field back to initial state) ──
        task.output_uris.clear()
        task.thumbnail_paths.clear()
        task.operation_name = None
        task.operation_names.clear()
        task.scene_ids.clear()
        task.video_outputs.clear()
        task.upscale_status = ""
        task.upscale_error = ""
        task.upscale_media_ids.clear()
        task.image_upload_status = ""       # Reset upload UI status
        task.continuation_frame_uri = None  # Force fresh extraction
        task.continuation_frame_local_path = None  # Force fresh extraction
        task.image_uris.clear()             # Force re-upload of images
        task.image_uris_account = None
        # State depends on parent dependency
        if task.parent_task_id:
            parent = self._all_tasks.get(task.parent_task_id)
            parent_done = parent and parent.state == TaskState.COMPLETED if parent else True
            if parent_done and parent:
                # ★ FRAME RECOVERY: Parent is COMPLETED → extract frame from parent's video
                # Without this, child goes READY with NO continuation frame → Missing Image error
                best_video = None
                for vo in parent.video_outputs:
                    f = vo.best_file
                    if f:
                        import os as _os
                        if _os.path.isfile(f):
                            best_video = f
                            break
                if not best_video:
                    for uri in parent.output_uris:
                        if uri:
                            import os as _os
                            if _os.path.isfile(uri):
                                best_video = uri
                                break
                if best_video:
                    task._pending_frame_source = best_video
                    task.state = TaskState.READY
                    log.info(
                        f"[ForceRetry] Child {task_id}: parent COMPLETED → "
                        f"frame recovery from {best_video}"
                    )
                else:
                    # Parent's video files missing → must wait for parent re-gen
                    task.state = TaskState.WAITING
                    log.warning(
                        f"[ForceRetry] Child {task_id}: parent COMPLETED but "
                        f"no video files found → WAITING"
                    )
            elif parent_done:
                # parent_done=True but parent is None (orphan) → try READY
                task.state = TaskState.READY
            else:
                # Parent not completed → child must WAIT, not run immediately
                task.state = TaskState.WAITING
        else:
            task.state = TaskState.READY
        task.stage = TaskStage.INIT
        task.progress = 0
        task.error = None
        task.retry_attempts = 0
        task.chain_retry_count = 0          # Reset auto-retry counter too
        task.dl_retry_generation_count = 0  # Reset download-failure re-gen counter
        task.status_text = ""               # Clear stale UI status text
        task.started_at = None
        task.completed_at = None
        task.excluded_accounts = set()      # Allow any account to pick up
        # prompt_index intentionally preserved for correct file naming (NNN_*)
        # image_paths intentionally preserved (local source files, not generated data)
        # parent_task_id intentionally preserved (structural relationship)
        log.info(f"[ForceRetry] Task {task_id}: state={task.state.value}, "
                 f"prompt_index={task.prompt_index} preserved, all generated data purged")
        
        # ── Account handling ──
        if task.parent_task_id:
            # CHILD task: preserve account affinity from parent
            parent = self._all_tasks.get(task.parent_task_id)
            if parent and parent.assigned_account:
                task.required_account = parent.assigned_account
                log.info(f"[ForceRetry] Child {task_id}: preserving account affinity "
                         f"→ {parent.assigned_account}")
            else:
                task.assigned_account = None
                task.required_account = None
        else:
            # ROOT/standalone task: any account can pick this up
            task.assigned_account = None
            task.required_account = None
        
        # ── PARENT: recursively reset ALL descendants + purge their data ──
        if has_children:
            # Collect ALL descendants recursively (not just direct children)
            all_descendants = []
            queue = list(children_ids)
            while queue:
                cid = queue.pop(0)
                all_descendants.append(cid)
                grandchildren = [
                    t.id for t in self._all_tasks.values()
                    if t.parent_task_id == cid
                ]
                queue.extend(grandchildren)
            
            for desc_id in all_descendants:
                child = self._all_tasks.get(desc_id)
                if not child:
                    continue
                
                # Cancel descendant's upscale queue jobs too
                if self._on_cancel_upscale:
                    try:
                        self._on_cancel_upscale(desc_id)
                    except Exception:
                        pass
                
                # Delete descendant's files too
                for path in list(child.output_uris):
                    try:
                        if os.path.isfile(path):
                            os.remove(path)
                            log.debug(f"[ForceRetry] Deleted descendant output: {path}")
                    except Exception:
                        pass
                for path in list(child.thumbnail_paths):
                    try:
                        if os.path.isfile(path):
                            os.remove(path)
                    except Exception:
                        pass
                for vo in child.video_outputs:
                    for vpath in (vo.file_720p, vo.file_upscaled, vo.thumbnail_path):
                        if vpath:
                            try:
                                if os.path.isfile(vpath):
                                    os.remove(vpath)
                            except Exception:
                                pass
                if child.continuation_frame_local_path:
                    try:
                        if os.path.isfile(child.continuation_frame_local_path):
                            os.remove(child.continuation_frame_local_path)
                    except Exception:
                        pass
                
                # Full data reset for descendant
                child.state = TaskState.WAITING
                child.stage = TaskStage.INIT
                child.continuation_frame_uri = None
                child.continuation_frame_local_path = None
                child.image_uris.clear()
                child.image_uris_account = None
                child.image_upload_status = ""
                child.output_uris.clear()
                child.thumbnail_paths.clear()
                child.video_outputs.clear()
                child.operation_name = None
                child.operation_names.clear()
                child.scene_ids.clear()
                child.upscale_status = ""
                child.upscale_error = ""
                child.upscale_media_ids.clear()
                child.progress = 0
                child.error = None
                child.retry_attempts = 0
                child.chain_retry_count = 0
                child.dl_retry_generation_count = 0
                child.status_text = ""
                child.started_at = None
                child.completed_at = None
                child.assigned_account = None
                child.required_account = None
                child.excluded_accounts = set()
                
                # Put back in waiting_tasks
                self._waiting_tasks[desc_id] = child
                
                # Re-register parent→child link (popped by _cascade_fail_children)
                pid = child.parent_task_id
                if pid:
                    if pid not in self._parent_to_children:
                        self._parent_to_children[pid] = []
                    if desc_id not in self._parent_to_children[pid]:
                        self._parent_to_children[pid].append(desc_id)
                
                log.info(f"[ForceRetry] Descendant {desc_id} fully purged + reset to WAITING"
                         f" (parent={child.parent_task_id})")
            
            log.info(f"[ForceRetry] Purged & re-registered chain links for "
                     f"{len(all_descendants)} descendants of {task_id}")
        
        # Re-queue or register dependency
        if task.state == TaskState.READY:
            self._queued_task_ids.discard(task.id)  # Allow re-enqueue
            self._enqueue_task(task, priority=1)  # Normal priority: runs in FIFO order from Start All
            if self._on_task_ready:
                self._on_task_ready(task)
            log.info(f"[ForceRetry] Task {task_id} fully purged and re-queued"
                     f"{' (+ ' + str(len(children_ids)) + ' children → WAITING)' if has_children else ''}")
        else:
            # WAITING child: register in parent→child map (will be activated
            # when parent completes via _resolve_dependencies)
            pid = task.parent_task_id
            if pid:
                if pid not in self._parent_to_children:
                    self._parent_to_children[pid] = []
                if task_id not in self._parent_to_children[pid]:
                    self._parent_to_children[pid].append(task_id)
            self._waiting_tasks[task_id] = task
            log.info(f"[ForceRetry] Task {task_id} fully purged → WAITING for parent {pid}"
                     f"{' (+ ' + str(len(children_ids)) + ' children → WAITING)' if has_children else ''}")
        return True
    
    def force_retry_video(self, task_id: str, video_index: int) -> bool:
        """Force retry a SINGLE video by index, preserving all other videos.
        
        Instead of re-generating the entire prompt (4 videos), this:
        1. Deletes only the target video's files (720p, upscaled, thumbnail)
        2. Resets only that VideoOutputInfo slot
        3. Creates a NEW 1-output task with same prompt/config
        4. Links the new task back so its result replaces the failed slot
        
        The new replacement task:
        - Has output_count=1 (generates fresh single video)
        - Same prompt, aspect_ratio, model, workflow_type
        - Stores _replace_target = (original_task_id, video_index) for linking
        
        Returns True if retry was initiated, False if invalid index/task.
        """
        import os
        task = self._all_tasks.get(task_id)
        if not task:
            log.warning(f"[ForceRetryVideo] Task {task_id} not found")
            return False
        
        if video_index < 0 or video_index >= len(task.video_outputs):
            log.warning(f"[ForceRetryVideo] Invalid video_index {video_index} "
                        f"(task has {len(task.video_outputs)} videos)")
            return False
        
        vo = task.video_outputs[video_index]
        
        # ── Guard: if already retrying, cancel old replacement first ──
        if vo.quality == "retrying":
            # Find and cancel the old replacement task
            old_replacement_id = None
            for rep_id, (orig_id, v_idx) in list(self._replace_target_map.items()):
                if orig_id == task_id and v_idx == video_index:
                    old_replacement_id = rep_id
                    break
            
            if old_replacement_id:
                old_task = self._all_tasks.get(old_replacement_id)
                if old_task and old_task.state in (TaskState.READY, TaskState.WAITING):
                    old_task.state = TaskState.CANCELLED
                    # Remove from group
                    for group in self._task_groups.values():
                        group.tasks = [t for t in group.tasks if t.id != old_replacement_id]
                    # Remove from maps
                    self._replace_target_map.pop(old_replacement_id, None)
                    self._all_tasks.pop(old_replacement_id, None)
                    log.info(f"[ForceRetryVideo] Cancelled old retry task {old_replacement_id}")
                elif old_task and old_task.state == TaskState.RUNNING:
                    log.warning(f"[ForceRetryVideo] Video {video_index} retry is actively RUNNING, skipping")
                    return False
            
            log.info(f"[ForceRetryVideo] Re-retrying video {video_index} (replacing old retry)")
        
        log.info(f"[ForceRetryVideo] Task {task_id} video {video_index}: "
                 f"quality={vo.quality}, upscale_status={vo.upscale_status}")
        
        # ── 1. Delete only this video's files ──
        for vpath in (vo.file_720p, vo.file_upscaled, vo.thumbnail_path):
            if vpath:
                try:
                    if os.path.isfile(vpath):
                        os.remove(vpath)
                        log.debug(f"[ForceRetryVideo] Deleted: {vpath}")
                except Exception as e:
                    log.warning(f"[ForceRetryVideo] Could not delete {vpath}: {e}")
        
        # Also remove from task.output_uris / thumbnail_paths if present
        for path_list in (task.output_uris, task.thumbnail_paths):
            for vpath in (vo.file_720p, vo.file_upscaled, vo.thumbnail_path):
                if vpath and vpath in path_list:
                    path_list.remove(vpath)
        
        # ── 2. Reset this VideoOutputInfo slot ──
        vo.file_720p = ""
        vo.file_upscaled = ""
        vo.thumbnail_path = ""
        vo.quality = "retrying"  # Special state: shows ♻️ in UI
        vo.upscale_status = ""
        vo.upscale_error = ""
        vo.operation_name = ""
        vo.scene_id = ""
        vo.media_id = ""
        
        log.info(f"[ForceRetryVideo] Reset video_outputs[{video_index}] for task {task_id}")
        
        # ── 3. Create replacement 1-video task ──
        from datetime import datetime
        # Microsecond-precision ID prevents collision when retrying rapidly
        replacement_id = f"{task_id}_retry_v{video_index}_{datetime.now().strftime('%H%M%S%f')}"
        
        # Use unique prompt_index (9000+) to avoid overwriting original files
        # Original task might be prompt_index=0 → files: 001a_*.mp4
        # Replacement uses 9000+idx → files: 9001_*.mp4 (no collision)
        retry_prompt_index = 9000 + (task.prompt_index or 0) * 10 + video_index
        
        replacement = Task(
            id=replacement_id,
            workflow_type=task.workflow_type,
            prompt=task.prompt,
            aspect_ratio=task.aspect_ratio,
            model=task.model,
            output_count=1,  # Only 1 video to replace the failed slot
            duration_seconds=task.duration_seconds,
            seed=task.seed,
            download_quality=task.download_quality,
            output_folder=task.output_folder,
            project_name=task.project_name,
            prompt_index=retry_prompt_index,  # Unique index to avoid file collision
            replace_target=(task_id, video_index),  # Proper field → serialized
        )
        
        # Copy image references for I2V/R2V workflows
        if task.image_paths:
            replacement.image_paths = list(task.image_paths)
        if task.image_uris:
            replacement.image_uris = list(task.image_uris)
        
        # ── 4. Add to parent's TaskGroup for serialization + UI ──
        group_found = False
        for group in self._task_groups.values():
            if any(t.id == task_id for t in group.tasks):
                group.tasks.append(replacement)
                group_found = True
                log.info(f"[ForceRetryVideo] Added replacement to group '{group.name}' "
                         f"(now {len(group.tasks)} tasks)")
                break
        if not group_found:
            log.warning(f"[ForceRetryVideo] No group found for task {task_id} — "
                        f"replacement {replacement_id} won't be serialized in session!")
        
        # ── 5. Register replacement mapping for progress propagation ──
        self._replace_target_map[replacement_id] = (task_id, video_index)
        
        # ── 6. Register and enqueue ──
        self._all_tasks[replacement_id] = replacement
        replacement.state = TaskState.READY
        self._queued_task_ids.discard(replacement_id)
        self._enqueue_task(replacement, priority=1)  # Normal priority: FIFO order
        if self._on_task_ready:
            self._on_task_ready(replacement)
        
        log.info(f"[ForceRetryVideo] Created replacement task {replacement_id} "
                 f"(1 video, prompt_index={retry_prompt_index}) → will replace video_outputs[{video_index}]")
        
        return True
    
    def reset_all_tasks(self) -> int:
        """Reset ALL non-completed, non-running tasks. Returns count reset.
        
        Iterates through groups in creation order so tasks are re-queued
        top-to-bottom (first group first), ensuring Start All processes
        from the beginning of the queue downward.
        """
        count = 0
        # Iterate groups in chronological order for correct queue ordering
        sorted_groups = sorted(
            self._task_groups.values(),
            key=lambda g: g.created_at
        )
        for group in sorted_groups:
            for task in list(group.tasks):  # BUG-B9: snapshot for iteration safety
                # Skip completed and running tasks — only retry failed/pending/cancelled
                if task.state not in (TaskState.RUNNING, TaskState.COMPLETED, TaskState.WAITING_POLL):
                    # BUG-B16 fix: Skip replacement tasks (they'll be cleaned by parent's retry)
                    if task.replace_target:
                        continue
                    if self.force_retry_task(task.id):
                        count += 1
        return count
    
    def clear_all(self) -> int:
        """Clear ALL task groups and tasks (queue reset).
        
        Marks RUNNING/WAITING_POLL tasks as CANCELLED first so engine workers
        detect cancellation (they hold direct Task object references).
        
        Returns:
            Number of tasks removed
        """
        count = len(self._all_tasks)
        
        # Cancel all running tasks FIRST — engine workers hold task references
        for task in self._all_tasks.values():
            if task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                task.state = TaskState.CANCELLED
                self._running_count = max(0, self._running_count - 1)
        
        self._task_groups.clear()
        self._all_tasks.clear()
        self._replace_target_map.clear()  # BUG-B20 fix: Clean stale replacement mappings
        # Drain the ready queue
        while not self._ready_queue.empty():
            try:
                self._ready_queue.get_nowait()  # Discard (priority, counter, task)
            except Exception:
                break
        self._running_count = 0  # Reset to 0 since everything is cleared
        self._per_account_running.clear()  # PA3: Reset per-account counters
        log.info(f"[Dispatcher] Cleared all: {count} tasks removed")
        return count
    
    @staticmethod
    def _extract_prompt_index(task_id: str) -> int:
        """Extract prompt_index from task ID for backward compatibility.
        
        Task IDs follow the pattern: group_YYYYMMDD_HHMMSS_task_N
        where N is the 0-based prompt index within the group.
        
        Falls back to 0 if extraction fails.
        """
        try:
            if "_task_" in task_id:
                return int(task_id.rsplit("_task_", 1)[1])
        except (ValueError, IndexError):
            pass
        return 0
    
    def export_state(self) -> dict:
        """Export all task groups and tasks for session persistence.
        
        Returns:
            {"groups": [group_dicts], "task_count": int}
        """
        from core.session_manager import SessionManager
        sm = SessionManager()
        return {
            "groups": sm.serialize_queue(self._task_groups),
            "task_count": len(self._all_tasks),
        }
    
    def import_state(self, data: dict) -> int:
        """Import tasks from saved session data.
        
        Completed/failed tasks kept as history.
        Pending/ready tasks re-queued.
        
        Returns:
            Number of tasks restored
        """
        groups_data = data.get("groups", [])
        count = 0
        skipped = 0
        
        for gd in groups_data:
            group = TaskGroup(
                id=gd["id"],
                name=gd["name"],
                tasks=[],
            )
            # Restore created_at
            try:
                group.created_at = datetime.fromisoformat(gd["created_at"])
            except (ValueError, KeyError, TypeError):
                pass
            
            for td in gd.get("tasks", []):
                # ── Resolve relative paths → absolute ──
                output_folder = td.get("output_folder", "")
                project_name = td.get("project_name", "") or "Untitled"
                video_base = str(Path(output_folder) / project_name) if output_folder else ""
                cache_dir = str(Path.home() / ".veoauto" / "cache")
                
                def _abs_video(p):
                    """Resolve relative video path to absolute. Skips URLs."""
                    if not p:
                        return p
                    if p.startswith(("http://", "https://")):
                        return p
                    if not Path(p).is_absolute() and video_base:
                        return str(Path(video_base) / p)
                    return p
                
                def _abs_cache(p):
                    """Resolve relative cache path to absolute. Skips URLs."""
                    if not p:
                        return p
                    if p.startswith(("http://", "https://")):
                        return p
                    if not Path(p).is_absolute():
                        return str(Path(cache_dir) / p)
                    return p
                
                # Resolve output_uris
                raw_output_uris = td.get("output_uris", [])
                resolved_output_uris = [_abs_video(u) for u in raw_output_uris]
                
                # Resolve thumbnail_paths
                raw_thumbs = td.get("thumbnail_paths", [])
                resolved_thumbs = [_abs_cache(p) for p in raw_thumbs]
                
                # Resolve continuation_frame_local_path
                raw_frame = td.get("continuation_frame_local_path")
                resolved_frame = _abs_cache(raw_frame)
                
                task = Task(
                    id=td["id"],
                    workflow_type=td.get("workflow_type", "T2V"),
                    prompt=td.get("prompt", ""),
                    aspect_ratio=td.get("aspect_ratio", "VIDEO_ASPECT_RATIO_LANDSCAPE"),
                    model=td.get("model", ""),
                    output_count=td.get("output_count", 4),
                    duration_seconds=td.get("duration_seconds", 8),
                    seed=td.get("seed"),
                    image_uris=td.get("image_uris", []),
                    image_uris_account=td.get("image_uris_account"),
                    image_paths=td.get("image_paths", []),
                    parent_task_id=td.get("parent_task_id"),
                    continuation_frame_uri=td.get("continuation_frame_uri"),
                    continuation_frame_local_path=resolved_frame,
                    required_account=td.get("required_account"),
                    prompt_index=td.get("prompt_index", self._extract_prompt_index(td.get("id", ""))),
                    extract_point_ms=td.get("extract_point_ms", 750),
                    download_quality=td.get("download_quality", "720p"),
                    state=TaskState(td.get("state", "pending")),
                    progress=td.get("progress", 0),
                    error=td.get("error"),
                    retry_attempts=td.get("retry_attempts", 0),
                    operation_name=td.get("operation_name"),
                    output_uris=resolved_output_uris,
                    thumbnail_paths=resolved_thumbs,
                    assigned_account=td.get("assigned_account"),
                    project_id=td.get("project_id"),
                    output_folder=td.get("output_folder", ""),
                    project_name=td.get("project_name", ""),
                )
                # Restore lists that aren't constructor args
                task.operation_names = td.get("operation_names", [])
                task.scene_ids = td.get("scene_ids", [])
                task.chain_retry_count = td.get("chain_retry_count", 0)
                task.upscale_media_ids = td.get("upscale_media_ids", [])
                task.upscale_status = td.get("upscale_status", "")
                task.upscale_error = td.get("upscale_error", "")
                # Restore per-video retry link (serialized as list → tuple)
                rt = td.get("replace_target")
                if rt:
                    if isinstance(rt, (list, tuple)) and len(rt) == 2:
                        task.replace_target = tuple(rt)
                        # BUG-B15 fix: Rebuild _replace_target_map from field
                        self._replace_target_map[task.id] = task.replace_target
                        log.info(f"[SessionRestore] Task {task.id}: restored replace_target → "
                                 f"({rt[0]}, video[{rt[1]}])")
                    else:
                        log.warning(f"[SessionRestore] Task {task.id}: invalid replace_target format: {rt!r}")
                        task.replace_target = None
                # Restore timestamps
                # BUG-T6: Include started_at (was missing — timing lost on reload)
                for ts_field in ("created_at", "completed_at", "started_at"):
                    ts_val = td.get(ts_field)
                    if ts_val:
                        try:
                            setattr(task, ts_field, datetime.fromisoformat(ts_val))
                        except (ValueError, TypeError):
                            pass
                
                # Restore stage checkpoint
                stage_val = td.get("stage", "init")
                try:
                    task.stage = TaskStage(stage_val)
                except (ValueError, KeyError):
                    task.stage = TaskStage.INIT
                
                # Restore video_outputs with resolved paths
                for vod in td.get("video_outputs", []):
                    vo = VideoOutputInfo(
                        index=vod.get("index", 0),
                        operation_name=vod.get("operation_name", ""),
                        scene_id=vod.get("scene_id", ""),
                        media_id=vod.get("media_id", ""),
                        file_720p=_abs_video(vod.get("file_720p", "")),
                        file_upscaled=_abs_video(vod.get("file_upscaled", "")),
                        thumbnail_path=_abs_cache(vod.get("thumbnail_path", "")),
                        quality=vod.get("quality", "pending"),
                        upscale_status=vod.get("upscale_status", ""),
                        upscale_error=vod.get("upscale_error", ""),
                    )
                    task.video_outputs.append(vo)
                
                group.tasks.append(task)
                
                # Skip tasks already restored by crash journal
                if task.id in self._all_tasks:
                    # CRITICAL: Replace the NEW task object in group.tasks with
                    # the EXISTING one from _all_tasks. Otherwise _all_tasks and
                    # group.tasks point to different objects — force_retry modifies
                    # one but get_queue_groups reads the other → stale display.
                    group.tasks[-1] = self._all_tasks[task.id]
                    log.debug(
                        f"[Dispatcher] Skipped import for {task.id} "
                        f"(already restored from journal)"
                    )
                    skipped += 1
                    continue
                
                self._all_tasks[task.id] = task
                
                # Re-queue incomplete tasks (PENDING, READY, RUNNING, WAITING_POLL)
                # Tasks that were RUNNING/WAITING_POLL when app closed are
                # interrupted — they must restart from READY state.
                if task.state in (
                    TaskState.PENDING, TaskState.READY,
                    TaskState.RUNNING, TaskState.WAITING_POLL,
                ):
                    task.state = TaskState.READY
                    task.progress = 0
                    task.operation_name = None
                    task.assigned_account = None
                    task.retry_attempts = 0
                    # I2V image loss fix: clear stale media IDs on session restore.
                    # MediaIds from the previous session are expired — force re-upload
                    # from local files when available.
                    if task.image_paths:
                        task.image_uris = []
                        task.image_uris_account = None
                        task.image_upload_status = ""
                    self._enqueue_task(task)
                
                # Handle WAITING continuation tasks:
                # - If frame_uri already resolved → ready to run
                # - If still waiting on parent → rebuild dependency map
                elif task.state == TaskState.WAITING:
                    if task.continuation_frame_uri:
                        # Frame already resolved before app closed → safe to run
                        task.state = TaskState.READY
                        task.progress = 0
                        self._enqueue_task(task)
                    elif task.parent_task_id:
                        # Still depends on parent → rebuild dependency tracking
                        self._waiting_tasks[task.id] = task
                        pid = task.parent_task_id
                        if pid not in self._parent_to_children:
                            self._parent_to_children[pid] = []
                        self._parent_to_children[pid].append(task.id)
                
                count += 1
            
            self._task_groups[group.id] = group
        
        if count > 0:
            extra = f" ({skipped} already loaded)" if skipped else ""
            log.info(f"[Dispatcher] Restored {count} tasks from {len(groups_data)} groups{extra}")
        elif skipped > 0:
            log.debug(f"[Dispatcher] All {skipped} tasks already loaded — skipped duplicate restore")
        return count
