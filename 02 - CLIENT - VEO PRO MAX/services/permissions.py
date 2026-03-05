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
    """User roles — v2.2: Only 3 roles per LICENSE_TIERS_FEATURES.md"""
    TRIAL = "trial"        # 0 — Limited features during trial period
    PREMIUM = "premium"    # 1 — Full features for paid users (all tiers)
    TESTER = "tester"      # 2 — Full + Dev Console + Beta (trusted testers)


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
    BETA_FEATURES = "beta_features"


@dataclass
class RoleLimits:
    """Limits for a role."""
    max_accounts: int = 1
    max_foremen: int = 2          # Max concurrent foremen (submit workers)
    max_workers_per_account: int = 20  # Max workers per account
    max_prompts_per_batch: int = 10
    max_outputs_per_prompt: int = 4
    daily_generation_limit: int = 100
    features: Set[Feature] = field(default_factory=set)


class PermissionsSystem:
    """Role-based feature gating.
    
    Roles (v2.2 — per LICENSE_TIERS_FEATURES.md):
    - TRIAL (0): 1 cookie, 2 foremen, 10 prompts
    - PREMIUM (1): Unlimited (all paid tiers)
    - TESTER (2): Unlimited + Dev Console + Beta
    """
    
    # Role → Limits mapping (per docs)
    ROLE_LIMITS: Dict[Role, RoleLimits] = {
        Role.TRIAL: RoleLimits(
            max_accounts=1,
            max_foremen=2,          # Trial: max 2 concurrent foremen
            max_workers_per_account=8,
            max_prompts_per_batch=10,
            max_outputs_per_prompt=4,
            daily_generation_limit=100,
            features={
                Feature.TEXT_TO_VIDEO,
                Feature.IMAGE_TO_VIDEO,
                Feature.REF_TO_VIDEO,
                Feature.TEXT_TO_IMAGE,
                Feature.IMAGE_TO_IMAGE,
                Feature.QUEUE_MANAGER,
                Feature.AUTO_UPSCALE,
                Feature.DOWNLOAD_4K,
                Feature.BATCH_PROCESSING,
                Feature.MULTI_ACCOUNT,
                Feature.IMAGE_LIBRARY,
                Feature.CUSTOM_OUTPUT,
                Feature.ADVANCED_SETTINGS,
                # NOT included: CONTINUATION, DEV_CONSOLE, BETA_FEATURES
            },
        ),
        Role.PREMIUM: RoleLimits(
            max_accounts=-1,      # Unlimited
            max_foremen=-1,      # Unlimited
            max_workers_per_account=20,
            max_prompts_per_batch=-1,  # Unlimited
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
            max_accounts=-1,      # Unlimited
            max_foremen=-1,      # Unlimited
            max_workers_per_account=20,
            max_prompts_per_batch=-1,  # Unlimited
            max_outputs_per_prompt=4,
            daily_generation_limit=-1,  # Unlimited
            features=set(Feature),  # All features (incl. DEV_CONSOLE, BETA)
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
    
    def is_trial(self) -> bool:
        """Check if current role is TRIAL."""
        return self._current_role == Role.TRIAL
    
    def is_premium(self) -> bool:
        """Check if current role is PREMIUM."""
        return self._current_role == Role.PREMIUM
    
    def is_tester(self) -> bool:
        """Check if current role is TESTER."""
        return self._current_role == Role.TESTER
    
    def set_role(self, role: Role):
        """Set current role."""
        self._current_role = role
    
    def set_role_from_tier(self, tier: LicenseTier):
        """Set role from license tier.
        
        All paid tiers → PREMIUM. TESTER is set via Firebase _role field only.
        """
        if tier == LicenseTier.TRIAL:
            self._current_role = Role.TRIAL
        else:
            # All paid tiers (1M, 3M, 6M, 1Y, LIFETIME) → PREMIUM
            self._current_role = Role.PREMIUM
    
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
            limit_name: Name of the limit (e.g., 'max_accounts')
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
            "max_accounts": limits.max_accounts,
            "max_foremen": limits.max_foremen,
            "max_workers_per_account": limits.max_workers_per_account,
            "max_prompts_per_batch": limits.max_prompts_per_batch,
            "max_outputs_per_prompt": limits.max_outputs_per_prompt,
            "daily_generation_limit": limits.daily_generation_limit,
        }
    
    def apply_server_limits(self, lim: dict):
        """Override hardcoded limits with server values from _lim field.
        
        Args:
            lim: dict with short keys {ac, fm, wk, op, dg}
        """
        if not lim or not isinstance(lim, dict):
            return
        role_lim = self.limits
        if "ac" in lim:
            role_lim.max_accounts = int(lim["ac"])
        if "fm" in lim:
            role_lim.max_foremen = int(lim["fm"])
        if "wk" in lim:
            role_lim.max_workers_per_account = int(lim["wk"])
        if "op" in lim:
            role_lim.max_outputs_per_prompt = int(lim["op"])
        if "dg" in lim:
            role_lim.daily_generation_limit = int(lim["dg"])
        if "pb" in lim:
            role_lim.max_prompts_per_batch = int(lim["pb"])
        # Store for integrity verification
        self._server_lim = dict(lim)
    
    def verify_limits_integrity(self) -> bool:
        """Level 3: Verify RAM limits match signed cache.
        
        Returns True if OK, False if tampered.
        """
        lim = getattr(self, '_server_lim', None)
        if not lim:
            return True  # No server limits applied
        ram = self.limits
        return (
            ram.max_accounts == int(lim.get("ac", ram.max_accounts))
            and ram.max_foremen == int(lim.get("fm", ram.max_foremen))
            and ram.max_workers_per_account == int(lim.get("wk", ram.max_workers_per_account))
            and ram.max_outputs_per_prompt == int(lim.get("op", ram.max_outputs_per_prompt))
            and ram.daily_generation_limit == int(lim.get("dg", ram.daily_generation_limit))
            and ram.max_prompts_per_batch == int(lim.get("pb", ram.max_prompts_per_batch))
        )
    
    def reset_limits_from_cache(self):
        """Reset RAM limits from cached server values (after tamper detection)."""
        lim = getattr(self, '_server_lim', None)
        if lim:
            self.apply_server_limits(lim)
