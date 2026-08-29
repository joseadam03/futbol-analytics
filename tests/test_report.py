"""Test de humo del informe-CV en PDF, con datos sintéticos (sin red)."""

import pandas as pd

from futbol_analytics import fit, report


def eventos() -> pd.DataFrame:
    def ev(team, player, type_, x=60.0, end=None, **kw):
        base = {
            "match_id": 1,
            "period": 1,
            "team": team,
            "player": player,
            "type": type_,
            "location": [x, 40.0],
            "pass_end_location": end,
            "pass_outcome": None,
            "pass_type": None,
            "pass_shot_assist": None,
            "shot_type": None,
            "shot_outcome": None,
            "shot_statsbomb_xg": None,
            "duel_type": None,
        }
        base.update(kw)
        return base

    rows = []
    rows += [ev("Equipo X", "Jugadora Test", "Pass", x=50.0, end=[95.0, 40.0])] * 3
    rows += [ev("Equipo X", "Jugadora Test", "Carry", x=55.0)]
    rows.append(
        ev(
            "Equipo X",
            "Jugadora Test",
            "Shot",
            x=110.0,
            shot_type="Open Play",
            shot_outcome="Goal",
            shot_statsbomb_xg=0.4,
        )
    )
    rows += [ev("Equipo Y", "Rival", "Pass", x=50.0, end=[60.0, 40.0])] * 4
    rows += [ev("Equipo Y", "Rival", "Pressure", x=60.0)] * 2
    return pd.DataFrame(rows)


def tabla() -> pd.DataFrame:
    pct = {c: 60.0 for c in fit.GROUP_KEY_PCT["FW"]}

    def fw(nombre, equipo, minutos=450.0):
        return {
            "player": nombre,
            "nickname": nombre,
            "team": equipo,
            "primary_position": "Center Forward",
            "position_group": "FW",
            "role": "Delantero",
            "minutes": minutos,
            "npxg_p90": 0.4,
            "xa_p90": 0.2,
            "prog_passes_p90": 3.0,
            "prog_carries_p90": 2.0,
            "dribbles_cmp_p90": 1.5,
            "touches_box_p90": 4.0,
            "pressures_p90": 5.0,
            "padj_tack_int_p90": 1.0,
            "recoveries_p90": 3.0,
            "pass_pct": 78.0,
            **pct,
        }

    return pd.DataFrame([fw("Jugadora Test", "Equipo X"), fw("S1", "Equipo Y"), fw("S2", "Equipo Y")])


def test_player_report_pdf_genera_un_pdf_valido():
    pdf = report.player_report_pdf(tabla(), eventos(), "Jugadora Test", "Competición Test")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 10_000  # contiene los cuatro paneles renderizados
