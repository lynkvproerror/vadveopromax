"""
VEO Pro Max - Cookie Validator

Reference: SESSION_06_WORKFLOWS_SECURITY.md
Role: Validate cookies before use
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class CookieStatus(str, Enum):
    """Cookie validation status."""
    VALID = "valid"         # Cookie works, VEO accessible
    EXPIRED = "expired"     # Token expired, needs refresh
    INVALID = "invalid"     # Bad cookie, needs re-login
    UNKNOWN = "unknown"     # Could not verify


@dataclass
class CookieValidationResult:
    """Result of cookie validation."""
    email: str
    status: CookieStatus
    message: str
    has_veo_access: bool = False
    subscription_type: Optional[str] = None
    validated_at: datetime = field(default_factory=datetime.now)


class CookieValidator:
    """Validate cookies for VEO access.
    
    Features:
    - XPath detection for login page
    - VEO Flow indicators
    - Parallel validation
    """
    
    # Login page indicators (means cookie is invalid/expired)
    LOGIN_PAGE_PATTERNS = [
        "signin/identifier",
        "accounts.google.com",
        "Sign in - Google Accounts",
        "Choose an account",
    ]
    
    # VEO access indicators (means cookie is valid)
    VEO_ACCESS_PATTERNS = [
        "aistudio.google.com/app/generate",
        "Generate videos",
        "Video FX",
        "Veo",
    ]
    
    # XPath selectors for page elements
    XPATHS = {
        "login_form": "//form[@id='gaia_loginform']",
        "email_field": "//input[@type='email']",
        "password_field": "//input[@type='password']",
        "veo_sidebar": "//div[contains(@class, 'video-generation')]",
        "generate_button": "//button[contains(text(), 'Generate')]",
    }
    
    def __init__(self):
        self._playwright_available = False
        self._browser = None
    
    async def validate_cookie(
        self,
        email: str,
        profile_path: str,
        timeout_ms: int = 30000,
    ) -> CookieValidationResult:
        """Validate a single cookie.
        
        Args:
            email: Account email
            profile_path: Path to Chrome profile
            timeout_ms: Navigation timeout in ms
        
        Returns:
            CookieValidationResult
        """
        try:
            # Try to import playwright
            from playwright.async_api import async_playwright
            self._playwright_available = True
        except ImportError:
            return CookieValidationResult(
                email=email,
                status=CookieStatus.UNKNOWN,
                message="Playwright not installed",
            )
        
        try:
            async with async_playwright() as p:
                # Launch with existing profile
                browser = await p.chromium.launch_persistent_context(
                    profile_path,
                    channel="chrome",  # Use real Chrome instead of Chromium
                    headless=True,
                    timeout=timeout_ms,
                )
                
                page = await browser.new_page()
                
                # Navigate to AI Studio
                try:
                    await page.goto(
                        "https://aistudio.google.com/app/generate/video",
                        wait_until="networkidle",
                        timeout=timeout_ms,
                    )
                except Exception as e:
                    await browser.close()
                    return CookieValidationResult(
                        email=email,
                        status=CookieStatus.UNKNOWN,
                        message=f"Navigation failed: {str(e)[:100]}",
                    )
                
                # Check page content
                content = await page.content()
                url = page.url
                
                await browser.close()
                
                # Analyze result
                return self._analyze_page(email, url, content)
                
        except Exception as e:
            return CookieValidationResult(
                email=email,
                status=CookieStatus.UNKNOWN,
                message=f"Error: {str(e)[:100]}",
            )
    
    def _analyze_page(
        self,
        email: str,
        url: str,
        content: str,
    ) -> CookieValidationResult:
        """Analyze page to determine cookie status."""
        url_lower = url.lower()
        content_lower = content.lower()
        
        # Check for login page
        for pattern in self.LOGIN_PAGE_PATTERNS:
            if pattern.lower() in url_lower or pattern.lower() in content_lower:
                return CookieValidationResult(
                    email=email,
                    status=CookieStatus.EXPIRED,
                    message="Redirected to login page",
                    has_veo_access=False,
                )
        
        # Check for VEO access
        veo_found = False
        for pattern in self.VEO_ACCESS_PATTERNS:
            if pattern.lower() in url_lower or pattern.lower() in content_lower:
                veo_found = True
                break
        
        if veo_found:
            return CookieValidationResult(
                email=email,
                status=CookieStatus.VALID,
                message="VEO access confirmed",
                has_veo_access=True,
            )
        
        # Unknown state
        return CookieValidationResult(
            email=email,
            status=CookieStatus.UNKNOWN,
            message="Could not determine VEO access",
            has_veo_access=False,
        )
    
    async def validate_all(
        self,
        cookies: List[Dict[str, str]],  # [{"email": ..., "profile_path": ...}, ...]
        max_parallel: int = 3,
    ) -> List[CookieValidationResult]:
        """Validate multiple cookies in parallel.
        
        Args:
            cookies: List of cookie configs
            max_parallel: Max concurrent validations
        
        Returns:
            List of CookieValidationResult
        """
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def validate_with_semaphore(cookie):
            async with semaphore:
                return await self.validate_cookie(
                    email=cookie["email"],
                    profile_path=cookie["profile_path"],
                )
        
        tasks = [validate_with_semaphore(c) for c in cookies]
        return await asyncio.gather(*tasks)
    
    def validate_cookie_sync(
        self,
        email: str,
        profile_path: str,
    ) -> CookieValidationResult:
        """Synchronous wrapper for cookie validation."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.validate_cookie(email, profile_path)
            )
        finally:
            loop.close()
    
    @staticmethod
    def check_login_indicators(page_content: str) -> bool:
        """Quick check if page shows login indicators."""
        content_lower = page_content.lower()
        return any(
            pattern.lower() in content_lower
            for pattern in CookieValidator.LOGIN_PAGE_PATTERNS
        )
    
    @staticmethod
    def check_veo_indicators(page_content: str) -> bool:
        """Quick check if page shows VEO access."""
        content_lower = page_content.lower()
        return any(
            pattern.lower() in content_lower
            for pattern in CookieValidator.VEO_ACCESS_PATTERNS
        )
