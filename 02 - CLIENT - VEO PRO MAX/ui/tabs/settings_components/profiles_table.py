"""
Profiles Table mixin — Chrome Profiles table UI and data refresh.

Extracted from tab_settings.py.  All methods operate on shared `self`
attributes initialised by TabSettings.__init__.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QSpinBox,
)
from PySide6.QtCore import Qt, Slot

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class SettingsProfilesMixin:
    """Chrome Profiles table — create, refresh, and row helpers.

    ⚠️ Cross-mixin dependency: This mixin builds UI that connects to
    handlers defined in SettingsBrowserControlsMixin:
    _on_toggle_account, _on_slots_changed, _on_save_password,
    _on_refresh_session, _on_toggle_browser_visibility,
    _on_restart_browser, _on_reload_extension, _on_delete_profile,
    _on_add_profile_browser
    """

    def _create_profiles_section(self) -> QWidget:
        """Create Chrome Profiles section - per TAB_07_SETTINGS.md spec.

        9 columns: ✓, #, Email, Plan, Credits, Status, Total Output, Ext, Retry, Actions
        """
        from ui.tabs.tab_settings import ToggleSwitch

        section, layout = self._create_section("🌐 Chrome Profiles (Account Manager)")

        # Create QTableWidget with 10 columns
        self.profiles_table = QTableWidget()
        self.profiles_table.setColumnCount(10)
        self.profiles_table.setHorizontalHeaderLabels([
            "✓", "#", "Email", "Plan", "Credits", "Status", "Total Output", "Ext", "Retry", "Actions"
        ])

        # Set column widths per docs spec
        header = self.profiles_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # ✓
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # #
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Email
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # Plan
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Credits
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Status
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)    # Total Output
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)    # Ext
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)    # Retry
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)    # Actions

        self.profiles_table.setColumnWidth(0, 80)   # ✓
        self.profiles_table.setColumnWidth(1, 40)   # #
        self.profiles_table.setColumnWidth(3, 80)   # Plan
        self.profiles_table.setColumnWidth(4, 80)   # Credits
        self.profiles_table.setColumnWidth(5, 110)  # Status
        self.profiles_table.setColumnWidth(6, 95)   # Total Output - SpinBox 0-20
        self.profiles_table.setColumnWidth(7, 50)   # Ext - emoji status
        self.profiles_table.setColumnWidth(8, 50)   # Retry - number
        self.profiles_table.setColumnWidth(9, 290)  # Actions - 6 buttons

        self.profiles_table.setMinimumHeight(120)
        self.profiles_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Theme.SURFACE2};
                border: none;
                border-radius: 4px;
                gridline-color: {Theme.BORDER};
            }}
            QHeaderView::section {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                font-weight: bold;
                font-size: 12px;
                padding: 6px 4px;
                border: none;
                border-bottom: 2px solid {Theme.BORDER};
                border-right: 1px solid {Theme.BORDER};
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
        """)
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
        browser_btn = QPushButton("🌐 Add Profile (Browser Login)")
        browser_btn.setToolTip("Login in browser. Plan/Credits available immediately.")
        browser_btn.setFixedHeight(32)
        browser_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.GREEN};
                color: #1e1e2e;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 16px;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {Theme.GREEN};
                opacity: 0.9;
            }}
        """)
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
            if not email_item:
                continue
            # P3 fix: strip credential indicator prefix before matching
            email_text = email_item.text().strip()
            for prefix in ("🔑 ", "🔓 "):
                if email_text.startswith(prefix):
                    email_text = email_text[len(prefix):].strip()
                    break
            if email_text == email:
                # Update Status (col 5)
                status_item = self.profiles_table.item(row, 5)
                if status_item:
                    status_item.setText(status)

                # Update Credits if provided (col 4)
                if credits is not None:
                    credits_item = self.profiles_table.item(row, 4)
                    if credits_item:
                        credits_item.setText(credits)

                # Update Plan to show loading (col 3)
                if credits is not None:
                    plan_item = self.profiles_table.item(row, 3)
                    if plan_item:
                        plan_item.setText("⏳ Wait")

                break

    @Slot()
    def _refresh_profiles_table(self):
        """Refresh profiles table from controller data."""
        from ui.tabs.tab_settings import ToggleSwitch

        self.profiles_table.setRowCount(0)

        # Get profiles from ProfilesController
        accounts = self.profiles_controller.get_all_profiles()

        # If no profiles exist, show empty state message
        if not accounts:
            placeholder = QTableWidgetItem("No profiles added. Click '🌐 Add Account' to add.")
            self.profiles_table.insertRow(0)
            self.profiles_table.setSpan(0, 0, 1, 10)  # 10 columns
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

            # Plan (col 3) - tier_display already formatted - centered
            plan_item = QTableWidgetItem(acc.get('tier', '👤 Free'))
            plan_item.setFlags(plan_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            plan_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 3, plan_item)

            # Credits (col 4) - credits_display already formatted - centered
            credits_item = QTableWidgetItem(acc.get('credits', 'N/A'))
            credits_item.setFlags(credits_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            credits_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 4, credits_item)

            # Status (col 5) - Uses enhanced status_display from ChromeProfile - centered
            # Status values: 🔴 Expired, 🟠 Expiring, 🟢 Login, 🟢 Ready
            status = acc.get('status', '🟢 Login')
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 5, status_item)

            # Get email for action handlers
            email = acc.get('email', '')

            # Total Output SpinBox (col 6) — per-account concurrent worker limit
            slots_spin = QSpinBox()
            slots_spin.setRange(0, 20)
            slots_spin.setValue(acc.get('max_workers', acc.get('max_slots', 20)))
            slots_spin.setToolTip(
                "Số output/prompt xử lý đồng thời cho tài khoản này\n"
                "• 0 = TẮT (tài khoản không xử lý)\n"
                "• 1 output/prompt = 1 video một lúc\n"
                "• 20 output/prompt = tối đa song song"
            )
            slots_spin.setFixedWidth(72)
            # Explicit style: ensure number is visible on dark table background
            slots_spin.setStyleSheet(f"""
                QSpinBox {{
                    background-color: {Theme.SURFACE0};
                    color: {Theme.TEXT};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 3px;
                    padding: 2px 4px;
                    padding-right: 18px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QSpinBox:focus {{
                    border-color: {Theme.BLUE};
                }}
                QSpinBox::up-button {{
                    width: 20px;
                    border-left: 1px solid {Theme.BORDER};
                    background-color: {Theme.SURFACE1};
                    border-top-right-radius: 2px;
                }}
                QSpinBox::down-button {{
                    width: 20px;
                    border-left: 1px solid {Theme.BORDER};
                    background-color: {Theme.SURFACE1};
                    border-bottom-right-radius: 2px;
                }}
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                    background-color: {Theme.SURFACE2};
                }}
            """)
            slots_spin.valueChanged.connect(
                lambda value, e=email: self._on_slots_changed(e, value)
            )
            self.profiles_table.setCellWidget(actual_row, 6, slots_spin)

            # Extension status (col 7) — 3-state: 🟢 has headers, 🟡 connecting, 🔴 disconnected
            ext_connected = False
            ext_has_headers = False
            try:
                if self.controller and hasattr(self.controller, 'extension_bridge'):
                    bridge = self.controller.extension_bridge
                    ext_connected = bridge.is_connected(email)
                    if ext_connected:
                        headers = bridge.get_cached_headers(email, max_age_seconds=300)
                        ext_has_headers = bool(headers)
            except Exception:
                pass
            if ext_has_headers:
                ext_icon = "🟢"
                ext_tip = "Extension connected — headers ready"
            elif ext_connected:
                ext_icon = "🟡"
                ext_tip = "Extension connecting — waiting for headers..."
            else:
                ext_icon = "🔴"
                ext_tip = "Extension not connected"
            ext_item = QTableWidgetItem(ext_icon)
            ext_item.setFlags(ext_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ext_item.setToolTip(ext_tip)
            self.profiles_table.setItem(actual_row, 7, ext_item)

            # Retry count (col 8) — shows retry_count from settings
            retry_count = acc.get('retry_count', 3)
            retry_item = QTableWidgetItem(str(retry_count))
            retry_item.setFlags(retry_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            retry_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            retry_item.setToolTip("Max retries on failure (0 = no retries, task fails immediately)")
            self.profiles_table.setItem(actual_row, 8, retry_item)

            # Actions buttons (col 9)
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

            # Show/Hide Browser toggle button
            browser_state = "hidden"
            if hasattr(self, 'profiles_controller') and self.profiles_controller:
                browser_state = self.profiles_controller.get_debug_browser_state(email)
            is_visible = (browser_state == "visible")
            toggle_text = "👁️" if is_visible else "🌐"
            toggle_color = Theme.GREEN if is_visible else Theme.YELLOW
            toggle_tip = "Browser VISIBLE — click to HIDE" if is_visible else "Browser HIDDEN — click to SHOW"
            toggle_btn = QPushButton(toggle_text)
            toggle_btn.setFixedSize(32, 32)
            toggle_btn.setToolTip(toggle_tip)
            toggle_btn.setObjectName(f"toggle_vis_{email}")
            toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {toggle_color};
                    border: 1px solid rgba(255,255,255,0.15);
                    border-radius: 6px;
                    font-size: 15px;
                    padding: 0px;
                    {f'color: {Theme.CRUST};' if not is_visible else ''}
                }}
                QPushButton:hover {{
                    border: 1px solid rgba(255,255,255,0.5);
                }}
            """)
            toggle_btn.clicked.connect(lambda checked, e=email: self._on_toggle_browser_visibility(e))
            actions_layout.addWidget(toggle_btn)

            # Restart Browser button
            restart_btn = _action_btn("🔁", "Restart Browser (Kill + Relaunch)", "#FF6B00")
            restart_btn.clicked.connect(lambda checked, e=email: self._on_restart_browser(e))
            actions_layout.addWidget(restart_btn)

            # Reload Extension button
            ext_btn = _action_btn("🧩", "Reload Extension (hot-reload from disk)", "#9B59B6")
            ext_btn.clicked.connect(lambda checked, e=email: self._on_reload_extension(e))
            actions_layout.addWidget(ext_btn)

            # Delete button
            delete_btn = _action_btn("🗑️", "Delete Profile", Theme.RED)
            delete_btn.clicked.connect(lambda checked, e=email: self._on_delete_profile(e))
            actions_layout.addWidget(delete_btn)

            self.profiles_table.setCellWidget(actual_row, 9, actions_widget)

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
        # Use min/max height instead of fixedHeight so section can auto-expand
        min_h = max(total_height, 120)
        tbl.setMinimumHeight(min_h)
        tbl.setMaximumHeight(max(min_h, 700))  # Cap at 700px to avoid overwhelming UI

    # _create_profile_row — REMOVED (dead code from pre-componentization)
    # _create_accounts_section — REMOVED (replaced by Chrome Profiles table)

    def _refresh_ext_column(self):
        """Lightweight periodic refresh of Extension status column (col 7) only.

        Runs every 5s via QTimer. Does NOT rebuild the table — just updates
        the Ext icon cells using a composite check:
        - 🟢 WS bridge connected + headers ready
        - 🟡 WS bridge connected, waiting for headers
        - 🟠 Extension loaded (CDP) but WS bridge not connected
        - 🔴 Extension not loaded at all
        """
        if not self.controller or not hasattr(self.controller, 'extension_bridge'):
            return

        bridge = self.controller.extension_bridge
        if not bridge:
            return

        # Get CDP port mapping for CDP-level checks
        pc = getattr(self.controller, '_profiles_controller', None)
        debug_browsers = getattr(pc, '_debug_browsers', {}) if pc else {}

        for row in range(self.profiles_table.rowCount()):
            email_item = self.profiles_table.item(row, 2)  # Email column
            if not email_item:
                continue

            # Extract raw email from display text (may have 🔑 or 🔓 prefix)
            email_text = email_item.text().strip()
            # Remove credential indicator prefix if present
            for prefix in ("🔑 ", "🔓 "):
                if email_text.startswith(prefix):
                    email_text = email_text[len(prefix):].strip()
                    break

            ext_connected = False
            ext_has_headers = False
            cdp_loaded = False
            try:
                ext_connected = bridge.is_connected(email_text)
                if ext_connected:
                    headers = bridge.get_cached_headers(email_text, max_age_seconds=300)
                    ext_has_headers = bool(headers)
                else:
                    # WS bridge not connected — check CDP to distinguish
                    # "extension loaded but bridge disconnected" vs "extension missing"
                    entry = debug_browsers.get(email_text, {})
                    cdp_port = entry.get("cdp_port")
                    if cdp_port:
                        from core.extension_manager import is_extension_loaded
                        cdp_loaded = is_extension_loaded(cdp_port)
            except Exception:
                pass

            ext_item = self.profiles_table.item(row, 7)
            if ext_item:
                if ext_has_headers:
                    new_icon = "🟢"
                    new_tip = "Extension connected — headers ready"
                elif ext_connected:
                    new_icon = "🟡"
                    new_tip = "Extension connecting — waiting for headers..."
                elif cdp_loaded:
                    new_icon = "🟠"
                    new_tip = "Extension loaded but bridge not connected"
                else:
                    new_icon = "🔴"
                    new_tip = "Extension not loaded"
                if ext_item.text() != new_icon:
                    ext_item.setText(new_icon)
                    ext_item.setToolTip(new_tip)

    # _refresh_accounts — REMOVED (dead code, referenced non-existent self.accounts_list)
    # _create_account_row — REMOVED (dead code from pre-componentization)
    # _on_add_account — REMOVED (dead code, referenced non-existent self.account_email_input)
    # _on_remove_account — REMOVED (dead code, called removed _refresh_accounts)
