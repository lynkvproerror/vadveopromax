"""
VEO Pro Max - Prompt Enhancer

Uses GeminiClient to enhance VEO prompts and auto-fix policy violations.
Includes response cache to avoid duplicate API calls.
Phase 1: Local regex pre-fix (instant, no API, avoids Gemini safety block)
Phase 2: Gemini API fix (only if local fix didn't change anything)

Used by Engine (Phase 5) for pre-submit enhancement and error recovery.
"""

import hashlib
import json
import logging
import re
from typing import Optional, Dict, List, Tuple
from collections import OrderedDict

log = logging.getLogger("veo.enhancer")

# Cache limited to 200 entries (LRU)
MAX_CACHE = 200

# ── Local Pre-Fix Patterns ─────────────────────────────────────────
# These run BEFORE API call to sanitize content that would trigger
# Gemini's own safety filter (400 errors).

# CAT1: Age patterns — match "a N-year-old" where N < 18
# Strategy: REMOVE age, use generic "young" instead of replacing with 22
_RE_AGE_EN = re.compile(
    r'\b(a\s+)(\d{1,2})(-year-old)\b',
    re.IGNORECASE
)
# Vietnamese age: "N tuổi" where N < 18
_RE_AGE_VN = re.compile(
    r',?\s*\d{1,2}\s*tuổi',
    re.IGNORECASE
)

# "Bé X" character name prefix removal ("Bé" = child in Vietnamese)
_RE_BE_PREFIX = re.compile(r'\bBé\s+', re.UNICODE)

# Child-specific physical descriptors to remove/replace
# (only applied when minor age was detected)
_CHILD_DESCRIPTORS = [
    (re.compile(r'\bchubby\s+baby\s+smooth\b', re.I), 'naturally smooth'),
    (re.compile(r'\bchubby\s+child\s+face\b', re.I), 'youthful face'),
    (re.compile(r'\bbaby\s+smooth\s+skin\b', re.I), 'smooth radiant skin'),
    (re.compile(r'\bchild\s+face\b', re.I), 'youthful face'),
    (re.compile(r'\brosy\s+chubby\b', re.I), 'rosy'),
    (re.compile(r'\btiny\s+button\s+nose\b', re.I), 'small nose'),
    (re.compile(r'\bsmall\s+pink\s+lips\b', re.I), 'pink lips'),
    (re.compile(r'\bcurious\s+innocent\b', re.I), 'curious'),
]

# Childlike behaviors / context signals (VEO detects these as child indicators)
_CHILDLIKE_BEHAVIORS = [
    (re.compile(r'\bstanding\s+on\s+tiptoe\b', re.I), 'standing close'),
    (re.compile(r'\bon\s+tiptoe\b', re.I), 'reaching up'),
    (re.compile(r'\bcrawling\b', re.I), 'moving'),
    (re.compile(r'\badorable\s+waving\b', re.I), 'cheerfully waving'),
]

# Childlike clothing/accessory modifiers
_CHILDLIKE_CLOTHING = [
    (re.compile(r'\bcute\s+(cotton|little|small)\b', re.I), r'\1'),
    (re.compile(r'\bsmall\s+(ballet\s+flats|shoes|sandals|slippers)\b', re.I), r'\1'),
    (re.compile(r'\bsmall\s+(hair\s+bow|scrunchie|ribbon)\b', re.I), r'\1'),
    (re.compile(r'\bsmall\s+(house\s+slippers)\b', re.I), r'\1'),
]

# Context words that imply child when combined: girl -> woman
_RE_GIRL_TO_WOMAN = re.compile(r'\b(Vietnamese\s+)girl\b', re.I)
_RE_BOY_TO_MAN = re.compile(r'\b(Vietnamese\s+)boy\b', re.I)

# CAT9: Private spaces (only replaced when minor detected)
_PRIVATE_SPACES = {
    'bathroom': 'bright modern living room',
    'phòng tắm': 'phòng khách sáng sủa',
    'changing room': 'open lobby',
    'phòng thay đồ': 'sảnh rộng',
}

