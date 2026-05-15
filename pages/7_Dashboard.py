from __future__ import annotations

import streamlit as st

try:
    from st_keyup import st_keyup
except Exception:
    st_keyup = None

from sqlalchemy import select

from components.ui import render_sidebar, require_profile, require_user
from db.database import session_scope
from models.orm import EligibilityResult, SavedScholarship, RoutePlan, CaseDocument
from services.profile_service import get_profile
from services.scholarship_service import get_selected_scholarship
from services.route_plan_service import get_persisted_plan, resolve_required_documents
from services.document_service import list_evidence_for_profile
from services.auth_service import (
    current_user_id,
    get_current_user,
    logout_session,
    self_delete_current_user,
)


st.set_page_config(page_title="Dashboard · VisaForge", page_icon="📊", layout="wide")
require_user()

profile_id = require_profile()
profile = get_profile(profile_id)

if profile is None:
    st.error("Could not load your profile.")
    st.stop()


# -----------------------------
# Real dashboard data
# -----------------------------
user_name = profile.full_name or "Student"
destination = profile.destination_country or "Not selected"
degree = profile.intended_degree_level or "Not selected"
intake = profile.target_intake or "Not selected"

profile_fields = [
    profile.full_name,
    profile.age,
    profile.nationality,
    profile.country_of_residence,
    profile.passport_valid_until,
    profile.education_level,
    profile.gpa,
    profile.destination_country,
    profile.intended_degree_level,
    profile.target_intake,
]

profile_score = round(
    sum(1 for value in profile_fields if value not in (None, "", []))
    / len(profile_fields)
    * 100
)
st.session_state["_current_page_path"] = "pages/7_Dashboard.py"


with session_scope() as db:
    latest_eligibility = db.scalar(
        select(EligibilityResult)
        .where(EligibilityResult.profile_id == profile_id)
        .order_by(EligibilityResult.created_at.desc())
    )

if latest_eligibility:
    eligibility_score = round(float(latest_eligibility.confidence or 0) * 100)
    raw_status = (latest_eligibility.status or "not_run").lower()
else:
    eligibility_score = 0
    raw_status = "not_run"

eligibility_label = {
    "eligible": "Done",
    "conditionally_eligible": "Conditional",
    "high_risk": "High Risk",
    "not_eligible": "Needs Work",
    "not_run": "Not Run",
}.get(raw_status, raw_status.replace("_", " ").title())

selected = get_selected_scholarship(profile_id)
selected_scholarship = selected.title if selected else "No scholarship selected"
scholarship_score = 100 if selected else 0

plan = None
try:
    plan = get_persisted_plan(profile_id, destination)
except Exception:
    plan = None

route_steps = []
if plan:
    if hasattr(plan, "sections"):
        for section in plan.sections:
            route_steps.extend(getattr(section, "steps", []) or [])
    else:
        route_steps = list(getattr(plan, "steps", []) or [])

total_steps = len(route_steps)
completed_steps = len(
    [step for step in route_steps if (getattr(step, "status", "") or "").lower() == "completed"]
)

route_progress = round((completed_steps / total_steps) * 100) if total_steps else 0
route_label = "Ready" if route_progress >= 100 else ("In Progress" if route_progress > 0 else "Not Started")

documents = list_evidence_for_profile(profile_id)

documents_ready = len([
    doc for doc in documents
    if (getattr(doc, "verification_status", "") or "").lower()
    in ("verified", "processed", "processed_with_warnings", "user_confirmed", "admin_verified")
])

documents_total = 0
try:
    if plan:
        required_docs = resolve_required_documents(plan)
        documents_total = len(required_docs or [])
except Exception:
    documents_total = 0

if documents_total <= 0:
    documents_total = len(documents)

documents_score = round((documents_ready / documents_total) * 100) if documents_total else 0

readiness = round(
    (profile_score + eligibility_score + scholarship_score + route_progress + documents_score) / 5
)

readiness_label = "Ready" if readiness >= 80 else "Needs Work"

risk_status = "No significant risks detected." if readiness >= 80 else "Some areas need attention."
risk_subtitle = "Great job! You are on track." if readiness >= 80 else "Complete the pending items below to improve your readiness."

next_title = (
    "Route plan complete!"
    if route_progress >= 100
    else "Continue your route plan"
    if route_progress > 0
    else "Generate your route plan"
)

