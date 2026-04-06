"""
VEO Pro Max - Voice Library Service

Reference: R2V_Voice_Pipeline_Analysis.md §2, §3
Static catalog of 30 R2V voices + WAV preview cache.
"""

import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceInfo:
    """Represents a single R2V voice.
    
    Fields:
        id: API mediaId (lowercase), e.g. "aoede"
        display_name: PascalCase name for display + WAV filename, e.g. "Aoede"
        gender: "female" | "male" | "ungendered" | "unknown"
        tone: Descriptive tone, e.g. "soft", "firm" (empty if unknown)
        pitch: Pitch level, e.g. "mid", "mid-high" (empty if unknown)
    """
    id: str
    display_name: str
    gender: str
    tone: str
    pitch: str

    @property
    def preview_url(self) -> str:
        """Public gstatic.com WAV URL (no auth required)."""
        return f"https://www.gstatic.com/aistudio/voices/samples/{self.display_name}.wav"

    @property
    def gender_icon(self) -> str:
        return {"female": "♀", "male": "♂", "ungendered": "⚧"}.get(self.gender, "?")

    @property
    def gender_color(self) -> str:
        """Theme-appropriate color hex for gender."""
        from config.theme import Theme
        return {
            "female": Theme.RED,        # #F38BA8 — Catppuccin pink/flamingo
            "male": Theme.BLUE,
            "ungendered": Theme.PURPLE,  # #CBA6F7 — Catppuccin Mauve
        }.get(self.gender, Theme.SUBTEXT0)

    @property
    def subtitle(self) -> str:
        """Compact descriptor, e.g. '♀ soft · mid' or '♂'."""
        parts = [self.gender_icon]
        if self.tone:
            parts.append(self.tone)
        if self.pitch:
            parts.append(self.pitch)
        return " · ".join(parts)


# ─── FULL VOICE CATALOG (30 voices, alphabetically sorted) ───────────
# Source: Google VEO R2V UI (April 2026) — verified against live panel
_ALL_VOICES: List[VoiceInfo] = [
    # ─── FEMALE (13) ──────────────────────────────────
    VoiceInfo("achernar",      "Achernar",      "female", "soft",       "high"),
    VoiceInfo("aoede",         "Aoede",         "female", "breezy",     "mid"),
    VoiceInfo("autonoe",       "Autonoe",       "female", "bright",     "mid"),
    VoiceInfo("callirrhoe",    "Callirrhoe",    "female", "easy-going", "mid"),
    VoiceInfo("despina",       "Despina",       "female", "smooth",     "mid"),
    VoiceInfo("erinome",       "Erinome",       "female", "clear",      "mid"),
    VoiceInfo("gacrux",        "Gacrux",        "female", "mature",     "mid"),
    VoiceInfo("kore",          "Kore",          "female", "firm",       "mid"),
    VoiceInfo("laomedeia",     "Laomedeia",     "female", "upbeat",     "mid-high"),
    VoiceInfo("leda",          "Leda",          "female", "youthful",   "mid-high"),
    VoiceInfo("sulafat",       "Sulafat",       "female", "warm",       "mid"),
    VoiceInfo("vindemiatrix",  "Vindemiatrix",  "female", "gentle",     "mid"),
    VoiceInfo("zephyr",        "Zephyr",        "female", "bright",     "mid-high"),
    # ─── MALE (16) ────────────────────────────────────
    VoiceInfo("achird",        "Achird",        "male",   "friendly",       "mid"),
    VoiceInfo("algenib",       "Algenib",       "male",   "gravelly",       "low"),
    VoiceInfo("algieba",       "Algieba",       "male",   "easy-going",     "mid-low"),
    VoiceInfo("alnilam",       "Alnilam",       "male",   "firm",           "mid-low"),
    VoiceInfo("charon",        "Charon",        "male",   "informative",    "lower"),
    VoiceInfo("enceladus",     "Enceladus",     "male",   "breathy",        "lower"),
    VoiceInfo("fenrir",        "Fenrir",        "male",   "excitable",      "younger"),
    VoiceInfo("iapetus",       "Iapetus",       "male",   "clear",          "mid-low"),
    VoiceInfo("orus",          "Orus",          "male",   "firm",           "mid-low"),
    VoiceInfo("puck",          "Puck",          "male",   "upbeat",         "mid"),
    VoiceInfo("rasalgethi",    "Rasalgethi",    "male",   "informative",    "mid"),
    VoiceInfo("sadachbia",     "Sadachbia",     "male",   "lively",         "low"),
    VoiceInfo("sadaltager",    "Sadaltager",    "male",   "knowledgeable",  "mid"),
    VoiceInfo("schedar",       "Schedar",       "male",   "even",           "mid-low"),
    VoiceInfo("umbriel",       "Umbriel",       "male",   "smooth",         "lower"),
    VoiceInfo("zubenelgenubi", "Zubenelgenubi", "male",   "casual",         "mid-low"),
    # ─── OTHER (1) ────────────────────────────────────
    VoiceInfo("pulcherrima",   "Pulcherrima",   "ungendered", "forward", "mid-high"),
]

