"""
services/ingestion_service.py
-----------------------------
Orchestrates ingestion: provider -> parser -> DB upsert -> FetchLog.

Callers (admin page, scheduled jobs) invoke `refresh_sources()`
or `refresh_source(source_id)`. All errors are trapped and logged
so the UI never crashes from a bad source.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from db.database import session_scope
from ingestion.factory import get_ingestion_provider
from models.orm import FetchLog, ScholarshipSource
from services.scholarship_service import upsert_scholarships
from utils.helpers import utcnow
from utils.logger import get_logger

log = get_logger(__name__)


def refresh_source(source_id: int) -> dict:
    """Refresh a single source. Returns a result summary dict."""
    with session_scope() as db:
        src = db.get(ScholarshipSource, source_id)
        if not src:
            return {"ok": False, "error": "source_not_found"}
        url = src.url
        country = src.country
        name = src.name
        credibility = src.credibility
        src_snapshot = {
            "id": src.id, "name": name, "url": url,
            "country": country, "credibility": credibility,
        }

    provider = get_ingestion_provider()
    result = provider.fetch(url, country=country)

    # Enrich entries with the source's metadata
    for entry in result.entries:
        entry.country = entry.country or country
        entry.source_name = entry.source_name or name
        entry.credibility = entry.credibility or credibility

    inserted = updated = 0
    if result.success and result.entries:
        inserted, updated = upsert_scholarships(result.entries)

    status = "success" if result.success else "failed"
    if result.success and not result.entries:
        status = "partial"

    # Update source + log
    with session_scope() as db:
        src = db.get(ScholarshipSource, source_id)
        if src is not None:
            src.last_fetched_at = utcnow()
            src.last_status = status
            src.last_error = result.error or None

        db.add(FetchLog(
            provider=result.provider,
            source_url=url,
            status=status,
            items_found=len(result.entries),
            message=result.error or f"ok (in={inserted}, up={updated})",
            duration_ms=result.duration_ms,
        ))

    log.info(
        "Refreshed source id=%s url=%s status=%s entries=%d",
        source_id, url, status, len(result.entries),
    )
    return {
        "ok": result.success,
        "status": status,
        "source": src_snapshot,
        "entries": len(result.entries),
        "inserted": inserted,
        "updated": updated,
        "error": result.error,
        "provider": result.provider,
        "duration_ms": result.duration_ms,
    }


def refresh_sources(
    country: Optional[str] = None, only_active: bool = True
) -> list[dict]:
    """Refresh all sources (optionally filtered by country)."""
    with session_scope() as db:
        stmt = select(ScholarshipSource)
        if only_active:
            stmt = stmt.where(ScholarshipSource.active.is_(True))
        if country:
            stmt = stmt.where(ScholarshipSource.country == country)
        ids = [s.id for s in db.scalars(stmt)]

    results = []
    for sid in ids:
        try:
            results.append(refresh_source(sid))
        except Exception as e:
            log.exception("refresh_source failed for id=%s", sid)
            results.append({"ok": False, "error": str(e), "source_id": sid})
    return results


def recent_logs(limit: int = 50) -> list[FetchLog]:
    with session_scope() as db:
        rows = list(db.scalars(
            select(FetchLog).order_by(FetchLog.created_at.desc()).limit(limit)
        ))
        for r in rows:
            db.expunge(r)
        return rows
