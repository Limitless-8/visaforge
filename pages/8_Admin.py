from __future__ import annotations

import pandas as pd
import streamlit as st
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
)


st.set_page_config(
    page_title="Admin Â· VisaForge",
    page_icon="ðŸ›¡ï¸",
    layout="wide",
)

render_sidebar()
require_admin()


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
    "Logs",
]

tab_labels = [
    ("User Analytics", "📊 User Analytics"),
    ("Scholarship Reviews", "🎓 Scholarship Reviews"),
    ("Official Sources", "🌐 Official Sources"),
    ("Trusted Sources", "🛡️ Trusted Sources"),
    ("Scholarship Library", "📚 Scholarship Library"),
    ("Visa Routes & Rules", "🛂 Visa Routes & Rules"),
    ("Send Notifications", "📢 Send Notifications"),
    ("Logs", "📜 Logs"),
]

if "selected_admin_tab" not in st.session_state:
    st.session_state.selected_admin_tab = "User Analytics"

with st.container(border=True):
    st.markdown("#### Admin Control Center")
    st.caption("Choose what you want to manage.")

    row1 = st.columns(4)
    row2 = st.columns(4)

    for idx, (section_key, label) in enumerate(tab_labels[:4]):
        with row1[idx]:
            active = st.session_state.selected_admin_tab == section_key
            button_label = ("🟢 " + label) if active else label
            if st.button(button_label, key=f"tab_{idx}", use_container_width=True):
                st.session_state.selected_admin_tab = section_key
                st.rerun()

    for idx, (section_key, label) in enumerate(tab_labels[4:]):
        with row2[idx]:
            active = st.session_state.selected_admin_tab == section_key
            button_label = ("🟢 " + label) if active else label
            if st.button(button_label, key=f"tab_{idx+4}", use_container_width=True):
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

    rows = rows_for_charts
    if rows:
        progress_html = "<div style='display:flex;flex-direction:column;gap:14px;margin-bottom:26px;'>"

        stage_colors = {
            "Not Started": "#64748b",
            "Profile Complete": "#6366f1",
            "Eligibility Complete": "#06b6d4",
            "Scholarship Selected": "#8b5cf6",
            "Route Generated": "#2563eb",
            "Document Vault": "#f59e0b",
            "Completed": "#16a34a",
        }

        for row in rows:
            name = row.get("Name", "Unknown")
            email = row.get("Email", "")
            destination = row.get("Destination", "Not Selected")
            stage = row.get("Journey Stage", "Not Started")
            completion = row.get("Completion %", 0)
            color = stage_colors.get(stage, "#2563eb")

            progress_html += (
                f"<div style='background:rgba(255,255,255,0.9);border:1px solid rgba(148,163,184,0.22);border-radius:22px;padding:18px 20px;box-shadow:0 14px 32px rgba(15,23,42,0.06);display:grid;grid-template-columns:2fr 1fr 1.3fr 1.2fr;gap:18px;align-items:center;'>"
                f"<div>"
                f"<div style='font-weight:850;color:#0f172a;font-size:1rem;'>{name}</div>"
                f"<div style='font-size:0.82rem;color:#64748b;margin-top:4px;'>{email}</div>"
                f"</div>"
                f"<div>"
                f"<div style='font-size:0.75rem;color:#64748b;font-weight:700;text-transform:uppercase;'>Destination</div>"
                f"<div style='font-weight:800;color:#0f172a;margin-top:4px;'>{destination}</div>"
                f"</div>"
                f"<div>"
                f"<span style='display:inline-block;background:{color}22;color:{color};border:1px solid {color}55;border-radius:999px;padding:7px 12px;font-size:0.82rem;font-weight:800;'>{stage}</span>"
                f"</div>"
                f"<div>"
                f"<div style='display:flex;justify-content:space-between;font-size:0.78rem;font-weight:800;color:#334155;margin-bottom:7px;'>"
                f"<span>Completion</span><span>{completion}%</span>"
                f"</div>"
                f"<div style='height:9px;background:#e2e8f0;border-radius:999px;overflow:hidden;'>"
                f"<div style='height:9px;width:{completion}%;background:{color};border-radius:999px;'></div>"
                f"</div>"
                f"</div>"
                f"</div>"
            )

        progress_html += "</div>"

        st.markdown(progress_html, unsafe_allow_html=True)

        with st.expander("View Detailed Applicant Table"):
            progress_df = pd.DataFrame(rows)
            st.dataframe(progress_df, use_container_width=True, hide_index=True)
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
        "Review the controlled source registry used for safer, curated refreshes.",
    )

    c1, c2, c3 = st.columns([1.2, 1, 3])

    with c1:
        if st.button("Update Trusted Sources", type="primary", use_container_width=True):
            n = seed_from_json()
            st.success(f"{n} trusted source(s) updated.")
            st.rerun()

    with c2:
        only_active = st.toggle("Active only", value=False)

    sources = list_curated_sources(active_only=only_active)

    if not sources:
        st.info("No trusted sources are available yet. Update trusted sources to populate this registry.")
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

                        st.markdown(f"### {s.name}")
                        st.caption(s.provider or "Trusted provider")

                        st.markdown(
                            f"""
<span style="background:#eef2ff;color:#4338ca;padding:6px 11px;border-radius:999px;font-size:0.76rem;font-weight:800;margin-right:6px;">{s.destination_country}</span>
<span style="background:#ecfeff;color:#0f766e;padding:6px 11px;border-radius:999px;font-size:0.76rem;font-weight:800;margin-right:6px;">{purpose}</span>
<span style="background:{status_color}18;color:{status_color};border:1px solid {status_color}55;padding:6px 11px;border-radius:999px;font-size:0.76rem;font-weight:800;margin-right:6px;">{status}</span>
<span style="background:{review_color}18;color:{review_color};border:1px solid {review_color}55;padding:6px 11px;border-radius:999px;font-size:0.76rem;font-weight:800;">{review}</span>
""",
                            unsafe_allow_html=True,
                        )

                        st.caption(refreshed_label)

                        if s.base_url:
                            st.link_button(
                                "Open Website",
                                s.base_url,
                                use_container_width=True,
                            )

        st.markdown("#### Manage Trusted Source")

        names = [f"{s.id}: {s.name} ({s.destination_country})" for s in sources]
        choice = st.selectbox("Choose source", names)

        if choice:
            chosen_id = int(choice.split(":")[0])
            chosen = next((s for s in sources if s.id == chosen_id), None)

            if chosen:
                with st.container(border=True):
                    purpose = (chosen.source_type or "General").replace("_", " ").title()
                    active_label = "Active" if chosen.is_active else "Inactive"
                    active_color = "#16a34a" if chosen.is_active else "#64748b"
                    review_label = "Manual Review" if chosen.requires_admin_review else "Auto Approved"
                    review_color = "#f59e0b" if chosen.requires_admin_review else "#16a34a"

                    st.markdown(f"### {chosen.name}")

                    st.caption(chosen.provider or "Trusted Provider")

                    pills = f"""
<span style='background:#eef2ff;color:#4338ca;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;'>{chosen.destination_country}</span>
<span style='background:#ecfeff;color:#0f766e;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;'>{purpose}</span>
<span style='background:#dcfce7;color:#15803d;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;margin-right:8px;'>{active_label}</span>
<span style='background:#fef3c7;color:#b45309;padding:6px 12px;border-radius:999px;font-size:0.78rem;font-weight:800;'>{review_label}</span>
"""

                    st.markdown(pills, unsafe_allow_html=True)

                    st.caption(f"Last refreshed: {_safe_freshness(chosen.last_refreshed_at)}")

                    st.link_button(
                        "Open Website",
                        chosen.base_url,
                        use_container_width=False,
                    )

                    st.markdown("")

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

                    with st.expander("Crawler Rules & Restrictions"):
                        st.caption("Advanced controls used by the source crawler. Non-technical admins usually do not need to edit these.")

                        st.markdown("**Start URLs**")
                        st.write(chosen.start_urls or [])

                        st.markdown("**Allowed domains**")
                        st.write(chosen.allowed_domains or [])

                        st.markdown("**Follow keywords**")
                        st.write(chosen.follow_keywords or [])

                        st.markdown("**Blocked keywords**")
                        st.write(chosen.block_keywords or [])


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

        with st.expander("View Detailed Scholarship Table"):
            library_df = pd.DataFrame(
                [
                    {
                        "Scholarship": s.title,
                        "Provider": s.provider or "Not listed",
                        "Country": s.country or "Not listed",
                        "Degree Level": s.degree_level or "Any",
                        "Deadline": s.deadline or "Not listed",
                        "Trust": s.credibility.title() if s.credibility else "Unknown",
                        "Review Status": (s.review_status or "approved").replace("_", " ").title(),
                        "Source": s.source_url,
                    }
                    for s in scholarships
                ]
            )
            st.dataframe(library_df, use_container_width=True, hide_index=True)


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

            with st.expander("Advanced Details"):
                st.json(visa_meta)

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

            with st.expander("Advanced Details"):
                st.json(route_meta)


