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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# === TOKEN CACHE ===

class TokenCache:
    """Cache reCAPTCHA tokens to minimize browser calls.
    
    Reference: RECAPTCHA_BROWSER_MANAGEMENT.md §4.2
    """
    
    TOKEN_LIFETIME = 90  # seconds (conservative, actual ~120s)
    
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
    VEO_FALLBACK_URL = "https://aistudio.google.com/app/generate/video"
    
    def __init__(self, profile_path: str):
        self._profile_path = profile_path
        self._playwright = None
        self._context = None  # BrowserContext (persistent)
        self._page = None
        self._ready = False
        self._captured_headers: Dict[str, str] = {}
        self._lock = asyncio.Lock()
    
    @property
    def is_ready(self) -> bool:
        return self._ready and self._page is not None
    
    @property
    def captured_headers(self) -> Dict[str, str]:
        """Return captured x-browser-* headers."""
        return dict(self._captured_headers)
    
    async def ensure_ready(self, headless: bool = True, timeout_ms: int = 30000):
        """Open browser and navigate to VEO page if not already ready.
        
        Idempotent — safe to call multiple times.
        """
        async with self._lock:
            if self._ready:
                return
            
            try:
                from playwright.async_api import async_playwright
                
                self._playwright = await async_playwright().start()
                self._context = await self._playwright.chromium.launch_persistent_context(
                    self._profile_path,
                    channel="chrome",
                    headless=headless,
                    timeout=timeout_ms,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                
                self._page = await self._context.new_page()
                
                # Set up header interception
                await self._setup_header_interception()
                
                # Navigate to VEO
                try:
                    await self._page.goto(self.VEO_URL, wait_until="networkidle", timeout=timeout_ms)
                except Exception:
                    await self._page.goto(self.VEO_FALLBACK_URL, wait_until="networkidle", timeout=timeout_ms)
                
                self._ready = True
                print(f"[RecaptchaBrowserSession] ✅ Browser ready for {Path(self._profile_path).name}")
                
            except Exception as e:
                print(f"[RecaptchaBrowserSession] ❌ Failed to start browser: {e}")
                await self._cleanup()
                raise
    
    async def get_recaptcha_token(self) -> Optional[str]:
        """Execute grecaptcha and return fresh token.
        
        Fast (~100-500ms) because browser is already on VEO page.
        
        Returns:
            str: reCAPTCHA token valid for ~120s, or None if failed
        """
        if not self.is_ready:
            print("[RecaptchaBrowserSession] ⚠️ Browser not ready, call ensure_ready() first")
            return None
        
        try:
            # Wait for grecaptcha if needed (usually already loaded)
            try:
                await self._page.wait_for_function(
                    "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'",
                    timeout=5000
                )
            except Exception:
                # Try reloading page
                print("[RecaptchaBrowserSession] ⚠️ grecaptcha not found, reloading page...")
                try:
                    await self._page.reload(wait_until="networkidle", timeout=15000)
                    await self._page.wait_for_function(
                        "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'",
                        timeout=10000
                    )
                except Exception:
                    print("[RecaptchaBrowserSession] ❌ grecaptcha still not available after reload")
                    return None
            
            token = await self._page.evaluate('''
                async () => {
                    try {
                        let siteKey = null;
                        
                        // Method 1: From script src
                        const scripts = document.getElementsByTagName('script');
                        for (const script of scripts) {
                            const src = script.src || '';
                            const match = src.match(/render=([^&]+)/);
                            if (match) {
                                siteKey = match[1];
                                break;
                            }
                        }
                        
                        // Method 2: From data-sitekey attribute
                        if (!siteKey) {
                            const containers = document.querySelectorAll('[data-sitekey]');
                            if (containers.length > 0) {
                                siteKey = containers[0].getAttribute('data-sitekey');
                            }
                        }
                        
                        // Method 3: Fallback
                        if (!siteKey) {
                            siteKey = '6LfV2HQqAAAAAFY1I8F0WVK3i3Qlu9G4e_a7wPzR';
                        }
                        
                        return await grecaptcha.execute(siteKey, {action: 'generate'});
                    } catch (e) {
                        console.error('reCAPTCHA error:', e);
                        return null;
                    }
                }
            ''')
            
            if token:
                print(f"[RecaptchaBrowserSession] ✅ reCAPTCHA token refreshed ({len(token)} chars)")
            else:
                print("[RecaptchaBrowserSession] ❌ grecaptcha.execute() returned null")
            
            return token
            
        except Exception as e:
            print(f"[RecaptchaBrowserSession] ❌ reCAPTCHA extraction failed: {e}")
            return None
    
    async def extract_access_token(self) -> tuple:
        """Extract access token from __NEXT_DATA__ (if page is alive).
        
        Returns:
            (access_token, email) tuple
        """
        if not self.is_ready:
            return None, None
        
        try:
            next_data = await self._page.evaluate('''
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    return el ? JSON.parse(el.textContent) : null;
                }
            ''')
            
            if not next_data:
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
            
            return access_token, email
            
        except Exception as e:
            print(f"[RecaptchaBrowserSession] ❌ Access token extraction failed: {e}")
            return None, None
    
    async def refresh_headers(self):
        """Re-capture x-browser-* headers by triggering a light API interaction."""
        if not self.is_ready:
            return
        
        try:
            await self._page.reload(wait_until="networkidle", timeout=15000)
            await asyncio.sleep(1)
            print(f"[RecaptchaBrowserSession] ✅ Headers refreshed: {list(self._captured_headers.keys())}")
        except Exception as e:
            print(f"[RecaptchaBrowserSession] ⚠️ Header refresh failed: {e}")
    
    async def close(self):
        """Close browser and release resources."""
        async with self._lock:
            await self._cleanup()
    
    async def _cleanup(self):
        """Internal cleanup — close context and playwright."""
        self._ready = False
        self._page = None
        
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        
        print("[RecaptchaBrowserSession] 🔴 Browser closed")
    
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
        
        await self._page.route("**/*", intercept_request)
"""
    recaptcha_session.py - Persistent reCAPTCHA Browser Session

    Reference: RECAPTCHA_BROWSER_MANAGEMENT.md §4
    Architecture: CHỦ (AccountManager) owns one RecaptchaBrowserSession.
"""
