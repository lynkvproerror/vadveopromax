"""
Account Health — Credit Window for task routing decisions.

Inspired by TCP Congestion Control:
- Each account starts with MAX_CREDITS (10)
- Success → +1 credit
- Failure → -N credits (depends on error severity)
- credits ≤ 0 → account SUSPENDED (no new tasks)
- Passive recovery: +1 credit every PASSIVE_INTERVAL seconds
- When credits > PROBE_THRESHOLD → try probe request
- Probe OK → reactivate with slow start (credit=SLOW_START_CREDITS, cap=1)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

log = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────
MAX_CREDITS = 10
SUSPEND_THRESHOLD = 0
PROBE_THRESHOLD = 1
PASSIVE_INTERVAL = 60         # seconds (1 min) — was 300s, too slow for recovery
SLOW_START_CREDITS = 5


@dataclass
class AccountHealth:
    """Health state for one account."""
    credits: int = MAX_CREDITS
    suspended: bool = False
    suspended_at: float = 0.0
    last_passive_tick: float = 0.0
    probe_ready: bool = False
    slow_start_cap: int = 0      # 0 = no cap (normal mode)
    total_suspensions: int = 0
    
    # Stats for DevConsole
    total_successes: int = 0
    total_errors: int = 0
    last_error_type: str = ""
    last_error_time: float = 0.0
    last_recovery_time: float = 0.0


class CreditWindow:
    """Credit-based account health management.
    
    Thread safety: designed for single asyncio event loop (CPython GIL).
    All callers are coroutines on the same loop — no explicit locking needed.
    """
    
    def __init__(
        self,
        max_credits: int = MAX_CREDITS,
        passive_interval: int = PASSIVE_INTERVAL,
        probe_threshold: int = PROBE_THRESHOLD,
    ):
        self._accounts: Dict[str, AccountHealth] = {}
        self._max_credits = max_credits
        self._passive_interval = passive_interval
        self._probe_threshold = probe_threshold
    
    def _ensure(self, email: str) -> AccountHealth:
        """Get or create AccountHealth for email."""
        if email not in self._accounts:
            self._accounts[email] = AccountHealth(
                credits=self._max_credits,
                last_passive_tick=time.time(),
            )
        return self._accounts[email]
    
    # ── Credit Operations ─────────────────────────────────────
    
    def record_success(self, email: str) -> None:
        """Record successful submit — +1 credit, expand slow start."""
        h = self._ensure(email)
        h.credits = min(h.credits + 1, self._max_credits)
        h.total_successes += 1
        
        # Slow start expansion: double cap on each success
        if h.slow_start_cap > 0:
            h.slow_start_cap = min(h.slow_start_cap * 2, 8)
            if h.credits >= self._max_credits - 2:
                # Graduated to full speed
                h.slow_start_cap = 0
                log.info(
                    f"[CreditWindow] {email}: slow start → full speed "
                    f"(credits={h.credits})"
                )
    
    def record_error(self, email: str, credit_cost: int, error_type: str = "403") -> bool:
        """Record error — deduct credits. Returns True if account got suspended.
        
        Args:
            email: Account email.
            credit_cost: Credits to deduct (from ERROR_CREDIT_COST).
            error_type: Error type for diagnostics ("403", "timeout", etc.)
        
        Returns:
            True if this error caused the account to become suspended.
        """
        h = self._ensure(email)
        
        if h.suspended:
            return False  # Already suspended
        
        h.credits = max(h.credits - credit_cost, -5)  # Floor at -5
        h.total_errors += 1
        h.last_error_type = error_type
        h.last_error_time = time.time()
        
        log.info(
            f"[CreditWindow] {email}: credits {h.credits + credit_cost}→{h.credits} "
            f"(cost={credit_cost}, type={error_type})"
        )
        
        if h.credits <= SUSPEND_THRESHOLD:
            h.suspended = True
            h.suspended_at = time.time()
            h.probe_ready = False
            h.slow_start_cap = 0
            h.total_suspensions += 1
            log.warning(
                f"[CreditWindow] {email}: ⛔ SUSPENDED "
                f"(credits={h.credits}, suspension #{h.total_suspensions})"
            )
            return True
        
        return False
    
    def record_429(self, email: str) -> bool:
        """Record 429 rate-limit — deduct 2 credits (floor=1, NEVER suspend).
        
        Unlike 403 (suspend → probe → reactivate), 429 uses soft penalty:
        credits floor at 1, so account always accepts tasks but pipeline
        slows down via adaptive gap increase.
        
        Returns:
            True if credits are low (≤3) — caller should increase gap.
        """
        h = self._ensure(email)
        old = h.credits
        h.credits = max(h.credits - 2, 1)  # Floor=1 — never suspend
        h.total_errors += 1
        h.last_error_type = "429"
        h.last_error_time = time.time()
        
        log.info(
            f"[CreditWindow] {email}: 429 credits {old}→{h.credits} "
            f"(floor=1, no suspend)"
        )
        
        return h.credits <= 3  # Low health — increase gap
    
    # ── Query ─────────────────────────────────────────────────
    
    def is_suspended(self, email: str) -> bool:
        """Check if account is suspended."""
        h = self._accounts.get(email)
        return h.suspended if h else False
    
    def can_accept_task(self, email: str) -> bool:
        """Check if account can accept a new task.
        
        False if suspended or if slow start cap reached.
        """
        h = self._accounts.get(email)
        if not h:
            return True  # Unknown account = healthy
        if h.suspended:
            return False
        return True
    
    def check_slow_start(self, email: str, current_running: int) -> bool:
        """Check if account is within slow start capacity.
        
        Returns True if account can take more tasks.
        """
        h = self._accounts.get(email)
        if not h or h.slow_start_cap <= 0:
            return True  # No cap
        return current_running < h.slow_start_cap
    
    def get_health(self, email: str) -> Optional[AccountHealth]:
        """Get AccountHealth for DevConsole display."""
        return self._accounts.get(email)
    
    def get_all_health(self) -> Dict[str, AccountHealth]:
        """Get all account health states."""
        return dict(self._accounts)
    
    # ── Passive Recovery ──────────────────────────────────────
    
    def tick(self) -> list:
        """Periodic tick — recover credits for suspended accounts.
        
        Call this every ~60 seconds from a background coroutine.
        
        Also detects accounts suspended too long (>180s) and flags them
        for browser restart to break out of permanent suspension loops.
        
        Returns:
            List of emails that became probe-ready.
        """
        now = time.time()
        probe_ready = []
        
        for email, h in self._accounts.items():
            if not h.suspended:
                continue
            
            suspended_secs = int(now - h.suspended_at)
            
            elapsed = now - h.last_passive_tick
            if elapsed < self._passive_interval:
                continue
            
            # Grant passive credit
            h.credits += 1
            h.last_passive_tick = now
            
            log.info(
                f"[CreditWindow] {email}: passive +1 credit "
                f"(now {h.credits}, suspended {suspended_secs}s ago)"
            )
            
            # Check probe readiness
            if h.credits >= self._probe_threshold and not h.probe_ready:
                h.probe_ready = True
                probe_ready.append(email)
                log.info(
                    f"[CreditWindow] {email}: credits={h.credits} "
                    f"≥ {self._probe_threshold} → PROBE READY"
                )
        
        return probe_ready
    

    
    # ── Reactivation ──────────────────────────────────────────
    
    def reactivate(self, email: str) -> None:
        """Reactivate a suspended account after successful probe."""
        h = self._ensure(email)
        h.suspended = False
        h.probe_ready = False
        h.credits = SLOW_START_CREDITS
        h.slow_start_cap = 1  # Start with 1 task
        h.last_recovery_time = time.time()
        log.info(
            f"[CreditWindow] {email}: ✅ REACTIVATED "
            f"(credits={h.credits}, slow_start_cap=1)"
        )
    
    def probe_failed(self, email: str) -> None:
        """Mark probe as failed — reset credits and wait for next cycle."""
        h = self._ensure(email)
        h.credits = 0
        h.probe_ready = False
        h.last_passive_tick = time.time()  # Reset passive timer
        log.info(
            f"[CreditWindow] {email}: probe failed → credits=0, "
            f"next passive in {self._passive_interval}s"
        )
    
    # ── Diagnostics ───────────────────────────────────────────
    
    def get_dashboard_stats(self) -> dict:
        """Get stats for DevConsole Subsystems card."""
        stats = {
            "enabled": True,
            "accounts": {},
        }
        for email, h in self._accounts.items():
            stats["accounts"][email] = {
                "credits": h.credits,
                "max": self._max_credits,
                "suspended": h.suspended,
                "suspended_duration": (
                    int(time.time() - h.suspended_at) if h.suspended else 0
                ),
                "probe_ready": h.probe_ready,
                "slow_start_cap": h.slow_start_cap,
                "total_suspensions": h.total_suspensions,
                "success_rate": (
                    round(h.total_successes / max(1, h.total_successes + h.total_errors) * 100, 1)
                ),
            }
        return stats
