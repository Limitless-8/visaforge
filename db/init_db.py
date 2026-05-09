"""
db/init_db.py
-------------
Bootstraps the schema and seeds:
- users table (v0.4)
- scholarship sources (from source_registry.json)
- demo scholarships (from seed_scholarships.json) so the app works offline.
- initial admin user from ADMIN_EMAIL / ADMIN_PASSWORD if configured

Also performs lightweight additive migrations for v0.2 + v0.4 columns on
user_profiles so existing databases keep working without a full reset.

Idempotent: safe to call on every app start.
"""

from __future__ import annotations

from sqlalchemy import inspect, select, text

from config.settings import SEEDS_DIR
from db.database import get_engine, session_scope
from models.orm import (
    Base,
    ScholarshipEntry,
    ScholarshipSource,
    UserProfile,
)
# Import user to ensure the table is registered in Base.metadata
from models.user import User  # noqa: F401
from utils.helpers import safe_load_json, utcnow
from utils.logger import get_logger

log = get_logger(__name__)


# --- v0.2 + v0.4 additive migration --------------------------------------

# (column_name, DDL type) — all nullable / default-able so adding them
# to an existing table is safe.
_USER_PROFILE_COLUMNS: list[tuple[str, str]] = [
    # v0.2
    ("offer_letter_status", "VARCHAR(60)"),
    ("proof_of_funds_status", "VARCHAR(60)"),
    ("previous_field_of_study", "VARCHAR(120)"),
    # v0.4
    ("user_id", "INTEGER"),
]

# v0.6: additive migrations for scholarship tables.
_SCHOLARSHIP_ENTRY_COLUMNS: list[tuple[str, str]] = [
    ("eligibility_json", "TEXT"),
    # v0.8: source_type classification
    ("source_type", "VARCHAR(40)"),
    # v0.9: review workflow + extraction + versioning
    ("review_status", "VARCHAR(20)"),
    ("extracted_payload_json", "TEXT"),
    ("version", "INTEGER DEFAULT 1"),
    ("curated_source_id", "INTEGER"),
]

# v0.10: route plans become scholarship-driven.
_ROUTE_PLAN_COLUMNS: list[tuple[str, str]] = [
    ("scholarship_id", "INTEGER"),
    ("user_id", "INTEGER"),
]

# v0.10: route steps gain section + source + UI hint columns.
_ROUTE_STEP_COLUMNS: list[tuple[str, str]] = [
    ("section_id", "VARCHAR(40)"),
    ("source", "VARCHAR(40)"),
    ("priority", "VARCHAR(20)"),
    ("required_documents_json", "TEXT DEFAULT '[]'"),
    ("action_label", "VARCHAR(80)"),
    ("action_target", "VARCHAR(120)"),
    ("help_text", "TEXT"),
    ("pakistan_process_id", "VARCHAR(60)"),
    # v0.11: completion timestamp set when user clicks Mark as Complete.
    ("completed_at", "DATETIME"),
]

# v0.11: case_documents gains evidence-verification columns.
# v0.12: case_documents gains extraction-pipeline visibility columns.
_CASE_DOCUMENT_COLUMNS: list[tuple[str, str]] = [
    ("user_id", "INTEGER"),
    ("step_key", "VARCHAR(80)"),
    ("document_type", "VARCHAR(60)"),
    ("original_filename", "VARCHAR(300)"),
    ("stored_path", "VARCHAR(500)"),
    ("mime_type", "VARCHAR(80)"),
    ("file_size", "INTEGER"),
    ("extracted_text", "TEXT"),
    ("extracted_json", "TEXT"),
    ("verification_status", "VARCHAR(30)"),
    ("issues_json", "TEXT"),
    ("updated_at", "DATETIME"),
    # v0.12 extraction-pipeline visibility
    ("extraction_method", "VARCHAR(40)"),
    ("extraction_status", "VARCHAR(40)"),
    ("extraction_errors", "TEXT"),
    ("warnings_json", "TEXT"),
    ("matched_fields_json", "TEXT"),
    ("verified_at", "DATETIME"),
    # v0.14 manual confirmation path. NOT NULL omitted from the
    # migration because SQLite's ALTER TABLE ADD COLUMN does honor
    # DEFAULT 0 for existing rows, but if a partial v0.14 deployment
    # had inserted NULL into this column on some installs, requiring
    # NOT NULL retroactively would fail. The SQLAlchemy mapping still
    # declares NOT NULL on the model, which guards new writes; the DB
    # column itself is left as nullable-with-default for safety.
    ("confirmed_by_user", "BOOLEAN DEFAULT 0"),
    ("confirmed_at", "DATETIME"),
    ("confirmed_by_admin_id", "INTEGER"),
    # v0.16 (Phase 5.7) — optional free-text note the user can add
    # when they self-review a document.
    ("confirmation_note", "TEXT"),
    # v0.17 (Phase 5.8) — OCR quality signal
    ("ocr_quality_score", "REAL"),
    ("ocr_quality_label", "VARCHAR(20)"),
]
_SAVED_SCHOLARSHIP_COLUMNS: list[tuple[str, str]] = [
    ("is_selected", "BOOLEAN DEFAULT 0"),
]


