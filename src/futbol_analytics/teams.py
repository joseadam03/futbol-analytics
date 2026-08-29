"""Métricas de estilo y rendimiento por equipo.

Como en el resto del proyecto, se excluyen las tandas de penaltis
(periodo 5). Las coordenadas de StatsBomb son siempre desde la
perspectiva atacante del equipo del evento (portería rival en x=120).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# PPDA: pases que se permiten al rival en su zona de construcción (su 60 %
# inicial, x <= 72 en sus coordenadas) por cada acción defensiva propia en
# zona alta (x >= 48 en las nuestras, la zona equivalente del campo).
BUILDUP_X_MAX = 72.0
HIGH_PRESS_X_MIN = 48.0

DEFENSIVE_ACTION_TYPES = {"Interception", "Foul Committed"}


def team_match_stats(events: pd.DataFrame) -> pd.DataFrame:
    """Totales por (partido, equipo) que alimentan las métricas de equipo."""
    ev = events[(events["period"] <= 4) & events["team"].notna()].copy()

    def col(name: str) -> pd.Series:
        if name in ev.columns:
            return ev[name]
        return pd.Series(np.nan, index=ev.index)

    x = pd.Series(np.nan, index=ev.index)
    has_loc = ev["location"].notna()
    x.loc[has_loc] = ev.loc[has_loc, "location"].str[0].astype(float)

    is_pass = ev["type"] == "Pass"
    is_shot = ev["type"] == "Shot"
    non_penalty = col("shot_type") != "Penalty"
    is_def_action = ev["type"].isin(DEFENSIVE_ACTION_TYPES) | (col("duel_type") == "Tackle")

    flags = pd.DataFrame(
        {
            "passes": is_pass,
            "buildup_passes": is_pass & (x <= BUILDUP_X_MAX),
            "def_actions_high": is_def_action & (x >= HIGH_PRESS_X_MIN),
            "pressures": ev["type"] == "Pressure",
            "goals": is_shot & (col("shot_outcome") == "Goal"),
            "shots": is_shot & non_penalty,
        },
        index=ev.index,
    ).astype(float)
    flags["npxg"] = np.where(is_shot & non_penalty, col("shot_statsbomb_xg").fillna(0.0), 0.0)

    flags["match_id"] = ev["match_id"]
    flags["team"] = ev["team"]
    return flags.groupby(["match_id", "team"], as_index=False).sum()


def team_metrics(events: pd.DataFrame) -> pd.DataFrame:
    """Tabla por equipo: posesión, npxG a favor/en contra, PPDA, presión."""
    per_match = team_match_stats(events)

    merged = per_match.merge(per_match, on="match_id", suffixes=("", "_opp"))
    merged = merged[merged["team"] != merged["team_opp"]]

    agg = merged.groupby("team").agg(
        matches=("match_id", "nunique"),
        passes=("passes", "sum"),
        passes_opp=("passes_opp", "sum"),
        buildup_passes_opp=("buildup_passes_opp", "sum"),
        def_actions_high=("def_actions_high", "sum"),
        pressures=("pressures", "sum"),
        goals_for=("goals", "sum"),
        goals_against=("goals_opp", "sum"),
        shots=("shots", "sum"),
        npxg_for=("npxg", "sum"),
        npxg_against=("npxg_opp", "sum"),
    )

    out = pd.DataFrame(index=agg.index)
    out["matches"] = agg["matches"]
    out["possession"] = 100 * agg["passes"] / (agg["passes"] + agg["passes_opp"])
    out["npxg_for_pm"] = agg["npxg_for"] / agg["matches"]
    out["npxg_against_pm"] = agg["npxg_against"] / agg["matches"]
    out["npxg_diff_pm"] = out["npxg_for_pm"] - out["npxg_against_pm"]
    out["goals_for"] = agg["goals_for"]
    out["goals_against"] = agg["goals_against"]
    out["ppda"] = np.where(
        agg["def_actions_high"] > 0, agg["buildup_passes_opp"] / agg["def_actions_high"], np.nan
    )
    out["pressures_pm"] = agg["pressures"] / agg["matches"]
    out["shots_pm"] = agg["shots"] / agg["matches"]
    return out.reset_index().sort_values("npxg_diff_pm", ascending=False).reset_index(drop=True)
