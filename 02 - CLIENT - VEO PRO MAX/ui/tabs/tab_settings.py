"""
VEO Pro Max - Tab 07: Settings - PySide6 Version

Reference: TAB_07_SETTINGS.md
Migrated from CustomTkinter to PySide6 - EXACT MATCH to CTK version.
"""

from typing import Optional, List
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QComboBox, QLineEdit, QCheckBox,
    QRadioButton, QButtonGroup, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt, Signal, Slot

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from core.profiles_controller import ProfilesController


class ToggleSwitch(QPushButton):
    """Custom toggle switch widget styled as a slide button."""
    
    toggled_signal = Signal(bool)  # Emitted when toggle state changes
    
    def __init__(self, checked: bool = True, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._checked = checked
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(56, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        self.clicked.connect(self._on_clicked)
    
    def _on_clicked(self):
        """Handle click - toggle state."""
        self._checked = self.isChecked()
        self._update_style()
        self.toggled_signal.emit(self._checked)
    
    def _update_style(self):
        """Update visual style based on state."""
        if self._checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.GREEN};
                    border-radius: 13px;
                    border: none;
                    color: white;
                    font-size: 11px;
                    font-weight: bold;
                    text-align: right;
                    padding-right: 8px;
                }}
            """)
            self.setText("ON")
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.OVERLAY0};
                    border-radius: 13px;
                    border: none;
                    color: #aaa;
                    font-size: 11px;
                    font-weight: bold;
                    text-align: left;
                    padding-left: 8px;
                }}
            """)
            self.setText("OFF")
    
    def isToggled(self) -> bool:
        """Get current toggle state."""
        return self._checked
    
    def setToggled(self, checked: bool):
        """Set toggle state programmatically."""
        self._checked = checked
        self.setChecked(checked)
        self._update_style()


