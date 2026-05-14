from __future__ import annotations

import html

import pandas as pd
import streamlit as st

try:
    from st_keyup import st_keyup
except Exception:
    st_keyup = None

import streamlit.components.v1 as components

from components.ui import (
    disclaimer,
    freshness_label,
    page_header,
    render_sidebar,
    require_admin,
)
from config.settings import settings
from models.schemas import SourceConfig
from services.admin_service import (
    get_user_funnel_stats,
    get_user_progress_table,
)
from services.ingestion_service import (
    recent_logs,
    refresh_source,
    refresh_sources,
)
from services.notification_service import send_admin_email_campaign
from services.auth_service import (
    AuthError,
    create_admin_account,
    current_user_id,
    get_current_user,
    is_super_admin,
    list_account_management_users,
    list_admin_audit_logs,
    set_user_active_status,
    update_user_role,
)
from services.policy_service import (
    add_source,
    get_route_templates_meta,
    get_visa_rules_meta,
    list_sources,
    set_source_active,
)
from services.scholarship_service import (
    list_by_review_status,
    list_scholarships,
    reclassify_all,
    review_status_counts,
    set_review_status,
)
from services.source_registry_service import (
    list_sources as list_curated_sources,
    seed_from_json,
    set_active as set_curated_active,
    upsert_source as upsert_curated_source,
)


st.set_page_config(
    page_title="Admin Â· VisaForge",
    page_icon="ðŸ›¡ï¸",
    layout="wide",
)

render_sidebar()
require_admin()
current_admin = get_current_user() or {}
current_admin_id = current_user_id()
current_admin_email = current_admin.get("email", "")


