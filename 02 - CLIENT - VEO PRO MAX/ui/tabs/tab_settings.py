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
    QRadioButton, QButtonGroup, QSpinBox, QTableWidget, QTableWidgetItem,
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
    
    def _create_profiles_section(self) -> QWidget:
        """Create Chrome Profiles section - per TAB_07_SETTINGS.md spec.
        
        8 columns: ✓, #, Email, Type, Plan, Credits, Status, Actions
        """
        section, layout = self._create_section("🌐 Chrome Profiles (Account Manager)")
        
        # Create QTableWidget with 8 columns (added Type column)
        self.profiles_table = QTableWidget()
        self.profiles_table.setColumnCount(8)
        self.profiles_table.setHorizontalHeaderLabels([
            "✓", "#", "Email", "Type", "Plan", "Credits", "Status", "Actions"
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
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)  # Actions
        
        self.profiles_table.setColumnWidth(0, 80)   # ✓
        self.profiles_table.setColumnWidth(1, 40)   # #
        self.profiles_table.setColumnWidth(3, 80)   # Type - emoji only
        self.profiles_table.setColumnWidth(4, 80)   # Plan
        self.profiles_table.setColumnWidth(5, 80)   # Credits
        self.profiles_table.setColumnWidth(6, 110)  # Status - "🟢 Ready" needs more space
        self.profiles_table.setColumnWidth(7, 120)  # Actions - 3 buttons + spacing
        
        self.profiles_table.setMinimumHeight(150)
        self.profiles_table.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        self.profiles_table.setAlternatingRowColors(True)
        
        # Set default row height for better visibility
        self.profiles_table.verticalHeader().setDefaultSectionSize(48)
        self.profiles_table.verticalHeader().setVisible(False)  # Hide row numbers
        
        # Load profiles from controller
        self._refresh_profiles_table()
        
        layout.addWidget(self.profiles_table)
        
        # Dual login buttons - OAuth (quick) and Browser (full session)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # OAuth login - quick but plan shows "Wait"
        oauth_btn = QPushButton("🔑 OAuth")
        oauth_btn.setToolTip("Quick login via OAuth. Plan/Credits will show after first video.")
        oauth_btn.setStyleSheet(f"background-color: {Theme.BLUE}; height: 32px;")
        oauth_btn.clicked.connect(self._on_add_profile)
        btn_layout.addWidget(oauth_btn)
        
        # Browser login - full session with real-time subscription
        browser_btn = QPushButton("🌐 Browser")
        browser_btn.setToolTip("Login in browser. Plan/Credits available immediately.")
        browser_btn.setStyleSheet(f"background-color: {Theme.GREEN}; height: 32px;")
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
            placeholder = QTableWidgetItem("No profiles added. Click '🔑 OAuth' or '🌐 Browser' to add.")
            self.profiles_table.insertRow(0)
            self.profiles_table.setSpan(0, 0, 1, 8)  # 8 columns now
            self.profiles_table.setItem(0, 0, placeholder)
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
            
            # Email (col 2)
            email_item = QTableWidgetItem(acc.get('email', 'Unknown'))
            email_item.setFlags(email_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.profiles_table.setItem(i, 2, email_item)
            
            # Type (col 3) - 🔑 OAuth or 🌐 Browser (emoji only) - centered
            login_method = acc.get('login_method', 'oauth')
            type_emoji = "🌐" if login_method == "browser" else "🔑"
            type_tooltip = "Browser Login - Full session" if login_method == "browser" else "OAuth Login - Token based"
            type_item = QTableWidgetItem(type_emoji)
            type_item.setToolTip(type_tooltip)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(i, 3, type_item)
            
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
            
            # Actions buttons (col 7)
            actions_widget = QWidget()
            actions_widget.setStyleSheet("background: transparent;")
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 0, 2, 0)
            actions_layout.setSpacing(3)
            
            style = self.style()
            
            # Refresh button - refresh OAuth tokens
            refresh_btn = QPushButton()
            refresh_btn.setIcon(style.standardIcon(style.StandardPixmap.SP_BrowserReload))
            refresh_btn.setFixedSize(26, 26)
            refresh_btn.setToolTip("Refresh OAuth Token")
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
            
            self.profiles_table.setCellWidget(i, 7, actions_widget)
    
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
        """Add new account."""
        email = self.account_email_input.text().strip()
        if not email or '@' not in email:
            return
        
        if self.controller and hasattr(self.controller, 'add_account'):
            from core.session import AccountSession
            session = AccountSession(email=email)
            self.controller.add_account(session)
            self.account_email_input.clear()
            self._refresh_accounts()
    
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
        """Create Continuation Frame section - matches CTK lines 204-299."""
        section, layout = self._create_section("🔗 Continuation Frame Extraction")
        
        # Enable toggle
        enable_layout = QHBoxLayout()
        enable_label = QLabel("Enable Continuation:")
        enable_label.setStyleSheet(f"color: {Theme.TEXT};")
        enable_layout.addWidget(enable_label)
        enable_layout.addStretch()
        
        self.cont_switch = QCheckBox()
        self.cont_switch.setChecked(True)
        enable_layout.addWidget(self.cont_switch)
        layout.addLayout(enable_layout)
        
        # Extract Point - EXACT from CTK line 244
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
        
        # Frame Mode for I2V - CTK lines 261-299
        mode_label = QLabel("── TAB_02 (I2V/F2V) ──")
        mode_label.setStyleSheet(f"color: {Theme.SUBTEXT1}; font-size: 11px;")
        layout.addWidget(mode_label)
        
        frame_layout = QHBoxLayout()
        frame_label = QLabel("Use extracted frame as:")
        frame_label.setFixedWidth(150)
        frame_label.setStyleSheet(f"color: {Theme.TEXT};")
        frame_layout.addWidget(frame_label)
        
        self.frame_button_group = QButtonGroup(self)
        
        first_radio = QRadioButton("First Frame")
        first_radio.setChecked(True)
        first_radio.setStyleSheet(f"color: {Theme.TEXT};")
        self.frame_button_group.addButton(first_radio)
        frame_layout.addWidget(first_radio)
        
        last_radio = QRadioButton("Last Frame")
        last_radio.setStyleSheet(f"color: {Theme.TEXT};")
        self.frame_button_group.addButton(last_radio)
        frame_layout.addWidget(last_radio)
        
        frame_layout.addStretch()
        layout.addLayout(frame_layout)
        
        return section
    
    def _create_worker_section(self) -> QWidget:
        """Create Worker Settings section per TAB_07_SETTINGS.md spec."""
        section, layout = self._create_section("🎯 Worker Settings")
        
        # Max Concurrent Workers
        workers_row = QHBoxLayout()
        workers_label = QLabel("Max Concurrent Workers:")
        workers_label.setFixedWidth(180)
        workers_label.setStyleSheet(f"color: {Theme.TEXT};")
        workers_row.addWidget(workers_label)
        
        self.max_workers = QSpinBox()
        self.max_workers.setRange(1, 8)
        self.max_workers.setValue(2)
        self.max_workers.setFixedWidth(80)
        self.max_workers.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        workers_row.addWidget(self.max_workers)
        workers_row.addStretch()
        layout.addLayout(workers_row)
        
        # Retry on Error
        retry_row = QHBoxLayout()
        retry_label = QLabel("Retry on Error:")
        retry_label.setFixedWidth(180)
        retry_label.setStyleSheet(f"color: {Theme.TEXT};")
        retry_row.addWidget(retry_label)
        
        self.retry_count = QSpinBox()
        self.retry_count.setRange(0, 5)
        self.retry_count.setValue(3)
        self.retry_count.setFixedWidth(80)
        self.retry_count.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        retry_row.addWidget(self.retry_count)
        retry_row.addStretch()
        layout.addLayout(retry_row)
        
        # Request Timeout
        timeout_row = QHBoxLayout()
        timeout_label = QLabel("Request Timeout (s):")
        timeout_label.setFixedWidth(180)
        timeout_label.setStyleSheet(f"color: {Theme.TEXT};")
        timeout_row.addWidget(timeout_label)
        
        self.request_timeout = QSpinBox()
        self.request_timeout.setRange(30, 300)
        self.request_timeout.setValue(120)
        self.request_timeout.setFixedWidth(80)
        self.request_timeout.setSuffix("s")
        self.request_timeout.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        timeout_row.addWidget(self.request_timeout)
        timeout_row.addStretch()
        layout.addLayout(timeout_row)
        
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
    
    def _on_add_profile(self):
        """Add new Chrome profile via browser OAuth."""
        import threading
        
        # Show status in UI without blocking
        self.setEnabled(False)  # Disable tab during OAuth
        
        def run_oauth():
            """Run OAuth in background thread."""
            print("[Settings] Starting browser OAuth flow...")
            try:
                email = self.profiles_controller.add_profile_via_browser()
                
                # Update UI on main thread using signal
                from PySide6.QtCore import QMetaObject, Qt, Slot
                
                if email:
                    print(f"[Settings] Profile added: {email}")
                    # Schedule table refresh and re-enable
                    QMetaObject.invokeMethod(
                        self, "_on_oauth_complete",
                        Qt.ConnectionType.QueuedConnection
                    )
                else:
                    print("[Settings] OAuth cancelled or failed")
                    QMetaObject.invokeMethod(
                        self, "_on_oauth_failed",
                        Qt.ConnectionType.QueuedConnection
                    )
            except Exception as e:
                print(f"[Settings] OAuth error: {e}")
                from PySide6.QtCore import QMetaObject, Qt, Slot
                QMetaObject.invokeMethod(
                    self, "_on_oauth_failed",
                    Qt.ConnectionType.QueuedConnection
                )
        
        # Start OAuth in background thread
        thread = threading.Thread(target=run_oauth, daemon=True)
        thread.start()
        
        # Show non-blocking message (just print, browser opens automatically)
        print("[Settings] OAuth started - browser will open automatically")
    
    @Slot()
    def _on_oauth_complete(self):
        """Called when OAuth completes successfully."""
        self.setEnabled(True)  # Re-enable tab
        self._refresh_profiles_table()
        QMessageBox.information(self, "Success", "✅ Profile added successfully!")
    
    @Slot()
    def _on_oauth_failed(self):
        """Called when OAuth fails or is cancelled."""
        self.setEnabled(True)  # Re-enable tab
        self._refresh_profiles_table()
        QMessageBox.warning(self, "OAuth", "OAuth cancelled or failed.")
    
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
        from PySide6.QtWidgets import QLabel
        info_label = QLabel(
            "⚠️ Credentials are encrypted and stored locally.\n"
            "Browser will open to perform Google login."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
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
        
        if not email or not password:
            QMessageBox.warning(self, "Error", "Please enter both email and password.")
            return
        
        # Save credentials (encrypted)
        if not creds_manager.save_credentials(email, password):
            QMessageBox.warning(self, "Error", "Failed to save credentials.")
            return
        
        # Start auto-login
        self.setEnabled(False)
        
        def run_auto_login():
            """Run auto-login in background thread."""
            print(f"[Settings] Starting auto-login for {email}...")
            try:
                result_email = self.profiles_controller.auto_login_with_credentials(
                    email=email,
                    password=password,
                    timeout_seconds=120
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
        """Refresh session based on login method.
        
        OAuth: Refresh OAuth token, subscription shows placeholder
        Browser: Fetch subscription real-time via browser profile
        """
        import threading
        
        # Get profile to check login method
        profile = self.profiles_controller.get_profile(email)
        if not profile:
            QMessageBox.warning(self, "Error", f"Profile not found: {email}")
            return
        
        is_browser = profile.login_method == "browser"
        print(f"[Settings] Refreshing session for: {email} (method: {profile.login_method})")
        
        # Show loading state immediately on the row
        self._update_row_status(email, "⏳ Refreshing...", "...")
        
        if is_browser:
            # Browser profile: Just fetch subscription real-time
            self.setEnabled(False)
            
            def fetch_browser():
                print(f"[Settings] Fetching subscription via browser...")
                sub_success = self.profiles_controller.fetch_subscription_info(email)
                
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_on_subscription_fetched",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, email),
                    Q_ARG(bool, sub_success)
                )
            
            thread = threading.Thread(target=fetch_browser, daemon=True)
            thread.start()
        else:
            # OAuth profile: Refresh token, then fetch (placeholder)
            # Force UI repaint before blocking call so user sees loading state
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            token_success = self.profiles_controller.refresh_session(email)
            
            if not token_success:
                # Update row to show error state
                self._update_row_status(email, "🔴 Failed", "N/A")
                QMessageBox.warning(
                    self, "Token Refresh Failed",
                    f"❌ Failed to refresh token for {email}\nMay need to re-login."
                )
                return
            
            # Don't refresh table yet - keep showing loading state
            # Row already shows "⏳ Refreshing..." from above
            
            # Run subscription fetch in background
            def fetch_oauth():
                print(f"[Settings] OAuth refresh - fetching subscription...")
                success = self.profiles_controller.fetch_subscription_info(email)
                
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_on_subscription_fetched",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, email),
                    Q_ARG(bool, success)
                )
            
            thread = threading.Thread(target=fetch_oauth, daemon=True)
            thread.start()
            
            # No blocking QMessageBox - user sees inline "⏳ Refreshing..."
            print(f"[Settings] 🔑 OAuth token refreshed for {email}, fetching subscription...")
    
    @Slot(str, bool)
    def _on_subscription_fetched(self, email: str, success: bool):
        """Called when subscription fetch completes (from background thread)."""
        self.setEnabled(True)  # Re-enable tab (was disabled for browser fetch)
        self._refresh_profiles_table()
        
        if success:
            profile = self.profiles_controller.get_profile(email)
            if profile:
                print(f"[Settings] ✅ Subscription updated: {profile.tier_display}, {profile.credits} credits")
        else:
            print(f"[Settings] ⚠️ Couldn't fetch subscription for {email}")
    
    def _on_toggle_account(self, email: str, enabled: bool):
        """Handle toggle switch change - enable/disable account for generation.
        
        Args:
            email: Account email
            enabled: New enabled state
        """
        profile = self.profiles_controller.get_profile(email)
        if profile:
            profile.is_enabled = enabled
            self.profiles_controller.update_profile(profile)
            state_str = "enabled ✅" if enabled else "disabled ⚫"
            print(f"[Settings] Account {email} {state_str}")
    
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
            "continuation_enabled": self.cont_switch.isChecked(),
            "extract_point": self.extract_menu.currentText(),
            "language": self.lang_menu.currentText(),
            # Worker Settings (new per docs)
            "max_workers": self.max_workers.value(),
            "retry_count": self.retry_count.value(),
            "request_timeout": self.request_timeout.value(),
            # Font Size (new per docs)
            "font_size": self.font_size_menu.currentText(),
        }
