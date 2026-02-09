"""
VEO Pro Max - Prompt Table Component (PySide6)

Reference: TAB_01_TEXT_TO_VIDEO.md → Parsed Prompts section
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
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


class PromptStatus(Enum):
    """Status of a prompt in the table."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


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


class PromptTable(QWidget):
    """Table widget showing parsed prompts (PySide6).
    
    Columns: #, Prompt, Continue, Status, Actions
    """
    
    ROW_HEIGHT = 32
    
    # Signals
    edit_clicked = Signal(int)  # index
    delete_clicked = Signal(int)  # index
    continuation_toggled = Signal(int, bool)  # row_index, is_checked
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_edit: Optional[Callable[[int], None]] = None,
        on_delete: Optional[Callable[[int], None]] = None,
    ):
        super().__init__(parent)
        
        self.on_edit = on_edit
        self.on_delete = on_delete
        self._rows: List[PromptRow] = []
        self._refreshing = False  # Guard against re-entrance
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "Prompt", "Continue", "Status", "Actions"])
        
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
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # #
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Prompt
        header.setSectionResizeMode(2, QHeaderView.Fixed)  # Continue
        header.setSectionResizeMode(3, QHeaderView.Fixed)  # Status
        header.setSectionResizeMode(4, QHeaderView.Fixed)  # Actions
        
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 70)
        self.table.setColumnWidth(4, 90)
        
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
        for row in self._rows:
            self._add_row_to_table(row)
        self._refreshing = False
    
    def _add_row_to_table(self, row: PromptRow):
        """Add a single row to the table."""
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        self.table.setRowHeight(row_idx, self.ROW_HEIGHT)
        
        # Index
        index_item = QTableWidgetItem(str(row.index))
        index_item.setTextAlignment(Qt.AlignCenter)
        index_item.setForeground(QColor(Theme.SUBTEXT0))
        self.table.setItem(row_idx, 0, index_item)
        
        # Prompt text (truncated)
        prompt_text = row.text[:50] + "..." if len(row.text) > 50 else row.text
        prompt_item = QTableWidgetItem(prompt_text)
        prompt_item.setForeground(QColor(Theme.TEXT))
        self.table.setItem(row_idx, 1, prompt_item)
        
        # Continuation — interactive checkbox
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
        self.table.setCellWidget(row_idx, 2, cont_widget)
        
        # Status
        status_item = QTableWidgetItem(row.status.value.capitalize())
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor(self._get_status_color(row.status)))
        self.table.setItem(row_idx, 3, status_item)
        
        # Actions — visible styled buttons
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
        
        self.table.setCellWidget(row_idx, 4, actions_widget)
    
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
        cont_widget = self.table.cellWidget(row_idx, 2)
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
        for i, row in enumerate(self._rows):
            if row.index == index:
                row.status = status
                # Update table item
                status_item = self.table.item(i, 3)
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
