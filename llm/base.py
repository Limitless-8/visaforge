"""
llm/base.py
-----------
Abstract interface all LLM providers must implement.

Keeping this thin lets us swap Groq <-> OpenAI <-> anything else
by changing config only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from models.schemas import LLMMessage, LLMResponse


class LLMProvider(ABC):
    """Contract for any LLM provider used by VisaForge."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if provider has a usable API key/config."""

    @abstractmethod
    def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        """Run a chat completion and return a structured response."""
