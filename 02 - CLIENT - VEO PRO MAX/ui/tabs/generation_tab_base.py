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
from PySide6.QtCore import Qt, Signal, QTimer

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
    
    def get_searchable_widgets(self):
        """Return editable text widgets for global Search/Replace."""
        return [self.prompt_input] if hasattr(self, 'prompt_input') else []

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
        self.sidebar_frame.setFixedWidth(Theme.SIDEBAR_WIDTH)
        self.sidebar_frame.setObjectName("sidebarPanel")
        
        layout = QVBoxLayout(self.sidebar_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Section header
        mode_header = QFrame()
        mode_header.setFixedHeight(32)
        mode_header.setStyleSheet(f"QFrame {{ background-color: {self.MODE_HEADER_COLOR}; }}")
        mode_layout = QHBoxLayout(mode_header)
        mode_layout.setContentsMargins(12, 0, 12, 0)
        
        mode_title = QLabel(self.MODE_HEADER_TITLE)
        mode_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        mode_layout.addWidget(mode_title)
        
        mode_layout.addStretch()
        
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
        workspace.setStyleSheet(f"QFrame {{ background-color: {Theme.BASE}; }}")
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
        frame.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"QFrame {{ background-color: {self.MODE_HEADER_COLOR}; }}")
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
        # ── Debounce: delay parsing 400ms after last keystroke ──
        # Prevents UI freeze on large inputs (200k-300k lines).
        # Zero change to _parse_prompts / BatchParser logic.
        self._parse_timer = QTimer()
        self._parse_timer.setSingleShot(True)
        self._parse_timer.setInterval(400)  # 400ms idle before parsing
        self._parse_timer.timeout.connect(self._on_text_changed)
        self.prompt_input.textChanged.connect(self._parse_timer.start)
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
        
        self._find_btn = QPushButton("🔍 Find")
        self._find_btn.setProperty("variant", "secondary")
        self._find_btn.setToolTip("Find & Replace (Ctrl+H)")
        self._find_btn.clicked.connect(self._on_open_find_replace)
        btn_layout.addWidget(self._find_btn)
        
        btn_layout.addStretch()
        
        self.prompt_count = QLabel(t("generation.prompt_count").replace("{count}", "0"))
        self.prompt_count.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        btn_layout.addWidget(self.prompt_count)
        
        layout.addWidget(btn_frame)
        
        return frame
    
    def _create_parsed_section(self) -> QWidget:
        """Create parsed prompts section."""
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"QFrame {{ background-color: {self.MODE_HEADER_COLOR}; }}")
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
        self.prompt_table.slot_image_changed.connect(self._on_slot_changed)
        if self.SHOW_CONTINUATION:
            self.prompt_table.continuation_toggled.connect(self._on_continuation_checkbox_toggled)
        layout.addWidget(self.prompt_table)
        
        return frame
    
    # ── Event Handlers ───────────────────────────────────────────

    
    def _on_text_changed(self):
        """Handle text input change — parse and update table."""
        self._parse_prompts()
        # Show actual parsed prompt count (not raw line count)
        count = len(self.prompt_table.get_prompts())
        self.prompt_count.setText(f"{count} prompts")
    
    def _parse_prompts(self):
        """Parse input text into prompt rows, preserving continuation state."""
        from core.batch_parser import BatchParser
        
        text = self.prompt_input.toPlainText()
        
        # Use BatchParser for JSON auto-detection
        parser = BatchParser()
        parsed = parser.parse_text(text)
        
        if not parsed:
            self.prompt_table.set_prompts([])
            self._update_parsed_count(0)
            return
        
        if self.SHOW_CONTINUATION:
            # Preserve continuation state from existing rows
            old_rows = self.prompt_table.get_prompts()
            old_cont = {r.index: r.continuation_from for r in old_rows}
        
        prompts = []
        for i, p in enumerate(parsed):
            idx = i + 1
            # For TEXT format: use raw_line (preserves [tag] references)
            # For JSON format: use canonical display text.
            # Standard JSON keeps its scene object; synthesized nested JSON is
            # already flattened into p.text for direct submission.
            is_json = bool(getattr(p, 'scene_number', None) is not None
                          or getattr(p, 'metadata', {}))
            display_text = p.text if is_json else (p.raw_line or p.text)
            row = PromptRow(
                index=idx,
                text=display_text,
                continuation_from=old_cont.get(idx) if self.SHOW_CONTINUATION else None,
                duration=getattr(p, 'duration', None),
                metadata=getattr(p, 'metadata', {}),
            )
            # Wire ParsedPrompt.images → PromptRow.image_tags
            # (BatchParser extracts from [tag], {tag}, @tag, and JSON image/images fields)
            if getattr(p, 'images', None):
                row.image_tags = list(p.images)
            # Wire ParsedPrompt.voice_id → PromptRow.voice_id
            # (BatchParser extracts from {voice:xxx} in text or "voice":"xxx" in JSON)
            voice_id = getattr(p, 'voice_id', '')
            if voice_id:
                row.voice_id = voice_id
            prompts.append(row)
        
        self.prompt_table.set_prompts(prompts)
        self._update_parsed_count(len(prompts))
        if self.SHOW_CONTINUATION:
            self._update_chain_indicator(prompts)
    
    def _sync_to_input(self, prompts):
        """Sync prompt table changes back to text input (after edit/delete).
        
        JSON-aware: if prompts contain JSON text, reconstruct a proper
        JSON array/object instead of naively joining lines (which would
        destroy multi-line JSON formatting).
        """
        self.prompt_input.blockSignals(True)
        
        if prompts and prompts[0].text.strip().startswith('{'):
            # JSON mode: each prompt.text is a JSON object (possibly multi-line)
            import json as _json
            json_objects = []
            for p in prompts:
                try:
                    obj = _json.loads(p.text.strip())
                    json_objects.append(obj)
                except (ValueError, _json.JSONDecodeError):
                    json_objects.append(p.text)
            
            if len(json_objects) == 1 and isinstance(json_objects[0], dict):
                # Single object: output as pretty object
                text = _json.dumps(json_objects[0], ensure_ascii=False, indent=2)
            else:
                # Multiple objects: output as pretty array
                text = _json.dumps(json_objects, ensure_ascii=False, indent=2)
        else:
            # Plain text mode: simple newline join
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
    
    def _on_open_find_replace(self):
        """Open Find & Replace dialog via MainWindow."""
        win = self.window()
        if hasattr(win, '_toggle_search'):
            win._toggle_search(replace=True)
    
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
    
    # ── Image Library Handlers (format-aware) ────────────────────
    
    def _on_open_library(self):
        """Open image library manager (non-modal, singleton)."""
        if hasattr(self, '_library_popup') and self._library_popup and self._library_popup.isVisible():
            self._library_popup.raise_()
            self._library_popup.activateWindow()
            return
        from ui.popups.complex_popups import ImageManagerPopup
        self._library_popup = ImageManagerPopup(
            self,
            on_select=self._handle_library_select,
            on_use_for_all=self._handle_library_use_for_all,
            on_assign_sequential=self._handle_library_assign_sequential,
        )
        self._library_popup.show()
    
    def _detect_json_input(self, text: str) -> bool:
        """Detect if prompt input text is JSON format (any non-empty line starts with {)."""
        for line in text.strip().split('\n'):
            stripped = line.strip()
            if stripped and stripped.startswith('{'):
                return True
        return False
    
    def _apply_image_to_focused_row(self, tag: str):
        """Apply image tag to the focused (selected) row in prompt table.
        
        Used by library Select for JSON mode — updates PromptRow.image_tags
        and image slot directly without modifying raw JSON text.
        Falls back to first row if no selection.
        """
        import json as _json
        prompts = self.prompt_table.get_prompts()
        if not prompts:
            return
        
        selected = self.prompt_table.table.currentRow()
        target_idx = selected if 0 <= selected < len(prompts) else 0
        
        row = prompts[target_idx]
        if tag not in row.image_tags:
            row.image_tags.append(tag)
        
        text = row.text
        try:
            json_obj = _json.loads(text.strip())
            if isinstance(json_obj, dict):
                json_obj.pop('image', None)
                json_obj.pop('images', None)
                if len(row.image_tags) == 1:
                    json_obj['image'] = row.image_tags[0]
                elif len(row.image_tags) > 1:
                    json_obj['images'] = row.image_tags
                row.text = _json.dumps(json_obj, ensure_ascii=False, indent=2)
        except (ValueError, _json.JSONDecodeError):
            pass
        
        self.prompt_table._add_image_cells(target_idx, row)
        prompt_col = self.prompt_table._col_index("Prompt")
        item = self.prompt_table.table.item(target_idx, prompt_col)
        if item:
            item.setText(row.text)
            item.setToolTip(row.text)
        self._sync_to_input(prompts)
    
    def _apply_image_to_all_rows(self, tag: str):
        """Apply image tag to ALL rows in prompt table (JSON mode)."""
        import json as _json
        prompts = self.prompt_table.get_prompts()
        if not prompts:
            return
        
        for i, row in enumerate(prompts):
            if tag in row.image_tags:
                continue
            row.image_tags.append(tag)
            
            text = row.text
            try:
                json_obj = _json.loads(text.strip())
                if isinstance(json_obj, dict):
                    json_obj.pop('image', None)
                    json_obj.pop('images', None)
                    if len(row.image_tags) == 1:
                        json_obj['image'] = row.image_tags[0]
                    elif len(row.image_tags) > 1:
                        json_obj['images'] = row.image_tags
                    row.text = _json.dumps(json_obj, ensure_ascii=False, indent=2)
            except (ValueError, _json.JSONDecodeError):
                pass
            
            self.prompt_table._add_image_cells(i, row)
            prompt_col = self.prompt_table._col_index("Prompt")
            item = self.prompt_table.table.item(i, prompt_col)
            if item:
                item.setText(row.text)
                item.setToolTip(row.text)
        
        self._sync_to_input(prompts)
    
    def _handle_library_select(self, tag: str):
        """Insert selected image tag — format-aware.
        
        TEXT mode: Insert [tag] at cursor position in raw text input.
        JSON mode: Directly update the focused PromptRow's image field.
        """
        text = self.prompt_input.toPlainText()
        if self._detect_json_input(text):
            self._apply_image_to_focused_row(tag)
        else:
            cursor = self.prompt_input.textCursor()
            cursor.insertText(f"[{tag}] ")
            self.prompt_input.setTextCursor(cursor)
            self._parse_prompts()

    def _handle_library_use_for_all(self, tag: str):
        """Apply [tag] to every parsed prompt — format-aware."""
        text = self.prompt_input.toPlainText()
        if not text.strip():
            return
        
        if self._detect_json_input(text):
            self._apply_image_to_all_rows(tag)
        else:
            tag_ref = f"[{tag}]"
            lines = text.split("\n")
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    new_lines.append(line)
                elif tag_ref in line:
                    new_lines.append(line)
                else:
                    new_lines.append(f"{tag_ref} {line}")
            self.prompt_input.setPlainText("\n".join(new_lines))
            self._parse_prompts()
        main_win = self.window()
        if hasattr(main_win, 'show_toast'):
            main_win.show_toast(f"📋 [{tag}] applied to all prompts", "success")

    def _handle_library_assign_sequential(self, tags: list):
        """Assign images from a category sequentially: image[i] -> prompt[i].
        
        - If prompts >= images: each prompt gets one image, extras cycle.
        - If images > prompts: prompts are duplicated (round-robin) to match
          the number of images. E.g. 1 prompt + 5 images → 5 prompts.
        
        Replaces any existing [tag] at line start.
        """
        if not tags:
            return
        text = self.prompt_input.toPlainText()
        if not text.strip():
            return
        
        import re
        # Separate non-empty lines (prompts) from blank lines
        raw_lines = text.split("\n")
        content_lines = []
        for line in raw_lines:
            cleaned = re.sub(r'^\s*\[[^\]]+\]\s*', '', line)
            if cleaned.strip():
                content_lines.append(cleaned)
        
        if not content_lines:
            return
        
        n_images = len(tags)
        n_prompts = len(content_lines)
        
        # Auto-duplicate: if images > prompts, expand prompts round-robin
        if n_images > n_prompts:
            expanded = []
            for i in range(n_images):
                expanded.append(content_lines[i % n_prompts])
            content_lines = expanded
        
        # Assign [tag] to each line
        new_lines = []
        for i, line in enumerate(content_lines):
            tag_ref = f"[{tags[i % n_images]}]"
            new_lines.append(f"{tag_ref} {line}")
        
        self.prompt_input.setPlainText("\n".join(new_lines))
        self._parse_prompts()
        
        final_count = len(new_lines)
        duplicated = final_count - n_prompts if final_count > n_prompts else 0
        
        main_win = self.window()
        if hasattr(main_win, 'show_toast'):
            msg = f"⇅ {n_images} image(s) → {final_count} prompt(s)"
            if duplicated > 0:
                msg += f" (+{duplicated} duplicated)"
            main_win.show_toast(msg, "success")
    
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
        
        # ★ Credit cost warning gate
        # Scenarios:  Fast+4K → 60/video | Fast+non4K → 10/video | LP+4K → 50/video
        model_name = settings.get("model", "")
        _quality = str(settings.get("download_quality", "720p")).lower()
        _is_fast_paid = (
            "Fast" in model_name
            and "[LP]" not in model_name
            and "Quality" not in model_name
        )
        _has_upscale = "4k" in _quality
        _needs_warning = _is_fast_paid or _has_upscale

        if _needs_warning:
            n_prompts = len(prompts)
            n_outputs = settings.get("outputs_per_prompt", 4)
            from config.i18n import t
            from ui.popups.popups import show_credit_warning

            if _is_fast_paid and _has_upscale:
                cost_per_video = 60
            elif _is_fast_paid:
                cost_per_video = 10
            else:  # LP + 4K
                cost_per_video = 50

            total_credits = n_prompts * n_outputs * cost_per_video
            confirmed = show_credit_warning(
                self, model_name, n_prompts, n_outputs, total_credits,
                cost_per_video=cost_per_video, has_upscale=_has_upscale,
                confirm_text=t("generation.credit_warning.confirm"),
                cancel_text=t("generation.credit_warning.cancel"),
            )
            if not confirmed:
                _switched_parts = []
                # Downgrade model: Fast → LP
                if _is_fast_paid:
                    lp_name = model_name.replace(" - Fast", " - Fast [LP]")
                    idx = self.sidebar.model.findText(lp_name)
                    if idx >= 0:
                        self.sidebar.model.setCurrentIndex(idx)
                    settings["model"] = lp_name
                    _switched_parts.append(f"Model → {lp_name}")
                # Downgrade quality: 4K → 1080p
                if _has_upscale:
                    self.sidebar.download_quality.setCurrentText("1080p")
                    settings["download_quality"] = "1080p"
                    _switched_parts.append("Quality → 1080p")
                main_win = self.window()
                if hasattr(main_win, 'show_toast') and _switched_parts:
                    main_win.show_toast(f"⬇️ {' | '.join(_switched_parts)}", "info")
        
        if self.controller:
            method = getattr(self.controller, self.CONTROLLER_METHOD)
            method(prompts, settings)
            if self.CLEAR_AFTER_ADD:
                self.prompt_table.set_prompts([])
            main_win = self.window()
            if hasattr(main_win, 'show_toast'):
                main_win.show_toast(f"✅ Added {len(prompts)} prompt(s) to queue", "success")
            # Trigger auto-start if setting enabled
            if hasattr(main_win, 'tab_instances'):
                queue_tab = main_win.tab_instances.get('queue')
                if queue_tab and hasattr(queue_tab, '_auto_start_if_idle'):
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(500, queue_tab._auto_start_if_idle)
    
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
