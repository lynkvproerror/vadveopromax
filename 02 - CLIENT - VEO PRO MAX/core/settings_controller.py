"""
VEO Pro Max - Settings Controller

Controller for Settings and License tabs.
"""

from typing import Optional, Dict, Any, Callable
from dataclasses import asdict
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import AppSettings
from config.theme import ThemeManager
from security.license_client import LicenseClient, LicenseInfo
from services.permissions import PermissionsSystem, Role, Feature
from core.event_manager import EventType, emit_event


class SettingsController:
    """Controller for application settings.
    
    Manages:
    - Settings load/save
    - Theme switching
    - Output directory configuration
    """
    
    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._theme_manager = ThemeManager()
        
        # Callbacks
        self._on_settings_changed: Optional[Callable[[Dict], None]] = None
        self._on_theme_changed: Optional[Callable[[str], None]] = None
    
    def set_callbacks(
        self,
        on_settings_changed: Optional[Callable[[Dict], None]] = None,
        on_theme_changed: Optional[Callable[[str], None]] = None,
    ):
        """Set UI callbacks."""
        self._on_settings_changed = on_settings_changed
        self._on_theme_changed = on_theme_changed
    
    # === SETTINGS ACCESS ===
    
    def get_all_settings(self) -> Dict:
        """Get all settings as dict."""
        return asdict(self._settings)
    
    def get_setting(self, key: str) -> Any:
        """Get a specific setting value."""
        return getattr(self._settings, key, None)
    
    def set_setting(self, key: str, value: Any) -> bool:
        """Set a specific setting value.
        
        Returns True if successful.
        """
        if not hasattr(self._settings, key):
            return False
        
        setattr(self._settings, key, value)
        self._notify_settings_changed()
        return True
    
    def update_settings(self, updates: Dict[str, Any]) -> int:
        """Update multiple settings.
        
        Returns count of updated settings.
        """
        updated = 0
        for key, value in updates.items():
            if self.set_setting(key, value):
                updated += 1
        
        if updated > 0:
            self.save_settings()
        
        return updated
    
    # === PERSISTENCE ===
    
    def save_settings(self) -> bool:
        """Save settings to file."""
        try:
            self._settings.save()
            emit_event(EventType.SETTINGS_CHANGED, self.get_all_settings())
            return True
        except Exception:
            return False
    
    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        self._settings = AppSettings()
        self._notify_settings_changed()
    
    # === OUTPUT DIRECTORY ===
    
    def get_output_directory(self) -> str:
        """Get current output directory."""
        return str(self._settings.output_dir)
    
    def set_output_directory(self, path: str) -> bool:
        """Set output directory.
        
        Creates directory if it doesn't exist.
        """
        try:
            output_path = Path(path)
            output_path.mkdir(parents=True, exist_ok=True)
            self._settings.output_dir = output_path
            self.save_settings()
            return True
        except Exception:
            return False
    
    # === THEME ===
    
    def get_current_theme(self) -> str:
        """Get current theme name."""
        return self._settings.theme
    
    def set_theme(self, theme_name: str) -> bool:
        """Set application theme."""
        if self._theme_manager.set_theme(theme_name):
            self._settings.theme = theme_name
            self.save_settings()
            
            if self._on_theme_changed:
                self._on_theme_changed(theme_name)
            
            emit_event(EventType.THEME_CHANGED, {"theme": theme_name})
            return True
        return False
    
    def get_available_themes(self) -> list:
        """Get list of available themes."""
        return self._theme_manager.get_available_themes()
    
    # === HELPERS ===
    
    def _notify_settings_changed(self):
        """Notify UI of settings change."""
        if self._on_settings_changed:
            self._on_settings_changed(self.get_all_settings())


