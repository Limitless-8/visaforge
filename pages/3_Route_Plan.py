"""Page 3 — Route Plan (v0.15, Phase 5.6 pivot).

This page is *guidance + execution tracking* only. Document upload,
OCR, extraction, and verification have all moved to the Documents page.

Each step shows:
  * title, description, status pill, dependencies
  * required documents as a REFERENCE LIST (no upload UI here)
  * Pakistan-process help (when applicable)
  * three action buttons: Mark as Complete / Upload related document /
    Ask AI about this step

Completion rule (spec §2):
  * any step that is not 'locked' or 'blocked' can be marked complete
  * documents do NOT gate completion
  * dependencies still gate locked → available transitions

The "Upload related document" button stashes context (step_key +
suggested document types) in `st.session_state` and switches to the
Documents page so the upload widget there can pre-fill from it.
"""
from __future__ import annotations

import streamlit as st

from components.ui import (
    disclaimer,
    page_header,
    render_sidebar,
    require_profile,
    require_stage,
    require_user,
)
from services.ai_service import RouteStepContext
from services.auth_service import current_user_id
from services.pakistan_policy_service import get_process
from services.profile_service import get_profile
from services.route_plan_service import (
    can_complete_step,
    generate_and_save,
    get_next_actionable_step,
    get_persisted_plan,
    mark_step_complete,
    recompute_states_for_plan,
    resolve_required_documents,
)
from services.scholarship_service import get_selected_scholarship


# ---------- Setup --------------------------------------------------------

st.set_page_config(
    page_title="Route Plan · VisaForge",
    page_icon="🗺️", layout="wide",
)
st.session_state["_current_page_path"] = "pages/3_Route_Plan.py"



render_sidebar()
require_user()
require_stage("route_plan")
st.markdown("""
<style>
.vf-route-hero-final {
    border-radius: 28px;
    padding: 34px 44px;
    margin: 12px 0 34px 0;
    color: white;
    background:
        radial-gradient(circle at 88% 18%, rgba(255,255,255,.18), transparent 9%),
        linear-gradient(135deg,#7c3aed 0%,#2563eb 48%,#14b8a6 100%);
    box-shadow: 0 26px 72px rgba(37,99,235,.18);
}
.vf-route-hero-final h1 {
    margin: 0 0 18px 0;
    font-size: 34px;
    font-weight: 950;
    letter-spacing: -.04em;
}
.vf-route-hero-final p {
    margin: 0;
    max-width: 980px;
    font-size: 15px;
    line-height: 1.75;
    font-weight: 750;
    opacity: .96;
}

/* Route top summary polish */
.vf-route-summary-title {
    font-size: 13px;
    font-weight: 900;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 10px;
}
.vf-route-summary-main {
    font-size: 26px;
    font-weight: 950;
    color: #0f172a;
    margin-bottom: 8px;
}
.vf-route-summary-sub {
    color: #64748b;
    font-size: 14px;
    font-weight: 650;
}
.vf-route-progress-title {
    font-size: 28px;
    font-weight: 950;
    color: #0f172a;
}
.vf-route-template-pill {
    display: inline-flex;
    padding: 8px 14px;
    border-radius: 999px;
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
    font-size: 13px;
    font-weight: 900;
}


/* Regenerate button polish */
div[data-testid="stButton"] button {
    border-radius: 16px !important;
    font-weight: 850 !important;
}

.vf-regen-helper {
    color:#64748b;
    font-size:13px;
    font-weight:650;
    margin-top:8px;
}


/* Up next card polish */
.vf-next-title {
    font-size: 30px;
    font-weight: 950;
    letter-spacing: -.03em;
    color: #0f172a;
    margin-bottom: 10px;
}
.vf-next-sub {
    color: #64748b;
    font-size: 15px;
    font-weight: 650;
    line-height: 1.6;
}
.vf-next-label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 13px;
    border-radius: 999px;
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
    font-size: 13px;
    font-weight: 900;
    margin-bottom: 12px;
}

</style>

<div class="vf-route-hero-final">
    <h1>🗺️ Route Plan</h1>
    <p>Your complete guided study-abroad execution roadmap. Track scholarship preparation, Pakistan-side requirements, visa documentation, and final submission steps through a structured deterministic workflow.</p>
</div>
""", unsafe_allow_html=True)

