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


Rasgo = tuple[str, str]  # (título con percentil, definición en lenguaje llano)


def player_strengths(prow: pd.Series, pool_desc: str) -> tuple[str, list[Rasgo], list[Rasgo]]:
    """Nivel general en una frase, y sus rasgos en formato fortalezas/debilidades (no prosa):
    más escaneable para alguien que solo quiere ver de un vistazo en qué destaca y en qué no.

    Cada rasgo se devuelve como (título, definición) por separado — no como una sola línea —
    para que quien lo muestre pueda ponerlos en líneas distintas sin que el percentil (el dato
    que más importa) se pierda si la línea completa no cabe en el ancho disponible. `pool_desc`
    es el grupo/rol contra el que se comparan los percentiles (mismo texto que ya usa el resto
    del informe). Devuelve (resumen, fortalezas, debilidades); las listas pueden salir vacías
    si no hay métricas disponibles, pero el resumen sí lo estará en ese caso.
    """
    group = prow.get("position_group")
    metrics = viz.RADAR_METRICS.get(group, viz.RADAR_METRICS["MF"])
    valores = [
        (col, label.replace("\n", " "), float(prow[col]))
        for col, label in metrics
        if col in prow.index and pd.notna(prow[col])
    ]
    if not valores:
        return "", [], []

    valores.sort(key=lambda t: t[2], reverse=True)
    media = sum(pct for _, _, pct in valores) / len(valores)
    resumen = f"Perfil {_band(media)} entre {pool_desc} (percentil medio {media:.0f} en sus métricas clave)."

    def _rasgo(item: tuple[str, str, float]) -> Rasgo:
        col, label, pct = item
        return (f"{label} — percentil {pct:.0f}", _METRIC_DEFS.get(col, ""))

    fortalezas = [_rasgo(v) for v in valores[: min(2, len(valores))]]

    # solo cuenta como debilidad real (percentil ≤40); si nada llega tan bajo,
    # se muestra igualmente la más floja para no dejar la columna vacía
    flojas = [v for v in reversed(valores) if v[2] <= 40][:2] or [valores[-1]]
    debilidades = [_rasgo(v) for v in flojas]

    return resumen, fortalezas, debilidades


def season_strengths(temporadas: list[dict]) -> tuple[list[Rasgo], list[Rasgo]]:
    """Fortalezas y puntos a vigilar a partir de estadísticas de temporada (Sportmonks).

    Para jugadores fuera de los open data no hay eventos con coordenadas, así
    que no hay percentiles frente a rivales — esto no es un ranking, son
    hechos directos de la tabla de temporadas (participación, contribución de
    gol, titularidad) resumidos como conclusión. A diferencia de
    `player_strengths`, si no hay ninguna tendencia negativa real que señalar,
    la lista de "a vigilar" sale vacía en vez de forzar una: no hay percentil
    de referencia para decidir qué es "flojo".
    """
    con_minutos = [t for t in temporadas if isinstance(t.get("minutes"), (int, float)) and t["minutes"] > 0]
    if not con_minutos:
        return [], []
    recientes = sorted(con_minutos, key=lambda t: str(t.get("season_name", "")), reverse=True)
    actual = recientes[0]
    anterior = recientes[1] if len(recientes) > 1 else None

    def _num(t: dict, campo: str) -> float:
        v = t.get(campo)
        return float(v) if isinstance(v, (int, float)) else 0.0

    fortalezas: list[Rasgo] = []
    a_vigilar: list[Rasgo] = []

    if anterior is not None:
        min_actual, min_anterior = _num(actual, "minutes"), _num(anterior, "minutes")
        temporada_actual, temporada_anterior = (
            actual.get("season_name", "?"),
            anterior.get("season_name", "?"),
        )
        if min_anterior > 0 and min_actual >= min_anterior * 1.2:
            fortalezas.append(
                (
                    f"Más protagonismo — {min_actual:.0f} min en {temporada_actual}",
                    f"subió desde {min_anterior:.0f} min en {temporada_anterior}",
                )
            )
        elif min_anterior > 0 and min_actual <= min_anterior * 0.7:
            a_vigilar.append(
                (
                    f"Menos protagonismo — {min_actual:.0f} min en {temporada_actual}",
                    f"bajó desde {min_anterior:.0f} min en {temporada_anterior}",
                )
            )

    apariciones, titularidades = _num(actual, "appearances"), _num(actual, "lineups")
    if apariciones > 0:
        ratio = titularidades / apariciones
        temporada = actual.get("season_name", "?")
        if ratio >= 0.7:
            fortalezas.append(
                (
                    f"Titular habitual — {titularidades:.0f} de {apariciones:.0f} partidos ({temporada})",
                    "juega de inicio la mayoría de partidos disputados",
                )
            )
        elif ratio <= 0.3:
            a_vigilar.append(
                (
                    f"Poca titularidad — {titularidades:.0f} de {apariciones:.0f} partidos ({temporada})",
                    "entra sobre todo desde el banquillo",
                )
            )

    goles, asistencias, minutos = _num(actual, "goals"), _num(actual, "assists"), _num(actual, "minutes")
    if (goles + asistencias) > 0 and minutos > 0:
        temporada = actual.get("season_name", "?")
        fortalezas.append(
            (
                f"Contribución en gol — {goles:.0f}+{asistencias:.0f} en {temporada}",
                f"un gol o asistencia cada {minutos / (goles + asistencias):.0f} minutos",
            )
        )

    porterias_cero = actual.get("clean_sheets")
    if isinstance(porterias_cero, (int, float)) and apariciones > 0:
        temporada = actual.get("season_name", "?")
        fortalezas.append(
            (
                f"Porterías a cero — {porterias_cero:.0f} de {apariciones:.0f} partidos ({temporada})",
                "",
            )
        )

    return fortalezas[:2], a_vigilar[:2]


def similar_players_note(similar: pd.DataFrame | None) -> str:
    """Frase sobre a qué jugadores se parece, dejando claro que es de estilo, no de nivel."""
    if similar is None or similar.empty:
        return ""
    nombres = " y ".join(str(n) for n in similar["player"].head(2))
    return (
        f"Juega de forma parecida a {nombres} — mismo tipo de perfil dentro de la "
        "competición, no necesariamente el mismo nivel."
    )
