"""
VEO Pro Max - Workflow Scanner

Scans configured directories for .md template files with YAML frontmatter.
Templates self-describe via frontmatter fields: template_id, display_name,
group, keywords, visual_style, structure, scene_count_range, etc.

Zero-hardcode policy: all workflow logic comes from template files.
"""

import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

from core.data_loader import load_text, scan_data_files

try:
    from core.embedded_templates import EMBEDDED_TEMPLATES
except ImportError:
    EMBEDDED_TEMPLATES = []

log = logging.getLogger("veo.workflow")


@dataclass
class WorkflowTemplate:
    """A discovered workflow template from a .md file."""

    template_id: str = ""
    display_name: str = ""
    group: str = "untagged"
    keywords: List[str] = field(default_factory=list)
    visual_style: str = ""
    structure: str = ""
    scene_count_range: Tuple[int, int] = (8, 12)
    output_files: List[str] = field(default_factory=list)
    shared_rules: List[str] = field(default_factory=list)
    advanced_rules: List[str] = field(default_factory=list)
    body: str = ""  # Template content sans frontmatter
    source_path: Path = field(default_factory=Path)

    @property
    def is_tagged(self) -> bool:
        return bool(self.template_id)


@dataclass
class MatchResult:
    """Result of auto-detect mode matching."""

    template: WorkflowTemplate
    confidence: float  # 0.0 - 1.0
    matched_keywords: List[str] = field(default_factory=list)


