"""
VEO Pro Max - Application Settings

Reference: TAB_07_SETTINGS.md
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class AppSettings:
    """Application settings with persistence."""
    
    # === OUTPUT ===
    output_folder: str = ""
    include_timestamp: bool = True
    include_quality: bool = True
    include_model: bool = False
    row_digits: int = 3
    separator: str = "_"
    
    # === GENERATION DEFAULTS ===
    default_aspect_ratio: str = "LANDSCAPE"
    default_model: str = "Veo 3.1 - Fast"       # Display name (matches sidebar dropdown)
    default_output_count: int = 4                # Match sidebar default
    default_download_quality: str = "1080p"      # Video download quality
    default_image_quality: str = "1k"            # Image download quality
    auto_enhance_prompt: bool = False
    
    # === QUEUE ===
    auto_start_queue: bool = False
    pause_on_error: bool = True
    
    # === SESSION PERSISTENCE ===
    restore_queue_on_startup: bool = False   # Load queue from previous session (OFF to prevent stale tasks)
    restore_tabs_on_startup: bool = True     # Restore tab content (prompts, settings) on startup
    
    # Granular restore sub-options (only effective when restore_tabs_on_startup=True)
    restore_project_name: bool = True
    restore_output_folder: bool = True
    restore_aspect_ratio: bool = True
    restore_outputs_per_prompt: bool = True
    restore_ai_model: bool = True
    restore_download_quality: bool = True
    restore_prompt_input: bool = True        # Raw text in prompt input area
    restore_parsed_prompts: bool = True      # Parsed prompt table rows
    restore_prompt_images: bool = True       # Image paths in prompts (all tabs)
    restore_frame_mode: bool = True          # I2V frame mode dropdown
    
    # === WORKER DEFAULTS (applied to new accounts) ===
    # Per-account max_slots is stored in AccountSession, not here
    retry_count: int = 3        # Default retry count for new accounts
    request_timeout: int = 120  # Default timeout (seconds) for new accounts
    
    # === ANTI-DETECT SPAM ===
    anti_detect_enabled: bool = True
    anti_detect_delay_min: float = 3.0   # seconds (microsecond precision at runtime)
    anti_detect_delay_max: float = 8.0   # seconds
    
    # === BROWSER ===
    headless_mode: bool = False
    use_persistent_profile: bool = True
    
    # === CONTINUATION ===
    continuation_enabled: bool = True
    extract_point_ms: int = 750
    
    # === ENHANCER IMAGE (AI Upscale — Real-ESRGAN + GFPGAN) ===
    enhance_context_menu: bool = True        # Toggle 1: Right-click → ✨ Enhance Image
    enhance_library: bool = True             # Toggle 2: Library toolbar enhance button
    enhance_auto_continuation: bool = False  # Toggle 3: Auto-enhance continuation frames (BETA)
    
    # === UI ===
    developer_mode: bool = False
    show_json_preview: bool = False
    
    # === NOTIFICATIONS ===
    notify_toast_enabled: bool = True        # In-app toast on group complete
    notify_sound_enabled: bool = True        # Sound on group complete
    notify_sound_file: str = "default"       # "default" | "success" | "chime" | custom path
    
    # === PATHS ===
    profiles_folder: str = ""
    cache_folder: str = ""
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppSettings":
        """Load settings from JSON file."""
        if path is None:
            path = cls._default_path()
        
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass
        
        return cls()
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save settings to JSON file."""
        if path is None:
            path = self._default_path()
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
    
    @staticmethod
    def _default_path() -> Path:
        """Get default settings file path."""
        return Path.home() / ".veoauto" / "settings.json"


# Global settings instance
_settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    """Get global settings instance."""
    global _settings
    if _settings is None:
        _settings = AppSettings.load()
    return _settings


def save_settings() -> None:
    """Save global settings instance."""
    global _settings
    if _settings is not None:
        _settings.save()
