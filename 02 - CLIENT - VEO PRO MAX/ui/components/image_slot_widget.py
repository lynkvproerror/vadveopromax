"""
VEO Pro Max - Image Slot Widget

Reusable thumbnail slot for image-to-video prompts.
Supports: auto-detect from [tag], drag & drop, click-to-browse.
Used by: TabI2V (2 slots), TabR2V (3 slots), TabI2I (2-10 slots).
"""

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QToolTip, QSizePolicy, QMenu,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QSize
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QPainter, QColor

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme


class ImageSlotWidget(QFrame):
    """Single image slot with thumbnail preview.
    
    Features:
    - Display image thumbnail (80×80)
    - Auto-resolve [tag] from ImageLibrary
    - Drag & drop image files (auto-add to Library)
    - Click empty slot to browse
    - Clear button (✕)
    
    Signals:
        image_changed(str): Emitted when image changes (tag name or path)
        image_cleared(): Emitted when image is removed
    """
    
    image_changed = Signal(str)   # tag or path
    image_cleared = Signal()
    
    THUMB_SIZE = 72
    SLOT_SIZE = 84
    
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff'}
    
    def __init__(
        self,
        label: str = "",
        parent=None,
        accent_color: str = "",
        slot_size: int = 0,
    ):
        super().__init__(parent)
        self._label_text = label
        self._accent = accent_color or Theme.BLUE
        self._tag: str = ""
        self._image_path: str = ""
        self._library = None  # Lazy init to avoid circular import
        
        # Allow custom sizing for compact layouts
        if slot_size > 0:
            self.SLOT_SIZE = slot_size
            self.THUMB_SIZE = max(slot_size - 12, 20)
            # Compact label height for mini slots
            self._label_h = 14 if slot_size <= 50 else 20
        else:
            self._label_h = 28
        
        self.setAcceptDrops(True)
        self.setFixedSize(self.SLOT_SIZE + 8, self.SLOT_SIZE + self._label_h)
        self.setCursor(Qt.PointingHandCursor)
        self._setup_ui()
    
    def _get_library(self):
        """Lazy-load ImageLibrary singleton."""
        if self._library is None:
            try:
                from services.image_library import get_image_library
                self._library = get_image_library()
            except ImportError:
                pass
        return self._library
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)
        
        # Thumbnail container
        self._thumb_frame = QFrame()
        self._thumb_frame.setFixedSize(self.SLOT_SIZE, self.SLOT_SIZE)
        self._thumb_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE0};
                border: 2px dashed {Theme.BORDER};
                border-radius: 4px;
            }}
        """)
        thumb_layout = QVBoxLayout(self._thumb_frame)
        thumb_layout.setContentsMargins(4, 4, 4, 4)
        thumb_layout.setAlignment(Qt.AlignCenter)
        
        # Thumbnail image
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._thumb_label.setStyleSheet("border: none; background: transparent;")
        self._show_empty_state()
        thumb_layout.addWidget(self._thumb_label)
        
        layout.addWidget(self._thumb_frame)
        
        # Clear button (hidden when empty)
        self._clear_btn = QPushButton("✕")
        self._clear_btn.setMinimumSize(18, 18)
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.RED};
                color: {Theme.CRUST};
                border: none;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #EBA0AC;
            }}
        """)
        self._clear_btn.clicked.connect(self.clear)
        self._clear_btn.hide()
        # Position clear button at top-right of thumb_frame
        self._clear_btn.setParent(self._thumb_frame)
        self._clear_btn.move(self.SLOT_SIZE - 20, 2)
        
        # Tag/label text
        self._tag_label = QLabel(self._label_text or "Drop image")
        self._tag_label.setAlignment(Qt.AlignCenter)
        self._tag_label.setFixedWidth(self.SLOT_SIZE + 4)
        self._tag_label.setStyleSheet(f"""
            color: {Theme.SUBTEXT0};
            font-size: 10px;
            background: transparent;
            border: none;
        """)
        self._tag_label.setWordWrap(False)
        layout.addWidget(self._tag_label)
    
    def _show_empty_state(self):
        """Show empty placeholder."""
        self._thumb_label.setText("🖼️")
        self._thumb_label.setStyleSheet(f"""
            border: none;
            background: transparent;
            color: {Theme.OVERLAY0};
            font-size: 28px;
        """)
        self._thumb_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE0};
                border: 2px dashed {Theme.BORDER};
                border-radius: 4px;
            }}
        """)
    
    def _show_thumbnail(self, path: str):
        """Display image as thumbnail."""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self._show_empty_state()
            return
        
        scaled = pixmap.scaled(
            self.THUMB_SIZE, self.THUMB_SIZE,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._thumb_label.setPixmap(scaled)
        self._thumb_label.setStyleSheet("border: none; background: transparent;")
        self._thumb_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE0};
                border: 2px solid {self._accent};
                border-radius: 4px;
            }}
        """)
        self._clear_btn.show()
        self._clear_btn.raise_()
    
    # === PUBLIC API ===
    
    def set_tag(self, tag: str):
        """Resolve tag from ImageLibrary and show thumbnail."""
        self._tag = tag
        lib = self._get_library()
        if lib:
            img = lib.resolve_tag(tag)
            if img:
                self._image_path = img.path
                self._show_thumbnail(img.path)
                self._tag_label.setText(tag)
                self._tag_label.setToolTip(img.path)
                return
        # Tag not found — show pending indicator (auto-refreshes when library changes)
        self._tag_label.setText(f"⏳ {tag}")
        self._tag_label.setToolTip(f"Waiting for '{tag}' in library")
        self._show_empty_state()
    
    def refresh_tag(self):
        """Re-resolve stored tag from library.
        
        Called by PromptTable when ImageLibrary changes.
        Only re-resolves if tag is set but image is missing.
        """
        if self._tag and not self._image_path:
            self.set_tag(self._tag)
    
    def set_image_path(self, path: str, auto_tag: str = ""):
        """Set image directly from file path.
        
        If auto_tag is provided, use it. Otherwise generate from filename.
        Auto-adds to ImageLibrary.
        """
        if not Path(path).exists():
            return
        
        self._image_path = path
        tag = auto_tag or Path(path).stem
        self._tag = tag
        
        # Auto-add to library
        lib = self._get_library()
        if lib:
            existing = lib.resolve_tag(tag)
            if not existing:
                lib.add_image(path, tags=[tag])
        
        self._show_thumbnail(path)
        self._tag_label.setText(tag)
        self._tag_label.setToolTip(path)
        self.image_changed.emit(tag)
    
    def clear(self):
        """Clear the image slot."""
        self._tag = ""
        self._image_path = ""
        self._show_empty_state()
        self._clear_btn.hide()
        self._tag_label.setText(self._label_text or "Drop image")
        self._tag_label.setToolTip("")
        self.image_cleared.emit()
    
    @property
    def tag(self) -> str:
        return self._tag
    
    @property
    def image_path(self) -> str:
        return self._image_path
    
    @property
    def has_image(self) -> bool:
        return bool(self._image_path)
    
    # === EVENTS ===
    
    def mousePressEvent(self, event):
        """Click empty slot → open file dialog. Right-click → context menu."""
        if event.button() == Qt.RightButton and self._image_path:
            self._show_context_menu(event.globalPosition().toPoint())
            return
        if not self._image_path and event.button() == Qt.LeftButton:
            self._browse_image()
        super().mousePressEvent(event)
    
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
        
        # Enhance action (only if toggle enabled in Settings)
        enhance_act = None
        _show_enhance = True
        try:
            from config.settings import get_settings
            _show_enhance = getattr(get_settings(), 'enhance_context_menu', True)
        except Exception:
            pass
        if _show_enhance:
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
            # Find enhancer service from app controller
            enhancer = None
            app = self.window()
            if hasattr(app, 'controller') and hasattr(app.controller, 'image_enhancer'):
                enhancer = app.controller.image_enhancer
            
            dialog = EnhanceDialog(
                image_path=self._image_path,
                enhancer=enhancer,
                parent=self,
            )
            if dialog.exec() == EnhanceDialog.Accepted and dialog.result_path:
                # Update slot with enhanced image
                self.set_image_path(dialog.result_path)
        except Exception as e:
            print(f"[ImageSlot] Enhance error: {e}")
    
    def _browse_image(self):
        """Open file dialog to select image."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff)",
        )
        if path:
            self.set_image_path(path)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag if it contains image files."""
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    ext = Path(url.toLocalFile()).suffix.lower()
                    if ext in self.IMAGE_EXTENSIONS:
                        event.acceptProposedAction()
                        self._thumb_frame.setStyleSheet(f"""
                            QFrame {{
                                background-color: {Theme.SURFACE1};
                                border: 2px solid {self._accent};
                                border-radius: 4px;
                            }}
                        """)
                        return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Reset border on drag leave."""
        if not self._image_path:
            self._show_empty_state()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        """Handle dropped image file."""
        mime = event.mimeData()
        if mime.hasUrls():
            # Use tag from mime text if provided (e.g. from ImageLibrary drag)
            auto_tag = mime.text().strip() if mime.hasText() else ""
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    ext = Path(path).suffix.lower()
                    if ext in self.IMAGE_EXTENSIONS:
                        self.set_image_path(path, auto_tag=auto_tag)
                        event.acceptProposedAction()
                        return
        event.ignore()


class ImageSlotRow(QFrame):
    """A horizontal row of ImageSlotWidgets.
    
    Configurations per tab:
    - I2V: 2 fixed slots (Start, End)
    - R2V: 3 fixed slots (Ref 1, Ref 2, Ref 3)
    - I2I: 2 default + expandable to max_slots (10)
    """
    
    slots_changed = Signal()  # Emitted when any slot changes
    
    def __init__(
        self,
        slot_labels: list = None,
        max_slots: int = 2,
        expandable: bool = False,
        accent_color: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._max_slots = max_slots
        self._expandable = expandable
        self._accent = accent_color or Theme.BLUE
        self._slot_labels = slot_labels or []
        self._slots: list[ImageSlotWidget] = []
        
        self.setStyleSheet("background: transparent; border: none;")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignLeft)
        
        # Create initial slots
        initial_count = len(self._slot_labels) if self._slot_labels else 2
        initial_count = min(initial_count, max_slots)
        for i in range(initial_count):
            label = self._slot_labels[i] if i < len(self._slot_labels) else f"Img {i+1}"
            self._add_slot(label)
        
        # Add "+" button if expandable
        if self._expandable and initial_count < max_slots:
            self._add_plus_button()
    
    def _add_slot(self, label: str) -> ImageSlotWidget:
        """Add a new image slot."""
        slot = ImageSlotWidget(label=label, accent_color=self._accent)
        slot.image_changed.connect(lambda _: self.slots_changed.emit())
        slot.image_cleared.connect(self.slots_changed.emit)
        self._slots.append(slot)
        
        # Insert before "+" button if it exists
        idx = self._layout.count() - 1 if self._expandable else self._layout.count()
        idx = max(0, idx)
        self._layout.insertWidget(idx, slot)
        return slot
    
    def _add_plus_button(self):
        """Add expandable '+' button."""
        self._plus_btn = QPushButton("+")
        self._plus_btn.setMinimumSize(40, 40)
        self._plus_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1};
                color: {Theme.SUBTEXT0};
                border: 2px dashed {Theme.BORDER};
                border-radius: 4px;
                font-size: 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE2};
                color: {Theme.BLUE};
                border-color: {Theme.BLUE};
            }}
        """)
        self._plus_btn.setToolTip(f"Add image slot (max {self._max_slots})")
        self._plus_btn.clicked.connect(self._on_add_slot)
        self._layout.addWidget(self._plus_btn)
    
    def _on_add_slot(self):
        """Handle '+' button click."""
        if len(self._slots) >= self._max_slots:
            return
        idx = len(self._slots) + 1
        self._add_slot(f"Img {idx}")
        
        # Hide '+' if at max
        if len(self._slots) >= self._max_slots:
            self._plus_btn.hide()
    
    # === PUBLIC API ===
    
    def set_tags(self, tags: list):
        """Auto-fill slots from parsed tags.
        
        If expandable and tags > current slots, auto-expand.
        """
        # Auto-expand if needed (only for expandable mode)
        while self._expandable and len(tags) > len(self._slots) and len(self._slots) < self._max_slots:
            idx = len(self._slots) + 1
            self._add_slot(f"Img {idx}")
        
        # Fill slots
        for i, slot in enumerate(self._slots):
            if i < len(tags):
                slot.set_tag(tags[i])
            else:
                slot.clear()
        
        # Update '+' button visibility
        if self._expandable and hasattr(self, '_plus_btn'):
            self._plus_btn.setVisible(len(self._slots) < self._max_slots)
    
    def get_tags(self) -> list:
        """Get list of tags from all filled slots."""
        return [s.tag for s in self._slots if s.tag]
    
    def get_image_paths(self) -> list:
        """Get list of image paths from all filled slots."""
        return [s.image_path for s in self._slots if s.image_path]
    
    def clear_all(self):
        """Clear all slots."""
        for slot in self._slots:
            slot.clear()
    
    def set_slot_visibility(self, index: int, visible: bool):
        """Show/hide a specific slot by index."""
        if 0 <= index < len(self._slots):
            self._slots[index].setVisible(visible)
    
    @property
    def slot_count(self) -> int:
        return len(self._slots)
    
    @property
    def filled_count(self) -> int:
        return sum(1 for s in self._slots if s.has_image)
