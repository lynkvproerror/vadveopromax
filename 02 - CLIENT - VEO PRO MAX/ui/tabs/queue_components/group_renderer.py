"""
Queue Group Renderer — group widgets, headers, child rows, setup dialog.

Mixin class for TabQueue. All methods operate on `self` (the TabQueue instance).
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
)
from ui.popups import show_confirm
from PySide6.QtGui import QPixmap, QCursor
from PySide6.QtCore import Qt

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme
from config.i18n import t


class QueueGroupMixin:
    """Mixin providing group rendering, header updates, and group operations."""
    
    def _create_group_widget(self, group_data: dict, expanded: bool = True, lazy: bool = False) -> QWidget:
        """Create a collapsible group widget with header + child prompt rows.
        
        If lazy=True, skip creating child task widgets (expensive). Children
        will be built on-demand when the user expands the group.
        """
        gid = group_data['id']
        mode_icons = {"T2V": "📹", "I2V": "🎬", "R2V": "🧪", "T2I": "🎯", "I2I": "✨"}
        mode_icon = mode_icons.get(group_data.get('mode', 'T2V'), "📹")
        
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # === GROUP HEADER ===
        header = QFrame()
        header.setObjectName("queueGroupHeader")
        header.setFixedHeight(40)
        header.setCursor(Qt.PointingHandCursor)
        
        status_color = Theme.BLUE if group_data['status'] == 'running' else (
            Theme.GREEN if group_data['status'] == 'completed' else Theme.SUBTEXT0
        )
        header.setStyleSheet(f"""
            QFrame#queueGroupHeader {{
                background-color: {Theme.SURFACE2};
                border-left: 4px solid {status_color};
                border-bottom: 1px solid {Theme.SURFACE0};
            }}
            QFrame#queueGroupHeader:hover {{
                background-color: {Theme.OVERLAY0 if hasattr(Theme, 'OVERLAY0') else Theme.SURFACE2};
            }}
            QFrame#queueGroupHeader > * {{ border: none; }}
        """)
        
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 4, 12, 4)
        h_layout.setSpacing(10)
        
        arrow = QLabel("▼" if expanded else "▶")
        arrow.setFixedWidth(16)
        arrow.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 12px; border: none;")
        h_layout.addWidget(arrow)
        
        # Group name — clickable
        output_folder = group_data.get('output_folder', '')
        project_name = group_data.get('project_name', '') or group_data.get('name', '')
        folder_path = str(Path(output_folder) / project_name) if output_folder and project_name else output_folder
        
        completed = group_data.get('completed', 0)
        total = group_data.get('total', 0)
        pct = group_data.get('progress', 0)
        
        name_label = QPushButton(f"📁 {group_data['name']}")
        name_label.setFlat(True)
        name_label.setCursor(Qt.PointingHandCursor)
        name_label.setStyleSheet(self._name_label_style(pct))
        name_label.setToolTip(f"📂 Click to open: {folder_path}" if folder_path else "⚠️ No output folder")
        name_label.clicked.connect(lambda checked, fp=folder_path: self._open_group_folder(fp))
        h_layout.addWidget(name_label, stretch=1)
        
        progress_label = QLabel(f"🔄 {completed}/{total} ({pct}%)")
        progress_label.setStyleSheet(f"color: {Theme.BLUE}; font-size: 11px; border: none;")
        h_layout.addWidget(progress_label)
        
        # Elapsed timer — replaces mode/model labels
        elapsed = group_data.get('elapsed_seconds', 0)
        if elapsed > 0:
            e_int = int(elapsed)
            if e_int >= 3600:
                timer_text = f"⏱ {e_int // 3600}h {(e_int % 3600) // 60:02d}m"
            else:
                timer_text = f"⏱ {e_int // 60:02d}:{e_int % 60:02d}"
        else:
            timer_text = "⏱ --:--"
        timer_label = QLabel(timer_text)
        timer_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
        timer_label.setToolTip(t("queue_extra.group_elapsed_tooltip"))
        h_layout.addWidget(timer_label)
        
        # Header buttons — build list dynamically
        header_buttons = [
            ("⚒️", "Setup: change model, aspect ratio, output folder, outputs", Theme.BLUE,
             lambda checked, _gid=gid, _gd=group_data: self._on_setup_group(_gid, _gd)),
        ]
        # JOIN button only for video groups (not T2I/I2I)
        group_mode = group_data.get('mode', 'T2V').upper()
        if group_mode not in ('T2I', 'I2I'):
            header_buttons.append(
                ("JOIN", "Concat all videos in this group into one final video", Theme.GREEN,
                 lambda checked, _gid=gid: self._on_concat_group(_gid)),
            )
        header_buttons.extend([
            ("FRC", "Force retry ALL prompts in this group", Theme.PEACH,
             lambda checked, _gid=gid: self._on_force_retry_group(_gid)),
            ("RST", "Reset group: delete all downloads & cache, re-queue", Theme.YELLOW,
             lambda checked, _gid=gid: self._on_reset_group(_gid)),
            ("DEL", "Delete entire group", Theme.SUBTEXT0,
             lambda checked, _gid=gid: self._on_delete_group(_gid)),
        ])
        # ── Wrap action buttons in fixed-width container to prevent overflow ──
        actions_container = QWidget()
        actions_container.setStyleSheet("border: none; background: transparent;")
        actions_container.setFixedWidth(200)
        ac_layout = QHBoxLayout(actions_container)
        ac_layout.setContentsMargins(0, 0, 0, 0)
        ac_layout.setSpacing(2)
        ac_layout.addStretch()
        _join_btn_ref = None
        for btn_text, btn_tip, btn_color, btn_connect in header_buttons:
            btn = QPushButton(btn_text)
            btn.setMinimumSize(36 if btn_text not in ("⚒️",) else 32, 24)
            btn.setToolTip(btn_tip)
            hover_bg = Theme.RED if btn_text == "DEL" else btn_color
            hover_color = Theme.CRUST
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {btn_color};
                    border: 1px solid {Theme.SURFACE2 if btn_text == 'DEL' else btn_color};
                    border-radius: 4px;
                    font-family: 'Segoe UI';
                    font-size: {'12px' if btn_text == '⚒️' else '10px'};
                    font-weight: bold;
                    padding: 2px;
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                    border-color: {hover_bg};
                    color: {hover_color};
                }}
            """)
            btn.clicked.connect(btn_connect)
            ac_layout.addWidget(btn)
            if btn_text == "JOIN":
                _join_btn_ref = btn
        h_layout.addWidget(actions_container)
        
        container_layout.addWidget(header)
        
        # === CHILD CONTENT ===
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(1)
        
        import logging
        _glog = logging.getLogger("veo.tab_queue")
        
        if lazy:
            # Lazy mode: skip child widget creation, defer until expand
            _glog.info(f"[GroupCreate] gid={gid} name='{group_data.get('name', '?')}' LAZY (deferred) expanded=False")
            content.setVisible(False)
        else:
            # ★ R3: Suppress repaints during bulk child creation
            content.setUpdatesEnabled(False)
            try:
                from ui.tabs.tab_queue import QueueItem
                for td in group_data.get('tasks', []):
                    item = QueueItem(
                        id=td['id'], prompt=td['prompt'],
                        status=td['status'], progress=td['progress'],
                        mode=td.get('mode', 'T2V'),
                    )
                    row = self._create_queue_item_widget(item, task_data=td)
                    row._task_id = str(td['id'])
                    content_layout.addWidget(row)
                    self._task_widgets[str(td['id'])] = row
            finally:
                content.setUpdatesEnabled(True)
            _glog.info(f"[GroupCreate] gid={gid} name='{group_data.get('name', '?')}' children={content_layout.count()} expanded={expanded}")
            content.setVisible(expanded)
        
        container_layout.addWidget(content)
        
        # ★ Auto-detect if joined files exist on disk (survives restart)
        _join_done = self._has_joined_files(group_data)
        
        self._group_widgets[gid] = {
            'container': container, 'header': header, 'content': content,
            'arrow': arrow, 'name_label': name_label,
            'progress_label': progress_label, 'timer_label': timer_label,
            'group_data': group_data,
            '_lazy_pending': lazy,  # True = children not yet built
            'join_btn': _join_btn_ref,  # For color update after concat
            '_join_done': _join_done,  # Detected from disk
        }
        
        def _header_click(event, _gid=gid):
            child = header.childAt(event.pos())
            if isinstance(child, QPushButton):
                return
            self._toggle_group(_gid)
        header.mousePressEvent = _header_click
        
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
        
        # Update elapsed timer
        elapsed = group_data.get('elapsed_seconds', 0)
        if elapsed > 0:
            e_int = int(elapsed)
            if e_int >= 3600:
                timer_text = f"⏱ {e_int // 3600}h {(e_int % 3600) // 60:02d}m"
            else:
                timer_text = f"⏱ {e_int // 60:02d}:{e_int % 60:02d}"
        else:
            timer_text = "⏱ --:--"
        if 'timer_label' in gw:
            gw['timer_label'].setText(timer_text)
        
        # Bug 13: Cache header key — skip CSS rebuild if status+pct unchanged
        status = group_data['status']
        # ★ Auto-detect JOINED state (check disk if not flagged yet, throttle 30s)
        if not gw.get('_join_done'):
            import time as _t
            _now = _t.monotonic()
            if _now - gw.get('_join_check_ts', 0) > 30:
                gw['_join_check_ts'] = _now
                gw['_join_done'] = self._has_joined_files(group_data)
        if gw.get('_join_done'):
            for child in header.findChildren(QPushButton):
                if child.text() in ("JOIN", "JOINED"):
                    if child.text() != "JOINED":
                        child.setText("JOINED")
                        child.setStyleSheet(f"""
                            QPushButton {{
                                background: transparent;
                                color: {Theme.BLUE};
                                border: 1px solid {Theme.BLUE};
                                border-radius: 4px;
                                font-family: 'Segoe UI';
                                font-size: 10px;
                                font-weight: bold;
                                padding: 2px;
                            }}
                            QPushButton:hover {{
                                background-color: {Theme.BLUE};
                                border-color: {Theme.BLUE};
                                color: {Theme.CRUST};
                            }}
                        """)
                    break
        
        header_key = (status, pct)
        if gw.get('_last_header_key') == header_key:
            return
        gw['_last_header_key'] = header_key
        
        gw['name_label'].setStyleSheet(self._name_label_style(pct))
        
        status_color = Theme.BLUE if status == 'running' else (
            Theme.GREEN if status == 'completed' else Theme.SUBTEXT0
        )
        header.setStyleSheet(f"""
            QFrame#queueGroupHeader {{
                background-color: {Theme.SURFACE2};
                border-left: 4px solid {status_color};
                border-bottom: 1px solid {Theme.SURFACE0};
            }}
            QFrame#queueGroupHeader:hover {{
                background-color: {Theme.OVERLAY0 if hasattr(Theme, 'OVERLAY0') else Theme.SURFACE2};
            }}
            QFrame#queueGroupHeader > * {{ border: none; }}
        """)
    
    def _rebuild_group_children(self, gw: dict, group_data: dict):
        """Differential update: reuse existing row widgets, only create/remove as needed.
        
        ★ Anti-freeze: Uses setUpdatesEnabled(false) to batch layout changes.
        """
        content = gw['content']
        layout = content.layout()
        new_tasks = group_data.get('tasks', [])
        new_task_ids = {str(td['id']) for td in new_tasks}
        
        # ★ Anti-freeze: Suppress paint events during bulk layout changes
        content.setUpdatesEnabled(False)
        try:
            existing_ids = set()
            i = 0
            while i < layout.count():
                child = layout.itemAt(i)
                widget = child.widget() if child else None
                if widget and hasattr(widget, '_task_id'):
                    if widget._task_id not in new_task_ids:
                        layout.takeAt(i)
                        if hasattr(widget, 'thumb_slots'):
                            for s in widget.thumb_slots:
                                self._unregister_shimmer_slot(s)
                        widget.deleteLater()
                        continue
                    existing_ids.add(widget._task_id)
                i += 1
            
            from ui.tabs.tab_queue import QueueItem
            for idx, td in enumerate(new_tasks):
                tid = str(td['id'])
                existing_widget = self._task_widgets.get(tid)
                if existing_widget and tid in existing_ids:
                    self._update_task_widget_data(existing_widget, td)
                else:
                    item = QueueItem(
                        id=td['id'], prompt=td['prompt'],
                        status=td['status'], progress=td['progress'],
                        mode=td.get('mode', 'T2V'),
                    )
                    row = self._create_queue_item_widget(item, task_data=td)
                    row._task_id = tid
                    row._task_status = td['status']
                    layout.insertWidget(idx, row)
                    self._task_widgets[tid] = row
                    self._fade_in_widget(row)
        finally:
            content.setUpdatesEnabled(True)
    
    def _update_task_widget_data(self, widget: QFrame, td: dict):
        """Update an existing task row widget with new data (no destroy/recreate).
        
        ★ Perf: Skips expensive thumbnail operations for off-screen widgets,
        marking them for deferred refresh when they scroll into view.
        """
        try:
            new_status = td.get('status', 'running')
            widget._task_status = new_status
            if hasattr(widget, 'status_label'):
                self._update_status_label(widget, td)
            
            # ★ Perf: Viewport culling — skip expensive thumb ops for off-screen rows
            in_viewport = self._is_widget_in_viewport(widget)
            
            # 🔒 Rebuild thumb_slots if output_count changed (always — structural)
            if hasattr(widget, 'thumb_slots') and hasattr(widget, 'thumb_container'):
                new_count = td.get('output_count', len(widget.thumb_slots))
                if new_count != len(widget.thumb_slots):
                    self._rebuild_thumb_slots(widget, td, new_count)
            
            if hasattr(widget, 'thumb_slots'):
                if in_viewport:
                    self._update_thumb_slot_data(widget, td)
                    widget._needs_thumb_refresh = False
                else:
                    # ★ Perf: Mark for deferred refresh when scrolled into view
                    widget._needs_thumb_refresh = True
            
            # Update Mode label if workflow type changed (e.g. force retry)
            new_mode = td.get('mode', '')
            if new_mode and hasattr(widget, 'mode_label'):
                mode_icons = {"T2V": "📹", "I2V": "🎬", "R2V": "🧪", "T2I": "🎯", "I2I": "✨"}
                new_text = f"{mode_icons.get(new_mode, '📹')} {new_mode}"
                if widget.mode_label.text() != new_text:
                    widget.mode_label.setText(new_text)
            
            # Refresh Image column only when source data changes AND in viewport
            # (avoid rebuilding every 2s refresh cycle)
            if in_viewport and hasattr(widget, 'input_thumbs_container'):
                # Compute current image data fingerprint
                img_data = td.get('image_paths', []) or []
                cont = td.get('continuation_frame', '') or ''
                if td.get('has_continuation') and not img_data and cont:
                    img_data = [cont]
                new_key = f"{new_mode}:{','.join(img_data)}"
                old_key = getattr(widget, '_input_thumbs_key', None)
                if new_key != old_key:
                    new_container = self._create_input_thumbs(new_mode, td)
                    old_container = widget.input_thumbs_container
                    parent_layout = widget.layout()
                    if parent_layout:
                        idx = parent_layout.indexOf(old_container)
                        if idx >= 0:
                            parent_layout.removeWidget(old_container)
                            old_container.deleteLater()
                            parent_layout.insertWidget(idx, new_container)
                            widget.input_thumbs_container = new_container
                    widget._input_thumbs_key = new_key
            
            # Toggle retry button visibility based on new status
            if hasattr(widget, 'retry_btn'):
                if new_status in ('failed', 'cancelled'):
                    widget.retry_btn.show()
                else:
                    widget.retry_btn.hide()
            
            # Bug 12: Cache accent — skip setStyleSheet if border color unchanged
            status_colors = {
                'ready': Theme.SUBTEXT0, 'pending': Theme.SUBTEXT0,
                'waiting': Theme.YELLOW if hasattr(Theme, 'YELLOW') else Theme.SUBTEXT0,
                'running': Theme.BLUE, 'waiting_poll': Theme.BLUE,
                'completed': Theme.GREEN, 'failed': Theme.RED,
                'cancelled': Theme.SUBTEXT0,
            }
            accent = status_colors.get(new_status, Theme.SUBTEXT0)
            
            # ★ R3: Override border accent for completed tasks with active upscale
            if new_status == 'completed':
                upscale_status = td.get('upscale_status', '')
                video_outputs = td.get('video_outputs', [])
                has_upscaling = any(
                    vo.get('upscale_status') in ('submitting', 'polling')
                    for vo in video_outputs
                ) or upscale_status in ('submitting', 'polling')
                has_upscale_fail = any(
                    vo.get('upscale_status') == 'failed'
                    for vo in video_outputs
                ) or upscale_status == 'failed'
                has_retrying = any(
                    vo.get('quality') == 'retrying'
                    for vo in video_outputs
                )
                if has_retrying or has_upscaling:
                    accent = Theme.PURPLE
                elif has_upscale_fail:
                    accent = Theme.YELLOW
            
            if getattr(widget, '_last_accent', None) != accent:
                widget._last_accent = accent
                widget.setStyleSheet(f"""
                    QFrame#queueItemRow {{
                        background-color: {Theme.SURFACE1};
                        border-bottom: 1px solid {Theme.SURFACE0};
                        border-left: 3px solid {accent};
                    }}
                    QFrame#queueItemRow:hover {{
                        background-color: {Theme.SURFACE2};
                    }}
                    QFrame#queueItemRow > * {{ border: none; }}
                """)
        except RuntimeError:
            pass
    
    def _rebuild_thumb_slots(self, widget: QFrame, td: dict, new_count: int):
        """Rebuild thumb_slots when output_count changes (e.g. Group Setup)."""
        try:
            container = widget.thumb_container
            layout = container.layout()
            
            # Unregister old shimmer/animation slots
            for slot in widget.thumb_slots:
                self._unregister_shimmer_slot(slot)
            
            # Clear existing slots
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # Create new slots
            status = td.get('status', 'pending')
            progress = td.get('progress', 0)
            thumbnails = td.get('thumbnails', [])
            output_files = td.get('output_files', [])
            video_outputs = td.get('video_outputs', [])
            
            new_slots = []
            for vi in range(new_count):
                vi_info = video_outputs[vi] if vi < len(video_outputs) else None
                video_path = None
                if vi_info:
                    video_path = vi_info.get('best_file') or (
                        output_files[vi] if vi < len(output_files) else None
                    )
                else:
                    video_path = output_files[vi] if vi < len(output_files) else None
                
                slot = self._create_thumb_slot(
                    vi, status, progress,
                    thumbnails[vi] if vi < len(thumbnails) else None,
                    video_path,
                    video_info=vi_info
                )
                layout.addWidget(slot)
                new_slots.append(slot)
            
            widget.thumb_slots = new_slots
            container.setFixedWidth(new_count * 44)
        except RuntimeError:
            pass
    
    def _update_status_label(self, widget, td):
        """Update the status label on a task row widget.
        
        ★ Fix: Now checks upscale_status for completed tasks — previously
        showed "✅ COMPLETED" even when upscale was actively in progress.
        """
        status = td.get('status', '')
        progress = td.get('progress', 0)
        video_outputs = td.get('video_outputs', [])
        upscale_status = td.get('upscale_status', '')
        
        if progress >= 100:
            # ── Priority 1: Per-video retrying ──
            retrying_count = sum(1 for vo in video_outputs if vo.get('quality') == 'retrying')
            if retrying_count > 0:
                retry_pct = td.get('retry_progress', -1)
                retry_txt = td.get('retry_status_text', '')
                if retry_pct >= 0 and retry_pct < 100:
                    label = f"♻️ RETRYING {retrying_count}/{len(video_outputs)} • {retry_pct}%"
                    if retry_txt:
                        label += f" {retry_txt}"
                else:
                    label = f"♻️ RETRYING {retrying_count}/{len(video_outputs)}"
                widget.status_label.setText(label)
                widget.status_label.setStyleSheet(
                    f"color: {Theme.PURPLE}; font-size: 10px; font-weight: bold; border: none;"
                )
                return
            
            # ── Priority 2: Upscale in progress (submitting/polling) ──
            upscaling_count = sum(
                1 for vo in video_outputs
                if vo.get('upscale_status') in ('submitting', 'polling')
            )
            if upscaling_count > 0 or upscale_status in ('submitting', 'polling'):
                total = len(video_outputs) or 1
                done = sum(1 for vo in video_outputs if vo.get('upscale_status') == 'success')
                download_quality = td.get('download_quality', '1080p')
                # Use status_text from engine if available (e.g. "⬆️ Upscaling 1080p...")
                status_text = td.get('status_text', '')
                if status_text and ('Upscal' in status_text or '⬆️' in status_text):
                    label = status_text[:18]
                else:
                    label = f"⬆️ Upscale {done}/{total}"
                widget.status_label.setText(label)
                widget.status_label.setStyleSheet(
                    f"color: {Theme.PURPLE}; font-size: 10px; font-weight: bold; border: none;"
                )
                # Tooltip with per-video details
                vo_lines = []
                for vo in video_outputs:
                    us = vo.get('upscale_status', '')
                    idx = vo.get('index', 0) + 1
                    if us == 'success':
                        vo_lines.append(f"  Video {idx}: ✅ Done")
                    elif us == 'polling':
                        vo_lines.append(f"  Video {idx}: 🔄 Polling")
                    elif us == 'submitting':
                        vo_lines.append(f"  Video {idx}: ⬆️ Submitting")
                    elif us == 'failed':
                        vo_lines.append(f"  Video {idx}: ❌ {vo.get('upscale_error', 'Failed')}")
                if vo_lines:
                    widget.status_label.setToolTip("Per-video upscale:\n" + "\n".join(vo_lines))
                return
            
            # ── Priority 3: Upscale failed ──
            failed_count = sum(
                1 for vo in video_outputs
                if vo.get('upscale_status') == 'failed'
            )
            if failed_count > 0 or upscale_status == 'failed':
                total = len(video_outputs) or 1
                if total <= 1:
                    label = "⚠️ UP FAIL"
                else:
                    label = f"⚠️ {failed_count}/{total} FAIL"
                widget.status_label.setText(label)
                widget.status_label.setStyleSheet(
                    f"color: {Theme.YELLOW}; font-size: 10px; font-weight: bold; border: none;"
                )
                # Tooltip with error details
                fail_details = []
                for vo in video_outputs:
                    if vo.get('upscale_status') == 'failed':
                        fail_details.append(f"Video {vo.get('index', 0)+1}: {vo.get('upscale_error', '?')}")
                tooltip = "\n".join(fail_details) if fail_details else "Upscale failed"
                tooltip += "\nRight-click → Re-Upscale"
                widget.status_label.setToolTip(tooltip)
                return
            
            # ── Priority 4: Truly completed ──
            widget.status_label.setText(t("queue_extra.completed"))
            widget.status_label.setStyleSheet(
                f"color: {Theme.GREEN}; font-size: 10px; font-weight: bold; border: none;"
            )
        elif status in ('running', 'waiting_poll'):
            display = td.get('status_text', '🔥 PROCESSING')
            widget.status_label.setText(display)
            if "⬇️" in display or "Download" in display:
                color = Theme.SAPPHIRE
            elif "⬆️" in display or "Upscal" in display:
                color = Theme.PURPLE
            elif "✅" in display:
                color = Theme.GREEN
            else:
                color = Theme.PEACH
            widget.status_label.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: bold; border: none;"
            )
        elif status == 'failed':
            error_msg = td.get('error', '')
            # Distinct status for prompt policy violations
            if error_msg and ('Policy Violation' in error_msg or 'UNSAFE' in error_msg.upper()):
                widget.status_label.setText(t("queue_extra.status_policy"))
                widget.status_label.setStyleSheet(
                    f"color: {Theme.PEACH}; font-size: 10px; font-weight: bold; border: none;"
                )
            else:
                widget.status_label.setText(t("queue_extra.label_failed"))
                widget.status_label.setStyleSheet(
                    f"color: {Theme.RED}; font-size: 10px; font-weight: bold; border: none;"
                )
            if error_msg:
                widget.status_label.setToolTip(error_msg)
        else:
            icons = {'ready': '⏳', 'pending': '⏳', 'waiting': '🔗', 'cancelled': '⛔'}
            icon = icons.get(status, '⏳')
            color = Theme.YELLOW if status == 'waiting' else Theme.SUBTEXT0
            widget.status_label.setText(f"{icon} {status.upper()}")
            widget.status_label.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: bold; border: none;"
            )
    
    def _update_thumb_slot_data(self, widget, td):
        """Update thumbnail slot rendering on an existing widget.
        
        ★ Anti-flicker: Uses per-slot fingerprints to skip redundant updates.
        """
        progress = td.get('progress', 0)
        thumbnails = td.get('thumbnails', [])
        video_outputs = td.get('video_outputs', [])
        output_files = td.get('output_files', [])
        status = td.get('status', '')
        
        for i, slot in enumerate(widget.thumb_slots):
            vi = video_outputs[i] if i < len(video_outputs) else None
            slot._video_info = vi
            if vi:
                slot._border_color_name = vi.get('border_color', 'gray')
        
        if progress == 0 and status in ('ready', 'pending', 'waiting') and not video_outputs:
            for slot in widget.thumb_slots:
                try:
                    # ★ Anti-flicker: Skip if already in empty state
                    if getattr(slot, '_slot_fingerprint', None) == 'empty':
                        continue
                    slot._slot_fingerprint = 'empty'
                    slot.clear()
                    slot.setText('')
                    slot._border_color_name = 'gray'
                    slot._video_info = None
                    slot._progress_pct = 0.0
                    slot._original_pixmap = None
                    slot.setStyleSheet(f"""
                        QLabel {{
                            background-color: {Theme.SURFACE0};
                            border: 1px solid {Theme.SURFACE1};
                            border-radius: 4px;
                            color: {Theme.SUBTEXT0};
                            font-size: 10px;
                        }}
                    """)
                    self._unregister_shimmer_slot(slot)
                except RuntimeError:
                    continue
        elif progress >= 100:
            # ★ P5: Hoist import outside slot loop (avoids N×sys.modules lookup)
            from ui.popups.media_preview import attach_hover_zoom as _attach_hz
            for i, slot in enumerate(widget.thumb_slots):
                try:
                    vi = video_outputs[i] if i < len(video_outputs) else None
                    slot._original_pixmap = None
                    thumb_path = (vi.get('thumbnail_path', '') if vi else '') or (thumbnails[i] if i < len(thumbnails) else '')
                    if thumb_path:
                        self._invalidate_file_cache(thumb_path)
                    if vi:
                        bc_name = vi.get('border_color', '')
                        if bc_name:
                            slot._border_color_name = bc_name
                        # Auto-register pulsing border for active upscale
                        if bc_name == 'purple':
                            self._register_upscale_spinner(slot)
                    
                    # ★ Anti-flicker fingerprint: skip repaint if nothing changed
                    us = vi.get('upscale_status', '') if vi else ''
                    best_file = (vi.get('best_file', '') if vi else '') or (
                        output_files[i] if i < len(output_files) else ''
                    )
                    bc = self._slot_border(slot, Theme.GREEN)
                    fp = f"done|{thumb_path}|{bc}|{us}|{best_file}"
                    if getattr(slot, '_slot_fingerprint', None) == fp:
                        continue  # Nothing changed — skip expensive repaint
                    slot._slot_fingerprint = fp
                    
                    is_failed = vi and vi.get('upscale_status') == 'failed'
                    
                    quality = vi.get('quality', '') if vi else ''
                    ue = vi.get('upscale_error', '') if vi else ''
                    tip_parts = [f"Video {i+1}"]
                    if quality: tip_parts.append(f"Quality: {quality}")
                    if us: tip_parts.append(f"Upscale: {us}")
                    if ue: tip_parts.append(f"Error: {ue}")
                    slot.setToolTip(" | ".join(tip_parts))
                    
                    if thumb_path and self._cached_file_exists(thumb_path):
                        pix = self._get_cached_pixmap(thumb_path, 40)
                        if not pix.isNull():
                            slot.setPixmap(pix)
                            slot.setStyleSheet(
                                f"QLabel {{ border: 2px solid {bc}; border-radius: 4px;"
                                f"background-color: {Theme.BASE}; padding: 1px; }}"
                                f"QLabel:hover {{ border-color: {Theme.LAVENDER}; }}"
                            )
                            self._unregister_shimmer_slot(slot)
                    elif not (slot.pixmap() and not slot.pixmap().isNull()):
                        slot.setText('')
                        border_c = Theme.RED if is_failed else bc
                        bg = Theme.SURFACE0
                        slot.setStyleSheet(f"""
                            QLabel {{
                                background-color: {bg};
                                border: 2px solid {border_c};
                                border-radius: 4px;
                            }}
                        """)
                        self._unregister_shimmer_slot(slot)
                    
                    # ── Wire click-to-play + right-click context menu ──
                    if best_file and self._cached_file_exists(best_file):
                        slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                        slot.mousePressEvent = lambda e, p=best_file: (
                            self._open_media(p) if e.button() == Qt.MouseButton.LeftButton else None
                        )
                    # ★ Hover-zoom on completed thumbnail
                    if thumb_path and self._cached_file_exists(thumb_path):
                        _attach_hz(slot, thumb_path)
                    if vi:
                        self._attach_slot_context_menu(slot, vi)
                except RuntimeError:
                    continue
        else:
            for i, slot in enumerate(widget.thumb_slots):
                try:
                    if i < len(video_outputs):
                        slot._video_info = video_outputs[i]
                        bc_name = video_outputs[i].get('border_color', '')
                        if bc_name:
                            slot._border_color_name = bc_name
                    
                    # Load thumbnail into slot if available but not yet loaded
                    # This ensures _apply_thumb_effect can render upscale overlay
                    has_pixmap = slot.pixmap() and not slot.pixmap().isNull()
                    if not has_pixmap:
                        vi = video_outputs[i] if i < len(video_outputs) else None
                        thumb_path = (vi.get('thumbnail_path', '') if vi else '') or (
                            thumbnails[i] if i < len(thumbnails) else ''
                        )
                        if thumb_path:
                            self._invalidate_file_cache(thumb_path)
                            if self._cached_file_exists(thumb_path):
                                pix = self._get_cached_pixmap(thumb_path, 40)
                                if not pix.isNull():
                                    slot.setPixmap(pix)
                                    slot._original_pixmap = pix
                    
                    self._apply_thumb_effect(slot, progress, status)
                except RuntimeError:
                    continue
    
    def _toggle_group(self, group_id: str):
        """Toggle expand/collapse of a group. Builds children on-demand for lazy groups.
        
        ★ Anti-freeze R1: Uses setUpdatesEnabled(false) to batch repaints.
        ★ Anti-freeze R2: Stops refresh timer during toggle; on-expand catch-up.
        ★ Anti-freeze R3: Chunked incremental loading — builds widgets in
          batches of 5, yielding to event loop between batches so UI stays
          responsive. Arrow + visibility update instantly; heavy work deferred.
        """
        from PySide6.QtCore import QTimer
        
        gw = self._group_widgets.get(group_id)
        if not gw:
            return
        expanded = not self._group_expanded.get(group_id, True)
        self._group_expanded[group_id] = expanded
        
        content = gw['content']
        
        # ★ R2: Stop 2s refresh timer during toggle
        _timer = getattr(self, '_auto_refresh_timer', None)
        _timer_was_active = _timer and _timer.isActive()
        if _timer_was_active:
            _timer.stop()
        
        # ★ R3: Update arrow + visibility IMMEDIATELY → instant visual feedback
        gw['arrow'].setText("▼" if expanded else "▶")
        
        if not expanded:
            # Collapse: simply hide content — cheap operation
            content.setVisible(False)
            if _timer_was_active and _timer:
                _timer.start()
            return
        
        # === EXPAND PATH ===
        
        # Lazy-load: chunked incremental widget creation
        if gw.get('_lazy_pending'):
            gw['_lazy_pending'] = False
            group_data = gw.get('group_data', {})
            tasks = group_data.get('tasks', [])
            
            CHUNK_SIZE = 5
            content_layout = content.layout()
            
            def _build_chunk(start_idx):
                """Build CHUNK_SIZE widgets, then schedule next chunk."""
                # Guard: group may have been collapsed while we were building
                if not self._group_expanded.get(group_id, False):
                    if _timer_was_active and _timer:
                        _timer.start()
                    return
                
                content.setUpdatesEnabled(False)
                try:
                    from ui.tabs.tab_queue import QueueItem
                    end_idx = min(start_idx + CHUNK_SIZE, len(tasks))
                    for i in range(start_idx, end_idx):
                        td = tasks[i]
                        item = QueueItem(
                            id=td['id'], prompt=td['prompt'],
                            status=td['status'], progress=td['progress'],
                            mode=td.get('mode', 'T2V'),
                        )
                        row = self._create_queue_item_widget(item, task_data=td)
                        row._task_id = str(td['id'])
                        content_layout.addWidget(row)
                        self._task_widgets[str(td['id'])] = row
                finally:
                    content.setUpdatesEnabled(True)
                
                if end_idx < len(tasks):
                    # More chunks to build — schedule next
                    QTimer.singleShot(0, lambda: _build_chunk(end_idx))
                else:
                    # All done — restart refresh timer
                    import logging
                    logging.getLogger("veo.tab_queue").info(
                        f"[LazyExpand] gid={group_id} built {len(tasks)} children (chunked)"
                    )
                    if _timer_was_active and _timer:
                        _timer.start()
            
            # Show content first (may be empty / partially filled)
            content.setVisible(True)
            # Start chunked building
            QTimer.singleShot(0, lambda: _build_chunk(0))
            return
        
        # Dirty catch-up: defer rebuild so arrow updates first
        if gw.get('_dirty'):
            gw['_dirty'] = False
            content.setVisible(True)
            
            def _deferred_rebuild():
                if not self._group_expanded.get(group_id, False):
                    if _timer_was_active and _timer:
                        _timer.start()
                    return
                group_data = gw.get('group_data', {})
                self._rebuild_group_children(gw, group_data)
                if _timer_was_active and _timer:
                    _timer.start()
            
            QTimer.singleShot(0, _deferred_rebuild)
            return
        
        # Normal expand (children already built, not dirty)
        content.setVisible(True)
        if _timer_was_active and _timer:
            _timer.start()
    
    def _on_setup_group(self, group_id: str, group_data: dict):
        """Show setup dialog to adjust group settings."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QFileDialog
        
        if self.controller and hasattr(self.controller, 'get_queue_groups'):
            for g in self.controller.get_queue_groups():
                if g['id'] == group_id:
                    group_data = g
                    break
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"⚒️ Group Setup — {group_data.get('name', group_id)}")
        dialog.setMinimumWidth(450)
        dialog.setStyleSheet(f"""
            QDialog {{ background-color: {Theme.BASE}; }}
            QLabel {{ color: {Theme.TEXT}; font-size: 12px; }}
            QLineEdit, QComboBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: none; border-radius: 4px;
                padding: 4px 8px; font-size: 12px; font-weight: bold;
                min-height: 28px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {Theme.GREEN}; }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel(f"⚒️ Adjust settings for group: {group_data.get('name', group_id)}")
        title.setStyleSheet(f"color: {Theme.TEXT}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        # ── Detect mode: Image vs Video ──
        mode = group_data.get('mode', 'T2V').upper()
        is_image = mode in ('T2I', 'I2I')
        
        layout.addWidget(QLabel("🤖 AI Model"))
        model_combo = QComboBox()
        if is_image:
            model_combo.addItems(["🔥 Nano Banana Pro", "🔥 Nano Banana 2", "Imagen 4"])
            current_model = group_data.get('model', '').upper()
            idx = 1 if 'NARWHAL' in current_model else (2 if 'IMAGEN' in current_model else 0)
        else:
            model_combo.addItems(["Veo 3.1 - Fast", "Veo 3.1 - Fast [LP]", "Veo 3.1 - Quality", "Veo 2 - Fast", "Veo 2 - Quality"])
            current_model = group_data.get('model', '').lower()
            if '3_1' in current_model or '3.1' in current_model:
                idx = 1 if ('lp' in current_model or 'relaxed' in current_model) else (2 if 'quality' in current_model else 0)
            elif '2' in current_model or '3_0' in current_model:
                idx = 4 if 'quality' in current_model else 3
            else:
                idx = 0
        model_combo.setCurrentIndex(idx)
        layout.addWidget(model_combo)
        _label_style = f"color: {Theme.TEXT}; font-weight: bold;"
        _input_style = f"""
            QLineEdit {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: none; border-radius: 4px;
                padding: 4px 8px; font-weight: bold;
            }}
        """
        _combo_style = f"""
            QComboBox {{
                background-color: {Theme.SURFACE1}; color: {Theme.TEXT};
                border: none; border-radius: 4px;
                padding: 4px 8px; font-weight: bold;
            }}
        """
        
        _ar_label = QLabel("📐 Aspect Ratio")
        _ar_label.setStyleSheet(_label_style)
        layout.addWidget(_ar_label)
        ar_combo = QComboBox()
        ar_combo.addItems(["16:9 (Landscape)", "9:16 (Portrait)"])
        ar_combo.setStyleSheet(_combo_style)
        if 'PORTRAIT' in group_data.get('aspect_ratio', '').upper():
            ar_combo.setCurrentIndex(1)
        layout.addWidget(ar_combo)
        
        _folder_label = QLabel("📂 Output Folder")
        _folder_label.setStyleSheet(_label_style)
        layout.addWidget(_folder_label)
        folder_row = QHBoxLayout()
        folder_input = QLineEdit()
        folder_input.setText(group_data.get('output_folder', ''))
        folder_input.setStyleSheet(_input_style)
        folder_row.addWidget(folder_input)
        browse_btn = QPushButton("📂")
        browse_btn.setFixedHeight(34)
        browse_btn.setMinimumWidth(40)
        browse_btn.setProperty("variant", "secondary")
        browse_btn.setToolTip("Browse output folder")
        browse_btn.clicked.connect(
            lambda: folder_input.setText(QFileDialog.getExistingDirectory(dialog, "Select Output Folder") or folder_input.text())
        )
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)
        
        out_label = "🖼️ Outputs per Prompt" if is_image else "🎬 Outputs per Prompt"
        out_unit = "image" if is_image else "video"
        layout.addWidget(QLabel(out_label))
        output_combo = QComboBox()
        output_combo.addItems([f"1 {out_unit}", f"2 {out_unit}s", f"3 {out_unit}s", f"4 {out_unit}s"])
        output_combo.setCurrentIndex(max(0, min(group_data.get('output_count', 4) - 1, 3)))
        layout.addWidget(output_combo)
        
        if is_image:
            layout.addWidget(QLabel("🖼️ Image Quality"))
            quality_combo = QComboBox()
            quality_combo.addItems(["1k", "2k", "4k"])
            cq = group_data.get('download_quality', '2k').lower()
            qi = {"1k": 0, "2k": 1, "4k": 2}.get(cq, 1)
            quality_combo.setCurrentIndex(qi)
            layout.addWidget(quality_combo)
        else:
            layout.addWidget(QLabel("📺 Download Quality"))
            quality_combo = QComboBox()
            quality_combo.addItems(["720p", "1080p", "4K"])
            cq = group_data.get('download_quality', '720p')
            qi = {"720p": 0, "1080p": 1, "4K": 2, "4k": 2}.get(cq, 0)
            quality_combo.setCurrentIndex(qi)
            layout.addWidget(quality_combo)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumSize(100, 36)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("✅ Apply")
        apply_btn.setMinimumSize(120, 36)
        apply_btn.setProperty("btnSize", "lg")
        
        def _apply_settings():
            from config.constants import resolve_model_key, WorkflowType
            ar_text = ar_combo.currentText()
            ar_value = "PORTRAIT" if "Portrait" in ar_text else "LANDSCAPE"
            wf = getattr(WorkflowType, mode, WorkflowType.T2V)
            try:
                if is_image:
                    # Image models: map display name → API key
                    img_map = {"🔥 Nano Banana Pro": "GEM_PIX_2", "🔥 Nano Banana 2": "NARWHAL", "Imagen 4": "IMAGEN_3_5"}
                    model_key = img_map.get(model_combo.currentText(), model_combo.currentText())
                else:
                    model_key = resolve_model_key(model_combo.currentText(), wf, ar_value, False)
            except Exception:
                model_key = model_combo.currentText()
            ar_api = "VIDEO_ASPECT_RATIO_PORTRAIT" if ar_value == "PORTRAIT" else "VIDEO_ASPECT_RATIO_LANDSCAPE"
            settings = {
                'model': model_key, 'aspect_ratio': ar_api,
                'output_folder': folder_input.text().strip(),
                'output_count': int(output_combo.currentText().split()[0]),
                'download_quality': quality_combo.currentText(),
            }
            if self.controller and hasattr(self.controller, 'update_group_settings'):
                if self.controller.update_group_settings(group_id, settings):
                    mw = self.window()
                    if mw and hasattr(mw, 'show_toast'):
                        mw.show_toast("✅ Group settings updated", "success")
                    self._refresh_queue_from_controller()
            dialog.accept()
        
        apply_btn.clicked.connect(_apply_settings)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)
        dialog.exec()
    
    def _on_force_retry_group(self, group_id: str):
        """Force retry ALL tasks in a group (re-generate everything)."""
        if not self.controller or not hasattr(self.controller, 'dispatcher'):
            return
        group = self.controller.dispatcher.get_group(group_id)
        if not group:
            return
        # BUG-B19: Count only original tasks (exclude replacements) for display
        original_tasks = [t for t in group.tasks if not t.replace_target]
        task_count = len(original_tasks)
        if not show_confirm(self, t("queue_extra.confirm_force_group"),
                f"Force re-generate ALL {task_count} prompts in this group?\n\n"
                "This will delete existing outputs and re-queue everything.",
                danger=True):
            return
        count = 0
        if hasattr(self.controller, 'force_retry_task'):
            # BUG-B9 fix: Iterate over snapshot to avoid mutation during iteration
            # BUG-B19 fix: Skip replacement tasks (handled by parent's force_retry)
            for task in list(group.tasks):
                if task.replace_target:
                    continue
                if task.state.value != 'running':
                    if self.controller.force_retry_task(str(task.id)):
                        count += 1
        self._refresh_queue_from_controller()
        self._update_stats()
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            mw.show_toast(f"🔄 Force retrying {count}/{task_count} prompts in group", "info")

    def _on_reset_group(self, group_id: str):
        """Reset all tasks in a group."""
        if not self.controller or not hasattr(self.controller, 'dispatcher'):
            return
        group = self.controller.dispatcher.get_group(group_id)
        if not group:
            return
        if not show_confirm(self, t("queue_extra.confirm_reset_group"),
                "Reset incomplete/failed prompts in this group?\n\nCompleted tasks will be PRESERVED.",
                danger=True):
            return
        count = 0
        # BUG-B19 fix: list() snapshot + skip replacement tasks
        for task in list(group.tasks):
            if task.replace_target:
                continue
            if task.state.value in ('completed', 'running', 'waiting_poll'):
                continue
            if hasattr(self.controller, 'force_retry_task'):
                if self.controller.force_retry_task(str(task.id)):
                    count += 1
        self._refresh_queue_from_controller()
        self._update_stats()
        original_count = len([t for t in group.tasks if not t.replace_target])
        print(f"[Queue] Force-retried group {group_id}: {count}/{original_count} tasks")
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            mw.show_toast(f"Force-retried {count} prompts — re-queued", "info")
    
    def _on_delete_group(self, group_id: str):
        """Delete an entire task group and all its tasks."""
        gw = self._group_widgets.get(group_id)
        if not gw:
            return
        if not show_confirm(self, t("queue_extra.confirm_delete_group"),
                "Delete this group and all its tasks?", danger=True):
            return
        # BUG-B7 fix: remove_group now handles cancel + _all_tasks cleanup
        if self.controller and hasattr(self.controller, 'dispatcher'):
            self.controller.dispatcher.remove_group(group_id)
        # Clean UI references
        gw['container'].deleteLater()
        self._group_widgets.pop(group_id, None)
        self._group_expanded.pop(group_id, None)
        # Clean task widgets that belonged to this group
        for tid in list(self._task_widgets.keys()):
            if tid.startswith(group_id):
                w = self._task_widgets.pop(tid, None)
                if w:
                    w.deleteLater()
        self._queue_items = [i for i in self._queue_items if not str(i.id).startswith(group_id)]
        self._update_stats()
        print(f"[Queue] Deleted group: {group_id}")
    
    def _has_joined_files(self, group_data: dict) -> bool:
        """Check if joined output files exist on disk for this group.
        
        Scans for *_joined.mp4 pattern in the group's output directory.
        Uses the same naming convention as _on_concat_group.
        """
        import os, re, glob
        output_folder = group_data.get('output_folder', '')
        project_name = group_data.get('project_name', '') or group_data.get('name', '')
        group_name = group_data.get('name', '')
        if not output_folder or not group_name:
            return False
        
        safe_name = re.sub(r'[<>:"/\\|?*]', '', group_name).replace(" ", "_").strip("._")[:50]
        if project_name:
            final_dir = os.path.join(output_folder, project_name)
        else:
            final_dir = output_folder
        
        if not os.path.isdir(final_dir):
            return False
        
        pattern = os.path.join(final_dir, f"{safe_name}_*_joined.mp4")
        return len(glob.glob(pattern)) > 0

    def _on_concat_group(self, group_id: str):
        """Concat all videos in a group into joined files using FFmpeg.
        
        Multi-output support: groups clips by video_index (slot position).
        - 1 output/prompt → 1 joined file (same as before)
        - 2+ outputs/prompt → separate files per track:
          Track A (slot 0): 001a → 002a → 003a
          Track B (slot 1): 001b → 002b → 003b
        """
        import os
        import logging
        from collections import defaultdict
        _log = logging.getLogger("veo.tab_queue")
        
        if not self.controller or not hasattr(self.controller, 'dispatcher'):
            return
        group = self.controller.dispatcher.get_group(group_id)
        if not group:
            return
        
        # ── Collect clips grouped by video_index (track/slot position) ──
        # tracks[video_index] = [(task_idx, file_path)]
        tracks = defaultdict(list)
        missing = []     # [(task_idx, video_index)]
        task_idx = 0
        for task in group.tasks:
            if task.replace_target:
                continue  # Skip replacement tasks
            task_idx += 1
            if not task.video_outputs:
                missing.append((task_idx, 0))
                continue
            for vi, vo in enumerate(task.video_outputs):
                bf = vo.best_file
                if bf and os.path.isfile(bf):
                    tracks[vi].append((task_idx, bf))
                else:
                    missing.append((task_idx, vi))
        
        total_clips = sum(len(t) for t in tracks.values())
        if total_clips == 0:
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast("❌ No video files found in this group", "error")
            return
        
        # Warn about missing videos
        if missing:
            missing_desc = ", ".join(f"#{t}" if v == 0 else f"#{t}-v{v+1}" for t, v in missing)
            if not show_confirm(
                self, "⚠️ Missing Videos",
                f"{len(missing)} video(s) missing: {missing_desc}\n\n"
                f"Concat {total_clips} available clips anyway?",
                danger=False
            ):
                return
        
        # Determine output path
        output_folder = ""
        project_name = ""
        for task in group.tasks:
            if not task.replace_target:
                output_folder = task.output_folder or ""
                project_name = task.project_name or ""
                break
        
        if not output_folder and tracks:
            first_track = tracks[min(tracks.keys())]
            if first_track:
                output_folder = os.path.dirname(first_track[0][1])
        
        # Build output filename base
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        group_name = group.name or "concat"
        import re
        safe_name = re.sub(r'[<>:"/\\|?*]', '', group_name).replace(" ", "_").strip("._")[:50]
        
        if project_name:
            final_dir = os.path.join(output_folder, project_name)
        else:
            final_dir = output_folder
        os.makedirs(final_dir, exist_ok=True)
        
        # Build per-track output paths
        num_tracks = len(tracks)
        track_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        track_paths = {}  # {video_index: final_path}
        for vi in sorted(tracks.keys()):
            if num_tracks == 1:
                # Single track → no suffix (backward compatible)
                track_paths[vi] = os.path.join(final_dir, f"{safe_name}_{ts}_joined.mp4")
            else:
                label = track_labels[vi] if vi < len(track_labels) else str(vi + 1)
                track_paths[vi] = os.path.join(
                    final_dir, f"{safe_name}_{ts}_track{label}_joined.mp4"
                )
        
        # ── Check for existing joined files (prevent accidental re-join) ──
        existing_files = []
        # Also scan for ANY previous joined files with same group name
        import glob
        for vi, path in track_paths.items():
            if os.path.isfile(path):
                existing_files.append(path)
        # Scan for older timestamps with same pattern
        old_pattern = os.path.join(final_dir, f"{safe_name}_*_joined.mp4")
        if num_tracks > 1:
            old_pattern_track = os.path.join(final_dir, f"{safe_name}_*_track*_joined.mp4")
            old_files = glob.glob(old_pattern) + glob.glob(old_pattern_track)
        else:
            old_files = glob.glob(old_pattern)
        # Deduplicate and exclude current paths
        old_files = [f for f in set(old_files) if f not in track_paths.values()]
        
        if existing_files or old_files:
            all_existing = existing_files + old_files
            file_list = "\n".join(
                f"  • {os.path.basename(f)} ({os.path.getsize(f) / 1024 / 1024:.1f} MB)"
                for f in all_existing if os.path.isfile(f)
            )
            count = len(all_existing)
            if not show_confirm(
                self, "⚠️ Joined File Already Exists",
                f"{count} joined file(s) already exist:\n\n{file_list}\n\n"
                f"Join again? (new files will overwrite current output)",
                danger=True
            ):
                return
        
        # Get FFmpeg path
        try:
            from core.frame_extractor import get_ffmpeg_path
            ffmpeg_path = get_ffmpeg_path()
        except ImportError:
            ffmpeg_path = None
        
        if not ffmpeg_path:
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast("❌ FFmpeg not available", "error")
            return
        
        # Show progress toast
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            if num_tracks == 1:
                mw.show_toast(f"⏳ Joining {total_clips} clips...", "info")
            else:
                mw.show_toast(
                    f"⏳ Joining {num_tracks} tracks × {len(tracks[min(tracks.keys())])} clips...",
                    "info"
                )
        
        # Run FFmpeg in background thread — one concat per track
        import threading
        def _run_concat():
            import subprocess
            success_tracks = []
            failed_tracks = []
            total_size = 0.0
            
            for vi in sorted(tracks.keys()):
                track_clips = tracks[vi]
                final_path = track_paths[vi]
                label = track_labels[vi] if vi < len(track_labels) else str(vi + 1)
                
                try:
                    concat_list = os.path.join(
                        final_dir, f"_concat_{ts}_track{label}.txt"
                    )
                    with open(concat_list, "w", encoding="utf-8") as f:
                        for _, path in track_clips:
                            safe = path.replace("\\", "/")
                            f.write(f"file '{safe}'\n")
                    
                    cmd = [
                        ffmpeg_path, "-y",
                        "-f", "concat", "-safe", "0",
                        "-i", concat_list,
                        "-c", "copy",
                        final_path,
                    ]
                    
                    result = subprocess.run(
                        cmd, capture_output=True, text=True,
                        encoding='utf-8', errors='replace',
                        timeout=600,
                        creationflags=(
                            subprocess.CREATE_NO_WINDOW
                            if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                        ),
                    )
                    
                    # Cleanup concat list
                    try:
                        os.remove(concat_list)
                    except OSError:
                        pass
                    
                    if result.returncode == 0 and os.path.isfile(final_path):
                        size_mb = os.path.getsize(final_path) / 1024 / 1024
                        total_size += size_mb
                        success_tracks.append((label, len(track_clips), final_path, size_mb))
                        _log.info(
                            f"[Queue] JOIN track {label}: ✅ "
                            f"{len(track_clips)} clips → {final_path} ({size_mb:.1f} MB)"
                        )
                    else:
                        err = result.stderr[:200] if result.stderr else "Unknown"
                        failed_tracks.append((label, err))
                        _log.error(f"[Queue] JOIN track {label}: ❌ FFmpeg: {err}")
                        
                except subprocess.TimeoutExpired:
                    failed_tracks.append((label, "Timeout >10 min"))
                    _log.error(f"[Queue] JOIN track {label}: ❌ timeout")
                except Exception as e:
                    failed_tracks.append((label, str(e)))
                    _log.error(f"[Queue] JOIN track {label}: ❌ {e}")
            
            # Report results on main thread
            # ★ FIX: Use QMetaObject.invokeMethod instead of QTimer.singleShot
            # QTimer.singleShot from a non-Qt thread is unreliable — the timer
            # has affinity to the calling thread which has no event loop.
            # QMetaObject.invokeMethod with QueuedConnection is Qt's approved
            # cross-thread dispatch mechanism.
            from PySide6.QtCore import QMetaObject, Qt as _Qt, Q_ARG
            if success_tracks and not failed_tracks:
                # All tracks succeeded
                _first_path = success_tracks[0][2]
                _n_tracks = len(success_tracks)
                _n_missing = len(missing)
                def _cb_ok():
                    self._on_concat_complete(
                        True, _first_path, total_clips, total_size,
                        _n_missing, num_tracks=_n_tracks,
                        group_id=group_id
                    )
                QMetaObject.invokeMethod(self, _cb_ok, _Qt.ConnectionType.QueuedConnection)
            elif success_tracks:
                # Partial success
                _first_path = success_tracks[0][2]
                _fail_info = "; ".join(f"Track {l}: {e}" for l, e in failed_tracks)
                _n_tracks = len(success_tracks)
                _n_missing = len(missing)
                def _cb_partial():
                    self._on_concat_complete(
                        True, _first_path, total_clips, total_size,
                        _n_missing, num_tracks=_n_tracks,
                        partial_fail=_fail_info, group_id=group_id
                    )
                QMetaObject.invokeMethod(self, _cb_partial, _Qt.ConnectionType.QueuedConnection)
            else:
                # All failed
                _fail_info = "; ".join(f"Track {l}: {e}" for l, e in failed_tracks)
                _n_missing = len(missing)
                def _cb_fail():
                    self._on_concat_complete(
                        False, _fail_info, total_clips, 0, _n_missing,
                        group_id=group_id
                    )
                QMetaObject.invokeMethod(self, _cb_fail, _Qt.ConnectionType.QueuedConnection)
        
        _concat_thread = threading.Thread(target=_run_concat, daemon=True)
        _concat_thread.start()
    
    def _on_concat_complete(self, success: bool, path_or_error: str,
                            clip_count: int, size_mb: float, missing_count: int,
                            *, num_tracks: int = 1, partial_fail: str = "",
                            group_id: str = ""):
        """Handle concat completion on main thread."""
        import logging as _lg
        _clog = _lg.getLogger("veo.tab_queue")
        _clog.info(f"[Queue] _on_concat_complete called: success={success}, group_id={group_id}, clips={clip_count}")
        mw = self.window()
        if success:
            missing_note = f" ({missing_count} missing)" if missing_count else ""
            if num_tracks > 1:
                msg = f"✅ Joined {num_tracks} tracks ({clip_count} clips){missing_note} → {size_mb:.1f} MB"
            else:
                msg = f"✅ Joined {clip_count} clips{missing_note} → {size_mb:.1f} MB"
            if partial_fail:
                msg += f"\n⚠️ {partial_fail}"
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast(msg, "success")
            # ★ Update JOIN button → outline blue + "JOINED"
            if group_id:
                gw = self._group_widgets.get(group_id)
                if gw:
                    # Set persistent flag — survives refresh cycles
                    gw['_join_done'] = True
                    # Find JOIN button dynamically (works even without stored ref)
                    join_btn = gw.get('join_btn')
                    if not join_btn:
                        header = gw.get('header')
                        if header:
                            for child in header.findChildren(QPushButton):
                                if child.text() in ("JOIN", "JOINED"):
                                    join_btn = child
                                    break
                    if join_btn:
                        try:
                            join_btn.setText("JOINED")
                            join_btn.setStyleSheet(f"""
                                QPushButton {{
                                    background: transparent;
                                    color: {Theme.BLUE};
                                    border: 1px solid {Theme.BLUE};
                                    border-radius: 4px;
                                    font-family: 'Segoe UI';
                                    font-size: 10px;
                                    font-weight: bold;
                                    padding: 2px;
                                }}
                                QPushButton:hover {{
                                    background-color: {Theme.BLUE};
                                    border-color: {Theme.BLUE};
                                    color: {Theme.CRUST};
                                }}
                            """)
                            _clog.info(f"[Queue] JOIN btn → JOINED ✅ (gid={group_id})")
                        except RuntimeError:
                            pass
                    else:
                        _clog.warning(f"[Queue] JOIN btn NOT FOUND for gid={group_id}")
            # Open output folder
            import os, subprocess
            folder = os.path.dirname(path_or_error)
            if os.path.isdir(folder):
                subprocess.Popen(['explorer', '/select,', os.path.normpath(path_or_error)])
        else:
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast(f"❌ Concat failed: {path_or_error[:100]}", "error")

