"""
services/eligibility_service.py
-------------------------------
Deterministic eligibility engine (v0.3).

Two-phase pipeline:

  Phase 1 — Rule evaluation (this file)
  --------------------------------------
  Each rule is evaluated against the profile and returns a
  RuleEvaluation with outcome, priority, category, and the
  metadata needed for next-step generation.

  Phase 2 — Analysis (services/eligibility_analysis.py)
  --------------------------------------
  The RuleEvaluations are passed to the analysis module which
  computes the decision state, confidence breakdown, risk flags,
  weakest area, next steps and timeline.

The LLM is NEVER involved in either phase; AI explanations live
elsewhere and consume the structured output.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import select

from config.settings import SEEDS_DIR
from db.database import session_scope
from models.orm import EligibilityResult, UserProfile
from models.schemas import (
    EligibilityReport,
    EligibilityStatus,
    ProfileIn,
    RuleEvaluation,
)
from services import eligibility_analysis as analysis
from utils.helpers import safe_load_json, utcnow
from utils.logger import get_logger
from utils.reference_data import (
    FUNDS_STATUS_STRENGTH,
    OFFER_STATUS_STRENGTH,
)

log = get_logger(__name__)

_RULES_CACHE: dict[str, Any] | None = None


def _load_rules() -> dict[str, Any]:
    global _RULES_CACHE
    if _RULES_CACHE is None:
        _RULES_CACHE = safe_load_json(SEEDS_DIR / "visa_rules.json")
    return _RULES_CACHE


def reload_rules() -> None:
    """For the admin page: force re-read of rules from disk."""
    global _RULES_CACHE
    _RULES_CACHE = None


# ---------- check primitives ----------------------------------------------


def _check_non_empty_date(value: Any) -> tuple[bool, str]:
    if not value:
        return False, "No passport validity date provided."
    try:
        s = str(value)[:10]
        d = datetime.strptime(s, "%Y-%m-%d").date()
        if d < date.today():
            return False, f"Passport expires in the past ({s})."
        return True, f"Passport valid until {s}."
    except ValueError:
        return False, f"Could not parse passport date: {value!r}"


def _check_is_true(value: Any) -> tuple[bool, str]:
    if bool(value):
        return True, "Confirmed."
    return False, "Not confirmed."


def _check_numeric_min(
    value: Any, params: dict[str, Any]
) -> tuple[bool, str]:
    min_value = float(params.get("min_value", 0))
    try:
        if value is None or value == "":
            return False, f"No value provided (minimum required: {min_value})."
        v = float(value)
        if v >= min_value:
            return True, f"Score {v} meets minimum {min_value}."
        return False, f"Score {v} below minimum {min_value}."
    except (TypeError, ValueError):
        return False, f"Could not parse numeric value: {value!r}"


def _check_numeric_min_or_na(
    value: Any, applies: bool, params: dict[str, Any]
) -> tuple[bool, str]:
    if not applies:
        return True, "Language test not applicable for this pathway."
    return _check_numeric_min(value, params)


def _check_non_empty_string(value: Any) -> tuple[bool, str]:
    if value and str(value).strip():
        return True, f"Provided: {value}."
    return False, "Not provided."


def _check_offer_status(value: Any) -> tuple[str, str]:
    status = str(value) if value else ""
    strength = OFFER_STATUS_STRENGTH.get(status, "none")
    if strength == "strong":
        return "strong", f"Offer status: {status} — sufficient."
    if strength == "partial":
        return "partial", (
            f"Offer status: {status} — partial evidence; unconditional "
            f"offer will be needed before the visa application."
        )
    if not status:
        return "none", "No offer letter status provided."
    return "none", f"Offer status: {status} — not yet sufficient evidence."


def _check_funds_status(value: Any) -> tuple[str, str]:
    status = str(value) if value else ""
    strength = FUNDS_STATUS_STRENGTH.get(status, "none")
    if strength == "strong":
        return "strong", f"Funds status: {status} — sufficient."
    if strength == "partial":
        return "partial", (
            f"Funds status: {status} — partial evidence; full financial "
            f"proof must be ready before submission."
        )
    if not status:
        return "none", "No proof-of-funds status provided."
    return "none", f"Funds status: {status} — not yet sufficient evidence."


# ---------- priority inference (back-compat) ------------------------------


def _priority_for_rule(rule: dict[str, Any]) -> str:
    """Return the rule's declared priority or infer from weight.

    v0.3 rule files set 'priority' explicitly. For older files we infer:
      weight >= 1.0 → CRITICAL
      weight >= 0.6 → IMPORTANT
      otherwise    → OPTIONAL
    """
    priority = (rule.get("priority") or "").upper()
    if priority in ("CRITICAL", "IMPORTANT", "OPTIONAL"):
        return priority
    weight = float(rule.get("weight", 1.0))
    if weight >= 1.0:
        return "CRITICAL"
    if weight >= 0.6:
        return "IMPORTANT"
    return "OPTIONAL"


def _category_for_rule(rule: dict[str, Any]) -> str:
    cat = (rule.get("category") or "").lower()
    if cat in ("documents", "financial", "academic", "language", "other"):
        return cat
    # Infer from check type as a fallback
    check = (rule.get("check") or "").lower()
    if check in ("offer_status", "non_empty_date"):
        return "documents"
    if check == "funds_status":
        return "financial"
    if check in ("numeric_min", "numeric_min_or_na"):
        return "language"
    if check == "non_empty_string":
        return "academic"
    return "other"


# ---------- main engine ---------------------------------------------------


def evaluate_eligibility(
    profile: ProfileIn | UserProfile,
) -> EligibilityReport:
    """Run the deterministic eligibility engine and produce an enriched
    EligibilityReport (including decision state, next steps, timeline)."""
    rules_doc = _load_rules()
    country = getattr(profile, "destination_country", None)
    if not country:
        return _empty_report("UK", "No destination country selected.")

    country_rules = rules_doc.get("countries", {}).get(country)
    if not country_rules:
        return _empty_report(country, f"No rule set configured for {country}.")

    trace: list[RuleEvaluation] = []
    missing_evidence: set[str] = set()

    for rule in country_rules.get("rules", []):
        rid = rule["id"]
        desc = rule["description"]
        field = rule["field"]
        check = rule["check"]
        params = rule.get("params", {}) or {}
        priority = _priority_for_rule(rule)
        category = _category_for_rule(rule)
        value = getattr(profile, field, None)

        ok: bool = False
        partial: bool = False
        detail: str = ""

        if check == "non_empty_date":
            ok, detail = _check_non_empty_date(value)
        elif check == "is_true":
            ok, detail = _check_is_true(value)
        elif check == "numeric_min":
            applies_field = params.get("applies_if_field")
            applies = bool(getattr(profile, applies_field, None)) \
                if applies_field else True
            if not applies:
                ok = False
                detail = (
                    "Language test indicated as not taken — please provide one."
                )
            else:
                ok, detail = _check_numeric_min(value, params)
        elif check == "numeric_min_or_na":
            applies_field = params.get("applies_if_field")
            applies = bool(getattr(profile, applies_field, None)) \
                if applies_field else True
            ok, detail = _check_numeric_min_or_na(value, applies, params)
        elif check == "non_empty_string":
            ok, detail = _check_non_empty_string(value)
        elif check == "offer_status":
            strength, detail = _check_offer_status(value)
            ok = strength == "strong"
            partial = strength == "partial"
        elif check == "funds_status":
            strength, detail = _check_funds_status(value)
            ok = strength == "strong"
            partial = strength == "partial"
        else:
            ok = False
            detail = f"Unknown check '{check}' — treating as failed."

        # Outcome mapping:
        #   passed              → rule satisfied
        #   missing_evidence    → partial / soft fail on non-critical rule
        #   failed              → CRITICAL rule failed outright
        if ok:
            outcome = "passed"
        elif partial:
            outcome = "missing_evidence"
            for ev in rule.get("evidence_required", []):
                missing_evidence.add(ev)
        else:
            # Hard failure only if this is CRITICAL; softer rules flagged
            # as missing_evidence so the user can address them without
            # crashing the decision to NOT_ELIGIBLE.
            outcome = "failed" if priority == "CRITICAL" else "missing_evidence"
            for ev in rule.get("evidence_required", []):
                missing_evidence.add(ev)

        trace.append(
            RuleEvaluation(
                rule_id=rid,
                description=desc,
                outcome=outcome,  # type: ignore[arg-type]
                detail=detail,
                evidence_required=rule.get("evidence_required", []),
                priority=priority,   # type: ignore[arg-type]
                category=category,   # type: ignore[arg-type]
                why_it_matters=rule.get("why_it_matters"),
                what_to_do=rule.get("what_to_do"),
                estimated_time=rule.get("estimated_time"),
            )
        )

    # ---- Phase 2: analysis -----------------------------------------------

    decision = analysis.derive_decision(trace)
    breakdown = analysis.compute_confidence_breakdown(trace)
    confidence = analysis.overall_confidence_from_breakdown(breakdown)
    blocking_issues = analysis.collect_blocking_issues(trace)
    important_gaps = analysis.collect_important_gaps(trace)
    weakest_area = analysis.derive_weakest_area(trace, breakdown)
    risk_flags = analysis.derive_risk_flags(profile, trace)
    next_steps = analysis.build_next_steps(trace)
    timeline_plan = analysis.build_timeline_plan(profile)

    # Legacy-compatible status for DB storage
    status = _legacy_status_from_decision(decision)

    summary = _build_summary(
        country_rules, decision, confidence, trace, weakest_area
    )

    return EligibilityReport(
        country=country,
        status=status,
        confidence=confidence,
        summary=summary,
        trace=trace,
        missing_evidence=sorted(missing_evidence),
        evaluated_at=utcnow(),
        # v0.3 additions
        decision=decision,
        confidence_breakdown=breakdown,
        blocking_issues=blocking_issues,
        important_gaps=important_gaps,
        risk_flags=risk_flags,
        weakest_area=weakest_area,
        next_steps=next_steps,
        timeline_plan=timeline_plan,
    )


def _legacy_status_from_decision(decision: str) -> EligibilityStatus:
    """Map new decision state to the legacy 3-value status so older code
    (and the existing DB column) keep working."""
    mapping: dict[str, EligibilityStatus] = {
        "ELIGIBLE": "eligible",
        "CONDITIONALLY_ELIGIBLE": "partial",
        "HIGH_RISK": "partial",
        "NOT_ELIGIBLE": "not_eligible",
    }
    return mapping.get(decision, "not_eligible")


def _build_summary(
    country_rules: dict[str, Any],
    decision: str,
    confidence: float,
    trace: list[RuleEvaluation],
    weakest_area: str | None,
) -> str:
    visa_name = country_rules.get("visa_name", "Student visa")
    passed = sum(1 for t in trace if t.outcome == "passed")
    total = len(trace)
    reference = country_rules.get("official_reference", "")
    ref_line = f" See official reference: {reference}" if reference else ""

    headline = {
        "ELIGIBLE": (
            f"You meet the headline requirements for the {visa_name} "
            f"({passed}/{total} rules passed)."
        ),
        "CONDITIONALLY_ELIGIBLE": (
            f"Conditionally eligible for the {visa_name} "
            f"({passed}/{total} rules passed, confidence "
            f"{confidence:.0%}). Resolve the blocking items below."
        ),
        "HIGH_RISK": (
            f"High-risk profile for the {visa_name} "
            f"({passed}/{total} rules passed, confidence "
            f"{confidence:.0%}). Address the important gaps to strengthen "
            f"your case."
        ),
        "NOT_ELIGIBLE": (
            f"Current profile does not yet meet key requirements for the "
            f"{visa_name} ({passed}/{total} rules passed)."
        ),
    }[decision]

    weakest_line = f" Weakest area: {weakest_area}." if weakest_area else ""
    return headline + weakest_line + ref_line


def _empty_report(country: str, msg: str) -> EligibilityReport:
    return EligibilityReport(
        country=country,
        status="not_eligible",
        confidence=0.0,
        summary=msg,
        trace=[],
        missing_evidence=[],
        evaluated_at=utcnow(),
        decision="NOT_ELIGIBLE",
    )


# ---------- persistence ---------------------------------------------------


def save_report(profile_id: int, report: EligibilityReport) -> int:
    """Persist the report. The new v0.3 analysis payload is stored inside
    `trace_json` by serializing the whole report; this keeps the DB schema
    unchanged. `missing_evidence_json` still stores the flat list."""
    with session_scope() as db:
        full_payload = report.model_dump(mode="json")
        row = EligibilityResult(
            profile_id=profile_id,
            country=report.country,
            status=report.status,
            confidence=report.confidence,
            summary=report.summary,
            trace_json=json.dumps(full_payload, default=str),
            missing_evidence_json=json.dumps(report.missing_evidence),
        )
        db.add(row)
        db.flush()
        return row.id


def latest_report(profile_id: int) -> EligibilityResult | None:
    with session_scope() as db:
        row = db.scalars(
            select(EligibilityResult)
            .where(EligibilityResult.profile_id == profile_id)
            .order_by(EligibilityResult.created_at.desc())
        ).first()
        if row:
            db.expunge(row)
        return row