next_body = (
    "All steps are marked complete. Keep your profile updated, upload any remaining documents, and ensure your scholarship application is submitted."
    if route_progress >= 100
    else "Continue the available route steps and keep your documents updated."
    if route_progress > 0
    else "Generate a route plan after selecting a scholarship and running eligibility."

)

# -----------------------------
# Progress helpers
# -----------------------------
def progress_state(score: int) -> str:
    if score >= 100:
        return "complete"
    if score >= 80:
        return "good"
    if score >= 50:
        return "warn"
    return "bad"


def progress_label(score: int) -> str:
    if score >= 100:
        return "Complete"
    if score >= 80:
        return "Strong"
    if score >= 50:
        return "In Progress"
    return "Needs Work"


def progress_icon(score: int) -> str:
    if score >= 100:
        return "✓"
    if score >= 50:
        return "!"
    return "!"


def progress_color(score: int) -> str:
    if score >= 100:
        return "#16a34a"
    if score >= 80:
        return "#22c55e"
    if score >= 50:
        return "#f59e0b"
    return "#ef4444"


journey_state = progress_state(route_progress)
eligibility_state = progress_state(eligibility_score)
scholarship_state = progress_state(scholarship_score)
route_state = progress_state(route_progress)
documents_state = "good"
readiness_state = progress_state(readiness)

readiness_color = progress_color(readiness)

# Journey milestones
milestones = [
    {
        "label": "Complete profile",
        "done": profile_score >= 80,
        "page": "pages/1_Profile.py",
    },
    {
        "label": "Run eligibility check",
        "done": eligibility_score > 0,
        "page": "pages/2_Eligibility.py",
    },
    {
        "label": "Select a scholarship",
        "done": selected is not None,
        "page": "pages/4_Scholarships.py",
    },
    {
        "label": "Generate route plan",
        "done": total_steps > 0,
        "page": "pages/3_Route_Plan.py",
    },
]

first_incomplete_index = next(
    (i for i, step in enumerate(milestones) if not step["done"]),
    len(milestones),
)

completed_milestones = sum(1 for step in milestones if step["done"])
journey_progress_score = round((completed_milestones / len(milestones)) * 100)

st.session_state["journey_progress"] = journey_progress_score
st.session_state["route_progress"] = route_progress
st.session_state["readiness_score"] = readiness

render_sidebar()

if first_incomplete_index < len(milestones):
    next_title = milestones[first_incomplete_index]["label"]
    next_body = "Continue with this step to improve your application readiness."
    next_page = milestones[first_incomplete_index]["page"]
else:
    next_title = "Review your final application"
    next_body = "Your core workflow is complete. Review documents, scholarship details, and AI guidance before submission."
    next_page = "pages/6_AI_Assistant.py"

# Risk alert
risk_items = []

if profile_score < 80:
    risk_items.append("Profile is incomplete. Add missing academic, passport, intake, and destination details.")
if eligibility_score <= 0:
    risk_items.append("Eligibility has not been evaluated yet.")
elif eligibility_score < 80:
    risk_items.append("Eligibility result needs attention. Review the deterministic trace.")
if selected is None:
    risk_items.append("No scholarship has been selected yet.")
if total_steps <= 0:
    risk_items.append("Route plan has not been generated yet.")
elif route_progress < 100:
    risk_items.append("Route plan has pending steps.")
if documents_total and documents_score < 80:
    risk_items.append("Some required documents are still pending or need review.")

if readiness >= 80 and not risk_items:
    risk_status = "No significant risks detected."
    risk_subtitle = "Great job! You are on track."
elif readiness >= 50:
    risk_status = "Moderate risk areas detected."
    risk_subtitle = "Fix the pending items below to strengthen your application."
else:
    risk_status = "High risk: important steps are still missing."
    risk_subtitle = "Complete the next required steps before relying on readiness."

risk_html = ""
if risk_items:
    risk_html = "<ul style='margin:10px 0 0 18px;padding:0;'>" + "".join(
        f"<li>{item}</li>" for item in risk_items
    ) + "</ul>"



# -----------------------------
# CSS
# -----------------------------
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(99,102,241,.08), transparent 34%),
        linear-gradient(180deg,#fbfcff 0%,#ffffff 42%,#fbfbff 100%);
}

