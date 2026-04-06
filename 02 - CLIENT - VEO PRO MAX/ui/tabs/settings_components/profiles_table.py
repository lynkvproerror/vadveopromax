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
from config.i18n import t


class SettingsProfilesMixin:
    """Chrome Profiles table — create, refresh, and row helpers.

    ⚠️ Cross-mixin dependency: This mixin builds UI that connects to
    handlers defined in SettingsBrowserControlsMixin:
    _on_toggle_account, _on_slots_changed, _on_save_password,
    _on_refresh_session, _on_toggle_browser_visibility,
    _on_reload_extension, _on_delete_profile,
    _on_add_profile_browser,
    _on_bulk_add_profiles
    """

    def _create_profiles_section(self) -> QWidget:
        """Create Chrome Profiles section.

        12 columns: ✓, #, Email, API Key, Plan, Credits, Status, Workers, LP, Ext, Actions
        """
        from ui.tabs.tab_settings import ToggleSwitch

        section, layout = self._create_section(t("profiles.section_title"))

        # Email privacy state — load from saved settings
        from config.settings import get_settings
        self._emails_hidden = get_settings().hide_emails

        # Create QTableWidget with 11 columns
        self.profiles_table = QTableWidget()
        self.profiles_table.setColumnCount(11)
        self.profiles_table.setHorizontalHeaderLabels([
            t("profiles.columns.toggle"), t("profiles.columns.num"),
            t("profiles.columns.email"), t("profiles.columns.api_key"),
            t("profiles.columns.plan"),
            t("profiles.columns.credits"), t("profiles.columns.status"),
            "Workers", "LP", t("profiles.columns.ext"),
            t("profiles.columns.actions")
        ])

        # Set column widths
        header = self.profiles_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # ✓
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # #
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Email
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # API Key
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Plan
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Credits
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)    # Status
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)    # Workers
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)    # LP
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Fixed)    # Ext
        header.setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)   # Actions

        self.profiles_table.setColumnWidth(0, 80)   # ✓
        self.profiles_table.setColumnWidth(1, 40)   # #
        self.profiles_table.setColumnWidth(3, 50)   # API Key
        self.profiles_table.setColumnWidth(4, 80)   # Plan
        self.profiles_table.setColumnWidth(5, 80)   # Credits
        self.profiles_table.setColumnWidth(6, 110)  # Status
        self.profiles_table.setColumnWidth(7, 75)   # Workers - SpinBox 0-20
        self.profiles_table.setColumnWidth(8, 75)   # LP - SpinBox 0-8
        self.profiles_table.setColumnWidth(9, 50)   # Ext - emoji status
        self.profiles_table.setColumnWidth(10, 290) # Actions - 6 buttons

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
        browser_btn = QPushButton(t("profiles.add_profile"))
        browser_btn.setToolTip(t("tooltips.login_tooltip"))
        browser_btn.setFixedHeight(32)
        browser_btn.setProperty("variant", "success")
        browser_btn.clicked.connect(self._on_add_profile_browser)
        btn_layout.addWidget(browser_btn)

        # Bulk Add — paste email|password list
        bulk_btn = QPushButton(t("profiles.bulk_add"))
        bulk_btn.setToolTip(t("bulk_add.info"))
        bulk_btn.setFixedHeight(32)
        bulk_btn.clicked.connect(self._on_bulk_add_profiles)
        btn_layout.addWidget(bulk_btn)

        btn_layout.addStretch()

        # Email hide/show toggle button
        self._email_toggle_btn = QPushButton(t("profiles.show_email") if self._emails_hidden else t("profiles.hide_email"))
        self._email_toggle_btn.setFixedHeight(32)
        self._email_toggle_btn.setToolTip(t("profiles.show_email") if self._emails_hidden else t("profiles.hide_email"))
        self._email_toggle_btn.setProperty("variant", "secondary")
        self._email_toggle_btn.clicked.connect(self._toggle_email_visibility)
        btn_layout.addWidget(self._email_toggle_btn)
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
            # Use authoritative UserRole data (works with masked emails)
            item_email = email_item.data(Qt.ItemDataRole.UserRole)
            if item_email == email:
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
                        plan_item.setText(t("pipeline_status.wait"))

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
            placeholder = QTableWidgetItem(t("profiles.empty_state"))
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
            toggle.setToolTip(t("tooltips.toggle_account"))
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
            display_email = self._mask_email(email_text) if self._emails_hidden else email_text
            email_item = QTableWidgetItem(f"{cred_icon} {display_email}")
            email_item.setToolTip(cred_tip)
            email_item.setData(Qt.ItemDataRole.UserRole, email_text)  # Store real email
            email_item.setFlags(email_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.profiles_table.setItem(actual_row, 2, email_item)

            # API Key (col 3) — per-profile Gemini key status (emoji only)
            api_key_text = "❌"
            api_key_tip = t("profiles.no_api_key")
            try:
                from services.gemini_key_manager import GeminiKeyManager
                _km = GeminiKeyManager()
                _key = _km.get_key(email_text)
                if _key and _key.startswith("AIza"):
                    api_key_text = "✅"
                    api_key_tip = f"Key: {_key[:10]}...{_key[-6:]}"
            except Exception:
                pass
            key_item = QTableWidgetItem(api_key_text)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            key_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            key_item.setToolTip(api_key_tip)
            self.profiles_table.setItem(actual_row, 3, key_item)

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
            # Status values: 🔴 Expired, 🟠 Expiring, 🟢 Login, 🟢 Ready
            status = acc.get('status', '🟢 Login')
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.profiles_table.setItem(actual_row, 6, status_item)

            # Get email for action handlers
            email = acc.get('email', '')

            # Total Output SpinBox (col 7) — per-account concurrent worker limit
            slots_spin = QSpinBox()
            # Dynamic max from server (default=20, only server can raise above 20)
            _max_wk = 20
            try:
                if self.controller and hasattr(self.controller, '_permissions'):
                    server_wk = self.controller._permissions.limits.max_workers_per_account
                    if server_wk < 0:
                        _max_wk = 20   # -1 unlimited → cap at 20 (server must set explicit value to go higher)
                    else:
                        _max_wk = max(1, server_wk)  # Anti-patch: never allow 0 or negative max
            except Exception:
                pass
            slots_spin.setRange(0, _max_wk)  # min=0 (OFF), max=server-driven
            slots_spin.setValue(min(acc.get('max_workers', acc.get('max_slots', 20)), _max_wk))
            slots_spin.setToolTip(
                f"Số output/prompt xử lý đồng thời cho tài khoản này\n"
                f"• 0 = TẮT (tài khoản không xử lý)\n"
                f"• 1 output/prompt = 1 video một lúc\n"
                f"• {_max_wk} output/prompt = tối đa song song"
            )
            slots_spin.setFixedWidth(65)
            # Explicit style: ensure number is visible on dark table background
            slots_spin.setStyleSheet(f"""
                QSpinBox {{
                    background-color: {Theme.SURFACE1};
                    color: {Theme.TEXT};
                    border: none;
                    border-radius: 4px;
                    padding: 2px 4px;
                    padding-right: 18px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QSpinBox:focus {{
                    border: 1px solid {Theme.GREEN};
                }}
                QSpinBox::up-button {{
                    width: 20px;
                    border: none;
                    background-color: {Theme.SURFACE2};
                    border-top-right-radius: 3px;
                }}
                QSpinBox::down-button {{
                    width: 20px;
                    border: none;
                    background-color: {Theme.SURFACE2};
                    border-bottom-right-radius: 3px;
                }}
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                    background-color: {Theme.LAVENDER};
                }}
            """)
            slots_spin.valueChanged.connect(
                lambda value, e=email: self._on_slots_changed(e, value)
            )
            self.profiles_table.setCellWidget(actual_row, 7, slots_spin)

            # LP Workers SpinBox (col 8) — per-account LP concurrent worker limit
            lp_spin = QSpinBox()
            _max_lp = 20  # LP max (same as total workers)
            lp_spin.setRange(0, _max_lp)
            lp_spin.setValue(min(acc.get('max_workers_lp', 8), _max_lp))
            lp_spin.setToolTip(
                f"Số LP worker tối đa cho tài khoản này\n"
                f"• LP = Low Priority (Fast Low Priority model)\n"
                f"• 0 = TẮT LP\n"
                f"• {_max_lp} = tối đa LP song song"
            )
            lp_spin.setFixedWidth(65)
            lp_spin.setStyleSheet(f"""
                QSpinBox {{
                    background-color: {Theme.SURFACE1};
                    color: {Theme.TEXT};
                    border: none;
                    border-radius: 4px;
                    padding: 2px 4px;
                    padding-right: 18px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QSpinBox:focus {{
                    border: 1px solid {Theme.LAVENDER};
                }}
                QSpinBox::up-button {{
                    width: 20px;
                    border: none;
                    background-color: {Theme.SURFACE2};
                    border-top-right-radius: 3px;
                }}
                QSpinBox::down-button {{
                    width: 20px;
                    border: none;
                    background-color: {Theme.SURFACE2};
                    border-bottom-right-radius: 3px;
                }}
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                    background-color: {Theme.LAVENDER};
                }}
            """)
            lp_spin.valueChanged.connect(
                lambda value, e=email: self._on_lp_slots_changed(e, value)
            )
            self.profiles_table.setCellWidget(actual_row, 8, lp_spin)

            # Extension status (col 9) — app-centric delivery state
            ext_icon, ext_tip = self._get_ext_ui_state(email)
            ext_item = QTableWidgetItem(ext_icon)
            ext_item.setFlags(ext_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            ext_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ext_item.setToolTip(ext_tip)
            self.profiles_table.setItem(actual_row, 9, ext_item)

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

            # Paste Gemini API Key button
            gemini_btn = _action_btn("🤖", t("profiles.actions_tooltip.gemini_key"), Theme.TEAL if hasattr(Theme, 'TEAL') else "#2ecc71")
            gemini_btn.clicked.connect(lambda checked, e=email: self._on_paste_gemini_key(e))
            actions_layout.addWidget(gemini_btn)

            # Save Password button
            pwd_btn = _action_btn("🔑", t("profiles.actions_tooltip.save_password"), Theme.YELLOW)
            pwd_btn.clicked.connect(lambda checked, e=email: self._on_save_password(e))
            actions_layout.addWidget(pwd_btn)

            # Refresh button
            refresh_btn = _action_btn("🔃", t("profiles.actions_tooltip.refresh_session"), Theme.BLUE)
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
            toggle_btn.setMinimumSize(32, 32)
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


            # Reload Extension button
            ext_btn = _action_btn("🧩", "Reload Extension", "#9B59B6")
            ext_btn.clicked.connect(lambda checked, e=email: self._on_reload_extension(e))
            actions_layout.addWidget(ext_btn)

            # Delete button
            delete_btn = _action_btn("🗑️", t("profiles.actions_tooltip.delete_profile"), Theme.RED)
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
        # Use min/max height instead of fixedHeight so section can auto-expand
        min_h = max(total_height, 120)
        tbl.setMinimumHeight(min_h)
        tbl.setMaximumHeight(max(min_h, 700))  # Cap at 700px to avoid overwhelming UI

    # _create_profile_row — REMOVED (dead code from pre-componentization)
    # _create_accounts_section — REMOVED (replaced by Chrome Profiles table)

    @staticmethod
    def _mask_email(email: str) -> str:
        """Mask email for privacy: user@domain.com → u***@domain.com"""
        if "@" not in email:
            return "***"
        local, domain = email.split("@", 1)
        if len(local) <= 1:
            masked_local = "*"
        else:
            masked_local = local[0] + "***"
        return f"{masked_local}@{domain}"

    def _toggle_email_visibility(self):
        """Toggle email display between real and masked (***) in the table."""
        self._emails_hidden = not self._emails_hidden

        # Persist to settings
        try:
            from config.settings import get_settings, save_settings
            get_settings().hide_emails = self._emails_hidden
            save_settings()
        except Exception:
            pass

        # Update button text
        self._email_toggle_btn.setText(t("profiles.show_email") if self._emails_hidden else t("profiles.hide_email"))
        self._email_toggle_btn.setToolTip(
            t("profiles.show_email") if self._emails_hidden else t("profiles.hide_email")
        )

        # Update all email cells (col 2) — block signals to avoid side effects
        self.profiles_table.blockSignals(True)
        try:
            for row in range(self.profiles_table.rowCount()):
                email_item = self.profiles_table.item(row, 2)
                if not email_item:
                    continue
                real_email = email_item.data(Qt.ItemDataRole.UserRole)
                if not real_email:
                    continue  # placeholder row

                # Extract credential icon prefix
                current = email_item.text().strip()
                cred_icon = ""
                for prefix in ("🔑 ", "🔓 "):
                    if current.startswith(prefix):
                        cred_icon = prefix.rstrip() 
                        break

                display = self._mask_email(real_email) if self._emails_hidden else real_email
                email_item.setText(f"{cred_icon} {display}" if cred_icon else display)
        finally:
            self.profiles_table.blockSignals(False)

    def _get_ext_ui_state(self, email: str) -> tuple[str, str]:
        """Return `(icon, tooltip)` for app-centric extension delivery state."""
        bridge = None
        if self.controller and hasattr(self.controller, 'extension_bridge'):
            bridge = self.controller.extension_bridge

        snapshot = {
            "connected": False,
            "headers_ready": False,
            "headers_any": False,
            "last_headers_age_seconds": None,
        }
        if bridge:
            try:
                snapshot.update(bridge.get_delivery_status(email, max_age_seconds=300))
            except Exception:
                pass

        cdp_loaded = False
        try:
            pc = getattr(self.controller, '_profiles_controller', None)
            debug_browsers = getattr(pc, '_debug_browsers', {}) if pc else {}
            entry = debug_browsers.get(email, {})
            cdp_port = entry.get("cdp_port")
            if cdp_port:
                from core.extension_manager import is_extension_loaded
                cdp_loaded = bool(is_extension_loaded(cdp_port))
        except Exception:
            pass

        if snapshot["headers_ready"]:
            icon = "🟢"
            tip = "Extension connected — headers delivered to app"
        elif snapshot["connected"]:
            icon = "🟡"
            age = snapshot.get("last_headers_age_seconds")
            if snapshot["headers_any"] and age is not None:
                tip = (
                    f"Bridge connected to app, but cached headers are stale ({int(age)}s old) — "
                    "waiting for fresh delivery"
                )
            else:
                tip = "Bridge connected to app — waiting for first headers delivery"
        elif cdp_loaded:
            icon = "🟠"
            tip = (
                "Extension loaded in Chrome, but bridge to app is disconnected.\n"
                "Popup may show headers captured locally, but app has not received live headers yet."
            )
        elif snapshot["headers_any"]:
            icon = "🟠"
            tip = "App only has stale headers from an earlier session; live bridge is currently disconnected."
        else:
            icon = "🔴"
            tip = "Extension not loaded"

        if not snapshot["headers_ready"] and bridge:
            try:
                diag = bridge.get_connection_diagnosis()
                if diag.get('severity') in ('warning', 'error'):
                    tip = f"{tip}\n\n{diag['reason']}\n\n💡 {diag['fix']}"
            except Exception:
                pass

        return icon, tip

    def _refresh_ext_column(self):
        """Lightweight periodic refresh of Extension status column (col 8) only.

        Runs every 5s via QTimer. Does NOT rebuild the table — just updates
        the Ext icon cells using app-centric delivery states:
        - 🟢 headers already delivered into app
        - 🟡 bridge connected, waiting for first/fresh headers
        - 🟠 extension loaded in Chrome or stale cached headers, but live bridge not ready
        - 🔴 extension not loaded at all
        """
        if not self.controller or not hasattr(self.controller, 'extension_bridge'):
            return

        bridge = self.controller.extension_bridge
        if not bridge:
            return

        for row in range(self.profiles_table.rowCount()):
            email_item = self.profiles_table.item(row, 2)  # Email column
            if not email_item:
                continue

            # Get real email from UserRole (not display text, which may be masked)
            email_text = email_item.data(Qt.ItemDataRole.UserRole)
            if not email_text:
                continue

            ext_item = self.profiles_table.item(row, 9)
            if ext_item:
                new_icon, new_tip = self._get_ext_ui_state(email_text)
                if ext_item.text() != new_icon:
                    ext_item.setText(new_icon)
                ext_item.setToolTip(new_tip)

    # _refresh_accounts — REMOVED (dead code, referenced non-existent self.accounts_list)
    # _create_account_row — REMOVED (dead code from pre-componentization)
    # _on_add_account — REMOVED (dead code, referenced non-existent self.account_email_input)
    # _on_remove_account — REMOVED (dead code, called removed _refresh_accounts)