profile_id = require_profile()

st.markdown("""
<style>

/* ---------- Route plan premium UI ---------- */

.vf-route-hero {
    padding: 28px 32px;
    border-radius: 28px;
    background:
        radial-gradient(circle at top right, rgba(59,130,246,.18), transparent 30%),
        linear-gradient(135deg,#ffffff,#f8fbff);
    border:1px solid #dbeafe;
    box-shadow:0 24px 60px rgba(37,99,235,.08);
    margin-bottom:18px;
}

.vf-route-progress {
    padding:24px 28px;
    border-radius:24px;
    background:white;
    border:1px solid #e2e8f0;
    box-shadow:0 14px 34px rgba(15,23,42,.05);
}

.vf-next-step {
    padding:24px 28px;
    border-radius:24px;
    background:
        linear-gradient(135deg,#eff6ff,#ffffff);
    border:1px solid #bfdbfe;
    box-shadow:0 14px 30px rgba(59,130,246,.08);
}

.vf-section-title {
    font-size:44px !important;
    font-weight:900 !important;
    letter-spacing:-0.03em;
    margin-bottom:6px !important;
    color:#0f172a;
}

.vf-step-card {
    border-radius:24px !important;
    border:1px solid #e2e8f0 !important;
    background:white !important;
    box-shadow:0 10px 26px rgba(15,23,42,.04) !important;
    padding-top:8px !important;
    transition:all .18s ease;
}

.vf-step-card:hover {
    transform:translateY(-2px);
    box-shadow:0 18px 42px rgba(15,23,42,.08) !important;
}

.vf-pill {
    display:inline-flex;
    align-items:center;
    gap:6px;
    padding:6px 12px;
    border-radius:999px;
    font-size:12px;
    font-weight:800;
    letter-spacing:.01em;
}

.vf-pill-available {
    background:#dbeafe;
    color:#2563eb;
}

.vf-pill-locked {
    background:#e5e7eb;
    color:#475569;
}

.vf-pill-high {
    background:#fee2e2;
    color:#dc2626;
}

.vf-pill-medium {
    background:#fef3c7;
    color:#d97706;
}

.vf-pill-completed {
    background:#dcfce7;
    color:#15803d;
}









/* Route Plan visual polish - no logic changes */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(37,99,235,.07), transparent 32%),
        linear-gradient(180deg,#fbfcff 0%,#ffffff 45%,#fbfbff 100%);
}

.block-container {
    max-width: 1220px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 24px !important;
    border: 1px solid #e2e8f0 !important;
    background: rgba(255,255,255,.96) !important;
    box-shadow: 0 18px 46px rgba(15,23,42,.055) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: #bfdbfe !important;
    box-shadow: 0 22px 54px rgba(37,99,235,.09) !important;
}

div[data-testid="stHorizontalBlock"] {
    gap: 18px !important;
}

.stProgress > div > div > div > div {
    background: linear-gradient(90deg,#2563eb,#4f46e5) !important;
}

/* Main headings */
h1 {
    letter-spacing: -.04em !important;
}

h2 {
    letter-spacing: -.035em !important;
    margin-top: 1.2rem !important;
}

h3, h4 {
    letter-spacing: -.02em !important;
}

/* Step buttons */






/* Captions and body readability */
[data-testid="stCaptionContainer"] {
    color: #64748b !important;
    font-weight: 560 !important;
    line-height: 1.6 !important;
}

/* Page links at footer */
.stPageLink a {
    border-radius: 16px !important;
    border: 1px solid #bfdbfe !important;
    background: linear-gradient(135deg,#ffffff,#eff6ff) !important;
    box-shadow: 0 12px 28px rgba(37,99,235,.08) !important;
    font-weight: 850 !important;
}

/* Expanders */
div[data-testid="stExpander"] {
    border-radius: 16px !important;
    border: 1px solid #e5e7eb !important;
    background: rgba(255,255,255,.96) !important;
}

/* Status and priority pills inside markdown */
span[style*="border-radius:12px"],
span[style*="border-radius:10px"] {
    padding: 5px 11px !important;
    border-radius: 999px !important;
    font-weight: 850 !important;
}

/* Top cards spacing */
hr {
    margin: 1.7rem 0 !important;
    border-color: #e5e7eb !important;
}

</style>
""", unsafe_allow_html=True)

