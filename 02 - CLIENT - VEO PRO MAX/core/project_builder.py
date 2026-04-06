"""
VEO Pro Max - Project Builder

Orchestrates AI-powered VEO project generation:
1. Topic analysis + auto-detect template
2. Per-topic fresh context reload (no cross-contamination)
3. Multi-step Gemini API pipeline: Research → Bible → Prompts → SEO
4. Post-processing: parse, validate, suffix/prefix
5. Deduplication: exact + fuzzy + history

Supports Semi-Manual mode (no API) and Full Auto mode.
"""

import re
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Any
from datetime import datetime

from core.data_loader import load_text, scan_data_files

log = logging.getLogger("veo.builder")


# ── Data Classes ───────────────────────────────────────────────


@dataclass
class PromptRow:
    """A single parsed prompt row."""
    index: int
    prompt: str
    scene_description: str = ""
    style_prefix: str = ""
    negative_suffix: str = ""
    valid: bool = True
    violations: List[str] = field(default_factory=list)


@dataclass
class TopicResult:
    """Result of processing a single topic."""
    topic: str
    template_id: str = ""
    template_name: str = ""
    status: str = "pending"  # pending, processing, done, error
    research: str = ""
    bible: str = ""
    master: str = ""
    dubbing: str = ""
    seo: str = ""
    prompts: List[PromptRow] = field(default_factory=list)
    error: str = ""
    tokens_used: int = 0
    steps_completed: int = 0
    steps_total: int = 4  # Research, Bible, Prompts, SEO
    files: Dict[str, str] = field(default_factory=dict)  # {"Bible": content, ...}


@dataclass
class DedupResult:
    """Result of deduplication check."""
    status: str = "ok"  # ok, warning, block
    reason: str = ""
    similar_topic: str = ""
    similarity: float = 0.0


# ── Dedup Checker ──────────────────────────────────────────────


class DedupChecker:
    """3-layer deduplication: exact, fuzzy (batch), history (cross-session).
    
    Fix #6: Thresholds configurable via constructor.
    Fix #9: History limit configurable.
    """

    HISTORY_FILE = Path.home() / ".veoauto" / "project_history.json"

    def __init__(self, fuzzy_threshold: float = 0.85,
                 history_threshold: float = 0.80,
                 history_limit: int = 500):
        self._batch_topics: List[str] = []
        self.fuzzy_threshold = fuzzy_threshold
        self.history_threshold = history_threshold
        self.history_limit = history_limit

    def check_all(self, topic: str) -> DedupResult:
        """Run all 3 dedup layers."""
        # Layer 1: Exact match in current batch
        normalized = self._normalize(topic)
        topic_hash = self._topic_hash(topic)
        for existing in self._batch_topics:
            if self._normalize(existing) == normalized or self._topic_hash(existing) == topic_hash:
                return DedupResult(
                    status="block",
                    reason="Exact duplicate in current batch",
                    similar_topic=existing,
                    similarity=1.0,
                )

        # Layer 2: Fuzzy match in current batch
        for existing in self._batch_topics:
            sim = self._jaccard(topic, existing)
            if sim >= self.fuzzy_threshold:
                # Bug 6 fix: still add to batch so future topics can detect this one
                self._batch_topics.append(topic)
                return DedupResult(
                    status="warning",
                    reason=f"Similar topic in batch ({sim:.0%})",
                    similar_topic=existing,
                    similarity=sim,
                )

        # Layer 3: History check
        history = self._load_history()
        for entry in history:
            sim = self._jaccard(topic, entry.get("topic", ""))
            if sim >= self.history_threshold:
                # Bug 6 fix: still add to batch so future topics can detect this one
                self._batch_topics.append(topic)
                return DedupResult(
                    status="warning",
                    reason=f"Similar to previous project ({sim:.0%})",
                    similar_topic=entry.get("topic", ""),
                    similarity=sim,
                )

        # Add to batch (Bug 6 fix: also add warning topics to prevent cascading)
        self._batch_topics.append(topic)
        return DedupResult(status="ok")

    def save_to_history(
        self, topic: str, template_id: str, output_dir: str
    ) -> None:
        """Save completed topic to history."""
        history = self._load_history()
        history.append({
            "topic": topic,
            "template_id": template_id,
            "output_dir": output_dir,
            "date": datetime.now().isoformat(),
        })
        # Keep last 500 entries
        history = history[-self.history_limit:]
        self.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    def _load_history(self) -> List[Dict]:
        if self.HISTORY_FILE.exists():
            try:
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'\s+', ' ', text.lower().strip())

    @staticmethod
    def _jaccard(a: str, b: str) -> float:
        """Jaccard similarity between two texts."""
        words_a = set(re.findall(r'\w+', a.lower()))
        words_b = set(re.findall(r'\w+', b.lower()))
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @staticmethod
    def _topic_hash(text: str) -> str:
        """Normalized hash for near-exact dedup. Strips punctuation, lowercases, sorts words."""
        import hashlib
        words = sorted(re.findall(r'\w+', text.lower()))
        return hashlib.md5(" ".join(words).encode()).hexdigest()[:12]


# ── Context Manager ────────────────────────────────────────────


