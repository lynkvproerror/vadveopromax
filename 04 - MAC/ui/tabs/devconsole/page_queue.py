"""
DevConsole — Queue & Performance Page

Displays queue state and system performance in a vertical split:
- Top: Queue State (task counts + processing status)
- Bottom: Performance (uptime, CPU, RAM, API calls)

Data sources:
- AppController queue state dict
- AppController performance dict
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


class QueuePerfPage(QWidget):
    """Queue State + Performance metrics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QLabel("📋 Queue & Performance")
        header.setStyleSheet(
            f"color: {Theme.BLUE}; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(header)

        splitter = QSplitter(Qt.Vertical)

        # Queue State card
        self._queue_text = self._create_section("📊 Queue State", splitter)

        # Performance card
        self._perf_text = self._create_section("⚡ Performance", splitter)

        splitter.setSizes([300, 200])
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

    def update_queue_state(self, state: dict):
        """Update Queue State section."""
        lines = [
            f"Total     : {state.get('total', 0)}",
            f"Pending   : {state.get('pending', 0)}",
            f"Processing: {state.get('processing', 0)}",
            f"Completed : {state.get('completed', 0)}",
            f"Failed    : {state.get('errors', 0)}",
            "",
            f"Status    : {'🟢 Active' if state.get('is_processing') else '⏸️ Stopped'}",
        ]
        self._queue_text.setPlainText("\n".join(lines))
        self._timestamp.setText(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

    def update_performance(self, data: dict):
        """Update Performance section."""
        lines = [
            f"Uptime   : {data.get('uptime', '00:00:00')}",
            f"CPU      : {data.get('cpu', '?')}%",
            f"RAM      : {data.get('ram', '?')} MB",
            f"Threads  : {data.get('threads', '?')}",
            "",
            f"API Calls: {data.get('api_calls', 0)}",
            f"Downloads: {data.get('downloads', 0)}",
            f"Errors   : {data.get('errors', 0)}",
        ]
        self._perf_text.setPlainText("\n".join(lines))
        self._timestamp.setText(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
