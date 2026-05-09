"""
services/route_service.py
-------------------------
Generates deterministic route/workflow plans from templates
(data/seeds/route_templates.json) and tracks step status per profile.

Key rules:
- Templates are the source of truth; the LLM never invents steps.
- Step status is derived from:
    * dependency completion
    * eligibility report signals (e.g. missing evidence -> pending_evidence)
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from config.settings import SEEDS_DIR
from db.database import session_scope
from models.orm import RoutePlan, RouteStep
from models.schemas import EligibilityReport, RoutePlanDTO, RouteStepDTO
from utils.helpers import safe_load_json
from utils.logger import get_logger

log = get_logger(__name__)

_TEMPLATES_CACHE: dict[str, Any] | None = None


def _load_templates() -> dict[str, Any]:
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None:
        _TEMPLATES_CACHE = safe_load_json(SEEDS_DIR / "route_templates.json")
    return _TEMPLATES_CACHE


def reload_templates() -> None:
    global _TEMPLATES_CACHE
    _TEMPLATES_CACHE = None


# Map eligibility rule -> route step key so we can mark steps as
# pending_evidence when the deterministic engine flagged them.
_RULE_TO_STEP_KEYS: dict[str, list[str]] = {
    # UK
    "uk_passport_validity": ["passport_ready"],
    "uk_offer_letter": ["offer_letter"],
    "uk_proof_of_funds": ["financial_proof"],
    "uk_english_language": ["language_cert"],
    "uk_education_level": ["document_checklist"],
    # Canada
    "ca_passport_validity": ["passport_ready"],
    "ca_dli_letter": ["dli_offer"],
    "ca_proof_of_funds": ["financial_proof"],
    "ca_language": ["language_cert"],
    "ca_education_level": ["document_checklist"],
    # Germany
    "de_passport_validity": ["passport_ready"],
    "de_admission": ["admission"],
    "de_blocked_account": ["blocked_account"],
    "de_language": ["language_cert"],
    "de_education_level": ["document_checklist"],
}


def generate_plan(
    country: str, report: EligibilityReport | None = None
) -> RoutePlanDTO:
    """Build a RoutePlanDTO from the template, applying eligibility-aware
    statuses."""
    tmpl_doc = _load_templates()
    tmpl = tmpl_doc.get("templates", {}).get(country)
    if not tmpl:
        log.warning("No template for country=%s", country)
        return RoutePlanDTO(country=country, template_key="none", steps=[])

    # Collect failed/missing-evidence rule ids from eligibility report.
    failed_rule_ids: set[str] = set()
    if report is not None:
        for t in report.trace:
            if t.outcome in ("failed", "missing_evidence"):
                failed_rule_ids.add(t.rule_id)

    # Which step keys should be pending_evidence?
    pending_keys: set[str] = set()
    for rid in failed_rule_ids:
        for k in _RULE_TO_STEP_KEYS.get(rid, []):
            pending_keys.add(k)

    steps: list[RouteStepDTO] = []
    completed: set[str] = set()  # always empty at generation time
    for idx, s in enumerate(tmpl["steps"]):
        deps = s.get("depends_on", [])
        unmet_deps = [d for d in deps if d not in completed]
        if s["key"] in pending_keys:
            status = "pending_evidence"
        elif unmet_deps:
            status = "locked"
        else:
            status = "available"

        steps.append(
            RouteStepDTO(
                key=s["key"],
                title=s["title"],
                description=s.get("description", ""),
                status=status,  # type: ignore[arg-type]
                depends_on=deps,
                notes="",
            )
        )

    return RoutePlanDTO(
        country=country,
        template_key=tmpl.get("template_key", country.lower() + "_v1"),
        steps=steps,
    )


# ---------- persistence ---------------------------------------------------


def save_plan(profile_id: int, plan: RoutePlanDTO) -> int:
    """Persist a route plan and its steps. Replaces any prior plan for
    the same (profile, country)."""
    with session_scope() as db:
        # Wipe prior plans for this profile+country
        prior = list(
            db.scalars(
                select(RoutePlan).where(
                    (RoutePlan.profile_id == profile_id)
                    & (RoutePlan.country == plan.country)
                )
            )
        )
        for p in prior:
            db.delete(p)
        db.flush()

        row = RoutePlan(
            profile_id=profile_id,
            country=plan.country,
            template_key=plan.template_key,
        )
        db.add(row)
        db.flush()
        for idx, s in enumerate(plan.steps):
            db.add(
                RouteStep(
                    plan_id=row.id,
                    order_index=idx,
                    key=s.key,
                    title=s.title,
                    description=s.description,
                    status=s.status,
                    depends_on_json=json.dumps(s.depends_on),
                    notes=s.notes or "",
                )
            )
        return row.id


def get_plan(profile_id: int, country: str) -> RoutePlanDTO | None:
    with session_scope() as db:
        row = db.scalars(
            select(RoutePlan).where(
                (RoutePlan.profile_id == profile_id)
                & (RoutePlan.country == country)
            )
        ).first()
        if not row:
            return None
        steps = [
            RouteStepDTO(
                key=s.key,
                title=s.title,
                description=s.description,
                status=s.status,  # type: ignore[arg-type]
                depends_on=json.loads(s.depends_on_json or "[]"),
                notes=s.notes,
            )
            for s in row.steps
        ]
        return RoutePlanDTO(
            country=row.country,
            template_key=row.template_key,
            steps=steps,
        )


def update_step_status(
    profile_id: int, country: str, step_key: str, new_status: str
) -> bool:
    """Update a single step's status and cascade availability to dependents."""
    allowed = {"locked", "available", "completed", "blocked", "pending_evidence"}
    if new_status not in allowed:
        raise ValueError(f"Invalid status: {new_status}")

    with session_scope() as db:
        plan = db.scalars(
            select(RoutePlan).where(
                (RoutePlan.profile_id == profile_id)
                & (RoutePlan.country == country)
            )
        ).first()
        if not plan:
            return False

        # Update the target step
        target = next((s for s in plan.steps if s.key == step_key), None)
        if not target:
            return False
        target.status = new_status

        # Cascade: unlock dependents if all their deps are completed
        completed_keys = {s.key for s in plan.steps if s.status == "completed"}
        for s in plan.steps:
            if s.status != "locked":
                continue
            deps = json.loads(s.depends_on_json or "[]")
            if all(d in completed_keys for d in deps):
                s.status = "available"
        return True
