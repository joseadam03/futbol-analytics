"""Tests de interfaz: la app completa renderiza sobre la liga sintética, sin red.

Con FUTBOL_ANALYTICS_FAKE=1 el proveedor demo es el primero del registro y
la barra lateral lo selecciona por defecto, así que AppTest ejecuta el
mismo código que ve un usuario — carga de datos, sidebar y cada página —
en segundos y de forma determinista.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from futbol_analytics import photos, tsdb

ROOT = Path(__file__).resolve().parents[1]
PAGINAS = [
    "inicio",
    "buscador",
    "jugador",
    "comparar",
    "encaje",
    "equipos",
    "informe_equipo",
    "competicion",
    "secuencias",
    "evolucion",
    "modelo_xg",
    "metodologia",
]


@pytest.fixture(autouse=True)
def modo_demo(monkeypatch, tmp_path):
    monkeypatch.setenv("FUTBOL_ANALYTICS_FAKE", "1")
    monkeypatch.setattr(tsdb, "search_players", lambda name: [])  # nada de red
    monkeypatch.setattr(photos, "CACHE_FILE", tmp_path / "photos.json")  # ni de disco compartido


def _app() -> AppTest:
    return AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)


def test_la_app_arranca_en_modo_demo():
    at = _app()
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    ctx = at.session_state["ctx"]
    assert ctx["provider_key"] == "fake"
    assert len(ctx["table"]) == 22


@pytest.mark.parametrize("pagina", PAGINAS)
def test_cada_pagina_renderiza_sin_excepciones(pagina):
    at = _app()
    at.switch_page(f"app_pages/{pagina}.py")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
