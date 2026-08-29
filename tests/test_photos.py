"""Tests de la caché de fotos, con el cliente de TheSportsDB simulado."""

import json

import pytest

from futbol_analytics import photos, tsdb


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(photos, "CACHE_FILE", tmp_path / "photos.json")


def test_foto_encontrada_se_cachea(monkeypatch):
    calls = []

    def fake_search(name):
        calls.append(name)
        return [{"foto": None}, {"foto": "https://img/dju.png"}]

    monkeypatch.setattr(tsdb, "search_players", fake_search)
    assert photos.photo_url("Franculino Djú") == "https://img/dju.png"
    # segunda llamada: sale de la caché en disco, sin tocar el cliente
    assert photos.photo_url("Franculino Djú") == "https://img/dju.png"
    assert calls == ["Franculino Djú"]


def test_servicio_caido_devuelve_none_sin_cachear(monkeypatch):
    def fake_search(name):
        raise tsdb.ServiceUnavailable("HTTP 403")

    monkeypatch.setattr(tsdb, "search_players", fake_search)
    assert photos.photo_url("Franculino Djú") is None
    assert not photos.CACHE_FILE.exists()  # transitorio: se reintentará


def test_sin_foto_se_cachea_como_none(monkeypatch):
    monkeypatch.setattr(tsdb, "search_players", lambda name: [])
    assert photos.photo_url("Jugador Sin Foto") is None
    assert json.loads(photos.CACHE_FILE.read_text()) == {"Jugador Sin Foto": None}


def test_disco_de_solo_lectura_no_revienta(monkeypatch, tmp_path):
    monkeypatch.setattr(tsdb, "search_players", lambda name: [{"foto": "https://img/x.png"}])
    # CACHE_FILE apunta a un directorio que no se puede crear (es un fichero)
    bloqueo = tmp_path / "bloqueo"
    bloqueo.write_text("no soy un directorio")
    monkeypatch.setattr(photos, "CACHE_FILE", bloqueo / "photos.json")
    assert photos.photo_url("Jugador") == "https://img/x.png"
