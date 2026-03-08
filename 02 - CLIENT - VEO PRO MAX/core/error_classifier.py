"""
Error Classifier — Categorize task failures for targeted recovery.

Maps error messages and context into ErrorType enum values.
Used by remedy_registry.py to select the correct recovery chain.
"""

from enum import Enum
from typing import Optional


class ErrorType(Enum):
    """Categorized error types for recovery routing."""
    RECAPTCHA_403 = "recaptcha_403"
    RECAPTCHA_TIMEOUT = "recaptcha_timeout"
    TOKEN_TOO_SHORT = "token_too_short"
    TAB_FROZEN = "tab_frozen"
    XCD_STUCK = "xcd_stuck_short"
    AUTH_EXPIRED = "auth_expired"
    NETWORK_ERROR = "network_error"
    POLICY_VIOLATION = "policy_violation"
    UNKNOWN = "unknown"


# Credit cost per error type (higher = more severe)
ERROR_CREDIT_COST = {
    ErrorType.RECAPTCHA_403: 3,
    ErrorType.RECAPTCHA_TIMEOUT: 2,
    ErrorType.TOKEN_TOO_SHORT: 2,
    ErrorType.TAB_FROZEN: 2,
    ErrorType.XCD_STUCK: 2,
    ErrorType.AUTH_EXPIRED: 1,
    ErrorType.NETWORK_ERROR: 0,  # Network errors don't penalize account
    ErrorType.POLICY_VIOLATION: 0,  # Prompt issue, not account health
    ErrorType.UNKNOWN: 1,
}


def classify_error(
    error_msg: str,
    context: Optional[dict] = None,
) -> ErrorType:
    """Classify an error message into an ErrorType.
    
    Args:
        error_msg: Raw error string from WorkerResult or exception.
        context: Optional dict with extra signals:
            - token_len (int): reCAPTCHA token length
            - tab_state (str): "frozen", "alive", etc.
            - xcd_len (int): x-client-data header length
    
    Returns:
        ErrorType enum value for remedy lookup.
    """
    ctx = context or {}
    lower = (error_msg or "").lower()
    
    # ── Policy violations (prompt blocked — not account issue) ──
    policy_signals = (
        "policy", "blocked", "safety", "harmful", "responsible ai",
        "violat", "inappropri", "offensive", "filtered",
        "unsafe", "sexual", "public_error_unsafe", "public_error_sexual",
    )
    if any(s in lower for s in policy_signals) and "403" not in (error_msg or ""):
        return ErrorType.POLICY_VIOLATION
    
    # ── Network errors (highest priority — don't penalize account) ──
    network_signals = (
        "network", "connection", "dns", "econnreset", "econnrefused",
        "etimedout", "fetch failed", "net::", "err_connection",
    )
    if any(s in lower for s in network_signals):
        return ErrorType.NETWORK_ERROR
    
    # ── Auth errors ──
    if any(s in lower for s in ("access token expired", "refresh failed", "401", "unauthenticated")):
        return ErrorType.AUTH_EXPIRED
    
    # ── Tab frozen/dead ──
    if "tab" in lower and any(s in lower for s in ("frozen", "dead", "unresponsive", "crashed")):
        return ErrorType.TAB_FROZEN
    if ctx.get("tab_state") == "frozen":
        return ErrorType.TAB_FROZEN
    
    # ── x-client-data stuck short ──
    xcd_len = ctx.get("xcd_len", 9999)
    if "x-client-data" in lower and ("8 chars" in lower or "short" in lower):
        return ErrorType.XCD_STUCK
    if xcd_len < 20:
        return ErrorType.XCD_STUCK
    
    # ── Token too short ──
    token_len = ctx.get("token_len", 9999)
    if "token too short" in lower or "token" in lower and "short" in lower:
        return ErrorType.TOKEN_TOO_SHORT
    if 0 < token_len < 1000:
        return ErrorType.TOKEN_TOO_SHORT
    
    # ── reCAPTCHA 403 (most common) ──
    is_recaptcha = "recaptcha" in lower
    is_403 = "403" in (error_msg or "")
    if is_recaptcha and is_403:
        return ErrorType.RECAPTCHA_403
    if is_recaptcha and "timeout" in lower:
        return ErrorType.RECAPTCHA_TIMEOUT
    if is_403:
        return ErrorType.RECAPTCHA_403
    if is_recaptcha:
        return ErrorType.RECAPTCHA_TIMEOUT
    
    return ErrorType.UNKNOWN
