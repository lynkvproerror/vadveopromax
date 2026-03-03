"""
VEO Pro Max — Internationalization (i18n)

Bilingual support: English + Tiếng Việt.
Uses JSON locale files + global t() function.
Supports hot-reload (no restart required).

Usage:
    from config.i18n import t, set_language, language_changed
    
    label = QLabel(t("settings.anti_detect"))
    language_changed.connect(self._refresh_text)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal

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


class _I18nManager(QObject):
    """Singleton i18n manager with Qt signal for hot-reload."""
    
    language_changed = Signal(str)  # Emits language code ("en" / "vi")
    
    def __init__(self):
        super().__init__()
        self._lang: str = DEFAULT_LANG
        self._strings: Dict[str, Dict] = {}  # {"en": {...}, "vi": {...}}
        self._flat_cache: Dict[str, str] = {}  # Flattened dot-notation cache
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
        """Flatten nested dict to dot-notation keys.
        
        Preserves list values as-is (e.g., greetings array).
        Converts other non-dict values to string.
        """
        result = {}
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten(value, full_key))
            elif isinstance(value, list):
                result[full_key] = value  # Preserve lists (e.g., greetings)
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
        """Switch language and emit signal for hot-reload.
        
        Args:
            lang: "en", "vi", "English", or "Tiếng Việt"
        """
        code = LANG_MAP.get(lang, lang)
        if code not in self._strings:
            log.warning(f"Unknown language '{lang}' (code={code}), falling back to {DEFAULT_LANG}")
            code = DEFAULT_LANG
        
        if code == self._lang:
            return  # No change
        
        self._lang = code
        self._rebuild_cache()
        log.info(f"Language switched to: {code}")
        self.language_changed.emit(code)
    
    def t(self, key: str) -> str:
        """Translate a dot-notation key.
        
        Returns the translated string, or the key itself if not found.
        
        Examples:
            t("app.title")          → "VEO Pro Max"
            t("settings.language")  → "Ngôn ngữ" (vi) / "Language" (en)
        """
        return self._flat_cache.get(key, key)
    
    def get_language(self) -> str:
        """Get current language code."""
        return self._lang
    
    def get_display_name(self) -> str:
        """Get display name for current language."""
        for display, code in LANG_MAP.items():
            if code == self._lang and display not in ("en", "vi"):
                return display
        return self._lang


# ── Singleton ──
_manager: Optional[_I18nManager] = None


def _get_manager() -> _I18nManager:
    global _manager
    if _manager is None:
        _manager = _I18nManager()
    return _manager


# ── Public API ──

def t(key: str) -> str:
    """Translate a key. Main entry point for all UI text."""
    return _get_manager().t(key)


def set_language(lang: str):
    """Switch language (hot-reload, no restart needed)."""
    _get_manager().set_language(lang)


def get_language() -> str:
    """Get current language code ("en" / "vi")."""
    return _get_manager().get_language()


# Signal for hot-reload — connect to widget refresh methods
language_changed: Signal = property(lambda self: _get_manager().language_changed)


def get_signal():
    """Get the language_changed signal for connecting slots."""
    return _get_manager().language_changed
