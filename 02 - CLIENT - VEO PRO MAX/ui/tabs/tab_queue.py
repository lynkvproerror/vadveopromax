"""
VEO Pro Max - Tab 06: Queue Manager - PySide6 Version

Reference: TAB_06_QUEUE_MANAGER.md
Migrated from CustomTkinter to PySide6.
FIXED: All 12 audit issues addressed.

Componentized: Animation, Thumbnails, Context Menus, Group Rendering
are in ui/tabs/queue_components/ as mixin classes.
"""

from typing import Optional, List, Dict
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from collections import OrderedDict

from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLineEdit, QComboBox,
)
from ui.popups import show_confirm
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QPixmap, QCursor
from PySide6.QtWidgets import QGraphicsOpacityEffect

try:
    from PySide6.QtGui import QDesktopServices
except ImportError:
    QDesktopServices = None

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from config.i18n import t

# Mixin imports
from ui.tabs.queue_components.animation_engine import QueueAnimationMixin
from ui.tabs.queue_components.thumbnail_system import QueueThumbnailMixin
from ui.tabs.queue_components.context_menu import QueueContextMenuMixin
from ui.tabs.queue_components.group_renderer import QueueGroupMixin


@dataclass
class QueueItem:
    id: int
    prompt: str
    status: str
    progress: int
    mode: str = "T2V"
    project: str = "Default"


