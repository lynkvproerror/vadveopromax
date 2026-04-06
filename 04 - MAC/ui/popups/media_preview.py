"""
VEO Pro Max — Centralized Media Preview System

Provides:
- MediaPreviewPopup: Click-to-preview for both images and videos.
  Auto-detects file type. Images open in a styled dialog; videos
  delegate to VideoPlayerPopup.
- attach_hover_zoom(): Adds hover-to-zoom tooltip to any QLabel/QPushButton
  that displays a thumbnail.
"""

from typing import Optional
from pathlib import Path
import sys

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QDialog, QApplication
from PySide6.QtCore import Qt, QPoint, QTimer, QEvent
from PySide6.QtGui import QPixmap, QKeySequence, QShortcut, QPainter, QColor

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme

VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.avi', '.mkv', '.wmv', '.flv'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff', '.tif'}


# ═══════════════════════════════════════════════════════════════
#  MediaPreviewPopup — click-to-preview (image or video)
# ═══════════════════════════════════════════════════════════════

class MediaPreviewPopup:
    """Centralized media preview — static API.
    
    Usage:
        MediaPreviewPopup.preview(parent_widget, "/path/to/file")
    """
    
    @staticmethod
    def preview(parent: Optional[QWidget], file_path: str):
        """Auto-detect file type and show appropriate preview.
        
        - Image files → styled popup dialog with scaled image
        - Video files → VideoPlayerPopup (in-app player)
        """
        if not file_path:
            return
        path = Path(file_path)
        if not path.exists():
            return
        
        ext = path.suffix.lower()
        
        if ext in VIDEO_EXTENSIONS:
            MediaPreviewPopup._preview_video(parent, str(path), path.name)
        elif ext in IMAGE_EXTENSIONS:
            MediaPreviewPopup._preview_image(parent, str(path), path.name)
        else:
            # Fallback: try as image first
            MediaPreviewPopup._preview_image(parent, str(path), path.name)
    
    @staticmethod
    def _preview_video(parent: Optional[QWidget], video_path: str, title: str):
        """Open in-app video player with click-outside-to-dismiss overlay."""
        try:
            from ui.popups.video_player import VideoPlayerPopup
            overlay = _VideoOverlayDialog(parent, video_path, title)
            overlay.exec()
        except Exception as e:
            print(f"[MediaPreview] VideoPlayer fallback: {e}")
            # Fallback to system player
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(video_path))
    
    @staticmethod
    def _preview_image(parent: Optional[QWidget], image_path: str, title: str):
        """Show image in a styled preview dialog."""
        dialog = _ImagePreviewDialog(parent, image_path, title)
        dialog.exec()


