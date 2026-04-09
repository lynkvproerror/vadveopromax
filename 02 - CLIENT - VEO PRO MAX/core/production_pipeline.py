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
import re
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
class BackgroundData:
    """Background/setting definition for the project.
    
    Parsed from Bible §3 SETTINGS. Each background gets a T2I prompt
    for image generation, and a tag for [BG:tag] matching in prompts.
    """
    name: str                     # e.g. "Bờm's Village Hut"
    description: str = ""         # Full Bible description
    prompt: str = ""              # T2I prompt for image generation
    image_path: str = ""          # Generated background image path
    tag: str = ""                 # Normalized tag for matching


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
class VersionData:
    """One version of a video (Feature A/C: multi-version/multi-idea).
    
    Each version has its own Bible, scenes, prompts, and output paths.
    Characters may be shared (Feature A) or unique (Feature C/multi-idea).
    """
    index: int                                          # 0-based version index
    label: str = ""                                     # e.g. "Version 1", "Idea 1"
    bible: str = ""                                     # Version-specific Bible text
    scenes: List[SceneData] = field(default_factory=list)
    characters: List[CharacterData] = field(default_factory=list)
    final_video_path: str = ""
    output_subfolder: str = ""                          # e.g. "v1", "v2"


@dataclass
class EpisodeData:
    """One episode of a multi-part video (Feature B).
    
    Characters are SHARED across episodes (gen once, reuse).
    Each episode has its own scenes, prompts, and output paths.
    """
    index: int                                          # 0-based episode index
    label: str = ""                                     # e.g. "Tập 1"
    scenes: List[SceneData] = field(default_factory=list)
    final_video_path: str = ""
    output_subfolder: str = ""                          # e.g. "ep1", "ep2"


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
    backgrounds: List['BackgroundData'] = field(default_factory=list)  # BG images from Bible §3
    final_video_path: str = ""
    
    # ── Multi-Version (Feature A/C) ──
    video_count: int = 1                                # N versions to produce
    multi_idea: bool = False                            # True = C (different ideas), False = A (variations)
    versions: List[VersionData] = field(default_factory=list)
    current_version_idx: int = 0                        # Which version is currently active
    
    # ── Multi-Episode (Feature B) ──
    episode_enabled: bool = False
    episode_count: int = 1
    episodes: List[EpisodeData] = field(default_factory=list)
    current_episode_idx: int = 0                        # Which episode is currently active
    shared_characters: List[CharacterData] = field(default_factory=list)  # Shared across episodes
    
    def is_multi_version(self) -> bool:
        """True if producing multiple versions (Feature A or A+C)."""
        return self.video_count > 1
    
    def is_multi_episode(self) -> bool:
        """True if splitting into episodes (Feature B)."""
        return self.episode_enabled and self.episode_count > 1
    
    def get_active_version(self) -> Optional['VersionData']:
        """Get currently active version, or None if single-version."""
        if self.versions and self.current_version_idx < len(self.versions):
            return self.versions[self.current_version_idx]
        return None
    
    def get_active_episode(self) -> Optional['EpisodeData']:
        """Get currently active episode, or None if single-episode."""
        if self.episodes and self.current_episode_idx < len(self.episodes):
            return self.episodes[self.current_episode_idx]
        return None
    
    def activate_version(self, idx: int):
        """Switch to a different version — swap scenes/characters into active state."""
        if not self.versions or idx >= len(self.versions):
            return
        v = self.versions[idx]
        self.current_version_idx = idx
        self.scenes = v.scenes
        if v.characters:
            self.characters = v.characters
        log.info(f"[Pipeline] Activated version {idx + 1}/{len(self.versions)}: {v.label}")
    
    def activate_episode(self, idx: int):
        """Switch to a different episode — swap scenes, keep shared characters."""
        if not self.episodes or idx >= len(self.episodes):
            return
        ep = self.episodes[idx]
        self.current_episode_idx = idx
        self.scenes = ep.scenes
        # Characters are SHARED — restore from shared pool
        if self.shared_characters:
            self.characters = self.shared_characters
        log.info(f"[Pipeline] Activated episode {idx + 1}/{len(self.episodes)}: {ep.label}")
    
    def save_active_version(self):
        """Save current scenes/characters back to the active VersionData."""
        v = self.get_active_version()
        if v:
            v.scenes = self.scenes
            v.characters = self.characters
    
    def save_active_episode(self):
        """Save current scenes back to the active EpisodeData."""
        ep = self.get_active_episode()
        if ep:
            ep.scenes = self.scenes
    
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
            # Multi-version / Multi-episode
            "video_count": self.video_count,
            "multi_idea": self.multi_idea,
            "current_version_idx": self.current_version_idx,
            "versions": [
                {
                    "index": v.index, "label": v.label, "bible": v.bible,
                    "output_subfolder": v.output_subfolder,
                    "final_video_path": v.final_video_path,
                    "scenes": [
                        {"index": s.index, "title": s.title, "description": s.description,
                         "prompt": s.prompt, "character_ref": s.character_ref,
                         "duration_s": s.duration_s, "image_path": s.image_path,
                         "video_path": s.video_path}
                        for s in v.scenes
                    ],
                    "characters": [
                        {"name": c.name, "description": c.description,
                         "prompt": c.prompt, "image_path": c.image_path}
                        for c in v.characters
                    ],
                }
                for v in self.versions
            ],
            "episode_enabled": self.episode_enabled,
            "episode_count": self.episode_count,
            "current_episode_idx": self.current_episode_idx,
            "episodes": [
                {
                    "index": ep.index, "label": ep.label,
                    "output_subfolder": ep.output_subfolder,
                    "final_video_path": ep.final_video_path,
                    "scenes": [
                        {"index": s.index, "title": s.title, "description": s.description,
                         "prompt": s.prompt, "character_ref": s.character_ref,
                         "duration_s": s.duration_s, "image_path": s.image_path,
                         "video_path": s.video_path}
                        for s in ep.scenes
                    ],
                }
                for ep in self.episodes
            ],
            "shared_characters": [
                {"name": c.name, "description": c.description,
                 "prompt": c.prompt, "image_path": c.image_path}
                for c in self.shared_characters
            ],
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
        
        # Restore multi-version state
        state.video_count = data.get("video_count", 1)
        state.multi_idea = data.get("multi_idea", False)
        state.current_version_idx = data.get("current_version_idx", 0)
        for vd in data.get("versions", []):
            v = VersionData(
                index=vd.get("index", 0),
                label=vd.get("label", ""),
                bible=vd.get("bible", ""),
                output_subfolder=vd.get("output_subfolder", ""),
                final_video_path=vd.get("final_video_path", ""),
            )
            for sd in vd.get("scenes", []):
                v.scenes.append(SceneData(
                    index=sd.get("index", 0), title=sd.get("title", ""),
                    description=sd.get("description", ""), prompt=sd.get("prompt", ""),
                    character_ref=sd.get("character_ref", ""),
                    duration_s=sd.get("duration_s", 8.0),
                    image_path=sd.get("image_path", ""),
                    video_path=sd.get("video_path", ""),
                ))
            for cd in vd.get("characters", []):
                v.characters.append(CharacterData(
                    name=cd.get("name", ""), description=cd.get("description", ""),
                    prompt=cd.get("prompt", ""), image_path=cd.get("image_path", ""),
                ))
            state.versions.append(v)
        
        # Restore multi-episode state
        state.episode_enabled = data.get("episode_enabled", False)
        state.episode_count = data.get("episode_count", 1)
        state.current_episode_idx = data.get("current_episode_idx", 0)
        for ed in data.get("episodes", []):
            ep = EpisodeData(
                index=ed.get("index", 0),
                label=ed.get("label", ""),
                output_subfolder=ed.get("output_subfolder", ""),
                final_video_path=ed.get("final_video_path", ""),
            )
            for sd in ed.get("scenes", []):
                ep.scenes.append(SceneData(
                    index=sd.get("index", 0), title=sd.get("title", ""),
                    description=sd.get("description", ""), prompt=sd.get("prompt", ""),
                    character_ref=sd.get("character_ref", ""),
                    duration_s=sd.get("duration_s", 8.0),
                    image_path=sd.get("image_path", ""),
                    video_path=sd.get("video_path", ""),
                ))
            state.episodes.append(ep)
        
        for cd in data.get("shared_characters", []):
            state.shared_characters.append(CharacterData(
                name=cd.get("name", ""), description=cd.get("description", ""),
                prompt=cd.get("prompt", ""), image_path=cd.get("image_path", ""),
            ))
        
        # ★ Re-link state.scenes to active version/episode after restore.
        # Without this, state.scenes is a separate copy that doesn't share
        # references with version.scenes — causing confirm handlers to see
        # stale video_path="" and re-queue already-completed videos.
        if state.versions:
            state.activate_version(state.current_version_idx)
        elif state.episodes:
            state.activate_episode(state.current_episode_idx)
        
        return state


