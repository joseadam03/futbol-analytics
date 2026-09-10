"""Panel admin: crear usuarios desde la app, sin tocar YAML ni terminal.

Solo visible/accesible para la cuenta `admin` (ver auth.py) — el enlace en
la navegación ya está condicionado a eso en streamlit_app.py, pero la propia
página también se protege por si alguien llega aquí con la URL directa.

El formulario es manual (no `Authenticate.register_user()`): esa función
crea su propio `CookieManager`, y ya hay uno vivo desde el login de
`requiere_login()` en esta misma página — dos en la misma sesión chocan
(mismo id de componente `key="init"`, comprobado en un test real). Además
así la validación queda igual de simple que en `scripts/crear_usuario.py`,
que sigue siendo la otra vía para crear cuentas.
"""

import streamlit as st
import streamlit_authenticator as stauth

from futbol_analytics import auth

if st.session_state.get("username") != auth.ADMIN_USER:
    st.error("Esta página es solo para la cuenta admin.")
    st.stop()

st.title("🛠️ Admin")
st.caption("Crea cuentas nuevas para que cada quien entre con las suyas — sin editar config.yaml a mano.")

config = auth.cargar_config()

st.subheader("Usuarios actuales")
st.table(
    [
        {"Usuario": u, "Nombre": d.get("name", ""), "Email": d.get("email", "")}
        for u, d in sorted(config["credentials"]["usernames"].items())
    ]
)

st.subheader("Crear usuario")
with st.form("crear_usuario", clear_on_submit=True):
    nombre = st.text_input("Nombre a mostrar")
    email = st.text_input("Email")
    usuario = st.text_input("Usuario (sin espacios)")
    password = st.text_input("Contraseña", type="password")
    password_repetida = st.text_input("Repite la contraseña", type="password")
    enviado = st.form_submit_button("Crear usuario")

if enviado:
    usuario = usuario.strip()
    if not usuario or " " in usuario:
        st.error("El usuario no puede estar vacío ni llevar espacios.")
    elif usuario in config["credentials"]["usernames"]:
        st.error(f"Ya existe un usuario «{usuario}».")
    elif not password:
        st.error("La contraseña no puede estar vacía.")
    elif password != password_repetida:
        st.error("Las dos contraseñas no coinciden.")
    else:
        config["credentials"]["usernames"][usuario] = {
            "email": email,
            "name": nombre or usuario,
            "password": stauth.Hasher.hash(password),
        }
        auth.guardar_config(config)
        st.success(f"Usuario «{usuario}» creado — ya puede entrar con su contraseña.")
        st.rerun()
