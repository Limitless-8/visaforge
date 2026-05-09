"""
ingestion/base.py
-----------------
Abstract interface for web ingestion providers.

Every provider must:
- accept a URL
- return an `IngestionResult` with raw text + normalised entries
- never raise on HTTP/parse errors (return success=False instead)
- respect polite-crawling defaults
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.schemas import IngestionResult


class IngestionProvider(ABC):
    """Contract for a scholarship/policy ingestion provider."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if provider is configured and ready to use."""

    @abstractmethod
    def fetch(self, url: str, *, country: str = "UK") -> IngestionResult:
        """Fetch a URL and return normalized content.

        Must not raise on network/parse failures — return an IngestionResult
        with success=False and a populated `error` instead. This lets the
        caller degrade gracefully.
        """
