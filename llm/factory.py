"""
llm/factory.py
--------------
Factory for LLM providers. The rest of the app calls `get_llm_provider()`
and never instantiates a provider directly.

Supported values for settings.LLM_PROVIDER:
  - "groq"   : Groq (uses GROQ_API_KEY)
  - "xai"    : xAI Grok (uses XAI_API_KEY, OpenAI-compatible endpoint)
  - "openai" : OpenAI (placeholder; not activated in MVP)
  - "auto"   : autodetect based on which API key is present; prefers xAI
"""

from __future__ import annotations

from functools import lru_cache

from config.settings import settings
from llm.base import LLMProvider
from llm.groq_provider import (
    GroqProvider,
    XAIProvider,
    resolve_auto_provider,
)
from llm.openai_provider import OpenAIProvider
from utils.logger import get_logger

log = get_logger(__name__)


_REGISTRY: dict[str, type[LLMProvider]] = {
    "groq": GroqProvider,
    "xai": XAIProvider,
    "openai": OpenAIProvider,
}


@lru_cache(maxsize=4)
def get_llm_provider(name: str | None = None) -> LLMProvider:
    key = (name or settings.LLM_PROVIDER).lower()

    if key == "auto":
        provider = resolve_auto_provider()
        log.info(
            "LLM provider (auto) resolved: %s (available=%s)",
            provider.name, provider.is_available(),
        )
        return provider

    cls = _REGISTRY.get(key)
    if cls is None:
        log.warning(
            "Unknown LLM provider '%s'; falling back to auto-detect.", key
        )
        provider = resolve_auto_provider()
    else:
        provider = cls()

    log.info(
        "LLM provider resolved: %s (available=%s)",
        provider.name, provider.is_available(),
    )
    return provider
