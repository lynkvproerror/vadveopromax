"""
VEO Pro Max - Toast Notification System

Floating toast popup notifications that slide up from bottom-right.
Replaces static status bar text with animated, dismissible toasts.
"""

from pathlib import Path
import sys

from PySide6.QtWidgets import QLabel, QFrame, QHBoxLayout, QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve, Property
from PySide6.QtGui import QFont

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


# Toast level → (icon, bg, border_color)
TOAST_STYLES = {
    "success": ("✅", Theme.GREEN_BG, Theme.GREEN),
    "error":   ("❌", Theme.RED_BG, Theme.RED),
    "warning": ("⚠️", "#3D3224", Theme.YELLOW),
    "info":    ("ℹ️", Theme.SURFACE0, Theme.BLUE),
}


class ToastWidget(QFrame):
    """A single floating toast notification."""
    
    def __init__(self, message: str, level: str = "info",
                 duration: int = 4000, parent: QWidget = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        
        self._duration = duration
        self._level = level
        
        icon, bg, border = TOAST_STYLES.get(level, TOAST_STYLES["info"])
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border-left: 4px solid {border};
                border-radius: 6px;
                border: 1px solid {Theme.SURFACE2};
                border-left: 4px solid {border};
            }}
        """)
        self.setMinimumWidth(300)
        self.setMaximumWidth(420)
        self.setFixedHeight(48)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # Icon
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 16px; border: none;")
        icon_label.setFixedWidth(24)
        layout.addWidget(icon_label)
        
        # Message
        msg_label = QLabel(message)
        msg_label.setStyleSheet(f"""
            color: {Theme.TEXT};
            font-size: 12px;
            border: none;
        """)
        msg_label.setWordWrap(True)
        layout.addWidget(msg_label, stretch=1)
        
        # Close button
        close_btn = QLabel("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setAlignment(Qt.AlignCenter)
        close_btn.setStyleSheet(f"""
            color: {Theme.OVERLAY0};
            font-size: 12px;
            font-weight: bold;
            border: none;
        """)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.mousePressEvent = lambda e: self.dismiss()
        layout.addWidget(close_btn)
        
        # Click anywhere to dismiss
        self.mousePressEvent = lambda e: self.dismiss()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Auto-dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
    
    def show_animated(self, target_pos: QPoint):
        """Slide up from below target position."""
        start = QPoint(target_pos.x(), target_pos.y() + 60)
        self.move(start)
        self.show()
        
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(250)
        self._anim.setStartValue(start)
        self._anim.setEndValue(target_pos)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()
        
        self._timer.start(self._duration)
    
    def dismiss(self):
        """Slide down and fade out."""
        self._timer.stop()
        
        current = self.pos()
        end = QPoint(current.x(), current.y() + 60)
        
        self._dismiss_anim = QPropertyAnimation(self, b"pos")
        self._dismiss_anim.setDuration(200)
        self._dismiss_anim.setStartValue(current)
        self._dismiss_anim.setEndValue(end)
        self._dismiss_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._dismiss_anim.finished.connect(self._on_dismissed)
        self._dismiss_anim.start()
    
    def _on_dismissed(self):
        """Cleanup after dismiss animation completes."""
        self.hide()
        self.deleteLater()


class ToastManager:
    """Manages toast stack — max 3 visible, auto-positioning."""
    
    MAX_VISIBLE = 3
    TOAST_GAP = 8
    MARGIN_RIGHT = 20
    MARGIN_BOTTOM = 60  # Above status bar
    
    def __init__(self, parent_window):
        self._parent = parent_window
        self._toasts: list = []
    
    def show_toast(self, message: str, level: str = "info", duration: int = 4000):
        """Show a new toast notification."""
        # Enforce max visible
        while len(self._toasts) >= self.MAX_VISIBLE:
            oldest = self._toasts.pop(0)
            try:
                oldest.dismiss()
            except RuntimeError:
                pass  # Widget already deleted
        
        toast = ToastWidget(message, level, duration, parent=None)
        toast.adjustSize()
        
        # Calculate position
        pos = self._calculate_position(len(self._toasts), toast)
        toast.show_animated(pos)
        
        self._toasts.append(toast)
        
        # Cleanup ref when dismissed
        toast.destroyed.connect(lambda: self._remove_toast(toast))
    
    def _calculate_position(self, index: int, toast: ToastWidget) -> QPoint:
        """Calculate toast position from bottom-right of parent window."""
        parent_geo = self._parent.geometry()
        
        # Stack from bottom
        x = parent_geo.right() - toast.width() - self.MARGIN_RIGHT
        y = parent_geo.bottom() - self.MARGIN_BOTTOM - (index + 1) * (toast.height() + self.TOAST_GAP)
        
        return QPoint(x, y)
    
    def _remove_toast(self, toast):
        """Remove toast ref from stack."""
        try:
            self._toasts.remove(toast)
        except ValueError:
            pass
        # Reposition remaining
        self._reposition()
    
    def _reposition(self):
        """Reposition remaining toasts after one is dismissed."""
        for i, toast in enumerate(self._toasts):
            try:
                pos = self._calculate_position(i, toast)
                anim = QPropertyAnimation(toast, b"pos")
                anim.setDuration(150)
                anim.setEndValue(pos)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.start()
                # Keep reference alive
                toast._reposition_anim = anim
            except RuntimeError:
                pass
