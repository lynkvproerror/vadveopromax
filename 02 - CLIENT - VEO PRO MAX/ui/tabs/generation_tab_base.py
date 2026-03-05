"""
VEO Pro Max - Generation Tab Base Class

Shared logic for all 5 generation tabs (T2V, I2V, R2V, T2I, I2I).
Subclasses only define configuration and tab-specific overrides.

Eliminates ~1,200 lines of duplicated code.
"""

from typing import Optional, List
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from config.i18n import t
from ui.components.prompt_table import PromptTable, PromptRow, PromptStatus, ImageMode
from ui.components.drop_widgets import TextFileDropEdit
from ui.components.continuation_toggle import ContinuationHeader


class GenerationTabBase(QWidget):
    """Base class for all generation tabs (T2V, I2V, R2V, T2I, I2I).
    
    Subclasses configure behavior via class attributes and override hooks.
    
    Class attributes (MUST be set by subclass):
        TAB_LABEL:          str  — Tab display name for toasts  
        MODE_HEADER_TITLE:  str  — Sidebar header text (e.g. "📹 VIDEO MODE")
        MODE_HEADER_COLOR:  str  — Header color (Theme.BLUE or Theme.PURPLE)
        PROMPT_INPUT_TITLE: str  — Input section header text
        INPUT_PLACEHOLDER:  str  — Prompt input placeholder text
        CONTROLLER_METHOD:  str  — Controller method name (e.g. "add_t2v_batch")
        SHOW_CONTINUATION:  bool — Show continuation toggle in parsed section
        SHOW_IMAGE_LIBRARY: bool — Show image library in sidebar
        IMAGE_MODE:         Optional[ImageMode] — Image mode for prompt table
        CLEAR_AFTER_ADD:    bool — Clear prompts after adding to queue
    """
    
    # Signals
    add_to_queue = Signal(list)
    
    # Class-level flag: suppress concurrency warning until app restart
    # Shared across ALL generation tabs (intentional - one dismiss = all)
    _suppress_concurrency_warning = False
    
    # ── Subclass Configuration (override in subclass) ────────────
    
    TAB_LABEL = ""
    MODE_HEADER_TITLE = ""
    MODE_HEADER_COLOR = Theme.BLUE
    PROMPT_INPUT_TITLE = ""  # Overridden by t() at runtime
    INPUT_PLACEHOLDER = ""   # Overridden by t() at runtime
    CONTROLLER_METHOD = ""
    SHOW_CONTINUATION = True
    SHOW_IMAGE_LIBRARY = False
    IMAGE_MODE = None         # None = no image column
    CLEAR_AFTER_ADD = False
    PROMPT_TABLE_ACCENT = None  # None = default accent
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        self._init_extra()
        self._setup_ui()
    
    @property
    def _is_trial(self) -> bool:
        """Live check — re-evaluates on every access so upgrade takes effect immediately."""
        try:
            if self.controller:
                from services.permissions import Role
                return self.controller._permissions.role == Role.TRIAL
        except Exception:
            pass
        return False
    
    def _init_extra(self):
        """Hook for subclass-specific init (e.g. FrameMode enum)."""
        pass
    
    # ── UI Setup ─────────────────────────────────────────────────
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        self._create_sidebar()
        layout.addWidget(self.sidebar_frame)
        
        workspace = self._create_workspace()
        layout.addWidget(workspace, stretch=1)
    
    def retranslate_ui(self):
        """Hot-reload: rebuild UI when language changes (preserves state)."""
        # Save current state
        saved_state = self.save_state()
        
        # Properly remove old layout — Qt won't allow a new layout if old one exists
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            # Transfer old layout to a temp widget → releases self for new layout
            QWidget().setLayout(old_layout)
        
        # Rebuild UI with new language
        self._setup_ui()
        
        # Restore state
        self.restore_state(saved_state)
    
    def _create_sidebar_widget(self):
        """Create the sidebar widget. Override for custom sidebar type.
        
        Returns:
            Sidebar widget instance with add_to_queue signal.
        """
        from ui.components.sidebar_base import VideoSidebar
        return VideoSidebar(self, show_image_library=self.SHOW_IMAGE_LIBRARY)
    
    def _create_sidebar(self):
        """Create sidebar with section header + sidebar widget."""
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setFixedWidth(260)
        self.sidebar_frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QVBoxLayout(self.sidebar_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Section header
        mode_header = QFrame()
        mode_header.setFixedHeight(32)
        mode_header.setStyleSheet(f"background-color: {self.MODE_HEADER_COLOR};")
        mode_layout = QHBoxLayout(mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        
        mode_title = QLabel(self.MODE_HEADER_TITLE)
        mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        
        mode_layout.addStretch()
        
        help_btn = QPushButton("❓")
        help_btn.setFixedSize(24, 24)
        help_btn.clicked.connect(self._on_help)
        mode_layout.addWidget(help_btn)
        
        layout.addWidget(mode_header)
        
        # Sidebar-specific content (hook for subclass)
        self._create_sidebar_extra(layout)
        
        # Standard sidebar
        self.sidebar = self._create_sidebar_widget()
        self.sidebar.add_to_queue.connect(self._on_add_to_queue)
        if self.SHOW_IMAGE_LIBRARY and hasattr(self.sidebar, 'image_library_clicked'):
            self.sidebar.image_library_clicked.connect(self._on_open_library)
        layout.addWidget(self.sidebar)
    
    def _create_sidebar_extra(self, layout):
        """Hook for adding content between header and sidebar widget.
        
        Override in subclass (e.g. I2V adds frame mode dropdown).
        """
        pass
    
    def _create_workspace(self) -> QWidget:
        """Create main workspace area."""
        workspace = QFrame()
        workspace.setStyleSheet(f"background-color: {Theme.BASE};")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        input_section = self._create_input_section()
        layout.addWidget(input_section)
        
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
        header.setStyleSheet(f"background-color: {self.MODE_HEADER_COLOR};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        title = QLabel(t("generation.prompt_input"))
        title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addWidget(header)
        
        # Text input
        self.prompt_input = TextFileDropEdit()
        self.prompt_input.setFixedHeight(150)
        self.prompt_input.setPlaceholderText(self.INPUT_PLACEHOLDER)
        self.prompt_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.prompt_input)
        
        # Action buttons
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(8, 4, 8, 0)
        
        self.import_btn = QPushButton(t("generation.import_file"))
        self.import_btn.setProperty("variant", "secondary")
        self.import_btn.clicked.connect(self._on_import_txt)
        btn_layout.addWidget(self.import_btn)
        
        self.clear_btn = QPushButton(t("generation.clear"))
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
        header.setStyleSheet(f"background-color: {self.MODE_HEADER_COLOR};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        self.parsed_title = QLabel(f"{t('generation.parsed_prompts')} (0)")
        self.parsed_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(self.parsed_title)
        
        # Chain indicator (only for continuation tabs)
        if self.SHOW_CONTINUATION:
            self.chain_indicator = QLabel("")
            self.chain_indicator.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
            header_layout.addWidget(self.chain_indicator)
        
        header_layout.addStretch()
        
        # Continuation toggle (only for video tabs)
        if self.SHOW_CONTINUATION:
            self.continuation = ContinuationHeader()
            self.continuation.select_all.connect(self._on_select_all_cont)
            self.continuation.select_none.connect(self._on_select_none_cont)
            header_layout.addWidget(self.continuation)
        
        layout.addWidget(header)
        
        # Prompt table
        table_kwargs = {}
        if self.IMAGE_MODE is not None:
            table_kwargs['image_mode'] = self.IMAGE_MODE
        if self.PROMPT_TABLE_ACCENT is not None:
            table_kwargs['accent_color'] = self.PROMPT_TABLE_ACCENT
        if not self.SHOW_CONTINUATION:
            table_kwargs['show_continuation'] = False
        
        self.prompt_table = PromptTable(**table_kwargs)
        self.prompt_table.edit_clicked.connect(self._on_edit_prompt)
        self.prompt_table.delete_clicked.connect(self._on_delete_prompt)
        if self.IMAGE_MODE is not None:
            self.prompt_table.slot_image_changed.connect(self._on_slot_changed)
        if self.SHOW_CONTINUATION:
            self.prompt_table.continuation_toggled.connect(self._on_continuation_checkbox_toggled)
        layout.addWidget(self.prompt_table)
        
        return frame
    
    # ── Event Handlers ───────────────────────────────────────────
    
    def _on_help(self):
        """Show help dialog. MUST be overridden by subclass."""
        raise NotImplementedError("Subclass must implement _on_help()")
    
    def _on_text_changed(self):
        """Handle text input change — parse and update table."""
        text = self.prompt_input.toPlainText()
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        self.prompt_count.setText(f"{len(lines)} prompts")
        self._parse_prompts()
    
    def _parse_prompts(self):
        """Parse input text into prompt rows, preserving continuation state."""
        text = self.prompt_input.toPlainText()
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        
        if self.SHOW_CONTINUATION:
            # Preserve continuation state from existing rows
            old_rows = self.prompt_table.get_prompts()
            old_cont = {r.index: r.continuation_from for r in old_rows}
            prompts = []
            for i, line in enumerate(lines):
                idx = i + 1
                row = PromptRow(idx, line, continuation_from=old_cont.get(idx))
                prompts.append(row)
        else:
            prompts = [PromptRow(i + 1, line) for i, line in enumerate(lines)]
        
        self.prompt_table.set_prompts(prompts)
        self._update_parsed_count(len(prompts))
        if self.SHOW_CONTINUATION:
            self._update_chain_indicator(prompts)
    
    def _sync_to_input(self, prompts):
        """Sync prompt table changes back to text input (after edit/delete)."""
        self.prompt_input.blockSignals(True)
        text = '\n'.join(p.text for p in prompts)
        self.prompt_input.setPlainText(text)
        self.prompt_input.blockSignals(False)
        self.prompt_count.setText(f"{len(prompts)} prompts")
    
    def _update_parsed_count(self, count: int):
        """Update parsed prompts count label."""
        self.parsed_title.setText(f"{t('generation.parsed_prompts')} ({count})")
    
    def _update_chain_indicator(self, prompts):
        """Update chain grouping indicator."""
        if not hasattr(self, 'chain_indicator'):
            return
        if not prompts:
            self.chain_indicator.setText("")
            return
        
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
        """Clear prompt input and remove auto-added images from library."""
        # Collect tags from current parsed prompts before clearing
        if self.IMAGE_MODE is not None:
            all_tags = []
            for row in self.prompt_table.get_prompts():
                row.extract_tags()
                all_tags.extend(row.image_tags)
            if all_tags:
                try:
                    from services.image_library import get_image_library
                    lib = get_image_library()
                    lib.remove_by_tags(all_tags, delete_files=False)
                except Exception:
                    pass
        
        self.prompt_input.clear()
        self.prompt_table.set_prompts([])
        self._update_parsed_count(0)
    
    def _on_select_all_cont(self):
        """Select all prompts for continuation."""
        # Trial guard: block continuation
        if self._is_trial:
            from ui.popups import show_warning
            show_warning(
                self, "🔒 Trial Limit",
                "Continuation chỉ dành cho gói Premium.\n\n"
                "Nâng cấp để sử dụng tính năng nối cảnh mượt."
            )
            return
        prompts = self.prompt_table.get_prompts()
        for i, _ in enumerate(prompts):
            if i > 0:
                prompts[i].continuation_from = prompts[i - 1].index
        self.prompt_table.set_prompts(prompts)
    
    def _on_continuation_checkbox_toggled(self, idx: int, checked: bool):
        """Handle individual continuation checkbox toggle."""
        # Trial guard: block continuation
        if self._is_trial and checked:
            # Revert the checkbox
            prompts = self.prompt_table.get_prompts()
            for p in prompts:
                if p.index == idx:
                    p.continuation_from = None
                    break
            self.prompt_table.set_prompts(prompts)
            from ui.popups import show_warning
            show_warning(
                self, "🔒 Trial Limit",
                "Continuation chỉ dành cho gói Premium.\n\n"
                "Nâng cấp để sử dụng tính năng nối cảnh mượt."
            )
            return
        self._update_chain_indicator(self.prompt_table.get_prompts())
    
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
            self._update_parsed_count(len(prompts))
            self._sync_to_input(prompts)
    
    def _on_slot_changed(self, row_idx: int):
        """Sync prompt text back to input when a slot image changes."""
        prompts = self.prompt_table.get_prompts()
        self._sync_to_input(prompts)
    
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
    
    # ── Add to Queue (shared concurrency warning + submit) ───────
    
    def _customize_settings(self, settings: dict) -> dict:
        """Hook for subclass to add extra settings before submit.
        
        Override in subclass (e.g. I2V adds frame_mode).
        """
        return settings
    
    def _validate_inputs(self, prompts, settings) -> list:
        """Validate prompts and settings before submitting to queue.
        
        Returns list of error messages (empty = valid).
        Subclasses can override to add tab-specific checks.
        """
        errors = []
        
        # 1. Output folder
        output_folder = settings.get("output_folder", "").strip()
        if not output_folder:
            errors.append("No output folder set — please set one in the sidebar.")
        elif not Path(output_folder).exists():
            errors.append(f"Output folder does not exist: {output_folder}")
        
        # 2. Empty/whitespace prompts
        empty_indices = [
            str(p.index) for p in prompts
            if not p.text.strip()
        ]
        if empty_indices:
            errors.append(f"Empty prompts at row(s): {', '.join(empty_indices)}")
        
        # 3. Image paths for image-mode tabs (I2V, R2V, I2I)
        if self.IMAGE_MODE is not None:
            for p in prompts:
                if p.image_path and not Path(p.image_path).exists():
                    errors.append(f"Row {p.index}: image file not found — {p.image_path}")
        
        return errors
    
    def _on_add_to_queue(self):
        """Collect prompts and settings, submit to controller."""
        prompts = self.prompt_table.get_prompts()
        if not prompts:
            return
        
        # Enforce max prompts per batch from server limits
        max_pb = -1
        try:
            if self.controller and hasattr(self.controller, '_permissions'):
                max_pb = self.controller._permissions.limits.max_prompts_per_batch
        except Exception:
            pass
        if max_pb > 0 and len(prompts) > max_pb:
            from ui.popups import show_warning
            show_warning(
                self, "🔒 Prompt Limit",
                f"Giới hạn tối đa {max_pb} prompts mỗi dự án.\n"
                f"Hiện tại: {len(prompts)} prompts.\n\n"
                "Liên hệ admin để nâng giới hạn."
            )
            return
        
        settings = self.sidebar.get_values()
        settings = self._customize_settings(settings)
        
        # Validate inputs before submitting
        errors = self._validate_inputs(prompts, settings)
        if errors:
            from ui.popups import show_warning
            show_warning(
                self, "Validation Error",
                "Please fix the following issues:\n\n" + "\n".join(f"• {e}" for e in errors)
            )
            return
        
        if self.controller:
            method = getattr(self.controller, self.CONTROLLER_METHOD)
            method(prompts, settings)
            if self.CLEAR_AFTER_ADD:
                self.prompt_table.set_prompts([])
            main_win = self.window()
            if hasattr(main_win, 'show_toast'):
                main_win.show_toast(f"✅ Added {len(prompts)} prompt(s) to queue", "success")
    
    # ── Session Persistence ──────────────────────────────────────
    
    def _get_extra_prompt_fields(self, prompt) -> dict:
        """Return extra fields to save per prompt. Override in subclass."""
        return {}
    
    def _restore_extra_prompt_fields(self, pd: dict, restore_imgs: bool) -> dict:
        """Return extra kwargs for PromptRow from saved data. Override in subclass."""
        return {}
    
    def _get_extra_state(self) -> dict:
        """Return extra state to save. Override in subclass (e.g. frame_mode)."""
        return {}
    
    def _restore_extra_state(self, data: dict, opts):
        """Restore extra state. Override in subclass (e.g. frame_mode dropdown)."""
        pass
    
    def save_state(self) -> dict:
        """Save tab state for session persistence."""
        prompts = self.prompt_table.get_prompts()
        prompt_data = []
        for p in prompts:
            d = {
                "index": p.index,
                "text": p.text,
            }
            if self.SHOW_CONTINUATION:
                d["continuation_from"] = p.continuation_from
            if self.IMAGE_MODE is not None:
                d["image_path"] = p.image_path
            # Add tab-specific fields (frames, etc.)
            d.update(self._get_extra_prompt_fields(p))
            prompt_data.append(d)
        
        state = {
            "prompt_input": self.prompt_input.toPlainText(),
            "prompts": prompt_data,
            "sidebar": self.sidebar.get_values(),
        }
        state.update(self._get_extra_state())
        return state
    
    def restore_state(self, data: dict, restore_options=None):
        """Restore tab state from saved session data."""
        from ui.components.prompt_table import PromptRow
        opts = restore_options
        
        # Restore sidebar (filtered)
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
        
        # Restore extra state (e.g. frame_mode dropdown)
        self._restore_extra_state(data, opts)
        
        # Restore raw prompt input text
        if (not opts or opts.restore_prompt_input) and "prompt_input" in data:
            self.prompt_input.blockSignals(True)
            self.prompt_input.setPlainText(data["prompt_input"])
            self.prompt_input.blockSignals(False)
        
        # Restore parsed prompts
        if (not opts or opts.restore_parsed_prompts) and "prompts" in data and data["prompts"]:
            rows = []
            for pd_item in data["prompts"]:
                restore_imgs = not opts or opts.restore_prompt_images
                kwargs = {
                    "index": pd_item.get("index", 0),
                    "text": pd_item.get("text", ""),
                }
                if self.SHOW_CONTINUATION:
                    kwargs["continuation_from"] = pd_item.get("continuation_from")
                if self.IMAGE_MODE is not None and restore_imgs:
                    kwargs["image_path"] = pd_item.get("image_path")
                # Extra per-prompt fields from subclass
                kwargs.update(self._restore_extra_prompt_fields(pd_item, restore_imgs))
                rows.append(PromptRow(**kwargs))
            self.prompt_table.set_prompts(rows)
            self._update_parsed_count(len(rows))
        else:
            # No saved prompts (e.g. T2I clears after add) — re-parse from input text
            if self.prompt_input.toPlainText().strip():
                self._parse_prompts()
