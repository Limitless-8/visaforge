"""
services/journey_service.py
---------------------------
Deterministic user-journey state.

Every flag is computed directly from the DB / session, never from the
LLM. The dashboard and page-access guards both read from here, so the
whole journey stays coherent no matter where the user clicks.

Journey order:
    profile_complete
        → country_selected
            → eligibility_completed
                → scholarship_selected
                    → route_plan_generated
                        → documents_started

Notes:
  * `country_selected` is implied by `profile_complete` in the current
    model (destination_country is a required profile field). The flag is
    kept separate so the UI can still render it explicitly in the
    progress bar and so a later "country picker" screen could split it
    out cleanly.
  * A scholarship is considered "selected" if the user has bookmarked
    at least one scholarship. This preserves today's Scholarships page
    behaviour while preparing the structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from db.database import session_scope
from models.orm import (
    CaseDocument,
    EligibilityResult,
    RoutePlan,
    SavedScholarship,
    UserProfile,
)
from services.profile_service import get_profile, list_profiles_for_user
from utils.logger import get_logger

log = get_logger(__name__)


# ---------- Profile completeness -----------------------------------------

# Fields required for a profile to count as "complete". Keep in sync
# with the intake form on pages/1_Profile.py.
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = (
    "full_name",
    "nationality",
    "country_of_residence",
    "destination_country",
    "intended_degree_level",
)


def is_profile_complete(profile: Optional[UserProfile]) -> bool:
    """Deterministic profile-completeness check. True iff every required
    field has a non-empty value."""
    if profile is None:
        return False
    for field in REQUIRED_PROFILE_FIELDS:
        value = getattr(profile, field, None)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def missing_profile_fields(profile: Optional[UserProfile]) -> list[str]:
    """Human-readable list of missing required fields for the dashboard."""
    pretty = {
        "full_name": "Full name",
        "nationality": "Nationality",
        "country_of_residence": "Country of residence",
        "passport_valid_until": "Passport validity date",
        "education_level": "Highest education level",
        "destination_country": "Destination country",
        "intended_degree_level": "Intended degree level",
        "field_of_study": "Intended field(s) of study",
        "offer_letter_status": "Offer / admission letter status",
        "proof_of_funds_status": "Proof of funds status",
    }
    if profile is None:
        return list(pretty.values())
    gaps: list[str] = []
    for field in REQUIRED_PROFILE_FIELDS:
        value = getattr(profile, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            gaps.append(pretty.get(field, field))
    return gaps


# ---------- Journey state dataclass --------------------------------------

@dataclass
class JourneyStatus:
    """Deterministic snapshot of where the user is in the journey."""
    # Stage flags (in order)
    profile_complete: bool = False
    country_selected: bool = False
    eligibility_completed: bool = False
    scholarship_selected: bool = False
    route_plan_generated: bool = False
    documents_started: bool = False

    # Supporting data for the dashboard
    profile_id: Optional[int] = None
    destination_country: Optional[str] = None
    selected_scholarship_id: Optional[int] = None
    latest_eligibility_decision: Optional[str] = None
    documents_completed: int = 0
    documents_total: int = 0

    def stage_flags(self) -> list[tuple[str, bool]]:
        """Ordered list of (human name, completed) for progress rendering.

        v0.16 (Phase 5.7) — per spec §1, document upload is no longer
        a journey gate. The five gates are: profile, destination,
        eligibility, scholarship, route_plan. Documents become
        optional/supporting and are surfaced separately on the
        dashboard.
        """
        return [
            ("Complete profile", self.profile_complete),
            ("Run eligibility check", self.eligibility_completed),
            ("Select a scholarship", self.scholarship_selected),
            ("Generate route plan", self.route_plan_generated),
        ]

    def progress_ratio(self) -> float:
        """Completed-only journey progress.

        Does not count the current active step as complete.
        Example: profile, eligibility, and scholarship complete = 3/4 = 75%.
        """
        flags = self.stage_flags()
        done = sum(1 for _, ok in flags if ok)
        return done / len(flags) if flags else 0.0

    def current_step(self) -> tuple[str, Optional[str]]:
        """Return (friendly next-step name, target page path) or
        (final message, None) when the journey is complete.

        v0.16 (Phase 5.7) — documents_started is NO LONGER part of the
        next-step chain. Once the route plan is generated the journey
        is "complete" from the gating perspective; the user can
        continue working on individual route steps and (optionally)
        upload documents on the Documents page. The dashboard
        renders a separate "Continue your route" CTA in that state.
        """
        mapping: list[tuple[bool, str, str]] = [
            (self.profile_complete,
             "Complete your profile", "pages/1_Profile.py"),
            (self.eligibility_completed,
             "Run your eligibility check", "pages/2_Eligibility.py"),
            (self.scholarship_selected,
             "Explore and save a scholarship", "pages/4_Scholarships.py"),
            (self.route_plan_generated,
             "Generate your route plan", "pages/3_Route_Plan.py"),
        ]
        for done, label, target in mapping:
            if not done:
                return (label, target)
        # All five gates met. Point the user at the Route Plan to
        # continue working on individual steps; the dashboard layer
        # may further refine this via get_next_actionable_step().
        return (
            "Continue working through your route plan",
            "pages/3_Route_Plan.py",
        )


# ---------- Builder -------------------------------------------------------

def compute_journey(user_id: int) -> JourneyStatus:
    """Build a JourneyStatus snapshot for the given user. Safe to call
    on every page render — all checks are short, indexed lookups."""
    if user_id is None:
        return JourneyStatus()

    status = JourneyStatus()

    # Pick the most recent profile belonging to the user.
    profiles = list_profiles_for_user(user_id)
    if not profiles:
        return status

    profile = profiles[0]  # list is already ordered by created_at desc
    status.profile_id = profile.id
    status.destination_country = profile.destination_country
    status.profile_complete = is_profile_complete(profile)
    status.country_selected = bool(
        profile.destination_country
        and str(profile.destination_country).strip()
    )

    # ---- Eligibility ----
    with session_scope() as db:
        latest = db.scalars(
            select(EligibilityResult)
            .where(EligibilityResult.profile_id == profile.id)
            .order_by(EligibilityResult.created_at.desc())
        ).first()
        if latest is not None:
            status.eligibility_completed = True
            status.latest_eligibility_decision = latest.status

        # ---- Scholarship selection ----
        # v0.6: an explicit `is_selected` row trumps a generic bookmark.
        # Fall back to any saved row for back-compat with v0.5.
        selected = db.scalars(
            select(SavedScholarship)
            .where(
                (SavedScholarship.profile_id == profile.id)
                & (SavedScholarship.is_selected.is_(True))
            )
        ).first()
        if selected is None:
            selected = db.scalars(
                select(SavedScholarship)
                .where(SavedScholarship.profile_id == profile.id)
                .order_by(SavedScholarship.created_at.desc())
            ).first()
        if selected is not None:
            status.scholarship_selected = True
            status.selected_scholarship_id = selected.scholarship_id

        # ---- Route plan ----
        # v0.10: route_plan_generated is true only when ALL of these hold:
        #   * a profile exists (already true to reach this branch)
        #   * an eligibility check has been completed
        #   * a scholarship is selected
        #   * a RoutePlan row exists for (profile, destination_country)
        # The first three are derived above; combining them keeps the
        # journey card honest if a plan was generated long ago and the
        # user later cleared their scholarship selection.
        plan = db.scalars(
            select(RoutePlan)
            .where(
                (RoutePlan.profile_id == profile.id)
                & (RoutePlan.country == profile.destination_country)
            )
        ).first()
        plan_exists = plan is not None

        # Route plan is only considered valid if:
        #   1. eligibility is complete
        #   2. scholarship is selected
        #   3. route plan exists
        #   4. selected scholarship still matches the route plan
        #
        # This keeps dashboard + journey progress synchronized when
        # users change scholarships or regenerate plans.

        scholarship_matches_route = True

        if (
            plan is not None
            and hasattr(plan, "scholarship_id")
            and status.selected_scholarship_id is not None
        ):
            scholarship_matches_route = (
                plan.scholarship_id == status.selected_scholarship_id
            )

        if (
            plan_exists
            and status.eligibility_completed
            and status.scholarship_selected
            and scholarship_matches_route
        ):
            status.route_plan_generated = True

        # ---- Documents (started = any doc with status != pending) ----
        docs = list(db.scalars(
            select(CaseDocument).where(
                (CaseDocument.profile_id == profile.id)
                & (CaseDocument.country == profile.destination_country)
            )
        ))
        status.documents_total = len(docs)
        status.documents_completed = sum(
            1 for d in docs if d.status in ("uploaded", "verified")
        )
        status.documents_started = any(
            d.status != "pending" for d in docs
        )

    return status


# ---------- Per-page gating -----------------------------------------------

# Which stage flag does each page require?
# None means the page is unconditionally accessible for logged-in users.
_PAGE_REQUIREMENT: dict[str, tuple[Optional[str], Optional[str]]] = {
    # page_key                 -> (required_stage_flag, redirect_label)
    "profile":      (None, None),
    "eligibility":  ("profile_complete",
                     "Complete your profile first."),
    "scholarships": ("eligibility_completed",
                     "Run your eligibility check first."),
    "route_plan":   ("eligibility_completed",
                     "Run your eligibility check first."),
    "documents":    ("route_plan_generated",
                     "Generate a route plan first."),
    "ai_assistant": (None, None),  # accessible; soft-warn elsewhere
    "dashboard":    (None, None),
}


def require_stage(page_key: str, status: JourneyStatus) -> Optional[tuple[str, str]]:
    """Return (warning_message, redirect_page_path) if the page is locked,
    else None. Pages call this and render a friendly block if it returns
    a tuple."""
    if page_key not in _PAGE_REQUIREMENT:
        return None
    required, message = _PAGE_REQUIREMENT[page_key]
    if required is None:
        return None
    if getattr(status, required, False):
        return None

    # Find the page the user must visit to satisfy the requirement.
    redirect = {
        "profile_complete": "pages/1_Profile.py",
        "country_selected": "pages/1_Profile.py",
        "eligibility_completed": "pages/2_Eligibility.py",
        "scholarship_selected": "pages/4_Scholarships.py",
        "route_plan_generated": "pages/3_Route_Plan.py",
    }.get(required, "pages/7_Dashboard.py")

    return (message or "This step is locked until earlier ones are complete.",
            redirect)


# ---------- Selected-scholarship helper (session bridge) ------------------

def selected_scholarship_for_user(user_id: int) -> Optional[int]:
    """Return the scholarship id the user has selected as their target
    (is_selected=True), falling back to the most recently saved one
    for back-compat. Returns None if nothing saved yet."""
    if not user_id:
        return None
    with session_scope() as db:
        # Prefer explicit selection
        row = db.scalars(
            select(SavedScholarship)
            .join(
                UserProfile,
                UserProfile.id == SavedScholarship.profile_id,
            )
            .where(
                (UserProfile.user_id == user_id)
                & (SavedScholarship.is_selected.is_(True))
            )
            .order_by(SavedScholarship.created_at.desc())
        ).first()
        if row is not None:
            return row.scholarship_id
        # Fallback: any saved
        row = db.scalars(
            select(SavedScholarship)
            .join(
                UserProfile,
                UserProfile.id == SavedScholarship.profile_id,
            )
            .where(UserProfile.user_id == user_id)
            .order_by(SavedScholarship.created_at.desc())
        ).first()
        return row.scholarship_id if row else None
