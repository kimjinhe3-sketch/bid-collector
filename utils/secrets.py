"""Secret resolution: st.secrets (cloud) > os.environ (.env loaded) > None."""
from __future__ import annotations

import os


def get_secret(key: str, default: str | None = None) -> str | None:
    # st.secrets only works when Streamlit runtime is active
    try:
        import streamlit as st  # type: ignore
        try:
            if key in st.secrets:
                val = st.secrets[key]
                if val:
                    return str(val)
        except Exception:
            pass
    except ImportError:
        pass
    return os.environ.get(key, default)
