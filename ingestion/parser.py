"""
ingestion/parser.py
-------------------
Shared content-normalization helpers used by ingestion providers.

Given a page's text (markdown or extracted HTML text), produce a list of
candidate `ScholarshipDTO` entries. Deliberately conservative: when in
doubt, we create a single "fallback" page-level entry rather than
hallucinate multiple structured scholarships.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from models.schemas import ScholarshipDTO
from utils.helpers import truncate, try_extract_deadline, utcnow


# Heuristics for scholarship-like headings in extracted text
_HEADING_RX = re.compile(
    r"^(?P<title>[A-Z][^\n]{8,160}?(scholarship|bursary|fellowship|"
    r"grant|award|stipend)s?[^\n]{0,80})$",
    re.IGNORECASE | re.MULTILINE,
)

_LINK_RX = re.compile(r"\[([^\]]{4,200})\]\((https?://[^\s)]+)\)")


def _source_name_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or url
        return host.replace("www.", "")
    except Exception:
        return url


def extract_scholarships(
    *,
    url: str,
    country: str,
    text: str,
    source_name: str | None = None,
    credibility: str = "official",
) -> list[ScholarshipDTO]:
    """Extract plausible scholarship entries from page text.

    Strategy:
      1. Find markdown-style links whose anchor text looks scholarship-like.
      2. Fall back to heading-line heuristics.
      3. If nothing found, return a single page-level fallback entry so
         the UI always has something attributable to show.
    """
    if not text:
        return [
            _fallback_entry(url, country, source_name, credibility,
                            summary="(Source reachable but empty content)")
        ]

    source_name = source_name or _source_name_from_url(url)
    entries: list[ScholarshipDTO] = []
    seen_titles: set[str] = set()

    # 1) Link-based extraction (works well on Firecrawl markdown)
    for m in _LINK_RX.finditer(text):
        anchor, link = m.group(1).strip(), m.group(2).strip()
        low = anchor.lower()
        if not any(
            kw in low
            for kw in (
                "scholarship", "bursary", "fellowship", "grant",
                "award", "stipend", "funding",
            )
        ):
            continue
        if anchor in seen_titles or len(anchor) < 10:
            continue
        seen_titles.add(anchor)

        # Pull a few surrounding chars as context for deadline extraction
        start = max(0, m.start() - 200)
        end = min(len(text), m.end() + 300)
        context = text[start:end]

        entries.append(
            ScholarshipDTO(
                title=truncate(anchor, 380),
                provider=source_name,
                country=country,
                degree_level=None,
                field_of_study=None,
                deadline=try_extract_deadline(context),
                summary=truncate(context.replace("\n", " "), 320),
                source_url=link if link.startswith("http") else url,
                source_name=source_name,
                credibility=credibility,
                fetched_at=utcnow(),
                is_fallback=False,
            )
        )

    # 2) Heading-line heuristic
    if not entries:
        for m in _HEADING_RX.finditer(text):
            title = m.group("title").strip()
            if title in seen_titles or len(title) < 15:
                continue
            seen_titles.add(title)
            start = max(0, m.start() - 100)
            end = min(len(text), m.end() + 400)
            context = text[start:end]
            entries.append(
                ScholarshipDTO(
                    title=truncate(title, 380),
                    provider=source_name,
                    country=country,
                    deadline=try_extract_deadline(context),
                    summary=truncate(context.replace("\n", " "), 320),
                    source_url=url,
                    source_name=source_name,
                    credibility=credibility,
                    fetched_at=utcnow(),
                    is_fallback=False,
                )
            )

    # 3) Fallback — always give the UI something attributable
    if not entries:
        entries.append(
            _fallback_entry(url, country, source_name, credibility,
                            summary=truncate(text.replace("\n", " "), 320))
        )

    return entries[:40]  # sensible cap per page


def _fallback_entry(
    url: str,
    country: str,
    source_name: str | None,
    credibility: str,
    *,
    summary: str,
) -> ScholarshipDTO:
    return ScholarshipDTO(
        title=f"{source_name or _source_name_from_url(url)} — scholarships page",
        provider=source_name or _source_name_from_url(url),
        country=country,
        deadline=None,
        summary=summary or "Visit source for full details.",
        source_url=url,
        source_name=source_name or _source_name_from_url(url),
        credibility=credibility,
        fetched_at=utcnow(),
        is_fallback=True,
    )
