"""
VEO Pro Max — Parsed Projects Panel for Project Builder

Displays generated projects with:
- Horizontal file tabs per project (Bible, Master, Prompts, Dubbing, SEO)
- Adaptive file viewer (markdown / prompt table / text / structured)
- Queue status badges (⏳ Generating, ❌ Not queued, ✅ Queued, ⚠️ Error)
- Add to Queue / Add All buttons
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QTextEdit,
    QSplitter, QStackedWidget,
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


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
        super().__init__(file_type[:2], parent)  # "Bi", "Ma", "Pr", "Du", "SE"
        self.project_idx = project_idx
        self.file_type = file_type
        self._active = False

        self.setFixedSize(32, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(file_type)
        self._apply_style()
        self.clicked.connect(lambda: self.clicked_file.emit(self.project_idx, self.file_type))

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.BLUE};
                    color: {Theme.CRUST};
                    border: none; border-radius: 3px;
                    font-size: 10px; font-weight: bold;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.SURFACE2};
                    color: {Theme.TEXT};
                    border: 1px solid {Theme.BORDER}; border-radius: 3px;
                    font-size: 10px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.BLUE};
                    color: {Theme.CRUST};
                }}
            """)

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()


# ═══════════════════════════════════════════════════════════════════
# ProjectRow: One project row with file tabs + status
# ═══════════════════════════════════════════════════════════════════

class ProjectRow(QFrame):
    """A single project row: [#] [Name] [Bi][Ma][Pr][Du][SE] [Status]"""

    file_selected = Signal(int, str)  # (project_index, file_type)
    add_to_queue = Signal(int)        # project_index

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
                padding: 2px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # Number + Name
        idx_label = QLabel(f"{index + 1:02d}.")
        idx_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold; border: none;")
        idx_label.setFixedWidth(24)
        layout.addWidget(idx_label)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px; border: none;")
        name_label.setMinimumWidth(80)
        layout.addWidget(name_label, stretch=1)

        # File tabs
        for ft in FILE_TYPES:
            btn = FileTabButton(index, ft)
            btn.clicked_file.connect(self._on_file_click)
            self._file_tabs[ft] = btn
            layout.addWidget(btn)

        # Status badge
        self._status_label = QLabel()
        self._status_label.setFixedWidth(28)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet("border: none;")
        layout.addWidget(self._status_label)

        self._update_status_badge()

    def _on_file_click(self, proj_idx: int, file_type: str):
        # Deactivate old
        if self._active_file and self._active_file in self._file_tabs:
            self._file_tabs[self._active_file].set_active(False)
        # Activate new
        self._active_file = file_type
        self._file_tabs[file_type].set_active(True)
        self.file_selected.emit(proj_idx, file_type)

    def set_status(self, status: str):
        self._status = status
        self._update_status_badge()

    def _update_status_badge(self):
        emoji, color = STATUS_BADGES.get(self._status, ("?", Theme.SUBTEXT0))
        self._status_label.setText(emoji)
        self._status_label.setToolTip(self._status.capitalize())

    def get_status(self) -> str:
        return self._status


# ═══════════════════════════════════════════════════════════════════
# FileViewer: Adaptive viewer based on file type
# ═══════════════════════════════════════════════════════════════════