# ── Pipeline Orchestrator ─────────────────────────────────────


STAGE_ORDER = [
    "duration_estimate",
    "bible_gen",
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
        result = await pipeline.run_stage("bible_gen", config)
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
            elif stage_name == "bible_gen":
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
            elif stage_name == "bible_gen":
                await self._stage_bible_gen(stage, config)
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
        
        # Multi-version / Multi-episode config from sidebar
        self.state.video_count = config.get("video_count", 1)
        self.state.multi_idea = config.get("multi_idea", False)
        self.state.episode_enabled = config.get("episode_enabled", False)
        self.state.episode_count = config.get("episode_count", 1) if self.state.episode_enabled else 1
        
        stage.scene_count = scene_count
        stage.clip_duration = clip_duration
        stage.data = {
            "scene_count": scene_count,
            "clip_duration": clip_duration,
            "target_duration": target_duration,
            "topic": ai_title or topic[:100],
            "source": "ai_detected" if detected else "sidebar_defaults",
            "ai_detected": detected,
            "video_count": self.state.video_count,
            "multi_idea": self.state.multi_idea,
            "episode_enabled": self.state.episode_enabled,
            "episode_count": self.state.episode_count,
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
    
    async def _stage_bible_gen(self, stage: StageResult, config: Dict):
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
        
        # ── Step 1.5: Dialogue Extraction & Analysis (when voice enabled) ──
        extracted_dialogues = []
        dialogue_analysis = ""
        if voice_enabled:
            extracted_dialogues = self._extract_dialogues_from_script(topic)
            if extracted_dialogues:
                log.info(f"[Pipeline] Found {len(extracted_dialogues)} existing dialogues → running AI analysis")
                dialogue_analysis = await self._analyze_dialogues(
                    extracted_dialogues, topic, config
                )
                self.state.script_json["dialogue_analysis"] = dialogue_analysis
                self.state.script_json["extracted_dialogues"] = extracted_dialogues
        
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
            if dialogue_analysis:
                # Script has existing dialogues → use analyzed/improved version
                bible_prompt += (
                    "\n## 6. DIALOGUE GUIDE\n"
                    "⚠️ PHÂN TÍCH LỜI THOẠI TỪ KỊCH BẢN GỐC (bắt buộc tuân thủ):\n"
                    f"{dialogue_analysis}\n\n"
                    "NGUYÊN TẮC:\n"
                    "- ✅ GIỮ NGUYÊN: Sao chép CHÍNH XÁC câu thoại gốc vào Dialogue Guide\n"
                    "- 🔧 CẢI THIỆN: Dùng phiên bản cải thiện thay cho câu gốc\n"
                    "- ➕ BỔ SUNG: Thêm câu thoại mới vào đúng vị trí cảnh\n"
                    "- Mỗi câu thoại PHẢI có: Speaker Name, Tone of Voice, Line\n"
                )
            else:
                # No existing dialogues → AI creates fresh dialogue
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
            "extracted_dialogues": extracted_dialogues,
            "dialogue_analysis": dialogue_analysis,
        }
        
        # ── R5-1 Fix: Always merge Bible characters (not just when empty) ──
        # Bible may introduce new characters (e.g. Phú Bà) not found by Stage 1 AI detection.
        # Merge ALL Bible chars into state.characters using diacritic-insensitive dedup.
        char_profiles = self._extract_char_profiles_from_bible(bible)
        if char_profiles:
            existing_names = {self._strip_diacritics(c.name) for c in self.state.characters}
            merged_count = 0
            for name, desc in char_profiles.items():
                if self._strip_diacritics(name) not in existing_names:
                    self.state.characters.append(CharacterData(name=name, description=desc))
                    existing_names.add(self._strip_diacritics(name))
                    merged_count += 1
                    log.info(f"[Pipeline] R5-1: Merged Bible character '{name}' into state")
                else:
                    # Update description if existing one is sparse
                    for c in self.state.characters:
                        if self._strip_diacritics(c.name) == self._strip_diacritics(name):
                            if not c.description or len(c.description) < len(desc):
                                c.description = desc
                            break
            if merged_count:
                log.info(f"[Pipeline] R5-1: Merged {merged_count} new characters from Bible")
            else:
                log.info(f"[Pipeline] R5-1: All {len(char_profiles)} Bible characters already exist")
        
        # ── Multi-Idea: Generate N different Bibles (Feature C) ──
        version_bibles = [bible]  # First Bible is always the main one
        video_count = self.state.video_count
        
        if self.state.multi_idea and video_count > 1:
            log.info(f"[Pipeline] Multi-Idea mode: generating {video_count - 1} additional Bibles")
            for vi in range(1, video_count):
                variation_prompt = (
                    f"{bible_prompt}\n\n"
                    f"⚠️ VARIATION {vi + 1}/{video_count}: Create a COMPLETELY DIFFERENT approach to this topic.\n"
                    f"- MUST keep the same characters and general subject\n"
                    f"- Change: story angle, tone, narrative style, scene order, visual approach\n"
                    f"- Previous Bible #{vi} summary: {bible[:300]}...\n"
                    f"- Do NOT repeat the exact same story — find a FRESH perspective\n"
                    f"- Duration and scene count MUST be identical: {scene_count} scenes x {clip_dur}s\n"
                )
                alt_bible = await self._call_gemini_with_rotation(
                    prompt=variation_prompt, system=bible_system,
                    max_tokens=16000, temperature=0.6 + (vi * 0.05),  # Higher temp for diversity
                )
                version_bibles.append(alt_bible)
                log.info(f"[Pipeline] Multi-Idea: Bible {vi + 1}/{video_count} generated ({len(alt_bible)} chars)")
        
        # ── Create VersionData objects ──
        self.state.versions.clear()
        if video_count > 1:
            for vi, vbible in enumerate(version_bibles):
                label = f"Idea {vi + 1}" if self.state.multi_idea else f"Version {vi + 1}"
                self.state.versions.append(VersionData(
                    index=vi,
                    label=label,
                    bible=vbible,
                    output_subfolder=f"v{vi + 1}",
                    characters=list(self.state.characters),  # Copy for each version
                ))
            log.info(f"[Pipeline] Created {len(self.state.versions)} VersionData objects")
        
        # ── Episode Split (Feature B) ──
        if self.state.is_multi_episode():
            ep_count = self.state.episode_count
            log.info(f"[Pipeline] Episode mode: marking {ep_count} episodes for Stage 3 split")
            self.state.episodes.clear()
            for ei in range(ep_count):
                self.state.episodes.append(EpisodeData(
                    index=ei,
                    label=f"Tập {ei + 1}",
                    output_subfolder=f"ep{ei + 1}",
                ))
            # Store shared characters for reuse across episodes
            self.state.shared_characters = list(self.state.characters)
        
        # Update stage data with version/episode info
        stage.data["version_count"] = len(version_bibles)
        stage.data["episode_count"] = self.state.episode_count if self.state.is_multi_episode() else 1
        stage.data["multi_idea"] = self.state.multi_idea
        
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
            # Include dialogue context from Bible if available
            dialogue_section = self._extract_bible_section(bible, "DIALOGUE GUIDE")
            if dialogue_section:
                prompts_user += (
                    f"- Include speaker expressions matching DIALOGUE GUIDE from Bible:\n"
                    f"  Speaker = mouth open speaking, matching emotion from their dialogue line\n"
                    f"  Listener = attentive listening, nodding, reaction expression\n"
                    f"- Audio cues should describe ambient sound AND dialogue mood\n"
                    f"- Reference DIALOGUE GUIDE for accurate character emotions per scene\n\n"
                )
            else:
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
        
        # ══ PHASE B2: Verify extended characters ══
        # Scan ALL [CharName] tags in AI-generated scenes and ensure they exist
        # in state.characters. Add missing ones so Stage 4 generates images for ALL.
        import re as _re_b2
        all_tags = set()
        for line in raw_scenes.split('\n'):
            tags = _re_b2.findall(r'\[([^\]]+)\]', line)
            for tag in tags:
                all_tags.add(tag.strip())
        
        # Build lookup of existing characters (diacritic-insensitive)
        existing_names = {}
        for c in (self.state.characters or []):
            existing_names[self._strip_diacritics(c.name)] = c.name
        
        # R5-2: Blacklist non-character tags that AI may generate
        _NON_CHAR_TAGS = {
            'narrator', 'voiceover', 'voice over', 'camera', 'bgm', 'sfx',
            'music', 'text', 'text overlay', 'title', 'title card',
            'sound', 'audio', 'fade', 'transition', 'cut',
        }
        
        # Find missing characters (with blacklist filter)
        extended_chars = []
        for tag in sorted(all_tags):
            # Skip blacklisted non-character tags
            if tag.strip().lower() in _NON_CHAR_TAGS:
                log.info(f"[Pipeline] Phase B2: Skipped blacklisted tag: '{tag}'")
                continue
            tag_stripped = self._strip_diacritics(tag)
            if tag_stripped not in existing_names:
                # New character — add to state with enriched description from Bible
                desc = f"Supporting character: {tag}"
                # R5-4: Try to get richer description from Bible char_profiles
                for prof_name, prof_desc in char_profiles.items():
                    if self._strip_diacritics(prof_name) == tag_stripped:
                        desc = prof_desc
                        log.info(f"[Pipeline] R5-4: Enriched '{tag}' desc from Bible profile")
                        break
                new_char = CharacterData(
                    name=tag,
                    description=desc,
                )
                self.state.characters.append(new_char)
                existing_names[tag_stripped] = tag
                extended_chars.append(tag)
                log.info(f"[Pipeline] Phase B2: Extended character detected: '{tag}'")
        
        if extended_chars:
            log.warning(
                f"[Pipeline] Phase B2: {len(extended_chars)} extended characters detected "
                f"and added: {extended_chars}. Stage 4 will generate images for ALL characters."
            )
            # Store in stage data for UI notification
            self._extended_chars_detected = extended_chars
        else:
            self._extended_chars_detected = []
        
        # Parse prompts into scenes
        scenes = self._parse_text_prompts(raw_prompts)
        self.state.scenes = scenes
        
        # R5-6: Warn if AI generated fewer scenes than requested
        if len(scenes) < scene_count:
            log.warning(
                f"[Pipeline] ⚠️ Scene count mismatch: requested {scene_count}, "
                f"got {len(scenes)}. AI may have merged scenes."
            )
        
        # ══ PHASE C: Generate CHARACTER T2I prompts (for Stage 4) ══
        char_prompts = []
        if bible and self.client:
            type_instruction = PROJECT_TYPE_PROMPTS.get(config.get("project_type", ""), "")
            char_prompt_request = f"""Từ Production Bible sau, trích xuất CHARACTER REFERENCE SHEET PROMPT cho TỪNG nhân vật.

{type_instruction}

Mỗi prompt là CHARACTER TURNAROUND MODEL SHEET cho Text-to-Image (T2I):

⚠️ BẮT BUỘC — LAYOUT 4-VIEW TRÊN 1 ẢNH DUY NHẤT (16:9 ngang):
- Chia ảnh thành 4 panel rõ ràng, mỗi panel có LABEL TEXT phía trên:
  • Panel 1 (trái): "FRONT VIEW" — toàn thân chính diện, nhìn thẳng camera
  • Panel 2 (giữa-trái): "LEFT ¾ VIEW" — góc ¾ từ bên trái
  • Panel 3 (giữa-phải): "RIGHT ¾ VIEW" — góc ¾ từ bên phải
  • Panel 4 (phải): "BACK VIEW" — phía sau lưng nhân vật
- Tất cả 4 panel CÙNG tỉ lệ, CÙNG kích thước, CÙNG nhân vật
- Trong prompt PHẢI có cụm: "character turnaround model sheet, 4-view panel layout"
- Mô tả ngoại hình đầy đủ (tuổi, chiều cao, da, mặt, tóc, trang phục, phụ kiện)
- Phong cách nghệ thuật matching Bible visual style
- PLAIN WHITE BACKGROUND ONLY — NO environment, NO scene, NO props
- Professional studio lighting, clean edges, concept art quality
- Aspect ratio: 16:9 horizontal ONLY

Trả về mỗi prompt một dòng, ngăn cách bằng dòng trống.
Chỉ trả về prompts, không giải thích.

Bible:
{bible[:8000]}"""
            
            char_system = (
                "Bạn là chuyên gia tạo character turnaround model sheet prompts. "
                "Tạo prompt mô tả CHÍNH XÁC 4-panel layout (FRONT, LEFT ¾, RIGHT ¾, BACK) "
                "trên 1 ảnh duy nhất, nền trắng, tỉ lệ 16:9 ngang, concept art quality. "
                "Mỗi prompt PHẢI bắt đầu bằng 'Character turnaround model sheet'."
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
                desc = c.description or f"character {c.name}"
                char_prompts.append(
                    f"Character turnaround model sheet, 4-view panel layout, "
                    f"FRONT VIEW (full body facing camera), LEFT ¾ VIEW, RIGHT ¾ VIEW, BACK VIEW, "
                    f"{desc}, plain white background, professional studio lighting, "
                    f"concept art quality, ultra detailed, 16:9 horizontal layout"
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
        
        # R5-3: Name-based prompt mapping (not blind index)
        _used_prompts = set()  # Track which prompts have been matched
        for c in self.state.characters:
            c_stripped = self._strip_diacritics(c.name)
            matched = False
            for pi, p in enumerate(char_prompts):
                if pi in _used_prompts:
                    continue
                p_stripped = self._strip_diacritics(p)
                if c_stripped in p_stripped or c.name.lower() in p.lower():
                    c.prompt = p
                    _used_prompts.add(pi)
                    matched = True
                    log.info(f"[Pipeline] R5-3: Name-matched prompt for '{c.name}'")
                    break
            if not matched:
                # Fallback: take first unmatched prompt by index
                for pi, p in enumerate(char_prompts):
                    if pi not in _used_prompts:
                        c.prompt = p
                        _used_prompts.add(pi)
                        log.warning(f"[Pipeline] R5-3: Fallback index-match for '{c.name}' (idx={pi})")
                        break
        
        # ══ PHASE C2: Fallback prompts for extended characters ══
        # Phase B2 detected secondary characters (e.g. [Official]) and added them
        # to state.characters, but Phase C only generates prompts for Bible-defined
        # characters. Generate fallback T2I prompts for any character without one.
        visual_style = self._extract_bible_section(bible, "PROJECT INFO") or ""
        style_match = re.search(r'Visual Style[:\s]*(.+)', visual_style, re.IGNORECASE)
        style_desc = style_match.group(1).strip() if style_match else "detailed illustration"
        
        c2_count = 0
        # Group keywords: these should generate multi-character scenes, not turnaround sheets
        _GROUP_KW = {'villagers', 'crowd', 'soldiers', 'guards', 'children', 'people',
                     'monks', 'servants', 'workers', 'merchants', 'elders', 'townspeople',
                     'dân làng', 'đám đông', 'lính', 'trẻ em', 'nhóm', 'người dân',
                     'quân lính', 'đầy tớ', 'thương nhân', 'bô lão'}
        for c in self.state.characters:
            if not c.prompt:
                name_lower = c.name.lower()
                is_group = any(kw in name_lower for kw in _GROUP_KW)
                desc = c.description or f'supporting character: {c.name}'
                
                if is_group:
                    # Group scene: multiple varied characters, not a turnaround sheet
                    c.prompt = (
                        f"Group illustration of {c.name}, 3-5 diverse characters with varied ages, "
                        f"heights, poses and expressions, {desc}, {style_desc}, "
                        f"plain white background, full body view facing camera, "
                        f"concept art quality, character lineup, ultra detailed, 16:9 horizontal layout"
                    )
                    c2_count += 1
                    log.info(f"[Pipeline] Phase C2: Generated GROUP prompt for '{c.name}'")
                else:
                    # Individual character turnaround sheet
                    c.prompt = (
                        f"Character turnaround model sheet, 4-view panel layout, "
                        f"FRONT VIEW (full body facing camera), LEFT ¾ VIEW, RIGHT ¾ VIEW, BACK VIEW, "
                        f"{c.name}, {desc}, "
                        f"{style_desc}, "
                        f"plain white background, professional studio lighting, "
                        f"concept art quality, ultra detailed, 16:9 horizontal layout"
                    )
                    c2_count += 1
                    log.info(f"[Pipeline] Phase C2: Generated fallback prompt for '{c.name}'")
        if c2_count:
            log.info(f"[Pipeline] Phase C2: {c2_count} extended characters got fallback T2I prompts")
            char_prompts = [c.prompt for c in self.state.characters if c.prompt]
        
        # ══ PHASE D: Background image prompts from Bible §3 SETTINGS ══
        settings_section = self._extract_bible_section(bible, "SETTINGS")
        bg_entries = self._parse_settings_to_backgrounds(settings_section, style_desc)
        self.state.backgrounds = bg_entries
        bg_prompts = [bg.prompt for bg in bg_entries if bg.prompt]
        log.info(f"[Pipeline] Phase D: {len(bg_entries)} backgrounds parsed, {len(bg_prompts)} T2I prompts generated")
        
        # ══ PHASE E: Inject [BG:Location] tags into scene prompts ══
        if bg_entries:
            raw_prompts = self._inject_background_tags(raw_prompts, bg_entries)
            # Re-parse with BG tags
            scenes = self._parse_text_prompts(raw_prompts)
            self.state.scenes = scenes
            log.info(f"[Pipeline] Phase E: Injected [BG:] tags into {len(scenes)} scene prompts")
        
        stage.scenes = scenes
        stage.characters = self.state.characters
        stage.prompts = [s.prompt for s in scenes]
        
        # ══ Build JSON scene_configs (rich structured data) ══
        import re as _re_sc
        _bible_dialogues = self._extract_bible_section(bible, "DIALOGUE GUIDE") or ""
        _bible_settings = self._extract_bible_section(bible, "SETTINGS") or ""
        _settings_names = [bg.name for bg in (self.state.backgrounds or [])] if hasattr(self.state, 'backgrounds') and self.state.backgrounds else []
        
        scene_configs = []
        for s in scenes:
            prompt = s.prompt or ""
            
            # --- Extract characters from [Tag] ---
            chars_in_scene = [t.strip() for t in _re_sc.findall(r'\[([^\]]+)\]', prompt)
                              if t.strip().lower() not in _NON_CHAR_TAGS
                              and not t.strip().startswith('BG:')]
            
            # --- Determine type ---
            n_chars = len(chars_in_scene)
            if n_chars == 0:
                sc_type = "landscape"
            elif n_chars == 1:
                sc_type = "solo"
            elif n_chars == 2:
                sc_type = "duo"
            else:
                sc_type = "group"
            
            # --- Detect text overlay ---
            has_overlay = bool(_re_sc.search(r'(?i)text\s+overlay|stylized\s+text', prompt))
            overlay_content = None
            if has_overlay:
                sc_type = "text_overlay"
                overlay_match = _re_sc.search(r'["\u201c](.+?)["\u201d]', prompt)
                overlay_content = overlay_match.group(1) if overlay_match else None
            
            # --- Extract shot type ---
            shot_type = "medium shot"
            for st in ['extreme close-up', 'close-up', 'medium close-up', 'medium shot',
                        'wide shot', 'establishing shot', 'aerial shot', 'pov shot']:
                if st.lower() in prompt.lower():
                    shot_type = st
                    break
            
            # --- Extract camera movement ---
            camera_movement = "static"
            for cm in ['slow dolly in', 'dolly in', 'dolly out', 'pan left', 'pan right',
                        'tilt up', 'tilt down', 'zoom in', 'zoom out', 'tracking shot',
                        'crane shot', 'orbit', 'push in', 'pull back', 'jib shot']:
                if cm.lower() in prompt.lower():
                    camera_movement = cm
                    break
            
            # --- Extract scene type ---
            scene_type = "action"
            if s.index == 1:
                scene_type = "establishing"
            elif s.index == len(scenes):
                scene_type = "closing"
            elif has_overlay:
                scene_type = "text_overlay"
            elif 'montage' in prompt.lower() or 'split screen' in prompt.lower():
                scene_type = "montage"
            elif any(kw in prompt.lower() for kw in ['speaking', 'mouth open', 'dialogue', 'whispering', 'consulting']):
                scene_type = "dialogue"
            elif any(kw in prompt.lower() for kw in ['transition', 'fade']):
                scene_type = "transition"
            
            # --- Extract setting ---
            setting = ""
            # Try to match Bible §3 settings
            for sname in _settings_names:
                if self._strip_diacritics(sname).lower() in self._strip_diacritics(prompt).lower():
                    setting = sname
                    break
            if not setting:
                # Extract from prompt context
                setting_patterns = [
                    r'(?:interior|exterior)[.,]?\s*([A-Z][^.]+)',
                    r"([A-Z][\w\s']+(?:mansion|hut|village|path|field|pond|courtyard|interior))",
                ]
                for sp in setting_patterns:
                    m = _re_sc.search(sp, prompt)
                    if m:
                        setting = m.group(1).strip().rstrip(',')
                        break
            
            # --- Extract character actions & emotions ---
            char_actions = {}
            char_emotions = {}
            for ch in chars_in_scene:
                # Find text after [CharName] until next [CharName] or period
                pattern = r'\[' + re.escape(ch) + r'\]\s*([^\[]+?)(?=\[|Audio|no text|$)'
                m = _re_sc.search(pattern, prompt)
                if m:
                    action_text = m.group(1).strip().rstrip(',. ')
                    char_actions[ch] = action_text
                    # Extract emotion keywords
                    emotion_kw = []
                    for emo in ['content', 'happy', 'sad', 'angry', 'worried', 'smug',
                                'desperate', 'frustrated', 'calm', 'joyful', 'serene',
                                'scheming', 'greedy', 'avaricious', 'exasperated',
                                'knowing', 'disapproving', 'triumphant', 'mocking',
                                'amused', 'troubled', 'doubtful']:
                        if emo in action_text.lower():
                            emotion_kw.append(emo)
                    if emotion_kw:
                        char_emotions[ch] = ', '.join(emotion_kw)
            
            # --- Extract props ---
            props = []
            for prop in ['fan', 'gold coins', 'sticky rice', 'xôi', 'quạt mo',
                         'cage', 'bird', 'raft', 'lim wood', 'pond', 'bowl',
                         'firewood', 'cattle', 'buffaloes', 'cows']:
                if prop.lower() in prompt.lower():
                    props.append(prop)
            
            # --- Extract audio cue ---
            audio_cue = ""
            audio_match = _re_sc.search(r'Audio of ([^,]+(?:,[^,]+)*?)(?:,\s*no text|$)', prompt)
            if audio_match:
                audio_cue = audio_match.group(1).strip()
            
            # --- Extract dialogue from Bible §6 ---
            dialogue = None
            if _bible_dialogues:
                scene_dlg_match = _re_sc.search(
                    rf'\*\*Scene {s.index}[^*]*\*\*[\s\S]*?\*\*([^*]+)\s*\(([^)]+)\)\*\*\s*[:"]\s*["\u201c]?(.+?)["\u201d]?\s*$',
                    _bible_dialogues, _re_sc.MULTILINE
                )
                if scene_dlg_match:
                    dialogue = {
                        "speaker": scene_dlg_match.group(1).strip(),
                        "tone": scene_dlg_match.group(2).strip(),
                        "line": scene_dlg_match.group(3).strip().strip('"\u201c\u201d'),
                    }
            
            # --- Extract tone from Bible §5 ---
            tone = ""
            tone_match = _re_sc.search(
                rf'\*\*Scene {s.index}\b[^*]*\*\*[\s\S]*?\*\*Tone:\*\*\s*(.+)',
                bible, _re_sc.MULTILINE
            )
            if tone_match:
                tone = tone_match.group(1).strip()
            
            # --- Extract negative prompt ---
            neg_prompt = ""
            neg_match = _re_sc.search(r'(no text,\s*no subtitles[^\n]+)', prompt)
            if neg_match:
                neg_prompt = neg_match.group(1).strip()
            
            # --- Extract visual style (first line portion) ---
            vs = style_desc if style_desc else ""
            vs_match = _re_sc.match(r'^([^.]+\.\s*[^.]+\.\s*[^.]+\.)', prompt)
            if vs_match:
                vs = vs_match.group(1).strip()
            
            scene_configs.append({
                "scene_index": s.index,
                "scene_type": scene_type,
                "type": sc_type,
                "shot_type": shot_type,
                "camera_movement": camera_movement,
                "visual_style": vs,
                "setting": setting,
                "setting_location": setting,
                "characters": chars_in_scene,
                "character_actions": char_actions,
                "character_emotions": char_emotions,
                "props": props,
                "audio_cue": audio_cue,
                "dialogue": dialogue,
                "tone": tone,
                "has_text_overlay": has_overlay,
                "text_overlay_content": overlay_content,
                "duration_s": s.duration_s,
                "negative_prompt": neg_prompt,
                "prompt_text": prompt,
            })
        
        # ══ Build JSON character_configs (for Stage 4) ══
        character_configs = []
        for c in self.state.characters:
            # Parse structured appearance from Bible §2
            appearance = self._parse_character_appearance(c.name, bible)
            is_group = any(kw in c.name.lower() for kw in _GROUP_KW)
            char_type = "group" if is_group else (
                "main" if any(self._strip_diacritics(c.name) == self._strip_diacritics(pn)
                              for pn in (char_profiles or {}).keys()) else "supporting"
            )
            character_configs.append({
                "character_name": c.name,
                "role": appearance.get("role", ""),
                "type": char_type,
                "age": appearance.get("age", ""),
                "appearance": {
                    "height": appearance.get("height", ""),
                    "skin": appearance.get("skin", ""),
                    "face": appearance.get("face", ""),
                    "hair": appearance.get("hair", ""),
                    "clothing_top": appearance.get("clothing_top", ""),
                    "clothing_bottom": appearance.get("clothing_bottom", ""),
                    "accessories": appearance.get("accessories", ""),
                },
                "visual_style": style_desc,
                "layout": "group lineup" if is_group else "4-view turnaround",
                "prompt_text": c.prompt or "",
            })
        
        stage.data = {
            "raw_prompts": raw_prompts,
            "raw_scenes": raw_scenes,
            "prompt_count": len(scenes),
            "scene_configs": scene_configs,
            "character_configs": character_configs,
            "character_prompts": char_prompts,
            "character_prompt_count": len(char_prompts),
            "extended_chars": getattr(self, '_extended_chars_detected', []),
            "background_prompts": bg_prompts,
            "background_names": [bg.name for bg in bg_entries],
            "background_count": len(bg_entries),
        }
        
        # ── Multi-Version Prompt Generation ──
        video_count = self.state.video_count
        
        if video_count > 1 and self.state.versions:
            # Store first version's scenes
            self.state.versions[0].scenes = list(scenes)
            
            if self.state.multi_idea:
                # Feature C: Each version has a DIFFERENT Bible → generate unique prompts
                for vi in range(1, min(video_count, len(self.state.versions))):
                    v = self.state.versions[vi]
                    alt_bible = v.bible
                    if not alt_bible:
                        continue
                    
                    log.info(f"[Pipeline] Multi-Idea: Generating prompts for {v.label} from its Bible")
                    
                    # Use same extraction pipeline on the version's Bible
                    alt_char_profiles = self._extract_char_profiles_from_bible(alt_bible)
                    alt_char_names = ", ".join(alt_char_profiles.keys()) if alt_char_profiles else char_names
                    
                    alt_bible_summary = ""
                    for section_name in ["PROJECT INFO", "SETTINGS", "STORY STRUCTURE"]:
                        section = self._extract_bible_section(alt_bible, section_name)
                        if section:
                            alt_bible_summary += f"{section_name}:\n{section}\n\n"
                    if not alt_bible_summary:
                        alt_bible_summary = alt_bible[:2000]
                    
                    alt_prompts_user = (
                        f"Topic: {topic}\n\n"
                        + (f"{type_instruction}\n" if type_instruction else "")
                        + f"{self._build_dimension_context(config)}\n"
                        + f"BIBLE SUMMARY:\n{alt_bible_summary}\n\n"
                        f"Character names: {alt_char_names}\n\n"
                        f"REQUIREMENTS:\n"
                        f"- Generate EXACTLY {scene_count} scene descriptions\n"
                        f"- Total: {scene_count} x {clip_duration}s = {scene_count * clip_duration}s\n"
                        f"- Each scene = 1 line, 1 blank line between scenes\n"
                        f"- Use [CharacterName] tag for each character\n"
                        f"- Do NOT write full character descriptions — just the NAME TAG + action\n"
                        f"- At least 3-5 scenes use multi-segment (>>)\n"
                        f"- Each scene MUST advance the story — NO filler/padding\n"
                    )
                    
                    alt_raw = await self._call_gemini_with_rotation(
                        prompt=alt_prompts_user, system=prompts_system,
                        max_tokens=16000, temperature=0.5,
                    )
                    alt_raw_injected = self._inject_character_profiles(alt_raw, alt_char_profiles or char_profiles)
                    v.scenes = self._parse_text_prompts(alt_raw_injected)
                    log.info(f"[Pipeline] Multi-Idea: {v.label} → {len(v.scenes)} scenes generated")
                
            else:
                # Feature A: Same Bible → generate VARIATIONS (different camera, wording, scene order)
                for vi in range(1, min(video_count, len(self.state.versions))):
                    v = self.state.versions[vi]
                    log.info(f"[Pipeline] Multi-Version: Generating variation {v.label}")
                    
                    variation_prompt = (
                        f"Topic: {topic}\n\n"
                        f"BIBLE SUMMARY:\n{bible_summary}\n\n"
                        f"Character names: {char_names}\n\n"
                        f"TASK: Generate a VARIATION of the scene sequence.\n"
                        f"⚠️ VARIATION RULES:\n"
                        f"- Keep the SAME story content and characters\n"
                        f"- CHANGE: camera angles, shot types, scene order, wording\n"
                        f"- Use different camera movements (dolly, pan, tilt, zoom vs original)\n"
                        f"- Reorder scenes where narratively possible\n"
                        f"- Rephrase action descriptions with different vocabulary\n"
                        f"- Generate EXACTLY {scene_count} scenes\n"
                        f"- Each scene = 1 line, 1 blank line between scenes\n"
                        f"- Use [CharacterName] tags\n"
                        f"- This is variation #{vi + 1} — must be DISTINCT from the original\n"
                    )
                    
                    alt_raw = await self._call_gemini_with_rotation(
                        prompt=variation_prompt, system=prompts_system,
                        max_tokens=16000, temperature=0.6 + (vi * 0.05),
                    )
                    alt_raw_injected = self._inject_character_profiles(alt_raw, char_profiles)
                    v.scenes = self._parse_text_prompts(alt_raw_injected)
                    v.bible = bible  # Same Bible for all versions in Feature A
                    log.info(f"[Pipeline] Multi-Version: {v.label} → {len(v.scenes)} scenes generated")
            
            stage.data["version_scenes"] = {
                v.label: len(v.scenes) for v in self.state.versions
            }
        
        # ── Episode Scene Distribution (Feature B) ──
        if self.state.is_multi_episode() and self.state.episodes:
            ep_count = len(self.state.episodes)
            scenes_per_ep = max(1, len(scenes) // ep_count)
            remainder = len(scenes) % ep_count
            
            offset = 0
            for ei, ep in enumerate(self.state.episodes):
                count = scenes_per_ep + (1 if ei < remainder else 0)
                ep.scenes = scenes[offset:offset + count]
                # Re-index episodes' scenes starting from 1
                for si, s in enumerate(ep.scenes):
                    s.index = si + 1
                offset += count
                log.info(f"[Pipeline] Episode {ep.label}: {len(ep.scenes)} scenes (idx {offset - count + 1}-{offset})")
            
            stage.data["episode_scenes"] = {
                ep.label: len(ep.scenes) for ep in self.state.episodes
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
    
    def _parse_character_appearance(self, char_name: str, bible: str) -> dict:
        """Parse structured appearance data from Bible §2 CHARACTER PROFILE LOCK.
        
        Returns dict with keys: role, age, height, skin, face, hair,
        clothing_top, clothing_bottom, accessories.
        """
        import re
        result = {}
        
        # Find the character section in Bible
        char_stripped = self._strip_diacritics(char_name)
        # Pattern: ### CharName (Role)\n\n* fields...
        pattern = rf'###\s*{re.escape(char_name)}.*?\n([\s\S]*?)(?=###|## \d|$)'
        match = re.search(pattern, bible, re.IGNORECASE)
        if not match:
            # Try diacritic-insensitive
            for section in re.findall(r'###\s*(.+?)\n([\s\S]*?)(?=###|## \d|$)', bible):
                if char_stripped in self._strip_diacritics(section[0]):
                    match_text = section[1]
                    break
            else:
                return result
        else:
            match_text = match.group(1)
        
        # Extract role from header: ### CharName (The Role)
        role_match = re.search(rf'###\s*{re.escape(char_name)}\s*\((.+?)\)', bible, re.IGNORECASE)
        if role_match:
            result['role'] = role_match.group(1).strip()
        
        # Parse key-value fields
        field_map = {
            'age': r'Age \+ Role[:\s]*(.+)',
            'height': r'Height[:\s]*(.+)',
            'skin': r'Skin \+ Modifier[:\s]*(.+)',
            'face': r'Face features?[:\s]*(.+)',
            'hair': r'Hair[:\s]*(.+)',
            'clothing_top': r'Clothing top[:\s]*(.+)',
            'clothing_bottom': r'Clothing bottom[:\s]*(.+)',
            'accessories': r'Accessories?[:\s]*(.+)',
        }
        
        for key, pat in field_map.items():
            m = re.search(pat, match_text, re.IGNORECASE)
            if m:
                result[key] = m.group(1).strip()
        
        return result
    
    @staticmethod
    def _extract_dialogues_from_script(text: str) -> list:
        """Extract existing dialogues from input script text (LOCAL, no API).
        
        Detects Vietnamese script dialogue patterns:
          - Character Name:\n"dialogue"
          - Character Name: "dialogue"  
          - Narrator/Sound effects
        
        Returns: list of {"speaker": str, "line": str, "scene_idx": int}
        """
        import re
        dialogues = []
        scene_idx = 0
        lines = text.split('\n')
        i = 0
        
        # Pattern: scene headers like "Cảnh 1", "Scene 2", "Khung 3"
        scene_pattern = re.compile(
            r'^(?:Cảnh|Scene|Màn|Phần)\s*\d+', re.IGNORECASE
        )
        # Pattern: speaker line like "Tên Nhân Vật:" or "Tên Nhân Vật:\n"
        speaker_pattern = re.compile(
            r'^([A-ZÀ-Ỹa-zà-ỹ][A-ZÀ-Ỹa-zà-ỹ\s]+?)(?:\s+mỉm cười)?:\s*$'
        )
        # Pattern: speaker + inline dialogue like 'Name: "dialogue"'
        inline_pattern = re.compile(
            r'^([A-ZÀ-Ỹa-zà-ỹ][A-ZÀ-Ỹa-zà-ỹ\s]+?):\s*["\u201c](.+?)["\u201d]\s*$'
        )
        # Pattern: quoted text on its own line
        quote_pattern = re.compile(
            r'^\s*["\u201c](.+?)["\u201d]\s*$'
        )
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detect scene boundary
            if scene_pattern.match(line):
                scene_idx += 1
                i += 1
                continue
            
            # Case 1: Inline dialogue — 'Character: "dialogue"'
            m_inline = inline_pattern.match(line)
            if m_inline:
                speaker = m_inline.group(1).strip()
                dialogue_text = m_inline.group(2).strip()
                if dialogue_text:
                    dialogues.append({
                        "speaker": speaker,
                        "line": dialogue_text,
                        "scene_idx": max(1, scene_idx),
                    })
                i += 1
                continue
            
            # Case 2: Speaker on one line, dialogue on next — 'Character:\n"dialogue"'
            m_speaker = speaker_pattern.match(line)
            if m_speaker:
                speaker = m_speaker.group(1).strip()
                # Look ahead for quoted line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    m_quote = quote_pattern.match(next_line)
                    if m_quote:
                        dialogue_text = m_quote.group(1).strip()
                        if dialogue_text:
                            dialogues.append({
                                "speaker": speaker,
                                "line": dialogue_text,
                                "scene_idx": max(1, scene_idx),
                            })
                        i += 2
                        continue
            
            i += 1
        
        if dialogues:
            log.info(f"[Pipeline] Extracted {len(dialogues)} dialogues from script "
                     f"({len(set(d['speaker'] for d in dialogues))} speakers)")
        return dialogues
    
    async def _analyze_dialogues(self, dialogues: list, topic: str, config: dict) -> str:
        """AI-powered dialogue analysis and improvement.
        
        Sends extracted dialogues to Gemini for:
        - Rating: KEEP (good), IMPROVE (needs work), ADD (missing)
        - Improved versions for weak dialogues
        - Suggested new dialogues for scenes without them
        
        Returns: structured text for Bible DIALOGUE GUIDE injection.
        """
        if not dialogues or not self.client:
            return ""
        
        # Format dialogues for AI
        dialogue_text = ""
        current_scene = 0
        for d in dialogues:
            if d["scene_idx"] != current_scene:
                current_scene = d["scene_idx"]
                dialogue_text += f"\n--- Cảnh {current_scene} ---\n"
            dialogue_text += f'  {d["speaker"]}: "{d["line"]}"\n'
        
        scene_count = self.state.scene_count or 10
        
        # Build audience/tone context
        tone = ", ".join(config.get("tone", [])) or "không xác định"
        audience = ", ".join(config.get("audience", [])) or "không xác định"
        
        system = (
            "Bạn là chuyên gia biên kịch lời thoại cho video. "
            "Phân tích lời thoại đã có trong kịch bản và cải thiện chúng."
        )
        
        prompt = f"""Phân tích lời thoại từ kịch bản sau:

Chủ đề: {topic[:500]}
Đối tượng: {audience}
Tone: {tone}
Tổng số cảnh mong muốn: {scene_count}

LỜI THOẠI HIỆN CÓ:
{dialogue_text}

YÊU CẦU:
1. Đánh giá TỪNG câu thoại:
   - ✅ GIỮ NGUYÊN: câu thoại tốt, tự nhiên, phù hợp nhân vật
   - 🔧 CẢI THIỆN: câu thoại cần sửa (kèm phiên bản mới)
   - ➕ BỔ SUNG: đề xuất thêm câu thoại cho cảnh còn thiếu

2. Nguyên tắc:
   - Giữ nguyên tối đa lời thoại gốc hay
   - Cải thiện phải giữ ý nghĩa + tính cách nhân vật
   - Bổ sung phải phù hợp bối cảnh và nhân vật
   - Phù hợp đối tượng {audience}, tone {tone}

3. Format output:
   Cho mỗi cảnh, liệt kê:
   ### Cảnh [N]
   [Speaker]: "[Lời thoại]" — [✅ GIỮ / 🔧 CẢI THIỆN từ "original" / ➕ BỔ SUNG]
   
   Cuối cùng thêm section:
   ### TỔNG KẾT
   - Tổng số câu thoại gốc: X
   - Giữ nguyên: Y
   - Cải thiện: Z  
   - Bổ sung: W
"""
        
        result = await self._call_gemini_with_rotation(
            prompt=prompt, system=system,
            max_tokens=8000, temperature=0.3,
        )
        
        log.info(f"[Pipeline] Dialogue analysis complete: {len(dialogues)} dialogues analyzed")
        return result
    
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
    
    def _parse_settings_to_backgrounds(
        self, settings_text: str, visual_style: str
    ) -> list:
        """Parse Bible §3 SETTINGS into BackgroundData with T2I prompts.
        
        Handles formats:
          * **Name:** Description
          **Name:** Description
          - **Name:** Description
        
        Returns List[BackgroundData].
        """
        if not settings_text:
            return []
        
        backgrounds = []
        # Match: optional bullet + **Name:** Description
        pattern = re.compile(
            r'(?:^|\n)\s*(?:[*\-•]\s*)?'    # optional bullet
            r'\*\*([^*]+)\*\*\s*[:：]\s*'      # **Name**:
            r'(.+?)(?=\n\s*(?:[*\-•]\s*)?\*\*|\Z)',  # Description until next entry or end
            re.DOTALL
        )
        
        for match in pattern.finditer(settings_text):
            name = match.group(1).strip()
            desc = match.group(2).strip()
            
            # Clean description (remove newlines within a single entry)
            desc = re.sub(r'\s+', ' ', desc).strip()
            
            # Build a normalized tag for matching in prompts
            # "Bờm's Village Hut" → "bờm's village hut"
            tag = name.lower().strip()
            
            # Generate T2I prompt for this background
            prompt = (
                f"Establishing shot, wide angle landscape, {desc}, "
                f"{visual_style}, "
                f"cinematic composition, detailed background art, "
                f"no characters, empty scene, atmospheric lighting, "
                f"concept art quality, 16:9 horizontal layout, "
                f"no text, no watermarks"
            )
            
            backgrounds.append(BackgroundData(
                name=name,
                description=desc,
                prompt=prompt,
                tag=tag,
            ))
            log.info(f"[Pipeline] Phase D: Background '{name}' → tag='{tag}'")
        
        return backgrounds
    
    def _inject_background_tags(
        self, raw_prompts: str, backgrounds: list
    ) -> str:
        """Inject [BG:LocationName] tags into scene prompts.
        
        For each line, check if any background name/keyword appears
        (diacritic-insensitive, fuzzy substring match). If found, insert
        [BG:LocationName] tag at the beginning of the setting mention.
        """
        if not backgrounds:
            return raw_prompts
        
        # Build match patterns: each background → list of possible keyword forms
        bg_patterns = []
        for bg in backgrounds:
            # Primary: full name
            keywords = [bg.name.lower()]
            # Also add short forms: "Bờm's Village Hut" → "bờm's hut", "village hut"
            words = bg.name.split()
            if len(words) >= 2:
                # Possessive shortcut: "Bờm's Village Hut" → "bờm's hut"
                if words[0].lower().endswith(("'s", "'s")):
                    keywords.append(f"{words[0].lower()} {words[-1].lower()}")
                # Last two words: "Village Hut" → "village hut"
                keywords.append(' '.join(words[-2:]).lower())
            bg_patterns.append((bg, keywords))
        
        lines = raw_prompts.split('\n')
        result_lines = []
        inject_count = 0
        
        for line in lines:
            if not line.strip():
                result_lines.append(line)
                continue
            
            modified = line
            line_lower = self._strip_diacritics(line.lower())
            
            for bg, keywords in bg_patterns:
                # Check if any keyword matches in this line
                matched = False
                for kw in keywords:
                    kw_stripped = self._strip_diacritics(kw)
                    if kw_stripped in line_lower:
                        matched = True
                        break
                
                if matched:
                    # Check if [BG:...] already present for this bg
                    bg_tag = f"[BG:{bg.name}]"
                    if bg_tag not in modified:
                        # Insert after the first setting mention (after "." or ", " near the match)
                        # Simple approach: prepend the BG tag before the setting text
                        # Find the keyword position and insert tag before it
                        for kw in keywords:
                            kw_stripped = self._strip_diacritics(kw)
                            idx = line_lower.find(kw_stripped)
                            if idx >= 0:
                                # Insert [BG:Name] right before the keyword in the original line
                                modified = modified[:idx] + bg_tag + " " + modified[idx:]
                                inject_count += 1
                                break
            
            result_lines.append(modified)
        
        if inject_count:
            log.info(f"[Pipeline] Phase E: Injected {inject_count} [BG:] tags across scene prompts")
        
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
        # Also include background prompts for Stage 4 dispatch
        bg_prompts = [bg.prompt for bg in (self.state.backgrounds or []) if bg.prompt]
        bg_names = [bg.name for bg in (self.state.backgrounds or [])]
        
        # Read character_configs from Stage 3 (pre-built)
        s3 = self.state.get_stage("scene_breakdown")
        character_configs = s3.data.get("character_configs", []) if s3.data else []
        
        stage.data = {
            "character_configs": character_configs,
            "character_prompts": char_prompts,
            "character_names": [c.name for c in characters],
            "prompt_count": len(char_prompts),
            "mode": "T2I",
            "background_prompts": bg_prompts,
            "background_names": bg_names,
            "background_count": len(bg_prompts),
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
        
        # Read Stage 3 scene_configs for metadata enrichment
        s3 = self.state.get_stage("scene_breakdown")
        s3_scene_configs = s3.data.get("scene_configs", []) if s3.data else []
        s3_lookup = {sc["scene_index"]: sc for sc in s3_scene_configs}
        
        for s in scenes:
            # Stage 3 prompts already contain full character profiles (Phase B)
            # Only add T2I style suffix — do NOT re-inject character descriptions
            base = s.prompt or s.description or f"Scene {s.index}"
            base = base.replace(">>", "—")
            
            # R5-5: Strip text overlay instructions (AI can't render text accurately)
            import re as _re_text
            has_overlay = bool(_re_text.search(r'(?i)text\s+overlay|stylized\s+text', base))
            overlay_content = None
            if has_overlay:
                overlay_match = _re_text.search(r'["\u201c](.+?)["\u201d]', base)
                overlay_content = overlay_match.group(1) if overlay_match else None
                # Strip text overlay from prompt
                base = _re_text.sub(
                    r'(?i)(?:stylized\s+)?text(?:\s+overlay)?[\s:.]*["\u201c].*?["\u201d]\.?\s*',
                    '', base
                )
                base = _re_text.sub(r'(?i)\btext\s+overlay\b', '', base)
                log.info(f"[Pipeline] R5-5: Stripped text overlay from Scene {s.index}")
            
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
            # Uses diacritic-insensitive matching + alias extraction:
            #   [Milo] matches "Mèo Em (Milo)" via parenthesized alias
            #   [Tam] matches "TẤM" via diacritic stripping
            import re as _re
            prompt_tags = {t.strip().lower() for t in _re.findall(r'\[([^\]]+)\]', base)}
            scene_char_images = []
            chars_in_scene = []
            for cr in char_refs:
                cr_name_stripped = self._strip_diacritics(cr["name"])
                # Build alias set: full name + parenthesized parts + base name
                cr_aliases = {cr_name_stripped}
                parens = _re.findall(r'\(([^)]+)\)', cr["name"])
                for p in parens:
                    cr_aliases.add(self._strip_diacritics(p.strip()))
                # Base name without parenthesized part: "Mèo Em (Milo)" → "Mèo Em"
                base_name = _re.sub(r'\s*\([^)]*\)\s*', '', cr["name"]).strip()
                if base_name:
                    cr_aliases.add(self._strip_diacritics(base_name))
                if any(self._strip_diacritics(tag) in cr_aliases for tag in prompt_tags):
                    scene_char_images.append(cr["image_path"])
                    chars_in_scene.append(cr["name"])
            
            # ★ Match [BG:Location] tags to background images
            scene_bg_images = []
            bg_tags = {t.strip().lower() for t in _re.findall(r'\[BG:([^\]]+)\]', base)}
            for bg in (self.state.backgrounds or []):
                if bg.image_path and bg.tag:
                    bg_tag_stripped = self._strip_diacritics(bg.tag)
                    if any(self._strip_diacritics(bt) == bg_tag_stripped for bt in bg_tags):
                        scene_bg_images.append(bg.image_path)
            # Combine: char images first, then BG images
            all_ref_images = scene_char_images + scene_bg_images
            
            mode = "I2I" if all_ref_images else "T2I"
            
            # Enrich from Stage 3 scene_config
            s3_sc = s3_lookup.get(s.index, {})
            
            scene_configs.append({
                "scene_index": s.index,
                "mode": mode,
                "type": s3_sc.get("type", "landscape"),
                "scene_type": s3_sc.get("scene_type", "action"),
                "shot_type": s3_sc.get("shot_type", "medium shot"),
                "setting": s3_sc.get("setting", ""),
                "characters_in_scene": chars_in_scene,
                "character_actions": s3_sc.get("character_actions", {}),
                "reference_images": all_ref_images,
                "background_image": scene_bg_images[0] if scene_bg_images else None,
                "style_suffix": style_suffix,
                "has_text_overlay": has_overlay,
                "text_overlay_content": overlay_content,
                "negative_prompt": s3_sc.get("negative_prompt", ""),
                "prompt_text": t2i_prompt,
                # Legacy compat fields
                "index": s.index,
                "prompt": t2i_prompt,
            })
        
        stage.scenes = scenes
        stage.prompts = [c["prompt_text"] for c in scene_configs]
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
        
        # Read Stage 3 scene_configs for metadata enrichment
        s3 = self.state.get_stage("scene_breakdown")
        s3_scene_configs = s3.data.get("scene_configs", []) if s3.data else []
        s3_lookup = {sc["scene_index"]: sc for sc in s3_scene_configs}
        
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
            
            # Enrich from Stage 3 scene_config
            s3_sc = s3_lookup.get(s.index, {})
            
            video_configs.append({
                "scene_index": s.index,
                "mode": mode,
                "type": s3_sc.get("type", "landscape"),
                "scene_type": s3_sc.get("scene_type", "action"),
                "scene_tag": scene_tag,
                "image_path": img_path,
                "duration_s": s.duration_s,
                "characters_in_scene": s3_sc.get("characters", []),
                "character_actions": s3_sc.get("character_actions", {}),
                "setting": s3_sc.get("setting", ""),
                "shot_type": s3_sc.get("shot_type", "medium shot"),
                "camera_movement": s3_sc.get("camera_movement", "static"),
                "audio_cue": s3_sc.get("audio_cue", ""),
                "tone": s3_sc.get("tone", ""),
                "has_text_overlay": s3_sc.get("has_text_overlay", False),
                "text_overlay_content": s3_sc.get("text_overlay_content", None),
                "output_folder": output_folder,
                "prompt_text": tagged_prompt,
                # Legacy compat fields
                "index": s.index,
                "prompt": tagged_prompt,
            })
        
        stage.scenes = scenes
        stage.prompts = [c["prompt_text"] for c in video_configs]
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
        
        # ★ Diagnostic logging
        log.info(f"[Pipeline] Stage 7: START — {len(scenes)} scenes, output_folder='{output_folder}'")
        for s in scenes:
            has_file = os.path.isfile(s.video_path) if s.video_path else False
            log.info(f"[Pipeline] Stage 7: scene[{s.index}] video_path='{s.video_path}' exists={has_file}")
        
        # Collect video paths
        clips = []
        missing = []
        for s in scenes:
            if s.video_path and os.path.isfile(s.video_path):
                clips.append({"index": s.index, "path": s.video_path, "duration_s": s.duration_s})
            else:
                missing.append(s.index)
        
        # ── Fallback: auto-resolve video_path from disk ──
        # Queue downloads videos to output folder but scene.video_path may not be set.
        # Scan for files matching {index:03d}_*_720p.mp4 or {index:03d}_*.mp4 pattern.
        if missing and output_folder:
            import glob, re as _re
            
            # ★ FIX: Use project_name from config (same as Stage 6 output folder)
            project_slug = config.get("project_name", "")
            if not project_slug:
                # Fallback: derive from topic (may not match Stage 6 folder)
                topic_raw_resolve = self.state.topic[:50] or "production"
                project_slug = _re.sub(r'[<>:"/\\|?*]', '', topic_raw_resolve).replace(" ", "_").strip("._")
                log.warning(f"[Pipeline] Stage 7: No project_name in config, using fallback: '{project_slug}'")
            
            video_dirs = [
                # Project subfolder paths (where Stage 6 actually saves)
                os.path.join(output_folder, project_slug, "video", "720p"),
                os.path.join(output_folder, project_slug, "video"),
                os.path.join(output_folder, project_slug),
                # Direct paths (legacy/fallback)
                os.path.join(output_folder, "video", "720p"),
                os.path.join(output_folder, "video"),
                output_folder,
            ]
            
            # Also scan numbered project folders (e.g. "001 - Project_Name")
            try:
                for entry in os.scandir(output_folder):
                    if entry.is_dir() and project_slug in entry.name:
                        video_dirs.insert(0, os.path.join(entry.path, "video", "720p"))
                        video_dirs.insert(1, os.path.join(entry.path, "video"))
                        video_dirs.insert(2, entry.path)
            except OSError:
                pass
            
            log.info(f"[Pipeline] Stage 7: {len(missing)} missing scenes, scanning {len(video_dirs)} dirs")
            
            resolved = []
            for scene_idx in list(missing):
                found_path = None
                # Get scene tag for tag-based matching
                scene_tag = None
                for s in scenes:
                    if s.index == scene_idx:
                        scene_tag = (s.title or "").strip()
                        break
                safe_tag = _re.sub(r'[<>:"/\\|?*]', '_', scene_tag) if scene_tag else None
                
                for vdir in video_dirs:
                    if not os.path.isdir(vdir):
                        continue
                    # Try multiple filename patterns
                    patterns = [
                        f"{scene_idx:03d}_*_720p.mp4",
                        f"{scene_idx:03d}_*.mp4",
                    ]
                    # Also try scene-tag based pattern (e.g. "Canh_1_*.mp4")
                    if safe_tag:
                        patterns.append(f"{safe_tag}*.mp4")
                        patterns.append(f"*{safe_tag}*.mp4")
                    
                    for pattern in patterns:
                        matches = glob.glob(os.path.join(vdir, pattern))
                        if matches:
                            found_path = matches[0]
                            break
                    if found_path:
                        break
                
                if found_path:
                    # Update scene data
                    for s in scenes:
                        if s.index == scene_idx:
                            s.video_path = found_path
                            clips.append({"index": s.index, "path": found_path, "duration_s": s.duration_s})
                            break
                    resolved.append(scene_idx)
                    missing.remove(scene_idx)
                    log.info(f"[Pipeline] Stage 7: Auto-resolved scene {scene_idx} → {found_path}")
                else:
                    log.warning(f"[Pipeline] Stage 7: Could NOT resolve scene {scene_idx} (tag='{scene_tag}')")
            
            if resolved:
                log.info(f"[Pipeline] Stage 7: Auto-resolved {len(resolved)}/{len(resolved)+len(missing)} missing video paths")
                # Sort clips by index to maintain correct order
                clips.sort(key=lambda c: c["index"])
        
        # Generate output path
        import re
        # ★ Use config project_name (consistent with Stage 6 folder)
        project_name = config.get("project_name", "")
        if not project_name:
            topic_raw = self.state.topic[:50] or "production"
            project_name = re.sub(r'[<>:"/\\|?*]', '', topic_raw).replace(" ", "_").strip("._")
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # ★ FIX: Output final video in project subfolder (same as Stage 6 videos)
        if output_folder:
            project_dir = os.path.join(output_folder, project_name)
            os.makedirs(project_dir, exist_ok=True)
            final_path = os.path.join(project_dir, f"{project_name}_{ts}_final.mp4")
        else:
            final_path = f"{project_name}_{ts}_final.mp4"
        
        self.state.final_video_path = final_path
        log.info(
            f"[Pipeline] Stage 7: {len(clips)} clips ready, {len(missing)} missing. "
            f"Output → {final_path}"
        )
        
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
                        encoding='utf-8',
                        errors='replace',
                        timeout=300,  # 5 min timeout
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
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
        from services.gemini_client import RateLimitError, GeminiAPIError, InvalidKeyError, GeminiClient
        
        # Auto-create client if None (pipeline may be initialized without one)
        if not self.client:
            self.client = GeminiClient()
            log.info("[Pipeline] Auto-created GeminiClient (was None)")
        
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
                # Also reset key quota blocks so keys are re-available
                try:
                    from services.key_quota_manager import get_quota_manager
                    qm = get_quota_manager()
                    qm.reset_rpm_blocks()
                    log.info(f"[Pipeline] Round {round_num + 1}: reset model exhaustion + key RPM blocks")
                except Exception:
                    pass
                # Reset api_key to original so rotation starts fresh
                api_key = self.api_key or api_key
            
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
                
                except InvalidKeyError as e:
                    # ★ 403 "denied access" — could be model-specific OR key/project-level
                    # Strategy: mark BOTH model exhausted AND key denied, try next of each
                    last_error = e
                    try:
                        rotation.mark_exhausted("pipeline", model)
                    except Exception:
                        pass
                    # Mark key denied + rotate to next available key
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        qm.mark_denied(api_key)
                        if custom_keys:
                            next_key = qm.get_available_key(custom_keys)
                            if next_key and next_key != api_key:
                                log.info(f"[Pipeline] 403 → switched key ...{next_key[-8:]}")
                                api_key = next_key
                    except Exception:
                        pass
                    log.warning(
                        f"[Pipeline] {model} access denied (403): {e} — "
                        f"model exhausted + key rotated, trying next..."
                    )
                    continue
                    
                except GeminiAPIError as e:
                    last_error = e
                    if e.status == 400:
                        log.warning(f"[Pipeline] {model} blocked (400), trying next model...")
                        continue
                    if e.status >= 500:
                        # 503 = server overload, 500 = internal error — retryable
                        log.warning(f"[Pipeline] {model} server error ({e.status}), trying next model...")
                        continue
                    # Other client errors (e.g. 404): try next model
                    log.warning(f"[Pipeline] {model} error ({e.status}), trying next model...")
                    continue
                    
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
