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
    thumbnail_path: str = ""  # file path for preview image
    video_thumbnail_path: str = ""  # file path for video preview (frame/video)
    accent_color: str = ""    # stage-specific accent (fallback: Theme.BLUE)
    metadata: dict = None     # optional extra metadata

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PipelinePromptTable(QWidget):
    """Table widget for pipeline stage prompts — styled like PromptTable.

    Columns (default):       # | Preview | Info | Prompt | Actions (Edit)
    Columns (video mode):    # | Image Preview | Video Preview | Info | Prompt | Actions
    """

    ROW_HEIGHT = 80

    # Signals
    prompt_edited = Signal(int, str)   # (item_index, new_text)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        accent_color: str = "",
        thumb_size: tuple = (70, 52),
        show_video_preview: bool = False,
    ):
        super().__init__(parent)
        self._items: List[PipelinePromptItem] = []
        self._accent = accent_color or Theme.BLUE
        self._thumb_w, self._thumb_h = thumb_size
        self._show_video_preview = show_video_preview
        self._setup_ui()

    # ── UI Setup ─────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        if self._show_video_preview:
            columns = ["#", "Image Preview", "Video Preview", "Info", "Prompt", ""]
        else:
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
        if self._show_video_preview:
            # 6-column mode: # | Image Preview | Video Preview | Info | Prompt | Actions
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(0, 36)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(1, self._thumb_w + 20)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(2, self._thumb_w + 20)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(3, 140)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(5, 70)
        else:
            # 5-column mode: # | Preview | Info | Prompt | Actions
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(0, 36)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(1, self._thumb_w + 20)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(2, 140)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
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

        # Determine column offsets based on mode
        if self._show_video_preview:
            col_idx, col_img, col_vid, col_info, col_prompt, col_action = 0, 1, 2, 3, 4, 5
        else:
            col_idx, col_img, col_vid, col_info, col_prompt, col_action = 0, 1, -1, 2, 3, 4

        # Col: Index
        idx_item = QTableWidgetItem(str(item.index))
        idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_item.setForeground(QColor(Theme.SUBTEXT0))
        self.table.setItem(row_idx, col_idx, idx_item)

        # Col: Image Preview thumbnail
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
            thumb_btn.clicked.connect(
                lambda checked=False, idx=row_idx: self._open_image_preview(idx)
            )
        else:
            thumb_btn.setText("\u23f3\n\U0001f5bc\ufe0f")
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
        thumb_container = QWidget()
        thumb_container.setStyleSheet("background: transparent; border: none;")
        thumb_lay = QHBoxLayout(thumb_container)
        thumb_lay.setContentsMargins(4, 4, 4, 4)
        thumb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_lay.addWidget(thumb_btn)
        self.table.setCellWidget(row_idx, col_img, thumb_container)

        # Col: Video Preview thumbnail (only in video mode)
        if self._show_video_preview:
            vid_btn = QPushButton()
            vid_btn.setFixedSize(self._thumb_w, self._thumb_h)
            has_vid = item.video_thumbnail_path and os.path.isfile(item.video_thumbnail_path)
            if has_vid:
                pix = QPixmap(item.video_thumbnail_path).scaled(
                    self._thumb_w - 4, self._thumb_h - 4,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                vid_btn.setIcon(pix)
                vid_btn.setIconSize(QSize(self._thumb_w - 4, self._thumb_h - 4))
                # Try to find actual video file for click-to-open
                vid_btn.setToolTip(f"Click to play video")
                vid_btn.clicked.connect(
                    lambda checked=False, idx=row_idx: self._open_video_preview(idx)
                )
            else:
                vid_btn.setText("\u23f3\n\U0001f3ac")
                vid_btn.setToolTip("Video will appear after Queue processes this task")
            vid_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Theme.MANTLE};
                    border: 1px dashed {Theme.OVERLAY0};
                    border-radius: 4px;
                    font-size: 14px; color: {Theme.SUBTEXT0};
                }}
                QPushButton:hover {{ border-color: {Theme.PEACH}; }}
            """)
            vid_container = QWidget()
            vid_container.setStyleSheet("background: transparent; border: none;")
            vid_lay = QHBoxLayout(vid_container)
            vid_lay.setContentsMargins(4, 4, 4, 4)
            vid_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vid_lay.addWidget(vid_btn)
            self.table.setCellWidget(row_idx, col_vid, vid_container)

        # Col: Info (name + metadata)
        info_lbl = QLabel(item.name)
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet(f"""
            color: {accent}; font-weight: bold; font-size: 11px;
            background: transparent; border: none; padding: 4px;
        """)
        self.table.setCellWidget(row_idx, col_info, info_lbl)

        # Col: Prompt text
        prompt_item = QTableWidgetItem(item.prompt)
        prompt_item.setForeground(QColor(Theme.TEXT))
        prompt_item.setToolTip(item.prompt)
        self.table.setItem(row_idx, col_prompt, prompt_item)

        # Col: Actions (Edit button)
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
        self.table.setCellWidget(row_idx, col_action, action_container)

    # ── In-app preview helpers ───────────────────────────────────

    def _open_image_preview(self, row_idx: int):
        """Open in-app image viewer at the given row, with all items navigable."""
        from ui.tabs.project_components.media_preview import ImagePreviewDialog
        paths = [it.thumbnail_path for it in self._items if it.thumbnail_path]
        labels = [it.name for it in self._items if it.thumbnail_path]
        if not paths:
            return
        # Map row_idx to index in filtered paths list
        target_path = self._items[row_idx].thumbnail_path if row_idx < len(self._items) else ""
        start = paths.index(target_path) if target_path in paths else 0
        ImagePreviewDialog.show_preview(self, paths, start, labels)

    def _open_video_preview(self, row_idx: int):
        """Open in-app video player at the given row, with all items navigable."""
        from ui.tabs.project_components.media_preview import VideoPreviewDialog
        paths, labels = [], []
        for it in self._items:
            vp = (it.metadata or {}).get("video_path", it.video_thumbnail_path)
            if vp and os.path.isfile(vp):
                paths.append(vp)
                labels.append(it.name)
        if not paths:
            return
        # Map row_idx → index in filtered list
        item = self._items[row_idx] if row_idx < len(self._items) else None
        target = (item.metadata or {}).get("video_path", item.video_thumbnail_path) if item else ""
        start = paths.index(target) if target in paths else 0
        VideoPreviewDialog.show_preview(self, paths, start, labels)

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
                font-family: 'SF Pro Display', 'Inter', sans-serif;
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
                # Update table cell — prompt column depends on mode
                prompt_col = 4 if self._show_video_preview else 3
                prompt_cell = self.table.item(row_idx, prompt_col)
                if prompt_cell:
                    prompt_cell.setText(new_text)
                    prompt_cell.setToolTip(new_text)
                self.prompt_edited.emit(item.index, new_text)
