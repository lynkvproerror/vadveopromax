"""
VEO Pro Max - Gemini API Client

REST client for Google Gemini/Gemma API (generativelanguage.googleapis.com).
Used by PromptEnhancer (Phase 3) and ProjectBuilder (Phase 6).
"""

import logging
from typing import Optional

import aiohttp

log = logging.getLogger("veo.gemini")


# ── Custom Exceptions ──────────────────────────────────────────────


class GeminiAPIError(Exception):
    """Base Gemini API error."""

    def __init__(self, status: int, message: str = ""):
        self.status = status
        super().__init__(f"Gemini API error {status}: {message}")


class RateLimitError(GeminiAPIError):
    """HTTP 429 — quota exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(429, message)


class InvalidKeyError(GeminiAPIError):
    """HTTP 401/403 — invalid or revoked API key."""

    def __init__(self, message: str = "Invalid API key"):
        super().__init__(403, message)


# ── GeminiClient ───────────────────────────────────────────────────


class GeminiClient:
    """Async REST client for Gemini 2.0 Flash generateContent API.

    Usage:
        client = GeminiClient()
        text = await client.generate(
            prompt="Describe a sunset",
            system="You are a visual expert.",
            api_key="AIza...",
        )
    """

    BASE = "https://generativelanguage.googleapis.com/v1beta"
    MODEL = "models/gemma-3-27b-it"  # Default (14,400 RPD free tier)
    MODEL_FLASH = "models/gemini-2.5-flash"  # Fallback
    MODEL_PRO = "models/gemini-2.5-pro"  # Highest quality (paid)
    DEFAULT_TIMEOUT = 30  # seconds
    
    # Model alias registry
    _MODEL_ALIASES = {
        "flash": "models/gemini-2.5-flash",
        "pro": "models/gemini-2.5-pro",
        "flash-lite": "models/gemini-2.5-flash-lite",
        "gemma-27b": "models/gemma-3-27b-it",
        "gemma-4": "models/gemma-4-31b-it",
    }

    # ── System Prompts (class-level constants) ─────────────────────

    ENHANCE_SYSTEM = (
        "You are a video prompt optimizer for Google VEO AI video generation.\n\n"
        "ABSOLUTE RULES (violation = failure):\n"
        "1. OUTPUT LENGTH: Your output MUST be AT LEAST as long as the input. "
        "If the input has 500 characters, your output must have ≥500 characters. "
        "NEVER truncate, abbreviate, or stop mid-sentence.\n"
        "2. PRESERVE EVERYTHING: Keep ALL SEG segments (SEG1, SEG2, SEG3, etc), "
        "ALL >> separators, ALL [CharacterName] blocks with FULL descriptions, "
        "ALL quoted dialogue, ALL camera directions, ALL audio notes.\n"
        "3. COUNT: If input has N segments, output MUST have exactly N segments.\n"
        "4. LANGUAGE: ALL character dialogue MUST stay in its original language. "
        "Do NOT translate dialogue. If a character speaks Japanese, keep Japanese. "
        "If Vietnamese, keep Vietnamese. If English, keep English.\n"
        "5. ENHANCE by adding richer visual adjectives, lighting details, "
        "camera movements, color grading, texture descriptions.\n"
        "6. DO NOT remove any segment, character description, or dialogue line.\n"
        "7. DO NOT add policy-violating content.\n"
        "8. DIALOGUE RULE: First, detect whether the input contains character dialogue "
        "(quoted speech like \"...\", voice/audio notes like (Giọng:...), "
        "or any text describing what a character says). "
        "If YES → keep ALL dialogue EXACTLY as-is, word for word, in its original language. "
        "If NO → absolutely do NOT invent or add any dialogue, quoted speech, "
        "voice notes, or audio descriptions. Only enhance visual elements.\n\n"
        "Output the COMPLETE enhanced prompt. No explanations. "
        "You MUST output the entire prompt from start to end."
    )

    FIX_POLICY_SYSTEM = (
        "VEO prompt blocked: {error}\n\n"
        "SCAN for these triggers, then fix ONLY flagged words:\n\n"
        "CAT1 MINORS: child/kid/teen/teenager/young girl/boy, trẻ em/thiếu niên/học sinh, "
        "any age <18 → change to adult (20+, young woman/man, cô gái trẻ/thanh niên)\n"
        "CAT2 VIOLENCE: blood/gore/stab/kill/murder/torture, máu/giết/chém/tra tấn "
        "→ euphemisms (conflict, dramatic confrontation)\n"
        "CAT3 WEAPONS: gun/rifle/sword/knife/bomb, súng/dao/kiếm/bom "
        "→ remove or neutral (tool, device)\n"
        "CAT4 SEXUAL: nude/naked/sexy/erotic/lingerie/revealing, khỏa thân/gợi cảm "
        "→ modest (elegant dress, trang phục lịch sự)\n"
        "CAT5 SELF-HARM: suicide/self-harm/tự tử → remove entirely\n"
        "CAT6 DRUGS: drug/cocaine/heroin/meth, ma túy → remove\n"
        "CAT7 HATE: slurs/stereotypes → remove\n"
        "CAT8 DANGEROUS: arson/poison/kidnap/strangle, đốt/bắt cóc/đầu độc "
        "→ safe alternatives\n\n"
        "CAT9 COMBO TRAPS (not individual, but combined = trigger):\n"
        "  minor + private space (bathroom/bedroom) + body-fitting clothes → "
        "change age to 20+ OR location to public space OR clothes to modest\n"
        "CAT10 NEGATIVE PROMPTING:\n"
        "  'no dandruff' → AI generates dandruff. 'hết gàu/hết mụn/no acne' → "
        "use positive: 'flawless shiny hair', 'tóc sạch bóng mượt', 'da mịn rạng rỡ'\n"
        "CAT11 DIALOGUE PRESERVATION:\n"
        "  If the input contains character dialogue (quoted speech, voice notes), "
        "keep ALL dialogue EXACTLY as-is in its original language. Do NOT remove, "
        "translate, or modify dialogue. Do NOT add new dialogue if none exists.\n"
        "CAT12 NOISY DETAILS:\n"
        "  Remove height (1.50m). Simplify stacked colors: "
        "'vivid hot pink bright fuchsia' → 'vivid fuchsia'\n\n"
        "RULES: Same length as input. Copy everything, change ONLY flagged words. "
        "Preserve ALL SEG/>> separators/[Character] blocks/camera directions. "
        "Vietnamese stays Vietnamese. Minimal changes. "
        "Output COMPLETE fixed prompt, no explanations."
    )

    # ── Core Method ────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system: str,
        api_key: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        timeout: int = DEFAULT_TIMEOUT,
        model: str = "flash",
    ) -> str:
        """Send a generateContent request to Gemini API.

        Args:
            prompt: User prompt text.
            system: System instruction text.
            api_key: Gemini API key (AIza...).
            max_tokens: Max output tokens (512 for enhance, 8192 for project builder).
            temperature: Sampling temperature.
            timeout: Request timeout in seconds.
            model: 'flash' (default), 'pro', or full model path.

        Returns:
            Generated text response.

        Raises:
            RateLimitError: HTTP 429.
            InvalidKeyError: HTTP 401/403.
            GeminiAPIError: Other HTTP errors.
        """
        # Resolve model alias → full path
        model_path = self._MODEL_ALIASES.get(model, model)
        if not model_path.startswith("models/"):
            model_path = f"models/{model_path}"
        
        url = f"{self.BASE}/{model_path}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                params={"key": api_key},
                json=body,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._extract_text(data)

                # Error handling
                error_body = ""
                try:
                    error_data = await resp.json()
                    error_body = error_data.get("error", {}).get("message", "")
                except Exception:
                    error_body = await resp.text()

                if resp.status == 429:
                    log.warning(f"[Gemini] Rate limited: {error_body}")
                    raise RateLimitError(error_body)

                if resp.status in (401, 403):
                    log.error(f"[Gemini] Invalid key: {error_body}")
                    raise InvalidKeyError(error_body)

                log.error(f"[Gemini] API error {resp.status}: {error_body}")
                raise GeminiAPIError(resp.status, error_body)

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(data: dict) -> str:
        """Extract text from Gemini API response.

        Response structure:
            candidates[0].content.parts[0].text
        """
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                # Check for prompt feedback (blocked)
                feedback = data.get("promptFeedback", {})
                block_reason = feedback.get("blockReason", "")
                if block_reason:
                    raise GeminiAPIError(400, f"Prompt blocked: {block_reason}")
                raise GeminiAPIError(500, "No candidates in response")

            # Check output-level safety/policy block
            finish_reason = candidates[0].get("finishReason", "")
            if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                raise GeminiAPIError(400, f"Output blocked: finishReason={finish_reason}")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                raise GeminiAPIError(500, "No parts in candidate")

            text = parts[0].get("text", "").strip()

            # Warn if output was truncated (MAX_TOKENS)
            if finish_reason == "MAX_TOKENS" and text:
                log.warning(
                    f"[Gemini] Output truncated (MAX_TOKENS): "
                    f"{len(text)} chars returned. Result may be incomplete."
                )

            return text
        except (KeyError, IndexError, TypeError) as e:
            raise GeminiAPIError(500, f"Failed to parse response: {e}")

    async def test_key(self, api_key: str) -> bool:
        """Quick test if API key is valid.

        Returns True if key works, False otherwise.
        """
        try:
            result = await self.generate(
                prompt="Say 'OK'",
                system="Reply with exactly 'OK'.",
                api_key=api_key,
                max_tokens=8,
                temperature=0.0,
                timeout=10,
            )
            return bool(result)
        except InvalidKeyError:
            return False
        except Exception as e:
            log.debug(f"[Gemini] Key test failed: {e}")
            return False
