"""
services/source_registry_service.py
-----------------------------------
CRUD + seeding for the v0.9 curated source registry.

Registry rows drive the controlled refresh: only links inside
`allowed_domains` whose anchor or URL contains a `follow_keyword` (and
no `block_keywords`) may be followed, bounded by `max_depth`.

JSON-list fields (`start_urls`, `allowed_domains`, `follow_keywords`,
`block_keywords`) are stored as Text/JSON for SQLite portability and
decoded transparently by this service.
"""

from __future__ import annotations

import json
from typing import Iterable, Optional

from sqlalchemy import select

from config.settings import SEEDS_DIR
from db.database import session_scope
from models.orm import CuratedSource
from models.schemas import CuratedSourceDTO
from utils.helpers import safe_load_json, utcnow
from utils.logger import get_logger

log = get_logger(__name__)


# ---------- DTO conversion -----------------------------------------------


def _decode_list(blob: Optional[str]) -> list[str]:
    if not blob:
        return []
    try:
        v = json.loads(blob)
    except json.JSONDecodeError:
        return []
    if not isinstance(v, list):
        return []
    return [str(x) for x in v if isinstance(x, (str, int, float))]


def _to_dto(row: CuratedSource) -> CuratedSourceDTO:
    return CuratedSourceDTO(
        id=row.id,
        name=row.name,
        provider=row.provider,
        destination_country=row.destination_country,
        base_url=row.base_url,
        start_urls=_decode_list(row.start_urls_json),
        allowed_domains=_decode_list(row.allowed_domains_json),
        follow_keywords=_decode_list(row.follow_keywords_json),
        block_keywords=_decode_list(row.block_keywords_json),
        max_depth=row.max_depth,
        source_type=row.source_type,
        is_active=row.is_active,
        requires_admin_review=row.requires_admin_review,
        last_refreshed_at=row.last_refreshed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ---------- Reads ---------------------------------------------------------


def list_sources(
    *,
    active_only: bool = False,
    destination_country: Optional[str] = None,
) -> list[CuratedSourceDTO]:
    with session_scope() as db:
        stmt = select(CuratedSource)
        if active_only:
            stmt = stmt.where(CuratedSource.is_active.is_(True))
        if destination_country:
            stmt = stmt.where(
                CuratedSource.destination_country == destination_country
            )
        stmt = stmt.order_by(CuratedSource.destination_country,
                             CuratedSource.name)
        return [_to_dto(r) for r in db.scalars(stmt)]


def get_source(source_id: int) -> Optional[CuratedSourceDTO]:
    with session_scope() as db:
        row = db.get(CuratedSource, source_id)
        return _to_dto(row) if row else None


def get_source_by_name(
    name: str, destination_country: str,
) -> Optional[CuratedSourceDTO]:
    with session_scope() as db:
        row = db.scalar(
            select(CuratedSource).where(
                (CuratedSource.name == name)
                & (CuratedSource.destination_country == destination_country)
            )
        )
        return _to_dto(row) if row else None


# ---------- Writes --------------------------------------------------------


def upsert_source(payload: dict) -> int:
    """Create or update a curated source by (name, destination_country).
    Returns the row id."""
    name = (payload.get("name") or "").strip()
    dest = (payload.get("destination_country") or "").strip()
    if not name or not dest:
        raise ValueError("name and destination_country are required.")

    with session_scope() as db:
        row = db.scalar(
            select(CuratedSource).where(
                (CuratedSource.name == name)
                & (CuratedSource.destination_country == dest)
            )
        )
        is_new = row is None
        if is_new:
            row = CuratedSource(
                name=name, destination_country=dest,
                base_url=payload.get("base_url", ""),
            )
            db.add(row)

        # Mutable fields
        if "provider" in payload:
            row.provider = payload.get("provider")
        if "base_url" in payload:
            row.base_url = payload.get("base_url") or row.base_url
        for json_attr, key in (
            ("start_urls_json",      "start_urls"),
            ("allowed_domains_json", "allowed_domains"),
            ("follow_keywords_json", "follow_keywords"),
            ("block_keywords_json",  "block_keywords"),
        ):
            if key in payload:
                items = payload.get(key) or []
                if not isinstance(items, list):
                    raise ValueError(f"{key} must be a list of strings")
                setattr(row, json_attr, json.dumps([str(x) for x in items]))
        if "max_depth" in payload:
            row.max_depth = int(payload.get("max_depth") or 2)
        if "source_type" in payload:
            row.source_type = (
                payload.get("source_type") or "scholarship_program"
            )
        if "is_active" in payload:
            row.is_active = bool(payload.get("is_active"))
        if "requires_admin_review" in payload:
            row.requires_admin_review = bool(
                payload.get("requires_admin_review")
            )
        row.updated_at = utcnow()

        db.flush()
        log.info(
            "%s curated source: id=%s name=%s country=%s",
            "Created" if is_new else "Updated",
            row.id, row.name, row.destination_country,
        )
        return row.id


def set_active(source_id: int, active: bool) -> bool:
    with session_scope() as db:
        row = db.get(CuratedSource, source_id)
        if row is None:
            return False
        row.is_active = active
        row.updated_at = utcnow()
        return True


def mark_refreshed(source_id: int) -> None:
    with session_scope() as db:
        row = db.get(CuratedSource, source_id)
        if row is None:
            return
        row.last_refreshed_at = utcnow()


def delete_source(source_id: int) -> bool:
    with session_scope() as db:
        row = db.get(CuratedSource, source_id)
        if row is None:
            return False
        db.delete(row)
        return True


# ---------- Seeding -------------------------------------------------------


def seed_from_json() -> int:
    """Load the curated registry from data/seeds/scholarship_sources.json.
    Idempotent: existing rows (matched by name+country) are updated, not
    duplicated. Returns count inserted/updated."""
    doc = safe_load_json(SEEDS_DIR / "scholarship_sources.json") or {}
    seeds: Iterable[dict] = doc.get("sources") or []
    count = 0
    for s in seeds:
        try:
            upsert_source(s)
            count += 1
        except Exception as e:
            log.warning(
                "Could not seed curated source %r: %s", s.get("name"), e
            )
    if count:
        log.info("Seeded/updated %d curated source(s).", count)
    return count
