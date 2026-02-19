"""
DevConsole page widgets — sidebar navigation content pages.

Each page is a self-contained QWidget displayed in a QStackedWidget
when the corresponding sidebar item is selected.
"""

from .page_dashboard import DashboardPage
from .page_queue import QueuePerfPage
from .page_accounts import AccountsPage
from .page_logs import LogsPage
from .page_network import NetworkPage

__all__ = [
    "DashboardPage",
    "QueuePerfPage",
    "AccountsPage",
    "LogsPage",
    "NetworkPage",
]
