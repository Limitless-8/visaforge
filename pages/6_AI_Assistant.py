"""Page 6 — AI Guidance Assistant (v0.18 Phase 6).

Pakistan Immigration Expert Mode. Grounded in profile, eligibility,
scholarship, route plan, readiness score, and risk list.

Quick-action buttons surface the most common questions so the user
doesn't have to compose them from scratch.
"""
from __future__ import annotations

import streamlit as st
import html
import re

from components.ui import (
    disclaimer,
    page_header,
    render_sidebar,
    require_profile,
    require_stage,
    require_user,
)
from models.schemas import LLMMessage
from services.ai_service import (
    RouteStepContext,
    ask,
    ask_about_step,
)


st.set_page_config(
    page_title="AI Assistant · VisaForge",
    page_icon="🤖", layout="wide",
)
st.session_state["_current_page_path"] = "pages/6_AI_Assistant.py"




st.markdown("""
<style>

/* ===== AI PAGE HERO ===== */

.vf-ai-hero{
    position:relative;
    overflow:hidden;
    padding:34px 44px;
    border-radius:28px;
    margin: 0 0 24px 0;
    background:
        radial-gradient(circle at top right, rgba(255,255,255,.14), transparent 22%),
        linear-gradient(135deg,#7c3aed 0%,#2563eb 55%,#14b8a6 100%);
    box-shadow:0 24px 60px rgba(37,99,235,.16);
}

.vf-ai-hero h1{
    color:white !important;
    font-size:42px !important;
    font-weight:900 !important;
    margin:0 0 18px 0 !important;
    letter-spacing:-2px;
}

.vf-ai-hero p{
    color:rgba(255,255,255,.94) !important;
    font-size:16px !important;
    line-height:1.65 !important;
    font-weight:600;
    max-width:1100px;
}

/* ===== FOCUS CARD ===== */

.vf-focus-card{
    background:linear-gradient(135deg,#eff6ff,#f8fbff);
    border:1px solid #bfdbfe;
    border-radius:26px;
    padding:24px 28px;
    margin:18px 0 26px 0;
    box-shadow:0 16px 38px rgba(37,99,235,.08);
}

.vf-focus-title{
    font-size:15px;
    font-weight:900;
    text-transform:uppercase;
    letter-spacing:.12em;
    color:#2563eb;
    margin-bottom:10px;
}

.vf-focus-step{
    font-size:28px;
    font-weight:900;
    color:#0f172a;
    margin-bottom:10px;
}

.vf-focus-desc{
    font-size:17px;
    line-height:1.7;
    color:#475569;
    font-weight:600;
}

/* ===== CHAT CARDS ===== */

.vf-user-msg{
    background:linear-gradient(135deg,#eff6ff,#f8fbff);
    border:1px solid #bfdbfe;
    border-radius:24px;
    padding:24px 28px;
    margin-bottom:18px;
    box-shadow:0 12px 28px rgba(37,99,235,.06);
}

.vf-ai-msg{
    background:white;
    border:1px solid #e2e8f0;
    border-radius:28px;
    padding:32px 36px;
    margin-bottom:20px;
    box-shadow:0 14px 36px rgba(15,23,42,.05);
}

/* ===== INPUT ===== */

.stChatInputContainer{
    border-radius:22px !important;
}

.stChatInputContainer > div{
    border-radius:22px !important;
    border:1px solid #bfdbfe !important;
    box-shadow:0 10px 30px rgba(37,99,235,.08) !important;
}

/* ===== BUTTONS ===== */

.stButton > button{
    min-height:52px !important;
    border-radius:18px !important;
    font-weight:850 !important;
    border:1px solid #bfdbfe !important;
    background:linear-gradient(135deg,#ffffff,#eff6ff) !important;
    box-shadow:0 10px 24px rgba(37,99,235,.08) !important;
}

.stButton > button:hover{
    transform:translateY(-2px);
    border-color:#60a5fa !important;
    box-shadow:0 16px 34px rgba(37,99,235,.14) !important;
}

</style>
""", unsafe_allow_html=True)



