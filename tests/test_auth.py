"""Login siempre obligatorio: sin config.yaml solo existe la cuenta demo
integrada; con él, sus usuarios se añaden a esa demo. En ambos casos hay
que pasar por usuario/contraseña antes de ver cualquier página. También
cubre los campos opcionales por usuario: proveedor forzado a demo y claves
propias de Wyscout/StatsBomb (que no deben filtrarse a otras sesiones)."""

from pathlib import Path

import pytest
import streamlit_authenticator as stauth
import yaml
from streamlit.testing.v1 import AppTest

from futbol_analytics import auth, tsdb

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def modo_demo(monkeypatch):
    monkeypatch.setenv("FUTBOL_ANALYTICS_FAKE", "1")
    monkeypatch.delenv("SPORTMONKS_API_TOKEN", raising=False)
    monkeypatch.setattr(tsdb, "search_players", lambda name: [])


def _app() -> AppTest:
    return AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)


def _login(at: AppTest, username: str, password: str) -> AppTest:
    """Login normal (usuario/contraseña ya conocidos) + un `run()` extra.

    Tras un login válido, streamlit-authenticator solo deja de redibujar su
    propio formulario Usuario/Contraseña en el SIGUIENTE render (el
    `st.rerun()` interno no siempre dispara dentro del propio `run()` de
    AppTest) — este segundo `run()` lo asienta, para no confundir esos
    campos con los de un formulario distinto que se muestre a continuación
    (p. ej. el de cambio de contraseña del admin).
    """
    at.text_input[0].set_value(username)
    at.text_input[1].set_value(password)
    at.button[0].click().run()
    at.run()
    return at


def _campo(at: AppTest, etiqueta: str):
    return next(ti for ti in at.text_input if ti.label == etiqueta)


def _boton(at: AppTest, etiqueta: str):
    return next(b for b in at.button if b.label == etiqueta)


