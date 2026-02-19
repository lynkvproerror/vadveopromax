"""
VEO Pro Max - Sidebar Base Component (PySide6)

Reference: TAB_01_TEXT_TO_VIDEO.md → Sidebar section
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional, Callable
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QComboBox, QFrame, QFileDialog
)
from PySide6.QtCore import Qt, Signal

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.components.drop_widgets import FolderDropLineEdit


class SidebarBase(QWidget):
    """Base class for tab sidebars (PySide6).
    
    Fixed width: 240px
    Common widgets: Project Name, Output Folder, Aspect Ratio, etc.
    Subclasses add tab-specific widgets.
    """
    
    WIDTH = 240
    
    # Signals
    add_to_queue = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None, on_add_to_queue: Optional[Callable] = None):
        super().__init__(parent)
        
        self._on_add_to_queue = on_add_to_queue
        
        # Fixed width
        self.setFixedWidth(self.WIDTH)
        self.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        # Main layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)
        
        # Create common widgets
        self._create_widgets()
        
        # Create tab-specific widgets (implemented by subclass)
        self._create_tab_widgets()
        
        # Add stretch before bottom
        self._layout.addStretch()
        
        # Create bottom section
        self._create_bottom_section()
    
    def _create_section_label(self, text: str) -> QLabel:
        """Create a section label."""
        label = QLabel(text)
        label.setStyleSheet(f"""
            color: {Theme.SUBTEXT0};
            font-size: 11px;
            padding-top: 8px;
            padding-bottom: 2px;
        """)
        self._layout.addWidget(label)
        return label
    
    def _create_widgets(self):
        """Create common sidebar widgets."""
        # === PROJECT NAME ===
        self._create_section_label("📁 Project Name")
        
        self.project_name = QLineEdit()
        self.project_name.setPlaceholderText("T2V-Project-01")
        self.project_name.setMinimumHeight(32)
        self._layout.addWidget(self.project_name)
        
        # === OUTPUT FOLDER ===
        self._create_section_label("📂 Output Folder")
        
        self.output_folder = FolderDropLineEdit()
        self.output_folder.setPlaceholderText("D:/Projects/VEO (or drag folder here)")
        self.output_folder.setMinimumHeight(32)
        self._layout.addWidget(self.output_folder)
        
        self.browse_btn = QPushButton("📂 Browse")
        self.browse_btn.setMinimumHeight(28)
        self.browse_btn.setProperty("variant", "secondary")
        self.browse_btn.clicked.connect(self._browse_folder)
        self._layout.addWidget(self.browse_btn)
        
        # Auto-populate from global default settings
        global_settings = None
        try:
            from config.settings import get_settings
            global_settings = get_settings()
            if global_settings and global_settings.output_folder:
                self.output_folder.setText(global_settings.output_folder)
        except Exception:
            pass
        
        # === ASPECT RATIO ===
        self._create_section_label("📐 Aspect Ratio")
        
        self.aspect_ratio = QComboBox()
        self.aspect_ratio.addItems(["16:9 (Landscape)", "9:16 (Portrait)"])
        self.aspect_ratio.setMinimumHeight(32)
        # Auto-populate from AppSettings
        if global_settings:
            _ar = getattr(global_settings, 'default_aspect_ratio', 'LANDSCAPE')
            self.aspect_ratio.setCurrentText("9:16 (Portrait)" if "PORTRAIT" in _ar.upper() else "16:9 (Landscape)")
        self._layout.addWidget(self.aspect_ratio)
    
    def _create_tab_widgets(self):
        """Create tab-specific widgets. Override in subclass."""
        # Base implementation does nothing - subclasses override
        pass
    
    def _create_bottom_section(self):
        """Create bottom section with queue status and add button."""
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet(f"background-color: {Theme.BORDER};")
        separator.setMaximumHeight(1)
        self._layout.addWidget(separator)
        
        # Queue status
        self.queue_status = QLabel("📊 Queue: 0 pending")
        self.queue_status.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 4px 0;")
        self._layout.addWidget(self.queue_status)
        
        # Add to queue button
        self.add_queue_btn = QPushButton("📋 Add to Queue")
        self.add_queue_btn.setMinimumHeight(36)
        self.add_queue_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BLUE};
                color: {Theme.CRUST};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.LAVENDER};
            }}
        """)
        self.add_queue_btn.clicked.connect(self._handle_add_to_queue)
        self._layout.addWidget(self.add_queue_btn)
    
    def _handle_add_to_queue(self):
        """Handle add to queue button click."""
        self.add_to_queue.emit()
        if self._on_add_to_queue:
            self._on_add_to_queue()
    
    def _browse_folder(self):
        """Open folder picker dialog."""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder.setText(folder)
    
    def set_queue_count(self, count: int):
        """Update queue status display."""
        self.queue_status.setText(f"📊 Queue: {count} pending")
    
    def get_project_name(self) -> str:
        """Get current project name."""
        return self.project_name.text() or "Untitled"
    
    def get_output_folder(self) -> str:
        """Get current output folder."""
        return self.output_folder.text()
    
    def get_aspect_ratio(self) -> str:
        """Get selected aspect ratio."""
        value = self.aspect_ratio.currentText()
        if "Landscape" in value:
            return "LANDSCAPE"
        return "PORTRAIT"
    
    def get_values(self) -> dict:
        """Get all sidebar values as a dictionary."""
        return {
            "project_name": self.get_project_name(),
            "output_folder": self.get_output_folder(),
            "aspect_ratio": self.get_aspect_ratio(),
        }
    
    def set_values(self, data: dict):
        """Restore sidebar values from a dictionary."""
        if "project_name" in data:
            self.project_name.setText(data["project_name"])
        if "output_folder" in data:
            self.output_folder.setText(data["output_folder"])
        if "aspect_ratio" in data:
            ar = data["aspect_ratio"]
            for i in range(self.aspect_ratio.count()):
                if ar.lower() in self.aspect_ratio.itemText(i).lower():
                    self.aspect_ratio.setCurrentIndex(i)
                    break
    
    def apply_defaults(self):
        """Re-read AppSettings and push defaults to sidebar widgets (live-update)."""
        try:
            from config.settings import get_settings
            s = get_settings()
            if s.output_folder:
                self.output_folder.setText(s.output_folder)
            ar = getattr(s, 'default_aspect_ratio', 'LANDSCAPE')
            self.aspect_ratio.setCurrentText(
                "9:16 (Portrait)" if "PORTRAIT" in ar.upper() else "16:9 (Landscape)"
            )
        except Exception:
            pass


