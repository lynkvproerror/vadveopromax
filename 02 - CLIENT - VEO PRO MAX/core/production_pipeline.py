"""
VEO Pro Max — Production Pipeline

Stage-based orchestrator for full video production:
1. Duration Estimation (auto from sidebar)
2. Script Analysis (Gemini API → structured JSON)
3. Scene Breakdown (Gemini API → scene prompts)
4. Character Image Generation (→ Queue tab T2I)
5. Scene Image Generation (→ Queue tab T2I)
6. Video Generation (→ Queue tab I2V/R2V)
7. Concat (FFmpeg → final video)

Each stage pauses for user checkpoint (review/confirm/edit).
Stages 4-7 reuse existing engine tabs and Queue tab.
"""

import json
import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from enum import Enum

log = logging.getLogger("veo.pipeline")


# ── Self-Contained Production Rules (from workflow analysis) ──────

BIBLE_RULES = """
## CHARACTER PROFILE LOCK (8 MANDATORY FIELDS)

Mỗi nhân vật PHẢI có đầy đủ 8 fields trong Bible (với HEX + Text Description):

1. Age + Role: "58-year-old Vietnamese mother-in-law"
2. Height: "1.58m"
3. Skin + Modifier: "#D4A574 - warm golden tan, sun-kissed skin"
4. Face features: "round face, smile lines, prominent cheekbones"
5. Hair: "#1A1A1A - soft matte black, gray-streaked hair in bun"
6. Clothing top: "#3D2314 - deep dark chocolate brown ao ba ba"
7. Clothing bottom: "#1A1A1A - soft matte black loose pants"
8. Accessories: "#FFD700 - rich metallic gold earrings, #00A86B - vivid jade green bracelet"

FORMAT: Bible chua CA HEX + Text (VD: #FF6B00 - bold bright orange)

## CHARACTER IMAGE PROMPT
Moi nhan vat (chinh + phu) PHAI co 1 prompt tao anh rieng trong Bible.
Prompt chi tiet style + body + HEX + expression + background.

## VISUAL STYLE
Chon MOT phong cach duy nhat va giu xuyen suot. Khong mix styles.
Vi du: "realistic Vietnamese family scene, cinematic lighting, warm color grading"
hoac: "The 3D cute animation style, Pixar render, soft lighting, vibrant colors"
"""

PROMPT_RULES_COMPACT = """
## RULES FOR COMPACT VEO SCENE DESCRIPTIONS
## (Character profiles will be injected automatically — do NOT include them)

### 1. CHARACTER NAME TAG [Name] (MANDATORY)
- Use [Name] tag for EVERY character appearing in a scene
- Format: [Name] action/expression/pose
- Do NOT write full character descriptions — only name tag + action
- Example: [Tam] kneeling and digging, weary expression

### 2. MULTI-SEGMENT (sub-scenes per prompt)
- Each prompt (8s clip) can have 1-3 sub-scenes
- Use >> to separate segments
- At least 3-5 prompts MUST use multi-segment >>

### 3. NEGATIVE PROMPTS — ADD AT END OF EVERY PROMPT
, no text, no subtitles, no labels, no watermarks

### 4. SPEAKER EXPRESSION
- Speaker: "mouth open speaking firmly" / "speaking instructively"
- Listener: "attentive listening expression" / "nodding while listening"

### 5. ZERO TEXT POLICY
- NO: shows, displays, clock, timer, labeled, sign reads, poster

### 6. BLANK LINE
- Each prompt = 1 line
- Between 2 prompts = 1 blank line (press enter twice)

### 7. FORMAT (NO brackets on scene type)
Scene type, context. Shot, Camera. Visual Style. Setting.
[CharName] action/expression. Audio of sound,
no text, no subtitles, no labels, no watermarks

### 8. STORY PACING — NO FILLER
- Each prompt MUST have concrete action advancing the story
- Do NOT create "Transition" filler prompts
- If story needs only 35 prompts, create ONLY 35
"""

PROMPT_RULES_FULL = """
## FULL PRODUCTION RULES (for reference — applied automatically)

### CHARACTER PROFILE LOCK — INJECTED AUTOMATICALLY
- Full 8-field Character Profile Lock is injected into EVERY prompt automatically
- Fields: age+role, height, skin+modifier, face, hair, clothing top, clothing bottom, accessories
- NO agent decay — all 8 fields present in every prompt, every character

### NEGATIVE PROMPTS (FULL)
, no deformed limbs, no mutated faces, no extra fingers, no melting geometry, no color shifts, no texture distortion
"""


# ── Stage Status ──────────────────────────────────────────────


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRM = "waiting_confirm"  # Checkpoint — paused for user
    CONFIRMED = "confirmed"
    SKIPPED = "skipped"
    ERROR = "error"


# ── Data Classes ──────────────────────────────────────────────


@dataclass
class SceneData:
    """A single scene in the video."""
    index: int
    title: str = ""
    description: str = ""
    prompt: str = ""              # T2V/T2I prompt
    character_ref: str = ""       # Character reference description
    duration_s: float = 8.0       # Clip duration in seconds
    image_path: str = ""          # Generated scene image path
    video_path: str = ""          # Generated video clip path


@dataclass 
class CharacterData:
    """Character definition for the project."""
    name: str
    description: str = ""         # Visual description for T2I
    prompt: str = ""              # T2I prompt
    image_path: str = ""          # Generated character image path


@dataclass
class StageResult:
    """Result of a single pipeline stage."""
    stage: str
    status: StageStatus = StageStatus.PENDING
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    
    # Convenience fields populated per stage
    scene_count: int = 0
    clip_duration: int = 8
    script_json: str = ""
    scenes: List[SceneData] = field(default_factory=list)
    characters: List[CharacterData] = field(default_factory=list)
    prompts: List[str] = field(default_factory=list)


@dataclass
class PipelineState:
    """Full pipeline state across all stages."""
    topic: str = ""
    pipeline_mode: str = "full_production"
    current_stage: str = "duration_estimate"
    stages: Dict[str, StageResult] = field(default_factory=dict)
    
    # Accumulated data across stages
    scene_count: int = 0
    clip_duration: int = 8
    target_duration: int = 0
    script_json: Dict = field(default_factory=dict)
    scenes: List[SceneData] = field(default_factory=list)
    characters: List[CharacterData] = field(default_factory=list)
    final_video_path: str = ""
    
    def get_stage(self, name: str) -> StageResult:
        if name not in self.stages:
            self.stages[name] = StageResult(stage=name)
        return self.stages[name]
    
    def to_session_dict(self) -> dict:
        """Serialize full pipeline state for session save.
        
        Captures everything needed to restore a session:
        - topic, pipeline_mode, current_stage position
        - All stage results (status, data, prompts, error)
        - Accumulated data: characters, scenes, script_json
        - Duration/count settings
        """
        return {
            "topic": self.topic,
            "pipeline_mode": self.pipeline_mode,
            "current_stage": self.current_stage,
            "scene_count": self.scene_count,
            "clip_duration": self.clip_duration,
            "target_duration": self.target_duration,
            "script_json": self.script_json,
            "final_video_path": self.final_video_path,
            "characters": [
                {"name": c.name, "description": c.description,
                 "prompt": c.prompt, "image_path": c.image_path}
                for c in self.characters
            ],
            "scenes": [
                {"index": s.index, "title": s.title, "description": s.description,
                 "prompt": s.prompt, "character_ref": s.character_ref,
                 "duration_s": s.duration_s, "image_path": s.image_path,
                 "video_path": s.video_path}
                for s in self.scenes
            ],
            "stages": {
                name: {
                    "status": sr.status.value,
                    "data": sr.data,
                    "error": sr.error,
                    "prompts": sr.prompts,
                }
                for name, sr in self.stages.items()
            },
        }
    
    @classmethod
    def from_session_dict(cls, data: dict) -> "PipelineState":
        """Restore pipeline state from saved session JSON.
        
        Reconstructs PipelineState with all accumulated data,
        stage results, characters, and scenes.
        """
        state = cls()
        state.topic = data.get("topic", "")
        state.pipeline_mode = data.get("pipeline_mode", "full_production")
        state.current_stage = data.get("current_stage", "duration_estimate")
        state.scene_count = data.get("scene_count", 0)
        state.clip_duration = data.get("clip_duration", 8)
        state.target_duration = data.get("target_duration", 0)
        state.script_json = data.get("script_json", {})
        state.final_video_path = data.get("final_video_path", "")
        
        # Restore characters
        for cd in data.get("characters", []):
            state.characters.append(CharacterData(
                name=cd.get("name", ""),
                description=cd.get("description", ""),
                prompt=cd.get("prompt", ""),
                image_path=cd.get("image_path", ""),
            ))
        
        # Restore scenes
        for sd in data.get("scenes", []):
            state.scenes.append(SceneData(
                index=sd.get("index", 0),
                title=sd.get("title", ""),
                description=sd.get("description", ""),
                prompt=sd.get("prompt", ""),
                character_ref=sd.get("character_ref", ""),
                duration_s=sd.get("duration_s", 8.0),
                image_path=sd.get("image_path", ""),
                video_path=sd.get("video_path", ""),
            ))
        
        # Restore stages
        for stage_name, sr_data in data.get("stages", {}).items():
            try:
                status = StageStatus(sr_data.get("status", "pending"))
            except (ValueError, KeyError):
                status = StageStatus.PENDING
            sr = StageResult(
                stage=stage_name,
                status=status,
                data=sr_data.get("data", {}),
                error=sr_data.get("error", ""),
                prompts=sr_data.get("prompts", []),
            )
            state.stages[stage_name] = sr
        
        return state


