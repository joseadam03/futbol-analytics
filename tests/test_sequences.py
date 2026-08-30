"""Tests de secuencias de posesión con eventos sintéticos (sin red)."""

import pandas as pd
import pytest

from futbol_analytics import sequences


def _ev(team, type_, possession, x=50.0, minute=0, second=0, **kw):
    base = {
        "match_id": 1,
        "period": 1,
        "team": team,
        "player": f"{team}-1",
        "type": type_,
        "location": [x, 40.0],
        "possession": possession,
        "play_pattern": "Regular Play",
        "minute": minute,
        "second": second,
        "shot_type": None,
        "shot_outcome": None,
        "shot_statsbomb_xg": None,
    }
    base.update(kw)
    return base


def eventos() -> pd.DataFrame:
    rows = []
    # A: elaboración larga desde atrás que acaba en tiro
    for i in range(6):
        rows.append(_ev("A", "Pass", 1, x=20.0 + 8 * i, minute=0, second=5 * i))
    rows.append(_ev("A", "Shot", 1, x=105.0, minute=0, second=35, shot_outcome="Goal", shot_statsbomb_xg=0.3))
    # B: robo alto y tiro inmediato (contragolpe)
    rows.append(_ev("B", "Ball Recovery", 2, x=85.0, minute=10, second=0, play_pattern="From Counter"))
    rows.append(
        _ev(
            "B",
            "Shot",
            2,
            x=100.0,
            minute=10,
            second=6,
            shot_outcome="Off T",
            shot_statsbomb_xg=0.1,
            play_pattern="From Counter",
        )
    )
    # A: córner
    rows.append(_ev("A", "Pass", 3, x=119.0, minute=20, second=0, play_pattern="From Corner"))
    rows.append(
        _ev(
            "A",
            "Shot",
            3,
            x=110.0,
            minute=20,
            second=4,
            shot_outcome="Off T",
            shot_statsbomb_xg=0.2,
            play_pattern="From Corner",
        )
    )
    # posesión sin tiro: no debe aparecer
    rows += [_ev("B", "Pass", 4, x=30.0, minute=30)] * 3
    # penalti y tanda: excluidos
    rows.append(_ev("A", "Shot", 5, x=108.0, minute=40, shot_type="Penalty", shot_statsbomb_xg=0.76))
    rows.append(_ev("A", "Shot", 6, x=108.0, minute=0, period=5, shot_statsbomb_xg=0.76))
    return pd.DataFrame(rows)


def test_solo_las_posesiones_con_tiro_entran():
    seq = sequences.shot_sequences(eventos())
    assert sorted(seq["possession"]) == [1, 2, 3]


def test_pases_previos_al_primer_tiro():
    seq = sequences.shot_sequences(eventos()).set_index("possession")
    assert seq.loc[1, "passes_before"] == 6  # elaboración larga
    assert seq.loc[2, "passes_before"] == 0  # tiro tras robo


def test_zona_de_inicio_y_robo_alto():
    seq = sequences.shot_sequences(eventos()).set_index("possession")
    assert seq.loc[1, "start_x"] == pytest.approx(20.0)
    assert seq.loc[1, "high_start"] == 0.0  # nace atrás
    assert seq.loc[2, "high_start"] == 1.0  # robo en campo contrario


def test_duracion_y_velocidad_directa():
    seq = sequences.shot_sequences(eventos()).set_index("possession")
    assert seq.loc[1, "duration"] == pytest.approx(35.0)
    # progresa 85 unidades en 35 s
    assert seq.loc[1, "direct_speed"] == pytest.approx(85.0 / 35.0)
    # el contragolpe avanza menos metros pero mucho más rápido
    assert seq.loc[2, "direct_speed"] > seq.loc[1, "direct_speed"]


def test_perfil_por_equipo():
    perfil = sequences.team_sequence_profile(sequences.shot_sequences(eventos())).set_index("team")
    assert perfil.loc["A", "sequences"] == 2
    assert perfil.loc["A", "npxg"] == pytest.approx(0.5)
    assert perfil.loc["A", "set_piece_share"] == pytest.approx(50.0)  # una de dos es córner
    assert perfil.loc["B", "direct_share"] == pytest.approx(100.0)


def test_desglose_por_patron():
    desglose = sequences.pattern_breakdown(sequences.shot_sequences(eventos()))
    assert set(desglose["pattern"]) == {"Regular Play", "From Counter", "From Corner"}
    assert desglose["npxg_share"].sum() == pytest.approx(100.0)
    assert desglose.iloc[0]["label"] == "Juego regular"  # el de más npxG


def test_desglose_filtrado_por_equipo():
    seq = sequences.shot_sequences(eventos())
    assert set(sequences.pattern_breakdown(seq, team="B")["pattern"]) == {"From Counter"}


def test_sin_columna_de_posesion_devuelve_vacio():
    ev = eventos().drop(columns=["possession"])
    assert sequences.shot_sequences(ev).empty
    assert sequences.team_sequence_profile(sequences.shot_sequences(ev)).empty
    assert sequences.pattern_breakdown(sequences.shot_sequences(ev)).empty
