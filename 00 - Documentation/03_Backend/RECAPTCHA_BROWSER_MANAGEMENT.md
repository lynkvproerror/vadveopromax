# 🔐 reCAPTCHA Token Retrieval & Browser Session Management

**Location**: `03_Backend/RECAPTCHA_BROWSER_MANAGEMENT.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-03

---

## 1. Overview

VEO API sử dụng **reCAPTCHA Enterprise** để bảo vệ các endpoint. Hầu hết operations yêu cầu token hợp lệ.

### Operations Requiring reCAPTCHA

| Operation | reCAPTCHA Required | Notes |
|-----------|-------------------|-------|
| `CMD_GENERATE_VIDEO` | ✅ YES | T2V, I2V, F2V, R2V |
| `CMD_GENERATE_IMAGE` | ✅ YES | T2I, I2I |
| `CMD_UPSCALE_VIDEO` | ✅ YES | 1080p, 4K |
| `CMD_UPSCALE_IMAGE` | ✅ YES | 2K, 4K |
| `CMD_UPLOAD_IMAGE` | ❌ NO | Headers only |
| `CMD_CHECK_STATUS` | ❌ NO | Headers only |
| `CMD_DOWNLOAD` | ❌ NO | API Key + Headers |

---

## 2. Playwright Usage (Scope Limitation)

### What Playwright IS Used For:

| Use Case | Description |
|----------|-------------|
| **reCAPTCHA Token Extraction** | Execute reCAPTCHA challenge in headless browser |
| **Auth Cookie Extraction** | Get session cookies from Chrome profile |
| **Initial Login** | Handle Google OAuth flow (if needed) |

### What Playwright IS NOT Used For:

| NOT Used For | Reason |
|--------------|--------|
| ❌ Page navigation | API-first approach |
| ❌ Form filling | Direct API calls |
| ❌ Video downloads | HTTP requests |
| ❌ Image uploads | API endpoint |
| ❌ Status polling | REST API |

---

## 3. Browser Session Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    BROWSER SESSION MANAGER                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ Chrome Profile   │    │ Playwright       │                   │
│  │ (Persistent)     │────│ Browser Context  │                   │
│  │                  │    │ (Headless)       │                   │
│  │ • Cookies        │    │                  │                   │
│  │ • Auth tokens    │    │ • Page instance  │                   │
│  │ • Local storage  │    │ • reCAPTCHA exec │                   │
│  └──────────────────┘    └────────┬─────────┘                   │
│                                   │                              │
│                                   ▼                              │
│                    ┌──────────────────────────┐                  │
│                    │   reCAPTCHA Token        │                  │
│                    │   (Valid ~2 minutes)     │                  │
│                    └──────────────────────────┘                  │
│                                   │                              │
│                                   ▼                              │
│                    ┌──────────────────────────┐                  │
│                    │   API Request            │                  │
│                    │   + Token + Headers      │                  │
│                    └──────────────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation

### 4.1 Browser Manager Class

```python
from playwright.async_api import async_playwright
import asyncio

