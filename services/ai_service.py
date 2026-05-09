"""
services/ai_service.py
----------------------
v0.18 (Phase 6): Upgraded to Pakistan Immigration Expert Mode.

Phase 6 adds:
* Pakistan expert system prompt (default for all users)
* Readiness score + risk list injected into every context packet
* `build_context` now accepts pre-computed readiness / risks so the
  dashboard can pass them without re-computing
* New quick-question presets for the AI Assistant page
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from llm.factory import get_llm_provider
from models.orm import UserProfile
from models.schemas import (
    DynamicRoutePlanDTO,
    DynamicRouteStepDTO,
    EligibilityReport,
    LLMMessage,
    LLMResponse,
    ScholarshipDTO,
)
from services import (
    eligibility_service,
    pakistan_policy_service,
    route_plan_service,
    scholarship_service,
)
from services.profile_service import get_profile
from utils.logger import get_logger

log = get_logger(__name__)


# ---------- System prompts -----------------------------------------------

# v0.18 Phase 6: Pakistan Immigration Expert base section.
# Prepended to EVERY system prompt so all interactions carry Pakistan
# domain knowledge by default.
_PAKISTAN_EXPERT_PREAMBLE = """
You are an expert immigration advisor specifically for Pakistani students.

You have deep knowledge of:

HEC (Higher Education Commission Pakistan):
- Degree attestation requirements and process
- Online portal workflow (HEC e-Portal)
- Required documents: original degree, transcript, ID card copy
- Timeline: typically 3–6 weeks; expedited in 1–2 weeks for fee
- After HEC: document must go to MOFA for foreign use

IBCC (Inter Board Committee of Chairmen):
- Equivalence certificate for O-Level / A-Level / Matric / FSc
- Required: SSC / HSSC certificate, mark sheets, school leaving
  certificate; passport, CNIC
- Processing time: 2–4 weeks
- Online portal available at ibcc.edu.pk

MOFA (Ministry of Foreign Affairs Pakistan):
- Attestation of HEC / IBCC / NADRA documents for foreign use
- Required AFTER HEC / IBCC attestation
- Types: Normal (4–7 days), Express (1–2 days)
- Islamabad head office + regional offices in Lahore, Karachi

NADRA (National Database and Registration Authority):
- Issues CNIC (Computerized National Identity Card)
- B-Form for minors
- Family Registration Certificate (FRC)
- CNIC needed for: HEC application, MOFA attestation, visa applications

Police Clearance Certificate (PCC):
- Required for many student visa applications
- Obtained from the relevant District Police Office or via:
  - Online at dgip.gov.pk (some provinces)
  - In person at the district Superintendent of Police office
- Required for UK visas when the student has lived abroad 12+ months

English Language Requirements:
- UK: IELTS 6.0–7.0 depending on course; typically 6.5 for postgraduate
- Canada: IELTS 6.0–6.5 for most universities
- Germany: 6.0 for English-medium; TestDaF / DSH for German-medium
- TOEFL / PTE / Duolingo accepted by many institutions

Student Visa Processes:
- UK: CAS (Confirmation of Acceptance for Studies) from university →
  Student Visa application; biometrics; decision in 3 weeks typically
- Canada: Letter of Acceptance → Study Permit online; 8–12 weeks
- Germany: APS (Academic Evaluation Centre) certificate required for
  Pakistani students; blocked bank account (Sperrkonto) ≥ €11,208/year;
  apply at German Embassy Islamabad

GUARDRAILS — these override all other guidance:
- Do NOT invent official rules, fees, timelines, or office addresses
  beyond what is stated in this prompt or the structured context below
- Do NOT guarantee visa approval or claim a document is authentic
- Do NOT override any deterministic status in the context
- Refer users to official sources: hec.gov.pk, ibcc.edu.pk, nadra.gov.pk,
  mofa.gov.pk, vfsglobal.com, canada.ca, bamf.de, auswaertiges-amt.de

Always mention that visa rules change, and advise the user to verify
current requirements from official sources before submitting.
"""


# ---------- System prompts -----------------------------------------------

# General-purpose grounding prompt (open chat surface, no step focus).
# v0.18: Pakistan expert preamble prepended.
SYSTEM_PROMPT_GENERAL = _PAKISTAN_EXPERT_PREAMBLE + """

