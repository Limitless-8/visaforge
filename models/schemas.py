"""
models/schemas.py
-----------------
Pydantic models used for validated in-memory structures and for
serializing results into the UI / LLM context.

v0.3 — Eligibility engine upgrade:
  * RuleEvaluation gains: priority, category, why_it_matters,
    what_to_do, estimated_time.
  * EligibilityReport gains: decision, confidence_breakdown,
    blocking_issues, important_gaps, risk_flags, weakest_area,
    timeline_plan, next_steps.
  * Legacy fields (status, trace, missing_evidence) remain so
    older saved reports still render.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator


# Legacy status — kept for DB/back-compat
EligibilityStatus = Literal["eligible", "partial", "not_eligible"]

# New decision state
EligibilityDecision = Literal[
    "ELIGIBLE",
    "CONDITIONALLY_ELIGIBLE",
    "HIGH_RISK",
    "NOT_ELIGIBLE",
]

RuleOutcome = Literal["passed", "failed", "missing_evidence", "warning"]
RulePriority = Literal["CRITICAL", "IMPORTANT", "OPTIONAL"]
RuleCategory = Literal[
    "documents", "financial", "academic", "language", "other"
]
StepStatus = Literal[
    "locked", "available", "completed", "blocked", "pending_evidence"
]


class ProfileIn(BaseModel):
    """User-submitted profile (intake form)."""

    full_name: str
    age: Optional[int] = None
    nationality: str
    country_of_residence: str
    passport_valid_until: Optional[str] = None
    previous_travel_history: Optional[str] = None

    education_level: Optional[str] = None
    gpa: Optional[float] = None
    english_test_type: Optional[str] = None
    english_test_score: Optional[float] = None

    destination_country: str
    intended_degree_level: Optional[str] = None
    intended_institution_type: Optional[str] = None

    offer_letter_status: Optional[str] = None
    proof_of_funds_status: Optional[str] = None

    has_offer_letter: bool = False
    has_proof_of_funds: bool = False
    has_dependents: bool = False

    field_of_study: Optional[str] = None
    previous_field_of_study: Optional[str] = None

    target_intake: Optional[str] = None
    budget_notes: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("field_of_study", mode="before")
    @classmethod
    def _normalize_field_of_study(cls, v: Any) -> Optional[str]:
        if v is None or v == "":
            return None
        if isinstance(v, (list, tuple, set)):
            items = [str(x).strip() for x in v if str(x).strip()]
            return ", ".join(items) if items else None
        return str(v).strip() or None


# ---------- Eligibility engine output ------------------------------------


class RuleEvaluation(BaseModel):
    """One rule's evaluation outcome — used for the audit trace."""

    rule_id: str
    description: str
    outcome: RuleOutcome
    detail: str = ""
    evidence_required: list[str] = Field(default_factory=list)

    # v0.3 additions (all optional so older rule files keep working)
    priority: RulePriority = "IMPORTANT"
    category: RuleCategory = "other"
    why_it_matters: Optional[str] = None
    what_to_do: Optional[str] = None
    estimated_time: Optional[str] = None


class NextStep(BaseModel):
    """An actionable recommendation surfaced from a failed/partial rule."""

    rule_id: str
    title: str                 # e.g. "Secure UK CAS"
    priority: RulePriority
    what_to_do: str
    why_it_matters: str
    estimated_time: Optional[str] = None


class TimelineItem(BaseModel):
    """A single item on the suggested backward-planned timeline."""

    step: str
    recommended_by: str        # human-readable window, e.g. "March 2027"
    category: RuleCategory = "other"
    notes: Optional[str] = None


class ConfidenceBreakdown(BaseModel):
    documents: int = Field(ge=0, le=100, default=0)
    financial: int = Field(ge=0, le=100, default=0)
    academic: int = Field(ge=0, le=100, default=0)
    language: int = Field(ge=0, le=100, default=0)


