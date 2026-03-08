"""
Key Quota Manager — Smart API key rotation with quota tracking.

Tracks per-key RPM (per-minute) and RPD (per-day) limits.
Auto re-enables keys when quota refreshes:
  - RPM: 60 seconds after block
  - RPD: 00:00 Pacific Time (~14:00-15:00 Vietnam time)

Persists state to ~/.veoauto/key_quota.json every 5 minutes.
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("veo.key_quota")

# Pacific Time offset (UTC-8 standard, UTC-7 daylight)
try:
    from zoneinfo import ZoneInfo
    PACIFIC = ZoneInfo("America/Los_Angeles")
except ImportError:
    PACIFIC = timezone(timedelta(hours=-8))

_QUOTA_FILE = Path.home() / ".veoauto" / "key_quota.json"
_SAVE_INTERVAL = 300  # 5 minutes


class KeyState:
    """Quota state for a single API key."""

    __slots__ = ("key", "rpm_blocked_at", "rpd_blocked_at",
                 "total_requests", "last_used")

    def __init__(self, key: str):
        self.key = key
        self.rpm_blocked_at: Optional[float] = None   # epoch timestamp
        self.rpd_blocked_at: Optional[float] = None   # epoch timestamp
        self.total_requests: int = 0
        self.last_used: Optional[float] = None

    def is_rpm_available(self) -> bool:
        """RPM block clears after 60 seconds."""
        if self.rpm_blocked_at is None:
            return True
        return time.time() - self.rpm_blocked_at >= 60

    def is_rpd_available(self) -> bool:
        """RPD block clears at next 00:00 Pacific Time."""
        if self.rpd_blocked_at is None:
            return True
        now = datetime.now(PACIFIC)
        blocked = datetime.fromtimestamp(self.rpd_blocked_at, tz=PACIFIC)
        # Next reset = midnight PT after the block time
        next_reset = blocked.replace(hour=0, minute=0, second=0, microsecond=0)
        next_reset += timedelta(days=1)
        return now >= next_reset

    def is_available(self) -> bool:
        return self.is_rpm_available() and self.is_rpd_available()

    def to_dict(self) -> dict:
        return {
            "rpm_blocked_at": self.rpm_blocked_at,
            "rpd_blocked_at": self.rpd_blocked_at,
            "total_requests": self.total_requests,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, key: str, data: dict) -> "KeyState":
        ks = cls(key)
        ks.rpm_blocked_at = data.get("rpm_blocked_at")
        ks.rpd_blocked_at = data.get("rpd_blocked_at")
        ks.total_requests = data.get("total_requests", 0)
        ks.last_used = data.get("last_used")
        return ks


class KeyQuotaManager:
    """Singleton managing quota state for all custom API keys."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._states: Dict[str, KeyState] = {}
        self._save_timer: Optional[threading.Timer] = None
        self._dirty = False
        self._load_from_json()
        self._schedule_save()

    @classmethod
    def instance(cls) -> "KeyQuotaManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_state(self, key: str) -> KeyState:
        """Get or create state for a key."""
        key = key.strip()
        if key not in self._states:
            self._states[key] = KeyState(key)
        return self._states[key]

    # ── Public API ──

    def get_available_key(self, keys: List[str]) -> Optional[str]:
        """Get first available key from the list (round-robin aware).

        Args:
            keys: List of API keys to choose from.

        Returns:
            First available key, or None if all blocked.
        """
        if not keys:
            return None

        for key in keys:
            key = key.strip()
            if not key:
                continue
            state = self._get_state(key)
            if state.is_available():
                state.total_requests += 1
                state.last_used = time.time()
                self._dirty = True
                return key

        # All keys blocked — find the one that will unblock soonest
        log.warning(
            f"[KeyQuota] All {len(keys)} keys blocked. "
            f"RPM keys will refresh within 60s."
        )
        return None

    def mark_rpm_blocked(self, key: str):
        """Mark a key as RPM rate-limited (refreshes in 60s)."""
        if not key:
            return
        state = self._get_state(key)
        state.rpm_blocked_at = time.time()
        self._dirty = True
        remaining = 60
        log.info(
            f"[KeyQuota] Key ...{key[-8:]} RPM blocked "
            f"(refresh in {remaining}s)"
        )

    def mark_rpd_blocked(self, key: str):
        """Mark a key as RPD exhausted (refreshes at 00:00 PT)."""
        if not key:
            return
        state = self._get_state(key)
        state.rpd_blocked_at = time.time()
        self._dirty = True

        # Calculate next refresh time for logging
        now_pt = datetime.now(PACIFIC)
        next_reset = now_pt.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        delta = next_reset - now_pt
        hours = int(delta.total_seconds() // 3600)
        mins = int((delta.total_seconds() % 3600) // 60)
        log.info(
            f"[KeyQuota] Key ...{key[-8:]} RPD exhausted "
            f"(refresh in {hours}h{mins}m at 00:00 PT)"
        )

    def is_available(self, key: str) -> bool:
        """Check if a key is currently available."""
        if not key:
            return False
        return self._get_state(key).is_available()

    def get_status_summary(self) -> str:
        """Get human-readable status of all tracked keys."""
        lines = []
        for key, state in self._states.items():
            suffix = key[-8:] if len(key) > 8 else key
            status = "✅" if state.is_available() else "❌"
            rpm = "OK" if state.is_rpm_available() else "BLOCKED"
            rpd = "OK" if state.is_rpd_available() else "EXHAUSTED"
            lines.append(
                f"  ...{suffix}: {status} RPM={rpm} RPD={rpd} "
                f"reqs={state.total_requests}"
            )
        return "\n".join(lines) if lines else "  (no keys tracked)"

    # ── Persistence ──

    def _load_from_json(self):
        """Load saved quota state from disk."""
        try:
            if _QUOTA_FILE.exists():
                data = json.loads(_QUOTA_FILE.read_text(encoding="utf-8"))
                for key, state_data in data.items():
                    self._states[key] = KeyState.from_dict(key, state_data)
                log.info(
                    f"[KeyQuota] Loaded {len(self._states)} key states"
                )
        except Exception as e:
            log.warning(f"[KeyQuota] Failed to load quota file: {e}")

    def save_to_json(self):
        """Persist current quota state to disk."""
        if not self._dirty:
            return
        try:
            _QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.to_dict() for k, v in self._states.items()}
            _QUOTA_FILE.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            self._dirty = False
            log.debug(f"[KeyQuota] Saved {len(data)} key states")
        except Exception as e:
            log.warning(f"[KeyQuota] Failed to save: {e}")

    def _schedule_save(self):
        """Schedule periodic save every 5 minutes."""
        def _tick():
            self.save_to_json()
            self._schedule_save()

        self._save_timer = threading.Timer(_SAVE_INTERVAL, _tick)
        self._save_timer.daemon = True
        self._save_timer.start()


def get_quota_manager() -> KeyQuotaManager:
    """Get the singleton KeyQuotaManager instance."""
    return KeyQuotaManager.instance()
