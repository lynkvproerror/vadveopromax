"""VEO Pro Max - UI Components Package

Shared components for all tabs.
"""

from .sidebar_base import SidebarBase, VideoSidebar, ImageSidebar
from .image_upload_box import ImageUploadBox, UploadBoxState
from .prompt_table import PromptTable, PromptRow, PromptStatus
from .continuation_toggle import (
    ContinuationHeader,
    ContinuationCheckbox,
    ContinuationMode,
    ContinuationToggle,  # Backward compat alias
)

__all__ = [
    # Sidebar
    "SidebarBase",
    "VideoSidebar",
    "ImageSidebar",
    
    # Upload
    "ImageUploadBox",
    "UploadBoxState",
    
    # Table
    "PromptTable",
    "PromptRow",
    "PromptStatus",
    
    # Continuation
    "ContinuationHeader",
    "ContinuationCheckbox",
    "ContinuationMode",
    "ContinuationToggle",  # Backward compat
]

