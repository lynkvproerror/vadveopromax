"""
VEO Pro Max - AI Client Factory

Creates the correct API client based on provider setting.
Google → GeminiClient, others → OpenAICompatClient.

Usage:
    from services.ai_client_factory import create_ai_client

    client = create_ai_client()  # Reads from Settings automatically
    text = await client.generate(prompt=..., system=..., api_key=..., model=...)
"""

import logging

log = logging.getLogger("veo.ai_factory")

# Providers that use OpenAI-compatible API format
_OPENAI_COMPAT_PROVIDERS = {"OpenAI", "Anthropic", "DeepSeek", "xAI", "Mistral", "OpenRouter"}

# Default base URLs per provider
_DEFAULT_BASE_URLS = {
    "Google": "https://generativelanguage.googleapis.com/v1beta",
    "OpenAI": "https://api.openai.com/v1",
    "Anthropic": "https://api.anthropic.com/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "xAI": "https://api.x.ai/v1",
    "Mistral": "https://api.mistral.ai/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
}


def create_ai_client(provider: str = "", base_url: str = ""):
    """Create the correct AI client based on provider.

    Args:
        provider: Provider name ("Google", "DeepSeek", etc.).
                  If empty, reads from Settings.
        base_url: Custom base URL. If empty, uses provider default.

    Returns:
        GeminiClient or OpenAICompatClient instance.
    """
    # Read from Settings if not specified
    if not provider:
        try:
            from config.settings import get_settings
            s = get_settings()
            provider = getattr(s, 'pb_ai_provider', 'Google')
            base_url = base_url or getattr(s, 'pb_ai_base_url', '') or ''
        except Exception:
            provider = "Google"

    if provider in _OPENAI_COMPAT_PROVIDERS:
        from services.openai_compat_client import OpenAICompatClient
        url = base_url or _DEFAULT_BASE_URLS.get(provider, "")
        log.debug(f"[AIFactory] Using OpenAI-compat client: {provider} → {url}")
        return OpenAICompatClient(base_url=url)
    else:
        # Google (default)
        from services.gemini_client import GeminiClient
        client = GeminiClient()
        if base_url:
            client.BASE = base_url
        log.debug(f"[AIFactory] Using Gemini client: {provider}")
        return client


# Module-level counter for fallback round-robin
_custom_key_index = 0


def get_ai_config():
    """Get full AI config from Settings.

    Returns:
        dict with keys: api_key, model, provider, base_url, source, custom_keys
    """
    global _custom_key_index
    from config.settings import get_settings
    s = get_settings()

    source = getattr(s, 'pb_ai_source', 'account')
    provider = getattr(s, 'pb_ai_provider', 'Google')
    model = getattr(s, 'pb_ai_model', 'gemini-2.5-flash')
    base_url = getattr(s, 'pb_ai_base_url', '') or ''

    api_key = ""
    keys = []
    if source == 'custom':
        keys = [k.strip() for k in getattr(s, 'pb_ai_custom_keys', []) if k.strip()]
        if keys:
            # Use KeyQuotaManager for smart selection (skip blocked keys)
            try:
                from services.key_quota_manager import get_quota_manager
                api_key = get_quota_manager().get_available_key(keys) or ""
            except Exception:
                pass
            # Fallback to simple round-robin if quota manager fails
            if not api_key:
                api_key = keys[_custom_key_index % len(keys)]
                _custom_key_index += 1
    else:
        # source='account': collect ALL profile-provisioned keys for rotation
        try:
            from services.gemini_key_manager import GeminiKeyManager
            mgr = GeminiKeyManager()
            all_profile_keys = mgr._load_all()
            for email_k, data in all_profile_keys.items():
                k = None
                if isinstance(data, dict):
                    k = mgr._decrypt(data.get("encrypted", ""))
                elif isinstance(data, str):
                    k = data
                if k and k.startswith("AIza") and k not in keys:
                    keys.append(k)
        except Exception:
            pass
        # Select best key from collected profile keys
        if keys and not api_key:
            try:
                from services.key_quota_manager import get_quota_manager
                api_key = get_quota_manager().get_available_key(keys) or ""
            except Exception:
                pass
            if not api_key:
                api_key = keys[_custom_key_index % len(keys)]
                _custom_key_index += 1

    return {
        "api_key": api_key,
        "model": model,
        "provider": provider,
        "base_url": base_url,
        "source": source,
        "custom_keys": keys,  # All keys for fallback rotation (account OR custom)
    }