ADDITIONAL RULES FOR OPEN CHAT:
1. You are ADVISORY ONLY. You MUST NOT override or contradict the
   deterministic decision in the context. Use the value of
   `eligibility_report.decision` as the authoritative verdict:
   ELIGIBLE / CONDITIONALLY_ELIGIBLE / HIGH_RISK / NOT_ELIGIBLE.
2. NEVER invent scholarship names, deadlines, URLs, visa rules, or
   next steps that are not present in the provided context. If
   information is missing, say so plainly.
3. When the user asks about eligibility, anchor your answer in
   `eligibility_report.decision`, `blocking_issues`, `important_gaps`,
   and `next_steps`. Prefer paraphrasing the user's own data back to
   them in plain language.
4. For recommendations, ONLY reference items from
   `eligibility_report.next_steps` or `eligibility_report.timeline_plan`.
   Do not invent new steps.
5. When discussing scholarships, cite the `source_name` and
   `source_url` from the provided list. Do not recommend opportunities
   outside the list.
6. You are NOT a lawyer. Add a short reminder that this is guidance,
   not legal advice, when the user asks anything high-stakes.
7. Be concise, practical, and kind. Prefer bullet points for steps.
8. If the user profile is missing a field relevant to their question,
   ask for it before answering.
9. Use `readiness` and `risks` in context when available to personalise
   guidance. Reference specific risk items by name (e.g. "your IELTS
   score is flagged as a risk").

Always ground your answer in the JSON context supplied below.
"""


# v0.10 step-focused system prompt — updated with Pakistan expertise.
SYSTEM_PROMPT_STEP_FOCUSED = _PAKISTAN_EXPERT_PREAMBLE + """

YOUR ROLE FOR THIS TURN:
The user clicked an "Explain this step" or "How to complete this in
Pakistan" button on a route step. Their question relates to a single
step of their personalised route plan.

STRICT RULES:
1. Read the `current_step` block in the grounding context. That step
   has a deterministic `status` (locked / available / completed /
   blocked). You MUST NOT change, override, or claim to override that
   status.
2. If the step has a `pakistan_process` block in context, use ONLY
   the requirements, steps, time estimate, and `official_source_url`
   from that block. Do not introduce other procedures.
3. If `current_step.depends_on` is non-empty and any of those
   dependencies are not yet completed, explain that the step is
   waiting on those dependencies — name them by title.
4. NEVER invent deadlines, fees, processing times, or office locations
   beyond what the structured context contains.
5. End with the official source URL when available.

Be concise and practical. Use bullet points for procedural steps.
Always ground your answer in the JSON context below.
"""


# v0.11 document-focused system prompt — updated with Pakistan expertise.
SYSTEM_PROMPT_DOCUMENT_FOCUSED = _PAKISTAN_EXPERT_PREAMBLE + """

YOUR ROLE FOR THIS TURN:
The user clicked "Ask AI about this document". The grounding context
contains a `current_document` block with:
  - document_type, verification_status, extracted_fields, issues,
    warnings, extracted_text (when available)

STRICT RULES:
1. Treat `verification_status` and `issues` as AUTHORITATIVE. You MUST
   NOT contradict them, mark a document valid/invalid, or claim the
   verification was wrong.
2. Do NOT authenticate the document. Explain each issue in plain
   English. Suggest concrete next steps.
3. If the document is a Pakistan-side process (e.g. HEC attestation,
   MOFA, NADRA), use the procedural knowledge in your preamble to
   advise the user on the standard process.
4. NEVER invent fees or office locations beyond the context + preamble.
5. If extracted_fields is empty and verification_status is
   extraction_failed, explain OCR failure and suggest fixes.

Be concise. Use bullet points. Always ground your answer in context.
"""


# ---------- Profile / report / plan / scholarship serialisers -----------

def _profile_to_dict(p: UserProfile) -> dict:
    keys = [
        "id", "full_name", "age", "nationality", "country_of_residence",
        "passport_valid_until", "previous_travel_history",
        "education_level", "gpa", "previous_field_of_study",
        "english_test_type", "english_test_score",
        "destination_country", "intended_degree_level",
        "intended_institution_type",
        "offer_letter_status", "proof_of_funds_status",
        "has_offer_letter", "has_proof_of_funds", "has_dependents",
        "field_of_study", "target_intake", "budget_notes", "notes",
    ]
    return {k: getattr(p, k, None) for k in keys}


def _report_to_dict(r: EligibilityReport) -> dict:
    """Serialize the full v0.3 report for the LLM context."""
    data = r.model_dump(mode="json")
    data.setdefault("decision", r.decision)
    data.setdefault("overall_confidence", r.confidence)
    return data


def _step_to_dict(s: DynamicRouteStepDTO) -> dict:
    return {
        "key": s.key,
        "title": s.title,
        "description": s.description,
        "status": s.status,
        "status_reason": s.status_reason,
        "depends_on": list(s.depends_on),
        "source": s.source,
        "priority": s.priority,
        "required_documents": list(s.required_documents),
        "section_id": s.section_id,
        "pakistan_process_id": s.pakistan_process_id,
        "action_label": s.action_label,
        "action_target": s.action_target,
    }


def _plan_to_dict(plan: DynamicRoutePlanDTO) -> dict:
    return {
        "destination_country": plan.destination_country,
        "template_key": plan.template_key,
        "scholarship_id": plan.scholarship_id,
        "overall_progress_pct": plan.overall_progress_pct,
        "blocked_reason": plan.blocked_reason,
        "sections": [
            {
                "section_id": sec.section_id,
                "title": sec.title,
                "progress_pct": sec.progress_pct,
                "steps": [_step_to_dict(st) for st in sec.steps],
            }
            for sec in plan.sections
        ],
    }


def _scholarship_to_dict(s: ScholarshipDTO) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "provider": s.provider,
        "country": s.country,
        "degree_level": s.degree_level,
        "deadline": s.deadline,
        "summary": s.summary,
        "source_url": s.source_url,
        "source_name": s.source_name,
        "credibility": s.credibility,
        "review_status": s.review_status,
        "source_type": s.source_type,
    }


# ---------- Step-focused context dataclass -------------------------------


@dataclass
class RouteStepContext:
    """Ephemeral packet handed from the Route Plan / Documents pages
    to the AI Assistant when the user clicks Explain / How-in-Pakistan /
    Ask AI / Explain Issues / Ask AI about this document.

    The originating page builds this and stores it under
    `st.session_state['ai_step_context']`. The AI Assistant page
    consumes it on next render and clears the session entry.

    `kind` controls the default question composed if the user doesn't
    type their own:
      * "explain"   — explain this step in plain English
      * "pakistan"  — Pakistan-specific procedure for this step
      * "ask"       — generic "ask AI about this step"
      * "issues"    — v0.11: explain document verification issues
      * "document"  — v0.15: explain a document's content + how it
                     fits into the visa/scholarship process

    `step_key` is optional in v0.15: for "document" kind handoffs from
    the Documents page (free-form upload, no related step), `step_key`
    can be the empty string and the AI will answer based on the
    document context only.

    For "issues" / "document", `document_id` MUST be set. The context
    builder loads the matching CaseDocument and adds a
    `current_document` block to the grounding payload.
    """
    profile_id: int
    step_key: str = ""
    kind: str = "explain"
    user_question: Optional[str] = None
    document_id: Optional[int] = None  # v0.11+: for kind=issues/document


# ---------- Context builder ---------------------------------------------


def build_context(
    profile_id: int,
    *,
    focused_step_key: Optional[str] = None,
    focused_document_id: Optional[int] = None,
    readiness: Optional[dict] = None,
    risks: Optional[list] = None,
) -> dict:
    """Assemble the grounded context packet for the LLM.

    v0.18 (Phase 6): also accepts pre-computed `readiness` and `risks`
    dicts/lists (from readiness_service / risk_engine). If not provided,
    they are computed inside this function. Pass them from the dashboard
    to avoid duplicate computation.
    """
    ctx: dict[str, Any] = {
        "profile": None,
        "eligibility_report": None,
        "route_plan": None,
        "selected_scholarship": None,
        "saved_scholarships": [],
        "top_scholarships": [],
        "current_step": None,
        "pakistan_process": None,
        "current_document": None,
        # v0.18 Phase 6 additions
        "readiness": None,
        "risks": [],
        "next_action": None,
    }

    profile = get_profile(profile_id)
    if profile is None:
        return ctx
    ctx["profile"] = _profile_to_dict(profile)

    # Eligibility
    report = None
    try:
        report = eligibility_service.evaluate_eligibility(profile)
        ctx["eligibility_report"] = _report_to_dict(report)
    except Exception as e:
        log.warning("eligibility for ctx failed: %s", e)

    # Selected scholarship
    selected = None
    try:
        selected = scholarship_service.get_selected_scholarship(profile_id)
        if selected is not None:
            ctx["selected_scholarship"] = _scholarship_to_dict(selected)
    except Exception as e:
        log.warning("selected scholarship for ctx failed: %s", e)

    # Route plan
    plan: Optional[DynamicRoutePlanDTO] = None
    try:
        if profile.destination_country:
            plan = route_plan_service.get_persisted_plan(
                profile_id, profile.destination_country
            )
            if plan is None:
                plan = route_plan_service.generate_plan(profile_id)
        if plan is not None:
            ctx["route_plan"] = _plan_to_dict(plan)
    except Exception as e:
        log.warning("route plan for ctx failed: %s", e)

    # Focused step + Pakistan policy
    if focused_step_key and plan is not None:
        for sec in plan.sections:
            for step in sec.steps:
                if step.key == focused_step_key:
                    ctx["current_step"] = _step_to_dict(step)
                    if step.pakistan_process_id:
                        proc = pakistan_policy_service.explain_for_ai(
                            step.pakistan_process_id
                        )
                        if proc is not None:
                            ctx["pakistan_process"] = proc
                    break
            if ctx["current_step"]:
                break

    # Focused document
    if focused_document_id is not None:
        try:
            from services.document_service import get_evidence_by_id
            evidence = get_evidence_by_id(focused_document_id)
        except Exception as e:
            log.warning("evidence load for ctx failed: %s", e)
            evidence = None
        if evidence is not None:
            ctx["current_document"] = {
                "id": evidence.id,
                "step_key": evidence.step_key,
                "document_type": evidence.document_type,
                "original_filename": evidence.original_filename,
                "mime_type": evidence.mime_type,
                "verification_status": evidence.verification_status,
                "extracted_fields": evidence.extracted_fields,
                "issues": list(evidence.issues),
                "warnings": list(evidence.warnings),
                "extracted_text": (
                    (evidence.extracted_text or "")[:500]
                    if evidence.extracted_text else None
                ),
                "uploaded_at": (
                    evidence.uploaded_at.isoformat()
                    if evidence.uploaded_at else None
                ),
            }
            if (ctx["current_step"] is None
                    and evidence.step_key
                    and plan is not None):
                for sec in plan.sections:
                    for step in sec.steps:
                        if step.key == evidence.step_key:
                            ctx["current_step"] = _step_to_dict(step)
                            if step.pakistan_process_id:
                                proc = pakistan_policy_service.explain_for_ai(
                                    step.pakistan_process_id
                                )
                                if proc is not None:
                                    ctx["pakistan_process"] = proc
                            break
                    if ctx["current_step"]:
                        break

    # Scholarships
    try:
        ctx["saved_scholarships"] = [
            _scholarship_to_dict(s)
            for s in scholarship_service.list_bookmarks(profile_id)
        ][:5]
        if profile.destination_country:
            ctx["top_scholarships"] = [
                _scholarship_to_dict(s)
                for s in scholarship_service.list_scholarships(
                    country=profile.destination_country, limit=8,
                )
            ]
    except Exception as e:
        log.warning("scholarships for ctx failed: %s", e)

    # v0.18: Readiness + risks (use pre-computed if provided)
    try:
        if readiness is not None:
            ctx["readiness"] = readiness
        else:
            from services.readiness_service import compute_readiness
            from services.document_service import list_evidence_for_profile
            docs = []
            try:
                docs = list_evidence_for_profile(profile_id) or []
            except Exception:
                pass
            ctx["readiness"] = compute_readiness(
                profile=profile,
                eligibility_report=report,
                selected_scholarship=selected,
                route_plan=plan,
                documents=docs,
            )
    except Exception as e:
        log.warning("readiness for ctx failed: %s", e)

    try:
        if risks is not None:
            ctx["risks"] = risks
        else:
            from services.risk_engine import detect_risks
            ctx["risks"] = detect_risks(
                profile=profile,
                eligibility_report=report,
                route_plan=plan,
                selected_scholarship=selected,
            )
    except Exception as e:
        log.warning("risks for ctx failed: %s", e)

    try:
        from services.next_step_service import get_next_action
        ctx["next_action"] = get_next_action(
            profile=profile,
            route_plan=plan,
            risks=ctx.get("risks") or [],
            selected_scholarship=selected,
            eligibility_report=report,
        )
    except Exception as e:
        log.warning("next_action for ctx failed: %s", e)

    return ctx


# ---------- Public chat entrypoints --------------------------------------


def _provider_unavailable_response(provider) -> LLMResponse:
    return LLMResponse(
        content=(
            "⚠️ AI provider is not configured. Please set the LLM "
            "API key in your environment or Streamlit secrets. "
            "Meanwhile, your deterministic results on the Eligibility, "
            "Route Plan, and Scholarships pages remain valid."
        ),
        provider=provider.name,
        model="unconfigured",
    )


def _llm_error_response(provider, e: Exception) -> LLMResponse:
    log.exception("LLM call failed")
    return LLMResponse(
        content=(
            f"Sorry — the AI service errored ({e.__class__.__name__}). "
            "The deterministic pages (Eligibility, Route Plan, "
            "Scholarships) are unaffected."
        ),
        provider=provider.name,
        model="error",
    )


def ask(
    profile_id: int,
    user_message: str,
    history: Optional[list[LLMMessage]] = None,
    *,
    focused_step_key: Optional[str] = None,
    focused_document_id: Optional[int] = None,
) -> LLMResponse:
    """Answer a free-form user question, grounded in the deterministic
    context.

    Pass `focused_step_key` for step-focused chat (current_step +
    pakistan_process blocks). Pass `focused_document_id` for v0.11
    document-issue chat (current_document block + the system prompt
    that forbids the AI from validating documents itself).
    """
    provider = get_llm_provider()
    if not provider.is_available():
        return _provider_unavailable_response(provider)

    context = build_context(
        profile_id,
        focused_step_key=focused_step_key,
        focused_document_id=focused_document_id,
    )
    context_json = json.dumps(context, default=str, indent=2)

    if focused_document_id is not None:
        system_prompt = SYSTEM_PROMPT_DOCUMENT_FOCUSED
    elif focused_step_key:
        system_prompt = SYSTEM_PROMPT_STEP_FOCUSED
    else:
        system_prompt = SYSTEM_PROMPT_GENERAL

    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(
            role="system",
            content=(
                "GROUNDING CONTEXT (JSON). Treat as authoritative; do not "
                "contradict it.\n\n" + context_json
            ),
        ),
    ]
    if history:
        messages.extend(history[-8:])
    messages.append(LLMMessage(role="user", content=user_message))

    try:
        return provider.chat(messages, temperature=0.2, max_tokens=900)
    except Exception as e:
        return _llm_error_response(provider, e)


def ask_about_step(
    ctx: RouteStepContext,
    *,
    history: Optional[list[LLMMessage]] = None,
) -> tuple[str, LLMResponse]:
    """Compose a default question for the requested kind and answer it.

    Returns (composed_or_user_question, response) so the caller can
    display the question in the chat history. Honors the user's typed
    question if `ctx.user_question` is set.
    """
    if ctx.user_question and ctx.user_question.strip():
        question = ctx.user_question.strip()
    elif ctx.kind == "issues":
        question = (
            "Please explain the verification issues found on this "
            "document. Use only the issues, extracted_fields, and "
            "verification_status in `current_document`. Tell me what "
            "to fix and how to re-upload, but do NOT claim the "
            "document is valid or invalid — that's the deterministic "
            "service's job."
        )
    elif ctx.kind == "document":
        # v0.15 spec §7: "Ask AI about this document" handoff from the
        # Documents page. AI explains content + missing info +
        # relation to visa process. AI must NOT verify authenticity
        # or mark steps complete.
        question = (
            "Please explain what this document contains in plain "
            "English. Use only the extracted_text, extracted_fields, "
            "and document_type in `current_document`. Highlight any "
            "information that looks missing or unclear, and explain "
            "how this document fits into the user's visa or "
            "scholarship process. Do NOT claim the document is "
            "authentic, valid, or invalid — that is not your role."
        )
    elif ctx.kind == "pakistan":
        question = (
            "How do I complete this step in Pakistan? Use only the "
            "Pakistan-specific procedure in context. Reference the "
            "official source URL if available."
        )
    else:  # "explain" / "ask"
        question = (
            "Please explain this step in plain English. What does it "
            "mean, why does it matter for my route plan, and what do "
            "I need to do next? Reference my profile data and any "
            "dependencies in context."
        )

    response = ask(
        ctx.profile_id, question, history=history,
        focused_step_key=ctx.step_key,
        focused_document_id=ctx.document_id,
    )
    return question, response
