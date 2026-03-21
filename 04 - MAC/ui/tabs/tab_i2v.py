"""
VEO Pro Max - Tab 02: Image to Video (I2V) - PySide6 Version

Extends GenerationTabBase. Adds Frame Mode selector (START/START+END).
"""

from typing import Optional
from enum import Enum

from PySide6.QtWidgets import QWidget, QVBoxLayout, QFrame, QComboBox, QLabel

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
    
    def _create_sidebar(self):
        """Override: create sidebar then inject mode dropdown inside it."""
        super()._create_sidebar()
        self._inject_mode_into_sidebar()
    
    def _create_sidebar_extra(self, layout):
        """No-op: mode dropdown is added inside sidebar after creation."""
        pass
    
    def _inject_mode_into_sidebar(self):
        """Inject frame mode dropdown into sidebar, just above Image Library button."""
        # Create "Mode:" label
        mode_label = QLabel("📂 Mode:")
        mode_label.setStyleSheet(f"""
            color: {Theme.SUBTEXT0};
            font-size: 11px;
            font-weight: bold;
            padding-top: 8px;
            padding-bottom: 2px;
        """)
        
        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems([
            "START only",
            "START + END"
        ])
        self.mode_dropdown.currentTextChanged.connect(self._on_mode_change)
        
        # Insert right before the image library button in the sidebar layout
        sidebar_layout = self.sidebar._layout
        if hasattr(self.sidebar, 'image_library_btn'):
            # Find index of image_library_btn
            idx = sidebar_layout.indexOf(self.sidebar.image_library_btn)
            if idx >= 0:
                sidebar_layout.insertWidget(idx, self.mode_dropdown)
                sidebar_layout.insertWidget(idx, mode_label)
                return
        
        # Fallback: insert before the stretch
        stretch_idx = sidebar_layout.count() - 1  # stretch is last before bottom
        sidebar_layout.insertWidget(stretch_idx, mode_label)
        sidebar_layout.insertWidget(stretch_idx + 1, self.mode_dropdown)
    
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
