"""
VEO Pro Max - Permissions System

Reference: SESSION_06_WORKFLOWS_SECURITY.md
Role: Role-based feature gating
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Set
from enum import Enum
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.constants import LicenseTier


class Role(str, Enum):
    """User roles."""
    TRIAL = "trial"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    PREMIUM = "premium"
    TESTER = "tester"
    ADMIN = "admin"


class Feature(str, Enum):
    """Application features."""
    # Generation
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    REF_TO_VIDEO = "ref_to_video"
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    CONTINUATION = "continuation"
    
    # Advanced
    BATCH_PROCESSING = "batch_processing"
    MULTI_ACCOUNT = "multi_account"
    AUTO_UPSCALE = "auto_upscale"
    DOWNLOAD_4K = "download_4k"
    
    # UI
    DEV_CONSOLE = "dev_console"
    QUEUE_MANAGER = "queue_manager"
    IMAGE_LIBRARY = "image_library"
    
    # Settings
    CUSTOM_OUTPUT = "custom_output"
    ADVANCED_SETTINGS = "advanced_settings"


@dataclass
class RoleLimits:
    """Limits for a role."""
    max_cookies: int = 1
    max_threads: int = 2
    max_prompts_per_batch: int = 10
    max_outputs_per_prompt: int = 2
    daily_generation_limit: int = 20
    features: Set[Feature] = field(default_factory=set)


class PermissionsSystem:
    """Role-based feature gating.
    
    Features:
    - Role-based access control
    - Feature gating per role
    - Trial limits enforcement
    """
    
    # Role → Limits mapping
    ROLE_LIMITS: Dict[Role, RoleLimits] = {
        Role.TRIAL: RoleLimits(
            max_cookies=1,
            max_threads=2,
            max_prompts_per_batch=10,
            max_outputs_per_prompt=2,
            daily_generation_limit=20,
            features={
                Feature.TEXT_TO_VIDEO,
                Feature.QUEUE_MANAGER,
            },
        ),
        Role.BASIC: RoleLimits(
            max_cookies=2,
            max_threads=4,
            max_prompts_per_batch=50,
            max_outputs_per_prompt=4,
            daily_generation_limit=100,
            features={
                Feature.TEXT_TO_VIDEO,
                Feature.IMAGE_TO_VIDEO,
                Feature.TEXT_TO_IMAGE,
                Feature.QUEUE_MANAGER,
                Feature.CUSTOM_OUTPUT,
            },
        ),
        Role.PROFESSIONAL: RoleLimits(
            max_cookies=5,
            max_threads=8,
            max_prompts_per_batch=200,
            max_outputs_per_prompt=4,
            daily_generation_limit=500,
            features={
                Feature.TEXT_TO_VIDEO,
                Feature.IMAGE_TO_VIDEO,
                Feature.REF_TO_VIDEO,
                Feature.TEXT_TO_IMAGE,
                Feature.IMAGE_TO_IMAGE,
                Feature.CONTINUATION,
                Feature.BATCH_PROCESSING,
                Feature.MULTI_ACCOUNT,
                Feature.QUEUE_MANAGER,
                Feature.IMAGE_LIBRARY,
                Feature.CUSTOM_OUTPUT,
                Feature.ADVANCED_SETTINGS,
            },
        ),
        Role.PREMIUM: RoleLimits(
            max_cookies=10,
            max_threads=16,
            max_prompts_per_batch=1000,
            max_outputs_per_prompt=4,
            daily_generation_limit=-1,  # Unlimited
            features={
                Feature.TEXT_TO_VIDEO,
                Feature.IMAGE_TO_VIDEO,
                Feature.REF_TO_VIDEO,
                Feature.TEXT_TO_IMAGE,
                Feature.IMAGE_TO_IMAGE,
                Feature.CONTINUATION,
                Feature.BATCH_PROCESSING,
                Feature.MULTI_ACCOUNT,
                Feature.AUTO_UPSCALE,
                Feature.DOWNLOAD_4K,
                Feature.QUEUE_MANAGER,
                Feature.IMAGE_LIBRARY,
                Feature.CUSTOM_OUTPUT,
                Feature.ADVANCED_SETTINGS,
            },
        ),
        Role.TESTER: RoleLimits(
            max_cookies=10,
            max_threads=16,
            max_prompts_per_batch=100,
            max_outputs_per_prompt=4,
            daily_generation_limit=100,
            features={
                Feature.TEXT_TO_VIDEO,
                Feature.IMAGE_TO_VIDEO,
                Feature.REF_TO_VIDEO,
                Feature.TEXT_TO_IMAGE,
                Feature.IMAGE_TO_IMAGE,
                Feature.CONTINUATION,
                Feature.BATCH_PROCESSING,
                Feature.MULTI_ACCOUNT,
                Feature.DEV_CONSOLE,
                Feature.QUEUE_MANAGER,
                Feature.IMAGE_LIBRARY,
                Feature.CUSTOM_OUTPUT,
                Feature.ADVANCED_SETTINGS,
            },
        ),
        Role.ADMIN: RoleLimits(
            max_cookies=-1,  # Unlimited
            max_threads=-1,
            max_prompts_per_batch=-1,
            max_outputs_per_prompt=4,
            daily_generation_limit=-1,
            features=set(Feature),  # All features
        ),
    }
    
    def __init__(self, default_role: Role = Role.TRIAL):
        self._current_role = default_role
        self._custom_features: Set[Feature] = set()
    
    @property
    def role(self) -> Role:
        return self._current_role
    
    @property
    def limits(self) -> RoleLimits:
        return self.ROLE_LIMITS.get(self._current_role, self.ROLE_LIMITS[Role.TRIAL])
    
    def set_role(self, role: Role):
        """Set current role."""
        self._current_role = role
    
    def set_role_from_tier(self, tier: LicenseTier):
        """Set role from license tier."""
        tier_to_role = {
            LicenseTier.TRIAL: Role.TRIAL,
            LicenseTier.BASIC: Role.BASIC,
            LicenseTier.PROFESSIONAL: Role.PROFESSIONAL,
            LicenseTier.PREMIUM: Role.PREMIUM,
            LicenseTier.LIFETIME: Role.PREMIUM,
        }
        self._current_role = tier_to_role.get(tier, Role.TRIAL)
    
    def has_feature(self, feature: Feature) -> bool:
        """Check if current role has a feature."""
        if feature in self._custom_features:
            return True
        return feature in self.limits.features
    
    def grant_feature(self, feature: Feature):
        """Grant a custom feature (temporary override)."""
        self._custom_features.add(feature)
    
    def revoke_feature(self, feature: Feature):
        """Revoke a custom feature."""
        self._custom_features.discard(feature)
    
    def check_limit(self, limit_name: str, current_value: int) -> bool:
        """Check if a limit is exceeded.
        
        Args:
            limit_name: Name of the limit (e.g., 'max_cookies')
            current_value: Current usage value
        
        Returns:
            True if within limits, False if exceeded
        """
        limit_value = getattr(self.limits, limit_name, None)
        if limit_value is None:
            return True
        
        if limit_value == -1:  # Unlimited
            return True
        
        return current_value < limit_value
    
    def get_remaining(self, limit_name: str, current_value: int) -> int:
        """Get remaining quota for a limit.
        
        Returns -1 for unlimited.
        """
        limit_value = getattr(self.limits, limit_name, None)
        if limit_value is None or limit_value == -1:
            return -1
        
        return max(0, limit_value - current_value)
    
    def can_access_dev_console(self) -> bool:
        """Check if user can access dev console."""
        return self.has_feature(Feature.DEV_CONSOLE)
    
    def can_use_multi_account(self) -> bool:
        """Check if user can use multiple accounts."""
        return self.has_feature(Feature.MULTI_ACCOUNT)
    
    def can_batch_process(self) -> bool:
        """Check if user can do batch processing."""
        return self.has_feature(Feature.BATCH_PROCESSING)
    
    def get_feature_status(self) -> Dict[str, bool]:
        """Get status of all features."""
        return {
            feature.value: self.has_feature(feature)
            for feature in Feature
        }
    
    def get_limits_summary(self) -> Dict[str, int]:
        """Get all limits as dict."""
        limits = self.limits
        return {
            "max_cookies": limits.max_cookies,
            "max_threads": limits.max_threads,
            "max_prompts_per_batch": limits.max_prompts_per_batch,
            "max_outputs_per_prompt": limits.max_outputs_per_prompt,
            "daily_generation_limit": limits.daily_generation_limit,
        }
