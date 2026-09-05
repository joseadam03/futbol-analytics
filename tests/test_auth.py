"""Login opcional: sin config.yaml no cambia nada; con él, exige
usuario/contraseña antes de mostrar cualquier página."""

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