profile = get_profile(profile_id)
if profile is None:
    st.error("Could not load your profile.")
    st.stop()

uid = current_user_id()
country = profile.destination_country


# ---------- Status pill helpers -----------------------------------------

# v0.15 produces only four step statuses. Legacy values from
# v0.11–v0.14 persisted plans are upgraded by the route service on
# read, so the page never sees them; the extra entries below are
# defensive (e.g. if a stale row somehow leaks through).
_STATUS_STYLE: dict[str, tuple[str, str, str]] = {
    "completed": ("✅", "#d1fadf", "#054f31"),
    "available": ("🔓", "#dbeafe", "#1d4ed8"),
    "locked":    ("🔒", "#e5e7eb", "#374151"),
    "blocked":   ("⛔", "#fee2e2", "#991b1b"),
    # Defensive fallbacks
    "pending":              ("⏳", "#fef3c7", "#854d0e"),
    "in_progress":          ("🟡", "#fef3c7", "#854d0e"),
    "ready_to_complete":    ("🟢", "#d1fadf", "#065f46"),
    "awaiting_documents":   ("📤", "#dbeafe", "#1e40af"),
    "pending_verification": ("🔄", "#fef3c7", "#854d0e"),
    "needs_attention":      ("⚠️", "#fee2e2", "#991b1b"),
}


def _status_pill(status: str) -> str:
    icon, bg, fg = _STATUS_STYLE.get(status, ("•", "#e5e7eb", "#374151"))
    return (
        f"<span style='display:inline-block;padding:2px 10px;"
        f"border-radius:12px;background:{bg};color:{fg};"
        f"font-size:0.78rem;font-weight:600;'>{icon} {status}</span>"
    )


def _priority_badge(priority: str) -> str:
    if priority == "high":
        bg, fg, label = "#fee2e2", "#991b1b", "high"
    elif priority == "low":
        bg, fg, label = "#f3f4f6", "#6b7280", "low"
    else:
        bg, fg, label = "#fef3c7", "#92400e", "medium"
    return (
        f"<span style='display:inline-block;padding:2px 8px;"
        f"border-radius:10px;background:{bg};color:{fg};"
        f"font-size:0.72rem;'>{label}</span>"
    )


# ---------- Top: scholarship + destination -------------------------------

selected = get_selected_scholarship(profile_id)

with st.container(border=True):
    h_l, h_r = st.columns([3, 1])

    with h_l:
        if selected is None:
            st.warning(
                "**No scholarship selected.** Pick one before generating "
                "your route plan — the plan is built around your specific "
                "scholarship and destination."
            )
            st.page_link("pages/4_Scholarships.py", label="Go to Scholarships", icon="🎓")
        else:
            meta = " • ".join(
                p for p in (
                    selected.provider,
                    selected.country,
                    f"deadline: {selected.deadline}" if selected.deadline else None,
                )
                if p
            )
            st.markdown(
                f"""
<div class="vf-route-summary-title">🎯 Selected scholarship</div>
<div class="vf-route-summary-main">{selected.title}</div>
<div class="vf-route-summary-sub">{meta}</div>
""",
                unsafe_allow_html=True,
            )

    with h_r:
        st.markdown(
            f"""
<div class="vf-route-summary-title">Destination</div>
<div class="vf-route-summary-main">{country or '—'}</div>
<div class="vf-route-summary-sub">Route country</div>
""",
            unsafe_allow_html=True,
        )

        btn_label = "🔄 Re-generate plan" if get_persisted_plan(profile_id, country) else "✨ Generate plan"
        if st.button(btn_label, use_container_width=True):
            plan = generate_and_save(profile_id, user_id=uid)
            if plan is None:
                st.error(
                    "Could not generate a plan. Make sure a scholarship is "
                    "selected and your destination is supported (UK, Canada, "
                    "or Germany)."
                )
                st.stop()
            st.rerun()
        st.markdown('<div class="vf-regen-helper">Refresh your workflow if your profile or scholarship changed.</div>', unsafe_allow_html=True)

