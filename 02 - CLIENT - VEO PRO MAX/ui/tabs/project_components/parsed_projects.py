"""
VEO Pro Max — Parsed Projects Panel for Project Builder

Compact layout with inline collapsible viewer per project:
- Click file tab (Bi/Ma/Pr/Du/SE) → expand/collapse inline viewer below that row
- Queue status badges (⏳ Generating, ❌ Not queued, ✅ Queued, ⚠️ Error)
- Compact Add to Queue buttons
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QTextEdit,
    QCheckBox, QComboBox,
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme
from config.i18n import t


# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

FILE_TYPES = ["Bible", "Master", "Prompts", "Dubbing", "SEO"]

STATUS_BADGES = {
    "generating": ("⏳", Theme.YELLOW if hasattr(Theme, 'YELLOW') else "#f9e2af"),
    "ready":      ("❌", Theme.SUBTEXT0),
    "queued":     ("✅", Theme.GREEN),
    "error":      ("⚠️", Theme.RED if hasattr(Theme, 'RED') else "#f38ba8"),
}


# ═══════════════════════════════════════════════════════════════════
# FileTabButton: Clickable file tab
# ═══════════════════════════════════════════════════════════════════

class FileTabButton(QPushButton):
    """Small clickable tab for a file type."""

    clicked_file = Signal(int, str)  # (project_index, file_type)

    def __init__(self, project_idx: int, file_type: str, parent=None):
        super().__init__(file_type, parent)  # Full text: "Bible", "Master", etc.
        self.project_idx = project_idx
        self.file_type = file_type
        self._active = False

        # Use objectName for QSS specificity (override global QPushButton)
        self.setObjectName("fileTab")
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(file_type)
        self._apply_style()
        self.clicked.connect(lambda: self.clicked_file.emit(self.project_idx, self.file_type))

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton#fileTab {{
                    background-color: {Theme.BLUE};
                    color: {Theme.CRUST};
                    border: none; border-radius: 3px;
                    padding: 0px 4px; margin: 0px;
                    font-size: 10px; font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton#fileTab {{
                    background-color: {Theme.SURFACE2};
                    color: {Theme.TEXT};
                    border: 1px solid {Theme.BORDER}; border-radius: 3px;
                    padding: 0px 4px; margin: 0px;
                    font-size: 10px;
                }}
                QPushButton#fileTab:hover {{
                    background-color: {Theme.BLUE};
                    color: {Theme.CRUST};
                }}
            """)

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()


# ═══════════════════════════════════════════════════════════════════
# ProjectRow: One project row with file tabs + inline viewer
# ═══════════════════════════════════════════════════════════════════

