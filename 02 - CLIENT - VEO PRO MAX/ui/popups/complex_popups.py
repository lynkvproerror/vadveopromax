"""
VEO Pro Max - Complex Popups (PySide6)

Contains: EditPromptPopup, AddProfileDialog, HelpTooltipPopup, 
          ImageManagerPopup, LicenseExpirationDialog
Migrated from CustomTkinter to PySide6.
"""

from typing import Optional, Callable, List, Dict
import sys
import webbrowser
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QTextEdit, QLineEdit, QScrollArea, QGridLayout,
    QFileDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from ui.popups.popups import BasePopup


class EditPromptPopup(BasePopup):
    """Edit Prompt Popup with character count (PySide6)."""
    
    MAX_CHARS = 500
    
    # Signals
    saved = Signal(int, str)  # row_index, prompt_text
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        row_index: int = 0,
        prompt_text: str = "",
        on_save: Optional[Callable[[int, str], None]] = None,
    ):
        self.row_index = row_index
        self.prompt_text = prompt_text
        self.on_save = on_save
        
        super().__init__(parent, title=f"📝 EDIT PROMPT - Row #{row_index}", width=500, height=280)
    
    def _create_content(self):
        """Create prompt editor."""
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        
        # Prompt textbox
        self.prompt_textbox = QTextEdit()
        self.prompt_textbox.setStyleSheet(f"background-color: {Theme.SURFACE0}; color: {Theme.TEXT};")
        self.prompt_textbox.setPlainText(self.prompt_text)
        self.prompt_textbox.textChanged.connect(self._update_char_count)
        self.content_layout.addWidget(self.prompt_textbox)
        
        # Character count
        self.char_count_label = QLabel(f"Character Count: {len(self.prompt_text)}/{self.MAX_CHARS}")
        self.char_count_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        self.content_layout.addWidget(self.char_count_label)
        
        self._main_layout.addWidget(self.content, stretch=1)
        self._update_char_count()
    
    def _create_footer(self):
        """Create footer with Cancel and Save buttons."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("variant", "secondary")
        cancel_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(cancel_btn)
        
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
        self.save_btn.clicked.connect(self._on_save)
        self.footer_layout.addWidget(self.save_btn)
        
        self._main_layout.addWidget(self.footer)
    
    def _update_char_count(self):
        """Update character count display."""
        text = self.prompt_textbox.toPlainText()
        count = len(text)
        
        color = Theme.RED if count > self.MAX_CHARS else Theme.SUBTEXT0
        self.char_count_label.setText(f"Character Count: {count}/{self.MAX_CHARS}")
        self.char_count_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        
        self.save_btn.setEnabled(count <= self.MAX_CHARS)
    
    def _on_save(self):
        """Save prompt and close."""
        text = self.prompt_textbox.toPlainText().strip()
        self._result = text
        
        self.saved.emit(self.row_index, text)
        if self.on_save:
            self.on_save(self.row_index, text)
        
        self.accept()


class AddProfileDialog(BasePopup):
    """Add Chrome profile dialog with auto-detect (PySide6)."""
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        profile_data: Optional[Dict] = None,
    ):
        self._profile_data = profile_data or {}
        self._is_edit = bool(profile_data)
        self._detected_profiles = self._detect_chrome_profiles()
        self._selected_profile_path = None
        
        title = "✏️ Edit Profile" if self._is_edit else "➕ Add Chrome Profile"
        height = 380 if len(self._detected_profiles) > 0 else 280
        super().__init__(parent, title=title, width=480, height=height)
        
        self.email_entry.setFocus()
    
    def _detect_chrome_profiles(self) -> List[Dict]:
        """Detect Chrome profiles on Windows."""
        import os
        profiles = []
        
        try:
            chrome_data = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"
            
            if chrome_data.exists():
                # Check Default profile
                default_path = chrome_data / "Default"
                if default_path.exists():
                    profiles.append({
                        "name": "Default", 
                        "path": str(default_path),
                        "display": "Profile 1 (Default)"
                    })
                
                # Check Profile N folders
                for folder in sorted(chrome_data.iterdir()):
                    if folder.name.startswith("Profile ") and folder.is_dir():
                        num = folder.name.replace("Profile ", "")
                        profiles.append({
                            "name": folder.name, 
                            "path": str(folder),
                            "display": f"Profile {int(num)+1} ({folder.name})"
                        })
        except Exception as e:
            print(f"[AddProfileDialog] Error detecting profiles: {e}")
        
        return profiles
    
    def _create_content(self):
        """Create profile input form with auto-detect."""
        from PySide6.QtWidgets import QRadioButton, QButtonGroup, QScrollArea
        
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(10)
        
        # Profile selection (if profiles detected)
        if self._detected_profiles:
            profile_label = QLabel("Detected Chrome Profiles:")
            profile_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
            self.content_layout.addWidget(profile_label)
            
            # Scrollable profile list
            scroll = QScrollArea()
            scroll.setStyleSheet(f"background-color: {Theme.SURFACE0}; border-radius: 8px;")
            scroll.setWidgetResizable(True)
            scroll.setMaximumHeight(120)
            
            profile_container = QWidget()
            profile_layout = QVBoxLayout(profile_container)
            profile_layout.setContentsMargins(8, 8, 8, 8)
            profile_layout.setSpacing(4)
            
            self._profile_group = QButtonGroup(self)
            
            for i, profile in enumerate(self._detected_profiles):
                radio = QRadioButton(profile["display"])
                radio.setStyleSheet(f"color: {Theme.TEXT};")
                radio.setProperty("profile_path", profile["path"])
                self._profile_group.addButton(radio, i)
                profile_layout.addWidget(radio)
                
                # Select first by default
                if i == 0:
                    radio.setChecked(True)
                    self._selected_profile_path = profile["path"]
            
            self._profile_group.buttonClicked.connect(self._on_profile_selected)
            
            scroll.setWidget(profile_container)
            self.content_layout.addWidget(scroll)
        else:
            # No profiles detected - show manual entry
            no_profile_label = QLabel("⚠️ No Chrome profiles detected")
            no_profile_label.setStyleSheet(f"color: {Theme.YELLOW};")
            self.content_layout.addWidget(no_profile_label)
            
            # Manual path entry
            path_label = QLabel("Chrome Profile Path *")
            path_label.setStyleSheet(f"color: {Theme.TEXT};")
            self.content_layout.addWidget(path_label)
            
            path_layout = QHBoxLayout()
            self.path_entry = QLineEdit()
            self.path_entry.setPlaceholderText("C:\\Users\\...\\Chrome\\User Data\\Default")
            self.path_entry.setMinimumHeight(36)
            path_layout.addWidget(self.path_entry)
            
            browse_btn = QPushButton("📂")
            browse_btn.setFixedWidth(40)
            browse_btn.clicked.connect(self._on_browse)
            path_layout.addWidget(browse_btn)
            self.content_layout.addLayout(path_layout)
        
        # Email field (required)
        email_label = QLabel("Email Address *")
        email_label.setStyleSheet(f"color: {Theme.TEXT};")
        self.content_layout.addWidget(email_label)
        
        self.email_entry = QLineEdit()
        self.email_entry.setPlaceholderText("example@gmail.com")
        self.email_entry.setMinimumHeight(36)
        if self._profile_data.get("email"):
            self.email_entry.setText(self._profile_data["email"])
        self.content_layout.addWidget(self.email_entry)
        
        # Display name (optional)
        name_label = QLabel("Display Name (optional)")
        name_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        self.content_layout.addWidget(name_label)
        
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText("e.g. Work Account")
        self.name_entry.setMinimumHeight(36)
        if self._profile_data.get("display_name"):
            self.name_entry.setText(self._profile_data["display_name"])
        self.content_layout.addWidget(self.name_entry)
        
        self.content_layout.addStretch()
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _on_profile_selected(self, button):
        """Handle profile radio button selection."""
        self._selected_profile_path = button.property("profile_path")
    
    def _create_footer(self):
        """Create footer with Cancel and Add buttons."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("variant", "secondary")
        cancel_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(cancel_btn)
        
        add_btn = QPushButton("➕ Add Profile")
        add_btn.setStyleSheet(f"background-color: {Theme.GREEN};")
        add_btn.clicked.connect(self._on_save)
        self.footer_layout.addWidget(add_btn)
        
        self._main_layout.addWidget(self.footer)
    
    def _on_browse(self):
        """Browse for profile directory."""
        folder = QFileDialog.getExistingDirectory(self, "Select Chrome Profile Directory")
        if folder:
            self.path_entry.setText(folder)
    
    def _on_save(self):
        """Validate and save profile."""
        email = self.email_entry.text().strip()
        
        # Get path from selection or manual entry
        if self._detected_profiles:
            path = self._selected_profile_path
        else:
            path = self.path_entry.text().strip() if hasattr(self, 'path_entry') else ""
        
        if not email or not path:
            return
        
        self._result = {
            "email": email,
            "profile_path": path,
            "display_name": self.name_entry.text().strip(),
        }
        self.accept()


