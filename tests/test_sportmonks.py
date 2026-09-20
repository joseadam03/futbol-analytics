"""Tests de sportmonks.py con la red simulada (sin llamadas reales).

Los payloads reproducen exactamente la forma verificada contra la API real
(búsqueda de Franculino Djú, Superliga danesa): un bloque de estadísticas
por (equipo, temporada), cada uno con una lista `details` de
`{type: {name}, value: {total: ...}}`. Los traspasos también son los reales
de ese mismo jugador (Benfica U23 -> Midtjylland 2023 sin importe público,
Midtjylland -> Trabzonspor 2026 por 17M).
"""

import json

import pytest
import requests

from futbol_analytics import sportmonks


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("body is not JSON")
        return self._payload


SEARCH_PAYLOAD = {
    "data": [
        {
            "id": 37597771,
            "display_name": "Franculino",
            "name": "Franculino Gluda Djú",
            "date_of_birth": "2004-06-28",
            "image_path": "https://cdn.sportmonks.com/x.png",
        }
    ]
}

TRANSFERS_PAYLOAD = {
    "data": {
        "id": 37597771,
        "display_name": "Franculino",
        "transfers": [
            {
                "id": 388730,
                "date": "2023-07-01",
                "amount": None,
                "fromTeam": {"id": 230221, "name": "Benfica U23"},
                "toTeam": {"id": 939, "name": "FC Midtjylland"},
            },
            {
                "id": 596348,
                "date": "2026-09-02",
                "amount": 17000000,
                "fromTeam": {"id": 939, "name": "FC Midtjylland"},
                "toTeam": {"id": 688, "name": "Trabzonspor"},
            },
        ],
    }
}

PLAYER_PAYLOAD = {
    "data": {
        "id": 37597771,
        "display_name": "Franculino",
        "statistics": [
            {
                "team_id": 939,
                "season_id": 27897,
                "season": {"id": 27897, "name": "2026/2027"},
                "details": [
                    {"type": {"name": "Goals"}, "value": {"total": 1, "goals": 1, "penalties": 0}},
                    {"type": {"name": "Yellowcards"}, "value": {"total": 1}},
                    {"type": {"name": "Minutes Played"}, "value": {"total": 208}},
                    {"type": {"name": "Appearances"}, "value": {"total": 3}},
                    {"type": {"name": "Something Unmapped"}, "value": {"total": 99}},
                ],
            },
            {
                "team_id": 939,
                "season_id": 25000,
                "season": {"id": 25000, "name": "2025/2026"},
                "details": [
                    {"type": {"name": "Goals"}, "value": {"total": 17, "goals": 15, "penalties": 2}},
                    {"type": {"name": "Assists"}, "value": {"total": 3}},
                    {"type": {"name": "Minutes Played"}, "value": {"total": 1343}},
                ],
            },
        ],
    }
}


@pytest.fixture(autouse=True)
def token_y_cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "test-token")
    monkeypatch.setattr(sportmonks, "CACHE_FILE", tmp_path / "sportmonks_players.json")


def make_get(responses, calls):
    def fake_get(url, params=None, **kwargs):
        calls.append((url, params))
        resp = responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    return fake_get


def test_available_depende_del_token(monkeypatch):
    assert sportmonks.available() is True
    monkeypatch.delenv("SPORTMONKS_API_TOKEN", raising=False)
    assert sportmonks.available() is False


def test_token_de_sesion_tiene_prioridad_sobre_el_del_entorno(monkeypatch):
    # ContextVar directo, no la fixture de sesión: hay que restaurarlo a mano
    # para no filtrar este token a los demás tests del proceso.
    sportmonks.set_session_credentials("token-de-club")
    try:
        assert sportmonks.available() is True
        vistos = []
        monkeypatch.setattr(
            sportmonks.requests, "get", make_get([FakeResponse(payload=SEARCH_PAYLOAD)], vistos)
        )
        sportmonks.search_players("Dju")
        assert vistos[0][1]["api_token"] == "token-de-club"
    finally:
        sportmonks._TOKEN.set(None)


def test_sin_token_lanza_service_unavailable(monkeypatch):
    monkeypatch.delenv("SPORTMONKS_API_TOKEN", raising=False)
    with pytest.raises(sportmonks.ServiceUnavailable):
        sportmonks.search_players("Dju")


def test_error_http_lanza_service_unavailable(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(status_code=403)], []))
    with pytest.raises(sportmonks.ServiceUnavailable):
        sportmonks.search_players("Dju")


def test_cuerpo_no_json_lanza_service_unavailable(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(status_code=200)], []))
    with pytest.raises(sportmonks.ServiceUnavailable):
        sportmonks.search_players("Dju")


def test_timeout_lanza_service_unavailable(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([requests.Timeout("boom")], []))
    with pytest.raises(sportmonks.ServiceUnavailable):
        sportmonks.search_players("Dju")


def test_search_players_normaliza_candidatos(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(payload=SEARCH_PAYLOAD)], []))
    candidatos = sportmonks.search_players("Franculino")
    assert len(candidatos) == 1
    assert candidatos[0]["nombre"] == "Franculino"
    assert candidatos[0]["id"] == 37597771


def test_player_seasons_mapea_las_estadisticas_conocidas():
    filas = sportmonks._extract_seasons_from_payload(PLAYER_PAYLOAD)
    assert len(filas) == 2

    reciente = next(f for f in filas if f["season_name"] == "2026/2027")
    assert reciente["goals"] == 1.0
    assert reciente["minutes"] == 208.0
    assert reciente["appearances"] == 3.0
    assert reciente["yellow_cards"] == 1.0
    assert "assists" not in reciente  # esa temporada no trae asistencias

    anterior = next(f for f in filas if f["season_name"] == "2025/2026")
    assert anterior["goals"] == 17.0  # total, no solo los de juego (excluye penaltis aparte)
    assert anterior["assists"] == 3.0


