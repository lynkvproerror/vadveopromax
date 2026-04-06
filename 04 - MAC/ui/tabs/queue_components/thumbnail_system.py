"""
Queue Thumbnail System — pixmap cache, file existence checks, thumb slot creation.

Mixin class for TabQueue. All methods operate on `self` (the TabQueue instance).

Performance: 3-tier thumbnail strategy for 200+ prompt queues:
  Tier 1 (Micro):  40×40 pre-generated .webp files (~2-5KB) for grid display
  Tier 2 (Hover):  300px zoom loaded on-demand from original file (300ms delay)
  Tier 3 (Click):  Full-res preview loaded on click from original file
"""

import time
import hashlib
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict

from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QScrollArea
from PySide6.QtGui import QPixmap, QImage, QCursor
from PySide6.QtCore import Qt, Signal, QObject

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme

_log = logging.getLogger("veo.thumb_system")


# ── Background Micro-Thumbnail Generator ────────────────────────

class _MicroThumbWorker(QObject):
    """Signals for background micro-thumbnail generation results."""
    thumb_ready = Signal(str, str)  # (original_path, micro_thumb_path)

_micro_worker = _MicroThumbWorker()
_micro_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="micro_thumb")
_micro_pending: set = set()  # Paths currently being generated


def _get_micro_thumb_dir() -> Path:
    """Get/create the micro-thumbnail cache directory."""
    cache_dir = Path.home() / ".veoauto" / "cache" / "micro_thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _micro_thumb_path(source_path: str) -> Path:
    """Compute the micro-thumbnail path for a given source image/video frame."""
    h = hashlib.md5(source_path.encode('utf-8', errors='replace')).hexdigest()[:12]
    return _get_micro_thumb_dir() / f"{h}.webp"


