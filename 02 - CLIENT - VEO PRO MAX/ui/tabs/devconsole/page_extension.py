"""
DevConsole — Extension Debug Page

Full debug view of all data exchanged between Extension and App:
- Live WebSocket message stream (IN/OUT with action, email, timestamp)
- Connection state summary
- Message filtering by action or email
- Auto-refresh via QTimer
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QComboBox, QPlainTextEdit,
    QSplitter,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class ExtensionDebugPage(QWidget):
    """Live Extension ↔ App message debug page."""

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self._last_count = 0  # Track message count for incremental updates
        self._setup_ui()
        self._start_auto_refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Header ──
        header_row = QHBoxLayout()
        title = QLabel("🧩 Extension Debug — WebSocket Messages")
        title.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 15px; font-weight: bold;"
        )
        header_row.addWidget(title)
        header_row.addStretch()
        layout.addLayout(header_row)

        # ── Filter row ──
        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("Filter:"))
        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Action or email...")
        self._filter_input.setFixedWidth(200)
        filter_row.addWidget(self._filter_input)

        self._dir_filter = QComboBox()
        self._dir_filter.addItems(["All", "IN ←", "OUT →"])
        self._dir_filter.setFixedWidth(80)
        filter_row.addWidget(self._dir_filter)

        # Auto-refresh toggle
        self._auto_refresh_btn = QPushButton("⏸ Auto")
        self._auto_refresh_btn.setMinimumWidth(80)
        self._auto_refresh_btn.setFixedHeight(28)
        self._auto_refresh_btn.setCheckable(True)
        self._auto_refresh_btn.setChecked(True)
        self._auto_refresh_btn.setProperty("variant", "success")
        self._auto_refresh_btn.setProperty("btnSize", "sm")
        self._auto_refresh_btn.toggled.connect(self._on_auto_toggle)
        filter_row.addWidget(self._auto_refresh_btn)

        # Manual refresh
        refresh_btn = QPushButton("🔄")
        refresh_btn.setMinimumSize(34, 28)
        refresh_btn.setToolTip("Refresh now")
        refresh_btn.setProperty("variant", "secondary")
        refresh_btn.clicked.connect(self._do_refresh)
        filter_row.addWidget(refresh_btn)

        filter_row.addStretch()

        self._msg_count_label = QLabel("0 messages")
        self._msg_count_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        filter_row.addWidget(self._msg_count_label)

        layout.addLayout(filter_row)

        # ── Splitter: Table + Detail ──
        splitter = QSplitter(Qt.Vertical)

        # Message table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Dir", "Time", "Action", "Email", "Preview"])
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 45)
        self._table.setColumnWidth(1, 70)
        self._table.setColumnWidth(2, 150)
        self._table.setColumnWidth(3, 180)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.currentCellChanged.connect(self._on_row_selected)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {Theme.SURFACE0};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                gridline-color: {Theme.SURFACE1};
                font-size: 11px;
            }}
            QTableWidget::item:alternate {{
                background-color: {Theme.MANTLE};
            }}
            QHeaderView::section {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                padding: 4px;
                border: 1px solid {Theme.BORDER};
                font-weight: bold;
                font-size: 11px;
            }}
        """)
        splitter.addWidget(self._table)

        # Detail view (JSON preview of selected message)
        detail_frame = QFrame()
        detail_frame.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px; }}"
        )
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(8, 6, 8, 6)

        detail_header = QLabel("📋 Message Detail")
        detail_header.setStyleSheet(
            f"color: {Theme.BLUE}; font-weight: bold; font-size: 12px; border: none;"
        )
        detail_layout.addWidget(detail_header)

        self._detail_text = QPlainTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setFont(QFont(Theme.FONT_FAMILY_MONO if hasattr(Theme, 'FONT_FAMILY_MONO') else 'Consolas', 10))
        self._detail_text.setStyleSheet(
            f"background-color: {Theme.MANTLE}; color: {Theme.SUBTEXT0}; "
            f"border: none; padding: 4px;"
        )
        self._detail_text.setPlaceholderText("Click a message row to see full payload...")
        detail_layout.addWidget(self._detail_text)

        splitter.addWidget(detail_frame)
        splitter.setSizes([400, 150])

        layout.addWidget(splitter, stretch=1)

        # Store messages for detail view
        self._messages_data = []

    def _start_auto_refresh(self):
        """Start auto-refresh timer (every 1 second)."""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._do_refresh)
        self._timer.start()

    def _on_auto_toggle(self, checked: bool):
        if checked:
            self._timer.start()
            self._auto_refresh_btn.setText("⏸ Auto")
            self._auto_refresh_btn.setProperty("variant", "success")
        else:
            self._timer.stop()
            self._auto_refresh_btn.setText("▶ Auto")
            self._auto_refresh_btn.setProperty("variant", "secondary")
        self._auto_refresh_btn.style().unpolish(self._auto_refresh_btn)
        self._auto_refresh_btn.style().polish(self._auto_refresh_btn)

    def set_controller(self, controller):
        """Set controller reference (for lazy binding)."""
        self.controller = controller

    def _get_bridge(self):
        """Get ExtensionBridge instance from controller."""
        if self.controller and hasattr(self.controller, '_extension_bridge'):
            return self.controller._extension_bridge
        return None

    def _do_refresh(self):
        """Fetch latest messages from bridge and update table."""
        bridge = self._get_bridge()
        if not bridge:
            return

        messages = bridge.get_message_log(last_n=300)
        if len(messages) == self._last_count:
            return  # No new messages
        self._last_count = len(messages)

        # Apply filters
        filter_text = self._filter_input.text().strip().lower()
        dir_filter = self._dir_filter.currentText()

        filtered = []
        for m in messages:
            if dir_filter == "IN ←" and m['dir'] != 'IN':
                continue
            if dir_filter == "OUT →" and m['dir'] != 'OUT':
                continue
            if filter_text:
                if (filter_text not in m.get('action', '').lower() and
                    filter_text not in m.get('email', '').lower()):
                    continue
            filtered.append(m)

        self._messages_data = filtered
        self._update_table(filtered)
        self._msg_count_label.setText(f"{len(filtered)}/{len(messages)} messages")

    def _update_table(self, messages: list):
        """Populate table with messages."""
        self._table.setRowCount(len(messages))
        for i, m in enumerate(messages):
            # Direction
            d = m['dir']
            dir_item = QTableWidgetItem("← IN" if d == 'IN' else "→ OUT")
            dir_item.setForeground(QColor(Theme.GREEN if d == 'IN' else Theme.BLUE))
            dir_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 0, dir_item)

            # Timestamp
            ts = datetime.fromtimestamp(m['ts']).strftime("%H:%M:%S")
            ts_item = QTableWidgetItem(ts)
            ts_item.setForeground(QColor(Theme.OVERLAY0))
            self._table.setItem(i, 1, ts_item)

            # Action
            action = m.get('action', '?')
            action_item = QTableWidgetItem(action)
            # Color-code common actions
            action_colors = {
                'register': Theme.GREEN,
                'headers_update': Theme.YELLOW,
                'recaptcha_response': Theme.PEACH if hasattr(Theme, 'PEACH') else Theme.YELLOW,
                'request_recaptcha': Theme.BLUE,
                'submit_prompt': Theme.BLUE,
                'heartbeat': Theme.SUBTEXT0,
                'content_heartbeat': Theme.SUBTEXT0,
                'pong': Theme.SUBTEXT0,
            }
            color = action_colors.get(action, Theme.TEXT)
            action_item.setForeground(QColor(color))
            self._table.setItem(i, 2, action_item)

            # Email
            email = m.get('email', '')
            email_item = QTableWidgetItem(email[:35])
            self._table.setItem(i, 3, email_item)

            # Preview (compact)
            preview = m.get('preview', {})
            # Remove redundant fields already shown in columns
            compact = {k: v for k, v in preview.items()
                       if k not in ('action', 'email')}
            preview_str = json.dumps(compact, ensure_ascii=False, default=str)
            if len(preview_str) > 120:
                preview_str = preview_str[:120] + "..."
            preview_item = QTableWidgetItem(preview_str)
            preview_item.setForeground(QColor(Theme.SUBTEXT0))
            self._table.setItem(i, 4, preview_item)

        # Auto-scroll to bottom
        if messages:
            self._table.scrollToBottom()

    def _on_row_selected(self, row, col, prev_row, prev_col):
        """Show full message detail when row is clicked."""
        if 0 <= row < len(self._messages_data):
            m = self._messages_data[row]
            detail = {
                'direction': m['dir'],
                'action': m.get('action'),
                'email': m.get('email'),
                'timestamp': datetime.fromtimestamp(m['ts']).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                'payload': m.get('preview', {}),
            }
            self._detail_text.setPlainText(
                json.dumps(detail, indent=2, ensure_ascii=False, default=str)
            )
