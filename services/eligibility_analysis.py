"""
services/eligibility_analysis.py
--------------------------------
Post-evaluation analysis for the deterministic eligibility engine.

Takes a freshly computed list of RuleEvaluations plus the source
UserProfile and produces:

  * decision          : ELIGIBLE | CONDITIONALLY_ELIGIBLE | HIGH_RISK | NOT_ELIGIBLE
  * confidence_breakdown by category
  * blocking_issues (failed CRITICAL rules)
  * important_gaps  (failed IMPORTANT rules)
  * risk_flags      (soft signals — late timeline, thin funds, etc.)
  * weakest_area    (one-liner for the dashboard)
  * next_steps      (ordered actionable recommendations)
  * timeline_plan   (backward-planned milestones from target_intake)

Keeps the engine focused on "did the rule pass?" and this module focused
on "what does it all mean?" — both remain 100% deterministic.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from models.orm import UserProfile
from models.schemas import (
    ConfidenceBreakdown,
    EligibilityDecision,
    NextStep,
    ProfileIn,
    RuleEvaluation,
    TimelineItem,
)
from utils.reference_data import (
    FUNDS_STATUS_STRENGTH,
    OFFER_STATUS_STRENGTH,
)


# ---------- Decision mapping ---------------------------------------------


def derive_decision(
    rules: list[RuleEvaluation],
) -> EligibilityDecision:
    """Map rule outcomes + priorities to a final decision state.

    Rules:
      - Any CRITICAL rule outright failed (outcome='failed')     → NOT_ELIGIBLE
      - Any CRITICAL rule missing_evidence                       → CONDITIONALLY_ELIGIBLE
      - Multiple IMPORTANT failures / missing                    → HIGH_RISK
      - Otherwise, all CRITICAL passed                           → ELIGIBLE
    """
    critical_failed = [
        r for r in rules if r.priority == "CRITICAL" and r.outcome == "failed"
    ]
    critical_missing = [
        r for r in rules
        if r.priority == "CRITICAL" and r.outcome == "missing_evidence"
    ]
    important_issues = [
        r for r in rules
        if r.priority == "IMPORTANT"
        and r.outcome in ("failed", "missing_evidence")
    ]

    if critical_failed:
        return "NOT_ELIGIBLE"
    if critical_missing:
        return "CONDITIONALLY_ELIGIBLE"
    if len(important_issues) >= 2:
        return "HIGH_RISK"
    return "ELIGIBLE"


# ---------- Confidence breakdown -----------------------------------------


_CATEGORIES = ("documents", "financial", "academic", "language")


def compute_confidence_breakdown(
    rules: list[RuleEvaluation],
) -> ConfidenceBreakdown:
    """Compute a 0–100 score per category, weighted by rule weight implied
    by priority: CRITICAL=1.0, IMPORTANT=0.6, OPTIONAL=0.3."""
    weight_for = {"CRITICAL": 1.0, "IMPORTANT": 0.6, "OPTIONAL": 0.3}
    score_for = {"passed": 1.0, "missing_evidence": 0.5, "warning": 0.5,
                 "failed": 0.0}

    totals: dict[str, float] = {c: 0.0 for c in _CATEGORIES}
    earned: dict[str, float] = {c: 0.0 for c in _CATEGORIES}

    for r in rules:
        cat = r.category if r.category in _CATEGORIES else "documents"
        w = weight_for.get(r.priority, 0.6)
        s = score_for.get(r.outcome, 0.0)
        totals[cat] += w
        earned[cat] += w * s

    def pct(cat: str) -> int:
        if totals[cat] <= 0:
            return 100  # no rules in this category → not penalised
        return int(round(100 * earned[cat] / totals[cat]))

    return ConfidenceBreakdown(
        documents=pct("documents"),
        financial=pct("financial"),
        academic=pct("academic"),
        language=pct("language"),
    )


def overall_confidence_from_breakdown(b: ConfidenceBreakdown) -> float:
    """Re-compute the single 0.0–1.0 overall confidence from the
    per-category breakdown. Critical categories (documents + financial)
    are weighted more heavily since they block the application."""
    weighted = (
        b.documents * 0.35
        + b.financial * 0.30
        + b.academic * 0.15
        + b.language * 0.20
    )
    return round(weighted / 100.0, 3)


# ---------- Issue buckets -------------------------------------------------


def collect_blocking_issues(rules: Iterable[RuleEvaluation]) -> list[str]:
    return [
        r.description
        for r in rules
        if r.priority == "CRITICAL"
        and r.outcome in ("failed", "missing_evidence")
    ]


def collect_important_gaps(rules: Iterable[RuleEvaluation]) -> list[str]:
    return [
        r.description
        for r in rules
        if r.priority == "IMPORTANT"
        and r.outcome in ("failed", "missing_evidence")
    ]


# ---------- Weakest area --------------------------------------------------


_CATEGORY_LABELS = {
    "documents": "Documents (offer/passport)",
    "financial": "Financial proof",
    "academic":  "Academic record",
    "language":  "Language proficiency",
}


def derive_weakest_area(
    rules: list[RuleEvaluation],
    breakdown: ConfidenceBreakdown,
) -> Optional[str]:
    """Pick the weakest area — first by unresolved CRITICAL issues, then by
    the lowest confidence-breakdown category."""
    # 1. Most severe CRITICAL issue takes precedence
    for r in rules:
        if r.priority == "CRITICAL" and r.outcome in ("failed", "missing_evidence"):
            return f"{_CATEGORY_LABELS.get(r.category, r.category)} — {r.description}"

    # 2. Otherwise, worst-scoring category (if meaningfully weak)
    scores = {
        "documents": breakdown.documents,
        "financial": breakdown.financial,
        "academic": breakdown.academic,
        "language": breakdown.language,
    }
    worst_cat, worst_score = min(scores.items(), key=lambda kv: kv[1])
    if worst_score < 80:
        return f"{_CATEGORY_LABELS[worst_cat]} ({worst_score}%)"
    return None


# ---------- Risk flags ---------------------------------------------------


def derive_risk_flags(
    profile: ProfileIn | UserProfile,
    rules: list[RuleEvaluation],
) -> list[str]:
    """Soft signals that don't block the visa but reduce success odds."""
    flags: list[str] = []

    # Travel history
    travel = getattr(profile, "previous_travel_history", None) or ""
    if not travel.strip():
        flags.append(
            "No previous international travel history on file — may reduce "
            "credibility with some missions."
        )

    # Funds barely sufficient
    funds_status = getattr(profile, "proof_of_funds_status", None) or ""
    if FUNDS_STATUS_STRENGTH.get(funds_status) == "partial":
        flags.append(
            "Proof of funds only partially prepared — full financial "
            "evidence will be required before submission."
        )

    # Conditional-only offer
    offer_status = getattr(profile, "offer_letter_status", None) or ""
    if OFFER_STATUS_STRENGTH.get(offer_status) == "partial":
        flags.append(
            "Only a conditional offer is available — an unconditional offer "
            "or CAS/Zulassungsbescheid will be required before the visa "
            "application."
        )

    # Borderline language
    test_type = getattr(profile, "english_test_type", None) or ""
    score = getattr(profile, "english_test_score", None) or 0
    if test_type and test_type.lower().startswith("ielts") and 0 < float(score) < 6.0:
        flags.append(
            f"IELTS score {score} is borderline for many institutions; "
            f"consider a retake for a stronger profile."
        )

    # Late timeline
    target = getattr(profile, "target_intake", None) or ""
    month_year = _parse_intake(target)
    if month_year is not None:
        months_away = _months_until(month_year[0], month_year[1])
        if months_away is not None and months_away < 6:
            flags.append(
                f"Target intake ({target}) is only ~{months_away} month(s) "
                f"away — visa processing and document gathering may not fit."
            )

    # Passport near expiry
    passport = getattr(profile, "passport_valid_until", None)
    if passport:
        try:
            exp = date.fromisoformat(str(passport)[:10])
            days_left = (exp - date.today()).days
            if 0 <= days_left < 365:
                flags.append(
                    f"Passport expires within a year ({passport}); consider "
                    f"renewing before the visa application."
                )
        except ValueError:
            pass

    return flags


