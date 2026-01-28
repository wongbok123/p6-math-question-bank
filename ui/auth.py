"""
Authentication module for P6 Math Question Bank.
Provides site-wide password protection.
"""

import streamlit as st

SITE_PASSWORD = "p6math2025"


def check_authentication():
    """Check if user is authenticated. If not, show login form and stop execution."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Show login form
    st.title("P6 Math Question Bank")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log In"):
                if password == SITE_PASSWORD:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect password")
    st.stop()


def show_logout_button():
    """Show logout button in sidebar if user is authenticated."""
    if st.session_state.get("authenticated"):
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.session_state.pop("edit_mode_unlocked", None)
            st.rerun()
