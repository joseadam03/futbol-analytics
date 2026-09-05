"""Login obligatorio, con un usuario demo integrado por defecto.

La app siempre pide login — en local, en `make demo`, en los tests y en
producción — así no hay ninguna ruta de código que quede sin pasar por el
gate. Sin `config.yaml` se usa un único usuario embebido en este fichero,
`demo` / `demo1234`, con la liga sintética preseleccionada
(`provider: fake`): es la puerta de entrada para un recruiter sin pedirle
que configure nada ni exponerle datos reales. La contraseña se enseña en la
propia pantalla de login (no es un secreto: es la cuenta pública de demo).

Para un despliegue propio con usuarios reales, copia `config.example.yaml` a
`config.yaml` (contraseñas generadas con `scripts/hash_password.py`, nunca
en texto plano). Sus usuarios se **añaden** a la demo integrada, no la
sustituyen, así el acceso de demo sigue funcionando aunque `config.yaml`
solo defina cuentas nuevas. `FUTBOL_ANALYTICS_AUTH_CONFIG` apunta a otra
ruta si no está en el directorio de trabajo.

Cada usuario puede llevar, además de sus credenciales de login, dos campos
opcionales (ver `config.example.yaml`):
- `wyscout_client_id` / `wyscout_client_secret`: sus propias claves de la API
  de Wyscout, que se usan solo en su sesión — no se comparten con el resto
  de cuentas ni hace falta ponerlas en `.env` para todo el despliegue.
- `provider: fake`: le fuerza por defecto la liga sintética de demo, para dar
  acceso a alguien (un recruiter, por ejemplo) sin exponerle datos reales.
"""

from __future__ import annotations

import copy
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from streamlit_authenticator.utilities import LoginError

from .providers.wyscout import set_session_credentials

CONFIG_PATH = Path(os.environ.get("FUTBOL_ANALYTICS_AUTH_CONFIG", "config.yaml"))

DEMO_USER = "demo"
DEMO_PASSWORD = "demo1234"

# Hash de DEMO_PASSWORD generado con scripts/hash_password.py — la contraseña
# en sí se enseña en la pantalla de login, así que no hace falta mantenerla
# en secreto ni fuera del repo.
DEFAULT_CONFIG: dict[str, Any] = {
    "credentials": {
        "usernames": {
            DEMO_USER: {
                "email": "demo@example.com",
                "name": "Demo",
                "password": "$2b$12$yR4kBZPUSNhv.R3xKkvdG.75AjgME4WpDmeHkNNgScL9evg.9b8qC",
                "provider": "fake",
            }
        }
    },
    "cookie": {
        "name": "futbol_analytics_auth",
        "key": "futbol-analytics-demo-cookie-key",
        "expiry_days": 30,
    },
}

_USUARIO_ACTUAL: ContextVar[dict[str, Any] | None] = ContextVar("usuario_actual", default=None)


def _cargar_config() -> dict[str, Any]:
    """Config efectiva: la demo integrada, con `config.yaml` (si existe) añadido encima."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            propio = yaml.safe_load(f) or {}
        config["credentials"]["usernames"].update(propio.get("credentials", {}).get("usernames", {}))
        config["cookie"].update(propio.get("cookie", {}))
    return config


def usuario_actual() -> dict[str, Any] | None:
    """Datos del usuario logueado (name, wyscout_client_id, provider...).

    None si esta sesión aún no ha entrado.
    """
    return _USUARIO_ACTUAL.get()


def requiere_login() -> bool:
    """Pide login (demo integrada + `config.yaml` si lo hay); devuelve si la app puede continuar."""
    config = _cargar_config()

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
        st.caption(f"Modo demo: usuario `{DEMO_USER}`, contraseña `{DEMO_PASSWORD}`")
    else:
        datos = config["credentials"]["usernames"].get(st.session_state.get("username"), {})
        _USUARIO_ACTUAL.set(datos)
        if datos.get("wyscout_client_id") and datos.get("wyscout_client_secret"):
            set_session_credentials(datos["wyscout_client_id"], datos["wyscout_client_secret"])

        with st.sidebar:
            st.caption(f"Sesión: {st.session_state.get('name')}")
            authenticator.logout("Salir", "sidebar")

    return bool(status)
