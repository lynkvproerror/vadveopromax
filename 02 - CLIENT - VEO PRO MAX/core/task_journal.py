"""
VEO Pro Max - TaskJournal

Write-ahead log for crash-safe task persistence.
Subscribes to EventManager stage-change events and periodically
saves a snapshot of the Dispatcher's state to disk.

Architecture ref: ENGINE_PIPELINE_ARCHITECTURE.md §11 — Component 1B
"""

import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from core.event_manager import get_event_manager, EventType, Event

log = logging.getLogger(__name__)


class TaskJournal:
    """Crash-safe task persistence via periodic snapshots.
    
    Subscribes to TASK_STARTED, TASK_COMPLETED, TASK_FAILED, and
    TASK_PROGRESS (stage-change only) events. When any occurs, marks
    state as dirty. A background coroutine saves every `interval_sec`
    seconds if dirty.
    
    Save is atomic: write to .tmp then rename (safe on NTFS).
    """
    
    DEFAULT_INTERVAL = 30.0  # seconds between saves
    
    def __init__(self, dispatcher, save_dir: Path, interval_sec: float = DEFAULT_INTERVAL):
        """
        Args:
            dispatcher: Dispatcher instance (provides export_state / import_state)
            save_dir: Directory for journal file
            interval_sec: Auto-save interval in seconds
        """
        self._dispatcher = dispatcher
        self._save_path = save_dir / "task_journal.json"
        self._interval = interval_sec
        self._dirty = False
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Stats
        self._save_count = 0
        self._last_save_at: Optional[datetime] = None
    
    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Subscribe to events and start periodic save loop.
        
        Args:
            loop: The background async event loop. If provided, schedules
                  the save loop via run_coroutine_threadsafe (for calling
                  from non-async context like Qt main thread).
        """
        em = get_event_manager()
        
        # Stage-change events → mark dirty
        em.subscribe(EventType.TASK_STARTED, self._on_dirty)
        em.subscribe(EventType.TASK_COMPLETED, self._on_dirty)
        em.subscribe(EventType.TASK_FAILED, self._on_dirty)
        em.subscribe(EventType.TASK_PROGRESS, self._on_stage_change)
        
        # Start background save loop
        self._running = True
        self._loop = loop
        if loop and loop.is_running():
            # Called from main thread — schedule on background loop
            asyncio.run_coroutine_threadsafe(self._start_save_loop(), loop)
        else:
            # Called from within async context
            self._task = asyncio.create_task(self._periodic_save_loop())
        log.info(f"[TaskJournal] Started — saving to {self._save_path} every {self._interval}s")
    
    def stop(self):
        """Stop background loop and do a final save."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        
        # Final save on shutdown
        self.save_snapshot()
        log.info(f"[TaskJournal] Stopped — total saves: {self._save_count}")
    
    # ─── Event Handlers ───────────────────────────────────────────
    
    def _on_dirty(self, event: Event):
        """Mark state as dirty (any task lifecycle event)."""
        self._dirty = True
    
    def _on_stage_change(self, event: Event):
        """Only mark dirty for PROGRESS events that contain a stage change."""
        if event.data and event.data.get("stage"):
            self._dirty = True
    
    # ─── Background Save Loop ─────────────────────────────────────
    
    async def _start_save_loop(self):
        """Wrapper to create the task from within the async loop."""
        self._task = asyncio.create_task(self._periodic_save_loop())
    
    async def _periodic_save_loop(self):
        """Background coroutine: save snapshot if dirty."""
        try:
            while self._running:
                await asyncio.sleep(self._interval)
                if self._dirty:
                    self.save_snapshot()
                    self._dirty = False
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[TaskJournal] Save loop error: {e}")
    
    # ─── Save / Load ──────────────────────────────────────────────
    
    def save_snapshot(self):
        """Atomic save: write to .tmp then rename.
        
        Uses Dispatcher.export_state() which returns:
            {"groups": [serialized group dicts], "task_count": int}
        """
        try:
            data = self._dispatcher.export_state()
            data["saved_at"] = datetime.now().isoformat()
            data["save_count"] = self._save_count + 1
            
            # Ensure directory exists
            self._save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write: .tmp → rename
            tmp_path = self._save_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            tmp_path.replace(self._save_path)  # Atomic on NTFS
            
            self._save_count += 1
            self._last_save_at = datetime.now()
            log.debug(
                f"[TaskJournal] Snapshot saved — "
                f"{data.get('task_count', '?')} tasks, "
                f"save #{self._save_count}"
            )
        except Exception as e:
            log.error(f"[TaskJournal] Failed to save snapshot: {e}")
    
    def load_snapshot(self) -> Optional[dict]:
        """Load the most recent snapshot from disk.
        
        Returns:
            Parsed dict (same format as export_state) or None if no file.
        """
        if not self._save_path.exists():
            log.info("[TaskJournal] No journal file found — fresh start")
            return None
        
        try:
            data = json.loads(self._save_path.read_text(encoding="utf-8"))
            saved_at = data.get("saved_at", "unknown")
            task_count = data.get("task_count", 0)
            log.info(
                f"[TaskJournal] Loaded snapshot — "
                f"{task_count} tasks from {saved_at}"
            )
            return data
        except Exception as e:
            log.error(f"[TaskJournal] Failed to load snapshot: {e}")
            return None
    
    def force_save(self):
        """Force an immediate save (called from UI or shutdown)."""
        self.save_snapshot()
        self._dirty = False
    
    # ─── Status ───────────────────────────────────────────────────
    
    def get_status(self) -> dict:
        """Return journal health info for StatusAggregator."""
        return {
            "save_count": self._save_count,
            "last_save_at": self._last_save_at.isoformat() if self._last_save_at else None,
            "dirty": self._dirty,
            "file_exists": self._save_path.exists(),
            "file_size_kb": round(self._save_path.stat().st_size / 1024, 1) if self._save_path.exists() else 0,
        }
