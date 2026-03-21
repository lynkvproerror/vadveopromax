"""
In-app media preview dialogs for Pipeline Stages 4–7.

ImagePreviewDialog  — fullscreen image viewer with ← → navigation
VideoPreviewDialog  — in-app video player with controls and ← → navigation

Both replace os.startfile() with native PySide6 widgets.
"""

import os
import subprocess
from typing import List, Optional, Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QWidget, QApplication, QSizePolicy,
)
from PySide6.QtCore import Qt, QUrl, QSize, Signal, QTimer
from PySide6.QtGui import QPixmap, QKeyEvent, QColor, QPalette, QShortcut, QKeySequence

from config.theme import Theme

# ── Helpers ──────────────────────────────────────────────────────

_DIALOG_STYLE = f"""
    QDialog {{
        background-color: {Theme.CRUST};
    }}
    QLabel {{
        color: {Theme.TEXT};
    }}
    QPushButton {{
        background-color: {Theme.SURFACE1};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {Theme.BLUE};
        color: {Theme.CRUST};
    }}
    QPushButton:disabled {{
        background-color: {Theme.SURFACE0};
        color: {Theme.OVERLAY0};
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {Theme.SURFACE2};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {Theme.BLUE};
        width: 14px;
        margin: -4px 0;
        border-radius: 7px;
    }}
    QSlider::sub-page:horizontal {{
        background: {Theme.BLUE};
        border-radius: 3px;
    }}
"""


def _ms_to_time(ms: int) -> str:
    """Format milliseconds as MM:SS."""
    s = max(0, ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


# ═══════════════════════════════════════════════════════════════════
#  ImagePreviewDialog — Stage 4 & 5
# ═══════════════════════════════════════════════════════════════════

class ImagePreviewDialog(QDialog):
    """Full-size image viewer with navigation for pipeline images.

    Usage:
        ImagePreviewDialog.show_preview(parent, paths, start_index)
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        image_paths: List[str],
        start_index: int = 0,
        labels: Optional[List[str]] = None,
    ):
        super().__init__(parent)
        self._paths = [p for p in image_paths if p and os.path.isfile(p)]
        self._labels = labels or [os.path.basename(p) for p in self._paths]
        self._index = min(start_index, len(self._paths) - 1) if self._paths else 0

        self.setWindowTitle("🖼️ Image Preview")
        self.setStyleSheet(_DIALOG_STYLE)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        # Size: 80% of screen
        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.8)
        h = int(screen.height() * 0.8)
        self.resize(w, h)

        self._setup_ui()
        self._show_current()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Image area ──
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._image_label.setStyleSheet(f"background: {Theme.MANTLE}; border: none;")
        layout.addWidget(self._image_label, stretch=1)

        # ── Bottom bar ──
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"background: {Theme.BASE}; border-top: 1px solid {Theme.BORDER};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 8, 16, 8)

        # Prev button
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedSize(44, 36)
        self._prev_btn.clicked.connect(self._go_prev)
        bar_layout.addWidget(self._prev_btn)

        # Info label
        self._info_label = QLabel()
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 12px;")
        bar_layout.addWidget(self._info_label, stretch=1)

        # Next button
        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedSize(44, 36)
        self._next_btn.clicked.connect(self._go_next)
        bar_layout.addWidget(self._next_btn)

        # Open externally
        open_btn = QPushButton("📂 Open File")
        open_btn.setFixedHeight(36)
        open_btn.clicked.connect(self._open_external)
        bar_layout.addWidget(open_btn)

        # Close
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(44, 36)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1}; color: {Theme.RED};
                border: 1px solid {Theme.BORDER}; border-radius: 6px;
                font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {Theme.RED}; color: {Theme.CRUST}; }}
        """)
        close_btn.clicked.connect(self.close)
        bar_layout.addWidget(close_btn)

        layout.addWidget(bar)

    def _show_current(self):
        if not self._paths:
            self._image_label.setText("No images available")
            return

        path = self._paths[self._index]
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            # Scale to fit while keeping aspect ratio
            scaled = pixmap.scaled(
                self._image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)
        else:
            self._image_label.setText(f"Cannot load: {path}")

        # Info
        label = self._labels[self._index] if self._index < len(self._labels) else ""
        self._info_label.setText(f"{label}  —  {self._index + 1} / {len(self._paths)}")

        # Nav button state
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < len(self._paths) - 1)

    def _go_prev(self):
        if self._index > 0:
            self._index -= 1
            self._show_current()

    def _go_next(self):
        if self._index < len(self._paths) - 1:
            self._index += 1
            self._show_current()

    def _open_external(self):
        if self._paths:
            subprocess.Popen(['open', self._paths[self._index]])

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            self._go_prev()
        elif event.key() == Qt.Key.Key_Right:
            self._go_next()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-scale image on resize
        if self._paths:
            self._show_current()

    @staticmethod
    def show_preview(
        parent: QWidget,
        image_paths: List[str],
        start_index: int = 0,
        labels: Optional[List[str]] = None,
    ):
        """Convenience: open modal image preview dialog."""
        dlg = ImagePreviewDialog(parent, image_paths, start_index, labels)
        dlg.exec()


# ═══════════════════════════════════════════════════════════════════
#  VideoPreviewDialog — Stage 6 & 7
# ═══════════════════════════════════════════════════════════════════

