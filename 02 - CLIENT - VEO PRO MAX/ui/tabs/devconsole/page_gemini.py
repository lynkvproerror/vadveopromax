"""
DevConsole — Gemini API Page

Debug panel for Project Builder's Gemini API integration:
- Diagnostic badges: Templates, Rules, API key, Model, Output folder
- Real-time generation log viewer with timestamps
- Full traceback display on errors
"""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QTextEdit,
)
from PySide6.QtCore import Qt, Slot

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.theme import Theme


class GeminiApiPage(QWidget):
    """Gemini API debug page for DevConsole."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── Header ──
        header_row = QHBoxLayout()
        title = QLabel("🤖 Gemini API — Project Builder Debug")
        title.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 15px; font-weight: bold;"
        )
        header_row.addWidget(title)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setFixedWidth(90)
        refresh_btn.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"height: 28px; border-radius: 4px;"
        )
        refresh_btn.clicked.connect(self.refresh_diagnostics)
        header_row.addWidget(refresh_btn)

        # Clear log
        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.setFixedWidth(80)
        clear_btn.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"height: 28px; border-radius: 4px;"
        )
        clear_btn.clicked.connect(lambda: self._log_view.clear())
        header_row.addWidget(clear_btn)

        header_row.addStretch()
        layout.addLayout(header_row)

        # ── Diagnostic badges ──
        self._badges_frame = QFrame()
        self._badges_frame.setStyleSheet(
            f"QFrame {{ background-color: {Theme.SURFACE0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 6px; }}"
        )
        self._badges_layout = QHBoxLayout(self._badges_frame)
        self._badges_layout.setContentsMargins(10, 6, 10, 6)
        self._badges_layout.setSpacing(8)

        # Placeholder badges
        self._placeholder = QLabel("Press 🔄 Refresh to check diagnostics")
        self._placeholder.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px;")
        self._badges_layout.addWidget(self._placeholder)
        self._badges_layout.addStretch()

        layout.addWidget(self._badges_frame)

        # ── Log viewer ──
        log_header = QLabel("📋 Generation Log")
        log_header.setStyleSheet(
            f"color: {Theme.TEXT}; font-size: 13px; font-weight: bold;"
        )
        layout.addWidget(log_header)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.MANTLE};
                color: {Theme.SUBTEXT0};
                font-family: 'Cascadia Code', 'Consolas', monospace;
                font-size: 11px;
                border: 1px solid {Theme.SURFACE0};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        self._log_view.setPlaceholderText(
            "Generation logs will appear here when you run Project Builder...\n"
            "Logs include: API calls, step progress, errors with full tracebacks."
        )
        layout.addWidget(self._log_view, stretch=1)

        # ── Stats footer ──
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet(
            f"color: {Theme.OVERLAY0}; font-size: 11px;"
        )
        layout.addWidget(self._stats_label)

    def _make_badge(self, text: str, color: str) -> QLabel:
        """Create a colored badge label."""
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"background-color: {color}; color: {Theme.CRUST}; "
            f"font-size: 10px; font-weight: bold; "
            f"padding: 3px 10px; border-radius: 10px;"
        )
        return lbl

    def refresh_diagnostics(self):
        """Refresh diagnostic badges by reading live settings."""
        # Clear old badges
        while self._badges_layout.count() > 0:
            item = self._badges_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            from config.settings import get_settings
            s = get_settings()

            # Scanner status
            tmpl_count = 0
            rules_count = 0
            try:
                from core.workflow_scanner import WorkflowScanner
                from core.rules_loader import RulesLoader
                scanner = WorkflowScanner()
                bundled_root = Path(__file__).parent.parent.parent.parent / "data" / "workflows"
                bundled_templates = str(bundled_root / "02_Universal" / "Templates")
                user_dirs = getattr(s, 'workflow_template_sources', []) if s else []
                all_dirs = [d for d in [bundled_templates] + user_dirs if Path(d).exists()]
                if all_dirs:
                    tmpl_count = scanner.scan_sources(all_dirs)

                rules_loader = RulesLoader()
                bundled_rules = [
                    str(bundled_root / "02_Universal"),
                    str(bundled_root / "03_Advanced"),
                ]
                user_rules = getattr(s, 'workflow_rules_sources', []) if s else []
                rules_all = [d for d in bundled_rules + user_rules if Path(d).exists()]
                if rules_all:
                    rules_loader.index_sources(rules_all)
                    if hasattr(rules_loader, '_index'):
                        rules_count = len(rules_loader._index)
            except Exception:
                pass

            self._badges_layout.addWidget(
                self._make_badge(f"Templates: {tmpl_count}", Theme.GREEN if tmpl_count > 0 else Theme.RED)
            )
            self._badges_layout.addWidget(
                self._make_badge(f"Rules: {rules_count}", Theme.GREEN if rules_count > 0 else Theme.YELLOW)
            )

            # API config
            try:
                source = getattr(s, 'pb_ai_source', 'account')
                model = getattr(s, 'pb_ai_model', 'gemini-2.0-flash')

                if source == 'custom':
                    keys = getattr(s, 'pb_ai_custom_keys', [])
                    if keys:
                        k = keys[0].strip()
                        key_short = f"{k[:8]}...{k[-4:]}" if len(k) > 12 else k
                        self._badges_layout.addWidget(
                            self._make_badge(f"API: {key_short}", Theme.GREEN)
                        )
                    else:
                        self._badges_layout.addWidget(
                            self._make_badge("API: ❌ No custom key", Theme.RED)
                        )
                else:
                    # Check profile keys
                    try:
                        from services.gemini_key_manager import GeminiKeyManager
                        mgr = GeminiKeyManager()
                        all_keys = mgr._load_all()
                        if all_keys:
                            first = next(iter(all_keys))
                            api_key = mgr.get_key(first)
                            if api_key:
                                key_short = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else api_key
                                self._badges_layout.addWidget(
                                    self._make_badge(f"API: {key_short}", Theme.GREEN)
                                )
                            else:
                                self._badges_layout.addWidget(
                                    self._make_badge("API: ❌ Key empty", Theme.RED)
                                )
                        else:
                            self._badges_layout.addWidget(
                                self._make_badge("API: ❌ No profile key", Theme.RED)
                            )
                    except Exception:
                        self._badges_layout.addWidget(
                            self._make_badge("API: ❌ Error", Theme.RED)
                        )

                self._badges_layout.addWidget(
                    self._make_badge(f"Model: {model}", Theme.BLUE)
                )
                self._badges_layout.addWidget(
                    self._make_badge(f"Source: {source}", Theme.SURFACE2)
                )
            except Exception:
                self._badges_layout.addWidget(
                    self._make_badge("API: ❌ Config error", Theme.RED)
                )

        except Exception as e:
            self._badges_layout.addWidget(
                self._make_badge(f"Error: {str(e)[:40]}", Theme.RED)
            )

        self._badges_layout.addStretch()

        # Log the diagnostic refresh
        self.append_log("[Diag] Diagnostics refreshed")

    @Slot(str)
    def append_log(self, text: str):
        """Append a timestamped line to the log viewer."""
        import time
        ts = time.strftime("%H:%M:%S")
        self._log_view.append(f"[{ts}] {text}")
        # Auto-scroll
        scrollbar = self._log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        # Update stats
        lines = self._log_view.document().blockCount()
        self._stats_label.setText(f"{lines} log lines")