st.markdown("""
<style>
.block-container {
    padding-top: 1.2rem !important;
    max-width: 1180px !important;
}

div[data-testid="stChatMessage"] {
    border-radius: 22px !important;
    padding: 18px 20px !important;
    margin-bottom: 14px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 10px 28px rgba(15,23,42,.04) !important;
}

div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    background: linear-gradient(135deg,#eff6ff,#f8fbff) !important;
}

div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    background: #ffffff !important;
}

.vf-focus-card {
    padding: 20px 24px !important;
    border-radius: 22px !important;
}

.vf-focus-step {
    font-size: 24px !important;
}

.vf-focus-desc {
    font-size: 15px !important;
}
</style>
""", unsafe_allow_html=True)


render_sidebar()
require_user()
require_stage("ai_assistant")
st.markdown("""
<div class="vf-ai-hero">
    <h1>Pakistan Immigration Expert</h1>
    <p>
        Get AI-guided explanations grounded in your profile, eligibility,
        scholarship selection, readiness score, and deterministic route workflow.
        The AI explains and guides — it never changes eligibility decisions or route status.
    </p>
</div>
""", unsafe_allow_html=True)

profile_id = require_profile()






def _clean_chat_text(value: object) -> str:
    raw = str(value or "")

    # Decode repeatedly — handles double/triple-encoded HTML entities
    for _ in range(8):
        prev = raw
        raw = html.unescape(raw)
        if raw == prev:
            break

    raw = raw.replace('\\\"', '"').replace("\\'", "'")
    raw = raw.replace("\\n", "\n")
    raw = raw.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

    # Remove known chat labels/wrappers first
    raw = re.sub(r'(?is)<div[^>]*vf-chat-label[^>]*>.*?</div>', '', raw)
    raw = re.sub(r'(?is)<div[^>]*vf-chat-bubble[^>]*>', '\n', raw)
    raw = re.sub(r'(?is)<div[^>]*vf-chat-ai[^>]*>', '\n', raw)
    raw = re.sub(r'(?is)<div[^>]*vf-chat-user[^>]*>', '\n', raw)
    raw = re.sub(r'(?is)<div[^>]*vf-ai-content[^>]*>', '\n', raw)

    # Hard strip of ALL remaining HTML tags (opening and closing)
    raw = re.sub(r'(?is)</?[a-zA-Z][^>]*>', '\n', raw)
    # Catch stray angle-bracket fragments
    raw = re.sub(r'<[^>]{0,120}>', ' ', raw)

    # Remove labels if they survived as plain text
    raw = raw.replace("VISAFORGE AI ASSISTANT", "")
    raw = raw.replace("VisaForge AI Assistant", "")
    raw = raw.replace("YOUR QUESTION", "")
    raw = raw.replace("Your Question", "")

    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'\n\s*\n\s*\n+', '\n\n', raw)
    return raw.strip()


def _is_html_garbage(text: str) -> bool:
    """Return True if text still looks like raw HTML after cleaning."""
    return bool(re.match(r'(?i)\s*<(div|span|html|body|p)\b', text.strip()))


# ---------- Session-state keys ------------------------------------------

history_key = f"ai_history_v2_{profile_id}"
if history_key not in st.session_state:
    st.session_state[history_key] = []



# Force-clean any old broken HTML saved in session state
st.session_state[history_key] = [
    {
        "role": _turn.get("role", "assistant"),
        "content": _clean_chat_text(_turn.get("content", "")),
    }
    for _turn in st.session_state[history_key]
    if _clean_chat_text(_turn.get("content", ""))
]




# ---------- Step-context handoff from Route Plan / Documents ------------

incoming: RouteStepContext | None = st.session_state.pop(
    "ai_step_context", None
)
if incoming is not None:
    st.session_state["ai_focused_step"] = {
        "key":         incoming.step_key,
        "kind":        incoming.kind,
        "document_id": incoming.document_id,
    }