class ProjectRow(QFrame):
    """A single project row with inline collapsible viewer.

    Layout:
      ┌──────────────────────────────────────────────┐
      │ 01. Topic name  │Bi│Ma│Pr│Du│SE│ [✅]        │
      ├──────────────────────────────────────────────┤
      │ (inline viewer — shown when file tab active) │
      └──────────────────────────────────────────────┘
    """

    file_selected = Signal(int, str)  # (project_index, file_type)
    add_to_queue = Signal(int)        # project_index
    retry_requested = Signal(int)     # project_index (Fix #3)

    def __init__(self, index: int, name: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.name = name
        self._status = "ready"
        self._file_tabs: Dict[str, FileTabButton] = {}
        self._active_file: Optional[str] = None

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header row ──
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(6, 3, 6, 3)
        header_layout.setSpacing(4)

        # Checkbox for selection
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(True)
        self._checkbox.setFixedWidth(18)
        self._checkbox.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 14px; height: 14px; border-radius: 3px;
                border: 1px solid {Theme.BORDER};
                background-color: {Theme.SURFACE0};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.BLUE};
                border-color: {Theme.BLUE};
            }}
        """)
        header_layout.addWidget(self._checkbox)

        # Number + Name
        idx_label = QLabel(f"{index + 1:02d}.")
        idx_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold; border: none;")
        idx_label.setFixedWidth(24)
        header_layout.addWidget(idx_label)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px; border: none;")
        name_label.setMinimumWidth(60)
        header_layout.addWidget(name_label, stretch=1)

        # File tabs
        for ft in FILE_TYPES:
            btn = FileTabButton(index, ft)
            btn.clicked_file.connect(self._on_file_click)
            self._file_tabs[ft] = btn
            header_layout.addWidget(btn)

        self._status_label = QLabel()
        self._status_label.setFixedWidth(24)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("border: none;")
        header_layout.addWidget(self._status_label)

        # Retry button (Fix #3 — visible only on error)
        self._retry_btn = QPushButton("🔄")
        self._retry_btn.setObjectName("retryBtn")
        self._retry_btn.setMinimumSize(22, 22)
        self._retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._retry_btn.setToolTip("Retry this topic")
        self._retry_btn.setVisible(False)
        self._retry_btn.setStyleSheet(f"""
            QPushButton#retryBtn {{
                background-color: {Theme.YELLOW if hasattr(Theme, 'YELLOW') else '#f9e2af'};
                color: {Theme.CRUST};
                border: none; border-radius: 3px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton#retryBtn:hover {{ background-color: {Theme.BLUE}; }}
        """)
        self._retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.index))
        header_layout.addWidget(self._retry_btn)

        main_layout.addWidget(header_widget)

        # ── Inline viewer (hidden by default, Fix #11: editable) ──
        self._inline_viewer = QTextEdit()
        self._inline_viewer.setReadOnly(False)  # Fix #11: editable
        self._inline_viewer.setVisible(False)
        self._inline_viewer.setMinimumHeight(450)
        self._inline_viewer.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: none;
                border-top: 1px solid {Theme.BORDER};
                padding: 10px 12px;
                font-size: 13px;
                font-family: 'Segoe UI', 'Inter', 'SF Pro Display', sans-serif;
            }}
        """)
        main_layout.addWidget(self._inline_viewer)

        self._update_status_badge()

    def _on_file_click(self, proj_idx: int, file_type: str):
        # Toggle: click same tab → collapse; click different → switch
        if self._active_file == file_type:
            # Collapse
            self._file_tabs[file_type].set_active(False)
            self._active_file = None
            self._inline_viewer.setVisible(False)
        else:
            # Deactivate old
            if self._active_file and self._active_file in self._file_tabs:
                self._file_tabs[self._active_file].set_active(False)
            # Activate new
            self._active_file = file_type
            self._file_tabs[file_type].set_active(True)
            self._inline_viewer.setVisible(True)
            self.file_selected.emit(proj_idx, file_type)

    def show_file_content(self, content: str):
        """Update inline viewer content."""
        self._inline_viewer.setPlainText(content)
        self._inline_viewer.setVisible(True)

    def collapse_viewer(self):
        """Collapse inline viewer."""
        if self._active_file and self._active_file in self._file_tabs:
            self._file_tabs[self._active_file].set_active(False)
        self._active_file = None
        self._inline_viewer.setVisible(False)

    def set_status(self, status: str):
        self._status = status
        self._update_status_badge()
        # Fix #3: Show retry button on error
        self._retry_btn.setVisible(status == "error")

    def _update_status_badge(self):
        emoji, color = STATUS_BADGES.get(self._status, ("?", Theme.SUBTEXT0))
        self._status_label.setText(emoji)
        self._status_label.setToolTip(self._status.capitalize())

    def get_status(self) -> str:
        return self._status

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool):
        self._checkbox.setChecked(checked)


# ═══════════════════════════════════════════════════════════════════
# ParsedProjectsPanel: Main panel (no separate viewer)
# ═══════════════════════════════════════════════════════════════════