# ---------- Next steps ---------------------------------------------------


_PRIORITY_ORDER = {"CRITICAL": 0, "IMPORTANT": 1, "OPTIONAL": 2}

# Fallback generic guidance for rules that predate v0.3 metadata
_GENERIC_WHY = "This requirement affects your visa application."
_GENERIC_WHAT = "Review the evidence requirements and prepare the missing items."


def build_next_steps(rules: list[RuleEvaluation]) -> list[NextStep]:
    """Produce an ordered, actionable next-steps list from failed/partial
    rules. Sorted by priority, then by outcome severity."""
    items: list[NextStep] = []
    outcome_rank = {"failed": 0, "missing_evidence": 1, "warning": 2}

    for r in rules:
        if r.outcome in ("passed",):
            continue
        if r.outcome == "warning":
            # Include only if priority is CRITICAL/IMPORTANT
            if r.priority == "OPTIONAL":
                continue
        items.append(
            NextStep(
                rule_id=r.rule_id,
                title=_short_title(r),
                priority=r.priority,
                what_to_do=r.what_to_do or _GENERIC_WHAT,
                why_it_matters=r.why_it_matters or _GENERIC_WHY,
                estimated_time=r.estimated_time,
            )
        )

    items.sort(
        key=lambda s: (
            _PRIORITY_ORDER.get(s.priority, 99),
            outcome_rank.get("failed" if s.priority == "CRITICAL" else "missing_evidence", 99),
        )
    )
    return items


