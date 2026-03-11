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
    
    def _on_help(self):
        """Show help for T2V workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """T2V (Text to Video) Workflow:

1. Enter prompts in the input area (one per line)
2. Use Continuation toggle to chain video sequences
3. Click Add to Queue when ready

Prompt Formats:
- Plain text: one prompt per line
- JSON scene: {"prompt_en": "...", "duration": "8s"}
  → Auto-detects duration and metadata

Settings:
- Aspect Ratio: Choose between Landscape, Portrait, or Square
- Outputs/Prompt: Number of videos per prompt
- AI Model: Veo 3.1 Fast or Quality mode
- Download Quality: 1080p or 720p

Tips:
- Use descriptive prompts for best results
- Chain prompts with Continuation for longer sequences"""
        
        HelpTooltipPopup(self, "T2V Workflow", help_text).exec()
