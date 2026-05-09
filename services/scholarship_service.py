"""
services/scholarship_service.py
-------------------------------
Scholarship CRUD, filtering, bookmarking, and — new in v0.6 — explicit
selection and deterministic matching.

v0.7:
  * Text cleaning applied on upsert (`clean_text` from utils).
  * Deduplication on upsert (URL exact + title-similarity Jaccard).
  * `list_scholarships` and `list_with_match` defensively dedupe at
    read time too.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

from sqlalchemy import and_, or_, select

from db.database import session_scope
from models.orm import SavedScholarship, ScholarshipEntry, UserProfile
from models.schemas import (
    ScholarshipDTO,
    ScholarshipEligibility,
    ScholarshipFitReport,
)
from services.scholarship_matching import match_scholarship
from services.source_classifier import (
    USER_VISIBLE_SOURCE_TYPES,
    classify_source,
    is_user_visible,
)
from utils.helpers import utcnow
from utils.logger import get_logger
from utils.text_cleaning import clean_text, deduplicate, title_similarity

log = get_logger(__name__)


# ---------- DTO conversion ------------------------------------------------


def _to_dto(r: ScholarshipEntry) -> ScholarshipDTO:
    elig: Optional[ScholarshipEligibility] = None
    if r.eligibility_json:
        try:
            elig = ScholarshipEligibility(**json.loads(r.eligibility_json))
        except Exception:  # pragma: no cover — malformed stored JSON
            log.warning("Bad eligibility_json on scholarship id=%s", r.id)
    # Defensive cleaning at display time — covers older rows that were
    # ingested before v0.7.
    summary = clean_text(r.summary or "", max_chars=500)
    return ScholarshipDTO(
        id=r.id,
        title=r.title,
        provider=r.provider,
        country=r.country,
        degree_level=r.degree_level,
        field_of_study=r.field_of_study,
        deadline=r.deadline,
        summary=summary,
        source_url=r.source_url,
        source_name=r.source_name,
        credibility=r.credibility,  # type: ignore[arg-type]
        fetched_at=r.fetched_at,
        is_fallback=r.is_fallback,
        eligibility=elig,
        source_type=r.source_type,
        review_status=r.review_status,
        version=r.version or 1,
        curated_source_id=r.curated_source_id,
    )


# ---------- Listing / filtering ------------------------------------------


def list_scholarships(
    *,
    country: Optional[str] = None,
    degree_level: Optional[str] = None,
    field_of_study: Optional[str] = None,
    only_with_deadline: bool = False,
    hide_expired: bool = True,
    include_hidden: bool = False,
    limit: int = 200,
) -> list[ScholarshipDTO]:
    """List scholarships, by default filtering to user-visible types only.

    `include_hidden=True` returns all rows including visa policy pages,
    generic education pages, and noise — used by the admin dashboard.
    """
    with session_scope() as db:
        stmt = select(ScholarshipEntry)
        conds = []
        if country:
            conds.append(ScholarshipEntry.country == country)
        if degree_level:
            conds.append(
                or_(
                    ScholarshipEntry.degree_level.is_(None),
                    ScholarshipEntry.degree_level.ilike(f"%{degree_level}%"),
                )
            )
        if field_of_study:
            conds.append(
                or_(
                    ScholarshipEntry.field_of_study.is_(None),
                    ScholarshipEntry.field_of_study.ilike(f"%{field_of_study}%"),
                )
            )
        if only_with_deadline:
            conds.append(ScholarshipEntry.deadline.is_not(None))
        if not include_hidden:
            # v0.8: filter to user-visible source types
            # (NULL → visible, for back-compat with pre-v0.8 rows; the
            # bootstrap backfill classifies them on next run).
            conds.append(
                or_(
                    ScholarshipEntry.source_type.is_(None),
                    ScholarshipEntry.source_type.in_(
                        list(USER_VISIBLE_SOURCE_TYPES)
                    ),
                )
            )
            # v0.9: only approved records reach the user view.
            # NULL review_status is treated as approved for back-compat —
            # the bootstrap backfill marks legacy rows accordingly.
            conds.append(
                or_(
                    ScholarshipEntry.review_status.is_(None),
                    ScholarshipEntry.review_status == "approved",
                )
            )
        if conds:
            stmt = stmt.where(and_(*conds))
        stmt = stmt.order_by(ScholarshipEntry.fetched_at.desc()).limit(limit)
        rows = list(db.scalars(stmt))

        today = date.today().isoformat()
        out = []
        for r in rows:
            if hide_expired and r.deadline and r.deadline < today:
                continue
            out.append(_to_dto(r))
        # Defensive dedupe at read time
        out = deduplicate(out, title_attr="title", url_attr="source_url")
        return out


def get_scholarship(sch_id: int) -> ScholarshipDTO | None:
    with session_scope() as db:
        r = db.get(ScholarshipEntry, sch_id)
        if not r:
            return None
        return _to_dto(r)


# ---------- Writes --------------------------------------------------------


def upsert_scholarships(entries: list[ScholarshipDTO]) -> tuple[int, int]:
    """Insert new or update existing entries, deduplicating + cleaning text.

    Dedupe order:
      1. Match an existing row on (source_url, title) exact pair.
      2. If no exact match, look for a row with the same source_url and
         a near-identical title (Jaccard ≥ 0.85) and update it instead
         of inserting.

    Text cleaning:
      Summary fields are passed through `clean_text` (HTML strip + nav
      noise removal + truncation) before being persisted.
    """
    inserted = 0
    updated = 0
    # Pre-clean and pre-dedupe the incoming batch first.
    cleaned: list[ScholarshipDTO] = []
    for e in entries:
        e = e.model_copy(update={
            "title": (e.title or "").strip(),
            "summary": clean_text(e.summary, max_chars=500),
        })
        if e.title:
            cleaned.append(e)
    cleaned = deduplicate(
        cleaned, title_attr="title", url_attr="source_url"
    )  # type: ignore[assignment]

    with session_scope() as db:
        for e in cleaned:
            # Classify source type before persisting (v0.8). Always
            # recompute on upsert so changes to source content update
            # the classification.
            classification = classify_source(
                title=e.title,
                summary=e.summary,
                source_url=e.source_url,
                source_name=e.source_name,
            )

            # 1. exact source_url + title
            existing = db.scalar(
                select(ScholarshipEntry).where(
                    (ScholarshipEntry.source_url == e.source_url)
                    & (ScholarshipEntry.title == e.title)
                )
            )
            # 2. fall-back: same URL with near-duplicate title
            if existing is None:
                same_url = list(db.scalars(
                    select(ScholarshipEntry).where(
                        ScholarshipEntry.source_url == e.source_url
                    )
                ))
                for cand in same_url:
                    if title_similarity(e.title, cand.title) >= 0.85:
                        existing = cand
                        break

            if existing:
                existing.summary = e.summary or existing.summary
                existing.deadline = e.deadline or existing.deadline
                existing.degree_level = e.degree_level or existing.degree_level
                existing.field_of_study = (
                    e.field_of_study or existing.field_of_study
                )
                existing.provider = e.provider or existing.provider
                existing.source_name = e.source_name or existing.source_name
                existing.credibility = e.credibility or existing.credibility
                existing.fetched_at = utcnow()
                existing.is_fallback = e.is_fallback
                existing.source_type = classification.source_type
                updated += 1
            else:
                db.add(
                    ScholarshipEntry(
                        title=e.title,
                        provider=e.provider,
                        country=e.country,
                        degree_level=e.degree_level,
                        field_of_study=e.field_of_study,
                        deadline=e.deadline,
                        summary=e.summary,
                        source_url=e.source_url,
                        source_name=e.source_name,
                        credibility=e.credibility,
                        fetched_at=e.fetched_at or utcnow(),
                        is_fallback=e.is_fallback,
                        source_type=classification.source_type,
                    )
                )
                inserted += 1
    log.info(
        "Scholarships upserted: inserted=%d updated=%d (after clean+dedupe+classify)",
        inserted, updated,
    )
    return inserted, updated


def reclassify_all() -> dict[str, int]:
    """Re-run the source classifier over every ScholarshipEntry. Useful
    after updating classifier rules. Returns a count breakdown."""
    counts: dict[str, int] = {}
    with session_scope() as db:
        for row in db.scalars(select(ScholarshipEntry)):
            r = classify_source(
                title=row.title,
                summary=row.summary or "",
                source_url=row.source_url,
                source_name=row.source_name,
            )
            row.source_type = r.source_type
            counts[r.source_type] = counts.get(r.source_type, 0) + 1
    log.info("Reclassified all scholarships: %s", counts)
    return counts


# ---------- Admin review workflow (v0.9) -------------------------------


_VALID_REVIEW_STATUSES = frozenset({
    "pending_review", "approved", "rejected", "needs_attention",
})


def set_review_status(scholarship_id: int, status: str) -> bool:
    """Update a scholarship's review_status. Returns True if updated."""
    if status not in _VALID_REVIEW_STATUSES:
        raise ValueError(
            f"Invalid review_status {status!r}. "
            f"Must be one of {sorted(_VALID_REVIEW_STATUSES)}."
        )
    with session_scope() as db:
        row = db.get(ScholarshipEntry, scholarship_id)
        if row is None:
            return False
        row.review_status = status
        log.info(
            "Review status: scholarship=%s → %s", scholarship_id, status
        )
        return True


