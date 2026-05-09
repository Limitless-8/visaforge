import streamlit as st
from urllib.parse import urlparse, parse_qs
from services.auth_service import reset_password_with_token

st.set_page_config(page_title="Reset Password", layout="centered")

query = st.query_params
token = query.get("token")

st.title("Reset Password")

if not token:
    st.error("Invalid reset link")
else:
    new_password = st.text_input("New Password", type="password")

    if st.button("Reset Password"):
        try:
            reset_password_with_token(token, new_password)
            st.success("Password updated successfully")
        except Exception as e:
            st.error(str(e))