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


def _format_stage_result(stage_name: str, result, state=None) -> str:
    """Format stage result for human-readable review display.
    
    Args:
        stage_name: Stage identifier
        result: StageResult object
        state: Optional PipelineState for version/episode grouping
    """
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
        # Multi-version / episode info
        v_count = d.get('video_count', 1)
        if v_count > 1:
            mode_label = "Multi-Idea" if d.get('multi_idea') else "Multi-Version"
            lines.append(f"\n🎬 {mode_label}: {v_count} videos")
        ep_count = d.get('episode_count', 1)
        if d.get('episode_enabled') and ep_count > 1:
            lines.append(f"📺 Episodes: {ep_count} tập")
        lines.append("\n(Bạn có thể chỉnh sửa scene count/duration ở Sidebar trước khi Confirm)")
    elif stage_name == "bible_gen":
        # Bible text (plain, editable)
        bible = result.data.get("bible", "") if result.data else ""
        
        # ── Grouped display: Multi-Idea Bibles ──
        if state and state.is_multi_version() and state.multi_idea and state.versions:
            lines.append(f"📖 PRODUCTION BIBLES ({len(state.versions)} ideas)\n")
            lines.append("(Mỗi idea có Bible riêng. Bạn có thể chỉnh sửa từng Bible.)")
            for v in state.versions:
                sep = f"{'═' * 20} 📌 {v.label} {'═' * 20}"
                lines.append(f"\n{sep}")
                v_bible = v.bible or "(No Bible generated)"
                lines.append(v_bible)
            lines.append(f"\n{'═' * 50}")
        elif bible:
            lines.append("📖 PRODUCTION BIBLE\n")
            lines.append("(Bạn có thể chỉnh sửa kịch bản bên dưới trước khi Confirm)")
            lines.append("=" * 40)
            lines.append(bible)
        else:
            lines.append(str(result.data))
    elif stage_name == "scene_breakdown":
        # Plain text prompts (editable)
        raw = result.data.get("raw_prompts", "") if result.data else ""
        
        # ── Grouped display: Multi-Version prompts ──
        has_versions = state and state.is_multi_version() and state.versions
        has_episodes = state and state.is_multi_episode() and state.episodes
        
        if has_versions and any(v.scenes for v in state.versions):
            total_scenes = sum(len(v.scenes) for v in state.versions)
            lines.append(f"🎬 VEO PROMPTS — {len(state.versions)} versions ({total_scenes} total scenes)\n")
            lines.append("(Mỗi version có prompts riêng biệt.)")
            version_scenes_info = result.data.get("version_scenes", {}) if result.data else {}
            for v in state.versions:
                scene_count = len(v.scenes)
                sep = f"{'═' * 18} 📌 {v.label} ({scene_count} scenes) {'═' * 18}"
                lines.append(f"\n{sep}")
                if v.scenes:
                    for s in v.scenes:
                        lines.append(f"\n--- Scene {s.index} ---")
                        lines.append(s.prompt or s.description or "(empty)")
                else:
                    lines.append("(No scenes generated yet)")
            lines.append(f"\n{'═' * 55}")
        elif has_episodes and any(ep.scenes for ep in state.episodes):
            total_scenes = sum(len(ep.scenes) for ep in state.episodes)
            lines.append(f"🎬 VEO PROMPTS — {len(state.episodes)} episodes ({total_scenes} total scenes)\n")
            lines.append("(Mỗi tập có prompts riêng biệt. Characters shared.)")
            for ep in state.episodes:
                scene_count = len(ep.scenes)
                sep = f"{'═' * 18} 📺 {ep.label} ({scene_count} scenes) {'═' * 18}"
                lines.append(f"\n{sep}")
                if ep.scenes:
                    for s in ep.scenes:
                        lines.append(f"\n--- Scene {s.index} ---")
                        lines.append(s.prompt or s.description or "(empty)")
                else:
                    lines.append("(No scenes generated yet)")
            lines.append(f"\n{'═' * 55}")
        elif raw:
            scene_cfgs = result.data.get("scene_configs", []) if result.data else []
            count = result.data.get('prompt_count', 0)
            lines.append(f"🎬 VEO PROMPTS ({count} scenes)\n")
            lines.append("(Bạn có thể chỉnh sửa prompts bên dưới trước khi Confirm)")
            lines.append("=" * 40)
            if scene_cfgs:
                for sc in scene_cfgs:
                    idx = sc.get('scene_index', '?')
                    stype = sc.get('scene_type', '')
                    sc_type = sc.get('type', '')
                    shot = sc.get('shot_type', '')
                    cam = sc.get('camera_movement', '')
                    setting = sc.get('setting', '')
                    chars = sc.get('characters', [])
                    audio = sc.get('audio_cue', '')
                    overlay = sc.get('has_text_overlay', False)
                    lines.append(f"\n--- Scene {idx} [{stype}] [{sc_type}] ---")
                    lines.append(f"  📷 {shot} | 🎥 {cam}")
                    if setting:
                        lines.append(f"  📍 Setting: {setting}")
                    if chars:
                        lines.append(f"  👤 Characters: {', '.join(chars)}")
                        actions = sc.get('character_actions', {})
                        for ch, act in actions.items():
                            lines.append(f"     • {ch}: {act}")
                    if audio:
                        lines.append(f"  🔊 Audio: {audio}")
                    if overlay:
                        lines.append(f"  📝 Text Overlay: {sc.get('text_overlay_content', 'N/A')}")
                    lines.append(f"  ⏱️ Duration: {sc.get('duration_s', 8)}s")
                    lines.append(f"  Prompt: {sc.get('prompt_text', '')[:200]}...")
            else:
                lines.append(raw)
    elif stage_name == "character_gen":
        d = result.data or {}
        char_cfgs = d.get("character_configs", [])
        names = d.get("character_names", [])
        prompts = d.get("character_prompts", [])
        lines.append(f"👤 CHARACTER T2I PROMPTS ({len(prompts)} characters)\n")
        lines.append("(Bạn có thể chỉnh sửa prompts bên dưới trước khi Confirm)")
        lines.append("Mode: T2I (Text → Image)")
        lines.append("=" * 40)
        if char_cfgs:
            for cc in char_cfgs:
                name = cc.get('character_name', '?')
                ctype = cc.get('type', 'main')
                role = cc.get('role', '')
                age = cc.get('age', '')
                layout = cc.get('layout', '4-view turnaround')
                app = cc.get('appearance', {})
                type_icon = '⭐' if ctype == 'main' else ('👥' if ctype == 'group' else '🔹')
                lines.append(f"\n{type_icon} [{name}] ({ctype}) — {layout}")
                if role:
                    lines.append(f"  Role: {role}")
                if age:
                    lines.append(f"  Age: {age}")
                if app:
                    for field in ['height', 'skin', 'face', 'hair', 'clothing_top', 'clothing_bottom', 'accessories']:
                        val = app.get(field, '')
                        if val:
                            lines.append(f"  {field}: {val}")
                prompt = cc.get('prompt_text', '')
                if prompt:
                    lines.append(f"  Prompt: {prompt[:200]}...")
        else:
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
            idx = c.get('scene_index', c.get('index', '?'))
            ref_count = len(c.get("reference_images", []))
            ref_info = f" [+{ref_count} refs]" if ref_count > 0 else ""
            sc_type = c.get('type', '')
            setting = c.get('setting', '')
            chars = c.get('characters_in_scene', [])
            overlay = c.get('has_text_overlay', False)
            lines.append(f"\n--- Scene {idx} [{c['mode']}] [{sc_type}]{ref_info} ---")
            if setting:
                lines.append(f"  📍 {setting}")
            if chars:
                lines.append(f"  👤 {', '.join(chars)}")
            if overlay:
                lines.append(f"  📝 Text Overlay: {c.get('text_overlay_content', 'N/A')}")
            lines.append(f"  Prompt: {c.get('prompt_text', c.get('prompt', ''))[:200]}...")
    elif stage_name == "video_gen":
        d = result.data or {}
        configs = d.get("video_configs", [])
        modes = d.get("modes", [])
        lines.append(f"🎬 VIDEO GENERATION ({len(configs)} clips)\n")
        lines.append(f"Modes: {', '.join(modes)}")
        lines.append("=" * 40)
        for c in configs:
            mode_icon = "🎬" if c["mode"] == "I2V" else ("🔗" if c["mode"] == "R2V" else "📹")
            idx = c.get('scene_index', c.get('index', '?'))
            img = f" | Image: {c.get('image_path', '')}" if c.get("image_path") else (" | Refs: char images" if c["mode"] == "R2V" else "")
            sc_type = c.get('type', '')
            cam = c.get('camera_movement', '')
            tone = c.get('tone', '')
            audio = c.get('audio_cue', '')
            chars = c.get('characters_in_scene', [])
            lines.append(f"\n{mode_icon} Scene {idx} [{c['mode']}] [{sc_type}] ({c.get('duration_s', 8)}s){img}")
            if cam and cam != 'static':
                lines.append(f"  🎥 Camera: {cam}")
            if chars:
                lines.append(f"  👤 {', '.join(chars)}")
            if tone:
                lines.append(f"  🎭 Tone: {tone}")
            if audio:
                lines.append(f"  🔊 Audio: {audio}")
            prompt_text = c.get('prompt_text', c.get('prompt', ''))
            lines.append(f"  Prompt: {prompt_text[:150]}...")
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
    # Signal: queue task completed (thread-safe bridge from engine thread)
    _pipeline_queue_signal = Signal()

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
        
        # Pipeline ↔ Queue bidirectional tracking
        # Maps group_id → {"project_idx": int, "stage": str, "prompt_count": int}
        self._active_group_ids: dict = {}
        self._pipeline_auto_restore_enabled = True
        self._pipeline_persist_epoch = 0
        # Queue bridge (extracted queue-polling + session persistence logic)
        from ui.pipeline_queue_bridge import PipelineQueueBridge
        self._queue_bridge = PipelineQueueBridge()
        self._pipeline_queue_signal.connect(self._on_pipeline_queue_check)

        self._setup_ui()
        self._init_builder()
        
        # Register queue callback for pipeline tracking (deferred until controller ready)
        if self.controller:
            self._register_queue_callback()
            self._queue_bridge.set_controller(self.controller)
        
        # Auto-restore pipeline state from last session (deferred so UI is ready)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._auto_restore_pipeline)

    def get_searchable_widgets(self):
        """Return editable text widgets for global Search/Replace."""
        widgets = []
        if hasattr(self, '_topic_input'):
            widgets.append(self._topic_input)
        if hasattr(self, '_stage_viewer'):
            widgets.append(self._stage_viewer)
        return widgets

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
            # Fallback: if no templates found from filesystem, use embedded
            if self._scanner and tmpl_count == 0:
                tmpl_count = self._scanner.load_embedded()
                if tmpl_count:
                    log.info(f"[TabProject] Using {tmpl_count} embedded templates (data/workflows/ not found)")

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
            self._setup_matrix.image_library_clicked.connect(self._on_open_image_library)
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

        find_btn = QPushButton("🔍 Find")
        find_btn.setProperty("variant", "secondary")
        find_btn.setProperty("btnSize", "sm")
        find_btn.setToolTip("Find & Replace (Ctrl+H)")
        find_btn.clicked.connect(self._on_open_find_replace)
        btn_row.addWidget(find_btn)

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
            "bible_gen": "2.Bible",
            "scene_breakdown": "3.Prompts",
            "character_gen": "4.Character",
            "scene_image_gen": "5.Scenes",
            "video_gen": "6.Video",
            "concat": "7.Final",
        }
        for stage_name in STAGE_ORDER:
            dot = QPushButton(STAGE_LABELS.get(stage_name, stage_name))
            dot.setFixedHeight(24)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.SURFACE1};
                    color: {Theme.SUBTEXT0};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 3px;
                    font-size: 10px; padding: 2px 6px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.SURFACE2};
                    border-color: {Theme.BLUE};
                    color: {Theme.TEXT};
                }}
            """)
            dot.setToolTip(f"Click to view {STAGE_LABELS.get(stage_name, stage_name)} data")
            dot.clicked.connect(lambda checked, _sn=stage_name: self._on_stage_dot_clicked(_sn))
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
        self._thumb_scroll.setMaximumHeight(16777215)
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
        self._thumb_scroll.setWidgetResizable(True)
        self._thumb_scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        panel_layout.addWidget(self._thumb_scroll, stretch=3)

        # ★ Centralized button state tracking
        self._viewing_mode = "idle"  # idle | running | done | error | review | complete

        # Action buttons — [Start] [✅Confirm] [📂Output] [🗑Reset] [📥Load]
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._stage_run_btn = QPushButton("▶️ Start")
        self._stage_run_btn.setProperty("variant", "success")
        self._stage_run_btn.setProperty("btnSize", "sm")
        self._stage_run_btn.setFixedHeight(30)
        self._stage_run_btn.clicked.connect(self._on_stage_run_clicked)
        btn_row.addWidget(self._stage_run_btn)

        self._stage_confirm_btn = QPushButton("✅ Confirm & Next")
        self._stage_confirm_btn.setProperty("variant", "success")
        self._stage_confirm_btn.setProperty("btnSize", "sm")
        self._stage_confirm_btn.setFixedHeight(30)
        self._stage_confirm_btn.setEnabled(False)
        self._stage_confirm_btn.clicked.connect(self._on_stage_confirm)
        btn_row.addWidget(self._stage_confirm_btn)

        self._stage_output_btn = QPushButton("\U0001f4c2 Output")
        self._stage_output_btn.setProperty("variant", "secondary")
        self._stage_output_btn.setProperty("btnSize", "sm")
        self._stage_output_btn.setFixedHeight(30)
        self._stage_output_btn.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self._stage_output_btn)

        self._stage_reset_btn = QPushButton("\U0001f5d1 Reset")
        self._stage_reset_btn.setProperty("variant", "warning")
        self._stage_reset_btn.setProperty("btnSize", "sm")
        self._stage_reset_btn.setFixedHeight(30)
        self._stage_reset_btn.setToolTip("Clear current pipeline and reset viewer to initial state")
        self._stage_reset_btn.clicked.connect(self._reset_pipeline_viewer)
        btn_row.addWidget(self._stage_reset_btn)

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
        bright = (f"QPushButton {{ background-color: {Theme.GREEN}; color: black; "
                  f"border: 2px solid {Theme.TEXT}; "
                  f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}")
        normal = (f"QPushButton {{ background-color: {Theme.GREEN}; color: black; "
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

    # ── GRP: Collapsible group header for pipeline stages ──
    def _create_pipeline_group(self, group_id: str, title: str, icon: str,
                                item_count: int, accent_color: str,
                                content_widget, expanded: bool = True):
        """Create a collapsible group container (header + content) like Queue tab groups."""
        from PySide6.QtWidgets import QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout
        from PySide6.QtCore import Qt

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # === HEADER ===
        header = QFrame()
        header.setObjectName(f"pipelineGroupHeader_{group_id}")
        header.setFixedHeight(36)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setStyleSheet(f"""
            QFrame#{header.objectName()} {{
                background-color: {Theme.SURFACE2};
                border-left: 4px solid {accent_color};
                border-bottom: 1px solid {Theme.SURFACE0};
            }}
            QFrame#{header.objectName()}:hover {{
                background-color: {Theme.OVERLAY0 if hasattr(Theme, 'OVERLAY0') else Theme.SURFACE2};
            }}
            QFrame#{header.objectName()} > * {{ border: none; }}
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 4, 12, 4)
        h_layout.setSpacing(8)

        arrow = QLabel("▼" if expanded else "▶")
        arrow.setFixedWidth(16)
        arrow.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 12px; border: none;")
        h_layout.addWidget(arrow)

        title_lbl = QLabel(f"{icon} {title}")
        title_lbl.setStyleSheet(f"color: {Theme.TEXT}; font-weight: bold; font-size: 12px; border: none;")
        h_layout.addWidget(title_lbl, stretch=1)

        count_lbl = QLabel(f"{item_count} items")
        count_lbl.setStyleSheet(f"color: {accent_color}; font-size: 11px; border: none;")
        h_layout.addWidget(count_lbl)

        container_layout.addWidget(header)

        # === CONTENT ===
        content_widget.setVisible(expanded)
        container_layout.addWidget(content_widget)

        # Store ref for toggle
        if not hasattr(self, '_pipeline_groups'):
            self._pipeline_groups = {}
        self._pipeline_groups[group_id] = {
            'arrow': arrow, 'content': content_widget, 'expanded': expanded,
        }

        # Click header → toggle
        def _on_header_click(event, _gid=group_id):
            self._toggle_pipeline_group(_gid)
        header.mousePressEvent = _on_header_click

        return container

    def _toggle_pipeline_group(self, group_id: str):
        """Toggle expand/collapse of a pipeline group."""
        grp = self._pipeline_groups.get(group_id)
        if not grp:
            return
        expanded = not grp['expanded']
        grp['expanded'] = expanded
        grp['content'].setVisible(expanded)
        grp['arrow'].setText("▼" if expanded else "▶")

    def _get_cached_frame(self, video_path: str) -> str:
        """Fix 6: Extract first frame with caching to avoid redundant FFmpeg calls.
        
        Returns cached frame path if available, otherwise extracts and caches.
        Eliminates ~200ms FFmpeg subprocess per video on repeated navigation.
        """
        import os
        _MAX_FRAME_CACHE = 100
        if not hasattr(self, '_frame_cache'):
            self._frame_cache = {}
        if video_path in self._frame_cache:
            cached = self._frame_cache[video_path]
            if cached and os.path.isfile(cached):
                return cached
        # Evict oldest entries when cache is full
        if len(self._frame_cache) >= _MAX_FRAME_CACHE:
            keys_to_remove = list(self._frame_cache.keys())[:20]
            for k in keys_to_remove:
                del self._frame_cache[k]
        # Extract and cache
        try:
            if not hasattr(self, '_frame_extractor'):
                from core.frame_extractor import FrameExtractor
                self._frame_extractor = FrameExtractor()
            if self._frame_extractor.is_available:
                frame = self._frame_extractor.extract_first_frame(video_path)
                self._frame_cache[video_path] = frame or ""
                return frame or ""
        except Exception:
            pass
        self._frame_cache[video_path] = ""
        return ""
    
    def _compute_thumb_fingerprint(self, stage_name: str) -> str:
        """Fix 7: Compute a lightweight fingerprint of thumbnail-relevant data.
        
        Used to skip full widget rebuild when navigating back to an
        already-rendered stage with unchanged data.
        """
        if not self._pipeline:
            return ""
        state = self._pipeline.state
        if stage_name == "scene_breakdown":
            n = len(state.scenes or [])
            return f"{stage_name}:s{n}"
        elif stage_name == "character_gen":
            chars = state.characters or []
            n_img = sum(1 for c in chars if c.image_path)
            return f"{stage_name}:{len(chars)}:{n_img}"
        elif stage_name == "scene_image_gen":
            scenes = state.scenes or []
            n_img = sum(1 for s in scenes if s.image_path)
            return f"{stage_name}:{len(scenes)}:{n_img}"
        elif stage_name == "video_gen":
            scenes = state.scenes or []
            n_vid = sum(1 for s in scenes if s.video_path)
            return f"{stage_name}:{len(scenes)}:{n_vid}"
        elif stage_name == "concat":
            scenes = state.scenes or []
            n_vid = sum(1 for s in scenes if s.video_path)
            has_final = 1 if state.final_video_path else 0
            return f"{stage_name}:{n_vid}:{has_final}"
        return f"{stage_name}:unknown"
    
    def _update_thumbnails(self, stage_name: str):
        """Update thumbnail gallery for visual stages (3-7).

        All stages use PipelinePromptTable wrapped in collapsible groups.
        """
        import os
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import QSize, Qt
        from ui.tabs.project_components.pipeline_prompt_table import (
            PipelinePromptTable, PipelinePromptItem,
        )

        visual_stages = {"scene_breakdown", "character_gen", "scene_image_gen", "video_gen", "concat"}
        list_stages   = {"scene_breakdown", "scene_image_gen", "video_gen", "concat"}

        if stage_name not in visual_stages:
            self._thumb_scroll.setVisible(False)
            # UI-2: Reset to small max without fixedHeight conflict
            self._thumb_scroll.setMinimumHeight(0)
            self._thumb_scroll.setMaximumHeight(100)
            return

        # ── Fix 7: Skip rebuild if same stage already rendered with same data ──
        new_fp = self._compute_thumb_fingerprint(stage_name)
        old_fp = getattr(self, '_thumb_data_fingerprint', None)
        old_stage = getattr(self, '_thumb_current_stage', None)
        if old_stage == stage_name and old_fp == new_fp and new_fp:
            # Already showing this exact data — just ensure visible + expandable
            self._thumb_scroll.setVisible(True)
            self._thumb_scroll.setMaximumHeight(16777215)
            return
        self._thumb_current_stage = stage_name
        self._thumb_data_fingerprint = new_fp

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
        self._thumb_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        # AN-5: Animated height transition
        self._animate_scroll_height(250, 16777215)

        # ── Stage 3: Scene Breakdown prompts (PipelinePromptTable) ──
        if stage_name == "scene_breakdown":
            state = self._pipeline.state if self._pipeline else None
            stage_obj = self._pipeline.state.get_stage("scene_breakdown") if state else None
            has_versions = state and state.is_multi_version() and state.versions
            has_episodes = state and state.is_multi_episode() and state.episodes

            if has_versions and any(v.scenes for v in state.versions):
                # Multi-version: one collapsible group per version
                for vi, v in enumerate(state.versions):
                    if not v.scenes:
                        continue
                    items = []
                    for s in v.scenes:
                        shot_type = s.description.split('.')[0] if s.description and '.' in s.description else "Scene"
                        items.append(PipelinePromptItem(
                            index=s.index,
                            name=f"🎬 Scene {s.index}\n{shot_type}",
                            prompt=s.prompt or s.description or "(empty)",
                            accent_color=Theme.PEACH,
                        ))
                    tbl = PipelinePromptTable(accent_color=Theme.PEACH, thumb_size=(1, 1))
                    tbl.table.setColumnHidden(1, True)
                    tbl.set_items(items)
                    grp = self._create_pipeline_group(
                        f"s3_v{vi}", f"{v.label}", "📌",
                        len(v.scenes), Theme.PEACH, tbl,
                    )
                    self._thumb_layout.addWidget(grp)
                self._pipeline_prompt_table = None
            elif has_episodes and any(ep.scenes for ep in state.episodes):
                # Multi-episode: one collapsible group per episode
                for ei, ep in enumerate(state.episodes):
                    if not ep.scenes:
                        continue
                    items = []
                    for s in ep.scenes:
                        shot_type = s.description.split('.')[0] if s.description and '.' in s.description else "Scene"
                        items.append(PipelinePromptItem(
                            index=s.index,
                            name=f"🎬 Scene {s.index}\n{shot_type}",
                            prompt=s.prompt or s.description or "(empty)",
                            accent_color=Theme.PEACH,
                        ))
                    tbl = PipelinePromptTable(accent_color=Theme.PEACH, thumb_size=(1, 1))
                    tbl.table.setColumnHidden(1, True)
                    tbl.set_items(items)
                    grp = self._create_pipeline_group(
                        f"s3_ep{ei}", f"{ep.label}", "📺",
                        len(ep.scenes), Theme.PEACH, tbl,
                    )
                    self._thumb_layout.addWidget(grp)
                self._pipeline_prompt_table = None
            else:
                # Single version: one flat table
                scenes = state.scenes if state else []
                raw_prompts = stage_obj.data.get("raw_prompts", "") if stage_obj and stage_obj.data else ""
                if not scenes and raw_prompts:
                    # Fallback: parse raw_prompts text into items
                    import re
                    blocks = re.split(r'\n---\s*Scene\s+(\d+)\s*---\n', raw_prompts)
                    items = []
                    if len(blocks) > 1:
                        for j in range(1, len(blocks), 2):
                            idx = int(blocks[j])
                            prompt = blocks[j + 1].strip() if j + 1 < len(blocks) else ""
                            items.append(PipelinePromptItem(
                                index=idx, name=f"🎬 Scene {idx}",
                                prompt=prompt, accent_color=Theme.PEACH,
                            ))
                    else:
                        # Single block — show as one item
                        items.append(PipelinePromptItem(
                            index=1, name="🎬 All Scenes",
                            prompt=raw_prompts.strip(), accent_color=Theme.PEACH,
                        ))
                    self._pipeline_prompt_table = PipelinePromptTable(
                        accent_color=Theme.PEACH, thumb_size=(1, 1),
                    )
                    self._pipeline_prompt_table.table.setColumnHidden(1, True)
                    self._pipeline_prompt_table.set_items(items)
                    grp = self._create_pipeline_group(
                        "s3_single", "Scene Prompts", "📝",
                        len(items), Theme.PEACH, self._pipeline_prompt_table,
                    )
                    self._thumb_layout.addWidget(grp)
                elif scenes:
                    items = []
                    for s in scenes:
                        shot_type = s.description.split('.')[0] if s.description and '.' in s.description else "Scene"
                        items.append(PipelinePromptItem(
                            index=s.index,
                            name=f"🎬 Scene {s.index}\n{shot_type}",
                            prompt=s.prompt or s.description or "(empty)",
                            accent_color=Theme.PEACH,
                        ))
                    self._pipeline_prompt_table = PipelinePromptTable(
                        accent_color=Theme.PEACH, thumb_size=(1, 1),
                    )
                    self._pipeline_prompt_table.table.setColumnHidden(1, True)
                    self._pipeline_prompt_table.set_items(items)
                    grp = self._create_pipeline_group(
                        "s3_scenes", "Scene Prompts", "📝",
                        len(items), Theme.PEACH, self._pipeline_prompt_table,
                    )
                    self._thumb_layout.addWidget(grp)
                else:
                    lbl = QLabel("⏳ Scene prompts will appear after Stage 3 completes")
                    lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                    self._thumb_layout.addWidget(lbl)

            self._fade_in_thumb_scroll()
            return

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

            state = self._pipeline.state
            has_versions = state.is_multi_version() and state.versions
            has_episodes = state.is_multi_episode() and state.episodes

            def _build_char_items(chars, char_prompts=None):
                items = []
                cp = char_prompts or []
                count = max(len(chars), len(cp))
                for i in range(count):
                    char = chars[i] if i < len(chars) else None
                    prompt = cp[i] if i < len(cp) else (char.prompt if char else "")
                    name = char.name if char else f"Character {i+1}"
                    thumb_path = (char.image_path if char and char.image_path and os.path.isfile(char.image_path) else "")
                    items.append(PipelinePromptItem(
                        index=i + 1, name=f"👤 {name}", prompt=prompt,
                        thumbnail_path=thumb_path, accent_color=Theme.BLUE,
                    ))
                return items

            if has_versions and any(v.characters for v in state.versions):
                # Multi-version: one group per version
                for vi, v in enumerate(state.versions):
                    if not v.characters:
                        continue
                    items = _build_char_items(v.characters)
                    tbl = PipelinePromptTable(accent_color=Theme.BLUE, thumb_size=thumb_sz)
                    tbl.set_items(items)
                    label = v.label or f"Version {v.index + 1}"
                    grp = self._create_pipeline_group(
                        f"s4_v{vi}", f"👤 {label}", "👤",
                        len(items), Theme.BLUE, tbl,
                    )
                    self._thumb_layout.addWidget(grp)
                self._pipeline_prompt_table = None
            elif has_episodes:
                # Multi-episode: characters are SHARED — show one group
                chars = state.shared_characters or state.characters or []
                if chars:
                    items = _build_char_items(chars)
                    self._pipeline_prompt_table = PipelinePromptTable(
                        accent_color=Theme.BLUE, thumb_size=thumb_sz,
                    )
                    self._pipeline_prompt_table.set_items(items)
                    grp = self._create_pipeline_group(
                        "s4_shared", "Shared Characters", "👤",
                        len(items), Theme.BLUE, self._pipeline_prompt_table,
                    )
                    self._thumb_layout.addWidget(grp)
                else:
                    lbl = QLabel("⏳ Character data will appear after Stage 4 completes")
                    lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                    self._thumb_layout.addWidget(lbl)
            else:
                # Single project
                stage_obj = state.get_stage("character_gen")
                characters = state.characters or []
                char_prompts = stage_obj.prompts or []
                if not characters and not char_prompts:
                    lbl = QLabel("⏳ Character data will appear after Stage 4 completes")
                    lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                    self._thumb_layout.addWidget(lbl)
                else:
                    items = _build_char_items(characters, char_prompts)
                    self._pipeline_prompt_table = PipelinePromptTable(
                        accent_color=Theme.BLUE, thumb_size=thumb_sz,
                    )
                    self._pipeline_prompt_table.set_items(items)
                    grp = self._create_pipeline_group(
                        "s4_chars", "Character Prompts", "👤",
                        len(items), Theme.BLUE, self._pipeline_prompt_table,
                    )
                    self._thumb_layout.addWidget(grp)

            # ── Stage 4b: Background prompts (if any) ──
            backgrounds = getattr(state, 'backgrounds', []) or []
            if backgrounds:
                bg_items = []
                for bi, bg in enumerate(backgrounds):
                    bg_name = getattr(bg, 'name', None) or getattr(bg, 'tag', None) or f"Background {bi+1}"
                    bg_prompt = getattr(bg, 'prompt', '') or ''
                    bg_img = getattr(bg, 'image_path', '') or ''
                    bg_thumb = bg_img if (bg_img and os.path.isfile(bg_img)) else ""
                    bg_items.append(PipelinePromptItem(
                        index=bi + 1, name=f"🏞️ {bg_name}", prompt=bg_prompt,
                        thumbnail_path=bg_thumb, accent_color=Theme.GREEN,
                    ))
                if bg_items:
                    bg_tbl = PipelinePromptTable(accent_color=Theme.GREEN, thumb_size=thumb_sz)
                    bg_tbl.set_items(bg_items)
                    bg_grp = self._create_pipeline_group(
                        "s4_bgs", "Background Prompts", "🏞️",
                        len(bg_items), Theme.GREEN, bg_tbl,
                    )
                    self._thumb_layout.addWidget(bg_grp)

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

            state = self._pipeline.state
            has_versions = state.is_multi_version() and state.versions
            has_episodes = state.is_multi_episode() and state.episodes

            def _build_scene_img_items(scenes):
                items = []
                for s in scenes:
                    has_image = s.image_path and os.path.isfile(s.image_path)
                    thumb_path = s.image_path if has_image else ""
                    status_icon = "✅" if has_image else "⏳"
                    items.append(PipelinePromptItem(
                        index=s.index,
                        name=f"{status_icon} Scene {s.index}",
                        prompt=s.prompt or s.description or "(empty)",
                        thumbnail_path=thumb_path,
                        accent_color=Theme.GREEN,
                    ))
                return items

            if has_versions and any(v.scenes for v in state.versions):
                for vi, v in enumerate(state.versions):
                    if not v.scenes:
                        continue
                    items = _build_scene_img_items(v.scenes)
                    tbl = PipelinePromptTable(accent_color=Theme.GREEN, thumb_size=thumb_sz)
                    tbl.set_items(items)
                    label = v.label or f"Version {v.index + 1}"
                    grp = self._create_pipeline_group(
                        f"s5_v{vi}", f"🖼️ {label}", "🖼️",
                        len(items), Theme.GREEN, tbl,
                    )
                    self._thumb_layout.addWidget(grp)
                self._pipeline_prompt_table = None
            elif has_episodes and any(ep.scenes for ep in state.episodes):
                for ei, ep in enumerate(state.episodes):
                    if not ep.scenes:
                        continue
                    items = _build_scene_img_items(ep.scenes)
                    tbl = PipelinePromptTable(accent_color=Theme.GREEN, thumb_size=thumb_sz)
                    tbl.set_items(items)
                    label = ep.label or f"Tập {ep.index + 1}"
                    grp = self._create_pipeline_group(
                        f"s5_ep{ei}", f"🖼️ {label}", "🖼️",
                        len(items), Theme.GREEN, tbl,
                    )
                    self._thumb_layout.addWidget(grp)
                self._pipeline_prompt_table = None
            else:
                # Single project — use stage_obj data or scenes
                stage_obj = state.get_stage("scene_image_gen")
                scene_configs = []
                if stage_obj.data and isinstance(stage_obj.data, dict):
                    scene_configs = stage_obj.data.get("scene_configs", [])
                scenes = state.scenes or []

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
                    grp = self._create_pipeline_group(
                        "s5_images", "Scene Images", "🖼️",
                        len(items), Theme.GREEN, self._pipeline_prompt_table,
                    )
                    self._thumb_layout.addWidget(grp)

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

            state = self._pipeline.state
            has_versions = state.is_multi_version() and state.versions
            has_episodes = state.is_multi_episode() and state.episodes

            def _build_video_items(scenes):
                items = []
                for idx, s in enumerate(scenes):
                    has_video = s.video_path and os.path.isfile(s.video_path)
                    # Start frame: scene own image
                    thumb_path = s.image_path if (s.image_path and os.path.isfile(s.image_path)) else ""
                    # End frame: next scene image (for First+Last frame dual-I2V)
                    next_s = scenes[idx + 1] if idx + 1 < len(scenes) else None
                    end_frame = (
                        next_s.image_path
                        if next_s and next_s.image_path and os.path.isfile(next_s.image_path)
                        else ""
                    )
                    # Video preview from generated video
                    vid_thumb_path = ""
                    actual_video_path = ""
                    if has_video:
                        actual_video_path = s.video_path
                        vid_thumb_path = self._get_cached_frame(s.video_path)
                        if not vid_thumb_path:
                            vid_thumb_path = s.video_path
                    status_icon = "✅" if has_video else "⏳"
                    end_label = f" → S{next_s.index}" if next_s else " (last)"
                    items.append(PipelinePromptItem(
                        index=s.index,
                        name=f"{status_icon} Scene {s.index}{end_label}",
                        prompt=s.prompt or s.description or "(empty)",
                        thumbnail_path=thumb_path,
                        video_thumbnail_path=vid_thumb_path,
                        end_frame_path=end_frame,
                        accent_color=Theme.PEACH,
                        metadata={"video_path": actual_video_path},
                    ))
                return items

            if has_versions and any(v.scenes for v in state.versions):
                for vi, v in enumerate(state.versions):
                    if not v.scenes:
                        continue
                    items = _build_video_items(v.scenes)
                    tbl = PipelinePromptTable(
                        accent_color=Theme.PEACH, thumb_size=thumb_sz,
                        show_video_preview=True,
                    )
                    tbl.set_items(items)
                    label = v.label or f"Version {v.index + 1}"
                    grp = self._create_pipeline_group(
                        f"s6_v{vi}", f"📹 {label}", "📹",
                        len(items), Theme.PEACH, tbl,
                    )
                    self._thumb_layout.addWidget(grp)
                self._pipeline_prompt_table = None
            elif has_episodes and any(ep.scenes for ep in state.episodes):
                for ei, ep in enumerate(state.episodes):
                    if not ep.scenes:
                        continue
                    items = _build_video_items(ep.scenes)
                    tbl = PipelinePromptTable(
                        accent_color=Theme.PEACH, thumb_size=thumb_sz,
                        show_video_preview=True,
                    )
                    tbl.set_items(items)
                    label = ep.label or f"Tập {ep.index + 1}"
                    grp = self._create_pipeline_group(
                        f"s6_ep{ei}", f"📹 {label}", "📹",
                        len(items), Theme.PEACH, tbl,
                    )
                    self._thumb_layout.addWidget(grp)
                self._pipeline_prompt_table = None
            else:
                # Single project — use stage_obj data
                stage_obj = state.get_stage("video_gen")
                video_configs = []
                if stage_obj.data and isinstance(stage_obj.data, dict):
                    video_configs = stage_obj.data.get("video_configs", [])
                scenes = state.scenes or []

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
                        # Image Preview: always show source image
                        thumb_path = img_path if (img_path and os.path.isfile(img_path)) else ""
                        # Video Preview: show frame from generated video
                        vid_thumb_path = ""
                        actual_video_path = ""
                        if has_video:
                            actual_video_path = scene.video_path
                            vid_thumb_path = self._get_cached_frame(scene.video_path)
                            if not vid_thumb_path:
                                vid_thumb_path = scene.video_path  # fallback
                        mode_icon = "🎬" if mode == "I2V" else ("📐" if mode == "R2V" else "📹")
                        status_icon = "✅" if has_video else "⏳"
                        duration = vc.get("duration_s", 8)
                        items.append(PipelinePromptItem(
                            index=idx,
                            name=f"{status_icon} {scene_tag}\n{mode_icon} {mode} • {duration}s",
                            prompt=prompt, thumbnail_path=thumb_path,
                            video_thumbnail_path=vid_thumb_path,
                            accent_color=Theme.PEACH,
                            metadata={"video_path": actual_video_path},
                        ))
                    self._pipeline_prompt_table = PipelinePromptTable(
                        accent_color=Theme.PEACH, thumb_size=thumb_sz,
                        show_video_preview=True,
                    )
                    self._pipeline_prompt_table.set_items(items)
                    grp = self._create_pipeline_group(
                        "s6_videos", "Video Prompts", "📹",
                        len(items), Theme.PEACH, self._pipeline_prompt_table,
                    )
                    self._thumb_layout.addWidget(grp)

            # AN-1: Fade-in scroll
            self._fade_in_thumb_scroll()
            return

        # ── Stage 7 (concat): Final concatenated videos only ──
        if stage_name == "concat":
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            vid_aspect = config.get("video_aspect", "LANDSCAPE")
            if vid_aspect == "PORTRAIT":
                thumb_sz = (60, 107)
            else:
                thumb_sz = (107, 60)

            state = self._pipeline.state
            project_name = (state.topic or "Project").strip().split("\n")[0][:60]

            # Collect final videos based on project type
            final_videos = []  # [(index, label, video_path)]

            # ★ Diagnostic: log which branch will be taken
            log.info(
                f"[Pipeline] Stage 7 display: multi_ver={state.is_multi_version()} "
                f"(video_count={state.video_count}, versions={len(state.versions)}), "
                f"multi_ep={state.is_multi_episode()} "
                f"(ep_enabled={state.episode_enabled}, ep_count={state.episode_count}), "
                f"final_video_path='{state.final_video_path}'"
            )

            if state.is_multi_version() and state.versions:
                # Multi-version: each version has its own final video
                for v in state.versions:
                    vp = v.final_video_path
                    if vp and os.path.isfile(vp):
                        label = v.label or f"Version {v.index + 1}"
                        final_videos.append((v.index + 1, f"{project_name} — {label}", vp))
            elif state.is_multi_episode() and state.episodes:
                # Multi-episode: each episode has its own final video
                for ep in state.episodes:
                    vp = ep.final_video_path
                    if vp and os.path.isfile(vp):
                        label = ep.label or f"Tập {ep.index + 1}"
                        final_videos.append((ep.index + 1, f"{project_name} — {label}", vp))
            else:
                # Single project: one final video
                vp = state.final_video_path
                if vp and os.path.isfile(vp):
                    final_videos.append((1, project_name, vp))

            # ★ Universal fallback: if no videos found from any branch,
            # try stage.data['final_output'] as last resort
            if not final_videos:
                concat_stage = state.get_stage("concat")
                fallback_vp = (concat_stage.data or {}).get("final_output", "")
                if fallback_vp and os.path.isfile(fallback_vp):
                    state.final_video_path = fallback_vp
                    final_videos.append((1, project_name, fallback_vp))
                    log.info(f"[Pipeline] Stage 7 display: ✅ recovered from stage.data → {fallback_vp}")
                else:
                    log.warning(
                        f"[Pipeline] Stage 7 display: ❌ no final video found. "
                        f"fallback_vp='{fallback_vp}', "
                        f"exists={os.path.isfile(fallback_vp) if fallback_vp else False}"
                    )

            if not final_videos:
                lbl = QLabel("⏳ Video thành phẩm sẽ hiển thị sau khi Stage 7 hoàn tất")
                lbl.setStyleSheet(f"color: {Theme.SUBTEXT0}; font-size: 11px; padding: 20px;")
                self._thumb_layout.addWidget(lbl)
            else:
                items = []
                for idx, name, path in final_videos:
                    # Thumbnail from video frame
                    thumb_path = self._get_cached_frame(path)

                    # File info
                    try:
                        size_mb = os.path.getsize(path) / (1024 * 1024)
                        file_info = f"📁 {os.path.basename(path)}\n💾 {size_mb:.1f} MB"
                    except Exception:
                        file_info = f"📁 {os.path.basename(path)}"

                    items.append(PipelinePromptItem(
                        index=idx,
                        name=f"🏁 {name}",
                        prompt=file_info,
                        thumbnail_path=thumb_path,
                        accent_color=Theme.GREEN,
                        metadata={"video_path": path},
                    ))
                self._pipeline_prompt_table = PipelinePromptTable(
                    accent_color=Theme.GREEN, thumb_size=thumb_sz,
                )
                self._pipeline_prompt_table.set_items(items)
                total_label = f"Final Output ({len(items)} video{'s' if len(items) > 1 else ''})"
                grp = self._create_pipeline_group(
                    "s7_output", total_label, "🏁",
                    len(items), Theme.GREEN, self._pipeline_prompt_table,
                )
                self._thumb_layout.addWidget(grp)

            # AN-1: Fade-in scroll
            self._fade_in_thumb_scroll()
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
            self._generate_btn.setText("▶️​ Start")
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

    # ── Centralized Button State ──────────────────────────────────

    def _sync_buttons(self, mode: str, stage_name: str = ""):
        """Single source of truth for all button states.
        
        Modes: idle, running, done, error, review, complete
        """
        self._viewing_mode = mode
        if mode == "idle":
            self._stage_run_btn.setText("▶️ Start")
            self._stage_run_btn.setEnabled(True)
            self._stage_confirm_btn.setEnabled(False)
        elif mode == "running":
            self._stage_run_btn.setText(f"⏳ Running: {stage_name}...")
            self._stage_run_btn.setEnabled(False)
            self._stage_confirm_btn.setEnabled(False)
        elif mode == "done":
            self._stage_run_btn.setText("▶️ Start")
            self._stage_run_btn.setEnabled(True)
            self._stage_confirm_btn.setEnabled(True)
        elif mode == "error":
            self._stage_run_btn.setText("🔄 Retry")
            self._stage_run_btn.setEnabled(True)
            self._stage_confirm_btn.setEnabled(False)
        elif mode == "review":
            self._stage_run_btn.setText("🔄 Re-run")
            self._stage_run_btn.setEnabled(True)
            has_data = bool(
                self._pipeline.state.get_stage(stage_name).data
            ) if self._pipeline and stage_name else False
            self._stage_confirm_btn.setEnabled(has_data)
        elif mode == "complete":
            self._stage_run_btn.setText("🔄 Re-run")
            self._stage_run_btn.setEnabled(True)
            self._stage_confirm_btn.setEnabled(False)

    # ── Run / Re-run / Retry ─────────────────────────────────────

    def _on_stage_run_clicked(self):
        """Handle run button click — uses _viewing_mode to detect re-run."""
        from core.production_pipeline import StageStatus
        current = self._pipeline_current_stage or ""
        
        # ★ Re-run / Retry mode (detected via _viewing_mode, NOT button text)
        if self._viewing_mode in ("review", "complete", "error") and current and self._pipeline:
            stage_result = self._pipeline.state.get_stage(current)
            if stage_result.status in (StageStatus.CONFIRMED, StageStatus.WAITING_CONFIRM,
                                       StageStatus.ERROR, StageStatus.SKIPPED):
                stage_result.status = StageStatus.PENDING
                stage_result.error = ""
                # Reset ALL downstream stages
                from core.production_pipeline import STAGE_ORDER
                idx = STAGE_ORDER.index(current) if current in STAGE_ORDER else -1
                if idx >= 0 and idx < len(STAGE_ORDER) - 1:
                    next_downstream = STAGE_ORDER[idx + 1]
                    self._pipeline.reset_from_stage(next_downstream)
                    log.info(f"[Pipeline] Re-run: reset '{current}' + downstream from '{next_downstream}' → all PENDING")
                else:
                    log.info(f"[Pipeline] Re-run: reset '{current}' → PENDING, forcing re-run")
                self._run_pipeline_stage(force_stage=current)
                return
        
        # Normal mode: run next stage in pipeline order
        self._run_pipeline_stage()

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
                self._set_viewer_text(
                    f"🎬 Batch mode: {len(all_topics)} topics\n"
                    f"Starting topic 1/{len(all_topics)}: {all_topics[0][:60]}..."
                )

        # Find next stage (or use forced stage for retry/back)
        next_stage = force_stage or self._pipeline.get_next_stage()
        if not next_stage:
            self._set_viewer_text("✅ Pipeline complete! All stages done.")
            # ★ FIX: Re-enable buttons so user can navigate back and re-run stages
            self._sync_buttons("complete")
            return

        self._pipeline_current_stage = next_stage

        # Fix 4: Reset dot to yellow (running) — covers retry after red error
        self._stage_dots[next_stage].setStyleSheet(
            f"QPushButton {{ background-color: {Theme.YELLOW}; color: black; "
            f"border: 1px solid {Theme.YELLOW}; border-radius: 3px; "
            f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
        )

        self._sync_buttons("running", next_stage)
        
        # ★ Set pipeline mode active — defers AutoStop during stage transitions
        if self.controller and hasattr(self.controller, 'set_pipeline_mode_active'):
            self.controller.set_pipeline_mode_active(True)

        # Get config from sidebar — sidebar values always take priority
        config = self._setup_matrix.get_config() if self._setup_matrix else {}
        config["topic"] = self._pipeline.state.topic
        # ★ Pass cached project_name so _stage_concat can find the right folder
        config["project_name"] = self._get_sanitized_project_name(config)

        # Run async stage in background thread
        # ★ SAFE cleanup: Never call terminate() — it kills the process!
        # Instead, detach old thread (let it finish naturally) and start a new one.
        # Old thread's done signal is silently ignored via _generation_id guard.
        if hasattr(self, '_stage_thread') and self._stage_thread is not None:
            old_thread = self._stage_thread
            if old_thread.isRunning():
                log.warning(
                    f"[Pipeline] ⚠️ Previous stage thread still running — "
                    f"detaching (will finish in background, result discarded)"
                )
                # Disconnect signals to prevent old thread from updating UI
                try:
                    old_thread.started.disconnect()
                except (RuntimeError, TypeError):
                    pass
                # ★ FIX: Keep strong reference so GC doesn't destroy running thread
                if not hasattr(self, '_detached_threads'):
                    self._detached_threads = []
                self._detached_threads.append(old_thread)
                # Auto-cleanup: remove from list + deleteLater when finished
                def _on_detached_done(thread_ref=old_thread):
                    log.info("[Pipeline] 🧵 Detached old thread finished (result discarded)")
                    try:
                        if hasattr(self, '_detached_threads') and thread_ref in self._detached_threads:
                            self._detached_threads.remove(thread_ref)
                    except (ValueError, RuntimeError):
                        pass
                    thread_ref.deleteLater()
                old_thread.finished.connect(_on_detached_done)
            else:
                log.debug(f"[Pipeline] Previous thread already finished (state: {old_thread.isFinished()})")
        
        # Increment generation ID — stale done signals (from detached threads) are ignored
        if not hasattr(self, '_generation_id'):
            self._generation_id = 0
        self._generation_id += 1
        current_gen = self._generation_id
        
        log.info(f"[Pipeline] 🧵 Creating new QThread for stage '{next_stage}' (gen={current_gen})")
        self._stage_thread = QThread()
        self._stage_worker_obj = _StageWorker(self._pipeline, next_stage, config)
        self._stage_worker_obj.moveToThread(self._stage_thread)
        self._stage_thread.started.connect(self._stage_worker_obj.run)
        # Guard: only process done signal if generation_id matches (not from detached old thread)
        # ★ THREADING FIX: Use QueuedConnection so _on_stage_done runs on GUI thread.
        # Lambda forces DirectConnection → UI widgets created on worker thread → crash.
        self._stage_worker_obj._gen_id = current_gen  # tag worker with generation ID
        self._stage_worker_obj.done.connect(
            self._on_stage_done_dispatch, Qt.ConnectionType.QueuedConnection
        )
        self._stage_worker_obj.done.connect(self._stage_thread.quit)
        # ★ prevent GC of finished thread — deleteLater cleans up safely
        self._stage_thread.finished.connect(
            lambda: log.info(f"[Pipeline] 🧵 QThread for '{next_stage}' finished")
        )
        self._stage_thread.start()

    def _set_viewer_text(self, text: str, *, reset_scroll: bool = False):
        """Set stage viewer text while preserving scroll position.
        
        Args:
            text: Content to display
            reset_scroll: If True, scroll to top (used for new stage results)
        """
        if reset_scroll:
            self._stage_viewer.setPlainText(text)
            self._stage_viewer.verticalScrollBar().setValue(0)
        else:
            vbar = self._stage_viewer.verticalScrollBar()
            pos = vbar.value()
            self._stage_viewer.setPlainText(text)
            # Restore — clamp to new max in case content is shorter
            vbar.setValue(min(pos, vbar.maximum()))

    def _on_stage_done_dispatch(self, stage_name: str, result_text: str, error: str):
        """Thread-safe dispatch slot for stage worker done signal.
        
        Connected via Qt.QueuedConnection so this always runs on GUI thread.
        Checks generation-ID staleness before forwarding to _on_stage_done.
        """
        # Retrieve generation ID tagged on the worker
        worker_gen = getattr(self._stage_worker_obj, '_gen_id', -1) if hasattr(self, '_stage_worker_obj') else -1
        current_gen = getattr(self, '_generation_id', -1)
        if worker_gen != current_gen:
            log.info(f"[Pipeline] 🗑️ Stale result from gen={worker_gen} discarded (current={current_gen})")
            return
        self._on_stage_done(stage_name, result_text, error)

    def _on_stage_done(self, stage_name: str, result_text: str, error: str):
        """Handle stage completion — show result for user review."""
        from core.production_pipeline import STAGE_ORDER
        if error:
            self._sync_buttons("error")
            # Ensure viewer is visible for error messages (card stages hide it)
            self._stage_viewer.setMinimumHeight(120)
            self._stage_viewer.setMaximumHeight(16777215)
            self._stage_viewer.setVisible(True)
            self._thumb_scroll.setVisible(False)
            self._set_viewer_text(f"❌ Stage '{stage_name}' error:\n\n{error}")
            self._stage_dots[stage_name].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.RED}; color: black; "
                f"border-radius: 3px; font-size: 10px; padding: 2px 6px; }}"
            )
            self._queue_awaiting_completion = False
        else:
            self._sync_buttons("done")
            
            # Stages 4-7: hide text viewer, show only vertical list/cards
            card_stages = {"scene_breakdown", "character_gen", "scene_image_gen", "video_gen", "concat"}
            if stage_name in card_stages:
                self._stage_viewer.setMaximumHeight(0)
                self._stage_viewer.setVisible(False)
            else:
                self._stage_viewer.setMinimumHeight(120)
                self._stage_viewer.setMaximumHeight(16777215)
                self._stage_viewer.setVisible(True)
                self._set_viewer_text(result_text)
            
            # confirm btn already enabled by _sync_buttons("done")
            # AN-4: Flash dot 2x on completion instead of instant color change
            self._stage_dots[stage_name].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.GREEN}; color: black; "
                f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )
            self._flash_dot(stage_name)
            self._update_nav_buttons(stage_name)
            self._update_thumbnails(stage_name)
            
            # Auto-confirm: auto-advance for ALL stages (including concat)
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            if config.get("auto_confirm", False):
                from PySide6.QtCore import QTimer
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
            
            # 2. Fallback: extract title from Stage 2 Bible text (bible_gen)
            if not name:
                try:
                    stage2 = self._pipeline.state.get_stage("bible_gen")
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
            
            # 3. Fallback: raw topic (extract meaningful part even from conversational junk)
            if not name:
                raw_topic = getattr(self._pipeline.state, 'topic', '') or ''
                if raw_topic:
                    # Multi-line topics: take first non-empty line as candidate
                    first_line = raw_topic.strip()
                    for line in raw_topic.split('\n'):
                        line = line.strip()
                        if line and len(line) >= 3:
                            first_line = line
                            break
                    
                    # Detect conversational junk on first line only
                    junk_prefixes = ('tuyệt', 'ok', 'được', 'vâng', 'hay', 'tốt', 'ừ', 'ờ')
                    is_junk = (
                        len(first_line) > 50
                        or '—' in first_line
                        or first_line.lower().startswith(junk_prefixes)
                        or first_line.count(' ') > 8
                    )
                    if not is_junk:
                        name = first_line
                        ai_source = "raw_topic"
                    else:
                        # Extract meaningful words from first line
                        clean = first_line
                        # Remove interjection prefix
                        for prefix in junk_prefixes:
                            if clean.lower().startswith(prefix):
                                clean = clean[len(prefix):].lstrip(' ,!.—-–')
                                break
                        # Remove em dash and everything before it
                        if '—' in clean:
                            clean = clean.split('—')[-1].strip()
                        if '–' in clean:
                            clean = clean.split('–')[-1].strip()
                        # Take first 5 words
                        words = clean.split()[:5]
                        if words:
                            name = ' '.join(words)
                            ai_source = "raw_topic_cleaned"
                            log.info(f"[Pipeline] Cleaned junk topic: '{first_line[:60]}' → '{name}'")
            
            # 3b. Fallback: first character name from pipeline state
            if not name:
                chars = getattr(self._pipeline.state, 'characters', []) or []
                if chars and chars[0].name:
                    name = chars[0].name
                    ai_source = "character_name"
            
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
        
        # Final fallback: timestamped name (never use generic "Production")
        if not name:
            from datetime import datetime as _dt
            name = config.get("project_name", "") or f"Project_{_dt.now().strftime('%Y%m%d_%H%M')}"
        
        # Cache for subsequent stages in this pipeline run
        self._pipeline_project_name = name
        log.info(f"[Pipeline] Project name: '{name}' (source={ai_source or 'config'})")
        
        return name

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

    def _ensure_pipeline_scenes_linked(self):
        """Defensive: re-link state.scenes to the active version/episode.
        
        After session restore, state.scenes may be a stale copy disconnected
        from version.scenes. This method ensures they share the same reference,
        preventing stages 5/6/7 from seeing empty image_path/video_path.
        """
        if not self._pipeline:
            return
        state = self._pipeline.state
        if state.versions and state.current_version_idx < len(state.versions):
            v = state.versions[state.current_version_idx]
            if state.scenes is not v.scenes:
                log.warning(
                    f"[Pipeline] ★ scenes reference mismatch detected! "
                    f"Re-linking state.scenes → version[{state.current_version_idx}].scenes "
                    f"({len(v.scenes)} scenes, {sum(1 for s in v.scenes if s.video_path)} with video)"
                )
                state.scenes = v.scenes
        elif state.episodes and state.current_episode_idx < len(state.episodes):
            ep = state.episodes[state.current_episode_idx]
            if state.scenes is not ep.scenes:
                log.warning(
                    f"[Pipeline] ★ scenes reference mismatch detected! "
                    f"Re-linking state.scenes → episode[{state.current_episode_idx}].scenes"
                )
                state.scenes = ep.scenes
    
    def _on_stage_confirm(self):
        """User confirms current stage result — parse edits, save to disk, advance."""
        if not self._pipeline or not self._pipeline_current_stage:
            return
        
        # ★ Guard: block re-confirm of already-confirmed stages
        from core.production_pipeline import StageStatus
        stage_obj = self._pipeline.state.get_stage(self._pipeline_current_stage)
        if stage_obj.status == StageStatus.CONFIRMED:
            log.info(f"[Pipeline] Stage '{self._pipeline_current_stage}' already confirmed, skipping")
            return
        
        # ★ Defensive: ensure state.scenes is linked to active version/episode
        self._ensure_pipeline_scenes_linked()
        
        # ★ Reset queue flag — manual confirm supersedes any pending queue state.
        # Without this, stale _queue_awaiting_completion=True from prior stages
        # blocks auto-advance (e.g. Stage 6 → Stage 7 concat never runs).
        self._queue_awaiting_completion = False
        # ★ Track whether queue was actually submitted for this stage.
        # Used at advance gate to prevent bypass for queue-dependent stages.
        self._queue_submitted_for_stage = False
        
        # Fix 1: Parse edited JSON correctly
        edited_data = self._parse_edited_stage_data()
        self._pipeline.confirm_stage(self._pipeline_current_stage, edited_data)
        self._stage_confirm_btn.setEnabled(False)
        
        # ── Save stage output to disk (async to avoid blocking GUI) ──
        self._save_stage_to_disk(self._pipeline_current_stage)
        # Session save is already called inside _save_stage_to_disk
        # (via _save_session_to_disk_async for non-blocking I/O)
        
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
        import os  # Needed for os.path.isfile in multiple branches below
        
        if cur == "character_gen" and self.controller:
            # ── Smart routing: check if character images already exist ──
            characters = self._pipeline.state.characters or []
            chars_with_images = [c for c in characters if c.image_path and os.path.isfile(c.image_path)]
            backgrounds = getattr(self._pipeline.state, 'backgrounds', []) or []
            bgs_with_images = [bg for bg in backgrounds if bg.image_path and os.path.isfile(bg.image_path)]
            
            all_chars_done = characters and len(chars_with_images) == len(characters)
            all_bgs_done = (not backgrounds) or (len(bgs_with_images) == len(backgrounds))
            
            if all_chars_done and all_bgs_done:
                # All characters AND backgrounds have image files → skip queue, advance
                log.info(
                    f"[Pipeline] Stage 4: All {len(characters)} characters + "
                    f"{len(backgrounds)} backgrounds have images. "
                    f"Skipping queue → advancing to next stage."
                )
                # Don't set _queue_awaiting_completion — let auto-advance proceed below
                self._queue_submitted_for_stage = True  # Legitimate skip — all files exist
            else:
                if chars_with_images:
                    log.info(
                        f"[Pipeline] Stage 4: {len(chars_with_images)}/{len(characters)} "
                        f"characters have images. Sending missing prompts to queue."
                    )
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
                        "aspect_ratio": "LANDSCAPE",  # 16:9 — character turnaround sheet needs horizontal layout (4 views)
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
                        
                        # ── Stage 4b: Background T2I prompts ──
                        bg_prompts = stage_obj.data.get("background_prompts", [])
                        if bg_prompts:
                            bg_settings = {
                                "model": config.get("image_model", "GEM_PIX_2"),
                                "aspect_ratio": "LANDSCAPE",
                                "download_quality": config.get("image_quality", "2k"),
                                "outputs_per_prompt": 1,
                                "output_folder": config.get("output_folder", ""),
                                "project_name": f"{project_name}/backgrounds",
                            }
                            bg_group_id = self.controller.add_t2i_batch(
                                prompts=bg_prompts, settings=bg_settings
                            )
                            log.info(
                                f"[Pipeline] Stage 4b: Sent {len(bg_prompts)} BG prompts "
                                f"to queue (group={bg_group_id})"
                            )
                            if bg_group_id:
                                self._start_queue_polling(bg_group_id, "character_gen")
                        else:
                            log.info("[Pipeline] Stage 4b: No background prompts to dispatch")
                    else:
                        log.warning("[Pipeline] Stage 4: controller has no add_t2i_batch method!")
                else:
                    log.warning("[Pipeline] Stage 4: No character prompts available to send!")
        elif cur == "scene_image_gen" and self.controller:
            state = self._pipeline.state
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            project_name = self._get_sanitized_project_name(config)
            
            # ── Multi-Version: create one group per version ──
            if state.is_multi_version() and state.versions and len(state.versions) > 1:
                # Check if ALL versions' scenes have images already
                all_have_images = True
                for v in state.versions:
                    v_scenes = v.scenes or []
                    missing = [s for s in v_scenes if not (s.image_path and os.path.isfile(s.image_path))]
                    if missing:
                        all_have_images = False
                        break
                
                if all_have_images:
                    log.info(f"[Pipeline] Stage 5: All {len(state.versions)} versions have scene images → skipping queue")
                    self._queue_submitted_for_stage = True  # Legitimate skip — all files exist
                else:
                    group_version_map = {}  # {group_id: version_idx}
                    saved_vi = state.current_version_idx  # Save active version
                    
                    for vi, version in enumerate(state.versions):
                        state.activate_version(vi)
                        v_scenes = state.scenes or []
                        if not v_scenes:
                            log.warning(f"[Pipeline] Stage 5: {version.label} has no scenes → skipping")
                            continue
                        
                        # Check which scenes still need images
                        need_images = [s for s in v_scenes if not (s.image_path and os.path.isfile(s.image_path))]
                        if not need_images:
                            log.info(f"[Pipeline] Stage 5: {version.label} — all {len(v_scenes)} scenes have images → skip")
                            continue
                        
                        # Build prompts from stage data for this version
                        prompts = [s.prompt or s.description or f"Scene {s.index}" for s in v_scenes if s.prompt or s.description]
                        # ★ VEO accepts full JSON as prompt — no unwrapping needed
                        if not prompts:
                            continue
                        
                        v_settings = {
                            "model": config.get("image_model", "GEM_PIX_2"),
                            "aspect_ratio": config.get("image_aspect", config.get("video_aspect", "LANDSCAPE")),
                            "download_quality": config.get("image_quality", "2k"),
                            "outputs_per_prompt": config.get("image_outputs", 1),
                            "output_folder": config.get("output_folder", ""),
                            "project_name": f"{project_name}/scenes/{version.label}",
                        }
                        
                        # Character ref images (shared across versions)
                        ref_images = []
                        for c in (state.characters or []):
                            if c.image_path and os.path.isfile(c.image_path):
                                ref_images.append(c.image_path)
                        if ref_images:
                            v_settings["reference_images"] = ref_images
                        
                        if hasattr(self.controller, "add_t2i_batch"):
                            group_id = self.controller.add_t2i_batch(prompts=prompts, settings=v_settings)
                            if group_id:
                                group_version_map[group_id] = vi
                                log.info(
                                    f"[Pipeline] Stage 5: {version.label} → "
                                    f"{len(prompts)} prompts → group={group_id}"
                                )
                    
                    # Restore original active version
                    state.activate_version(saved_vi)
                    
                    if group_version_map:
                        self._start_multi_group_polling(group_version_map, "scene_image_gen")
                        # ★ Wait for library pre-upload before engine starts
                        if hasattr(self.controller, 'flush_pending_pre_upload'):
                            self.controller.flush_pending_pre_upload(
                                on_done=self._trigger_queue_auto_start
                            )
                        else:
                            self._trigger_queue_auto_start()
                        log.info(
                            f"[Pipeline] Stage 5: Created {len(group_version_map)} version groups "
                            f"for parallel scene image generation"
                        )
            else:
                # ── Single version (original logic) ──
                scenes = state.scenes or []
                scenes_with_images = [s for s in scenes if s.image_path and os.path.isfile(s.image_path)]
                if scenes and len(scenes_with_images) == len(scenes):
                    log.info(
                        f"[Pipeline] Stage 5: All {len(scenes)} scenes have images. "
                        f"Skipping queue → advancing to next stage."
                    )
                    self._queue_submitted_for_stage = True  # Legitimate skip — all files exist
                else:
                    if scenes_with_images:
                        log.info(
                            f"[Pipeline] Stage 5: {len(scenes_with_images)}/{len(scenes)} "
                            f"scenes have images. Sending missing prompts to queue."
                        )
                    stage_obj = state.get_stage("scene_image_gen")
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
                    # ★ VEO accepts full JSON as prompt — no unwrapping needed
                    log.info(f"[Pipeline] Stage 5 prompts: {len(prompts)} from scene_configs (sanitized)")
                    if prompts:
                        settings = {
                            "model": config.get("image_model", "GEM_PIX_2"),
                            "aspect_ratio": config.get("image_aspect", config.get("video_aspect", "LANDSCAPE")),
                            "download_quality": config.get("image_quality", "2k"),
                            "outputs_per_prompt": config.get("image_outputs", 1),
                            "output_folder": config.get("output_folder", ""),
                            "project_name": f"{project_name}/scenes",
                        }
                        # Build per-prompt image map from scene_configs (per-scene matching)
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
                            ref_images = []
                            for c in (state.characters or []):
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
                                # ★ Wait for library pre-upload before engine starts
                                if hasattr(self.controller, 'flush_pending_pre_upload'):
                                    self.controller.flush_pending_pre_upload(
                                        on_done=self._trigger_queue_auto_start
                                    )
                                else:
                                    self._trigger_queue_auto_start()
        elif cur == "video_gen" and self.controller:
            state = self._pipeline.state
            config = self._setup_matrix.get_config() if self._setup_matrix else {}
            project_name = self._get_sanitized_project_name(config)
            
            # ── Multi-Version: create one group per version ──
            if state.is_multi_version() and state.versions and len(state.versions) > 1:
                # Check if ALL versions' scenes have videos already
                all_have_videos = True
                for v in state.versions:
                    v_scenes = v.scenes or []
                    missing = [s for s in v_scenes if not (s.video_path and os.path.isfile(s.video_path))]
                    if missing:
                        all_have_videos = False
                        break
                
                if all_have_videos:
                    log.info(f"[Pipeline] Stage 6: All {len(state.versions)} versions have videos → skipping queue")
                    self._queue_submitted_for_stage = True  # Legitimate skip — all files exist
                else:
                    from config.constants import WorkflowType
                    group_version_map = {}  # {group_id: version_idx}
                    saved_vi = state.current_version_idx
                    
                    # Base settings shared across versions
                    base_settings = {
                        "model": config.get("video_model", "Veo 3.1 - Fast"),
                        "aspect_ratio": config.get("video_aspect", "LANDSCAPE"),
                        "download_quality": config.get("video_quality", "720p"),
                        "duration": config.get("clip_duration", 8),
                        "outputs_per_prompt": config.get("video_outputs", 1),
                        "output_folder": config.get("output_folder", ""),
                    }
                    stage_data_global = state.get_stage("video_gen").data or {}
                    base_settings["voice_enabled"] = stage_data_global.get(
                        "voice_enabled", config.get("voice_enabled", True)
                    )
                    
                    # Shared character images (from Stage 4)
                    char_images = []
                    for c in (state.characters or []):
                        if c.image_path and os.path.isfile(c.image_path):
                            char_images.append(c.image_path)
                    
                    for vi, version in enumerate(state.versions):
                        state.activate_version(vi)
                        v_scenes = state.scenes or []
                        if not v_scenes:
                            log.warning(f"[Pipeline] Stage 6: {version.label} has no scenes → skipping")
                            continue
                        
                        # Check which scenes still need videos
                        need_videos = [s for s in v_scenes if not (s.video_path and os.path.isfile(s.video_path))]
                        if not need_videos:
                            log.info(f"[Pipeline] Stage 6: {version.label} — all {len(v_scenes)} scenes have videos → skip")
                            continue
                        
                        # ★ VEO accepts full JSON as prompt — no unwrapping needed
                        if not prompts:
                            continue
                        
                        v_settings = dict(base_settings)
                        v_settings["project_name"] = f"{project_name}/video/{version.label}"
                        
                        # Per-version I2V / R2V / T2V routing
                        per_prompt_images = {}
                        per_prompt_workflows = {}
                        i2v_count = r2v_count = t2v_count = 0
                        for i, s in enumerate(v_scenes):
                            if i >= len(prompts):
                                break
                            if s.image_path and os.path.isfile(s.image_path):
                                # ★ Consecutive pair: Scene[i] (start) + Scene[i+1] (end)
                                next_s = v_scenes[i + 1] if i + 1 < len(v_scenes) else None
                                if next_s and next_s.image_path and os.path.isfile(next_s.image_path):
                                    per_prompt_images[i] = [s.image_path, next_s.image_path]
                                else:
                                    per_prompt_images[i] = [s.image_path]  # last scene: single-frame
                                per_prompt_workflows[i] = "I2V"
                                i2v_count += 1
                            elif char_images:
                                per_prompt_images[i] = char_images
                                per_prompt_workflows[i] = "R2V"
                                r2v_count += 1
                            else:
                                per_prompt_workflows[i] = "T2V"
                                t2v_count += 1
                        # Enable _fl_ model when pairs are available
                        v_settings["frame_mode"] = "both"
                        
                        log.info(
                            f"[Pipeline] Stage 6 {version.label}: "
                            f"{i2v_count} I2V, {r2v_count} R2V, {t2v_count} T2V "
                            f"out of {len(prompts)} prompts"
                        )
                        
                        group_id = None
                        if per_prompt_images:
                            group_id = self.controller.submit_prompts(
                                prompts=prompts,
                                workflow=WorkflowType.I2V,
                                per_prompt_images=per_prompt_images,
                                per_prompt_workflows=per_prompt_workflows,
                                settings=v_settings,
                            )
                        elif hasattr(self.controller, "add_t2v_batch"):
                            group_id = self.controller.add_t2v_batch(prompts=prompts, settings=v_settings)
                        
                        if group_id:
                            group_version_map[group_id] = vi
                            log.info(
                                f"[Pipeline] Stage 6: {version.label} → "
                                f"{len(prompts)} prompts → group={group_id}"
                            )
                    
                    # Restore original active version
                    state.activate_version(saved_vi)
                    
                    if group_version_map:
                        self._start_multi_group_polling(group_version_map, "video_gen")
                        # ★ Wait for library pre-upload before engine starts
                        if hasattr(self.controller, 'flush_pending_pre_upload'):
                            self.controller.flush_pending_pre_upload(
                                on_done=self._trigger_queue_auto_start
                            )
                        else:
                            self._trigger_queue_auto_start()
                        log.info(
                            f"[Pipeline] Stage 6: Created {len(group_version_map)} version groups "
                            f"for parallel video generation"
                        )
            else:
                # ── Single version (original logic) ──
                scenes = state.scenes or []
                videos_exist = [s for s in scenes if s.video_path and os.path.isfile(s.video_path)]
                if scenes and len(videos_exist) == len(scenes):
                    log.info(
                        f"[Pipeline] Stage 6: All {len(scenes)} scenes have video files. "
                        f"Skipping queue → advancing to concat."
                    )
                    self._queue_submitted_for_stage = True  # Legitimate skip — all files exist
                else:
                    if videos_exist:
                        log.info(
                            f"[Pipeline] Stage 6: {len(videos_exist)}/{len(scenes)} scenes "
                            f"have videos. Re-sending missing prompts to queue."
                        )
                    
                    stage_data = state.get_stage("video_gen").data or {}
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
                    # ★ VEO accepts full JSON as prompt — no unwrapping needed
                    for i, p in enumerate(prompts):
                        log.info(f"[Pipeline] Stage 6 prompt[{i}]: {p[:80]}...")
                    log.info(f"[Pipeline] Stage 6 prompts: {len(prompts)} from video_configs (sanitized)")
                    if prompts:
                        settings = {
                            "model": config.get("video_model", "Veo 3.1 - Fast"),
                            "aspect_ratio": config.get("video_aspect", "LANDSCAPE"),
                            "download_quality": config.get("video_quality", "720p"),
                            "duration": config.get("clip_duration", 8),
                            "outputs_per_prompt": config.get("video_outputs", 1),
                            "output_folder": config.get("output_folder", ""),
                            "project_name": f"{project_name}/video",
                            "frame_mode": config.get("video_frame_mode", "both"),
                        }
                        # R4-2 Fix: Pass voice_enabled from pipeline stage data to engine
                        stage_data = state.get_stage("video_gen").data if self._pipeline else {}
                        settings["voice_enabled"] = stage_data.get("voice_enabled", config.get("voice_enabled", True))
                        # Route: per-scene I2V (scene image) or R2V (char images from Stage 4)
                        from config.constants import WorkflowType
                        scenes = state.scenes if self._pipeline else []
                        char_images = []
                        for c in (state.characters or []):
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
                                # ★ Consecutive pair: Scene[i] (start) + Scene[i+1] (end)
                                # This drives the _fl_ (First+Last) model for smooth transitions.
                                # Last scene has no next scene → falls back to single-frame I2V.
                                next_scene = scenes[i + 1] if i + 1 < len(scenes) else None
                                if next_scene and next_scene.image_path and os.path.isfile(next_scene.image_path):
                                    per_prompt_images[i] = [s.image_path, next_scene.image_path]
                                else:
                                    per_prompt_images[i] = [s.image_path]  # last scene: single-frame
                                per_prompt_workflows[i] = "I2V"
                                i2v_count += 1
                            elif char_images:
                                per_prompt_images[i] = char_images
                                per_prompt_workflows[i] = "R2V"
                                r2v_count += 1
                            else:
                                per_prompt_workflows[i] = "T2V"
                                t2v_count += 1
                        # Enable _fl_ model when pairs are available
                        settings["frame_mode"] = "both"
                        
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
                            # ★ Wait for library pre-upload before engine starts
                            if hasattr(self.controller, 'flush_pending_pre_upload'):
                                self.controller.flush_pending_pre_upload(
                                    on_done=self._trigger_queue_auto_start
                                )
                            else:
                                self._trigger_queue_auto_start()

        # Auto-advance AND auto-run next stage
        # BUT: if we just started queue polling, defer advance to _on_queue_group_complete
        if getattr(self, '_queue_awaiting_completion', False):
            log.info(f"[Pipeline] Auto-advance deferred — waiting for queue group to complete")
            return
        
        # ★ BYPASS GUARD: For queue-dependent stages, block advance if queue
        # was NOT submitted. This prevents cascading empty data (e.g. Stage 4
        # advances without images → Stage 5/6/7 all lack data).
        QUEUE_STAGES = {"character_gen", "scene_image_gen", "video_gen"}
        if cur in QUEUE_STAGES and not getattr(self, '_queue_submitted_for_stage', False):
            log.warning(
                f"[Pipeline] ⚠️ Stage '{cur}' is queue-dependent but no tasks were "
                f"submitted to queue. Blocking auto-advance to prevent data loss. "
                f"Click 'Confirm & Next' manually after reviewing."
            )
            self._set_viewer_text(
                f"⚠️ Stage '{cur}' completed but no tasks were sent to queue.\n\n"
                f"This usually means prompts are missing or all files already exist.\n"
                f"Check the stage output and click 'Confirm & Next' to proceed manually."
            )
            self._sync_buttons("done")
            return
        
        next_stage = self._pipeline.get_next_stage()
        if next_stage:
            self._set_viewer_text(
                f"✅ Stage '{self._pipeline_current_stage}' confirmed.\n\n"
                f"⏳ Auto-running: {next_stage}..."
            )
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, self._run_pipeline_stage)
        else:
            # All stages complete for current version/episode
            # Check if there are more versions/episodes to process
            if self._advance_to_next_version_or_episode():
                return  # Started next version/episode
            self._advance_to_next_topic()
    
    # ── Multi-Version / Episode Advance ────────────────────────
    
    def _advance_to_next_version_or_episode(self) -> bool:
        """Check for more versions/episodes and advance if available.
        
        Returns True if started a new version/episode, False if all done.
        
        Flow:
        - Feature A/C (versions): after Stage 7 done → save current version →
          activate next → reset stages 2-7 → run from Stage 2
        - Feature B (episodes): after Stage 7 done → save current episode →
          activate next (shared chars) → reset stages 3-7 → run from Stage 3
          (skip Stage 4 since characters are shared)
        """
        if not self._pipeline:
            return False
        
        state = self._pipeline.state
        from core.production_pipeline import STAGE_ORDER, StageStatus
        
        # ── Multi-Version (Feature A/C) ──
        if state.is_multi_version() and state.versions:
            current_vi = state.current_version_idx
            total_v = len(state.versions)
            
            if current_vi < total_v - 1:
                # Save current version's results
                state.save_active_version()
                next_vi = current_vi + 1
                next_v = state.versions[next_vi]
                
                log.info(
                    f"[Pipeline] Version {current_vi + 1}/{total_v} complete. "
                    f"Starting {next_v.label} ({next_vi + 1}/{total_v})"
                )
                
                # Activate next version
                state.activate_version(next_vi)
                
                # Reset stages 2-7 for next version (Stage 1 is shared)
                for sn in STAGE_ORDER[1:]:  # Skip duration_estimate (Stage 1)
                    sr = state.get_stage(sn)
                    sr.status = StageStatus.PENDING
                    sr.data = {}
                    sr.error = ""
                    sr.prompts = []
                    sr.scenes = []
                    sr.characters = []
                
                # Reset UI dots
                for sn in STAGE_ORDER[1:]:
                    if sn in self._stage_dots:
                        self._stage_dots[sn].setStyleSheet(f"""
                            QPushButton {{
                                background-color: {Theme.SURFACE1};
                                color: {Theme.SUBTEXT0};
                                border: 1px solid {Theme.BORDER};
                                border-radius: 3px;
                                font-size: 10px; padding: 2px 6px;
                            }}
                        """)
                
                # Update state to re-run from Stage 2
                state.current_stage = STAGE_ORDER[1]  # bible_gen
                
                # Show progress
                self._set_viewer_text(
                    f"🎬 {next_v.label} ({next_vi + 1}/{total_v})\n\n"
                    f"⏳ Generating Bible & prompts for version {next_vi + 1}...\n"
                    f"Topic: {state.topic[:100]}..."
                )
                
                # Update version label on UI
                self._update_version_label(next_v.label, next_vi + 1, total_v)
                
                from PySide6.QtCore import QTimer
                QTimer.singleShot(500, self._run_pipeline_stage)
                return True
        
        # ── Multi-Episode (Feature B) ──
        if state.is_multi_episode() and state.episodes:
            current_ei = state.current_episode_idx
            total_e = len(state.episodes)
            
            if current_ei < total_e - 1:
                # Save current episode's results
                state.save_active_episode()
                next_ei = current_ei + 1
                next_ep = state.episodes[next_ei]
                
                log.info(
                    f"[Pipeline] {state.episodes[current_ei].label} complete. "
                    f"Starting {next_ep.label} ({next_ei + 1}/{total_e})"
                )
                
                # Activate next episode (shared characters)
                state.activate_episode(next_ei)
                
                # Reset stages 3-7 for next episode (Stage 1-2 shared, Stage 4 skipped)
                # BUT: keep Stage 4 (character_gen) as-is since chars are shared
                for sn in STAGE_ORDER[2:]:  # scene_breakdown onwards
                    if sn == "character_gen":
                        continue  # Skip — characters shared across episodes
                    sr = state.get_stage(sn)
                    sr.status = StageStatus.PENDING
                    sr.data = {}
                    sr.error = ""
                    sr.prompts = []
                    sr.scenes = []
                
                # Reset UI dots for stages 3-7 (except Stage 4)
                for sn in STAGE_ORDER[2:]:
                    if sn == "character_gen":
                        continue
                    if sn in self._stage_dots:
                        self._stage_dots[sn].setStyleSheet(f"""
                            QPushButton {{
                                background-color: {Theme.SURFACE1};
                                color: {Theme.SUBTEXT0};
                                border: 1px solid {Theme.BORDER};
                                border-radius: 3px;
                                font-size: 10px; padding: 2px 6px;
                            }}
                        """)
                
                # Mark Stage 4 as already confirmed/complete (chars shared)
                s4 = state.get_stage("character_gen")
                s4.status = StageStatus.CONFIRMED
                
                # Re-run from Stage 3 (scene_breakdown)
                state.current_stage = "scene_breakdown"
                
                self._set_viewer_text(
                    f"📺 {next_ep.label} ({next_ei + 1}/{total_e})\n\n"
                    f"⏳ Generating scenes for episode {next_ei + 1}...\n"
                    f"Characters: shared from episode 1\n"
                    f"Topic: {state.topic[:100]}..."
                )
                
                self._update_version_label(next_ep.label, next_ei + 1, total_e)
                
                from PySide6.QtCore import QTimer
                QTimer.singleShot(500, self._run_pipeline_stage)
                return True
        
        return False
    
    def _update_version_label(self, label: str, current: int, total: int):
        """Update the stage dot area with version/episode progress indicator."""
        pass  # Label removed — progress is shown in group headers
    
    def _populate_version_selector(self):
        """Stub — version selector and progress label removed."""
        pass
    
    def _on_version_selector_changed(self, index: int):
        """Handle version/episode selector change — debounced to prevent freeze on rapid clicks.
        
        _show_stage_review → _update_thumbnails rebuilds many QWidgets which is heavy.
        A 150ms debounce ensures only the LAST selection is processed.
        """
        if index < 0 or not self._pipeline:
            return
        
        # Debounce: cancel previous pending timer, start new one
        if not hasattr(self, '_version_debounce_timer'):
            from PySide6.QtCore import QTimer
            self._version_debounce_timer = QTimer(self)
            self._version_debounce_timer.setSingleShot(True)
            self._version_debounce_timer.timeout.connect(self._apply_version_change)
        
        self._version_pending_index = index
        self._version_debounce_timer.start(150)  # ms
    
    def _apply_version_change(self):
        """Apply the debounced version/episode switch."""
        index = getattr(self, '_version_pending_index', -1)
        if index < 0 or not self._pipeline:
            return
        
        state = self._pipeline.state
        
        if state.is_multi_version() and state.versions:
            if index != state.current_version_idx:
                state.save_active_version()
                state.activate_version(index)
                v = state.versions[index]
                log.info(f"[Pipeline] UI: Switched to {v.label} (idx={index})")
                self._update_version_label(v.label, index + 1, len(state.versions))
        elif state.is_multi_episode() and state.episodes:
            if index != state.current_episode_idx:
                state.save_active_episode()
                state.activate_episode(index)
                ep = state.episodes[index]
                log.info(f"[Pipeline] UI: Switched to {ep.label} (idx={index})")
                self._update_version_label(ep.label, index + 1, len(state.episodes))
        
        # Refresh the current stage display
        if self._pipeline_current_stage:
            self._show_stage_review(self._pipeline_current_stage)
    
    def _hide_version_selector(self):
        """Stub — version progress label removed."""
        pass

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
            for sn in ["duration_estimate", "bible_gen", "scene_breakdown",
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
            self._set_viewer_text(
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
            
            self._set_viewer_text("\n".join(summary_lines))
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
        
        For single-group stages (character_gen) or single-version.
        For multi-version stages, use _start_multi_group_polling() instead.
        """
        from PySide6.QtCore import QTimer
        
        # Stop any existing polling timer
        if hasattr(self, '_queue_poll_timer') and self._queue_poll_timer:
            self._queue_poll_timer.stop()
        
        self._queue_poll_group_id = group_id
        self._queue_poll_stage = stage_name
        self._queue_poll_multi_groups = None  # Single-group mode
        self._queue_awaiting_completion = True  # Block auto-advance until queue finishes
        self._queue_submitted_for_stage = True  # Mark that queue WAS submitted
        self._populated_tasks = set()  # Dedup: skip already-processed tasks on subsequent polls
        # Notify controller to defer auto-stop during pipeline queue processing
        if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
            self.controller.set_pipeline_queue_active(True)
        self._queue_poll_timer = QTimer(self)
        # Fix 5: Visual stages with thumbnails → poll less frequently to reduce UI rebuild load
        visual_poll_stages = {"scene_image_gen", "video_gen", "concat"}
        interval = 4000 if stage_name in visual_poll_stages else 2000
        self._queue_poll_timer.setInterval(interval)
        self._queue_poll_timer.timeout.connect(self._check_queue_progress)
        self._queue_poll_timer.start()
        
        log.info(f"[Pipeline] Started queue polling for group={group_id}, stage={stage_name}")
        self._set_viewer_text(
            f"⏳ Queue Processing: 0/? tasks\n"
            f"Stage: {stage_name}\n"
            f"Group: {group_id}\n\n"
            f"Waiting for VEO engine to process...\n"
            f"Switch to Queue tab to see detailed progress."
        )
    
    def _start_multi_group_polling(self, group_version_map: dict, stage_name: str):
        """Start polling for MULTIPLE queue groups simultaneously.
        
        Used by multi-version Stages 5 & 6 — each version creates its own
        queue group, all processed in parallel.
        
        Args:
            group_version_map: {group_id: version_idx, ...}
            stage_name: "scene_image_gen" or "video_gen"
        """
        from PySide6.QtCore import QTimer
        
        if hasattr(self, '_queue_poll_timer') and self._queue_poll_timer:
            self._queue_poll_timer.stop()
        
        self._queue_poll_group_id = None  # Not single-group mode
        self._queue_poll_stage = stage_name
        # Multi-group tracking: {group_id: {"version_idx": int, "done": False}}
        self._queue_poll_multi_groups = {
            gid: {"version_idx": vi, "done": False}
            for gid, vi in group_version_map.items()
        }
        self._queue_awaiting_completion = True
        self._queue_submitted_for_stage = True  # Mark that queue WAS submitted
        self._populated_tasks = set()  # Dedup: skip already-processed tasks on subsequent polls
        if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
            self.controller.set_pipeline_queue_active(True)
        
        self._queue_poll_timer = QTimer(self)
        # Fix 5: Visual stages with thumbnails → poll less frequently to reduce UI rebuild load
        visual_poll_stages = {"scene_image_gen", "video_gen", "concat"}
        interval = 4000 if stage_name in visual_poll_stages else 2000
        self._queue_poll_timer.setInterval(interval)
        self._queue_poll_timer.timeout.connect(self._check_queue_progress)
        self._queue_poll_timer.start()
        
        version_labels = []
        if self._pipeline and self._pipeline.state.versions:
            for gid, vi in group_version_map.items():
                if vi < len(self._pipeline.state.versions):
                    version_labels.append(self._pipeline.state.versions[vi].label)
        
        log.info(
            f"[Pipeline] Started MULTI-GROUP polling for {len(group_version_map)} groups, "
            f"stage={stage_name}, versions={list(group_version_map.values())}"
        )
        self._set_viewer_text(
            f"⏳ Queue Processing: {len(group_version_map)} version groups\n"
            f"Stage: {stage_name}\n"
            f"Versions: {', '.join(version_labels) or str(list(group_version_map.values()))}\n\n"
            f"Waiting for VEO engine to process all groups in parallel...\n"
            f"Switch to Queue tab to see detailed progress."
        )
    
    def _check_queue_progress(self):
        """Poll controller for queue group status, update UI.
        
        Supports both single-group and multi-group modes.
        """
        if not self._pipeline:
            if hasattr(self, '_queue_poll_timer') and self._queue_poll_timer:
                self._queue_poll_timer.stop()
            self._queue_poll_multi_groups = None
            return

        if not self.controller or not hasattr(self.controller, 'get_group_status'):
            return
        
        # ── Multi-group mode ──
        if getattr(self, '_queue_poll_multi_groups', None):
            self._check_multi_group_progress()
            return
        
        # ── Single-group mode (original logic) ──
        if not hasattr(self, '_queue_poll_group_id') or not self._queue_poll_group_id:
            return
        
        group_id = self._queue_poll_group_id
        stage_name = self._queue_poll_stage
        
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
        self._set_viewer_text(
            f"⏳ Queue Processing: {completed}/{total} completed"
            f"{f', {failed} failed' if failed else ''}\n"
            f"Stage: {stage_name}\n"
            f"Group: {group_id}\n\n"
            f"[{progress_bar}]\n\n"
            f"Switch to Queue tab for detailed progress."
        )
        
        # Populate paths from completed tasks (dedup — skip already-processed)
        # Key = (task_id, best_file) so force-retry with new output is re-processed
        _dedup = getattr(self, '_populated_tasks', set())
        for task_info in status.get("completed_tasks", []):
            _tid = task_info.get("task_id", "")
            _bf = task_info.get("best_file", "")
            _key = (_tid, _bf)
            if _tid and _key in _dedup:
                continue
            self._populate_path_from_task(stage_name, task_info)
            if _tid:
                _dedup.add(_key)
        
        # Debounce: only update thumbnails if completed count changed
        prev_completed = getattr(self, '_queue_poll_prev_completed', -1)
        if completed != prev_completed:
            self._queue_poll_prev_completed = completed
            # Fix 1: Throttle thumbnail rebuilds to max 1x/5s during queue polling
            self._throttled_update_thumbnails(stage_name)
            # Incremental save every 5 completions — prevents video_path loss on crash
            # Fix 2: Use async save to avoid blocking GUI thread
            if completed > 0 and completed % 5 == 0:
                self._save_session_to_disk_async()
        
        # Check if group is done
        if status.get("is_done"):
            self._queue_poll_timer.stop()
            self._queue_awaiting_completion = False  # Unblock auto-advance
            log.info(f"[Pipeline] Queue group {group_id} completed: {completed}/{total} OK, {failed} failed")
            # ★ Subscribe to TASK_COMPLETED events for late force-retry detection
            self._subscribe_late_completion(group_id, stage_name)
            self._on_queue_group_complete(stage_name, status)
    
    def _check_multi_group_progress(self):
        """Poll ALL groups in multi-group mode. Advance when ALL complete."""
        if not self._pipeline:
            if hasattr(self, '_queue_poll_timer') and self._queue_poll_timer:
                self._queue_poll_timer.stop()
            self._queue_poll_multi_groups = None
            return

        stage_name = self._queue_poll_stage
        groups = self._queue_poll_multi_groups
        
        total_completed = 0
        total_failed = 0
        total_tasks = 0
        all_done = True
        version_lines = []
        
        for gid, info in groups.items():
            vi = info["version_idx"]
            if info["done"]:
                # Already completed — skip re-query
                continue
            
            try:
                status = self.controller.get_group_status(gid)
            except Exception as e:
                log.warning(f"[Pipeline] Multi-group poll error for {gid}: {e}")
                all_done = False
                continue
            
            if not status:
                all_done = False
                continue
            
            c, f, t = status["completed"], status["failed"], status["total"]
            total_completed += c
            total_failed += f
            total_tasks += t
            
            # Populate paths — version-aware (dedup — skip already-processed)
            # Key = (task_id, best_file) so force-retry with new output is re-processed
            _dedup = getattr(self, '_populated_tasks', set())
            for task_info in status.get("completed_tasks", []):
                _tid = task_info.get("task_id", "")
                _bf = task_info.get("best_file", "")
                _key = (_tid, _bf)
                if _tid and _key in _dedup:
                    continue
                self._populate_path_from_task(
                    stage_name, task_info, version_idx=vi
                )
                if _tid:
                    _dedup.add(_key)
            
            # Version label
            v_label = f"V{vi+1}"
            if self._pipeline and self._pipeline.state.versions:
                if vi < len(self._pipeline.state.versions):
                    v_label = self._pipeline.state.versions[vi].label
            
            if status.get("is_done"):
                info["done"] = True
                version_lines.append(f"  ✅ {v_label}: {c}/{t} done{f', {f} failed' if f else ''}")
                self._subscribe_late_completion(gid, stage_name)
                log.info(f"[Pipeline] Multi-group: {v_label} (group={gid}) completed: {c}/{t} OK, {f} failed")
            else:
                all_done = False
                bar = "█" * c + "░" * (t - c - f) + "✗" * f
                version_lines.append(f"  ⏳ {v_label}: [{bar}] {c}/{t}")
        
        # Update UI
        self._set_viewer_text(
            f"⏳ Multi-Version Queue: {total_completed}/{total_tasks} completed"
            f"{f', {total_failed} failed' if total_failed else ''}\n"
            f"Stage: {stage_name}\n\n"
            + "\n".join(version_lines)
            + "\n\nSwitch to Queue tab for detailed progress."
        )
        
        # Debounce thumbnails
        prev = getattr(self, '_queue_poll_prev_completed', -1)
        if total_completed != prev:
            self._queue_poll_prev_completed = total_completed
            # Fix 1: Throttle thumbnail rebuilds to max 1x/5s during queue polling
            self._throttled_update_thumbnails(stage_name)
            # Fix 2: Use async save to avoid blocking GUI thread
            if total_completed > 0 and total_completed % 5 == 0:
                self._save_session_to_disk_async()
        
        # ALL groups done → advance
        if all_done:
            self._queue_poll_timer.stop()
            self._queue_poll_multi_groups = None
            self._queue_awaiting_completion = False
            log.info(
                f"[Pipeline] ALL {len(groups)} version groups completed for {stage_name}: "
                f"{total_completed}/{total_tasks} OK, {total_failed} failed"
            )
            # Build aggregated status for _on_queue_group_complete
            agg_status = {
                "completed": total_completed,
                "failed": total_failed,
                "total": total_tasks,
                "is_done": True,
            }
            self._on_queue_group_complete(stage_name, agg_status)
    
    def _populate_path_from_task(self, stage_name: str, task_info: dict, version_idx: int = None):
        """Populate pipeline state paths from a completed queue task.
        
        Allows overwrite: force retry in Queue tab will update stale paths.
        
        Args:
            stage_name: Pipeline stage name
            task_info: Task completion info from get_group_status()
            version_idx: If provided, map to version's scenes instead of active state.scenes
        """
        idx = task_info.get("prompt_index", 0)
        best_file = task_info.get("best_file", "")
        if not best_file:
            return
        
        # Resolve scenes list — version-aware for multi-group
        def _get_scenes():
            """Get the right scenes list for this version."""
            if version_idx is not None and self._pipeline and self._pipeline.state.versions:
                versions = self._pipeline.state.versions
                if version_idx < len(versions):
                    return versions[version_idx].scenes
            return self._pipeline.state.scenes
        
        if stage_name == "character_gen":
            chars = self._pipeline.state.characters
            
            # ── Detect Background images (Stage 4b) ──
            # BG tasks output to /backgrounds/ subfolder (from Stage 4b dispatch)
            is_bg_task = 'backgrounds' in best_file.replace('\\', '/').lower()
            
            if is_bg_task:
                # Background image completion
                bgs = getattr(self._pipeline.state, 'backgrounds', []) or []
                if idx < len(bgs):
                    bg = bgs[idx]
                    final_path = best_file
                    
                    # Rename to BG name for readability
                    if bg.name:
                        import re as _re
                        from pathlib import Path as _Path
                        src = _Path(best_file)
                        safe_name = _re.sub(r'[<>:"/\\|?*]', '_', bg.name.strip())
                        dest = src.parent / f"{safe_name}{src.suffix}"
                        try:
                            if dest.exists() and dest != src:
                                dest = src.parent / f"{safe_name}_{idx}{src.suffix}"
                            if not src.exists() and dest.exists():
                                final_path = str(dest)
                            else:
                                src.rename(dest)
                                final_path = str(dest)
                                log.info(f"[Pipeline] Renamed BG image: {src.name} → {dest.name}")
                        except Exception as e:
                            log.warning(f"[Pipeline] Could not rename BG image: {e}")
                    
                    bg.image_path = final_path
                    log.info(f"[Pipeline] ← background[{idx}].image_path = {final_path} ({bg.name})")
                    
                    # Register in ImageLibrary with BG: prefix
                    if bg.name:
                        try:
                            from services.image_library import get_image_library
                            lib = get_image_library()
                            tag_list = [f"bg:{bg.name.lower().strip()}"]
                            if bg.tag and bg.tag not in tag_list:
                                tag_list.append(f"bg:{bg.tag}")
                            lib.update_or_add_image(
                                final_path, tags=tag_list,
                                category="Backgrounds", copy_to_library=False
                            )
                            log.info(f"[Pipeline] ✅ BG {tag_list} registered in ImageLibrary → {final_path}")
                        except Exception as e:
                            log.warning(f"[Pipeline] BG ImageLibrary registration failed: {e}")
                else:
                    log.warning(f"[Pipeline] BG image idx={idx} out of range (only {len(bgs)} backgrounds)")
                return  # Done — don't fall through to character handling
            
            if idx < len(chars):
                old_path = chars[idx].image_path
                if old_path and old_path != best_file:
                    log.info(f"[Pipeline] ♻️ character[{idx}].image_path OVERWRITTEN (force retry): {old_path} → {best_file}")
                if True:  # Always overwrite — supports force retry
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
                            if not src.exists() and dest.exists():
                                # Already renamed by previous poll — use dest
                                final_path = str(dest)
                                log.debug(f"[Pipeline] Char image already renamed: {dest.name}")
                            else:
                                src.rename(dest)
                                final_path = str(dest)
                                log.info(f"[Pipeline] Renamed char image: {src.name} → {dest.name}")
                        except Exception as e:
                            log.warning(f"[Pipeline] Could not rename char image: {e}")
                    
                    chars[idx].image_path = final_path
                    log.info(f"[Pipeline] ← character[{idx}].image_path = {final_path}")
                    
                    # Register in ImageLibrary for [tag] auto-resolution
                    # Build tag list with aliases: "Mèo Em (Milo)" → ["mèo em (milo)", "milo", "mèo em"]
                    if char_name:
                        try:
                            import re as _tag_re
                            from services.image_library import get_image_library
                            lib = get_image_library()
                            tag_list = [char_name.lower().strip()]
                            # Extract parenthesized aliases
                            parens = _tag_re.findall(r'\(([^)]+)\)', char_name)
                            for p in parens:
                                alias = p.strip().lower()
                                if alias and alias not in tag_list:
                                    tag_list.append(alias)
                            # Base name without parentheses
                            base = _tag_re.sub(r'\s*\([^)]*\)\s*', '', char_name).strip().lower()
                            if base and base not in tag_list:
                                tag_list.append(base)
                            img, was_updated = lib.update_or_add_image(
                                final_path, tags=tag_list,
                                category="Characters", copy_to_library=False
                            )
                            if was_updated:
                                log.info(f"[Pipeline] ♻️ {tag_list} UPDATED in ImageLibrary → {final_path} (old mediaIds cleared)")
                            else:
                                log.info(f"[Pipeline] ✅ {tag_list} registered in ImageLibrary → {final_path}")
                        except Exception as e:
                            log.warning(f"[Pipeline] ImageLibrary registration failed: {e}")
        elif stage_name == "scene_image_gen":
            scenes = _get_scenes()
            v_label = f" (V{version_idx+1})" if version_idx is not None else ""
            if idx < len(scenes):
                old_path = scenes[idx].image_path
                if old_path and old_path != best_file:
                    log.info(f"[Pipeline] ♻️ scene[{idx}]{v_label}.image_path OVERWRITTEN: {old_path} → {best_file}")
                if True:  # Always overwrite — supports force retry
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
                        if not src.exists() and dest.exists():
                            # Already renamed by previous poll — use dest
                            final_path = str(dest)
                            log.debug(f"[Pipeline] Scene image already renamed: {dest.name}")
                        else:
                            src.rename(dest)
                            final_path = str(dest)
                            log.info(f"[Pipeline] Renamed scene image: {src.name} → {dest.name}")
                    except Exception as e:
                        log.warning(f"[Pipeline] Could not rename scene image: {e}")
                    
                    scenes[idx].image_path = final_path
                    log.info(f"[Pipeline] ← scene[{idx}]{v_label}.image_path = {final_path}")
                    
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
            scenes = _get_scenes()
            v_label = f" (V{version_idx+1})" if version_idx is not None else ""
            if idx < len(scenes):
                old_path = scenes[idx].video_path
                if old_path and old_path != best_file:
                    log.info(f"[Pipeline] ♻️ scene[{idx}]{v_label}.video_path OVERWRITTEN: {old_path} → {best_file}")
                scenes[idx].video_path = best_file
                log.info(f"[Pipeline] ← scene[{idx}]{v_label}.video_path = {best_file}")
    
    def _subscribe_late_completion(self, group_id: str, stage_name: str):
        """Subscribe to TASK_COMPLETED events for force-retry detection.
        
        After group polling stops (is_done=True), force-retried tasks
        can still complete later. This event listener catches those
        late completions and updates pipeline state + thumbnails.
        """
        from core.event_manager import get_event_manager, EventType
        
        # Avoid duplicate subscriptions
        if hasattr(self, '_late_completion_cb') and self._late_completion_cb:
            get_event_manager().unsubscribe(EventType.TASK_COMPLETED, self._late_completion_cb)
        
        def _on_late_task_completed(event):
            """Handle TASK_COMPLETED event for force-retried tasks."""
            task_id = event.data.get("task_id", "")
            if not task_id or not self._pipeline:
                return
            # Check if this task belongs to our pipeline group
            if not task_id.startswith(group_id):
                return
            
            log.info(f"[Pipeline] 🔄 Late TASK_COMPLETED detected: {task_id} (force retry?)")
            
            # Re-query group status to get updated best_file
            if not self.controller or not hasattr(self.controller, 'get_group_status'):
                return
            try:
                status = self.controller.get_group_status(group_id)
                if not status:
                    return
                for task_info in status.get("completed_tasks", []):
                    if task_info.get("task_id") == task_id:
                        self._populate_path_from_task(stage_name, task_info)
                        # Refresh thumbnails on UI thread
                        from PySide6.QtCore import QMetaObject, Qt
                        QMetaObject.invokeMethod(
                            self, "_update_thumbnails_safe",
                            Qt.ConnectionType.QueuedConnection,
                        )
                        break
            except Exception as e:
                log.warning(f"[Pipeline] Late completion handler error: {e}")
        
        self._late_completion_cb = _on_late_task_completed
        self._late_completion_group_id = group_id
        self._late_completion_stage = stage_name
        get_event_manager().subscribe(EventType.TASK_COMPLETED, _on_late_task_completed)
        log.info(f"[Pipeline] ★ Subscribed to late TASK_COMPLETED for group={group_id}")
    
    def _unsubscribe_late_completion(self):
        """Unsubscribe from TASK_COMPLETED events (called on pipeline reset)."""
        if hasattr(self, '_late_completion_cb') and self._late_completion_cb:
            from core.event_manager import get_event_manager, EventType
            get_event_manager().unsubscribe(EventType.TASK_COMPLETED, self._late_completion_cb)
            self._late_completion_cb = None
            log.info("[Pipeline] ★ Unsubscribed from late TASK_COMPLETED")
        self._late_completion_group_id = None
        self._late_completion_stage = None
    
    from PySide6.QtCore import Slot
    @Slot()
    def _update_thumbnails_safe(self):
        """Thread-safe wrapper to refresh thumbnails from event callback."""
        if not self._pipeline:
            return
        stage = getattr(self, '_late_completion_stage', None)
        if stage:
            self._update_thumbnails(stage)
    
    # ── Fix 1: Throttled thumbnail rebuild ──────────────────────
    
    def _throttled_update_thumbnails(self, stage_name: str):
        """Throttle thumbnail rebuilds to max once per 5s during queue polling.
        
        Prevents main-thread freeze from destroying/creating hundreds of widgets
        every 2-4s when queue tasks complete in rapid succession.
        """
        if not self._pipeline:
            return
        import time
        now = time.monotonic()
        last = getattr(self, '_thumb_last_rebuild', 0.0)
        if now - last < 5.0:
            # Schedule one deferred rebuild if none pending
            if not getattr(self, '_thumb_deferred', False):
                self._thumb_deferred = True
                from PySide6.QtCore import QTimer
                remain_ms = int((5.0 - (now - last)) * 1000) + 100
                QTimer.singleShot(remain_ms, lambda: self._deferred_thumb_rebuild(stage_name))
            return
        self._thumb_last_rebuild = now
        self._thumb_deferred = False
        self._update_thumbnails(stage_name)
    
    def _deferred_thumb_rebuild(self, stage_name: str):
        """Execute deferred thumbnail rebuild after throttle window expires."""
        if not self._pipeline:
            self._thumb_deferred = False
            return
        import time
        self._thumb_last_rebuild = time.monotonic()
        self._thumb_deferred = False
        self._update_thumbnails(stage_name)
    
    # ── Fix 2: Async session save ───────────────────────────────
    
    def _save_session_to_disk_async(self):
        """Non-blocking version: snapshots state on main thread, writes file on bg thread.
        
        Used in queue polling paths where blocking the GUI is unacceptable.
        The sync _save_session_to_disk() is still used on explicit user actions
        (skip, queue-group-complete) where data integrity is critical.
        """
        import threading
        if not self._pipeline:
            return
        self._pipeline_auto_restore_enabled = True
        persist_epoch = getattr(self, '_pipeline_persist_epoch', 0)
        
        # Snapshot data on main thread (fast dict copy)
        try:
            session_data = self._pipeline.state.to_session_dict()
            session_data["_ui"] = {
                "pipeline_current_stage": self._pipeline_current_stage or "",
                "viewer_text": self._stage_viewer.toPlainText() if hasattr(self, '_stage_viewer') else "",
            }
        except Exception as e:
            log.warning(f"[Pipeline] Session snapshot failed: {e}")
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
        
        def _write():
            import json as _json
            from pathlib import Path
            if persist_epoch != getattr(self, '_pipeline_persist_epoch', 0):
                log.debug("[Pipeline] Async session save skipped: stale epoch")
                return
            project_dir = Path(output_folder) / folder_name
            project_dir.mkdir(parents=True, exist_ok=True)
            session_path = project_dir / "_pipeline_session.json"
            try:
                session_path.write_text(
                    _json.dumps(session_data, ensure_ascii=False, indent=2, default=str),
                    encoding='utf-8'
                )
                log.info(f"[Pipeline] Session saved (async) → {session_path}")
                # Update session registry
                try:
                    from core.session_registry import SessionRegistry
                    SessionRegistry().update(str(project_dir), topic=topic_slug)
                except Exception:
                    pass
            except Exception as e:
                log.warning(f"[Pipeline] Async session save failed: {e}")
        
        threading.Thread(target=_write, daemon=True, name="pipeline-save").start()
    
    def _on_queue_group_complete(self, stage_name: str, status: dict):
        """Queue group finished → update UI → auto-advance if enabled."""
        # ★ Persist video_paths/image_paths populated during queue polling.
        # Without this, restart loses all video results and re-queues everything.
        self._save_session_to_disk()
        # Emit event for subscribers
        try:
            from core.pipeline_events import pipeline_bus, Events
            pipeline_bus.emit(Events.GROUP_COMPLETED, stage_name=stage_name, status=status)
        except Exception:
            pass
        
        completed = status["completed"]
        failed = status["failed"]
        total = status["total"]
        
        if failed > 0:
            self._set_viewer_text(
                f"⚠️ Queue completed with errors: {completed}/{total} OK, {failed} failed\n"
                f"Stage: {stage_name}\n\n"
                f"Some tasks failed. Check Queue tab for details.\n"
                f"You can still confirm to proceed with available results."
            )
        else:
            self._set_viewer_text(
                f"✅ Queue completed: {completed}/{total} tasks done\n"
                f"Stage: {stage_name}\n\n"
                f"All results populated. Click 'Confirm & Next' to proceed."
            )
        
        self._update_thumbnails(stage_name)
        # Fix 6: Only re-enable confirm if stage hasn't been confirmed yet
        from core.production_pipeline import StageStatus
        stage_result = self._pipeline.state.get_stage(stage_name)
        if stage_result.status != StageStatus.CONFIRMED:
            self._sync_buttons("done")
        
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
                    # ★ Defensive: ensure scenes are linked before concat check
                    self._ensure_pipeline_scenes_linked()
                    scenes = self._pipeline.state.scenes or []
                    if not scenes:
                        log.warning(
                            "[Pipeline] R2-6: No scene data — cannot auto-advance to concat. "
                            "Pipeline state may have lost scene data."
                        )
                        self._set_viewer_text(
                            f"⚠️ Queue completed: {completed}/{total} tasks done\n"
                            f"Stage: {stage_name}\n\n"
                            f"ERROR: No scene data available for concatenation.\n"
                            f"Scene data may not have been saved properly.\n\n"
                            f"Try re-running from Stage 3 (Scene Breakdown)."
                        )
                        if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
                            self.controller.set_pipeline_queue_active(False)
                        return
                    missing_videos = [s.index for s in scenes if not s.video_path]
                    if missing_videos:
                        log.warning(
                            f"[Pipeline] R2-6: {len(missing_videos)} scenes missing video_path "
                            f"before concat: {missing_videos}. Concat may produce partial video."
                        )
                        self._set_viewer_text(
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
                        self._sync_buttons("done")
                        return
                
                log.info(f"[Pipeline] Auto-advancing to '{next_stage}' after queue completion (stage '{stage_name}' already confirmed)")
                # ★ Keep pipeline_queue_active=True during auto-advance transition
                # to prevent AutoStop from killing engine before next stage adds tasks
                if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
                    self.controller.set_pipeline_queue_active(True)
                self._set_viewer_text(
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
        self._pipeline_auto_restore_enabled = True
        
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
            "bible_gen": "bible",
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
            display = _format_stage_result(stage_name, stage_result, state=self._pipeline.state if self._pipeline else None)
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
            # Also save full session for proper restore on restart
            # Fix 2: Use async save to avoid blocking GUI thread
            self._save_session_to_disk_async()
        except Exception:
            pass
    
    def _parse_edited_stage_data(self) -> dict:
        """Parse user-edited viewer text into correct pipeline data keys.
        
        Stage 2 (bible_gen): User edits Bible text → pass back as-is
        Stage 3 (scene_breakdown): User edits prompts text → pass back as-is
        """
        stage = self._pipeline_current_stage
        # Fix 10: Card stages use card UI edits, not hidden text viewer
        card_stages = {"character_gen", "scene_image_gen", "video_gen", "concat"}
        if stage in card_stages:
            return {}
        # Stage 3 (scene_breakdown): read edits from PipelinePromptTable
        if stage == "scene_breakdown":
            if hasattr(self, '_pipeline_prompt_table') and self._pipeline_prompt_table:
                edited = self._pipeline_prompt_table.get_items()
                if edited:
                    # Reconstruct raw_prompts text from edited table items
                    parts = []
                    for item in edited:
                        parts.append(f"--- Scene {item.index} ---")
                        parts.append(item.prompt)
                    return {"prompts_text": "\n".join(parts)}
            # Fallback: no table → empty (multi-version/episode mode)
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
        
        if stage == "bible_gen":
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
        self._sync_buttons("running", self._pipeline_current_stage)
        # _update_nav_buttons is no-op (stage dots handle nav)
        next_stage = self._pipeline.get_next_stage()
        if next_stage:
            self._set_viewer_text(f"Stage skipped.\n\n⏳ Auto-running: {next_stage}...")
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
            f"QPushButton {{ background-color: {Theme.BLUE}; color: black; "
            f"border: 1px solid {Theme.BLUE}; border-radius: 3px; "
            f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
        )
        
        self._pipeline_current_stage = prev_stage
        
        # Show saved result for review/editing
        self._show_stage_review(prev_stage)
        
        self._sync_buttons("review", prev_stage)
    
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
            f"QPushButton {{ background-color: {Theme.BLUE}; color: black; "
            f"border: 1px solid {Theme.BLUE}; border-radius: 3px; "
            f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
        )
        
        self._pipeline_current_stage = next_stage
        self._show_stage_review(next_stage)
        
        self._sync_buttons("review", next_stage)
    
    def _show_stage_review(self, stage_name: str):
        """Show saved stage data in viewer for review/editing.
        Uses _format_result() for consistent formatted display.
        """
        if not self._pipeline:
            self._clear_pipeline_visual_state()
            return

        # Toggle viewer visibility: hide for card-based stages, show for others
        card_stages = {"scene_breakdown", "character_gen", "scene_image_gen", "video_gen", "concat"}
        if stage_name in card_stages:
            self._stage_viewer.setMaximumHeight(0)
            self._stage_viewer.setVisible(False)
        else:
            self._stage_viewer.setMinimumHeight(120)
            self._stage_viewer.setMaximumHeight(16777215)
            self._stage_viewer.setVisible(True)
        # Height logic is handled inside _update_thumbnails
        self._update_thumbnails(stage_name)
        
        # Populate version/episode selector if multi-version/episode
        self._populate_version_selector()

        # Fix 7: Skip text formatting for hidden card stages
        if stage_name in card_stages:
            return

        stage_result = self._pipeline.state.get_stage(stage_name)
        if stage_result.data:
            try:
                display = _format_stage_result(stage_name, stage_result, state=self._pipeline.state if self._pipeline else None)
            except Exception:
                display = str(stage_result.data)
            
            # ── Extended character notification for Stage 3 ──
            ext_chars_notice = ""
            if stage_name == "scene_breakdown":
                ext_chars = stage_result.data.get("extended_chars", [])
                if ext_chars:
                    ext_chars_notice = (
                        f"\n{'=' * 40}\n"
                        f"⚠️ EXTENDED CHARACTERS DETECTED ({len(ext_chars)}):\n"
                        f"Các nhân vật sau xuất hiện trong prompts nhưng KHÔNG có trong Bible:\n"
                    )
                    for name in ext_chars:
                        ext_chars_notice += f"  • {name} (auto-added, AI sẽ tự tạo profile)\n"
                    ext_chars_notice += (
                        f"\nCác nhân vật này đã được tự động thêm vào danh sách.\n"
                        f"Stage 4 sẽ tạo ảnh nhân vật cho TẤT CẢ (gồm cả mở rộng).\n"
                        f"Nhấn Confirm & Next để tiếp tục, hoặc chỉnh sửa Bible nếu cần.\n"
                    )
            
            self._set_viewer_text(
                f"\U0001f4cb Reviewing: {stage_name.replace('_', ' ')}\n"
                f"Edit below, then Confirm & Next or click stage dot to navigate.\n"
                f"{'=' * 40}\n\n{display}{ext_chars_notice}"
            )
        else:
            self._set_viewer_text(
                f"\U0001f4cb {stage_name.replace('_', ' ')}\nNo saved data. Click '▶️ Start' to run."
            )
    
    def _clear_pipeline_visual_state(self):
        """Clear all viewer-side pipeline UI state, including caches that can repopulate stale data."""
        self._thumb_current_stage = None
        self._thumb_data_fingerprint = None
        self._thumb_last_rebuild = 0.0
        self._thumb_deferred = False
        self._pipeline_prompt_table = None
        self._pipeline_groups = {}
        self._stage_dot_busy = False

        if hasattr(self, '_version_debounce_timer') and self._version_debounce_timer:
            try:
                self._version_debounce_timer.stop()
            except Exception:
                pass
        self._version_pending_index = -1

        self._stage_viewer.setMinimumHeight(120)
        self._stage_viewer.setMaximumHeight(16777215)
        self._stage_viewer.setVisible(True)
        self._set_viewer_text("", reset_scroll=True)
        self._stage_viewer.setPlaceholderText("Stage results will appear here for review...")

        while self._thumb_layout.count() > 1:
            item = self._thumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._thumb_scroll.setVisible(False)
        self._thumb_scroll.setMinimumHeight(0)
        self._thumb_scroll.setMaximumHeight(100)


    def _update_nav_buttons(self, stage_name: str):
        """No-op: Back/Next buttons removed. Stage dots handle navigation."""
        pass
    
    def _on_stage_dot_clicked(self, stage_name: str):
        """Handle click on a stage dot — jump directly to that stage's data.
        
        Re-entrancy guard prevents freeze when user clicks rapidly:
        _show_stage_review → _update_thumbnails is heavy (widget rebuild).
        """
        from core.production_pipeline import STAGE_ORDER, StageStatus
        if not self._pipeline:
            return
        if stage_name not in self._stage_dots:
            return
        
        # Re-entrancy guard: reject rapid clicks while previous is processing
        if getattr(self, '_stage_dot_busy', False):
            return
        self._stage_dot_busy = True
        
        try:
            stage_result = self._pipeline.state.get_stage(stage_name)
            
            # Can only jump to stages that have data (completed/confirmed/error with data)
            if not stage_result.data and stage_result.status == StageStatus.PENDING:
                return
            
            # Restore current dot to its real status color
            if self._pipeline_current_stage and self._pipeline_current_stage in self._stage_dots:
                self._restore_dot_color(self._pipeline_current_stage)
            
            # Mark clicked dot as active (blue = review)
            self._stage_dots[stage_name].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.BLUE}; color: black; "
                f"border: 1px solid {Theme.BLUE}; border-radius: 3px; "
                f"font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )
            
            self._pipeline_current_stage = stage_name
            
            # Fix 3: Defer heavy _show_stage_review to next event loop tick
            # so dot color update paints immediately (no visible freeze)
            from PySide6.QtCore import QTimer
            _sr_data = stage_result.data  # capture for lambda
            def _deferred_review(_sn=stage_name, _data=_sr_data):
                self._show_stage_review(_sn)
                self._sync_buttons("review", _sn)
            QTimer.singleShot(0, _deferred_review)
        finally:
            # Fix 4: Release guard after 800ms (was 200ms) to cover full thumbnail rebuild time
            from PySide6.QtCore import QTimer
            QTimer.singleShot(800, lambda: setattr(self, '_stage_dot_busy', False))
    
    def _reset_pipeline_viewer(self):
        """Reset pipeline viewer to initial state — clear all data and UI."""
        from core.production_pipeline import STAGE_ORDER
        deleted_resume_files = self._delete_pipeline_resume_files()
        self._pipeline_auto_restore_enabled = False
        self._pipeline_persist_epoch = getattr(self, '_pipeline_persist_epoch', 0) + 1
        if hasattr(self, '_queue_bridge'):
            self._queue_bridge.reset()

        if hasattr(self, '_queue_poll_timer') and self._queue_poll_timer:
            try:
                self._queue_poll_timer.stop()
            except Exception:
                pass
        self._queue_poll_multi_groups = None
        self._queue_poll_prev_completed = -1
        self._queue_submitted_for_stage = False
        self._populated_tasks = set()
        if self.controller and hasattr(self.controller, 'set_pipeline_queue_active'):
            self.controller.set_pipeline_queue_active(False)
        if self.controller and hasattr(self.controller, 'set_pipeline_mode_active'):
            self.controller.set_pipeline_mode_active(False)
        
        # Reset pipeline object
        self._pipeline = None
        self._pipeline_current_stage = None
        self._pipeline_project_name = ''
        self._active_group_ids.clear()
        self._queue_poll_group_id = None
        self._queue_poll_stage = None
        
        # Reset all stage dots to default grey
        for sn, dot in self._stage_dots.items():
            dot.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.SURFACE1};
                    color: {Theme.SUBTEXT0};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 3px;
                    font-size: 10px; padding: 2px 6px;
                }}
                QPushButton:hover {{
                    background-color: {Theme.SURFACE2};
                    border-color: {Theme.BLUE};
                    color: {Theme.TEXT};
                }}
            """)
        
        # Reset viewer/caches before any delayed callbacks can repopulate them
        self._clear_pipeline_visual_state()
        
        # Reset buttons + invalidate any running thread
        self._generation_id = getattr(self, '_generation_id', 0) + 1
        self._sync_buttons("idle")
        
        # Clear batch state
        self._batch_topics = []
        self._batch_topic_idx = 0
        self._batch_results = []
        self._queue_awaiting_completion = False
        self._unsubscribe_late_completion()  # Clean up event listener
        
        if deleted_resume_files:
            deleted_names = ", ".join(path.name for path in deleted_resume_files)
            log.info(f"[Pipeline] Deleted resume files on reset: {deleted_names}")
        log.info("[Pipeline] Viewer reset to initial state")
        # Clear session registry so auto-restore won't revive this project
        try:
            from core.session_registry import SessionRegistry
            SessionRegistry().clear()
        except Exception:
            pass
        # Emit reset event and clear bus
        try:
            from core.pipeline_events import pipeline_bus, Events
            pipeline_bus.emit(Events.PIPELINE_RESET)
            pipeline_bus.clear()
        except Exception:
            pass

    def _get_pipeline_project_dir(self) -> Optional[Path]:
        """Return the current pipeline project directory, if it can be resolved."""
        if not self._pipeline:
            return None
        output_folder = ""
        if hasattr(self, '_setup_matrix') and hasattr(self._setup_matrix, 'output_folder'):
            output_folder = self._setup_matrix.output_folder.text().strip()
        if not output_folder:
            return None
        config = self._setup_matrix.get_config() if self._setup_matrix else {}
        topic_slug = self._get_sanitized_project_name(config)
        if not topic_slug:
            topic_slug = "Production"
        project_index = getattr(self._pipeline.state, '_project_index', 0)
        total_projects = getattr(self._pipeline.state, '_total_projects', 1)
        folder_name = f"{project_index + 1:03d} - {topic_slug}" if total_projects > 1 else topic_slug
        return Path(output_folder) / folder_name

    def _delete_pipeline_resume_files(self) -> List[Path]:
        """Delete resume files so Reset cannot be undone by auto-restore."""
        deleted: List[Path] = []
        project_dir = self._get_pipeline_project_dir()
        if not project_dir:
            return deleted
        for name in ("_pipeline_session.json", "_pipeline_state.json"):
            path = project_dir / name
            if not path.exists():
                continue
            try:
                path.unlink()
                deleted.append(path)
            except OSError as e:
                log.warning(f"[Pipeline] Failed to delete {path.name} during reset: {e}")
        return deleted
    
    def _restore_dot_color(self, stage_name: str):
        """Restore a stage dot to its real status color (green/red/grey)."""
        from core.production_pipeline import StageStatus
        stage = self._pipeline.state.get_stage(stage_name)
        # Fix 1: WAITING_CONFIRM also shows green (stage completed successfully)
        if stage.status in (StageStatus.CONFIRMED, StageStatus.WAITING_CONFIRM):
            color, weight, text_color = Theme.GREEN, "font-weight: bold; ", "black"
        elif stage.status == StageStatus.SKIPPED:
            color, weight, text_color = Theme.SURFACE1, "", Theme.SUBTEXT0
        elif stage.error:
            color, weight, text_color = Theme.RED, "", "black"
        else:
            color, weight, text_color = Theme.SURFACE1, "", Theme.SUBTEXT0
        self._stage_dots[stage_name].setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: {text_color}; "
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
        self._pipeline_auto_restore_enabled = True
        
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
            # Update session registry for reliable auto-restore
            try:
                from core.session_registry import SessionRegistry
                from core.production_pipeline import StageStatus
                completed = sum(
                    1 for sr in self._pipeline.state.stages.values()
                    if sr.status in (StageStatus.CONFIRMED, StageStatus.SKIPPED)
                )
                SessionRegistry().update(
                    str(project_dir),
                    topic=getattr(self._pipeline.state, 'topic', '')[:100],
                    stages_completed=completed,
                )
            except Exception:
                pass
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
        if not getattr(self, '_pipeline_auto_restore_enabled', True):
            log.info("[Pipeline] Auto-restore skipped: disabled by prior reset")
            return
        main_window = self.window()
        app_settings = getattr(main_window, 'settings', None)
        if app_settings:
            if not getattr(app_settings, 'restore_tabs_on_startup', True):
                log.info("[Pipeline] Auto-restore skipped: restore_tabs_on_startup=False")
                return
            if not getattr(app_settings, 'restore_project_builder', True):
                log.info("[Pipeline] Auto-restore skipped: restore_project_builder=False")
                return
        
        # Skip if pipeline already has data (user started a new project)
        if self._pipeline and self._pipeline_current_stage:
            return
        
        # ── Priority 0: Session Registry (deterministic) ──
        best_file = None
        best_mtime = 0
        # Check if we have an explicit last-project record
        try:
            from core.session_registry import SessionRegistry
            entry = SessionRegistry().get_last_project()
            if entry and entry.is_valid():
                # Use session file from registry
                restore_file = entry.session_path
                if not restore_file.exists():
                    restore_file = entry.state_path
                if restore_file.exists():
                    log.info(
                        f"[Pipeline] Registry restore: {entry.topic or restore_file.parent.name} "
                        f"({entry.stages_completed} stages)"
                    )
                    best_file = restore_file
                    best_mtime = restore_file.stat().st_mtime
        except Exception as e:
            log.debug(f"[Pipeline] Registry lookup failed: {e}")

        # ── Fallback: rglob scan (legacy) ──
        if not best_file:
            # Get output folder from setup matrix
            output_folder = ""
            if hasattr(self, '_setup_matrix') and hasattr(self._setup_matrix, 'output_folder'):
                output_folder = self._setup_matrix.output_folder.text().strip()

            if not output_folder or not Path(output_folder).is_dir():
                return

            # Find most recent _pipeline_state.json across all project subfolders
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
            
            # ── Priority 1: Full session file (_pipeline_session.json) ──
            # Contains scenes, characters, topic, etc. via to_session_dict()
            session_file = best_file.parent / "_pipeline_session.json"
            use_full_restore = False
            if session_file.exists():
                try:
                    session_raw = _json.loads(session_file.read_text(encoding='utf-8'))
                    if session_raw.get("stages"):
                        raw = session_raw
                        use_full_restore = True
                        log.info(f"[Pipeline] Found full session file: {session_file.name}")
                except Exception as e:
                    log.debug(f"[Pipeline] Session file read failed: {e}")
            
            # Check if it has actual completed stages
            if use_full_restore:
                stages_dict = raw.get("stages", {})
                completed_count = sum(
                    1 for sn, sr in stages_dict.items()
                    if sr.get('status') in ('confirmed', 'completed', 'skipped')
                )
            else:
                completed_count = sum(
                    1 for sn, sr in raw.items()
                    if not sn.startswith('_')
                    and sr.get('status') in ('confirmed', 'completed', 'skipped')
                )
            if completed_count == 0:
                return
            
            # Restore state
            if use_full_restore:
                # Full restore: scenes, characters, topic, all stage data
                restored_state = PipelineState.from_session_dict(raw)
                log.info(
                    f"[Pipeline] Full restore: {len(restored_state.scenes)} scenes, "
                    f"{len(restored_state.characters)} characters, "
                    f"topic='{restored_state.topic[:50]}'"
                )
            else:
                # Legacy partial restore: only stages (no scenes/characters)
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
            
            # Find current stage: prefer saved UI state, fallback to first non-completed
            ui_data = raw.get("_ui", {}) if use_full_restore else {}
            saved_current = ui_data.get("pipeline_current_stage", "")
            
            if saved_current and saved_current in STAGE_ORDER:
                current_stage = saved_current
            else:
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
                    f"QPushButton {{ background-color: {Theme.BLUE}; color: black; "
                    f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
                )
            
            # Show review
            self._show_stage_review(current_stage)
            self._update_thumbnails(current_stage)
            
            # Enable buttons
            self._sync_buttons("review", current_stage)
            
            # Restore topic
            topic = restored_state.topic
            if topic and hasattr(self, '_topics_input'):
                self._topics_input.setPlainText(topic)
            
            log.info(
                f"[Pipeline] ♻️ Auto-restored from {best_file.parent.name}: "
                f"{completed_count} completed stage(s), current={current_stage}"
                f"{', FULL session' if use_full_restore else ', partial (legacy)'}"
            )
        except Exception as e:
            log.warning(f"[Pipeline] Auto-restore failed: {e}")
    
    # ── Pipeline ↔ Queue Bidirectional Sync ────────────────────
    
    def _register_queue_callback(self):
        """Register callback on controller to receive queue updates.
        
        Called from __init__ and restore_state. Uses existing
        set_queue_updated_callback() chain — engine thread calls us,
        we bridge to main thread via _pipeline_queue_signal.
        """
        if not self.controller:
            return
        try:
            self.controller.set_queue_updated_callback(self._on_queue_updated_bridge)
            log.info("[TabProject] ✅ Registered queue_updated callback for pipeline tracking")
        except Exception as e:
            log.debug(f"[TabProject] Queue callback registration failed: {e}")
    
    def _on_queue_updated_bridge(self, status: dict):
        """Bridge from engine thread → main thread via Qt Signal.
        
        Called by controller._notify_queue_updated() from engine thread.
        Emits _pipeline_queue_signal which is connected to _on_pipeline_queue_check.
        """
        # Only emit if we have active groups to check
        if self._active_group_ids:
            self._pipeline_queue_signal.emit()
    
    @Slot()
    def _on_pipeline_queue_check(self):
        """Main-thread handler: poll get_group_status() for each tracked group.
        
        When a group's tasks are all done → update parsed project status.
        Removes completed groups from _active_group_ids.
        """
        if not self._active_group_ids or not self.controller:
            return
        
        completed_groups = []
        
        for group_id, info in list(self._active_group_ids.items()):
            try:
                status = self.controller.get_group_status(group_id)
                if not status:
                    continue  # Group not found (maybe cleared)
                
                if status.get("is_done"):
                    project_idx = info.get("project_idx", -1)
                    stage = info.get("stage", "")
                    project_name = info.get("project_name", "")
                    total = status.get("total", 0)
                    completed = status.get("completed", 0)
                    failed = status.get("failed", 0)
                    
                    log.info(
                        f"[TabProject] 🔗 Queue group {group_id} DONE: "
                        f"{completed}/{total} completed, {failed} failed, "
                        f"stage={stage}, project={project_name}"
                    )
                    
                    # Update ParsedProjectsPanel status
                    if self._parsed_panel and project_idx >= 0:
                        if failed == 0:
                            self._parsed_panel.set_project_status(project_idx, "completed")
                            log.info(f"[TabProject] ✅ Project '{project_name}' → completed")
                        else:
                            self._parsed_panel.set_project_status(project_idx, "partial")
                            log.info(
                                f"[TabProject] ⚠️ Project '{project_name}' → partial "
                                f"({failed}/{total} tasks failed)"
                            )
                    
                    # Collect output files from completed tasks
                    completed_tasks = status.get("completed_tasks", [])
                    if completed_tasks and self._parsed_panel and project_idx >= 0:
                        for ct in completed_tasks:
                            best_file = ct.get("best_file", "")
                            if best_file:
                                log.info(
                                    f"[TabProject] 📁 Task {ct['task_id']} output: "
                                    f"{best_file}"
                                )
                    
                    completed_groups.append(group_id)
            except Exception as e:
                log.debug(f"[TabProject] Queue check error for {group_id}: {e}")
        
        # Clean up completed groups
        for gid in completed_groups:
            self._active_group_ids.pop(gid, None)
        
        if completed_groups:
            log.info(
                f"[TabProject] 🔗 Pipeline tracking: {len(completed_groups)} group(s) "
                f"completed, {len(self._active_group_ids)} remaining"
            )
    
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
        self._pipeline_auto_restore_enabled = True
        self._pipeline_persist_epoch = getattr(self, '_pipeline_persist_epoch', 0) + 1
        
        # Restore stage dot colors
        for sn in STAGE_ORDER:
            self._restore_dot_color(sn)
        
        # Highlight current stage
        if current_stage in self._stage_dots:
            self._stage_dots[current_stage].setStyleSheet(
                f"QPushButton {{ background-color: {Theme.BLUE}; color: black; "
                f"border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px; }}"
            )
        
        # Restore viewer content
        card_stages = {"scene_breakdown", "character_gen", "scene_image_gen", "video_gen", "concat"}
        viewer_text = ui_state.get("viewer_text", "")
        if viewer_text and current_stage not in card_stages:
            self._stage_viewer.setMinimumHeight(120)
            self._stage_viewer.setMaximumHeight(16777215)
            self._stage_viewer.setVisible(True)
            self._set_viewer_text(viewer_text)
        else:
            self._show_stage_review(current_stage)
        
        # Update thumbnails for current stage
        self._update_thumbnails(current_stage)
        
        # Enable/disable buttons
        self._sync_buttons("review", current_stage)
        
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
        from services.ai_client_factory import get_ai_config
        cfg = get_ai_config()

        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "gemini-2.5-flash")
        base_url = cfg.get("base_url", "")
        provider = cfg.get("provider", "Google")

        # If no key found, provide a helpful error
        if not api_key:
            source = cfg.get("source", "account")
            if source == "custom":
                raise ValueError(
                    "Chưa có Custom API key!\n"
                    "Vào Settings → AI Prompt Processing → Project Builder để nhập key."
                )
            else:
                raise ValueError(
                    "Chưa có Gemini API key!\n"
                    "Vào Settings → AI Prompt Processing để paste key."
                )

        return api_key, model, base_url, provider

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
        """Clear topics input + parsed projects panel + pipeline viewer."""
        self._topic_input.clear()
        if self._parsed_panel:
            self._parsed_panel.clear_projects()
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._topics_header.setText(t("project_extra.topics_collapsed"))
        self._topics_expanded = True
        self._topics_body.setVisible(True)
        # Also reset pipeline viewer
        self._reset_pipeline_viewer()
    def _on_open_image_library(self):
        """Open image library manager (non-modal, singleton)."""
        if hasattr(self, '_library_popup') and self._library_popup and self._library_popup.isVisible():
            self._library_popup.raise_()
            self._library_popup.activateWindow()
            return
        from ui.popups.complex_popups import ImageManagerPopup
        self._library_popup = ImageManagerPopup(
            self,
            on_select=self._handle_library_select,
            on_use_for_all=self._handle_library_use_for_all,
        )
        self._library_popup.show()

    def _handle_library_select(self, tag: str):
        """Insert [tag] into topic input or stage viewer."""
        target = None
        if hasattr(self, '_stage_viewer') and self._stage_viewer and self._stage_viewer.isVisible():
            target = self._stage_viewer
        elif hasattr(self, '_topic_input') and self._topic_input:
            target = self._topic_input
        if target:
            cursor = target.textCursor()
            cursor.insertText(f"[{tag}] ")
            target.setTextCursor(cursor)

    def _handle_library_use_for_all(self, tag: str):
        """Prepend [tag] to every line in the active text widget."""
        target = None
        if hasattr(self, '_stage_viewer') and self._stage_viewer and self._stage_viewer.isVisible():
            target = self._stage_viewer
        elif hasattr(self, '_topic_input') and self._topic_input:
            target = self._topic_input
        if not target:
            return
        text = target.toPlainText()
        if not text.strip():
            return
        tag_ref = f"[{tag}]"
        lines = text.split("\n")
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                new_lines.append(line)
            elif tag_ref in line:
                new_lines.append(line)
            else:
                new_lines.append(f"{tag_ref} {line}")
        target.setPlainText("\n".join(new_lines))

    def _on_open_find_replace(self):
        """Open Find & Replace dialog via MainWindow."""
        win = self.window()
        if hasattr(win, '_toggle_search'):
            win._toggle_search(replace=True)

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

        # Cleanup previous retry thread if still alive
        if hasattr(self, '_retry_thread') and self._retry_thread is not None:
            try:
                if self._retry_thread.isRunning():
                    self._retry_thread.quit()
                    self._retry_thread.wait(2000)
                self._retry_thread.deleteLater()
            except RuntimeError:
                pass
            self._retry_thread = None
            self._retry_worker = None

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
                self._do_queue_add(prompts, name, project_idx=project_idx)
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

    def _do_queue_add(self, prompts: list, project_name: str, project_idx: int = -1, stage_name: str = ""):
        """Common queue-add logic — routes to T2V or T2I based on combo.
        
        Pipeline tracking: captures group_id from controller and stores it in
        _active_group_ids so queue completion can update pipeline state.
        """
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
                settings["download_quality"] = config.get("video_quality", "720p")
                settings["outputs_per_prompt"] = config.get("video_outputs", 4)
        elif hasattr(self, '_aspect_combo'):
            settings["aspect_ratio"] = "LANDSCAPE" if "Landscape" in self._aspect_combo.currentText() else "PORTRAIT"

        # Route to correct controller method
        method_name = "add_t2i_batch" if output_type == "T2I" else "add_t2v_batch"

        # ★ Credit cost warning gate
        # Scenarios:  Fast+4K → 60/video | Fast+non4K → 10/video | LP+4K → 50/video
        if output_type != "T2I":
            _model = settings.get("model", "")
            _quality = str(settings.get("download_quality", "720p")).lower()
            _is_fast_paid = (
                "Fast" in _model
                and "[LP]" not in _model
                and "Quality" not in _model
            )
            _has_upscale = "4k" in _quality
            _needs_warning = _is_fast_paid or _has_upscale

            if _needs_warning:
                n_prompts = len(prompts)
                n_outputs = settings.get("outputs_per_prompt", 4)
                from config.i18n import t as _t
                from ui.popups.popups import show_credit_warning

                if _is_fast_paid and _has_upscale:
                    cost_per_video = 60
                elif _is_fast_paid:
                    cost_per_video = 10
                else:  # LP + 4K
                    cost_per_video = 50

                total_credits = n_prompts * n_outputs * cost_per_video
                confirmed = show_credit_warning(
                    self, _model, n_prompts, n_outputs, total_credits,
                    cost_per_video=cost_per_video, has_upscale=_has_upscale,
                    confirm_text=_t("generation.credit_warning.confirm"),
                    cancel_text=_t("generation.credit_warning.cancel"),
                )
                if not confirmed:
                    _switched_parts = []
                    # Downgrade model: Fast → LP
                    if _is_fast_paid:
                        lp_name = _model.replace(" - Fast", " - Fast [LP]")
                        settings["model"] = lp_name
                        if self._setup_matrix:
                            idx = self._setup_matrix.video_model.findText(lp_name)
                            if idx >= 0:
                                self._setup_matrix.video_model.setCurrentIndex(idx)
                        _switched_parts.append(f"Model → {lp_name}")
                    # Downgrade quality: 4K → 1080p
                    if _has_upscale:
                        settings["download_quality"] = "1080p"
                        if self._setup_matrix:
                            self._setup_matrix.video_quality.setCurrentText("1080p")
                        _switched_parts.append("Quality → 1080p")
                    main_win = self.window()
                    if hasattr(main_win, 'show_toast') and _switched_parts:
                        main_win.show_toast(f"⬇️ {' | '.join(_switched_parts)}", "info")

        log.info(f"[TabProject] Calling controller.{method_name}() with {len(prompts)} prompts, controller={self.controller is not None}")
        if self.controller and hasattr(self.controller, method_name):
            group_id = getattr(self.controller, method_name)(
                prompts=prompts,
                settings=settings,
            )
            log.info(f"[TabProject] ✅ Successfully added {len(prompts)} prompts to queue as {output_type} (group_id={group_id})")
            
            # ── Pipeline tracking: store group_id for bidirectional sync ──
            if group_id and (project_idx >= 0 or stage_name):
                self._active_group_ids[group_id] = {
                    "project_idx": project_idx,
                    "stage": stage_name,
                    "prompt_count": len(prompts),
                    "project_name": project_name,
                }
                log.info(f"[TabProject] 🔗 Pipeline tracking group_id={group_id} → project_idx={project_idx}, stage={stage_name}")
            
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
        """Save tab state for session persistence.
        
        Includes pipeline ↔ queue tracking data so retry/restart
        can resume pipeline-queue interaction.
        """
        state = {}
        state["pipeline_auto_restore_enabled"] = bool(
            getattr(self, '_pipeline_auto_restore_enabled', True)
        )
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
        
        # ── Pipeline ↔ Queue tracking (Part 1+3: bidirectional sync) ──
        if self._active_group_ids:
            state["active_group_ids"] = dict(self._active_group_ids)
        
        # ── Pipeline stage queue polling (stages 5-7 resume on restart) ──
        poll_gid = getattr(self, '_queue_poll_group_id', None)
        poll_stage = getattr(self, '_queue_poll_stage', None)
        if poll_gid and poll_stage:
            state["queue_poll"] = {
                "group_id": poll_gid,
                "stage": poll_stage,
            }
        
        # ── Parsed projects data (Part 4: persist across restart) ──
        if self._parsed_panel and hasattr(self._parsed_panel, '_projects'):
            projects_save = []
            for i, row in enumerate(self._parsed_panel._projects):
                proj_data = {}
                if i < len(self._parsed_panel._project_data):
                    proj_data = self._parsed_panel._project_data[i]
                projects_save.append({
                    "name": row.name,
                    "status": row.get_status(),
                    "files": proj_data,
                })
            if projects_save:
                state["parsed_projects"] = projects_save
        
        return state

    def restore_state(self, data: dict, restore_options=None):
        """Restore tab state from saved session data.
        
        Includes pipeline ↔ queue tracking and parsed projects.
        """
        if not data:
            return
        self._pipeline_auto_restore_enabled = bool(
            data.get("pipeline_auto_restore_enabled", True)
        )
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
            
            # ── Restore pipeline ↔ queue tracking (Part 1+3) ──
            saved_groups = data.get("active_group_ids", {})
            if saved_groups:
                self._active_group_ids = dict(saved_groups)
                log.info(f"[TabProject] Restored {len(saved_groups)} active group_ids for pipeline tracking")
                # Re-register queue callback if controller available
                if self.controller:
                    self._register_queue_callback()
            
            # ── Restore pipeline stage queue polling (stages 5-7) ──
            poll_data = data.get("queue_poll")
            if poll_data and self.controller:
                gid = poll_data.get("group_id", "")
                stage = poll_data.get("stage", "")
                if gid and stage:
                    # Check if group is still in-progress
                    try:
                        status = self.controller.get_group_status(gid)
                        if status and not status.get("is_done"):
                            log.info(f"[TabProject] ♻️ Resuming queue polling: group={gid}, stage={stage}")
                            self._start_queue_polling(gid, stage)
                        elif status and status.get("is_done"):
                            log.info(f"[TabProject] Queue group {gid} already done — skipping poll resume")
                            # Immediately handle completion
                            self._on_queue_group_complete(stage, status)
                        else:
                            log.info(f"[TabProject] Queue group {gid} not found — poll data stale")
                    except Exception as e:
                        log.debug(f"[TabProject] Poll restore check failed: {e}")
            
            # ── Restore parsed projects (Part 4) ──
            saved_projects = data.get("parsed_projects", [])
            if saved_projects and self._parsed_panel:
                self._parsed_panel.clear_projects()
                for proj in saved_projects:
                    name = proj.get("name", "")
                    files = proj.get("files", {})
                    status = proj.get("status", "ready")
                    self._parsed_panel.add_project(name, files, status)
                log.info(f"[TabProject] Restored {len(saved_projects)} parsed projects from session")
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