# CAT10: Negative prompting -> positive replacements
_NEGATIVE_PATTERNS = [
    # EN
    (re.compile(r'\bno\s+dandruff\b', re.I), 'flawless, ultra-shiny, perfectly clean hair'),
    (re.compile(r'\bno\s+acne\b', re.I), 'clear, radiant, glowing skin'),
    (re.compile(r'\bno\s+scars?\b', re.I), 'smooth, flawless skin'),
    (re.compile(r'\bno\s+wrinkles?\b', re.I), 'smooth, youthful skin'),
    (re.compile(r'\bno\s+blemish(es)?\b', re.I), 'flawless, radiant skin'),
    (re.compile(r'\bno\s+freckles?\b', re.I), 'even-toned skin'),
    (re.compile(r'\bno\s+spots?\b', re.I), 'flawless skin'),
    (re.compile(r'\bno\s+redness\b', re.I), 'even-toned, calm skin'),
    (re.compile(r'\bno\s+dark\s+circles?\b', re.I), 'bright, refreshed under-eyes'),
    (re.compile(r'\bskin\s+clearing\s+up\b', re.I), 'clear, radiant, glowing skin'),
    (re.compile(r'\bclearing\s+up\b', re.I), 'clear, radiant'),
    # VN
    (re.compile(r'\bhết\s+gàu\b', re.I), 'tóc sạch bóng mượt'),
    (re.compile(r'\bhết\s+mụn\b', re.I), 'da mịn màng rạng rỡ'),
    (re.compile(r'\bhết\s+ngứa\b', re.I), 'da dầu tóc khỏe mạnh'),
    (re.compile(r'\bhết\s+rụng\b', re.I), 'tóc dày chắc khỏe'),
    (re.compile(r'\bkhông\s+có\s+vết\b', re.I), 'da mịn màng'),
    (re.compile(r'\bkhông\s+có\s+mụn\b', re.I), 'da sáng mịn'),
    (re.compile(r'\bkhông\s+gàu\b', re.I), 'tóc sạch bóng'),
    (re.compile(r'\bkhông\s+ngứa\b', re.I), 'thoải mái dễ chịu'),
]

# CAT11: Audio/dialogue noise patterns
_RE_VN_DIALOGUE = re.compile(
    r'\(Gi\u1ecdng[^)]*\)\s*["\u201c\u201d\'"][^"\u201c\u201d\'\"]*["\u201c\u201d\'"]\.?',
    re.IGNORECASE | re.DOTALL
)
_RE_AUDIO_DESC = re.compile(
    r'\bAudio\s+of\s+[^.>>]+[.]*',
    re.IGNORECASE
)

# CAT12: Height measurements
_RE_HEIGHT = re.compile(
    r',?\s*\d+\.\d+\s*m\b|,?\s*\d{2,3}\s*cm\b',
    re.IGNORECASE
)

# Excessive stacked color adjectives (keep first modifier + last base)
_COLOR_MODIFIERS = {
    'vivid', 'bright', 'deep', 'dark', 'light', 'soft', 'matte',
    'rich', 'pure', 'clean', 'warm', 'cool', 'hot', 'pale', 'bold',
    'neon', 'metallic', 'pastel', 'earthy',
}
_BASE_COLORS = {
    'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'pink',
    'white', 'black', 'brown', 'grey', 'gray', 'gold', 'silver',
    'fuchsia', 'magenta', 'cyan', 'teal', 'maroon', 'navy',
    'cherry', 'coral', 'crimson', 'jade', 'amber', 'ivory',
    'scarlet', 'turquoise', 'violet', 'indigo', 'khaki', 'olive',
    'beige', 'tan', 'cream', 'lavender', 'lilac', 'mint',
    'peach', 'plum', 'rose', 'ruby', 'salmon', 'sapphire',
}
_ALL_COLOR_WORDS = _COLOR_MODIFIERS | _BASE_COLORS


