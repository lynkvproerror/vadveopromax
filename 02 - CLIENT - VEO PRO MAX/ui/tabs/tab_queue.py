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
    QMessageBox, QMenu
)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QPixmap, QCursor

try:
    from PySide6.QtGui import QDesktopServices
except ImportError:
    QDesktopServices = None

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
    stop_all = Signal()
    retry_failed = Signal()
    reset_all = Signal()
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
        self._is_paused = False
        self._start_time = None
        self._retry_pending = []  # Staggered retry queue
        
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
        """Handle progress update — update inline thumbnail slot gradients."""
        widget = self._task_widgets.get(task_id)
        if not widget:
            return
        
        # Update thumbnail slot gradients during generating phase
        if hasattr(widget, 'thumb_slots'):
            pct = max(0, min(100, progress)) / 100.0
            for slot in widget.thumb_slots:
                try:
                    # Only update slots that don't have a thumbnail yet
                    if slot.pixmap() and not slot.pixmap().isNull():
                        continue  # Already has thumbnail, skip
                    slot.setText(f"{progress}%")
                    slot.setStyleSheet(f"""
                        QLabel {{
                            background-color: qlineargradient(
                                x1:0, y1:1, x2:0, y2:0,
                                stop:0 #1E3A5E,
                                stop:{pct:.2f} {Theme.BLUE},
                                stop:{min(pct + 0.01, 1.0):.2f} {Theme.SURFACE0},
                                stop:1 {Theme.SURFACE0}
                            );
                            border: 1px solid {Theme.BLUE};
                            border-radius: 4px;
                            color: {Theme.TEXT};
                            font-size: 10px;
                            font-weight: bold;
                        }}
                    """)
                except RuntimeError:
                    continue  # C++ QLabel already deleted, skip
        
        # Update status label with granular phase from engine
        if hasattr(widget, 'status_label'):
            try:
                if progress >= 100:
                    widget.status_label.setText("✅ DONE")
                    widget.status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 10px; font-weight: bold; border: none;")
                elif progress > 0:
                    # Use engine's status_text for granular phases
                    display_text = status_text if status_text else "🔥 PROCESSING"
                    widget.status_label.setText(display_text)
                    # Color by phase
                    if "⬇️" in display_text or "Download" in display_text:
                        phase_color = Theme.SAPPHIRE
                    elif "⬆️" in display_text or "Upscal" in display_text:
                        phase_color = Theme.PURPLE
                    elif "✅" in display_text:
                        phase_color = Theme.GREEN
                    else:
                        phase_color = Theme.PEACH
                    widget.status_label.setStyleSheet(f"color: {phase_color}; font-size: 10px; font-weight: bold; border: none;")
            except RuntimeError:
                pass  # C++ QLabel already deleted (group removed mid-update)
    
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
        self.status_filter.addItems(["All Status", "Pending", "Processing", "Completed", "Failed", "Cancelled"])
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
        """Apply all filters to queue view.
        
        Uses _task_widgets (populated by grouped refresh) for visibility control.
        Status mapping: 'Processing' matches running/waiting_poll/ready states.
        """
        project = self.project_filter.currentText()
        status = self.status_filter.currentText().lower()
        mode = self.mode_filter.currentText()
        search = self.search_input.text().lower()
        
        # Map UI status labels to internal task states
        status_groups = {
            "pending": {"pending", "waiting"},
            "processing": {"running", "waiting_poll", "ready"},
            "completed": {"completed"},
            "failed": {"failed"},
            "cancelled": {"cancelled"},
        }
        allowed_statuses = status_groups.get(status)  # None = all status
        
        # Show/hide widgets based on filters
        for item in self._queue_items:
            # Try _task_widgets first (grouped view), fall back to _item_widgets
            widget = self._task_widgets.get(str(item.id)) or self._item_widgets.get(item.id)
            if widget is None:
                continue
            
            # Check all filter conditions
            show = True
            
            # Project filter
            if project != "All Projects" and getattr(item, 'project', '') != project:
                show = False
            
            # Status filter (using status groups for correct matching)
            if allowed_statuses is not None and item.status not in allowed_statuses:
                show = False
            
            # Mode filter
            if mode != "All Modes" and item.mode != mode:
                show = False
            
            # Search filter
            if search and search not in item.prompt.lower():
                show = False
            
            widget.setVisible(show)
    
    def _create_control_bar(self) -> QWidget:
        """Create control buttons bar.
        
        Two primary buttons:
        - Toggle: Start → Pause → Resume (cycles based on state)
        - Stop: always available when running/paused
        """
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # Toggle button — Start / Pause / Resume (state-driven)
        self.toggle_btn = QPushButton("▶ Start All")
        self.toggle_btn.setStyleSheet(f"background-color: {Theme.GREEN};")
        self.toggle_btn.clicked.connect(self._on_toggle_engine)
        layout.addWidget(self.toggle_btn)
        
        # Stop button — always separate
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setStyleSheet(f"background-color: {Theme.RED};")
        self.stop_btn.setToolTip("Stop all processing immediately")
        self.stop_btn.clicked.connect(self._on_stop_all)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)
        
        layout.addStretch()
        
        # Retry Failed button — retry all failed prompts
        self.retry_failed_btn = QPushButton("↻ Retry Failed")
        self.retry_failed_btn.setStyleSheet(f"background-color: {Theme.PEACH};")
        self.retry_failed_btn.setToolTip("Retry all failed prompts")
        self.retry_failed_btn.clicked.connect(self._on_retry_failed)
        layout.addWidget(self.retry_failed_btn)
        
        # Reset All — clear entire queue
        self.reset_btn = QPushButton("⟲ Reset All")
        self.reset_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.YELLOW};")
        self.reset_btn.setToolTip("Clear entire queue and start fresh")
        self.reset_btn.clicked.connect(self._on_reset_all)
        layout.addWidget(self.reset_btn)
        
        # Delete All — delete all groups
        self.delete_all_btn = QPushButton("🗑 Delete All")
        self.delete_all_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.RED};")
        self.delete_all_btn.setToolTip("Delete all groups and tasks from queue")
        self.delete_all_btn.clicked.connect(self._on_delete_all)
        layout.addWidget(self.delete_all_btn)
        
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
        header_layout.setContentsMargins(9, 0, 12, 0)
        header_layout.setSpacing(8)
        
        # Column widths matching item widget
        # Only Prompt stretches; Progress/thumbnails use fixed width
        cols = [
            # (label, width, stretch, align_center)
            ("#", 40, 0, False), ("Mode", 55, 0, False),
            ("Images", 120, 0, False),
            ("Prompt", 0, 1, False), 
            ("Progress", 180, 0, True), ("Status", 90, 0, True),
            ("Actions", 68, 0, True),
        ]
        for label_text, width, stretch, center in cols:
            lbl = QLabel(label_text)
            if width > 0:
                lbl.setFixedWidth(width)
            if center:
                lbl.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(lbl, stretch=stretch)
        
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
    
    def _create_queue_item_widget(self, item: QueueItem, task_data: dict = None) -> QWidget:
        """Create a queue item card with inline thumbnail slots."""
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
        widget.setFixedHeight(60)
        widget.setProperty("item_id", item.id)
        widget.task_id = str(item.id)
        
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(9, 4, 12, 4)
        layout.setSpacing(8)
        
        # Col 1: Index (#) — 40px
        prompt_idx = task_data.get('index', '?') if task_data else '?'
        index_label = QLabel(f"#{prompt_idx}")
        index_label.setFixedWidth(40)
        index_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-weight: bold; font-size: 11px; border: none;")
        layout.addWidget(index_label)
        
        # Col 2: Mode — 55px
        mode_label = QLabel(f"{mode_icon} {item.mode}")
        mode_label.setFixedWidth(55)
        mode_label.setStyleSheet(f"color: {Theme.BLUE}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(mode_label)
        
        # Col 3: Input Images — 120px
        input_thumbs = self._create_input_thumbs(item.mode, task_data)
        layout.addWidget(input_thumbs)
        
        # Col 4: Prompt — flex
        prompt_text = item.prompt[:60] + "..." if len(item.prompt) > 60 else item.prompt
        prompt_label = QLabel(prompt_text)
        prompt_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; border: none;")
        prompt_label.setToolTip(item.prompt)
        layout.addWidget(prompt_label, stretch=1)
        
        # Col 4: Thumbnail Slots (replaces QProgressBar)
        output_count = task_data.get('output_count', 4) if task_data else 4
        thumbnails = task_data.get('thumbnails', []) if task_data else []
        output_files = task_data.get('output_files', []) if task_data else []
        
        thumb_container = QWidget()
        thumb_container.setStyleSheet("border: none; background: transparent;")
        thumb_layout = QHBoxLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(4)
        
        # Video output info for per-video status (border color, click-to-play)
        video_outputs = task_data.get('video_outputs', []) if task_data else []
        
        thumb_slots = []
        for vi in range(output_count):
            vi_info = video_outputs[vi] if vi < len(video_outputs) else None
            # Best file: prefer upscale, fallback to 720p, fallback to output_files
            if vi_info:
                video_path = vi_info.get('best_file') or (
                    output_files[vi] if vi < len(output_files) else None
                )
            else:
                video_path = output_files[vi] if vi < len(output_files) else None
            slot = self._create_thumb_slot(
                vi, item.status, item.progress,
                thumbnails[vi] if vi < len(thumbnails) else None,
                video_path,
                video_info=vi_info
            )
            thumb_layout.addWidget(slot)
            thumb_slots.append(slot)
        
        # Fixed width — no stretch, just enough for thumbnails
        thumb_width = output_count * 44  # 40px slot + 4px spacing
        thumb_container.setFixedWidth(thumb_width)
        widget.thumb_slots = thumb_slots
        widget.thumb_container = thumb_container
        
        # Center thumbnails within 180px Progress column
        progress_wrapper = QWidget()
        progress_wrapper.setStyleSheet("border: none; background: transparent;")
        progress_wrapper.setFixedWidth(180)
        pw_layout = QHBoxLayout(progress_wrapper)
        pw_layout.setContentsMargins(0, 0, 0, 0)
        pw_layout.setSpacing(0)
        pw_layout.addStretch()
        pw_layout.addWidget(thumb_container)
        pw_layout.addStretch()
        layout.addWidget(progress_wrapper)
        
        # Col 5: Status badge — 90px
        # Check if this is an upscale-failed task (completed but upscale failed)
        upscale_status = task_data.get('upscale_status', '') if task_data else ''
        
        if item.status == "completed" and upscale_status == "failed":
            # Status label showing per-video fail count (re-upscale via right-click menu)
            video_outputs = task_data.get('video_outputs', []) if task_data else []
            failed_count = sum(1 for vo in video_outputs if vo.get('upscale_status') == 'failed')
            total_count = len(video_outputs) or 1
            download_quality = task_data.get('download_quality', '?') if task_data else '?'
            
            if total_count <= 1:
                status_text = "⚠️ UP FAIL"
            else:
                status_text = f"⚠️ {failed_count}/{total_count} FAIL"
            
            status_label = QLabel(status_text)
            status_label.setFixedWidth(90)
            status_label.setAlignment(Qt.AlignCenter)
            
            # Tooltip with per-video error details
            fail_details = []
            for vo in video_outputs:
                if vo.get('upscale_status') == 'failed':
                    fail_details.append(f"Video {vo.get('index', 0)+1}: {vo.get('upscale_error', '?')}")
            tooltip = "\n".join(fail_details) if fail_details else f"Upscale {download_quality} failed"
            tooltip += "\nRight-click → Re-Upscale"
            status_label.setToolTip(tooltip)
            
            status_label.setStyleSheet(f"""
                color: {Theme.YELLOW};
                font-size: 10px;
                font-weight: bold;
                border: none;
            """)
            widget.status_label = status_label
            layout.addWidget(status_label)
        else:
            # Normal status label
            status_label = QLabel(f"{cfg['icon']} {item.status.upper()}")
            status_label.setFixedWidth(90)
            status_label.setAlignment(Qt.AlignCenter)
            status_label.setStyleSheet(f"""
                color: {cfg['color']};
                font-size: 10px;
                font-weight: bold;
                border: none;
            """)
            widget.status_label = status_label
            layout.addWidget(status_label)
        
        # Col 6-7: Action buttons — 2 fixed-width columns for alignment
        # Override global QSS (which sets all QPushButton to blue bg)
        _DELETE_BTN_STYLE = f"""
            QPushButton {{
                background: transparent;
                color: {Theme.SUBTEXT0};
                border: 1px solid {Theme.SURFACE2};
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {Theme.RED};
                border-color: {Theme.RED};
                color: {Theme.CRUST};
            }}
        """
        _RETRY_BTN_STYLE = f"""
            QPushButton {{
                background: transparent;
                color: {Theme.GREEN};
                border: 1px solid {Theme.GREEN};
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {Theme.GREEN};
                color: {Theme.CRUST};
            }}
        """
        
        # Action buttons wrapper — center within 68px Actions column
        actions_wrapper = QWidget()
        actions_wrapper.setStyleSheet("border: none; background: transparent;")
        actions_wrapper.setFixedWidth(68)
        aw_layout = QHBoxLayout(actions_wrapper)
        aw_layout.setContentsMargins(0, 0, 0, 0)
        aw_layout.setSpacing(4)
        aw_layout.addStretch()
        
        # Retry button — \u27f3 green (only for failed/cancelled)
        retry_btn = QPushButton("\u27f3")
        retry_btn.setFixedSize(30, 24)
        retry_btn.setToolTip("Retry this prompt")
        retry_btn.setStyleSheet(_RETRY_BTN_STYLE)
        retry_btn.clicked.connect(lambda checked, _id=item.id: self._on_retry_item(_id))
        if item.status not in ("failed", "cancelled"):
            retry_btn.hide()
        aw_layout.addWidget(retry_btn)
        
        # Delete button — \u2715 red-on-hover (always visible)
        delete_btn = QPushButton("\u2715")
        delete_btn.setFixedSize(30, 24)
        delete_btn.setToolTip("Remove this prompt")
        delete_btn.setStyleSheet(_DELETE_BTN_STYLE)
        delete_btn.clicked.connect(lambda checked, _id=item.id: self._on_delete_item(_id))
        aw_layout.addWidget(delete_btn)
        
        aw_layout.addStretch()
        layout.addWidget(actions_wrapper)
        
        # Right-click context menu for task row
        widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        widget.customContextMenuRequested.connect(
            lambda pos, _id=item.id, w=widget: self._show_task_context_menu(pos, _id, w)
        )
        
        return widget
    
    def _create_input_thumbs(self, mode: str, task_data: dict = None) -> QWidget:
        """Create input image thumbnails widget with workflow-specific labels.
        
        Layout varies by mode:
        - I2V: [Start] or [Start][End]
        - R2V: [Ref 1][Ref 2][Ref 3]
        - I2I: [Img 1][Img 2]...
        - T2V/T2I: "—" (no images)
        - Continuation: [Frame]
        """
        container = QWidget()
        container.setFixedWidth(120)
        container.setStyleSheet("border: none; background: transparent;")
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignLeft)
        
        image_paths = task_data.get('image_paths', []) if task_data else []
        has_continuation = task_data.get('has_continuation', False) if task_data else False
        cont_frame = task_data.get('continuation_frame', '') if task_data else ''
        
        # Determine labels based on workflow mode
        if mode in ("T2V", "T2I") and not image_paths and not cont_frame:
            # No input images
            dash = QLabel("—")
            dash.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
            dash.setAlignment(Qt.AlignCenter)
            lay.addWidget(dash)
            return container
        
        # Build (path, label) pairs
        pairs = []
        is_continuation = task_data.get('has_continuation', False) if task_data else False
        
        if cont_frame:
            pairs.append((cont_frame, "Frame"))
        elif is_continuation and not image_paths:
            # Continuation child but frame not extracted yet → pending indicator
            pairs.append(("", "Frame ⏳"))
        elif mode == "I2V":
            labels = ["Start", "End"]
            for i, p in enumerate(image_paths):
                pairs.append((p, labels[i] if i < len(labels) else f"Img {i+1}"))
        elif mode == "R2V":
            for i, p in enumerate(image_paths):
                pairs.append((p, f"Ref {i+1}"))
        elif mode == "I2I":
            for i, p in enumerate(image_paths):
                pairs.append((p, f"Img {i+1}"))
        else:
            # Fallback for any mode with images
            for i, p in enumerate(image_paths):
                pairs.append((p, f"Img {i+1}"))
        
        if not pairs:
            dash = QLabel("—")
            dash.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
            dash.setAlignment(Qt.AlignCenter)
            lay.addWidget(dash)
            return container
        
        # Render each thumbnail + label
        total_count = len(pairs)
        show_pairs = pairs[:3]  # Max 3 shown
        remaining = total_count - 3  # Extra images beyond 3
        
        for idx, (path, label) in enumerate(show_pairs):
            slot = QWidget()
            slot.setFixedSize(36, 50)
            slot.setStyleSheet("border: none; background: transparent;")
            slot_lay = QVBoxLayout(slot)
            slot_lay.setContentsMargins(0, 0, 0, 0)
            slot_lay.setSpacing(1)
            
            # Thumbnail container (for overlay stacking)
            thumb_container = QWidget()
            thumb_container.setFixedSize(34, 34)
            thumb_container.setStyleSheet("border: none; background: transparent;")
            
            # Thumbnail
            thumb = QLabel(thumb_container)
            thumb.setFixedSize(34, 34)
            thumb.move(0, 0)
            thumb.setAlignment(Qt.AlignCenter)
            
            # Mode-specific border color
            border_colors = {
                "Start": Theme.GREEN, "End": Theme.BLUE,
                "Frame": Theme.YELLOW if hasattr(Theme, 'YELLOW') else Theme.BLUE,
            }
            border_c = border_colors.get(label, Theme.PURPLE if hasattr(Theme, 'PURPLE') else Theme.BLUE)
            
            thumb.setStyleSheet(
                f"border: 2px solid {border_c}; border-radius: 3px;"
                f"background-color: {Theme.SURFACE0};"
            )
            
            # Load thumbnail if path exists
            if path and Path(path).exists():
                pix = QPixmap(path)
                if not pix.isNull():
                    scaled = pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    thumb.setPixmap(scaled)
                else:
                    thumb.setText("?")
                    thumb.setStyleSheet(
                        thumb.styleSheet() + f"color: {Theme.SUBTEXT0}; font-size: 10px;"
                    )
            else:
                thumb.setText("?")
                thumb.setStyleSheet(
                    thumb.styleSheet() + f"color: {Theme.SUBTEXT0}; font-size: 10px;"
                )
            
            thumb.setToolTip(f"{label}: {path}" if path else label)
            
            # "+N" dark overlay on the 3rd thumbnail when extra images exist
            if idx == 2 and remaining > 0:
                overlay = QLabel(thumb_container)
                overlay.setFixedSize(34, 34)
                overlay.move(0, 0)
                overlay.setText(f"+{remaining}")
                overlay.setAlignment(Qt.AlignCenter)
                overlay.setStyleSheet(
                    "background-color: rgba(0, 0, 0, 160);"
                    "color: white;"
                    "font-size: 12px;"
                    "font-weight: bold;"
                    "border-radius: 3px;"
                    "border: none;"
                )
                overlay.raise_()
                # Update tooltip to show total count
                thumb.setToolTip(f"{total_count} images total")
            
            slot_lay.addWidget(thumb_container, alignment=Qt.AlignCenter)
            
            # Label text
            lbl = QLabel(label)
            lbl.setFixedHeight(12)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {border_c}; font-size: 8px; font-weight: bold; border: none;"
            )
            slot_lay.addWidget(lbl)
            
            lay.addWidget(slot)
        
        return container
    
    def _create_thumb_slot(self, index: int, task_status: str, progress: int,
                           thumb_path: str = None, video_path: str = None,
                           video_info: dict = None) -> QLabel:
        """Create a single thumbnail slot with state-based styling.
        
        Border colors (Phase 7 unified system):
        - gray:   pending / no download
        - yellow: 720p downloaded, no upscale
        - blue:   upscaled (1080p/4K)
        - red:    upscale failed (still shows 720p thumbnail)
        """
        slot = QLabel()
        slot.setFixedSize(40, 40)
        slot.setAlignment(Qt.AlignCenter)
        
        has_thumb = thumb_path and Path(thumb_path).exists()
        is_active = task_status in ('running', 'waiting_poll')
        is_failed = task_status in ('failed', 'cancelled')
        is_done = task_status == 'completed'
        
        # Determine border color from video_info (per-video) or fallback
        border_color_name = "gray"  # default
        if video_info:
            border_color_name = video_info.get('border_color', 'gray')
        elif has_thumb and is_done:
            border_color_name = "yellow"  # legacy: has thumb but no video_info
        
        BORDER_COLORS = {
            'gray':   Theme.BORDER,
            'yellow': Theme.YELLOW,
            'blue':   Theme.BLUE,
            'red':    Theme.RED,
        }
        border_color = BORDER_COLORS.get(border_color_name, Theme.BORDER)
        
        if has_thumb:
            # Show thumbnail with per-video border color
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                slot.setPixmap(scaled)
            slot.setStyleSheet(f"""
                QLabel {{
                    border: 2px solid {border_color};
                    border-radius: 4px;
                    background-color: {Theme.BASE};
                    padding: 1px;
                }}
                QLabel:hover {{
                    border-color: {Theme.LAVENDER};
                }}
            """)
            
            # Quality tooltip
            quality = video_info.get('quality', '') if video_info else ''
            if video_path and Path(video_path).exists():
                slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                tooltip = f"▶ {Path(video_path).name}"
                if quality:
                    tooltip += f" ({quality})"
                slot.setToolTip(tooltip)
                slot.mousePressEvent = lambda e, p=video_path: self._open_video(p) if e.button() == Qt.MouseButton.LeftButton else None
            
            # Right-click context menu for ALL thumbnails with video_info
            if video_info:
                slot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                slot.customContextMenuRequested.connect(
                    lambda pos, vi=video_info, s=slot: self._show_video_context_menu(pos, vi, s)
                )
        elif is_failed:
            # ❌ Failed — red border with X
            slot.setText("❌")
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.RED_BG};
                    border: 2px solid {Theme.RED};
                    border-radius: 4px;
                    color: {Theme.RED};
                    font-size: 14px;
                }}
            """)
        elif is_active:
            # 🔄 Generating — gradient progress fill
            pct = max(0, min(100, progress)) / 100.0
            slot.setText(f"{progress}%")
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: qlineargradient(
                        x1:0, y1:1, x2:0, y2:0,
                        stop:0 #1E3A5E,
                        stop:{pct:.2f} {Theme.BLUE},
                        stop:{min(pct + 0.01, 1.0):.2f} {Theme.SURFACE0},
                        stop:1 {Theme.SURFACE0}
                    );
                    border: 1px solid {Theme.BLUE};
                    border-radius: 4px;
                    color: {Theme.TEXT};
                    font-size: 10px;
                    font-weight: bold;
                }}
            """)
        else:
            # ⏳ Pending — dark placeholder
            slot.setText("⏳")
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.SURFACE0};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 4px;
                    color: {Theme.OVERLAY0};
                    font-size: 14px;
                }}
            """)
        
        return slot
    
    def _open_video(self, video_path: str):
        """Open video file in the in-app video player popup."""
        try:
            from ui.popups.video_player import VideoPlayerPopup
            video_name = Path(video_path).stem
            popup = VideoPlayerPopup(
                parent=self,
                video_path=video_path,
                video_title=video_name,
            )
            popup.exec()
        except Exception as e:
            print(f"[Queue] Failed to open video player: {e}")
            # Fallback to OS player
            try:
                if QDesktopServices:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(video_path))
                else:
                    import os
                    os.startfile(video_path)
            except Exception:
                pass
    
    def _update_thumb_slots(self, widget: QFrame, task_data: dict):
        """Update thumbnail slots on an existing row widget during refresh."""
        if not hasattr(widget, 'thumb_slots'):
            return
        
        status = task_data.get('status', 'pending')
        progress = task_data.get('progress', 0)
        thumbnails = task_data.get('thumbnails', [])
        output_files = task_data.get('output_files', [])
        video_outputs = task_data.get('video_outputs', [])
        
        for vi, slot in enumerate(widget.thumb_slots):
            thumb = thumbnails[vi] if vi < len(thumbnails) else None
            vi_info = video_outputs[vi] if vi < len(video_outputs) else None
            if vi_info:
                video = vi_info.get('best_file') or (
                    output_files[vi] if vi < len(output_files) else None
                )
            else:
                video = output_files[vi] if vi < len(output_files) else None
            new_slot = self._create_thumb_slot(
                vi, status, progress, thumb, video, video_info=vi_info
            )
            # Copy styling and content from new slot
            slot.setStyleSheet(new_slot.styleSheet())
            if new_slot.pixmap() and not new_slot.pixmap().isNull():
                slot.setPixmap(new_slot.pixmap())
                slot.setText('')
            else:
                slot.setPixmap(QPixmap())
                slot.setText(new_slot.text())
            slot.setToolTip(new_slot.toolTip())
            if video and Path(video).exists():
                slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                slot.mousePressEvent = lambda e, p=video: self._open_video(p) if e.button() == Qt.MouseButton.LeftButton else None
            # Copy context menu policy for red thumbnails
            slot.setContextMenuPolicy(new_slot.contextMenuPolicy())
            new_slot.deleteLater()
    
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
        
        # Group name — clickable to open output folder
        output_folder = group_data.get('output_folder', '')
        project_name = group_data.get('project_name', '') or group_data.get('name', '')
        if output_folder:
            folder_path = str(Path(output_folder) / project_name) if project_name else output_folder
        else:
            folder_path = ''
        
        # Progress data (needed for name label gradient + progress label)
        completed = group_data.get('completed', 0)
        total = group_data.get('total', 0)
        pct = group_data.get('progress', 0)
        
        name_label = QPushButton(f"📁 {group_data['name']}")
        name_label.setFlat(True)
        name_label.setCursor(Qt.PointingHandCursor)
        name_label.setStyleSheet(self._name_label_style(pct))
        if folder_path:
            name_label.setToolTip(f"📂 Click to open: {folder_path}")
        else:
            name_label.setToolTip("⚠️ No output folder configured")
        name_label.clicked.connect(lambda checked, fp=folder_path: self._open_group_folder(fp))
        h_layout.addWidget(name_label, stretch=1)
        
        # Progress fraction
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
        
        # Setup group button ⚒️ — adjust settings for group
        setup_group_btn = QPushButton("⚒️")
        setup_group_btn.setFixedSize(32, 24)
        setup_group_btn.setToolTip("Setup: change model, aspect ratio, output folder, outputs")
        setup_group_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.BLUE};
                border: 1px solid {Theme.BLUE};
                border-radius: 4px;
                font-size: 12px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: {Theme.BLUE};
                border-color: {Theme.BLUE};
                color: {Theme.CRUST};
            }}
        """)
        setup_group_btn.clicked.connect(lambda checked, _gid=gid, _gd=group_data: self._on_setup_group(_gid, _gd))
        h_layout.addWidget(setup_group_btn)
        
        # Reset group button — reset all tasks in group (delete cache + re-queue)
        reset_group_btn = QPushButton("RST")
        reset_group_btn.setFixedSize(36, 24)
        reset_group_btn.setToolTip("Reset group: delete all downloads & cache, re-queue")
        reset_group_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.YELLOW};
                border: 1px solid {Theme.YELLOW};
                border-radius: 4px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: bold;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: {Theme.YELLOW};
                border-color: {Theme.YELLOW};
                color: {Theme.CRUST};
            }}
        """)
        reset_group_btn.clicked.connect(lambda checked, _gid=gid: self._on_reset_group(_gid))
        h_layout.addWidget(reset_group_btn)
        
        # Delete group button — override global QSS explicitly
        delete_group_btn = QPushButton("DEL")
        delete_group_btn.setFixedSize(36, 24)
        delete_group_btn.setToolTip("Delete entire group")
        delete_group_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Theme.SUBTEXT0};
                border: 1px solid {Theme.SURFACE2};
                border-radius: 4px;
                font-family: 'Segoe UI';
                font-size: 10px;
                font-weight: bold;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: {Theme.RED};
                border-color: {Theme.RED};
                color: {Theme.CRUST};
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
            row = self._create_queue_item_widget(item, task_data=td)
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
            'group_data': group_data,  # Store for Setup dialog
        }
        
        # Click header to toggle — but NOT when clicking on buttons
        def _header_click(event, _gid=gid):
            # If click landed on a QPushButton child, let it handle naturally
            child = header.childAt(event.pos())
            if isinstance(child, QPushButton):
                return  # Let button handle its own click
            self._toggle_group(_gid)
        header.mousePressEvent = _header_click
        
        return container
    
    def _name_label_style(self, pct: int) -> str:
        """Generate name label stylesheet with progress gradient fill."""
        # Use a subtle blue fill from left based on completion %
        fill_color = "rgba(137, 180, 250, 0.25)"  # Theme.BLUE with transparency
        fill_done = "rgba(166, 227, 161, 0.30)"    # Theme.GREEN for 100%
        fill = fill_done if pct >= 100 else fill_color
        return f"""
            QPushButton {{
                color: {Theme.TEXT};
                font-weight: bold;
                font-size: 13px;
                border: none;
                text-align: left;
                padding: 2px 6px;
                border-radius: 4px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {fill},
                    stop:{max(pct / 100.0, 0.001):.3f} {fill},
                    stop:{min(pct / 100.0 + 0.001, 1.0):.3f} transparent,
                    stop:1 transparent);
            }}
            QPushButton:hover {{
                color: {Theme.BLUE};
                text-decoration: underline;
            }}
        """
    
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
        # Update progress gradient fill on name label
        gw['name_label'].setStyleSheet(self._name_label_style(pct))
        
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
            row = self._create_queue_item_widget(item, task_data=td)
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
    def _on_toggle_engine(self):
        """Unified Start/Pause/Resume toggle.
        
        State machine:
          Idle → Start (green) → Running
          Running → Pause (yellow) → Paused
          Paused → Resume (blue) → Running
        """
        if not self._is_processing:
            # Idle → Start
            if self.controller and hasattr(self.controller, '_dispatcher'):
                if self.controller._dispatcher.ready_count == 0:
                    return  # Nothing to process
            self.start_all.emit()
            if self.controller:
                self.controller.start_processing()
            self._is_processing = self.controller.state.is_processing if self.controller else True
            self._is_paused = False
        elif self._is_paused:
            # Paused → Resume
            self.resume_all.emit()
            if self.controller:
                self.controller.resume_processing()
            self._is_paused = False
        else:
            # Running → Pause
            self.pause_all.emit()
            if self.controller:
                self.controller.pause_processing()
            self._is_paused = True
        
        self._update_button_states()
    
    def _on_stop_all(self):
        """Stop all processing immediately."""
        self._is_processing = False
        self._is_paused = False
        self.stop_all.emit()
        if self.controller:
            self.controller.stop_processing()
        self._is_processing = self.controller.state.is_processing if self.controller else False
        self._update_button_states()
    
    def _update_button_states(self):
        """Update toggle button appearance based on engine state."""
        if not self._is_processing:
            # Idle state → show "Start"
            self.toggle_btn.setText("▶ Start All")
            self.toggle_btn.setStyleSheet(f"background-color: {Theme.GREEN};")
            self.stop_btn.setEnabled(False)
        elif self._is_paused:
            # Paused → show "Resume"
            self.toggle_btn.setText("▶ Resume")
            self.toggle_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
            self.stop_btn.setEnabled(True)
        else:
            # Running → show "Pause"
            self.toggle_btn.setText("⏸ Pause")
            self.toggle_btn.setStyleSheet(f"background-color: {Theme.YELLOW};")
            self.stop_btn.setEnabled(True)
    
    def _on_retry_failed(self):
        """Retry ALL failed tasks — staggered 1 per 2s to avoid flooding."""
        failed_items = [i for i in self._queue_items if i.status == "failed"]
        if not failed_items:
            return
        
        self._retry_pending = list(failed_items)
        total = len(self._retry_pending)
        self.retry_failed.emit()
        
        # Show toast
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(f"Retrying {total} failed prompts (1 per 2s)", "info")
        
        self._retry_next()
    
    def _retry_next(self):
        """Retry next item in the staggered queue."""
        if not self._retry_pending:
            self._refresh_queue_from_controller()
            self._update_stats()
            return
        
        item = self._retry_pending.pop(0)
        if self.controller and hasattr(self.controller, 'retry_task'):
            if self.controller.retry_task(str(item.id)):
                item.status = "pending"
                item.progress = 0
                print(f"[Queue] Retried task {item.id} ({len(self._retry_pending)} remaining)")
        
        if self._retry_pending:
            QTimer.singleShot(2000, self._retry_next)
        else:
            # Last one done — refresh UI
            self._refresh_queue_from_controller()
            self._update_stats()
    
    def _on_delete_all(self):
        """Delete ALL groups and tasks from the queue.
        
        Uses controller.clear_queue() which properly:
        - Clears _all_tasks, _task_groups, _ready_queue
        - Deletes session file (prevents stale reload)
        """
        group_count = len(self._group_widgets)
        if group_count == 0:
            return
        
        reply = QMessageBox.question(
            self, "Delete All",
            f"Delete all {group_count} group(s) and their tasks?\n\n"
            f"This will permanently remove everything from the queue\n"
            f"and delete the session file.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Clear via controller → dispatcher.clear_all() + session file
        count = 0
        if self.controller and hasattr(self.controller, 'clear_queue'):
            count = self.controller.clear_queue()
        
        # Clear all UI state
        for gid, gw in list(self._group_widgets.items()):
            gw['container'].deleteLater()
        self._group_widgets.clear()
        self._group_expanded.clear()
        self._task_widgets.clear()
        self._queue_items.clear()
        self._item_widgets.clear()
        
        self._update_stats()
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(
                f"🗑 Deleted all {group_count} group(s), {count} tasks removed", "info"
            )
    
    def _on_reset_all(self):
        """Reset ALL tasks — delete downloaded files, thumbnails, cache. Re-queue."""
        total = len(self._queue_items)
        if total == 0:
            return
        
        reply = QMessageBox.question(
            self, "Reset All",
            f"Reset incomplete/failed prompts?\n\n"
            f"Completed tasks will be PRESERVED.\n"
            f"Only pending, failed, and errored tasks will be reset and re-queued.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Reset via controller → dispatcher (deletes files + resets state)
        count = 0
        if self.controller and hasattr(self.controller, 'reset_all_tasks'):
            count = self.controller.reset_all_tasks()
        
        self.reset_all.emit()
        self._refresh_queue_from_controller()
        self._update_stats()
        print(f"[Queue] Reset {count}/{total} tasks")
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(f"Reset {count} prompts — cache cleared, re-queued", "info")
    
    def _on_reset_item(self, item_id):
        """Reset a single task — delete its downloads/cache, re-queue."""
        if self.controller and hasattr(self.controller, 'reset_task'):
            if self.controller.reset_task(str(item_id)):
                # Update local state
                for item in self._queue_items:
                    if item.id == item_id:
                        item.status = "pending"
                        item.progress = 0
                        self._refresh_item_widget(item)
                        break
                self._update_stats()
                
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Reset prompt #{item_id} — cache cleared", "info")
    
    def _on_retry_item(self, item_id):
        """Retry a specific failed item."""
        if self.controller and hasattr(self.controller, 'retry_task'):
            success = self.controller.retry_task(str(item_id))
            if success:
                # Refresh entire queue UI from controller to reflect new state
                self._refresh_queue_from_controller()
                self._update_stats()
                
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Retrying prompt #{item_id}", "info")
            else:
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Cannot retry prompt #{item_id}", "warning")
    
    def _show_task_context_menu(self, pos, task_id, widget):
        """Show right-click context menu for a task row.
        
        Menu items are context-sensitive based on task state:
        - Force Retry: always available (re-generate from scratch)
        - Re-Upscale Failed: when any video has upscale_status='failed'
        - Re-Upscale All: when task completed with 1080p/4K quality
        - Reset Task: always available (delete cache + re-queue)
        """
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
            }}
            QMenu::item:disabled {{
                color: {Theme.SUBTEXT0};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Theme.SURFACE2};
                margin: 4px 8px;
            }}
        """)
        
        # Fetch LIVE task data from controller
        task_data = None
        if self.controller and hasattr(self.controller, 'get_queue_groups'):
            for group in self.controller.get_queue_groups():
                for td in group.get('tasks', []):
                    if str(td.get('id', '')) == str(task_id):
                        task_data = td
                        break
                if task_data:
                    break
        
        task_status = task_data.get('status', '') if task_data else ''
        upscale_status = task_data.get('upscale_status', '') if task_data else ''
        download_quality = task_data.get('download_quality', '720p') if task_data else '720p'
        video_outputs = task_data.get('video_outputs', []) if task_data else []
        has_upscale_quality = download_quality in ('1080p', '4K')
        
        # Count per-video statuses
        failed_upscale_count = sum(1 for vo in video_outputs if vo.get('upscale_status') == 'failed')
        total_videos = len(video_outputs)
        
        # === 1. Force Retry (always) ===
        force_retry_action = menu.addAction("🔄 Force Retry (re-generate)")
        force_retry_action.triggered.connect(
            lambda: self._on_force_retry_item(task_id)
        )
        
        # === 2. Re-Upscale options (only for completed tasks with 1080p/4K) ===
        if task_status == 'completed' and has_upscale_quality:
            menu.addSeparator()
            
            if failed_upscale_count > 0:
                # Re-upscale only failed videos
                re_up_failed = menu.addAction(
                    f"⬆️ Re-Upscale Failed ({failed_upscale_count}/{total_videos}) → {download_quality}"
                )
                re_up_failed.triggered.connect(
                    lambda: self._on_reupscale_item(task_id)
                )
            
            # Re-upscale ALL videos (regardless of current status)
            re_up_all = menu.addAction(f"⬆️ Re-Upscale All → {download_quality}")
            re_up_all.triggered.connect(
                lambda: self._on_reupscale_item(task_id)
            )
        
        # === 3. Reset Task ===
        menu.addSeparator()
        reset_action = menu.addAction("🗑️ Reset (delete cache + re-queue)")
        reset_action.triggered.connect(
            lambda: self._on_reset_item(task_id)
        )
        
        menu.exec(widget.mapToGlobal(pos))
    
    def _on_force_retry_item(self, item_id):
        """Force retry a task regardless of state (including completed)."""
        if self.controller and hasattr(self.controller, 'force_retry_task'):
            success = self.controller.force_retry_task(str(item_id))
            if success:
                self._refresh_queue_from_controller()
                self._update_stats()
                
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Force retrying prompt #{item_id}", "info")
            else:
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Cannot force retry prompt #{item_id}", "warning")
    
    def _on_delete_item(self, item_id):
        """Delete a specific item."""
        if self.controller and hasattr(self.controller, 'cancel_task'):
            self.controller.cancel_task(str(item_id))
        
        self._queue_items = [i for i in self._queue_items if i.id != item_id]
        widget = self._item_widgets.pop(item_id, None)
        if widget:
            widget.deleteLater()
        self._update_stats()
    
    def _on_reupscale_item(self, item_id):
        """Re-upscale ALL failed videos in a completed task."""
        if self.controller and hasattr(self.controller, 're_upscale_task'):
            self.controller.re_upscale_task(str(item_id))
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast("⬆️ Re-upscaling all failed videos...", "info")
    
    def _show_video_context_menu(self, pos, video_info: dict, parent_widget):
        """Right-click context menu on any thumbnail — state-dependent items.
        
        Border colors → menu items:
        - yellow (720p only): Upscale → target quality
        - blue (upscaled OK): Re-Upscale → target quality
        - red (upscale failed): Re-Upscale → target quality (with error info)
        - gray (pending/no download): info only
        """
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2};
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
            }}
            QMenu::item:disabled {{
                color: {Theme.SUBTEXT0};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Theme.SURFACE2};
                margin: 4px 8px;
            }}
        """)
        
        idx = video_info.get('index', 0)
        border_color = video_info.get('border_color', 'gray')
        quality = video_info.get('quality', '')
        target_quality = video_info.get('target_quality', '1080p')
        upscale_error = video_info.get('upscale_error', '')
        upscale_status = video_info.get('upscale_status', '')
        task_id = video_info.get('task_id', '')
        best_file = video_info.get('best_file', '')
        has_upscale_quality = target_quality in ('1080p', '4K')
        
        # === Info header (disabled) ===
        if border_color == 'red':
            info_text = f"❌ Video {idx + 1}: {upscale_error or 'upscale failed'}"
        elif border_color == 'blue':
            info_text = f"✅ Video {idx + 1}: {quality}"
        elif border_color == 'yellow':
            info_text = f"🟡 Video {idx + 1}: 720p"
        else:
            info_text = f"⏳ Video {idx + 1}: pending"
        info_action = menu.addAction(info_text)
        info_action.setEnabled(False)
        
        menu.addSeparator()
        
        # === Upscale / Re-Upscale ===
        if has_upscale_quality:
            if border_color == 'yellow':
                # 720p only → offer upscale
                up_action = menu.addAction(f"⬆️ Upscale → {target_quality}")
                up_action.triggered.connect(
                    lambda: self._on_reupscale_single_video(task_id, idx)
                )
            elif border_color in ('red', 'blue'):
                # Failed or already upscaled → offer re-upscale
                label = "Re-Upscale" if border_color == 'blue' else "Re-Upscale (retry)"
                re_up_action = menu.addAction(f"⬆️ {label} → {target_quality}")
                re_up_action.triggered.connect(
                    lambda: self._on_reupscale_single_video(task_id, idx)
                )
        
        # === Open in Explorer ===
        if best_file and Path(best_file).exists():
            menu.addSeparator()
            open_action = menu.addAction(f"📂 Open in Explorer")
            open_action.triggered.connect(
                lambda: self._open_file_in_explorer(best_file)
            )
        
        menu.exec(parent_widget.mapToGlobal(pos))
    
    def _on_reupscale_single_video(self, task_id: str, video_index: int):
        """Re-upscale a single video by index."""
        if self.controller and hasattr(self.controller, 're_upscale_single_video'):
            self.controller.re_upscale_single_video(str(task_id), video_index)
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast(f"⬆️ Re-upscaling video {video_index + 1}...", "info")
    
    def _open_file_in_explorer(self, file_path: str):
        """Open file explorer and select the specific file."""
        try:
            import subprocess
            file_path = str(Path(file_path).resolve())
            subprocess.Popen(f'explorer /select,"{file_path}"')
        except Exception as e:
            print(f"[Queue] Failed to open explorer: {e}")
    
    def _open_group_folder(self, folder_path: str):
        """Open the group's output folder in file explorer."""
        if not folder_path:
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast("⚠️ No output folder configured for this group", "warning")
            return
        
        from PySide6.QtCore import QUrl
        folder = Path(folder_path)
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            # Try opening parent folder
            parent = folder.parent
            if parent.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent)))
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"📂 Folder not yet created, opened parent: {parent.name}", "info")
            else:
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"⚠️ Folder does not exist: {folder_path}", "warning")
    
    def _on_setup_group(self, group_id: str, group_data: dict):
        """Show setup dialog to adjust group settings."""
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QLineEdit, QComboBox, QPushButton, QFileDialog
        )
        
        # Fetch LIVE data from controller instead of using stale group_data
        if self.controller and hasattr(self.controller, 'get_queue_groups'):
            for g in self.controller.get_queue_groups():
                if g['id'] == group_id:
                    group_data = g
                    break
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"⚒️ Group Setup — {group_data.get('name', group_id)}")
        dialog.setMinimumWidth(450)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.BASE};
            }}
            QLabel {{
                color: {Theme.TEXT};
                font-size: 12px;
            }}
            QLineEdit, QComboBox {{
                background-color: {Theme.SURFACE0};
                color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2};
                border-radius: 6px;
                padding: 6px 10px;
                min-height: 28px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {Theme.BLUE};
            }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel(f"⚒️ Adjust settings for group: {group_data.get('name', group_id)}")
        title.setStyleSheet(f"color: {Theme.TEXT}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        # --- Model ---
        layout.addWidget(QLabel("🤖 AI Model"))
        model_combo = QComboBox()
        model_combo.addItems([
            "Veo 3.1 - Fast",
            "Veo 3.1 - Fast [LP]",
            "Veo 3.1 - Quality",
            "Veo 2 - Fast",
            "Veo 2 - Quality",
        ])
        # Try to match current model key to display name
        current_model = group_data.get('model', '')
        if current_model:
            m = current_model.lower()
            # Match based on key fragments
            if '3_1' in m or '3.1' in m:
                if 'lp' in m or 'relaxed' in m:
                    match_idx = 1  # Veo 3.1 - Fast [LP]
                elif 'quality' in m:
                    match_idx = 2  # Veo 3.1 - Quality
                else:
                    match_idx = 0  # Veo 3.1 - Fast
            elif '2' in m or '3_0' in m:
                if 'quality' in m:
                    match_idx = 4  # Veo 2 - Quality
                else:
                    match_idx = 3  # Veo 2 - Fast
            else:
                match_idx = 0  # Default
            model_combo.setCurrentIndex(match_idx)
        layout.addWidget(model_combo)
        
        # --- Aspect Ratio ---
        layout.addWidget(QLabel("📐 Aspect Ratio"))
        ar_combo = QComboBox()
        ar_combo.addItems(["16:9 (Landscape)", "9:16 (Portrait)"])
        current_ar = group_data.get('aspect_ratio', '')
        if 'PORTRAIT' in current_ar.upper():
            ar_combo.setCurrentIndex(1)
        layout.addWidget(ar_combo)
        
        # --- Output Folder ---
        layout.addWidget(QLabel("📂 Output Folder"))
        folder_row = QHBoxLayout()
        folder_input = QLineEdit()
        folder_input.setText(group_data.get('output_folder', ''))
        folder_input.setPlaceholderText("D:/Projects/VEO")
        folder_row.addWidget(folder_input)
        
        browse_btn = QPushButton("📂")
        browse_btn.setFixedSize(36, 28)
        browse_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; border-radius: 6px;")
        browse_btn.clicked.connect(
            lambda: folder_input.setText(
                QFileDialog.getExistingDirectory(dialog, "Select Output Folder") or folder_input.text()
            )
        )
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)
        
        # --- Outputs per Prompt ---
        layout.addWidget(QLabel("🎬 Outputs per Prompt"))
        output_combo = QComboBox()
        output_combo.addItems(["1 video", "2 videos", "3 videos", "4 videos"])
        current_count = group_data.get('output_count', 4)
        idx = max(0, min(current_count - 1, 3))
        output_combo.setCurrentIndex(idx)
        layout.addWidget(output_combo)
        
        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE2};
                color: {Theme.TEXT};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.OVERLAY0 if hasattr(Theme, 'OVERLAY0') else Theme.SURFACE2};
            }}
        """)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("✅ Apply")
        apply_btn.setFixedSize(120, 36)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.LAVENDER};
            }}
        """)
        
        def _apply_settings():
            # Resolve model display name to API key
            from config.constants import resolve_model_key, WorkflowType
            model_display_name = model_combo.currentText()
            ar_text = ar_combo.currentText()
            ar_value = "PORTRAIT" if "Portrait" in ar_text else "LANDSCAPE"
            
            # Resolve to API model key
            mode = group_data.get('mode', 'T2V')
            wf = getattr(WorkflowType, mode, WorkflowType.T2V)
            try:
                model_key = resolve_model_key(model_display_name, wf, ar_value, False)
            except Exception:
                model_key = model_display_name
            
            # Map aspect ratio to API format
            ar_api = "VIDEO_ASPECT_RATIO_PORTRAIT" if ar_value == "PORTRAIT" else "VIDEO_ASPECT_RATIO_LANDSCAPE"
            
            settings = {
                'model': model_key,
                'aspect_ratio': ar_api,
                'output_folder': folder_input.text().strip(),
                'output_count': int(output_combo.currentText().split()[0]),
            }
            
            if self.controller and hasattr(self.controller, 'update_group_settings'):
                success = self.controller.update_group_settings(group_id, settings)
                if success:
                    main_window = self.window()
                    if main_window and hasattr(main_window, 'show_toast'):
                        main_window.show_toast(f"✅ Group settings updated", "success")
                    # Refresh queue to show updated info
                    self._refresh_queue_from_controller()
            dialog.accept()
        
        apply_btn.clicked.connect(_apply_settings)
        btn_layout.addWidget(apply_btn)
        
        layout.addLayout(btn_layout)
        
        dialog.exec()
    
    def _on_reset_group(self, group_id: str):
        """Reset all tasks in a group — delete downloads/cache, re-queue."""
        if not self.controller or not hasattr(self.controller, '_dispatcher'):
            return
        
        dispatcher = self.controller._dispatcher
        group = dispatcher._task_groups.get(group_id)
        if not group:
            return
        
        total = len(group.tasks)
        reply = QMessageBox.question(
            self, "Reset Group",
            f"Reset incomplete/failed prompts in this group?\n\n"
            f"Completed tasks will be PRESERVED.\n"
            f"Only pending, failed, and errored tasks will be reset and re-queued.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        count = 0
        for task in group.tasks:
            if hasattr(self.controller, 'reset_task'):
                if self.controller.reset_task(str(task.id)):
                    count += 1
        
        self._refresh_queue_from_controller()
        self._update_stats()
        print(f"[Queue] Reset group {group_id}: {count}/{total} tasks")
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(f"Reset {count} prompts — cache cleared, re-queued", "info")
    
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
