"""
VEO Pro Max - StatusAggregator

Realtime metrics dashboard from EventManager subscriptions.
Tracks throughput, error rates, bottlenecks, and active tasks.

Architecture ref: ENGINE_PIPELINE_ARCHITECTURE.md §11 — Component 2C
"""

import logging
from collections import deque
from datetime import datetime
from typing import Dict, Optional

from core.event_manager import get_event_manager, EventType, Event

log = logging.getLogger(__name__)


class StatusAggregator:
    """Realtime pipeline metrics from EventManager events.
    
    Subscribes to task lifecycle events and computes:
    - Active task count + per-account breakdown
    - Completion/failure totals
    - Avg completion time (rolling window)
    - Throughput (prompts/hour)
    - Error type distribution
    - Bottleneck detection (stuck tasks, high error rate)
    """
    
    def __init__(self):
        # ─── Counters ─────────────────────────────────
        self._completed_count = 0
        self._failed_count = 0
        self._watchdog_recoveries = 0
        
        # ─── Active Tasks ────────────────────────────
        self._active_tasks: Dict[str, dict] = {}  # task_id → {account, started_at, stage}
        
        # ─── Rolling Windows (last 100) ──────────────
        self._completion_times: deque = deque(maxlen=100)  # seconds
        self._error_history: deque = deque(maxlen=100)     # {time, error, reason}
        
        # ─── Per-Account Stats ────────────────────────
        self._account_stats: Dict[str, dict] = {}  # email → {completed, failed, active}
        
        # ─── Timestamps ──────────────────────────────
        self._start_time = datetime.now()
        self._running = False
    
    def start(self):
        """Subscribe to EventManager events."""
        em = get_event_manager()
        em.subscribe(EventType.TASK_STARTED, self._on_task_started)
        em.subscribe(EventType.TASK_COMPLETED, self._on_task_completed)
        em.subscribe(EventType.TASK_FAILED, self._on_task_failed)
        em.subscribe(EventType.TASK_PROGRESS, self._on_task_progress)
        em.subscribe(EventType.ENGINE_ERROR, self._on_engine_error)
        self._running = True
        log.info("[StatusAggregator] Started — tracking pipeline metrics")
    
    def stop(self):
        """Stop tracking."""
        self._running = False
    
    # ─── Event Handlers ───────────────────────────────────────────
    
    def _on_task_started(self, event: Event):
        data = event.data or {}
        task_id = data.get("task_id", "")
        account = data.get("account", "unknown")
        
        self._active_tasks[task_id] = {
            "account": account,
            "started_at": datetime.now(),
            "stage": "started",
        }
        
        # Per-account tracking
        if account not in self._account_stats:
            self._account_stats[account] = {"completed": 0, "failed": 0, "active": 0}
        self._account_stats[account]["active"] += 1
    
    def _on_task_completed(self, event: Event):
        data = event.data or {}
        task_id = data.get("task_id", "")
        
        self._completed_count += 1
        
        # Calculate completion time
        if task_id in self._active_tasks:
            started = self._active_tasks[task_id]["started_at"]
            elapsed = (datetime.now() - started).total_seconds()
            self._completion_times.append(elapsed)
            
            account = self._active_tasks[task_id].get("account", "unknown")
            if account in self._account_stats:
                self._account_stats[account]["completed"] += 1
                self._account_stats[account]["active"] = max(0, self._account_stats[account]["active"] - 1)
            
            del self._active_tasks[task_id]
    
    def _on_task_failed(self, event: Event):
        data = event.data or {}
        task_id = data.get("task_id", "")
        error = data.get("error", "unknown")
        reason = data.get("reason", "unknown")
        
        self._failed_count += 1
        self._error_history.append({
            "time": datetime.now().isoformat(),
            "error": error[:100],
            "reason": reason,
        })
        
        if task_id in self._active_tasks:
            account = self._active_tasks[task_id].get("account", "unknown")
            if account in self._account_stats:
                self._account_stats[account]["failed"] += 1
                self._account_stats[account]["active"] = max(0, self._account_stats[account]["active"] - 1)
            del self._active_tasks[task_id]
    
    def _on_task_progress(self, event: Event):
        data = event.data or {}
        task_id = data.get("task_id", "")
        stage = data.get("stage", "")
        
        if task_id in self._active_tasks and stage:
            self._active_tasks[task_id]["stage"] = stage
    
    def _on_engine_error(self, event: Event):
        data = event.data or {}
        if data.get("type") == "watchdog_recovery":
            self._watchdog_recoveries += 1
    
    # ─── Dashboard ────────────────────────────────────────────────
    
    def get_dashboard(self) -> dict:
        """Return complete metrics snapshot for UI/DevConsole."""
        uptime = (datetime.now() - self._start_time).total_seconds()
        
        return {
            "uptime_sec": round(uptime),
            "active_tasks": len(self._active_tasks),
            "completed_total": self._completed_count,
            "failed_total": self._failed_count,
            "watchdog_recoveries": self._watchdog_recoveries,
            "avg_completion_sec": self._avg_completion(),
            "throughput_per_hour": self._throughput(uptime),
            "success_rate": self._success_rate(),
            "error_rate_last_10": self._recent_error_rate(),
            "bottlenecks": self._detect_bottlenecks(),
            "per_account": dict(self._account_stats),
            "recent_errors": list(self._error_history)[-5:],  # Last 5 errors
        }
    
    def get_summary_line(self) -> str:
        """One-line summary for status bar."""
        active = len(self._active_tasks)
        rate = self._throughput((datetime.now() - self._start_time).total_seconds())
        return f"Active: {active} | Done: {self._completed_count} | Failed: {self._failed_count} | {rate:.1f}/hr"
    
    # ─── Internal Metrics ─────────────────────────────────────────
    
    def _avg_completion(self) -> Optional[float]:
        if not self._completion_times:
            return None
        return round(sum(self._completion_times) / len(self._completion_times), 1)
    
    def _throughput(self, uptime_sec: float) -> float:
        if uptime_sec < 60:
            return 0.0
        return round(self._completed_count / (uptime_sec / 3600), 1)
    
    def _success_rate(self) -> Optional[float]:
        total = self._completed_count + self._failed_count
        if total == 0:
            return None
        return round(self._completed_count / total * 100, 1)
    
    def _recent_error_rate(self) -> float:
        """Error rate in last 10 tasks."""
        recent = list(self._completion_times)[-10:] if self._completion_times else []
        recent_errors = list(self._error_history)[-10:] if self._error_history else []
        total = len(recent) + len(recent_errors)
        if total == 0:
            return 0.0
        return round(len(recent_errors) / total * 100, 1)
    
    def _detect_bottlenecks(self) -> list:
        """Auto-detect pipeline bottlenecks."""
        bottlenecks = []
        
        # Check for stuck tasks (active > 15 min)
        now = datetime.now()
        for task_id, info in self._active_tasks.items():
            elapsed = (now - info["started_at"]).total_seconds()
            if elapsed > 900:  # 15 min
                bottlenecks.append({
                    "type": "stuck_task",
                    "task_id": task_id,
                    "elapsed_sec": round(elapsed),
                    "stage": info.get("stage", "unknown"),
                })
        
        # High error rate warning
        if self._completed_count + self._failed_count >= 10:
            rate = self._success_rate()
            if rate is not None and rate < 70:
                bottlenecks.append({
                    "type": "high_error_rate",
                    "success_rate": rate,
                })
        
        # Watchdog recoveries indicate issues
        if self._watchdog_recoveries > 3:
            bottlenecks.append({
                "type": "frequent_watchdog",
                "recoveries": self._watchdog_recoveries,
            })
        
        return bottlenecks