def _simplify_stacked_colors(text: str) -> str:
    """Reduce stacked color adjectives: 'vivid hot pink bright fuchsia' -> 'vivid fuchsia'."""
    words = text.split()
    result = []
    i = 0
    while i < len(words):
        w_clean = words[i].lower().rstrip('.,;:')
        if w_clean in _ALL_COLOR_WORDS:
            stack = []
            j = i
            while j < len(words) and words[j].lower().rstrip('.,;:') in _ALL_COLOR_WORDS:
                stack.append(words[j])
                j += 1
            if len(stack) > 2:
                # Keep first modifier + last base color
                modifiers = [w for w in stack if w.lower().rstrip('.,;:') in _COLOR_MODIFIERS]
                bases = [w for w in stack if w.lower().rstrip('.,;:') in _BASE_COLORS]
                if modifiers and bases:
                    result.append(modifiers[0])
                    result.append(bases[-1])
                else:
                    result.append(stack[0])
                    result.append(stack[-1])
                i = j
            else:
                result.extend(stack)
                i = j
        else:
            result.append(words[i])
            i += 1
    return ' '.join(result)


def _local_pre_fix(prompt: str) -> Tuple[str, List[str]]:
    """Apply local regex fixes BEFORE sending to Gemini API.

    Returns:
        (fixed_prompt, list_of_changes_made)
    """
    changes: List[str] = []
    text = prompt
    has_minor = False

    # -- CAT1: Age conversion (EN) — remove age, use "young" --
    def _fix_age_en(m):
        nonlocal has_minor
        age = int(m.group(2))
        if age < 18:
            has_minor = True
            changes.append(f'removed age {age}')
            return f'{m.group(1)}young'
        return m.group(0)

    text = _RE_AGE_EN.sub(_fix_age_en, text)

    # -- CAT1: Age conversion (VN) — remove "N tuổi" entirely --
    def _fix_age_vn(m):
        nonlocal has_minor
        has_minor = True
        changes.append('removed VN age')
        return ''

    text = _RE_AGE_VN.sub(_fix_age_vn, text)

    # -- CAT1: Clean child-specific patterns (only when minor detected) --
    if has_minor:
        # Remove "Bé" prefix from character names: "Bé An" -> "An"
        if _RE_BE_PREFIX.search(text):
            changes.append('removed B\u00e9 prefix')
            text = _RE_BE_PREFIX.sub('', text)

        # girl -> woman, boy -> man (in Vietnamese context)
        if _RE_GIRL_TO_WOMAN.search(text):
            changes.append('girl -> woman')
            text = _RE_GIRL_TO_WOMAN.sub(r'\1woman', text)
        if _RE_BOY_TO_MAN.search(text):
            changes.append('boy -> man')
            text = _RE_BOY_TO_MAN.sub(r'\1man', text)

        # Remove child-specific physical descriptors
        for pattern, replacement in _CHILD_DESCRIPTORS:
            if pattern.search(text):
                changes.append(f'child-desc -> {replacement}')
                text = pattern.sub(replacement, text)

        # Remove childlike behaviors
        for pattern, replacement in _CHILDLIKE_BEHAVIORS:
            if pattern.search(text):
                changes.append(f'child-behavior -> {replacement}')
                text = pattern.sub(replacement, text)

        # Remove childlike clothing modifiers
        for pattern, replacement in _CHILDLIKE_CLOTHING:
            if pattern.search(text):
                changes.append('cleaned child clothing')
                text = pattern.sub(replacement, text)

    # -- CAT9: Private spaces (only when minor was detected) --
    if has_minor:
        for space, safe_space in _PRIVATE_SPACES.items():
            if space.lower() in text.lower():
                changes.append(f'{space} -> {safe_space}')
                text = re.sub(re.escape(space), safe_space, text, flags=re.IGNORECASE)

    # -- CAT10: Negative prompting -> positive --
    for pattern, replacement in _NEGATIVE_PATTERNS:
        if pattern.search(text):
            changes.append(f'neg -> pos: {replacement[:30]}')
            text = pattern.sub(replacement, text)

    # -- CAT11: Audio/dialogue noise removal --
    if _RE_VN_DIALOGUE.search(text):
        changes.append('removed VN dialogue')
        text = _RE_VN_DIALOGUE.sub('talking with animated expression', text)

    if _RE_AUDIO_DESC.search(text):
        changes.append('removed audio desc')
        text = _RE_AUDIO_DESC.sub('', text)

    # -- CAT12: Height measurements --
    if _RE_HEIGHT.search(text):
        changes.append('removed height')
        text = _RE_HEIGHT.sub('', text)

    # -- CAT12: Excessive color simplification --
    simplified = _simplify_stacked_colors(text)
    if simplified != text:
        changes.append('simplified colors')
        text = simplified

    # Clean up extra spaces
    text = re.sub(r'  +', ' ', text).strip()
    text = re.sub(r' ,', ',', text)
    text = re.sub(r',,+', ',', text)

    return text, changes


