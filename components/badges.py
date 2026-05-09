"""
components/badges.py
--------------------
Consistent colored badges used across pages. Uses Streamlit's
unsafe_allow_html to render compact pills.
"""

from __future__ import annotations

import streamlit as st


# Legacy eligibility status (back-compat)
_ELIGIBILITY_STYLES = {
    "eligible": ("#0a7c2f", "#e6f4ea", "Eligible"),
    "partial": ("#8a5a00", "#fff4cf", "Partial"),
    "not_eligible": ("#a6292e", "#fde7e9", "Not yet eligible"),
}

# v0.3 decision state
_DECISION_STYLES = {
    "ELIGIBLE":               ("#0a7c2f", "#e6f4ea", "Eligible"),
    "CONDITIONALLY_ELIGIBLE": ("#1f6feb", "#e0ecff", "Conditionally eligible"),
    "HIGH_RISK":              ("#8a5a00", "#fff4cf", "High risk"),
    "NOT_ELIGIBLE":           ("#a6292e", "#fde7e9", "Not eligible"),
}

_STEP_STYLES = {
    "completed":        ("#0a7c2f", "#e6f4ea", "Completed"),
    "available":        ("#1f6feb", "#e0ecff", "Available"),
    "pending_evidence": ("#8a5a00", "#fff4cf", "Pending evidence"),
    "blocked":          ("#a6292e", "#fde7e9", "Blocked"),
    "locked":           ("#555",    "#eee",    "Locked"),
}

_CREDIBILITY_STYLES = {
    "official":       ("#0a7c2f", "#e6f4ea", "Official"),
    "institutional":  ("#1f6feb", "#e0ecff", "Institutional"),
    "informational":  ("#555",    "#eee",    "Informational"),
}

_OUTCOME_STYLES = {
    "passed":            ("#0a7c2f", "#e6f4ea", "Passed"),
    "failed":            ("#a6292e", "#fde7e9", "Failed"),
    "missing_evidence":  ("#8a5a00", "#fff4cf", "Missing evidence"),
    "warning":           ("#8a5a00", "#fff4cf", "Warning"),
}

_PRIORITY_STYLES = {
    "CRITICAL":  ("#a6292e", "#fde7e9", "Critical"),
    "IMPORTANT": ("#8a5a00", "#fff4cf", "Important"),
    "OPTIONAL":  ("#1f6feb", "#e0ecff", "Optional"),
}

_MATCH_STYLES = {
    "strong_match":   ("#0a7c2f", "#e6f4ea", "Strong match"),
    "possible_match": ("#1f6feb", "#e0ecff", "Possible match"),
    "weak_match":     ("#8a5a00", "#fff4cf", "Weak match"),
    "not_eligible":   ("#a6292e", "#fde7e9", "Not eligible"),
}


def _pill(fg: str, bg: str, label: str) -> str:
    return (
        f"<span style='background:{bg};color:{fg};"
        f"padding:2px 10px;border-radius:12px;font-size:0.8rem;"
        f"font-weight:600;white-space:nowrap;'>"
        f"{label}</span>"
    )


def eligibility_badge(status: str) -> str:
    fg, bg, label = _ELIGIBILITY_STYLES.get(status, ("#555", "#eee", status))
    return _pill(fg, bg, label)


def decision_badge(decision: str) -> str:
    fg, bg, label = _DECISION_STYLES.get(decision, ("#555", "#eee", decision))
    return _pill(fg, bg, label)


def step_badge(status: str) -> str:
    fg, bg, label = _STEP_STYLES.get(status, ("#555", "#eee", status))
    return _pill(fg, bg, label)


def credibility_badge(level: str) -> str:
    fg, bg, label = _CREDIBILITY_STYLES.get(level, ("#555", "#eee", level))
    return _pill(fg, bg, label)


def outcome_badge(outcome: str) -> str:
    fg, bg, label = _OUTCOME_STYLES.get(outcome, ("#555", "#eee", outcome))
    return _pill(fg, bg, label)


def priority_badge(priority: str) -> str:
    fg, bg, label = _PRIORITY_STYLES.get(priority, ("#555", "#eee", priority))
    return _pill(fg, bg, label)


def match_badge(status: str) -> str:
    fg, bg, label = _MATCH_STYLES.get(status, ("#555", "#eee", status))
    return _pill(fg, bg, label)


def render_badge(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)