class VideoSidebar(SidebarBase):
    """Sidebar for video generation tabs (T2V, I2V, R2V).
    
    Additional widgets: Outputs/Prompt, AI Model, Download Quality
    """
    
    # Signals
    image_library_clicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None, show_image_library: bool = False, **kwargs):
        self._show_image_library = show_image_library
        super().__init__(parent, **kwargs)
    
    def _create_tab_widgets(self):
        """Create video-specific sidebar widgets."""
        # Load defaults from AppSettings
        _s = None
        try:
            from config.settings import get_settings
            _s = get_settings()
        except Exception:
            pass
        
        # === OUTPUTS PER PROMPT ===
        self._create_section_label("🎬 Outputs/Prompt")
        
        self.outputs_per_prompt = QComboBox()
        self.outputs_per_prompt.addItems(["1 video", "2 videos", "3 videos", "4 videos"])
        _oc = getattr(_s, 'default_output_count', 4) if _s else 4
        self.outputs_per_prompt.setCurrentText(f"{_oc} video" if _oc == 1 else f"{_oc} videos")
        self.outputs_per_prompt.setMinimumHeight(32)
        self._layout.addWidget(self.outputs_per_prompt)
        
        # === AI MODEL ===
        self._create_section_label("🤖 AI Model")
        
        self.model = QComboBox()
        self.model.addItems([
            "Veo 3.1 - Fast",
            "Veo 3.1 - Fast [LP]",
            "Veo 3.1 - Quality",
            "Veo 2 - Fast",
            "Veo 2 - Quality",
        ])
        if _s:
            _m = getattr(_s, 'default_model', 'Veo 3.1 - Fast')
            idx = self.model.findText(_m)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
        self.model.setMinimumHeight(32)
        self._layout.addWidget(self.model)
        
        # === DOWNLOAD QUALITY ===
        self._create_section_label("📹 Download Quality")
        
        self.download_quality = QComboBox()
        self.download_quality.addItems(["720p", "1080p", "4K"])
        if _s:
            _dq = getattr(_s, 'default_download_quality', '1080p')
            self.download_quality.setCurrentText(_dq)
        self.download_quality.setMinimumHeight(32)
        self._layout.addWidget(self.download_quality)
        
        # === IMAGE LIBRARY BUTTON ===
        if self._show_image_library:
            self.image_library_btn = QPushButton("📂 Image Library")
            self.image_library_btn.setMinimumHeight(32)
            self.image_library_btn.setProperty("variant", "secondary")
            self.image_library_btn.clicked.connect(self._on_open_image_library)
            self._layout.addWidget(self.image_library_btn)
    
    def _on_open_image_library(self):
        """Open Image Library Popup."""
        self.image_library_clicked.emit()
    
    def get_outputs_count(self) -> int:
        """Get number of outputs per prompt."""
        value = self.outputs_per_prompt.currentText()
        return int(value.split()[0])
    
    def get_model(self) -> str:
        """Get selected AI model."""
        return self.model.currentText()
    
    def get_download_quality(self) -> str:
        """Get selected download quality."""
        return self.download_quality.currentText()
    
    def apply_defaults(self):
        """Re-read AppSettings and push video defaults to sidebar (live-update)."""
        super().apply_defaults()
        try:
            from config.settings import get_settings
            s = get_settings()
            # Outputs per prompt
            oc = getattr(s, 'default_output_count', 4)
            self.outputs_per_prompt.setCurrentText(f"{oc} video" if oc == 1 else f"{oc} videos")
            # AI Model
            m = getattr(s, 'default_model', 'Veo 3.1 - Fast')
            idx = self.model.findText(m)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
            # Download Quality
            dq = getattr(s, 'default_download_quality', '1080p')
            self.download_quality.setCurrentText(dq)
        except Exception:
            pass
    
    def get_values(self) -> dict:
        """Get all sidebar values as a dictionary (includes video-specific fields)."""
        values = super().get_values()
        values.update({
            "outputs_per_prompt": self.get_outputs_count(),
            "model": self.get_model(),
            "download_quality": self.get_download_quality(),
        })
        return values
    
    def set_values(self, data: dict):
        """Restore video sidebar values from a dictionary."""
        super().set_values(data)
        if "outputs_per_prompt" in data:
            target = f"{data['outputs_per_prompt']} video"
            for i in range(self.outputs_per_prompt.count()):
                if self.outputs_per_prompt.itemText(i).startswith(str(data['outputs_per_prompt'])):
                    self.outputs_per_prompt.setCurrentIndex(i)
                    break
        if "model" in data:
            idx = self.model.findText(data["model"])
            if idx >= 0:
                self.model.setCurrentIndex(idx)
        if "download_quality" in data:
            idx = self.download_quality.findText(data["download_quality"])
            if idx >= 0:
                self.download_quality.setCurrentIndex(idx)