def list_by_review_status(
    status: str, *, limit: int = 200,
) -> list[ScholarshipDTO]:
    """List scholarships by review_status (admin-only)."""
    with session_scope() as db:
        rows = list(db.scalars(
            select(ScholarshipEntry)
            .where(ScholarshipEntry.review_status == status)
            .order_by(ScholarshipEntry.fetched_at.desc())
            .limit(limit)
        ))
        return [_to_dto(r) for r in rows]


def review_status_counts() -> dict[str, int]:
    """Count scholarships by review_status (NULL counted as 'approved')."""
    counts: dict[str, int] = {}
    with session_scope() as db:
        for row in db.scalars(select(ScholarshipEntry)):
            key = row.review_status or "approved"
            counts[key] = counts.get(key, 0) + 1
    return counts


# ---------- Bookmarks (saved list) ---------------------------------------


def save_bookmark(profile_id: int, scholarship_id: int) -> bool:
    with session_scope() as db:
        exists = db.scalar(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.scholarship_id == scholarship_id)
            )
        )
        if exists:
            return False
        db.add(SavedScholarship(
            profile_id=profile_id, scholarship_id=scholarship_id
        ))
        return True


def remove_bookmark(profile_id: int, scholarship_id: int) -> bool:
    with session_scope() as db:
        row = db.scalar(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.scholarship_id == scholarship_id)
            )
        )
        if not row:
            return False
        db.delete(row)
        return True


