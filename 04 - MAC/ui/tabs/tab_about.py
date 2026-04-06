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
        scroll.setStyleSheet(f"QScrollArea {{ background-color: {Theme.BASE}; }}")
        
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
        """Create a section frame with header (delegates to shared utility)."""
        from ui.components.section_frame import create_section
        return create_section(title, content_spacing=0)
    
    def _create_logo_section(self) -> QWidget:
        """Create ASCII logo section."""
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        
        logo = QLabel(self.ASCII_LOGO)
        logo.setFont(QFont("Menlo", 9))
        logo.setStyleSheet(f"color: {Theme.BLUE};")
        logo.setAlignment(Qt.AlignCenter)
        logo.setWordWrap(False)
        logo.setMinimumWidth(600)  # Prevent shrinking below logo width
        layout.addWidget(logo, alignment=Qt.AlignCenter)
        
        return frame
    
    def _create_version_section(self) -> QWidget:
        """Create version info section."""
        section, layout = self._create_section("ℹ️ VERSION INFO")
        
        info_items = [
            ("Application", AppConstants.APP_NAME),
            ("Version", AppConstants.APP_VERSION),
            ("Framework", "PySide6 + Playwright"),
            ("Python", "3.10+"),
            ("Platform", "macOS 13+ (Ventura+)"),
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
        
        from config.contact_provider import get_contact_info
        _ci = get_contact_info()

        links = [
            ("🌐 Website", "https://veoauto.com"),
            ("📖 Documentation", "https://docs.veoauto.com"),
            ("💬 Support", "https://support.veoauto.com"),
            (f"📞 Hotline", _ci.get("phone", "N/A")),
            (f"💬 Zalo", _ci.get("zalo", "N/A")),
        ]
        
        for icon_label, url in links:
            btn = QPushButton(f"{icon_label}: {url}")
            btn.setProperty("variant", "link")
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
