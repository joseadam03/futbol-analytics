"""Modelo de xG propio: regresión logística sobre distancia, ángulo y cabeza.

No pretende batir al xG de StatsBomb — que ve presión, posición del
portero, altura del balón y mucho más —: el objetivo es tener un modelo
**transparente**, entrenado sobre la propia competición con validación
cruzada, y contrastar su calibración con la del proveedor. Es el
ejercicio clásico de "¿sabes lo que mide tu métrica?".

Reglas de la casa: fuera penaltis y tandas (periodo 5), como en el resto
del proyecto. Las predicciones mostradas son *out-of-fold* (cada tiro se
predice con un modelo que no lo vio), para que la calibración sea real y
no un ajuste sobre los mismos datos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

GOAL_X, GOAL_Y = 120.0, 40.0
POST_Y_LOW, POST_Y_HIGH = 36.0, 44.0

FEATURES = ["dist", "angle", "header"]
FEATURE_LABELS = {"dist": "Distancia a portería", "angle": "Ángulo de tiro", "header": "Remate de cabeza"}


def shot_table(events: pd.DataFrame) -> pd.DataFrame:
    """Un tiro por fila con sus rasgos, el resultado y el xG del proveedor."""
    ev = events[(events["period"] <= 4) & (events["type"] == "Shot")].copy()
    if "shot_type" in ev.columns:
        ev = ev[ev["shot_type"] != "Penalty"]
    ev = ev[ev["location"].notna()]

    x = ev["location"].str[0].astype(float)
    y = ev["location"].str[1].astype(float)
    dist = np.sqrt((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2)

    # ángulo que subtiende la portería desde el punto de tiro
    ux, uy = GOAL_X - x, POST_Y_LOW - y
    vx, vy = GOAL_X - x, POST_Y_HIGH - y
    dot = ux * vx + uy * vy
    normas = np.sqrt(ux**2 + uy**2) * np.sqrt(vx**2 + vy**2)
    angle = np.arccos(np.clip(dot / np.where(normas > 0, normas, 1.0), -1.0, 1.0))

    if "shot_body_part" in ev.columns:
        header = (ev["shot_body_part"] == "Head").astype(int)
    else:
        header = pd.Series(0, index=ev.index)

    return pd.DataFrame(
        {
            "player": ev.get("player"),
            "team": ev.get("team"),
            "dist": dist,
            "angle": angle,
            "header": header,
            "goal": (ev["shot_outcome"] == "Goal").astype(int),
            "sb_xg": ev.get("shot_statsbomb_xg", pd.Series(np.nan, index=ev.index)).astype(float),
        }
    ).reset_index(drop=True)


def train_xg(events: pd.DataFrame, cv: int = 5, random_state: int = 7):
    """Entrena el modelo y devuelve (coeficientes, tiros con xg_own out-of-fold).

    Con menos de 50 tiros o una sola clase no hay validación cruzada digna:
    se predice in-sample y se marca en el resumen (in_sample=True).
    """
    shots = shot_table(events)
    X = shots[FEATURES].to_numpy(dtype=float)
    y = shots["goal"].to_numpy(dtype=int)

    model = LogisticRegression(max_iter=1000)
    n_min_clase = int(min(y.sum(), len(y) - y.sum())) if len(y) else 0
    in_sample = len(shots) < 50 or n_min_clase < 2

    if in_sample:
        if len(shots) and n_min_clase >= 1:
            model.fit(X, y)
            shots["xg_own"] = model.predict_proba(X)[:, 1]
        else:
            shots["xg_own"] = float(y.mean()) if len(y) else np.nan
    else:
        splits = int(min(cv, n_min_clase))
        skf = StratifiedKFold(n_splits=splits, shuffle=True, random_state=random_state)
        shots["xg_own"] = cross_val_predict(model, X, y, cv=skf, method="predict_proba")[:, 1]
        model.fit(X, y)

    coef = dict(zip(FEATURES, model.coef_[0])) if hasattr(model, "coef_") else {}
    resumen = {
        "n_shots": int(len(shots)),
        "n_goals": int(y.sum()) if len(y) else 0,
        "coef": coef,
        "intercept": float(model.intercept_[0]) if hasattr(model, "intercept_") else np.nan,
        "in_sample": in_sample,
        "brier_own": brier(shots["xg_own"], shots["goal"]),
        "brier_sb": brier(shots["sb_xg"], shots["goal"]),
        "brier_base": brier(pd.Series(y.mean(), index=shots.index), shots["goal"]) if len(y) else np.nan,
    }
    return resumen, shots


def brier(p: pd.Series, y: pd.Series) -> float:
    """Error cuadrático medio de la probabilidad (más bajo = mejor calibrado)."""
    mask = p.notna() & y.notna()
    if not mask.any():
        return float("nan")
    return float(((p[mask] - y[mask]) ** 2).mean())


def calibration_bins(p: pd.Series, y: pd.Series, bins: int = 8) -> pd.DataFrame:
    """Curva de fiabilidad: xG medio predicho vs frecuencia real de gol por tramo."""
    mask = p.notna() & y.notna()
    df = pd.DataFrame({"p": p[mask], "y": y[mask]})
    if df.empty:
        return pd.DataFrame(columns=["pred", "obs", "n"])
    df["tramo"] = pd.qcut(df["p"], q=min(bins, df["p"].nunique()), duplicates="drop")
    out = df.groupby("tramo", observed=True).agg(pred=("p", "mean"), obs=("y", "mean"), n=("y", "size"))
    return out.reset_index(drop=True)