.block-container {
    max-width: 1220px;
    padding-top: 1.4rem;
    padding-bottom: 3rem;
}

#MainMenu, footer, header {
    visibility: hidden;
}

.vf-hero {
    position: relative;
    overflow: hidden;
    padding: 34px;
    border-radius: 24px;
    color: white;
    background: linear-gradient(135deg,#2157f3 0%,#2563eb 38%,#16b8b0 100%);
    box-shadow: 0 24px 70px rgba(37,99,235,.22);
    border: 1px solid rgba(255,255,255,.28);
}

.vf-hero:after {
    content: "";
    position: absolute;
    right: -90px;
    top: -60px;
    width: 520px;
    height: 260px;
    background: repeating-radial-gradient(ellipse at center, rgba(255,255,255,.12) 0 1px, transparent 2px 18px);
    opacity: .45;
    transform: rotate(-10deg);
}

.vf-hero h1 {
    position: relative;
    z-index: 1;
    margin: 0 0 14px 0;
    font-size: 34px;
    line-height: 1.1;
    letter-spacing: -.8px;
    font-weight: 900;
}

.vf-hero p {
    position: relative;
    z-index: 1;
    margin: 0;
    max-width: 760px;
    font-size: 15px;
    line-height: 1.65;
    font-weight: 650;
    opacity: .94;
}

.vf-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin: 22px 0 28px 0;
}

.vf-pill {
    padding: 9px 15px;
    border-radius: 999px;
    background: rgba(255,255,255,.86);
    border: 1px solid #e9e7ff;
    box-shadow: 0 10px 24px rgba(88,80,236,.08);
    color: #4c1d95;
    font-size: 12px;
    font-weight: 850;
}

.vf-metric-card {
    border-radius: 18px;
    padding: 22px;
    min-height: 190px;
    border: 1px solid #e5e7eb;
    background: rgba(255,255,255,.92);
    box-shadow: 0 18px 45px rgba(15,23,42,.06);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}


