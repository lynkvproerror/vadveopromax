"""
VEO Pro Max - Account Manager (CHỦ)

Reference: ACCOUNT_SESSION_MANAGEMENT.md
Role: Manages individual account session, token refresh, slot semaphore

Architecture: Asyncio (Hybrid with ProcessPoolExecutor for CPU tasks)
"""

from typing import Optional, Callable
from datetime import datetime, timedelta
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession, SubscriptionType, PaygateTier
from config.constants import TokenLifetime


class AccountManager:
    """CHỦ - Manages a single VEO account session.
    
    Responsibilities:
    - Session management (email, access_token, recaptcha)
    - 4-slot semaphore with acquire_slot() / release_slot()
    - Token refresh coordination
    - Project management integration
    """
    
    MAX_SLOTS = 4
    
    def __init__(self, session: AccountSession):
        self._session = session
        self._slot_semaphore = asyncio.Semaphore(self.MAX_SLOTS)
        self._lock = asyncio.Lock()
        
        # Callbacks for token refresh
        self._on_token_refresh_needed: Optional[Callable] = None
        self._on_recaptcha_refresh_needed: Optional[Callable] = None
        
        # Project cache
        self._project_id: Optional[str] = None
    
    @property
    def session(self) -> AccountSession:
        """Get the account session."""
        return self._session
    
    @property
    def email(self) -> str:
        """Get account email."""
        return self._session.email
    
    @property
    def is_ready(self) -> bool:
        """Check if account is ready for API calls."""
        return self._session.is_ready
    
    @property
    def available_slots(self) -> int:
        """Get number of available slots."""
        return self._session.available_slots
    
    @property
    def active_slots(self) -> int:
        """Get number of active slots."""
        return self._session.active_slots
    
    @property
    def project_id(self) -> Optional[str]:
        """Get cached project ID."""
        return self._project_id
    
    def set_project_id(self, project_id: str):
        """Set project ID for this account."""
        self._project_id = project_id
    
    def acquire_slot(self, timeout: Optional[float] = None) -> bool:
        """Attempt to acquire a slot (non-blocking check).
        
        For async semaphore, use non-blocking try_acquire pattern.
        In async context, use 'async with self._slot_semaphore' instead.
        
        Returns:
            True if slot acquired, False otherwise.
        """
        # Quick check without blocking
        acquired = self._slot_semaphore._value > 0
        if acquired:
            # Decrement semaphore
            self._slot_semaphore._value -= 1
            self._session.active_slots += 1
            self._session.last_activity = datetime.now()
        
        return acquired
    
    def release_slot(self):
        """Release a slot."""
        if self._session.active_slots > 0:
            self._session.active_slots -= 1
            self._slot_semaphore.release()
    
    def get_access_token(self) -> Optional[str]:
        """Get valid access token.
        
        Returns None if token is expired.
        Triggers refresh callback if token expiring soon.
        """
        if self._session.is_token_expired:
            # Token expired, trigger refresh
            if self._on_token_refresh_needed:
                self._on_token_refresh_needed(self)
            return None
        
        # Check if nearing expiration (5 min before)
        buffer_check = timedelta(minutes=5)
        if datetime.now() >= (self._session.token_expires - buffer_check):
            # Trigger background refresh
            if self._on_token_refresh_needed:
                self._on_token_refresh_needed(self)
        
        return self._session.access_token
    
    def get_recaptcha_token(self) -> Optional[str]:
        """Get valid reCAPTCHA token.
        
        Returns None if token needs refresh.
        Triggers refresh callback if needed.
        """
        if self._session.needs_recaptcha_refresh:
            if self._on_recaptcha_refresh_needed:
                self._on_recaptcha_refresh_needed(self)
            return None
        
        return self._session.recaptcha_token
    
    def update_access_token(self, token: str, expires_in: int = TokenLifetime.ACCESS_TOKEN):
        """Update access token.
        
        Args:
            token: New access token.
            expires_in: Token lifetime in seconds.
        """
        with self._lock:
            self._session.access_token = token
            self._session.token_expires = datetime.now() + timedelta(seconds=expires_in)
    
    def update_recaptcha_token(self, token: str):
        """Update reCAPTCHA token."""
        with self._lock:
            self._session.update_recaptcha(token)
    
    def update_from_api_response(self, response: dict):
        """Update account info from API response."""
        with self._lock:
            self._session.update_from_api_response(response)
    
    def set_token_refresh_callback(self, callback: Callable):
        """Set callback for when token refresh is needed."""
        self._on_token_refresh_needed = callback
    
    def set_recaptcha_refresh_callback(self, callback: Callable):
        """Set callback for when reCAPTCHA refresh is needed."""
        self._on_recaptcha_refresh_needed = callback
    
    def get_headers(self) -> Optional[dict]:
        """Get HTTP headers for API requests.
        
        Returns None if tokens not available.
        """
        access_token = self.get_access_token()
        recaptcha_token = self.get_recaptcha_token()
        
        if not access_token or not recaptcha_token:
            return None
        
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-recaptcha-token": recaptcha_token,
        }
    
    def get_status(self) -> dict:
        """Get account status summary."""
        return {
            "email": self.email,
            "sku": self._session.sku.value,
            "paygate_tier": self._session.paygate_tier.value,
            "credits": self._session.credits,
            "slots": f"{self.active_slots}/{self.MAX_SLOTS}",
            "token_expired": self._session.is_token_expired,
            "needs_recaptcha": self._session.needs_recaptcha_refresh,
            "recaptcha_age": f"{self._session.recaptcha_age:.0f}s",
            "project_id": self._project_id,
            "is_ready": self.is_ready,
        }
