"""Fútbol Analytics — app de análisis de jugadores y equipos.

Ejecutar:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

import app_common as ac

st.set_page_config(page_title="Fútbol Analytics", page_icon="⚽", layout="wide")

st.sidebar.title("⚽ Fútbol Analytics")
st.session_state["ctx"] = ac.sidebar_context()

pages = st.navigation(
    [
        st.Page("app_pages/inicio.py", title="Inicio", icon="🏠", default=True),
        st.Page("app_pages/buscador.py", title="Buscador", icon="🔍"),
        st.Page("app_pages/jugador.py", title="Jugador", icon="📊"),
        st.Page("app_pages/comparar.py", title="Comparar", icon="⚔️"),
        st.Page("app_pages/equipos.py", title="Equipos", icon="🛡️"),
        st.Page("app_pages/competicion.py", title="Competición", icon="🌍"),
        st.Page("app_pages/metodologia.py", title="Metodología", icon="📖"),
    ]
)
pages.run()
