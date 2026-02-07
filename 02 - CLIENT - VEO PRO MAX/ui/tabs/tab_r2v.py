"""
VEO Pro Max - Tab 03: Ingredients / References to Video (R2V) - PySide6 Version

Reference: TAB_03_INGREDIENTS.md
Migrated from CustomTkinter to PySide6.
Uses Library [tag] for up to 3 reference images.
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
from ui.components.sidebar_base import VideoSidebar
from ui.components.prompt_table import PromptTable, PromptRow
from ui.components.continuation_toggle import ContinuationHeader


class TabR2V(QWidget):
    """Ingredients/References to Video tab (PySide6).
    
    Layout per TAB_03_INGREDIENTS.md:
    - Sidebar: Same as TAB_01 + [📂 Manage Images] button
    - Workspace: Prompt input with [tag] for up to 3 reference images
    
    Image source: Library [tag] only (max 3 per prompt)
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
        
        # Sidebar with custom section header (following I2V pattern)
        self._create_sidebar()
        layout.addWidget(self.sidebar_frame)
        
        # Workspace
        workspace = self._create_workspace()
        layout.addWidget(workspace, stretch=1)
    
    def _create_sidebar(self):
        """Create sidebar with INGREDIENTS MODE section header."""
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setFixedWidth(260)
        self.sidebar_frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QVBoxLayout(self.sidebar_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Section header
        mode_header = QFrame()
        mode_header.setFixedHeight(32)
        mode_header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        mode_layout = QHBoxLayout(mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        
        mode_title = QLabel("🍳 INGREDIENTS MODE")
        mode_title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        
        mode_layout.addStretch()
        
        help_btn = QPushButton("❓")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._on_help)
        mode_layout.addWidget(help_btn)
        
        layout.addWidget(mode_header)
        
        # Standard video sidebar with Image Library
        self.sidebar = VideoSidebar(self, show_image_library=True)
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
        
        # Help banner removed - info now in sidebar ❓ button
        
        # Prompt input section
        input_section = self._create_input_section()
        layout.addWidget(input_section)
        
        # Parsed prompts section
        parsed_section = self._create_parsed_section()
        layout.addWidget(parsed_section, stretch=1)
        
        return workspace
    
    def _create_help_banner(self) -> QWidget:
        """Create help banner explaining [tag] usage."""
        banner = QFrame()
        banner.setStyleSheet(f"background-color: {Theme.SURFACE2}; border-radius: 4px;")
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 8, 12, 8)
        
        icon = QLabel("💡")
        icon.setStyleSheet("font-size: 18px;")
        layout.addWidget(icon)
        
        text = QLabel(
            "Use up to 3 [tag] references per prompt to include ingredient images. "
            "Example: [hero] [villain] [background] a scene with both characters"
        )
        text.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px;")
        text.setWordWrap(True)
        layout.addWidget(text, stretch=1)
        
        help_btn = QPushButton("❓ Help")
        help_btn.setFixedWidth(60)
        help_btn.clicked.connect(self._on_help)
        layout.addWidget(help_btn)
        
        # Note: Image Library button is in sidebar, not here (avoid duplicate)
        
        return banner
    
    def _create_input_section(self) -> QWidget:
        """Create prompt input section."""
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        title = QLabel("📝 PROMPT INPUT (max 3 [tags] per prompt)")
        title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        header_layout.addWidget(title)
        layout.addWidget(header)
        
        # Text input
        self.prompt_input = QTextEdit()
        self.prompt_input.setFixedHeight(150)
        self.prompt_input.setPlaceholderText(
            "Enter prompts with [tag] references to Library images...\n\n"
            "[hero] [bg_castle] epic battle scene\n"
            "[hero] [villain] confrontation in the rain\n"
            "[hero] [sidekick] [artifact] discovering the treasure"
        )
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
        
        self.prompt_count = QLabel("0 prompts")
        self.prompt_count.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        btn_layout.addWidget(self.prompt_count)
        
        layout.addWidget(btn_frame)
        
        return frame
    
    def _create_parsed_section(self) -> QWidget:
        """Create parsed prompts section with Ingredients column."""
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        self.parsed_title = QLabel("📊 PARSED PROMPTS (0)")
        self.parsed_title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        header_layout.addWidget(self.parsed_title)
        
        header_layout.addStretch()
        
        self.continuation = ContinuationHeader()
        header_layout.addWidget(self.continuation)
        
        layout.addWidget(header)
        
        # Prompt table (with Ingredients column)
        self.prompt_table = PromptTable()
        layout.addWidget(self.prompt_table)
        
        return frame
    
    # Event handlers
    def _on_help(self):
        """Show help for R2V workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """R2V (Ingredients) Workflow:

1. Use [tag] in your prompts to reference Library images
2. Maximum 3 reference images per prompt
3. Tags are matched from your Image Library

Example prompts:
- [hero] transforms into action
- [hero] [villain] epic confrontation
- [hero] [bg_forest] [artifact] discovering treasure

Note: All images come from the Library.
Use "Manage Library" to add/edit images."""
        
        HelpTooltipPopup(self, "Ingredients Workflow", help_text).exec()
    
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
        settings = self.sidebar.get_values()
        settings['mode'] = 'R2V'
        
        self.add_to_queue.emit(prompts)
        
        if self.controller:
            self.controller.add_r2v_batch(prompts, settings)
