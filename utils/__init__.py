"""Utility helpers for VisaForge."""
from .logger import get_logger
from .helpers import (
    utcnow,
    iso_now,
    safe_load_json,
    safe_write_json,
    try_extract_deadline,
    truncate,
    slugify,
)
from .reference_data import (
    country_names,
    nationality_options,
    STUDY_FIELDS,
    OFFER_STATUS_OPTIONS,
    FUNDS_STATUS_OPTIONS,
    OFFER_STATUS_STRENGTH,
    FUNDS_STATUS_STRENGTH,
    TARGET_INTAKE_OPTIONS,
    normalize_fields,
    fields_to_storage,
    safe_index,
)
from .text_cleaning import (
    clean_text,
    title_similarity,
    is_likely_duplicate,
    deduplicate,
)

__all__ = [
    "get_logger",
    "utcnow",
    "iso_now",
    "safe_load_json",
    "safe_write_json",
    "try_extract_deadline",
    "truncate",
    "slugify",
    "country_names",
    "nationality_options",
    "STUDY_FIELDS",
    "OFFER_STATUS_OPTIONS",
    "FUNDS_STATUS_OPTIONS",
    "OFFER_STATUS_STRENGTH",
    "FUNDS_STATUS_STRENGTH",
    "TARGET_INTAKE_OPTIONS",
    "normalize_fields",
    "fields_to_storage",
    "safe_index",
    "clean_text",
    "title_similarity",
    "is_likely_duplicate",
    "deduplicate",
]
