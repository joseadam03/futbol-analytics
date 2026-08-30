"""Tests de las series temporales con eventos sintéticos (sin red)."""

import pandas as pd
import pytest

from futbol_analytics import series


def _ev(team, type_, match_id, x=50.0, **kw):
    base = {
        "match_id": match_id,
        "period": 1,
        "team": team,
        "player": f"{team}-1",
        "type": type_,
        "location": [x, 40.0],
        "pass_end_location": None,
        "pass_outcome": None,
        "pass_shot_assist": None,
        "pass_goal_assist": None,
        "shot_type": None,
        "shot_outcome": None,
        "shot_statsbomb_xg": None,
        "shot_key_pass_id": None,
        "duel_type": None,
        "id": None,
    }
    base.update(kw)
    return base


def eventos() -> pd.DataFrame:
    """Tres partidos: A mejora, B empeora."""
    rows = []
    for match_id, (xg_a, xg_b) in enumerate([(0.5, 1.5), (1.0, 1.0), (2.0, 0.5)], start=1):
        rows += [_ev("A", "Pass", match_id)] * 10
        rows += [_ev("B", "Pass", match_id)] * 10
        rows.append(_ev("A", "Shot", match_id, x=105.0, shot_outcome="Off T", shot_statsbomb_xg=xg_a))
        rows.append(_ev("B", "Shot", match_id, x=105.0, shot_outcome="Off T", shot_statsbomb_xg=xg_b))
    return pd.DataFrame(rows)


def calendario() -> pd.DataFrame:
    # las fechas van al revés que los ids, para comprobar que manda la fecha
    return pd.DataFrame(
        [
            {"match_id": 1, "match_date": "2026-03-01", "match_week": 3},
            {"match_id": 2, "match_date": "2026-02-01", "match_week": 2},
            {"match_id": 3, "match_date": "2026-01-01", "match_week": 1},
        ]
    )


def test_serie_por_equipo_con_medias_moviles():
    ts = series.team_series(eventos())
    a = ts[ts["team"] == "A"].sort_values("orden")
    assert a["npxg_for"].tolist() == pytest.approx([0.5, 1.0, 2.0])
    assert a["npxg_against"].tolist() == pytest.approx([1.5, 1.0, 0.5])
    assert a["npxg_diff"].tolist() == pytest.approx([-1.0, 0.0, 1.5])
    # la media móvil suaviza: el último punto es la media de los tres
    assert a["npxg_diff_roll"].iloc[-1] == pytest.approx(0.5 / 3)
    assert a["npxg_for_cum"].iloc[-1] == pytest.approx(3.5)
    assert a["partido"].tolist() == [1, 2, 3]


def test_el_calendario_manda_sobre_el_id():
    ts = series.team_series(eventos(), calendario())
    a = ts[ts["team"] == "A"].sort_values("orden")
    # ordenado por fecha, el partido 3 va primero
    assert a["match_id"].tolist() == [3, 2, 1]
    assert a["jornada"].tolist() == [1, 2, 3]
    assert a["npxg_for"].tolist() == pytest.approx([2.0, 1.0, 0.5])


def test_sin_calendario_el_orden_es_el_del_id():
    ts = series.team_series(eventos())
    a = ts[ts["team"] == "A"].sort_values("orden")
    assert a["match_id"].tolist() == [1, 2, 3]


def test_posesion_por_partido():
    rows = [_ev("A", "Pass", 1)] * 7 + [_ev("B", "Pass", 1)] * 3
    ts = series.team_series(pd.DataFrame(rows)).set_index("team")
    assert ts.loc["A", "possession"] == pytest.approx(70.0)


def test_serie_de_jugador():
    ps = series.player_series(eventos(), "A-1", calendario())
    assert ps["npxg"].tolist() == pytest.approx([2.0, 1.0, 0.5])  # por fecha
    assert ps["shots"].tolist() == [1.0, 1.0, 1.0]
    assert ps["npxg_cum"].iloc[-1] == pytest.approx(3.5)
    assert ps["npxg_roll"].iloc[-1] == pytest.approx(3.5 / 3)


def test_xa_del_jugador_hereda_el_xg_del_tiro():
    rows = [
        _ev("A", "Pass", 1, id="p1", pass_shot_assist=True),
        _ev("A", "Shot", 1, shot_statsbomb_xg=0.4, shot_key_pass_id="p1", shot_outcome="Off T"),
    ]
    ps = series.player_series(pd.DataFrame(rows), "A-1")
    assert ps["xa"].iloc[0] == pytest.approx(0.4)
    assert ps["key_passes"].iloc[0] == 1.0


def test_jugador_inexistente_devuelve_vacio():
    assert series.player_series(eventos(), "Nadie").empty


def test_eventos_vacios_no_revientan():
    vacio = eventos().iloc[:0]
    assert series.team_series(vacio).empty
