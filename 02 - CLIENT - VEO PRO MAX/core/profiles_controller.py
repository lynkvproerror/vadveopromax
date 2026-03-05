import logging

log = logging.getLogger(__name__)
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


def _get_chrome_executable() -> Optional[str]:
    """Get Chrome executable path for Playwright.
    
    Priority: branded Chrome (full headers + reCAPTCHA trust) > CfT > None.
    Falls back to None (Playwright will use its own bundled Chromium).
    """
    try:
        from core.chrome_manager import find_chrome_exe
        exe = find_chrome_exe()
        if exe:
            return exe
    except Exception:
        pass
    return None




# ── Win32 API helpers for true browser window hiding ────────────────────
import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

def _find_hwnds_by_pid(pid: int) -> list:
    """Find Chrome browser window handles owned by a process and its children.
    
    Chrome for Testing spawns child processes (GPU, renderer) that may own
    taskbar-visible windows. We scan the entire process tree to catch all
    Chrome_WidgetWin_1 windows.
    """
    if not pid:
        return []
    
    # Build set of PIDs: main process + all children
    pids_to_check = {pid}
    try:
        import psutil
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            pids_to_check.add(child.pid)
    except Exception:
        pass  # psutil not available or process gone — fall back to main PID only
    
    hwnds = []
    
    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _enum_callback(hwnd, _lparam):
        proc_id = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if proc_id.value in pids_to_check:
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value == 'Chrome_WidgetWin_1':
                hwnds.append(int(hwnd))
        return True
    
    user32.EnumWindows(_enum_callback, 0)
    return hwnds

def _find_chrome_pid_by_profile(profile_dir_name: str) -> int:
    """Find Chrome main process PID by matching --user-data-dir in command line."""
    import subprocess
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where',
             f"name='chrome.exe' and commandline like '%{profile_dir_name}%' and not commandline like '%--type=%'",
             'get', 'processid', '/value'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith('ProcessId='):
                return int(line.split('=')[1])
    except Exception as e:
        log.error(f"[Win32] PID lookup error: {e}")
    return 0

def _win32_hide_hwnds(hwnds: list):
    """Hide specific window handles (disappears from taskbar + Alt+Tab)."""
    for hwnd in hwnds:
        user32.ShowWindow(hwnd, SW_HIDE)