focused = st.session_state.get("ai_focused_step")

if focused:
    fc_l, fc_r = st.columns([4, 1])
    with fc_l:
        kind_label = {
            "explain":  "Explain this step",
            "pakistan": "How to complete this in Pakistan",
            "ask":      "About this step",
            "issues":   "Explain document issues",
            "document": "Ask AI about this document",
        }.get(focused["kind"], focused["kind"])
        if focused.get("document_id"):
            st.info(
                f"🎯 **Focused on a document** · {kind_label} · "
                f"step `{focused['key'] or '—'}` · "
                f"doc id `{focused['document_id']}` "
                "— grounded in extracted text, fields, and issues."
            )
        else:
            with st.container(border=True):
                st.markdown("#### Current Route Focus")
                st.markdown(
                    f"### {focused['key'].replace('_', ' ').title() if focused.get('key') else 'General Immigration Guidance'}"
                )
                st.caption(
                    "AI responses are grounded against this route-plan step, your profile, "
                    "scholarship workflow, documents, and Pakistan-side process requirements where applicable."
                )


if focused:
    clear_focus_col, _ = st.columns([1, 4])
    with clear_focus_col:
        if st.button("Clear focus", use_container_width=True):
            st.session_state.pop("ai_focused_step", None)
            st.rerun()

# ---------- Quick-action buttons per spec §5 ----------------------------

if not focused:
    st.caption("**Quick questions — click to ask:**")
    qa_cols = st.columns(5)

    _QUICK_BUTTONS = [
        (
            "What should I do next?",
            "Based on my profile, route plan, readiness score, and risk "
            "analysis in your context, what is the single most important "
            "thing I should do right now? Be specific and actionable.",
        ),
        (
            "Am I ready for visa?",
            "Looking at my eligibility result, readiness breakdown, and "
            "the risks listed in context, assess how visa-ready I am. "
            "What are the biggest gaps I need to close before I can "
            "confidently apply for a student visa?",
        ),
        (
            "Check my risks",
            "Summarise all the risks currently detected for my application "
            "(use the `risks` list in context). For each risk, explain "
            "why it matters and what concrete step I should take to "
            "resolve it.",
        ),
        (
            "Explain Pakistan steps",
            "Explain the Pakistan-side preparation steps I need to complete "
            "before leaving for university. Cover HEC degree attestation, "
            "IBCC (if applicable), MOFA attestation, police clearance, "
            "and NADRA CNIC — in the right order. Use my profile "
            "destination country and degree to tailor the advice.",
        ),
        (
            "Explain my documents",
            "Review the documents I have uploaded (as listed in the route "
            "plan and document context). Which ones are marked as needing "
            "review or could not be read? What should I do to fix them?",
        ),
    ]

    for col, (label, prompt) in zip(qa_cols, _QUICK_BUTTONS):
        if col.button(label, use_container_width=True, key=f"qa_{label[:15]}"):
            st.session_state["_pending_prompt"] = prompt


st.divider()



st.markdown("""
<style>
.vf-chat-label-user {
    font-size: 13px;
    font-weight: 900;
    letter-spacing: .10em;
    text-transform: uppercase;
    color: #2563eb;
    margin-bottom: 10px;
}

.vf-chat-label-ai {
    font-size: 13px;
    font-weight: 900;
    letter-spacing: .10em;
    text-transform: uppercase;
    color: #0f766e;
    margin-bottom: 10px;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 24px !important;
    border: 1px solid #dbeafe !important;
    box-shadow: 0 18px 42px rgba(15,23,42,.055) !important;
    background: linear-gradient(135deg,#ffffff,#f8fbff) !important;
}

div[data-testid="stMarkdownContainer"] p {
    line-height: 1.85 !important;
    font-size: 16px !important;
}
</style>
""", unsafe_allow_html=True)



