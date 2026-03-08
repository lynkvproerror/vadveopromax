"""
VEO Pro Max - Project Builder Tab (PySide6)

UI for AI-powered project generation:
- Left: Setup Matrix panel (8 content dimensions + production settings)
- Right: Topics input + Parsed Projects panel

Supports Semi-Manual mode (no API) and Full Auto mode.

Fixes applied:
- Fix 1: Background thread generation (no main thread blocking)
- Fix 2: Auto-add to Queue checkbox
- Fix 5: Rich per-topic status panel
- Fix 6: Settings AI config integration (custom provider/model/keys)
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTextEdit, QFrame,
    QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox,
)
from PySide6.QtCore import Qt, Signal, Slot, QObject, QThread, QTimer

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.theme import Theme
from config.i18n import t

try:
    from core.app_controller import AppController
except ImportError:
    AppController = None  # type: ignore

try:
    from ui.tabs.project_components.setup_matrix import SetupMatrixPanel
    from ui.tabs.project_components.parsed_projects import ParsedProjectsPanel
except ImportError:
    SetupMatrixPanel = None  # type: ignore
    ParsedProjectsPanel = None  # type: ignore

log = logging.getLogger("veo.tab_project")


# ── Background Worker ──────────────────────────────────────────

class _GenerationWorker(QObject):
    """Runs ProjectBuilder.process_batch in a background thread."""

    # Signals for thread-safe UI updates
    step_update = Signal(str, str, int, int)   # step, topic, step_num, topic_index
    topic_done = Signal(int, str, str)          # topic_index, status, error
    all_done = Signal(list)                     # List[TopicResult]
    error = Signal(str)                         # Fatal error message
    log_msg = Signal(str)                       # Debug log line

    def __init__(self, topics, template, api_key, output_base,
                 scanner, rules_loader, model_name="", base_url="", provider="Google",
                 matrix_config=None):
        super().__init__()
        self.topics = topics
        self.template = template
        self.api_key = api_key
        self.output_base = output_base
        self.scanner = scanner
        self.rules_loader = rules_loader
        self.model_name = model_name
        self.base_url = base_url
        self.provider = provider
        self.matrix_config = matrix_config or {}

    @Slot()
    def run(self):
        """Execute generation in background thread."""
        try:
            self.log_msg.emit(f"[Worker] Starting generation: {len(self.topics)} topics")
            self.log_msg.emit(f"[Worker] Template: {self.template.display_name if self.template else 'None'}")
            self.log_msg.emit(f"[Worker] Model: {self.model_name or 'default'}")
            self.log_msg.emit(f"[Worker] Provider: {self.provider}")
            if self.base_url:
                self.log_msg.emit(f"[Worker] Base URL: {self.base_url}")

            # Create correct client based on provider
            from services.ai_client_factory import create_ai_client
            from core.project_builder import ProjectBuilder
            client = create_ai_client(self.provider, self.base_url)

            builder = ProjectBuilder(
                gemini_client=client,
                scanner=self.scanner,
                rules_loader=self.rules_loader,
            )

            # Wire progress callbacks
            topic_idx = [0]  # mutable closure
            def on_step(step, topic, step_num):
                self.log_msg.emit(f"[Step {step_num}] {step}: {topic[:60]}")
                self.step_update.emit(step, topic, step_num, topic_idx[0])
            builder.on_step_start = on_step

            def on_topic(result):
                status = result.status
                err = result.error or ""
                if status == 'done':
                    self.log_msg.emit(f"[Topic {topic_idx[0]+1}] ✅ Done")
                else:
                    self.log_msg.emit(f"[Topic {topic_idx[0]+1}] ❌ Error: {err}")
                self.topic_done.emit(topic_idx[0], status, err)
                topic_idx[0] += 1
            builder.on_topic_done = on_topic

            # Run async generation in a new event loop (this thread only)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(
                builder.process_batch(
                    self.topics, self.template, self.api_key, self.output_base,
                    model=self.model_name,
                    matrix_config=self.matrix_config,
                )
            )
            loop.close()

            self.log_msg.emit(f"[Worker] Generation complete: {len(results)} results")
            self.all_done.emit(results)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.log_msg.emit(f"[Worker] FATAL ERROR:\n{tb}")
            self.error.emit(str(e))
            log.error(f"[GenerationWorker] Fatal: {e}")


class TabProject(QWidget):
    """Project Builder tab — AI-powered VEO project generation."""

    # Signal: prompts ready to add to queue
    prompts_ready = Signal(list)  # List[dict] with prompt + config

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._scanner = None
        self._rules_loader = None
        self._worker_thread = None
        self._worker = None
        self._setup_matrix = None # Added for SetupMatrixPanel
        self._parsed_panel = None # Added for ParsedProjectsPanel

        self._setup_ui()
        self._init_builder()

    def _init_builder(self):
        """Initialize builder components (lazy)."""
        try:
            from core.workflow_scanner import WorkflowScanner
            from core.rules_loader import RulesLoader

            self._scanner = WorkflowScanner()
            self._rules_loader = RulesLoader()

            # Always auto-scan (bundled data + user sources)
            self._do_rescan()
        except Exception as e:
            log.debug(f"[TabProject] Init builder: {e}")

    def _do_rescan(self):
        """Rescan workflow and rules sources.

        Auto-includes bundled data/workflows/ + user's custom dirs from Settings.
        Supports hot-update: user can add/edit .md files and Rescan.
        """
        try:
            from config.settings import get_settings
            s = get_settings()

            # ── Bundled data paths (always included) ──
            bundled_root = Path(__file__).parent.parent.parent / "data" / "workflows"
            bundled_templates = str(bundled_root / "02_Universal" / "Templates")
            bundled_rules = [
                str(bundled_root / "02_Universal"),
                str(bundled_root / "03_Advanced"),
            ]
            bundled_research = str(bundled_root / "01_Research")

            # ── User's custom dirs from Settings ──
            user_template_dirs = getattr(s, 'workflow_template_sources', []) if s else []
            user_rules_dirs = getattr(s, 'workflow_rules_sources', []) if s else []

            # ── Merge: bundled + user (dedup) ──
            template_dirs = self._merge_dirs([bundled_templates], user_template_dirs)
            rules_dirs = self._merge_dirs(bundled_rules, user_rules_dirs)

            # ── Scan templates ──
            tmpl_count = 0
            if self._scanner and template_dirs:
                tmpl_count = self._scanner.scan_sources(template_dirs)

            # ── Scan rules ──
            if self._rules_loader and rules_dirs:
                self._rules_loader.index_sources(rules_dirs)

            # ── Update UI labels (old sidebar, if present) ──
            if hasattr(self, '_sources_label'):
                self._sources_label.setText(f"Sources: {len(template_dirs)}")
            if hasattr(self, '_templates_label'):
                self._templates_label.setText(f"Templates: {tmpl_count}")
            if hasattr(self, '_template_combo'):
                self._update_template_dropdown()

            log.info(
                f"[TabProject] Rescan: {tmpl_count} templates from "
                f"{len(template_dirs)} template dirs, {len(rules_dirs)} rules dirs"
            )

        except Exception as e:
            log.debug(f"[TabProject] Rescan error: {e}")

    @staticmethod
    def _merge_dirs(bundled: list, user: list) -> list:
        """Merge bundled + user dirs, deduplicating and filtering non-existent."""
        seen = set()
        result = []
        for d in bundled + user:
            norm = str(Path(d).resolve())
            if norm not in seen and Path(d).exists():
                seen.add(norm)
                result.append(d)
        return result

    # ── UI Setup ───────────────────────────────────────────────

    def _setup_ui(self):
        """Build the tab layout: Setup Matrix + Workspace."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ── SETUP MATRIX (fixed width sidebar — matches GenerationTabBase) ──
        if SetupMatrixPanel:
            self._setup_matrix = SetupMatrixPanel()
            main_layout.addWidget(self._setup_matrix)
        else:
            # Fallback: old sidebar if component not available
            self._setup_matrix = None
            sidebar = self._create_sidebar()
            main_layout.addWidget(sidebar)

        # ── WORKSPACE ──
        workspace = self._create_workspace()
        main_layout.addWidget(workspace, stretch=1)

    def _create_sidebar(self) -> QWidget:
        """Create sidebar with workflow + VEO settings."""
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.SURFACE0};
                border-right: 1px solid {Theme.BORDER};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── WORKFLOW Section ──
        wf_header = QLabel("── WORKFLOW ──")
        wf_header.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(wf_header)

        self._sources_label = QLabel("Sources: 0")
        self._sources_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; border: none;")
        layout.addWidget(self._sources_label)

        self._templates_label = QLabel("Templates: 0")
        self._templates_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; border: none;")
        layout.addWidget(self._templates_label)

        # Rescan button
        rescan_btn = QPushButton("🔄 Rescan")
        rescan_btn.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"height: 28px; border-radius: 4px; border: none;"
        )
        rescan_btn.clicked.connect(self._do_rescan)
        layout.addWidget(rescan_btn)

        # Template dropdown
        tmpl_label = QLabel("Template:")
        tmpl_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
        layout.addWidget(tmpl_label)

        self._template_combo = QComboBox()
        self._template_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        layout.addWidget(self._template_combo)

        # ── VEO Section ──
        layout.addSpacing(16)
        veo_header = QLabel("── VEO ──")
        veo_header.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(veo_header)

        # Aspect ratio
        ar_label = QLabel("Aspect:")
        ar_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
        layout.addWidget(ar_label)
        self._aspect_combo = QComboBox()
        self._aspect_combo.addItems(["16:9 (Landscape)", "9:16 (Portrait)"])
        self._aspect_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        layout.addWidget(self._aspect_combo)

        # Output folder
        out_label = QLabel("📂 Output:")
        out_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; border: none;")
        layout.addWidget(out_label)
        out_btn = QPushButton("Browse...")
        out_btn.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"height: 28px; border-radius: 4px; border: none;"
        )
        out_btn.clicked.connect(self._browse_output)
        layout.addWidget(out_btn)
        self._output_label = QLabel("Not set")
        self._output_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px; border: none;")
        self._output_label.setWordWrap(True)
        layout.addWidget(self._output_label)

        layout.addStretch()
        return sidebar

    def _create_workspace(self) -> QWidget:
        """Create workspace with Phase-Aware Layout.
        
        INPUT phase:  Topics expanded, Parsed empty
        GENERATE:     Topics auto-collapse, progress bar active
        REVIEW phase: Topics collapsed, Parsed+Viewer stretch
        """
        workspace = QFrame()
        workspace.setStyleSheet(f"background-color: {Theme.BASE};")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ═══════════════════════════════════════════════════
        # SECTION 1: Topics Input (collapsible)
        # ═══════════════════════════════════════════════════
        topics_section = QFrame()
        topics_section.setStyleSheet(f"background-color: {Theme.SURFACE0};")
        topics_layout = QVBoxLayout(topics_section)
        topics_layout.setContentsMargins(0, 0, 0, 0)
        topics_layout.setSpacing(0)

        # Color header (clickable — collapse/expand)
        self._topics_header = QPushButton("📝 TOPICS INPUT ▼")
        self._topics_header.setFixedHeight(32)
        self._topics_header.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.GREEN};
                color: {Theme.CRUST};
                font-weight: bold;
                border: none;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                background-color: {Theme.GREEN};
            }}
        """)
        self._topics_header.setCursor(Qt.CursorShape.PointingHandCursor)
        topics_layout.addWidget(self._topics_header)

        # Collapsible body
        self._topics_body = QWidget()
        body_layout = QVBoxLayout(self._topics_body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(6)

        self._topic_input = QTextEdit()
        self._topic_input.setAcceptRichText(False)  # ★ Force plain-text paste (Google Sheets sends HTML <table>)
        self._topic_input.setPlaceholderText(
            "Enter topics, one per line:\n"
            "Tác hại ăn mì tôm\n"
            "10 loại trái cây tốt cho sức khỏe\n"
            "Cách tiết kiệm tiền hiệu quả"
        )
        self._topic_input.setMaximumHeight(120)
        self._topic_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }}
        """)
        # Auto-detect on text change (debounced)
        self._detect_timer = QTimer()
        self._detect_timer.setSingleShot(True)
        self._detect_timer.setInterval(500)
        self._detect_timer.timeout.connect(self._on_detect_timeout)
        self._topic_input.textChanged.connect(lambda: self._detect_timer.start())
        body_layout.addWidget(self._topic_input)

        # Auto-detect badges
        self._detect_frame = QFrame()
        self._detect_layout = QHBoxLayout(self._detect_frame)
        self._detect_layout.setContentsMargins(0, 0, 0, 0)
        self._detect_layout.setSpacing(6)
        self._detect_layout.addStretch()
        body_layout.addWidget(self._detect_frame)

        # Action buttons row
        btn_row = QHBoxLayout()

        self._generate_btn = QPushButton("🚀 Generate (Full Auto)")
        self._generate_btn.setStyleSheet(
            f"background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
            f"height: 36px; font-weight: bold; border-radius: 6px;"
        )
        self._generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self._generate_btn)

        import_btn = QPushButton("📋 Import Prompts")
        import_btn.setStyleSheet(
            f"background-color: {Theme.SURFACE2}; color: {Theme.TEXT}; "
            f"height: 36px; border-radius: 6px;"
        )
        import_btn.clicked.connect(self._on_import_prompts)
        btn_row.addWidget(import_btn)

        self._auto_add_cb = QCheckBox("Auto-add to Queue")
        self._auto_add_cb.setStyleSheet(f"""
            QCheckBox {{ color: {Theme.TEXT}; font-size: 12px; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 4px;
                border: 2px solid {Theme.SUBTEXT0};
                background-color: {Theme.SURFACE0};
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid {Theme.BLUE};
                background-color: {Theme.BLUE};
            }}
        """)
        self._auto_add_cb.setChecked(True)
        btn_row.addWidget(self._auto_add_cb)

        btn_row.addStretch()
        body_layout.addLayout(btn_row)

        topics_layout.addWidget(self._topics_body)

        # Progress bar (thin 4px — hidden by default)
        from PySide6.QtWidgets import QProgressBar
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Theme.SURFACE1};
                border: none;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.GREEN};
            }}
        """)
        self._progress_bar.setVisible(False)
        topics_layout.addWidget(self._progress_bar)

        layout.addWidget(topics_section)

        # Toggle topics collapse/expand
        self._topics_expanded = True
        def _toggle_topics():
            self._topics_expanded = not self._topics_expanded
            self._topics_body.setVisible(self._topics_expanded)
            arrow = "▼" if self._topics_expanded else "▶"
            count = len([ln for ln in self._topic_input.toPlainText().strip().split("\n") if ln.strip()])
            if self._topics_expanded:
                self._topics_header.setText(f"📝 TOPICS INPUT {arrow}")
            else:
                self._topics_header.setText(f"📝 TOPICS ({count} topics) {arrow}")
        self._topics_header.clicked.connect(_toggle_topics)

        # ═══════════════════════════════════════════════════
        # SECTION 2: Parsed Projects (stretch=1)
        # ═══════════════════════════════════════════════════
        if ParsedProjectsPanel:
            self._parsed_panel = ParsedProjectsPanel()
            self._parsed_panel.add_project_to_queue.connect(self._on_add_project_to_queue)
            self._parsed_panel.add_all_to_queue.connect(self._on_add_all_to_queue)
            layout.addWidget(self._parsed_panel, stretch=1)
        else:
            # Fallback: old flat table
            self._parsed_panel = None
            table_header = QLabel("📊 Parsed Prompts")
            table_header.setStyleSheet(f"color: {Theme.TEXT}; font-size: 14px; font-weight: bold;")
            layout.addWidget(table_header)

            self._prompts_table = QTableWidget(0, 3)
            self._prompts_table.setHorizontalHeaderLabels(["#", "Prompt", "Status"])
            self._prompts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self._prompts_table.setColumnWidth(0, 40)
            self._prompts_table.setColumnWidth(2, 80)
            self._prompts_table.setStyleSheet(f"""
                QTableWidget {{
                    background-color: {Theme.SURFACE0};
                    color: {Theme.TEXT};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 4px;
                    gridline-color: {Theme.BORDER};
                }}
                QHeaderView::section {{
                    background-color: {Theme.SURFACE1};
                    color: {Theme.TEXT};
                    padding: 6px;
                    border: 1px solid {Theme.BORDER};
                    font-weight: bold;
                }}
            """)
            layout.addWidget(self._prompts_table, stretch=1)

            queue_btn = QPushButton("📤 Add All to Queue")
            queue_btn.setStyleSheet(
                f"background-color: {Theme.BLUE}; color: white; "
                f"height: 36px; font-weight: bold; border-radius: 6px;"
            )
            queue_btn.clicked.connect(self._on_add_to_queue)
            layout.addWidget(queue_btn)

        # Dummy status references (for backward compat — no-op)
        self._topic_status_labels: List[QLabel] = []

        return workspace

    # ── Template Dropdown ──────────────────────────────────────

    def _update_template_dropdown(self):
        """Refresh template dropdown with discovered templates."""
        self._template_combo.clear()
        if not self._scanner:
            return

        for tmpl in self._scanner.templates:
            label = f"[{tmpl.group}] {tmpl.display_name}" if tmpl.is_tagged else tmpl.display_name
            self._template_combo.addItem(label, tmpl.template_id)

    def _get_selected_template(self):
        """Get currently selected template."""
        if self._setup_matrix:
            # In new design: auto-detect from WorkflowScanner based on topics
            if self._scanner and self._scanner.templates:
                topics = self._topic_input.toPlainText().strip()
                if topics:
                    matches = self._scanner.detect_mode(topics.split("\n")[0].strip())
                    if matches:
                        return matches[0].template
                # Fallback: first template
                return self._scanner.templates[0] if self._scanner.templates else None
            return None
        
        # Fallback for old sidebar
        if not self._scanner:
            return None
        idx = self._template_combo.currentIndex()
        if idx < 0 or idx >= len(self._scanner.templates):
            return None
        return self._scanner.templates[idx]

    # ── Auto-detect ────────────────────────────────────────────

    def _on_detect_timeout(self):
        """Run auto-detect on current topic text."""
        text = self._topic_input.toPlainText().strip()
        if not text or not self._scanner:
            self._clear_detect_badges()
            return

        # Use first line for detection
        first_line = text.split("\n")[0].strip()
        if not first_line:
            return

        # ── Auto-update sidebar from tab columns ──
        self._topic_col_idx = 0  # default: topic is column 0
        if "\t" in first_line:
            if self._setup_matrix:
                columns = first_line.split("\t")
                log.info(
                    f"[TabProject] Auto-detect: {len(columns)} columns "
                    f"from tab-separated input"
                )
                if len(columns) >= 2:
                    try:
                        self._topic_col_idx = self._setup_matrix.set_from_tab_columns(columns)
                        log.info(
                            f"[TabProject] Topic column index: {self._topic_col_idx}"
                        )
                    except Exception as e:
                        log.warning(f"[TabProject] set_from_tab_columns error: {e}")
            else:
                log.warning(
                    "[TabProject] Tab columns detected but SetupMatrixPanel "
                    "is not available (import failed?)"
                )

        # Template detection (use detected topic column)
        if "\t" in first_line:
            parts = first_line.split("\t")
            first_topic = parts[self._topic_col_idx].strip() if self._topic_col_idx < len(parts) else parts[0].strip()
        else:
            first_topic = first_line
        matches = self._scanner.detect_mode(first_topic)
        self._show_detect_badges(matches)

    def _show_detect_badges(self, matches):
        """Show auto-detect result badges."""
        self._clear_detect_badges()

        for match in matches:
            pct = int(match.confidence * 100)
            color = Theme.GREEN if pct >= 70 else Theme.YELLOW if pct >= 40 else Theme.SUBTEXT0
            badge = QLabel(f"  {match.template.display_name} {pct}%  ")
            badge.setStyleSheet(
                f"background-color: {color}; color: {Theme.CRUST}; "
                f"font-size: 11px; font-weight: bold; "
                f"padding: 3px 8px; border-radius: 10px;"
            )
            self._detect_layout.insertWidget(self._detect_layout.count() - 1, badge)

    def _clear_detect_badges(self):
        """Clear all detect badges."""
        while self._detect_layout.count() > 1:
            item = self._detect_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _route_worker_log(self, text: str):
        """Route worker log messages to DevConsole Gemini API page via logging."""
        log.info(f"[ProjectBuilder] {text}")
        # Also send directly to DevConsole's Gemini page if available
        if self.controller and hasattr(self.controller, 'dev_console') and self.controller.dev_console:
            dev = self.controller.dev_console
            if hasattr(dev, '_gemini_page'):
                dev._gemini_page.append_log(text)

    # ── Settings Integration (Fix 6) ───────────────────────────

    def _get_ai_config(self):
        """Get API key, model, base URL, and provider from Settings tab config.

        Returns:
            (api_key, model_name, base_url, provider) or raises ValueError.
        """
        from config.settings import get_settings
        s = get_settings()

        source = getattr(s, 'pb_ai_source', 'account')
        model = getattr(s, 'pb_ai_model', 'gemini-2.5-flash')
        base_url = getattr(s, 'pb_ai_base_url', '') or ''
        provider = getattr(s, 'pb_ai_provider', 'Google')

        if source == 'custom':
            # Use custom API keys from Settings
            keys = getattr(s, 'pb_ai_custom_keys', [])
            if not keys:
                raise ValueError(
                    "Chưa có Custom API key!\n"
                    "Vào Settings → AI Prompt Processing → Project Builder để nhập key."
                )
            # Round-robin: use first key (could implement rotation later)
            api_key = keys[0].strip()
            if not api_key:
                raise ValueError("Custom API key trống!")
            return api_key, model, base_url, provider
        else:
            # Use key from Profile (GeminiKeyManager)
            try:
                from services.gemini_key_manager import GeminiKeyManager
                mgr = GeminiKeyManager()
                all_keys = mgr._load_all()
                if all_keys:
                    first = next(iter(all_keys))
                    api_key = mgr.get_key(first)
                    if api_key:
                        return api_key, model, base_url, provider
            except Exception:
                pass
            raise ValueError(
                "Chưa có Gemini API key!\n"
                "Vào Settings → AI Prompt Processing để paste key."
            )

    # ── Phase-Aware Status (replaces old status panel) ─────────

    def _init_status_panel(self, topics):
        """Phase transition: INPUT → GENERATING.
        
        Auto-collapse Topics, show progress bar.
        """
        self._total_topics = len(topics)
        self._done_topics = 0

        # Auto-collapse Topics section to save space
        if self._topics_expanded:
            self._topics_expanded = False
            self._topics_body.setVisible(False)
            self._topics_header.setText(f"📝 TOPICS ({self._total_topics} topics) ▶")

        # Show progress bar
        self._progress_bar.setMaximum(self._total_topics)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)

    def _update_topic_step(self, step, topic, step_num, topic_idx):
        """Update progress bar during generation."""
        # Progress = completed topics + partial current topic
        partial = (step_num - 1) / 4  # 4 steps per topic
        progress = int((topic_idx + partial) / self._total_topics * 100)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(progress)

        # Update header with current step info
        short = topic[:30] + "..." if len(topic) > 30 else topic
        self._topics_header.setText(
            f"⏳ [{topic_idx+1}/{self._total_topics}] {step} — {short}"
        )

    def _update_topic_done(self, topic_idx, status, error):
        """Update per-topic completion — update progress bar + ProjectRow status."""
        self._done_topics = topic_idx + 1
        self._progress_bar.setMaximum(self._total_topics)
        self._progress_bar.setValue(self._done_topics)

        # Update ProjectRow status badge (if panel exists)
        if self._parsed_panel and hasattr(self._parsed_panel, 'set_project_status'):
            proj_status = "queued" if status == "done" else "error"
            if topic_idx < self._parsed_panel.get_project_count():
                self._parsed_panel.set_project_status(topic_idx, proj_status)

    # ── Actions ────────────────────────────────────────────────

    def _on_generate(self):
        """Start full auto generation (Fix 1: runs in background thread)."""
        topics = self._topic_input.toPlainText().strip()
        if not topics:
            from ui.popups import show_warning
            show_warning(self, "No Topics", "Nhập ít nhất 1 topic!")
            return

        template = self._get_selected_template()
        if not template:
            from ui.popups import show_warning
            show_warning(self, "No Template", "Chọn template trước!")
            return

        # ── Validate Setup Matrix (required dimensions) ──
        matrix_config = {}
        if self._setup_matrix:
            matrix_config = self._setup_matrix.get_config()
            missing = []
            required_dims = [
                ("category",  "Category (D1)"),
                ("structure", "Structure (D2)"),
                ("style",     "Visual Style (D3)"),
                ("character", "Character (D4)"),
                ("audience",  "Audience (D5)"),
                ("tone",      "Tone (D7)"),
            ]
            for key, label in required_dims:
                val = matrix_config.get(key, [])
                if isinstance(val, list) and not val:
                    missing.append(label)
                elif not val:
                    missing.append(label)
            
            if not matrix_config.get("output_folder"):
                missing.append("📂 Output Folder")
            
            if missing:
                from ui.popups import show_warning
                msg = "Vui lòng chọn đủ thông tin:\n\n• " + "\n• ".join(missing)
                show_warning(self, "Thiếu thông tin", msg)
                return

        # Get API config from Settings (Fix 6)
        try:
            api_key, model_name, base_url, provider = self._get_ai_config()
        except ValueError as e:
            from ui.popups import show_warning
            show_warning(self, "API Error", str(e))
            return

        # Extract topic names from lines (handle tab-separated columns)
        topic_col_idx = getattr(self, '_topic_col_idx', 0)
        topic_list = []
        for ln in topics.split("\n"):
            ln = ln.strip()
            if not ln:
                continue
            if "\t" in ln:
                parts = ln.split("\t")
                topic = parts[topic_col_idx].strip() if topic_col_idx < len(parts) else parts[0].strip()
            else:
                topic = ln
            if topic:
                topic_list.append(topic)

        # Initialize rich status panel (Fix 5)
        self._init_status_panel(topic_list)

        # Disable generate button during generation
        self._generate_btn.setEnabled(False)
        self._generate_btn.setText("⏳ Generating...")

        output_base = ""
        if self._setup_matrix:
            output_base = self._setup_matrix.output_folder.text()
        elif hasattr(self, '_output_label'):
            output_base = self._output_label.text()
            if output_base == "Not set":
                output_base = ""

        # Run in background thread (Fix 1)
        self._worker_thread = QThread()
        self._worker = _GenerationWorker(
            topics=topic_list,
            template=template,
            api_key=api_key,
            output_base=output_base,
            scanner=self._scanner,
            rules_loader=self._rules_loader,
            model_name=model_name,
            base_url=base_url,
            provider=provider,
            matrix_config=matrix_config,
        )
        self._worker.moveToThread(self._worker_thread)

        # Connect signals
        self._worker_thread.started.connect(self._worker.run)
        self._worker.step_update.connect(self._update_topic_step)
        self._worker.topic_done.connect(self._update_topic_done)
        self._worker.all_done.connect(self._on_generation_done)
        self._worker.error.connect(self._on_generation_error)
        self._worker.log_msg.connect(self._route_worker_log)

        # Cleanup when done
        self._worker.all_done.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)

        self._worker_thread.start()

    def _on_generation_done(self, results):
        """Handle generation completion (runs on main thread via signal)."""
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("🚀 Generate (Full Auto)")

        # Complete progress bar
        self._progress_bar.setValue(self._progress_bar.maximum())

        # Display results in parsed projects panel
        all_prompts = []
        done_count = 0
        for r in results:
            if r.status == "done":
                all_prompts.extend(r.prompts)
                done_count += 1

                # Add to parsed panel if available
                if self._parsed_panel:
                    files = {}
                    if hasattr(r, 'files'):
                        files = r.files  # {"Bible": content, "Master": content, ...}
                    status = "queued" if self._auto_add_cb.isChecked() else "ready"
                    self._parsed_panel.add_project(r.topic, files, status)
            elif self._parsed_panel and hasattr(r, 'topic'):
                self._parsed_panel.add_project(
                    r.topic, {}, "error"
                )

        # Legacy fallback: populate old table
        if not self._parsed_panel:
            self._show_prompts_in_table(all_prompts)

        # Update header with final status
        total = len(results)
        self._topics_header.setText(
            f"✅ Done: {done_count}/{total} topics, {len(all_prompts)} prompts ▶"
        )

        # Auto-add to Queue
        if self._auto_add_cb.isChecked() and all_prompts:
            self._on_add_to_queue()

    def _on_generation_error(self, error_msg):
        """Handle fatal generation error."""
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText("🚀 Generate (Full Auto)")
        self._status_summary.setText(f"❌ Fatal Error: {error_msg}")
        self._status_summary.setStyleSheet(
            f"color: {Theme.RED}; font-size: 12px; font-weight: bold; border: none;"
        )

    def _on_import_prompts(self):
        """Import prompts from clipboard or file (Semi-Manual mode)."""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Import Prompts",
            "Paste VEO prompts (1 per line):",
            "",
        )
        if ok and text.strip():
            template = self._get_selected_template()
            if not template:
                # Create a minimal template
                from core.workflow_scanner import WorkflowTemplate
                template = WorkflowTemplate(display_name="Manual")

            from core.project_builder import ProjectBuilder
            builder = ProjectBuilder()
            prompts = builder.import_prompts(text, template)

            if self._parsed_panel:
                # For imported prompts, we don't have files, just the prompt text
                # Create a dummy project entry for each imported prompt
                for i, p in enumerate(prompts):
                    self._parsed_panel.add_project(
                        f"Imported Prompt {i+1}",
                        {"Master": p.prompt}, # Store prompt in 'Master' file for display
                        "ready"
                    )
            else:
                self._show_prompts_in_table(prompts)

            self._status_summary.setText(f"✅ Imported {len(prompts)} prompts")
            self._status_frame.setVisible(True)

            # Auto-add if enabled
            if self._auto_add_cb.isChecked() and prompts:
                self._on_add_to_queue()

    def _show_prompts_in_table(self, prompts):
        """Populate the prompts table."""
        self._prompts_table.setRowCount(len(prompts))
        for i, p in enumerate(prompts):
            self._prompts_table.setItem(i, 0, QTableWidgetItem(str(p.index)))
            self._prompts_table.setItem(i, 1, QTableWidgetItem(p.prompt))
            status = "✅" if p.valid else f"⚠️ {', '.join(p.violations)}"
            self._prompts_table.setItem(i, 2, QTableWidgetItem(status))

    def _on_add_to_queue(self):
        """Add all parsed prompts to the VEO queue."""
        if self._parsed_panel:
            self._on_add_all_to_queue()
            return

        # Legacy: flat table fallback
        if not hasattr(self, '_prompts_table'):
            return
        row_count = self._prompts_table.rowCount()
        if row_count == 0:
            from ui.popups import show_warning
            show_warning(self, "Empty", "Chưa có prompts để thêm!")
            return

        prompts = []
        for i in range(row_count):
            item = self._prompts_table.item(i, 1)
            if item:
                prompts.append(item.text())

        self._do_queue_add(prompts, "Project Builder")

    def _on_add_project_to_queue(self, project_idx: int):
        """Add a single project's prompts to queue."""
        if not self._parsed_panel:
            return
        data = self._parsed_panel._project_data
        if project_idx < len(data):
            prompts_text = data[project_idx].get("Prompts", "")
            prompts = [ln.strip() for ln in prompts_text.split("\n") if ln.strip()]
            name = self._parsed_panel._projects[project_idx].name
            self._do_queue_add(prompts, name)
            self._parsed_panel.set_project_status(project_idx, "queued")

    def _on_add_all_to_queue(self):
        """Add all ready projects to queue."""
        if not self._parsed_panel:
            return
        for i, row in enumerate(self._parsed_panel._projects):
            if row.get_status() == "ready":
                self._on_add_project_to_queue(i)

    def _do_queue_add(self, prompts: list, project_name: str):
        """Common queue-add logic."""
        if not prompts:
            return

        # Build settings dict from SetupMatrixPanel or legacy
        settings = {"project_name": project_name}
        if self._setup_matrix:
            config = self._setup_matrix.get_config()
            settings["aspect_ratio"] = config.get("video_aspect", "LANDSCAPE")
            settings["output_folder"] = config.get("output_folder", "")
            settings["model"] = config.get("video_model", "Veo 3.1 - Fast")
            settings["download_quality"] = config.get("video_quality", "1080p")
            settings["outputs_per_prompt"] = config.get("video_outputs", 4)
        elif hasattr(self, '_aspect_combo'):
            settings["aspect_ratio"] = "LANDSCAPE" if "Landscape" in self._aspect_combo.currentText() else "PORTRAIT"

        if self.controller and hasattr(self.controller, 'add_t2v_batch'):
            self.controller.add_t2v_batch(
                prompts=prompts,
                settings=settings,
            )
            from ui.popups import show_info
            show_info(self, "Added", f"✅ {len(prompts)} prompts added to queue!")
        else:
            from ui.popups import show_info
            show_info(self, "Ready", f"📋 {len(prompts)} prompts ready (controller not connected)")

    def _browse_output(self):
        """Browse for output folder."""
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            if hasattr(self, '_output_label'):
                self._output_label.setText(folder)
            if self._setup_matrix:
                self._setup_matrix.output_folder.setText(folder)

    def retranslate_ui(self):
        """Hot-reload UI text on language change."""
        pass  # Tab labels managed by app.py