def _generate_micro_thumb_bg(source_path: str):
    """Background thread: generate a 40×40 WebP micro-thumbnail.
    
    Uses QImage (thread-safe for loading) instead of QPixmap.
    Emits thumb_ready signal when done.
    """
    try:
        micro_path = _micro_thumb_path(source_path)
        if micro_path.exists():
            _micro_pending.discard(source_path)
            _micro_worker.thumb_ready.emit(source_path, str(micro_path))
            return
        
        img = QImage(source_path)
        if img.isNull():
            _micro_pending.discard(source_path)
            return
        
        scaled = img.scaled(
            40, 40,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.save(str(micro_path), "WEBP", 75)
        _micro_pending.discard(source_path)
        _micro_worker.thumb_ready.emit(source_path, str(micro_path))
    except Exception as e:
        _micro_pending.discard(source_path)
        _log.debug(f"[MicroThumb] Failed for {source_path}: {e}")


class QueueThumbnailMixin:
    """Mixin providing thumbnail slot creation and caching.
    
    Expects host to provide:
    - self._pixmap_cache, self._pixmap_cache_max
    - self._file_exists_cache, self._file_exists_ttl
    - self._input_pulse_thumbs, self._input_pulse_phase
    """
    
    # ── Performance Caches ───────────────────────────────────────
    
    def _init_micro_thumb_system(self):
        """Initialize micro-thumbnail background generation system.
        
        Call this once during __init__ after super().__init__().
        """
        _micro_worker.thumb_ready.connect(self._on_micro_thumb_ready)
    
    def _on_micro_thumb_ready(self, source_path: str, micro_path: str):
        """Slot: micro-thumbnail generated in background → update pixmap cache."""
        # Update the LRU cache with the new micro-thumbnail
        cache_key = f"{source_path}:40"
        if cache_key not in self._pixmap_cache:
            pix = QPixmap(micro_path)
            if not pix.isNull():
                self._pixmap_cache[cache_key] = pix
                while len(self._pixmap_cache) > self._pixmap_cache_max:
                    self._pixmap_cache.popitem(last=False)
        # Trigger a lightweight refresh to swap in the new thumbnail
        if hasattr(self, '_completion_refresh_timer') and not self._completion_refresh_timer.isActive():
            self._completion_refresh_timer.start()
    
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
        # Evict oldest 50% when cache exceeds 2000 entries to prevent unbounded growth
        if len(self._file_exists_cache) > 2000:
            sorted_keys = sorted(self._file_exists_cache, key=lambda k: self._file_exists_cache[k][1])
            for k in sorted_keys[:len(sorted_keys) // 2]:
                del self._file_exists_cache[k]
        return exists
    
    def _invalidate_file_cache(self, path: str):
        """Invalidate file existence cache when a file is newly created."""
        self._file_exists_cache.pop(path, None)
    
    def _get_cached_pixmap(self, path: str, size: int = 40) -> 'QPixmap':
        """Get scaled QPixmap from LRU cache with micro-thumbnail acceleration.
        
        For size=40 (grid thumbnails), tries to load a pre-generated 40×40 .webp
        micro-thumbnail (~2-5KB) instead of the full-res source (~200-500KB).
        If the micro-thumbnail doesn't exist, queues background generation and
        returns a synchronously-scaled version in the meantime.
        
        For other sizes (e.g. hover zoom), loads from original file.
        """
        cache_key = f"{path}:{size}"
        if cache_key in self._pixmap_cache:
            self._pixmap_cache.move_to_end(cache_key)
            return self._pixmap_cache[cache_key]
        
        # ── Tier 1: Try micro-thumbnail for grid display (size=40) ──
        if size <= 40:
            micro = _micro_thumb_path(path)
            if micro.exists():
                pixmap = QPixmap(str(micro))
                if not pixmap.isNull():
                    self._pixmap_cache[cache_key] = pixmap
                    while len(self._pixmap_cache) > self._pixmap_cache_max:
                        self._pixmap_cache.popitem(last=False)
                    return pixmap
            else:
                # Queue background generation (non-blocking)
                if path not in _micro_pending:
                    _micro_pending.add(path)
                    _micro_executor.submit(_generate_micro_thumb_bg, path)
        
        # ── Fallback: load + scale from original (first time only) ──
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
    
    # ── Viewport Awareness ───────────────────────────────────────
    
    def _is_widget_in_viewport(self, widget: QWidget, buffer_px: int = 80) -> bool:
        """Check if a widget is within the visible scroll viewport (±buffer).
        
        Used to skip expensive thumbnail updates for off-screen rows.
        Returns True if viewport can't be determined (safe fallback).
        """
        try:
            scroll_area = None
            parent = widget.parent()
            while parent:
                if isinstance(parent, QScrollArea):
                    scroll_area = parent
                    break
                parent = parent.parent()
            
            if not scroll_area:
                return True  # Can't determine → assume visible
            
            viewport = scroll_area.viewport()
            if not viewport:
                return True
            
            # Map widget position to scroll area viewport coordinates
            widget_pos = widget.mapTo(viewport, widget.rect().topLeft())
            widget_bottom = widget_pos.y() + widget.height()
            viewport_height = viewport.height()
            
            # Widget is visible if it overlaps viewport rect (with buffer)
            return widget_bottom >= -buffer_px and widget_pos.y() <= viewport_height + buffer_px
        except (RuntimeError, AttributeError):
            return True  # Widget deleted or can't determine → assume visible
    
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
                # ★ Click → in-app preview (image or video)
                preview_path = video_path if (video_path and self._cached_file_exists(video_path)) else thumbnail_path
                if preview_path:
                    slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    slot.mousePressEvent = lambda e, p=preview_path: self._open_media(p) if e.button() == Qt.MouseButton.LeftButton else None
                
                # ★ Hover → zoom tooltip
                from ui.popups.media_preview import attach_hover_zoom
                attach_hover_zoom(slot, thumbnail_path)
                
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
            
            # ★ Click → in-app preview
            if video_path and self._cached_file_exists(video_path):
                slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                slot.mousePressEvent = lambda e, p=video_path: self._open_media(p) if e.button() == Qt.MouseButton.LeftButton else None
            
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
        
        if status in ("failed", "cancelled"):
            # Failed/cancelled — show clear indicator
            indicator = '✕' if status == 'failed' else '—'
            indicator_color = Theme.RED if status == 'failed' else Theme.SUBTEXT0
            slot.setText(indicator)
            slot.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.SURFACE0};
                    border: 2px solid {indicator_color};
                    border-radius: 4px;
                    color: {indicator_color};
                    font-size: 14px;
                    font-weight: bold;
                }}
            """)
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
        """Attach right-click context menu to a thumbnail slot.
        
        Safe to call multiple times — disconnects previous handler first.
        """
        # Disconnect any existing context menu handler to prevent stacking
        try:
            if slot.receivers(slot.customContextMenuRequested) > 0:
                slot.customContextMenuRequested.disconnect()
        except (RuntimeError, TypeError):
            pass  # No previous connection — safe to ignore
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
        
        # Continuation tasks: frame comes from continuation_frame, not image_paths
        if not input_images and task_data.get('has_continuation'):
            cont_frame = task_data.get('continuation_frame', '')
            if cont_frame:
                input_images = [cont_frame]
        
        # BUG-A5 fix: Track thumbs per-container, don't append to global list indefinitely
        container_thumbs = []
        upload_status = task_data.get('image_upload_status', '') if task_data else ''
        for img_path in input_images[:3]:  # Max 3 thumbnails
            if img_path and self._cached_file_exists(img_path):
                thumb = QLabel()
                thumb.setFixedSize(30, 30)
                thumb.setAlignment(Qt.AlignCenter)
                pix = self._get_cached_pixmap(img_path, 30)
                if not pix.isNull():
                    thumb.setPixmap(pix)
                    # Border color depends on upload status:
                    # - "ready" → solid green (upload complete)
                    # - "extracting"/"uploading" → pulsing blue (active)
                    # - "" or other → solid blue (static)
                    if upload_status == 'ready':
                        border_color = Theme.GREEN
                    else:
                        border_color = Theme.BLUE
                    thumb.setStyleSheet(f"""
                        QLabel {{
                            border: 1px solid {border_color};
                            border-radius: 4px;
                            background-color: {Theme.BASE};
                            padding: 1px;
                        }}
                    """)
                    thumb.setToolTip(f"Input: {Path(img_path).name}")
                    container_thumbs.append(thumb)
                    layout.addWidget(thumb)
        
        # BUG-A5 fix: Store refs on container for cleanup
        container._pulse_thumbs = container_thumbs
        # Only register pulsing for active upload (extracting/uploading)
        # Once "ready" or empty → static border, no pulsing
        if upload_status in ('extracting', 'uploading'):
            self._input_pulse_thumbs.extend(container_thumbs)
            # Bug 8: Start timer on-demand (no longer auto-started in __init__)
            if container_thumbs and not self._input_pulse_timer.isActive():
                self._input_pulse_timer.start()
        
        layout.addStretch()
        return container
    
    def _update_thumb_slots(self, widget, task_data: dict):
        """Update thumbnail slots on an existing row widget during refresh.
        
        ★ Anti-flicker: Uses per-slot fingerprints to skip redundant updates.
        Only rebuilds slots whose data actually changed.
        """
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
            
            # ★ Anti-flicker: Compute fingerprint — skip update if nothing changed
            bc_name = vi_info.get('border_color', 'gray') if vi_info else 'gray'
            us = vi_info.get('upscale_status', '') if vi_info else ''
            fp = f"{thumb}|{video}|{bc_name}|{us}|{status}|{progress}"
            if getattr(slot, '_slot_fingerprint', None) == fp:
                continue  # Nothing changed — skip expensive repaint
            slot._slot_fingerprint = fp
            
            new_slot = self._create_thumb_slot(
                vi, status, progress, thumb, video, video_info=vi_info
            )
            
            # Unregister REAL slot + temp slot from ALL animations before update
            self._unregister_shimmer_slot(slot)
            self._unregister_shimmer_slot(new_slot)
            
            # Copy styling and content from new slot
            slot.setStyleSheet(new_slot.styleSheet())
            if new_slot.pixmap() and not new_slot.pixmap().isNull():
                slot.setPixmap(new_slot.pixmap())
                slot.setText('')
            else:
                slot.setPixmap(QPixmap())
                slot.setText(new_slot.text())
            slot.setToolTip(new_slot.toolTip())
            # Transfer border color and video info
            slot._border_color_name = getattr(new_slot, '_border_color_name', 'gray')
            slot._video_info = getattr(new_slot, '_video_info', None)
            slot._progress_pct = getattr(new_slot, '_progress_pct', 0.0)
            
            # Re-register shimmer ONLY if task is actively running
            if status in ('running', 'waiting_poll') and progress < 100:
                self._register_shimmer_slot(slot)
            else:
                # Task completed/failed/cancelled — ensure no residual animation
                self._unregister_shimmer_slot(slot)
            
            if video and self._cached_file_exists(video):
                slot.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                slot.mousePressEvent = lambda e, p=video: self._open_media(p) if e.button() == Qt.MouseButton.LeftButton else None
            # ★ Hover-zoom on updated thumbnail
            thumb = thumbnails[vi] if vi < len(thumbnails) else None
            if thumb and self._cached_file_exists(thumb):
                from ui.popups.media_preview import attach_hover_zoom
                attach_hover_zoom(slot, thumb)
            # Copy context menu policy for red thumbnails
            slot.setContextMenuPolicy(new_slot.contextMenuPolicy())
            new_slot.deleteLater()
    
    def _open_media(self, file_path: str):
        """Open image/video using in-app MediaPreviewPopup."""
        try:
            from ui.popups.media_preview import MediaPreviewPopup
            MediaPreviewPopup.preview(self if hasattr(self, 'window') else None, str(Path(file_path).resolve()))
        except Exception as e:
            # Fallback to system player
            print(f"[Queue] MediaPreview failed, falling back: {e}")
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(file_path).resolve())))

    def _open_video(self, video_path: str):
        """Legacy alias — redirects to _open_media."""
        self._open_media(video_path)
