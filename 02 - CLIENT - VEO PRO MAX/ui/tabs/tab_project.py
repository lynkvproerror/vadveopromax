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
import os
from pathlib import Path
from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTextEdit, QPlainTextEdit, QFrame,
    QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QScrollArea,
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
        return _format_stage_result(self._stage, result)


def _format_stage_result(stage_name: str, result) -> str:
    """Format stage result for human-readable review display."""
    lines = [f"✅ Stage: {stage_name}\n"]
    if stage_name == "duration_estimate":
        d = result.data
        source = d.get("source", "sidebar_defaults")
        source_label = "🤖 AI Auto-Detect" if source == "ai_detected" else "⚙️ Sidebar Defaults"
        ai = d.get("ai_detected", {})
        # Show AI-detected title and narrative info prominently
        ai_title = ai.get("title", "") if ai else ""
        display_title = ai_title or d.get('topic', 'N/A')
        lines.append(f"Source: {source_label}")
        lines.append(f"\n📌 Title: {display_title}")
        # Show characters upfront if detected
        chars = ai.get("characters", []) if ai else []
        if chars:
            char_names = [c.get('name', '?') for c in chars]
            lines.append(f"👤 Characters ({len(chars)}): {', '.join(char_names)}")
            for c in chars:
                lines.append(f"   • {c.get('name', '?')}: {c.get('description', '')}")
        if ai.get("style"):
            lines.append(f"🎨 Style: {ai['style']}")
        if ai.get("tone"):
            lines.append(f"🎭 Tone: {ai['tone']}")
        ai_scenes = ai.get("scene_count", 0) if ai else 0
        if ai_scenes:
            lines.append(f"📖 Story scenes detected: {ai_scenes}")
        # VEO Production Config
        lines.append(f"\n🎬 VEO PRODUCTION CONFIG:")
        scene_count = d.get('scene_count', 0)
        clip_dur = d.get('clip_duration', 8)
        total = d.get('target_duration', 0)
        mins, secs = int(total) // 60, int(total) % 60
        lines.append(f"  VEO clips: {scene_count}")
        lines.append(f"  Clip duration: {clip_dur}s")
        lines.append(f"  Total duration: {mins}:{secs:02d}")
        lines.append(f"  = {scene_count} clips × {clip_dur}s = {scene_count * clip_dur}s (target: {total}s)")
        lines.append("\n(Bạn có thể chỉnh sửa scene count/duration ở Sidebar trước khi Confirm)")
    elif stage_name == "script_analysis":
        # Bible text (plain, editable)
        bible = result.data.get("bible", "") if result.data else ""
        if bible:
            lines.append("📖 PRODUCTION BIBLE\n")
            lines.append("(Bạn có thể chỉnh sửa kịch bản bên dưới trước khi Confirm)")
            lines.append("=" * 40)
            lines.append(bible)
        else:
            lines.append(str(result.data))
    elif stage_name == "scene_breakdown":
        # Plain text prompts (editable)
        raw = result.data.get("raw_prompts", "") if result.data else ""
        if raw:
            lines.append(f"🎬 VEO PROMPTS ({result.data.get('prompt_count', 0)} scenes)\n")
            lines.append("(Bạn có thể chỉnh sửa prompts bên dưới trước khi Confirm)")
            lines.append("=" * 40)
            lines.append(raw)
        else:
            lines.append(f"Generated {len(result.scenes)} scenes:")
            for s in result.scenes:
                lines.append(f"\n  Scene {s.index}: {s.prompt}")
    elif stage_name == "character_gen":
        d = result.data or {}
        names = d.get("character_names", [])
        prompts = d.get("character_prompts", [])
        lines.append(f"👤 CHARACTER T2I PROMPTS ({len(prompts)} characters)\n")
        lines.append("(Bạn có thể chỉnh sửa prompts bên dưới trước khi Confirm)")
        lines.append("Mode: T2I (Text → Image)")
        lines.append("=" * 40)
        for i, p in enumerate(prompts):
            name = names[i] if i < len(names) else f"Character {i+1}"
            lines.append(f"\n[{name}]")
            lines.append(p)
    elif stage_name == "scene_image_gen":
        d = result.data or {}
        configs = d.get("scene_configs", [])
        char_refs = d.get("char_refs", [])
        mode = d.get("mode", "T2I")
        lines.append(f"🖼️ SCENE IMAGE GENERATION ({len(configs)} scenes)\n")
        if char_refs:
            lines.append(f"👤 Character references: {len(char_refs)} images")
            for cr in char_refs:
                lines.append(f"  • {cr['name']}: {cr['image_path']}")
            lines.append("")
        lines.append(f"Mode: {mode}")
        lines.append("(Bạn có thể chỉnh sửa prompts bên dưới trước khi Confirm)")
        lines.append("=" * 40)
        for c in configs:
            ref_count = len(c.get("reference_images", []))
            ref_info = f" [+{ref_count} char refs]" if ref_count > 0 else ""
            lines.append(f"\n--- Scene {c['index']} [{c['mode']}]{ref_info} ---")
            lines.append(c["prompt"])
    elif stage_name == "video_gen":
        d = result.data or {}
        configs = d.get("video_configs", [])
        modes = d.get("modes", [])
        lines.append(f"🎬 VIDEO GENERATION ({len(configs)} clips)\n")
        lines.append(f"Modes: {', '.join(modes)}")
        lines.append("=" * 40)
        for c in configs:
            mode_icon = "🎬" if c["mode"] == "I2V" else ("🔗" if c["mode"] == "R2V" else "📹")
            img = f" | Image: {c['image_path']}" if c.get("image_path") else (" | Refs: char images" if c["mode"] == "R2V" else "")
            lines.append(f"\n{mode_icon} Scene {c['index']} [{c['mode']}] ({c['duration_s']}s){img}")
            lines.append(f"  Prompt: {c['prompt'][:150]}...")
    elif stage_name == "concat":
        d = result.data or {}
        clips = d.get("clips", [])
        missing = d.get("missing_scenes", [])
        ready = d.get("ready", False)
        lines.append(f"🎞️ FINAL CONCAT\n")
        lines.append(f"Clips ready: {len(clips)}/{d.get('total_clips', 0)}")
        total_s = d.get("total_duration_s", 0)
        mins, secs = int(total_s) // 60, int(total_s) % 60
        lines.append(f"Total duration: {mins}:{secs:02d}")
        lines.append(f"Output: {d.get('final_output', 'N/A')}")
        if missing:
            lines.append(f"\n⚠️ Missing video for scenes: {missing}")
        lines.append("=" * 40)
        for c in clips:
            lines.append(f"  Scene {c['index']}: {c['path']} ({c['duration_s']}s)")
        if ready:
            lines.append("\n✅ Ready to concat! Confirm to start FFmpeg.")
        else:
            lines.append(f"\n❌ {len(missing)} scenes still need video generation.")
    else:
        import json
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
        
        # Auto-restore pipeline state from last session (deferred so UI is ready)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._auto_restore_pipeline)

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
            "duration_estimate": "1.Analysis",
            "script_analysis": "2.Bible",
            "scene_breakdown": "3.Prompts",
            "character_gen": "4.Character",
            "scene_image_gen": "5.Scenes",
            "video_gen": "6.Video",
            "concat": "7.Final",
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
            dot.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # UI-5: indicator only, no dim
            dots_row.addWidget(dot)
            self._stage_dots[stage_name] = dot
        panel_layout.addLayout(dots_row)

        # Stage result viewer
        # UI-3: QPlainTextEdit (plain text only — prevents HTML paste issues)
        self._stage_viewer = QPlainTextEdit()
        self._stage_viewer.setReadOnly(False)
        self._stage_viewer.setMinimumHeight(120)
        self._stage_viewer.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Theme.BASE};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 12px; padding: 8px;
            }}
        """)
        self._stage_viewer.setPlaceholderText("Stage results will appear here for review...")
        panel_layout.addWidget(self._stage_viewer, stretch=3)

        # Thumbnail gallery for Stage 4-7 (images/videos)
        self._thumb_scroll = QScrollArea()
        self._thumb_scroll.setWidgetResizable(True)
        # UI-2: Use min/max instead of fixedHeight to avoid conflicts
        self._thumb_scroll.setMinimumHeight(0)
        self._thumb_scroll.setMaximumHeight(100)
        self._thumb_scroll.setVisible(False)
        self._thumb_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {Theme.MANTLE};
                border: 1px solid {Theme.BORDER};
                border-radius: 4px;
            }}
        """)
        self._thumb_container = QWidget()
        self._thumb_layout = QHBoxLayout(self._thumb_container)
        self._thumb_layout.setContentsMargins(4, 4, 4, 4)
        self._thumb_layout.setSpacing(4)
        self._thumb_layout.addStretch()
        self._thumb_scroll.setWidget(self._thumb_container)
        panel_layout.addWidget(self._thumb_scroll)

        # Action buttons — UI-1: ordered as [Start] [⬅Back] [➡Next] [✅Confirm] [⏭Skip] [📂Output]
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._stage_run_btn = QPushButton("▶️ Start Pipeline")
        self._stage_run_btn.setProperty("variant", "success")
        self._stage_run_btn.setProperty("btnSize", "sm")
        self._stage_run_btn.setFixedHeight(30)
        self._stage_run_btn.clicked.connect(self._run_pipeline_stage)
        btn_row.addWidget(self._stage_run_btn)

        self._stage_back_btn = QPushButton("⬅️​ Back")
        self._stage_back_btn.setProperty("variant", "secondary")
        self._stage_back_btn.setProperty("btnSize", "sm")
        self._stage_back_btn.setFixedHeight(30)
        self._stage_back_btn.setEnabled(False)
        self._stage_back_btn.clicked.connect(self._on_stage_back)
        btn_row.addWidget(self._stage_back_btn)

        self._stage_next_btn = QPushButton("➡️​ Next")
        self._stage_next_btn.setProperty("variant", "secondary")
        self._stage_next_btn.setProperty("btnSize", "sm")
        self._stage_next_btn.setFixedHeight(30)
        self._stage_next_btn.setEnabled(False)
        self._stage_next_btn.clicked.connect(self._on_stage_next)
        btn_row.addWidget(self._stage_next_btn)

        self._stage_confirm_btn = QPushButton("✅ Confirm & Next")
        self._stage_confirm_btn.setProperty("variant", "success")
        self._stage_confirm_btn.setProperty("btnSize", "sm")
        self._stage_confirm_btn.setFixedHeight(30)
        self._stage_confirm_btn.setEnabled(False)
        self._stage_confirm_btn.clicked.connect(self._on_stage_confirm)
        btn_row.addWidget(self._stage_confirm_btn)

        self._stage_skip_btn = QPushButton("⏭️​ Skip")
        self._stage_skip_btn.setProperty("variant", "warning")
        self._stage_skip_btn.setProperty("btnSize", "sm")
        self._stage_skip_btn.setFixedHeight(30)
        self._stage_skip_btn.clicked.connect(self._on_stage_skip)
        btn_row.addWidget(self._stage_skip_btn)

        self._stage_output_btn = QPushButton("\U0001f4c2 Output")
        self._stage_output_btn.setProperty("variant", "secondary")
        self._stage_output_btn.setProperty("btnSize", "sm")
        self._stage_output_btn.setFixedHeight(30)
        self._stage_output_btn.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self._stage_output_btn)

        self._stage_load_btn = QPushButton("\U0001f4e5 Load")
        self._stage_load_btn.setProperty("variant", "secondary")
        self._stage_load_btn.setProperty("btnSize", "sm")
        self._stage_load_btn.setFixedHeight(30)
        self._stage_load_btn.setToolTip("Load an incomplete pipeline session from a project folder")
        self._stage_load_btn.clicked.connect(self._load_project_session)
        btn_row.addWidget(self._stage_load_btn)

        btn_row.addStretch()
        panel_layout.addLayout(btn_row)

        # Pipeline state tracking
        self._pipeline = None
        self._pipeline_current_stage = None

        return panel

    def _open_output_folder(self):
        """Open pipeline output folder in OS file explorer."""
        import os, subprocess
        folder = ""
        if hasattr(self, '_setup_matrix') and hasattr(self._setup_matrix, 'output_folder'):
            folder = self._setup_matrix.output_folder.text().strip()
        if folder and os.path.isdir(folder):
            # Fix 9: Use _get_sanitized_project_name for consistent folder lookup
            if self._pipeline:
                config = self._setup_matrix.get_config() if self._setup_matrix else {}
                topic_slug = self._get_sanitized_project_name(config)
                if topic_slug:
                    proj_dir = os.path.join(folder, topic_slug)
                    if os.path.isdir(proj_dir):
                        folder = proj_dir
            os.startfile(folder)
        elif folder:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        else:
            from ui.popups import show_warning
            show_warning(self, "No Output", "Ch\u01b0a c\u00e0i \u0111\u1eb7t Output Folder trong Sidebar.")

    # ── AN-1: Fade-in for thumbnail scroll area ──
    def _fade_in_thumb_scroll(self):
        """Fade in the thumbnail scroll area: opacity 0→1 over 300ms."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        self._thumb_scroll.setVisible(True)
        effect = QGraphicsOpacityEffect(self._thumb_scroll)
        effect.setOpacity(0.0)
        self._thumb_scroll.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self._thumb_scroll)
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._thumb_scroll.setGraphicsEffect(None))
        anim.start()
        self._thumb_fade_anim = anim  # prevent GC

    # ── AN-2: Staggered card fade-in ──
    def _stagger_fade_cards(self, widgets: list):
        """Fade in cards one-by-one with 80ms stagger per widget."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
        self._card_fade_anims = []  # prevent GC
        for i, w in enumerate(widgets):
            effect = QGraphicsOpacityEffect(w)
            effect.setOpacity(0.0)
            w.setGraphicsEffect(effect)
            def _start_fade(widget=w, eff=effect):
                anim = QPropertyAnimation(eff, b"opacity", widget)
                anim.setDuration(250)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                anim.finished.connect(lambda ww=widget: ww.setGraphicsEffect(None))
                anim.start()
                self._card_fade_anims.append(anim)
            QTimer.singleShot(i * 80, _start_fade)

    # ── AN-4: Dot completion flash (2x pulse) ──
    def _flash_dot(self, stage_name: str):
        """Flash a stage dot 2x between bright/dim green on completion."""
        from PySide6.QtCore import QTimer
        dot = self._stage_dots.get(stage_name)
        if not dot:
            return
        flash_count = [0]
        bright = (f"QPushButton {{ background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                  f"border: 2px solid {Theme.TEXT}; "
                  f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}")
        normal = (f"QPushButton {{ background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                  f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}")
        def _tick():
            flash_count[0] += 1
            dot.setStyleSheet(bright if flash_count[0] % 2 == 1 else normal)
            if flash_count[0] >= 4:  # 2 complete on/off cycles
                dot.setStyleSheet(normal)
                return
            QTimer.singleShot(150, _tick)
        QTimer.singleShot(0, _tick)

    # ── AN-5: Animated scroll height transition ──
    def _animate_scroll_height(self, target_min: int, target_max: int):
        """Smoothly animate thumb_scroll min/max height over 200ms."""
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        current_min = self._thumb_scroll.minimumHeight()
        # Only animate minimumHeight (maxHeight change is instant — no visual jank)
        self._thumb_scroll.setMaximumHeight(target_max)
        if current_min == target_min:
            return
        anim = QPropertyAnimation(self._thumb_scroll, b"minimumHeight")
        anim.setDuration(200)
        anim.setStartValue(current_min)
        anim.setEndValue(target_min)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._scroll_height_anim = anim  # prevent GC

    def _update_thumbnails(self, stage_name: str):
        """Update thumbnail gallery for visual stages (4-7).
        
        Stage 4: Horizontal card scroll (character cards)
        Stage 5-7: Vertical list with horizontal row cards (thumbnail left + info right)
        """
        import os
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import QSize, Qt
        from ui.tabs.project_components.pipeline_prompt_table import (
            PipelinePromptTable, PipelinePromptItem,
        )

        visual_stages = {"character_gen", "scene_image_gen", "video_gen", "concat"}
        list_stages   = {"scene_image_gen", "video_gen", "concat"}

        if stage_name not in visual_stages:
            self._thumb_scroll.setVisible(False)
            # UI-2: Reset to small max without fixedHeight conflict
            self._thumb_scroll.setMinimumHeight(0)
            self._thumb_scroll.setMaximumHeight(100)
            return

        # ── Rebuild layout direction based on stage type ──
        # Stage 4 = HBox (horizontal cards), Stages 5-7 = VBox (vertical list)
        old_layout = self._thumb_container.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            # TH-6: Properly detach + delete orphan widget to avoid leak
            _tmp = QWidget()
            _tmp.setLayout(old_layout)
            _tmp.deleteLater()

        # All stages now use VBox (PipelinePromptTable handles its own layout)
        self._thumb_layout = QVBoxLayout(self._thumb_container)
        self._thumb_layout.setContentsMargins(4, 4, 4, 4)
        self._thumb_layout.setSpacing(6)
        # AN-5: Animated height transition
        self._animate_scroll_height(250, 16777215)

        # ── Stage 4: Character prompts (PipelinePromptTable) ──
        if stage_name == "character_gen":
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            img_aspect = config.get("image_aspect", "PORTRAIT")
            if img_aspect == "PORTRAIT":
                thumb_sz = (60, 80)
            elif img_aspect == "LANDSCAPE":
                thumb_sz = (80, 45)
            else:
                thumb_sz = (60, 60)

            stage_obj = self._pipeline.state.get_stage("character_gen")
            characters = self._pipeline.state.characters or []
            char_prompts = stage_obj.prompts or []

            if not characters and not char_prompts:
                lbl = QLabel("⏳ Character data will appear after Stage 4 completes")
                lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                self._thumb_layout.addWidget(lbl)
            else:
                items = []
                count = max(len(characters), len(char_prompts))
                for i in range(count):
                    char = characters[i] if i < len(characters) else None
                    prompt = char_prompts[i] if i < len(char_prompts) else (char.prompt if char else "")
                    name = char.name if char else f"Character {i+1}"
                    thumb_path = (char.image_path if char and char.image_path and os.path.isfile(char.image_path) else "")
                    items.append(PipelinePromptItem(
                        index=i + 1, name=f"👤 {name}", prompt=prompt,
                        thumbnail_path=thumb_path, accent_color=Theme.BLUE,
                    ))
                self._pipeline_prompt_table = PipelinePromptTable(
                    accent_color=Theme.BLUE, thumb_size=thumb_sz,
                )
                self._pipeline_prompt_table.set_items(items)
                self._thumb_layout.addWidget(self._pipeline_prompt_table)

            # AN-1: Fade-in scroll
            self._fade_in_thumb_scroll()
            return

        # ── Stage 5: Scene Image prompts (PipelinePromptTable) ──
        if stage_name == "scene_image_gen":
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            img_aspect = config.get("image_aspect", "LANDSCAPE")
            if img_aspect == "PORTRAIT":
                thumb_sz = (60, 80)
            elif img_aspect == "LANDSCAPE":
                thumb_sz = (90, 50)
            else:
                thumb_sz = (70, 70)

            stage_obj = self._pipeline.state.get_stage("scene_image_gen")
            scene_configs = []
            if stage_obj.data and isinstance(stage_obj.data, dict):
                scene_configs = stage_obj.data.get("scene_configs", [])
            scenes = self._pipeline.state.scenes or []

            if not scene_configs and not scenes:
                lbl = QLabel("⏳ Scene data will appear after Stage 5 completes")
                lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                self._thumb_layout.addWidget(lbl)
            else:
                items = []
                count = max(len(scene_configs), len(scenes))
                for i in range(count):
                    sc = scene_configs[i] if i < len(scene_configs) else {}
                    scene = scenes[i] if i < len(scenes) else None
                    idx = sc.get("index", i + 1)
                    prompt = sc.get("prompt", scene.prompt if scene else "")
                    mode = sc.get("mode", "T2I")
                    has_image = scene and scene.image_path and os.path.isfile(scene.image_path)
                    thumb_path = scene.image_path if has_image else ""
                    mode_icon = "🖼️" if mode == "I2I" else "✏️"
                    status_icon = "✅" if has_image else "⏳"
                    items.append(PipelinePromptItem(
                        index=idx,
                        name=f"{status_icon} Scene {idx}\n{mode_icon} {mode}",
                        prompt=prompt, thumbnail_path=thumb_path,
                        accent_color=Theme.GREEN,
                    ))
                self._pipeline_prompt_table = PipelinePromptTable(
                    accent_color=Theme.GREEN, thumb_size=thumb_sz,
                )
                self._pipeline_prompt_table.set_items(items)
                self._thumb_layout.addWidget(self._pipeline_prompt_table)

            # AN-1: Fade-in scroll
            self._fade_in_thumb_scroll()
            return

        # ── Stage 6: Video prompts (PipelinePromptTable) ──
        if stage_name == "video_gen":
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            vid_aspect = config.get("video_aspect", "LANDSCAPE")
            if vid_aspect == "PORTRAIT":
                thumb_sz = (60, 107)
            else:
                thumb_sz = (107, 60)

            stage_obj = self._pipeline.state.get_stage("video_gen")
            video_configs = []
            if stage_obj.data and isinstance(stage_obj.data, dict):
                video_configs = stage_obj.data.get("video_configs", [])
            scenes = self._pipeline.state.scenes or []

            if not video_configs and not scenes:
                lbl = QLabel("⏳ Video configs will appear after Stage 6 runs")
                lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                self._thumb_layout.addWidget(lbl)
            else:
                items = []
                for i, vc in enumerate(video_configs):
                    scene = scenes[i] if i < len(scenes) else None
                    idx = vc.get("index", i + 1)
                    prompt = vc.get("prompt", "")
                    scene_tag = vc.get("scene_tag", f"Scene {idx}")
                    mode = vc.get("mode", "T2V")
                    img_path = vc.get("image_path", "")
                    has_video = scene and scene.video_path and os.path.isfile(scene.video_path)
                    # Resolve thumbnail: video frame > source image > empty
                    thumb_path = ""
                    if has_video:
                        try:
                            if not hasattr(self, '_frame_extractor'):
                                from core.frame_extractor import FrameExtractor
                                self._frame_extractor = FrameExtractor()
                            if self._frame_extractor.is_available:
                                thumb_path = self._frame_extractor.extract_first_frame(scene.video_path) or ""
                        except Exception:
                            pass
                        if not thumb_path:
                            thumb_path = scene.video_path  # fallback: let PipelinePromptTable try
                    elif img_path and os.path.isfile(img_path):
                        thumb_path = img_path
                    mode_icon = "🎬" if mode == "I2V" else ("📐" if mode == "R2V" else "📹")
                    status_icon = "✅" if has_video else "⏳"
                    duration = vc.get("duration_s", 8)
                    items.append(PipelinePromptItem(
                        index=idx,
                        name=f"{status_icon} {scene_tag}\n{mode_icon} {mode} • {duration}s",
                        prompt=prompt, thumbnail_path=thumb_path,
                        accent_color=Theme.PEACH,
                    ))
                self._pipeline_prompt_table = PipelinePromptTable(
                    accent_color=Theme.PEACH, thumb_size=thumb_sz,
                )
                self._pipeline_prompt_table.set_items(items)
                self._thumb_layout.addWidget(self._pipeline_prompt_table)

            # AN-1: Fade-in scroll
            self._fade_in_thumb_scroll()
            return

        # ── Stage 7 (concat): Final video row ──
        if stage_name == "concat":
            # TH-3: Respect video aspect config instead of hardcoding landscape
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            vid_aspect = config.get("video_aspect", "LANDSCAPE")
            if vid_aspect == "PORTRAIT":
                thumb_w, thumb_h = 100, 178
            else:
                thumb_w, thumb_h = 178, 100
            # Collect all scene videos + final
            items = []
            for s in (self._pipeline.state.scenes or []):
                if s.video_path and os.path.isfile(s.video_path):
                    items.append(("clip", f"Scene {s.index}", s.video_path))
            vp = self._pipeline.state.final_video_path
            if vp and os.path.isfile(vp):
                items.append(("final", "🎬 Final Video", vp))

            if not items:
                lbl = QLabel("⏳ Final video will appear after Stage 7 completes")
                lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                self._thumb_layout.insertWidget(0, lbl)
            else:
                for kind, name, path in items:
                    row = QFrame()
                    border_color = Theme.GREEN if kind == "final" else Theme.BORDER
                    bg = Theme.SURFACE0 if kind == "clip" else Theme.SURFACE1
                    row.setStyleSheet(f"""
                        QFrame {{
                            background: {bg};
                            border: 1px solid {border_color};
                            border-radius: 6px;
                        }}
                    """)
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(8, 6, 8, 6)
                    row_layout.setSpacing(10)

                    # Left: Thumbnail (video frame)
                    thumb_btn = QPushButton()
                    tw = thumb_w if kind == "clip" else thumb_w + 40
                    th = thumb_h if kind == "clip" else thumb_h + 20
                    thumb_btn.setFixedSize(tw, th)
                    frame_thumb = None
                    try:
                        if not hasattr(self, '_frame_extractor'):
                            from core.frame_extractor import FrameExtractor
                            self._frame_extractor = FrameExtractor()
                        if self._frame_extractor.is_available:
                            frame_thumb = self._frame_extractor.extract_first_frame(path)
                    except Exception as e:
                        log.warning(f"[Pipeline] Frame extraction failed: {e}")
                    if frame_thumb:
                        pix = QPixmap(frame_thumb).scaled(
                            tw - 4, th - 4, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        thumb_btn.setIcon(pix)
                        thumb_btn.setIconSize(QSize(tw - 4, th - 4))
                    else:
                        thumb_btn.setText(f"🎬\n{name}")
                    thumb_btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {Theme.MANTLE};
                            border: 1px dashed {Theme.OVERLAY0};
                            border-radius: 4px;
                            font-size: 14px; color: {Theme.SUBTEXT0};
                        }}
                        QPushButton:hover {{ border-color: {Theme.TEAL}; }}  /* TH-5: distinct from Stage 5 */
                    """)
                    thumb_btn.setToolTip(f"Click to play: {path}")
                    fp = path
                    thumb_btn.clicked.connect(lambda checked=False, p=fp: os.startfile(p))
                    row_layout.addWidget(thumb_btn)

                    # Right: Info
                    right_panel = QVBoxLayout()
                    right_panel.setSpacing(4)

                    icon = "🏁" if kind == "final" else "🎞️"
                    title_color = Theme.GREEN if kind == "final" else Theme.TEXT
                    name_lbl = QLabel(f"{icon} {name}")
                    name_lbl.setStyleSheet(f"""
                        color: {title_color}; font-weight: bold; font-size: 13px;
                        background: transparent; border: none;
                    """)
                    right_panel.addWidget(name_lbl)

                    # File info
                    try:
                        size_mb = os.path.getsize(path) / (1024 * 1024)
                        info_text = f"📁 {os.path.basename(path)}\n💾 {size_mb:.1f} MB"
                    except Exception:
                        info_text = f"📁 {os.path.basename(path)}"
                    info_lbl = QLabel(info_text)
                    info_lbl.setStyleSheet(f"""
                        color: {Theme.SUBTEXT0}; font-size: 11px;
                        background: transparent; border: none;
                    """)
                    info_lbl.setWordWrap(True)
                    right_panel.addWidget(info_lbl)

                    # Play button for final video
                    if kind == "final":
                        play_btn = QPushButton("▶️ Play Final Video")
                        play_btn.setFixedHeight(28)
                        play_btn.setStyleSheet(f"""
                            QPushButton {{
                                background: {Theme.GREEN}; color: {Theme.CRUST};
                                border: none; border-radius: 4px;
                                font-weight: bold; font-size: 11px;
                            }}
                            QPushButton:hover {{ background: {Theme.TEAL}; }}
                        """)
                        play_fp = path
                        play_btn.clicked.connect(lambda checked=False, p=play_fp: os.startfile(p))
                        right_panel.addWidget(play_btn)

                    right_panel.addStretch()
                    row_layout.addLayout(right_panel, stretch=1)
                    self._thumb_layout.insertWidget(self._thumb_layout.count() - 1, row)

            # AN-1 + AN-2: Fade-in scroll + stagger rows
            self._fade_in_thumb_scroll()
            rows = [self._thumb_layout.itemAt(i).widget() for i in range(self._thumb_layout.count()) if self._thumb_layout.itemAt(i).widget()]
            self._stagger_fade_cards(rows)
            return

        self._thumb_scroll.setVisible(False)

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
            self._generate_btn.setText("▶️​ Start Pipeline")
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

    def _run_pipeline_stage(self, force_stage: str = ""):
        """Run the next (or specified) pipeline stage."""
        import asyncio
        from core.production_pipeline import ProductionPipeline, STAGE_ORDER
        
        # Initialize pipeline if needed
        if not self._pipeline:
            # ── Validation ──
            topic_text = self._topic_input.toPlainText().strip()
            if not topic_text:
                from ui.popups import show_warning
                show_warning(
                    self, "⚠️ Production Input Required",
                    "Vui lòng nhập nội dung kịch bản hoặc tiêu đề video\n"
                    "vào ô Production Input trước khi bắt đầu pipeline."
                )
                return
            
            # AI config
            try:
                api_key, model_name, base_url, provider = self._get_ai_config()
            except ValueError as e:
                from ui.popups import show_warning
                show_warning(self, "API Error", str(e))
                return
            
            # Output folder fallback
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            if not config.get("output_folder", "").strip():
                import os
                fallback = os.path.join(os.path.expanduser("~"), "VEO_Production")
                os.makedirs(fallback, exist_ok=True)
                if self._setup_matrix:
                    self._setup_matrix.output_folder.setText(fallback)
                log.info(f"[TabProject] Output folder auto-set: {fallback}")
            
            # Create pipeline
            from services.ai_client_factory import create_ai_client
            client = create_ai_client(provider, base_url)
            self._pipeline = ProductionPipeline(
                gemini_client=client, api_key=api_key, model=model_name
            )
            # Full Production: entire text = ONE screenplay
            # Batch mode: split by newlines = multiple topics
            if self._pipeline_mode == "full_production":
                all_topics = [topic_text]  # Entire text as single topic
            else:
                all_topics = [t.strip() for t in topic_text.split("\n") if t.strip()]
            self._batch_topics = all_topics
            self._batch_topic_idx = 0
            self._batch_results = []  # (topic, success_bool)
            
            # Set first topic
            self._pipeline.state.topic = all_topics[0]
            if len(all_topics) > 1:
                log.info(f"[Pipeline] Multi-topic batch: {len(all_topics)} topics")
                self._stage_viewer.setPlainText(
                    f"🎬 Batch mode: {len(all_topics)} topics\n"
                    f"Starting topic 1/{len(all_topics)}: {all_topics[0][:60]}..."
                )

        # Find next stage (or use forced stage for retry/back)
        next_stage = force_stage or self._pipeline.get_next_stage()
        if not next_stage:
            self._stage_viewer.setPlainText("✅ Pipeline complete! All stages done.")
            return

        self._pipeline_current_stage = next_stage

        # Fix 4: Reset dot to yellow (running) — covers retry after red error
        self._stage_dots[next_stage].setStyleSheet(
            f"QPushButton {{ background-color: {Theme.YELLOW}; color: {Theme.CRUST}; "
            f"border: 1px solid {Theme.YELLOW}; border-radius: 3px; "
            f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
        )

        self._stage_run_btn.setEnabled(False)
        self._stage_run_btn.setText(f"⏳ Running: {next_stage}...")
        self._stage_confirm_btn.setEnabled(False)
        self._stage_back_btn.setEnabled(False)
        
        # ★ Set pipeline mode active — defers AutoStop during stage transitions
        if self.controller and hasattr(self.controller, 'set_pipeline_mode_active'):
            self.controller.set_pipeline_mode_active(True)

        # Get config from sidebar — sidebar values always take priority
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
        from core.production_pipeline import STAGE_ORDER
        self._stage_run_btn.setEnabled(True)

        if error:
            # Fix 2: Retry label on error
            self._stage_run_btn.setText("🔄 Retry")
            # Fix 12: Ensure viewer is visible for error messages (card stages hide it)
            self._stage_viewer.setVisible(True)
            # UI-4: Hide stale thumbnail gallery on error
            self._thumb_scroll.setVisible(False)
            self._stage_viewer.setPlainText(f"❌ Stage '{stage_name}' error:\n\n{error}")
            self._stage_dots[stage_name].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.RED}; color: {Theme.CRUST}; "
                f"border-radius: 3px; font-size: 10px; padding: 2px 6px; }}"
            )
            self._update_nav_buttons(stage_name)
            # R5-3 Fix: Reset queue awaiting flag on error so future auto-advance isn't blocked
            self._queue_awaiting_completion = False
        else:
            self._stage_run_btn.setText("▶️ Start Pipeline")
            
            # Stages 4-7: hide text viewer, show only vertical list/cards
            card_stages = {"character_gen", "scene_image_gen", "video_gen", "concat"}
            if stage_name in card_stages:
                self._stage_viewer.setVisible(False)
            else:
                self._stage_viewer.setVisible(True)
                self._stage_viewer.setPlainText(result_text)
            
            self._stage_confirm_btn.setEnabled(True)
            # AN-4: Flash dot 2x on completion instead of instant color change
            self._stage_dots[stage_name].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.GREEN}; color: {Theme.CRUST}; "
                f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )
            self._flash_dot(stage_name)
            self._update_nav_buttons(stage_name)
            self._update_thumbnails(stage_name)
            
            # Auto-confirm: auto-advance for all stages except concat (needs manual review)
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            if config.get("auto_confirm", False):
                from PySide6.QtCore import QTimer
                if stage_name == "concat":
                    log.info(f"[Pipeline] Auto-confirm skipped for 'concat' (needs manual review)")
                else:
                    log.info(f"[Pipeline] Auto-confirm triggered for '{stage_name}'")
                    QTimer.singleShot(500, self._on_stage_confirm)

    def _trigger_queue_auto_start(self):
        """Trigger auto-start on queue tab after pipeline adds tasks."""
        try:
            from config.settings import get_settings
            s = get_settings()
            if not getattr(s, 'auto_start_queue', False):
                log.info("[Pipeline] auto_start_queue setting is disabled, skipping auto-start")
                return

            mw = self.window()
            if not mw or not hasattr(mw, 'tab_instances'):
                log.warning("[Pipeline] No main window or tab_instances found")
                return
            
            queue_tab = mw.tab_instances.get('queue')
            if not queue_tab:
                log.warning("[Pipeline] queue tab not found in tab_instances")
                return
            
            # Log current state for debugging
            ctrl = getattr(queue_tab, 'controller', None)
            ready = ctrl.ready_count if ctrl else -1
            is_proc = getattr(queue_tab, '_is_processing', None)
            log.info(f"[Pipeline] Auto-start check: ready_count={ready}, _is_processing={is_proc}")
            
            if hasattr(queue_tab, '_auto_start_if_idle'):
                from PySide6.QtCore import QTimer
                # Use 1500ms delay to ensure tasks are fully registered in dispatcher
                QTimer.singleShot(1500, queue_tab._auto_start_if_idle)
                log.info("[Pipeline] Scheduled queue auto-start (1500ms delay)")
        except Exception as e:
            log.warning(f"[Pipeline] Failed to trigger auto-start: {e}")

    def _get_sanitized_project_name(self, config: dict) -> str:
        """Build a Windows-safe project name from pipeline state.
        
        Priority: cached > AI title (Stage1) > Bible title (Stage2) > existing folder > raw topic
        Strips Windows-invalid path chars: < > : " / \\ | ? *
        
        Once computed, the name is cached in _pipeline_project_name so all stages
        (4, 5, 6, 7) use the same folder name within one pipeline run.
        """
        # Return cached name if available (same pipeline run)
        cached = getattr(self, '_pipeline_project_name', '')
        if cached:
            return cached
        
        import re, os
        name = ""
        ai_source = ""
        
        if self._pipeline:
            # 1. Try AI-detected title from Stage 1 (duration_estimate)
            try:
                stage1 = self._pipeline.state.get_stage("duration_estimate")
                if stage1 and stage1.data:
                    ai_title = stage1.data.get("topic", "") or stage1.data.get("title", "")
                    if ai_title and ai_title not in ("Không có tiêu đề", "Untitled"):
                        name = ai_title
                        ai_source = "stage1"
            except Exception:
                pass
            
            # 2. Fallback: extract title from Stage 2 Bible text (script_analysis)
            if not name:
                try:
                    stage2 = self._pipeline.state.get_stage("script_analysis")
                    if stage2 and stage2.data:
                        bible = stage2.data.get("bible", "") or stage2.data.get("text", "")
                        if bible:
                            # Look for title patterns: "# Title", "Title:", first line
                            title_match = re.search(r'^#\s+(.+)', bible, re.MULTILINE)
                            if title_match:
                                name = title_match.group(1).strip()
                                ai_source = "stage2_header"
                            if not name:
                                title_match = re.search(r'(?:Title|Tiêu đề|Tựa đề)[:\s]+(.+)', bible, re.IGNORECASE)
                                if title_match:
                                    name = title_match.group(1).strip()
                                    ai_source = "stage2_title"
                except Exception:
                    pass
            
            # 3. Fallback: raw topic (but check if it's conversational junk)
            if not name:
                raw_topic = getattr(self._pipeline.state, 'topic', '') or ''
                if raw_topic:
                    # Detect conversational junk: starts with interjections, contains em dash, >40 chars
                    junk_prefixes = ('tuyệt', 'ok', 'được', 'vâng', 'hay', 'tốt', 'ừ', 'ờ')
                    is_junk = (
                        len(raw_topic) > 40
                        or '—' in raw_topic
                        or raw_topic.lower().startswith(junk_prefixes)
                        or raw_topic.count(' ') > 8
                    )
                    if not is_junk:
                        name = raw_topic
                        ai_source = "raw_topic"
                    else:
                        log.info(f"[Pipeline] Rejected junk topic: '{raw_topic[:60]}...'")
            
            # 4. Fallback: find existing VEO_Production folder matching character names
            if not name:
                name = self._find_existing_project_folder(config)
                if name:
                    ai_source = "existing_folder"
        
        if name:
            # Strip Windows-invalid path characters
            name = re.sub(r'[<>:"/\\|?*]', '', name)
            # Also strip markdown formatting artifacts
            name = name.replace('**', '').replace('~~', '')
            # Collapse whitespace
            name = re.sub(r'\s+', ' ', name).strip()
            # Truncate to safe length
            name = name[:50].rstrip('. ')
        
        # R5-1 Fix: Append batch index to prevent folder collision in batch mode
        if hasattr(self, '_batch_topics') and len(getattr(self, '_batch_topics', [])) > 1:
            batch_idx = getattr(self, '_batch_topic_idx', 0)
            name = f"{name}_{batch_idx + 1}" if name else f"Topic_{batch_idx + 1}"
        
        result = name if name else config.get("project_name", "Production")
        
        # Cache for subsequent stages in this pipeline run
        self._pipeline_project_name = result
        log.info(f"[Pipeline] Project name: '{result}' (source={ai_source or 'config'})")
        
        return result

    def _find_existing_project_folder(self, config: dict) -> str:
        """Find existing project folder in output dir matching current character names."""
        import os
        try:
            output_folder = config.get("output_folder", "")
            if not output_folder:
                output_folder = os.path.join(os.path.expanduser("~"), "VEO_Production")
            if not os.path.isdir(output_folder):
                return ""
            
            # Get current character names from pipeline
            char_names = set()
            if self._pipeline:
                chars = getattr(self._pipeline.state, 'characters', []) or []
                for ch in chars:
                    n = ch.get("name", "") if isinstance(ch, dict) else getattr(ch, "name", "")
                    if n:
                        char_names.add(n.lower().strip())
            
            if not char_names:
                return ""
            
            # Scan existing folders: find one with character/ subfolder containing matching filenames
            best_match = ""
            best_mtime = 0
            for folder_name in os.listdir(output_folder):
                folder_path = os.path.join(output_folder, folder_name)
                char_dir = os.path.join(folder_path, "character")
                if not os.path.isdir(char_dir):
                    continue
                # Check if character images match our character names
                existing_files = set()
                for sub in os.listdir(char_dir):
                    sub_path = os.path.join(char_dir, sub)
                    if os.path.isdir(sub_path):
                        for f in os.listdir(sub_path):
                            existing_files.add(os.path.splitext(f)[0].lower().strip())
                    elif os.path.isfile(sub_path):
                        existing_files.add(os.path.splitext(sub)[0].lower().strip())
                
                # Count matching characters
                matches = char_names & existing_files
                if len(matches) >= max(1, len(char_names) // 2):
                    mtime = os.path.getmtime(char_dir)
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best_match = folder_name
                        log.info(f"[Pipeline] Found existing folder '{folder_name}' matching {len(matches)}/{len(char_names)} chars")
            
            return best_match
        except Exception as e:
            log.debug(f"[Pipeline] Existing folder scan failed: {e}")
            return ""

    def _on_stage_confirm(self):
        """User confirms current stage result — parse edits, save to disk, advance."""
        if not self._pipeline or not self._pipeline_current_stage:
            return
        
        # Fix 1: Parse edited JSON correctly
        edited_data = self._parse_edited_stage_data()
        self._pipeline.confirm_stage(self._pipeline_current_stage, edited_data)
        self._stage_confirm_btn.setEnabled(False)
        
        # ── Save stage output to disk ──
        self._save_stage_to_disk(self._pipeline_current_stage)
        self._save_session_to_disk()  # Full session save for resume
        
        # Check if prompts stage → auto-feed to parsed panel
        if self._pipeline_current_stage == "scene_breakdown" and self._pipeline.state.scenes:
            scenes = self._pipeline.state.scenes
            prompts = [s.prompt for s in scenes if s.prompt]
            if prompts and self._parsed_panel:
                for i, p in enumerate(prompts):
                    self._parsed_panel.add_project(f"Scene {i+1}", {"Prompts": p}, "ready")

        # Stage 4-6: Send to VEO queue on confirm + track group_id for progress
        cur = self._pipeline_current_stage
        log.info(f"[Pipeline] Confirm: stage='{cur}', controller={'YES' if self.controller else 'NO'}")
        
        if cur == "character_gen" and self.controller:
            # Read edited prompts from character card UI (if available)
            if hasattr(self, '_pipeline_prompt_table') and self._pipeline_prompt_table:
                edited = self._pipeline_prompt_table.get_edited_prompts()
                if edited:
                    edited_prompts = [text for _, text in edited if text]
                    if edited_prompts:
                        stage_obj = self._pipeline.state.get_stage("character_gen")
                        stage_obj.prompts = edited_prompts
                        stage_obj.data["character_prompts"] = edited_prompts
                    log.info(f"[Pipeline] Stage 4: Updated {len(edited_prompts)} prompts from card UI edits")
            
            stage_obj = self._pipeline.state.get_stage("character_gen")
            prompts = stage_obj.prompts or []
            log.info(f"[Pipeline] Stage 4 prompts: {len(prompts)} found (from stage.prompts)")
            if not prompts:
                # Fallback: try data dict
                prompts = stage_obj.data.get("character_prompts", [])
                log.info(f"[Pipeline] Stage 4 fallback from data: {len(prompts)} found")
            if prompts:
                config = self._setup_matrix.get_config() if self._setup_matrix else {}
                # Build project name: prefer AI title, fallback to topic, sanitize for Windows
                project_name = self._get_sanitized_project_name(config)
                settings = {
                    "model": config.get("image_model", "GEM_PIX_2"),
                    "aspect_ratio": "PORTRAIT",  # Always PORTRAIT for character portraits
                    "download_quality": config.get("image_quality", "2k"),
                    "outputs_per_prompt": config.get("image_outputs", 1),
                    "output_folder": config.get("output_folder", ""),
                    "project_name": f"{project_name}/character",
                }
                if hasattr(self.controller, "add_t2i_batch"):
                    group_id = self.controller.add_t2i_batch(prompts=prompts, settings=settings)
                    log.info(f"[Pipeline] Stage 4: Sent {len(prompts)} T2I character prompts to queue (group={group_id})")
                    if group_id:
                        self._start_queue_polling(group_id, "character_gen")
                        self._trigger_queue_auto_start()
                    else:
                        log.warning("[Pipeline] Stage 4: add_t2i_batch returned empty group_id!")
                else:
                    log.warning("[Pipeline] Stage 4: controller has no add_t2i_batch method!")
            else:
                log.warning("[Pipeline] Stage 4: No character prompts available to send!")
        elif cur == "scene_image_gen" and self.controller:
            stage_obj = self._pipeline.state.get_stage("scene_image_gen")
            stage_data = stage_obj.data or {}
            configs = stage_data.get("scene_configs", [])
            
            # Read edited prompts from scene card UI (if available)
            if hasattr(self, '_pipeline_prompt_table') and self._pipeline_prompt_table:
                edited = self._pipeline_prompt_table.get_edited_prompts()
                if edited:
                    edited_prompts = [text for _, text in edited if text]
                    if edited_prompts:
                        for i, ep in enumerate(edited_prompts):
                            if i < len(configs):
                                configs[i]["prompt"] = ep
                        stage_obj.prompts = edited_prompts
                        log.info(f"[Pipeline] Stage 5: Updated {len(edited_prompts)} prompts from table UI edits")
            
            prompts = [c["prompt"] for c in configs if c.get("prompt")]
            log.info(f"[Pipeline] Stage 5 prompts: {len(prompts)} from scene_configs")
            if prompts:
                config = self._setup_matrix.get_config() if self._setup_matrix else {}
                project_name = self._get_sanitized_project_name(config)
                settings = {
                    "model": config.get("image_model", "GEM_PIX_2"),
                    "aspect_ratio": config.get("image_aspect", config.get("video_aspect", "LANDSCAPE")),
                    "download_quality": config.get("image_quality", "2k"),
                    "outputs_per_prompt": config.get("image_outputs", 1),
                    "output_folder": config.get("output_folder", ""),
                    "project_name": f"{project_name}/scenes",
                }
                # Build per-prompt image map from scene_configs (per-scene matching)
                # _stage_scene_image_gen already matched character names to each scene's prompt
                per_prompt_ref = {}
                for i, cfg in enumerate(configs):
                    cfg_refs = cfg.get("reference_images", [])
                    valid_refs = [r for r in cfg_refs if r and os.path.isfile(r)]
                    if valid_refs:
                        per_prompt_ref[i] = valid_refs
                
                if per_prompt_ref:
                    settings["per_prompt_images"] = per_prompt_ref
                    log.info(f"[Pipeline] Stage 5: {len(per_prompt_ref)}/{len(configs)} scenes with per-scene char refs")
                else:
                    # Fallback: all character images for all scenes (no per-scene match available)
                    ref_images = []
                    for c in (self._pipeline.state.characters or []):
                        if c.image_path and os.path.isfile(c.image_path):
                            ref_images.append(c.image_path)
                    if ref_images:
                        settings["reference_images"] = ref_images
                        log.info(f"[Pipeline] Stage 5: {len(ref_images)} character ref images for I2I (fallback: all chars)")
                
                if hasattr(self.controller, "add_t2i_batch"):
                    group_id = self.controller.add_t2i_batch(prompts=prompts, settings=settings)
                    log.info(f"[Pipeline] Stage 5: Sent {len(prompts)} scene prompts to queue (group={group_id})")
                    if group_id:
                        self._start_queue_polling(group_id, "scene_image_gen")
                        self._trigger_queue_auto_start()
        elif cur == "video_gen" and self.controller:
            stage_data = self._pipeline.state.get_stage("video_gen").data or {}
            configs = stage_data.get("video_configs", [])
            
            # Read edited prompts from video card UI (if available)
            if hasattr(self, '_pipeline_prompt_table') and self._pipeline_prompt_table:
                edited = self._pipeline_prompt_table.get_edited_prompts()
                if edited:
                    for idx, text in edited:
                        ci = idx - 1  # PipelinePromptItem.index is 1-based
                        if text and 0 <= ci < len(configs):
                            configs[ci]["prompt"] = text
                    log.info(f"[Pipeline] Stage 6: Updated prompts from table UI edits")
            
            prompts = [c["prompt"] for c in configs if c.get("prompt")]
            log.info(f"[Pipeline] Stage 6 prompts: {len(prompts)} from video_configs")
            if prompts:
                config = self._setup_matrix.get_config() if self._setup_matrix else {}
                project_name = self._get_sanitized_project_name(config)
                settings = {
                    "model": config.get("video_model", "Veo 3.1 - Fast"),
                    "aspect_ratio": config.get("video_aspect", "LANDSCAPE"),
                    "download_quality": config.get("video_quality", "1080p"),
                    "duration": config.get("clip_duration", 8),
                    "outputs_per_prompt": config.get("video_outputs", 1),
                    "output_folder": config.get("output_folder", ""),
                    "project_name": f"{project_name}/video",
                }
                # R4-2 Fix: Pass voice_enabled from pipeline stage data to engine
                stage_data = self._pipeline.state.get_stage("video_gen").data if self._pipeline else {}
                settings["voice_enabled"] = stage_data.get("voice_enabled", config.get("voice_enabled", True))
                # Route: per-scene I2V (scene image) or R2V (char images from Stage 4)
                from config.constants import WorkflowType
                scenes = self._pipeline.state.scenes if self._pipeline else []
                char_images = []
                for c in (self._pipeline.state.characters or []):
                    if c.image_path and os.path.isfile(c.image_path):
                        char_images.append(c.image_path)
                
                per_prompt_images = {}
                per_prompt_workflows = {}
                i2v_count = 0
                r2v_count = 0
                t2v_count = 0
                for i, s in enumerate(scenes):
                    if i >= len(prompts):
                        break
                    if s.image_path and os.path.isfile(s.image_path):
                        # Scene has Stage 5 image → I2V (image as start frame)
                        per_prompt_images[i] = [s.image_path]
                        per_prompt_workflows[i] = "I2V"
                        i2v_count += 1
                    elif char_images:
                        # No scene image, but have character refs → R2V
                        per_prompt_images[i] = char_images
                        per_prompt_workflows[i] = "R2V"
                        r2v_count += 1
                    else:
                        # No images at all → T2V
                        per_prompt_workflows[i] = "T2V"
                        t2v_count += 1
                
                log.info(
                    f"[Pipeline] Stage 6 routing: {i2v_count} I2V, "
                    f"{r2v_count} R2V, {t2v_count} T2V out of {len(prompts)} prompts"
                )
                
                if per_prompt_images:
                    group_id = self.controller.submit_prompts(
                        prompts=prompts,
                        workflow=WorkflowType.I2V,  # default, overridden per-task
                        per_prompt_images=per_prompt_images,
                        per_prompt_workflows=per_prompt_workflows,
                        settings=settings,
                    )
                    log.info(f"[Pipeline] Stage 6: Sent {len(prompts)} mixed-workflow prompts (group={group_id})")
                elif hasattr(self.controller, "add_t2v_batch"):
                    # Final fallback: T2V (no images at all)
                    group_id = self.controller.add_t2v_batch(prompts=prompts, settings=settings)
                    log.info(f"[Pipeline] Stage 6: Sent {len(prompts)} T2V prompts (no images) (group={group_id})")
                else:
                    group_id = None
                    log.warning("[Pipeline] Stage 6: No suitable controller method available")
                if group_id:
                    self._start_queue_polling(group_id, "video_gen")
                    self._trigger_queue_auto_start()

        # Auto-advance AND auto-run next stage
        # BUT: if we just started queue polling, defer advance to _on_queue_group_complete
        if getattr(self, '_queue_awaiting_completion', False):
            log.info(f"[Pipeline] Auto-advance deferred — waiting for queue group to complete")
            return
        
        next_stage = self._pipeline.get_next_stage()
        if next_stage:
            self._stage_viewer.setPlainText(
                f"✅ Stage '{self._pipeline_current_stage}' confirmed.\n\n"
                f"⏳ Auto-running: {next_stage}..."
            )
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, self._run_pipeline_stage)
        else:
            # All stages complete for current topic
            self._advance_to_next_topic()
    
    # ── Multi-Topic Batch Advance ────────────────────────────────
    
    def _advance_to_next_topic(self):
        """Advance to next topic in batch, or show summary if all done."""
        from core.production_pipeline import STAGE_ORDER
        
        topics = getattr(self, '_batch_topics', [])
        idx = getattr(self, '_batch_topic_idx', 0)
        results = getattr(self, '_batch_results', [])
        
        # R5-4 Fix: Track actual success based on pipeline stage statuses
        from core.production_pipeline import StageStatus
        has_error = False
        if self._pipeline:
            for sn in ["duration_estimate", "script_analysis", "scene_breakdown",
                       "character_gen", "scene_image_gen", "video_gen", "concat"]:
                sr = self._pipeline.state.get_stage(sn)
                if sr.status == StageStatus.ERROR:
                    has_error = True
                    break
        current_topic = topics[idx] if idx < len(topics) else "Unknown"
        results.append((current_topic, not has_error))
        self._batch_results = results
        
        next_idx = idx + 1
        self._batch_topic_idx = next_idx
        
        if next_idx < len(topics):
            # More topics → reset pipeline, reset UI dots, start next
            next_topic = topics[next_idx]
            log.info(f"[Pipeline] Batch: topic {next_idx + 1}/{len(topics)}: {next_topic[:60]}")
            
            # Reset pipeline state for new topic
            self._pipeline.reset()
            self._pipeline_project_name = ''  # Clear cached name for new topic
            
            # R5-2 Fix: Clear ImageLibrary tags from previous topic to prevent cross-contamination
            try:
                from services.image_library import get_image_library
                lib = get_image_library()
                if hasattr(lib, 'clear_session_tags'):
                    lib.clear_session_tags()
                    log.info("[Pipeline] R5-2: Cleared ImageLibrary session tags for new topic")
            except Exception as e:
                log.debug(f"[Pipeline] R5-2: ImageLibrary tag cleanup skipped: {e}")
            self._pipeline.state.topic = next_topic
            
            # Reset UI stage dots
            for sn, dot in self._stage_dots.items():
                dot.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {Theme.SURFACE1};
                        color: {Theme.SUBTEXT0};
                        border: 1px solid {Theme.BORDER};
                        border-radius: 3px;
                        font-size: 10px; padding: 2px 6px;
                    }}
                """)
            
            # Show transition message
            self._stage_viewer.setPlainText(
                f"✅ Topic {idx + 1}/{len(topics)} complete: {current_topic[:50]}\n\n"
                f"⏳ Starting topic {next_idx + 1}/{len(topics)}:\n"
                f"{next_topic[:100]}..."
            )
            
            # Clear thumbnails
            while self._thumb_layout.count() > 1:
                item = self._thumb_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # Auto-start next topic's pipeline after short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._run_pipeline_stage)
        else:
            # All topics done → show batch summary
            total = len(results)
            ok = sum(1 for _, s in results if s)
            
            summary_lines = [f"🎬 Batch Production Complete: {ok}/{total} topics\n"]
            for i, (topic, success) in enumerate(results):
                icon = "✅" if success else "❌"
                summary_lines.append(f"  {icon} {i+1}. {topic[:60]}")
            
            self._stage_viewer.setPlainText("\n".join(summary_lines))
            log.info(f"[Pipeline] Batch complete: {ok}/{total} topics OK")
            # ★ Pipeline fully done — allow AutoStop
            if self.controller and hasattr(self.controller, 'set_pipeline_mode_active'):
                self.controller.set_pipeline_mode_active(False)
            if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
                self.controller.set_pipeline_queue_active(False)
    
    # ── Queue Progress Tracking ─────────────────────────────────
    
    def _start_queue_polling(self, group_id: str, stage_name: str):
        """Start polling queue every 2s for group completion.
        
        Tracks progress, populates image_path/video_path from results,
        and auto-advances pipeline when group finishes.
        """
        from PySide6.QtCore import QTimer
        
        # Stop any existing polling timer
        if hasattr(self, '_queue_poll_timer') and self._queue_poll_timer:
            self._queue_poll_timer.stop()
        
        self._queue_poll_group_id = group_id
        self._queue_poll_stage = stage_name
        self._queue_awaiting_completion = True  # Block auto-advance until queue finishes
        # Notify controller to defer auto-stop during pipeline queue processing
        if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
            self.controller.set_pipeline_queue_active(True)
        self._queue_poll_timer = QTimer(self)
        self._queue_poll_timer.setInterval(2000)  # 2 seconds
        self._queue_poll_timer.timeout.connect(self._check_queue_progress)
        self._queue_poll_timer.start()
        
        log.info(f"[Pipeline] Started queue polling for group={group_id}, stage={stage_name}")
        self._stage_viewer.setPlainText(
            f"⏳ Queue Processing: 0/? tasks\n"
            f"Stage: {stage_name}\n"
            f"Group: {group_id}\n\n"
            f"Waiting for VEO engine to process...\n"
            f"Switch to Queue tab to see detailed progress."
        )
    
    def _check_queue_progress(self):
        """Poll controller for queue group status, update UI."""
        if not hasattr(self, '_queue_poll_group_id') or not self.controller:
            return
        
        group_id = self._queue_poll_group_id
        stage_name = self._queue_poll_stage
        
        if not hasattr(self.controller, 'get_group_status'):
            log.warning("[Pipeline] Controller missing get_group_status method")
            return
        
        try:
            status = self.controller.get_group_status(group_id)
        except Exception as e:
            log.warning(f"[Pipeline] Queue poll error: {e}")
            return
        
        if not status:
            return
        
        completed = status["completed"]
        failed = status["failed"]
        total = status["total"]
        
        # Update stage viewer with progress
        progress_bar = "█" * completed + "░" * (total - completed - failed) + "✗" * failed
        self._stage_viewer.setPlainText(
            f"⏳ Queue Processing: {completed}/{total} completed"
            f"{f', {failed} failed' if failed else ''}\n"
            f"Stage: {stage_name}\n"
            f"Group: {group_id}\n\n"
            f"[{progress_bar}]\n\n"
            f"Switch to Queue tab for detailed progress."
        )
        
        # Populate paths from completed tasks
        for task_info in status.get("completed_tasks", []):
            self._populate_path_from_task(stage_name, task_info)
        
        # Debounce: only update thumbnails if completed count changed
        prev_completed = getattr(self, '_queue_poll_prev_completed', -1)
        if completed != prev_completed:
            self._queue_poll_prev_completed = completed
            self._update_thumbnails(stage_name)
        
        # Check if group is done
        if status.get("is_done"):
            self._queue_poll_timer.stop()
            self._queue_awaiting_completion = False  # Unblock auto-advance
            log.info(f"[Pipeline] Queue group {group_id} completed: {completed}/{total} OK, {failed} failed")
            self._on_queue_group_complete(stage_name, status)
    
    def _populate_path_from_task(self, stage_name: str, task_info: dict):
        """Populate pipeline state paths from a completed queue task."""
        idx = task_info.get("prompt_index", 0)
        best_file = task_info.get("best_file", "")
        if not best_file:
            return
        
        if stage_name == "character_gen":
            chars = self._pipeline.state.characters
            if idx < len(chars):
                if not chars[idx].image_path:  # Don't overwrite
                    char_name = chars[idx].name
                    final_path = best_file
                    
                    # Rename file to character name for [tag] auto-detection
                    if char_name:
                        import re as _re
                        from pathlib import Path as _Path
                        src = _Path(best_file)
                        safe_name = _re.sub(r'[<>:"/\\|?*]', '_', char_name.strip())
                        dest = src.parent / f"{safe_name}{src.suffix}"
                        try:
                            if dest.exists() and dest != src:
                                # Append index to avoid collision
                                dest = src.parent / f"{safe_name}_{idx}{src.suffix}"
                            src.rename(dest)
                            final_path = str(dest)
                            log.info(f"[Pipeline] Renamed char image: {src.name} → {dest.name}")
                        except Exception as e:
                            log.warning(f"[Pipeline] Could not rename char image: {e}")
                    
                    chars[idx].image_path = final_path
                    log.info(f"[Pipeline] ← character[{idx}].image_path = {final_path}")
                    
                    # Register in ImageLibrary for [tag] auto-resolution
                    if char_name:
                        try:
                            from services.image_library import get_image_library
                            lib = get_image_library()
                            tag_name = char_name.lower().strip()
                            img, was_updated = lib.update_or_add_image(
                                final_path, tags=[tag_name],
                                category="Characters", copy_to_library=False
                            )
                            if was_updated:
                                log.info(f"[Pipeline] ♻️ [{tag_name}] UPDATED in ImageLibrary → {final_path} (old mediaIds cleared)")
                            else:
                                log.info(f"[Pipeline] ✅ [{tag_name}] registered in ImageLibrary → {final_path}")
                        except Exception as e:
                            log.warning(f"[Pipeline] ImageLibrary registration failed: {e}")
        elif stage_name == "scene_image_gen":
            scenes = self._pipeline.state.scenes
            if idx < len(scenes):
                if not scenes[idx].image_path:
                    scene = scenes[idx]
                    final_path = best_file
                    
                    # Build scene tag name from title or index
                    scene_tag = scene.title.strip() if scene.title else f"Scene_{scene.index}"
                    
                    # Rename file to scene tag for [tag] auto-detection in Stage 6
                    import re as _re
                    from pathlib import Path as _Path
                    src = _Path(best_file)
                    safe_name = _re.sub(r'[<>:"/\\|?*]', '_', scene_tag)
                    dest = src.parent / f"{safe_name}{src.suffix}"
                    try:
                        if dest.exists() and dest != src:
                            dest = src.parent / f"{safe_name}_{idx}{src.suffix}"
                        src.rename(dest)
                        final_path = str(dest)
                        log.info(f"[Pipeline] Renamed scene image: {src.name} → {dest.name}")
                    except Exception as e:
                        log.warning(f"[Pipeline] Could not rename scene image: {e}")
                    
                    scenes[idx].image_path = final_path
                    log.info(f"[Pipeline] ← scene[{idx}].image_path = {final_path}")
                    
                    # Register in ImageLibrary for [tag] auto-resolution in Stage 6
                    try:
                        from services.image_library import get_image_library
                        lib = get_image_library()
                        tag_name = scene_tag.lower().strip()
                        img, was_updated = lib.update_or_add_image(
                            final_path, tags=[tag_name],
                            category="Backgrounds", copy_to_library=False
                        )
                        if was_updated:
                            log.info(f"[Pipeline] ♻️ [{tag_name}] UPDATED in ImageLibrary → {final_path} (old mediaIds cleared)")
                        else:
                            log.info(f"[Pipeline] ✅ [{tag_name}] registered in ImageLibrary → {final_path}")
                    except Exception as e:
                        log.warning(f"[Pipeline] Scene ImageLibrary registration failed: {e}")
        elif stage_name == "video_gen":
            scenes = self._pipeline.state.scenes
            if idx < len(scenes):
                if not scenes[idx].video_path:
                    scenes[idx].video_path = best_file
                    log.info(f"[Pipeline] ← scene[{idx}].video_path = {best_file}")
    
    def _on_queue_group_complete(self, stage_name: str, status: dict):
        """Queue group finished → update UI → auto-advance if enabled."""
        completed = status["completed"]
        failed = status["failed"]
        total = status["total"]
        
        if failed > 0:
            self._stage_viewer.setPlainText(
                f"⚠️ Queue completed with errors: {completed}/{total} OK, {failed} failed\n"
                f"Stage: {stage_name}\n\n"
                f"Some tasks failed. Check Queue tab for details.\n"
                f"You can still confirm to proceed with available results."
            )
        else:
            self._stage_viewer.setPlainText(
                f"✅ Queue completed: {completed}/{total} tasks done\n"
                f"Stage: {stage_name}\n\n"
                f"All results populated. Click 'Confirm & Next' to proceed."
            )
        
        self._update_thumbnails(stage_name)
        # Fix 6: Only re-enable confirm if stage hasn't been confirmed yet
        from core.production_pipeline import StageStatus
        stage_result = self._pipeline.state.get_stage(stage_name)
        if stage_result.status != StageStatus.CONFIRMED:
            self._stage_confirm_btn.setEnabled(True)
        
        # Auto-advance if enabled AND no failures
        # NOTE: Stage was already confirmed BEFORE queue polling started.
        # We must NOT call _on_stage_confirm() again — that would double-confirm
        # and double-submit T2I tasks. Instead, advance directly to next stage.
        config = self._setup_matrix.get_config() if self._setup_matrix else {}
        if config.get("auto_confirm", False) and failed == 0:
            from PySide6.QtCore import QTimer
            next_stage = self._pipeline.get_next_stage() if self._pipeline else None
            if next_stage:
                # R2-6 Fix: Check video_path completeness before concat
                if next_stage == "concat" and self._pipeline:
                    scenes = self._pipeline.state.scenes or []
                    missing_videos = [s.index for s in scenes if not s.video_path]
                    if missing_videos:
                        log.warning(
                            f"[Pipeline] R2-6: {len(missing_videos)} scenes missing video_path "
                            f"before concat: {missing_videos}. Concat may produce partial video."
                        )
                        self._stage_viewer.setPlainText(
                            f"⚠️ Queue completed: {completed}/{total} tasks done\n"
                            f"Stage: {stage_name}\n\n"
                            f"WARNING: {len(missing_videos)} scenes missing video files.\n"
                            f"Missing: scenes {missing_videos}\n\n"
                            f"Click 'Confirm & Next' to concatenate available clips,\n"
                            f"or check Queue tab for failed tasks."
                        )
                        # Don't auto-advance — let user decide
                        if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
                            self.controller.set_pipeline_queue_active(False)
                        self._stage_confirm_btn.setEnabled(True)
                        return
                
                log.info(f"[Pipeline] Auto-advancing to '{next_stage}' after queue completion (stage '{stage_name}' already confirmed)")
                # ★ Keep pipeline_queue_active=True during auto-advance transition
                # to prevent AutoStop from killing engine before next stage adds tasks
                if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
                    self.controller.set_pipeline_queue_active(True)
                self._stage_viewer.setPlainText(
                    f"✅ Queue completed: {completed}/{total} tasks done\n"
                    f"Stage: {stage_name}\n\n"
                    f"⏳ Auto-running: {next_stage}..."
                )
                QTimer.singleShot(500, self._run_pipeline_stage)
            else:
                # No next stage — allow auto-stop
                if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
                    self.controller.set_pipeline_queue_active(False)
                log.info(f"[Pipeline] Queue complete, no next stage — advancing to next topic")
                QTimer.singleShot(500, self._advance_to_next_topic)
        else:
            # No auto-advance — allow auto-stop
            if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
                self.controller.set_pipeline_queue_active(False)
    
    # ── Disk Save ──────────────────────────────────────────────
    
    def _save_stage_to_disk(self, stage_name: str):
        """Auto-save stage output to output folder on confirm.
        
        Creates: output_folder/Production_<topic>/
            01_duration_estimate.txt
            02_bible.txt
            03_prompts.txt
            04_character_prompts.txt
            05_scene_image_prompts.txt
            06_video_configs.txt
            07_concat_plan.txt
            _pipeline_state.json  (full JSON backup)
        """
        import os, json as _json
        from pathlib import Path
        
        output_folder = ""
        if hasattr(self, '_setup_matrix') and hasattr(self._setup_matrix, 'output_folder'):
            output_folder = self._setup_matrix.output_folder.text().strip()
        
        if not output_folder:
            return  # No output folder configured
        
        # Fix 3: Use same folder name as _get_sanitized_project_name
        #         to ensure text files and media files are co-located
        config = self._setup_matrix.get_config() if self._setup_matrix else {}
        topic_slug = self._get_sanitized_project_name(config)
        if not topic_slug:
            topic_slug = "Production"
        
        # ── Numbering logic for multi-video projects ──
        # Get current project index (for multi-topic batches)
        project_index = getattr(self._pipeline.state, '_project_index', 0)
        total_projects = getattr(self._pipeline.state, '_total_projects', 1)
        
        if total_projects > 1:
            folder_name = f"{project_index + 1:03d} - {topic_slug}"
        else:
            folder_name = topic_slug
        
        project_dir = Path(output_folder) / folder_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Stage → filename mapping
        from core.production_pipeline import STAGE_ORDER
        stage_idx = STAGE_ORDER.index(stage_name) + 1 if stage_name in STAGE_ORDER else 0
        
        stage_filenames = {
            "duration_estimate": "duration_estimate",
            "script_analysis": "bible",
            "scene_breakdown": "prompts",
            "character_gen": "character_prompts",
            "scene_image_gen": "scene_image_prompts",
            "video_gen": "video_configs",
            "concat": "concat_plan",
        }
        
        filename = stage_filenames.get(stage_name, stage_name)
        txt_path = project_dir / f"{stage_idx:02d}_{filename}.txt"
        
        # Get formatted display text (same as what user sees)
        stage_result = self._pipeline.state.get_stage(stage_name)
        try:
            display = _format_stage_result(stage_name, stage_result)
        except Exception:
            display = str(stage_result.data)
        
        # Save human-readable text
        try:
            txt_path.write_text(display, encoding='utf-8')
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to save stage file: {e}")
        
        # Save JSON backup (machine-readable)
        json_path = project_dir / "_pipeline_state.json"
        try:
            # Merge with existing state file
            existing = {}
            if json_path.exists():
                try:
                    existing = _json.loads(json_path.read_text(encoding='utf-8'))
                except Exception:
                    pass
            existing[stage_name] = {
                "status": stage_result.status.value if hasattr(stage_result.status, 'value') else str(stage_result.status),
                "data": stage_result.data,
            }
            json_path.write_text(
                _json.dumps(existing, ensure_ascii=False, indent=2, default=str),
                encoding='utf-8'
            )
        except Exception:
            pass
    
    def _parse_edited_stage_data(self) -> dict:
        """Parse user-edited viewer text into correct pipeline data keys.
        
        Stage 2 (script_analysis): User edits Bible text → pass back as-is
        Stage 3 (scene_breakdown): User edits prompts text → pass back as-is
        """
        stage = self._pipeline_current_stage
        # Fix 10: Card stages use card UI edits, not hidden text viewer
        card_stages = {"character_gen", "scene_image_gen", "video_gen", "concat"}
        if stage in card_stages:
            return {}
        text = self._stage_viewer.toPlainText().strip()
        
        # Strip header lines (📋 Reviewing:... / ===)
        lines = text.split("\n")
        content_start = 0
        for i, line in enumerate(lines):
            if line.startswith("=" * 10):
                content_start = i + 1
                break
        clean_text = "\n".join(lines[content_start:]).strip() if content_start > 0 else text
        
        if stage == "script_analysis":
            # Bible text — pass directly, pipeline stores in state.script_json["bible"]
            if clean_text:
                return {"bible": clean_text}
        elif stage == "scene_breakdown":
            # Prompts text — pass directly, pipeline re-parses into scenes
            if clean_text:
                return {"prompts_text": clean_text}
        elif stage == "duration_estimate":
            import re
            m = re.search(r'(?:VEO clips|Scene count):\s*(\d+)', text)
            if m:
                return {"scene_count": int(m.group(1))}
        # R3-2: Card stages (character_gen, scene_image_gen, video_gen) 
        # are handled via card UI edits in _on_stage_confirm, not text parsing.
        # Dead code branches removed.
        return {}

    def _on_stage_skip(self):
        """User skips current stage → auto-advance to next."""
        if not self._pipeline or not self._pipeline_current_stage:
            return
        self._pipeline.skip_stage(self._pipeline_current_stage)
        self._save_session_to_disk()  # Full session save for resume
        self._stage_dots[self._pipeline_current_stage].setStyleSheet(
            f"QPushButton {{ background-color: {Theme.SURFACE1}; color: {Theme.SUBTEXT0}; "
            f"border: 1px solid {Theme.BORDER}; border-radius: 3px; "
            f"font-size: 10px; padding: 2px 6px; }}"
        )
        self._stage_confirm_btn.setEnabled(False)
        # Fix 8: Update nav buttons after skip
        self._update_nav_buttons(self._pipeline_current_stage)
        next_stage = self._pipeline.get_next_stage()
        if next_stage:
            self._stage_viewer.setPlainText(f"Stage skipped.\n\n⏳ Auto-running: {next_stage}...")
            # Fix 2: Auto-advance to next stage (same as confirm)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, self._run_pipeline_stage)
        else:
            self._advance_to_next_topic()
    
    def _on_stage_back(self):
        """Navigate back to previous stage for review/edit.
        
        - Shows previous stage's saved result for editing
        - Does NOT reset stages — just lets user review/edit
        - Re-confirming with edits (via Confirm button) will reset downstream stages
        """
        from core.production_pipeline import STAGE_ORDER, StageStatus
        if not self._pipeline or not self._pipeline_current_stage:
            return
        
        prev_stage = self._pipeline.get_prev_stage(self._pipeline_current_stage)
        if not prev_stage:
            return
        
        # Restore current dot to its real status color (green/grey/red)
        self._restore_dot_color(self._pipeline_current_stage)
        
        # Mark prev stage dot as active (blue = review)
        self._stage_dots[prev_stage].setStyleSheet(
            f"QPushButton {{ background-color: {Theme.BLUE}; color: {Theme.CRUST}; "
            f"border: 1px solid {Theme.BLUE}; border-radius: 3px; "
            f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
        )
        
        self._pipeline_current_stage = prev_stage
        
        # Show saved result for review/editing
        self._show_stage_review(prev_stage)
        
        self._stage_run_btn.setText("▶ Start Pipeline")
        self._stage_run_btn.setEnabled(True)
        stage_result = self._pipeline.state.get_stage(prev_stage)
        # Fix 11: For card stages, only enable confirm after thumbnails render
        card_stages = {"character_gen", "scene_image_gen", "video_gen", "concat"}
        if prev_stage in card_stages:
            self._stage_confirm_btn.setEnabled(False)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(200, lambda: self._stage_confirm_btn.setEnabled(bool(stage_result.data)))
        else:
            self._stage_confirm_btn.setEnabled(bool(stage_result.data))
        self._update_nav_buttons(prev_stage)
    
    def _on_stage_next(self):
        """Navigate forward to the next confirmed/completed stage.
        
        Shows saved result of next stage for review without re-running.
        Only navigates to stages that have data (CONFIRMED, COMPLETED, or ERROR with data).
        """
        from core.production_pipeline import STAGE_ORDER, StageStatus
        if not self._pipeline or not self._pipeline_current_stage:
            return
        
        idx = STAGE_ORDER.index(self._pipeline_current_stage) if self._pipeline_current_stage in STAGE_ORDER else -1
        if idx < 0 or idx >= len(STAGE_ORDER) - 1:
            return
        
        next_stage = STAGE_ORDER[idx + 1]
        next_result = self._pipeline.state.get_stage(next_stage)
        
        # Can only navigate forward to stages that have been run (have data)
        if not next_result.data and next_result.status == StageStatus.PENDING:
            return
        
        # Mark current dot back to its real status color
        self._restore_dot_color(self._pipeline_current_stage)
        
        # Mark next stage dot as active (blue = review)
        self._stage_dots[next_stage].setStyleSheet(
            f"QPushButton {{ background-color: {Theme.BLUE}; color: {Theme.CRUST}; "
            f"border: 1px solid {Theme.BLUE}; border-radius: 3px; "
            f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
        )
        
        self._pipeline_current_stage = next_stage
        self._show_stage_review(next_stage)
        
        self._stage_run_btn.setText("▶ Start Pipeline")
        self._stage_run_btn.setEnabled(True)
        self._stage_confirm_btn.setEnabled(bool(next_result.data))
        self._update_nav_buttons(next_stage)
    
    def _show_stage_review(self, stage_name: str):
        """Show saved stage data in viewer for review/editing.
        Uses _format_result() for consistent formatted display.
        """
        # Toggle viewer visibility: hide for card-based stages, show for others
        card_stages = {"character_gen", "scene_image_gen", "video_gen", "concat"}
        if stage_name in card_stages:
            self._stage_viewer.setVisible(False)
        else:
            self._stage_viewer.setVisible(True)
        # Height logic is handled inside _update_thumbnails
        self._update_thumbnails(stage_name)

        # Fix 7: Skip text formatting for hidden card stages
        if stage_name in card_stages:
            return

        stage_result = self._pipeline.state.get_stage(stage_name)
        if stage_result.data:
            try:
                display = _format_stage_result(stage_name, stage_result)
            except Exception:
                display = str(stage_result.data)
            self._stage_viewer.setPlainText(
                f"\U0001f4cb Reviewing: {stage_name}\n"
                f"Edit below, then Confirm & Next or Start Pipeline to re-run.\n"
                f"{'=' * 40}\n\n{display}"
            )
        else:
            self._stage_viewer.setPlainText(
                f"\U0001f4cb {stage_name}\nNo saved data. Click '\u25b6 Start Pipeline' to run."
            )
    

    def _update_nav_buttons(self, stage_name: str):
        """Update Back/Next button enabled state based on current stage position."""
        from core.production_pipeline import STAGE_ORDER, StageStatus
        idx = STAGE_ORDER.index(stage_name) if stage_name in STAGE_ORDER else 0
        
        # Back: enabled if not first stage
        self._stage_back_btn.setEnabled(idx > 0)
        
        # Next: enabled if next stage has been run (has data)
        if idx < len(STAGE_ORDER) - 1:
            next_s = STAGE_ORDER[idx + 1]
            next_result = self._pipeline.state.get_stage(next_s)
            self._stage_next_btn.setEnabled(
                bool(next_result.data) or next_result.status != StageStatus.PENDING
            )
        else:
            self._stage_next_btn.setEnabled(False)
    
    def _restore_dot_color(self, stage_name: str):
        """Restore a stage dot to its real status color (green/red/grey)."""
        from core.production_pipeline import StageStatus
        stage = self._pipeline.state.get_stage(stage_name)
        # Fix 1: WAITING_CONFIRM also shows green (stage completed successfully)
        if stage.status in (StageStatus.CONFIRMED, StageStatus.WAITING_CONFIRM):
            color, weight = Theme.GREEN, "font-weight: bold; "
        elif stage.status == StageStatus.SKIPPED:
            color, weight = Theme.SURFACE1, ""
        elif stage.error:
            color, weight = Theme.RED, ""
        else:
            color, weight = Theme.SURFACE1, ""
        self._stage_dots[stage_name].setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: {Theme.CRUST}; "
            f"border-radius: 3px; font-size: 10px; {weight}padding: 2px 6px; }}"
        )
    
    # ── Session Save / Load ─────────────────────────────────────
    
    def _save_session_to_disk(self):
        """Save full pipeline session to project folder for resume.
        
        Creates _pipeline_session.json in the project output folder.
        Called on every confirm/skip so incomplete sessions can be restored.
        """
        import json as _json
        from pathlib import Path
        
        if not self._pipeline:
            return
        
        output_folder = ""
        if hasattr(self, '_setup_matrix') and hasattr(self._setup_matrix, 'output_folder'):
            output_folder = self._setup_matrix.output_folder.text().strip()
        if not output_folder:
            return
        
        config = self._setup_matrix.get_config() if self._setup_matrix else {}
        topic_slug = self._get_sanitized_project_name(config)
        if not topic_slug:
            topic_slug = "Production"
        
        project_index = getattr(self._pipeline.state, '_project_index', 0)
        total_projects = getattr(self._pipeline.state, '_total_projects', 1)
        folder_name = f"{project_index + 1:03d} - {topic_slug}" if total_projects > 1 else topic_slug
        
        project_dir = Path(output_folder) / folder_name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        session_path = project_dir / "_pipeline_session.json"
        try:
            session_data = self._pipeline.state.to_session_dict()
            # Add UI-specific state
            session_data["_ui"] = {
                "pipeline_current_stage": self._pipeline_current_stage or "",
                "viewer_text": self._stage_viewer.toPlainText() if hasattr(self, '_stage_viewer') else "",
            }
            session_path.write_text(
                _json.dumps(session_data, ensure_ascii=False, indent=2, default=str),
                encoding='utf-8'
            )
            log.info(f"[Pipeline] Session saved → {session_path}")
        except Exception as e:
            log.warning(f"[Pipeline] Session save failed: {e}")
    
    def _restore_dot_color(self, stage_name: str):
        """Restore a stage dot color based on pipeline state."""
        if stage_name not in self._stage_dots:
            return
        dot = self._stage_dots[stage_name]
        if not self._pipeline:
            return
        sr = self._pipeline.state.stages.get(stage_name)
        if not sr:
            # Default: pending
            dot.setStyleSheet(
                f"QPushButton {{ background-color: {Theme.SURFACE1}; "
                f"color: {Theme.SUBTEXT0}; border: 1px solid {Theme.BORDER}; "
                f"border-radius: 3px; font-size: 10px; padding: 2px 6px; }}"
            )
            return
        from core.production_pipeline import StageStatus
        if sr.status in (StageStatus.CONFIRMED, StageStatus.SKIPPED):
            dot.setStyleSheet(
                f"QPushButton {{ background-color: {Theme.GREEN}; color: white; "
                f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )
        elif sr.status == StageStatus.WAITING_CONFIRM:
            dot.setStyleSheet(
                f"QPushButton {{ background-color: {Theme.YELLOW}; color: black; "
                f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )
        else:
            dot.setStyleSheet(
                f"QPushButton {{ background-color: {Theme.SURFACE1}; "
                f"color: {Theme.SUBTEXT0}; border: 1px solid {Theme.BORDER}; "
                f"border-radius: 3px; font-size: 10px; padding: 2px 6px; }}"
            )
    
    def _update_nav_buttons(self, current_stage: str = ""):
        """Update navigation button states (prev/next)."""
        # Nav buttons are optional — skip if not present
        pass
    
    def _auto_restore_pipeline(self):
        """Auto-restore pipeline from most recent session on app startup.
        
        Scans output_folder for subfolders containing _pipeline_state.json,
        picks the most recently modified one, and restores it.
        Called once via QTimer.singleShot(500) after UI init.
        """
        import json as _json
        from pathlib import Path
        
        # Skip if pipeline already has data (user started a new project)
        if self._pipeline and self._pipeline_current_stage:
            return
        
        # Get output folder from setup matrix
        output_folder = ""
        if hasattr(self, '_setup_matrix') and hasattr(self._setup_matrix, 'output_folder'):
            output_folder = self._setup_matrix.output_folder.text().strip()
        
        if not output_folder or not Path(output_folder).is_dir():
            return
        
        # Find most recent _pipeline_state.json across all project subfolders
        best_file = None
        best_mtime = 0
        
        root = Path(output_folder)
        for state_file in root.rglob("_pipeline_state.json"):
            try:
                mtime = state_file.stat().st_mtime
                if mtime > best_mtime:
                    best_mtime = mtime
                    best_file = state_file
            except OSError:
                continue
        
        if not best_file:
            return
        
        # Check if state file is recent (within last 7 days)
        import time
        age_days = (time.time() - best_mtime) / 86400
        if age_days > 7:
            log.debug(
                f"[Pipeline] Auto-restore skipped: {best_file.parent.name} "
                f"is {age_days:.0f} days old"
            )
            return
        
        try:
            raw = _json.loads(best_file.read_text(encoding='utf-8'))
            
            from core.production_pipeline import (
                ProductionPipeline, PipelineState, StageResult,
                STAGE_ORDER, StageStatus
            )
            
            # Check if it has actual completed stages
            completed_count = sum(
                1 for sn, sr in raw.items()
                if not sn.startswith('_')
                and sr.get('status') in ('confirmed', 'completed', 'skipped')
            )
            if completed_count == 0:
                return
            
            # Restore state
            restored_state = PipelineState()
            for stage_name, sr_data in raw.items():
                if stage_name.startswith('_'):
                    continue
                try:
                    status = StageStatus(sr_data.get('status', 'pending'))
                except (ValueError, KeyError):
                    status = StageStatus.PENDING
                sr = StageResult(
                    stage=stage_name,
                    status=status,
                    data=sr_data.get('data', {}),
                )
                restored_state.stages[stage_name] = sr
            
            # Create pipeline
            if not self._pipeline:
                self._pipeline = ProductionPipeline()
            self._pipeline.state = restored_state
            
            # Find current stage (first non-completed)
            current_stage = STAGE_ORDER[0]
            for sn in STAGE_ORDER:
                sr = restored_state.stages.get(sn)
                if sr and sr.status in (StageStatus.CONFIRMED, StageStatus.SKIPPED):
                    continue
                current_stage = sn
                break
            
            self._pipeline_current_stage = current_stage
            
            # Restore stage dot colors
            for sn in STAGE_ORDER:
                self._restore_dot_color(sn)
            
            # Highlight current stage
            if current_stage in self._stage_dots:
                from config.theme import Theme
                self._stage_dots[current_stage].setStyleSheet(
                    f"QPushButton {{ background-color: {Theme.BLUE}; color: white; "
                    f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
                )
            
            # Show review
            self._show_stage_review(current_stage)
            self._update_thumbnails(current_stage)
            
            # Enable buttons
            self._stage_run_btn.setText("▶️ Continue Pipeline")
            self._stage_run_btn.setEnabled(True)
            sr = restored_state.stages.get(current_stage)
            self._stage_confirm_btn.setEnabled(
                bool(sr and sr.data and sr.status == StageStatus.WAITING_CONFIRM)
            )
            self._update_nav_buttons(current_stage)
            
            # Restore topic
            topic = restored_state.topic
            if topic and hasattr(self, '_topics_input'):
                self._topics_input.setPlainText(topic)
            
            log.info(
                f"[Pipeline] ♻️ Auto-restored from {best_file.parent.name}: "
                f"{completed_count} completed stage(s), current={current_stage}"
            )
        except Exception as e:
            log.warning(f"[Pipeline] Auto-restore failed: {e}")
    
    def _load_project_session(self):
        """Load a pipeline session from a project folder.
        
        Opens a folder picker, looks for _pipeline_session.json (preferred)
        or _pipeline_state.json (fallback), and restores the pipeline state.
        """
        import json as _json
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog
        from core.production_pipeline import (
            ProductionPipeline, PipelineState, STAGE_ORDER, StageStatus
        )
        
        # Default to output_folder if available
        start_dir = ""
        if hasattr(self, '_setup_matrix') and hasattr(self._setup_matrix, 'output_folder'):
            start_dir = self._setup_matrix.output_folder.text().strip()
        
        folder = QFileDialog.getExistingDirectory(
            self, "Select Project Folder", start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return
        
        folder_path = Path(folder)
        
        # Try _pipeline_session.json first (full session with UI state)
        session_file = folder_path / "_pipeline_session.json"
        state_file = folder_path / "_pipeline_state.json"
        
        session_data = None
        is_full_session = False
        
        if session_file.exists():
            try:
                session_data = _json.loads(session_file.read_text(encoding='utf-8'))
                is_full_session = True
                log.info(f"[Pipeline] Loading full session from {session_file}")
            except Exception as e:
                log.warning(f"[Pipeline] Failed to parse session file: {e}")
        
        if not session_data and state_file.exists():
            try:
                raw = _json.loads(state_file.read_text(encoding='utf-8'))
                # _pipeline_state.json has flat {stage_name: {status, data}} format
                # Convert to session format
                session_data = {"stages": raw}
                log.info(f"[Pipeline] Loading legacy state from {state_file}")
            except Exception as e:
                log.warning(f"[Pipeline] Failed to parse state file: {e}")
        
        if not session_data:
            from ui.popups import show_warning
            show_warning(
                self, "No Session Found",
                f"Không tìm thấy _pipeline_session.json hoặc _pipeline_state.json\n"
                f"trong: {folder}"
            )
            return
        
        # Restore pipeline state
        if is_full_session:
            restored_state = PipelineState.from_session_dict(session_data)
        else:
            # Legacy: only stage data available
            restored_state = PipelineState()
            for stage_name, sr_data in session_data.get("stages", {}).items():
                try:
                    status = StageStatus(sr_data.get("status", "pending"))
                except (ValueError, KeyError):
                    status = StageStatus.PENDING
                from core.production_pipeline import StageResult
                sr = StageResult(
                    stage=stage_name,
                    status=status,
                    data=sr_data.get("data", {}),
                )
                restored_state.stages[stage_name] = sr
        
        # Create pipeline if needed
        if not self._pipeline:
            self._pipeline = ProductionPipeline()
        
        # Swap in restored state
        self._pipeline.state = restored_state
        
        # Determine current stage: from UI state or find last completed + 1
        ui_state = session_data.get("_ui", {})
        current_stage = ui_state.get("pipeline_current_stage", "")
        
        if not current_stage:
            # Find first non-confirmed/non-skipped stage
            current_stage = STAGE_ORDER[0]
            for sn in STAGE_ORDER:
                sr = restored_state.stages.get(sn)
                if sr and sr.status in (StageStatus.CONFIRMED, StageStatus.SKIPPED):
                    continue
                current_stage = sn
                break
        
        self._pipeline_current_stage = current_stage
        
        # Restore stage dot colors
        for sn in STAGE_ORDER:
            self._restore_dot_color(sn)
        
        # Highlight current stage
        if current_stage in self._stage_dots:
            self._stage_dots[current_stage].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.BLUE}; color: white; "
                f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )
        
        # Restore viewer content
        viewer_text = ui_state.get("viewer_text", "")
        if viewer_text:
            self._stage_viewer.setVisible(True)
            self._stage_viewer.setPlainText(viewer_text)
        else:
            self._show_stage_review(current_stage)
        
        # Update thumbnails for current stage
        self._update_thumbnails(current_stage)
        
        # Enable/disable buttons
        self._stage_run_btn.setText("▶️ Continue Pipeline")
        self._stage_run_btn.setEnabled(True)
        sr = restored_state.stages.get(current_stage)
        self._stage_confirm_btn.setEnabled(
            bool(sr and sr.data and sr.status == StageStatus.WAITING_CONFIRM)
        )
        self._update_nav_buttons(current_stage)
        
        # Update topic in sidebar if available
        topic = restored_state.topic
        if topic and hasattr(self, '_topics_input'):
            self._topics_input.setPlainText(topic)
        
        loaded_stages = sum(
            1 for sn in STAGE_ORDER
            if sn in restored_state.stages
            and restored_state.stages[sn].status not in (StageStatus.PENDING,)
        )
        log.info(
            f"[Pipeline] Session loaded: {loaded_stages}/{len(STAGE_ORDER)} stages, "
            f"current={current_stage}, topic='{topic[:60]}'"
        )

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
            # Use AI-detected title if available, fallback to topic name
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            name = self._get_sanitized_project_name(config)
            if name in ("Production", "Untitled"):
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
                    # Auto-start engine if setting enabled
                    if queue_tab and hasattr(queue_tab, '_auto_start_if_idle'):
                        from PySide6.QtCore import QTimer
                        QTimer.singleShot(500, queue_tab._auto_start_if_idle)
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

    # ── Session Persistence ─────────────────────────────────────

    def save_state(self) -> dict:
        """Save tab state for session persistence."""
        state = {}
        # Topic input text
        if hasattr(self, '_topic_input'):
            state["topic_text"] = self._topic_input.toPlainText()
        # Checkbox states
        if hasattr(self, '_auto_add_cb'):
            state["auto_add_queue"] = self._auto_add_cb.isChecked()
        if hasattr(self, '_prompt_format_combo'):
            state["prompt_format"] = self._prompt_format_combo.currentIndex()
        if hasattr(self, '_skip_research_cb'):
            state["skip_research"] = self._skip_research_cb.isChecked()
        if hasattr(self, '_skip_seo_cb'):
            state["skip_seo"] = self._skip_seo_cb.isChecked()
        if hasattr(self, '_per_topic_tmpl_cb'):
            state["per_topic_template"] = self._per_topic_tmpl_cb.isChecked()
        # SetupMatrix sidebar config
        if self._setup_matrix and hasattr(self._setup_matrix, 'get_config'):
            state["sidebar"] = self._setup_matrix.get_config()
        return state

    def restore_state(self, data: dict, restore_options=None):
        """Restore tab state from saved session data."""
        if not data:
            return
        # Check granular setting
        if restore_options and not getattr(restore_options, 'restore_project_builder', True):
            return
        try:
            # Topic input
            topic_text = data.get("topic_text", "")
            if topic_text and hasattr(self, '_topic_input'):
                self._topic_input.setPlainText(topic_text)
            # Checkboxes
            if "auto_add_queue" in data and hasattr(self, '_auto_add_cb'):
                self._auto_add_cb.setChecked(data["auto_add_queue"])
            if "prompt_format" in data and hasattr(self, '_prompt_format_combo'):
                self._prompt_format_combo.setCurrentIndex(data["prompt_format"])
            if "skip_research" in data and hasattr(self, '_skip_research_cb'):
                self._skip_research_cb.setChecked(data["skip_research"])
            if "skip_seo" in data and hasattr(self, '_skip_seo_cb'):
                self._skip_seo_cb.setChecked(data["skip_seo"])
            if "per_topic_template" in data and hasattr(self, '_per_topic_tmpl_cb'):
                self._per_topic_tmpl_cb.setChecked(data["per_topic_template"])
            # SetupMatrix sidebar
            sidebar = data.get("sidebar", {})
            if sidebar and self._setup_matrix:
                self._restore_setup_matrix(sidebar)
        except Exception as e:
            log.debug(f"[TabProject] Restore state error: {e}")

    def _restore_setup_matrix(self, config: dict):
        """Restore SetupMatrix combos from saved config dict."""
        m = self._setup_matrix
        try:
            # Pipeline mode
            if "pipeline_mode" in config and hasattr(m, '_pipeline_mode'):
                idx = m._pipeline_mode.findData(config["pipeline_mode"])
                if idx >= 0:
                    m._pipeline_mode.setCurrentIndex(idx)
            # Detail mode
            if "detail_mode" in config and hasattr(m, '_detail_mode'):
                idx = m._detail_mode.findData(config["detail_mode"])
                if idx >= 0:
                    m._detail_mode.setCurrentIndex(idx)
            # Project type
            if "project_type" in config and hasattr(m, 'd0_project_type'):
                idx = m.d0_project_type.findData(config["project_type"])
                if idx >= 0:
                    m.d0_project_type.setCurrentIndex(idx)
            # Checkboxes
            if "voice_enabled" in config and hasattr(m, '_voice_enabled'):
                m._voice_enabled.setChecked(config["voice_enabled"])
            if "auto_confirm" in config and hasattr(m, '_auto_confirm'):
                m._auto_confirm.setChecked(config["auto_confirm"])
            # Duration
            if "target_duration" in config and hasattr(m, '_target_duration'):
                m._target_duration.setText(config.get("target_duration", ""))
            if "clip_duration" in config and hasattr(m, '_clip_duration'):
                idx = m._clip_duration.findData(config["clip_duration"])
                if idx >= 0:
                    m._clip_duration.setCurrentIndex(idx)
            if "video_count" in config and hasattr(m, '_video_count'):
                m._video_count.setValue(config["video_count"])
            # Production settings
            if "output_folder" in config and hasattr(m, 'output_folder'):
                m.output_folder.setText(config.get("output_folder", ""))
            if "video_aspect" in config and hasattr(m, 'video_aspect'):
                m.video_aspect.setCurrentIndex(1 if config.get("video_aspect") == "PORTRAIT" else 0)
            if "video_model" in config and hasattr(m, 'video_model'):
                idx = m.video_model.findText(config.get("video_model", ""))
                if idx >= 0:
                    m.video_model.setCurrentIndex(idx)
            if "video_quality" in config and hasattr(m, 'video_quality'):
                idx = m.video_quality.findText(config.get("video_quality", ""))
                if idx >= 0:
                    m.video_quality.setCurrentIndex(idx)
            if "image_model" in config and hasattr(m, 'image_model'):
                idx = m.image_model.findData(config.get("image_model"))
                if idx >= 0:
                    m.image_model.setCurrentIndex(idx)
            if "image_quality" in config and hasattr(m, 'image_quality'):
                idx = m.image_quality.findText(config.get("image_quality", ""))
                if idx >= 0:
                    m.image_quality.setCurrentIndex(idx)
            # Content dimensions (multi-select)
            if "category" in config and hasattr(m, 'd1_category') and hasattr(m.d1_category, 'set_selected_by_data'):
                m.d1_category.set_selected_by_data(config.get("category", []))
            if "structure" in config and hasattr(m, 'd2_structure'):
                vals = config.get("structure", [])
                if vals:
                    m._auto_select_combo(m.d2_structure, vals[0])
            if "style" in config and hasattr(m, 'd3_style'):
                vals = config.get("style", [])
                if vals:
                    m._auto_select_combo(m.d3_style, vals[0])
            if "character" in config and hasattr(m, 'd4_character'):
                vals = config.get("character", [])
                if vals:
                    m._auto_select_combo(m.d4_character, vals[0])
            if "audience" in config and hasattr(m, 'd5_audience'):
                vals = config.get("audience", [])
                if vals:
                    m._auto_select_combo(m.d5_audience, vals[0])
            if "persona" in config and hasattr(m, 'd6_persona'):
                val = config.get("persona")
                if val:
                    m._auto_select_combo(m.d6_persona, val)
            if "tone" in config and hasattr(m, 'd7_tone'):
                vals = config.get("tone", [])
                if vals:
                    m._auto_select_combo(m.d7_tone, vals[0])
            if "voice" in config and hasattr(m, 'd8_voice') and hasattr(m.d8_voice, 'set_selected_by_data'):
                m.d8_voice.set_selected_by_data(config.get("voice", []))
            if "camera_technique" in config and hasattr(m, 'd9_camera') and hasattr(m.d9_camera, 'set_selected_by_data'):
                m.d9_camera.set_selected_by_data(config.get("camera_technique", []))
        except Exception as e:
            log.debug(f"[TabProject] Restore matrix error: {e}")

