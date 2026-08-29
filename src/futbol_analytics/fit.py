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
   hace mucho de lo que el estilo del equipo pide.

2. **Mejora del puesto** — percentil medio del jugador en las métricas
   clave de su grupo posicional (las mismas del radar) menos el nivel
   medio de los jugadores que el equipo ya tiene en ese grupo. Positivo
   significa que sube el nivel de la posición. Si el equipo no tiene
   jugadores de ese grupo en la tabla, se compara contra la media de la
   competición (percentil 50).

El encaje final (0-100) es el percentil de la media de ambos componentes
estandarizados dentro del conjunto comparado: ordena destinos o
fichajes *dentro de la competición cargada*, no tasa mercados reales.
Limitaciones completas en la página de Metodología.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import SET_PIECE_PASS_TYPES, is_progressive
from .teams import team_metrics

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


def team_style(events: pd.DataFrame) -> pd.DataFrame:
    """Por equipo: contexto crudo (posesión, PPDA, npxG...) + ejes de estilo (sufijo _z)."""
    base = team_metrics(events).set_index("team")

    ev = events[(events["period"] <= 4) & events["team"].notna()]
    passes = ev[(ev["type"] == "Pass") & ev["location"].notna() & ev["pass_end_location"].notna()]
    if "pass_outcome" in passes.columns:
        passes = passes[passes["pass_outcome"].isna()]
    if "pass_type" in passes.columns:
        passes = passes[~passes["pass_type"].isin(SET_PIECE_PASS_TYPES)]
    prog = is_progressive(passes["location"], passes["pass_end_location"])
    share = pd.DataFrame({"team": passes["team"], "prog": prog}).groupby("team")["prog"].mean()
    base["prog_share"] = (100 * share).reindex(base.index)

    base["posesion_z"] = _z(base["possession"])
    ppda = base["ppda"].fillna(base["ppda"].median())
    base["presion_z"] = (_z(-ppda) + _z(base["pressures_pm"])) / 2
    base["verticalidad_z"] = _z(base["prog_share"].fillna(base["prog_share"].median()))
    return base


def player_traits(table: pd.DataFrame) -> pd.DataFrame:
    """Rasgos per-90 del jugador estandarizados dentro de su grupo posicional."""
    traits = table[["player", "team", "position_group"]].copy()
    for col in TRAIT_COLS:
        if col in table.columns:
            traits[col] = table.groupby("position_group")[col].transform(_z)
        else:
            traits[col] = 0.0
    return traits


def style_breakdown(traits: pd.DataFrame, style_row: pd.Series) -> pd.DataFrame:
    """Aporte de cada eje de estilo (y el total) de cada jugador para un equipo."""
    out = pd.DataFrame(index=traits.index)
    for axis, pesos in AFFINITY.items():
        demanda = sum(w * traits[col] for col, w in pesos.items())
        out[axis] = float(style_row[f"{axis}_z"]) * demanda
    out["estilo"] = out[STYLE_AXES].sum(axis=1)
    return out


def _key_pct_mean(df: pd.DataFrame, group: str) -> pd.Series:
    cols = [c for c in GROUP_KEY_PCT.get(group, GROUP_KEY_PCT["MF"]) if c in df.columns]
    if not cols:
        return pd.Series(50.0, index=df.index)
    return df[cols].mean(axis=1)


def squad_level(table: pd.DataFrame) -> pd.DataFrame:
    """Nivel medio (percentil clave) de cada (equipo, grupo posicional)."""
    rows = [
        {"team": team, "position_group": group, "nivel": float(_key_pct_mean(sub, group).mean())}
        for (team, group), sub in table.groupby(["team", "position_group"])
    ]
    return pd.DataFrame(rows)


def _combine(estilo: pd.Series, mejora: pd.Series) -> pd.Series:
    """Encaje 0-100: percentil de la media de ambos componentes estandarizados."""
    total = (_z(estilo) + _z(mejora)) / 2
    return (100 * total.rank(pct=True)).round(0)


def teams_for_player(table: pd.DataFrame, events: pd.DataFrame, player: str) -> pd.DataFrame:
    """Ranking de equipos de la competición para un jugador, con desglose."""
    style = team_style(events)
    traits = player_traits(table)
    prow = table[table["player"] == player].iloc[0]
    ptraits = traits[traits["player"] == player]
    group = prow["position_group"]
    nivel_jugador = float(_key_pct_mean(table[table["player"] == player], group).iloc[0])
    niveles = squad_level(table).set_index(["team", "position_group"])["nivel"]

    rows = []
    for team, style_row in style.iterrows():
        desglose = style_breakdown(ptraits, style_row).iloc[0]
        nivel_puesto = float(niveles.get((team, group), 50.0))
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
    out["encaje"] = _combine(out["estilo"], out["mejora_puesto"])
    return out.sort_values("encaje", ascending=False).reset_index(drop=True)


def players_for_team(
    table: pd.DataFrame,
    events: pd.DataFrame,
    team: str,
    group: str | None = None,
) -> pd.DataFrame:
    """Ranking de fichajes de la competición para un equipo, con desglose."""
    style_row = team_style(events).loc[team]
    traits = player_traits(table)
    desglose = style_breakdown(traits, style_row)
    niveles = squad_level(table).set_index(["team", "position_group"])["nivel"]

    context = [c for c in PLAYER_CONTEXT_COLS if c in table.columns]
    out = table[["player", "team", "primary_position", "position_group", "minutes", *context]].copy()
    out = out.join(desglose[[*STYLE_AXES, "estilo"]])
    nivel_jugador = pd.Series(0.0, index=table.index)
    for g, sub in table.groupby("position_group"):
        nivel_jugador.loc[sub.index] = _key_pct_mean(sub, g)
    out["nivel_jugador"] = nivel_jugador
    out["mejora_puesto"] = [
        row["nivel_jugador"] - float(niveles.get((team, row["position_group"]), 50.0))
        for _, row in out.iterrows()
    ]

    out = out[out["team"] != team]
    if group:
        out = out[out["position_group"] == group]
    out = out.copy()
    out["encaje"] = _combine(out["estilo"], out["mejora_puesto"])
    return out.sort_values("encaje", ascending=False).reset_index(drop=True)
