"""
VEO Pro Max - P06: Video Player Popup - PySide6 Version

Reference: 01_POPUP_LAYOUTS.md P06
Inline video player popup for previewing generated videos.
Uses QMediaPlayer + QVideoWidget for native playback.

Debug flag: Set environment variable VEO_DEBUG_VIDEO=1 to enable
verbose logging of media pipeline state transitions.
"""

from typing import Optional
import sys
import os
import subprocess
import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QApplication, QStyle
)
from PySide6.QtCore import Qt, Slot, QUrl, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont

# Multimedia imports — gracefully degrade if not available
_HAS_MULTIMEDIA = False
try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _HAS_MULTIMEDIA = True
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.popups.popups import BasePopup

log = logging.getLogger("video_player")

# ── Debug flag ──
# Enable with: set VEO_DEBUG_VIDEO=1 (Windows) or export VEO_DEBUG_VIDEO=1 (Linux/Mac)
DEBUG_VIDEO = os.environ.get("VEO_DEBUG_VIDEO", "0") == "1"

def _dbg(msg: str):
    """Debug log — only prints when VEO_DEBUG_VIDEO=1."""
    if DEBUG_VIDEO:
        log.info(f"[VideoDBG] {msg}")
    else:
        log.debug(f"[VideoDBG] {msg}")


