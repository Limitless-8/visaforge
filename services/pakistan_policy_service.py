"""
services/pakistan_policy_service.py
-----------------------------------
Deterministic, source-attributed Pakistan-specific process data.

Used by:
  * services/route_plan_service.py — to inject Pakistan-specific
    preparation steps (HEC attestation, MOFA, PCC, etc.) into a
    user's destination-aware route plan.
  * pages/6_AI_Assistant.py — to provide structured grounding context
    when a user clicks "How to complete this in Pakistan" on a step.

Read-only. JSON-backed. Never mutates state. Cached at module level
so repeated calls in a render loop are cheap.

No AI. No network. Every fact ties back to an `official_source_url`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from config.settings import SEEDS_DIR
from utils.helpers import safe_load_json
from utils.logger import get_logger

log = get_logger(__name__)


# ---------- Loader -------------------------------------------------------


@lru_cache(maxsize=1)
def _processes() -> dict[str, dict]:
    """Return a dict of process_id → process record, loaded from
    data/seeds/pakistan_processes.json."""
    doc = safe_load_json(SEEDS_DIR / "pakistan_processes.json") or {}
    procs: dict[str, dict] = {}
    for p in doc.get("processes") or []:
        pid = p.get("id")
        if not pid:
            continue
        procs[pid] = p
    if not procs:
        log.warning(
            "No Pakistan policy processes loaded. Check that "
            "data/seeds/pakistan_processes.json is present and parses."
        )
    return procs


def reload() -> int:
    """Force-clear the module cache and reload the JSON. Returns the
    new count of processes."""
    _processes.cache_clear()
    return len(_processes())


# ---------- Reads --------------------------------------------------------


def get_process(process_id: str) -> Optional[dict]:
    """Return one process record by id, or None if unknown."""
    return _processes().get(process_id)


def list_processes() -> list[dict]:
    """All processes, in the order they appear in the seed file."""
    return list(_processes().values())


def list_processes_for_country(country: str) -> list[dict]:
    """Processes that apply to a given destination country.

    A process applies if `applicable_countries` includes the country
    or is the literal string "any". Returned in seed order.
    """
    if not country:
        return []
    out: list[dict] = []
    for proc in _processes().values():
        applicable = proc.get("applicable_countries") or []
        if applicable == "any":
            out.append(proc)
            continue
        if isinstance(applicable, list) and country in applicable:
            out.append(proc)
    return out


def required_for_destination(country: str) -> list[str]:
    """Return process_ids that should appear in the Pakistan
    Preparation Phase of a route plan for the given destination.

    Currently returns every process applicable to the country (the
    UI later marks each step's status against profile/document data).
    Encapsulated as a function so the policy can grow more selective
    later (e.g. omit MOFA for UK self-funded routes) without touching
    the route plan generator.
    """
    return [p["id"] for p in list_processes_for_country(country)]


def explain_for_ai(process_id: str) -> Optional[dict]:
    """Return a stable, AI-friendly subset of a process record so the
    assistant can ground answers in the official text without inventing.

    Stripped to the fields the AI is allowed to surface: name,
    description, requirements, steps, estimated_time_days,
    when_required, notes, and the official_source_url. The id and
    applicable_countries are also included for citation.
    """
    proc = get_process(process_id)
    if proc is None:
        return None
    keys = (
        "id", "name", "description", "requirements", "steps",
        "estimated_time_days", "when_required", "notes",
        "official_source_url", "applicable_countries",
    )
    return {k: proc.get(k) for k in keys if k in proc}
