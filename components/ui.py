"""
components/ui.py
----------------
Reusable UI fragments: sidebar (role-aware), header, disclaimer,
profile-required guards, source freshness, auth guards, stage gating.

v0.5 journey changes:
  * Sidebar strictly enforces role visibility:
      - logged out          â†’ Login / Register only
      - logged in (user)    â†’ user journey pages + Logout
      - logged in (admin)   â†’ Admin + Dashboard + Logout (no user pages)
  * require_stage(page_key) guards a page against the deterministic
    journey state computed by services/journey_service.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from config.settings import settings
from services.auth_service import (
    current_user_id,
    get_current_user,
    is_admin,
    is_logged_in,
    logout_session,
)
from services.journey_service import (
    JourneyStatus,
    compute_journey,
    require_stage as _journey_require_stage,
)
from services.profile_service import get_profile


DISCLAIMER_TEXT = (
    "⚖️ **Disclaimer** — VisaForge provides guidance and information "
    "support only. It is **not** legal or immigration advice. Always "
    "verify details against official government sources before acting."
)


# ---------- header / disclaimer ------------------------------------------

def page_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()


def disclaimer(compact: bool = False) -> None:
    if compact:
        st.caption(DISCLAIMER_TEXT)
    else:
        st.info(DISCLAIMER_TEXT, icon="⚖️")


# ---------- polished user UI helpers --------------------------------------

def inject_user_ui_css() -> None:
    """Shared polished styling for user journey pages."""
    st.markdown(
        """
<style>
.block-container {
    padding-top: 1.5rem;
    max-width: 1220px;
}