class EligibilityReport(BaseModel):
    """Output of the deterministic eligibility engine."""

    # --- v0.1 legacy fields (kept for storage + back-compat) -----------
    country: str
    status: EligibilityStatus
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    trace: list[RuleEvaluation]
    missing_evidence: list[str] = Field(default_factory=list)
    evaluated_at: datetime

    # --- v0.3 enriched fields ------------------------------------------
    decision: EligibilityDecision = "NOT_ELIGIBLE"
    confidence_breakdown: ConfidenceBreakdown = Field(
        default_factory=ConfidenceBreakdown
    )
    blocking_issues: list[str] = Field(default_factory=list)
    important_gaps: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    weakest_area: Optional[str] = None
    next_steps: list[NextStep] = Field(default_factory=list)
    timeline_plan: list[TimelineItem] = Field(default_factory=list)


class RouteStepDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    title: str
    description: str = ""
    status: StepStatus = "locked"
    depends_on: list[str] = Field(default_factory=list)
    notes: str = ""


class RoutePlanDTO(BaseModel):
    country: str
    template_key: str
    steps: list[RouteStepDTO]


class ScholarshipEligibility(BaseModel):
    """Structured eligibility criteria attached to a scholarship. All
    fields optional — missing criteria score conservatively as Unknown
    by the matching engine."""
    model_config = ConfigDict(extra="allow")

    destination_country: Optional[str] = None
    # `eligible_nationalities`: list[str] | "any" | named group key
    eligible_nationalities: Optional[Any] = None
    excluded_nationalities: list[str] = Field(default_factory=list)
    degree_levels: Optional[list[str]] = None
    # `fields_of_study`: list[str] | "any"
    fields_of_study: Optional[Any] = None
    min_gpa_4: Optional[float] = None
    min_ielts: Optional[float] = None
    requires_offer: Optional[bool] = None
    requires_funds: Optional[bool] = None
    min_work_experience_years: Optional[int] = None
    notes: Optional[str] = None


class ScholarshipDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    provider: Optional[str] = None
    country: str
    degree_level: Optional[str] = None
    field_of_study: Optional[str] = None
    deadline: Optional[str] = None
    summary: str = ""
    source_url: str
    source_name: Optional[str] = None
    credibility: Literal[
        "official", "institutional", "informational"
    ] = "official"
    fetched_at: Optional[datetime] = None
    is_fallback: bool = False
    eligibility: Optional[ScholarshipEligibility] = None
    source_type: Optional[str] = None
    classification_reasons: list[str] = Field(default_factory=list)
    # v0.9: review workflow + extraction
    review_status: Optional[str] = None
    version: int = 1
    extracted_payload: Optional[dict] = None
    curated_source_id: Optional[int] = None


# ---------- Scholarship matching engine (v0.6) ----------------------------

MatchStatus = Literal[
    "strong_match",
    "possible_match",
    "weak_match",
    "not_eligible",
]

CriterionStrength = Literal["pass", "partial", "unknown", "fail"]


class CriterionResult(BaseModel):
    """One criterion's evaluation — used for the transparent fit trace."""
    key: str                       # e.g. "nationality"
    label: str                     # human label
    weight: float                  # 0.0–1.0 weight of this criterion
    earned: float                  # 0.0–weight portion earned
    strength: CriterionStrength
    detail: str = ""


class ScholarshipFitReport(BaseModel):
    """Deterministic match result for a single (profile, scholarship)."""
    scholarship_id: int
    fit_score: int = Field(ge=0, le=100)
    match_status: MatchStatus
    matched_criteria: list[str] = Field(default_factory=list)
    missing_criteria: list[str] = Field(default_factory=list)
    unknown_criteria: list[str] = Field(default_factory=list)
    improvement_advice: list[str] = Field(default_factory=list)
    trace: list[CriterionResult] = Field(default_factory=list)


# ---------- Curated source registry (v0.9) -------------------------------


ReviewStatus = Literal[
    "pending_review", "approved", "rejected", "needs_attention"
]


