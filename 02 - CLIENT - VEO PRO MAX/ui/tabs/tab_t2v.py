"""
VEO Pro Max - Tab 01: Text to Video (T2V) - PySide6 Version

Reference: TAB_01_TEXT_TO_VIDEO.md
Migrated from CustomTkinter to PySide6.
Layout only - connects to controller via signals.
"""

from typing import Optional, List
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QSplitter
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.components.sidebar_base import VideoSidebar
from ui.components.prompt_table import PromptTable, PromptRow
from ui.components.continuation_toggle import ContinuationHeader


class TabT2V(QWidget):
    """Text to Video tab (PySide6).
    
    Layout:
    - Sidebar: Project settings, output options
    - Workspace: Prompt input, parsed prompts table
    """
    
    # Signals
    add_to_queue = Signal(list)  # List of prompts
    
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
        """Create sidebar with custom section header (following I2V pattern)."""
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
        
        mode_title = QLabel("📹 VIDEO MODE")
        mode_title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        
        mode_layout.addStretch()
        
        help_btn = QPushButton("❓")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._on_help)
        mode_layout.addWidget(help_btn)
        
        layout.addWidget(mode_header)
        
        # Standard video sidebar
        self.sidebar = VideoSidebar(self, show_image_library=False)
        self.sidebar.add_to_queue.connect(self._on_add_to_queue)
        layout.addWidget(self.sidebar)
    
    def _create_workspace(self) -> QWidget:
        """Create main workspace area."""
        workspace = QFrame()
        workspace.setStyleSheet(f"background-color: {Theme.BASE};")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # === PROMPT INPUT SECTION ===
        input_section = self._create_input_section()
        layout.addWidget(input_section)
        
        # === PARSED PROMPTS SECTION ===
        parsed_section = self._create_parsed_section()
        layout.addWidget(parsed_section, stretch=1)
        
        # Queue Preview removed - info now in Queue Manager tab (consistency with I2V)
        
        return workspace
    
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
        
        title = QLabel("📝 PROMPT INPUT")
        title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addWidget(header)
        
        # Text input
        self.prompt_input = QTextEdit()
        self.prompt_input.setFixedHeight(150)  # Standardized to match I2V
        self.prompt_input.setPlaceholderText(
            "Enter prompts here, one per line...\n\n"
            "A sunset scene over mountains with golden light\n"
            "Camera pans across the valley revealing a river\n"
            "Birds flying in formation against the orange sky"
        )
        self.prompt_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.prompt_input)
        
        # Action buttons
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
        """Create parsed prompts section."""
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with continuation toggle
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        self.parsed_title = QLabel("📊 PARSED PROMPTS (0)")
        self.parsed_title.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        header_layout.addWidget(self.parsed_title)
        
        self.chain_indicator = QLabel("")
        self.chain_indicator.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        header_layout.addWidget(self.chain_indicator)
        
        header_layout.addStretch()
        
        self.continuation = ContinuationHeader()
        self.continuation.select_all.connect(self._on_select_all_cont)
        self.continuation.select_none.connect(self._on_select_none_cont)
        header_layout.addWidget(self.continuation)
        
        layout.addWidget(header)
        
        # Prompt table
        self.prompt_table = PromptTable()
        self.prompt_table.edit_clicked.connect(self._on_edit_prompt)
        self.prompt_table.delete_clicked.connect(self._on_delete_prompt)
        layout.addWidget(self.prompt_table)
        
        # Sample prompts for preview
        sample = [
            PromptRow(1, "A sunset scene over mountains with golden light"),
            PromptRow(2, "Camera pans across the valley revealing a river", continuation_from=1),
            PromptRow(3, "Birds flying in formation against the orange sky", continuation_from=2),
        ]
        self.prompt_table.set_prompts(sample)
        self._update_parsed_count(len(sample))
        self._update_chain_indicator(sample)
        
        return frame
    
    def _create_queue_preview(self) -> QWidget:
        """Create fixed 60px queue preview at bottom."""
        frame = QFrame()
        frame.setFixedHeight(60)
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(24)
        header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 8, 0)
        
        title = QLabel("📋 QUEUE PREVIEW")
        title.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        header_layout.addWidget(title)
        layout.addWidget(header)
        
        # Queue info
        info_frame = QFrame()
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(8, 4, 8, 4)
        
        self.queue_status_label = QLabel("0 jobs pending • Output: Not set")
        self.queue_status_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px;")
        info_layout.addWidget(self.queue_status_label)
        
        layout.addWidget(info_frame)
        
        return frame
    
    # Event handlers
    def _on_help(self):
        """Show help for T2V workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """T2V (Text to Video) Workflow:

1. Enter prompts in the input area (one per line)
2. Use Continuation toggle to chain video sequences
3. Click Add to Queue when ready

Settings:
- Aspect Ratio: Choose between Landscape, Portrait, or Square
- Outputs/Prompt: Number of videos per prompt
- AI Model: Veo 3.1 Fast or Quality mode
- Download Quality: 1080p or 720p

Tips:
- Use descriptive prompts for best results
- Chain prompts with Continuation for longer sequences"""
        
        HelpTooltipPopup(self, "T2V Workflow", help_text).exec()
    
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
        self._update_parsed_count(len(prompts))
    
    def _update_parsed_count(self, count: int):
        """Update parsed prompts count label."""
        self.parsed_title.setText(f"📊 PARSED PROMPTS ({count})")
    
    def _update_chain_indicator(self, prompts):
        """Update chain grouping indicator - matches CTK tab_t2v.py lines 252-275."""
        if not prompts:
            self.chain_indicator.setText("")
            return
        
        # Count chains
        chains = []
        current_chain = []
        for p in prompts:
            if p.continuation_from is None:
                if current_chain:
                    chains.append(len(current_chain))
                current_chain = [p]
            else:
                current_chain.append(p)
        if current_chain:
            chains.append(len(current_chain))
        
        if len(chains) == 1:
            self.chain_indicator.setText(f"Chain A: {chains[0]} prompts")
        else:
            chain_text = ", ".join([f"Chain {chr(65+i)}: {c}" for i, c in enumerate(chains)])
            self.chain_indicator.setText(chain_text)
    
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
        self._update_parsed_count(0)
    
    def _on_select_all_cont(self):
        """Select all prompts for continuation."""
        prompts = self.prompt_table.get_prompts()
        for i, _ in enumerate(prompts):
            if i > 0:  # First prompt cannot be continuation
                prompts[i].continuation_from = prompts[i - 1].index
        self.prompt_table.set_prompts(prompts)
    
    def _on_select_none_cont(self):
        """Deselect all prompts from continuation."""
        prompts = self.prompt_table.get_prompts()
        for prompt in prompts:
            prompt.continuation_from = None
        self.prompt_table.set_prompts(prompts)
    
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
    
    def _on_delete_prompt(self, row_index: int):
        """Handle delete prompt action."""
        prompts = self.prompt_table.get_prompts()
        if 0 <= row_index < len(prompts):
            del prompts[row_index]
            # Reindex remaining prompts
            for i, prompt in enumerate(prompts):
                prompt.index = i + 1
            self.prompt_table.set_prompts(prompts)
            self._update_parsed_count(len(prompts))
    
    def _on_add_to_queue(self):
        """Collect prompts and settings, submit to controller."""
        prompts = self.prompt_table.get_prompts()
        settings = self.sidebar.get_values()
        
        self.add_to_queue.emit(prompts)
        
        if self.controller:
            self.controller.add_t2v_batch(prompts, settings)