class VideoPlayerPopup(BasePopup):
    """
    Video preview popup (PySide6) with inline playback.
    
    Features:
    - Inline video playback via QMediaPlayer + QVideoWidget
    - Play/Pause toggle, seek slider, volume control
    - Video duration + position display
    - Fallback to placeholder if QtMultimedia unavailable
    - Open in external player option
    - Debug logging via VEO_DEBUG_VIDEO=1
    """
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        video_path: Optional[str] = None,
        video_title: str = "Video Preview",
    ):
        self._video_path = video_path
        self._video_title = video_title
        self._player = None
        self._audio = None
        self._is_seeking = False  # True while user drags slider
        
        _dbg(f"__init__: path={video_path}, title={video_title}")
        _dbg(f"__init__: QtMultimedia available = {_HAS_MULTIMEDIA}")
        
        # Check file existence early
        if video_path:
            p = Path(video_path)
            _dbg(f"__init__: file exists={p.exists()}, size={p.stat().st_size if p.exists() else 'N/A'}")
            if not p.exists():
                log.warning(f"[VideoPlayer] File not found: {video_path}")
        
        super().__init__(
            parent,
            title=f"🎬 {video_title}",
            width=720,
            height=520,
        )
    
    def _create_content(self):
        """Create video player content with inline playback."""
        self.content = QFrame()
        self.content.setStyleSheet(f"background-color: {Theme.BASE};")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(4)
        
        _dbg("_create_content: building UI")
        
        if _HAS_MULTIMEDIA and self._video_path and Path(self._video_path).exists():
            self._create_player()
        else:
            self._create_placeholder()
        
        # Controls bar
        self._create_controls()
        
        # Info bar
        if self._video_path:
            info_bar = QFrame()
            info_layout = QHBoxLayout(info_bar)
            info_layout.setContentsMargins(0, 0, 0, 0)
            
            path_label = QLabel(f"📁 {Path(self._video_path).name}")
            path_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
            info_layout.addWidget(path_label)
            info_layout.addStretch()
            
            # File size
            try:
                size_mb = Path(self._video_path).stat().st_size / (1024 * 1024)
                size_label = QLabel(f"💾 {size_mb:.1f} MB")
                size_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
                info_layout.addWidget(size_label)
            except Exception:
                pass
            
            self.content_layout.addWidget(info_bar)
        
        # Debug panel (only shown when VEO_DEBUG_VIDEO=1)
        if DEBUG_VIDEO:
            self._create_debug_panel()
        
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_player(self):
        """Create QMediaPlayer + QVideoWidget for inline playback."""
        _dbg("_create_player: creating QVideoWidget")
        
        # Video display widget
        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumHeight(300)
        self._video_widget.setStyleSheet("background-color: black; border-radius: 4px;")
        self.content_layout.addWidget(self._video_widget, stretch=1)
        
        # Audio output
        self._audio = QAudioOutput()
        self._audio.setVolume(0.7)
        _dbg(f"_create_player: audio output created, volume=0.7")
        
        # Media player
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)
        
        # Connect signals for debug + UI updates
        self._player.errorOccurred.connect(self._on_media_error)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        
        # Set source
        url = QUrl.fromLocalFile(str(Path(self._video_path).resolve()))
        _dbg(f"_create_player: setting source URL = {url.toString()}")
        self._player.setSource(url)
    
    def _create_placeholder(self):
        """Fallback placeholder when multimedia is not available."""
        _dbg("_create_placeholder: no multimedia or no file")
        
        video_frame = QFrame()
        video_frame.setStyleSheet(f"background-color: {Theme.CRUST}; border-radius: 4px;")
        video_layout = QVBoxLayout(video_frame)
        
        reason = ""
        if not _HAS_MULTIMEDIA:
            reason = "\n\n⚠️ PySide6-Multimedia not installed.\nInstall with: pip install PySide6-Multimedia"
        elif not self._video_path:
            reason = "\n\n⚠️ No video path provided."
        elif not Path(self._video_path).exists():
            reason = f"\n\n⚠️ File not found:\n{self._video_path}"
        
        placeholder = QLabel(
            f"🎬\n\nVideo preview not available.{reason}\n\n"
            "Use 'Open in Player' to view in external application."
        )
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 13px;")
        placeholder.setWordWrap(True)
        video_layout.addWidget(placeholder)
        
        self.content_layout.addWidget(video_frame, stretch=1)
    
    def _create_controls(self):
        """Create transport controls: play/pause, seek, time, volume."""
        controls = QFrame()
        controls.setFixedHeight(50)
        controls.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE0};
                border-radius: 4px;
            }}
        """)
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(8, 4, 8, 4)
        
        has_player = self._player is not None
        
        # Play/Pause button
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setMinimumWidth(90)
        self.play_btn.setFixedHeight(32)
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {Theme.LAVENDER};
            }}
            QPushButton:disabled {{
                background-color: {Theme.SURFACE2};
                color: {Theme.SUBTEXT0};
            }}
        """)
        self.play_btn.setEnabled(has_player)
        self.play_btn.clicked.connect(self._on_play_pause)
        controls_layout.addWidget(self.play_btn)
        
        # Seek slider
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(has_player)
        self.seek_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {Theme.SURFACE2};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.BLUE};
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Theme.BLUE};
                border-radius: 3px;
            }}
        """)
        self.seek_slider.sliderPressed.connect(self._on_seek_start)
        self.seek_slider.sliderReleased.connect(self._on_seek_end)
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)
        controls_layout.addWidget(self.seek_slider, stretch=1)
        
        # Time label
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setFixedWidth(90)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        controls_layout.addWidget(self.time_label)
        
        # Volume slider
        vol_icon = QLabel("🔊")
        vol_icon.setFixedWidth(20)
        controls_layout.addWidget(vol_icon)
        
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.setFixedWidth(70)
        self.vol_slider.setEnabled(has_player)
        self.vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {Theme.SURFACE2};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.GREEN};
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Theme.GREEN};
                border-radius: 2px;
            }}
        """)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        controls_layout.addWidget(self.vol_slider)
        
        self.content_layout.addWidget(controls)
    
    def _create_debug_panel(self):
        """Debug panel — only visible when VEO_DEBUG_VIDEO=1."""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.CRUST};
                border: 1px solid {Theme.YELLOW};
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(6, 4, 6, 4)
        panel_layout.setSpacing(2)
        
        header = QLabel("🐛 Video Debug (VEO_DEBUG_VIDEO=1)")
        header.setStyleSheet(f"color: {Theme.YELLOW}; font-weight: bold; font-size: 11px;")
        panel_layout.addWidget(header)
        
        self._debug_label = QLabel("Waiting for media events...")
        self._debug_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px;")
        self._debug_label.setWordWrap(True)
        panel_layout.addWidget(self._debug_label)
        
        self.content_layout.addWidget(panel)
        
        # Update debug panel periodically
        self._debug_timer = QTimer(self)
        self._debug_timer.timeout.connect(self._update_debug_panel)
        self._debug_timer.start(500)
    
    def _update_debug_panel(self):
        """Refresh debug panel with current player state."""
        if not hasattr(self, '_debug_label') or not self._player:
            return
        
        state_map = {
            QMediaPlayer.PlaybackState.StoppedState: "Stopped",
            QMediaPlayer.PlaybackState.PlayingState: "Playing",
            QMediaPlayer.PlaybackState.PausedState: "Paused",
        }
        
        status_map = {
            QMediaPlayer.MediaStatus.NoMedia: "NoMedia",
            QMediaPlayer.MediaStatus.LoadingMedia: "Loading",
            QMediaPlayer.MediaStatus.LoadedMedia: "Loaded",
            QMediaPlayer.MediaStatus.StalledMedia: "Stalled",
            QMediaPlayer.MediaStatus.BufferingMedia: "Buffering",
            QMediaPlayer.MediaStatus.BufferedMedia: "Buffered",
            QMediaPlayer.MediaStatus.EndOfMedia: "EndOfMedia",
            QMediaPlayer.MediaStatus.InvalidMedia: "InvalidMedia",
        }
        
        state = state_map.get(self._player.playbackState(), "Unknown")
        status = status_map.get(self._player.mediaStatus(), "Unknown")
        pos = self._player.position()
        dur = self._player.duration()
        error = self._player.errorString()
        src = self._player.source().toString() if self._player.source() else "None"
        has_video = self._player.hasVideoOutput() if hasattr(self._player, 'hasVideoOutput') else "?"
        
        lines = [
            f"State: {state} | Status: {status}",
            f"Pos: {pos}ms | Dur: {dur}ms | HasVideo: {has_video}",
            f"Source: {src}",
        ]
        if error:
            lines.append(f"⚠️ Error: {error}")
        
        self._debug_label.setText("\n".join(lines))
    
    def _create_footer(self):
        """Create footer with action buttons."""
        footer = QFrame()
        footer.setFixedHeight(50)
        footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 4, 8, 4)
        
        # Copy path button (left side)
        if self._video_path:
            copy_btn = QPushButton("📋 Copy Path")
            copy_btn.setMinimumWidth(100)
            copy_btn.clicked.connect(self._on_copy_path)
            footer_layout.addWidget(copy_btn)
        
        footer_layout.addStretch()
        
        # Open in external player
        open_btn = QPushButton("📺 Open in Player")
        open_btn.setMinimumWidth(130)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.LAVENDER};
            }}
        """)
        open_btn.clicked.connect(self._on_open_external)
        footer_layout.addWidget(open_btn)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(80)
        close_btn.setStyleSheet(
            f"QPushButton {{ background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"border: none; border-radius: {Theme.RADIUS_BTN}px; "
            f"padding: 8px 16px; font-weight: bold; font-size: 13px; }}"
            f"QPushButton:hover {{ background-color: {Theme.OVERLAY0}; }}"
        )
        close_btn.clicked.connect(self._on_close)
        footer_layout.addWidget(close_btn)
        
        self._main_layout.addWidget(footer)
    
    # ── Transport Controls ──
    
    @Slot()
    def _on_play_pause(self):
        """Toggle play/pause."""
        if not self._player:
            return
        
        state = self._player.playbackState()
        _dbg(f"_on_play_pause: current state = {state}")
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()
    
    @Slot()
    def _on_seek_start(self):
        """User started dragging seek slider."""
        self._is_seeking = True
        _dbg("_on_seek_start: user dragging")
    
    @Slot()
    def _on_seek_end(self):
        """User released seek slider."""
        if self._player:
            pos = self.seek_slider.value()
            _dbg(f"_on_seek_end: seeking to {pos}ms")
            self._player.setPosition(pos)
        self._is_seeking = False
    
    @Slot(int)
    def _on_seek_moved(self, pos: int):
        """Update time label while dragging (don't set player position yet)."""
        if self._player and self._is_seeking:
            dur = self._player.duration()
            self.time_label.setText(f"{self._fmt_time(pos)} / {self._fmt_time(dur)}")
    
    @Slot(int)
    def _on_volume_changed(self, value: int):
        """Update audio volume."""
        if self._audio:
            vol = value / 100.0
            self._audio.setVolume(vol)
            _dbg(f"_on_volume_changed: {vol:.2f}")
    
    # ── Media Player Signals ──
    
    @Slot()
    def _on_state_changed(self, state):
        """Handle playback state changes."""
        state_names = {
            QMediaPlayer.PlaybackState.StoppedState: "Stopped",
            QMediaPlayer.PlaybackState.PlayingState: "Playing",
            QMediaPlayer.PlaybackState.PausedState: "Paused",
        }
        name = state_names.get(state, f"Unknown({state})")
        _dbg(f"_on_state_changed: {name}")
        
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸ Pause")
        else:
            self.play_btn.setText("▶ Play")
        
        if state == QMediaPlayer.PlaybackState.StoppedState:
            # Reset seek to beginning
            self.seek_slider.setValue(0)
    
    @Slot(int)
    def _on_position_changed(self, position: int):
        """Update seek slider + time label as video plays."""
        if not self._is_seeking:
            self.seek_slider.setValue(position)
        dur = self._player.duration() if self._player else 0
        self.time_label.setText(f"{self._fmt_time(position)} / {self._fmt_time(dur)}")
    
    @Slot(int)
    def _on_duration_changed(self, duration: int):
        """Set seek slider range when media duration is known."""
        _dbg(f"_on_duration_changed: {duration}ms ({duration/1000:.1f}s)")
        self.seek_slider.setRange(0, duration)
    
    @Slot()
    def _on_media_status_changed(self, status):
        """Log media status transitions for debugging."""
        status_names = {
            QMediaPlayer.MediaStatus.NoMedia: "NoMedia",
            QMediaPlayer.MediaStatus.LoadingMedia: "LoadingMedia",
            QMediaPlayer.MediaStatus.LoadedMedia: "LoadedMedia",
            QMediaPlayer.MediaStatus.StalledMedia: "StalledMedia",
            QMediaPlayer.MediaStatus.BufferingMedia: "BufferingMedia",
            QMediaPlayer.MediaStatus.BufferedMedia: "BufferedMedia",
            QMediaPlayer.MediaStatus.EndOfMedia: "EndOfMedia",
            QMediaPlayer.MediaStatus.InvalidMedia: "InvalidMedia",
        }
        name = status_names.get(status, f"Unknown({status})")
        _dbg(f"_on_media_status_changed: {name}")
        
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            err = self._player.errorString() if self._player else "unknown"
            log.error(f"[VideoPlayer] InvalidMedia: {err}")
            _dbg(f"InvalidMedia error: {err}")
    
    @Slot()
    def _on_media_error(self, error, message=""):
        """Handle media player errors."""
        err_str = self._player.errorString() if self._player else str(error)
        log.error(f"[VideoPlayer] Media error: {error} — {err_str} — {message}")
        _dbg(f"_on_media_error: code={error}, msg={err_str}, detail={message}")
    
    # ── Actions ──
    
    @Slot()
    def _on_open_external(self):
        """Open video in default system player."""
        if self._video_path and Path(self._video_path).exists():
            _dbg(f"_on_open_external: opening {self._video_path}")
            if sys.platform == "win32":
                os.startfile(self._video_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", self._video_path])
            else:
                subprocess.run(["xdg-open", self._video_path])
        else:
            log.warning(f"[VideoPlayer] No video path or file not found: {self._video_path}")
    
    @Slot()
    def _on_copy_path(self):
        """Copy video path to clipboard."""
        if self._video_path:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._video_path)
            _dbg(f"_on_copy_path: copied {self._video_path}")
    
    def _on_close(self):
        """Clean up player before closing."""
        _dbg("_on_close: cleaning up")
        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())  # Release file handle
        if hasattr(self, '_debug_timer'):
            self._debug_timer.stop()
        super()._on_close()
    
    def closeEvent(self, event):
        """Ensure player is stopped when dialog is closed."""
        _dbg("closeEvent: stopping player")
        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())
        if hasattr(self, '_debug_timer'):
            self._debug_timer.stop()
        super().closeEvent(event)
    
    # ── Helpers ──
    
    @staticmethod
    def _fmt_time(ms: int) -> str:
        """Format milliseconds as M:SS."""
        if ms < 0:
            ms = 0
        secs = ms // 1000
        m, s = divmod(secs, 60)
        return f"{m}:{s:02d}"


# For testing
if __name__ == "__main__":
    os.environ["VEO_DEBUG_VIDEO"] = "1"  # Enable debug for testing
    logging.basicConfig(level=logging.DEBUG)
    
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    popup = VideoPlayerPopup(
        video_path="C:/test/video.mp4",
        video_title="Test Video"
    )
    popup.exec()
