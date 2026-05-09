"""
llm/groq_provider.py
--------------------
Dual-mode chat provider supporting Groq AND xAI (Grok).

Both vendors expose OpenAI-compatible chat.completions APIs, so one
implementation — differing only in `base_url`, API key, and default
model — can serve both. Selection is driven by config:

  LLM_PROVIDER=groq   → uses GROQ_API_KEY at Groq's native SDK
  LLM_PROVIDER=xai    → uses XAI_API_KEY at https://api.x.ai/v1 via openai SDK
  LLM_PROVIDER=auto   → autodetect: prefers xAI if XAI_API_KEY set, else Groq

Public surface is unchanged:
  - class GroqProvider (kept for backward compat with llm/factory.py)
  - class XAIProvider (new)
  - class ChatProvider (shared base, exposed for future use)
  - .is_available()
  - .chat(messages, temperature, max_tokens) -> LLMResponse

Notes on Grok model names (as of April 2026):
  - `grok-2-latest` is legacy. Current recommended models are the
    `grok-4-1-fast-reasoning` / `grok-4-1-fast-non-reasoning` family
    and the `grok-4.20` flagship. The default here honors the spec
    (`grok-2-latest`) but is fully overridable via XAI_MODEL in env
    or Streamlit secrets.
"""

from __future__ import annotations

from typing import Any, Sequence

from config.settings import settings
from llm.base import LLMProvider
from models.schemas import LLMMessage, LLMResponse
from utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared base: one implementation, two vendors.
# ---------------------------------------------------------------------------


class ChatProvider(LLMProvider):
    """Shared implementation for OpenAI-compatible chat providers.

    Subclasses set:
      - name
      - _vendor      : "groq" | "xai"
      - _api_key     : bound at __init__ from config
      - _model       : default model name
      - _base_url    : None for Groq (uses native SDK); URL for xAI
    """

    name: str = "chat"
    _vendor: str = "chat"
    _api_key: str | None = None
    _model: str = ""
    _base_url: str | None = None

    # Lazily-resolved client (Groq SDK OR openai.OpenAI pointed at x.ai)
    _client: Any = None

    # ---------- availability ---------------------------------------------

    def is_available(self) -> bool:
        return bool(self._api_key)

    # ---------- client bootstrap -----------------------------------------

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(
                f"{self.name} API key not configured. Set the appropriate "
                f"environment variable (GROQ_API_KEY or XAI_API_KEY) or "
                f"Streamlit secret."
            )

        if self._vendor == "groq":
            try:
                from groq import Groq  # lazy
            except ImportError as e:
                raise RuntimeError(
                    "groq package not installed. Run: pip install groq"
                ) from e
            self._client = Groq(api_key=self._api_key)
            log.debug("Initialised Groq client (model=%s)", self._model)

        elif self._vendor == "xai":
            try:
                # xAI is OpenAI-compatible; use the `openai` SDK pointed
                # at https://api.x.ai/v1.
                from openai import OpenAI  # lazy
            except ImportError as e:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai "
                    "(required for xAI support — xAI uses the OpenAI-compatible "
                    "interface)."
                ) from e
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url or "https://api.x.ai/v1",
            )
            log.debug(
                "Initialised xAI client (model=%s base_url=%s)",
                self._model, self._base_url,
            )
        else:
            raise RuntimeError(
                f"Unknown vendor '{self._vendor}' — expected 'groq' or 'xai'."
            )

        return self._client

    # ---------- chat ------------------------------------------------------

    def chat(
        self,
        messages: Sequence[LLMMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> LLMResponse:
        client = self._get_client()
        payload = [{"role": m.role, "content": m.content} for m in messages]
        log.debug(
            "%s chat: model=%s msgs=%d temp=%.2f max_tokens=%d",
            self.name, self._model, len(payload), temperature, max_tokens,
        )

        try:
            resp = client.chat.completions.create(
                model=self._model,
                messages=payload,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            # Uniform error surface; the ai_service layer already catches
            # this and renders a friendly message, so we just enrich the log
            # and re-raise.
            log.exception(
                "%s chat.completions.create failed (model=%s): %s",
                self.name, self._model, e,
            )
            raise

        # Both Groq and openai SDKs return the same shape.
        try:
            content = (resp.choices[0].message.content or "").strip()
        except (AttributeError, IndexError) as e:
            log.error(
                "%s returned unexpected response shape: %r", self.name, resp
            )
            raise RuntimeError(
                f"{self.name}: empty or malformed response"
            ) from e

        usage: dict[str, Any] = {}
        if getattr(resp, "usage", None):
            # Both SDKs expose these three attributes.
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                "completion_tokens": getattr(
                    resp.usage, "completion_tokens", None
                ),
                "total_tokens": getattr(resp.usage, "total_tokens", None),
            }

        return LLMResponse(
            content=content,
            provider=self.name,
            model=self._model,
            usage=usage,
        )


# ---------------------------------------------------------------------------
# Groq — kept as the original export so llm/factory.py does not change.
# ---------------------------------------------------------------------------


class GroqProvider(ChatProvider):
    """Groq LLM provider. Uses the native `groq` SDK."""

    name = "groq"
    _vendor = "groq"

    def __init__(self) -> None:
        self._api_key = settings.GROQ_API_KEY
        self._model = settings.GROQ_MODEL or "llama-3.3-70b-versatile"
        self._base_url = None
        self._client = None


# ---------------------------------------------------------------------------
# xAI (Grok) — new, OpenAI-compatible.
# ---------------------------------------------------------------------------


class XAIProvider(ChatProvider):
    """xAI (Grok) LLM provider via the OpenAI-compatible endpoint."""

    name = "xai"
    _vendor = "xai"

    def __init__(self) -> None:
        self._api_key = settings.XAI_API_KEY
        self._model = settings.XAI_MODEL or "grok-2-latest"
        # Default xAI endpoint. Override via settings.XAI_BASE_URL if
        # you ever need the us-west-1 regional endpoint.
        self._base_url = (
            getattr(settings, "XAI_BASE_URL", None) or "https://api.x.ai/v1"
        )
        self._client = None


# ---------------------------------------------------------------------------
# Auto-detection helper.
#
# Used by llm/factory.py when LLM_PROVIDER=auto (or is unset). Prefers xAI
# when XAI_API_KEY is present, otherwise falls back to Groq. If neither is
# set, returns a GroqProvider whose .is_available() will cleanly return
# False — callers (ai_service) already render a friendly "not configured"
# message in that case.
# ---------------------------------------------------------------------------


def resolve_auto_provider() -> ChatProvider:
    if settings.XAI_API_KEY:
        log.info("Auto-detect: XAI_API_KEY present → using xAI (Grok).")
        return XAIProvider()
    if settings.GROQ_API_KEY:
        log.info("Auto-detect: GROQ_API_KEY present → using Groq.")
        return GroqProvider()
    log.warning(
        "Auto-detect: no LLM API key set (GROQ_API_KEY / XAI_API_KEY). "
        "Returning Groq provider; .is_available() will be False."
    )
    return GroqProvider()
