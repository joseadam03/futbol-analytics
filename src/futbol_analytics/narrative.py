"""Narrativa en lenguaje llano sobre el perfil de un jugador.

Traduce los mismos percentiles que ya se ven en el radar (`viz.RADAR_METRICS`)
a 2-3 frases legibles por alguien no técnico. Nada inventado: reglas fijas y
deterministas sobre el dato ya calculado, no un LLM — así es reproducible y
se puede verificar frase a frase contra la tabla de percentiles.
"""

from __future__ import annotations

import pandas as pd

from . import viz

# (percentil mínimo, cómo se describe)
_BANDS = [
    (90, "de los mejores de la competición"),
    (75, "por encima de la media"),
    (25, "en la media"),
    (10, "por debajo de la media"),
    (0, "de los más bajos de la competición"),
]


def _band(pct: float) -> str:
    for umbral, etiqueta in _BANDS:
        if pct >= umbral:
            return etiqueta
    return _BANDS[-1][1]


def player_summary(prow: pd.Series, pool_desc: str, similar: pd.DataFrame | None = None) -> str:
    """2-3 frases: mejor y peor faceta del jugador (ejes de su radar) y a quién se parece.

    `pool_desc` es el grupo/rol contra el que se comparan los percentiles
    (mismo texto que ya usa el resto del informe). `similar`, si se pasa, es
    el resultado de `similarity.similar_players` (se usan sus 2 primeras filas).
    """
    group = prow.get("position_group")
    metrics = viz.RADAR_METRICS.get(group, viz.RADAR_METRICS["MF"])
    valores = [
        (label.replace("\n", " "), float(prow[col]))
        for col, label in metrics
        if col in prow.index and pd.notna(prow[col])
    ]
    if not valores:
        return ""

    valores.sort(key=lambda par: par[1], reverse=True)
    mejor_label, mejor_pct = valores[0]
    peor_label, peor_pct = valores[-1]

    # sin .lower(): abreviaturas como "PAdj" o "xA" pierden el sentido en minúsculas
    frases = [
        f"Su rasgo más destacado es {mejor_label} (percentil {mejor_pct:.0f}, "
        f"{_band(mejor_pct)} entre {pool_desc})."
    ]
    if peor_label != mejor_label and (mejor_pct - peor_pct) >= 20:
        frases.append(f"Su faceta más floja es {peor_label} (percentil {peor_pct:.0f}).")

    if similar is not None and not similar.empty:
        nombres = " y ".join(str(n) for n in similar["player"].head(2))
        frases.append(f"El perfil más parecido dentro de la competición es el de {nombres}.")

    return " ".join(frases)