def list_bookmarks(profile_id: int) -> list[ScholarshipDTO]:
    with session_scope() as db:
        rows = list(db.scalars(
            select(SavedScholarship).where(
                SavedScholarship.profile_id == profile_id
            )
        ))
        return [_to_dto(b.scholarship) for b in rows]


def is_bookmarked(profile_id: int, scholarship_id: int) -> bool:
    with session_scope() as db:
        return db.scalar(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.scholarship_id == scholarship_id)
            )
        ) is not None


# ---------- Selection (v0.6) ---------------------------------------------


def set_selected_scholarship(profile_id: int, scholarship_id: int) -> bool:
    """Mark one scholarship as the selected target for a profile.
    Also saves it if it wasn't bookmarked. Returns True on success.

    v0.10: enforces that the scholarship must be approved (or NULL
    review_status for back-compat) AND user-visible per source_type.
    Selecting a rejected/pending/visa-page scholarship is rejected.
    """
    with session_scope() as db:
        # Ensure the scholarship exists AND is selectable.
        sch = db.get(ScholarshipEntry, scholarship_id)
        if sch is None:
            return False
        if not is_user_visible(sch.source_type):
            log.warning(
                "Refusing to select scholarship id=%s — source_type=%r "
                "is not user-visible.",
                scholarship_id, sch.source_type,
            )
            return False
        if sch.review_status not in (None, "approved"):
            log.warning(
                "Refusing to select scholarship id=%s — review_status=%r.",
                scholarship_id, sch.review_status,
            )
            return False

        # Clear prior selection for this profile
        for row in db.scalars(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.is_selected.is_(True))
            )
        ):
            row.is_selected = False

        # Find or create the saved row for this scholarship
        saved = db.scalar(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.scholarship_id == scholarship_id)
            )
        )
        if saved is None:
            saved = SavedScholarship(
                profile_id=profile_id,
                scholarship_id=scholarship_id,
                is_selected=True,
            )
            db.add(saved)
        else:
            saved.is_selected = True

        log.info(
            "Selected scholarship: profile=%s scholarship=%s",
            profile_id, scholarship_id,
        )
        return True