class _ImagePreviewDialog(QDialog):
    """Lightweight image preview dialog — Catppuccin styled.
    
    Features:
    - Scaled to fit screen (max 900×700)
    - Dark semi-transparent overlay
    - ESC or click-outside to close
    - File name in title
    """
    
    MAX_W, MAX_H = 900, 700
    
    def __init__(self, parent: Optional[QWidget], image_path: str, title: str):
        super().__init__(parent)
        self.setWindowTitle(f"🖼️ {title}")
        # Full-screen overlay: frameless + transparent background
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        # Make it cover the entire parent/screen
        if parent:
            self.setGeometry(parent.window().geometry())
        else:
            screen = QApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.availableGeometry())
        
        # Overlay layout — centers the image card
        overlay_layout = QVBoxLayout(self)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setAlignment(Qt.AlignCenter)
        
        # Image card container
        card = QLabel()
        card.setStyleSheet(
            f"background-color: {Theme.CRUST}; "
            f"border-radius: 8px; padding: 4px;"
        )
        card.setAlignment(Qt.AlignCenter)
        card.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                self.MAX_W, self.MAX_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            card.setPixmap(scaled)
            card.setFixedSize(scaled.width() + 8, scaled.height() + 8)
        else:
            card.setText("Cannot load image")
            card.setStyleSheet(f"color: {Theme.RED}; font-size: 14px; background-color: {Theme.CRUST}; border-radius: 8px; padding: 20px;")
            card.setFixedSize(300, 150)
        
        self._card = card
        overlay_layout.addWidget(card)
        
        # ESC to close
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self.close)
    
    def paintEvent(self, event):
        """Draw semi-transparent dark overlay background."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
        painter.end()
    
    def mousePressEvent(self, event):
        """Click outside image card → close."""
        # Check if click is on the card
        card_rect = self._card.geometry()
        if not card_rect.contains(event.pos()):
            self.close()
        else:
            super().mousePressEvent(event)


class _VideoOverlayDialog(QDialog):
    """Full-screen overlay wrapping VideoPlayerPopup for click-outside-to-dismiss.
    
    The video player widget is embedded (not a separate dialog) so that
    clicking outside the player area on the dark overlay closes everything.
    """
    
    def __init__(self, parent: Optional[QWidget], video_path: str, title: str):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        
        # Cover the entire parent window
        if parent:
            self.setGeometry(parent.window().geometry())
        else:
            screen = QApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.availableGeometry())
        
        # Overlay layout — centers the video player
        overlay_layout = QVBoxLayout(self)
        overlay_layout.setContentsMargins(40, 40, 40, 40)
        overlay_layout.setAlignment(Qt.AlignCenter)
        
        # Embed the VideoPlayerPopup as a widget (not a separate dialog)
        from ui.popups.video_player import VideoPlayerPopup
        self._player_popup = VideoPlayerPopup(
            parent=None,  # No parent — we embed it manually
            video_path=video_path,
            video_title=title,
        )
        # Convert from dialog to embedded widget
        self._player_popup.setWindowFlags(Qt.Widget)
        self._player_popup.setFixedSize(720, 520)
        self._player_popup.setStyleSheet(
            f"background-color: {Theme.BASE}; border-radius: 8px;"
        )
        overlay_layout.addWidget(self._player_popup)
        self._player_popup.show()
        
        # Override the player popup's close to close the overlay too
        original_close = self._player_popup._on_close
        def _close_overlay():
            original_close()
            self.close()
        self._player_popup._on_close = _close_overlay
        
        # ESC to close
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        esc.activated.connect(self._cleanup_and_close)
    
    def paintEvent(self, event):
        """Draw semi-transparent dark overlay background."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
        painter.end()
    
    def mousePressEvent(self, event):
        """Click outside video player → close."""
        player_rect = self._player_popup.geometry()
        if not player_rect.contains(event.pos()):
            self._cleanup_and_close()
        else:
            super().mousePressEvent(event)
    
    def _cleanup_and_close(self):
        """Stop player and close overlay."""
        if hasattr(self._player_popup, '_player') and self._player_popup._player:
            self._player_popup._player.stop()
            from PySide6.QtCore import QUrl
            self._player_popup._player.setSource(QUrl())
        self.close()
    
    def closeEvent(self, event):
        """Ensure player cleanup on any close path."""
        if hasattr(self, '_player_popup'):
            if hasattr(self._player_popup, '_player') and self._player_popup._player:
                self._player_popup._player.stop()
                from PySide6.QtCore import QUrl
                self._player_popup._player.setSource(QUrl())
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════
#  HoverZoom — attach hover-to-zoom tooltip to any widget
# ═══════════════════════════════════════════════════════════════

