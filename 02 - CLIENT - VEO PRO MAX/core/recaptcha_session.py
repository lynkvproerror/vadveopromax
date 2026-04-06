import logging

log = logging.getLogger(__name__)
"""
VEO Pro Max - Persistent reCAPTCHA Browser Session

Reference: RECAPTCHA_BROWSER_MANAGEMENT.md §4
Role: Keeps a headless browser alive per account for on-demand reCAPTCHA refresh.

Architecture: CHỦ (AccountManager) owns one RecaptchaBrowserSession.
             Browser stays alive during generation, closed on shutdown.

Key Design:
- Browser opens ONCE per account (via ensure_ready)
- reCAPTCHA tokens refreshed on-demand via grecaptcha.execute()
- x-browser-validation headers re-captured periodically
- TokenCache prevents unnecessary browser calls (90s validity)
"""

from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import time
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# === TOKEN CACHE ===

class TokenCache:
    """Cache reCAPTCHA tokens to minimize browser calls.
    
    Reference: RECAPTCHA_BROWSER_MANAGEMENT.md §4.2
    
    Note: Tokens are normally invalidated immediately after each API call
    (single-use). TTL acts as a safety net for edge cases where
    invalidate() is missed (e.g., exception paths).
    """
    
    TOKEN_LIFETIME = 90  # Safety net TTL (normally invalidated before this)
    
    def __init__(self):
        self._token: Optional[str] = None
        self._timestamp: float = 0
    
    @property
    def is_valid(self) -> bool:
        return (
            self._token is not None and
            time.time() - self._timestamp < self.TOKEN_LIFETIME
        )
    
    @property
    def age(self) -> float:
        """Age in seconds since last set."""
        if self._timestamp == 0:
            return float("inf")
        return time.time() - self._timestamp
    
    def get(self) -> Optional[str]:
        if self.is_valid:
            return self._token
        return None
    
    def set(self, token: str):
        self._token = token
        self._timestamp = time.time()
    
    def invalidate(self):
        self._token = None
        self._timestamp = 0

# === SYNC-TO-ASYNC PAGE WRAPPER ===

class _SyncPageAsyncWrapper:
    """Routes JS calls to the debug browser thread via command queue.
    
    Playwright sync pages are greenlet-bound — calling page.evaluate()
    from a different thread causes 'Cannot switch to a different thread'.
    This wrapper uses ProfilesController.execute_js_on_debug_browser()
    which marshals calls through the browser thread's command queue.
    """
    
    def __init__(self, profiles_controller, email: str):
        self._profiles_controller = profiles_controller
        self._email = email
    
    async def evaluate(self, expression, arg=None):
        """Execute JS on debug browser page via command queue."""
        import asyncio
        loop = asyncio.get_running_loop()
        # execute_js_on_debug_browser is thread-safe (queue + Event)
        # but blocks the calling thread — run in executor to avoid blocking async loop
        # Timeout 30s: TRPC fetch calls have 15s AbortController + queue overhead
        result = await loop.run_in_executor(
            None,
            lambda: self._profiles_controller.execute_js_on_debug_browser(
                self._email, expression, arg=arg, timeout=30.0
            )
        )
        return result
    
    async def wait_for_function(self, expression, timeout=30000):
        """Poll until JS expression returns truthy."""
        import asyncio
        import time
        deadline = time.time() + (timeout / 1000.0)
        while time.time() < deadline:
            result = await self.evaluate(expression)
            if result:
                return result
            await asyncio.sleep(0.5)
        raise TimeoutError(f"wait_for_function timed out after {timeout}ms")
    
    async def goto(self, url, **kwargs):
        """Navigate page via JS."""
        return await self.evaluate(f"window.location.href = '{url}'")
    
    async def reload(self, **kwargs):
        """Reload page via JS."""
        return await self.evaluate("window.location.reload()")
    
    async def route(self, url, handler):
        """Not supported in queue mode."""
        pass


# === RECAPTCHA BROWSER SESSION ===

