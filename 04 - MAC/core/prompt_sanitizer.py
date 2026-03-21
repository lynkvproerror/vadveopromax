"""
Prompt Sanitizer — Local auto-fix for policy-violating prompts.

Runs BEFORE Gemini API fallback. Loads rules from data/policy_fix_rules.json.
3 fix passes:
  1. Dangerous phrases — regex removal (e.g. "no deformed limbs")
  2. Trigger words — single word removal/replacement
  3. Dialogue stripping — remove quoted speech
  4. Quality tags — append positive reinforcement if fixes applied

Usage:
    from core.prompt_sanitizer import get_sanitizer
    sanitizer = get_sanitizer()
    fixed, changes = sanitizer.sanitize(prompt)
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

log = logging.getLogger("veo.sanitizer")

_RULES_FILE = Path(__file__).parent.parent / "data" / "policy_fix_rules.json"


class PromptSanitizer:
    """Local prompt sanitizer using rule-based pattern matching."""

    def __init__(self, rules_path: Optional[Path] = None):
        self._rules_path = rules_path or _RULES_FILE
        self._rules: dict = {}
        self._compiled_phrases: List[Tuple[re.Pattern, str, str]] = []
        self._compiled_triggers: List[Tuple[re.Pattern, str, str]] = []
        self._compiled_dialogue: List[re.Pattern] = []
        self._load_rules()

    def _load_rules(self):
        """Load and compile rules from JSON file."""
        try:
            if self._rules_path.exists():
                self._rules = json.loads(
                    self._rules_path.read_text(encoding="utf-8")
                )
                self._compile_patterns()
                phrase_count = len(self._compiled_phrases)
                trigger_count = len(self._compiled_triggers)
                log.info(
                    f"[Sanitizer] Loaded rules v{self._rules.get('version', '?')}: "
                    f"{phrase_count} phrases, {trigger_count} triggers"
                )
            else:
                log.warning(f"[Sanitizer] Rules file not found: {self._rules_path}")
        except Exception as e:
            log.error(f"[Sanitizer] Failed to load rules: {e}")

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        # Dangerous phrases (regex)
        for rule in self._rules.get("dangerous_phrases", []):
            try:
                pat = re.compile(rule["pattern"], re.IGNORECASE)
                repl = rule.get("replacement", "")
                note = rule.get("note", "")
                self._compiled_phrases.append((pat, repl, note))
            except re.error as e:
                log.warning(f"[Sanitizer] Bad phrase regex '{rule['pattern']}': {e}")

        # Trigger words (whole word match)
        for rule in self._rules.get("trigger_words", []):
            try:
                word = re.escape(rule["word"])
                # \b word boundary — only match standalone words
                pat = re.compile(rf"\b{word}\b", re.IGNORECASE)
                repl = rule.get("replacement", "")
                note = rule.get("note", "")
                self._compiled_triggers.append((pat, repl, note))
            except re.error as e:
                log.warning(f"[Sanitizer] Bad trigger word '{rule['word']}': {e}")

        # Dialogue strip patterns
        ds = self._rules.get("dialogue_strip", {})
        if ds.get("enabled", False):
            for pattern in ds.get("patterns", []):
                try:
                    self._compiled_dialogue.append(
                        re.compile(pattern, re.IGNORECASE)
                    )
                except re.error as e:
                    log.warning(f"[Sanitizer] Bad dialogue regex: {e}")

    def reload_rules(self):
        """Hot-reload rules from disk (e.g. after user edits JSON)."""
        self._compiled_phrases.clear()
        self._compiled_triggers.clear()
        self._compiled_dialogue.clear()
        self._load_rules()

    def sanitize(self, prompt: str) -> Tuple[str, List[str]]:
        """Sanitize a prompt by applying all fix passes.

        Args:
            prompt: Raw prompt text.

        Returns:
            (sanitized_prompt, list_of_changes_made)
            If no changes needed, returns (original_prompt, []).
        """
        if not prompt or not prompt.strip():
            return prompt, []

        changes: List[str] = []
        result = prompt

        # ── Pass 1: Dangerous phrases ──
        phrases_removed = 0
        for pat, repl, note in self._compiled_phrases:
            match = pat.search(result)
            if match:
                matched_text = match.group(0)
                result = pat.sub(repl, result)
                phrases_removed += 1
                changes.append(f"⛔ Removed phrase: '{matched_text}' ({note})")

        # ── Pass 2: Trigger words ──
        for pat, repl, note in self._compiled_triggers:
            match = pat.search(result)
            if match:
                matched_text = match.group(0)
                if repl:
                    result = pat.sub(repl, result)
                    changes.append(f"🔄 Replaced '{matched_text}' → '{repl}' ({note})")
                else:
                    result = pat.sub("", result)
                    changes.append(f"⛔ Removed word: '{matched_text}' ({note})")

        # ── Pass 3: Dialogue stripping ──
        ds = self._rules.get("dialogue_strip", {})
        if ds.get("enabled", False):
            for pat in self._compiled_dialogue:
                match = pat.search(result)
                if match:
                    matched_text = match.group(0)
                    tone = ds.get("default_tone", "a natural expression")
                    replacement = ds.get("replacement_template", "speaking with {tone}")
                    replacement = replacement.replace("{tone}", tone)
                    result = pat.sub(replacement, result)
                    changes.append(
                        f"💬 Stripped dialogue: '{matched_text[:60]}...' "
                        f"→ '{replacement}'"
                    )

        # ── Pass 4: Append quality tags ──
        qt = self._rules.get("quality_tags", {})
        if phrases_removed > 0 and qt.get("append_when") == "dangerous_phrases_removed":
            positive_tags = qt.get("positive", "")
            if positive_tags and positive_tags not in result:
                result = result.rstrip(". ") + ". " + positive_tags
                changes.append(f"✨ Added quality tags: '{positive_tags[:60]}...'")

        # ── Cleanup: fix artifacts from phrase removal ──
        if changes:
            # Basic punctuation cleanup
            result = re.sub(r"\s{2,}", " ", result)           # double spaces
            result = re.sub(r",\s*,", ",", result)            # double commas
            result = re.sub(r"(,\s*){2,}", ", ", result)      # triple+ commas
            result = re.sub(r",\s*\.", ".", result)            # comma before period
            result = re.sub(r"\.\s*\.", ".", result)           # double periods
            result = re.sub(r"\band\s+and\b", "and", result)  # double "and"
            
            # Remove orphaned connectors at sentence boundaries
            result = re.sub(r",\s*and\s*\.", ".", result)     # ", and."
            result = re.sub(r",\s*or\s*\.", ".", result)      # ", or."
            result = re.sub(r"\band\s+\.", ".", result)       # "and."
            result = re.sub(r",\s*and\s*,", ",", result)     # ", and ,"
            
            # Remove sentences that became nearly empty after stripping
            # Pattern: sentence starting with capital letter, having mostly filler words
            filler_words = (
                r"(?:the|a|an|and|or|but|is|are|was|were|has|have|had|"
                r"ensures?|with|that|this|no|not|any|all|also|very|"
                r"absolutely|completely|entirely|totally|really|"
                r"visual|fidelity|quality|moreover|furthermore)\b"
            )
            # Remove sentences that are ONLY filler words + punctuation
            result = re.sub(
                rf"(?<=[.!?])\s*(?:{filler_words}\s*[,]?\s*){{1,}}[.!?]",
                ".", result, flags=re.IGNORECASE
            )
            # Also handle at start of string
            result = re.sub(
                rf"^(?:{filler_words}\s*[,]?\s*){{1,}}[.!?]\s*",
                "", result, flags=re.IGNORECASE
            )
            
            # Final cleanup
            result = re.sub(r"\s{2,}", " ", result)
            result = re.sub(r"\.\s*\.", ".", result)
            result = result.strip(" ,.")
            # Re-add final period
            if result and not result.endswith("."):
                result += "."

        if changes:
            log.info(
                f"[Sanitizer] Applied {len(changes)} fixes to prompt "
                f"({len(prompt)} → {len(result)} chars)"
            )
            for c in changes:
                log.debug(f"[Sanitizer]   {c}")

        return result, changes

    def has_rules(self) -> bool:
        """Check if any rules are loaded."""
        return bool(self._compiled_phrases or self._compiled_triggers)


# ── Singleton ──

_instance: Optional[PromptSanitizer] = None


def get_sanitizer() -> PromptSanitizer:
    """Get the singleton PromptSanitizer instance."""
    global _instance
    if _instance is None:
        _instance = PromptSanitizer()
    return _instance
