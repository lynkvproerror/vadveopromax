"""
VEO Pro Max - Application Settings

Reference: TAB_07_SETTINGS.md
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List

# Bump this when adding/removing/renaming fields
SETTINGS_VERSION = 11


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
    
    # === GEMINI AI ===
    prompt_enhance_enabled: bool = True       # Master toggle for Gemini features
    prompt_auto_enhance: bool = False          # Auto-enhance prompts before VEO submit
    prompt_auto_fix: bool = True              # Auto-fix policy-blocked prompts
    
    # === PROJECT BUILDER ===
    workflow_template_sources: List[str] = field(default_factory=list)
    workflow_rules_sources: List[str] = field(default_factory=list)
    project_default_scenes: int = 10
    project_output_base: str = ""
    
    # === PROJECT BUILDER AI ===
    pb_ai_source: str = "account"         # "account" = use profile Gemini keys, "custom" = external API
    pb_ai_provider: str = "Google"        # Provider: Google, OpenAI, Anthropic, DeepSeek, xAI, Mistral, OpenRouter
    pb_ai_model: str = "gemini-3.1-flash-lite-preview" # Model for AI (500 RPD free tier)
    pb_ai_base_url: str = ""              # Custom base URL (auto-filled per provider, user-editable)
    pb_ai_custom_keys: List[str] = field(default_factory=list)  # Custom API keys (round-robin)
    
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
    smart_hide_enabled: bool = False            # ON = hide on success, show on 403 error; OFF = always visible
    hide_all_browsers: bool = True               # ON = hide ALL browsers after startup; overrides smart_hide
    
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
    workload_priority: str = "upscale_priority" # 720p_priority | upscale_priority
    auto_retry_download: bool = True         # Auto re-generate when 720p download fails
    auto_retry_download_max: int = 5         # Max re-generation attempts before marking failed
    prewarm_enabled: bool = True              # Pre-warm reCAPTCHA after idle period
    prewarm_idle_threshold: int = 10          # minutes — trigger soft recovery if idle > this
    smart_recovery_enabled: bool = True       # Smart Recovery: Credit Window + Diagnose-Remedy
    credit_passive_interval: int = 5          # minutes — passive credit recovery interval
    credit_probe_after: int = 3               # credits threshold for probe request
    
    # === ENHANCER IMAGE (AI Upscale — Real-ESRGAN + GFPGAN) ===
    enhance_context_menu: bool = False        # Toggle 1: Right-click → ✨ Enhance Image
    enhance_library: bool = False             # Toggle 2: Library toolbar enhance button
    enhance_auto_continuation: bool = False  # Toggle 3: Auto-enhance continuation frames (BETA)
    
    # === UI ===
    ui_language: str = "Tiếng Việt"           # "English" | "Tiếng Việt"
    developer_mode: bool = False
    show_json_preview: bool = False
    hide_emails: bool = False            # Email masking in profiles table
    
    # === NOTIFICATIONS ===
    notify_toast_enabled: bool = True        # In-app toast on group complete
    notify_sound_enabled: bool = True        # Sound on group complete
    notify_sound_file: str = "default"       # "default" | "success" | "chime" | custom path
    
    # === POST-QUEUE ACTION ===
    post_queue_action_enabled: bool = False  # Master toggle
    post_queue_action: str = "nothing"       # "nothing" | "shutdown" | "sleep"
    auto_sweep_max_rounds: int = 5           # Max retry rounds before giving up
    
    # === AUTO-UPDATE ===
    auto_update_enabled: bool = True         # Check for updates on startup + every 30min
    
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
                'workload_priority': '720p_priority',
                'ui_language': 'Tiếng Việt',
            },
            # 2 → 3: Add auto-retry download settings
            2: lambda d: {**d,
                'auto_retry_download': True,
                'auto_retry_download_max': 3,
            },
            # 3 → 4: Add post-queue action (shutdown/sleep)
            3: lambda d: {**d,
                'post_queue_action_enabled': False,
                'post_queue_action': 'nothing',
            },
            # 4 → 5: Simplify browser visibility — 5 toggles → 1 smart_hide
            4: lambda d: {
                **{k: v for k, v in d.items() if not k.startswith('auto_hide')},
                'smart_hide_enabled': d.get('auto_hide_enabled', True),
            },
            # 5 → 6: Add pre-warm idle recovery settings
            5: lambda d: {**d,
                'prewarm_enabled': True,
                'prewarm_idle_threshold': 10,
            },
            # 6 → 7: Add Smart Recovery settings
            6: lambda d: {**d,
                'smart_recovery_enabled': True,
                'credit_passive_interval': 5,
                'credit_probe_after': 3,
            },
            # 7 → 8: Add hide_all_browsers
            7: lambda d: {**d,
                'hide_all_browsers': False,
            },
            # 8 → 9: Add auto_update_enabled
            8: lambda d: {**d,
                'auto_update_enabled': True,
            },
            # 9 → 10: Add Gemini AI + Project Builder fields
            9: lambda d: {**d,
                'prompt_enhance_enabled': True,
                'prompt_auto_enhance': False,
                'prompt_auto_fix': True,
                'workflow_template_sources': [],
                'workflow_rules_sources': [],
                'project_default_scenes': 10,
                'project_output_base': '',
            },
            # 10 → 11: Add auto-sweep max rounds
            10: lambda d: {**d,
                'auto_sweep_max_rounds': 5,
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
