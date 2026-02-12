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
from config.constants import TokenLifetime
from core.project_manager import ProjectManager
from core.recaptcha_session import RecaptchaBrowserSession, TokenCache

log = logging.getLogger(__name__)


class AccountManager:
    """CHỦ - Manages a single VEO account session.
    
    Responsibilities:
    - Session management (email, access_token, recaptcha)
    - 4-slot semaphore with acquire_slot() / release_slot()
    - Token refresh coordination
    - Project management integration
    """
    
    @property
    def max_slots(self) -> int:
        """Get max concurrent slots for this account."""
        return self._session.max_slots
    
    def set_max_slots(self, n: int):
        """Set max concurrent slots (0-4). 0 effectively disables processing."""
        self._session.max_slots = max(0, min(n, 4))
    
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
    
    def acquire_slot(self) -> bool:
        """Attempt to acquire a slot (non-blocking, thread-safe).
        
        Delegates to AccountSession.acquire_slot() which is the
        single source of truth for slot tracking (Issue 4+9 fix).
        
        Returns:
            True if slot acquired, False otherwise.
        """
        with self._lock:
            return self._session.acquire_slot()
    
    def release_slot(self):
        """Release a slot (thread-safe).
        
        Delegates to AccountSession.release_slot().
        """
        with self._lock:
            self._session.release_slot()
    
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
        """
        self._token_cache.invalidate()
        self._session.recaptcha_token = None
        log.debug(f"[{self.email}] reCAPTCHA token invalidated (single-use consumed)")

    async def refresh_recaptcha(self) -> Optional[str]:
        """Get fresh reCAPTCHA token from alive browser.
        
        This is the CORRECT way to refresh reCAPTCHA:
        - Browser is already on VEO page (persistent session)
        - Calls grecaptcha.execute() directly (~100-500ms)
        - Updates both TokenCache and AccountSession
        
        Returns:
            Fresh reCAPTCHA token, or None if browser is not available
        """
        if not self._browser_session or not self._browser_session.is_ready:
            log.warning(f"[{self.email}] Browser not ready for reCAPTCHA refresh")
            # Fallback: fire old callback if exists
            if self._on_recaptcha_refresh_needed:
                self._on_recaptcha_refresh_needed(self)
            return None
        
        try:
            token = await self._browser_session.get_recaptcha_token()
            if token:
                self._token_cache.set(token)
                self._session.update_recaptcha(token)
                log.info(f"[{self.email}] reCAPTCHA refreshed via persistent browser")
            return token
        except Exception as e:
            log.error(f"[{self.email}] reCAPTCHA refresh failed: {e}")
            return None
    
    async def ensure_browser(self, headless: bool = True):
        """Start persistent browser if not running.
        
        Called by MultiAccountManager.startup() or lazily before first generate.
        
        Priority:
        1. If debug browser is already open → attach to its page (no new browser)
        2. Otherwise → launch headless browser with persistent profile
        """
        if self._browser_session and self._browser_session.is_ready:
            return
        
        profile_path = self._session.profile_path
        if not profile_path:
            log.warning(f"[{self.email}] No profile_path set, cannot start browser")
            return
        
        # Priority 1: Try to attach to existing debug browser page
        # This avoids Chrome profile lock conflict (only 1 process per user-data-dir)
        if self._profiles_controller:
            # Wait for debug browser to be ready (may be starting on background thread)
            # Without this wait, we fall through to Priority 2 which crashes
            # because it tries to launch headless Chrome on the same locked profile dir
            debug_page = self._profiles_controller.get_debug_browser_page(self.email)
            if not debug_page:
                # Check if debug browser is being opened (entry exists but page not ready)
                entry = self._profiles_controller._debug_browsers.get(self.email) if hasattr(self._profiles_controller, '_debug_browsers') else None
                if entry:
                    log.info(f"[{self.email}] ⏳ Debug browser starting, waiting...")
                    for _ in range(60):  # Wait up to 30s
                        await asyncio.sleep(0.5)
                        debug_page = self._profiles_controller.get_debug_browser_page(self.email)
                        if debug_page:
                            break
            
            if debug_page:
                log.info(f"[{self.email}] 🔗 Attaching to debug browser (shared profile)")
                self._browser_session = RecaptchaBrowserSession(profile_path)
                self._browser_session.attach_to_sync_page(self._profiles_controller, self.email)
                
                # Bug 10 fix: Capture x-browser-* headers from debug browser
                # RecaptchaBrowserSession._SyncPageAsyncWrapper.route() is a no-op,
                # so captured_headers is always empty. Read directly from
                # profiles_controller which has real request interception.
                headers = self._profiles_controller.get_debug_browser_headers(self.email)
                if headers:
                    self._session.update_browser_headers(
                        browser_validation=headers.get("x-browser-validation", ""),
                        client_data=headers.get("x-client-data", ""),
                        browser_channel=headers.get("x-browser-channel", "stable"),
                        browser_copyright=headers.get("x-browser-copyright", ""),
                        browser_year=headers.get("x-browser-year", ""),
                    )
                    log.info(f"[{self.email}] Browser headers captured from debug browser: {list(headers.keys())}")
                else:
                    log.warning(f"[{self.email}] ⚠️ Debug browser attached but no x-browser-* headers captured")
                
                # Extract access_token from debug browser page
                if not self._session.access_token:
                    access_token, email = await self._browser_session.extract_access_token()
                    if access_token:
                        self._session.access_token = access_token
                        self._session.token_expires = datetime.now() + timedelta(hours=1)
                        log.info(f"[{self.email}] ✅ Access token extracted from debug browser ({len(access_token)} chars)")
                    else:
                        log.warning(f"[{self.email}] ⚠️ Could not extract access_token from debug browser")
                return
        
        # Priority 2: Launch own headless browser (no debug browser available)
        self._browser_session = RecaptchaBrowserSession(profile_path)
        await self._browser_session.ensure_ready(headless=headless)
        
        # Extract access_token from __NEXT_DATA__ (page is on VEO)
        # ChromeProfile does NOT store access_token, so we must get it live
        if not self._session.access_token:
            access_token, email = await self._browser_session.extract_access_token()
            if access_token:
                self._session.access_token = access_token
                # Set expiry to 1 hour from now (Google OAuth2 default)
                self._session.token_expires = datetime.now() + timedelta(hours=1)
                log.info(f"[{self.email}] ✅ Access token extracted from browser ({len(access_token)} chars)")
            else:
                log.warning(f"[{self.email}] ⚠️ Could not extract access_token from browser page")
        
        # Capture initial headers — ALL 5 per Protocol Analysis §1.4
        headers = self._browser_session.captured_headers
        if headers:
            self._session.update_browser_headers(
                browser_validation=headers.get("x-browser-validation", ""),
                client_data=headers.get("x-client-data", ""),
                browser_channel=headers.get("x-browser-channel", "stable"),
                browser_copyright=headers.get("x-browser-copyright", ""),
                browser_year=headers.get("x-browser-year", ""),
            )
            log.info(f"[{self.email}] Browser headers captured: {list(headers.keys())}")
    
    async def restart_browser(self):
        """Kill Chrome process completely and relaunch for fresh session.
        
        Full restart sequence:
        1. Close session wrapper (RecaptchaBrowserSession)
        2. Kill Chrome process via profiles_controller
        3. Wait for process to fully exit
        4. Relaunch Chrome via profiles_controller
        5. Wait for debug browser to be ready
        6. Re-attach via ensure_browser() (re-extracts tokens/headers)
        
        Returns:
            True if restart successful, False otherwise
        """
        email = self.email
        log.info(f"[{email}] 🔄 Full browser restart: killing Chrome process...")
        
        # Step 1: Close session wrapper
        if self._browser_session:
            try:
                await self._browser_session.close()
            except Exception:
                pass
            self._browser_session = None
        
        # Step 2: Kill Chrome process via profiles_controller
        if self._profiles_controller:
            try:
                self._profiles_controller.kill_debug_browser(email)
                log.info(f"[{email}] Chrome kill signal sent")
            except Exception as e:
                log.error(f"[{email}] kill_debug_browser error: {e}")
        
        # Step 3: Wait for Chrome to fully exit
        await asyncio.sleep(3)
        
        # Step 4: Invalidate cached tokens (force fresh extraction)
        self._session.access_token = None
        self._session.token_expires = None
        self._session.recaptcha_token = None
        self._token_cache = TokenCache()
        
        # Step 5: Relaunch Chrome via profiles_controller
        if self._profiles_controller:
            try:
                self._profiles_controller.open_browser_for_debug(email)
                log.info(f"[{email}] Chrome relaunch signal sent, waiting for ready...")
                # Wait for debug browser to initialize
                await asyncio.sleep(5)
            except Exception as e:
                log.error(f"[{email}] open_browser_for_debug error: {e}")
                return False
        
        # Step 6: Re-attach via ensure_browser (extracts fresh token + headers)
        try:
            await self.ensure_browser(headless=True)
            log.info(f"[{email}] ✅ Browser restart complete — fresh PID, tokens, reCAPTCHA")
            return True
        except Exception as e:
            log.error(f"[{email}] ❌ ensure_browser after restart failed: {e}")
            return False

    async def close_browser(self):
        """Close persistent browser session."""
        if self._browser_session:
            await self._browser_session.close()
            self._browser_session = None
    
    def get_api_headers(self) -> dict:
        """Get per-account x-browser-* headers for API calls.
        
        Returns dict suitable for passing as account_headers to VEOApiClient.
        Delegates to AccountSession.get_browser_headers().
        """
        return self._session.get_browser_headers()
    
    def get_browser_headers(self) -> dict:
        """Get x-browser-* headers from persistent browser."""
        # Try browser session first (works for Priority 2: own headless browser)
        if self._browser_session:
            headers = self._browser_session.captured_headers
            if headers:
                return headers
        # Fallback to profiles_controller (for Priority 1: debug browser)
        if self._profiles_controller:
            return self._profiles_controller.get_debug_browser_headers(self.email)
        return {}
    
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
            "slots": f"{self.active_slots}/{self.max_slots}",
            "token_expired": self._session.is_token_expired,
            "needs_recaptcha": self._session.needs_recaptcha_refresh,
            "recaptcha_age": f"{self._session.recaptcha_age:.0f}s",
            "recaptcha_cache_age": cache_age,
            "browser_alive": browser_ready,
            "project_id": self._project_id,
            "is_ready": self.is_ready,
        }