# ---------------------------------------------------------------------
# 7. Send Notifications
# ---------------------------------------------------------------------

elif selected_section == "Send Notifications":
    _section_intro(
        "Send Notifications",
        "Create targeted applicant emails, reminders, and important notices.",
    )

    left, right = st.columns([1.15, 1])

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

    with left:
        with st.container(border=True):
            st.markdown("### Campaign Setup")
            st.caption("Choose the audience, message type, and optional notice content.")

            audience = st.selectbox(
                "Target Audience",
                list(audience_map.keys()),
                format_func=lambda x: audience_map.get(x, x),
            )

            country = None
            if audience == "destination_country":
                country = st.selectbox(
                    "Destination Country",
                    list(settings.SUPPORTED_COUNTRIES),
                )

            email_type = st.selectbox(
                "Campaign Type",
                list(email_type_map.keys()),
                format_func=lambda x: email_type_map.get(x, x),
            )

            custom_message = None
            if email_type == "important_notice":
                custom_message = st.text_area(
                    "Notice Message",
                    placeholder="Write the message applicants should receive...",
                    height=160,
                )

            st.markdown("#### Quick Summary")
            st.info(
                f"Audience: **{audience_map.get(audience, audience)}**\n\n"
                f"Campaign: **{email_type_map.get(email_type, email_type)}**"
            )

            if st.button("Send Campaign", type="primary", use_container_width=True):
                if email_type == "important_notice" and not custom_message:
                    st.error("Please write the notice message first.")
                else:
                    result = send_admin_email_campaign(
                        audience=audience,
                        email_type=email_type,
                        country=country,
                        custom_message=custom_message,
                    )

                    st.success(
                        f"Campaign completed. Targeted {result['targeted']} applicant(s), "
                        f"sent {result['sent']}, failed {result['failed']}."
                    )

    with right:
        with st.container(border=True):
            st.markdown("### Email Preview")
            st.caption("This preview helps admins understand what will be sent.")

            preview_title = email_type_map.get(email_type, email_type)

            st.markdown(f"#### {preview_title}")
            st.caption(f"Target: {audience_map.get(audience, audience)}")

            with st.container(border=True):
                if email_type == "journey_reminder":
                    st.markdown("**Subject:** Continue your VisaForge journey")
                    st.write(
                        "Applicants will receive a reminder to continue their profile, "
                        "eligibility check, scholarship selection, or route plan."
                    )

                elif email_type == "platform_tip":
                    st.markdown("**Subject:** What VisaForge can help you with")
                    st.write(
                        "Applicants will receive a helpful overview of VisaForge features "
                        "and how to continue their study-abroad journey."
                    )

                elif email_type == "destination_insight":
                    st.markdown("**Subject:** Destination country guidance")
                    st.write(
                        "Applicants will receive destination-specific preparation guidance "
                        "based on their selected country."
                    )

                elif email_type == "scholarship_insight":
                    st.markdown("**Subject:** Scholarship guidance")
                    st.write(
                        "Applicants with selected scholarships will receive guidance about "
                        "reviewing criteria, deadlines, documents, and next steps."
                    )

                elif email_type == "important_notice":
                    st.markdown("**Subject:** Important VisaForge notice")
                    st.write(custom_message or "Your notice message will appear here.")

            st.markdown("#### Delivery Status")
            st.success("Ready to send")

            p1, p2 = st.columns(2)
            with p1:
                st.metric("Mode", "Email")
            with p2:
                st.metric("Status", "Ready")


