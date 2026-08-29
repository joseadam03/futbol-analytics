"""Motor de encaje jugador–equipo: ¿quién ficha a quién, según los datos?

Responde a dos preguntas simétricas sobre la competición cargada:
a qué equipos les encaja un jugador, y qué jugadores le encajan a un
equipo. El encaje combina dos componentes:

1. **Estilo** — cada equipo se caracteriza en tres ejes (z-score entre
   los equipos de la competición): posesión, intensidad de presión
   (PPDA invertido + presiones por partido) y verticalidad (cuota de
   pases progresivos sobre pases completados en juego). Cada jugador se
   caracteriza por sus métricas per-90 estandarizadas dentro de su grupo
   posicional. La matriz AFFINITY traduce cada eje en los rasgos que ese
   estilo demanda: un equipo presionante valora presiones y
   recuperaciones; uno posesivo, fiabilidad y progresión en el pase; uno
   vertical, conducción, regate y llegada. El componente de estilo es el
   producto z_equipo · AFFINITY · z_jugador: positivo cuando el jugador
   hace mucho de lo que el estilo del equipo pide. Los ejes admiten
   pesos configurables (axis_weights) para explorar los supuestos.

2. **Mejora del puesto** — percentil medio del jugador en las métricas
   clave de su grupo posicional (las mismas del radar) menos el nivel
   del puesto en el equipo de destino: la media de sus jugadores del
   mismo **rol fino** (un lateral no compite con un central),
   **ponderada por minutos** (el titular pesa más que el suplente).
   Sin jugadores de ese rol, se compara contra el grupo posicional; sin
   grupo, contra la media de la competición (percentil 50).

El encaje final (0-100) es el percentil de la combinación ponderada
(w_estilo, por defecto 0.5) de ambos componentes estandarizados dentro
del conjunto comparado: ordena destinos o fichajes *dentro del pool
analizado*, no tasa mercados reales.

Si la tabla trae una columna ``competition`` (pool multi-competición),
los z-scores y niveles se calculan dentro de la competición de origen de
cada jugador: comparar percentiles entre competiciones de nivel dispar
es una aproximación, y así se documenta en la app.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .teams import team_metrics, team_style_metrics

STYLE_AXES = ["posesion", "presion", "verticalidad"]

# eje de estilo -> rasgos per-90 del jugador que ese estilo demanda
AFFINITY = {
    "posesion": {"pass_pct": 0.5, "prog_passes_p90": 0.3, "xa_p90": 0.2},
    "presion": {"pressures_p90": 0.6, "recoveries_p90": 0.25, "padj_tack_int_p90": 0.15},
    "verticalidad": {
        "prog_carries_p90": 0.35,
        "dribbles_cmp_p90": 0.25,
        "prog_passes_p90": 0.2,
        "touches_box_p90": 0.2,
    },
}
TRAIT_COLS = sorted({col for pesos in AFFINITY.values() for col in pesos})

# métricas clave por grupo posicional (espejo del radar) para "mejora del puesto"
GROUP_KEY_PCT = {
    "FW": [
        "npxg_p90_pct",
        "shots_p90_pct",
        "xa_p90_pct",
        "key_passes_p90_pct",
        "dribbles_cmp_p90_pct",
        "touches_box_p90_pct",
        "prog_carries_p90_pct",
        "prog_passes_p90_pct",
        "pressures_p90_pct",
    ],
    "MF": [
        "npxg_p90_pct",
        "xa_p90_pct",
        "key_passes_p90_pct",
        "prog_passes_p90_pct",
        "prog_carries_p90_pct",
        "dribbles_cmp_p90_pct",
        "pressures_p90_pct",
        "padj_tack_int_p90_pct",
        "recoveries_p90_pct",
    ],
    "DF": [
        "padj_tack_int_p90_pct",
        "blocks_p90_pct",
        "clearances_p90_pct",
        "recoveries_p90_pct",
        "pressures_p90_pct",
        "prog_passes_p90_pct",
        "prog_carries_p90_pct",
        "xa_p90_pct",
    ],
}
GROUP_KEY_PCT["GK"] = GROUP_KEY_PCT["DF"]

# contexto del jugador que acompaña a los rankings de fichajes
PLAYER_CONTEXT_COLS = ["npxg_p90", "xa_p90", "prog_passes_p90", "pressures_p90", "padj_tack_int_p90"]


def _z(s: pd.Series) -> pd.Series:
    std = s.std(ddof=0)
    if not std or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def _pool_keys(table: pd.DataFrame, extra: list[str]) -> list[str]:
    """Claves de agrupación: dentro de la competición de origen si el pool es multi-comp."""
    return (["competition"] if "competition" in table.columns else []) + extra


def team_style(events: pd.DataFrame) -> pd.DataFrame:
    """Por equipo: contexto crudo (posesión, PPDA, npxG...) + ejes de estilo (sufijo _z)."""
    base = team_metrics(events).set_index("team")
    estilo = team_style_metrics(events).set_index("team")
    base["prog_share"] = estilo["prog_pass_share"].reindex(base.index)

    base["posesion_z"] = _z(base["possession"])
    ppda = base["ppda"].fillna(base["ppda"].median())
    base["presion_z"] = (_z(-ppda) + _z(base["pressures_pm"])) / 2
    base["verticalidad_z"] = _z(base["prog_share"].fillna(base["prog_share"].median()))
    return base


def player_traits(table: pd.DataFrame) -> pd.DataFrame:
    """Rasgos per-90 estandarizados dentro del grupo posicional (y competición de origen)."""
    keys = _pool_keys(table, ["position_group"])
    traits = table[["player", "team", "position_group"]].copy()
    for col in TRAIT_COLS:
        if col in table.columns:
            traits[col] = table.groupby(keys)[col].transform(_z)
        else:
            traits[col] = 0.0
    return traits


def style_breakdown(
    traits: pd.DataFrame,
    style_row: pd.Series,
    axis_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Aporte de cada eje de estilo (y el total) de cada jugador para un equipo."""
    axis_weights = axis_weights or {}
    out = pd.DataFrame(index=traits.index)
    for axis, pesos in AFFINITY.items():
        demanda = sum(w * traits[col] for col, w in pesos.items())
        out[axis] = float(axis_weights.get(axis, 1.0)) * float(style_row[f"{axis}_z"]) * demanda
    out["estilo"] = out[STYLE_AXES].sum(axis=1)
    return out