class LicenseController:
    """Controller for license management.
    
    Manages:
    - License validation via security/license_client.py
    - Trial status
    - Feature permissions
    """
    
    def __init__(
        self,
        license_client: LicenseClient,
        permissions: PermissionsSystem,
    ):
        self._license_client = license_client
        self._permissions = permissions
        
        # Callbacks
        self._on_license_changed: Optional[Callable[[Dict], None]] = None
        self._on_trial_warning: Optional[Callable[[int], None]] = None
    
    def set_callbacks(
        self,
        on_license_changed: Optional[Callable[[Dict], None]] = None,
        on_trial_warning: Optional[Callable[[int], None]] = None,
    ):
        """Set UI callbacks."""
        self._on_license_changed = on_license_changed
        self._on_trial_warning = on_trial_warning
    
    # === LICENSE STATUS ===
    
    def get_license_status(self) -> Dict:
        """Get current license status."""
        try:
            info = self._license_client.validate()
            from datetime import datetime
            return {
                "is_licensed": info.valid and info.tier and info.tier.value != "TRIA",
                "is_trial": info.tier and info.tier.value == "TRIA" if info.valid else True,
                "tier": info.tier.value if info.tier else None,
                "days_remaining": (info.expires - datetime.now()).days if info.expires else 0,
                "trial_expired": not info.valid and "expired" in (info.error or "").lower(),
                "machine_id": self._license_client.get_display_machine_id(),
            }
        except Exception:
            return {"is_licensed": False, "is_trial": True, "tier": None, "days_remaining": 0}
    
    def get_usage_stats(self) -> Dict:
        """Get usage statistics."""
        usage = self._license_client.usage
        return {
            "total_generations": usage.total_generations,
            "today_generations": usage.today_generations,
            "total_downloads": usage.total_downloads,
        }
    
    # === LICENSE ACTIVATION ===
    
    def activate_license(self, license_key: str) -> Dict:
        """Activate a license key.
        
        Returns dict with success status, message, and tier info.
        """
        try:
            info = self._license_client.activate(license_key)
            
            if info.valid:
                # Update permissions from tier
                if info.tier:
                    self._permissions.set_role_from_tier(info.tier)
                
                # Apply dynamic limits from Firebase _lim
                if hasattr(info, 'limits_override') and info.limits_override:
                    self._permissions.apply_server_limits(info.limits_override)
                
                emit_event(EventType.LICENSE_VALIDATED, {"key": license_key[:8] + "..."})
                self._notify_license_changed()
                
                return {
                    "success": True,
                    "message": f"License activated: {info.tier.name if info.tier else 'Unknown'}",
                    "tier": info.tier.value if info.tier else None,
                    "role": info.role.value if info.role else "trial",
                }
            else:
                return {
                    "success": False,
                    "message": info.error or "Invalid license key",
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Activation failed: {str(e)}",
            }
    
    def deactivate_license(self):
        """Deactivate current license."""
        self._license_client.deactivate()
        self._permissions.set_role(Role.TRIAL)
        self._notify_license_changed()
    
    # === PERMISSIONS ===
    
    def has_feature(self, feature: str) -> bool:
        """Check if feature is available."""
        try:
            f = Feature(feature)
            return self._permissions.has_feature(f)
        except ValueError:
            return False
    
    def get_limits(self) -> Dict:
        """Get current limits."""
        return self._permissions.get_limits_summary()
    
    def get_role(self) -> str:
        """Get current role."""
        return self._permissions.role.value
    
    # === TRIAL ===
    
    def check_trial_warning(self):
        """Check if trial warning should be shown."""
        try:
            info = self._license_client.validate()
            if info.valid and info.tier and info.tier.value == "TRIA":
                from datetime import datetime
                if info.expires:
                    days = (info.expires - datetime.now()).days
                    if days <= 3 and self._on_trial_warning:
                        self._on_trial_warning(days)
                        emit_event(EventType.TRIAL_WARNING, {"days_remaining": days})
        except Exception:
            pass
    
    # === HELPERS ===
    
    def _notify_license_changed(self):
        """Notify UI of license change."""
        if self._on_license_changed:
            self._on_license_changed(self.get_license_status())

