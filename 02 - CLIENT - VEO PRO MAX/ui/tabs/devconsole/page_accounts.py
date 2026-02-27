"""
DevConsole — Accounts Page

Consolidates per-account data from three sources:
- Session Data (tokens, cookies, credits)
- Playwright (browser status)
- Extension Bridge (connection per email)

Renders as scrollable per-account cards.
"""

import sys
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QFrame,
    QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class AccountsPage(QWidget):
    """Per-account consolidated view: Session + Browser + Extension."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._account_cards: dict[str, QPlainTextEdit] = {}
        self._session_data: list = []
        self._browser_data: list = []
        self._extension_data: dict = {}
        self._prewarm_data: dict = {}  # email → {total_prewarms, current_idle_secs, ...}
        self._circuit_data: dict = {}  # email → {state, consecutive_403, open_duration_sec}
        self._cooldown_data: dict = {} # email → {remaining_sec, backoff_level, until}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QLabel("👥 Accounts")
        header.setStyleSheet(
            f"color: {Theme.BLUE}; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(header)

        # Scrollable card container
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
        )

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(10)
        self._card_layout.addStretch()

        scroll.setWidget(self._card_container)
        layout.addWidget(scroll, stretch=1)

        self._timestamp = QLabel("")
        self._timestamp.setStyleSheet(f"color: {Theme.OVERLAY0}; font-size: 11px;")
        self._timestamp.setAlignment(Qt.AlignRight)
        layout.addWidget(self._timestamp)

    def _get_or_create_card(self, email: str) -> QPlainTextEdit:
        """Get existing card or create a new one for an email."""
        if email in self._account_cards:
            return self._account_cards[email]

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px; }}"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 8, 10, 8)
        frame_layout.setSpacing(4)

        label = QLabel(f"📧 {email}")
        label.setStyleSheet(
            f"color: {Theme.BLUE}; font-weight: bold; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        frame_layout.addWidget(label)

        content = QPlainTextEdit()
        content.setReadOnly(True)
        content.setFont(QFont(Theme.FONT_FAMILY_MONO, 11))
        content.setStyleSheet(
            f"background-color: transparent; color: {Theme.TEXT}; "
            f"border: none; padding: 0px;"
        )
        content.setMaximumHeight(220)
        content.setPlainText("Loading...")
        frame_layout.addWidget(content)

        # Insert before the stretch
        idx = self._card_layout.count() - 1
        self._card_layout.insertWidget(idx, frame)
        self._account_cards[email] = content
        return content

    # ── Public API ────────────────────────────────────────────

    def update_session_data(self, accounts: list):
        """Update session/token/cookie data (from AppController.get_session_data)."""
        self._session_data = accounts or []
        self._render_all()

    def update_browser_status(self, accounts: list):
        """Update browser status per account."""
        self._browser_data = accounts or []
        self._render_all()

    def update_extension_status(self, status: dict):
        """Update extension bridge data (connection per email)."""
        self._extension_data = status or {}
        self._render_all()

    def update_prewarm_data(self, prewarm: dict):
        """Update pre-warm stats from engine dashboard."""
        self._prewarm_data = prewarm.get('accounts', {}) if prewarm else {}
        self._render_all()

    def update_circuit_data(self, data: dict):
        """Update circuit breaker status per-account from engine dashboard."""
        self._circuit_data = data or {}
        self._render_all()

    def update_cooldown_data(self, data: dict):
        """Update cooldown status per-account from engine dashboard."""
        self._cooldown_data = data or {}
        self._render_all()

    # ── Render ────────────────────────────────────────────────

    def _render_all(self):
        """Re-render all account cards from latest data."""
        # Build browser lookup {email: browser_info}
        browser_map = {}
        for b in self._browser_data:
            email = b.get("email", "")
            if email:
                browser_map[email] = b

        # Extension lookup
        ext_emails = set(self._extension_data.get("emails", []))
        ext_headers = self._extension_data.get("cached_headers", {})

        for acc in self._session_data:
            email = acc.get("email", "?")
            card = self._get_or_create_card(email)
            lines = []

            # Plan & Credits
            sku = acc.get("sku", "?")
            credits_val = acc.get("credits", 0)
            workers = acc.get("workers", acc.get("slots_display", "?"))
            lines.append(f"Plan: {sku}  |  Credits: {credits_val:,}  |  Workers: {workers}")

            # Session
            lines.append(f"Session: {acc.get('session_status', '?')}")

            # Access Token
            at = acc.get("access_token", "")
            token_exp = acc.get("token_expiry", "")
            ext_connected = acc.get("ext_connected", False) or (email in ext_emails)
            if at:
                at_display = f"{at[:12]}...{at[-8:]}"
                lines.append(f"Token  : {at_display}")
            elif ext_connected:
                lines.append("Token  : 🟢 Pending (Extension)")
            else:
                lines.append("Token  : ❌ Missing")
            lines.append(f"Expiry : {token_exp}")

            # reCAPTCHA
            lines.append(f"reCAPTCHA: {acc.get('recaptcha_status', '?')}")

            # Extension
            if email in ext_emails:
                headers = ext_headers.get(email, [])
                h_count = len(headers)
                if h_count > 0:
                    h_names = ", ".join(h.replace("x-", "") for h in headers)
                    lines.append(f"Extension: 🟢 Connected → {h_count} headers ({h_names})")
                else:
                    lines.append("Extension: 🟡 Connecting → waiting headers...")
            else:
                lines.append("Extension: 🔴 Disconnected")

            # Cookies
            cookie_count = acc.get("cookie_count", 0)
            cookies_locked = acc.get("cookies_locked", False)
            if cookies_locked:
                lines.append("Cookies: 🔒 Locked (browser active)")
            elif cookie_count:
                domains = acc.get("cookie_domains", {})
                d_str = ", ".join(f"{d}: {c}" for d, c in list(domains.items())[:3])
                lines.append(f"Cookies: {cookie_count} ({d_str})")
            else:
                lines.append("Cookies: 0")

            # Browser (from Playwright data)
            b = browser_map.get(email, {})
            browser_state_map = {
                "visible": "🟢 Visible",
                "hidden": "🟡 Hidden",
                "closed": "⚪ Off",
            }
            bs = browser_state_map.get(b.get("state", "closed"), "⚪ Off")
            enabled = "✅" if b.get("enabled", acc.get("is_enabled")) else "❌"
            lines.append(f"Browser: {bs}  |  Enabled: {enabled}")

            # Pre-warm / Idle
            pw_acct = self._prewarm_data.get(email, {})
            if pw_acct:
                idle = pw_acct.get('current_idle_secs', 0)
                warms = pw_acct.get('total_prewarms', 0)
                idle_str = f"{idle // 60}m{idle % 60}s" if idle > 60 else f"{idle}s"
                lines.append(f"Pre-warm: idle={idle_str}  |  Warms: {warms}")

            # Circuit Breaker
            cb = self._circuit_data.get(email, {})
            if cb:
                cb_state = cb.get("state", "closed")
                cb_403 = cb.get("consecutive_403", 0)
                cb_dur = cb.get("open_duration_sec", 0)
                cb_icons = {
                    "closed": "🟢 OK",
                    "open": f"🔴 OPEN ({cb_dur}s)",
                    "half_open": "🟡 PROBING",
                }
                lines.append(f"Circuit: {cb_icons.get(cb_state, cb_state)}  |  Consecutive 403s: {cb_403}")

            # Cooldown
            cd = self._cooldown_data.get(email, {})
            if cd:
                cd_remaining = cd.get("remaining_sec", 0)
                cd_level = cd.get("backoff_level", 0)
                cd_until = cd.get("until", "?")
                level_map = {0: "30s", 1: "60s", 2: "120s", 3: "180s"}
                level_str = level_map.get(cd_level, f"{cd_level}")
                lines.append(
                    f"Cooldown: ❄️ {cd_remaining}s remaining  |  "
                    f"Level: {cd_level} ({level_str})  |  Until: {cd_until}"
                )

            card.setPlainText("\n".join(lines))

        self._timestamp.setText(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
