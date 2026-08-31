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


def test_destaca_el_percentil_mas_alto_y_el_mas_bajo():
    texto = narrative.player_summary(_prow(), "delanteros")
    assert "regates" in texto.lower() or "conducciones" in texto.lower()  # el 97 más alto (empate)
    assert "presiones" in texto.lower()  # el 3, el más bajo
    assert "percentil 97" in texto
    assert "percentil 3" in texto


def test_no_menciona_faceta_floja_si_la_diferencia_es_pequena():
    # todas las métricas a menos de 20 puntos del máximo (97): sin hueco notable
    prow = _prow(
        shots_p90_pct=85.0,
        xa_p90_pct=80.0,
        key_passes_p90_pct=90.0,
        touches_box_p90_pct=85.0,
        prog_passes_p90_pct=90.0,
        pressures_p90_pct=80.0,
    )
    texto = narrative.player_summary(prow, "delanteros")
    assert "faceta más floja" not in texto


def test_incluye_similares_si_se_pasan():
    similar = pd.DataFrame({"player": ["Jamal Musiala", "Lionel Messi"]})
    texto = narrative.player_summary(_prow(), "delanteros", similar)
    assert "Jamal Musiala" in texto
    assert "Lionel Messi" in texto


def test_sin_similares_no_revienta():
    texto = narrative.player_summary(_prow(), "delanteros", pd.DataFrame())
    assert "parecido" not in texto


def test_grupo_sin_metricas_conocidas_cae_a_mf():
    prow = _prow(position_group="XX")  # grupo inexistente
    texto = narrative.player_summary(prow, "jugadores")
    assert texto  # usa el set de MF por defecto, no revienta


def test_sin_ninguna_columna_de_percentil_devuelve_vacio():
    prow = pd.Series({"position_group": "FW"})
    assert narrative.player_summary(prow, "delanteros") == ""
