"""Ingestion provider abstraction layer."""
from .base import IngestionProvider
from .factory import get_ingestion_provider

__all__ = ["IngestionProvider", "get_ingestion_provider"]
