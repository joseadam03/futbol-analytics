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
    # a numérico explícito: si ningún tiro trae xG la columna llega como objeto
    # y los acumulados posteriores (cumsum, medias) fallarían
    xg_vals = pd.to_numeric(col("shot_statsbomb_xg"), errors="coerce").fillna(0.0)
    flags["npxg"] = np.where(is_shot & non_penalty, xg_vals, 0.0).astype(float)

    flags["match_id"] = ev["match_id"]
    flags["team"] = ev["team"]
    return flags.groupby(["match_id", "team"], as_index=False).sum()


def match_summary(events: pd.DataFrame, match_id: int) -> pd.DataFrame:
    """Local vs. visitante de un partido concreto: posesión, goles, tiros, npxG, presiones.

    Mismo cruce local-rival que `team_metrics`, pero acotado a un `match_id`
    para poder enfrentar exactamente las dos filas de ese partido.
    """
    per_match = team_match_stats(events[events["match_id"] == match_id])
    merged = per_match.merge(per_match, on="match_id", suffixes=("", "_opp"))
    merged = merged[merged["team"] != merged["team_opp"]]

    out = pd.DataFrame(index=merged.index)
    out["team"] = merged["team"]
    out["rival"] = merged["team_opp"]
    out["possession"] = 100 * merged["passes"] / (merged["passes"] + merged["passes_opp"])
    out["goals"] = merged["goals"]
    out["goals_against"] = merged["goals_opp"]
    out["shots"] = merged["shots"]
    out["npxg"] = merged["npxg"]
    out["npxg_against"] = merged["npxg_opp"]
    out["pressures"] = merged["pressures"]
    return out.reset_index(drop=True)


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


# Estilo de juego: tres familias (ritmo, presión, progresión) con las que se
# describe cómo juega un equipo, no solo cuánto rinde.
STYLE_METRICS = {
    "pass_length": "Longitud media de pase",
    "long_pass_share": "% de pases largos",
    "passes_per_possession": "Pases por posesión",
    "ppda": "PPDA",
    "pressures_pm": "Presiones/partido",
    "recovery_height": "Altura de recuperación",
    "prog_pass_share": "% de pases progresivos",
    "prog_carries_pm": "Conducciones prog./partido",
    "final_third_pm": "Entradas al último tercio/partido",
    "field_tilt": "Field tilt (% de toques rivales en su último tercio)",
}
# Métricas donde "más" no significa "más de ese estilo" (PPDA bajo = más presión)
STYLE_INVERTED = {"ppda"}

LONG_PASS_MIN = 30.0  # unidades StatsBomb (~27 m)
FINAL_THIRD_X = 80.0
TOUCH_TYPES = ("Pass", "Shot", "Carry", "Dribble", "Ball Receipt*")


