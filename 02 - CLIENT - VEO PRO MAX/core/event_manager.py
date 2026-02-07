"""
VEO Pro Max - Event Manager

Pub/Sub event system for UI-Core communication.
"""

from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class EventType(str, Enum):
    """Application event types."""
    
    # Task events
    TASK_SUBMITTED = "task_submitted"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    
    # Queue events
    QUEUE_UPDATED = "queue_updated"
    QUEUE_STARTED = "queue_started"
    QUEUE_STOPPED = "queue_stopped"
    QUEUE_CLEARED = "queue_cleared"
    
    # Account events
    ACCOUNT_ADDED = "account_added"
    ACCOUNT_REMOVED = "account_removed"
    ACCOUNT_EXPIRED = "account_expired"
    ACCOUNT_REFRESHED = "account_refreshed"
    
    # Download events
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    
    # UI events
    UI_STATUS_UPDATE = "ui_status_update"
    UI_ERROR = "ui_error"
    UI_NOTIFICATION = "ui_notification"
    
    # Settings events
    SETTINGS_CHANGED = "settings_changed"
    THEME_CHANGED = "theme_changed"
    
    # License events
    LICENSE_VALIDATED = "license_validated"
    LICENSE_EXPIRED = "license_expired"
    TRIAL_WARNING = "trial_warning"


@dataclass
class Event:
    """An application event."""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""


class EventManager:
    """Pub/Sub event manager for application-wide events.
    
    Features:
    - Subscribe to specific event types
    - Publish events to all subscribers
    - Thread-safe event handling
    - Event queue for async processing
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._global_subscribers: List[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        
        # Async event queue
        self._event_queue: queue.Queue[Event] = queue.Queue()
        self._processor_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Event history (limited)
        self._history: List[Event] = []
        self._max_history = 100
    
    def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
    ):
        """Subscribe to a specific event type.
        
        Args:
            event_type: Event type to subscribe to
            callback: Function to call when event occurs
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
    
    def subscribe_all(self, callback: Callable[[Event], None]):
        """Subscribe to all events.
        
        Args:
            callback: Function to call for any event
        """
        with self._lock:
            self._global_subscribers.append(callback)
    
    def unsubscribe(
        self,
        event_type: EventType,
        callback: Callable[[Event], None],
    ):
        """Unsubscribe from an event type.
        
        Args:
            event_type: Event type
            callback: Callback to remove
        """
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass
    
    def unsubscribe_all(self, callback: Callable[[Event], None]):
        """Remove global subscriber."""
        with self._lock:
            try:
                self._global_subscribers.remove(callback)
            except ValueError:
                pass
    
    def publish(self, event: Event):
        """Publish an event immediately.
        
        Calls all subscribers synchronously.
        """
        # Add to history
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)
        
        # Notify subscribers
        callbacks = []
        with self._lock:
            # Type-specific subscribers
            if event.type in self._subscribers:
                callbacks.extend(self._subscribers[event.type])
            # Global subscribers
            callbacks.extend(self._global_subscribers)
        
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                pass  # Don't let one callback break others
    
    def publish_async(self, event: Event):
        """Queue event for async processing.
        
        Event will be processed in background thread.
        """
        self._event_queue.put(event)
    
    def emit(
        self,
        event_type: EventType,
        data: Optional[Dict] = None,
        source: str = "",
    ):
        """Convenience method to create and publish event.
        
        Args:
            event_type: Event type
            data: Event data
            source: Event source identifier
        """
        event = Event(
            type=event_type,
            data=data or {},
            source=source,
        )
        self.publish(event)
    
    def emit_async(
        self,
        event_type: EventType,
        data: Optional[Dict] = None,
        source: str = "",
    ):
        """Convenience method to queue event."""
        event = Event(
            type=event_type,
            data=data or {},
            source=source,
        )
        self.publish_async(event)
    
    def start_processor(self):
        """Start background event processor."""
        if self._processor_thread and self._processor_thread.is_alive():
            return
        
        self._running = True
        self._processor_thread = threading.Thread(
            target=self._process_loop,
            daemon=True,
        )
        self._processor_thread.start()
    
    def stop_processor(self):
        """Stop background event processor."""
        self._running = False
        # Put sentinel to unblock queue
        self._event_queue.put(Event(type=EventType.UI_STATUS_UPDATE))
    
    def _process_loop(self):
        """Background event processing loop."""
        while self._running:
            try:
                event = self._event_queue.get(timeout=1.0)
                self.publish(event)
            except queue.Empty:
                continue
    
    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 50,
    ) -> List[Event]:
        """Get event history.
        
        Args:
            event_type: Filter by type (None for all)
            limit: Max events to return
        """
        with self._lock:
            if event_type:
                filtered = [e for e in self._history if e.type == event_type]
            else:
                filtered = self._history.copy()
        
        return filtered[-limit:]
    
    def clear_history(self):
        """Clear event history."""
        with self._lock:
            self._history.clear()


# Global event manager instance
_event_manager: Optional[EventManager] = None


def get_event_manager() -> EventManager:
    """Get global event manager instance."""
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
    return _event_manager


def emit_event(
    event_type: EventType,
    data: Optional[Dict] = None,
    source: str = "",
):
    """Convenience function to emit event."""
    get_event_manager().emit(event_type, data, source)