def _key_pct_mean(df: pd.DataFrame, group: str) -> pd.Series:
    cols = [c for c in GROUP_KEY_PCT.get(group, GROUP_KEY_PCT["MF"]) if c in df.columns]
    if not cols:
        return pd.Series(50.0, index=df.index)
    return df[cols].mean(axis=1)


def squad_level(table: pd.DataFrame, by: str = "position_group") -> pd.DataFrame:
    """Nivel del puesto por (equipo, `by`): percentil clave medio ponderado por minutos."""
    rows = []
    keys = _pool_keys(table, ["team", by])
    for key, sub in table.groupby(keys):
        group = sub["position_group"].mode().iloc[0]
        pcts = _key_pct_mean(sub, group)
        pesos = sub["minutes"].clip(lower=1.0)
        rows.append(
            {
                **dict(zip(keys, key if isinstance(key, tuple) else (key,))),
                "nivel": float(np.average(pcts, weights=pesos)),
            }
        )
    return pd.DataFrame(rows)


def _nivel_lookup(table: pd.DataFrame) -> tuple[pd.Series, pd.Series | None]:
    """Niveles por (equipo, grupo) y, si hay columna de rol, por (equipo, rol)."""
    por_grupo = squad_level(table, by="position_group").set_index(
        _pool_keys(table, ["team", "position_group"])
    )["nivel"]
    por_rol = None
    if "role" in table.columns and table["role"].notna().any():
        por_rol = squad_level(table.dropna(subset=["role"]), by="role").set_index(
            _pool_keys(table, ["team", "role"])
        )["nivel"]
    return por_grupo, por_rol