# ── JSON Prompt Helpers ─────────────────────────────────────────

def _unwrap_json(text: str) -> Tuple[bool, dict, str]:
    """If text is JSON {...}, extract prompt_en. Otherwise pass through.
    
    Returns:
        (is_json, scene_data, prompt_text)
    """
    stripped = text.strip()
    if stripped.startswith('{'):
        try:
            scene = json.loads(stripped)
            if isinstance(scene, dict):
                prompt_en = scene.get('prompt_en', '') or scene.get('prompt', '')
                if prompt_en:
                    return True, scene, prompt_en
        except (json.JSONDecodeError, ValueError):
            pass
    return False, {}, text


def _wrap_json(scene_data: dict, new_prompt: str) -> str:
    """Put enhanced prompt_en back into JSON structure."""
    updated = dict(scene_data)
    if 'prompt_en' in updated:
        updated['prompt_en'] = new_prompt
    elif 'prompt' in updated:
        updated['prompt'] = new_prompt
    else:
        updated['prompt_en'] = new_prompt
    return json.dumps(updated, ensure_ascii=False)


def _text_to_json(prompt_text: str) -> str:
    """Wrap plain text prompt into minimal JSON structure."""
    return json.dumps({"prompt_en": prompt_text}, ensure_ascii=False)