def _win32_show_hwnds(hwnds: list):
    """Show specific window handles, move on-screen, and bring to front."""
    SWP_NOZORDER = 0x0004
    SWP_NOSIZE = 0x0001
    # Get screen size to center the window
    screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    for hwnd in hwnds:
        # Move to center of screen (keep current size)
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        x = max(0, (screen_w - w) // 2)
        y = max(0, (screen_h - h) // 2)
        user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER)
        user32.ShowWindow(hwnd, SW_RESTORE)

def _win32_send_to_back(hwnds: list):
    """Send Chrome windows behind all other windows (no focus steal).
    
    Uses SetWindowPos with HWND_BOTTOM to push Chrome to the back of
    the Z-order. Windows remain visible but behind the active application.
    Also uses SWP_NOACTIVATE to prevent Chrome from stealing focus.
    
    Called after Chrome launch when smart_hide is disabled but we don't
    want Chrome to cover the user's IDE/workspace.
    """
    HWND_BOTTOM = 1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    for hwnd in hwnds:
        user32.SetWindowPos(
            hwnd, HWND_BOTTOM, 0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        )




@dataclass
class ChromeProfile:
    """Chrome profile data for account management."""
    
    email: str
    display_name: str = ""
    profile_path: str = ""
    sku: str = "WS_ULTRA"  # Default Ultra; auto-detected from /v1/credits
    paygate_tier: str = "PAYGATE_TIER_TWO"
    credits: int = 0
    is_ready: bool = False
    last_used: Optional[str] = None
    created_at: Optional[str] = None
    # New fields for dual login
    login_method: str = "browser"  # Always browser login
    browser_profile_path: str = ""  # Path to saved Chromium profile for browser login
    subscription_fetched: bool = False  # True if subscription was successfully fetched
    token_expires_at: Optional[str] = None  # ISO datetime when token expires (for status display)
    is_enabled: bool = True  # Account participates in rotation when generating
    max_workers: int = 20  # Per-account concurrent worker limit (0-20, 1 worker = 1 video)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.display_name:
            self.display_name = self.email.split("@")[0]
    
    @property
    def tier_display(self) -> str:
        """Get display name for tier."""
        # Not yet fetched subscription
        if not self.subscription_fetched:
            return "⏳ Wait"
        
        # Primary: check SKU
        tier_map = {
            "WS_ULTRA": "🚀 Ultra",
            "WS_PRO": "💎 Pro",
            "WS_FREEMIUM": "👤 Free",
        }
        result = tier_map.get(self.sku)
        if result:
            return result
        
        # Fallback: check paygate_tier when SKU is unknown/missing
        paygate_map = {
            "PAYGATE_TIER_TWO": "🚀 Ultra",
            "PAYGATE_TIER_ONE": "💎 Pro",
            "PAYGATE_TIER_NOT_PAID": "👤 Free",
        }
        return paygate_map.get(self.paygate_tier, "👤 Free")
    
    @property
    def credits_display(self) -> str:
        """Get display for credits."""
        if not self.subscription_fetched:
            return "N/A"
        return str(self.credits)
    
    @property
    def status_display(self) -> str:
        """Get display status with detailed token state.
        
        Status priority:
        1. 🔴 Expired - Token đã hết hạn, cần login lại
        2. 🟠 Expiring - Token sắp hết hạn (< 5 phút)
        3. 🟢 Login - Chưa đăng nhập hoặc chưa có token
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
            return "🟢 Login"
        return "🟢 Ready"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChromeProfile":
        """Create from dictionary."""
        # Handle legacy profiles without new fields
        if "login_method" not in data:
            data["login_method"] = "browser"
        if "browser_profile_path" not in data:
            data["browser_profile_path"] = ""
        if "subscription_fetched" not in data:
            data["subscription_fetched"] = False
        if "token_expires_at" not in data:
            data["token_expires_at"] = None
        if "is_enabled" not in data:
            data["is_enabled"] = True  # Default enabled for legacy profiles
        
        # Migrate max_slots → max_workers (field renamed in recent update)
        if "max_slots" in data and "max_workers" not in data:
            data["max_workers"] = data.pop("max_slots")
        elif "max_slots" in data:
            data.pop("max_slots")  # Remove duplicate if both exist
        
        # Remove legacy worker_profiles key if present
        data.pop("worker_profiles", None)
        
        # Filter out any unknown keys to prevent TypeError on cls(**data)
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        
        return cls(**filtered)


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
                         Defaults to ~/.veoauto/profiles.json
        """
        if storage_path is None:
            storage_path = Path.home() / ".veoauto" / "profiles.json"
        
        self.storage_path = Path(storage_path)
        self._profiles: List[ChromeProfile] = []
        self._callbacks: Dict[str, Callable] = {}
        
        # Ensure directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Auto-migrate: copy from old source-tree location if new file doesn't exist
        if not self.storage_path.exists():
            old_path = Path(__file__).parent.parent / "config" / "profiles.json"
            if old_path.exists():
                import shutil
                shutil.copy2(old_path, self.storage_path)
                log.info(f"[ProfilesController] Migrated profiles from {old_path} → {self.storage_path}")
                # Remove old file to prevent ghost restoration of deleted profiles
                try:
                    old_path.unlink()
                    log.info(f"[ProfilesController] 🗑️ Removed old migration source: {old_path}")
                except Exception as e:
                    log.warning(f"[ProfilesController] ⚠️ Could not remove old file: {e}")
        
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
        results = []
        for p in self._profiles:
            d = {
                "email": p.email,
                "display_name": p.display_name,
                "tier": p.tier_display,
                "credits": p.credits_display,
                "status": p.status_display,
                "is_ready": p.is_ready,
                "is_enabled": p.is_enabled,
                "profile_path": p.profile_path,
                "login_method": p.login_method,
                "max_workers": p.max_workers,
                "max_slots": p.max_workers,  # backward compat for old UI readers
            }
            results.append(d)
        return results
    
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
            log.info(f"[ProfilesController] Profile already exists: {email}")
            return False
        
        # G6: License gate — check max accounts limit
        try:
            from core.app_controller import AppController
            # Access singleton if available (set during app init)
            ctrl = getattr(self, '_app_controller', None)
            if ctrl and hasattr(ctrl, '_permissions'):
                max_accounts = ctrl._permissions.limits.max_accounts
                current_count = len(self._profiles)
                if max_accounts > 0 and current_count >= max_accounts:
                    log.warning(
                        f"[G6] Account limit reached: {current_count}/{max_accounts}. "
                        f"Upgrade license to add more. Rejected: {email}"
                    )
                    return False
        except Exception:
            pass
        
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
        
        log.info(f"[ProfilesController] Added profile: {email}")
        return True
    
    def remove_profile(self, email: str) -> bool:
        """Remove profile by email.
        
        Also cleans up:
        - Kills running Chrome process first
        - Browser profile folder on disk
        - Stored credentials for this email
        
        Returns:
            True if removed successfully
        """
        for i, p in enumerate(self._profiles):
            if p.email == email:
                import shutil
                import time
                
                # Step 1: Kill Chrome browser BEFORE deleting folder
                try:
                    self.kill_debug_browser(email)
                    log.info(f"[ProfilesController] 🔒 Chrome killed for {email}")
                    time.sleep(2)  # Wait for process to fully die
                except Exception as e:
                    log.warning(f"[ProfilesController] ⚠️ kill_debug_browser: {e}")
                
                # Also kill via PID file (in case debug browser wasn't tracked)
                if p.browser_profile_path:
                    try:
                        from core.chrome_manager import kill_chrome
                        kill_chrome(p.browser_profile_path)
                    except Exception:
                        pass
                    time.sleep(1)
                
                # Step 2: Cleanup browser profile folder (with retry)
                if p.browser_profile_path:
                    profile_dir = Path(p.browser_profile_path)
                    if profile_dir.exists():
                        deleted = False
                        for attempt in range(3):
                            try:
                                shutil.rmtree(profile_dir)
                                log.info(f"[ProfilesController] 🗑️ Deleted browser folder: {profile_dir.name}")
                                deleted = True
                                break
                            except Exception as e:
                                log.warning(f"[ProfilesController] ⚠️ rmtree attempt {attempt+1}/3: {e}")
                                time.sleep(2)
                        
                        if not deleted:
                            log.error(f"[ProfilesController] ❌ Could not delete {profile_dir.name} — may need manual cleanup")
                
                # Cleanup stored credentials
                try:
                    from core.credentials_manager import get_credentials_manager
                    get_credentials_manager().delete_credentials_for(email)
                except Exception:
                    pass
                
                # Cleanup tokens.json entry (stale access tokens)
                try:
                    tokens_path = self.storage_path.parent / "tokens.json"
                    if tokens_path.exists():
                        with open(tokens_path, 'r', encoding='utf-8') as f:
                            tokens_data = json.load(f)
                        if email in tokens_data:
                            del tokens_data[email]
                            with open(tokens_path, 'w', encoding='utf-8') as f:
                                json.dump(tokens_data, f, indent=2, ensure_ascii=False)
                            log.info(f"[ProfilesController] 🗑️ Removed {email} from tokens.json")
                except Exception as e:
                    log.warning(f"[ProfilesController] ⚠️ tokens.json cleanup: {e}")
                
                # Cleanup project cache
                try:
                    if hasattr(self, '_project_cache'):
                        keys_to_remove = [k for k in self._project_cache if k.startswith(f"{email}|")]
                        for k in keys_to_remove:
                            del self._project_cache[k]
                except Exception:
                    pass
                
                self._profiles.pop(i)
                self.save_profiles()
                log.info(f"[ProfilesController] Removed profile: {email}")
                return True
        
        log.warning(f"[ProfilesController] Profile not found: {email}")
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
        """Refresh access token for a profile via browser session.
        
        Uses TokenManager to refresh the access token.
        
        Args:
            email: Profile email
            
        Returns:
            True if refresh successful
        """
        from core.token_manager import get_token_manager
        
        profile = self.get_profile(email)
        if not profile:
            log.warning(f"[ProfilesController] Profile not found: {email}")
            return False
        
        log.info(f"[ProfilesController] Refreshing session for {email}")
        
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
                log.info(f"[ProfilesController] ✅ Session refreshed for {email}")
                return True
            else:
                profile.is_ready = False
                self.save_profiles()
                log.error(f"[ProfilesController] ❌ Failed to refresh session for {email}")
                return False
                
        except Exception as e:
            log.error(f"[ProfilesController] Refresh error: {e}")
            profile.is_ready = False
            self.save_profiles()
            return False
    
    def fetch_subscription_info(self, email: str) -> dict:
        """Fetch subscription info based on login method.
        
        Returns dict with:
        - success: bool
        - reason: str ("ok", "profile_missing", "session_expired", 
                       "not_logged_in", "credits_api_failed")
        - can_auto_login: bool (True if stored credentials exist for this email)
        """
        profile = self.get_profile(email)
        if not profile:
            log.warning(f"[ProfilesController] Profile not found: {email}")
            return {"success": False, "reason": "profile_not_found", "can_auto_login": False}
        
        # Check if auto-login is possible
        can_auto_login = False
        try:
            from core.credentials_manager import get_credentials_manager
            creds_manager = get_credentials_manager()
            can_auto_login = creds_manager.has_credentials_for(email)
        except Exception:
            pass
        
        log.info(f"[ProfilesController] Fetching subscription for {email}")
        
        if profile.browser_profile_path:
            # Browser login → Fetch real-time
            result = self._fetch_subscription_via_browser(profile)
            result["can_auto_login"] = can_auto_login
            return result
        else:
            # No browser profile path → needs login first
            log.error(f"[ProfilesController] ❌ No browser profile — needs login")
            return {"success": False, "reason": "not_logged_in", "can_auto_login": can_auto_login}
    
    def _fetch_subscription_via_browser(self, profile: "ChromeProfile") -> dict:
        """Fetch subscription using saved browser profile (for browser login).
        
        Returns dict with {success, reason} instead of bool.
        """
        try:
            # REUSE: If debug browser is already open or launching, use it
            # instead of launching a new one (which would cause profile lock crash)
            if hasattr(self, '_debug_browsers') and profile.email in self._debug_browsers:
                entry = self._debug_browsers[profile.email]
                if entry.get("context") is not None:
                    # Debug browser fully ready — reuse it
                    log.debug(f"[ProfilesController] Debug browser open for {profile.email} — reusing for subscription fetch")
                    return self._fetch_subscription_via_debug_browser(profile)
                else:
                    # Debug browser is still launching — wait for it
                    import time
                    log.debug(f"[ProfilesController] Debug browser launching for {profile.email} — waiting...")
                    for _ in range(30):  # Wait up to 15s
                        time.sleep(0.5)
                        if entry.get("context") is not None:
                            log.debug(f"[ProfilesController] Debug browser ready — reusing for subscription fetch")
                            return self._fetch_subscription_via_debug_browser(profile)
                    log.warning(f"[ProfilesController] Debug browser launch timeout — skipping subscription fetch")
                    return {"success": False, "reason": "browser_launching"}
            
            # Check if we're inside an asyncio loop
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                if loop:
                    log.warning(f"[ProfilesController] ⚠️ Inside asyncio loop - skipping sync subscription fetch")
                    log.info(f"[ProfilesController] Subscription will be fetched on next refresh")
                    return {"success": True, "reason": "deferred"}
            except RuntimeError:
                pass  # No running loop, safe to use sync API
            
            from playwright.sync_api import sync_playwright
            from datetime import datetime
            import os
            
            if not profile.browser_profile_path or not os.path.exists(profile.browser_profile_path):
                log.error(f"[ProfilesController] ❌ Browser profile path not found: {profile.browser_profile_path}")
                log.info(f"[ProfilesController] 🔑 Account needs re-login")
                profile.is_ready = False
                self.save_profiles()
                return {"success": False, "reason": "profile_missing"}
            
            API_KEY = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"
            CREDITS_URL = f"https://aisandbox-pa.googleapis.com/v1/credits?key={API_KEY}"
            
            log.info(f"[ProfilesController] Launching browser with saved profile...")
            
            
            with sync_playwright() as p:
                # Headless mode for subscription refresh - no need to show browser
                # Use branded Chrome (preferred) or CfT fallback
                _chrome_exe = _get_chrome_executable()
                _launch_kwargs = dict(
                    user_data_dir=profile.browser_profile_path,
                    headless=True,  # Run in background
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check"
                    ]
                )
                if _chrome_exe:
                    _launch_kwargs["executable_path"] = _chrome_exe
                else:
                    _launch_kwargs["channel"] = "chrome"  # Fallback to branded
                context = p.chromium.launch_persistent_context(**_launch_kwargs)
                
                page = context.new_page()
                
                try:
                    # Step 1: Navigate to labs.google/fx/tools/flow (needs full page for __NEXT_DATA__)
                    log.info(f"[ProfilesController] Navigating to labs.google/fx/tools/flow...")
                    page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)
                    
                    # Click "Create with Flow" button if present (activates VEO Flow)
                    try:
                        create_btn = page.locator("button:has-text('Create with Flow')")
                        if create_btn.count() > 0 and create_btn.first.is_visible():
                            log.info("[ProfilesController] Clicking 'Create with Flow' button...")
                            create_btn.first.click()
                            page.wait_for_timeout(3000)
                    except Exception:
                        pass
                    
                    # Step 2: Extract session from __NEXT_DATA__ (per docs Section 7.2)
                    access_token = None
                    session_result = {}
                    
                    for attempt in range(3):
                        log.info(f"[ProfilesController] Extracting __NEXT_DATA__ (attempt {attempt+1}/3)...")
                        try:
                            session_result = page.evaluate("""
                                () => {
                                    const script = document.getElementById('__NEXT_DATA__');
                                    if (!script) return { error: 'no_next_data' };
                                    
                                    try {
                                        const data = JSON.parse(script.textContent);
                                        const session = data?.props?.pageProps?.session;
                                        
                                        if (!session) return { error: 'no_session_in_next_data' };
                                        
                                        return {
                                            access_token: session.access_token || session.accessToken || '',
                                            expires: session.expires || '',
                                            user: {
                                                email: session.user?.email || '',
                                                name: session.user?.name || '',
                                                image: session.user?.image || ''
                                            }
                                        };
                                    } catch(e) {
                                        return { error: e.message };
                                    }
                                }
                            """)
                        except Exception as eval_err:
                            log.error(f"[ProfilesController] ⚠️ Evaluate failed: {eval_err}")
                            session_result = {"error": str(eval_err)}
                            page.wait_for_timeout(3000)
                            continue
                        
                        log.info(f"[ProfilesController] __NEXT_DATA__ result: {session_result}")
                        
                        if session_result and "error" not in session_result:
                            access_token = session_result.get("access_token") or session_result.get("accessToken")
                            if access_token:
                                log.info(f"[ProfilesController] ✅ Got access token on attempt {attempt+1}")
                                break
                        
                        if attempt < 2:
                            log.warning(f"[ProfilesController] ⚠️ No token yet, waiting 3s before retry...")
                            page.wait_for_timeout(3000)
                    
                    # Check for error or empty session (not logged in)
                    if not access_token:
                        log.error(f"[ProfilesController] ⚠️ __NEXT_DATA__ extraction failed after 3 attempts: {session_result}")
                        profile.is_ready = False
                        profile.subscription_fetched = False
                        self.save_profiles()
                        return {"success": False, "reason": "session_expired"}
                    
                    log.info(f"[ProfilesController] ✅ Got access token: {access_token[:20]}...")
                    
                    # Step 3: Call credits API with Bearer token
                    log.info(f"[ProfilesController] Fetching credits API with Bearer token...")
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
                    
                    log.info(f"[ProfilesController] Credits result: {credits_result}")
                    
                    if credits_result and "error" not in credits_result:
                        profile.sku = credits_result.get("sku", "WS_ULTRA")
                        profile.credits = credits_result.get("credits", 0)
                        profile.paygate_tier = credits_result.get("userPaygateTier", "PAYGATE_TIER_TWO")
                        profile.is_ready = True
                        profile.subscription_fetched = True
                        profile.last_used = datetime.now().isoformat()
                        self.save_profiles()
                        
                        log.info(f"[ProfilesController] ✅ Success: {profile.tier_display}, Credits: {profile.credits}")
                        return {"success": True, "reason": "ok"}
                    else:
                        # Still have session, just no credits info
                        log.error(f"[ProfilesController] ⚠️ Credits API failed: {credits_result}")
                        profile.is_ready = True
                        profile.subscription_fetched = False
                        profile.last_used = datetime.now().isoformat()
                        self.save_profiles()
                        return {"success": False, "reason": "credits_api_failed"}
                        
                finally:
                    context.close()
                    
        except Exception as e:
            import traceback
            log.error(f"[ProfilesController] Subscription fetch error: {e}")
            traceback.print_exc()
            return {"success": False, "reason": "exception"}
    

    def _fetch_subscription_via_debug_browser(self, profile: "ChromeProfile") -> dict:
        """Fetch subscription by REUSING the already-open debug browser.
        
        Instead of launching a new browser (which would crash due to profile lock),
        uses evaluate_in_debug_browser() to run JS in the existing page.
        """
        from datetime import datetime
        email = profile.email
        log.debug(f"[ProfilesController] Fetching subscription via debug browser for {email}...")
        
        # Step 1: Extract __NEXT_DATA__ for access token
        session_result = self.execute_js_on_debug_browser(email, """
            () => {
                const script = document.getElementById('__NEXT_DATA__');
                if (!script) return { error: 'no_next_data' };
                try {
                    const data = JSON.parse(script.textContent);
                    const session = data?.props?.pageProps?.session;
                    if (!session) return { error: 'no_session' };
                    return {
                        access_token: session.access_token || session.accessToken || '',
                        expires: session.expires || '',
                        user: {
                            email: session.user?.email || '',
                            name: session.user?.name || ''
                        }
                    };
                } catch(e) { return { error: e.message }; }
            }
        """, timeout=10)
        
        if not session_result or "error" in session_result:
            log.error(f"[ProfilesController] __NEXT_DATA__ extraction failed: {session_result}")
            return {"success": False, "reason": "no_session"}
        
        access_token = session_result.get("access_token", "")
        if not access_token:
            log.info(f"[ProfilesController] No access token in __NEXT_DATA__")
            return {"success": False, "reason": "no_token"}
        
        log.info(f"[ProfilesController] Got access token: {access_token[:20]}...")
        
        # Step 2: Fetch credits API using the debug browser's fetch()
        credits_js = """
            async () => {
                try {
                    const resp = await fetch(
                        'https://aisandbox-pa.googleapis.com/v1/credits?key=AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY',
                        {
                            headers: { 'Authorization': 'Bearer """ + access_token + """' },
                            credentials: 'include'
                        }
                    );
                    if (resp.ok) return await resp.json();
                    return { error: resp.status };
                } catch (e) { return { error: e.message }; }
            }
        """
        credits_result = self.execute_js_on_debug_browser(email, credits_js, timeout=15)
        
        log.info(f"[ProfilesController] Credits result: {credits_result}")
        
        if credits_result and "error" not in credits_result:
            profile.sku = credits_result.get("sku", "WS_ULTRA")
            profile.credits = credits_result.get("credits", 0)
            profile.paygate_tier = credits_result.get("userPaygateTier", "PAYGATE_TIER_TWO")
            profile.is_ready = True
            profile.subscription_fetched = True
            profile.last_used = datetime.now().isoformat()
            self.save_profiles()
            log.debug(f"[ProfilesController] \u2705 Success via debug browser: {profile.tier_display}, Credits: {profile.credits}")
            return {"success": True, "reason": "ok"}
        else:
            log.error(f"[ProfilesController] Credits API failed via debug browser: {credits_result}")
            profile.is_ready = True
            profile.subscription_fetched = False
            profile.last_used = datetime.now().isoformat()
            self.save_profiles()
            return {"success": False, "reason": "credits_api_failed"}

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
            log.info(f"[ProfilesController] ✅ Subscription updated from API: {profile.tier_display}, Credits: {profile.credits}")
            self._notify("subscription_updated", email)
        
        return updated
    
    # =========================================================================
    # Browser Operations
    # =========================================================================
    
    # add_profile_via_browser (OAuth) — REMOVED. Use add_profile_via_browser_login instead.
    
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
        
        log.info("[ProfilesController] Starting Browser Login flow...")
        
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
                log.info(f"[ProfilesController] Reusing existing browser profile: {profile_path}")
        
        if not profile_path:
            # Generate unique profile folder (first time login)
            profile_folder = f"browser_session_{uuid.uuid4().hex[:8]}"
            profile_path = self.storage_path.parent / "browser_profiles" / profile_folder
            profile_path.mkdir(parents=True, exist_ok=True)
            log.info(f"[ProfilesController] NEW browser profile path: {profile_path}")
        
        try:
            from playwright.sync_api import sync_playwright
            
            
            with sync_playwright() as p:
                # Launch VISIBLE browser for user to login
                # Use branded Chrome (preferred) or CfT fallback
                _chrome_exe = _get_chrome_executable()
                _launch_kwargs = dict(
                    user_data_dir=str(profile_path),
                    headless=False,  # VISIBLE for user interaction
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--start-maximized"
                    ]
                )
                if _chrome_exe:
                    _launch_kwargs["executable_path"] = _chrome_exe
                else:
                    _launch_kwargs["channel"] = "chrome"  # Fallback to branded
                context = p.chromium.launch_persistent_context(**_launch_kwargs)
                
                page = context.new_page()
                
                try:
                    # Navigate to labs.google/fx homepage
                    # The /api/auth/signin/google endpoint has aisandbox scope issues
                    log.info("[ProfilesController] Opening labs.google/fx...")
                    page.goto(
                        "https://labs.google/fx",
                        wait_until="networkidle",
                        timeout=30000
                    )
                    
                    # Wait for page to load
                    page.wait_for_timeout(2000)
                    
                    # Check if already logged in
                    current_url = page.url
                    log.info(f"[ProfilesController] Current URL: {current_url}")
                    
                    # Try to find Sign In button (user needs to click)
                    log.info("[ProfilesController] Looking for 'Sign In' button...")
                    
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
                                log.info(f"[ProfilesController] ✅ Clicked: {selector}")
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
                            log.info("[ProfilesController] ✅ Clicked via JavaScript")
                        except Exception as e:
                            log.error(f"[ProfilesController] JS click failed: {e}")
                    
                    if not clicked:
                        log.info("[ProfilesController] ℹ️ No Sign In button found - user may already be logged in or needs to click manually")
                    
                    if clicked:
                        # Wait for OAuth redirect
                        page.wait_for_timeout(3000)
                        log.info(f"[ProfilesController] Current URL: {page.url[:60]}...")
                        
                        if "accounts.google.com" in page.url:
                            log.info("[ProfilesController] ✅ Redirected to Google OAuth!")
                    
                    # Wait for user to login
                    log.warning(f"[ProfilesController] ⏳ Waiting for login (max {timeout_seconds}s)...")
                    log.info("[ProfilesController] Please login with your Google account in the browser window")
                    
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
                                    log.info(f"[ProfilesController] ✅ Detected login: {email}")
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
                                    log.info(f"[ProfilesController] ✅ Session detected: {email}")
                                    break
                                    
                        except Exception as e:
                            log.info(f"[ProfilesController] Detection check: {e}")
                        
                        log.warning(f"[ProfilesController] Waiting... ({(i+1)*5}/{timeout_seconds}s)")
                    
                    if not email:
                        log.error("[ProfilesController] ❌ Login timeout or cancelled")
                        context.close()
                        return None
                    
                    # Wait for storage to sync before closing
                    log.info("[ProfilesController] Syncing browser storage...")
                    page.wait_for_timeout(2000)
                    
                    # Close browser - profile is saved
                    log.info(f"[ProfilesController] Closing browser. Profile path: {profile_path}")
                    context.close()
                    
                    # Check if profile already exists
                    existing = self.get_profile(email)
                    if existing:
                        log.info(f"[ProfilesController] Updating existing profile: {email}")
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
                            log.info("[ProfilesController] Fetching subscription...")
                            self._fetch_subscription_via_browser(profile)
                        
                        log.info(f"[ProfilesController] ✅ Browser profile added: {email}")
                        return email
                    else:
                        log.error(f"[ProfilesController] Failed to add profile: {email}")
                        return None
                        
                except Exception as e:
                    log.error(f"[ProfilesController] Browser login error: {e}")
                    import traceback
                    traceback.print_exc()
                    context.close()
                    return None
                    
        except Exception as e:
            log.error(f"[ProfilesController] Browser login flow error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def open_browser_for_debug(self, email: str, on_state_change=None) -> bool:
        """Open browser with saved profile for manual debugging.
        
        Launches Chrome with the saved browser profile. Browser stays open
        until explicitly closed via close_debug_browser() or user closes all tabs.
        Supports hide/show toggling while keeping browser alive in background.
        
        Args:
            email: Account email to open browser for
            on_state_change: Optional callback(email, state) called when state changes.
                             state is "visible", "hidden", or "closed"
            
        Returns:
            True if browser launched successfully, False otherwise
        """
        import threading
        import queue as queue_mod
        
        # Initialize tracking dict
        if not hasattr(self, '_debug_browsers'):
            self._debug_browsers = {}
        
        # Prevent duplicate launches
        if email in self._debug_browsers:
            log.info(f"[ProfilesController] Browser already open for {email}")
            return True
        
        profile = self.get_profile(email)
        if not profile or not profile.browser_profile_path:
            log.info(f"[ProfilesController] No browser profile found for {email}")
            return False
        
        profile_path = Path(profile.browser_profile_path)
        if not profile_path.exists():
            log.info(f"[ProfilesController] Browser profile path missing: {profile_path}")
            return False
        
        log.debug(f"[ProfilesController] 🌐 Opening debug browser for {email}...")
        
        try:
            from playwright.sync_api import sync_playwright
            
            # Command queue for thread-safe hide/show/close
            cmd_queue = queue_mod.Queue()
            self._debug_browsers[email] = {
                "cmd_queue": cmd_queue,
                "state": "hidden",
                "context": None,
                "page": None,
            }
            
            def _run_debug_browser():
                """Run debug browser with command loop for hide/show/close.
                
                Uses persistent Chrome (detached process) that survives app exit.
                Connects via CDP — Chrome keeps running after disconnect.
                """
                cdp_session = None
                window_id = None
                browser_hwnds = []
                kill_on_exit = False  # Only True if user sends "kill" command
                chrome_pid = None  # Track for cleanup on failure
                
                try:
                    from core.chrome_manager import launch_or_reconnect, kill_chrome, has_tab_with_url
                    from config.settings import get_settings as _get_settings
                    
                    _s = _get_settings()
                    _should_hide = getattr(_s, 'smart_hide_enabled', True) or getattr(_s, 'hide_all_browsers', False)
                    
                    # Launch or reconnect to persistent Chrome
                    chrome_info = launch_or_reconnect(
                        str(profile_path),
                        email=email,
                        start_url="about:blank",
                        hidden=_should_hide,
                    )
                    chrome_pid = chrome_info["pid"]
                    cdp_port = chrome_info["port"]
                    is_reconnect = "tabs" in chrome_info  # reconnect returns tabs
                    
                    log.info(f"[ProfilesController] Chrome PID={chrome_pid}, port={cdp_port} ({'reconnected' if is_reconnect else 'new'})")
                    
                    # Collect HWNDs for later show/hide commands
                    browser_hwnds = _find_hwnds_by_pid(chrome_pid)
                    if _should_hide:
                        # Ensure all windows are hidden (launch_chrome already hides,
                        # but child windows may appear after launch)
                        _win32_hide_hwnds(browser_hwnds)
                        log.info(f"[ProfilesController] {len(browser_hwnds)} HWND(s) — hidden for {email}")
                        _initial_state = "hidden"
                    else:
                        # Send Chrome behind other windows instead of on top
                        _win32_send_to_back(browser_hwnds)
                        log.info(f"[ProfilesController] {len(browser_hwnds)} HWND(s) — visible (sent to back) for {email} (smart-hide disabled)")
                        _initial_state = "visible"
                    
                    if on_state_change:
                        try:
                            on_state_change(email, _initial_state)
                        except Exception:
                            pass
                    
                    with sync_playwright() as pw:
                        # Step 1: Connect to Chrome via CDP (with retry for cold-boot)
                        log.debug(f"[DEBUG] Step 1: Connecting to CDP on port {cdp_port}...")
                        browser = None
                        cdp_retries = 3
                        for cdp_attempt in range(cdp_retries):
                            try:
                                browser = pw.chromium.connect_over_cdp(
                                    f"http://127.0.0.1:{cdp_port}"
                                )
                                break
                            except Exception as cdp_err:
                                if cdp_attempt < cdp_retries - 1:
                                    log.error(f"[DEBUG] Step 1: CDP connect attempt {cdp_attempt + 1}/{cdp_retries} failed, retrying in 5s...")
                                    import time as _time
                                    _time.sleep(5)
                                else:
                                    raise cdp_err
                        log.debug(f"[DEBUG] Step 1: ✅ Connected. Contexts: {len(browser.contexts)}")
                        context = browser.contexts[0] if browser.contexts else browser.new_context()
                        
                        # Step 1b: Auto-install extension (branded Chrome only)
                        # Skip if freshly launched — launch_chrome() already installed it
                        if is_reconnect:
                            try:
                                from core.chrome_manager import is_branded_chrome
                                from core.extension_manager import install_if_needed
                                _ext_dir = Path(__file__).resolve().parent.parent / "extension"
                                _chrome_exe = chrome_info.get("chrome_exe", "")
                                if _ext_dir.exists() and (_ext_dir / "manifest.json").exists() and is_branded_chrome(_chrome_exe):
                                    _ext_ok = install_if_needed(cdp_port, str(_ext_dir))
                                    log.info(f"[DEBUG] Step 1b: Extension install → {'✅' if _ext_ok else '⚠️ failed'}")
                                else:
                                    log.debug(f"[DEBUG] Step 1b: Skipped (CfT or no extension dir)")
                            except Exception as _ext_e:
                                log.warning(f"[DEBUG] Step 1b: Extension install error (non-fatal): {_ext_e}")
                        else:
                            log.debug(f"[DEBUG] Step 1b: Skipped (fresh launch — already installed by launch_chrome)")
                        
                        # Step 2: Reuse existing pages — prefer one already on /tools/flow
                        existing_pages = context.pages
                        log.debug(f"[DEBUG] Step 2: Found {len(existing_pages)} existing page(s)")
                        if existing_pages:
                            # Prefer a page already on /tools/flow to avoid duplicating it
                            page = None
                            for ep in existing_pages:
                                try:
                                    if "/tools/flow" in (ep.url or ""):
                                        page = ep
                                        log.debug(f"[DEBUG] Step 2: ✅ Reusing existing flow tab: {ep.url}")
                                        break
                                except Exception:
                                    pass
                            if not page:
                                page = existing_pages[0]
                                log.debug(f"[DEBUG] Step 2: ✅ Reusing tab: {page.url}")
                        else:
                            page = context.new_page()
                            log.debug(f"[DEBUG] Step 2: ✅ Created new tab")
                        
                        # Step 2b: Close excess tabs (enforce max 3)
                        # Uses CDP Target.closeTarget — works on pinned tabs too
                        # (Playwright page.close() silently fails on pinned tabs)
                        ALLOWED_FRAGMENTS = ["mail.google.com", "youtube.com", "labs.google"]
                        if len(existing_pages) > 3:
                            log.info(f"[ProfilesController] Tab cleanup: {len(existing_pages)} tabs → closing excess")
                            # Categorize pages
                            allowed = []
                            blank = []
                            other = []
                            for p in existing_pages:
                                url = p.url or ""
                                if url in ("about:blank", "chrome://newtab/", ""):
                                    blank.append(p)
                                elif any(frag in url for frag in ALLOWED_FRAGMENTS):
                                    allowed.append(p)
                                else:
                                    other.append(p)
                            # Close blank + other + excess allowed (keep first 3 allowed)
                            to_close = blank + other + allowed[3:]
                            closed = 0
                            for p in to_close:
                                if p == page:
                                    continue  # Don't close the page we're using
                                try:
                                    # CDP Target.closeTarget handles pinned tabs
                                    import urllib.request, json as _json
                                    _targets_resp = urllib.request.urlopen(
                                        f"http://127.0.0.1:{cdp_port}/json", timeout=3
                                    )
                                    _targets = _json.loads(_targets_resp.read())
                                    _page_url = p.url or ""
                                    _closed_via_cdp = False
                                    for _t in _targets:
                                        if _t.get("url") == _page_url and _t.get("type") == "page":
                                            _tid = _t.get("id")
                                            if _tid:
                                                urllib.request.urlopen(
                                                    f"http://127.0.0.1:{cdp_port}/json/close/{_tid}",
                                                    timeout=3
                                                )
                                                _closed_via_cdp = True
                                                break
                                    if not _closed_via_cdp:
                                        p.close()  # Fallback
                                    closed += 1
                                except Exception:
                                    pass
                            if closed:
                                log.info(f"[ProfilesController] Tab cleanup: closed {closed} excess tab(s)")
                        
                        # Step 3: Set up header capture via CDP protocol
                        # (page.route() doesn't work reliably with connect_over_cdp)
                        captured_headers = {}
                        log.debug(f"[DEBUG] Step 3: Setting up CDP header capture...")
                        
                        try:
                            cdp_session = context.new_cdp_session(page)
                            log.debug(f"[DEBUG] Step 3: ✅ CDP session created")
                        except Exception as e:
                            log.error(f"[DEBUG] Step 3: ❌ CDP session failed: {e}")
                            cdp_session = None
                        
                        if cdp_session:
                            # Use CDP Network domain to capture headers
                            HEADER_KEYS = [
                                "x-browser-channel",
                                "x-browser-copyright", 
                                "x-browser-year",
                                "x-browser-validation",
                                "x-client-data",
                            ]
                            
                            # Anti-spam: track last logged state to avoid 70+ identical lines/sec
                            import time as _cdp_time
                            _extra_info_state = {"last_log": 0.0, "last_keys": ""}
                            
                            def on_request_will_be_sent(event):
                                url = event.get("request", {}).get("url", "")
                                if "googleapis.com" in url or "aisandbox" in url:
                                    headers = event.get("request", {}).get("headers", {})
                                    found = []
                                    for key in HEADER_KEYS:
                                        val = headers.get(key) or headers.get(key.title()) or headers.get(key.upper())
                                        if val:
                                            captured_headers[key] = val
                                            found.append(key)
                                    if found:
                                        log.debug(f"[DEBUG] CDP captured headers from {url[:60]}: {found}")
                            
                            def on_request_extra_info(event):
                                headers = event.get("headers", {})
                                found = []
                                for key in HEADER_KEYS:
                                    # CDP may use different casing
                                    for h_key, h_val in headers.items():
                                        if h_key.lower() == key and h_val:
                                            captured_headers[key] = h_val
                                            found.append(key)
                                if found:
                                    # Throttle + dedup: only log when keys change OR every 10s
                                    now = _cdp_time.monotonic()
                                    keys_sig = str(sorted(found))
                                    if (keys_sig != _extra_info_state["last_keys"]
                                            or now - _extra_info_state["last_log"] > 10.0):
                                        _extra_info_state["last_log"] = now
                                        _extra_info_state["last_keys"] = keys_sig
                                        log.debug(f"[DEBUG] CDP ExtraInfo captured: {found}")
                            
                            cdp_session.on("Network.requestWillBeSent", on_request_will_be_sent)
                            cdp_session.on("Network.requestWillBeSentExtraInfo", on_request_extra_info)
                            cdp_session.send("Network.enable")
                            log.debug(f"[DEBUG] Step 3: ✅ Network.enable active — listening for headers")
                            
                            # Also get window ID
                            try:
                                win_info = cdp_session.send("Browser.getWindowForTarget")
                                window_id = win_info.get("windowId")
                            except Exception as e:
                                log.warning(f"[DEBUG] Window ID warning: {e}")
                        
                        # Step 4: Navigate to VEO if needed
                        current_url = page.url
                        log.debug(f"[DEBUG] Step 4: Current URL = {current_url}")
                        if "/tools/flow" not in current_url:
                            log.debug(f"[DEBUG] Step 4: Navigating to VEO /tools/flow...")
                            try:
                                page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=30000)
                            except Exception as nav_err:
                                # ERR_ABORTED = Chrome redirected (e.g., to login) — not fatal
                                log.debug(f"[DEBUG] Step 4: Navigation interrupted ({type(nav_err).__name__}), checking final URL...")
                            page.wait_for_timeout(3000)
                            log.debug(f"[DEBUG] Step 4: Final URL = {page.url}")
                            
                            try:
                                create_btn = page.locator("button:has-text('Create with Flow')")
                                if create_btn.count() > 0 and create_btn.first.is_visible():
                                    create_btn.first.click()
                                    page.wait_for_timeout(3000)
                                    log.debug(f"[DEBUG] Step 4: Clicked 'Create with Flow'")
                            except Exception:
                                pass
                        else:
                            log.warning(f"[DEBUG] Step 4: ✅ Already on /tools/flow — skipping navigation")
                        
                        # Step 5: Trigger header capture via reload
                        log.debug(f"[DEBUG] Step 5: Headers so far = {list(captured_headers.keys())}")
                        if not captured_headers.get("x-browser-validation"):
                            log.debug(f"[DEBUG] Step 5: Reloading to trigger API calls...")
                            try:
                                page.reload(wait_until="load", timeout=15000)
                                page.wait_for_timeout(3000)
                                log.debug(f"[DEBUG] Step 5: Reload done. Headers = {list(captured_headers.keys())}")
                            except Exception as e:
                                log.error(f"[DEBUG] Step 5: Reload error: {e}")
                        
                        # Step 5b: If still no headers, try navigating away and back
                        # (avoid using non-localized URL since Chrome auto-redirects to /vi/ etc.)
                        if not captured_headers.get("x-browser-validation"):
                            log.debug(f"[DEBUG] Step 5b: Trying navigation away+back...")
                            try:
                                # Navigate away briefly to force fresh request headers
                                page.goto("https://labs.google/fx/tools/flow", wait_until="load", timeout=10000)
                                page.wait_for_timeout(1000)
                                # Reload to trigger API calls for header capture
                                page.goto("https://labs.google/fx/tools/flow",
                                          wait_until="load", timeout=15000)
                                page.wait_for_timeout(3000)
                                log.debug(f"[DEBUG] Step 5b: Headers after nav cycle = {list(captured_headers.keys())}")
                            except Exception as e:
                                log.error(f"[DEBUG] Step 5b: Nav cycle error: {e}")
                        
                        # Step 6: Compute missing branded headers for CfT
                        # Chrome for Testing doesn't inject x-browser-* headers.
                        # We compute them ourselves when they're missing.
                        if not captured_headers.get("x-browser-validation"):
                            # x-browser-validation = base64(sha1(chrome_api_key + user_agent))
                            # Windows Chrome API key (hardcoded in Chrome binary)
                            CHROME_API_KEY_WIN = "AIzaSyA2KlwBX3mkFo30om9LUFYQhpqLoa_BNhE"
                            try:
                                import hashlib
                                import base64 as b64
                                # Get UA from the browser
                                user_agent = page.evaluate("navigator.userAgent")
                                validation_data = CHROME_API_KEY_WIN + user_agent
                                sha1_hash = hashlib.sha1(validation_data.encode("utf-8")).digest()
                                validation_b64 = b64.b64encode(sha1_hash).decode("ascii")
                                captured_headers["x-browser-validation"] = validation_b64
                                log.info(f"[ProfilesController] 🔑 Computed x-browser-validation from UA: {validation_b64[:20]}...")
                            except Exception as e:
                                log.warning(f"[ProfilesController] ⚠️ Could not compute x-browser-validation: {e}")
                        
                        # Inject static branded headers if missing (CfT doesn't send these)
                        if "x-browser-channel" not in captured_headers:
                            captured_headers["x-browser-channel"] = "stable"
                        if "x-browser-copyright" not in captured_headers:
                            captured_headers["x-browser-copyright"] = "Copyright 2026 Google LLC. All Rights reserved."
                        if "x-browser-year" not in captured_headers:
                            captured_headers["x-browser-year"] = "2026"
                        
                        # Final result
                        if captured_headers:
                            log.info(f"[ProfilesController] ✅ Browser headers captured for {email}: {list(captured_headers.keys())}")
                        else:
                            log.warning(f"[ProfilesController] ⚠️ No x-browser-* headers captured for {email} — API calls may fail with 403")
                        
                        log.debug(f"[ProfilesController] ✅ Debug browser ready for {email} (persistent, port={cdp_port})")
                        
                        # Store refs for RecaptchaBrowserSession reuse
                        entry = self._debug_browsers.get(email)
                        if entry:
                            entry["context"] = context
                            entry["page"] = page
                            entry["hwnds"] = browser_hwnds
                            entry["captured_headers"] = captured_headers
                            entry["cdp_port"] = cdp_port
                            entry["chrome_pid"] = chrome_pid
                        
                        # ★ Post-setup re-hide: Chrome spawns new renderer processes
                        # during page navigation (step 4-5) — their HWNDs aren't
                        # captured by the initial hide at launch. Re-scan and hide.
                        if _should_hide:
                            import time as _rehide_time
                            _rehide_time.sleep(1)  # Brief wait for renderers to settle
                            browser_hwnds = _find_hwnds_by_pid(chrome_pid)
                            _win32_hide_hwnds(browser_hwnds)
                            # Update stored HWNDs
                            entry_ref = self._debug_browsers.get(email)
                            if entry_ref:
                                entry_ref["hwnds"] = browser_hwnds
                            log.info(
                                f"[ProfilesController] 🔇 Post-setup re-hide: "
                                f"{len(browser_hwnds)} HWND(s) hidden for {email}"
                            )
                        
                        # Command loop
                        running = True
                        while running:
                            try:
                                cmd = cmd_queue.get(timeout=0.5)
                                
                                if isinstance(cmd, tuple) and cmd[0] == "evaluate":
                                    _, expression, eval_arg, result_event, result_holder = cmd
                                    max_eval_attempts = 2
                                    for eval_attempt in range(max_eval_attempts):
                                        try:
                                            if eval_arg is not None:
                                                result = page.evaluate(expression, eval_arg)
                                            else:
                                                result = page.evaluate(expression)
                                            result_holder["value"] = result
                                            result_holder["error"] = None
                                            break  # success
                                        except Exception as eval_err:
                                            err_str = str(eval_err).lower()
                                            # Navigation destroyed context — retry after wait
                                            if eval_attempt < max_eval_attempts - 1 and (
                                                "context was destroyed" in err_str or
                                                "navigation" in err_str
                                            ):
                                                import time as _time
                                                _time.sleep(2)
                                                continue
                                            result_holder["value"] = None
                                            result_holder["error"] = str(eval_err)
                                    result_event.set()
                                
                                elif cmd == "hide":
                                    # Re-scan HWNDs (Chrome may have spawned new windows)
                                    browser_hwnds = _find_hwnds_by_pid(chrome_pid)
                                    _win32_hide_hwnds(browser_hwnds)
                                    entry = self._debug_browsers.get(email)
                                    if entry:
                                        entry["state"] = "hidden"
                                    log.info(f"[ProfilesController] 🔇 Browser hidden for {email}")
                                    if on_state_change:
                                        try:
                                            on_state_change(email, "hidden")
                                        except Exception:
                                            pass
                                            
                                elif cmd == "show":
                                    browser_hwnds = _find_hwnds_by_pid(chrome_pid)
                                    _win32_show_hwnds(browser_hwnds)
                                    entry = self._debug_browsers.get(email)
                                    if entry:
                                        entry["state"] = "visible"
                                    log.info(f"[ProfilesController] 👁️ Browser shown for {email}")
                                    if on_state_change:
                                        try:
                                            on_state_change(email, "visible")
                                        except Exception:
                                            pass
                                
                                elif cmd == "refresh_token":
                                    # Reload page to refresh session, extract fresh access_token
                                    log.info(f"[ProfilesController] 🔄 Refreshing token for {email}...")
                                    try:
                                        try:
                                            page.reload(wait_until="load", timeout=15000)
                                        except Exception:
                                            # Fallback: navigate directly if reload fails (frame detached)
                                            page.goto("https://labs.google/fx/tools/flow", wait_until="load", timeout=15000)
                                        page.wait_for_timeout(2000)
                                        
                                        # Extract access_token from __NEXT_DATA__
                                        token = page.evaluate("""() => {
                                            try {
                                                const nd = document.getElementById('__NEXT_DATA__');
                                                if (nd) {
                                                    const data = JSON.parse(nd.textContent);
                                                    return data?.props?.pageProps?.userInfo?.accessToken
                                                        || data?.props?.pageProps?.session?.accessToken
                                                        || null;
                                                }
                                            } catch {}
                                            return null;
                                        }""")
                                        
                                        if token and len(token) > 100:
                                            # Save to profile so Engine can pick it up
                                            profile = self.get_profile(email)
                                            if profile:
                                                profile.access_token = token
                                                from datetime import datetime, timedelta
                                                profile.token_expires = datetime.now() + timedelta(hours=1)
                                            log.info(f"[ProfilesController] ✅ Token refreshed for {email} ({len(token)} chars)")
                                        else:
                                            log.error(f"[ProfilesController] ⚠️ Token refresh failed — no token in page data")
                                    except Exception as e:
                                        log.error(f"[ProfilesController] ❌ Token refresh error: {e}")
                                
                                elif cmd == "close":
                                    # Disconnect only — Chrome keeps running
                                    running = False
                                
                                elif cmd == "kill":
                                    # Kill Chrome process entirely
                                    kill_on_exit = True
                                    running = False
                                    
                            except queue_mod.Empty:
                                pass
                            
                            # Check if browser process died externally
                            if running:
                                try:
                                    from core.chrome_manager import _is_chrome_process_alive
                                    if not _is_chrome_process_alive(chrome_pid, str(profile_path)):
                                        running = False
                                except Exception:
                                    pass
                        
                        # Disconnect Playwright (Chrome keeps running)
                        try:
                            browser.close()  # close() on CDP-connected browser = disconnect only
                        except Exception:
                            pass
                    
                    # If kill was requested, terminate Chrome
                    if kill_on_exit:
                        kill_chrome(str(profile_path))
                        log.info(f"[ProfilesController] 🔒 Chrome KILLED for {email}")
                    else:
                        log.info(f"[ProfilesController] 🔗 Playwright disconnected — Chrome still running for {email}")
                        
                except Exception as e:
                    log.error(f"[ProfilesController] Debug browser error: {e}")
                    import traceback
                    traceback.print_exc()
                    # Kill orphaned Chrome if CDP connect failed
                    # (prevents zombie Chrome windows after reboot/timeout)
                    try:
                        if chrome_pid:
                            kill_chrome(str(profile_path))
                            log.error(f"[ProfilesController] 🔒 Killed orphaned Chrome PID={chrome_pid} (CDP connect failed)")
                    except Exception:
                        pass
                finally:
                    self._debug_browsers.pop(email, None)
                    state = "closed" if kill_on_exit else "disconnected"
                    log.debug(f"[ProfilesController] Debug browser {state} for {email}")
                    if on_state_change:
                        try:
                            on_state_change(email, "closed")
                        except Exception:
                            pass
            
            thread = threading.Thread(target=_run_debug_browser, daemon=True)
            thread.start()
            return True
            
        except Exception as e:
            self._debug_browsers.pop(email, None)
            log.error(f"[ProfilesController] Debug browser error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def hide_debug_browser(self, email: str) -> bool:
        """Hide (minimize) a debug browser. Browser keeps running in background.
        
        Thread-safe: sends 'hide' command via queue to the browser thread.
        """
        if not hasattr(self, '_debug_browsers'):
            return False
        entry = self._debug_browsers.get(email)
        if not entry:
            return False
        entry["cmd_queue"].put("hide")
        return True
    
    def show_debug_browser(self, email: str) -> bool:
        """Show (restore) a hidden debug browser window.
        
        Thread-safe: sends 'show' command via queue to the browser thread.
        """
        if not hasattr(self, '_debug_browsers'):
            return False
        entry = self._debug_browsers.get(email)
        if not entry:
            return False
        entry["cmd_queue"].put("show")
        return True
    
    def close_debug_browser(self, email: str) -> bool:
        """Disconnect from debug browser (Chrome keeps running in background).
        
        Thread-safe: sends 'close' command via queue to the browser thread.
        Chrome process remains alive for fast reconnect.
        """
        if not hasattr(self, '_debug_browsers'):
            return False
        entry = self._debug_browsers.get(email)
        if not entry:
            return False
        entry["cmd_queue"].put("close")
        log.info(f"[ProfilesController] 🔗 Signaled disconnect for {email} (Chrome stays alive)")
        return True
    
    def kill_debug_browser(self, email: str) -> bool:
        """Kill debug browser completely (terminate Chrome process).
        
        Thread-safe: sends 'kill' command via queue to the browser thread.
        Removes PID file and terminates the Chrome process.
        """
        if not hasattr(self, '_debug_browsers'):
            return False
        entry = self._debug_browsers.get(email)
        if not entry:
            # No active Playwright connection — try direct kill via PID file
            profile = self.get_profile(email)
            if profile and profile.browser_profile_path:
                from core.chrome_manager import kill_chrome
                return kill_chrome(profile.browser_profile_path)
            return False
        entry["cmd_queue"].put("kill")
        log.info(f"[ProfilesController] 🔒 Signaled kill for {email}")
        return True
    
    def kill_all_debug_browsers(self):
        """Kill ALL debug browsers on app exit.
        
        1. Send 'kill' command to each active debug browser thread
        2. Fallback: kill any orphaned Chrome via PID files
        """
        if not hasattr(self, '_debug_browsers'):
            return
        
        # Phase 1: Signal kill to all active browser threads
        emails = list(self._debug_browsers.keys())
        for email in emails:
            try:
                entry = self._debug_browsers.get(email)
                if entry and entry.get("cmd_queue"):
                    entry["cmd_queue"].put("kill")
                    log.info(f"[ProfilesController] 🔒 Signaled kill for {email}")
            except Exception as e:
                log.warning(f"[ProfilesController] Kill signal failed for {email}: {e}")
        
        # Phase 2: Fallback — kill any Chrome still alive via PID files
        import time
        time.sleep(1)  # Give threads a moment to process kill commands
        try:
            from core.chrome_manager import kill_all_managed_chromes
            # Find the browser_profiles directory
            profiles_dir = None
            for profile in self._profiles:
                if profile.browser_profile_path:
                    from pathlib import Path
                    profiles_dir = str(Path(profile.browser_profile_path).parent)
                    break
            if profiles_dir:
                kill_all_managed_chromes(profiles_dir)
                log.info(f"[ProfilesController] 🔒 Killed all managed Chrome processes")
        except Exception as e:
            log.warning(f"[ProfilesController] Fallback Chrome kill failed: {e}")
    
    def is_debug_browser_open(self, email: str) -> bool:
        """Check if a debug browser is currently open (visible or hidden)."""
        if not hasattr(self, '_debug_browsers'):
            return False
        return email in self._debug_browsers
    
    def get_debug_browser_state(self, email: str) -> str:
        """Get the state of a debug browser.
        
        Returns: "visible", "hidden", or "closed"
        """
        if not hasattr(self, '_debug_browsers'):
            return "closed"
        entry = self._debug_browsers.get(email)
        if not entry:
            return "closed"
        return entry.get("state", "visible")
    
    def get_debug_browser_page(self, email: str):
        """Get the Playwright page from a running debug browser.
        
        Returns the sync Playwright Page object if debug browser is open,
        or None if not available. Used by RecaptchaBrowserSession to share
        the browser context instead of launching a separate headless browser.
        """
        if not hasattr(self, '_debug_browsers'):
            return None
        entry = self._debug_browsers.get(email)
        if not entry:
            return None
        return entry.get("page")
    
    def get_debug_browser_headers(self, email: str) -> Dict[str, str]:
        """Get captured x-browser-* headers from running debug browser.
        
        Returns dict with x-browser-validation, x-client-data, etc.
        Empty dict if no debug browser or headers not yet captured.
        """
        if not hasattr(self, '_debug_browsers'):
            return {}
        entry = self._debug_browsers.get(email)
        if not entry:
            return {}
        return dict(entry.get("captured_headers", {}))
    
    def execute_js_on_debug_browser(self, email: str, expression: str, arg=None, timeout: float = 10.0):
        """Execute JavaScript on the debug browser's page (thread-safe).
        
        This marshals the JS call through the command queue so it runs
        on the debug browser's own greenlet/thread — avoiding the
        Playwright 'Cannot switch to a different thread' error.
        
        Args:
            email: Account email
            expression: JavaScript expression to evaluate
            arg: Optional argument to pass to page.evaluate(expression, arg)
            timeout: Max seconds to wait for result
            
        Returns:
            The result of page.evaluate(expression), or None on error
        """
        import threading
        
        if not hasattr(self, '_debug_browsers'):
            return None
        entry = self._debug_browsers.get(email)
        if not entry:
            return None
        
        cmd_queue = entry.get("cmd_queue")
        if not cmd_queue:
            return None
        
        # Create result holder and event
        result_event = threading.Event()
        result_holder = {"value": None, "error": None}
        
        # Send evaluate command to the browser thread
        cmd_queue.put(("evaluate", expression, arg, result_event, result_holder))
        
        # Wait for the browser thread to process it
        if result_event.wait(timeout=timeout):
            if result_holder["error"]:
                log.error(f"[ProfilesController] JS eval error for {email}: {result_holder['error']}")
                return None
            return result_holder["value"]
        else:
            log.warning(f"[ProfilesController] JS eval timeout for {email} ({timeout}s)")
            return None
    
    def auto_login_with_credentials(
        self, 
        email: str,
        password: str,
        timeout_seconds: int = 120,
        headless: bool = False,
        keep_browser_open: bool = False
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
            headless: If True, hide browser window (for engine auto re-login)
                      If False, show browser (for user-initiated login, CAPTCHA)
            
        Returns:
            Email of created/updated profile, or None if failed
        """
        log.info(f"[ProfilesController] Starting Auto-Login for {email} (headless={headless})...")
        
        # Get or create browser profile path (each email gets its OWN profile)
        profile_path = None
        existing = self.get_profile(email)
        if existing and existing.browser_profile_path:
            existing_path = Path(existing.browser_profile_path)
            if existing_path.exists():
                profile_path = existing_path
                log.info(f"[ProfilesController] Reusing OWN browser profile: {profile_path}")
        
        if not profile_path:
            import uuid
            profile_folder = f"browser_session_{uuid.uuid4().hex[:8]}"
            profile_path = self.storage_path.parent / "browser_profiles" / profile_folder
            profile_path.mkdir(parents=True, exist_ok=True)
            log.info(f"[ProfilesController] NEW browser profile: {profile_path}")
        
        try:
            from playwright.sync_api import sync_playwright
            
            # Bug 4 fix: Kill ALL Chrome processes using this profile directory
            # (debug browser, ChromeManager, or any stale instance)
            # This prevents CDP port conflicts and profile lock errors.
            import time
            log.info(f"[ProfilesController] Killing any Chrome using profile: {profile_path.name}")
            try:
                # Force-close debug browser entry if exists
                if hasattr(self, '_debug_browsers') and email in self._debug_browsers:
                    entry = self._debug_browsers[email]
                    ctx = entry.get("context")
                    pw = entry.get("playwright")
                    try:
                        if ctx:
                            ctx.close()
                    except Exception:
                        pass
                    try:
                        if pw:
                            pw.stop()
                    except Exception:
                        pass
                    self._debug_browsers[email] = {"context": None, "playwright": None}
                
                # Kill chrome.exe processes that reference this profile path
                import subprocess
                profile_str = str(profile_path).replace("\\", "\\\\")
                kill_cmd = (
                    f'Get-WmiObject Win32_Process -Filter "Name=\'chrome.exe\'" | '
                    f'Where-Object {{ $_.CommandLine -like "*{profile_path.name}*" }} | '
                    f'ForEach-Object {{ $_.Terminate() }}'
                )
                subprocess.run(["powershell", "-Command", kill_cmd], capture_output=True, timeout=10)
                log.info(f"[ProfilesController] ✅ Chrome processes killed for {profile_path.name}")
            except Exception as e:
                log.warning(f"[ProfilesController] ⚠️ Chrome kill warning: {e}")
            
            time.sleep(3)  # Wait for Chrome to fully exit and release profile lock
            
            
            with sync_playwright() as p:
                # Use branded Chrome (preferred) or CfT fallback
                _chrome_exe = _get_chrome_executable()
                _launch_kwargs = dict(
                    user_data_dir=str(profile_path),
                    headless=headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--start-maximized"
                    ]
                )
                if _chrome_exe:
                    _launch_kwargs["executable_path"] = _chrome_exe
                else:
                    _launch_kwargs["channel"] = "chrome"  # Fallback to branded
                context = p.chromium.launch_persistent_context(**_launch_kwargs)
                
                page = context.new_page()
                
                try:
                    # Step 1: Navigate to Google login
                    log.info("[ProfilesController] Navigating to accounts.google.com...")
                    page.goto("https://accounts.google.com", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                    
                    # Check if already logged in (browser has session cookies)
                    current_url = page.url
                    if "accounts.google.com" not in current_url or "myaccount.google.com" in current_url:
                        log.info(f"[ProfilesController] ✅ Already logged in! URL: {current_url[:50]}...")
                        # Skip login, go directly to labs.google
                    else:
                        # Step 2: Fill email
                        log.info("[ProfilesController] Filling email...")
                        email_input = page.locator("#identifierId")
                        if email_input.count() > 0 and email_input.is_visible():
                            email_input.fill(email)
                            page.wait_for_timeout(500)
                            page.keyboard.press("Enter")
                            log.info("[ProfilesController] ✅ Email entered")
                        else:
                            # Maybe already past email step or different page
                            log.warning("[ProfilesController] ⚠️ Email input not found — may already be logged in")
                            # Check if we're on a chooser or different Google page
                            if "myaccount.google" in current_url or "SignOutOptions" in current_url:
                                log.warning("[ProfilesController] ✅ Already logged in, skipping...")
                            else:
                                log.info(f"[ProfilesController] Current URL: {current_url[:80]}")
                                # Try alternative selector as last resort
                                alt_input = page.locator("input[type='email']")
                                if alt_input.count() > 0:
                                    alt_input.first.fill(email)
                                    page.keyboard.press("Enter")
                                else:
                                    log.warning("[ProfilesController] ⚠️ No email field found at all")
                    
                    # Wait for password page
                    page.wait_for_timeout(3000)
                    
                    # Step 3: Fill password
                    log.info("[ProfilesController] Filling password...")
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
                        log.info("[ProfilesController] ✅ Password entered")
                    else:
                        log.warning("[ProfilesController] ⚠️ Password input not found - may need manual input")
                        # Wait for user to handle manually
                        page.wait_for_timeout(10000)
                    
                    # Step 4: Wait for login completion (redirect away from accounts.google.com)
                    log.warning(f"[ProfilesController] Waiting for login completion (max {timeout_seconds}s)...")
                    login_success = False
                    
                    for i in range(timeout_seconds // 5):
                        page.wait_for_timeout(5000)
                        current_url = page.url
                        log.info(f"[ProfilesController] Current URL: {current_url[:50]}...")
                        
                        # Check if redirected to labs.google or myaccount
                        if "accounts.google.com" not in current_url:
                            login_success = True
                            log.info("[ProfilesController] ✅ Login redirect detected!")
                            break
                        
                        # Check for error messages
                        error_visible = page.locator("[class*='error'], [class*='Error']").count() > 0
                        if error_visible:
                            log.error("[ProfilesController] ⚠️ Error detected on page")
                            
                        log.warning(f"[ProfilesController] Waiting... ({(i+1)*5}/{timeout_seconds}s)")
                    
                    if not login_success:
                        log.error("[ProfilesController] ❌ Login timeout - check for CAPTCHA/2FA")
                        context.close()
                        return None
                    
                    # Step 5: Navigate to labs.google and extract session from __NEXT_DATA__
                    # Per docs (ACCOUNT_SESSION_MANAGEMENT.md Section 7.2):
                    # Server-side renders session data into __NEXT_DATA__ when Google cookies are present
                    log.info("[ProfilesController] Navigating to labs.google/fx/tools/flow...")
                    page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)
                    
                    # Click "Create with Flow" button if present (activates VEO Flow)
                    try:
                        create_btn = page.locator("button:has-text('Create with Flow')")
                        if create_btn.count() > 0 and create_btn.first.is_visible():
                            log.info("[ProfilesController] Clicking 'Create with Flow' button...")
                            create_btn.first.click()
                            page.wait_for_timeout(3000)
                    except Exception:
                        pass
                    
                    # Step 6: Extract session from __NEXT_DATA__
                    access_token = None
                    session_result = {}
                    user_info = {}
                    session_email = email
                    
                    for attempt in range(3):
                        log.info(f"[ProfilesController] Extracting __NEXT_DATA__ (attempt {attempt+1}/3)...")
                        try:
                            session_result = page.evaluate("""
                                () => {
                                    const script = document.getElementById('__NEXT_DATA__');
                                    if (!script) return { error: 'no_next_data' };
                                    
                                    try {
                                        const data = JSON.parse(script.textContent);
                                        const session = data?.props?.pageProps?.session;
                                        
                                        if (!session) return { error: 'no_session_in_next_data' };
                                        
                                        return {
                                            access_token: session.access_token || session.accessToken || '',
                                            expires: session.expires || '',
                                            user: {
                                                email: session.user?.email || '',
                                                name: session.user?.name || '',
                                                image: session.user?.image || ''
                                            }
                                        };
                                    } catch(e) {
                                        return { error: e.message };
                                    }
                                }
                            """)
                        except Exception as eval_err:
                            log.error(f"[ProfilesController] ⚠️ Evaluate failed: {eval_err}")
                            session_result = {"error": str(eval_err)}
                            page.wait_for_timeout(3000)
                            continue
                        
                        log.info(f"[ProfilesController] __NEXT_DATA__ result: {session_result}")
                        
                        access_token = session_result.get("access_token") or session_result.get("accessToken")
                        user_info = session_result.get("user", {})
                        session_email = user_info.get("email", email)
                        
                        if access_token:
                            log.info(f"[ProfilesController] ✅ Got access token on attempt {attempt+1}")
                            break
                        
                        if attempt < 2:
                            log.warning(f"[ProfilesController] ⚠️ No token yet, waiting 3s...")
                            page.wait_for_timeout(3000)
                    
                    if not access_token:
                        log.warning("[ProfilesController] ⚠️ No access token from __NEXT_DATA__ - profile saved without token")
                    
                    # Step 7: Fetch credits/subscription on the SAME page (no second browser needed)
                    credits_data = {}
                    if access_token:
                        log.info(f"[ProfilesController] Fetching credits API with token...")
                        try:
                            credits_data = page.evaluate(f"""
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
                        except Exception as e:
                            log.error(f"[ProfilesController] Credits API error: {e}")
                            credits_data = {"error": str(e)}
                        
                        log.info(f"[ProfilesController] Credits result: {credits_data}")
                    
                    # Sync storage before close
                    log.info("[ProfilesController] Syncing browser storage...")
                    page.wait_for_timeout(2000)
                    
                    # Close browser (unless keep_browser_open for debugging)
                    if keep_browser_open:
                        log.debug("[ProfilesController] 🔓 Browser kept open for debugging. Close manually when done.")
                    else:
                        context.close()
                    
                    # Step 8: Save/update profile with ALL data (token + credits)
                    existing = self.get_profile(session_email)
                    if existing:
                        log.info(f"[ProfilesController] Updating existing profile: {session_email}")
                        existing.login_method = "browser"
                        existing.browser_profile_path = str(profile_path)
                        existing.is_ready = True
                        existing.last_used = datetime.now().isoformat()
                        if credits_data and "error" not in credits_data:
                            existing.sku = credits_data.get("sku", "WS_ULTRA")
                            existing.credits = credits_data.get("credits", 0)
                            existing.paygate_tier = credits_data.get("userPaygateTier", "PAYGATE_TIER_TWO")
                            existing.subscription_fetched = True
                            log.info(f"[ProfilesController] ✅ {existing.tier_display}, Credits: {existing.credits}")
                        self.save_profiles()
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
                            if credits_data and "error" not in credits_data:
                                profile.sku = credits_data.get("sku", "WS_ULTRA")
                                profile.credits = credits_data.get("credits", 0)
                                profile.paygate_tier = credits_data.get("userPaygateTier", "PAYGATE_TIER_TWO")
                                profile.subscription_fetched = True
                                log.info(f"[ProfilesController] ✅ {profile.tier_display}, Credits: {profile.credits}")
                            self.save_profiles()
                        
                        log.info(f"[ProfilesController] ✅ Auto-login successful: {session_email}")
                        return session_email
                    else:
                        log.error(f"[ProfilesController] Failed to add profile: {session_email}")
                        return None
                        
                except Exception as e:
                    log.error(f"[ProfilesController] Auto-login error: {e}")
                    import traceback
                    traceback.print_exc()
                    context.close()
                    return None
                    
        except Exception as e:
            log.error(f"[ProfilesController] Auto-login flow error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def copy_variations_and_warmup(self, email: str) -> bool:
        """Phase 2 recovery: Copy Variations from donor + warm up browser with tabs.
        
        Steps:
        1. Kill any Chrome using this profile
        2. Copy 'Local State' + 'Variations' from a working profile
        3. Launch browser with 3 warmup tabs (gmail, youtube, labs.google)
        4. Wait for Variations Service enrollment
        5. Close browser
        
        Args:
            email: Account email to recover
            
        Returns:
            True if Variations copied + warmup completed
        """
        import time
        import subprocess
        
        log.info(f"[ProfilesController] 🟠 Phase 2: Copy Variations + warmup for {email}")
        
        profile = self.get_profile(email)
        if not profile or not profile.browser_profile_path:
            log.error(f"[ProfilesController] ❌ Profile not found: {email}")
            return False
        
        profile_path = Path(profile.browser_profile_path)
        
        # Step 1: Kill any Chrome using this profile
        log.info(f"[ProfilesController] Step 1: Killing Chrome for {profile_path.name}...")
        try:
            self.kill_debug_browser(email)
        except Exception:
            pass
        
        try:
            # Force-close debug browser entry
            if hasattr(self, '_debug_browsers') and email in self._debug_browsers:
                entry = self._debug_browsers[email]
                try:
                    ctx = entry.get("context")
                    if ctx:
                        ctx.close()
                except Exception:
                    pass
                try:
                    pw = entry.get("playwright")
                    if pw:
                        pw.stop()
                except Exception:
                    pass
                self._debug_browsers[email] = {"context": None, "playwright": None}
            
            # Kill chrome.exe processes using this profile
            kill_cmd = (
                f'Get-WmiObject Win32_Process -Filter "Name=\'chrome.exe\'" | '
                f'Where-Object {{ $_.CommandLine -like "*{profile_path.name}*" }} | '
                f'ForEach-Object {{ $_.Terminate() }}'
            )
            subprocess.run(["powershell", "-Command", kill_cmd], capture_output=True, timeout=10)
        except Exception as e:
            log.warning(f"[ProfilesController] ⚠️ Chrome kill warning: {e}")
        
        time.sleep(3)  # Wait for Chrome to fully exit
        
        # Step 2: Copy Variations from donor
        log.info(f"[ProfilesController] Step 2: Copying Variations from donor...")
        donor_path = self._find_donor_profile(exclude_email=email)
        
        if not donor_path:
            log.warning(f"[ProfilesController] ⚠️ No donor profile found — warmup only")
        else:
            log.info(f"[ProfilesController] Donor: {donor_path.name}")
            self._copy_variations_files(donor_path, profile_path)
        
        time.sleep(3)  # Let Variations files settle
        
        # Step 3: Launch browser with warmup tabs
        warmup_urls = [
            "https://mail.google.com",
            "https://www.youtube.com",
            "https://labs.google/fx/tools/flow",
        ]
        
        log.info(f"[ProfilesController] Step 3: Warming up browser with {len(warmup_urls)} tabs...")
        try:
            # Use subprocess.Popen instead of Playwright to avoid greenlet
            # thread crash. Playwright's sync API requires main thread (greenlet),
            # but this function is called via run_in_executor (thread pool) from
            # engine.py Phase 2 recovery. subprocess.Popen is fully thread-safe.
            _chrome_exe = _get_chrome_executable()
            if not _chrome_exe:
                # Fallback: try to find system Chrome
                _chrome_exe = self._find_browser("auto")
            
            if not _chrome_exe:
                log.error(f"[ProfilesController] ❌ No Chrome executable found for warmup")
                return False
            
            chrome_args = [
                _chrome_exe,
                f"--user-data-dir={profile_path}",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--start-maximized",
                "--no-sandbox",
            ] + warmup_urls  # Chrome opens each URL as a separate tab
            
            log.info(f"[ProfilesController] Launching: {Path(_chrome_exe).name} with {len(warmup_urls)} URLs")
            proc = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # Wait for Variations Service enrollment + x-client-data generation
            # Chrome needs ~15s of runtime for Variations Service to download
            # config from Google servers and generate x-client-data header.
            log.info(f"[ProfilesController] ⏳ Waiting 15s for Variations enrollment (PID={proc.pid})...")
            time.sleep(15)
            
            # Graceful shutdown: terminate, then force-kill if needed
            log.info(f"[ProfilesController] Closing warmup browser (PID={proc.pid})...")
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            
            log.info(f"[ProfilesController] ✅ Phase 2 warmup complete for {email}")
            return True
            
        except Exception as e:
            log.error(f"[ProfilesController] ❌ Warmup browser error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _find_donor_profile(self, exclude_email: str) -> Optional[Path]:
        """Find a working Chrome profile to donate Variations files.
        
        Looks for a profile that has both 'Local State' and 'Variations' files,
        preferring profiles that are is_ready=True.
        
        Args:
            exclude_email: Email of the profile being reset (skip this one)
            
        Returns:
            Path to donor profile directory, or None
        """
        candidates = []
        for profile in self._profiles:
            if profile.email == exclude_email:
                continue
            profile_path = Path(profile.browser_profile_path) if profile.browser_profile_path else None
            if not profile_path or not profile_path.exists():
                continue
            
            local_state = profile_path / "Local State"
            variations = profile_path / "Variations"
            if local_state.exists() and variations.exists():
                candidates.append((profile, profile_path))
        
        if not candidates:
            return None
        
        # Prefer ready profiles
        ready = [p for p in candidates if p[0].is_ready]
        if ready:
            return ready[0][1]
        return candidates[0][1]
    
    def _copy_variations_files(self, source_path: Path, target_path: Path) -> bool:
        """Copy 'Local State' and 'Variations' from source to target profile.
        
        Args:
            source_path: Path to donor Chrome profile directory
            target_path: Path to target Chrome profile directory
            
        Returns:
            True if both files copied successfully
        """
        import shutil
        
        target_path.mkdir(parents=True, exist_ok=True)
        copied = 0
        
        for filename in ("Local State", "Variations"):
            src = source_path / filename
            dst = target_path / filename
            if src.exists():
                try:
                    shutil.copy2(str(src), str(dst))
                    log.info(f"[ProfilesController] ✅ Copied {filename}: {source_path.name} → {target_path.name}")
                    copied += 1
                except Exception as e:
                    log.error(f"[ProfilesController] ❌ Failed to copy {filename}: {e}")
            else:
                log.warning(f"[ProfilesController] ⚠️ {filename} not found in {source_path.name}")
        
        return copied == 2
    

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
                    log.error(f"[ProfilesController] Cookie read error: {e}")
        
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
                    log.error(f"[ProfilesController] Prefs read error: {e}")
        
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
        log.info(f"[ProfilesController] Session verified for: {email}")
        
        return True
    
    def mark_session_expired(self, email: str) -> bool:
        """Mark session as expired/needs login."""
        return self.update_profile(email, is_ready=False)
    
    def auto_extract_tokens(self, email: str, headless: bool = True) -> bool:
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
            log.warning(f"[ProfilesController] Profile not found: {email}")
            return False
        
        if not profile.profile_path:
            log.info(f"[ProfilesController] No profile path for: {email}")
            return False
        
        log.info(f"[ProfilesController] Extracting tokens for: {email}")
        
        try:
            from core.token_extractor import extract_tokens_sync
            
            tokens = extract_tokens_sync(profile.profile_path, headless=headless)
            
            if tokens and tokens.access_token:
                # Update profile with extracted data
                self.update_profile(
                    email,
                    is_ready=True,
                )
                log.info(f"[ProfilesController] Tokens extracted for: {email}")
                log.info(f"[ProfilesController] Token complete: {tokens.is_complete}")
                return True
            else:
                log.error(f"[ProfilesController] Token extraction failed for: {email}")
                self.update_profile(email, is_ready=False)
                return False
                
        except Exception as e:
            log.error(f"[ProfilesController] Error extracting tokens: {e}")
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
                log.error(f"[ProfilesController] Batch refresh error for {profile.email}: {e}")
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
            
            log.info(f"[ProfilesController] Exported {len(self._profiles)} profiles to {export_path}")
            return True
            
        except Exception as e:
            log.error(f"[ProfilesController] Export failed: {e}")
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
            
            log.info(f"[ProfilesController] Imported {imported} profiles from {import_path}")
            return imported
            
        except Exception as e:
            log.error(f"[ProfilesController] Import failed: {e}")
            return 0
    
    # =========================================================================
    # Persistence
    # =========================================================================
    
    def load_profiles(self) -> List[ChromeProfile]:
        """Load profiles from JSON file."""
        if not self.storage_path.exists():
            log.info(f"[ProfilesController] No profiles file, starting fresh")
            self._profiles = []
            return self._profiles
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self._profiles = [
                ChromeProfile.from_dict(p) 
                for p in data.get("profiles", [])
            ]
            log.info(f"[ProfilesController] Loaded {len(self._profiles)} profiles")
            
        except Exception as e:
            log.error(f"[ProfilesController] Error loading profiles: {e}")
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
            
            log.info(f"[ProfilesController] Saved {len(self._profiles)} profiles")
            
        except Exception as e:
            log.error(f"[ProfilesController] Error saving profiles: {e}")
    
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
                log.error(f"[ProfilesController] Callback error: {e}")
    
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


# ─────────────────────────────────────────────────────────────
# Global singleton — mirrors get_settings() pattern
# ─────────────────────────────────────────────────────────────

_profiles_controller: Optional[ProfilesController] = None


def get_profiles_controller() -> ProfilesController:
    """Get or create the global ProfilesController singleton.
    
    Used by UI components (tab_settings) that need profiles access
    without requiring the full AppController dependency.
    """
    global _profiles_controller
    if _profiles_controller is None:
        _profiles_controller = ProfilesController()
    return _profiles_controller