# ---------------------------------------------------------------------
# 8. Logs
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

        compact_rows = []

        for log in filtered_logs:
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

            compact_rows.append(
                {
                    "Source": short_source,
                    "Status": readable_status,
                    "Checked": _safe_freshness(log.created_at),
                    "Items": log.items_found,
                    "Duration": f"{log.duration_ms or 0} ms",
                }
            )

        styled_df = pd.DataFrame(compact_rows).rename(
            columns={"Checked": "Last Checked"}
        )

        def style_status(val):
            val = str(val)

            if "successfully" in val.lower():
                return "background-color:#dcfce7;color:#166534;font-weight:700;"
            elif "blocked" in val.lower():
                return "background-color:#fee2e2;color:#991b1b;font-weight:700;"
            elif "unavailable" in val.lower():
                return "background-color:#ffedd5;color:#c2410c;font-weight:700;"
            else:
                return "background-color:#fef3c7;color:#92400e;font-weight:700;"

        styled_logs = styled_df.style.map(
            style_status,
            subset=["Status"]
        )

        st.dataframe(
            styled_logs,
            use_container_width=True,
            hide_index=True,
            height=420,
        )

        with st.expander("Advanced Log Details"):
            detail_rows = [
                {
                    "Status": log.status,
                    "Message": log.message or "",
                    "Source URL": log.source_url or "",
                    "Created": _safe_freshness(log.created_at),
                    "Duration": f"{log.duration_ms or 0} ms",
                }
                for log in filtered_logs
            ]

            st.dataframe(
                pd.DataFrame(detail_rows),
                use_container_width=True,
                hide_index=True,
            )


st.divider()
disclaimer(compact=True)







































