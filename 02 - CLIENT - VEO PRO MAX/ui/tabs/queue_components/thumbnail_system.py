"""
Queue Thumbnail System — pixmap cache, file existence checks, thumb slot creation.

Mixin class for TabQueue. All methods operate on `self` (the TabQueue instance).
"""

import time
from pathlib import Path

from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PySide6.QtGui import QPixmap, QCursor
from PySide6.QtCore import Qt

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class QueueThumbnailMixin:
    """Mixin providing thumbnail slot creation and caching.
    
    Expects host to provide:
    - self._pixmap_cache, self._pixmap_cache_max
    - self._file_exists_cache, self._file_exists_ttl
    - self._input_pulse_thumbs, self._input_pulse_phase
    """
    
    # ── Performance Caches ───────────────────────────────────────
    
    def _cached_file_exists(self, path: str) -> bool:
        """Check if file exists with 10s TTL cache to avoid disk I/O on main thread."""
        if not path:
            return False
        now = time.monotonic()
        entry = self._file_exists_cache.get(path)
        if entry and (now - entry[1]) < self._file_exists_ttl:
            return entry[0]
        exists = Path(path).exists()
        self._file_exists_cache[path] = (exists, now)
        return exists
    
    def _invalidate_file_cache(self, path: str):
        """Invalidate file existence cache when a file is newly created."""
        self._file_exists_cache.pop(path, None)
    
    def _get_cached_pixmap(self, path: str, size: int = 40) -> 'QPixmap':
        """Get scaled QPixmap from LRU cache. Avoids repeated disk decode."""
        cache_key = f"{path}:{size}"
        if cache_key in self._pixmap_cache:
            self._pixmap_cache.move_to_end(cache_key)
            return self._pixmap_cache[cache_key]
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return pixmap
        scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        self._pixmap_cache[cache_key] = scaled
        # Evict oldest entries
        while len(self._pixmap_cache) > self._pixmap_cache_max:
            self._pixmap_cache.popitem(last=False)
        return scaled
    
    # ── Thumb Slot Creation ──────────────────────────────────────
    
    def _create_thumb_slot(self, index: int, status: str, progress: int,
                           thumbnail_path: str = None, video_path: str = None,
                           video_info: dict = None) -> QLabel:
        """Create a single 40×40 thumbnail slot for output video tracking.
        
        State-driven rendering:
        - Pending (gray border, empty) → Generating (shimmer + gradient fill)
        - Generated (green border, thumbnail or ✅) → Click to play
        - Failed (red border, ❌)
        
        Each slot gets a _border_color_name attribute for per-video independence.
        """
        slot = QLabel()
        slot.setFixedSize(40, 40)
        slot.setAlignment(Qt.AlignCenter)
        slot._border_color_name = 'gray'      # Per-slot border tracking
        slot._progress_pct = 0.0              # Per-slot progress for shimmer
        slot._video_info = video_info         # Per-slot video output info
        slot._original_pixmap = None          # For upscale overlay restore
        
        # Determine border color from video_info
        bc_name = 'gray'
        border_color = Theme.SURFACE1     # Default gray for pending
        if video_info:
            bc_name = video_info.get('border_color', 'gray')
            BORDER_COLORS = {
                'gray': Theme.SURFACE1, 'yellow': Theme.YELLOW,
                'blue': Theme.BLUE, 'red': Theme.RED,
                'green': Theme.GREEN, 'purple': Theme.PURPLE,
            }
            border_color = BORDER_COLORS.get(bc_name, Theme.SURFACE1)
        slot._border_color_name = bc_name
        
        if thumbnail_path and self._cached_file_exists(thumbnail_path):
            # Has real thumbnail — show it
            pix = self._get_cached_pixmap(thumbnail_path, 40)
            if not pix.isNull():
                slot.setPixmap(pix)
                slot.setStyleSheet(
                    f"QLabel {{ border: 2px solid {border_color}; border-radius: 4px;"
                    f"background-color: {Theme.BASE}; padding: 1px; }}"
                    f"QLabel:hover {{ border-color: {Theme.LAVENDER}; }}"
                )
                if video_path and self._cached_file_exists(video_path):
                    slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    slot.mousePressEvent = lambda e, p=video_path: self._open_video(p) if e.button() == Qt.MouseButton.LeftButton else None
                
                # Per-video right-click context menu (for completed videos)
                if video_info:
                    self._attach_slot_context_menu(slot, video_info)
                
                return slot
        
        if status in ("completed",) and progress >= 100:
            # Completed without thumbnail — show styled border based on quality
            slot.setText('')
            is_failed = video_info and video_info.get('upscale_status') == 'failed'
            if is_failed:
                slot.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Theme.SURFACE0};
                        border: 2px solid {Theme.RED};
                        border-radius: 4px;
                    }}
                """)
                # Red thumbnails also get right-click context menu
                if video_info:
                    self._attach_slot_context_menu(slot, video_info)
            else:
                slot.setStyleSheet(f"""
                    QLabel {{
                        background-color: {Theme.SURFACE0};
                        border: 2px solid {border_color};
                        border-radius: 4px;
                    }}
                """)
            
            # Click to play if video exists
            if video_path and self._cached_file_exists(video_path):
                slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                slot.mousePressEvent = lambda e, p=video_path: self._open_video(p) if e.button() == Qt.MouseButton.LeftButton else None
            
            return slot
        
        if status in ("running", "waiting_poll"):
            # Generating — register for shimmer animation
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.SURFACE0};
                    border: 1px solid {border_color};
                    border-radius: 4px;
                    color: {Theme.SUBTEXT0};
                    font-size: 10px;
                }}
            """)
            self._register_shimmer_slot(slot)
            return slot
        
        # Default: pending/empty
        slot.setStyleSheet(f"""
            QLabel {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.SURFACE1};
                border-radius: 4px;
                color: {Theme.SUBTEXT0};
                font-size: 10px;
            }}
        """)
        return slot
    
    def _attach_slot_context_menu(self, slot: QLabel, video_info: dict):
        """Attach right-click context menu to a thumbnail slot."""
        slot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        slot.customContextMenuRequested.connect(
            lambda pos, vi=dict(video_info), w=slot: self._show_video_context_menu(pos, vi, w)
        )
    
    def _create_input_thumbs(self, mode: str, task_data: dict = None) -> QWidget:
        """Create input thumbnail container for I2V/R2V/I2I modes.
        
        Shows the input image(s) with small thumbnails (30×30) and pulsing border.
        """
        container = QWidget()
        container.setStyleSheet("border: none; background: transparent;")
        container.setFixedWidth(120)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        if mode not in ('I2V', 'R2V', 'I2I') or not task_data:
            layout.addStretch()
            return container
        
        # Get input image path(s) — field name matches TaskDTO.image_paths
        input_images = task_data.get('image_paths', [])
        
        for img_path in input_images[:3]:  # Max 3 thumbnails
            if img_path and self._cached_file_exists(img_path):
                thumb = QLabel()
                thumb.setFixedSize(30, 30)
                thumb.setAlignment(Qt.AlignCenter)
                pix = self._get_cached_pixmap(img_path, 30)
                if not pix.isNull():
                    thumb.setPixmap(pix)
                    thumb.setStyleSheet(f"""
                        QLabel {{
                            border: 1px solid {Theme.BLUE};
                            border-radius: 4px;
                            background-color: {Theme.BASE};
                            padding: 1px;
                        }}
                    """)
                    thumb.setToolTip(f"Input: {Path(img_path).name}")
                    # Register for pulse animation
                    self._input_pulse_thumbs.append(thumb)
                    layout.addWidget(thumb)
        
        layout.addStretch()
        return container
    
    def _update_thumb_slots(self, widget, task_data: dict):
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
            if video and self._cached_file_exists(video):
                slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                slot.mousePressEvent = lambda e, p=video: self._open_video(p) if e.button() == Qt.MouseButton.LeftButton else None
            # Copy context menu policy for red thumbnails
            slot.setContextMenuPolicy(new_slot.contextMenuPolicy())
            new_slot.deleteLater()
    
    def _open_video(self, video_path: str):
        """Open video file using system default player."""
        try:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(video_path).resolve())))
        except Exception as e:
            print(f"[Queue] Failed to open video: {e}")
