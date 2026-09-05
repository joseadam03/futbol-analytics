"""Tests del motor de encaje jugador–equipo con datos sintéticos (sin red)."""

import pandas as pd
import pytest

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


def test_etiqueta_realismo_umbrales():
    assert fit.etiqueta_realismo(0.0) == ""
    assert fit.etiqueta_realismo(25.0) == ""  # el umbral es estricto, no inclusive
    assert fit.etiqueta_realismo(25.1) == "Mejora clara"
    assert fit.etiqueta_realismo(40.0) == "Mejora clara"
    assert fit.etiqueta_realismo(40.1) == "Sobrecualificado — fichaje improbable en la práctica"
    assert fit.etiqueta_realismo(-30.0) == ""  # un downgrade no es "sobrecualificado"


def test_realismo_aparece_en_destinos_y_fichajes():
    destinos = fit.teams_for_player(tabla_fw(), eventos_dos_estilos(), "Pressy")
    assert "realismo" in destinos.columns
    assert (destinos["realismo"] == "").all()  # percentiles iguales: sin salto de nivel

    fichajes = fit.players_for_team(tabla_fw(), eventos_dos_estilos(), "A", group="FW")
    assert "realismo" in fichajes.columns
    assert fichajes["realismo"].map(lambda t: t == "" or "Mejora" in t or "Sobrecualificado" in t).all()


def test_squad_level_pondera_por_minutos():
    base = {c: 40.0 for c in fit.GROUP_KEY_PCT["FW"]}
    top = {c: 80.0 for c in fit.GROUP_KEY_PCT["FW"]}
    df = pd.DataFrame(
        [
            {"player": "Titular", "team": "A", "position_group": "FW", "minutes": 900.0, **base},
            {"player": "Suplente", "team": "A", "position_group": "FW", "minutes": 90.0, **top},
        ]
    )
    nivel = fit.squad_level(df).iloc[0]["nivel"]
    assert nivel == pytest.approx((40 * 900 + 80 * 90) / 990)


def test_mejora_usa_rol_fino_con_fallback():
    def defensa(nombre, equipo, rol, pct, minutos=900.0):
        fila = {c: pct for c in fit.GROUP_KEY_PCT["DF"]}
        return {
            "player": nombre,
            "team": equipo,
            "primary_position": "?",
            "position_group": "DF",
            "role": rol,
            "minutes": minutos,
            **fila,
        }

    tabla = pd.DataFrame(
        [
            defensa("Central A", "A", "Central", 80.0),
            defensa("Lateral A", "A", "Lateral", 30.0),
            defensa("Lateral B", "B", "Lateral", 60.0),
            defensa("Mediocentro B", "B", "Pivote", 60.0),
        ]
    )
    fichajes = fit.players_for_team(tabla, eventos_dos_estilos(), "A")
    lateral = fichajes[fichajes["player"] == "Lateral B"].iloc[0]
    pivote = fichajes[fichajes["player"] == "Mediocentro B"].iloc[0]
    # el lateral se compara con el lateral de A (30), no con la media del grupo DF (55)
    assert lateral["mejora_puesto"] == pytest.approx(30.0)
    # A no tiene pivotes: caída al nivel del grupo DF ponderado (55)
    assert pivote["mejora_puesto"] == pytest.approx(60.0 - 55.0)


def test_w_estilo_extremos_cambian_el_ranking():
    def delantero(nombre, equipo, pct, **traits):
        fila = {c: pct for c in fit.GROUP_KEY_PCT["FW"]}
        return {
            "player": nombre,
            "team": equipo,
            "primary_position": "Center Forward",
            "position_group": "FW",
            "minutes": 900.0,
            **fila,
            **traits,
        }

    tabla = pd.DataFrame(
        [
            delantero("Ancla A", "A", 50.0, pressures_p90=5.0, pass_pct=75.0),
            delantero("Estiloso", "B", 30.0, pressures_p90=9.0, pass_pct=90.0, prog_passes_p90=6.0),
            delantero("Productivo", "B", 90.0, pressures_p90=1.0, pass_pct=60.0, prog_passes_p90=1.0),
            delantero("Relleno", "C", 50.0, pressures_p90=5.0, pass_pct=75.0, prog_passes_p90=3.0),
        ]
    )
    ev = eventos_dos_estilos()
    solo_estilo = fit.players_for_team(tabla, ev, "A", w_estilo=1.0)
    solo_mejora = fit.players_for_team(tabla, ev, "A", w_estilo=0.0)
    assert solo_estilo.iloc[0]["player"] == "Estiloso"
    assert solo_mejora.iloc[0]["player"] == "Productivo"


def test_axis_weights_anulan_ejes():
    style = fit.team_style(eventos_dos_estilos())
    traits = fit.player_traits(tabla_fw())
    desglose = fit.style_breakdown(traits, style.loc["A"], axis_weights={"presion": 0.0, "verticalidad": 0.0})
    assert (desglose["presion"] == 0.0).all()
    assert (desglose["verticalidad"] == 0.0).all()
    assert desglose["estilo"].equals(desglose["posesion"])


