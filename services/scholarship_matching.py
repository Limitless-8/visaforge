"""
services/scholarship_matching.py
--------------------------------
Deterministic Scholarship Matching Engine (v0.7).

Given a user profile and a scholarship, produce a transparent weighted
fit score. No AI. No network. Pure function.

v0.7 changes:
  * New weight scheme (matches the v0.7 spec):
      eligibility (nationality + destination + degree)   25%
      gpa                                                 20%
      english                                             20%
      field of study                                      15%
      readiness (offer + funds combined)                  10%
      deadline proximity                                  10%
  * Profile-aware fallback: when a scholarship has no structured
    `eligibility` block, the engine still consults the scholarship's
    free-text fields (`country`, `degree_level`, `field_of_study`).
    Only when BOTH structured AND free-text data are missing is a
    criterion marked "unknown".
  * Three-bucket output:
      - matched_criteria   → strength == "pass"
      - missing_criteria   → strength in ("fail", "partial")  (true gaps)
      - unknown_criteria   → strength == "unknown"            (data gap)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Iterable, Optional

from config.settings import SEEDS_DIR
from models.orm import ScholarshipEntry, UserProfile
from models.schemas import (
    CriterionResult,
    ProfileIn,
    ScholarshipEligibility,
    ScholarshipFitReport,
)
from utils.helpers import safe_load_json
from utils.logger import get_logger
from utils.reference_data import (
    FUNDS_STATUS_STRENGTH,
    OFFER_STATUS_STRENGTH,
    normalize_fields,
)

log = get_logger(__name__)


# ---------- Reference data (named nationality groups) --------------------


@lru_cache(maxsize=1)
def _nationality_groups() -> dict[str, set[str]]:
    doc = safe_load_json(SEEDS_DIR / "nationality_groups.json") or {}
    out: dict[str, set[str]] = {}
    for key, body in (doc.get("groups") or {}).items():
        dems = body.get("demonyms") or []
        out[key] = {d.strip() for d in dems if isinstance(d, str)}
    return out


def _resolve_nationality_set(value: Any) -> tuple[Optional[set[str]], str]:
    """Resolve `eligible_nationalities` to (set or None, label)."""
    if value is None:
        return (None, "unspecified")
    if isinstance(value, str):
        if value.strip().lower() == "any":
            return (None, "any")
        group = _nationality_groups().get(value.strip())
        if group is not None:
            return (group, f"group:{value.strip()}")
        return (None, f"unknown-group:{value}")
    if isinstance(value, (list, tuple, set)):
        return ({str(v).strip() for v in value if v}, "list")
    return (None, "unrecognised")


# ---------- Eligibility extraction ---------------------------------------


def _eligibility_of(
    scholarship: ScholarshipEntry | dict,
) -> Optional[ScholarshipEligibility]:
    """Pull the structured eligibility block off a scholarship row."""
    blob: Any = None
    if isinstance(scholarship, dict):
        blob = scholarship.get("eligibility") or scholarship.get(
            "eligibility_json"
        )
    else:
        blob = getattr(scholarship, "eligibility_json", None)
    if not blob:
        return None
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except json.JSONDecodeError:
            log.warning(
                "Could not parse eligibility_json on scholarship %r",
                getattr(scholarship, "title", "?"),
            )
            return None
    if not isinstance(blob, dict):
        return None
    try:
        return ScholarshipEligibility(**blob)
    except Exception as e:
        log.warning("Bad eligibility shape: %s", e)
        return None


def _scholarship_field(
    scholarship: ScholarshipEntry | dict, name: str
) -> Optional[str]:
    """Read a top-level scholarship attribute (`country`,
    `degree_level`, `field_of_study`, `deadline`) off either an ORM row
    or a dict, returning the stripped string or None."""
    if isinstance(scholarship, dict):
        v = scholarship.get(name)
    else:
        v = getattr(scholarship, name, None)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


# ---------- v0.7 weights -------------------------------------------------

# Weights sum to 1.0. Matches the published v0.7 scoring rubric.
_WEIGHTS = {
    "eligibility":      0.25,   # nationality + destination + degree
    "gpa":              0.20,
    "english":          0.20,
    "field":            0.15,
    "readiness":        0.10,   # offer + funds combined
    "deadline":         0.10,
}


# ---------- helpers ------------------------------------------------------

def _normalize(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _degree_matches(intended: str, accepted: list[str]) -> bool:
    a = _normalize(intended).replace("'", "").replace("’", "")
    if not a:
        return False
    for level in accepted:
        b = _normalize(level).replace("'", "").replace("’", "")
        if not b:
            continue
        if a == b or a in b or b in a:
            return True
    return False


# ---------- Criterion scorers --------------------------------------------


def _score_eligibility(
    profile: ProfileIn | UserProfile,
    elig: Optional[ScholarshipEligibility],
    scholarship: ScholarshipEntry | dict,
) -> CriterionResult:
    """Combined nationality + destination + degree-level rule.

    This is the v0.7 "Eligibility rules" criterion (25% weight). All
    three sub-checks must broadly pass; any single hard miss caps this
    criterion at 'fail' and short-circuits the entire match to
    not_eligible (handled by the caller).
    """
    weight = _WEIGHTS["eligibility"]
    nat_profile = _normalize(getattr(profile, "nationality", ""))
    dest_profile = _normalize(getattr(profile, "destination_country", ""))
    intended_degree = (
        getattr(profile, "intended_degree_level", "") or ""
    ).strip()

    # ----- destination -----
    dest_required = (
        _normalize(elig.destination_country) if elig and elig.destination_country
        else _normalize(_scholarship_field(scholarship, "country"))
    )
    if dest_required and dest_profile and dest_required != dest_profile:
        return CriterionResult(
            key="eligibility", label="Eligibility (nationality + destination + degree)",
            weight=weight, earned=0.0, strength="fail",
            detail=(
                f"Scholarship is for {dest_required.title()} but your "
                f"destination is {dest_profile.title()}."
            ),
        )

    # ----- exclusion -----
    excluded = set(elig.excluded_nationalities) if elig else set()
    if nat_profile and any(_normalize(x) == nat_profile for x in excluded):
        return CriterionResult(
            key="eligibility", label="Eligibility (nationality + destination + degree)",
            weight=weight, earned=0.0, strength="fail",
            detail=(
                f"{getattr(profile, 'nationality', '')} nationals are "
                f"excluded from this scholarship."
            ),
        )

    # ----- nationality whitelist -----
    nationality_strength: str          # "pass" | "unknown" | "fail"
    nationality_detail: str
    if elig is None or elig.eligible_nationalities is None:
        if nat_profile:
            nationality_strength = "unknown"
            nationality_detail = (
                "Eligible nationalities not specified by this source."
            )
        else:
            nationality_strength = "unknown"
            nationality_detail = "Your profile doesn't list a nationality."
    else:
        allowed, group_label = _resolve_nationality_set(
            elig.eligible_nationalities
        )
        if allowed is None:
            nationality_strength = "pass"
            nationality_detail = f"Open to all nationalities ({group_label})."
        elif not nat_profile:
            nationality_strength = "unknown"
            nationality_detail = (
                "Your profile doesn't list a nationality yet."
            )
        elif any(_normalize(x) == nat_profile for x in allowed):
            nationality_strength = "pass"
            nationality_detail = (
                f"Your nationality "
                f"({getattr(profile, 'nationality', '')}) is on the "
                f"eligibility list ({group_label})."
            )
        else:
            return CriterionResult(
                key="eligibility",
                label="Eligibility (nationality + destination + degree)",
                weight=weight, earned=0.0, strength="fail",
                detail=(
                    f"Your nationality "
                    f"({getattr(profile, 'nationality', '')}) is not on "
                    f"this scholarship's eligibility list ({group_label})."
                ),
            )

    # ----- degree level -----
    accepted_levels: list[str] = []
    degree_strength: str
    degree_detail: str
    if elig and elig.degree_levels:
        accepted_levels = list(elig.degree_levels)
    else:
        raw = _scholarship_field(scholarship, "degree_level")
        if raw:
            accepted_levels = [raw]

    if not accepted_levels:
        degree_strength = "unknown"
        degree_detail = "Degree level not specified by this source."
    elif not intended_degree:
        degree_strength = "unknown"
        degree_detail = (
            "Your profile doesn't specify an intended degree level."
        )
    elif _degree_matches(intended_degree, accepted_levels):
        degree_strength = "pass"
        degree_detail = (
            f"Intended {intended_degree} matches the scholarship "
            f"({', '.join(accepted_levels)})."
        )
    else:
        return CriterionResult(
            key="eligibility",
            label="Eligibility (nationality + destination + degree)",
            weight=weight, earned=0.0, strength="fail",
            detail=(
                f"Intended {intended_degree} doesn't match accepted "
                f"levels ({', '.join(accepted_levels)})."
            ),
        )

    # ----- combine sub-results -----
    strengths = [nationality_strength, degree_strength]
    if dest_required:
        strengths.append("pass")  # destination matched (or unspecified)

    pass_count = strengths.count("pass")
    unknown_count = strengths.count("unknown")

    if pass_count == len(strengths):
        return CriterionResult(
            key="eligibility",
            label="Eligibility (nationality + destination + degree)",
            weight=weight, earned=weight, strength="pass",
            detail=(
                f"Eligible: {nationality_detail} {degree_detail}".strip()
            ),
        )
    # Mixed pass + unknown → partial credit
    if unknown_count and pass_count:
        ratio = pass_count / len(strengths)
        return CriterionResult(
            key="eligibility",
            label="Eligibility (nationality + destination + degree)",
            weight=weight, earned=weight * (0.4 + 0.4 * ratio),
            strength="partial",
            detail=(
                f"Partial: {nationality_detail} {degree_detail}".strip()
            ),
        )
    # All unknown
    return CriterionResult(
        key="eligibility",
        label="Eligibility (nationality + destination + degree)",
        weight=weight, earned=weight * 0.5, strength="unknown",
        detail=(
            "Eligibility unspecified by this source — verify directly "
            "before applying."
        ),
    )


def _score_gpa(
    profile: ProfileIn | UserProfile,
    elig: Optional[ScholarshipEligibility],
) -> CriterionResult:
    weight = _WEIGHTS["gpa"]
    gpa = getattr(profile, "gpa", None) or 0.0
    min_gpa = elig.min_gpa_4 if (elig and elig.min_gpa_4 is not None) else None

    if min_gpa is None:
        # Scholarship doesn't specify → only mark unknown when we cannot
        # judge from the profile either way.
        if not gpa:
            return CriterionResult(
                key="gpa", label="GPA",
                weight=weight, earned=weight * 0.5, strength="unknown",
                detail=(
                    "No GPA threshold specified by the scholarship and "
                    "no GPA on your profile."
                ),
            )
        # Profile has a GPA but scholarship has no threshold:
        # generous "unknown" — half credit, marked unknown.
        return CriterionResult(
            key="gpa", label="GPA",
            weight=weight, earned=weight * 0.6, strength="unknown",
            detail=(
                f"Scholarship doesn't publish a GPA threshold; your "
                f"GPA is {gpa:.2f}/4.0."
            ),
        )

    # Scholarship has a min_gpa:
    if not gpa:
        # User profile data missing — true "missing", not "unknown".
        return CriterionResult(
            key="gpa", label="GPA",
            weight=weight, earned=weight * 0.2, strength="fail",
            detail=(
                f"No GPA on your profile (min required: {min_gpa}/4.0)."
            ),
        )
    if gpa >= min_gpa:
        return CriterionResult(
            key="gpa", label="GPA",
            weight=weight, earned=weight, strength="pass",
            detail=f"GPA {gpa:.2f} meets the {min_gpa}/4.0 minimum.",
        )
    ratio = max(0.0, min(1.0, gpa / min_gpa))
    if ratio >= 0.95:
        return CriterionResult(
            key="gpa", label="GPA",
            weight=weight, earned=weight * 0.6, strength="partial",
            detail=(
                f"GPA {gpa:.2f} is borderline against the {min_gpa}/4.0 "
                f"threshold."
            ),
        )
    return CriterionResult(
        key="gpa", label="GPA",
        weight=weight, earned=weight * 0.1, strength="fail",
        detail=f"GPA {gpa:.2f} is below the {min_gpa}/4.0 minimum.",
    )


def _score_english(
    profile: ProfileIn | UserProfile,
    elig: Optional[ScholarshipEligibility],
) -> CriterionResult:
    weight = _WEIGHTS["english"]
    score = getattr(profile, "english_test_score", None) or 0.0
    test_type = (getattr(profile, "english_test_type", None) or "").lower()
    min_ielts = elig.min_ielts if (elig and elig.min_ielts is not None) else None

    if min_ielts is None:
        if not score or not test_type:
            return CriterionResult(
                key="english", label="English proficiency",
                weight=weight, earned=weight * 0.5, strength="unknown",
                detail=(
                    "No explicit English threshold and no English test "
                    "on your profile."
                ),
            )
        return CriterionResult(
            key="english", label="English proficiency",
            weight=weight, earned=weight * 0.65, strength="unknown",
            detail=(
                f"Scholarship doesn't publish an English threshold; your "
                f"{test_type.upper()} score is {score}."
            ),
        )

    # Scholarship has a min_ielts:
    if not score or not test_type:
        return CriterionResult(
            key="english", label="English proficiency",
            weight=weight, earned=weight * 0.2, strength="fail",
            detail=(
                f"No English test on your profile "
                f"(min IELTS equivalent: {min_ielts})."
            ),
        )
    if not test_type.startswith("ielts"):
        return CriterionResult(
            key="english", label="English proficiency",
            weight=weight, earned=weight * 0.6, strength="partial",
            detail=(
                f"Your test is {test_type.upper()}; engine only compares "
                f"IELTS directly. Verify conversion against IELTS "
                f"{min_ielts}."
            ),
        )
    if score >= min_ielts:
        return CriterionResult(
            key="english", label="English proficiency",
            weight=weight, earned=weight, strength="pass",
            detail=f"IELTS {score} meets the {min_ielts} minimum.",
        )
    if score >= min_ielts - 0.5:
        return CriterionResult(
            key="english", label="English proficiency",
            weight=weight, earned=weight * 0.5, strength="partial",
            detail=(
                f"IELTS {score} is within 0.5 of the {min_ielts} "
                f"minimum; retake recommended."
            ),
        )
    return CriterionResult(
        key="english", label="English proficiency",
        weight=weight, earned=weight * 0.1, strength="fail",
        detail=f"IELTS {score} is below the {min_ielts} minimum.",
    )


def _score_field(
    profile: ProfileIn | UserProfile,
    elig: Optional[ScholarshipEligibility],
    scholarship: ScholarshipEntry | dict,
) -> CriterionResult:
    weight = _WEIGHTS["field"]
    user_intended = {
        _normalize(x) for x in normalize_fields(
            getattr(profile, "field_of_study", None)
        )
    }
    user_prev = _normalize(
        getattr(profile, "previous_field_of_study", "") or ""
    )
    user_fields = user_intended | ({user_prev} if user_prev else set())

    allowed: Any = None
    if elig and elig.fields_of_study is not None:
        allowed = elig.fields_of_study
    else:
        raw = _scholarship_field(scholarship, "field_of_study")
        if raw:
            allowed = [raw]

    # No allowed list at all → unknown.
    if allowed is None:
        if user_fields:
            return CriterionResult(
                key="field", label="Field of study",
                weight=weight, earned=weight * 0.6, strength="unknown",
                detail=(
                    "Eligible fields not specified by this source — your "
                    "profile fields will be considered if you apply."
                ),
            )
        return CriterionResult(
            key="field", label="Field of study",
            weight=weight, earned=weight * 0.5, strength="unknown",
            detail=(
                "Eligible fields not specified, and no field of study "
                "on your profile."
            ),
        )

    # "any" → pass
    if isinstance(allowed, str) and allowed.strip().lower() == "any":
        return CriterionResult(
            key="field", label="Field of study",
            weight=weight, earned=weight, strength="pass",
            detail="Open to all fields of study.",
        )

    allowed_set = {
        _normalize(x) for x in (
            allowed if isinstance(allowed, (list, tuple, set))
            else [allowed]
        )
    }

    if not user_fields:
        # User hasn't told us their field — true gap.
        return CriterionResult(
            key="field", label="Field of study",
            weight=weight, earned=weight * 0.3, strength="fail",
            detail="Your profile has no field of study yet.",
        )

    intersect = user_fields & allowed_set
    if intersect and (user_intended & allowed_set):
        return CriterionResult(
            key="field", label="Field of study",
            weight=weight, earned=weight, strength="pass",
            detail="Intended field matches the scholarship's scope.",
        )
    if intersect:
        return CriterionResult(
            key="field", label="Field of study",
            weight=weight, earned=weight * 0.6, strength="partial",
            detail=(
                "Your previous field matches but the intended field "
                "doesn't — strong candidates align both."
            ),
        )
    return CriterionResult(
        key="field", label="Field of study",
        weight=weight, earned=weight * 0.2, strength="partial",
        detail=(
            "Your field doesn't match the scholarship's scope; adjacent "
            "disciplines may still be considered — verify directly."
        ),
    )


def _score_readiness(
    profile: ProfileIn | UserProfile,
    elig: Optional[ScholarshipEligibility],
) -> CriterionResult:
    """Combined offer + funds readiness (10% weight)."""
    weight = _WEIGHTS["readiness"]
    offer_status = getattr(profile, "offer_letter_status", None) or ""
    funds_status = getattr(profile, "proof_of_funds_status", None) or ""
    offer_strength = OFFER_STATUS_STRENGTH.get(offer_status, "none")
    funds_strength = FUNDS_STATUS_STRENGTH.get(funds_status, "none")

    requires_offer = elig.requires_offer if elig else None
    requires_funds = elig.requires_funds if elig else None

    # If the scholarship covers funding, "no funds prepared" is fine.
    if requires_funds is False and funds_strength == "none":
        funds_strength = "covered"
    if requires_offer is False and offer_strength == "none":
        offer_strength = "not_required"

    # Score offer half (0..0.5 of weight)
    offer_score = {
        "strong": 0.5, "partial": 0.3, "covered": 0.5,
        "not_required": 0.5, "none": 0.05,
    }[offer_strength]
    funds_score = {
        "strong": 0.5, "partial": 0.3, "covered": 0.5,
        "not_required": 0.5, "none": 0.05,
    }[funds_strength]

    earned = weight * (offer_score + funds_score)
    detail_bits: list[str] = []
    if offer_strength in ("strong", "partial"):
        detail_bits.append(f"offer: {offer_status}")
    elif offer_strength == "covered":
        detail_bits.append("offer not required")
    elif offer_strength == "not_required":
        detail_bits.append("offer not required")
    else:
        detail_bits.append("offer: not yet")
    if funds_strength in ("strong", "partial"):
        detail_bits.append(f"funds: {funds_status}")
    elif funds_strength == "covered":
        detail_bits.append("funds covered by scholarship")
    elif funds_strength == "not_required":
        detail_bits.append("funds not required")
    else:
        detail_bits.append("funds: not yet")
    detail = "Readiness — " + "; ".join(detail_bits) + "."

    # Translate combined to strength label
    if earned >= weight * 0.95:
        strength = "pass"
    elif earned >= weight * 0.55:
        strength = "partial"
    else:
        strength = "fail"

    return CriterionResult(
        key="readiness", label="Readiness (offer + funds)",
        weight=weight, earned=earned, strength=strength,  # type: ignore[arg-type]
        detail=detail,
    )


# ---------- Deadline proximity ------------------------------------------

def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _score_deadline(
    profile: ProfileIn | UserProfile,
    scholarship: ScholarshipEntry | dict,
) -> CriterionResult:
    """Deadline proximity (10% weight).

    Pass:    deadline is at least 30 days from today (comfortable runway)
    Partial: deadline is 7–30 days away (tight but feasible)
    Fail:    deadline is in the past, or within 7 days
    Unknown: deadline missing
    """
    weight = _WEIGHTS["deadline"]
    deadline = _parse_iso_date(_scholarship_field(scholarship, "deadline"))
    if deadline is None:
        return CriterionResult(
            key="deadline", label="Deadline proximity",
            weight=weight, earned=weight * 0.5, strength="unknown",
            detail="Deadline not extracted reliably from this source.",
        )
    today = date.today()
    days = (deadline - today).days
    if days < 0:
        return CriterionResult(
            key="deadline", label="Deadline proximity",
            weight=weight, earned=0.0, strength="fail",
            detail=f"Deadline ({deadline.isoformat()}) has passed.",
        )
    if days < 7:
        return CriterionResult(
            key="deadline", label="Deadline proximity",
            weight=weight, earned=weight * 0.2, strength="fail",
            detail=(
                f"Deadline is in {days} day(s) — too tight to prepare a "
                f"strong application."
            ),
        )
    if days < 30:
        return CriterionResult(
            key="deadline", label="Deadline proximity",
            weight=weight, earned=weight * 0.6, strength="partial",
            detail=(
                f"Deadline in {days} day(s) — feasible but tight."
            ),
        )
    return CriterionResult(
        key="deadline", label="Deadline proximity",
        weight=weight, earned=weight, strength="pass",
        detail=f"Deadline {deadline.isoformat()} ({days} days away).",
    )


# ---------- Public API ----------------------------------------------------


def match_scholarship(
    profile: ProfileIn | UserProfile,
    scholarship: ScholarshipEntry | dict,
) -> ScholarshipFitReport:
    """Compute a deterministic fit report for one (profile, scholarship)."""
    elig = _eligibility_of(scholarship)
    sch_id = (
        scholarship.get("id") if isinstance(scholarship, dict)
        else getattr(scholarship, "id", 0)
    ) or 0

    trace: list[CriterionResult] = [
        _score_eligibility(profile, elig, scholarship),
        _score_gpa(profile, elig),
        _score_english(profile, elig),
        _score_field(profile, elig, scholarship),
        _score_readiness(profile, elig),
        _score_deadline(profile, scholarship),
    ]

    total_weight = sum(c.weight for c in trace)
    earned = sum(c.earned for c in trace)
    fit_score = int(round(100 * earned / total_weight)) if total_weight else 0

    # Hard-fail on the eligibility criterion → caps and forces not_eligible
    elig_failed = any(
        c.strength == "fail" and c.key == "eligibility" for c in trace
    )
    if elig_failed:
        fit_score = min(fit_score, 30)
        status = "not_eligible"
    else:
        fails = sum(1 for c in trace if c.strength == "fail")
        partials = sum(1 for c in trace if c.strength == "partial")
        if fit_score >= 85 and fails == 0 and partials <= 1:
            status = "strong_match"
        elif fit_score >= 70:
            status = "possible_match"
        elif fit_score >= 50:
            status = "weak_match"
        else:
            status = "not_eligible"

    # ---- Three-bucket output (v0.7) ----
    matched = [c.label for c in trace if c.strength == "pass"]
    missing = [c.label for c in trace if c.strength in ("fail", "partial")]
    unknown = [c.label for c in trace if c.strength == "unknown"]

    advice = _improvement_advice(trace)

    return ScholarshipFitReport(
        scholarship_id=int(sch_id),
        fit_score=max(0, min(100, fit_score)),
        match_status=status,  # type: ignore[arg-type]
        matched_criteria=matched,
        missing_criteria=missing,
        unknown_criteria=unknown,
        improvement_advice=advice,
        trace=trace,
    )


def _improvement_advice(trace: Iterable[CriterionResult]) -> list[str]:
    """Generate up to 5 concrete suggestions from failed/partial criteria.
    Unknown criteria do NOT produce advice — they're a data gap, not a
    profile gap."""
    tips: list[str] = []
    for c in trace:
        if c.strength in ("pass", "unknown"):
            continue
        if c.key == "eligibility":
            tips.append(
                "This scholarship's eligibility (nationality, destination, "
                "or degree level) doesn't fully align — focus on options "
                "that match all three."
            )
        elif c.key == "gpa":
            tips.append(
                "Strengthen your academic record (transcripts, references, "
                "publications) or shortlist scholarships with softer GPA "
                "thresholds."
            )
        elif c.key == "english":
            tips.append(
                "Book or retake IELTS Academic to meet the required band."
            )
        elif c.key == "field":
            tips.append(
                "Frame your intended field clearly to the scholarship's "
                "stated scope when you apply."
            )
        elif c.key == "readiness":
            tips.append(
                "Strengthen your application file: secure an unconditional "
                "offer if needed, and prepare proof of funds early."
            )
        elif c.key == "deadline":
            tips.append(
                "This deadline is tight or has passed — aim for the next "
                "intake cycle."
            )
    seen: set[str] = set()
    unique: list[str] = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            unique.append(t)
        if len(unique) >= 5:
            break
    return unique
