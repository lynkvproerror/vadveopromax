"""
VEO Pro Max - Token Extractor

Unified extraction of all required tokens from headless browser session.

Reference: TOKEN_SECURITY.md (Methods C, D, and Unified Flow)

Tokens extracted:
1. Access Token - from __NEXT_DATA__ JSON
2. reCAPTCHA Token - from grecaptcha.execute()
3. x-browser-validation - from intercepted API request
4. x-client-data - from intercepted API request
"""

from typing import Optional, Dict, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import asyncio
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import TokenLifetime


# === DATA CLASSES ===

@dataclass
class ExtractedTokens:
    """All tokens extracted from browser session."""
    email: str
    access_token: str
    recaptcha_token: str = ""
    browser_validation: str = ""
    client_data: str = ""
    extracted_at: datetime = field(default_factory=datetime.now)
    expires_in: int = TokenLifetime.ACCESS_TOKEN
    
    @property
    def is_complete(self) -> bool:
        """Check if all critical tokens are present."""
        return bool(self.access_token and self.recaptcha_token and self.browser_validation)
    
    @property
    def missing_tokens(self) -> list[str]:
        """Get list of missing token names."""
        missing = []
        if not self.access_token:
            missing.append("access_token")
        if not self.recaptcha_token:
            missing.append("recaptcha_token")
        if not self.browser_validation:
            missing.append("browser_validation")
        return missing
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "email": self.email,
            "access_token": self.access_token,
            "recaptcha_token": self.recaptcha_token,
            "browser_validation": self.browser_validation,
            "client_data": self.client_data,
            "extracted_at": self.extracted_at.isoformat(),
            "expires_in": self.expires_in,
        }


# === TOKEN EXTRACTOR ===

