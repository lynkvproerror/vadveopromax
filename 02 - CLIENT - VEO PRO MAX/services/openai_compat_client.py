"""
VEO Pro Max - OpenAI-Compatible API Client

REST client for OpenAI-compatible APIs (DeepSeek, OpenAI, xAI, Mistral, OpenRouter).
Same generate() interface as GeminiClient for drop-in replacement.
"""

import logging
from typing import Optional

import aiohttp

from services.gemini_client import GeminiAPIError, RateLimitError, InvalidKeyError

log = logging.getLogger("veo.openai_compat")


class OpenAICompatClient:
    """Async REST client for OpenAI-compatible chat/completions API.

    Supports: OpenAI, DeepSeek, xAI (Grok), Mistral, OpenRouter.
    All share the same request/response format.

    Usage:
        client = OpenAICompatClient(base_url="https://api.deepseek.com/v1")
        text = await client.generate(
            prompt="Describe a sunset",
            system="You are a visual expert.",
            api_key="sk-...",
            model="deepseek-chat",
        )
    """

    DEFAULT_TIMEOUT = 60  # seconds (some providers are slower)

    # Provider base URLs for reference
    PROVIDER_URLS = {
        "OpenAI": "https://api.openai.com/v1",
        "DeepSeek": "https://api.deepseek.com/v1",
        "xAI": "https://api.x.ai/v1",
        "Mistral": "https://api.mistral.ai/v1",
        "OpenRouter": "https://openrouter.ai/api/v1",
    }

    def __init__(self, base_url: str = "https://api.openai.com/v1"):
        self.base_url = base_url.rstrip("/")

    # Re-export system prompts from GeminiClient for compatibility
    @property
    def ENHANCE_SYSTEM(self):
        from services.gemini_client import GeminiClient
        return GeminiClient.ENHANCE_SYSTEM

    @property
    def FIX_POLICY_SYSTEM(self):
        from services.gemini_client import GeminiClient
        return GeminiClient.FIX_POLICY_SYSTEM

    async def generate(
        self,
        prompt: str,
        system: str,
        api_key: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        timeout: int = DEFAULT_TIMEOUT,
        model: str = "",
    ) -> str:
        """Send a chat/completions request.

        Args:
            prompt: User prompt text.
            system: System instruction text.
            api_key: Provider API key.
            max_tokens: Max output tokens.
            temperature: Sampling temperature.
            timeout: Request timeout in seconds.
            model: Model name (e.g. "deepseek-chat", "gpt-4o").

        Returns:
            Generated text response.

        Raises:
            RateLimitError: HTTP 429.
            InvalidKeyError: HTTP 401/403.
            GeminiAPIError: Other HTTP errors.
        """
        if not model:
            raise GeminiAPIError(400, "Model name required for OpenAI-compatible API")

        url = f"{self.base_url}/chat/completions"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # OpenRouter requires extra headers
        if "openrouter" in self.base_url.lower():
            headers["HTTP-Referer"] = "https://veo-pro-max.app"
            headers["X-Title"] = "VEO Pro Max"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return self._extract_text(data)

                # Error handling
                error_body = ""
                try:
                    error_data = await resp.json()
                    error_body = (
                        error_data.get("error", {}).get("message", "")
                        or str(error_data)
                    )
                except Exception:
                    error_body = await resp.text()

                if resp.status == 429:
                    log.warning(f"[OpenAI] Rate limited: {error_body}")
                    raise RateLimitError(error_body)

                if resp.status in (401, 403):
                    log.error(f"[OpenAI] Invalid key: {error_body}")
                    raise InvalidKeyError(error_body)

                log.error(f"[OpenAI] API error {resp.status}: {error_body}")
                raise GeminiAPIError(resp.status, error_body)

    @staticmethod
    def _extract_text(data: dict) -> str:
        """Extract text from OpenAI chat/completions response.

        Response structure:
            choices[0].message.content
        """
        try:
            choices = data.get("choices", [])
            if not choices:
                raise GeminiAPIError(500, "No choices in response")

            message = choices[0].get("message", {})
            content = message.get("content", "")
            if not content:
                # Some providers use "text" instead
                content = choices[0].get("text", "")

            return content.strip()
        except (KeyError, IndexError, TypeError) as e:
            raise GeminiAPIError(500, f"Failed to parse response: {e}")

    async def test_key(self, api_key: str, model: str = "") -> bool:
        """Quick test if API key is valid."""
        try:
            result = await self.generate(
                prompt="Say 'OK'",
                system="Reply with exactly 'OK'.",
                api_key=api_key,
                max_tokens=8,
                temperature=0.0,
                timeout=10,
                model=model,
            )
            return bool(result)
        except InvalidKeyError:
            return False
        except Exception as e:
            log.debug(f"[OpenAI] Key test failed: {e}")
            return False
