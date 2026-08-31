"""Tests del proveedor StatsBomb: un hueco puntual en los open data (un partido
sin fichero de eventos o de alineación publicado) no debe tumbar toda la
competición — solo ese partido debería perderse."""

import pandas as pd
import pytest
import requests

from futbol_analytics.providers import statsbomb as sbp


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    monkeypatch.setattr(sbp, "CACHE_DIR", tmp_path)


def _http_error(code: int = 400) -> requests.exceptions.HTTPError:
    resp = requests.Response()
    resp.status_code = code
    return requests.exceptions.HTTPError(response=resp)


def test_events_salta_un_partido_sin_datos_y_sigue(monkeypatch):
    provider = sbp.StatsBombProvider()
    monkeypatch.setattr(provider, "matches", lambda comp, season: pd.DataFrame({"match_id": [1, 2, 3]}))

    def fake_events(match_id):
        if match_id == 2:
            raise _http_error()
        return pd.DataFrame({"minute": [1], "period": [1]})

    monkeypatch.setattr(sbp.sb, "events", fake_events)
    out = provider.events(10, 20)
    assert sorted(out["match_id"].unique().tolist()) == [1, 3]


def test_events_lanza_error_claro_si_todos_los_partidos_fallan(monkeypatch):
    provider = sbp.StatsBombProvider()
    monkeypatch.setattr(provider, "matches", lambda comp, season: pd.DataFrame({"match_id": [1]}))

    def fake_events(match_id):
        raise _http_error()

    monkeypatch.setattr(sbp.sb, "events", fake_events)
    with pytest.raises(RuntimeError, match="ningún partido"):
        provider.events(10, 20)


def test_minutes_played_salta_una_alineacion_sin_datos_y_sigue(monkeypatch):
    provider = sbp.StatsBombProvider()
    events_df = pd.DataFrame({"match_id": [1, 1, 2], "period": [1, 1, 1], "minute": [10, 20, 5]})
    lineup_ok = pd.DataFrame(
        [
            {
                "player_name": "Jugadora Test",
                "player_nickname": None,
                "positions": [{"from": "0:00", "to": None, "position": "Center Forward"}],
            }
        ]
    )

    def fake_lineups(match_id):
        if match_id == 2:
            raise _http_error()
        return {"Equipo A": lineup_ok}

    monkeypatch.setattr(sbp.sb, "lineups", fake_lineups)
    out = provider.minutes_played(10, 20, events_df)
    assert list(out["player"]) == ["Jugadora Test"]
    assert (out["minutes"] > 0).all()


def test_minutes_played_lanza_error_claro_si_todas_las_alineaciones_fallan(monkeypatch):
    provider = sbp.StatsBombProvider()
    events_df = pd.DataFrame({"match_id": [1], "period": [1], "minute": [10]})

    def fake_lineups(match_id):
        raise _http_error()

    monkeypatch.setattr(sbp.sb, "lineups", fake_lineups)
    with pytest.raises(RuntimeError, match="ninguna alineación"):
        provider.minutes_played(10, 20, events_df)
