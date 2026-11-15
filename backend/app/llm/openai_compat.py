"""Any OpenAI-compatible chat endpoint.

This is the "my own LLM" slot. It covers:
  * Ollama           LLM_BASE_URL=http://localhost:11434/v1   LLM_MODEL=qwen3:8b
  * vLLM / SGLang    LLM_BASE_URL=http://my-gpu-box:8000/v1    LLM_MODEL=my-finetune
  * LM Studio        LLM_BASE_URL=http://localhost:1234/v1
  * OpenRouter, Together, Groq, OpenAI, etc.
"""
from __future__ import annotations

import httpx

from .base import LLMError, LLMProvider


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    @property
    def available(self) -> bool:
        return bool(self.settings.base_url and self.settings.model)

    def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if not self.available:
            raise LLMError("OpenAI-compatible provider needs a base URL and a model name.")
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        headers = {"content-type": "application/json"}
        if self.settings.api_key:
            headers["authorization"] = f"Bearer {self.settings.api_key}"
        payload = {
            "model": self.settings.model,
            "max_tokens": max_tokens,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=300)
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach {url}: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"LLM endpoint error {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response shape: {str(data)[:300]}") from exc
