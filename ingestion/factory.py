"""
ingestion/factory.py
--------------------
Factory for ingestion providers. All callers must go through
`get_ingestion_provider()`.
"""

from __future__ import annotations

from functools import lru_cache

from config.settings import settings
from ingestion.base import IngestionProvider
from ingestion.crawlee_provider import CrawleeProvider
from ingestion.firecrawl_provider import FirecrawlProvider
from ingestion.playwright_provider import PlaywrightProvider
from ingestion.tinyfish_provider import TinyFishProvider
from utils.logger import get_logger

log = get_logger(__name__)

_REGISTRY: dict[str, type[IngestionProvider]] = {
    "firecrawl": FirecrawlProvider,
    "tinyfish": TinyFishProvider,
    "playwright": PlaywrightProvider,
    "crawlee": CrawleeProvider,
}


@lru_cache(maxsize=4)
def get_ingestion_provider(name: str | None = None) -> IngestionProvider:
    key = (name or settings.INGESTION_PROVIDER).lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        log.warning(
            "Unknown ingestion provider '%s'; falling back to Firecrawl.", key
        )
        cls = FirecrawlProvider
    provider = cls()
    log.info("Ingestion provider resolved: %s (available=%s)",
             provider.name, provider.is_available())
    return provider
