"""
utils/helpers.py
----------------
Small, dependency-free helpers used across the app.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utcnow() -> datetime:
    """Timezone-aware UTC now. Prefer this over datetime.utcnow()."""
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat(timespec="seconds")


def safe_load_json(path: Path) -> Any:
    """Load a JSON file; return {} on missing/corrupt files."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def safe_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


# Loose deadline parsing: pull plausible dates from free text.
_DATE_PATTERNS = [
    # 12 March 2026 / 12 Mar 2026
    re.compile(
        r"\b(\d{1,2})\s+"
        r"(january|february|march|april|may|june|july|august|"
        r"september|october|november|december|"
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
        r"\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    # 2026-03-12
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    # 12/03/2026 or 03/12/2026 (ambiguous; we just capture)
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
]


def try_extract_deadline(text: str) -> Optional[str]:
    """
    Best-effort deadline extraction. Returns an ISO date string or None.
    We deliberately do NOT hallucinate — only return dates that actually
    appear in the text.
    """
    if not text:
        return None
    for rx in _DATE_PATTERNS:
        m = rx.search(text)
        if not m:
            continue
        try:
            if rx is _DATE_PATTERNS[0]:
                day, month_name, year = m.groups()
                month_map = {
                    "jan": 1, "january": 1, "feb": 2, "february": 2,
                    "mar": 3, "march": 3, "apr": 4, "april": 4,
                    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
                    "aug": 8, "august": 8, "sep": 9, "sept": 9,
                    "september": 9, "oct": 10, "october": 10,
                    "nov": 11, "november": 11, "dec": 12, "december": 12,
                }
                month = month_map[month_name.lower()]
                return f"{int(year):04d}-{month:02d}-{int(day):02d}"
            elif rx is _DATE_PATTERNS[1]:
                y, mo, d = map(int, m.groups())
                return f"{y:04d}-{mo:02d}-{d:02d}"
            else:
                a, b, y = map(int, m.groups())
                # Assume dd/mm/yyyy (UK/EU style, which dominates our sources)
                return f"{y:04d}-{b:02d}-{a:02d}"
        except (ValueError, KeyError):
            continue
    return None


def truncate(text: str, limit: int = 280) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower())
    return text.strip("-")[:80] or "item"
