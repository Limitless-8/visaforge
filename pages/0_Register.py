"""Page 0 — Register."""
from __future__ import annotations

import streamlit as st

from components.ui import disclaimer, render_sidebar
from config.settings import settings
from services.auth_service import (
    AuthError,
    is_logged_in,
    login_session,
    register_user,
)

st.set_page_config(
    page_title="Register · VisaForge",
    page_icon="📝",
    layout="centered",
)

render_sidebar()

st.markdown(
    """
<style>
.register-shell {
    max-width: 980px;
    margin: 0 auto;
    padding-top: 28px;
}

.register-hero {
    background: linear-gradient(135deg,#4f46e5 0%,#2563eb 58%,#14b8a6 100%);
    color: white;
    border-radius: 28px;
    padding: 34px 36px;
    box-shadow: 0 28px 70px rgba(37,99,235,0.24);
    margin-bottom: 24px;
}

.register-hero h1 {
    margin: 0 0 10px 0;
    font-size: 2.3rem;
    font-weight: 900;
}

.register-hero p {
    margin: 0;
    font-size: 1.02rem;
    opacity: 0.92;
    line-height: 1.65;
}

.register-tip {
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(148,163,184,0.24);
    border-radius: 22px;
    padding: 20px;
    box-shadow: 0 18px 45px rgba(15,23,42,0.07);
    margin-bottom: 18px;
}

.register-tip strong {
    color: #0f172a;
}

.stPageLink a {
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    width:100% !important;
    min-height:48px !important;
    border-radius:16px !important;
    background:linear-gradient(135deg,#2563eb 0%,#3b82f6 100%) !important;
    color:white !important;
    font-weight:800 !important;
    border:none !important;
    box-shadow:0 14px 30px rgba(37,99,235,0.20) !important;
    transition:all 0.18s ease !important;
}

.stPageLink a p {
    color:white !important;
    font-weight:800 !important;
}

.stPageLink a:hover {
    transform:translateY(-2px);
    box-shadow:0 18px 36px rgba(37,99,235,0.28) !important;
}
</style>
""",
    unsafe_allow_html=True,
)

if is_logged_in():
    st.success("You're already signed in.")
    st.page_link("pages/7_Dashboard.py", label="Go to Dashboard", icon="📊")
    st.stop()

st.markdown(
    f"""
<div class="register-shell">
    <div class="register-hero">
        <h1>Create your VisaForge account</h1>
        <p>{settings.APP_TAGLINE}</p>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

left, right = st.columns([1.18, 0.82])

with left:
    with st.container(border=True):
        st.markdown("## Create account")
        st.caption("Start your study-abroad journey with a secure VisaForge profile.")

        with st.form("register_form", clear_on_submit=False):
            name = st.text_input(
                "Full name",
                placeholder="e.g. Ayesha Khan",
            )

            email = st.text_input(
                "Email",
                autocomplete="username",
                placeholder="you@example.com",
            )

            password = st.text_input(
                "Password",
                type="password",
                autocomplete="new-password",
                placeholder="At least 8 characters",
                help="Use at least 8 characters.",
            )

            password_confirm = st.text_input(
                "Confirm password",
                type="password",
                autocomplete="new-password",
                placeholder="Repeat password",
            )

            agree = st.checkbox(
                "I understand VisaForge provides guidance only, not legal or immigration advice."
            )

            submitted = st.form_submit_button(
                "Create account",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            if not name or not email or not password:
                st.error("Please complete all required fields.")
            elif not agree:
                st.error("Please acknowledge the guidance disclaimer to continue.")
            elif password != password_confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    user = register_user(
                        name=name,
                        email=email,
                        password=password,
                        role="user",
                    )

                    login_session(user)

                    st.success(f"Welcome, {user.name}! Let's set up your profile.")
                    st.page_link(
                        "pages/1_Profile.py",
                        label="Create your profile",
                        icon="👤",
                    )
                    st.rerun()

                except AuthError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Could not create account: {e}")

with right:
    with st.container(border=True):
        st.markdown("### Already registered?")
        st.write(
            "Sign in to continue your profile, eligibility check, scholarship search, "
            "route plan, and documents."
        )

        st.page_link(
            "pages/0_Login.py",
            label="Sign in",
            icon="🔐",
            use_container_width=True,
        )

        st.divider()

        st.markdown("### What you can do")
        st.markdown(
            """
- Build your study-abroad profile
- Check eligibility readiness
- Review scholarship options
- Generate route guidance
- Track document preparation
"""
        )

        st.divider()
        disclaimer(compact=True)
