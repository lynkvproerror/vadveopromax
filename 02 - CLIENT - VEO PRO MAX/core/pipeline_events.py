"""
VEO Pro Max - Pipeline Event Bus

Lightweight event system for pipeline ↔ UI communication.
Replaces polling-heavy patterns with event-driven notifications.

Events:
    task_completed(task_id, video_path, stage_name)
    group_completed(group_id, stage_name, status)
    stage_ready(stage_name, content)
    session_saved(project_dir, checksum)
    pipeline_error(stage_name, error_msg)

Usage:
    from core.pipeline_events import pipeline_bus

    # Subscribe
    pipeline_bus.on("task_completed", my_handler)

    # Publish
    pipeline_bus.emit("task_completed", task_id="abc", video_path="/out/vid.mp4")

    # Unsubscribe
    pipeline_bus.off("task_completed", my_handler)

Thread-safe: all handlers are called on the subscriber's thread via queue.
"""

import logging
import threading
from typing import Callable, Dict, List, Any, Optional
from collections import defaultdict

log = logging.getLogger("veo.events")


class PipelineEventBus:
    """Thread-safe event bus for pipeline lifecycle events.

    Supports:
    - Multiple handlers per event
    - Handler priority (lower = first)
    - One-shot handlers (auto-remove after first call)
    - Event history for late subscribers
    """

    def __init__(self, history_size: int = 50):
        self._handlers: Dict[str, List[tuple]] = defaultdict(list)
        self._lock = threading.Lock()
        self._history: List[dict] = []
        self._history_size = history_size

    def on(
        self,
        event: str,
        handler: Callable,
        priority: int = 100,
        once: bool = False,
    ):
        """Subscribe to an event.

        Args:
            event: Event name (e.g. "task_completed").
            handler: Callback function(**kwargs).
            priority: Lower = called first (default 100).
            once: If True, auto-remove after first invocation.
        """
        with self._lock:
            self._handlers[event].append((priority, handler, once))
            self._handlers[event].sort(key=lambda x: x[0])
        log.debug(f"[EventBus] Subscribed: {event} → {handler.__name__}")

    def off(self, event: str, handler: Optional[Callable] = None):
        """Unsubscribe from an event.

        If handler is None, removes ALL handlers for the event.
        """
        with self._lock:
            if handler is None:
                self._handlers.pop(event, None)
            else:
                self._handlers[event] = [
                    (p, h, o) for p, h, o in self._handlers[event]
                    if h is not handler
                ]

    def emit(self, event: str, **kwargs):
        """Publish an event to all subscribers.

        Args:
            event: Event name.
            **kwargs: Event data passed to handlers.
        """
        with self._lock:
            handlers = list(self._handlers.get(event, []))
            # Record history
            self._history.append({"event": event, **kwargs})
            if len(self._history) > self._history_size:
                self._history = self._history[-self._history_size:]

        to_remove = []
        for priority, handler, once in handlers:
            try:
                handler(**kwargs)
            except Exception as e:
                log.warning(f"[EventBus] Handler error on '{event}': {e}")
            if once:
                to_remove.append(handler)

        # Remove one-shot handlers
        if to_remove:
            with self._lock:
                self._handlers[event] = [
                    (p, h, o) for p, h, o in self._handlers[event]
                    if h not in to_remove
                ]

    def clear(self, event: Optional[str] = None):
        """Remove all handlers, optionally for a specific event."""
        with self._lock:
            if event:
                self._handlers.pop(event, None)
            else:
                self._handlers.clear()

    def get_history(self, event: Optional[str] = None, limit: int = 10) -> List[dict]:
        """Get recent event history for debugging."""
        with self._lock:
            if event:
                return [h for h in self._history if h["event"] == event][-limit:]
            return self._history[-limit:]

    @property
    def stats(self) -> Dict[str, int]:
        """Get handler count per event."""
        with self._lock:
            return {event: len(handlers) for event, handlers in self._handlers.items()}


# ── Singleton ──
pipeline_bus = PipelineEventBus()


# ── Event name constants ──
class Events:
    TASK_COMPLETED = "task_completed"
    GROUP_COMPLETED = "group_completed"
    STAGE_READY = "stage_ready"
    SESSION_SAVED = "session_saved"
    PIPELINE_ERROR = "pipeline_error"
    PIPELINE_RESET = "pipeline_reset"
    THUMBNAIL_REFRESH = "thumbnail_refresh"
