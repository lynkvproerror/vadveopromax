"""
VEO Pro Max - Startup Splash Screen

Displays a premium splash banner with pastel illustration,
animated progress bar with %, and status text updates.
Stays visible until all browsers are launched and hidden.
"""

from pathlib import Path

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal, Slot
from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor, QFont, QPainterPath, QPen

from config.theme import Theme
from config.i18n import t


class SplashScreen(QWidget):
    """Frameless splash screen shown during app startup.
    
    Layout (800×600):
    ┌──────────────────────────────────────────────┐
    │                                              │
    │          [Pastel Director Image]             │
    │                                              │
    │          VEO PRO MAX                         │
    │          AI Video Generation Suite           │
    │                                              │
    │    ████████████████░░░░░░░░  45%             │
    │    Loading settings...                       │
    │                                        v2.0  │
    └──────────────────────────────────────────────┘
    """
    
    # Signal emitted when splash wants to close
    finished = Signal()
    
    SPLASH_WIDTH = 800
    SPLASH_HEIGHT = 600
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Frameless splash, no taskbar icon (NOT always-on-top)
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.SPLASH_WIDTH, self.SPLASH_HEIGHT)
        
        # Center on screen
        self._center_on_screen()
        
        # State
        self._progress = 0.0          # Display value (current position)
        self._target_progress = None  # None = auto-advance mode, float = explicit target
        self._auto_cap = 95.0         # Auto-advance stops here
        self._status_text = t("splash.starting")
        self._fade_out_running = False
        self._finish_pending = False
        self._finish_window = None
        
        # Load background image
        img_path = Path(__file__).parent.parent / "assets" / "splash_banner.png"
        self._bg_pixmap = QPixmap(str(img_path)) if img_path.exists() else None
        
        # Glow pulse state
        self._glow_alpha = 0
        self._glow_direction = 1
        
        # Single animation timer (handles auto-advance + interpolation + glow)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(20)  # 50fps
    
    def _center_on_screen(self):
        """Center the splash on the primary screen."""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.SPLASH_WIDTH) // 2 + geo.x()
            y = (geo.height() - self.SPLASH_HEIGHT) // 2 + geo.y()
            self.move(x, y)
    
    def _tick(self):
        """Animation tick: auto-advance or interpolation + glow pulse."""
        
        if self._target_progress is None:
            # ── AUTO-ADVANCE MODE (0 → 80%) ──
            # Steadily increment with deceleration near the cap
            if self._progress < self._auto_cap:
                remaining = self._auto_cap - self._progress
                # Decelerating: fast at start, slow near cap
                if self._progress < 30:
                    step = 0.65   # ~0.9s for 0→30
                elif self._progress < 55:
                    step = 0.50   # ~1.0s for 30→55
                elif self._progress < 75:
                    step = 0.35   # ~1.1s for 55→75
                elif self._progress < 88:
                    step = 0.20   # ~1.3s for 75→88
                else:
                    step = 0.10   # ~1.4s for 88→95 (crawl to cap)
                
                self._progress = min(self._progress + step, self._auto_cap)
            # else: at cap, just wait
        else:
            # ── EXPLICIT TARGET MODE (80% → 100%) ──
            diff = self._target_progress - self._progress
            if abs(diff) > 0.05:
                # Smooth interpolation for browser stages
                if self._progress < 95:
                    rate = 0.10
                    min_step = 0.25
                else:
                    rate = 0.06
                    min_step = 0.15
                
                step = diff * rate
                if abs(step) < min_step:
                    step = min_step if diff > 0 else -min_step
                self._progress += step
            else:
                self._progress = self._target_progress
        
        # Clamp
        self._progress = max(0.0, min(100.0, self._progress))
        
        # ── Glow pulse ──
        self._glow_alpha += self._glow_direction * 3
        if self._glow_alpha >= 80:
            self._glow_direction = -1
        elif self._glow_alpha <= 0:
            self._glow_direction = 1
        
        self.update()
    
    # ── Public API ──────────────────────────────────────────
    
    def set_status(self, text: str):
        """Update status text only (auto-advance keeps running).
        
        Used during early init (0-80%) where progress auto-advances
        and only the status message changes at each step.
        """
        self._status_text = text
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
    
    def set_progress(self, value: int, status: str = ""):
        """Set explicit target — switches OFF auto-advance mode.
        
        Used by controller for browser launch stages (80%+).
        Bar will smoothly animate toward this target.
        """
        self._target_progress = float(max(0, min(100, value)))
        if status:
            self._status_text = status
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
    
    def finish(self, main_window=None):
        """Smoothly animate to 100%, wait 2s, then fade out."""
        if self._fade_out_running or self._finish_pending:
            return
        self._finish_pending = True
        self._finish_window = main_window
        
        # Set target to 100 — the timer will smoothly animate there
        self._target_progress = 100.0
        self._status_text = t("splash.ready")
        
        # Poll until progress reaches 100, then delay + fade
        self._finish_check_timer = QTimer(self)
        self._finish_check_timer.timeout.connect(self._check_finish_ready)
        self._finish_check_timer.start(50)
    
    def _check_finish_ready(self):
        """Wait for progress to reach 100, then start 2s delay."""
        if self._progress >= 99.5:
            self._progress = 100.0
            self._target_progress = 100.0
            self._finish_check_timer.stop()
            # Brief pause at 100% before fade out
            QTimer.singleShot(500, self._do_fade_out)
    
    def _do_fade_out(self):
        """Execute the fade-out animation."""
        if self._fade_out_running:
            return
        self._fade_out_running = True
        self._anim_timer.stop()
        
        # Fade out
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(600)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        
        def _on_finished():
            if self._finish_window:
                self._finish_window.show()
                self._finish_window.raise_()
                self._finish_window.activateWindow()
            self.close()
            self.finished.emit()
        
        self._fade_anim.finished.connect(_on_finished)
        self._fade_anim.start()
    
    # ── Painting ────────────────────────────────────────────
    
    def paintEvent(self, event):
        """Custom paint for the splash screen."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        W, H = self.SPLASH_WIDTH, self.SPLASH_HEIGHT
        margin = 0
        radius = 20
        
        # ── 1. Background rounded rect with gradient ──
        path = QPainterPath()
        path.addRoundedRect(margin, margin, W - 2 * margin, H - 2 * margin, radius, radius)
        painter.setClipPath(path)
        
        # Dark gradient background
        bg_grad = QLinearGradient(0, 0, 0, H)
        bg_grad.setColorAt(0.0, QColor("#181825"))   # Mantle (top)
        bg_grad.setColorAt(0.5, QColor("#1E1E2E"))   # Base (middle)
        bg_grad.setColorAt(1.0, QColor("#11111B"))   # Crust (bottom)
        painter.fillPath(path, bg_grad)
        
        # ── 2. Background image (fill entire splash) ──
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            # Scale to fill entire 800×600, crop excess
            scaled = self._bg_pixmap.scaled(
                W, H,
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            # Crop: center both axes
            crop_x = (scaled.width() - W) // 2
            crop_y = (scaled.height() - H) // 2
            cropped = scaled.copy(crop_x, crop_y, W, H)
            
            painter.drawPixmap(0, 0, cropped)
            
            # Dark gradient overlay on bottom 50% for text readability
            overlay_grad = QLinearGradient(0, H * 0.45, 0, H)
            overlay_grad.setColorAt(0.0, QColor(17, 17, 27, 0))       # transparent
            overlay_grad.setColorAt(0.3, QColor(17, 17, 27, 140))     # soft fade
            overlay_grad.setColorAt(1.0, QColor(17, 17, 27, 240))     # near opaque
            painter.fillRect(0, int(H * 0.45), W, H, overlay_grad)
        
        # ── 3. App title ──
        title_y = int(H * 0.60)
        
        # Shadow
        title_font = QFont("Segoe UI", 32, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(0, 0, 0, 120))
        painter.drawText(0, title_y + 2, W, 50, Qt.AlignCenter, "VEO PRO MAX")
        
        # Main title
        painter.setPen(QColor(Theme.BLUE))
        painter.drawText(0, title_y, W, 50, Qt.AlignCenter, "VEO PRO MAX")
        
        # ── 4. Subtitle ──
        subtitle_font = QFont("Segoe UI", 13)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(Theme.SUBTEXT1))
        subtitle_y = title_y + 48
        painter.drawText(0, subtitle_y, W, 24, Qt.AlignCenter, t("splash.subtitle"))
        
        # ── 5. Progress bar ──
        bar_y = subtitle_y + 50
        bar_x = 80
        bar_w = W - 160
        bar_h = 8
        
        # Track
        track_path = QPainterPath()
        track_path.addRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)
        painter.fillPath(track_path, QColor(255, 255, 255, 30))
        
        # Fill
        if self._progress > 0:
            fill_w = int(bar_w * self._progress / 100)
            fill_path = QPainterPath()
            fill_path.addRoundedRect(bar_x, bar_y, fill_w, bar_h, 4, 4)
            
            fill_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            fill_grad.setColorAt(0.0, QColor(Theme.BLUE))
            fill_grad.setColorAt(1.0, QColor(Theme.PURPLE))
            painter.fillPath(fill_path, fill_grad)
            
            # Glow on leading edge
            if self._progress < 100:
                glow_x = bar_x + fill_w - 2
                glow_color = QColor(Theme.BLUE)
                glow_color.setAlpha(self._glow_alpha)
                painter.setPen(Qt.NoPen)
                painter.setBrush(glow_color)
                painter.drawEllipse(int(glow_x - 4), int(bar_y - 4), 16, 16)
        
        # ── 6. Percentage ──
        pct_font = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(pct_font)
        painter.setPen(QColor(Theme.TEXT))
        painter.drawText(bar_x, bar_y - 22, bar_w, 20, Qt.AlignRight, f"{self._progress:.1f}%")
        
        # ── 7. Status text ──
        status_font = QFont("Segoe UI", 11)
        painter.setFont(status_font)
        painter.setPen(QColor(Theme.SUBTEXT0))
        painter.drawText(bar_x, bar_y + bar_h + 12, bar_w, 20, Qt.AlignLeft, self._status_text)
        
        # ── 8. Version ──
        ver_font = QFont("Segoe UI", 9)
        painter.setFont(ver_font)
        painter.setPen(QColor(Theme.OVERLAY0))
        from config.constants import AppConstants
        painter.drawText(0, H - 35, W - 30, 20, Qt.AlignRight, f"v{AppConstants.APP_VERSION}")
        
        # ── 9. Border ──
        painter.setClipping(False)
        border_pen = QPen(QColor(Theme.BLUE))
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(1, 1, W - 2, H - 2, radius, radius)
        
        painter.end()
