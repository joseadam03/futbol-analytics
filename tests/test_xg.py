"""Tests del modelo de xG propio con tiros sintéticos (sin red)."""

import pandas as pd
import pytest

from futbol_analytics import xg


def _tiro(x, y, gol, sb=None, **kw):
    base = {
        "match_id": 1,
        "period": 1,
        "team": "A",
        "player": "P",
        "type": "Shot",
        "location": [x, y],
        "shot_type": "Open Play",
        "shot_outcome": "Goal" if gol else "Off T",
        "shot_statsbomb_xg": sb,
        "shot_body_part": "Right Foot",
    }
    base.update(kw)
    return base


def eventos_tiros() -> pd.DataFrame:
    rows = []
    # 100 tiros cercanos (50 % gol) y 100 lejanos (5 % gol)
    for i in range(100):
        rows.append(_tiro(112.0, 40.0, gol=(i % 2 == 0), sb=0.45))
    for i in range(100):
        rows.append(_tiro(85.0, 40.0, gol=(i % 20 == 0), sb=0.05))
    # ruido que debe quedar fuera: penalti y tanda de penaltis
    rows.append(_tiro(108.0, 40.0, gol=True, sb=0.76, shot_type="Penalty"))
    rows.append(_tiro(108.0, 40.0, gol=True, sb=0.76, period=5))
    return pd.DataFrame(rows)


def test_shot_table_excluye_penaltis_y_tandas():
    shots = xg.shot_table(eventos_tiros())
    assert len(shots) == 200
    assert shots["goal"].sum() == 55


def test_el_modelo_aprende_la_distancia():
    resumen, shots = xg.train_xg(eventos_tiros())
    cerca = shots[shots["dist"] < 15]["xg_own"].mean()
    lejos = shots[shots["dist"] > 15]["xg_own"].mean()
    assert cerca > lejos
    assert not resumen["in_sample"]
    assert resumen["coef"]["dist"] < 0  # más lejos, menos gol


def test_bate_a_la_prediccion_base():
    resumen, _ = xg.train_xg(eventos_tiros())
    assert resumen["brier_own"] < resumen["brier_base"]


def test_pocos_tiros_cae_a_in_sample():
    pocos = pd.DataFrame([_tiro(110.0, 40.0, gol=(i % 3 == 0), sb=0.3) for i in range(10)])
    resumen, shots = xg.train_xg(pocos)
    assert resumen["in_sample"] is True
    assert shots["xg_own"].between(0, 1).all()


def test_calibration_bins_conserva_los_tiros():
    _, shots = xg.train_xg(eventos_tiros())
    cal = xg.calibration_bins(shots["xg_own"], shots["goal"])
    assert cal["n"].sum() == len(shots)
    assert ((cal["pred"] >= 0) & (cal["pred"] <= 1)).all()


def test_brier_ignora_nan():
    p = pd.Series([0.5, None, 0.2])
    y = pd.Series([1, 0, 0])
    assert xg.brier(p, y) == pytest.approx((0.25 + 0.04) / 2)
