"""Page 0 — Login."""
from __future__ import annotations

import streamlit as st

from components.ui import disclaimer, render_sidebar
from config.settings import settings
from services.auth_service import (
    authenticate,
    is_logged_in,
    login_session,
)
from services.profile_service import list_profiles_for_user

st.set_page_config(
    page_title="Login · VisaForge",
    page_icon="🔐",
    layout="centered",
)

render_sidebar()

st.markdown(
    """
<style>
.login-shell {
    max-width: 980px;
    margin: 0 auto;
    padding-top: 28px;
}

.login-hero {
    background: linear-gradient(135deg,#4f46e5 0%,#2563eb 58%,#14b8a6 100%);
    color: white;
    border-radius: 28px;
    padding: 34px 36px;
    box-shadow: 0 28px 70px rgba(37,99,235,0.24);
    margin-bottom: 24px;
}

.login-hero h1 {
    margin: 0 0 10px 0;
    font-size: 2.35rem;
    font-weight: 900;
}

.login-hero p {
    margin: 0;
    font-size: 1.02rem;
    opacity: 0.92;
    line-height: 1.65;
}

.login-card {
    background: rgba(255,255,255,0.88);
    border: 1px solid rgba(148,163,184,0.24);
    border-radius: 26px;
    padding: 28px;
    box-shadow: 0 20px 55px rgba(15,23,42,0.08);
}

.login-note {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    color: #1d4ed8;
    border-radius: 18px;
    padding: 16px 18px;
    font-weight: 700;
    margin-bottom: 18px;
}

.login-muted {
    color: #64748b;
    font-size: 0.92rem;
    line-height: 1.6;
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

.stPageLink a:hover {
    transform:translateY(-2px);
    box-shadow:0 18px 36px rgba(37,99,235,0.28) !important;
}


.stPageLink a p {
    color:white !important;
    font-weight:800 !important;
}

</style>
""",
    unsafe_allow_html=True,
)

if is_logged_in():
    from services.auth_service import get_current_user

    current_user = get_current_user()

    current_role = (
        current_user.get("role")
        if isinstance(current_user, dict)
        else getattr(current_user, "role", None)
    )

    if current_role == "admin":
        st.switch_page("pages/8_Admin.py")
    else:
        st.switch_page("pages/7_Dashboard.py")

st.markdown(
    f"""
<div class="login-shell">
    <div class="login-hero">
        <h1>Welcome back to {settings.APP_NAME}</h1>
        <p>{settings.APP_TAGLINE}</p>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

left, right = st.columns([1.15, 0.85])

with left:
    with st.container(border=True):
        st.markdown("## Sign in")
        st.caption("Access your VisaForge dashboard, admin tools, and saved application progress.")

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input(
                "Email",
                autocomplete="username",
                placeholder="you@example.com",
            )

            password = st.text_input(
                "Password",
                type="password",
                autocomplete="current-password",
                placeholder="Enter your password",
            )

            submitted = st.form_submit_button(
                "Sign in",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            if not email or not password:
                st.error("Please enter your email and password.")
            else:
                user = authenticate(email, password)

                if user is None:
                    st.error("Invalid email or password. Please try again.")
                else:
                    login_session(user)

                    if user.is_admin():
                        st.switch_page("pages/8_Admin.py")
                    else:
                        has_profile = len(list_profiles_for_user(user.id)) > 0

                        if has_profile:
                            st.switch_page("pages/7_Dashboard.py")
                        else:
                            st.switch_page("pages/1_Profile.py")


with right:
    with st.container(border=True):
        st.markdown("### New here?")
        st.write(
            "Create an account to start your study-abroad profile, check eligibility, "
            "compare scholarships, and prepare your route plan."
        )

        st.page_link(
            "pages/0_Register.py",
            label="Create an account →",
            icon="📝",
            use_container_width=True,
        )

        st.divider()

        with st.expander("Forgot password?"):
            email_fp = st.text_input("Enter your email", key="forgot_password_email")

            if st.button("Send reset link", use_container_width=True):
                from services.auth_service import create_password_reset

                if create_password_reset(email_fp):
                    st.success("Reset link sent to your email.")
                else:
                    st.error("Email not found.")

        st.divider()
        disclaimer(compact=True)
