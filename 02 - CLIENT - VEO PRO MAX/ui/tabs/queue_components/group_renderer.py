"""
Queue Group Renderer — group widgets, headers, child rows, setup dialog.

Mixin class for TabQueue. All methods operate on `self` (the TabQueue instance).
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
)
from ui.popups import show_confirm
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class QueueGroupMixin:
    """Mixin providing group rendering, header updates, and group operations."""
    
    def _create_group_widget(self, group_data: dict, expanded: bool = True) -> QWidget:
        """Create a collapsible group widget with header + child prompt rows."""
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
        
        mode_label = QLabel(f"{mode_icon} {group_data.get('mode', 'T2V')}")
        mode_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
        h_layout.addWidget(mode_label)
        
        model_raw = group_data.get('model', '')
        model_short = model_raw.replace('veo_3_1_generate', 'Veo 3.1').replace('veo_3_0_generate', 'Veo 3.0').replace('_', ' ') if model_raw else ''
        if model_short:
            model_label = QLabel(model_short)
            model_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
            h_layout.addWidget(model_label)
        
        # Header buttons
        for btn_text, btn_tip, btn_color, btn_connect in [
            ("⚒️", "Setup: change model, aspect ratio, output folder, outputs", Theme.BLUE,
             lambda checked, _gid=gid, _gd=group_data: self._on_setup_group(_gid, _gd)),
            ("RST", "Reset group: delete all downloads & cache, re-queue", Theme.YELLOW,
             lambda checked, _gid=gid: self._on_reset_group(_gid)),
            ("DEL", "Delete entire group", Theme.SUBTEXT0,
             lambda checked, _gid=gid: self._on_delete_group(_gid)),
        ]:
            btn = QPushButton(btn_text)
            btn.setFixedSize(36 if btn_text != "⚒️" else 32, 24)
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
            h_layout.addWidget(btn)
        
        container_layout.addWidget(header)
        
        # === CHILD CONTENT ===
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(1)
        
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
        
        content.setVisible(expanded)
        container_layout.addWidget(content)
        
        self._group_widgets[gid] = {
            'container': container, 'header': header, 'content': content,
            'arrow': arrow, 'name_label': name_label,
            'progress_label': progress_label, 'group_data': group_data,
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
        gw['name_label'].setStyleSheet(self._name_label_style(pct))
        
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
    
    def _rebuild_group_children(self, gw: dict, group_data: dict):
        """Differential update: reuse existing row widgets, only create/remove as needed."""
        content = gw['content']
        layout = content.layout()
        new_tasks = group_data.get('tasks', [])
        new_task_ids = {str(td['id']) for td in new_tasks}
        
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
    
    def _update_task_widget_data(self, widget: QFrame, td: dict):
        """Update an existing task row widget with new data (no destroy/recreate)."""
        try:
            new_status = td.get('status', 'running')
            widget._task_status = new_status
            if hasattr(widget, 'status_label'):
                self._update_status_label(widget, td)
            if hasattr(widget, 'thumb_slots'):
                self._update_thumb_slot_data(widget, td)
            
            # Toggle retry button visibility based on new status
            if hasattr(widget, 'retry_btn'):
                if new_status in ('failed', 'cancelled'):
                    widget.retry_btn.show()
                else:
                    widget.retry_btn.hide()
            
            # Update left border accent color
            status_colors = {
                'ready': Theme.SUBTEXT0, 'pending': Theme.SUBTEXT0,
                'waiting': Theme.YELLOW if hasattr(Theme, 'YELLOW') else Theme.SUBTEXT0,
                'running': Theme.BLUE, 'waiting_poll': Theme.BLUE,
                'completed': Theme.GREEN, 'failed': Theme.RED,
                'cancelled': Theme.SUBTEXT0,
            }
            accent = status_colors.get(new_status, Theme.SUBTEXT0)
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
    
    def _update_status_label(self, widget, td):
        """Update the status label on a task row widget."""
        status = td.get('status', '')
        progress = td.get('progress', 0)
        video_outputs = td.get('video_outputs', [])
        
        if progress >= 100:
            retrying_count = sum(1 for vo in video_outputs if vo.get('quality') == 'retrying')
            if retrying_count > 0:
                widget.status_label.setText(f"♻️ RETRYING {retrying_count}/{len(video_outputs)}")
                widget.status_label.setStyleSheet(
                    f"color: {Theme.PURPLE}; font-size: 10px; font-weight: bold; border: none;"
                )
            else:
                widget.status_label.setText("✅ DONE")
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
            widget.status_label.setText("❌ FAILED")
            error_msg = td.get('error', '')
            if error_msg:
                widget.status_label.setToolTip(error_msg)
            widget.status_label.setStyleSheet(
                f"color: {Theme.RED}; font-size: 10px; font-weight: bold; border: none;"
            )
        else:
            icons = {'ready': '⏳', 'pending': '⏳', 'waiting': '🔗', 'cancelled': '⛔'}
            icon = icons.get(status, '⏳')
            color = Theme.YELLOW if status == 'waiting' else Theme.SUBTEXT0
            widget.status_label.setText(f"{icon} {status.upper()}")
            widget.status_label.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: bold; border: none;"
            )
    
    def _update_thumb_slot_data(self, widget, td):
        """Update thumbnail slot rendering on an existing widget."""
        progress = td.get('progress', 0)
        thumbnails = td.get('thumbnails', [])
        video_outputs = td.get('video_outputs', [])
        status = td.get('status', '')
        
        for i, slot in enumerate(widget.thumb_slots):
            vi = video_outputs[i] if i < len(video_outputs) else None
            slot._video_info = vi
            if vi:
                slot._border_color_name = vi.get('border_color', 'gray')
        
        if progress == 0 and status in ('ready', 'pending') and not video_outputs:
            for slot in widget.thumb_slots:
                try:
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
                    bc = self._slot_border(slot, Theme.GREEN)
                    is_failed = vi and vi.get('upscale_status') == 'failed'
                    
                    quality = vi.get('quality', '') if vi else ''
                    us = vi.get('upscale_status', '') if vi else ''
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
                    self._apply_thumb_effect(slot, progress, status)
                except RuntimeError:
                    continue
    
    def _toggle_group(self, group_id: str):
        """Toggle expand/collapse of a group."""
        gw = self._group_widgets.get(group_id)
        if not gw:
            return
        expanded = not self._group_expanded.get(group_id, True)
        self._group_expanded[group_id] = expanded
        gw['content'].setVisible(expanded)
        gw['arrow'].setText("▼" if expanded else "▶")
    
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
                background-color: {Theme.SURFACE0}; color: {Theme.TEXT};
                border: 1px solid {Theme.SURFACE2}; border-radius: 6px;
                padding: 6px 10px; min-height: 28px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {Theme.BLUE}; }}
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title = QLabel(f"⚒️ Adjust settings for group: {group_data.get('name', group_id)}")
        title.setStyleSheet(f"color: {Theme.TEXT}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        layout.addWidget(QLabel("🤖 AI Model"))
        model_combo = QComboBox()
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
        
        layout.addWidget(QLabel("📐 Aspect Ratio"))
        ar_combo = QComboBox()
        ar_combo.addItems(["16:9 (Landscape)", "9:16 (Portrait)"])
        if 'PORTRAIT' in group_data.get('aspect_ratio', '').upper():
            ar_combo.setCurrentIndex(1)
        layout.addWidget(ar_combo)
        
        layout.addWidget(QLabel("📂 Output Folder"))
        folder_row = QHBoxLayout()
        folder_input = QLineEdit()
        folder_input.setText(group_data.get('output_folder', ''))
        folder_row.addWidget(folder_input)
        browse_btn = QPushButton("📂")
        browse_btn.setFixedSize(36, 28)
        browse_btn.clicked.connect(
            lambda: folder_input.setText(QFileDialog.getExistingDirectory(dialog, "Select Output Folder") or folder_input.text())
        )
        folder_row.addWidget(browse_btn)
        layout.addLayout(folder_row)
        
        layout.addWidget(QLabel("🎬 Outputs per Prompt"))
        output_combo = QComboBox()
        output_combo.addItems(["1 video", "2 videos", "3 videos", "4 videos"])
        output_combo.setCurrentIndex(max(0, min(group_data.get('output_count', 4) - 1, 3)))
        layout.addWidget(output_combo)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(100, 36)
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("✅ Apply")
        apply_btn.setFixedSize(120, 36)
        apply_btn.setStyleSheet(f"QPushButton {{ background-color: {Theme.BLUE}; color: {Theme.CRUST}; border-radius: 8px; font-weight: bold; }}")
        
        def _apply_settings():
            from config.constants import resolve_model_key, WorkflowType
            ar_text = ar_combo.currentText()
            ar_value = "PORTRAIT" if "Portrait" in ar_text else "LANDSCAPE"
            mode = group_data.get('mode', 'T2V')
            wf = getattr(WorkflowType, mode, WorkflowType.T2V)
            try:
                model_key = resolve_model_key(model_combo.currentText(), wf, ar_value, False)
            except Exception:
                model_key = model_combo.currentText()
            ar_api = "VIDEO_ASPECT_RATIO_PORTRAIT" if ar_value == "PORTRAIT" else "VIDEO_ASPECT_RATIO_LANDSCAPE"
            settings = {
                'model': model_key, 'aspect_ratio': ar_api,
                'output_folder': folder_input.text().strip(),
                'output_count': int(output_combo.currentText().split()[0]),
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
    
    def _on_reset_group(self, group_id: str):
        """Reset all tasks in a group."""
        if not self.controller or not hasattr(self.controller, 'dispatcher'):
            return
        group = self.controller.dispatcher.get_group(group_id)
        if not group:
            return
        if not show_confirm(self, "Reset Group",
                "Reset incomplete/failed prompts in this group?\n\nCompleted tasks will be PRESERVED.",
                danger=True):
            return
        count = 0
        for task in group.tasks:
            if task.state.value in ('completed', 'running', 'waiting_poll'):
                continue
            if hasattr(self.controller, 'force_retry_task'):
                if self.controller.force_retry_task(str(task.id)):
                    count += 1
        self._refresh_queue_from_controller()
        self._update_stats()
        print(f"[Queue] Force-retried group {group_id}: {count}/{len(group.tasks)} tasks")
        mw = self.window()
        if mw and hasattr(mw, 'show_toast'):
            mw.show_toast(f"Force-retried {count} prompts — re-queued", "info")
    
    def _on_delete_group(self, group_id: str):
        """Delete an entire task group and all its tasks."""
        gw = self._group_widgets.get(group_id)
        if not gw:
            return
        if not show_confirm(self, "Delete Group",
                "Delete this group and all its tasks?", danger=True):
            return
        if self.controller and hasattr(self.controller, 'dispatcher'):
            dispatcher = self.controller.dispatcher
            group = dispatcher.get_group(group_id)
            if group:
                for task in group.tasks:
                    if hasattr(dispatcher, 'cancel_task'):
                        dispatcher.cancel_task(task.id)
                    self._queue_items = [i for i in self._queue_items if i.id != task.id]
                    w = self._item_widgets.pop(task.id, None)
                    if w:
                        w.deleteLater()
                dispatcher.remove_group(group_id)
        gw['container'].deleteLater()
        self._group_widgets.pop(group_id, None)
        self._group_expanded.pop(group_id, None)
        self._update_stats()
        print(f"[Queue] Deleted group: {group_id}")