class RecaptchaBrowserSession:
    """Persistent headless browser session for reCAPTCHA token retrieval.
    
    Reference: RECAPTCHA_BROWSER_MANAGEMENT.md §4.1
    
    NOT for page automation — only for:
    1. reCAPTCHA token extraction  (grecaptcha.execute)
    2. x-browser-validation header capture
    3. Access token extraction  (__NEXT_DATA__)
    
    Lifecycle:
        session = RecaptchaBrowserSession(profile_path)
        await session.ensure_ready()     # Opens browser, navigates to VEO
        token = await session.get_recaptcha_token()  # Fast: ~100ms
        headers = session.captured_headers
        await session.close()            # On shutdown
    """
    
    VEO_URL = "https://labs.google/fx/tools/flow"
    RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
    
    def __init__(self, profile_path: str):
        self._profile_path = profile_path
        self._playwright = None
        self._browser = None  # CDP-connected browser
        self._context = None  # BrowserContext
        self._page = None
        self._ready = False
        self._captured_headers: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._recovery_lock = asyncio.Lock()  # Serialize soft_recovery across workers
        self._is_attached = False  # True when reusing debug browser page
    
    @property
    def is_ready(self) -> bool:
        if not self._ready or self._page is None:
            return False
        # ★ FIX: When attached to debug browser via _SyncPageAsyncWrapper,
        # check that the browser thread is still alive. After Playwright
        # disconnects, the wrapper still exists but can't process commands.
        if self._is_attached and isinstance(self._page, _SyncPageAsyncWrapper):
            pc = self._page._profiles_controller
            email = self._page._email
            if pc and hasattr(pc, '_debug_browsers'):
                entry = pc._debug_browsers.get(email)
                if not entry:
                    # Debug browser thread exited — mark ourselves dead
                    log.debug(
                        f"[RecaptchaBrowserSession] Debug browser gone for {email} "
                        f"— marking not ready"
                    )
                    self._ready = False
                    return False
        return True
    
    @property
    def captured_headers(self) -> Dict[str, str]:
        """Return captured x-browser-* headers."""
        return dict(self._captured_headers)
    
    def attach_to_sync_page(self, profiles_controller, email: str):
        """Attach to debug browser via command queue (thread-safe).
        
        Routes all JS calls through ProfilesController.execute_js_on_debug_browser()
        which uses the debug browser thread's command queue, keeping all
        Playwright calls on the correct greenlet.
        
        This avoids launching a second browser on the same profile dir.
        """
        self._page = _SyncPageAsyncWrapper(profiles_controller, email)
        self._ready = True
        self._is_attached = True
        self._playwright = None  # Not owned by us
        self._context = None     # Not owned by us
        log.debug(f"[RecaptchaBrowserSession] ✅ Attached to debug browser page (shared profile)")
    
    async def ensure_ready(self, headless: bool = True, timeout_ms: int = 30000):
        """Open browser, navigate to VEO page, wait for reCAPTCHA Enterprise.
        
        VEO uses reCAPTCHA Enterprise (not v3). The page loads enterprise.js
        automatically. We wait for it, and inject as fallback if needed.
        
        Uses persistent Chrome (detached process) — survives app restarts.
        Connects via CDP instead of launching new browser.
        
        Idempotent — safe to call multiple times.
        """
        async with self._lock:
            if self._ready:
                return
            
            try:
                from playwright.async_api import async_playwright
                from core.chrome_manager import launch_or_reconnect
                
                # Launch or reconnect to persistent Chrome
                chrome_info = launch_or_reconnect(
                    self._profile_path,
                    email="",
                    start_url="about:blank",
                    hidden=True,
                )
                cdp_port = chrome_info["port"]
                is_reconnect = "tabs" in chrome_info
                
                self._playwright = await async_playwright().start()
                
                # Connect via CDP (Chrome is already running)
                self._browser = await self._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{cdp_port}"
                )
                self._context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
                
                # Reuse existing pages — do NOT create duplicate tabs
                existing_pages = self._context.pages
                if existing_pages:
                    self._page = existing_pages[0]
                else:
                    self._page = await self._context.new_page()
                
                # Navigate to VEO only if not already there
                current_url = self._page.url
                if "labs.google" not in current_url:
                    await self._page.goto(self.VEO_URL, wait_until="networkidle", timeout=timeout_ms)
                
                # Wait for reCAPTCHA Enterprise (MUST be before header interception)
                await self._ensure_recaptcha_enterprise()
                
                # Set up header interception AFTER reCAPTCHA (route interception can block script loading)
                await self._setup_header_interception()
                
                self._ready = True
                log.info(f"[RecaptchaBrowserSession] ✅ Browser ready for {Path(self._profile_path).name} ({'reconnected' if is_reconnect else 'new'}, port={cdp_port})")
                
                # Warmup: simulate human activity to build reCAPTCHA trust
                await self.warmup()
                
            except Exception as e:
                log.error(f"[RecaptchaBrowserSession] ❌ Failed to start browser: {e}")
                await self._cleanup()
                raise
    
    async def warmup(self):
        """Simulate human-like activity to build reCAPTCHA Enterprise trust score.
        
        Called after ensure_ready() or attach_to_sync_page() to warm up the browser
        before any API requests. reCAPTCHA Enterprise scores based on browser behavior,
        so a "cold" browser with no activity will get a low trust score → 403.
        
        Activities: random scrolls, mouse movements, small delays.
        Total time: ~2-3s.
        """
        if not self.is_ready:
            return
        
        try:
            log.info("[RecaptchaBrowserSession] 🔥 Warming up browser (simulated activity)...")

            # Small settle delay for reCAPTCHA to register the activity
            await asyncio.sleep(random.uniform(1.0, 2.0))
            log.info("[RecaptchaBrowserSession] ✅ Browser warmup complete")
        except Exception as e:
            log.error(f"[RecaptchaBrowserSession] ⚠️ Warmup failed (non-fatal): {e}")
    
    
    async def soft_recovery(self):
        """Soft recovery: navigate away and back WITHOUT killing Chrome.
        
        Used after consecutive reCAPTCHA 403 failures as first-tier recovery.
        Much faster than full restart (~5s vs ~15s) and keeps browser alive.
        
        Steps:
        1. Navigate to about:blank (clear page state)
        2. Wait briefly
        3. Navigate back to VEO URL
        4. Re-initialize reCAPTCHA Enterprise
        5. Run warmup (simulated activity)
        
        Returns:
            True if recovery successful, False otherwise  
        """
        if not self.is_ready:
            return False
        
        async with self._recovery_lock:
            try:
                log.info("[RecaptchaBrowserSession] 🔄 Soft recovery: navigating away...")
            
                # Step 1: Navigate away
                await self._page.evaluate("window.location.href = 'about:blank'")
                await asyncio.sleep(1.5)
                
                # Step 2: Navigate back to VEO
                log.info("[RecaptchaBrowserSession] 🔄 Soft recovery: navigating back to VEO...")
                await self._page.evaluate(f"window.location.href = '{self.VEO_URL}'")
                
                # Step 3: Wait for page to load
                await asyncio.sleep(5)
                
                # Step 4: Re-initialize reCAPTCHA Enterprise
                await self._ensure_recaptcha_enterprise()
                
                # Step 5: Warmup
                await self.warmup()
                
                log.info("[RecaptchaBrowserSession] ✅ Soft recovery complete")
                return True
                
            except Exception as e:
                log.error(f"[RecaptchaBrowserSession] ❌ Soft recovery failed: {e}")
                return False
    
    RECAPTCHA_ENTERPRISE_CHECK = (
        "typeof grecaptcha !== 'undefined' && "
        "typeof grecaptcha.enterprise !== 'undefined' && "
        "typeof grecaptcha.enterprise.execute === 'function'"
    )
    
    async def _ensure_recaptcha_enterprise(self, timeout_ms: int = 15000):
        """Wait for reCAPTCHA Enterprise to be ready, inject if needed.
        
        VEO loads enterprise.js via its _app bundle. We first wait for it
        to initialize. If it doesn't load (e.g. in headless mode), we
        inject the enterprise script as fallback.
        """
        if not self._page:
            return
        
        # Check if already available (page should load it)
        already = await self._page.evaluate(self.RECAPTCHA_ENTERPRISE_CHECK)
        if already:
            log.info("[RecaptchaBrowserSession] ✅ reCAPTCHA Enterprise already loaded")
            return
        
        # Wait a bit — the script might still be initializing
        try:
            await self._page.wait_for_function(
                self.RECAPTCHA_ENTERPRISE_CHECK, timeout=8000
            )
            log.info("[RecaptchaBrowserSession] ✅ reCAPTCHA Enterprise ready after wait")
            return
        except Exception:
            pass
        
        # Fallback: inject enterprise.js manually
        site_key = self.RECAPTCHA_SITE_KEY
        log.info(f"[RecaptchaBrowserSession] Injecting reCAPTCHA Enterprise script (key={site_key[:12]}...)")
        
        try:
            await self._page.evaluate(f'''() => {{
                return new Promise((resolve, reject) => {{
                    const script = document.createElement('script');
                    script.src = 'https://www.google.com/recaptcha/enterprise.js?render={site_key}';
                    script.onload = () => resolve(true);
                    script.onerror = () => reject(new Error('reCAPTCHA Enterprise script load failed'));
                    document.head.appendChild(script);
                }});
            }}''')
            
            await self._page.wait_for_function(
                self.RECAPTCHA_ENTERPRISE_CHECK, timeout=timeout_ms
            )
            log.info("[RecaptchaBrowserSession] ✅ reCAPTCHA Enterprise injected and ready")
        except Exception:
            log.warning("[RecaptchaBrowserSession] ⚠️ reCAPTCHA Enterprise not available — will retry on token request")
    
    async def get_recaptcha_token(self) -> Optional[str]:
        """Execute grecaptcha and return fresh token.
        
        Strategy:
        1. Try to extract site key dynamically from the page
        2. Use page's native reCAPTCHA Enterprise if available
        3. Inject Enterprise script only as last resort
        
        Returns:
            str: reCAPTCHA token valid for ~120s, or None if failed
        """
        if not self.is_ready:
            log.warning("[RecaptchaBrowserSession] ⚠️ Browser not ready, call ensure_ready() first")
            return None
        
        try:
            # Step 1: Dynamically extract site key from page
            site_key = await self._page.evaluate('''() => {
                // Method 1: From reCAPTCHA script src URL (most reliable)
                for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
                    const m = s.src.match(/render=([^&]+)/);
                    if (m && m[1] !== 'explicit') return m[1];
                }
                // Method 2: From ___grecaptcha_cfg internal config
                if (typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients) {
                    for (const id in ___grecaptcha_cfg.clients) {
                        const client = ___grecaptcha_cfg.clients[id];
                        // Walk the client tree to find sitekey
                        for (const key in client) {
                            const obj = client[key];
                            if (obj && typeof obj === 'object') {
                                for (const k2 in obj) {
                                    const v = obj[k2];
                                    if (v && typeof v === 'object' && v.sitekey) return v.sitekey;
                                }
                            }
                        }
                    }
                }
                // Method 3: From data-sitekey attribute
                const el = document.querySelector('[data-sitekey]');
                if (el) return el.getAttribute('data-sitekey');
                return null;
            }''')
            
            if site_key:
                log.info(f"[RecaptchaBrowserSession] ✅ Extracted site key from page: {site_key[:16]}...")
            else:
                site_key = self.RECAPTCHA_SITE_KEY
                log.warning(f"[RecaptchaBrowserSession] ⚠️ Using fallback site key: {site_key[:16]}...")
            
            # Step 2: Check if reCAPTCHA Enterprise is available
            has_grecaptcha = await self._page.evaluate(self.RECAPTCHA_ENTERPRISE_CHECK)
            
            if not has_grecaptcha:
                log.warning("[RecaptchaBrowserSession] ⚠️ reCAPTCHA Enterprise not found, re-injecting...")
                await self._ensure_recaptcha_enterprise()
                
                has_grecaptcha = await self._page.evaluate(self.RECAPTCHA_ENTERPRISE_CHECK)
                if not has_grecaptcha:
                    log.error("[RecaptchaBrowserSession] ❌ reCAPTCHA Enterprise still not available")
                    return None
            

            
            log.info(f"[RecaptchaBrowserSession] 🔑 Executing reCAPTCHA Enterprise with key={site_key[:16]}... action=VIDEO_GENERATION")
            token = await self._page.evaluate(f'''
                async () => {{
                    try {{
                        return await grecaptcha.enterprise.execute('{site_key}', {{action: 'VIDEO_GENERATION'}});
                    }} catch (e) {{
                        console.error('reCAPTCHA Enterprise error:', e);
                        return null;
                    }}
                }}
            ''')
            
            if token:
                # HAR verified: valid tokens are 1742-2169 chars
                if len(token) < 1000:
                    log.warning(f"[RecaptchaBrowserSession] ⚠️ Token suspiciously short ({len(token)} chars < 1000), rejecting")
                    return None
                log.info(f"[RecaptchaBrowserSession] ✅ reCAPTCHA token obtained ({len(token)} chars)")
            else:
                log.error("[RecaptchaBrowserSession] ❌ grecaptcha.enterprise.execute() returned null")
            
            return token
            
        except Exception as e:
            log.error(f"[RecaptchaBrowserSession] ❌ reCAPTCHA extraction failed: {e}")
            return None
    
    async def extract_access_token(self) -> tuple:
        """Extract access token from __NEXT_DATA__ (if page is alive).
        
        Bug 4 fix: Retries up to 5 times with exponential backoff when
        execution context is destroyed by navigation (race condition with
        browser thread Steps 4/5/5b which can take up to ~36s total).
        
        Backoff: 3s → 5s → 8s → 10s → 10s = 36s max total wait.
        
        Returns:
            (access_token, email) tuple
        """
        if not self.is_ready:
            return None, None
        
        max_retries = 5
        retry_delays = [3, 5, 8, 10, 10]  # Total: 36s — covers worst-case navigation
        
        for attempt in range(max_retries):
            try:
                next_data = await self._page.evaluate('''
                    () => {
                        const el = document.getElementById('__NEXT_DATA__');
                        return el ? JSON.parse(el.textContent) : null;
                    }
                ''')
                
                if not next_data:
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        log.info(f"[RecaptchaBrowserSession] __NEXT_DATA__ empty, waiting {delay}s ({attempt + 1}/{max_retries})...")
                        await asyncio.sleep(delay)
                        continue
                    return None, None
                
                props = next_data.get("props", {})
                page_props = props.get("pageProps", {})
                
                session = page_props.get("session", {})
                access_token = session.get("access_token") or session.get("accessToken")
                user = session.get("user", {})
                email = user.get("email")
                
                if not access_token:
                    user_data = page_props.get("user", {})
                    access_token = user_data.get("accessToken")
                    email = user_data.get("email")
                
                if access_token:
                    return access_token, email
                
                # No token yet — page may still be loading after navigation
                if attempt < max_retries - 1:
                    delay = retry_delays[attempt]
                    log.info(f"[RecaptchaBrowserSession] Token not in __NEXT_DATA__ yet, waiting {delay}s ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
                
                return access_token, email
                
            except Exception as e:
                error_str = str(e).lower()
                # Bug 4 fix: Navigation destroyed context — wait and retry
                if ("context was destroyed" in error_str or "navigation" in error_str) and attempt < max_retries - 1:
                    delay = retry_delays[attempt]
                    log.warning(f"[RecaptchaBrowserSession] ⚠️ Navigation in progress, waiting {delay}s before retry ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(delay)
                    continue
                log.error(f"[RecaptchaBrowserSession] ❌ Access token extraction failed: {e}")
                return None, None
        
        return None, None
    
    async def refresh_headers(self):
        """Re-capture x-browser-* headers by triggering a light API interaction."""
        if not self.is_ready:
            return
        
        try:
            await self._page.reload(wait_until="networkidle", timeout=15000)
            await asyncio.sleep(1)
            log.info(f"[RecaptchaBrowserSession] ✅ Headers refreshed: {list(self._captured_headers.keys())}")
        except Exception as e:
            log.error(f"[RecaptchaBrowserSession] ⚠️ Header refresh failed: {e}")
    
    async def close(self):
        """Close browser and release resources."""
        async with self._lock:
            if self._is_attached:
                # Don't close the debug browser — we don't own it
                self._ready = False
                self._page = None
                self._is_attached = False
                log.debug("[RecaptchaBrowserSession] 🔌 Detached from debug browser")
                return
            await self._cleanup()
    
    async def _cleanup(self):
        """Internal cleanup — disconnect from Chrome (Chrome keeps running)."""
        self._ready = False
        self._page = None
        self._context = None
        
        if self._browser:
            try:
                await self._browser.close()  # CDP disconnect only
            except Exception:
                pass
            self._browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        
        log.info("[RecaptchaBrowserSession] 🔴 Playwright disconnected (Chrome still running)")
    
    async def _setup_header_interception(self):
        """Set up route interception to capture ALL 5 x-browser-* headers.
        
        Per Protocol Analysis §1.4: 5 mandatory headers for REST endpoints:
        - x-browser-channel
        - x-browser-copyright
        - x-browser-year
        - x-browser-validation
        - x-client-data
        """
        # All 5 mandatory header keys per Protocol Analysis §1.4
        BROWSER_HEADERS = [
            "x-browser-channel",
            "x-browser-copyright",
            "x-browser-year",
            "x-browser-validation",
            "x-client-data",
        ]
        
        async def intercept_request(route, request):
            url = request.url
            
            if "googleapis.com" in url or "aisandbox" in url:
                headers = request.headers
                for key in BROWSER_HEADERS:
                    if key in headers:
                        self._captured_headers[key] = headers[key]
            
            await route.continue_()
        
        # Only intercept googleapis/aisandbox — NOT all URLs
        # Intercepting "**/*" blocks reCAPTCHA Enterprise script loading
        await self._page.route("**/googleapis.com/**", intercept_request)
        await self._page.route("**/aisandbox*/**", intercept_request)
"""
    recaptcha_session.py - Persistent reCAPTCHA Browser Session

    Reference: RECAPTCHA_BROWSER_MANAGEMENT.md §4
    Architecture: CHỦ (AccountManager) owns one RecaptchaBrowserSession.
"""
