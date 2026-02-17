"""
VEO Pro Max - Session Refresh Manager

Reference: SESSION_06_WORKFLOWS_SECURITY.md, VEO_Web_Client_Protocol_Analysis.md §1.4
Role: Manage browser session refresh flow

IMPORTANT (B2): REST auth uses x-browser-* headers (from browser context),
NOT rotating Bearer tokens. "Refresh" means re-extracting session data from
the live browser, not token rotation. Focus is on:
- Keeping browser context alive for x-browser-* header extraction
- Refreshing reCAPTCHA tokens (expire ~80s)
- Re-extracting session when cookies expire
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
    """A session refresh request (browser session keepalive)."""
    email: str
    reason: str
    requested_at: datetime
    status: RefreshStatus = RefreshStatus.PENDING
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class CookieRefreshManager:
    """Manage browser session refresh operations.
    
    Per Protocol Analysis §1.4: REST endpoints use x-browser-* headers
    (from browser context) for auth — NOT Bearer tokens. "Refresh" means
    re-extracting session data from the live browser.
    
    Features:
    - User-assisted browser re-login flow
    - Auto-refresh check timer (reCAPTCHA expiry + cookie expiry)
    - Refresh queue management per-account
    """
    
    REFRESH_CHECK_INTERVAL = 5 * 60   # 5 minutes
    TOKEN_REFRESH_BUFFER = 5 * 60     # Refresh 5 min before expiry
    
    def __init__(self):
        self._pending_requests: Dict[str, RefreshRequest] = {}
        self._refresh_history: List[RefreshRequest] = []
        
        # Callbacks
        self._on_refresh_needed: Optional[Callable[[str, str], None]] = None
        self._on_refresh_complete: Optional[Callable[[str, bool], None]] = None
        self._show_refresh_dialog: Optional[Callable[[RefreshRequest], bool]] = None
        self._on_auto_relogin: Optional[Callable[[str], Optional[str]]] = None
        
        # Extension bridge ref for auto header refresh
        self._extension_bridge = None
        
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
    
    def set_complete_callback(self, callback: Callable[[str, bool], None]):
        """Set callback when refresh completes. Callback receives (email, success)."""
        self._on_refresh_complete = callback
    
    def set_auto_relogin_callback(self, callback: Callable[[str], Optional[str]]):
        """Set callback for auto re-login when refresh fails.
        
        Callback receives email, returns email if success or None.
        This is typically profiles_controller.auto_relogin().
        """
        self._on_auto_relogin = callback
    
    def set_extension_bridge(self, bridge):
        """Set ExtensionBridge reference for auto header refresh."""
        self._extension_bridge = bridge
    
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
        
        # Auto re-login on failure
        if not success and self._on_auto_relogin:
            print(f"[RefreshManager] 🔑 Refresh failed for {email}, attempting auto re-login...")
            try:
                relogin_result = self._on_auto_relogin(email)
                if relogin_result:
                    print(f"[RefreshManager] ✅ Auto re-login successful for {email}")
                else:
                    print(f"[RefreshManager] ❌ Auto re-login failed for {email}")
            except Exception as e:
                print(f"[RefreshManager] Auto re-login error: {e}")
    
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
        Also triggers extension header refresh for stale headers.
        """
        need_refresh = []
        now = datetime.now()
        
        for email, session in self._sessions.items():
            # Skip already pending
            if email in self._pending_requests:
                continue
            
            # Check token expiry — extension will auto-refresh on next API call
            if session.token_expires:
                time_until_expiry = (session.token_expires - now).total_seconds()
                if time_until_expiry < self.TOKEN_REFRESH_BUFFER:
                    need_refresh.append(email)
                    continue
            
            # reCAPTCHA is on-demand via extension — no proactive refresh needed
        
        # Auto-refresh stale extension headers (Fix #6)
        if self._extension_bridge:
            for email in self._sessions:
                headers = self._extension_bridge.get_cached_headers(email, max_age_seconds=240)
                if headers is None and self._extension_bridge.is_connected(email):
                    # Headers stale (>12 min) — trigger refresh
                    try:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(
                                self._extension_bridge.refresh_headers(email, timeout=10)
                            )
                        else:
                            loop.run_until_complete(
                                self._extension_bridge.refresh_headers(email, timeout=10)
                            )
                    except Exception:
                        pass  # Best-effort
        
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
