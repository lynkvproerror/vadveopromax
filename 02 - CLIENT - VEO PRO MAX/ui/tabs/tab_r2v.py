"""
VEO Pro Max - Tab 03: Ingredients / References to Video (R2V) - PySide6 Version

Extends GenerationTabBase. Uses Library [tag] for up to 3 reference images.
"""

from typing import Optional

from PySide6.QtWidgets import QWidget

from config.theme import Theme
from ui.tabs.generation_tab_base import GenerationTabBase
from ui.components.prompt_table import ImageMode


class TabR2V(GenerationTabBase):
    """Ingredients/References to Video tab.
    
    Uses VideoSidebar with Image Library, BLUE accent, continuation enabled.
    Prompt table uses R2V image mode for up to 3 reference images per prompt.
    """
    
    TAB_LABEL = "R2V"
    MODE_HEADER_TITLE = "🍳 INGREDIENTS MODE"
    MODE_HEADER_COLOR = Theme.BLUE
    PROMPT_INPUT_TITLE = "📝 PROMPT INPUT (max 3 [tags] per prompt)"
    INPUT_PLACEHOLDER = (
        "Enter prompts with [tag] references to Library images...\n\n"
        "[hero] [bg_castle] epic battle scene\n"
        "[hero] [villain] confrontation in the rain\n"
        "[hero] [sidekick] [artifact] discovering the treasure"
    )
    CONTROLLER_METHOD = "add_r2v_batch"
    SHOW_CONTINUATION = True
    SHOW_IMAGE_LIBRARY = True
    IMAGE_MODE = ImageMode.R2V
    CLEAR_AFTER_ADD = False
    
    def _get_extra_prompt_fields(self, prompt) -> dict:
        """Save start_frame and end_frame for R2V prompts."""
        return {
            "start_frame": prompt.start_frame,
            "end_frame": prompt.end_frame,
        }
    
    def _restore_extra_prompt_fields(self, pd: dict, restore_imgs: bool) -> dict:
        """Restore start_frame and end_frame for R2V prompts."""
        if restore_imgs:
            return {
                "start_frame": pd.get("start_frame"),
                "end_frame": pd.get("end_frame"),
            }
        return {}
