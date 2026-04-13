"""
VEO Pro Max — Output Naming Helper

Canonical runtime filename contract for all pipeline outputs.
This is the SINGLE SOURCE OF TRUTH for output filenames.

Contract:
    {prompt_4digit}{variant?}_{timestamp?}_{quality?}_{model?}.{ext}

Variant resolution priority:
    1. explicit video_index param (from worker dispatch)
    2. replace_target[1]  (dispatcher replacement tasks)
    3. retry_original_indices  (engine auto-retry tasks)
    4. loop index fallback

Collision strategy:
    name.ext → name_1.ext → name_2.ext → ...

Reference: NAMING_FORMAT_AND_FAILURE_SEMANTICS_REPORT_2026-04-13.md
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger("output_naming")

# ── Constants ──────────────────────────────────────────────────────────────
INDEX_WIDTH = 4
VARIANT_LETTERS = "abcdefghijklmnopqrstuvwxyz"
TIMESTAMP_FMT = "%Y%m%d_%H%M%S"

# Image workflow identifiers
_IMAGE_WORKFLOWS = frozenset({"T2I", "I2I", "TEXT_TO_IMAGE", "IMAGE_TO_IMAGE"})


def resolve_variant_index(
    *,
    task,
    video_index: int = -1,
    loop_index: int = 0,
    total_outputs: int = 1,
) -> Tuple[int, bool, str]:
    """Resolve the correct variant index for a given output.

    Returns:
        (variant_idx, is_multi, source)
        - variant_idx: the index to use for variant letter lookup
        - is_multi: whether a variant letter should be appended
        - source: diagnostic string describing which path was used
    """
    task_output_count = getattr(task, 'output_count', 1) or 1
    is_multi = total_outputs > 1 or task_output_count > 1

    _replace_target = getattr(task, 'replace_target', None)
    _retry_indices = getattr(task, 'retry_original_indices', []) or []

    # Determine variant index + source for diagnostics
    source = "loop_index"
    variant_idx = loop_index

    if video_index >= 0:
        # Priority 1: explicit video_index from worker dispatch
        variant_idx = video_index
        source = "video_index"
        # Replacement tasks (force_retry_video) have output_count=1 but
        # replace a slot in a multi-output parent.  Force is_multi so the
        # variant letter (a/b/c/d) is appended to match the parent's naming.
        if not is_multi and _replace_target:
            is_multi = True
            source = "video_index+replace_target"
    elif not is_multi:
        # Single-output: check if this is a retry/replacement of a multi-output slot
        if _replace_target:
            _orig = _replace_target[1] if len(_replace_target) > 1 else -1
            if _orig >= 0:
                is_multi = True
                variant_idx = _orig
                source = "replace_target"
        elif len(_retry_indices) == 1:
            is_multi = True
            variant_idx = _retry_indices[0]
            source = "retry_original_indices[single]"
    else:
        # Multi-output: map loop index through retry_original_indices if available
        if _retry_indices and loop_index < len(_retry_indices):
            variant_idx = _retry_indices[loop_index]
            source = "retry_original_indices[multi]"

    return variant_idx, is_multi, source


def build_output_filename(
    *,
    task,
    video_index: int = -1,
    loop_index: int = 0,
    total_outputs: int = 1,
    target_quality: Optional[str] = None,
    quality_subfolder: Optional[str] = None,
    settings,
) -> str:
    """Build a canonical output filename.

    Uses the frozen contract:
        {prompt_4digit}{variant?}_{timestamp?}_{quality?}_{model?}.{ext}

    Args:
        task: The Task object (must have prompt_index, model, workflow_type, etc.)
        video_index: Explicit video index from worker dispatch (-1 = not set)
        loop_index: Current index in the output URI loop
        total_outputs: Total number of output URIs being downloaded
        target_quality: Quality string for UQ path (e.g. "1080p")
        quality_subfolder: Quality subfolder name for engine path
        settings: Settings object with include_timestamp, include_quality,
                  include_model, separator

    Returns:
        Filename string (e.g. "0009d_20260413_093259_1080p.mp4")
    """
    # ── Step 1: Prompt index ───────────────────────────────────────────────
    prompt_num = getattr(task, 'prompt_index', 0) + 1
    idx_str = str(prompt_num).zfill(INDEX_WIDTH)

    # ── Step 2: Variant resolution ─────────────────────────────────────────
    variant_idx, is_multi, source = resolve_variant_index(
        task=task,
        video_index=video_index,
        loop_index=loop_index,
        total_outputs=total_outputs,
    )

    # ── Step 3: Build parts ────────────────────────────────────────────────
    parts = []
    sep = getattr(settings, 'separator', '_')

    # Part 1: Index + variant
    if is_multi and variant_idx < len(VARIANT_LETTERS):
        parts.append(f"{idx_str}{VARIANT_LETTERS[variant_idx]}")
    else:
        parts.append(idx_str)

    # Part 2: Timestamp
    if getattr(settings, 'include_timestamp', True):
        parts.append(datetime.now().strftime(TIMESTAMP_FMT))

    # Part 3: Quality
    if getattr(settings, 'include_quality', True):
        file_quality = quality_subfolder or target_quality or getattr(task, 'download_quality', '')
        if file_quality:
            parts.append(file_quality)

    # Part 4: Model
    if getattr(settings, 'include_model', False):
        model = getattr(task, 'model', '') or ''
        if model:
            model_short = model.replace("veo_3_1_", "v31_").replace("_fast_", "_")
            parts.append(model_short)

    # ── Step 4: Extension ──────────────────────────────────────────────────
    wf = (getattr(task, 'workflow_type', '') or '').upper()
    is_image = wf in _IMAGE_WORKFLOWS
    ext = '.png' if is_image else '.mp4'

    filename = sep.join(parts) + ext

    # ── Step 5: Diagnostics ────────────────────────────────────────────────
    log.debug(
        f"[OutputNaming] task={getattr(task, 'id', '?')}, "
        f"prompt={idx_str}, variant_idx={variant_idx}, "
        f"is_multi={is_multi}, source={source}, "
        f"parts={parts} → {filename}"
    )

    return filename


def ensure_unique_path(filepath: Path) -> Path:
    """Ensure filepath doesn't collide with existing files.

    Collision strategy: name.ext → name_1.ext → name_2.ext → ...

    Args:
        filepath: Proposed file path

    Returns:
        A path that does not already exist on disk.
    """
    if not filepath.exists():
        return filepath

    stem = filepath.stem
    ext = filepath.suffix
    parent = filepath.parent

    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 9999:
            # Safety fallback — use microsecond timestamp
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            return parent / f"{stem}_{ts}{ext}"