.vf-metric-card.bad {border-color:#fecaca;background:linear-gradient(135deg,#ffffff,#fef2f2);}
.vf-metric-card.warn {border-color:#fde68a;background:linear-gradient(135deg,#ffffff,#fffbeb);}
.vf-metric-card.good {border-color:#bbf7d0;background:linear-gradient(135deg,#ffffff,#f0fdf4);}
.vf-metric-card.complete {border-color:#16a34a;background:linear-gradient(135deg,#ecfdf5,#dcfce7);}

.vf-metric-icon.bad {background:#fee2e2;color:#ef4444;}
.vf-metric-icon.warn {background:#fef3c7;color:#f59e0b;}
.vf-metric-icon.good {background:#dcfce7;color:#22c55e;}
.vf-metric-icon.complete {background:#16a34a;color:#ffffff;}

.vf-progress span.bad {background:linear-gradient(90deg,#ef4444,#f97316);}
.vf-progress span.warn {background:linear-gradient(90deg,#f59e0b,#facc15);}
.vf-progress span.good {background:linear-gradient(90deg,#22c55e,#16a34a);}
.vf-progress span.complete {background:linear-gradient(90deg,#16a34a,#047857);}

.vf-dot.locked {
    background:#e5e7eb;
    color:#64748b;
    box-shadow:none;
}

.vf-dot.active {
    background:#f59e0b;
    color:white;
    box-shadow:0 8px 20px rgba(245,158,11,.24);
}

.vf-card.vf-risk-bad {
    border-color:#fecaca;
    background:linear-gradient(135deg,#fef2f2,#ffffff);
    color:#991b1b;
}

.vf-card.vf-risk-warn {
    border-color:#fde68a;
    background:linear-gradient(135deg,#fffbeb,#ffffff);
    color:#92400e;
}

.vf-card.vf-risk-good {
    border-color:#bbf7d0;
    background:linear-gradient(135deg,#ecfdf5,#ffffff);
    color:#047857;
}

.vf-metric-card.purple {border-color:#ddd6fe; background:linear-gradient(135deg,#ffffff,#faf7ff);}
.vf-metric-card.green {border-color:#bbf7d0; background:linear-gradient(135deg,#ffffff,#f0fdf4);}
.vf-metric-card.blue {border-color:#bfdbfe; background:linear-gradient(135deg,#ffffff,#eff6ff);}
.vf-metric-card.orange {border-color:#fed7aa; background:linear-gradient(135deg,#ffffff,#fff7ed);}

.vf-metric-top {
    display:flex;
    align-items:center;
    gap:14px;
}

.vf-metric-icon {
    width:54px;
    height:54px;
    border-radius:999px;
    display:grid;
    place-items:center;
    font-size:25px;
    box-shadow:0 14px 30px rgba(15,23,42,.08);
}

.vf-metric-title {
    color:#334155;
    font-size:13px;
    font-weight:850;
}

.vf-metric-value {
    font-size:28px;
    font-weight:950;
    line-height:1;
}

.vf-metric-sub {
    color:#475569;
    font-size:12px;
    font-weight:700;
}

.vf-progress {
    height: 8px;
    border-radius: 99px;
    background: #eef2f7;
    overflow: hidden;
    margin: 10px 0;
}

.vf-progress span {
    display: block;
    height: 100%;
    border-radius: 99px;
    background: linear-gradient(90deg,#2563eb,#4f46e5);
}

.vf-card {
    border-radius: 18px;
    padding: 24px;
    border: 1px solid #e5e7eb;
    background: rgba(255,255,255,.92);
    box-shadow: 0 18px 45px rgba(15,23,42,.055);
    margin-bottom: 16px;
}

.vf-timeline {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    position: relative;
    padding-top: 8px;
}

.vf-timeline:before {
    content: "";
    position: absolute;
    left: 8%;
    right: 8%;
    top: 22px;
    height: 2px;
    background: #86efac;
    z-index: 0;
}

.vf-step {
    position: relative;
    z-index: 1;
    text-align: center;
    font-size: 12px;
    color: #111827;
    font-weight: 850;
}

.vf-dot {
    width: 28px;
    height: 28px;
    margin: 0 auto 9px auto;
    border-radius: 999px;
    background: #16a34a;
    color: white;
    display: grid;
    place-items: center;
    font-weight: 900;
    box-shadow: 0 8px 20px rgba(22,163,74,.24);
    position: relative;
    z-index: 2;
}

.vf-readiness {
    display: grid;
    grid-template-columns: 1fr 260px;
    gap: 24px;
    align-items: center;
}

.vf-breakdown {
    border-left: 1px solid #eef2f7;
    padding-left: 22px;
}

.vf-breakdown-row {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    font-size: 13px;
    margin: 9px 0;
    color: #334155;
    font-weight: 700;
}

.vf-success {
    border-color: #bbf7d0;
    background: linear-gradient(135deg,#ecfdf5,#ffffff);
    color: #047857;
    font-weight: 850;
}

.vf-next {
    border-color: #bfdbfe;
    background: linear-gradient(135deg,#eff6ff,#ffffff);
}

.vf-next h3 {
    margin: 0 0 8px 0;
    color: #1d4ed8;
    font-size: 22px;
    font-weight: 950;
}

.vf-native-icon {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    color: white;
    box-shadow: 0 12px 24px rgba(15,23,42,.14);
}

.vf-native-icon svg {
    width: 27px;
    height: 27px;
    stroke: currentColor;
    stroke-width: 2.3;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
}

.vf-native-title {
    font-size: 18px;
    font-weight: 950;
    color: #111827;
    margin-bottom: 4px;
}

.vf-native-sub {
    color: #475569;
    font-size: 13px;
    font-weight: 650;
}

.vf-native-purple {background:linear-gradient(135deg,#8b5cf6,#5b21b6);}
.vf-native-orange {background:linear-gradient(135deg,#f97316,#c2410c);}
.vf-native-green {background:linear-gradient(135deg,#16a34a,#047857);}
.vf-native-blue {background:linear-gradient(135deg,#2563eb,#1d4ed8);}
.vf-native-slate {background:linear-gradient(135deg,#64748b,#334155);}
.vf-native-pink {background:linear-gradient(135deg,#ec4899,#be185d);}

.vf-mini {
    display:inline-flex;
    align-items:center;
    padding:4px 9px;
    border-radius:999px;
    background:#eef2ff;
    color:#3730a3;
    font-size:11px;
    font-weight:850;
    margin-left:8px;
}

.vf-fit-small {
    text-align:center;
    color:#ea580c;
    font-size:22px;
    font-weight:950;
    margin-bottom:6px;
}


div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important;
    box-shadow: 0 10px 26px rgba(15,23,42,.045) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] > div {
    min-height: 86px !important;
}

.stPageLink a {
    min-width: 150px !important;
    height: 42px !important;
    justify-content: center !important;
    border-radius: 12px !important;
    border: 1px solid #dbeafe !important;
    background: rgba(255,255,255,.96) !important;
    color: #1d4ed8 !important;
    font-weight: 850 !important;
    font-size: 13px !important;
    box-shadow: 0 10px 24px rgba(37,99,235,.07) !important;
}

@media(max-width: 900px) {
    .vf-readiness {grid-template-columns: 1fr;}
    .vf-breakdown {border-left: 0; padding-left: 0;}
    .vf-timeline {grid-template-columns: 1fr;}
}

.vf-inline-link {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    min-width:170px;
    height:44px;
    padding:0 16px;
    border-radius:12px;
    border:1px solid #dbeafe;
    background:#ffffff;
    color:#1d4ed8 !important;
    text-decoration:none !important;
    font-weight:850;
    font-size:13px;
    box-shadow:0 10px 24px rgba(37,99,235,.08);
    white-space:nowrap;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    min-height:118px !important;
    border-radius:16px !important;
    box-shadow:0 10px 26px rgba(15,23,42,.045) !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] > div {
    min-height:118px !important;
}


.vf-next-inner h3 {
    margin:0 0 8px 0;
    color:#1d4ed8;
    font-size:22px;
    font-weight:950;
}
.vf-next-inner div {
    color:#111827;
    font-size:13px;
    font-weight:650;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    min-height:128px !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    min-height:128px !important;
    display:flex !important;
    align-items:center !important;
}


.vf-next-inner {
    padding: 10px 4px;
}
.vf-next-kicker {
    display:inline-flex;
    padding:5px 10px;
    border-radius:999px;
    background:#dbeafe;
    color:#1d4ed8;
    font-size:11px;
    font-weight:900;
    margin-bottom:10px;
}
.vf-next-inner h3 {
    margin:0 0 10px 0 !important;
    color:#1d4ed8 !important;
    font-size:26px !important;
    font-weight:950 !important;
}
.vf-next-inner div {
    color:#111827;
    font-size:14px;
    font-weight:700;
}


/* Timeline polish */
.vf-timeline {
    grid-template-columns: repeat(4, 1fr) !important;
    gap: 20px !important;
    padding: 18px 30px 4px 30px !important;
}

.vf-timeline:before {
    left: 14% !important;
    right: 14% !important;
    top: 32px !important;
    height: 3px !important;
    border-radius: 999px !important;
    background: linear-gradient(90deg,#22c55e,#86efac,#dbeafe) !important;
}

.vf-step {
    font-size: 13px !important;
    line-height: 1.35 !important;
}

.vf-dot {
    width: 34px !important;
    height: 34px !important;
    margin-bottom: 12px !important;
}

.vf-card .vf-mini {
    padding: 7px 12px !important;
}

</style>
""", unsafe_allow_html=True)


# -----------------------------
# Hero
# -----------------------------
st.markdown(
    f"""
<div class="vf-hero">
    <h1>👋 Welcome back, {user_name}</h1>
    <p>Track your eligibility, scholarships, visa route plan, documents, and study-abroad readiness from one intelligent dashboard.</p>
</div>
<div class="vf-pills">
    <div class="vf-pill">🎓 Scholarships</div>
    <div class="vf-pill">🗺 Visa Planning</div>
    <div class="vf-pill">📄 Documents</div>
    <div class="vf-pill">🤖 AI Guidance</div>
</div>
""",
    unsafe_allow_html=True,
)




# -----------------------------
# Account settings
# -----------------------------
with st.expander("Account settings", expanded=False):
    st.markdown("### Delete my account")
    st.warning(
        "This will remove your applicant profile data, eligibility records, selected scholarships, "
        "route progress, uploaded document records, and disable your login. This action cannot be undone from the app."
    )

    current_user = get_current_user() or {}
    current_email = str(current_user.get("email") or "").strip()
    current_uid = current_user_id()

    st.info(f"Signed in as: {current_email}")

    if st_keyup is not None:
        delete_email_raw = st_keyup(
            "Type your email to confirm",
            placeholder=current_email,
            key="dashboard_self_delete_email_live",
            debounce=250,
        )
    else:
        delete_email_raw = st.text_input(
            "Type your email to confirm",
            placeholder=current_email,
            key="dashboard_self_delete_email",
        )

    delete_email_confirmed = (
        (delete_email_raw or "").strip().lower() == current_email.lower()
        and bool(current_email)
    )

    if delete_email_confirmed:
        st.success("Email confirmed. You can now review the final deletion confirmation.")
    else:
        st.caption("The deletion review button unlocks only after your exact email is entered.")

    @st.dialog("Confirm account deletion")
    def _confirm_user_self_delete_dialog():
        st.markdown("### Final account deletion confirmation")
        st.error(
            "This will remove your applicant workflow data from the MVP database "
            "and deactivate your login."
        )

        st.markdown(
            f"""
            **Account email:** {current_email}

            The system will remove applicant-owned records where safely identifiable, anonymise your account,
            disable sign-in, and keep an audit record for accountability.
            """
        )

        final_confirm = st.checkbox(
            "I understand this action cannot be undone from the application.",
            key="dashboard_final_self_delete_confirm",
        )

        if st.button(
            "Confirm and Delete My Account",
            type="primary",
            use_container_width=True,
            disabled=not final_confirm,
            key="dashboard_final_self_delete_button",
        ):
            try:
                self_delete_current_user(current_uid)
                logout_session()
                try:
                    st.query_params.clear()
                except Exception:
                    pass
                st.success("Your account has been deleted/anonymised.")
                st.switch_page("pages/0_Login.py")
            except Exception as exc:
                st.error(f"Could not delete account: {exc}")

    if st.button(
        "Review Account Deletion",
        type="secondary",
        use_container_width=True,
        disabled=not delete_email_confirmed,
        key="dashboard_open_self_delete_dialog",
    ):
        _confirm_user_self_delete_dialog()


# -----------------------------
# Reset journey action
# -----------------------------
with st.expander("Reset journey progress", expanded=False):
    st.warning(
        "This will keep your profile, but clear eligibility results, selected scholarships, route plans, completed route steps, and uploaded documents."
    )

    confirm_reset = st.checkbox(
        "I understand this will reset my journey and keep only my profile."
    )

    if st.button("Reset my journey", type="secondary", use_container_width=True):
        if not confirm_reset:
            st.error("Please tick the confirmation checkbox first.")
        else:
            with session_scope() as db:
                for row in db.scalars(
                    select(EligibilityResult).where(EligibilityResult.profile_id == profile_id)
                ):
                    db.delete(row)

                for row in db.scalars(
                    select(SavedScholarship).where(SavedScholarship.profile_id == profile_id)
                ):
                    db.delete(row)

                for row in db.scalars(
                    select(RoutePlan).where(RoutePlan.profile_id == profile_id)
                ):
                    db.delete(row)

                for row in db.scalars(
                    select(CaseDocument).where(CaseDocument.profile_id == profile_id)
                ):
                    db.delete(row)

            for key in [
                "journey_progress",
                "route_progress",
                "readiness_score",
                "ai_focused_step",
            ]:
                st.session_state.pop(key, None)

            st.success("Journey reset. Your profile is still saved.")
            st.rerun()


# -----------------------------
# Metrics
# -----------------------------
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown(
        f"""
<div class="vf-metric-card {progress_state(journey_progress_score)}">
<div class="vf-metric-top">
<div class="vf-metric-icon {progress_state(journey_progress_score)}">{progress_icon(journey_progress_score)}</div>
<div class="vf-metric-title">Journey Progress</div>
</div>
<div class="vf-metric-value" style="color:{progress_color(journey_progress_score)};">{journey_progress_score}%</div>
<div class="vf-progress"><span class="{progress_state(journey_progress_score)}" style="width:{journey_progress_score}%"></span></div>
<div class="vf-metric-sub">{progress_label(journey_progress_score)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

with m2:
    st.markdown(
        f"""
<div class="vf-metric-card {eligibility_state}">
<div class="vf-metric-top">
<div class="vf-metric-icon {eligibility_state}">{progress_icon(eligibility_score)}</div>
<div class="vf-metric-title">Eligibility</div>
</div>
<div class="vf-metric-value" style="color:{progress_color(eligibility_score)};">{eligibility_label}</div>
<div class="vf-metric-sub">Rule-based check</div>
</div>
""",
        unsafe_allow_html=True,
    )

with m3:
    st.markdown(
        f"""
<div class="vf-metric-card {route_state}">
<div class="vf-metric-top">
<div class="vf-metric-icon {route_state}">{progress_icon(route_progress)}</div>
<div class="vf-metric-title">Route Plan</div>
</div>
<div class="vf-metric-value" style="color:{progress_color(route_progress)};">{route_label}</div>
<div class="vf-metric-sub">Workflow status</div>
</div>
""",
        unsafe_allow_html=True,
    )

with m4:
    st.markdown(
        f"""
<div class="vf-metric-card {documents_state}">
<div class="vf-metric-top">
<div class="vf-metric-icon {documents_state}">{progress_icon(documents_score)}</div>
<div class="vf-metric-title">Documents <span class="vf-mini">Optional</span></div>
</div>
<div class="vf-metric-value" style="color:#2563eb;">Vault</div>
<div class="vf-metric-sub">Optional support</div>
</div>
""",
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)


# -----------------------------
# Timeline
# -----------------------------
timeline_html = ""
for i, step in enumerate(milestones):
    if step["done"]:
        dot_class = ""
        dot_icon = "✓"
    elif i == first_incomplete_index:
        dot_class = "active"
        dot_icon = "!"
    else:
        dot_class = "locked"
        dot_icon = "🔒"

    timeline_html += (
        f'<div class="vf-step">'
        f'<div class="vf-dot {dot_class}">{dot_icon}</div>'
        f'{step["label"]}'
        f'</div>'
    )

optional_docs_html = (
    '<div style="margin-top:22px;display:flex;justify-content:center;">'
    '<div style="display:inline-flex;align-items:center;gap:10px;padding:10px 16px;'
    'border-radius:999px;border:1px dashed #bfdbfe;background:#f8fbff;color:#2563eb;'
    'font-size:13px;font-weight:900;">'
    '<span style="width:26px;height:26px;border-radius:999px;background:#dbeafe;'
    'display:grid;place-items:center;color:#2563eb;font-weight:950;">+</span>'
    'Optional documents vault'
    '</div></div>'
)

st.markdown(
    f"""
<div class="vf-card">
<div style="display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:18px;">
<h2 style="margin:0;font-size:28px;font-weight:950;">Your Journey Timeline</h2>
<span class="vf-mini">{journey_progress_score}% complete</span>
</div>
<div class="vf-timeline">
{timeline_html}
</div>
{optional_docs_html}
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------
# Readiness
# -----------------------------
st.markdown(
    f"""
<div class="vf-card">
    <div class="vf-readiness">
        <div>
            <h2 style="margin:0;font-size:30px;font-weight:950;">Application Readiness — <span style="color:{readiness_color};">{readiness}% ({readiness_label})</span></h2>
            <div class="vf-progress"><span class="{readiness_state}" style="width:{readiness}%"></span></div>
            <div style="color:#64748b;font-size:13px;font-weight:650;">Your score is based on your profile, eligibility result, scholarship selection, route plan progress, and documents.</div>
        </div>
        <div class="vf-breakdown">
            <div class="vf-breakdown-row"><span>Profile</span><b style="color:#2563eb;">{profile_score}%</b></div>
            <div class="vf-breakdown-row"><span>Eligibility</span><b style="color:#16a34a;">{eligibility_score}%</b></div>
            <div class="vf-breakdown-row"><span>Scholarship Fit</span><b style="color:#ea580c;">{scholarship_score}%</b></div>
            <div class="vf-breakdown-row"><span>Route Progress</span><b style="color:#16a34a;">{route_progress}%</b></div>
            <div class="vf-breakdown-row"><span>Documents</span><b style="color:#ea580c;">{documents_score}%</b></div>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

risk_card_class = "vf-risk-good" if readiness >= 80 else ("vf-risk-warn" if readiness >= 50 else "vf-risk-bad")

st.markdown(
    f"""
<div class="vf-card {risk_card_class}">
    <b>{risk_status}</b><br>
    <span style="font-size:13px;font-weight:650;">{risk_subtitle}</span>
    {risk_html}
</div>
""",
    unsafe_allow_html=True,
)

with st.container(border=True):
    next_l, next_r = st.columns([4.5, 1.4], vertical_alignment="center")
    with next_l:
        st.markdown(
            f"""
<div class="vf-next-inner">
    <div class="vf-next-kicker">Recommended next action</div>
    <h3>Next: {next_title}</h3>
    <div>{next_body}</div>
</div>
""",
            unsafe_allow_html=True,
        )
    with next_r:
        st.page_link(next_page, label=f"{next_title} ›")

st.markdown(
    """
<div class="vf-card" style="background:linear-gradient(135deg,#faf5ff,#ffffff);border-color:#ddd6fe;">
    <b>Optional:</b> upload documents for OCR, extraction, and AI review.
    <div style="margin-top:8px;color:#64748b;font-size:13px;font-weight:650;">
        Documents support your journey but do not block route progress. Use this to digitise CNICs, passports, transcripts, and offer letters, then ask the AI for explanations.
    </div>
</div>
""",
    unsafe_allow_html=True,
)


# -----------------------------
# Workflow rows
# -----------------------------
ICONS = {
    "profile": '<svg viewBox="0 0 24 24"><path d="M20 21a8 8 0 0 0-16 0"/><circle cx="12" cy="7" r="4"/></svg>',
    "scholarship": '<svg viewBox="0 0 24 24"><path d="M22 10 12 5 2 10l10 5 10-5Z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/><path d="M22 10v6"/></svg>',
    "eligibility": '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/></svg>',
    "route": '<svg viewBox="0 0 24 24"><path d="M9 18 3 21V6l6-3 6 3 6-3v15l-6 3-6-3Z"/><path d="M9 3v15"/><path d="M15 6v15"/></svg>',
    "documents": '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M8 13h8"/><path d="M8 17h6"/></svg>',
    "ai": '<svg viewBox="0 0 24 24"><rect x="5" y="8" width="14" height="10" rx="3"/><path d="M12 8V4"/><path d="M8 4h8"/><path d="M9 13h.01"/><path d="M15 13h.01"/></svg>',
}


def workflow_row(icon_key, icon_class, title, subtitle, page, button_label, extra=""):
    with st.container(border=True):
        c1, c2, c3 = st.columns([0.55, 5.25, 1.25], gap="small", vertical_alignment="center")

        with c1:
            st.markdown(
                f'<div class="vf-native-icon {icon_class}">{ICONS[icon_key]}</div>',
                unsafe_allow_html=True,
            )

        with c2:
            st.markdown(
                f"""
<div class="vf-native-title">{title}</div>
<div class="vf-native-sub">{subtitle}</div>
""",
                unsafe_allow_html=True,
            )

        with c3:
            if extra:
                st.markdown(extra, unsafe_allow_html=True)
            else:
                st.markdown('<div style="height:34px;"></div>', unsafe_allow_html=True)
            st.page_link(page, label=button_label)


workflow_row(
    "profile",
    "vf-native-purple",
    "Profile",
    f"Name: {user_name} • Destination: {destination} • Degree: {degree} • Intake: {intake}",
    "pages/1_Profile.py",
    "Edit profile",
)

workflow_row(
    "eligibility",
    "vf-native-green",
    'Eligibility <span class="vf-mini">Latest</span>',
    f"Latest result: {eligibility_label} • Confidence: {eligibility_score}%",
    "pages/2_Eligibility.py",
    "View full trace",
)

workflow_row(
    "scholarship",
    "vf-native-orange",
    'Selected Scholarship <span class="vf-mini">Official</span>',
    selected_scholarship,
    "pages/4_Scholarships.py",
    "Open scholarship",
    f'<div class="vf-fit-small">{scholarship_score}/100</div>',
)

workflow_row(
    "route",
    "vf-native-blue",
    f'Route Plan <span class="vf-mini">{route_label}</span>',
    f"Overall progress: {route_progress}%",
    "pages/3_Route_Plan.py",
    "Open route plan",
)

workflow_row(
    "documents",
    "vf-native-slate",
    'Documents <span class="vf-mini">Tracked</span>',
    "Upload, review, and ask AI about your documents",
    "pages/5_Documents.py",
    "Manage documents",
)

workflow_row(
    "ai",
    "vf-native-pink",
    "AI Assistant",
    "Grounded in your deterministic results. Explains each step with clarity.",
    "pages/6_AI_Assistant.py",
    "Open AI Guidance",
)

