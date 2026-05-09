"""Page 1 — Passport Profile intake form (v0.2)."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from components.ui import (
    disclaimer,
    page_header,
    render_sidebar,
    require_stage,
    require_user,
)
from config.settings import settings
from models.schemas import ProfileIn
from services.auth_service import current_user_id
from services.profile_service import (
    create_or_update_profile,
    get_profile,
    list_profiles_for_user,
)
try:
    from services.scholarship_service import get_selected_scholarship
except Exception:
    get_selected_scholarship = None

try:
    from services.document_service import list_evidence_for_profile
except Exception:
    list_evidence_for_profile = None

try:
    from services.eligibility_service import latest_report
except Exception:
    latest_report = None

from utils.reference_data import (
    FUNDS_STATUS_OPTIONS,
    OFFER_STATUS_OPTIONS,
    STUDY_FIELDS,
    TARGET_INTAKE_OPTIONS,
    country_names,
    nationality_options,
    normalize_fields,
    safe_index,
)

st.set_page_config(page_title="Profile · VisaForge", page_icon="👤", layout="wide")
render_sidebar()
require_user()
require_stage('profile')


st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(99,102,241,.08), transparent 34%),
        linear-gradient(180deg,#fbfcff 0%,#ffffff 42%,#fbfbff 100%);
}

.block-container {
    max-width: 1180px;
    padding-top: 1.6rem;
    padding-bottom: 3rem;
}

hr {
    margin: 1.4rem 0 1.2rem 0;
    border-color: #eef2f7;
}

div[data-testid="stExpander"] {
    border-radius: 16px !important;
    border: 1px solid #e5e7eb !important;
    background: rgba(255,255,255,.92) !important;
    box-shadow: 0 10px 26px rgba(15,23,42,.04) !important;
}

div[data-testid="stAlert"] {
    border-radius: 16px !important;
}

div[data-testid="stForm"] {
    border: 1px solid #e5e7eb;
    border-radius: 24px;
    padding: 26px 28px 30px 28px;
    background: rgba(255,255,255,.94);
    box-shadow: 0 20px 50px rgba(15,23,42,.065);
}

div[data-testid="stForm"] h4 {
    margin-top: 24px;
    margin-bottom: 14px;
    padding: 14px 16px;
    border-radius: 16px;
    background: linear-gradient(135deg,#eef2ff,#ffffff);
    border: 1px solid #e0e7ff;
    color: #111827;
    font-size: 20px;
    font-weight: 950;
    letter-spacing: -.25px;
}

div[data-testid="stForm"] h4:first-of-type {
    margin-top: 0;
}

label {
    font-weight: 750 !important;
    color: #334155 !important;
}

div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stDateInput"] input,
div[data-baseweb="select"] > div,
textarea {
    border-radius: 13px !important;
    background: #f8fafc !important;
    border: 1px solid #e5e7eb !important;
}

div[data-testid="stTextInput"] input:focus,
div[data-testid="stNumberInput"] input:focus,
div[data-testid="stDateInput"] input:focus,
textarea:focus {
    border-color: #93c5fd !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,.10) !important;
}

div[data-testid="stTextArea"] textarea {
    min-height: 92px;
}

button[kind="primary"] {
    border-radius: 14px !important;
    padding: 0.65rem 1.15rem !important;
    font-weight: 900 !important;
    background: linear-gradient(135deg,#2563eb,#4f46e5) !important;
    box-shadow: 0 14px 30px rgba(37,99,235,.20) !important;
}

button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 18px 34px rgba(37,99,235,.26) !important;
}

.vf-profile-hero {
    border-radius: 24px;
    padding: 28px 30px;
    margin: 8px 0 22px 0;
    color: white;
    background:
        radial-gradient(circle at 88% 16%, rgba(255,255,255,.22), transparent 7%),
        linear-gradient(135deg,#2157f3 0%,#2563eb 42%,#16b8b0 100%);
    box-shadow: 0 24px 70px rgba(37,99,235,.20);
    position: relative;
    overflow: hidden;
}

.vf-profile-hero:after {
    content: "";
    position: absolute;
    right: -80px;
    top: -70px;
    width: 460px;
    height: 250px;
    background: repeating-radial-gradient(ellipse at center, rgba(255,255,255,.12) 0 1px, transparent 2px 18px);
    opacity: .45;
    transform: rotate(-10deg);
}

.vf-profile-hero h2 {
    position: relative;
    z-index: 1;
    margin: 0 0 10px 0;
    font-size: 30px;
    font-weight: 950;
    letter-spacing: -.6px;
}

.vf-profile-hero p {
    position: relative;
    z-index: 1;
    margin: 0;
    max-width: 760px;
    font-size: 14px;
    line-height: 1.6;
    font-weight: 650;
    opacity: .95;
}

.vf-profile-hint {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin-bottom: 18px;
}

.vf-profile-hint-card {
    border-radius: 18px;
    padding: 16px 18px;
    background: rgba(255,255,255,.9);
    border: 1px solid #e5e7eb;
    box-shadow: 0 14px 34px rgba(15,23,42,.045);
}

.vf-profile-hint-card b {
    display: block;
    color: #111827;
    font-size: 14px;
    margin-bottom: 5px;
}

.vf-profile-hint-card span {
    color: #64748b;
    font-size: 12px;
    font-weight: 650;
}

@media(max-width: 900px) {
    .vf-profile-hint {
        grid-template-columns: 1fr;
    }
}

.vf-profile-completion-card {
    border-radius:18px;
    padding:20px 22px;
    margin:18px 0;
    background:linear-gradient(135deg,#ffffff,#f8fafc);
    border:1px solid #e5e7eb;
    box-shadow:0 14px 34px rgba(15,23,42,.045);
}

.vf-profile-completion-head {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:18px;
    margin-bottom:14px;
}

.vf-profile-completion-head b {
    display:block;
    color:#111827;
    font-size:18px;
    font-weight:950;
}

.vf-profile-completion-head span {
    color:#64748b;
    font-size:13px;
    font-weight:650;
}

.vf-profile-completion-head strong {
    color:#2563eb;
    font-size:28px;
    font-weight:950;
}

.vf-profile-completion-bar {
    height:10px;
    border-radius:999px;
    background:#e5e7eb;
    overflow:hidden;
}

.vf-profile-completion-bar div {
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg,#2563eb,#14b8a6);
}

.vf-profile-summary-grid {
    display:none;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:14px;
    margin:18px 0 18px 0;
}

.vf-profile-summary-card {
    border-radius:18px;
    padding:18px 20px;
    background:rgba(255,255,255,.92);
    border:1px solid #e5e7eb;
    box-shadow:0 14px 34px rgba(15,23,42,.045);
}

.vf-profile-summary-card span {
    display:block;
    color:#64748b;
    font-size:12px;
    font-weight:850;
    margin-bottom:8px;
}

.vf-profile-summary-card b {
    display:block;
    color:#111827;
    font-size:22px;
    font-weight:950;
    line-height:1.1;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
}

.vf-profile-summary-card small {
    display:inline-flex;
    margin-top:10px;
    padding:5px 9px;
    border-radius:999px;
    background:#eef2ff;
    color:#3730a3;
    font-size:11px;
    font-weight:850;
}

.vf-profile-summary-card.purple {border-color:#ddd6fe;background:linear-gradient(135deg,#ffffff,#faf5ff);}
.vf-profile-summary-card.green {border-color:#bbf7d0;background:linear-gradient(135deg,#ffffff,#f0fdf4);}
.vf-profile-summary-card.orange {border-color:#fed7aa;background:linear-gradient(135deg,#ffffff,#fff7ed);}
.vf-profile-summary-card.blue {border-color:#bfdbfe;background:linear-gradient(135deg,#ffffff,#eff6ff);}

div[data-testid="stExpander"] {
    border-radius:18px !important;
    border:1px solid #e5e7eb !important;
    background:rgba(255,255,255,.94) !important;
    box-shadow:0 12px 28px rgba(15,23,42,.045) !important;
    margin-bottom:14px !important;
}

div[data-testid="stExpander"] details summary {
    font-weight:950 !important;
    color:#111827 !important;
    font-size:17px !important;
}

.vf-section-progress {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin:0 0 12px 0;
}

.vf-section-progress span {
    color:#64748b;
    font-size:12px;
    font-weight:750;
}

.vf-section-progress b {
    color:#2563eb;
    font-size:12px;
    font-weight:950;
}

@media(max-width: 900px) {
    .vf-profile-completion-card {
    border-radius:18px;
    padding:20px 22px;
    margin:18px 0;
    background:linear-gradient(135deg,#ffffff,#f8fafc);
    border:1px solid #e5e7eb;
    box-shadow:0 14px 34px rgba(15,23,42,.045);
}

.vf-profile-completion-head {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:18px;
    margin-bottom:14px;
}

.vf-profile-completion-head b {
    display:block;
    color:#111827;
    font-size:18px;
    font-weight:950;
}

.vf-profile-completion-head span {
    color:#64748b;
    font-size:13px;
    font-weight:650;
}

.vf-profile-completion-head strong {
    color:#2563eb;
    font-size:28px;
    font-weight:950;
}

.vf-profile-completion-bar {
    height:10px;
    border-radius:999px;
    background:#e5e7eb;
    overflow:hidden;
}

.vf-profile-completion-bar div {
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg,#2563eb,#14b8a6);
}

.vf-profile-summary-grid {
        grid-template-columns:1fr 1fr;
    }
}

@media(max-width: 640px) {
    .vf-profile-completion-card {
    border-radius:18px;
    padding:20px 22px;
    margin:18px 0;
    background:linear-gradient(135deg,#ffffff,#f8fafc);
    border:1px solid #e5e7eb;
    box-shadow:0 14px 34px rgba(15,23,42,.045);
}

.vf-profile-completion-head {
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:18px;
    margin-bottom:14px;
}

.vf-profile-completion-head b {
    display:block;
    color:#111827;
    font-size:18px;
    font-weight:950;
}

.vf-profile-completion-head span {
    color:#64748b;
    font-size:13px;
    font-weight:650;
}

.vf-profile-completion-head strong {
    color:#2563eb;
    font-size:28px;
    font-weight:950;
}

.vf-profile-completion-bar {
    height:10px;
    border-radius:999px;
    background:#e5e7eb;
    overflow:hidden;
}

.vf-profile-completion-bar div {
    height:100%;
    border-radius:999px;
    background:linear-gradient(90deg,#2563eb,#14b8a6);
}

.vf-profile-summary-grid {
        grid-template-columns:1fr;
    }
}


.vf-save-panel {
    margin-top:18px;
    padding:18px 20px;
    border-radius:18px;
    background:linear-gradient(135deg,#eff6ff,#ffffff);
    border:1px solid #bfdbfe;
    box-shadow:0 12px 28px rgba(37,99,235,.06);
}

.vf-save-panel b {
    display:block;
    color:#111827;
    font-size:17px;
    font-weight:950;
    margin-bottom:4px;
}

.vf-save-panel span {
    color:#64748b;
    font-size:13px;
    font-weight:650;
}


div[data-testid="stExpander"] {
    overflow:hidden !important;
}

div[data-testid="stExpander"] summary {
    background:linear-gradient(135deg,#ffffff,#f8fafc) !important;
    border-radius:16px !important;
    padding:14px 16px !important;
}

div[data-testid="stExpander"] summary:hover {
    background:#f1f5f9 !important;
}

div[data-testid="stExpander"] summary p {
    font-weight:850 !important;
    color:#0f172a !important;
}

div[data-testid="stAlert"] {
    border-radius:18px !important;
    border:1px solid #bbf7d0 !important;
    background:linear-gradient(135deg,#ecfdf5,#ffffff) !important;
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="vf-profile-hero">
    <h2>Passport Profile</h2>
    <p>Complete your applicant details. Your answers power eligibility checks, scholarship matching, route planning, and grounded AI guidance.</p>
</div>

<div class="vf-profile-hint">
    <div class="vf-profile-hint-card">
        <b>Identity & passport</b>
        <span>Name, nationality, residence, passport validity, and travel history.</span>
    </div>
    <div class="vf-profile-hint-card">
        <b>Academic background</b>
        <span>Education level, GPA, language test, study field, and target degree.</span>
    </div>
    <div class="vf-profile-hint-card">
        <b>Evidence readiness</b>
        <span>Offer letter, proof of funds, dependents, budget notes, and supporting context.</span>
    </div>
</div>
""", unsafe_allow_html=True)


