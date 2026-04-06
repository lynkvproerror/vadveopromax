"""
VEO Pro Max - Tab 03: Ingredients / References to Video (R2V) - PySide6 Version

Extends GenerationTabBase. Uses Library [tag] for up to 3 reference images.
Includes Voice Library integration for R2V audio narration.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt

from config.theme import Theme
from ui.tabs.generation_tab_base import GenerationTabBase
from ui.components.prompt_table import ImageMode, PromptTable


class TabR2V(GenerationTabBase):
    """Ingredients/References to Video tab.
    
    Uses VideoSidebar with Image Library, BLUE accent, continuation enabled.
    Prompt table uses R2V image mode for up to 3 reference images per prompt.
    Voice Library popup for selecting R2V narration voice.
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
    
    # ── Init ─────────────────────────────────────────────────────
    
    def _init_extra(self):
        """Initialize voice selector state."""
        self._selected_voice_id = ""
        self._voice_popup = None
    
    # ── Sidebar: Voice Library Button ──────────────────────────────
    
    def _create_sidebar(self):
        """Override to inject Voice Library button below Image Library."""
        super()._create_sidebar()
        
        # Insert Voice Library button right after Image Library in sidebar layout
        self._voice_browse_btn = QPushButton("🎙️ Voice Library")
        self._voice_browse_btn.setFixedHeight(34)
        self._voice_browse_btn.setProperty("variant", "secondary")
        self._voice_browse_btn.clicked.connect(self._on_open_voice_library)
        
        # Find the Image Library button and insert after it
        sidebar_layout = self.sidebar._layout
        img_btn = getattr(self.sidebar, 'image_library_btn', None)
        if img_btn:
            idx = sidebar_layout.indexOf(img_btn)
            if idx >= 0:
                sidebar_layout.insertWidget(idx + 1, self._voice_browse_btn)
            else:
                sidebar_layout.addWidget(self._voice_browse_btn)
        else:
            sidebar_layout.addWidget(self._voice_browse_btn)

    
    # ── Prompt Table Override ────────────────────────────────────
    
    def _create_parsed_section(self):
        """Override to pass show_voice=True to PromptTable."""
        from PySide6.QtWidgets import QVBoxLayout
        from ui.components.prompt_table import PromptTable
        from ui.tabs.generation_tab_base import ContinuationHeader
        from config.i18n import t
        
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"QFrame {{ background-color: {self.MODE_HEADER_COLOR}; }}")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        self.parsed_title = QLabel(f"{t('generation.parsed_prompts')} (0)")
        self.parsed_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(self.parsed_title)
        
        # Chain indicator
        if self.SHOW_CONTINUATION:
            self.chain_indicator = QLabel("")
            self.chain_indicator.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
            header_layout.addWidget(self.chain_indicator)
        
        header_layout.addStretch()
        
        # Continuation toggle
        if self.SHOW_CONTINUATION:
            self.continuation = ContinuationHeader()
            self.continuation.select_all.connect(self._on_select_all_cont)
            self.continuation.select_none.connect(self._on_select_none_cont)
            header_layout.addWidget(self.continuation)
        
        layout.addWidget(header)
        
        # Prompt table with show_voice=True
        table_kwargs = {
            'image_mode': self.IMAGE_MODE,
            'show_voice': True,
        }
        if self.PROMPT_TABLE_ACCENT is not None:
            table_kwargs['accent_color'] = self.PROMPT_TABLE_ACCENT
        if not self.SHOW_CONTINUATION:
            table_kwargs['show_continuation'] = False
        
        self.prompt_table = PromptTable(**table_kwargs)
        self.prompt_table.edit_clicked.connect(self._on_edit_prompt)
        self.prompt_table.delete_clicked.connect(self._on_delete_prompt)
        self.prompt_table.slot_image_changed.connect(self._on_slot_changed)
        if self.SHOW_CONTINUATION:
            self.prompt_table.continuation_toggled.connect(self._on_continuation_checkbox_toggled)
        layout.addWidget(self.prompt_table)
        
        return frame
    
    # ── Voice Library Popup ──────────────────────────────────────
    
    def _on_open_voice_library(self):
        """Open Voice Library popup (singleton, non-modal)."""
        if self._voice_popup and self._voice_popup.isVisible():
            self._voice_popup.raise_()
            self._voice_popup.activateWindow()
            return
        
        from ui.popups.voice_library_popup import VoiceLibraryPopup
        self._voice_popup = VoiceLibraryPopup(
            self,
            on_select_all=self._on_voice_select_all,
            on_select_empty=self._on_voice_select_empty,
            current_voice=self._selected_voice_id,
        )
        self._voice_popup.show()
    
    def _on_voice_select_all(self, voice_id: str):
        """Apply voice to ALL prompts."""
        self._selected_voice_id = voice_id
        self.prompt_table.set_voice_for_all(voice_id)
    
    def _on_voice_select_empty(self, voice_id: str):
        """Apply voice only to prompts without a voice."""
        self._selected_voice_id = voice_id
        self.prompt_table.set_voice_for_empty(voice_id)
    
    # ── Extra Settings / Persistence ─────────────────────────────
    
    def _get_extra_prompt_fields(self, prompt) -> dict:
        """Save start_frame, end_frame, and voice_id for R2V prompts."""
        return {
            "start_frame": prompt.start_frame,
            "end_frame": prompt.end_frame,
            "voice_id": prompt.voice_id,
        }
    
    def _restore_extra_prompt_fields(self, pd: dict, restore_imgs: bool) -> dict:
        """Restore start_frame, end_frame, and voice_id for R2V prompts."""
        result = {"voice_id": pd.get("voice_id", "")}
        if restore_imgs:
            result["start_frame"] = pd.get("start_frame")
            result["end_frame"] = pd.get("end_frame")
        return result
    
    def _get_extra_state(self) -> dict:
        return {"selected_voice_id": self._selected_voice_id}
    
    def _restore_extra_state(self, data: dict, opts):
        vid = data.get("selected_voice_id", "")
        if vid:
            self._selected_voice_id = vid