def test_pool_multicompeticion_estandariza_dentro_de_cada_comp():
    def fw(nombre, equipo, comp, presiones):
        return {
            "player": nombre,
            "team": equipo,
            "competition": comp,
            "position_group": "FW",
            "minutes": 900.0,
            "pressures_p90": presiones,
        }

    pool = pd.DataFrame(
        [
            fw("X1", "A", "C1", 9.0),
            fw("X2", "B", "C1", 1.0),
            fw("Y1", "D", "C2", 5.0),
            fw("Y2", "E", "C2", 5.0),
        ]
    )
    traits = fit.player_traits(pool)
    assert traits[traits["player"] == "X1"].iloc[0]["pressures_p90"] > 0
    # en C2 todos presionan igual: z = 0 dentro de su competición
    assert traits[traits["player"] == "Y1"].iloc[0]["pressures_p90"] == pytest.approx(0.0)


def test_pool_multicompeticion_en_players_for_team():
    def fw(nombre, equipo, comp, pct):
        fila = {c: pct for c in fit.GROUP_KEY_PCT["FW"]}
        return {
            "player": nombre,
            "team": equipo,
            "competition": comp,
            "primary_position": "CF",
            "position_group": "FW",
            "minutes": 900.0,
            **fila,
        }

    pool = pd.DataFrame(
        [
            fw("Ancla A", "A", "C1", 50.0),
            fw("Cand B", "B", "C1", 60.0),
            fw("Cand D", "D", "C2", 70.0),
            fw("Cand E", "E", "C2", 30.0),
        ]
    )
    fichajes = fit.players_for_team(pool, eventos_dos_estilos(), "A")
    assert "competition" in fichajes.columns
    assert set(fichajes["player"]) == {"Cand B", "Cand D", "Cand E"}
    d = fichajes[fichajes["player"] == "Cand D"].iloc[0]
    # nivel del puesto del destino (A, FW en C1) = 55 ponderado... A solo tiene a Ancla (50)
    assert d["mejora_puesto"] == pytest.approx(70.0 - 50.0)


def _pool_puente(dif_nivel: float, n_puentes: int, n_propios: int = 5):
    """Pool de dos competiciones donde C2 infla los percentiles `dif_nivel` puntos."""
    filas = []

    def fw(nombre, equipo, comp, pct):
        base = {c: pct for c in fit.GROUP_KEY_PCT["FW"]}
        return {
            "player": nombre,
            "team": equipo,
            "competition": comp,
            "primary_position": "CF",
            "position_group": "FW",
            "minutes": 900.0,
            **base,
        }

    for i in range(n_puentes):  # jugadores presentes en las dos competiciones
        filas.append(fw(f"Puente {i}", "A", "C1", 50.0))
        filas.append(fw(f"Puente {i}", "D", "C2", 50.0 + dif_nivel))
    for i in range(n_propios):
        filas.append(fw(f"Solo1 {i}", "B", "C1", 40.0))
        filas.append(fw(f"Solo2 {i}", "E", "C2", 40.0 + dif_nivel))
    return pd.DataFrame(filas)


def test_offsets_detectan_la_inflacion_de_una_competicion():
    offsets = fit.competition_offsets(_pool_puente(dif_nivel=25.0, n_puentes=4), "C1")
    o = offsets.set_index("competition")
    assert o.loc["C1", "offset"] == 0.0  # la referencia no se mueve
    assert o.loc["C2", "bridged"]
    assert o.loc["C2", "n_bridge"] == 4
    # C2 infla 25 puntos -> hay que restarlos
    assert o.loc["C2", "offset"] == pytest.approx(-25.0)


def test_sin_puentes_suficientes_no_se_ajusta_y_se_marca():
    offsets = fit.competition_offsets(_pool_puente(dif_nivel=25.0, n_puentes=1), "C1")
    c2 = offsets.set_index("competition").loc["C2"]
    assert c2["offset"] == 0.0
    assert not c2["bridged"]
    assert c2["n_bridge"] == 1


def test_offsets_sin_columna_de_competicion_devuelve_vacio():
    assert fit.competition_offsets(tabla_fw(), "X").empty


def test_el_ajuste_corrige_la_mejora_del_puesto():
    pool = _pool_puente(dif_nivel=25.0, n_puentes=4)
    ev = eventos_dos_estilos()
    # el equipo A juega en C1; los candidatos de C2 llegan inflados
    sin = fit.players_for_team(pool, ev, "A", adjust_level=False)
    con = fit.players_for_team(pool, ev, "A", adjust_level=True)

    c2_sin = sin[sin["competition"] == "C2"]["mejora_puesto"].mean()
    c2_con = con[con["competition"] == "C2"]["mejora_puesto"].mean()
    assert c2_con == pytest.approx(c2_sin - 25.0)
    # los de la propia competición no se tocan
    c1_sin = sin[sin["competition"] == "C1"]["mejora_puesto"].mean()
    c1_con = con[con["competition"] == "C1"]["mejora_puesto"].mean()
    assert c1_con == pytest.approx(c1_sin)
    assert set(con["bridged"]) == {True}
