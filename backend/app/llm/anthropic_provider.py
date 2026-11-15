"""Claude via the Anthropic Messages API, using the user's own API key.

Note: Anthropic only permits API keys (from console.anthropic.com) in
third-party apps. Claude Free/Pro/Max subscription logins are restricted to
Claude Code and Claude.ai, so this app never asks for them.
"""
from __future__ import annotations

import httpx

from .. import config
from .base import LLMError, LLMProvider

API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    @property
    def available(self) -> bool:
        return bool(self.settings.api_key)

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if not self.settings.api_key:
            raise LLMError("No Anthropic API key provided.")
        url = (self.settings.base_url.rstrip("/") + "/v1/messages") if self.settings.base_url else API_URL
        payload = {
            "model": self.settings.model or config.DEFAULT_ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=180)
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Anthropic API: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
