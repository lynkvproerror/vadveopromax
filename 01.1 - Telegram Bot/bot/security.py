"""
Security Module
===============
Whitelist, rate limiting, input validation, audit logging.
"""

import os
import re
import time
import logging
from datetime import datetime
from typing import Optional

log = logging.getLogger("veo.bot.security")


# ─── Admin Whitelist ───────────────────────────────────────────

def get_admin_ids() -> set:
    """Get allowed admin Telegram user IDs from env var."""
    raw = os.environ.get("TELEGRAM_ADMIN_IDS", "").strip()
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def is_admin(user_id: int) -> bool:
    """Check if a Telegram user ID is whitelisted."""
    return user_id in get_admin_ids()


# ─── Multi-Role Access ────────────────────────────────────────

# Cache seller lookup (TTL-based, refreshed on miss)
_seller_cache: dict = {}  # telegram_id → seller_data
_seller_cache_ts: float = 0


def get_user_role(user_id: int, ops=None) -> tuple:
    """Return (role, data) for a Telegram user.
    
    role: 'admin' | 'seller' | 'none'
    data: seller dict if role == 'seller', else {}
    """
    if is_admin(user_id):
        return "admin", {}

    # Check seller cache (refresh every 5 min)
    global _seller_cache, _seller_cache_ts
    now = time.time()
    if now - _seller_cache_ts > 60:
        _seller_cache = {}
        _seller_cache_ts = now

    if user_id in _seller_cache:
        seller = _seller_cache[user_id]
        if seller and seller.get("status", "active") != "disabled":
            return "seller", seller
        return "none", {}

    # Lookup from Firebase
    if ops:
        seller = _find_seller_by_telegram(user_id, ops)
        _seller_cache[user_id] = seller
        if seller and seller.get("status", "active") != "disabled":
            return "seller", seller

    return "none", {}


def _find_seller_by_telegram(telegram_id: int, ops) -> dict:
    """Find seller by their linked Telegram ID."""
    try:
        sellers = ops.list_docs("_sellers", page_size=100)
        for s in sellers:
            if s.get("telegram_id") == telegram_id:
                return s
    except Exception as e:
        log.warning(f"[SEC] Seller lookup error: {e}")
    return {}


def invalidate_seller_cache():
    """Clear seller cache (call after /linkseller)."""
    global _seller_cache, _seller_cache_ts
    _seller_cache = {}
    _seller_cache_ts = 0


# ─── Rate Limiting ─────────────────────────────────────────────

class RateLimiter:
    """Simple sliding-window rate limiter (in-memory)."""

    def __init__(self, max_calls: int = 30, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self._calls: dict = {}  # user_id → [timestamps]

    def check(self, user_id: int) -> bool:
        """Returns True if allowed, False if rate-limited."""
        now = time.time()
        if user_id not in self._calls:
            self._calls[user_id] = []

        # Remove old entries
        self._calls[user_id] = [
            t for t in self._calls[user_id] if now - t < self.window
        ]

        if len(self._calls[user_id]) >= self.max_calls:
            return False

        self._calls[user_id].append(now)
        return True


# Global rate limiter
_rate_limiter = RateLimiter(max_calls=30, window_seconds=60)


def check_rate_limit(user_id: int) -> bool:
    return _rate_limiter.check(user_id)


# ─── Input Validation ─────────────────────────────────────────

# Machine ID: 8-64 hex characters
MID_PATTERN = re.compile(r"^[A-Fa-f0-9]{8,64}$")

# License key: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX (9 segments)
# or legacy 8-segment format
KEY_PATTERN = re.compile(
    r"^[A-Fa-f0-9]{4}(-[A-Fa-f0-9]{4}){7,8}$"
)

# Tier codes
VALID_TIERS = {"TRIA", "1M", "3M", "6M", "1Y", "LT"}


def validate_mid(mid: str) -> Optional[str]:
    """Validate and sanitize Machine ID. Returns cleaned MID or None."""
    mid = mid.strip().upper()
    if MID_PATTERN.match(mid):
        return mid
    return None


def validate_key(key: str) -> Optional[str]:
    """Validate and sanitize license key. Returns cleaned key or None."""
    key = key.strip().upper().replace(" ", "")
    if KEY_PATTERN.match(key):
        return key
    return None


def validate_tier(tier: str) -> Optional[str]:
    """Validate tier code. Returns cleaned tier or None."""
    tier = tier.strip().upper()
    return tier if tier in VALID_TIERS else None


def validate_days(days_str: str) -> Optional[int]:
    """Validate days input. Returns int or None."""
    try:
        days = int(days_str.strip())
        if 1 <= days <= 36500:
            return days
    except (ValueError, TypeError):
        pass
    return None


# ─── Webhook Secret Verification ──────────────────────────────

def verify_webhook_secret(request_path: str) -> bool:
    """Verify webhook URL contains the correct secret path."""
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        log.warning("[SEC] WEBHOOK_SECRET not set!")
        return False
    return secret in request_path


def verify_telegram_secret(headers: dict) -> bool:
    """Verify X-Telegram-Bot-Api-Secret-Token header (case-insensitive)."""
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        log.warning("[SEC] WEBHOOK_SECRET not set — blocking request")
        return False  # Must configure secret
    # Search case-insensitively for the header
    for key, val in headers.items():
        if key.lower() == "x-telegram-bot-api-secret-token":
            return val.strip() == secret
    return False  # Header not found


def verify_cron_secret(headers: dict) -> bool:
    """Verify cron secret via X-Cron-Secret or Vercel's Authorization: Bearer."""
    secret = os.environ.get("CRON_SECRET", "").strip()
    if not secret:
        log.warning("[SEC] CRON_SECRET not set — blocking request")
        return False  # Must configure secret
    
    # Check X-Cron-Secret header (custom, case-insensitive)
    header_val = (
        headers.get("X-Cron-Secret", "")
        or headers.get("x-cron-secret", "")
    ).strip()
    if header_val == secret:
        return True
    
    # Check Authorization: Bearer (Vercel built-in cron sends this)
    auth_val = (
        headers.get("Authorization", "")
        or headers.get("authorization", "")
    ).strip()
    if auth_val.startswith("Bearer ") and auth_val[7:].strip() == secret:
        return True
    
    return False


# ─── Audit Logging ─────────────────────────────────────────────

def build_audit_entry(
    action: str,
    admin_id: int,
    admin_name: str,
    target: str = "",
    detail: str = "",
) -> dict:
    """Build an audit log entry dict."""
    return {
        "action": action,
        "admin_telegram_id": admin_id,
        "admin_name": admin_name,
        "target": target,
        "detail": detail,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
