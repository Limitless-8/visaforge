"""services/next_step_service.py
---------------------------------
v0.18 (Phase 6): Next Action Engine.

Determines the single most important action the user should take right
now. Pure deterministic logic — no LLM.

Priority order (highest wins):
  1. Any step currently in `needs_attention` (broken upload, issue)
  2. First available step with dependencies satisfied
  3. No route plan → "Generate your route plan"
  4. No scholarship selected → "Select a scholarship"
  5. Weak eligibility signal → "Improve your IELTS score / profile"
  6. Route complete → congratulations + keep updating

The returned dict feeds directly into the Dashboard next-action card
and into the AI context packet.
"""
from __future__ import annotations

from typing import Any, Optional

from utils.logger import get_logger

log = get_logger(__name__)


def get_next_action(
    *,
    profile,
    route_plan=None,
    risks: Optional[list[dict]] = None,
    selected_scholarship=None,
    eligibility_report=None,
) -> dict[str, Any]:
    """Return the single highest-priority action for the student.

    Returns:
        {
          "step_key":    str | None,
          "title":       str,
          "description": str,
          "cta":         str,       # button label
          "target":      str,       # page path
          "priority":    str,       # "critical" | "high" | "normal"
        }
    """
    risks = risks or []
    high_risks = [r for r in risks if r.get("severity") == "High"]

    # 1. Route step in needs_attention
    _needs_attention_step = _find_step_by_status(route_plan, "needs_attention")
    if _needs_attention_step:
        return {
            "step_key":    _needs_attention_step.get("key") or "",
            "title":       _needs_attention_step.get("title", "Fix document issue"),
            "description": (
                "One of your route steps needs attention — "
                "likely a document that couldn't be read. "
                "Visit the Documents page to reprocess or re-upload."
            ),
            "cta":     "Go to Documents",
            "target":  "pages/5_Documents.py",
            "priority": "critical",
        }

    # 2. No scholarship → nothing else can proceed
    if selected_scholarship is None:
        return {
            "step_key":    None,
            "title":       "Select a scholarship",
            "description": (
                "You haven't selected a target scholarship yet. "
                "Browse the Scholarships tab and save one — "
                "your route plan will be tailored around it."
            ),
            "cta":     "Browse scholarships",
            "target":  "pages/4_Scholarships.py",
            "priority": "high",
        }

    # 3. No route plan generated
    if route_plan is None:
        return {
            "step_key":    None,
            "title":       "Generate your route plan",
            "description": (
                "Generate your personalised step-by-step plan. "
                "It covers scholarship, Pakistan preparation, and visa."
            ),
            "cta":     "Open Route Plan",
            "target":  "pages/3_Route_Plan.py",
            "priority": "high",
        }

    # 4. High-risk eligibility issue (IELTS, passport) — surface before
    #    a regular route step so the user knows why steps may fail later
    if high_risks:
        top_risk = high_risks[0]
        return {
            "step_key":    None,
            "title":       f"Address risk: {top_risk['type']}",
            "description": top_risk["recommendation"],
            "cta":         "Review eligibility",
            "target":      "pages/2_Eligibility.py",
            "priority":    "critical",
        }

    # 5. Next available / actionable route step.
    #    Import at call time to avoid a circular module dependency.
    try:
        from services.route_plan_service import get_next_actionable_step
        next_step = get_next_actionable_step(route_plan)
    except Exception as exc:
        log.warning("get_next_actionable_step failed: %s", exc)
        next_step = None

    if next_step is not None and next_step.status != "completed":
        _label_map = {
            "locked":    "Up next (locked — complete dependencies first)",
            "available": "Up next",
            "blocked":   "Blocked — check eligibility",
        }
        return {
            "step_key":    next_step.key,
            "title":       next_step.title,
            "description": (
                next_step.status_reason
                or next_step.description
                or _label_map.get(next_step.status, "")
            ),
            "cta":     "Go to Route Plan",
            "target":  "pages/3_Route_Plan.py",
            "priority": "normal",
        }

    # 6. Route plan fully complete
    return {
        "step_key":    None,
        "title":       "Route plan complete!",
        "description": (
            "All steps are marked complete. Keep your profile "
            "updated, upload any remaining documents, and ensure "
            "your scholarship application is submitted."
        ),
        "cta":     "Review your plan",
        "target":  "pages/3_Route_Plan.py",
        "priority": "normal",
    }


# ---------- Helpers -------------------------------------------------------

def _find_step_by_status(route_plan, status: str) -> Optional[dict]:
    """Scan a DynamicRoutePlanDTO (or dict) for the first step
    with the given status. Returns a minimal step dict or None."""
    if route_plan is None:
        return None
    # dict form (from AI context)
    if isinstance(route_plan, dict):
        for sec in route_plan.get("sections", []):
            for step in sec.get("steps", []):
                if step.get("status") == status:
                    return step
        return None
    # DTO form
    for sec in getattr(route_plan, "sections", []):
        for step in getattr(sec, "steps", []):
            if getattr(step, "status", "") == status:
                return {
                    "key":    step.key,
                    "title":  step.title,
                    "status": step.status,
                }
    return None
