"""
VEO Pro Max - Profiles Controller

Reference: ACCOUNT_SESSION_MANAGEMENT.md, WORKFLOW_BROWSER_SESSION.md
Role: CRUD operations for Chrome profiles, JSON persistence
"""

from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession, SubscriptionType, PaygateTier


@dataclass
class ChromeProfile:
    """Chrome profile data for account management."""
    
    email: str
    display_name: str = ""
    profile_path: str = ""
    sku: str = "WS_FREEMIUM"  # WS_ULTRA, WS_PRO, WS_FREEMIUM
    paygate_tier: str = "PAYGATE_TIER_NOT_PAID"
    credits: int = 0
    is_ready: bool = False
    last_used: Optional[str] = None
    created_at: Optional[str] = None
    # New fields for dual login
    login_method: str = "oauth"  # "oauth" or "browser"
    browser_profile_path: str = ""  # Path to saved Chromium profile for browser login
    subscription_fetched: bool = False  # True if subscription was successfully fetched
    token_expires_at: Optional[str] = None  # ISO datetime when token expires (for status display)
    is_enabled: bool = True  # Account participates in rotation when generating
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.display_name:
            self.display_name = self.email.split("@")[0]
    
    @property
    def tier_display(self) -> str:
        """Get display name for tier."""
        # OAuth login without fetched subscription shows Wait
        if self.login_method == "oauth" and not self.subscription_fetched:
            return "⏳ Wait"
        
        tier_map = {
            "WS_ULTRA": "🚀 Ultra",
            "WS_PRO": "💎 Pro",
            "WS_FREEMIUM": "👤 Free",
        }
        return tier_map.get(self.sku, "👤 Free")
    
    @property
    def credits_display(self) -> str:
        """Get display for credits."""
        if self.login_method == "oauth" and not self.subscription_fetched:
            return "N/A"
        return str(self.credits)
    
    @property
    def status_display(self) -> str:
        """Get display status with detailed token state.
        
        Status priority:
        1. 🔴 Expired - Token đã hết hạn, cần login lại
        2. 🟠 Expiring - Token sắp hết hạn (< 5 phút)
        3. 🟡 Login - Chưa đăng nhập hoặc chưa có token
        4. 🟢 Ready - Sẵn sàng sử dụng
        """
        # Check token expiry if available
        if self.token_expires_at:
            try:
                expires = datetime.fromisoformat(self.token_expires_at)
                now = datetime.now()
                time_left = (expires - now).total_seconds()
                
                if time_left <= 0:
                    return "🔴 Expired"
                elif time_left < 5 * 60:  # < 5 minutes
                    return "🟠 Expiring"
            except (ValueError, TypeError):
                pass
        
        # Fallback to is_ready check
        if not self.is_ready:
            return "🟡 Login"
        return "🟢 Ready"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChromeProfile":
        """Create from dictionary."""
        # Handle legacy profiles without new fields
        if "login_method" not in data:
            data["login_method"] = "oauth"
        if "browser_profile_path" not in data:
            data["browser_profile_path"] = ""
        if "subscription_fetched" not in data:
            data["subscription_fetched"] = False
        if "token_expires_at" not in data:
            data["token_expires_at"] = None
        if "is_enabled" not in data:
            data["is_enabled"] = True  # Default enabled for legacy profiles
        return cls(**data)


