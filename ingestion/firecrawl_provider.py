"""
ingestion/firecrawl_provider.py
-------------------------------
Firecrawl-based ingestion provider (active for MVP).

Tries Firecrawl first; if the API key is missing, rate-limited, or any
error occurs, gracefully falls back to a polite requests+BeautifulSoup
fetch so demos don't break. All failures are captured in IngestionResult.
"""

from __future__ import annotations

import time
from typing import Any

from config.settings import settings
from ingestion.base import IngestionProvider
from ingestion.parser import extract_scholarships
from models.schemas import IngestionResult
from utils.logger import get_logger

log = get_logger(__name__)

_USER_AGENT = (
    "VisaForgeBot/0.1 (academic research prototype; contact: visaforge@example.org)"
)
_HTTP_TIMEOUT = 20


class FirecrawlProvider(IngestionProvider):
    name = "firecrawl"

    def __init__(self) -> None:
        self._api_key = settings.FIRECRAWL_API_KEY
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from firecrawl import FirecrawlApp  # lazy import
            self._client = FirecrawlApp(api_key=self._api_key)
            return self._client
        except ImportError:
            log.warning("firecrawl-py not installed; using HTTP fallback only.")
            return None
        except Exception as e:  # pragma: no cover
            log.warning("Firecrawl init failed (%s); using HTTP fallback.", e)
            return None

    def is_available(self) -> bool:
        # Always "available" — we can always fall back to plain HTTP.
        return True

    # ---------- main entry ----------

    def fetch(self, url: str, *, country: str = "UK") -> IngestionResult:
        t0 = time.time()
        text, error, used_firecrawl = self._fetch_text(url)
        if text is None and error:
            return IngestionResult(
                source_url=url,
                success=False,
                error=error,
                provider=self.name,
                duration_ms=int((time.time() - t0) * 1000),
            )

        try:
            entries = extract_scholarships(
                url=url,
                country=country,
                text=text or "",
            )
        except Exception as e:  # parser must never kill ingestion
            log.exception("Parser failed for %s", url)
            entries = []
            error = f"parser_error: {e}"

        return IngestionResult(
            source_url=url,
            success=True,
            raw_text=(text or "")[:20000],  # cap
            entries=entries,
            error=error,
            provider=self.name + ("" if used_firecrawl else "+http_fallback"),
            duration_ms=int((time.time() - t0) * 1000),
        )

    # ---------- internals ----------

    def _fetch_text(self, url: str) -> tuple[str | None, str | None, bool]:
        """Return (text, error, used_firecrawl)."""
        client = self._get_client()
        if client is not None:
            try:
                result = self._firecrawl_scrape(client, url)
                text = self._extract_text_from_firecrawl(result)
                if text and text.strip():
                    return text, None, True
                log.info("Firecrawl returned empty content for %s; falling back.", url)
            except Exception as e:
                log.warning("Firecrawl error for %s: %s", url, e)

        # HTTP fallback (polite)
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(
                url,
                timeout=_HTTP_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
            )
            if resp.status_code >= 400:
                return None, f"http_{resp.status_code}", False
            soup = BeautifulSoup(resp.text, "lxml")
            # Strip scripts/styles/nav noise
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return text, None, False
        except Exception as e:
            return None, f"http_fallback_error: {e}", False

    def _firecrawl_scrape(self, client: Any, url: str) -> Any:
        """Call Firecrawl's scrape endpoint. API varies by SDK version; we
        try the newer signature first, then fall back to the older one."""
        # Newer firecrawl-py (>= 1.x)
        try:
            return client.scrape_url(
                url,
                params={"formats": ["markdown"]},
            )
        except TypeError:
            pass
        except Exception:
            # Re-try older shape
            pass
        try:
            return client.scrape_url(url)
        except Exception as e:
            raise e

    @staticmethod
    def _extract_text_from_firecrawl(result: Any) -> str:
        """Firecrawl responses can be dict-like or object-like; normalise."""
        if result is None:
            return ""
        # Dict-shape (most common)
        if isinstance(result, dict):
            for key in ("markdown", "content", "text"):
                val = result.get(key)
                if isinstance(val, str) and val.strip():
                    return val
            data = result.get("data")
            if isinstance(data, dict):
                for key in ("markdown", "content", "text"):
                    val = data.get(key)
                    if isinstance(val, str) and val.strip():
                        return val
        # Object-shape
        for attr in ("markdown", "content", "text"):
            val = getattr(result, attr, None)
            if isinstance(val, str) and val.strip():
                return val
        return ""