# ── Pipeline Orchestrator ─────────────────────────────────────


STAGE_ORDER = [
    "duration_estimate",
    "script_analysis",
    "scene_breakdown",
    "character_gen",
    "scene_image_gen",
    "video_gen",
    "concat",
]

# Gemini prompts for text stages
SCRIPT_ANALYSIS_PROMPT = """Bạn là một chuyên gia biên kịch video. Phân tích tiêu đề/kịch bản sau và tạo cấu trúc video.

Tiêu đề: {topic}
Số scene yêu cầu: {scene_count}
Loại dự án: {project_type}
Phong cách: {visual_style}
Tone: {tone}

Trả về JSON (chỉ JSON, không markdown):
{{
  "title": "<tiêu đề thực tế rút ra từ nội dung>",
  "synopsis": "Tóm tắt nội dung 2-3 câu",
  "characters": [
    {{"name": "Tên nhân vật", "role": "Vai trò", "appearance": "Mô tả ngoại hình chi tiết cho T2I"}}
  ],
  "scenes": [
    {{"index": 1, "title": "Tên scene", "description": "Mô tả chi tiết", "dialogue": "Lời thoại nếu có", "mood": "Cảm xúc"}}
  ],
  "pacing": "Nhịp độ video",
  "total_duration_estimate": "{target_duration}s"
}}"""

SCENE_BREAKDOWN_PROMPT = """Dựa trên kịch bản đã phân tích, tạo prompts chi tiết cho từng scene.

Kịch bản:
{script_json}

Phong cách hình ảnh: {visual_style}
Nhân vật chính: {characters}

Cho mỗi scene, tạo:
1. Prompt cho T2I (mô tả hình ảnh chi tiết, bao gồm nhân vật, bối cảnh, ánh sáng, góc camera)
2. Prompt cho T2V (mô tả chuyển động, hành động)

Trả về JSON (chỉ JSON):
{{
  "scenes": [
    {{
      "index": 1,
      "title": "Tên scene",
      "image_prompt": "Prompt chi tiết cho tạo ảnh (T2I), bao gồm style, composition",
      "video_prompt": "Prompt chi tiết cho tạo video, bao gồm chuyển động camera và hành động",
      "duration_s": {clip_duration},
      "character_refs": ["Tên nhân vật xuất hiện"]
    }}
  ]
}}"""

# ── Project Type → AI instruction mapping ──
# Injected into ALL stage prompts so Gemini respects the chosen style.
PROJECT_TYPE_PROMPTS = {
    "video_voice": (
        "⚠️ PROJECT TYPE: VIDEO + VOICE-OVER\n"
        "- Cinematic video with voice narration/dialogue\n"
        "- Characters show speaking expressions (mouth open, gestures)\n"
        "- Include audio cues for mood and dialogue timing\n"
    ),
    "video_silent": (
        "⚠️ PROJECT TYPE: SILENT VIDEO (NO VOICE)\n"
        "- Visual storytelling only — NO dialogue, NO voice-over\n"
        "- Focus on actions, expressions, environment, music\n"
        "- Communicate emotion through visual composition and movement\n"
    ),
    "animation": (
        "⚠️ PROJECT TYPE: PHIM HOẠT HÌNH (ANIMATION/CARTOON)\n"
        "- ALL characters MUST be animated/cartoon/3D style (Pixar, anime, or 2D cartoon)\n"
        "- Do NOT create realistic/photorealistic human characters\n"
        "- Character descriptions must specify cartoon features: large expressive eyes, smooth skin, vibrant saturated colors, stylized proportions\n"
        "- Visual style: animated, colorful, clean lines, stylized\n"
        "- Backgrounds: painted/rendered style, not photographic\n"
    ),
    "action": (
        "⚠️ PROJECT TYPE: PHIM HÀNH ĐỘNG (ACTION FILM)\n"
        "- Cinematic, dramatic lighting, high contrast, intense mood\n"
        "- Dynamic camera movements, fast-paced action sequences\n"
        "- Characters: athletic, determined expressions, action-ready poses\n"
    ),
    "documentary": (
        "⚠️ PROJECT TYPE: PHIM TÀI LIỆU (DOCUMENTARY)\n"
        "- Realistic, authentic visual style, natural lighting\n"
        "- Observational camera, steady shots, real-world settings\n"
        "- Focus on factual accuracy and informative visuals\n"
    ),
    "philosophy": (
        "⚠️ PROJECT TYPE: TRIẾT LÝ / TÂM LINH\n"
        "- Contemplative, serene atmosphere, soft ethereal lighting\n"
        "- Symbolic imagery, abstract visuals, nature elements\n"
        "- Calm, meditative pace\n"
    ),
    "slideshow": (
        "⚠️ PROJECT TYPE: SLIDESHOW ẢNH\n"
        "- High-quality still images with subtle motion (pan, zoom)\n"
        "- Clean compositions, professional photography style\n"
    ),
    "storytelling": (
        "⚠️ PROJECT TYPE: KỂ CHUYỆN (STORYTELLING)\n"
        "- Warm, engaging visual narrative\n"
        "- Character-focused, emotional expressions, intimate shots\n"
    ),
    "comedy": (
        "⚠️ PROJECT TYPE: HÀI / GIẢI TRÍ\n"
        "- Bright, upbeat visual style, exaggerated expressions\n"
        "- Comedic timing through camera movement and character reactions\n"
    ),
    "music_video": (
        "⚠️ PROJECT TYPE: MUSIC VIDEO\n"
        "- Stylized, artistic visual approach, rhythm-driven editing\n"
        "- Creative lighting, color grading, dynamic compositions\n"
    ),
    "tutorial": (
        "⚠️ PROJECT TYPE: HƯỚNG DẪN / HOW-TO\n"
        "- Clear, well-lit instructional shots\n"
        "- Step-by-step visual progressions, close-ups on details\n"
    ),
    "product_review": (
        "⚠️ PROJECT TYPE: REVIEW SẢN PHẨM\n"
        "- Clean product photography style, studio lighting\n"
        "- Detailed close-ups, comparison shots, before/after\n"
    ),
    "custom": "",  # No special instruction for custom — user controls everything
}


