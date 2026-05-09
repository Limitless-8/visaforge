"""
utils/reference_data.py
-----------------------
Centralized reference data used by forms and the eligibility engine.

Keeps country, study-field, status, and intake lists in one place so
dropdowns stay consistent across the app and in the LLM context packet.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from config.settings import SEEDS_DIR
from utils.helpers import safe_load_json


# ---------- Countries -----------------------------------------------------

@lru_cache(maxsize=1)
def _load_countries() -> list[dict[str, str]]:
    doc = safe_load_json(SEEDS_DIR / "countries.json") or {}
    return list(doc.get("countries", []))


def country_names() -> list[str]:
    """Country names, alphabetical."""
    return [c["name"] for c in _load_countries()]


def nationality_options() -> list[str]:
    """Demonym/nationality strings, alphabetical."""
    return sorted({c["demonym"] for c in _load_countries()})


# ---------- Study fields --------------------------------------------------

STUDY_FIELDS: list[str] = [
    "Computer Science",
    "Software Engineering",
    "Data Science",
    "Artificial Intelligence",
    "Cybersecurity",
    "Business",
    "Finance",
    "Engineering",
    "Medicine",
    "Law",
    "Social Sciences",
    "Education",
    "Arts and Design",
    "Psychology",
    "Environmental Science",
    "Other",
]


# ---------- Offer / funds status ------------------------------------------

OFFER_STATUS_OPTIONS: list[str] = [
    "Not yet applied",
    "Applied and waiting",
    "Conditional offer received",
    "Unconditional offer received",
    "Not required / unsure",
]

FUNDS_STATUS_OPTIONS: list[str] = [
    "Not prepared",
    "Partially prepared",
    "Fully prepared",
    "Sponsored",
    "Not sure",
]

# Evidence strength classifications used by the eligibility engine.
# "strong"  → passes a hard requirement
# "partial" → passes a soft requirement but flags missing evidence
# "none"    → fails / missing
OFFER_STATUS_STRENGTH: dict[str, str] = {
    "Unconditional offer received": "strong",
    "Conditional offer received": "partial",
    "Applied and waiting": "none",
    "Not yet applied": "none",
    "Not required / unsure": "none",
}

FUNDS_STATUS_STRENGTH: dict[str, str] = {
    "Fully prepared": "strong",
    "Sponsored": "strong",
    "Partially prepared": "partial",
    "Not prepared": "none",
    "Not sure": "none",
}


# ---------- Intake periods ------------------------------------------------

TARGET_INTAKE_OPTIONS: list[str] = [
    "January 2026",
    "May 2026",
    "September 2026",
    "January 2027",
    "May 2027",
    "September 2027",
    "January 2028",
    "May 2028",
    "September 2028",
    "Other / unsure",
]


# ---------- Small helpers -------------------------------------------------

def normalize_fields(value: Any) -> list[str]:
    """Accept list/tuple/comma-string/None → return clean list[str]."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def fields_to_storage(value: Any) -> str | None:
    """List → comma-separated string for DB storage (None if empty)."""
    items = normalize_fields(value)
    return ", ".join(items) if items else None


def safe_index(options: list[str], value: Any, default: int = 0) -> int:
    """Return the index of `value` in `options`, else `default`."""
    if value is None:
        return default
    try:
        return options.index(str(value))
    except ValueError:
        return default
