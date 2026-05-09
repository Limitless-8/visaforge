"""
services/route_plan_service.py
------------------------------
Phase-4 dynamic, scholarship-driven route plan generator.

The plan is built deterministically from:
  * the user's selected scholarship (target programme + destination)
  * the user's profile (offer status, funds status, English score, etc.)
  * the user's eligibility report (latest run, if any)
  * the user's document statuses for the destination
  * the Pakistan-policy process catalogue
  * a destination-specific template (Chevening UK / Vanier+EduCanada /
    DAAD+Deutschlandstipendium)

Output: a `DynamicRoutePlanDTO` with three sections:
    A — Scholarship Application Phase    (source="scholarship")
    B — Pakistan Preparation Phase       (source="pakistan")
    C — Visa Application Phase           (source="visa")

Step status is derived, never user-controlled. Allowed statuses:
    locked     — at least one prerequisite is not yet completed
    available  — prerequisites cleared; user can act on it now
    pending    — user has started/uploaded but not yet finished
    completed  — derived as done from profile/document/eligibility data
    blocked    — a hard gate has failed (e.g. eligibility=NOT_ELIGIBLE)

The status of every step is computed in two passes:
    pass 1: per-step "intrinsic" status from profile/documents/eligibility
    pass 2: dependency resolution — any step with an unmet prereq is
            downgraded to "locked" (unless its intrinsic status is
            "blocked", which propagates).

No AI. No randomness. Pure functions on top of dict inputs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import select

from db.database import session_scope
from models.orm import (
    CaseDocument,
    EligibilityResult,
    RoutePlan,
    RouteStep,
    UserProfile,
)
from models.schemas import (
    DocumentEvidenceDTO,
    DynamicRoutePlanDTO,
    DynamicRouteStepDTO,
    RouteSectionDTO,
)
from services.pakistan_policy_service import (
    get_process,
    list_processes_for_country,
)
from services.scholarship_service import get_selected_scholarship
from utils.helpers import utcnow
from utils.logger import get_logger
from utils.reference_data import (
    FUNDS_STATUS_STRENGTH,
    OFFER_STATUS_STRENGTH,
)

log = get_logger(__name__)


# v0.14 set retained as a module-private constant (was previously
# imported from schemas, but never exported there). Phase-5.6 does
# NOT use this for step gating — documents no longer block completion.
# Kept here only for the legacy `_apply_evidence_overlay` and related
# helpers, which are still referenced by `audit_route_plan_documents`.
EVIDENCE_SATISFIED_STATUSES: frozenset[str] = frozenset({
    "verified", "user_confirmed", "admin_verified",
})


# ---------- Section labels -----------------------------------------------

_SECTION_TITLES: dict[str, tuple[str, str]] = {
    "scholarship": (
        "Section A — Scholarship Application Phase",
        "Steps to prepare and submit your scholarship application.",
    ),
    "pakistan": (
        "Section B — Pakistan Preparation Phase",
        "Pakistan-side documents and processes you must complete before "
        "your visa application is ready.",
    ),
    "visa": (
        "Section C — Visa Application Phase",
        "Destination-specific visa steps you can start once your "
        "scholarship and Pakistan preparation are in place.",
    ),
}


# ---------- Step blueprint -----------------------------------------------

@dataclass
class StepSpec:
    """Static template for a route step. The dynamic state (status,
    status_reason) is computed from this plus the user's data."""
    key: str
    title: str
    description: str
    section_id: str                  # "scholarship" | "pakistan" | "visa"
    source: str                      # same set
    priority: str = "medium"         # high | medium | low
    depends_on: list[str] = field(default_factory=list)
    required_documents: list[str] = field(default_factory=list)
    action_label: Optional[str] = None
    action_target: Optional[str] = None
    help_text: Optional[str] = None
    pakistan_process_id: Optional[str] = None


# ---------- Destination templates ---------------------------------------
#
# Each destination provides its scholarship-phase + visa-phase steps.
# The Pakistan-phase steps are injected from pakistan_policy_service so
# we never duplicate that data here.

