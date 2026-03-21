"""
VEO Pro Max - Account Browser Integration

Integrates browser sessions with account management.
"""

from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import asyncio
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.session import AccountSession
from core.browser_manager import BrowserManager, BrowserSession, BrowserConfig, BrowserState
from core.veo_automation import VEOAutomationHandler, VEOGenerationRequest, VEOGenerationResult
from core.event_manager import EventType, emit_event


@dataclass
class AccountBrowserMapping:
    """Maps account session to browser session."""
    account: AccountSession
    browser_session: Optional[BrowserSession] = None
    is_active: bool = False
    last_used: Optional[datetime] = None
    consecutive_errors: int = 0


class AccountBrowserIntegration:
    """Integrate browser automation with account management.
    
    Features:
    - Map accounts to browser sessions
    - Manage browser lifecycle per account
    - Handle session rotation
    - Track browser health
    """
    
    MAX_CONSECUTIVE_ERRORS = 3
    
    def __init__(self, browser_config: Optional[BrowserConfig] = None):
        self._config = browser_config or BrowserConfig()
        self._browser = BrowserManager(self._config)
        self._automation = VEOAutomationHandler(self._browser)
        
        # Account mappings
        self._mappings: Dict[str, AccountBrowserMapping] = {}
        
        # Currently processing accounts
        self._active_accounts: List[str] = []
        
        # Callbacks
        self._on_generation_complete: Optional[Callable[[str, VEOGenerationResult], None]] = None
        self._on_account_error: Optional[Callable[[str, str], None]] = None
    
    @property
    def browser(self) -> BrowserManager:
        return self._browser
    
    @property
    def automation(self) -> VEOAutomationHandler:
        return self._automation
    
    def set_callbacks(
        self,
        on_generation_complete: Optional[Callable[[str, VEOGenerationResult], None]] = None,
        on_account_error: Optional[Callable[[str, str], None]] = None,
    ):
        """Set callbacks."""
        self._on_generation_complete = on_generation_complete
        self._on_account_error = on_account_error
    
    async def initialize(self) -> bool:
        """Initialize browser automation.
        
        Returns True if successful.
        """
        try:
            return await self._browser.launch()
        except Exception:
            return False
    
    async def shutdown(self):
        """Shutdown all browser sessions."""
        for email in list(self._mappings.keys()):
            await self.release_account(email)
        
        await self._browser.close()
    
    async def register_account(
        self,
        account: AccountSession,
    ) -> bool:
        """Register an account for browser automation.
        
        Args:
            account: Account session to register
        
        Returns:
            True if successful
        """
        if account.email in self._mappings:
            return True  # Already registered
        
        self._mappings[account.email] = AccountBrowserMapping(
            account=account,
        )
        
        return True
    
    async def acquire_account(self, email: str) -> Optional[BrowserSession]:
        """Acquire a browser session for an account.
        
        Creates browser session if needed.
        
        Returns:
            BrowserSession if successful
        """
        mapping = self._mappings.get(email)
        if not mapping:
            return None
        
        if mapping.is_active:
            return mapping.browser_session  # Already active
        
        # Check if account is healthy
        if mapping.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
            return None
        
        # Create browser session
        session = await self._browser.create_session(
            email=email,
            profile_path=mapping.account.profile_path,
        )
        
        if not session:
            mapping.consecutive_errors += 1
            return None
        
        # Navigate to VEO
        if not await self._browser.navigate_to_veo(session.id):
            await self._browser.close_session(session.id)
            mapping.consecutive_errors += 1
            return None
        
        mapping.browser_session = session
        mapping.is_active = True
        mapping.last_used = datetime.now()
        self._active_accounts.append(email)
        
        emit_event(
            EventType.ACCOUNT_ADDED,
            {"email": email, "session_id": session.id},
        )
        
        return session
    
    async def release_account(self, email: str):
        """Release a browser session for an account."""
        mapping = self._mappings.get(email)
        if not mapping:
            return
        
        if mapping.browser_session:
            await self._browser.close_session(mapping.browser_session.id)
        
        mapping.browser_session = None
        mapping.is_active = False
        
        if email in self._active_accounts:
            self._active_accounts.remove(email)
    
    async def execute_generation(
        self,
        email: str,
        request: VEOGenerationRequest,
    ) -> Optional[VEOGenerationResult]:
        """Execute a generation using account's browser session.
        
        Args:
            email: Account email
            request: Generation request
        
        Returns:
            VEOGenerationResult if successful
        """
        session = await self.acquire_account(email)
        if not session:
            return VEOGenerationResult(
                success=False,
                request=request,
                error="Could not acquire browser session",
            )
        
        try:
            result = await self._automation.generate(session, request)
            
            mapping = self._mappings.get(email)
            if mapping:
                mapping.last_used = datetime.now()
                if result.success:
                    mapping.consecutive_errors = 0
                else:
                    mapping.consecutive_errors += 1
            
            if self._on_generation_complete:
                self._on_generation_complete(email, result)
            
            return result
            
        except Exception as e:
            mapping = self._mappings.get(email)
            if mapping:
                mapping.consecutive_errors += 1
            
            if self._on_account_error:
                self._on_account_error(email, str(e))
            
            return VEOGenerationResult(
                success=False,
                request=request,
                error=str(e),
            )
    
    def get_available_accounts(self) -> List[str]:
        """Get list of available (non-errored) accounts."""
        return [
            email for email, mapping in self._mappings.items()
            if mapping.consecutive_errors < self.MAX_CONSECUTIVE_ERRORS
        ]
    
    def get_active_accounts(self) -> List[str]:
        """Get list of active accounts with browser sessions."""
        return list(self._active_accounts)
    
    def get_account_status(self, email: str) -> Dict:
        """Get status of an account."""
        mapping = self._mappings.get(email)
        if not mapping:
            return {"registered": False}
        
        return {
            "registered": True,
            "is_active": mapping.is_active,
            "session_id": mapping.browser_session.id if mapping.browser_session else None,
            "last_used": mapping.last_used.isoformat() if mapping.last_used else None,
            "consecutive_errors": mapping.consecutive_errors,
            "is_healthy": mapping.consecutive_errors < self.MAX_CONSECUTIVE_ERRORS,
        }
    
    def reset_account_errors(self, email: str):
        """Reset error count for an account."""
        mapping = self._mappings.get(email)
        if mapping:
            mapping.consecutive_errors = 0
    
    async def rotate_session(self, email: str) -> bool:
        """Rotate browser session for an account.
        
        Closes current session and creates new one.
        
        Returns:
            True if successful
        """
        await self.release_account(email)
        session = await self.acquire_account(email)
        return session is not None
