"""
VEO Pro Max - Pipeline Queue Bridge

Extracted queue-polling, session persistence, and thumbnail throttling logic
from TabProject. This module provides reusable helpers that TabProject (or
any future orchestrator) can delegate to.

Purpose: Reduce TabProject's responsibility scope from ~6400 lines by
isolating the queue ↔ pipeline interaction layer.

Usage:
    from ui.pipeline_queue_bridge import PipelineQueueBridge
    bridge = PipelineQueueBridge(tab)
    bridge.start_polling(group_id, stage_name)
    bridge.stop_polling()
    bridge.save_session()
"""

import json
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, List, Set

log = logging.getLogger("veo.queue_bridge")


class PipelineQueueBridge:
    """Manages queue polling, session persistence, and thumbnail throttling.

    Decoupled from UI — receives callbacks instead of directly manipulating widgets.
    """

    def __init__(self, controller=None):
        self.controller = controller

        # Poll state
        self._group_id: Optional[str] = None
        self._stage_name: Optional[str] = None
        self._multi_groups: Optional[Dict] = None
        self._prev_completed: int = -1
        self._submitted: bool = False
        self._populated_tasks: Set[str] = set()

        # Throttle state
        self._thumb_last_rebuild: float = 0.0
        self._thumb_deferred: bool = False

        # Persist state
        self._persist_epoch: int = 0
        self._auto_restore_enabled: bool = True

        # Callbacks
        self.on_progress_update = None  # (completed, total, failed) -> None
        self.on_group_complete = None   # (stage_name, status_dict) -> None
        self.on_task_populated = None   # (task_id, video_path) -> None

    def set_controller(self, controller):
        """Update controller reference (hot-swap safe)."""
        self.controller = controller

    # ── Polling ──────────────────────────────────────────────────

    def poll_group_status(self) -> Optional[Dict]:
        """Poll controller for single group status. Returns status dict or None."""
        if not self.controller or not self._group_id:
            return None
        if not hasattr(self.controller, 'get_group_status'):
            return None
        try:
            return self.controller.get_group_status(self._group_id)
        except Exception as e:
            log.debug(f"[QueueBridge] Poll error: {e}")
            return None

    def poll_multi_group_status(self) -> Dict[str, Dict]:
        """Poll controller for multiple group statuses. Returns {group_id: status}."""
        if not self.controller or not self._multi_groups:
            return {}
        results = {}
        for gid in self._multi_groups:
            try:
                status = self.controller.get_group_status(gid)
                if status:
                    results[gid] = status
            except Exception:
                continue
        return results

    def start_polling(self, group_id: str, stage_name: str):
        """Register a group for polling."""
        self._group_id = group_id
        self._stage_name = stage_name
        self._prev_completed = -1
        self._submitted = True
        log.info(f"[QueueBridge] Polling started: {group_id} → {stage_name}")

    def start_multi_polling(self, groups: Dict, stage_name: str):
        """Register multiple groups for polling."""
        self._multi_groups = groups
        self._stage_name = stage_name
        log.info(f"[QueueBridge] Multi-polling started: {len(groups)} groups → {stage_name}")

    def stop_polling(self):
        """Stop all polling."""
        self._group_id = None
        self._multi_groups = None
        self._prev_completed = -1
        self._submitted = False
        self._populated_tasks.clear()
        log.debug("[QueueBridge] Polling stopped")

    def reset(self):
        """Full reset of bridge state."""
        self.stop_polling()
        self._persist_epoch += 1
        self._auto_restore_enabled = False
        self._thumb_last_rebuild = 0.0
        self._thumb_deferred = False

    # ── Thumbnail Throttling ─────────────────────────────────────

    def should_rebuild_thumbnails(self, cooldown_s: float = 5.0) -> bool:
        """Check if enough time has passed since last thumbnail rebuild.

        Returns True if rebuild should proceed, False if throttled.
        """
        now = time.monotonic()
        if now - self._thumb_last_rebuild < cooldown_s:
            self._thumb_deferred = True
            return False
        self._thumb_last_rebuild = now
        self._thumb_deferred = False
        return True

    def has_deferred_rebuild(self) -> bool:
        """Check if a deferred thumbnail rebuild is pending."""
        return self._thumb_deferred

    def mark_rebuild_done(self):
        """Mark that a thumbnail rebuild was completed."""
        self._thumb_last_rebuild = time.monotonic()
        self._thumb_deferred = False

    # ── Session Persistence ──────────────────────────────────────

    def save_session_async(
        self,
        session_data: dict,
        project_dir: str,
        topic_slug: str = "",
    ):
        """Non-blocking session save on background thread.

        Args:
            session_data: Pipeline state dict (from PipelineState.to_session_dict()).
            project_dir: Absolute path to project output directory.
            topic_slug: Sanitized topic name for registry.
        """
        epoch = self._persist_epoch

        def _write():
            if epoch != self._persist_epoch:
                log.debug("[QueueBridge] Async save skipped: stale epoch")
                return
            pdir = Path(project_dir)
            pdir.mkdir(parents=True, exist_ok=True)
            sp = pdir / "_pipeline_session.json"
            try:
                sp.write_text(
                    json.dumps(session_data, ensure_ascii=False, indent=2, default=str),
                    encoding='utf-8',
                )
                log.info(f"[QueueBridge] Session saved (async) → {sp}")
                # Update registry
                try:
                    from core.session_registry import SessionRegistry
                    SessionRegistry().update(str(pdir), topic=topic_slug)
                except Exception:
                    pass
            except Exception as e:
                log.warning(f"[QueueBridge] Async save failed: {e}")

        threading.Thread(target=_write, daemon=True, name="bridge-save").start()

    # ── Task Population Tracking ─────────────────────────────────

    def is_task_populated(self, task_id: str) -> bool:
        """Check if a task's video_path has already been populated."""
        return task_id in self._populated_tasks

    def mark_task_populated(self, task_id: str):
        """Mark a task as having its video_path populated."""
        self._populated_tasks.add(task_id)

    @property
    def persist_epoch(self) -> int:
        return self._persist_epoch

    @property
    def auto_restore_enabled(self) -> bool:
        return self._auto_restore_enabled

    @auto_restore_enabled.setter
    def auto_restore_enabled(self, value: bool):
        self._auto_restore_enabled = value
