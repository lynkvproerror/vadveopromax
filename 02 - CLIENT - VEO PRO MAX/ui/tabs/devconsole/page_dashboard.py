"""
DevConsole — Dashboard Page

Displays engine metrics in a card-based 2×2 grid:
- Throughput (tasks/hr, completion, avg time)
- Account Health (per-account table)
- Subsystems (reCAPTCHA pool, upscale queue, adaptive burst)
- Bottlenecks (live warnings)

Data source: AppController.get_engine_dashboard()
"""

import sys
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPlainTextEdit, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class DashboardPage(QWidget):
    """Engine Dashboard — card-based metrics overview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    # ── UI Setup ──────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Header
        header = QLabel("📊 Engine Dashboard")
        header.setStyleSheet(
            f"color: {Theme.BLUE}; font-size: 16px; font-weight: bold;"
        )
        layout.addWidget(header)

        # 2×2 card grid
        grid = QGridLayout()
        grid.setSpacing(10)

        self._throughput_card = self._create_card("🏭 Throughput", grid, 0, 0)
        self._accounts_card = self._create_card("👥 Account Health", grid, 0, 1)
        self._subsystems_card = self._create_card("🔧 Subsystems", grid, 1, 0)
        self._bottlenecks_card = self._create_card("⚠️ Bottlenecks", grid, 1, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        layout.addLayout(grid, stretch=1)

        # Timestamp
        self._timestamp = QLabel("")
        self._timestamp.setStyleSheet(f"color: {Theme.OVERLAY0}; font-size: 11px;")
        self._timestamp.setAlignment(Qt.AlignRight)
        layout.addWidget(self._timestamp)

    def _create_card(self, title: str, grid: QGridLayout, row: int, col: int) -> QPlainTextEdit:
        """Create a metric card with title + text content."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 4px; }}"
        )
        card_layout = QVBoxLayout(frame)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(4)

        label = QLabel(title)
        label.setStyleSheet(
            f"color: {Theme.BLUE}; font-weight: bold; font-size: 13px; "
            f"background: transparent; border: none;"
        )
        card_layout.addWidget(label)

        content = QPlainTextEdit()
        content.setReadOnly(True)
        content.setFont(QFont(Theme.FONT_FAMILY_MONO, 11))
        content.setStyleSheet(
            f"background-color: transparent; color: {Theme.TEXT}; "
            f"border: none; padding: 0px;"
        )
        content.setPlainText("No data yet")
        card_layout.addWidget(content, stretch=1)

        grid.addWidget(frame, row, col)
        return content

    # ── Public Update API ─────────────────────────────────────

    def update_dashboard(self, data: dict):
        """Update all cards from AppController.get_engine_dashboard() data."""
        self._update_throughput(data.get("aggregator", {}))
        self._update_accounts(
            data.get("health_scores", {}),
            data.get("burst_controller", {}),
        )
        self._update_subsystems(data)
        self._update_bottlenecks(data.get("bottlenecks", []))
        self._timestamp.setText(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

    # ── Card renderers ────────────────────────────────────────

    def _update_throughput(self, agg: dict):
        if not agg:
            self._throughput_card.setPlainText("No data yet")
            return

        completed = agg.get("completed", 0)
        failed = agg.get("failed", 0)
        active = agg.get("active_tasks", 0)
        avg_sec = agg.get("avg_completion_sec", 0)
        throughput = agg.get("throughput_per_hour", 0)
        success_rate = agg.get("success_rate", 0)
        error_rate = agg.get("recent_error_rate", 0)

        avg_min = int(avg_sec // 60) if avg_sec else 0
        avg_s = int(avg_sec % 60) if avg_sec else 0

        lines = [
            f"Tasks/hr : {throughput:.0f}  |  Active: {active}",
            f"✅ Done  : {completed}",
            f"❌ Failed: {failed}",
            f"📈 Rate  : {success_rate:.1f}%",
            f"⏱ Avg   : {avg_min}m {avg_s}s",
            f"Recent err: {error_rate:.0f}%",
        ]
        self._throughput_card.setPlainText("\n".join(lines))

    def _update_accounts(self, hs: dict, burst: dict):
        accounts = hs.get("accounts", {})
        burst_accounts = burst.get("accounts", {})

        if not accounts:
            self._accounts_card.setPlainText("No accounts active")
            return

        lines = [f"{'Account':<22} {'Slots':>5} {'Score':>6} {'Burst':>6} {'Ext':>4}"]
        lines.append(f"{'─' * 22} {'─' * 5} {'─' * 6} {'─' * 6} {'─' * 4}")

        for email, info in accounts.items():
            short = email[:19] + ".." if len(email) > 21 else email
            slots = f"{info.get('active_slots', 0)}/{info.get('max_slots', 5)}"
            score = info.get("score", 0)
            ext = "✅" if info.get("ext_connected") else "❌"
            b_delay = burst_accounts.get(email, {}).get("delay", "-")
            b_str = f"{b_delay}s" if isinstance(b_delay, (int, float)) else str(b_delay)
            lines.append(f"{short:<22} {slots:>5} {score:>6} {b_str:>6} {ext:>4}")

        self._accounts_card.setPlainText("\n".join(lines))

    def _update_subsystems(self, data: dict):
        lines = []

        pool = data.get("recaptcha_pool", {})
        if pool:
            lines.append(
                f"• reCAPTCHA Pool: hits={pool.get('hits', 0)}, "
                f"misses={pool.get('misses', 0)}, "
                f"rate={pool.get('hit_rate', 0):.1f}%"
            )
        else:
            lines.append("• reCAPTCHA Pool: not active")

        uq = data.get("upscale_queue", {})
        if uq:
            lines.append(
                f"• Upscale Queue: pending={uq.get('pending_jobs', 0)}, "
                f"done={uq.get('total_completed', 0)}, "
                f"failed={uq.get('total_failed', 0)}"
            )
        else:
            lines.append("• Upscale Queue: not active")

        burst = data.get("burst_controller", {})
        if burst:
            lines.append(
                f"• Adaptive Burst: avg delay={burst.get('global_avg_delay', '-')}s"
            )
        else:
            lines.append("• Adaptive Burst: not active")

        self._subsystems_card.setPlainText("\n".join(lines))

    def _update_bottlenecks(self, bottlenecks: list):
        if bottlenecks:
            lines = [f"• {bn}" for bn in bottlenecks]
        else:
            lines = ["✅ No bottlenecks detected"]
        self._bottlenecks_card.setPlainText("\n".join(lines))
