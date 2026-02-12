"""
VEO Pro Max - Tab 06: Queue Manager - PySide6 Version

Reference: TAB_06_QUEUE_MANAGER.md
Migrated from CustomTkinter to PySide6.
FIXED: All 12 audit issues addressed.
"""

from typing import Optional, List, Dict
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QProgressBar, QComboBox, QLineEdit,
    QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class QueueItem:
    """Data class for a queue item."""
    def __init__(self, id: int, prompt: str, status: str = "pending", 
                 progress: int = 0, mode: str = "T2V", project: str = "Default"):
        self.id = id
        self.prompt = prompt
        self.status = status  # pending, processing, completed, failed
        self.progress = progress
        self.mode = mode  # T2V, I2V, R2V, T2I, I2I
        self.project = project


class TabQueue(QWidget):
    """Queue Manager tab (PySide6).
    
    Layout:
    - Filter bar with working filters
    - Control bar with all buttons connected
    - Hierarchical tree view: Task Group → Prompt Rows
    - Status badges with colors
    - Progress indicators with real-time updates
    """
    
    # Signals
    start_all = Signal()
    pause_all = Signal()
    resume_all = Signal()
    cancel_all = Signal()
    clear_failed = Signal()
    _progress_signal = Signal(str, int, str)  # task_id, progress, status_text (thread-safe)
    _queue_updated_signal = Signal()  # thread-safe queue refresh trigger
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self._queue_items: List[QueueItem] = []
        self._item_widgets: Dict[int, QFrame] = {}  # Track widgets by item ID
        self._task_widgets: Dict[str, QFrame] = {}   # task_id → row widget (for progress updates)
        self._group_widgets: Dict[str, dict] = {}   # group_id → {header, content, items}
        self._group_expanded: Dict[str, bool] = {}   # group_id → expanded state
        self._projects: List[str] = ["All Projects"]  # Dynamic project list
        self._is_processing = False
        self._start_time = None
        
        self._setup_ui()
        self._register_controller_callbacks()
        # Sample data only if no controller
        if not controller:
            self._add_sample_items()
    
    def _register_controller_callbacks(self):
        """Register callbacks with controller for real-time updates."""
        if self.controller:
            self.controller.set_queue_updated_callback(self._on_queue_updated_from_thread)
            if hasattr(self.controller, 'set_progress_callback'):
                self.controller.set_progress_callback(self._on_progress_update_from_thread)
        # Connect signals for thread-safe UI updates
        self._progress_signal.connect(self._on_progress_update)
        self._queue_updated_signal.connect(self._on_queue_updated)
    
    def _on_progress_update_from_thread(self, task_id: str, progress: int, status_text: str = ""):
        """Thread-safe bridge: emit signal from worker thread → main thread."""
        self._progress_signal.emit(task_id, progress, status_text)
    
    def _on_progress_update(self, task_id: str, progress: int, status_text: str = ""):
        """Handle progress update from controller.
        
        Uses _task_widgets dict for O(1) lookup instead of scanning
        nested group containers.
        """
        widget = self._task_widgets.get(task_id)
        if widget and hasattr(widget, 'progress_bar'):
            widget.progress_bar.setValue(progress)
            if status_text:
                widget.progress_bar.setFormat(f"{status_text} {progress}%")
            else:
                widget.progress_bar.setFormat(f"{progress}%")
            # Update status label dynamically
            if hasattr(widget, 'status_label'):
                if progress >= 100:
                    widget.status_label.setText("✅ DONE")
                    widget.status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 10px; font-weight: bold; border: none;")
                elif progress > 0:
                    widget.status_label.setText("🔥 PROCESSING")
                    widget.status_label.setStyleSheet(f"color: {Theme.PEACH}; font-size: 10px; font-weight: bold; border: none;")
    
    def _on_queue_updated_from_thread(self, status: Dict):
        """Thread-safe bridge: emit signal from any thread → main thread."""
        self._queue_updated_signal.emit()
    
    def _on_queue_updated(self):
        """Handle queue update on GUI thread."""
        self._refresh_queue_from_controller()
    
    def _refresh_queue_from_controller(self):
        """Refresh queue from controller using hierarchical group data."""
        if not self.controller:
            return
        
        # Try group-based data first (preferred)
        if hasattr(self.controller, 'get_queue_groups'):
            groups_data = self.controller.get_queue_groups()
            self._refresh_groups(groups_data)
        elif hasattr(self.controller, 'get_queue_items'):
            # Fallback to flat items
            self._refresh_flat_items()
        
        self._update_stats()
        self._apply_filters()
        self._update_button_states()
    
    def _refresh_groups(self, groups_data: list):
        """Refresh hierarchical group → prompt row view."""
        current_group_ids = {g['id'] for g in groups_data}
        
        # Remove stale groups
        stale = [gid for gid in self._group_widgets if gid not in current_group_ids]
        for gid in stale:
            gw = self._group_widgets.pop(gid)
            gw['container'].deleteLater()
        
        # Update or create groups
        self._queue_items.clear()
        self._item_widgets.clear()
        self._task_widgets.clear()
        
        for g in groups_data:
            gid = g['id']
            
            if gid in self._group_widgets:
                # Update existing group
                gw = self._group_widgets[gid]
                self._update_group_header(gw['header'], g)
                # Rebuild children
                self._rebuild_group_children(gw, g)
            else:
                # Create new group
                expanded = self._group_expanded.get(gid, True)
                container = self._create_group_widget(g, expanded)
                self._group_expanded[gid] = expanded
                self.queue_layout.insertWidget(
                    self.queue_layout.count() - 1, container
                )
            
            # Track items for stats
            for td in g.get('tasks', []):
                item = QueueItem(
                    id=td['id'], prompt=td['prompt'],
                    status=td['status'], progress=td['progress'],
                    mode=td.get('mode', 'T2V'),
                )
                self._queue_items.append(item)
    
    def _refresh_flat_items(self):
        """Fallback: refresh using flat item list (no groups)."""
        items_data = self.controller.get_queue_items()
        controller_ids = {d['id'] for d in items_data}
        
        stale_ids = [iid for iid in list(self._item_widgets.keys()) if str(iid) not in controller_ids]
        for iid in stale_ids:
            widget = self._item_widgets.pop(iid, None)
            if widget:
                widget.deleteLater()
        self._queue_items = [i for i in self._queue_items if str(i.id) not in {str(s) for s in stale_ids}]
        
        existing_ids = {str(i.id) for i in self._queue_items}
        for d in items_data:
            tid = d['id']
            if tid in existing_ids:
                for item in self._queue_items:
                    if str(item.id) == tid:
                        changed = (item.status != d['status'] or item.progress != d['progress'])
                        item.status = d['status']
                        item.progress = d['progress']
                        if changed:
                            self._refresh_item_widget(item)
                        break
            else:
                item = QueueItem(
                    id=tid, prompt=d['prompt'],
                    status=d['status'], progress=d['progress'],
                    mode=d.get('mode', 'T2V'),
                    project=d.get('project', 'Default'),
                )
                if item.project not in self._projects:
                    self._projects.append(item.project)
                    self.project_filter.addItem(item.project)
                self._add_queue_item(item)
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Filter bar (per TAB_06_QUEUE_MANAGER.md)
        filter_bar = self._create_filter_bar()
        layout.addWidget(filter_bar)
        
        # Control bar
        control_bar = self._create_control_bar()
        layout.addWidget(control_bar)
        
        # Queue view
        queue_view = self._create_queue_view()
        layout.addWidget(queue_view, stretch=1)
        
        # Stats bar
        stats_bar = self._create_stats_bar()
        layout.addWidget(stats_bar)
    
    def _create_filter_bar(self) -> QWidget:
        """Create filter bar with dropdowns and search."""
        bar = QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet(f"background-color: {Theme.SURFACE1};")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)
        
        # Filter label
        filter_label = QLabel("🔍 Filter:")
        filter_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        layout.addWidget(filter_label)
        
        # Project dropdown
        self.project_filter = QComboBox()
        self.project_filter.setFixedWidth(150)
        self.project_filter.addItems(self._projects)
        self.project_filter.currentTextChanged.connect(self._on_filter_changed)
        layout.addWidget(self.project_filter)
        
        # Status dropdown
        self.status_filter = QComboBox()
        self.status_filter.setFixedWidth(100)
        self.status_filter.addItems(["All Status", "Pending", "Processing", "Completed", "Failed"])
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        layout.addWidget(self.status_filter)
        
        # Mode dropdown
        self.mode_filter = QComboBox()
        self.mode_filter.setFixedWidth(100)
        self.mode_filter.addItems(["All Modes", "T2V", "I2V", "R2V", "T2I", "I2I"])
        self.mode_filter.currentTextChanged.connect(self._on_filter_changed)
        layout.addWidget(self.mode_filter)
        
        layout.addStretch()
        
        # Search input (no separate button - textChanged is enough)
        self.search_input = QLineEdit()
        self.search_input.setFixedWidth(200)
        self.search_input.setPlaceholderText("Search prompts...")
        self.search_input.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.search_input)
        
        return bar
    
    def _on_filter_changed(self, text: str = None):
        """Handle any filter change - apply all filters."""
        self._apply_filters()
    
    def _apply_filters(self):
        """Apply all filters to queue view - ACTUALLY FILTERS NOW."""
        project = self.project_filter.currentText()
        status = self.status_filter.currentText().lower()
        mode = self.mode_filter.currentText()
        search = self.search_input.text().lower()
        
        # Show/hide widgets based on filters
        for item in self._queue_items:
            widget = self._item_widgets.get(item.id)
            if widget is None:
                continue
            
            # Check all filter conditions
            show = True
            
            # Project filter
            if project != "All Projects" and item.project != project:
                show = False
            
            # Status filter
            if status != "all status" and item.status != status:
                show = False
            
            # Mode filter
            if mode != "All Modes" and item.mode != mode:
                show = False
            
            # Search filter
            if search and search not in item.prompt.lower():
                show = False
            
            widget.setVisible(show)
    
    def _create_control_bar(self) -> QWidget:
        """Create control buttons bar."""
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # Start All button
        self.start_btn = QPushButton("▶️ Start All")
        self.start_btn.setStyleSheet(f"background-color: {Theme.GREEN};")
        self.start_btn.clicked.connect(self._on_start_all)
        layout.addWidget(self.start_btn)
        
        # Pause button
        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setStyleSheet(f"background-color: {Theme.YELLOW};")
        self.pause_btn.clicked.connect(self._on_pause_all)
        layout.addWidget(self.pause_btn)
        
        # Resume button - NOW CONNECTED
        self.resume_btn = QPushButton("▶️ Resume")
        self.resume_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
        self.resume_btn.clicked.connect(self._on_resume_all)
        layout.addWidget(self.resume_btn)
        
        layout.addStretch()
        
        # Clear Failed button
        self.clear_btn = QPushButton("🗑️ Clear Failed")
        self.clear_btn.setStyleSheet(f"background-color: {Theme.RED};")
        self.clear_btn.clicked.connect(self._on_clear_failed)
        layout.addWidget(self.clear_btn)
        
        self.cancel_btn = QPushButton("❌ Cancel All")
        self.cancel_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.RED};")
        self.cancel_btn.clicked.connect(self._on_cancel_all)
        layout.addWidget(self.cancel_btn)
        
        return bar
    
    def _create_queue_view(self) -> QWidget:
        """Create queue view with column header + scrollable item list."""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Column header row
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE1};
                border-bottom: 1px solid {Theme.SURFACE2};
            }}
            QLabel {{
                color: {Theme.SUBTEXT0};
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        # Column widths matching item widget
        cols = [
            ("#", 40), ("Mode", 55), ("Prompt", 0), 
            ("Progress", 120), ("Status", 80), ("Actions", 70),
        ]
        for label_text, width in cols:
            lbl = QLabel(label_text)
            if width > 0:
                lbl.setFixedWidth(width)
            else:
                lbl.setMinimumWidth(100)
            header_layout.addWidget(lbl, stretch=(1 if width == 0 else 0))
        
        container_layout.addWidget(header)
        
        # Scrollable item list
        scroll = QScrollArea()
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {Theme.SURFACE0};
                border: none;
            }}
        """)
        scroll.setWidgetResizable(True)
        
        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setContentsMargins(0, 4, 0, 4)
        self.queue_layout.setSpacing(2)
        self.queue_layout.addStretch()
        
        scroll.setWidget(self.queue_container)
        container_layout.addWidget(scroll, stretch=1)
        
        return container
    
    def _create_queue_item_widget(self, item: QueueItem) -> QWidget:
        """Create a queue item card aligned with column headers."""
        # Status-based styling
        status_config = {
            "pending":      {"icon": "⏳", "color": Theme.SUBTEXT0, "bg": Theme.SURFACE1},
            "ready":        {"icon": "⏳", "color": Theme.SUBTEXT0, "bg": Theme.SURFACE1},
            "waiting":      {"icon": "🔗", "color": Theme.YELLOW if hasattr(Theme, 'YELLOW') else Theme.SUBTEXT0, "bg": Theme.SURFACE1},
            "running":      {"icon": "🔄", "color": Theme.BLUE,     "bg": Theme.SURFACE1},
            "waiting_poll": {"icon": "🔄", "color": Theme.BLUE,     "bg": Theme.SURFACE1},
            "completed":    {"icon": "✅", "color": Theme.GREEN,    "bg": Theme.SURFACE1},
            "failed":       {"icon": "❌", "color": Theme.RED,      "bg": Theme.SURFACE1},
            "cancelled":    {"icon": "⛔", "color": Theme.SUBTEXT0, "bg": Theme.SURFACE1},
        }
        cfg = status_config.get(item.status, status_config["pending"])
        
        # Mode icons
        mode_icons = {
            "T2V": "📹", "I2V": "🎬", "R2V": "🧪", 
            "T2I": "🎯", "I2I": "✨",
        }
        mode_icon = mode_icons.get(item.mode, "📹")
        
        widget = QFrame()
        widget.setStyleSheet(f"""
            QFrame {{
                background-color: {cfg['bg']};
                border-bottom: 1px solid {Theme.SURFACE0};
                border-left: 3px solid {cfg['color']};
            }}
            QFrame:hover {{
                background-color: {Theme.SURFACE2};
            }}
        """)
        widget.setFixedHeight(44)
        widget.setProperty("item_id", item.id)
        widget.task_id = str(item.id)  # For progress update lookup
        
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(9, 4, 12, 4)
        layout.setSpacing(8)
        
        # Col 1: Index (#) — 40px
        index_label = QLabel(f"#{item.id}")
        index_label.setFixedWidth(40)
        index_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-weight: bold; font-size: 11px; border: none;")
        layout.addWidget(index_label)
        
        # Col 2: Mode — 55px
        mode_label = QLabel(f"{mode_icon} {item.mode}")
        mode_label.setFixedWidth(55)
        mode_label.setStyleSheet(f"color: {Theme.BLUE}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(mode_label)
        
        # Col 3: Prompt — flex
        prompt_text = item.prompt[:80] + "..." if len(item.prompt) > 80 else item.prompt
        prompt_label = QLabel(prompt_text)
        prompt_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; border: none;")
        prompt_label.setToolTip(item.prompt)
        layout.addWidget(prompt_label, stretch=1)
        
        # Col 4: Progress + Status Text — 180px
        progress = QProgressBar()
        progress.setFixedWidth(180)
        progress.setFixedHeight(16)
        progress.setValue(item.progress)
        progress.setTextVisible(True)
        # Show status_text if available
        status_text = getattr(item, 'status_text', '') or ''
        if status_text and item.progress > 0 and item.progress < 100:
            progress.setFormat(f"{status_text} {item.progress}%")
        else:
            progress.setFormat(f"{item.progress}%")
        progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.SURFACE2};
                border-radius: 4px;
                text-align: center;
                font-size: 10px;
                color: {Theme.TEXT};
            }}
            QProgressBar::chunk {{
                background-color: {cfg['color']};
                border-radius: 3px;
            }}
        """)
        widget.progress_bar = progress  # Store reference for live updates
        layout.addWidget(progress)
        
        # Col 5: Status badge — 80px
        status_label = QLabel(f"{cfg['icon']} {item.status.upper()}")
        status_label.setFixedWidth(80)
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet(f"""
            color: {cfg['color']};
            font-size: 10px;
            font-weight: bold;
            border: none;
        """)
        widget.status_label = status_label  # Store reference for live updates
        layout.addWidget(status_label)
        
        # Col 6: Actions — 70px
        actions_widget = QWidget()
        actions_widget.setFixedWidth(70)
        actions_layout = QHBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(2)
        
        retry_btn = QPushButton("🔄")
        retry_btn.setFixedSize(28, 28)
        retry_btn.setToolTip("Retry this item")
        retry_btn.setStyleSheet("border: none;")
        retry_btn.clicked.connect(lambda checked, _id=item.id: self._on_retry_item(_id))
        actions_layout.addWidget(retry_btn)
        
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setToolTip("Delete this item")
        delete_btn.setStyleSheet("border: none;")
        delete_btn.clicked.connect(lambda checked, _id=item.id: self._on_delete_item(_id))
        actions_layout.addWidget(delete_btn)
        
        layout.addWidget(actions_widget)
        
        return widget
    
    def _create_group_widget(self, group_data: dict, expanded: bool = True) -> QWidget:
        """Create a collapsible group widget with header + child prompt rows."""
        gid = group_data['id']
        mode_icons = {"T2V": "📹", "I2V": "🎬", "R2V": "🧪", "T2I": "🎯", "I2I": "✨"}
        mode_icon = mode_icons.get(group_data.get('mode', 'T2V'), "📹")
        
        # Container for entire group
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # === GROUP HEADER (collapsible toggle) ===
        header = QFrame()
        header.setFixedHeight(40)
        header.setCursor(Qt.PointingHandCursor)
        
        status_color = Theme.BLUE if group_data['status'] == 'running' else (
            Theme.GREEN if group_data['status'] == 'completed' else Theme.SUBTEXT0
        )
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE2};
                border-left: 4px solid {status_color};
                border-bottom: 1px solid {Theme.SURFACE0};
            }}
            QFrame:hover {{
                background-color: {Theme.OVERLAY0 if hasattr(Theme, 'OVERLAY0') else Theme.SURFACE2};
            }}
        """)
        
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 4, 12, 4)
        h_layout.setSpacing(10)
        
        # Expand/collapse indicator
        arrow = QLabel("▼" if expanded else "▶")
        arrow.setFixedWidth(16)
        arrow.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 12px; border: none;")
        h_layout.addWidget(arrow)
        
        # Group name
        name_label = QLabel(f"📁 {group_data['name']}")
        name_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 13px; border: none;")
        h_layout.addWidget(name_label, stretch=1)
        
        # Progress fraction
        completed = group_data.get('completed', 0)
        total = group_data.get('total', 0)
        pct = group_data.get('progress', 0)
        progress_label = QLabel(f"🔄 {completed}/{total} ({pct}%)")
        progress_label.setStyleSheet(f"color: {Theme.BLUE}; font-size: 11px; border: none;")
        h_layout.addWidget(progress_label)
        
        # Mode
        mode_label = QLabel(f"{mode_icon} {group_data.get('mode', 'T2V')}")
        mode_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
        h_layout.addWidget(mode_label)
        
        # Model
        model_raw = group_data.get('model', '')
        model_short = model_raw.replace('veo_3_1_generate', 'Veo 3.1').replace('veo_3_0_generate', 'Veo 3.0').replace('_', ' ') if model_raw else ''
        if model_short:
            model_label = QLabel(model_short)
            model_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
            h_layout.addWidget(model_label)
        
        # Delete group button
        delete_group_btn = QPushButton("🗑️")
        delete_group_btn.setFixedSize(28, 28)
        delete_group_btn.setToolTip("Delete entire group")
        delete_group_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {Theme.RED};
            }}
        """)
        delete_group_btn.clicked.connect(lambda checked, _gid=gid: self._on_delete_group(_gid))
        h_layout.addWidget(delete_group_btn)
        
        container_layout.addWidget(header)
        
        # === CHILD CONTENT (prompt rows) ===
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(1)
        
        for td in group_data.get('tasks', []):
            cont_label = ""
            if td.get('has_continuation'):
                # Find parent index
                cont_label = f"🔗←"
            
            item = QueueItem(
                id=td['id'], prompt=td['prompt'],
                status=td['status'], progress=td['progress'],
                mode=td.get('mode', 'T2V'),
            )
            row = self._create_queue_item_widget(item)
            content_layout.addWidget(row)
            # Register for progress updates
            self._task_widgets[str(td['id'])] = row
        
        content.setVisible(expanded)
        container_layout.addWidget(content)
        
        # Store refs
        self._group_widgets[gid] = {
            'container': container,
            'header': header,
            'content': content,
            'arrow': arrow,
            'name_label': name_label,
            'progress_label': progress_label,
        }
        
        # Click header to toggle
        header.mousePressEvent = lambda e, _gid=gid: self._toggle_group(_gid)
        
        return container
    
    def _update_group_header(self, header: QFrame, group_data: dict):
        """Update group header labels without recreating."""
        gid = group_data['id']
        gw = self._group_widgets.get(gid)
        if not gw:
            return
        
        completed = group_data.get('completed', 0)
        total = group_data.get('total', 0)
        pct = group_data.get('progress', 0)
        gw['progress_label'].setText(f"🔄 {completed}/{total} ({pct}%)")
        gw['name_label'].setText(f"📁 {group_data['name']}")
        
        status_color = Theme.BLUE if group_data['status'] == 'running' else (
            Theme.GREEN if group_data['status'] == 'completed' else Theme.SUBTEXT0
        )
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE2};
                border-left: 4px solid {status_color};
                border-bottom: 1px solid {Theme.SURFACE0};
            }}
            QFrame:hover {{
                background-color: {Theme.OVERLAY0 if hasattr(Theme, 'OVERLAY0') else Theme.SURFACE2};
            }}
        """)
    
    def _rebuild_group_children(self, gw: dict, group_data: dict):
        """Rebuild child prompt rows inside an existing group."""
        content = gw['content']
        layout = content.layout()
        
        # Clear existing children
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Rebuild
        for td in group_data.get('tasks', []):
            item = QueueItem(
                id=td['id'], prompt=td['prompt'],
                status=td['status'], progress=td['progress'],
                mode=td.get('mode', 'T2V'),
            )
            row = self._create_queue_item_widget(item)
            layout.addWidget(row)
            # Register for progress updates
            self._task_widgets[str(td['id'])] = row
    
    def _toggle_group(self, group_id: str):
        """Toggle expand/collapse of a group."""
        gw = self._group_widgets.get(group_id)
        if not gw:
            return
        
        expanded = not self._group_expanded.get(group_id, True)
        self._group_expanded[group_id] = expanded
        
        gw['content'].setVisible(expanded)
        gw['arrow'].setText("▼" if expanded else "▶")
    
    def _create_stats_bar(self) -> QWidget:
        """Create statistics bar at bottom."""
        bar = QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        
        self.stats_label = QLabel("Pending: 0 | Processing: 0 | Completed: 0 | Failed: 0")
        self.stats_label.setStyleSheet(f"color: {Theme.TEXT};")
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        
        self.eta_label = QLabel("ETA: --:--")
        self.eta_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        layout.addWidget(self.eta_label)
        
        return bar
    
    def _add_sample_items(self):
        """Add sample queue items for preview - only when no controller."""
        samples = [
            QueueItem(1, "A sunset scene over mountains with golden light", "completed", 100, "T2V", "Project A"),
            QueueItem(2, "Camera pans across the valley revealing a river", "processing", 45, "I2V", "Project A"),
            QueueItem(3, "Birds flying in formation against the orange sky", "pending", 0, "R2V", "Project B"),
            QueueItem(4, "A failed generation attempt", "failed", 0, "T2I", "Project B"),
        ]
        
        # Update project filter with sample projects
        for item in samples:
            if item.project not in self._projects:
                self._projects.append(item.project)
                self.project_filter.addItem(item.project)
        
        for item in samples:
            self._add_queue_item(item)
        
        self._update_stats()
    
    def _add_queue_item(self, item: QueueItem):
        """Add a queue item to the display."""
        self._queue_items.append(item)
        widget = self._create_queue_item_widget(item)
        self._item_widgets[item.id] = widget
        self.queue_layout.insertWidget(self.queue_layout.count() - 1, widget)
    
    def _update_stats(self):
        """Update statistics bar."""
        pending = sum(1 for i in self._queue_items if i.status in ("pending", "ready", "waiting"))
        processing = sum(1 for i in self._queue_items if i.status in ("running", "waiting_poll"))
        completed = sum(1 for i in self._queue_items if i.status == "completed")
        failed = sum(1 for i in self._queue_items if i.status in ("failed", "cancelled"))
        
        self.stats_label.setText(f"Pending: {pending} | Processing: {processing} | Completed: {completed} | Failed: {failed}")
        
        # Calculate ETA based on processing rate
        self._update_eta(pending, processing)
    
    def _update_eta(self, pending: int, processing: int):
        """Calculate and update ETA."""
        if pending == 0 and processing == 0:
            self.eta_label.setText("ETA: Done!")
        elif processing == 0:
            self.eta_label.setText(f"ETA: {pending} items queued")
        else:
            # ~90 seconds average per VEO generation
            estimated_seconds = (pending + processing) * 90
            if estimated_seconds >= 3600:
                hours = estimated_seconds // 3600
                minutes = (estimated_seconds % 3600) // 60
                self.eta_label.setText(f"ETA: {hours}h {minutes:02d}m")
            else:
                minutes = estimated_seconds // 60
                seconds = estimated_seconds % 60
                self.eta_label.setText(f"ETA: {minutes:02d}:{seconds:02d}")
    
    # Event handlers
    def _on_start_all(self):
        """Start processing all pending tasks."""
        # Bug 1 fix: Don't start engine if queue is empty
        if self.controller and hasattr(self.controller, '_dispatcher'):
            if self.controller._dispatcher.ready_count == 0:
                return  # Nothing to process
        
        self.start_all.emit()
        if self.controller:
            self.controller.start_processing()
        # Bug 6 fix: Sync with controller's actual state
        self._is_processing = self.controller.state.is_processing if self.controller else True
        self._update_button_states()
    
    def _on_pause_all(self):
        """Pause all processing."""
        self.pause_all.emit()
        if self.controller:
            self.controller.stop_processing()
        # Bug 6 fix: Sync with controller's actual state
        self._is_processing = self.controller.state.is_processing if self.controller else False
        self._update_button_states()
    
    def _on_resume_all(self):
        """Resume processing."""
        self.resume_all.emit()
        if self.controller:
            self.controller.start_processing()
        # Bug 6 fix: Sync with controller's actual state
        self._is_processing = self.controller.state.is_processing if self.controller else True
        self._update_button_states()
    
    def _on_cancel_all(self):
        """Cancel all tasks and clear queue."""
        if not self._queue_items:
            return
        
        reply = QMessageBox.question(
            self, "Cancel All",
            f"Are you sure you want to cancel all {len(self._queue_items)} tasks?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self._is_processing = False
        self.cancel_all.emit()
        if self.controller:
            self.controller.stop_processing()
            if hasattr(self.controller, 'clear_all_tasks'):
                self.controller.clear_all_tasks()
        
        self._clear_all_items()
        self._update_stats()
        self._update_button_states()
    
    def _on_clear_failed(self):
        """Clear all failed tasks."""
        failed_ids = [i.id for i in self._queue_items if i.status == "failed"]
        self._queue_items = [i for i in self._queue_items if i.status != "failed"]
        
        for item_id in failed_ids:
            if self.controller and hasattr(self.controller, 'cancel_task'):
                self.controller.cancel_task(str(item_id))
            widget = self._item_widgets.pop(item_id, None)
            if widget:
                widget.deleteLater()
        
        self.clear_failed.emit()
        self._update_stats()
    
    def _on_retry_item(self, item_id):
        """Retry a specific item."""
        if self.controller and hasattr(self.controller, 'retry_task'):
            self.controller.retry_task(str(item_id))
        
        for item in self._queue_items:
            if item.id == item_id:
                item.status = "pending"
                item.progress = 0
                self._refresh_item_widget(item)
                break
        self._update_stats()
    
    def _on_delete_item(self, item_id):
        """Delete a specific item."""
        if self.controller and hasattr(self.controller, 'cancel_task'):
            self.controller.cancel_task(str(item_id))
        
        self._queue_items = [i for i in self._queue_items if i.id != item_id]
        widget = self._item_widgets.pop(item_id, None)
        if widget:
            widget.deleteLater()
        self._update_stats()
    
    def _on_delete_group(self, group_id: str):
        """Delete an entire task group and all its tasks."""
        gw = self._group_widgets.get(group_id)
        if not gw:
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, "Delete Group",
            f"Delete this group and all its tasks?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Cancel all tasks in this group via dispatcher
        if self.controller and hasattr(self.controller, '_dispatcher'):
            dispatcher = self.controller._dispatcher
            group = dispatcher._task_groups.get(group_id)
            if group:
                for task in group.tasks:
                    if hasattr(dispatcher, 'cancel_task'):
                        dispatcher.cancel_task(task.id)
                    # Remove from local queue items
                    self._queue_items = [i for i in self._queue_items if i.id != task.id]
                    widget = self._item_widgets.pop(task.id, None)
                    if widget:
                        widget.deleteLater()
                # Remove the group from dispatcher
                dispatcher._task_groups.pop(group_id, None)
        
        # Remove group widget from UI
        gw['container'].deleteLater()
        self._group_widgets.pop(group_id, None)
        self._group_expanded.pop(group_id, None)
        
        self._update_stats()
        print(f"[Queue] Deleted group: {group_id}")
    
    def _refresh_item_widget(self, item: QueueItem):
        """Refresh a single item widget."""
        old_widget = self._item_widgets.get(item.id)
        if old_widget:
            index = self.queue_layout.indexOf(old_widget)
            old_widget.deleteLater()
            
            new_widget = self._create_queue_item_widget(item)
            self._item_widgets[item.id] = new_widget
            self.queue_layout.insertWidget(index, new_widget)
    
    def _clear_all_items(self):
        """Clear all queue items and widgets."""
        for widget in self._item_widgets.values():
            widget.deleteLater()
        self._item_widgets.clear()
        self._queue_items.clear()
    
    def _update_button_states(self):
        """Update button enabled/disabled states based on processing state."""
        is_processing = self._is_processing
        if self.controller and hasattr(self.controller, 'get_queue_status'):
            status = self.controller.get_queue_status()
            is_processing = status.get('is_processing', self._is_processing)
            self._is_processing = is_processing
        
        self.start_btn.setEnabled(not is_processing)
        self.pause_btn.setEnabled(is_processing)
        self.resume_btn.setEnabled(not is_processing and len(self._queue_items) > 0)
    
    # Public API for external updates
    def add_item(self, prompt: str, mode: str = "T2V", project: str = "Default"):
        """Add a new item to the queue (called from generation tabs)."""
        new_id = max([i.id for i in self._queue_items], default=0) + 1
        item = QueueItem(new_id, prompt, "pending", 0, mode, project)
        
        # Update project filter if new project
        if project not in self._projects:
            self._projects.append(project)
            self.project_filter.addItem(project)
        
        self._add_queue_item(item)
        self._update_stats()
    
    def update_item_status(self, item_id: int, status: str, progress: int = 0):
        """Update status of a specific item."""
        for item in self._queue_items:
            if item.id == item_id:
                item.status = status
                item.progress = progress
                self._refresh_item_widget(item)
                break
        self._update_stats()
