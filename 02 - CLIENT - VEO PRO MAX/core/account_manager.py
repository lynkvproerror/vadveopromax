"""
VEO Pro Max - Account Manager (CHỦ)

Reference: ACCOUNT_SESSION_MANAGEMENT.md, MULTITHREADING_ARCHITECTURE.md
Role: Manages individual account session, token refresh, slot semaphore,
      persistent browser session, and reCAPTCHA token cache.

Architecture: CHỦ owns BrowserManager + TokenCache per architecture spec.
              Browser stays alive during generation for on-demand reCAPTCHA refresh.
"""

from typing import Optional, Callable
from datetime import datetime, timedelta
import asyncio
import threading
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession, AccountState, SubscriptionType, PaygateTier
from config.constants import TokenLifetime, MIN_VALID_XCD, XCD_VARIATIONS_WAIT_TIMEOUT
from core.project_manager import ProjectManager
from core.recaptcha_session import RecaptchaBrowserSession, TokenCache

log = logging.getLogger(__name__)


class AccountManager:
    """CHỦ - Manages a single VEO account session.
    
    Responsibilities:
    - Session management (email, access_token, recaptcha)
    - Worker semaphore with acquire_workers() / release_workers()
    - Per-account reCAPTCHA lock (serializes all reCAPTCHA requests)
    - Token refresh coordination
    - Project management integration
    """
    
    @property
    def max_workers(self) -> int:
        """Get max concurrent workers (THỢ = videos) for this account."""
        return self._session.max_workers
    
    def set_max_workers(self, n: int):
        """Set max concurrent workers. Value from UI 'Total Output' column."""
        self._session.max_workers = max(0, n)
    
    # --- Deprecated slot accessors (backward compat) ---
    @property
    def max_slots(self) -> int:
        """DEPRECATED: Use max_workers instead."""
        return self._session.max_workers
    
    def set_max_slots(self, n: int):
        """DEPRECATED: Use set_max_workers instead."""
        self.set_max_workers(n)
    
    @property
    def retry_count(self) -> int:
        """Get retry count for this account."""
        return self._session.retry_count
    
    @property
    def request_timeout(self) -> int:
        """Get request timeout for this account."""
        return self._session.request_timeout
    
    def __init__(self, session: AccountSession):
        self._session = session
        self._lock = threading.Lock()  # threading.Lock for sync methods
        
        # Enabled flag — disabled accounts are skipped during dispatch
        self._enabled = True
        
        # Callbacks for token refresh
        self._on_token_refresh_needed: Optional[Callable] = None
        self._on_recaptcha_refresh_needed: Optional[Callable] = None
        
        # Project manager (CHỦ owns ProjectManager per MULTITHREADING_ARCHITECTURE.md)
        self._project_manager = ProjectManager()
        self._project_id: Optional[str] = None
        
        # Persistent browser session for reCAPTCHA refresh
        # (CHỦ owns BrowserManager per MULTITHREADING_ARCHITECTURE.md §6.1)
        self._browser_session: Optional[RecaptchaBrowserSession] = None
        self._token_cache = TokenCache()
        
        # Paygate tier — auto-detected from GET /v1/credits
        self._paygate_tier: str = "PAYGATE_TIER_TWO"
        
        # ProfilesController ref — set by AppController for debug browser sharing
        self._profiles_controller = None
        
        # Extension bridge ref — set by AppController for real-web token extraction
        self._extension_bridge = None
        
        # GAP #5: Restart-in-progress flag — prevents race between
        # extension reconnect and app-initiated browser restart
        self._restart_in_progress = False
    
    @property
    def extension_bridge(self):
        """Get extension bridge reference (public API for external access)."""
        return self._extension_bridge
    
    @extension_bridge.setter
    def extension_bridge(self, value):
        """Set extension bridge reference."""
        self._extension_bridge = value
        
        # Per-account reCAPTCHA lock — serializes all reCAPTCHA requests
        # across worker loop AND upscale queue (Bug #3 fix)
        self._recaptcha_lock = asyncio.Lock()
    
    @property
    def recaptcha_lock(self) -> asyncio.Lock:
        """Per-account lock to serialize reCAPTCHA requests.
        
        Prevents contention between engine worker loop and upscale queue
        both trying to refresh reCAPTCHA on the same account simultaneously.
        """
        return self._recaptcha_lock
    
    def set_profiles_controller(self, profiles_controller):
        """Set ProfilesController reference for debug browser sharing."""
        self._profiles_controller = profiles_controller
    
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
        """Check if account is ready for API calls.
        
        Must be enabled AND session ready.
        """
        return self._enabled and self._session.is_ready
    
    @property
    def is_enabled(self) -> bool:
        """Check if account is enabled for dispatch."""
        return self._enabled
    
    def enable(self):
        """Enable this account for task dispatch."""
        self._enabled = True
        log.info(f"[{self.email}] Account enabled")
    
    def disable(self):
        """Disable this account — won't be selected for new tasks.
        
        Running tasks will complete normally.
        """
        self._enabled = False
        log.info(f"[{self.email}] Account disabled")
    

    
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
    
    @property
    def project_manager(self) -> ProjectManager:
        """Get the ProjectManager for this account (CHỬ owns it)."""
        return self._project_manager
    
    def set_project_id(self, project_id: str):
        """Set project ID for this account."""
        self._project_id = project_id
    
    @property
    def paygate_tier(self) -> str:
        """Get cached paygate tier (auto-detected from /v1/credits)."""
        return self._paygate_tier
    
    async def fetch_paygate_tier(self, api_client) -> str:
        """Fetch paygate tier from GET /v1/credits and cache it.
        
        Protocol §3.3.1: Response contains userPaygateTier field.
        Called once per account, cached for session lifetime.
        """
        try:
            resp = await api_client.get_credits(
                access_token=self.get_access_token() or "",
                account_headers=self.get_api_headers(),
            )
            if resp.success and resp.data:
                tier = resp.data.get("userPaygateTier", "")
                if tier:
                    self._paygate_tier = tier
                    log.info(f"Account {self.email}: paygate tier = {tier}")
        except Exception as e:
            log.warning(f"Failed to fetch paygate tier for {self.email}: {e}")
        return self._paygate_tier
    
    def acquire_workers(self, n: int = 1) -> bool:
        """Acquire n workers atomically (thread-safe).
        
        Each worker = 1 THỢ = 1 concurrent video.
        Delegates to AccountSession.acquire_workers() which is the
        single source of truth for capacity tracking.
        
        Args:
            n: Number of workers to acquire.
        Returns:
            True if all n workers acquired, False otherwise.
        """
        with self._lock:
            return self._session.acquire_workers(n)
    
    def release_workers(self, n: int = 1):
        """Release n Fast ops workers (thread-safe)."""
        with self._lock:
            self._session.release_workers(n)
    
    def acquire_workers_lp(self, n: int = 1) -> bool:
        """Acquire n LP workers (thread-safe). LP soft cap defaults to full shared pool."""
        with self._lock:
            return self._session.acquire_workers_lp(n)
    
    def release_workers_lp(self, n: int = 1):
        """Release n LP workers (thread-safe)."""
        with self._lock:
            self._session.release_workers_lp(n)
        # Signal engine to wake foremen waiting for LP slots
        cb = getattr(self, '_on_lp_released', None)
        if cb:
            cb(self.email)
    
    def acquire_upscale_worker(self) -> bool:
        """Acquire 1 upscale worker slot (thread-safe).
        
        Separate from ops pool — max 4 concurrent upscale by default.
        Returns False if upscale pool is full.
        """
        with self._lock:
            return self._session.acquire_upscale_worker()
    
    def release_upscale_worker(self):
        """Release 1 upscale worker slot (thread-safe)."""
        with self._lock:
            self._session.release_upscale_worker()
    
    # --- Deprecated slot methods (backward compat) ---
    def acquire_slot(self) -> bool:
        """DEPRECATED: Use acquire_workers(n) instead."""
        with self._lock:
            return self._session.acquire_workers(1)
    
    def release_slot(self):
        """DEPRECATED: Use release_workers(n) instead."""
        with self._lock:
            self._session.release_workers(1)
    
    def get_access_token(self) -> Optional[str]:
        """Get valid access token.
        
        Returns None if token is expired and no sync refresh is available.
        Triggers refresh callback if token expiring soon.
        """
        if self._session.is_token_expired:
            # Token expired, trigger refresh callback (legacy)
            if self._on_token_refresh_needed:
                self._on_token_refresh_needed(self)
            return None
        
        # Check if nearing expiration (5 min before)
        buffer_check = timedelta(minutes=5)
        if self._session.token_expires and datetime.now() >= (self._session.token_expires - buffer_check):
            # Trigger background refresh
            if self._on_token_refresh_needed:
                self._on_token_refresh_needed(self)
        
        return self._session.access_token
    
    async def refresh_access_token(self) -> Optional[str]:
        """Refresh access token via extension bridge.
        
        Called when get_access_token() returns None (expired).
        Extension extracts fresh token from __NEXT_DATA__ on the VEO page.
        If page token is also stale, triggers tab reload first.
        
        Returns:
            Fresh access token, or None if all sources exhausted.
        """
        # Priority 1: Extension bridge (extract from live VEO page)
        if self._extension_bridge and self._extension_bridge.is_connected(self.email):
            try:
                result = await self._extension_bridge.request_access_token(self.email, timeout=10)
                # request_access_token() returns token string directly (not a dict)
                token = result if isinstance(result, str) else (result.get('token') if isinstance(result, dict) else None)
                if token:
                    # Update session with fresh token (assume ~55 min lifetime)
                    self._session.access_token = token
                    self._session.token_expires = datetime.now() + timedelta(minutes=55)
                    log.info(f"[{self.email}] 🔑 Access token refreshed via Extension bridge")
                    return token
                
                # Token from page was also stale — reload tab and try again
                log.info(f"[{self.email}] Page token stale, triggering tab reload via cooldown manager...")
                await self._extension_bridge._trigger_refresh(self.email, "Stale token recovery", level="full")
                # Wait for page to reload and re-render __NEXT_DATA__
                await asyncio.sleep(5)
                
                result = await self._extension_bridge.request_access_token(self.email, timeout=10)
                token = result if isinstance(result, str) else (result.get('token') if isinstance(result, dict) else None)
                if token:
                    self._session.access_token = token
                    self._session.token_expires = datetime.now() + timedelta(minutes=55)
                    log.info(f"[{self.email}] 🔑 Access token refreshed after tab reload")
                    return token
                    
            except Exception as e:
                log.warning(f"[{self.email}] Extension access token refresh failed: {e}")
        
        # Priority 2: Check if token became valid (e.g., refreshed by another path)
        if not self._session.is_token_expired:
            return self._session.access_token
        
        # ─── Priority 3: Active Extension Recovery Loop ───
        # After hard browser restart, Extension needs time to reconnect.
        # ALL workers on this account are blocked anyway (no reCAPTCHA either),
        # so waiting here is the correct behavior — not wasted time.
        if self._extension_bridge and not self._extension_bridge.is_connected(self.email):
            # Graceful wait: extension may be reconnecting
            log.debug(f"[{self.email}] Extension disconnected — waiting for reconnection...")
            reconnected = await self._extension_bridge.wait_for_extension(
                self.email, timeout=15.0
            )
            if reconnected:
                # Connected! Try token extraction
                try:
                    result = await self._extension_bridge.request_access_token(self.email, timeout=10)
                    token = result if isinstance(result, str) else (result.get('token') if isinstance(result, dict) else None)
                    if token:
                        self._session.access_token = token
                        self._session.token_expires = datetime.now() + timedelta(minutes=55)
                        log.info(f"[{self.email}] 🔑 Access token refreshed after reconnection")
                        return token
                except Exception as e:
                    log.debug(f"[{self.email}] Token extract after reconnect failed: {e}")
            
            # Still not connected — fall into active recovery
            log.debug(f"[{self.email}] Starting active extension recovery...")
            token = await self._active_extension_recovery()
            if token:
                return token
        
        log.error(f"[{self.email}] ❌ Access token refresh failed — all sources exhausted")
        return None
    
    def get_recaptcha_token(self) -> Optional[str]:
        """Get valid reCAPTCHA token from cache or session.
        
        Returns cached token if still valid (< 90s old).
        Returns session token as fallback.
        Returns None if all expired.
        """
        # Priority 1: TokenCache (most fresh, < 90s)
        cached = self._token_cache.get()
        if cached:
            return cached
        
        # Priority 2: Session token (may be stale but worth trying)
        if not self._session.needs_recaptcha_refresh:
            return self._session.recaptcha_token
        
        # All expired — caller must await refresh_recaptcha()
        return None
    
    def invalidate_recaptcha(self):
        """Invalidate current reCAPTCHA token (both cache and session).
        
        reCAPTCHA tokens are single-use: after any API call (success or failure),
        the token is consumed by Google's server. Call this before retry to force
        a fresh token on the next attempt.
        
        Idempotent: skips silently if already invalidated (Issue #2 fix).
        """
        if not self._token_cache.get() and not self._session.recaptcha_token:
            return  # Already invalidated — skip log to avoid noise
        self._token_cache.invalidate()
        self._session.recaptcha_token = None
        log.debug(f"[{self.email}] reCAPTCHA token invalidated (single-use consumed)")
    
    async def ensure_valid_token(self) -> Optional[str]:
        """Gap #2 fix: Centralized token validation + refresh.
        
        Checks if access_token is valid (non-empty, non-expired).
        If expired, refreshes via extension bridge.
        
        Returns:
            Valid access token, or None if refresh failed.
        """
        token = self.get_access_token()
        if token and not self._session.is_token_expired:
            return token
        
        log.info(f"[{self.email}] Access token invalid/expired, refreshing...")
        fresh = await self.refresh_access_token()
        if fresh:
            return fresh
        
        log.error(f"[{self.email}] ensure_valid_token: refresh failed")
        return None

    async def refresh_recaptcha(self) -> Optional[str]:
        """Get fresh reCAPTCHA token via Extension bridge (extension-only).
        
        Retries up to 3 times with progressive delay on timeout
        (CfT cold start or reCAPTCHA script loading may delay first attempts).
        
        Circuit-breaker: After 2+ consecutive full-cycle failures,
        applies escalating backoff (30s→60s→120s) to prevent infinite retry loops.
        
        Returns:
            Fresh reCAPTCHA token, or None if extension not connected.
        """
        # ── Circuit-breaker backoff ──
        # After 2+ consecutive failures, sleep before allowing retry
        consec = getattr(self, '_recaptcha_consecutive_failures', 0)
        if consec >= 2:
            backoff = min(30 * (2 ** (consec - 2)), 120)  # 30, 60, 120 cap
            log.warning(
                f"[{self.email}] ⏸️ reCAPTCHA circuit-breaker: {consec} consecutive "
                f"failures → backing off {backoff}s before retry"
            )
            await asyncio.sleep(backoff)
        
        if not self._extension_bridge:
            # Auto-recover Layer 1: find bridge from sibling accounts via parent manager
            if hasattr(self, '_parent_manager') and self._parent_manager:
                for acc in getattr(self._parent_manager, '_accounts', []):
                    if acc.extension_bridge and acc is not self:
                        self._extension_bridge = acc.extension_bridge
                        log.info(f"[{self.email}] ✅ Auto-recovered extension bridge from sibling {acc.email}")
                        break
            # Auto-recover Layer 2: get bridge from engine (always set at controller init)
            if not self._extension_bridge:
                engine_bridge = getattr(getattr(self, '_engine', None), '_extension_bridge', None)
                if engine_bridge:
                    self._extension_bridge = engine_bridge
                    log.info(f"[{self.email}] ✅ Auto-recovered extension bridge from engine")
            if not self._extension_bridge:
                log.warning(f"[{self.email}] ⏳ Extension bridge not yet available — reCAPTCHA deferred")
                self._recaptcha_consecutive_failures = consec + 1
                return None
        if not self._extension_bridge.is_connected(self.email):
            # Graceful wait: extension may be reconnecting (browser restart, network blip)
            log.debug(f"[{self.email}] Extension not connected — waiting for reconnection...")
            reconnected = await self._extension_bridge.wait_for_extension(
                self.email, timeout=15.0
            )
            if not reconnected:
                # Still not connected — silent return, caller handles retry
                log.debug(
                    f"[{self.email}] Extension still offline after 15s — "
                    f"reCAPTCHA deferred (bridge has {len(self._extension_bridge._connections)} conn(s))"
                )
                self._recaptcha_consecutive_failures = consec + 1
                return None
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                token = await self._extension_bridge.request_recaptcha(self.email, timeout=25)
                if token:
                    self._token_cache.set(token)
                    self._session.update_recaptcha(token)
                    # Reset circuit-breaker on success
                    self._recaptcha_consecutive_failures = 0
                    log.info(f"[{self.email}] 🧩 reCAPTCHA refreshed via Extension bridge (attempt {attempt})")
                    return token
                log.warning(f"[{self.email}] Extension bridge returned no reCAPTCHA token (attempt {attempt})")
            except Exception as e:
                log.warning(f"[{self.email}] Extension reCAPTCHA failed (attempt {attempt}): {e}")
            
            # Progressive delay (reCAPTCHA script may still be loading)
            if attempt < max_attempts:
                delay = 3 * attempt  # 3s, 6s
                log.info(f"[{self.email}] Retrying reCAPTCHA in {delay}s...")
                await asyncio.sleep(delay)
        
        # All attempts failed — increment circuit-breaker counter
        self._recaptcha_consecutive_failures = consec + 1
        log.warning(
            f"[{self.email}] ❌ reCAPTCHA refresh failed all {max_attempts} attempts "
            f"(consecutive failures: {consec + 1})"
        )
        return None
    
    async def ensure_browser(self, headless: bool = True):
        """Attach to debug browser page for TRPCClient access only.
        
        Extension-only architecture: headers, access tokens, and reCAPTCHA
        are ALL provided by the Extension bridge. The debug browser page
        is only needed for TRPCClient project operations.
        
        No headless browser is launched — extension handles all runtime data.
        """
        if self._browser_session and self._browser_session.is_ready:
            return
        
        profile_path = self._session.profile_path
        if not profile_path:
            log.warning(f"[{self.email}] No profile_path set, cannot attach browser")
            return
        
        # Try to attach to existing debug browser page (for TRPCClient only)
        launch_in_progress = False
        launch_stage = ""
        launch_error = ""
        if self._profiles_controller:
            debug_page = self._profiles_controller.get_debug_browser_page(self.email)
            if not debug_page:
                # Check if debug browser is being opened (entry exists but page not ready)
                entry = self._profiles_controller._debug_browsers.get(self.email) if hasattr(self._profiles_controller, '_debug_browsers') else None
                if entry:
                    import time as _wait_time
                    get_launch_status = getattr(self._profiles_controller, "get_debug_browser_launch_status", None)
                    status = get_launch_status(self.email) if callable(get_launch_status) else {}
                    launch_stage = status.get("stage") or "starting"
                    launch_error = status.get("error") or ""
                    launch_in_progress = launch_stage not in ("", "failed", "ready")
                    log.info(f"[{self.email}] ⏳ Debug browser launching (stage={launch_stage})...")
                    deadline = _wait_time.monotonic() + 5.0
                    last_stage = launch_stage
                    while _wait_time.monotonic() < deadline:
                        await asyncio.sleep(0.25)
                        debug_page = self._profiles_controller.get_debug_browser_page(self.email)
                        if debug_page:
                            break
                        status = get_launch_status(self.email) if callable(get_launch_status) else {}
                        launch_stage = status.get("stage") or launch_stage or "starting"
                        launch_error = status.get("error") or launch_error
                        if launch_stage == "failed":
                            break
                        if launch_stage != last_stage:
                            log.info(f"[{self.email}] ⏳ Debug browser launch stage → {launch_stage}")
                            last_stage = launch_stage
            
            if debug_page:
                log.info(f"[{self.email}] 🔗 Attaching to debug browser (page access only)")
                self._browser_session = RecaptchaBrowserSession(profile_path)
                self._browser_session.attach_to_sync_page(self._profiles_controller, self.email)
                # NOTE: No header capture, no token extraction, no warmup.
                # Extension bridge provides all runtime data.
                return
            
            if launch_in_progress:
                import time as _wait_time
                get_launch_status = getattr(self._profiles_controller, "get_debug_browser_launch_status", None)
                status = get_launch_status(self.email) if callable(get_launch_status) else {}
                started_at = status.get("started_at")
                elapsed = max(0.0, _wait_time.time() - started_at) if started_at else 0.0
                stage = status.get("stage") or launch_stage or "starting"
                err = status.get("error") or launch_error
                if stage == "failed":
                    log.warning(f"[{self.email}] Debug browser launch failed at stage={stage}: {err or 'unknown error'}")
                else:
                    log.info(
                        f"[{self.email}] Debug browser still launching "
                        f"(stage={stage}, elapsed={elapsed:.1f}s) — continuing extension-only for now"
                    )
                return
        
        # No debug browser available — that's fine in extension-only architecture.
        # Extension provides headers, tokens, and reCAPTCHA.
        # TRPCClient will fall back to API-based project creation.
        log.info(f"[{self.email}] No debug browser — extension-only mode (TRPCClient unavailable)")
    
    async def soft_recover_browser(self):
        """Soft recovery: navigate away and back WITHOUT killing Chrome.
        
        First-tier recovery for reCAPTCHA 403 failures.
        Keeps browser process alive, just reloads the page + warms up.
        
        Returns:
            True if recovery successful, False otherwise
        """
        email = self.email
        log.info(f"[{email}] 🔄 Soft browser recovery (no kill)...")
        
        if not self._browser_session:
            # FIX L1: Extension-only accounts - try extension bridge recovery
            if self._extension_bridge and self._extension_bridge.is_connected(email):
                log.info(f"[{email}] No browser session - using extension hard_navigation")
                try:
                    result = await self._extension_bridge.trigger_hard_navigation(email)
                    if result:
                        log.info(f"[{email}] Extension hard_navigation recovery complete")
                        return True
                except Exception as e:
                    log.warning(f"[{email}] Extension hard_navigation error: {e}")
            log.warning(f"[{email}] No browser session for soft recovery")
            return False
        
        # Invalidate reCAPTCHA token (force fresh request)
        self._session.recaptcha_token = None
        self._token_cache = TokenCache()
        
        try:
            result = await self._browser_session.soft_recovery()
            if result:
                log.info(f"[{email}] ✅ Soft recovery complete")
            else:
                log.warning(f"[{email}] ⚠️ Soft recovery returned False")
            return result
        except Exception as e:
            log.error(f"[{email}] ❌ Soft recovery failed: {e}")
            return False
    
    async def restart_browser(self):
        """Kill Chrome process completely and relaunch for fresh session.
        
        Uses profiles_controller to kill/relaunch the debug browser.
        GAP #2: Poll process exit instead of hardcoded sleep(3).
        GAP #5: Set _restart_in_progress flag to prevent reconnect race.
        
        Returns:
            True if restart successful, False otherwise
        """
        email = self.email
        
        # GAP #5: Guard against concurrent restarts
        if self._restart_in_progress:
            log.warning(f"[{email}] ⚠️ Restart already in progress — skipping")
            return False
        
        self._restart_in_progress = True
        log.info(f"[{email}] 🔄 Full browser restart: killing Chrome process...")
        
        try:
            # Step 1: Close session wrapper
            if self._browser_session:
                try:
                    await self._browser_session.close()
                except Exception:
                    pass
                self._browser_session = None
            
            # Step 2+3: Kill and relaunch Chrome via profiles_controller
            if self._profiles_controller:
                try:
                    self._profiles_controller.kill_debug_browser(email)
                    log.info(f"[{email}] Chrome kill signal sent")
                except Exception as e:
                    log.error(f"[{email}] kill_debug_browser error: {e}")
                
                # GAP #2: Poll process exit instead of hardcoded sleep(3)
                for i in range(10):
                    if not self._profiles_controller.is_debug_browser_open(email):
                        log.info(f"[{email}] Chrome process exited after {i+1}s")
                        break
                    await asyncio.sleep(1)
                else:
                    log.warning(f"[{email}] ⚠️ Chrome still running after 10s — proceeding anyway")
                
                try:
                    self._profiles_controller.open_browser_for_debug(email)
                    log.info(f"[{email}] Chrome relaunch signal sent, waiting for Extension...")
                    # Event-driven wait instead of hardcoded sleep(10)
                    if self._extension_bridge:
                        connected = await self._extension_bridge.wait_for_extension(email, timeout=30)
                        if connected:
                            log.info(f"[{email}] ✅ Extension reconnected after restart")
                        else:
                            log.warning(f"[{email}] ⚠️ Extension not reconnected within 30s")
                    else:
                        await asyncio.sleep(10)  # Fallback if no bridge
                except Exception as e:
                    log.error(f"[{email}] open_browser_for_debug error: {e}")
                    return False
            
            saved_client_data = self._session.client_data or ""  # For logging only
            self._session.access_token = None
            self._session.token_expires = None
            self._session.recaptcha_token = None
            self._session.client_data = ""          # Must clear to accept new value from new PID
            self._session.browser_validation = ""   # Also browser-specific
            self._session.browser_copyright = ""
            self._session.browser_year = ""
            self._token_cache = TokenCache()
            # ★ Reset reCAPTCHA circuit-breaker — fresh Chrome = fresh state
            # Without this, stale counter (up to 8) causes 120s backoff
            # even though the new Chrome's reCAPTCHA is perfectly healthy.
            self._recaptcha_consecutive_failures = 0
            
            # Step 5: Re-attach via ensure_browser (extracts fresh token + headers)
            try:
                await self.ensure_browser(headless=True)
                
            # Step 6: Wait for Variations Service to produce valid x-client-data
                # After restart, Chrome needs ~10-15s for Variations Service to load.
                # DO NOT restore the old cached value — it belonged to the killed PID
                # and causes 403 when paired with new PID's reCAPTCHA token.
                import time as _time
                wait_start = _time.monotonic()
                while _time.monotonic() - wait_start < XCD_VARIATIONS_WAIT_TIMEOUT:
                    current_cd = self._session.client_data or ""
                    if len(current_cd) >= MIN_VALID_XCD:
                        log.info(f"[{email}] ✅ x-client-data ready ({len(current_cd)} chars, waited {_time.monotonic() - wait_start:.1f}s)")
                        break
                    # Also check bridge cache directly
                    if self._extension_bridge:
                        bridge_headers = self._extension_bridge.get_cached_headers(email, max_age_seconds=0)
                        if bridge_headers:
                            bxcd = bridge_headers.get('x-client-data', '')
                            if len(bxcd) >= MIN_VALID_XCD:
                                self._session.client_data = bxcd
                                log.info(f"[{email}] ✅ x-client-data from bridge ({len(bxcd)} chars, waited {_time.monotonic() - wait_start:.1f}s)")
                                break
                    await asyncio.sleep(1)
                else:
                    current_cd = self._session.client_data or ""
                    log.warning(
                        f"[{email}] ⚠️ x-client-data still short ({len(current_cd)} chars) "
                        f"after {XCD_VARIATIONS_WAIT_TIMEOUT}s — engine borrow_headers will fix"
                    )
                
                log.info(f"[{email}] ✅ Browser restart complete — fresh PID, tokens, reCAPTCHA")
                return True
            except Exception as e:
                log.error(f"[{email}] ❌ ensure_browser after restart failed: {e}")
            return False
        finally:
            # GAP #5: Always clear restart flag
            self._restart_in_progress = False

    async def close_browser(self):
        """Close persistent browser session."""
        if self._browser_session:
            await self._browser_session.close()
            self._browser_session = None
    
    # ═══════════════════════════════════════════════════════════════
    # ACTIVE EXTENSION RECOVERY
    # ═══════════════════════════════════════════════════════════════
    
    async def _active_extension_recovery(self) -> Optional[str]:
        """Actively drive Extension reconnection through all phases.
        
        Phase 1: Verify Chrome alive → relaunch if dead
        Phase 2: Verify Extension loaded via CDP → wait/kill+relaunch
        Phase 3: Wait for WebSocket registration (event-driven)
        Phase 4: Extract access token
        
        Loops indefinitely until success. Only gives up on confirmed
        internet loss (120s consecutive down).
        """
        email = self.email
        cycle = 0
        
        while True:
            cycle += 1
            log.info(f"[{email}] 🔄 Recovery cycle {cycle}")
            
            # ── Phase 1: Chrome Process ──
            chrome_alive = await self._verify_chrome_alive()
            if not chrome_alive:
                # Check internet first
                if not await self._check_internet():
                    log.warning(f"[{email}] 🌐 Internet appears down — waiting...")
                    # Wait up to 120s for internet, checking every 10s
                    inet_restored = False
                    for _ in range(12):
                        await asyncio.sleep(10)
                        if await self._check_internet():
                            inet_restored = True
                            break
                    if not inet_restored:
                        log.error(f"[{email}] ❌ Internet down for 120s — giving up")
                        return None
                
                # Internet OK → relaunch Chrome
                if self._profiles_controller:
                    log.info(f"[{email}] Relaunching Chrome...")
                    try:
                        self._profiles_controller.open_browser_for_debug(email)
                        await asyncio.sleep(3)  # Process startup
                    except Exception as e:
                        log.error(f"[{email}] Chrome relaunch failed: {e}")
                        await asyncio.sleep(5)
                        continue
            
            # ── Phase 2: Extension Loaded (CDP check) ──
            ext_loaded = False
            for attempt in range(6):  # 6 × 5s = 30s max
                if self._is_extension_loaded_check():
                    ext_loaded = True
                    break
                log.debug(f"[{email}] Extension not loaded yet (attempt {attempt + 1}/6)")
                await asyncio.sleep(5)
            
            if not ext_loaded:
                log.warning(f"[{email}] Extension not loaded after 30s — kill + relaunch")
                if self._profiles_controller:
                    try:
                        self._profiles_controller.kill_debug_browser(email)
                    except Exception:
                        pass
                    await asyncio.sleep(3)
                continue  # Back to Phase 1
            
            # ── Phase 3: WebSocket Registration (event-driven) ──
            if self._extension_bridge:
                if self._extension_bridge.is_connected(email):
                    log.info(f"[{email}] ✅ Extension already connected")
                else:
                    log.info(f"[{email}] Waiting for WebSocket registration...")
                    connected = await self._extension_bridge.wait_for_extension(
                        email, timeout=30.0
                    )
                    if not connected:
                        log.warning(f"[{email}] WebSocket timeout — retry cycle")
                        continue  # Back to Phase 1
                    log.info(f"[{email}] ✅ Extension WebSocket connected")
            
            # ── Phase 4: Token Refresh ──
            for token_attempt in range(3):
                try:
                    result = await self._extension_bridge.request_access_token(
                        email, timeout=10
                    )
                    token = (
                        result if isinstance(result, str)
                        else (result.get('token') if isinstance(result, dict) else None)
                    )
                    if token:
                        self._session.access_token = token
                        self._session.token_expires = datetime.now() + timedelta(minutes=55)
                        log.info(f"[{email}] 🔑 Access token refreshed after recovery (cycle {cycle})")
                        return token
                except Exception as e:
                    log.warning(f"[{email}] Token extract attempt {token_attempt + 1}/3: {e}")
                await asyncio.sleep(2)
            
            log.warning(f"[{email}] Token refresh failed after connection — retry cycle")
    
    def _is_extension_loaded_check(self) -> bool:
        """Check if Extension is loaded in Chrome via CDP /json endpoint."""
        try:
            from core.extension_manager import is_extension_loaded
            from core.chrome_manager import _load_pid_file
            profile_path = self._session.profile_path
            if not profile_path:
                return False
            pid_info = _load_pid_file(profile_path)
            if not pid_info:
                return False
            return is_extension_loaded(pid_info["port"])
        except Exception:
            return False
    
    async def _verify_chrome_alive(self) -> bool:
        """Check if Chrome process is still running for this account."""
        try:
            from core.chrome_manager import _is_chrome_process_alive, _load_pid_file
            profile_path = self._session.profile_path
            if not profile_path:
                return False
            pid_info = _load_pid_file(profile_path)
            if not pid_info:
                return False
            return _is_chrome_process_alive(pid_info["pid"], profile_path)
        except Exception:
            return False
    
    async def _check_internet(self) -> bool:
        """Quick internet connectivity check (HEAD to google.com)."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    "https://www.google.com",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status < 500
        except Exception:
            return False
    
    async def _efficiency_mode_watchdog(self):
        """Re-disable Windows Efficiency Mode every 5 minutes.
        
        Windows may re-apply Efficiency Mode after we disable it,
        especially when the window is hidden or after user interaction
        with Task Manager. Periodic re-check keeps Chrome responsive.
        """
        while True:
            await asyncio.sleep(300)  # 5 minutes
            try:
                from core.chrome_manager import _disable_efficiency_mode, _load_pid_file
                profile_path = self._session.profile_path
                if not profile_path:
                    continue
                pid_info = _load_pid_file(profile_path)
                if pid_info:
                    _disable_efficiency_mode(pid_info["pid"])
            except Exception:
                pass
    
    def get_api_headers(self) -> dict:
        """Get per-account x-browser-* headers for API calls (extension-only).
        
        Returns dict suitable for passing as account_headers to VEOApiClient.
        Source: Extension bridge cached headers only.
        """
        return self.get_browser_headers()
    
    def get_browser_headers(self) -> dict:
        """Get x-browser-* headers from Extension bridge, with session fallback."""
        MIN_XCD = MIN_VALID_XCD  # Shared constant (40)
        if self._extension_bridge:
            ext_headers = self._extension_bridge.get_cached_headers(self.email)
            if ext_headers:
                xcd = ext_headers.get('x-client-data', '')
                xcd_len = len(xcd)
                if xcd_len < MIN_XCD:
                    # Bridge has short xcd — try session's guarded value
                    session_xcd = getattr(self._session, 'client_data', '') or '' if self._session else ''
                    if len(session_xcd) >= MIN_XCD:
                        ext_headers = {**ext_headers, 'x-client-data': session_xcd}
                        log.debug(f"[{self.email}] get_browser_headers: bridge xcd={xcd_len} chars → substituted session xcd={len(session_xcd)} chars")
                    else:
                        # Fallback: CDP-captured headers from ProfilesController
                        # Extension's onBeforeSendHeaders may have stale 8-char xcd,
                        # but CDP Network.requestWillBeSentExtraInfo captures the full value.
                        cdp_xcd = self._get_cdp_client_data()
                        if cdp_xcd and len(cdp_xcd) >= MIN_XCD:
                            ext_headers = {**ext_headers, 'x-client-data': cdp_xcd}
                            # Also update session so future calls don't need CDP lookup
                            if self._session:
                                self._session.client_data = cdp_xcd
                            log.info(f"[{self.email}] get_browser_headers: bridge xcd={xcd_len} → CDP xcd={len(cdp_xcd)} chars")
                        else:
                            log.debug(f"[{self.email}] get_browser_headers: bridge xcd={xcd_len} chars, session xcd={len(session_xcd)} chars (both short)")
                return ext_headers
            else:
                log.debug(f"[{self.email}] get_browser_headers: bridge returned None (cache miss or stale)")
        else:
            log.debug(f"[{self.email}] get_browser_headers: no _extension_bridge ref")
        # Fallback: use session-stored headers from CDP/debug browser capture
        if self._session:
            session_headers = {}
            if getattr(self._session, 'browser_validation', None):
                session_headers['x-browser-validation'] = self._session.browser_validation
            if getattr(self._session, 'client_data', None):
                session_headers['x-client-data'] = self._session.client_data
            if getattr(self._session, 'browser_channel', None):
                session_headers['x-browser-channel'] = self._session.browser_channel
            if getattr(self._session, 'browser_copyright', None):
                session_headers['x-browser-copyright'] = self._session.browser_copyright
            if getattr(self._session, 'browser_year', None):
                session_headers['x-browser-year'] = self._session.browser_year
            if session_headers:
                return session_headers
        return {}
    
    def _get_cdp_client_data(self) -> str:
        """Get x-client-data from ProfilesController's CDP-captured headers.
        
        CDP (Network.requestWillBeSentExtraInfo) captures the REAL x-client-data
        that Chrome sends, while Extension's webRequest API may have a stale value.
        This bridges the gap between the two independent header capture systems.
        
        Rate-limited to avoid excessive ProfilesController lookups.
        """
        try:
            pc = getattr(self, '_profiles_controller', None)
            if not pc:
                return ''
            cdp_headers = pc.get_debug_browser_headers(self.email)
            return cdp_headers.get('x-client-data', '')
        except Exception:
            return ''
    
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
        
        DEPRECATED: This method previously returned wrong auth headers
        (Authorization: Bearer, application/json, x-recaptcha-token).
        
        Per VEO_Web_Client_Protocol_Analysis.md §3.3:
        - REST endpoints use text/plain;charset=UTF-8
        - NO Authorization: Bearer header
        - reCAPTCHA goes in request body clientContext, not headers
        - x-browser-* headers are set by api_client._build_headers()
        
        Callers should use api_client._build_headers() instead.
        Returns minimal headers for backwards compatibility.
        """
        access_token = self.get_access_token()
        recaptcha_token = self.get_recaptcha_token()
        
        if not access_token or not recaptcha_token:
            return None
        
        # Only return Content-Type — auth is handled via x-browser-* headers
        # in api_client._build_headers()
        return {
            "Content-Type": "text/plain;charset=UTF-8",
        }
    
    def get_status(self) -> dict:
        """Get account status summary."""
        browser_ready = self._browser_session.is_ready if self._browser_session else False
        cache_age = f"{self._token_cache.age:.0f}s" if self._token_cache.age != float("inf") else "N/A"
        return {
            "email": self.email,
            "enabled": self._enabled,
            "sku": self._session.sku.value,
            "paygate_tier": self._session.paygate_tier.value,
            "credits": self._session.credits,
            "workers": f"{self._session.active_workers}/{self._session.max_workers}",
            "slots": f"{self._session.active_workers}/{self._session.max_workers}",  # compat
            "token_expired": self._session.is_token_expired,
            "needs_recaptcha": self._session.needs_recaptcha_refresh,
            "recaptcha_age": f"{self._session.recaptcha_age:.0f}s",
            "recaptcha_cache_age": cache_age,
            "browser_alive": browser_ready,
            "project_id": self._project_id,
            "is_ready": self.is_ready,
        }
