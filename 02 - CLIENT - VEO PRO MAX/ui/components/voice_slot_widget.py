"""
VEO Pro Max - Voice Slot Widget

Compact voice display widget for prompt table Voice column.
Shows voice name + gender icon + clear button, or "—" if empty.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from config.theme import Theme


class VoiceSlotWidget(QWidget):
    """Compact voice indicator for prompt table cell (~90×30px).
    
    States:
        Empty:    │         —          │
        Assigned: │ ♀ Aoede        [×] │
    
    Signals:
        voice_cleared: Emitted when user clicks [×] to remove voice
    """
    
    voice_cleared = Signal()  # user clicked [×]
    
    def __init__(
        self,
        accent_color: str = "",
        slot_width: int = 85,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._accent = accent_color or Theme.BLUE
        self._voice_id = ""
        self._slot_width = slot_width
        
        self.setFixedHeight(28)
        self.setMinimumWidth(slot_width)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        self._setup_ui()
        self._apply_empty_style()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 2, 2)
        layout.setSpacing(2)
        
        # Voice label
        self._label = QLabel("—")
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 10px; border: none; background: transparent;"
        )
        layout.addWidget(self._label, stretch=1)
        
        # Clear button (hidden when empty)
        self._clear_btn = QPushButton("×")
        self._clear_btn.setFixedSize(18, 18)
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setToolTip("Remove voice from this prompt")
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.SURFACE2};
                color: {Theme.SUBTEXT0};
                border: none;
                border-radius: 9px;
                font-size: 11px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background: {Theme.RED};
                color: {Theme.CRUST};
            }}
        """)
        self._clear_btn.clicked.connect(self._on_clear)
        self._clear_btn.hide()
        layout.addWidget(self._clear_btn)
    
    def set_voice(self, voice_id: str):
        """Set or update the displayed voice.
        
        Args:
            voice_id: Voice ID (e.g. "aoede"), or "" to clear.
        """
        self._voice_id = voice_id
        
        if not voice_id:
            self._label.setText("—")
            self._clear_btn.hide()
            self._apply_empty_style()
            return
        
        # Lookup voice info
        try:
            from services.voice_library import get_voice_library
            voice = get_voice_library().get_voice(voice_id)
        except Exception:
            voice = None
        
        if voice:
            self._label.setText(f"{voice.gender_icon} {voice.display_name}")
            self._label.setStyleSheet(
                f"color: {voice.gender_color}; font-size: 10px; font-weight: bold; "
                f"border: none; background: transparent;"
            )
            self._label.setToolTip(
                f"Voice: {voice.display_name}\n"
                f"Gender: {voice.gender.title()}\n"
                f"Tone: {voice.tone or '—'}\n"
                f"Pitch: {voice.pitch or '—'}"
            )
        else:
            self._label.setText(f"🎤 {voice_id}")
            self._label.setStyleSheet(
                f"color: {Theme.TEXT}; font-size: 10px; font-weight: bold; "
                f"border: none; background: transparent;"
            )
        
        self._clear_btn.show()
        self._apply_assigned_style()
    
    def clear_voice(self):
        """Programmatically clear the voice."""
        self.set_voice("")
    
    @property
    def voice_id(self) -> str:
        return self._voice_id
    
    def _on_clear(self):
        """Handle [×] click."""
        self.set_voice("")
        self.voice_cleared.emit()
    
    def _apply_empty_style(self):
        """Grey dashed border — no voice assigned."""
        self.setStyleSheet(f"""
            VoiceSlotWidget {{
                background: {Theme.SURFACE0};
                border: 1px dashed {Theme.OVERLAY0};
                border-radius: 4px;
            }}
        """)
    
    def _apply_assigned_style(self):
        """Green accent border — voice assigned."""
        self.setStyleSheet(f"""
            VoiceSlotWidget {{
                background: {Theme.SURFACE1};
                border: 1px solid {Theme.GREEN};
                border-radius: 4px;
            }}
        """)
