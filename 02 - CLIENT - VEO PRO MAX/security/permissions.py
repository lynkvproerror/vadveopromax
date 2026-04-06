"""
DEPRECATED - DO NOT USE - Runtime uses services/permissions.py
Permissions v2.0 - Hardened Role-based Feature Visibility (LEGACY MODULE)

Security hardening (v2.0):
- No permanent role cache — re-queries LicenseClient per call (60s TTL in LicenseClient)
- Cross-validates role with AppController._tamper_detected flag
- Methods are not simple pass-through — inline checks prevent single-point patch

Usage in VEO App:
    from permissions import Permissions
    
    perms = Permissions()
    
    # In UI code:
    if perms.can_see_dev_console():
        self.tab_bar.add_tab("Dev Console", dev_console_tab)
"""

try:
    from security.license_client import LicenseClient, UserRole
except ImportError:
    from license_client import LicenseClient, UserRole


class Permissions:
    """
    Hardened permission manager for role-based feature visibility.
    
    Security layers:
    1. Role from LicenseClient (re-queried each call, 60s cache in LicenseClient)
    2. Tamper detection cross-check (via AppController flag)
    3. No single-point-of-failure — each method validates independently
    """
    
    def __init__(self, client: LicenseClient = None):
        self._client = client or LicenseClient()
        self._app_controller = None  # Set by AppController after init
    
    def _is_tampered(self) -> bool:
        """Check if anti-tamper guards detected tampering."""
        if self._app_controller and getattr(self._app_controller, '_tamper_detected', False):
            return True
        return False
    
    def _get_role(self) -> UserRole:
        """Get current role — always re-query, never cache permanently."""
        if self._is_tampered():
            return UserRole.TRIAL  # Force TRIAL on tamper
        try:
            return self._client.get_role()
        except Exception:
            return UserRole.TRIAL  # Safe default
    
    def refresh(self):
        """Force license re-validation on next role check."""
        try:
            self._client._invalidate_validate_cache()
        except Exception:
            pass
    
    # =========================
    # Feature Visibility
    # =========================
    
    def can_see_dev_console(self) -> bool:
        """Dev Console tab: TESTER only, tamper-proof"""
        if self._is_tampered():
            return False
        return self._get_role() == UserRole.TESTER
    
    def can_see_beta_features(self) -> bool:
        """Beta features: TESTER only"""
        if self._is_tampered():
            return False
        return self._get_role() == UserRole.TESTER
    
    def can_see_advanced_settings(self) -> bool:
        """Advanced Settings section: TESTER only"""
        if self._is_tampered():
            return False
        return self._get_role() == UserRole.TESTER
    
    def can_see_debug_info(self) -> bool:
        """Debug info overlay: TESTER only"""
        if self._is_tampered():
            return False
        return self._get_role() == UserRole.TESTER
    
    # =========================
    # Feature Limits
    # =========================
    
    def get_max_accounts(self) -> int:
        """Max accounts allowed — cross-validated"""
        if self._is_tampered():
            return 1
        role = self._get_role()
        if role == UserRole.TRIAL:
            return 1
        return 999  # Unlimited for Premium/Tester
    
    def get_max_foremen(self) -> int:
        """Max concurrent foremen allowed — cross-validated"""
        if self._is_tampered():
            return 1
        role = self._get_role()
        if role == UserRole.TRIAL:
            return 2
        return 99  # Unlimited for Premium/Tester
    
    def get_max_prompts(self) -> int:
        """Max prompts per queue — cross-validated"""
        if self._is_tampered():
            return 3
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
