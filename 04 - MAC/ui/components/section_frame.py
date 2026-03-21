"""
VEO Pro Max - Shared Section Frame Utility

Reusable section frame with header for settings and info tabs.
Eliminates duplicate _create_section() methods in tab_settings and tab_about.
"""

from PySide6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
)
from config.theme import Theme


def create_section(title: str, content_spacing: int = 4) -> tuple:
    """Create a section frame with styled header.
    
    Returns:
        (section_frame, content_layout) — add the section_frame to your parent,
        add child widgets to content_layout.
    """
    section = QFrame()
    section.setStyleSheet(f"background-color: {Theme.SURFACE0};")
    layout = QVBoxLayout(section)
    layout.setContentsMargins(0, 0, 0, 8)
    layout.setSpacing(0)
    
    # Header
    header = QFrame()
    header.setFixedHeight(32)
    header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
    header_layout = QHBoxLayout(header)
    header_layout.setContentsMargins(12, 0, 12, 0)
    
    title_label = QLabel(title)
    title_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
    header_layout.addWidget(title_label)
    
    layout.addWidget(header)
    
    # Content area
    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(12, 8, 12, 0)
    content_layout.setSpacing(content_spacing)
    layout.addWidget(content)
    
    return section, content_layout
