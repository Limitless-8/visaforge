"""
ingestion/crawlee_provider.py
-----------------------------
PLACEHOLDER provider. Not active in the MVP.

Crawlee (https://crawlee.dev) provides production-grade crawling with
built-in proxy rotation, queueing, and storage. Wire it up here when
large-scale / scheduled ingestion is needed.
"""

from __future__ import annotations

from ingestion.base import IngestionProvider
from models.schemas import IngestionResult


class CrawleeProvider(IngestionProvider):
    name = "crawlee"

    def is_available(self) -> bool:
        return False  # Not implemented

    def fetch(self, url: str, *, country: str = "UK") -> IngestionResult:
        return IngestionResult(
            source_url=url,
            success=False,
            error="CrawleeProvider is a placeholder — not yet implemented.",
            provider=self.name,
        )