def test_player_seasons_ignora_tipos_no_mapeados(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(payload=PLAYER_PAYLOAD)], []))
    filas = sportmonks.player_seasons(37597771)
    claves = {k for fila in filas for k in fila}
    assert "something_unmapped" not in claves
    assert "goals" in claves


def test_player_ficha_completa_y_cachea(monkeypatch):
    calls = []
    monkeypatch.setattr(
        sportmonks.requests,
        "get",
        make_get(
            [
                FakeResponse(payload=SEARCH_PAYLOAD),
                FakeResponse(payload=PLAYER_PAYLOAD),
                FakeResponse(payload=TRANSFERS_PAYLOAD),
            ],
            calls,
        ),
    )
    ficha = sportmonks.player_ficha("Franculino")
    assert ficha["nombre"] == "Franculino"
    assert len(ficha["temporadas"]) == 2
    assert len(ficha["traspasos"]) == 2

    # segunda llamada: sale de la caché en disco, sin tocar la red
    ficha2 = sportmonks.player_ficha("Franculino")
    assert ficha2 == ficha
    assert len(calls) == 3


def test_extract_transfers_mapea_origen_destino_e_importe():
    filas = sportmonks._extract_transfers_from_payload(TRANSFERS_PAYLOAD)
    assert len(filas) == 2

    sin_importe = next(f for f in filas if f["fecha"] == "2023-07-01")
    assert sin_importe["origen"] == "Benfica U23"
    assert sin_importe["destino"] == "FC Midtjylland"
    assert sin_importe["importe"] is None  # no inventado cuando no es público

    con_importe = next(f for f in filas if f["fecha"] == "2026-09-02")
    assert con_importe["origen"] == "FC Midtjylland"
    assert con_importe["destino"] == "Trabzonspor"
    assert con_importe["importe"] == 17000000


def test_extract_transfers_tolera_grafia_en_minusculas():
    payload = {
        "data": {
            "transfers": [
                {
                    "date": "2020-01-01",
                    "amount": None,
                    "fromteam": {"name": "Club A"},
                    "toteam": {"name": "Club B"},
                }
            ]
        }
    }
    filas = sportmonks._extract_transfers_from_payload(payload)
    assert filas[0]["origen"] == "Club A"
    assert filas[0]["destino"] == "Club B"


def test_extract_transfers_payload_vacio():
    assert sportmonks._extract_transfers_from_payload({}) == []
    assert sportmonks._extract_transfers_from_payload({"data": {}}) == []


def test_player_transfers(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(payload=TRANSFERS_PAYLOAD)], []))
    filas = sportmonks.player_transfers(37597771)
    assert len(filas) == 2


def test_player_bio_altura_y_pie_desde_metadata(monkeypatch):
    # a diferencia de los demás payloads de este fichero (verificados
    # contra una respuesta real de Sportmonks), este esquema de
    # "metadata" sale de su documentación pública, no de una llamada real
    # comprobada aquí — no hay token de prueba en este entorno para
    # verificarlo en vivo. Por eso player_bio busca por tipo cuyo nombre
    # contenga "foot" en vez de una clave exacta, y este test cubre ese
    # margen de tolerancia.
    payload = {
        "data": {
            "id": 37597771,
            "height": 180,
            "metadata": [{"type": {"name": "Preferred Foot"}, "values": "right"}],
        }
    }
    monkeypatch.setattr(
        sportmonks.requests,
        "get",
        make_get([FakeResponse(payload=SEARCH_PAYLOAD), FakeResponse(payload=payload)], []),
    )
    assert sportmonks.player_bio("Franculino") == {"altura": "180 cm", "pie": "Right"}


def test_player_bio_sin_altura_ni_metadata(monkeypatch):
    payload = {"data": {"id": 37597771, "height": None, "metadata": []}}
    monkeypatch.setattr(
        sportmonks.requests,
        "get",
        make_get([FakeResponse(payload=SEARCH_PAYLOAD), FakeResponse(payload=payload)], []),
    )
    assert sportmonks.player_bio("Franculino") == {"altura": None, "pie": None}


def test_player_bio_sin_candidatos_da_none(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(payload={"data": []})], []))
    assert sportmonks.player_bio("NadieDeVerdad") is None


def test_player_ficha_sin_resultados_se_cachea_como_none(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(payload={"data": []})], []))
    assert sportmonks.player_ficha("NadieDeVerdad") is None
    assert json.loads(sportmonks.CACHE_FILE.read_text()) == {"NadieDeVerdad": None}


def test_player_ficha_servicio_caido_no_se_cachea(monkeypatch):
    monkeypatch.setattr(sportmonks.requests, "get", make_get([FakeResponse(status_code=500)], []))
    with pytest.raises(sportmonks.ServiceUnavailable):
        sportmonks.player_ficha("Franculino")
    assert not sportmonks.CACHE_FILE.exists()


def test_stat_value_tolera_formas_inesperadas():
    assert sportmonks._stat_value({"value": {"total": 5}}) == 5.0
    assert sportmonks._stat_value({"value": 7}) == 7.0
    assert sportmonks._stat_value({"value": None}) is None
    assert sportmonks._stat_value({"value": {"home": 1}}) is None  # sin "total"
    assert sportmonks._stat_value({}) is None
