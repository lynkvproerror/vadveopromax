"""
VEO Pro Max - Tab 05: Image to Image (I2I) - PySide6 Version

Extends GenerationTabBase. Uses ImageSidebar + PURPLE accent + Image Library.
"""

from typing import Optional

from PySide6.QtWidgets import QWidget

from config.theme import Theme
from ui.tabs.generation_tab_base import GenerationTabBase
from ui.components.prompt_table import ImageMode


class TabI2I(GenerationTabBase):
    """Image to Image tab — uses PURPLE accent, Image Library, no continuation.
    
    Uses ImageSidebar with Image Library, I2I image mode.
    Clears prompts after adding to queue.
    """
    
    TAB_LABEL = "I2I"
    MODE_HEADER_TITLE = "✨ TRANSFORM MODE"
    MODE_HEADER_COLOR = Theme.PURPLE
    PROMPT_INPUT_TITLE = "📝 PROMPT INPUT"
    INPUT_PLACEHOLDER = (
        "Enter prompts with [image_tag] references...\n\n"
        "[portrait] Make it more dramatic with moody lighting\n"
        "[landscape] Add rain and storm clouds\n"
        "[sketch] Convert to anime style illustration"
    )
    CONTROLLER_METHOD = "add_i2i_batch"
    SHOW_CONTINUATION = False
    SHOW_IMAGE_LIBRARY = True
    IMAGE_MODE = ImageMode.I2I
    CLEAR_AFTER_ADD = False
    PROMPT_TABLE_ACCENT = Theme.PURPLE
    
    def _create_sidebar_widget(self):
        """Use ImageSidebar with Image Library."""
        from ui.components.sidebar_base import ImageSidebar
        return ImageSidebar(self, show_image_library=True)
