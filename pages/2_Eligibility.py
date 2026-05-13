"""Page 2 — Deterministic eligibility evaluation (v0.3)."""
from __future__ import annotations

import streamlit as st

from components.badges import (
    decision_badge,
    outcome_badge,
    priority_badge,
    render_badge,
)
from components.ui import (
    disclaimer,
    page_header,
    render_sidebar,
    require_profile,
    require_stage,
    require_user,
)
from services.eligibility_service import evaluate_eligibility, save_report
from services.profile_service import get_profile

st.set_page_config(
    page_title="Eligibility · VisaForge", page_icon="✅", layout="wide"
)
st.session_state["_current_page_path"] = "pages/2_Eligibility.py"

render_sidebar()
require_user()
require_stage('eligibility')


st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(99,102,241,.08), transparent 34%),
        linear-gradient(180deg,#fbfcff 0%,#ffffff 45%,#fbfbff 100%);
}

.block-container {
    max-width: 1180px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
}

hr {
    border-color:#eef2f7;
    margin:1.7rem 0;
}

div[data-testid="stMetric"] {
    padding:18px 20px;
    border-radius:18px;
    background:rgba(255,255,255,.92);
    border:1px solid #e5e7eb;
    box-shadow:0 14px 34px rgba(15,23,42,.045);
}

div[data-testid="stMetric"] label {
    color:#64748b !important;
    font-weight:750 !important;
}

div[data-testid="stMetricValue"] {
    color:#111827 !important;
    font-weight:950 !important;
}

div[data-testid="stButton"] button,
.stPageLink a {
    border-radius:14px !important;
    min-height:44px !important;
    font-weight:850 !important;
    border:1px solid #dbeafe !important;
    box-shadow:0 10px 24px rgba(37,99,235,.08) !important;
}