if selected is None:
    st.stop()

if not country:
    st.error(
        "Your profile does not have a destination country set. Update "
        "it on the Profile page."
    )
    st.page_link("pages/1_Profile.py", label="Go to Profile", icon="👤")
    st.stop()


# ---------- Load / re-resolve / regenerate ------------------------------

# v0.10.1 bug fix preserved: recompute persisted statuses on every
# load so completion cascades through dependents.
try:
    recompute_states_for_plan(profile_id, country)
except Exception:
    pass  # display still correct via get_persisted_plan's own re-resolve

plan = get_persisted_plan(profile_id, country)


if plan is None:
    st.info(
        "No route plan yet. Click **Generate plan** above to build one "
        "tailored to your selected scholarship and destination."
    )
    st.stop()


# ---------- Overall progress + next-step CTA ----------------------------

if plan.blocked_reason:
    st.error(f"⛔ **Visa phase blocked.** {plan.blocked_reason}")

with st.container(border=True):
    st.markdown(
        f'<div class="vf-route-progress-title">Overall progress — {plan.overall_progress_pct}%</div>',
        unsafe_allow_html=True,
    )
    st.progress(plan.overall_progress_pct / 100.0)


# v0.15 spec §8: "Continue current step" CTA.
next_step = get_next_actionable_step(plan)
if next_step is not None and next_step.status != "completed":
    label = {
        "locked":    "Up next (locked)",
        "available": "Up next",
        "blocked":   "Blocked",
    }.get(next_step.status, "Up next")
    with st.container(border=True):
        cl, cr = st.columns([4, 1])
        with cl:
            next_text = next_step.status_reason or next_step.description or "Continue this step to move your route forward."
            st.markdown(
                f"""
<div class="vf-next-label">➡️ {label}</div>
<div class="vf-next-title">{next_step.title}</div>
<div class="vf-next-sub">{next_text}</div>
""",
                unsafe_allow_html=True,
            )
        with cr:
            anchor_id = f"step-{next_step.key}"
            st.markdown(
                f"<a href='#{anchor_id}' style='display:inline-flex;align-items:center;justify-content:center;width:100%;min-height:52px;background:linear-gradient(135deg,#2563eb,#4f46e5);color:white;border-radius:16px;text-decoration:none;font-weight:900;font-size:0.95rem;box-shadow:0 14px 30px rgba(37,99,235,.18);'>Continue →</a>",
                unsafe_allow_html=True,
            )


# Title lookup for dependency rendering.
_step_titles_by_key = {
    s.key: s.title for sec in plan.sections for s in sec.steps
}


# ---------- Step rendering ----------------------------------------------


def _render_pakistan_help(step) -> None:
    """Inline policy details for Pakistan-side steps."""
    if not step.pakistan_process_id:
        return
    proc = get_process(step.pakistan_process_id)
    if not proc:
        return
    with st.expander("🇵🇰 Pakistan process details"):
        if desc := proc.get("description"):
            st.write(desc)
        if reqs := proc.get("requirements"):
            st.markdown("**Requirements:**")
            for r in reqs:
                st.markdown(f"- {r}")
        if procedure := proc.get("steps"):
            st.markdown("**Process steps:**")
            for i, s in enumerate(procedure, 1):
                st.markdown(f"{i}. {s}")
        if t := proc.get("estimated_time_days"):
            st.caption(f"⏱️ Estimated time: {t} days")
        if note := proc.get("notes"):
            st.caption(f"📝 {note}")
        if url := proc.get("official_source_url"):
            st.markdown(f"🔗 [Official source]({url})")


