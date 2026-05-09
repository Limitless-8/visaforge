"""
ingestion/tinyfish_provider.py
------------------------------
PLACEHOLDER provider. Not active in the MVP.

TinyFish (https://tinyfish.io) is an agentic web data extraction service.
When activated, configure TINYFISH_API_KEY and set
INGESTION_PROVIDER=tinyfish.

The factory will pick this up automatically; no other code changes needed.
"""

from __future__ import annotations

from config.settings import settings
from ingestion.base import IngestionProvider
from models.schemas import IngestionResult


class TinyFishProvider(IngestionProvider):
    name = "tinyfish"

    def __init__(self) -> None:
        self._api_key = settings.TINYFISH_API_KEY

    def is_available(self) -> bool:
        return bool(self._api_key)

    def fetch(self, url: str, *, country: str = "UK") -> IngestionResult:
        # --- Scaffolded implementation (pseudo) ---
        # import requests
        # resp = requests.post(
        #     "https://api.tinyfish.io/v1/extract",
        #     headers={"Authorization": f"Bearer {self._api_key}"},
        #     json={"url": url, "schema": "scholarships"},
        #     timeout=30,
        # )
        # resp.raise_for_status()
        # data = resp.json()
        # entries = [...]  # map data -> ScholarshipDTO
        # return IngestionResult(source_url=url, success=True,
        #                        entries=entries, provider=self.name)
        return IngestionResult(
            source_url=url,
            success=False,
            error="TinyFishProvider is a placeholder — not yet implemented.",
            provider=self.name,
        )
