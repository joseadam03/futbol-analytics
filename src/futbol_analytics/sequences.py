"""Secuencias de posesión: de dónde nacen las ocasiones de cada equipo.

Una posesión es una secuencia continua de acciones de un equipo. StatsBomb
las numera (`possession`) y etiqueta cómo empezaron (`play_pattern`:
juego regular, córner, falta, saque de banda, contragolpe...). Cruzando
ambas cosas con los tiros se responde a la pregunta que hace un analista
antes que ninguna otra: **¿este equipo crea desde el juego elaborado, del
balón parado, o robando arriba?**

Para cada posesión que termina en tiro se mide:

- **patrón de origen** — cómo empezó la secuencia,
- **zona de inicio** — la x del primer evento del equipo en la posesión;
  arrancar en el último tercio es un robo alto, no una construcción,
- **pases previos** — cuántos pases propios preceden al primer tiro
  (una secuencia larga es elaboración; cero o uno, transición),
- **duración** y **velocidad directa** — cuánto avanza el balón hacia la
  portería rival por segundo, la medida clásica de verticalidad.

Como en el resto del proyecto se excluyen las tandas de penaltis y los
penaltis de las métricas de tiro.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

GOAL_X = 120.0
FINAL_THIRD_X = 80.0
HIGH_START_X = 60.0  # a partir de campo contrario, el arranque es "robo alto"
DIRECT_PATTERNS = {"From Counter", "From Keeper", "From Goal Kick"}
SET_PIECE_PATTERNS = {"From Corner", "From Free Kick", "From Throw In"}

PATTERN_LABELS = {
    "Regular Play": "Juego regular",
    "From Counter": "Contragolpe",
    "From Corner": "Córner",
    "From Free Kick": "Falta",
    "From Throw In": "Saque de banda",
    "From Goal Kick": "Saque de puerta",
    "From Keeper": "Salida del portero",
    "From Kick Off": "Saque de centro",
    "Other": "Otros",
}


def shot_sequences(events: pd.DataFrame) -> pd.DataFrame:
    """Una fila por posesión que acaba en tiro, con su origen y su forma."""
    columnas = [
        "match_id",
        "possession",
        "team",
        "pattern",
        "start_x",
        "high_start",
        "passes_before",
        "duration",
        "progression",
        "direct_speed",
        "shots",
        "npxg",
        "goals",
    ]
    if "possession" not in events.columns:
        return pd.DataFrame(columns=columnas)

    ev = events[(events["period"] <= 4) & events["team"].notna() & events["possession"].notna()].copy()
    if ev.empty:
        return pd.DataFrame(columns=columnas)

    def col(nombre: str, defecto=np.nan) -> pd.Series:
        return ev[nombre] if nombre in ev.columns else pd.Series(defecto, index=ev.index)

    ev["_x"] = np.nan
    con_loc = ev["location"].notna()
    ev.loc[con_loc, "_x"] = ev.loc[con_loc, "location"].str[0].astype(float)

    es_tiro = ev["type"] == "Shot"
    sin_penalti = col("shot_type", None) != "Penalty"
    ev["_shot"] = (es_tiro & sin_penalti).astype(float)
    ev["_goal"] = (es_tiro & sin_penalti & (col("shot_outcome", None) == "Goal")).astype(float)
    xg_vals = pd.to_numeric(col("shot_statsbomb_xg"), errors="coerce").fillna(0.0)
    ev["_npxg"] = np.where(es_tiro & sin_penalti, xg_vals, 0.0).astype(float)
    ev["_pass"] = (ev["type"] == "Pass").astype(float)

    # el momento de cada evento en segundos, para duración y velocidad
    minuto = col("minute", 0).fillna(0).astype(float)
    segundo = col("second", 0).fillna(0).astype(float)
    ev["_t"] = 60 * minuto + segundo

    # el equipo dueño de la posesión es el que más eventos tiene en ella
    dueno = (
        ev.groupby(["match_id", "possession", "team"])
        .size()
        .rename("n")
        .reset_index()
        .sort_values("n", ascending=False)
        .drop_duplicates(["match_id", "possession"])
        .set_index(["match_id", "possession"])["team"]
    )

    filas = []
    for (match_id, posesion), sub in ev.groupby(["match_id", "possession"], sort=False):
        equipo = dueno.get((match_id, posesion))
        propios = sub[sub["team"] == equipo]
        if propios.empty or propios["_shot"].sum() == 0:
            continue

        primer_tiro = propios.index[propios["_shot"] > 0][0]
        previos = propios.loc[: primer_tiro - 1] if primer_tiro != propios.index[0] else propios.iloc[:0]

        patron = propios["play_pattern"].iloc[0] if "play_pattern" in propios.columns else "Regular Play"
        xs = propios["_x"].dropna()
        start_x = float(xs.iloc[0]) if len(xs) else np.nan
        tiro_x = float(propios.loc[primer_tiro, "_x"]) if pd.notna(propios.loc[primer_tiro, "_x"]) else np.nan

        tiempos = propios["_t"].dropna()
        duracion = float(tiempos.max() - tiempos.min()) if len(tiempos) else np.nan
        progresion = (start_x - tiro_x) * -1 if not np.isnan(start_x) and not np.isnan(tiro_x) else np.nan
        velocidad = (
            progresion / duracion if duracion and duracion > 0 and not np.isnan(progresion) else np.nan
        )

        filas.append(
            {
                "match_id": match_id,
                "possession": posesion,
                "team": equipo,
                "pattern": patron if isinstance(patron, str) else "Other",
                "start_x": start_x,
                "high_start": float(start_x >= HIGH_START_X) if not np.isnan(start_x) else np.nan,
                "passes_before": float(previos["_pass"].sum()),
                "duration": duracion,
                "progression": progresion,
                "direct_speed": velocidad,
                "shots": float(propios["_shot"].sum()),
                "npxg": float(propios["_npxg"].sum()),
                "goals": float(propios["_goal"].sum()),
            }
        )
    return pd.DataFrame(filas, columns=columnas)


def team_sequence_profile(sequences: pd.DataFrame) -> pd.DataFrame:
    """Perfil por equipo: cuántas ocasiones crea y de qué tipo de secuencia."""
    if sequences.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "sequences",
                "npxg",
                "npxg_per_sequence",
                "passes_before",
                "duration",
                "direct_speed",
                "high_start_share",
                "set_piece_share",
                "direct_share",
                "build_up_share",
            ]
        )

    def cuota(sub: pd.DataFrame, patrones: set[str]) -> float:
        return 100 * sub["pattern"].isin(patrones).mean()

    filas = []
    for equipo, sub in sequences.groupby("team"):
        filas.append(
            {
                "team": equipo,
                "sequences": float(len(sub)),
                "npxg": float(sub["npxg"].sum()),
                "npxg_per_sequence": float(sub["npxg"].mean()),
                "passes_before": float(sub["passes_before"].mean()),
                "duration": float(sub["duration"].mean()),
                "direct_speed": float(sub["direct_speed"].mean()),
                "high_start_share": 100 * float(sub["high_start"].mean()),
                "set_piece_share": cuota(sub, SET_PIECE_PATTERNS),
                "direct_share": cuota(sub, DIRECT_PATTERNS),
                "build_up_share": cuota(sub, {"Regular Play"}),
            }
        )
    return pd.DataFrame(filas).sort_values("npxg", ascending=False).reset_index(drop=True)


def pattern_breakdown(sequences: pd.DataFrame, team: str | None = None) -> pd.DataFrame:
    """npxG y ocasiones por patrón de origen, para un equipo o para todos."""
    sub = sequences if team is None else sequences[sequences["team"] == team]
    if sub.empty:
        return pd.DataFrame(columns=["pattern", "label", "sequences", "npxg", "goals", "npxg_share"])

    agg = sub.groupby("pattern").agg(
        sequences=("possession", "size"), npxg=("npxg", "sum"), goals=("goals", "sum")
    )
    agg["npxg_share"] = 100 * agg["npxg"] / agg["npxg"].sum() if agg["npxg"].sum() else 0.0
    agg = agg.reset_index()
    agg["label"] = agg["pattern"].map(PATTERN_LABELS).fillna(agg["pattern"])
    return agg.sort_values("npxg", ascending=False).reset_index(drop=True)
