"""
VEO Pro Max - P06: Video Player Popup - PySide6 Version

Reference: 01_POPUP_LAYOUTS.md P06
Simple video player popup for previewing generated videos.
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional
import sys
import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QApplication
)
from PySide6.QtCore import Qt, Slot

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.popups.popups import BasePopup


class VideoPlayerPopup(BasePopup):
    """
    Video preview popup (PySide6).
    
    Features:
    - Video thumbnail/placeholder
    - Basic controls (play/pause - placeholder)
    - Video info display
    - Open in external player option
    """
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        video_path: Optional[str] = None,
        video_title: str = "Video Preview",
    ):
        self._video_path = video_path
        self._video_title = video_title
        
        super().__init__(
            parent,
            title=f"🎬 {video_title}",
            width=640,
            height=480,
        )
    
    def _create_content(self):
        """Create video player content."""
        content = QFrame()
        content.setStyleSheet(f"background-color: {Theme.BASE};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Video area (placeholder - actual video requires QMediaPlayer)
        video_frame = QFrame()
        video_frame.setStyleSheet(f"background-color: {Theme.CRUST}; border-radius: 4px;")
        video_layout = QVBoxLayout(video_frame)
        
        # Placeholder message
        placeholder = QLabel(
            "🎬\n\nVideo preview not available.\n\n"
            "Use 'Open in Player' to view in external application."
        )
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 14px;")
        video_layout.addWidget(placeholder)
        
        layout.addWidget(video_frame, stretch=1)
        
        # Controls bar
        controls = QFrame()
        controls.setFixedHeight(50)
        controls.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(8, 4, 8, 4)
        
        # Play button (disabled - placeholder)
        self.play_btn = QPushButton("▶️ Play")
        self.play_btn.setFixedWidth(80)
        self.play_btn.setEnabled(False)
        controls_layout.addWidget(self.play_btn)
        
        # Progress bar (placeholder)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Theme.SURFACE2};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.BLUE};
                border-radius: 4px;
            }}
        """)
        controls_layout.addWidget(self.progress, stretch=1)
        
        # Time label
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        controls_layout.addWidget(self.time_label)
        
        layout.addWidget(controls)
        
        # Info bar
        if self._video_path:
            info_bar = QFrame()
            info_layout = QHBoxLayout(info_bar)
            info_layout.setContentsMargins(0, 0, 0, 0)
            
            path_label = QLabel(f"📁 {Path(self._video_path).name}")
            path_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
            info_layout.addWidget(path_label)
            info_layout.addStretch()
            
            layout.addWidget(info_bar)
        
        # Add to dialog content area
        self.content_layout.addWidget(content)
    
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
            copy_btn.setFixedWidth(100)
            copy_btn.clicked.connect(self._on_copy_path)
            footer_layout.addWidget(copy_btn)
        
        footer_layout.addStretch()
        
        # Open in external player
        open_btn = QPushButton("📺 Open in Player")
        open_btn.setFixedWidth(130)
        open_btn.setStyleSheet(f"background-color: {Theme.BLUE}; color: {Theme.CRUST};")
        open_btn.clicked.connect(self._on_open_external)
        footer_layout.addWidget(open_btn)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self._on_close)
        footer_layout.addWidget(close_btn)
        
        self.main_layout.addWidget(footer)
    
    @Slot()
    def _on_open_external(self):
        """Open video in default system player."""
        if self._video_path and Path(self._video_path).exists():
            if sys.platform == "win32":
                os.startfile(self._video_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", self._video_path])
            else:
                subprocess.run(["xdg-open", self._video_path])
        else:
            print("[VideoPlayer] No video path or file not found")
    
    @Slot()
    def _on_copy_path(self):
        """Copy video path to clipboard."""
        if self._video_path:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._video_path)
            print(f"[VideoPlayer] Copied: {self._video_path}")


# For testing
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    popup = VideoPlayerPopup(video_path="C:/test/video.mp4", video_title="Test Video")
    popup.exec()
