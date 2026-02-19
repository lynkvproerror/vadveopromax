"""
DevConsole — Network Page

Displays Extension Bridge status and API activity:
- WebSocket bridge status (running, port, connections)
- Registered tabs with cached header details
- API activity log (filtered from main log stream)

Data source: ExtensionBridge.get_status()
"""

import sys
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QFrame, QSplitter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class NetworkPage(QWidget):
    """Extension Bridge + API activity view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QLabel("🌐 Network")
        header.setStyleSheet(
            f"color: {Theme.BLUE}; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(header)

        splitter = QSplitter(Qt.Vertical)

        # Extension Bridge section
        self._ext_text = self._create_section("🧩 Extension Bridge", splitter)

        # API Activity section
        self._api_text = self._create_section("📡 API Activity", splitter)
        self._api_text.setPlainText("API activity will appear here during processing...\n")

        splitter.setSizes([250, 300])
        layout.addWidget(splitter, stretch=1)

        self._timestamp = QLabel("")
        self._timestamp.setStyleSheet(f"color: {Theme.OVERLAY0}; font-size: 11px;")
        self._timestamp.setAlignment(Qt.AlignRight)
        layout.addWidget(self._timestamp)

    def _create_section(self, title: str, splitter: QSplitter) -> QPlainTextEdit:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px; }}"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(10, 8, 10, 8)
        frame_layout.setSpacing(4)

        label = QLabel(title)
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
        content.setPlainText("Waiting for data...")
        frame_layout.addWidget(content, stretch=1)

        splitter.addWidget(frame)
        return content

    # ── Public API ────────────────────────────────────────────

    def update_extension_status(self, status: dict):
        """Update Extension Bridge panel."""
        if not status:
            self._ext_text.setPlainText("Extension bridge not started.\n")
            return

        running = status.get('running', False)
        port = status.get('port', 8765)
        conn_count = status.get('connections', 0)
        emails = status.get('emails', [])
        cached_headers = status.get('cached_headers', {})

        ws_icon = "🟢" if running else "🔴"
        conn_icon = "🔌" if conn_count > 0 else "⚪"

        lines = [
            f"{ws_icon} WebSocket: ws://127.0.0.1:{port}  |  {conn_icon} Connections: {conn_count}",
            "",
        ]

        if emails:
            lines.append(f"📧 Registered Tabs ({len(emails)}):")
            for email in emails:
                headers = cached_headers.get(email, [])
                h_count = len(headers)
                if h_count > 0:
                    h_names = ", ".join(h.replace("x-", "") for h in headers)
                    lines.append(f"  ✅ {email}  →  {h_count} headers ({h_names})")
                else:
                    lines.append(f"  ⏳ {email}  →  waiting for headers...")
        else:
            lines.append("📧 No tabs registered yet")
            lines.append("  └─ Open a debug browser to connect extension")

        self._ext_text.setPlainText("\n".join(lines))
        self._timestamp.setText(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

    def append_api_log(self, message: str):
        """Append an API activity log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"

        # Append and cap at 200 lines
        text = self._api_text.toPlainText()
        lines = text.split("\n")
        lines.append(entry)
        if len(lines) > 200:
            lines = lines[-200:]
        self._api_text.setPlainText("\n".join(lines))

        # Scroll to bottom
        sb = self._api_text.verticalScrollBar()
        sb.setValue(sb.maximum())
