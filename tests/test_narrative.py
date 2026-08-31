"""Tests de la narrativa por reglas: nada inventado, solo texto sobre percentiles reales."""

import pandas as pd

from futbol_analytics import narrative


def _prow(**overrides) -> pd.Series:
    base = {
        "position_group": "FW",
        "npxg_p90_pct": 88.0,
        "shots_p90_pct": 70.0,
        "xa_p90_pct": 68.0,
        "key_passes_p90_pct": 60.0,
        "dribbles_cmp_p90_pct": 97.0,
        "touches_box_p90_pct": 80.0,
        "prog_carries_p90_pct": 97.0,
        "prog_passes_p90_pct": 87.0,
        "pressures_p90_pct": 3.0,
    }
    base.update(overrides)
    return pd.Series(base)


def test_fortalezas_son_los_percentiles_mas_altos():
    _, fortalezas, _ = narrative.player_strengths(_prow(), "delanteros")
    titulos = " ".join(titulo for titulo, _ in fortalezas)
    assert "regates" in titulos.lower() or "conducciones" in titulos.lower()  # el 97 más alto (empate)
    assert "percentil 97" in titulos


def test_debilidades_son_los_percentiles_mas_bajos():
    _, _, debilidades = narrative.player_strengths(_prow(), "delanteros")
    titulos = " ".join(titulo for titulo, _ in debilidades)
    assert "presiones" in titulos.lower()  # el 3, el más bajo
    assert "percentil 3" in titulos


def test_debilidades_no_vacia_aunque_nada_baje_de_40():
    # todas las métricas a 60+: ninguna es una "debilidad" de verdad, pero
    # la columna no debe quedar vacía — se muestra igualmente la más floja
    prow = _prow(
        shots_p90_pct=85.0,
        xa_p90_pct=80.0,
        key_passes_p90_pct=90.0,
        touches_box_p90_pct=85.0,
        prog_passes_p90_pct=90.0,
        pressures_p90_pct=60.0,
    )
    _, _, debilidades = narrative.player_strengths(prow, "delanteros")
    assert debilidades


def test_grupo_sin_metricas_conocidas_cae_a_mf():
    prow = _prow(position_group="XX")  # grupo inexistente
    resumen, fortalezas, debilidades = narrative.player_strengths(prow, "jugadores")
    assert resumen and fortalezas and debilidades  # usa el set de MF por defecto, no revienta


def test_sin_ninguna_columna_de_percentil_devuelve_vacio():
    prow = pd.Series({"position_group": "FW"})
    resumen, fortalezas, debilidades = narrative.player_strengths(prow, "delanteros")
    assert resumen == "" and fortalezas == [] and debilidades == []


def test_incluye_una_definicion_en_lenguaje_llano_de_la_metrica_destacada():
    # sin esto, alguien que no conoce la jerga no sabe qué es "Regates"
    _, fortalezas, _ = narrative.player_strengths(_prow(), "delanteros")
    definiciones = " ".join(definicion for _, definicion in fortalezas)
    assert "1 contra 1" in definiciones  # definición de Regates


def test_incluye_un_percentil_medio_como_resumen_general():
    resumen, _, _ = narrative.player_strengths(_prow(), "delanteros")
    assert "percentil medio" in resumen
    assert resumen.startswith("Perfil ")


def test_similar_players_note_incluye_los_nombres():
    similar = pd.DataFrame({"player": ["Jamal Musiala", "Lionel Messi"]})
    texto = narrative.similar_players_note(similar)
    assert "Jamal Musiala" in texto
    assert "Lionel Messi" in texto
    assert "no necesariamente el mismo nivel" in texto


def test_similar_players_note_vacio_sin_datos():
    assert narrative.similar_players_note(None) == ""
    assert narrative.similar_players_note(pd.DataFrame()) == ""
