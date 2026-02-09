"""
VEO Pro Max - Queue Project Group Component (PySide6)

Reference: TAB_06_QUEUE_MANAGER.md Lines 91-114
Collapsible project header with child prompt rows.
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class QueueStatus(Enum):
    """Status of a queue item."""
    PENDING = "pending"
    PROCESSING = "processing"
    UPSCALING = "upscaling"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    EDITED = "edited"


class GenerationMode(Enum):
    """Generation mode types."""
    T2V = "📹"
    I2V = "🎬"
    R2V = "✏️"
    T2I = "🎯"
    I2I = "✨"


@dataclass
class QueuePrompt:
    """Single prompt in queue."""
    index: int
    mode: GenerationMode
    prompt_text: str
    status: QueueStatus = QueueStatus.PENDING
    progress: int = 0
    error_type: Optional[str] = None
    start_image: Optional[str] = None
    end_image: Optional[str] = None
    continuation_from: Optional[int] = None
    outputs: List[str] = None
    
    def __post_init__(self):
        if self.outputs is None:
            self.outputs = []
    
    @property
    def status_display(self) -> str:
        if self.status == QueueStatus.PENDING:
            return "⏳ Queue"
        elif self.status == QueueStatus.PROCESSING:
            return f"🔄 {self.progress}% Generating"
        elif self.status == QueueStatus.UPSCALING:
            return f"📈 {self.progress}% Upscaling"
        elif self.status == QueueStatus.DOWNLOADING:
            return f"⬇️ {self.progress}% Downloading"
        elif self.status == QueueStatus.COMPLETED:
            return "✅ Done"
        elif self.status == QueueStatus.FAILED:
            return f"❌ {self.error_type or 'Error'}"
        elif self.status == QueueStatus.EDITED:
            return "✏️ Edited"
        return "⚪ Unknown"
    
    @property
    def link_display(self) -> str:
        if self.continuation_from:
            return f"🔗←#{self.continuation_from}"
        return "⚪ None"


@dataclass
class QueueProject:
    """Project group in queue."""
    name: str
    mode: GenerationMode
    model: str = "Veo 3.1"
    quality: str = "1080p"
    output_path: str = ""
    prompts: List[QueuePrompt] = None
    
    def __post_init__(self):
        if self.prompts is None:
            self.prompts = []
    
    @property
    def total(self) -> int:
        return len(self.prompts)
    
    @property
    def completed(self) -> int:
        return sum(1 for p in self.prompts if p.status == QueueStatus.COMPLETED)
    
    @property
    def failed(self) -> int:
        return sum(1 for p in self.prompts if p.status == QueueStatus.FAILED)
    
    @property
    def progress_percent(self) -> int:
        if self.total == 0:
            return 0
        return int(self.completed / self.total * 100)
    
    @property
    def progress_display(self) -> str:
        if self.failed > 0:
            return f"❌ FAILED ({self.failed}/{self.total})"
        if self.completed == self.total:
            return f"✅ {self.completed}/{self.total} (100%)"
        return f"🔄 {self.completed}/{self.total} ({self.progress_percent}%)"


class QueueProjectGroup(QWidget):
    """Collapsible project group widget (PySide6).
    
    Layout:
    ╔════════════════════════════════════════════════════════════════╗
    ║ ▼/▶ 📁 Project Name  │  Progress  │  Mode  │  Actions        ║
    ╠════════════════════════════════════════════════════════════════╣
    ║ (child prompt rows when expanded)                              ║
    ╚════════════════════════════════════════════════════════════════╝
    """
    
    HEADER_HEIGHT = 50
    
    # Signals
    start_clicked = Signal(QueueProject)
    pause_clicked = Signal(QueueProject)
    delete_clicked = Signal(QueueProject)
    retry_all_clicked = Signal(QueueProject)
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        project: Optional[QueueProject] = None,
        on_start: Optional[Callable] = None,
        on_pause: Optional[Callable] = None,
        on_delete: Optional[Callable] = None,
        on_retry_all: Optional[Callable] = None,
    ):
        super().__init__(parent)
        
        self.project = project or QueueProject(name="Untitled", mode=GenerationMode.T2V)
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_delete = on_delete
        self.on_retry_all = on_retry_all
        
        self._expanded = True
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        self._create_header()
        layout.addWidget(self.header)
        
        # Prompts table
        self._create_prompts_table()
        layout.addWidget(self.prompts_table)
    
    def _create_header(self):
        """Create collapsible header."""
        self.header = QFrame()
        self.header.setFixedHeight(self.HEADER_HEIGHT)
        self.header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(8, 0, 8, 0)
        
        # Left side
        left_layout = QHBoxLayout()
        left_layout.setSpacing(8)
        
        # Toggle button
        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setFixedSize(24, 24)
        self.toggle_btn.setProperty("variant", "secondary")
        self.toggle_btn.clicked.connect(self._toggle)
        left_layout.addWidget(self.toggle_btn)
        
        # Project name
        self.name_label = QLabel(f"📁 {self.project.name} ({self.project.total} prompts)")
        self.name_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        left_layout.addWidget(self.name_label)
        
        # Progress
        self.progress_label = QLabel(self.project.progress_display)
        progress_color = Theme.GREEN if self.project.completed == self.project.total else Theme.SUBTEXT0
        self.progress_label.setStyleSheet(f"color: {progress_color};")
        left_layout.addWidget(self.progress_label)
        
        # Mode
        mode_label = QLabel(f"Mode: {self.project.mode.value}")
        mode_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        left_layout.addWidget(mode_label)
        
        # Model
        model_label = QLabel(f"Model: {self.project.model}")
        model_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        left_layout.addWidget(model_label)
        
        left_layout.addStretch()
        header_layout.addLayout(left_layout)
        
        # Right side - Action buttons
        right_layout = QHBoxLayout()
        right_layout.setSpacing(4)
        
        # Start button
        start_btn = QPushButton("▶️ Start")
        start_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.GREEN};
                color: {Theme.CRUST};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        start_btn.clicked.connect(self._on_start)
        right_layout.addWidget(start_btn)
        
        # Pause button
        pause_btn = QPushButton("⏸️")
        pause_btn.setFixedWidth(36)
        pause_btn.setStyleSheet(f"background-color: {Theme.YELLOW};")
        pause_btn.clicked.connect(self._on_pause)
        right_layout.addWidget(pause_btn)
        
        # Delete button
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedWidth(36)
        delete_btn.setStyleSheet(f"background-color: {Theme.RED};")
        delete_btn.clicked.connect(self._on_delete)
        right_layout.addWidget(delete_btn)
        
        # Retry All (only if failed)
        if self.project.failed > 0:
            retry_btn = QPushButton("🔄 Retry All")
            retry_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
            retry_btn.clicked.connect(self._on_retry_all)
            right_layout.addWidget(retry_btn)
        
        header_layout.addLayout(right_layout)
    
    def _create_prompts_table(self):
        """Create prompts table."""
        self.prompts_table = QTableWidget()
        self.prompts_table.setColumnCount(8)
        self.prompts_table.setHorizontalHeaderLabels([
            "#", "Mode", "Images", "Prompt", "Link", "Videos", "Status", "Actions"
        ])
        
        # Style
        self.prompts_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Theme.BASE};
                gridline-color: {Theme.SURFACE1};
                border: none;
            }}
        """)
        
        # Configure headers
        header = self.prompts_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        
        self.prompts_table.setColumnWidth(0, 40)
        self.prompts_table.setColumnWidth(1, 50)
        self.prompts_table.setColumnWidth(2, 100)
        self.prompts_table.setColumnWidth(4, 80)
        self.prompts_table.setColumnWidth(5, 100)
        self.prompts_table.setColumnWidth(6, 120)
        self.prompts_table.setColumnWidth(7, 80)
        
        # Selection
        self.prompts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.prompts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Populate
        self._refresh_prompts()
    
    def _refresh_prompts(self):
        """Refresh prompts table."""
        self.prompts_table.setRowCount(0)
        
        for prompt in self.project.prompts:
            row_idx = self.prompts_table.rowCount()
            self.prompts_table.insertRow(row_idx)
            self.prompts_table.setRowHeight(row_idx, 32)
            
            # Index
            self.prompts_table.setItem(row_idx, 0, QTableWidgetItem(str(prompt.index)))
            
            # Mode
            self.prompts_table.setItem(row_idx, 1, QTableWidgetItem(prompt.mode.value))
            
            # Images
            images_text = self._get_images_display(prompt)
            self.prompts_table.setItem(row_idx, 2, QTableWidgetItem(images_text))
            
            # Prompt
            prompt_text = prompt.prompt_text[:40] + "..." if len(prompt.prompt_text) > 40 else prompt.prompt_text
            self.prompts_table.setItem(row_idx, 3, QTableWidgetItem(prompt_text))
            
            # Link
            link_item = QTableWidgetItem(prompt.link_display)
            link_color = Theme.BLUE if prompt.continuation_from else Theme.SUBTEXT1
            link_item.setForeground(QColor(link_color))
            self.prompts_table.setItem(row_idx, 4, link_item)
            
            # Videos placeholder
            self.prompts_table.setItem(row_idx, 5, QTableWidgetItem("▶️" * min(len(prompt.outputs), 4)))
            
            # Status
            status_item = QTableWidgetItem(prompt.status_display)
            status_item.setForeground(QColor(self._get_status_color(prompt.status)))
            self.prompts_table.setItem(row_idx, 6, status_item)
            
            # Actions - create widget
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(2)
            
            edit_btn = QPushButton("📝")
            edit_btn.setFixedSize(24, 24)
            actions_layout.addWidget(edit_btn)
            
            if prompt.status in [QueueStatus.FAILED, QueueStatus.EDITED]:
                retry_btn = QPushButton("🔄")
                retry_btn.setFixedSize(24, 24)
                actions_layout.addWidget(retry_btn)
            
            self.prompts_table.setCellWidget(row_idx, 7, actions_widget)
    
    def _get_images_display(self, prompt: QueuePrompt) -> str:
        """Get image display based on mode."""
        mode = prompt.mode
        if mode == GenerationMode.T2V:
            return ""
        elif mode == GenerationMode.I2V:
            if prompt.continuation_from:
                return f"[🔗←#{prompt.continuation_from}]"
            parts = []
            if prompt.start_image:
                parts.append("[START]")
            if prompt.end_image:
                parts.append("[END]")
            return " ".join(parts) or "[➕]"
        elif mode == GenerationMode.R2V:
            return "[REF1][REF2][REF3]"
        elif mode == GenerationMode.T2I:
            return "(N/A)"
        elif mode == GenerationMode.I2I:
            return "[SOURCE]"
        return ""
    
    def _get_status_color(self, status: QueueStatus) -> str:
        """Get color for status."""
        colors = {
            QueueStatus.PENDING: Theme.SUBTEXT1,
            QueueStatus.PROCESSING: Theme.YELLOW,
            QueueStatus.UPSCALING: Theme.BLUE,
            QueueStatus.DOWNLOADING: Theme.BLUE,
            QueueStatus.COMPLETED: Theme.GREEN,
            QueueStatus.FAILED: Theme.RED,
            QueueStatus.EDITED: Theme.PURPLE,
        }
        return colors.get(status, Theme.SUBTEXT1)
    
    def _toggle(self):
        """Toggle expand/collapse."""
        self._expanded = not self._expanded
        self.toggle_btn.setText("▼" if self._expanded else "▶")
        self.prompts_table.setVisible(self._expanded)
    
    def _on_start(self):
        self.start_clicked.emit(self.project)
        if self.on_start:
            self.on_start(self.project)
    
    def _on_pause(self):
        self.pause_clicked.emit(self.project)
        if self.on_pause:
            self.on_pause(self.project)
    
    def _on_delete(self):
        self.delete_clicked.emit(self.project)
        if self.on_delete:
            self.on_delete(self.project)
    
    def _on_retry_all(self):
        self.retry_all_clicked.emit(self.project)
        if self.on_retry_all:
            self.on_retry_all(self.project)
    
    def update_project(self, project: QueueProject):
        """Update project data and refresh display."""
        self.project = project
        self.name_label.setText(f"📁 {project.name} ({project.total} prompts)")
        self.progress_label.setText(project.progress_display)
        self._refresh_prompts()