# --- Load-for-edit selector -----------------------------------------------
profiles = list_profiles_for_user(current_user_id())
if profiles:
    with st.expander("Existing profiles", expanded=False):
        options = {"— Create a new profile —": None}
        for p in profiles:
            options[f"{p.full_name} ({p.destination_country}) · id={p.id}"] = p.id
        chosen_key = st.selectbox("Load an existing profile",
                                  list(options.keys()))
        if options[chosen_key] is not None and st.button("Load", type="primary"):
            st.session_state["profile_id"] = options[chosen_key]
            st.rerun()

loaded_id = st.session_state.get("profile_id")
loaded = get_profile(loaded_id) if loaded_id else None
if loaded:
    st.success(f"Editing profile #{loaded.id}: **{loaded.full_name}**")


def _val(attr, default=None):
    return getattr(loaded, attr, default) if loaded else default


def _filled(value) -> bool:
    return value not in (None, "", [])


def _section_score(values: list) -> int:
    if not values:
        return 0
    return round(sum(1 for v in values if _filled(v)) / len(values) * 100)


identity_score = _section_score([
    _val("full_name"),
    _val("age"),
    _val("nationality"),
    _val("country_of_residence"),
    _val("passport_valid_until"),
])

education_score = _section_score([
    _val("education_level"),
    _val("gpa"),
    _val("english_test_type"),
    _val("english_test_score"),
    _val("previous_field_of_study"),
])