class ContextManager:
    """Assemble system prompts for each step of topic processing.

    Each topic gets a FRESH context — no cross-topic contamination.
    Injects matrix config dimensions and workflow rules into prompts.
    """

    def __init__(self):
        self._workflow_cache: Dict[str, str] = {}

    def _load_workflow_rules(self) -> str:
        """Load content-video.md workflow rules (cached)."""
        if "content-video" not in self._workflow_cache:
            wf_path = Path(__file__).parent.parent / "data" / "workflows" / "content-video.md"
            try:
                content = load_text(wf_path)
                self._workflow_cache["content-video"] = content
            except (FileNotFoundError, Exception):
                self._workflow_cache["content-video"] = ""
        return self._workflow_cache["content-video"]

    def _load_research_data(self) -> str:
        """Load research data (trending keywords, sensitive words, etc.) — cached."""
        if "research" not in self._workflow_cache:
            research_dir = Path(__file__).parent.parent / "data" / "workflows" / "01_Research"
            parts = []
            if research_dir.exists():
                for f in sorted(scan_data_files(research_dir, recursive=False)):
                    try:
                        content = load_text(f)
                        # Limit each file to ~4000 chars to manage token budget
                        parts.append(f"## {f.stem}\n{content[:4000]}")
                    except Exception:
                        pass
            self._workflow_cache["research"] = "\n\n".join(parts)
        return self._workflow_cache["research"]

    def _build_matrix_context(self, matrix_config: Dict) -> str:
        """Build context section from Setup Matrix dimensions."""
        if not matrix_config:
            return ""
        parts = ["# SETUP MATRIX (User-selected parameters)"]
        dim_map = {
            "category":  "Category",
            "structure": "Structure",
            "style":     "Visual Style",
            "character": "Character Type",
            "audience":  "Target Audience",
            "persona":   "Director Persona",
            "tone":      "Tone",
            "voice":     "Voice Region",
            "camera_technique": "Camera Technique",
        }
        for key, label in dim_map.items():
            val = matrix_config.get(key)
            if val:
                if isinstance(val, list):
                    val = ", ".join(val)
                parts.append(f"- {label}: {val}")
        return "\n".join(parts)

    def build_context(
        self,
        step: str,
        topic: str,
        template_body: str,
        rules_text: str,
        previous_output: str = "",
        matrix_config: Optional[Dict] = None,
        prompt_format: str = "text",
        scene_count: int = 0,
        clip_duration: int = 8,
    ) -> str:
        """Build system prompt for a processing step.

        Args:
            step: "Research", "Bible", "Prompts", "Fix", "SEO"
            topic: Current topic text.
            template_body: Template content.
            rules_text: Combined rules content.
            previous_output: Output from previous step.
            matrix_config: Setup Matrix dimensions from UI.

        Returns:
            (system_prompt, user_instruction) tuple.
        """
        parts = [
            f"# PRODUCTION TEMPLATE\n{template_body}",
            f"\n# PRODUCTION RULES\n{rules_text}" if rules_text else "",
        ]

        # Inject matrix config dimensions
        matrix_ctx = self._build_matrix_context(matrix_config)
        if matrix_ctx:
            parts.append(f"\n{matrix_ctx}")

        # Inject workflow rules for ALL steps (phased)
        wf_rules = self._load_workflow_rules()
        if wf_rules:
            phase_map = {
                "Research": "PHASE 2: RESEARCH",
                "Bible":   "PHASE 3: BIBLE CREATION",
                "Prompts": "PHASE 4: MASTER SCRIPT",
                "Fix":     "PHASE 5: PROMPTS EXTRACTION",
                "SEO":     "PHASE 7: SEO",
            }
            phase_key = phase_map.get(step, "")
            relevant = self._extract_phase(wf_rules, phase_key)
            if relevant:
                parts.append(f"\n# WORKFLOW RULES ({step})\n{relevant}")

        # Inject research data for Research and SEO steps
        if step in ("Research", "SEO"):
            research = self._load_research_data()
            if research:
                parts.append(f"\n# RESEARCH DATA\n{research}")

        if previous_output:
            parts.append(f"\n# PREVIOUS STEP OUTPUT\n{previous_output}")

        system = "\n\n".join(p for p in parts if p)

        # Step-specific user instructions
        # Determine style/tone from matrix for richer instructions
        style = ""
        tone = ""
        if matrix_config:
            style_list = matrix_config.get("style", [])
            style = style_list[0] if style_list else ""
            tone_list = matrix_config.get("tone", [])
            tone = tone_list[0] if tone_list else ""

        instructions = {
            "Research": (
                f"Research the topic: \"{topic}\"\n\n"
                "Provide scientific data, key facts, statistics, and important "
                "information. Focus on accuracy and relevance for video content."
            ),
            "Bible": (
                f"Generate a Production Bible for topic: \"{topic}\"\n\n"
                "Include: Character descriptions with CHARACTER PROFILE LOCK "
                "(8 mandatory fields: age+role, height, skin+detail, face, hair, "
                "clothing top, clothing bottom, accessories).\n"
                "Include: HEX color + text description for ALL colors.\n"
                "Include: Setting details, visual style guidelines, scene breakdowns.\n"
                "Include: CHARACTER IMAGE PROMPT for each character.\n"
                f"Visual style: {style or 'as specified in template'}\n"
                f"Tone: {tone or 'as specified in template'}"
            ),
            "Prompts": (
                f"Generate VEO video prompts for topic: \"{topic}\"\n\n"
                "CRITICAL RULES:\n"
                "- One prompt per line, BLANK LINE between prompts\n"
                + (f"- EXACTLY {scene_count} prompts required (1 prompt = 1 VEO clip of {clip_duration}s, total {scene_count * clip_duration}s)\n\n"
                   if scene_count > 0
                   else "- 10-12 prompts preferred\n\n"
                ) +
                "FORMAT CONVENTION:\n"
                "- Use () for metadata: (N SEG), (Giọng: region, age)\n"
                "- Use [] ONLY for character name tags: [Mẹ Năm], [Bé Na]\n"
                "- Do NOT use [] for metadata or () for character names\n\n"
                "CHARACTER PROFILE LOCK — 8 MANDATORY FIELDS in EVERY scene:\n"
                "1. Age + Role (e.g. 45-year-old Vietnamese mother)\n"
                "2. Height (e.g. 1.57m)\n"
                "3. Skin + detail (e.g. warm golden tan sun-kissed skin)\n"
                "4. Face (e.g. round warm face with laugh lines)\n"
                "5. Hair (e.g. deep dark chocolate brown shoulder-length hair in bun)\n"
                "6. Clothing top (e.g. vivid tomato red floral apron over white tee)\n"
                "7. Clothing bottom (e.g. soft matte black loose cotton pants)\n"
                "8. Accessories (e.g. warm earthy brown house sandals, gold wedding band)\n"
                "ANTI-DECAY: Copy ALL 8 fields identically to EVERY scene. "
                "Never write 'same character' — always repeat full description.\n\n"
                "MULTI-SEGMENT (>>) — at least 3 prompts must use >>:\n"
                "- Hook: 2-3 SEG required\n"
                "- Teaching/Tips: 2-3 SEG when multi-step demo\n"
                "- Each SEG MUST have dialogue: (Giọng: region, age) \"Lời thoại...\"\n"
                "- Speaker: mouth open speaking indicator\n"
                "- Listener: listening/attentive expression\n\n"
                "NEGATIVE PROMPTS — append to EVERY prompt:\n"
                "no deformed limbs, no mutated faces, no extra fingers, "
                "no melting geometry, no color shifts, no texture distortion\n"
                "SUFFIX: no text, no subtitles, no labels, no watermarks\n\n"
                "CAMERA DIRECTION — Match camera movement to each scene's emotion:\n"
                "Available techniques: Forward, Backward, Left-to-Right, Right-to-Left, "
                "Up, Down, Dolly In+Zoom Out (Vertigo), Dolly Out+Zoom In, "
                "Stationary, Pan Left/Right, Tilt Up/Down, Push Forward, Pull Backward.\n"
                "Include camera direction in EVERY prompt, e.g.: "
                "'camera slowly pushes forward revealing...', "
                "'stationary shot, camera fixed on...', "
                "'dolly zoom creating vertigo effect as...'\n\n"
                "Use TEXT descriptions ONLY (NO HEX colors in prompts)."
            ),
            "Prompts_json": (
                f"Generate VEO video prompts for topic: \"{topic}\"\n\n"
                "OUTPUT FORMAT: JSON ARRAY\n"
                "Output ONLY a valid JSON array. Each element MUST have ALL these fields:\n"
                '{\n'
                '  "scene_index": 1,\n'
                '  "scene_type": "establishing|dialogue|action|transition|montage|text_overlay|closing",\n'
                '  "type": "solo|duo|group|landscape|text_overlay",\n'
                '  "shot_type": "wide shot|medium shot|close-up|extreme close-up|establishing shot|aerial shot",\n'
                '  "camera_movement": "static|slow dolly in|dolly out|pan left|pan right|tilt up|tilt down|zoom in|tracking shot|orbit",\n'
                '  "setting": "description of location/environment",\n'
                '  "characters": ["CharName1", "CharName2"],\n'
                '  "character_actions": {"CharName1": "action description", "CharName2": "action description"},\n'
                '  "character_emotions": {"CharName1": "emotion", "CharName2": "emotion"},\n'
                '  "props": ["important objects in scene"],\n'
                '  "audio_cue": "ambient sound or music description",\n'
                '  "tone": "emotional tone of the scene",\n'
                '  "has_text_overlay": false,\n'
                '  "text_overlay_content": null,\n'
                + (f'  "duration_s": {clip_duration},\n' if clip_duration else '  "duration_s": 8,\n') +
                '  "negative_prompt": "no text, no subtitles, no labels, no watermarks, no deformed limbs, no mutated faces, no extra fingers",\n'
                '  "prompt_text": "Full VEO video prompt in English with [CharName] tags, camera direction, style, and negative suffix"\n'
                '}\n\n'
                "RULES:\n"
                + (f"- EXACTLY {scene_count} scenes required (1 scene = 1 VEO clip of {clip_duration}s, total {scene_count * clip_duration}s)\n"
                   if scene_count > 0
                   else "- 10-12 scenes preferred\n"
                ) +
                "- prompt_text must be the FULL detailed VEO video prompt in English\n"
                "- prompt_text MUST include [CharName] tags for all characters in scene\n"
                "- prompt_text MUST include CHARACTER PROFILE LOCK (8 fields) for EVERY character in EVERY scene\n"
                "- prompt_text MUST end with negative suffix: no text, no subtitles, no labels, no watermarks\n"
                "- characters[] must list character names present in the scene\n"
                "- type is auto-determined: solo (1 char), duo (2), group (3+), landscape (0), text_overlay\n"
                "- scene_type describes narrative function: establishing, dialogue, action, etc.\n"
                "- Output ONLY the JSON array, no markdown fences, no explanation"
            ),
            "Fix": (
                "The following prompts were BLOCKED by safety filters.\n"
                "Rewrite them to convey the same visual concept without any "
                "policy violations. Keep Character Profile Lock intact.\n"
                "Output ONLY the fixed prompts."
            ),
            "SEO": (
                f"Generate SEO content for topic: \"{topic}\"\n\n"
                "Provide:\n- Title (attention-grabbing, <60 chars)\n"
                "- Description (100-150 words)\n"
                "- Hashtags (10-15 with view counts)\n"
                "- YouTube Tags (<500 chars)\n"
                "- Thumbnail Text (3-4 shock words)\n"
                "- Disclaimer if health-related"
            ),
        }

        # For Prompts step, select text or JSON variant
        step_key = step
        if step == "Prompts" and prompt_format == "json":
            step_key = "Prompts_json"

        return system, instructions.get(step_key, instructions.get(step, f"Process: {topic}"))

    def _extract_phase(self, full_workflow: str, phase_key: str) -> str:
        """Extract a specific phase section + compliance checklist from workflow."""
        result = []
        # Extract the specific phase
        if phase_key and phase_key in full_workflow:
            start = full_workflow.index(phase_key)
            # Find next phase or end
            next_phase = full_workflow.find("### PHASE", start + len(phase_key))
            if next_phase > 0:
                result.append(full_workflow[start:next_phase].strip())
            else:
                result.append(full_workflow[start:start+3000].strip())

        # Always include compliance checklist (compact)
        checklist_key = "QUICK COMPLIANCE CHECKLIST"
        if checklist_key in full_workflow:
            cl_start = full_workflow.index(checklist_key)
            cl_end = full_workflow.find("---", cl_start + 10)
            if cl_end > 0:
                result.append(full_workflow[cl_start:cl_end].strip())

        return "\n\n".join(result) if result else ""