class FileViewer(QFrame):
    """Adaptive file viewer that changes display based on file type.

    - Bible (.md):   Markdown text viewer with Edit/Save
    - Master (.txt): Text viewer (will upgrade to PromptTable later)
    - Prompts (.txt): Text viewer (will upgrade to PromptTable later)
    - Dubbing (.txt): Text viewer with Edit/Save
    - SEO (.txt):    Structured viewer with Edit/Save
    """

    content_changed = Signal(int, str, str)  # (project_idx, file_type, new_content)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header
        header_row = QHBoxLayout()
        self._header = QLabel("👁️ File Viewer")
        self._header.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold; border: none;"
        )
        header_row.addWidget(self._header)
        header_row.addStretch()

        self._edit_btn = QPushButton("✏️ Edit")
        self._edit_btn.setFixedSize(60, 24)
        self._edit_btn.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"border-radius: 4px; font-size: 10px; border: none;"
        )
        self._edit_btn.clicked.connect(self._toggle_edit)
        header_row.addWidget(self._edit_btn)

        self._save_btn = QPushButton("💾 Save")
        self._save_btn.setFixedSize(60, 24)
        self._save_btn.setStyleSheet(
            f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
            f"border-radius: 4px; font-size: 10px; font-weight: bold; border: none;"
        )
        self._save_btn.clicked.connect(self._save)
        self._save_btn.setVisible(False)
        header_row.addWidget(self._save_btn)

        layout.addLayout(header_row)

        # Content area
        self._text_view = QTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
            }}
        """)
        layout.addWidget(self._text_view, stretch=1)

        self._current_project_idx = -1
        self._current_file_type = ""
        self._editing = False

    def show_content(self, project_idx: int, file_type: str, content: str):
        """Display file content."""
        self._current_project_idx = project_idx
        self._current_file_type = file_type
        self._editing = False
        self._edit_btn.setVisible(True)
        self._save_btn.setVisible(False)
        self._text_view.setReadOnly(True)

        self._header.setText(f"👁️ {file_type}")
        self._text_view.setPlainText(content)

    def show_empty(self):
        """Show empty state."""
        self._header.setText("👁️ File Viewer")
        self._text_view.setPlainText("Select a file tab above to view content.")
        self._text_view.setReadOnly(True)
        self._edit_btn.setVisible(False)
        self._save_btn.setVisible(False)

    def _toggle_edit(self):
        self._editing = not self._editing
        self._text_view.setReadOnly(not self._editing)
        self._edit_btn.setVisible(not self._editing)
        self._save_btn.setVisible(self._editing)

    def _save(self):
        content = self._text_view.toPlainText()
        self.content_changed.emit(
            self._current_project_idx, self._current_file_type, content
        )
        self._editing = False
        self._text_view.setReadOnly(True)
        self._edit_btn.setVisible(True)
        self._save_btn.setVisible(False)


# ═══════════════════════════════════════════════════════════════════
# ParsedProjectsPanel: Main panel
# ═══════════════════════════════════════════════════════════════════

class ParsedProjectsPanel(QFrame):
    """Panel displaying parsed projects with file tabs and viewer.

    Layout:
      ┌─────────────────────────────────────────────┐
      │ 01. Topic name  │Bi│Ma│Pr│Du│SE│ [✅ Q]    │
      │ 02. Topic name  │Bi│Ma│Pr│Du│SE│ [❌  ]    │
      ├─────────────────────────────────────────────┤
      │ 👁️ FILE VIEWER                              │
      │ (content based on selected file)             │
      └─────────────────────────────────────────────┘
      [📤 Add Selected] [📤 Add All] 2/3 queued
    """

    add_project_to_queue = Signal(int)         # project_index
    add_all_to_queue = Signal()
    file_content_changed = Signal(int, str, str)  # proj_idx, file_type, content

    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects: List[ProjectRow] = []
        self._project_data: List[dict] = []  # [{file_type: content, ...}, ...]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Color header (matches GenerationTabBase)
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.GREEN};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        self._header_title = QLabel("📊 PARSED PROJECTS (0)")
        self._header_title.setStyleSheet(f"color: {Theme.CRUST}; font-weight: bold;")
        header_layout.addWidget(self._header_title)
        header_layout.addStretch()
        layout.addWidget(header)

        # Splitter: project list (top) | file viewer (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Project list (scrollable) ──
        self._project_scroll = QScrollArea()
        self._project_scroll.setWidgetResizable(True)
        # No maxHeight — let splitter/stretching manage
        self._project_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._project_container = QWidget()
        self._project_list_layout = QVBoxLayout(self._project_container)
        self._project_list_layout.setContentsMargins(0, 0, 0, 0)
        self._project_list_layout.setSpacing(3)
        self._project_list_layout.addStretch()

        self._project_scroll.setWidget(self._project_container)
        splitter.addWidget(self._project_scroll)

        # ── File viewer ──
        self._viewer = FileViewer()
        self._viewer.content_changed.connect(self._on_content_changed)
        self._viewer.show_empty()
        splitter.addWidget(self._viewer)

        splitter.setSizes([150, 300])
        layout.addWidget(splitter, stretch=1)

        # ── Bottom buttons ──
        btn_row = QHBoxLayout()

        self._add_selected_btn = QPushButton("📤 Add Selected")
        self._add_selected_btn.setStyleSheet(
            f"background-color: {Theme.BLUE}; color: {Theme.CRUST}; "
            f"height: 32px; border-radius: 6px; font-weight: bold; font-size: 12px;"
        )
        self._add_selected_btn.clicked.connect(self._on_add_selected)
        btn_row.addWidget(self._add_selected_btn)

        self._add_all_btn = QPushButton("📤 Add All")
        self._add_all_btn.setStyleSheet(
            f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
            f"height: 32px; border-radius: 6px; font-weight: bold; font-size: 12px;"
        )
        self._add_all_btn.clicked.connect(lambda: self.add_all_to_queue.emit())
        btn_row.addWidget(self._add_all_btn)

        self._queue_summary = QLabel("0/0 queued")
        self._queue_summary.setStyleSheet(
            f"color: {Theme.SUBTEXT0}; font-size: 11px;"
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
        self._viewer.show_empty()
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
        """Show file content in viewer."""
        # Deactivate other project rows' file tabs
        for i, row in enumerate(self._projects):
            if i != project_idx:
                for ft, btn in row._file_tabs.items():
                    btn.set_active(False)

        content = self._project_data[project_idx].get(file_type, "(No content)")
        self._viewer.show_content(project_idx, file_type, content)

    def _on_content_changed(self, proj_idx: int, file_type: str, content: str):
        """Handle edit+save from viewer."""
        if 0 <= proj_idx < len(self._project_data):
            self._project_data[proj_idx][file_type] = content
        self.file_content_changed.emit(proj_idx, file_type, content)

    def _on_add_selected(self):
        """Add projects that haven't been queued yet."""
        for i, row in enumerate(self._projects):
            if row.get_status() == "ready":
                self.add_project_to_queue.emit(i)

    def _update_summary(self):
        queued = self.get_queued_count()
        total = len(self._projects)
        self._queue_summary.setText(f"{queued}/{total} queued")
        self._header_title.setText(f"📊 PARSED PROJECTS ({total})")