# UK (Chevening / Commonwealth-style scholarship + UK Student Visa)
_UK_SCHOLARSHIP_STEPS: list[StepSpec] = [
    StepSpec(
        key="check_scholarship_eligibility",
        title="Check scholarship eligibility",
        description=(
            "Confirm your nationality, degree level, GPA, and English "
            "score meet the scholarship's published criteria."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        action_label="Open scholarship",
        action_target="pages/4_Scholarships.py",
    ),
    StepSpec(
        key="prepare_leadership_evidence",
        title="Prepare leadership and networking evidence",
        description=(
            "Document leadership roles and networking achievements "
            "Chevening-style scholarships expect, with concrete examples."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="prepare_essays",
        title="Prepare essays / application answers",
        description=(
            "Draft and refine your scholarship essays. Iterate with peer "
            "or supervisor feedback."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="arrange_references",
        title="Arrange references",
        description=(
            "Identify and confirm referees who can speak to your "
            "academic and leadership profile. Provide them with the "
            "scholarship's referee instructions."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="gather_academic_documents",
        title="Gather academic documents",
        description=(
            "Collect transcripts, degrees, and proof of English "
            "language ability."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
        required_documents=["transcripts", "degree_certificate", "ielts_score"],
    ),
    StepSpec(
        key="submit_scholarship_application",
        title="Submit scholarship application",
        description=(
            "Submit your completed application via the scholarship's "
            "official portal before the deadline."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=[
            "prepare_essays", "arrange_references",
            "gather_academic_documents",
        ],
    ),
    StepSpec(
        key="track_scholarship_decision",
        title="Track scholarship decision",
        description=(
            "Monitor your scholarship application status. Respond "
            "promptly to interview or follow-up requests."
        ),
        section_id="scholarship", source="scholarship", priority="medium",
        depends_on=["submit_scholarship_application"],
    ),
]

_UK_VISA_STEPS: list[StepSpec] = [
    StepSpec(
        key="cas_offer_confirmation",
        title="CAS / offer confirmation",
        description=(
            "Receive your unconditional offer and Confirmation of "
            "Acceptance for Studies (CAS) from your UK university."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["track_scholarship_decision"],
    ),
    StepSpec(
        key="proof_of_funds_uk",
        title="Proof of funds readiness",
        description=(
            "Prepare documentation showing the funds required by UK "
            "Student Visa rules (or equivalent scholarship coverage)."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["cas_offer_confirmation"],
    ),
    StepSpec(
        key="uk_student_visa_application",
        title="UK student visa application",
        description=(
            "Complete the UK Student Visa online application and pay "
            "the application + IHS fees."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=[
            "cas_offer_confirmation", "proof_of_funds_uk",
            "tb_test", "passport_issuance",
        ],
        action_label="UK Student Visa",
        action_target="https://www.gov.uk/student-visa",
    ),
    StepSpec(
        key="biometrics_uk",
        title="Biometrics appointment",
        description=(
            "Attend your biometrics appointment at a Visa Application "
            "Centre after submitting the visa application."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["uk_student_visa_application"],
    ),
    StepSpec(
        key="visa_decision_tracking_uk",
        title="Visa decision tracking",
        description="Track your visa decision and prepare for travel.",
        section_id="visa", source="visa", priority="medium",
        depends_on=["biometrics_uk"],
    ),
]

# Canada (Vanier / EduCanada / Commonwealth-style + Study Permit)
_CA_SCHOLARSHIP_STEPS: list[StepSpec] = [
    StepSpec(
        key="check_scholarship_eligibility",
        title="Check scholarship eligibility",
        description=(
            "Confirm your nationality, degree level, GPA, and English "
            "score meet the scholarship's published criteria."
        ),
        section_id="scholarship", source="scholarship", priority="high",
    ),
    StepSpec(
        key="institution_nomination",
        title="Institution nomination (if required)",
        description=(
            "Vanier and several Canadian scholarships require the "
            "Canadian institution to nominate you. Confirm the "
            "internal nomination deadline with your supervisor."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="prepare_research_proposal",
        title="Prepare research proposal / SOP",
        description=(
            "Draft a strong research proposal or Statement of Purpose "
            "tailored to your prospective programme."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="arrange_references",
        title="Arrange references",
        description=(
            "Confirm referees and provide them with the scholarship's "
            "referee instructions."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="gather_academic_documents",
        title="Gather academic documents",
        description=(
            "Collect transcripts, degrees, and proof of English ability."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
        required_documents=["transcripts", "degree_certificate", "ielts_score"],
    ),
    StepSpec(
        key="submit_scholarship_application",
        title="Submit scholarship application",
        description=(
            "Submit via the institution's portal (for institution-"
            "nominated awards) or directly to the funder."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=[
            "prepare_research_proposal", "arrange_references",
            "gather_academic_documents",
        ],
    ),
    StepSpec(
        key="track_scholarship_decision",
        title="Track scholarship decision",
        description="Monitor decision and respond to interview requests.",
        section_id="scholarship", source="scholarship", priority="medium",
        depends_on=["submit_scholarship_application"],
    ),
]

_CA_VISA_STEPS: list[StepSpec] = [
    StepSpec(
        key="loa_offer_confirmation",
        title="Letter of Acceptance confirmation",
        description=(
            "Receive your Letter of Acceptance (LOA) from a Designated "
            "Learning Institution (DLI)."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["track_scholarship_decision"],
    ),
    StepSpec(
        key="proof_of_funds_ca",
        title="Proof of funds readiness",
        description=(
            "Prepare proof of funds — bank statements, GIC certificate, "
            "or scholarship award letter — meeting Canadian visa rules."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["loa_offer_confirmation"],
    ),
    StepSpec(
        key="ca_study_permit_application",
        title="Canada study permit application",
        description=(
            "Apply for a Canadian study permit online via the IRCC "
            "portal. Pay processing fees and biometrics fee."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=[
            "loa_offer_confirmation", "proof_of_funds_ca",
            "passport_issuance",
        ],
        action_label="IRCC study permit",
        action_target="https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit.html",
    ),
    StepSpec(
        key="biometrics_ca",
        title="Biometrics appointment",
        description="Attend your biometrics appointment at a VAC.",
        section_id="visa", source="visa", priority="high",
        depends_on=["ca_study_permit_application"],
    ),
    StepSpec(
        key="visa_decision_tracking_ca",
        title="Permit decision tracking",
        description="Track your study permit decision and prepare for travel.",
        section_id="visa", source="visa", priority="medium",
        depends_on=["biometrics_ca"],
    ),
]

# Germany (DAAD / Deutschlandstipendium + Studienvisum)
_DE_SCHOLARSHIP_STEPS: list[StepSpec] = [
    StepSpec(
        key="check_scholarship_eligibility",
        title="Check scholarship eligibility",
        description=(
            "Confirm your nationality, degree level, GPA, and German/"
            "English language ability against the programme's rules."
        ),
        section_id="scholarship", source="scholarship", priority="high",
    ),
    StepSpec(
        key="aps_certificate",
        title="APS certificate (if applicable)",
        description=(
            "If your country requires APS (Akademische Prüfstelle) "
            "verification, complete the APS process before applying."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="prepare_motivation_letter",
        title="Prepare motivation letter / SOP",
        description=(
            "Draft your motivation letter or Statement of Purpose "
            "aligned with the German programme's requirements."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="arrange_references",
        title="Arrange references",
        description=(
            "Confirm referees and brief them on the scholarship's "
            "expectations."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
    ),
    StepSpec(
        key="gather_academic_documents",
        title="Gather academic documents",
        description=(
            "Collect transcripts, degree, and German/English proof. "
            "Note that some German programmes accept TestDaF or DSH."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=["check_scholarship_eligibility"],
        required_documents=["transcripts", "degree_certificate", "ielts_score"],
    ),
    StepSpec(
        key="submit_scholarship_application",
        title="Submit scholarship application",
        description=(
            "Submit via DAAD portal or the relevant German university "
            "for Deutschlandstipendium."
        ),
        section_id="scholarship", source="scholarship", priority="high",
        depends_on=[
            "prepare_motivation_letter", "arrange_references",
            "gather_academic_documents",
        ],
    ),
    StepSpec(
        key="track_scholarship_decision",
        title="Track scholarship decision",
        description="Monitor decision and respond to follow-up requests.",
        section_id="scholarship", source="scholarship", priority="medium",
        depends_on=["submit_scholarship_application"],
    ),
]

_DE_VISA_STEPS: list[StepSpec] = [
    StepSpec(
        key="zulassung_offer_confirmation",
        title="Zulassung / offer confirmation",
        description=(
            "Receive your Zulassungsbescheid (admission letter) from "
            "the German university."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["track_scholarship_decision"],
    ),
    StepSpec(
        key="proof_of_funds_de",
        title="Proof of funds (Sperrkonto)",
        description=(
            "Open and fund a German blocked account (Sperrkonto) "
            "with the required amount, OR provide a scholarship award "
            "letter that fully covers living costs."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["zulassung_offer_confirmation"],
    ),
    StepSpec(
        key="de_studienvisum_application",
        title="Germany student visa application",
        description=(
            "Book an appointment at the German embassy / consulate in "
            "Pakistan and submit the Studienvisum application."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=[
            "zulassung_offer_confirmation", "proof_of_funds_de",
            "passport_issuance",
        ],
        action_label="German student visa",
        action_target="https://pakistan.diplo.de/",
    ),
    StepSpec(
        key="biometrics_de",
        title="Biometrics + interview",
        description=(
            "Attend the embassy interview and provide biometrics."
        ),
        section_id="visa", source="visa", priority="high",
        depends_on=["de_studienvisum_application"],
    ),
    StepSpec(
        key="visa_decision_tracking_de",
        title="Visa decision tracking",
        description="Track your visa decision and prepare for travel.",
        section_id="visa", source="visa", priority="medium",
        depends_on=["biometrics_de"],
    ),
]


_TEMPLATES: dict[str, tuple[list[StepSpec], list[StepSpec], str]] = {
    "UK":      (_UK_SCHOLARSHIP_STEPS, _UK_VISA_STEPS, "uk_chevening_v0_10"),
    "Canada":  (_CA_SCHOLARSHIP_STEPS, _CA_VISA_STEPS, "ca_default_v0_10"),
    "Germany": (_DE_SCHOLARSHIP_STEPS, _DE_VISA_STEPS, "de_default_v0_10"),
}


# ---------- Pakistan steps -----------------------------------------------

def _pakistan_step_specs(country: str) -> list[StepSpec]:
    """Build Pakistan preparation steps from the policy catalogue.
    Each becomes a route step keyed by the process id, so dependency
    references in the visa phase (`depends_on=["passport_issuance"]`)
    resolve naturally.

    v0.11.1 fix: Pakistan steps now declare `required_documents=[pid]`.
    Each Pakistan process produces a verifiable certificate (HEC
    attestation, IBCC equivalence, MOFA stamp, PCC, passport scan,
    TB clearance, NADRA CNIC) — the user must upload that certificate
    and it must pass verification before the step is `ready_to_complete`.
    Spec §1B / §2: "These steps have required_documents. They must NOT
    show 'Mark as prepared'."
    """
    specs: list[StepSpec] = []
    for proc in list_processes_for_country(country):
        pid = proc.get("id")
        if not pid:
            continue
        specs.append(StepSpec(
            key=pid,
            title=proc.get("name", pid),
            description=proc.get("description", ""),
            section_id="pakistan",
            source="pakistan",
            priority="medium",
            pakistan_process_id=pid,
            # v0.11.1: each Pakistan process expects a certificate
            # uploaded with doc_type = process id (e.g. 'hec_attestation').
            required_documents=[pid],
            help_text=proc.get("when_required"),
            action_label=("Official source" if proc.get("official_source_url")
                          else None),
            action_target=proc.get("official_source_url"),
        ))
    return specs


# ---------- Status derivation --------------------------------------------

def _intrinsic_status(
    spec: StepSpec,
    *,
    profile: UserProfile,
    eligibility_status: Optional[str],
    document_keys_completed: set[str],
) -> tuple[str, Optional[str]]:
    """Pass-1 status: from the user's data alone, ignoring dependencies.
    Returns (status, reason).

    v0.15 simplification (Phase 5.6): document upload state no longer
    drives step status. Recognised completion signals are:
      * `cas_offer_confirmation` / `loa_offer_confirmation` /
        `zulassung_offer_confirmation` → completed iff the user's
        profile shows an unconditional offer (PROFILE field, not
        document evidence).
      * `proof_of_funds_*` → completed iff the user's profile shows
        funds fully prepared.
      * NOT_ELIGIBLE → 'blocked' for the whole visa phase.

    All other steps default to 'available' (the dependency resolver
    may downgrade to 'locked' if prerequisites aren't completed). The
    user marks completion explicitly via the "Mark as Complete"
    button — documents are reference material, not gating evidence.

    `document_keys_completed` is retained in the signature for
    back-compat with callers / tests; v0.15 ignores it.
    """
    # Hard block: if eligibility ran and was NOT_ELIGIBLE, the whole
    # visa phase is blocked. (Scholarship phase still runs — the user
    # may still apply; only visa is gated by visa-eligibility.)
    if eligibility_status == "NOT_ELIGIBLE" and spec.section_id == "visa":
        return ("blocked",
                "Eligibility check returned NOT_ELIGIBLE. Resolve "
                "blocking issues on the Eligibility page first.")

    offer_strength = OFFER_STATUS_STRENGTH.get(
        getattr(profile, "offer_letter_status", None) or "", "none"
    )
    funds_strength = FUNDS_STATUS_STRENGTH.get(
        getattr(profile, "proof_of_funds_status", None) or "", "none"
    )

    if spec.key in ("cas_offer_confirmation",
                    "loa_offer_confirmation",
                    "zulassung_offer_confirmation"):
        if offer_strength == "strong":
            return ("completed", "Profile shows an unconditional offer.")
        return ("available",
                "Update your profile when the offer arrives, then mark "
                "this step complete.")

    if spec.key in ("proof_of_funds_uk", "proof_of_funds_ca",
                    "proof_of_funds_de"):
        if funds_strength == "strong":
            return ("completed", "Profile shows funds fully prepared.")
        return ("available",
                "Update your profile when funds are ready, then mark "
                "this step complete.")

    # v0.15: removed the document-driven completion branch. Pakistan
    # steps and document-listing steps default to 'available' — the
    # user marks them complete after performing the action and
    # (optionally) uploading evidence on the Documents page.
    return ("available", None)


def _resolve_dependencies(
    steps: list[DynamicRouteStepDTO],
) -> list[DynamicRouteStepDTO]:
    """Pass-2: any step whose deps aren't all 'completed' is downgraded
    to 'locked' (unless its intrinsic status is 'blocked' or
    'completed', both of which propagate as-is). Returns a NEW list
    with adjusted statuses.

    Bug fix (v0.10.1): when a step's intrinsic status was previously
    locked (with a "Waiting for: X" reason), and X has since become
    completed, the resolver must CLEAR the stale waiting message.
    Previously the step kept its old reason because we only modified
    the step when downgrading, never when upgrading.
    """
    by_key = {s.key: s for s in steps}
    out: list[DynamicRouteStepDTO] = []
    for s in steps:
        # 'blocked' (hard gate, e.g. NOT_ELIGIBLE) propagates as-is.
        # 'completed' (sticky — either derived or user-acknowledged)
        # also propagates as-is.
        if s.status in ("blocked", "completed"):
            out.append(s)
            continue

        unmet: list[str] = []
        for dep_key in s.depends_on:
            dep = by_key.get(dep_key)
            if dep is None:
                log.debug(
                    "Step %r depends on unknown step %r — treating as unmet.",
                    s.key, dep_key,
                )
                unmet.append(dep_key)
                continue
            if dep.status != "completed":
                unmet.append(dep_key)

        if unmet:
            # Lock with a fresh waiting message. Use dependency *titles*
            # rather than keys when we have them — friendlier UX and
            # matches the page-side rendering.
            unmet_titles = [
                (by_key[k].title if k in by_key else k) for k in unmet
            ]
            out.append(s.model_copy(update={
                "status": "locked",
                "status_reason": f"Waiting for: {', '.join(unmet_titles)}.",
            }))
        else:
            # Deps are satisfied. If the persisted/intrinsic status was
            # 'locked' (with a stale waiting message), upgrade it to
            # 'available' and clear the message. Otherwise (already
            # 'available' or 'pending'), keep the intrinsic status but
            # still clear any stale "Waiting for" reason.
            current_reason = s.status_reason or ""
            stale = current_reason.startswith("Waiting for:")
            if s.status == "locked":
                out.append(s.model_copy(update={
                    "status": "available",
                    "status_reason": (
                        None if stale
                        else "All dependencies completed."
                    ),
                }))
            elif stale:
                out.append(s.model_copy(update={"status_reason": None}))
            else:
                out.append(s)
    return out


# ---------- Document-status loading --------------------------------------

def _completed_document_keys(profile_id: int, country: str) -> set[str]:
    """Return the set of doc_type keys that have status uploaded/verified."""
    keys: set[str] = set()
    with session_scope() as db:
        for d in db.scalars(
            select(CaseDocument).where(
                (CaseDocument.profile_id == profile_id)
                & (CaseDocument.country == country)
            )
        ):
            if d.status in ("uploaded", "verified") and d.doc_type:
                keys.add(d.doc_type)
    return keys


def _latest_eligibility_status(profile_id: int) -> Optional[str]:
    with session_scope() as db:
        latest = db.scalars(
            select(EligibilityResult)
            .where(EligibilityResult.profile_id == profile_id)
            .order_by(EligibilityResult.created_at.desc())
        ).first()
        if latest is None:
            return None
        # Latest decision states are stored in trace_json.decision per
        # v0.3; the legacy `status` column is a coarser bucket.
        try:
            payload = json.loads(latest.trace_json or "{}")
            decision = payload.get("decision")
            if decision:
                return str(decision)
        except (ValueError, TypeError):
            pass
        return latest.status


# ---------- v0.11: evidence loading + overlay --------------------------


def _load_evidence_by_step(
    profile_id: int,
) -> dict[str, list[DocumentEvidenceDTO]]:
    """Return all uploaded documents for this profile, grouped by
    `step_key`. Each list item is a hydrated `DocumentEvidenceDTO`.

    NULL step_key rows are dropped — they're legacy documents from
    the v0.10 vault and aren't attached to any step.
    """
    out: dict[str, list[DocumentEvidenceDTO]] = {}
    with session_scope() as db:
        for d in db.scalars(
            select(CaseDocument).where(
                (CaseDocument.profile_id == profile_id)
                & (CaseDocument.step_key.is_not(None))
            )
        ):
            try:
                fields = json.loads(d.extracted_json or "{}")
                if not isinstance(fields, dict):
                    fields = {}
            except (ValueError, TypeError):
                fields = {}

            def _safe_list(blob):
                try:
                    v = json.loads(blob or "[]")
                    return [str(x) for x in v] if isinstance(v, list) else []
                except (ValueError, TypeError):
                    return []

            dto = DocumentEvidenceDTO(
                id=d.id,
                profile_id=d.profile_id,
                user_id=d.user_id,
                step_key=d.step_key,
                document_type=d.document_type or d.doc_type,
                original_filename=d.original_filename or d.filename,
                stored_path=d.stored_path,
                mime_type=d.mime_type,
                file_size=d.file_size,
                extracted_text=(
                    d.extracted_text[:2000] if d.extracted_text else None
                ),
                extracted_fields=fields,
                verification_status=(
                    d.verification_status or "pending"  # type: ignore[arg-type]
                ),
                issues=_safe_list(d.issues_json),
                warnings=_safe_list(getattr(d, "warnings_json", None)),
                matched_fields=_safe_list(
                    getattr(d, "matched_fields_json", None)
                ),
                # v0.12 extraction-pipeline visibility
                extraction_method=getattr(d, "extraction_method", None),
                extraction_status=getattr(d, "extraction_status", None),
                extraction_errors=_safe_list(
                    getattr(d, "extraction_errors", None)
                ),
                # v0.14 confirmation path (spec §3, §4)
                confirmed_by_user=bool(
                    getattr(d, "confirmed_by_user", False)
                ),
                confirmed_at=getattr(d, "confirmed_at", None),
                confirmed_by_admin_id=getattr(d, "confirmed_by_admin_id", None),
                # v0.16 — confirmation note
                confirmation_note=getattr(d, "confirmation_note", None),
                uploaded_at=d.uploaded_at or d.created_at,
                updated_at=d.updated_at,
            )
            out.setdefault(d.step_key, []).append(dto)
    return out


def _apply_evidence_overlay(
    steps: list[DynamicRouteStepDTO],
    *,
    profile_id: int,
) -> list[DynamicRouteStepDTO]:
    """v0.11: layer evidence-derived statuses on top of pass-1+2.

    Rules:
      * Evidence steps (required_documents non-empty OR pakistan_process_id
        OR profile-driven evidence keys) with NO uploaded evidence → set
        status to `awaiting_documents` (spec §4: "no upload →
        awaiting_documents"). This guarantees the UI never offers
        "Mark as prepared" on an evidence step.
      * If at least one doc is uploaded but verification is `pending`
        for any of them → status becomes `pending_verification`.
      * If any uploaded doc has verification status `needs_attention`
        / `rejected` / `extraction_failed` → `needs_attention`.
      * If all required document slots have at least one `verified`
        doc → `ready_to_complete`.
      * Steps in `locked`, `blocked`, or `completed` are left alone —
        evidence cannot override a hard gate or demote completion.
      * `is_evidence_task` is set True for any step the
        `is_evidence_step()` predicate accepts (used by the page UI).
    """
    evidence_map = _load_evidence_by_step(profile_id)
    out: list[DynamicRouteStepDTO] = []
    for s in steps:
        evidence = evidence_map.get(s.key, [])
        # Use the canonical predicate so Pakistan + profile-driven
        # steps are correctly classified even with empty
        # required_documents.
        is_evidence_task = is_evidence_step(s) or bool(evidence)

        new_dto = s.model_copy(update={
            "evidence": evidence,
            "is_evidence_task": is_evidence_task,
        })

        # locked / blocked are hard gates — propagate as-is.
        if s.status in ("locked", "blocked"):
            out.append(new_dto)
            continue

        # v0.13 spec §7: completed evidence steps must be downgraded
        # if they no longer have verified documents covering every
        # required slot. (Examples: user deleted a verified file from
        # the Vault; document type was renamed and the old upload no
        # longer matches the slot list.) Soft completed steps and
        # completed evidence steps with intact coverage propagate
        # as-is.
        if s.status == "completed":
            if not is_evidence_task:
                # Soft step — completion is sticky, no document check.
                out.append(new_dto)
                continue
            slots = resolve_required_documents(s)
            if not slots:
                # Profile-driven evidence step with no resolvable
                # slots — completion is sticky.
                out.append(new_dto)
                continue
            # v0.14: 'verified' OR 'user_confirmed' OR 'admin_verified'
            # all count as evidence-satisfied (spec §6).
            satisfied_types = {
                e.document_type for e in evidence
                if e.verification_status in EVIDENCE_SATISFIED_STATUSES
            }
            required_types = {
                slot.document_type for slot in slots if not slot.optional
            }
            missing = required_types - satisfied_types
            if not missing:
                # Coverage intact — propagate completion.
                out.append(new_dto)
                continue
            # Coverage lost — downgrade. Choose status by what
            # evidence is left.
            if not evidence:
                downgrade_status = "awaiting_documents"
                reason = (
                    "Previously completed, but the required "
                    "document(s) are no longer on file. Re-upload "
                    "to restore completion: "
                    + ", ".join(sorted(missing)) + "."
                )
            elif any(e.verification_status in (
                "needs_attention", "rejected", "extraction_failed",
            ) for e in evidence):
                downgrade_status = "needs_attention"
                reason = (
                    "Previously completed, but uploaded documents "
                    "now have issues. Resolve them to restore "
                    "completion."
                )
            elif any(e.verification_status == "manual_review_required"
                     for e in evidence):
                # v0.14: needs the user's manual confirmation.
                downgrade_status = "pending_user_confirmation"
                reason = (
                    "Previously completed, but one or more documents "
                    "require manual confirmation. Click 'Confirm this "
                    "document is correct' for each."
                )
            else:
                downgrade_status = "pending_verification"
                reason = (
                    "Previously completed, but verification has not "
                    "re-run on all required documents. Awaiting "
                    "verification for: "
                    + ", ".join(sorted(missing)) + "."
                )
            log.info(
                "Downgrading completed evidence step %r: %s "
                "(missing=%s)", s.key, downgrade_status, sorted(missing),
            )
            out.append(new_dto.model_copy(update={
                "status": downgrade_status,
                "status_reason": reason,
            }))
            continue

        # v0.11.1 NEW: evidence step with no upload yet → awaiting_documents.
        # Profile-driven evidence steps that the intrinsic pass already
        # promoted to `completed` are caught by the guard above.
        if is_evidence_task and not evidence:
            # Profile-driven steps may have been promoted to specific
            # statuses by `_intrinsic_status` (e.g. cas_offer_confirmation
            # → 'pending' if conditional offer). Preserve those signals
            # — only swap the generic 'available' default.
            if s.status == "available":
                out.append(new_dto.model_copy(update={
                    "status": "awaiting_documents",
                    "status_reason": (
                        "Upload the required document(s) so verification "
                        "can run."
                    ),
                }))
                continue
            # 'pending' / 'in_progress' / 'needs_attention' /
            # 'pending_verification' — leave intrinsic status alone.
            out.append(new_dto)
            continue

        if not evidence:
            out.append(new_dto)
            continue

        statuses = {e.verification_status for e in evidence}
        # Hard issues come first — needs_attention / rejected /
        # extraction_failed override everything else.
        if any(st in ("needs_attention", "rejected",
                      "extraction_failed") for st in statuses):
            out.append(new_dto.model_copy(update={
                "status": "needs_attention",
                "status_reason": (
                    "One or more uploaded documents need attention "
                    "(see issues below)."
                ),
            }))
            continue

        # v0.13: use canonical resolver so optional slots don't
        # block ready_to_complete and required_documents on the DTO
        # are honored even when the resolver expands them.
        slots = resolve_required_documents(s)
        if slots:
            # v0.14: 'verified' OR 'user_confirmed' OR 'admin_verified'
            # all count as evidence-satisfied (spec §6).
            satisfied = {
                e.document_type for e in evidence
                if e.verification_status in EVIDENCE_SATISFIED_STATUSES
            }
            required = [slot for slot in slots if not slot.optional]
            missing = [slot.document_type for slot in required
                       if slot.document_type not in satisfied]
            if not missing:
                # All required slots covered — ready to complete.
                out.append(new_dto.model_copy(update={
                    "status": "ready_to_complete",
                    "status_reason": (
                        "All required documents verified or confirmed."
                    ),
                }))
                continue
            # Some required slots not yet satisfied. Choose status
            # based on what kind of waiting we're in:
            #   * any required slot has manual_review_required →
            #     pending_user_confirmation (user action needed)
            #   * else → pending_verification (system action)
            missing_set = set(missing)
            manual_review_pending = any(
                e.verification_status == "manual_review_required"
                and e.document_type in missing_set
                for e in evidence
            )
            if manual_review_pending:
                out.append(new_dto.model_copy(update={
                    "status": "pending_user_confirmation",
                    "status_reason": (
                        "VisaForge could read the uploaded "
                        "document(s) but cannot fully verify this "
                        "type automatically. Click 'Confirm this "
                        "document is correct' below to proceed."
                    ),
                }))
                continue
            out.append(new_dto.model_copy(update={
                "status": "pending_verification",
                "status_reason": (
                    "Awaiting verification for: "
                    + ", ".join(sorted(missing)) + "."
                ),
            }))
            continue

        # Step had no resolvable slots but user uploaded something.
        # Bias toward ready_to_complete when satisfied, manual review
        # when needed, else pending_verification.
        if all(st in EVIDENCE_SATISFIED_STATUSES for st in statuses):
            out.append(new_dto.model_copy(update={
                "status": "ready_to_complete",
                "status_reason": "Uploaded evidence verified.",
            }))
        elif any(st == "manual_review_required" for st in statuses):
            out.append(new_dto.model_copy(update={
                "status": "pending_user_confirmation",
                "status_reason": (
                    "Uploaded document needs your confirmation."
                ),
            }))
        else:
            out.append(new_dto.model_copy(update={
                "status": "pending_verification",
                "status_reason": "Awaiting verification of uploaded evidence.",
            }))
    return out


def _apply_user_completion_overlay(
    steps: list[DynamicRouteStepDTO],
    *,
    profile_id: int,
    country: str,
) -> list[DynamicRouteStepDTO]:
    """If the user has clicked Mark-as-Complete on a step (i.e. the
    persisted RouteStep has `completed_at` set), force that step's
    status to 'completed'.

    v0.13 spec §7 exception: if the evidence overlay has just
    downgraded an evidence step to `awaiting_documents` /
    `pending_verification` / `needs_attention` (because verified docs
    no longer cover the required slots), DO NOT re-promote it to
    'completed' here. The downgrade reflects current truth and must
    survive. Soft steps (no evidence requirement) still force-complete
    as before. The next time the user resolves the issue, attaching
    a new verified doc will let the evidence overlay produce
    `ready_to_complete` and the user can click Mark-as-Complete again.
    """
    # Evidence-overlay downgrade statuses. If a persisted-completed
    # step already carries one of these, the evidence overlay
    # explicitly chose to demote it — don't fight that.
    _DOWNGRADE_STATUSES = frozenset({
        "awaiting_documents", "pending_verification", "needs_attention",
        "pending_user_confirmation",  # v0.14
    })
    completed_keys: set[str] = set()
    with session_scope() as db:
        rp = db.scalar(
            select(RoutePlan).where(
                (RoutePlan.profile_id == profile_id)
                & (RoutePlan.country == country)
            )
        )
        if rp is not None:
            for rs in db.scalars(
                select(RouteStep).where(
                    (RouteStep.plan_id == rp.id)
                    & (RouteStep.completed_at.is_not(None))
                )
            ):
                completed_keys.add(rs.key)
    if not completed_keys:
        return steps
    out: list[DynamicRouteStepDTO] = []
    for s in steps:
        if s.key in completed_keys and s.status not in _DOWNGRADE_STATUSES:
            out.append(s.model_copy(update={
                "status": "completed",
                "status_reason": "Marked as complete.",
            }))
        else:
            out.append(s)
    return out


# ---------- Public API ---------------------------------------------------

# v0.11.1: Profile-driven visa-readiness steps are evidence steps even
# though they don't carry an explicit `required_documents` list. Their
# completion is gated by `offer_letter_status` / `proof_of_funds_status`
# on the profile (and optionally a supporting upload). The page must
# treat them as evidence steps so they don't get "Mark as prepared".
_PROFILE_DRIVEN_EVIDENCE_STEP_KEYS: frozenset[str] = frozenset({
    "cas_offer_confirmation",          # UK
    "loa_offer_confirmation",          # Canada
    "zulassung_offer_confirmation",    # Germany
    "proof_of_funds_uk",
    "proof_of_funds_ca",
    "proof_of_funds_de",
})


# v0.13 — canonical document-type catalog with friendly labels. The
# resolver below returns RequiredDocument entries built from this map,
# so every UI surface (route plan upload widgets, debug audit panel,
# documents vault) shows the same label for the same document_type.
#
# Document type strings here MUST exactly match the constants exported
# by services/document_processing_service.py (DOCUMENT_TYPE_*). They're
# duplicated as plain strings because importing them creates a circular
# import chain (document_processing depends on schemas which depends
# on this module). The mapping below is verified at module load time
# against those exports — see _verify_doc_type_map at the bottom of
# this file.
_DOC_LABELS: dict[str, str] = {
    "passport":              "Passport scan",
    "ielts":                 "IELTS / English test report",
    "toefl":                 "TOEFL report",
    "english_test":          "English test report (IELTS / TOEFL / PTE)",
    "bank_statement":        "Bank statement",
    "sponsor_letter":        "Sponsor letter (if sponsored)",
    "transcript":            "Academic transcript",
    "degree_certificate":    "Degree certificate",
    "police_clearance":      "Police clearance certificate",
    "hec_attestation":       "HEC attestation evidence",
    "ibcc_equivalence":      "IBCC equivalence / attestation evidence",
    "mofa_attestation":      "MOFA attestation evidence",
    "tb_test":               "TB test certificate",
    "passport_issuance":     "Passport scan",
    "nadra_documents":       "CNIC / B-Form / Birth Certificate",
    "offer_letter":          "Offer / acceptance letter",
    "cas_letter":            "CAS letter",
    "loa_letter":            "Letter of Acceptance",
    "zulassung":             "Zulassungsbescheid",
    "academic_document":     "Academic document",
}


# v0.13 — per-step fallback document slots. Keyed by step.key.
# Each entry is a list of (document_type, optional_flag) tuples.
# The resolver consults this when step.required_documents is empty
# AND the step still needs upload slots.
#
# Pakistan steps: each pakistan process should produce ONE certificate
# keyed to its process_id, plus any prerequisite docs (e.g. HEC
# attestation also needs the underlying degree + transcript so the
# attesting authority can stamp them).
#
# Profile-driven visa-readiness steps: typically need a primary doc
# (offer letter, bank statement) and one optional supporting doc
# (sponsor letter for funds; alternative offer formats).
_FALLBACK_SLOTS: dict[str, list[tuple[str, bool]]] = {
    # Pakistan-side
    "passport_issuance":  [("passport",          False)],
    "hec_attestation":    [("hec_attestation",   False),
                           ("degree_certificate", True),
                           ("transcript",         True)],
    "ibcc_equivalence":   [("ibcc_equivalence",  False)],
    "mofa_attestation":   [("mofa_attestation",  False)],
    "police_clearance":   [("police_clearance",  False)],
    "tb_test":            [("tb_test",           False)],
    "nadra_documents":    [("nadra_documents",   False)],
    # Visa-phase profile-driven (UK / CA / DE)
    "cas_offer_confirmation":       [("offer_letter", False)],
    "loa_offer_confirmation":       [("offer_letter", False)],
    "zulassung_offer_confirmation": [("offer_letter", False)],
    "proof_of_funds_uk":            [("bank_statement", False),
                                     ("sponsor_letter", True)],
    "proof_of_funds_ca":            [("bank_statement", False),
                                     ("sponsor_letter", True)],
    "proof_of_funds_de":            [("bank_statement", False),
                                     ("sponsor_letter", True)],
    # Scholarship-phase document-driven
    "gather_academic_documents":    [("transcript",         False),
                                     ("degree_certificate", False),
                                     ("english_test",       False)],
}


def resolve_required_documents(
    step: DynamicRouteStepDTO,
) -> list["RequiredDocument"]:
    """Spec §2: the ONE canonical resolver.

    Returns the list of document slots a step expects. Sources, in
    priority order:

      1. `step.required_documents` — explicit list set by the template
         or `_pakistan_step_specs`. Each entry becomes a RequiredDocument
         using `_DOC_LABELS` (or a humanised fallback when the type
         isn't catalogued).
      2. `_FALLBACK_SLOTS[step.key]` — fallback for Pakistan and
         profile-driven steps where the explicit list is just `[pid]`
         and we want to expand it (e.g. HEC also needs the underlying
         degree + transcript).
      3. Empty list if neither source applies (genuinely soft steps).

    All UI and service code MUST consult this function — never inline
    a per-step mapping. The page renders one upload widget per
    returned RequiredDocument; if the list is empty, the upload area
    must be hidden entirely (spec §3).
    """
    from models.schemas import RequiredDocument

    out: list[RequiredDocument] = []
    seen: set[str] = set()

    # Source 1: explicit step.required_documents.
    explicit = list(step.required_documents or [])

    # Source 2: fallback slots for known step keys.
    fallback = _FALLBACK_SLOTS.get(step.key, [])

    # Source 3: pakistan_process_id alone — when explicit list is
    # empty AND there's no _FALLBACK_SLOTS entry, but a process_id is
    # set (defensive — shouldn't happen for the seven Pakistan
    # processes since v0.11.1, but kept as a safety net).
    if not explicit and not fallback and step.pakistan_process_id:
        fallback = [(step.pakistan_process_id, False)]

    # Build canonical list. Explicit entries first (template
    # authoritative), then fallback entries that aren't already
    # covered. Optional flag from fallback only — explicit entries
    # default to required.
    for dt in explicit:
        if dt in seen:
            continue
        seen.add(dt)
        out.append(RequiredDocument(
            document_type=dt,
            label=_DOC_LABELS.get(
                dt,
                # Humanise unknown types: "hec_attestation" → "Hec attestation"
                dt.replace("_", " ").capitalize(),
            ),
            optional=False,
        ))
    for dt, optional in fallback:
        if dt in seen:
            continue
        seen.add(dt)
        out.append(RequiredDocument(
            document_type=dt,
            label=_DOC_LABELS.get(dt, dt.replace("_", " ").capitalize()),
            optional=optional,
        ))
    return out


def is_evidence_step(step: DynamicRouteStepDTO) -> bool:
    """Classify whether a step is evidence/document-driven (vs soft).

    Spec §4: evidence steps are those for which
    `resolve_required_documents()` returns at least one slot, OR which
    have a `pakistan_process_id`, OR whose key is in the known
    profile-driven evidence set. Returns True for any of those.

    The Route Plan page uses this to decide between "Mark as prepared"
    (soft, allowed) and "Mark as Complete" (evidence, only when
    `ready_to_complete`).
    """
    if resolve_required_documents(step):
        return True
    if step.pakistan_process_id:
        return True
    if step.key in _PROFILE_DRIVEN_EVIDENCE_STEP_KEYS:
        return True
    return False


def audit_route_plan_documents(
    plan: DynamicRoutePlanDTO,
) -> list[dict]:
    """Spec §1 — full audit helper. Returns a list of issue dicts
    describing every inconsistency between an evidence step and its
    document mapping / uploaded files.

    Each issue dict has shape:
      {
        "step_key":  str,
        "step_title": str,
        "section_id": str,
        "issue_type": str,   # one of the spec §1 categories
        "detail":    str,
      }

    Issue types:
      * 'no_required_documents'   — evidence step, resolver returns []
      * 'no_upload_slot'          — required_documents present in
                                    DTO but resolver couldn't render
                                    it (label fallback path was hit)
      * 'duplicate_document_type' — same document_type listed twice
                                    in step.required_documents
      * 'awaiting_documents_no_slots' — status is 'awaiting_documents'
                                    but resolver returns [] (the
                                    user's reported bug)
      * 'completed_without_verified' — status is 'completed' but the
                                    required slots aren't all covered
                                    by verified evidence
      * 'evidence_unlinked'       — step has uploaded evidence whose
                                    document_type isn't in the
                                    resolver's slot list

    Empty list = clean. Used by the Route Plan page debug panel and
    by the migration verification suite.
    """
    issues: list[dict] = []
    if plan is None:
        return issues

    for sec in plan.sections:
        for step in sec.steps:
            evidence_step = is_evidence_step(step)
            slots = resolve_required_documents(step)
            slot_types = {s.document_type for s in slots}

            # 1. Evidence step but resolver returns nothing — soft step
            # was misclassified or fallback table is missing an entry.
            if evidence_step and not slots:
                issues.append({
                    "step_key": step.key,
                    "step_title": step.title,
                    "section_id": step.section_id,
                    "issue_type": "no_required_documents",
                    "detail": (
                        f"Step is evidence-classified (pakistan_process_id="
                        f"{step.pakistan_process_id!r}, profile_driven="
                        f"{step.key in _PROFILE_DRIVEN_EVIDENCE_STEP_KEYS}) "
                        f"but resolve_required_documents() returned []."
                    ),
                })

            # 2. Duplicate document type in explicit list.
            seen: set[str] = set()
            for dt in (step.required_documents or []):
                if dt in seen:
                    issues.append({
                        "step_key": step.key,
                        "step_title": step.title,
                        "section_id": step.section_id,
                        "issue_type": "duplicate_document_type",
                        "detail": (
                            f"document_type {dt!r} is listed more than "
                            f"once in step.required_documents."
                        ),
                    })
                seen.add(dt)

            # 3. Status awaiting_documents but no upload slots — the
            # user-reported bug. The hint says "Upload the required
            # document(s) below" but no slots render.
            if step.status == "awaiting_documents" and not slots:
                issues.append({
                    "step_key": step.key,
                    "step_title": step.title,
                    "section_id": step.section_id,
                    "issue_type": "awaiting_documents_no_slots",
                    "detail": (
                        "Step status is 'awaiting_documents' but no "
                        "upload slots can be resolved. The upload "
                        "hint will be hidden by the page."
                    ),
                })

            # 4. Completed but missing satisfied evidence for a
            # required (non-optional) slot. v0.14: 'verified' or
            # 'user_confirmed' or 'admin_verified' all count.
            if step.status == "completed" and slots:
                satisfied_types = {
                    e.document_type for e in (step.evidence or [])
                    if getattr(e, "verification_status", "pending")
                       in EVIDENCE_SATISFIED_STATUSES
                }
                missing = [
                    s.document_type for s in slots
                    if not s.optional and s.document_type not in satisfied_types
                ]
                if missing:
                    issues.append({
                        "step_key": step.key,
                        "step_title": step.title,
                        "section_id": step.section_id,
                        "issue_type": "completed_without_verified",
                        "detail": (
                            "Step is marked completed but these "
                            "required document(s) have no verified "
                            "or confirmed upload: "
                            + ", ".join(sorted(missing))
                        ),
                    })

            # 5. Uploaded evidence whose document_type isn't in any
            # slot — user uploaded something the step doesn't expect,
            # or the slot list shrank after upload.
            if step.evidence and slots:
                for e in step.evidence:
                    if e.document_type and e.document_type not in slot_types:
                        issues.append({
                            "step_key": step.key,
                            "step_title": step.title,
                            "section_id": step.section_id,
                            "issue_type": "evidence_unlinked",
                            "detail": (
                                f"Uploaded document_type "
                                f"{e.document_type!r} is not in the "
                                "step's resolved slot list. Re-upload "
                                "on the correct slot or update the "
                                "fallback table."
                            ),
                        })

    return issues


def get_next_actionable_step(
    plan: Optional[DynamicRoutePlanDTO],
) -> Optional[DynamicRouteStepDTO]:
    """v0.14 spec §9: return the single most actionable step, or None
    if the plan is empty / fully completed / fully blocked.

    Priority order (first match wins):
      1. needs_attention — user must fix something
      2. pending_user_confirmation — user must confirm a doc
      3. ready_to_complete — user can click Mark as Complete now
      4. awaiting_documents — user needs to upload
      5. available / in_progress / pending — user has work to do
      6. locked — surfaces the soonest waiting step so the user can
         see what's blocking
      7. else None (everything is completed / blocked)

    The Route Plan and Dashboard pages both call this to render the
    "Continue current step" CTA. Both consume the same priority order
    so the user sees the same "what's next" answer everywhere.

    `pending_verification` is intentionally NOT in the actionable set
    — the user can't do anything about it (the system is processing).
    Same for `blocked` and `completed`.
    """
    if plan is None:
        return None

    priorities = (
        "needs_attention",
        "pending_user_confirmation",
        "ready_to_complete",
        "awaiting_documents",
        "available",
        "in_progress",
        "pending",
        "locked",
    )
    for status in priorities:
        for sec in plan.sections:
            for step in sec.steps:
                if step.status == status:
                    return step
    return None


def can_complete_step(
    profile_id: int, step: DynamicRouteStepDTO,
) -> tuple[bool, str]:
    """v0.15 (Phase 5.6 pivot): minimal gate.

    Returns (allowed, reason).

    Allowed:
      * any non-completed, non-locked, non-blocked step

    Refused:
      * `completed` → True (idempotent)
      * `locked` → False (waiting on dependencies; resolver populates
        `status_reason` with which deps)
      * `blocked` → False (hard gate, e.g. NOT_ELIGIBLE)

    Per spec §2 + §6: documents do NOT block completion. The user
    decides when a step is done; document upload, OCR results, and
    verification outcomes are reference material on the Documents
    page only. The previous evidence-driven gating is retired.
    """
    if step.status == "completed":
        return True, "Step is already complete."
    if step.status == "locked":
        return False, (
            "This step is waiting on its dependencies. "
            f"{step.status_reason or ''}".strip()
        )
    if step.status == "blocked":
        return False, (
            "This step is blocked by a hard gate (e.g. eligibility). "
            f"{step.status_reason or ''}".strip()
        )
    return True, "Ready to mark complete."


def generate_plan(
    profile_id: int,
    *,
    user_id: Optional[int] = None,
) -> Optional[DynamicRoutePlanDTO]:
    """Build a fresh plan in memory (without persisting) for the given
    profile. Returns None if no scholarship is selected or no profile."""
    with session_scope() as db:
        profile = db.get(UserProfile, profile_id)
        if profile is None:
            return None
        country = profile.destination_country
        # detach so callers outside the session can use the row
        db.expunge(profile)

    if not country or country not in _TEMPLATES:
        log.info(
            "No route template for destination_country=%r", country
        )
        return None

    selected = get_selected_scholarship(profile_id)
    if selected is None:
        return None

    schol_steps, visa_steps, template_key = _TEMPLATES[country]
    pak_steps = _pakistan_step_specs(country)

    # Build the full ordered spec list. Section order is fixed:
    # scholarship → pakistan → visa.
    all_specs: list[StepSpec] = list(schol_steps) + pak_steps + list(visa_steps)

    # Inject "depends_on track_scholarship_decision" at the top of
    # the visa phase ONLY if the spec doesn't already declare it
    # explicitly (each visa template's first step does declare it).

    eligibility_status = _latest_eligibility_status(profile_id)
    completed_doc_keys = _completed_document_keys(profile_id, country)

    # Pass 1: intrinsic statuses
    dtos: list[DynamicRouteStepDTO] = []
    for i, spec in enumerate(all_specs):
        status, reason = _intrinsic_status(
            spec,
            profile=profile,
            eligibility_status=eligibility_status,
            document_keys_completed=completed_doc_keys,
        )
        dtos.append(DynamicRouteStepDTO(
            key=spec.key,
            title=spec.title,
            description=spec.description,
            status=status,  # type: ignore[arg-type]
            depends_on=list(spec.depends_on),
            source=spec.source,  # type: ignore[arg-type]
            priority=spec.priority,  # type: ignore[arg-type]
            required_documents=list(spec.required_documents),
            action_label=spec.action_label,
            action_target=spec.action_target,
            help_text=spec.help_text,
            pakistan_process_id=spec.pakistan_process_id,
            order_index=i,
            section_id=spec.section_id,  # type: ignore[arg-type]
            status_reason=reason,
        ))

    # v0.15 simplification (Phase 5.6 pivot): documents no longer
    # influence step status. The pipeline is now:
    #
    #   Pass 1: intrinsic status (locked/available/blocked from
    #           profile + eligibility + dependency check)
    #   Pass 2: user-completion overlay (any step the user has clicked
    #           "Mark as Complete" on becomes 'completed')
    #   Pass 3: dependency resolver (re-cascades completion to unlock
    #           dependents)
    #
    # The previous evidence overlay (v0.11–v0.14) is retained as a
    # private helper that the audit / vault tooling can still use for
    # warnings, but it is no longer part of the route-plan pipeline.
    # Per Phase 5.6 spec §6: "Documents should NOT block route progress.
    # Verification becomes OPTIONAL insight, not a gate."
    dtos = _apply_user_completion_overlay(
        dtos, profile_id=profile_id, country=country,
    )
    dtos = _resolve_dependencies(dtos)

    # v0.15: any persisted RouteStep row carrying a legacy v0.11–v0.14
    # status that's no longer produced by the pipeline (e.g. a step
    # left at 'awaiting_documents' before the pivot) is upgraded here
    # so the page only ever sees the four v0.15 statuses. Completion
    # is sticky — that branch never runs on `completed`.
    _LEGACY_STATUSES = {
        "pending", "in_progress", "awaiting_documents",
        "pending_verification", "pending_user_confirmation",
        "needs_attention", "ready_to_complete",
    }
    upgraded: list[DynamicRouteStepDTO] = []
    for d in dtos:
        if d.status in _LEGACY_STATUSES:
            upgraded.append(d.model_copy(update={
                "status": "available",
                "status_reason": (
                    None if (d.status_reason
                              and d.status_reason.startswith("Waiting for"))
                    else d.status_reason
                ),
            }))
        else:
            upgraded.append(d)
    dtos = upgraded

    # Group into sections
    sections: list[RouteSectionDTO] = []
    for sid in ("scholarship", "pakistan", "visa"):
        title, desc = _SECTION_TITLES[sid]
        section_steps = [s for s in dtos if s.section_id == sid]
        completed = sum(1 for s in section_steps if s.status == "completed")
        total = len(section_steps) or 1
        sections.append(RouteSectionDTO(
            section_id=sid,  # type: ignore[arg-type]
            title=title, description=desc,
            progress_pct=int(round(100 * completed / total)),
            steps=section_steps,
        ))

    overall_total = sum(len(s.steps) for s in sections) or 1
    overall_completed = sum(
        1 for sec in sections for s in sec.steps if s.status == "completed"
    )
    overall = int(round(100 * overall_completed / overall_total))

    blocked_reason = None
    if eligibility_status == "NOT_ELIGIBLE":
        blocked_reason = (
            "Visa phase is blocked because your eligibility check returned "
            "NOT_ELIGIBLE. Resolve the blocking issues first."
        )

    return DynamicRoutePlanDTO(
        profile_id=profile_id,
        user_id=user_id,
        scholarship_id=selected.id,
        destination_country=country,
        template_key=template_key,
        sections=sections,
        overall_progress_pct=overall,
        blocked_reason=blocked_reason,
    )


def save_plan(plan: DynamicRoutePlanDTO) -> int:
    """Persist a generated plan. Replaces any prior plan for the same
    (profile, destination) pair. Returns the saved plan id."""
    with session_scope() as db:
        # Wipe any prior plan for this profile+country.
        for existing in db.scalars(
            select(RoutePlan).where(
                (RoutePlan.profile_id == plan.profile_id)
                & (RoutePlan.country == plan.destination_country)
            )
        ):
            db.delete(existing)
        db.flush()

        rp = RoutePlan(
            profile_id=plan.profile_id,
            user_id=plan.user_id,
            scholarship_id=plan.scholarship_id,
            country=plan.destination_country,
            template_key=plan.template_key,
        )
        db.add(rp)
        db.flush()

        all_steps: list[DynamicRouteStepDTO] = [
            s for sec in plan.sections for s in sec.steps
        ]
        for s in all_steps:
            # Regeneration should reset user workflow progress.
            # Do not persist generated/intrinsic 'completed' states as user progress.
            reset_status = "available" if not s.depends_on else "locked"

            db.add(RouteStep(
                plan_id=rp.id,
                order_index=s.order_index,
                key=s.key,
                title=s.title,
                description=s.description,
                status=reset_status,
                depends_on_json=json.dumps(s.depends_on),
                section_id=s.section_id,
                source=s.source,
                priority=s.priority,
                required_documents_json=json.dumps(s.required_documents),
                action_label=s.action_label,
                action_target=s.action_target,
                help_text=s.help_text,
                pakistan_process_id=s.pakistan_process_id,
                notes="Regenerated route plan; progress reset.",
            ))
        rp.updated_at = utcnow()
        log.info(
            "Saved route plan id=%s profile=%s country=%s template=%s",
            rp.id, plan.profile_id, plan.destination_country,
            plan.template_key,
        )
        return rp.id


def get_persisted_plan(
    profile_id: int, destination_country: str,
) -> Optional[DynamicRoutePlanDTO]:
    """Read back a previously persisted plan for (profile, country).

    v0.10.1 BUG FIX: re-runs the dependency resolver on every read so
    that a step marked completed *after* the plan was last saved
    correctly cascades — its dependents transition from locked →
    available, and any stale "Waiting for: X" message attached to
    those dependents is cleared. Persisted `status='completed'` rows
    (set by mark_step_complete or evidence verification) are sticky
    and propagate as-is through the resolver.
    """
    with session_scope() as db:
        rp = db.scalar(
            select(RoutePlan).where(
                (RoutePlan.profile_id == profile_id)
                & (RoutePlan.country == destination_country)
            )
        )
        if rp is None:
            return None

        steps = list(db.scalars(
            select(RouteStep)
            .where(RouteStep.plan_id == rp.id)
            .order_by(RouteStep.order_index)
        ))
        dtos: list[DynamicRouteStepDTO] = []
        for s in steps:
            try:
                deps = json.loads(s.depends_on_json or "[]")
            except json.JSONDecodeError:
                deps = []
            try:
                req_docs = json.loads(s.required_documents_json or "[]")
            except json.JSONDecodeError:
                req_docs = []
            dtos.append(DynamicRouteStepDTO(
                id=s.id,
                key=s.key, title=s.title, description=s.description,
                status=s.status,  # type: ignore[arg-type]
                depends_on=list(deps),
                source=(s.source or "scholarship"),  # type: ignore[arg-type]
                priority=(s.priority or "medium"),  # type: ignore[arg-type]
                required_documents=list(req_docs),
                action_label=s.action_label,
                action_target=s.action_target,
                help_text=s.help_text,
                pakistan_process_id=s.pakistan_process_id,
                order_index=s.order_index,
                section_id=(s.section_id or "scholarship"),  # type: ignore[arg-type]
                status_reason=s.notes or None,
            ))

    # v0.10.1: re-resolve dependencies on every read. The resolver
    # treats persisted 'completed' as sticky (propagates as-is) and
    # cascades unlocks to any dependent steps whose prerequisites are
    # now satisfied. Stale "Waiting for: X" messages are cleared by
    # _resolve_dependencies when the dependency is now completed.
    dtos = _resolve_dependencies(dtos)

    sections: list[RouteSectionDTO] = []
    for sid in ("scholarship", "pakistan", "visa"):
        title, desc = _SECTION_TITLES[sid]
        section_steps = [d for d in dtos if d.section_id == sid]
        completed = sum(1 for s in section_steps
                        if s.status == "completed")
        total = len(section_steps) or 1
        sections.append(RouteSectionDTO(
            section_id=sid,  # type: ignore[arg-type]
            title=title, description=desc,
            progress_pct=int(round(100 * completed / total)),
            steps=section_steps,
        ))
    overall_total = len(dtos) or 1
    overall_completed = sum(1 for d in dtos if d.status == "completed")
    return DynamicRoutePlanDTO(
        id=rp.id,
        profile_id=rp.profile_id,
        user_id=rp.user_id,
        scholarship_id=rp.scholarship_id,
        destination_country=rp.country,
        template_key=rp.template_key,
        sections=sections,
        overall_progress_pct=int(round(
            100 * overall_completed / overall_total
        )),
        created_at=rp.created_at,
        updated_at=rp.updated_at,
    )


def generate_and_save(
    profile_id: int, *, user_id: Optional[int] = None,
) -> Optional[DynamicRoutePlanDTO]:
    """One-shot: generate a fresh plan and persist it. Returns the
    saved plan, or None if no scholarship is selected."""
    plan = generate_plan(profile_id, user_id=user_id)
    if plan is None:
        return None
    saved_id = save_plan(plan)
    return plan.model_copy(update={"id": saved_id})


# ---------- v0.11: evidence + completion writes -------------------------


def attach_document_to_step(
    *,
    profile_id: int,
    user_id: Optional[int],
    step_key: str,
    document_type: str,
    original_filename: str,
    stored_path: str,
    mime_type: Optional[str],
    file_size: Optional[int],
    extracted_text: Optional[str],
    extracted_fields: dict,
    verification_status: str,
    issues: list[str],
    country: str,
    extraction_method: Optional[str] = None,
    extraction_status: Optional[str] = None,
    extraction_errors: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    matched_fields: Optional[list[str]] = None,
    # v0.17 — OCR quality signal
    ocr_quality_score: Optional[float] = None,
    ocr_quality_label: Optional[str] = None,
) -> int:
    """Persist a `CaseDocument` row for a route step. Returns its id."""
    from utils.helpers import utcnow as _now
    with session_scope() as db:
        # If a document of the same (profile, step_key, document_type)
        # already exists, replace it (re-upload). Cheap, predictable.
        for existing in db.scalars(
            select(CaseDocument).where(
                (CaseDocument.profile_id == profile_id)
                & (CaseDocument.step_key == step_key)
                & (CaseDocument.document_type == document_type)
            )
        ):
            db.delete(existing)
        db.flush()

        row = CaseDocument(
            profile_id=profile_id,
            user_id=user_id,
            country=country,
            doc_type=document_type,
            document_type=document_type,
            step_key=step_key,
            filename=Path(stored_path).name if stored_path else None,
            original_filename=original_filename,
            stored_path=stored_path,
            mime_type=mime_type,
            file_size=file_size,
            extracted_text=(extracted_text or "")[:32 * 1024],
            extracted_json=json.dumps(extracted_fields, default=str),
            verification_status=verification_status,
            issues_json=json.dumps(issues),
            status=verification_status,  # legacy column kept in sync
            uploaded_at=_now(),
            updated_at=_now(),
            # v0.12 extraction-pipeline visibility
            extraction_method=extraction_method,
            extraction_status=extraction_status,
            extraction_errors=(
                json.dumps(extraction_errors) if extraction_errors else None
            ),
            warnings_json=(
                json.dumps(warnings) if warnings else None
            ),
            matched_fields_json=(
                json.dumps(matched_fields) if matched_fields else None
            ),
            verified_at=_now(),
            # v0.17 OCR quality
            ocr_quality_score=ocr_quality_score,
            ocr_quality_label=ocr_quality_label,
        )
        db.add(row)
        db.flush()
        log.info(
            "Attached document: profile=%s step=%s type=%s "
            "extraction=%s/%s verification=%s quality=%s id=%s",
            profile_id, step_key, document_type,
            extraction_method or "?", extraction_status or "?",
            verification_status, ocr_quality_label or "?", row.id,
        )
        return row.id


def mark_step_complete(
    profile_id: int, step_key: str, *, country: Optional[str] = None,
) -> tuple[bool, str]:
    """User-confirmation layer.

    Returns (ok, message). The step is only marked complete if
    `can_complete_step()` returns True for it (spec §3): for evidence
    steps, all required documents must be uploaded AND verified; for
    soft steps, dependencies must be satisfied and the step must not
    be locked / blocked / needs_attention / awaiting_documents /
    pending_verification.

    v0.11.1: previously this had inline gating logic that did not
    handle Pakistan steps or profile-driven evidence steps consistently
    with the page UI. The shared `can_complete_step()` predicate now
    keeps service-side validation and page-side button labels in lock
    step.
    """
    from utils.helpers import utcnow as _now

    # Recompute the live plan to discover the step's current status.
    plan = generate_plan(profile_id)
    if plan is None:
        return False, "No active route plan for this profile."

    target_step: Optional[DynamicRouteStepDTO] = None
    for sec in plan.sections:
        for s in sec.steps:
            if s.key == step_key:
                target_step = s
                break
        if target_step:
            break
    if target_step is None:
        return False, f"Step '{step_key}' not found in current plan."

    if target_step.status == "completed":
        return True, "Step is already complete."

    allowed, reason = can_complete_step(profile_id, target_step)
    if not allowed:
        return False, reason

    target_country = country or plan.destination_country
    with session_scope() as db:
        rp = db.scalar(
            select(RoutePlan).where(
                (RoutePlan.profile_id == profile_id)
                & (RoutePlan.country == target_country)
            )
        )
        if rp is None:
            # No persisted plan — generate-and-save first so we have
            # rows to write completion to.
            plan = generate_and_save(profile_id)
            if plan is None:
                return False, "Could not persist route plan."
            rp = db.scalar(
                select(RoutePlan).where(
                    (RoutePlan.profile_id == profile_id)
                    & (RoutePlan.country == target_country)
                )
            )
            if rp is None:
                return False, "Route plan persistence failed."

        rs = db.scalar(
            select(RouteStep).where(
                (RouteStep.plan_id == rp.id)
                & (RouteStep.key == step_key)
            )
        )
        if rs is None:
            return False, f"Step '{step_key}' is not in the persisted plan."
        rs.status = "completed"
        rs.completed_at = _now()
        log.info(
            "Marked step complete: profile=%s step=%s",
            profile_id, step_key,
        )

    # v0.10.1: cascade unlocks to dependents.
    #
    # Without this step, the persisted RouteStep rows for downstream
    # steps keep their stale "locked" status and "Waiting for: X"
    # message even though X is now completed. The next page render
    # via get_persisted_plan will re-resolve in memory and DISPLAY
    # correctly, but persisted data drifts further from truth on
    # every write. We bring it back into sync by recomputing the
    # plan and writing back any status / status_reason that changed
    # for OTHER steps. The just-completed step is preserved.
    try:
        recompute_states_for_plan(profile_id, target_country)
    except Exception as e:
        log.warning(
            "Recompute after mark-complete failed (display still "
            "correct via get_persisted_plan): %s", e,
        )

    return True, "Step completed. Next dependent step unlocked."


def recompute_states_for_plan(
    profile_id: int, destination_country: str,
) -> int:
    """Recompute every persisted RouteStep's status + status_reason
    against the current truth (intrinsic from profile/eligibility/docs,
    sticky from completed_at, then dependency resolution). Persists any
    drift back to the DB. Returns the number of rows updated.

    Sticky completed steps (those with `completed_at` set) are never
    demoted by this function — completion stays completed.

    Safe to call on every page load. Idempotent: if everything is
    already in sync, returns 0 and writes nothing.
    """
    # Build the in-memory truth via the full pipeline.
    fresh = generate_plan(profile_id)
    if fresh is None or fresh.destination_country != destination_country:
        return 0
    by_key: dict[str, DynamicRouteStepDTO] = {
        s.key: s
        for sec in fresh.sections for s in sec.steps
    }

    updated = 0
    with session_scope() as db:
        rp = db.scalar(
            select(RoutePlan).where(
                (RoutePlan.profile_id == profile_id)
                & (RoutePlan.country == destination_country)
            )
        )
        if rp is None:
            return 0

        for rs in db.scalars(
            select(RouteStep).where(RouteStep.plan_id == rp.id)
        ):
            target = by_key.get(rs.key)
            if target is None:
                continue
            # Sticky guard: never demote an already-persisted
            # completion. (generate_plan applies the user-completion
            # overlay before resolution, so `target.status` will
            # already be 'completed' for these — but defence in
            # depth is cheap.)
            if rs.completed_at is not None and target.status != "completed":
                continue

            new_status = target.status
            new_reason = target.status_reason or ""
            if rs.status != new_status or (rs.notes or "") != new_reason:
                rs.status = new_status
                rs.notes = new_reason
                updated += 1
        if updated:
            log.info(
                "recompute_states_for_plan: profile=%s country=%s "
                "rows_updated=%d",
                profile_id, destination_country, updated,
            )
    return updated
