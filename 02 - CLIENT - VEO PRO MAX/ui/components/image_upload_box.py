"""
VEO Pro Max - Image Upload Box Component (PySide6)

Reference: TAB_02_IMAGE_TO_VIDEO.md → Upload Areas
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional, Callable
from pathlib import Path
from enum import Enum
import sys

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame, QFileDialog, QMenu
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class UploadBoxState(Enum):
    """States for the upload box."""
    EMPTY = "empty"
    FILLED = "filled"
    LOCKED = "locked"
    AUTO = "auto"


class ImageUploadBox(QWidget):
    """Image upload box with click-to-browse, thumbnail preview (PySide6).
    
    Features:
    - Click to browse
    - Thumbnail preview
    - Clear button
    - Multiple states: Empty, Filled, Locked, Auto
    """
    
    DEFAULT_SIZE = 150
    THUMBNAIL_SIZE = 120
    
    # Signals
    image_changed = Signal(str)  # path or None
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        label: str = "Start Frame",
        size: int = DEFAULT_SIZE,
        on_image_change: Optional[Callable[[Optional[str]], None]] = None,
    ):
        super().__init__(parent)
        
        self.size = size
        self.label_text = label
        self.on_image_change = on_image_change
        
        self._image_path: Optional[str] = None
        self._state = UploadBoxState.EMPTY
        
        self.setFixedSize(size, size + 30)
        self._setup_ui()
        self._update_display()
    
    def _setup_ui(self):
        """Create upload box widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Label
        self.title_label = QLabel(self.label_text)
        self.title_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        # Upload zone frame
        self.upload_frame = QFrame()
        self.upload_frame.setFixedSize(self.size - 10, self.size - 10)
        self.upload_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE2};
                border: 1px dashed {Theme.BORDER};
            }}
        """)
        layout.addWidget(self.upload_frame, alignment=Qt.AlignCenter)
        
        # Frame layout
        frame_layout = QVBoxLayout(self.upload_frame)
        frame_layout.setContentsMargins(5, 5, 5, 5)
        
        # Drop zone label (shown when empty)
        self.drop_label = QLabel("📷\nDrop image\nor click")
        self.drop_label.setStyleSheet(f"color: {Theme.SUBTEXT1}; font-size: 11px;")
        self.drop_label.setAlignment(Qt.AlignCenter)
        frame_layout.addWidget(self.drop_label)
        
        # Thumbnail label (shown when filled)
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.hide()
        frame_layout.addWidget(self.thumbnail_label)
        
        # Clear button (shown when filled)
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setFixedSize(24, 24)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.RED};
                color: {Theme.TEXT};
                border-radius: 12px;
                font-size: 12px;
            }}
        """)
        self.clear_btn.clicked.connect(self.clear)
        self.clear_btn.hide()
        
        # Status labels
        self.lock_label = QLabel("🔒 Locked")
        self.lock_label.setStyleSheet(f"color: {Theme.YELLOW}; font-size: 11px; background-color: {Theme.SURFACE0}; padding: 2px 4px;")
        self.lock_label.setAlignment(Qt.AlignCenter)
        self.lock_label.hide()
        
        self.auto_label = QLabel("🔗 Auto")
        self.auto_label.setStyleSheet(f"color: {Theme.GREEN}; font-size: 11px; background-color: {Theme.SURFACE0}; padding: 2px 4px;")
        self.auto_label.setAlignment(Qt.AlignCenter)
        self.auto_label.hide()
        
        # Click handler
        self.upload_frame.mousePressEvent = self._on_click
        self.drop_label.mousePressEvent = self._on_click
    
    def _on_click(self, event=None):
        """Handle click to browse for image."""
        if self._state in (UploadBoxState.LOCKED, UploadBoxState.AUTO):
            return
        
        # Right-click → context menu (if image is loaded)
        if event and hasattr(event, 'button') and event.button() == Qt.RightButton and self._image_path:
            self._show_context_menu(event.globalPosition().toPoint())
            return
        
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All files (*.*)"
        )
        
        if path:
            self.set_image(path)
    
    def _show_context_menu(self, pos):
        """Show right-click context menu with Enhance option."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.OVERLAY0};
                padding: 4px;
            }}
            QMenu::item:selected {{
                background-color: {Theme.BLUE};
            }}
        """)
        
        enhance_act = menu.addAction("✨ Enhance Image")
        menu.addSeparator()
        copy_act = menu.addAction("📋 Copy Path")
        clear_act = menu.addAction("✕ Clear")
        
        action = menu.exec(pos)
        if action == enhance_act:
            self._open_enhance_dialog()
        elif action == copy_act:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._image_path)
        elif action == clear_act:
            self.clear()
    
    def _open_enhance_dialog(self):
        """Open the AI enhance dialog for this image."""
        if not self._image_path:
            return
        try:
            from ui.components.enhance_dialog import EnhanceDialog
            enhancer = None
            app = self.window()
            if hasattr(app, 'controller') and hasattr(app.controller, '_image_enhancer'):
                enhancer = app.controller._image_enhancer
            
            dialog = EnhanceDialog(
                image_path=self._image_path,
                enhancer=enhancer,
                parent=self,
            )
            if dialog.exec() == EnhanceDialog.Accepted and dialog.result_path:
                self.set_image(dialog.result_path)
        except Exception as e:
            print(f"[UploadBox] Enhance error: {e}")
    
    def set_image(self, path: str, state: UploadBoxState = UploadBoxState.FILLED):
        """Set the image path and update display."""
        self._image_path = path
        self._state = state
        self._update_display()
        
        self.image_changed.emit(path)
        if self.on_image_change:
            self.on_image_change(path)
    
    def clear(self):
        """Clear the current image."""
        if self._state == UploadBoxState.LOCKED:
            return
        
        self._image_path = None
        self._state = UploadBoxState.EMPTY
        self._update_display()
        
        self.image_changed.emit("")
        if self.on_image_change:
            self.on_image_change(None)
    
    def set_locked(self, locked: bool):
        """Set the locked state."""
        if self._image_path:
            self._state = UploadBoxState.LOCKED if locked else UploadBoxState.FILLED
            self._update_display()
    
    def set_auto(self, auto: bool):
        """Set the auto state (continuation frame)."""
        self._state = UploadBoxState.AUTO if auto else UploadBoxState.EMPTY
        self._update_display()
    
    def _update_display(self):
        """Update display based on current state."""
        # Hide all
        self.drop_label.hide()
        self.thumbnail_label.hide()
        self.clear_btn.hide()
        self.lock_label.hide()
        self.auto_label.hide()
        
        if self._state == UploadBoxState.EMPTY:
            self.drop_label.show()
            
        elif self._state == UploadBoxState.FILLED:
            self._show_thumbnail()
            self.clear_btn.show()
            self.clear_btn.raise_()
            
        elif self._state == UploadBoxState.LOCKED:
            self._show_thumbnail()
            self.lock_label.show()
            
        elif self._state == UploadBoxState.AUTO:
            self.auto_label.show()
    
    def _show_thumbnail(self):
        """Load and display thumbnail image."""
        if not self._image_path:
            return
        
        try:
            pixmap = QPixmap(self._image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.thumbnail_label.setPixmap(scaled)
                self.thumbnail_label.show()
        except Exception:
            # Show filename on error
            filename = Path(self._image_path).name if self._image_path else ""
            self.thumbnail_label.setText(filename[:15] + "...")
            self.thumbnail_label.show()
    
    def get_image_path(self) -> Optional[str]:
        """Get the current image path."""
        return self._image_path
    
    def get_state(self) -> UploadBoxState:
        """Get the current state."""
        return self._state
