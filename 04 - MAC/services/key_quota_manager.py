"""
Key Quota Manager — Simple round-robin API key rotation.

Cycles through all available keys without quota tracking.
All mark_* methods are kept as no-ops for backward compatibility.
"""

import logging
import threading
from typing import Dict, List, Optional

log = logging.getLogger("veo.key_quota")


class KeyQuotaManager:
    """Singleton — simple round-robin key rotation (no quota tracking)."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._index = 0  # Round-robin counter

    @classmethod
    def instance(cls) -> "KeyQuotaManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Public API ──

    def get_available_key(self, keys: List[str]) -> Optional[str]:
        """Get next key via round-robin. Always returns a key if list is non-empty."""
        clean = [k.strip() for k in keys if k.strip()]
        if not clean:
            return None
        key = clean[self._index % len(clean)]
        self._index += 1
        return key

    def mark_rpm_blocked(self, key: str):
        """No-op — kept for backward compatibility."""
        pass

    def mark_rpd_blocked(self, key: str):
        """No-op — kept for backward compatibility."""
        pass

    def is_available(self, key: str) -> bool:
        """Always returns True — no quota tracking."""
        return True

    def get_status_summary(self) -> str:
        """Simple status."""
        return f"  Round-robin index: {self._index} (no quota tracking)"

    def save_to_json(self):
        """No-op — no state to persist."""
        pass


def get_quota_manager() -> KeyQuotaManager:
    """Get the singleton KeyQuotaManager instance."""
    return KeyQuotaManager.instance()