def _render_required_docs_reference(step) -> None:
    """v0.15 spec §1: required documents shown as a REFERENCE LIST.
    No upload UI — the Documents page is the upload workspace.
    The "Upload related document" button below pre-fills the
    Documents page with the step context."""
    slots = resolve_required_documents(step)
    if not slots:
        return
    st.markdown("**📎 Supporting documents (reference):**")
    for rd in slots:
        suffix = " _(optional)_" if rd.optional else ""
        st.markdown(
            f"- **{rd.label}** "
            f"<span style='color:#6b7280;font-size:0.8rem;'>"
            f"`{rd.document_type}`</span>"
            f"{suffix}",
            unsafe_allow_html=True,
        )
    st.caption(
        "ℹ️ These documents are useful for this step but you can mark "
        "the step complete without uploading them. Upload happens on "
        "the Documents page."
    )


def _render_step(step) -> None:
    pill = _status_pill(step.status)
    pri = _priority_badge(step.priority)
    with st.container(border=True):
        # Anchor for the top-of-page Continue → link.
        st.markdown(
            f"<div id='step-{step.key}'></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**{step.order_index + 1}. {step.title}** "
            f"&nbsp;{pill}&nbsp;{pri}",
            unsafe_allow_html=True,
        )
        if step.description:
            st.caption(step.description)
        if step.status_reason:
            st.caption(f"ℹ️ {step.status_reason}")

        # Dependencies
        if step.depends_on:
            dep_titles = [
                _step_titles_by_key.get(k, k) for k in step.depends_on
            ]
            st.caption("Depends on: " + ", ".join(dep_titles))

        # Pakistan inline policy help
        _render_pakistan_help(step)

        # Required documents (reference only — spec §1, §3, §12)
        _render_required_docs_reference(step)

        # ---------- Action buttons (spec §1, §3) ----------
        st.markdown("&nbsp;")
        b1, b2, b3 = st.columns(3)

        # 1) Mark as Complete
        with b1:
            if step.status == "completed":
                st.success("✅ Completed")
            else:
                allowed, reason = can_complete_step(profile_id, step)
                if allowed:
                    if st.button(
                        "✅ Mark as Complete",
                        key=f"complete_{step.key}",
                        type="primary", use_container_width=True,
                    ):
                        ok, msg = mark_step_complete(
                            profile_id, step.key, country=country,
                        )
                        if ok:
                            st.session_state["_route_plan_toast"] = msg
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    # locked / blocked — explain why, no button
                    st.button(
                        "🔒 Locked",
                        key=f"locked_{step.key}",
                        disabled=True, use_container_width=True,
                    )
                    if reason:
                        st.caption(f"_{reason}_")

        # 2) Upload related document (spec §3)
        with b2:
            slots = resolve_required_documents(step)
            if slots:
                if st.button(
                    "📎 Upload related document",
                    key=f"upload_{step.key}",
                    use_container_width=True,
                ):
                    # Spec §3: pass step_key + suggested document types
                    # so the Documents page can pre-fill.
                    st.session_state["doc_step_context"] = {
                        "step_key": step.key,
                        "step_title": step.title,
                        "suggested_document_types": [
                            {
                                "document_type": rd.document_type,
                                "label": rd.label,
                                "optional": rd.optional,
                            }
                            for rd in slots
                        ],
                    }
                    st.switch_page("pages/5_Documents.py")
            else:
                # Soft step — no associated documents to upload.
                st.button(
                    "📎 No documents needed",
                    key=f"no_docs_{step.key}",
                    disabled=True, use_container_width=True,
                )

        # 3) Ask AI about this step
        with b3:
            if st.button(
                "🤖 Ask AI about this step",
                key=f"ai_{step.key}",
                use_container_width=True,
            ):
                st.session_state["ai_step_context"] = RouteStepContext(
                    profile_id=profile_id,
                    step_key=step.key,
                    kind="explain",
                )
                st.switch_page("pages/6_AI_Assistant.py")

        # Optional external action (e.g. "Open official source")
        if step.action_target and step.action_target.startswith("http"):
            st.markdown(
                f"🔗 [{step.action_label or 'Open official source'}]"
                f"({step.action_target})"
            )


