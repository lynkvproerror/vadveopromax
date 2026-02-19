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
    QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer

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
        
        # Periodic refresh timer for Extension status column (lightweight)
        self._ext_status_timer = QTimer(self)
        self._ext_status_timer.timeout.connect(self._refresh_ext_column)
        self._ext_status_timer.start(5000)  # Every 5 seconds
        
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
        
        # === DEFAULT SETTINGS SECTION ===
        defaults_section = self._create_defaults_section()
        self.content_layout.addWidget(defaults_section)
        
        # === OUTPUT SETTINGS SECTION ===
        output_section = self._create_output_section()
        self.content_layout.addWidget(output_section)
        
        # === CONTINUATION FRAME SECTION ===
        cont_section = self._create_continuation_section()
        self.content_layout.addWidget(cont_section)
        
        # === WORKER SETTINGS SECTION ===
        worker_section = self._create_worker_section()
        self.content_layout.addWidget(worker_section)
        
        # === SESSION & DATA SECTION ===
        session_section = self._create_session_section()
        self.content_layout.addWidget(session_section)
        
        # === NOTIFICATIONS SECTION ===
        notif_section = self._create_notification_section()
        self.content_layout.addWidget(notif_section)
        
        # === UI SECTION ===
        ui_section = self._create_ui_section()
        self.content_layout.addWidget(ui_section)
        
        # === PIPELINE OPTIMIZATION SECTION ===
        pipeline_section = self._create_pipeline_section()
        self.content_layout.addWidget(pipeline_section)
        
        # === IMAGE ENHANCER SECTION ===
        enhancer_section = self._create_enhancer_section()
        self.content_layout.addWidget(enhancer_section)
        
        # === ACTION BUTTONS (Save, Reset, Export, Import, Reload) ===
        action_buttons = self._create_action_buttons()
        self.content_layout.addWidget(action_buttons)
        
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
        
        9 columns: ✓, #, Email, Type, Plan, Credits, Status, Workers, Actions
        """
        section, layout = self._create_section("🌐 Chrome Profiles (Account Manager)")
        
        # Create QTableWidget with 11 columns (added Ext + Retry)
        self.profiles_table = QTableWidget()
        self.profiles_table.setColumnCount(11)
        self.profiles_table.setHorizontalHeaderLabels([
            "✓", "#", "Email", "Type", "Plan", "Credits", "Status", "Workers", "Ext", "Retry", "Actions"
        ])
        
        # Set column widths per docs spec
        header = self.profiles_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # ✓
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # #
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Email
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # Type
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Plan
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Credits
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)    # Status
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)    # Workers
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)    # Ext
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)    # Retry
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)   # Actions
        
        self.profiles_table.setColumnWidth(0, 80)   # ✓
        self.profiles_table.setColumnWidth(1, 40)   # #
        self.profiles_table.setColumnWidth(3, 120)  # Type - browser toggle button
        self.profiles_table.setColumnWidth(4, 80)   # Plan
        self.profiles_table.setColumnWidth(5, 80)   # Credits
        self.profiles_table.setColumnWidth(6, 110)  # Status
        self.profiles_table.setColumnWidth(7, 60)   # Workers - SpinBox 0-4
        self.profiles_table.setColumnWidth(8, 50)   # Ext - emoji status
        self.profiles_table.setColumnWidth(9, 50)   # Retry - number
        self.profiles_table.setColumnWidth(10, 260) # Actions - 5 buttons
        
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
            self.profiles_table.setSpan(0, 0, 1, 11)  # 11 columns
            self.profiles_table.setItem(0, 0, placeholder)
            self._adjust_table_height()
            return
        
        actual_row = 0  # Track actual table row (accounts + detail rows)
        
        for i, acc in enumerate(accounts):
            self.profiles_table.insertRow(actual_row)
            
            # Toggle switch (col 0) - Enable/Disable account for rotation
            is_enabled = acc.get('is_enabled', True)
            toggle = ToggleSwitch(checked=is_enabled)
            toggle.setToolTip("Toggle ON/OFF to enable/disable account for generation")
            email_for_toggle = acc.get('email', '')
            toggle.toggled_signal.connect(
                lambda checked, e=email_for_toggle: self._on_toggle_account(e, checked)
            )
            self.profiles_table.setCellWidget(actual_row, 0, toggle)
            
            # # row number (col 1) - centered
            row_item = QTableWidgetItem(str(i + 1))
            row_item.setFlags(row_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            row_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 1, row_item)
            
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
            self.profiles_table.setItem(actual_row, 2, email_item)
            
            # Type (col 3) - Toggle 🌐/👁️ button to show/hide browser
            type_btn = QPushButton("🌐 Open")
            type_btn.setToolTip("Click to open browser with this profile")
            type_btn.setFixedSize(75, 34)
            type_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.SURFACE2};
                    border: 1px solid {Theme.OVERLAY0};
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 2px 8px;
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
            self.profiles_table.setCellWidget(actual_row, 3, type_btn)
            
            # Plan (col 4) - tier_display already formatted - centered
            plan_item = QTableWidgetItem(acc.get('tier', '👤 Free'))
            plan_item.setFlags(plan_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            plan_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 4, plan_item)
            
            # Credits (col 5) - credits_display already formatted - centered
            credits_item = QTableWidgetItem(acc.get('credits', 'N/A'))
            credits_item.setFlags(credits_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            credits_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 5, credits_item)
            
            # Status (col 6) - Uses enhanced status_display from ChromeProfile - centered
            # Status values: 🔴 Expired, 🟠 Expiring, 🟡 Login, 🟢 Ready
            status = acc.get('status', '🟡 Login')
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 6, status_item)
            
            # Get email for action handlers
            email = acc.get('email', '')
            
            # Workers SpinBox (col 7) — per-account concurrent worker limit
            slots_spin = QSpinBox()
            slots_spin.setRange(0, 5)
            slots_spin.setValue(acc.get('max_slots', 4))
            slots_spin.setToolTip("Max concurrent workers for this account (0 = disable processing)")
            slots_spin.setFixedWidth(50)
            slots_spin.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 2px; text-align: center;")
            slots_spin.valueChanged.connect(
                lambda value, e=email: self._on_slots_changed(e, value)
            )
            self.profiles_table.setCellWidget(actual_row, 7, slots_spin)
            
            # Extension status (col 8) — shows if Extension WebSocket is connected for this email
            ext_connected = False
            try:
                if self.controller and hasattr(self.controller, '_extension_bridge'):
                    ext_connected = self.controller._extension_bridge.is_connected(email)
            except Exception:
                pass
            ext_icon = "🟢" if ext_connected else "🔴"
            ext_tip = "Extension connected" if ext_connected else "Extension not connected"
            ext_item = QTableWidgetItem(ext_icon)
            ext_item.setFlags(ext_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ext_item.setToolTip(ext_tip)
            self.profiles_table.setItem(actual_row, 8, ext_item)
            
            # Retry count (col 9) — shows retry_count from settings
            retry_count = acc.get('retry_count', 3)
            retry_item = QTableWidgetItem(str(retry_count))
            retry_item.setFlags(retry_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            retry_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            retry_item.setToolTip("Max retries on failure")
            self.profiles_table.setItem(actual_row, 9, retry_item)
            
            # Actions buttons (col 10)
            actions_widget = QWidget()
            actions_widget.setStyleSheet("background: transparent;")
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(4)
            
            # Common button style for high visibility on dark background
            def _action_btn(text, tip, bg_color):
                btn = QPushButton(text)
                btn.setFixedSize(32, 32)
                btn.setToolTip(tip)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {bg_color};
                        border: 1px solid rgba(255,255,255,0.15);
                        border-radius: 6px;
                        font-size: 15px;
                        padding: 0px;
                    }}
                    QPushButton:hover {{
                        border: 1px solid rgba(255,255,255,0.5);
                        background-color: {bg_color};
                    }}
                """)
                return btn
            
            # Save Password button
            pwd_btn = _action_btn("🔑", "Save Password (for auto re-login)", Theme.YELLOW)
            pwd_btn.clicked.connect(lambda checked, e=email: self._on_save_password(e))
            actions_layout.addWidget(pwd_btn)
            
            # Refresh button
            refresh_btn = _action_btn("🔃", "Refresh Session", Theme.BLUE)
            refresh_btn.clicked.connect(lambda checked, e=email: self._on_refresh_session(e))
            actions_layout.addWidget(refresh_btn)
            
            # Restart Browser button
            restart_btn = _action_btn("🔁", "Restart Browser (Kill + Relaunch)", "#FF6B00")
            restart_btn.clicked.connect(lambda checked, e=email: self._on_restart_browser(e))
            actions_layout.addWidget(restart_btn)
            
            # Delete button
            delete_btn = _action_btn("🗑️", "Delete Profile", Theme.RED)
            delete_btn.clicked.connect(lambda checked, e=email: self._on_delete_profile(e))
            actions_layout.addWidget(delete_btn)
            
            self.profiles_table.setCellWidget(actual_row, 10, actions_widget)
            
            actual_row += 1
        
        # Auto-expand table height to fit visible rows
        self._adjust_table_height()
    
    def _adjust_table_height(self):
        """Adjust table height to fit all visible rows (including expanded detail rows)."""
        tbl = self.profiles_table
        header_height = tbl.horizontalHeader().height()
        total_row_height = 0
        visible_count = 0
        for row in range(tbl.rowCount()):
            if not tbl.isRowHidden(row):
                # Use actual row height (detail rows may be taller)
                h = tbl.rowHeight(row)
                total_row_height += h
                visible_count += 1
        
        # Cap visible rows at 12 to avoid overly tall table
        if visible_count > 12:
            # Estimate: use average row height × 12
            avg = total_row_height // visible_count if visible_count else 48
            total_row_height = avg * 12
        
        total_height = header_height + total_row_height + 4  # +4 for borders
        tbl.setFixedHeight(max(total_height, 80))
    

    
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
    
    # _create_accounts_section — REMOVED (replaced by Chrome Profiles table)
    
    def _refresh_ext_column(self):
        """Lightweight periodic refresh of Extension status column (col 8) only.
        
        Runs every 5s via QTimer. Does NOT rebuild the table — just updates
        the Ext icon cells by checking is_connected() for each row's email.
        """
        if not self.controller or not hasattr(self.controller, '_extension_bridge'):
            return
        
        bridge = self.controller._extension_bridge
        if not bridge:
            return
        
        for row in range(self.profiles_table.rowCount()):
            email_item = self.profiles_table.item(row, 2)  # Email column
            if not email_item:
                continue
            
            # Extract raw email from display text (may have 🔑 prefix)
            email_text = email_item.text().strip()
            # Remove credential indicator prefix if present
            if email_text.startswith("🔑 "):
                email_text = email_text[2:].strip()
            
            ext_connected = False
            try:
                ext_connected = bridge.is_connected(email_text)
            except Exception:
                pass
            
            ext_item = self.profiles_table.item(row, 8)
            if ext_item:
                new_icon = "🟢" if ext_connected else "🔴"
                if ext_item.text() != new_icon:
                    ext_item.setText(new_icon)
                    ext_item.setToolTip(
                        "Extension connected" if ext_connected else "Extension not connected"
                    )
    
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
        slots_label = QLabel(f"Workers: {slots}")
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
        """Create Default Settings section — split into Video + Image sub-sections."""
        section, layout = self._create_section("⚙️ Default Settings")
        
        # Load saved values from AppSettings
        try:
            from config.settings import get_settings as _gs
            _s = _gs()
        except Exception:
            _s = None
        
        self.setting_combos = {}
        
        # --- Shared: Aspect Ratio ---
        ar_options = ["16:9 (Landscape)", "9:16 (Portrait)"]
        combo = self._create_setting_row(layout, "Aspect Ratio", ar_options)
        if _s:
            _ar = getattr(_s, 'default_aspect_ratio', 'LANDSCAPE')
            combo.setCurrentText("9:16 (Portrait)" if "PORTRAIT" in _ar.upper() else "16:9 (Landscape)")
        self.setting_combos["Aspect Ratio"] = combo
        
        # --- Shared: Outputs per Prompt ---
        out_options = ["1", "2", "3", "4"]
        combo = self._create_setting_row(layout, "Outputs per Prompt", out_options)
        if _s:
            _cnt = str(getattr(_s, 'default_output_count', 4))
            if _cnt in out_options:
                combo.setCurrentText(_cnt)
        self.setting_combos["Outputs per Prompt"] = combo
        
        # ─── 🎬 Video Defaults ───
        vid_label = QLabel("🎬 Video Defaults")
        vid_label.setStyleSheet(f"color: {Theme.BLUE}; font-weight: bold; padding-top: 8px;")
        layout.addWidget(vid_label)
        
        # Video: AI Model
        model_options = [
            "Veo 3.1 - Fast",
            "Veo 3.1 - Fast [LP]",
            "Veo 3.1 - Quality",
            "Veo 2 - Fast",
            "Veo 2 - Quality",
        ]
        combo = self._create_setting_row(layout, "AI Model", model_options)
        if _s:
            _m = getattr(_s, 'default_model', 'Veo 3.1 - Fast')
            idx = combo.findText(_m)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.setting_combos["AI Model"] = combo
        
        # Video: Download Quality
        vq_options = ["720p", "1080p", "4K"]
        combo = self._create_setting_row(layout, "Download Quality", vq_options)
        if _s:
            _vq = getattr(_s, 'default_download_quality', '1080p')
            if _vq in vq_options:
                combo.setCurrentText(_vq)
        self.setting_combos["Download Quality"] = combo
        
        # ─── 🖼️ Image Defaults ───
        img_label = QLabel("🖼️ Image Defaults")
        img_label.setStyleSheet(f"color: {Theme.PURPLE}; font-weight: bold; padding-top: 8px;")
        layout.addWidget(img_label)
        
        # Image: Download Quality
        iq_options = ["1k", "2k", "4k"]
        combo = self._create_setting_row(layout, "Image Quality", iq_options)
        if _s:
            _iq = getattr(_s, 'default_image_quality', '1k')
            if _iq in iq_options:
                combo.setCurrentText(_iq)
        self.setting_combos["Image Quality"] = combo
        
        # Wire save-on-change for all combos
        for key, cb in self.setting_combos.items():
            cb.currentTextChanged.connect(self._save_default_settings)
        
        return section
    
    def _save_default_settings(self, *args):
        """Persist default settings to AppSettings."""
        try:
            from config.settings import get_settings as _gs
            settings = _gs()
            # Aspect Ratio
            ar_text = self.setting_combos["Aspect Ratio"].currentText()
            settings.default_aspect_ratio = "PORTRAIT" if "Portrait" in ar_text else "LANDSCAPE"
            # Outputs per Prompt
            settings.default_output_count = int(self.setting_combos["Outputs per Prompt"].currentText())
            # Video: AI Model
            settings.default_model = self.setting_combos["AI Model"].currentText()
            # Video: Download Quality
            settings.default_download_quality = self.setting_combos["Download Quality"].currentText()
            # Image: Quality
            settings.default_image_quality = self.setting_combos["Image Quality"].currentText()
            settings.save()
        except Exception:
            pass
    
    def _create_output_section(self) -> QWidget:
        """Create Output Settings section — folder + filename toggles."""
        section, layout = self._create_section("📁 Output Settings")
        
        # Load saved values
        try:
            from config.settings import get_settings as _gs
            _s = _gs()
        except Exception:
            _s = None
        
        # Default output folder
        folder_layout = QHBoxLayout()
        
        folder_label = QLabel("Default Output Folder:")
        folder_label.setFixedWidth(150)
        folder_label.setStyleSheet(f"color: {Theme.TEXT};")
        folder_layout.addWidget(folder_label)
        
        self.output_folder_entry = QLineEdit()
        self.output_folder_entry.setPlaceholderText("D:/Projects/VEO")
        self.output_folder_entry.setMinimumWidth(300)
        if _s and getattr(_s, 'output_folder', ''):
            self.output_folder_entry.setText(_s.output_folder)
        folder_layout.addWidget(self.output_folder_entry)
        
        browse_btn = QPushButton("📂")
        browse_btn.setFixedSize(32, 32)
        browse_btn.setStyleSheet(f"background-color: {Theme.SURFACE2};")
        browse_btn.clicked.connect(self._browse_output_folder)
        folder_layout.addWidget(browse_btn)
        folder_layout.addStretch()
        
        layout.addLayout(folder_layout)
        
        # Toggles with saved state
        _ts = getattr(_s, 'include_timestamp', True) if _s else True
        _qs = getattr(_s, 'include_quality', True) if _s else True
        _as = getattr(_s, 'auto_start_queue', False) if _s else False
        _ps = getattr(_s, 'pause_on_error', True) if _s else True
        
        toggles = [
            ("Include timestamp in filename", _ts),
            ("Include quality in filename", _qs),
            ("Auto-start queue when adding", _as),
            ("Pause on error", _ps),
        ]
        
        self.output_toggles = {}
        for label, default in toggles:
            checkbox = QCheckBox(label)
            checkbox.setChecked(default)
            checkbox.setStyleSheet(f"color: {Theme.TEXT};")
            checkbox.toggled.connect(self._save_output_settings)
            layout.addWidget(checkbox)
            self.output_toggles[label] = checkbox
        
        # Wire folder save
        self.output_folder_entry.textChanged.connect(self._save_output_settings)
        
        return section
    
    def _browse_output_folder(self):
        """Open folder picker for default output folder."""
        folder = QFileDialog.getExistingDirectory(self, "Select Default Output Folder")
        if folder:
            self.output_folder_entry.setText(folder)
    
    def _save_output_settings(self, *args):
        """Persist output settings to AppSettings."""
        try:
            from config.settings import get_settings as _gs
            settings = _gs()
            settings.output_folder = self.output_folder_entry.text()
            settings.include_timestamp = self.output_toggles.get("Include timestamp in filename").isChecked() if "Include timestamp in filename" in self.output_toggles else True
            settings.include_quality = self.output_toggles.get("Include quality in filename").isChecked() if "Include quality in filename" in self.output_toggles else True
            settings.auto_start_queue = self.output_toggles.get("Auto-start queue when adding").isChecked() if "Auto-start queue when adding" in self.output_toggles else False
            settings.pause_on_error = self.output_toggles.get("Pause on error").isChecked() if "Pause on error" in self.output_toggles else True
            settings.save()
        except Exception:
            pass
    
    # _create_browser_section — REMOVED (headless/persistent profile managed elsewhere)
    
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
        
        # ✨ Enhancer Image — see dedicated section below (_create_enhancer_section)
        # Old Quality/Upscale dropdowns removed; replaced by 3-toggle system
        
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
                'anti_detect_delay_min': getattr(s, 'anti_detect_delay_min', 3.0),
                'anti_detect_delay_max': getattr(s, 'anti_detect_delay_max', 8.0),
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
        self.anti_detect_delay_min.setValue(saved.get('anti_detect_delay_min', 3.0))
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
        self.anti_detect_delay_max.setValue(saved.get('anti_detect_delay_max', 8.0))
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
    
    def _create_session_section(self) -> QWidget:
        """Create Session & Data Management section."""
        section, layout = self._create_section("💾 Session & Data")
        
        # Load saved values
        saved_restore_queue = False
        saved_restore_tabs = True
        if self.controller and hasattr(self.controller, 'settings') and self.controller.settings:
            s = self.controller.settings
            saved_restore_queue = getattr(s, 'restore_queue_on_startup', False)
            saved_restore_tabs = getattr(s, 'restore_tabs_on_startup', True)
        
        # Toggle: Restore Queue
        self.restore_queue_switch = self._create_enable_row(
            "Restore Queue:", checked=saved_restore_queue
        )
        layout.addLayout(self.restore_queue_switch._row_layout)
        
        # Description for restore queue
        queue_desc = QLabel("⚠️ When ON, tasks from previous session are reloaded. Turn OFF to prevent stale/broken tasks.")
        queue_desc.setWordWrap(True)
        queue_desc.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; margin-left: 16px; margin-bottom: 4px;")
        layout.addWidget(queue_desc)
        
        # Toggle: Restore Tabs
        self.restore_tabs_switch = self._create_enable_row(
            "Restore Tabs:", checked=saved_restore_tabs
        )
        layout.addLayout(self.restore_tabs_switch._row_layout)
        
        # Auto-save: persist session toggles immediately on change
        self.restore_queue_switch.toggled_signal.connect(self._save_session_settings)
        self.restore_tabs_switch.toggled_signal.connect(self._save_session_settings)
        
        # === Granular Restore Sub-toggles (grouped columns) ===
        self._restore_sub_container = QFrame()
        self._restore_sub_container.setStyleSheet(f"margin-left: 16px; padding: 4px 0;")
        sub_outer = QVBoxLayout(self._restore_sub_container)
        sub_outer.setContentsMargins(0, 4, 0, 4)
        sub_outer.setSpacing(4)
        
        sub_label = QLabel("Choose what to restore:")
        sub_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-style: italic;")
        sub_outer.addWidget(sub_label)
        
        # Load saved granular values
        _g = lambda attr, default=True: getattr(s, attr, default) if self.controller and hasattr(self.controller, 'settings') and self.controller.settings else default
        
        # Define groups with their options
        restore_groups = [
            ("📁 Project", [
                ("Project Name",    "restore_project_name",       _g('restore_project_name')),
                ("Output Folder",   "restore_output_folder",      _g('restore_output_folder')),
            ]),
            ("⚙️ Generation", [
                ("Aspect Ratio",      "restore_aspect_ratio",       _g('restore_aspect_ratio')),
                ("Outputs/Prompt",    "restore_outputs_per_prompt", _g('restore_outputs_per_prompt')),
                ("AI Model",          "restore_ai_model",           _g('restore_ai_model')),
                ("Download Quality",  "restore_download_quality",   _g('restore_download_quality')),
                ("Frame Mode (I2V)",  "restore_frame_mode",         _g('restore_frame_mode')),
            ]),
            ("✍️ Content", [
                ("Prompt Input",    "restore_prompt_input",       _g('restore_prompt_input')),
                ("Parsed Prompts",  "restore_parsed_prompts",     _g('restore_parsed_prompts')),
                ("Prompt Images",   "restore_prompt_images",      _g('restore_prompt_images')),
            ]),
        ]
        
        # Create columns layout
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(12)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        
        self._restore_sub_toggles = {}  # attr_name -> toggle widget
        
        for group_title, options in restore_groups:
            group_frame = QFrame()
            group_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {Theme.SURFACE1};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 6px;
                    padding: 4px;
                }}
            """)
            group_layout = QVBoxLayout(group_frame)
            group_layout.setContentsMargins(8, 6, 8, 6)
            group_layout.setSpacing(2)
            
            # Group header
            header = QLabel(group_title)
            header.setStyleSheet(f"color: {Theme.TEXT}; font-size: 11px; font-weight: bold; border: none; padding: 0; margin-bottom: 2px;")
            group_layout.addWidget(header)
            
            for label_text, attr_name, checked in options:
                toggle = self._create_enable_row(label_text, checked=checked)
                group_layout.addLayout(toggle._row_layout)
                toggle.toggled_signal.connect(self._save_session_settings)
                self._restore_sub_toggles[attr_name] = toggle
            
            group_layout.addStretch()
            columns_layout.addWidget(group_frame)
        
        sub_outer.addLayout(columns_layout)
        
        layout.addWidget(self._restore_sub_container)
        
        # Show/hide sub-toggles based on Restore Tabs state
        self._restore_sub_container.setVisible(saved_restore_tabs)
        self.restore_tabs_switch.toggled_signal.connect(
            lambda checked: self._restore_sub_container.setVisible(checked)
        )
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {Theme.BORDER}; max-height: 1px; margin: 8px 0;")
        layout.addWidget(sep)
        
        # Cache stats label
        cache_stats = self._get_cache_stats_text()
        self.cache_stats_label = QLabel(cache_stats)
        self.cache_stats_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        layout.addWidget(self.cache_stats_label)
        
        # Action buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # Clear Cache button (YELLOW)
        clear_cache_btn = QPushButton("🧹 Clear Cache")
        clear_cache_btn.setFixedHeight(32)
        clear_cache_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.YELLOW};
                color: {Theme.CRUST};
                border-radius: 6px;
                padding: 0 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #FCE8C0;
            }}
        """)
        clear_cache_btn.setToolTip("Delete cached files (downloaded videos, temp data)")
        clear_cache_btn.clicked.connect(self._on_clear_cache)
        btn_layout.addWidget(clear_cache_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return section
    
    def _get_cache_stats_text(self) -> str:
        """Get cache statistics as display text."""
        try:
            if self.controller and hasattr(self.controller, 'get_cache_stats'):
                stats = self.controller.get_cache_stats()
                size_mb = stats.get("size_mb", 0)
                file_count = stats.get("file_count", 0)
                return f"📊 Cache: {size_mb:.1f} MB ({file_count} files)"
        except Exception:
            pass
        return "📊 Cache: N/A"
    
    def _on_clear_cache(self):
        """Clear cache files with confirmation."""
        reply = QMessageBox.question(
            self, "Clear Cache",
            "🧹 This will delete ALL cached files.\n\n"
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.controller and hasattr(self.controller, 'clear_cache'):
                result = self.controller.clear_cache()
                deleted = result.get("deleted_count", 0)
                freed = result.get("freed_mb", 0)
                QMessageBox.information(
                    self, "Cache Cleared",
                    f"✅ {deleted} files removed ({freed:.1f} MB freed)."
                )
                # Refresh cache stats
                self.cache_stats_label.setText(self._get_cache_stats_text())

    def _create_notification_section(self) -> QWidget:
        """Create Notifications section — toast + sound settings."""
        section, layout = self._create_section("🔔 Notifications")
        
        from config.settings import get_settings
        settings = get_settings()
        
        # Row 1: In-App Toast toggle
        toast_row = QHBoxLayout()
        
        toast_label = QLabel("In-App Toast:")
        toast_label.setFixedWidth(150)
        toast_label.setStyleSheet(f"color: {Theme.TEXT};")
        toast_row.addWidget(toast_label)
        
        self.notify_toast_toggle = ToggleSwitch(checked=settings.notify_toast_enabled)
        toast_row.addWidget(self.notify_toast_toggle)
        toast_row.addStretch()
        layout.addLayout(toast_row)
        
        # Row 2: Sound Notification toggle + sound selector + preview
        sound_row = QHBoxLayout()
        
        sound_label = QLabel("Sound Notification:")
        sound_label.setFixedWidth(150)
        sound_label.setStyleSheet(f"color: {Theme.TEXT};")
        sound_row.addWidget(sound_label)
        
        self.notify_sound_toggle = ToggleSwitch(checked=settings.notify_sound_enabled)
        sound_row.addWidget(self.notify_sound_toggle)
        
        # Separator
        sep = QFrame()
        sep.setFixedSize(1, 24)
        sep.setStyleSheet(f"background-color: {Theme.BORDER};")
        sound_row.addWidget(sep)
        
        # Sound selector dropdown
        sound_select_label = QLabel("Sound:")
        sound_select_label.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        sound_row.addWidget(sound_select_label)
        
        self.sound_file_combo = QComboBox()
        from core.notification_manager import BUILTIN_SOUNDS
        self._builtin_sound_names = list(BUILTIN_SOUNDS.keys())
        self.sound_file_combo.addItems(self._builtin_sound_names + ["Custom..."])
        self.sound_file_combo.setFixedWidth(140)
        
        # Set current selection from settings
        current_sound = settings.notify_sound_file
        if current_sound in self._builtin_sound_names:
            self.sound_file_combo.setCurrentText(current_sound)
        elif current_sound:
            # Custom file — show filename
            from pathlib import Path
            custom_name = Path(current_sound).name
            idx = self.sound_file_combo.count() - 1  # Before "Custom..."
            self.sound_file_combo.insertItem(idx, f"📁 {custom_name}")
            self.sound_file_combo.setCurrentIndex(idx)
            self.sound_file_combo.setItemData(idx, current_sound, Qt.UserRole)
        
        self.sound_file_combo.currentIndexChanged.connect(self._on_sound_selection_changed)
        sound_row.addWidget(self.sound_file_combo)
        
        # Preview button
        from PySide6.QtWidgets import QPushButton
        preview_btn = QPushButton("🔊 Preview")
        preview_btn.setFixedWidth(90)
        preview_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {Theme.SURFACE2};
            }}
        """)
        preview_btn.clicked.connect(self._on_preview_sound)
        sound_row.addWidget(preview_btn)
        
        sound_row.addStretch()
        layout.addLayout(sound_row)
        
        # Auto-save: connect toggles + dropdown to persist immediately
        self.notify_toast_toggle.toggled_signal.connect(self._save_notification_settings)
        self.notify_sound_toggle.toggled_signal.connect(self._save_notification_settings)
        self.sound_file_combo.currentIndexChanged.connect(
            lambda: self._save_notification_settings()
        )
        
        return section
    
    def _save_notification_settings(self, *args):
        """Persist notification settings to AppSettings singleton."""
        from config.settings import get_settings, save_settings
        settings = get_settings()
        settings.notify_toast_enabled = self.notify_toast_toggle.isToggled()
        settings.notify_sound_enabled = self.notify_sound_toggle.isToggled()
        settings.notify_sound_file = self._get_selected_sound()
        save_settings()
    
    def _save_session_settings(self, *args):
        """Persist session toggles (Restore Queue/Tabs + granular options) to AppSettings immediately."""
        from config.settings import get_settings, save_settings
        settings = get_settings()
        settings.restore_queue_on_startup = self.restore_queue_switch.isToggled()
        settings.restore_tabs_on_startup = self.restore_tabs_switch.isToggled()
        # Save granular sub-toggles
        for attr_name, toggle in self._restore_sub_toggles.items():
            setattr(settings, attr_name, toggle.isToggled())
        save_settings()
    
    def _on_sound_selection_changed(self, index: int):
        """Handle sound dropdown selection change."""
        text = self.sound_file_combo.currentText()
        if text == "Custom...":
            from PySide6.QtWidgets import QFileDialog
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Select Sound File", "",
                "Sound Files (*.wav *.mp3);;All Files (*)"
            )
            if filepath:
                from pathlib import Path
                custom_name = Path(filepath).name
                # Insert custom file before "Custom..." item
                insert_idx = self.sound_file_combo.count() - 1
                self.sound_file_combo.blockSignals(True)
                self.sound_file_combo.insertItem(insert_idx, f"📁 {custom_name}")
                self.sound_file_combo.setItemData(insert_idx, filepath, Qt.UserRole)
                self.sound_file_combo.setCurrentIndex(insert_idx)
                self.sound_file_combo.blockSignals(False)
            else:
                # User cancelled — revert to "default"
                self.sound_file_combo.blockSignals(True)
                self.sound_file_combo.setCurrentIndex(0)
                self.sound_file_combo.blockSignals(False)
    
    def _on_preview_sound(self):
        """Preview the currently selected notification sound."""
        sound = self._get_selected_sound()
        try:
            from core.notification_manager import NotificationManager
            if not hasattr(self, '_preview_player'):
                self._preview_player = NotificationManager()
            self._preview_player.play(sound, duration_ms=4000)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Sound Error", f"Cannot play sound: {e}")
    
    def _get_selected_sound(self) -> str:
        """Get the sound file name/path from the current dropdown selection."""
        text = self.sound_file_combo.currentText()
        if text in self._builtin_sound_names:
            return text
        # Custom file — get path from UserRole data
        custom_path = self.sound_file_combo.itemData(
            self.sound_file_combo.currentIndex(), Qt.UserRole
        )
        return custom_path if custom_path else "default"
    
    def _create_ui_section(self) -> QWidget:
        """Create UI section — Language selector."""
        section, layout = self._create_section("🎨 UI")
        
        row_layout = QHBoxLayout()
        
        # Language
        lang_label = QLabel("🌐 Language:")
        lang_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        row_layout.addWidget(lang_label)
        
        self.lang_menu = QComboBox()
        self.lang_menu.addItems(["Tiếng Việt", "English"])
        self.lang_menu.setFixedWidth(140)
        row_layout.addWidget(self.lang_menu)
        
        row_layout.addStretch()
        layout.addLayout(row_layout)
        
        return section
    
    def _create_pipeline_section(self) -> QWidget:
        """Create Pipeline Optimization section with live-tunable settings."""
        section, layout = self._create_section("🔧 Pipeline Optimization")
        
        # Load current values from controller
        ps = {}
        if self.controller and hasattr(self.controller, 'get_pipeline_settings'):
            ps = self.controller.get_pipeline_settings()
        
        def _update(key):
            """Factory for pipeline settings callback."""
            def _cb(value):
                if self.controller and hasattr(self.controller, 'update_pipeline_settings'):
                    self.controller.update_pipeline_settings(key, value)
            return _cb
        
        # --- Adaptive Burst ---
        self.burst_switch = self._create_enable_row(
            "⚡ Adaptive Burst:", checked=ps.get('adaptive_burst_enabled', True),
            bold=True, color=Theme.BLUE
        )
        layout.addLayout(self.burst_switch._row_layout)
        
        burst_container = QWidget()
        burst_layout = QVBoxLayout(burst_container)
        burst_layout.setContentsMargins(0, 0, 0, 0)
        
        # Burst Min Delay
        bmin_row = QHBoxLayout()
        bmin_label = QLabel("Min Delay:")
        bmin_label.setFixedWidth(150)
        bmin_label.setStyleSheet(f"color: {Theme.TEXT};")
        bmin_row.addWidget(bmin_label)
        self.burst_min = QDoubleSpinBox()
        self.burst_min.setRange(0.5, 10.0)
        self.burst_min.setSingleStep(0.5)
        self.burst_min.setDecimals(1)
        self.burst_min.setValue(ps.get('burst_min_delay', 2.0))
        self.burst_min.setFixedWidth(80)
        self.burst_min.setSuffix("s")
        self.burst_min.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        self.burst_min.valueChanged.connect(_update('burst_min_delay'))
        bmin_row.addWidget(self.burst_min)
        bmin_row.addStretch()
        burst_layout.addLayout(bmin_row)
        
        # Burst Max Delay
        bmax_row = QHBoxLayout()
        bmax_label = QLabel("Max Delay:")
        bmax_label.setFixedWidth(150)
        bmax_label.setStyleSheet(f"color: {Theme.TEXT};")
        bmax_row.addWidget(bmax_label)
        self.burst_max = QDoubleSpinBox()
        self.burst_max.setRange(5.0, 60.0)
        self.burst_max.setSingleStep(1.0)
        self.burst_max.setDecimals(1)
        self.burst_max.setValue(ps.get('burst_max_delay', 15.0))
        self.burst_max.setFixedWidth(80)
        self.burst_max.setSuffix("s")
        self.burst_max.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        self.burst_max.valueChanged.connect(_update('burst_max_delay'))
        bmax_row.addWidget(self.burst_max)
        bmax_row.addStretch()
        burst_layout.addLayout(bmax_row)
        
        layout.addWidget(burst_container)
        burst_container.setVisible(self.burst_switch.isToggled())
        self.burst_switch.toggled_signal.connect(burst_container.setVisible)
        
        # --- reCAPTCHA Pool ---
        self.pool_switch = self._create_enable_row(
            "🔄 reCAPTCHA Pool:", checked=ps.get('recaptcha_pool_enabled', True),
            bold=True, color=Theme.GREEN
        )
        self.pool_switch.toggled_signal.connect(_update('recaptcha_pool_enabled'))
        layout.addLayout(self.pool_switch._row_layout)
        
        pool_row = QHBoxLayout()
        pool_label = QLabel("Pool Size:")
        pool_label.setFixedWidth(150)
        pool_label.setStyleSheet(f"color: {Theme.TEXT};")
        pool_row.addWidget(pool_label)
        self.pool_size = QSpinBox()
        self.pool_size.setRange(1, 5)
        self.pool_size.setValue(ps.get('pool_size', 2))
        self.pool_size.setFixedWidth(80)
        self.pool_size.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        self.pool_size.valueChanged.connect(_update('pool_size'))
        pool_row.addWidget(self.pool_size)
        pool_row.addStretch()
        layout.addLayout(pool_row)
        
        # --- Watchdog ---
        wd_row = QHBoxLayout()
        wd_label = QLabel("🐕 Watchdog Timeout:")
        wd_label.setFixedWidth(150)
        wd_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        wd_row.addWidget(wd_label)
        self.watchdog_timeout = QSpinBox()
        self.watchdog_timeout.setRange(5, 60)
        self.watchdog_timeout.setValue(ps.get('watchdog_timeout_min', 10))
        self.watchdog_timeout.setFixedWidth(80)
        self.watchdog_timeout.setSuffix(" min")
        self.watchdog_timeout.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        self.watchdog_timeout.valueChanged.connect(_update('watchdog_timeout_min'))
        wd_row.addWidget(self.watchdog_timeout)
        wd_row.addStretch()
        layout.addLayout(wd_row)
        
        # --- Journal ---
        jr_row = QHBoxLayout()
        jr_label = QLabel("📓 Journal Auto-save:")
        jr_label.setFixedWidth(150)
        jr_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        jr_row.addWidget(jr_label)
        self.journal_interval = QSpinBox()
        self.journal_interval.setRange(10, 120)
        self.journal_interval.setValue(ps.get('journal_save_interval_sec', 30))
        self.journal_interval.setFixedWidth(80)
        self.journal_interval.setSuffix("s")
        self.journal_interval.setStyleSheet(f"background-color: {Theme.SURFACE2}; padding: 4px;")
        self.journal_interval.valueChanged.connect(_update('journal_save_interval_sec'))
        jr_row.addWidget(self.journal_interval)
        jr_row.addStretch()
        layout.addLayout(jr_row)
        
        return section
    
    def _create_enhancer_section(self) -> QWidget:
        """Create Image Enhancer section — GPU status, 3 toggles, model download."""
        section, layout = self._create_section("✨ Image Enhancer (AI Upscale)")
        
        # GPU Status row
        gpu_row = QHBoxLayout()
        gpu_label = QLabel("GPU Status:")
        gpu_label.setFixedWidth(150)
        gpu_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        gpu_row.addWidget(gpu_label)
        
        self._enhance_gpu_status = QLabel("🔍 Detecting GPU...")
        self._enhance_gpu_status.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        gpu_row.addWidget(self._enhance_gpu_status)
        gpu_row.addStretch()
        layout.addLayout(gpu_row)
        
        # Model Status row
        model_row = QHBoxLayout()
        model_label = QLabel("AI Models:")
        model_label.setFixedWidth(150)
        model_label.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold;")
        model_row.addWidget(model_label)
        
        self._enhance_model_status = QLabel("⏳ Checking...")
        self._enhance_model_status.setStyleSheet(f"color: {Theme.SUBTEXT0};")
        model_row.addWidget(self._enhance_model_status)
        
        self._enhance_download_btn = QPushButton("⬇️ Download Models")
        self._enhance_download_btn.setFixedHeight(28)
        self._enhance_download_btn.setStyleSheet(
            f"background-color: {Theme.BLUE}; font-size: 11px; padding: 2px 12px;"
        )
        self._enhance_download_btn.clicked.connect(self._on_download_enhancer_models)
        self._enhance_download_btn.setVisible(False)  # Show only when models missing
        model_row.addWidget(self._enhance_download_btn)
        model_row.addStretch()
        layout.addLayout(model_row)
        
        # Download progress bar (hidden by default)
        self._enhance_progress = None
        try:
            from PySide6.QtWidgets import QProgressBar
            self._enhance_progress = QProgressBar()
            self._enhance_progress.setFixedHeight(18)
            self._enhance_progress.setRange(0, 100)
            self._enhance_progress.setVisible(False)
            self._enhance_progress.setStyleSheet(f"""
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
            layout.addWidget(self._enhance_progress)
        except Exception:
            pass
        
        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Theme.OVERLAY0};")
        layout.addWidget(sep)
        
        # Load saved toggle states from settings
        _ctx_on = True
        _lib_on = True
        _auto_on = False
        if self.controller:
            _s = getattr(self.controller, 'settings', None)
            if _s:
                _ctx_on = getattr(_s, 'enhance_context_menu', True)
                _lib_on = getattr(_s, 'enhance_library', True)
                _auto_on = getattr(_s, 'enhance_auto_continuation', False)
        
        # Toggle 1: Context Menu Enhance
        self._enhance_context_toggle = self._create_enable_row(
            "Context Menu", checked=_ctx_on, badge=""
        )
        self._enhance_context_toggle.setToolTip(
            "Right-click on images to enhance them (upscale/face restore)"
        )
        layout.addLayout(self._enhance_context_toggle._row_layout)
        
        # Toggle 2: Library Enhance
        self._enhance_library_toggle = self._create_enable_row(
            "Library Enhance", checked=_lib_on, badge=""
        )
        self._enhance_library_toggle.setToolTip(
            "Add 'Enhance' button to Image Library toolbar"
        )
        layout.addLayout(self._enhance_library_toggle._row_layout)
        
        # Toggle 3: Auto-Enhance Continuation Frames
        self._enhance_auto_toggle = self._create_enable_row(
            "Auto-Enhance", checked=_auto_on, badge="BETA"
        )
        self._enhance_auto_toggle.setToolTip(
            "Automatically enhance continuation frames before uploading (may add 5-10s per chain)"
        )
        layout.addLayout(self._enhance_auto_toggle._row_layout)
        
        # Connect toggles to save
        self._enhance_context_toggle.toggled_signal.connect(self._save_enhancer_settings)
        self._enhance_library_toggle.toggled_signal.connect(self._save_enhancer_settings)
        self._enhance_auto_toggle.toggled_signal.connect(self._save_enhancer_settings)
        
        # PyTorch install button (shown only if torch not installed)
        self._enhance_install_btn = QPushButton("📦 Install PyTorch (CUDA)")
        self._enhance_install_btn.setFixedHeight(28)
        self._enhance_install_btn.setStyleSheet(
            f"background-color: {Theme.YELLOW}; color: {Theme.BASE}; "
            f"font-size: 11px; font-weight: bold; padding: 2px 12px;"
        )
        self._enhance_install_btn.clicked.connect(self._on_install_pytorch)
        self._enhance_install_btn.setVisible(False)
        layout.addWidget(self._enhance_install_btn)
        
        # Start GPU detection refresh (poll GPUDetector result)
        self._enhance_check_timer = QTimer(self)
        self._enhance_check_timer.timeout.connect(self._refresh_enhancer_status)
        self._enhance_check_timer.start(2000)  # Check every 2s until resolved
        
        return section
    
    def _refresh_enhancer_status(self):
        """Poll GPU detector and model manager status — update UI."""
        if not self.controller:
            return
        
        # GPU detector
        gpu_det = getattr(self.controller, '_gpu_detector', None)
        if gpu_det:
            status = gpu_det.available
            if status is not None:
                self._enhance_gpu_status.setText(gpu_det.display_text)
                if status:
                    self._enhance_gpu_status.setStyleSheet(f"color: {Theme.GREEN};")
                else:
                    self._enhance_gpu_status.setStyleSheet(f"color: {Theme.RED};")
                    # Show install button if PyTorch missing
                    if gpu_det.install_hint:
                        self._enhance_install_btn.setVisible(True)
                    # Disable toggles if no GPU
                    self._enhance_context_toggle.setEnabled(False)
                    self._enhance_library_toggle.setEnabled(False)
                    self._enhance_auto_toggle.setEnabled(False)
        
        # Model manager
        mdl_mgr = getattr(self.controller, '_model_manager', None)
        if mdl_mgr:
            if mdl_mgr.all_installed:
                self._enhance_model_status.setText(
                    f"✅ All models installed ({mdl_mgr.total_download_size_mb}MB)"
                )
                self._enhance_model_status.setStyleSheet(f"color: {Theme.GREEN};")
                self._enhance_download_btn.setVisible(False)
            else:
                missing = mdl_mgr.missing_download_size_mb
                self._enhance_model_status.setText(
                    f"⬇️ Missing models ({missing}MB)"
                )
                self._enhance_model_status.setStyleSheet(f"color: {Theme.YELLOW};")
                self._enhance_download_btn.setVisible(True)
                self._enhance_download_btn.setText(f"⬇️ Download ({missing}MB)")
        
        # Stop polling once both are resolved
        if gpu_det and gpu_det.available is not None:
            # Keep slower poll for model status changes
            self._enhance_check_timer.setInterval(10000)
    
    def _on_download_enhancer_models(self):
        """Start downloading AI models in background."""
        if not self.controller:
            return
        mdl_mgr = getattr(self.controller, '_model_manager', None)
        if not mdl_mgr:
            return
        
        self._enhance_download_btn.setEnabled(False)
        self._enhance_download_btn.setText("⏳ Downloading...")
        if self._enhance_progress:
            self._enhance_progress.setVisible(True)
            self._enhance_progress.setValue(0)
        
        import threading
        def _download():
            def _progress(pct, msg):
                if self._enhance_progress and pct >= 0:
                    # Thread-safe UI update
                    QTimer.singleShot(0, lambda: self._enhance_progress.setValue(pct))
                    QTimer.singleShot(0, lambda: self._enhance_model_status.setText(msg))
            
            success = mdl_mgr.download_all(progress_callback=_progress)
            QTimer.singleShot(0, lambda: self._on_download_complete(success))
        
        threading.Thread(target=_download, daemon=True, name="model-download").start()
    
    def _on_download_complete(self, success: bool):
        """Handle model download completion."""
        if self._enhance_progress:
            self._enhance_progress.setVisible(False)
        self._enhance_download_btn.setEnabled(True)
        
        if success:
            self._enhance_model_status.setText("✅ All models installed")
            self._enhance_model_status.setStyleSheet(f"color: {Theme.GREEN};")
            self._enhance_download_btn.setVisible(False)
        else:
            self._enhance_model_status.setText("❌ Download failed — retry?")
            self._enhance_model_status.setStyleSheet(f"color: {Theme.RED};")
            self._enhance_download_btn.setText("🔄 Retry Download")
    
    def _on_install_pytorch(self):
        """Show PyTorch install confirmation dialog."""
        reply = QMessageBox.question(
            self,
            "Install PyTorch (CUDA)",
            "This will install PyTorch with CUDA support (~2.5GB).\n\n"
            "Command:\npip install torch torchvision torchaudio "
            "--index-url https://download.pytorch.org/whl/cu121\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._enhance_install_btn.setEnabled(False)
            self._enhance_install_btn.setText("⏳ Installing...")
            
            import subprocess, sys, threading
            def _install():
                try:
                    result = subprocess.run(
                        [sys.executable, '-m', 'pip', 'install',
                         'torch', 'torchvision', 'torchaudio',
                         '--index-url', 'https://download.pytorch.org/whl/cu121'],
                        capture_output=True, text=True, timeout=600,
                    )
                    success = result.returncode == 0
                except Exception:
                    success = False
                QTimer.singleShot(0, lambda: self._on_pytorch_install_complete(success))
            
            threading.Thread(target=_install, daemon=True, name="pytorch-install").start()
    
    def _on_pytorch_install_complete(self, success: bool):
        """Handle PyTorch install completion."""
        self._enhance_install_btn.setEnabled(True)
        if success:
            self._enhance_install_btn.setVisible(False)
            self._enhance_gpu_status.setText("🔄 Restart app to detect GPU")
            self._enhance_gpu_status.setStyleSheet(f"color: {Theme.YELLOW};")
            QMessageBox.information(
                self, "PyTorch Installed",
                "PyTorch installed successfully!\n\n"
                "Please restart the app to enable GPU detection."
            )
        else:
            self._enhance_install_btn.setText("❌ Install Failed — Retry")
            QMessageBox.warning(
                self, "Install Failed",
                "PyTorch installation failed.\n\n"
                "Try manually:\npip install torch torchvision torchaudio "
                "--index-url https://download.pytorch.org/whl/cu121"
            )
    
    def _save_enhancer_settings(self, *args):
        """Persist enhancer toggle states to AppSettings dataclass."""
        if not self.controller:
            return
        settings = getattr(self.controller, 'settings', None)
        if settings:
            settings.enhance_context_menu = self._enhance_context_toggle.isToggled()
            settings.enhance_library = self._enhance_library_toggle.isToggled()
            settings.enhance_auto_continuation = self._enhance_auto_toggle.isToggled()
            try:
                settings.save()
            except Exception:
                pass
    
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
        
        # Reload App button — restart Python process
        reload_btn = QPushButton("🔄 Reload App")
        reload_btn.setToolTip("Restart application (browsers keep running)")
        reload_btn.setStyleSheet(f"background-color: #FF6B00; color: {Theme.CRUST}; height: 36px; font-weight: bold;")
        reload_btn.clicked.connect(self._on_reload_app)
        layout.addWidget(reload_btn)
        
        layout.addStretch()
        
        return frame
    
    def _on_save(self):
        """Save settings and emit signal."""
        settings = self.get_settings()
        self.settings_changed.emit(settings)
    
    def _on_reset(self):
        """Reset to default values."""
        # Reset defaults section
        if "Aspect Ratio" in self.setting_combos:
            self.setting_combos["Aspect Ratio"].setCurrentText("16:9 (Landscape)")
        if "Outputs per Prompt" in self.setting_combos:
            self.setting_combos["Outputs per Prompt"].setCurrentText("4")
        if "AI Model" in self.setting_combos:
            self.setting_combos["AI Model"].setCurrentText("Veo 3.1 - Fast")
        if "Download Quality" in self.setting_combos:
            self.setting_combos["Download Quality"].setCurrentText("1080p")
        if "Image Quality" in self.setting_combos:
            self.setting_combos["Image Quality"].setCurrentText("1k")
        # Reset output toggles
        if hasattr(self, 'output_toggles'):
            for key, toggle in self.output_toggles.items():
                if "timestamp" in key.lower() or "quality" in key.lower() or "Pause" in key:
                    toggle.setChecked(True)
                else:
                    toggle.setChecked(False)
        # Reset worker spinboxes to defaults
        self.retry_count.setValue(3)
        self.request_timeout.setValue(120)
        # Reset anti-detect spam to defaults
        self.anti_detect_switch.setToggled(True)
        self.anti_detect_delay_min.setValue(3.0)
        self.anti_detect_delay_max.setValue(8.0)
        # Reset enhancer toggles to defaults (new 3-toggle system)
        if hasattr(self, '_enhance_context_toggle'):
            self._enhance_context_toggle.setToggled(True)
        if hasattr(self, '_enhance_library_toggle'):
            self._enhance_library_toggle.setToggled(True)
        if hasattr(self, '_enhance_auto_toggle'):
            self._enhance_auto_toggle.setToggled(False)
        # Reset session & data to defaults
        self.restore_queue_switch.setToggled(False)
        self.restore_tabs_switch.setToggled(True)
    
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
        # Session & Data
        if "restore_queue_on_startup" in settings:
            self.restore_queue_switch.setToggled(bool(settings["restore_queue_on_startup"]))
        if "restore_tabs_on_startup" in settings:
            self.restore_tabs_switch.setToggled(bool(settings["restore_tabs_on_startup"]))
    
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
        """Toggle browser state for an account (3-state cycle).
        
        - closed  → open (visible)
        - visible → hide (minimized, still running)
        - hidden  → show (restore window)
        """
        state = self.profiles_controller.get_debug_browser_state(email)
        
        if state == "closed":
            # Not running → Open browser
            print(f"[Settings] Opening browser for {email}...")
            self._update_browser_button_state(email, "visible")
            
            def on_state_change(changed_email, new_state):
                """Called by ProfilesController when browser state changes."""
                from PySide6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self, "_refresh_browser_buttons",
                    Qt.ConnectionType.QueuedConnection
                )
            
            success = self.profiles_controller.open_browser_for_debug(
                email, on_state_change=on_state_change
            )
            if not success:
                self._update_browser_button_state(email, "closed")
                from PySide6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self, "_on_debug_browser_failed",
                    Qt.ConnectionType.QueuedConnection
                )
            self._push_dev_console_status()
            
        elif state == "visible":
            # Running & visible → Hide (minimize, keep running)
            print(f"[Settings] Hiding browser for {email}...")
            self.profiles_controller.hide_debug_browser(email)
            self._update_browser_button_state(email, "hidden")
            self._push_dev_console_status()
            
        elif state == "hidden":
            # Running & hidden → Show (restore window)
            print(f"[Settings] Showing browser for {email}...")
            self.profiles_controller.show_debug_browser(email)
            self._update_browser_button_state(email, "visible")
            self._push_dev_console_status()
    
    def _update_browser_button_state(self, email: str, state: str):
        """Update button appearance for 3 states: visible/hidden/closed."""
        for row in range(self.profiles_table.rowCount()):
            email_item = self.profiles_table.item(row, 2)
            if email_item and email in email_item.text():
                btn = self.profiles_table.cellWidget(row, 3)
                if btn and isinstance(btn, QPushButton):
                    if state == "visible":
                        btn.setText("👁️ Visible")
                        btn.setToolTip("Browser is VISIBLE — click to HIDE")
                        btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {Theme.GREEN};
                                border: 1px solid {Theme.GREEN};
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background-color: {Theme.SAPPHIRE};
                            }}
                        """)
                    elif state == "hidden":
                        btn.setText("🔇 Hidden")
                        btn.setToolTip("Browser is HIDDEN (running in background) — click to SHOW")
                        btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {Theme.YELLOW};
                                border: 1px solid {Theme.YELLOW};
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                                color: {Theme.CRUST};
                            }}
                            QPushButton:hover {{
                                background-color: {Theme.PEACH};
                            }}
                        """)
                    else:  # closed
                        btn.setText("🌐 Open")
                        btn.setToolTip("Click to open browser with this profile")
                        btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {Theme.SURFACE2};
                                border: 1px solid {Theme.OVERLAY0};
                                border-radius: 6px;
                                font-size: 13px;
                                font-weight: bold;
                            }}
                            QPushButton:hover {{
                                background-color: {Theme.BLUE};
                                border-color: {Theme.BLUE};
                            }}
                        """)
                break
    
    @Slot()
    def _refresh_browser_buttons(self):
        """Refresh all browser toggle buttons from actual ProfilesController state.
        
        Called from main thread via QMetaObject when a browser state changes.
        """
        for row in range(self.profiles_table.rowCount()):
            email_item = self.profiles_table.item(row, 2)
            if not email_item:
                continue
            # Extract raw email (remove emoji prefix like 🔑 or 🔓)
            text = email_item.text()
            parts = text.split(' ', 1)
            email = parts[-1].strip() if len(parts) > 1 else text.strip()
            
            state = self.profiles_controller.get_debug_browser_state(email)
            self._update_browser_button_state(email, state)
        
        self._push_dev_console_status()
    
    def _push_dev_console_status(self):
        """Push browser status and session data to DevConsole via controller."""
        if self.controller and hasattr(self.controller, '_push_browser_status'):
            self.controller._push_browser_status()
        if self.controller and hasattr(self.controller, '_push_session_data'):
            self.controller._push_session_data()
    
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
        self._push_dev_console_status()  # Refresh DevConsole panels
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
    
    def _on_restart_browser(self, email: str):
        """Kill and relaunch Chrome browser for this account."""
        import threading
        
        reply = QMessageBox.question(
            self, "Restart Browser",
            f"Kill and relaunch Chrome for:\n{email}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        print(f"[Settings] 🔁 Restarting browser for: {email}")
        self._update_row_status(email, "⏳ Restarting...", "...")
        self.setEnabled(False)
        
        def _do_restart():
            ok = False
            if self.controller:
                ok = self.controller.restart_browser_for(email)
            
            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self, "_on_browser_restarted",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, email),
                Q_ARG(str, "ok" if ok else "fail"),
            )
        
        thread = threading.Thread(target=_do_restart, daemon=True)
        thread.start()
    
    @Slot(str, str)
    def _on_browser_restarted(self, email: str, result: str):
        """Called when browser restart completes (from background thread)."""
        self.setEnabled(True)
        self._refresh_profiles_table()
        if result == "ok":
            QMessageBox.information(
                self, "Restart Browser",
                f"✅ Browser restarted for {email}"
            )
        else:
            QMessageBox.warning(
                self, "Restart Browser",
                f"❌ Failed to restart browser for {email}"
            )
    
    def _on_reload_app(self):
        """Restart the entire Python application process."""
        reply = QMessageBox.question(
            self, "Reload App",
            "Restart application with latest code?\n\n"
            "• All running tasks will stop\n"
            "• Chrome browsers will keep running\n"
            "• App will relaunch automatically\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        if self.controller:
            self.controller.hot_reload_app()
    

    
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
        
        action = "Please re-login manually using the Browser button." if reason != "credits_api_failed" else "Try refreshing again later."
        QMessageBox.warning(
            self,
            f"⚠️ Session Problem - {email}",
            f"{msg}\n\n{action}"
        )
    
    def _on_save_password(self, email: str):
        """Show dialog to save/update password for an account."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox
        
        try:
            from core.credentials_manager import get_credentials_manager
            creds_manager = get_credentials_manager()
        except ImportError as e:
            QMessageBox.warning(self, "Error", f"Credentials manager not available: {e}")
            return
        
        # Check existing credentials
        existing = creds_manager.load_credentials_for(email)
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"🔑 Save Password — {email}")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        form = QFormLayout()
        
        email_label = QLineEdit(email)
        email_label.setReadOnly(True)
        email_label.setStyleSheet("color: #888;")
        
        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_input.setPlaceholderText("Enter Google account password")
        if existing:
            password_input.setText(existing.get("password", ""))
        
        form.addRow("📧 Email:", email_label)
        form.addRow("🔑 Password:", password_input)
        layout.addLayout(form)
        
        info = QLabel(
            "⚠️ Password is encrypted locally (Fernet).\n"
            "Used for auto re-login when profile needs reset."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        password = password_input.text()
        if not password:
            QMessageBox.warning(self, "Error", "Password cannot be empty.")
            return
        
        if creds_manager.save_credentials(email, password):
            QMessageBox.information(self, "Saved", f"✅ Password saved for {email}")
            self._refresh_profiles_table()  # Update 🔑/🔓 icon
        else:
            QMessageBox.warning(self, "Error", "Failed to save credentials.")
    
    
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
        """Delete the specified profile after confirmation.
        
        Full cleanup:
        1. profiles_controller.remove_profile() — kills Chrome, deletes browser folder,
           credentials, tokens.json entry, removes from _profiles list
        2. controller.remove_account() — removes from runtime engine (_multi_account),
           unregisters from session_monitor and refresh_manager
        3. Push updated data to Dev Console (session + browser panels)
        """
        reply = QMessageBox.question(
            self, 
            "Delete Profile",
            f"Are you sure you want to delete profile '{email}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            print(f"[Settings] Deleting profile: {email}")
            
            # Step 1: Remove profile (Chrome, browser folder, credentials, tokens.json)
            self.profiles_controller.remove_profile(email)
            
            # Step 2: Remove from runtime engine (multi_account, monitors)
            if self.controller and hasattr(self.controller, 'remove_account'):
                try:
                    self.controller.remove_account(email)
                    print(f"[Settings] ✅ Removed {email} from runtime engine")
                except Exception as e:
                    print(f"[Settings] ⚠️ remove_account: {e}")
            
            # Step 3: Refresh UI immediately
            self._refresh_profiles_table()
            
            # Step 4: Push updated data to Dev Console
            if self.controller:
                try:
                    if hasattr(self.controller, '_push_session_data'):
                        self.controller._push_session_data()
                    if hasattr(self.controller, '_push_browser_status'):
                        self.controller._push_browser_status()
                except Exception as e:
                    print(f"[Settings] ⚠️ Dev Console refresh: {e}")
    
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
            "image_quality": self.setting_combos.get("Image Quality").currentText() if "Image Quality" in self.setting_combos else "",
            "output_folder": self.output_folder_entry.text(),
            "include_timestamp": self.output_toggles.get("Include timestamp in filename").isChecked() if "Include timestamp in filename" in self.output_toggles else False,
            "include_quality": self.output_toggles.get("Include quality in filename").isChecked() if "Include quality in filename" in self.output_toggles else False,
            "auto_start_queue": self.output_toggles.get("Auto-start queue when adding").isChecked() if "Auto-start queue when adding" in self.output_toggles else False,
            "pause_on_error": self.output_toggles.get("Pause on error").isChecked() if "Pause on error" in self.output_toggles else False,
            "continuation_enabled": self.cont_switch.isToggled(),
            "extract_point_ms": self._parse_extract_point(self.extract_menu.currentText()),
            # Enhancer Image (3-toggle system)
            "enhance_context_menu": self._enhance_context_toggle.isToggled() if hasattr(self, '_enhance_context_toggle') else True,
            "enhance_library": self._enhance_library_toggle.isToggled() if hasattr(self, '_enhance_library_toggle') else True,
            "enhance_auto_continuation": self._enhance_auto_toggle.isToggled() if hasattr(self, '_enhance_auto_toggle') else False,
            "language": self.lang_menu.currentText(),
            # Worker Settings (defaults for new accounts)
            "retry_count": self.retry_count.value(),
            "request_timeout": self.request_timeout.value(),
            # Anti-Detect Spam
            "anti_detect_enabled": self.anti_detect_switch.isToggled(),
            "anti_detect_delay_min": self.anti_detect_delay_min.value(),
            "anti_detect_delay_max": self.anti_detect_delay_max.value(),
            # Session & Data
            "restore_queue_on_startup": self.restore_queue_switch.isToggled(),
            "restore_tabs_on_startup": self.restore_tabs_switch.isToggled(),
        }
