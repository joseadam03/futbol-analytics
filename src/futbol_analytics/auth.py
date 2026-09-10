"""Login obligatorio, con cuentas demo y admin integradas por defecto.

La app siempre pide login — en local, en `make demo`, en los tests y en
producción — así no hay ninguna ruta de código que quede sin pasar por el
gate. Sin `config.yaml` hay dos cuentas embebidas en este fichero:

- `demo` / `demo1234`: liga sintética preseleccionada (`provider: fake`), la
  puerta de entrada para un recruiter sin pedirle que configure nada. La
  contraseña se enseña en la propia pantalla de login — no es un secreto.
- `admin` / `admin`: entra igual que cualquier usuario, pero mientras la
  contraseña siga siendo la de fábrica, `requiere_login()` bloquea el resto
  de la app y obliga a cambiarla antes de nada más. Una vez cambiada (se
  guarda en `config.yaml`), desbloquea la página **Admin** — un panel para
  crear usuarios nuevos con un formulario, sin tocar YAML ni la terminal.
  `scripts/crear_usuario.py` sigue siendo la vía rápida desde la terminal
  para quien la prefiera; ambas caen en el mismo `config.yaml`.

Cada usuario puede llevar, además de sus credenciales de login, varios campos
opcionales (ver `config.example.yaml`) — todos se pueden rellenar también
desde la página **Admin** al crear el usuario, sin tocar el YAML:
- `wyscout_client_id` / `wyscout_client_secret`: sus propias claves de la API
  de Wyscout, que se usan solo en su sesión — no se comparten con el resto
  de cuentas ni hace falta ponerlas en `.env` para todo el despliegue.
- `statsbomb_user` / `statsbomb_password`: igual, pero para la API privada de
  StatsBomb (`SB_USERNAME`/`SB_PASSWORD` en la librería `statsbombpy`) — sin
  ellas, `StatsBombProvider` sigue funcionando con los open data públicos,
  que no requieren credenciales.
- `provider: fake`: le fuerza por defecto la liga sintética de demo, para dar
  acceso a alguien (un recruiter, por ejemplo) sin exponerle datos reales.
"""

from __future__ import annotations

import copy
import os
import secrets
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from streamlit_authenticator.utilities import LoginError

from .providers.statsbomb import set_session_credentials as set_statsbomb_credentials
from .providers.wyscout import set_session_credentials as set_wyscout_credentials

CONFIG_PATH = Path(os.environ.get("FUTBOL_ANALYTICS_AUTH_CONFIG", "config.yaml"))

DEMO_USER = "demo"
DEMO_PASSWORD = "demo1234"

ADMIN_USER = "admin"
ADMIN_DEFAULT_PASSWORD = "admin"

# Hashes de DEMO_PASSWORD/ADMIN_DEFAULT_PASSWORD generados con
# scripts/hash_password.py — ninguna de las dos contraseñas es secreta (la
# demo se enseña en pantalla; la de admin es la de fábrica, pensada para
# cambiarse en el primer login, no para quedarse así).
DEFAULT_CONFIG: dict[str, Any] = {
    "credentials": {
        "usernames": {
            DEMO_USER: {
                "email": "demo@example.com",
                "name": "Demo",
                "password": "$2b$12$yR4kBZPUSNhv.R3xKkvdG.75AjgME4WpDmeHkNNgScL9evg.9b8qC",
                "provider": "fake",
            },
            ADMIN_USER: {
                "email": "admin@example.com",
                "name": "Admin",
                "password": "$2b$12$x/kCSxS86ei.fVJaz/CwwOpnqYdbDkCw1NeeRFnl6BH9SRy9.6Rve",
            },
        }
    },
    "cookie": {
        "name": "futbol_analytics_auth",
        "key": "futbol-analytics-demo-cookie-key",
        "expiry_days": 30,
    },
}

_USUARIO_ACTUAL: ContextVar[dict[str, Any] | None] = ContextVar("usuario_actual", default=None)


