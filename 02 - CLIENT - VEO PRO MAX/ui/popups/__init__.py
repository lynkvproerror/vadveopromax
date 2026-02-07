"""
VEO Pro Max - Popups Package (PySide6)

Reference: 01_POPUP_LAYOUTS.md
All popup dialogs for the application.
Consolidated into popups.py and complex_popups.py
"""

# Base classes and common dialogs
from ui.popups.popups import (
    BasePopup,
    ConfirmDialog,
    ErrorDialog,
    RenameDialog,
)

# Complex dialogs
from ui.popups.complex_popups import (
    EditPromptPopup,
    AddProfileDialog,
    HelpTooltipPopup,
    ImageManagerPopup,
    LicenseExpirationDialog,
)

# Video player
from ui.popups.video_player import VideoPlayerPopup

__all__ = [
    # Base
    'BasePopup',
    'ConfirmDialog',
    'ErrorDialog',
    'RenameDialog',
    # Complex
    'EditPromptPopup',
    'AddProfileDialog',
    'HelpTooltipPopup',
    'ImageManagerPopup',
    'LicenseExpirationDialog',
    # Video
    'VideoPlayerPopup',
]
