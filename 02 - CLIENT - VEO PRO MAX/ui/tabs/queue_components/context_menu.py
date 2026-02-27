"""
Queue Context Menus — right-click menus for task rows and thumbnail slots.

Mixin class for TabQueue. All methods operate on `self` (the TabQueue instance).
"""

from pathlib import Path

from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtCore import Qt

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class QueueContextMenuMixin:
    """Mixin providing context menu logic for queue task rows and thumbnail slots."""
    
    def _create_styled_menu(self) -> 'QMenu':
        """Create a QMenu with unified Catppuccin styling."""
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
        return menu
    
    def _show_task_context_menu(self, pos, task_id, widget):
        """Right-click context menu for a TASK ROW."""
        menu = self._create_styled_menu()
        
        task_data, group_data = None, None
        if self.controller and hasattr(self.controller, 'get_queue_groups'):
            for group in self.controller.get_queue_groups():
                for td in group.get('tasks', []):
                    if str(td.get('id', '')) == str(task_id):
                        task_data, group_data = td, group
                        break
                if task_data:
                    break
        
        task_status = task_data.get('status', '') if task_data else ''
        download_quality = task_data.get('download_quality', '720p') if task_data else '720p'
        video_outputs = task_data.get('video_outputs', []) if task_data else []
        has_upscale_quality = download_quality.upper() in ('1080P', '4K', '2K')
        
        failed_count = sum(
            1 for vo in video_outputs
            if vo.get('quality') in ('failed', 'pending', '')
            or vo.get('upscale_status') == 'failed'
        )
        failed_upscale_count = sum(1 for vo in video_outputs if vo.get('upscale_status') == 'failed')
        total_videos = len(video_outputs)
        
        if task_status != 'running':
            if 0 < failed_count < total_videos:
                retry_label = f"♻️ Retry {failed_count} Failed Video(s)"
            else:
                retry_label = "🔄 Force Retry (re-generate all)"
            menu.addAction(retry_label).triggered.connect(
                lambda: self._on_force_retry_item(task_id)
            )
        
        if task_status == 'completed' and video_outputs:
            menu.addAction("⬇️ Re-download All 720p").triggered.connect(
                lambda: self._on_redownload_720p_item(task_id)
            )
        
        if task_status == 'completed' and has_upscale_quality:
            menu.addSeparator()
            if failed_upscale_count > 0:
                menu.addAction(
                    f"⬆️ Re-Upscale Failed ({failed_upscale_count}/{total_videos}) → {download_quality}"
                ).triggered.connect(lambda: self._on_reupscale_item(task_id, True))
            menu.addAction(f"⬆️ Re-Upscale All → {download_quality}").triggered.connect(
                lambda: self._on_reupscale_item(task_id, False)
            )
        
        output_folder = group_data.get('output_folder', '') if group_data else ''
        if output_folder:
            menu.addSeparator()
            menu.addAction("📂 Open Output Folder").triggered.connect(
                lambda: self._open_group_folder(output_folder)
            )
        
        # --- Data reuse actions ---
        menu.addSeparator()
        menu.addAction("📋 Clone Prompt").triggered.connect(
            lambda: self._on_clone_task(task_id)
        )
        menu.addAction("💾 Export Task Config").triggered.connect(
            lambda: self._on_export_task_config(task_id)
        )
        
        # Fork continuation (only for completed video tasks with continuation frame)
        if task_status == 'completed' and task_data:
            cont_frame = task_data.get('continuation_frame_local_path') or task_data.get('continuation_frame_uri')
            if cont_frame:
                menu.addAction("🔀 Fork from this frame").triggered.connect(
                    lambda: self._on_fork_continuation(task_id)
                )
        
        menu.exec(widget.mapToGlobal(pos))
    
    def _on_force_retry_item(self, item_id):
        """Force retry a task — smart per-video retry for failed videos only."""
        task_id = str(item_id)
        task_data = None
        if hasattr(self.controller, 'get_queue_groups'):
            for g in self.controller.get_queue_groups():
                for td in g.get('tasks', []):
                    if td.get('id') == task_id:
                        task_data = td
                        break
                if task_data:
                    break
        
        video_outputs = task_data.get('video_outputs', []) if task_data else []
        
        if video_outputs and self.controller and hasattr(self.controller, 'force_retry_video'):
            failed_indices = [
                i for i, vo in enumerate(video_outputs)
                if vo.get('quality', '') in ('failed', 'pending', '') or vo.get('upscale_status') == 'failed'
            ]
            if failed_indices and len(failed_indices) < len(video_outputs):
                retried = sum(1 for idx in failed_indices if self.controller.force_retry_video(task_id, idx))
                if retried > 0:
                    self._refresh_queue_from_controller()
                    self._update_stats()
                    mw = self.window()
                    if mw and hasattr(mw, 'show_toast'):
                        mw.show_toast(f"♻️ Retrying {retried} failed video(s)", "info")
                    return
        
        if self.controller and hasattr(self.controller, 'force_retry_task'):
            success = self.controller.force_retry_task(task_id)
            self._refresh_queue_from_controller()
            self._update_stats()
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                msg = f"🔄 Force retrying prompt #{item_id}" if success else f"Cannot force retry #{item_id}"
                mw.show_toast(msg, "info" if success else "warning")
    
    def _on_delete_item(self, item_id):
        """Delete a specific task."""
        task_id = str(item_id)
        if self.controller and hasattr(self.controller, 'cancel_task'):
            self.controller.cancel_task(task_id)
        if self.controller and hasattr(self.controller, 'dispatcher'):
            disp = self.controller.dispatcher
            disp._all_tasks.pop(task_id, None)
            for group in disp._task_groups.values():
                group.tasks = [t for t in group.tasks if t.id != task_id]
        tw = self._task_widgets.pop(task_id, None)
        if tw:
            tw.deleteLater()
        self._item_widgets.pop(item_id, None)
        self._queue_items = [i for i in self._queue_items if str(i.id) != task_id]
        self._refresh_queue_from_controller()
        self._update_stats()
    
    def _on_reupscale_item(self, item_id, failed_only: bool = True):
        """Re-upscale videos in a completed task."""
        if self.controller and hasattr(self.controller, 're_upscale_task'):
            self.controller.re_upscale_task(str(item_id), failed_only=failed_only)
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast(f"⬆️ Re-upscaling {'failed' if failed_only else 'all'} videos...", "info")
    
    def _on_redownload_720p_item(self, item_id):
        """Re-download 720p videos."""
        if self.controller and hasattr(self.controller, 're_download_720p'):
            self.controller.re_download_720p(str(item_id))
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast("⬇️ Re-downloading 720p videos...", "info")
    
    def _on_clone_task(self, task_id):
        """Clone a task — create a fresh copy with same input."""
        if self.controller and hasattr(self.controller, 'clone_task'):
            new_id = self.controller.clone_task(str(task_id))
            if new_id:
                self._refresh_queue_from_controller()
                self._update_stats()
                mw = self.window()
                if mw and hasattr(mw, 'show_toast'):
                    mw.show_toast("📋 Prompt cloned and queued", "success")
    
    def _on_export_task_config(self, task_id):
        """Export task configuration as JSON."""
        if not self.controller or not hasattr(self.controller, 'export_task_config'):
            return
        config = self.controller.export_task_config(str(task_id))
        if not config:
            return
        from PySide6.QtWidgets import QFileDialog
        import json
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Task Config", f"task_{task_id}.json",
            "JSON files (*.json)"
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast(f"💾 Config exported to {Path(path).name}", "success")
    
    def _on_fork_continuation(self, task_id):
        """Fork continuation — create new task from completed task's frame."""
        if not self.controller or not hasattr(self.controller, 'fork_continuation'):
            return
        from ui.popups import RenameDialog
        dlg = RenameDialog(self, title="Fork Continuation", placeholder="Enter new prompt...")
        if dlg.exec():
            new_prompt = dlg.get_result()
            if new_prompt and new_prompt.strip():
                new_id = self.controller.fork_continuation(str(task_id), 0, new_prompt)
                if new_id:
                    self._refresh_queue_from_controller()
                    self._update_stats()
                    mw = self.window()
                    if mw and hasattr(mw, 'show_toast'):
                        mw.show_toast("🔀 Forked continuation queued", "success")
    
    def _show_video_context_menu(self, pos, video_info: dict, parent_widget):
        """Right-click context menu on a THUMBNAIL SLOT."""
        menu = self._create_styled_menu()
        idx = video_info.get('index', 0)
        bc = video_info.get('border_color', 'gray')
        quality = video_info.get('quality', '')
        target_q = video_info.get('target_quality', '1080p')
        task_id = video_info.get('task_id', '')
        best_file = video_info.get('best_file', '')
        has_upscale = target_q.upper() in ('1080P', '4K', '2K')
        is_failed = bc == 'red' or quality in ('failed', 'retrying') or video_info.get('upscale_status') == 'failed'
        
        # Detect image vs video by file extension or quality label
        is_image = (
            quality.upper() in ('1K', '2K')
            or (best_file and Path(best_file).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'))
        )
        item_label = "Image" if is_image else "Video"
        
        status_map = {
            'red': f"❌ {item_label} {idx+1}: {video_info.get('upscale_error','failed')}",
            'blue': f"✅ {item_label} {idx+1}: {quality}",
            'yellow': f"🟡 {item_label} {idx+1}: {quality or '720p'}",
            'purple': f"♻️ {item_label} {idx+1}: processing",
        }
        info_action = menu.addAction(status_map.get(bc, f"⏳ Video {idx+1}: pending"))
        info_action.setEnabled(False)
        menu.addSeparator()
        
        retry_label = "♻️ Retry This Video (re-generate)" if is_failed else "🔄 Re-generate This Video"
        menu.addAction(retry_label).triggered.connect(
            lambda c=False, t=task_id, i=idx, s=parent_widget: self._on_retry_single_video(t, i, s)
        )
        
        if has_upscale and bc in ('yellow', 'red', 'blue'):
            label = "Upscale" if bc == 'yellow' else "Re-Upscale"
            menu.addAction(f"⬆️ {label} → {target_q}").triggered.connect(
                lambda c=False, t=task_id, i=idx, s=parent_widget: self._on_reupscale_single_video(t, i, s)
            )
        
        if quality not in ('', 'pending', 'retrying', 'failed'):
            menu.addAction("⬇️ Re-download 720p").triggered.connect(
                lambda c=False, t=task_id, i=idx, s=parent_widget: self._on_redownload_single_720p(t, i, s)
            )
        
        if best_file and self._cached_file_exists(best_file):
            menu.addSeparator()
            menu.addAction("📂 Open in Explorer").triggered.connect(
                lambda: self._open_file_in_explorer(best_file)
            )
            
            # Add to Image Library — only for image files
            if Path(best_file).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                menu.addAction("🖼️ Add to Image Library").triggered.connect(
                    lambda c=False, f=best_file: self._on_add_to_library(f)
                )
        
        menu.exec(parent_widget.mapToGlobal(pos))
    
    def _on_reupscale_single_video(self, task_id, video_index, slot=None):
        """Re-upscale a single video by index."""
        if self.controller and hasattr(self.controller, 're_upscale_single_video'):
            self.controller.re_upscale_single_video(str(task_id), video_index)
            if slot:
                self._apply_processing_overlay(slot, "⬆️", Theme.PURPLE)
                slot._border_color_name = 'purple'
                self._register_upscale_spinner(slot)
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast(f"⬆️ Re-upscaling video {video_index+1}...", "info")
    
    def _on_retry_single_video(self, task_id, video_index, slot=None):
        """Retry a single failed video."""
        if self.controller and hasattr(self.controller, 'force_retry_video'):
            success = self.controller.force_retry_video(task_id, video_index)
            if success and slot:
                self._apply_processing_overlay(slot, "♻️", Theme.PURPLE)
            self._refresh_queue_from_controller()
            self._update_stats()
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                msg = f"♻️ Retrying video {video_index+1}" if success else f"Cannot retry video {video_index+1}"
                mw.show_toast(msg, "info" if success else "warning")
    
    def _on_redownload_single_720p(self, task_id, video_index, slot=None):
        """Re-download a single 720p video."""
        if self.controller and hasattr(self.controller, 're_download_single_720p'):
            self.controller.re_download_single_720p(str(task_id), video_index)
            if slot:
                self._apply_processing_overlay(slot, "⬇️", Theme.SAPPHIRE)
                slot._border_color_name = 'blue'
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast(f"⬇️ Re-downloading video {video_index+1} (720p)...", "info")
    
    def _apply_processing_overlay(self, slot: QLabel, icon: str, color: str):
        """Apply a dark overlay with icon on a thumbnail slot."""
        try:
            if slot.pixmap() and not slot.pixmap().isNull():
                pixmap = slot.pixmap().copy()
                overlay = QPixmap(pixmap.size())
                overlay.fill(QColor(0, 0, 0, 0))
                painter = QPainter(overlay)
                painter.drawPixmap(0, 0, pixmap)
                painter.fillRect(overlay.rect(), QColor(0, 0, 0, 140))
                painter.setPen(QColor(color))
                font = QFont("Segoe UI", 10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(overlay.rect(), Qt.AlignCenter, icon)
                painter.end()
                slot.setPixmap(overlay)
            else:
                slot.setText('')
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.SURFACE0};
                    border: 2px solid {color};
                    border-radius: 4px;
                    color: {color};
                    font-size: 14px;
                }}
            """)
        except (RuntimeError, Exception):
            pass
    
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
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast("⚠️ No output folder configured", "warning")
            return
        from PySide6.QtCore import QUrl
        try:
            from PySide6.QtGui import QDesktopServices
        except ImportError:
            QDesktopServices = None
        folder = Path(folder_path)
        if folder.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            parent = folder.parent
            if parent.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent)))
    
    def _on_add_to_library(self, file_path: str):
        """Add an image file to the Image Library with tag input dialog."""
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
            QPushButton, QComboBox, QDialogButtonBox,
        )
        from PySide6.QtGui import QPixmap
        
        try:
            from services.image_library import get_image_library
            library = get_image_library()
        except Exception:
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast("⚠️ Image Library not available", "warning")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("🖼️ Add to Image Library")
        dialog.setFixedSize(400, 340)
        dialog.setStyleSheet(f"background-color: {Theme.BASE}; color: {Theme.TEXT};")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        # Image preview
        preview = QLabel()
        preview.setFixedSize(200, 200)
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet(
            f"background-color: {Theme.SURFACE0}; border: 1px solid {Theme.SURFACE2}; border-radius: 8px;"
        )
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(196, 196, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            preview.setPixmap(scaled)
        
        preview_row = QHBoxLayout()
        preview_row.addStretch()
        preview_row.addWidget(preview)
        preview_row.addStretch()
        layout.addLayout(preview_row)
        
        # File name
        name_label = QLabel(f"📄 {Path(file_path).name}")
        name_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)
        
        # Tag input
        tag_label = QLabel("Tags (comma separated):")
        tag_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        layout.addWidget(tag_label)
        
        tag_input = QLineEdit(Path(file_path).stem)
        tag_input.setMinimumHeight(32)
        tag_input.setPlaceholderText("e.g. cat, sunset, hero")
        tag_input.setStyleSheet(
            f"background-color: {Theme.SURFACE0}; color: {Theme.TEXT}; "
            f"border: 1px solid {Theme.SURFACE2}; border-radius: 4px; padding: 4px 8px;"
        )
        layout.addWidget(tag_input)
        
        # Category combo
        cat_row = QHBoxLayout()
        cat_lbl = QLabel("Category:")
        cat_lbl.setStyleSheet(f"color: {Theme.TEXT};")
        cat_row.addWidget(cat_lbl)
        
        cat_combo = QComboBox()
        cat_combo.setStyleSheet(f"background-color: {Theme.SURFACE1}; color: {Theme.TEXT};")
        for cat in library.get_categories():
            cat_combo.addItem(cat)
        cat_row.addWidget(cat_combo, stretch=1)
        layout.addLayout(cat_row)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        tag_input.setFocus()
        tag_input.selectAll()
        
        if dialog.exec() == QDialog.Accepted:
            tags = [t.strip() for t in tag_input.text().split(",") if t.strip()]
            if not tags:
                tags = [Path(file_path).stem]
            category = cat_combo.currentText()
            library.add_image(file_path, tags=tags, category=category)
            mw = self.window()
            if mw and hasattr(mw, 'show_toast'):
                mw.show_toast(f"🖼️ Added to library: [{tags[0]}]", "success")

