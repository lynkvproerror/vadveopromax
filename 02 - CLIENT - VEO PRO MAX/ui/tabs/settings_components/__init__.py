"""
Settings components — mixin classes extracted from tab_settings.py.

Each mixin owns a cohesive group of methods that operate on shared `self`
attributes initialised by TabSettings.__init__.
"""

from .profiles_table import SettingsProfilesMixin
from .settings_sections import SettingsSectionsMixin
from .pipeline_enhancer import SettingsPipelineEnhancerMixin
from .browser_controls import SettingsBrowserControlsMixin

__all__ = [
    "SettingsProfilesMixin",
    "SettingsSectionsMixin",
    "SettingsPipelineEnhancerMixin",
    "SettingsBrowserControlsMixin",
]
