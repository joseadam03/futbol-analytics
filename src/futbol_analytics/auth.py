"""Login opcional para despliegues públicos.

Sin `config.yaml` (el caso por defecto: local, `make demo`, tests de
AppTest) la app no pide login y se comporta exactamente igual que antes —
así ningún flujo existente se rompe. Para exigir login en un despliegue
propio, copia `config.example.yaml` a `config.yaml`, dale un usuario por
persona (contraseña generada con `scripts/hash_password.py`, nunca en
texto plano) y monta ese fichero en el contenedor; `FUTBOL_ANALYTICS_AUTH_CONFIG`
apunta a otra ruta si no está en el directorio de trabajo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from streamlit_authenticator.utilities import LoginError

CONFIG_PATH = Path(os.environ.get("FUTBOL_ANALYTICS_AUTH_CONFIG", "config.yaml"))


def _cargar_config() -> dict[str, Any] | None:
    if not CONFIG_PATH.exists():
        return None
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def requiere_login() -> bool:
    """Pide login si hay `config.yaml`; devuelve si la app puede continuar."""
    config = _cargar_config()
    if config is None:
        return True

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )
    try:
        authenticator.login()
    except LoginError as e:
        st.error(str(e))
        return False

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Usuario o contraseña incorrectos")
    elif status is None:
        st.warning("Introduce tus credenciales para entrar")
    else:
        with st.sidebar:
            st.caption(f"Sesión: {st.session_state.get('name')}")
            authenticator.logout("Salir", "sidebar")

    return bool(status)
