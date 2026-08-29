"""Tests del cliente de TheSportsDB con la red simulada: sin llamadas reales.

Cubren el caso que rompía la app: el servicio detrás de Cloudflare
devolviendo un challenge HTML (403/429/503) en lugar de JSON.
"""

import pytest
import requests

from futbol_analytics import tsdb


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("body is not JSON")
        return self._payload


VALID_PAYLOAD = {
    "player": [
        {"strSport": "Basketball", "strPlayer": "Otro", "strCutout": "https://img/otro.png"},
        {
            "strSport": "Soccer",
            "strPlayer": "Franculino Djú",
            "strTeam": "Midtjylland",
            "strPosition": "Forward",
            "strNationality": "Guinea-Bissau",
            "dateBorn": "2004-06-28",
            "strCutout": None,
            "strThumb": "https://img/thumb.png",
        },
    ]
}


@pytest.fixture(autouse=True)
def circuito_cerrado(monkeypatch):
    monkeypatch.setattr(tsdb, "_consecutive_failures", 0)


def make_get(responses, calls):
    def fake_get(url, **kwargs):
        calls.append(url)
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    return fake_get


def test_challenge_de_cloudflare_lanza_service_unavailable(monkeypatch):
    monkeypatch.setattr(tsdb.requests, "get", make_get([FakeResponse(status_code=403)], []))
    with pytest.raises(tsdb.ServiceUnavailable):
        tsdb.search_players("Francisco Dju")


def test_timeout_lanza_service_unavailable(monkeypatch):
    monkeypatch.setattr(tsdb.requests, "get", make_get([requests.Timeout("boom")], []))
    with pytest.raises(tsdb.ServiceUnavailable):
        tsdb.search_players("Francisco Dju")


def test_cuerpo_no_json_lanza_service_unavailable(monkeypatch):
    monkeypatch.setattr(tsdb.requests, "get", make_get([FakeResponse(status_code=200)], []))
    with pytest.raises(tsdb.ServiceUnavailable):
        tsdb.search_players("Francisco Dju")


def test_respuesta_valida_normaliza_fichas(monkeypatch):
    monkeypatch.setattr(tsdb.requests, "get", make_get([FakeResponse(payload=VALID_PAYLOAD)], []))
    fichas = tsdb.search_players("Franculino")
    assert len(fichas) == 1  # el jugador de baloncesto se filtra
    ficha = fichas[0]
    assert ficha["nombre"] == "Franculino Djú"
    assert ficha["equipo"] == "Midtjylland"
    assert ficha["foto"] == "https://img/thumb.png"  # sin recorte, usa el thumb


def test_sin_resultados_devuelve_lista_vacia(monkeypatch):
    monkeypatch.setattr(tsdb.requests, "get", make_get([FakeResponse(payload={"player": None})], []))
    assert tsdb.search_players("Nadie") == []


def test_forma_inesperada_no_revienta(monkeypatch):
    monkeypatch.setattr(
        tsdb.requests, "get", make_get([FakeResponse(payload={"player": "rate limited"})], [])
    )
    assert tsdb.search_players("Alguien") == []


def test_circuito_corta_tras_fallos_consecutivos(monkeypatch):
    calls = []
    fallos = [FakeResponse(status_code=403), requests.ConnectionError("down")]
    monkeypatch.setattr(tsdb.requests, "get", make_get(fallos, calls))
    for _ in range(2):
        with pytest.raises(tsdb.ServiceUnavailable):
            tsdb.search_players("Jugador")
    # el circuito está abierto: la tercera petición ni toca la red
    with pytest.raises(tsdb.ServiceUnavailable):
        tsdb.search_players("Jugador")
    assert len(calls) == 2


def test_un_exito_rearma_el_circuito(monkeypatch):
    calls = []
    respuestas = [FakeResponse(status_code=403), FakeResponse(payload=VALID_PAYLOAD)]
    monkeypatch.setattr(tsdb.requests, "get", make_get(respuestas, calls))
    with pytest.raises(tsdb.ServiceUnavailable):
        tsdb.search_players("Jugador A")
    assert tsdb.search_players("Franculino")[0]["nombre"] == "Franculino Djú"
    assert tsdb._consecutive_failures == 0
