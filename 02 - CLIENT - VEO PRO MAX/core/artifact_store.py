"""
VEO Pro Max - Artifact Store

Designated module for project output file management.
Handles saving generated content (Bible, Master, Prompts, Dubbing, SEO)
to the output directory structure.

Currently re-exports from ProjectBuilder._save_outputs.
When full decomposition is done, this module will contain the actual
save/load logic decoupled from the builder.

Usage:
    from core.artifact_store import save_project_outputs
    save_project_outputs(result, output_dir, prompt_format="json")
"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("veo.artifacts")


def save_project_outputs(result, output_dir: str, prompt_format: str = "text") -> None:
    """Save generated content to output files.

    Args:
        result: TopicResult with .bible, .master, .dubbing, .seo, .research, .files
        output_dir: Absolute path to project output directory.
        prompt_format: "json" or "text" — determines prompts filename.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    prompts_filename = "Prompts.json" if prompt_format == "json" else "Prompts.txt"

    file_map = {
        "Bible":   ("Bible.md",        getattr(result, 'bible', '')),
        "Master":  ("Master.txt",      getattr(result, 'master', '')),
        "Prompts": (prompts_filename,  result.files.get("Prompts", "") if hasattr(result, 'files') else ''),
        "Dubbing": ("Dubbing.txt",     getattr(result, 'dubbing', '')),
        "SEO":     ("SEO.txt",         getattr(result, 'seo', '')),
    }

    written = []
    for key, (filename, content) in file_map.items():
        if content:
            (out / filename).write_text(content, encoding="utf-8")
            written.append(filename)

    # Research (internal, also saved)
    research = getattr(result, 'research', '')
    if research:
        (out / "Research.md").write_text(research, encoding="utf-8")
        written.append("Research.md")

    log.info(f"[Artifacts] Saved {len(written)} files to {output_dir}: {', '.join(written)}")


def load_project_file(project_dir: str, filename: str) -> Optional[str]:
    """Load a specific file from a project directory.

    Args:
        project_dir: Absolute path to project output directory.
        filename: Name of file to load (e.g. "Bible.md").

    Returns:
        File content as string, or None if not found.
    """
    path = Path(project_dir) / filename
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"[Artifacts] Failed to read {path}: {e}")
    return None


def list_project_files(project_dir: str) -> dict:
    """List all project output files with sizes.

    Returns:
        Dict of {filename: size_bytes}.
    """
    out = Path(project_dir)
    if not out.is_dir():
        return {}
    return {
        f.name: f.stat().st_size
        for f in out.iterdir()
        if f.is_file() and not f.name.startswith("_")
    }
