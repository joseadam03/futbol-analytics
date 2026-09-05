"""Tests del módulo de métricas de equipo con eventos sintéticos."""

import pandas as pd
import pytest

from futbol_analytics.teams import match_summary, team_metrics, team_style_metrics, team_style_percentiles


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
        "pass_end_location": None,
        "pass_outcome": None,
        "pass_type": None,
        "carry_end_location": None,
        "possession": None,
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


def test_match_summary_compara_local_y_visitante():
    rows = []
    rows += [_event("A", "Pass", x=50)] * 6 + [_event("B", "Pass", x=60)] * 4
    rows.append(_event("A", "Shot", x=110, shot_outcome="Goal", shot_statsbomb_xg=0.5))
    rows.append(_event("B", "Shot", x=105, shot_outcome="Off T", shot_statsbomb_xg=0.2))
    resumen = match_summary(pd.DataFrame(rows), match_id=1)

    a = resumen[resumen["team"] == "A"].iloc[0]
    b = resumen[resumen["team"] == "B"].iloc[0]
    assert a["rival"] == "B" and b["rival"] == "A"
    assert a["possession"] == pytest.approx(60.0)
    assert a["goals"] == 1 and a["goals_against"] == 0
    assert b["goals"] == 0 and b["goals_against"] == 1
    assert a["npxg"] == pytest.approx(0.5)
    assert b["npxg"] == pytest.approx(0.2)


def test_match_summary_ignora_otros_partidos():
    rows = [_event("A", "Pass", x=50)] * 3 + [_event("B", "Pass", x=50)] * 3
    rows += [_event("A", "Pass", x=50, match_id=2)] * 20
    resumen = match_summary(pd.DataFrame(rows), match_id=1)
    assert set(resumen["team"]) == {"A", "B"}


def _estilo(team, largo, prog, **kw):
    """Pase con destino explícito, para las métricas de ritmo y progresión."""
    inicio = kw.pop("x", 40.0)
    fin = inicio + (40.0 if prog else 3.0)
    return _event(
        team,
        "Pass",
        x=inicio,
        pass_end_location=[fin, 40.0],
        pass_outcome=None,
        pass_type=None,
        **kw,
    )


def eventos_estilo() -> pd.DataFrame:
    """Lento (A: pases cortos, presión alta) frente a directo (B)."""
    rows = []
    rows += [_estilo("A", largo=False, prog=False)] * 12
    rows += [_estilo("A", largo=False, prog=True, x=45.0)] * 3
    rows += [_estilo("B", largo=True, prog=True, x=30.0)] * 6
    rows += [_estilo("B", largo=False, prog=False)] * 2
    # A recupera arriba; B, atrás (las intercepciones altas alimentan el PPDA)
    rows += [_event("A", "Ball Recovery", x=80.0)] * 4
    rows += [_event("B", "Ball Recovery", x=20.0)] * 4
    rows += [_event("A", "Interception", x=70.0)] * 4
    rows += [_event("B", "Interception", x=50.0), _event("B", "Interception", x=30.0)]
    # toques en el último tercio: A domina territorialmente (6 frente a 2)
    rows += [_event("A", "Ball Receipt*", x=100.0)] * 6
    rows += [_event("B", "Ball Receipt*", x=95.0)] * 2
    # conducciones progresivas de B
    rows += [
        _event("B", "Carry", x=50.0, carry_end_location=[90.0, 40.0]),
        _event("B", "Carry", x=52.0, carry_end_location=[95.0, 40.0]),
    ]
    return pd.DataFrame(rows)


def test_ritmo_distingue_juego_corto_de_directo():
    style = team_style_metrics(eventos_estilo()).set_index("team")
    assert style.loc["B", "pass_length"] > style.loc["A", "pass_length"]
    assert style.loc["B", "long_pass_share"] > style.loc["A", "long_pass_share"]


def test_altura_de_recuperacion():
    style = team_style_metrics(eventos_estilo()).set_index("team")
    assert style.loc["A", "recovery_height"] > style.loc["B", "recovery_height"]


def test_progresion_pases_conducciones_y_ultimo_tercio():
    style = team_style_metrics(eventos_estilo()).set_index("team")
    # B: 6 de 8 pases en juego son progresivos; A: 3 de 15
    assert style.loc["B", "prog_pass_share"] == pytest.approx(75.0)
    assert style.loc["A", "prog_pass_share"] == pytest.approx(20.0)
    # las dos conducciones de B cruzan x=80 y son progresivas
    assert style.loc["B", "prog_carries_pm"] == pytest.approx(2.0)
    assert style.loc["A", "prog_carries_pm"] == pytest.approx(0.0)
    # entradas al último tercio: A, 3 pases (45->85). Los de B (30->70) se quedan
    # cortos pese a ser progresivos, así que solo cuentan sus 2 conducciones.
    assert style.loc["A", "final_third_pm"] == pytest.approx(3.0)
    assert style.loc["B", "final_third_pm"] == pytest.approx(2.0)


def test_field_tilt_suma_cien_entre_los_dos_equipos():
    style = team_style_metrics(eventos_estilo()).set_index("team")
    assert style["field_tilt"].sum() == pytest.approx(100.0)


def test_pases_por_posesion():
    rows = [_estilo("A", largo=False, prog=False, possession=1)] * 6
    rows += [_estilo("A", largo=False, prog=False, possession=2)] * 4
    rows += [_estilo("B", largo=False, prog=False, possession=3)] * 2
    style = team_style_metrics(pd.DataFrame(rows)).set_index("team")
    assert style.loc["A", "passes_per_possession"] == pytest.approx(5.0)  # (6+4)/2
    assert style.loc["B", "passes_per_possession"] == pytest.approx(2.0)


def test_percentiles_de_estilo_invierten_el_ppda():
    style = team_style_metrics(eventos_estilo())
    pct = team_style_percentiles(style).set_index("team")
    # A presiona más (PPDA más bajo) -> percentil de presión más alto
    assert pct.loc["A", "ppda"] < pct.loc["B", "ppda"]
    assert pct.loc["A", "ppda_pct"] > pct.loc["B", "ppda_pct"]
