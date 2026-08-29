"""Tests de la lógica pura de métricas (sin red ni datos reales)."""

import numpy as np
import pandas as pd
import pytest

from futbol_analytics.metrics import (
    is_progressive,
    position_group,
    team_possession_share,
)
from futbol_analytics.providers.statsbomb import _clock_to_min
from futbol_analytics.similarity import similar_players


def test_clock_to_min():
    assert _clock_to_min("00:00") == 0.0
    assert _clock_to_min("45:30") == 45.5
    assert _clock_to_min("103:15") == pytest.approx(103.25)


@pytest.mark.parametrize(
    ("position", "group"),
    [
        ("Goalkeeper", "GK"),
        ("Right Center Back", "DF"),
        ("Left Wing Back", "DF"),
        ("Center Defensive Midfield", "MF"),
        ("Left Midfield", "MF"),
        ("Right Wing", "FW"),
        ("Center Forward", "FW"),
        ("Secondary Striker", "FW"),
    ],
)
def test_position_group(position, group):
    assert position_group(position) == group


def test_position_group_nan():
    assert pd.isna(position_group(np.nan))


def test_is_progressive():
    start = pd.Series([[60.0, 40.0], [60.0, 40.0], [110.0, 40.0]])
    end = pd.Series([[100.0, 40.0], [62.0, 40.0], [80.0, 40.0]])
    result = is_progressive(start, end)
    # 60->100 reduce la distancia de 60 a 20 (progresivo);
    # 60->62 apenas avanza; 110->80 retrocede.
    assert result.tolist() == [True, False, False]


def test_team_possession_share():
    events = pd.DataFrame(
        {
            "match_id": [1] * 10,
            "team": ["A"] * 7 + ["B"] * 3,
            "type": ["Pass"] * 10,
        }
    )
    poss = team_possession_share(events)
    assert poss["A"] == pytest.approx(0.7)
    assert poss["B"] == pytest.approx(0.3)


def test_similar_players_finds_the_clone():
    rng = np.random.default_rng(7)
    base = rng.random((6, 3))
    base[5] = base[0] * 1.02  # el jugador 5 es casi idéntico al 0
    df = pd.DataFrame(base, columns=["npxg_p90", "xa_p90", "pressures_p90"])
    df["player"] = [f"J{i}" for i in range(6)]
    df["team"] = "X"
    df["primary_position"] = "Center Forward"
    df["position_group"] = "FW"
    df["minutes"] = 900

    top = similar_players(df, "J0", n=3, features=["npxg_p90", "xa_p90", "pressures_p90"])
    assert top.iloc[0]["player"] == "J5"
