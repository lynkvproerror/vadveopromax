"""
Permissions v1.0 - Role-based feature visibility

This module provides easy-to-use functions to check feature visibility
based on user role from the license system.

Usage in VEO App:
    from permissions import Permissions
    
    perms = Permissions()
    
    # In UI code:
    if perms.can_see_dev_console():
        self.tab_bar.add_tab("Dev Console", dev_console_tab)
"""

from license_client import LicenseClient, UserRole


class Permissions:
    """
    Permission manager for role-based feature visibility.
    
    Roles:
        TRIAL (0): Limited features
        PREMIUM (1): Full features (paid users)
        TESTER (2): Full features + Dev tools + Beta
    """
    
    def __init__(self, client: LicenseClient = None):
        self._client = client or LicenseClient()
        self._cached_role: UserRole = None
    
    def _get_role(self) -> UserRole:
        """Get current role (cached for performance)"""
        if self._cached_role is None:
            self._cached_role = self._client.get_role()
        return self._cached_role
    
    def refresh(self):
        """Refresh cached role (call on license change)"""
        self._cached_role = None
    
    # =========================
    # Feature Visibility
    # =========================
    
    def can_see_dev_console(self) -> bool:
        """Dev Console tab: TESTER only"""
        return self._get_role() == UserRole.TESTER
    
    def can_see_beta_features(self) -> bool:
        """Beta features: TESTER only"""
        return self._get_role() == UserRole.TESTER
    
    def can_see_advanced_settings(self) -> bool:
        """Advanced Settings section: TESTER only"""
        return self._get_role() == UserRole.TESTER
    
    def can_see_debug_info(self) -> bool:
        """Debug info overlay: TESTER only"""
        return self._get_role() == UserRole.TESTER
    
    # =========================
    # Feature Limits
    # =========================
    
    def get_max_cookies(self) -> int:
        """Max browser cookies allowed"""
        role = self._get_role()
        if role == UserRole.TRIAL:
            return 1
        return 999  # Unlimited for Premium/Tester
    
    def get_max_foremen(self) -> int:
        """Max concurrent foremen allowed"""
        role = self._get_role()
        if role == UserRole.TRIAL:
            return 2
        return 99  # Unlimited for Premium/Tester
    
    def get_max_prompts(self) -> int:
        """Max prompts per queue"""
        role = self._get_role()
        if role == UserRole.TRIAL:
            return 10
        return 9999  # Unlimited for Premium/Tester


# Singleton instance for easy access
_permissions = None

def get_permissions() -> Permissions:
    """Get global Permissions instance"""
    global _permissions
    if _permissions is None:
        _permissions = Permissions()
    return _permissions
