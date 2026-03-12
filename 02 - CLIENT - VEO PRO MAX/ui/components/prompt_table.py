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
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget, QTableWidgetItem,
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


# Tag extraction patterns:
#   [tag_name]      → tag_name
#   [tag name].png  → tag name.png  (extension outside brackets)
#   @tag_name.png   → tag_name.png  (@ with extension)
#   @"my tag"       → my tag        (@ with quoted tag for spaces)
_TAG_PATTERN = re.compile(r'\[([^\]]+)\](\.\w+)?|@"([^"]+)"|@([\w\-]+(?:\.\w+)?)')


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
    duration: Optional[int] = None                       # Per-scene duration (from JSON)
    metadata: dict = field(default_factory=dict)          # Extra fields (description_vi, narration_vi)
    
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
        """Extract [tag], @tag, and @"quoted tag" references from text."""
        matches = _TAG_PATTERN.findall(self.text)
        tags = []
        for bracket_name, bracket_ext, at_quoted, at_tag in matches:
            if bracket_name:
                # [name] or [name].ext → combine
                tags.append(bracket_name + bracket_ext)
            elif at_quoted:
                # @"tag with spaces"
                tags.append(at_quoted)
            elif at_tag:
                tags.append(at_tag)
        # Deduplicate while preserving first-occurrence order
        # (same tag referenced multiple times → only one image slot)
        self.image_tags = list(dict.fromkeys(tags))


