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


def _is_widget_alive(widget) -> bool:
    """Check if a QWidget reference is still valid (not deleted)."""
    try:
        widget.isVisible()  # Will raise RuntimeError if C++ object deleted
        return True
    except RuntimeError:
        return False


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

        self._start_time = None
        self._retry_pending = []  # Staggered retry queue
        self._input_pulse_thumbs: List[QLabel] = []  # Thumbnails with pulsing border
        self._input_pulse_phase = False  # Toggle for pulse animation
        self._post_queue_triggered = False  # Guard: prevent double-trigger
        self._sweep_count = 0           # Auto-sweep rounds executed
        self._max_sweep_rounds = 5      # Safety limit: max retry rounds
        self._sweep_in_progress = False  # Prevent concurrent sweeps
        
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
        # BUG-A8 fix: Input pulse timer for I2V/R2V thumbnails (was missing)
        self._input_pulse_timer = QTimer(self)
        self._input_pulse_timer.setInterval(800)  # 0.8s toggle
        self._input_pulse_timer.timeout.connect(self._tick_input_pulse)
        self._input_pulse_timer.start()
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
            if self._is_processing:
                self.toggle_btn.setText(t("queue.stop"))
            else:
                self.toggle_btn.setText(t("queue.start_all"))
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
            # BUG-A3 fix: Get live task status (not stale from widget creation)
            task_status = getattr(widget, '_task_status', 'running')
            live_task = None  # Init for use in slot refresh below
            if self.controller and hasattr(self.controller, 'dispatcher'):
                live_task = self.controller.dispatcher.get_all_tasks_dict().get(task_id)
                if live_task:
                    task_status = live_task.state.value
                    widget._task_status = task_status  # Update cached status
            for vi_idx, slot in enumerate(widget.thumb_slots):
                try:
                    # ⚡ FIX: Refresh _video_info from live dispatcher data
                    # so _apply_thumb_effect sees current upscale_status
                    # (prevents stale snapshot from rendering green instead of purple)
                    if live_task and hasattr(live_task, 'video_outputs') and vi_idx < len(live_task.video_outputs):
                        live_vo = live_task.video_outputs[vi_idx]
                        slot._video_info = {
                            'quality': live_vo.quality,
                            'upscale_status': live_vo.upscale_status,
                            'upscale_error': live_vo.upscale_error,
                            'border_color': live_vo.border_color,
                            'best_file': live_vo.best_file,
                            'thumbnail_path': live_vo.thumbnail_path,
                            'upscale_poll_count': getattr(live_vo, 'upscale_poll_count', 0),
                        }
                        slot._border_color_name = live_vo.border_color
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
                        widget.status_label.setText(t("queue_extra.retrying").replace("{count}", str(retrying_count)).replace("{total}", str(total)))
                        widget.status_label.setStyleSheet(f"color: {Theme.PURPLE}; font-size: 10px; font-weight: bold; border: none;")
                    else:
                        widget.status_label.setText(t("queue_extra.completed"))
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
                # BUG-A9 fix: Use 'running' status for retry animation path
                # (original task is 'completed' but replacement is actively running)
                self._apply_thumb_effect(slot, progress, 'running')
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
    
    def _tick_input_pulse(self):
        """BUG-A8 fix: Animate input thumbnails border (I2V/R2V modes)."""
        if not self._input_pulse_thumbs:
            return
        self._input_pulse_phase = not self._input_pulse_phase
        bright = Theme.BLUE
        dim = "#3a4a6a"  # Muted blue
        border_color = bright if self._input_pulse_phase else dim
        alive = []
        for thumb in self._input_pulse_thumbs:
            try:
                thumb.setStyleSheet(f"""
                    QLabel {{
                        border: 1px solid {border_color};
                        border-radius: 4px;
                        background-color: {Theme.BASE};
                        padding: 1px;
                    }}
                """)
                alive.append(thumb)
            except RuntimeError:
                continue
        self._input_pulse_thumbs = alive
    
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
        bar.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE1}; }}")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)
        
        # Filter label
        filter_label = QLabel(t("queue_extra.filter"))
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
        self.status_filter.setMinimumWidth(130)
        self.status_filter.addItems([t("queue_extra.all_status"), t("queue_extra.status_pending"), t("queue_extra.status_processing"), t("queue_extra.status_completed"), t("queue_extra.status_failed"), t("queue_extra.status_cancelled")])
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        layout.addWidget(self.status_filter)
        
        # Mode dropdown
        self.mode_filter = QComboBox()
        self.mode_filter.setMinimumWidth(160)
        self.mode_filter.addItem(t("queue_extra.all_modes"), "ALL")
        self.mode_filter.addItem("Text → Video", "T2V")
        self.mode_filter.addItem("Image → Video", "I2V")
        self.mode_filter.addItem("Remix Video", "R2V")
        self.mode_filter.addItem("Text → Image", "T2I")
        self.mode_filter.addItem("Image → Image", "I2I")
        self.mode_filter.currentIndexChanged.connect(self._on_filter_changed)
        layout.addWidget(self.mode_filter)
        
        layout.addStretch()
        
        # Search input (no separate button - textChanged is enough)
        self.search_input = QLineEdit()
        self.search_input.setFixedWidth(200)
        self.search_input.setPlaceholderText(t("queue_extra.search_placeholder"))
        self.search_input.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.search_input)
        
        return bar
    
    def _on_filter_changed(self, text: str = None):
        """Handle any filter change - apply all filters."""
        self._apply_filters()
    
    def _on_toggle_all_groups(self):
        """Toggle expand/collapse ALL groups at once."""
        if not self._group_widgets:
            return
        # Determine target state: if any group is expanded → collapse all, else expand all
        any_expanded = any(self._group_expanded.get(gid, True) for gid in self._group_widgets)
        new_state = not any_expanded  # If any expanded → collapse; if all collapsed → expand
        
        for gid, gw in self._group_widgets.items():
            self._group_expanded[gid] = new_state
            gw['content'].setVisible(new_state)
            gw['arrow'].setText("▼" if new_state else "▶")
        
        # Update header button icon
        if hasattr(self, '_toggle_all_btn'):
            self._toggle_all_btn.setText("▼" if new_state else "▶")
    
    def _apply_filters(self):
        """Apply all filters to queue view."""
        # ── FIX: Use index-based checks instead of hardcoded English strings ──
        # Index 0 = "All" option for each filter, works regardless of language
        project_idx = self.project_filter.currentIndex()
        project = self.project_filter.currentText()
        status = self.status_filter.currentText().lower()
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
            
            # Project filter: index 0 = All Projects
            if project_idx != 0 and getattr(item, 'project', '') != project:
                show = False
            
            # Status filter (using status groups for correct matching)
            # index 0 = All Statuses → allowed_statuses will be None → show all
            if allowed_statuses is not None and item.status not in allowed_statuses:
                show = False
            
            # Mode filter: use itemData for matching (display shows full description)
            selected_mode = self.mode_filter.currentData()
            if selected_mode and selected_mode != "ALL" and item.mode != selected_mode:
                show = False
            
            # Search filter
            if search and search not in item.prompt.lower():
                show = False
            
            widget.setVisible(show)
    
    def _create_control_bar(self) -> QWidget:
        """Create control buttons bar."""
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; }}")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        self.toggle_btn = QPushButton(t("queue.start_all"))
        self.toggle_btn.setProperty("variant", "success")
        self.toggle_btn.clicked.connect(self._on_toggle_engine)
        layout.addWidget(self.toggle_btn)
        
        # Post-queue action dropdown — synced with Settings tab
        from config.settings import get_settings as _gs
        _s = _gs()
        _action_map = {"nothing": "🔌 Do Nothing", "shutdown": "⚡ Shutdown", "sleep": "💤 Sleep"}
        saved_action = _action_map.get(getattr(_s, 'post_queue_action', 'nothing'), "🔌 Do Nothing")
        
        self.post_queue_combo = QComboBox()
        self.post_queue_combo.addItems([t("queue_extra.do_nothing"), t("queue_extra.shutdown"), t("queue_extra.sleep")])
        self.post_queue_combo.setCurrentText(saved_action)
        self.post_queue_combo.setMinimumWidth(150)
        self.post_queue_combo.setToolTip(t("queue_extra.post_queue_tooltip"))
        self.post_queue_combo.currentIndexChanged.connect(self._post_queue_combo_changed)
        layout.addWidget(self.post_queue_combo)
        
        layout.addStretch()
        
        # Retry Failed button
        self.retry_failed_btn = QPushButton(t("queue.retry_failed"))
        self.retry_failed_btn.setProperty("variant", "warning")
        self.retry_failed_btn.setToolTip(t("queue_extra.retry_failed_tooltip"))
        self.retry_failed_btn.clicked.connect(self._on_retry_failed)
        layout.addWidget(self.retry_failed_btn)

        # Retry Failed Videos button — retry only failed video slots (partial failures)
        self.retry_videos_btn = QPushButton(t("queue_extra.retry_videos"))
        self.retry_videos_btn.setProperty("variant", "secondary")
        self.retry_videos_btn.setToolTip(t("queue_extra.retry_videos_tooltip"))
        self.retry_videos_btn.clicked.connect(self._on_retry_failed_videos)
        layout.addWidget(self.retry_videos_btn)

        # Force Retry All button — force re-generate ALL tasks
        self.force_all_btn = QPushButton(t("queue_extra.force_all"))
        self.force_all_btn.setProperty("variant", "secondary")
        self.force_all_btn.setToolTip(t("queue_extra.force_all_tooltip"))
        self.force_all_btn.clicked.connect(self._on_force_retry_all)
        layout.addWidget(self.force_all_btn)

        # Reset All
        self.reset_btn = QPushButton(t("queue.reset_all"))
        self.reset_btn.setProperty("variant", "secondary")
        self.reset_btn.setToolTip(t("queue_extra.reset_tooltip"))
        self.reset_btn.clicked.connect(self._on_reset_all)
        layout.addWidget(self.reset_btn)
        
        # Delete All
        self.delete_all_btn = QPushButton(t("queue.delete_all"))
        self.delete_all_btn.setProperty("variant", "danger")
        self.delete_all_btn.setToolTip(t("queue_extra.delete_all_tooltip"))
        self.delete_all_btn.clicked.connect(self._on_delete_all)
        layout.addWidget(self.delete_all_btn)

        # 🔍 Debug Queue (temporary diagnostic)
        self._debug_btn = QPushButton("🔍 Debug")
        self._debug_btn.setMinimumWidth(70)
        self._debug_btn.setProperty("variant", "secondary")
        self._debug_btn.setToolTip("Dump queue state for diagnostics")
        self._debug_btn.clicked.connect(self._on_debug_dump)
        layout.addWidget(self._debug_btn)
        
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
            (None, 40, 0, False), ("Mode", 55, 0, False),
            ("Images", 120, 0, False),
            ("Prompt", 0, 1, False), 
            ("Progress", 180, 0, True), ("Status", 120, 0, True),
            ("Actions", 68, 0, True),
        ]
        for label_text, width, stretch, center in cols:
            if label_text is None:
                # Toggle All expand/collapse button
                self._toggle_all_btn = QPushButton("▼")
                self._toggle_all_btn.setMinimumSize(40, 24)
                self._toggle_all_btn.setToolTip(t("queue_extra.toggle_all_tooltip"))
                self._toggle_all_btn.setCursor(Qt.PointingHandCursor)
                self._toggle_all_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent; color: {Theme.SUBTEXT0};
                        border: none; font-size: 12px; font-weight: bold;
                    }}
                    QPushButton:hover {{ color: {Theme.TEXT}; }}
                """)
                self._toggle_all_btn.clicked.connect(self._on_toggle_all_groups)
                header_layout.addWidget(self._toggle_all_btn, stretch=stretch)
            else:
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
        bar.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; }}")
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        
        self.stats_label = QLabel(t("queue_extra.stats").replace("{pending}", "0").replace("{processing}", "0").replace("{completed}", "0").replace("{failed}", "0"))
        self.stats_label.setStyleSheet(f"color: {Theme.TEXT};")
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        
        self.eta_label = QLabel(t("queue_extra.eta_default"))
        self.eta_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        layout.addWidget(self.eta_label)
        
        self.total_time_label = QLabel(t("queue_extra.total_time"))
        self.total_time_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        self.total_time_label.setToolTip(t("queue_extra.total_time_tooltip"))
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
        widget.mode_label = mode_label  # Store ref for differential update
        
        # Col 3: Input Images — 120px
        input_thumbs = self._create_input_thumbs(item.mode, task_data)
        layout.addWidget(input_thumbs)
        widget.input_thumbs_container = input_thumbs  # Store ref for differential update
        
        # Col 4: Prompt — flex (2-line: scene name + detail)
        full_prompt = item.prompt or ""
        # Extract scene name (text before first ". " or full if short)
        dot_pos = full_prompt.find(". ")
        if dot_pos > 0 and dot_pos < 120:
            scene_name = full_prompt[:dot_pos]
            detail_text = full_prompt[dot_pos + 2:]
        else:
            scene_name = full_prompt[:80]
            detail_text = full_prompt[80:] if len(full_prompt) > 80 else ""
        
        prompt_widget = QWidget()
        prompt_widget.setStyleSheet("border: none; background: transparent;")
        prompt_layout_v = QVBoxLayout(prompt_widget)
        prompt_layout_v.setContentsMargins(0, 2, 0, 2)
        prompt_layout_v.setSpacing(1)
        
        # Line 1: Scene name (bold, prominent)
        scene_label = QLabel(scene_name)
        scene_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold; border: none;")
        scene_label.setToolTip(full_prompt)
        prompt_layout_v.addWidget(scene_label)
        
        # Line 2: Remaining detail (smaller, muted)
        if detail_text:
            detail_label = QLabel(detail_text[:200])
            detail_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px; border: none;")
            detail_label.setToolTip(full_prompt)
            prompt_layout_v.addWidget(detail_label)
        
        layout.addWidget(prompt_widget, stretch=1)
        
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
        retry_btn.setMinimumSize(30, 24)
        retry_btn.setToolTip(t("queue_extra.retry_prompt_tooltip"))
        retry_btn.setStyleSheet(_RETRY_BTN_STYLE)
        retry_btn.clicked.connect(lambda checked, _id=item.id: self._on_retry_item(_id))
        if item.status not in ("failed", "cancelled"):
            retry_btn.hide()
        aw_layout.addWidget(retry_btn)
        widget.retry_btn = retry_btn  # Store for status-update toggling
        
        # Delete button
        delete_btn = QPushButton("\u2715")
        delete_btn.setMinimumSize(30, 24)
        delete_btn.setToolTip(t("queue_extra.remove_prompt_tooltip"))
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
    
    # ── Debug ─────────────────────────────────────────────────────

    def _on_debug_dump(self):
        """Dump queue state for diagnostics — shows controller data + widget tree."""
        lines = ["═══ QUEUE DEBUG DUMP ═══\n"]

        # 1. Controller data
        if self.controller and hasattr(self.controller, 'get_queue_groups'):
            groups = self.controller.get_queue_groups()
            lines.append(f"📊 Controller: {len(groups)} groups")
            for g in groups:
                tasks = g.get('tasks', [])
                lines.append(f"  📁 {g.get('name', '?')} (id={g.get('id', '?')}) — {len(tasks)} tasks")
                for t in tasks[:3]:  # Show first 3 prompts
                    prompt_short = t.get('prompt', '')[:60]
                    lines.append(f"    #{t.get('index','?')} [{t.get('status','?')}] {prompt_short}...")
                if len(tasks) > 3:
                    lines.append(f"    ... +{len(tasks)-3} more")
        else:
            lines.append("❌ No controller or get_queue_groups")

        # 2. Widget tree
        lines.append(f"\n🧩 Widget tree: {len(self._group_widgets)} group widgets, {len(self._task_widgets)} task widgets")
        for gid, gw in self._group_widgets.items():
            content = gw.get('content')
            container = gw.get('container')
            expanded = self._group_expanded.get(gid, 'NOT SET')
            name_label = gw.get('name_label')
            name_text = name_label.text() if name_label else '?'
            child_count = content.layout().count() if content and content.layout() else 0
            content_visible = content.isVisible() if content else 'N/A'
            container_visible = container.isVisible() if container else 'N/A'
            content_height = content.height() if content else 0
            lines.append(f"  📁 {name_text}")
            lines.append(f"     gid={gid}")
            lines.append(f"     expanded={expanded} | content_visible={content_visible} | container_visible={container_visible}")
            lines.append(f"     children={child_count} | content_height={content_height}px")

            # Check child widgets
            if content and content.layout():
                for ci in range(min(child_count, 3)):
                    item = content.layout().itemAt(ci)
                    w = item.widget() if item else None
                    if w:
                        tid = getattr(w, '_task_id', '?')
                        vis = w.isVisible()
                        h = w.height()
                        lines.append(f"       child[{ci}] tid={tid} visible={vis} height={h}px")
                if child_count > 3:
                    lines.append(f"       ... +{child_count-3} more children")

        # 3. Queue items
        lines.append(f"\n📋 QueueItems tracked: {len(self._queue_items)}")
        for qi in self._queue_items[:5]:
            lines.append(f"  id={qi.id} status={qi.status} prompt={qi.prompt[:40]}...")
        if len(self._queue_items) > 5:
            lines.append(f"  ... +{len(self._queue_items)-5} more")

        # 4. Filters
        lines.append(f"\n🔧 Filters: project='{self.project_filter.currentText()}' status='{self.status_filter.currentText()}' mode='{self.mode_filter.currentText()}' search='{self.search_input.text()}'")

        dump_text = "\n".join(lines)

        # Show in scrollable dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("🔍 Queue Debug Dump")
        dlg.resize(700, 500)
        lay = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(dump_text)
        te.setStyleSheet(f"background: {Theme.CRUST}; color: {Theme.TEXT}; font-family: Consolas; font-size: 12px;")
        lay.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.exec()

    # ── Queue Refresh ────────────────────────────────────────────
    
    def _refresh_queue_from_controller(self):
        """Refresh queue from controller using hierarchical group data."""
        if not self.controller:
            return
        
        # BUG-A7 + A10 fix: Don't clear ALL animation slots — prune dead refs only
        # Clearing all slots causes shimmer/spinner flicker on every 2s refresh
        # because re-registration only happens via _apply_thumb_effect which
        # may not run for all slots during differential update.
        self._input_pulse_thumbs = [
            t for t in self._input_pulse_thumbs
            if _is_widget_alive(t)
        ]
        self._shimmer_active_slots = [
            s for s in self._shimmer_active_slots
            if _is_widget_alive(s)
        ]
        self._upscale_spinner_slots = [
            s for s in self._upscale_spinner_slots
            if _is_widget_alive(s)
        ]
        
        # Try group-based data first (preferred)
        if hasattr(self.controller, 'get_queue_groups'):
            groups_data = self.controller.get_queue_groups()
            import logging
            _qlog = logging.getLogger("veo.tab_queue")
            total_tasks = sum(len(g.get('tasks', [])) for g in groups_data)
            _qlog.info(f"[QueueRefresh] {len(groups_data)} groups, {total_tasks} total tasks, existing_groups={list(self._group_widgets.keys())}")
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
                expanded = self._group_expanded.get(gid, True)
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
        
        # BUG-T2 fix: Compute total elapsed as wall-clock span
        # (earliest start → latest end across ALL groups)
        # instead of summing individual groups (which double-counts
        # concurrent execution)
        from datetime import datetime as _dt
        _now_ts = _dt.now()
        all_starts = []
        all_ends = []
        groups_with_time = 0
        
        for g in groups_data:
            for td in g.get('tasks', []):
                sa = td.get('started_at')
                ca = td.get('completed_at')
                if sa:
                    # Parse ISO string if needed
                    if isinstance(sa, str):
                        try:
                            sa = _dt.fromisoformat(sa)
                        except (ValueError, TypeError):
                            continue
                    all_starts.append(sa)
                    if ca:
                        if isinstance(ca, str):
                            try:
                                ca = _dt.fromisoformat(ca)
                            except (ValueError, TypeError):
                                ca = _now_ts
                        all_ends.append(ca)
                    else:
                        all_ends.append(_now_ts)  # Still running
            
            if g.get('elapsed_seconds', 0) > 0:
                groups_with_time += 1
        
        if all_starts:
            total_elapsed = (max(all_ends) - min(all_starts)).total_seconds()
            te = int(total_elapsed)
            if te >= 3600:
                time_text = f"⏱ Total: {te // 3600}h {(te % 3600) // 60:02d}m"
            else:
                time_text = f"⏱ Total: {te // 60:02d}:{te % 60:02d}"
            self.total_time_label.setText(time_text)
        else:
            self.total_time_label.setText(t("queue_extra.total_time"))
    
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
        
        self.stats_label.setText(t("queue_extra.stats").replace("{pending}", str(pending)).replace("{processing}", str(processing)).replace("{completed}", str(completed)).replace("{failed}", str(failed)))
        
        # Calculate ETA based on processing rate
        self._update_eta(pending, processing)
    
    def _update_eta(self, pending: int, processing: int):
        """Calculate and update ETA."""
        if pending == 0 and processing == 0:
            self.eta_label.setText(t("queue_extra.eta_done"))
        elif processing == 0:
            self.eta_label.setText(t("queue_extra.eta_queued").replace("{count}", str(pending)))
        else:
            # ~90 seconds average per VEO generation
            estimated_seconds = (pending + processing) * 90
            if estimated_seconds >= 3600:
                hours = estimated_seconds // 3600
                minutes = (estimated_seconds % 3600) // 60
                self.eta_label.setText(t("queue_extra.eta_hours").replace("{hours}", str(hours)).replace("{minutes}", f"{minutes:02d}"))
            else:
                minutes = estimated_seconds // 60
                seconds = estimated_seconds % 60
                self.eta_label.setText(t("queue_extra.eta_minutes").replace("{minutes}", f"{minutes:02d}").replace("{seconds}", f"{seconds:02d}"))
    
    # ── Engine Controls ──────────────────────────────────────────
    
    def _auto_start_if_idle(self):
        """Auto-start engine if idle and ready tasks exist.
        
        Called after force_retry creates replacement tasks
        so the user doesn't have to click Start All manually.
        Skips preflight/license checks (retry = re-running existing work).
        """
        if self._is_processing:
            return  # Already running
        if not self.controller:
            return
        if self.controller.ready_count == 0:
            return  # No tasks to process
        
        # Auto-start
        self.start_all.emit()
        self._is_processing = self.controller.state.is_processing if self.controller else True
        self._auto_refresh_timer.start()
        self._update_button_states()
        
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            mw.show_toast("▶️ Engine auto-started for retry tasks", "info", duration=3000)
    
    def _on_toggle_engine(self):
        """Start ↔ Stop toggle (2-state)."""
        if not self._is_processing:
            # ── IDLE → START ──
            # Only reset sweep counter if there are ready tasks (new work).
            # When _only_ incomplete work exists (re-upscale), preserve the
            # counter so max rounds isn't bypassed by repeated Start-All clicks.
            has_ready_tasks = False
            if self.controller:
                has_ready_tasks = getattr(self.controller, 'ready_count', 0) > 0
            if has_ready_tasks:
                self._sweep_count = 0
            self._sweep_in_progress = False
            self._post_queue_triggered = False
            if self.controller:
                ready = getattr(self.controller, 'ready_count', 0)
                if ready == 0:
                    # Check if there's incomplete work (failed tasks, failed upscale, etc.)
                    import logging
                    _log = logging.getLogger("queue")
                    has_work = False
                    try:
                        dispatcher = getattr(self.controller, '_dispatcher', None)
                        if dispatcher:
                            has_work = self._has_incomplete_work(dispatcher)
                            _log.info(f"[StartAll] ready_count=0, has_incomplete_work={has_work}")
                        else:
                            _log.warning("[StartAll] No _dispatcher on controller")
                    except Exception as e:
                        _log.error(f"[StartAll] Error checking incomplete work: {e}")
                    
                    if has_work:
                        # Trigger auto-sweep for re-upscale / retry
                        from config.settings import get_settings
                        s = get_settings()
                        action = getattr(s, 'post_queue_action', 'nothing')
                        self._run_auto_sweep(action or 'nothing')
                        return
                    
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
                    pass  # Warnings are auto-resolving
                else:
                    pass  # All OK
            
            # ── G0: Daily generation limit gate ──────────────────────
            _ctrl = self.controller
            _perm = getattr(_ctrl, '_permissions', None) if _ctrl else None
            _lc = getattr(_ctrl, '_license_client', None) if _ctrl else None
            
            if _perm and _lc:
                daily_limit = _perm.limits.daily_generation_limit
                if daily_limit > 0:  # -1 = unlimited
                    today_used = _lc.usage.today_generations
                    if today_used >= daily_limit:
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
                            self._is_processing = False
                            self._update_button_states()
                            return
                        else:
                            _perm = getattr(_ctrl, '_permissions', None)
                            new_limit = _perm.limits.daily_generation_limit if _perm else -1
                            if new_limit > 0 and _lc.usage.today_generations >= new_limit:
                                self._is_processing = False
                                self._update_button_states()
                                return
            # ── End G0 ───────────────────────────────────────────────
            
            self.start_all.emit()
            self._is_processing = self.controller.state.is_processing if self.controller else True
            self._auto_refresh_timer.start()
        else:
            # ── PROCESSING → STOP ──
            self._is_processing = False
            self._auto_refresh_timer.stop()
            self.stop_all.emit()
            if self.controller:
                self.controller.stop_processing()
            # BUG-B5 fix: Delayed state check — stop_processing is async
            QTimer.singleShot(200, self._sync_processing_state)
        
        self._update_button_states()
    
    def _update_button_states(self):
        """Update toggle button appearance: Start (green) ↔ Stop (red)."""
        if not self._is_processing:
            self.toggle_btn.setText(t("queue.start_all"))
            self.toggle_btn.setProperty("variant", "success")
        else:
            self.toggle_btn.setText(t("queue.stop"))
            self.toggle_btn.setProperty("variant", "danger")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)    
    def _on_retry_failed(self):
        """Retry ALL failed tasks — staggered 1 per 2s to avoid flooding."""
        # BUG-B3 fix: Query dispatcher for live failed tasks (not stale _queue_items)
        failed_ids = []
        if self.controller and hasattr(self.controller, 'dispatcher'):
            for task in self.controller.dispatcher._all_tasks.values():
                if task.state.value == 'failed':
                    failed_ids.append(task.id)
        if not failed_ids:
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast("No failed tasks to retry", "info")
            return
        
        # Debounce — disable button for 3s to prevent double-click
        self.retry_failed_btn.setEnabled(False)
        QTimer.singleShot(3000, lambda: self.retry_failed_btn.setEnabled(True))
        
        self._retry_pending_ids = list(failed_ids)
        total = len(self._retry_pending_ids)
        self.retry_failed.emit()
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(f"Retrying {total} failed prompts (1 per 2s)", "info")
        
        self._retry_next_by_id()

    def _on_retry_failed_videos(self):
        """Retry ALL failed video slots across all tasks (including completed with partial failures)."""
        if not self.controller or not hasattr(self.controller, 'force_retry_all_failed_videos'):
            return
        
        # Debounce — disable button for 3s
        self.retry_videos_btn.setEnabled(False)
        QTimer.singleShot(3000, lambda: self.retry_videos_btn.setEnabled(True))
        
        retried = self.controller.force_retry_all_failed_videos()
        self._refresh_queue_from_controller()
        self._update_stats()
        
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            if retried > 0:
                mw.show_toast(f"♻️ Retrying {retried} failed video(s) across all tasks", "info")
            else:
                mw.show_toast("No failed videos found to retry", "info")
        
        # Auto-start engine if idle
        if retried > 0:
            self._auto_start_if_idle()

    def _on_force_retry_all(self):
        """Force retry ALL tasks (re-generate everything) — runs in background thread."""
        all_items = [i for i in self._queue_items if i.status != 'running']
        if not all_items:
            return

        # BUG-B21 fix: Filter out replacement tasks (they'll be cleaned by parent's retry)
        original_items = [i for i in all_items if '_retry_v' not in str(i.id)]
        display_count = len(original_items) if original_items else len(all_items)

        if not show_confirm(self, t("queue_extra.confirm_force_retry"),
                t("queue_extra.confirm_force_retry_msg"),
                danger=True):
            return

        # Debounce
        self.force_all_btn.setEnabled(False)
        QTimer.singleShot(5000, lambda: self.force_all_btn.setEnabled(True))

        # BUG-B4 fix: Run heavy file I/O in background, use Signal for thread-safe UI
        import threading

        # BUG-B21 fix: Only retry original tasks (replacements cleaned by parent's force_retry)
        item_ids = [str(item.id) for item in (original_items if original_items else all_items)]

        def _bg_force_retry():
            count = 0
            if self.controller and hasattr(self.controller, 'force_retry_task'):
                for item_id in item_ids:
                    if self.controller.force_retry_task(item_id):
                        count += 1
            # BUG-B4 fix: Use signal instead of QTimer from background thread
            self._queue_updated_signal.emit()

        threading.Thread(target=_bg_force_retry, daemon=True).start()
    
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
    
    def _retry_next_by_id(self):
        """BUG-B3 fix: Staggered retry using task IDs from dispatcher."""
        if not hasattr(self, '_retry_pending_ids') or not self._retry_pending_ids:
            self._refresh_queue_from_controller()
            self._update_stats()
            return
        
        task_id = self._retry_pending_ids.pop(0)
        if self.controller and hasattr(self.controller, 'retry_task'):
            if self.controller.retry_task(str(task_id)):
                print(f"[Queue] Retried task {task_id} ({len(self._retry_pending_ids)} remaining)")
        
        if self._retry_pending_ids:
            QTimer.singleShot(2000, self._retry_next_by_id)
        else:
            self._refresh_queue_from_controller()
            self._update_stats()
    
    def _sync_processing_state(self):
        """BUG-B5 fix: Sync _is_processing from controller after async stop."""
        if self.controller:
            self._is_processing = self.controller.state.is_processing
        self._update_button_states()
    
    def _on_delete_all(self):
        """Delete ALL groups and tasks from the queue."""
        group_count = len(self._group_widgets)
        if group_count == 0:
            return
        
        if not show_confirm(self, t("queue_extra.confirm_delete_all"),
                t("queue_extra.confirm_delete_all_msg"), danger=True):
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
        
        if not show_confirm(self, t("queue_extra.confirm_reset_all"),
                t("queue_extra.confirm_reset_all_msg"),
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
        """Check if ALL queue groups are done (including upscale) → trigger action.
        
        Auto-sweep gate: ALWAYS auto-retry incomplete work (up to _max_sweep_rounds)
        regardless of post_queue_action. Sleep/shutdown only happens after sweep.
        """
        if self._post_queue_triggered:
            return
        if self._sweep_in_progress:
            return
        if not self.controller:
            return
        
        from config.settings import get_settings
        s = get_settings()
        action = getattr(s, 'post_queue_action', 'nothing')
        
        # Sync max sweep rounds from settings (user can change at runtime)
        self._max_sweep_rounds = getattr(s, 'auto_sweep_max_rounds', 5)
        
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
            failed = 0
            for group in groups.values():
                for task in group.tasks:
                    if task.replace_target:
                        continue  # Skip replacement tasks
                    if task.state in (TaskState.PENDING, TaskState.READY, TaskState.WAITING):
                        pending += 1
                    elif task.state in (TaskState.RUNNING, TaskState.WAITING_POLL):
                        processing += 1
                    elif task.state == TaskState.COMPLETED:
                        completed += 1
                    elif task.state in (TaskState.FAILED, TaskState.CANCELLED):
                        failed += 1
            
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
            
            # ── Account Readiness Gate ──
            # Don't attempt re-upscale if no account has extension bridge connected
            # (browser still launching after app restart → token refresh will fail)
            _any_account_ready = False
            try:
                ma = getattr(self.controller, '_multi_account', None)
                if ma:
                    for acc in getattr(ma, '_accounts', []):
                        if getattr(acc, 'extension_bridge', None) and getattr(acc, '_access_token', None):
                            _any_account_ready = True
                            break
            except Exception:
                pass
            
            if not _any_account_ready:
                return  # Browser not ready yet — wait for next tick
            
            # ── Auto-Sweep Gate (ALWAYS runs, independent of post_queue_action) ──
            # Guarantee 100% completion: retry failed/skipped tasks before any action
            has_incomplete = self._has_incomplete_work(dispatcher)
            
            if has_incomplete and self._sweep_count < self._max_sweep_rounds:
                self._run_auto_sweep(action)
                return  # Don't trigger sleep/shutdown yet — sweep first
            
            # If max sweeps exhausted but still incomplete → log warning
            if has_incomplete and self._sweep_count >= self._max_sweep_rounds:
                import logging
                logging.getLogger("queue").warning(
                    f"[AutoSweep] Max {self._max_sweep_rounds} rounds exhausted, "
                    f"{action} will proceed despite incomplete tasks"
                )
        except Exception:
            return  # Safe fallback — don't trigger on error
        
        # ── Completion: reset sweep counter for next batch ──
        if not has_incomplete and self._sweep_count > 0:
            import logging
            logging.getLogger("queue").info(
                f"[AutoSweep] ✅ All work complete after {self._sweep_count} sweep round(s)"
            )
            self._sweep_count = 0
        
        # Only execute post-queue action (sleep/shutdown) if configured
        if action == 'nothing':
            # Mark triggered to stop wasteful per-tick checks
            if not has_incomplete:
                self._post_queue_triggered = True
            return
        
        self._post_queue_triggered = True
        self._execute_post_queue_action(action)
    
    def _has_incomplete_work(self, dispatcher) -> bool:
        """Check if any COMPLETED tasks have incomplete video outputs."""
        import logging
        _log = logging.getLogger("queue")
        from core.dispatcher import TaskState
        for task in dispatcher._all_tasks.values():
            if task.replace_target:
                continue
            # Failed/cancelled tasks = incomplete
            if task.state in (TaskState.FAILED, TaskState.CANCELLED):
                _log.debug(f"[IncompleteCheck] Task {task.id}: state={task.state.value} → incomplete")
                return True
            if task.state != TaskState.COMPLETED:
                continue
            # Check video outputs for failures or missing upscale
            is_image = getattr(task, 'workflow_type', '') in ('T2I', 'I2I')
            needs_upscale = getattr(task, 'download_quality', '720p') in ('1080p', '4K', '2K')
            # Base quality for each mode
            base_quality = '1K' if is_image else '720p'
            for vo in (task.video_outputs or []):
                # Diagnostic: log video state for tasks wanting upscale
                if needs_upscale:
                    _log.info(
                        f"[IncompleteCheck] {task.id} V{vo.index}: "
                        f"q={vo.quality}, us={vo.upscale_status}, "
                        f"up={'Y' if vo.file_upscaled else 'N'}, "
                        f"720={'Y' if vo.file_720p else 'N'}, "
                        f"mid={'Y' if vo.media_id else 'N'}"
                    )
                if vo.quality == "failed":
                    return True
                if vo.upscale_status == "failed":
                    return True
                if vo.quality not in ("failed", "retrying") and not vo.file_720p:
                    return True
                # Upscale pending/skipped: task wants higher quality but output still at base
                if needs_upscale and vo.quality == base_quality and not vo.file_upscaled:
                    if vo.upscale_status not in ("submitting", "polling", "success"):
                        return True
        return False
    
    def _run_auto_sweep(self, action: str):
        """Execute one auto-sweep round: retry incomplete work, restart engine."""
        import logging
        log = logging.getLogger("queue")
        
        self._sweep_in_progress = True
        self._sweep_count += 1
        
        try:
            # Phase 1+2: Retry failed tasks + failed video slots
            result = {"retried_tasks": 0, "retried_videos": 0, "still_incomplete": 0}
            if hasattr(self.controller, 'auto_sweep'):
                result = self.controller.auto_sweep()
            
            total_retried = result["retried_tasks"] + result["retried_videos"]
            
            # Phase 3: Re-upscale videos that need upscaling
            reupscale_count = 0
            needs_retry_ids = []  # Tasks needing re-generate (no media_id)
            engine = getattr(self.controller, '_engine', None)
            if self.controller and hasattr(self.controller, 're_upscale_task'):
                try:
                    from core.dispatcher import TaskState
                    dispatcher = self.controller._dispatcher
                    for task in dispatcher._all_tasks.values():
                        if task.replace_target:
                            continue
                        if task.state != TaskState.COMPLETED:
                            continue
                        
                        wants_upscale = getattr(task, 'download_quality', '720p') in ('1080p', '4K', '2K')
                        if not wants_upscale:
                            continue
                        
                        is_image = getattr(task, 'workflow_type', '') in ('T2I', 'I2I')
                        base_quality = '1K' if is_image else '720p'
                        needs_reupscale = False
                        has_missing_media = False
                        
                        for vo in (task.video_outputs or []):
                            # Skip videos already being retried by Phase 2
                            # (force_retry_video sets quality='retrying')
                            if vo.quality == 'retrying':
                                continue
                            # Case 1: Explicit upscale failure
                            if vo.upscale_status == "failed":
                                if vo.media_id:
                                    needs_reupscale = True
                                else:
                                    has_missing_media = True
                            # Case 2: Output at base quality, not yet upscaled
                            elif vo.quality == base_quality and not vo.file_upscaled:
                                if vo.upscale_status not in ("submitting", "polling", "success"):
                                    if vo.media_id:
                                        needs_reupscale = True
                                    else:
                                        has_missing_media = True
                        
                        if has_missing_media and not needs_reupscale:
                            # Video never generated → need task retry, not re-upscale
                            log.warning(
                                f"[AutoSweep] Task {task.id}: video(s) missing media_id "
                                f"— needs re-generation, not re-upscale"
                            )
                            needs_retry_ids.append(task.id)
                        elif needs_reupscale:
                            # Dedup: skip if task already has pending jobs in upscale queue
                            already_queued = False
                            if engine:
                                uq = getattr(engine, '_upscale_queue', None)
                                if uq and hasattr(uq, '_job_queue'):
                                    try:
                                        for job in list(uq._job_queue.queue):
                                            if getattr(job, 'task_id', None) == task.id:
                                                already_queued = True
                                                break
                                    except Exception:
                                        pass
                            if not already_queued:
                                self.controller.re_upscale_task(task.id, failed_only=True)
                                reupscale_count += 1
                except Exception as e:
                    log.error(f"[AutoSweep] Re-upscale phase error: {e}")
            
            # Phase 4: Force-retry tasks with missing media_ids (re-generate)
            # BUG-FIX: Use _enqueue_task() instead of raw _ready_queue.put()
            # to properly handle duplicate guards, priority, and counter tracking.
            retry_regen = 0
            if needs_retry_ids and hasattr(self.controller, '_dispatcher'):
                try:
                    dispatcher = self.controller._dispatcher
                    for tid in needs_retry_ids:
                        task = dispatcher.get_task(tid)
                        if task:
                            from core.dispatcher import TaskState, TaskStage
                            task.state = TaskState.READY
                            task.progress = 0
                            task.error = None
                            task.stage = TaskStage.INIT
                            task.status_text = "🔄 Auto-sweep: re-generating missing video(s)"
                            task.assigned_account = None
                            # Clear stale data for fresh generation
                            task.image_uris.clear()
                            task.image_upload_status = ""
                            task.video_outputs.clear()
                            task.output_uris.clear()
                            task.operation_name = None
                            task.operation_names.clear()
                            task.scene_ids.clear()
                            dispatcher._queued_task_ids.discard(tid)
                            dispatcher._enqueue_task(task, priority=0)
                            retry_regen += 1
                            log.info(f"[AutoSweep] Task {tid}: reset to READY for re-generation")
                except Exception as e:
                    log.error(f"[AutoSweep] Re-generate phase error: {e}")
            
            total_retried += reupscale_count + retry_regen
            
            log.info(
                f"[AutoSweep] Round {self._sweep_count}/{self._max_sweep_rounds}: "
                f"retried {result['retried_tasks']} task(s), "
                f"{result['retried_videos']} video(s), "
                f"{reupscale_count} re-upscale(s), "
                f"{retry_regen} re-gen(s), "
                f"{result['still_incomplete']} still incomplete"
            )
            
            # Show toast to user
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                if total_retried > 0:
                    parts = []
                    if result["retried_tasks"] > 0:
                        parts.append(f"{result['retried_tasks']} task(s)")
                    if result["retried_videos"] > 0:
                        parts.append(f"{result['retried_videos']} video(s)")
                    if reupscale_count > 0:
                        parts.append(f"{reupscale_count} re-upscale(s)")
                    if retry_regen > 0:
                        parts.append(f"{retry_regen} re-gen(s)")
                    mw.show_toast(
                        f"🔄 Auto-sweep #{self._sweep_count}: "
                        f"retrying {', '.join(parts)}... "
                        f"({action} deferred)",
                        "warning", duration=5000
                    )
                elif result["still_incomplete"] > 0:
                    mw.show_toast(
                        f"⚠️ Sweep #{self._sweep_count}: "
                        f"{result['still_incomplete']} still incomplete "
                        f"(no retryable items found)",
                        "warning", duration=5000
                    )
            
            # Auto-start engine if we retried tasks/videos, re-gen'd, OR re-upscaled
            if result["retried_tasks"] + result["retried_videos"] + retry_regen > 0:
                self._auto_start_if_idle()
            elif reupscale_count > 0:
                # Re-upscale jobs queued → engine must be running for upscale lifecycle
                self._auto_start_if_idle()
            elif result["still_incomplete"] == 0:
                # Everything actually complete → allow action next tick
                pass  # Will be caught next _check_post_queue_action cycle
        except Exception as e:
            log.error(f"[AutoSweep] Error: {e}")
        finally:
            self._sweep_in_progress = False
    
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
