"""Tests de humo de las visualizaciones: cada figura se construye sin reventar.

No validan píxeles: comprueban que los contratos de columnas y la paleta
(tema claro y oscuro) siguen funcionando con datos mínimos. En CI corren
con el backend Agg (sin pantalla).
"""

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from futbol_analytics import viz


@pytest.fixture(autouse=True)
def tema_limpio():
    yield
    plt.close("all")
    viz.use_theme("light")


def fila_jugador() -> pd.Series:
    fila = {
        "player": "Jugadora Test",
        "team": "Equipo X",
        "minutes": 450.0,
        "position_group": "FW",
        "primary_position": "Center Forward",
    }
    for col, _ in viz.RADAR_METRICS["FW"]:
        fila[col] = 60.0
    return pd.Series(fila)


def eventos_minimos() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player": ["Jugadora Test"] * 4,
            "period": [1, 1, 2, 2],
            "type": ["Pass", "Pass", "Shot", "Carry"],
            "location": [[60.0, 40.0], [70.0, 30.0], [110.0, 42.0], [50.0, 20.0]],
            "pass_end_location": [[95.0, 40.0], [80.0, 35.0], None, None],
            "pass_outcome": [None, None, None, None],
            "pass_type": [None, None, None, None],
            "pass_shot_assist": [True, None, None, None],
            "shot_type": [None, None, "Open Play", None],
            "shot_outcome": [None, None, "Goal", None],
            "shot_statsbomb_xg": [None, None, 0.35, None],
        }
    )


@pytest.mark.parametrize("tema", ["light", "dark"])
def test_radar_chart_en_ambos_temas(tema):
    viz.use_theme(tema)
    fig = viz.radar_chart(fila_jugador(), "Competición Test", display="Apodo")
    assert fig is not None


def test_radar_chart_grupo_desconocido_usa_mf():
    fila = fila_jugador()
    for col, _ in viz.RADAR_METRICS["MF"]:
        fila[col] = 50.0
    fila["position_group"] = "???"
    assert viz.radar_chart(fila, "Competición Test") is not None


def test_radar_compare():
    fig = viz.radar_compare(fila_jugador(), fila_jugador(), "Competición Test", "A", "B")
    assert fig is not None


def test_touch_heatmap():
    fig = viz.touch_heatmap(eventos_minimos(), "Jugadora Test", "Competición Test")
    assert fig is not None


def test_pass_map():
    fig = viz.pass_map(eventos_minimos(), "Jugadora Test", "Competición Test")
    assert fig is not None


def test_shot_map():
    fig = viz.shot_map(eventos_minimos(), "Jugadora Test", "Competición Test")
    assert fig is not None


def test_save_crea_el_png(tmp_path):
    fig = viz.radar_chart(fila_jugador(), "Competición Test")
    destino = tmp_path / "informes" / "radar.png"
    viz.save(fig, destino)
    assert destino.exists() and destino.stat().st_size > 0


def test_style_map():
    style = pd.DataFrame(
        {
            "possession": [60.0, 40.0, 50.0],
            "ppda": [6.0, 14.0, 10.0],
            "prog_share": [8.0, 15.0, 11.0],
        },
        index=pd.Index(["A", "B", "C"], name="team"),
    )
    fig = viz.style_map(style, highlight=["B"], current_team="A", subtitle="Test")
    assert fig is not None


def test_team_radar():
    fila = pd.Series({c: 60.0 for c, _ in viz.TEAM_RADAR_METRICS})
    fig = viz.team_radar(fila, "Competición Test", "Equipo X")
    assert fig is not None


def test_team_radar_omite_metricas_ausentes():
    fila = pd.Series({"ppda_pct": 70.0, "field_tilt_pct": float("nan")})
    fig = viz.team_radar(fila, "Competición Test", "Equipo X")
    assert fig is not None
