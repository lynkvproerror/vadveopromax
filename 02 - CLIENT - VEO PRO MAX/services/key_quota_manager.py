"""
Key Quota Manager — API key rotation with 403-denial tracking.

Cycles through available keys via round-robin. Keys that receive 403
"denied access" are marked and skipped for the remainder of the session.
All mark_rpm/rpd methods are kept as no-ops for backward compatibility.
"""

import logging
import threading
from typing import Dict, List, Optional, Set

log = logging.getLogger("veo.key_quota")


class KeyQuotaManager:
    """Singleton — round-robin key rotation with 403-denial tracking."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._index = 0  # Round-robin counter
        self._denied_keys: Set[str] = set()  # Keys that returned 403

    @classmethod
    def instance(cls) -> "KeyQuotaManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── Public API ──

    def get_available_key(self, keys: List[str]) -> Optional[str]:
        """Get next available key via round-robin, skipping denied keys.
        
        If all keys are denied, falls back to returning the next key
        anyway (user may have fixed the project in the meantime).
        """
        clean = [k.strip() for k in keys if k.strip()]
        if not clean:
            return None
        
        # Try to find a non-denied key
        available = [k for k in clean if k not in self._denied_keys]
        if available:
            key = available[self._index % len(available)]
            self._index += 1
            return key
        
        # All keys denied — fall back to round-robin (best effort)
        log.warning(
            f"[KeyQuota] All {len(clean)} keys are denied — "
            f"trying round-robin fallback (user may have fixed project)"
        )
        key = clean[self._index % len(clean)]
        self._index += 1
        return key

    def mark_denied(self, key: str):
        """Mark a key as 403-denied. It will be skipped in future rotations."""
        stripped = key.strip()
        if stripped and stripped not in self._denied_keys:
            self._denied_keys.add(stripped)
            log.warning(
                f"[KeyQuota] Key ...{stripped[-8:]} marked DENIED (403). "
                f"Total denied: {len(self._denied_keys)}"
            )

    def clear_denied(self, key: str = ""):
        """Clear denied status for a specific key, or all keys if empty."""
        if key:
            self._denied_keys.discard(key.strip())
        else:
            self._denied_keys.clear()
            log.info("[KeyQuota] Cleared all denied keys")

    def mark_rpm_blocked(self, key: str):
        """No-op — kept for backward compatibility."""
        pass

    def mark_rpd_blocked(self, key: str):
        """No-op — kept for backward compatibility."""
        pass

    def reset_rpm_blocks(self):
        """Clear all denied keys — backward compat alias for retry rounds."""
        self.clear_denied()

    def is_available(self, key: str) -> bool:
        """Returns False if key is denied, True otherwise."""
        return key.strip() not in self._denied_keys

    def get_status_summary(self) -> str:
        """Status including denied key count."""
        denied_count = len(self._denied_keys)
        suffix = f", denied keys: {denied_count}" if denied_count else ""
        return f"  Round-robin index: {self._index}{suffix}"

    def save_to_json(self):
        """No-op — no state to persist."""
        pass


def get_quota_manager() -> KeyQuotaManager:
    """Get the singleton KeyQuotaManager instance."""
    return KeyQuotaManager.instance()