div[data-testid="stAlert"] {
    border-radius:16px !important;
    border:1px solid #bbf7d0 !important;
    background:linear-gradient(135deg,#ecfdf5,#ffffff) !important;
}

div[data-testid="stExpander"] {
    border-radius:16px !important;
    border:1px solid #e5e7eb !important;
    background:rgba(255,255,255,.94) !important;
    box-shadow:0 12px 28px rgba(15,23,42,.045) !important;
}

.vf-elig-hero {
    border-radius:24px;
    padding:30px 32px;
    margin:8px 0 24px 0;
    color:white;
    background:
        radial-gradient(circle at 88% 16%, rgba(255,255,255,.22), transparent 7%),
        linear-gradient(135deg,#16a34a 0%,#2563eb 48%,#14b8a6 100%);
    box-shadow:0 24px 70px rgba(37,99,235,.18);
    position:relative;
    overflow:hidden;
}

.vf-elig-hero:after {
    content:"";
    position:absolute;
    right:-80px;
    top:-70px;
    width:460px;
    height:250px;
    background:repeating-radial-gradient(ellipse at center, rgba(255,255,255,.12) 0 1px, transparent 2px 18px);
    opacity:.45;
    transform:rotate(-10deg);
}

.vf-elig-hero h1 {
    position:relative;
    z-index:1;
    margin:0 0 12px 0;
    font-size:34px;
    font-weight:950;
    letter-spacing:-.7px;
}

.vf-elig-hero p {
    position:relative;
    z-index:1;
    margin:0;
    max-width:780px;
    font-size:14px;
    line-height:1.65;
    font-weight:650;
    opacity:.95;
}

.vf-elig-card {
    border-radius:20px;
    padding:22px 24px;
    background:rgba(255,255,255,.94);
    border:1px solid #e5e7eb;
    box-shadow:0 18px 45px rgba(15,23,42,.055);
    margin-bottom:16px;
}

.vf-elig-section-title {
    font-size:24px;
    font-weight:950;
    color:#111827;
    margin:0 0 8px 0;
}

.vf-elig-muted {
    color:#64748b;
    font-size:13px;
    font-weight:650;
}

.vf-soft-row {
    border-radius:14px;
    padding:14px 16px;
    border:1px solid #e5e7eb;
    background:#ffffff;
    margin:10px 0;
}

.vf-soft-pill {
    display:inline-flex;
    padding:5px 10px;
    border-radius:999px;
    background:#ecfdf5;
    color:#047857;
    font-size:12px;
    font-weight:850;
}

.vf-risk-box {
    border-radius:18px;
    padding:20px;
    border:1px solid #e5e7eb;
    background:linear-gradient(135deg,#ffffff,#f8fafc);
    box-shadow:0 14px 34px rgba(15,23,42,.045);
}

@media(max-width:900px){
    .vf-elig-hero h1 {font-size:28px;}
}

/* Eligibility lower-page polish */
.vf-timeline-row,
.vf-soft-row {
    display:flex !important;
    align-items:center !important;
    justify-content:space-between !important;
    gap:16px !important;
    padding:16px 18px !important;
    border-radius:16px !important;
    background:rgba(255,255,255,.95) !important;
    border:1px solid #e5e7eb !important;
    box-shadow:0 10px 26px rgba(15,23,42,.045) !important;
    margin:10px 0 !important;
}

.vf-timeline-row:hover,
.vf-soft-row:hover {
    transform:translateY(-1px);
    border-color:#bfdbfe !important;
    box-shadow:0 16px 34px rgba(37,99,235,.08) !important;
}

.vf-timeline-date,
.vf-soft-pill {
    display:inline-flex !important;
    align-items:center !important;
    justify-content:center !important;
    padding:6px 11px !important;
    border-radius:999px !important;
    background:#ecfdf5 !important;
    color:#047857 !important;
    font-size:12px !important;
    font-weight:900 !important;
    white-space:nowrap !important;
}

.vf-risk-box {
    border-radius:20px !important;
    padding:24px !important;
    border:1px solid #fecaca !important;
    background:linear-gradient(135deg,#fff7f7,#ffffff) !important;
    box-shadow:0 18px 45px rgba(239,68,68,.06) !important;
}

.vf-risk-box h2,
.vf-risk-box h3 {
    color:#991b1b !important;
    font-weight:950 !important;
}

.vf-risk-box ul {
    margin-top:14px !important;
    padding-left:20px !important;
}

.vf-risk-box li {
    padding:8px 0 !important;
    color:#7f1d1d !important;
    font-weight:650 !important;
}

div[data-testid="stExpander"] {
    border-radius:18px !important;
    overflow:hidden !important;
    border:1px solid #dbeafe !important;
    background:rgba(255,255,255,.96) !important;
    box-shadow:0 14px 34px rgba(15,23,42,.045) !important;
}

div[data-testid="stExpander"] summary {
    padding:16px 18px !important;
    background:linear-gradient(135deg,#eff6ff,#ffffff) !important;
    font-weight:900 !important;
}

div[data-testid="stExpander"] summary p {
    font-weight:900 !important;
    color:#0f172a !important;
}

div[data-testid="stHorizontalBlock"]:has(.stPageLink) {
    gap:18px !important;
}

.stPageLink a {
    border-radius:16px !important;
    min-height:48px !important;
    padding:0 18px !important;
    background:rgba(255,255,255,.96) !important;
    border:1px solid #bfdbfe !important;
    color:#1d4ed8 !important;
    font-weight:900 !important;
    box-shadow:0 14px 32px rgba(37,99,235,.10) !important;
}

.stPageLink a:hover {
    transform:translateY(-2px) !important;
    background:linear-gradient(135deg,#eff6ff,#ffffff) !important;
    box-shadow:0 18px 38px rgba(37,99,235,.14) !important;
}

.stPageLink a p {
    font-weight:900 !important;
}


/* Suggested timeline premium polish */
.vf-soft-row.vf-timeline-row {
    position:relative !important;
    min-height:72px !important;
    padding:18px 22px 18px 54px !important;
    border-radius:18px !important;
    background:linear-gradient(135deg,#ffffff,#f8fafc) !important;
    border:1px solid #e5e7eb !important;
    box-shadow:0 12px 30px rgba(15,23,42,.045) !important;
}

.vf-soft-row.vf-timeline-row:before {
    content:"";
    position:absolute;
    left:22px;
    top:50%;
    transform:translateY(-50%);
    width:18px;
    height:18px;
    border-radius:999px;
    background:#2563eb;
    box-shadow:0 0 0 6px #dbeafe;
}

.vf-soft-row.vf-timeline-row:after {
    content:"";
    position:absolute;
    left:30px;
    top:54px;
    width:2px;
    height:34px;
    background:#dbeafe;
}

.vf-soft-row.vf-timeline-row:last-child:after {
    display:none;
}

.vf-soft-row.vf-timeline-row strong,
.vf-soft-row.vf-timeline-row b {
    color:#111827 !important;
    font-size:15px !important;
    font-weight:900 !important;
}

.vf-timeline-date {
    min-width:112px !important;
    background:#ecfdf5 !important;
    color:#047857 !important;
    border:1px solid #bbf7d0 !important;
    font-size:12px !important;
    font-weight:900 !important;
    box-shadow:0 8px 18px rgba(22,163,74,.08) !important;
}

.vf-soft-row.vf-timeline-row:hover {
    transform:translateY(-2px);
    border-color:#93c5fd !important;
    box-shadow:0 18px 38px rgba(37,99,235,.10) !important;
}

.vf-soft-row.vf-timeline-row:hover:before {
    background:#16a34a;
    box-shadow:0 0 0 6px #dcfce7;
}


/* Risk flags + bottom action polish */
.vf-risk-box {
    border-radius:22px !important;
    padding:26px 28px !important;
    border:1px solid #fecaca !important;
    background:
        radial-gradient(circle at right top, rgba(248,113,113,.10), transparent 28%),
        linear-gradient(135deg,#fff7f7,#ffffff) !important;
    box-shadow:0 18px 46px rgba(239,68,68,.08) !important;
}

.vf-risk-box h2,
.vf-risk-box h3 {
    display:flex !important;
    align-items:center !important;
    gap:10px !important;
    margin-bottom:10px !important;
    color:#991b1b !important;
    font-size:24px !important;
    font-weight:950 !important;
}

.vf-risk-box p {
    color:#64748b !important;
    font-size:14px !important;
    font-weight:650 !important;
}

.vf-risk-box li {
    margin:10px 0 !important;
    padding:12px 14px !important;
    list-style:none !important;
    border-radius:14px !important;
    background:#fff1f2 !important;
    border:1px solid #fecdd3 !important;
    color:#7f1d1d !important;
    font-weight:700 !important;
}

.vf-risk-box ul {
    padding-left:0 !important;
}

.vf-risk-box li:before {
    content:"!";
    display:inline-grid;
    place-items:center;
    width:22px;
    height:22px;
    margin-right:10px;
    border-radius:999px;
    background:#ef4444;
    color:white;
    font-size:12px;
    font-weight:950;
}

div[data-testid="stHorizontalBlock"] .stPageLink a {
    min-width:260px !important;
    height:52px !important;
    border-radius:16px !important;
    background:linear-gradient(135deg,#ffffff,#eff6ff) !important;
    border:1px solid #bfdbfe !important;
    color:#1d4ed8 !important;
    font-weight:950 !important;
    box-shadow:0 16px 36px rgba(37,99,235,.12) !important;
}

div[data-testid="stHorizontalBlock"] .stPageLink a:hover {
    transform:translateY(-2px) !important;
    border-color:#60a5fa !important;
    box-shadow:0 20px 44px rgba(37,99,235,.18) !important;
}

div[data-testid="stHorizontalBlock"] .stPageLink a p {
    font-size:15px !important;
    font-weight:950 !important;
}


/* Final eligibility timeline/risk/action polish */
.vf-timeline-final {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:18px;
    padding:18px 22px;
    margin:12px 0;
    border-radius:18px;
    background:linear-gradient(135deg,#ffffff,#f8fafc);
    border:1px solid #e5e7eb;
    box-shadow:0 12px 30px rgba(15,23,42,.045);
    transition:all .18s ease;
}

.vf-timeline-final:hover {
    transform:translateY(-2px);
    border-color:#93c5fd;
    box-shadow:0 18px 38px rgba(37,99,235,.10);
}

.vf-timeline-left {
    display:flex;
    align-items:center;
    gap:14px;
}

.vf-timeline-dot {
    width:34px;
    height:34px;
    border-radius:999px;
    display:grid;
    place-items:center;
    background:#dbeafe;
    color:#2563eb;
    font-weight:950;
    box-shadow:0 0 0 6px rgba(219,234,254,.55);
}

.vf-timeline-title {
    color:#111827;
    font-size:15px;
    font-weight:900;
}

.vf-timeline-date {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    padding:7px 12px;
    border-radius:999px;
    background:#ecfdf5;
    color:#047857;
    border:1px solid #bbf7d0;
    font-size:12px;
    font-weight:900;
    white-space:nowrap;
}

.vf-risk-final {
    border-radius:22px;
    padding:26px 28px;
    border:1px solid #fecaca;
    background:
        radial-gradient(circle at right top, rgba(248,113,113,.10), transparent 28%),
        linear-gradient(135deg,#fff7f7,#ffffff);
    box-shadow:0 18px 46px rgba(239,68,68,.08);
}

.vf-risk-final h3 {
    margin:0 0 8px 0;
    color:#991b1b;
    font-size:24px;
    font-weight:950;
}

.vf-risk-final p {
    margin:0 0 14px 0;
    color:#64748b;
    font-size:14px;
    font-weight:650;
}

.vf-risk-item {
    margin:10px 0;
    padding:13px 15px;
    border-radius:14px;
    background:#fff1f2;
    border:1px solid #fecdd3;
    color:#7f1d1d;
    font-weight:700;
}

.vf-risk-item:before {
    content:"!";
    display:inline-grid;
    place-items:center;
    width:22px;
    height:22px;
    margin-right:10px;
    border-radius:999px;
    background:#ef4444;
    color:white;
    font-size:12px;
    font-weight:950;
}

.vf-action-btn {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    min-width:260px;
    min-height:52px;
    padding:0 20px;
    border-radius:16px;
    text-decoration:none !important;
    font-size:15px;
    font-weight:950;
    border:1px solid #bfdbfe;
    box-shadow:0 16px 36px rgba(37,99,235,.12);
    transition:all .18s ease;
}

.vf-action-btn:hover {
    transform:translateY(-2px);
    box-shadow:0 20px 44px rgba(37,99,235,.18);
}

.vf-primary-btn {
    color:#ffffff !important;
    background:linear-gradient(135deg,#2563eb,#4f46e5);
}

.vf-secondary-btn {
    color:#1d4ed8 !important;
    background:linear-gradient(135deg,#ffffff,#eff6ff);
}

</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="vf-elig-hero">
    <h1>Visa Eligibility Check</h1>
    <p>Run a deterministic, rule-based evaluation for your selected destination. The AI only explains the result — it does not decide eligibility.</p>
</div>
""", unsafe_allow_html=True)

profile_id = require_profile()
profile = get_profile(profile_id)
assert profile is not None

# --- Context header -------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Profile", profile.full_name)
c2.metric("Destination", profile.destination_country)
c3.metric("Intake", profile.target_intake or "—")

run = st.button("▶️ Run eligibility evaluation", type="primary")

if run or st.session_state.get("eligibility_report"):
    if run:
        report = evaluate_eligibility(profile)
        try:
            save_report(profile_id, report)
        except Exception as e:
            st.warning(f"Could not persist report: {e}")
        st.session_state["eligibility_report"] = report
    else:
        report = st.session_state["eligibility_report"]

    # ---------- Decision card -------------------------------------------
    st.divider()
    with st.container(border=True):
        head_l, head_r = st.columns([3, 1])
        with head_l:
            render_badge(decision_badge(report.decision))
            st.markdown(f"### {report.country} — decision summary")
            st.write(report.summary)
            if report.weakest_area:
                st.caption(f"🎯 **Weakest area:** {report.weakest_area}")
        with head_r:
            st.metric("Overall confidence", f"{report.confidence:.0%}")

        # Confidence breakdown
        st.markdown("**Confidence breakdown**")
        b = report.confidence_breakdown
        bc = st.columns(4)
        bc[0].metric("Documents", f"{b.documents}%")
        bc[0].progress(b.documents / 100.0)
        bc[1].metric("Financial", f"{b.financial}%")
        bc[1].progress(b.financial / 100.0)
        bc[2].metric("Academic", f"{b.academic}%")
        bc[2].progress(b.academic / 100.0)
        bc[3].metric("Language", f"{b.language}%")
        bc[3].progress(b.language / 100.0)

          # ---------- Timeline -----------------------------------------------
    if report.timeline_plan:
        st.divider()
        st.markdown("### Suggested timeline")
        st.caption(
            f"Backward-planned from your target intake ({profile.target_intake}). "
            "Dates are recommendations, not deadlines."
        )

        timeline_html = ""
        for index, item in enumerate(report.timeline_plan, start=1):
            timeline_html += f"""
<div class="vf-timeline-final">
    <div class="vf-timeline-left">
        <div class="vf-timeline-dot">{index}</div>
        <div class="vf-timeline-title">{item.step}</div>
    </div>
    <div class="vf-timeline-date">{item.recommended_by}</div>
</div>
"""
        st.markdown(timeline_html, unsafe_allow_html=True)
    else:
        st.info("Set a target intake on your profile to see a timeline plan.")

    # ---------- Risk flags ---------------------------------------------
    if report.risk_flags:
        st.divider()

        risk_items = ""
        for flag in report.risk_flags:
            risk_items += f"""
<div class="vf-risk-item">{flag}</div>
"""

        st.markdown(
            f"""
<div class="vf-risk-final">
    <h3>Risk flags</h3>
    <p>Soft signals that may reduce your success odds.</p>
    {risk_items}
</div>
""",
            unsafe_allow_html=True,
        )

# ---------- Full rule trace ----------------------------------------

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.page_link(
            "pages/4_Scholarships.py",
            label="Select scholarship ->",
        )
    with c2:
        st.page_link(
            "pages/6_AI_Assistant.py",
            label="Explain with AI →",
        )

else:
    st.info(
        "Click **Run eligibility evaluation** to score your profile against "
        "the deterministic rule set for your destination country."
    )

st.divider()
disclaimer(compact=True)


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

