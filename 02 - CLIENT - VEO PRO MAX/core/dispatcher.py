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
class Task:
    """A single generation task."""
    id: str
    workflow_type: str           # T2V, I2V, R2V, T2I, I2I
    prompt: str
    
    # Configuration
    aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE"
    model: str = "veo_3_1_t2v_fast_landscape_ultra"  # Fixed: proper model key
    output_count: int = 4
    duration_seconds: int = 8
    seed: Optional[int] = None  # Seed for reproducibility (0-32767)
    
    # Image references (for I2V, R2V, I2I)
    image_uris: List[str] = field(default_factory=list)
    
    # Continuation
    parent_task_id: Optional[str] = None
    continuation_frame_uri: Optional[str] = None
    extract_point_ms: int = 750  # Milliseconds before video end for frame extraction
    required_account: Optional[str] = None  # D2: Force child to same account as parent
    
    # Output quality — "720p" (no upscale), "1080p", "4K"
    download_quality: str = "720p"
    
    # State
    state: TaskState = TaskState.PENDING
    progress: int = 0              # 0-100
    error: Optional[str] = None
    retry_attempts: int = 0        # Track retries for UI display
    
    # Results
    operation_name: Optional[str] = None
    output_uris: List[str] = field(default_factory=list)
    
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
        """Cancel a task if not running."""
        task = self._all_tasks.get(task_id)
        if not task:
            return False
        
        if task.state in (TaskState.PENDING, TaskState.WAITING, TaskState.READY):
            task.state = TaskState.CANCELLED
            
            # Remove from waiting queue
            if task_id in self._waiting_tasks:
                del self._waiting_tasks[task_id]
            
            return True
        return False
    
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
    
    def update_progress(self, task_id: str, progress: int):
        """Update task progress."""
        task = self._all_tasks.get(task_id)
        if task:
            task.progress = min(100, max(0, progress))
    
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
        return True
    
    def retry_all_failed(self) -> int:
        """Retry all failed tasks. Returns count retried."""
        count = 0
        for task in list(self._all_tasks.values()):
            if task.state == TaskState.FAILED:
                if self.retry_task(task.id):
                    count += 1
        return count
    
    def clear_all(self) -> int:
        """Clear all non-running tasks. Returns count cleared."""
        removable = [
            tid for tid, task in self._all_tasks.items()
            if task.state not in (TaskState.RUNNING, TaskState.WAITING_POLL)
        ]
        for tid in removable:
            del self._all_tasks[tid]
        return len(removable)
    
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
