"""Narrativa en lenguaje llano sobre el perfil de un jugador.

Traduce los mismos percentiles que ya se ven en el radar (`viz.RADAR_METRICS`)
a unas frases legibles por alguien no técnico, explicando también qué mide
cada métrica — no basta con nombrarla, un lector sin conocimiento de fútbol
analítico no sabe qué es un "PAdj" o un "pase progresivo". Reglas fijas y
deterministas sobre el dato ya calculado, no un LLM: nada inventado, todo
verificable frase a frase contra la tabla de percentiles.
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

# qué mide cada métrica del radar, en una frase corta para quien no conoce
# la jerga (las mismas métricas que documenta el README, resumidas)
_METRIC_DEFS = {
    "npxg_p90_pct": "peligro generado con los tiros, sin contar penaltis",
    "shots_p90_pct": "volumen de tiros a portería",
    "xa_p90_pct": "calidad de las ocasiones que genera con el pase",
    "key_passes_p90_pct": "pases que dejan a un compañero en posición de tirar",
    "dribbles_cmp_p90_pct": "regates completados, superar a un rival en el 1 contra 1",
    "touches_box_p90_pct": "presencia dentro del área rival",
    "prog_carries_p90_pct": "conducciones que avanzan el balón hacia la portería rival",
    "prog_passes_p90_pct": "pases que avanzan el balón hacia la portería rival",
    "pressures_p90_pct": "acciones para forzar la pérdida del balón rival",
    "padj_tack_int_p90_pct": "entradas e intercepciones, ajustadas por la posesión de su equipo",
    "recoveries_p90_pct": "recuperaciones de balón",
    "blocks_p90_pct": "bloqueos de tiros o pases",
    "clearances_p90_pct": "despejes defensivos",
}


def _band(pct: float) -> str:
    for umbral, etiqueta in _BANDS:
        if pct >= umbral:
            return etiqueta
    return _BANDS[-1][1]


def _con_definicion(label: str, col: str) -> str:
    definicion = _METRIC_DEFS.get(col)
    return f"{label} ({definicion})" if definicion else label


def player_summary(prow: pd.Series, pool_desc: str, similar: pd.DataFrame | None = None) -> str:
    """Perfil en lenguaje llano: nivel general, sus 2 rasgos más fuertes, el más flojo y a quién
    se parece — cada métrica con una definición corta, para que se entienda sin conocer la jerga.

    `pool_desc` es el grupo/rol contra el que se comparan los percentiles (mismo texto que ya
    usa el resto del informe). `similar`, si se pasa, es el resultado de
    `similarity.similar_players` (se usan sus 2 primeras filas).
    """
    group = prow.get("position_group")
    metrics = viz.RADAR_METRICS.get(group, viz.RADAR_METRICS["MF"])
    valores = [
        (col, label.replace("\n", " "), float(prow[col]))
        for col, label in metrics
        if col in prow.index and pd.notna(prow[col])
    ]
    if not valores:
        return ""

    valores.sort(key=lambda t: t[2], reverse=True)
    media = sum(pct for _, _, pct in valores) / len(valores)

    frases = [f"Perfil {_band(media)} entre {pool_desc} (percentil medio {media:.0f} en sus métricas clave)."]

    top = valores[: min(2, len(valores))]
    destacados = [f"{_con_definicion(label, col)}: percentil {pct:.0f}" for col, label, pct in top]
    frases.append("Destaca sobre todo en " + " y en ".join(destacados) + ".")

    col_p, label_p, pct_p = valores[-1]
    if label_p not in {label for _, label, _ in top} and (top[0][2] - pct_p) >= 20:
        frases.append(f"Su faceta más floja es {_con_definicion(label_p, col_p)}, con percentil {pct_p:.0f}.")

    if similar is not None and not similar.empty:
        nombres = " y ".join(str(n) for n in similar["player"].head(2))
        frases.append(
            f"Juega de forma parecida a {nombres} — mismo tipo de perfil dentro de la "
            "competición, no necesariamente el mismo nivel."
        )

    return " ".join(frases)
