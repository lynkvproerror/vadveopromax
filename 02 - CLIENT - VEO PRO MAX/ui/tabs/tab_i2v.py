"""
VEO Pro Max - Tab 02: Image to Video (I2V) - PySide6 Version

Reference: TAB_02_IMAGE_TO_VIDEO.md
Migrated from CustomTkinter to PySide6.
Layout only - Images sourced from Library [tag] or Continuation.
"""

from typing import Optional, List
from enum import Enum
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.components.sidebar_base import VideoSidebar
from ui.components.prompt_table import PromptTable, PromptRow
from ui.components.continuation_toggle import ContinuationHeader


class FrameMode(Enum):
    """Frame mode options for I2V."""
    START_ONLY = "start"
    END_ONLY = "end"
    START_END = "both"


class TabI2V(QWidget):
    """Image to Video tab (PySide6).
    
    Layout:
    - Sidebar: Project settings + frame mode selector
    - Workspace: Prompt input, parsed prompts table with [tag] matching
    
    Image source: Library [tag] only (no manual upload)
    """
    
    # Signals
    add_to_queue = Signal(list)
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self._frame_mode = FrameMode.START_ONLY
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Sidebar
        self._create_sidebar()
        layout.addWidget(self.sidebar_frame)
        
        # Workspace
        workspace = self._create_workspace()
        layout.addWidget(workspace, stretch=1)
    
    def _create_sidebar(self):
        """Create sidebar with video + frame mode options."""
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setFixedWidth(260)
        self.sidebar_frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QVBoxLayout(self.sidebar_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Frame Mode section header
        mode_header = QFrame()
        mode_header.setFixedHeight(32)
        mode_header.setStyleSheet(f"background-color: {Theme.BLUE};")
        mode_layout = QHBoxLayout(mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        
        mode_title = QLabel("🖼️ FRAME MODE")
        mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        
        help_btn = QPushButton("❓")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._on_help)
        mode_layout.addWidget(help_btn)
        
        layout.addWidget(mode_header)
        
        # Frame mode dropdown
        mode_content = QFrame()
        mode_content_layout = QVBoxLayout(mode_content)
        mode_content_layout.setContentsMargins(12, 8, 12, 8)
        
        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems([
            "START only",
            "END only", 
            "START + END"
        ])
        self.mode_dropdown.currentTextChanged.connect(self._on_mode_change)
        mode_content_layout.addWidget(self.mode_dropdown)
        
        # Help text removed - now in popup only (click ❓ button)
        
        layout.addWidget(mode_content)
        
        # Standard video sidebar - with Image Library for I2V
        self.sidebar = VideoSidebar(show_image_library=True)
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
        
        # Prompt input section
        input_section = self._create_input_section()
        layout.addWidget(input_section)
        
        # Parsed prompts section (with image indicators)
        parsed_section = self._create_parsed_section()
        layout.addWidget(parsed_section, stretch=1)
        
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
        header.setStyleSheet(f"background-color: {Theme.BLUE};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        title = QLabel("📝 PROMPT INPUT (use [tag] for images)")
        title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(title)
        layout.addWidget(header)
        
        # Text input
        self.prompt_input = QTextEdit()
        self.prompt_input.setFixedHeight(150)
        self.prompt_input.setPlaceholderText(
            "Enter prompts with [tag] to match Library images...\n\n"
            "[hero_pose] transforms into action sequence\n"
            "[sunset_bg] camera slowly pans across\n"
            "[character1] walks through the forest"
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
        """Create parsed prompts section."""
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.BLUE};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        self.parsed_title = QLabel("📊 PARSED PROMPTS (0)")
        self.parsed_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(self.parsed_title)
        
        header_layout.addStretch()
        
        self.continuation = ContinuationHeader()
        self.continuation.select_all.connect(self._on_select_all_cont)
        self.continuation.select_none.connect(self._on_select_none_cont)
        header_layout.addWidget(self.continuation)
        
        layout.addWidget(header)
        
        # Prompt table (with images column)
        self.prompt_table = PromptTable()
        self.prompt_table.edit_clicked.connect(self._on_edit_prompt)
        self.prompt_table.delete_clicked.connect(self._on_delete_prompt)
        layout.addWidget(self.prompt_table)
        
        return frame
    
    # Event handlers
    def _on_mode_change(self, value: str):
        """Handle frame mode change + CONT × Frame Mode matrix (Fix 6).
        
        Logic per §E2:
        VEO uses continuation frame as START frame (always):
        - Continuation frame → Start slot → disable if END_ONLY
        """
        if "START only" in value:
            self._frame_mode = FrameMode.START_ONLY
            mode_info = "Only START frame will be used"
        elif "END only" in value:
            self._frame_mode = FrameMode.END_ONLY
            mode_info = "Only END frame will be used"
        else:
            self._frame_mode = FrameMode.START_END
            mode_info = "Both START and END frames will be used"
        
        # Update parsed section title to show current mode
        self.parsed_title.setText(f"📊 PARSED PROMPTS ({self.prompt_table.get_count()}) • {mode_info}")
        
        # CONT × Frame Mode matrix (simplified — VEO always uses cont frame as Start)
        # Continuation frame → Start slot → conflict with END_ONLY mode
        cont_allowed = (self._frame_mode != FrameMode.END_ONLY)
        
        self.continuation.set_cont_enabled(cont_allowed)
        if not cont_allowed:
            self.continuation.reset_checkboxes()
    
    def _on_help(self):
        """Show help for I2V workflow."""
        from ui.popups.complex_popups import HelpTooltipPopup
        help_text = """I2V (Image to Video) Workflow:

1. Use [tag] in your prompts to reference Library images
2. Set Frame Mode: START only, END only, or both
3. Images auto-match from Library when prompt is parsed
4. Enable Continuation to chain videos together

Example prompts:
- [hero_pose] transforms into action
- [sunset_bg] camera pans across scene

Note: No manual image upload. All images come from 
the Library or from Continuation (previous video frame)."""
        
        HelpTooltipPopup(self, "I2V Workflow", help_text).exec()
    
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
        """Parse input text into prompt rows, preserving continuation state."""
        text = self.prompt_input.toPlainText()
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        
        # Preserve continuation state from existing rows
        old_rows = self.prompt_table.get_prompts()
        old_cont = {r.index: r.continuation_from for r in old_rows}
        
        prompts = []
        for i, line in enumerate(lines):
            idx = i + 1
            row = PromptRow(idx, line, continuation_from=old_cont.get(idx))
            prompts.append(row)
        
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
    
    def _on_select_all_cont(self):
        """Select all prompts for continuation."""
        prompts = self.prompt_table.get_prompts()
        for i, _ in enumerate(prompts):
            if i > 0:
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
        settings['frame_mode'] = self._frame_mode.value
        
        if self.controller:
            self.controller.add_i2v_batch(prompts, settings)
    
    # ── Session Persistence ─────────────────────────────────────
    
    def save_state(self) -> dict:
        """Save tab state for session persistence."""
        prompts = self.prompt_table.get_prompts()
        return {
            "prompts": [
                {
                    "index": p.index,
                    "text": p.text,
                    "continuation_from": p.continuation_from,
                    "image_path": p.image_path,
                    "start_frame": p.start_frame,
                    "end_frame": p.end_frame,
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
                    continuation_from=pd.get("continuation_from"),
                    image_path=pd.get("image_path"),
                    start_frame=pd.get("start_frame"),
                    end_frame=pd.get("end_frame"),
                ))
            self.prompt_table.set_prompts(rows)
