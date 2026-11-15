"""The LLM provider contract.

Every provider only has to turn (system, user) text into a text reply. All
prompting, JSON parsing and validation lives in pipeline/moments.py, so adding
a new model (your own fine-tune, a local Ollama model, another vendor) means
writing one small class and registering it in registry.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(RuntimeError):
    pass


@dataclass
class LLMSettings:
    provider: str                 # "anthropic" | "openai_compat" | "none"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    source: str = "user"          # "user" (bring-your-own) or "server" (owner config)


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    @property
    def available(self) -> bool:
        return True

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 4000) -> str:
        """Return the model's text reply."""

    def describe(self) -> str:
        return f"{self.name}:{self.settings.model or 'default'} ({self.settings.source})"
