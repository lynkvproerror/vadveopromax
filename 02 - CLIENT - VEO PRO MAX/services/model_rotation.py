"""
VEO Pro Max - Smart Model Rotation

Auto-rotate between Gemini models when quota is exceeded (429).
Tracks usage per profile (email) in JSON for daily reset.

Usage:
    from services.model_rotation import get_rotation
    rotation = get_rotation()
    model = rotation.get_model("user@gmail.com")
    # On 429 error:
    rotation.mark_exhausted("user@gmail.com", model)
    next_model = rotation.get_model("user@gmail.com")  # Returns fallback
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict

log = logging.getLogger("veo.rotation")

# Models ordered by RPD (high→low). Rate limits from Google AI Studio dashboard.
# Within same RPD tier: larger model first (better quality).
# Deprecated models (RPD=0) removed: gemini-2.0-flash, gemini-2.0-flash-lite
MODEL_POOL = [
    # ── Gemma 3 family: 14,400 RPD, 30 RPM, 15K TPM ──────────
    # Massive free quota. Best value for prompt enhancement.
    {"id": "gemma-3-27b-it",                "rpd": 14400, "rpm": 30},
    {"id": "gemma-3-12b-it",                "rpd": 14400, "rpm": 30},
    {"id": "gemma-3-4b-it",                 "rpd": 14400, "rpm": 30},
    {"id": "gemma-3-2b-it",                 "rpd": 14400, "rpm": 30},
    {"id": "gemma-3-1b-it",                 "rpd": 14400, "rpm": 30},
    # ── Gemma 4 family: 1,500 RPD, 15 RPM, Unlimited TPM ─────
    # Higher quality reasoning, unlimited token throughput.
    {"id": "gemma-4-31b-it",                "rpd": 1500,  "rpm": 15},
    {"id": "gemma-4-26b-it",                "rpd": 1500,  "rpm": 15},
    # ── Gemini Flash family: 20-500 RPD ───────────────────────
    # Proven models, lower quota but tested stable.
    {"id": "gemini-3.1-flash-lite-preview", "rpd": 500,   "rpm": 15},
    {"id": "gemini-3-flash-preview",        "rpd": 20,    "rpm": 5},
    {"id": "gemini-2.5-flash",              "rpd": 20,    "rpm": 5},
    {"id": "gemini-2.5-flash-lite",         "rpd": 20,    "rpm": 10},
]

# Quick lookup
_MODEL_IDS = [m["id"] for m in MODEL_POOL]
_MODEL_RPD = {m["id"]: m["rpd"] for m in MODEL_POOL}


class ModelRotation:
    """Smart model rotation with per-profile quota tracking."""

    def __init__(self, data_path: Optional[Path] = None):
        self._path = data_path or (Path.home() / ".veoauto" / "model_quota.json")
        self._data: Dict = {}
        self._load()

    # ── Public API ─────────────────────────────────────────────

    def get_model(self, profile_email: str = "") -> str:
        """Get best available model for this profile.

        Returns the highest-priority model that hasn't been marked exhausted.
        If all exhausted, returns the one with highest RPD (least likely full).
        """
        self._maybe_reset()
        key = profile_email or "_default"
        profile_data = self._data.get(key, {})

        for model_info in MODEL_POOL:
            mid = model_info["id"]
            model_state = profile_data.get(mid, {})
            if not model_state.get("exhausted_at"):
                log.debug(f"[Rotation] {key}: using {mid}")
                return mid

        # All exhausted — return highest RPD model (most likely to have recovered)
        best = MODEL_POOL[0]["id"]
        log.warning(f"[Rotation] {key}: all models exhausted, forcing {best}")
        return best

    def mark_exhausted(self, profile_email: str, model: str):
        """Mark a model as exhausted for this profile (got 429)."""
        key = profile_email or "_default"
        if key not in self._data:
            self._data[key] = {}
        if model not in self._data[key]:
            self._data[key][model] = {"used": 0}

        self._data[key][model]["exhausted_at"] = datetime.now().isoformat()
        log.info(f"[Rotation] {key}: marked {model} as exhausted")
        self._save()

    def increment_used(self, profile_email: str, model: str):
        """Increment usage counter for a model."""
        key = profile_email or "_default"
        if key not in self._data:
            self._data[key] = {}
        if model not in self._data[key]:
            self._data[key][model] = {"used": 0}

        self._data[key][model]["used"] = self._data[key][model].get("used", 0) + 1
        # Auto-mark exhausted if limit reached
        rpd = _MODEL_RPD.get(model, 20)
        if self._data[key][model]["used"] >= rpd:
            self._data[key][model]["exhausted_at"] = datetime.now().isoformat()
            log.info(f"[Rotation] {key}: {model} reached RPD limit ({rpd})")
        self._save()

    def reset_exhausted(self, profile_email: str):
        """Clear exhausted flags for all models of this profile.
        
        Called after cooldown wait to allow retry rounds to re-attempt models.
        Preserves usage counters — only clears exhausted_at flags.
        """
        key = profile_email or "_default"
        profile_data = self._data.get(key, {})
        cleared = 0
        for model_id in list(profile_data.keys()):
            if isinstance(profile_data[model_id], dict) and profile_data[model_id].get("exhausted_at"):
                profile_data[model_id].pop("exhausted_at", None)
                cleared += 1
        if cleared:
            log.info(f"[Rotation] {key}: reset {cleared} exhausted model(s) for retry")
            self._save()

    def get_all_models(self) -> List[str]:
        """Get all available model IDs."""
        return list(_MODEL_IDS)

    def get_status(self, profile_email: str = "") -> List[Dict]:
        """Get status of all models for a profile (for UI display)."""
        self._maybe_reset()
        key = profile_email or "_default"
        profile_data = self._data.get(key, {})

        result = []
        for m in MODEL_POOL:
            state = profile_data.get(m["id"], {})
            result.append({
                "id": m["id"],
                "rpd": m["rpd"],
                "rpm": m["rpm"],
                "used": state.get("used", 0),
                "exhausted": bool(state.get("exhausted_at")),
            })
        return result

    # ── Daily Reset ────────────────────────────────────────────

    def _maybe_reset(self):
        """Auto-reset all counters at midnight."""
        today = date.today().isoformat()
        if self._data.get("_last_reset") != today:
            log.info(f"[Rotation] Daily reset (new day: {today})")
            # Clear all profile data but keep structure
            for key in list(self._data.keys()):
                if key.startswith("_"):
                    continue
                for model in self._data[key]:
                    self._data[key][model] = {"used": 0}
            self._data["_last_reset"] = today
            self._save()

    # ── Persistence ────────────────────────────────────────────

    def _load(self):
        """Load quota data from JSON."""
        try:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception as e:
            log.debug(f"[Rotation] Load failed: {e}")
            self._data = {}

    def _save(self):
        """Save quota data to JSON."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            log.debug(f"[Rotation] Save failed: {e}")


# ── Singleton ──────────────────────────────────────────────────

_instance: Optional[ModelRotation] = None

def get_rotation() -> ModelRotation:
    """Get global ModelRotation instance."""
    global _instance
    if _instance is None:
        _instance = ModelRotation()
    return _instance
