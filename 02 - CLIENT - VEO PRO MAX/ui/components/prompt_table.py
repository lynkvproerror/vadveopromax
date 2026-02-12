"""
VEO Pro Max - Prompt Table Component (PySide6)

Reference: TAB_01_TEXT_TO_VIDEO.md → Parsed Prompts section
Migrated from CustomTkinter to PySide6.
Supports image columns for I2V, R2V, I2I tabs.
"""

from typing import Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum
import re
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QAbstractItemView, QLabel, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.components.image_slot_widget import ImageSlotWidget


class ImageMode(Enum):
    """Image column mode per tab type."""
    NONE = "none"         # T2V, T2I — no image columns
    I2V = "i2v"           # 2 columns: Start Image, End Image
    R2V = "r2v"           # 3 columns: Ref 1, Ref 2, Ref 3
    I2I = "i2i"           # 2 default + expandable to 10


class PromptStatus(Enum):
    """Status of a prompt in the table."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Tag extraction pattern
_TAG_PATTERN = re.compile(r'\[([^\]]+)\]')


@dataclass
class PromptRow:
    """Data for a single prompt row."""
    index: int
    text: str
    continuation_from: Optional[int] = None
    status: PromptStatus = PromptStatus.PENDING
    image_path: Optional[str] = None
    start_frame: Optional[str] = None
    end_frame: Optional[str] = None
    image_tags: List[str] = field(default_factory=list)  # Extracted [tag] references
    
    @property
    def is_continuation(self) -> bool:
        return self.continuation_from is not None
    
    @property
    def continuation_label(self) -> str:
        if self.continuation_from is not None:
            return f"🔗 ← #{self.continuation_from}"
        return "⚪ Start"
    
    @property
    def start_frame_label(self) -> str:
        """Display label for start frame."""
        if self.continuation_from is not None:
            return f"🔗←#{self.continuation_from}"
        if self.start_frame:
            return f"🖼️ {self.start_frame}"
        return "➕"
    
    @property
    def end_frame_label(self) -> str:
        """Display label for end frame."""
        if self.end_frame:
            return f"🖼️ {self.end_frame}"
        return "🔒"
    
    def extract_tags(self):
        """Extract [tag] references from text and populate image_tags."""
        self.image_tags = _TAG_PATTERN.findall(self.text)


class PromptTable(QWidget):
    """Table widget showing parsed prompts (PySide6).
    
    Columns vary by image_mode:
    - NONE: #, Prompt, Continue, Status, Actions
    - I2V:  #, Start Img, End Img, Prompt, Continue, Status, Actions
    - R2V:  #, Ref 1, Ref 2, Ref 3, Prompt, Continue, Status, Actions
    - I2I:  #, Img 1, Img 2, ..., Prompt, Continue, Status, Actions
    """
    
    ROW_HEIGHT = 32
    ROW_HEIGHT_WITH_IMAGES = 100  # Taller rows for image thumbnails
    
    # Signals
    edit_clicked = Signal(int)  # index
    delete_clicked = Signal(int)  # index
    continuation_toggled = Signal(int, bool)  # row_index, is_checked
    
    # Image column configs per mode
    _IMAGE_CONFIGS = {
        ImageMode.NONE: {'labels': [], 'max': 0, 'expandable': False},
        ImageMode.I2V:  {'labels': ['Start', 'End'], 'max': 2, 'expandable': False},
        ImageMode.R2V:  {'labels': ['Ref 1', 'Ref 2', 'Ref 3'], 'max': 3, 'expandable': False},
        ImageMode.I2I:  {'labels': ['Img 1', 'Img 2'], 'max': 10, 'expandable': True},
    }
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_edit: Optional[Callable[[int], None]] = None,
        on_delete: Optional[Callable[[int], None]] = None,
        image_mode: ImageMode = ImageMode.NONE,
        accent_color: str = "",
    ):
        super().__init__(parent)
        
        self.on_edit = on_edit
        self.on_delete = on_delete
        self._rows: List[PromptRow] = []
        self._refreshing = False  # Guard against re-entrance
        self._image_mode = image_mode
        self._accent_color = accent_color or Theme.BLUE
        self._image_config = self._IMAGE_CONFIGS[image_mode]
        self._image_col_count = len(self._image_config['labels'])  # Current visible image cols
        self._image_slots: dict = {}  # {row_idx: [ImageSlotWidget, ...]}
        
        self._setup_ui()
    
    def _build_columns(self):
        """Build column headers based on image_mode."""
        cols = ["#"]
        # Image columns
        for label in self._image_config['labels']:
            cols.append(label)
        # Standard columns
        cols.extend(["Prompt", "Continue", "Status", "Actions"])
        return cols
    
    def _col_index(self, name: str) -> int:
        """Get column index by name."""
        cols = self._build_columns()
        try:
            return cols.index(name)
        except ValueError:
            return -1
    
    def _setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        columns = self._build_columns()
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        
        # Style table
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
        """)
        
        # Configure headers
        header = self.table.horizontalHeader()
        
        # # column — fixed
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        
        # Image columns — fixed width for thumbnails
        img_col_width = 92  # Fits ImageSlotWidget (84+8)
        for i in range(1, 1 + self._image_col_count):
            header.setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, img_col_width)
        
        # Prompt — stretch
        prompt_col = self._col_index("Prompt")
        header.setSectionResizeMode(prompt_col, QHeaderView.Stretch)
        
        # Continue, Status, Actions — fixed
        cont_col = self._col_index("Continue")
        status_col = self._col_index("Status")
        actions_col = self._col_index("Actions")
        
        for col, width in [(cont_col, 100), (status_col, 70), (actions_col, 90)]:
            if col >= 0:
                header.setSectionResizeMode(col, QHeaderView.Fixed)
                self.table.setColumnWidth(col, width)
        
        # Selection behavior
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        
        # Edit triggers
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        layout.addWidget(self.table)
    
    def set_prompts(self, prompts: List[PromptRow]):
        """Set all prompts in the table."""
        self._rows = prompts
        self._refresh_table()
    
    def add_prompt(self, text: str, continuation_from: Optional[int] = None):
        """Add a new prompt to the table."""
        index = len(self._rows) + 1
        row = PromptRow(
            index=index,
            text=text,
            continuation_from=continuation_from,
        )
        self._rows.append(row)
        self._add_row_to_table(row)
    
    def _refresh_table(self):
        """Refresh table with current rows."""
        self._refreshing = True
        self.table.setRowCount(0)
        self._image_slots.clear()
        for row in self._rows:
            self._add_row_to_table(row)
        self._refreshing = False
    
    def _add_row_to_table(self, row: PromptRow):
        """Add a single row to the table."""
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        
        has_images = self._image_mode != ImageMode.NONE
        row_h = self.ROW_HEIGHT_WITH_IMAGES if has_images else self.ROW_HEIGHT
        self.table.setRowHeight(row_idx, row_h)
        
        # Extract tags from prompt text
        row.extract_tags()
        
        # Column: #
        index_item = QTableWidgetItem(str(row.index))
        index_item.setTextAlignment(Qt.AlignCenter)
        index_item.setForeground(QColor(Theme.SUBTEXT0))
        self.table.setItem(row_idx, 0, index_item)
        
        # Image columns (if any)
        if has_images:
            self._add_image_cells(row_idx, row)
        
        # Column: Prompt text (truncated)
        prompt_col = self._col_index("Prompt")
        prompt_text = row.text[:80] + "..." if len(row.text) > 80 else row.text
        prompt_item = QTableWidgetItem(prompt_text)
        prompt_item.setForeground(QColor(Theme.TEXT))
        prompt_item.setToolTip(row.text)  # Full text on hover
        self.table.setItem(row_idx, prompt_col, prompt_item)
        
        # Column: Continuation — interactive checkbox
        cont_col = self._col_index("Continue")
        cont_widget = QWidget()
        cont_layout = QHBoxLayout(cont_widget)
        cont_layout.setContentsMargins(4, 0, 4, 0)
        cont_layout.setSpacing(4)
        cont_layout.setAlignment(Qt.AlignCenter)
        
        cont_cb = QCheckBox()
        cont_cb.setObjectName(f"cont_cb_{row_idx}")
        cont_cb.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {Theme.GREEN};
                border: 1px solid {Theme.GREEN};
                border-radius: 3px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {Theme.SURFACE1};
                border: 1px solid {Theme.BORDER};
                border-radius: 3px;
            }}
            QCheckBox::indicator:disabled {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.SURFACE1};
            }}
        """)
        
        cont_label = QLabel()
        cont_label.setObjectName(f"cont_label_{row_idx}")
        
        # Set initial state BEFORE connecting signal (no spurious triggers)
        if row_idx == 0:
            cont_cb.setChecked(False)
            cont_cb.setEnabled(False)
            cont_label.setText("Start")
            cont_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        elif row.is_continuation:
            cont_cb.setChecked(True)
            cont_label.setText(f"← #{row.continuation_from}")
            cont_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
        else:
            cont_cb.setChecked(False)
            cont_label.setText("Start")
            cont_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        
        # Connect signal AFTER setting initial state
        cont_cb.stateChanged.connect(
            lambda state, idx=row_idx: self._on_cont_toggle(idx, state == Qt.Checked)
        )
        
        cont_layout.addWidget(cont_cb)
        cont_layout.addWidget(cont_label)
        self.table.setCellWidget(row_idx, cont_col, cont_widget)
        
        # Column: Status
        status_col = self._col_index("Status")
        status_item = QTableWidgetItem(row.status.value.capitalize())
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor(self._get_status_color(row.status)))
        self.table.setItem(row_idx, status_col, status_item)
        
        # Column: Actions — visible styled buttons
        actions_col = self._col_index("Actions")
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(4, 2, 4, 2)
        actions_layout.setSpacing(4)
        
        edit_btn = QPushButton("✏")
        edit_btn.setFixedSize(28, 28)
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {Theme.BLUE};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
            }}
        """)
        edit_btn.clicked.connect(lambda checked, idx=row_idx: self._on_edit(idx))
        actions_layout.addWidget(edit_btn)
        
        delete_btn = QPushButton("🗑")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {Theme.RED};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {Theme.RED};
                color: {Theme.CRUST};
            }}
        """)
        delete_btn.clicked.connect(lambda checked, idx=row_idx: self._on_delete(idx))
        actions_layout.addWidget(delete_btn)
        
        self.table.setCellWidget(row_idx, actions_col, actions_widget)
    
    def _add_image_cells(self, row_idx: int, row: PromptRow):
        """Add image slot widgets to image columns for this row."""
        slots = []
        labels = self._image_config['labels']
        
        for i, label in enumerate(labels):
            col = 1 + i  # Image columns start at column 1
            slot = ImageSlotWidget(label=label, accent_color=self._accent_color)
            
            # Auto-fill from tags
            if i < len(row.image_tags):
                slot.set_tag(row.image_tags[i])
            
            self.table.setCellWidget(row_idx, col, slot)
            slots.append(slot)
        
        # For I2I expandable: add more slots if tags exceed default
        if self._image_config['expandable'] and len(row.image_tags) > len(labels):
            extra_tags = row.image_tags[len(labels):]
            for j, tag in enumerate(extra_tags):
                if len(labels) + j >= self._image_config['max']:
                    break
                # Need to add extra column if not present
                extra_col = 1 + len(labels) + j
                if extra_col >= self.table.columnCount() - 4:  # Before Prompt/Continue/Status/Actions
                    self._expand_image_columns(len(labels) + j + 1)
                slot = ImageSlotWidget(
                    label=f"Img {len(labels) + j + 1}",
                    accent_color=self._accent_color,
                )
                slot.set_tag(tag)
                self.table.setCellWidget(row_idx, extra_col, slot)
                slots.append(slot)
        
        self._image_slots[row_idx] = slots
    
    def _expand_image_columns(self, new_count: int):
        """Expand image columns for I2I mode."""
        current = self._image_col_count
        if new_count <= current:
            return
        new_count = min(new_count, self._image_config['max'])
        
        # Insert new columns before Prompt column
        for i in range(current, new_count):
            col = 1 + i
            self.table.insertColumn(col)
            self.table.setHorizontalHeaderItem(col, QTableWidgetItem(f"Img {i+1}"))
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, 92)
        
        self._image_col_count = new_count
    
    def get_row_image_tags(self, row_idx: int) -> List[str]:
        """Get image tags from slots for a specific row."""
        slots = self._image_slots.get(row_idx, [])
        return [s.tag for s in slots if s.tag]
    
    def _get_status_color(self, status: PromptStatus) -> str:
        """Get color for status."""
        colors = {
            PromptStatus.PENDING: Theme.SUBTEXT1,
            PromptStatus.QUEUED: Theme.BLUE,
            PromptStatus.PROCESSING: Theme.YELLOW,
            PromptStatus.COMPLETED: Theme.GREEN,
            PromptStatus.FAILED: Theme.RED,
        }
        return colors.get(status, Theme.SUBTEXT1)
    
    def _on_cont_toggle(self, row_idx: int, checked: bool):
        """Handle per-row continuation checkbox toggle.
        
        Updates data and label IN-PLACE without rebuilding the table.
        """
        if self._refreshing:
            return
        if not (0 <= row_idx < len(self._rows)):
            return
        
        # Update data
        if checked and row_idx > 0:
            self._rows[row_idx].continuation_from = self._rows[row_idx - 1].index
        else:
            self._rows[row_idx].continuation_from = None
        
        # Update label in-place (no table rebuild)
        cont_col = self._col_index("Continue")
        cont_widget = self.table.cellWidget(row_idx, cont_col)
        if cont_widget:
            cont_label = cont_widget.findChild(QLabel)
            if cont_label:
                if checked and row_idx > 0:
                    cont_label.setText(f"← #{self._rows[row_idx - 1].index}")
                    cont_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
                else:
                    cont_label.setText("Start")
                    cont_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        
        # Emit signal for tab handlers
        self.continuation_toggled.emit(row_idx, checked)
    
    def _on_edit(self, index: int):
        """Handle edit button click."""
        self.edit_clicked.emit(index)
        if self.on_edit:
            self.on_edit(index)
    
    def _on_delete(self, index: int):
        """Handle delete button click."""
        self.delete_clicked.emit(index)
        if self.on_delete:
            self.on_delete(index)
    
    def get_prompts(self) -> List[PromptRow]:
        """Get all prompts."""
        return self._rows.copy()
    
    def update_status(self, index: int, status: PromptStatus):
        """Update status of a specific row."""
        status_col = self._col_index("Status")
        for i, row in enumerate(self._rows):
            if row.index == index:
                row.status = status
                # Update table item
                status_item = self.table.item(i, status_col)
                if status_item:
                    status_item.setText(status.value.capitalize())
                    status_item.setForeground(QColor(self._get_status_color(status)))
                break
    
    def clear(self):
        """Clear all prompts from table."""
        self._rows.clear()
        self.table.setRowCount(0)
    
    def get_count(self) -> int:
        """Get number of prompts."""
        return len(self._rows)
