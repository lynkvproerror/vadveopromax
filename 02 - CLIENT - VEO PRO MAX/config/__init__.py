"""VEO Pro Max - Configuration Package

Exports:
- Theme: UI theme class
- AppSettings: Application settings
- Constants: Enums and constants
"""

from .theme import Theme
from .settings import AppSettings, get_settings, save_settings
from .constants import (
    WorkflowType,
    APIEndpoints,
    AspectRatio,
    VideoQuality,
    VideoResolution,
    VideoModel,
    GenerationStatus,
    QueueItemStatus,
    AccountStatus,
    LicenseTier,
    ErrorCategory,
    TokenLifetime,
    AppConstants,
)

__all__ = [
    # Theme
    "Theme",
    
    # Settings
    "AppSettings",
    "get_settings",
    "save_settings",
    
    # Constants
    "WorkflowType",
    "APIEndpoints",
    "AspectRatio",
    "VideoQuality",
    "VideoResolution",
    "VideoModel",
    "GenerationStatus",
    "QueueItemStatus",
    "AccountStatus",
    "LicenseTier",
    "ErrorCategory",
    "TokenLifetime",
    "AppConstants",
]
