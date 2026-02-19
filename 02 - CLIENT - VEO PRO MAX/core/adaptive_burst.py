"""
VEO Pro Max - Adaptive Burst Controller

Dynamic anti-detect delay that adjusts based on server responses.
Tightens delay after consecutive successes, backs off on 403s.

Replaces fixed random.uniform(3, 8) delays with intelligent pacing.

Architecture ref: ENGINE_PIPELINE_ARCHITECTURE.md §11 — Component 4B
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Dict, Optional

log = logging.getLogger(__name__)


class AdaptiveBurstController:
    """Dynamic per-account delay controller for API request pacing.
    
    Algorithm:
    - Start at middle-ground delay (5.0s)
    - After 10 consecutive successes → decrease delay by 20% (min 2.0s)
    - On 403 error → increase delay by 50% (max 15.0s)
    - On 429 (rate limit) → increase delay by 100% (max 30.0s)
    - On 500+ (server error) → small increase by 25%
    - All waits include ±30% jitter for anti-fingerprinting
    
    Per-account: each account has its own delay state.
    """
    
    DEFAULT_DELAY = 5.0
    MIN_DELAY = 2.0
    MAX_DELAY = 15.0
    MAX_DELAY_429 = 30.0
    SUCCESS_THRESHOLD = 10  # Consecutive successes before tightening
    
    def __init__(
        self,
        min_delay: float = MIN_DELAY,
        max_delay: float = MAX_DELAY,
        initial_delay: float = DEFAULT_DELAY,
    ):
        self._min = min_delay
        self._max = max_delay
        self._initial = initial_delay
        
        # Per-account state
        self._delays: Dict[str, float] = {}           # email → current delay
        self._streaks: Dict[str, int] = {}             # email → consecutive successes
        self._total_403: Dict[str, int] = {}           # email → total 403 count
        self._last_adjustment: Dict[str, datetime] = {}
    
    def _get_delay(self, email: str) -> float:
        """Get current delay for account (lazy init)."""
        if email not in self._delays:
            self._delays[email] = self._initial
            self._streaks[email] = 0
            self._total_403[email] = 0
        return self._delays[email]
    
    def record_success(self, email: str):
        """Record a successful API call — may tighten delay."""
        delay = self._get_delay(email)
        self._streaks[email] = self._streaks.get(email, 0) + 1
        
        if self._streaks[email] >= self.SUCCESS_THRESHOLD:
            old = delay
            new = max(self._min, delay * 0.8)  # Decrease by 20%
            self._delays[email] = new
            self._streaks[email] = 0  # Reset streak
            self._last_adjustment[email] = datetime.now()
            
            if abs(old - new) > 0.1:
                log.debug(
                    f"[AdaptiveBurst] {email}: tightened {old:.1f}s → {new:.1f}s "
                    f"(after {self.SUCCESS_THRESHOLD} successes)"
                )
    
    def record_error(self, email: str, status_code: int = 403):
        """Record an error — backs off delay."""
        delay = self._get_delay(email)
        self._streaks[email] = 0  # Reset streak
        
        old = delay
        if status_code == 429:
            # Rate limited — aggressive backoff
            new = min(self.MAX_DELAY_429, delay * 2.0)
        elif status_code == 403:
            # Forbidden — moderate backoff
            new = min(self._max, delay * 1.5)
            self._total_403[email] = self._total_403.get(email, 0) + 1
        elif status_code >= 500:
            # Server error — mild backoff
            new = min(self._max, delay * 1.25)
        else:
            # Other error — small backoff
            new = min(self._max, delay * 1.1)
        
        self._delays[email] = new
        self._last_adjustment[email] = datetime.now()
        
        log.info(
            f"[AdaptiveBurst] {email}: backed off {old:.1f}s → {new:.1f}s "
            f"(HTTP {status_code})"
        )
    
    async def wait(self, email: str):
        """Wait the adaptive delay with jitter for an account.
        
        Call this before each API request to pace requests.
        """
        delay = self._get_delay(email)
        jitter = random.uniform(-delay * 0.3, delay * 0.3)
        actual_wait = max(self._min * 0.5, delay + jitter)
        
        log.debug(f"[AdaptiveBurst] {email}: waiting {actual_wait:.1f}s (base={delay:.1f}s)")
        await asyncio.sleep(actual_wait)
    
    def get_delay(self, email: str) -> float:
        """Get current delay value for monitoring."""
        return self._get_delay(email)
    
    def reset(self, email: str):
        """Reset account to initial delay."""
        self._delays[email] = self._initial
        self._streaks[email] = 0
        self._last_adjustment[email] = datetime.now()
    
    def get_stats(self) -> dict:
        """Return stats for all accounts."""
        return {
            "accounts": {
                email: {
                    "delay": round(self._delays.get(email, self._initial), 1),
                    "streak": self._streaks.get(email, 0),
                    "total_403": self._total_403.get(email, 0),
                }
                for email in self._delays
            },
            "global_avg_delay": round(
                sum(self._delays.values()) / max(1, len(self._delays)), 1
            ),
        }