def _migrate_user_profiles(engine) -> None:
    """Add missing columns to `user_profiles` if they are absent."""
    _apply_additive_migration(engine, "user_profiles", _USER_PROFILE_COLUMNS)


def _migrate_scholarship_tables(engine) -> None:
    _apply_additive_migration(
        engine, "scholarship_entries", _SCHOLARSHIP_ENTRY_COLUMNS
    )
    _apply_additive_migration(
        engine, "saved_scholarships", _SAVED_SCHOLARSHIP_COLUMNS
    )


def _migrate_route_tables(engine) -> None:
    """v0.10: route plans become scholarship-driven; route steps gain
    section/source/priority and UI hint columns. v0.11: route steps
    gain `completed_at`, case_documents gains evidence columns."""
    _apply_additive_migration(engine, "route_plans", _ROUTE_PLAN_COLUMNS)
    _apply_additive_migration(engine, "route_steps", _ROUTE_STEP_COLUMNS)
    _apply_additive_migration(engine, "case_documents", _CASE_DOCUMENT_COLUMNS)


def _apply_additive_migration(
    engine, table: str, cols: list[tuple[str, str]]
) -> None:
    """Add any missing nullable columns. Safe on SQLite and Postgres."""
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns(table)}
    with engine.begin() as conn:
        for col_name, col_type in cols:
            if col_name in existing:
                continue
            log.info("Migrating: adding %s.%s", table, col_name)
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            )


def _backfill_status_from_booleans() -> int:
    """For profiles that predate v0.2, populate *_status from the old booleans."""
    updated = 0
    with session_scope() as db:
        for p in db.scalars(select(UserProfile)):
            changed = False
            if not p.offer_letter_status:
                p.offer_letter_status = (
                    "Unconditional offer received"
                    if p.has_offer_letter
                    else "Not yet applied"
                )
                changed = True
            if not p.proof_of_funds_status:
                p.proof_of_funds_status = (
                    "Fully prepared"
                    if p.has_proof_of_funds
                    else "Not prepared"
                )
                changed = True
            if changed:
                updated += 1
    if updated:
        log.info("Backfilled status fields on %d legacy profile(s).", updated)
    return updated


# --- Schema + seeds -------------------------------------------------------


def create_tables() -> None:
    engine = get_engine()
    # Step 1: create missing tables (fresh DBs)
    Base.metadata.create_all(engine)
    # Step 2: additive migrations for existing DBs
    _migrate_user_profiles(engine)
    _migrate_scholarship_tables(engine)
    _migrate_route_tables(engine)
    # Step 3: backfill derived values
    _backfill_status_from_booleans()
    log.info("Database tables ensured.")


def seed_sources() -> int:
    """Load the curated source registry into the DB if not already present."""
    registry = safe_load_json(SEEDS_DIR / "source_registry.json") or {}
    sources = registry.get("sources", [])
    inserted = 0

    with session_scope() as db:
        for s in sources:
            url = s.get("url")
            if not url:
                continue
            exists = db.scalar(
                select(ScholarshipSource).where(ScholarshipSource.url == url)
            )
            if exists:
                continue
            db.add(
                ScholarshipSource(
                    name=s["name"],
                    url=url,
                    country=s["country"],
                    category=s.get("category", "scholarship"),
                    credibility=s.get("credibility", "official"),
                    active=s.get("active", True),
                )
            )
            inserted += 1
    if inserted:
        log.info("Seeded %d scholarship sources.", inserted)
    return inserted