class ImageSidebar(SidebarBase):
    """Sidebar for image generation tabs (T2I, I2I).
    
    Uses purple accent color.
    """
    
    # Signals
    image_library_clicked = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None, show_image_library: bool = False, **kwargs):
        self._show_image_library = show_image_library
        super().__init__(parent, **kwargs)
        
        # Override button color to purple
        self.add_queue_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.PURPLE};
                color: {Theme.CRUST};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.PURPLE_HOVER};
            }}
        """)
        
        # Update aspect ratio for image tabs
        # Must re-apply saved value after clear/addItems resets index to 0
        self.aspect_ratio.clear()
        self.aspect_ratio.addItems([
            "16:9 (Landscape)",
            "9:16 (Portrait)",
        ])
        # Re-apply saved aspect ratio from AppSettings (wiped by clear+addItems above)
        try:
            from config.settings import get_settings
            _s = get_settings()
            _ar = getattr(_s, 'default_aspect_ratio', 'LANDSCAPE')
            self.aspect_ratio.setCurrentText(
                "9:16 (Portrait)" if "PORTRAIT" in _ar.upper() else "16:9 (Landscape)"
            )
        except Exception:
            pass
    
    def _create_tab_widgets(self):
        """Create image-specific sidebar widgets."""
        # Load defaults from AppSettings
        _s = None
        try:
            from config.settings import get_settings
            _s = get_settings()
        except Exception:
            pass
        
        # === OUTPUTS PER PROMPT ===
        self._create_section_label("🎯 Outputs/Prompt")
        
        self.outputs_per_prompt = QComboBox()
        self.outputs_per_prompt.addItems(["1 image", "2 images", "3 images", "4 images"])
        _oc = getattr(_s, 'default_output_count', 4) if _s else 4
        self.outputs_per_prompt.setCurrentText(f"{_oc} image" if _oc == 1 else f"{_oc} images")
        self.outputs_per_prompt.setMinimumHeight(32)
        self._layout.addWidget(self.outputs_per_prompt)
        
        # === AI MODEL ===
        self._create_section_label("🤖 AI Model")
        
        self.model = QComboBox()
        self.model.addItems([
            "🔥 Nano Banana Pro",
            "🔥 Nano Banana",
            "Imagen 4",
        ])
        if _s:
            _im = getattr(_s, 'default_image_model', '🔥 Nano Banana Pro')
            idx = self.model.findText(_im)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
        self.model.setMinimumHeight(32)
        self._layout.addWidget(self.model)
        
        # === DOWNLOAD QUALITY ===
        # API: /v1/flow/upsampleImage → targetResolution
        # 1k = direct download (no upscale needed)
        # 2k = UPSAMPLE_IMAGE_RESOLUTION_2K
        # 4k = UPSAMPLE_IMAGE_RESOLUTION_4K
        self._create_section_label("🖼️ Download Quality")
        
        self.download_quality = QComboBox()
        self.download_quality.addItems(["1k", "2k", "4k"])
        if _s:
            _iq = getattr(_s, 'default_image_quality', '1k')
            self.download_quality.setCurrentText(_iq)
        self.download_quality.setMinimumHeight(32)
        self._layout.addWidget(self.download_quality)
        
        # === IMAGE LIBRARY BUTTON ===
        if self._show_image_library:
            self.image_library_btn = QPushButton("📂 Image Library")
            self.image_library_btn.setMinimumHeight(32)
            self.image_library_btn.setProperty("variant", "secondary")
            self.image_library_btn.clicked.connect(self._on_open_image_library)
            self._layout.addWidget(self.image_library_btn)
    
    def _on_open_image_library(self):
        """Open Image Library Popup."""
        self.image_library_clicked.emit()
    
    def get_outputs_count(self) -> int:
        """Get number of outputs per prompt."""
        value = self.outputs_per_prompt.currentText()
        return int(value.split()[0])
    
    def get_download_quality(self) -> str:
        """Get selected download quality."""
        return self.download_quality.currentText()
    
    def get_model(self) -> str:
        """Get selected image AI model (API key)."""
        _DISPLAY_TO_API = {
            "🔥 Nano Banana Pro": "GEM_PIX_2",
            "🔥 Nano Banana": "GEM_PIX",
            "Imagen 4": "IMAGEN_3_5",
        }
        return _DISPLAY_TO_API.get(self.model.currentText(), "GEM_PIX_2")
    
    def apply_defaults(self):
        """Re-read AppSettings and push image defaults to sidebar (live-update)."""
        super().apply_defaults()
        try:
            from config.settings import get_settings
            s = get_settings()
            # Outputs per prompt
            oc = getattr(s, 'default_output_count', 4)
            self.outputs_per_prompt.setCurrentText(f"{oc} image" if oc == 1 else f"{oc} images")
            # AI Model
            im = getattr(s, 'default_image_model', '🔥 Nano Banana Pro')
            idx = self.model.findText(im)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
            # Image Quality
            iq = getattr(s, 'default_image_quality', '1k')
            self.download_quality.setCurrentText(iq)
        except Exception:
            pass
    
    def get_values(self) -> dict:
        """Get all sidebar values as a dictionary (includes image-specific fields)."""
        values = super().get_values()
        values.update({
            "outputs_per_prompt": self.get_outputs_count(),
            "model": self.get_model(),
            "download_quality": self.get_download_quality(),
        })
        return values
    
    def set_values(self, data: dict):
        """Restore image sidebar values from a dictionary."""
        super().set_values(data)
        if "outputs_per_prompt" in data:
            for i in range(self.outputs_per_prompt.count()):
                if self.outputs_per_prompt.itemText(i).startswith(str(data['outputs_per_prompt'])):
                    self.outputs_per_prompt.setCurrentIndex(i)
                    break
        if "model" in data:
            # Try API key → display name mapping
            _API_TO_DISPLAY = {
                "GEM_PIX_2": "🔥 Nano Banana Pro",
                "GEM_PIX": "🔥 Nano Banana",
                "IMAGEN_3_5": "Imagen 4",
            }
            display = _API_TO_DISPLAY.get(data["model"], data["model"])
            idx = self.model.findText(display)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
        if "download_quality" in data:
            idx = self.download_quality.findText(data["download_quality"])
            if idx >= 0:
                self.download_quality.setCurrentIndex(idx)
