"""
VEO Pro Max — Debug Flags (macOS)
===================================
Centralized debug configuration via environment variables.

USAGE (Terminal):
    # Enable all debug areas:
    VEO_DEBUG=1 python main.py

    # Enable specific areas only:
    VEO_DEBUG_LICENSE=1 VEO_DEBUG_CHROME=1 python main.py

    # Or set in your shell profile (~/.zshrc) for persistent debug:
    export VEO_DEBUG_LICENSE=1

AREAS:
    VEO_DEBUG=1             Master switch — enables ALL areas below
    VEO_DEBUG_LICENSE=1     License validation, machine ID, hardware fingerprint
    VEO_DEBUG_CHROME=1      Chrome launch, CDP, tab management, extensions
    VEO_DEBUG_API=1         Firebase REST, API keys, request/response payloads
    VEO_DEBUG_SECURITY=1    Anti-tamper, native bridge, hardware binder
    VEO_DEBUG_UPDATE=1      Auto-updater: check, download, apply
    VEO_DEBUG_VIDEO=1       Video player media pipeline (already used in video_player.py)
    VEO_DEBUG_UI=1          UI rendering, theme, splash, dialogs
    VEO_DEBUG_ENGINE=1      Production engine, task queue, dispatcher
    VEO_DEBUG_STARTUP=1     Boot trace, import order, dependency check

LOG LEVELS per flag:
    flag=0 (default)   → logger uses INFO level for that module
    flag=1             → logger drops to DEBUG level for that module
"""

import os
import logging

# ── Flag definitions ──────────────────────────────────────────────────────────

# Master switch: enables every area when set to 1
_MASTER = os.environ.get("VEO_DEBUG", "0") == "1"


def _flag(env_name: str) -> bool:
    """Return True if this debug flag is set, or master switch is on."""
    return _MASTER or os.environ.get(env_name, "0") == "1"


# Individual area flags (module-level booleans — import and use directly)
DEBUG_LICENSE  = _flag("VEO_DEBUG_LICENSE")   # license_client, firebase_rest_client, native_bridge
DEBUG_CHROME   = _flag("VEO_DEBUG_CHROME")    # chrome_manager, extension_manager
DEBUG_API      = _flag("VEO_DEBUG_API")       # firebase_rest_client request/response
DEBUG_SECURITY = _flag("VEO_DEBUG_SECURITY")  # anti_tamper, native_bridge, security.py
DEBUG_UPDATE   = _flag("VEO_DEBUG_UPDATE")    # auto_updater
DEBUG_VIDEO    = _flag("VEO_DEBUG_VIDEO")     # video_player (mirrors VEO_DEBUG_VIDEO)
DEBUG_UI       = _flag("VEO_DEBUG_UI")        # ui.app, splash_screen, theme
DEBUG_ENGINE   = _flag("VEO_DEBUG_ENGINE")    # engine, dispatcher, production_pipeline
DEBUG_STARTUP  = _flag("VEO_DEBUG_STARTUP")   # main.py boot sequence


# ── Helper: apply debug level to loggers ─────────────────────────────────────

_FLAG_TO_LOGGERS: dict = {
    "DEBUG_LICENSE":  ["veo.license", "security.license_client",
                       "security.firebase_rest_client", "security.native_bridge"],
    "DEBUG_CHROME":   ["core.chrome_manager", "core.extension_manager",
                       "core.profiles_controller"],
    "DEBUG_API":      ["security.firebase_rest_client", "core.api_client"],
    "DEBUG_SECURITY": ["security.anti_tamper", "security.native_bridge",
                       "core.security"],
    "DEBUG_UPDATE":   ["core.auto_updater"],
    "DEBUG_VIDEO":    ["video_player"],
    "DEBUG_UI":       ["ui.app", "ui.splash_screen", "config.theme"],
    "DEBUG_ENGINE":   ["core.engine", "core.dispatcher",
                       "core.production_pipeline", "core.queue_controller"],
    "DEBUG_STARTUP":  ["__main__"],
}


def apply_debug_levels():
    """
    Lower log level to DEBUG for each enabled area's loggers.
    Call this ONCE early in main.py, after logging is configured.

    Without this, log.debug() calls in those modules are swallowed
    even though the root logger is set to DEBUG.
    """
    flag_values = {
        "DEBUG_LICENSE":  DEBUG_LICENSE,
        "DEBUG_CHROME":   DEBUG_CHROME,
        "DEBUG_API":      DEBUG_API,
        "DEBUG_SECURITY": DEBUG_SECURITY,
        "DEBUG_UPDATE":   DEBUG_UPDATE,
        "DEBUG_VIDEO":    DEBUG_VIDEO,
        "DEBUG_UI":       DEBUG_UI,
        "DEBUG_ENGINE":   DEBUG_ENGINE,
        "DEBUG_STARTUP":  DEBUG_STARTUP,
    }

    active_areas = []
    for flag_name, enabled in flag_values.items():
        if enabled:
            for logger_name in _FLAG_TO_LOGGERS.get(flag_name, []):
                logging.getLogger(logger_name).setLevel(logging.DEBUG)
            active_areas.append(flag_name)

    log = logging.getLogger("veo.debug_flags")
    if active_areas:
        log.info(f"[DebugFlags] 🐛 Active: {', '.join(active_areas)}")
    elif _MASTER:
        log.info("[DebugFlags] 🐛 Master switch ON — all areas at DEBUG level")
        # Lower ALL known loggers
        all_loggers = set()
        for names in _FLAG_TO_LOGGERS.values():
            all_loggers.update(names)
        for name in all_loggers:
            logging.getLogger(name).setLevel(logging.DEBUG)
    else:
        log.debug("[DebugFlags] No debug flags set — running in production mode")


# ── Quick-check summary (printed at startup when any flag is set) ─────────────

def print_active_flags():
    """Print a human-readable summary of active debug flags to stdout."""
    flags = {
        "VEO_DEBUG (master)": _MASTER,
        "VEO_DEBUG_LICENSE":  DEBUG_LICENSE and not _MASTER,
        "VEO_DEBUG_CHROME":   DEBUG_CHROME  and not _MASTER,
        "VEO_DEBUG_API":      DEBUG_API     and not _MASTER,
        "VEO_DEBUG_SECURITY": DEBUG_SECURITY and not _MASTER,
        "VEO_DEBUG_UPDATE":   DEBUG_UPDATE  and not _MASTER,
        "VEO_DEBUG_VIDEO":    DEBUG_VIDEO   and not _MASTER,
        "VEO_DEBUG_UI":       DEBUG_UI      and not _MASTER,
        "VEO_DEBUG_ENGINE":   DEBUG_ENGINE  and not _MASTER,
        "VEO_DEBUG_STARTUP":  DEBUG_STARTUP and not _MASTER,
    }
    active = [k for k, v in flags.items() if v]
    if active:
        print("[DebugFlags] ════════════════════════════════════")
        print("[DebugFlags]  🐛 DEBUG MODE ACTIVE")
        for name in active:
            print(f"[DebugFlags]    ✔ {name}")
        print("[DebugFlags] ════════════════════════════════════")
