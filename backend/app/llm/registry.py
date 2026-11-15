"""Pick an LLM provider for a request.

Priority:
  1. Settings the user sent with the request (bring-your-own-key).
  2. The server owner's provider from environment variables.
  3. None -> the pipeline falls back to signal-only (no LLM) ranking.

To add your own provider: subclass LLMProvider, then add it to PROVIDERS.
"""
from __future__ import annotations

from typing import Optional

from .. import config
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, LLMSettings
from .openai_compat import OpenAICompatProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai_compat": OpenAICompatProvider,
}


def server_settings() -> Optional[LLMSettings]:
    if config.SERVER_LLM_PROVIDER in PROVIDERS:
        return LLMSettings(
            provider=config.SERVER_LLM_PROVIDER,
            model=config.SERVER_LLM_MODEL,
            api_key=config.SERVER_LLM_API_KEY,
            base_url=config.SERVER_LLM_BASE_URL,
            source="server",
        )
    return None


def resolve(user: Optional[LLMSettings]) -> Optional[LLMProvider]:
    for settings in (user, server_settings()):
        if settings and settings.provider in PROVIDERS:
            provider = PROVIDERS[settings.provider](settings)
            if provider.available:
                return provider
    return None


def public_info() -> dict:
    s = server_settings()
    return {
        "providers": ["anthropic", "openai_compat", "none"],
        "server_provider": s.provider if s else None,
        "server_model": s.model if s else None,
        "default_anthropic_model": config.DEFAULT_ANTHROPIC_MODEL,
    }
