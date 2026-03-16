"""
VEO Pro Max - Tab 01: Text to Video (T2V) - PySide6 Version

Extends GenerationTabBase. Only defines T2V-specific configuration.
"""

from typing import Optional

from PySide6.QtWidgets import QWidget

from config.theme import Theme
from ui.tabs.generation_tab_base import GenerationTabBase


class TabT2V(GenerationTabBase):
    """Text to Video tab — simplest generation tab.
    
    Uses VideoSidebar, BLUE accent, continuation enabled, no image mode.
    """
    
    TAB_LABEL = "T2V"
    MODE_HEADER_TITLE = "📹 VIDEO MODE"
    MODE_HEADER_COLOR = Theme.BLUE
    PROMPT_INPUT_TITLE = "📝 PROMPT INPUT"
    INPUT_PLACEHOLDER = (
        "Enter prompts here, one per line...\n\n"
        "A sunset scene over mountains with golden light\n"
        "Camera pans across the valley revealing a river\n\n"
        "Or paste a JSON scene:\n"
        '{"prompt_en": "...", "duration": "8s", "description_vi": "..."}'
    )
    CONTROLLER_METHOD = "add_t2v_batch"
    SHOW_CONTINUATION = True
    SHOW_IMAGE_LIBRARY = False
    IMAGE_MODE = None
    CLEAR_AFTER_ADD = False
