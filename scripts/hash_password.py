"""Genera el hash bcrypt de una contraseña para config.yaml (login opcional).

La contraseña en texto plano no debe llegar nunca a config.yaml ni a un
commit: este script la pide de forma oculta (getpass) y solo imprime el
hash, listo para pegar en el campo `password` de un usuario.

Uso:

    python scripts/hash_password.py
"""

from __future__ import annotations

from getpass import getpass

import streamlit_authenticator as stauth


def main() -> None:
    password = getpass("Contraseña: ")
    if password != getpass("Repite la contraseña: "):
        raise SystemExit("Las dos contraseñas no coinciden.")
    print(stauth.Hasher.hash(password))


if __name__ == "__main__":
    main()
