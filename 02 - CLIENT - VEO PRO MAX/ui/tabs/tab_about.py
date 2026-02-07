"""
VEO Pro Max - Tab 09: About - PySide6 Version

Reference: TAB_09_ABOUT.md
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional
import sys
import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from config.constants import AppConstants


class TabAbout(QWidget):
    """About tab (PySide6).
    
    Layout:
    - ASCII logo display
    - Version info
    - External links
    - Changelog
    """
    
    ASCII_LOGO = """
██╗   ██╗███████╗ ██████╗     ██████╗ ██████╗  ██████╗     ███╗   ███╗ █████╗ ██╗  ██╗
██║   ██║██╔════╝██╔═══██╗    ██╔══██╗██╔══██╗██╔═══██╗    ████╗ ████║██╔══██╗╚██╗██╔╝
██║   ██║█████╗  ██║   ██║    ██████╔╝██████╔╝██║   ██║    ██╔████╔██║███████║ ╚███╔╝ 
╚██╗ ██╔╝██╔══╝  ██║   ██║    ██╔═══╝ ██╔══██╗██║   ██║    ██║╚██╔╝██║██╔══██║ ██╔██╗ 
 ╚████╔╝ ███████╗╚██████╔╝    ██║     ██║  ██║╚██████╔╝    ██║ ╚═╝ ██║██║  ██║██╔╝ ██╗
  ╚═══╝  ╚══════╝ ╚═════╝     ╚═╝     ╚═╝  ╚═╝ ╚═════╝     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
    """
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        
        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background-color: {Theme.BASE};")
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        
        # Logo section
        logo_section = self._create_logo_section()
        content_layout.addWidget(logo_section)
        
        # Version info section
        version_section = self._create_version_section()
        content_layout.addWidget(version_section)
        
        # Links section
        links_section = self._create_links_section()
        content_layout.addWidget(links_section)
        
        # Changelog section
        changelog_section = self._create_changelog_section()
        content_layout.addWidget(changelog_section)
        
        content_layout.addStretch()
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
    
    def _create_section(self, title: str) -> tuple:
        """Create a section frame with header."""
        section = QFrame()
        section.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        layout.addWidget(header)
        
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 0)
        layout.addWidget(content)
        
        return section, content_layout
    
    def _create_logo_section(self) -> QWidget:
        """Create ASCII logo section."""
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        
        logo = QLabel(self.ASCII_LOGO)
        logo.setFont(QFont("JetBrains Mono", 7))
        logo.setStyleSheet(f"color: {Theme.BLUE};")
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)
        
        return frame
    
    def _create_version_section(self) -> QWidget:
        """Create version info section."""
        section, layout = self._create_section("ℹ️ VERSION INFO")
        
        info_items = [
            ("Application", AppConstants.APP_NAME),
            ("Version", AppConstants.APP_VERSION),
            ("Framework", "PySide6 + Playwright"),
            ("Python", "3.10+"),
            ("Platform", "Windows 10/11"),
        ]
        
        for label, value in info_items:
            row = QHBoxLayout()
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet(f"color: {Theme.SUBTEXT0};")
            label_widget.setFixedWidth(100)
            row.addWidget(label_widget)
            
            value_widget = QLabel(value)
            value_widget.setStyleSheet(f"color: {Theme.TEXT};")
            row.addWidget(value_widget)
            row.addStretch()
            
            layout.addLayout(row)
        
        return section
    
    def _create_links_section(self) -> QWidget:
        """Create external links section."""
        section, layout = self._create_section("🔗 LINKS")
        
        links = [
            ("🌐 Website", "https://veoauto.com"),
            ("📖 Documentation", "https://docs.veoauto.com"),
            ("💬 Support", "https://support.veoauto.com"),
            ("📧 Contact", "support@veoauto.com"),
        ]
        
        for icon_label, url in links:
            btn = QPushButton(f"{icon_label}: {url}")
            btn.setStyleSheet(f"color: {Theme.BLUE}; text-align: left; background: transparent;")
            btn.clicked.connect(lambda checked, u=url: webbrowser.open(u) if "http" in u else None)
            layout.addWidget(btn)
        
        return section
    
    def _create_changelog_section(self) -> QWidget:
        """Create changelog section."""
        section, layout = self._create_section("📋 CHANGELOG")
        
        changelog = QTextEdit()
        changelog.setReadOnly(True)
        changelog.setFixedHeight(150)
        changelog.setStyleSheet(f"background-color: {Theme.SURFACE0}; color: {Theme.SUBTEXT0};")
        changelog.setPlainText("""v1.0.0 (2026-02-04)
- Initial release
- 10 tabs: T2V, I2V, R2V, T2I, I2I, Queue, Settings, License, About, DevConsole
- Multi-account support with 4 slots per account
- Frame continuation workflow
- Firebase license validation

v0.9.0 (Beta)
- Beta testing phase
- Core functionality complete
""")
        layout.addWidget(changelog)
        
        return section