class CuratedSourceDTO(BaseModel):
    """Public-shape dict for one curated crawl root."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    name: str
    provider: Optional[str] = None
    destination_country: str
    base_url: str
    start_urls: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    follow_keywords: list[str] = Field(default_factory=list)
    block_keywords: list[str] = Field(default_factory=list)
    max_depth: int = 2
    source_type: str = "scholarship_program"
    is_active: bool = True
    requires_admin_review: bool = True
    last_refreshed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------- Route plan v0.10 ---------------------------------------------
#
# New "dynamic, scholarship-driven" route plan shape. Lives alongside
# the v0.1 RouteStepDTO / RoutePlanDTO (used by the legacy generic
# route_service); the new shape is consumed by route_plan_service.


RouteStepStatus = Literal[
    # v0.15 simplification (Phase 5.6 pivot): Route Plan steps have
    # exactly four lifecycle states. Document upload no longer drives
    # any step status. The user clicks "Mark as Complete" once
    # dependencies are met.
    "locked",     # one or more dependency steps are not yet complete
    "available",  # ready for user to act on / mark complete
    "completed",  # user has marked complete
    "blocked",    # hard gate (e.g. NOT_ELIGIBLE — only the visa phase)
    # ---------- Legacy values, kept ONLY for back-compat with v0.11–
    # v0.14 persisted RouteStep rows. The Phase-5.6 pipeline never
    # produces these. On read, `_resolve_dependencies` /
    # `recompute_states_for_plan` upgrade any of these to the
    # appropriate v0.15 value (typically `available`).
    "pending", "in_progress",
    "awaiting_documents", "pending_verification",
    "pending_user_confirmation",
    "needs_attention", "ready_to_complete",
]
RouteStepSource = Literal["scholarship", "pakistan", "visa"]
RouteStepPriority = Literal["high", "medium", "low"]
SectionId = Literal["scholarship", "pakistan", "visa"]


# ---------- Document evidence (v0.11) ----------------------------------

# v0.14 — verification status literal extended for manual review +
# user/admin confirmation paths. Spec §5: when deterministic verifiers
# cannot prove authenticity (Pakistan attestations, NADRA documents),
# `manual_review_required` is the parking state; the user can then
# click "Confirm this document is correct" to move to `user_confirmed`,
# which counts as evidence-satisfied alongside `verified` for step
# completion purposes (spec §6).
VerificationStatus = Literal[
    "pending",                 # waiting for verification to run
    "verified",                # system-verified
    "user_confirmed",          # user manually confirmed (not auto-verified)
    "admin_verified",          # admin reviewed and approved (optional)
    "manual_review_required",  # OCR succeeded but verifier can't auto-confirm
    "needs_attention",         # verifier flagged real issues
    "needs_review",            # v0.17 alias for manual_review_required (UI-facing)
    "processed",               # v0.17 advisory-processed (all fields found)
    "processed_with_warnings", # v0.17 processed but with soft warnings
    "rejected",                # explicit rejection
    "extraction_failed",       # text extraction couldn't run
    "could_not_read",          # v0.17 alias for extraction_failed (UI-facing)
    "weak_ocr",                # v0.17 OCR ran but quality was low
]

# v0.14 — set of statuses that count as evidence-satisfied for the
# purposes of step completion. Both deterministic verification and
# explicit user/admin confirmation count. Imported by
# route_plan_service.evidence overlay + can_complete_step.
EVIDENCE_SATISFIED_STATUSES: frozenset[str] = frozenset({
    "verified", "user_confirmed", "admin_verified",
})


class RequiredDocument(BaseModel):
    """Canonical description of one document slot that an evidence step
    expects.

    v0.13 spec §2: every UI / service consumer must use the same
    `resolve_required_documents(step)` helper, which returns a list of
    these. Identifies the document by `document_type` (the value used
    by the extractor + verification service) and renders with a
    user-friendly `label`.
    """
    model_config = ConfigDict(from_attributes=True)

    document_type: str       # e.g. "passport", "hec_attestation"
    label: str               # e.g. "Passport scan"
    help_text: Optional[str] = None
    optional: bool = False   # If True, missing doc still allows
                             # ready_to_complete (e.g. "Sponsor letter
                             # if sponsored")


class DocumentEvidenceDTO(BaseModel):
    """One uploaded document attached to a route step."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    profile_id: int
    user_id: Optional[int] = None
    step_key: Optional[str] = None
    document_type: Optional[str] = None
    original_filename: Optional[str] = None
    stored_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    extracted_text: Optional[str] = None
    extracted_fields: dict = Field(default_factory=dict)
    verification_status: VerificationStatus = "pending"
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    matched_fields: list[str] = Field(default_factory=list)
    # v0.12 extraction-pipeline visibility (spec §10)
    extraction_method: Optional[str] = None
    extraction_status: Optional[str] = None
    extraction_errors: list[str] = Field(default_factory=list)
    # v0.17 (Phase 5.8) — OCR quality signal
    ocr_quality_score: Optional[float] = None
    ocr_quality_label: Optional[str] = None  # "good" | "medium" | "weak"
    # v0.14 — user / admin confirmation path (spec §3, §4)
    confirmed_by_user: bool = False
    confirmed_at: Optional[datetime] = None
    confirmed_by_admin_id: Optional[int] = None
    # v0.16 (Phase 5.7) — optional free-text note the user typed when
    # they clicked "I reviewed this document".
    confirmation_note: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VerificationResult(BaseModel):
    """Output of services/document_verification_service."""
    verification_status: VerificationStatus
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    matched_fields: list[str] = Field(default_factory=list)
    ready_for_completion: bool = False


