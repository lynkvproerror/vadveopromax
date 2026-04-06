"""
VEO Pro Max - Pipeline Session Registry

Replaces the unreliable "newest _pipeline_state.json in entire output folder"
strategy with an explicit registry that tracks the last pipeline project
the user actively worked on.

Registry file: ~/.veoauto/pipeline_registry.json
Format:
{
    "last_project_path": "D:/Output/Production_Topic_Name",
    "last_modified": "2026-04-04T07:30:00",
    "session_file": "_pipeline_session.json",
    "checksum": "sha256:abc123...",
    "topic": "Topic Name",
    "stages_completed": 5
}

Usage:
    from core.session_registry import SessionRegistry
    reg = SessionRegistry()
    reg.update(project_dir, topic="My Topic", stages_completed=5)
    info = reg.get_last_project()
    if info and info.is_valid():
        restore_from(info.session_path)
"""

import json
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

log = logging.getLogger("veo.registry")

_REGISTRY_PATH = Path.home() / ".veoauto" / "pipeline_registry.json"


@dataclass
class RegistryEntry:
    """Info about the last known pipeline project."""
    project_path: str = ""
    last_modified: str = ""
    session_file: str = "_pipeline_session.json"
    checksum: str = ""
    topic: str = ""
    stages_completed: int = 0

    @property
    def session_path(self) -> Path:
        return Path(self.project_path) / self.session_file

    @property
    def state_path(self) -> Path:
        """Fallback: legacy _pipeline_state.json."""
        return Path(self.project_path) / "_pipeline_state.json"

    def is_valid(self) -> bool:
        """Check if the registered session file still exists and matches checksum."""
        sp = self.session_path
        if not sp.exists():
            # Try legacy fallback
            sp = self.state_path
            if not sp.exists():
                log.debug(f"[Registry] Invalid: neither session nor state file exists at {self.project_path}")
                return False

        # Checksum verification (if we have one)
        if self.checksum:
            try:
                actual = _compute_checksum(sp)
                if actual != self.checksum:
                    log.warning(
                        f"[Registry] Checksum mismatch for {sp.name}: "
                        f"expected {self.checksum[:16]}..., got {actual[:16]}..."
                    )
                    return False
            except Exception as e:
                log.debug(f"[Registry] Checksum verify failed: {e}")
                # File exists but checksum failed — still valid for restore attempt
                return True

        return True


class SessionRegistry:
    """Persistent registry tracking the last active pipeline project."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _REGISTRY_PATH

    def update(
        self,
        project_dir: str,
        topic: str = "",
        stages_completed: int = 0,
        session_file: str = "_pipeline_session.json",
    ) -> None:
        """Register/update the current pipeline project as the active one.

        Called on every stage confirm/skip and session save.
        """
        project_path = Path(project_dir)
        if not project_path.is_dir():
            return

        # Compute checksum of session file
        sf = project_path / session_file
        checksum = ""
        if sf.exists():
            try:
                checksum = _compute_checksum(sf)
            except Exception:
                pass

        entry = {
            "last_project_path": str(project_path),
            "last_modified": datetime.now().isoformat(),
            "session_file": session_file,
            "checksum": checksum,
            "topic": topic,
            "stages_completed": stages_completed,
        }

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(entry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            log.debug(f"[Registry] Updated: {project_path.name} ({stages_completed} stages)")
        except Exception as e:
            log.warning(f"[Registry] Failed to write: {e}")

    def get_last_project(self) -> Optional[RegistryEntry]:
        """Retrieve the last registered pipeline project.

        Returns None if no registry exists or if data is corrupted.
        """
        if not self._path.exists():
            return None

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return RegistryEntry(
                project_path=raw.get("last_project_path", ""),
                last_modified=raw.get("last_modified", ""),
                session_file=raw.get("session_file", "_pipeline_session.json"),
                checksum=raw.get("checksum", ""),
                topic=raw.get("topic", ""),
                stages_completed=raw.get("stages_completed", 0),
            )
        except Exception as e:
            log.debug(f"[Registry] Failed to read: {e}")
            return None

    def clear(self) -> None:
        """Clear the registry (called on pipeline reset)."""
        if self._path.exists():
            try:
                self._path.unlink()
                log.debug("[Registry] Cleared")
            except Exception:
                pass


def _compute_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()[:32]}"