destination_score = _section_score([
    _val("destination_country"),
    _val("intended_degree_level"),
    _val("intended_institution_type"),
    _val("field_of_study"),
    _val("target_intake"),
])

evidence_score = _section_score([
    _val("offer_letter_status"),
    _val("proof_of_funds_status"),
])

budget_score = _section_score([
    _val("budget_notes"),
    _val("notes"),
])

profile_complete_score = round(
    (identity_score + education_score + destination_score) / 3
)
st.session_state["_current_page_path"] = "pages/1_Profile.py"


selected_scholarship = None
if loaded_id and get_selected_scholarship:
    try:
        selected_scholarship = get_selected_scholarship(loaded_id)
    except Exception:
        selected_scholarship = None

doc_count = 0
if loaded_id and list_evidence_for_profile:
    try:
        doc_count = len(list_evidence_for_profile(loaded_id))
    except Exception:
        doc_count = 0

eligibility_status = "Not run"
if loaded_id and latest_report:
    try:
        er = latest_report(loaded_id)
        if er:
            eligibility_status = (getattr(er, "status", None) or "Not run").replace("_", " ").title()
    except Exception:
        eligibility_status = "Not run"


def _status_chip(score: int) -> str:
    if score >= 90:
        return "Complete"
    if score >= 60:
        return "In progress"
    return "Needs work"


