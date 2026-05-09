"""
app.py
------
VisaForge main landing page.
"""

from __future__ import annotations

import streamlit as st

from components.ui import disclaimer, render_sidebar
from config.settings import settings
from db.init_db import initialize
from services.auth_service import is_admin, is_logged_in


st.set_page_config(
    page_title=f"{settings.APP_NAME} — {settings.APP_TAGLINE}",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _bootstrap() -> bool:
    initialize()
    return True


_bootstrap()
render_sidebar()

if is_logged_in():
    if is_admin():
        st.switch_page("pages/8_Admin.py")
    else:
        st.switch_page("pages/7_Dashboard.py")


st.markdown("""
<style>
.block-container {
    padding-top: 2rem;
    max-width: 1200px;
}

.vf-hero {
    background: linear-gradient(135deg,#4f46e5 0%,#2563eb 55%,#14b8a6 100%);
    border-radius: 34px;
    padding: 58px 56px;
    color: white;
    box-shadow: 0 30px 80px rgba(37,99,235,0.22);
    margin-bottom: 30px;
    text-align: center;
}

.vf-hero h1 {
    font-size: 4rem;
    font-weight: 900;
    margin: 0 0 14px 0;
}

.vf-hero p {
    font-size: 1.18rem;
    opacity: 0.95;
    margin: 0;
}

.vf-card {
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(148,163,184,0.18);
    border-radius: 28px;
    padding: 32px;
    box-shadow: 0 18px 50px rgba(15,23,42,0.06);
    min-height: 320px;
}

.vf-card h3 {
    font-size: 2rem;
    margin: 0 0 16px 0;
}

.vf-card p,
.vf-card li {
    font-size: 1.03rem;
    line-height: 1.85;
    color: #334155;
}

.vf-pill {
    display: inline-block;
    background: #eef2ff;
    color: #2563eb;
    border-radius: 999px;
    padding: 8px 14px;
    font-size: 0.85rem;
    font-weight: 800;
    margin-right: 8px;
    margin-bottom: 10px;
}

.stPageLink a {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    min-height: 48px !important;
    border-radius: 16px !important;
    background: linear-gradient(135deg,#2563eb 0%,#3b82f6 100%) !important;
    color: white !important;
    font-weight: 800 !important;
    border: none !important;
    box-shadow: 0 14px 30px rgba(37,99,235,0.20) !important;
}

.stPageLink a p {
    color: white !important;
    font-weight: 800 !important;
}
</style>
""", unsafe_allow_html=True)


st.markdown("""<div class="vf-hero">
    <h1>✈️ VisaForge</h1>
    <p>AI-assisted immigration & scholarship guidance for students planning their study-abroad journey.</p>
</div>""", unsafe_allow_html=True)


left, right = st.columns([1.8, 1])

with left:
    st.markdown("""<div class="vf-card">
    <h3>Start your study-abroad journey</h3>
    <p>
        VisaForge combines deterministic immigration workflows with grounded AI guidance,
        official policy sources, scholarship discovery, route planning, and document preparation.
    </p>
    <div style="margin-top:18px;">
        <span class="vf-pill">🇬🇧 United Kingdom</span>
        <span class="vf-pill">🇨🇦 Canada</span>
        <span class="vf-pill">🇩🇪 Germany</span>
        <span class="vf-pill">🎓 Scholarships</span>
    </div>
</div>""", unsafe_allow_html=True)

    st.markdown("")
    c1, c2 = st.columns(2)

    with c1:
        st.page_link("pages/0_Login.py", label="🔐 Sign in", use_container_width=True)

    with c2:
        st.page_link("pages/0_Register.py", label="📝 Create account", use_container_width=True)


with right:
    st.markdown("""<div class="vf-card">
    <h3>Why VisaForge?</h3>
    <ul>
        <li><strong>Deterministic first</strong> — AI never decides eligibility</li>
        <li><strong>Official-source grounded</strong> guidance</li>
        <li><strong>Scholarship tracking</strong> with freshness monitoring</li>
        <li><strong>Route planning</strong> and document readiness</li>
        <li><strong>Admin review systems</strong> for safer workflows</li>
    </ul>
</div>""", unsafe_allow_html=True)


st.markdown("")
st.divider()
disclaimer()
