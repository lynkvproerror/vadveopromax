"""
VEO Pro Max - Tab 02: Image to Video (I2V) - PySide6 Version

Extends GenerationTabBase. Adds Frame Mode selector (START/START+END).
"""

from typing import Optional
from enum import Enum

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QComboBox

from config.theme import Theme
from ui.tabs.generation_tab_base import GenerationTabBase
from ui.components.prompt_table import ImageMode


class FrameMode(Enum):
    """Frame mode options for I2V."""
    START_ONLY = "start"
    START_END = "both"


class TabI2V(GenerationTabBase):
    """Image to Video tab — adds Frame Mode dropdown to sidebar.
    
    Uses VideoSidebar with Image Library, BLUE accent, continuation enabled.
    Prompt table uses I2V image mode for start/end frame images.
    """
    
    TAB_LABEL = "I2V"
    MODE_HEADER_TITLE = "🖼️ FRAME MODE"
    MODE_HEADER_COLOR = Theme.BLUE
    PROMPT_INPUT_TITLE = "📝 PROMPT INPUT (use [tag] for images)"
    INPUT_PLACEHOLDER = (
        "Enter prompts with [tag] to match Library images...\n\n"
        "[hero_pose] transforms into action sequence\n"
        "[sunset_bg] camera slowly pans across\n"
        "[character1] walks through the forest"
    )
    CONTROLLER_METHOD = "add_i2v_batch"
    SHOW_CONTINUATION = True
    SHOW_IMAGE_LIBRARY = True
    IMAGE_MODE = ImageMode.I2V
    CLEAR_AFTER_ADD = False
    
    def _init_extra(self):
        """Initialize frame mode state."""
        self._frame_mode = FrameMode.START_ONLY
    
    def _create_sidebar_extra(self, layout):
        """Add frame mode dropdown between header and sidebar widget."""
        mode_content = QFrame()
        mode_content_layout = QVBoxLayout(mode_content)
        mode_content_layout.setContentsMargins(12, 8, 12, 8)
        
        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems([
            "START only",
            "START + END"
        ])
        self.mode_dropdown.currentTextChanged.connect(self._on_mode_change)
        mode_content_layout.addWidget(self.mode_dropdown)
        
        layout.addWidget(mode_content)
    
    def _on_mode_change(self, value: str):
        """Handle frame mode change — update image slots in parsed prompt table."""
        if "START only" in value:
            self._frame_mode = FrameMode.START_ONLY
            mode_info = "Only START frame will be used"
            self.prompt_table.set_image_labels(['Start'], max_slots=1)
        else:
            self._frame_mode = FrameMode.START_END
            mode_info = "Both START and END frames will be used"
            self.prompt_table.set_image_labels(['Start', 'End'], max_slots=2)
        
        self.parsed_title.setText(f"📊 PARSED PROMPTS ({self.prompt_table.get_count()}) • {mode_info}")
    
    def _customize_settings(self, settings: dict) -> dict:
        """Add frame_mode to settings before submit."""
        settings['frame_mode'] = self._frame_mode.value
        return settings
    
    def _get_extra_prompt_fields(self, prompt) -> dict:
        """Save start_frame and end_frame for I2V prompts."""
        return {
            "start_frame": prompt.start_frame,
            "end_frame": prompt.end_frame,
        }
    
    def _get_extra_state(self) -> dict:
        """Save frame_mode to session state."""
        return {"frame_mode": self._frame_mode.value}
    
    def _restore_extra_state(self, data: dict, opts):
        """Restore frame mode dropdown from saved state."""
        if (not opts or opts.restore_frame_mode) and "frame_mode" in data:
            fm = data["frame_mode"]
            mode_map = {"start": 0, "end": 1, "both": 2}
            idx = mode_map.get(fm, 0)
            self.mode_dropdown.setCurrentIndex(idx)
    
    def _restore_extra_prompt_fields(self, pd: dict, restore_imgs: bool) -> dict:
        """Restore start_frame and end_frame for I2V prompts."""
        if restore_imgs:
            return {
                "start_frame": pd.get("start_frame"),
                "end_frame": pd.get("end_frame"),
            }
        return {}
    
    def _on_help(self):
        """Show help for I2V workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """I2V (Image to Video) Workflow:

1. Use [tag] in your prompts to reference Library images
2. Set Frame Mode: START only, END only, or both
3. Images auto-match from Library when prompt is parsed
4. Enable Continuation to chain videos together

Example prompts:
- [hero_pose] transforms into action
- [sunset_bg] camera pans across scene

Note: No manual image upload. All images come from 
the Library or from Continuation (previous video frame)."""
        
        HelpTooltipPopup(self, "I2V Workflow", help_text).exec()