# ---------- Sections -----------------------------------------------------

_SECTION_HEADERS = {
    "scholarship": "🎓 Section A — Scholarship Application Phase",
    "pakistan":    "🇵🇰 Section B — Pakistan Preparation Phase",
    "visa":        "🛂 Section C — Visa Application Phase",
}

# Surface a one-time toast if mark_step_complete just ran.
_toast = st.session_state.pop("_route_plan_toast", None)
if _toast:
    st.success(_toast)

for section in plan.sections:
    st.markdown(
        f"## {_SECTION_HEADERS.get(section.section_id, section.title)}"
    )
    sec_l, sec_r = st.columns([4, 1])
    with sec_l:
        st.caption(section.description)
    with sec_r:
        st.markdown(
            f"<div style='text-align:right;font-weight:600;'>"
            f"{section.progress_pct}% complete</div>",
            unsafe_allow_html=True,
        )
    st.progress(section.progress_pct / 100.0)
    if not section.steps:
        st.caption("_(no steps in this section)_")
    else:
        for step in section.steps:
            _render_step(step)
    st.markdown("&nbsp;")


# ---------- Footer ------------------------------------------------------

st.divider()
nav_l, nav_r = st.columns(2)
with nav_l:
    st.page_link(
        "pages/5_Documents.py",
        label="Document vault →", icon="📄",
    )
with nav_r:
    st.page_link(
        "pages/6_AI_Assistant.py",
        label="Open AI Assistant →", icon="🤖",
    )

disclaimer(compact=True)

# Re-apply shared button style at bottom so page CSS cannot override it

# ===== PAGE-LOCAL CONSISTENT BUTTON CSS =====

st.markdown("""
<style>
/* ===== CONSISTENT VISAFORGE BUTTONS ===== */
.stButton > button,
div[data-testid="stButton"] button,
div[data-testid="stFormSubmitButton"] button,
div[data-testid="stLinkButton"] a,
a[data-testid="stLinkButton"] {
    min-height: 52px !important;
    height: 52px !important;
    border-radius: 18px !important;
    padding: 0 26px !important;
    font-size: 16px !important;
    font-weight: 850 !important;
    border: 1px solid #bfdbfe !important;
    background: linear-gradient(135deg,#ffffff,#eff6ff) !important;
    color: #0f172a !important;
    box-shadow: 0 10px 24px rgba(37,99,235,.08) !important;
}

.stButton > button:hover,
div[data-testid="stButton"] button:hover,
div[data-testid="stFormSubmitButton"] button:hover,
div[data-testid="stLinkButton"] a:hover,
a[data-testid="stLinkButton"]:hover {
    transform: translateY(-2px) !important;
    border-color: #60a5fa !important;
    box-shadow: 0 16px 34px rgba(37,99,235,.14) !important;
}

div[data-testid="stFormSubmitButton"] button {
    background: linear-gradient(135deg,#2563eb,#14b8a6) !important;
    color: white !important;
}
</style>
""", unsafe_allow_html=True)


# ===== FINAL PAGE-LOCAL CONSISTENT BUTTON CSS =====
st.markdown("""
<style>
.stButton > button,
div[data-testid="stButton"] button,
button[kind="primary"],


.stButton > button:hover,
div[data-testid="stButton"] button:hover {
    transform: translateY(-2px) !important;
    border-color: #60a5fa !important;
    box-shadow: 0 16px 34px rgba(37,99,235,.14) !important;
}


</style>
""", unsafe_allow_html=True)

