"""
VEO Pro Max - Account Session Data Class

Reference: ACCOUNT_SESSION_MANAGEMENT.md
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import TokenLifetime


class AccountState(str, Enum):
    """Account connection state machine.
    
    Reference: MULTITHREADING_ARCHITECTURE.md §5.2
    Flow: DISCONNECTED → CONNECTING → CONNECTED → READY → ACTIVE
    """
    DISCONNECTED = "disconnected"   # No session
    CONNECTING = "connecting"       # Loading browser context
    CONNECTED = "connected"         # Has session, no project yet
    READY = "ready"                 # Has session + project, can accept tasks
    ACTIVE = "active"               # Processing tasks


class SubscriptionType(str, Enum):
    """Google AI Studio subscription types (SKU)."""
    WS_ULTRA = "WS_ULTRA"           # Highest tier
    WS_PRO = "WS_PRO"               # Pro tier
    WS_FREEMIUM = "WS_FREEMIUM"     # Free tier
    UNKNOWN = "UNKNOWN"


class PaygateTier(str, Enum):
    """Payment gate tiers (from F12 HAR: userPaygateTier)."""
    PAYGATE_TIER_TWO = "PAYGATE_TIER_TWO"       # Premium (Ultra)
    PAYGATE_TIER_ONE = "PAYGATE_TIER_ONE"       # Standard (Pro)
    PAYGATE_TIER_NOT_PAID = "PAYGATE_TIER_NOT_PAID"  # Free
    TIER_ADVANCED = "TIER_ADVANCED"             # Advanced tier
    UNKNOWN = "UNKNOWN"


@dataclass
class AccountSession:
    """Session data for a VEO account.
    
    Contains:
    - Auth data from __NEXT_DATA__
    - SKU/tier info from API response
    - reCAPTCHA token from browser
    """
    
    # === From __NEXT_DATA__ ===
    email: str
    access_token: str
    token_expires: datetime
    
    # === From API Response (SKU Detection) ===
    sku: SubscriptionType = SubscriptionType.UNKNOWN
    paygate_tier: PaygateTier = PaygateTier.UNKNOWN
    credits: int = 0
    
    # === From Browser ===
    recaptcha_token: str = ""
    recaptcha_fetched_at: Optional[datetime] = None
    
    # === x-browser-* Headers (per-account, from browser context) ===
    # Per Protocol Analysis §1.4: these are MANDATORY for REST endpoints
    browser_validation: str = ""    # x-browser-validation header
    client_data: str = ""           # x-client-data header
    browser_channel: str = "stable" # x-browser-channel header
    browser_copyright: str = ""     # x-browser-copyright header
    browser_year: str = ""          # x-browser-year header
    
    # === Authorization (SAPISIDHASH) ===
    _sapisidhash: str = ""            # SAPISIDHASH authorization header (from extension)
    
    # === Internal State ===
    state: AccountState = AccountState.DISCONNECTED
    active_workers: int = 0     # Number of THỢ (videos) currently processing
    max_workers: int = 20       # Max concurrent THỢ (1 THỢ = 1 video)
    last_activity: Optional[datetime] = None
    
    # === Per-Account Worker Settings ===
    retry_count: int = 3       # Max retries on non-auth errors
    request_timeout: int = 120  # Seconds before API call times out
    
    # === Browser Profile ===
    profile_path: str = ""  # Chrome profile directory for persistent browser
    
    def __post_init__(self):
        """Initialize computed fields."""
        if self.recaptcha_fetched_at is None:
            self.recaptcha_fetched_at = datetime.min
    
    @property
    def is_token_expired(self) -> bool:
        """Check if access token is expired (with 60s buffer)."""
        if self.token_expires is None:
            return True  # No expiry set → treat as expired
        buffer = timedelta(seconds=60)
        return datetime.now() >= (self.token_expires - buffer)
    
    @property
    def needs_recaptcha_refresh(self) -> bool:
        """Check if reCAPTCHA token needs refresh.
        
        Safety net: Tokens are normally invalidated immediately after each
        API call (single-use). This 80s threshold catches edge cases where
        invalidate() was missed (e.g., exception paths, code changes).
        """
        if not self.recaptcha_token or self.recaptcha_fetched_at == datetime.min:
            return True
        
        age = (datetime.now() - self.recaptcha_fetched_at).total_seconds()
        return age >= TokenLifetime.RECAPTCHA_REFRESH
    
    @property
    def recaptcha_age(self) -> float:
        """Get age of reCAPTCHA token in seconds."""
        if self.recaptcha_fetched_at == datetime.min:
            return float("inf")
        return (datetime.now() - self.recaptcha_fetched_at).total_seconds()
    
    @property
    def available_workers(self) -> int:
        """Get number of available workers (THỢ = videos)."""
        return max(0, self.max_workers - self.active_workers)
    
    # --- Deprecated slot properties (backward compat) ---
    @property
    def available_slots(self) -> int:
        """DEPRECATED: Use available_workers instead."""
        return self.available_workers
    
    @property
    def active_slots(self) -> int:
        """DEPRECATED: Use active_workers instead."""
        return self.active_workers
    
    @active_slots.setter
    def active_slots(self, value: int):
        """DEPRECATED setter: routes to active_workers."""
        self.active_workers = value
    
    @property
    def max_slots(self) -> int:
        """DEPRECATED: Use max_workers instead."""
        return self.max_workers
    
    @max_slots.setter
    def max_slots(self, value: int):
        """DEPRECATED setter: routes to max_workers."""
        self.max_workers = value
    
    @property
    def is_connected(self) -> bool:
        """Backwards-compatible check (deprecated, use state instead)."""
        return self.state not in (AccountState.DISCONNECTED, AccountState.CONNECTING)
    
    @property
    def is_ready(self) -> bool:
        """Check if account is ready for API calls."""
        return (
            not self.is_token_expired
            and not self.needs_recaptcha_refresh
            and self.available_workers > 0
            # Note: browser_validation is desirable but NOT required for is_ready.
            # Missing headers will cause 403, handled by retry logic.
        )
    
    def acquire_workers(self, n: int = 1) -> bool:
        """Acquire n workers atomically. Returns False if insufficient capacity.
        
        Args:
            n: Number of workers (THỢ/videos) to acquire.
        """
        if self.active_workers + n > self.max_workers:
            return False
        self.active_workers += n
        self.last_activity = datetime.now()
        return True
    
    def release_workers(self, n: int = 1):
        """Release n workers."""
        self.active_workers = max(0, self.active_workers - n)
    
    # --- Deprecated slot methods (backward compat wrappers) ---
    def acquire_slot(self) -> bool:
        """DEPRECATED: Use acquire_workers(n) instead."""
        return self.acquire_workers(1)
    
    def release_slot(self):
        """DEPRECATED: Use release_workers(n) instead."""
        self.release_workers(1)
    
    def update_recaptcha(self, token: str):
        """Update reCAPTCHA token."""
        self.recaptcha_token = token
        self.recaptcha_fetched_at = datetime.now()
    
    def update_browser_headers(
        self,
        browser_validation: str,
        client_data: str,
        browser_channel: str = "stable",
        browser_copyright: str = "",
        browser_year: str = "",
    ):
        """Update x-browser-* headers for this account.
        
        Per Protocol Analysis §1.4: these are extracted from
        each account's browser context and are MANDATORY for REST endpoints.
        
        Guard: x-client-data is generated by Chrome's Variations Service.
        After a browser restart, the service hasn't loaded yet, producing
        a minimal value (e.g. 'CN3nygE=' ~10 chars) instead of the full
        value (~50+ chars). We preserve the existing good value to prevent
        reCAPTCHA 403 errors caused by truncated headers.
        """
        self.browser_validation = browser_validation
        
        # Guard: don't downgrade x-client-data to a shorter/stale value
        MIN_GOOD_LENGTH = 20  # Full x-client-data is typically 50+ chars
        existing = self.client_data or ""
        new_val = client_data or ""
        if len(existing) >= MIN_GOOD_LENGTH and len(new_val) < MIN_GOOD_LENGTH:
            import logging
            logging.getLogger("veo").warning(
                f"x-client-data downgrade blocked: "
                f"keeping existing ({len(existing)} chars), "
                f"rejected new ({len(new_val)} chars: {new_val!r})"
            )
        else:
            self.client_data = client_data
        
        self.browser_channel = browser_channel
        self.browser_copyright = browser_copyright
        self.browser_year = browser_year
    
    def get_browser_headers(self) -> dict:
        """Get all x-browser-* headers for API calls."""
        headers = {
            "x-browser-channel": self.browser_channel,
            "x-browser-validation": self.browser_validation,
            "x-client-data": self.client_data,
        }
        if self.browser_copyright:
            headers["x-browser-copyright"] = self.browser_copyright
        if self.browser_year:
            headers["x-browser-year"] = self.browser_year
        return headers
    
    def update_from_api_response(self, response: dict):
        """Update SKU/tier info from API response.
        
        Example response:
        {
            "subscriptionType": "WS_PRO",
            "paygateTier": "TIER_3",
            "credits": 500
        }
        """
        if "subscriptionType" in response:
            try:
                self.sku = SubscriptionType(response["subscriptionType"])
            except ValueError:
                self.sku = SubscriptionType.UNKNOWN
        
        if "paygateTier" in response:
            try:
                self.paygate_tier = PaygateTier(response["paygateTier"])
            except ValueError:
                self.paygate_tier = PaygateTier.UNKNOWN
        
        if "credits" in response:
            self.credits = int(response["credits"])
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization.
        
        Persists x-browser-* headers so account can be recovered
        without re-extracting from browser.
        """
        return {
            "email": self.email,
            "access_token": self.access_token,
            "token_expires": self.token_expires.isoformat(),
            "sku": self.sku.value,
            "paygate_tier": self.paygate_tier.value,
            "credits": self.credits,
            "recaptcha_token": self.recaptcha_token,
            "recaptcha_fetched_at": self.recaptcha_fetched_at.isoformat() if self.recaptcha_fetched_at else None,
            # x-browser-* headers (B3+B4: per-account, persisted)
            "browser_validation": self.browser_validation,
            "client_data": self.client_data,
            "browser_channel": self.browser_channel,
            "browser_copyright": self.browser_copyright,
            "browser_year": self.browser_year,
            # Account state
            "state": self.state.value,
            # Per-account worker settings
            "max_workers": self.max_workers,
            "retry_count": self.retry_count,
            "request_timeout": self.request_timeout,
            # Browser profile
            "profile_path": self.profile_path,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AccountSession":
        """Create from dictionary."""
        session = cls(
            email=data["email"],
            access_token=data["access_token"],
            token_expires=datetime.fromisoformat(data["token_expires"]),
            sku=SubscriptionType(data.get("sku", "UNKNOWN")),
            paygate_tier=PaygateTier(data.get("paygate_tier", "UNKNOWN")),
            credits=data.get("credits", 0),
            recaptcha_token=data.get("recaptcha_token", ""),
            recaptcha_fetched_at=datetime.fromisoformat(data["recaptcha_fetched_at"]) if data.get("recaptcha_fetched_at") else None,
            # Restore browser headers
            browser_validation=data.get("browser_validation", ""),
            client_data=data.get("client_data", ""),
            browser_channel=data.get("browser_channel", "stable"),
            browser_copyright=data.get("browser_copyright", ""),
            browser_year=data.get("browser_year", ""),
            # Restore profile path
            profile_path=data.get("profile_path", ""),
        )
        # Restore account state
        state_val = data.get("state")
        if state_val:
            try:
                session.state = AccountState(state_val)
            except ValueError:
                session.state = AccountState.DISCONNECTED
        # Restore per-account worker settings (with migration)
        if "max_workers" in data:
            session.max_workers = data["max_workers"]
        elif "max_slots" in data:
            # Migration: old profiles had max_slots=5 → convert to max_workers=20
            session.max_workers = data["max_slots"] * 4
        else:
            session.max_workers = 20
        # Bug #10 fix: Always reset active_workers on load (crash recovery)
        session.active_workers = 0
        session.retry_count = data.get("retry_count", 3)
        session.request_timeout = data.get("request_timeout", 120)
        return session
