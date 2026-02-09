"""
VEO Pro Max - Tab 04: Text to Image (T2I) - PySide6 Version

Reference: TAB_04_TEXT_TO_IMAGE.md
Migrated from CustomTkinter to PySide6.
Uses PURPLE accent color for differentiation.
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


class TabT2I(QWidget):
    """Text to Image tab (PySide6).
    
    Similar to T2V but simpler, uses PURPLE accent.
    Layout:
    - Sidebar: Project settings, outputs per prompt
    - Workspace: Prompt input, parsed prompts
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
        """Create sidebar with IMAGE MODE section header (PURPLE)."""
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
        
        mode_title = QLabel("🎯 IMAGE MODE")
        mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        
        mode_layout.addStretch()
        
        help_btn = QPushButton("❓")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._on_help)
        mode_layout.addWidget(help_btn)
        
        layout.addWidget(mode_header)
        
        # Standard image sidebar
        self.sidebar = ImageSidebar(self, show_image_library=False)
        self.sidebar.add_to_queue.connect(self._on_add_to_queue)
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
        
        title = QLabel("🎯 IMAGE PROMPT INPUT")
        title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")  # Dark text on purple
        header_layout.addWidget(title)
        layout.addWidget(header)
        
        # Text input
        self.prompt_input = QTextEdit()
        self.prompt_input.setFixedHeight(150)
        self.prompt_input.setPlaceholderText(
            "Enter image prompts, one per line...\n\n"
            "A majestic mountain landscape at sunset\n"
            "Abstract geometric patterns in vibrant colors\n"
            "Portrait of a futuristic robot"
        )
        self.prompt_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.prompt_input)
        
        # Buttons and count
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(8, 4, 8, 0)
        
        self.import_btn = QPushButton("📥 Import TXT")
        self.import_btn.setProperty("variant", "secondary")
        self.import_btn.clicked.connect(self._on_import_txt)
        btn_layout.addWidget(self.import_btn)
        
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
        
        self.parsed_title = QLabel("📊 PARSED PROMPTS (0)")
        self.parsed_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(self.parsed_title)
        
        layout.addWidget(header)
        
        # Prompt table (simpler than video tabs - no continuation)
        self.prompt_table = PromptTable()
        self.prompt_table.edit_clicked.connect(self._on_edit_prompt)
        self.prompt_table.delete_clicked.connect(self._on_delete_prompt)
        layout.addWidget(self.prompt_table)
        
        return frame
    
    # Event handlers    
    def _on_help(self):
        """Show help for T2I workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """T2I (Text to Image) Workflow:

1. Enter prompts in the input area (one per line)
2. Each prompt generates multiple image variations
3. Click Add to Queue when ready

Settings:
- Aspect Ratio: Choose between Landscape, Portrait, or Square
- Outputs/Prompt: Number of images per prompt (1-4)

Tips:
- Use detailed, descriptive prompts for best results
- Specify art style, lighting, and mood
- Include subject, setting, and composition details"""
        
        HelpTooltipPopup(self, "T2I Workflow", help_text).exec()
    
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
    
    def _sync_to_input(self, prompts):
        """Sync prompt table changes back to text input (after edit/delete)."""
        self.prompt_input.blockSignals(True)
        text = '\n'.join(p.text for p in prompts)
        self.prompt_input.setPlainText(text)
        self.prompt_input.blockSignals(False)
        self.prompt_count.setText(f"{len(prompts)} prompts")
    
    def _on_import_txt(self):
        """Import prompts from TXT file."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Prompts", "", "Text files (*.txt);;All files (*.*)"
        )
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                self.prompt_input.setPlainText(f.read())
    
    def _on_clear(self):
        """Clear prompt input."""
        self.prompt_input.clear()
        self.prompt_table.set_prompts([])
        self.parsed_title.setText("📊 PARSED PROMPTS (0)")
    
    def _on_edit_prompt(self, row_index: int):
        """Handle edit prompt action."""
        from PySide6.QtWidgets import QInputDialog
        prompts = self.prompt_table.get_prompts()
        if 0 <= row_index < len(prompts):
            current_text = prompts[row_index].text
            new_text, ok = QInputDialog.getMultiLineText(
                self, "Edit Prompt", "Prompt:", current_text
            )
            if ok and new_text:
                prompts[row_index].text = new_text
                self.prompt_table.set_prompts(prompts)
                self._sync_to_input(prompts)
    
    def _on_delete_prompt(self, row_index: int):
        """Handle delete prompt action."""
        prompts = self.prompt_table.get_prompts()
        if 0 <= row_index < len(prompts):
            del prompts[row_index]
            for i, prompt in enumerate(prompts):
                prompt.index = i + 1
            self.prompt_table.set_prompts(prompts)
            self.parsed_title.setText(f"📊 PARSED PROMPTS ({len(prompts)})")
            self._sync_to_input(prompts)
    
    def _on_add_to_queue(self):
        """Collect prompts and settings, submit to controller."""
        prompts = self.prompt_table.get_prompts()
        if not prompts:
            return
        
        settings = self.sidebar.get_values()
        
        if self.controller:
            self.controller.add_t2i_batch(prompts, settings)
            self.prompt_table.set_prompts([])
    
    # ── Session Persistence ─────────────────────────────────────
    
    def save_state(self) -> dict:
        """Save tab state for session persistence."""
        prompts = self.prompt_table.get_prompts()
        return {
            "prompts": [
                {
                    "index": p.index,
                    "text": p.text,
                    "image_path": p.image_path,
                }
                for p in prompts
            ],
            "sidebar": self.sidebar.get_values(),
        }
    
    def restore_state(self, data: dict):
        """Restore tab state from saved session data."""
        from ui.components.prompt_table import PromptRow
        
        if "sidebar" in data:
            self.sidebar.set_values(data["sidebar"])
        
        if "prompts" in data and data["prompts"]:
            rows = []
            for pd in data["prompts"]:
                rows.append(PromptRow(
                    index=pd.get("index", 0),
                    text=pd.get("text", ""),
                    image_path=pd.get("image_path"),
                ))
            self.prompt_table.set_prompts(rows)

