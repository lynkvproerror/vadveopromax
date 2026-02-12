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
        if self.upscale_status == "failed":
            return "red"
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
    extract_point_ms: int = 750  # Milliseconds before video end for frame extraction
    required_account: Optional[str] = None  # D2: Force child to same account as parent
    
    # Output quality — "720p" (no upscale), "1080p", "4K"
    download_quality: str = "720p"
    output_folder: str = ""  # Sidebar output folder for downloads
    project_name: str = ""   # Sidebar project name for subfolder
    prompt_index: int = 0    # Global position in batch (0-based) for sequential naming
    
    # State
    state: TaskState = TaskState.PENDING
    progress: int = 0              # 0-100
    error: Optional[str] = None
    retry_attempts: int = 0        # Track retries for UI display
    
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
        self._ready_queue: asyncio.Queue[Task] = asyncio.Queue()
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
            self._ready_queue.put_nowait(existing)
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
            self._ready_queue.put_nowait(task)
            
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
            self._ready_queue.put_nowait(task)
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
            task = self._ready_queue.get_nowait()
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
        continuation_frame_uri: Optional[str] = None
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
            self._resolve_dependencies(task_id, continuation_frame_uri)
        
        if self._on_task_completed:
            self._on_task_completed(task)
    
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
        
        # C1: Cascade-fail children waiting on this parent
        if task_id in self._parent_to_children:
            child_ids = self._parent_to_children.pop(task_id)
            for child_id in child_ids:
                child = self._waiting_tasks.pop(child_id, None)
                if child:
                    child.state = TaskState.FAILED
                    child.error = f"Parent task failed: {error}"
                    child.completed_at = datetime.now()
                    if self._on_task_failed:
                        self._on_task_failed(child, child.error)
    
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
        return True
    
    def has_children(self, task_id: str) -> bool:
        """Check if a task has pending continuation children."""
        return task_id in self._parent_to_children and bool(self._parent_to_children[task_id])
    
    def _resolve_dependencies(self, parent_id: str, frame_uri: Optional[str]):
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
                task.image_uris = [frame_uri]
                task.required_account = parent_account  # D2: same account
                
                # Move to ready queue
                task.state = TaskState.READY
                self._ready_queue.put_nowait(task)
                
                if self._on_task_ready:
                    self._on_task_ready(task)
            else:
                # C2: Frame extraction failed — fail child
                task.state = TaskState.FAILED
                task.error = "Continuation frame extraction failed (FFmpeg unavailable or download error)"
                task.completed_at = datetime.now()
                if self._on_task_failed:
                    self._on_task_failed(task, task.error)
    
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
        """Retry a failed task by resetting state to READY."""
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        if task.state not in (TaskState.FAILED, TaskState.CANCELLED):
            return False
        
        task.state = TaskState.READY
        task.error = None
        task.progress = 0
        task.retry_attempts += 1
        self._ready_queue.put_nowait(task)
        # Wake up engine workers waiting for tasks
        if self._on_task_ready:
            self._on_task_ready(task)
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
        task.state = TaskState.READY
        task.progress = 0
        task.error = None
        task.started_at = None
        task.completed_at = None
        task.assigned_account = None
        
        # Re-queue
        self._ready_queue.put_nowait(task)
        # Wake up engine workers waiting for tasks
        if self._on_task_ready:
            self._on_task_ready(task)
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
                self._ready_queue.get_nowait()
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
                    parent_task_id=td.get("parent_task_id"),
                    extract_point_ms=td.get("extract_point_ms", 750),
                    download_quality=td.get("download_quality", "720p"),
                    state=TaskState(td.get("state", "pending")),
                    progress=td.get("progress", 0),
                    error=td.get("error"),
                    retry_attempts=td.get("retry_attempts", 0),
                    operation_name=td.get("operation_name"),
                    output_uris=td.get("output_uris", []),
                    thumbnail_paths=td.get("thumbnail_paths", []),
                    assigned_account=td.get("assigned_account"),
                    project_id=td.get("project_id"),
                )
                # Restore timestamps
                for ts_field in ("created_at", "completed_at"):
                    ts_val = td.get(ts_field)
                    if ts_val:
                        try:
                            setattr(task, ts_field, datetime.fromisoformat(ts_val))
                        except (ValueError, TypeError):
                            pass
                
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
                    self._ready_queue.put_nowait(task)
                
                count += 1
            
            self._task_groups[group.id] = group
        
        print(f"[Dispatcher] Restored {count} tasks from {len(groups_data)} groups")
        return count
