"""
VEO Pro Max — Internationalization (i18n)

Bilingual support: English + Tiếng Việt.
Uses JSON locale files + global t() function.
Supports hot-reload (no restart required).

Usage:
    from config.i18n import t, set_language, get_signal
    
    label = QLabel(t("settings.anti_detect"))
    get_signal().connect(self._refresh_text)

★ macOS M-chip safety: This module does NOT import PySide6 at module level.
  PySide6 (QObject/Signal) is loaded lazily only when get_signal() is called,
  which is always after QApplication exists. This prevents segfault on Apple
  Silicon where Qt metaclass registration before QApplication crashes.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any, List, Callable

log = logging.getLogger(__name__)

# ── Locale directory ──
LOCALES_DIR = Path(__file__).parent / "locales"

# ── Language mapping ──
LANG_MAP = {
    "Tiếng Việt": "vi",
    "English": "en",
    "vi": "vi",
    "en": "en",
}

DEFAULT_LANG = "vi"


class _I18nManagerPlain:
    """Pure Python i18n manager — NO Qt dependency.
    
    Handles all translation logic. Qt Signal support is added
    lazily via _I18nManagerQt wrapper only when get_signal() is called.
    """
    
    def __init__(self):
        self._lang: str = DEFAULT_LANG
        self._strings: Dict[str, Dict] = {}  # {"en": {...}, "vi": {...}}
        self._flat_cache: Dict[str, str] = {}  # Flattened dot-notation cache
        self._listeners: List[Callable] = []   # Plain callback listeners
        self._load_all_locales()
    
    def _load_all_locales(self):
        """Pre-load all locale JSON files."""
        if not LOCALES_DIR.exists():
            log.warning(f"Locales directory not found: {LOCALES_DIR}")
            return
        for json_file in LOCALES_DIR.glob("*.json"):
            lang_code = json_file.stem  # "en", "vi"
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    self._strings[lang_code] = json.load(f)
                log.debug(f"Loaded locale: {lang_code} ({len(self._strings[lang_code])} top-level keys)")
            except Exception as e:
                log.error(f"Failed to load locale {json_file}: {e}")
        self._rebuild_cache()
    
    def _flatten(self, data: dict, prefix: str = "") -> dict:
        """Flatten nested dict to dot-notation keys."""
        result = {}
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten(value, full_key))
            elif isinstance(value, list):
                result[full_key] = value
            else:
                result[full_key] = str(value)
        return result
    
    def _rebuild_cache(self):
        """Rebuild flat cache for current language."""
        lang_data = self._strings.get(self._lang, {})
        self._flat_cache = self._flatten(lang_data)
    
    @property
    def lang(self) -> str:
        return self._lang
    
    def set_language(self, lang: str):
        """Switch language and notify listeners."""
        code = LANG_MAP.get(lang, lang)
        if code not in self._strings:
            log.warning(f"Unknown language '{lang}' (code={code}), falling back to {DEFAULT_LANG}")
            code = DEFAULT_LANG
        
        if code == self._lang:
            return
        
        self._lang = code
        self._rebuild_cache()
        log.info(f"Language switched to: {code}")
        
        # Notify plain listeners
        for cb in self._listeners:
            try:
                cb(code)
            except Exception:
                pass
    
    def t(self, key: str) -> str:
        """Translate a dot-notation key."""
        return self._flat_cache.get(key, key)
    
    def get_language(self) -> str:
        return self._lang
    
    def get_display_name(self) -> str:
        for display, code in LANG_MAP.items():
            if code == self._lang and display not in ("en", "vi"):
                return display
        return self._lang


# ── Singleton (pure Python — always safe) ──
_manager: Optional[_I18nManagerPlain] = None
_qt_signal_wrapper: Any = None  # Lazy QObject wrapper


def _get_manager() -> _I18nManagerPlain:
    global _manager
    if _manager is None:
        _manager = _I18nManagerPlain()
    return _manager


# ── Public API ──

def t(key: str) -> str:
    """Translate a key. Main entry point for all UI text."""
    return _get_manager().t(key)


def set_language(lang: str):
    """Switch language (hot-reload, no restart needed)."""
    mgr = _get_manager()
    mgr.set_language(lang)
    # Also emit Qt signal if wrapper exists
    if _qt_signal_wrapper is not None:
        try:
            _qt_signal_wrapper.language_changed.emit(lang)
        except Exception:
            pass


def get_language() -> str:
    """Get current language code ("en" / "vi")."""
    return _get_manager().get_language()


def get_signal():
    """Get the language_changed Qt Signal for connecting slots.
    
    ★ This is the ONLY function that imports PySide6.
    It is always called AFTER QApplication exists (from UI code).
    """
    global _qt_signal_wrapper
    if _qt_signal_wrapper is None:
        try:
            from PySide6.QtCore import QObject, Signal
            
            class _QtSignalBridge(QObject):
                language_changed = Signal(str)
            
            _qt_signal_wrapper = _QtSignalBridge()
        except Exception as e:
            log.warning(f"Qt Signal not available: {e}")
            return None
    return _qt_signal_wrapper.language_changed


# Backward compatibility alias
language_changed = property(lambda self: get_signal())

