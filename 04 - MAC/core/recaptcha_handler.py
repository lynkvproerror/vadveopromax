"""
VEO Pro Max - reCAPTCHA Handler

Handles reCAPTCHA detection and user notification.
"""

from typing import Optional, Callable, Dict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
import asyncio
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.event_manager import EventType, emit_event


class RecaptchaState(str, Enum):
    """reCAPTCHA state."""
    NONE = "none"
    DETECTED = "detected"
    WAITING_USER = "waiting_user"
    SOLVED = "solved"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class RecaptchaEvent:
    """A reCAPTCHA event."""
    email: str
    state: RecaptchaState
    timestamp: datetime
    session_id: Optional[str] = None
    message: Optional[str] = None


class RecaptchaHandler:
    """Handle reCAPTCHA detection and user-assisted solving.
    
    Features:
    - Detect reCAPTCHA on page
    - Notify user via UI
    - Wait for user to solve
    - Track solve timeout
    """
    
    # Selectors
    RECAPTCHA_FRAME = 'iframe[src*="recaptcha"]'
    RECAPTCHA_CHECKBOX = '#recaptcha-anchor'
    RECAPTCHA_CHALLENGE = 'iframe[title*="recaptcha challenge"]'
    
    # Timeouts
    SOLVE_TIMEOUT_SEC = 120  # 2 minutes for user to solve
    CHECK_INTERVAL_SEC = 2
    
    def __init__(self):
        self._state = RecaptchaState.NONE
        self._pending_solves: Dict[str, RecaptchaEvent] = {}
        
        # Callbacks
        self._on_recaptcha_detected: Optional[Callable[[str], None]] = None
        self._on_recaptcha_solved: Optional[Callable[[str], None]] = None
        self._on_recaptcha_expired: Optional[Callable[[str], None]] = None
    
    def set_callbacks(
        self,
        on_detected: Optional[Callable[[str], None]] = None,
        on_solved: Optional[Callable[[str], None]] = None,
        on_expired: Optional[Callable[[str], None]] = None,
    ):
        """Set callbacks."""
        self._on_recaptcha_detected = on_detected
        self._on_recaptcha_solved = on_solved
        self._on_recaptcha_expired = on_expired
    
    async def check_for_recaptcha(self, page, email: str) -> bool:
        """Check if reCAPTCHA is present on page.
        
        Args:
            page: Playwright page
            email: Account email
        
        Returns:
            True if reCAPTCHA detected
        """
        try:
            # Check for reCAPTCHA frame
            frame_count = await page.locator(self.RECAPTCHA_FRAME).count()
            
            if frame_count > 0:
                # Check if it's the challenge (not just checkbox)
                challenge_count = await page.locator(self.RECAPTCHA_CHALLENGE).count()
                
                event = RecaptchaEvent(
                    email=email,
                    state=RecaptchaState.DETECTED,
                    timestamp=datetime.now(),
                    message="Challenge" if challenge_count > 0 else "Checkbox",
                )
                
                self._pending_solves[email] = event
                
                if self._on_recaptcha_detected:
                    self._on_recaptcha_detected(email)
                
                emit_event(
                    EventType.UI_NOTIFICATION,
                    {
                        "type": "recaptcha",
                        "email": email,
                        "message": "reCAPTCHA detected - user action required",
                    },
                )
                
                return True
                
        except Exception:
            pass
        
        return False
    
    async def wait_for_solve(
        self,
        page,
        email: str,
        timeout_sec: Optional[int] = None,
    ) -> bool:
        """Wait for user to solve reCAPTCHA.
        
        Args:
            page: Playwright page
            email: Account email
            timeout_sec: Custom timeout
        
        Returns:
            True if solved, False if timeout/failed
        """
        timeout = timeout_sec or self.SOLVE_TIMEOUT_SEC
        elapsed = 0
        
        # Update state
        if email in self._pending_solves:
            self._pending_solves[email].state = RecaptchaState.WAITING_USER
        
        while elapsed < timeout:
            # Check if reCAPTCHA is gone
            if not await self.check_for_recaptcha(page, email):
                # Solved!
                if email in self._pending_solves:
                    self._pending_solves[email].state = RecaptchaState.SOLVED
                    del self._pending_solves[email]
                
                if self._on_recaptcha_solved:
                    self._on_recaptcha_solved(email)
                
                emit_event(
                    EventType.UI_NOTIFICATION,
                    {
                        "type": "recaptcha_solved",
                        "email": email,
                        "message": "reCAPTCHA solved",
                    },
                )
                
                return True
            
            await asyncio.sleep(self.CHECK_INTERVAL_SEC)
            elapsed += self.CHECK_INTERVAL_SEC
        
        # Timeout
        if email in self._pending_solves:
            self._pending_solves[email].state = RecaptchaState.EXPIRED
        
        if self._on_recaptcha_expired:
            self._on_recaptcha_expired(email)
        
        return False
    
    def get_pending_solves(self) -> Dict[str, RecaptchaEvent]:
        """Get all pending reCAPTCHA solves."""
        return dict(self._pending_solves)
    
    def clear_pending(self, email: str):
        """Clear pending solve for email."""
        if email in self._pending_solves:
            del self._pending_solves[email]
    
    def has_pending(self, email: str) -> bool:
        """Check if email has pending reCAPTCHA."""
        return email in self._pending_solves


class TokenExpiryHandler:
    """Handle token expiry detection.
    
    Detects when cookie/token has expired and needs refresh.
    """
    
    # Patterns indicating token expiry
    EXPIRY_PATTERNS = [
        "session has expired",
        "please sign in again",
        "authentication required",
        "login to continue",
        "access denied",
        "unauthorized",
    ]
    
    LOGIN_URL_PATTERNS = [
        "accounts.google.com",
        "accounts.google.com/signin",
        "accounts.google.com/ServiceLogin",
    ]
    
    def __init__(self):
        self._on_token_expired: Optional[Callable[[str], None]] = None
    
    def set_callback(self, on_expired: Optional[Callable[[str], None]] = None):
        """Set expiry callback."""
        self._on_token_expired = on_expired
    
    async def check_expiry(self, page, email: str) -> bool:
        """Check if token/session has expired.
        
        Args:
            page: Playwright page
            email: Account email
        
        Returns:
            True if expired
        """
        try:
            # Check URL for login redirect
            current_url = page.url.lower()
            for pattern in self.LOGIN_URL_PATTERNS:
                if pattern in current_url:
                    if self._on_token_expired:
                        self._on_token_expired(email)
                    
                    emit_event(
                        EventType.ACCOUNT_EXPIRED,
                        {"email": email, "reason": "login_redirect"},
                    )
                    return True
            
            # Check page content for expiry messages
            content = await page.content()
            content_lower = content.lower()
            
            for pattern in self.EXPIRY_PATTERNS:
                if pattern in content_lower:
                    if self._on_token_expired:
                        self._on_token_expired(email)
                    
                    emit_event(
                        EventType.ACCOUNT_EXPIRED,
                        {"email": email, "reason": pattern},
                    )
                    return True
                    
        except Exception:
            pass
        
        return False