st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(99,102,241,0.16), transparent 34%),
            radial-gradient(circle at top right, rgba(20,184,166,0.13), transparent 30%),
            linear-gradient(135deg, #f8fbff 0%, #eef4ff 45%, #f9f7ff 100%);
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #eef4ff 0%, #ffffff 55%, #eef7ff 100%);
        border-right: 1px solid rgba(148,163,184,0.25);
    }

    h1, h2, h3 {
        letter-spacing: -0.03em;
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #ffffff 0%, #f8fbff 100%);
        border: 1px solid rgba(148,163,184,0.22);
        border-radius: 22px;
        padding: 18px 20px;
        box-shadow: 0 14px 35px rgba(15, 23, 42, 0.07);
    }

    div[data-testid="stMetric"] label {
        color: #475569 !important;
        font-weight: 700 !important;
    }

    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-weight: 800 !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 24px !important;
        border: 1px solid rgba(148,163,184,0.22) !important;
        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.07);
        background: rgba(255,255,255,0.86);
        backdrop-filter: blur(14px);
    }

    .stButton > button {
        border-radius: 16px;
        border: 1px solid rgba(99,102,241,0.25);
        box-shadow: 0 8px 20px rgba(37,99,235,0.08);
        font-weight: 700;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 12px 24px rgba(37,99,235,0.16);
    }

    .stRadio [role="radiogroup"] {
        background: rgba(255,255,255,0.75);
        border: 1px solid rgba(148,163,184,0.25);
        border-radius: 22px;
        padding: 12px;
        box-shadow: 0 12px 30px rgba(15,23,42,0.06);
    }

    .stDataFrame {
        border-radius: 20px;
        overflow: hidden;
        box-shadow: 0 12px 30px rgba(15,23,42,0.05);
    }

    .vf-hero {
        padding: 28px 30px;
        border-radius: 28px;
        background:
            radial-gradient(circle at 95% 20%, rgba(255,255,255,0.45), transparent 22%),
            linear-gradient(135deg, #4f46e5 0%, #2563eb 45%, #14b8a6 100%);
        color: white;
        box-shadow: 0 25px 60px rgba(37,99,235,0.24);
        margin-bottom: 22px;
    }

    .vf-hero h1 {
        color: white;
        margin-bottom: 6px;
        font-size: 2.1rem;
    }

    .vf-hero p {
        color: rgba(255,255,255,0.86);
        font-size: 1rem;
        margin-bottom: 0;
    }

    .vf-section-title {
        padding: 8px 0 4px 0;
    }

    .vf-section-title h2 {
        font-size: 1.65rem;
        margin-bottom: 4px;
    }

    .vf-section-title p {
        color: #64748b;
        margin-top: 0;
    }
    </style>

<style>
/* Final admin polish */
div[data-testid="stVerticalBlockBorderWrapper"] {
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 22px 50px rgba(15,23,42,0.10) !important;
    border-color: rgba(99,102,241,0.28) !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg,#4f46e5 0%,#2563eb 100%) !important;
    color: white !important;
    border: none !important;
}

.stButton > button {
    min-height: 42px;
}

div[data-testid="stDataFrame"] {
    border-radius: 18px !important;
    overflow: hidden;
}

.vf-soft-note {
    background: rgba(255,255,255,0.72);
    border: 1px solid rgba(148,163,184,0.22);
    border-radius: 18px;
    padding: 16px 18px;
    box-shadow: 0 12px 28px rgba(15,23,42,0.05);
}
</style>


<div class="vf-hero">
    <h1>VisaForge Admin Dashboard</h1>
    <p>Manage applicants, scholarships, official sources, route rules, notifications, and platform health from one polished control center.</p>
</div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------

def _status_label(value: bool) -> str:
    return "Active" if value else "Inactive"


def _safe_freshness(value) -> str:
    return freshness_label(value) if value else "Never"


def _metric_card(
    title: str,
    value,
    caption: str | None = None,
    gradient: str = "linear-gradient(135deg,#4f46e5 0%,#2563eb 100%)",
):
    html = f"""
<div style="background:{gradient};padding:20px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(37,99,235,0.18);position:relative;overflow:hidden;min-height:125px;">
    <div style="position:absolute;right:-30px;top:-30px;width:140px;height:140px;background:rgba(255,255,255,0.10);border-radius:50%;"></div>
    <div style="font-size:0.95rem;opacity:0.9;font-weight:600;margin-bottom:14px;">{title}</div>
    <div style="font-size:2.45rem;font-weight:800;line-height:1;margin-bottom:12px;">{value}</div>
    <div style="font-size:0.92rem;opacity:0.85;">{caption or ""}</div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

def _section_intro(title: str, body: str):
    st.markdown(f"### {title}")
    st.caption(body)


def metric_card(title, value, subtitle, gradient):
    st.markdown(
        f"""
<div style="background:{gradient};padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(37,99,235,0.18);position:relative;overflow:hidden;min-height:125px;">
    <div style="position:absolute;right:-25px;top:-25px;width:120px;height:120px;background:rgba(255,255,255,0.10);border-radius:50%;"></div>
    <div style="font-size:0.92rem;font-weight:800;opacity:0.92;">{title}</div>
    <div style="font-size:3rem;font-weight:900;margin-top:12px;line-height:1;">{value}</div>
    <div style="font-size:0.92rem;opacity:0.9;margin-top:10px;">{subtitle}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def pill(text, bg, color):
    return f"<span style='background:{bg};color:{color};padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;display:inline-block;'>{text}</span>"


def soft_button(url, label="Open Website"):
    return f"<a href='{url}' target='_blank' style='display:inline-block;background:#eef2ff;color:#2563eb;border:1px solid #bfdbfe;border-radius:999px;padding:10px 16px;font-weight:800;text-decoration:none;box-shadow:0 8px 18px rgba(37,99,235,0.08);'>Open Website</a>"


def _human_source_status(status: str | None) -> str:
    if not status:
        return "Not refreshed yet"
    return {
        "success": "Healthy",
        "partial": "Partially Updated",
        "failed": "Needs Attention",
    }.get(status, status.title())


def _campaign_audience_label(key: str) -> str:
    return {
        "all": "All applicants",
        "incomplete_journey": "Applicants with incomplete journeys",
        "destination_country": "Applicants by destination country",
        "selected_scholarship": "Applicants with selected scholarships",
        "documents_started": "Applicants who started documents",
    }.get(key, key)


def _email_type_label(key: str) -> str:
    return {
        "journey_reminder": "Journey reminder",
        "platform_tip": "Platform tip",
        "destination_insight": "Destination insight",
        "scholarship_insight": "Scholarship insight",
        "important_notice": "Important notice",
    }.get(key, key)


# ---------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------

sections = [
    "User Analytics",
    "Scholarship Reviews",
    "Official Sources",
    "Trusted Sources",
    "Scholarship Library",
    "Visa Routes & Rules",
    "Send Notifications",
]

tab_labels = [
    ("User Analytics", "\U0001F4CA User Analytics"),
    ("Scholarship Reviews", "\U0001F393 Scholarship Reviews"),
    ("Official Sources", "\U0001F310 Official Sources"),
    ("Trusted Sources", "\U0001F6E1\U0000FE0F Trusted Sources"),
    ("Scholarship Library", "\U0001F4DA Scholarship Library"),
    ("Visa Routes & Rules", "\U0001F6C2 Visa Routes & Rules"),
    ("Send Notifications", "\U0001F4E2 Send Notifications"),
]

if is_super_admin():
    sections.append("Account Management")
    tab_labels.append(("Account Management", "\U0001F451 Account Management"))

sections.append("Logs")
tab_labels.append(("Logs", "\U0001F4DC Logs"))

if "selected_admin_tab" not in st.session_state:
    st.session_state.selected_admin_tab = "User Analytics"

if st.session_state.selected_admin_tab not in sections:
    st.session_state.selected_admin_tab = "User Analytics"

control_role = "Super Admin" if is_super_admin() else "Admin"

st.markdown(
    """
    <style>
    .vf-control-panel {
        background:
            radial-gradient(circle at top right, rgba(37,99,235,0.12), transparent 32%),
            radial-gradient(circle at bottom left, rgba(124,58,237,0.10), transparent 28%),
            linear-gradient(135deg, rgba(255,255,255,0.98), rgba(248,250,252,0.97));
        border: 1px solid rgba(148,163,184,0.28);
        border-radius: 28px;
        padding: 24px 24px 18px 24px;
        box-shadow: 0 24px 60px rgba(15,23,42,0.07);
        margin-bottom: 24px;
    }

    .vf-control-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 18px;
        margin-bottom: 18px;
        padding-bottom: 16px;
        border-bottom: 1px solid rgba(148,163,184,0.18);
    }

    .vf-control-title {
        font-size: 1.35rem;
        font-weight: 950;
        color: #0f172a;
        letter-spacing: -0.03em;
        margin-bottom: 5px;
    }

    .vf-control-subtitle {
        color: #64748b;
        font-size: 0.93rem;
        line-height: 1.55;
    }

    .vf-control-pill {
        background: linear-gradient(135deg,#2563eb,#7c3aed);
        color: white;
        border-radius: 999px;
        padding: 8px 13px;
        font-size: 0.78rem;
        font-weight: 900;
        white-space: nowrap;
        box-shadow: 0 14px 30px rgba(37,99,235,0.20);
    }

    div[data-testid="stButton"] > button {
        min-height: 58px !important;
        border-radius: 18px !important;
        border: 1px solid rgba(148,163,184,0.28) !important;
        background: rgba(255,255,255,0.96) !important;
        color: #0f172a !important;
        font-weight: 900 !important;
        box-shadow: 0 14px 32px rgba(15,23,42,0.055) !important;
        transition: all 0.16s ease !important;
        white-space: nowrap !important;
        text-align: center !important;
    }

    div[data-testid="stButton"] > button:hover {
        transform: translateY(-1px) !important;
        border-color: rgba(37,99,235,0.42) !important;
        box-shadow: 0 18px 40px rgba(37,99,235,0.12) !important;
        background: linear-gradient(135deg, rgba(239,246,255,0.98), rgba(245,243,255,0.98)) !important;
    }
    .vf-admin-active-control {
        min-height: 58px;
        border-radius: 18px;
        border: 1px solid rgba(34,197,94,0.34);
        background:
            radial-gradient(circle at top right, rgba(34,197,94,0.13), transparent 34%),
            linear-gradient(135deg, rgba(236,253,245,0.98), rgba(255,255,255,0.98));
        color: #0f172a;
        font-weight: 950;
        box-shadow: 0 18px 40px rgba(34,197,94,0.13);
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 0 16px;
        white-space: nowrap;
    }

    .vf-admin-active-capsule {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 34px;
        height: 26px;
        border-radius: 999px;
        background: rgba(34,197,94,0.16);
        border: 1px solid rgba(34,197,94,0.32);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.55);
        flex: 0 0 auto;
    }

    .vf-admin-active-light {
        width: 10px;
        height: 10px;
        border-radius: 999px;
        background: #22c55e;
        box-shadow: 0 0 0 4px rgba(34,197,94,0.16), 0 0 18px rgba(34,197,94,0.42);
        display: inline-block;
    }

    .vf-admin-active-label {
        overflow: hidden;
        text-overflow: ellipsis;
        font-size: 0.96rem;
        line-height: 1.2;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="vf-control-panel">
        <div class="vf-control-head">
            <div>
                <div class="vf-control-title">Admin Control Center</div>
                <div class="vf-control-subtitle">
                    Choose a management area below. Super admin tools are shown only to authorised accounts.
                </div>
            </div>
            <div class="vf-control-pill">{control_role}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 3-column grid keeps the control center balanced even with super-admin tools.
for row_start in range(0, len(tab_labels), 3):
    row_items = tab_labels[row_start:row_start + 3]
    row = st.columns(3)

    for idx, (section_key, label) in enumerate(row_items):
        with row[idx]:
            active = st.session_state.selected_admin_tab == section_key

            if active:
                st.markdown(
                    f"""
                    <div class="vf-admin-active-control">
                        <span class="vf-admin-active-capsule">
                            <span class="vf-admin-active-light"></span>
                        </span>
                        <span class="vf-admin-active-label">{label}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                if st.button(
                    label,
                    key=f"tab_{row_start + idx}",
                    use_container_width=True,
                ):
                    st.session_state.selected_admin_tab = section_key
                    st.rerun()

selected_section = st.session_state.selected_admin_tab

st.divider()


# ---------------------------------------------------------------------
# 1. User Analytics
# ---------------------------------------------------------------------

if selected_section == "User Analytics":
    _section_intro(
        "Platform Overview",
        "Understand applicant progress, journey completion, risk alerts, and country demand at a glance.",
    )

    stats = get_user_funnel_stats()
    total_users = stats.get("total_users", 0) or 0

    st.markdown(
        f"""
<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin-top:18px;margin-bottom:32px;">
    <div style="background:linear-gradient(135deg,#4f46e5 0%,#2563eb 100%);padding:20px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(37,99,235,0.18);min-height:125px;position:relative;overflow:hidden;">
        <div style="font-size:0.92rem;font-weight:700;opacity:0.9;">Total Applicants</div>
        <div style="font-size:2.45rem;font-weight:850;margin-top:12px;">{total_users}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Registered applicants</div>
    </div>
    <div style="background:linear-gradient(135deg,#7c3aed 0%,#6366f1 100%);padding:20px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(99,102,241,0.18);min-height:125px;position:relative;overflow:hidden;">
        <div style="font-size:0.92rem;font-weight:700;opacity:0.9;">Profiles Complete</div>
        <div style="font-size:2.45rem;font-weight:850;margin-top:12px;">{stats.get("profile_complete", 0)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Completed profile setup</div>
    </div>
    <div style="background:linear-gradient(135deg,#06b6d4 0%,#14b8a6 100%);padding:20px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(20,184,166,0.18);min-height:125px;position:relative;overflow:hidden;">
        <div style="font-size:0.92rem;font-weight:700;opacity:0.9;">Routes Generated</div>
        <div style="font-size:2.45rem;font-weight:850;margin-top:12px;">{stats.get("route_generated", 0)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Active route plans</div>
    </div>
    <div style="background:linear-gradient(135deg,#f97316 0%,#fb7185 100%);padding:20px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(249,115,22,0.18);min-height:125px;position:relative;overflow:hidden;">
        <div style="font-size:0.92rem;font-weight:700;opacity:0.9;">Document Vault</div>
        <div style="font-size:2.45rem;font-weight:850;margin-top:12px;">{stats.get("documents_started", 0)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Optional document support</div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    funnel_steps = [
        ("Profile Complete", stats.get("profile_complete", 0)),
        ("Eligibility Complete", stats.get("eligibility_completed", 0)),
        ("Scholarship Selected", stats.get("scholarship_selected", 0)),
        ("Route Generated", stats.get("route_generated", 0)),
        ("Document Vault", stats.get("documents_started", 0)),
        ("Completed", stats.get("completed", 0)),
    ]

    # --- Additional admin analytics charts --------------------------------
    rows_for_charts = get_user_progress_table()

    if rows_for_charts:
        all_chart_df = pd.DataFrame(rows_for_charts)
        country_options = ["All"] + sorted(
            [
                x for x in all_chart_df["Destination"]
                .fillna("Not Selected")
                .replace("", "Not Selected")
                .unique()
                .tolist()
            ]
        )

        selected_country = st.selectbox(
            "Filter applicants by country",
            country_options,
            key="admin_user_country_filter",
        )

        if selected_country != "All":
            rows_for_charts = [
                r for r in rows_for_charts
                if (r.get("Destination") or "Not Selected") == selected_country
            ]

        chart_df = pd.DataFrame(rows_for_charts)

        destination_counts = (
            chart_df["Destination"]
            .fillna("Not Selected")
            .replace("", "Not Selected")
            .value_counts()
            .to_dict()
        )

        completion_values = pd.to_numeric(
            chart_df["Completion %"],
            errors="coerce"
        ).fillna(0)

        completion_bins = {
            "0-25%": int(((completion_values >= 0) & (completion_values <= 25)).sum()),
            "26-50%": int(((completion_values > 25) & (completion_values <= 50)).sum()),
            "51-75%": int(((completion_values > 50) & (completion_values <= 75)).sum()),
            "76-100%": int(((completion_values > 75) & (completion_values <= 100)).sum()),
        }

        stage_order = [
            "Not Started",
            "Profile Complete",
            "Eligibility Complete",
            "Scholarship Selected",
            "Route Generated",
            "Document Vault",
            "Completed",
        ]
        stage_counts = chart_df["Journey Stage"].fillna("Not Started").replace("", "Not Started").value_counts().to_dict()
        stage_distribution = {stage: int(stage_counts.get(stage, 0)) for stage in stage_order}

        max_dest = max(destination_counts.values()) if destination_counts else 1
        max_completion = max(completion_bins.values()) if completion_bins else 1

        stage_colors = {
            "Not Started": "#64748b",
            "Profile Complete": "#6366f1",
            "Eligibility Complete": "#06b6d4",
            "Scholarship Selected": "#8b5cf6",
            "Route Generated": "#2563eb",
            "Document Vault": "#f59e0b",
            "Completed": "#16a34a",
        }

        chart_html = f"""
<div style="display:grid;grid-template-columns:minmax(0,1.2fr) minmax(360px,.8fr);gap:22px;margin:26px 0 18px 0;align-items:stretch;">

    <div style="background:rgba(255,255,255,.92);border:1px solid rgba(148,163,184,.22);border-radius:28px;padding:28px;box-shadow:0 22px 55px rgba(15,23,42,.075);">
        <div style="font-size:1.25rem;font-weight:950;color:#0f172a;margin-bottom:4px;">Applicant Stage Mix</div>
        <div style="font-size:.9rem;color:#64748b;font-weight:650;margin-bottom:22px;">A quick visual split of where applicants currently stand.</div>

        <div style="display:grid;grid-template-columns:300px 1fr;gap:30px;align-items:center;">
            <div style="display:flex;align-items:center;justify-content:center;">
                <div style="position:relative;width:260px;height:260px;border-radius:50%;background:conic-gradient(
"""

        total_stage = sum(stage_distribution.values()) or 1
        start_pct = 0
        conic_parts = []

        for stage, count in stage_distribution.items():
            pct = (count / total_stage) * 100
            color = stage_colors.get(stage, "#2563eb")
            conic_parts.append(f"{color} {start_pct:.1f}% {start_pct + pct:.1f}%")
            start_pct += pct

        chart_html += ", ".join(conic_parts) if conic_parts else "#e2e8f0 0% 100%"
        chart_html += """);box-shadow:0 24px 55px rgba(37,99,235,.16);">
                    <div style="position:absolute;inset:42px;background:linear-gradient(135deg,#ffffff,#f8fbff);border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;border:1px solid rgba(191,219,254,.9);box-shadow:inset 0 2px 12px rgba(255,255,255,.8),0 12px 28px rgba(15,23,42,.08);">
                        <div style="font-size:3.5rem;font-weight:950;line-height:1;background:linear-gradient(135deg,#2563eb,#14b8a6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">""" + str(total_stage) + """</div>
                        <div style="font-size:.82rem;font-weight:950;color:#64748b;text-transform:uppercase;letter-spacing:.16em;margin-top:8px;">Applicants</div>
                        <div style="width:62px;height:6px;border-radius:999px;background:linear-gradient(90deg,#2563eb,#14b8a6);margin-top:12px;"></div>
                    </div>
                </div>
            </div>

            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:22px;padding:18px 20px;display:flex;flex-direction:column;gap:11px;">
"""

        for stage, count in stage_distribution.items():
            pct = round((count / total_stage) * 100, 1)
            color = stage_colors.get(stage, "#2563eb")
            chart_html += f"""
                <div style="display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;">
                    <div style="display:flex;align-items:center;gap:10px;min-width:0;">
                        <span style="width:11px;height:11px;border-radius:50%;background:{color};display:inline-block;flex-shrink:0;"></span>
                        <span style="font-size:.9rem;font-weight:850;color:#334155;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{stage}</span>
                    </div>
                    <span style="font-size:.9rem;font-weight:950;color:#0f172a;white-space:nowrap;">{count} ? {pct}%</span>
                </div>
"""

        chart_html += """
            </div>
        </div>
    </div>

    <div style="background:rgba(255,255,255,.92);border:1px solid rgba(148,163,184,.22);border-radius:28px;padding:28px;box-shadow:0 22px 55px rgba(15,23,42,.075);">
        <div style="font-size:1.25rem;font-weight:950;color:#0f172a;margin-bottom:4px;">Completion Distribution</div>
        <div style="font-size:.9rem;color:#64748b;font-weight:650;margin-bottom:24px;">Shows how far applicants have progressed overall.</div>
"""

        for label, count in completion_bins.items():
            pct = round((count / max_completion) * 100, 1) if max_completion else 0
            chart_html += f"""
        <div style="margin-bottom:18px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:.9rem;font-weight:900;color:#334155;">{label}</span>
                <span style="font-size:.9rem;font-weight:950;color:#0f172a;">{count}</span>
            </div>
            <div style="height:13px;background:#e2e8f0;border-radius:999px;overflow:hidden;">
                <div style="height:13px;width:{pct}%;background:linear-gradient(90deg,#2563eb,#14b8a6);border-radius:999px;"></div>
            </div>
        </div>
"""

        chart_html += """
    </div>
</div>

<div style="background:rgba(255,255,255,.92);border:1px solid rgba(148,163,184,.22);border-radius:28px;padding:26px 28px;box-shadow:0 22px 55px rgba(15,23,42,.075);margin:0 0 18px 0;">
    <div style="font-size:1.25rem;font-weight:950;color:#0f172a;margin-bottom:4px;">Applicants by Destination</div>
    <div style="font-size:.9rem;color:#64748b;font-weight:650;margin-bottom:20px;">Helps admins see country demand and where applicants are concentrating.</div>
"""

        for dest, count in destination_counts.items():
            pct = round((count / max_dest) * 100, 1) if max_dest else 0
            chart_html += f"""
    <div style="display:grid;grid-template-columns:180px 1fr 45px;gap:16px;align-items:center;margin-bottom:13px;">
        <div style="font-weight:900;color:#0f172a;">{dest}</div>
        <div style="height:15px;background:#e2e8f0;border-radius:999px;overflow:hidden;">
            <div style="height:15px;width:{pct}%;background:linear-gradient(90deg,#7c3aed,#2563eb,#14b8a6);border-radius:999px;"></div>
        </div>
        <div style="font-weight:950;color:#2563eb;text-align:right;">{count}</div>
    </div>
"""

        chart_html += """
</div>
"""

        components.html(chart_html, height=620, scrolling=False)

    st.markdown("#### Stage Distribution")

    stage_distribution = stats.get("stage_distribution", {})
    if stage_distribution:
        stage_html = "<div style='display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:24px;'>"

        stage_colors = {
            "Not Started": "#64748b",
            "Profile Complete": "#6366f1",
            "Eligibility Complete": "#06b6d4",
            "Scholarship Selected": "#8b5cf6",
            "Route Generated": "#2563eb",
            "Document Vault": "#f59e0b",
            "Completed": "#16a34a",
        }

        for stage, count in stage_distribution.items():
            pct = round((count / total_users) * 100, 1) if total_users else 0
            color = stage_colors.get(stage, "#2563eb")

            stage_html += (
                f"<div style='background:rgba(255,255,255,0.88);border:1px solid rgba(148,163,184,0.22);border-radius:22px;padding:18px;box-shadow:0 14px 32px rgba(15,23,42,0.06);'>"
                f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:12px;'>"
                f"<div style='width:12px;height:12px;border-radius:50%;background:{color};'></div>"
                f"<div style='font-weight:800;color:#0f172a;'>{stage}</div>"
                f"</div>"
                f"<div style='font-size:2rem;font-weight:850;color:#0f172a;'>{count}</div>"
                f"<div style='font-size:0.85rem;color:#64748b;margin-bottom:10px;'>{pct}% of applicants</div>"
                f"<div style='height:9px;background:#e2e8f0;border-radius:999px;overflow:hidden;'>"
                f"<div style='height:9px;width:{pct}%;background:{color};border-radius:999px;'></div>"
                f"</div>"
                f"</div>"
            )

        stage_html += "</div>"

        st.markdown(stage_html, unsafe_allow_html=True)

    # --- Production-grade admin insights ---------------------------------
    insight_rows = rows_for_charts

    if insight_rows:
        insight_df = pd.DataFrame(insight_rows)

        missing_destination = int(
            insight_df["Destination"].fillna("Not Selected").replace("", "Not Selected").eq("Not Selected").sum()
        )

        zero_progress = int(
            pd.to_numeric(insight_df["Completion %"], errors="coerce").fillna(0).eq(0).sum()
        )

        documents_started_count = stats.get("documents_started", 0) or 0
        documents_not_started = max(total_users - documents_started_count, 0)

        funnel_pairs = []
        for i in range(len(funnel_steps) - 1):
            current_label, current_count = funnel_steps[i]
            next_label, next_count = funnel_steps[i + 1]
            drop = max(current_count - next_count, 0)
            drop_pct = round((drop / current_count) * 100, 1) if current_count else 0
            funnel_pairs.append((current_label, next_label, drop, drop_pct))

        biggest_drop = max(funnel_pairs, key=lambda x: x[2]) if funnel_pairs else None
        recent_items = insight_rows[:4]

        st.markdown("#### Admin Intelligence")

        insight_html = f"""
<div style="margin:18px 0 30px 0;">

    <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:18px;">
        <div style="background:linear-gradient(135deg,#fff7ed,#ffffff);border:1px solid #fed7aa;border-radius:22px;padding:18px 20px;box-shadow:0 14px 34px rgba(15,23,42,.06);">
            <div style="font-size:.82rem;font-weight:950;color:#9a3412;text-transform:uppercase;letter-spacing:.05em;">Missing destination</div>
            <div style="font-size:2.1rem;font-weight:950;color:#0f172a;margin-top:8px;">{missing_destination}</div>
            <div style="font-size:.86rem;color:#64748b;font-weight:650;">Need country selection</div>
        </div>

        <div style="background:linear-gradient(135deg,#fef2f2,#ffffff);border:1px solid #fecaca;border-radius:22px;padding:18px 20px;box-shadow:0 14px 34px rgba(15,23,42,.06);">
            <div style="font-size:.82rem;font-weight:950;color:#991b1b;text-transform:uppercase;letter-spacing:.05em;">No progress yet</div>
            <div style="font-size:2.1rem;font-weight:950;color:#0f172a;margin-top:8px;">{zero_progress}</div>
            <div style="font-size:.86rem;color:#64748b;font-weight:650;">Still at 0% completion</div>
        </div>

        <div style="background:linear-gradient(135deg,#eff6ff,#ffffff);border:1px solid #bfdbfe;border-radius:22px;padding:18px 20px;box-shadow:0 14px 34px rgba(15,23,42,.06);">
            <div style="font-size:.82rem;font-weight:950;color:#1d4ed8;text-transform:uppercase;letter-spacing:.05em;">Documents optional</div>
            <div style="font-size:2.1rem;font-weight:950;color:#0f172a;margin-top:8px;">{documents_not_started}</div>
            <div style="font-size:.86rem;color:#64748b;font-weight:650;">Optional review feature</div>
        </div>
    </div>
"""

        if biggest_drop:
            from_stage, to_stage, drop, drop_pct = biggest_drop
            insight_html += f"""
    <div style="display:grid;grid-template-columns:1fr 1.25fr;gap:16px;">
        <div style="background:rgba(255,255,255,.92);border:1px solid rgba(148,163,184,.22);border-radius:24px;padding:22px;box-shadow:0 18px 42px rgba(15,23,42,.07);">
            <div style="font-size:1.1rem;font-weight:950;color:#0f172a;margin-bottom:6px;">Funnel Drop-off</div>
            <div style="font-size:.88rem;color:#64748b;font-weight:650;margin-bottom:18px;">Largest applicant loss point.</div>

            <div style="padding:18px;border-radius:20px;background:linear-gradient(135deg,#eef2ff,#ffffff);border:1px solid #bfdbfe;">
                <div style="font-size:.78rem;color:#64748b;font-weight:950;text-transform:uppercase;letter-spacing:.08em;">Biggest drop-off</div>
                <div style="font-size:1.15rem;font-weight:950;color:#0f172a;margin-top:8px;">{from_stage} → {to_stage}</div>
                <div style="display:flex;align-items:end;gap:10px;margin-top:12px;">
                    <div style="font-size:2.4rem;font-weight:950;color:#2563eb;line-height:1;">{drop}</div>
                    <div style="font-size:.9rem;color:#64748b;font-weight:750;margin-bottom:5px;">lost · {drop_pct}%</div>
                </div>
            </div>
        </div>
"""
        else:
            insight_html += """
    <div style="display:grid;grid-template-columns:1fr 1.25fr;gap:16px;">
        <div style="background:rgba(255,255,255,.92);border:1px solid rgba(148,163,184,.22);border-radius:24px;padding:22px;box-shadow:0 18px 42px rgba(15,23,42,.07);">
            <div style="font-size:1.1rem;font-weight:950;color:#0f172a;">No funnel drop-off yet</div>
            <div style="font-size:.88rem;color:#64748b;font-weight:650;margin-top:6px;">More applicant activity is needed.</div>
        </div>
"""

        insight_html += """
        <div style="background:rgba(255,255,255,.92);border:1px solid rgba(148,163,184,.22);border-radius:24px;padding:22px;box-shadow:0 18px 42px rgba(15,23,42,.07);">
            <div style="font-size:1.1rem;font-weight:950;color:#0f172a;margin-bottom:6px;">Recent Activity</div>
            <div style="font-size:.88rem;color:#64748b;font-weight:650;margin-bottom:14px;">Latest applicant journey positions.</div>
            <div style="display:flex;flex-direction:column;gap:10px;">
"""

        for item in recent_items:
            name = item.get("Name", "Unknown")
            email = item.get("Email", "")
            stage = item.get("Journey Stage", "Not Started")
            destination = item.get("Destination", "Not Selected")
            completion = item.get("Completion %", 0)

            insight_html += f"""
                <div style="display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center;border-radius:16px;padding:12px 14px;background:#f8fafc;border:1px solid #e2e8f0;">
                    <div>
                        <div style="font-weight:900;color:#0f172a;">{name}</div>
                        <div style="font-size:.8rem;color:#64748b;">{email} · {destination}</div>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:.8rem;font-weight:950;color:#2563eb;">{stage}</div>
                        <div style="font-size:.78rem;color:#64748b;font-weight:800;">{completion}%</div>
                    </div>
                </div>
"""

        insight_html += """
            </div>
        </div>
    </div>
</div>
"""

        components.html(insight_html, height=520, scrolling=False)
    st.markdown("#### Applicant Progress")

    st.markdown(
        """
        <style>
        .vf-applicant-search-title {
            font-size: 1rem;
            font-weight: 950;
            color: #0f172a;
            letter-spacing: -0.02em;
            margin-top: 8px;
            margin-bottom: 4px;
        }
        .vf-applicant-search-help {
            color: #64748b;
            font-size: 0.86rem;
            line-height: 1.5;
            margin-bottom: 8px;
        }
        div[data-testid="stTextInput"] input {
            min-height: 52px !important;
            border-radius: 16px !important;
            border: 1px solid rgba(37,99,235,0.24) !important;
            background: rgba(255,255,255,0.98) !important;
            font-size: 0.95rem !important;
            box-shadow: 0 10px 26px rgba(15,23,42,0.04) !important;
        }
        div[data-testid="stTextInput"] input:focus {
            border-color: #2563eb !important;
            box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important;
        }
        </style>
        <div class="vf-applicant-search-title">Applicant Search</div>
        <div class="vf-applicant-search-help">
            Start typing to filter applicants. Results update after a short pause.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st_keyup is not None:
        applicant_search_raw = st_keyup(
            "",
            placeholder="Search by name, email, country, stage, or status...",
            key="admin_user_analytics_applicant_search_live",
            label_visibility="collapsed",
            debounce=350,
        )
    else:
        applicant_search_raw = st.text_input(
            "",
            placeholder="Search by name, email, country, stage, or status...",
            key="admin_user_analytics_applicant_search",
            label_visibility="collapsed",
        )

    applicant_search = (applicant_search_raw or "").strip().lower()

    rows = rows_for_charts
    if applicant_search:
        rows = [
            row for row in rows
            if applicant_search in " ".join(
                str(row.get(field, ""))
                for field in [
                    "Name",
                    "Email",
                    "Destination",
                    "Journey Stage",
                    "Profile",
                    "Eligibility",
                    "Scholarship",
                    "Route Plan",
                ]
            ).lower()
        ]

    if rows:
        def _clean(value, fallback=""):
            if value is None:
                return fallback
            value = str(value).strip()
            return value if value else fallback

        def _status_class(value):
            value = _clean(value, "Pending").lower()
            if value in {"complete", "completed", "selected", "generated", "route generated"}:
                return "good"
            if value in {"eligibility complete", "profile complete", "scholarship selected"}:
                return "blue"
            if value in {"pending", "not selected"}:
                return "warn"
            if value in {"not started"}:
                return "muted"
            return "blue"

        table_rows = []
        for index, row in enumerate(rows, start=1):
            name = html.escape(_clean(row.get("Name"), "Unknown Applicant"))
            email = html.escape(_clean(row.get("Email"), "No email"))
            destination = html.escape(_clean(row.get("Destination"), "Not Selected"))
            stage = html.escape(_clean(row.get("Journey Stage"), "Not Started"))
            profile = html.escape(_clean(row.get("Profile"), "Pending"))
            eligibility = html.escape(_clean(row.get("Eligibility"), "Pending"))
            scholarship = html.escape(_clean(row.get("Scholarship"), "Pending"))
            route_plan = html.escape(_clean(row.get("Route Plan"), "Pending"))

            try:
                completion = int(float(row.get("Completion %", 0)))
            except Exception:
                completion = 0
            completion = max(0, min(100, completion))

            table_rows.append(
                f"""
                <tr>
                    <td class="rank-cell">{index:02d}</td>
                    <td>
                        <div class="applicant-name">{name}</div>
                        <div class="applicant-email">{email}</div>
                    </td>
                    <td><span class="destination-pill">{destination}</span></td>
                    <td>
                        <div class="progress-line">
                            <div class="progress-track">
                                <div class="progress-fill" style="width:{completion}%;"></div>
                            </div>
                            <span>{completion}%</span>
                        </div>
                    </td>
                    <td><span class="status-badge {_status_class(stage)}">{stage}</span></td>
                    <td><span class="status-badge {_status_class(profile)}">{profile}</span></td>
                    <td><span class="status-badge {_status_class(eligibility)}">{eligibility}</span></td>
                    <td><span class="status-badge {_status_class(scholarship)}">{scholarship}</span></td>
                    <td><span class="status-badge {_status_class(route_plan)}">{route_plan}</span></td>
                </tr>
                """
            )

        table_template = """
        <!doctype html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                    color: #0f172a;
                }
                .vf-applicant-table-card {
                    background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                    border: 1px solid rgba(148,163,184,0.28);
                    border-radius: 26px;
                    box-shadow: 0 22px 55px rgba(15,23,42,0.08);
                    padding: 22px;
                    overflow: hidden;
                }
                .vf-applicant-table-head {
                    display: flex;
                    justify-content: space-between;
                    gap: 18px;
                    align-items: flex-start;
                    margin-bottom: 18px;
                    padding-bottom: 16px;
                    border-bottom: 1px solid rgba(148,163,184,0.20);
                }
                .vf-applicant-table-title {
                    font-size: 1.15rem;
                    font-weight: 900;
                    color: #0f172a;
                    letter-spacing: -0.02em;
                }
                .vf-applicant-table-subtitle {
                    color: #64748b;
                    font-size: 0.9rem;
                    margin-top: 5px;
                }
                .vf-applicant-count {
                    background: linear-gradient(135deg,#2563eb,#7c3aed);
                    color: white;
                    border-radius: 999px;
                    padding: 8px 14px;
                    font-size: 0.82rem;
                    font-weight: 850;
                    white-space: nowrap;
                    box-shadow: 0 12px 28px rgba(37,99,235,0.22);
                }
                .vf-table-wrap {
                    overflow-x: auto;
                    border-radius: 18px;
                    border: 1px solid rgba(226,232,240,0.95);
                }
                .vf-applicant-table {
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 1080px;
                    background: white;
                }
                .vf-applicant-table th {
                    background: #f8fafc;
                    color: #475569;
                    font-size: 0.72rem;
                    text-transform: uppercase;
                    letter-spacing: 0.06em;
                    font-weight: 900;
                    text-align: left;
                    padding: 14px 14px;
                    border-bottom: 1px solid #e2e8f0;
                    white-space: nowrap;
                }
                .vf-applicant-table td {
                    padding: 14px;
                    border-bottom: 1px solid #eef2f7;
                    color: #0f172a;
                    font-size: 0.9rem;
                    vertical-align: middle;
                }
                .vf-applicant-table tr:hover td {
                    background: #f8fbff;
                }
                .rank-cell {
                    color: #94a3b8 !important;
                    font-weight: 900;
                    width: 56px;
                }
                .applicant-name {
                    font-weight: 900;
                    color: #0f172a;
                }
                .applicant-email {
                    margin-top: 3px;
                    color: #64748b;
                    font-size: 0.78rem;
                }
                .destination-pill {
                    display: inline-flex;
                    align-items: center;
                    border-radius: 999px;
                    padding: 7px 11px;
                    background: #eff6ff;
                    color: #1d4ed8;
                    border: 1px solid #bfdbfe;
                    font-weight: 850;
                    font-size: 0.78rem;
                    white-space: nowrap;
                }
                .progress-line {
                    display: grid;
                    grid-template-columns: minmax(110px,1fr) 42px;
                    gap: 10px;
                    align-items: center;
                    font-weight: 850;
                    color: #334155;
                    font-size: 0.8rem;
                }
                .progress-track {
                    height: 9px;
                    background: #e2e8f0;
                    border-radius: 999px;
                    overflow: hidden;
                }
                .progress-fill {
                    height: 100%;
                    background: linear-gradient(90deg,#2563eb,#7c3aed);
                    border-radius: 999px;
                }
                .status-badge {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 999px;
                    padding: 7px 11px;
                    font-size: 0.76rem;
                    font-weight: 900;
                    white-space: nowrap;
                    border: 1px solid transparent;
                }
                .status-badge.good {
                    background: #ecfdf5;
                    color: #047857;
                    border-color: #a7f3d0;
                }
                .status-badge.blue {
                    background: #eff6ff;
                    color: #1d4ed8;
                    border-color: #bfdbfe;
                }
                .status-badge.warn {
                    background: #fffbeb;
                    color: #b45309;
                    border-color: #fde68a;
                }
                .status-badge.muted {
                    background: #f1f5f9;
                    color: #64748b;
                    border-color: #e2e8f0;
                }
            </style>
        </head>
        <body>
            <div class="vf-applicant-table-card">
                <div class="vf-applicant-table-head">
                    <div>
                        <div class="vf-applicant-table-title">Applicant Progress Table</div>
                        <div class="vf-applicant-table-subtitle">Complete overview of all applicants, journey progress, and current workflow status.</div>
                    </div>
                    <div class="vf-applicant-count">__COUNT__ Applicants</div>
                </div>
                <div class="vf-table-wrap">
                    <table class="vf-applicant-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Applicant</th>
                                <th>Destination</th>
                                <th>Progress</th>
                                <th>Journey Stage</th>
                                <th>Profile</th>
                                <th>Eligibility</th>
                                <th>Scholarship</th>
                                <th>Route Plan</th>
                            </tr>
                        </thead>
                        <tbody>
                            __ROWS__
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """

        table_html = (
            table_template
            .replace("__COUNT__", str(len(rows)))
            .replace("__ROWS__", "".join(table_rows))
        )

        table_height = min(760, max(360, 170 + (len(rows) * 58)))
        components.html(table_html, height=table_height, scrolling=True)
    else:
        st.info("No applicant progress records available yet.")


# ---------------------------------------------------------------------
# 2. Scholarship Reviews
# ---------------------------------------------------------------------

elif selected_section == "Scholarship Reviews":
    _section_intro(
        "Scholarship Reviews",
        "Approve, reject, or flag scholarships before they appear to applicants.",
    )

    counts = review_status_counts()

    review_metric_html = f"""
<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin:18px 0 28px 0;">
    <div style="background:linear-gradient(135deg,#f59e0b 0%,#fb7185 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(245,158,11,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Pending Review</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{counts.get("pending_review", 0)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Waiting for admin decision</div>
    </div>

    <div style="background:linear-gradient(135deg,#16a34a 0%,#14b8a6 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(22,163,74,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Approved</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{counts.get("approved", 0)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Visible to applicants</div>
    </div>

    <div style="background:linear-gradient(135deg,#ea580c 0%,#f97316 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(234,88,12,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Needs Attention</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{counts.get("needs_attention", 0)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Requires deeper review</div>
    </div>

    <div style="background:linear-gradient(135deg,#64748b 0%,#334155 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(51,65,85,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Rejected</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{counts.get("rejected", 0)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Hidden from applicants</div>
    </div>
</div>
"""
    components.html(review_metric_html, height=170, scrolling=False)

    review_filter = st.selectbox(
        "Review list",
        ["pending_review", "needs_attention", "approved", "rejected"],
        format_func=lambda x: x.replace("_", " ").title(),
    )

    rows = list_by_review_status(review_filter, limit=200)

    if not rows:
        st.info(f"No scholarships found in {review_filter.replace('_', ' ').title()}.")
    else:
        for r in rows:
            with st.container(border=True):
                left, right = st.columns([3.2, 1.25])

                with left:
                    st.markdown(f"#### {r.title}")
                    st.caption(
                        " Â· ".join(
                            str(x)
                            for x in [
                                r.provider or "Unknown provider",
                                r.country or "Unknown country",
                                r.degree_level or "Any degree level",
                            ]
                            if x
                        )
                    )

                    if r.summary:
                        st.write(r.summary)

                    if r.source_url:
                        st.markdown(f"[Open official source]({r.source_url})")

                with right:
                    status = review_filter.replace("_", " ").title()
                    status_colors = {
                        "Pending Review": "#f59e0b",
                        "Approved": "#16a34a",
                        "Needs Attention": "#ea580c",
                        "Rejected": "#dc2626",
                    }
                    status_color = status_colors.get(status, "#64748b")

                    st.markdown(
                        f"""
<div style="background:rgba(255,255,255,0.82);border:1px solid rgba(148,163,184,0.22);border-radius:20px;padding:16px;box-shadow:0 12px 28px rgba(15,23,42,0.06);margin-bottom:14px;">
    <div style="display:inline-block;background:{status_color}18;color:{status_color};border:1px solid {status_color}55;border-radius:999px;padding:7px 12px;font-size:0.82rem;font-weight:850;margin-bottom:12px;">
        {status}
    </div>
    <div style="font-size:0.82rem;color:#64748b;font-weight:700;margin-bottom:10px;">
        Fetched: {_safe_freshness(r.fetched_at)}
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <span style="background:#eef2ff;color:#4338ca;padding:5px 10px;border-radius:999px;font-size:0.72rem;font-weight:800;">{r.country or "Unknown"}</span>
        <span style="background:#ecfeff;color:#0f766e;padding:5px 10px;border-radius:999px;font-size:0.72rem;font-weight:800;">{r.degree_level or "Any level"}</span>
        <span style="background:#f8fafc;color:#475569;padding:5px 10px;border-radius:999px;font-size:0.72rem;font-weight:800;">Review Item</span>
    </div>
</div>
""",
                        unsafe_allow_html=True,
                    )

                    if r.id is not None:
                        if review_filter != "approved":
                            if st.button("Approve", key=f"approve_{r.id}", type="primary", use_container_width=True):
                                set_review_status(r.id, "approved")
                                st.rerun()

                        if review_filter != "needs_attention":
                            if st.button("Needs Review", key=f"attention_{r.id}", use_container_width=True):
                                set_review_status(r.id, "needs_attention")
                                st.rerun()

                        if review_filter != "rejected":
                            if st.button("Reject", key=f"reject_{r.id}", use_container_width=True):
                                set_review_status(r.id, "rejected")
                                st.rerun()

                        if review_filter != "pending_review":
                            if st.button("Move to Pending", key=f"pending_{r.id}", use_container_width=True):
                                set_review_status(r.id, "pending_review")
                                st.rerun()


# ---------------------------------------------------------------------
# 3. Official Sources
# ---------------------------------------------------------------------

elif selected_section == "Official Sources":
    _section_intro(
        "Official Sources",
        "Manage sources used for scholarship and policy updates. Keep active sources refreshed and healthy.",
    )

    top_left, top_right = st.columns([3, 1])

    with top_left:
        country_filter = st.selectbox(
            "Country",
            ["All"] + list(settings.SUPPORTED_COUNTRIES),
        )

    with top_right:
        if st.button("+ Add Source", type="primary", use_container_width=True):
            st.session_state["show_add_source_form"] = not st.session_state.get("show_add_source_form", False)

    if st.session_state.get("show_add_source_form", False):
        with st.container(border=True):
            st.markdown("#### Add Official Source")
            with st.form("add_source_form"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Source name")
                url = c2.text_input("Website URL")

                c3, c4, c5 = st.columns(3)
                country = c3.selectbox("Country", list(settings.SUPPORTED_COUNTRIES))
                category = c4.selectbox(
                    "Purpose",
                    ["scholarship", "policy", "guidance"],
                    format_func=lambda x: {
                        "scholarship": "Scholarships",
                        "policy": "Visa / Policy Rules",
                        "guidance": "Student Guidance",
                    }.get(x, x),
                )
                credibility = c5.selectbox(
                    "Trust level",
                    ["official", "institutional", "informational"],
                    format_func=lambda x: x.title(),
                )

                submitted = st.form_submit_button("Save Source", type="primary")

                if submitted:
                    if not name.strip() or not url.strip():
                        st.error("Source name and website URL are required.")
                    else:
                        sid = add_source(
                            SourceConfig(
                                name=name.strip(),
                                url=url.strip(),
                                country=country,
                                category=category,
                                credibility=credibility,
                            )
                        )
                        st.success(f"Source saved successfully.")
                        st.session_state["show_add_source_form"] = False
                        st.rerun()

    sources = list_sources(
        country=None if country_filter == "All" else country_filter
    )

    a1, a2, a3 = st.columns(3)
    metric_html = f"""
<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:18px 0 28px 0;">
    <div style="background:linear-gradient(135deg,#4f46e5 0%,#2563eb 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(37,99,235,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Total Sources</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{len(sources)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Registered official sources</div>
    </div>

    <div style="background:linear-gradient(135deg,#06b6d4 0%,#14b8a6 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(20,184,166,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Active Sources</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{sum(1 for s in sources if s.active)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Currently enabled sources</div>
    </div>

    <div style="background:linear-gradient(135deg,#f97316 0%,#fb7185 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(249,115,22,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Needs Attention</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{sum(1 for s in sources if s.last_status == "failed")}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Sources with failed refreshes</div>
    </div>
</div>
"""
    components.html(metric_html, height=170, scrolling=False)

    st.markdown("#### Source Health")

    if st.button("Refresh Sources", type="primary"):
        with st.spinner("Refreshing official sources..."):
            results = refresh_sources(
                country=None if country_filter == "All" else country_filter
            )

        success_count = sum(1 for r in results if r.get("ok"))
        failed_count = len(results) - success_count
        st.success(f"Refresh completed. {success_count} succeeded, {failed_count} need attention.")

        with st.expander("Advanced refresh details"):
            st.json(results, expanded=False)

        st.rerun()

    if not sources:
        st.info("No official sources found.")
    else:
        for s in sources:
            with st.container(border=True):
                left, right = st.columns([3.2, 1.25])

                with left:
                    st.markdown(f"#### {s.name}")
                    st.caption(
                        f"{s.country} Â· {s.category.title()} Â· {s.credibility.title()} Â· {_human_source_status(s.last_status)}"
                    )
                    st.markdown(
                        f"<a href='"+s.url+"' target='_blank' style='display:inline-block;background:#eef2ff;color:#2563eb;border:1px solid #bfdbfe;border-radius:999px;padding:8px 13px;font-weight:800;text-decoration:none;margin-top:4px;'>Open Source</a>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"Last refreshed: {_safe_freshness(s.last_fetched_at)}")

                with right:
                    active_color = "#16a34a" if s.active else "#64748b"
                    st.markdown(
                        f"""
<div style="background:rgba(255,255,255,0.82);border:1px solid rgba(148,163,184,0.22);border-radius:20px;padding:16px;box-shadow:0 12px 28px rgba(15,23,42,0.06);margin-bottom:14px;">
    <div style="font-size:0.78rem;color:#64748b;font-weight:800;text-transform:uppercase;margin-bottom:8px;">Source Status</div>
    <div style="display:inline-block;background:{active_color}18;color:{active_color};border:1px solid {active_color}55;border-radius:999px;padding:7px 12px;font-size:0.82rem;font-weight:850;">
        {_status_label(s.active)}
    </div>
</div>
""",
                        unsafe_allow_html=True,
                    )

                    if st.button(
                        "Refresh Source",
                        key=f"refresh_source_{s.id}",
                        use_container_width=True,
                    ):
                        with st.spinner("Refreshing source..."):
                            result = refresh_source(s.id)

                        if result.get("ok"):
                            st.success("Source refreshed successfully.")
                        else:
                            st.error("Source refresh failed.")

                        with st.expander("Advanced refresh details"):
                            st.json(result, expanded=False)

                    if st.button(
                        "Deactivate" if s.active else "Activate",
                        key=f"toggle_source_{s.id}",
                        use_container_width=True,
                    ):
                        set_source_active(s.id, not s.active)
                        st.rerun()


# ---------------------------------------------------------------------
# 4. Trusted Sources
# ---------------------------------------------------------------------

elif selected_section == "Trusted Sources":
    _section_intro(
        "Trusted Sources",
        "Manage the curated source registry used for safer, controlled scholarship and policy refreshes.",
    )

    st.markdown(
        """
        <style>
        div[data-testid="stExpander"] {
            border: 1px solid rgba(148,163,184,0.30) !important;
            border-radius: 24px !important;
            overflow: hidden !important;
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96)) !important;
            box-shadow: 0 18px 46px rgba(15,23,42,0.07) !important;
        }
        div[data-testid="stExpander"] summary {
            padding: 18px 22px !important;
            background:
                radial-gradient(circle at top right, rgba(124,58,237,0.12), transparent 32%),
                linear-gradient(135deg, rgba(239,246,255,0.95), rgba(245,243,255,0.95)) !important;
            font-weight: 900 !important;
            color: #0f172a !important;
            letter-spacing: -0.01em !important;
        }
        div[data-testid="stExpander"] summary:hover {
            background:
                radial-gradient(circle at top right, rgba(124,58,237,0.16), transparent 34%),
                linear-gradient(135deg, rgba(219,234,254,0.98), rgba(237,233,254,0.98)) !important;
        }
        .vf-trusted-form-note {
            background: linear-gradient(135deg, rgba(37,99,235,0.10), rgba(124,58,237,0.09));
            border: 1px solid rgba(96,165,250,0.26);
            border-radius: 18px;
            padding: 14px 16px;
            color: #334155;
            font-weight: 750;
            line-height: 1.6;
            margin: 6px 0 18px 0;
        }
        .vf-trusted-form-note strong {
            color: #1d4ed8;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def _list_from_text(value: str) -> list[str]:
        if not value:
            return []
        raw_items = []
        for line in value.replace(",", "\n").splitlines():
            item = line.strip()
            if item:
                raw_items.append(item)
        return raw_items

    def _list_to_text(items: list[str]) -> str:
        return "\n".join(str(item) for item in (items or []))

    def _source_payload(
        *,
        name: str,
        provider: str,
        destination_country: str,
        base_url: str,
        start_urls_text: str,
        allowed_domains_text: str,
        follow_keywords_text: str,
        block_keywords_text: str,
        max_depth: int,
        source_type: str,
        is_active: bool,
        requires_admin_review: bool,
    ) -> dict:
        return {
            "name": name.strip(),
            "provider": provider.strip(),
            "destination_country": destination_country.strip(),
            "base_url": base_url.strip(),
            "start_urls": _list_from_text(start_urls_text),
            "allowed_domains": _list_from_text(allowed_domains_text),
            "follow_keywords": _list_from_text(follow_keywords_text),
            "block_keywords": _list_from_text(block_keywords_text),
            "max_depth": int(max_depth or 2),
            "source_type": source_type,
            "is_active": bool(is_active),
            "requires_admin_review": bool(requires_admin_review),
        }

    country_options = list(settings.SUPPORTED_COUNTRIES)
    if not country_options:
        country_options = ["UK", "Canada", "Germany", "Australia", "Hungary"]

    source_type_options = [
        "scholarship_program",
        "government_portal",
        "university_portal",
        "policy_source",
        "general",
    ]

    action_col1, action_col2, action_col3 = st.columns([1.2, 1.1, 2.7])

    with action_col1:
        if st.button("Sync Trusted Source Registry", type="primary", use_container_width=True):
            n = seed_from_json()
            st.success(f"Trusted source registry synced. {n} source record(s) updated from the saved registry.")
            st.rerun()

    with action_col2:
        only_active = st.toggle("Active only", value=False)

    with action_col3:
        st.caption(
            "Use Sync for saved registry records. Use Add/Edit below when an admin needs to manage trusted sources directly."
        )

    sources = list_curated_sources(active_only=only_active)

    with st.expander("Add New Trusted Source", expanded=False):
        st.markdown(
            """
            <div class="vf-trusted-form-note">
                <strong>Add a curated source</strong><br>
                Use this form for official government, university, or recognised scholarship sources.
                Keep the source information clear so future admins can understand why it is trusted.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <style>
            .vf-form-section-title {
                font-size: 0.92rem;
                font-weight: 950;
                color: #1e3a8a;
                margin: 18px 0 8px 0;
                letter-spacing: 0.02em;
                text-transform: uppercase;
            }
            .vf-form-help {
                color: #64748b;
                font-size: 0.86rem;
                line-height: 1.5;
                margin-bottom: 12px;
            }
            div[data-testid="stTextInput"] input,
            div[data-baseweb="select"] > div {
                min-height: 52px !important;
                border-radius: 14px !important;
            }
            div[data-testid="stTextArea"] textarea {
                min-height: 118px !important;
                border-radius: 14px !important;
            }
            div[data-testid="stNumberInput"] input {
                min-height: 52px !important;
                border-radius: 14px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="vf-form-section-title">Basic Source Details</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="vf-form-help">Add the public-facing identity of the trusted source.</div>',
            unsafe_allow_html=True,
        )

        basic_1, basic_2 = st.columns(2)
        with basic_1:
            add_name = st.text_input(
                "Source name",
                placeholder="Example: Chevening Scholarships",
                key="trusted_add_name",
            )
        with basic_2:
            add_provider = st.text_input(
                "Provider",
                placeholder="Example: UK Government",
                key="trusted_add_provider",
            )

        basic_3, basic_4 = st.columns(2)
        with basic_3:
            add_country = st.selectbox(
                "Destination country",
                country_options,
                key="trusted_add_country",
            )
        with basic_4:
            add_source_type = st.selectbox(
                "Source type",
                source_type_options,
                format_func=lambda x: x.replace("_", " ").title(),
                key="trusted_add_source_type",
            )

        add_base_url = st.text_input(
            "Main source URL",
            placeholder="https://www.example.gov/scholarships",
            key="trusted_add_base_url",
        )

        st.markdown('<div class="vf-form-section-title">Crawler Guidance</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="vf-form-help">Tell VisaForge where it can start, which domains are safe, and which pages should be prioritised or avoided.</div>',
            unsafe_allow_html=True,
        )

        crawl_1, crawl_2 = st.columns(2)
        with crawl_1:
            add_start_urls = st.text_area(
                "Starting page(s)",
                placeholder="One URL per line",
                height=118,
                key="trusted_add_start_urls",
            )
        with crawl_2:
            add_allowed_domains = st.text_area(
                "Allowed domain(s)",
                placeholder="example.gov\nwww.example.gov",
                height=118,
                key="trusted_add_allowed_domains",
            )

        crawl_3, crawl_4 = st.columns(2)
        with crawl_3:
            add_follow_keywords = st.text_area(
                "Pages to prioritise",
                placeholder="scholarship\nstudy\ninternational",
                height=118,
                key="trusted_add_follow_keywords",
            )
        with crawl_4:
            add_block_keywords = st.text_area(
                "Pages to avoid",
                placeholder="privacy\ncookies\nnews\npress",
                height=118,
                key="trusted_add_block_keywords",
            )

        st.markdown('<div class="vf-form-section-title">Source Controls</div>', unsafe_allow_html=True)

        add_opt1, add_opt2, add_opt3 = st.columns(3)
        with add_opt1:
            add_max_depth = st.number_input(
                "Crawler depth",
                min_value=1,
                max_value=5,
                value=2,
                step=1,
                key="trusted_add_max_depth",
            )
        with add_opt2:
            add_is_active = st.checkbox(
                "Source is active",
                value=True,
                key="trusted_add_is_active",
            )
        with add_opt3:
            add_requires_review = st.checkbox(
                "Requires admin review",
                value=True,
                key="trusted_add_requires_review",
            )

        if st.button("Save Trusted Source", type="primary", use_container_width=True):
            if not add_name.strip() or not add_country.strip() or not add_base_url.strip():
                st.error("Source name, destination country, and main source URL are required.")
            else:
                payload = _source_payload(
                    name=add_name,
                    provider=add_provider,
                    destination_country=add_country,
                    base_url=add_base_url,
                    start_urls_text=add_start_urls or add_base_url,
                    allowed_domains_text=add_allowed_domains,
                    follow_keywords_text=add_follow_keywords,
                    block_keywords_text=add_block_keywords,
                    max_depth=add_max_depth,
                    source_type=add_source_type,
                    is_active=add_is_active,
                    requires_admin_review=add_requires_review,
                )
                try:
                    source_id = upsert_curated_source(payload)
                    st.success(f"Trusted source saved successfully. Source ID: {source_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save trusted source: {exc}")

    if not sources:
        st.info("No trusted sources are available yet. Sync the trusted source registry or add a trusted source manually.")
    else:
        st.markdown("#### Trusted Source Registry")

        active_count = sum(1 for s in sources if s.is_active)
        countries_count = len(set(s.destination_country for s in sources if s.destination_country))
        program_count = sum(1 for s in sources if (s.source_type or "").lower() == "scholarship_program")

        m1, m2, m3 = st.columns(3)
        with m1:
            _metric_card("Active Sources", active_count, "Currently enabled")
        with m2:
            _metric_card("Countries", countries_count, "Covered destinations")
        with m3:
            _metric_card("Scholarship Programs", program_count, "Program-level sources")

        search_query = st.text_input(
            "Search trusted sources",
            placeholder="Search by source, provider, country, or purpose...",
            key="trusted_source_search",
        ).strip().lower()

        if search_query:
            visible_sources = [
                s for s in sources
                if search_query in (s.name or "").lower()
                or search_query in (s.provider or "").lower()
                or search_query in (s.destination_country or "").lower()
                or search_query in (s.source_type or "").lower()
            ]
        else:
            visible_sources = sources

        if not visible_sources:
            st.info("No trusted sources match your search.")
        else:
            grid = st.columns(2)

            for idx, s in enumerate(visible_sources):
                with grid[idx % 2]:
                    with st.container(border=True):
                        status = "Active" if s.is_active else "Inactive"
                        purpose = (s.source_type or "general").replace("_", " ").title()
                        review = "Manual Review" if s.requires_admin_review else "Auto Approved"
                        refreshed = _safe_freshness(s.last_refreshed_at)
                        refreshed_label = "Never refreshed" if refreshed == "Never" else f"Refreshed {refreshed}"

                        status_color = "#16a34a" if s.is_active else "#64748b"
                        review_color = "#f59e0b" if s.requires_admin_review else "#16a34a"

                        st.markdown(
                            f"""
<div style="padding:6px 0;">
    <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
        <div>
            <div style="font-size:1.05rem;font-weight:900;color:#0f172a;">{s.name}</div>
            <div style="font-size:0.86rem;color:#64748b;margin-top:4px;">{s.provider or 'Provider not listed'} ? {s.destination_country}</div>
        </div>
        <span style="background:{status_color};color:white;border-radius:999px;padding:6px 11px;font-size:0.74rem;font-weight:900;">{status}</span>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;">
        <span style="background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:999px;padding:6px 10px;font-size:0.76rem;font-weight:850;">{purpose}</span>
        <span style="background:#fff7ed;color:{review_color};border:1px solid #fed7aa;border-radius:999px;padding:6px 10px;font-size:0.76rem;font-weight:850;">{review}</span>
        <span style="background:#f8fafc;color:#475569;border:1px solid #e2e8f0;border-radius:999px;padding:6px 10px;font-size:0.76rem;font-weight:850;">{refreshed_label}</span>
    </div>
</div>
""",
                            unsafe_allow_html=True,
                        )

    st.markdown("#### Manage Trusted Source")

    all_sources_for_manage = list_curated_sources(active_only=False)

    if not all_sources_for_manage:
        st.info("Add or sync trusted sources before managing them.")
    else:
        choice = st.selectbox(
            "Choose source",
            all_sources_for_manage,
            format_func=lambda s: s.name,
            key="admin_manage_trusted_source_select",
        )

        if choice:
            chosen = choice

            with st.container(border=True):
                st.markdown(f"### {chosen.name}")
                st.caption(f"{chosen.provider or 'Provider not listed'} ? {chosen.destination_country}")

                edit_mode = st.toggle(
                    "Edit this trusted source",
                    value=False,
                    key=f"trusted_edit_mode_{chosen.id}",
                )

                if edit_mode:
                    edit_col1, edit_col2 = st.columns(2)

                    current_country_options = list(dict.fromkeys(country_options + [chosen.destination_country]))
                    current_source_type_options = list(dict.fromkeys(source_type_options + [chosen.source_type or "general"]))

                    with edit_col1:
                        edit_name = st.text_input(
                            "Source name",
                            value=chosen.name,
                            key=f"trusted_edit_name_{chosen.id}",
                        )
                        edit_provider = st.text_input(
                            "Provider",
                            value=chosen.provider or "",
                            key=f"trusted_edit_provider_{chosen.id}",
                        )
                        edit_country = st.selectbox(
                            "Destination country",
                            current_country_options,
                            index=current_country_options.index(chosen.destination_country)
                            if chosen.destination_country in current_country_options else 0,
                            key=f"trusted_edit_country_{chosen.id}",
                        )
                        edit_base_url = st.text_input(
                            "Main source URL",
                            value=chosen.base_url or "",
                            key=f"trusted_edit_base_url_{chosen.id}",
                        )
                        edit_source_type = st.selectbox(
                            "Source type",
                            current_source_type_options,
                            index=current_source_type_options.index(chosen.source_type)
                            if chosen.source_type in current_source_type_options else 0,
                            format_func=lambda x: x.replace("_", " ").title(),
                            key=f"trusted_edit_source_type_{chosen.id}",
                        )

                    with edit_col2:
                        edit_start_urls = st.text_area(
                            "Starting page(s)",
                            value=_list_to_text(chosen.start_urls),
                            height=90,
                            key=f"trusted_edit_start_urls_{chosen.id}",
                        )
                        edit_allowed_domains = st.text_area(
                            "Allowed domain(s)",
                            value=_list_to_text(chosen.allowed_domains),
                            height=90,
                            key=f"trusted_edit_allowed_domains_{chosen.id}",
                        )
                        edit_follow_keywords = st.text_area(
                            "Pages to prioritise",
                            value=_list_to_text(chosen.follow_keywords),
                            height=90,
                            key=f"trusted_edit_follow_keywords_{chosen.id}",
                        )
                        edit_block_keywords = st.text_area(
                            "Pages to avoid",
                            value=_list_to_text(chosen.block_keywords),
                            height=90,
                            key=f"trusted_edit_block_keywords_{chosen.id}",
                        )

                    edit_opt1, edit_opt2, edit_opt3 = st.columns(3)
                    with edit_opt1:
                        edit_max_depth = st.number_input(
                            "Crawler depth",
                            min_value=1,
                            max_value=5,
                            value=int(chosen.max_depth or 2),
                            step=1,
                            key=f"trusted_edit_max_depth_{chosen.id}",
                        )
                    with edit_opt2:
                        edit_is_active = st.checkbox(
                            "Source is active",
                            value=bool(chosen.is_active),
                            key=f"trusted_edit_is_active_{chosen.id}",
                        )
                    with edit_opt3:
                        edit_requires_review = st.checkbox(
                            "Requires admin review",
                            value=bool(chosen.requires_admin_review),
                            key=f"trusted_edit_requires_review_{chosen.id}",
                        )

                    if st.button("Save Trusted Source Changes", type="primary", use_container_width=True):
                        if not edit_name.strip() or not edit_country.strip() or not edit_base_url.strip():
                            st.error("Source name, destination country, and main source URL are required.")
                        else:
                            payload = _source_payload(
                                name=edit_name,
                                provider=edit_provider,
                                destination_country=edit_country,
                                base_url=edit_base_url,
                                start_urls_text=edit_start_urls,
                                allowed_domains_text=edit_allowed_domains,
                                follow_keywords_text=edit_follow_keywords,
                                block_keywords_text=edit_block_keywords,
                                max_depth=edit_max_depth,
                                source_type=edit_source_type,
                                is_active=edit_is_active,
                                requires_admin_review=edit_requires_review,
                            )
                            try:
                                source_id = upsert_curated_source(payload)
                                st.success(f"Trusted source changes saved. Source ID: {source_id}")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not update trusted source: {exc}")

                else:
                    new_active = st.checkbox(
                        "Source is active",
                        value=chosen.is_active,
                        key=f"curated_active_{chosen.id}",
                    )

                    action_1, action_2 = st.columns([1, 3])

                    with action_1:
                        if new_active != chosen.is_active:
                            if st.button("Save Changes", key=f"save_curated_{chosen.id}", type="primary", use_container_width=True):
                                set_curated_active(chosen.id, new_active)
                                st.success("Trusted source updated.")
                                st.rerun()

                    with st.expander("Crawler Summary"):
                        st.caption("Plain-English summary of how this trusted source is used during scholarship and policy refreshes.")

                        start_urls = chosen.start_urls or []
                        allowed_domains = chosen.allowed_domains or []
                        follow_keywords = chosen.follow_keywords or []
                        blocked_keywords = chosen.block_keywords or []

                        st.markdown("**Where the crawler starts**")
                        if start_urls:
                            for url in start_urls:
                                st.markdown(f"- It starts checking from: `{url}`")
                        else:
                            st.markdown("- No starting page has been configured yet.")

                        st.markdown("**Which website it is allowed to use**")
                        if allowed_domains:
                            readable_domains = ", ".join(str(domain) for domain in allowed_domains)
                            st.markdown(f"- It only follows pages from: **{readable_domains}**")
                        else:
                            st.markdown("- No allowed website domain has been configured yet.")

                        st.markdown("**What type of pages it looks for**")
                        if follow_keywords:
                            readable_follow = ", ".join(str(keyword) for keyword in follow_keywords)
                            st.markdown(f"- It prioritises pages related to: **{readable_follow}**")
                        else:
                            st.markdown("- No priority keywords have been configured yet.")

                        st.markdown("**What type of pages it avoids**")
                        if blocked_keywords:
                            readable_blocked = ", ".join(str(keyword) for keyword in blocked_keywords)
                            st.markdown(f"- It avoids pages related to: **{readable_blocked}**")
                        else:
                            st.markdown("- No blocked keywords have been configured yet.")

                        st.info("This summary is shown for admin understanding only. It does not change crawler behaviour.")


# ---------------------------------------------------------------------
# 5. Scholarship Library
# ---------------------------------------------------------------------

elif selected_section == "Scholarship Library":
    _section_intro(
        "Scholarship Library",
        "Browse collected scholarships in a readable admin-friendly format.",
    )

    f1, f2, f3 = st.columns([1.2, 1.2, 1.4])

    with f1:
        country = st.selectbox("Country", ["All"] + list(settings.SUPPORTED_COUNTRIES))

    with f2:
        show_hidden = st.toggle("Include hidden/internal records", value=False)

    with f3:
        if st.button("Refresh Scholarship Labels", use_container_width=True):
            counts = reclassify_all()
            st.success("Scholarship records reclassified.")
            with st.expander("Advanced classification summary"):
                st.json(counts)
            st.rerun()

    scholarships = list_scholarships(
        country=None if country == "All" else country,
        include_hidden=show_hidden,
        hide_expired=False,
        limit=500,
    )

    library_metric_html = f"""
<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:18px 0 28px 0;">
    <div style="background:linear-gradient(135deg,#4f46e5 0%,#2563eb 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(37,99,235,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Scholarships Found</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{len(scholarships)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Matching current filters</div>
    </div>

    <div style="background:linear-gradient(135deg,#16a34a 0%,#14b8a6 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(22,163,74,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Approved</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{sum(1 for s in scholarships if (s.review_status or "approved") == "approved")}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Visible to applicants</div>
    </div>

    <div style="background:linear-gradient(135deg,#f97316 0%,#fb7185 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(249,115,22,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">With Deadlines</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{sum(1 for s in scholarships if s.deadline)}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Deadline listed</div>
    </div>
</div>
"""
    components.html(library_metric_html, height=170, scrolling=False)

    if not scholarships:
        st.info("No scholarships match the current filters.")
    else:
        st.markdown("#### Scholarship Records")

        for s in scholarships:
            with st.container(border=True):
                left, right = st.columns([3.2, 1.2])

                with left:
                    summary = (s.summary or "No summary available.").strip()
                    if len(summary) > 260:
                        summary = summary[:260].rstrip() + "..."

                    st.markdown(f"### {s.title}")
                    st.caption(s.provider or "Provider not listed")

                    status = (s.review_status or "approved").replace("_", " ").title()
                    deadline = s.deadline or "Not listed"
                    degree = s.degree_level or "Any level"
                    trust = s.credibility.title() if s.credibility else "Unknown"

                    st.markdown(
                        f"""
<span style="background:#eef2ff;color:#4338ca;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;">{s.country or "Unknown country"}</span>
<span style="background:#ecfeff;color:#0f766e;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;">{degree}</span>
<span style="background:#fff7ed;color:#c2410c;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;">{trust}</span>
<span style="background:#f8fafc;color:#475569;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;">{status}</span>
""",
                        unsafe_allow_html=True,
                    )

                    st.write(summary)

                with right:
                    st.markdown("##### Details")
                    st.caption(f"Deadline: {deadline}")

                    if s.source_url:
                        st.link_button(
                            "Open Source",
                            s.source_url,
                            use_container_width=True,
                        )

        def _sch_clean(value, fallback="Not listed"):
            if value is None:
                return fallback
            value = str(value).strip()
            return value if value else fallback

        def _sch_status_class(value):
            value = _sch_clean(value, "Unknown").lower()
            if value in {"official", "approved", "verified", "government"}:
                return "good"
            if value in {"institutional", "university", "trusted"}:
                return "blue"
            if value in {"pending", "not listed", "unknown"}:
                return "warn"
            if value in {"rejected", "hidden"}:
                return "bad"
            return "blue"

        scholarship_rows = []
        for index, s in enumerate(scholarships, start=1):
            title = html.escape(_sch_clean(s.title, "Untitled scholarship"))
            provider = html.escape(_sch_clean(s.provider, "Provider not listed"))
            country_value = html.escape(_sch_clean(s.country, "Not listed"))
            degree = html.escape(_sch_clean(s.degree_level, "Any"))
            deadline = html.escape(_sch_clean(s.deadline, "Not listed"))
            trust = html.escape(_sch_clean(s.credibility.title() if s.credibility else "Unknown", "Unknown"))
            review_status = html.escape(_sch_clean((s.review_status or "approved").replace("_", " ").title(), "Approved"))
            source_url = _sch_clean(s.source_url, "")

            if source_url:
                source_html = f'<a class="source-link" href="{html.escape(source_url)}" target="_blank">Open Source</a>'
            else:
                source_html = '<span class="source-muted">Not listed</span>'

            scholarship_rows.append(
                f"""
                <tr>
                    <td class="rank-cell">{index:02d}</td>
                    <td>
                        <div class="sch-title">{title}</div>
                        <div class="sch-provider">{provider}</div>
                    </td>
                    <td><span class="country-pill">{country_value}</span></td>
                    <td><span class="degree-pill">{degree}</span></td>
                    <td><span class="deadline-pill">{deadline}</span></td>
                    <td><span class="status-badge {_sch_status_class(trust)}">{trust}</span></td>
                    <td><span class="status-badge {_sch_status_class(review_status)}">{review_status}</span></td>
                    <td>{source_html}</td>
                </tr>
                """
            )

        table_template = """
        <!doctype html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                    color: #0f172a;
                }
                .vf-scholarship-table-card {
                    background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                    border: 1px solid rgba(148,163,184,0.28);
                    border-radius: 26px;
                    box-shadow: 0 22px 55px rgba(15,23,42,0.08);
                    padding: 22px;
                    overflow: hidden;
                    margin-top: 18px;
                }
                .vf-scholarship-table-head {
                    display: flex;
                    justify-content: space-between;
                    gap: 18px;
                    align-items: flex-start;
                    margin-bottom: 18px;
                    padding-bottom: 16px;
                    border-bottom: 1px solid rgba(148,163,184,0.20);
                }
                .vf-scholarship-table-title {
                    font-size: 1.15rem;
                    font-weight: 900;
                    color: #0f172a;
                    letter-spacing: -0.02em;
                }
                .vf-scholarship-table-subtitle {
                    color: #64748b;
                    font-size: 0.9rem;
                    margin-top: 5px;
                }
                .vf-scholarship-count {
                    background: linear-gradient(135deg,#2563eb,#7c3aed);
                    color: white;
                    border-radius: 999px;
                    padding: 8px 14px;
                    font-size: 0.82rem;
                    font-weight: 850;
                    white-space: nowrap;
                    box-shadow: 0 12px 28px rgba(37,99,235,0.22);
                }
                .vf-table-wrap {
                    overflow-x: auto;
                    border-radius: 18px;
                    border: 1px solid rgba(226,232,240,0.95);
                }
                .vf-scholarship-table {
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 1120px;
                    background: white;
                }
                .vf-scholarship-table th {
                    background: #f8fafc;
                    color: #475569;
                    font-size: 0.72rem;
                    text-transform: uppercase;
                    letter-spacing: 0.06em;
                    font-weight: 900;
                    text-align: left;
                    padding: 14px 14px;
                    border-bottom: 1px solid #e2e8f0;
                    white-space: nowrap;
                }
                .vf-scholarship-table td {
                    padding: 14px;
                    border-bottom: 1px solid #eef2f7;
                    color: #0f172a;
                    font-size: 0.9rem;
                    vertical-align: middle;
                }
                .vf-scholarship-table tr:hover td {
                    background: #f8fbff;
                }
                .rank-cell {
                    color: #94a3b8 !important;
                    font-weight: 900;
                    width: 56px;
                }
                .sch-title {
                    font-weight: 900;
                    color: #0f172a;
                    line-height: 1.25;
                }
                .sch-provider {
                    margin-top: 4px;
                    color: #64748b;
                    font-size: 0.78rem;
                    line-height: 1.35;
                }
                .country-pill,
                .degree-pill,
                .deadline-pill {
                    display: inline-flex;
                    align-items: center;
                    border-radius: 999px;
                    padding: 7px 11px;
                    font-weight: 850;
                    font-size: 0.78rem;
                    white-space: nowrap;
                }
                .country-pill {
                    background: #eff6ff;
                    color: #1d4ed8;
                    border: 1px solid #bfdbfe;
                }
                .degree-pill {
                    background: #f5f3ff;
                    color: #6d28d9;
                    border: 1px solid #ddd6fe;
                }
                .deadline-pill {
                    background: #fff7ed;
                    color: #c2410c;
                    border: 1px solid #fed7aa;
                }
                .status-badge {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 999px;
                    padding: 7px 11px;
                    font-size: 0.76rem;
                    font-weight: 900;
                    white-space: nowrap;
                    border: 1px solid transparent;
                }
                .status-badge.good {
                    background: #ecfdf5;
                    color: #047857;
                    border-color: #a7f3d0;
                }
                .status-badge.blue {
                    background: #eff6ff;
                    color: #1d4ed8;
                    border-color: #bfdbfe;
                }
                .status-badge.warn {
                    background: #fffbeb;
                    color: #b45309;
                    border-color: #fde68a;
                }
                .status-badge.bad {
                    background: #fef2f2;
                    color: #b91c1c;
                    border-color: #fecaca;
                }
                .source-link {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    text-decoration: none;
                    border-radius: 999px;
                    padding: 8px 12px;
                    background: linear-gradient(135deg,#2563eb,#7c3aed);
                    color: white;
                    font-size: 0.76rem;
                    font-weight: 900;
                    white-space: nowrap;
                }
                .source-muted {
                    color: #94a3b8;
                    font-size: 0.8rem;
                    font-weight: 800;
                }
            </style>
        </head>
        <body>
            <div class="vf-scholarship-table-card">
                <div class="vf-scholarship-table-head">
                    <div>
                        <div class="vf-scholarship-table-title">Scholarship Library Table</div>
                        <div class="vf-scholarship-table-subtitle">Readable overview of all scholarship records, providers, trust level, deadlines, and source links.</div>
                    </div>
                    <div class="vf-scholarship-count">__COUNT__ Records</div>
                </div>
                <div class="vf-table-wrap">
                    <table class="vf-scholarship-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Scholarship</th>
                                <th>Country</th>
                                <th>Degree Level</th>
                                <th>Deadline</th>
                                <th>Trust</th>
                                <th>Review</th>
                                <th>Source</th>
                            </tr>
                        </thead>
                        <tbody>
                            __ROWS__
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """

        scholarship_table_html = (
            table_template
            .replace("__COUNT__", str(len(scholarships)))
            .replace("__ROWS__", "".join(scholarship_rows))
        )

        scholarship_table_height = min(820, max(390, 170 + (len(scholarships) * 58)))
        components.html(scholarship_table_html, height=scholarship_table_height, scrolling=True)


# ---------------------------------------------------------------------
# 6. Visa Routes & Rules
# ---------------------------------------------------------------------

elif selected_section == "Visa Routes & Rules":
    _section_intro(
        "Visa Routes & Rules",
        "Review country route readiness, policy rule availability, and workflow health.",
    )

    visa_meta = get_visa_rules_meta()
    route_meta = get_route_templates_meta()

    visa_version = visa_meta.get("version", "Not listed") if visa_meta else "Not listed"
    route_version = route_meta.get("version", "Not listed") if route_meta else "Not listed"

    supported_countries = list(settings.SUPPORTED_COUNTRIES)
    countries_count = len(supported_countries)

    route_metric_html = f"""
<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin:18px 0 28px 0;">
    <div style="background:linear-gradient(135deg,#4f46e5 0%,#2563eb 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(37,99,235,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Countries Supported</div>
        <div style="font-size:2.6rem;font-weight:900;margin-top:10px;">{countries_count}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Available route destinations</div>
    </div>

    <div style="background:linear-gradient(135deg,#06b6d4 0%,#14b8a6 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(20,184,166,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Visa Rules</div>
        <div style="font-size:2.1rem;font-weight:900;margin-top:14px;">{visa_version}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Current rules version</div>
    </div>

    <div style="background:linear-gradient(135deg,#7c3aed 0%,#6366f1 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(99,102,241,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">Route Templates</div>
        <div style="font-size:2.1rem;font-weight:900;margin-top:14px;">{route_version}</div>
        <div style="font-size:0.86rem;opacity:0.86;">Workflow template version</div>
    </div>

    <div style="background:linear-gradient(135deg,#f97316 0%,#fb7185 100%);padding:22px;border-radius:22px;color:white;box-shadow:0 20px 45px rgba(249,115,22,0.18);">
        <div style="font-size:0.92rem;font-weight:800;opacity:0.9;">System Status</div>
        <div style="font-size:2.1rem;font-weight:900;margin-top:14px;">Ready</div>
        <div style="font-size:0.86rem;opacity:0.86;">Routes available to users</div>
    </div>
</div>
"""
    components.html(route_metric_html, height=170, scrolling=False)

    st.markdown("#### Country Route Coverage")

    country_grid = st.columns(3)

    for idx, country in enumerate(supported_countries):
        with country_grid[idx % 3]:
            with st.container(border=True):
                st.markdown(f"### {country}")
                st.caption("Available applicant workflows")

                st.markdown(
                    """
<span style="background:#dcfce7;color:#15803d;padding:7px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;">Active</span>
<span style="background:#eef2ff;color:#4338ca;padding:7px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;">Student Visa</span>
<span style="background:#ecfeff;color:#0f766e;padding:7px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;">Scholarship Ready</span>
""",
                    unsafe_allow_html=True,
                )

                st.caption("Routes and scholarship guidance are currently active.")

    st.markdown("#### Policy & Route Readiness")

    left, right = st.columns(2)

    with left:
        with st.container(border=True):
            st.markdown("### Visa Rules")
            st.caption("Rules used to explain student visa readiness.")

            st.markdown(
                f"""
<span style="background:#eef2ff;color:#4338ca;padding:7px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;">Version {visa_version}</span>
<span style="background:#dcfce7;color:#15803d;padding:7px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;">Available</span>
""",
                unsafe_allow_html=True,
            )

            st.write(
                visa_meta.get(
                    "description",
                    "Visa rule metadata is available for the admin dashboard.",
                )
                if visa_meta
                else "Visa rule metadata is not available yet."
            )

    with right:
        with st.container(border=True):
            st.markdown("### Route Templates")
            st.caption("Workflow templates used to guide applicants step by step.")

            st.markdown(
                f"""
<span style="background:#eef2ff;color:#4338ca;padding:7px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;">Version {route_version}</span>
<span style="background:#dcfce7;color:#15803d;padding:7px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;">Available</span>
""",
                unsafe_allow_html=True,
            )

            st.write(
                route_meta.get(
                    "description",
                    "Route template metadata is available for the admin dashboard.",
                )
                if route_meta
                else "Route template metadata is not available yet."
            )


# ---------------------------------------------------------------------
# 7. Send Notifications
# ---------------------------------------------------------------------

elif selected_section == "Send Notifications":
    _section_intro(
        "Send Notifications",
        "Create targeted applicant emails, reminders, and important notices.",
    )

    audience_map = {
        "all": "All applicants",
        "incomplete_journey": "Applicants with incomplete journeys",
        "destination_country": "Applicants by destination country",
        "selected_scholarship": "Applicants with selected scholarships",
        "documents_started": "Applicants who started documents",
    }

    email_type_map = {
        "journey_reminder": "Journey reminder",
        "platform_tip": "Platform tip",
        "destination_insight": "Destination insight",
        "scholarship_insight": "Scholarship insight",
        "important_notice": "Important notice",
    }

    st.markdown(
        """
        <style>
        .vf-email-note {
            background: linear-gradient(135deg, rgba(37,99,235,0.10), rgba(124,58,237,0.10));
            border: 1px solid rgba(96,165,250,0.28);
            border-radius: 18px;
            padding: 14px 16px;
            color: #1e3a8a;
            font-weight: 750;
            margin: 8px 0 18px 0;
        }
        .vf-email-preview-card {
            background: rgba(255,255,255,0.72);
            border: 1px solid rgba(148,163,184,0.28);
            border-radius: 22px;
            padding: 20px;
            box-shadow: 0 18px 42px rgba(15,23,42,0.06);
        }
        .vf-email-subject {
            font-size: 0.95rem;
            color: #475569;
            margin-bottom: 12px;
        }
        .vf-email-body {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 18px;
            padding: 18px;
            line-height: 1.7;
            color: #0f172a;
        }
        .vf-report-strip {
            background: linear-gradient(135deg, rgba(16,185,129,0.12), rgba(37,99,235,0.10));
            border: 1px solid rgba(16,185,129,0.22);
            border-radius: 22px;
            padding: 18px;
            margin-top: 18px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.08, 1])

    with left:
        with st.container(border=True):
            st.markdown("### Campaign Setup")
            st.caption("Choose who should receive the email and what type of message should be sent.")

            audience = st.selectbox(
                "Target Audience",
                list(audience_map.keys()),
                format_func=lambda x: audience_map.get(x, x),
                key="admin_notification_audience",
            )

            country = None
            if audience == "destination_country":
                country = st.selectbox(
                    "Destination Country",
                    list(settings.SUPPORTED_COUNTRIES),
                    key="admin_notification_country",
                )

            email_type = st.selectbox(
                "Campaign Type",
                list(email_type_map.keys()),
                format_func=lambda x: email_type_map.get(x, x),
                key="admin_notification_email_type",
            )

            custom_message = ""
            if email_type == "important_notice":
                custom_message = st.text_area(
                    "Notice Message",
                    placeholder="Write the important notice applicants should receive...",
                    height=150,
                    key="admin_notification_custom_message",
                )

            st.markdown("#### Quick Summary")
            target_label = audience_map.get(audience, audience)
            if audience == "destination_country" and country:
                target_label = f"{target_label}: {country}"

            st.markdown(
                f"""
                <div class="vf-email-note">
                    Audience: {target_label}<br>
                    Campaign: {email_type_map.get(email_type, email_type)}
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("Send Campaign", type="primary", use_container_width=True):
                if email_type == "important_notice" and not custom_message.strip():
                    st.error("Please write the notice message first.")
                else:
                    with st.spinner("Sending campaign and preparing delivery report..."):
                        result = send_admin_email_campaign(
                            audience=audience,
                            email_type=email_type,
                            country=country,
                            custom_message=custom_message,
                        )

                    st.session_state["admin_last_delivery_report"] = result

                    st.success(
                        f"Campaign completed. Targeted {result.get('targeted', 0)} applicant(s), "
                        f"sent {result.get('sent', 0)}, failed {result.get('failed', 0)}, "
                        f"skipped {result.get('skipped', 0)}."
                    )

    with right:
        with st.container(border=True):
            st.markdown("### Email Preview")
            st.caption("Live preview of the message that will be sent to the selected applicant audience.")

            target_label = audience_map.get(audience, audience)
            if audience == "destination_country" and country:
                target_label = f"{target_label}: {country}"

            preview_templates = {
                "journey_reminder": {
                    "title": "Journey reminder",
                    "subject": "Continue your VisaForge journey",
                    "body": (
                        "This reminder encourages applicants to continue their VisaForge journey by completing "
                        "their profile, checking eligibility, selecting a scholarship, generating a route plan, "
                        "or uploading required documents."
                    ),
                },
                "platform_tip": {
                    "title": "Platform tip",
                    "subject": "VisaForge preparation tip",
                    "body": (
                        "This email shares a useful platform tip to help applicants understand their next steps "
                        "and use VisaForge more effectively during their study abroad preparation."
                    ),
                },
                "destination_insight": {
                    "title": "Destination guidance update",
                    "subject": "Destination guidance update",
                    "body": (
                        "This email provides applicants with guidance related to their selected destination country, "
                        "including preparation reminders and route-readiness suggestions."
                    ),
                },
                "scholarship_insight": {
                    "title": "Scholarship preparation guidance",
                    "subject": "Scholarship preparation guidance",
                    "body": (
                        "This email reminds applicants to review scholarship criteria, deadlines, required documents, "
                        "and next steps for their selected scholarship opportunities."
                    ),
                },
                "important_notice": {
                    "title": "Important notice",
                    "subject": "Important VisaForge notice",
                    "body": custom_message or "Your notice message will appear here before the campaign is sent.",
                },
            }

            preview = preview_templates.get(
                email_type,
                {
                    "title": email_type_map.get(email_type, "Email campaign"),
                    "subject": "VisaForge notification",
                    "body": "Campaign preview will appear here.",
                },
            )

            st.markdown(f"#### {preview['title']}")
            st.caption(f"Target audience: {target_label}")

            st.markdown(
                f"""
                <div class="vf-email-preview-card">
                    <div class="vf-email-subject"><strong>Subject:</strong> {preview['subject']}</div>
                    <div class="vf-email-body">
                        <p>Dear applicant,</p>
                        <p>{preview['body']}</p>
                        <p>Regards,<br><strong>VisaForge Team</strong></p>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("#### Campaign Readiness")
            p1, p2 = st.columns(2)
            with p1:
                st.metric("Channel", "Email")
            with p2:
                st.metric("Preview", "Ready to send")

    last_report = st.session_state.get("admin_last_delivery_report")
    if last_report:
        st.markdown("---")
        st.markdown("### Delivery Report")
        st.caption("Campaign result summary with searchable recipient details and a downloadable delivery log.")

        targeted_count = int(last_report.get("targeted", 0) or 0)
        sent_count = int(last_report.get("sent", 0) or 0)
        failed_count = int(last_report.get("failed", 0) or 0)
        skipped_count = int(last_report.get("skipped", 0) or 0)

        success_rate = round((sent_count / targeted_count) * 100, 1) if targeted_count else 0
        issue_count = failed_count + skipped_count

        st.markdown(
            f"""
            <style>
            .vf-delivery-hero {{
                background:
                    radial-gradient(circle at top left, rgba(37,99,235,0.18), transparent 34%),
                    radial-gradient(circle at top right, rgba(124,58,237,0.16), transparent 30%),
                    linear-gradient(135deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                border: 1px solid rgba(148,163,184,0.28);
                border-radius: 28px;
                padding: 22px;
                box-shadow: 0 24px 60px rgba(15,23,42,0.08);
                margin-top: 16px;
                margin-bottom: 18px;
            }}
            .vf-delivery-title {{
                font-size: 1.05rem;
                font-weight: 950;
                color: #0f172a;
                margin-bottom: 6px;
            }}
            .vf-delivery-subtitle {{
                color: #64748b;
                font-size: 0.9rem;
                line-height: 1.6;
            }}
            .vf-delivery-grid {{
                display: grid;
                grid-template-columns: repeat(5, minmax(0, 1fr));
                gap: 14px;
                margin-top: 18px;
            }}
            .vf-delivery-card {{
                border-radius: 22px;
                padding: 18px;
                min-height: 108px;
                border: 1px solid rgba(148,163,184,0.20);
                box-shadow: 0 16px 38px rgba(15,23,42,0.06);
                position: relative;
                overflow: hidden;
            }}
            .vf-delivery-card::after {{
                content: "";
                position: absolute;
                width: 90px;
                height: 90px;
                border-radius: 999px;
                top: -36px;
                right: -26px;
                background: rgba(255,255,255,0.18);
            }}
            .vf-card-blue {{
                background: linear-gradient(135deg,#2563eb,#4f46e5);
                color: white;
            }}
            .vf-card-green {{
                background: linear-gradient(135deg,#059669,#10b981);
                color: white;
            }}
            .vf-card-red {{
                background: linear-gradient(135deg,#ef4444,#f97316);
                color: white;
            }}
            .vf-card-purple {{
                background: linear-gradient(135deg,#7c3aed,#2563eb);
                color: white;
            }}
            .vf-card-amber {{
                background: linear-gradient(135deg,#f59e0b,#f97316);
                color: white;
            }}
            .vf-card-label {{
                font-size: 0.78rem;
                font-weight: 900;
                opacity: 0.92;
                margin-bottom: 10px;
            }}
            .vf-card-value {{
                font-size: 2.05rem;
                font-weight: 950;
                line-height: 1;
                letter-spacing: -0.05em;
            }}
            .vf-card-hint {{
                font-size: 0.76rem;
                font-weight: 800;
                opacity: 0.88;
                margin-top: 10px;
            }}
            .vf-report-note {{
                background: linear-gradient(135deg, rgba(37,99,235,0.10), rgba(124,58,237,0.10));
                border: 1px solid rgba(96,165,250,0.26);
                border-radius: 20px;
                padding: 15px 17px;
                color: #1e3a8a;
                font-weight: 800;
                line-height: 1.6;
                margin: 16px 0;
            }}
            @media (max-width: 1000px) {{
                .vf-delivery-grid {{
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }}
            }}
            </style>

            <div class="vf-delivery-hero">
                <div class="vf-delivery-title">Latest Campaign Result</div>
                <div class="vf-delivery-subtitle">
                    Summary of the most recent notification campaign. Recipient details are searchable below and the complete report can be downloaded.
                </div>
                <div class="vf-delivery-grid">
                    <div class="vf-delivery-card vf-card-blue">
                        <div class="vf-card-label">TARGETED</div>
                        <div class="vf-card-value">{targeted_count}</div>
                        <div class="vf-card-hint">Applicants matched</div>
                    </div>
                    <div class="vf-delivery-card vf-card-green">
                        <div class="vf-card-label">SENT</div>
                        <div class="vf-card-value">{sent_count}</div>
                        <div class="vf-card-hint">Successfully processed</div>
                    </div>
                    <div class="vf-delivery-card vf-card-red">
                        <div class="vf-card-label">FAILED</div>
                        <div class="vf-card-value">{failed_count}</div>
                        <div class="vf-card-hint">Email provider errors</div>
                    </div>
                    <div class="vf-delivery-card vf-card-amber">
                        <div class="vf-card-label">SKIPPED</div>
                        <div class="vf-card-value">{skipped_count}</div>
                        <div class="vf-card-hint">Missing required data</div>
                    </div>
                    <div class="vf-delivery-card vf-card-purple">
                        <div class="vf-card-label">SUCCESS RATE</div>
                        <div class="vf-card-value">{success_rate}%</div>
                        <div class="vf-card-hint">Sent / targeted</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        delivery_rows = last_report.get("delivery_report", [])
        if delivery_rows:
            report_df = pd.DataFrame(delivery_rows)

            expected_cols = ["Name", "Email", "Status", "Reason"]
            for col in expected_cols:
                if col not in report_df.columns:
                    report_df[col] = ""

            report_df = report_df[expected_cols].copy()
            report_df["Status"] = report_df["Status"].fillna("Unknown").astype(str)
            report_df["Name"] = report_df["Name"].fillna("Applicant").astype(str)
            report_df["Email"] = report_df["Email"].fillna("No email").astype(str)
            report_df["Reason"] = report_df["Reason"].fillna("").astype(str)

            sent_df = report_df[report_df["Status"] == "Sent"].copy()
            issue_df = report_df[report_df["Status"].isin(["Failed", "Skipped"])].copy()

            st.markdown(
                """
                <div class="vf-report-note">
                    Recipient tables are limited on-screen for performance. Use search to narrow results or download the full CSV report for large campaigns.
                </div>
                """,
                unsafe_allow_html=True,
            )

            csv_col, info_col = st.columns([1, 2])
            with csv_col:
                csv_data = report_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download full delivery report",
                    data=csv_data,
                    file_name="visaforge_delivery_report.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with info_col:
                st.caption(
                    f"Full report contains {len(report_df)} recipient record(s), "
                    f"including {len(sent_df)} sent and {len(issue_df)} failed/skipped record(s)."
                )

            def _delivery_status_class(value):
                value = str(value or "").lower()
                if value == "sent":
                    return "good"
                if value == "failed":
                    return "bad"
                if value == "skipped":
                    return "warn"
                return "blue"

            def _render_delivery_table(title, subtitle, rows_df, count_label, empty_message):
                table_rows = []
                for index, row in enumerate(rows_df.to_dict("records"), start=1):
                    name = html.escape(str(row.get("Name", "Applicant")))
                    email = html.escape(str(row.get("Email", "No email")))
                    status = html.escape(str(row.get("Status", "Unknown")))
                    reason = html.escape(str(row.get("Reason", "")))
                    status_class = _delivery_status_class(status)

                    table_rows.append(
                        f"""
                        <tr>
                            <td class="rank-cell">{index:02d}</td>
                            <td>
                                <div class="recipient-name">{name}</div>
                                <div class="recipient-email">{email}</div>
                            </td>
                            <td><span class="status-badge {status_class}">{status}</span></td>
                            <td><div class="reason-cell">{reason}</div></td>
                        </tr>
                        """
                    )

                if not table_rows:
                    table_rows.append(
                        f"""
                        <tr>
                            <td colspan="4">
                                <div class="empty-state">{html.escape(empty_message)}</div>
                            </td>
                        </tr>
                        """
                    )

                table_template = """
                <!doctype html>
                <html>
                <head>
                    <style>
                        body {
                            margin: 0;
                            padding: 0;
                            background: transparent;
                            font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                            color: #0f172a;
                        }
                        .vf-delivery-table-card {
                            background:
                                radial-gradient(circle at top left, rgba(37,99,235,0.10), transparent 30%),
                                linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                            border: 1px solid rgba(148,163,184,0.28);
                            border-radius: 26px;
                            box-shadow: 0 22px 55px rgba(15,23,42,0.08);
                            padding: 22px;
                            overflow: hidden;
                        }
                        .vf-delivery-table-head {
                            display: flex;
                            justify-content: space-between;
                            gap: 18px;
                            align-items: flex-start;
                            margin-bottom: 18px;
                            padding-bottom: 16px;
                            border-bottom: 1px solid rgba(148,163,184,0.20);
                        }
                        .vf-table-title {
                            font-size: 1.08rem;
                            font-weight: 950;
                            color: #0f172a;
                            letter-spacing: -0.02em;
                        }
                        .vf-table-subtitle {
                            color: #64748b;
                            font-size: 0.86rem;
                            margin-top: 5px;
                            line-height: 1.5;
                        }
                        .vf-table-count {
                            background: linear-gradient(135deg,#2563eb,#7c3aed);
                            color: white;
                            border-radius: 999px;
                            padding: 8px 14px;
                            font-size: 0.78rem;
                            font-weight: 900;
                            white-space: nowrap;
                            box-shadow: 0 12px 28px rgba(37,99,235,0.22);
                        }
                        .vf-table-wrap {
                            overflow-x: auto;
                            border-radius: 18px;
                            border: 1px solid rgba(226,232,240,0.95);
                        }
                        .vf-delivery-table {
                            width: 100%;
                            border-collapse: collapse;
                            min-width: 860px;
                            background: white;
                        }
                        .vf-delivery-table th {
                            background: #f8fafc;
                            color: #475569;
                            font-size: 0.72rem;
                            text-transform: uppercase;
                            letter-spacing: 0.06em;
                            font-weight: 900;
                            text-align: left;
                            padding: 14px 14px;
                            border-bottom: 1px solid #e2e8f0;
                            white-space: nowrap;
                        }
                        .vf-delivery-table td {
                            padding: 14px;
                            border-bottom: 1px solid #eef2f7;
                            color: #0f172a;
                            font-size: 0.9rem;
                            vertical-align: middle;
                        }
                        .vf-delivery-table tr:hover td {
                            background: #f8fbff;
                        }
                        .rank-cell {
                            color: #94a3b8 !important;
                            font-weight: 900;
                            width: 56px;
                        }
                        .recipient-name {
                            font-weight: 900;
                            color: #0f172a;
                            line-height: 1.25;
                        }
                        .recipient-email {
                            margin-top: 4px;
                            color: #64748b;
                            font-size: 0.78rem;
                            line-height: 1.35;
                        }
                        .status-badge {
                            display: inline-flex;
                            align-items: center;
                            justify-content: center;
                            border-radius: 999px;
                            padding: 7px 11px;
                            font-size: 0.76rem;
                            font-weight: 900;
                            white-space: nowrap;
                            border: 1px solid transparent;
                        }
                        .status-badge.good {
                            background: #ecfdf5;
                            color: #047857;
                            border-color: #a7f3d0;
                        }
                        .status-badge.blue {
                            background: #eff6ff;
                            color: #1d4ed8;
                            border-color: #bfdbfe;
                        }
                        .status-badge.warn {
                            background: #fffbeb;
                            color: #b45309;
                            border-color: #fde68a;
                        }
                        .status-badge.bad {
                            background: #fef2f2;
                            color: #b91c1c;
                            border-color: #fecaca;
                        }
                        .reason-cell {
                            color: #334155;
                            font-size: 0.82rem;
                            font-weight: 750;
                            max-width: 520px;
                            overflow: hidden;
                            text-overflow: ellipsis;
                            white-space: nowrap;
                        }
                        .empty-state {
                            background: #ecfdf5;
                            border: 1px solid #a7f3d0;
                            color: #047857;
                            border-radius: 16px;
                            padding: 16px;
                            font-weight: 900;
                            text-align: center;
                        }
                    </style>
                </head>
                <body>
                    <div class="vf-delivery-table-card">
                        <div class="vf-delivery-table-head">
                            <div>
                                <div class="vf-table-title">__TITLE__</div>
                                <div class="vf-table-subtitle">__SUBTITLE__</div>
                            </div>
                            <div class="vf-table-count">__COUNT__</div>
                        </div>
                        <div class="vf-table-wrap">
                            <table class="vf-delivery-table">
                                <thead>
                                    <tr>
                                        <th>#</th>
                                        <th>Recipient</th>
                                        <th>Status</th>
                                        <th>Delivery Note</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    __ROWS__
                                </tbody>
                            </table>
                        </div>
                    </div>
                </body>
                </html>
                """

                table_html = (
                    table_template
                    .replace("__TITLE__", html.escape(title))
                    .replace("__SUBTITLE__", html.escape(subtitle))
                    .replace("__COUNT__", html.escape(count_label))
                    .replace("__ROWS__", "".join(table_rows))
                )

                table_height = min(720, max(320, 170 + (len(rows_df) * 62)))
                components.html(table_html, height=table_height, scrolling=True)

            sent_tab, issue_tab = st.tabs(
                [
                    f"Sent recipients ({len(sent_df)})",
                    f"Failed / skipped ({len(issue_df)})",
                ]
            )

            with sent_tab:
                if st_keyup is not None:
                    sent_search_raw = st_keyup(
                        "",
                        placeholder="Search by name or email...",
                        key="admin_delivery_sent_search_live",
                        debounce=350,
                        label_visibility="collapsed",
                    )
                else:
                    sent_search_raw = st.text_input(
                        "",
                        placeholder="Search by name or email...",
                        key="admin_delivery_sent_search",
                        label_visibility="collapsed",
                    )

                sent_search = (sent_search_raw or "").strip().lower()

                visible_sent_df = sent_df.copy()
                if sent_search:
                    visible_sent_df = visible_sent_df[
                        visible_sent_df["Name"].str.lower().str.contains(sent_search, na=False)
                        | visible_sent_df["Email"].str.lower().str.contains(sent_search, na=False)
                    ]

                visible_sent_df = visible_sent_df.head(50)

                _render_delivery_table(
                    "Sent Recipients",
                    "Showing up to 50 successful recipients. Download the CSV for the complete delivery log.",
                    visible_sent_df,
                    f"{len(sent_df)} Sent",
                    "No sent recipients match the current search.",
                )

            with issue_tab:
                if st_keyup is not None:
                    issue_search_raw = st_keyup(
                        "",
                        placeholder="Search by name, email, status, or reason...",
                        key="admin_delivery_issue_search_live",
                        debounce=350,
                        label_visibility="collapsed",
                    )
                else:
                    issue_search_raw = st.text_input(
                        "",
                        placeholder="Search by name, email, status, or reason...",
                        key="admin_delivery_issue_search",
                        label_visibility="collapsed",
                    )

                issue_search = (issue_search_raw or "").strip().lower()

                visible_issue_df = issue_df.copy()
                if issue_search:
                    visible_issue_df = visible_issue_df[
                        visible_issue_df["Name"].str.lower().str.contains(issue_search, na=False)
                        | visible_issue_df["Email"].str.lower().str.contains(issue_search, na=False)
                        | visible_issue_df["Status"].str.lower().str.contains(issue_search, na=False)
                        | visible_issue_df["Reason"].str.lower().str.contains(issue_search, na=False)
                    ]

                _render_delivery_table(
                    "Failed or Skipped Recipients",
                    "Applicants that were not sent an email because of provider errors or missing required data.",
                    visible_issue_df,
                    f"{len(issue_df)} Issues",
                    "No failed or skipped recipients in the latest campaign.",
                )
        else:
            st.info("No recipient-level delivery details were returned for this campaign.")


# ---------------------------------------------------------------------
# 8. Account Management
# ---------------------------------------------------------------------

elif selected_section == "Account Management":
    if not is_super_admin():
        st.error("Only super admins can access account management.")
        st.stop()

    _section_intro(
        "Account Management",
        "Create admin accounts, manage roles, control access, and review administrative account activity.",
    )

    st.markdown(
        """
        <style>
        .vf-account-hero {
            background:
                radial-gradient(circle at top left, rgba(37,99,235,0.18), transparent 34%),
                radial-gradient(circle at top right, rgba(124,58,237,0.16), transparent 30%),
                linear-gradient(135deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
            border: 1px solid rgba(148,163,184,0.28);
            border-radius: 28px;
            padding: 22px;
            box-shadow: 0 24px 60px rgba(15,23,42,0.08);
            margin: 14px 0 20px 0;
        }
        .vf-account-hero-title {
            font-size: 1.1rem;
            font-weight: 950;
            color: #0f172a;
            letter-spacing: -0.02em;
            margin-bottom: 6px;
        }
        .vf-account-hero-text {
            color: #64748b;
            font-size: 0.92rem;
            line-height: 1.6;
        }
        .vf-account-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin: 18px 0 22px 0;
        }
        .vf-account-card {
            border-radius: 22px;
            padding: 18px;
            color: white;
            box-shadow: 0 16px 38px rgba(15,23,42,0.08);
            overflow: hidden;
            position: relative;
        }
        .vf-account-card::after {
            content: "";
            position: absolute;
            width: 88px;
            height: 88px;
            border-radius: 999px;
            top: -34px;
            right: -28px;
            background: rgba(255,255,255,0.18);
        }
        .vf-card-blue { background: linear-gradient(135deg,#2563eb,#4f46e5); }
        .vf-card-purple { background: linear-gradient(135deg,#7c3aed,#2563eb); }
        .vf-card-green { background: linear-gradient(135deg,#059669,#10b981); }
        .vf-card-amber { background: linear-gradient(135deg,#f59e0b,#f97316); }
        .vf-account-label {
            font-size: 0.78rem;
            font-weight: 900;
            opacity: 0.92;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .vf-account-value {
            font-size: 2.05rem;
            font-weight: 950;
            line-height: 1;
            letter-spacing: -0.05em;
        }
        .vf-account-hint {
            font-size: 0.76rem;
            font-weight: 800;
            opacity: 0.88;
            margin-top: 10px;
        }
        @media (max-width: 1000px) {
            .vf-account-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    users = list_account_management_users()
    total_accounts = len(users)
    active_accounts = sum(1 for u in users if u.get("is_active"))
    admin_accounts = sum(1 for u in users if u.get("role") == "admin")
    super_admin_accounts = sum(1 for u in users if u.get("role") == "super_admin")

    st.markdown(
        f"""
        <div class="vf-account-hero">
            <div class="vf-account-hero-title">Super Admin Control</div>
            <div class="vf-account-hero-text">
                Manage platform access without exposing account controls to regular admins.
                Role changes and activation updates are recorded in the admin audit log.
            </div>
            <div class="vf-account-grid">
                <div class="vf-account-card vf-card-blue">
                    <div class="vf-account-label">Total Accounts</div>
                    <div class="vf-account-value">{total_accounts}</div>
                    <div class="vf-account-hint">Registered users</div>
                </div>
                <div class="vf-account-card vf-card-green">
                    <div class="vf-account-label">Active</div>
                    <div class="vf-account-value">{active_accounts}</div>
                    <div class="vf-account-hint">Can sign in</div>
                </div>
                <div class="vf-account-card vf-card-purple">
                    <div class="vf-account-label">Admins</div>
                    <div class="vf-account-value">{admin_accounts}</div>
                    <div class="vf-account-hint">Operational admins</div>
                </div>
                <div class="vf-account-card vf-card-amber">
                    <div class="vf-account-label">Super Admins</div>
                    <div class="vf-account-value">{super_admin_accounts}</div>
                    <div class="vf-account-hint">Full account control</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <style>
        div[data-testid="stTabs"] {
            margin-top: 10px;
        }

        div[data-testid="stTabs"] div[role="tablist"] {
            gap: 10px;
            border-bottom: 1px solid rgba(148,163,184,0.22);
            padding-bottom: 10px;
        }

        div[data-testid="stTabs"] button[role="tab"] {
            background: rgba(255,255,255,0.92);
            border: 1px solid rgba(148,163,184,0.26);
            border-radius: 999px;
            padding: 10px 18px;
            color: #475569;
            font-weight: 850;
            box-shadow: 0 10px 24px rgba(15,23,42,0.045);
            transition: all 0.16s ease;
        }

        div[data-testid="stTabs"] button[role="tab"]:hover {
            background: linear-gradient(135deg, rgba(239,246,255,0.98), rgba(245,243,255,0.98));
            border-color: rgba(37,99,235,0.35);
            color: #1d4ed8;
        }

        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            background: linear-gradient(135deg,#2563eb,#7c3aed);
            color: white;
            border-color: transparent;
            box-shadow: 0 14px 32px rgba(37,99,235,0.20);
        }

        div[data-testid="stTabs"] button[role="tab"] p {
            font-size: 0.92rem;
            font-weight: 900;
            margin: 0;
        }

        div[data-testid="stTabs"] div[role="tabpanel"] {
            padding-top: 18px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    create_tab, manage_tab, audit_tab = st.tabs(
        [
            "➕ Create Admin",
            "👥 Manage Accounts",
            "📜 Admin Audit Log",
        ]
    )

    with create_tab:
        with st.container(border=True):
            st.markdown("### Create Admin Account")
            st.caption(
                "Create a new administrative account for platform operations. "
                "Use a temporary password and ask the recipient to change it after first login."
            )

            guide_1, guide_2, guide_3 = st.columns(3)

            with guide_1:
                with st.container(border=True):
                    st.markdown("#### Access Level")
                    st.write("Choose between a standard admin and a super admin account.")

            with guide_2:
                with st.container(border=True):
                    st.markdown("#### Security")
                    st.write("Use a temporary password with at least 8 characters.")

            with guide_3:
                with st.container(border=True):
                    st.markdown("#### Good Practice")
                    st.write("Only grant admin access to trusted team members.")

            st.divider()

            with st.form("super_admin_create_account_form", clear_on_submit=False):
                c1, c2 = st.columns(2)

                with c1:
                    new_name = st.text_input(
                        "Full name",
                        placeholder="Example: Admin User",
                    )
                    new_email = st.text_input(
                        "Email",
                        placeholder="admin@example.com",
                    )

                with c2:
                    new_role = st.selectbox(
                        "Role",
                        ["admin", "super_admin"],
                        format_func=lambda r: "Admin" if r == "admin" else "Super Admin",
                    )
                    new_password = st.text_input(
                        "Temporary password",
                        type="password",
                        placeholder="At least 8 characters",
                    )

                if new_role == "admin":
                    st.info("Selected role: Admin ? can access operational admin dashboard features.")
                else:
                    st.warning(
                        "Selected role: Super Admin ? can manage admin accounts, roles, "
                        "activation status, and audit access."
                    )

                confirm_create = st.checkbox(
                    "I confirm this account should receive administrative access."
                )

                submitted = st.form_submit_button(
                    "Create Admin Account",
                    type="primary",
                    use_container_width=True,
                )

        if submitted:
            if not confirm_create:
                st.error("Please confirm administrative access before creating the account.")
            else:
                try:
                    created = create_admin_account(
                        actor_user_id=current_admin_id,
                        actor_email=current_admin_email,
                        name=new_name,
                        email=new_email,
                        password=new_password,
                        role=new_role,
                    )
                    st.success(
                        f"{new_role.replace('_', ' ').title()} account created for {created.email}."
                    )
                    st.rerun()
                except AuthError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Could not create account: {exc}")

    with manage_tab:
        st.markdown("### Manage Accounts")
        st.caption(
            "Search users, review account status, update roles, and activate or deactivate accounts. "
            "Safety checks prevent removing the last active super admin."
        )

        if not users:
            st.info("No user accounts found.")
        else:
            users_df = pd.DataFrame(users)
            expected_cols = ["id", "name", "email", "role", "is_active", "created_at", "last_login_at"]

            for col in expected_cols:
                if col not in users_df.columns:
                    users_df[col] = ""

            st.markdown(
                """
                <style>
                .vf-account-search-title {
                    font-size: 0.95rem;
                    font-weight: 950;
                    color: #0f172a;
                    margin-top: 8px;
                    margin-bottom: 4px;
                }
                .vf-account-search-help {
                    color: #64748b;
                    font-size: 0.86rem;
                    line-height: 1.5;
                    margin-bottom: 8px;
                }
                </style>
                <div class="vf-account-search-title">Account Search</div>
                <div class="vf-account-search-help">
                    Start typing to filter accounts by name, email, or role.
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st_keyup is not None:
                account_search_raw = st_keyup(
                    "",
                    placeholder="Search accounts...",
                    key="super_admin_account_search_live",
                    debounce=350,
                    label_visibility="collapsed",
                )
            else:
                account_search_raw = st.text_input(
                    "",
                    placeholder="Search accounts...",
                    key="super_admin_account_search",
                    label_visibility="collapsed",
                )

            account_search = (account_search_raw or "").strip().lower()

            visible_df = users_df.copy()
            if account_search:
                visible_df = visible_df[
                    visible_df["name"].astype(str).str.lower().str.contains(account_search, na=False)
                    | visible_df["email"].astype(str).str.lower().str.contains(account_search, na=False)
                    | visible_df["role"].astype(str).str.lower().str.contains(account_search, na=False)
                ]

            def _role_label(value):
                value = str(value or "user")
                return value.replace("_", " ").title()

            def _role_class(value):
                value = str(value or "").lower()
                if value == "super_admin":
                    return "super"
                if value == "admin":
                    return "admin"
                return "user"

            def _active_class(value):
                return "active" if bool(value) else "inactive"

            def _active_label(value):
                return "Active" if bool(value) else "Inactive"

            def _short_date(value):
                value = str(value or "").strip()
                if not value or value.lower() in {"none", "nan", "nat"}:
                    return "Never"
                return value.replace("T", " ")[:16]

            table_rows = []
            for index, row in enumerate(visible_df.to_dict("records"), start=1):
                name = html.escape(str(row.get("name") or "Unnamed User"))
                email = html.escape(str(row.get("email") or "No email"))
                role = str(row.get("role") or "user")
                role_label = html.escape(_role_label(role))
                role_class = _role_class(role)
                active_label = html.escape(_active_label(row.get("is_active")))
                active_class = _active_class(row.get("is_active"))
                created = html.escape(_short_date(row.get("created_at")))
                last_login = html.escape(_short_date(row.get("last_login_at")))

                table_rows.append(
                    f"""
                    <tr>
                        <td class="rank-cell">{index:02d}</td>
                        <td>
                            <div class="account-name">{name}</div>
                            <div class="account-email">{email}</div>
                        </td>
                        <td><span class="role-badge {role_class}">{role_label}</span></td>
                        <td><span class="status-badge {active_class}">{active_label}</span></td>
                        <td><span class="date-pill">{created}</span></td>
                        <td><span class="date-pill">{last_login}</span></td>
                    </tr>
                    """
                )

            if not table_rows:
                table_rows.append(
                    """
                    <tr>
                        <td colspan="6">
                            <div class="empty-state">No accounts match the current search.</div>
                        </td>
                    </tr>
                    """
                )

            table_template = """
            <!doctype html>
            <html>
            <head>
                <style>
                    body {
                        margin: 0;
                        padding: 0;
                        background: transparent;
                        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                        color: #0f172a;
                    }
                    .vf-account-table-card {
                        background:
                            radial-gradient(circle at top left, rgba(37,99,235,0.10), transparent 30%),
                            linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                        border: 1px solid rgba(148,163,184,0.28);
                        border-radius: 26px;
                        box-shadow: 0 22px 55px rgba(15,23,42,0.08);
                        padding: 22px;
                        overflow: hidden;
                    }
                    .vf-account-table-head {
                        display: flex;
                        justify-content: space-between;
                        gap: 18px;
                        align-items: flex-start;
                        margin-bottom: 18px;
                        padding-bottom: 16px;
                        border-bottom: 1px solid rgba(148,163,184,0.20);
                    }
                    .vf-table-title {
                        font-size: 1.08rem;
                        font-weight: 950;
                        color: #0f172a;
                        letter-spacing: -0.02em;
                    }
                    .vf-table-subtitle {
                        color: #64748b;
                        font-size: 0.86rem;
                        margin-top: 5px;
                        line-height: 1.5;
                    }
                    .vf-table-count {
                        background: linear-gradient(135deg,#2563eb,#7c3aed);
                        color: white;
                        border-radius: 999px;
                        padding: 8px 14px;
                        font-size: 0.78rem;
                        font-weight: 900;
                        white-space: nowrap;
                        box-shadow: 0 12px 28px rgba(37,99,235,0.22);
                    }
                    .vf-table-wrap {
                        overflow-x: auto;
                        border-radius: 18px;
                        border: 1px solid rgba(226,232,240,0.95);
                    }
                    .vf-account-table {
                        width: 100%;
                        border-collapse: collapse;
                        min-width: 980px;
                        background: white;
                    }
                    .vf-account-table th {
                        background: #f8fafc;
                        color: #475569;
                        font-size: 0.72rem;
                        text-transform: uppercase;
                        letter-spacing: 0.06em;
                        font-weight: 900;
                        text-align: left;
                        padding: 14px 14px;
                        border-bottom: 1px solid #e2e8f0;
                        white-space: nowrap;
                    }
                    .vf-account-table td {
                        padding: 14px;
                        border-bottom: 1px solid #eef2f7;
                        color: #0f172a;
                        font-size: 0.9rem;
                        vertical-align: middle;
                    }
                    .vf-account-table tr:hover td {
                        background: #f8fbff;
                    }
                    .rank-cell {
                        color: #94a3b8 !important;
                        font-weight: 900;
                        width: 56px;
                    }
                    .account-name {
                        font-weight: 900;
                        color: #0f172a;
                        line-height: 1.25;
                    }
                    .account-email {
                        margin-top: 4px;
                        color: #64748b;
                        font-size: 0.78rem;
                        line-height: 1.35;
                    }
                    .role-badge,
                    .status-badge,
                    .date-pill {
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                        border-radius: 999px;
                        padding: 7px 11px;
                        font-size: 0.76rem;
                        font-weight: 900;
                        white-space: nowrap;
                        border: 1px solid transparent;
                    }
                    .role-badge.super {
                        background: #f5f3ff;
                        color: #6d28d9;
                        border-color: #ddd6fe;
                    }
                    .role-badge.admin {
                        background: #eff6ff;
                        color: #1d4ed8;
                        border-color: #bfdbfe;
                    }
                    .role-badge.user {
                        background: #f1f5f9;
                        color: #475569;
                        border-color: #e2e8f0;
                    }
                    .status-badge.active {
                        background: #ecfdf5;
                        color: #047857;
                        border-color: #a7f3d0;
                    }
                    .status-badge.inactive {
                        background: #fef2f2;
                        color: #b91c1c;
                        border-color: #fecaca;
                    }
                    .date-pill {
                        background: #f8fafc;
                        color: #475569;
                        border-color: #e2e8f0;
                    }
                    .empty-state {
                        background: #f8fafc;
                        border: 1px solid #e2e8f0;
                        color: #64748b;
                        border-radius: 16px;
                        padding: 16px;
                        font-weight: 900;
                        text-align: center;
                    }
                </style>
            </head>
            <body>
                <div class="vf-account-table-card">
                    <div class="vf-account-table-head">
                        <div>
                            <div class="vf-table-title">Account Directory</div>
                            <div class="vf-table-subtitle">Searchable overview of platform users, roles, account status, and recent login activity.</div>
                        </div>
                        <div class="vf-table-count">__COUNT__ Accounts</div>
                    </div>
                    <div class="vf-table-wrap">
                        <table class="vf-account-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Account</th>
                                    <th>Role</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Last Login</th>
                                </tr>
                            </thead>
                            <tbody>
                                __ROWS__
                            </tbody>
                        </table>
                    </div>
                </div>
            </body>
            </html>
            """

            table_html = (
                table_template
                .replace("__COUNT__", str(len(visible_df)))
                .replace("__ROWS__", "".join(table_rows))
            )

            table_height = min(720, max(340, 180 + (len(visible_df) * 62)))
            components.html(table_html, height=table_height, scrolling=True)

            st.markdown("#### Update Selected Account")

            visible_records = visible_df.to_dict("records")
            if not visible_records:
                st.info("No account is available to update for the current search.")
            else:
                account_options = {
                    (
                        f"{u.get('name') or 'Unnamed User'} | "
                        f"{u.get('email') or 'No email'} | "
                        f"{str(u.get('role') or 'user').replace('_', ' ').title()}"
                    ): u
                    for u in visible_records
                }

                selected_label = st.selectbox(
                    "Select account to update",
                    list(account_options.keys()),
                    key="super_admin_selected_account",
                )

                selected_user = account_options[selected_label]
                selected_role_label = str(selected_user.get("role") or "user").replace("_", " ").title()
                selected_status_label = "Active" if selected_user.get("is_active") else "Inactive"

                st.markdown(
                    f"""
                    <div style="
                        background:linear-gradient(135deg,rgba(239,246,255,0.95),rgba(245,243,255,0.95));
                        border:1px solid rgba(96,165,250,0.24);
                        border-radius:20px;
                        padding:16px 18px;
                        margin:12px 0 16px 0;">
                        <div style="font-size:0.78rem;font-weight:900;color:#2563eb;text-transform:uppercase;letter-spacing:0.06em;">
                            Selected Account
                        </div>
                        <div style="font-size:1.1rem;font-weight:950;color:#0f172a;margin-top:6px;">
                            {selected_user.get('name') or 'Unnamed User'}
                        </div>
                        <div style="color:#64748b;font-size:0.9rem;margin-top:3px;">
                            {selected_user.get('email') or 'No email'} ? {selected_role_label} ? {selected_status_label}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                control_1, control_2 = st.columns(2)

                with control_1:
                    with st.container(border=True):
                        st.markdown("##### Role")
                        st.caption("Change the account permission level.")
                        selected_new_role = st.selectbox(
                            "New role",
                            ["user", "admin", "super_admin"],
                            index=["user", "admin", "super_admin"].index(selected_user.get("role", "user"))
                            if selected_user.get("role", "user") in ["user", "admin", "super_admin"]
                            else 0,
                            format_func=lambda r: r.replace("_", " ").title(),
                            key=f"role_for_{selected_user.get('id')}",
                            label_visibility="collapsed",
                        )

                with control_2:
                    with st.container(border=True):
                        st.markdown("##### Account Status")
                        st.caption("Control whether this account can sign in.")
                        selected_active = st.toggle(
                            "Account is active",
                            value=bool(selected_user.get("is_active")),
                            key=f"active_for_{selected_user.get('id')}",
                        )

                apply_changes = st.button(
                    "Apply Account Changes",
                    type="primary",
                    use_container_width=True,
                    key=f"apply_account_changes_{selected_user.get('id')}",
                )

                if apply_changes:
                    try:
                        changed = False

                        if selected_new_role != selected_user.get("role"):
                            update_user_role(
                                actor_user_id=current_admin_id,
                                actor_email=current_admin_email,
                                target_user_id=int(selected_user.get("id")),
                                new_role=selected_new_role,
                            )
                            changed = True

                        if bool(selected_active) != bool(selected_user.get("is_active")):
                            set_user_active_status(
                                actor_user_id=current_admin_id,
                                actor_email=current_admin_email,
                                target_user_id=int(selected_user.get("id")),
                                active=bool(selected_active),
                            )
                            changed = True

                        if changed:
                            st.success("Account changes saved.")
                            st.rerun()
                        else:
                            st.info("No changes were made.")

                    except AuthError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Could not update account: {exc}")

    with audit_tab:
        st.markdown("### Admin Audit Log")
        st.caption("Recent super-admin account management actions, including account creation, role changes, and access updates.")

        audit_rows = list_admin_audit_logs(limit=150)

        def _audit_action_label(value):
            value = str(value or "").strip().lower()
            return {
                "create_account": "Created Account",
                "change_role": "Changed Role",
                "activate_account": "Activated Account",
                "deactivate_account": "Deactivated Account",
            }.get(value, value.replace("_", " ").title() or "Account Action")

        def _audit_action_class(value):
            value = str(value or "").strip().lower()
            if value == "create_account":
                return "blue"
            if value == "change_role":
                return "purple"
            if value == "activate_account":
                return "good"
            if value == "deactivate_account":
                return "bad"
            return "muted"

        def _audit_time(value):
            value = str(value or "").strip()
            if not value or value.lower() in {"none", "nan", "nat"}:
                return "Not recorded"
            return value.replace("T", " ")[:19]

        if not audit_rows:
            st.info("No admin account actions have been recorded yet.")
        else:
            table_rows = []

            for index, row in enumerate(audit_rows, start=1):
                time_value = html.escape(_audit_time(row.get("created_at")))
                actor = html.escape(str(row.get("actor_email") or "System"))
                target = html.escape(str(row.get("target_email") or "No target"))
                action_raw = row.get("action")
                action_label = html.escape(_audit_action_label(action_raw))
                action_class = _audit_action_class(action_raw)
                details = html.escape(str(row.get("details") or "No additional details."))

                table_rows.append(
                    f"""
                    <tr>
                        <td class="rank-cell">{index:02d}</td>
                        <td><span class="time-pill">{time_value}</span></td>
                        <td>
                            <div class="actor-name">{actor}</div>
                            <div class="actor-sub">Performed action</div>
                        </td>
                        <td><span class="action-badge {action_class}">{action_label}</span></td>
                        <td>
                            <div class="target-name">{target}</div>
                            <div class="target-sub">Target account</div>
                        </td>
                        <td><div class="details-cell">{details}</div></td>
                    </tr>
                    """
                )

            table_template = """
            <!doctype html>
            <html>
            <head>
                <style>
                    body {
                        margin: 0;
                        padding: 0;
                        background: transparent;
                        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                        color: #0f172a;
                    }
                    .vf-audit-table-card {
                        background:
                            radial-gradient(circle at top left, rgba(37,99,235,0.10), transparent 30%),
                            linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                        border: 1px solid rgba(148,163,184,0.28);
                        border-radius: 26px;
                        box-shadow: 0 22px 55px rgba(15,23,42,0.08);
                        padding: 22px;
                        overflow: hidden;
                    }
                    .vf-audit-table-head {
                        display: flex;
                        justify-content: space-between;
                        gap: 18px;
                        align-items: flex-start;
                        margin-bottom: 18px;
                        padding-bottom: 16px;
                        border-bottom: 1px solid rgba(148,163,184,0.20);
                    }
                    .vf-table-title {
                        font-size: 1.08rem;
                        font-weight: 950;
                        color: #0f172a;
                        letter-spacing: -0.02em;
                    }
                    .vf-table-subtitle {
                        color: #64748b;
                        font-size: 0.86rem;
                        margin-top: 5px;
                        line-height: 1.5;
                    }
                    .vf-table-count {
                        background: linear-gradient(135deg,#2563eb,#7c3aed);
                        color: white;
                        border-radius: 999px;
                        padding: 8px 14px;
                        font-size: 0.78rem;
                        font-weight: 900;
                        white-space: nowrap;
                        box-shadow: 0 12px 28px rgba(37,99,235,0.22);
                    }
                    .vf-table-wrap {
                        overflow-x: auto;
                        border-radius: 18px;
                        border: 1px solid rgba(226,232,240,0.95);
                    }
                    .vf-audit-table {
                        width: 100%;
                        border-collapse: collapse;
                        min-width: 1180px;
                        background: white;
                    }
                    .vf-audit-table th {
                        background: #f8fafc;
                        color: #475569;
                        font-size: 0.72rem;
                        text-transform: uppercase;
                        letter-spacing: 0.06em;
                        font-weight: 900;
                        text-align: left;
                        padding: 14px 14px;
                        border-bottom: 1px solid #e2e8f0;
                        white-space: nowrap;
                    }
                    .vf-audit-table td {
                        padding: 14px;
                        border-bottom: 1px solid #eef2f7;
                        color: #0f172a;
                        font-size: 0.9rem;
                        vertical-align: middle;
                    }
                    .vf-audit-table tr:hover td {
                        background: #f8fbff;
                    }
                    .rank-cell {
                        color: #94a3b8 !important;
                        font-weight: 900;
                        width: 56px;
                    }
                    .actor-name,
                    .target-name {
                        font-weight: 900;
                        color: #0f172a;
                        line-height: 1.25;
                    }
                    .actor-sub,
                    .target-sub {
                        margin-top: 4px;
                        color: #64748b;
                        font-size: 0.76rem;
                        line-height: 1.35;
                    }
                    .time-pill,
                    .action-badge {
                        display: inline-flex;
                        align-items: center;
                        justify-content: center;
                        border-radius: 999px;
                        padding: 7px 11px;
                        font-size: 0.76rem;
                        font-weight: 900;
                        white-space: nowrap;
                        border: 1px solid transparent;
                    }
                    .time-pill {
                        background: #f8fafc;
                        color: #475569;
                        border-color: #e2e8f0;
                    }
                    .action-badge.good {
                        background: #ecfdf5;
                        color: #047857;
                        border-color: #a7f3d0;
                    }
                    .action-badge.blue {
                        background: #eff6ff;
                        color: #1d4ed8;
                        border-color: #bfdbfe;
                    }
                    .action-badge.purple {
                        background: #f5f3ff;
                        color: #6d28d9;
                        border-color: #ddd6fe;
                    }
                    .action-badge.bad {
                        background: #fef2f2;
                        color: #b91c1c;
                        border-color: #fecaca;
                    }
                    .action-badge.muted {
                        background: #f1f5f9;
                        color: #475569;
                        border-color: #e2e8f0;
                    }
                    .details-cell {
                        color: #334155;
                        font-size: 0.82rem;
                        font-weight: 750;
                        max-width: 420px;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
                    }
                </style>
            </head>
            <body>
                <div class="vf-audit-table-card">
                    <div class="vf-audit-table-head">
                        <div>
                            <div class="vf-table-title">Admin Activity Trail</div>
                            <div class="vf-table-subtitle">Readable audit history of privileged account management actions performed by super admins.</div>
                        </div>
                        <div class="vf-table-count">__COUNT__ Events</div>
                    </div>
                    <div class="vf-table-wrap">
                        <table class="vf-audit-table">
                            <thead>
                                <tr>
                                    <th>#</th>
                                    <th>Time</th>
                                    <th>Actor</th>
                                    <th>Action</th>
                                    <th>Target</th>
                                    <th>Details</th>
                                </tr>
                            </thead>
                            <tbody>
                                __ROWS__
                            </tbody>
                        </table>
                    </div>
                </div>
            </body>
            </html>
            """

            table_html = (
                table_template
                .replace("__COUNT__", str(len(audit_rows)))
                .replace("__ROWS__", "".join(table_rows))
            )

            table_height = min(720, max(340, 180 + (len(audit_rows) * 62)))
            components.html(table_html, height=table_height, scrolling=True)


# ---------------------------------------------------------------------
# 9. Logs
# ---------------------------------------------------------------------

elif selected_section == "Logs":
    _section_intro(
        "Logs",
        "Monitor recent source refreshes, platform updates, and ingestion health.",
    )

    logs = recent_logs(limit=100)

    if not logs:
        st.info("No platform activity has been recorded yet.")
    else:
        total_logs = len(logs)
        healthy_logs = sum(1 for log in logs if _human_source_status(log.status) == "Healthy")
        attention_logs = sum(1 for log in logs if _human_source_status(log.status) == "Needs Attention")
        avg_duration = round(
            sum((log.duration_ms or 0) for log in logs) / total_logs
        ) if total_logs else 0

        l1, l2, l3, l4 = st.columns(4)

        with l1:
            metric_card(
                "Total Refreshes",
                total_logs,
                "Recent activity logs",
                "linear-gradient(135deg,#4f46e5 0%,#2563eb 100%)",
            )

        with l2:
            metric_card(
                "Healthy",
                healthy_logs,
                "Successful refreshes",
                "linear-gradient(135deg,#16a34a 0%,#14b8a6 100%)",
            )

        with l3:
            metric_card(
                "Needs Attention",
                attention_logs,
                "Failed or blocked sources",
                "linear-gradient(135deg,#f97316 0%,#fb7185 100%)",
            )

        with l4:
            metric_card(
                "Avg Duration",
                f"{avg_duration} ms",
                "Refresh speed",
                "linear-gradient(135deg,#7c3aed 0%,#6366f1 100%)",
            )

        st.markdown("#### Recent Activity")

        status_filter = st.selectbox(
            "Filter by status",
            ["All", "Healthy", "Needs Attention"],
        )

        filtered_logs = [
            log for log in logs
            if status_filter == "All" or _human_source_status(log.status) == status_filter
        ]

        def _log_clean(value, fallback="Not listed"):
            if value is None:
                return fallback
            value = str(value).strip()
            return value if value else fallback

        def _log_status_class(value):
            value = _log_clean(value, "Needs attention").lower()
            if "successfully" in value or value == "success":
                return "good"
            if "blocked" in value or "403" in value:
                return "bad"
            if "unavailable" in value or "404" in value:
                return "warn"
            if "attention" in value or "failed" in value:
                return "warn"
            return "blue"

        compact_table_rows = []
        detail_table_rows = []

        for index, log in enumerate(filtered_logs, start=1):
            status = _human_source_status(log.status)

            if status == "Healthy":
                readable_status = "Refreshed successfully"
            elif str(log.message or "").lower().startswith("http_403"):
                readable_status = "Access blocked"
            elif str(log.message or "").lower().startswith("http_404"):
                readable_status = "Source unavailable"
            else:
                readable_status = "Needs attention"

            source = log.source_url or "Source not listed"
            short_source = source.replace("https://", "").replace("http://", "").split("/")[0]
            checked = _safe_freshness(log.created_at)
            items_found = log.items_found or 0
            duration = f"{log.duration_ms or 0} ms"

            compact_table_rows.append(
                f"""
                <tr>
                    <td class="rank-cell">{index:02d}</td>
                    <td>
                        <div class="source-name">{html.escape(short_source)}</div>
                        <div class="source-url">{html.escape(source)}</div>
                    </td>
                    <td><span class="status-badge {_log_status_class(readable_status)}">{html.escape(readable_status)}</span></td>
                    <td><span class="time-pill">{html.escape(checked)}</span></td>
                    <td><span class="items-pill">{html.escape(str(items_found))}</span></td>
                    <td><span class="duration-pill">{html.escape(duration)}</span></td>
                </tr>
                """
            )

            detail_table_rows.append(
                f"""
                <tr>
                    <td class="rank-cell">{index:02d}</td>
                    <td><span class="status-badge {_log_status_class(log.status)}">{html.escape(_log_clean(log.status, "Unknown"))}</span></td>
                    <td><div class="message-cell">{html.escape(_log_clean(log.message, "No message"))}</div></td>
                    <td><div class="source-url wide">{html.escape(source)}</div></td>
                    <td><span class="time-pill">{html.escape(checked)}</span></td>
                    <td><span class="duration-pill">{html.escape(duration)}</span></td>
                </tr>
                """
            )

        logs_table_template = """
        <!doctype html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                    color: #0f172a;
                }
                .vf-log-card {
                    background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                    border: 1px solid rgba(148,163,184,0.28);
                    border-radius: 26px;
                    box-shadow: 0 22px 55px rgba(15,23,42,0.08);
                    padding: 22px;
                    overflow: hidden;
                }
                .vf-log-head {
                    display: flex;
                    justify-content: space-between;
                    gap: 18px;
                    align-items: flex-start;
                    margin-bottom: 18px;
                    padding-bottom: 16px;
                    border-bottom: 1px solid rgba(148,163,184,0.20);
                }
                .vf-log-title {
                    font-size: 1.15rem;
                    font-weight: 900;
                    color: #0f172a;
                    letter-spacing: -0.02em;
                }
                .vf-log-subtitle {
                    color: #64748b;
                    font-size: 0.9rem;
                    margin-top: 5px;
                }
                .vf-log-count {
                    background: linear-gradient(135deg,#2563eb,#7c3aed);
                    color: white;
                    border-radius: 999px;
                    padding: 8px 14px;
                    font-size: 0.82rem;
                    font-weight: 850;
                    white-space: nowrap;
                    box-shadow: 0 12px 28px rgba(37,99,235,0.22);
                }
                .vf-table-wrap {
                    overflow-x: auto;
                    border-radius: 18px;
                    border: 1px solid rgba(226,232,240,0.95);
                }
                .vf-log-table {
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 1040px;
                    background: white;
                }
                .vf-log-table th {
                    background: #f8fafc;
                    color: #475569;
                    font-size: 0.72rem;
                    text-transform: uppercase;
                    letter-spacing: 0.06em;
                    font-weight: 900;
                    text-align: left;
                    padding: 14px 14px;
                    border-bottom: 1px solid #e2e8f0;
                    white-space: nowrap;
                }
                .vf-log-table td {
                    padding: 14px;
                    border-bottom: 1px solid #eef2f7;
                    color: #0f172a;
                    font-size: 0.9rem;
                    vertical-align: middle;
                }
                .vf-log-table tr:hover td {
                    background: #f8fbff;
                }
                .rank-cell {
                    color: #94a3b8 !important;
                    font-weight: 900;
                    width: 56px;
                }
                .source-name {
                    font-weight: 900;
                    color: #0f172a;
                    line-height: 1.25;
                }
                .source-url {
                    margin-top: 4px;
                    color: #64748b;
                    font-size: 0.76rem;
                    line-height: 1.35;
                    max-width: 410px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                .source-url.wide {
                    max-width: 520px;
                }
                .message-cell {
                    color: #334155;
                    font-size: 0.82rem;
                    font-weight: 750;
                    max-width: 260px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                .status-badge,
                .time-pill,
                .items-pill,
                .duration-pill {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 999px;
                    padding: 7px 11px;
                    font-size: 0.76rem;
                    font-weight: 900;
                    white-space: nowrap;
                    border: 1px solid transparent;
                }
                .status-badge.good {
                    background: #ecfdf5;
                    color: #047857;
                    border-color: #a7f3d0;
                }
                .status-badge.blue {
                    background: #eff6ff;
                    color: #1d4ed8;
                    border-color: #bfdbfe;
                }
                .status-badge.warn {
                    background: #fffbeb;
                    color: #b45309;
                    border-color: #fde68a;
                }
                .status-badge.bad {
                    background: #fef2f2;
                    color: #b91c1c;
                    border-color: #fecaca;
                }
                .time-pill {
                    background: #f1f5f9;
                    color: #475569;
                    border-color: #e2e8f0;
                }
                .items-pill {
                    background: #eff6ff;
                    color: #1d4ed8;
                    border-color: #bfdbfe;
                    min-width: 34px;
                }
                .duration-pill {
                    background: #f5f3ff;
                    color: #6d28d9;
                    border-color: #ddd6fe;
                }
            </style>
        </head>
        <body>
            <div class="vf-log-card">
                <div class="vf-log-head">
                    <div>
                        <div class="vf-log-title">Recent Source Activity</div>
                        <div class="vf-log-subtitle">Readable overview of refresh status, source health, items found, and ingestion duration.</div>
                    </div>
                    <div class="vf-log-count">__COUNT__ Logs</div>
                </div>
                <div class="vf-table-wrap">
                    <table class="vf-log-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Source</th>
                                <th>Status</th>
                                <th>Last Checked</th>
                                <th>Items</th>
                                <th>Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            __ROWS__
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """

        logs_table_html = (
            logs_table_template
            .replace("__COUNT__", str(len(filtered_logs)))
            .replace("__ROWS__", "".join(compact_table_rows))
        )

        logs_table_height = min(780, max(390, 170 + (len(filtered_logs) * 58)))
        components.html(logs_table_html, height=logs_table_height, scrolling=True)

        advanced_template = """
        <!doctype html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                    color: #0f172a;
                }
                .vf-log-card {
                    background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
                    border: 1px solid rgba(148,163,184,0.28);
                    border-radius: 26px;
                    box-shadow: 0 22px 55px rgba(15,23,42,0.08);
                    padding: 22px;
                    overflow: hidden;
                }
                .vf-log-title {
                    font-size: 1.1rem;
                    font-weight: 900;
                    color: #0f172a;
                    margin-bottom: 5px;
                }
                .vf-log-subtitle {
                    color: #64748b;
                    font-size: 0.88rem;
                    margin-bottom: 16px;
                }
                .vf-table-wrap {
                    overflow-x: auto;
                    border-radius: 18px;
                    border: 1px solid rgba(226,232,240,0.95);
                }
                .vf-log-table {
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 1120px;
                    background: white;
                }
                .vf-log-table th {
                    background: #f8fafc;
                    color: #475569;
                    font-size: 0.72rem;
                    text-transform: uppercase;
                    letter-spacing: 0.06em;
                    font-weight: 900;
                    text-align: left;
                    padding: 14px 14px;
                    border-bottom: 1px solid #e2e8f0;
                    white-space: nowrap;
                }
                .vf-log-table td {
                    padding: 14px;
                    border-bottom: 1px solid #eef2f7;
                    color: #0f172a;
                    font-size: 0.9rem;
                    vertical-align: middle;
                }
                .vf-log-table tr:hover td {
                    background: #f8fbff;
                }
                .rank-cell {
                    color: #94a3b8 !important;
                    font-weight: 900;
                    width: 56px;
                }
                .status-badge,
                .time-pill,
                .duration-pill {
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 999px;
                    padding: 7px 11px;
                    font-size: 0.76rem;
                    font-weight: 900;
                    white-space: nowrap;
                    border: 1px solid transparent;
                }
                .status-badge.good {
                    background: #ecfdf5;
                    color: #047857;
                    border-color: #a7f3d0;
                }
                .status-badge.blue {
                    background: #eff6ff;
                    color: #1d4ed8;
                    border-color: #bfdbfe;
                }
                .status-badge.warn {
                    background: #fffbeb;
                    color: #b45309;
                    border-color: #fde68a;
                }
                .status-badge.bad {
                    background: #fef2f2;
                    color: #b91c1c;
                    border-color: #fecaca;
                }
                .message-cell {
                    color: #334155;
                    font-size: 0.82rem;
                    font-weight: 750;
                    max-width: 260px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                .source-url {
                    color: #64748b;
                    font-size: 0.76rem;
                    line-height: 1.35;
                    max-width: 520px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                .time-pill {
                    background: #f1f5f9;
                    color: #475569;
                    border-color: #e2e8f0;
                }
                .duration-pill {
                    background: #f5f3ff;
                    color: #6d28d9;
                    border-color: #ddd6fe;
                }
            </style>
        </head>
        <body>
            <div class="vf-log-card">
                <div class="vf-log-title">Advanced Log Details</div>
                <div class="vf-log-subtitle">Technical status, crawler message, full source URL, creation time, and duration.</div>
                <div class="vf-table-wrap">
                    <table class="vf-log-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Status</th>
                                <th>Message</th>
                                <th>Source URL</th>
                                <th>Created</th>
                                <th>Duration</th>
                            </tr>
                        </thead>
                        <tbody>
                            __ROWS__
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        """

        with st.expander("Advanced Log Details"):
            advanced_html = advanced_template.replace("__ROWS__", "".join(detail_table_rows))
            advanced_height = min(760, max(360, 160 + (len(filtered_logs) * 58)))
            components.html(advanced_html, height=advanced_height, scrolling=True)


st.divider()
disclaimer(compact=True)







