class DynamicRouteStepDTO(BaseModel):
    """One step in a v0.10 dynamic route plan, with v0.11 evidence."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    key: str
    title: str
    description: str = ""
    status: RouteStepStatus = "locked"
    depends_on: list[str] = Field(default_factory=list)
    source: RouteStepSource = "scholarship"
    priority: RouteStepPriority = "medium"
    required_documents: list[str] = Field(default_factory=list)
    action_label: Optional[str] = None
    action_target: Optional[str] = None
    help_text: Optional[str] = None
    pakistan_process_id: Optional[str] = None
    order_index: int = 0
    section_id: SectionId = "scholarship"
    # Diagnostic — why is this step in its current status?
    status_reason: Optional[str] = None
    # v0.11: documents the user has uploaded against this step.
    evidence: list[DocumentEvidenceDTO] = Field(default_factory=list)
    # v0.11: True iff this step has required_documents (an "evidence
    # task"); False for soft tasks like "Prepare essays". Soft tasks
    # can be marked complete once dependencies clear.
    is_evidence_task: bool = False


class RouteSectionDTO(BaseModel):
    """A grouped section of route steps (A: scholarship, B: pakistan,
    C: visa)."""
    section_id: SectionId
    title: str
    description: str = ""
    progress_pct: int = Field(default=0, ge=0, le=100)
    steps: list[DynamicRouteStepDTO] = Field(default_factory=list)


class DynamicRoutePlanDTO(BaseModel):
    """Full computed route plan."""
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    profile_id: int
    user_id: Optional[int] = None
    scholarship_id: Optional[int] = None
    destination_country: str
    template_key: str
    sections: list[RouteSectionDTO] = Field(default_factory=list)
    overall_progress_pct: int = Field(default=0, ge=0, le=100)
    blocked_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ExtractedScholarship(BaseModel):
    """Structured extraction output from one or more crawled pages.

    Every field that wasn't found in the source is the literal string
    "unknown" rather than None — this keeps the matching engine and
    UI from confusing 'data wasn't reported' with 'data is empty'.
    Numeric fields use None to mean unknown (Pydantic-friendly).
    """
    model_config = ConfigDict(extra="allow")

    title: str
    provider: str = "unknown"
    destination_country: str = "unknown"
    eligible_nationalities: Any = "unknown"
    pakistan_eligible: Any = "unknown"   # bool | "unknown"
    degree_levels: Any = "unknown"
    fields_of_study: Any = "unknown"
    minimum_gpa: Optional[float] = None
    english_requirement: str = "unknown"
    work_experience_requirement: str = "unknown"
    offer_required: Any = "unknown"      # bool | "unknown"
    funding_type: str = "unknown"
    benefits: list[str] = Field(default_factory=list)
    deadline: str = "unknown"
    application_open_date: str = "unknown"
    application_process: str = "unknown"
    required_documents: list[str] = Field(default_factory=list)
    official_links: list[str] = Field(default_factory=list)
    source_urls_used: list[str] = Field(default_factory=list)
    extracted_summary: str = ""
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    review_status: ReviewStatus = "pending_review"


class SourceConfig(BaseModel):
    name: str
    url: str
    country: str
    category: str
    credibility: Literal[
        "official", "institutional", "informational"
    ] = "official"
    notes: Optional[str] = None


class IngestionResult(BaseModel):
    source_url: str
    success: bool
    raw_text: str = ""
    entries: list[ScholarshipDTO] = Field(default_factory=list)
    error: Optional[str] = None
    provider: str = "unknown"
    duration_ms: int = 0


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
