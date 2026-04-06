"""
VEO Pro Max - TaskWatchdog

Background coroutine that scans for stuck tasks and
recovers them by re-queuing. Prevents slot leaks.

Architecture ref: ENGINE_PIPELINE_ARCHITECTURE.md §11 — Component 1C
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from core.event_manager import emit_event, EventType

if TYPE_CHECKING:
    from core.dispatcher import Dispatcher
    from core.engine import Engine

log = logging.getLogger(__name__)


class TaskWatchdog:
    """Background task stuck-detection and recovery.
    
    Scans all tasks every SCAN_INTERVAL seconds. If a task has been
    in RUNNING or WAITING_POLL longer than its timeout, it is force
    re-queued and the orphaned workers released.
    """
    
    # Timeout thresholds (seconds)
    RUNNING_TIMEOUT = 900       # 15min — T2I serial submit can take 5-7min
    POLL_TIMEOUT = 900          # 15min — poll should not exceed MAX_POLL_TIME
    SCAN_INTERVAL = 30          # Check every 30s
    
    def __init__(self, dispatcher: 'Dispatcher', engine: 'Engine'):
        self._dispatcher = dispatcher
        self._engine = engine
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Stats
        self._recoveries = 0
        self._scans = 0
        self._last_scan_at: Optional[datetime] = None
    
    def start(self):
        """Start the background scan loop."""
        self._running = True
        self._task = asyncio.create_task(self._scan_loop())
        log.info(
            f"[Watchdog] Started — "
            f"RUNNING timeout={self.RUNNING_TIMEOUT}s, "
            f"POLL timeout={self.POLL_TIMEOUT}s, "
            f"scan every {self.SCAN_INTERVAL}s"
        )
    
    async def start_async(self):
        """Async entry point (for use with run_coroutine_threadsafe)."""
        self.start()
    
    def stop(self):
        """Stop the scan loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        log.info(f"[Watchdog] Stopped — total recoveries: {self._recoveries}")
    
    # ─── Scan Loop ────────────────────────────────────────────────
    
    async def _scan_loop(self):
        """Main background loop."""
        from core.dispatcher import TaskState, TaskStage
        
        try:
            while self._running:
                await asyncio.sleep(self.SCAN_INTERVAL)
                
                if not self._running:
                    break
                
                self._scans += 1
                self._last_scan_at = datetime.now()
                now = datetime.now()
                
                stuck_count = 0
                for task in self._dispatcher.get_all_tasks():
                    # Skip tasks managed by UpscaleQueue (background upscale)
                    # These tasks have state=WAITING_POLL but are NOT stuck —
                    # they're actively being processed by UpscaleQueue
                    if getattr(task, 'stage', None) in (TaskStage.UPSCALING, TaskStage.UPSCALED):
                        continue
                    
                    if task.state == TaskState.RUNNING:
                        if self._is_stuck(task, now, self.RUNNING_TIMEOUT):
                            self._recover(task, "RUNNING timeout", self.RUNNING_TIMEOUT)
                            stuck_count += 1
                    elif task.state == TaskState.WAITING_POLL:
                        if self._is_stuck(task, now, self.POLL_TIMEOUT):
                            self._recover(task, "POLL timeout", self.POLL_TIMEOUT)
                            stuck_count += 1
                
                if stuck_count > 0:
                    log.warning(f"[Watchdog] Scan #{self._scans}: recovered {stuck_count} stuck task(s)")
                
                # Counter audit: detect and auto-fix _running_count mismatches
                self._dispatcher.audit_counters()
                
                # Upscale counter audit: detect leaked active_upscale_workers
                multi_acc = getattr(self._engine, '_multi_account', None)
                if multi_acc and hasattr(multi_acc, 'audit_upscale_counters'):
                    # Pass empty set = no inline upscale tasks expected
                    # (if any are truly inline, they'd be caught by RUNNING timeout above)
                    multi_acc.audit_upscale_counters(running_task_ids=set())
                
                # Task pruning: every 20 scans (~10 min) — respects user settings
                if self._scans % 20 == 0:
                    try:
                        from config.settings import get_settings
                        _s = get_settings()
                        _age = getattr(_s, 'prune_age_minutes', 0)
                        _cap = getattr(_s, 'auto_clear_tasks_max', 0)

                        if _age > 0:
                            pruned = self._dispatcher.prune_completed_tasks(max_age_minutes=_age)
                            if pruned:
                                log.info(f"[Watchdog] Pruned {pruned} tasks older than {_age} min")

                        if _cap > 0:
                            capped = self._dispatcher.enforce_task_cap(_cap)
                            if capped:
                                log.info(f"[Watchdog] Enforced task cap ({_cap}): removed {capped} oldest tasks")
                    except Exception as e:
                        log.debug(f"[Watchdog] Prune error: {e}")
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[Watchdog] Scan loop error: {e}")
    
    # ─── Detection ────────────────────────────────────────────────
    
    def _is_stuck(self, task, now: datetime, timeout_sec: float) -> bool:
        """Check if a task has exceeded its timeout."""
        if not task.started_at:
            return False
        
        elapsed = (now - task.started_at).total_seconds()
        return elapsed > timeout_sec
    
    # ─── Recovery ─────────────────────────────────────────────────
    
    def _recover(self, task, reason: str, timeout: float):
        """Force re-queue a stuck task and release its slot."""
        from core.dispatcher import TaskState
        
        elapsed = 0
        if task.started_at:
            elapsed = (datetime.now() - task.started_at).total_seconds()
        
        log.warning(
            f"🐕 [Watchdog] {reason}: task {task.id} "
            f"stuck for {elapsed:.0f}s (limit {timeout}s). "
            f"Account: {task.assigned_account or 'unknown'}. "
            f"Re-queuing."
        )
        
        # ★ BUG-1 FIX: Do NOT set task.state=READY here!
        # requeue_task() checks prev_state to decrement _running_count.
        # If we set READY first, requeue sees prev_state=READY → skip decrement
        # → _running_count drifts permanently.
        # Save assigned_account BEFORE requeue clears it (for worker release below).
        assigned_account = task.assigned_account
        
        # Clear partial results so UI doesn't show stale thumbnails on READY
        task.output_uris = []
        task.thumbnail_paths = []
        task.video_outputs = []
        task.operation_name = None
        
        # Re-queue in dispatcher — handles state transition + counter decrement
        self._dispatcher.requeue_task(task)
        
        # Try to release the orphaned workers
        if assigned_account:
            try:
                account = self._engine.get_account(assigned_account)
                if account:
                    # Release workers proportional to task output_count
                    worker_count = getattr(task, '_worker_count', None) or getattr(task, 'output_count', 1) or 1
                    account.release_workers(worker_count)
                    log.info(f"[Watchdog] Released {worker_count} orphaned worker(s) for {assigned_account}")
            except Exception as e:
                log.debug(f"[Watchdog] Could not release workers for {assigned_account}: {e}")
        
        # Emit event for subscribers (Journal, StatusAggregator)
        emit_event(EventType.ENGINE_ERROR, {
            "type": "watchdog_recovery",
            "task_id": task.id,
            "reason": reason,
            "elapsed_sec": round(elapsed),
            "prev_state": reason,
            "account": assigned_account,
        }, source="watchdog")
        
        self._recoveries += 1
    
    # ─── Status ───────────────────────────────────────────────────
    
    def get_status(self) -> dict:
        """Return watchdog health info for StatusAggregator."""
        return {
            "running": self._running,
            "scans": self._scans,
            "recoveries": self._recoveries,
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "thresholds": {
                "running_timeout": self.RUNNING_TIMEOUT,
                "poll_timeout": self.POLL_TIMEOUT,
                "scan_interval": self.SCAN_INTERVAL,
            },
        }