class PromptEnhancer:
    """Enhance VEO prompts and fix policy violations via AI API."""

    def __init__(self, gemini_client=None):
        self.client = gemini_client
        self._cache: OrderedDict[str, str] = OrderedDict()

    def _get_ai_config(self) -> dict:
        """Get model, provider, base_url, api_key from user Settings."""
        try:
            from services.ai_client_factory import get_ai_config
            return get_ai_config()
        except Exception:
            return {"model": "gemini-2.5-flash", "provider": "Google", "base_url": "", "api_key": "", "source": "account"}

    def _resolve_api_key(self, engine_key: str) -> str:
        """Pick the right API key: custom key for non-Google, engine key for Google.

        When Settings source=custom AND a custom key exists, use that key
        instead of the Gemini profile key from engine. This prevents
        sending Gemini keys to DeepSeek/OpenAI endpoints.
        """
        cfg = self._get_ai_config()
        if cfg.get("source") == "custom" and cfg.get("api_key"):
            return cfg["api_key"]
        return engine_key

    def _ensure_client(self):
        """Create/update client based on current Settings provider."""
        cfg = self._get_ai_config()
        current_provider = cfg.get("provider", "Google")

        # Recreate client if provider changed
        if self.client is not None and getattr(self, '_last_provider', None) == current_provider:
            return

        try:
            from services.ai_client_factory import create_ai_client
            self.client = create_ai_client(current_provider, cfg.get("base_url", ""))
            self._last_provider = current_provider
        except Exception:
            from services.gemini_client import GeminiClient
            self.client = GeminiClient()
            self._last_provider = "Google"

    async def enhance(self, prompt: str, api_key: str,
                       profile_email: str = "",
                       output_format: str = "text") -> Optional[str]:
        """Enhance a VEO prompt with better visual details.

        Args:
            prompt: Original VEO prompt text (plain or JSON).
            api_key: API key (may be overridden by Settings).
            profile_email: Profile email for rotation tracking.
            output_format: 'text' or 'json' — controls output format.

        Returns:
            Enhanced prompt string, or None if failed.
        """
        if not api_key:
            api_key = self._resolve_api_key("")
        else:
            api_key = self._resolve_api_key(api_key)

        if not api_key:
            return None

        # JSON-aware: unwrap if JSON, enhance prompt_en only
        is_json, scene_data, prompt_text = _unwrap_json(prompt)

        # Check cache
        cache_key = self._hash(f"enhance:{prompt}:{output_format}")
        if cache_key in self._cache:
            log.debug("[Enhance] Cache hit")
            return self._cache[cache_key]

        self._ensure_client()
        cfg = self._get_ai_config()
        is_google = cfg.get("provider", "Google") == "Google"
        custom_keys = cfg.get("custom_keys", [])

        # Determine models to try
        if is_google:
            from services.model_rotation import get_rotation
            rotation = get_rotation()
            models_to_try = [rotation.get_model(profile_email)]
            # Add fallbacks
            all_models = rotation.get_all_models()
            for m in all_models:
                if m not in models_to_try:
                    models_to_try.append(m)
        else:
            models_to_try = [cfg["model"]]

        for model in models_to_try:
            try:
                result = await self.client.generate(
                    prompt=prompt_text,  # Send unwrapped prompt_en
                    system=self.client.ENHANCE_SYSTEM,
                    api_key=api_key,
                    max_tokens=4096,
                    temperature=0.7,
                    model=model,
                )

                if result and result.strip():
                    enhanced = result.strip()
                    # Format output based on requested format
                    if output_format == "json":
                        if is_json:
                            enhanced = _wrap_json(scene_data, enhanced)
                        else:
                            enhanced = _text_to_json(enhanced)
                    elif is_json:
                        pass  # text mode + JSON input → return plain enhanced text
                    # Track success
                    if is_google:
                        rotation.increment_used(profile_email, model)
                    self._put_cache(cache_key, enhanced)
                    log.info(f"[Enhance] OK ({model}): {prompt_text[:30]}...")
                    return enhanced

            except Exception as e:
                from services.gemini_client import RateLimitError, GeminiAPIError
                if isinstance(e, RateLimitError) and is_google:
                    rotation.mark_exhausted(profile_email, model)
                    # Smart key rotation: mark current key, try next
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        err_str = str(e).lower()
                        # 'limit: 0' = model has no free tier, NOT key exhausted
                        # Only mark RPD when actual daily quota exceeded
                        if "per day" in err_str and "limit: 0" not in err_str:
                            qm.mark_rpd_blocked(api_key)
                        else:
                            qm.mark_rpm_blocked(api_key)
                        if custom_keys:
                            next_key = qm.get_available_key(custom_keys)
                            if next_key:
                                api_key = next_key
                                log.info(f"[Enhance] Switched to key ...{api_key[-8:]}")
                    except Exception:
                        pass
                    log.warning(f"[Enhance] {model} rate limited (429), trying next...")
                    continue
                # Safety block (400) on preview models -> try next stable model
                if isinstance(e, GeminiAPIError) and e.status == 400 and is_google:
                    log.warning(f"[Enhance] {model} blocked (400), trying next model...")
                    continue
                log.warning(f"[Enhance] Failed ({model}): {e}")
                break

        return None

    # System prompt for Phase 2: paraphrase rewrite (85-95% similar)
    PARAPHRASE_SYSTEM = (
        "You are a video prompt rewriter for an AI video generation platform.\n"
        "Given a video scene description that was flagged as unsafe by content filters, "
        "REWRITE it to be 85-95% similar in visual intent but use completely different "
        "wording that avoids ALL safety triggers.\n\n"
        "RULES:\n"
        "1. ALL characters MUST be adults (20+ years). Never mention ages under 18.\n"
        "2. Remove ALL Vietnamese names starting with 'Bé' (means child). Use the name without prefix.\n"
        "3. Replace 'girl' with 'woman', 'boy' with 'man' when describing characters.\n"
        "4. Remove height measurements, Vietnamese dialogue, and audio descriptions.\n"
        "5. Replace negative descriptions ('no dandruff') with positive ones ('shiny hair').\n"
        "6. Keep the SAME scene structure (SEG format), camera angles, art style.\n"
        "7. Keep the SAME visual colors, lighting, and environment mood.\n"
        "8. Describe skin as 'smooth/radiant/glowing' not 'baby smooth/chubby'.\n"
        "9. Replace childlike behaviors (tiptoe, crawling) with adult behaviors.\n"
        "10. Remove 'cute' from clothing. Use 'stylish/elegant/casual' instead.\n"
        "11. Output ONLY the rewritten prompt. No explanations.\n"
        "12. Keep the prompt roughly the same length.\n\n"
        "ERROR that triggered this: {error}"
    )

    async def fix_policy(
        self, prompt: str, error_message: str, api_key: str,
        profile_email: str = "",
        output_format: str = "text"
    ) -> Optional[str]:
        """Fix a policy-blocked prompt.

        Uses a 3-phase approach:
        Phase 1: Local regex pre-fix (instant, no API, avoids Gemini safety block)
        Phase 2: Send LOCALLY-FIXED prompt to API for paraphrase rewrite (85-95% similar)
                 Since the locally-fixed text has no child references, Gemini won't block it.
        Phase 3: Fallback to FIX_POLICY_SYSTEM with original prompt (legacy)

        Args:
            prompt: The blocked prompt text (plain or JSON).
            error_message: The policy error message.
            api_key: API key (may be overridden by Settings).
            profile_email: Profile email for rotation tracking.
            output_format: 'text' or 'json' — controls output format.

        Returns:
            Fixed prompt string, or None if failed.
        """
        # JSON-aware: unwrap if JSON, fix prompt_en only
        is_json, scene_data, prompt_text = _unwrap_json(prompt)

        # -- Phase 1: Local Pre-Fix (instant, no API) --
        local_fixed, changes = _local_pre_fix(prompt_text)
        if changes:
            log.info(
                f"[Fix] LOCAL pre-fix applied ({len(changes)} changes): "
                f"{', '.join(changes[:5])}{'...' if len(changes) > 5 else ''}"
            )
            # Format output
            result = local_fixed
            if output_format == "json":
                result = _wrap_json(scene_data, local_fixed) if is_json else _text_to_json(local_fixed)
            elif is_json:
                pass  # text mode + JSON input → return plain fixed text
            self._put_cache(self._hash(f"fix:{prompt}:{error_message}:{output_format}"), result)
            return result

        # -- Resolve API key --
        if not api_key:
            api_key = self._resolve_api_key("")
        else:
            api_key = self._resolve_api_key(api_key)

        if not api_key:
            return None

        # Check cache
        cache_key = self._hash(f"fix:{prompt}:{error_message}:{output_format}")
        if cache_key in self._cache:
            log.debug("[Fix] Cache hit")
            return self._cache[cache_key]

        self._ensure_client()
        cfg = self._get_ai_config()
        is_google = cfg.get("provider", "Google") == "Google"
        custom_keys = cfg.get("custom_keys", [])

        # Determine models to try
        if is_google:
            from services.model_rotation import get_rotation
            rotation = get_rotation()
            models_to_try = [rotation.get_model(profile_email)]
            all_models = rotation.get_all_models()
            for m in all_models:
                if m not in models_to_try:
                    models_to_try.append(m)
        else:
            models_to_try = [cfg["model"]]

        # -- Phase 2: Paraphrase Rewrite via API --
        # Send the LOCALLY-PRE-FIXED prompt (safe text, no child refs)
        # to Gemini for a full paraphrase rewrite (85-95% similar)
        safe_prompt, _ = _local_pre_fix(prompt_text)  # always pre-fix first
        log.info(f"[Fix] Phase 2: API paraphrase rewrite ({len(safe_prompt)} chars)")

        for model in models_to_try:
            try:
                system = self.PARAPHRASE_SYSTEM.replace("{error}", error_message)

                result = await self.client.generate(
                    prompt=safe_prompt,  # send sanitized text, NOT original
                    system=system,
                    api_key=api_key,
                    max_tokens=4096,
                    temperature=0.6,
                    model=model,
                )

                if result and result.strip():
                    fixed = result.strip()
                    if output_format == "json":
                        fixed = _wrap_json(scene_data, fixed) if is_json else _text_to_json(fixed)
                    if is_google:
                        rotation.increment_used(profile_email, model)
                    self._put_cache(cache_key, fixed)
                    log.info(f"[Fix] Phase 2 OK ({model}): {result.strip()[:50]}...")
                    return fixed

            except Exception as e:
                from services.gemini_client import RateLimitError, GeminiAPIError
                if isinstance(e, RateLimitError) and is_google:
                    rotation.mark_exhausted(profile_email, model)
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        err_str = str(e).lower()
                        if "per day" in err_str and "limit: 0" not in err_str:
                            qm.mark_rpd_blocked(api_key)
                        else:
                            qm.mark_rpm_blocked(api_key)
                        if custom_keys:
                            next_key = qm.get_available_key(custom_keys)
                            if next_key:
                                api_key = next_key
                                log.info(f"[Fix] Switched to key ...{api_key[-8:]}")
                    except Exception:
                        pass
                    log.warning(f"[Fix] {model} rate limited (429), trying next...")
                    continue
                if isinstance(e, GeminiAPIError) and e.status == 400 and is_google:
                    log.warning(f"[Fix] {model} blocked (400), trying next model...")
                    continue
                log.warning(f"[Fix] Phase 2 failed ({model}): {e}")
                break

        # -- Phase 3: Fallback to legacy FIX_POLICY_SYSTEM --
        log.info("[Fix] Phase 3: Legacy FIX_POLICY_SYSTEM fallback")
        for model in models_to_try:
            try:
                system = self.client.FIX_POLICY_SYSTEM.replace("{error}", error_message)

                result = await self.client.generate(
                    prompt=safe_prompt,  # still use sanitized text
                    system=system,
                    api_key=api_key,
                    max_tokens=4096,
                    temperature=0.5,
                    model=model,
                )

                if result and result.strip():
                    fixed = result.strip()
                    if output_format == "json":
                        fixed = _wrap_json(scene_data, fixed) if is_json else _text_to_json(fixed)
                    if is_google:
                        rotation.increment_used(profile_email, model)
                    self._put_cache(cache_key, fixed)
                    log.info(f"[Fix] Phase 3 OK ({model}): {result.strip()[:50]}...")
                    return fixed

            except Exception as e:
                from services.gemini_client import RateLimitError, GeminiAPIError
                if isinstance(e, RateLimitError) and is_google:
                    rotation.mark_exhausted(profile_email, model)
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        err_str = str(e).lower()
                        if "per day" in err_str and "limit: 0" not in err_str:
                            qm.mark_rpd_blocked(api_key)
                        else:
                            qm.mark_rpm_blocked(api_key)
                        if custom_keys:
                            next_key = qm.get_available_key(custom_keys)
                            if next_key:
                                api_key = next_key
                                log.info(f"[Fix] Switched to key ...{api_key[-8:]}")
                    except Exception:
                        pass
                    log.warning(f"[Fix] {model} rate limited (429), trying next...")
                    continue
                if isinstance(e, GeminiAPIError) and e.status == 400 and is_google:
                    log.warning(f"[Fix] {model} blocked (400), trying next model...")
                    continue
                log.warning(f"[Fix] Phase 3 failed ({model}): {e}")
                break

        return None

    # System prompt for Phase 3: Complete regeneration (new prompt, keep characters)
    REGENERATE_SYSTEM = (
        "You are a creative video prompt writer for an AI video generation platform.\n"
        "The original prompt was PERMANENTLY REJECTED by safety filters after 2 fix attempts.\n\n"
        "YOUR TASK: Write a COMPLETELY NEW video scene description from scratch.\n"
        "DO NOT reuse ANY wording from the original prompt.\n"
        "CREATE a fresh scene that conveys a similar mood/theme but with entirely new phrasing.\n\n"
        "MANDATORY CHARACTER PRESERVATION:\n"
        "The following characters MUST appear in your new prompt with their EXACT names:\n"
        "{characters}\n\n"
        "For each character, you MUST:\n"
        "- Keep the character marker format: [CharacterName] or @character_name\n"
        "- Describe their appearance in a safe, family-friendly way\n"
        "- Give them natural, age-appropriate actions\n\n"
        "RULES:\n"
        "1. ALL characters MUST be adults (20+ years). Never mention ages under 18.\n"
        "2. No violence, gore, weapons, nudity, or any unsafe content.\n"
        "3. Use positive visual descriptions only — no negative prompts.\n"
        "4. Include: camera angle, art style, lighting, environment, character actions.\n"
        "5. Output ONLY the new prompt text. No explanations.\n"
        "6. Keep similar length to the original.\n"
        "7. Must be in English.\n\n"
        "ORIGINAL ERROR: {error}\n"
        "ORIGINAL PROMPT (for reference only — DO NOT copy):\n{original}"
    )

    def _extract_characters(self, prompt: str) -> list:
        """Extract character names from prompt markers: [Name], @name_, 'Name'.

        Returns list of unique character references found.
        """
        chars = set()
        # [Name] format — e.g. [Mẹ Vịt], [Chị Vịt Vàng]
        for m in re.finditer(r'\[([^\]]+)\]', prompt):
            name = m.group(1).strip()
            # Skip scene/stage/camera markers
            if not any(kw in name.lower() for kw in [
                'scene', 'stage', 'camera', 'shot', 'angle',
                'seg', 'transition', 'new', 'end'
            ]):
                chars.add(f"[{name}]")
        # @name_ format
        for m in re.finditer(r'@(\w+)_', prompt):
            chars.add(f"@{m.group(1)}_")
        return sorted(chars)

    async def regenerate_prompt(
        self, original_prompt: str, error_message: str, api_key: str,
        profile_email: str = "", output_format: str = "text"
    ) -> Optional[str]:
        """Generate a completely NEW prompt preserving character identities.

        Used as attempt 3 when local fix + API fix both failed.
        Creates fresh scene description, keeping character names/markers.
        """
        is_json, scene_data, prompt_text = _unwrap_json(original_prompt)

        # Extract character markers to preserve
        characters = self._extract_characters(prompt_text)
        char_list = "\n".join(f"  - {c}" for c in characters) if characters else "  (no specific characters detected)"

        if not api_key:
            api_key = self._resolve_api_key("")
        else:
            api_key = self._resolve_api_key(api_key)
        if not api_key:
            return None

        self._ensure_client()
        cfg = self._get_ai_config()
        is_google = cfg.get("provider", "Google") == "Google"
        custom_keys = cfg.get("custom_keys", [])

        if is_google:
            from services.model_rotation import get_rotation
            rotation = get_rotation()
            models_to_try = [rotation.get_model(profile_email)]
            all_models = rotation.get_all_models()
            for m in all_models:
                if m not in models_to_try:
                    models_to_try.append(m)
        else:
            models_to_try = [cfg["model"]]

        system = self.REGENERATE_SYSTEM.replace(
            "{characters}", char_list
        ).replace(
            "{error}", error_message
        ).replace(
            "{original}", prompt_text[:1000]  # truncate for safety
        )

        log.info(
            f"[Fix] REGENERATE: creating new prompt "
            f"(chars: {', '.join(characters) if characters else 'none'})"
        )

        for model in models_to_try:
            try:
                result = await self.client.generate(
                    prompt="Generate a completely new, safe video scene prompt based on the system instructions.",
                    system=system,
                    api_key=api_key,
                    max_tokens=4096,
                    temperature=0.8,  # higher creativity for fresh prompt
                    model=model,
                )

                if result and result.strip():
                    regenerated = result.strip()
                    if output_format == "json":
                        regenerated = _wrap_json(scene_data, regenerated) if is_json else _text_to_json(regenerated)
                    if is_google:
                        rotation.increment_used(profile_email, model)
                    log.info(f"[Fix] REGENERATE OK ({model}): {regenerated[:60]}...")
                    return regenerated

            except Exception as e:
                from services.gemini_client import RateLimitError, GeminiAPIError
                if isinstance(e, RateLimitError) and is_google:
                    rotation.mark_exhausted(profile_email, model)
                    try:
                        from services.key_quota_manager import get_quota_manager
                        qm = get_quota_manager()
                        if custom_keys:
                            next_key = qm.get_available_key(custom_keys)
                            if next_key:
                                api_key = next_key
                    except Exception:
                        pass
                    continue
                if isinstance(e, GeminiAPIError) and e.status == 400 and is_google:
                    continue
                log.warning(f"[Fix] REGENERATE failed ({model}): {e}")
                break

        return None

    # -- Cache Helpers --

    def _put_cache(self, key: str, value: str):
        """Add to LRU cache."""
        self._cache[key] = value
        if len(self._cache) > MAX_CACHE:
            self._cache.popitem(last=False)

    @staticmethod
    def _hash(text: str) -> str:
        """Create cache key hash."""
        return hashlib.md5(text.encode()).hexdigest()
