"""Tests del motor de encaje jugador–equipo con datos sintéticos (sin red)."""

import pandas as pd

from futbol_analytics import fit


def _ev(team, type_, x=60.0, end=None, **kw):
    base = {
        "match_id": 1,
        "period": 1,
        "team": team,
        "type": type_,
        "location": [x, 40.0],
        "pass_end_location": end,
        "pass_outcome": None,
        "pass_type": None,
        "shot_type": None,
        "shot_outcome": None,
        "shot_statsbomb_xg": None,
        "duel_type": None,
    }
    base.update(kw)
    return base


def eventos_dos_estilos() -> pd.DataFrame:
    """A: posesivo y presionante; B: directo, poca posesión y poca presión."""
    rows = []
    # posesión: A 10 pases cortos (no progresivos), B 4 pases largos progresivos
    rows += [_ev("A", "Pass", x=50.0, end=[55.0, 40.0])] * 10
    rows += [_ev("B", "Pass", x=50.0, end=[95.0, 40.0])] * 4
    # presión: A presiona mucho y roba arriba; B apenas
    rows += [_ev("A", "Pressure", x=70.0)] * 8
    rows += [_ev("B", "Pressure", x=60.0)] * 2
    rows += [_ev("A", "Interception", x=70.0)] * 3
    rows += [_ev("B", "Interception", x=50.0)]
    return pd.DataFrame(rows)


def tabla_fw() -> pd.DataFrame:
    """Cuatro delanteros: Pressy (presión+pase) y Runner (conducción), más relleno."""
    base_pct = {c: 50.0 for c in fit.GROUP_KEY_PCT["FW"]}
    comunes = {"primary_position": "Center Forward", "position_group": "FW", "minutes": 900.0}

    def jugador(nombre, equipo, **traits):
        return {"player": nombre, "team": equipo, **comunes, **base_pct, **traits}

    return pd.DataFrame(
        [
            jugador(
                "Pressy",
                "B",
                pressures_p90=9.0,
                recoveries_p90=8.0,
                padj_tack_int_p90=5.0,
                pass_pct=90.0,
                prog_passes_p90=6.0,
                xa_p90=0.4,
                prog_carries_p90=1.0,
                dribbles_cmp_p90=0.5,
                touches_box_p90=2.0,
                npxg_p90=0.3,
            ),
            jugador(
                "Runner",
                "A",
                pressures_p90=2.0,
                recoveries_p90=2.0,
                padj_tack_int_p90=1.0,
                pass_pct=65.0,
                prog_passes_p90=2.0,
                xa_p90=0.1,
                prog_carries_p90=8.0,
                dribbles_cmp_p90=5.0,
                touches_box_p90=6.0,
                npxg_p90=0.5,
            ),
            jugador(
                "Medio A",
                "A",
                pressures_p90=4.0,
                recoveries_p90=4.0,
                padj_tack_int_p90=2.0,
                pass_pct=75.0,
                prog_passes_p90=3.0,
                xa_p90=0.2,
                prog_carries_p90=3.0,
                dribbles_cmp_p90=2.0,
                touches_box_p90=3.0,
                npxg_p90=0.2,
            ),
            jugador(
                "Medio B",
                "B",
                pressures_p90=4.0,
                recoveries_p90=4.0,
                padj_tack_int_p90=2.0,
                pass_pct=75.0,
                prog_passes_p90=3.0,
                xa_p90=0.2,
                prog_carries_p90=3.0,
                dribbles_cmp_p90=2.0,
                touches_box_p90=3.0,
                npxg_p90=0.2,
            ),
        ]
    )


def test_team_style_separa_los_dos_estilos():
    style = fit.team_style(eventos_dos_estilos())
    a, b = style.loc["A"], style.loc["B"]
    assert a["posesion_z"] > b["posesion_z"]
    assert a["presion_z"] > b["presion_z"]
    assert b["verticalidad_z"] > a["verticalidad_z"]


def test_player_traits_estandariza_dentro_del_grupo():
    traits = fit.player_traits(tabla_fw())
    pressy = traits[traits["player"] == "Pressy"].iloc[0]
    runner = traits[traits["player"] == "Runner"].iloc[0]
    assert pressy["pressures_p90"] > 0 > runner["pressures_p90"]
    assert runner["prog_carries_p90"] > 0 > pressy["prog_carries_p90"]


def test_el_presionador_encaja_en_el_equipo_presionante():
    destinos = fit.teams_for_player(tabla_fw(), eventos_dos_estilos(), "Pressy")
    assert destinos.iloc[0]["team"] == "A"
    a = destinos[destinos["team"] == "A"].iloc[0]
    b = destinos[destinos["team"] == "B"].iloc[0]
    assert a["estilo"] > b["estilo"]
    assert bool(b["propio"]) is True  # Pressy juega en B
    assert bool(a["propio"]) is False


def test_el_conductor_encaja_en_el_equipo_directo():
    destinos = fit.teams_for_player(tabla_fw(), eventos_dos_estilos(), "Runner")
    a = destinos[destinos["team"] == "A"].iloc[0]
    b = destinos[destinos["team"] == "B"].iloc[0]
    assert b["estilo"] > a["estilo"]


def test_fichajes_excluyen_a_los_propios_y_ordenan_por_encaje():
    fichajes = fit.players_for_team(tabla_fw(), eventos_dos_estilos(), "A", group="FW")
    assert set(fichajes["team"]) == {"B"}  # solo candidatos externos
    # para el equipo posesivo y presionante, Pressy por delante del relleno
    assert fichajes.iloc[0]["player"] == "Pressy"
    assert {"encaje", "estilo", "mejora_puesto", "posesion", "presion", "verticalidad"} <= set(
        fichajes.columns
    )


def test_mejora_del_puesto_neutral_con_percentiles_iguales():
    destinos = fit.teams_for_player(tabla_fw(), eventos_dos_estilos(), "Pressy")
    assert destinos["mejora_puesto"].abs().max() == 0.0
