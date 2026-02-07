"""
VEO Pro Max - Continuation Toggle Component (PySide6)

Reference: TAB_01_TEXT_TO_VIDEO.md
Migrated from CustomTkinter to PySide6.
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


class ContinuationPlacement(Enum):
    """Where to place continuation frame (for I2V/R2V tabs)."""
    FIRST = "first"
    LAST = "last"


class ContinuationHeader(QWidget):
    """Header component with All/None quick select (PySide6).
    
    UI: 🔗 CONT: [☐ All] [☐ None]
    """
    
    # Signals
    select_all = Signal()
    select_none = Signal()
    placement_changed = Signal(ContinuationPlacement)
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_select_all: Optional[Callable[[], None]] = None,
        on_select_none: Optional[Callable[[], None]] = None,
        show_placement: bool = False,
    ):
        super().__init__(parent)
        
        self._on_select_all = on_select_all
        self._on_select_none = on_select_none
        self.show_placement = show_placement
        self._placement = ContinuationPlacement.FIRST
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Create header widgets."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Label
        label = QLabel("🔗 CONT:")
        label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        layout.addWidget(label)
        
        # All checkbox
        self.all_checkbox = QCheckBox("All")
        self.all_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT};
                font-size: 11px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.GREEN};
            }}
        """)
        self.all_checkbox.stateChanged.connect(self._on_all_click)
        layout.addWidget(self.all_checkbox)
        
        # None checkbox
        self.none_checkbox = QCheckBox("None")
        self.none_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {Theme.TEXT};
                font-size: 11px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.RED};
            }}
        """)
        self.none_checkbox.stateChanged.connect(self._on_none_click)
        layout.addWidget(self.none_checkbox)
        
        # Placement selector (optional, for I2V/R2V)
        if self.show_placement:
            sep = QLabel("|")
            sep.setStyleSheet(f"color: {Theme.BORDER};")
            layout.addWidget(sep)
            
            self.first_btn = QPushButton("First")
            self.first_btn.setFixedSize(40, 24)
            self.first_btn.clicked.connect(lambda: self._set_placement(ContinuationPlacement.FIRST))
            layout.addWidget(self.first_btn)
            
            self.last_btn = QPushButton("Last")
            self.last_btn.setFixedSize(40, 24)
            self.last_btn.setProperty("variant", "secondary")
            self.last_btn.clicked.connect(lambda: self._set_placement(ContinuationPlacement.LAST))
            layout.addWidget(self.last_btn)
            
            self._update_placement_buttons()
        
        layout.addStretch()
    
    def _on_all_click(self, state):
        """Handle All checkbox click."""
        if state == Qt.Checked:
            self.none_checkbox.setChecked(False)
            self.select_all.emit()
            if self._on_select_all:
                self._on_select_all()
    
    def _on_none_click(self, state):
        """Handle None checkbox click."""
        if state == Qt.Checked:
            self.all_checkbox.setChecked(False)
            self.select_none.emit()
            if self._on_select_none:
                self._on_select_none()
    
    def _set_placement(self, placement: ContinuationPlacement):
        """Set placement and update button states."""
        self._placement = placement
        self._update_placement_buttons()
        self.placement_changed.emit(placement)
    
    def _update_placement_buttons(self):
        """Update placement button styles."""
        if not self.show_placement:
            return
        
        if self._placement == ContinuationPlacement.FIRST:
            self.first_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
            self.last_btn.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        else:
            self.first_btn.setStyleSheet(f"background-color: {Theme.SURFACE2};")
            self.last_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
    
    def get_placement(self) -> ContinuationPlacement:
        """Get current placement."""
        return self._placement
    
    def reset_checkboxes(self):
        """Reset All/None checkboxes to unchecked."""
        self.all_checkbox.setChecked(False)
        self.none_checkbox.setChecked(False)


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
