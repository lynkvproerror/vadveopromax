"""
VEO Pro Max - Application Settings

Reference: TAB_07_SETTINGS.md
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Bump this when adding/removing/renaming fields
SETTINGS_VERSION = 2


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
    default_image_model: str = "🔥 Nano Banana Pro"  # Image AI model display name
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
    
    # === BROWSER VISIBILITY ===
    auto_hide_enabled: bool = True              # Master toggle for all auto-hide
    auto_hide_on_launch: bool = True            # A: Hide Chrome on debug browser open
    auto_hide_on_engine_start: bool = True      # B: Hide during "Start Engine" auto-launch
    auto_hide_on_data_extract: bool = True      # C: Hide during x-client-data extraction
    auto_hide_on_worker_start: bool = True      # D: Engine browsers use headless mode
    
    # === CONTINUATION ===
    continuation_enabled: bool = True
    extract_point_ms: int = 750
    
    # === PIPELINE OPTIMIZATION ===
    adaptive_burst_enabled: bool = True
    burst_min_delay: float = 2.0             # seconds
    burst_max_delay: float = 15.0            # seconds
    recaptcha_pool_enabled: bool = True
    recaptcha_pool_size: int = 2
    watchdog_timeout_min: int = 10           # minutes
    journal_save_interval_sec: int = 30      # seconds
    workload_priority: str = "prompts_first" # balanced | prompts_first | upscale_first
    
    # === ENHANCER IMAGE (AI Upscale — Real-ESRGAN + GFPGAN) ===
    enhance_context_menu: bool = True        # Toggle 1: Right-click → ✨ Enhance Image
    enhance_library: bool = True             # Toggle 2: Library toolbar enhance button
    enhance_auto_continuation: bool = False  # Toggle 3: Auto-enhance continuation frames (BETA)
    
    # === UI ===
    ui_language: str = "English"             # "English" | "Tiếng Việt"
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
        """Load settings from JSON file, applying migrations if needed."""
        if path is None:
            path = cls._default_path()
        
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Run migrations if version is behind
                data = cls._migrate(data)
                
                # Filter to known fields only (ignore obsolete keys)
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                instance = cls(**known)
                
                # Auto-save if migration was applied
                if data.get("_version", 0) != SETTINGS_VERSION:
                    instance.save(path)
                
                return instance
            except Exception:
                pass
        
        return cls()
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save settings to JSON file with version stamp."""
        if path is None:
            path = self._default_path()
        
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["_version"] = SETTINGS_VERSION
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def _migrate(cls, data: dict) -> dict:
        """Apply sequential migrations from file version to current version.
        
        Each migration function transforms data from version N to N+1.
        Add new migrations to _MIGRATIONS when bumping SETTINGS_VERSION.
        """
        file_version = data.get("_version", 0)
        
        # Migration functions: version N → N+1
        _MIGRATIONS = {
            # 0 → 1: Initial versioning, no data changes needed
            0: lambda d: d,
            # 1 → 2: Add pipeline optimization + language fields
            1: lambda d: {**d,
                'adaptive_burst_enabled': True,
                'burst_min_delay': 2.0,
                'burst_max_delay': 15.0,
                'recaptcha_pool_enabled': True,
                'recaptcha_pool_size': 2,
                'watchdog_timeout_min': 10,
                'journal_save_interval_sec': 30,
                'workload_priority': 'prompts_first',
                'ui_language': 'English',
            },
        }
        
        while file_version < SETTINGS_VERSION:
            migrator = _MIGRATIONS.get(file_version)
            if migrator:
                data = migrator(data)
                file_version += 1
            else:
                # Unknown version gap — skip remaining migrations
                break
        
        data["_version"] = SETTINGS_VERSION
        return data
    
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