class TabSettings(QWidget):
    """Settings tab (PySide6).
    
    Layout (matches CTK exactly):
    - Chrome Profiles section
    - Default Settings section
    - Output Settings section
    - Browser Settings section
    - Continuation Frame Extraction section
    - UI section
    - Action buttons
    """
    
    # Signals
    settings_changed = Signal(dict)
    
    def __init__(self, parent: Optional[QWidget] = None, controller=None):
        super().__init__(parent)
        self.controller = controller
        
        # Initialize ProfilesController for Chrome profiles management
        self.profiles_controller = ProfilesController()
        self.profiles_controller.set_callbacks(
            on_profiles_changed=self._refresh_profiles_table
        )
        
        # Issue E: Bridge ProfilesController → AppController for startup sync
        if self.controller and hasattr(self.controller, 'set_profiles_controller'):
            self.controller.set_profiles_controller(self.profiles_controller)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup main layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"background-color: {Theme.BASE};")
        
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setSpacing(16)
        
        # === CHROME PROFILES SECTION ===
        profiles_section = self._create_profiles_section()
        self.content_layout.addWidget(profiles_section)
        
        # === CONTINUATION FRAME SECTION ===
        cont_section = self._create_continuation_section()
        self.content_layout.addWidget(cont_section)
        
        # === WORKER SETTINGS SECTION ===
        worker_section = self._create_worker_section()
        self.content_layout.addWidget(worker_section)
        
        # === UI SECTION ===
        ui_section = self._create_ui_section()
        self.content_layout.addWidget(ui_section)
        
        self.content_layout.addStretch()
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
    
    def _create_section(self, title: str) -> tuple:
        """Create a section frame with header."""
        section = QFrame()
        section.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setFixedHeight(32)
        header.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        layout.addWidget(header)
        
        # Content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 8, 12, 0)
        content_layout.setSpacing(4)
        layout.addWidget(content)
        
        return section, content_layout
    
    def _create_enable_row(
        self, label_text: str, checked: bool = True,
        bold: bool = False, color: str = "", badge: str = ""
    ) -> ToggleSwitch:
        """Create a standard enable/disable row with label + ToggleSwitch.
        
        Returns the ToggleSwitch widget for signal connections.
        Layout: [Label 150px] [ToggleSwitch 56x26] [badge?] [stretch]
        
        Args:
            bold: Make label bold (for sub-feature headers)
            color: Override label color (e.g. Theme.YELLOW)
            badge: Optional badge text after toggle (e.g. "BETA")
        """
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setFixedWidth(150)
        style_parts = [f"color: {color or Theme.TEXT}"]
        if bold:
            style_parts.append("font-weight: bold")
        label.setStyleSheet("; ".join(style_parts) + ";")
        row.addWidget(label)
        
        toggle = ToggleSwitch(checked=checked)
        row.addWidget(toggle)
        
        if badge:
            badge_label = QLabel(badge)
            badge_label.setStyleSheet(
                f"color: {Theme.BASE}; background-color: {Theme.YELLOW};"
                f" font-size: 9px; font-weight: bold; padding: 1px 6px;"
                f" border-radius: 3px;"
            )
            row.addWidget(badge_label)
        
        row.addStretch()
        
        # Store layout reference for caller
        toggle._row_layout = row
        return toggle
    
    def _create_profiles_section(self) -> QWidget:
        """Create Chrome Profiles section - per TAB_07_SETTINGS.md spec.
        
        9 columns: ✓, #, Email, Type, Plan, Credits, Status, Slots, Actions
        """
        section, layout = self._create_section("🌐 Chrome Profiles (Account Manager)")
        
        # Create QTableWidget with 9 columns (added Slots column)
        self.profiles_table = QTableWidget()
        self.profiles_table.setColumnCount(9)
        self.profiles_table.setHorizontalHeaderLabels([
            "✓", "#", "Email", "Type", "Plan", "Credits", "Status", "Slots", "Actions"
        ])
        
        # Set column widths per docs spec
        header = self.profiles_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # ✓
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # #
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Email
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Type
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)  # Plan
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Credits
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)  # Status
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)  # Slots
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)  # Actions
        
        self.profiles_table.setColumnWidth(0, 80)   # ✓
        self.profiles_table.setColumnWidth(1, 40)   # #
        self.profiles_table.setColumnWidth(3, 80)   # Type - emoji only
        self.profiles_table.setColumnWidth(4, 80)   # Plan
        self.profiles_table.setColumnWidth(5, 80)   # Credits
        self.profiles_table.setColumnWidth(6, 110)  # Status - "🟢 Ready" needs more space
        self.profiles_table.setColumnWidth(7, 60)   # Slots - SpinBox 0-4
        self.profiles_table.setColumnWidth(8, 120)  # Actions - 3 buttons + spacing
        
        self.profiles_table.setMinimumHeight(80)
        self.profiles_table.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        self.profiles_table.setAlternatingRowColors(True)
        
        # Set default row height for better visibility
        self.profiles_table.verticalHeader().setDefaultSectionSize(48)
        self.profiles_table.verticalHeader().setVisible(False)  # Hide row numbers
        
        # Load profiles from controller
        self._refresh_profiles_table()
        
        layout.addWidget(self.profiles_table)
        
        # Login button - Browser login only
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # Browser login - full session with real-time subscription
        browser_btn = QPushButton("🌐 Add Account")
        browser_btn.setToolTip("Login in browser. Plan/Credits available immediately.")
        browser_btn.setFixedHeight(28)
        browser_btn.setStyleSheet(f"background-color: {Theme.GREEN}; font-size: 12px; padding: 2px 12px;")
        browser_btn.clicked.connect(self._on_add_profile_browser)
        btn_layout.addWidget(browser_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return section
    
    def _update_row_status(self, email: str, status: str, credits: str = None):
        """Update status and optionally credits for a specific row by email.
        
        Used to show loading states like '⏳ Refreshing...' during async operations.
        
        Args:
            email: Account email to find row
            status: New status text (e.g., '⏳ Refreshing...', '🟢 Ready')
            credits: Optional new credits text (e.g., '...' during loading)
        """
        for row in range(self.profiles_table.rowCount()):
            email_item = self.profiles_table.item(row, 2)  # Email is col 2
            if email_item and email_item.text() == email:
                # Update Status (col 6)
                status_item = self.profiles_table.item(row, 6)
                if status_item:
                    status_item.setText(status)
                
                # Update Credits if provided (col 5)
                if credits is not None:
                    credits_item = self.profiles_table.item(row, 5)
                    if credits_item:
                        credits_item.setText(credits)
                
                # Update Plan to show loading (col 4)
                if credits is not None:
                    plan_item = self.profiles_table.item(row, 4)
                    if plan_item:
                        plan_item.setText("⏳ Wait")
                
                break
    
    @Slot()
    def _refresh_profiles_table(self):
        """Refresh profiles table from controller data."""
        self.profiles_table.setRowCount(0)
        
        # Get profiles from ProfilesController
        accounts = self.profiles_controller.get_all_profiles()
        
        # If no profiles exist, show empty state message
        if not accounts:
            placeholder = QTableWidgetItem("No profiles added. Click '🌐 Add Account' to add.")
            self.profiles_table.insertRow(0)
            self.profiles_table.setSpan(0, 0, 1, 9)  # 9 columns now
            self.profiles_table.setItem(0, 0, placeholder)
            self._adjust_table_height(1)
            return
        
        for i, acc in enumerate(accounts):
            self.profiles_table.insertRow(i)
            
            # Toggle switch (col 0) - Enable/Disable account for rotation
            is_enabled = acc.get('is_enabled', True)
            toggle = ToggleSwitch(checked=is_enabled)
            toggle.setToolTip("Toggle ON/OFF to enable/disable account for generation")
            email_for_toggle = acc.get('email', '')
            toggle.toggled_signal.connect(
                lambda checked, e=email_for_toggle: self._on_toggle_account(e, checked)
            )
            self.profiles_table.setCellWidget(i, 0, toggle)
            
            # # row number (col 1) - centered
            row_item = QTableWidgetItem(str(i + 1))
            row_item.setFlags(row_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            row_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(i, 1, row_item)
            
            # Email (col 2) — with credential status icon
            email_text = acc.get('email', 'Unknown')
            try:
                from core.credentials_manager import get_credentials_manager
                has_creds = get_credentials_manager().has_credentials_for(email_text)
                cred_icon = "🔑" if has_creds else "🔓"
                cred_tip = "Stored credentials available (auto re-login ready)" if has_creds else "No stored credentials"
            except Exception:
                cred_icon = ""
                cred_tip = ""
            email_item = QTableWidgetItem(f"{cred_icon} {email_text}")
            email_item.setToolTip(cred_tip)
            email_item.setFlags(email_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.profiles_table.setItem(i, 2, email_item)
            
            # Type (col 3) - Clickable 🌐 button to open debug browser
            type_btn = QPushButton("🌐")
            type_btn.setToolTip("Click to open browser with this profile for debugging")
            type_btn.setFixedSize(40, 30)
            type_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.SURFACE2};
                    border: 1px solid {Theme.OVERLAY0};
                    border-radius: 4px;
                    font-size: 16px;
                    cursor: pointer;
                }}
                QPushButton:hover {{
                    background-color: {Theme.BLUE};
                    border-color: {Theme.BLUE};
                }}
            """)
            email_for_browser = acc.get('email', '')
            type_btn.clicked.connect(
                lambda checked, e=email_for_browser: self._on_open_debug_browser(e)
            )
            self.profiles_table.setCellWidget(i, 3, type_btn)
            
            # Plan (col 4) - tier_display already formatted - centered
            plan_item = QTableWidgetItem(acc.get('tier', '👤 Free'))
            plan_item.setFlags(plan_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            plan_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(i, 4, plan_item)
            
            # Credits (col 5) - credits_display already formatted - centered
            credits_item = QTableWidgetItem(acc.get('credits', 'N/A'))
            credits_item.setFlags(credits_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            credits_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(i, 5, credits_item)
            
            # Status (col 6) - Uses enhanced status_display from ChromeProfile - centered
            # Status values: 🔴 Expired, 🟠 Expiring, 🟡 Login, 🟢 Ready
            status = acc.get('status', '🟡 Login')
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(i, 6, status_item)
            
            # Get email for action handlers
            email = acc.get('email', '')
            
            # Slots SpinBox (col 7) — per-account concurrent worker limit
            slots_spin = QSpinBox()
            slots_spin.setRange(0, 4)
            slots_spin.setValue(acc.get('max_slots', 4))
            slots_spin.setToolTip("Max concurrent workers for this account (0 = disabled)")
            slots_spin.setFixedWidth(50)
            slots_spin.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 2px; text-align: center;")
            slots_spin.valueChanged.connect(
                lambda value, e=email: self._on_slots_changed(e, value)
            )
            self.profiles_table.setCellWidget(i, 7, slots_spin)
            
            # Actions buttons (col 8)
            actions_widget = QWidget()
            actions_widget.setStyleSheet("background: transparent;")
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(3)
            
            style = self.style()
            
            # Refresh button - refresh session via browser
            refresh_btn = QPushButton()
            refresh_btn.setIcon(style.standardIcon(style.StandardPixmap.SP_BrowserReload))
            refresh_btn.setFixedSize(26, 26)
            refresh_btn.setToolTip("Refresh Session")
            refresh_btn.setStyleSheet(f"background-color: {Theme.BLUE}; border-radius: 4px;")
            refresh_btn.clicked.connect(lambda checked, e=email: self._on_refresh_session(e))
            actions_layout.addWidget(refresh_btn)
            
            # Delete button - remove profile
            delete_btn = QPushButton()
            delete_btn.setIcon(style.standardIcon(style.StandardPixmap.SP_TrashIcon))
            delete_btn.setFixedSize(26, 26)
            delete_btn.setToolTip("Delete Profile")
            delete_btn.setStyleSheet(f"background-color: {Theme.RED}; border-radius: 4px;")
            delete_btn.clicked.connect(lambda checked, e=email: self._on_delete_profile(e))
            actions_layout.addWidget(delete_btn)
            
            self.profiles_table.setCellWidget(i, 8, actions_widget)
        
        # Auto-expand table height to fit all rows
        self._adjust_table_height(len(accounts))
    
    def _adjust_table_height(self, row_count: int):
        """Adjust table height to show all rows without scrolling (max 10 rows)."""
        row_height = self.profiles_table.verticalHeader().defaultSectionSize()
        header_height = self.profiles_table.horizontalHeader().height()
        visible_rows = min(row_count, 10)  # Cap at 10 rows visible
        # +2 for borders/padding
        total_height = header_height + (row_height * visible_rows) + 2
        self.profiles_table.setFixedHeight(max(total_height, 80))
    
    def _create_profile_row(self, name: str, status: str, last_used: str) -> QWidget:
        """Create a profile row - matches CTK _create_profile_row."""
        row = QFrame()
        row.setStyleSheet(f"background-color: {Theme.SURFACE2}; border-radius: 4px;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        
        name_label = QLabel(name)
        name_label.setFixedWidth(150)
        name_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        layout.addWidget(name_label)
        
        status_label = QLabel(status)
        status_label.setFixedWidth(100)
        layout.addWidget(status_label)
        
        last_label = QLabel(last_used)
        last_label.setFixedWidth(120)
        last_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        layout.addWidget(last_label)
        
        layout.addStretch()
        
        edit_btn = QPushButton("✏️")
        edit_btn.setFixedSize(28, 28)
        layout.addWidget(edit_btn)
        
        delete_btn = QPushButton("🗑️")
        delete_btn.setFixedSize(28, 28)
        layout.addWidget(delete_btn)
        
        return row
    
    def _create_accounts_section(self) -> QWidget:
        """Create Google Accounts management section."""
        section, layout = self._create_section("👥 Google Accounts")
        
        # Description
        desc = QLabel("Manage accounts for parallel generation (4 slots each)")
        desc.setStyleSheet(f"color: {Theme.SUBTEXT0}; margin-bottom: 8px;")
        layout.addWidget(desc)
        
        # Accounts list container
        self.accounts_list = QVBoxLayout()
        self.accounts_list.setSpacing(4)
        layout.addLayout(self.accounts_list)
        
        # Load existing accounts
        self._refresh_accounts()
        
        # Add account row
        add_row = QHBoxLayout()
        self.account_email_input = QLineEdit()
        self.account_email_input.setPlaceholderText("Enter Google email...")
        self.account_email_input.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 6px;")
        add_row.addWidget(self.account_email_input, stretch=1)
        
        add_btn = QPushButton("➕ Add")
        add_btn.setStyleSheet(f"background-color: {Theme.BLUE}; padding: 6px 12px;")
        add_btn.clicked.connect(self._on_add_account)
        add_row.addWidget(add_btn)
        
        layout.addLayout(add_row)
        
        return section
    
    def _refresh_accounts(self):
        """Refresh accounts list from controller."""
        # Clear existing
        while self.accounts_list.count():
            item = self.accounts_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if self.controller and hasattr(self.controller, 'get_accounts'):
            for acc in self.controller.get_accounts():
                row = self._create_account_row(acc)
                self.accounts_list.addWidget(row)
    
    def _create_account_row(self, acc: dict) -> QWidget:
        """Create account row widget."""
        row = QFrame()
        row.setStyleSheet(f"background-color: {Theme.SURFACE2}; border-radius: 4px;")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        
        email = acc.get('email', 'Unknown')
        email_label = QLabel(f"📧 {email}")
        email_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        layout.addWidget(email_label, stretch=1)
        
        slots = acc.get('slots', '0/4')
        slots_label = QLabel(f"Slots: {slots}")
        slots_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        layout.addWidget(slots_label)
        
        is_ready = acc.get('is_ready', False)
        status_text = "● Ready" if is_ready else "○ Not Ready"
        status_color = Theme.GREEN if is_ready else Theme.RED
        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"color: {status_color}; margin: 0 8px;")
        layout.addWidget(status_label)
        
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet(f"color: {Theme.RED}; border: 1px solid {Theme.RED}; border-radius: 12px;")
        remove_btn.clicked.connect(lambda: self._on_remove_account(email))
        layout.addWidget(remove_btn)
        
        return row
    
    def _on_add_account(self):
        """Add new account via simplified path.
        
        Note: This is a convenience shortcut. The primary way to add accounts
        is through Browser login in the profiles table, which sets
        up proper tokens and browser sessions.
        
        This path only creates a placeholder profile that needs login afterward.
        """
        email = self.account_email_input.text().strip()
        if not email or '@' not in email:
            return
        
        # Add as a profile placeholder (needs login later)
        if self.profiles_controller:
            success = self.profiles_controller.add_profile(
                email=email,
                profile_path="",
                display_name=email.split("@")[0],
                is_ready=False,
            )
            if success:
                self.account_email_input.clear()
                self._refresh_profiles_table()
                print(f"[Settings] Profile added: {email} (needs login)")
            else:
                print(f"[Settings] Profile already exists: {email}")
    
    def _on_remove_account(self, email: str):
        """Remove account."""
        if self.controller and hasattr(self.controller, 'remove_account'):
            self.controller.remove_account(email)
            self._refresh_accounts()
    
    def _create_defaults_section(self) -> QWidget:
        """Create Default Settings section - matches CTK lines 94-106."""
        section, layout = self._create_section("⚙️ Default Settings")
        
        # Settings - EXACT from CTK lines 98-103
        settings = [
            ("Aspect Ratio", ["16:9 (Landscape)", "9:16 (Portrait)"]),
            ("Download Quality", ["720p", "1080p", "4K"]),
            ("AI Model", ["Veo 3.1 - Fast", "Veo 3.1 - Quality", "Veo 2 - Fast"]),
            ("Outputs per Prompt", ["1", "2", "3", "4"]),
        ]
        
        self.setting_combos = {}
        for label, options in settings:
            combo = self._create_setting_row(layout, label, options)
            self.setting_combos[label] = combo
        
        return section
    
    def _create_output_section(self) -> QWidget:
        """Create Output Settings section - matches CTK lines 108-170."""
        section, layout = self._create_section("📁 Output Settings")
        
        # Default output folder
        folder_layout = QHBoxLayout()
        
        folder_label = QLabel("Default Output Folder:")
        folder_label.setFixedWidth(150)
        folder_label.setStyleSheet(f"color: {Theme.TEXT};")
        folder_layout.addWidget(folder_label)
        
        self.output_folder_entry = QLineEdit()
        self.output_folder_entry.setPlaceholderText("D:/Projects/VEO")
        self.output_folder_entry.setMinimumWidth(300)
        folder_layout.addWidget(self.output_folder_entry)
        
        browse_btn = QPushButton("📂")
        browse_btn.setFixedSize(32, 32)
        browse_btn.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        folder_layout.addWidget(browse_btn)
        folder_layout.addStretch()
        
        layout.addLayout(folder_layout)
        
        # Toggles - EXACT from CTK lines 142-147
        toggles = [
            ("Include timestamp in filename", True),
            ("Include quality in filename", True),
            ("Auto-start queue when adding", False),
            ("Pause on error", True),
        ]
        
        self.output_toggles = {}
        for label, default in toggles:
            checkbox = QCheckBox(label)
            checkbox.setChecked(default)
            checkbox.setStyleSheet(f"color: {Theme.TEXT};")
            layout.addWidget(checkbox)
            self.output_toggles[label] = checkbox
        
        return section
    
    def _create_browser_section(self) -> QWidget:
        """Create Browser Settings section - matches CTK lines 172-202."""
        section, layout = self._create_section("🌐 Browser Settings")
        
        # Toggles - EXACT from CTK lines 176-180
        toggles = [
            ("Headless mode", False),
            ("Use persistent profile", True),
            ("Enable auto-retry on failure", True),
        ]
        
        self.browser_toggles = {}
        for label, default in toggles:
            checkbox = QCheckBox(label)
            checkbox.setChecked(default)
            checkbox.setStyleSheet(f"color: {Theme.TEXT};")
            layout.addWidget(checkbox)
            self.browser_toggles[label] = checkbox
        
        return section
    
    def _create_continuation_section(self) -> QWidget:
        """Create Continuation Frame section."""
        section, layout = self._create_section("🔗 Continuation Frame Extraction")
        
        # Enable toggle
        self.cont_switch = self._create_enable_row("Enable Continuation:", checked=True)
        layout.addLayout(self.cont_switch._row_layout)
        
        # Extract Point
        extract_layout = QHBoxLayout()
        extract_label = QLabel("Extract Point:")
        extract_label.setFixedWidth(150)
        extract_label.setStyleSheet(f"color: {Theme.TEXT};")
        extract_layout.addWidget(extract_label)
        
        self.extract_menu = QComboBox()
        self.extract_menu.addItems(["500ms", "750ms (recommended)", "1000ms", "Custom"])
        self.extract_menu.setCurrentText("750ms (recommended)")
        self.extract_menu.setFixedWidth(200)
        extract_layout.addWidget(self.extract_menu)
        
        suffix_label = QLabel("before video end")
        suffix_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        extract_layout.addWidget(suffix_label)
        extract_layout.addStretch()
        layout.addLayout(extract_layout)
        
        # === ✨ Enhancer Image — BETA sub-feature ===
        self.enhancer_switch = self._create_enable_row(
            "✨ Enhancer Image (beta):", checked=False,
            bold=True, color=Theme.PURPLE
        )
        layout.addLayout(self.enhancer_switch._row_layout)
        
        # Collapsible settings for Enhancer
        self.enhancer_container = QWidget()
        enhancer_layout = QVBoxLayout(self.enhancer_container)
        enhancer_layout.setContentsMargins(0, 0, 0, 0)
        
        # Quality
        quality_row = QHBoxLayout()
        quality_label = QLabel("Quality:")
        quality_label.setFixedWidth(150)
        quality_label.setStyleSheet(f"color: {Theme.TEXT};")
        quality_row.addWidget(quality_label)
        
        self.enhancer_quality = QComboBox()
        self.enhancer_quality.addItems(["Low (fast)", "Medium", "High (slow)"])
        self.enhancer_quality.setCurrentText("Medium")
        self.enhancer_quality.setFixedWidth(200)
        quality_row.addWidget(self.enhancer_quality)
        quality_row.addStretch()
        enhancer_layout.addLayout(quality_row)
        
        # Scale
        scale_row = QHBoxLayout()
        scale_label = QLabel("Upscale:")
        scale_label.setFixedWidth(150)
        scale_label.setStyleSheet(f"color: {Theme.TEXT};")
        scale_row.addWidget(scale_label)
        
        self.enhancer_scale = QComboBox()
        self.enhancer_scale.addItems(["1x (enhance only)", "2x", "4x"])
        self.enhancer_scale.setCurrentText("1x (enhance only)")
        self.enhancer_scale.setFixedWidth(200)
        scale_row.addWidget(self.enhancer_scale)
        scale_row.addStretch()
        enhancer_layout.addLayout(scale_row)
        
        layout.addWidget(self.enhancer_container)
        
        # Toggle visibility
        self.enhancer_container.setVisible(self.enhancer_switch.isToggled())
        self.enhancer_switch.toggled_signal.connect(self.enhancer_container.setVisible)
        
        return section
    
    def _create_worker_section(self) -> QWidget:
        """Create Worker Settings section per TAB_07_SETTINGS.md spec."""
        section, layout = self._create_section("🎯 Worker Settings")
        
        # Load saved values from controller if available
        saved = {}
        if self.controller and hasattr(self.controller, 'settings') and self.controller.settings:
            s = self.controller.settings
            saved = {
                'retry_count': getattr(s, 'retry_count', 3),
                'request_timeout': getattr(s, 'request_timeout', 120),
                'anti_detect_enabled': getattr(s, 'anti_detect_enabled', True),
                'anti_detect_delay_min': getattr(s, 'anti_detect_delay_min', 1.0),
                'anti_detect_delay_max': getattr(s, 'anti_detect_delay_max', 5.0),
            }
        
        # Note: Max Concurrent Workers removed — now per-account via Chrome Profiles
        
        # Retry on Error (default for new accounts)
        retry_row = QHBoxLayout()
        retry_label = QLabel("Retry on Error:")
        retry_label.setFixedWidth(150)
        retry_label.setStyleSheet(f"color: {Theme.TEXT};")
        retry_row.addWidget(retry_label)
        
        self.retry_count = QSpinBox()
        self.retry_count.setRange(0, 5)
        self.retry_count.setValue(saved.get('retry_count', 3))
        self.retry_count.setFixedWidth(80)
        self.retry_count.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        retry_row.addWidget(self.retry_count)
        retry_row.addStretch()
        layout.addLayout(retry_row)
        
        # Request Timeout
        timeout_row = QHBoxLayout()
        timeout_label = QLabel("Request Timeout (s):")
        timeout_label.setFixedWidth(150)
        timeout_label.setStyleSheet(f"color: {Theme.TEXT};")
        timeout_row.addWidget(timeout_label)
        
        self.request_timeout = QSpinBox()
        self.request_timeout.setRange(30, 300)
        self.request_timeout.setValue(saved.get('request_timeout', 120))
        self.request_timeout.setFixedWidth(80)
        self.request_timeout.setSuffix("s")
        self.request_timeout.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        timeout_row.addWidget(self.request_timeout)
        timeout_row.addStretch()
        layout.addLayout(timeout_row)
        
        # === Anti-Detect Spam — bold + emoji ===
        self.anti_detect_switch = self._create_enable_row(
            "🛡️ Anti-Detect Spam:", checked=saved.get('anti_detect_enabled', True),
            bold=True, color=Theme.YELLOW
        )
        layout.addLayout(self.anti_detect_switch._row_layout)
        
        # Collapsible container for delay settings
        self.anti_detect_container = QWidget()
        detect_layout = QVBoxLayout(self.anti_detect_container)
        detect_layout.setContentsMargins(0, 0, 0, 0)
        
        # Min Delay
        min_delay_row = QHBoxLayout()
        min_delay_label = QLabel("Min Delay (s):")
        min_delay_label.setFixedWidth(150)
        min_delay_label.setStyleSheet(f"color: {Theme.TEXT};")
        min_delay_row.addWidget(min_delay_label)
        
        self.anti_detect_delay_min = QDoubleSpinBox()
        self.anti_detect_delay_min.setRange(0.5, 10.0)
        self.anti_detect_delay_min.setSingleStep(0.1)
        self.anti_detect_delay_min.setDecimals(1)
        self.anti_detect_delay_min.setValue(saved.get('anti_detect_delay_min', 1.0))
        self.anti_detect_delay_min.setFixedWidth(80)
        self.anti_detect_delay_min.setSuffix("s")
        self.anti_detect_delay_min.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        min_delay_row.addWidget(self.anti_detect_delay_min)
        min_delay_row.addStretch()
        detect_layout.addLayout(min_delay_row)
        
        # Max Delay
        max_delay_row = QHBoxLayout()
        max_delay_label = QLabel("Max Delay (s):")
        max_delay_label.setFixedWidth(150)
        max_delay_label.setStyleSheet(f"color: {Theme.TEXT};")
        max_delay_row.addWidget(max_delay_label)
        
        self.anti_detect_delay_max = QDoubleSpinBox()
        self.anti_detect_delay_max.setRange(1.0, 30.0)
        self.anti_detect_delay_max.setSingleStep(0.1)
        self.anti_detect_delay_max.setDecimals(1)
        self.anti_detect_delay_max.setValue(saved.get('anti_detect_delay_max', 5.0))
        self.anti_detect_delay_max.setFixedWidth(80)
        self.anti_detect_delay_max.setSuffix("s")
        self.anti_detect_delay_max.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        max_delay_row.addWidget(self.anti_detect_delay_max)
        max_delay_row.addStretch()
        detect_layout.addLayout(max_delay_row)
        
        layout.addWidget(self.anti_detect_container)
        
        # Toggle visibility based on enable state
        self.anti_detect_container.setVisible(self.anti_detect_switch.isToggled())
        self.anti_detect_switch.toggled_signal.connect(self.anti_detect_container.setVisible)
        
        return section
    
    def _create_ui_section(self) -> QWidget:
        """Create UI section - matches CTK lines 301-355."""
        section, layout = self._create_section("🎨 UI")
        
        row_layout = QHBoxLayout()
        
        # Theme - CTK lines 308-333
        theme_label = QLabel("Theme:")
        theme_label.setStyleSheet(f"color: {Theme.TEXT};")
        row_layout.addWidget(theme_label)
        
        self.theme_group = QButtonGroup(self)
        
        dark_radio = QRadioButton("Dark")
        dark_radio.setChecked(True)
        dark_radio.setStyleSheet(f"color: {Theme.TEXT};")
        self.theme_group.addButton(dark_radio)
        row_layout.addWidget(dark_radio)
        
        light_radio = QRadioButton("Light")
        light_radio.setStyleSheet(f"color: {Theme.TEXT};")
        self.theme_group.addButton(light_radio)
        row_layout.addWidget(light_radio)
        
        # Separator
        sep = QFrame()
        sep.setFixedSize(1, 24)
        sep.setStyleSheet(f"background-color: {Theme.BORDER};")
        row_layout.addWidget(sep)
        
        # Language - CTK lines 338-355
        lang_label = QLabel("Language:")
        lang_label.setStyleSheet(f"color: {Theme.TEXT};")
        row_layout.addWidget(lang_label)
        
        self.lang_menu = QComboBox()
        self.lang_menu.addItems(["Tiếng Việt", "English"])
        self.lang_menu.setFixedWidth(120)
        row_layout.addWidget(self.lang_menu)
        
        # Separator 2
        sep2 = QFrame()
        sep2.setFixedSize(1, 24)
        sep2.setStyleSheet(f"background-color: {Theme.BORDER};")
        row_layout.addWidget(sep2)
        
        # Font Size - per TAB_07_SETTINGS.md spec
        font_label = QLabel("Font Size:")
        font_label.setStyleSheet(f"color: {Theme.TEXT};")
        row_layout.addWidget(font_label)
        
        self.font_size_menu = QComboBox()
        self.font_size_menu.addItems(["Small", "Medium", "Large"])
        self.font_size_menu.setCurrentIndex(1)  # Default to Medium
        self.font_size_menu.setFixedWidth(100)
        row_layout.addWidget(self.font_size_menu)
        
        row_layout.addStretch()
        layout.addLayout(row_layout)
        
        return section
    
    def _create_action_buttons(self) -> QWidget:
        """Create action buttons - matches CTK lines 357-401."""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 16, 0, 0)
        
        # Save button - green
        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet(f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; height: 36px;")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)
        
        # Reset Defaults button
        reset_btn = QPushButton("🔄 Reset Defaults")
        reset_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; height: 36px;")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)
        
        # Export Config button - blue
        export_btn = QPushButton("📤 Export Config")
        export_btn.setStyleSheet(f"background-color: {Theme.BLUE}; height: 36px;")
        export_btn.clicked.connect(self._on_export)
        layout.addWidget(export_btn)
        
        # Import Config button
        import_btn = QPushButton("📥 Import Config")
        import_btn.setStyleSheet(f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; height: 36px;")
        import_btn.clicked.connect(self._on_import)
        layout.addWidget(import_btn)
        
        layout.addStretch()
        
        return frame
    
    def _on_save(self):
        """Save settings and emit signal."""
        settings = self.get_settings()
        self.settings_changed.emit(settings)
    
    def _on_reset(self):
        """Reset to default values."""
        # Reset combos to first value
        for combo in self.setting_combos.values():
            combo.setCurrentIndex(0)
        # Reset toggles
        for toggle in self.output_toggles.values():
            toggle.setChecked(False)
        for toggle in self.browser_toggles.values():
            toggle.setChecked(False)
        # Reset worker spinboxes to defaults
        self.retry_count.setValue(3)
        self.request_timeout.setValue(120)
        # Reset anti-detect spam to defaults
        self.anti_detect_switch.setToggled(True)
        self.anti_detect_delay_min.setValue(1.0)
        self.anti_detect_delay_max.setValue(5.0)
        # Reset enhancer image to defaults
        self.enhancer_switch.setToggled(False)
        self.enhancer_quality.setCurrentText("Medium")
        self.enhancer_scale.setCurrentText("1x (enhance only)")
    
    def _on_export(self):
        """Export config to file."""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Config", "", "JSON Files (*.json)"
        )
        if file_path:
            import json
            settings = self.get_settings()
            with open(file_path, 'w') as f:
                json.dump(settings, f, indent=2)
    
    def _on_import(self):
        """Import config from file."""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Config", "", "JSON Files (*.json)"
        )
        if file_path:
            import json
            with open(file_path, 'r') as f:
                settings = json.load(f)
            # Apply settings to widgets
            self._apply_imported_settings(settings)
            self.settings_changed.emit(settings)
    
    def _apply_imported_settings(self, settings: dict):
        """Apply imported settings to UI widgets."""
        if "aspect_ratio" in settings and "Aspect Ratio" in self.setting_combos:
            self.setting_combos["Aspect Ratio"].setCurrentText(settings["aspect_ratio"])
        if "download_quality" in settings and "Download Quality" in self.setting_combos:
            self.setting_combos["Download Quality"].setCurrentText(settings["download_quality"])
        if "ai_model" in settings and "AI Model" in self.setting_combos:
            self.setting_combos["AI Model"].setCurrentText(settings["ai_model"])
        if "output_folder" in settings:
            self.output_folder_entry.setText(settings["output_folder"])
        # Worker settings
        if "retry_count" in settings:
            self.retry_count.setValue(int(settings["retry_count"]))
        if "request_timeout" in settings:
            self.request_timeout.setValue(int(settings["request_timeout"]))
        # Anti-Detect Spam
        if "anti_detect_enabled" in settings:
            self.anti_detect_switch.setToggled(bool(settings["anti_detect_enabled"]))
        if "anti_detect_delay_min" in settings:
            self.anti_detect_delay_min.setValue(float(settings["anti_detect_delay_min"]))
        if "anti_detect_delay_max" in settings:
            self.anti_detect_delay_max.setValue(float(settings["anti_detect_delay_max"]))
    
    def _create_setting_row(self, parent_layout, label: str, options: list) -> QComboBox:
        """Create a setting row with dropdown - matches CTK lines 443-465."""
        row_layout = QHBoxLayout()
        
        label_widget = QLabel(f"{label}:")
        label_widget.setFixedWidth(150)
        label_widget.setStyleSheet(f"color: {Theme.TEXT};")
        row_layout.addWidget(label_widget)
        
        combo = QComboBox()
        combo.addItems(options)
        combo.setFixedWidth(200)
        combo.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        row_layout.addWidget(combo)
        
        row_layout.addStretch()
        parent_layout.addLayout(row_layout)
        
        return combo
    
    def _on_open_debug_browser(self, email: str):
        """Open browser with saved profile for manual debugging."""
        import threading
        
        print(f"[Settings] Opening debug browser for {email}...")
        
        def open_browser():
            success = self.profiles_controller.open_browser_for_debug(email)
            if not success:
                from PySide6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self, "_on_debug_browser_failed",
                    Qt.ConnectionType.QueuedConnection
                )
        
        thread = threading.Thread(target=open_browser, daemon=True)
        thread.start()
    
    @Slot()
    def _on_debug_browser_failed(self):
        """Called when debug browser fails to open."""
        QMessageBox.warning(
            self, "Browser Error",
            "Failed to open debug browser.\n"
            "Profile may not have a browser session yet.\n"
            "Try 'Add Account' first."
        )
    
    def _on_add_profile(self):
        """Add new profile via browser login (same as _on_add_profile_browser)."""
        self._on_add_profile_browser()
    
    @Slot()
    def _on_oauth_complete(self):
        """Called when login completes successfully."""
        self.setEnabled(True)  # Re-enable tab
        self._refresh_profiles_table()
        QMessageBox.information(self, "Success", "✅ Profile added successfully!")
    
    @Slot()
    def _on_oauth_failed(self):
        """Called when login fails or is cancelled."""
        self.setEnabled(True)  # Re-enable tab
        self._refresh_profiles_table()
        QMessageBox.warning(self, "Login", "Login cancelled or failed.")
    
    def _on_add_profile_browser(self):
        """Auto-login with email/password credentials."""
        import threading
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox
        
        # Import credentials manager
        try:
            from core.credentials_manager import get_credentials_manager
            creds_manager = get_credentials_manager()
        except ImportError as e:
            QMessageBox.warning(self, "Error", f"Credentials manager not available: {e}")
            return
        
        # Check if credentials already exist
        existing_creds = creds_manager.load_credentials()
        
        # Create credentials dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("🔐 Auto Login")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        # Form layout for inputs
        form = QFormLayout()
        
        email_input = QLineEdit()
        email_input.setPlaceholderText("example@gmail.com")
        if existing_creds:
            email_input.setText(existing_creds.get("email", ""))
        
        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_input.setPlaceholderText("••••••••")
        if existing_creds:
            password_input.setText(existing_creds.get("password", ""))
        
        form.addRow("📧 Email:", email_input)
        form.addRow("🔑 Password:", password_input)
        
        layout.addLayout(form)
        
        # Info label
        from PySide6.QtWidgets import QLabel, QCheckBox
        info_label = QLabel(
            "⚠️ Credentials are encrypted and stored locally.\n"
            "Browser will open for Google login.\n"
            "You can interact with 2FA/CAPTCHA if needed."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Keep browser open checkbox
        keep_open_cb = QCheckBox("🔓 Keep browser open after login (for debugging)")
        keep_open_cb.setChecked(False)
        keep_open_cb.setToolTip(
            "When checked, the browser will NOT auto-close after login.\n"
            "Use this to manually inspect the browser session."
        )
        layout.addWidget(keep_open_cb)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        # Show dialog
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        email = email_input.text().strip()
        password = password_input.text()
        keep_browser_open = keep_open_cb.isChecked()
        
        if not email or not password:
            QMessageBox.warning(self, "Error", "Please enter both email and password.")
            return
        
        # Save credentials (encrypted)
        if not creds_manager.save_credentials(email, password):
            QMessageBox.warning(self, "Error", "Failed to save credentials.")
            return
        
        # Always show browser — login often needs 2FA/CAPTCHA interaction
        headless = False
        
        # Start auto-login
        self.setEnabled(False)
        
        def run_auto_login():
            """Run auto-login in background thread."""
            print(f"[Settings] Starting auto-login for {email} (headless={headless})...")
            try:
                result_email = self.profiles_controller.auto_login_with_credentials(
                    email=email,
                    password=password,
                    timeout_seconds=120,
                    headless=headless,
                    keep_browser_open=keep_browser_open
                )
                
                from PySide6.QtCore import QMetaObject, Qt
                
                if result_email:
                    print(f"[Settings] Auto-login successful: {result_email}")
                    QMetaObject.invokeMethod(
                        self, "_on_browser_login_complete",
                        Qt.ConnectionType.QueuedConnection
                    )
                else:
                    print("[Settings] Auto-login failed")
                    QMetaObject.invokeMethod(
                        self, "_on_browser_login_failed",
                        Qt.ConnectionType.QueuedConnection
                    )
            except Exception as e:
                print(f"[Settings] Auto-login error: {e}")
                from PySide6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self, "_on_browser_login_failed",
                    Qt.ConnectionType.QueuedConnection
                )
        
        thread = threading.Thread(target=run_auto_login, daemon=True)
        thread.start()
    
    @Slot()
    def _on_browser_login_complete(self):
        """Called when browser login completes successfully."""
        self.setEnabled(True)
        self._refresh_profiles_table()
        QMessageBox.information(
            self, 
            "Success", 
            "✅ Profile added via browser!\n\nPlan/Credits are now available."
        )
    
    @Slot()
    def _on_browser_login_failed(self):
        """Called when browser login fails or times out."""
        self.setEnabled(True)
        self._refresh_profiles_table()
        QMessageBox.warning(self, "Browser Login", "Login cancelled or timed out.")
    
    def _on_refresh_session(self, email: str):
        """Refresh session via browser — fetch subscription real-time."""
        import threading
        
        profile = self.profiles_controller.get_profile(email)
        if not profile:
            QMessageBox.warning(self, "Error", f"Profile not found: {email}")
            return
        
        print(f"[Settings] Refreshing session for: {email}")
        
        # Show loading state immediately on the row
        self._update_row_status(email, "⏳ Refreshing...", "...")
        self.setEnabled(False)
        
        def fetch_browser():
            print(f"[Settings] Fetching subscription via browser...")
            result = self.profiles_controller.fetch_subscription_info(email)
            
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            import json
            result_json = json.dumps(result)
            QMetaObject.invokeMethod(
                self, "_on_subscription_fetched",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, email),
                Q_ARG(str, result_json)
            )
        
        thread = threading.Thread(target=fetch_browser, daemon=True)
        thread.start()
    
    @Slot(str, str)
    def _on_subscription_fetched(self, email: str, result_json: str):
        """Called when subscription fetch completes (from background thread).
        
        Shows notification dialog with specific failure reason and auto-login option.
        """
        import json
        result = json.loads(result_json)
        
        self.setEnabled(True)  # Re-enable tab
        self._refresh_profiles_table()
        
        success = result.get("success", False)
        reason = result.get("reason", "unknown")
        can_auto_login = result.get("can_auto_login", False)
        
        if success:
            profile = self.profiles_controller.get_profile(email)
            if profile:
                print(f"[Settings] ✅ Subscription updated: {profile.tier_display}, {profile.credits} credits")
            return
        
        # --- FAILURE: Show notification dialog ---
        reason_messages = {
            "profile_missing": "Browser profile not found.\nThe saved browser data has been deleted or moved.",
            "session_expired": "Session has expired.\nGoogle login session is no longer valid.",
            "not_logged_in": "Not logged in.\nNo active Google session found in browser profile.",
            "credits_api_failed": "Credits API failed.\nCouldn't fetch subscription info, but session is active.",
            "exception": "Unexpected error during subscription fetch.",
        }
        
        msg = reason_messages.get(reason, f"Unknown error: {reason}")
        
        if can_auto_login and reason in ("profile_missing", "session_expired", "not_logged_in"):
            # Offer auto-login
            reply = QMessageBox.question(
                self,
                f"⚠️ Session Problem - {email}",
                f"{msg}\n\n"
                f"🔑 Stored credentials found.\n"
                f"Auto re-login now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self._start_auto_relogin(email)
        else:
            # No auto-login available
            action = "Please re-login manually using the Browser button." if reason != "credits_api_failed" else "Try refreshing again later."
            QMessageBox.warning(
                self,
                f"⚠️ Session Problem - {email}",
                f"{msg}\n\n{action}"
            )
    
    def _start_auto_relogin(self, email: str):
        """Start auto re-login in background thread."""
        import threading
        
        self.setEnabled(False)
        self._update_row_status(email, "🔑 Re-logging in...", "...")
        
        def run_relogin():
            result_email = self.profiles_controller.auto_relogin(email)
            
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            if result_email:
                QMetaObject.invokeMethod(
                    self, "_on_auto_relogin_complete",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, email)
                )
            else:
                QMetaObject.invokeMethod(
                    self, "_on_auto_relogin_failed",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, email)
                )
        
        thread = threading.Thread(target=run_relogin, daemon=True)
        thread.start()
    
    @Slot(str)
    def _on_auto_relogin_complete(self, email: str):
        """Called when auto re-login succeeds."""
        self.setEnabled(True)
        self._refresh_profiles_table()
        QMessageBox.information(
            self,
            "Auto Re-Login",
            f"✅ Successfully re-logged in: {email}\n\nSubscription info updated."
        )
    
    @Slot(str)
    def _on_auto_relogin_failed(self, email: str):
        """Called when auto re-login fails."""
        self.setEnabled(True)
        self._refresh_profiles_table()
        QMessageBox.warning(
            self,
            "Auto Re-Login Failed",
            f"❌ Failed to re-login: {email}\n\nPlease login manually using the Browser button."
        )
    
    def _on_toggle_account(self, email: str, enabled: bool):
        """Handle toggle switch change - enable/disable account for generation.
        
        Args:
            email: Account email
            enabled: New enabled state
        """
        # Issue A fix: correct update_profile signature (email, **kwargs)
        if self.profiles_controller:
            self.profiles_controller.update_profile(email, is_enabled=enabled)
        
        # Issue C fix: propagate to runtime AccountManager._enabled
        if self.controller and hasattr(self.controller, 'toggle_account'):
            self.controller.toggle_account(email, enabled)
        
        state_str = "enabled ✅" if enabled else "disabled ⚫"
        print(f"[Settings] Account {email} {state_str}")
    
    def _on_slots_changed(self, email: str, value: int):
        """Handle Slots SpinBox change — per-account concurrent worker limit.
        
        Args:
            email: Account email
            value: New max_slots value (0-4)
        """
        # Persist to ChromeProfile
        if self.profiles_controller:
            self.profiles_controller.update_profile(email, max_slots=value)
        
        # Propagate to runtime AccountManager._session.max_slots
        if self.controller and hasattr(self.controller, 'set_account_max_slots'):
            self.controller.set_account_max_slots(email, value)
        
        print(f"[Settings] Account {email} max_slots → {value}")
    
    def _on_delete_profile(self, email: str):
        """Delete the specified profile after confirmation."""
        reply = QMessageBox.question(
            self, 
            "Delete Profile",
            f"Are you sure you want to delete profile '{email}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            print(f"[Settings] Deleting profile: {email}")
            self.profiles_controller.remove_profile(email)
            self._refresh_profiles_table()  # Reload table after delete
    
    def _parse_extract_point(self, text: str) -> int:
        """Convert '750ms (recommended)' → 750."""
        import re
        match = re.search(r'(\d+)', text)
        return int(match.group(1)) if match else 750
    
    def get_settings(self) -> dict:
        """Get current settings."""
        return {
            "aspect_ratio": self.setting_combos.get("Aspect Ratio").currentText() if "Aspect Ratio" in self.setting_combos else "",
            "download_quality": self.setting_combos.get("Download Quality").currentText() if "Download Quality" in self.setting_combos else "",
            "ai_model": self.setting_combos.get("AI Model").currentText() if "AI Model" in self.setting_combos else "",
            "outputs_per_prompt": self.setting_combos.get("Outputs per Prompt").currentText() if "Outputs per Prompt" in self.setting_combos else "",
            "output_folder": self.output_folder_entry.text(),
            "include_timestamp": self.output_toggles.get("Include timestamp in filename").isChecked() if "Include timestamp in filename" in self.output_toggles else False,
            "include_quality": self.output_toggles.get("Include quality in filename").isChecked() if "Include quality in filename" in self.output_toggles else False,
            "auto_start_queue": self.output_toggles.get("Auto-start queue when adding").isChecked() if "Auto-start queue when adding" in self.output_toggles else False,
            "pause_on_error": self.output_toggles.get("Pause on error").isChecked() if "Pause on error" in self.output_toggles else False,
            "headless": self.browser_toggles.get("Headless mode").isChecked() if "Headless mode" in self.browser_toggles else False,
            "persistent_profile": self.browser_toggles.get("Use persistent profile").isChecked() if "Use persistent profile" in self.browser_toggles else False,
            "auto_retry": self.browser_toggles.get("Enable auto-retry on failure").isChecked() if "Enable auto-retry on failure" in self.browser_toggles else False,
            "continuation_enabled": self.cont_switch.isToggled(),
            "extract_point_ms": self._parse_extract_point(self.extract_menu.currentText()),
            # Enhancer Image (BETA)
            "enhancer_enabled": self.enhancer_switch.isToggled(),
            "enhancer_quality": self.enhancer_quality.currentText(),
            "enhancer_scale": self.enhancer_scale.currentText(),
            "language": self.lang_menu.currentText(),
            # Worker Settings (defaults for new accounts)
            "retry_count": self.retry_count.value(),
            "request_timeout": self.request_timeout.value(),
            # Anti-Detect Spam
            "anti_detect_enabled": self.anti_detect_switch.isToggled(),
            "anti_detect_delay_min": self.anti_detect_delay_min.value(),
            "anti_detect_delay_max": self.anti_detect_delay_max.value(),
            # Font Size (new per docs)
            "font_size": self.font_size_menu.currentText(),
        }
