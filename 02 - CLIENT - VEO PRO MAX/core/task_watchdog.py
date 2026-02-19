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
    re-queued and the orphaned slot released.
    """
    
    # Timeout thresholds (seconds)
    RUNNING_TIMEOUT = 600       # 10min — task should not stay RUNNING this long
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
        from core.dispatcher import TaskState
        
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
        
        # Reset task state for re-processing
        prev_state = task.state
        task.state = TaskState.READY
        assigned_account = task.assigned_account
        task.assigned_account = None
        task.operation_name = None
        
        # Re-queue in dispatcher
        self._dispatcher.requeue_task(task)
        
        # Try to release the orphaned slot
        if assigned_account:
            try:
                account = self._engine._account_manager.get_account(assigned_account)
                if account:
                    account.release_slot()
                    log.info(f"[Watchdog] Released orphaned slot for {assigned_account}")
            except Exception as e:
                log.debug(f"[Watchdog] Could not release slot for {assigned_account}: {e}")
        
        # Emit event for subscribers (Journal, StatusAggregator)
        emit_event(EventType.ENGINE_ERROR, {
            "type": "watchdog_recovery",
            "task_id": task.id,
            "reason": reason,
            "elapsed_sec": round(elapsed),
            "prev_state": prev_state,
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
