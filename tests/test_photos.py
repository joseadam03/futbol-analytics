"""Tests de photos.py con la red simulada: sin llamadas reales.

Cubren el caso que rompía la app: TheSportsDB detrás de Cloudflare
devolviendo un challenge HTML (403/429/503) en lugar de JSON.
"""

import json

import pytest
import requests

from futbol_analytics import photos


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("body is not JSON")
        return self._payload


CLOUDFLARE_CHALLENGE = FakeResponse(status_code=403, payload=None)
VALID_PAYLOAD = {
    "player": [
        {"strSport": "Basketball", "strCutout": "https://img/otro.png"},
        {"strSport": "Soccer", "strCutout": "https://img/dju.png", "strThumb": "https://img/thumb.png"},
    ]
}


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(photos, "CACHE_FILE", tmp_path / "photos.json")
    monkeypatch.setattr(photos, "_consecutive_failures", 0)


def make_get(responses, calls):
    def fake_get(url, **kwargs):
        calls.append(url)
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    return fake_get


def test_cloudflare_challenge_devuelve_none_sin_cachear(monkeypatch):
    calls = []
    monkeypatch.setattr(photos.requests, "get", make_get([CLOUDFLARE_CHALLENGE], calls))
    assert photos.photo_url("Francisco Dju") is None
    assert not photos.CACHE_FILE.exists()  # transitorio: se reintentará en otra ejecución


def test_timeout_devuelve_none(monkeypatch):
    calls = []
    monkeypatch.setattr(photos.requests, "get", make_get([requests.Timeout("boom")], calls))
    assert photos.photo_url("Francisco Dju") is None
    assert not photos.CACHE_FILE.exists()


def test_respuesta_valida_cachea_la_url(monkeypatch):
    calls = []
    monkeypatch.setattr(
        photos.requests, "get", make_get([FakeResponse(payload=VALID_PAYLOAD)], calls)
    )
    assert photos.photo_url("Francisco Dju") == "https://img/dju.png"
    # segunda llamada: sale de la caché en disco, sin tocar la red
    assert photos.photo_url("Francisco Dju") == "https://img/dju.png"
    assert len(calls) == 1


def test_sin_foto_se_cachea_como_none(monkeypatch):
    calls = []
    monkeypatch.setattr(photos.requests, "get", make_get([FakeResponse(payload={"player": None})], calls))
    assert photos.photo_url("Francisco Dju") is None
    assert json.loads(photos.CACHE_FILE.read_text()) == {"Francisco Dju": None}


def test_cuerpo_inesperado_no_revienta(monkeypatch):
    calls = []
    monkeypatch.setattr(
        photos.requests,
        "get",
        make_get([FakeResponse(payload=[]), FakeResponse(payload={"player": "rate limited"})], calls),
    )
    assert photos.photo_url("Francisco Dju") is None
    assert photos.photo_url("Otro Jugador") is None


def test_circuito_corta_tras_fallos_consecutivos(monkeypatch):
    calls = []
    fallos = [CLOUDFLARE_CHALLENGE, requests.ConnectionError("down")]
    monkeypatch.setattr(photos.requests, "get", make_get(fallos, calls))
    assert photos.photo_url("Jugador A") is None
    assert photos.photo_url("Jugador B") is None
    # el circuito está abierto: la tercera petición ni toca la red
    assert photos.photo_url("Jugador C") is None
    assert len(calls) == 2


def test_un_exito_rearma_el_circuito(monkeypatch):
    calls = []
    respuestas = [CLOUDFLARE_CHALLENGE, FakeResponse(payload=VALID_PAYLOAD)]
    monkeypatch.setattr(photos.requests, "get", make_get(respuestas, calls))
    assert photos.photo_url("Jugador A") is None
    assert photos.photo_url("Francisco Dju") == "https://img/dju.png"
    assert photos._consecutive_failures == 0
