"""VEO Pro Max - UI Tabs Package

All 10 tabs for the application.
"""

from .tab_t2v import TabT2V
from .tab_i2v import TabI2V
from .tab_r2v import TabR2V
from .tab_t2i import TabT2I
from .tab_i2i import TabI2I
from .tab_queue import TabQueue
from .tab_settings import TabSettings
from .tab_license import TabLicense
from .tab_about import TabAbout
from .tab_devconsole import TabDevConsole

__all__ = [
    # Generation tabs
    "TabT2V",
    "TabI2V",
    "TabR2V",
    "TabT2I",
    "TabI2I",
    
    # Management tabs
    "TabQueue",
    "TabSettings",
    "TabLicense",
    "TabAbout",
    "TabDevConsole",
]
