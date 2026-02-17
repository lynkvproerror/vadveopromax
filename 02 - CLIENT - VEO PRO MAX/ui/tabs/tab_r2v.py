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
from ui.components.prompt_table import PromptTable, PromptRow, PromptStatus, ImageMode
from ui.components.drop_widgets import TextFileDropEdit
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
    
    # Class-level flag: suppress concurrency warning until app restart
    _suppress_concurrency_warning = False
    
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
        mode_header.setStyleSheet(f"background-color: {Theme.BLUE};")
        mode_layout = QHBoxLayout(mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        
        mode_title = QLabel("🍳 INGREDIENTS MODE")
        mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
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
        
        title = QLabel("📝 PROMPT INPUT (max 3 [tags] per prompt)")
        title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(title)
        layout.addWidget(header)
        
        # Text input
        self.prompt_input = TextFileDropEdit()
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
        
        self.import_btn = QPushButton("📥 Import File")
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
        """Create parsed prompts section with Ingredients column."""
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
        
        # Prompt table (with Ingredients column)
        self.prompt_table = PromptTable(image_mode=ImageMode.R2V)
        self.prompt_table.edit_clicked.connect(self._on_edit_prompt)
        self.prompt_table.delete_clicked.connect(self._on_delete_prompt)
        self.prompt_table.slot_image_changed.connect(self._on_slot_changed)
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
        """Open image library manager (non-modal, singleton)."""
        if hasattr(self, '_library_popup') and self._library_popup and self._library_popup.isVisible():
            self._library_popup.raise_()
            self._library_popup.activateWindow()
            return
        from ui.popups.complex_popups import ImageManagerPopup
        self._library_popup = ImageManagerPopup(self, on_select=self._handle_library_select)
        self._library_popup.show()
    
    def _handle_library_select(self, tag: str):
        """Insert selected image tag into prompt input and refresh table."""
        cursor = self.prompt_input.textCursor()
        cursor.insertText(f"[{tag}] ")
        self.prompt_input.setTextCursor(cursor)
        self._parse_prompts()
    
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
    
    def _on_slot_changed(self, row_idx: int):
        """Sync prompt text back to input when a slot image changes."""
        prompts = self.prompt_table.get_prompts()
        self._sync_to_input(prompts)
    
    def _on_import_txt(self):
        """Import prompts from text file (.txt, .md, .csv, .log)."""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Prompts", "",
            "Text files (*.txt *.md *.csv *.log *.text);;All files (*.*)"
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
        """Handle edit prompt action — sync updated prompts back to input."""
        prompts = self.prompt_table.get_prompts()
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
        
        # Check concurrency warnings
        if not TabR2V._suppress_concurrency_warning and self.controller and hasattr(self.controller, 'get_concurrency_warnings'):
            output_count = self.sidebar.get_values().get("output_count", 2)
            warnings = self.controller.get_concurrency_warnings(output_per_prompt=output_count)
            if warnings:
                from PySide6.QtWidgets import QMessageBox, QCheckBox
                details = "\n".join(
                    f"  • {email}: {workers} workers × {output_count} outputs = {load} calls (safe: ≤{safe})"
                    for email, workers, load, safe in warnings
                )
                msgbox = QMessageBox(self)
                msgbox.setWindowModality(Qt.WindowModal)
                msgbox.setIcon(QMessageBox.Warning)
                msgbox.setWindowTitle("⚠️ High Concurrency Risk")
                msgbox.setText(
                    f"Some accounts exceed the safe concurrent API limit:\n\n"
                    f"{details}\n\n"
                    f"Higher values may cause 403 errors from Google.\n"
                    f"Go to Settings tab to adjust workers.\n\n"
                    f"Add to queue anyway?"
                )
                dont_remind = QCheckBox("Don't remind again this session")
                msgbox.setCheckBox(dont_remind)
                msgbox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msgbox.setDefaultButton(QMessageBox.StandardButton.No)
                result = msgbox.exec()
                if dont_remind.isChecked():
                    TabR2V._suppress_concurrency_warning = True
                if result != QMessageBox.StandardButton.Yes:
                    return
        
        settings = self.sidebar.get_values()
        
        # Block if no output folder set
        if not settings.get("output_folder", "").strip():
            main_win = self.window()
            if hasattr(main_win, 'show_toast'):
                main_win.show_toast("❌ No output folder set — please set one in sidebar before adding to queue!", "error")
            return
        
        if self.controller:
            self.controller.add_r2v_batch(prompts, settings)
            main_win = self.window()
            if hasattr(main_win, 'show_toast'):
                main_win.show_toast(f"✅ Added {len(prompts)} prompt(s) to queue", "success")
    
    # ── Session Persistence ─────────────────────────────────────
    
    def save_state(self) -> dict:
        """Save tab state for session persistence."""
        prompts = self.prompt_table.get_prompts()
        return {
            "prompt_input": self.prompt_input.toPlainText(),
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
    
    def restore_state(self, data: dict, restore_options=None):
        """Restore tab state from saved session data."""
        from ui.components.prompt_table import PromptRow
        opts = restore_options
        
        if "sidebar" in data:
            sidebar_data = dict(data["sidebar"])
            if opts:
                if not opts.restore_project_name:
                    sidebar_data.pop("project_name", None)
                if not opts.restore_output_folder:
                    sidebar_data.pop("output_folder", None)
                if not opts.restore_aspect_ratio:
                    sidebar_data.pop("aspect_ratio", None)
                if not opts.restore_outputs_per_prompt:
                    sidebar_data.pop("outputs_per_prompt", None)
                if not opts.restore_ai_model:
                    sidebar_data.pop("model", None)
                if not opts.restore_download_quality:
                    sidebar_data.pop("download_quality", None)
            if sidebar_data:
                self.sidebar.set_values(sidebar_data)
        
        if (not opts or opts.restore_prompt_input) and "prompt_input" in data:
            self.prompt_input.blockSignals(True)
            self.prompt_input.setPlainText(data["prompt_input"])
            self.prompt_input.blockSignals(False)
        
        if (not opts or opts.restore_parsed_prompts) and "prompts" in data and data["prompts"]:
            rows = []
            for pd in data["prompts"]:
                restore_imgs = not opts or opts.restore_prompt_images
                rows.append(PromptRow(
                    index=pd.get("index", 0),
                    text=pd.get("text", ""),
                    continuation_from=pd.get("continuation_from"),
                    image_path=pd.get("image_path") if restore_imgs else None,
                    start_frame=pd.get("start_frame") if restore_imgs else None,
                    end_frame=pd.get("end_frame") if restore_imgs else None,
                ))
            self.prompt_table.set_prompts(rows)

