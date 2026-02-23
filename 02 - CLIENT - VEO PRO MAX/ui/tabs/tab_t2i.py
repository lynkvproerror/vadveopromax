"""
VEO Pro Max - Tab 04: Text to Image (T2I) - PySide6 Version

Extends GenerationTabBase. Uses ImageSidebar + PURPLE accent.
"""

from typing import Optional

from PySide6.QtWidgets import QWidget

from config.theme import Theme
from ui.tabs.generation_tab_base import GenerationTabBase
from ui.components.prompt_table import ImageMode


class TabT2I(GenerationTabBase):
    """Text to Image tab — uses PURPLE accent, no continuation.
    
    Uses ImageSidebar, no image mode, clears prompts after adding to queue.
    """
    
    TAB_LABEL = "T2I"
    MODE_HEADER_TITLE = "🎯 IMAGE MODE"
    MODE_HEADER_COLOR = Theme.PURPLE
    PROMPT_INPUT_TITLE = "🎯 IMAGE PROMPT INPUT"
    INPUT_PLACEHOLDER = (
        "Enter image prompts, one per line...\n\n"
        "A majestic mountain landscape at sunset\n"
        "Abstract geometric patterns in vibrant colors\n"
        "Portrait of a futuristic robot"
    )
    CONTROLLER_METHOD = "add_t2i_batch"
    SHOW_CONTINUATION = False
    SHOW_IMAGE_LIBRARY = False
    IMAGE_MODE = None
    CLEAR_AFTER_ADD = True
    
    def _create_sidebar_widget(self):
        """Use ImageSidebar instead of VideoSidebar."""
        from ui.components.sidebar_base import ImageSidebar
        return ImageSidebar(self, show_image_library=False)
    
    def _on_help(self):
        """Show help for T2I workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """T2I (Text to Image) Workflow:

1. Enter prompts in the input area (one per line)
2. Each prompt generates multiple image variations
3. Click Add to Queue when ready

Settings:
- Aspect Ratio: Choose between Landscape, Portrait, or Square
- Outputs/Prompt: Number of images per prompt (1-4)

Tips:
- Use detailed, descriptive prompts for best results
- Specify art style, lighting, and mood
- Include subject, setting, and composition details"""
        
        HelpTooltipPopup(self, "T2I Workflow", help_text).exec()