class ProductionPipeline:
    """Full production orchestrator with per-stage user checkpoints.
    
    Usage:
        pipeline = ProductionPipeline(gemini_client, api_key)
        
        # Stage 1: Duration
        result = await pipeline.run_stage("duration_estimate", config)
        # → User reviews → confirms
        
        # Stage 2: Script Analysis
        result = await pipeline.run_stage("script_analysis", config)
        # → User reviews → confirms/edits
        
        # ... etc, one stage at a time
    """
    
    def __init__(self, gemini_client=None, api_key: str = "", model: str = ""):
        self.client = gemini_client
        self.api_key = api_key
        self.model = model
        self.state = PipelineState()
        self._cancelled = False
        
        # Callbacks for UI updates
        self.on_stage_start: Optional[Callable] = None
        self.on_stage_done: Optional[Callable] = None
    
    def cancel(self):
        """Cancel current stage."""
        self._cancelled = True
    
    def get_state(self) -> PipelineState:
        """Get full pipeline state."""
        return self.state
    
    def get_next_stage(self) -> Optional[str]:
        """Get next stage to run (after current confirmed stage)."""
        current_idx = -1
        for i, s in enumerate(STAGE_ORDER):
            stage = self.state.get_stage(s)
            if stage.status in (StageStatus.CONFIRMED, StageStatus.SKIPPED):
                current_idx = i
            else:
                break
        next_idx = current_idx + 1
        if next_idx < len(STAGE_ORDER):
            return STAGE_ORDER[next_idx]
        return None
    
    def confirm_stage(self, stage_name: str, edited_data: Optional[Dict] = None):
        """User confirms a stage result, optionally with edits.
        
        If edited_data is provided AND the stage was already confirmed,
        all downstream stages are reset to PENDING so they re-run with updated data.
        """
        stage = self.state.get_stage(stage_name)
        if edited_data:
            # Fix 4: Re-confirm with edits → reset all downstream stages
            if stage.status == StageStatus.CONFIRMED:
                idx = STAGE_ORDER.index(stage_name) if stage_name in STAGE_ORDER else -1
                if idx >= 0 and idx < len(STAGE_ORDER) - 1:
                    next_stage = STAGE_ORDER[idx + 1]
                    self.reset_from_stage(next_stage)
                    log.info(f"[Pipeline] Re-confirm with edits: reset from '{next_stage}' onward")
            stage.data.update(edited_data)
            # Apply edits to pipeline state
            if stage_name == "duration_estimate" and "scene_count" in edited_data:
                new_sc = edited_data["scene_count"]
                self.state.scene_count = new_sc
                # Recalculate target_duration to stay consistent
                clip = self.state.clip_duration or 8
                self.state.target_duration = new_sc * clip
                stage.data["target_duration"] = self.state.target_duration
                # R3-4 Fix: Clear stale scenes so Stage 3 regenerates with new count
                self.state.scenes = []
                log.info(f"[Pipeline] Scene count edited → {new_sc}, target_duration recalculated → {self.state.target_duration}s, scenes cleared")
            elif stage_name == "script_analysis":
                # Bible text edit — update state for Stage 3
                if "bible" in edited_data:
                    if isinstance(self.state.script_json, dict):
                        self.state.script_json["bible"] = edited_data["bible"]
                    # R3-1 Fix: Re-sync characters from edited Bible
                    char_profiles = self._extract_char_profiles_from_bible(edited_data["bible"])
                    if char_profiles:
                        self.state.characters = [
                            CharacterData(name=n, description=d)
                            for n, d in char_profiles.items()
                        ]
                        log.info(f"[Pipeline] R3-1: Re-synced {len(char_profiles)} characters from edited Bible")
                elif "script_json" in edited_data:
                    self.state.script_json = edited_data["script_json"]
            elif stage_name == "scene_breakdown":
                # Prompts text edit — re-parse into scenes
                if "prompts_text" in edited_data:
                    self.state.scenes = self._parse_text_prompts(edited_data["prompts_text"])
                elif "scenes" in edited_data:
                    self.state.scenes = edited_data["scenes"]
        stage.status = StageStatus.CONFIRMED
        log.info(f"[Pipeline] Stage '{stage_name}' confirmed by user")
    
    def skip_stage(self, stage_name: str):
        """User skips a stage."""
        stage = self.state.get_stage(stage_name)
        stage.status = StageStatus.SKIPPED
        log.info(f"[Pipeline] Stage '{stage_name}' skipped by user")
    
    def reset_from_stage(self, stage_name: str):
        """Reset this stage and ALL subsequent stages to PENDING.
        
        Used when user goes back and edits a previous stage —
        all downstream stages must be re-run with updated data.
        """
        found = False
        for s in STAGE_ORDER:
            if s == stage_name:
                found = True
            if found:
                stage = self.state.get_stage(s)
                stage.status = StageStatus.PENDING
                stage.error = ""
                # Fix 13: Clear stale data/prompts so UI doesn't show old cards
                stage.data = {}
                stage.prompts = []
        log.info(f"[Pipeline] Reset from '{stage_name}' onward → all PENDING (data cleared)")
    
    def reset(self):
        """Full reset for multi-topic batch — clear all state, keep client/keys."""
        self.state = PipelineState()
        self._cancelled = False
        log.info("[Pipeline] Full reset for next topic")
    
    def get_prev_stage(self, stage_name: str) -> Optional[str]:
        """Get the stage immediately before the given one."""
        for i, s in enumerate(STAGE_ORDER):
            if s == stage_name and i > 0:
                return STAGE_ORDER[i - 1]
        return None
    
    async def run_stage(self, stage_name: str, config: Dict) -> StageResult:
        """Run a single stage. Returns result for user review.
        
        Pipeline PAUSES after returning — UI must call confirm_stage() 
        before running the next stage.
        """
        self._cancelled = False
        stage = self.state.get_stage(stage_name)
        stage.status = StageStatus.RUNNING
        
        if self.on_stage_start:
            self.on_stage_start(stage_name)
        
        try:
            if stage_name == "duration_estimate":
                await self._stage_duration(stage, config)
            elif stage_name == "script_analysis":
                await self._stage_script_analysis(stage, config)
            elif stage_name == "scene_breakdown":
                await self._stage_scene_breakdown(stage, config)
            elif stage_name == "character_gen":
                await self._stage_character_gen(stage, config)
            elif stage_name == "scene_image_gen":
                await self._stage_scene_image_gen(stage, config)
            elif stage_name == "video_gen":
                await self._stage_video_gen(stage, config)
            elif stage_name == "concat":
                await self._stage_concat(stage, config)
            
            stage.status = StageStatus.WAITING_CONFIRM
            log.info(f"[Pipeline] Stage '{stage_name}' done → waiting for user confirm")
            
        except InterruptedError:
            stage.status = StageStatus.ERROR
            stage.error = "Cancelled by user"
        except Exception as e:
            stage.status = StageStatus.ERROR
            stage.error = str(e)
            log.error(f"[Pipeline] Stage '{stage_name}' error: {e}")
        
        if self.on_stage_done:
            self.on_stage_done(stage_name, stage)
        
        return stage
    
    # ── Stage Implementations ─────────────────────────────────
    
    @staticmethod
    def _build_dimension_context(config: Dict) -> str:
        """Build human-readable context from D1-D9 sidebar dimensions.
        
        Converts sidebar selections into an instruction block that AI can use
        to tailor its output (Bible, prompts, character descriptions).
        """
        lines = []
        
        # D1: Category
        cats = config.get("category", [])
        if cats:
            lines.append(f"Category: {', '.join(cats)}")
        
        # D2: Structure
        structs = config.get("structure", [])
        if structs:
            lines.append(f"Story Structure: {', '.join(structs)}")
        
        # D3: Visual Style (CRITICAL for character/scene consistency)
        styles = config.get("style", [])
        if styles:
            lines.append(f"⚠️ Visual Style: {', '.join(styles)} — MUST maintain this style consistently across ALL characters and scenes")
        
        # D4: Character Type
        char_types = config.get("character", [])
        if char_types:
            lines.append(f"Character Type: {', '.join(char_types)}")
        
        # D5: Audience
        auds = config.get("audience", [])
        if auds:
            lines.append(f"Target Audience: {', '.join(auds)}")
        
        # D6: Persona
        persona = config.get("persona")
        if persona and persona != "none":
            lines.append(f"AI Persona: {persona}")
        
        # D7: Tone
        tones = config.get("tone", [])
        if tones:
            lines.append(f"Tone: {', '.join(tones)}")
        
        # D8: Voice Region
        voices = config.get("voice", [])
        if voices:
            lines.append(f"Voice Region: {', '.join(voices)}")
        
        # D9: Camera Technique
        cameras = config.get("camera_technique", [])
        if cameras:
            lines.append(f"Preferred Camera: {', '.join(cameras)}")
        
        if not lines:
            return ""
        return "\n## SIDEBAR DIMENSIONS (user-selected):\n" + "\n".join(f"- {l}" for l in lines) + "\n"
    
    async def _stage_duration(self, stage: StageResult, config: Dict):
        """Stage 1: Analyze input + calculate duration.
        
        Priority: Sidebar explicit values > AI detected > defaults.
        
        If input text is a detailed script (>200 chars), uses AI to extract:
        - scene_count, total_duration, characters, style
        Then merges with sidebar config.
        """
        topic = config.get("topic", "")
        self.state.topic = topic
        
        # Sidebar values (always have defaults)
        sidebar_clip = config.get("clip_duration", 8)
        sidebar_scenes = config.get("scene_count", 8)
        sidebar_duration_str = config.get("target_duration", "")
        
        # Detect if input is a detailed script worth analyzing
        is_detailed_script = len(topic) > 200
        
        detected = {}
        if is_detailed_script and self.client:
            try:
                detected = await self._ai_detect_from_input(topic)
                log.info(f"[Pipeline] AI detected: {detected}")
            except Exception as e:
                log.warning(f"[Pipeline] AI detect failed, using sidebar: {e}")
        
        # ── Merge: sidebar ALWAYS wins for duration ──
        ai_characters = detected.get("characters", [])
        ai_title = detected.get("title", "")
        ai_narrative_scenes = detected.get("scene_count", 0)
        
        # clip_duration = VEO clip length (always from sidebar, default 8s)
        clip_duration = sidebar_clip
        
        # target_duration: SIDEBAR ALWAYS WINS
        # Sidebar has either explicit text (e.g. "500") or scene_count from spinner
        if sidebar_duration_str:
            target_duration = self._parse_duration_str(sidebar_duration_str) or (clip_duration * sidebar_scenes)
        else:
            # No text input → use sidebar scene_count × clip_duration
            target_duration = clip_duration * sidebar_scenes
        
        # scene_count = number of VEO clips = ceil(target_duration / clip_duration)
        if target_duration > 0 and clip_duration > 0:
            scene_count = max(1, int(target_duration / clip_duration + 0.999))
        else:
            scene_count = sidebar_scenes
        
        # Store characters if AI detected them
        if ai_characters:
            self.state.characters = [
                CharacterData(name=c.get("name", ""), description=c.get("description", ""))
                for c in ai_characters
            ]
        
        # Store state
        self.state.clip_duration = clip_duration
        self.state.scene_count = scene_count
        self.state.target_duration = target_duration
        
        stage.scene_count = scene_count
        stage.clip_duration = clip_duration
        stage.data = {
            "scene_count": scene_count,
            "clip_duration": clip_duration,
            "target_duration": target_duration,
            "topic": ai_title or topic[:100],
            "source": "ai_detected" if detected else "sidebar_defaults",
            "ai_detected": detected,
        }
    
    async def _ai_detect_from_input(self, input_text: str) -> dict:
        """Use AI to extract structured data from input script.
        
        Returns dict with: scene_count, characters, title, style, tone.
        Duration is NOT detected by AI — sidebar values always win.
        """
        prompt = f"""Phân tích kịch bản/nội dung sau và trích xuất thông tin cấu trúc.

QUAN TRỌNG: 
- Trường "title" phải là tiêu đề THỰC TẾ rút ra từ nội dung
- KHÔNG cần phân tích thời lượng — thời lượng đã có từ sidebar
- Phải tìm TÊN NHÂN VẬT cụ thể trong nội dung, kể cả khi danh sách dùng ký hiệu "* —" hoặc bullet
  (đọc phần mô tả và nội dung cảnh để xác định tên nhân vật)

Trả về JSON (chỉ JSON, không markdown):
{{
  "title": "<tiêu đề thực tế rút ra từ nội dung>",
  "scene_count": <số cảnh/màn trong câu chuyện>,
  "characters": [
    {{"name": "Tên cụ thể (VD: Tấm, Cám...)", "description": "Mô tả ngắn về ngoại hình và tính cách"}}
  ],
  "style": "phong cách hình ảnh phù hợp với nội dung",
  "tone": "tone/cảm xúc chung"
}}

Nội dung:
{input_text[:6000]}"""
        
        system = (
            "Bạn là trợ lý phân tích kịch bản. "
            "Đọc nội dung và trích xuất thông tin cấu trúc. "
            "Chỉ trả về JSON, không giải thích."
        )
        
        response = await self._call_gemini_with_rotation(
            prompt=prompt, system=system,
            max_tokens=2000, temperature=0.2,
        )
        return self._extract_json(response)
    
    @staticmethod
    def _parse_duration_str(text: str) -> int:
        """Parse duration string like '1:30', '90s', '1:00:00' → seconds."""
        import re
        text = text.strip()
        if not text:
            return 0
        # Format: HH:MM:SS or MM:SS
        m = re.match(r'(\d+):(\d+):(\d+)', text)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        m = re.match(r'(\d+):(\d+)', text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        # Format: Ns
        m = re.match(r'(\d+)\s*s', text)
        if m:
            return int(m.group(1))
        # Pure number
        try:
            return int(text)
        except ValueError:
            return 0
    
    async def _stage_script_analysis(self, stage: StageResult, config: Dict):
        """Stage 2: Research + Bible Generation (self-contained).
        
        LOCAL: topic, characters (from Stage 1), BIBLE_RULES constant
        API: AI researches topic accuracy, creates Character Profile Lock
        """
        topic = self.state.topic or config.get("topic", "")
        voice_enabled = config.get("voice_enabled", True)
        
        # ── Build character context from Stage 1 ──
        char_context = ""
        if self.state.characters:
            char_lines = []
            for c in self.state.characters:
                char_lines.append(f"  - {c.name}: {c.description}")
            char_context = "\n".join(char_lines)
        
        style_info = ""
        ai_data = {}
        # Get AI-detected style/tone from Stage 1
        dur_stage = self.state.stages.get("duration_estimate")
        if dur_stage and isinstance(dur_stage.data, dict):
            ai_data = dur_stage.data.get("ai_detected", {})
        if ai_data.get("style"):
            style_info += f"\nVisual Style: {ai_data['style']}"
        if ai_data.get("tone"):
            style_info += f"\nTone: {ai_data['tone']}"
        
        # ── Step 1: Research ──
        research_system = (
            "You are a content research expert. "
            "Task: Research and VERIFY accuracy of information related to the topic. "
            "Research cultural context, history, character authenticity. "
            "Return detailed research results."
        )
        type_instruction = PROJECT_TYPE_PROMPTS.get(config.get("project_type", ""), "")
        research_prompt = (
            f"Topic: {topic}\n\n"
            + (f"{type_instruction}\n" if type_instruction else "")
            + f"Characters detected:\n{char_context}\n"
            f"{style_info}\n\n"
            "RESEARCH REQUIREMENTS:\n"
            "1. Verify accuracy of information, cultural/historical context\n"
            "2. Research character details, personality, relationships\n"
            "3. Identify important visual elements (costumes, settings, props)\n"
            "4. Note details that must be accurate (era, customs, language)\n"
            "5. Suggest appropriate visual style\n"
        )
        
        research = await self._call_gemini_with_rotation(
            prompt=research_prompt, system=research_system,
            max_tokens=8000, temperature=0.3,
        )
        self.state.script_json = {"research": research}
        
        # ── Step 2: Bible ──
        bible_system = (
            "You are an AI video production expert (VEO). "
            "Task: Create a Production Bible for a video project. "
            "The Bible is the source of truth defining characters, settings, visual style.\n\n"
            f"{BIBLE_RULES}"
        )
        target_dur = self.state.target_duration or 0
        dur_mins = target_dur // 60
        dur_secs = target_dur % 60
        scene_count = self.state.scene_count or 0
        clip_dur = self.state.clip_duration or 8
        
        bible_prompt = (
            f"Topic: {topic}\n\n"
            f"{type_instruction}\n"
            f"{self._build_dimension_context(config)}\n"
            f"⚠️ MANDATORY DURATION: {dur_mins}:{dur_secs:02d} ({target_dur}s) = {scene_count} VEO clips x {clip_dur}s\n"
            f"IGNORE any duration mentioned in the input text. The ONLY valid duration is {target_dur}s from sidebar.\n\n"
            f"RESEARCH RESULTS:\n{research}\n\n"
            f"Characters detected:\n{char_context}\n"
            f"{style_info}\n\n"
            "CREATE PRODUCTION BIBLE WITH SECTIONS:\n\n"
            "## 1. PROJECT INFO\n"
            f"Topic, visual style, tone, target duration = {target_dur}s ({dur_mins}:{dur_secs:02d})\n\n"
            "## 2. CHARACTER PROFILE LOCK\n"
            "For EACH character — header format: ### Tên (Role)\n"
            "Do NOT use bold ** in headers. Do NOT prefix with 'Character N:'.\n"
            "ALL 8 fields with HEX + Text Description:\n"
            "- Age + Role\n- Height\n- Skin + Modifier (HEX + text)\n"
            "- Face features\n- Hair (HEX + text)\n- Clothing top (HEX + text)\n"
            "- Clothing bottom (HEX + text)\n- Accessories (HEX + text)\n\n"
            "## 3. SETTINGS\n"
            "Detailed description of main settings/backgrounds\n\n"
            "## 4. CHARACTER IMAGE PROMPT\n"
            "For each character: 1 detailed image generation prompt\n\n"
            "## 5. STORY STRUCTURE\n"
            f"Outline story in EXACTLY {scene_count} scenes fitting {target_dur}s total.\n"
            f"Each scene = {clip_dur}s. Do NOT use input's original duration.\n"
        )
        if voice_enabled:
            bible_prompt += (
                "\n## 6. DIALOGUE GUIDE\n"
                "Key dialogue lines for voice-over/narration per scene.\n"
                "Include speaker name, tone of voice, and line.\n"
            )
        else:
            bible_prompt += (
                "\nNOTE: This is a SILENT video (no voice-over/dialogue).\n"
                "Focus on visual storytelling — actions, expressions, environment.\n"
                "Do NOT include dialogue or narration in the Bible.\n"
            )
        
        bible = await self._call_gemini_with_rotation(
            prompt=bible_prompt, system=bible_system,
            max_tokens=16000, temperature=0.4,
        )
        
        self.state.script_json["bible"] = bible
        stage.script_json = bible
        stage.data = {
            "research": research,
            "bible": bible,
            "topic": topic,
        }
        
        # ── R2-4 Fix: Populate state.characters from Bible if still empty ──
        # Short input (<200 chars) skips AI detection, so characters list is []
        # Parse CHARACTER PROFILE LOCK to create CharacterData entries
        if not self.state.characters:
            char_profiles = self._extract_char_profiles_from_bible(bible)
            if char_profiles:
                for name, desc in char_profiles.items():
                    self.state.characters.append(CharacterData(name=name, description=desc))
                log.info(f"[Pipeline] R2-4: Populated {len(char_profiles)} characters from Bible (was empty)")
        
        # Save is handled by tab_project._save_stage_to_disk() on confirm
    
    async def _stage_scene_breakdown(self, stage: StageResult, config: Dict):
        """Stage 3: Two-Phase Prompt Generation (token-efficient).
        
        Phase A (API): AI generates compact scene descriptions
                       (scene type, shot, setting, character NAMES + actions)
                       WITHOUT full character profiles — saves tokens!
        Phase B (LOCAL): Code injects full character profiles from Bible
                         into each prompt automatically.
        """
        topic = self.state.topic or config.get("topic", "")
        voice_enabled = config.get("voice_enabled", True)
        
        # Get Bible from Stage 2 (may have been edited by user)
        bible = self.state.script_json.get("bible", "") if isinstance(self.state.script_json, dict) else ""
        if not bible:
            raise ValueError("No Bible data from Script stage -- run Stage 2 first")
        
        scene_count = self.state.scene_count or 10
        clip_duration = self.state.clip_duration or 8
        
        # ── Extract character profiles from Bible (LOCAL) ──
        char_profiles = self._extract_char_profiles_from_bible(bible)
        log.info(f"[Pipeline] Extracted {len(char_profiles)} character profiles from Bible")
        
        # Build char name list for AI
        char_names = ", ".join(char_profiles.keys()) if char_profiles else "unknown"
        
        # ══ PHASE A: API — Compact scene descriptions ══
        prompts_system = (
            "You are a VEO video prompts expert. "
            "Generate COMPACT scene descriptions for AI video generation.\n\n"
            "IMPORTANT: Do NOT include full character descriptions. "
            "Only use character NAMES — full profiles will be injected automatically.\n\n"
            f"{PROMPT_RULES_COMPACT}"
        )
        
        # Extract only story structure from Bible for API (saves tokens)
        story_section = self._extract_bible_section(bible, "STORY STRUCTURE")
        settings_section = self._extract_bible_section(bible, "SETTINGS")
        style_section = self._extract_bible_section(bible, "PROJECT INFO")
        
        bible_summary = ""
        if style_section:
            bible_summary += f"PROJECT INFO:\n{style_section}\n\n"
        if settings_section:
            bible_summary += f"SETTINGS:\n{settings_section}\n\n"
        if story_section:
            bible_summary += f"STORY STRUCTURE:\n{story_section}\n\n"
        
        # R2-3 Fix: Include research data for accuracy
        research_data = self.state.script_json.get("research", "") if isinstance(self.state.script_json, dict) else ""
        if research_data:
            # Truncate research to avoid token bloat — keep key facts
            bible_summary += f"RESEARCH HIGHLIGHTS:\n{research_data[:1500]}\n\n"
        
        if not bible_summary:
            bible_summary = bible[:2000]  # Fallback: first 2000 chars
        
        type_instruction = PROJECT_TYPE_PROMPTS.get(config.get("project_type", ""), "")
        prompts_user = (
            f"Topic: {topic}\n\n"
            + (f"{type_instruction}\n" if type_instruction else "")
            + f"{self._build_dimension_context(config)}\n"
            + f"BIBLE SUMMARY (character profiles omitted — injected automatically):\n{bible_summary}\n\n"
            f"Character names: {char_names}\n\n"
            f"REQUIREMENTS:\n"
            f"- Generate EXACTLY {scene_count} scene descriptions\n"
            f"- Total: {scene_count} x {clip_duration}s = {scene_count * clip_duration}s\n"
            f"- Each scene = 1 line, 1 blank line between scenes\n"
            f"- Use [CharacterName] tag for each character (e.g. [Tam])\n"
            f"- Do NOT write full character descriptions — just the NAME TAG + action\n"
            f"- At least 3-5 scenes use multi-segment (>>)\n"
            f"- Each scene MUST advance the story — NO filler/padding\n"
        )
        if voice_enabled:
            prompts_user += (
                f"- Include speaker expressions: mouth open speaking, listening, nodding\n"
                f"- Audio cues should describe ambient sound AND dialogue mood\n\n"
            )
        else:
            prompts_user += (
                f"- This is a SILENT video — NO dialogue, NO voice-over\n"
                f"- Focus on actions, expressions, visual storytelling only\n"
                f"- Audio should be ambient sound ONLY (nature, music, effects)\n\n"
            )
        prompts_user += (
            f"Scene type, context. Shot, Camera. Visual Style. Setting. "
            f"[CharName] action/expression. Audio of sound, "
            f"no text, no subtitles, no labels, no watermarks\n\n"
            f"EXAMPLE:\n"
            f"Opening scene. Wide shot, slow dolly in. Cinematic style. Vietnamese cottage at dawn. "
            f"[Tam] kneeling and digging through coal, weary expression. "
            f"Audio of birds chirping, no text, no subtitles, no labels, no watermarks\n"
        )
        
        raw_scenes = await self._call_gemini_with_rotation(
            prompt=prompts_user, system=prompts_system,
            max_tokens=16000, temperature=0.5,
        )
        
        # ══ PHASE B: LOCAL — Inject character profiles ══
        raw_prompts = self._inject_character_profiles(raw_scenes, char_profiles)
        
        # Parse prompts into scenes
        scenes = self._parse_text_prompts(raw_prompts)
        self.state.scenes = scenes
        
        # ══ PHASE C: Generate CHARACTER T2I prompts (for Stage 4) ══
        char_prompts = []
        if bible and self.client:
            type_instruction = PROJECT_TYPE_PROMPTS.get(config.get("project_type", ""), "")
            char_prompt_request = f"""Từ Production Bible sau, trích xuất CHARACTER IMAGE PROMPT cho TỪNG nhân vật.

{type_instruction}

Mỗi prompt là mô tả VISUAL chi tiết cho Text-to-Image (T2I), bao gồm:
- Mô tả ngoại hình đầy đủ (tuổi, chiều cao, da, mặt, tóc, trang phục, phụ kiện)
- Phong cách nghệ thuật
- Bối cảnh (background đơn giản, studio lighting)
- Camera angle: portrait, medium shot

Trả về mỗi prompt một dòng, ngăn cách bằng dòng trống.
Chỉ trả về prompts, không giải thích.

Bible:
{bible[:8000]}"""
            
            char_system = (
                "Bạn là chuyên gia tạo prompt hình ảnh nhân vật. "
                "Trích xuất và tạo T2I prompts chi tiết cho từng nhân vật từ Bible."
            )
            
            char_response = await self._call_gemini_with_rotation(
                prompt=char_prompt_request, system=char_system,
                max_tokens=4000, temperature=0.3,
            )
            
            for block in char_response.strip().split("\n\n"):
                block = block.strip()
                if block and len(block) > 20:
                    char_prompts.append(block)
            log.info(f"[Pipeline] Stage 3 Phase C: Generated {len(char_prompts)} character T2I prompts")
        
        # Fallback: use character descriptions from Stage 1
        characters = self.state.characters or []
        if not char_prompts and characters:
            for c in characters:
                desc = c.description or f"Portrait of {c.name}"
                char_prompts.append(
                    f"Professional portrait, {desc}, "
                    f"studio lighting, neutral background, ultra detailed, 8K"
                )
        
        # R2-1 Fix: Sync char_prompts count with state.characters
        # If Phase C generated MORE prompts than characters, create new CharacterData
        if len(char_prompts) > len(self.state.characters):
            for i in range(len(self.state.characters), len(char_prompts)):
                self.state.characters.append(CharacterData(
                    name=f"Character_{i+1}",
                    description="",
                    prompt=char_prompts[i],
                ))
            log.info(f"[Pipeline] R2-1: Created {len(char_prompts) - len(characters)} extra CharacterData from Phase C")
        
        # Update character data with generated prompts
        for i, c in enumerate(self.state.characters):
            if i < len(char_prompts):
                c.prompt = char_prompts[i]
        
        stage.scenes = scenes
        stage.characters = self.state.characters
        stage.prompts = [s.prompt for s in scenes]
        stage.data = {
            "raw_prompts": raw_prompts,
            "raw_scenes": raw_scenes,
            "prompt_count": len(scenes),
            "character_prompts": char_prompts,
            "character_prompt_count": len(char_prompts),
        }
        
        # Save is handled by tab_project._save_stage_to_disk() on confirm
    
    @staticmethod
    def _extract_bible_section(bible: str, section_name: str) -> str:
        """Extract a named section from Bible text.
        
        Looks for ## N. SECTION_NAME or ## SECTION_NAME headers.
        Returns content until next ## header.
        """
        lines = bible.split('\n')
        capturing = False
        result = []
        search_lower = section_name.lower()
        
        for line in lines:
            stripped = line.strip()
            # Check if this is a ## header
            if stripped.startswith('##') and not stripped.startswith('###'):
                header = stripped.lstrip('#').strip()
                # Remove numbering: "1. " or "2. "
                import re
                header_clean = re.sub(r'^\d+\.?\s*', '', header).strip().lower()
                if search_lower in header_clean:
                    capturing = True
                    continue
                elif capturing:
                    break  # Hit next ## section
            elif capturing:
                result.append(line)
        
        return '\n'.join(result).strip()
    
    def _extract_char_profiles_from_bible(self, bible: str) -> dict:
        """Extract character text-only profiles from Bible.
        
        ONLY parses within the CHARACTER PROFILE LOCK section (## 2.).
        Builds: {name: "text-only description (no HEX)"} dict.
        """
        import re
        profiles = {}
        
        # First, extract only the CHARACTER PROFILE LOCK section
        char_section = self._extract_bible_section(bible, "CHARACTER PROFILE LOCK")
        if not char_section:
            log.warning("[Pipeline] No CHARACTER PROFILE LOCK section found in Bible")
            return profiles
        
        current_name = None
        current_fields = []
        
        for line in char_section.split('\n'):
            stripped = line.strip()
            
            # Detect character header: ### 1. NAME (Role) or ### NAME
            # R4-3 Fix: Also detect bold headers: **Name** or **1. Name (Role)**
            is_header = stripped.startswith('###')
            if not is_header:
                bold_match = re.match(r'^\*\*\s*(?:\d+\.?\s*)?([^*]+?)\s*\*\*\s*$', stripped)
                if bold_match and not re.match(r'^\d+\.\s*\*\*', stripped):  # Skip numbered field lines
                    is_header = True
            
            if is_header:
                # Save previous character
                if current_name and current_fields:
                    profiles[current_name] = ", ".join(current_fields)
                    log.info(f"[Pipeline] Char profile: {current_name} ({len(current_fields)} fields)")
                
                # Parse name from header
                header = stripped.lstrip('#').strip()
                # Remove bold markers: **text** → text
                header = header.replace('**', '')
                header = re.sub(r'^\d+\.?\s*', '', header)  # Remove "1. "
                # Remove "Character N:" prefix from AI output
                header = re.sub(r'^Character\s*\d*:?\s*', '', header, flags=re.IGNORECASE)
                # Extract name before parentheses
                paren_idx = header.find('(')
                name = header[:paren_idx].strip() if paren_idx > 0 else header.strip()
                # Clean trailing colons/spaces
                name = name.rstrip(': ')
                
                current_name = name if name else None
                current_fields = []
                log.debug(f"[Pipeline] Parsed char header: '{stripped}' → name='{name}'")
                continue
            
            # Collect fields for current character
            if current_name and stripped:
                # Must look like a numbered field: "1. **Field:** value"
                if re.match(r'^\d+\.', stripped):
                    # Remove number prefix and bold markers
                    cleaned = re.sub(r'^\d+\.\s*', '', stripped)
                    cleaned = re.sub(r'\*\*[^*]+\*\*:?\s*', '', cleaned)
                    # Remove HEX codes: #FF6B00
                    cleaned = re.sub(r'#[0-9A-Fa-f]{6}\s*-?\s*', '', cleaned)
                    cleaned = cleaned.strip(' -.,')
                    if cleaned and len(cleaned) > 3:
                        current_fields.append(cleaned)
        
        # Save last character
        if current_name and current_fields:
            profiles[current_name] = ", ".join(current_fields)
            log.info(f"[Pipeline] Char profile: {current_name} ({len(current_fields)} fields)")
        
        return profiles
    
    @staticmethod
    def _strip_diacritics(text: str) -> str:
        """Remove Vietnamese diacritics for fuzzy matching."""
        import unicodedata
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()
    
    def _inject_character_profiles(self, raw_scenes: str, char_profiles: dict) -> str:
        """Inject full character profiles into compact scene descriptions.
        
        Phase B: Replace [CharName] tags with [CharName] CharName, full profile + action.
        Uses diacritic-insensitive matching: [Tam] matches profile "TẤM".
        """
        import re
        
        # Build diacritic-insensitive lookup: "tam" → ("TẤM", "profile...")
        name_lookup = {}
        for name, profile in char_profiles.items():
            stripped = self._strip_diacritics(name)
            name_lookup[stripped] = (name, profile)
        
        lines = raw_scenes.split('\n')
        result_lines = []
        
        # Negative prompts suffix
        neg_suffix = (
            ", no deformed limbs, no mutated faces, no extra fingers"
            ", no melting geometry, no color shifts, no texture distortion"
        )
        
        for line in lines:
            if not line.strip():
                result_lines.append(line)
                continue
            
            modified = line
            
            # Find all [Name] tags in this line
            tags = re.findall(r'\[([^\]]+)\]', modified)
            for tag_name in tags:
                tag_stripped = self._strip_diacritics(tag_name.strip())
                if tag_stripped in name_lookup:
                    real_name, profile = name_lookup[tag_stripped]
                    # Replace [TagName] with [RealName] RealName, profile,
                    old_tag = f"[{tag_name}]"
                    new_tag = f"[{real_name}] {real_name}, {profile},"
                    modified = modified.replace(old_tag, new_tag, 1)
            
            # Ensure negative prompts suffix is present
            if modified.strip() and 'no deformed' not in modified:
                modified = modified.rstrip('. ')
                modified += neg_suffix
            
            result_lines.append(modified)
        
        return '\n'.join(result_lines)
    
    def _parse_text_prompts(self, raw_text: str) -> list:
        """Parse plain text prompts (blank-line separated) into SceneData list."""
        # Keep blank lines for separator detection
        lines = [l.strip() for l in raw_text.strip().split("\n")]
        
        scenes = []
        current_prompt = []
        idx = 1
        
        for line in lines:
            if not line:
                # Blank line = separator between prompts
                if current_prompt:
                    prompt_text = "\n".join(current_prompt)
                    scenes.append(SceneData(
                        index=idx,
                        title=f"Scene {idx}",
                        prompt=prompt_text,
                        duration_s=self.state.clip_duration,
                    ))
                    idx += 1
                    current_prompt = []
            else:
                current_prompt.append(line)
        
        # Last prompt
        if current_prompt:
            prompt_text = "\n".join(current_prompt)
            scenes.append(SceneData(
                index=idx,
                title=f"Scene {idx}",
                prompt=prompt_text,
                duration_s=self.state.clip_duration,
            ))
        
        return scenes
    
    # ── Stages 4-7 ─────────────────────────────────────────────
    
    async def _stage_character_gen(self, stage: StageResult, config: Dict):
        """Stage 4: Character T2I — pass-through (prompts pre-generated by Stage 3).
        
        Stage 3 Phase C already generated character T2I prompts.
        This stage just reads them from state and packages for Queue tab.
        No Gemini AI call needed.
        
        Output: list of T2I prompts (editable), ready to send to Queue tab.
        """
        characters = self.state.characters or []
        
        # Read prompts already generated by Stage 3 Phase C
        char_prompts = [c.prompt for c in characters if c.prompt]
        
        # Also check Stage 3 data for character_prompts (backup)
        if not char_prompts:
            s3 = self.state.get_stage("scene_breakdown")
            if s3.data and "character_prompts" in s3.data:
                char_prompts = s3.data["character_prompts"]
                log.info(f"[Pipeline] Stage 4: Read {len(char_prompts)} prompts from Stage 3 data")
        
        if not char_prompts:
            raise ValueError("No character prompts — Stage 3 may not have generated them")
        
        log.info(f"[Pipeline] Stage 4: {len(char_prompts)} character T2I prompts (pre-generated by Stage 3)")
        
        stage.characters = characters
        stage.prompts = char_prompts
        stage.data = {
            "character_prompts": char_prompts,
            "character_names": [c.name for c in characters],
            "prompt_count": len(char_prompts),
            "mode": "T2I",
        }
    
    async def _stage_scene_image_gen(self, stage: StageResult, config: Dict):
        """Stage 5: Generate scene images using T2I/I2I.
        
        Takes VEO prompts from Stage 3 (already contain character profiles
        from Phase B injection) and adapts for T2I/I2I.
        
        Uses character reference images from Stage 4 for I2I mode
        to maintain visual consistency across all scenes.
        
        NOTE: Character descriptions are NOT re-injected here —
        Stage 3 Phase B already injects full Bible profiles into each prompt.
        """
        scenes = self.state.scenes
        if not scenes:
            raise ValueError("No scene data — run Stage 3 first")
        
        # ── Collect character reference images from Stage 4 ──
        char_refs = []  # list of {"name", "image_path", "description"}
        if self.state.characters:
            for c in self.state.characters:
                if c.image_path:
                    char_refs.append({
                        "name": c.name,
                        "image_path": c.image_path,
                        "description": c.description,
                    })
        
        has_char_images = len(char_refs) > 0
        
        scene_configs = []
        for s in scenes:
            # Stage 3 prompts already contain full character profiles (Phase B)
            # Only add T2I style suffix — do NOT re-inject character descriptions
            base = s.prompt or s.description or f"Scene {s.index}"
            base = base.replace(">>", "—")
            
            # R2-2 Fix: Use config-aware style suffix instead of hardcoded
            # R4-1 Fix: Normalize style to list (may be string from single-select)
            style_suffix = ""
            user_styles = config.get("style", [])
            if isinstance(user_styles, str):
                user_styles = [user_styles] if user_styles else []
            proj_type = config.get("project_type", "")
            if user_styles:
                style_suffix = f"{', '.join(user_styles)} style"
            elif proj_type == "animation":
                style_suffix = "3D animation style, Pixar quality, vibrant colors"
            else:
                style_suffix = "cinematic composition, detailed illustration"
            
            t2i_prompt = (
                f"{base}, "
                f"{style_suffix}, "
                f"professional lighting, 4K, highly detailed"
            )
            
            # Find character images by matching [tag] in prompt text
            # Uses diacritic-insensitive matching: [Tam] matches character "TẤM"
            import re as _re
            prompt_tags = {t.strip().lower() for t in _re.findall(r'\[([^\]]+)\]', base)}
            scene_char_images = []
            for cr in char_refs:
                cr_name_stripped = self._strip_diacritics(cr["name"])
                if any(self._strip_diacritics(tag) == cr_name_stripped for tag in prompt_tags):
                    scene_char_images.append(cr["image_path"])
            
            mode = "I2I" if scene_char_images else "T2I"
            
            scene_configs.append({
                "index": s.index,
                "prompt": t2i_prompt,
                "mode": mode,
                "reference_images": scene_char_images,
            })
        
        stage.scenes = scenes
        stage.prompts = [c["prompt"] for c in scene_configs]
        stage.data = {
            "scene_configs": scene_configs,
            "prompt_count": len(scene_configs),
            "char_ref_count": len(char_refs),
            "char_refs": char_refs,
            "mode": "I2I" if has_char_images else "T2I",
        }
    
    async def _stage_video_gen(self, stage: StageResult, config: Dict):
        """Stage 6: Generate video from scene images + prompts.
        
        Combines:
        - Scene images from Stage 5 (I2V input)
        - Scene prompts from Stage 3 (motion/action description)
        
        Output: list of I2V/T2V configs (editable), ready for Queue tab.
        """
        scenes = self.state.scenes
        if not scenes:
            raise ValueError("No scene data — run Stage 3 first")
        
        output_folder = config.get("output_folder", "")
        
        # Collect character reference images for R2V fallback
        char_images = [c.image_path for c in (self.state.characters or []) if c.image_path]
        
        video_configs = []
        for s in scenes:
            img_path = s.image_path or ""
            if img_path:
                mode = "I2V"  # Scene has Stage 5 image → I2V
            elif char_images:
                mode = "R2V"  # No scene image, but have char refs → R2V
            else:
                mode = "T2V"  # No images at all → T2V
            
            # Build scene tag matching Stage 5 registered tag name
            scene_tag = s.title.strip() if s.title else f"Scene_{s.index}"
            
            # Prepend [Scene_Tag] to prompt for tag auto-resolution in engine
            tagged_prompt = f"[{scene_tag}] {s.prompt}" if s.prompt else s.prompt
            
            video_configs.append({
                "index": s.index,
                "mode": mode,
                "prompt": tagged_prompt,
                "scene_tag": scene_tag,
                "image_path": img_path,
                "duration_s": s.duration_s,
                "output_folder": output_folder,
            })
        
        stage.scenes = scenes
        stage.prompts = [c["prompt"] for c in video_configs]
        # R2-5 Fix: Include voice_enabled in stage data for queue routing
        voice_enabled = config.get("voice_enabled", True)
        stage.data = {
            "video_configs": video_configs,
            "config_count": len(video_configs),
            "modes": list(set(c["mode"] for c in video_configs)),
            "voice_enabled": voice_enabled,
        }
    
    async def _stage_concat(self, stage: StageResult, config: Dict):
        """Stage 7: Concat all video clips into final video.
        
        1. Collects all video clip paths from scenes
        2. Writes FFmpeg concat list file
        3. Executes FFmpeg concat → final video
        4. Reports result for user review
        """
        import os
        import subprocess
        
        scenes = self.state.scenes
        if not scenes:
            raise ValueError("No scene data available")
        
        output_folder = config.get("output_folder", "")
        
        # Collect video paths
        clips = []
        missing = []
        for s in scenes:
            if s.video_path and os.path.isfile(s.video_path):
                clips.append({"index": s.index, "path": s.video_path, "duration_s": s.duration_s})
            else:
                missing.append(s.index)
        
        # Generate output path
        import re
        topic_raw = self.state.topic[:50] or "production"
        topic_slug = re.sub(r'[<>:"/\\|?*]', '', topic_raw).replace(" ", "_").strip("._")
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = os.path.join(output_folder, f"{topic_slug}_{ts}_final.mp4") if output_folder else f"{topic_slug}_{ts}_final.mp4"
        
        self.state.final_video_path = final_path
        
        # ── Execute FFmpeg concat if all clips ready ──
        concat_success = False
        concat_error = ""
        
        if clips and not missing:
            # Get FFmpeg path from centralized resolver
            try:
                from core.frame_extractor import get_ffmpeg_path
                ffmpeg_path = get_ffmpeg_path()
            except ImportError:
                ffmpeg_path = None
            
            if ffmpeg_path:
                try:
                    # Write concat list file
                    concat_list_path = os.path.join(
                        output_folder or os.path.dirname(clips[0]["path"]),
                        f"_concat_list_{ts}.txt"
                    )
                    with open(concat_list_path, "w", encoding="utf-8") as f:
                        for c in clips:
                            # FFmpeg concat requires forward slashes and escaped quotes
                            safe_path = c["path"].replace("\\", "/")
                            f.write(f"file '{safe_path}'\n")
                    
                    log.info(f"[Pipeline] Stage 7: FFmpeg concat list → {concat_list_path}")
                    log.info(f"[Pipeline] Stage 7: {len(clips)} clips → {final_path}")
                    
                    # Ensure output directory exists
                    os.makedirs(os.path.dirname(final_path) or ".", exist_ok=True)
                    
                    # Execute FFmpeg concat
                    cmd = [
                        ffmpeg_path,
                        "-y",                    # Overwrite output
                        "-f", "concat",          # Concat demuxer
                        "-safe", "0",            # Allow absolute paths
                        "-i", concat_list_path,   # Input list
                        "-c", "copy",            # Stream copy (no re-encode)
                        final_path,
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,  # 5 min timeout
                    )
                    
                    if result.returncode == 0 and os.path.isfile(final_path):
                        file_size_mb = os.path.getsize(final_path) / 1024 / 1024
                        log.info(f"[Pipeline] Stage 7: ✅ Concat complete → {final_path} ({file_size_mb:.1f} MB)")
                        concat_success = True
                    else:
                        concat_error = f"FFmpeg exit code {result.returncode}: {result.stderr[:500]}"
                        log.error(f"[Pipeline] Stage 7: ❌ FFmpeg failed: {concat_error}")
                    
                    # Cleanup concat list
                    try:
                        os.remove(concat_list_path)
                    except OSError:
                        pass
                        
                except subprocess.TimeoutExpired:
                    concat_error = "FFmpeg timeout (>5 min)"
                    log.error(f"[Pipeline] Stage 7: ❌ {concat_error}")
                except Exception as e:
                    concat_error = str(e)
                    log.error(f"[Pipeline] Stage 7: ❌ Concat error: {e}")
            else:
                concat_error = "FFmpeg not available — install or auto-download will be attempted"
                log.warning(f"[Pipeline] Stage 7: {concat_error}")
        
        stage.data = {
            "clips": clips,
            "missing_scenes": missing,
            "clip_count": len(clips),
            "total_clips": len(scenes),
            "final_output": final_path,
            "total_duration_s": sum(c["duration_s"] for c in clips),
            "ready": len(missing) == 0,
            "concat_success": concat_success,
            "concat_error": concat_error,
            "file_size_mb": round(os.path.getsize(final_path) / 1024 / 1024, 1) if concat_success and os.path.isfile(final_path) else 0,
        }
    
    # ── Shared Gemini Call with Rotation ───────────────────────
    
    async def _call_gemini_with_rotation(
        self, prompt: str, system: str,
        max_tokens: int = 8000, temperature: float = 0.7,
    ) -> str:
        """Call Gemini API with the same multi-key + model rotation as Enhancer.
        
        Rotation order:
        1. Current model → fallback models (via model_rotation)
        2. On 429: mark key exhausted → try next available key
        3. On 400: safety block → try next model
        4. Raises on complete exhaustion
        """
        from services.gemini_client import RateLimitError, GeminiAPIError
        
        api_key = self.api_key
        
        # Resolve models to try (same logic as PromptEnhancer)
        try:
            from services.model_rotation import get_rotation
            rotation = get_rotation()
            models_to_try = [rotation.get_model("pipeline")]
            for m in rotation.get_all_models():
                if m not in models_to_try:
                    models_to_try.append(m)
        except Exception:
            models_to_try = [self.model or "flash"]
        
        # Collect custom keys for fallback (hot-reload: reads fresh from Settings each call)
        custom_keys = []
        try:
            from services.ai_client_factory import get_ai_config
            cfg = get_ai_config()
            custom_keys = cfg.get("custom_keys", [])
            # If no api_key yet, try custom key from Settings
            if not api_key and cfg.get("api_key"):
                api_key = cfg["api_key"]
            log.debug(f"[Pipeline] Hot-reload: {len(custom_keys)} key(s) available")
        except Exception:
            pass
        
        if not api_key:
            raise ValueError("No API key available (profile key, Settings, or custom)")
        
        last_error = None
        max_rounds = 3  # Retry up to 3 rounds if all keys/models exhausted
        
        for round_num in range(max_rounds):
            if round_num > 0:
                wait_secs = 30 * round_num  # 30s, 60s
                log.info(f"[Pipeline] All keys exhausted — waiting {wait_secs}s for cooldown (round {round_num + 1}/{max_rounds})...")
                import asyncio
                await asyncio.sleep(wait_secs)
                # Reset exhausted models for retry
                try:
                    rotation.reset_exhausted("pipeline")
                except Exception:
                    pass
            
            for model in models_to_try:
                try:
                    result = await self.client.generate(
                        prompt=prompt,
                        system=system,
                        api_key=api_key,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        model=model,
                    )
                    
                    if result and result.strip():
                        # Track success
                        try:
                            rotation.increment_used("pipeline", model)
                        except Exception:
                            pass
                        log.info(f"[Pipeline] Gemini OK ({model}): {len(result)} chars")
                        return result.strip()
                        
                except RateLimitError as e:
                    last_error = e
                    # Mark model exhausted
                    try:
                        rotation.mark_exhausted("pipeline", model)
                    except Exception:
                        pass
                    # Mark key quota
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        err_str = str(e).lower()
                        if "per day" in err_str and "limit: 0" not in err_str:
                            qm.mark_rpd_blocked(api_key)
                        else:
                            qm.mark_rpm_blocked(api_key)
                        # Try next available key
                        if custom_keys:
                            next_key = qm.get_available_key(custom_keys)
                            if next_key:
                                api_key = next_key
                                log.info(f"[Pipeline] Switched to key ...{api_key[-8:]}")
                    except Exception:
                        pass
                    log.warning(f"[Pipeline] {model} rate limited (429), trying next...")
                    continue
                    
                except GeminiAPIError as e:
                    last_error = e
                    if e.status == 400:
                        log.warning(f"[Pipeline] {model} blocked (400), trying next model...")
                        continue
                    raise  # Other errors: propagate immediately
                    
                except Exception as e:
                    last_error = e
                    log.warning(f"[Pipeline] {model} failed: {e}")
                    continue  # Try next model (don't break retry rounds)
        
        # All rounds exhausted
        raise last_error or ValueError("All Gemini models exhausted after retries")
    
    # ── Helpers ────────────────────────────────────────────────
    
    @staticmethod
    def _extract_json(text: str) -> Dict:
        """Extract JSON from LLM response (may be wrapped in markdown)."""
        import re
        # Try to find JSON block in markdown
        json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        # Try direct parse
        text = text.strip()
        # Find first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning(f"[Pipeline] Failed to parse JSON from response: {text[:200]}")
            return {"error": "Failed to parse JSON", "raw": text}
