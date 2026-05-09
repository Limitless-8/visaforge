"""
services/policy_service.py
--------------------------
Manages the source registry (scholarship + policy sources) and
exposes readers for visa rules / route templates so the admin page
can show freshness and let users refresh.
"""

from __future__ import annotations

from sqlalchemy import select

from config.settings import SEEDS_DIR
from db.database import session_scope
from models.orm import ScholarshipSource
from models.schemas import SourceConfig
from utils.helpers import safe_load_json
from utils.logger import get_logger

log = get_logger(__name__)


def list_sources(country: str | None = None) -> list[ScholarshipSource]:
    with session_scope() as db:
        stmt = select(ScholarshipSource).order_by(
            ScholarshipSource.country, ScholarshipSource.name
        )
        if country:
            stmt = stmt.where(ScholarshipSource.country == country)
        rows = list(db.scalars(stmt))
        for r in rows:
            db.expunge(r)
        return rows


def add_source(cfg: SourceConfig) -> int:
    with session_scope() as db:
        existing = db.scalar(
            select(ScholarshipSource).where(
                ScholarshipSource.url == cfg.url
            )
        )
        if existing:
            return existing.id
        row = ScholarshipSource(
            name=cfg.name,
            url=cfg.url,
            country=cfg.country,
            category=cfg.category,
            credibility=cfg.credibility,
            active=True,
        )
        db.add(row)
        db.flush()
        return row.id


def set_source_active(source_id: int, active: bool) -> bool:
    with session_scope() as db:
        row = db.get(ScholarshipSource, source_id)
        if not row:
            return False
        row.active = active
        return True


def get_visa_rules_meta() -> dict:
    """Return metadata for the visa rules seed (used by admin page)."""
    data = safe_load_json(SEEDS_DIR / "visa_rules.json")
    return data.get("_meta", {})


def get_route_templates_meta() -> dict:
    data = safe_load_json(SEEDS_DIR / "route_templates.json")
    return data.get("_meta", {})