def _short_title(r: RuleEvaluation) -> str:
    """Short, imperative-ish title for a next step."""
    desc = r.description.strip()
    # Keep it under ~70 chars
    return desc if len(desc) <= 70 else desc[:67].rstrip() + "…"


# ---------- Timeline -----------------------------------------------------


_MONTH_LOOKUP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # abbreviations
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_intake(target_intake: str) -> Optional[tuple[int, int]]:
    """Parse strings like 'September 2027' → (2027, 9)."""
    if not target_intake:
        return None
    parts = target_intake.replace(",", " ").split()
    month = None
    year = None
    for p in parts:
        low = p.lower()
        if low in _MONTH_LOOKUP:
            month = _MONTH_LOOKUP[low]
        elif low.isdigit() and len(low) == 4:
            year = int(low)
    if month is None or year is None:
        return None
    return (year, month)


def _months_until(year: int, month: int, *, from_today: Optional[date] = None) -> Optional[int]:
    today = from_today or date.today()
    return (year - today.year) * 12 + (month - today.month)


def _shift_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return (year, month) shifted by `delta` months (can be negative)."""
    total = (year * 12 + (month - 1)) + delta
    y, m0 = divmod(total, 12)
    return (y, m0 + 1)


def _month_name(month: int) -> str:
    return [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ][month - 1]


def _format_window(year: int, month: int, span: int = 1) -> str:
    """Render a month/year window. span=1 → 'March 2027'; span=2 → 'Mar–Apr 2027'."""
    if span <= 1:
        return f"{_month_name(month)} {year}"
    y2, m2 = _shift_months(year, month, span - 1)
    if y2 == year:
        return f"{_month_name(month)[:3]}\u2013{_month_name(m2)[:3]} {year}"
    return f"{_month_name(month)[:3]} {year} \u2013 {_month_name(m2)[:3]} {y2}"


# Backward offsets from intake, in months.
# Each tuple: (step title, category, months_before_intake, window_span)
_TIMELINE_TEMPLATE: list[tuple[str, str, int, int]] = [
    ("Take/retake language test (IELTS/TOEFL/TestDaF)", "language", 12, 2),
    ("Apply to universities", "academic",               10, 2),
    ("Receive offer / CAS / Zulassungsbescheid", "documents", 6, 2),
    ("Prepare financial proof (GIC, Sperrkonto, statements)", "financial", 4, 1),
    ("Gather document checklist & certified translations", "documents", 4, 1),
    ("Apply for visa", "documents", 2, 1),
    ("Biometrics / interview", "documents", 1, 1),
]


def build_timeline_plan(
    profile: ProfileIn | UserProfile,
) -> list[TimelineItem]:
    """Generate a backward-planned timeline from the user's target intake."""
    intake = _parse_intake(getattr(profile, "target_intake", None) or "")
    if intake is None:
        return []

    year, month = intake
    items: list[TimelineItem] = []
    for title, category, months_before, span in _TIMELINE_TEMPLATE:
        y, m = _shift_months(year, month, -months_before)
        items.append(
            TimelineItem(
                step=title,
                recommended_by=_format_window(y, m, span),
                category=category,  # type: ignore[arg-type]
            )
        )
    return items
