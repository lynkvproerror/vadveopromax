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
    topic_result = Signal(int, str, dict, str)  # idx, topic_name, files_dict, status
    all_done = Signal(list)                     # List[TopicResult]
    error = Signal(str)                         # Fatal error message
    log_msg = Signal(str)                       # Debug log line

    def __init__(self, topics, template, api_key, output_base,
                 scanner, rules_loader, model_name="", base_url="", provider="Google",
                 matrix_config=None, prompt_format="text",
                 skip_seo=False, skip_research=False, skip_bible=False,
                 per_topic_template=False):
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
        self.prompt_format = prompt_format
        self.skip_seo = skip_seo
        self.skip_research = skip_research
        self.skip_bible = skip_bible
        self.per_topic_template = per_topic_template
        self._builder = None  # Reference for cancel support

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
            self._builder = builder  # Store for cancel support

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
                # Emit full result data for incremental UI update
                files = dict(result.files) if hasattr(result, 'files') and result.files else {}
                self.log_msg.emit(f"[Topic {topic_idx[0]+1}] Files keys: {list(files.keys())}")
                self.topic_result.emit(topic_idx[0], result.topic, files, status)
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
                    prompt_format=self.prompt_format,
                    skip_seo=self.skip_seo,
                    skip_research=self.skip_research,
                    skip_bible=self.skip_bible,
                    per_topic_template=self.per_topic_template,
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