class TabQueue(
    QueueAnimationMixin,
    QueueThumbnailMixin,
    QueueContextMenuMixin,
    QueueGroupMixin,
    QWidget,
):
    """Queue manager tab — group-based hierarchical view with per-video tracking."""
    
    # Signals for controller communication
    start_all = Signal()
    pause_all = Signal()
    resume_all = Signal()
    stop_all = Signal()
    reset_all = Signal()
    retry_failed = Signal()
    
    # Thread-safe signals for callbacks
    _progress_signal = Signal(str, int, str)
    _queue_updated_signal = Signal()
    
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
        self._input_pulse_thumbs: List[QLabel] = []  # Thumbnails with pulsing border
        self._input_pulse_phase = False  # Toggle for pulse animation
        self._post_queue_triggered = False  # Guard: prevent double-trigger
        
        # ── Phase 1 Performance Caches ──
        self._pixmap_cache: OrderedDict = OrderedDict()  # path → scaled QPixmap
        self._pixmap_cache_max = 500
        self._file_exists_cache: Dict[str, tuple] = {}    # path → (exists_bool, timestamp)
        self._file_exists_ttl = 10.0  # seconds before re-checking
        self._progress_throttle_timer = QTimer(self)
        self._progress_throttle_timer.setSingleShot(True)
        self._progress_throttle_timer.setInterval(200)  # 200ms debounce
        self._progress_throttle_timer.timeout.connect(self._flush_throttled_refresh)
        self._throttled_refresh_pending = False
        
        # ── Phase 2 Dynamic Effects ──
        # Shimmer wave on generating thumbnails
        self._shimmer_offset = 0.0
        self._shimmer_active_slots: List[QLabel] = []
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(50)  # 20fps shimmer
        self._shimmer_timer.timeout.connect(self._tick_shimmer)
        # Completion glow pulse
        self._glow_slots: Dict[str, dict] = {}  # task_id → {slots, count, phase}
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(200)  # glow phase toggle
        self._glow_timer.timeout.connect(self._tick_glow)
        # Smooth progress tracking
        self._smooth_progress: Dict[str, float] = {}  # task_id → current animated value
        # Phase 3: Upscale spinner
        self._upscale_spinner_slots: List[QLabel] = []  # slots with animated dots
        self._upscale_spinner_phase = 0
        self._upscale_spinner_timer = QTimer(self)
        self._upscale_spinner_timer.setInterval(400)  # dots cycle 400ms
        self._upscale_spinner_timer.timeout.connect(self._tick_upscale_spinner)
        # Auto-refresh timer: periodic full queue refresh while engine is running
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(2000)  # every 2s
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh_tick)
        
        self._setup_ui()
        self._register_controller_callbacks()
        # Load existing queue data on startup (deferred to ensure UI ready)
        if controller:
            QTimer.singleShot(100, self._refresh_queue_from_controller)
        else:
            # Sample data only if no controller
            self._add_sample_items()
    
    def retranslate_ui(self):
        """Hot-reload: update button labels when language changes.
        
        Does NOT rebuild queue view (preserves animations/thumbnails).
        Only updates translatable UI text.
        """
        # Control bar buttons
        if hasattr(self, 'toggle_btn'):
            # Preserve current state text
            if self._is_paused:
                self.toggle_btn.setText(t("queue.resume"))
            elif self._is_processing:
                self.toggle_btn.setText(t("queue.pause"))
            else:
                self.toggle_btn.setText(t("queue.start_all"))
        if hasattr(self, 'stop_btn'):
            self.stop_btn.setText(t("queue.stop"))
        if hasattr(self, 'retry_failed_btn'):
            self.retry_failed_btn.setText(t("queue.retry_failed"))
        if hasattr(self, 'reset_btn'):
            self.reset_btn.setText(t("queue.reset_all"))
        if hasattr(self, 'delete_all_btn'):
            self.delete_all_btn.setText(t("queue.delete_all"))
    
    # ── Controller Callbacks ─────────────────────────────────────
    
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
        """Handle progress update — shimmer + smooth gradient + glow on complete."""
        widget = self._task_widgets.get(task_id)
        if not widget:
            # Check if this is a hidden replacement task — forward to original slot
            self._forward_replacement_progress(task_id, progress, status_text)
            return
        
        # During download/upscale phase: trigger full refresh so thumb overlays update
        is_refresh_phase = status_text and (
            "⬆️" in status_text or "Upscal" in status_text
            or "🔄" in status_text or "📥" in status_text
        )
        if is_refresh_phase:
            if not hasattr(self, '_upscale_refresh_timer'):
                self._upscale_refresh_timer = QTimer(self)  # parent=self to avoid leak
                self._upscale_refresh_timer.setSingleShot(True)
                self._upscale_refresh_timer.timeout.connect(
                    self._refresh_queue_from_controller
                )
            if not self._upscale_refresh_timer.isActive():
                self._upscale_refresh_timer.start(500)
        
        # Phase 2: Smooth progress interpolation
        smooth_pct = self._get_smooth_progress(task_id, progress) / 100.0
        smooth_pct = max(0.0, min(1.0, smooth_pct))
        
        # Update thumbnail slot gradients via unified _apply_thumb_effect
        if hasattr(widget, 'thumb_slots'):
            # Get task status from widget (stored during creation)
            task_status = getattr(widget, '_task_status', 'running')
            for slot in widget.thumb_slots:
                try:
                    self._apply_thumb_effect(slot, progress, task_status)
                except RuntimeError:
                    continue
        
        # Auto-refresh: when progress hits 100%, trigger delayed refresh
        # so thumbnails load from just-generated files without right-click
        if progress >= 100:
            QTimer.singleShot(500, self._refresh_queue_from_controller)
        
        # Update status label
        if hasattr(widget, 'status_label'):
            try:
                if progress >= 100:
                    # Check if any videos are retrying (via thumb_slots metadata)
                    retrying_count = 0
                    if hasattr(widget, 'thumb_slots'):
                        for slot in widget.thumb_slots:
                            vi = getattr(slot, '_video_info', None)
                            if vi and vi.get('quality') == 'retrying':
                                retrying_count += 1
                    if retrying_count > 0:
                        total = len(widget.thumb_slots) if hasattr(widget, 'thumb_slots') else '?'
                        widget.status_label.setText(f"♻️ RETRYING {retrying_count}/{total}")
                        widget.status_label.setStyleSheet(f"color: {Theme.PURPLE}; font-size: 10px; font-weight: bold; border: none;")
                    else:
                        widget.status_label.setText("✅ COMPLETED")
                        widget.status_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 10px; font-weight: bold; border: none;")
                    # Phase 2: Trigger completion glow
                    self._trigger_completion_glow(task_id)
                    # Cleanup smooth progress
                    self._smooth_progress.pop(task_id, None)
                elif progress > 0:
                    display_text = status_text if status_text else "🔥 PROCESSING"
                    widget.status_label.setText(display_text)
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
                pass
    
    def _forward_replacement_progress(self, task_id: str, progress: int, status_text: str = ""):
        """Forward progress from a hidden replacement task to the original task's video slot."""
        if not self.controller or not hasattr(self.controller, 'get_replace_target'):
            return
        
        target = self.controller.get_replace_target(task_id)
        if not target:
            return
        
        orig_task_id, video_index = target
        widget = self._task_widgets.get(orig_task_id)
        if not widget or not hasattr(widget, 'thumb_slots'):
            return
        
        # Update only the specific video slot
        if video_index < len(widget.thumb_slots):
            slot = widget.thumb_slots[video_index]
            try:
                # Store retry progress on slot for _apply_thumb_effect to use
                slot._retry_progress = progress
                # Ensure video_info reflects retrying state so animation_engine
                # enters the retry rendering path (quality=='retrying' check)
                vi = getattr(slot, '_video_info', None)
                if vi and isinstance(vi, dict):
                    vi['quality'] = 'retrying'
                    vi['border_color'] = 'purple'
                elif vi is None:
                    slot._video_info = {'quality': 'retrying', 'border_color': 'purple'}
                slot._border_color_name = 'purple'
                task_status = getattr(widget, '_task_status', 'completed')
                self._apply_thumb_effect(slot, progress, task_status)
            except RuntimeError:
                pass
    
    def _on_queue_updated_from_thread(self, status: Dict):
        """Thread-safe bridge: emit signal from any thread → main thread."""
        self._queue_updated_signal.emit()
    
    def _on_queue_updated(self):
        """Handle queue update on GUI thread — throttled to avoid storms."""
        self._schedule_throttled_refresh()
    
    # ── Throttled Refresh ────────────────────────────────────────
    
    def _schedule_throttled_refresh(self):
        """Debounce queue refresh — merge multiple updates within 200ms window."""
        self._throttled_refresh_pending = True
        if not self._progress_throttle_timer.isActive():
            self._progress_throttle_timer.start()
    
    def _flush_throttled_refresh(self):
        """Execute throttled refresh if pending."""
        if self._throttled_refresh_pending:
            self._throttled_refresh_pending = False
            self._refresh_queue_from_controller()
    
    def _on_auto_refresh_tick(self):
        """Periodic queue refresh while engine is running (every 2s)."""
        # Skip refresh while context menu is open to prevent parent widget deletion
        if getattr(self, '_pause_refresh_for_menu', False):
            return
        self._refresh_queue_from_controller()
        # Auto-stop timer if engine no longer processing AND upscale queue is idle
        if self.controller and hasattr(self.controller, 'state'):
            if not self.controller.state.is_processing:
                self._is_processing = False
                self._is_paused = False
                self._update_button_states()
                
                # Keep timer alive while upscale queue has work
                upscale_active = False
                engine = getattr(self.controller, '_engine', None)
                if engine:
                    uq = getattr(engine, '_upscale_queue', None)
                    if uq:
                        stats = uq.get_stats()
                        upscale_active = (
                            stats.get('pending_jobs', 0) > 0 or
                            stats.get('active_workers', 0) > 0
                        )
                
                if not upscale_active:
                    self._auto_refresh_timer.stop()
        # Check post-queue action every tick (handles upscale-only completion)
        self._check_post_queue_action()
    
    # ── UI Setup ─────────────────────────────────────────────────
    
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
        """Apply all filters to queue view."""
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
        """Create control buttons bar."""
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # Toggle button — Start / Pause / Resume (state-driven)
        self.toggle_btn = QPushButton(t("queue.start_all"))
        self.toggle_btn.setStyleSheet(f"background-color: {Theme.GREEN};")
        self.toggle_btn.clicked.connect(self._on_toggle_engine)
        layout.addWidget(self.toggle_btn)
        
        # Stop button — always separate
        self.stop_btn = QPushButton(t("queue.stop"))
        self.stop_btn.setStyleSheet(f"background-color: {Theme.RED};")
        self.stop_btn.setToolTip("Stop all processing immediately")
        self.stop_btn.clicked.connect(self._on_stop_all)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)
        
        # Post-queue action dropdown — synced with Settings tab
        from config.settings import get_settings as _gs
        _s = _gs()
        _action_map = {"nothing": "🔌 Do Nothing", "shutdown": "⚡ Shutdown", "sleep": "💤 Sleep"}
        saved_action = _action_map.get(getattr(_s, 'post_queue_action', 'nothing'), "🔌 Do Nothing")
        
        self.post_queue_combo = QComboBox()
        self.post_queue_combo.addItems(["🔌 Do Nothing", "⚡ Shutdown", "💤 Sleep"])
        self.post_queue_combo.setCurrentText(saved_action)
        self.post_queue_combo.setFixedWidth(140)
        self.post_queue_combo.setToolTip("Action after all tasks complete")
        self.post_queue_combo.currentIndexChanged.connect(self._post_queue_combo_changed)
        layout.addWidget(self.post_queue_combo)
        
        layout.addStretch()
        
        # Retry Failed button
        self.retry_failed_btn = QPushButton(t("queue.retry_failed"))
        self.retry_failed_btn.setStyleSheet(f"background-color: {Theme.PEACH};")
        self.retry_failed_btn.setToolTip("Retry all failed prompts")
        self.retry_failed_btn.clicked.connect(self._on_retry_failed)
        layout.addWidget(self.retry_failed_btn)

        # Force Retry All button — force re-generate ALL tasks
        self.force_all_btn = QPushButton("Force All")
        self.force_all_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.PEACH};")
        self.force_all_btn.setToolTip("Force retry ALL prompts (re-generate everything)")
        self.force_all_btn.clicked.connect(self._on_force_retry_all)
        layout.addWidget(self.force_all_btn)

        # Reset All
        self.reset_btn = QPushButton(t("queue.reset_all"))
        self.reset_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.YELLOW};")
        self.reset_btn.setToolTip("Clear entire queue and start fresh")
        self.reset_btn.clicked.connect(self._on_reset_all)
        layout.addWidget(self.reset_btn)
        
        # Delete All
        self.delete_all_btn = QPushButton(t("queue.delete_all"))
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
        header.setObjectName("queueColumnHeader")
        header.setFixedHeight(32)
        header.setStyleSheet(f"""
            QFrame#queueColumnHeader {{
                background-color: {Theme.SURFACE1};
                border-bottom: 1px solid {Theme.SURFACE2};
            }}
            QFrame#queueColumnHeader > * {{ border: none; }}
            QFrame#queueColumnHeader QLabel {{
                color: {Theme.SUBTEXT0};
                font-size: 11px;
                font-weight: bold;
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(9, 0, 12, 0)
        header_layout.setSpacing(8)
        
        # Column widths matching item widget
        cols = [
            ("#", 40, 0, False), ("Mode", 55, 0, False),
            ("Images", 120, 0, False),
            ("Prompt", 0, 1, False), 
            ("Progress", 180, 0, True), ("Status", 120, 0, True),
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
        
        self.total_time_label = QLabel("⏱ Total: --:--")
        self.total_time_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        self.total_time_label.setToolTip("Total processing time across all groups")
        layout.addWidget(self.total_time_label)
        
        return bar
    
    # ── Queue Item Widget ────────────────────────────────────────
    
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
        widget.setObjectName("queueItemRow")
        widget.setStyleSheet(f"""
            QFrame#queueItemRow {{
                background-color: {cfg['bg']};
                border-bottom: 1px solid {Theme.SURFACE0};
                border-left: 3px solid {cfg['color']};
            }}
            QFrame#queueItemRow:hover {{
                background-color: {Theme.SURFACE2};
            }}
            QFrame#queueItemRow > * {{ border: none; }}
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
        
        # Col 5: Status badge — 120px
        video_outputs = task_data.get('video_outputs', []) if task_data else []
        upscale_status = task_data.get('upscale_status', '') if task_data else ''
        
        # ── Per-video retry badge: ♻️ 3/4 ──
        retrying_count = sum(1 for vo in video_outputs if vo.get('quality') == 'retrying')
        
        if item.status == "completed" and retrying_count > 0:
            total_count = len(video_outputs) or 1
            done_count = total_count - retrying_count
            status_text = f"♻️ {done_count}/{total_count}"
            
            status_label = QLabel(status_text)
            status_label.setFixedWidth(120)
            status_label.setAlignment(Qt.AlignCenter)
            status_label.setToolTip(
                f"{retrying_count} video(s) retrying\n"
                f"{done_count} video(s) done"
            )
            status_label.setStyleSheet(f"""
                color: {Theme.PURPLE if hasattr(Theme, 'PURPLE') else Theme.BLUE};
                font-size: 10px;
                font-weight: bold;
                border: none;
            """)
            widget.status_label = status_label
            layout.addWidget(status_label)
        elif item.status == "completed" and upscale_status == "failed":
            # Status label showing per-video fail count
            failed_count = sum(1 for vo in video_outputs if vo.get('upscale_status') == 'failed')
            total_count = len(video_outputs) or 1
            download_quality = task_data.get('download_quality', '?') if task_data else '?'
            
            if total_count <= 1:
                status_text = "⚠️ UP FAIL"
            else:
                status_text = f"⚠️ {failed_count}/{total_count} FAIL"
            
            status_label = QLabel(status_text)
            status_label.setFixedWidth(120)
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
            display_status = f"{cfg['icon']} {item.status.upper()}"
            tooltip_text = ""
            display_color = cfg['color']
            
            if item.status in ("running", "waiting_poll") and task_data:
                last_status = task_data.get('status_text', '')
                if last_status:
                    display_status = last_status[:18]
                    if "⬇️" in last_status or "Download" in last_status:
                        display_color = Theme.SAPPHIRE
                    elif "⬆️" in last_status or "Upscal" in last_status:
                        display_color = Theme.PURPLE if hasattr(Theme, 'PURPLE') else Theme.BLUE
                    elif "🔄" in last_status or "Poll" in last_status:
                        display_color = Theme.PEACH
                
                # Per-video upscale status tooltip
                video_outputs = task_data.get('video_outputs', [])
                if video_outputs:
                    vo_lines = []
                    for vo in video_outputs:
                        us = vo.get('upscale_status', '')
                        idx = vo.get('index', 0) + 1
                        if us == 'success':
                            vo_lines.append(f"  Video {idx}: ✅ Upscaled")
                        elif us == 'polling':
                            vo_lines.append(f"  Video {idx}: 🔄 Polling")
                        elif us == 'failed':
                            vo_lines.append(f"  Video {idx}: ❌ {vo.get('upscale_error', 'Failed')}")
                        elif us == 'skipped':
                            vo_lines.append(f"  Video {idx}: ⏭ Skipped")
                    if vo_lines:
                        tooltip_text = "Per-video status:\n" + "\n".join(vo_lines)
            
            status_label = QLabel(display_status)
            status_label.setFixedWidth(120)
            status_label.setAlignment(Qt.AlignCenter)
            status_label.setStyleSheet(f"""
                color: {display_color};
                font-size: 10px;
                font-weight: bold;
                border: none;
            """)
            if tooltip_text:
                status_label.setToolTip(tooltip_text)
            widget.status_label = status_label
            layout.addWidget(status_label)
        
        # Col 6-7: Action buttons
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
        
        actions_wrapper = QWidget()
        actions_wrapper.setStyleSheet("border: none; background: transparent;")
        actions_wrapper.setFixedWidth(68)
        aw_layout = QHBoxLayout(actions_wrapper)
        aw_layout.setContentsMargins(0, 0, 0, 0)
        aw_layout.setSpacing(4)
        aw_layout.addStretch()
        
        # Retry button
        retry_btn = QPushButton("\u27f3")
        retry_btn.setFixedSize(30, 24)
        retry_btn.setToolTip("Retry this prompt")
        retry_btn.setStyleSheet(_RETRY_BTN_STYLE)
        retry_btn.clicked.connect(lambda checked, _id=item.id: self._on_retry_item(_id))
        if item.status not in ("failed", "cancelled"):
            retry_btn.hide()
        aw_layout.addWidget(retry_btn)
        widget.retry_btn = retry_btn  # Store for status-update toggling
        
        # Delete button
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
    
    # ── Queue Refresh ────────────────────────────────────────────
    
    def _refresh_queue_from_controller(self):
        """Refresh queue from controller using hierarchical group data."""
        if not self.controller:
            return
        
        # Clear stale pulse/animation references (widgets may be rebuilt)
        self._input_pulse_thumbs.clear()
        self._shimmer_active_slots.clear()
        self._upscale_spinner_slots.clear()
        
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
        all_task_ids = set()
        
        for g in groups_data:
            gid = g['id']
            
            if gid in self._group_widgets:
                # Update existing group
                gw = self._group_widgets[gid]
                self._update_group_header(gw['header'], g)
                # Differential rebuild children
                self._rebuild_group_children(gw, g)
            else:
                # Create new group
                expanded = self._group_expanded.get(gid, False)
                container = self._create_group_widget(g, expanded)
                self._group_expanded[gid] = expanded
                self.queue_layout.insertWidget(
                    self.queue_layout.count() - 1, container
                )
            
            # Track items for stats + collect all task IDs
            for td in g.get('tasks', []):
                all_task_ids.add(str(td['id']))
                item = QueueItem(
                    id=td['id'], prompt=td['prompt'],
                    status=td['status'], progress=td['progress'],
                    mode=td.get('mode', 'T2V'),
                )
                self._queue_items.append(item)
        
        # Prune stale entries from _task_widgets and _smooth_progress
        stale_tids = [tid for tid in self._task_widgets if tid not in all_task_ids]
        for tid in stale_tids:
            self._task_widgets.pop(tid, None)
            self._smooth_progress.pop(tid, None)
        
        # Update total elapsed time across all groups
        total_elapsed = sum(g.get('elapsed_seconds', 0) for g in groups_data)
        if total_elapsed > 0:
            te = int(total_elapsed)
            if te >= 3600:
                self.total_time_label.setText(f"⏱ Total: {te // 3600}h {(te % 3600) // 60:02d}m")
            else:
                self.total_time_label.setText(f"⏱ Total: {te // 60:02d}:{te % 60:02d}")
        else:
            self.total_time_label.setText("⏱ Total: --:--")
    
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
    
    # ── Sample Data & Item Operations ────────────────────────────
    
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
    
    # ── Engine Controls ──────────────────────────────────────────
    
    def _on_toggle_engine(self):
        """Unified Start/Pause/Resume toggle."""
        if not self._is_processing:
            # Idle → Start
            if self.controller and hasattr(self.controller, 'dispatcher'):
                if self.controller.ready_count == 0:
                    main_window = self.window()
                    if main_window and hasattr(main_window, 'show_toast'):
                        main_window.show_toast(
                            t("queue.no_tasks_ready"),
                            "warning", duration=4000
                        )
                    return  # Nothing to process
            
            # Pre-flight readiness check — show detailed feedback
            if self.controller and hasattr(self.controller, 'preflight_check'):
                check = self.controller.preflight_check()
                main_window = self.window()
                
                if not check["can_start"]:
                    details = []
                    for acc in check["accounts"]:
                        if acc["issues"]:
                            details.append(f"{acc['email']}: {', '.join(acc['issues'])}")
                    msg = f"{check['summary']}\n" + "\n".join(details)
                    if main_window and hasattr(main_window, 'show_toast'):
                        main_window.show_toast(msg, "error", duration=8000)
                    return
                
                elif any(acc["warnings"] for acc in check["accounts"]):
                    warns = []
                    for acc in check["accounts"]:
                        if acc["warnings"]:
                            warns.append(f"{acc['email']}: {', '.join(acc['warnings'])}")
                    if main_window and hasattr(main_window, 'show_toast'):
                        main_window.show_toast(
                            f"{check['summary']}\n" + "\n".join(warns),
                            "warning", duration=5000
                        )
                else:
                    if main_window and hasattr(main_window, 'show_toast'):
                        main_window.show_toast(check["summary"], "success", duration=3000)
            
            # ── G0: Daily generation limit gate ──────────────────────
            # Check BEFORE engine starts — block if limit exceeded.
            # Only applies to TRIAL (PREMIUM/TESTER have limit = -1).
            _ctrl = self.controller
            _perm = getattr(_ctrl, '_permissions', None) if _ctrl else None
            _lc = getattr(_ctrl, '_license_client', None) if _ctrl else None
            
            if _perm and _lc:
                daily_limit = _perm.limits.daily_generation_limit
                if daily_limit > 0:  # -1 = unlimited
                    today_used = _lc.usage.today_generations
                    if today_used >= daily_limit:
                        # Show purchase popup — blocks until user acts
                        from ui.popups.license_popup import LicenseRequiredDialog
                        dlg = LicenseRequiredDialog(
                            parent=self,
                            controller=_ctrl,
                            force_exit=False,
                            license_error=(
                                f"Daily limit reached ({today_used}/{daily_limit}). "
                                "Upgrade to continue generating."
                            ),
                        )
                        result = dlg.exec()
                        
                        if result != dlg.DialogCode.Accepted:
                            # User closed without purchasing → force stop
                            self._is_processing = False
                            self._is_paused = False
                            self._update_button_states()
                            return  # Block engine start entirely
                        else:
                            # License activated → re-check limits
                            _perm = getattr(_ctrl, '_permissions', None)
                            new_limit = _perm.limits.daily_generation_limit if _perm else -1
                            if new_limit > 0 and _lc.usage.today_generations >= new_limit:
                                # Still exceeded (shouldn't happen after upgrade)
                                self._is_processing = False
                                self._is_paused = False
                                self._update_button_states()
                                return
            # ── End G0 ───────────────────────────────────────────────
            
            self.start_all.emit()
            # Note: start_all signal is connected to controller.start_processing() in app.py
            # — no direct call needed here
            self._is_processing = self.controller.state.is_processing if self.controller else True
            self._is_paused = False
            self._auto_refresh_timer.start()
        elif self._is_paused:
            # Paused → Resume
            self.resume_all.emit()
            if self.controller:
                self.controller.resume_processing()
            self._is_paused = False
            self._auto_refresh_timer.start()
        else:
            # Running → Pause
            self.pause_all.emit()
            if self.controller:
                self.controller.pause_processing()
            self._is_paused = True
            self._auto_refresh_timer.stop()
        
        self._update_button_states()
    
    def _on_stop_all(self):
        """Stop all processing immediately."""
        self._is_processing = False
        self._is_paused = False
        self._auto_refresh_timer.stop()
        self.stop_all.emit()
        if self.controller:
            self.controller.stop_processing()
        self._is_processing = self.controller.state.is_processing if self.controller else False
        self._update_button_states()
    
    def _update_button_states(self):
        """Update toggle button appearance based on engine state."""
        if not self._is_processing:
            self.toggle_btn.setText(t("queue.start_all"))
            self.toggle_btn.setStyleSheet(f"background-color: {Theme.GREEN};")
            self.stop_btn.setEnabled(False)
        elif self._is_paused:
            self.toggle_btn.setText(t("queue.resume"))
            self.toggle_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
            self.stop_btn.setEnabled(True)
        else:
            self.toggle_btn.setText(t("queue.pause"))
            self.toggle_btn.setStyleSheet(f"background-color: {Theme.YELLOW};")
            self.stop_btn.setEnabled(True)
    
    def _on_retry_failed(self):
        """Retry ALL failed tasks — staggered 1 per 2s to avoid flooding."""
        failed_items = [i for i in self._queue_items if i.status == "failed"]
        if not failed_items:
            return
        
        # Bug 5 fix: Debounce — disable button for 3s to prevent double-click
        self.retry_failed_btn.setEnabled(False)
        QTimer.singleShot(3000, lambda: self.retry_failed_btn.setEnabled(True))
        
        self._retry_pending = list(failed_items)
        total = len(self._retry_pending)
        self.retry_failed.emit()
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(f"Retrying {total} failed prompts (1 per 2s)", "info")
        
        self._retry_next()

    def _on_force_retry_all(self):
        """Force retry ALL tasks (re-generate everything) — staggered 1 per 2s."""
        all_items = [i for i in self._queue_items if i.status != 'running']
        if not all_items:
            return

        if not show_confirm(self, "Force Retry All",
                f"Force re-generate ALL {len(all_items)} prompts?\n\n"
                "This will delete existing outputs and re-queue everything.",
                danger=True):
            return

        # Debounce
        self.force_all_btn.setEnabled(False)
        QTimer.singleShot(5000, lambda: self.force_all_btn.setEnabled(True))

        count = 0
        if self.controller and hasattr(self.controller, 'force_retry_task'):
            for item in all_items:
                if self.controller.force_retry_task(str(item.id)):
                    count += 1

        self._refresh_queue_from_controller()
        self._update_stats()

        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(f"🔄 Force retrying {count} prompts — re-queued", "info")
    
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
        """Delete ALL groups and tasks from the queue."""
        group_count = len(self._group_widgets)
        if group_count == 0:
            return
        
        if not show_confirm(self, "Delete All",
                f"Delete all {group_count} group(s) and their tasks?\n\n"
                f"This will permanently remove everything from the queue\n"
                f"and delete the session file.", danger=True):
            return
        
        count = 0
        if self.controller and hasattr(self.controller, 'clear_queue'):
            count = self.controller.clear_queue()
        
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
        
        if not show_confirm(self, "Reset All",
                f"Reset incomplete/failed prompts?\n\n"
                f"Completed tasks will be PRESERVED.\n"
                f"Only pending, failed, and errored tasks will be reset and re-queued.",
                danger=True):
            return
        
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
    
    def _on_retry_item(self, item_id):
        """Retry a specific failed item."""
        if self.controller and hasattr(self.controller, 'retry_task'):
            success = self.controller.retry_task(str(item_id))
            if success:
                self._refresh_queue_from_controller()
                self._update_stats()
                
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Retrying prompt #{item_id}", "info")
            else:
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Cannot retry prompt #{item_id}", "warning")
    
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
    
    # ── Post-Queue Action ─────────────────────────────────────────
    
    def _post_queue_combo_changed(self, index: int):
        """Sync Queue dropdown → AppSettings (two-way sync with Settings tab)."""
        _reverse_map = {"🔌 Do Nothing": "nothing", "⚡ Shutdown": "shutdown", "💤 Sleep": "sleep"}
        try:
            from config.settings import get_settings, save_settings
            s = get_settings()
            text = self.post_queue_combo.currentText()
            s.post_queue_action = _reverse_map.get(text, "nothing")
            s.post_queue_action_enabled = (s.post_queue_action != "nothing")
            save_settings()
        except Exception:
            pass
    
    def _check_post_queue_action(self):
        """Check if ALL queue groups are done (including upscale) → trigger action."""
        if self._post_queue_triggered:
            return
        if not self.controller:
            return
        
        from config.settings import get_settings
        s = get_settings()
        action = getattr(s, 'post_queue_action', 'nothing')
        if action == 'nothing':
            return
        
        # Use dispatcher task states (source of truth, not UI widgets)
        try:
            dispatcher = self.controller._dispatcher
            groups = dispatcher.get_task_groups()
            if not groups:
                return  # No tasks in queue
            
            from core.dispatcher import TaskState
            pending = 0
            processing = 0
            completed = 0
            for group in groups.values():
                for task in group.tasks:
                    if task.state in (TaskState.PENDING, TaskState.READY, TaskState.WAITING):
                        pending += 1
                    elif task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                        processing += 1
                    elif task.state == TaskState.COMPLETED:
                        completed += 1
                    # FAILED/CANCELLED are ignored (don't block shutdown)
            
            if pending > 0 or processing > 0 or completed == 0:
                return
            
            # Also check upscale queue — don't shutdown while upscaling
            engine = getattr(self.controller, '_engine', None)
            if engine:
                uq = getattr(engine, '_upscale_queue', None)
                if uq:
                    stats = uq.get_stats()
                    if stats.get('pending_jobs', 0) > 0 or stats.get('active_workers', 0) > 0:
                        return  # Upscale still running
        except Exception:
            return  # Safe fallback — don't trigger on error
        
        self._post_queue_triggered = True
        self._execute_post_queue_action(action)
    
    def _execute_post_queue_action(self, action: str):
        """Execute shutdown or sleep with countdown toast."""
        import subprocess
        import logging
        log = logging.getLogger("queue")
        
        main_window = self.window()
        
        if action == "shutdown":
            log.info("[Queue] Post-queue action: SHUTDOWN in 60s")
            # Schedule shutdown with 60s delay (cancelable via `shutdown /a`)
            try:
                subprocess.Popen(["shutdown", "/s", "/t", "60"], shell=True)
            except Exception as e:
                log.error(f"[Queue] Shutdown command failed: {e}")
                return
            
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast(
                    "⚡ All tasks done! Shutting down in 60 seconds...\n"
                    "Click Cancel below or run 'shutdown /a' to abort.",
                    "warning", duration=55000
                )
            # Show cancel button via separate timer
            self._shutdown_cancel_timer = QTimer(self)
            self._shutdown_cancel_timer.setSingleShot(True)
            self._shutdown_cancel_timer.setInterval(55000)
            self._shutdown_cancel_timer.timeout.connect(
                lambda: setattr(self, '_post_queue_triggered', False)
            )
            self._shutdown_cancel_timer.start()
            
        elif action == "sleep":
            log.info("[Queue] Post-queue action: SLEEP")
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast(
                    "💤 All tasks done! Putting computer to sleep...",
                    "info", duration=5000
                )
            # Delay 5s then sleep
            QTimer.singleShot(5000, lambda: self._do_sleep())
    
    def _do_sleep(self):
        """Execute sleep command."""
        import subprocess
        import logging
        try:
            subprocess.Popen(
                ["rundll32", "powrprof.dll,SetSuspendState", "0,1,0"],
                shell=True
            )
        except Exception as e:
            logging.getLogger("queue").error(f"[Queue] Sleep command failed: {e}")
    
    def _cancel_post_queue_action(self):
        """Cancel a pending shutdown."""
        import subprocess
        import logging
        try:
            subprocess.Popen(["shutdown", "/a"], shell=True)
            self._post_queue_triggered = False
            logging.getLogger("queue").info("[Queue] Shutdown cancelled")
            main_window = self.window()
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast("✅ Shutdown cancelled.", "success", duration=3000)
        except Exception as e:
            logging.getLogger("queue").error(f"[Queue] Cancel shutdown failed: {e}")
