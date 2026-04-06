"""
VEO Pro Max - Prompt Schema Validator

Strict validation for AI-generated prompts:
  Layer 1 (JSON): Required fields, non-empty prompt_text, negative_prompt,
                   camera_movement, duration sanity, character consistency.
  Layer 2 (all):  Sensitive word check via rules_loader patterns.
  Layer 3 (all):  Scene count check vs expected.

Usage:
    from core.prompt_validator import validate_prompts
    validate_prompts(prompts, expected_count=10, prompt_format="json", rules_loader=loader)
"""

import json
import logging
from typing import List, Optional, Dict

log = logging.getLogger("veo.validator")


# ── Required vs Expected fields ────────────────────────────────

_REQUIRED_FIELDS = {"scene_index", "prompt_text"}

_EXPECTED_FIELDS = {
    "scene_type", "type", "shot_type", "camera_movement",
    "setting", "characters", "negative_prompt", "duration_s",
}


def validate_prompts(
    prompts: List,
    expected_count: int = 0,
    prompt_format: str = "text",
    rules_loader=None,
) -> None:
    """Validate prompts in-place: set .valid=False and append to .violations.

    Args:
        prompts: List of PromptRow objects (must have .prompt, .valid, .violations).
        expected_count: Expected scene count (0 = skip check).
        prompt_format: "json" enables schema validation; "text" skips Layer 1.
        rules_loader: Optional rules loader with get_sensitive_words() method.
    """
    # ── Layer 1: JSON schema validation ──
    if prompt_format == "json":
        _validate_json_schema(prompts)

    # ── Layer 2: Scene count check ──
    if expected_count > 0 and len(prompts) != expected_count:
        delta = len(prompts) - expected_count
        direction = f"+{delta}" if delta > 0 else str(delta)
        log.warning(
            f"[Validator] Scene count mismatch: got {len(prompts)}, "
            f"expected {expected_count} ({direction})"
        )
        # Attach batch-level warning to last prompt
        if prompts:
            prompts[-1].violations.append(
                f"Scene count: {len(prompts)} vs expected {expected_count}"
            )

    # ── Layer 3: Sensitive word check ──
    _validate_sensitive_words(prompts, rules_loader)

    # Summary log
    invalid = sum(1 for p in prompts if not p.valid)
    warned = sum(1 for p in prompts if p.violations and p.valid)
    if invalid or warned:
        log.info(
            f"[Validator] Result: {invalid} invalid, {warned} warned "
            f"out of {len(prompts)} prompts"
        )


def _validate_json_schema(prompts: List) -> None:
    """Layer 1: Validate JSON prompts against schema rules."""
    all_characters: Dict[str, int] = {}  # char_name → appearance count

    for p in prompts:
        try:
            scene = json.loads(p.prompt)
        except (json.JSONDecodeError, ValueError):
            p.valid = False
            p.violations.append("JSON parse error: prompt is not valid JSON")
            continue

        if not isinstance(scene, dict):
            p.valid = False
            p.violations.append("JSON schema error: prompt must be a JSON object")
            continue

        # Required fields — hard fail
        for field in _REQUIRED_FIELDS:
            val = scene.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                p.valid = False
                p.violations.append(f"Missing required: {field}")

        # Expected fields — warning only
        missing_expected = [f for f in _EXPECTED_FIELDS if f not in scene]
        if missing_expected:
            p.violations.append(
                f"Missing optional: {', '.join(missing_expected)}"
            )

        # Negative prompt quality
        neg = scene.get("negative_prompt", "")
        if isinstance(neg, str) and len(neg.strip()) < 10:
            p.violations.append("Weak negative_prompt (< 10 chars)")

        # Camera movement presence
        cam = scene.get("camera_movement", "")
        if isinstance(cam, str) and cam.strip().lower() in ("", "none"):
            p.violations.append("Missing camera_movement")

        # Duration sanity
        dur = scene.get("duration_s", 8)
        if not isinstance(dur, (int, float)) or dur <= 0 or dur > 60:
            p.violations.append(f"Invalid duration_s: {dur}")

        # prompt_text minimum length (avoid empty/stub prompts)
        pt = scene.get("prompt_text", "")
        if isinstance(pt, str) and 0 < len(pt.strip()) < 30:
            p.violations.append(
                f"prompt_text too short ({len(pt.strip())} chars, min 30)"
            )

        # Track characters for consistency check
        chars = scene.get("characters", [])
        if isinstance(chars, list):
            for c in chars:
                if isinstance(c, str) and c.strip():
                    name = c.strip()
                    all_characters[name] = all_characters.get(name, 0) + 1

    # Character consistency: log if any named character appears in < 30% of scenes
    if all_characters and len(prompts) >= 3:
        threshold = max(2, int(len(prompts) * 0.3))
        sparse_chars = [
            f"'{name}' ({count}/{len(prompts)})"
            for name, count in all_characters.items()
            if count < threshold
        ]
        if sparse_chars:
            log.info(
                f"[Validator] Sparse characters (< {threshold} scenes): "
                f"{', '.join(sparse_chars)}"
            )


def _validate_sensitive_words(prompts: List, rules_loader=None) -> None:
    """Layer 3: Check prompts against sensitive word patterns."""
    sensitive_patterns = []
    if rules_loader and hasattr(rules_loader, 'get_sensitive_words'):
        try:
            sensitive_patterns = rules_loader.get_sensitive_words()
        except Exception:
            pass

    if not sensitive_patterns:
        return

    for p in prompts:
        lower_prompt = p.prompt.lower()
        for pattern in sensitive_patterns:
            if isinstance(pattern, str) and pattern.lower() in lower_prompt:
                p.valid = False
                p.violations.append(f"Sensitive: '{pattern}'")
            elif hasattr(pattern, 'search') and pattern.search(p.prompt):
                p.valid = False
                p.violations.append(f"Pattern match: {pattern.pattern}")
