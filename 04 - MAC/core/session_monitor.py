"""
VEO Pro Max - Session Monitor

Reference: SESSION_06_WORKFLOWS_SECURITY.md
Role: Monitor sessions for expiry and errors
"""

from dataclasses import dataclass
from collections import deque
from typing import Optional, Callable, List, Dict
from datetime import datetime, timedelta
from enum import Enum
import threading
import time
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession


class SessionEvent(str, Enum):
    """Session events."""
    TOKEN_EXPIRED = "token_expired"
    RECAPTCHA_EXPIRED = "recaptcha_expired"
    SESSION_ERROR = "session_error"
    RATE_LIMITED = "rate_limited"
    SESSION_RESTORED = "session_restored"


@dataclass
class SessionError:
    """A session error event."""
    email: str
    event: SessionEvent
    message: str
    timestamp: datetime
    raw_error: Optional[str] = None


class SessionMonitor:
    """Monitor sessions for expiry and errors.
    
    Features:
    - Runtime expiry detection
    - Error pattern matching
    - Event callbacks
    """
    
    # Error patterns that indicate session issues
    ERROR_PATTERNS = {
        SessionEvent.TOKEN_EXPIRED: [
            r"401",
            r"unauthorized",
            r"token.*expired",
            r"invalid.*token",
            r"session.*expired",
        ],
        SessionEvent.RECAPTCHA_EXPIRED: [
            r"recaptcha.*expired",
            r"captcha.*invalid",
            r"verification.*failed",
        ],
        SessionEvent.RATE_LIMITED: [
            r"429",
            r"rate.*limit",
            r"too.*many.*requests",
            r"quota.*exceeded",
        ],
    }
    
    def __init__(self):
        self._sessions: Dict[str, AccountSession] = {}
        self._errors: deque = deque(maxlen=500)  # FIFO eviction prevents unbounded growth
        
        # Callbacks
        self._on_session_expired: Optional[Callable[[str, SessionEvent], None]] = None
        self._on_error: Optional[Callable[[SessionError], None]] = None
        
        # Background monitoring
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._check_interval = 30  # seconds
    
    def register_session(self, session: AccountSession):
        """Register a session for monitoring."""
        self._sessions[session.email] = session
    
    def unregister_session(self, email: str):
        """Remove a session from monitoring."""
        if email in self._sessions:
            del self._sessions[email]
    
    def set_expired_callback(self, callback: Callable[[str, SessionEvent], None]):
        """Set callback for session expiry.
        
        Callback receives (email, event_type).
        """
        self._on_session_expired = callback
    
    def set_error_callback(self, callback: Callable[[SessionError], None]):
        """Set callback for errors."""
        self._on_error = callback
    
    def check_session(self, email: str) -> Optional[SessionEvent]:
        """Check if session has issues.
        
        Returns SessionEvent if issue detected, None if OK.
        """
        session = self._sessions.get(email)
        if not session:
            return None
        
        if session.is_token_expired:
            self._trigger_expired(email, SessionEvent.TOKEN_EXPIRED)
            return SessionEvent.TOKEN_EXPIRED
        
        if session.needs_recaptcha_refresh:
            self._trigger_expired(email, SessionEvent.RECAPTCHA_EXPIRED)
            return SessionEvent.RECAPTCHA_EXPIRED
        
        return None
    
    def check_all_sessions(self) -> Dict[str, Optional[SessionEvent]]:
        """Check all registered sessions."""
        return {
            email: self.check_session(email)
            for email in self._sessions
        }
    
    def analyze_error(self, email: str, error: str) -> Optional[SessionEvent]:
        """Analyze an error message to detect session issues.
        
        Args:
            email: Account email
            error: Error message or response
        
        Returns:
            SessionEvent if pattern matched
        """
        error_lower = error.lower()
        
        for event, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_lower):
                    session_error = SessionError(
                        email=email,
                        event=event,
                        message=f"Pattern matched: {pattern}",
                        timestamp=datetime.now(),
                        raw_error=error[:500],
                    )
                    self._errors.append(session_error)
                    
                    if self._on_error:
                        self._on_error(session_error)
                    
                    if event in (SessionEvent.TOKEN_EXPIRED, SessionEvent.RECAPTCHA_EXPIRED):
                        self._trigger_expired(email, event)
                    
                    return event
        
        return None
    
    def _trigger_expired(self, email: str, event: SessionEvent):
        """Trigger expired callback."""
        if self._on_session_expired:
            self._on_session_expired(email, event)
    
    def start_monitoring(self, interval: int = 30):
        """Start background monitoring thread.
        
        Args:
            interval: Check interval in seconds
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        
        self._check_interval = interval
        self._stop_event.clear()
        
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
        )
        self._monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        while not self._stop_event.is_set():
            self.check_all_sessions()
            self._stop_event.wait(self._check_interval)
    
    def get_recent_errors(self, limit: int = 10) -> List[SessionError]:
        """Get recent session errors."""
        return self._errors[-limit:]
    
    def get_session_status(self, email: str) -> Dict:
        """Get status of a specific session."""
        session = self._sessions.get(email)
        if not session:
            return {"exists": False}
        
        return {
            "exists": True,
            "email": email,
            "is_token_expired": session.is_token_expired,
            "needs_recaptcha_refresh": session.needs_recaptcha_refresh,
            "is_ready": session.is_ready,
            "active_workers": session.active_workers,
            "available_workers": session.available_workers,
            # Backward compat
            "active_slots": session.active_workers,
            "available_slots": session.available_workers,
        }
    
    def clear_errors(self):
        """Clear error history."""
        self._errors.clear()
