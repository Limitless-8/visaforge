"""
llm/openai_provider.py
----------------------
PLACEHOLDER provider. Not active in the MVP.

To activate later:
1. `pip install openai` (uncomment in requirements.txt)
2. Set OPENAI_API_KEY and LLM_PROVIDER=openai
3. Remove the NotImplementedError guards below.

The method signatures already match `LLMProvider`, so the factory
will pick it up with zero changes elsewhere.
"""

from __future__ import annotations

from typing import Sequence

from config.settings import settings
from llm.base import LLMProvider
from models.schemas import LLMMessage, LLMResponse


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        self._model = settings.OPENAI_MODEL
        self._api_key = settings.OPENAI_API_KEY

    def is_available(self) -> bool:
        return bool(self._api_key)

    def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        # --- Scaffolded implementation ---
        # from openai import OpenAI
        # client = OpenAI(api_key=self._api_key)
        # payload = [{"role": m.role, "content": m.content} for m in messages]
        # resp = client.chat.completions.create(
        #     model=self._model,
        #     messages=payload,
        #     temperature=temperature,
        #     max_tokens=max_tokens,
        # )
        # content = (resp.choices[0].message.content or "").strip()
        # usage = {}
        # if resp.usage:
        #     usage = {
        #         "prompt_tokens": resp.usage.prompt_tokens,
        #         "completion_tokens": resp.usage.completion_tokens,
        #         "total_tokens": resp.usage.total_tokens,
        #     }
        # return LLMResponse(
        #     content=content, provider=self.name,
        #     model=self._model, usage=usage,
        # )
        raise NotImplementedError(
            "OpenAIProvider is a placeholder for the MVP. "
            "Uncomment the scaffolded implementation to activate."
        )
