"""Tests de la lógica pura de métricas (sin red ni datos reales)."""

import numpy as np
import pandas as pd
import pytest

from futbol_analytics import metrics
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


def _jugadores(roles, metrica="npxg_p90"):
    """Tabla mínima: (rol, grupo, valor) por jugador."""
    filas = [
        {"player": f"J{i}", "role": rol, "position_group": grupo, metrica: valor}
        for i, (rol, grupo, valor) in enumerate(roles)
    ]
    return pd.DataFrame(filas)


def test_percentiles_por_grupo_es_el_comportamiento_por_defecto():
    df = _jugadores([("Central", "DF", 1.0), ("Lateral", "DF", 2.0), ("Lateral", "DF", 3.0)])
    out = metrics.percentiles(df, ["npxg_p90"])
    assert out["npxg_p90_pct"].tolist() == pytest.approx([100 / 3, 200 / 3, 100.0])
    assert set(out["pct_basis"]) == {"position_group"}


def test_percentiles_por_rol_compara_dentro_del_rol():
    # 8 centrales y 8 laterales: ambos roles superan el mínimo de muestra
    roles = [("Central", "DF", float(i)) for i in range(8)]
    roles += [("Lateral", "DF", 100.0 + i) for i in range(8)]
    out = metrics.percentiles(_jugadores(roles), ["npxg_p90"], group_col="role")

    assert set(out["pct_basis"]) == {"role"}
    # el peor lateral tiene valor altísimo, pero dentro de su rol es el último
    peor_lateral = out[out["role"] == "Lateral"].iloc[0]
    assert peor_lateral["npxg_p90"] == 100.0
    assert peor_lateral["npxg_p90_pct"] == pytest.approx(12.5)
    # el mejor central es el 100 de su rol pese a tener valores bajos
    assert out[out["role"] == "Central"]["npxg_p90_pct"].max() == pytest.approx(100.0)


def test_rol_con_muestra_pequena_cae_al_grupo_posicional():
    roles = [("Lateral", "DF", float(i)) for i in range(8)]  # rol grande
    roles += [("Central", "DF", 3.5), ("Central", "DF", 7.5)]  # rol pequeño
    out = metrics.percentiles(_jugadores(roles), ["npxg_p90"], group_col="role")

    laterales = out[out["role"] == "Lateral"]
    centrales = out[out["role"] == "Central"]
    assert set(laterales["pct_basis"]) == {"role"}
    assert set(centrales["pct_basis"]) == {"position_group"}
    # los centrales se comparan contra TODO el grupo DF (los 10), no solo entre ellos:
    # ordenados, 3.5 es el 5.º de 10 -> 50; 7.5 es el 10.º -> 100
    assert sorted(centrales["npxg_p90_pct"].round().tolist()) == [50.0, 100.0]


def test_percentiles_ignora_columnas_ausentes():
    df = _jugadores([("Central", "DF", 1.0), ("Central", "DF", 2.0)])
    out = metrics.percentiles(df, ["npxg_p90", "no_existe"])
    assert "npxg_p90_pct" in out.columns
    assert "no_existe_pct" not in out.columns


@pytest.mark.parametrize(
    ("position", "role"),
    [
        ("Goalkeeper", "Portero"),
        ("Right Center Back", "Central"),
        ("Left Back", "Lateral"),
        ("Right Wing Back", "Lateral"),
        ("Center Defensive Midfield", "Pivote"),
        ("Center Attacking Midfield", "Mediapunta"),
        ("Left Center Midfield", "Interior"),
        ("Right Wing", "Extremo"),
        ("Center Forward", "Delantero"),
    ],
)
def test_position_role(position, role):
    assert metrics.position_role(position) == role


def test_position_role_nan():
    assert pd.isna(metrics.position_role(np.nan))
