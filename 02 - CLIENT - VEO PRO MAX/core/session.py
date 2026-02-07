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
    
    # === Internal State ===
    is_connected: bool = False
    active_slots: int = 0
    max_slots: int = 4
    last_activity: Optional[datetime] = None
    
    def __post_init__(self):
        """Initialize computed fields."""
        if self.recaptcha_fetched_at is None:
            self.recaptcha_fetched_at = datetime.min
    
    @property
    def is_token_expired(self) -> bool:
        """Check if access token is expired (with 60s buffer)."""
        buffer = timedelta(seconds=60)
        return datetime.now() >= (self.token_expires - buffer)
    
    @property
    def needs_recaptcha_refresh(self) -> bool:
        """Check if reCAPTCHA token needs refresh (80s threshold)."""
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
    def available_slots(self) -> int:
        """Get number of available slots."""
        return max(0, self.max_slots - self.active_slots)
    
    @property
    def is_ready(self) -> bool:
        """Check if account is ready for API calls."""
        return (
            not self.is_token_expired
            and not self.needs_recaptcha_refresh
            and self.available_slots > 0
        )
    
    def acquire_slot(self) -> bool:
        """Attempt to acquire a slot. Returns True if successful."""
        if self.active_slots >= self.max_slots:
            return False
        self.active_slots += 1
        self.last_activity = datetime.now()
        return True
    
    def release_slot(self):
        """Release a slot."""
        if self.active_slots > 0:
            self.active_slots -= 1
    
    def update_recaptcha(self, token: str):
        """Update reCAPTCHA token."""
        self.recaptcha_token = token
        self.recaptcha_fetched_at = datetime.now()
    
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
        """Convert to dictionary for serialization."""
        return {
            "email": self.email,
            "access_token": self.access_token,
            "token_expires": self.token_expires.isoformat(),
            "sku": self.sku.value,
            "paygate_tier": self.paygate_tier.value,
            "credits": self.credits,
            "recaptcha_token": self.recaptcha_token,
            "recaptcha_fetched_at": self.recaptcha_fetched_at.isoformat() if self.recaptcha_fetched_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AccountSession":
        """Create from dictionary."""
        return cls(
            email=data["email"],
            access_token=data["access_token"],
            token_expires=datetime.fromisoformat(data["token_expires"]),
            sku=SubscriptionType(data.get("sku", "UNKNOWN")),
            paygate_tier=PaygateTier(data.get("paygate_tier", "UNKNOWN")),
            credits=data.get("credits", 0),
            recaptcha_token=data.get("recaptcha_token", ""),
            recaptcha_fetched_at=datetime.fromisoformat(data["recaptcha_fetched_at"]) if data.get("recaptcha_fetched_at") else None,
        )