class WorkflowScanner:
    """Scan directories for .md workflow templates and auto-detect modes."""

    # ── YAML frontmatter regex ─────────────────────────────────
    _FM_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n",
        re.DOTALL,
    )

    # Known frontmatter fields → types
    _LIST_FIELDS = {
        "keywords", "output_files", "shared_rules", "advanced_rules",
    }
    _RANGE_FIELDS = {"scene_count_range"}

    def __init__(self):
        self._templates: List[WorkflowTemplate] = []

    @property
    def templates(self) -> List[WorkflowTemplate]:
        return self._templates

    @property
    def template_count(self) -> int:
        return len(self._templates)

    @property
    def groups(self) -> List[str]:
        """Get unique groups from loaded templates."""
        seen = []
        for t in self._templates:
            if t.group not in seen:
                seen.append(t.group)
        return seen

    def scan_sources(self, dirs: List[str], recursive: bool = True) -> int:
        """Scan directories for .md template files.

        Args:
            dirs: List of directory paths to scan.
            recursive: If True, scan subdirectories too.

        Returns:
            Number of templates found.
        """
        self._templates = []
        for dir_path in dirs:
            p = Path(dir_path)
            if not p.exists() or not p.is_dir():
                log.warning(f"[Scan] Skipping non-existent dir: {dir_path}")
                continue

            pattern = "**/*.md" if recursive else "*.md"
            for md_file in sorted(scan_data_files(p, recursive=recursive)):
                try:
                    tmpl = self._parse_template(md_file)
                    if tmpl:
                        self._templates.append(tmpl)
                except Exception as e:
                    log.warning(f"[Scan] Failed to parse {md_file}: {e}")

        log.info(f"[Scan] Found {len(self._templates)} templates from {len(dirs)} sources")
        return len(self._templates)

    def load_embedded(self) -> int:
        """Load embedded templates as fallback.

        Called automatically when scan_sources() finds 0 templates.
        Safe to call manually if you want to pre-populate from embedded data.

        Returns:
            Number of embedded templates loaded.
        """
        if not EMBEDDED_TEMPLATES:
            log.warning("[Scan] No embedded templates available")
            return 0

        loaded = 0
        for t_dict in EMBEDDED_TEMPLATES:
            try:
                tmpl = WorkflowTemplate(
                    template_id=t_dict.get("template_id", ""),
                    display_name=t_dict.get("display_name", ""),
                    group=t_dict.get("group", "untagged"),
                    keywords=t_dict.get("keywords", []),
                    visual_style=t_dict.get("visual_style", ""),
                    structure=t_dict.get("structure", ""),
                    scene_count_range=tuple(t_dict.get("scene_count_range", [8, 12])),
                    output_files=t_dict.get("output_files", []),
                    shared_rules=t_dict.get("shared_rules", []),
                    advanced_rules=t_dict.get("advanced_rules", []),
                    body=t_dict.get("body", ""),
                )
                self._templates.append(tmpl)
                loaded += 1
            except Exception as e:
                log.warning(f"[Scan] Failed to load embedded template '{t_dict.get('template_id')}': {e}")

        log.info(f"[Scan] Loaded {loaded} embedded templates (fallback mode)")
        return loaded

    def get_by_id(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Get template by ID."""
        for t in self._templates:
            if t.template_id == template_id:
                return t
        return None

    def get_by_group(self, group: str) -> List[WorkflowTemplate]:
        """Get all templates in a group."""
        return [t for t in self._templates if t.group == group]

    # ── Auto-detect Mode ───────────────────────────────────────

    def detect_mode(self, topic_text: str, top_n: int = 3) -> List[MatchResult]:
        """Score topic against all templates' keywords.

        Uses Jaccard-based scoring: how many of a template's keywords
        appear in the topic text.

        Args:
            topic_text: User's topic text.
            top_n: Number of top matches to return.

        Returns:
            List of MatchResult sorted by confidence descending.
        """
        if not topic_text or not self._templates:
            return []

        topic_lower = topic_text.lower()
        topic_words = set(re.findall(r'\w+', topic_lower))
        results = []

        for tmpl in self._templates:
            if not tmpl.keywords:
                continue

            matched = []
            for kw in tmpl.keywords:
                kw_lower = kw.lower()
                # Check both exact substring and word-level match
                if kw_lower in topic_lower:
                    matched.append(kw)
                else:
                    kw_words = set(re.findall(r'\w+', kw_lower))
                    if kw_words and kw_words.issubset(topic_words):
                        matched.append(kw)

            if matched:
                confidence = len(matched) / len(tmpl.keywords)
                results.append(MatchResult(
                    template=tmpl,
                    confidence=min(confidence, 1.0),
                    matched_keywords=matched,
                ))

        # Sort by confidence desc
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:top_n]

    # ── Parse Template ─────────────────────────────────────────

    def _parse_template(self, path: Path) -> Optional[WorkflowTemplate]:
        """Parse a .md file into a WorkflowTemplate."""
        content = load_text(path)

        # Try to extract YAML frontmatter
        fm_match = self._FM_PATTERN.match(content)

        if fm_match:
            fm_raw = fm_match.group(1)
            body = content[fm_match.end():]
            meta = self._parse_yaml_simple(fm_raw)

            tmpl = WorkflowTemplate(
                template_id=meta.get("template_id", ""),
                display_name=meta.get("display_name", path.stem),
                group=meta.get("group", "untagged"),
                keywords=meta.get("keywords", []),
                visual_style=meta.get("visual_style", ""),
                structure=meta.get("structure", ""),
                output_files=meta.get("output_files", []),
                shared_rules=meta.get("shared_rules", []),
                advanced_rules=meta.get("advanced_rules", []),
                body=body.strip(),
                source_path=path,
            )

            # Parse scene_count_range
            scr = meta.get("scene_count_range", [8, 12])
            if isinstance(scr, list) and len(scr) == 2:
                tmpl.scene_count_range = (int(scr[0]), int(scr[1]))

            return tmpl
        else:
            # No frontmatter — treat as untagged template
            return WorkflowTemplate(
                display_name=path.stem,
                group="untagged",
                body=content.strip(),
                source_path=path,
            )

    def _parse_yaml_simple(self, raw: str) -> Dict:
        """Simple YAML parser for frontmatter (no PyYAML dependency).

        Handles:
        - key: value
        - key: [item1, item2]
        - key: "quoted value"
        """
        result = {}
        for line in raw.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            # Remove quotes
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            # Parse list: [item1, item2, ...]
            if value.startswith("[") and value.endswith("]"):
                items = value[1:-1].split(",")
                result[key] = [
                    i.strip().strip('"').strip("'")
                    for i in items if i.strip()
                ]
            elif key in self._LIST_FIELDS and not value.startswith("["):
                # Single value → wrap in list
                result[key] = [value] if value else []
            elif key in self._RANGE_FIELDS:
                # Parse as list of ints
                try:
                    parts = value.strip("[]").split(",")
                    result[key] = [int(p.strip()) for p in parts]
                except ValueError:
                    result[key] = [8, 12]
            else:
                result[key] = value

        return result
