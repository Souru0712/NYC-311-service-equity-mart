import streamlit as st


def is_dev() -> bool:
    """Returns True when DEV_MODE=true is set in st.secrets.
    On Streamlit Cloud, omit DEV_MODE entirely so public users never see dev controls.
    Locally, set DEV_MODE = 'true' in .streamlit/secrets.toml.
    """
    try:
        return str(st.secrets.get("DEV_MODE", "false")).lower() == "true"
    except Exception:
        return False