class _HoverZoomPopup(QDialog):
    """Frameless tooltip-style popup showing a zoomed image.
    
    ★ Anti-flicker: Avoids redundant show()/setFixedSize()/setPixmap() calls.
    """
    
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput  # Mouse passes through → no Enter/Leave bounce
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose, False)  # Reuse instance
        
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            f"background-color: {Theme.CRUST}; "
            f"border: 2px solid {Theme.OVERLAY0}; "
            f"border-radius: 6px; "
            f"padding: 2px;"
        )
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        
        self._current_image_key: str = ""  # Track current image to skip redundant scaling
    
    def _compute_position(self, global_pos: QPoint, w: int, h: int) -> QPoint:
        """Compute popup position, keeping it on screen."""
        screen = QApplication.primaryScreen()
        x = global_pos.x() + 16
        y = global_pos.y() + 16
        if screen:
            geo = screen.availableGeometry()
            if x + w > geo.right():
                x = global_pos.x() - w - 8
            if y + h > geo.bottom():
                y = global_pos.y() - h - 8
        return QPoint(x, y)
    
    def show_image(self, pixmap: QPixmap, global_pos: QPoint, zoom_size: int):
        """Display zoomed image. Skips redundant updates when already showing same image."""
        image_key = f"{id(pixmap)}:{zoom_size}"
        
        if self._current_image_key != image_key:
            # Different image — need to rescale and update pixmap
            self._current_image_key = image_key
            scaled = pixmap.scaled(
                zoom_size, zoom_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._label.setPixmap(scaled)
            new_w = scaled.width() + 8
            new_h = scaled.height() + 8
            pos = self._compute_position(global_pos, new_w, new_h)
            # Batch: resize + move before show to prevent intermediate blank frame
            self.setGeometry(pos.x(), pos.y(), new_w, new_h)
        else:
            # Same image — just update position
            pos = self._compute_position(global_pos, self.width(), self.height())
            self.move(pos)
        
        if not self.isVisible():
            self.show()
    
    def update_position(self, global_pos: QPoint):
        """Move popup to follow cursor without recreating content."""
        if self.isVisible():
            pos = self._compute_position(global_pos, self.width(), self.height())
            self.move(pos)
    
    def dismiss(self):
        """Hide and reset tracking state."""
        self._current_image_key = ""
        self.hide()


class _HoverZoomFilter(QWidget):
    """Event filter that shows a zoom popup on hover.
    
    Installed per-widget via attach_hover_zoom().
    
    ★ Anti-flicker design (Round 3):
    - Popup uses WindowTransparentForInput → mouse events pass through
    - Leave uses 150ms hysteresis delay → absorbs Enter/Leave bounce
    - Re-enter during hysteresis cancels hide (no 300ms gap)
    - MouseMove dynamically updates popup position while visible
    - Popup skips redundant pixmap/size/show updates
    """
    
    # Class-level shared state
    _shared_popup: Optional[_HoverZoomPopup] = None
    _active_owner: Optional['_HoverZoomFilter'] = None
    
    def __init__(self, target: QWidget, image_path: str, zoom_size: int = 300):
        super().__init__(target)
        self._target = target
        self._image_path = image_path
        self._zoom_size = zoom_size
        self._cached_pixmap: Optional[QPixmap] = None
        
        # Show delay timer
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(300)
        self._show_timer.timeout.connect(self._do_show)
        
        # Hide hysteresis timer
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(150)  # 150ms grace period
        self._hide_timer.timeout.connect(self._do_hide)
        
        self._pending_pos: Optional[QPoint] = None
    
    @classmethod
    def _get_popup(cls) -> _HoverZoomPopup:
        if cls._shared_popup is None:
            cls._shared_popup = _HoverZoomPopup()
        return cls._shared_popup
    
    def update_path(self, new_path: str):
        """Update the image path (e.g. when thumbnail refreshes)."""
        if new_path != self._image_path:
            self._image_path = new_path
            self._cached_pixmap = None
    
    def eventFilter(self, obj, event):
        if obj is not self._target:
            return False
        
        etype = event.type()
        
        if etype == QEvent.Enter:
            # Cancel any pending hide
            self._hide_timer.stop()
            
            # If popup is already visible and we own it → just keep it (no re-delay)
            if (
                _HoverZoomFilter._active_owner is self
                and _HoverZoomFilter._shared_popup
                and _HoverZoomFilter._shared_popup.isVisible()
            ):
                return False  # ★ No restart of 300ms delay — popup stays visible
            
            # Start delayed show for fresh hover
            self._pending_pos = self._target.mapToGlobal(
                QPoint(self._target.width(), 0)
            )
            self._show_timer.start()
            return False
        
        if etype == QEvent.Leave:
            self._show_timer.stop()
            if _HoverZoomFilter._active_owner is self:
                self._hide_timer.start()
            return False
        
        if etype == QEvent.MouseMove:
            pos = self._target.mapToGlobal(event.position().toPoint())
            self._pending_pos = pos
            # ★ Dynamically update popup position while visible
            if (
                _HoverZoomFilter._active_owner is self
                and _HoverZoomFilter._shared_popup
                and _HoverZoomFilter._shared_popup.isVisible()
            ):
                _HoverZoomFilter._shared_popup.update_position(pos)
            return False
        
        return False
    
    def _do_show(self):
        """Show the zoom popup after delay."""
        if not self._image_path or not Path(self._image_path).exists():
            return
        
        if self._cached_pixmap is None:
            self._cached_pixmap = QPixmap(self._image_path)
            if self._cached_pixmap.isNull():
                self._cached_pixmap = None
                return
        
        pos = self._pending_pos or QPoint(0, 0)
        popup = self._get_popup()
        _HoverZoomFilter._active_owner = self
        popup.show_image(self._cached_pixmap, pos, self._zoom_size)
    
    def _do_hide(self):
        """Hide popup after hysteresis delay (only if we still own it)."""
        if _HoverZoomFilter._active_owner is self:
            if _HoverZoomFilter._shared_popup:
                _HoverZoomFilter._shared_popup.dismiss()
            _HoverZoomFilter._active_owner = None


def attach_hover_zoom(
    widget: QWidget,
    image_path: str,
    zoom_size: int = 300,
) -> _HoverZoomFilter:
    """Attach hover-to-zoom behavior to any QWidget.
    
    When the user hovers over `widget`, a tooltip-style popup appears
    showing a zoomed version of the image at `image_path`.
    
    Args:
        widget: The QLabel/QPushButton to attach to
        image_path: Path to the image file
        zoom_size: Max dimension of the zoom popup (default 300)
    
    Returns:
        The filter object (can be used to call .update_path() later)
    
    Usage:
        from ui.popups.media_preview import attach_hover_zoom
        attach_hover_zoom(my_thumbnail_label, "/path/to/image.png")
    """
    # Check if already attached — update path instead of double-installing
    existing = getattr(widget, '_hover_zoom_filter', None)
    if existing and isinstance(existing, _HoverZoomFilter):
        existing.update_path(image_path)
        return existing
    
    filt = _HoverZoomFilter(widget, image_path, zoom_size)
    widget.installEventFilter(filt)
    widget._hover_zoom_filter = filt  # Prevent GC + allow update
    return filt