def seed_demo_scholarships() -> int:
    """Load offline-safe demo scholarships so the app always has content.

    Also runs the deterministic source classifier (v0.8) so every row —
    new or existing — gets a non-null `source_type`. Existing rows are
    only re-classified if their source_type is NULL, so admin overrides
    are preserved.
    """
    import json as _json
    from services.source_classifier import classify_source

    data = safe_load_json(SEEDS_DIR / "seed_scholarships.json") or {}
    entries = data.get("entries", [])
    inserted = 0
    backfilled_eligibility = 0
    backfilled_source_type = 0

    with session_scope() as db:
        for e in entries:
            title = e.get("title")
            source_url = e.get("source_url")
            if not title or not source_url:
                continue

            elig_blob = e.get("eligibility")
            elig_json = _json.dumps(elig_blob) if elig_blob else None

            classification = classify_source(
                title=title,
                summary=e.get("summary", ""),
                source_url=source_url,
                source_name=e.get("source_name"),
            )

            existing = db.scalar(
                select(ScholarshipEntry).where(
                    (ScholarshipEntry.title == title)
                    & (ScholarshipEntry.source_url == source_url)
                )
            )
            if existing is not None:
                if elig_json and not existing.eligibility_json:
                    existing.eligibility_json = elig_json
                    backfilled_eligibility += 1
                if not existing.source_type:
                    existing.source_type = classification.source_type
                    backfilled_source_type += 1
                continue

            db.add(
                ScholarshipEntry(
                    title=title,
                    provider=e.get("provider"),
                    country=e.get("country", "UK"),
                    degree_level=e.get("degree_level"),
                    field_of_study=e.get("field_of_study"),
                    deadline=e.get("deadline"),
                    summary=e.get("summary", ""),
                    source_url=source_url,
                    source_name=e.get("source_name"),
                    credibility=e.get("credibility", "official"),
                    fetched_at=utcnow(),
                    is_fallback=False,
                    eligibility_json=elig_json,
                    source_type=classification.source_type,
                )
            )
            inserted += 1

        # ---- Backfill any existing rows (scraped or older seeds) that
        # have a NULL source_type. ---
        unclassified = list(db.scalars(
            select(ScholarshipEntry).where(
                ScholarshipEntry.source_type.is_(None)
            )
        ))
        for row in unclassified:
            classification = classify_source(
                title=row.title,
                summary=row.summary or "",
                source_url=row.source_url,
                source_name=row.source_name,
            )
            row.source_type = classification.source_type
            backfilled_source_type += 1

    if inserted or backfilled_eligibility or backfilled_source_type:
        log.info(
            "Seeded %d demo scholarships; "
            "backfilled eligibility on %d, source_type on %d.",
            inserted, backfilled_eligibility, backfilled_source_type,
        )
    return inserted


def seed_admin() -> None:
    """Seed the initial admin from env/secrets if configured."""
    # Local import to avoid a circular dependency at module load time.
    from services.auth_service import seed_admin_from_env
    try:
        seed_admin_from_env()
    except Exception:
        log.exception("Admin seeding failed (non-fatal).")


def seed_curated_sources() -> int:
    """v0.9: load the curated source registry from JSON."""
    # Local import keeps the module load order safe.
    from services.source_registry_service import seed_from_json
    try:
        return seed_from_json()
    except Exception:
        log.exception("Curated source seeding failed (non-fatal).")
        return 0


def backfill_review_status() -> int:
    """v0.9: legacy ScholarshipEntry rows have NULL review_status. The
    spec says 'only approved records appear to users'. To avoid silently
    hiding our well-known seed scholarships, mark them approved on the
    first run; admin can change later. Pre-existing scraped rows that
    look like noise (source_type in the hidden set) are marked
    rejected so they stay out of the user view by default."""
    from sqlalchemy import select as _sel
    HIDDEN = {"visa_policy_page", "generic_education_page",
              "invalid_or_noise"}
    touched = 0
    with session_scope() as db:
        for row in db.scalars(_sel(ScholarshipEntry).where(
            ScholarshipEntry.review_status.is_(None)
        )):
            if row.source_type in HIDDEN:
                row.review_status = "rejected"
            else:
                row.review_status = "approved"
            touched += 1
    if touched:
        log.info("Backfilled review_status on %d legacy row(s).", touched)
    return touched


def initialize() -> None:
    """One-shot init: tables + migrations + seed data + admin."""
    create_tables()
    seed_sources()
    seed_curated_sources()
    seed_demo_scholarships()
    backfill_review_status()
    seed_admin()


if __name__ == "__main__":
    initialize()
    print("VisaForge DB initialised.")
