"""Page 4 — Scholarship discovery, fit scoring, and selection."""
from __future__ import annotations

import streamlit as st

from components.badges import credibility_badge, match_badge, render_badge
from components.ui import (
    disclaimer,
    freshness_label,
    page_header,
    render_sidebar,
    require_profile,
    require_stage,
    require_user,
)
from services.profile_service import get_profile
from services.scholarship_service import (
    clear_selected_scholarship,
    get_selected_scholarship,
    is_bookmarked,
    is_selected,
    list_bookmarks,
    list_with_match,
    match_report_for,
    remove_bookmark,
    save_bookmark,
    set_selected_scholarship,
)
from utils.reference_data import STUDY_FIELDS


st.set_page_config(
    page_title="Scholarships · VisaForge",
    page_icon="🎓",
    layout="wide",
)
st.session_state["_current_page_path"] = "pages/4_Scholarships.py"

render_sidebar()
require_user()
require_stage("scholarships")

st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(99,102,241,.08), transparent 34%),
        linear-gradient(180deg,#fbfcff 0%,#ffffff 44%,#fbfbff 100%);
}
.block-container {
    max-width: 1220px;
    padding-top: 1.4rem;
    padding-bottom: 3rem;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 22px !important;
    border: 1px solid #e5e7eb !important;
    background: rgba(255,255,255,.94) !important;
    box-shadow: 0 16px 40px rgba(15,23,42,.055) !important;
}
div[data-testid="stExpander"] {
    border-radius: 15px !important;
    border: 1px solid #e5e7eb !important;
    background: rgba(255,255,255,.96) !important;
}
.stButton > button {
    border-radius: 14px !important;
    min-height: 44px !important;
    font-weight: 850 !important;
}
button[kind="primary"] {
    background: linear-gradient(135deg,#2563eb,#4f46e5) !important;
    color: white !important;
    border: none !important;
}
.vf-sch-hero {
    border-radius: 24px;
    padding: 30px 32px;
    margin: 8px 0 24px 0;
    color: white;
    background:
        radial-gradient(circle at 88% 16%, rgba(255,255,255,.22), transparent 7%),
        linear-gradient(135deg,#7c3aed 0%,#2563eb 48%,#14b8a6 100%);
    box-shadow: 0 24px 70px rgba(37,99,235,.18);
}
.vf-sch-hero h1 {
    margin: 0 0 12px 0;
    font-size: 34px;
    font-weight: 950;
    letter-spacing: -.7px;
}
.vf-sch-hero p {
    margin: 0;
    max-width: 820px;
    font-size: 14px;
    line-height: 1.65;
    font-weight: 650;
    opacity: .95;
}
.vf-fit-label {
    color:#64748b;
    font-size:12px;
    font-weight:900;
    letter-spacing:.06em;
    text-transform:uppercase;
    margin-bottom:8px;
}
.vf-fit-score {
    color:#111827;
    font-size:42px;
    font-weight:950;
    line-height:1;
}
.vf-source-btn a {
    display:inline-flex;
    padding:8px 13px;
    border-radius:999px;
    background:#eff6ff;
    border:1px solid #bfdbfe;
    color:#1d4ed8 !important;
    text-decoration:none;
    font-weight:850;
    font-size:13px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="vf-sch-hero">
    <h1>🎓 Scholarship Matching</h1>
    <p>Explore approved scholarship opportunities scored against your profile using a transparent deterministic Fit Score. Select one scholarship to target in your route plan.</p>
</div>
""", unsafe_allow_html=True)

profile_id = require_profile()
profile = get_profile(profile_id)
assert profile is not None


# --- Active selection banner ---------------------------------------------
selected = get_selected_scholarship(profile_id)

if selected is not None and is_selected(profile_id, selected.id or 0):
    provider = selected.provider or "Unknown provider"
    country = selected.country or "Unknown country"
    deadline = selected.deadline or "Deadline not available"

    left, right = st.columns([6, 1])

    with left:
        html = f"""
<div style='border-radius:24px;padding:26px 30px;border:1px solid #bfdbfe;background:linear-gradient(135deg,#ffffff,#eff6ff);box-shadow:0 18px 42px rgba(37,99,235,.10);margin-bottom:22px;'>
  <div style='display:inline-flex;padding:8px 14px;border-radius:999px;background:#dbeafe;color:#2563eb;font-weight:900;margin-bottom:14px;'>🎯 Selected Scholarship</div>
  <div style='font-size:30px;font-weight:950;color:#0f172a;margin-bottom:12px;line-height:1.1;'>{selected.title}</div>
  <div style='display:flex;flex-wrap:wrap;gap:10px;'>
    <span style='padding:8px 12px;border-radius:999px;background:white;border:1px solid #e5e7eb;color:#475569;font-weight:750;'>🏛 {provider}</span>
    <span style='padding:8px 12px;border-radius:999px;background:white;border:1px solid #e5e7eb;color:#475569;font-weight:750;'>🌍 {country}</span>
    <span style='padding:8px 12px;border-radius:999px;background:white;border:1px solid #e5e7eb;color:#475569;font-weight:750;'>📅 {deadline}</span>
  </div>
</div>
"""
        st.markdown(html, unsafe_allow_html=True)

    with right:
        if st.button("Clear", key="clear_selection"):
            clear_selected_scholarship(profile_id)
            st.rerun()


# --- Filters --------------------------------------------------------------
with st.container(border=True):
    st.markdown("#### 🔎 Filters")
    c1, c2, c3, c4 = st.columns(4)

    country_options = ["Any", "UK", "Canada", "Germany"]
    country = c1.selectbox(
        "Country",
        country_options,
        index=country_options.index(profile.destination_country)
        if profile.destination_country in country_options[1:] else 0,
    )
    degree_level = c2.selectbox(
        "Degree level",
        ["Any", "Bachelor's", "Masters", "PhD", "Postdoctoral"],
    )
    field = c3.selectbox("Field of study", ["Any"] + STUDY_FIELDS)
    match_filter = c4.selectbox(
        "Minimum match",
        ["Any", "Weak match", "Possible match", "Strong match"],
    )

    c5, c6 = st.columns(2)
    only_with_deadline = c5.checkbox("Only with known deadline", value=False)
    hide_expired = c6.checkbox("Hide expired deadlines", value=True)


# --- Scored results -------------------------------------------------------
scored = list_with_match(
    profile,
    country=None if country == "Any" else country,
    degree_level=None if degree_level == "Any" else degree_level,
    field_of_study=None if field == "Any" else field,
    only_with_deadline=only_with_deadline,
    hide_expired=hide_expired,
)

_match_rank = {
    "not_eligible": 0,
    "weak_match": 1,
    "possible_match": 2,
    "strong_match": 3,
}
_filter_min = {
    "Any": 0,
    "Weak match": 1,
    "Possible match": 2,
    "Strong match": 3,
}[match_filter]

scored = [
    (dto, report)
    for dto, report in scored
    if _match_rank[report.match_status] >= _filter_min
]


# --- Tabs -----------------------------------------------------------------
saved_count = len(list_bookmarks(profile_id))
tab_results, tab_saved = st.tabs([f"Results ({len(scored)})", f"⭐ Saved ({saved_count})"])


with tab_results:
    if not scored:
        st.info(
            "No approved scholarships are currently available. Please ask an admin "
            "to refresh and approve sources."
        )
    else:
        st.caption(
            "Only approved scholarship records are shown. Visa policy pages and "
            "non-scholarship content are filtered out automatically."
        )

    for dto, report in scored:
        with st.container(border=True):
            head_l, head_m, head_r = st.columns([4, 2, 1])

            with head_l:
                st.markdown(f"### {dto.title}")
                meta_bits = []
                if dto.provider:
                    meta_bits.append(dto.provider)
                meta_bits.append(dto.country)
                if dto.degree_level:
                    meta_bits.append(dto.degree_level)
                st.caption(" • ".join(meta_bits))

            with head_m:
                st.markdown(
                    f"""
<div class="vf-fit-label">Fit Score</div>
<div class="vf-fit-score">{report.fit_score}<span style="font-size:26px;">/100</span></div>
""",
                    unsafe_allow_html=True,
                )
                render_badge(match_badge(report.match_status))

            with head_r:
                render_badge(credibility_badge(dto.credibility))
                if dto.is_fallback:
                    st.caption("⚠️ Page-level fallback")

            if dto.summary:
                st.write(dto.summary)

            m1, m2, m3 = st.columns(3)
            m1.caption(f"**Deadline:** {dto.deadline or 'unknown'}")
            m2.caption(f"**Fetched:** {freshness_label(dto.fetched_at)}")
            m3.markdown(f"[🔗 Source]({dto.source_url})")

            cA, cB, cC = st.columns(3)
            with cA:
                with st.expander(f"✅ Matched ({len(report.matched_criteria)})"):
                    if report.matched_criteria:
                        for m in report.matched_criteria:
                            st.markdown(f"- {m}")
                    else:
                        st.caption("No criteria fully matched yet.")

            with cB:
                with st.expander(f"⚠️ Missing ({len(report.missing_criteria)})"):
                    if report.missing_criteria:
                        st.caption("Missing = your profile lacks or fails this criterion.")
                        for m in report.missing_criteria:
                            st.markdown(f"- {m}")
                    else:
                        st.caption("No gaps — strong profile fit.")

            with cC:
                with st.expander(f"❔ Unknown ({len(report.unknown_criteria)})"):
                    if report.unknown_criteria:
                        st.caption(
                            "Unknown = the scholarship source does not publish this criterion. "
                            "Verify directly."
                        )
                        for m in report.unknown_criteria:
                            st.markdown(f"- {m}")
                    else:
                        st.caption("All criteria fully specified by source.")

            if report.improvement_advice:
                with st.expander(f"💡 Improvement advice ({len(report.improvement_advice)})"):
                    for tip in report.improvement_advice:
                        st.markdown(f"- {tip}")

            with st.expander("🔎 Full fit score breakdown"):
                st.caption(
                    "Every criterion, its weight, and what was earned. "
                    "Weights: Eligibility 25%, GPA 20%, English 20%, "
                    "Field 15%, Readiness 10%, Deadline 10%."
                )
                for c in report.trace:
                    pct = int(round(100 * c.earned / c.weight)) if c.weight else 0
                    st.markdown(
                        f"- **{c.label}** "
                        f"(weight {int(round(c.weight * 100))}%) — "
                        f"{pct}% earned • `{c.strength}` — {c.detail}"
                    )

            btn_l, btn_m, btn_r = st.columns([1, 1, 3])
            if dto.id is not None:
                already_selected = is_selected(profile_id, dto.id)

                if btn_l.button(
                    "🎯 Selected" if already_selected else "🎯 Select",
                    key=f"sel_{dto.id}",
                    type="primary" if not already_selected else "secondary",
                    disabled=already_selected,
                    use_container_width=True,
                ):
                    set_selected_scholarship(profile_id, dto.id)
                    st.rerun()

                if is_bookmarked(profile_id, dto.id):
                    if btn_m.button("★ Saved", key=f"unsave_{dto.id}", use_container_width=True):
                        remove_bookmark(profile_id, dto.id)
                        st.rerun()
                else:
                    if btn_m.button("☆ Save", key=f"save_{dto.id}", use_container_width=True):
                        save_bookmark(profile_id, dto.id)
                        st.rerun()


with tab_saved:
    saved = list_bookmarks(profile_id)

    if not saved:
        st.info(
            "No saved scholarships yet. Save ones you want to revisit, "
            "and select one to make it your target."
        )

    for dto in saved:
        with st.container(border=True):
            report = match_report_for(profile, dto)
            head_l, head_r = st.columns([4, 1])

            with head_l:
                selected_label = " 🎯" if dto.id and is_selected(profile_id, dto.id) else ""
                st.markdown(f"**{dto.title}{selected_label}**")
                st.caption(
                    f"{dto.provider or '—'} • {dto.country} • "
                    f"deadline: {dto.deadline or 'unknown'}"
                )
                st.markdown(f"[🔗 {dto.source_name or 'Source'}]({dto.source_url})")

            with head_r:
                st.metric("Fit", f"{report.fit_score}/100")
                render_badge(match_badge(report.match_status))

            bL, bM = st.columns(2)

            if dto.id is not None:
                if is_selected(profile_id, dto.id):
                    if bL.button("Clear selection", key=f"clr_{dto.id}", use_container_width=True):
                        clear_selected_scholarship(profile_id)
                        st.rerun()
                else:
                    if bL.button(
                        "🎯 Select this",
                        key=f"sel_saved_{dto.id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        set_selected_scholarship(profile_id, dto.id)
                        st.rerun()

                if bM.button("Remove", key=f"rm_saved_{dto.id}", use_container_width=True):
                    remove_bookmark(profile_id, dto.id)
                    st.rerun()


st.divider()
st.caption(
    "ℹ️ Fit Score is a readiness indicator based on your profile against the "
    "scholarship's published criteria. It is not a prediction of acceptance. "
    "Always verify current eligibility on the official source."
)
disclaimer(compact=True)
