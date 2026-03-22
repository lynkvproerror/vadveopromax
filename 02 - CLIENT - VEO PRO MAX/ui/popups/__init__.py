"""
VEO Pro Max - Popups Package (PySide6)

Reference: 01_POPUP_LAYOUTS.md
All popup dialogs for the application.
Consolidated into popups.py and complex_popups.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


# Base classes and common dialogs
from ui.popups.popups import (
    BasePopup,
    ConfirmDialog,
    ErrorDialog,
    RenameDialog,
)

# Complex dialogs
from ui.popups.complex_popups import (
    EditPromptPopup,
    AddProfileDialog,
    HelpTooltipPopup,
    ImageManagerPopup,
    LicenseExpirationDialog,
)

# Video player
from ui.popups.video_player import VideoPlayerPopup

__all__ = [
    # Base
    'BasePopup',
    'ConfirmDialog',
    'ErrorDialog',
    'RenameDialog',
    # Complex
    'EditPromptPopup',
    'AddProfileDialog',
    'HelpTooltipPopup',
    'ImageManagerPopup',
    'LicenseExpirationDialog',
    # Video
    'VideoPlayerPopup',
    # Helpers
    'show_info',
    'show_warning',
    'show_confirm',
    'show_confirm_with_checkbox',
    'show_error',
]


# ─────────────────────────────────────────────────────────────
# Themed helpers — replace scattered QMessageBox calls
# ─────────────────────────────────────────────────────────────

def _themed_stylesheet() -> str:
    """Catppuccin-styled QMessageBox stylesheet."""
    return (
        f"QMessageBox {{ background-color: {Theme.BASE}; color: {Theme.TEXT}; }}"
        f"QMessageBox QLabel {{ color: {Theme.TEXT}; font-size: 13px; }}"
        f"QPushButton {{ background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
        f"  padding: 6px 16px; border-radius: 4px; font-weight: bold; min-width: 70px; }}"
        f"QPushButton:hover {{ background-color: {Theme.OVERLAY0}; }}"
    )


def show_info(parent, title: str, message: str):
    """Themed information popup."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(QMessageBox.Icon.Information, title, message, parent=parent)
    box.setStyleSheet(_themed_stylesheet())
    box.exec()


def show_warning(parent, title: str, message: str):
    """Themed warning popup."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(QMessageBox.Icon.Warning, title, message, parent=parent)
    box.setStyleSheet(_themed_stylesheet())
    box.exec()


def show_error(parent, title: str, message: str, details: str = None):
    """Themed error popup with optional details."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(QMessageBox.Icon.Critical, title, message, parent=parent)
    if details:
        box.setDetailedText(details)
    box.setStyleSheet(_themed_stylesheet())
    box.exec()


def show_confirm(parent, title: str, message: str, danger: bool = False) -> bool:
    """Themed yes/no confirmation. Returns True if user chose Yes."""
    from PySide6.QtWidgets import QMessageBox
    icon = QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question
    box = QMessageBox(icon, title, message, parent=parent)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    box.setStyleSheet(_themed_stylesheet())
    return box.exec() == QMessageBox.StandardButton.Yes


def show_confirm_with_checkbox(
    parent, title: str, message: str,
    checkbox_text: str = "Don't remind again",
    danger: bool = False,
) -> tuple:
    """Themed yes/no confirmation with a checkbox.
    
    Returns:
        (confirmed: bool, checkbox_checked: bool)
    """
    from PySide6.QtWidgets import QMessageBox, QCheckBox
    icon = QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question
    box = QMessageBox(icon, title, message, parent=parent)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    cb = QCheckBox(checkbox_text)
    box.setCheckBox(cb)
    box.setStyleSheet(_themed_stylesheet())
    confirmed = box.exec() == QMessageBox.StandardButton.Yes
    return confirmed, cb.isChecked()
