"""Fútbol Analytics — app de análisis de jugadores y equipos.

Ejecutar:  streamlit run streamlit_app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

import app_common as ac
from futbol_analytics import auth

load_dotenv()  # credenciales opcionales (p. ej. Wyscout) desde .env

# favicon propio (balón en el azul de marca) en vez del emoji genérico del
# navegador; si el asset no está por lo que sea, cae al emoji en vez de romper
FAVICON = Path(__file__).parent / "docs" / "favicon.png"
st.set_page_config(
    page_title="Fútbol Analytics", page_icon=str(FAVICON) if FAVICON.exists() else "⚽", layout="wide"
)

# Sin config.yaml no hay gate (local, make demo, tests) — ver auth.py.
if not auth.requiere_login():
    st.stop()

st.sidebar.title("⚽ Fútbol Analytics")
st.session_state["ctx"] = ac.sidebar_context()

pages = st.navigation(
    [
        st.Page("app_pages/inicio.py", title="Inicio", icon="🏠", default=True),
        st.Page("app_pages/buscador.py", title="Buscador", icon="🔍"),
        st.Page("app_pages/jugador.py", title="Jugador", icon="📊"),
        st.Page("app_pages/comparar.py", title="Comparar", icon="⚔️"),
        st.Page("app_pages/encaje.py", title="Encaje", icon="🧩"),
        st.Page("app_pages/equipos.py", title="Equipos", icon="🛡️"),
        st.Page("app_pages/informe_equipo.py", title="Informe de equipo", icon="📋"),
        st.Page("app_pages/partido.py", title="Partido", icon="🥅"),
        st.Page("app_pages/competicion.py", title="Competición", icon="🌍"),
        st.Page("app_pages/secuencias.py", title="Secuencias", icon="🧵"),
        st.Page("app_pages/evolucion.py", title="Evolución", icon="📈"),
        st.Page("app_pages/modelo_xg.py", title="Modelo xG", icon="🎯"),
        st.Page("app_pages/metodologia.py", title="Metodología", icon="📖"),
    ],
    # Streamlit 1.63 colapsa el menú tras 12 páginas ("View 3 more"); con 13
    # páginas eso escondía Evolución, Modelo xG y Metodología por defecto.
    expanded=True,
)
pages.run()
