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
    - Non-modal: does not block main app interaction
    - Browse images with thumbnails in a scrollable grid
    - Filter by category (dynamic from library)
    - Search by tag or filename
    - Add images via file dialog or drag from Explorer
    - Drag images from popup into prompt thumbnails
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
        
        # Make non-modal so user can interact with main app
        self.setModal(False)
        # Use native title bar instead of custom header
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.header.hide()  # Hide redundant custom header
        self.footer.hide()  # Hide redundant Close button
        # Allow resizing
        self.setMinimumSize(600, 400)
        self.setMaximumSize(1200, 800)
        
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
            btn = _DroppableCategoryButton(f"{icon} {name}", name, self)
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
        
        # Scrollable grid with drop support
        self._grid_scroll = QScrollArea()
        self._grid_scroll.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setAcceptDrops(True)
        
        self._grid_widget = _DroppableGridWidget(self)
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
        """Create a single draggable image card widget."""
        from PySide6.QtGui import QPixmap
        
        tag_text = img.tags[0] if img.tags else img.filename
        card = _DraggableImageCard(img.path, tag_text, self.THUMB_SIZE, image_id=img.id)
        
        # Thumbnail
        pixmap = QPixmap(img.path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(self.THUMB_SIZE, self.THUMB_SIZE,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            card.thumb.setPixmap(scaled)
        else:
            card.thumb.setText("🖼️")
            card.thumb.setStyleSheet(f"border: none; color: {Theme.OVERLAY0}; font-size: 28px;")
        
        # Double-click thumbnail for full-size preview
        card.thumb.mouseDoubleClickEvent = lambda e, p=img.path: self._show_preview(p)
        card.thumb.setCursor(Qt.PointingHandCursor)
        
        # Tag label tooltip
        card.tag_label.setToolTip(
            f"Tags: {', '.join(img.tags)}\nCategory: {img.category}\nPath: {img.path}"
            f"\n\n💡 Drag to prompt | Double-click to preview")
        
        # Action buttons row 1: Select + Edit + Delete
        btn_row = QHBoxLayout()
        btn_row.setSpacing(2)
        
        _btn_base = "border: none; border-radius: 3px; font-size: 12px; font-weight: bold; padding: 0px;"
        
        # Select button
        select_btn = QPushButton("S")
        select_btn.setFixedSize(28, 20)
        select_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.GREEN}; color: #ffffff; {_btn_base} }}"
            f"QPushButton:hover {{ background: #B8F0B2; }}"
        )
        select_btn.setToolTip("Select this image")
        select_btn.clicked.connect(lambda _, t=tag_text: self._on_image_select(t))
        btn_row.addWidget(select_btn)
        
        # Edit tags button
        edit_btn = QPushButton("E")
        edit_btn.setFixedSize(28, 20)
        edit_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.BLUE}; color: #ffffff; {_btn_base} }}"
            f"QPushButton:hover {{ background: #89B4FA; }}"
        )
        edit_btn.setToolTip("Edit tags / Move category")
        edit_btn.clicked.connect(lambda _, iid=img.id, itags=img.tags, icat=img.category: self._on_edit_image(iid, itags, icat))
        btn_row.addWidget(edit_btn)
        
        # Delete button
        del_btn = QPushButton("X")
        del_btn.setFixedSize(28, 20)
        del_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.RED}; color: #ffffff; {_btn_base} }}"
            f"QPushButton:hover {{ background: #EBA0AC; }}"
        )
        del_btn.setToolTip("Delete from library")
        del_btn.clicked.connect(lambda _, iid=img.id: self._on_delete_image(iid))
        btn_row.addWidget(del_btn)
        
        card.card_layout.addLayout(btn_row)
        
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
        self._add_files_to_library(files)
    
    def _add_files_to_library(self, files):
        """Add image files to library — per-image tag popup with preview."""
        if not files or not self._library:
            return
        IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff'}
        valid_files = [f for f in files if Path(f).suffix.lower() in IMAGE_EXTS]
        if not valid_files:
            return
        
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
            QScrollArea, QDialogButtonBox, QFrame,
        )
        from PySide6.QtGui import QPixmap
        
        cat = self._selected_category if self._selected_category != "All" else "All"
        
        # Build per-image tag dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"🖼️ Add {len(valid_files)} Image(s) to Library")
        dialog.setMinimumWidth(480)
        dialog.setMaximumHeight(600)
        dialog.setStyleSheet(f"background-color: {Theme.BASE}; color: {Theme.TEXT};")
        
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.setContentsMargins(16, 12, 16, 12)
        dlg_layout.setSpacing(8)
        
        # Header
        header = QLabel(f"Set tags for each image  ·  Category: {cat}")
        header.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 12px;")
        dlg_layout.addWidget(header)
        
        # Scrollable list of image rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {Theme.SURFACE0}; border-radius: 8px; border: none; }}"
        )
        container = QWidget()
        rows_layout = QVBoxLayout(container)
        rows_layout.setContentsMargins(8, 8, 8, 8)
        rows_layout.setSpacing(10)
        
        tag_inputs = []  # parallel list of QLineEdit
        
        for f in valid_files:
            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ background: {Theme.SURFACE1}; border-radius: 6px; "
                f"border: 1px solid {Theme.SURFACE2}; }}"
            )
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(8, 8, 8, 8)
            row_lay.setSpacing(10)
            
            # Thumbnail
            thumb = QLabel()
            thumb.setFixedSize(80, 80)
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet("border: none; background: transparent;")
            pix = QPixmap(f)
            if not pix.isNull():
                thumb.setPixmap(pix.scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("🖼️")
            row_lay.addWidget(thumb)
            
            # Info + tag input column
            info_col = QVBoxLayout()
            info_col.setSpacing(4)
            
            fname = QLabel(Path(f).name)
            fname.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px; font-weight: bold; border: none;")
            fname.setWordWrap(True)
            info_col.addWidget(fname)
            
            tag_edit = QLineEdit(Path(f).stem)
            tag_edit.setMinimumHeight(28)
            tag_edit.setPlaceholderText("tag1, tag2, tag3")
            tag_edit.setStyleSheet(
                f"background: {Theme.SURFACE0}; color: {Theme.TEXT}; "
                f"border: 1px solid {Theme.SURFACE2}; border-radius: 4px; padding: 2px 6px;"
            )
            info_col.addWidget(tag_edit)
            tag_inputs.append(tag_edit)
            
            row_lay.addLayout(info_col, stretch=1)
            rows_layout.addWidget(row)
        
        scroll.setWidget(container)
        dlg_layout.addWidget(scroll, stretch=1)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)
        
        # Focus first tag input
        if tag_inputs:
            tag_inputs[0].setFocus()
            tag_inputs[0].selectAll()
        
        if dialog.exec() == QDialog.Accepted:
            for f, tag_edit in zip(valid_files, tag_inputs):
                raw = tag_edit.text().strip()
                tags = [t.strip() for t in raw.split(",") if t.strip()] if raw else [Path(f).stem]
                self._library.add_image(f, tags=tags, category=cat)
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
    
    def _on_edit_image(self, image_id: str, current_tags: list, current_cat: str):
        """Edit tags and category for an image."""
        from PySide6.QtWidgets import QInputDialog, QDialog, QDialogButtonBox, QComboBox
        
        # Create a small edit dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("✏️ Edit Image")
        dialog.setFixedSize(350, 180)
        dialog.setStyleSheet(f"background-color: {Theme.BASE}; color: {Theme.TEXT};")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        # Tags input
        tag_label = QLabel("Tags (comma separated):")
        tag_label.setStyleSheet(f"color: {Theme.TEXT};")
        layout.addWidget(tag_label)
        
        tag_input = QLineEdit(", ".join(current_tags))
        tag_input.setMinimumHeight(32)
        layout.addWidget(tag_input)
        
        # Category combo
        cat_label = QLabel("Category:")
        cat_label.setStyleSheet(f"color: {Theme.TEXT};")
        layout.addWidget(cat_label)
        
        cat_combo = QComboBox()
        cat_combo.setStyleSheet(f"background-color: {Theme.SURFACE1}; color: {Theme.TEXT};")
        if self._library:
            for cat in self._library.get_categories():
                cat_combo.addItem(cat)
            idx = cat_combo.findText(current_cat)
            if idx >= 0:
                cat_combo.setCurrentIndex(idx)
        layout.addWidget(cat_combo)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.Accepted and self._library:
            # Update tags
            new_tags = [t.strip() for t in tag_input.text().split(",") if t.strip()]
            if new_tags:
                self._library.update_image_tags(image_id, new_tags)
            # Update category
            new_cat = cat_combo.currentText()
            if new_cat != current_cat:
                self._library.update_image_category(image_id, new_cat)
            self._reload_grid()
    
    def _show_preview(self, image_path: str):
        """Show full-size image preview dialog."""
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QDialog
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"🖼️ {Path(image_path).name}")
        dialog.setStyleSheet(f"background-color: {Theme.CRUST};")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(4, 4, 4, 4)
        
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            # Scale to fit screen but max 800x600
            scaled = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label = QLabel()
            label.setPixmap(scaled)
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
            dialog.setFixedSize(scaled.width() + 8, scaled.height() + 8)
        else:
            label = QLabel("Cannot load image")
            label.setStyleSheet(f"color: {Theme.RED};")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
        
        dialog.exec()
    
    def _on_image_select(self, tag: str):
        """Handle image selection — insert [tag] in prompt without closing."""
        if self._on_select:
            self._on_select(tag)

    def _move_image_to_category(self, image_id: str, category: str):
        """Move a library image to another category (called by droppable category buttons)."""
        if self._library:
            self._library.update_image_category(image_id, category)
            self._reload_grid()


