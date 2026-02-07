"""
VEO Pro Max - Cookie Refresh Manager

Reference: SESSION_06_WORKFLOWS_SECURITY.md
Role: Manage cookie refresh flow
"""

from dataclasses import dataclass
from typing import Optional, Callable, Dict, List
from datetime import datetime, timedelta
from enum import Enum
import threading
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession


class RefreshStatus(str, Enum):
    """Refresh operation status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    USER_CANCELLED = "user_cancelled"


@dataclass
class RefreshRequest:
    """A cookie refresh request."""
    email: str
    reason: str
    requested_at: datetime
    status: RefreshStatus = RefreshStatus.PENDING
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class CookieRefreshManager:
    """Manage cookie refresh operations.
    
    Features:
    - User-assisted refresh flow
    - Auto-refresh check timer
    - Refresh queue management
    """
    
    REFRESH_CHECK_INTERVAL = 30 * 60  # 30 minutes
    TOKEN_REFRESH_BUFFER = 5 * 60     # Refresh 5 min before expiry
    
    def __init__(self):
        self._pending_requests: Dict[str, RefreshRequest] = {}
        self._refresh_history: List[RefreshRequest] = []
        
        # Callbacks
        self._on_refresh_needed: Optional[Callable[[str, str], None]] = None
        self._on_refresh_complete: Optional[Callable[[str, bool], None]] = None
        self._show_refresh_dialog: Optional[Callable[[RefreshRequest], bool]] = None
        
        # Timer
        self._timer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._sessions: Dict[str, AccountSession] = {}
    
    def register_session(self, session: AccountSession):
        """Register session for refresh monitoring."""
        self._sessions[session.email] = session
    
    def unregister_session(self, email: str):
        """Remove session from monitoring."""
        if email in self._sessions:
            del self._sessions[email]
    
    def set_refresh_callback(self, callback: Callable[[str, str], None]):
        """Set callback when refresh is needed.
        
        Callback receives (email, reason).
        """
        self._on_refresh_needed = callback
    
    def set_dialog_callback(self, callback: Callable[[RefreshRequest], bool]):
        """Set callback to show refresh dialog.
        
        Callback should return True if user completed refresh.
        """
        self._show_refresh_dialog = callback
    
    def request_refresh(self, email: str, reason: str) -> RefreshRequest:
        """Request a cookie refresh.
        
        Args:
            email: Account requiring refresh
            reason: Why refresh is needed
        
        Returns:
            RefreshRequest object
        """
        request = RefreshRequest(
            email=email,
            reason=reason,
            requested_at=datetime.now(),
        )
        
        self._pending_requests[email] = request
        
        # Notify callback
        if self._on_refresh_needed:
            self._on_refresh_needed(email, reason)
        
        return request
    
    def start_refresh(self, email: str) -> bool:
        """Start the refresh process for an account.
        
        Returns True if started successfully.
        """
        request = self._pending_requests.get(email)
        if not request:
            return False
        
        request.status = RefreshStatus.IN_PROGRESS
        
        # Show dialog if callback set
        if self._show_refresh_dialog:
            success = self._show_refresh_dialog(request)
            if success:
                self.complete_refresh(email, True)
            else:
                self.complete_refresh(email, False, "User cancelled")
            return success
        
        return True
    
    def complete_refresh(
        self,
        email: str,
        success: bool,
        error: Optional[str] = None,
        new_session: Optional[AccountSession] = None,
    ):
        """Mark refresh as complete.
        
        Args:
            email: Account email
            success: Whether refresh succeeded
            error: Error message if failed
            new_session: Updated session if successful
        """
        request = self._pending_requests.get(email)
        if not request:
            return
        
        request.status = RefreshStatus.COMPLETED if success else RefreshStatus.FAILED
        request.completed_at = datetime.now()
        request.error = error
        
        # Update session if provided
        if success and new_session:
            self._sessions[email] = new_session
        
        # Move to history
        del self._pending_requests[email]
        self._refresh_history.append(request)
        
        # Notify
        if self._on_refresh_complete:
            self._on_refresh_complete(email, success)
    
    def cancel_refresh(self, email: str):
        """Cancel a pending refresh request."""
        request = self._pending_requests.get(email)
        if request:
            request.status = RefreshStatus.USER_CANCELLED
            request.completed_at = datetime.now()
            del self._pending_requests[email]
            self._refresh_history.append(request)
    
    def check_sessions_need_refresh(self) -> List[str]:
        """Check which sessions need refresh.
        
        Returns list of emails needing refresh.
        """
        need_refresh = []
        now = datetime.now()
        
        for email, session in self._sessions.items():
            # Skip already pending
            if email in self._pending_requests:
                continue
            
            # Check token expiry
            if session.token_expires:
                time_until_expiry = (session.token_expires - now).total_seconds()
                if time_until_expiry < self.TOKEN_REFRESH_BUFFER:
                    self.request_refresh(email, "Token expiring soon")
                    need_refresh.append(email)
                    continue
            
            # Check reCAPTCHA
            if session.needs_recaptcha_refresh:
                self.request_refresh(email, "reCAPTCHA expired")
                need_refresh.append(email)
        
        return need_refresh
    
    def start_auto_check(self, interval: Optional[int] = None):
        """Start auto-refresh check timer.
        
        Args:
            interval: Check interval in seconds (default 30 min)
        """
        if self._timer_thread and self._timer_thread.is_alive():
            return
        
        check_interval = interval or self.REFRESH_CHECK_INTERVAL
        self._stop_event.clear()
        
        self._timer_thread = threading.Thread(
            target=self._auto_check_loop,
            args=(check_interval,),
            daemon=True,
        )
        self._timer_thread.start()
    
    def stop_auto_check(self):
        """Stop auto-refresh check timer."""
        self._stop_event.set()
        if self._timer_thread:
            self._timer_thread.join(timeout=5)
    
    def _auto_check_loop(self, interval: int):
        """Background auto-check loop."""
        while not self._stop_event.is_set():
            self.check_sessions_need_refresh()
            self._stop_event.wait(interval)
    
    def get_pending_requests(self) -> List[RefreshRequest]:
        """Get all pending refresh requests."""
        return list(self._pending_requests.values())
    
    def get_history(self, limit: int = 50) -> List[RefreshRequest]:
        """Get refresh history."""
        return self._refresh_history[-limit:]
    
    def has_pending(self, email: str) -> bool:
        """Check if account has pending refresh."""
        return email in self._pending_requests
