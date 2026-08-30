"""Tests del modelo de xG con tiros sintéticos (sin red)."""

import numpy as np
import pandas as pd
import pytest

from futbol_analytics import xg


def _tiro(x, y, gol, sb=None, frame=None, **kw):
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
        "shot_freeze_frame": frame,
        "under_pressure": None,
        "shot_one_on_one": None,
        "shot_first_time": None,
        "play_pattern": "Regular Play",
    }
    base.update(kw)
    return base


def _actor(x, y, teammate=False, portero=False):
    return {
        "location": [x, y],
        "player": {"id": 1, "name": "X"},
        "position": {"id": 1, "name": "Goalkeeper" if portero else "Center Back"},
        "teammate": teammate,
    }


def eventos_tiros() -> pd.DataFrame:
    rows = []
    for i in range(100):  # cerca, sin oposición: mucho gol
        rows.append(_tiro(112.0, 40.0, gol=(i % 2 == 0), sb=0.45))
    for i in range(100):  # lejos: poco gol
        rows.append(_tiro(85.0, 40.0, gol=(i % 20 == 0), sb=0.05))
    rows.append(_tiro(108.0, 40.0, gol=True, sb=0.76, shot_type="Penalty"))
    rows.append(_tiro(108.0, 40.0, gol=True, sb=0.76, period=5))
    return pd.DataFrame(rows)


# --- geometría del cono de tiro -------------------------------------------


def test_defensor_entre_tirador_y_porteria_esta_en_el_cono():
    frame = [_actor(110.0, 40.0), _actor(60.0, 10.0)]  # uno tapando, otro lejísimos
    f = xg._freeze_frame_features(frame, np.array([100.0, 40.0]))
    assert f["defenders_cone"] == 1.0


def test_portero_no_cuenta_como_defensor_pero_si_se_mide():
    frame = [_actor(118.0, 40.0, portero=True)]
    f = xg._freeze_frame_features(frame, np.array([100.0, 40.0]))
    assert f["defenders_cone"] == 0.0
    assert f["gk_dist_goal"] == pytest.approx(2.0)  # a 2 unidades de la portería
    assert f["gk_offline"] == pytest.approx(0.0)  # centrado en el eje del tiro


def test_portero_descolocado_del_eje():
    frame = [_actor(115.0, 47.0, portero=True)]
    f = xg._freeze_frame_features(frame, np.array([100.0, 40.0]))
    assert f["gk_offline"] > 5.0


def test_distancia_al_defensor_mas_cercano():
    frame = [_actor(103.0, 44.0), _actor(115.0, 40.0)]
    f = xg._freeze_frame_features(frame, np.array([100.0, 40.0]))
    assert f["dist_nearest_def"] == pytest.approx(5.0)  # 3-4-5


def test_companeros_se_ignoran():
    frame = [_actor(110.0, 40.0, teammate=True)]
    f = xg._freeze_frame_features(frame, np.array([100.0, 40.0]))
    assert np.isnan(f["defenders_cone"])


def test_freeze_frame_ausente_o_corrupto():
    for malo in (None, [], "basura", [{"sin": "location"}]):
        f = xg._freeze_frame_features(malo, np.array([100.0, 40.0]))
        assert np.isnan(f["defenders_cone"])


# --- tabla de tiros y modelos ---------------------------------------------


def test_shot_table_excluye_penaltis_y_tandas():
    shots = xg.shot_table(eventos_tiros())
    assert len(shots) == 200
    assert shots["goal"].sum() == 55


def test_contexto_se_extrae_a_columnas():
    ev = pd.DataFrame(
        [
            _tiro(
                100.0,
                40.0,
                gol=True,
                sb=0.3,
                frame=[_actor(110.0, 40.0), _actor(118.0, 40.0, portero=True)],
                under_pressure=True,
                shot_one_on_one=True,
                play_pattern="From Counter",
            )
        ]
    )
    fila = xg.shot_table(ev).iloc[0]
    assert fila["under_pressure"] == 1.0
    assert fila["one_on_one"] == 1.0
    assert fila["from_counter"] == 1.0
    assert fila["from_set_piece"] == 0.0
    assert fila["defenders_cone"] == 1.0


def test_available_features_descarta_constantes():
    shots = xg.shot_table(eventos_tiros())  # sin freeze frames ni presión
    assert xg.available_features(shots) == []


def test_el_modelo_aprende_la_distancia():
    resumen, shots = xg.train_xg(eventos_tiros())
    cerca = shots[shots["dist"] < 15]["xg_own"].mean()
    lejos = shots[shots["dist"] > 15]["xg_own"].mean()
    assert cerca > lejos
    assert not resumen["in_sample"]
    assert resumen["coef_base"]["dist"] < 0


def test_sin_contexto_cae_al_modelo_geometrico():
    resumen, shots = xg.train_xg(eventos_tiros())
    assert resumen["has_context"] is False
    assert resumen["best_model"] == "base"
    assert shots["xg_own"].equals(shots["xg_base"])


def test_bate_a_la_prediccion_ingenua():
    resumen, _ = xg.train_xg(eventos_tiros())
    assert resumen["brier_own"] < resumen["brier_naive"]


def test_el_contexto_gana_cuando_aporta_senal():
    """Tiros idénticos en geometría: solo el contexto separa gol de fallo."""
    rng = np.random.default_rng(3)
    rows = []
    for _ in range(150):
        despejado = rng.random() < 0.5
        frame = [_actor(118.0 if not despejado else 112.0, 40.0, portero=True)]
        if not despejado:
            frame += [_actor(105.0, 40.0), _actor(107.0, 41.0)]
        # con portería despejada marca casi siempre; tapada, casi nunca
        gol = rng.random() < (0.75 if despejado else 0.08)
        rows.append(_tiro(100.0, 40.0, gol=gol, sb=0.2, frame=frame))
    resumen, _ = xg.train_xg(pd.DataFrame(rows))
    assert resumen["has_context"]
    assert resumen["best_model"] == "contextual"
    assert resumen["brier_ctx"] < resumen["brier_base"]


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