.vf-user-hero {
    background: linear-gradient(135deg,#4f46e5 0%,#2563eb 55%,#14b8a6 100%);
    color: white;
    border-radius: 32px;
    padding: 34px 36px;
    box-shadow: 0 26px 70px rgba(37,99,235,0.22);
    margin-bottom: 24px;
}

.vf-user-hero h1 {
    margin: 0 0 10px 0;
    font-size: 2.4rem;
    font-weight: 900;
    line-height: 1.1;
}

.vf-user-hero p {
    margin: 0;
    opacity: 0.92;
    font-size: 1.02rem;
    line-height: 1.65;
}

.vf-soft-card {
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(148,163,184,0.22);
    border-radius: 24px;
    padding: 22px;
    box-shadow: 0 18px 45px rgba(15,23,42,0.07);
}

.vf-pill {
    display: inline-block;
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 0.78rem;
    font-weight: 850;
    margin-right: 8px;
    margin-bottom: 8px;
    background: #eef2ff;
    color: #3730a3;
}

.vf-muted {
    color: #64748b;
    font-size: 0.92rem;
    line-height: 1.6;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 22px 50px rgba(15,23,42,0.10) !important;
    border-color: rgba(99,102,241,0.28) !important;
}

.stButton > button {
    border-radius: 14px !important;
    min-height: 44px;
    font-weight: 800 !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg,#2563eb 0%,#3b82f6 100%) !important;
    color: white !important;
    border: none !important;
    box-shadow: 0 14px 30px rgba(37,99,235,0.20) !important;
}


.vf-feature-card {
    border-radius: 26px;
    padding: 24px;
    color: white;
    position: relative;
    overflow: hidden;
    min-height: 180px;
    box-shadow: 0 24px 60px rgba(15,23,42,0.16);
    margin-bottom: 18px;
}

.vf-feature-card h3 {
    margin: 0 0 12px 0;
    font-size: 1.55rem;
    font-weight: 900;
}

.vf-feature-card p {
    margin: 0;
    line-height: 1.7;
    opacity: 0.94;
}

.vf-card-blue {
    background: linear-gradient(135deg,#4338ca 0%,#2563eb 100%);
}

.vf-card-purple {
    background: linear-gradient(135deg,#7c3aed 0%,#4f46e5 100%);
}

.vf-card-teal {
    background: linear-gradient(135deg,#0891b2 0%,#14b8a6 100%);
}

.vf-card-orange {
    background: linear-gradient(135deg,#ea580c 0%,#fb7185 100%);
}

.vf-card-dark {
    background: linear-gradient(135deg,#0f172a 0%,#1e293b 100%);
}

.vf-stat {
    font-size: 2.6rem;
    font-weight: 900;
    margin-top: 18px;
}




/* Final dashboard polish */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 24px !important;
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 22px 52px rgba(15,23,42,0.11) !important;
    border-color: rgba(37,99,235,0.30) !important;
}

/* Prevent metric overflow like 95/1... */
[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    line-height: 1.1 !important;
    white-space: nowrap !important;
}

[data-testid="stMetricLabel"] {
    font-size: 0.85rem !important;
    color: #64748b !important;
}

/* Cleaner captions */
[data-testid="stCaptionContainer"] {
    color: #64748b !important;
    font-size: 0.88rem !important;
}

/* Page links feel more like action buttons */
.stPageLink a {
    border-radius: 14px !important;
    transition: all 0.18s ease !important;
}

.stPageLink a:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 30px rgba(37,99,235,0.16) !important;
}

/* Compact disclaimer */
div[data-testid="stAlert"] {
    border-radius: 18px !important;
}



/* Animated dashboard polish */

@keyframes vfFloat {
    0% { transform: translateY(0px); }
    50% { transform: translateY(-2px); }
    100% { transform: translateY(0px); }
}

@keyframes vfGlow {
    0% { box-shadow: 0 0 0 rgba(37,99,235,0.0); }
    50% { box-shadow: 0 0 22px rgba(37,99,235,0.14); }
    100% { box-shadow: 0 0 0 rgba(37,99,235,0.0); }
}

/* Hero banner enhancement */
.vf-hero,
.vf-dashboard-hero {
    position: relative;
    overflow: hidden;
}

.vf-hero::after,
.vf-dashboard-hero::after {
    content: "";
    position: absolute;
    inset: 0;
    background:
        radial-gradient(circle at top right,
        rgba(255,255,255,0.18),
        transparent 32%);
    pointer-events: none;
}

/* KPI cards */
div[data-testid="stVerticalBlockBorderWrapper"] {
    backdrop-filter: blur(12px);
}

/* Timeline cards */
.vf-timeline-step {
    transition: all 0.18s ease;
}

.vf-timeline-step:hover {
    transform: translateY(-4px) scale(1.02);
}

.vf-step-done {
    animation: vfGlow 3s infinite ease-in-out;
}

/* Pills */
.vf-soft-pill {
    transition: all 0.18s ease !important;
}

.vf-soft-pill:hover {
    transform: translateY(-2px);
    background: rgba(37,99,235,0.08) !important;
}

/* Buttons */
button[kind="secondary"] {
    border-radius: 14px !important;
    transition: all 0.18s ease !important;
}

button[kind="secondary"]:hover {
    transform: translateY(-2px);
    border-color: rgba(37,99,235,0.45) !important;
}

/* Progress bars */
[data-testid="stProgressBar"] > div > div {
    background: linear-gradient(
        90deg,
        #2563eb,
        #3b82f6,
        #06b6d4
    ) !important;
}

/* Smooth section appearance */
.main .block-container > div {
    animation: vfFloat 0.45s ease;
}



/* Premium card upgrade */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background:
        linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.92)) !important;
    border: 1px solid rgba(148,163,184,0.24) !important;
    border-radius: 26px !important;
    box-shadow:
        0 18px 45px rgba(15,23,42,0.06),
        inset 0 1px 0 rgba(255,255,255,0.85) !important;
    overflow: hidden !important;
}

/* Card heading refinement */
div[data-testid="stVerticalBlockBorderWrapper"] h3,
div[data-testid="stVerticalBlockBorderWrapper"] h4 {
    letter-spacing: -0.035em !important;
    color: #0f172a !important;
}

/* Softer text inside cards */
div[data-testid="stVerticalBlockBorderWrapper"] p {
    color: #334155 !important;
    line-height: 1.7 !important;
}

/* Make CTA links inside cards feel clickable */
div[data-testid="stVerticalBlockBorderWrapper"] .stPageLink a {
    background: rgba(239,246,255,0.72) !important;
    border: 1px solid rgba(147,197,253,0.35) !important;
    padding: 8px 12px !important;
    border-radius: 999px !important;
    width: fit-content !important;
    min-height: 38px !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] .stPageLink a p {
    color: #1d4ed8 !important;
    font-weight: 850 !important;
}

/* Stronger selected/positive badges */
span[data-testid="stBadge"],
[data-testid="stMarkdownContainer"] span {
    font-weight: 800;
}

/* Status success strips */
div[data-testid="stAlert"] {
    border-radius: 20px !important;
    border: 1px solid rgba(34,197,94,0.16) !important;
}

/* Metric-style cards feel less flat */
[data-testid="stMetricValue"] {
    color: #0f172a !important;
    font-weight: 950 !important;
}

/* Dashboard buttons */
.stButton > button {
    background: rgba(255,255,255,0.86) !important;
    border: 1px solid rgba(148,163,184,0.30) !important;
    box-shadow: 0 10px 24px rgba(15,23,42,0.05) !important;
}

.stButton > button:hover {
    background: linear-gradient(135deg,#2563eb 0%,#3b82f6 100%) !important;
    color: white !important;
    border-color: transparent !important;
    box-shadow: 0 16px 34px rgba(37,99,235,0.20) !important;
}

.stButton > button:hover p {
    color: white !important;
}



/* Colored dashboard list-card style */
.vf-list-head {
    display:flex;
    align-items:center;
    gap:12px;
    padding:14px 16px;
    border-radius:18px;
    margin-bottom:18px;
    font-size:1.25rem;
    font-weight:950;
    letter-spacing:-0.03em;
}

.vf-head-profile {
    background:linear-gradient(135deg,#ede9fe,#f5f3ff);
    color:#4c1d95;
    border:1px solid #ddd6fe;
}

.vf-head-eligibility {
    background:linear-gradient(135deg,#dcfce7,#ecfdf5);
    color:#166534;
    border:1px solid #bbf7d0;
}

.vf-head-scholarship {
    background:linear-gradient(135deg,#fff7ed,#fffbeb);
    color:#92400e;
    border:1px solid #fed7aa;
}

.vf-head-route {
    background:linear-gradient(135deg,#dbeafe,#ecfeff);
    color:#1e40af;
    border:1px solid #bfdbfe;
}

.vf-head-documents {
    background:linear-gradient(135deg,#f1f5f9,#f8fafc);
    color:#475569;
    border:1px solid #e2e8f0;
}

.vf-head-ai {
    background:linear-gradient(135deg,#fce7f3,#eef2ff);
    color:#831843;
    border:1px solid #fbcfe8;
}

.vf-info-row {
    display:flex;
    justify-content:space-between;
    gap:18px;
    padding:10px 0;
    border-bottom:1px solid rgba(148,163,184,0.16);
}

.vf-info-row:last-child {
    border-bottom:none;
}

.vf-info-label {
    color:#64748b;
    font-weight:800;
    font-size:0.9rem;
}

.vf-info-value {
    color:#0f172a;
    font-weight:850;
    text-align:right;
}

.vf-muted-note {
    color:#64748b;
    line-height:1.7;
    font-size:0.94rem;
}


    /* Compact global sidebar polish */
    [data-testid="stSidebar"] {
        min-width: 270px !important;
        max-width: 300px !important;
    }

    .vf-side-brand {
        border-radius: 20px !important;
        padding: 18px 18px !important;
        margin-bottom: 14px !important;
    }

    .vf-side-brand h2 {
        font-size: 1.25rem !important;
        margin-bottom: 6px !important;
    }

    .vf-side-brand p {
        font-size: 0.82rem !important;
        line-height: 1.45 !important;
    }

    .vf-side-card {
        border-radius: 18px !important;
        padding: 15px 16px !important;
        margin: 10px 0 14px 0 !important;
    }

    .vf-side-label {
        font-size: 0.68rem !important;
        letter-spacing: 0.08em !important;
    }

    .vf-side-name {
        font-size: 0.95rem !important;
    }

    .vf-side-email {
        font-size: 0.78rem !important;
    }

    [data-testid="stSidebar"] .stPageLink a {
        min-height: 38px !important;
        padding: 7px 10px !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,.78) !important;
        border: 1px solid rgba(191,219,254,.75) !important;
        box-shadow: 0 6px 16px rgba(15,23,42,.035) !important;
        font-size: 0.86rem !important;
    }

    [data-testid="stSidebar"] .stPageLink a p {
        font-size: 0.86rem !important;
        font-weight: 750 !important;
        margin: 0 !important;
    }

    [data-testid="stSidebar"] .stButton button {
        min-height: 38px !important;
        border-radius: 12px !important;
        font-size: 0.86rem !important;
        font-weight: 750 !important;
    }

    .vf-side-status span {
        padding: 5px 8px !important;
        font-size: 0.68rem !important;
    }

    
    /* Active sidebar nav highlight */
.vf-active-nav {
    min-height: 44px;
    padding: 0 14px;
    border-radius: 14px;
    background: linear-gradient(135deg,#2563eb,#14b8a6);
    color: white !important;
    font-size: 0.94rem;
    font-weight: 900;
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 6px 0;
    box-shadow: 0 14px 30px rgba(37,99,235,.22);
    border: 1px solid rgba(255,255,255,.45);
}

.vf-nav-icon {
    min-width: 28px;
    height: 28px;
    border-radius: 10px;
    display: inline-grid;
    place-items: center;
    background: rgba(255,255,255,.22);
    color: white;
    font-size: 0.72rem;
    font-weight: 950;
}
    
</style>
""",
        unsafe_allow_html=True,
    )


def user_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
<div class="vf-user-hero">
    <h1>{title}</h1>
    <p>{subtitle}</p>
</div>
""",
        unsafe_allow_html=True,
    )




def styled_card():
    """Consistent polished card wrapper."""
    return st.container(border=True)

def soft_pill(text: str, bg: str = "#eef2ff", color: str = "#3730a3") -> str:
    return (
        f"<span class='vf-pill' style='background:{bg};color:{color};'>"
        f"{text}</span>"
    )




# ---------- auth guards ---------------------------------------------------

def require_auth() -> dict:
    """Block rendering unless the user is logged in.

    Admins accessing a user-journey page are redirected to Admin â€”
    the journey does not apply to them and the spec requires clean
    role separation.
    """
    user = get_current_user()
    if user is None:
        st.warning("Please log in to continue.")
        l, r = st.columns(2)
        with l:
            st.page_link("pages/0_Login.py", label="Go to Login", icon="🔐")
        with r:
            st.page_link("pages/0_Register.py",
                         label="Create an account", icon="📝")
        st.stop()
    return user  # type: ignore[return-value]


def require_admin() -> dict:
    """Block rendering unless the user is an admin."""
    user = require_auth()
    if not is_admin():
        st.error("🚫 Admins only. You don't have access to this page.")
        st.page_link("pages/7_Dashboard.py",
                     label="Back to Dashboard", icon="📊")
        st.stop()
    return user


def require_user() -> dict:
    """Block rendering for admins on user-journey pages â€” admins belong
    on the Admin dashboard."""
    user = require_auth()
    if is_admin():
        st.info(
            "You're signed in as an admin. User-journey pages are reserved "
            "for applicant accounts."
        )
        st.page_link("pages/8_Admin.py",
                     label="Go to Admin Dashboard", icon="⚙️")
        st.stop()
    return user


def require_stage(page_key: str) -> JourneyStatus:
    """Enforce journey gating for a given page_key. Returns the current
    JourneyStatus so the page can render contextual details.

    Must be called AFTER require_user() / require_auth()."""
    uid = current_user_id()
    status = compute_journey(uid) if uid else JourneyStatus()
    lock = _journey_require_stage(page_key, status)
    if lock is not None:
        msg, redirect = lock
        st.warning(f"🔒 {msg}")
        st.page_link(redirect, label=f"→ Go to required step")
        st.page_link("pages/7_Dashboard.py",
                     label="Back to Dashboard", icon="📊")
        st.stop()
    return status


# ---------- profile selection --------------------------------------------

def _profiles_for_current_user() -> list:
    """Admins see all profiles, users see only their own."""
    from services.profile_service import list_profiles, list_profiles_for_user
    uid = current_user_id()
    if is_admin():
        return list_profiles()
    if uid is None:
        return []
    return list_profiles_for_user(uid)


def ensure_profile_selected() -> Optional[int]:
    """Show a profile picker if no profile is in session. Returns profile_id."""
    profile_id = st.session_state.get("profile_id")
    if profile_id is not None:
        p = get_profile(profile_id)
        if p is not None:
            if is_admin() or getattr(p, "user_id", None) == current_user_id():
                return profile_id
        st.session_state.pop("profile_id", None)

    profiles = _profiles_for_current_user()
    if not profiles:
        st.warning(
            "No profile found yet. Create one first on the **Profile** page."
        )
        st.page_link("pages/1_Profile.py", label="→ Create a profile",
                     icon="👤")
        return None

    if len(profiles) == 1:
        st.session_state["profile_id"] = profiles[0].id
        return profiles[0].id

    options = {
        f"{p.full_name} → {p.destination_country}": p.id for p in profiles
    }
    choice = st.selectbox("Select a profile", list(options.keys()))
    if choice:
        st.session_state["profile_id"] = options[choice]
    return st.session_state.get("profile_id")


def require_profile():
    """Stop rendering if no profile selected."""
    pid = ensure_profile_selected()
    if pid is None:
        st.stop()
    return pid


# ---------- sidebar -------------------------------------------------------

_USER_NAV: list[tuple[str, str]] = [
    ("pages/7_Dashboard.py",    "📊 Dashboard"),
    ("pages/1_Profile.py",      "👤 Profile"),
    ("pages/2_Eligibility.py",  "✅ Eligibility"),
    ("pages/4_Scholarships.py", "🎓 Scholarships"),
    ("pages/3_Route_Plan.py",   "🗺️ Route Plan"),
    ("pages/5_Documents.py",    "📄 Documents"),
    ("pages/6_AI_Assistant.py", "🤖 AI Assistant"),
]

_ADMIN_NAV: list[tuple[str, str]] = [
    ("pages/8_Admin.py", "⚙️ Admin"),
]


def _hide_auto_pages_css() -> None:
    """Streamlit auto-discovers every file in pages/ and lists them in the
    sidebar regardless of our custom links. We hide that auto-list so
    only our role-filtered `page_link` navigation is visible."""
    st.markdown(
        """
        <style>
        /* Hide Streamlit's auto-generated multipage navigation so our
           role-filtered links are the only ones shown. */
        [data-testid="stSidebarNav"] { display: none !important; }
        section[data-testid="stSidebar"] ul[data-testid="stSidebarNavItems"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    _hide_auto_pages_css()

    sidebar_css = """
    <style>
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg,#eef4ff 0%,#f8fafc 100%);
    }

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.65rem;
    }

    .vf-side-brand {
        background: linear-gradient(135deg,#4f46e5 0%,#2563eb 58%,#14b8a6 100%);
        color: white;
        border-radius: 24px;
        padding: 22px 20px;
        box-shadow: 0 18px 42px rgba(37,99,235,0.22);
        margin-bottom: 18px;
    }

    .vf-side-brand h2 {
        font-size: 1.45rem;
        margin: 0 0 8px 0;
        font-weight: 900;
    }

    .vf-side-brand p {
        margin: 0;
        opacity: 0.9;
        line-height: 1.5;
        font-size: 0.92rem;
    }

    .vf-side-card {
        background: rgba(255,255,255,0.82);
        border: 1px solid rgba(148,163,184,0.24);
        border-radius: 20px;
        padding: 18px;
        box-shadow: 0 12px 30px rgba(15,23,42,0.06);
        margin: 12px 0 18px 0;
    }

    .vf-side-label {
        font-size: 0.78rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 900;
        margin-bottom: 8px;
    }

    .vf-side-name {
        font-size: 1.06rem;
        color: #0f172a;
        font-weight: 900;
        margin-bottom: 6px;
    }

    .vf-side-email {
        font-size: 0.84rem;
        color: #2563eb;
        word-break: break-word;
    }

    .vf-side-pill {
        display: inline-block;
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #86efac;
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 0.72rem;
        font-weight: 900;
        margin-top: 10px;
    }

    .vf-side-status {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 12px;
    }


    .vf-active-nav {
        min-height: 44px !important;
        padding: 0 14px !important;
        border-radius: 14px !important;
        background: linear-gradient(135deg,#2563eb,#14b8a6) !important;
        color: white !important;
        font-size: 0.94rem !important;
        font-weight: 900 !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        margin: 6px 0 !important;
        box-shadow: 0 14px 30px rgba(37,99,235,.22) !important;
        border: 1px solid rgba(255,255,255,.45) !important;
    }

    .vf-nav-icon {
        min-width: 28px !important;
        height: 28px !important;
        border-radius: 10px !important;
        display: inline-grid !important;
        place-items: center !important;
        background: rgba(255,255,255,.22) !important;
        color: white !important;
        font-size: 0.72rem !important;
        font-weight: 950 !important;
    }

    .vf-side-status span {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        color: #475569;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 0.74rem;
        font-weight: 800;
    }
    </style>
    """

    st.markdown(sidebar_css, unsafe_allow_html=True)
    st.markdown('\n<style>\n/* Final compact sidebar button polish */\nsection[data-testid="stSidebar"] {\n    background: linear-gradient(180deg,#eef4ff 0%,#f8fafc 100%) !important;\n}\n\nsection[data-testid="stSidebar"] .stPageLink {\n    margin: 4px 0 !important;\n}\n\nsection[data-testid="stSidebar"] .stPageLink a {\n    min-height: 42px !important;\n    height: 42px !important;\n    width: 100% !important;\n    padding: 0 14px !important;\n    border-radius: 13px !important;\n    background: rgba(255,255,255,.88) !important;\n    border: 1px solid rgba(191,219,254,.85) !important;\n    box-shadow: 0 8px 20px rgba(15,23,42,.035) !important;\n    display: flex !important;\n    align-items: center !important;\n    justify-content: flex-start !important;\n    text-align: left !important;\n}\n\nsection[data-testid="stSidebar"] .stPageLink a:hover {\n    background: #ffffff !important;\n    border-color: rgba(37,99,235,.35) !important;\n    transform: translateY(-1px) !important;\n    box-shadow: 0 12px 24px rgba(37,99,235,.10) !important;\n}\n\nsection[data-testid="stSidebar"] .stPageLink a[aria-current="page"] {\n    background: #e2e8f0 !important;\n    border-color: rgba(148,163,184,.35) !important;\n}\n\nsection[data-testid="stSidebar"] .stPageLink a p {\n    margin: 0 !important;\n    font-size: 0.92rem !important;\n    font-weight: 750 !important;\n    color: #0f172a !important;\n    line-height: 1 !important;\n}\n\nsection[data-testid="stSidebar"] h4,\nsection[data-testid="stSidebar"] h3 {\n    margin-top: 12px !important;\n    margin-bottom: 8px !important;\n    font-size: 1rem !important;\n}\n\nsection[data-testid="stSidebar"] .vf-side-brand {\n    transform: none !important;\n    width: auto !important;\n    border-radius: 22px !important;\n    padding: 20px 18px !important;\n}\n\nsection[data-testid="stSidebar"] .vf-side-card {\n    border-radius: 18px !important;\n    padding: 16px !important;\n}\n\nsection[data-testid="stSidebar"] .stButton button {\n    height: 42px !important;\n    min-height: 42px !important;\n    border-radius: 13px !important;\n    font-size: 0.92rem !important;\n    font-weight: 750 !important;\n}\n</style>\n', unsafe_allow_html=True)
    st.markdown("""
<style>
/* Force compact sidebar navigation */
section[data-testid=\"stSidebar\"] {
    width: 280px !important;
    min-width: 280px !important;
}

section[data-testid=\"stSidebar\"] .stPageLink a {
    min-height: 34px !important;
    padding: 6px 10px !important;
    border-radius: 10px !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

section[data-testid=\"stSidebar\"] .stPageLink a p {
    font-size: 0.88rem !important;
    font-weight: 650 !important;
}

section[data-testid=\"stSidebar\"] .stPageLink a:hover {
    background: rgba(37,99,235,.08) !important;
}

section[data-testid=\"stSidebar\"] .stButton button {
    min-height: 36px !important;
    padding: 6px 10px !important;
    border-radius: 10px !important;
    font-size: 0.88rem !important;
}

.vf-side-brand {
    transform: scale(.92);
    transform-origin: top left;
    width: 108%;
    margin-bottom: 0 !important;
}

.vf-side-card {
    padding: 14px 16px !important;
    border-radius: 16px !important;
}
</style>
""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(
            f"""
<div class="vf-side-brand">
    <h2>VisaForge</h2>
    <p>{settings.APP_TAGLINE}</p>
</div>
""",
            unsafe_allow_html=True,
        )

        # --- Not logged in -> Login + Register only -----------------------
        if not is_logged_in():
            st.markdown(
                """
<div class="vf-side-card">
    <div class="vf-side-label">Welcome</div>
    <div class="vf-side-name">Start your journey</div>
    <div style="color:#64748b;font-size:0.9rem;line-height:1.55;">
        Log in or create an account to continue.
    </div>
</div>
""",
                unsafe_allow_html=True,
            )

            st.page_link("pages/0_Login.py", label="🔐 Login")
            st.page_link("pages/0_Register.py", label="📝 Register")

            return

        user = get_current_user() or {}
        user_name = user.get("name", "User")
        user_email = user.get("email", "")
        user_role = user.get("role", "user")

        st.markdown(
            f"""
<div class="vf-side-card">
    <div class="vf-side-label">Signed in as</div>
    <div class="vf-side-name">{user_name}</div>
    <div class="vf-side-email">{user_email}</div>
    <div class="vf-side-pill">{user_role.title()}</div>
</div>
""",
            unsafe_allow_html=True,
        )

        # --- Admin -> admin-only navigation -------------------------------
        if is_admin():
            st.markdown("#### Navigation")

            for path, label in _ADMIN_NAV:
                st.page_link(path, label=label)

            st.divider()

            if st.button("Logout", use_container_width=True):
                logout_session()
                st.switch_page("app.py")

            return

        # --- Regular user -> user journey + progress ----------------------
        pid = st.session_state.get("profile_id")
        if pid is not None:
            p = get_profile(pid)
            if p:
                st.markdown(
                    f"""
<div class="vf-side-card">
    <div class="vf-side-label">Active Profile</div>
    <div class="vf-side-name">{p.full_name}</div>
    <div style="color:#64748b;font-size:0.9rem;">Destination: {p.destination_country}</div>
</div>
""",
                    unsafe_allow_html=True,
                )

        uid = current_user_id()
        status = compute_journey(uid) if uid else JourneyStatus()

        st.markdown("#### Journey Progress")
        st.progress(status.progress_ratio())
        st.caption(f"{int(status.progress_ratio() * 100)}% complete")

        st.markdown("#### Navigation")
        _render_nav_item(status, "pages/7_Dashboard.py", "Dashboard", None)
        _render_nav_item(status, "pages/1_Profile.py", "Profile", None)
        _render_nav_item(status, "pages/2_Eligibility.py", "Eligibility", "profile_complete")
        _render_nav_item(status, "pages/4_Scholarships.py", "Scholarships", "eligibility_completed")
        _render_nav_item(status, "pages/3_Route_Plan.py", "Route Plan", "eligibility_completed")
        _render_nav_item(status, "pages/5_Documents.py", "Documents", "route_plan_generated")
        _render_nav_item(status, "pages/6_AI_Assistant.py", "AI Assistant", None)

        st.divider()

        if st.button("Logout", use_container_width=True):
            logout_session()
            st.switch_page("app.py")



def _render_nav_item(
    status: JourneyStatus,
    path: str,
    label: str,
    required_flag: Optional[str],
) -> None:
    unlocked = required_flag is None or getattr(status, required_flag, False)
    current_path = st.session_state.get("_current_page_path")

    icons = {
        "Dashboard": "📊",
        "Profile": "👤",
        "Eligibility": "✅",
        "Scholarships": "🎓",
        "Route Plan": "🗺️",
        "Documents": "📄",
        "AI Assistant": "🤖",
    }

    icon = icons.get(label, "")

    if current_path == path:
        st.markdown(
            f"""
            <div class="vf-active-nav">
                <span class="vf-nav-icon">{icon}</span>
                <span>{label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if unlocked:
        st.page_link(path, label=label)
    else:
        st.page_link(path, label=f"Locked {label}", disabled=True)


# ---------- misc fragments ------------------------------------------------

def freshness_label(ts: datetime | None) -> str:
    if ts is None:
        return "never"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - ts
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs} hr ago"
    days = hrs // 24
    return f"{days}d ago"


def section_card(title: str, body_fn, *, icon: str = "") -> None:
    """Render a titled bordered container."""
    with st.container(border=True):
        st.markdown(f"**{icon} {title}**" if icon else f"**{title}**")
        body_fn()

# ---------- Global premium theme -----------------------------------------

def apply_premium_theme() -> None:
    st.markdown(
        """
        <style>

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(99,102,241,0.10), transparent 28%),
                radial-gradient(circle at top right, rgba(20,184,166,0.10), transparent 30%),
                linear-gradient(180deg,#f4f7fb 0%, #eef2ff 100%);
        }

        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 4rem;
            max-width: 1250px;
        }

        div[data-testid="stMetric"] {
            background: rgba(255,255,255,0.82);
            border: 1px solid rgba(148,163,184,0.18);
            padding: 18px;
            border-radius: 24px;
            box-shadow: 0 12px 30px rgba(15,23,42,0.06);
        }

        div[data-testid="stMetricLabel"] {
            font-weight: 700;
        }

        div[data-testid="stVerticalBlock"] div:has(> div.element-container div.stButton) button {
            border-radius: 16px !important;
        }

        .stButton > button {
            border-radius: 16px !important;
            border: none !important;
            background: linear-gradient(
                135deg,
                #4f46e5 0%,
                #2563eb 60%,
                #14b8a6 100%
            ) !important;
            color: white !important;
            font-weight: 700 !important;
            padding: 0.7rem 1rem !important;
            box-shadow: 0 10px 24px rgba(37,99,235,0.22);
            transition: all 0.2s ease;
        }

        .stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 28px rgba(37,99,235,0.28);
        }

        div[data-testid="stForm"] {
            background: rgba(255,255,255,0.76);
            border: 1px solid rgba(148,163,184,0.18);
            padding: 24px;
            border-radius: 28px;
            box-shadow: 0 12px 30px rgba(15,23,42,0.06);
        }

        div[data-testid="stExpander"] {
            border-radius: 20px !important;
            overflow: hidden;
            border: 1px solid rgba(148,163,184,0.15);
        }

        .vf-glass-card {
            background: rgba(255,255,255,0.80);
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 28px;
            padding: 24px;
            box-shadow: 0 12px 30px rgba(15,23,42,0.06);
        }

        .vf-hero {
            background: linear-gradient(
                135deg,
                #4f46e5 0%,
                #2563eb 58%,
                #14b8a6 100%
            );
            border-radius: 32px;
            padding: 38px;
            color: white;
            box-shadow: 0 24px 48px rgba(37,99,235,0.22);
            margin-bottom: 24px;
        }

        .vf-hero h1,
        .vf-hero h2,
        .vf-hero h3 {
            color: white !important;
            margin-bottom: 10px;
        }

        .vf-soft-text {
            color: rgba(255,255,255,0.88);
            line-height: 1.7;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


