"""
config/settings.py
------------------
Central configuration loader for VisaForge.

Reads configuration from (in order of precedence):
  1. Streamlit secrets (when running inside Streamlit)
  2. Environment variables
  3. .env file (via python-dotenv)
  4. Safe defaults

Design goals:
- Single source of truth for all tunable values.
- No module outside `config/` should read env vars directly.
- Easy swap between providers (LLM, ingestion) via config only.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load .env if present (no-op on Streamlit Cloud if absent).
load_dotenv()

# ----- Paths ---------------------------------------------------------------
ROOT_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = ROOT_DIR / "data"
SEEDS_DIR: Path = DATA_DIR / "seeds"
CACHE_DIR: Path = DATA_DIR / "cache"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a config value from Streamlit secrets or env vars.
    Streamlit secrets take precedence when available.
    """
    # Try Streamlit secrets first — but only if Streamlit is importable
    # AND a secrets file actually exists. This avoids noisy warnings.
    try:
        import streamlit as st  # local import to keep non-Streamlit use possible
        # st.secrets raises if no secrets.toml is configured; guard it.
        if hasattr(st, "secrets"):
            try:
                if key in st.secrets:
                    return str(st.secrets[key])
            except Exception:
                # No secrets.toml configured; fall through to env.
                pass
    except ImportError:
        pass

    val = os.getenv(key)
    if val is not None and val != "":
        return val
    return default


class Settings:
    """Immutable-ish settings object, exposed as a singleton `settings`."""

    # --- App ---
    APP_NAME: str = "VisaForge"
    APP_TAGLINE: str = "AI-assisted immigration & scholarship guidance"
    APP_ENV: str = _get("APP_ENV", "development") or "development"
    LOG_LEVEL: str = _get("LOG_LEVEL", "INFO") or "INFO"

    # --- Database ---
    DATABASE_URL: str = _get(
        "DATABASE_URL", f"sqlite:///{DATA_DIR / 'visaforge.db'}"
    ) or f"sqlite:///{DATA_DIR / 'visaforge.db'}"

    # --- LLM provider ---
    # Supported values: "groq" | "xai" | "openai" | "auto"
    # "auto" prefers xAI when XAI_API_KEY is present, else Groq.
    LLM_PROVIDER: str = (_get("LLM_PROVIDER", "auto") or "auto").lower()

    # Groq
    GROQ_API_KEY: Optional[str] = _get("GROQ_API_KEY")
    GROQ_MODEL: str = _get("GROQ_MODEL", "llama-3.3-70b-versatile") \
        or "llama-3.3-70b-versatile"

    # xAI (Grok)
    XAI_API_KEY: Optional[str] = _get("XAI_API_KEY")
    XAI_MODEL: str = _get("XAI_MODEL", "grok-4-1-fast-non-reasoning") or "grok-4-1-fast-non-reasoning"
    XAI_BASE_URL: str = _get("XAI_BASE_URL", "https://api.x.ai/v1") \
        or "https://api.x.ai/v1"

    # OpenAI (placeholder)
    OPENAI_API_KEY: Optional[str] = _get("OPENAI_API_KEY")
    OPENAI_MODEL: str = _get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"

    # --- Ingestion provider ---
    INGESTION_PROVIDER: str = (
        _get("INGESTION_PROVIDER", "firecrawl") or "firecrawl"
    ).lower()
    FIRECRAWL_API_KEY: Optional[str] = _get("FIRECRAWL_API_KEY")
    TINYFISH_API_KEY: Optional[str] = _get("TINYFISH_API_KEY")

    # --- Email / SMTP ---
    EMAIL_FROM: str = _get("EMAIL_FROM", "") or ""
    SMTP_HOST: str = _get("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com"
    SMTP_PORT: int = int(_get("SMTP_PORT", "587") or "587")
    SMTP_USER: str = _get("SMTP_USER", "") or ""
    SMTP_PASSWORD: str = _get("SMTP_PASSWORD", "") or ""

    # --- Feature flags ---
    ENABLE_LIVE_INGESTION: bool = (
        _get("ENABLE_LIVE_INGESTION", "true") or "true"
    ).lower() == "true"

    # --- Countries in scope ---
    SUPPORTED_COUNTRIES: tuple = ("UK", "Canada", "Germany")

    def as_dict(self) -> dict[str, Any]:
        """Return a redacted dict suitable for the admin/debug page."""
        def redact(v: Optional[str]) -> str:
            if not v:
                return "<unset>"
            if len(v) < 8:
                return "***"
            return v[:4] + "…" + v[-2:]

        return {
            "APP_ENV": self.APP_ENV,
            "LOG_LEVEL": self.LOG_LEVEL,
            "DATABASE_URL": self.DATABASE_URL,
            "LLM_PROVIDER": self.LLM_PROVIDER,
            "GROQ_MODEL": self.GROQ_MODEL,
            "GROQ_API_KEY": redact(self.GROQ_API_KEY),
            "XAI_MODEL": self.XAI_MODEL,
            "XAI_API_KEY": redact(self.XAI_API_KEY),
            "XAI_BASE_URL": self.XAI_BASE_URL,
            "OPENAI_MODEL": self.OPENAI_MODEL,
            "OPENAI_API_KEY": redact(self.OPENAI_API_KEY),
            "INGESTION_PROVIDER": self.INGESTION_PROVIDER,
            "FIRECRAWL_API_KEY": redact(self.FIRECRAWL_API_KEY),
            "ENABLE_LIVE_INGESTION": self.ENABLE_LIVE_INGESTION,
            "SUPPORTED_COUNTRIES": list(self.SUPPORTED_COUNTRIES),
            "EMAIL_FROM": self.EMAIL_FROM,
            "SMTP_HOST": self.SMTP_HOST,
            "SMTP_PORT": self.SMTP_PORT,
            "SMTP_USER": redact(self.SMTP_USER),
            "SMTP_PASSWORD": redact(self.SMTP_PASSWORD),
        }

settings = Settings()