class ParsedProjectsPanel(QFrame):
    """Panel displaying parsed projects with inline collapsible viewers.

    Layout:
      ┌─────────────────────────────────────────────┐
      │ 📊 PARSED PROJECTS (3)                       │
      ├─────────────────────────────────────────────┤
      │ 01. Topic A  │Bi│Ma│Pr│Du│SE│ [✅]          │
      │ 02. Topic B  │Bi│Ma│Pr│Du│SE│ [❌]          │
      │   ┌── inline viewer (Prompts) ──┐           │
      │   │ 1. prompt text...           │           │
      │   └─────────────────────────────┘           │
      │ 03. Topic C  │Bi│Ma│Pr│Du│SE│ [⏳]          │
      ├─────────────────────────────────────────────┤
      │ [📤 Add Ready] [📤 Add All] 1/3 queued      │
      └─────────────────────────────────────────────┘
    """

    add_project_to_queue = Signal(int)         # project_index
    add_all_to_queue = Signal()
    retry_project = Signal(int)                   # project_index (Fix #3)
    file_content_changed = Signal(int, str, str)  # proj_idx, file_type, content
    output_type_changed = Signal(str)              # "T2V" or "T2I"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects: List[ProjectRow] = []
        self._project_data: List[dict] = []  # [{file_type: content, ...}, ...]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Color header
        header = QFrame()
        header.setFixedHeight(28)
        header.setStyleSheet(f"QFrame {{ background-color: {Theme.GREEN}; }}")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 0, 10, 0)
        self._header_title = QLabel(f"{t('project_builder.parsed_header')} (0)")
        self._header_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold; font-size: 11px;")
        header_layout.addWidget(self._header_title)
        header_layout.addStretch()
        layout.addWidget(header)

        # ── Project list (scrollable — no splitter) ──
        self._project_scroll = QScrollArea()
        self._project_scroll.setWidgetResizable(True)
        self._project_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._project_container = QWidget()
        self._project_list_layout = QVBoxLayout(self._project_container)
        self._project_list_layout.setContentsMargins(4, 4, 4, 4)
        self._project_list_layout.setSpacing(3)
        self._project_list_layout.addStretch()

        self._project_scroll.setWidget(self._project_container)
        layout.addWidget(self._project_scroll, stretch=1)

        # ── Bottom bar (compact) ──
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(4, 2, 4, 4)
        btn_row.setSpacing(4)

        # T2V / T2I selector
        self._output_combo = QComboBox()
        self._output_combo.setObjectName("outputCombo")
        self._output_combo.addItems(["📹 T2V", "🎯 T2I"])
        self._output_combo.setFixedHeight(24)
        self._output_combo.setFixedWidth(80)
        self._output_combo.setStyleSheet(f"""
            QComboBox#outputCombo {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: none; border-radius: 4px;
                padding: 0 6px; font-size: 11px; font-weight: bold;
            }}
            QComboBox#outputCombo::drop-down {{
                border: none; width: 16px;
            }}
            QComboBox#outputCombo QAbstractItemView {{
                background-color: {Theme.SURFACE0}; color: {Theme.TEXT};
                selection-background-color: {Theme.SURFACE2};
                border: 1px solid {Theme.BORDER};
            }}
        """)
        btn_row.addWidget(self._output_combo)

        self._add_selected_btn = QPushButton(t("project_builder.add_selected"))
        self._add_selected_btn.setFixedHeight(24)
        self._add_selected_btn.setProperty("variant", "success")
        self._add_selected_btn.setProperty("btnSize", "sm")
        self._add_selected_btn.clicked.connect(self._on_add_selected)
        btn_row.addWidget(self._add_selected_btn)

        self._add_all_btn = QPushButton(t("project_builder.add_all"))
        self._add_all_btn.setFixedHeight(24)
        self._add_all_btn.setProperty("variant", "success")
        self._add_all_btn.setProperty("btnSize", "sm")
        self._add_all_btn.clicked.connect(self._on_add_all)
        btn_row.addWidget(self._add_all_btn)

        self._queue_summary = QLabel(t("project_sidebar.queued_summary").replace("{done}", "0").replace("{total}", "0"))
        self._queue_summary.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 10px;"
        )
        btn_row.addWidget(self._queue_summary)
        btn_row.addStretch()

        layout.addLayout(btn_row)

    # ── Public API ─────────────────────────────────────────────

    def clear_projects(self):
        """Remove all project rows."""
        for row in self._projects:
            row.setParent(None)
            row.deleteLater()
        self._projects.clear()
        self._project_data.clear()
        self._update_summary()

    def add_project(self, name: str, files: dict, status: str = "ready"):
        """Add a project.

        Args:
            name: Topic name
            files: {file_type: content} e.g. {"Bible": "...", "Master": "..."}
            status: "generating" | "ready" | "queued" | "error"
        """
        idx = len(self._projects)
        row = ProjectRow(idx, name)
        row.set_status(status)
        row.file_selected.connect(self._on_file_selected)
        row.add_to_queue.connect(lambda i: self.add_project_to_queue.emit(i))
        row.retry_requested.connect(lambda i: self.retry_project.emit(i))

        # Insert before stretch
        insert_pos = self._project_list_layout.count() - 1  # before stretch
        self._project_list_layout.insertWidget(insert_pos, row)

        self._projects.append(row)
        self._project_data.append(files)
        self._update_summary()

    def set_project_status(self, index: int, status: str):
        """Update project status badge."""
        if 0 <= index < len(self._projects):
            self._projects[index].set_status(status)
            self._update_summary()

    def update_project_files(self, index: int, files: dict):
        """Update file contents for a project."""
        if 0 <= index < len(self._project_data):
            self._project_data[index].update(files)

    def get_project_count(self) -> int:
        return len(self._projects)

    def get_queued_count(self) -> int:
        return sum(1 for p in self._projects if p.get_status() == "queued")

    # ── Internal ──────────────────────────────────────────────

    def _on_file_selected(self, project_idx: int, file_type: str):
        """Show file content in inline viewer of that project row."""
        # Collapse other project rows' viewers
        for i, row in enumerate(self._projects):
            if i != project_idx:
                row.collapse_viewer()

        content = self._project_data[project_idx].get(file_type, "(No content)")
        self._projects[project_idx].show_file_content(content)

    def _on_add_selected(self):
        """Add checked projects to queue."""
        import logging
        _log = logging.getLogger("veo.parsed_projects")
        added = 0
        for i, row in enumerate(self._projects):
            checked = row.is_checked()
            status = row.get_status()
            _log.info(f"[ParsedProjects] _on_add_selected: row {i} checked={checked} status={status}")
            # Allow any status except 'generating' — user explicitly clicked Add
            if checked and status != "generating":
                _log.info(f"[ParsedProjects] Emitting add_project_to_queue for index {i}")
                self.add_project_to_queue.emit(i)
                added += 1
        _log.info(f"[ParsedProjects] _on_add_selected: emitted {added} projects")

    def _on_add_all(self):
        """Add ALL projects to queue (ignore checkbox state)."""
        import logging
        _log = logging.getLogger("veo.parsed_projects")
        added = 0
        for i, row in enumerate(self._projects):
            status = row.get_status()
            _log.info(f"[ParsedProjects] _on_add_all: row {i} status={status}")
            # Allow any status except 'generating' — user explicitly clicked Add All
            if status != "generating":
                _log.info(f"[ParsedProjects] Emitting add_project_to_queue for index {i}")
                self.add_project_to_queue.emit(i)
                added += 1
        _log.info(f"[ParsedProjects] _on_add_all: emitted {added} projects")

    def get_output_type(self) -> str:
        """Return 'T2V' or 'T2I' based on combo selection."""
        text = self._output_combo.currentText()
        return "T2I" if "T2I" in text else "T2V"

    def get_checked_indices(self) -> List[int]:
        """Return indices of checked projects."""
        return [i for i, row in enumerate(self._projects) if row.is_checked()]

    def _update_summary(self):
        queued = self.get_queued_count()
        total = len(self._projects)
        checked = sum(1 for r in self._projects if r.is_checked())
        self._queue_summary.setText(f"{queued}/{total} queued · {checked} selected")
        self._header_title.setText(f"{t('project_builder.parsed_header')} ({total})")