class _StageWorker(QObject):
    """Runs a single pipeline stage in a background thread."""
    done = Signal(str, str, str)  # stage_name, result_text, error

    def __init__(self, pipeline, stage_name: str, config: dict):
        super().__init__()
        self._pipeline = pipeline
        self._stage = stage_name
        self._config = config

    def run(self):
        import asyncio
        import json
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self._pipeline.run_stage(self._stage, self._config)
            )
            loop.close()
            # Format result for display
            if result.error:
                self.done.emit(self._stage, "", result.error)
            else:
                display = self._format_result(result)
                self.done.emit(self._stage, display, "")
        except Exception as e:
            self.done.emit(self._stage, "", str(e))

    def _format_result(self, result) -> str:
        """Format stage result for human review."""
        import json
        lines = [f"✅ Stage: {self._stage}\n"]
        if self._stage == "duration_estimate":
            d = result.data
            lines.append(f"Topic: {d.get('topic', 'N/A')}")
            lines.append(f"Scene count: {d.get('scene_count', 0)}")
            lines.append(f"Clip duration: {d.get('clip_duration', 8)}s")
            total = d.get('target_duration', 0)
            mins, secs = total // 60, total % 60
            lines.append(f"Total duration: {mins}:{secs:02d}")
        elif self._stage == "script_analysis":
            lines.append("Script JSON:")
            lines.append(result.script_json if result.script_json else json.dumps(result.data, ensure_ascii=False, indent=2))
        elif self._stage == "scene_breakdown":
            lines.append(f"Generated {len(result.scenes)} scenes:\n")
            for s in result.scenes:
                lines.append(f"  Scene {s.index}: {s.title}")
                lines.append(f"    Image: {s.description[:100]}...")
                lines.append(f"    Video: {s.prompt[:100]}...")
                lines.append("")
        elif self._stage in ("character_gen", "scene_image_gen"):
            lines.append(f"Generated {len(result.prompts)} prompts:")
            for i, p in enumerate(result.prompts, 1):
                lines.append(f"  {i}. {p[:120]}...")
        else:
            lines.append(json.dumps(result.data, ensure_ascii=False, indent=2))
        return "\n".join(lines)


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
        self._pipeline_mode = "text_only"  # Pipeline mode tracking

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
        sidebar.setFixedWidth(Theme.SIDEBAR_WIDTH)
        sidebar.setObjectName("sidebarPanel")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(
            Theme.SIDEBAR_PADDING, Theme.SIDEBAR_PADDING,
            Theme.SIDEBAR_PADDING, Theme.SIDEBAR_PADDING
        )
        layout.setSpacing(Theme.SIDEBAR_SPACING)

        # ── WORKFLOW Section ──
        wf_header = QLabel(t("project_sidebar.workflow_header"))
        wf_header.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(wf_header)

        self._sources_label = QLabel(t("project_sidebar.sources").replace("{count}", "0"))
        self._sources_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; border: none;")
        layout.addWidget(self._sources_label)

        self._templates_label = QLabel(t("project_sidebar.templates").replace("{count}", "0"))
        self._templates_label.setStyleSheet(f"color: {Theme.TEXT}; font-size: 12px; border: none;")
        layout.addWidget(self._templates_label)

        rescan_btn = QPushButton(t("project_sidebar.rescan"))
        rescan_btn.setProperty("variant", "secondary")
        rescan_btn.setProperty("btnSize", "sm")
        rescan_btn.clicked.connect(self._do_rescan)
        layout.addWidget(rescan_btn)

        # Template dropdown
        tmpl_label = QLabel(t("project_sidebar.template_label"))
        tmpl_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(tmpl_label)
        self._aspect_combo = QComboBox()
        self._aspect_combo.addItems([t("project_sidebar.landscape"), t("project_sidebar.portrait")])
        layout.addWidget(self._aspect_combo)

        # Output folder
        out_label = QLabel(t("project_sidebar.output_label"))
        out_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; font-weight: bold; border: none;")
        layout.addWidget(out_label)
        out_btn = QPushButton(t("project_sidebar.browse"))
        out_btn.setProperty("variant", "secondary")
        out_btn.setProperty("btnSize", "sm")
        out_btn.clicked.connect(self._browse_output)
        layout.addWidget(out_btn)
        self._output_label = QLabel(t("project_sidebar.not_set"))
        self._output_label.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 10px; font-weight: bold; border: none;")
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
        workspace.setStyleSheet(f"QFrame {{ background-color: {Theme.BASE}; }}")
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ═══════════════════════════════════════════════════
        # SECTION 1: Topics Input (collapsible)
        # ═══════════════════════════════════════════════════
        topics_section = QFrame()
        topics_section.setStyleSheet(f"QFrame {{ background-color: {Theme.SURFACE0}; border-radius: 0px; }}")
        topics_layout = QVBoxLayout(topics_section)
        topics_layout.setContentsMargins(0, 0, 0, 0)
        topics_layout.setSpacing(0)

        # Color header (clickable — collapse/expand)
        self._topics_header = QPushButton(f"{t('project_builder.topics_header')} ▼")
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
        self._topic_input.setPlaceholderText(t("project_builder.topics_placeholder"))
        self._topic_input.setMaximumHeight(120)
        self._topic_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: 2px solid {Theme.BLUE};
                border-radius: 0px;
                padding: 8px;
                font-size: 13px;
            }}
            QTextEdit:focus {{
                border-color: {Theme.GREEN};
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

        self._generate_btn = QPushButton(t("project_builder.generate"))
        self._generate_btn.setProperty("variant", "success")
        self._generate_btn.setProperty("btnSize", "sm")
        self._generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self._generate_btn)

        import_btn = QPushButton(t("project_builder.import"))
        import_btn.setProperty("variant", "secondary")
        import_btn.setProperty("btnSize", "sm")
        import_btn.clicked.connect(self._on_import_prompts)
        btn_row.addWidget(import_btn)

        clear_btn = QPushButton(t("project_builder.clear"))
        clear_btn.setProperty("variant", "danger")
        clear_btn.setProperty("btnSize", "sm")
        clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(clear_btn)

        self._auto_add_cb = QCheckBox(t("project_builder.auto_add_queue"))
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

        # Prompt format toggle
        self._prompt_format_combo = QComboBox()
        self._prompt_format_combo.addItems(["Text", "JSON"])
        self._prompt_format_combo.setFixedWidth(70)
        self._prompt_format_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Theme.SURFACE1};
                color: {Theme.TEXT};
                border: none;
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 12px; font-weight: bold;
            }}
        """)
        self._prompt_format_combo.setToolTip("Prompt output format: Text (1 line/prompt) or JSON ({...})")
        btn_row.addWidget(self._prompt_format_combo)

        # Skip-step checkboxes (Fix #4, #12)
        skip_style = f"""
            QCheckBox {{ color: {Theme.SUBTEXT0}; font-size: 11px; spacing: 4px; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px; border-radius: 3px;
                border: 1px solid {Theme.SUBTEXT0};
                background-color: {Theme.SURFACE0};
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid {Theme.YELLOW};
                background-color: {Theme.YELLOW};
            }}
        """
        self._skip_research_cb = QCheckBox("Skip Research")
        self._skip_research_cb.setStyleSheet(skip_style)
        self._skip_research_cb.setToolTip("Skip AI research step (use when topic is well-known)")
        btn_row.addWidget(self._skip_research_cb)

        self._skip_seo_cb = QCheckBox("Skip SEO")
        self._skip_seo_cb.setStyleSheet(skip_style)
        self._skip_seo_cb.setToolTip("Skip SEO generation step")
        btn_row.addWidget(self._skip_seo_cb)

        self._per_topic_tmpl_cb = QCheckBox("Auto Template")
        self._per_topic_tmpl_cb.setStyleSheet(skip_style)
        self._per_topic_tmpl_cb.setChecked(True)
        self._per_topic_tmpl_cb.setToolTip("Auto-detect template for EACH topic (not just first line)")
        btn_row.addWidget(self._per_topic_tmpl_cb)

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
                background-color: {Theme.RED};
            }}
        """)
        self._progress_bar.setVisible(False)
        topics_layout.addWidget(self._progress_bar)

        self._cancel_btn = QPushButton(t("project_builder.cancel") if t("project_builder.cancel") != "project_builder.cancel" else "⛔ Cancel")
        self._cancel_btn.setProperty("variant", "danger")
        self._cancel_btn.setProperty("btnSize", "sm")
        self._cancel_btn.setFixedHeight(28)
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._on_cancel_generation)
        topics_layout.addWidget(self._cancel_btn)

        layout.addWidget(topics_section)

        # Toggle topics collapse/expand
        self._topics_expanded = True
        def _toggle_topics():
            self._topics_expanded = not self._topics_expanded
            self._topics_body.setVisible(self._topics_expanded)
            arrow = "▼" if self._topics_expanded else "▶"
            count = len([ln for ln in self._topic_input.toPlainText().strip().split("\n") if ln.strip()])
            if self._topics_expanded:
                self._topics_header.setText(f"{t('project_builder.topics_header')} {arrow}")
            else:
                self._topics_header.setText(f"📝 TOPICS ({count} topics) {arrow}")
        self._topics_header.clicked.connect(_toggle_topics)

        # ═══════════════════════════════════════════════════
        # SECTION 1.5: Stage Checkpoint Panel (Full Production)
        # ═══════════════════════════════════════════════════
        self._stage_panel = self._create_stage_panel()
        self._stage_panel.setVisible(False)  # Hidden until Full Production mode
        layout.addWidget(self._stage_panel, stretch=1)

        # Wire pipeline mode from sidebar
        if self._setup_matrix:
            self._setup_matrix.pipeline_mode_changed.connect(self._on_pipeline_mode_changed)

        # ═══════════════════════════════════════════════════
        # SECTION 2: Parsed Projects (stretch=1)
        # ═══════════════════════════════════════════════════
        if ParsedProjectsPanel:
            self._parsed_panel = ParsedProjectsPanel()
            self._parsed_panel.add_project_to_queue.connect(self._on_add_project_to_queue)
            self._parsed_panel.add_all_to_queue.connect(self._on_add_all_to_queue)
            self._parsed_panel.retry_project.connect(self._retry_topic)
            layout.addWidget(self._parsed_panel, stretch=1)
        else:
            # Fallback: old flat table
            self._parsed_panel = None
            table_header = QLabel(t("project_builder.fallback.parsed_prompts"))
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

            queue_btn = QPushButton(t("project_builder.fallback.add_all_queue"))
            queue_btn.setFixedHeight(36)
            queue_btn.setProperty("btnSize", "lg")
            queue_btn.clicked.connect(self._on_add_to_queue)
            layout.addWidget(queue_btn)

        # Dummy status references (for backward compat — no-op)
        self._topic_status_labels: List[QLabel] = []

        return workspace

    # ── Stage Checkpoint Panel (Full Production) ──────────────

    def _create_stage_panel(self) -> QWidget:
        """Create the stage checkpoint panel for Full Production mode."""
        from core.production_pipeline import STAGE_ORDER
        
        panel = QWidget()
        panel.setObjectName("stagePanel")
        panel.setStyleSheet(f"""
            #stagePanel {{
                background-color: {Theme.SURFACE0};
                border: 1px solid {Theme.BLUE};
                border-radius: 6px;
            }}
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 6, 8, 6)
        panel_layout.setSpacing(4)

        # Stage progress dots
        dots_row = QHBoxLayout()
        dots_row.setSpacing(2)
        self._stage_dots = {}
        STAGE_LABELS = {
            "duration_estimate": "1.Duration",
            "script_analysis": "2.Script",
            "scene_breakdown": "3.Scenes",
            "character_gen": "4.CharImg",
            "scene_image_gen": "5.SceneImg",
            "video_gen": "6.Video",
            "concat": "7.Concat",
        }
        for stage_name in STAGE_ORDER:
            dot = QPushButton(STAGE_LABELS.get(stage_name, stage_name))
            dot.setFixedHeight(24)
            dot.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.SURFACE1};
                    color: {Theme.SUBTEXT0};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 3px;
                    font-size: 10px; padding: 2px 6px;
                }}
            """)
            dot.setEnabled(False)
            dots_row.addWidget(dot)
            self._stage_dots[stage_name] = dot
        panel_layout.addLayout(dots_row)

        # Stage result viewer
        self._stage_viewer = QTextEdit()
        self._stage_viewer.setReadOnly(False)
        self._stage_viewer.setMinimumHeight(120)
        self._stage_viewer.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BASE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 12px; padding: 8px;
            }}
        """)
        self._stage_viewer.setPlaceholderText("Stage results will appear here for review...")
        panel_layout.addWidget(self._stage_viewer)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._stage_run_btn = QPushButton("▶ Run Stage")
        self._stage_run_btn.setProperty("variant", "success")
        self._stage_run_btn.setProperty("btnSize", "sm")
        self._stage_run_btn.setFixedHeight(30)
        self._stage_run_btn.clicked.connect(self._run_pipeline_stage)
        btn_row.addWidget(self._stage_run_btn)

        self._stage_confirm_btn = QPushButton("✅ Confirm & Next")
        self._stage_confirm_btn.setProperty("variant", "success")
        self._stage_confirm_btn.setProperty("btnSize", "sm")
        self._stage_confirm_btn.setFixedHeight(30)
        self._stage_confirm_btn.setEnabled(False)
        self._stage_confirm_btn.clicked.connect(self._on_stage_confirm)
        btn_row.addWidget(self._stage_confirm_btn)

        self._stage_skip_btn = QPushButton("⏭ Skip")
        self._stage_skip_btn.setProperty("variant", "warning")
        self._stage_skip_btn.setProperty("btnSize", "sm")
        self._stage_skip_btn.setFixedHeight(30)
        self._stage_skip_btn.clicked.connect(self._on_stage_skip)
        btn_row.addWidget(self._stage_skip_btn)

        btn_row.addStretch()
        panel_layout.addLayout(btn_row)

        # Pipeline state tracking
        self._pipeline = None
        self._pipeline_current_stage = None

        return panel

    def _on_pipeline_mode_changed(self, mode: str):
        """Switch entire workspace between Text Only and Full Production modes."""
        is_full = mode == "full_production"

        # ── Stage Checkpoint Panel ──
        self._stage_panel.setVisible(is_full)

        # ── Text-only controls (hidden in Full Production) ──
        text_only_widgets = [
            self._skip_research_cb, self._skip_seo_cb,
            self._per_topic_tmpl_cb, self._prompt_format_combo,
            self._auto_add_cb, self._detect_frame,
        ]
        for w in text_only_widgets:
            w.setVisible(not is_full)

        # ── Topics header ──
        if is_full:
            self._topics_header.setText("🎬 PRODUCTION INPUT ▼")
            self._topics_header.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.BLUE};
                    color: {Theme.CRUST};
                    font-weight: bold; border: none;
                    text-align: left; padding-left: 12px;
                }}
            """)
            self._topic_input.setPlaceholderText(
                "Nhập tiêu đề/kịch bản video...\n"
                "VD: Bí mật cuộc sống vĩ đại - 10 bài học triết lý"
            )
            self._topic_input.setMaximumHeight(16777215)  # Remove height limit — let it stretch
        else:
            self._topics_header.setText(f"{t('project_builder.topics_header')} ▼")
            self._topics_header.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.GREEN};
                    color: {Theme.CRUST};
                    font-weight: bold; border: none;
                    text-align: left; padding-left: 12px;
                }}
            """)
            self._topic_input.setPlaceholderText(t("project_builder.topics_placeholder"))
            self._topic_input.setMaximumHeight(16777215)  # Same as Full Production — no limit

        # ── Generate button ──
        if is_full:
            self._generate_btn.setText("▶ Start Pipeline")
            self._generate_btn.setProperty("variant", "primary")
        else:
            self._generate_btn.setText(t("project_builder.generate"))
            self._generate_btn.setProperty("variant", "success")
        self._generate_btn.style().unpolish(self._generate_btn)
        self._generate_btn.style().polish(self._generate_btn)

        # ── Parsed Projects panel ──
        # Hidden in Full Production (stage panel replaces it)
        if self._parsed_panel:
            self._parsed_panel.setVisible(not is_full)

        self._pipeline_mode = mode
        log.info(f"[TabProject] Pipeline mode: {mode}")

    def _run_pipeline_stage(self):
        """Run the next pipeline stage."""
        import asyncio
        from core.production_pipeline import ProductionPipeline, STAGE_ORDER
        
        # Initialize pipeline if needed
        if not self._pipeline:
            try:
                api_key, model_name, base_url, provider = self._get_ai_config()
            except ValueError as e:
                from ui.popups import show_warning
                show_warning(self, "API Error", str(e))
                return
            from services.ai_client_factory import create_ai_client
            client = create_ai_client(provider, base_url)
            self._pipeline = ProductionPipeline(
                gemini_client=client, api_key=api_key, model=model_name
            )
            # Set topic from input
            topic_text = self._topic_input.toPlainText().strip()
            if topic_text:
                self._pipeline.state.topic = topic_text.split("\n")[0].strip()

        # Find next stage
        next_stage = self._pipeline.get_next_stage()
        if not next_stage:
            self._stage_viewer.setPlainText("✅ Pipeline complete! All stages done.")
            return

        self._pipeline_current_stage = next_stage

        # Update dots
        for name, dot in self._stage_dots.items():
            if name == next_stage:
                dot.setStyleSheet(
                    f"QPushButton {{ background-color: {Theme.YELLOW}; color: {Theme.CRUST}; "
                    f"border: 1px solid {Theme.YELLOW}; border-radius: 3px; "
                    f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
                )

        self._stage_run_btn.setEnabled(False)
        self._stage_run_btn.setText(f"⏳ Running: {next_stage}...")
        self._stage_confirm_btn.setEnabled(False)

        # Get config from sidebar
        config = self._setup_matrix.get_config() if self._setup_matrix else {}
        config["topic"] = self._pipeline.state.topic

        # Run async stage in background thread
        self._stage_thread = QThread()
        self._stage_worker_obj = _StageWorker(self._pipeline, next_stage, config)
        self._stage_worker_obj.moveToThread(self._stage_thread)
        self._stage_thread.started.connect(self._stage_worker_obj.run)
        self._stage_worker_obj.done.connect(self._on_stage_done)
        self._stage_worker_obj.done.connect(self._stage_thread.quit)
        self._stage_thread.start()

    def _on_stage_done(self, stage_name: str, result_text: str, error: str):
        """Handle stage completion — show result for user review."""
        self._stage_run_btn.setEnabled(True)
        self._stage_run_btn.setText("▶ Run Stage")

        if error:
            self._stage_viewer.setPlainText(f"❌ Stage '{stage_name}' error:\n\n{error}")
            self._stage_dots[stage_name].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.RED}; color: {Theme.CRUST}; "
                f"border-radius: 3px; font-size: 10px; padding: 2px 6px; }}"
            )
        else:
            self._stage_viewer.setPlainText(result_text)
            self._stage_confirm_btn.setEnabled(True)
            self._stage_dots[stage_name].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )

    def _on_stage_confirm(self):
        """User confirms current stage result."""
        if not self._pipeline or not self._pipeline_current_stage:
            return
        # Pass any user edits back to pipeline
        edited_text = self._stage_viewer.toPlainText()
        self._pipeline.confirm_stage(self._pipeline_current_stage, {"user_edited": edited_text})
        self._stage_confirm_btn.setEnabled(False)
        
        # Check if prompts stage → auto-feed to parsed panel
        if self._pipeline_current_stage == "scene_breakdown" and self._pipeline.state.scenes:
            scenes = self._pipeline.state.scenes
            prompts = [s.prompt for s in scenes if s.prompt]
            if prompts and self._parsed_panel:
                for i, p in enumerate(prompts):
                    self._parsed_panel.add_project(f"Scene {i+1}", {"Prompts": p}, "ready")

        # Auto-advance to next stage
        next_stage = self._pipeline.get_next_stage()
        if next_stage:
            self._stage_viewer.setPlainText(f"Stage '{self._pipeline_current_stage}' confirmed.\n\n→ Ready for: {next_stage}\nClick '▶ Run Stage' to proceed.")
        else:
            self._stage_viewer.setPlainText("✅ All stages complete!")

    def _on_stage_skip(self):
        """User skips current stage."""
        if not self._pipeline or not self._pipeline_current_stage:
            return
        self._pipeline.skip_stage(self._pipeline_current_stage)
        self._stage_dots[self._pipeline_current_stage].setStyleSheet(
            f"QPushButton {{ background-color: {Theme.SURFACE1}; color: {Theme.SUBTEXT0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 3px; "
            f"font-size: 10px; padding: 2px 6px; }}"
        )
        self._stage_confirm_btn.setEnabled(False)
        next_stage = self._pipeline.get_next_stage()
        if next_stage:
            self._stage_viewer.setPlainText(f"Stage skipped.\n\n→ Ready for: {next_stage}")

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
            # Smart rotation: pick first available key via KeyQuotaManager
            api_key = None
            try:
                from services.key_quota_manager import get_quota_manager
                api_key = get_quota_manager().get_available_key(keys)
            except Exception:
                pass
            if not api_key:
                api_key = keys[0].strip()  # Fallback (auto-unblock in 60s)
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
        Pre-populate ParsedProjectsPanel with placeholder rows.
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

        # Pre-populate ParsedProjectsPanel with placeholder rows (⏳ Generating)
        if self._parsed_panel:
            self._parsed_panel.clear_projects()
            for topic_name in topics:
                self._parsed_panel.add_project(topic_name, {}, "generating")

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
        """Update per-topic completion — update progress bar."""
        self._done_topics = topic_idx + 1
        self._progress_bar.setMaximum(self._total_topics)
        self._progress_bar.setValue(self._done_topics)

    def _on_topic_result(self, topic_idx: int, topic_name: str,
                         files: dict, status: str):
        """Stream project data into ParsedProjectsPanel as each topic completes."""
        if not self._parsed_panel:
            return

        log.info(f"[TabProject] _on_topic_result idx={topic_idx} status={status} files_keys={list(files.keys()) if files else []}")

        if topic_idx < self._parsed_panel.get_project_count():
            # Update existing placeholder row with actual file data
            if files:
                self._parsed_panel.update_project_files(topic_idx, files)
                log.info(f"[TabProject] Updated project_data[{topic_idx}] with {len(files)} files")
            else:
                log.warning(f"[TabProject] Empty files dict for topic {topic_idx}!")

            # Always set 'ready' — actual queue-add happens in _on_generation_done
            proj_status = "ready" if status == "done" else "error"
            self._parsed_panel.set_project_status(topic_idx, proj_status)

    # ── Actions ────────────────────────────────────────────────

    def _on_clear(self):
        """Clear topics input + parsed projects panel."""
        self._topic_input.clear()
        if self._parsed_panel:
            self._parsed_panel.clear_projects()
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._topics_header.setText(t("project_extra.topics_collapsed"))
        self._topics_expanded = True
        self._topics_body.setVisible(True)

    def _on_generate(self):
        """Start full auto generation (Fix 1: runs in background thread)."""
        # ── Full Production mode → redirect to stage pipeline ──
        if getattr(self, '_pipeline_mode', '') == 'full_production':
            self._run_pipeline_stage()
            return
        
        # ── Permission check: AI Prompt Processing ──
        if self.controller and hasattr(self.controller, '_permissions'):
            from services.permissions import Feature
            if not self.controller._permissions.has_feature(Feature.AI_PROMPT_PROCESSING):
                from ui.popups import show_warning
                show_warning(
                    self, t("popups.premium_feature_title"),
                    t("popups.ai_prompt_premium_only")
                )
                return
        
        topics = self._topic_input.toPlainText().strip()
        if not topics:
            from ui.popups import show_warning
            show_warning(self, t("project.no_topics_title"), t("project.no_topics_msg"))
            return

        template = self._get_selected_template()
        if not template:
            from ui.popups import show_warning
            show_warning(self, t("project.no_template_title"), t("project.no_template_msg"))
            return

        # ── Validate Setup Matrix (required dimensions) ──
        matrix_config = {}
        if self._setup_matrix:
            matrix_config = self._setup_matrix.get_config()
            missing = []
            required_dims = [
                ("category",  "Category (D1)"),
                # D2-D7 are optional — AI will freely choose if left as "---"
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
                msg = t("project.missing_info_msg") + "\n• ".join(missing)
                show_warning(self, t("project.missing_info_title"), msg)
                return

        # Get API config from Settings (Fix 6)
        try:
            api_key, model_name, base_url, provider = self._get_ai_config()
        except ValueError as e:
            from ui.popups import show_warning
            show_warning(self, t("project.api_error"), str(e))
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

        # Disable generate button, show cancel (Fix #1)
        self._generate_btn.setEnabled(False)
        self._generate_btn.setText(t("project_extra.generating"))
        self._cancel_btn.setVisible(True)

        output_base = ""
        if self._setup_matrix:
            output_base = self._setup_matrix.output_folder.text()
        elif hasattr(self, '_output_label'):
            output_base = self._output_label.text()
            if output_base == "Not set":
                output_base = ""

        # Cleanup previous worker thread if still alive (Bug 4 fix)
        if self._worker_thread is not None:
            try:
                if self._worker_thread.isRunning():
                    self._worker_thread.quit()
                    self._worker_thread.wait(2000)
                self._worker_thread.deleteLater()
            except RuntimeError:
                pass
            self._worker_thread = None
            self._worker = None

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
            prompt_format="json" if self._prompt_format_combo.currentText() == "JSON" else "text",
            skip_seo=self._skip_seo_cb.isChecked(),
            skip_research=self._skip_research_cb.isChecked(),
            skip_bible=False,
            per_topic_template=self._per_topic_tmpl_cb.isChecked(),
        )
        self._worker.moveToThread(self._worker_thread)

        # Connect signals
        self._worker_thread.started.connect(self._worker.run)
        self._worker.step_update.connect(self._update_topic_step)
        self._worker.topic_done.connect(self._update_topic_done)
        self._worker.topic_result.connect(self._on_topic_result)
        self._worker.all_done.connect(self._on_generation_done)
        self._worker.error.connect(self._on_generation_error)
        self._worker.log_msg.connect(self._route_worker_log)

        # Cleanup when done
        self._worker.all_done.connect(self._worker_thread.quit)
        self._worker.error.connect(self._worker_thread.quit)

        self._worker_thread.start()

    def _on_generation_done(self, results):
        """Handle generation completion (runs on main thread via signal).

        Projects already streamed via topic_result signal — just finalize.
        """
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText(t("project_builder.generate"))
        self._cancel_btn.setVisible(False)

        # Complete progress bar
        self._progress_bar.setValue(self._progress_bar.maximum())

        # Count results (projects already displayed via _on_topic_result)
        all_prompts = []
        done_count = 0
        for r in results:
            if r.status == "done":
                all_prompts.extend(r.prompts)
                done_count += 1

        # ── Fallback: ensure _project_data is populated from results ──
        # In case topic_result signal lost data crossing thread boundary
        if self._parsed_panel:
            for i, r in enumerate(results):
                if r.status == "done" and hasattr(r, 'files') and r.files:
                    if i < len(self._parsed_panel._project_data):
                        existing = self._parsed_panel._project_data[i]
                        if not existing.get("Prompts") and not existing.get("Master"):
                            self._parsed_panel._project_data[i].update(r.files)
                            log.info(f"[TabProject] Fallback: populated project_data[{i}] from all_done results")

        # Legacy fallback: populate old table
        if not self._parsed_panel:
            self._show_prompts_in_table(all_prompts)

        # Update header with final status
        total = len(results)
        self._topics_header.setText(
            f"✅ Done: {done_count}/{total} topics, {len(all_prompts)} prompts ▶"
        )

        # Auto-add to Queue: add each ready project individually (skip already queued — Bug 8 fix)
        if self._auto_add_cb.isChecked() and self._parsed_panel:
            for i, row in enumerate(self._parsed_panel._projects):
                if row.get_status() == "ready":
                    self._on_add_project_to_queue(i)

    def _on_generation_error(self, error_msg):
        """Handle fatal generation error (Bug 1 fix: no _status_summary)."""
        self._generate_btn.setEnabled(True)
        self._generate_btn.setText(t("project_builder.generate"))
        self._cancel_btn.setVisible(False)
        # Show error in header (works for both old and new UI)
        self._topics_header.setText(f"❌ Error: {error_msg[:80]}")
        self._progress_bar.setVisible(False)
        # Show popup so user sees the error
        try:
            from ui.popups import show_warning
            show_warning(self, "Generation Error", f"Fatal error during generation:\n\n{error_msg}")
        except Exception:
            pass

    def _on_cancel_generation(self):
        """Fix #1: Cancel running generation."""
        if self._worker and hasattr(self._worker, '_builder') and self._worker._builder:
            self._worker._builder.cancel()
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("⏳ Cancelling...")
        self._topics_header.setText("⛔ Cancelling... (finishing current topic)")
        log.info("[TabProject] Cancel requested by user")

    def _retry_topic(self, topic_idx: int):
        """Fix #3: Retry a single failed topic."""
        if not self._parsed_panel or topic_idx >= len(self._parsed_panel._projects):
            return
        row = self._parsed_panel._projects[topic_idx]
        if row.get_status() not in ("error", "ready"):
            return

        topic_name = row.name
        row.set_status("generating")
        log.info(f"[TabProject] Retrying topic {topic_idx}: '{topic_name}'")

        try:
            api_key, model_name, base_url, provider = self._get_ai_config()
        except ValueError as e:
            from ui.popups import show_warning
            show_warning(self, "API Error", str(e))
            row.set_status("error")
            return

        template = self._get_selected_template()
        output_base = self._setup_matrix.output_folder.text() if self._setup_matrix else ""

        # Run single-topic in background thread
        self._retry_thread = QThread()
        self._retry_worker = _GenerationWorker(
            topics=[topic_name],
            template=template,
            api_key=api_key,
            output_base=output_base,
            scanner=self._scanner,
            rules_loader=self._rules_loader,
            model_name=model_name,
            base_url=base_url,
            provider=provider,
            matrix_config=self._setup_matrix.get_config() if self._setup_matrix else {},
            prompt_format="json" if self._prompt_format_combo.currentText() == "JSON" else "text",
            skip_seo=self._skip_seo_cb.isChecked(),
            skip_research=self._skip_research_cb.isChecked(),
        )
        retry_idx = topic_idx  # Capture for closure
        self._retry_worker.moveToThread(self._retry_thread)
        self._retry_thread.started.connect(self._retry_worker.run)

        def on_retry_done(results):
            if results and results[0].status == "done":
                files = dict(results[0].files) if hasattr(results[0], 'files') and results[0].files else {}
                if files:
                    self._parsed_panel.update_project_files(retry_idx, files)
                self._parsed_panel.set_project_status(retry_idx, "ready")
                log.info(f"[TabProject] Retry topic {retry_idx} succeeded")
            else:
                self._parsed_panel.set_project_status(retry_idx, "error")
                log.warning(f"[TabProject] Retry topic {retry_idx} failed")
            self._retry_thread.quit()

        def on_retry_error(msg):
            self._parsed_panel.set_project_status(retry_idx, "error")
            log.error(f"[TabProject] Retry fatal: {msg}")
            self._retry_thread.quit()

        self._retry_worker.all_done.connect(on_retry_done)
        self._retry_worker.error.connect(on_retry_error)
        self._retry_thread.start()

    def _on_import_prompts(self):
        """Import prompts from a text file (txt, md, doc, docx, csv)."""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Prompts from File",
            "",
            "Text Files (*.txt *.md *.csv);;Word Documents (*.docx *.doc);;All Files (*.*)",
        )
        if not file_path:
            return
        
        # Read file content
        try:
            if file_path.lower().endswith('.docx'):
                try:
                    from docx import Document
                    doc = Document(file_path)
                    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                except ImportError:
                    # Fallback: read raw (may not work well for docx)
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
            else:
                # txt, md, csv, doc (plain text)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
        except Exception as e:
            from ui.popups import show_warning
            show_warning(self, "Import Error", f"Cannot read file:\n{e}")
            return
        
        if not text.strip():
            from ui.popups import show_warning
            show_warning(self, "Empty File", "The selected file is empty.")
            return
        
        # In Full Production mode, paste content into topic input
        if getattr(self, '_pipeline_mode', '') == 'full_production':
            self._topic_input.setPlainText(text.strip())
            import os
            self._topics_header.setText(f"🎬 PRODUCTION INPUT — {os.path.basename(file_path)} ▼")
            return
        
        # Text-Only mode: parse as prompts
        template = self._get_selected_template()
        if not template:
            from core.workflow_scanner import WorkflowTemplate
            template = WorkflowTemplate(display_name="Manual")

        from core.project_builder import ProjectBuilder
        builder = ProjectBuilder()
        prompts = builder.import_prompts(text, template)

        if self._parsed_panel:
            for i, p in enumerate(prompts):
                self._parsed_panel.add_project(
                    f"Imported Prompt {i+1}",
                    {"Prompts": p.prompt, "Master": p.prompt},
                    "ready"
                )
        else:
            self._show_prompts_in_table(prompts)

        import os
        self._topics_header.setText(
            f"✅ Imported {len(prompts)} prompts from {os.path.basename(file_path)} ▶"
        )

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
            show_warning(self, t("project.empty_prompts_title"), t("project.empty_prompts_msg"))
            return

        prompts = []
        for i in range(row_count):
            item = self._prompts_table.item(i, 1)
            if item:
                prompts.append(item.text())

        self._do_queue_add(prompts, "Project Builder")

    def _on_add_project_to_queue(self, project_idx: int):
        """Add a single project's prompts to queue."""
        import re
        if not self._parsed_panel:
            return
        data = self._parsed_panel._project_data
        if project_idx < len(data):
            project_files = data[project_idx]
            log.info(f"[TabProject] Adding project {project_idx} to queue. Data keys: {list(project_files.keys())}")

            # Try 'Prompts' key first, fallback to 'Master'
            prompts_text = project_files.get("Prompts", "") or project_files.get("Master", "")

            if not prompts_text:
                log.warning(f"[TabProject] project_data[{project_idx}] has NO Prompts/Master content. Full keys: {list(project_files.keys())}")

            prompts = []
            for ln in prompts_text.split("\n"):
                ln = ln.strip()
                if not ln:
                    continue
                # Strip numbering: "1. ", "2) ", "Scene 1: "
                cleaned = re.sub(r'^(\d+[\.\)]\s*|Scene\s+\d+:\s*)', '', ln).strip()
                if cleaned:
                    prompts.append(cleaned)
            name = self._parsed_panel._projects[project_idx].name
            log.info(f"[TabProject] Extracted {len(prompts)} prompts for '{name}'")
            if prompts:
                self._do_queue_add(prompts, name)
                self._parsed_panel.set_project_status(project_idx, "queued")
            else:
                log.warning(f"[TabProject] No prompts found for project '{name}' (idx={project_idx})")
                from ui.popups import show_warning
                show_warning(self, "No Prompts", f"Project '{name}' has no prompt content to queue.")

    def _on_add_all_to_queue(self):
        """Add all ready (non-generating, non-queued) projects to queue.
        
        Bug 5+8 fix: skip 'generating', 'queued', and 'error' to prevent
        duplicate queue entries and adding broken projects.
        """
        if not self._parsed_panel:
            return
        added = 0
        for i, row in enumerate(self._parsed_panel._projects):
            if row.get_status() == "ready":
                self._on_add_project_to_queue(i)
                added += 1
        log.info(f"[TabProject] _on_add_all_to_queue: added {added} ready projects")

    def _do_queue_add(self, prompts: list, project_name: str):
        """Common queue-add logic — routes to T2V or T2I based on combo."""
        if not prompts:
            log.warning(f"[TabProject] _do_queue_add called with empty prompts for '{project_name}'")
            return

        log.info(f"[TabProject] _do_queue_add: {len(prompts)} prompts for '{project_name}'")

        # Determine output type from ParsedProjectsPanel combo
        output_type = "T2V"
        if self._parsed_panel and hasattr(self._parsed_panel, 'get_output_type'):
            output_type = self._parsed_panel.get_output_type()

        # Build settings dict from SetupMatrixPanel or legacy
        settings = {"project_name": project_name}
        if self._setup_matrix:
            config = self._setup_matrix.get_config()
            settings["output_folder"] = config.get("output_folder", "")
            if output_type == "T2I":
                # Image settings
                settings["model"] = config.get("image_model", "GEM_PIX_2")
                settings["aspect_ratio"] = config.get("image_aspect", "LANDSCAPE")
                settings["download_quality"] = config.get("image_quality", "2k")
                settings["outputs_per_prompt"] = config.get("image_outputs", 4)
            else:
                # Video settings
                settings["model"] = config.get("video_model", "Veo 3.1 - Fast")
                settings["aspect_ratio"] = config.get("video_aspect", "LANDSCAPE")
                settings["download_quality"] = config.get("video_quality", "1080p")
                settings["outputs_per_prompt"] = config.get("video_outputs", 4)
        elif hasattr(self, '_aspect_combo'):
            settings["aspect_ratio"] = "LANDSCAPE" if "Landscape" in self._aspect_combo.currentText() else "PORTRAIT"

        # Route to correct controller method
        method_name = "add_t2i_batch" if output_type == "T2I" else "add_t2v_batch"
        log.info(f"[TabProject] Calling controller.{method_name}() with {len(prompts)} prompts, controller={self.controller is not None}")
        if self.controller and hasattr(self.controller, method_name):
            getattr(self.controller, method_name)(
                prompts=prompts,
                settings=settings,
            )
            log.info(f"[TabProject] ✅ Successfully added {len(prompts)} prompts to queue as {output_type}")
            from ui.popups import show_info
            show_info(self, t("dialogs.added"), t("project_sidebar.added_queue").replace("{count}", str(len(prompts))).replace("{type}", output_type))

            # ── Force Queue tab refresh + switch ──
            # show_info blocks the main thread, so queue signals may be lost.
            # Explicitly refresh Queue tab and switch to it after popup.
            try:
                main_window = self.window()
                if main_window and hasattr(main_window, 'tab_instances'):
                    queue_tab = main_window.tab_instances.get('queue')
                    if queue_tab and hasattr(queue_tab, '_refresh_queue_from_controller'):
                        queue_tab._refresh_queue_from_controller()
                        log.info("[TabProject] ✅ Queue tab force-refreshed after add")
                    # Switch to Queue tab
                    if hasattr(main_window, 'tabview'):
                        for i in range(main_window.tabview.count()):
                            if main_window.tabview.widget(i) is queue_tab:
                                main_window.tabview.setCurrentIndex(i)
                                log.info(f"[TabProject] ✅ Switched to Queue tab (index {i})")
                                break
            except Exception as e:
                log.warning(f"[TabProject] Queue refresh/switch failed: {e}")
        else:
            log.warning(f"[TabProject] ⚠️ Controller missing or no {method_name} method! controller={self.controller}")
            from ui.popups import show_info
            show_info(self, "Ready", t("project_sidebar.ready").replace("{count}", str(len(prompts))))

    def _browse_output(self):
        """Browse for output folder."""
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, t("project_sidebar.select_output"))
        if folder:
            if hasattr(self, '_output_label'):
                self._output_label.setText(folder)
            if self._setup_matrix:
                self._setup_matrix.output_folder.setText(folder)

    def retranslate_ui(self):
        """Hot-reload UI text on language change — rebuild entire tab.
        
        Bug 9 fix: re-init builder after rebuilding UI so scanner/rules_loader
        remain available.
        """
        # Remove old layout
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            QWidget().setLayout(old_layout)

        # Reset references
        self._setup_matrix = None
        self._parsed_panel = None

        # Rebuild UI + re-init builder (Bug 9 fix)
        self._setup_ui()
        self._init_builder()
