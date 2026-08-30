"""Series temporales: cómo evoluciona el rendimiento partido a partido.

Una tabla de temporada esconde la historia: un equipo con +0,3 de npxG por
partido puede haber sumado todo en septiembre y hundirse después. Este
módulo desagrega las métricas por partido, las ordena por fecha (o por el
orden de los partidos si el proveedor no da fechas) y añade una **media
móvil**, que es como se lee de verdad una racha: el dato de un partido es
ruido; la tendencia de cinco, información.

Se apoya en `teams.team_match_stats` para no duplicar definiciones: lo que
cambia aquí es el eje, no la métrica.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .teams import team_match_stats

ROLLING_WINDOW = 5

TEAM_SERIES_METRICS = {
    "npxg_for": "npxG a favor",
    "npxg_against": "npxG en contra",
    "npxg_diff": "npxG diferencia",
    "possession": "Posesión %",
    "shots": "Tiros",
    "goals_for": "Goles a favor",
    "goals_against": "Goles en contra",
}
PLAYER_SERIES_METRICS = {
    "npxg": "npxG",
    "xa": "xA",
    "shots": "Tiros",
    "key_passes": "Pases clave",
    "prog_passes": "Pases progresivos",
    "pressures": "Presiones",
}


def _match_order(matches: pd.DataFrame | None, match_ids) -> pd.DataFrame:
    """Orden y etiqueta de cada partido: por fecha si la hay, si no por id."""
    ids = pd.Index(pd.unique(pd.Series(list(match_ids)))).dropna()
    orden = pd.DataFrame({"match_id": ids})

    if matches is not None and not matches.empty and "match_id" in matches.columns:
        cols = ["match_id"]
        for extra in ("match_date", "match_week", "home_team", "away_team"):
            if extra in matches.columns:
                cols.append(extra)
        orden = orden.merge(matches[cols].drop_duplicates("match_id"), on="match_id", how="left")

    if "match_date" in orden.columns:
        orden["fecha"] = pd.to_datetime(orden["match_date"], errors="coerce")
        orden = orden.sort_values(["fecha", "match_id"])
    else:
        orden["fecha"] = pd.NaT
        orden = orden.sort_values("match_id")

    orden = orden.reset_index(drop=True)
    orden["jornada"] = (
        orden["match_week"].astype("Int64")
        if "match_week" in orden.columns and orden["match_week"].notna().any()
        else pd.Series(range(1, len(orden) + 1), dtype="Int64")
    )
    orden["orden"] = range(1, len(orden) + 1)
    return orden


def team_series(
    events: pd.DataFrame,
    matches: pd.DataFrame | None = None,
    window: int = ROLLING_WINDOW,
) -> pd.DataFrame:
    """Métricas por (equipo, partido) en orden temporal, con media móvil.

    Cada fila lleva la métrica del partido y su versión suavizada
    (`<métrica>_roll`), además de los acumulados de npxG, para ver de un
    vistazo si un equipo va de más a menos.
    """
    per_match = team_match_stats(events)
    if per_match.empty:
        return pd.DataFrame()

    rival = per_match.merge(per_match, on="match_id", suffixes=("", "_opp"))
    rival = rival[rival["team"] != rival["team_opp"]]

    df = pd.DataFrame(
        {
            "match_id": rival["match_id"],
            "team": rival["team"],
            "opponent": rival["team_opp"],
            "npxg_for": rival["npxg"],
            "npxg_against": rival["npxg_opp"],
            "goals_for": rival["goals"],
            "goals_against": rival["goals_opp"],
            "shots": rival["shots"],
        }
    )
    df["npxg_diff"] = df["npxg_for"] - df["npxg_against"]
    total_pases = rival["passes"] + rival["passes_opp"]
    df["possession"] = 100 * rival["passes"] / total_pases.replace(0, np.nan)

    orden = _match_order(matches, df["match_id"])
    df = df.merge(orden[["match_id", "fecha", "jornada", "orden"]], on="match_id", how="left")
    df = df.sort_values(["team", "orden"]).reset_index(drop=True)

    for metrica in TEAM_SERIES_METRICS:
        if metrica in df.columns:
            df[f"{metrica}_roll"] = df.groupby("team")[metrica].transform(
                lambda s: s.rolling(window, min_periods=1).mean()
            )
    df["npxg_for_cum"] = df.groupby("team")["npxg_for"].cumsum()
    df["npxg_against_cum"] = df.groupby("team")["npxg_against"].cumsum()
    df["partido"] = df.groupby("team").cumcount() + 1
    return df


def player_series(
    events: pd.DataFrame,
    player: str,
    matches: pd.DataFrame | None = None,
    window: int = ROLLING_WINDOW,
) -> pd.DataFrame:
    """Producción por partido de un jugador, en orden temporal y suavizada."""
    ev = events[(events["period"] <= 4) & (events["player"] == player)].copy()
    if ev.empty:
        return pd.DataFrame()

    def col(nombre: str, defecto=np.nan) -> pd.Series:
        return ev[nombre] if nombre in ev.columns else pd.Series(defecto, index=ev.index)

    es_tiro = ev["type"] == "Shot"
    sin_penalti = col("shot_type", None) != "Penalty"

    ev["_shots"] = (es_tiro & sin_penalti).astype(float)
    xg_vals = pd.to_numeric(col("shot_statsbomb_xg"), errors="coerce").fillna(0.0)
    ev["_npxg"] = np.where(es_tiro & sin_penalti, xg_vals, 0.0).astype(float)
    ev["_key_passes"] = (
        col("pass_shot_assist", None).eq(True) | col("pass_goal_assist", None).eq(True)
    ).astype(float)
    ev["_pressures"] = (ev["type"] == "Pressure").astype(float)

    # xA real: el pase clave hereda el xG del tiro que generó
    if "shot_key_pass_id" in events.columns and "id" in events.columns:
        tiros = events[events["type"] == "Shot"].dropna(subset=["shot_key_pass_id"])
        mapa = tiros.groupby("shot_key_pass_id")["shot_statsbomb_xg"].sum()
        mapa = pd.to_numeric(mapa, errors="coerce").fillna(0.0)
        ev["_xa"] = ev["id"].map(mapa).fillna(0.0) if "id" in ev.columns else 0.0
    else:
        ev["_xa"] = 0.0

    prog = pd.Series(0.0, index=ev.index)
    if "pass_end_location" in ev.columns:
        from .metrics import is_progressive

        mask = (
            (ev["type"] == "Pass")
            & col("pass_outcome", None).isna()
            & ev["location"].notna()
            & ev["pass_end_location"].notna()
        )
        if mask.any():
            prog.loc[mask] = is_progressive(
                ev.loc[mask, "location"], ev.loc[mask, "pass_end_location"]
            ).astype(float)
    ev["_prog_passes"] = prog

    agg = ev.groupby("match_id").agg(
        npxg=("_npxg", "sum"),
        xa=("_xa", "sum"),
        shots=("_shots", "sum"),
        key_passes=("_key_passes", "sum"),
        prog_passes=("_prog_passes", "sum"),
        pressures=("_pressures", "sum"),
    )
    df = agg.reset_index()

    orden = _match_order(matches, df["match_id"])
    df = df.merge(orden[["match_id", "fecha", "jornada", "orden"]], on="match_id", how="left")
    df = df.sort_values("orden").reset_index(drop=True)

    for metrica in PLAYER_SERIES_METRICS:
        if metrica in df.columns:
            df[f"{metrica}_roll"] = df[metrica].rolling(window, min_periods=1).mean()
    df["npxg_cum"] = df["npxg"].cumsum()
    df["partido"] = range(1, len(df) + 1)
    return df
