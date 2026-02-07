"""
VEO Pro Max - Multi-Account Manager (ĐẠI CHỦ)

Reference: MULTITHREADING_ARCHITECTURE.md
Role: Manages multiple AccountManagers, load balancing, capacity tracking

Architecture: Asyncio (Hybrid with ProcessPoolExecutor for CPU tasks)
"""

from typing import Optional, List
from datetime import datetime
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession
from core.account_manager import AccountManager


class MultiAccountManager:
    """ĐẠI CHỦ - Manages multiple VEO account managers (CHỦ).
    
    Responsibilities:
    - Track total capacity (N accounts × 4 slots each)
    - Load balancing: prefer account with most available slots
    - Account health monitoring
    - Slot allocation coordination
    
    IMPORTANT: ĐẠI CHỦ manages AccountManagers (CHỦ), NOT raw AccountSessions.
    All session access goes through AccountManager layer.
    """
    
    def __init__(self):
        self._accounts: List[AccountManager] = []
        self._lock = asyncio.Lock()
    
    @property
    def total_capacity(self) -> int:
        """Total capacity = N accounts × 4 slots."""
        return len(self._accounts) * AccountManager.MAX_SLOTS
    
    @property
    def total_available(self) -> int:
        """Sum of available slots from all accounts."""
        return sum(acc.available_slots for acc in self._accounts)
    
    @property
    def total_active(self) -> int:
        """Sum of active slots from all accounts."""
        return sum(acc.active_slots for acc in self._accounts)
    
    @property
    def account_count(self) -> int:
        """Number of registered accounts."""
        return len(self._accounts)
    
    @property
    def ready_accounts(self) -> List[AccountManager]:
        """Get account managers that are ready for API calls."""
        return [acc for acc in self._accounts if acc.is_ready]
    
    async def add_account(self, session: AccountSession) -> bool:
        """Add a new account to the pool.
        
        Wraps the AccountSession in an AccountManager automatically.
        Returns True if added successfully.
        """
        async with self._lock:
            # Check for duplicate email
            if any(acc.email == session.email for acc in self._accounts):
                return False
            
            manager = AccountManager(session)
            self._accounts.append(manager)
            return True
    
    async def remove_account(self, email: str) -> bool:
        """Remove an account from the pool.
        
        Returns True if removed successfully.
        """
        async with self._lock:
            for i, acc in enumerate(self._accounts):
                if acc.email == email:
                    # Don't remove if has active slots
                    if acc.active_slots > 0:
                        return False
                    self._accounts.pop(i)
                    return True
            return False
    
    def get_account(self, email: str) -> Optional[AccountManager]:
        """Get an account manager by email."""
        for acc in self._accounts:
            if acc.email == email:
                return acc
        return None
    
    async def get_available_account(self) -> Optional[AccountManager]:
        """Get the best available account for a new task.
        
        Load balancing strategy:
        1. Filter accounts that are ready (token valid, reCAPTCHA fresh, has slots)
        2. Prefer account with most available slots
        3. Among equal slots, prefer least recently used
        
        Returns None if no account available.
        """
        async with self._lock:
            ready = [acc for acc in self._accounts if acc.is_ready]
            
            if not ready:
                return None
            
            # Sort by: available_slots (desc), last_activity (asc)
            ready.sort(
                key=lambda a: (
                    -a.available_slots,
                    a.session.last_activity or datetime.min
                )
            )
            
            return ready[0]
    
    async def acquire_slot(self) -> Optional[AccountManager]:
        """Acquire a slot from the best available account.
        
        Returns the account manager if successful, None if no slots available.
        """
        account = await self.get_available_account()
        if account and account.acquire_slot():
            return account
        return None
    
    async def release_slot(self, email: str):
        """Release a slot from the specified account."""
        async with self._lock:
            account = self.get_account(email)
            if account:
                account.release_slot()
    
    def get_accounts_needing_refresh(self) -> List[AccountManager]:
        """Get accounts that need token or reCAPTCHA refresh."""
        return [
            acc for acc in self._accounts
            if acc.session.is_token_expired or acc.session.needs_recaptcha_refresh
        ]
    
    def get_status_summary(self) -> dict:
        """Get summary of all accounts' status."""
        return {
            "total_accounts": self.account_count,
            "total_capacity": self.total_capacity,
            "total_available": self.total_available,
            "total_active": self.total_active,
            "ready_accounts": len(self.ready_accounts),
            "accounts": [acc.get_status() for acc in self._accounts]
        }
    
    async def clear_all(self):
        """Clear all accounts (for testing/reset)."""
        async with self._lock:
            # Only clear if no active slots
            if self.total_active == 0:
                self._accounts.clear()