class TokenExtractor:
    """
    Extract all required tokens from headless browser session.
    
    Tokens extracted:
    1. Access Token - from __NEXT_DATA__ JSON
    2. reCAPTCHA Token - from grecaptcha.execute()
    3. x-browser-validation - from intercepted API request
    4. x-client-data - from intercepted API request
    
    Usage:
        extractor = TokenExtractor()
        await extractor.initialize()
        tokens = await extractor.extract_all(profile_path)
        await extractor.close()
        
    Or use convenience function:
        tokens = await extract_tokens(profile_path)
    """
    
    # VEO URLs
    VEO_URL = "https://labs.google/fx/tools/flow"
    VEO_FALLBACK_URL = "https://aistudio.google.com/app/generate/video"
    
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._captured_headers: Dict[str, str] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize Playwright."""
        if self._initialized:
            return
        
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._initialized = True
        except ImportError:
            raise RuntimeError("Playwright not installed. Run: pip install playwright && playwright install chromium")
    
    async def close(self):
        """Close browser and Playwright."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        
        self._initialized = False
    
    async def extract_all(
        self,
        profile_path: str,
        headless: bool = True,
        timeout_ms: int = 30000,
    ) -> Optional[ExtractedTokens]:
        """
        Extract all tokens from browser session.
        
        Args:
            profile_path: Chrome profile directory
            headless: Run in headless mode
            timeout_ms: Navigation timeout
            
        Returns:
            ExtractedTokens if successful, None otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        self._captured_headers = {}
        
        try:
            # Launch browser with profile
            self._browser = await self._playwright.chromium.launch_persistent_context(
                profile_path,
                channel="chrome",  # Use real Chrome instead of Chromium
                headless=headless,
                timeout=timeout_ms,
                args=["--disable-blink-features=AutomationControlled"],
            )
            
            page = await self._browser.new_page()
            
            # Set up request interception for x-browser headers
            await self._setup_header_interception(page)
            
            # Navigate to VEO
            try:
                await page.goto(self.VEO_URL, wait_until="networkidle", timeout=timeout_ms)
            except Exception:
                # Try fallback URL
                await page.goto(self.VEO_FALLBACK_URL, wait_until="networkidle", timeout=timeout_ms)
            
            # 1. Extract access token from __NEXT_DATA__
            access_token, email = await self._extract_access_token(page)
            if not access_token:
                print("Failed to extract access token")
                return None
            
            # 2. Extract reCAPTCHA token
            recaptcha_token = await self._extract_recaptcha_token(page)
            if not recaptcha_token:
                print("Warning: Failed to extract reCAPTCHA token")
            
            # 3. Get captured x-browser headers
            browser_validation = self._captured_headers.get("x-browser-validation", "")
            client_data = self._captured_headers.get("x-client-data", "")
            
            # If headers not captured, trigger an API call
            if not browser_validation:
                await self._trigger_api_call(page)
                await asyncio.sleep(1)
                browser_validation = self._captured_headers.get("x-browser-validation", "")
                client_data = self._captured_headers.get("x-client-data", "")
            
            if not browser_validation:
                print("Warning: Failed to capture x-browser-validation header")
            
            return ExtractedTokens(
                email=email or "unknown@gmail.com",
                access_token=access_token,
                recaptcha_token=recaptcha_token or "",
                browser_validation=browser_validation,
                client_data=client_data,
                extracted_at=datetime.now(),
            )
            
        except Exception as e:
            print(f"Token extraction failed: {e}")
            return None
        finally:
            if self._browser:
                await self._browser.close()
                self._browser = None
    
    async def _setup_header_interception(self, page):
        """Set up route interception to capture x-browser headers."""
        
        async def intercept_request(route, request):
            url = request.url
            
            # Capture headers from googleapis.com requests
            if "googleapis.com" in url or "aisandbox" in url:
                headers = request.headers
                if "x-browser-validation" in headers:
                    self._captured_headers["x-browser-validation"] = headers["x-browser-validation"]
                if "x-client-data" in headers:
                    self._captured_headers["x-client-data"] = headers["x-client-data"]
            
            await route.continue_()
        
        await page.route("**/*", intercept_request)
    
    async def _extract_access_token(self, page) -> tuple[Optional[str], Optional[str]]:
        """Extract access token from __NEXT_DATA__ JSON."""
        try:
            next_data = await page.evaluate('''
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    return el ? JSON.parse(el.textContent) : null;
                }
            ''')
            
            if not next_data:
                return None, None
            
            # Navigate JSON structure - try multiple paths
            props = next_data.get("props", {})
            page_props = props.get("pageProps", {})
            
            # Path 1: session.access_token
            session = page_props.get("session", {})
            access_token = session.get("access_token") or session.get("accessToken")
            user = session.get("user", {})
            email = user.get("email")
            
            # Path 2: user.accessToken
            if not access_token:
                user_data = page_props.get("user", {})
                access_token = user_data.get("accessToken")
                email = user_data.get("email")
            
            # Path 3: dehydratedState
            if not access_token:
                dehydrated = page_props.get("dehydratedState", {})
                queries = dehydrated.get("queries", [])
                for query in queries:
                    state = query.get("state", {})
                    data = state.get("data", {})
                    if "accessToken" in data:
                        access_token = data["accessToken"]
                        break
            
            return access_token, email
            
        except Exception as e:
            print(f"Access token extraction failed: {e}")
            return None, None
    
    async def _extract_recaptcha_token(self, page) -> Optional[str]:
        """Extract reCAPTCHA v3 token by calling grecaptcha.execute()."""
        try:
            # Wait for reCAPTCHA to load
            try:
                await page.wait_for_function(
                    "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'",
                    timeout=10000
                )
            except Exception:
                print("grecaptcha not available on page")
                return None
            
            # Find site key and execute
            token = await page.evaluate('''
                async () => {
                    try {
                        // Find site key from page
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
                        
                        // Method 2: From grecaptcha.getResponse container
                        if (!siteKey) {
                            const containers = document.querySelectorAll('[data-sitekey]');
                            if (containers.length > 0) {
                                siteKey = containers[0].getAttribute('data-sitekey');
                            }
                        }
                        
                        // Method 3: Fallback (may need update)
                        if (!siteKey) {
                            siteKey = '6LfV2HQqAAAAAFY1I8F0WVK3i3Qlu9G4e_a7wPzR';
                        }
                        
                        // Execute and get token
                        return await grecaptcha.execute(siteKey, {action: 'generate'});
                    } catch (e) {
                        console.error('reCAPTCHA error:', e);
                        return null;
                    }
                }
            ''')
            
            return token
            
        except Exception as e:
            print(f"reCAPTCHA extraction failed: {e}")
            return None
    
    async def _trigger_api_call(self, page):
        """Trigger an API call to capture headers if not already captured."""
        try:
            # Wait for any network activity
            await page.wait_for_timeout(2000)
            
            # Try to trigger an action that makes API call
            try:
                await page.click('button:has-text("Generate")', timeout=3000)
            except Exception:
                pass
            
            try:
                await page.click('[aria-label="Generate"]', timeout=2000)
            except Exception:
                pass
            
            await page.wait_for_timeout(1000)
            
        except Exception:
            pass
    
    def extract_all_sync(self, profile_path: str, headless: bool = True) -> Optional[ExtractedTokens]:
        """Synchronous wrapper for extract_all."""
        async def run():
            await self.initialize()
            try:
                return await self.extract_all(profile_path, headless=headless)
            finally:
                await self.close()
        
        return asyncio.run(run())


# === CONVENIENCE FUNCTIONS ===

async def extract_tokens(profile_path: str, headless: bool = True) -> Optional[ExtractedTokens]:
    """
    Convenience function to extract all tokens.
    
    Args:
        profile_path: Chrome profile directory (e.g. "C:/Users/xxx/AppData/Local/Google/Chrome/User Data/Default")
        headless: Run browser headless
        
    Returns:
        ExtractedTokens with all tokens, or None if failed
        
    Example:
        tokens = await extract_tokens("C:/Users/xxx/Chrome/User Data/Default")
        if tokens:
            print(f"Access Token: {tokens.access_token[:20]}...")
            print(f"Complete: {tokens.is_complete}")
    """
    extractor = TokenExtractor()
    await extractor.initialize()
    try:
        return await extractor.extract_all(profile_path, headless=headless)
    finally:
        await extractor.close()


def extract_tokens_sync(profile_path: str, headless: bool = True) -> Optional[ExtractedTokens]:
    """
    Synchronous convenience function.
    
    Args:
        profile_path: Chrome profile directory
        headless: Run browser headless
        
    Returns:
        ExtractedTokens with all tokens, or None if failed
    """
    return asyncio.run(extract_tokens(profile_path, headless=headless))


# === HAR FALLBACK ===

def extract_headers_from_har(har_path: str) -> Dict[str, str]:
    """
    Extract x-browser headers from HAR file.
    
    Fallback when live extraction fails.
    
    Args:
        har_path: Path to HAR file
        
    Returns:
        Dict with x-browser-validation and x-client-data
    """
    try:
        with open(har_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        result = {}
        
        for entry in data.get('log', {}).get('entries', []):
            request = entry.get('request', {})
            url = request.get('url', '')
            
            if 'googleapis.com' not in url and 'aisandbox' not in url:
                continue
            
            for header in request.get('headers', []):
                name = header.get('name', '').lower()
                value = header.get('value', '')
                
                if name == 'x-browser-validation':
                    result['x-browser-validation'] = value
                elif name == 'x-client-data':
                    result['x-client-data'] = value
            
            if 'x-browser-validation' in result:
                break
        
        return result
        
    except Exception as e:
        print(f"HAR extraction failed: {e}")
        return {}
