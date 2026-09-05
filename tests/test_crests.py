"""Tests de la caché de escudos, con el cliente de TheSportsDB simulado.

Mismo patrón que test_photos.py: `crests.crest_url` solo cachea la URL,
la descarga de bytes para incrustar en el PDF la hace `photos.fetch_bytes`
(ya testeada), sin duplicar esa lógica aquí.
"""

import json

import pytest

from futbol_analytics import crests, tsdb


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(crests, "CACHE_FILE", tmp_path / "crests.json")


def test_escudo_encontrado_se_cachea(monkeypatch):
    calls = []

    def fake_search(name):
        calls.append(name)
        return [{"escudo": None}, {"escudo": "https://img/sestao.png"}]

    monkeypatch.setattr(tsdb, "search_teams", fake_search)
    assert crests.crest_url("Sestao River Club") == "https://img/sestao.png"
    # segunda llamada: sale de la caché en disco, sin tocar el cliente
    assert crests.crest_url("Sestao River Club") == "https://img/sestao.png"
    assert calls == ["Sestao River Club"]


def test_servicio_caido_devuelve_none_sin_cachear(monkeypatch):
    def fake_search(name):
        raise tsdb.ServiceUnavailable("HTTP 403")

    monkeypatch.setattr(tsdb, "search_teams", fake_search)
    assert crests.crest_url("Equipo") is None
    assert not crests.CACHE_FILE.exists()  # transitorio: se reintentará


def test_sin_escudo_se_cachea_como_none(monkeypatch):
    monkeypatch.setattr(tsdb, "search_teams", lambda name: [])
    assert crests.crest_url("Equipo Sin Escudo") is None
    assert json.loads(crests.CACHE_FILE.read_text()) == {"Equipo Sin Escudo": None}


def test_disco_de_solo_lectura_no_revienta(monkeypatch, tmp_path):
    monkeypatch.setattr(tsdb, "search_teams", lambda name: [{"escudo": "https://img/x.png"}])
    bloqueo = tmp_path / "bloqueo"
    bloqueo.write_text("no soy un directorio")
    monkeypatch.setattr(crests, "CACHE_FILE", bloqueo / "crests.json")
    assert crests.crest_url("Equipo") == "https://img/x.png"
