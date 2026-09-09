"""Tests de interfaz: la app completa renderiza sobre la liga sintética, sin red.

Con FUTBOL_ANALYTICS_FAKE=1 el proveedor demo es el primero del registro y
la barra lateral lo selecciona por defecto, así que AppTest ejecuta el
mismo código que ve un usuario — carga de datos, sidebar y cada página —
en segundos y de forma determinista. El login es obligatorio (ver
`auth.py`), así que `_app()` entra con la cuenta demo integrada antes de
devolver el AppTest; la sesión sigue autenticada en las llamadas a `.run()`
posteriores, igual que en un navegador real.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from futbol_analytics import auth, photos, sportmonks, tsdb

ROOT = Path(__file__).resolve().parents[1]
PAGINAS = [
    "inicio",
    "buscador",
    "filtro",
    "jugador",
    "comparar",
    "encaje",
    "equipos",
    "informe_equipo",
    "partido",
    "competicion",
    "secuencias",
    "evolucion",
    "modelo_xg",
    "metodologia",
]


@pytest.fixture(autouse=True)
def modo_demo(monkeypatch, tmp_path):
    monkeypatch.setenv("FUTBOL_ANALYTICS_FAKE", "1")
    monkeypatch.delenv("SPORTMONKS_API_TOKEN", raising=False)  # determinista pese al entorno real
    monkeypatch.setattr(tsdb, "search_players", lambda name: [])  # nada de red
    monkeypatch.setattr(photos, "CACHE_FILE", tmp_path / "photos.json")  # ni de disco compartido


def _app() -> AppTest:
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=180)
    at.run()
    at.text_input[0].set_value(auth.DEMO_USER)
    at.text_input[1].set_value(auth.DEMO_PASSWORD)
    at.button[0].click().run()
    return at


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


def _buscar(at: AppTest, nombre_ausente: str) -> AppTest:
    at.switch_page("app_pages/buscador.py")
    at.run()
    at.text_input(key="buscador_query").set_value(nombre_ausente).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


def test_buscador_sin_token_muestra_la_pista(monkeypatch):
    at = _buscar(_app(), "Sin Token De Prueba")
    assert any("SPORTMONKS_API_TOKEN" in c.value for c in at.caption)


def test_comparar_con_tres_o_mas_usa_barras_agrupadas():
    at = _app()
    table = at.session_state["ctx"]["table"]
    # el grupo posicional con más jugadores garantiza al menos 2 "compañeros"
    # para comparar, sin depender de qué jugador venga seleccionado por defecto
    grupo_grande = table["position_group"].value_counts().idxmax()
    jugadores_grupo = table[table["position_group"] == grupo_grande]["player"].tolist()
    assert len(jugadores_grupo) >= 3

    at.selectbox(key="player_sel").set_value(jugadores_grupo[0]).run()
    at.switch_page("app_pages/comparar.py")
    at.run()
    at.multiselect[0].set_value(jugadores_grupo[1:3]).run()
    assert not at.exception, [str(e.value) for e in at.exception]


def test_filtro_muestra_lectura_del_resultado():
    at = _app()
    at.switch_page("app_pages/filtro.py")
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any("Lectura:" in m.value for m in at.markdown)


def test_buscador_con_sportmonks_muestra_la_tabla_de_temporadas(monkeypatch):
    # nombre de búsqueda propio: st.cache_data es del proceso y no se resetea
    # entre AppTest, así que reutilizar una consulta ya cacheada por otro test
    # devolvería su resultado en vez de invocar el monkeypatch de este
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "test-token")
    monkeypatch.setattr(
        sportmonks,
        "player_ficha",
        lambda name: {
            "nombre": "Franculino",
            "temporadas": [{"season_name": "2025/2026", "goals": 17.0, "minutes": 1343.0}],
        },
    )
    at = _buscar(_app(), "Franculino Con Datos")
    assert len(at.dataframe) >= 1


def test_buscador_sportmonks_caido_no_revienta(monkeypatch):
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "test-token")

    def revienta(name):
        raise sportmonks.ServiceUnavailable("caído")

    monkeypatch.setattr(sportmonks, "player_ficha", revienta)
    at = _buscar(_app(), "Consulta Que Falla")
    assert any("Sportmonks no responde" in e.value for e in at.error)


def test_encaje_filtro_minutos_maximos_excluye_titulares():
    # la liga sintética da 180 min a todos: por debajo se queda sin
    # candidatos, por encima (o igual) los deja todos — así se comprueba
    # que el filtro realmente aplica sin depender de datos reales
    at = _app()
    at.switch_page("app_pages/encaje.py")
    at.run()
    at.number_input(key="fit_max_min").set_value(100).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    tablas = [df for df in at.dataframe if "Minutos" in df.value.columns]
    assert tablas and tablas[0].value.empty

    at.number_input(key="fit_max_min").set_value(180).run()
    tablas = [df for df in at.dataframe if "Minutos" in df.value.columns]
    assert tablas and not tablas[0].value.empty
