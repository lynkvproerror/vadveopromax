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
import time as _time
import logging  # ★ R5: Module-level (was inside _refresh_queue_from_controller)
from pathlib import Path
from datetime import datetime as _dt  # ★ R5: Module-level (was inside _refresh_groups)
from dataclasses import dataclass, field
from collections import OrderedDict

from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLineEdit, QComboBox, QSizePolicy,  # ★ R5: QSizePolicy moved here
    QGraphicsOpacityEffect,
)
from ui.popups import show_confirm
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QPixmap, QCursor

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
        self._queue_item_index: Dict[str, QueueItem] = {}
        self._item_widgets: Dict[int, QFrame] = {}  # Track widgets by item ID
        self._task_widgets: Dict[str, QFrame] = {}   # task_id → row widget (for progress updates)
        self._task_data_index: Dict[str, dict] = {}
        self._task_prompt_lc_index: Dict[str, str] = {}
        self._group_widgets: Dict[str, dict] = {}   # group_id → {header, content, items}
        self._group_expanded: Dict[str, bool] = {}   # group_id → expanded state
        self._pending_group_rebuilds: Dict[str, int] = {}
        self._projects: List[str] = ["All Projects"]  # Dynamic project list
        self._is_processing = False

        self._start_time = None
        self._latest_groups_data: List[dict] = []
        self._queue_eta_seconds: Optional[float] = None
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
        self._progress_throttle_timer.setInterval(500)  # 500ms debounce to reduce full queue rebuild storms
        self._progress_throttle_timer.timeout.connect(self._flush_throttled_refresh)
        self._throttled_refresh_pending = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(120)  # search debounce
        self._filter_apply_timer.timeout.connect(self._apply_filters)
        self._suspend_filter_changes = False
        self._bulk_group_materialize_timer = QTimer(self)
        self._bulk_group_materialize_timer.setSingleShot(True)
        self._bulk_group_materialize_timer.setInterval(50)  # ★ Perf: 50ms gap between groups during expand-all
        self._bulk_group_materialize_timer.timeout.connect(self._process_bulk_group_materialize)
        self._bulk_group_materialize_queue: List[str] = []
        self._bulk_group_materialize_active = False
        self._bulk_group_resume_refresh = False
        self._queue_virtualize_threshold = 200  # ★ v2: was 600 — trigger virtual scroll earlier
        self._queue_virtual_window = 80  # ★ v2: was 140 — fewer real widgets in virtual mode
        self._queue_virtual_buffer = 20  # ★ v2: was 30
        self._queue_virtual_row_height = 61
        
        # ── Phase 2 Dynamic Effects ──
        # Shimmer wave on generating thumbnails
        self._shimmer_offset = 0.0
        self._shimmer_active_slots: List[QLabel] = []
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(100)  # Bug 9: 10fps shimmer (was 50ms/20fps — halves CSS parse load)
        self._shimmer_timer.timeout.connect(self._tick_shimmer)
        # Completion glow pulse
        self._glow_slots: Dict[str, dict] = {}  # task_id → {slots, count, phase}
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(400)  # ★ Fix L: 400ms glow (was 200ms — halves CSS parse load during completion bursts)
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
        # Bug 8: Don't auto-start — start when thumbs registered, stop when empty
        # Round 4 Fix A: Unified completion refresh debounce timer
        # Replaces scattered QTimer.singleShot(500) and _upscale_refresh_timer
        # so N simultaneous completions/upscale phases coalesce into 1 refresh
        self._completion_refresh_timer = QTimer(self)
        self._completion_refresh_timer.setSingleShot(True)
        self._completion_refresh_timer.setInterval(500)  # 500ms debounce
        self._completion_refresh_timer.timeout.connect(self._refresh_queue_from_controller)
        self._background_upscale_refresh_timer = QTimer(self)
        self._background_upscale_refresh_timer.setSingleShot(True)
        # Background upscale churn can emit hundreds of status updates across
        # large queues; coalesce them more aggressively than normal completion.
        self._background_upscale_refresh_timer.setInterval(1000)
        self._background_upscale_refresh_timer.timeout.connect(self._refresh_queue_from_controller)
        self._last_refresh_ts = 0.0  # monotonic timestamp of last actual refresh
        self._refresh_hidden_pending = False
        self._filters_need_reapply = False
        self._force_queue_refresh_pending = False
        # Auto-refresh timer: periodic full queue refresh while engine is running
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(8000)  # every 8s while processing large queues
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh_tick)
        
        self._setup_ui()
        self._register_controller_callbacks()
        self._init_micro_thumb_system()  # ★ Perf: background micro-thumbnail pre-generation
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
        # ★ FIX P1-#1: Register post-queue action check at app level
        if hasattr(self.controller, 'set_queue_complete_callback'):
            self.controller.set_queue_complete_callback(self._check_post_queue_action)    
    
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
        
        status_lower = (status_text or "").lower()
        is_prompt_change = status_text and (
            "✨" in status_text or "🔧" in status_text
        )
        is_upscale_phase = status_text and (
            "⬆️" in status_text or "upscal" in status_lower
        )
        is_download_phase = status_text and "📥" in status_text

        # ★ Fix O1: Per-task progress throttle
        # Background upscale is especially noisy because queued/polling/upscaling
        # status updates arrive for many tasks at once. Throttle those harder
        # than ordinary progress to keep the GUI thread responsive.
        is_completion = progress >= 100
        if not is_completion and not is_prompt_change:
            if not hasattr(self, '_progress_last_ts'):
                self._progress_last_ts = {}
            now = _time.time()
            last = self._progress_last_ts.get(task_id, 0)
            min_gap = 0.5 if is_upscale_phase else (0.25 if is_download_phase else 0.15)
            if now - last < min_gap:
                return  # Skip — too soon since last update for this task
            self._progress_last_ts[task_id] = now
        
        # ★ R6: Single get_all_tasks_dict() call — reuse for both prompt update + thumb effect
        live_task = None
        if self.controller and hasattr(self.controller, '_dispatcher'):
            _all_tasks = self.controller._dispatcher.get_all_tasks_dict()
            live_task = _all_tasks.get(task_id)
        elif self.controller and hasattr(self.controller, 'dispatcher'):
            _all_tasks = self.controller.dispatcher.get_all_tasks_dict()
            live_task = _all_tasks.get(task_id)
        
        # ★ Detect prompt enhance/fix → refresh prompt labels
        if is_prompt_change and hasattr(widget, '_scene_label'):
            if live_task and live_task.prompt:
                new_prompt = live_task.prompt
                dot_pos = new_prompt.find(". ")
                if dot_pos > 0 and dot_pos < 120:
                    scene_name = new_prompt[:dot_pos]
                    detail_text = new_prompt[dot_pos + 2:]
                else:
                    scene_name = new_prompt[:80]
                    detail_text = new_prompt[80:] if len(new_prompt) > 80 else ""
                try:
                    widget._scene_label.setText(scene_name)
                    widget._scene_label.setToolTip(new_prompt)
                    if hasattr(widget, '_detail_label') and widget._detail_label:
                        widget._detail_label.setText(detail_text[:200])
                        widget._detail_label.setToolTip(new_prompt)
                except RuntimeError:
                    pass

        # During download/upscale phase: trigger full refresh so thumb overlays update
        # Round 4 Fix A: Use unified _completion_refresh_timer instead of separate timer
        is_refresh_phase = status_text and (
            is_upscale_phase or "🔄" in status_text or is_download_phase
        )
        if is_refresh_phase and not getattr(self, '_pause_refresh_for_menu', False) and self.isVisible():
            if is_upscale_phase:
                if not self._background_upscale_refresh_timer.isActive():
                    self._background_upscale_refresh_timer.start()
            elif not self._completion_refresh_timer.isActive():
                self._completion_refresh_timer.start()
        
        # Phase 2: Smooth progress interpolation
        smooth_pct = self._get_smooth_progress(task_id, progress) / 100.0
        smooth_pct = max(0.0, min(1.0, smooth_pct))
        
        # Update thumbnail slot gradients via unified _apply_thumb_effect
        if hasattr(widget, 'thumb_slots'):
            # BUG-A3 fix: Get live task status (not stale from widget creation)
            task_status = getattr(widget, '_task_status', 'running')
            # ★ R6: Reuse live_task from single dict call above
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
        # Round 4 Fix A: Use unified debounce timer (coalesces N completions → 1 refresh)
        if progress >= 100 and not getattr(self, '_pause_refresh_for_menu', False) and self.isVisible():
            if not self._completion_refresh_timer.isActive():
                self._completion_refresh_timer.start()
        
        # Update status label
        if hasattr(widget, 'status_label'):
            try:
                live_td = dict(getattr(widget, '_task_snapshot', {}) or {})
                live_td.update({
                    'id': task_id,
                    'status': getattr(widget, '_task_status', live_td.get('status', 'running')),
                    'progress': progress,
                    'status_text': status_text or live_td.get('status_text', ''),
                })

                if live_task:
                    live_td.update({
                        'status': live_task.state.value,
                        'progress': progress,
                        'mode': getattr(live_task, 'workflow_type', live_td.get('mode', 'T2V')) or live_td.get('mode', 'T2V'),
                        'workflow': getattr(live_task, 'workflow_type', live_td.get('mode', 'T2V')) or live_td.get('workflow', live_td.get('mode', 'T2V')),
                        'output_count': getattr(live_task, 'output_count', live_td.get('output_count', 0)),
                        'upscale_status': getattr(live_task, 'upscale_status', live_td.get('upscale_status', '')),
                        'output_files': list(getattr(live_task, 'output_uris', []) or live_td.get('output_files', [])),
                        'image_paths': list(getattr(live_task, 'image_paths', []) or live_td.get('image_paths', [])),
                        'thumbnails': [
                            getattr(vo, 'thumbnail_path', '')
                            for vo in (getattr(live_task, 'video_outputs', []) or [])
                            if getattr(vo, 'thumbnail_path', '')
                        ] or live_td.get('thumbnails', []),
                        'video_outputs': [
                            {
                                'index': getattr(vo, 'index', 0),
                                'quality': getattr(vo, 'quality', ''),
                                'upscale_status': getattr(vo, 'upscale_status', ''),
                                'upscale_error': getattr(vo, 'upscale_error', ''),
                                'best_file': getattr(vo, 'best_file', ''),
                                'border_color': getattr(vo, 'border_color', 'gray'),
                                'thumbnail_path': getattr(vo, 'thumbnail_path', ''),
                            }
                            for vo in (getattr(live_task, 'video_outputs', []) or [])
                        ],
                    })

                self._update_status_label(widget, live_td)
                if self._is_fully_completed_task_data(live_td):
                    self._trigger_completion_glow(task_id)
                    self._smooth_progress.pop(task_id, None)
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

    def _get_dispatcher(self):
        """Return the live dispatcher if the controller exposes one."""
        if not self.controller:
            return None
        dispatcher = getattr(self.controller, 'dispatcher', None)
        if dispatcher is None:
            dispatcher = getattr(self.controller, '_dispatcher', None)
        return dispatcher

    def _get_live_tasks(self) -> List:
        """Read the live task snapshot from dispatcher instead of stale widget caches."""
        dispatcher = self._get_dispatcher()
        if not dispatcher:
            return []
        getter = getattr(dispatcher, 'get_all_tasks_dict', None)
        if callable(getter):
            tasks = getter()
        else:
            tasks = getattr(dispatcher, '_all_tasks', {})
        return list(tasks.values()) if isinstance(tasks, dict) else []

    def _request_immediate_queue_refresh(self):
        """Bypass debounce/cooldown after explicit user actions."""
        if getattr(self, '_pause_refresh_for_menu', False):
            self._force_queue_refresh_pending = True
            self._schedule_throttled_refresh()
            return

        self._force_queue_refresh_pending = False
        self._throttled_refresh_pending = False
        if self._progress_throttle_timer.isActive():
            self._progress_throttle_timer.stop()
        if self._completion_refresh_timer.isActive():
            self._completion_refresh_timer.stop()
        if self._background_upscale_refresh_timer.isActive():
            self._background_upscale_refresh_timer.stop()
        self._last_refresh_ts = 0.0
        self._refresh_queue_from_controller(force=True)
    
    # ── Throttled Refresh ────────────────────────────────────────
    
    def _schedule_throttled_refresh(self):
        """Debounce queue refresh — merge multiple updates within a 500ms window."""
        self._throttled_refresh_pending = True
        if not self._progress_throttle_timer.isActive():
            self._progress_throttle_timer.start()
    
    def _flush_throttled_refresh(self):
        """Execute throttled refresh if pending."""
        if self._throttled_refresh_pending:
            # Skip refresh while context menu is open to prevent widget rebuild
            if getattr(self, '_pause_refresh_for_menu', False):
                return  # Will be picked up by next throttle cycle
            force_refresh = self._force_queue_refresh_pending
            self._throttled_refresh_pending = False
            self._force_queue_refresh_pending = False
            self._refresh_queue_from_controller(force=force_refresh)
    
    def _on_auto_refresh_tick(self):
        """Periodic queue refresh while engine is running (every 8s)."""
        # Bug 10: Skip refresh when Queue tab is not visible
        if not self.isVisible():
            return
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
    
    def _on_scroll_viewport_changed(self):
        """★ Perf: Refresh thumbnails for rows that just scrolled into view.
        
        Called 150ms after scroll stops (debounced). Iterates task widgets
        and loads thumbnails only for newly-visible rows that were previously
        skipped by viewport culling.
        """
        if not self.isVisible():
            return
        if getattr(self, '_pause_refresh_for_menu', False):
            return
        
        for tid, widget in self._task_widgets.items():
            try:
                if not _is_widget_alive(widget):
                    continue
                if not self._is_widget_in_viewport(widget):
                    continue
                # Check if this widget needs a deferred thumb refresh
                if getattr(widget, '_needs_thumb_refresh', False):
                    widget._needs_thumb_refresh = False
                    if hasattr(widget, 'thumb_slots'):
                        # Get live data from controller
                        td = self._get_live_task_data(tid)
                        if td:
                            self._update_thumb_slot_data(widget, td)
            except RuntimeError:
                continue
        if hasattr(self, '_refresh_virtualized_groups_in_viewport'):
            self._refresh_virtualized_groups_in_viewport()
    
    def _get_live_task_data(self, task_id: str) -> dict:
        """★ R2: O(1) lookup from cached task data index (built during _refresh_groups)."""
        idx = getattr(self, '_task_data_index', None)
        if idx:
            return idx.get(task_id)
        # Fallback: full scan (only if _task_data_index not yet built)
        if not self.controller or not hasattr(self.controller, 'get_queue_groups'):
            return None
        try:
            for group in self.controller.get_queue_groups():
                for td in group.get('tasks', []):
                    if str(td.get('id', '')) == task_id:
                        return td
        except Exception:
            pass
        return None
    
    def _tick_input_pulse(self):
        """BUG-A8 fix: Animate input thumbnails border (I2V/R2V modes)."""
        # ★ Fix L: Skip animation when Queue tab is hidden
        if not self.isVisible():
            return
        if not self._input_pulse_thumbs:
            # Bug 8: Stop timer when no thumbs to animate
            self._input_pulse_timer.stop()
            return
        self._input_pulse_phase = not self._input_pulse_phase
        bright = Theme.BLUE
        dim = "#3a4a6a"  # Muted blue
        border_color = bright if self._input_pulse_phase else dim
        alive = []
        pulse_key = self._input_pulse_phase
        for thumb in self._input_pulse_thumbs:
            try:
                # ★ Fix L2: Skip hidden thumbs (collapsed group)
                if not thumb.isVisible():
                    continue
                # R6-A: Skip redundant setStyleSheet if phase unchanged for this thumb
                if getattr(thumb, '_last_pulse_key', None) == pulse_key:
                    alive.append(thumb)
                    continue
                thumb._last_pulse_key = pulse_key
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
        # Bug 8: Stop timer when all thumbs have been GC'd
        if not alive:
            self._input_pulse_timer.stop()
    
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
        self.status_filter.setMinimumWidth(160)
        self.status_filter.addItems([
            t("queue_extra.all_status"),
            t("queue_extra.status_pending"),
            t("queue_extra.status_processing"),
            t("queue_extra.status_upscaling"),
            t("queue_extra.status_completed"),
            t("queue_extra.status_failed"),
            t("queue_extra.status_cancelled"),
            t("queue_extra.status_partial_failed"),
        ])
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
        if self._suspend_filter_changes:
            return
        sender = self.sender()
        self._schedule_filter_apply(immediate=(sender is not self.search_input))
    
    def _on_toggle_all_groups(self):
        """Toggle expand/collapse ALL groups at once."""
        if not self._group_widgets:
            return
        target_group_ids = [
            gid for gid, gw in self._group_widgets.items()
            if not self._has_active_filters() or not gw['container'].isHidden()
        ]
        if not target_group_ids:
            return

        any_expanded = any(self._group_expanded.get(gid, True) for gid in target_group_ids)
        new_state = not any_expanded

        self._cancel_bulk_group_materialize()
        timer = getattr(self, '_auto_refresh_timer', None)
        timer_was_active = bool(timer and timer.isActive())
        if timer_was_active:
            timer.stop()
        queue_container = getattr(self, 'queue_container', None)
        try:
            if queue_container:
                queue_container.setUpdatesEnabled(False)

            if not new_state:
                for gid in target_group_ids:
                    gw = self._group_widgets.get(gid)
                    if not gw:
                        continue
                    self._group_expanded[gid] = False
                    gw['arrow'].setText("▶")
                    gw['content'].setVisible(False)
            else:
                deferred_materialize = []
                for gid in target_group_ids:
                    gw = self._group_widgets.get(gid)
                    if not gw:
                        continue
                    self._group_expanded[gid] = True
                    gw['arrow'].setText("▼")
                    if gw.get('_lazy_pending') or gw.get('_dirty'):
                        gw['content'].setVisible(False)
                        deferred_materialize.append(gid)
                    else:
                        gw['content'].setVisible(True)

                if deferred_materialize:
                    self._bulk_group_materialize_queue = deferred_materialize
                    self._bulk_group_materialize_active = True
                    self._bulk_group_resume_refresh = timer_was_active
                    self._bulk_group_materialize_timer.start()
        finally:
            if queue_container:
                queue_container.setUpdatesEnabled(True)
                queue_container.update()
            if not new_state and timer_was_active and timer:
                timer.start()

        self._update_toggle_all_button_state(target_group_ids)
        if self._has_active_filters():
            self._schedule_filter_apply(immediate=True)
    
    def _has_active_filters(self) -> bool:
        """★ P2: Check if any filter is active (non-default)."""
        if self.project_filter.currentIndex() != 0:
            return True
        if self.status_filter.currentIndex() != 0:
            return True
        if self.mode_filter.currentIndex() != 0:
            return True
        if self.search_input.text().strip():
            return True
        return False

    def _schedule_filter_apply(self, immediate: bool = False):
        """Apply filters immediately or via short debounce for search typing."""
        if self._suspend_filter_changes:
            return
        if immediate:
            if self._filter_apply_timer.isActive():
                self._filter_apply_timer.stop()
            self._apply_filters()
        else:
            self._filter_apply_timer.start()

    def _sync_project_filter_options(self, projects: List[str]):
        """Rebuild project filter from live queue data while preserving selection."""
        normalized = ["All Projects"]
        seen = {"All Projects"}
        for project in projects:
            value = (project or "").strip() or "Default"
            if value in seen:
                continue
            normalized.append(value)
            seen.add(value)

        if normalized == self._projects:
            return

        current_text = self.project_filter.currentText() if hasattr(self, 'project_filter') else "All Projects"
        self._projects = normalized
        self._suspend_filter_changes = True
        previous_block = self.project_filter.blockSignals(True)
        try:
            self.project_filter.clear()
            self.project_filter.addItems(self._projects)
            current_index = self.project_filter.findText(current_text)
            self.project_filter.setCurrentIndex(current_index if current_index >= 0 else 0)
        finally:
            self.project_filter.blockSignals(previous_block)
            self._suspend_filter_changes = False

    def _task_filter_signature(self, task_data: Optional[dict]):
        """Return only the fields that can change filter visibility."""
        if not isinstance(task_data, dict):
            return None
        video_outputs = task_data.get('video_outputs', []) or []
        video_sig = tuple(
            (
                str(vo.get('quality', '') or ''),
                str(vo.get('upscale_status', '') or ''),
                str(vo.get('upscale_error', '') or ''),
            )
            for vo in video_outputs
            if isinstance(vo, dict)
        )
        return (
            str(task_data.get('project', '') or ''),
            str(task_data.get('status', '') or ''),
            str(task_data.get('mode', '') or ''),
            str(task_data.get('prompt', '') or ''),
            str(task_data.get('stage', '') or ''),
            str(task_data.get('upscale_status', '') or ''),
            bool(task_data.get('is_upscaling')),
            video_sig,
        )

    def _build_filter_context(self) -> dict:
        """Collect filter state once so grouped/flat paths reuse the same rules."""
        status_idx = self.status_filter.currentIndex()
        is_partial_failed_filter = (status_idx == 7)
        is_upscaling_filter = (status_idx == 3)
        partial_failed_ids = set()
        upscaling_ids = set()
        if is_partial_failed_filter:
            task_data_idx = getattr(self, '_task_data_index', {})
            for tid, td in task_data_idx.items():
                if self._is_partial_failed_task_data(td):
                    partial_failed_ids.add(tid)
        if is_upscaling_filter or status_idx == 2:
            task_data_idx = getattr(self, '_task_data_index', {})
            for tid, td in task_data_idx.items():
                if self._is_task_data_upscaling(td):
                    upscaling_ids.add(tid)

        return {
            'project_idx': self.project_filter.currentIndex(),
            'project': self.project_filter.currentText(),
            'status_idx': status_idx,
            'allowed_statuses': {
                1: {"pending", "waiting", "ready"},
                2: {"running", "waiting_poll"},
                4: {"completed"},
                5: {"failed"},
                6: {"cancelled"},
            }.get(status_idx),
            'is_partial_failed_filter': is_partial_failed_filter,
            'partial_failed_ids': partial_failed_ids,
            'is_upscaling_filter': is_upscaling_filter,
            'upscaling_ids': upscaling_ids,
            'selected_mode': self.mode_filter.currentData(),
            'search': self.search_input.text().strip().lower(),
            'has_filters': self._has_active_filters(),
        }

    def _is_task_data_upscaling(self, task_data: dict) -> bool:
        """Decide whether a Queue DTO represents active upscale work."""
        if not isinstance(task_data, dict):
            return False
        if bool(task_data.get('is_upscaling')):
            return True
        stage = str(task_data.get('stage', '') or '').lower()
        active_upscale_statuses = {'submitting', 'polling', 'pending', 'retrying'}
        upscale_lifecycle_stages = {'downloaded_720', 'upscaling', 'upscaled', 'completed'}
        if stage == 'upscaling':
            return True
        if stage not in upscale_lifecycle_stages:
            return False
        video_outputs = task_data.get('video_outputs', []) or []
        if any(
            str(vo.get('upscale_status', '') or '').lower() in active_upscale_statuses
            for vo in video_outputs
            if isinstance(vo, dict)
        ):
            return True
        overall = str(task_data.get('upscale_status', '') or '').lower()
        return overall in active_upscale_statuses

    def _task_matches_filters(self, task_data: dict, item_lookup: Dict[str, QueueItem], ctx: dict, group_data: dict = None) -> bool:
        """Evaluate one task against the active filter set."""
        tid = str(task_data.get('id', ''))
        item = item_lookup.get(tid)
        group_data = group_data or {}

        project_name = (
            task_data.get('project')
            or group_data.get('project_name')
            or getattr(item, 'project', '')
            or group_data.get('name')
            or "Default"
        )
        status = task_data.get('status') or getattr(item, 'status', '')
        mode = task_data.get('mode') or getattr(item, 'mode', 'T2V')
        prompt = task_data.get('prompt') or getattr(item, 'prompt', '')

        if ctx['project_idx'] != 0 and project_name != ctx['project']:
            return False
        if ctx.get('is_upscaling_filter'):
            if tid not in ctx.get('upscaling_ids', set()):
                return False
        elif ctx['is_partial_failed_filter']:
            if tid not in ctx['partial_failed_ids']:
                return False
        elif ctx['allowed_statuses'] is not None and status not in ctx['allowed_statuses']:
            return False
        if ctx['selected_mode'] and ctx['selected_mode'] != "ALL" and mode != ctx['selected_mode']:
            return False
        prompt_lc = (
            getattr(self, '_task_prompt_lc_index', {}).get(tid)
            or str(prompt or '').lower()
        )
        if ctx['search'] and ctx['search'] not in prompt_lc:
            return False
        # Exclude upscaling tasks from Processing filter (index 2)
        if ctx.get('status_idx') == 2 and tid in ctx.get('upscaling_ids', set()):
            return False
        return True

    def _update_toggle_all_button_state(self, visible_group_ids: Optional[List[str]] = None):
        """Keep the expand/collapse-all icon aligned with the visible groups."""
        if not hasattr(self, '_toggle_all_btn'):
            return
        group_ids = visible_group_ids if visible_group_ids is not None else list(self._group_widgets.keys())
        if not group_ids:
            self._toggle_all_btn.setText("▶")
            return
        any_expanded = any(self._group_expanded.get(gid, True) for gid in group_ids)
        self._toggle_all_btn.setText("▼" if any_expanded else "▶")

    def _cancel_bulk_group_materialize(self):
        """Cancel any in-flight bulk expand materialization queue."""
        if self._bulk_group_materialize_timer.isActive():
            self._bulk_group_materialize_timer.stop()
        self._bulk_group_materialize_queue.clear()
        self._bulk_group_materialize_active = False
        self._bulk_group_resume_refresh = False

    def _process_bulk_group_materialize(self):
        """Materialize heavy expand-all groups sequentially to avoid UI stalls."""
        if not self._bulk_group_materialize_queue:
            if self._bulk_group_resume_refresh and hasattr(self, '_auto_refresh_timer'):
                self._auto_refresh_timer.start()
            self._bulk_group_materialize_active = False
            self._bulk_group_resume_refresh = False
            return

        group_id = self._bulk_group_materialize_queue.pop(0)
        self._set_group_expanded_state(
            group_id,
            True,
            manage_refresh_timer=False,
            force_refresh=True,
        )

        if self._bulk_group_materialize_queue:
            self._bulk_group_materialize_timer.start()
        else:
            if self._bulk_group_resume_refresh and hasattr(self, '_auto_refresh_timer'):
                self._auto_refresh_timer.start()
            self._bulk_group_materialize_active = False
            self._bulk_group_resume_refresh = False

    def _apply_filters(self):
        """Apply filters to both rows and group containers."""
        ctx = self._build_filter_context()
        item_lookup = getattr(self, '_queue_item_index', {})
        queue_container = getattr(self, 'queue_container', None)

        if queue_container:
            queue_container.setUpdatesEnabled(False)
        try:
            if not self._group_widgets:
                for item in self._queue_items:
                    widget = self._task_widgets.get(str(item.id)) or self._item_widgets.get(item.id)
                    if widget is None:
                        continue
                    task_data = self._get_live_task_data(str(item.id)) or {
                        'id': item.id,
                        'prompt': item.prompt,
                        'status': item.status,
                        'mode': item.mode,
                        'project': item.project,
                    }
                    widget.setVisible(self._task_matches_filters(task_data, item_lookup, ctx))
                self._filters_need_reapply = False
                return

            visible_group_ids = []
            for gid, gw in self._group_widgets.items():
                group_data = gw.get('group_data', {})
                group_tasks = group_data.get('tasks', [])
                if ctx['has_filters']:
                    matching_ids = {
                        str(td['id'])
                        for td in group_tasks
                        if self._task_matches_filters(td, item_lookup, ctx, group_data)
                    }
                else:
                    matching_ids = {str(td['id']) for td in group_tasks}

                gw['_filter_visible_task_ids'] = matching_ids
                group_visible = bool(matching_ids)
                gw['container'].setVisible(group_visible)

                if not group_visible:
                    gw['content'].setVisible(False)
                    continue

                visible_group_ids.append(gid)
                expanded = self._group_expanded.get(gid, True)
                gw['arrow'].setText("▼" if expanded else "▶")
                gw['content'].setVisible(expanded)

                if gw.get('_lazy_pending'):
                    continue

                if gw.get('_virtualized'):
                    self._refresh_virtualized_group(gw, group_data, force=True)
                    continue

                for td in group_tasks:
                    task_widget = self._task_widgets.get(str(td['id']))
                    if task_widget is not None:
                        task_widget.setVisible(str(td['id']) in matching_ids)

            self._update_toggle_all_button_state(visible_group_ids)
        finally:
            if queue_container:
                queue_container.setUpdatesEnabled(True)
                queue_container.update()
        self._filters_need_reapply = False
    
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
        # ★ FIX: Use index-based init (locale-safe, no English/Vietnamese mismatch)
        _action_index = {"nothing": 0, "shutdown": 1, "sleep": 2}
        saved_idx = _action_index.get(getattr(_s, 'post_queue_action', 'nothing'), 0)
        
        self.post_queue_combo = QComboBox()
        self.post_queue_combo.addItems([t("queue_extra.do_nothing"), t("queue_extra.shutdown"), t("queue_extra.sleep")])
        self.post_queue_combo.setCurrentIndex(saved_idx)
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

        # Clean Completed — remove fully-completed tasks (no failed videos)
        self.clean_completed_btn = QPushButton("Clean ✓")
        self.clean_completed_btn.setProperty("variant", "secondary")
        self.clean_completed_btn.setToolTip(
            "Remove fully completed tasks (all videos OK).\n"
            "Tasks with failed/retrying videos are preserved."
        )
        self.clean_completed_btn.clicked.connect(self._on_clean_completed)
        layout.addWidget(self.clean_completed_btn)
        
        # Delete All
        self.delete_all_btn = QPushButton(t("queue.delete_all"))
        self.delete_all_btn.setProperty("variant", "danger")
        self.delete_all_btn.setToolTip(t("queue_extra.delete_all_tooltip"))
        self.delete_all_btn.clicked.connect(self._on_delete_all)
        layout.addWidget(self.delete_all_btn)

        # 🔍 Find & Replace — opens global search dialog
        self._find_btn = QPushButton("🔍 Find")
        self._find_btn.setMinimumWidth(70)
        self._find_btn.setProperty("variant", "secondary")
        self._find_btn.setToolTip("Find & Replace (Ctrl+H)")
        self._find_btn.clicked.connect(self._on_open_find_replace)
        layout.addWidget(self._find_btn)
        
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
            ("Actions", 200, 0, True),
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
        
        # ★ Perf: Scroll-triggered viewport-aware loading
        self._scroll_area = scroll
        self._scroll_refresh_timer = QTimer(self)
        self._scroll_refresh_timer.setSingleShot(True)
        self._scroll_refresh_timer.setInterval(150)  # 150ms debounce
        self._scroll_refresh_timer.timeout.connect(self._on_scroll_viewport_changed)
        scroll.verticalScrollBar().valueChanged.connect(
            lambda _: self._scroll_refresh_timer.start() if not self._scroll_refresh_timer.isActive() else None
        )
        
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
    
    def _on_open_find_replace(self):
        """Open Find & Replace dialog via MainWindow."""
        win = self.window()
        if hasattr(win, '_toggle_search'):
            win._toggle_search(replace=True)
    
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
        
        # ★ R3: Override border color for completed tasks with active upscale
        border_color = cfg['color']
        if item.status == "completed" and task_data:
            video_outputs = task_data.get('video_outputs', [])
            us = task_data.get('upscale_status', '')
            has_upscaling = any(
                vo.get('upscale_status') in ('submitting', 'polling')
                for vo in video_outputs
            ) or us in ('submitting', 'polling')
            has_upscale_fail = any(
                vo.get('upscale_status') == 'failed'
                for vo in video_outputs
            ) or us == 'failed'
            has_retrying = any(
                vo.get('quality') == 'retrying'
                for vo in video_outputs
            )
            if has_retrying or has_upscaling:
                border_color = Theme.PURPLE
            elif has_upscale_fail:
                border_color = Theme.YELLOW
        
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
                border-left: 3px solid {border_color};
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
        prompt_widget.setMinimumWidth(0)
        # ★ R5: QSizePolicy now imported at module level
        prompt_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        prompt_layout_v = QVBoxLayout(prompt_widget)
        prompt_layout_v.setContentsMargins(0, 2, 0, 2)
        prompt_layout_v.setSpacing(1)
        
        # Line 1: Scene name (bold, prominent) — clipped to available width
        scene_label = QLabel(scene_name)
        scene_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; font-weight: bold; border: none;")
        scene_label.setToolTip(full_prompt)
        scene_label.setMinimumWidth(0)
        scene_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        prompt_layout_v.addWidget(scene_label)
        
        # Line 2: Remaining detail (smaller, muted) — clipped to available width
        if detail_text:
            detail_label = QLabel(detail_text[:200])
            detail_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px; border: none;")
            detail_label.setToolTip(full_prompt)
            detail_label.setMinimumWidth(0)
            detail_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            prompt_layout_v.addWidget(detail_label)
        
        layout.addWidget(prompt_widget, stretch=1)
        # ★ Store prompt label refs for live updates (enhance/fix)
        widget._scene_label = scene_label
        widget._detail_label = detail_label if detail_text else None
        
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
        status_label = QLabel("")
        status_label.setFixedWidth(120)
        status_label.setAlignment(Qt.AlignCenter)
        widget.status_label = status_label
        layout.addWidget(status_label)

        status_td = dict(task_data) if task_data else {}
        status_td.setdefault('id', str(item.id))
        status_td.setdefault('status', item.status)
        status_td.setdefault('progress', item.progress)
        status_td.setdefault('mode', item.mode)
        status_td.setdefault('workflow', item.mode)
        status_td.setdefault('output_count', output_count)
        status_td.setdefault('thumbnails', thumbnails)
        status_td.setdefault('output_files', output_files)
        status_td.setdefault('video_outputs', video_outputs)
        self._update_status_label(widget, status_td)
        
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
        actions_wrapper.setFixedWidth(200)
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
    
    def _refresh_queue_from_controller(self, force: bool = False):
        """Refresh queue from controller using hierarchical group data.
        
        Round 4 Fix B: 1s cooldown guard prevents rapid-fire rebuilds.
        If called within cooldown, defers via _completion_refresh_timer unless forced.
        """
        if not self.controller:
            return

        if not self.isVisible():
            self._refresh_hidden_pending = True
            return
        self._refresh_hidden_pending = False
        
        # Adaptive cooldown: scale with queue size to keep main thread responsive.
        # Tiny queues refresh instantly; mega queues (5M+) only every 30s.
        now = _time.monotonic()
        _q_size = len(self._queue_items) or 0
        if _q_size > 50_000:
            cooldown_window = 30.0
        elif _q_size > 5_000:
            cooldown_window = 10.0 if self._is_processing else 5.0
        elif _q_size > 1_000:
            cooldown_window = 5.0 if self._is_processing else 3.0
        elif _q_size > 200:
            cooldown_window = 3.0 if self._is_processing else 2.0
        else:
            cooldown_window = 2.0 if self._is_processing else 1.0
        if not force and (now - self._last_refresh_ts) < cooldown_window:
            # Too soon — schedule deferred refresh
            if not self._completion_refresh_timer.isActive():
                remaining_ms = int((cooldown_window - (now - self._last_refresh_ts)) * 1000)
                self._completion_refresh_timer.start(max(50, remaining_ms))
            return
        self._last_refresh_ts = now
        
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
            # ★ R5: logging now imported at module level
            _qlog = logging.getLogger("veo.tab_queue")
            total_tasks = sum(len(g.get('tasks', [])) for g in groups_data)
            _qlog.debug(f"[QueueRefresh] {len(groups_data)} groups, {total_tasks} total tasks, existing_groups={list(self._group_widgets.keys())}")
            self._refresh_groups(groups_data)
        elif hasattr(self.controller, 'get_queue_items'):
            # Fallback to flat items
            self._refresh_flat_items()
        
        self._update_stats()
        self._update_toggle_all_button_state()
        if self._has_active_filters() and self._filters_need_reapply:
            self._schedule_filter_apply(immediate=False)
        self._update_button_states()

    def showEvent(self, event):
        """Catch up one deferred refresh when the Queue tab becomes visible again."""
        super().showEvent(event)
        self._restart_animation_timers()
        if self._refresh_hidden_pending:
            self._refresh_hidden_pending = False
            # ★ Perf: 150ms delay — let tab paint its frame first before
            # heavy DTO rebuild + widget refresh hits the GUI thread.
            QTimer.singleShot(150, self._refresh_queue_from_controller)

    def hideEvent(self, event):
        """Stop animation timers while the Queue tab is hidden."""
        for timer_name in (
            '_shimmer_timer',
            '_glow_timer',
            '_upscale_spinner_timer',
            '_input_pulse_timer',
        ):
            timer = getattr(self, timer_name, None)
            if timer and timer.isActive():
                timer.stop()
        super().hideEvent(event)

    def _restart_animation_timers(self):
        """Resume only the animation timers that still have live work."""
        if not self.isVisible():
            return
        if self._shimmer_active_slots and not self._shimmer_timer.isActive():
            self._shimmer_timer.start()
        if self._glow_slots and not self._glow_timer.isActive():
            self._glow_timer.start()
        if self._upscale_spinner_slots and not self._upscale_spinner_timer.isActive():
            self._upscale_spinner_timer.start()
        if self._input_pulse_thumbs and not self._input_pulse_timer.isActive():
            self._input_pulse_timer.start()
    
    def _refresh_groups(self, groups_data: list):
        """Refresh hierarchical group → prompt row view."""
        current_group_ids = {g['id'] for g in groups_data}
        previous_projects = tuple(self._projects)
        previous_task_data_index = getattr(self, '_task_data_index', {})
        filters_active = self._has_active_filters()
        filters_need_reapply = False
        self._sync_project_filter_options([
            g.get('project_name') or g.get('name') or "Default"
            for g in groups_data
        ])
        if filters_active and tuple(self._projects) != previous_projects:
            filters_need_reapply = True
        
        # Remove stale groups
        stale = [gid for gid in self._group_widgets if gid not in current_group_ids]
        if filters_active and stale:
            filters_need_reapply = True
        for gid in stale:
            gw = self._group_widgets.pop(gid)
            gw['container'].deleteLater()
            self._group_expanded.pop(gid, None)
            self._pending_group_rebuilds.pop(gid, None)
        
        # Update or create groups
        # ★ P1: Don't clear — prune stale items after loop instead
        # self._queue_items.clear()  # REMOVED — causes 200+ re-allocations
        
        # Update or create groups
        # ★ P1: Don't clear — prune stale items after loop instead
        # self._queue_items.clear()  # REMOVED — causes 200+ re-allocations
        self._item_widgets.clear()
        all_task_ids = set()
        # ★ R1: Build dict index for O(1) QueueItem lookup (replaces O(N) list scan)
        qi_index = {str(qi.id): qi for qi in self._queue_items}
        # ★ R2: Build task data index for O(1) _get_live_task_data
        task_data_index = {}
        task_prompt_lc_index = {}
        
        # Lazy-load: skip child widget creation for large queues on first load
        total_tasks = sum(len(g.get('tasks', [])) for g in groups_data)
        use_lazy = total_tasks > 50
        
        for g in groups_data:
            gid = g['id']
            group_project = g.get('project_name') or g.get('name') or "Default"
            
            if gid in self._group_widgets:
                # Update existing group
                gw = self._group_widgets[gid]
                self._update_group_header(gw['header'], g)
                # Update stored group_data for lazy groups
                gw['group_data'] = g
                if gw.get('_lazy_pending'):
                    # Skip child rebuild — not yet materialized
                    pass
                elif not self._group_expanded.get(gid, total_tasks <= 50):
                    # ★ v2: Default collapsed for large queues (>50 tasks)
                    gw['_dirty'] = True  # Mark for catch-up on expand
                else:
                    # Differential rebuild children (group is expanded)
                    gw['_dirty'] = False
                    _group_size = len(g.get('tasks', []))
                    if _group_size > 100:
                        # Always async for 100+ tasks — prevents main-thread freeze
                        self._schedule_group_children_rebuild(gw, g, delay_ms=0)
                    else:
                        self._rebuild_group_children(gw, g)
            else:
                # Create new group
                if use_lazy:
                    # Large queue: start collapsed, defer child creation
                    expanded = self._group_expanded.get(gid, False)
                    container = self._create_group_widget(g, expanded=expanded, lazy=not expanded)
                else:
                    expanded = self._group_expanded.get(gid, True)
                    container = self._create_group_widget(g, expanded)
                self._group_expanded[gid] = expanded
                self.queue_layout.insertWidget(
                    self.queue_layout.count() - 1, container
                )
                if filters_active:
                    filters_need_reapply = True
            
            # Track items for stats + collect all task IDs
            # ★ v2: For mega queues (>10K), skip QueueItem list — use dict index only
            _skip_qi_list = total_tasks > 10_000
            for td in g.get('tasks', []):
                tid_str = str(td['id'])
                all_task_ids.add(tid_str)
                normalized_td = dict(td)
                normalized_td.setdefault('project', group_project)
                # ★ R2: Build task data index for O(1) _get_live_task_data
                task_data_index[tid_str] = normalized_td
                task_prompt_lc_index[tid_str] = str(normalized_td.get('prompt', '') or '').lower()
                if filters_active:
                    if self._task_filter_signature(previous_task_data_index.get(tid_str)) != self._task_filter_signature(normalized_td):
                        filters_need_reapply = True
                # ★ R1: O(1) dict lookup instead of O(N) list scan
                if not _skip_qi_list:
                    existing_qi = qi_index.get(tid_str)
                    if existing_qi:
                        existing_qi.prompt = normalized_td['prompt']
                        existing_qi.status = normalized_td['status']
                        existing_qi.progress = normalized_td['progress']
                        existing_qi.mode = normalized_td.get('mode', 'T2V')
                        existing_qi.project = group_project
                    else:
                        item = QueueItem(
                            id=normalized_td['id'], prompt=normalized_td['prompt'],
                            status=normalized_td['status'], progress=normalized_td['progress'],
                            mode=normalized_td.get('mode', 'T2V'),
                            project=group_project,
                        )
                        self._queue_items.append(item)
                        qi_index[tid_str] = item  # Keep index in sync
        
        # ★ R2: Store task data index for O(1) lookups in _get_live_task_data
        self._task_data_index = task_data_index
        self._task_prompt_lc_index = task_prompt_lc_index

        # Prune stale entries from _task_widgets, _smooth_progress, and _queue_items
        stale_tids = [tid for tid in self._task_widgets if tid not in all_task_ids]
        for tid in stale_tids:
            self._task_widgets.pop(tid, None)
            self._smooth_progress.pop(tid, None)
        if filters_active and (set(previous_task_data_index.keys()) - all_task_ids):
            filters_need_reapply = True
        # ★ R1: Prune stale QueueItems
        self._queue_items = [qi for qi in self._queue_items if str(qi.id) in all_task_ids]
        self._queue_item_index = {str(qi.id): qi for qi in self._queue_items}
        self._filters_need_reapply = filters_need_reapply
        
        self._latest_groups_data = groups_data
        time_metrics = self._compute_queue_time_metrics(groups_data)
        self._queue_eta_seconds = float(time_metrics.get('eta_seconds', 0.0) or 0.0)
        total_elapsed = float(time_metrics.get('elapsed_seconds', 0.0) or 0.0)
        if total_elapsed > 0:
            self.total_time_label.setText(
                f"⏱ Total: {self._format_time_compact(total_elapsed)}"
            )
        else:
            self.total_time_label.setText(t("queue_extra.total_time"))
    
    def _refresh_flat_items(self):
        """Fallback: refresh using flat item list (no groups)."""
        self._latest_groups_data = []
        self._queue_eta_seconds = None
        items_data = self.controller.get_queue_items()
        previous_projects = tuple(self._projects)
        previous_task_data_index = getattr(self, '_task_data_index', {})
        filters_active = self._has_active_filters()
        filters_need_reapply = False
        self._sync_project_filter_options([d.get('project', 'Default') for d in items_data])
        if filters_active and tuple(self._projects) != previous_projects:
            filters_need_reapply = True
        controller_ids = {str(d['id']) for d in items_data}
        item_index = {str(item.id): item for item in self._queue_items}
        task_data_index = {}
        task_prompt_lc_index = {}
        
        stale_ids = [iid for iid in list(self._item_widgets.keys()) if str(iid) not in controller_ids]
        if filters_active and stale_ids:
            filters_need_reapply = True
        for iid in stale_ids:
            widget = self._item_widgets.pop(iid, None)
            if widget:
                widget.deleteLater()
        stale_id_strs = {str(s) for s in stale_ids}
        self._queue_items = [i for i in self._queue_items if str(i.id) not in stale_id_strs]
        for stale_id in stale_id_strs:
            item_index.pop(stale_id, None)
        
        for d in items_data:
            tid = str(d['id'])
            task_data_index[tid] = d
            task_prompt_lc_index[tid] = str(d.get('prompt', '') or '').lower()
            if filters_active:
                if self._task_filter_signature(previous_task_data_index.get(tid)) != self._task_filter_signature(d):
                    filters_need_reapply = True
            item = item_index.get(tid)
            if item:
                changed = (
                    item.status != d['status']
                    or item.progress != d['progress']
                    or item.prompt != d['prompt']
                    or item.mode != d.get('mode', 'T2V')
                    or item.project != d.get('project', 'Default')
                )
                item.prompt = d['prompt']
                item.status = d['status']
                item.progress = d['progress']
                item.mode = d.get('mode', 'T2V')
                item.project = d.get('project', 'Default')
                if changed:
                    self._refresh_item_widget(item)
            else:
                item = QueueItem(
                    id=d['id'], prompt=d['prompt'],
                    status=d['status'], progress=d['progress'],
                    mode=d.get('mode', 'T2V'),
                    project=d.get('project', 'Default'),
                )
                if item.project not in self._projects:
                    self._projects.append(item.project)
                    self.project_filter.addItem(item.project)
                self._add_queue_item(item)
                item_index[tid] = item
                if filters_active:
                    filters_need_reapply = True
        self._task_data_index = task_data_index
        self._task_prompt_lc_index = task_prompt_lc_index
        self._queue_item_index = {str(item.id): item for item in self._queue_items}
        self._filters_need_reapply = filters_need_reapply
    
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
        self._queue_item_index[str(item.id)] = item
        widget = self._create_queue_item_widget(item)
        self._item_widgets[item.id] = widget
        self.queue_layout.insertWidget(self.queue_layout.count() - 1, widget)
    
    def _parse_queue_datetime(self, value, default=None):
        """Parse datetime values from DTO payloads."""
        if isinstance(value, _dt):
            return value
        if isinstance(value, str):
            try:
                return _dt.fromisoformat(value)
            except (TypeError, ValueError):
                return default
        return default
    
    def _format_time_compact(self, seconds: float, default: str = "--:--") -> str:
        """Format seconds into a compact human-readable label."""
        if seconds is None or seconds <= 0:
            return default
        total = max(0, int(seconds))
        if total >= 3600:
            return f"{total // 3600}h {(total % 3600) // 60:02d}m"
        if total >= 60:
            return f"{total // 60:02d}:{total % 60:02d}"
        return f"{total}s"
    
    def _compute_queue_time_metrics(self, groups_data: list) -> dict:
        """Compute wall-clock elapsed + ETA without double-counting concurrency."""
        now_ts = _dt.now()
        overall_starts = []
        overall_ends = []
        overall_completed = 0
        overall_remaining = 0
        overall_processing = 0
        group_metrics = []
        
        for group in groups_data:
            tasks = group.get('tasks', []) or []
            group_starts = []
            group_ends = []
            group_completed = 0
            group_remaining = 0
            group_processing = 0
            
            for td in tasks:
                status = str(td.get('status', '') or '').lower()
                if status == "completed":
                    group_completed += 1
                    overall_completed += 1
                elif status not in ("failed", "cancelled"):
                    group_remaining += 1
                    overall_remaining += 1
                    if status in ("running", "waiting_poll"):
                        group_processing += 1
                        overall_processing += 1
                
                started_at = self._parse_queue_datetime(td.get('started_at'))
                if not started_at:
                    continue
                completed_at = self._parse_queue_datetime(td.get('completed_at'), now_ts) or now_ts
                group_starts.append(started_at)
                group_ends.append(completed_at)
                overall_starts.append(started_at)
                overall_ends.append(completed_at)
            
            group_elapsed = float(group.get('elapsed_seconds', 0) or 0.0)
            if group_starts:
                group_elapsed = max(
                    group_elapsed,
                    (max(group_ends) - min(group_starts)).total_seconds(),
                )
            group_rate = (
                (group_completed / group_elapsed)
                if group_completed > 0 and group_elapsed > 0
                else 0.0
            )
            group_metrics.append({
                "remaining": group_remaining,
                "processing": group_processing,
                "elapsed": group_elapsed,
                "rate": group_rate,
            })
        
        overall_elapsed = (
            (max(overall_ends) - min(overall_starts)).total_seconds()
            if overall_starts else 0.0
        )
        overall_rate = (
            (overall_completed / overall_elapsed)
            if overall_completed > 0 and overall_elapsed > 0
            else 0.0
        )
        
        for idx, group in enumerate(groups_data):
            gm = group_metrics[idx]
            eta_seconds = 0.0
            if gm["remaining"] > 0:
                if gm["rate"] > 0:
                    eta_seconds = gm["remaining"] / gm["rate"]
                elif overall_rate > 0:
                    eta_seconds = gm["remaining"] / overall_rate
                else:
                    eta_seconds = (gm["remaining"] * 90.0) / max(1, gm["processing"])
            group["elapsed_seconds"] = gm["elapsed"]
            group["eta_seconds"] = eta_seconds
        
        queue_eta = 0.0
        if overall_remaining > 0:
            if overall_rate > 0:
                queue_eta = overall_remaining / overall_rate
            else:
                queue_eta = (overall_remaining * 90.0) / max(1, overall_processing)
        
        return {
            "elapsed_seconds": overall_elapsed,
            "eta_seconds": queue_eta,
        }
    
    def _update_stats(self):
        """Update statistics bar.
        
        ★ R3: Single-pass counter (was 4 separate iterations).
        """
        pending = processing = completed = failed = 0
        _pending_set = {"pending", "ready", "waiting"}
        _proc_set = {"running", "waiting_poll"}
        _fail_set = {"failed", "cancelled"}
        for i in self._queue_items:
            s = i.status
            if s in _pending_set:
                pending += 1
            elif s in _proc_set:
                processing += 1
            elif s == "completed":
                completed += 1
            elif s in _fail_set:
                failed += 1
        
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
            estimated_seconds = int(self._queue_eta_seconds or 0)
            if estimated_seconds <= 0:
                # Fallback only when no observed throughput exists yet.
                estimated_seconds = int(((pending + processing) * 90) / max(1, processing))
            if estimated_seconds >= 3600:
                hours = estimated_seconds // 3600
                minutes = (estimated_seconds % 3600) // 60
                self.eta_label.setText(t("queue_extra.eta_hours").replace("{hours}", str(hours)).replace("{minutes}", f"{minutes:02d}"))
            else:
                minutes = estimated_seconds // 60
                seconds = estimated_seconds % 60
                self.eta_label.setText(t("queue_extra.eta_minutes").replace("{minutes}", f"{minutes:02d}").replace("{seconds}", f"{seconds:02d}"))
    
    # ── Engine Controls ──────────────────────────────────────────
    
    def _auto_start_if_idle(self, force: bool = False):
        """Auto-start engine if idle and ready tasks exist.
        
        Args:
            force: If True, bypass auto_start_queue setting check.
                   Used for retry contexts (user-initiated re-runs).
                   If False, only auto-start when setting is enabled.
        
        Skips preflight/license checks (assumed valid for auto-start).
        """
        import logging
        log = logging.getLogger(__name__)
        
        if self._is_processing:
            # Check if controller already finished stopping (UI flag out of sync)
            ctrl_processing = self.controller.state.is_processing if self.controller else True
            if not ctrl_processing:
                # Engine already stopped — sync flag and proceed
                log.info("[AutoStart] Syncing _is_processing (was True, controller says False)")
                self._is_processing = False
                self._update_button_states()
            else:
                # Engine truly still running/stopping — schedule retry after stop completes
                # Throttle: log only once per 30s to avoid flooding
                import time as _time
                _now = _time.time()
                _last = getattr(self, '_last_deferred_log_ts', 0)
                if _now - _last > 30:
                    log.info(f"[AutoStart] Deferred — engine still processing, retry in 5s")
                    self._last_deferred_log_ts = _now
                from PySide6.QtCore import QTimer
                QTimer.singleShot(5000, self._auto_start_if_idle)
                return
        
        if not self.controller:
            log.warning(f"[AutoStart] Skipped — no controller")
            return
        
        ready = self.controller.ready_count
        if ready == 0:
            log.info(f"[AutoStart] Skipped — ready_count=0 (no tasks)")
            return  # No tasks to process
        
        # Check auto_start_queue setting (skip for forced retry contexts)
        if not force:
            try:
                from config.settings import get_settings
                s = get_settings()
                if not getattr(s, 'auto_start_queue', False):
                    log.info(f"[AutoStart] Skipped — auto_start_queue=False, ready={ready}")
                    return  # Setting disabled — user must click Start All
            except Exception:
                return
        
        log.info(f"[AutoStart] ✅ Starting engine! ready_count={ready}, force={force}")
        # Auto-start
        self.start_all.emit()
        self._is_processing = self.controller.state.is_processing if self.controller else True
        self._auto_refresh_timer.start()
        self._update_button_states()
        
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            source = "retry" if force else "new tasks"
            mw.show_toast(f"▶️ Engine auto-started ({source})", "info", duration=3000)
    
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
                    # Compact toast: summary + bullet issues per account
                    lines = [check['summary']]
                    for acc in check["accounts"]:
                        if acc["issues"]:
                            short_email = acc['email'].split('@')[0]
                            for issue in acc["issues"]:
                                # Strip verbose suffix after "—"
                                short_issue = issue.split('—')[0].strip()
                                lines.append(f"  • {short_email}: {short_issue}")
                    msg = "\n".join(lines)
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
        failed_ids = [
            task.id for task in self._get_live_tasks()
            if getattr(getattr(task, 'state', None), 'value', '') == 'failed'
        ]
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
        self._request_immediate_queue_refresh()
        
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            if retried > 0:
                mw.show_toast(f"♻️ Retrying {retried} failed video(s) across all tasks", "info")
            else:
                mw.show_toast("No failed videos found to retry", "info")
        
        # Auto-start engine if idle
        if retried > 0:
            self._auto_start_if_idle(force=True)

    def _on_force_retry_all(self):
        """Force retry ALL tasks (re-generate everything) — runs in background thread."""
        live_tasks = []
        for task in self._get_live_tasks():
            state_value = getattr(getattr(task, 'state', None), 'value', '')
            if state_value in {'running', 'waiting_poll'}:
                continue
            if getattr(task, 'replace_target', None):
                continue
            live_tasks.append(task)
        if not live_tasks:
            return

        if not show_confirm(self, t("queue_extra.confirm_force_retry"),
                t("queue_extra.confirm_force_retry_msg"),
                danger=True):
            return

        # Debounce
        self.force_all_btn.setEnabled(False)
        QTimer.singleShot(5000, lambda: self.force_all_btn.setEnabled(True))

        # BUG-B4 fix: Run heavy file I/O in background, use Signal for thread-safe UI
        import threading

        item_ids = [str(task.id) for task in live_tasks]
        self._force_queue_refresh_pending = True

        def _bg_force_retry():
            count = 0
            if self.controller and hasattr(self.controller, 'force_retry_tasks'):
                count = self.controller.force_retry_tasks(item_ids, label="force_retry_all")
            elif self.controller and hasattr(self.controller, 'force_retry_task'):
                for item_id in item_ids:
                    if self.controller.force_retry_task(item_id):
                        count += 1
            # BUG-B4 fix: Use signal instead of QTimer from background thread
            self._queue_updated_signal.emit()

        threading.Thread(target=_bg_force_retry, daemon=True).start()
        # ★ FIX: Auto-start engine after force retry completes
        # Delayed 2s to let background thread finish resetting tasks
        QTimer.singleShot(2000, lambda: self._auto_start_if_idle(force=True))
    
    def _retry_next(self):
        """Retry next item in the staggered queue."""
        if not self._retry_pending:
            self._request_immediate_queue_refresh()
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
            self._request_immediate_queue_refresh()
    
    def _retry_next_by_id(self):
        """BUG-B3 fix: Staggered retry using task IDs from dispatcher."""
        if not hasattr(self, '_retry_pending_ids') or not self._retry_pending_ids:
            self._request_immediate_queue_refresh()
            return
        
        task_id = self._retry_pending_ids.pop(0)
        if self.controller and hasattr(self.controller, 'retry_task'):
            if self.controller.retry_task(str(task_id)):
                print(f"[Queue] Retried task {task_id} ({len(self._retry_pending_ids)} remaining)")
        
        if self._retry_pending_ids:
            QTimer.singleShot(2000, self._retry_next_by_id)
        else:
            self._request_immediate_queue_refresh()
            # ★ FIX: Auto-start engine to process retried tasks
            # Without this, tasks sit in READY state until user clicks Start All
            self._auto_start_if_idle(force=True)
    
    def _sync_processing_state(self):
        """BUG-B5 fix: Sync _is_processing from controller after async stop."""
        if self.controller:
            self._is_processing = self.controller.state.is_processing
        self._update_button_states()
    
    def _on_clean_completed(self):
        """Remove fully-completed tasks — all video outputs OK, no fails.
        
        Preserves:
        - Tasks with any failed/retrying/pending video slots
        - Tasks still running/pending/ready
        - Replacement tasks that are still active
        """
        dispatcher = self._get_dispatcher()
        if not dispatcher:
            return

        task_data_idx = getattr(self, '_task_data_index', {})
        
        # Phase 1: Identify fully-completed task IDs
        clean_ids = [
            tid for tid, td in task_data_idx.items()
            if self._is_fully_completed_task_data(td)
        ]
        
        if not clean_ids:
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast("No fully-completed tasks to clean", "info")
            return
        
        # Phase 2: Confirm
        if not show_confirm(
            self,
            "Clean Completed Tasks",
            f"Remove {len(clean_ids)} fully-completed task(s)?\n"
            f"Tasks with failed videos will be preserved.",
        ):
            return
        
        # Phase 3: Remove from dispatcher (batch for performance)
        removed = dispatcher.remove_tasks(clean_ids)
        
        self._request_immediate_queue_refresh()
        
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            mw.show_toast(f"🧹 Cleaned {removed} completed task(s)", "info")

    def _on_delete_all(self):
        """Delete ALL groups and tasks from the queue."""
        live_groups = self.controller.get_queue_groups() if self.controller and hasattr(self.controller, 'get_queue_groups') else []
        group_count = len(live_groups) if live_groups else len(self._group_widgets)
        if group_count == 0:
            return
        
        if not show_confirm(self, t("queue_extra.confirm_delete_all"),
                t("queue_extra.confirm_delete_all_msg"), danger=True):
            return
        
        count = 0
        if self.controller and hasattr(self.controller, 'clear_queue'):
            count = self.controller.clear_queue()
        self._request_immediate_queue_refresh()
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(
                f"🗑 Deleted all {group_count} group(s), {count} tasks removed", "info"
            )
    
    def _on_reset_all(self):
        """Reset ALL tasks — delete downloaded files, thumbnails, cache. Re-queue."""
        total = len(self._get_live_tasks()) or len(self._queue_items)
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
        self._request_immediate_queue_refresh()
        print(f"[Queue] Reset {count}/{total} tasks")
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast(f"Reset {count} prompts — cache cleared, re-queued", "info")
    
    def _on_retry_item(self, item_id):
        """Retry a specific failed item."""
        if self.controller and hasattr(self.controller, 'retry_task'):
            success = self.controller.retry_task(str(item_id))
            if success:
                self._request_immediate_queue_refresh()
                
                main_window = self.window()
                if main_window and hasattr(main_window, 'show_toast'):
                    main_window.show_toast(f"Retrying prompt #{item_id}", "info")
                # ★ BUG FIX: Auto-start engine if idle (was missing)
                self._auto_start_if_idle(force=True)
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
        self._queue_item_index.clear()
        self._task_data_index.clear()
        self._task_prompt_lc_index.clear()
    
    
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
        # ★ FIX: Use index-based mapping (locale-safe, no English/Vietnamese mismatch)
        _index_map = {0: "nothing", 1: "shutdown", 2: "sleep"}
        new_action = _index_map.get(index, "nothing")
        try:
            from config.settings import get_settings, save_settings
            s = get_settings()
            s.post_queue_action = new_action
            s.post_queue_action_enabled = (new_action != "nothing")
            save_settings()
        except Exception:
            pass
        
        if new_action == "nothing":
            # ★ FIX P1-#2: Switching to Do Nothing MUST cancel pending actions
            self._cancel_post_queue_action()
        else:
            # ★ BUG FIX: When user switches to Sleep/Shutdown, reset the
            # "already triggered" guard so the action can fire.
            self._post_queue_triggered = False
            delay = 3000 if self._sweep_in_progress else 500
            QTimer.singleShot(delay, self._check_post_queue_action)
    
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
        
        # ★ R7-1: Don't trigger sleep/shutdown while pipeline is active
        # _check_auto_stop in app_controller checks these flags, but this
        # separate post-queue action path was bypassing that guard.
        if getattr(self.controller, '_pipeline_mode_active', False):
            return
        if getattr(self.controller, '_pipeline_awaiting_queue', False):
            return
        
        from config.settings import get_settings
        s = get_settings()
        # ★ FIX: Respect post_queue_action_enabled master toggle
        # Without this check, shutdown/sleep triggers even when toggle is OFF
        is_enabled = getattr(s, 'post_queue_action_enabled', False)
        action = getattr(s, 'post_queue_action', 'nothing')
        if not is_enabled:
            action = 'nothing'
        
        # Sync max sweep rounds from settings (user can change at runtime)
        self._max_sweep_rounds = getattr(s, 'auto_sweep_max_rounds', 5)
        
        # ★ R2-3: Init before try block to prevent NameError on exception
        has_incomplete = False
        
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
            
            # ★ FIX P2-#4: Allow action when ALL tasks failed/cancelled (not just completed)
            # Old: completed == 0 blocked action when everything failed.
            # New: require at least 1 finished task (completed OR failed/cancelled)
            if pending > 0 or processing > 0 or (completed + failed) == 0:
                return
            
            # Also check upscale queue — don't shutdown while upscaling
            engine = getattr(self.controller, '_engine', None)
            if engine:
                uq = getattr(engine, '_upscale_queue', None)
                if uq:
                    stats = uq.get_stats()
                    if stats.get('pending_jobs', 0) > 0 or stats.get('active_workers', 0) > 0:
                        return  # Upscale still running
            
            # ── Auto-Sweep Gate ──
            # ★ FIX P1-#3: Auto-sweep when action is shutdown/sleep,
            # OR when auto_retry_failed is ON (regardless of post_queue_action).
            auto_retry = getattr(s, 'auto_retry_failed', True)
            has_incomplete = self._has_incomplete_work(dispatcher) if (action != 'nothing' or auto_retry) else False
            
            if has_incomplete and self._sweep_count < self._max_sweep_rounds:
                # ★ R2-2: Account Readiness Gate — only needed for auto-sweep
                # (sleep/shutdown don't need extension bridge, but re-upscale does)
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
                    return  # Browser not ready — wait for next tick before sweep
                
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
                self._auto_start_if_idle(force=True)
            elif reupscale_count > 0:
                # Re-upscale jobs queued → engine must be running for upscale lifecycle
                self._auto_start_if_idle(force=True)
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
            
            # ★ FIX P1-#2: Toast with Cancel button (wired to _cancel_post_queue_action)
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast(
                    "⚡ All tasks done! Shutting down in 60 seconds... (switch to 'Do Nothing' to cancel)",
                    "warning", duration=55000,
                )
            
        elif action == "sleep":
            log.info("[Queue] Post-queue action: SLEEP")
            if main_window and hasattr(main_window, 'show_toast'):
                main_window.show_toast(
                    "💤 All tasks done! Putting computer to sleep in 5s... (switch to 'Do Nothing' to cancel)",
                    "info", duration=5000,
                )
            # ★ FIX P2-#5: Use member timer (cancelable) instead of singleShot
            if not hasattr(self, '_pending_sleep_timer'):
                self._pending_sleep_timer = QTimer(self)
                self._pending_sleep_timer.setSingleShot(True)
                self._pending_sleep_timer.timeout.connect(self._do_sleep)
            self._pending_sleep_timer.start(5000)
    
    def _do_sleep(self):
        """Execute sleep command."""
        import subprocess
        import logging
        try:
            subprocess.Popen(
                "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
                shell=True
            )
        except Exception as e:
            logging.getLogger("queue").error(f"[Queue] Sleep command failed: {e}")
    
    def _cancel_post_queue_action(self):
        """Cancel any pending shutdown or sleep."""
        import subprocess
        import logging
        log = logging.getLogger("queue")
        
        # Cancel pending shutdown (Windows shutdown /a)
        try:
            subprocess.Popen(["shutdown", "/a"], shell=True)
            log.info("[Queue] Shutdown cancelled via shutdown /a")
        except Exception:
            pass  # May fail if no shutdown was scheduled — that's OK
        
        # ★ FIX P2-#5: Cancel pending sleep timer
        if hasattr(self, '_pending_sleep_timer') and self._pending_sleep_timer.isActive():
            self._pending_sleep_timer.stop()
            log.info("[Queue] Sleep timer cancelled")
        
        self._post_queue_triggered = False
        log.info("[Queue] Post-queue action cancelled")
        
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_toast'):
            main_window.show_toast("✅ Shutdown/Sleep cancelled.", "success", duration=3000)