def team_style_metrics(events: pd.DataFrame) -> pd.DataFrame:
    """Estilo de juego por equipo: ritmo, presión y progresión.

    - **Ritmo**: longitud media de pase, cuota de pases largos y pases por
      secuencia de posesión (más pases por posesión = juego más elaborado).
    - **Presión**: PPDA y presiones por partido (ya en `team_metrics`), más la
      altura media de las acciones defensivas: dónde recupera el equipo.
    - **Progresión**: cuota de pases progresivos, conducciones progresivas por
      partido, entradas al último tercio y *field tilt* (qué parte de los
      toques en zona de peligro son propios, señal de dominio territorial).
    """
    from .metrics import SET_PIECE_PASS_TYPES, is_progressive

    ev = events[(events["period"] <= 4) & events["team"].notna()].copy()
    base = team_metrics(events).set_index("team")

    def col(name: str) -> pd.Series:
        return ev[name] if name in ev.columns else pd.Series(np.nan, index=ev.index)

    x = pd.Series(np.nan, index=ev.index)
    con_loc = ev["location"].notna()
    x.loc[con_loc] = ev.loc[con_loc, "location"].str[0].astype(float)

    # --- ritmo -------------------------------------------------------------
    passes = ev[(ev["type"] == "Pass") & con_loc & col("pass_end_location").notna()]
    if "pass_outcome" in passes.columns:
        completos = passes[passes["pass_outcome"].isna()]
    else:
        completos = passes
    if "pass_type" in completos.columns:
        en_juego = completos[~completos["pass_type"].isin(SET_PIECE_PASS_TYPES)]
    else:
        en_juego = completos

    inicio_x = en_juego["location"].str[0].astype(float)
    inicio_y = en_juego["location"].str[1].astype(float)
    fin_x = en_juego["pass_end_location"].str[0].astype(float)
    fin_y = en_juego["pass_end_location"].str[1].astype(float)
    largo = np.sqrt((fin_x - inicio_x) ** 2 + (fin_y - inicio_y) ** 2)
    aux = pd.DataFrame({"team": en_juego["team"], "largo": largo})

    out = pd.DataFrame(index=base.index)
    out["pass_length"] = aux.groupby("team")["largo"].mean().reindex(base.index)
    out["long_pass_share"] = (
        100 * aux.assign(largo_p=aux["largo"] >= LONG_PASS_MIN).groupby("team")["largo_p"].mean()
    ).reindex(base.index)

    if "possession" in ev.columns:
        por_posesion = ev[ev["type"] == "Pass"].groupby(["team", "possession"]).size().groupby("team").mean()
        out["passes_per_possession"] = por_posesion.reindex(base.index)
    else:
        out["passes_per_possession"] = np.nan

    # --- presión -----------------------------------------------------------
    acciones_def = ev["type"].isin(DEFENSIVE_ACTION_TYPES) | (col("duel_type") == "Tackle")
    acciones_def |= ev["type"].isin(["Pressure", "Ball Recovery"])
    alturas = pd.DataFrame({"team": ev["team"], "x": x})[acciones_def & con_loc]
    out["recovery_height"] = alturas.groupby("team")["x"].mean().reindex(base.index)
    out["ppda"] = base["ppda"]
    out["pressures_pm"] = base["pressures_pm"]

    # --- progresión --------------------------------------------------------
    prog = is_progressive(en_juego["location"], en_juego["pass_end_location"])
    out["prog_pass_share"] = (
        100 * pd.DataFrame({"team": en_juego["team"], "p": prog}).groupby("team")["p"].mean()
    ).reindex(base.index)

    carries = ev[(ev["type"] == "Carry") & con_loc & col("carry_end_location").notna()]
    if not carries.empty:
        prog_c = is_progressive(carries["location"], carries["carry_end_location"], min_advance=5.0)
        conteo = pd.DataFrame({"team": carries["team"], "p": prog_c}).groupby("team")["p"].sum()
        # un equipo sin conducciones hizo cero, no "dato ausente"
        conteo = conteo.reindex(base.index, fill_value=0.0)
        out["prog_carries_pm"] = conteo / base["matches"]
    else:
        out["prog_carries_pm"] = 0.0

    # entradas al último tercio: pases y conducciones que cruzan x=80
    entradas = pd.Series(0.0, index=base.index)
    if not en_juego.empty:
        cruza = (inicio_x < FINAL_THIRD_X) & (fin_x >= FINAL_THIRD_X)
        entradas = entradas.add(
            pd.DataFrame({"team": en_juego["team"], "c": cruza}).groupby("team")["c"].sum(),
            fill_value=0.0,
        )
    if not carries.empty:
        ci = carries["location"].str[0].astype(float)
        cf = carries["carry_end_location"].str[0].astype(float)
        cruza_c = (ci < FINAL_THIRD_X) & (cf >= FINAL_THIRD_X)
        entradas = entradas.add(
            pd.DataFrame({"team": carries["team"], "c": cruza_c}).groupby("team")["c"].sum(),
            fill_value=0.0,
        )
    out["final_third_pm"] = (entradas / base["matches"]).reindex(base.index)

    # field tilt: cuota de toques en último tercio propios frente al rival
    toques = pd.DataFrame({"match_id": ev["match_id"], "team": ev["team"], "x": x})[
        ev["type"].isin(TOUCH_TYPES) & con_loc
    ]
    tercio = toques[toques["x"] >= FINAL_THIRD_X]
    if tercio.empty:
        out["field_tilt"] = np.nan
    else:
        por_partido = tercio.groupby(["match_id", "team"]).size().rename("toques").reset_index()
        total = por_partido.groupby("match_id")["toques"].sum().rename("total")
        por_partido = por_partido.merge(total, on="match_id")
        sumas = por_partido.groupby("team")[["toques", "total"]].sum()
        tilt = 100 * sumas["toques"] / sumas["total"].replace(0, np.nan)
        out["field_tilt"] = tilt.reindex(base.index)

    return out.reset_index()


def team_style_percentiles(style: pd.DataFrame) -> pd.DataFrame:
    """Percentil de cada métrica de estilo dentro de la competición.

    Las métricas invertidas (PPDA) se voltean para que un percentil alto
    signifique siempre "más de ese rasgo".
    """
    out = style.copy()
    for col in STYLE_METRICS:
        if col not in out.columns:
            continue
        serie = -out[col] if col in STYLE_INVERTED else out[col]
        out[f"{col}_pct"] = serie.rank(pct=True) * 100
    return out