# Build lookup dict
_VOICE_MAP = {v.id: v for v in _ALL_VOICES}


class VoiceLibrary:
    """Static catalog of 30 R2V voices with WAV preview caching.
    
    Unlike ImageLibrary, this catalog is NOT user-editable.
    Voices are hardcoded from Google AI Studio's R2V pipeline.
    """

    # ─── Filter category labels ──────────────────────
    GENDER_FILTERS = ["All", "Female", "Male", "Other"]
    
    # Only tones that actually appear in the catalog
    TONE_FILTERS = [
        "All", "breezy", "breathy", "bright", "casual", "clear",
        "easy-going", "even", "excitable", "firm", "forward",
        "friendly", "gentle", "gravelly", "informative",
        "knowledgeable", "lively", "mature", "smooth", "soft",
        "upbeat", "warm", "youthful",
    ]
    
    PITCH_FILTERS = ["All", "high", "mid-high", "mid", "mid-low", "low", "lower", "younger"]

    def __init__(self):
        self._cache_dir = Path.home() / "Documents" / "VEO Pro Max" / "Voices"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_all_voices() -> List[VoiceInfo]:
        """Get all 30 voices (alphabetically sorted)."""
        return list(_ALL_VOICES)

    def get_voices(
        self,
        gender: str = "All",
        tone: str = "All",
        pitch: str = "All",
    ) -> List[VoiceInfo]:
        """Filter voices by gender, tone, pitch (AND logic).
        
        Args:
            gender: "All", "Female", "Male", "Other"
            tone: "All" or specific tone like "soft", "firm"
            pitch: "All" or specific pitch like "mid", "mid-high"
        
        Returns:
            Filtered list of VoiceInfo
        """
        result = list(_ALL_VOICES)
        
        if gender != "All":
            if gender == "Other":
                result = [v for v in result if v.gender in ("unknown", "ungendered")]
            else:
                result = [v for v in result if v.gender == gender.lower()]
        
        if tone != "All":
            result = [v for v in result if v.tone == tone]
        
        if pitch != "All":
            result = [v for v in result if v.pitch == pitch]
        
        return result

    def search(self, query: str) -> List[VoiceInfo]:
        """Search voices by name or attributes.
        
        Args:
            query: Search string (case-insensitive)
        
        Returns:
            Matching voices
        """
        q = query.lower().strip()
        if not q:
            return list(_ALL_VOICES)
        return [
            v for v in _ALL_VOICES
            if q in v.id
            or q in v.display_name.lower()
            or q in v.gender
            or q in v.tone
            or q in v.pitch
        ]

    @staticmethod
    def get_voice(voice_id: str) -> Optional[VoiceInfo]:
        """Lookup a single voice by ID.
        
        Args:
            voice_id: Lowercase voice name, e.g. "aoede"
        
        Returns:
            VoiceInfo or None
        """
        return _VOICE_MAP.get(voice_id)

    def get_cached_wav(self, voice_id: str) -> Optional[Path]:
        """Get local WAV path if already cached.
        
        Returns:
            Path to local WAV file, or None if not cached
        """
        voice = self.get_voice(voice_id)
        if not voice:
            return None
        path = self._cache_dir / f"{voice.display_name}.wav"
        return path if path.exists() else None

    def download_wav_sync(self, voice_id: str) -> Optional[Path]:
        """Download WAV from gstatic.com (synchronous, for QThread).
        
        Args:
            voice_id: Voice ID to download
        
        Returns:
            Path to downloaded WAV, or None on failure
        """
        voice = self.get_voice(voice_id)
        if not voice:
            return None
        
        dest = self._cache_dir / f"{voice.display_name}.wav"
        if dest.exists():
            return dest
        
        try:
            import urllib.request
            req = urllib.request.Request(
                voice.preview_url,
                headers={
                    "Referer": "https://labs.google/",
                    "sec-fetch-dest": "audio",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            
            dest.write_bytes(data)
            log.info(f"[VoiceLibrary] ✅ Downloaded {voice.display_name}.wav ({len(data)} bytes)")
            return dest
        except Exception as e:
            log.warning(f"[VoiceLibrary] ❌ Download failed for {voice_id}: {e}")
            return None

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def voice_count(self) -> int:
        return len(_ALL_VOICES)


# ─── Singleton ───────────────────────────────────────────────────────
_instance: Optional[VoiceLibrary] = None


def get_voice_library() -> VoiceLibrary:
    """Get the singleton VoiceLibrary instance."""
    global _instance
    if _instance is None:
        _instance = VoiceLibrary()
    return _instance
