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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import GenerationStatus
from core.event_manager import emit_event, EventType


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
        if self.quality in ("1080p", "4K"):
            return "blue"
        if self.quality == "720p":
            return "yellow"
        return "gray"


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
    
    # Results
    operation_name: Optional[str] = None
    operation_names: List[str] = field(default_factory=list)   # Ordered list of op UUIDs
    scene_ids: List[str] = field(default_factory=list)          # Ordered list of scene UUIDs
    output_uris: List[str] = field(default_factory=list)
    thumbnail_paths: List[str] = field(default_factory=list)  # Local paths to cached thumbnails
    video_outputs: List[VideoOutputInfo] = field(default_factory=list)  # Per-video tracking
    
    # Upscale state — backward compat (overall status derived from video_outputs)
    upscale_status: str = ""           # "", "success", "failed"
    upscale_media_ids: List[str] = field(default_factory=list)  # For re-upscale
    upscale_error: str = ""            # Error message for display
    
    # Image upload tracking (for UI thumbnail effects)
    image_upload_status: str = ""      # "" | "extracting" | "uploading" | "ready" | "error"
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    assigned_account: Optional[str] = None
    project_id: Optional[str] = None
    
    @property
    def is_continuation(self) -> bool:
        return self.parent_task_id is not None
    
    @property
    def has_dependency(self) -> bool:
        return self.is_continuation and self.continuation_frame_uri is None