def _nivel_puesto(
    por_grupo: pd.Series,
    por_rol: pd.Series | None,
    key_prefix: tuple,
    team: str,
    role,
    group: str,
) -> float:
    """Rol fino si el equipo tiene jugadores de ese rol; si no, grupo; si no, 50."""
    if por_rol is not None and isinstance(role, str):
        clave = (*key_prefix, team, role)
        if clave in por_rol.index:
            return float(por_rol.loc[clave])
    clave = (*key_prefix, team, group)
    if clave in por_grupo.index:
        return float(por_grupo.loc[clave])
    return 50.0


MIN_BRIDGE_PLAYERS = 3


def competition_offsets(
    pool: pd.DataFrame,
    reference: str,
    min_players: int = MIN_BRIDGE_PLAYERS,
) -> pd.DataFrame:
    """Desplazamiento de nivel de cada competición frente a la de referencia.

    Los percentiles son relativos a su propia competición: un 80 en una liga
    menor no vale lo mismo que un 80 en una mayor. Para corregirlo sin
    inventar coeficientes, se usa el truco clásico de *linking* por elementos
    comunes: los **jugadores puente**, presentes en ambas competiciones. Si un
    jugador rinde en el percentil 60 en la de referencia y en el 85 en la otra,
    esos 25 puntos son inflación de la segunda. El desplazamiento es la
    mediana de esa diferencia entre todos los puentes (robusta a casos raros).

    Devuelve una fila por competición con el desplazamiento (`offset`, a sumar
    a sus percentiles), cuántos puentes lo sustentan y si hay puente. Las
    competiciones sin puentes suficientes quedan con offset 0 y `bridged=False`:
    la app lo dice en vez de fingir una corrección que no puede calcular.
    """
    filas = []
    if "competition" not in pool.columns:
        return pd.DataFrame(columns=["competition", "offset", "n_bridge", "bridged"])

    nivel = pd.Series(0.0, index=pool.index)
    for g, sub in pool.groupby("position_group"):
        nivel.loc[sub.index] = _key_pct_mean(sub, g)
    aux = pool[["player", "competition"]].assign(nivel=nivel)
    ref = aux[aux["competition"] == reference].groupby("player")["nivel"].mean()

    for comp, sub in aux.groupby("competition"):
        if comp == reference:
            filas.append({"competition": comp, "offset": 0.0, "n_bridge": 0, "bridged": True})
            continue
        niveles = sub.groupby("player")["nivel"].mean()
        puentes = niveles.index.intersection(ref.index)
        if len(puentes) >= min_players:
            offset = float((ref[puentes] - niveles[puentes]).median())
            filas.append({"competition": comp, "offset": offset, "n_bridge": len(puentes), "bridged": True})
        else:
            filas.append({"competition": comp, "offset": 0.0, "n_bridge": len(puentes), "bridged": False})
    return pd.DataFrame(filas)


def _combine(estilo: pd.Series, mejora: pd.Series, w_estilo: float = 0.5) -> pd.Series:
    """Encaje 0-100: percentil de la combinación ponderada de componentes estandarizados."""
    w = min(max(float(w_estilo), 0.0), 1.0)
    total = w * _z(estilo) + (1 - w) * _z(mejora)
    return (100 * total.rank(pct=True)).round(0)


