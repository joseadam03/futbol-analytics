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
ac.inject_css()

# Login siempre obligatorio, con usuario demo integrado — ver auth.py.
if not auth.requiere_login():
    st.stop()

st.sidebar.title("⚽ Fútbol Analytics")
st.session_state["ctx"] = ac.sidebar_context()

pages = st.navigation(
    # Agrupado por secciones (Streamlit >=1.36) en vez de una lista plana de 14
    # páginas: con tantas páginas, un solo bloque sin jerarquía es lo que hacía
    # que el menú se viera anticuado/desordenado — la sección ya cuenta parte
    # de la historia antes de leer el nombre de cada página.
    {
        "": [st.Page("app_pages/inicio.py", title="Inicio", icon="🏠", default=True)],
        "Jugadores": [
            st.Page("app_pages/buscador.py", title="Buscador", icon="🔍"),
            st.Page("app_pages/filtro.py", title="Filtro avanzado", icon="🎚️"),
            st.Page("app_pages/jugador.py", title="Jugador", icon="📊"),
            st.Page("app_pages/comparar.py", title="Comparar", icon="⚔️"),
        ],
        "Equipos": [
            st.Page("app_pages/encaje.py", title="Encaje", icon="🧩"),
            st.Page("app_pages/equipos.py", title="Equipos", icon="🛡️"),
            st.Page("app_pages/informe_equipo.py", title="Informe de equipo", icon="📋"),
            st.Page("app_pages/partido.py", title="Partido", icon="🥅"),
        ],
        "Competición": [
            st.Page("app_pages/competicion.py", title="Competición", icon="🌍"),
            st.Page("app_pages/secuencias.py", title="Secuencias", icon="🧵"),
            st.Page("app_pages/evolucion.py", title="Evolución", icon="📈"),
            st.Page("app_pages/modelo_xg.py", title="Modelo xG", icon="🎯"),
        ],
        "Ayuda": [st.Page("app_pages/metodologia.py", title="Metodología", icon="📖")],
    },
    # Streamlit colapsa el menú a partir de cierto número de páginas ("View X
    # more"); con 14 páginas eso escondía las últimas por defecto.
    expanded=True,
)
pages.run()
