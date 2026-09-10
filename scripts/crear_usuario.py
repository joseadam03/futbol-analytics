"""Crea o actualiza un usuario en config.yaml sin tener que editarlo a mano.

La cuenta demo integrada (ver auth.py) siempre funciona sin hacer nada, pero
fuerza la liga sintética — para entrar con datos reales (StatsBomb open data,
o Wyscout con tus propias claves) hace falta una cuenta propia. Este script
hace en un solo paso lo que antes eran tres (copiar config.example.yaml,
generar el hash de la contraseña, pegarlo a mano en el YAML): pide tus datos,
crea config.yaml si no existe (con una clave de cookie aleatoria) y guarda tu
contraseña ya hasheada, nunca en texto plano.

Uso:

    python scripts/crear_usuario.py
"""

from __future__ import annotations

from getpass import getpass

import streamlit_authenticator as stauth

from futbol_analytics.auth import CONFIG_PATH, cargar_config, guardar_config


def main() -> None:
    config = cargar_config()

    username = input("Usuario (sin espacios): ").strip()
    if not username:
        raise SystemExit("El usuario no puede estar vacío.")
    name = input("Nombre a mostrar: ").strip() or username
    email = input("Email: ").strip()
    password = getpass("Contraseña: ")
    if not password:
        raise SystemExit("La contraseña no puede estar vacía.")
    if password != getpass("Repite la contraseña: "):
        raise SystemExit("Las dos contraseñas no coinciden.")

    config["credentials"]["usernames"][username] = {
        "email": email,
        "name": name,
        "password": stauth.Hasher.hash(password),
    }

    guardar_config(config)

    print(f"\nListo — usuario «{username}» guardado en {CONFIG_PATH}.")
    print("Arranca la app (run_windows.bat o `make run`) y entra con ese usuario y contraseña.")


if __name__ == "__main__":
    main()