def _config_con_usuario(tmp_path: Path, password: str) -> Path:
    config = {
        "credentials": {
            "usernames": {
                "recruiter": {
                    "email": "recruiter@example.com",
                    "name": "Recruiter",
                    "password": stauth.Hasher.hash(password),
                }
            }
        },
        "cookie": {"name": "test_auth", "key": "clave-de-test", "expiry_days": 1},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def _config_con_usuario_admin(tmp_path: Path, password: str, path: Path | None = None) -> Path:
    """`config.yaml` con la cuenta admin ya con contraseña propia (no la de fábrica)."""
    config = {
        "credentials": {
            "usernames": {
                auth.ADMIN_USER: {
                    "email": "admin@example.com",
                    "name": "Admin",
                    "password": stauth.Hasher.hash(password),
                }
            }
        },
        "cookie": {"name": "test_auth", "key": "clave-de-test", "expiry_days": 1},
    }
    path = path or tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def test_sin_config_pide_login_y_la_demo_integrada_entra(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", tmp_path / "no-existe.yaml")
    at = _app()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "ctx" not in at.session_state
    assert len(at.text_input) == 2

    at.text_input[0].set_value(auth.DEMO_USER)
    at.text_input[1].set_value(auth.DEMO_PASSWORD)
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["ctx"]["provider_key"] == "fake"


def test_config_propio_anade_usuarios_sin_perder_la_demo_integrada(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", _config_con_usuario(tmp_path, "clave123"))
    at = _app()
    at.run()
    at.text_input[0].set_value(auth.DEMO_USER)
    at.text_input[1].set_value(auth.DEMO_PASSWORD)
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["ctx"]["provider_key"] == "fake"


def test_con_config_pide_login_y_bloquea_sin_credenciales(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", _config_con_usuario(tmp_path, "clave123"))
    at = _app()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "ctx" not in at.session_state
    assert len(at.text_input) == 2


def test_con_config_credenciales_incorrectas_no_entra(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", _config_con_usuario(tmp_path, "clave123"))
    at = _app()
    at.run()
    at.text_input[0].set_value("recruiter")
    at.text_input[1].set_value("mala")
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "ctx" not in at.session_state
    assert any("incorrect" in e.value.lower() for e in at.error)


def test_con_config_credenciales_correctas_entra(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", _config_con_usuario(tmp_path, "clave123"))
    at = _app()
    at.run()
    at.text_input[0].set_value("recruiter")
    at.text_input[1].set_value("clave123")
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["ctx"]["provider_key"] == "fake"


def test_usuario_con_provider_fake_forzado_lo_preselecciona(monkeypatch, tmp_path):
    # Sin FUTBOL_ANALYTICS_FAKE global: solo este usuario ve la demo, por su
    # propia entrada de config.yaml, no porque el despliegue entero esté en
    # modo demo.
    monkeypatch.delenv("FUTBOL_ANALYTICS_FAKE", raising=False)
    config = {
        "credentials": {
            "usernames": {
                "recruiter": {
                    "email": "recruiter@example.com",
                    "name": "Recruiter",
                    "password": stauth.Hasher.hash("clave123"),
                    "provider": "fake",
                }
            }
        },
        "cookie": {"name": "test_auth", "key": "clave-de-test", "expiry_days": 1},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(auth, "CONFIG_PATH", path)

    at = _app()
    at.run()
    at.text_input[0].set_value("recruiter")
    at.text_input[1].set_value("clave123")
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["ctx"]["provider_key"] == "fake"


def test_admin_con_password_de_fabrica_bloquea_el_resto_de_la_app(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", tmp_path / "no-existe.yaml")
    at = _app()
    at.run()
    at.text_input[0].set_value(auth.ADMIN_USER)
    at.text_input[1].set_value(auth.ADMIN_DEFAULT_PASSWORD)
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "ctx" not in at.session_state
    assert any("fábrica" in w.value for w in at.warning)


def test_cambiar_la_password_de_fabrica_del_admin_persiste_y_desbloquea(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(auth, "CONFIG_PATH", config_path)
    at = _app()
    at.run()
    _login(at, auth.ADMIN_USER, auth.ADMIN_DEFAULT_PASSWORD)
    assert not at.exception, [str(e.value) for e in at.exception]

    _campo(at, "Contraseña actual").set_value(auth.ADMIN_DEFAULT_PASSWORD)
    _campo(at, "Contraseña nueva").set_value("Otra-Clave-9!")
    _campo(at, "Repite la contraseña nueva").set_value("Otra-Clave-9!")
    _boton(at, "Cambiar contraseña").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["ctx"]["provider_key"] == "fake"

    assert config_path.exists()
    guardado = yaml.safe_load(config_path.read_text())
    admin_guardado = guardado["credentials"]["usernames"][auth.ADMIN_USER]
    assert (
        admin_guardado["password"]
        != auth.DEFAULT_CONFIG["credentials"]["usernames"][auth.ADMIN_USER]["password"]
    )
    # La primera escritura real también renueva la clave de firma de la
    # cookie — sigue siendo la de fábrica (pública en el repo) hasta ese
    # momento, ver auth.guardar_config.
    assert guardado["cookie"]["key"] != auth.DEFAULT_CONFIG["cookie"]["key"]


def test_admin_con_password_ya_cambiada_no_bloquea(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", _config_con_usuario_admin(tmp_path, "otra-clave"))
    at = _app()
    at.run()
    _login(at, auth.ADMIN_USER, "otra-clave")
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["ctx"]["provider_key"] == "fake"


def test_nav_no_registra_la_pagina_admin_para_quien_no_es_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", tmp_path / "no-existe.yaml")
    at = _app()
    at.run()
    at.text_input[0].set_value(auth.DEMO_USER)
    at.text_input[1].set_value(auth.DEMO_PASSWORD)
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]

    with pytest.raises(ValueError):
        at.switch_page("app_pages/admin.py")


def test_pagina_admin_bloqueada_por_si_misma_para_quien_no_es_admin():
    # Guarda propia de admin.py, aparte de que la navegación ya no la
    # registre para quien no es admin (test anterior) — comprobada cargando
    # la página directamente, como el patrón "mini_app" de más abajo.
    at = AppTest.from_file(str(ROOT / "app_pages" / "admin.py"), default_timeout=60)
    at.session_state["username"] = auth.DEMO_USER
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any("solo para la cuenta admin" in e.value for e in at.error)
    assert not at.subheader


def test_pagina_admin_crea_usuario_y_persiste(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(
        auth, "CONFIG_PATH", _config_con_usuario_admin(tmp_path, "otra-clave", path=config_path)
    )
    at = _app()
    at.run()
    _login(at, auth.ADMIN_USER, "otra-clave")
    assert not at.exception, [str(e.value) for e in at.exception]

    at.switch_page("app_pages/admin.py")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any(s.value == "Usuarios actuales" for s in at.subheader)

    _campo(at, "Nombre a mostrar").set_value("Nueva Persona")
    _campo(at, "Email").set_value("nueva@example.com")
    _campo(at, "Usuario (sin espacios)").set_value("nueva_persona")
    _campo(at, "Contraseña").set_value("clave-nueva-1234")
    _campo(at, "Repite la contraseña").set_value("clave-nueva-1234")
    _boton(at, "Crear usuario").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]

    guardado = yaml.safe_load(config_path.read_text())
    assert "nueva_persona" in guardado["credentials"]["usernames"]


def test_pagina_admin_elimina_usuario(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config = {
        "credentials": {
            "usernames": {
                auth.ADMIN_USER: {
                    "email": "admin@example.com",
                    "name": "Admin",
                    "password": stauth.Hasher.hash("otra-clave"),
                },
                "borrame": {
                    "email": "borrame@example.com",
                    "name": "Borrame",
                    "password": stauth.Hasher.hash("clave123"),
                },
            }
        },
        "cookie": {"name": "test_auth", "key": "clave-de-test", "expiry_days": 1},
    }
    config_path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(auth, "CONFIG_PATH", config_path)

    at = _app()
    at.run()
    _login(at, auth.ADMIN_USER, "otra-clave")
    assert not at.exception, [str(e.value) for e in at.exception]

    at.switch_page("app_pages/admin.py")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    _boton(at, "Eliminar «borrame»").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]

    guardado = yaml.safe_load(config_path.read_text())
    assert "borrame" not in guardado["credentials"]["usernames"]


def test_pagina_admin_no_puede_eliminar_demo_ni_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", _config_con_usuario_admin(tmp_path, "otra-clave"))
    at = _app()
    at.run()
    _login(at, auth.ADMIN_USER, "otra-clave")
    assert not at.exception, [str(e.value) for e in at.exception]

    at.switch_page("app_pages/admin.py")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    # Sin más cuentas creadas desde el panel: solo queda el aviso, no el desplegable de borrado.
    assert any("vienen integradas en el código" in c.value for c in at.caption)


def test_pagina_admin_guarda_claves_de_api_opcionales(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(
        auth, "CONFIG_PATH", _config_con_usuario_admin(tmp_path, "otra-clave", path=config_path)
    )
    at = _app()
    at.run()
    _login(at, auth.ADMIN_USER, "otra-clave")
    assert not at.exception, [str(e.value) for e in at.exception]

    at.switch_page("app_pages/admin.py")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]

    _campo(at, "Nombre a mostrar").set_value("Con Claves")
    _campo(at, "Email").set_value("conclaves@example.com")
    _campo(at, "Usuario (sin espacios)").set_value("con_claves")
    _campo(at, "Contraseña").set_value("clave-nueva-1234")
    _campo(at, "Repite la contraseña").set_value("clave-nueva-1234")
    _campo(at, "Wyscout — Client ID").set_value("id-club")
    _campo(at, "Wyscout — Client Secret").set_value("secreto-club")
    _campo(at, "StatsBomb — usuario").set_value("usuario-club")
    _campo(at, "StatsBomb — contraseña").set_value("clave-club")
    _boton(at, "Crear usuario").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]

    datos = yaml.safe_load(config_path.read_text())["credentials"]["usernames"]["con_claves"]
    assert datos["wyscout_client_id"] == "id-club"
    assert datos["wyscout_client_secret"] == "secreto-club"
    assert datos["statsbomb_user"] == "usuario-club"
    assert datos["statsbomb_password"] == "clave-club"


def test_pagina_admin_sin_claves_de_api_no_las_guarda(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(
        auth, "CONFIG_PATH", _config_con_usuario_admin(tmp_path, "otra-clave", path=config_path)
    )
    at = _app()
    at.run()
    _login(at, auth.ADMIN_USER, "otra-clave")
    assert not at.exception, [str(e.value) for e in at.exception]

    at.switch_page("app_pages/admin.py")
    at.run()

    _campo(at, "Nombre a mostrar").set_value("Sin Claves")
    _campo(at, "Email").set_value("sinclaves@example.com")
    _campo(at, "Usuario (sin espacios)").set_value("sin_claves")
    _campo(at, "Contraseña").set_value("clave-nueva-1234")
    _campo(at, "Repite la contraseña").set_value("clave-nueva-1234")
    _boton(at, "Crear usuario").click().run()
    assert not at.exception, [str(e.value) for e in at.exception]

    datos = yaml.safe_load(config_path.read_text())["credentials"]["usernames"]["sin_claves"]
    assert "wyscout_client_id" not in datos
    assert "statsbomb_user" not in datos


def test_usuario_con_claves_propias_se_inyectan_en_su_sesion(monkeypatch, tmp_path):
    config = {
        "credentials": {
            "usernames": {
                "jose": {
                    "email": "jose@example.com",
                    "name": "Jose",
                    "password": stauth.Hasher.hash("clave123"),
                    "wyscout_client_id": "id-de-jose",
                    "wyscout_client_secret": "secreto-de-jose",
                    "statsbomb_user": "usuario-sb-de-jose",
                    "statsbomb_password": "clave-sb-de-jose",
                }
            }
        },
        "cookie": {"name": "test_auth", "key": "clave-de-test", "expiry_days": 1},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(auth, "CONFIG_PATH", config_path)

    # App mínima: no pasa por filter_bar_context (evita que la app real intente
    # golpear las APIs reales de Wyscout/StatsBomb al elegir ese proveedor).
    app_path = tmp_path / "mini_app.py"
    app_path.write_text(
        "import streamlit as st\n"
        "from futbol_analytics import auth\n"
        "from futbol_analytics.providers.wyscout import WyscoutProvider\n"
        "from futbol_analytics.providers.statsbomb import StatsBombProvider\n"
        "if auth.requiere_login():\n"
        "    wy = WyscoutProvider()._auth\n"
        "    sb = StatsBombProvider()._creds\n"
        "    st.write(f\"CREDS:{wy[0]}:{wy[1]}:{sb['user']}:{sb['passwd']}\")\n"
    )

    at = AppTest.from_file(str(app_path), default_timeout=60)
    at.run()
    at.text_input[0].set_value("jose")
    at.text_input[1].set_value("clave123")
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.markdown[-1].value == "CREDS:id-de-jose:secreto-de-jose:usuario-sb-de-jose:clave-sb-de-jose"