st.markdown("""
<style>
.vf-chat-window {
    height: 520px;
    overflow-y: auto;
    padding: 22px;
    border-radius: 28px;
    border: 1px solid #bfdbfe;
    background: linear-gradient(180deg,#ffffff,#f8fbff);
    box-shadow: 0 22px 54px rgba(15,23,42,.06);
    margin: 22px 0 26px 0;
}

.vf-chat-window::-webkit-scrollbar {
    width: 10px;
}

.vf-chat-window::-webkit-scrollbar-thumb {
    background: #bfdbfe;
    border-radius: 999px;
}

.vf-chat-window::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 999px;
}

.vf-chat-bubble {
    max-width: 86%;
    padding: 18px 20px;
    border-radius: 22px;
    margin-bottom: 18px;
    line-height: 1.75;
    font-size: 15.5px;
    box-shadow: 0 10px 26px rgba(15,23,42,.045);
}

.vf-chat-user {
    margin-left: auto;
    background: linear-gradient(135deg,#eff6ff,#dbeafe);
    border: 1px solid #bfdbfe;
    color: #0f172a;
}

.vf-chat-ai {
    margin-right: auto;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    color: #1e293b;
}

.vf-chat-label {
    font-size: 12px;
    font-weight: 950;
    letter-spacing: .12em;
    text-transform: uppercase;
    margin-bottom: 8px;
    color: #2563eb;
}

.vf-chat-ai .vf-chat-label {
    color: #0f766e;
}

.vf-empty-chat {
    height: 100%;
    display: grid;
    place-items: center;
    text-align: center;
    color: #64748b;
    font-weight: 700;
}

</style>
""", unsafe_allow_html=True)


# ---------- Render prior turns ------------------------------------------

chat_html = ""

for turn in st.session_state[history_key]:
    role = turn.get("role", "assistant")

    label = (
        "YOUR QUESTION"
        if role == "user"
        else "VISAFORGE AI ASSISTANT"
    )

    klass = (
        "vf-chat-user"
        if role == "user"
        else "vf-chat-ai"
    )

    clean_text = _clean_chat_text(turn.get("content", ""))

    # Safety net: if _clean_chat_text somehow left HTML garbage, clean again
    if _is_html_garbage(clean_text):
        clean_text = re.sub(r'<[^>]*>', ' ', clean_text).strip()

    content = html.escape(clean_text).replace("\n", "<br>")

    chat_html += (
        f'<div class="vf-chat-bubble {klass}">'
        f'<div class="vf-chat-label">{label}</div>'
        f'<div>{content}</div>'
        f'</div>'
    )

if not chat_html:
    chat_html = '<div class="vf-empty-chat">Start a conversation with VisaForge AI.</div>' 

st.markdown(
    f'<div class="vf-chat-window">{chat_html}</div>',
    unsafe_allow_html=True,
)

# ---------- Auto-run the composed question when arriving from a step ----

if incoming is not None and not (getattr(incoming, "user_question", None) or "").strip():
    history = [
        LLMMessage(role=t["role"], content=t["content"])
        for t in st.session_state[history_key]
    ]

    question, resp = ask_about_step(incoming, history=history)

    st.session_state[history_key].append(
        {"role": "user", "content": _clean_chat_text(question)}
    )
    st.session_state[history_key].append(
        {"role": "assistant", "content": _clean_chat_text(resp.content)}
    )

    st.rerun()



