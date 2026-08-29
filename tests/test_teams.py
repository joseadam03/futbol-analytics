"""Tests del módulo de métricas de equipo con eventos sintéticos."""

import pandas as pd
import pytest

from futbol_analytics.teams import team_metrics


def _event(team, type_, x=60.0, **kw):
    base = {
        "match_id": 1,
        "period": 1,
        "team": team,
        "type": type_,
        "location": [x, 40.0],
        "shot_type": None,
        "shot_outcome": None,
        "shot_statsbomb_xg": None,
        "duel_type": None,
    }
    base.update(kw)
    return base


def test_team_metrics_basic():
    rows = []
    # A: 6 pases (4 en zona de construcción), B: 4 pases (2 en construcción)
    rows += [_event("A", "Pass", x=50)] * 4 + [_event("A", "Pass", x=100)] * 2
    rows += [_event("B", "Pass", x=60)] * 2 + [_event("B", "Pass", x=90)] * 2
    # B hace 2 acciones defensivas en zona alta (x>=48) y 1 en zona baja
    rows += [_event("B", "Interception", x=70), _event("B", "Duel", x=50, duel_type="Tackle")]
    rows += [_event("B", "Interception", x=20)]
    # A: un gol de 0.5 xG; B: un tiro sin gol de 0.2 xG
    rows.append(_event("A", "Shot", x=110, shot_outcome="Goal", shot_statsbomb_xg=0.5))
    rows.append(_event("B", "Shot", x=105, shot_outcome="Off T", shot_statsbomb_xg=0.2))
    # las tandas de penaltis se ignoran
    rows.append(_event("A", "Shot", shot_outcome="Goal", shot_statsbomb_xg=0.9) | {"period": 5})

    df = team_metrics(pd.DataFrame(rows))
    a = df[df["team"] == "A"].iloc[0]
    b = df[df["team"] == "B"].iloc[0]

    assert a["possession"] == pytest.approx(60.0)
    assert a["goals_for"] == 1 and a["goals_against"] == 0
    assert b["goals_against"] == 1
    assert a["npxg_for_pm"] == pytest.approx(0.5)
    assert a["npxg_against_pm"] == pytest.approx(0.2)
    assert b["npxg_diff_pm"] == pytest.approx(-0.3)
    # PPDA de B: 4 pases de A en construcción / 2 acciones defensivas altas
    assert b["ppda"] == pytest.approx(2.0)
