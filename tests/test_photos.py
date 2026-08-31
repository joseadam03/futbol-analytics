"""Tests de la caché de fotos, con el cliente de TheSportsDB simulado."""

import json

import pytest
import requests

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


class FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


def test_fetch_bytes_devuelve_el_contenido_si_hay_200(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(200, b"\x89PNG..."))
    assert photos.fetch_bytes("https://img/x.png") == b"\x89PNG..."


def test_fetch_bytes_devuelve_none_si_falla_el_http(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **kw: FakeResponse(404))
    assert photos.fetch_bytes("https://img/no-existe.png") is None


def test_fetch_bytes_devuelve_none_si_hay_error_de_red(monkeypatch):
    def fake_get(url, **kw):
        raise requests.RequestException("timeout")

    monkeypatch.setattr(requests, "get", fake_get)
    assert photos.fetch_bytes("https://img/x.png") is None
