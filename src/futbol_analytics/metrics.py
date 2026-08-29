"""Métricas de rendimiento por jugador a partir de eventos StatsBomb.

Definiciones completas en el README (sección Metodología). Reglas globales:
- Se excluyen las tandas de penaltis (periodo 5).
- npxG y npG excluyen penaltis dentro del juego.
- Pase progresivo/conducción progresiva: reduce la distancia a portería
  rival en al menos un 25 % (portería en x=120, y=40).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SET_PIECE_PASS_TYPES = {"Corner", "Free Kick", "Throw-in", "Kick Off", "Goal Kick"}

GOAL_X, GOAL_Y = 120.0, 40.0
BOX_X, BOX_Y_MIN, BOX_Y_MAX = 102.0, 18.0, 62.0

COUNT_METRICS = [
    "npg", "npxg", "shots", "assists", "xa", "key_passes",
    "passes_cmp", "prog_passes", "prog_carries", "dribbles_cmp",
    "touches_box", "pressures", "tackles", "interceptions",
    "padj_tack_int", "recoveries", "blocks", "clearances",
]


def position_group(position: str | float) -> str | float:
    if not isinstance(position, str):
        return np.nan
    if position == "Goalkeeper":
        return "GK"
    if "Back" in position:
        return "DF"
    if "Midfield" in position:
        return "MF"
    return "FW"


def _xy(loc: pd.Series) -> tuple[pd.Series, pd.Series]:
    x = loc.str[0].astype(float)
    y = loc.str[1].astype(float)
    return x, y


def _dist_to_goal(x: pd.Series, y: pd.Series) -> pd.Series:
    return np.sqrt((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2)


def is_progressive(start_loc: pd.Series, end_loc: pd.Series, min_advance: float = 0.0) -> pd.Series:
    """Acción que acerca el balón a portería rival al menos un 25 %."""
    x0, y0 = _xy(start_loc)
    x1, y1 = _xy(end_loc)
    before = _dist_to_goal(x0, y0)
    after = _dist_to_goal(x1, y1)
    moved = np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    return (after <= 0.75 * before) & (moved >= min_advance)


def team_possession_share(events: pd.DataFrame) -> pd.Series:
    """Cuota de posesión por equipo (pases propios / pases totales en sus partidos)."""
    passes = events[events["type"] == "Pass"]
    per_match = passes.groupby(["match_id", "team"]).size().rename("passes").reset_index()
    totals = per_match.groupby("match_id")["passes"].sum().rename("total")
    per_match = per_match.merge(totals, on="match_id")
    agg = per_match.groupby("team")[["passes", "total"]].sum()
    return agg["passes"] / agg["total"]


def player_metrics(
    events: pd.DataFrame,
    minutes: pd.DataFrame,
    min_minutes: float = 0.0,
) -> pd.DataFrame:
    """Tabla por jugador: totales, minutos y métricas per-90."""
    ev = events[events["period"] <= 4].copy()
    ev = ev[ev["player"].notna()]

    def col(name: str) -> pd.Series:
        if name in ev.columns:
            return ev[name]
        return pd.Series(np.nan, index=ev.index)

    is_pass = ev["type"] == "Pass"
    is_shot = ev["type"] == "Shot"
    is_carry = ev["type"] == "Carry"
    pass_completed = is_pass & col("pass_outcome").isna()
    open_play_pass = is_pass & ~col("pass_type").isin(SET_PIECE_PASS_TYPES)
    non_penalty = col("shot_type") != "Penalty"

    # xA real: a cada pase clave se le asigna el xG del tiro que generó
    shots = ev[is_shot]
    if "shot_key_pass_id" in shots.columns:
        xa_map = (
            shots.dropna(subset=["shot_key_pass_id"])
            .groupby("shot_key_pass_id")["shot_statsbomb_xg"]
            .sum()
        )
        ev["xa"] = ev["id"].map(xa_map).fillna(0.0)
    else:
        ev["xa"] = 0.0

    flags = pd.DataFrame(index=ev.index)
    flags["npg"] = is_shot & (col("shot_outcome") == "Goal") & non_penalty
    flags["shots"] = is_shot & non_penalty
    flags["assists"] = col("pass_goal_assist").eq(True)
    flags["key_passes"] = col("pass_shot_assist").eq(True) | col("pass_goal_assist").eq(True)
    flags["passes_att"] = is_pass
    flags["passes_cmp"] = pass_completed

    prog_pass = pd.Series(False, index=ev.index)
    mask = pass_completed & open_play_pass & col("pass_end_location").notna() & ev["location"].notna()
    if mask.any():
        prog_pass.loc[mask] = is_progressive(ev.loc[mask, "location"], ev.loc[mask, "pass_end_location"])
    flags["prog_passes"] = prog_pass

    prog_carry = pd.Series(False, index=ev.index)
    mask = is_carry & col("carry_end_location").notna() & ev["location"].notna()
    if mask.any():
        prog_carry.loc[mask] = is_progressive(
            ev.loc[mask, "location"], ev.loc[mask, "carry_end_location"], min_advance=5.0
        )
    flags["prog_carries"] = prog_carry

    flags["dribbles_cmp"] = col("dribble_outcome") == "Complete"
    flags["dribbles_att"] = ev["type"] == "Dribble"

    x, y = _xy(ev["location"].where(ev["location"].notna()))
    in_box = (x >= BOX_X) & (y >= BOX_Y_MIN) & (y <= BOX_Y_MAX)
    touch_types = ["Pass", "Shot", "Carry", "Dribble", "Ball Receipt*"]
    flags["touches_box"] = in_box.fillna(False) & ev["type"].isin(touch_types)

    flags["pressures"] = ev["type"] == "Pressure"
    flags["tackles"] = col("duel_type") == "Tackle"
    flags["interceptions"] = ev["type"] == "Interception"
    flags["recoveries"] = (ev["type"] == "Ball Recovery") & col(
        "ball_recovery_recovery_failure"
    ).ne(True)
    flags["blocks"] = ev["type"] == "Block"
    flags["clearances"] = ev["type"] == "Clearance"

    ev = pd.concat([ev, flags.astype(float)], axis=1)
    ev["npxg"] = np.where(is_shot & non_penalty, col("shot_statsbomb_xg").fillna(0.0), 0.0)

    sums = ev.groupby("player")[
        list(flags.columns) + ["npxg", "xa"]
    ].sum()

    primary_pos = (
        ev.dropna(subset=["position"])
        .groupby("player")["position"]
        .agg(lambda s: s.mode().iloc[0])
    )

    out = minutes.merge(sums, left_on="player", right_index=True, how="left")
    out = out.merge(primary_pos.rename("primary_position"), left_on="player", right_index=True, how="left")
    out["primary_position"] = out["primary_position"].fillna(out["lineup_position"])
    out["position_group"] = out["primary_position"].map(position_group)

    metric_cols = [c for c in out.columns if c in set(COUNT_METRICS) | {"passes_att", "dribbles_att"}]
    out[metric_cols] = out[metric_cols].fillna(0.0)

    # PAdj: acciones defensivas ajustadas por la posesión del equipo.
    # Un equipo con 65 % de posesión tiene ~la mitad de oportunidades de
    # defender que uno con 35 %; factor = 0.5 / (1 - posesión propia).
    poss = team_possession_share(events)
    factor = (0.5 / (1 - out["team"].map(poss))).clip(upper=3.0)
    out["padj_tack_int"] = (out["tackles"] + out["interceptions"]) * factor

    out["pass_pct"] = np.where(
        out["passes_att"] > 0, 100 * out["passes_cmp"] / out["passes_att"], np.nan
    )
    out["npxg_per_shot"] = np.where(out["shots"] > 0, out["npxg"] / out["shots"], np.nan)

    for m in COUNT_METRICS:
        out[f"{m}_p90"] = np.where(out["minutes"] > 0, out[m] / out["minutes"] * 90, 0.0)

    out = out[out["minutes"] >= min_minutes].reset_index(drop=True)
    return out


def percentiles(
    metrics_df: pd.DataFrame,
    metric_cols: list[str],
    group_col: str = "position_group",
) -> pd.DataFrame:
    """Percentil (0-100) de cada métrica dentro del grupo posicional."""
    pct = metrics_df.groupby(group_col)[metric_cols].rank(pct=True) * 100
    pct.columns = [f"{c}_pct" for c in pct.columns]
    return pd.concat([metrics_df, pct], axis=1)
