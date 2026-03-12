"""
VEO Pro Max - Continuation Toggle Component (PySide6)

Reference: TAB_01_TEXT_TO_VIDEO.md
Migrated from CustomTkinter to PySide6.

Simplified: VEO only supports start frame input, so continuation
always extracts from video END. No placement choice needed.
"""

from typing import Optional, Callable
from enum import Enum
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QCheckBox, QPushButton
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class ContinuationMode(Enum):
    """Continuation mode options."""
    OFF = "off"
    ON = "on"


class ContinuationHeader(QWidget):
    """Header component with All/None quick select (PySide6).
    
    UI: 🔗 CONT: [☐ All] [☐ None]
    
    Simplified: No First/Last placement — VEO always uses
    extracted frame as start frame for next video.
    """
    
    # Signals
    select_all = Signal()
    select_none = Signal()
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_select_all: Optional[Callable[[], None]] = None,
        on_select_none: Optional[Callable[[], None]] = None,
        show_placement: bool = False,  # Kept for backward compat, ignored
    ):
        super().__init__(parent)
        
        self._on_select_all = on_select_all
        self._on_select_none = on_select_none
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Create header widgets."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        layout.addStretch()
        
        # Label
        label = QLabel("🔗 CONT:")
        label.setStyleSheet(f"color: {Theme.CRUST}; font-size: 12px; font-weight: bold;")
        layout.addWidget(label)
        
        # All button
        self.all_btn = QPushButton("All")
        self.all_btn.setMinimumSize(60, 28)
        self.all_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1};
                color: {Theme.GREEN};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {Theme.GREEN};
                color: {Theme.CRUST};
            }}
        """)
        self.all_btn.clicked.connect(self._on_all_click)
        layout.addWidget(self.all_btn)
        
        # None button
        self.none_btn = QPushButton("None")
        self.none_btn.setMinimumSize(60, 28)
        self.none_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1};
                color: {Theme.RED};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {Theme.RED};
                color: {Theme.CRUST};
            }}
        """)
        self.none_btn.clicked.connect(self._on_none_click)
        layout.addWidget(self.none_btn)
    
    def _on_all_click(self):
        """Handle All button click."""
        self.select_all.emit()
        if self._on_select_all:
            self._on_select_all()
    
    def _on_none_click(self):
        """Handle None button click."""
        self.select_none.emit()
        if self._on_select_none:
            self._on_select_none()
    
    def reset_checkboxes(self):
        """Reset All/None buttons (no-op for buttons, kept for backward compat)."""
        pass
    
    def set_cont_enabled(self, enabled: bool):
        """Enable or disable all continuation controls."""
        self.all_btn.setEnabled(enabled)
        self.none_btn.setEnabled(enabled)


class ContinuationCheckbox(QCheckBox):
    """Simple checkbox for per-row continuation toggle (PySide6)."""
    
    # Signals
    toggled_signal = Signal(bool)
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_change: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__(parent)
        
        self._on_change = on_change
        
        # No text, just checkbox
        self.setText("")
        self.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.GREEN};
            }}
        """)
        
        self.stateChanged.connect(self._on_toggle)
    
    def _on_toggle(self, state):
        """Handle checkbox toggle."""
        checked = state == Qt.Checked
        self.toggled_signal.emit(checked)
        if self._on_change:
            self._on_change(checked)
    
    def is_checked(self) -> bool:
        """Get checkbox state."""
        return self.isChecked()
    
    def set_checked(self, checked: bool):
        """Set checkbox state."""
        self.setChecked(checked)
    
    def get_mode(self) -> ContinuationMode:
        """Get continuation mode based on checkbox state."""
        return ContinuationMode.ON if self.isChecked() else ContinuationMode.OFF


# Backward compatibility alias
ContinuationToggle = ContinuationHeader
