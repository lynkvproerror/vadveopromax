"""
Browser Controls mixin — browser visibility, login, restart, extension reload,
profile CRUD, session refresh, password management.

Extracted from tab_settings.py.  All methods operate on shared `self`
attributes initialised by TabSettings.__init__.
"""

from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel,
)
from ui.popups import show_info, show_warning, show_confirm
from PySide6.QtCore import Slot

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class SettingsBrowserControlsMixin:
    """Browser visibility, login flows, restart, extension, profile CRUD."""

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
            self._update_visibility_toggle_btn(email, state)

        self._push_dev_console_status()

    def _on_toggle_browser_visibility(self, email: str):
        """Toggle browser visibility for an account.

        3-state: closed → open (visible), visible → hide, hidden → show.
        """
        state = self.profiles_controller.get_debug_browser_state(email)

        if state == "closed":
            # Not running → Open browser
            print(f"[Settings] 🌐 Opening browser for {email}...")
            self._update_visibility_toggle_btn(email, "visible")

            def on_state_change(changed_email, new_state):
                from PySide6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self, "_refresh_browser_buttons",
                    Qt.ConnectionType.QueuedConnection
                )

            success = self.profiles_controller.open_browser_for_debug(
                email, on_state_change=on_state_change
            )
            if not success:
                self._update_visibility_toggle_btn(email, "closed")
                from PySide6.QtCore import QMetaObject, Qt
                QMetaObject.invokeMethod(
                    self, "_on_debug_browser_failed",
                    Qt.ConnectionType.QueuedConnection
                )
            self._push_dev_console_status()

        elif state == "visible":
            # Visible → Hide
            print(f"[Settings] 🌐 Hiding browser for {email}...")
            self.profiles_controller.hide_debug_browser(email)
            self._update_visibility_toggle_btn(email, "hidden")
            self._push_dev_console_status()

        else:
            # Hidden → Show
            print(f"[Settings] 👁️ Showing browser for {email}...")
            self.profiles_controller.show_debug_browser(email)
            self._update_visibility_toggle_btn(email, "visible")
            self._push_dev_console_status()

    def _update_visibility_toggle_btn(self, email: str, state: str):
        """Update the visibility toggle button appearance based on browser state."""
        # Find the toggle button by objectName in the actions widget
        for row in range(self.profiles_table.rowCount()):
            email_item = self.profiles_table.item(row, 2)
            if not email_item or email not in email_item.text():
                continue
            actions_widget = self.profiles_table.cellWidget(row, 9)
            if not actions_widget:
                break
            toggle_btn = actions_widget.findChild(QPushButton, f"toggle_vis_{email}")
            if not toggle_btn:
                break

            is_visible = (state == "visible")
            is_closed = (state == "closed")

            if is_closed:
                toggle_btn.setText("⬛")
                toggle_btn.setToolTip("Browser not running")
                toggle_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Theme.SURFACE2};
                        border: 1px solid rgba(255,255,255,0.15);
                        border-radius: 6px;
                        font-size: 15px;
                        padding: 0px;
                    }}
                    QPushButton:hover {{
                        border: 1px solid rgba(255,255,255,0.5);
                    }}
                """)
            elif is_visible:
                toggle_btn.setText("👁️")
                toggle_btn.setToolTip("Browser VISIBLE — click to HIDE")
                toggle_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Theme.GREEN};
                        border: 1px solid rgba(255,255,255,0.15);
                        border-radius: 6px;
                        font-size: 15px;
                        padding: 0px;
                    }}
                    QPushButton:hover {{
                        border: 1px solid rgba(255,255,255,0.5);
                    }}
                """)
            else:  # hidden
                toggle_btn.setText("🌐")
                toggle_btn.setToolTip("Browser HIDDEN — click to SHOW")
                toggle_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Theme.YELLOW};
                        border: 1px solid rgba(255,255,255,0.15);
                        border-radius: 6px;
                        font-size: 15px;
                        padding: 0px;
                        color: {Theme.CRUST};
                    }}
                    QPushButton:hover {{
                        border: 1px solid rgba(255,255,255,0.5);
                    }}
                """)
            break

    def _push_dev_console_status(self):
        """Push browser status and session data to DevConsole via controller."""
        if self.controller and hasattr(self.controller, 'push_status_updates'):
            self.controller.push_browser_status()
        if self.controller and hasattr(self.controller, 'push_status_updates'):
            self.controller.push_session_data()

    def _refresh_status_bar(self):
        """Trigger immediate status bar refresh on the main window.
        
        Walks up the widget tree to find VEOProMaxApp and calls _poll_status_bar().
        This ensures status bar reflects profile changes in realtime.
        """
        try:
            widget = self
            while widget is not None:
                if hasattr(widget, '_poll_status_bar'):
                    widget._poll_status_bar()
                    return
                widget = getattr(widget, 'parent', lambda: None)()
        except Exception:
            pass

    @Slot()
    def _on_debug_browser_failed(self):
        """Called when debug browser fails to open."""
        show_warning(
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
        self._refresh_status_bar()
        show_info(self, "Success", "✅ Profile added successfully!")

    @Slot()
    def _on_oauth_failed(self):
        """Called when login fails or is cancelled."""
        self.setEnabled(True)  # Re-enable tab
        self._refresh_profiles_table()
        show_warning(self, "Login", "Login cancelled or failed.")

    def _on_add_profile_browser(self):
        """Auto-login with email/password credentials."""
        import threading
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox

        # Trial guard: max 1 account
        try:
            if self.controller and hasattr(self.controller, '_permissions'):
                from services.permissions import Role
                role = self.controller._permissions.role
                if role == Role.TRIAL:
                    accounts = self.profiles_controller.get_all_profiles()
                    if len(accounts) >= 1:
                        show_warning(
                            self, "🔒 Trial Limit",
                            "Gói Trial chỉ cho phép 1 tài khoản.\n\n"
                            "Nâng cấp lên Premium để thêm không giới hạn tài khoản."
                        )
                        return
        except Exception:
            pass

        # Import credentials manager
        try:
            from core.credentials_manager import get_credentials_manager
            creds_manager = get_credentials_manager()
        except ImportError as e:
            show_warning(self, "Error", f"Credentials manager not available: {e}")
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
            show_warning(self, "Error", "Please enter both email and password.")
            return

        # Save credentials (encrypted)
        if not creds_manager.save_credentials(email, password):
            show_warning(self, "Error", "Failed to save credentials.")
            return

        # Always show browser — login often needs 2FA/CAPTCHA interaction
        headless = False

        # Start auto-login
        self.setEnabled(False)

        def run_auto_login():
            """Run single-browser add profile in background thread.
            
            All steps happen in ONE Chrome browser session:
            1. Launch Chrome (no extension) → Login
            2. Install extension (after login, cookies present)
            3. AI Studio → API key
            4. labs.google → subscription
            5. Browser stays as debug browser
            """
            print(f"[Settings] Starting single-browser add profile for {email}...")
            try:
                result_email = self.profiles_controller.add_profile_single_browser(
                    email=email,
                    password=password,
                    timeout_seconds=120,
                    headless=headless,
                )

                from PySide6.QtCore import QMetaObject, Qt

                if not result_email:
                    print("[Settings] ❌ Add profile failed")
                    QMetaObject.invokeMethod(
                        self, "_on_browser_login_failed",
                        Qt.ConnectionType.QueuedConnection
                    )
                    return

                print(f"[Settings] ✅ Profile added: {result_email}")
                # Browser is already hidden by profiles_controller — do NOT show it
                
                QMetaObject.invokeMethod(
                    self, "_on_browser_login_complete",
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
        """Called when browser login completes successfully.
        
        Gemini key provision already ran in run_auto_login thread (same browser).
        This slot only refreshes UI.
        """
        self.setEnabled(True)
        self._refresh_profiles_table()
        self._refresh_status_bar()
        self._push_dev_console_status()  # Refresh DevConsole panels

        show_info(
            self,
            "Success",
            "✅ Profile added via browser!\n\n"
            "Plan/Credits đã được lấy.\n"
            "🔑 Gemini API key đã tự động xử lý."
        )

    @Slot()
    def _on_gemini_key_provisioned(self):
        """Called when Gemini key auto-provision completes."""
        # Refresh key display on Settings tab
        if hasattr(self, '_refresh_gemini_key_display'):
            self._refresh_gemini_key_display()
        show_info(self, "Gemini Key", "✅ Gemini API key đã tự động lấy thành công!")

    @Slot()
    def _on_browser_login_failed(self):
        """Called when browser login fails or times out."""
        self.setEnabled(True)
        self._refresh_profiles_table()
        show_warning(self, "Browser Login", "Login cancelled or timed out.")

    def _on_paste_gemini_key(self, email: str):
        """Show dialog to manually paste Gemini API key for a specific profile."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle(f"🤖 Gemini API Key — {email}")
        dialog.setMinimumWidth(450)

        layout = QVBoxLayout(dialog)

        form = QFormLayout()

        email_label = QLineEdit(email)
        email_label.setReadOnly(True)
        email_label.setStyleSheet("color: #888;")

        key_input = QLineEdit()
        key_input.setPlaceholderText("Paste API key (AIza...)")

        # Show existing key if any
        try:
            from services.gemini_key_manager import GeminiKeyManager
            mgr = GeminiKeyManager()
            existing = mgr.get_key(email)
            if existing:
                key_input.setText(existing)
        except Exception:
            pass

        form.addRow("📧 Profile:", email_label)
        form.addRow("🔑 API Key:", key_input)
        layout.addLayout(form)

        from PySide6.QtWidgets import QLabel
        info = QLabel(
            "⚠️ Key được mã hóa và lưu riêng cho từng profile.\n"
            "Lấy key tại: aistudio.google.com/apikey"
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

        key = key_input.text().strip()
        if not key:
            # Empty = remove key
            try:
                from services.gemini_key_manager import GeminiKeyManager
                GeminiKeyManager().remove_key(email)
                show_info(self, "Removed", f"🗑️ Đã xóa Gemini key cho {email}")
                self._refresh_profiles_table()
            except Exception:
                pass
            return

        if not key.startswith("AIza"):
            show_warning(self, "Invalid Key", "Key phải bắt đầu bằng 'AIza...'")
            return

        try:
            from services.gemini_key_manager import GeminiKeyManager
            mgr = GeminiKeyManager()
            mgr.set_key(email, key)
            self._refresh_profiles_table()
            show_info(self, "Saved", f"✅ Gemini API key đã lưu cho {email}")
        except Exception as e:
            show_warning(self, "Error", f"Không thể lưu key: {e}")

    def _on_refresh_session(self, email: str):
        """Refresh session via browser — fetch subscription real-time."""
        import threading

        profile = self.profiles_controller.get_profile(email)
        if not profile:
            show_warning(self, "Error", f"Profile not found: {email}")
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


    def _on_reload_extension(self, email: str):
        """Hot-reload the Chrome extension for this account."""
        import threading

        print(f"[Settings] 🧩 Reloading extension for: {email}")
        self._update_row_status(email, "⏳ Reloading ext...")
        self.setEnabled(False)

        def _do_reload():
            ok = False
            if self.controller:
                ok = self.controller.reload_extension_for(email)

            from PySide6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(
                self, "_on_extension_reloaded",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, email),
                Q_ARG(str, "ok" if ok else "fail"),
            )

        thread = threading.Thread(target=_do_reload, daemon=True)
        thread.start()

    @Slot(str, str)
    def _on_extension_reloaded(self, email: str, result: str):
        """Called when extension reload completes (from background thread)."""
        self.setEnabled(True)
        self._refresh_profiles_table()
        if result == "ok":
            show_info(
                self, "Reload Extension",
                f"✅ Extension reloaded for {email}"
            )
        else:
            show_warning(
                self, "Reload Extension",
                f"⚠️ Extension reload may have failed for {email}\n"
                f"Try restarting the browser instead."
            )

    def _on_reload_app(self):
        """Restart the entire Python application process."""
        if not show_confirm(self, "Reload App",
                "Restart application with latest code?\n\n"
                "• All running tasks will stop\n"
                "• Chrome browsers will keep running\n"
                "• App will relaunch automatically\n\n"
                "Continue?", danger=True):
            return

        # C3 fix: save any dirty settings before restarting
        try:
            self._on_save()
        except Exception:
            pass

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
        self._refresh_status_bar()

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
        show_warning(
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
            show_warning(self, "Error", f"Credentials manager not available: {e}")
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
            show_warning(self, "Error", "Password cannot be empty.")
            return

        if creds_manager.save_credentials(email, password):
            show_info(self, "Saved", f"✅ Password saved for {email}")
            self._refresh_profiles_table()  # Update 🔑/🔓 icon
        else:
            show_warning(self, "Error", "Failed to save credentials.")


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
        """Handle Workers SpinBox change — per-account concurrent worker limit.

        Args:
            email: Account email
            value: New max_workers value (0-20, capped at 8 for Trial)
        """
        # Workers cap: enforce max_workers_per_account from dynamic limits
        try:
            if self.controller and hasattr(self.controller, '_permissions'):
                max_wk = self.controller._permissions.limits.max_workers_per_account
                if max_wk > 0 and value > max_wk:
                    # Reset spinbox to limit
                    for row in range(self.profiles_table.rowCount()):
                        email_item = self.profiles_table.item(row, 2)
                        if email_item and email in email_item.text():
                            spin = self.profiles_table.cellWidget(row, 7)
                            if spin:
                                spin.blockSignals(True)
                                spin.setValue(max_wk)
                                spin.blockSignals(False)
                            break
                    show_warning(
                        self, "🔒 Workers Limit",
                        f"License giới hạn tối đa {max_wk} workers/account.\n\n"
                        "Nâng cấp gói để tăng giới hạn."
                    )
                    value = max_wk
        except Exception:
            pass

        # Persist to ChromeProfile
        if self.profiles_controller:
            self.profiles_controller.update_profile(email, max_workers=value)

        # Propagate to runtime AccountManager._session.max_workers
        if self.controller:
            setter = getattr(self.controller, 'set_account_max_workers',
                             getattr(self.controller, 'set_account_max_slots', None))
            if setter:
                setter(email, value)

        print(f"[Settings] Account {email} max_workers → {value}")

    def _on_delete_profile(self, email: str):
        """Delete the specified profile after confirmation.

        Full cleanup:
        1. profiles_controller.remove_profile() — kills Chrome, deletes browser folder,
           credentials, tokens.json entry, removes from _profiles list
        2. controller.remove_account() — removes from runtime engine (_multi_account),
           unregisters from session_monitor and refresh_manager
        3. Push updated data to Dev Console (session + browser panels)
        """
        if show_confirm(self, "Delete Profile",
                f"Are you sure you want to delete profile '{email}'?", danger=True):
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

            # Step 3: Refresh UI immediately (table + status bar)
            self._refresh_profiles_table()
            self._refresh_status_bar()

            # Step 4: Push updated data to Dev Console
            if self.controller:
                try:
                    if hasattr(self.controller, 'push_status_updates'):
                        self.controller.push_session_data()
                    if hasattr(self.controller, 'push_status_updates'):
                        self.controller.push_browser_status()
                except Exception as e:
                    print(f"[Settings] ⚠️ Dev Console refresh: {e}")
