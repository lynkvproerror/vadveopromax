"""
VEO Pro Max - reCAPTCHA Token Pool

Pre-fetches reCAPTCHA tokens in the background so workers don't block
waiting for browser-based token refresh during submit/upscale.

Token TTL is ~90s, so we maintain a small pool per account and
refill proactively.

Architecture ref: ENGINE_PIPELINE_ARCHITECTURE.md §11 — Component 4A
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Callable, Awaitable

log = logging.getLogger(__name__)


@dataclass
class CachedToken:
    """A pre-fetched reCAPTCHA token with expiry tracking."""
    value: str
    fetched_at: datetime = field(default_factory=datetime.now)
    
    def is_fresh(self, ttl_sec: float = 85.0) -> bool:
        """Check if token is still usable (within TTL)."""
        age = (datetime.now() - self.fetched_at).total_seconds()
        return age < ttl_sec


class RecaptchaPool:
    """Pre-fetch reCAPTCHA tokens in background for zero-wait submit.
    
    Each account maintains a small pool (default 2 tokens).
    Background refill loop checks every 5s and tops up expired/used tokens.
    
    Usage:
        token = await pool.get_token("user@email.com")
        # Returns pre-fetched token instantly, or falls back to direct request
    """
    
    POOL_SIZE = 2           # Max ready tokens per account
    REFILL_INTERVAL = 5.0   # Seconds between refill checks
    TOKEN_TTL = 85.0        # Use within 85s (actual TTL ~90s)
    
    def __init__(self):
        self._pools: Dict[str, deque] = {}  # email → deque[CachedToken]
        self._fetchers: Dict[str, Callable[[str], Awaitable[Optional[str]]]] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._should_skip_fn: Optional[Callable[[str], bool]] = None  # email → skip refill?
        
        # Stats
        self._hits = 0      # Served from pool
        self._misses = 0    # Fell back to direct fetch
        self._prefetched = 0
        self._skipped_refills = 0  # Skipped due to cooldown/circuit
    
    def register_account(
        self,
        email: str,
        fetch_fn: Callable[[str], Awaitable[Optional[str]]],
    ):
        """Register an account with its token fetch function.
        
        Args:
            email: Account email
            fetch_fn: Async function that takes email and returns a reCAPTCHA token.
                     This is typically account.refresh_recaptcha().
        """
        if email not in self._pools:
            self._pools[email] = deque(maxlen=self.POOL_SIZE)
        self._fetchers[email] = fetch_fn
    
    def set_skip_check(self, fn: Callable[[str], bool]):
        """Set a function to check if refill should be skipped.
        
        Args:
            fn: Function that takes email and returns True if refill
                should be skipped (e.g., account on cooldown or circuit OPEN).
        """
        self._should_skip_fn = fn
    
    def unregister_account(self, email: str):
        """Remove account from pool."""
        self._pools.pop(email, None)
        self._fetchers.pop(email, None)
    
    def inject_token(self, email: str, token: str):
        """Fix E: Inject an externally-obtained token into the pool.
        
        Used by readiness check callback to cache trial-execute tokens
        so workers don't need an extra round-trip to the extension.
        
        Args:
            email: Account email.
            token: reCAPTCHA token string (must be >500 chars to be useful).
        """
        if not token or len(token) < 500:
            return  # Reject garbage tokens
        pool = self._pools.get(email)
        if pool is None:
            return  # Account not registered
        # Don't exceed pool size — drop oldest if full
        if len(pool) >= self.POOL_SIZE:
            pool.popleft()
        pool.append(CachedToken(value=token))
        self._prefetched += 1
        log.debug(
            f"[RecaptchaPool] Injected readiness token for {email} "
            f"(pool={len(pool)}/{self.POOL_SIZE})"
        )
    
    def start(self):
        """Start background refill loop."""
        self._running = True
        self._task = asyncio.create_task(self._refill_loop())
        log.info(
            f"[RecaptchaPool] Started — pool_size={self.POOL_SIZE}, "
            f"ttl={self.TOKEN_TTL}s, refill_interval={self.REFILL_INTERVAL}s"
        )
    
    def stop(self):
        """Stop background refill."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        log.info(
            f"[RecaptchaPool] Stopped — "
            f"hits={self._hits}, misses={self._misses}, prefetched={self._prefetched}"
        )
    
    async def get_token(self, email: str) -> Optional[str]:
        """Get a reCAPTCHA token for the given account.
        
        1. Try to pop a fresh token from the pool (instant)
        2. If none available, fall back to direct fetch (blocking)
        
        Returns:
            reCAPTCHA token string, or None if all methods failed.
        """
        # Try pool first
        if email in self._pools:
            pool = self._pools[email]
            while pool:
                token = pool.popleft()
                if token.is_fresh(self.TOKEN_TTL):
                    self._hits += 1
                    log.debug(f"[RecaptchaPool] HIT for {email} (pool={len(pool)} remaining)")
                    return token.value
                # Token expired, discard and try next
            
        # Pool empty or all expired → direct fetch
        self._misses += 1
        log.debug(f"[RecaptchaPool] MISS for {email} — direct fetch")
        
        if email in self._fetchers:
            try:
                return await self._fetchers[email](email)
            except Exception as e:
                log.error(f"[RecaptchaPool] Direct fetch failed for {email}: {e}")
                return None
        
        return None
    
    async def priority_prefetch(self, email: str, count: int = 2) -> int:
        """Layer 3: Immediately prefetch tokens for continuation priority.
        
        Called when parent task completes and child needs token soon.
        Bypasses the normal refill interval (5s) for instant refill.
        Includes quality gate: rejects tokens < 1000 chars.
        
        Args:
            email: Account email to prefetch for.
            count: Number of tokens to prefetch.
            
        Returns:
            Number of tokens successfully prefetched.
        """
        if email not in self._fetchers:
            return 0
        
        pool = self._pools.setdefault(email, deque(maxlen=self.POOL_SIZE))
        fetched = 0
        
        for _ in range(count):
            try:
                token_value = await self._fetchers[email](email)
                if token_value and len(token_value) > 1000:  # Quality gate
                    pool.append(CachedToken(value=token_value))
                    fetched += 1
                    self._prefetched += 1
                    log.info(
                        f"[RecaptchaPool] Priority prefetch for {email} "
                        f"({fetched}/{count}, {len(token_value)} chars)"
                    )
                else:
                    log.debug(
                        f"[RecaptchaPool] Priority prefetch got bad token "
                        f"for {email}: {len(token_value) if token_value else 0} chars"
                    )
                    break  # Don't retry if quality is bad
            except Exception as e:
                log.debug(f"[RecaptchaPool] Priority prefetch failed for {email}: {e}")
                break
            
            # Brief pause between fetches to avoid browser contention
            await asyncio.sleep(1.0)
        
        return fetched
    
    async def _refill_loop(self):
        """Background: keep pools topped up with fresh tokens."""
        while self._running:
            try:
                await asyncio.sleep(self.REFILL_INTERVAL)
                
                for email in list(self._fetchers.keys()):
                    if not self._running:
                        break
                    
                    # Skip refill if account is on cooldown or circuit OPEN
                    if self._should_skip_fn and self._should_skip_fn(email):
                        self._skipped_refills += 1
                        continue
                    
                    pool = self._pools.get(email, deque(maxlen=self.POOL_SIZE))
                    
                    # Remove expired tokens
                    while pool and not pool[0].is_fresh(self.TOKEN_TTL):
                        pool.popleft()
                    
                    # Refill if below capacity
                    while len(pool) < self.POOL_SIZE:
                        try:
                            token_value = await self._fetchers[email](email)
                            if token_value:
                                pool.append(CachedToken(value=token_value))
                                self._prefetched += 1
                                log.debug(
                                    f"[RecaptchaPool] Prefetched for {email} "
                                    f"(pool={len(pool)}/{self.POOL_SIZE})"
                                )
                            else:
                                break  # Fetch failed, don't retry immediately
                        except Exception as e:
                            log.debug(f"[RecaptchaPool] Prefetch failed for {email}: {e}")
                            break
                        
                        # Small delay between fetches to avoid browser contention
                        await asyncio.sleep(1.0)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"[RecaptchaPool] Refill loop error: {e}")
                await asyncio.sleep(10)
    
    def get_stats(self) -> dict:
        """Return pool stats for monitoring."""
        pool_sizes = {
            email: len(pool) for email, pool in self._pools.items()
        }
        return {
            "hits": self._hits,
            "misses": self._misses,
            "prefetched": self._prefetched,
            "hit_rate": round(self._hits / max(1, self._hits + self._misses) * 100, 1),
            "pool_sizes": pool_sizes,
        }