def teams_for_player(
    table: pd.DataFrame,
    events: pd.DataFrame,
    player: str,
    w_estilo: float = 0.5,
    axis_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Ranking de equipos de la competición para un jugador, con desglose."""
    style = team_style(events)
    traits = player_traits(table)
    prow = table[table["player"] == player].iloc[0]
    ptraits = traits[traits["player"] == player]
    group = prow["position_group"]
    role = prow.get("role")
    nivel_jugador = float(_key_pct_mean(table[table["player"] == player], group).iloc[0])
    por_grupo, por_rol = _nivel_lookup(table)
    key_prefix: tuple = (prow["competition"],) if "competition" in table.columns else ()

    rows = []
    for team, style_row in style.iterrows():
        desglose = style_breakdown(ptraits, style_row, axis_weights).iloc[0]
        nivel_puesto = _nivel_puesto(por_grupo, por_rol, key_prefix, team, role, group)
        rows.append(
            {
                "team": team,
                "propio": team == prow["team"],
                "estilo": desglose["estilo"],
                **{axis: desglose[axis] for axis in STYLE_AXES},
                "nivel_puesto": nivel_puesto,
                "mejora_puesto": nivel_jugador - nivel_puesto,
                "possession": style_row["possession"],
                "ppda": style_row["ppda"],
                "prog_share": style_row["prog_share"],
                "npxg_diff_pm": style_row["npxg_diff_pm"],
                "matches": style_row["matches"],
            }
        )
    out = pd.DataFrame(rows)
    out["encaje"] = _combine(out["estilo"], out["mejora_puesto"], w_estilo)
    return out.sort_values("encaje", ascending=False).reset_index(drop=True)


def players_for_team(
    table: pd.DataFrame,
    events: pd.DataFrame,
    team: str,
    group: str | None = None,
    w_estilo: float = 0.5,
    axis_weights: dict[str, float] | None = None,
    adjust_level: bool = True,
) -> pd.DataFrame:
    """Ranking de fichajes para un equipo, con desglose. La tabla puede ser un
    pool multi-competición (columna ``competition``); el equipo destino debe
    pertenecer a la competición de la que provienen ``events``.

    Con `adjust_level`, los percentiles de las competiciones ajenas se corrigen
    con `competition_offsets` (jugadores puente) antes de calcular la mejora
    del puesto; las columnas `offset` y `bridged` dejan ver el ajuste aplicado."""
    style_row = team_style(events).loc[team]
    traits = player_traits(table)
    desglose = style_breakdown(traits, style_row, axis_weights)
    por_grupo, por_rol = _nivel_lookup(table)

    # el nivel del puesto se mide en el equipo destino, dentro de SU competición
    key_prefix: tuple = ()
    if "competition" in table.columns:
        comp_destino = table.loc[table["team"] == team, "competition"]
        key_prefix = (comp_destino.iloc[0],) if not comp_destino.empty else (None,)

    cols = ["player", "team", "primary_position", "position_group", "minutes"]
    for opcional in ("nickname", "role", "competition"):
        if opcional in table.columns:
            cols.append(opcional)
    cols += [c for c in PLAYER_CONTEXT_COLS if c in table.columns]
    out = table[cols].copy()
    out = out.join(desglose[[*STYLE_AXES, "estilo"]])

    nivel_jugador = pd.Series(0.0, index=table.index)
    for g, sub in table.groupby("position_group"):
        nivel_jugador.loc[sub.index] = _key_pct_mean(sub, g)
    out["nivel_jugador"] = nivel_jugador

    # el nivel de otras competiciones se corrige con los jugadores puente
    if adjust_level and "competition" in table.columns and key_prefix:
        offsets = competition_offsets(table, str(key_prefix[0])).set_index("competition")
        out["offset"] = out["competition"].map(offsets["offset"]).fillna(0.0)
        out["bridged"] = out["competition"].map(offsets["bridged"]).fillna(False)
        out["nivel_jugador"] = (out["nivel_jugador"] + out["offset"]).clip(0, 100)

    out["mejora_puesto"] = [
        row["nivel_jugador"]
        - _nivel_puesto(por_grupo, por_rol, key_prefix, team, row.get("role"), row["position_group"])
        for _, row in out.iterrows()
    ]

    out = out[out["team"] != team]
    if group:
        out = out[out["position_group"] == group]
    out = out.copy()
    out["encaje"] = _combine(out["estilo"], out["mejora_puesto"], w_estilo)
    return out.sort_values("encaje", ascending=False).reset_index(drop=True)