st.markdown(
    f"""
<div class="vf-profile-completion-card">
    <div class="vf-profile-completion-head">
        <div>
            <b>Profile completion</b>
            <span>Complete your details to unlock stronger eligibility and route guidance.</span>
        </div>
        <strong>{profile_complete_score}%</strong>
    </div>
    <div class="vf-profile-completion-bar">
        <div style="width:{profile_complete_score}%;"></div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)


# --- Reference-data option lists ------------------------------------------
NATIONALITIES = nationality_options()
COUNTRIES = country_names()

EDUCATION_LEVELS = ["", "High school", "Bachelor's", "Master's", "PhD", "Other"]
ENGLISH_TESTS = ["", "IELTS", "IELTS UKVI", "TOEFL", "PTE", "Duolingo",
                 "Other", "None"]
DEGREE_LEVELS = ["", "Bachelor's", "Master's", "PhD", "Diploma", "Other"]
INSTITUTION_TYPES = ["", "University", "College", "Polytechnic",
                     "Research institute"]
PREVIOUS_FIELDS = [""] + STUDY_FIELDS  # allow "not specified" as first entry


# --- Passport date default -------------------------------------------------
def _parse_passport(value: str | None) -> date:
    """Parse stored YYYY-MM-DD string; if invalid/missing, pick a sensible default."""
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            pass
    # Default: 5 years from today, which is a typical adult-passport validity.
    return date.today() + timedelta(days=365 * 5)


# --- Form ------------------------------------------------------------------
with st.form("profile_form", clear_on_submit=False):

    # ========== Personal information ==========
    with st.expander("Personal information", expanded=True):
        st.markdown(f"""<div class="vf-section-progress"><span>Section progress</span><b>{identity_score}% · {_status_chip(identity_score)}</b></div>""", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        full_name = c1.text_input("Full name *", value=_val("full_name", ""))
        age = c2.number_input(
            "Age", min_value=15, max_value=80,
            value=int(_val("age") or 22), step=1,
        )
        nationality = c3.selectbox(
            "Nationality *",
            NATIONALITIES,
            index=safe_index(
                NATIONALITIES,
                _val("nationality") or "Pakistani",
                default=safe_index(NATIONALITIES, "Pakistani"),
            ),
            help="Your passport nationality.",
        )

        c4, c5 = st.columns(2)
        country_of_residence = c4.selectbox(
            "Country of residence *",
            COUNTRIES,
            index=safe_index(
                COUNTRIES,
                _val("country_of_residence") or "Pakistan",
                default=safe_index(COUNTRIES, "Pakistan"),
            ),
            help="Where you currently live.",
        )
        passport_valid_until_date = c5.date_input(
            "Passport valid until *",
            value=_parse_passport(_val("passport_valid_until")),
            min_value=date.today() - timedelta(days=365),
            max_value=date.today() + timedelta(days=365 * 15),
            help="Your passport expiry date. Stored as YYYY-MM-DD.",
        )

        previous_travel_history = st.text_input(
            "Previous travel history (brief)",
            value=_val("previous_travel_history", "") or "",
            placeholder="e.g. Schengen 2023, UK 2022, UAE 2024",
            help="A quick summary of prior international travel, if any.",
        )

    # ========== Education ==========
    with st.expander("Personal information", expanded=False):
        st.markdown(f"""<div class="vf-section-progress"><span>Section progress</span><b>{education_score}% · {_status_chip(education_score)}</b></div>""", unsafe_allow_html=True)
        c7, c8, c9 = st.columns(3)
        education_level = c7.selectbox(
            "Highest education *",
            EDUCATION_LEVELS,
            index=safe_index(EDUCATION_LEVELS, _val("education_level") or ""),
        )
        gpa = c8.number_input(
            "GPA / grade (0–4.0 scale)",
            min_value=0.0, max_value=4.0,
            value=float(_val("gpa") or 0.0), step=0.1,
            help="Convert to a 4.0 scale if needed. Leave 0 if unsure.",
        )
        previous_field_of_study = c9.selectbox(
            "Previous field of study",
            PREVIOUS_FIELDS,
            index=safe_index(
                PREVIOUS_FIELDS,
                _val("previous_field_of_study") or "",
            ),
            help="What you studied previously (your most recent qualification).",
        )

        c10, c11 = st.columns(2)
        english_test_type = c10.selectbox(
            "English language test",
            ENGLISH_TESTS,
            index=safe_index(ENGLISH_TESTS, _val("english_test_type") or ""),
        )
        english_test_score = c11.number_input(
            "English test score",
            min_value=0.0, max_value=120.0,
            value=float(_val("english_test_score") or 0.0),
            step=0.5,
            help=("IELTS overall band (0""9) or TOEFL iBT score (0""120). "
                  "Leave 0 if not taken yet."),
        )

    # ========== Destination & intent ==========
    with st.expander("Education", expanded=False):
        st.markdown(f"""<div class="vf-section-progress"><span>Section progress</span><b>{destination_score}% · {_status_chip(destination_score)}</b></div>""", unsafe_allow_html=True)
        c12, c13, c14 = st.columns(3)
        destination_country = c12.selectbox(
            "Destination country *",
            list(settings.SUPPORTED_COUNTRIES),
            index=safe_index(
                list(settings.SUPPORTED_COUNTRIES),
                _val("destination_country") or "UK",
            ),
        )
        intended_degree_level = c13.selectbox(
            "Intended degree level",
            DEGREE_LEVELS,
            index=safe_index(DEGREE_LEVELS, _val("intended_degree_level") or ""),
        )
        intended_institution_type = c14.selectbox(
            "Intended institution type",
            INSTITUTION_TYPES,
            index=safe_index(
                INSTITUTION_TYPES,
                _val("intended_institution_type") or "",
            ),
        )

        # Intended field(s) of study — multiselect
        current_fields = normalize_fields(_val("field_of_study"))
        field_of_study_list = st.multiselect(
            "Intended field(s) of study",
            STUDY_FIELDS,
            default=[f for f in current_fields if f in STUDY_FIELDS],
            help="Select one or more subject areas you intend to pursue.",
        )

        target_intake = st.selectbox(
            "Target intake / semester",
            TARGET_INTAKE_OPTIONS,
            index=safe_index(
                TARGET_INTAKE_OPTIONS,
                _val("target_intake") or "September 2026",
            ),
        )

    # ========== Evidence status ==========
    with st.expander("Destination & intent", expanded=False):
        st.markdown(f"""<div class="vf-section-progress"><span>Section progress</span><b>{evidence_score}% · {_status_chip(evidence_score)}</b></div>""", unsafe_allow_html=True)
        st.caption(
            "Be honest about where you are. The eligibility engine weights these "
            "carefully — a tick is no longer enough."
        )
        c15, c16, c17 = st.columns(3)
        offer_letter_status = c15.selectbox(
            "Offer / admission letter status",
            OFFER_STATUS_OPTIONS,
            index=safe_index(
                OFFER_STATUS_OPTIONS,
                _val("offer_letter_status")
                or ("Unconditional offer received"
                    if _val("has_offer_letter") else "Not yet applied"),
            ),
            help=(
                "Unconditional = strong evidence · Conditional = partial · "
                "Applied/waiting/not yet = insufficient."
            ),
        )
        proof_of_funds_status = c16.selectbox(
            "Proof of funds status",
            FUNDS_STATUS_OPTIONS,
            index=safe_index(
                FUNDS_STATUS_OPTIONS,
                _val("proof_of_funds_status")
                or ("Fully prepared"
                    if _val("has_proof_of_funds") else "Not prepared"),
            ),
            help=(
                "Fully prepared or Sponsored = strong · Partially prepared = "
                "partial · Not prepared / Not sure = insufficient."
            ),
        )
        has_dependents = c17.checkbox(
            "Travelling with dependents?",
            value=bool(_val("has_dependents", False)),
        )

    # ========== Budget & notes ==========
    with st.expander("Evidence status", expanded=False):
        st.markdown(f"""<div class="vf-section-progress"><span>Section progress</span><b>Optional section · Helps improve AI guidance and planning</b></div>""", unsafe_allow_html=True)
        budget_notes = st.text_area(
            "Budget constraints (optional)",
            value=_val("budget_notes", "") or "",
            placeholder="e.g. Tuition £15,000/year, need scholarship for living costs",
            height=70,
        )
        notes = st.text_area(
            "Additional notes (optional)",
            value=_val("notes", "") or "",
            height=80,
        )

    st.markdown("""
<div class="vf-save-panel">
    <div>
        <b>Ready to save?</b>
        <span>Your profile will update eligibility, scholarship matching, dashboard progress, and AI guidance.</span>
    </div>
</div>
""", unsafe_allow_html=True)

    submitted = st.form_submit_button("Save profile", type="primary")

if submitted:
        if not full_name or not nationality or not country_of_residence \
           or not destination_country:
            st.error("Please fill in all fields marked with *.")
        else:
            try:
                data = ProfileIn(
                    full_name=full_name.strip(),
                    age=int(age) if age else None,
                    nationality=nationality,
                    country_of_residence=country_of_residence,
                    passport_valid_until=passport_valid_until_date.isoformat()
                    if passport_valid_until_date else None,
                    previous_travel_history=previous_travel_history.strip() or None,
                    education_level=education_level or None,
                    gpa=float(gpa) if gpa else None,
                    english_test_type=english_test_type or None,
                    english_test_score=float(english_test_score)
                    if english_test_score else None,
                    destination_country=destination_country,
                    intended_degree_level=intended_degree_level or None,
                    intended_institution_type=intended_institution_type or None,
                    offer_letter_status=offer_letter_status,
                    proof_of_funds_status=proof_of_funds_status,
                    has_dependents=has_dependents,
                    field_of_study=field_of_study_list,  # Pydantic normalizes list -> string
                    previous_field_of_study=previous_field_of_study or None,
                    target_intake=target_intake or None,
                    budget_notes=budget_notes or None,
                    notes=notes or None,
                )
                new_id = create_or_update_profile(
                    data,
                    profile_id=loaded_id,
                    user_id=current_user_id(),
                )

                st.session_state["profile_id"] = new_id
                st.session_state["profile_saved_success"] = True
                st.rerun()  

            except Exception as e:
                st.error(f"Could not save profile: {e}")
                
if st.session_state.get("profile_saved_success", False):
                    st.success("Profile saved successfully. Your eligibility and route guidance are now updated.")

                    with st.container(border=True):
                        st.markdown("### Next step")
                        st.markdown(
                            "Run your eligibility check to evaluate visa readiness, "
                            "identify risks, and generate your recommended immigration route."
                        )

                        if st.button(
                            "✅ Run eligibility check →",
                            use_container_width=False,
                            key="profile_go_eligibility",
                        ):
                            st.session_state["profile_saved_success"] = False
                            st.switch_page("pages/2_Eligibility.py")         

st.divider()
disclaimer(compact=True)





