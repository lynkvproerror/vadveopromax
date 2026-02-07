"""
VEO Pro Max - Tab 05: Image to Image (I2I) - PySide6 Version

Reference: TAB_05_IMAGE_TO_IMAGE.md
Migrated from CustomTkinter to PySide6.
Uses PURPLE accent color for differentiation from T2I.

Note: No manual image upload UI per TAB_05_IMAGE_TO_IMAGE.md line 86-87.
Images are auto-sourced from Library [tag] or Continuation.
"""

from typing import Optional, List
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.components.sidebar_base import ImageSidebar
from ui.components.prompt_table import PromptTable, PromptRow


class TabI2I(QWidget):
    """Image to Image tab (PySide6).
    
    Layout per TAB_05_IMAGE_TO_IMAGE.md:
    - Sidebar: Project settings, [📂 Manage Images] button
    - Workspace: Prompt input (with [image_tag] references), Parsed prompts table
    
    NOTE: NO ImageUploadBox - images sourced via [tag] in prompts or Continuation.
    """
    
    # Signals
    add_to_queue = Signal(list)
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Sidebar with PURPLE section header
        self._create_sidebar()
        layout.addWidget(self.sidebar_frame)
        
        # Workspace
        workspace = self._create_workspace()
        layout.addWidget(workspace, stretch=1)
    
    def _create_sidebar(self):
        """Create sidebar with TRANSFORM MODE section header (PURPLE)."""
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setFixedWidth(260)
        self.sidebar_frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QVBoxLayout(self.sidebar_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Section header with PURPLE accent
        mode_header = QFrame()
        mode_header.setFixedHeight(32)
        mode_header.setStyleSheet(f"background-color: {Theme.PURPLE};")
        mode_layout = QHBoxLayout(mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        
        mode_title = QLabel("✨ TRANSFORM MODE")
        mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        
        mode_layout.addStretch()
        
        help_btn = QPushButton("❓")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._on_help)
        mode_layout.addWidget(help_btn)
        
        layout.addWidget(mode_header)
        
        # Standard image sidebar with Image Library
        self.sidebar = ImageSidebar(self, show_image_library=True)
        self.sidebar.add_to_queue.connect(self._on_add_to_queue)
        self.sidebar.image_library_clicked.connect(self._on_open_library)
        layout.addWidget(self.sidebar)
    
    def _create_workspace(self) -> QWidget:
        """Create main workspace area."""
        workspace = QFrame()
        workspace.setStyleSheet(f"background-color: {Theme.BASE};")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Prompt input section (PURPLE header)
        input_section = self._create_input_section()
        layout.addWidget(input_section)
        
        # Parsed prompts section
        parsed_section = self._create_parsed_section()
        layout.addWidget(parsed_section, stretch=1)
        
        return workspace
    
    def _create_input_section(self) -> QWidget:
        """Create prompt input section with PURPLE accent."""
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        
        # Header with PURPLE accent
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.PURPLE};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        title = QLabel("📝 PROMPT INPUT")
        title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")  # Dark text on purple
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Help button
        help_btn = QPushButton("❓")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._on_help)
        header_layout.addWidget(help_btn)
        
        layout.addWidget(header)
        
        # Text input
        self.prompt_input = QTextEdit()
        self.prompt_input.setFixedHeight(150)  # Standardized to match other tabs
        self.prompt_input.setPlaceholderText(
            "Enter prompts with [image_tag] references...\n\n"
            "[portrait] Make it more dramatic with moody lighting\n"
            "[landscape] Add rain and storm clouds\n"
            "[sketch] Convert to anime style illustration"
        )
        # Sample prompts
        sample_prompts = """[portrait] Make it more dramatic with moody lighting
[landscape] Add rain and storm clouds
[sketch] Convert to anime style illustration
[photo] Add cinematic color grading and film grain
[concept] Transform to watercolor painting style"""
        self.prompt_input.setPlainText(sample_prompts)
        self.prompt_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.prompt_input)
        
        # Buttons and count
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(8, 4, 8, 0)
        
        self.import_btn = QPushButton("📥 Import TXT")
        self.import_btn.setProperty("variant", "secondary")
        btn_layout.addWidget(self.import_btn)
        
        # Open Library removed - already in sidebar as Image Library
        
        self.clear_btn = QPushButton("🗑️ Clear")
        self.clear_btn.setProperty("variant", "secondary")
        self.clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(self.clear_btn)
        
        btn_layout.addStretch()
        
        self.prompt_count = QLabel("5 prompts")
        self.prompt_count.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        btn_layout.addWidget(self.prompt_count)
        
        layout.addWidget(btn_frame)
        
        return frame
    
    def _create_parsed_section(self) -> QWidget:
        """Create parsed prompts section with PURPLE header."""
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with PURPLE accent
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.PURPLE};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        self.parsed_title = QLabel("📊 PARSED PROMPTS (5)")
        self.parsed_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(self.parsed_title)
        
        layout.addWidget(header)
        
        # Prompt table (simpler than video tabs - no continuation)
        self.prompt_table = PromptTable()
        layout.addWidget(self.prompt_table)
        
        # Parse initial prompts
        self._parse_prompts()
        
        return frame
    
    # Event handlers
    def _on_help(self):
        """Show help for I2I workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """Image Tag Usage:
• Use [tag_name] in prompts to reference source images
• Example: [portrait] Add dramatic lighting

Tag Format:
• Tags reference images from your Image Library
• Each tag matches an image you've added with that tag

Workflow:
1. Add images to Library with tags (📂 Image Library)
2. Write prompts with [tag] references
3. System auto-matches tags to images

Image Library:
• Click 📂 Image Library in sidebar to manage images
• Add tags when importing images"""
        
        HelpTooltipPopup(self, "Image to Image", help_text).exec()
    
    def _on_open_library(self):
        """Open image library manager."""
        from ui.popups.complex_popups import ImageManagerPopup
        ImageManagerPopup(self, on_select=self._handle_library_select).exec()
    
    def _handle_library_select(self, tag: str):
        """Insert selected image tag into prompt input."""
        cursor = self.prompt_input.textCursor()
        cursor.insertText(f"[{tag}] ")
        self.prompt_input.setTextCursor(cursor)
    
    def _on_text_changed(self):
        """Handle text input change."""
        text = self.prompt_input.toPlainText()
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        self.prompt_count.setText(f"{len(lines)} prompts")
        self._parse_prompts()
    
    def _parse_prompts(self):
        """Parse input text into prompt rows."""
        text = self.prompt_input.toPlainText()
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        
        prompts = [PromptRow(i + 1, line) for i, line in enumerate(lines)]
        self.prompt_table.set_prompts(prompts)
        self.parsed_title.setText(f"📊 PARSED PROMPTS ({len(prompts)})")
    
    def _on_clear(self):
        """Clear prompt input."""
        self.prompt_input.clear()
        self.prompt_table.set_prompts([])
        self.parsed_title.setText("📊 PARSED PROMPTS (0)")
    
    def _on_add_to_queue(self):
        """Collect prompts and settings, submit to controller."""
        prompts = self.prompt_table.get_prompts()
        if not prompts:
            return
        
        settings = self.sidebar.get_values()
        settings['mode'] = 'I2I'
        
        self.add_to_queue.emit(prompts)
        
        if self.controller:
            self.controller.add_i2i_batch(prompts, settings)
            self.prompt_table.set_prompts([])
