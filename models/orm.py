"""
models/orm.py
-------------
SQLAlchemy 2.0 ORM entities for VisaForge.

All persisted data goes through these entities. Schema is intentionally
simple and Postgres-compatible so migration later is a config change,
not a rewrite.

NOTE ON BACKWARD COMPATIBILITY (v0.2):
- `has_offer_letter` and `has_proof_of_funds` are kept for compatibility
  with older saved profiles. New code prefers `offer_letter_status` and
  `proof_of_funds_status`. The profile service keeps both in sync.
- `previous_field_of_study` is new.
- `field_of_study` stores a comma-separated list of selected fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from utils.helpers import utcnow


class Base(DeclarativeBase):
    pass


# ---------- User / Profile -------------------------------------------------


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Owner (nullable for v0.1/v0.2 profiles predating auth; v0.4 writes always set it)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nationality: Mapped[str] = mapped_column(String(80))
    country_of_residence: Mapped[str] = mapped_column(String(80))
    passport_valid_until: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # ISO YYYY-MM-DD
    previous_travel_history: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    education_level: Mapped[Optional[str]] = mapped_column(String(80))
    gpa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    english_test_type: Mapped[Optional[str]] = mapped_column(String(40))
    english_test_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    destination_country: Mapped[str] = mapped_column(String(40))
    intended_degree_level: Mapped[Optional[str]] = mapped_column(String(80))
    intended_institution_type: Mapped[Optional[str]] = mapped_column(String(80))

    # --- v0.1 legacy booleans (kept for backward compatibility) ---
    # New code reads *_status; these remain in sync via profile_service.
    has_offer_letter: Mapped[bool] = mapped_column(Boolean, default=False)
    has_proof_of_funds: Mapped[bool] = mapped_column(Boolean, default=False)
    has_dependents: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- v0.2 evidence-status fields ---
    offer_letter_status: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True
    )
    proof_of_funds_status: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True
    )

    # --- Study fields ---
    # `field_of_study` stored as comma-separated list of intended subjects.
    field_of_study: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_field_of_study: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )

    target_intake: Mapped[Optional[str]] = mapped_column(String(40))
    budget_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    eligibility_results: Mapped[list["EligibilityResult"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    route_plans: Mapped[list["RoutePlan"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    saved_scholarships: Mapped[list["SavedScholarship"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    documents: Mapped[list["CaseDocument"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


# ---------- Eligibility ----------------------------------------------------


class EligibilityResult(Base):
    __tablename__ = "eligibility_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"))
    country: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text, default="")
    trace_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profile: Mapped[UserProfile] = relationship(
        back_populates="eligibility_results"
    )


# ---------- Route / Workflow ----------------------------------------------


class RoutePlan(Base):
    __tablename__ = "route_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"))
    country: Mapped[str] = mapped_column(String(40))
    template_key: Mapped[str] = mapped_column(String(80))
    # v0.10: route plans are now scholarship-driven and user-scoped.
    # Both nullable for back-compat with v0.1 plans.
    scholarship_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("scholarship_entries.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    profile: Mapped[UserProfile] = relationship(back_populates="route_plans")
    steps: Mapped[list["RouteStep"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="RouteStep.order_index",
    )


class RouteStep(Base):
    __tablename__ = "route_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("route_plans.id"))
    order_index: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="locked")
    depends_on_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str] = mapped_column(Text, default="")
    # ---------- v0.10 additions ----------
    # Section grouping: "scholarship" | "pakistan" | "visa"
    section_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    # Where the step originates from: "scholarship" | "pakistan" | "visa"
    source: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # "high" | "medium" | "low" — informational priority for the UI
    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # JSON-encoded list of document keys this step needs.
    required_documents_json: Mapped[str] = mapped_column(Text, default="[]")
    # UI hints
    action_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    action_target: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    help_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # If this step is a Pakistan-policy process, its id (e.g. "hec_attestation").
    pakistan_process_id: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, index=True,
    )
    # v0.11: timestamp set by user_confirmation layer when user clicks
    # "Mark as Complete" on a step that is `ready_to_complete`. Once
    # set, the deterministic status overlay returns 'completed' for
    # this step regardless of upstream evidence changes — completion
    # is sticky because the user explicitly confirmed it.
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )

    plan: Mapped[RoutePlan] = relationship(back_populates="steps")


# ---------- Documents ------------------------------------------------------


class CaseDocument(Base):
    __tablename__ = "case_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"))
    country: Mapped[str] = mapped_column(String(40))
    doc_type: Mapped[str] = mapped_column(String(100))
    filename: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # ---------- v0.11 evidence verification additions ----------
    # User scope (nullable for back-compat with v0.4 rows).
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    # Route-step linkage. We use `step_key` (string FK to RouteStep.key)
    # rather than RouteStep.id so the document persists even if the
    # route plan is regenerated. Indexed for fast per-step lookup.
    step_key: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True, index=True
    )
    document_type: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True, index=True
    )
    # Original filename as uploaded (preserved separately from the
    # safe stored filename in `filename`).
    original_filename: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True
    )
    # Absolute or app-relative path to the stored file under
    # data/uploads/{profile_id}/{step_key}/.
    stored_path: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    mime_type: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True
    )
    file_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    # OCR / PDF-extracted plain text. Capped at ~32 KB at write time.
    extracted_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # JSON-encoded structured extraction (per document type).
    extracted_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # Result of services/document_verification_service. One of:
    # 'pending' | 'verified' | 'rejected' | 'needs_attention' |
    # 'extraction_failed'. Nullable for legacy rows; treated as
    # 'pending' for back-compat.
    verification_status: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, index=True
    )
    # JSON-encoded list of issue strings (e.g. "passport expires
    # before course end"). Empty list means no issues.
    issues_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # ---------- v0.12 extraction-pipeline visibility ----------
    # Which library/path produced the extracted_text? One of:
    # 'pymupdf' | 'pdfplumber' | 'pytesseract' | '' (none).
    # Nullable for back-compat with v0.11 rows.
    extraction_method: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True
    )
    # Outcome of the text-extraction stage. One of:
    # 'ok' | 'empty' | 'failed' | 'library_missing' |
    # 'tesseract_missing' | 'unsupported_type' | 'file_not_found' |
    # 'pending'. Distinct from `verification_status` so the UI can
    # tell "no text could be read" apart from "text was read but
    # verification flagged issues."
    extraction_status: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    # JSON-encoded list of error/diagnostic strings from the
    # extraction stage (e.g. "PyMuPDF failed: ...", "Tesseract
    # binary not found on PATH"). Empty list / null when extraction
    # succeeded cleanly.
    extraction_errors: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # JSON-encoded list of soft warnings from verification (e.g.
    # "Could not extract bank balance"). Distinct from `issues_json`
    # which holds harder problems. Empty list / null when no warnings.
    warnings_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # JSON-encoded list of profile field names whose values matched
    # the extracted fields (e.g. ["full_name", "nationality"]).
    matched_fields_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # Timestamp when verification last ran (verified or otherwise).
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    # v0.14 — manual confirmation path (spec §3, §4). When the
    # deterministic verifier sets verification_status to
    # 'manual_review_required', the user can click "Confirm this
    # document is correct" which flips verification_status to
    # 'user_confirmed' and records timestamps below. An admin can
    # do the same via the admin review page (MVP optional, spec §4).
    confirmed_by_user: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    confirmed_by_admin_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    # v0.16 (Phase 5.7): free-text note the user can add when they
    # click "I reviewed this document" — e.g. "translated by NOTAR".
    # Optional. Empty by default.
    confirmation_note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # v0.17 (Phase 5.8): OCR quality signal. Stored as a float in
    # [0.0, 1.0] and a human-readable label ("good" | "medium" | "weak").
    # Nullable for back-compat with pre-5.8 rows.
    ocr_quality_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    ocr_quality_label: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    profile: Mapped[UserProfile] = relationship(back_populates="documents")


# ---------- Scholarships ---------------------------------------------------


class ScholarshipSource(Base):
    __tablename__ = "scholarship_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500), unique=True)
    country: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(60))
    credibility: Mapped[str] = mapped_column(String(20), default="official")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    last_status: Mapped[str] = mapped_column(String(30), default="never_run")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ScholarshipEntry(Base):
    __tablename__ = "scholarship_entries"
    __table_args__ = (
        UniqueConstraint("source_url", "title", name="uq_source_title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(400))
    provider: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    country: Mapped[str] = mapped_column(String(40))
    degree_level: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    field_of_study: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    deadline: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(500))
    source_name: Mapped[Optional[str]] = mapped_column(String(200))
    credibility: Mapped[str] = mapped_column(String(20), default="official")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    # v0.6: structured eligibility block for the matching engine.
    eligibility_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # v0.8: deterministic source-type classification.
    source_type: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )
    # v0.9: admin review workflow.
    # One of: 'pending_review', 'approved', 'rejected', 'needs_attention'.
    # Nullable for legacy rows; treated as 'approved' for back-compat.
    review_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True, default="pending_review"
    )
    # v0.9: structured extracted-payload JSON (full v0.9 extraction
    # output: title, eligible_nationalities, pakistan_eligible,
    # required_documents, etc.). Separate from `eligibility_json`
    # which holds only the matching-engine-readable subset.
    extracted_payload_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    # v0.9: monotonically increasing version number per (source_url,title).
    # Each refresh that detects changes increments this.
    version: Mapped[int] = mapped_column(Integer, default=1)
    # v0.9: link back to the curated source that produced this row, if any.
    curated_source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("curated_sources.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )


class SavedScholarship(Base):
    __tablename__ = "saved_scholarships"
    __table_args__ = (
        UniqueConstraint("profile_id", "scholarship_id", name="uq_profile_schol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"))
    scholarship_id: Mapped[int] = mapped_column(
        ForeignKey("scholarship_entries.id")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # v0.6: exactly one saved scholarship per profile can be "selected" as
    # the target. Enforced by the service layer (see scholarship_service).
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profile: Mapped[UserProfile] = relationship(
        back_populates="saved_scholarships"
    )
    scholarship: Mapped[ScholarshipEntry] = relationship()


# ---------- Curated source registry (v0.9) ---------------------------------


class CuratedSource(Base):
    """v0.9 curated source registry.

    Each row is an approved root for the controlled refresh system. The
    fields drive the crawl orchestrator: only links inside
    `allowed_domains` whose anchor or URL contains a `follow_keyword`
    (and no `block_keywords`) are followed, bounded by `max_depth`.

    JSON-list fields are stored as Text (JSON-encoded) for SQLite
    portability — no SQLite ARRAY type. Service-layer accessors decode
    these on read.
    """
    __tablename__ = "curated_sources"
    __table_args__ = (
        UniqueConstraint("name", "destination_country",
                         name="uq_curated_name_country"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    destination_country: Mapped[str] = mapped_column(String(60), index=True)
    base_url: Mapped[str] = mapped_column(String(500))

    # JSON-encoded lists (string[]). Decoded by the service layer.
    start_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    allowed_domains_json: Mapped[str] = mapped_column(Text, default="[]")
    follow_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    block_keywords_json: Mapped[str] = mapped_column(Text, default="[]")

    max_depth: Mapped[int] = mapped_column(Integer, default=2)
    source_type: Mapped[str] = mapped_column(
        String(40), default="scholarship_program"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_admin_review: Mapped[bool] = mapped_column(Boolean, default=True)

    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


# ---------- Ingestion logs -------------------------------------------------


class FetchLog(Base):
    __tablename__ = "fetch_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30))
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
