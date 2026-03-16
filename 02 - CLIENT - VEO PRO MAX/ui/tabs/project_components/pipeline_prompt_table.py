"""
PipelinePromptTable — PromptTable-style component for Project Builder stages.

Replicates the look-and-feel of the main tabs' PromptTable (QTableWidget with
# / Preview / Info / Prompt / Actions columns) but adapted for pipeline data:
  - Thumbnails are display-only file paths (not ImageSlotWidget tags)
  - No continuation chains
  - Edit dialog matches PromptTable's modal exactly
  - Prompts come from pipeline state, not user text input

Used by _update_thumbnails() in tab_project.py for Stages 4-6.
"""

from dataclasses import dataclass
from typing import Optional, List
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QAbstractItemView, QLabel, QDialog,
    QTextEdit, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPixmap

from config.theme import Theme


@dataclass
class PipelinePromptItem:
    """Data for a single row in the pipeline prompt table."""
    index: int
    name: str               # e.g. "👤 Character 1", "Scene 3 • I2V • 8s"
    prompt: str
    thumbnail_path: str = ""  # file path for preview image/video frame
    accent_color: str = ""    # stage-specific accent (fallback: Theme.BLUE)
    metadata: dict = None     # optional extra metadata

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PipelinePromptTable(QWidget):
    """Table widget for pipeline stage prompts — styled like PromptTable.

    Columns: # | Preview | Info | Prompt | Actions (Edit)
    """

    ROW_HEIGHT = 80

    # Signals
    prompt_edited = Signal(int, str)   # (item_index, new_text)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        accent_color: str = "",
        thumb_size: tuple = (70, 52),
    ):
        super().__init__(parent)
        self._items: List[PipelinePromptItem] = []
        self._accent = accent_color or Theme.BLUE
        self._thumb_w, self._thumb_h = thumb_size
        self._setup_ui()

    # ── UI Setup ─────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        columns = ["#", "Preview", "Info", "Prompt", ""]
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        # Style — identical to PromptTable
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Theme.SURFACE0};
                gridline-color: {Theme.BORDER};
                border: none;
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background-color: {Theme.SURFACE2};
            }}
            QHeaderView::section {{
                background-color: {Theme.SURFACE1};
                color: {Theme.SUBTEXT0};
                border: 1px solid {Theme.BORDER};
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
        """)

        header = self.table.horizontalHeader()
        # # column — fixed 36px
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        # Preview — fixed
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, self._thumb_w + 20)
        # Info — fixed 140px
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 140)
        # Prompt — stretch
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # Actions — fixed 70px
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 70)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        layout.addWidget(self.table)

    # ── Public API ───────────────────────────────────────────────

    def set_items(self, items: List[PipelinePromptItem]):
        """Populate the table with pipeline prompt items."""
        self._items = list(items)
        self._refresh_table()

    def get_edited_prompts(self) -> List[tuple]:
        """Return [(index, current_text), ...] for all items."""
        return [(item.index, item.prompt) for item in self._items]

    def get_items(self) -> List[PipelinePromptItem]:
        """Return all items (with any edits applied)."""
        return list(self._items)

    # ── Internal ─────────────────────────────────────────────────

    def _refresh_table(self):
        self.table.setRowCount(0)
        for item in self._items:
            self._add_row(item)

    def _add_row(self, item: PipelinePromptItem):
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        self.table.setRowHeight(row_idx, self.ROW_HEIGHT)

        accent = item.accent_color or self._accent

        # Col 0: Index
        idx_item = QTableWidgetItem(str(item.index))
        idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_item.setForeground(QColor(Theme.SUBTEXT0))
        self.table.setItem(row_idx, 0, idx_item)

        # Col 1: Preview thumbnail
        thumb_btn = QPushButton()
        thumb_btn.setFixedSize(self._thumb_w, self._thumb_h)
        has_thumb = item.thumbnail_path and os.path.isfile(item.thumbnail_path)
        if has_thumb:
            pix = QPixmap(item.thumbnail_path).scaled(
                self._thumb_w - 4, self._thumb_h - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb_btn.setIcon(pix)
            thumb_btn.setIconSize(QSize(self._thumb_w - 4, self._thumb_h - 4))
            thumb_btn.setToolTip(f"Click to preview: {item.thumbnail_path}")
            fp = item.thumbnail_path
            thumb_btn.clicked.connect(lambda checked=False, p=fp: os.startfile(p))
        else:
            thumb_btn.setText("⏳\n🖼️")
            thumb_btn.setToolTip("Image will appear after generation")
        thumb_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.MANTLE};
                border: 1px dashed {Theme.OVERLAY0};
                border-radius: 4px;
                font-size: 14px; color: {Theme.SUBTEXT0};
            }}
            QPushButton:hover {{ border-color: {accent}; }}
        """)
        # Center in cell
        thumb_container = QWidget()
        thumb_container.setStyleSheet("background: transparent; border: none;")
        thumb_lay = QHBoxLayout(thumb_container)
        thumb_lay.setContentsMargins(4, 4, 4, 4)
        thumb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_lay.addWidget(thumb_btn)
        self.table.setCellWidget(row_idx, 1, thumb_container)

        # Col 2: Info (name + metadata)
        info_lbl = QLabel(item.name)
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"""
            color: {accent}; font-weight: bold; font-size: 11px;
            background: transparent; border: none; padding: 4px;
        """)
        self.table.setCellWidget(row_idx, 2, info_lbl)

        # Col 3: Prompt text
        prompt_item = QTableWidgetItem(item.prompt)
        prompt_item.setForeground(QColor(Theme.TEXT))
        prompt_item.setToolTip(item.prompt)
        self.table.setItem(row_idx, 3, prompt_item)

        # Col 4: Actions (Edit button)
        edit_btn = QPushButton("Edit")
        edit_btn.setMinimumSize(55, 30)
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {accent};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {accent};
                color: {Theme.CRUST};
            }}
        """)
        edit_btn.setToolTip("Edit this prompt")
        edit_btn.clicked.connect(lambda checked=False, idx=row_idx: self._on_edit(idx))

        action_container = QWidget()
        action_container.setStyleSheet("background: transparent; border: none;")
        action_lay = QHBoxLayout(action_container)
        action_lay.setContentsMargins(4, 4, 4, 4)
        action_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_lay.addWidget(edit_btn)
        self.table.setCellWidget(row_idx, 4, action_container)

    def _on_edit(self, row_idx: int):
        """Open modal edit dialog — same styling as PromptTable._on_edit."""
        if not (0 <= row_idx < len(self._items)):
            return

        item = self._items[row_idx]

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Prompt — {item.name}")
        dialog.setMinimumSize(500, 300)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.BASE};
            }}
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)

        text_edit = QTextEdit()
        text_edit.setPlainText(item.prompt)
        text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.SURFACE0};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }}
            QTextEdit:focus {{
                border: 1px solid {self._accent};
            }}
        """)
        layout.addWidget(text_edit)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self._accent};
                color: {Theme.CRUST};
            }}
        """)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = text_edit.toPlainText().strip()
            if new_text and new_text != item.prompt:
                item.prompt = new_text
                # Update table cell
                prompt_cell = self.table.item(row_idx, 3)
                if prompt_cell:
                    prompt_cell.setText(new_text)
                    prompt_cell.setToolTip(new_text)
                self.prompt_edited.emit(item.index, new_text)