# ── Token / Temperature Per Step (model comes from Settings) ──

STEP_MODEL_CONFIG = {
    "Research": {"max_tokens": 4096,  "temperature": 0.7},
    "Bible":    {"max_tokens": 16384, "temperature": 0.7},
    "Prompts":  {"max_tokens": 16384, "temperature": 0.5},
    "Fix":      {"max_tokens": 4096,  "temperature": 0.3},
    "SEO":      {"max_tokens": 2048,  "temperature": 0.7},
}


# ── Project Builder ────────────────────────────────────────────


class ProjectBuilder:
    """Main orchestrator for AI-powered project generation.

    Usage:
        builder = ProjectBuilder(gemini_client, scanner, rules_loader)
        result = await builder.process_topic("Tác hại ăn mì tôm", template)
    """

    def __init__(self, gemini_client=None, scanner=None, rules_loader=None):
        self.client = gemini_client
        self.scanner = scanner
        self.rules_loader = rules_loader
        self.context_mgr = ContextManager()
        self.dedup = DedupChecker()
        self._cancelled = False  # Fix #1: Cancel support

        # Callbacks for UI progress updates
        self.on_step_start: Optional[Callable] = None
        self.on_step_done: Optional[Callable] = None
        self.on_topic_done: Optional[Callable] = None

    def cancel(self):
        """Request cancellation of the current generation."""
        self._cancelled = True
        log.info("[Builder] Cancellation requested")

    def _check_cancelled(self):
        """Raise if cancelled."""
        if self._cancelled:
            raise InterruptedError("Generation cancelled by user")

    async def process_topic(
        self,
        topic: str,
        template,
        api_key: str,
        output_dir: str = "",
        skip_seo: bool = False,
        skip_research: bool = False,
        skip_bible: bool = False,
        matrix_config: Optional[Dict] = None,
        model: str = "",
        prompt_format: str = "text",
        step_config: Optional[Dict] = None,
    ) -> TopicResult:
        """Process a single topic through the full pipeline.

        Args:
            topic: Topic text.
            template: WorkflowTemplate instance.
            api_key: Gemini API key.
            output_dir: Output directory for files.
            skip_seo: Skip SEO generation step.
            skip_research: Skip Research step (Fix #4).
            skip_bible: Skip Bible step (Fix #4).
            step_config: Override STEP_MODEL_CONFIG per step (Fix #5).

        Returns:
            TopicResult with all generated content.
        """
        result = TopicResult(
            topic=topic,
            template_id=template.template_id,
            template_name=template.display_name,
        )

        try:
            result.status = "processing"
            self._model = model  # Store for _safe_generate calls
            _cfg = step_config or {}  # Fix #5: user overrides

            # Load rules for this template
            rules_text = ""
            if self.rules_loader:
                rules_text, _ = self.rules_loader.load_for_template(
                    template.shared_rules,
                    template.advanced_rules,
                )

            # ── Step 1: Research (skippable — Fix #4) ──
            self._check_cancelled()
            research = ""
            if not skip_research:
                step_cfg = {**STEP_MODEL_CONFIG["Research"], **_cfg.get("Research", {})}
                self._emit("Research", topic, 1)
                system, user_prompt = self.context_mgr.build_context(
                    "Research", topic, template.body, rules_text,
                    matrix_config=matrix_config,
                )
                research = await self._safe_generate(
                    prompt=user_prompt,
                    system=system,
                    api_key=api_key,
                    max_tokens=step_cfg["max_tokens"],
                    temperature=step_cfg["temperature"],
                    model=self._model,
                )
            result.research = research
            result.steps_completed = 1

            # ── Step 2: Bible Generation (skippable — Fix #4) ──
            self._check_cancelled()
            bible = ""
            if not skip_bible:
                step_cfg = {**STEP_MODEL_CONFIG["Bible"], **_cfg.get("Bible", {})}
                self._emit("Bible", topic, 2)
                system, user_prompt = self.context_mgr.build_context(
                    "Bible", topic, template.body, rules_text,
                    previous_output=research,
                    matrix_config=matrix_config,
                )
                bible = await self._safe_generate(
                    prompt=user_prompt,
                    system=system,
                    api_key=api_key,
                    max_tokens=step_cfg["max_tokens"],
                    temperature=step_cfg["temperature"],
                    model=self._model,
                )
            result.bible = bible
            result.steps_completed = 2

            # ── Step 3: Prompt Generation ──
            self._check_cancelled()
            step_cfg = {**STEP_MODEL_CONFIG["Prompts"], **_cfg.get("Prompts", {})}
            self._emit("Prompts", topic, 3)
            system, user_prompt = self.context_mgr.build_context(
                "Prompts", topic, template.body, rules_text,
                previous_output=bible,
                matrix_config=matrix_config,
                prompt_format=prompt_format,
            )
            raw_prompts = await self._safe_generate(
                prompt=user_prompt,
                system=system,
                api_key=api_key,
                max_tokens=step_cfg["max_tokens"],
                temperature=step_cfg["temperature"],
                model=self._model,
            )
            result.prompts = self._parse_prompts(raw_prompts, template,
                                                  prompt_format=prompt_format)
            result.steps_completed = 3

            # ── Step 3b: Validate & Auto-Fix ──
            from core.prompt_validator import validate_prompts
            validate_prompts(
                result.prompts,
                expected_count=getattr(template, 'scene_count', 0),
                prompt_format=prompt_format,
                rules_loader=self.rules_loader,
            )
            has_violations = any(not p.valid for p in result.prompts)
            if has_violations and self.client:
                log.info(f"[Builder] Validation found violations — auto-fixing")
                self._emit("Fix", topic, 3)
                violated_text = "\n".join(
                    f"{p.index}. {p.prompt} [VIOLATIONS: {', '.join(p.violations)}]"
                    for p in result.prompts if not p.valid
                )
                fix_cfg = STEP_MODEL_CONFIG["Fix"]
                system, user_prompt = self.context_mgr.build_context(
                    "Fix", topic, template.body, rules_text,
                    previous_output=violated_text,
                    matrix_config=matrix_config,
                )
                fixed_raw = await self._safe_generate(
                    prompt=user_prompt,
                    system=system,
                    api_key=api_key,
                    max_tokens=fix_cfg["max_tokens"],
                    temperature=fix_cfg["temperature"],
                    model=self._model,
                )
                fixed_prompts = self._parse_prompts(fixed_raw, template,
                                                  prompt_format=prompt_format)
                # Merge fixed prompts back (replace violated ones)
                fixed_map = {p.index: p for p in fixed_prompts}
                for p in result.prompts:
                    if not p.valid and p.index in fixed_map:
                        p.prompt = fixed_map[p.index].prompt
                        p.valid = True
                        p.violations = []

            # ── Step 4: SEO (optional — Fix #12 UI toggle) ──
            self._check_cancelled()
            if not skip_seo:
                seo_cfg = {**STEP_MODEL_CONFIG["SEO"], **_cfg.get("SEO", {})}
                self._emit("SEO", topic, 4)
                system, user_prompt = self.context_mgr.build_context(
                    "SEO", topic, template.body, "",
                    matrix_config=matrix_config,
                )
                seo = await self._safe_generate(
                    prompt=user_prompt,
                    system=system,
                    api_key=api_key,
                    max_tokens=seo_cfg["max_tokens"],
                    temperature=seo_cfg["temperature"],
                    model=self._model,
                )
                result.seo = seo
                result.steps_completed = 4

            # Build master + dubbing from prompts + bible
            result.master = self._build_master(result)
            result.dubbing = self._build_dubbing(result)

            # Populate files dict for ParsedProjectsPanel
            result.files = {
                "Bible":   result.bible,
                "Master":  result.master,
                "Dubbing": result.dubbing,
                "SEO":     result.seo,
            }

            # ── Step 5: Format prompts for files dict ──
            if prompt_format == "json":
                # JSON output: full structured data
                json_prompts = []
                for p in result.prompts:
                    try:
                        scene = json.loads(p.prompt)
                        json_prompts.append(scene)
                    except (json.JSONDecodeError, ValueError):
                        json_prompts.append({"scene_index": p.index, "prompt_text": p.prompt})
                result.files["Prompts"] = json.dumps(json_prompts, ensure_ascii=False, indent=2)
            else:
                result.files["Prompts"] = "\n".join(
                    f"{p.index}. {p.prompt}" for p in result.prompts
                )

            # Save to history
            self.dedup.save_to_history(topic, template.template_id, output_dir)

            # Save output files (Bug 3 fix: pass prompt_format)
            if output_dir:
                self._save_outputs(result, output_dir, prompt_format=prompt_format)

            result.status = "done"

        except Exception as e:
            result.status = "cancelled" if isinstance(e, InterruptedError) else "error"
            result.error = str(e)
            log.error(f"[Builder] Failed processing '{topic}': {e}")

        if self.on_topic_done:
            self.on_topic_done(result)

        return result

    async def process_batch(
        self,
        topics: List[str],
        template,
        api_key: str,
        output_base: str = "",
        skip_seo: bool = False,
        skip_research: bool = False,
        skip_bible: bool = False,
        model: str = "",
        matrix_config: Optional[Dict] = None,
        prompt_format: str = "text",
        step_config: Optional[Dict] = None,
        per_topic_template: bool = False,
        max_concurrent: int = 1,
    ) -> List[TopicResult]:
        """Process multiple topics sequentially with fresh context per topic.
        
        Fix #2: per_topic_template=True → auto-detect template for EACH topic.
        Fix #4: skip_research/skip_bible → skip those pipeline steps.
        """
        results = []
        if max_concurrent > 1 and len(topics) > 1:
            return await self._process_batch_concurrent(
                topics, template, api_key, output_base, skip_seo,
                skip_research, skip_bible, model, matrix_config,
                prompt_format, step_config, per_topic_template, max_concurrent,
            )
        for i, topic in enumerate(topics):
            if self._cancelled:
                break
            topic = topic.strip()
            # Extract topic from tab-separated data (topic = longest column)
            if "\t" in topic:
                parts = [p.strip() for p in topic.split("\t") if p.strip()]
                topic = max(parts, key=len) if parts else topic
            if not topic:
                continue

            log.info(f"[Builder] Processing {i+1}/{len(topics)}: {topic}")

            # Dedup check
            dedup = self.dedup.check_all(topic)
            if dedup.status == "block":
                results.append(TopicResult(
                    topic=topic,
                    status="error",
                    error=f"Blocked: {dedup.reason}",
                ))
                continue

            # Fresh context per topic (discard previous)
            output_dir = ""
            if output_base:
                # Topics may contain tab-separated columns from auto-detect
                # (e.g. "Topic\tHoạt hình\tThực phẩm\tChỉ dạy")
                # → take only the first column (actual topic name)
                topic_name = topic.split("\t")[0].strip()
                # Remove Windows-illegal chars: \ / : * ? " < > |
                safe_name = re.sub(r'[\\/:*?"<>|\t\n\r]', '', topic_name)
                safe_name = re.sub(r'\s+', ' ', safe_name).strip()
                if len(safe_name) > 50:
                    import hashlib
                    suffix = hashlib.sha1(topic_name.encode()).hexdigest()[:6]
                    safe_name = f"{safe_name[:50]}_{suffix}"
                output_dir = str(Path(output_base) / safe_name)

            # Fix #2: Per-topic template detection
            topic_template = template
            if per_topic_template and self.scanner:
                topic_name = topic.split("\t")[0].strip() if "\t" in topic else topic
                matches = self.scanner.detect_mode(topic_name)
                if matches:
                    topic_template = matches[0].template
                    log.info(f"[Builder] Topic '{topic_name[:30]}' → template '{topic_template.display_name}'")

            result = await self.process_topic(
                topic, topic_template, api_key, output_dir, skip_seo,
                skip_research=skip_research,
                skip_bible=skip_bible,
                model=model,
                matrix_config=matrix_config,
                prompt_format=prompt_format,
                step_config=step_config,
            )
            results.append(result)

        return results

    # ── Concurrent Batch Processing ─────────────────────────────

    async def _process_batch_concurrent(
        self, topics, template, api_key, output_base, skip_seo,
        skip_research, skip_bible, model, matrix_config,
        prompt_format, step_config, per_topic_template, max_concurrent,
    ) -> List[TopicResult]:
        """Process batch with bounded concurrency via asyncio.Semaphore."""
        import asyncio
        sem = asyncio.Semaphore(max_concurrent)
        slots = [None] * len(topics)

        async def _run(idx, raw):
            if self._cancelled:
                return
            raw = raw.strip()
            if "\t" in raw:
                parts = [p.strip() for p in raw.split("\t") if p.strip()]
                raw = max(parts, key=len) if parts else raw
            if not raw:
                return
            dd = self.dedup.check_all(raw)
            if dd.status == "block":
                slots[idx] = TopicResult(topic=raw, status="error", error=f"Blocked: {dd.reason}")
                return
            od = ""
            if output_base:
                tn = raw.split("\t")[0].strip()
                sn = re.sub(r'[\\/:\*?"<>|\t\n\r]', '', tn)
                sn = re.sub(r'\s+', ' ', sn).strip()
                if len(sn) > 50:
                    import hashlib
                    sn = f"{sn[:50]}_{hashlib.sha1(tn.encode()).hexdigest()[:6]}"
                od = str(Path(output_base) / sn)
            tt = template
            if per_topic_template and self.scanner:
                tname = raw.split("\t")[0].strip() if "\t" in raw else raw
                m = self.scanner.detect_mode(tname)
                if m:
                    tt = m[0].template
            async with sem:
                log.info(f"[Builder] {idx+1}/{len(topics)} (parallel x{max_concurrent}): {raw[:50]}")
                slots[idx] = await self.process_topic(
                    raw, tt, api_key, od, skip_seo,
                    skip_research=skip_research, skip_bible=skip_bible,
                    model=model, matrix_config=matrix_config,
                    prompt_format=prompt_format, step_config=step_config,
                )

        await asyncio.gather(*[_run(i, t) for i, t in enumerate(topics)], return_exceptions=True)
        return [r for r in slots if r is not None]

    # ── Semi-Manual Mode ───────────────────────────────────────

    def import_prompts(self, raw_text: str, template) -> List[PromptRow]:
        """Parse manually pasted/imported prompts (no API needed).

        Args:
            raw_text: Raw prompt text (one per line or numbered).
            template: WorkflowTemplate for post-processing.

        Returns:
            List of parsed and post-processed PromptRow.
        """
        return self._parse_prompts(raw_text, template)

    # ── Prompt Parsing & Post-processing ───────────────────────

    def _parse_prompts(self, raw: str, template,
                        prompt_format: str = "text") -> List[PromptRow]:
        """Parse raw text into PromptRow list with post-processing."""
        # JSON format: try parsing as JSON array first
        if prompt_format == "json":
            parsed = self._try_parse_json_prompts(raw, template)
            if parsed:
                return parsed
            log.warning("[Builder] JSON parse failed, falling back to text mode")

        lines = raw.strip().split("\n")
        prompts = []
        idx = 0

        # Get negative suffix from template (e.g. "no text, no watermark")
        negative_suffix = ""
        if template and hasattr(template, 'negative_suffix'):
            negative_suffix = getattr(template, 'negative_suffix', '') or ''

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove numbering: "1. " or "1) " or "Scene 1:"
            cleaned = re.sub(r'^(\d+[\.\)]\s*|Scene\s+\d+:\s*)', '', line).strip()
            if not cleaned:
                continue

            idx += 1
            prompt_text = cleaned

            # Apply visual style prefix (Fix 4a)
            style_prefix = ""
            if template and template.visual_style:
                style_prefix = template.visual_style
                prompt_text = f"{template.visual_style}, {prompt_text}"

            # Apply negative suffix (Fix 4b)
            if negative_suffix:
                prompt_text = f"{prompt_text}. {negative_suffix}"

            row = PromptRow(
                index=idx,
                prompt=prompt_text,
                style_prefix=style_prefix,
                negative_suffix=negative_suffix,
            )
            prompts.append(row)

        return prompts

    def _try_parse_json_prompts(self, raw: str, template) -> Optional[List[PromptRow]]:
        """Try parsing AI output as JSON prompt object(s) into PromptRow list.
        
        Supports legacy and current formats such as:
        - scene_number + prompt_en
        - scene_index + prompt_text
        - prompt / text fallback keys from imported JSON prompts
        - nested analysis JSON that needs synthesized prompt_text fallback
        """
        try:
            # Strip markdown fences if AI wrapped in ```json ... ```
            text = raw.strip()
            if text.startswith('```'):
                text = re.sub(r'^```(?:json)?\s*', '', text)
                text = re.sub(r'```\s*$', '', text)
                text = text.strip()

            # Sanitize: handle [tag] prefix, concatenated arrays, bare objects
            from core.batch_parser import BatchParser
            text = BatchParser._sanitize_json_text(text)

            data = json.loads(text)
            if isinstance(data, dict):
                data = [data]

            if not isinstance(data, list):
                return None

            prompts = []
            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    continue

                item = BatchParser._unwrap_single_key_scene(item)
                
                # Support both old and new field names
                scene_idx = item.get('scene_index', item.get('scene_number', i + 1))
                prompt_text, _ = BatchParser._extract_prompt_from_scene(item)
                if not prompt_text:
                    continue
                
                # Build a normalized JSON object with all schema fields
                normalized = {
                    "scene_index": scene_idx,
                    "scene_type": item.get('scene_type', 'action'),
                    "type": item.get('type', 'landscape'),
                    "shot_type": item.get('shot_type', 'medium shot'),
                    "camera_movement": item.get('camera_movement', 'static'),
                    "setting": item.get('setting', ''),
                    "characters": item.get('characters', []),
                    "character_actions": item.get('character_actions', {}),
                    "character_emotions": item.get('character_emotions', {}),
                    "props": item.get('props', []),
                    "audio_cue": item.get('audio_cue', ''),
                    "tone": item.get('tone', ''),
                    "has_text_overlay": item.get('has_text_overlay', False),
                    "text_overlay_content": item.get('text_overlay_content', None),
                    "duration_s": item.get('duration_s', 8),
                    "negative_prompt": item.get('negative_prompt', ''),
                    "prompt_text": prompt_text,
                }
                
                # Auto-detect type from characters count if not provided
                if 'type' not in item and normalized['characters']:
                    n = len(normalized['characters'])
                    normalized['type'] = 'solo' if n == 1 else ('duo' if n == 2 else 'group')
                
                # Store the full JSON object as the prompt text
                row = PromptRow(
                    index=scene_idx,
                    prompt=json.dumps(normalized, ensure_ascii=False),
                    scene_description=item.get('description_vi', normalized.get('setting', '')),
                )
                prompts.append(row)

            if prompts:
                log.info(f"[Builder] Parsed {len(prompts)} JSON prompts (schema v2)")
                return prompts
        except (json.JSONDecodeError, ValueError) as e:
            log.debug(f"[Builder] JSON parse error: {e}")
        return None

    def _validate_prompts(self, prompts: List[PromptRow]) -> None:
        """Validate prompts against sensitive words (Fix 3).

        Checks each prompt against loaded sensitive words from rules_loader.
        Marks invalid prompts with violation reasons.
        """
        # Load sensitive words from rules_loader
        sensitive_patterns = []
        if self.rules_loader and hasattr(self.rules_loader, 'get_sensitive_words'):
            try:
                sensitive_patterns = self.rules_loader.get_sensitive_words()
            except Exception:
                pass

        if not sensitive_patterns:
            return  # No validation data available

        for p in prompts:
            violations = []
            lower_prompt = p.prompt.lower()
            for pattern in sensitive_patterns:
                if isinstance(pattern, str) and pattern.lower() in lower_prompt:
                    violations.append(f"Sensitive: '{pattern}'")
                elif hasattr(pattern, 'search') and pattern.search(p.prompt):
                    violations.append(f"Pattern match: {pattern.pattern}")
            if violations:
                p.valid = False
                p.violations = violations

    def _build_master(self, result: TopicResult) -> str:
        """Build Master file: scene prompts with dialogue + bible summary."""
        lines = [f"# Master — {result.topic}\n"]
        if result.bible:
            # Fix #8: Include full bible character section (not just 5 lines)
            bible_lines = result.bible.strip().split("\n")[:20]
            lines.append("## Bible Summary")
            lines.extend(bible_lines)
            lines.append("")
        lines.append("## Scene Prompts")
        for p in result.prompts:
            lines.append(f"{p.index}. {p.prompt}")
        return "\n".join(lines)

    def _build_dubbing(self, result: TopicResult) -> str:
        """Build Dubbing file: voice script with scene markers.
        
        Bug 7 fix: Extract real dialogue/narration from prompts instead of
        placeholder text. Looks for (Giọng: ...) "dialogue" patterns.
        """
        lines = [f"# Dubbing Script — {result.topic}\n"]
        dialogue_re = re.compile(
            r'\(Giọng[^)]*\)\s*["\u201c]([^"\u201d]+)["\u201d]',
            re.IGNORECASE
        )
        for p in result.prompts:
            lines.append(f"[Scene {p.index}]")
            if p.scene_description:
                lines.append(f"  Visual: {p.scene_description}")
            # Extract dialogues from prompt text
            dialogues = dialogue_re.findall(p.prompt)
            if dialogues:
                for d in dialogues:
                    lines.append(f"  Narration: \"{d.strip()}\"")
            else:
                _cue = self._extract_dubbing_cue(p.prompt, p.index)
                lines.append(f"  Narration: {_cue}")
            lines.append("")
        return "\n".join(lines)

    def _extract_dubbing_cue(self, prompt_text: str, scene_idx: int) -> str:
        """Extract narration cue from prompt when regex dialogue fails.

        Priority: audio_cue > tone + setting > prompt_text summary.
        """
        try:
            scene = json.loads(prompt_text)
            if isinstance(scene, dict):
                # Priority 1: explicit audio cue
                audio = scene.get("audio_cue", "").strip()
                if audio and len(audio) > 5:
                    return f'"{audio}"'

                # Priority 2: tone + setting combination
                tone = scene.get("tone", "").strip()
                setting = scene.get("setting", "").strip()
                if tone and setting:
                    return f"[{tone}] {setting[:60]}"
                if setting:
                    return f"[Scene {scene_idx}] {setting[:80]}"

                # Priority 3: characters doing something
                chars = scene.get("characters", [])
                actions = scene.get("character_actions", {})
                if chars and actions:
                    parts = []
                    for c in chars[:2]:
                        act = actions.get(c, "")
                        if act:
                            parts.append(f"{c}: {act[:40]}")
                    if parts:
                        return f"[Action] {'; '.join(parts)}"

                # Priority 4: prompt_text first 80 chars
                pt = scene.get("prompt_text", "")
                if pt:
                    return f"[Visual] {pt[:80]}..."
        except (json.JSONDecodeError, ValueError, AttributeError):
            pass

        # Final fallback: raw prompt summary
        clean = prompt_text.replace("\n", " ")[:80]
        return f"[Scene {scene_idx}] {clean}..."

    def _save_outputs(self, result: TopicResult, output_dir: str,
                       prompt_format: str = "text") -> None:
        """Save generated content to output files."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Determine prompts filename based on format
        prompts_filename = "Prompts.json" if prompt_format == "json" else "Prompts.txt"

        # Write all files from the files dict
        file_map = {
            "Bible":   ("Bible.md",   result.bible),
            "Master":  ("Master.txt", result.master),
            "Prompts": (prompts_filename, result.files.get("Prompts", "")),
            "Dubbing": ("Dubbing.txt", result.dubbing),
            "SEO":     ("SEO.txt",    result.seo),
        }
        for key, (filename, content) in file_map.items():
            if content:
                (out / filename).write_text(content, encoding="utf-8")

        # Research (internal, also saved)
        if result.research:
            (out / "Research.md").write_text(result.research, encoding="utf-8")

        log.info(f"[Builder] Saved outputs to {output_dir}")

    async def _safe_generate(self, **kwargs) -> str:
        """API call with exponential backoff + model/key fallback.

        Strategy:
        - Try primary model with 3 retries for rate limits
        - On rate limit (429) → mark key, switch to next available key
        - On safety block (400) → try fallback models from rotation pool
        - On auth error (401/403) → raise immediately
        """
        import asyncio
        from services.gemini_client import GeminiAPIError

        # Get custom keys for rotation
        custom_keys = []
        try:
            from services.ai_client_factory import get_ai_config
            custom_keys = get_ai_config().get("custom_keys", [])
        except Exception:
            pass

        # Build model fallback chain: primary → rotation pool
        primary_model = kwargs.get("model", "")
        fallback_models = []
        try:
            from services.model_rotation import get_rotation
            all_models = get_rotation().get_all_models()
            for m in all_models:
                if m != primary_model and m not in fallback_models:
                    fallback_models.append(m)
        except Exception:
            pass

        models_to_try = [primary_model] + fallback_models if primary_model else fallback_models

        for model in (models_to_try or [""]):
            if model:
                kwargs["model"] = model

            for attempt in range(3):
                try:
                    return await self.client.generate(**kwargs)
                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "rate" in err_str:
                        # Smart key rotation on rate limit
                        current_key = kwargs.get("api_key", "")
                        try:
                            from services.key_quota_manager import get_quota_manager
                            qm = get_quota_manager()
                            if "limit: 0" in err_str or "per day" in err_str:
                                qm.mark_rpd_blocked(current_key)
                            else:
                                qm.mark_rpm_blocked(current_key)
                            if custom_keys:
                                next_key = qm.get_available_key(custom_keys)
                                if next_key and next_key != current_key:
                                    kwargs["api_key"] = next_key
                                    log.info(
                                        f"[Builder] Switched to key "
                                        f"...{next_key[-8:]}"
                                    )
                                    continue  # Retry immediately with new key
                        except Exception:
                            pass
                        wait = 2 ** attempt
                        log.warning(f"[Builder] Rate limited ({model}), waiting {wait}s...")
                        await asyncio.sleep(wait)
                    elif "401" in err_str or "403" in err_str:
                        log.error(f"[Builder] Auth error: {e}")
                        raise
                    elif "prompt blocked" in err_str or "output blocked" in err_str:
                        # Safety block → try next model
                        log.warning(f"[Builder] Safety block ({model}), trying next model...")
                        break  # Break retry loop, continue model loop
                    else:
                        log.error(f"[Builder] API error ({model}, attempt {attempt+1}): {e}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1)
            else:
                # All 3 retries exhausted for this model (rate limit)
                continue
            # break from retry loop = safety block → continue to next model
            continue

        raise RuntimeError("API exhausted: all models blocked or failed")

    def _emit(self, step: str, topic: str, step_num: int) -> None:
        """Emit step progress callback."""
        if self.on_step_start:
            self.on_step_start(step, topic, step_num)

    # ── AI-Powered Workflow Generator ──────────────────────────

    @staticmethod
    def _bundled_path() -> Path:
        """Get bundled data/workflows/ path relative to project root."""
        return Path(__file__).parent.parent / "data" / "workflows"

    @staticmethod
    def _user_data_path() -> Path:
        """Fix #10: User-writable path for generated templates/rules."""
        p = Path.home() / ".veoauto" / "workflows"
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def generate_template(
        self,
        category: str,
        description: str,
        api_key: str,
        structure: str = "",
        visual_style: str = "",
        example_count: int = 2,
    ) -> Path:
        """Use Gemini API to generate a new workflow template .md file.

        Args:
            category: Template category name (e.g. "Cooking", "Travel").
            description: What the template is about.
            api_key: Gemini API key.
            structure: Story structure hint (e.g. "3act", "pmcs").
            visual_style: Visual style hint (e.g. "3D Pixar", "Realistic").
            example_count: Number of existing templates to use as examples.

        Returns:
            Path to the newly created .md file.
        """
        # Gather existing templates as context examples
        examples_text = ""
        if self.scanner and self.scanner.templates:
            samples = self.scanner.templates[:example_count]
            for t in samples:
                body_preview = t.body[:800] if t.body else "(empty)"
                examples_text += (
                    f"\n--- EXAMPLE: {t.display_name} ---\n"
                    f"{body_preview}\n"
                )

        # Load core principles as context
        core_path = self._bundled_path() / "02_Universal" / "00_Core_Principles.md"
        core_text = ""
        try:
            core_text = load_text(core_path)[:3000]
        except (FileNotFoundError, Exception):
            pass

        system_prompt = (
            "You are a VEO video production template designer.\n"
            "Create a comprehensive .md template file for AI video production.\n\n"
            "The file MUST start with YAML frontmatter between --- delimiters:\n"
            "```\n"
            "---\n"
            f'template_id: "{category.lower().replace(" ", "_")}"\n'
            f'display_name: "{category}"\n'
            f'group: "custom"\n'
            f'keywords: [{", ".join(f"{w}" for w in category.lower().split())}]\n'
            f'visual_style: "{visual_style or "3D Pixar Animation"}"\n'
            f'structure: "{structure or "3act"}"\n'
            "scene_count_range: [6, 10]\n"
            "output_files: [Bible, Master, Prompts, Dubbing, SEO]\n"
            "shared_rules: [01_Technical_Rules]\n"
            "---\n"
            "```\n\n"
            "After frontmatter, include:\n"
            "1. Bible Template (character descriptions, settings, visual cues)\n"
            "2. Story Structure explanation\n"
            "3. Scene breakdown template\n"
            "4. Checklist\n\n"
            "Write in Vietnamese + English mix (same style as examples).\n\n"
            f"## CORE PRINCIPLES\n{core_text}\n\n"
            f"## EXISTING TEMPLATE EXAMPLES\n{examples_text}"
        )

        user_prompt = (
            f"Create a production template for category: **{category}**\n"
            f"Description: {description}\n"
            f"Structure: {structure or 'flexible'}\n"
            f"Visual style: {visual_style or 'auto'}\n\n"
            "Output the COMPLETE .md file including YAML frontmatter."
        )

        raw = await self._safe_generate(
            prompt=user_prompt,
            system=system_prompt,
            api_key=api_key,
            max_tokens=8192,
            temperature=0.7,
            model=getattr(self, '_model', ''),
        )

        # Strip markdown code fences if present
        content = raw.strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = "\n".join(content.split("\n")[:-1])

        # Save to user-writable directory (not bundled — may be read-only in packaged builds)
        safe_name = re.sub(r'[^\w\s-]', '', category).replace(" ", "_")
        templates_dir = self._user_data_path() / "Templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        output_path = templates_dir / f"{safe_name}.md"

        output_path.write_text(content.strip(), encoding="utf-8")
        log.info(f"[Builder] Generated template: {output_path}")

        # Re-scan to pick up new template
        if self.scanner:
            self.scanner.scan_sources([str(templates_dir)])

        return output_path

    async def generate_rule(
        self,
        rule_name: str,
        description: str,
        api_key: str,
        rule_type: str = "advanced",
    ) -> Path:
        """Use Gemini API to generate a new rule .md file.

        Args:
            rule_name: Rule name (e.g. "Background Music Guide").
            description: What the rule covers.
            api_key: Gemini API key.
            rule_type: "universal" or "advanced".

        Returns:
            Path to the newly created rule .md file.
        """
        # Load existing rules as context
        existing_rules = ""
        rules_dir = self._bundled_path() / "03_Advanced"
        if rules_dir.exists():
            for f in sorted(scan_data_files(rules_dir, recursive=False))[:3]:
                try:
                    preview = load_text(f)[:600]
                    existing_rules += f"\n--- EXAMPLE: {f.name} ---\n{preview}\n"
                except Exception:
                    pass

        system_prompt = (
            "You are a VEO video production rules designer.\n"
            "Create a comprehensive production rule .md file.\n\n"
            "The rule should include:\n"
            "1. Clear title and purpose\n"
            "2. Numbered rules (E-format: E01, E02, etc. or custom numbering)\n"
            "3. Do's and Don'ts tables\n"
            "4. Examples with visual descriptions\n"
            "5. Checklist at the end\n\n"
            "Write in Vietnamese + English mix (same style as examples).\n\n"
            f"## EXISTING RULE EXAMPLES\n{existing_rules}"
        )

        user_prompt = (
            f"Create a production rule file for: **{rule_name}**\n"
            f"Description: {description}\n\n"
            "Output the COMPLETE .md rule file."
        )

        raw = await self._safe_generate(
            prompt=user_prompt,
            system=system_prompt,
            api_key=api_key,
            max_tokens=8192,
            temperature=0.7,
            model=getattr(self, '_model', ''),
        )

        content = raw.strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = "\n".join(content.split("\n")[:-1])

        # Save to user-writable directory (not bundled — may be read-only in packaged builds)
        subdir = "02_Universal" if rule_type == "universal" else "03_Advanced"
        target_dir = self._user_data_path() / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Auto-number based on existing files
        existing_nums = []
        for f in target_dir.glob("*.md"):
            match = re.match(r'^(\d+)', f.stem)
            if match:
                existing_nums.append(int(match.group(1)))
        next_num = max(existing_nums, default=0) + 1

        safe_name = re.sub(r'[^\w\s-]', '', rule_name).replace(" ", "_")
        filename = f"{next_num:02d}_{safe_name}.md"
        output_path = target_dir / filename

        output_path.write_text(content.strip(), encoding="utf-8")
        log.info(f"[Builder] Generated rule: {output_path}")

        return output_path

    async def update_research(
        self,
        data_type: str,
        api_key: str,
        context: str = "",
    ) -> Path:
        """Use Gemini API to update research/keywords data.

        Args:
            data_type: "trending_keywords", "seo_bank", or "title_bank".
            api_key: Gemini API key.
            context: Additional context (e.g. current trends, niche).

        Returns:
            Path to the updated research .md file.
        """
        research_dir = self._bundled_path() / "01_Research"
        research_dir.mkdir(parents=True, exist_ok=True)

        # Load existing research file as base
        file_map = {
            "trending_keywords": "01_Trending_Keywords_2026.md",
            "seo_bank": "03_SEO_Bank_Tet_2026.md",
            "title_bank": "02_Title_Bank_Tet_2026.md",
        }
        filename = file_map.get(data_type, f"{data_type}.md")
        target_path = research_dir / filename

        existing_content = ""
        if target_path.exists():
            existing_content = target_path.read_text(
                encoding="utf-8", errors="ignore"
            )[:4000]

        type_instructions = {
            "trending_keywords": (
                "Update the trending keywords file for Vietnamese YouTube Shorts.\n"
                "Include: trending topics, viral phrases, seasonal keywords.\n"
                "Format: categorized lists with search volume estimates."
            ),
            "seo_bank": (
                "Update the SEO bank with new titles, descriptions, hashtags.\n"
                "Focus on Vietnamese audience engagement patterns.\n"
                "Format: grouped by content category with A/B/C title variants."
            ),
            "title_bank": (
                "Update the title bank with new attention-grabbing title formulas.\n"
                "Include: hook patterns, number formats, emotion triggers.\n"
                "Format: template patterns with placeholders and examples."
            ),
        }

        system_prompt = (
            "You are a Vietnamese YouTube content SEO specialist.\n"
            f"{type_instructions.get(data_type, 'Update the research data file.')}\n\n"
            "IMPORTANT: Preserve the existing structure and ADD new content.\n"
            "Mark new additions with date stamp.\n\n"
            f"## EXISTING CONTENT\n{existing_content}"
        )

        user_prompt = (
            f"Update the {data_type.replace('_', ' ')} research data.\n"
            f"Additional context: {context or 'General update for 2026'}\n\n"
            "Add new entries while keeping existing ones. Mark new entries with "
            f"[NEW {datetime.now().strftime('%Y-%m')}]."
        )

        raw = await self._safe_generate(
            prompt=user_prompt,
            system=system_prompt,
            api_key=api_key,
            max_tokens=4096,
            temperature=0.7,
            model=getattr(self, '_model', ''),
        )

        content = raw.strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = "\n".join(content.split("\n")[:-1])

        target_path.write_text(content.strip(), encoding="utf-8")
        log.info(f"[Builder] Updated research: {target_path}")

        return target_path
