"""
VEO Pro Max — Image Enhance Dialog

Modal dialog for AI image enhancement.
Shows mode selector, live progress, before/after preview.
"""

import sys
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QProgressBar, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class EnhanceDialog(QDialog):
    """Image enhancement modal dialog.
    
    Usage:
        dialog = EnhanceDialog(image_path, enhancer_service, parent=self)
        if dialog.exec() == QDialog.Accepted:
            enhanced_path = dialog.result_path
    """
    
    enhance_complete = Signal(str)  # Emitted with output path on success
    
    MODES = [
        ("⬆️ Upscale 4× (Real-ESRGAN)", "upscale_4x"),
        ("⬆️ Upscale 2× (Real-ESRGAN)", "upscale_2x"),
        ("👤 Face Restore (GFPGAN)", "face_restore"),
        ("✨ Full (Upscale + Face)", "full"),
    ]
    
    def __init__(
        self,
        image_path: str,
        enhancer=None,
        parent=None,
    ):
        super().__init__(parent)
        self._image_path = image_path
        self._enhancer = enhancer
        self._result_path: Optional[str] = None
        self._is_processing = False
        
        self.setWindowTitle("✨ Enhance Image")
        self.setFixedSize(520, 460)
        self.setStyleSheet(f"background-color: {Theme.BASE}; color: {Theme.TEXT};")
        self.setModal(True)
        
        self._setup_ui()
    
    @property
    def result_path(self) -> Optional[str]:
        """Output path after successful enhancement."""
        return self._result_path
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Header
        header = QLabel("✨ AI Image Enhancement")
        header.setStyleSheet(f"color: {Theme.TEXT}; font-size: 16px; font-weight: bold;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        
        # Preview area (before)
        preview_frame = QFrame()
        preview_frame.setFixedHeight(200)
        preview_frame.setStyleSheet(
            f"background-color: {Theme.SURFACE0}; border-radius: 8px;"
        )
        preview_layout = QHBoxLayout(preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        
        # Before image
        before_col = QVBoxLayout()
        before_label = QLabel("Before")
        before_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px;")
        before_label.setAlignment(Qt.AlignCenter)
        before_col.addWidget(before_label)
        
        self._before_preview = QLabel()
        self._before_preview.setFixedSize(180, 160)
        self._before_preview.setAlignment(Qt.AlignCenter)
        self._before_preview.setStyleSheet(
            f"background-color: {Theme.SURFACE1}; border-radius: 4px;"
        )
        self._load_preview(self._image_path, self._before_preview)
        before_col.addWidget(self._before_preview)
        preview_layout.addLayout(before_col)
        
        # Arrow
        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 24px;")
        arrow.setAlignment(Qt.AlignCenter)
        arrow.setFixedWidth(40)
        preview_layout.addWidget(arrow)
        
        # After image  
        after_col = QVBoxLayout()
        after_label = QLabel("After")
        after_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px;")
        after_label.setAlignment(Qt.AlignCenter)
        after_col.addWidget(after_label)
        
        self._after_preview = QLabel("Enhanced image\nwill appear here")
        self._after_preview.setFixedSize(180, 160)
        self._after_preview.setAlignment(Qt.AlignCenter)
        self._after_preview.setStyleSheet(
            f"background-color: {Theme.SURFACE1}; border-radius: 4px;"
            f" color: {Theme.OVERLAY0}; font-size: 11px;"
        )
        after_col.addWidget(self._after_preview)
        preview_layout.addLayout(after_col)
        
        layout.addWidget(preview_frame)
        
        # File info
        filename = Path(self._image_path).name
        info = QLabel(f"📁 {filename}")
        info.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        layout.addWidget(info)
        
        # Mode selector row
        mode_row = QHBoxLayout()
        mode_label = QLabel("Mode:")
        mode_label.setFixedWidth(50)
        mode_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        mode_row.addWidget(mode_label)
        
        self._mode_combo = QComboBox()
        for display, _ in self.MODES:
            self._mode_combo.addItem(display)
        self._mode_combo.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; padding: 4px;"
        )
        mode_row.addWidget(self._mode_combo, stretch=1)
        layout.addLayout(mode_row)
        
        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedHeight(20)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Theme.SURFACE2};
                border-radius: 4px;
                text-align: center;
                font-size: 10px;
                color: {Theme.TEXT};
            }}
            QProgressBar::chunk {{
                background-color: {Theme.GREEN};
                border-radius: 4px;
            }}
        """)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)
        
        # Status text
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        self._status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status_label)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setMinimumSize(100, 32)
        self._cancel_btn.setProperty("variant", "secondary")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self._cancel_btn)
        
        self._enhance_btn = QPushButton("✨ Enhance")
        self._enhance_btn.setMinimumSize(120, 32)
        self._enhance_btn.setProperty("variant", "success")
        self._enhance_btn.clicked.connect(self._on_enhance)
        btn_row.addWidget(self._enhance_btn)
        
        layout.addLayout(btn_row)
    
    def _load_preview(self, path: str, label: QLabel):
        """Load image preview into label."""
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                label.width() - 4, label.height() - 4,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            label.setPixmap(scaled)
    
    def _on_enhance(self):
        """Start enhancement in background thread."""
        if self._is_processing:
            return
        if not self._enhancer:
            self._status_label.setText("❌ Enhancer service not available")
            return
        
        self._is_processing = True
        self._enhance_btn.setEnabled(False)
        self._enhance_btn.setText("⏳ Processing...")
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status_label.setText("Initializing...")
        
        # Get selected mode
        mode_idx = self._mode_combo.currentIndex()
        mode_value = self.MODES[mode_idx][1]
        
        # Run in background
        def _run():
            from core.image_enhancer import EnhanceMode
            mode_enum = EnhanceMode(mode_value)
            
            def _progress(pct, status):
                QTimer.singleShot(0, lambda: self._update_progress(pct, status))
            
            result = self._enhancer.enhance_sync(
                self._image_path,
                mode=mode_enum,
                progress_callback=_progress,
            )
            QTimer.singleShot(0, lambda: self._on_complete(result))
        
        threading.Thread(target=_run, daemon=True, name="enhance-dialog").start()
    
    def _update_progress(self, pct: int, status: str):
        """Update progress bar and status (called from main thread)."""
        self._progress.setValue(pct)
        self._status_label.setText(status)
    
    def _on_complete(self, result):
        """Handle enhancement completion."""
        self._is_processing = False
        self._enhance_btn.setEnabled(True)
        
        if result.success:
            self._result_path = result.output_path
            self._progress.setValue(100)
            self._status_label.setText("✅ Enhancement complete!")
            self._enhance_btn.setText("✅ Done")
            
            # Show after preview
            self._load_preview(result.output_path, self._after_preview)
            
            # Auto-close after 1.5s
            QTimer.singleShot(1500, self.accept)
        else:
            self._progress.setVisible(False)
            self._status_label.setText(f"❌ {result.error}")
            self._enhance_btn.setText("🔄 Retry")
    
    def _on_cancel(self):
        """Cancel enhancement."""
        if self._is_processing and self._enhancer:
            self._enhancer.cancel()
        self.reject()
