"""Modelo de xG propio: de la geometría al contexto del tiro.

Se entrenan y comparan dos modelos sobre la misma competición:

- **base** — solo geometría: distancia, ángulo de portería y remate de
  cabeza. Es el modelo mínimo defendible, el que cualquiera puede
  reproducir con lápiz y papel.
- **contextual** — añade lo que rodea al disparo: presión sobre el
  tirador, defensores dentro del cono de tiro, distancia al defensor más
  cercano, posición del portero (lo lejos que está de su línea y cuánto
  se ha desplazado del eje del disparo), mano a mano, remate de primeras
  y patrón de juego (contragolpe, balón parado...).

La comparación es el ejercicio interesante: cuánto añade el contexto
sobre la pura geometría, medido con el Brier score y la calibración.
Ninguno pretende batir al xG de StatsBomb, que ve más cosas todavía.

Reglas de la casa: fuera penaltis y tandas (periodo 5). Las predicciones
mostradas son *out-of-fold* (cada tiro se predice con un modelo que no lo
vio), para que la calibración sea real y no un ajuste sobre sí misma.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

GOAL_X, GOAL_Y = 120.0, 40.0
POST_Y_LOW, POST_Y_HIGH = 36.0, 44.0

BASE_FEATURES = ["dist", "angle", "header"]
CONTEXT_FEATURES = [
    "under_pressure",
    "defenders_cone",
    "dist_nearest_def",
    "gk_dist_goal",
    "gk_offline",
    "one_on_one",
    "first_time",
    "from_counter",
    "from_set_piece",
]
FEATURE_LABELS = {
    "dist": "Distancia a portería",
    "angle": "Ángulo de tiro",
    "header": "Remate de cabeza",
    "under_pressure": "Bajo presión",
    "defenders_cone": "Defensores en el cono de tiro",
    "dist_nearest_def": "Distancia al defensor más cercano",
    "gk_dist_goal": "Portero adelantado",
    "gk_offline": "Portero descolocado del eje",
    "one_on_one": "Mano a mano",
    "first_time": "Remate de primeras",
    "from_counter": "Contragolpe",
    "from_set_piece": "Posesión nacida de balón parado",
}
SET_PIECE_PATTERNS = {"From Corner", "From Free Kick", "From Throw In"}


def _triangle_sign(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Lado de la recta AB en el que cae cada punto P (signo del producto cruzado)."""
    return (p[:, 0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[:, 1] - b[1])


def _in_shot_cone(puntos: np.ndarray, tirador: np.ndarray) -> np.ndarray:
    """¿Qué puntos caen dentro del triángulo tirador-poste-poste?"""
    if not len(puntos):
        return np.zeros(0, dtype=bool)
    poste_a = np.array([GOAL_X, POST_Y_LOW])
    poste_b = np.array([GOAL_X, POST_Y_HIGH])
    d1 = _triangle_sign(puntos, tirador, poste_a)
    d2 = _triangle_sign(puntos, poste_a, poste_b)
    d3 = _triangle_sign(puntos, poste_b, tirador)
    negativos = (d1 < 0) | (d2 < 0) | (d3 < 0)
    positivos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    return ~(negativos & positivos)


def _freeze_frame_features(frame, tirador: np.ndarray) -> dict:
    """Rasgos del contexto de un tiro a partir de su freeze frame.

    El freeze frame de StatsBomb lista a los jugadores visibles con su
    posición y si son compañeros. De ahí salen los defensores que tapan el
    disparo y dónde estaba el portero.
    """
    vacio = {
        "defenders_cone": np.nan,
        "dist_nearest_def": np.nan,
        "gk_dist_goal": np.nan,
        "gk_offline": np.nan,
    }
    if not isinstance(frame, (list, tuple)) or not len(frame):
        return vacio

    rivales, portero = [], None
    for actor in frame:
        if not isinstance(actor, dict) or actor.get("teammate", True):
            continue
        loc = actor.get("location")
        if not isinstance(loc, (list, tuple)) or len(loc) < 2:
            continue
        punto = [float(loc[0]), float(loc[1])]
        rivales.append(punto)
        if (actor.get("position") or {}).get("name") == "Goalkeeper":
            portero = punto

    if not rivales:
        return vacio

    puntos = np.array(rivales, dtype=float)
    # el portero no cuenta como "defensor que tapa": se mide aparte
    de_campo = puntos
    if portero is not None:
        de_campo = puntos[~np.all(np.isclose(puntos, portero), axis=1)]

    en_cono = int(_in_shot_cone(de_campo, tirador).sum()) if len(de_campo) else 0
    if len(de_campo):
        distancias = np.hypot(de_campo[:, 0] - tirador[0], de_campo[:, 1] - tirador[1])
        mas_cerca = float(distancias.min())
    else:
        mas_cerca = np.nan

    gk_dist = gk_offline = np.nan
    if portero is not None:
        gk = np.array(portero, dtype=float)
        gk_dist = float(np.hypot(GOAL_X - gk[0], GOAL_Y - gk[1]))
        # cuánto se separa el portero de la recta tirador->centro de portería
        eje = np.array([GOAL_X, GOAL_Y]) - tirador
        largo = float(np.hypot(*eje))
        if largo > 0:
            # determinante 2D a mano: np.cross con vectores 2D está deprecado
            d = gk - tirador
            gk_offline = float(abs(eje[0] * d[1] - eje[1] * d[0]) / largo)

    return {
        "defenders_cone": float(en_cono),
        "dist_nearest_def": mas_cerca,
        "gk_dist_goal": gk_dist,
        "gk_offline": gk_offline,
    }


def shot_table(events: pd.DataFrame) -> pd.DataFrame:
    """Un tiro por fila con geometría, contexto, resultado y xG del proveedor."""
    ev = events[(events["period"] <= 4) & (events["type"] == "Shot")].copy()
    if "shot_type" in ev.columns:
        ev = ev[ev["shot_type"] != "Penalty"]
    ev = ev[ev["location"].notna()]

    def col(nombre: str, defecto=np.nan) -> pd.Series:
        return ev[nombre] if nombre in ev.columns else pd.Series(defecto, index=ev.index)

    x = ev["location"].str[0].astype(float)
    y = ev["location"].str[1].astype(float)
    dist = np.sqrt((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2)

    # ángulo que subtiende la portería desde el punto de tiro
    ux, uy = GOAL_X - x, POST_Y_LOW - y
    vx, vy = GOAL_X - x, POST_Y_HIGH - y
    dot = ux * vx + uy * vy
    normas = np.sqrt(ux**2 + uy**2) * np.sqrt(vx**2 + vy**2)
    angle = np.arccos(np.clip(dot / np.where(normas > 0, normas, 1.0), -1.0, 1.0))

    tabla = pd.DataFrame(
        {
            "player": ev.get("player"),
            "team": ev.get("team"),
            "match_id": ev.get("match_id"),
            "dist": dist,
            "angle": angle,
            "header": (col("shot_body_part", None) == "Head").astype(float),
            "under_pressure": col("under_pressure", None).eq(True).astype(float),
            "one_on_one": col("shot_one_on_one", None).eq(True).astype(float),
            "first_time": col("shot_first_time", None).eq(True).astype(float),
            "from_counter": col("play_pattern", None).eq("From Counter").astype(float),
            "from_set_piece": col("play_pattern", None).isin(SET_PIECE_PATTERNS).astype(float),
            "goal": (ev["shot_outcome"] == "Goal").astype(int),
            "sb_xg": col("shot_statsbomb_xg").astype(float),
        }
    )

    frames = col("shot_freeze_frame", None)
    contexto = [
        _freeze_frame_features(frame, np.array([xi, yi], dtype=float)) for frame, xi, yi in zip(frames, x, y)
    ]
    tabla = pd.concat([tabla.reset_index(drop=True), pd.DataFrame(contexto)], axis=1)
    return tabla


def available_features(shots: pd.DataFrame) -> list[str]:
    """Rasgos de contexto con información real en estos datos.

    Un rasgo constante o siempre ausente no aporta nada al modelo y solo
    ensucia los coeficientes, así que se descarta.
    """
    utiles = []
    for f in CONTEXT_FEATURES:
        if f not in shots.columns:
            continue
        serie = shots[f].dropna()
        if len(serie) >= 0.5 * len(shots) and serie.nunique() > 1:
            utiles.append(f)
    return utiles


def _fit_predict(shots: pd.DataFrame, features: list[str], cv: int, seed: int):
    """Ajusta el modelo y devuelve (predicciones out-of-fold, modelo, in_sample)."""
    X = shots[features].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=np.nanmedian(X, axis=0) if len(X) else 0.0)
    y = shots["goal"].to_numpy(dtype=int)

    n_min = int(min(y.sum(), len(y) - y.sum())) if len(y) else 0
    in_sample = len(shots) < 50 or n_min < 2

    # Con pocos tiros y muchos rasgos el modelo se sobreajusta: la fuerza de la
    # regularización se elige por validación cruzada *dentro* de cada fold de
    # entrenamiento (anidada), así que no contamina las predicciones out-of-fold.
    if in_sample or n_min < 6:
        clf: LogisticRegression | GridSearchCV = LogisticRegression(max_iter=1000)
    else:
        clf = GridSearchCV(
            LogisticRegression(max_iter=1000),
            {"C": np.logspace(-3, 1, 9)},
            scoring="neg_brier_score",
            cv=3,
        )
    modelo = make_pipeline(StandardScaler(), clf)

    if in_sample:
        if len(shots) and n_min >= 1:
            modelo.fit(X, y)
            pred = modelo.predict_proba(X)[:, 1]
        else:
            pred = np.full(len(shots), float(y.mean()) if len(y) else np.nan)
    else:
        skf = StratifiedKFold(n_splits=int(min(cv, n_min)), shuffle=True, random_state=seed)
        pred = cross_val_predict(modelo, X, y, cv=skf, method="predict_proba")[:, 1]
        modelo.fit(X, y)
    return pred, modelo, in_sample


def train_xg(events: pd.DataFrame, cv: int = 5, random_state: int = 7):
    """Entrena el modelo base y el contextual; devuelve (resumen, tiros).

    Los tiros llevan `xg_base` y `xg_ctx` out-of-fold. Si no hay rasgos de
    contexto utilizables (datos sin freeze frame), el contextual repite al
    base y el resumen lo indica con `has_context=False`.
    """
    shots = shot_table(events)
    contexto = available_features(shots)
    y = shots["goal"]

    base_pred, base_model, in_sample = _fit_predict(shots, BASE_FEATURES, cv, random_state)
    shots["xg_base"] = base_pred

    if contexto:
        ctx_features = BASE_FEATURES + contexto
        ctx_pred, ctx_model, _ = _fit_predict(shots, ctx_features, cv, random_state)
    else:
        ctx_features, ctx_pred, ctx_model = BASE_FEATURES, base_pred, base_model
    shots["xg_ctx"] = ctx_pred

    # Más rasgos no es mejor por definición: gana el que mejor calibra fuera de
    # muestra. Con muestras pequeñas suele ganar el base, y eso es un hallazgo,
    # no un fallo: la app lo enseña en vez de esconderlo.
    brier_base, brier_ctx = brier(shots["xg_base"], y), brier(shots["xg_ctx"], y)
    gana_contexto = bool(contexto) and brier_ctx < brier_base
    shots["xg_own"] = shots["xg_ctx"] if gana_contexto else shots["xg_base"]

    def coeficientes(modelo, features):
        """Coeficientes del regresor, esté o no envuelto en una búsqueda en rejilla."""
        try:
            estimador = modelo[-1]
            estimador = getattr(estimador, "best_estimator_", estimador)
            return dict(zip(features, estimador.coef_[0]))
        except (TypeError, IndexError, AttributeError):
            return {}

    resumen = {
        "n_shots": int(len(shots)),
        "n_goals": int(y.sum()) if len(y) else 0,
        "in_sample": in_sample,
        "has_context": bool(contexto),
        "context_features": contexto,
        "base_features": BASE_FEATURES,
        "coef_base": coeficientes(base_model, BASE_FEATURES),
        "coef_ctx": coeficientes(ctx_model, ctx_features),
        "best_model": "contextual" if gana_contexto else "base",
        "brier_base": brier_base,
        "brier_ctx": brier_ctx,
        "brier_sb": brier(shots["sb_xg"], y),
        "brier_naive": brier(pd.Series(y.mean(), index=shots.index), y) if len(y) else np.nan,
    }
    # compatibilidad con los consumidores que esperaban un único modelo
    resumen["coef"] = resumen["coef_ctx"] if gana_contexto else resumen["coef_base"]
    resumen["brier_own"] = brier(shots["xg_own"], y)
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
