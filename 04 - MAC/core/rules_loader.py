"""
VEO Pro Max - Rules Loader

Loads rule files referenced by workflow templates.
Manages token budget for Gemini API context window (max ~900k tokens).
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple

log = logging.getLogger("veo.rules")

# Approximate token ratio: 1 token ≈ 4 chars (for English/Vietnamese mixed)
CHARS_PER_TOKEN = 4
MAX_CONTEXT_TOKENS = 900_000  # Gemini 2.0 Flash = 1M, leave 100k headroom


class RulesLoader:
    """Index and load rule .md files for workflow templates."""

    def __init__(self):
        self._index: Dict[str, Path] = {}  # filename → full path
        self._cache: Dict[str, str] = {}   # filename → content

    def index_sources(self, dirs: List[str]) -> int:
        """Index all .md files in given directories.

        Args:
            dirs: List of directory paths containing rule files.

        Returns:
            Number of rule files indexed.
        """
        self._index.clear()
        self._cache.clear()

        for dir_path in dirs:
            p = Path(dir_path)
            if not p.exists() or not p.is_dir():
                continue
            for md_file in sorted(p.rglob("*.md")):
                name = md_file.name
                if name not in self._index:
                    self._index[name] = md_file

        log.info(f"[Rules] Indexed {len(self._index)} rule files")
        return len(self._index)

    def load_for_template(
        self,
        shared_rules: List[str],
        advanced_rules: List[str],
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> Tuple[str, Dict[str, str]]:
        """Load rule files for a template, respecting token budget.

        Priority: shared_rules first (always load), advanced_rules truncated if over budget.

        Args:
            shared_rules: List of required rule filenames.
            advanced_rules: List of optional rule filenames.
            max_tokens: Maximum token budget.

        Returns:
            Tuple of (combined_text, loaded_files_dict).
        """
        loaded = {}
        total_chars = 0
        max_chars = max_tokens * CHARS_PER_TOKEN

        # Load shared rules (mandatory)
        for name in shared_rules:
            content = self._load_file(name)
            if content:
                loaded[name] = content
                total_chars += len(content)

        # Load advanced rules (optional, budget-limited)
        for name in advanced_rules:
            content = self._load_file(name)
            if content:
                if total_chars + len(content) > max_chars:
                    log.warning(
                        f"[Rules] Truncating: {name} would exceed "
                        f"{max_tokens} token budget"
                    )
                    break
                loaded[name] = content
                total_chars += len(content)

        # Combine all loaded rules
        combined = "\n\n".join(
            f"# === {name} ===\n{content}"
            for name, content in loaded.items()
        )

        tokens_used = total_chars // CHARS_PER_TOKEN
        log.info(
            f"[Rules] Loaded {len(loaded)} files, "
            f"~{tokens_used:,} tokens ({total_chars:,} chars)"
        )

        return combined, loaded

    def load_research_data(self, research_dir: str) -> Dict[str, str]:
        """Load research data files from a directory.

        Looks for files like:
        - Trending_Keywords.txt
        - Sensitive_Words.txt

        Args:
            research_dir: Path to research data directory.

        Returns:
            Dict of filename → content.
        """
        result = {}
        p = Path(research_dir)
        if not p.exists():
            return result

        for f in p.iterdir():
            if f.is_file() and f.suffix in (".txt", ".md"):
                try:
                    result[f.name] = f.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    log.warning(f"[Rules] Failed to read {f}: {e}")

        return result

    def get_available_rules(self) -> List[str]:
        """List all indexed rule filenames."""
        return sorted(self._index.keys())

    def _load_file(self, name: str) -> Optional[str]:
        """Load a single rule file by name."""
        # Check cache first
        if name in self._cache:
            return self._cache[name]

        path = self._index.get(name)
        if not path or not path.exists():
            log.debug(f"[Rules] Not found: {name}")
            return None

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            self._cache[name] = content
            return content
        except Exception as e:
            log.warning(f"[Rules] Failed to read {name}: {e}")
            return None