class _DroppableCategoryButton(QPushButton):
    """Category button that accepts drops from library image cards.
    
    Accepts internal library drags (MIME_LIBRARY_IMAGE_ID) to move images
    between categories. Shows green highlight on drag-over.
    """
    
    MIME_LIBRARY_IMAGE_ID = "application/x-veo-library-image-id"
    
    def __init__(self, text: str, category_name: str, popup: ImageManagerPopup):
        super().__init__(text)
        self._category_name = category_name
        self._popup = popup
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_LIBRARY_IMAGE_ID):
            event.acceptProposedAction()
            # Visual feedback: highlight
            self.setStyleSheet(self.styleSheet().replace(
                f"background-color: transparent",
                f"background-color: {Theme.GREEN}"
            ).replace(
                f"background-color: {Theme.SURFACE2}",
                f"background-color: {Theme.GREEN}"
            ))
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        # Restore original style — full reload is cheapest
        self._popup._rebuild_category_buttons()
    
    def dropEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_LIBRARY_IMAGE_ID):
            image_id = bytes(event.mimeData().data(self.MIME_LIBRARY_IMAGE_ID)).decode('utf-8')
            self._popup._move_image_to_category(image_id, self._category_name)
            event.acceptProposedAction()
        else:
            event.ignore()


class _DraggableImageCard(QFrame):
    """Image card that supports drag-out to prompt thumbnails and between categories."""
    
    # Custom MIME type for internal library drag (carries image_id)
    MIME_LIBRARY_IMAGE_ID = "application/x-veo-library-image-id"
    
    def __init__(self, image_path: str, tag_text: str, thumb_size: int = 100, image_id: str = ""):
        super().__init__()
        self._image_path = image_path
        self._tag_text = tag_text
        self._image_id = image_id
        self._drag_start_pos = None
        
        self.setFixedSize(thumb_size + 16, thumb_size + 50)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE1};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
            }}
            QFrame:hover {{
                border-color: {Theme.BLUE};
            }}
        """)
        self.setCursor(Qt.PointingHandCursor)
        
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(4, 4, 4, 4)
        self.card_layout.setSpacing(2)
        
        # Thumbnail label
        self.thumb = QLabel()
        self.thumb.setFixedSize(thumb_size, thumb_size)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("border: none; background: transparent;")
        self.card_layout.addWidget(self.thumb)
        
        # Tag label
        self.tag_label = QLabel(tag_text)
        self.tag_label.setAlignment(Qt.AlignCenter)
        self.tag_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 10px; border: none;")
        self.tag_label.setWordWrap(False)
        self.card_layout.addWidget(self.tag_label)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton) or self._drag_start_pos is None:
            return
        
        # Check minimum drag distance
        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        from PySide6.QtWidgets import QApplication
        if distance < QApplication.startDragDistance():
            return
        
        from PySide6.QtGui import QDrag, QPixmap
        from PySide6.QtCore import QMimeData, QUrl
        
        drag = QDrag(self)
        mime = QMimeData()
        
        # Set file URL so ImageSlotWidget can accept it
        mime.setUrls([QUrl.fromLocalFile(self._image_path)])
        mime.setText(self._tag_text)
        # Include library image ID for internal category drag
        if self._image_id:
            mime.setData(self.MIME_LIBRARY_IMAGE_ID, self._image_id.encode('utf-8'))
        drag.setMimeData(mime)
        
        # Create drag pixmap from thumbnail
        if self.thumb.pixmap() and not self.thumb.pixmap().isNull():
            drag.setPixmap(self.thumb.pixmap().scaled(
                64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        drag.exec(Qt.CopyAction | Qt.MoveAction)
        self._drag_start_pos = None


class _DroppableGridWidget(QWidget):
    """Grid widget that accepts image drops from Explorer."""
    
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff'}
    
    def __init__(self, popup: ImageManagerPopup):
        super().__init__()
        self._popup = popup
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = Path(url.toLocalFile()).suffix.lower()
                    if ext in self.IMAGE_EXTS:
                        event.acceptProposedAction()
                        return
        event.ignore()
    
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    files.append(url.toLocalFile())
            if files:
                self._popup._add_files_to_library(files)
                event.acceptProposedAction()
                return
        event.ignore()


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