@dataclass
class TaskGroup:
    """A group of related tasks (e.g., from one prompt input)."""
    id: str
    name: str
    tasks: List[Task] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def progress(self) -> int:
        if not self.tasks:
            return 0
        completed = sum(1 for t in self.tasks if t.state == TaskState.COMPLETED)
        return int(completed / len(self.tasks) * 100)
    
    @property
    def status(self) -> str:
        states = [t.state for t in self.tasks]
        if all(s == TaskState.COMPLETED for s in states):
            return "completed"
        if any(s == TaskState.RUNNING for s in states):
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
        self._waiting_tasks: Dict[str, Task] = {}  # task_id → Task
        self._all_tasks: Dict[str, Task] = {}      # task_id → Task
        self._task_groups: Dict[str, TaskGroup] = {}
        
        # Dependency tracking: parent_id → [child_ids]
        self._parent_to_children: Dict[str, List[str]] = {}
        
        self._lock = threading.Lock()  # threading.Lock for sync submit_task_group
        self._max_concurrent = max_concurrent
        self._running_count = 0
        
        # Callbacks
        self._on_task_ready: Optional[Callable[[Task], None]] = None
        self._on_task_completed: Optional[Callable[[Task], None]] = None
        self._on_task_failed: Optional[Callable[[Task, str], None]] = None
    
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
    
    def requeue_task(self, task: Task):
        """Re-queue a task that was interrupted (e.g., by engine stop).
        
        Bug 7: Called when engine pauses to re-queue RUNNING/WAITING_POLL tasks.
        Task state should already be set to READY by the caller.
        Decrements _running_count since the task is no longer running.
        """
        if task.state == TaskState.READY:
            self._enqueue_task(task, priority=0)  # Requeue = high priority
            self._running_count = max(0, self._running_count - 1)
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
    
    def get_next_task(self, timeout: Optional[float] = None) -> Optional[Task]:
        """Get the next ready task.
        
        Non-blocking. Returns None if no task available.
        
        Bug 15 note: _running_count += 1 is safe in CPython because all workers
        run on the same asyncio event loop and get_nowait() is synchronous.
        The GIL ensures atomicity for single statements in cooperative multitasking.
        """
        try:
            _, _, task = self._ready_queue.get_nowait()
            task.state = TaskState.RUNNING
            task.started_at = datetime.now()
            self._running_count += 1
            return task
        except asyncio.QueueEmpty:
            return None
    
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
        self._running_count = max(0, self._running_count - 1)
        
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
        task.error = error
        task.completed_at = datetime.now()
        self._running_count = max(0, self._running_count - 1)
        
        if self._on_task_failed:
            self._on_task_failed(task, error)
        emit_event(EventType.TASK_FAILED, {
            "task_id": task_id, "error": error,
        }, source="dispatcher")
        
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
        if prev_state in (TaskState.RUNNING, TaskState.WAITING_POLL):
            self._running_count = max(0, self._running_count - 1)
        
        print(f"[Dispatcher] Cancelled task {task_id} (was {prev_state})")
        emit_event(EventType.QUEUE_UPDATED, {
            "action": "cancel", "task_id": task_id,
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
        
        # Trigger UI refresh so thumbnails update
        if child_ids and self._on_queue_updated:
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
                task.required_account = parent_account  # D2: same account
                
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
            task.progress = min(100, max(0, progress))
            if status_text:
                task.status_text = status_text
            # Notify UI callback if registered
            if hasattr(self, '_on_progress_callback') and self._on_progress_callback:
                self._on_progress_callback(task_id, task.progress, status_text)
    
    def set_progress_callback(self, callback):
        """Register callback for progress updates: callback(task_id, progress, status_text)."""
        self._on_progress_callback = callback
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._all_tasks.get(task_id)
    
    def get_group(self, group_id: str) -> Optional[TaskGroup]:
        """Get task group by ID."""
        return self._task_groups.get(group_id)
    
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
    
    def _enqueue_task(self, task: Task, priority: int = 1):
        """Add task to priority queue.
        
        Args:
            task: Task to enqueue
            priority: 0 = high (retry/requeue), 1 = normal (new task)
        """
        self._queue_counter += 1
        self._ready_queue.put_nowait((priority, self._queue_counter, task))
    
    def set_callbacks(
        self,
        on_ready: Optional[Callable[[Task], None]] = None,
        on_completed: Optional[Callable[[Task], None]] = None,
        on_failed: Optional[Callable[[Task, str], None]] = None,
    ):
        """Set event callbacks."""
        self._on_task_ready = on_ready
        self._on_task_completed = on_completed
        self._on_task_failed = on_failed
    
    def clear_completed(self):
        """Clear completed tasks from tracking."""
        completed_ids = [
            tid for tid, task in self._all_tasks.items()
            if task.state in (TaskState.COMPLETED, TaskState.CANCELLED, TaskState.FAILED)
        ]
        for tid in completed_ids:
            del self._all_tasks[tid]
    
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
    
    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task by resetting state to READY.
        
        If the task is a chain root with failed descendants,
        automatically uses retry_chain() to preserve continuation identity.
        """
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        if task.state not in (TaskState.FAILED, TaskState.CANCELLED):
            return False
        
        # Chain-aware: if this task has failed descendants, use retry_chain
        if self._has_failed_descendants(task_id):
            return self.retry_chain(task_id)
        
        task.state = TaskState.READY
        task.error = None
        task.progress = 0
        task.retry_attempts += 1
        # D2: Pin retry to same account
        # INIT stage: prefer same (project_id reuse), SUBMITTED+: require same (operation_name bound)
        if task.assigned_account:
            task.required_account = task.assigned_account
        # NOTE: task.stage preserved — worker will resume from checkpoint
        self._enqueue_task(task, priority=0)  # Retry = high priority
        # Wake up engine workers waiting for tasks
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
        # D2: Pin retry to same account — project_id is account-bound
        if root.assigned_account:
            root.required_account = root.assigned_account
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
        
        Used by network error handler: task goes back to queue
        and will be picked up after engine resumes.
        """
        if not task:
            return False
        task.state = TaskState.READY
        task.error = None
        # NOTE: Don't increment retry_attempts — this isn't a real failure
        # NOTE: Preserve task.stage — resume from checkpoint after reconnect
        self._enqueue_task(task, priority=0)  # High priority: was already running
        return True
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks. Returns count retried."""
        count = 0
        for task in list(self._all_tasks.values()):
            if task.state == TaskState.FAILED:
                if self.retry_task(task.id):
                    count += 1
        return count
    
    def reset_task(self, task_id: str) -> bool:
        """Reset a task to initial state — delete all cached/downloaded files.
        
        Clears: output files, thumbnails, operation reference, progress.
        Preserves: prompt, config, image_uris, workflow_type.
        Sets state back to READY and re-queues.
        
        Skips: RUNNING tasks (active) and COMPLETED tasks (already done).
        """
        import os
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        # Don't reset a currently running task
        if task.state == TaskState.RUNNING:
            return False
        # Don't reset already completed tasks — preserve finished work
        if task.state == TaskState.COMPLETED:
            return False
        
        # Delete downloaded video files
        for path in list(task.output_uris):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    print(f"[Reset] Deleted output: {path}")
            except Exception as e:
                print(f"[Reset] Could not delete {path}: {e}")
        
        # Delete cached thumbnails
        for path in list(task.thumbnail_paths):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    print(f"[Reset] Deleted thumbnail: {path}")
            except Exception as e:
                print(f"[Reset] Could not delete {path}: {e}")
        
        # Reset runtime state (keep prompt, config, image_uris)
        task.output_uris.clear()
        task.thumbnail_paths.clear()
        task.operation_name = None
        task.operation_names.clear()
        task.scene_ids.clear()
        task.video_outputs.clear()
        task.upscale_status = ""
        task.upscale_error = ""
        task.upscale_media_ids.clear()
        task.stage = TaskStage.INIT  # Reset stage — start from scratch
        task.progress = 0
        task.error = None
        task.started_at = None
        task.completed_at = None
        task.assigned_account = None
        task.required_account = None  # Full reset → any account OK
        
        # Handle continuation tasks: children must WAIT for parent
        if task.parent_task_id:
            parent = self._all_tasks.get(task.parent_task_id)
            parent_done = parent and parent.state == TaskState.COMPLETED if parent else False
            
            if parent_done and parent and parent.output_uris:
                # Parent already completed — child can start immediately
                task.state = TaskState.READY
                self._enqueue_task(task, priority=0)
                if self._on_task_ready:
                    self._on_task_ready(task)
            else:
                # Parent hasn't completed yet — child must wait
                task.continuation_frame_uri = None  # Clear so has_dependency = True
                task.image_uris.clear()
                task.state = TaskState.WAITING
                self._waiting_tasks[task.id] = task
                
                # Re-register dependency mapping
                pid = task.parent_task_id
                if pid not in self._parent_to_children:
                    self._parent_to_children[pid] = []
                if task.id not in self._parent_to_children[pid]:
                    self._parent_to_children[pid].append(task.id)
                
                print(f"[Reset] Task {task.id} is continuation → WAITING for parent {pid}")
        else:
            # Normal task — ready to run
            task.state = TaskState.READY
            self._enqueue_task(task, priority=0)  # Reset = high priority
            if self._on_task_ready:
                self._on_task_ready(task)
        
        return True
    
    def force_retry_task(self, task_id: str) -> bool:
        """Force retry a task regardless of current state (including COMPLETED).
        
        Fully resets the task: clears all outputs, thumbnails, video_outputs,
        upscale state. Re-queues as READY for fresh generation.
        
        Unlike reset_task(), this accepts ANY state including COMPLETED and RUNNING.
        
        Continuation-aware:
        - PARENT retry: resets + re-registers all children as WAITING
        - CHILD retry: preserves frame data + account affinity from parent
        - Protects parent video files that children need for frame extraction
        """
        import os
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        
        # ── Identify continuation children (before deleting outputs) ──
        children_ids = [
            t.id for t in self._all_tasks.values()
            if t.parent_task_id == task_id
        ]
        has_children = bool(children_ids)
        
        # ── Delete downloaded video files ──
        # If this task has children, KEEP video files (children need them
        # for _re_extract_frame_from_parent). They'll be replaced when
        # the retried task completes with new outputs.
        if not has_children:
            for path in list(task.output_uris):
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                        print(f"[ForceRetry] Deleted output: {path}")
                except Exception as e:
                    print(f"[ForceRetry] Could not delete {path}: {e}")
        else:
            print(f"[ForceRetry] Keeping {len(task.output_uris)} output files "
                  f"(needed by {len(children_ids)} children for frame extraction)")
        
        # Delete cached thumbnails (always safe to delete)
        for path in list(task.thumbnail_paths):
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    print(f"[ForceRetry] Deleted thumbnail: {path}")
            except Exception as e:
                print(f"[ForceRetry] Could not delete {path}: {e}")
        
        # Delete per-video files from video_outputs (720p, upscaled, thumbnails)
        # Skip if children exist (they may need parent 720p for frame extraction)
        if not has_children:
            deleted = set(task.output_uris) | set(task.thumbnail_paths)
            for vo in task.video_outputs:
                for vpath in (vo.file_720p, vo.file_upscaled, vo.thumbnail_path):
                    if vpath and vpath not in deleted:
                        try:
                            if os.path.isfile(vpath):
                                os.remove(vpath)
                                print(f"[ForceRetry] Deleted video_output file: {vpath}")
                        except Exception as e:
                            print(f"[ForceRetry] Could not delete {vpath}: {e}")
                        deleted.add(vpath)
        
        # ── Full reset (common to all tasks) ──
        task.output_uris.clear()
        task.thumbnail_paths.clear()
        task.operation_name = None
        task.operation_names.clear()
        task.scene_ids.clear()
        task.video_outputs.clear()
        task.upscale_status = ""
        task.upscale_error = ""
        task.upscale_media_ids.clear()
        task.state = TaskState.READY
        task.stage = TaskStage.INIT
        task.progress = 0
        task.error = None
        task.retry_attempts = 0
        task.started_at = None
        task.completed_at = None
        
        # ── Continuation-aware account handling ──
        if task.parent_task_id:
            # CHILD task: preserve account affinity from parent
            parent = self._all_tasks.get(task.parent_task_id)
            if parent and parent.assigned_account:
                task.required_account = parent.assigned_account
                print(f"[ForceRetry] Child {task_id}: preserving account affinity "
                      f"→ {parent.assigned_account}")
            else:
                # Parent gone or no account — allow any account
                task.assigned_account = None
                task.required_account = None
            # Keep continuation_frame_local_path for re-upload
            # Keep parent_task_id for frame re-extraction fallback
        else:
            # ROOT/standalone task: any account can pick this up
            task.assigned_account = None
            task.required_account = None
        
        # ── PARENT: reset + re-register children ──
        if has_children:
            for child_id in children_ids:
                child = self._all_tasks.get(child_id)
                if not child:
                    continue
                
                # Reset child to WAITING (will be activated when parent completes)
                child.state = TaskState.WAITING
                child.stage = TaskStage.INIT
                child.continuation_frame_uri = None
                child.continuation_frame_local_path = None
                child.image_uris.clear()
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
                child.started_at = None
                child.completed_at = None
                child.assigned_account = None
                child.required_account = None
                
                # Put back in waiting_tasks
                self._waiting_tasks[child_id] = child
                
                print(f"[ForceRetry] Child {child_id} reset to WAITING")
            
            # Re-register parent→children mapping (consumed by previous _resolve_dependencies)
            self._parent_to_children[task_id] = children_ids
            print(f"[ForceRetry] Re-registered {len(children_ids)} children "
                  f"for parent {task_id}")
        
        # Re-queue
        self._enqueue_task(task, priority=0)
        if self._on_task_ready:
            self._on_task_ready(task)
        print(f"[ForceRetry] Task {task_id} reset and re-queued"
              f"{' (+ ' + str(len(children_ids)) + ' children → WAITING)' if has_children else ''}")
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
            for task in group.tasks:
                if task.state not in (TaskState.RUNNING, TaskState.COMPLETED):
                    if self.reset_task(task.id):
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
        # Drain the ready queue
        while not self._ready_queue.empty():
            try:
                self._ready_queue.get_nowait()  # Discard (priority, counter, task)
            except Exception:
                break
        self._running_count = 0  # Reset to 0 since everything is cleared
        print(f"[Dispatcher] Cleared all: {count} tasks removed")
        return count
    
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
                    image_paths=td.get("image_paths", []),
                    parent_task_id=td.get("parent_task_id"),
                    continuation_frame_uri=td.get("continuation_frame_uri"),
                    continuation_frame_local_path=resolved_frame,
                    required_account=td.get("required_account"),
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
                # Restore timestamps
                for ts_field in ("created_at", "completed_at"):
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
        
        print(f"[Dispatcher] Restored {count} tasks from {len(groups_data)} groups")
        return count