def cargar_config() -> dict[str, Any]:
    """Config efectiva: las cuentas integradas, con `config.yaml` (si existe) añadido encima."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            propio = yaml.safe_load(f) or {}
        config["credentials"]["usernames"].update(propio.get("credentials", {}).get("usernames", {}))
        config["cookie"].update(propio.get("cookie", {}))
    return config


def guardar_config(config: dict[str, Any]) -> None:
    """Persiste `config` en CONFIG_PATH.

    No escribe las cuentas integradas (demo/admin) si siguen exactamente
    igual que su valor por defecto — evita duplicarlas en el YAML en cada
    guardado. Si alguna cambió de verdad (p. ej. la contraseña del admin
    tras el cambio obligatorio), sí se guarda: ya no coincide con el default.

    Si es el primer `config.yaml` real del despliegue (aún no existía) y
    sigue con la clave de cookie de fábrica, se genera una propia — esa
    clave firma la cookie de sesión y la de fábrica es pública (está en el
    código, en este mismo repo), así que no debe quedarse en un despliegue
    real. Como efecto colateral cierra cualquier sesión abierta con la clave
    vieja, lo cual es lo esperable justo después de cambiar una contraseña.
    """
    a_guardar = copy.deepcopy(config)
    usernames = a_guardar["credentials"]["usernames"]
    for u in (DEMO_USER, ADMIN_USER):
        if usernames.get(u) == DEFAULT_CONFIG["credentials"]["usernames"].get(u):
            usernames.pop(u, None)
    if not CONFIG_PATH.exists() and a_guardar["cookie"].get("key") == DEFAULT_CONFIG["cookie"]["key"]:
        a_guardar["cookie"]["key"] = secrets.token_hex(32)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(a_guardar, f, allow_unicode=True)


def usuario_actual() -> dict[str, Any] | None:
    """Datos del usuario logueado (name, wyscout_client_id, provider...).

    None si esta sesión aún no ha entrado.
    """
    return _USUARIO_ACTUAL.get()


def requiere_login() -> bool:
    """Pide login (demo/admin integradas + `config.yaml` si lo hay); devuelve si la app puede continuar."""
    config = cargar_config()

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
        return False
    if status is None:
        st.warning("Introduce tus credenciales para entrar")
        st.caption(f"Modo demo: usuario `{DEMO_USER}`, contraseña `{DEMO_PASSWORD}`")
        return False

    username = st.session_state.get("username")
    datos = config["credentials"]["usernames"].get(username, {})

    # admin con la contraseña de fábrica: bloquea el resto de la app hasta
    # que la cambie — ver el módulo docstring
    es_admin_por_defecto = (
        username == ADMIN_USER
        and datos.get("password") == DEFAULT_CONFIG["credentials"]["usernames"][ADMIN_USER]["password"]
    )
    if es_admin_por_defecto:
        st.warning(
            "Estás usando la contraseña de fábrica del admin — cámbiala antes de seguir "
            f"(la actual es `{ADMIN_DEFAULT_PASSWORD}`)."
        )
        try:
            cambiada = authenticator.reset_password(
                ADMIN_USER,
                key="reset_admin_password",
                fields={
                    "Form name": "Cambiar contraseña",
                    "Current password": "Contraseña actual",
                    "New password": "Contraseña nueva",
                    "Repeat password": "Repite la contraseña nueva",
                    "Reset": "Cambiar contraseña",
                },
            )
        except Exception as e:
            st.error(str(e))
            cambiada = None
        if cambiada:
            guardar_config(config)
            st.success("Contraseña actualizada.")
            st.rerun()
        with st.sidebar:
            authenticator.logout("Salir", "sidebar")
        st.stop()

    _USUARIO_ACTUAL.set(datos)
    if datos.get("wyscout_client_id") and datos.get("wyscout_client_secret"):
        set_wyscout_credentials(datos["wyscout_client_id"], datos["wyscout_client_secret"])
    if datos.get("statsbomb_user") and datos.get("statsbomb_password"):
        set_statsbomb_credentials(datos["statsbomb_user"], datos["statsbomb_password"])

    with st.sidebar:
        st.caption(f"Sesión: {st.session_state.get('name')}")
        authenticator.logout("Salir", "sidebar")

    return True
