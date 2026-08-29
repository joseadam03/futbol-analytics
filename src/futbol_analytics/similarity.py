"""Jugadores similares: similitud de coseno sobre perfiles per-90 estandarizados."""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_FEATURES = [
    "npxg_p90", "shots_p90", "xa_p90", "key_passes_p90",
    "prog_passes_p90", "prog_carries_p90", "dribbles_cmp_p90",
    "touches_box_p90", "pass_pct",
    "pressures_p90", "padj_tack_int_p90", "recoveries_p90",
    "blocks_p90", "clearances_p90",
]


def similar_players(
    metrics_df: pd.DataFrame,
    player: str,
    n: int = 10,
    features: list[str] | None = None,
    same_group: bool = True,
) -> pd.DataFrame:
    """Top-n jugadores con el perfil estadístico más parecido al indicado.

    Estandariza cada métrica (z-score) dentro del grupo posicional y compara
    con similitud de coseno, de modo que importa la *forma* del perfil y no
    el volumen absoluto.
    """
    features = features or DEFAULT_FEATURES
    features = [f for f in features if f in metrics_df.columns]

    target = metrics_df[metrics_df["player"] == player]
    if target.empty:
        raise ValueError(f"Jugador no encontrado: {player}")
    target = target.iloc[0]

    pool = metrics_df
    if same_group:
        pool = pool[pool["position_group"] == target["position_group"]]
    pool = pool.reset_index(drop=True)

    X = pool[features].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0)
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std == 0] = 1.0
    Z = (X - mean) / std

    idx = pool.index[pool["player"] == player][0]
    v = Z[idx]
    norms = np.linalg.norm(Z, axis=1) * np.linalg.norm(v)
    norms[norms == 0] = 1.0
    sims = Z @ v / norms

    pool = pool.assign(similarity=np.round(sims, 3))
    pool = pool[pool["player"] != player]
    cols = ["player", "team", "primary_position", "minutes", "similarity"]
    return pool.sort_values("similarity", ascending=False).head(n)[cols].reset_index(drop=True)