class HelpTooltipPopup(BasePopup):
    """Help/Info popup for contextual help (PySide6)."""
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Help",
        help_text: str = "",
        link_url: Optional[str] = None,
        link_text: str = "Learn more",
    ):
        self._help_text = help_text
        self._link_url = link_url
        self._link_text = link_text
        
        super().__init__(parent, title=f"❓ {title}", width=450, height=300)
    
    def _create_content(self):
        """Create help content area."""
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        
        # Help text in scroll area
        scroll = QScrollArea()
        scroll.setStyleSheet(f"background-color: {Theme.SURFACE0}; border-radius: 8px;")
        scroll.setWidgetResizable(True)
        
        help_label = QLabel(self._help_text)
        help_label.setStyleSheet(f"color: {Theme.TEXT}; padding: 8px;")
        help_label.setWordWrap(True)
        help_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(help_label)
        
        self.content_layout.addWidget(scroll)
        
        # Optional link
        if self._link_url:
            link_btn = QPushButton(f"🔗 {self._link_text}")
            link_btn.setStyleSheet(f"color: {Theme.BLUE}; background: transparent;")
            link_btn.clicked.connect(lambda: webbrowser.open(self._link_url))
            self.content_layout.addWidget(link_btn)
        
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_footer(self):
        """Create footer with close button."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        close_btn = QPushButton("Got it!")
        close_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
        close_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(close_btn)
        
        self._main_layout.addWidget(self.footer)


class ImageManagerPopup(BasePopup):
    """Image Library Manager popup (PySide6).
    
    Features:
    - Browse images with thumbnails in a scrollable grid
    - Filter by category (dynamic from library)
    - Search by tag or filename
    - Add images via file dialog
    - Delete images
    - Edit tags on images
    - Select image → insert [tag] into prompt (on_select callback)
    """
    
    THUMB_SIZE = 100
    GRID_COLS = 5
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_select: Optional[Callable[[str], None]] = None,
    ):
        self._on_select = on_select
        self._selected_category = "All"
        self._library = None
        self._cat_buttons: Dict[str, QPushButton] = {}
        
        super().__init__(parent, title="📂 Image Library", width=800, height=550)
        
        # Load library and populate
        self._init_library()
        self._reload_grid()
    
    def _init_library(self):
        """Initialize ImageLibrary connection."""
        try:
            from services.image_library import get_image_library
            self._library = get_image_library()
        except ImportError:
            self._library = None
    
    def _create_content(self):
        """Create split layout with category list and image grid."""
        self.content = QWidget()
        content_layout = QHBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Category sidebar
        sidebar = self._create_sidebar()
        content_layout.addWidget(sidebar)
        
        # Image grid area
        grid_area = self._create_grid_area()
        content_layout.addWidget(grid_area, stretch=1)
        
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_sidebar(self) -> QWidget:
        """Create category sidebar with dynamic categories."""
        self._sidebar_frame = QFrame()
        self._sidebar_frame.setFixedWidth(180)
        self._sidebar_frame.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        
        self._sidebar_layout = QVBoxLayout(self._sidebar_frame)
        self._sidebar_layout.setContentsMargins(8, 8, 8, 8)
        self._sidebar_layout.setSpacing(4)
        
        header = QLabel("📁 Categories")
        header.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        self._sidebar_layout.addWidget(header)
        
        # Category buttons container
        self._cat_container = QWidget()
        self._cat_layout = QVBoxLayout(self._cat_container)
        self._cat_layout.setContentsMargins(0, 0, 0, 0)
        self._cat_layout.setSpacing(2)
        self._sidebar_layout.addWidget(self._cat_container)
        
        self._sidebar_layout.addStretch()
        
        add_cat_btn = QPushButton("➕ New Category")
        add_cat_btn.setProperty("variant", "secondary")
        add_cat_btn.clicked.connect(self._on_add_category)
        self._sidebar_layout.addWidget(add_cat_btn)
        
        return self._sidebar_frame
    
    def _rebuild_category_buttons(self):
        """Rebuild category buttons from library."""
        # Clear existing
        for btn in self._cat_buttons.values():
            btn.deleteLater()
        self._cat_buttons.clear()
        
        # Default categories + dynamic from library
        default_cats = [("All", "📋")]
        if self._library:
            lib_cats = self._library.get_categories()
            for cat in lib_cats:
                if cat != "All":
                    icon = {"Characters": "👤", "Backgrounds": "🏞️",
                            "Objects": "📦", "Styles": "🎨"}.get(cat, "📂")
                    default_cats.append((cat, icon))
        
        for name, icon in default_cats:
            btn = QPushButton(f"{icon} {name}")
            is_active = (name == self._selected_category)
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding: 6px 8px;
                    background-color: {Theme.SURFACE2 if is_active else 'transparent'};
                    color: {Theme.BLUE if is_active else Theme.TEXT};
                    border: none;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.SURFACE1};
                }}
            """)
            btn.clicked.connect(lambda c, n=name: self._select_category(n))
            self._cat_layout.addWidget(btn)
            self._cat_buttons[name] = btn
    
    def _create_grid_area(self) -> QWidget:
        """Create image grid area with toolbar."""
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        add_btn = QPushButton("➕ Add Images")
        add_btn.setStyleSheet(f"background-color: {Theme.BLUE};")
        add_btn.clicked.connect(self._on_add_images)
        toolbar.addWidget(add_btn)
        
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("🔍 Search by tag...")
        self.search_entry.setFixedWidth(200)
        self.search_entry.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_entry)
        
        toolbar.addStretch()
        
        self.image_count = QLabel("0 images")
        self.image_count.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        toolbar.addWidget(self.image_count)
        
        layout.addLayout(toolbar)
        
        # Scrollable grid
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self._grid_scroll.setWidgetResizable(True)
        
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(8)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)
        self._grid_scroll.setWidget(self._grid_widget)
        
        layout.addWidget(self._grid_scroll)
        
        return area
    
    def _create_footer(self):
        """Create footer with close button."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setProperty("variant", "secondary")
        close_btn.clicked.connect(self._on_close)
        self.footer_layout.addWidget(close_btn)
        
        self._main_layout.addWidget(self.footer)
    
    def _reload_grid(self):
        """Reload image grid from library."""
        # Rebuild categories
        self._rebuild_category_buttons()
        
        # Clear grid
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not self._library:
            empty = QLabel("Library not available.\nCheck ImageLibrary service.")
            empty.setStyleSheet(f"color: {Theme.RED};")
            empty.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(empty, 0, 0)
            self.image_count.setText("0 images")
            return
        
        # Get images
        cat = self._selected_category if self._selected_category != "All" else None
        images = self._library.get_images(category=cat)
        
        # Apply search filter
        query = self.search_entry.text().strip().lower() if hasattr(self, 'search_entry') else ""
        if query:
            images = [img for img in images
                      if query in img.filename.lower()
                      or any(query in t.lower() for t in img.tags)]
        
        self.image_count.setText(f"{len(images)} images")
        
        if not images:
            empty = QLabel("No images found.\nClick '➕ Add Images' to import.")
            empty.setStyleSheet(f"color: {Theme.SUBTEXT0};")
            empty.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(empty, 0, 0, 1, self.GRID_COLS)
            return
        
        # Render image cards
        from PySide6.QtGui import QPixmap
        for i, img in enumerate(images):
            row = i // self.GRID_COLS
            col = i % self.GRID_COLS
            card = self._create_image_card(img)
            self._grid_layout.addWidget(card, row, col)
    
    def _create_image_card(self, img) -> QFrame:
        """Create a single image card widget."""
        from PySide6.QtGui import QPixmap
        
        card = QFrame()
        card.setFixedSize(self.THUMB_SIZE + 16, self.THUMB_SIZE + 50)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE1};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
            }}
            QFrame:hover {{
                border-color: {Theme.BLUE};
            }}
        """)
        card.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("border: none; background: transparent;")
        
        pixmap = QPixmap(img.path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(self.THUMB_SIZE, self.THUMB_SIZE,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            thumb.setPixmap(scaled)
        else:
            thumb.setText("🖼️")
            thumb.setStyleSheet(f"border: none; color: {Theme.OVERLAY0}; font-size: 28px;")
        
        layout.addWidget(thumb)
        
        # Tag label (first tag or filename)
        tag_text = img.tags[0] if img.tags else img.filename
        tag_label = QLabel(tag_text)
        tag_label.setAlignment(Qt.AlignCenter)
        tag_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 10px; border: none;")
        tag_label.setToolTip(f"Tags: {', '.join(img.tags)}\nPath: {img.path}")
        tag_label.setWordWrap(False)
        layout.addWidget(tag_label)
        
        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)
        
        # Select button
        select_btn = QPushButton("✓")
        select_btn.setFixedSize(24, 20)
        select_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.GREEN};
                color: {Theme.CRUST};
                border: none; border-radius: 3px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #B8F0B2; }}
        """)
        select_btn.setToolTip("Select this image")
        select_btn.clicked.connect(lambda _, t=tag_text: self._on_image_select(t))
        btn_row.addWidget(select_btn)
        
        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 20)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.RED};
                color: {Theme.CRUST};
                border: none; border-radius: 3px;
                font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #EBA0AC; }}
        """)
        del_btn.setToolTip("Delete from library")
        del_btn.clicked.connect(lambda _, iid=img.id: self._on_delete_image(iid))
        btn_row.addWidget(del_btn)
        
        layout.addLayout(btn_row)
        
        return card
    
    def _select_category(self, name: str):
        """Handle category selection."""
        self._selected_category = name
        self._reload_grid()
    
    def _on_search(self, text: str):
        """Handle search input change."""
        self._reload_grid()
    
    def _on_add_images(self):
        """Open file dialog to add images to library."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", "",
            "Image files (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff);;All files (*.*)"
        )
        if files and self._library:
            for f in files:
                tag = Path(f).stem
                cat = self._selected_category if self._selected_category != "All" else "All"
                self._library.add_image(f, tags=[tag], category=cat)
            self._reload_grid()
    
    def _on_delete_image(self, image_id: str):
        """Delete image from library."""
        if self._library:
            self._library.remove_image(image_id, delete_file=False)
            self._reload_grid()
    
    def _on_add_category(self):
        """Add new category via simple input dialog."""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if ok and name.strip() and self._library:
            self._library.add_category(name.strip())
            self._reload_grid()
    
    def _on_image_select(self, tag: str):
        """Handle image selection — callback to insert [tag] in prompt."""
        if self._on_select:
            self._on_select(tag)
        self._on_close()


class LicenseExpirationDialog(BasePopup):
    """License expiration warning/error dialog (PySide6)."""
    
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        days_remaining: int = 0,
        license_type: str = "Trial",
    ):
        self._days_remaining = days_remaining
        self._license_type = license_type
        self._is_expired = days_remaining <= 0
        
        title = "⚠️ License Expiration" if not self._is_expired else "❌ License Expired"
        super().__init__(parent, title=title, width=450, height=250)
    
    def _create_content(self):
        """Create warning/error message content."""
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        
        # Icon
        icon_text = "⚠️" if not self._is_expired else "❌"
        icon_color = Theme.YELLOW if not self._is_expired else Theme.RED
        icon = QLabel(icon_text)
        icon.setStyleSheet(f"color: {icon_color}; font-size: 48px;")
        icon.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(icon)
        
        # Message
        if self._is_expired:
            message = f"Your {self._license_type} license has expired.\n\nPlease renew to continue using VEO Pro Max."
        else:
            days = self._days_remaining
            message = f"Your {self._license_type} license will expire in {days} day{'s' if days != 1 else ''}.\n\nRenew now to avoid interruption."
        
        msg_label = QLabel(message)
        msg_label.setStyleSheet(f"color: {Theme.TEXT};")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setWordWrap(True)
        self.content_layout.addWidget(msg_label)
        
        # License info
        info = QLabel(f"License Type: {self._license_type}")
        info.setStyleSheet(f"color: {Theme.SUBTEXT0}; background-color: {Theme.SURFACE2}; padding: 8px;")
        info.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(info)
        
        self._main_layout.addWidget(self.content, stretch=1)
    
    def _create_footer(self):
        """Create footer with action buttons."""
        self.footer = QFrame()
        self.footer.setFixedHeight(50)
        self.footer.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(12, 8, 12, 8)
        
        self.footer_layout.addStretch()
        
        # Renew button
        renew_btn = QPushButton("🔄 Renew License")
        renew_btn.setStyleSheet(f"background-color: {Theme.GREEN};")
        renew_btn.clicked.connect(self._on_renew)
        self.footer_layout.addWidget(renew_btn)
        
        if not self._is_expired:
            continue_btn = QPushButton("Continue")
            continue_btn.setProperty("variant", "secondary")
            continue_btn.clicked.connect(self._on_close)
            self.footer_layout.addWidget(continue_btn)
        else:
            close_btn = QPushButton("Close App")
            close_btn.setStyleSheet(f"background-color: {Theme.RED};")
            close_btn.clicked.connect(self._on_close_app)
            self.footer_layout.addWidget(close_btn)
        
        self._main_layout.addWidget(self.footer)
    
    def _on_renew(self):
        """Handle renew button."""
        webbrowser.open("https://veopro.example.com/renew")
        self._result = "renew"
        self._on_close()
    
    def _on_close_app(self):
        """Close the entire application."""
        self._result = "close_app"
        self._on_close()


# Convenience functions
def show_edit_prompt(parent, row_index: int, prompt_text: str = "",
                     on_save: Optional[Callable[[int, str], None]] = None) -> Optional[str]:
    """Show edit prompt dialog."""
    dialog = EditPromptPopup(parent, row_index, prompt_text, on_save)
    return dialog.wait_for_close()