class VideoPreviewDialog(QDialog):
    """In-app video player with navigation for pipeline videos.

    Usage:
        VideoPreviewDialog.show_preview(parent, paths, start_index)
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        video_paths: List[str],
        start_index: int = 0,
        labels: Optional[List[str]] = None,
    ):
        from PySide6.QtMultimediaWidgets import QVideoWidget
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

        super().__init__(parent)
        self._paths = [p for p in video_paths if p and os.path.isfile(p)]
        self._labels = labels or [os.path.basename(p) for p in self._paths]
        self._index = min(start_index, len(self._paths) - 1) if self._paths else 0
        self._seeking = False

        self.setWindowTitle("🎬 Video Preview")
        self.setStyleSheet(_DIALOG_STYLE)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        # Size: 80% of screen
        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.8)
        h = int(screen.height() * 0.8)
        self.resize(w, h)

        # Media player
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._video_widget = QVideoWidget()
        self._player.setVideoOutput(self._video_widget)
        self._video_widget.setStyleSheet(f"background: {Theme.MANTLE};")

        # Connect signals
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

        self._setup_ui()
        self._load_current()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Video area ──
        layout.addWidget(self._video_widget, stretch=1)

        # ── Controls bar ──
        controls = QWidget()
        controls.setFixedHeight(56)
        controls.setStyleSheet(f"background: {Theme.BASE}; border-top: 1px solid {Theme.BORDER};")
        ctrl_layout = QHBoxLayout(controls)
        ctrl_layout.setContentsMargins(16, 8, 16, 8)

        # Nav prev
        self._prev_btn = QPushButton("◀")
        self._prev_btn.setFixedSize(44, 36)
        self._prev_btn.clicked.connect(self._go_prev)
        ctrl_layout.addWidget(self._prev_btn)

        # Play/Pause
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedSize(44, 36)
        self._play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.GREEN}; color: {Theme.CRUST};
                border: none; border-radius: 6px;
                font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {Theme.TEAL}; }}
        """)
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl_layout.addWidget(self._play_btn)

        # Time label
        self._time_label = QLabel("0:00")
        self._time_label.setFixedWidth(50)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._time_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-family: monospace;")
        ctrl_layout.addWidget(self._time_label)

        # Progress slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        ctrl_layout.addWidget(self._slider, stretch=1)

        # Duration label
        self._duration_label = QLabel("0:00")
        self._duration_label.setFixedWidth(50)
        self._duration_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._duration_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-family: monospace;")
        ctrl_layout.addWidget(self._duration_label)

        # Info
        self._info_label = QLabel()
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        self._info_label.setFixedWidth(100)
        ctrl_layout.addWidget(self._info_label)

        # Nav next
        self._next_btn = QPushButton("▶")
        self._next_btn.setFixedSize(44, 36)
        self._next_btn.clicked.connect(self._go_next)
        ctrl_layout.addWidget(self._next_btn)

        # Open externally
        open_btn = QPushButton("📂")
        open_btn.setFixedSize(44, 36)
        open_btn.setToolTip("Open in external player")
        open_btn.clicked.connect(self._open_external)
        ctrl_layout.addWidget(open_btn)

        # Close
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(44, 36)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1}; color: {Theme.RED};
                border: 1px solid {Theme.BORDER}; border-radius: 6px;
                font-size: 16px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {Theme.RED}; color: {Theme.CRUST}; }}
        """)
        close_btn.clicked.connect(self.close)
        ctrl_layout.addWidget(close_btn)

        layout.addWidget(controls)

    def _load_current(self):
        if not self._paths:
            return

        self._player.stop()
        path = self._paths[self._index]
        self._player.setSource(QUrl.fromLocalFile(path))

        # Auto-play
        QTimer.singleShot(100, self._player.play)

        # Update info
        label = self._labels[self._index] if self._index < len(self._labels) else ""
        self._info_label.setText(f"{self._index + 1} / {len(self._paths)}")
        self.setWindowTitle(f"🎬 {label}")

        # Nav state
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < len(self._paths) - 1)

    def _toggle_play(self):
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_position_changed(self, pos: int):
        if not self._seeking:
            self._slider.setValue(pos)
        self._time_label.setText(_ms_to_time(pos))

    def _on_duration_changed(self, dur: int):
        self._slider.setRange(0, dur)
        self._duration_label.setText(_ms_to_time(dur))

    def _on_state_changed(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸")
        else:
            self._play_btn.setText("▶")

    def _on_slider_pressed(self):
        self._seeking = True

    def _on_slider_released(self):
        self._player.setPosition(self._slider.value())
        self._seeking = False

    def _go_prev(self):
        if self._index > 0:
            self._index -= 1
            self._load_current()

    def _go_next(self):
        if self._index < len(self._paths) - 1:
            self._index += 1
            self._load_current()

    def _open_external(self):
        if self._paths:
            subprocess.Popen(['open', self._paths[self._index]])

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space:
            self._toggle_play()
        elif event.key() == Qt.Key.Key_Left:
            self._go_prev()
        elif event.key() == Qt.Key.Key_Right:
            self._go_next()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._player.stop()
        super().closeEvent(event)

    @staticmethod
    def show_preview(
        parent: QWidget,
        video_paths: List[str],
        start_index: int = 0,
        labels: Optional[List[str]] = None,
    ):
        """Convenience: open modal video preview dialog."""
        dlg = VideoPreviewDialog(parent, video_paths, start_index, labels)
        dlg.exec()
