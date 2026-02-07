"""
VEO Pro Max - Browser Manager

Playwright-based browser automation for VEO.
"""

from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum
import asyncio
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Playwright imports
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


class BrowserState(str, Enum):
    """Browser state."""
    CLOSED = "closed"
    LAUNCHING = "launching"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class BrowserConfig:
    """Browser configuration."""
    headless: bool = True
    profile_path: Optional[str] = None
    use_persistent: bool = False
    timeout_ms: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: Optional[str] = None
    proxy: Optional[str] = None
    slow_mo: int = 0  # Slow down by ms for debugging
    
    # Anti-detection
    use_stealth: bool = True
    humanize_actions: bool = True
    min_action_delay: int = 100
    max_action_delay: int = 500


@dataclass
class BrowserSession:
    """A browser session."""
    id: str
    email: str
    profile_path: str
    state: BrowserState = BrowserState.CLOSED
    page: Optional["Page"] = None
    context: Optional["BrowserContext"] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    error: Optional[str] = None


class BrowserManager:
    """Manage browser instances for VEO automation.
    
    Features:
    - Launch persistent or incognito browsers
    - Anti-detection measures
    - Multiple session management
    - Humanized action delays
    """
    
    VEO_URL = "https://aistudio.google.com/app/generate/video"
    
    def __init__(self, config: Optional[BrowserConfig] = None):
        if not HAS_PLAYWRIGHT:
            raise ImportError("Playwright not installed. Run: pip install playwright && playwright install chromium")
        
        self._config = config or BrowserConfig()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._sessions: Dict[str, BrowserSession] = {}
        self._state = BrowserState.CLOSED
        
        # Callbacks
        self._on_state_changed: Optional[Callable[[BrowserState], None]] = None
        self._on_session_ready: Optional[Callable[[str], None]] = None
    
    @property
    def state(self) -> BrowserState:
        return self._state
    
    @property
    def is_ready(self) -> bool:
        return self._state == BrowserState.READY
    
    def set_callbacks(
        self,
        on_state_changed: Optional[Callable[[BrowserState], None]] = None,
        on_session_ready: Optional[Callable[[str], None]] = None,
    ):
        """Set event callbacks."""
        self._on_state_changed = on_state_changed
        self._on_session_ready = on_session_ready
    
    def _set_state(self, state: BrowserState):
        """Update state and notify."""
        self._state = state
        if self._on_state_changed:
            self._on_state_changed(state)
    
    async def launch(self) -> bool:
        """Launch browser (non-persistent mode).
        
        Returns True if successful.
        """
        if self._state != BrowserState.CLOSED:
            return False
        
        self._set_state(BrowserState.LAUNCHING)
        
        try:
            self._playwright = await async_playwright().start()
            
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
            
            self._browser = await self._playwright.chromium.launch(
                channel="chrome",  # Use real Chrome instead of Chromium
                headless=self._config.headless,
                args=launch_args,
                slow_mo=self._config.slow_mo,
            )
            
            self._set_state(BrowserState.READY)
            return True
            
        except Exception as e:
            self._set_state(BrowserState.ERROR)
            return False
    
    async def close(self):
        """Close browser and all sessions."""
        for session_id in list(self._sessions.keys()):
            await self.close_session(session_id)
        
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        
        self._set_state(BrowserState.CLOSED)
    
    async def create_session(
        self,
        email: str,
        profile_path: Optional[str] = None,
    ) -> Optional[BrowserSession]:
        """Create a new browser session.
        
        Args:
            email: Account email for identification
            profile_path: Chrome profile path for persistent session
        
        Returns:
            BrowserSession if successful
        """
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{email[:8]}"
        
        try:
            if profile_path and self._config.use_persistent:
                # Persistent context
                context = await self._playwright.chromium.launch_persistent_context(
                    profile_path,
                    channel="chrome",  # Use real Chrome instead of Chromium
                    headless=self._config.headless,
                    viewport={"width": self._config.viewport_width, "height": self._config.viewport_height},
                    user_agent=self._config.user_agent,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                page = context.pages[0] if context.pages else await context.new_page()
            else:
                # Incognito context
                if not self._browser:
                    await self.launch()
                
                context = await self._browser.new_context(
                    viewport={"width": self._config.viewport_width, "height": self._config.viewport_height},
                    user_agent=self._config.user_agent,
                )
                page = await context.new_page()
            
            # Apply stealth if enabled
            if self._config.use_stealth:
                await self._apply_stealth(page)
            
            session = BrowserSession(
                id=session_id,
                email=email,
                profile_path=profile_path or "",
                state=BrowserState.READY,
                page=page,
                context=context,
            )
            
            self._sessions[session_id] = session
            
            if self._on_session_ready:
                self._on_session_ready(session_id)
            
            return session
            
        except Exception as e:
            return None
    
    async def close_session(self, session_id: str):
        """Close a browser session."""
        session = self._sessions.get(session_id)
        if not session:
            return
        
        try:
            if session.context:
                await session.context.close()
        except Exception:
            pass
        
        session.state = BrowserState.CLOSED
        del self._sessions[session_id]
    
    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def get_sessions(self) -> List[BrowserSession]:
        """Get all active sessions."""
        return list(self._sessions.values())
    
    async def _apply_stealth(self, page: "Page"):
        """Apply anti-detection measures."""
        await page.add_init_script("""
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });
            
            // Add language
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Hide automation
            window.chrome = {
                runtime: {},
            };
            
            // Permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
    
    async def navigate_to_veo(self, session_id: str) -> bool:
        """Navigate session to VEO page.
        
        Returns True if successful.
        """
        session = self._sessions.get(session_id)
        if not session or not session.page:
            return False
        
        try:
            await session.page.goto(
                self.VEO_URL,
                wait_until="networkidle",
                timeout=self._config.timeout_ms,
            )
            session.last_used = datetime.now()
            return True
        except Exception:
            return False
    
    async def humanized_delay(self):
        """Add random delay for human-like behavior."""
        if not self._config.humanize_actions:
            return
        
        import random
        delay = random.randint(
            self._config.min_action_delay,
            self._config.max_action_delay
        )
        await asyncio.sleep(delay / 1000.0)
    
    async def humanized_click(self, page: "Page", selector: str):
        """Click with human-like delay."""
        await self.humanized_delay()
        await page.click(selector)
        await self.humanized_delay()
    
    async def humanized_type(self, page: "Page", selector: str, text: str):
        """Type with human-like delays."""
        await self.humanized_delay()
        
        # Type character by character with small delays
        element = page.locator(selector)
        await element.click()
        
        for char in text:
            await element.type(char, delay=50)
        
        await self.humanized_delay()