class ProfilesController:
    """Controller for Chrome profiles management.
    
    Responsibilities:
    - CRUD operations for profiles
    - JSON persistence (save/load)
    - Profile validation
    - Status updates
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize controller.
        
        Args:
            storage_path: Path to JSON storage file. 
                         Defaults to config/profiles.json
        """
        if storage_path is None:
            storage_path = Path(__file__).parent.parent / "config" / "profiles.json"
        
        self.storage_path = Path(storage_path)
        self._profiles: List[ChromeProfile] = []
        self._callbacks: Dict[str, Callable] = {}
        
        # Ensure directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing profiles
        self.load_profiles()
    
    def set_callbacks(
        self,
        on_profiles_changed: Optional[Callable[[], None]] = None,
        on_profile_status_changed: Optional[Callable[[str, bool], None]] = None,
    ):
        """Set UI callbacks."""
        if on_profiles_changed:
            self._callbacks["profiles_changed"] = on_profiles_changed
        if on_profile_status_changed:
            self._callbacks["status_changed"] = on_profile_status_changed
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    def get_all_profiles(self) -> List[Dict[str, Any]]:
        """Get all profiles for UI display.
        
        Returns list of dicts with UI-friendly format.
        """
        return [
            {
                "email": p.email,
                "display_name": p.display_name,
                "tier": p.tier_display,
                "credits": p.credits_display,  # Use display property (shows N/A for OAuth)
                "status": p.status_display,
                "is_ready": p.is_ready,
                "profile_path": p.profile_path,
                "login_method": p.login_method,  # "oauth" or "browser"
            }
            for p in self._profiles
        ]
    
    def get_profile(self, email: str) -> Optional[ChromeProfile]:
        """Get profile by email."""
        for p in self._profiles:
            if p.email == email:
                return p
        return None
    
    def add_profile(self, email: str, profile_path: str, display_name: str = "", is_ready: bool = False, notify: bool = True) -> bool:
        """Add new Chrome profile.
        
        Args:
            email: Google account email
            profile_path: Path to Chrome user data directory
            display_name: Optional display name
            is_ready: Whether session is ready (default False)
            notify: Whether to notify UI callbacks (set False from background thread)
            
        Returns:
            True if added successfully
        """
        # Check for duplicate
        if self.get_profile(email):
            print(f"[ProfilesController] Profile already exists: {email}")
            return False
        
        profile = ChromeProfile(
            email=email,
            display_name=display_name or email.split("@")[0],
            profile_path=profile_path,
            is_ready=is_ready,
        )
        
        self._profiles.append(profile)
        self.save_profiles()
        if notify:
            self._notify("profiles_changed")
        
        print(f"[ProfilesController] Added profile: {email}")
        return True
    
    def remove_profile(self, email: str) -> bool:
        """Remove profile by email.
        
        Returns:
            True if removed successfully
        """
        for i, p in enumerate(self._profiles):
            if p.email == email:
                self._profiles.pop(i)
                self.save_profiles()
                self._notify("profiles_changed")
                print(f"[ProfilesController] Removed profile: {email}")
                return True
        
        print(f"[ProfilesController] Profile not found: {email}")
        return False
    
    def update_profile(self, email: str, **updates) -> bool:
        """Update profile fields.
        
        Args:
            email: Profile email
            **updates: Fields to update (sku, credits, is_ready, etc.)
            
        Returns:
            True if updated successfully
        """
        profile = self.get_profile(email)
        if not profile:
            return False
        
        for key, value in updates.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        profile.last_used = datetime.now().isoformat()
        self.save_profiles()
        self._notify("profiles_changed")
        return True
    
    def refresh_session(self, email: str) -> bool:
        """Refresh OAuth tokens for a profile.
        
        Uses TokenManager to refresh the access token.
        
        Args:
            email: Profile email
            
        Returns:
            True if refresh successful
        """
        from core.token_manager import get_token_manager
        
        profile = self.get_profile(email)
        if not profile:
            print(f"[ProfilesController] Profile not found: {email}")
            return False
        
        print(f"[ProfilesController] Refreshing session for {email}")
        
        try:
            # Get or create token manager
            token_manager = get_token_manager()
            
            # Force refresh token
            new_token = token_manager.get_valid_token(email)
            
            if new_token:
                profile.is_ready = True
                profile.last_used = datetime.now().isoformat()
                self.save_profiles()
                self._notify("profiles_changed")
                print(f"[ProfilesController] ✅ Session refreshed for {email}")
                return True
            else:
                profile.is_ready = False
                self.save_profiles()
                print(f"[ProfilesController] ❌ Failed to refresh session for {email}")
                return False
                
        except Exception as e:
            print(f"[ProfilesController] Refresh error: {e}")
            profile.is_ready = False
            self.save_profiles()
            return False
    
    def fetch_subscription_info(self, email: str) -> bool:
        """Fetch subscription info based on login method.
        
        OAuth Login:
        - Sets placeholder values (subscription_fetched=False)
        - Will be updated after first video render
        
        Browser Login:
        - Fetches real-time from Credits API using saved browser profile
        
        Args:
            email: Profile email
            
        Returns:
            True if successful
        """
        profile = self.get_profile(email)
        if not profile:
            print(f"[ProfilesController] Profile not found: {email}")
            return False
        
        print(f"[ProfilesController] Fetching subscription for {email} (method: {profile.login_method})")
        
        if profile.login_method == "browser" and profile.browser_profile_path:
            # Browser login → Fetch real-time
            return self._fetch_subscription_via_browser(profile)
        else:
            # OAuth login → Placeholder, will update after first render
            print(f"[ProfilesController] ℹ️ OAuth login - subscription will update after first video")
            from datetime import datetime
            profile.is_ready = True
            profile.subscription_fetched = False  # Will be True after first render
            profile.last_used = datetime.now().isoformat()
            self.save_profiles()
            print(f"[ProfilesController] ✅ Profile ready (Plan: {profile.tier_display})")
            return True
    
    def _fetch_subscription_via_browser(self, profile: "ChromeProfile") -> bool:
        """Fetch subscription using saved browser profile (for browser login).
        
        Uses Chromium with the saved profile to call Credits API.
        Chrome/Chromium auto-injects x-browser-* headers for Google domains.
        """
        try:
            # Check if we're inside an asyncio loop
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                if loop:
                    print(f"[ProfilesController] ⚠️ Inside asyncio loop - skipping sync subscription fetch")
                    print(f"[ProfilesController] Subscription will be fetched on next refresh")
                    return True  # Return success, subscription will be fetched later
            except RuntimeError:
                pass  # No running loop, safe to use sync API
            
            from playwright.sync_api import sync_playwright
            from datetime import datetime
            import os
            
            if not profile.browser_profile_path or not os.path.exists(profile.browser_profile_path):
                print(f"[ProfilesController] Browser profile path not found: {profile.browser_profile_path}")
                return False
            
            API_KEY = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"
            CREDITS_URL = f"https://aisandbox-pa.googleapis.com/v1/credits?key={API_KEY}"
            
            print(f"[ProfilesController] Launching browser with saved profile...")
            
            with sync_playwright() as p:
                # Headless mode for subscription refresh - no need to show browser
                context = p.chromium.launch_persistent_context(
                    user_data_dir=profile.browser_profile_path,
                    channel="chrome",  # Use real Chrome instead of Chromium
                    headless=True,  # Run in background
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check"
                    ]
                )
                
                page = context.new_page()
                
                try:
                    # Step 1: Navigate to labs.google to establish session
                    print(f"[ProfilesController] Navigating to labs.google/fx...")
                    page.goto("https://labs.google/fx", wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(2000)
                    
                    # Step 2: Fetch session API to get access_token
                    print(f"[ProfilesController] Fetching session API...")
                    session_result = page.evaluate("""
                        async () => {
                            try {
                                const resp = await fetch('https://labs.google/fx/api/auth/session', {
                                    credentials: 'include'
                                });
                                if (resp.ok) {
                                    return await resp.json();
                                }
                                return { error: resp.status };
                            } catch (e) {
                                return { error: e.message };
                            }
                        }
                    """)
                    
                    print(f"[ProfilesController] Session result: {session_result}")
                    
                    # Check for error or empty session (not logged in)
                    if not session_result or "error" in session_result:
                        print(f"[ProfilesController] ⚠️ Session API error: {session_result}")
                        profile.is_ready = True
                        profile.subscription_fetched = False
                        self.save_profiles()
                        return False
                    
                    access_token = session_result.get("accessToken") or session_result.get("access_token")
                    user_info = session_result.get("user", {})
                    
                    # Empty session = not logged in
                    if not access_token:
                        print(f"[ProfilesController] ⚠️ Not logged in - no accessToken in session")
                        print(f"[ProfilesController] ℹ️ Please login first using Browser button")
                        profile.is_ready = True
                        profile.subscription_fetched = False
                        self.save_profiles()
                        return False
                    
                    print(f"[ProfilesController] ✅ Got access token: {access_token[:20]}...")
                    
                    # Step 3: Call credits API with Bearer token
                    print(f"[ProfilesController] Fetching credits API with Bearer token...")
                    credits_result = page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch('https://aisandbox-pa.googleapis.com/v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY', {{
                                    headers: {{
                                        'Authorization': 'Bearer {access_token}'
                                    }},
                                    credentials: 'include'
                                }});
                                if (resp.ok) {{
                                    return await resp.json();
                                }}
                                return {{ error: resp.status }};
                            }} catch (e) {{
                                return {{ error: e.message }};
                            }}
                        }}
                    """)
                    
                    print(f"[ProfilesController] Credits result: {credits_result}")
                    
                    if credits_result and "error" not in credits_result:
                        profile.sku = credits_result.get("sku", "WS_FREEMIUM")
                        profile.credits = credits_result.get("credits", 0)
                        profile.paygate_tier = credits_result.get("userPaygateTier", "PAYGATE_TIER_NOT_PAID")
                        profile.is_ready = True
                        profile.subscription_fetched = True
                        profile.last_used = datetime.now().isoformat()
                        self.save_profiles()
                        
                        print(f"[ProfilesController] ✅ Success: {profile.tier_display}, Credits: {profile.credits}")
                        return True
                    else:
                        # Still have session, just no credits info
                        print(f"[ProfilesController] ⚠️ Credits API failed: {credits_result}")
                        profile.is_ready = True
                        profile.subscription_fetched = False
                        profile.last_used = datetime.now().isoformat()
                        self.save_profiles()
                        return False
                        
                finally:
                    context.close()
                    
        except Exception as e:
            import traceback
            print(f"[ProfilesController] Subscription fetch error: {e}")
            traceback.print_exc()
            return False
    
    def update_subscription_from_response(self, email: str, response: dict) -> bool:
        """Update subscription info from VEO API response.
        
        Called after video generation to update OAuth profiles with real subscription data.
        
        Args:
            email: Profile email
            response: VEO API response containing sku, credits, etc.
            
        Returns:
            True if updated
        """
        profile = self.get_profile(email)
        if not profile:
            return False
        
        updated = False
        
        # Check for subscription fields in response
        if "sku" in response:
            profile.sku = response["sku"]
            updated = True
        if "credits" in response:
            profile.credits = response["credits"]
            updated = True
        if "userPaygateTier" in response:
            profile.paygate_tier = response["userPaygateTier"]
            updated = True
        
        if updated:
            profile.subscription_fetched = True
            self.save_profiles()
            print(f"[ProfilesController] ✅ Subscription updated from API: {profile.tier_display}, Credits: {profile.credits}")
            self._notify("subscription_updated", email)
        
        return updated
    
    # =========================================================================
    # Browser Operations
    # =========================================================================
    
    def add_profile_via_browser(
        self, 
        timeout_seconds: int = 300
    ) -> Optional[str]:
        """Add new profile via Google OAuth Authorization Code flow.
        
        Mirrors Antigravity-Manager approach:
        1. Start localhost callback server
        2. Open Google OAuth URL in browser
        3. User logs in with Google account
        4. Google redirects to localhost with auth code
        5. Exchange code for access_token + refresh_token
        6. Get user info (email)
        7. Save profile with tokens
        
        Args:
            timeout_seconds: Max time to wait for login
            
        Returns:
            Email of created profile, or None if cancelled/failed
        """
        import uuid
        
        from core.oauth_server import run_oauth_flow, OAuthResult
        
        print("[ProfilesController] Starting Google OAuth flow...")
        
        # Generate unique profile folder for storing session data
        profile_folder = f"profile_{uuid.uuid4().hex[:8]}"
        profile_path = self.storage_path.parent / "browser_profiles" / profile_folder
        profile_path.mkdir(parents=True, exist_ok=True)
        
        print(f"[ProfilesController] Profile path: {profile_path}")
        
        try:
            # Run the complete OAuth flow
            result: OAuthResult = run_oauth_flow(timeout=timeout_seconds)
            
            if not result.success:
                print(f"[ProfilesController] OAuth failed: {result.error}")
                return None
            
            # Extract data from result
            email = result.user_info.email
            display_name = result.user_info.display_name
            access_token = result.token_response.access_token
            refresh_token = result.token_response.refresh_token
            expires_at = result.token_response.expires_at
            
            print(f"[ProfilesController] Logged in as: {email}")
            
            # Check if profile already exists
            existing = self.get_profile(email)
            if existing:
                # Update existing profile with new tokens
                print(f"[ProfilesController] Updating existing profile: {email}")
                existing.is_ready = True
                existing.last_used = datetime.now().isoformat()
                # Store tokens (will add token fields to ChromeProfile)
                self.save_profiles()
                # DO NOT call _notify here - we're in background thread!
                # UI will be refreshed via invokeMethod in tab_settings.py
                
                # Save tokens to separate secure storage
                self._save_tokens(email, access_token, refresh_token, expires_at)
                
                return email
            
            # Add new profile (notify=False because we're in background thread)
            success = self.add_profile(
                email=email,
                profile_path=str(profile_path),
                display_name=display_name,
                is_ready=True,
                notify=False  # Don't notify from background thread!
            )
            
            if success:
                print(f"[ProfilesController] ✅ Profile added: {email}")
                
                # Save tokens to separate secure storage
                self._save_tokens(email, access_token, refresh_token, expires_at)
                
                return email
            else:
                print(f"[ProfilesController] Failed to add profile: {email}")
                return None
                
        except Exception as e:
            print(f"[ProfilesController] OAuth flow error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def add_profile_via_browser_login(
        self, 
        timeout_seconds: int = 300
    ) -> Optional[str]:
        """Add new profile via browser login (user logs in manually).
        
        Flow:
        1. Create dedicated browser profile folder
        2. Launch visible Chromium browser
        3. Navigate to labs.google/fx
        4. User logs in with Google account manually
        5. Detect login success (email appears on page)
        6. Save browser profile for reuse
        7. Fetch subscription real-time
        
        Benefits over OAuth:
        - Full browser session with x-browser-* headers
        - Can fetch subscription in real-time
        - No scope limitations
        
        Args:
            timeout_seconds: Max time to wait for login
            
        Returns:
            Email of created profile, or None if cancelled/failed
        """
        import uuid
        
        print("[ProfilesController] Starting Browser Login flow...")
        
        # Check if we have an existing profile with browser_profile_path
        # If so, reuse it to maintain session
        profile_path = None
        existing_profiles = [p for p in self._profiles if p.browser_profile_path]
        
        if existing_profiles:
            # Use the most recently used profile's browser path
            existing_profiles.sort(key=lambda p: p.last_used or "", reverse=True)
            existing_path = Path(existing_profiles[0].browser_profile_path)
            if existing_path.exists():
                profile_path = existing_path
                print(f"[ProfilesController] Reusing existing browser profile: {profile_path}")
        
        if not profile_path:
            # Generate unique profile folder (first time login)
            profile_folder = f"browser_session_{uuid.uuid4().hex[:8]}"
            profile_path = self.storage_path.parent / "browser_profiles" / profile_folder
            profile_path.mkdir(parents=True, exist_ok=True)
            print(f"[ProfilesController] NEW browser profile path: {profile_path}")
        
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                # Launch VISIBLE browser for user to login
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_path),
                    channel="chrome",  # Use real Chrome instead of Chromium
                    headless=False,  # VISIBLE for user interaction
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--start-maximized"
                    ]
                )
                
                page = context.new_page()
                
                try:
                    # Navigate to labs.google/fx homepage
                    # The /api/auth/signin/google endpoint has aisandbox scope issues
                    print("[ProfilesController] Opening labs.google/fx...")
                    page.goto(
                        "https://labs.google/fx",
                        wait_until="networkidle",
                        timeout=30000
                    )
                    
                    # Wait for page to load
                    page.wait_for_timeout(2000)
                    
                    # Check if already logged in
                    current_url = page.url
                    print(f"[ProfilesController] Current URL: {current_url}")
                    
                    # Try to find Sign In button (user needs to click)
                    print("[ProfilesController] Looking for 'Sign In' button...")
                    
                    clicked = False
                    
                    # Try various selectors for the Sign In button
                    selectors = [
                        "#sign-in-now-button",
                        "button:has-text('Sign in')",
                        "button:has-text('Sign In')", 
                        "a:has-text('Sign in')",
                        "[data-testid='sign-in-button']",
                        "button:has-text('Get started')",
                    ]
                    
                    for selector in selectors:
                        try:
                            btn = page.locator(selector).first
                            if btn.count() > 0 and btn.is_visible():
                                btn.click(force=True)
                                clicked = True
                                print(f"[ProfilesController] ✅ Clicked: {selector}")
                                break
                        except Exception:
                            continue
                    
                    # Fallback: JavaScript click
                    if not clicked:
                        try:
                            page.evaluate("""
                                const btns = [...document.querySelectorAll('button, a, div[role="button"]')];
                                const signInBtn = btns.find(b => 
                                    b.textContent.toLowerCase().includes('sign in') || 
                                    b.id === 'sign-in-now-button'
                                );
                                if (signInBtn) signInBtn.click();
                            """)
                            clicked = True
                            print("[ProfilesController] ✅ Clicked via JavaScript")
                        except Exception as e:
                            print(f"[ProfilesController] JS click failed: {e}")
                    
                    if not clicked:
                        print("[ProfilesController] ℹ️ No Sign In button found - user may already be logged in or needs to click manually")
                    
                    if clicked:
                        # Wait for OAuth redirect
                        page.wait_for_timeout(3000)
                        print(f"[ProfilesController] Current URL: {page.url[:60]}...")
                        
                        if "accounts.google.com" in page.url:
                            print("[ProfilesController] ✅ Redirected to Google OAuth!")
                    
                    # Wait for user to login
                    print(f"[ProfilesController] ⏳ Waiting for login (max {timeout_seconds}s)...")
                    print("[ProfilesController] Please login with your Google account in the browser window")
                    
                    email = None
                    for i in range(timeout_seconds // 5):
                        page.wait_for_timeout(5000)
                        
                        # Try to find logged-in indicators
                        # Check for avatar/profile button that contains email or account info
                        try:
                            # Method 1: Check page URL for success
                            if "labs.google" in page.url and "accounts.google" not in page.url:
                                # Try to extract email from page
                                # Usually visible in header or settings
                                email_result = page.evaluate("""
                                    () => {
                                        // Try various selectors for email/account info
                                        const selectors = [
                                            '[data-email]',
                                            '[aria-label*="@"]',
                                            'a[href*="myaccount.google.com"]'
                                        ];
                                        for (const sel of selectors) {
                                            const el = document.querySelector(sel);
                                            if (el) {
                                                const email = el.getAttribute('data-email') || 
                                                              el.getAttribute('aria-label') || 
                                                              el.textContent;
                                                if (email && email.includes('@')) {
                                                    // Extract email from text
                                                    const match = email.match(/[\\w.-]+@[\\w.-]+\\.\\w+/);
                                                    if (match) return match[0];
                                                }
                                            }
                                        }
                                        return null;
                                    }
                                """)
                                
                                if email_result:
                                    email = email_result
                                    print(f"[ProfilesController] ✅ Detected login: {email}")
                                    break
                                
                                # Method 2: Try calling session API
                                session_result = page.evaluate("""
                                    async () => {
                                        try {
                                            const resp = await fetch('https://labs.google/fx/api/auth/session', {
                                                credentials: 'include'
                                            });
                                            if (resp.ok) {
                                                const data = await resp.json();
                                                return data.user?.email || null;
                                            }
                                        } catch (e) {}
                                        return null;
                                    }
                                """)
                                
                                if session_result:
                                    email = session_result
                                    print(f"[ProfilesController] ✅ Session detected: {email}")
                                    break
                                    
                        except Exception as e:
                            print(f"[ProfilesController] Detection check: {e}")
                        
                        print(f"[ProfilesController] Waiting... ({(i+1)*5}/{timeout_seconds}s)")
                    
                    if not email:
                        print("[ProfilesController] ❌ Login timeout or cancelled")
                        context.close()
                        return None
                    
                    # Wait for storage to sync before closing
                    print("[ProfilesController] Syncing browser storage...")
                    page.wait_for_timeout(2000)
                    
                    # Close browser - profile is saved
                    print(f"[ProfilesController] Closing browser. Profile path: {profile_path}")
                    context.close()
                    
                    # Check if profile already exists
                    existing = self.get_profile(email)
                    if existing:
                        print(f"[ProfilesController] Updating existing profile: {email}")
                        existing.login_method = "browser"
                        existing.browser_profile_path = str(profile_path)
                        existing.is_ready = True
                        existing.last_used = datetime.now().isoformat()
                        self.save_profiles()
                        
                        # Fetch subscription
                        self._fetch_subscription_via_browser(existing)
                        return email
                    
                    # Add new profile
                    success = self.add_profile(
                        email=email,
                        profile_path=str(profile_path),
                        display_name=email.split("@")[0],
                        is_ready=True,
                        notify=False
                    )
                    
                    if success:
                        # Update with browser-specific fields
                        profile = self.get_profile(email)
                        if profile:
                            profile.login_method = "browser"
                            profile.browser_profile_path = str(profile_path)
                            self.save_profiles()
                            
                            # Fetch subscription real-time
                            print("[ProfilesController] Fetching subscription...")
                            self._fetch_subscription_via_browser(profile)
                        
                        print(f"[ProfilesController] ✅ Browser profile added: {email}")
                        return email
                    else:
                        print(f"[ProfilesController] Failed to add profile: {email}")
                        return None
                        
                except Exception as e:
                    print(f"[ProfilesController] Browser login error: {e}")
                    import traceback
                    traceback.print_exc()
                    context.close()
                    return None
                    
        except Exception as e:
            print(f"[ProfilesController] Browser login flow error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def auto_login_with_credentials(
        self, 
        email: str,
        password: str,
        timeout_seconds: int = 120
    ) -> Optional[str]:
        """Auto-login with email/password credentials.
        
        Flow:
        1. Navigate to accounts.google.com
        2. Auto-fill email → Enter
        3. Auto-fill password → Enter
        4. Wait for redirect to labs.google
        5. Fetch session API
        6. Save profile
        
        Args:
            email: Google account email
            password: Google account password
            timeout_seconds: Max time to wait for login completion
            
        Returns:
            Email of created/updated profile, or None if failed
        """
        print(f"[ProfilesController] Starting Auto-Login for {email}...")
        
        # Get or create browser profile path
        profile_path = None
        existing_profiles = [p for p in self._profiles if p.browser_profile_path]
        
        if existing_profiles:
            existing_profiles.sort(key=lambda p: p.last_used or "", reverse=True)
            existing_path = Path(existing_profiles[0].browser_profile_path)
            if existing_path.exists():
                profile_path = existing_path
                print(f"[ProfilesController] Reusing browser profile: {profile_path}")
        
        if not profile_path:
            import uuid
            profile_folder = f"browser_session_{uuid.uuid4().hex[:8]}"
            profile_path = self.storage_path.parent / "browser_profiles" / profile_folder
            profile_path.mkdir(parents=True, exist_ok=True)
            print(f"[ProfilesController] NEW browser profile: {profile_path}")
        
        try:
            from playwright.sync_api import sync_playwright
            
            with sync_playwright() as p:
                # Launch visible browser (for CAPTCHA handling if needed)
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile_path),
                    channel="chrome",  # Use real Chrome instead of Chromium
                    headless=False,  # Visible for CAPTCHA/2FA
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--start-maximized"
                    ]
                )
                
                page = context.new_page()
                
                try:
                    # Step 1: Navigate to Google login
                    print("[ProfilesController] Navigating to accounts.google.com...")
                    page.goto("https://accounts.google.com", wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(2000)
                    
                    # Step 2: Fill email
                    print("[ProfilesController] Filling email...")
                    email_input = page.locator("#identifierId")
                    if email_input.count() > 0:
                        email_input.fill(email)
                        page.wait_for_timeout(500)
                        page.keyboard.press("Enter")
                        print("[ProfilesController] ✅ Email entered")
                    else:
                        print("[ProfilesController] ⚠️ Email input not found, trying alternative...")
                        # Try alternative selector
                        page.locator("input[type='email']").first.fill(email)
                        page.keyboard.press("Enter")
                    
                    # Wait for password page
                    page.wait_for_timeout(3000)
                    
                    # Step 3: Fill password
                    print("[ProfilesController] Filling password...")
                    password_input = page.locator("input[name='Passwd']")
                    
                    # Wait for password input to be visible
                    for _ in range(10):
                        if password_input.count() > 0 and password_input.is_visible():
                            break
                        page.wait_for_timeout(500)
                    
                    if password_input.count() > 0 and password_input.is_visible():
                        password_input.fill(password)
                        page.wait_for_timeout(500)
                        page.keyboard.press("Enter")
                        print("[ProfilesController] ✅ Password entered")
                    else:
                        print("[ProfilesController] ⚠️ Password input not found - may need manual input")
                        # Wait for user to handle manually
                        page.wait_for_timeout(10000)
                    
                    # Step 4: Wait for login completion (redirect away from accounts.google.com)
                    print(f"[ProfilesController] Waiting for login completion (max {timeout_seconds}s)...")
                    login_success = False
                    
                    for i in range(timeout_seconds // 5):
                        page.wait_for_timeout(5000)
                        current_url = page.url
                        print(f"[ProfilesController] Current URL: {current_url[:50]}...")
                        
                        # Check if redirected to labs.google or myaccount
                        if "accounts.google.com" not in current_url:
                            login_success = True
                            print("[ProfilesController] ✅ Login redirect detected!")
                            break
                        
                        # Check for error messages
                        error_visible = page.locator("[class*='error'], [class*='Error']").count() > 0
                        if error_visible:
                            print("[ProfilesController] ⚠️ Error detected on page")
                            
                        print(f"[ProfilesController] Waiting... ({(i+1)*5}/{timeout_seconds}s)")
                    
                    if not login_success:
                        print("[ProfilesController] ❌ Login timeout - check for CAPTCHA/2FA")
                        context.close()
                        return None
                    
                    # Step 5: Navigate to labs.google/fx/tools/flow and fetch session
                    print("[ProfilesController] Navigating to labs.google/fx/tools/flow...")
                    page.goto("https://labs.google/fx/tools/flow", wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(3000)
                    
                    # Step 6: Fetch session API
                    print("[ProfilesController] Fetching session API...")
                    session_result = page.evaluate("""
                        async () => {
                            try {
                                const resp = await fetch('https://labs.google/fx/api/auth/session', {
                                    credentials: 'include'
                                });
                                if (resp.ok) {
                                    return await resp.json();
                                }
                                return { error: resp.status };
                            } catch (e) {
                                return { error: e.message };
                            }
                        }
                    """)
                    
                    print(f"[ProfilesController] Session result: {session_result}")
                    
                    # Get access token
                    access_token = session_result.get("accessToken") or session_result.get("access_token")
                    user_info = session_result.get("user", {})
                    session_email = user_info.get("email", email)
                    
                    if not access_token:
                        print("[ProfilesController] ⚠️ No access token - session may not be valid")
                    
                    # Sync storage before close
                    print("[ProfilesController] Syncing browser storage...")
                    page.wait_for_timeout(2000)
                    
                    # Close browser
                    context.close()
                    
                    # Step 7: Save/update profile
                    existing = self.get_profile(session_email)
                    if existing:
                        print(f"[ProfilesController] Updating existing profile: {session_email}")
                        existing.login_method = "browser"
                        existing.browser_profile_path = str(profile_path)
                        existing.is_ready = True
                        existing.last_used = datetime.now().isoformat()
                        self.save_profiles()
                        
                        # Fetch subscription
                        self._fetch_subscription_via_browser(existing)
                        return session_email
                    
                    # Add new profile
                    success = self.add_profile(
                        email=session_email,
                        profile_path=str(profile_path),
                        display_name=session_email.split("@")[0],
                        is_ready=True,
                        notify=False
                    )
                    
                    if success:
                        profile = self.get_profile(session_email)
                        if profile:
                            profile.login_method = "browser"
                            profile.browser_profile_path = str(profile_path)
                            self.save_profiles()
                            
                            # Fetch subscription
                            print("[ProfilesController] Fetching subscription...")
                            self._fetch_subscription_via_browser(profile)
                        
                        print(f"[ProfilesController] ✅ Auto-login successful: {session_email}")
                        return session_email
                    else:
                        print(f"[ProfilesController] Failed to add profile: {session_email}")
                        return None
                        
                except Exception as e:
                    print(f"[ProfilesController] Auto-login error: {e}")
                    import traceback
                    traceback.print_exc()
                    context.close()
                    return None
                    
        except Exception as e:
            print(f"[ProfilesController] Auto-login flow error: {e}")
            import traceback
            traceback.print_exc()
            return None

    
    def _save_tokens(self, email: str, access_token: str, refresh_token: str, expires_at: float):
        """Save OAuth tokens for a profile.
        
        Stores tokens in tokens.json for auto-refresh capability.
        """
        tokens_path = self.storage_path.parent / "tokens.json"
        
        # Load existing tokens
        tokens = {}
        if tokens_path.exists():
            try:
                with open(tokens_path, 'r', encoding='utf-8') as f:
                    tokens = json.load(f)
            except:
                tokens = {}
        
        # Update tokens for this email
        tokens[email] = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "updated_at": datetime.now().isoformat()
        }
        
        # Save
        with open(tokens_path, 'w', encoding='utf-8') as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
        
        print(f"[ProfilesController] Tokens saved for {email}")
    
    def get_tokens(self, email: str) -> Optional[dict]:
        """Get stored tokens for an email."""
        tokens_path = self.storage_path.parent / "tokens.json"
        
        if not tokens_path.exists():
            return None
        
        try:
            with open(tokens_path, 'r', encoding='utf-8') as f:
                tokens = json.load(f)
                return tokens.get(email)
        except:
            return None
    
    def _create_oauth_landing_page(self, callback_url: str, profile_path: str) -> str:
        """Create OAuth landing page that guides user through login.
        
        Returns file:// URL to the landing page.
        """
        import tempfile
        import urllib.parse
        
        html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>VEO Pro Max - Đăng nhập Google</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }}
        .container {{
            text-align: center;
            padding: 50px;
            background: rgba(255,255,255,0.05);
            border-radius: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
            max-width: 500px;
        }}
        .icon {{ font-size: 72px; margin-bottom: 24px; }}
        h1 {{ font-size: 28px; margin-bottom: 16px; color: #60a5fa; }}
        .subtitle {{ color: #94a3b8; margin-bottom: 32px; font-size: 16px; }}
        .btn {{
            display: inline-block;
            padding: 16px 48px;
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
            color: white;
            font-size: 18px;
            font-weight: 600;
            text-decoration: none;
            border-radius: 12px;
            margin: 10px;
            transition: all 0.3s;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
        }}
        .btn:hover {{ transform: translateY(-2px); box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5); }}
        .btn-success {{
            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.4);
        }}
        .btn-success:hover {{ box-shadow: 0 6px 20px rgba(34, 197, 94, 0.5); }}
        .steps {{ text-align: left; margin: 24px 0; padding: 20px; background: rgba(0,0,0,0.2); border-radius: 12px; }}
        .step {{ padding: 8px 0; color: #e2e8f0; }}
        .step-num {{ color: #22c55e; font-weight: bold; margin-right: 8px; }}
        .divider {{ height: 1px; background: rgba(255,255,255,0.1); margin: 24px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🔐</div>
        <h1>Thêm tài khoản Google</h1>
        <div class="subtitle">Đăng nhập để sử dụng VEO Pro Max</div>
        
        <a href="https://aistudio.google.com/prompts/new_chat" target="_blank" class="btn" onclick="showStep2()">
            🚀 Mở AI Studio để đăng nhập
        </a>
        
        <div class="steps">
            <div class="step"><span class="step-num">1.</span> Nhấn nút trên để mở AI Studio</div>
            <div class="step"><span class="step-num">2.</span> Đăng nhập với tài khoản Google</div>
            <div class="step"><span class="step-num">3.</span> Quay lại tab này và nhấn "Hoàn tất"</div>
        </div>
        
        <div class="divider"></div>
        
        <a href="{callback_url}?profile_path={urllib.parse.quote(profile_path)}" class="btn btn-success">
            ✅ Tôi đã đăng nhập xong - Hoàn tất
        </a>
    </div>
    
    <script>
        function showStep2() {{
            // Optional: Show visual feedback
        }}
    </script>
</body>
</html>'''
        
        # Save to temp file
        html_path = Path(tempfile.gettempdir()) / f"veo_oauth_{profile_path.split('_')[-1]}.html"
        html_path.write_text(html_content, encoding='utf-8')
        
        return f"file:///{html_path}".replace("\\", "/")
    
    def _find_browser(self, preference: str = "auto") -> Optional[str]:
        """Find real browser executable.
        
        Args:
            preference: "chrome", "edge", "coccoc", or "auto"
            
        Returns:
            Path to browser executable or None
        """
        import os
        
        browser_paths = {
            "chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            ],
            "edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ],
            "coccoc": [
                r"C:\Program Files\CocCoc\Browser\Application\browser.exe",
                r"C:\Program Files (x86)\CocCoc\Browser\Application\browser.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\CocCoc\Browser\Application\browser.exe"),
            ],
        }
        
        # Order to try
        if preference == "auto":
            order = ["chrome", "coccoc", "edge"]
        else:
            order = [preference]
        
        for browser_name in order:
            paths = browser_paths.get(browser_name, [])
            for path in paths:
                if os.path.exists(path):
                    return path
        
        return None
    
    def _extract_email_from_profile(self, profile_path: Path) -> Optional[str]:
        """Extract email from browser profile cookies.
        
        Args:
            profile_path: Path to browser profile folder
            
        Returns:
            Email address or None
        """
        import sqlite3
        import shutil
        import tempfile
        import re
        import uuid
        
        # Chrome/Edge store cookies in SQLite database
        cookies_paths = [
            profile_path / "Default" / "Cookies",
            profile_path / "Default" / "Network" / "Cookies",
            profile_path / "Cookies",
        ]
        
        for cookies_file in cookies_paths:
            if cookies_file.exists():
                try:
                    # Copy to temp to avoid lock issues
                    temp_file = Path(tempfile.gettempdir()) / f"cookies_{uuid.uuid4().hex[:8]}.db"
                    shutil.copy2(cookies_file, temp_file)
                    
                    conn = sqlite3.connect(str(temp_file))
                    cursor = conn.cursor()
                    
                    # Try to find email in cookies
                    # Google sets cookies like GMAIL_AT, contains email info
                    cursor.execute("""
                        SELECT name, value, host_key FROM cookies 
                        WHERE host_key LIKE '%google%' OR host_key LIKE '%gmail%'
                    """)
                    
                    for name, value, host in cursor.fetchall():
                        # Look for email patterns in cookie values
                        if '@' in str(value):
                            match = re.search(r'[\w.-]+@[\w.-]+\.\w+', str(value))
                            if match:
                                conn.close()
                                temp_file.unlink(missing_ok=True)
                                return match.group(0)
                    
                    conn.close()
                    temp_file.unlink(missing_ok=True)
                    
                except Exception as e:
                    print(f"[ProfilesController] Cookie read error: {e}")
        
        # Alternative: Try to read from Local State or Preferences
        prefs_paths = [
            profile_path / "Default" / "Preferences",
            profile_path / "Local State",
        ]
        
        for prefs_file in prefs_paths:
            if prefs_file.exists():
                try:
                    import json
                    with open(prefs_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Look for email in account info
                    account_info = data.get('account_info', [])
                    if account_info and len(account_info) > 0:
                        email = account_info[0].get('email')
                        if email:
                            return email
                    
                    # Check signin info
                    signin = data.get('signin', {})
                    email = signin.get('email') or signin.get('account_id')
                    if email and '@' in email:
                        return email
                        
                except Exception as e:
                    print(f"[ProfilesController] Prefs read error: {e}")
        
        return None
    
    def verify_session(self, email: str, sku: str = None, credits: int = None) -> bool:
        """Verify and update session status.
        
        Called after user manually logs in to update profile status.
        
        Args:
            email: Profile email
            sku: Plan type (WS_ULTRA, WS_PRO, WS_FREEMIUM)
            credits: Remaining credits
        """
        profile = self.get_profile(email)
        if not profile:
            return False
        
        updates = {"is_ready": True}
        
        if sku:
            updates["sku"] = sku
        if credits is not None:
            updates["credits"] = credits
        
        self.update_profile(email, **updates)
        print(f"[ProfilesController] Session verified for: {email}")
        
        return True
    
    def mark_session_expired(self, email: str) -> bool:
        """Mark session as expired/needs login."""
        return self.update_profile(email, is_ready=False)
    
    def auto_extract_tokens(self, email: str, headless: bool = False) -> bool:
        """Auto-extract tokens from browser session using Playwright.
        
        Uses TokenExtractor to headlessly extract:
        - Access token
        - reCAPTCHA token  
        - Browser validation headers
        
        Args:
            email: Profile email
            headless: Run browser in headless mode (default: False for visibility)
            
        Returns:
            True if extraction successful
        """
        profile = self.get_profile(email)
        if not profile:
            print(f"[ProfilesController] Profile not found: {email}")
            return False
        
        if not profile.profile_path:
            print(f"[ProfilesController] No profile path for: {email}")
            return False
        
        print(f"[ProfilesController] Extracting tokens for: {email}")
        
        try:
            from core.token_extractor import extract_tokens_sync
            
            tokens = extract_tokens_sync(profile.profile_path, headless=headless)
            
            if tokens and tokens.access_token:
                # Update profile with extracted data
                self.update_profile(
                    email,
                    is_ready=True,
                )
                print(f"[ProfilesController] Tokens extracted for: {email}")
                print(f"[ProfilesController] Token complete: {tokens.is_complete}")
                return True
            else:
                print(f"[ProfilesController] Token extraction failed for: {email}")
                self.update_profile(email, is_ready=False)
                return False
                
        except Exception as e:
            print(f"[ProfilesController] Error extracting tokens: {e}")
            return False
    
    # =========================================================================
    # Batch Operations
    # =========================================================================
    
    def refresh_all_profiles(self) -> dict:
        """Refresh all profiles.
        
        Returns:
            Dict with success/failure counts
        """
        results = {"success": 0, "failed": 0, "total": len(self._profiles)}
        
        for profile in self._profiles:
            try:
                success = self.auto_extract_tokens(profile.email, headless=True)
                if success:
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception as e:
                print(f"[ProfilesController] Batch refresh error for {profile.email}: {e}")
                results["failed"] += 1
        
        return results
    
    def get_ready_profiles(self) -> List[ChromeProfile]:
        """Get all profiles that are ready for use."""
        return [p for p in self._profiles if p.is_ready]
    
    def get_expired_profiles(self) -> List[ChromeProfile]:
        """Get all profiles that need login/refresh."""
        return [p for p in self._profiles if not p.is_ready]
    
    def export_profiles(self, export_path: Path) -> bool:
        """Export profiles to a JSON file.
        
        Args:
            export_path: Destination file path
        """
        try:
            data = {
                "profiles": [p.to_dict() for p in self._profiles],
                "exported_at": datetime.now().isoformat(),
            }
            
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"[ProfilesController] Exported {len(self._profiles)} profiles to {export_path}")
            return True
            
        except Exception as e:
            print(f"[ProfilesController] Export failed: {e}")
            return False
    
    def import_profiles(self, import_path: Path, merge: bool = True) -> int:
        """Import profiles from a JSON file.
        
        Args:
            import_path: Source file path
            merge: If True, merge with existing. If False, replace all.
            
        Returns:
            Number of profiles imported
        """
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            imported = 0
            
            if not merge:
                self._profiles = []
            
            for p_data in data.get("profiles", []):
                email = p_data.get("email")
                
                # Skip duplicates in merge mode
                if merge and self.get_profile(email):
                    continue
                
                profile = ChromeProfile.from_dict(p_data)
                self._profiles.append(profile)
                imported += 1
            
            self.save_profiles()
            self._notify("profiles_changed")
            
            print(f"[ProfilesController] Imported {imported} profiles from {import_path}")
            return imported
            
        except Exception as e:
            print(f"[ProfilesController] Import failed: {e}")
            return 0
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def load_profiles(self) -> List[ChromeProfile]:
        """Load profiles from JSON file."""
        if not self.storage_path.exists():
            print(f"[ProfilesController] No profiles file, starting fresh")
            self._profiles = []
            return self._profiles
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._profiles = [
                ChromeProfile.from_dict(p) 
                for p in data.get("profiles", [])
            ]
            print(f"[ProfilesController] Loaded {len(self._profiles)} profiles")
            
        except Exception as e:
            print(f"[ProfilesController] Error loading profiles: {e}")
            self._profiles = []
        
        return self._profiles
    
    def save_profiles(self):
        """Save profiles to JSON file."""
        try:
            data = {
                "profiles": [p.to_dict() for p in self._profiles],
                "last_updated": datetime.now().isoformat(),
            }
            
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"[ProfilesController] Saved {len(self._profiles)} profiles")
            
        except Exception as e:
            print(f"[ProfilesController] Error saving profiles: {e}")
    
    # =========================================================================
    # Helpers
    # =========================================================================
    
    def _notify(self, event: str, *args):
        """Notify callbacks."""
        callback = self._callbacks.get(event)
        if callback:
            try:
                callback(*args)
            except Exception as e:
                print(f"[ProfilesController] Callback error: {e}")
    
    def get_status_summary(self) -> dict:
        """Get summary for display."""
        ready_count = sum(1 for p in self._profiles if p.is_ready)
        total_credits = sum(p.credits for p in self._profiles)
        
        return {
            "total_profiles": len(self._profiles),
            "ready_profiles": ready_count,
            "total_credits": total_credits,
            "capacity": len(self._profiles) * 4,  # 4 slots per account
        }
