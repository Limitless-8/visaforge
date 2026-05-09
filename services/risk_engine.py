"""services/risk_engine.py
--------------------------
v0.18 (Phase 6): Deterministic Risk Detection Engine.

Inspects the student's profile, eligibility result, route plan, and
uploaded documents and returns a ranked list of risks. Each risk has a
severity (High / Medium / Low) and a recommended next action.

All logic is deterministic. No LLM is called here. The AI assistant
page may present these risks in conversation, but the engine itself
never talks to an AI.

Rules:
  * Documents never block route progress (Phase 5.6 pivot is preserved).
  * This engine is ADVISORY. Risks explain WHY something may go wrong;
    they do not stop the user from completing steps.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from utils.logger import get_logger

log = get_logger(__name__)


# ---------- Thresholds ---------------------------------------------------

_IELTS_THRESHOLDS: dict[str, float] = {
    "UK":      6.5,
    "Canada":  6.0,
    "Germany": 6.0,
}

_PASSPORT_WARN_MONTHS = 6   # warn if expiry < 6 months from today


# ---------- Individual risk detectors ------------------------------------

def _risk_ielts(profile, dest_country: str) -> Optional[dict]:
    score_str = getattr(profile, "english_test_score", None) or ""
    test_type = getattr(profile, "english_test_type", None) or ""
    threshold = _IELTS_THRESHOLDS.get(dest_country, 6.5)

    if not score_str:
        return {
            "type":           "IELTS / English test",
            "severity":       "High",
            "message":        "No English test score found on your profile.",
            "recommendation": (
                f"Most {dest_country} universities require an IELTS score "
                f"of {threshold}+ (or equivalent TOEFL/PTE). Book a test "
                "and update your profile score."
            ),
        }
    try:
        score = float(score_str)
    except ValueError:
        return None
    if score < threshold:
        return {
            "type":      "IELTS / English test",
            "severity":  "High",
            "message":   (
                f"Your {test_type or 'English test'} score ({score}) is "
                f"below the typical {dest_country} requirement of {threshold}+."
            ),
            "recommendation": (
                f"Retake IELTS (or switch to TOEFL/PTE) and aim for "
                f"{threshold}. Your current score may make it harder to "
                "secure admission or a visa."
            ),
        }
    return None


def _risk_passport(profile) -> Optional[dict]:
    passport_until = getattr(profile, "passport_valid_until", None)
    if passport_until is None:
        return {
            "type":      "Passport",
            "severity":  "High",
            "message":   "Passport expiry date is missing from your profile.",
            "recommendation": (
                "Add your passport expiry date in the Profile page. "
                "Most visa applications require at least 6 months of "
                "validity beyond your intended course end date."
            ),
        }
    try:
        if isinstance(passport_until, str):
            expiry = date.fromisoformat(passport_until[:10])
        else:
            expiry = passport_until  # already a date
        months_remaining = (
            (expiry.year - date.today().year) * 12
            + (expiry.month - date.today().month)
        )
        if months_remaining < 0:
            return {
                "type":      "Passport",
                "severity":  "High",
                "message":   (
                    f"Your passport expired on {expiry.isoformat()}."
                ),
                "recommendation": (
                    "Renew your passport immediately at the Passport "
                    "Office / National Database Registration Authority "
                    "(NADRA). You cannot apply for a student visa with "
                    "an expired passport."
                ),
            }
        if months_remaining < _PASSPORT_WARN_MONTHS:
            return {
                "type":      "Passport",
                "severity":  "Medium",
                "message":   (
                    f"Passport expires in {months_remaining} months "
                    f"({expiry.isoformat()}) — less than 6 months."
                ),
                "recommendation": (
                    "Start the passport renewal process now. UK / Canada "
                    "/ Germany visa offices often require 6+ months "
                    "validity past your intended departure date."
                ),
            }
    except (ValueError, TypeError):
        return {
            "type":      "Passport",
            "severity":  "Medium",
            "message":   "Passport expiry date on your profile cannot be parsed.",
            "recommendation": (
                "Update the passport expiry date on your Profile page "
                "in YYYY-MM-DD format."
            ),
        }
    return None


def _risk_funds(profile, dest_country: str) -> Optional[dict]:
    funds_status = (
        getattr(profile, "proof_of_funds_status", None) or ""
    ).lower()
    if funds_status in ("not prepared", "not sure", ""):
        severity = "High" if dest_country == "Germany" else "Medium"
        return {
            "type":      "Proof of Funds",
            "severity":  severity,
            "message":   "Proof of funds status is unclear or not prepared.",
            "recommendation": (
                {
                    "Germany": (
                        "Germany requires a blocked account (Sperrkonto) "
                        "of at least €11,208/year. Open one with Deutsche "
                        "Bank or similar before applying for your visa."
                    ),
                    "UK": (
                        "UK visas require evidence of sufficient funds "
                        "(typically £1,334/month outside London or "
                        "£1,523/month in London). Prepare your bank "
                        "statements now."
                    ),
                    "Canada": (
                        "Canada Study Permit requires evidence of at "
                        "least CAD 10,000 (plus tuition) in accessible "
                        "funds. A GIC (Guaranteed Investment Certificate) "
                        "from a designated Canadian bank is commonly used."
                    ),
                }.get(dest_country, (
                    "Ensure you can demonstrate sufficient financial "
                    "resources for your first year of study + living costs."
                ))
            ),
        }
    return None


def _risk_no_scholarship(selected_scholarship) -> Optional[dict]:
    if selected_scholarship is None:
        return {
            "type":      "Scholarship",
            "severity":  "Medium",
            "message":   "No scholarship selected yet.",
            "recommendation": (
                "Browse the Scholarships tab and bookmark at least one "
                "programme. A selected scholarship is required to "
                "generate your route plan."
            ),
        }
    return None


def _risk_no_offer(profile) -> Optional[dict]:
    offer_status = (
        getattr(profile, "offer_letter_status", None) or ""
    )
    if offer_status in (
        "Not yet applied", "Applied and waiting", "",
        "Not required / unsure",
    ):
        return {
            "type":      "Offer letter / CAS",
            "severity":  "Medium",
            "message":   (
                f"Offer status is '{offer_status}'. "
                "Without a confirmed offer you cannot obtain a CAS "
                "(UK), LOA (Canada), or Zulassung (Germany)."
            ),
            "recommendation": (
                "Apply to universities now. Once you receive an offer, "
                "update your profile and it will unlock the visa steps "
                "on your route plan."
            ),
        }
    return None


def _risk_weak_academic(profile) -> Optional[dict]:
    gpa = getattr(profile, "gpa", None)
    if gpa is None:
        return {
            "type":      "Academic profile",
            "severity":  "Low",
            "message":   "GPA / academic score is missing from your profile.",
            "recommendation": (
                "Add your GPA or grade average to your profile. This "
                "information is used by the eligibility engine and can "
                "affect scholarship matching."
            ),
        }
    try:
        gpa_f = float(gpa)
    except (TypeError, ValueError):
        return None
    if gpa_f < 2.0:
        return {
            "type":      "Academic profile",
            "severity":  "Medium",
            "message":   f"GPA ({gpa_f:.2f}/4.0) is below typical university requirements.",
            "recommendation": (
                "A GPA below 2.0 may limit scholarship options. "
                "Consider an academic upgrading course or a foundation "
                "year. Highlight work experience or publications in "
                "your personal statement to compensate."
            ),
        }
    return None


def _risk_missing_route_steps(route_plan) -> Optional[dict]:
    """Flag if the user has no route plan at all."""
    if route_plan is None:
        return {
            "type":      "Route plan",
            "severity":  "Medium",
            "message":   "No route plan has been generated yet.",
            "recommendation": (
                "Go to the Route Plan page and generate your plan. "
                "It gives you a personalised step-by-step checklist "
                "for scholarship, Pakistan preparation, and visa."
            ),
        }
    return None


def _risk_low_progress(route_plan) -> Optional[dict]:
    """Flag if the route plan exists but progress is very low."""
    if route_plan is None:
        return None
    if isinstance(route_plan, dict):
        pct = float(route_plan.get("overall_progress_pct", 0) or 0)
    else:
        pct = float(getattr(route_plan, "overall_progress_pct", 0) or 0)
    if pct < 20:
        return {
            "type":      "Route plan progress",
            "severity":  "Low",
            "message":   f"Only {pct:.0f}% of your route plan is complete.",
            "recommendation": (
                "Open your Route Plan and start working through the "
                "available steps. The Pakistan preparation section "
                "typically needs 4–8 weeks — start early."
            ),
        }
    return None


def _risk_no_documents(documents: list | None) -> Optional[dict]:
    """Advisory-only: no documents uploaded at all."""
    if not documents:
        return {
            "type":      "Documents",
            "severity":  "Low",
            "message":   "No supporting documents have been uploaded yet.",
            "recommendation": (
                "Upload your passport scan, IELTS certificate, and "
                "academic transcripts to the Documents tab. These are "
                "advisory — they don't block your route plan, but "
                "they help the AI give better guidance."
            ),
        }
    return None


# ---------- Public API ---------------------------------------------------

def detect_risks(
    *,
    profile,
    eligibility_report=None,
    route_plan=None,
    documents: Optional[list] = None,
    selected_scholarship=None,
) -> list[dict[str, Any]]:
    """Run all risk detectors and return a list of issues sorted by
    severity (High first, then Medium, then Low).

    All detectors are defensive — they never raise; failures are
    logged and skipped.

    Returns:
        list of dicts, each with keys:
          "type"           — short category label
          "severity"       — "High" | "Medium" | "Low"
          "message"        — one-sentence description of the risk
          "recommendation" — what to do about it
    """
    dest = (
        getattr(profile, "destination_country", None)
        or (
            eligibility_report.get("destination_country")
            if isinstance(eligibility_report, dict)
            else getattr(eligibility_report, "destination_country", None)
        )
        or "UK"
    )

    detectors = [
        lambda: _risk_ielts(profile, dest),
        lambda: _risk_passport(profile),
        lambda: _risk_funds(profile, dest),
        lambda: _risk_no_scholarship(selected_scholarship),
        lambda: _risk_no_offer(profile),
        lambda: _risk_weak_academic(profile),
        lambda: _risk_missing_route_steps(route_plan),
        lambda: _risk_low_progress(route_plan),
        lambda: _risk_no_documents(documents),
    ]

    risks: list[dict[str, Any]] = []
    for fn in detectors:
        try:
            result = fn()
            if result is not None:
                risks.append(result)
        except Exception as exc:
            log.warning("risk detector failed: %s", exc)

    # Sort: High first, then Medium, then Low
    _order = {"High": 0, "Medium": 1, "Low": 2}
    risks.sort(key=lambda r: _order.get(r.get("severity", "Low"), 2))
    log.debug("detect_risks: %d risks found", len(risks))
    return risks
