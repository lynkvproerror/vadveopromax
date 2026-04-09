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
        agg = data.get("aggregator", {})
        self._update_throughput(agg)
        self._update_accounts(
            data.get("health_scores", {}),
            data.get("burst_controller", {}),
            data.get("circuit_breaker_status", {}),
            data.get("cooldowns", {}),
            data.get("rate_locks", {}),
        )
        self._update_subsystems(data)
        self._update_bottlenecks(
            data.get("bottlenecks", []),
            recent_errors=agg.get("recent_errors", []),
        )
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

    def _update_accounts(self, hs: dict, burst: dict,
                         circuit: dict = None, cooldowns: dict = None,
                         rate_locks: dict = None):
        accounts = hs.get("accounts", {})
        burst_accounts = burst.get("accounts", {})
        circuit = circuit or {}
        cooldowns = cooldowns or {}
        rate_locks = rate_locks or {}

        if not accounts:
            self._accounts_card.setPlainText("No accounts active")
            return

        lines = [f"{'Account':<22} {'Slots':>5} {'Score':>6} {'Burst':>6} {'CB':>5} {'CD':>6} {'Ext':>4}"]
        lines.append(f"{'─' * 22} {'─' * 5} {'─' * 6} {'─' * 6} {'─' * 5} {'─' * 6} {'─' * 4}")

        for email, info in accounts.items():
            short = email[:19] + ".." if len(email) > 21 else email
            slots = f"{info.get('active_workers', 0)}/{info.get('max_workers', 20)}"
            upscale = info.get(
                'active_upscale_total',
                info.get('active_upscale', 0) + info.get('active_bg_upscale', 0),
            )
            if upscale > 0:
                slots += f" ⬆️{upscale}/{info.get('max_upscale', 8)}"
            score = info.get("score", 0)
            ext = "✅" if info.get("ext_connected") else "❌"
            b_delay = burst_accounts.get(email, {}).get("delay", "-")
            b_str = f"{b_delay}s" if isinstance(b_delay, (int, float)) else str(b_delay)
            
            # Circuit Breaker column
            cb_info = circuit.get(email, {})
            cb_state = cb_info.get("state", "closed")
            cb_403 = cb_info.get("consecutive_403", 0)
            if cb_state == "closed":
                cb_str = "🟢"
            elif cb_state == "half_open":
                cb_str = "🟡P"
            else:  # open
                cb_str = f"🔴{cb_403}"
            
            # Cooldown column
            cd_info = cooldowns.get(email, {})
            cd_remaining = cd_info.get("remaining_sec", 0)
            if cd_remaining > 0:
                cd_str = f"❄️{cd_remaining}s"
            else:
                cd_str = "✅"
            
            lines.append(f"{short:<22} {slots:>5} {score:>6} {b_str:>6} {cb_str:>5} {cd_str:>6} {ext:>4}")

        self._accounts_card.setPlainText("\n".join(lines))

    def _update_subsystems(self, data: dict):
        lines = []

        # Tab Keepalive
        ka = data.get("keepalive", {})
        if ka:
            state = ka.get('state', 'NOT_STARTED')
            state_icons = {
                "ACTIVE": "🟢 ACTIVE",
                "PAUSED": "⏸️ PAUSED (Engine Processing)",
                "STOPPED": "🔴 STOPPED",
                "NOT_STARTED": "⚪ Not Started",
            }
            controller = ka.get('controller', '?')
            ping_count = ka.get('last_ping_count', 0)
            ping_time = ka.get('last_ping_time', 0)
            if ping_time > 0:
                ago = int(datetime.now().timestamp() - ping_time)
                ping_ago = f"{ago}s ago" if ago < 120 else f"{ago // 60}m ago"
            else:
                ping_ago = "never"
            lines.append(f"• Tab Keepalive: {state_icons.get(state, state)}")
            lines.append(f"  └ Controller: {controller}  |  Last: {ping_count} tabs ({ping_ago})")
        else:
            lines.append("• Tab Keepalive: ⚪ Not Started")

        # reCAPTCHA Pool (with per-account depth)
        pool = data.get("recaptcha_pool", {})
        if pool:
            lines.append(
                f"• reCAPTCHA Pool: hits={pool.get('hits', 0)}, "
                f"misses={pool.get('misses', 0)}, "
                f"rate={pool.get('hit_rate', 0):.1f}%"
            )
            pool_sizes = pool.get("pool_sizes", {})
            if pool_sizes:
                for email, depth in pool_sizes.items():
                    short = email.split('@')[0][:12]
                    lines.append(f"  └ {short}: {depth} token(s) ready")
        else:
            lines.append("• reCAPTCHA Pool: not active")

        # Upscale Queue
        uq = data.get("upscale_queue", {})
        if uq:
            lines.append(
                f"• Upscale Queue: pending={uq.get('pending_jobs', 0)}, "
                f"done={uq.get('total_completed', 0)}, "
                f"failed={uq.get('total_failed', 0)}"
            )
            # TRPC/FIFE download stats
            trpc = uq.get("trpc", {})
            fife = uq.get("fife", {})
            trpc_a = trpc.get("attempts", 0)
            fife_a = fife.get("attempts", 0)
            if trpc_a > 0 or fife_a > 0:
                trpc_rate = f"{trpc.get('success',0)}/{trpc_a}" if trpc_a else "—"
                fife_rate = f"{fife.get('success',0)}/{fife_a}" if fife_a else "—"
                lines.append(
                    f"  └ TRPC: {trpc_rate} ✅  |  "
                    f"FIFE: {fife_rate} ✅"
                )
                trpc_fail = trpc.get("fail", 0)
                fife_fail = fife.get("fail", 0)
                if trpc_fail > 0 or fife_fail > 0:
                    lines.append(
                        f"    TRPC fail={trpc_fail}  |  FIFE fail={fife_fail}"
                    )
            xcd_bypass = uq.get("xcd_bypass", 0)
            if xcd_bypass > 0:
                lines.append(f"  └ xcd-bypass (trial token): {xcd_bypass}×")
        else:
            lines.append("• Upscale Queue: not active")

        # Adaptive Burst
        burst = data.get("burst_controller", {})
        if burst:
            lines.append(
                f"• Adaptive Burst: avg delay={burst.get('global_avg_delay', '-')}s"
            )
        else:
            lines.append("• Adaptive Burst: not active")


        # Pre-warm stats
        pw = data.get("prewarm", {})
        if pw:
            enabled = "✅ ON" if pw.get('enabled', True) else "❌ OFF"
            threshold = pw.get('threshold_sec', 600)
            lines.append(f"• Pre-warm: {enabled} (threshold: {threshold // 60}m)")
            for email, acct in pw.get('accounts', {}).items():
                short = email.split('@')[0][:12]
                idle = acct.get('current_idle_secs', 0)
                count = acct.get('total_prewarms', 0)
                idle_str = f"{idle // 60}m{idle % 60}s" if idle > 60 else f"{idle}s"
                lines.append(f"  └ {short}: idle={idle_str}, warms={count}")

        # Rate Locks
        rl = data.get("rate_locks", {})
        if rl:
            locked_count = sum(1 for v in rl.values() if v.get("locked"))
            total = len(rl)
            if locked_count > 0:
                lines.append(f"• Rate Locks: 🔒 {locked_count}/{total} locked")
            else:
                lines.append(f"• Rate Locks: 🔓 {total} free")

        self._subsystems_card.setPlainText("\n".join(lines))

    def _update_bottlenecks(self, bottlenecks: list, recent_errors: list = None):
        lines = []
        if bottlenecks:
            for bn in bottlenecks:
                if isinstance(bn, dict):
                    bn_type = bn.get("type", "unknown")
                    if bn_type == "stuck_task":
                        elapsed = bn.get('elapsed_sec', 0)
                        stage = bn.get('stage', '?')
                        task_id = str(bn.get('task_id', ''))[:8]
                        lines.append(f"⚠️ Stuck: {task_id}.. ({elapsed // 60}m, stage={stage})")
                    elif bn_type == "high_error_rate":
                        rate = bn.get('success_rate', 0)
                        lines.append(f"⚠️ Low success rate: {rate:.1f}%")
                    elif bn_type == "frequent_watchdog":
                        recoveries = bn.get('recoveries', 0)
                        lines.append(f"⚠️ Watchdog recoveries: {recoveries}")
                    else:
                        lines.append(f"⚠️ {bn_type}: {bn}")
                else:
                    lines.append(f"• {bn}")
        else:
            lines.append("✅ No bottlenecks detected")

        # Recent Errors (from StatusAggregator)
        if recent_errors:
            lines.append("")
            lines.append("── Recent Errors ──")
            for err in recent_errors[-5:]:
                if isinstance(err, dict):
                    t = err.get("time", "")
                    reason = str(err.get("reason", "?"))[:70]
                    lines.append(f"  {t} | {reason}")
                else:
                    lines.append(f"  {str(err)[:80]}")

        self._bottlenecks_card.setPlainText("\n".join(lines))