class BrowserManager:
    """
    Manages Playwright browser instance for reCAPTCHA token retrieval.
    
    NOT for page automation - only for token extraction.
    """
    
    def __init__(self, chrome_profile_path: str = None):
        self.chrome_profile_path = chrome_profile_path
        self.browser = None
        self.context = None
        self.page = None
    
    async def initialize(self, headless: bool = True):
        """
        Launch browser with persistent profile.
        """
        playwright = await async_playwright().start()
        
        if self.chrome_profile_path:
            # Use persistent context for cookie reuse
            self.context = await playwright.chromium.launch_persistent_context(
                user_data_dir=self.chrome_profile_path,
                headless=headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        else:
            # Standard browser
            self.browser = await playwright.chromium.launch(headless=headless)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
    
    async def get_recaptcha_token(self, site_key: str = None) -> str:
        """
        Execute reCAPTCHA and return token.
        
        Returns:
            str: reCAPTCHA token valid for ~2 minutes
        """
        # Navigate to VEO page if needed
        if "labs.google" not in self.page.url:
            await self.page.goto("https://labs.google.com/fx/tools/video-fx")
        
        # Get token from grecaptcha object
        token = await self.page.evaluate("""
            () => {
                return new Promise((resolve, reject) => {
                    grecaptcha.enterprise.execute(
                        '<SITE_KEY>',
                        {action: 'generate'}
                    ).then(token => resolve(token))
                     .catch(err => reject(err));
                });
            }
        """)
        
        return token
    
    async def extract_cookies(self) -> dict:
        """
        Extract session cookies for API requests.
        """
        cookies = await self.context.cookies()
        return {c['name']: c['value'] for c in cookies}
    
    async def close(self):
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
```

### 4.2 Token Cache

```python
import time

class TokenCache:
    """
    Cache reCAPTCHA tokens to minimize browser calls.
    """
    
    TOKEN_LIFETIME = 90  # seconds (conservative, actual ~120s)
    
    def __init__(self):
        self._token = None
        self._timestamp = 0
    
    @property
    def is_valid(self) -> bool:
        return (
            self._token is not None and 
            time.time() - self._timestamp < self.TOKEN_LIFETIME
        )
    
    def get(self) -> str | None:
        if self.is_valid:
            return self._token
        return None
    
    def set(self, token: str):
        self._token = token
        self._timestamp = time.time()
    
    def invalidate(self):
        self._token = None
        self._timestamp = 0
```

---

## 5. Usage in VEO Engine

```python
class VEOEngine:
    """
    Main engine orchestrating API calls with reCAPTCHA.
    """
    
    def __init__(self):
        self.browser_manager = BrowserManager()
        self.token_cache = TokenCache()
        self.api_client = VEOAPIClient()
    
    async def generate_video(self, prompt: str, model: str) -> str:
        """
        Generate video with automatic token handling.
        """
        # Get cached or fresh token
        token = self.token_cache.get()
        if not token:
            token = await self.browser_manager.get_recaptcha_token()
            self.token_cache.set(token)
        
        # Make API call
        try:
            operation_id = await self.api_client.generate_video(
                prompt=prompt,
                model=model,
                recaptcha_token=token
            )
            return operation_id
        except RecaptchaExpiredError:
            # Token expired, get fresh one and retry
            self.token_cache.invalidate()
            token = await self.browser_manager.get_recaptcha_token()
            self.token_cache.set(token)
            
            return await self.api_client.generate_video(
                prompt=prompt,
                model=model,
                recaptcha_token=token
            )
```

---

## 6. Settings (TAB_07)

### Browser Options

| Setting | Values | Default |
|---------|--------|---------|
| Chrome Profile | Path / Auto-detect | Auto-detect |
| Headless Mode | On / Off | On |
| Connection Timeout | 10s - 60s | 30s |

### Anti-Detection

| Setting | Purpose |
|---------|---------|
| `use_persistent_profile` | Reuse cookies/session |
| `humanize_actions` | Random delays (100-500ms) |
| `disable_automation_flag` | Remove Playwright fingerprint |

---

## 7. Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `RecaptchaExpiredError` | Token > 2 min old | Get fresh token |
| `RecaptchaChallengeRequired` | Suspicious activity | Show browser, manual solve |
| `ProfileNotFound` | Invalid Chrome path | Prompt user to select |
| `BrowserCrash` | Resource exhaustion | Restart browser |

---

## Cross-References

- [API_ENDPOINTS.md](../Research/reference/API_ENDPOINTS.md) - Full API documentation
- [PAYLOAD_SCHEMAS.md](../Research/reference/PAYLOAD_SCHEMAS.md) - Request/response formats
- [TAB_07_SETTINGS.md](../01_UI_UX/TAB_07_SETTINGS.md) - Browser settings UI
