"""
VEO Pro Max - Multi-Account Manager (ĐẠI CHỦ)

Reference: MULTITHREADING_ARCHITECTURE.md
Role: Manages multiple AccountManagers, load balancing, capacity tracking,
      and browser lifecycle for all accounts.

Architecture: Asyncio (Hybrid with ProcessPoolExecutor for CPU tasks)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.session import AccountSession
from core.account_manager import AccountManager

log = logging.getLogger(__name__)


class MultiAccountManager:
    """ĐẠI CHỦ - Manages multiple VEO account managers (CHỦ).
    
    Responsibilities:
    - Track total capacity (N accounts × max_workers each)
    - Load balancing: prefer account with most available workers
    - Account health monitoring
    - Worker allocation coordination
    
    IMPORTANT: ĐẠI CHỦ manages AccountManagers (CHỦ), NOT raw AccountSessions.
    All session access goes through AccountManager layer.
    """
    
    def __init__(self):
        self._accounts: List[AccountManager] = []
        self._lock = asyncio.Lock()
    
    @property
    def total_capacity(self) -> int:
        """Total capacity = N accounts × max_workers."""
        return sum(acc.max_workers for acc in self._accounts)
    
    @property
    def total_available(self) -> int:
        """Sum of available workers from all accounts."""
        return sum(acc.available_workers for acc in self._accounts)
    
    @property
    def total_active(self) -> int:
        """Sum of active workers from all accounts."""
        return sum(acc.active_workers for acc in self._accounts)
    
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
        
        Closes browser before removing.
        Returns True if removed successfully.
        """
        async with self._lock:
            for i, acc in enumerate(self._accounts):
                if acc.email == email:
                    if acc.active_workers > 0:
                        return False
                    await acc.close_browser()
                    self._accounts.pop(i)
                    return True
            return False
    
    def get_account(self, email: str) -> Optional[AccountManager]:
        """Get an account manager by email."""
        for acc in self._accounts:
            if acc.email == email:
                return acc
        return None
    
    def _compute_health_score(self, account: AccountManager) -> int:
        """Compute health score for load balancing.
        
        Score formula:
          + available_workers × 10   (more free workers = better)
          - active_workers × 5       (busy accounts penalized)
          - consecutive_403s × 20  (error-prone accounts avoided)
          + ext_connected × 15     (extension ready = bonus)
        
        Higher score = preferred account.
        """
        available = account.available_workers
        active = account.active_workers
        
        # Get 403 count from adaptive burst controller (if set on engine)
        consecutive_403 = 0
        if hasattr(account, '_consecutive_403'):
            consecutive_403 = account._consecutive_403
        elif hasattr(self, '_burst_controller') and self._burst_controller:
            stats = self._burst_controller.get_stats()
            acc_stats = stats.get("accounts", {}).get(account.email, {})
            consecutive_403 = acc_stats.get("total_403", 0)
        
        # Extension connected bonus
        ext_connected = 0
        if account.extension_bridge:
            ext_connected = 1 if account.extension_bridge.is_connected(account.email) else 0
        
        score = (available * 10) - (active * 5) - (consecutive_403 * 20) + (ext_connected * 15)
        return score
    
    def get_health_scores(self) -> dict:
        """Get health scores for all accounts (for UI dashboard).
        
        Returns:
            {
                "accounts": {
                    "email@gmail.com": {
                        "score": 85,
                        "available_workers": 3,
                        "active_workers": 2,
                        "max_workers": 20,
                        "ext_connected": True,
                        "enabled": True,
                    }
                }
            }
        """
        result = {"accounts": {}}
        for acc in self._accounts:
            ext_connected = False
            if acc.extension_bridge:
                ext_connected = acc.extension_bridge.is_connected(acc.email)
            
            result["accounts"][acc.email] = {
                "score": self._compute_health_score(acc),
                "available_workers": acc.available_workers,
                "active_workers": acc.active_workers,
                "max_workers": acc.max_workers,
                # Backward compat
                "available_slots": acc.available_workers,
                "active_slots": acc.active_workers,
                "max_slots": acc.max_workers,
                "ext_connected": ext_connected,
                "enabled": acc.is_enabled,
            }
        return result
    
    def set_burst_controller(self, controller):
        """Set reference to AdaptiveBurstController for health scoring."""
        self._burst_controller = controller
    
    async def get_available_account(self) -> Optional[AccountManager]:
        """Get the best available account for a new task.
        
        Health-score based load balancing:
        1. Filter accounts that are ready (token valid, reCAPTCHA fresh, has slots)
        2. Compute health score per account  
        3. Prefer highest score; break ties with least recently used
        
        Returns None if no account available.
        """
        async with self._lock:
            ready = [acc for acc in self._accounts if acc.is_ready]
            
            if not ready:
                return None
            
            # Sort by: health_score (desc), last_activity (asc)
            ready.sort(
                key=lambda a: (
                    -self._compute_health_score(a),
                    a.session.last_activity or datetime.min
                )
            )
            
            best = ready[0]
            score = self._compute_health_score(best)
            log.debug(
                f"[LoadBalancer] Selected {best.email} "
                f"(score={score}, workers={best.available_workers}/{best.max_workers})"
            )
            return best
    
    async def acquire_slot(self) -> Optional[AccountManager]:
        """Acquire a worker from the best available account.
        
        Returns the account manager if successful, None if no workers available.
        Deprecated: use acquire_workers() pattern in engine instead.
        """
        account = await self.get_available_account()
        if account and account.acquire_workers(1):
            return account
        return None
    
    async def release_slot(self, email: str):
        """Release a worker from the specified account.
        Deprecated: use account.release_workers(n) directly.
        """
        async with self._lock:
            account = self.get_account(email)
            if account:
                account.release_workers(1)
    
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
    
    async def startup_browsers(self, headless: bool = True):
        """Start persistent browsers for all accounts.
        
        Call this when engine starts. Each CHỦ gets a persistent browser
        for on-demand reCAPTCHA refresh.
        
        Note: Each browser uses ~100-200MB RAM.
        """
        # Seed Variations data to managed profiles BEFORE launching browsers
        # This ensures Chrome has full x-client-data from the start
        self._seed_variations_to_profiles()
        
        log.info(f"Starting browsers for {len(self._accounts)} accounts...")
        for acc in self._accounts:
            try:
                await acc.ensure_browser(headless=headless)
            except Exception as e:
                log.error(f"Failed to start browser for {acc.email}: {e}")
        log.info("All account browsers initialized")
        
        # Cross-pollinate x-client-data: share longest value to accounts with short values
        self.fix_short_client_data()
    
    def _seed_variations_to_profiles(self):
        """Copy Chrome Variations data from default profile to managed profiles.
        
        x-client-data is computed by Chrome's Variations Service from the seed
        stored in 'Local State'. Fresh/managed profiles produce short values (8 chars)
        because they haven't enrolled in Variations yet.
        
        By copying Local State from the user's default Chrome, managed profiles
        inherit the full Variations seed → full x-client-data (50+ chars).
        """
        import os
        import shutil
        
        # Find user's default Chrome Local State
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            return
        default_local_state = os.path.join(
            local_app_data, "Google", "Chrome", "User Data", "Local State"
        )
        if not os.path.isfile(default_local_state):
            log.debug("No default Chrome Local State found — skipping Variations seed")
            return
        
        seeded = 0
        for acc in self._accounts:
            profile_path = acc.session.profile_path
            if not profile_path or not os.path.isdir(profile_path):
                continue
            
            target = os.path.join(profile_path, "Local State")
            try:
                # Only copy if managed profile doesn't have it yet or it's very small
                if not os.path.isfile(target) or os.path.getsize(target) < 1000:
                    shutil.copy2(default_local_state, target)
                    seeded += 1
            except Exception as e:
                log.debug(f"Failed to seed Variations to {profile_path}: {e}")
        
        if seeded:
            log.info(f"🌱 Seeded Chrome Variations data to {seeded} managed profile(s)")
    
    def get_best_client_data(self) -> str:
        """Get the longest x-client-data from any account.
        
        x-client-data is generated by Chrome's Variations Service and depends
        on Chrome version + OS, NOT the Google account. All Chrome instances
        on the same machine should have the same value, but new/fresh profiles
        may have a very short value because Variations hasn't fully enrolled.
        
        Returns the longest x-client-data found, or "" if none available.
        """
        best = ""
        for acc in self._accounts:
            cd = acc.session.client_data or ""
            if len(cd) > len(best):
                best = cd
        return best
    
    def fix_short_client_data(self):
        """Share x-client-data across accounts on the same machine.
        
        Chrome's x-client-data depends on Chrome version + OS, not the
        Google account. When one profile has a short value (Variations
        Service not loaded), we can safely borrow from another profile
        that has the full value.
        
        Note: No longer launches temp Chrome for extraction — Extension
        bridge provides x-client-data from the managed browser's headers.
        Cross-pollination is triggered again when Extension sends fresh data.
        
        This fixes reCAPTCHA 403 errors caused by short x-client-data.
        """
        MIN_GOOD = 20  # Full x-client-data is typically 50+ chars
        best = self.get_best_client_data()
        
        if len(best) < MIN_GOOD:
            # Don't launch temp Chrome — Extension will provide data shortly
            log.info(
                f"⏳ No account has good x-client-data yet (best={len(best)} chars). "
                f"Extension bridge will provide fresh value from browser headers."
            )
            return
        
        fixed = 0
        for acc in self._accounts:
            cd = acc.session.client_data or ""
            if len(cd) < MIN_GOOD:
                log.info(
                    f"🔄 [{acc.email}] x-client-data too short ({len(cd)} chars), "
                    f"borrowing from pool ({len(best)} chars)"
                )
                acc.session.client_data = best
                fixed += 1
        
        if fixed:
            log.info(f"✅ Fixed x-client-data for {fixed} account(s)")
    
    async def shutdown_browsers(self):
        """Close all persistent browsers.
        
        Call this on engine stop or application exit.
        """
        log.info("Shutting down all account browsers...")
        for acc in self._accounts:
            try:
                await acc.close_browser()
            except Exception as e:
                log.error(f"Failed to close browser for {acc.email}: {e}")
        log.info("All browsers closed")
    
    async def clear_all(self):
        """Clear all accounts (for testing/reset)."""
        async with self._lock:
            if self.total_active == 0:
                # Shutdown pools + browsers first
                await self.shutdown_browsers()
                self._accounts.clear()
