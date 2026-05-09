"""services/readiness_service.py
--------------------------------
v0.18 (Phase 6): Deterministic Readiness Engine.

Computes an overall readiness score (0–100) from four weighted
dimensions. Pure computation — no LLM, no DB writes. Called by
the dashboard and AI context builder.

Scoring model:

  Profile completeness    20%
  Eligibility strength    20%
  Scholarship fit         20%
  Route progress          30%
  Documents uploaded      advisory only — not part of score

Total 100 → levels: Low (0–39) | Moderate (40–64) | High (65–84) | Ready (85+)
"""
from __future__ import annotations

from typing import Any, Optional

from utils.logger import get_logger

log = get_logger(__name__)


# ---------- Thresholds ---------------------------------------------------

_IELTS_THRESHOLDS: dict[str, float] = {
    "UK":      6.5,
    "Canada":  6.0,
    "Germany": 6.0,
}

_READINESS_LEVELS: list[tuple[int, str]] = [
    (85, "Ready"),
    (65, "High"),
    (40, "Moderate"),
    (0,  "Low"),
]


# ---------- Helpers -------------------------------------------------------

def _pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return min(100.0, max(0.0, 100.0 * numerator / denominator))


def _level_for(score: float) -> str:
    for threshold, label in _READINESS_LEVELS:
        if score >= threshold:
            return label
    return "Low"


# ---------- Profile score (20 points max) --------------------------------

_PROFILE_REQUIRED = [
    "full_name", "nationality", "destination_country",
    "education_level", "intended_degree_level",
]
_PROFILE_IMPORTANT = [
    "english_test_type", "english_test_score",
    "offer_letter_status", "proof_of_funds_status",
    "gpa", "field_of_study",
]


def _score_profile(profile) -> float:
    """Returns 0–100 representing profile completeness."""
    if profile is None:
        return 0.0
    required_score = sum(
        1 for k in _PROFILE_REQUIRED
        if getattr(profile, k, None) not in (None, "", "Not sure", "Not required / unsure")
    ) / len(_PROFILE_REQUIRED)
    important_score = sum(
        1 for k in _PROFILE_IMPORTANT
        if getattr(profile, k, None) not in (None, "", "Not sure", "Not required / unsure")
    ) / len(_PROFILE_IMPORTANT)
    return _pct(required_score * 0.6 + important_score * 0.4, 1.0)


# ---------- Eligibility score (20 points max) ----------------------------

_ELIGIBILITY_WEIGHTS: dict[str, float] = {
    "ELIGIBLE":               1.0,
    "CONDITIONALLY_ELIGIBLE": 0.65,
    "HIGH_RISK":              0.35,
    "NOT_ELIGIBLE":           0.0,
}


def _score_eligibility(eligibility_report) -> float:
    """Returns 0–100 from the deterministic eligibility decision."""
    if eligibility_report is None:
        return 0.0
    # Accepts either an EligibilityReport ORM / DTO or a plain dict
    if isinstance(eligibility_report, dict):
        decision = eligibility_report.get("decision", "")
    else:
        decision = getattr(eligibility_report, "decision", "") or ""
    return _pct(_ELIGIBILITY_WEIGHTS.get(decision, 0.0), 1.0)


# ---------- Scholarship score (20 points max) ----------------------------

def _score_scholarship(selected_scholarship) -> float:
    """Returns 0–100 based on whether a scholarship is selected + fit."""
    if selected_scholarship is None:
        return 0.0
    # If we have a score attribute (from the matching engine), use it
    score_attr = getattr(selected_scholarship, "score", None)
    if score_attr is None and isinstance(selected_scholarship, dict):
        score_attr = selected_scholarship.get("score")
    if score_attr is not None:
        try:
            return _pct(float(score_attr), 100.0)
        except (TypeError, ValueError):
            pass
    # Scholarship selected but no match score available — give partial credit
    return 60.0


# ---------- Route progress score (30 points max) -------------------------

def _score_route(route_plan) -> float:
    """Returns 0–100 from the proportion of completed steps."""
    if route_plan is None:
        return 0.0
    # Accepts DynamicRoutePlanDTO or dict
    if isinstance(route_plan, dict):
        pct = route_plan.get("overall_progress_pct", 0)
        return float(pct)
    pct = getattr(route_plan, "overall_progress_pct", None)
    if pct is not None:
        return float(pct)
    # Manual count if pct not available
    total = completed = 0
    sections = getattr(route_plan, "sections", []) or []
    for sec in sections:
        for step in (getattr(sec, "steps", []) or []):
            total += 1
            if getattr(step, "status", "") == "completed":
                completed += 1
    return _pct(completed, total)


# ---------- Documents score (10 points max) ------------------------------

def _score_documents(documents: list | None) -> float:
    """Returns 0–100 based on how many documents are on file.

    Advisory only. We reward any upload effort — this never blocks.
    5+ documents → 100%; 0 → 0%.
    """
    if not documents:
        return 0.0
    count = len(documents)
    return min(100.0, count * 20.0)  # 5 docs → 100%


# ---------- Main API ------------------------------------------------------


def compute_readiness(
    *,
    profile,
    eligibility_report=None,
    selected_scholarship=None,
    route_plan=None,
    documents: Optional[list] = None,
) -> dict[str, Any]:
    """Compute the readiness score for a student.

    All arguments are optional — missing values score 0 for their
    dimension rather than crashing.

    Returns:
        {
          "score": int,
          "level": str,
          "breakdown": {
              "profile": float,
              "eligibility": float,
              "scholarship_fit": float,
              "route_progress": float,
          },
          "documents_advisory": int,
          "summary": str,
        }
    """
    p_profile   = _score_profile(profile)
    p_elig      = _score_eligibility(eligibility_report)
    p_scholar   = _score_scholarship(selected_scholarship)
    p_route     = _score_route(route_plan)
    p_docs      = _score_documents(documents)

    # Weighted composite — documents are advisory only and do not affect readiness.
    score = (
        p_profile   * 0.25
        + p_elig    * 0.25
        + p_scholar * 0.20
        + p_route   * 0.30
    )
    score_int = round(score)
    level = _level_for(score)

    breakdown = {
        "profile":         round(p_profile),
        "eligibility":     round(p_elig),
        "scholarship_fit": round(p_scholar),
        "route_progress":  round(p_route),
    }

    # Generate a one-sentence human summary
    weakest = min(breakdown, key=breakdown.get)  # type: ignore[arg-type]
    _weakness_labels = {
        "profile":         "complete your profile",
        "eligibility":     "strengthen your eligibility",
        "scholarship_fit": "select a matched scholarship",
        "route_progress":  "progress through your route plan",
    }
    if level == "Ready":
        summary = (
            "Your application looks strong. Keep your documents "
            "up to date and proceed to scholarship submission."
        )
    elif level == "High":
        summary = (
            f"You're in good shape. Focus on: "
            f"{_weakness_labels.get(weakest, weakest)}."
        )
    elif level == "Moderate":
        summary = (
            f"Moderate readiness. Priority action: "
            f"{_weakness_labels.get(weakest, weakest)}."
        )
    else:
        summary = (
            "Low readiness. Several key areas need attention before "
            f"applying — start with: {_weakness_labels.get(weakest, weakest)}."
        )

    log.debug(
        "compute_readiness: score=%d level=%s breakdown=%s",
        score_int, level, breakdown,
    )
    return {
        "score": score_int,
        "level": level,
        "breakdown": breakdown,
        "documents_advisory": round(p_docs),
        "summary": summary,
    }