st.markdown("""
<style>
div[data-testid="stChatMessage"] {
    border-radius: 28px !important;
    padding: 22px 26px !important;
    margin-bottom: 18px !important;
    border: 1px solid #dbeafe !important;
    box-shadow: 0 18px 42px rgba(15,23,42,.055) !important;
    background: linear-gradient(135deg,#ffffff,#f8fbff) !important;
}

div[data-testid="stChatMessage"] p {
    font-size: 16px !important;
    line-height: 1.8 !important;
}

div[data-testid="stChatMessage"] a {
    font-weight: 800 !important;
}

[data-testid="stChatInput"] {
    border-radius: 24px !important;
    border: 1px solid #bfdbfe !important;
    box-shadow: 0 18px 42px rgba(37,99,235,.10) !important;
    background: linear-gradient(135deg,#ffffff,#f8fbff) !important;
}

[data-testid="stChatInput"] textarea {
    font-size: 16px !important;
    font-weight: 600 !important;
}

[data-testid="stChatInput"] button {
    border-radius: 16px !important;
    background: linear-gradient(135deg,#2563eb,#14b8a6) !important;
    color: white !important;
}

div[data-testid="stForm"] {
    border-radius: 24px !important;
    border: 1px solid #bfdbfe !important;
    background: linear-gradient(135deg,#ffffff,#f8fbff) !important;
    box-shadow: 0 18px 42px rgba(37,99,235,.10) !important;
    padding: 18px !important;
    margin-top: 24px !important;
}

textarea {
    border-radius: 18px !important;
    font-size: 16px !important;
    font-weight: 600 !important;
}

div[data-testid="stFormSubmitButton"] button {
    border-radius: 16px !important;
    background: linear-gradient(135deg,#2563eb,#14b8a6) !important;
    color: white !important;
    font-weight: 900 !important;
    min-height: 48px !important;
}

.vf-ai-disclaimer {
    margin-top: 22px;
    padding: 18px 22px;
    border-radius: 18px;
    background: #fffaf0;
    border: 1px solid #fde68a;
    color: #92400e;
    line-height: 1.7;
    font-size: 15px;
}
</style>
""", unsafe_allow_html=True)



# ---------- User input --------------------------------------------------

with st.form("ai_message_form", clear_on_submit=True):
    prompt = st.text_area(
        "Ask VisaForge AI",
        placeholder="Ask about eligibility, IELTS, HEC, MOFA, scholarships, visa, or documents...",
        height=90,
        label_visibility="collapsed",
    )
    send = st.form_submit_button("Send message", use_container_width=True)

pending = st.session_state.pop("_pending_prompt", None)
if pending and not prompt:
    prompt = pending

if not send and not pending:
    prompt = None


if prompt:
    st.session_state[history_key].append(
        {"role": "user", "content": _clean_chat_text(prompt)}
    )

    history = [
        LLMMessage(role=t["role"], content=t["content"])
        for t in st.session_state[history_key][:-1]
    ]

    focused_key = focused["key"] if focused else None
    focused_doc_id = (
        focused.get("document_id") if focused else None
    )

    resp = ask(
        profile_id,
        prompt,
        history=history,
        focused_step_key=focused_key,
        focused_document_id=focused_doc_id,
    )

    raw_assistant_text = str(getattr(resp, "content", resp))

    # Always clean the response; the cleaner handles HTML wrappers
    assistant_text = _clean_chat_text(raw_assistant_text)

    # If after cleaning the text is empty or still HTML-like, it was
    # a garbled/rate-limited response — show a friendly error
    if not assistant_text or _is_html_garbage(assistant_text):
        assistant_text = (
            "Sorry — the AI service is temporarily unavailable due to the current provider rate limit. "
            "Your deterministic pages like Eligibility, Route Plan, Scholarships, and Documents are unaffected."
        )

    st.session_state[history_key].append(
        {
            "role": "assistant",
            "content": assistant_text,
        }
    )

    st.rerun()


# ---------- Footer ------------------------------------------------------

clear_l, _ = st.columns([1, 3])

with clear_l:
    if st.button("🗑 Clear conversation"):
        st.session_state[history_key] = []
        st.session_state.pop("ai_focused_step", None)
        st.rerun()

st.divider()

st.markdown("""
<div class="vf-ai-disclaimer">
⚖️ <strong>Disclaimer</strong> ⚖️ VisaForge provides guidance and information support only.
It is <strong>not</strong> legal or immigration advice. Always verify details against official government sources before acting.
</div>
""", unsafe_allow_html=True)

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

