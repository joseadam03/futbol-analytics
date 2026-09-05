"""Login opcional: sin config.yaml no cambia nada; con él, exige
usuario/contraseña antes de mostrar cualquier página. También cubre los dos
campos opcionales por usuario: proveedor forzado a demo y claves de Wyscout
propias (que no deben filtrarse a otras sesiones)."""

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


def test_sin_config_no_pide_login(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", tmp_path / "no-existe.yaml")
    at = _app()
    at.run()
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


def test_usuario_con_claves_wyscout_propias_se_inyectan_en_su_sesion(monkeypatch, tmp_path):
    config = {
        "credentials": {
            "usernames": {
                "jose": {
                    "email": "jose@example.com",
                    "name": "Jose",
                    "password": stauth.Hasher.hash("clave123"),
                    "wyscout_client_id": "id-de-jose",
                    "wyscout_client_secret": "secreto-de-jose",
                }
            }
        },
        "cookie": {"name": "test_auth", "key": "clave-de-test", "expiry_days": 1},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(auth, "CONFIG_PATH", config_path)

    # App mínima: no pasa por sidebar_context (evita que la app real intente
    # golpear la API real de Wyscout al elegir ese proveedor).
    app_path = tmp_path / "mini_app.py"
    app_path.write_text(
        "import streamlit as st\n"
        "from futbol_analytics import auth\n"
        "from futbol_analytics.providers.wyscout import WyscoutProvider\n"
        "if auth.requiere_login():\n"
        '    st.write(f"CREDS:{WyscoutProvider()._auth[0]}:{WyscoutProvider()._auth[1]}")\n'
    )

    at = AppTest.from_file(str(app_path), default_timeout=60)
    at.run()
    at.text_input[0].set_value("jose")
    at.text_input[1].set_value("clave123")
    at.button[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.markdown[-1].value == "CREDS:id-de-jose:secreto-de-jose"