def clear_selected_scholarship(profile_id: int) -> None:
    with session_scope() as db:
        for row in db.scalars(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.is_selected.is_(True))
            )
        ):
            row.is_selected = False


def get_selected_scholarship(profile_id: int) -> Optional[ScholarshipDTO]:
    """Return the explicitly selected scholarship; fall back to the most
    recently saved one (back-compat with v0.5 journey logic)."""
    with session_scope() as db:
        selected = db.scalar(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.is_selected.is_(True))
            )
        )
        if selected is not None:
            return _to_dto(selected.scholarship)

        # Fallback: most recently saved
        fallback = db.scalars(
            select(SavedScholarship).where(
                SavedScholarship.profile_id == profile_id
            ).order_by(SavedScholarship.created_at.desc())
        ).first()
        if fallback is not None:
            return _to_dto(fallback.scholarship)
        return None


def is_selected(profile_id: int, scholarship_id: int) -> bool:
    with session_scope() as db:
        row = db.scalar(
            select(SavedScholarship).where(
                (SavedScholarship.profile_id == profile_id)
                & (SavedScholarship.scholarship_id == scholarship_id)
            )
        )
        return bool(row and row.is_selected)


# ---------- Matching (v0.6) ----------------------------------------------


def match_report_for(
    profile: UserProfile,
    scholarship: ScholarshipDTO | ScholarshipEntry,
) -> ScholarshipFitReport:
    """Public entry to the matching engine. Accepts either a DTO or an
    ORM row — the engine normalises."""
    if isinstance(scholarship, ScholarshipDTO):
        payload = {
            "id": scholarship.id,
            "country": scholarship.country,
            "degree_level": scholarship.degree_level,
            "field_of_study": scholarship.field_of_study,
            "eligibility": (
                scholarship.eligibility.model_dump()
                if scholarship.eligibility else None
            ),
        }
        return match_scholarship(profile, payload)
    return match_scholarship(profile, scholarship)


def list_with_match(
    profile: UserProfile,
    *,
    country: Optional[str] = None,
    degree_level: Optional[str] = None,
    field_of_study: Optional[str] = None,
    only_with_deadline: bool = False,
    hide_expired: bool = True,
    limit: int = 200,
) -> list[tuple[ScholarshipDTO, ScholarshipFitReport]]:
    """Return (DTO, FitReport) pairs, sorted by fit_score descending."""
    entries = list_scholarships(
        country=country,
        degree_level=degree_level,
        field_of_study=field_of_study,
        only_with_deadline=only_with_deadline,
        hide_expired=hide_expired,
        limit=limit,
    )
    scored = [
        (dto, match_report_for(profile, dto))
        for dto in entries
    ]
    scored.sort(key=lambda pair: pair[1].fit_score, reverse=True)
    return scored