class PromptTable(QWidget):
    """Table widget showing parsed prompts (PySide6).
    
    Columns vary by image_mode:
    - NONE:  #, Prompt, Continue, Actions
    - I2V:   #, Images, Prompt, Continue, Actions
    - R2V:   #, Images, Prompt, Continue, Actions
    - I2I:   #, Images, Prompt, Actions  (no Continue — image mode)
    
    Image slots are displayed inside a single 'Images' column cell
    as mini thumbnails that auto-scale to fit.
    """
    
    ROW_HEIGHT = 40
    ROW_HEIGHT_WITH_IMAGES = 100  # Taller rows for mini image thumbnails
    
    # Signals
    edit_clicked = Signal(int)  # index
    delete_clicked = Signal(int)  # index
    continuation_toggled = Signal(int, bool)  # row_index, is_checked
    slot_image_changed = Signal(int)  # row_index — emitted when a slot image changes
    
    # Image column configs per mode
    _IMAGE_CONFIGS = {
        ImageMode.NONE: {'labels': [], 'max': 0, 'expandable': False},
        ImageMode.I2V:  {'labels': ['Start'], 'max': 1, 'expandable': False},  # Default: START only
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
        show_continuation: bool = True,
    ):
        super().__init__(parent)
        
        self.on_edit = on_edit
        self.on_delete = on_delete
        self._rows: List[PromptRow] = []
        self._refreshing = False  # Guard against re-entrance
        self._image_mode = image_mode
        self._show_continuation = show_continuation
        self._accent_color = accent_color or Theme.BLUE
        self._image_config = self._IMAGE_CONFIGS[image_mode]
        self._image_col_count = 1 if image_mode != ImageMode.NONE else 0  # Single 'Images' column
        self._image_slots: dict = {}  # {row_idx: [ImageSlotWidget, ...]}
        
        # Register library change callback for auto-refresh
        if image_mode != ImageMode.NONE:
            try:
                from services.image_library import get_image_library
                get_image_library().on_change(self._on_library_changed)
            except Exception:
                pass
        
        self._setup_ui()
    
    def set_image_labels(self, labels: list, max_slots: int = 0):
        """Dynamically update image slot labels and max count, then refresh.
        
        Used by I2V tab when switching frame modes:
        - START only → labels=['Start'], max=1
        - START + END → labels=['Start', 'End'], max=2
        """
        if not max_slots:
            max_slots = len(labels)
        self._image_config = dict(self._image_config)  # Copy to avoid mutating class-level
        self._image_config['labels'] = labels
        self._image_config['max'] = max_slots
        if self._rows:
            self._refresh_table()
    
    def _has_continuation(self) -> bool:
        """Whether this table shows the Continue column."""
        return self._show_continuation
    
    def _build_columns(self):
        """Build column headers based on image_mode."""
        cols = ["#"]
        # Single 'Images' column (if mode uses images)
        if self._image_mode != ImageMode.NONE:
            cols.append("Images")
        # Standard columns
        cols.append("Prompt")
        if self._has_continuation():
            cols.append("Continue")
        cols.append("Actions")
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
        
        # Image column — fixed width
        img_col = self._col_index("Images")
        if img_col >= 0:
            img_width = 250 if self._image_config.get('expandable') else 200
            header.setSectionResizeMode(img_col, QHeaderView.Fixed)
            self.table.setColumnWidth(img_col, img_width)
        
        # Prompt — stretch
        prompt_col = self._col_index("Prompt")
        header.setSectionResizeMode(prompt_col, QHeaderView.Stretch)
        
        # Continue — fixed (only for video modes)
        cont_col = self._col_index("Continue")
        if cont_col >= 0:
            header.setSectionResizeMode(cont_col, QHeaderView.Fixed)
            self.table.setColumnWidth(cont_col, 90)
        
        # Actions — fixed
        actions_col = self._col_index("Actions")
        if actions_col >= 0:
            header.setSectionResizeMode(actions_col, QHeaderView.Fixed)
            self.table.setColumnWidth(actions_col, 130)
        
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
        
        # Rebuild column structure
        columns = self._build_columns()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        
        # Re-apply column sizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 40)
        
        img_col = self._col_index("Images")
        if img_col >= 0:
            img_width = 250 if self._image_config.get('expandable') else 200
            header.setSectionResizeMode(img_col, QHeaderView.Fixed)
            self.table.setColumnWidth(img_col, img_width)
        
        prompt_col = self._col_index("Prompt")
        if prompt_col >= 0:
            header.setSectionResizeMode(prompt_col, QHeaderView.Stretch)
        
        cont_col = self._col_index("Continue")
        if cont_col >= 0:
            header.setSectionResizeMode(cont_col, QHeaderView.Fixed)
            self.table.setColumnWidth(cont_col, 90)
        
        actions_col = self._col_index("Actions")
        if actions_col >= 0:
            header.setSectionResizeMode(actions_col, QHeaderView.Fixed)
            self.table.setColumnWidth(actions_col, 130)
        
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
        prompt_item = QTableWidgetItem(row.text)
        prompt_item.setForeground(QColor(Theme.TEXT))
        prompt_item.setToolTip(row.text)  # Full text on hover
        self.table.setItem(row_idx, prompt_col, prompt_item)
        
        # Column: Continuation — interactive checkbox (video modes only)
        if self._has_continuation():
            cont_col = self._col_index("Continue")
            cont_widget = QWidget()
            cont_layout = QHBoxLayout(cont_widget)
            cont_layout.setContentsMargins(0, 0, 0, 0)
            cont_layout.setSpacing(2)
            
            cont_cb = QCheckBox()
            cont_cb.setObjectName(f"cont_cb_{row_idx}")
            cont_cb.setStyleSheet(f"""
                QCheckBox::indicator {{
                    width: 20px;
                    height: 20px;
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
            
            # Set initial state BEFORE connecting signal (no spurious triggers)
            if row_idx == 0:
                cont_cb.setChecked(False)
                cont_cb.setEnabled(False)
            elif row.is_continuation:
                cont_cb.setChecked(True)
            else:
                cont_cb.setChecked(False)
            
            # Connect signal AFTER setting initial state
            cont_cb.stateChanged.connect(
                lambda state, idx=row_idx: self._on_cont_toggle(idx, state == Qt.Checked)
            )
            
            # Center checkbox with stretches
            cont_layout.addStretch()
            cont_layout.addWidget(cont_cb)
            
            # Add continuation label only if active
            if row.is_continuation and row_idx > 0:
                cont_label = QLabel(f"← #{row.continuation_from}")
                cont_label.setObjectName(f"cont_label_{row_idx}")
                cont_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px;")
                cont_layout.addWidget(cont_label)
            
            cont_layout.addStretch()
            self.table.setCellWidget(row_idx, cont_col, cont_widget)
        
        
        # Column: Actions — visible styled buttons with text
        actions_col = self._col_index("Actions")
        actions_widget = QWidget()
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(2, 2, 2, 2)
        actions_layout.setSpacing(4)
        actions_layout.setAlignment(Qt.AlignCenter)
        
        edit_btn = QPushButton("Edit")
        edit_btn.setMinimumSize(55, 30)
        edit_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {Theme.BLUE};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
            }}
        """)
        edit_btn.setToolTip("Edit this prompt")
        edit_btn.clicked.connect(lambda checked, idx=row_idx: self._on_edit(idx))
        actions_layout.addWidget(edit_btn)
        
        delete_btn = QPushButton("Del")
        delete_btn.setMinimumSize(55, 30)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {Theme.RED};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {Theme.RED};
                color: {Theme.CRUST};
            }}
        """)
        delete_btn.setToolTip("Delete this prompt")
        delete_btn.clicked.connect(lambda checked, idx=row_idx: self._on_delete(idx))
        actions_layout.addWidget(delete_btn)
        
        self.table.setCellWidget(row_idx, actions_col, actions_widget)
    
    def _add_image_cells(self, row_idx: int, row: PromptRow):
        """Add image slots inside a single 'Images' column cell."""
        img_col = self._col_index("Images")
        if img_col < 0:
            return
        
        labels = self._image_config['labels']
        max_slots = self._image_config['max']
        expandable = self._image_config.get('expandable', False)
        
        # Determine how many slots to create
        tag_count = len(row.image_tags)
        if expandable:
            slot_count = max(1, tag_count)
        else:
            slot_count = max(len(labels), tag_count)
        slot_count = min(slot_count, max_slots)
        
        # Container widget
        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        
        if expandable:
            # Grid layout: 5 columns per row, wrap to row 2
            COLS_PER_ROW = 5
            grid = QGridLayout(container)
            grid.setContentsMargins(2, 1, 2, 1)
            grid.setSpacing(1)
            
            # Calculate slot size for 5-column grid
            col_width = 250
            mini_size = max((col_width - 4) // COLS_PER_ROW - 4, 30)
            mini_size = min(mini_size, 44)
            
            slots = []
            for i in range(slot_count):
                label = labels[i] if i < len(labels) else f"Img {i+1}"
                slot = ImageSlotWidget(
                    label=label,
                    accent_color=self._accent_color,
                    slot_size=mini_size,
                )
                
                has_image = i < len(row.image_tags) and row.image_tags[i]
                if has_image:
                    slot.set_tag(row.image_tags[i])
                
                slot.image_changed.connect(
                    lambda new_tag, r=row_idx, s=i: self._on_slot_image_changed(r, s, new_tag)
                )
                
                grid_row = i // COLS_PER_ROW
                grid_col = i % COLS_PER_ROW
                
                # Overlay '×' remove button at top-right corner for empty slots
                if not has_image and slot_count > 1:
                    rm_btn = QPushButton("×", slot)  # Parent = slot for overlay
                    rm_size = 14
                    rm_btn.setMinimumSize(rm_size, rm_size)
                    rm_btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {Theme.SURFACE2};
                            color: {Theme.SUBTEXT0};
                            border: 1px solid {Theme.OVERLAY0};
                            border-radius: {rm_size // 2}px;
                            font-size: 9px;
                            font-weight: bold;
                            padding: 0px;
                        }}
                        QPushButton:hover {{
                            background-color: {Theme.RED};
                            color: {Theme.CRUST};
                            border: 1px solid {Theme.RED};
                        }}
                    """)
                    rm_btn.setToolTip("Remove this slot")
                    rm_btn.clicked.connect(
                        lambda checked, r=row_idx, s=i: self._on_remove_slot_clicked(r, s)
                    )
                    # Position at top-right corner of the slot
                    slot_w = slot.sizeHint().width()
                    rm_btn.move(slot_w - rm_size + 2, -2)
                    rm_btn.raise_()
                
                grid.addWidget(slot, grid_row, grid_col, alignment=Qt.AlignCenter)
                
                slots.append(slot)
            
            # Add '+' button (only if below max)
            if slot_count < max_slots:
                plus_btn = QPushButton("+")
                plus_size = min(mini_size, 30)
                plus_btn.setMinimumSize(plus_size, plus_size)
                plus_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Theme.SURFACE1};
                        color: {self._accent_color};
                        border: 2px dashed {self._accent_color};
                        border-radius: 4px;
                        font-size: 16px;
                        font-weight: bold;
                        padding: 0px;
                    }}
                    QPushButton:hover {{
                        background-color: {self._accent_color};
                        color: {Theme.CRUST};
                        border: 2px solid {self._accent_color};
                    }}
                """)
                plus_btn.setToolTip(f"Add image slot (max {max_slots})")
                plus_btn.clicked.connect(
                    lambda checked, r=row_idx: self._on_add_slot_clicked(r)
                )
                plus_row = slot_count // COLS_PER_ROW
                plus_col = slot_count % COLS_PER_ROW
                grid.addWidget(plus_btn, plus_row, plus_col, alignment=Qt.AlignCenter)
            
            # Adjust row height: 2 rows needed when >5 items
            total_items = slot_count + (1 if slot_count < max_slots else 0)
            if total_items > COLS_PER_ROW:
                self.table.setRowHeight(row_idx, 140)
            else:
                self.table.setRowHeight(row_idx, self.ROW_HEIGHT_WITH_IMAGES)
        
        else:
            # Non-expandable (I2V, R2V): simple horizontal layout
            col_width = 200
            items_to_fit = slot_count
            available = col_width - 8
            per_item = max(available // max(items_to_fit, 1) - 6, 30)
            mini_size = min(per_item, 60)
            
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(4, 2, 4, 2)
            h_layout.setSpacing(4)
            h_layout.setAlignment(Qt.AlignCenter)
            
            slots = []
            for i in range(slot_count):
                label = labels[i] if i < len(labels) else f"Img {i+1}"
                slot = ImageSlotWidget(
                    label=label,
                    accent_color=self._accent_color,
                    slot_size=mini_size,
                )
                
                has_image = i < len(row.image_tags) and row.image_tags[i]
                if has_image:
                    slot.set_tag(row.image_tags[i])
                
                slot.image_changed.connect(
                    lambda new_tag, r=row_idx, s=i: self._on_slot_image_changed(r, s, new_tag)
                )
                
                h_layout.addWidget(slot)
                slots.append(slot)
        
        self._image_slots[row_idx] = slots
        self.table.setCellWidget(row_idx, img_col, container)
    
    def _on_add_slot_clicked(self, row_idx: int):
        """Handle '+' button click — add a slot and rebuild that row's image cell."""
        if row_idx >= len(self._rows):
            return
        row = self._rows[row_idx]
        current_slots = len(self._image_slots.get(row_idx, []))
        max_slots = self._image_config['max']
        if current_slots >= max_slots:
            return
        # Pad image_tags to match current visible slot count, then append one more
        while len(row.image_tags) < current_slots:
            row.image_tags.append("")
        row.image_tags.append("")  # The new slot
        # Rebuild only this row's image cell
        self._add_image_cells(row_idx, row)
    
    def _on_remove_slot_clicked(self, row_idx: int, slot_idx: int):
        """Handle '−' button click — remove an empty slot."""
        if row_idx >= len(self._rows):
            return
        row = self._rows[row_idx]
        # Safety: don't remove if slot has an image
        if slot_idx < len(row.image_tags) and row.image_tags[slot_idx]:
            return
        # Remove the tag at this index
        if slot_idx < len(row.image_tags):
            row.image_tags.pop(slot_idx)
        # Ensure at least 1 slot remains
        # Rebuild this row's image cell
        self._add_image_cells(row_idx, row)
    
    def get_row_image_tags(self, row_idx: int) -> List[str]:
        """Get image tags from slots for a specific row."""
        slots = self._image_slots.get(row_idx, [])
        return [s.tag for s in slots if s.tag]
    
    def _on_library_changed(self):
        """Auto-refresh unresolved image slots when library changes.
        
        Called by ImageLibrary.on_change() callback.
        Only re-resolves slots that have a tag but no image yet.
        """
        for row_idx, slots in self._image_slots.items():
            for slot in slots:
                slot.refresh_tag()
    
    def _on_slot_image_changed(self, row_idx: int, slot_idx: int, new_tag: str):
        """Handle slot image change — update [tag] in prompt text.
        
        If the slot had an old tag in the prompt text, replace it.
        If no tag existed for this slot, append [new_tag] to the prompt.
        """
        if row_idx >= len(self._rows):
            return
        row = self._rows[row_idx]
        old_tags = row.image_tags.copy() if row.image_tags else []
        
        import re
        text = row.text
        
        if slot_idx < len(old_tags):
            # Replace existing tag
            old_tag = old_tags[slot_idx]
            # Try to replace [old_tag] with [new_tag]
            pattern = re.escape(f"[{old_tag}]")
            new_text = re.sub(pattern, f"[{new_tag}]", text, count=1)
            if new_text == text:
                # Try @"old_tag" (quoted)
                at_q_pattern = r'@"' + re.escape(old_tag) + r'"'
                new_text = re.sub(at_q_pattern, f'@"{new_tag}"', text, count=1)
            if new_text == text:
                # Try @old_tag (unquoted)
                at_pattern = r'@' + re.escape(old_tag) + r'(?=\s|$)'
                new_text = re.sub(at_pattern, f"@{new_tag}", text, count=1)
            if new_text == text:
                # Still not found, just append
                new_text = text.rstrip() + f" [{new_tag}]"
            row.text = new_text
        else:
            # New slot, append tag
            row.text = text.rstrip() + f" [{new_tag}]"
        
        # Re-extract tags
        row.extract_tags()
        
        # Update the prompt text cell in table
        prompt_col = self._col_index("Prompt")
        item = self.table.item(row_idx, prompt_col)
        if item:
            item.setText(row.text)
            item.setToolTip(row.text)
        
        # Emit signal for tab to sync back to text input
        self.slot_image_changed.emit(row_idx)
    
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
        
        # Refresh table to update checkbox + label layout
        self._refresh_table()
        
        # Emit signal for tab handlers
        self.continuation_toggled.emit(row_idx, checked)
    
    def _on_edit(self, index: int):
        """Handle edit button click — show word-wrapping edit dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        
        if 0 <= index < len(self._rows):
            current_text = self._rows[index].text
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Prompt")
            dialog.setMinimumSize(500, 300)
            dialog.setStyleSheet(f"""
                QDialog {{
                    background-color: {Theme.BASE};
                }}
            """)
            
            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(12, 12, 12, 12)
            
            text_edit = QTextEdit()
            text_edit.setPlainText(current_text)
            text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
            text_edit.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {Theme.SURFACE0};
                    color: {Theme.TEXT};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 13px;
                }}
            """)
            layout.addWidget(text_edit)
            
            btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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
                    background-color: {Theme.BLUE};
                    color: {Theme.CRUST};
                }}
            """)
            btn_box.accepted.connect(dialog.accept)
            btn_box.rejected.connect(dialog.reject)
            layout.addWidget(btn_box)
            
            if dialog.exec() == QDialog.Accepted:
                new_text = text_edit.toPlainText().strip()
                if new_text:
                    self._rows[index].text = new_text
                    self._refresh_table()
        
        self.edit_clicked.emit(index)
    
    def _on_delete(self, index: int):
        """Handle delete button click."""
        self.delete_clicked.emit(index)
        if self.on_delete:
            self.on_delete(index)
    
    def get_prompts(self) -> List[PromptRow]:
        """Get all prompts with synced image data from slots."""
        for row_idx, row in enumerate(self._rows):
            slots = self._image_slots.get(row_idx, [])
            if slots:
                # Sync image_tags from slot widgets (actual current state)
                row.image_tags = [s.tag for s in slots if s.tag]
                # Sync image_path from first filled slot
                for s in slots:
                    if s.image_path:
                        row.image_path = s.image_path
                        break
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
