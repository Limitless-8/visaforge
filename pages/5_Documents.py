"""Page 5 — Documents (v0.15, Phase 5.6 pivot).

This is the *central document intelligence workspace*. All uploads,
OCR, extraction, and verification-as-warning happen here. The Route
Plan page is reference-only and links here when the user clicks
"Upload related document" on a step.

Top of page: Upload form.
  * Document type (optional dropdown)
  * Related step (optional dropdown, pre-filled when arriving from
    Route Plan via `st.session_state['doc_step_context']`)
  * File picker
  * Upload runs OCR + extraction; verification runs as informational
    warnings only (it does NOT gate route progress).

Per-document cards show everything: filename, type, linked step,
extraction method, extraction status, extracted text, structured
fields, verification status (as a hint, not a gate), and four
actions: Re-upload / Delete / Reprocess OCR / Ask AI.
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
from services.document_service import (
    confirm_document_manually,
    delete_document,
    list_evidence_for_profile,
    reprocess_document,
    save_uploaded_document,
)
from services.profile_service import get_profile
from services.route_plan_service import (
    get_persisted_plan,
    resolve_required_documents,
)


# ---------- Setup --------------------------------------------------------

st.set_page_config(
    page_title="Documents ? VisaForge",
    page_icon="??",
    layout="wide",
)
st.session_state["_current_page_path"] = "pages/5_Documents.py"



render_sidebar()
require_user()
require_stage("documents")
st.markdown("""
<style>
.vf-doc-hero {
    border-radius: 28px;
    padding: 34px 44px;
    margin: 0 0 30px 0;
    color: white;
    background: linear-gradient(135deg,#7c3aed 0%,#2563eb 50%,#14b8a6 100%);
    box-shadow: 0 26px 72px rgba(37,99,235,.18);
}
.vf-doc-hero h1 {
    margin: 0 0 18px 0;
    font-size: 34px;
    font-weight: 950;
    letter-spacing: -.04em;
}
.vf-doc-hero p {
    margin: 0;
    max-width: 980px;
    font-size: 15px;
    line-height: 1.75;
    font-weight: 750;
    opacity: .96;
}
</style>

<div class="vf-doc-hero">
    <h1>Documents</h1>
    <p>Upload, organise, and analyse your supporting documents. OCR extraction, verification hints, and AI explanations all happen here.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
.block-container {
    padding-top: 0.6rem !important;
    margin-top: 0 !important;
}

.vf-doc-hero {
    margin-top: 18px !important;
}
</style>
""", unsafe_allow_html=True)

profile_id = require_profile()
profile = get_profile(profile_id)
if profile is None:
    st.error("Could not load your profile.")
    st.stop()

uid = current_user_id()
country = profile.destination_country or "UK"


# ---------- Document-type catalog (used by the upload dropdown) ---------

# Friendly labels for the document_type dropdown. Pulled from the same
# names the OCR field-extractor + verification service understand.
_DOC_TYPE_OPTIONS: list[tuple[str, str]] = [
    ("",                     "— Auto-detect / unspecified —"),
    ("passport",             "Passport scan"),
    ("transcript",           "Academic transcript"),
    ("degree_certificate",   "Degree certificate"),
    ("english_test",         "English test report (IELTS / TOEFL / PTE)"),
    ("ielts",                "IELTS report"),
    ("toefl",                "TOEFL report"),
    ("offer_letter",         "Offer / acceptance letter"),
    ("cas_letter",           "CAS letter (UK)"),
    ("loa_letter",           "Letter of Acceptance (Canada)"),
    ("zulassung",            "Zulassungsbescheid (Germany)"),
    ("bank_statement",       "Bank statement / proof of funds"),
    ("sponsor_letter",       "Sponsor letter"),
    ("hec_attestation",      "HEC attestation evidence"),
    ("ibcc_equivalence",     "IBCC equivalence / attestation"),
    ("mofa_attestation",     "MOFA attestation evidence"),
    ("police_clearance",     "Police clearance certificate"),
    ("tb_test",              "TB test certificate"),
    ("nadra_documents",      "CNIC / B-Form / Birth Certificate"),
]
_DOC_TYPE_LABELS: dict[str, str] = {k: v for k, v in _DOC_TYPE_OPTIONS}


# ---------- Verification-status pill (informational only) ----------------

# v0.15: verification status is shown as a *hint*, never as a gate.
# Status values come from `services/document_verification_service.py`.
#
# v0.16 spec §2 + v0.17 spec §11: the raw enum is mapped to a
# user-friendly display label. Mapping:
#   verified / user_confirmed / admin_verified
#     / processed / processed_with_warnings → "Processed"
#   manual_review_required / needs_attention / pending
#     / needs_review / weak_ocr → "Needs review"
#   extraction_failed / rejected / could_not_read → "Couldn't read"
_STATUS_DISPLAY: dict[str, tuple[str, str, str, str]] = {
    # raw_status: (icon, bg, fg, friendly_label)
    "verified":                ("✅", "#d1fadf", "#054f31", "Processed"),
    "user_confirmed":          ("👤", "#dbeafe", "#1d4ed8", "Processed (you reviewed)"),
    "admin_verified":          ("👑", "#d1fadf", "#054f31", "Processed (admin reviewed)"),
    "processed":               ("✅", "#d1fadf", "#054f31", "Processed"),
    "processed_with_warnings": ("⚠️", "#fef3c7", "#854d0e", "Processed (with warnings)"),
    "manual_review_required":  ("🟡", "#fef3c7", "#854d0e", "Needs review"),
    "needs_attention":         ("🟡", "#fef3c7", "#854d0e", "Needs review"),
    "needs_review":            ("🟡", "#fef3c7", "#854d0e", "Needs review"),
    "pending":                 ("⏳", "#fef3c7", "#854d0e", "Needs review"),
    "weak_ocr":                ("🟡", "#fef3c7", "#854d0e", "Needs review (weak OCR)"),
    "extraction_failed":       ("❌", "#fee2e2", "#991b1b", "Couldn't read"),
    "could_not_read":          ("❌", "#fee2e2", "#991b1b", "Couldn't read"),
    "rejected":                ("⛔", "#fee2e2", "#991b1b", "Couldn't read"),
}


def _verif_pill(status: str) -> str:
    icon, bg, fg, label = _STATUS_DISPLAY.get(
        status, ("•", "#e5e7eb", "#374151", status or "—"),
    )
    return (
        f"<span style='display:inline-block;padding:2px 10px;"
        f"border-radius:12px;background:{bg};color:{fg};"
        f"font-size:0.78rem;font-weight:600;'>{icon} {label}</span>"
    )


def _friendly_status(status: str) -> str:
    """Plain string for use in flash messages and titles."""
    _, _, _, label = _STATUS_DISPLAY.get(
        status, ("", "", "", status or "—"),
    )
    return label


# ---------- OCR quality badge --------------------------------------------

_OCR_QUALITY_STYLE: dict[str, tuple[str, str, str]] = {
    # label: (icon, bg, fg)
    "good":   ("🟢", "#d1fadf", "#054f31"),
    "medium": ("🟡", "#fef3c7", "#854d0e"),
    "weak":   ("🔴", "#fee2e2", "#991b1b"),
}


def _ocr_quality_badge(label: str | None, score: float | None) -> str:
    """Render a small coloured badge for the OCR quality label."""
    if not label:
        return ""
    icon, bg, fg = _OCR_QUALITY_STYLE.get(
        label, ("•", "#e5e7eb", "#374151")
    )
    score_str = f" ({score:.0%})" if score is not None else ""
    return (
        f"<span style='display:inline-block;padding:2px 8px;"
        f"border-radius:10px;background:{bg};color:{fg};"
        f"font-size:0.72rem;'>"
        f"{icon} OCR: {label}{score_str}</span>"
    )


# ---------- Step dropdown (related_step picker) -------------------------

# Build step options from the user's persisted route plan so the user
# can link an upload to one of their actual steps.
_step_options: list[tuple[str, str]] = [("", "— Not linked to a step —")]
_route_plan = None
try:
    _route_plan = get_persisted_plan(profile_id, country)
except Exception:
    _route_plan = None
if _route_plan:
    for sec in _route_plan.sections:
        for step in sec.steps:
            _step_options.append((step.key, f"{step.title}  ({sec.title})"))


# ---------- Tesseract install banner ------------------------------------

_all_evidence = list_evidence_for_profile(profile_id)
if any(getattr(ev, "extraction_status", None) == "tesseract_missing"
       for ev in _all_evidence):
    st.warning(
        "🔧 **Tesseract OCR not installed.** Some image uploads couldn't "
        "be read. Install Tesseract OCR and add it to your PATH, then "
        "use **Reprocess OCR** below to retry. Text-based PDFs work "
        "without Tesseract."
    )
    with st.expander("How to install Tesseract on Windows"):
        st.markdown(
            "1. Download the installer from the "
            "[UB-Mannheim builds]"
            "(https://github.com/UB-Mannheim/tesseract/wiki).\n"
            "2. Run the installer (default path: "
            "`C:\\Program Files\\Tesseract-OCR`).\n"
            "3. Add that directory to your `PATH`.\n"
            "4. Verify with `tesseract --version` in a new "
            "PowerShell window.\n"
            "5. Restart Streamlit and click **Reprocess OCR** on "
            "the affected documents."
        )



st.markdown("""
<style>
.vf-upload-title {
    display:flex;
    align-items:center;
    gap:14px;
    margin: 18px 0 16px 0;
}

.vf-upload-icon {
    width:52px;
    height:52px;
    border-radius:16px;
    display:grid;
    place-items:center;
    color:white;
    font-size:26px;
    background:linear-gradient(135deg,#2563eb,#14b8a6);
    box-shadow:0 14px 32px rgba(37,99,235,.22);
}

.vf-upload-title h2 {
    margin:0 !important;
    font-size:34px !important;
    font-weight:950 !important;
    letter-spacing:-.04em !important;
    color:#0f172a !important;
}

div[data-testid="stFileUploader"] section {
    border-radius:20px !important;
    border:1px dashed #bfdbfe !important;
    background:linear-gradient(135deg,#f8fbff,#f1f5f9) !important;
    padding:22px !important;
}

div[data-testid="stFileUploader"] button {
    border-radius:14px !important;
    font-weight:850 !important;
    min-height:48px !important;
}

div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    border-radius:14px !important;
    background:#f8fafc !important;
    border:1px solid #e5e7eb !important;
    min-height:54px !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius:24px !important;
    border:1px solid #dbeafe !important;
    box-shadow:0 18px 44px rgba(15,23,42,.055) !important;
    background:rgba(255,255,255,.96) !important;
}
</style>
""", unsafe_allow_html=True)


# ---------- Upload form (top of page) -----------------------------------

st.markdown("### ⬆️ Upload a document")

# Spec §3: the Route Plan "Upload related document" button stashes
# step context in session state. Pull and clear it so the dropdowns
# pre-fill with the suggested type + step.
incoming_ctx = st.session_state.pop("doc_step_context", None)
preselect_step = ""
preselect_type = ""
suggested_types_blurb = None
if incoming_ctx:
    preselect_step = incoming_ctx.get("step_key", "") or ""
    suggested = incoming_ctx.get("suggested_document_types") or []
    if suggested:
        # Default to the first non-optional suggested type, falling
        # back to the first suggestion overall.
        non_optional = [s for s in suggested if not s.get("optional")]
        chosen = (non_optional or suggested)[0]
        preselect_type = chosen.get("document_type", "") or ""
        # Friendly blurb shown above the form so the user knows where
        # the pre-fill came from.
        types_str = ", ".join(s.get("label", "") for s in suggested if s.get("label"))
        suggested_types_blurb = (
            f"Suggested for **{incoming_ctx.get('step_title','this step')}**: "
            f"{types_str}"
        )

if suggested_types_blurb:
    st.info("📎 " + suggested_types_blurb)

# Make sure preselect values exist in their dropdowns; fall back to
# blank if not (e.g. step was renamed since context was created).
_doc_type_keys = [k for k, _ in _DOC_TYPE_OPTIONS]
if preselect_type not in _doc_type_keys:
    preselect_type = ""
_step_keys = [k for k, _ in _step_options]
if preselect_step not in _step_keys:
    preselect_step = ""

with st.container(border=True):
    fc1, fc2 = st.columns(2)
    with fc1:
        doc_type = st.selectbox(
            "Document type (optional)",
            options=_doc_type_keys,
            format_func=lambda k: _DOC_TYPE_LABELS.get(k, k),
            index=_doc_type_keys.index(preselect_type),
            key="upload_doc_type",
            help=(
                "Helps the field extractor pull the right structured "
                "data. Leave blank to upload a generic document."
            ),
        )
    with fc2:
        related_step = st.selectbox(
            "Related route step (optional)",
            options=_step_keys,
            format_func=lambda k: dict(_step_options).get(k, k),
            index=_step_keys.index(preselect_step),
            key="upload_related_step",
            help=(
                "Linking to a step lets the Route Plan know this "
                "document supports it (still doesn't gate completion)."
            ),
        )

    uploaded_file = st.file_uploader(
        "Upload PDF or image",
        type=["pdf", "png", "jpg", "jpeg"],
        key="vault_uploader",
    )

    if uploaded_file is not None:
        # Run only once per (filename, size) pair.
        signature = (
            f"{uploaded_file.name}:{uploaded_file.size}:"
            f"{related_step}:{doc_type}"
        )
        if st.session_state.get("_vault_processed") != signature:
            with st.spinner(
                f"Reading {uploaded_file.name} and running OCR…"
            ):
                # If no step is selected, persist under a sentinel key
                # so the row isn't dropped. Most downstream readers
                # treat empty step_key as "unattached".
                step_key_to_save = related_step or "unattached"
                # If no document type selected, fall back to a generic
                # type so the verifier doesn't crash on a missing
                # extractor.
                doc_type_to_save = doc_type or "academic_document"

                outcome = save_uploaded_document(
                    profile_id=profile_id, user_id=uid,
                    step_key=step_key_to_save,
                    document_type=doc_type_to_save,
                    country=country,
                    original_filename=uploaded_file.name,
                    file_bytes=uploaded_file.getvalue(),
                    mime_type=getattr(uploaded_file, "type", None),
                    profile=profile,
                )
            if not outcome["ok"]:
                st.error(outcome.get("error") or "Upload failed.")
            else:
                st.session_state["_vault_processed"] = signature
                friendly = _friendly_status(outcome["verification_status"])
                st.success(
                    f"✅ Uploaded **{uploaded_file.name}** — "
                    f"OCR `{outcome['extraction_status']}`, "
                    f"status **{friendly}** "
                    "_(informational; does not gate steps)_."
                )
                st.rerun()



st.markdown("""
<style>
/* Document vault polish */
.vf-vault-title {
    display:flex;
    align-items:center;
    gap:14px;
    margin: 34px 0 18px 0;
}

.vf-vault-title h2 {
    margin:0 !important;
    font-size:34px !important;
    font-weight:950 !important;
    letter-spacing:-.04em !important;
}

.vf-doc-name {
    display:flex;
    align-items:center;
    gap:16px;
    margin-bottom:18px;
}

.vf-doc-file-icon {
    width:56px;
    height:56px;
    border-radius:16px;
    display:grid;
    place-items:center;
    background:linear-gradient(135deg,#eef2ff,#f8fafc);
    border:1px solid #e0e7ff;
    font-size:28px;
    box-shadow:0 12px 28px rgba(79,70,229,.08);
}

.vf-doc-name h3 {
    margin:0 !important;
    font-size:32px !important;
    font-weight:950 !important;
    letter-spacing:-.04em !important;
    color:#0f172a !important;
}

.vf-doc-meta {
    display:flex;
    flex-wrap:wrap;
    gap:10px;
    margin:12px 0 18px 0;
}

.vf-doc-meta span {
    padding:8px 13px;
    border-radius:999px;
    background:#f8fafc;
    border:1px solid #e2e8f0;
    color:#475569;
    font-size:13px;
    font-weight:750;
}

.vf-review-note {
    border-radius:18px;
    padding:18px 20px;
    background:linear-gradient(135deg,#fff7ed,#eff6ff);
    border:1px solid #fed7aa;
    color:#92400e;
    font-weight:750;
    line-height:1.65;
    margin:18px 0;
}

div[data-testid="stExpander"] {
    border-radius:16px !important;
    border:1px solid #e2e8f0 !important;
    background:#ffffff !important;
    box-shadow:0 8px 22px rgba(15,23,42,.035) !important;
}

div[data-testid="stExpander"] summary {
    font-weight:800 !important;
    color:#0f172a !important;
}




</style>
""", unsafe_allow_html=True)



st.markdown("""
<style>
.vf-doc-card-title {
    display:flex;
    align-items:center;
    gap:16px;
    margin-bottom:16px;
}

.vf-doc-card-icon {
    width:58px;
    height:58px;
    border-radius:18px;
    display:grid;
    place-items:center;
    background:linear-gradient(135deg,#eef2ff,#ffffff);
    border:1px solid #dbeafe;
    font-size:30px;
    box-shadow:0 14px 32px rgba(37,99,235,.08);
}

.vf-doc-card-title h3 {
    margin:0 !important;
    font-size:34px !important;
    line-height:1.1 !important;
    font-weight:950 !important;
    letter-spacing:-.04em !important;
    color:#0f172a !important;
}

.vf-doc-meta-row {
    display:flex;
    flex-wrap:wrap;
    gap:10px;
    margin:10px 0 18px 0;
}

.vf-doc-meta-row span {
    padding:8px 13px;
    border-radius:999px;
    background:#f8fafc;
    border:1px solid #e2e8f0;
    color:#475569;
    font-size:13px;
    font-weight:750;
}

.vf-review-warning {
    margin:18px 0;
    padding:18px 20px;
    border-radius:18px;
    border:1px solid #fed7aa;
    background:linear-gradient(135deg,#fff7ed,#eff6ff);
    color:#92400e;
    font-weight:750;
    line-height:1.65;
}

.vf-review-warning strong {
    color:#9a3412;
}

div[data-testid="stExpander"] {
    border-radius:16px !important;
    border:1px solid #dbeafe !important;
    background:#ffffff !important;
    box-shadow:0 8px 22px rgba(15,23,42,.035) !important;
}

div[data-testid="stExpander"] summary {
    font-weight:850 !important;
}


</style>
""", unsafe_allow_html=True)



st.markdown("""
<style>

/* Cleaner document dropdowns / expanders */
div[data-testid="stExpander"] {
    border-radius: 18px !important;
    border: 1px solid #dbeafe !important;
    background: linear-gradient(135deg,#ffffff,#f8fbff) !important;
    box-shadow: 0 10px 26px rgba(15,23,42,.045) !important;
    margin-bottom: 12px !important;
    overflow: hidden !important;
}

div[data-testid="stExpander"] summary {
    min-height: 56px !important;
    padding: 0 16px !important;
    font-size: 16px !important;
    font-weight: 850 !important;
    color: #0f172a !important;
}

div[data-testid="stExpander"]:hover {
    border-color: #93c5fd !important;
    box-shadow: 0 14px 34px rgba(37,99,235,.08) !important;
}

/* Document action buttons */




/* Footer page links */
div[data-testid="stPageLink"] a {
    min-height: 54px !important;
    border-radius: 18px !important;
    border: 1px solid #bfdbfe !important;
    background: linear-gradient(135deg,#ffffff,#eff6ff) !important;
    box-shadow: 0 12px 30px rgba(37,99,235,.08) !important;
    font-weight: 850 !important;
    padding: 14px 20px !important;
    text-decoration: none !important;
}

div[data-testid="stPageLink"] a:hover {
    transform: translateY(-2px);
    border-color: #60a5fa !important;
    box-shadow: 0 18px 38px rgba(37,99,235,.14) !important;
}

</style>
""", unsafe_allow_html=True)


# ---------- Documents on file -------------------------------------------

st.markdown("### 📚 Your documents")

# Refresh after the upload may have inserted a row.
all_evidence = list_evidence_for_profile(profile_id)

if not all_evidence:
    st.info(
        "No documents uploaded yet. Use the form above to add your "
        "first one. You can always upload from the Route Plan by "
        "clicking _Upload related document_ on a step."
    )
else:
    # Build a {step_key: step_title} lookup so each card can show
    # which step a doc supports.
    step_titles: dict[str, str] = {}
    if _route_plan:
        for sec in _route_plan.sections:
            for step in sec.steps:
                step_titles[step.key] = step.title

    for ev in all_evidence:
        with st.container(border=True):
            head_l, head_r = st.columns([3, 1])
            with head_l:
                st.markdown(
                    f"""
<div class="vf-doc-card-title">
    <div class="vf-doc-card-icon">&#128196;</div>
    <h3>{ev.original_filename or '(unnamed)'}</h3>
</div>
""",
                    unsafe_allow_html=True,
                )
                meta = []
                if ev.document_type:
                    label = _DOC_TYPE_LABELS.get(
                        ev.document_type, ev.document_type
                    )
                    meta.append(f"**Type:** {label}")
                if ev.step_key and ev.step_key != "unattached":
                    title = step_titles.get(ev.step_key, ev.step_key)
                    meta.append(f"**Linked step:** {title}")
                if ev.uploaded_at:
                    meta.append(
                        "**Uploaded:** "
                        + ev.uploaded_at.strftime('%Y-%m-%d %H:%M')
                    )
                st.markdown(" · ".join(meta))
            with head_r:
                st.markdown(
                    _verif_pill(ev.verification_status),
                    unsafe_allow_html=True,
                )

            # v0.17 spec §12: OCR engine + quality badge
            ocr_method = ev.extraction_method or ""
            ocr_label = getattr(ev, "ocr_quality_label", None)
            ocr_score = getattr(ev, "ocr_quality_score", None)

            meta_row = []
            if ocr_method:
                meta_row.append(f"OCR engine: `{ocr_method}`")
            if ev.extraction_status:
                meta_row.append(f"status: `{ev.extraction_status}`")
            if ev.file_size:
                meta_row.append(f"{ev.file_size / 1024:.1f} KB")

            badge_html = _ocr_quality_badge(ocr_label, ocr_score)
            if meta_row or badge_html:
                cols = st.columns([3, 1])
                with cols[0]:
                    st.caption(" · ".join(meta_row) if meta_row else "")
                with cols[1]:
                    if badge_html:
                        st.markdown(badge_html, unsafe_allow_html=True)

            # v0.17 spec §12: advisory messages based on status
            if ev.verification_status in (
                "needs_review", "manual_review_required", "needs_attention",
            ):
                st.info(
                    "🟡 **Needs review.** This document was read, but some "
                    "details need manual review. Use the extracted fields "
                    "and text preview below to check, then click "
                    "_I reviewed this document_ to acknowledge."
                )
            elif ocr_label == "weak":
                st.warning(
                    "🔴 **OCR quality is weak.** Try uploading a clearer "
                    "scan or photo, or a text-based PDF, for better "
                    "results."
                )
            elif ev.verification_status == "extraction_failed":
                st.error(
                    "❌ **Couldn't read this document.** VisaForge could "
                    "not extract text. Try a clearer scan or a text-based "
                    "PDF, then click **Reprocess OCR**."
                )

            # Verification hints (warnings, never gates — spec §6)
            if ev.issues:
                with st.expander(f"⚠️ Issues ({len(ev.issues)})"):
                    for issue in ev.issues:
                        st.markdown(f"- {issue}")
            if ev.warnings:
                with st.expander(f"💬 Warnings ({len(ev.warnings)})"):
                    for w in ev.warnings:
                        st.markdown(f"- {w}")
            if ev.matched_fields:
                st.caption(
                    "✅ Matched fields: " + ", ".join(ev.matched_fields)
                )

            # Extracted structured fields
            if ev.extracted_fields:
                with st.expander("📋 Extracted fields"):
                    for k, v in ev.extracted_fields.items():
                        st.markdown(f"- **{k}**: {v}")

            # Extracted text preview (spec §12 + §16)
            if ev.extracted_text:
                with st.expander("📄 Extracted text preview"):
                    st.code(
                        ev.extracted_text[:1500] or "(empty)",
                        language="text",
                    )
                    if len(ev.extracted_text) > 1500:
                        st.caption(
                            f"_…showing 1500 of "
                            f"{len(ev.extracted_text)} stored "
                            "characters._"
                        )

            # Action buttons
            a1, a2, a3, a4 = st.columns(4)
            with a1:
                # Re-upload — same step, prompt user to upload again
                if st.button(
                    "🔄 Re-upload",
                    key=f"reupload_{ev.id}",
                    use_container_width=True,
                ):
                    # Stash the step context so the Documents form at
                    # top of page pre-fills correctly, and clear the
                    # one-shot processed marker so a new upload runs.
                    st.session_state["doc_step_context"] = {
                        "step_key": ev.step_key or "",
                        "step_title": step_titles.get(
                            ev.step_key, ev.step_key or ""
                        ),
                        "suggested_document_types": [{
                            "document_type": ev.document_type,
                            "label": _DOC_TYPE_LABELS.get(
                                ev.document_type or "",
                                ev.document_type or "",
                            ),
                            "optional": False,
                        }] if ev.document_type else [],
                    }
                    st.session_state.pop("_vault_processed", None)
                    st.rerun()

            with a2:
                if st.button(
                    "🔧 Reprocess OCR",
                    key=f"reproc_{ev.id}",
                    use_container_width=True,
                ):
                    with st.spinner("Re-extracting and re-verifying…"):
                        out = reprocess_document(ev.id, profile)
                    if out.get("ok"):
                        st.success(
                            "Reprocessed — extraction "
                            f"`{out['extraction_status']}`."
                        )
                        st.rerun()
                    else:
                        st.error(
                            out.get("error") or "Reprocess failed."
                        )

            with a3:
                if st.button(
                    "🤖 Ask AI",
                    key=f"ai_{ev.id}",
                    use_container_width=True,
                ):
                    # v0.15 spec §7: "Ask AI about this document"
                    # uses kind="document" so the AI prompt is
                    # focused on document content (not step semantics)
                    # and explicitly tells the model not to claim
                    # authenticity / validity.
                    st.session_state["ai_step_context"] = (
                        RouteStepContext(
                            profile_id=profile_id,
                            step_key=ev.step_key or "",
                            kind="document",
                            document_id=ev.id,
                        )
                    )
                    st.switch_page("pages/6_AI_Assistant.py")

            with a4:
                if st.button(
                    "🗑 Delete",
                    key=f"del_{ev.id}",
                    use_container_width=True,
                ):
                    if delete_document(ev.id):
                        st.success(
                            f"Deleted: {ev.original_filename}"
                        )
                        st.rerun()
                    else:
                        st.error("Could not delete.")

            # v0.16 spec §8 — "I reviewed this document" self-review.
            # Available for any non-extraction-failed document. When
            # the doc is already user_confirmed, show a passive
            # acknowledgement with a remove-confirmation option (re-
            # uploading or reprocessing OCR clears it automatically).
            already_reviewed = bool(getattr(ev, "confirmed_by_user", False))
            review_eligible = (
                ev.verification_status != "extraction_failed"
            )

            if already_reviewed:
                st.markdown(
                    "<div style='margin-top:6px;padding:8px 12px;"
                    "border-radius:6px;background:#dbeafe;color:#1d4ed8;"
                    "font-size:0.82rem;'>"
                    "👤 <strong>You reviewed this document.</strong> "
                    "VisaForge has not independently verified it."
                    "</div>",
                    unsafe_allow_html=True,
                )
                if note := getattr(ev, "confirmation_note", None):
                    st.caption(f"Your note: _{note}_")
            elif review_eligible:
                # Collapsed review panel — opens a small note field
                # under a "I reviewed this document" expander so the
                # main action row stays compact.
                with st.expander(
                    "👤 I reviewed this document", expanded=False,
                ):
                    st.caption(
                        "Use this only if you've eyeballed the "
                        "extracted text and confirmed the document is "
                        "what you intended to upload. This is **not** "
                        "the same as automated verification — "
                        "VisaForge will mark the document as "
                        "_Processed (you reviewed)_ but the disclaimer "
                        "still applies."
                    )
                    note_value = st.text_input(
                        "Optional note (e.g. 'translated copy', "
                        "'original on file at home')",
                        key=f"review_note_{ev.id}",
                        max_chars=300,
                    )
                    if st.button(
                        "Confirm I reviewed it",
                        key=f"review_btn_{ev.id}",
                        type="primary",
                    ):
                        ok = confirm_document_manually(
                            ev.id, note=note_value or None,
                        )
                        if ok:
                            st.success(
                                "Recorded. Status updated to "
                                "_Processed (you reviewed)_."
                            )
                            st.rerun()
                        else:
                            st.error(
                                "Could not record review — the "
                                "document may have moved to a "
                                "definitive verifier outcome since "
                                "you opened this panel."
                            )


# ---------- Footer ------------------------------------------------------

st.divider()
nav_l, nav_r = st.columns(2)
with nav_l:
    st.page_link(
        "pages/3_Route_Plan.py",
        label="← Back to Route Plan", icon="🗺️",
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

