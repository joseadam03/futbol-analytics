"""Tests del mapeo de Wyscout al esquema común, sin red.

Los payloads reproducen la forma documentada de la API v3. No sustituyen a
una verificación contra datos reales —que requiere credenciales—, pero sí
fijan el contrato: si alguien toca el mapeo, estos tests dicen qué se rompe.
"""

import numpy as np
import pandas as pd
import pytest

from futbol_analytics import metrics
from futbol_analytics.providers.wyscout import WyscoutProvider


def evento(primary, secondary=None, x=50, y=50, **kw):
    ev = {
        "id": kw.pop("id", 1),
        "matchPeriod": kw.pop("period", "1H"),
        "minute": kw.pop("minute", 10),
        "location": {"x": x, "y": y},
        "team": {"id": 1, "name": kw.pop("team", "Equipo A")},
        "player": {"id": 7, "name": kw.pop("player", "Jugadora Test")},
        "position": {"code": "cf", "name": "Centre Forward"},
        "type": {"primary": primary, "secondary": list(secondary or [])},
        "possession": {"id": kw.pop("possession", 100)},
    }
    ev.update(kw)
    return ev


def mapear(*eventos, match_id=1) -> pd.DataFrame:
    return WyscoutProvider._map_events({"events": list(eventos)}, match_id)


def test_coordenadas_a_unidades_statsbomb():
    df = mapear(evento("pass", x=50, y=50, **{"pass": {"accurate": True}}))
    assert df.iloc[0]["location"] == [60.0, 40.0]  # centro del campo


def test_periodos_y_tanda_de_penaltis():
    df = mapear(
        evento("pass", period="1H", **{"pass": {"accurate": True}}),
        evento("pass", period="2H", id=2, **{"pass": {"accurate": True}}),
        evento("pass", period="E1", id=3, **{"pass": {"accurate": True}}),
        evento("pass", period="P", id=4, **{"pass": {"accurate": True}}),
    )
    assert df["period"].tolist() == [1, 2, 3, 5]


def test_pase_completado_e_incompleto():
    df = mapear(
        evento("pass", x=25, y=50, **{"pass": {"accurate": True, "endLocation": {"x": 75, "y": 50}}}),
        evento("pass", id=2, **{"pass": {"accurate": False, "endLocation": {"x": 60, "y": 50}}}),
    )
    completo, fallado = df.iloc[0], df.iloc[1]
    assert completo["type"] == "Pass"
    assert pd.isna(completo["pass_outcome"])  # el esquema común usa NaN para el acierto
    assert completo["pass_end_location"] == [90.0, 40.0]
    assert fallado["pass_outcome"] == "Incomplete"


def test_balon_parado_se_etiqueta():
    df = mapear(
        evento("pass", ["corner"], **{"pass": {"accurate": True}}),
        evento("pass", ["throw_in"], id=2, **{"pass": {"accurate": True}}),
        evento("pass", ["free_kick_cross"], id=3, **{"pass": {"accurate": True}}),
    )
    assert df["pass_type"].tolist() == ["Corner", "Throw-in", "Free Kick"]
    # y son los que metrics excluye del juego en marcha
    assert set(df["pass_type"]) <= metrics.SET_PIECE_PASS_TYPES


def test_tiro_con_xg_y_gol():
    df = mapear(
        evento("shot", x=90, y=50, shot={"xg": 0.32, "isGoal": True, "bodyPart": "head"}),
        evento("shot", id=2, shot={"xg": 0.05, "isGoal": False, "bodyPart": "right_foot"}),
    )
    gol, fallo = df.iloc[0], df.iloc[1]
    assert gol["type"] == "Shot"
    assert gol["shot_statsbomb_xg"] == pytest.approx(0.32)
    assert gol["shot_outcome"] == "Goal"
    assert gol["shot_body_part"] == "Head"
    assert gol["shot_type"] == "Open Play"
    assert fallo["shot_outcome"] == "Off T"


def test_penalti_se_marca_para_poder_excluirlo():
    df = mapear(evento("shot", ["penalty"], shot={"xg": 0.78, "isGoal": True}))
    assert df.iloc[0]["shot_type"] == "Penalty"


def test_pase_clave_se_enlaza_con_el_tiro_de_su_posesion():
    df = mapear(
        evento(
            "pass", id=10, possession=5, **{"pass": {"accurate": True, "endLocation": {"x": 80, "y": 50}}}
        ),
        evento("shot", id=11, possession=5, shot={"xg": 0.2, "isGoal": False}),
        # otra posesión: el tiro no debe heredar el pase anterior
        evento("shot", id=12, possession=6, shot={"xg": 0.1, "isGoal": False}),
    )
    assert df[df["id"] == "11"].iloc[0]["shot_key_pass_id"] == "10"
    assert pd.isna(df[df["id"] == "12"].iloc[0]["shot_key_pass_id"])


def test_conduccion_corta_es_recepcion_y_larga_es_carry():
    larga = evento("carry_evt", x=20, y=50) | {
        "type": {"primary": "acceleration", "secondary": []},
        "carry": {"endLocation": {"x": 60, "y": 50}},
    }
    corta = evento("touch", x=50, y=50, id=2, carry={"endLocation": {"x": 51, "y": 50}})
    df = mapear(larga, corta)
    assert df.iloc[0]["type"] == "Carry"
    assert df.iloc[0]["carry_end_location"] == [72.0, 40.0]
    assert df.iloc[1]["type"] == "Ball Receipt*"  # 1.2 unidades: es un toque


def test_duelos_entradas_y_regates():
    df = mapear(
        evento("duel", ["sliding_tackle"]),
        evento("duel", ["dribble"], id=2, groundDuel={"keptPossession": True}),
        evento("duel", ["take_on"], id=3, groundDuel={"keptPossession": False}),
    )
    assert df.iloc[0]["duel_type"] == "Tackle"
    assert df.iloc[1]["type"] == "Dribble" and df.iloc[1]["dribble_outcome"] == "Complete"
    assert df.iloc[2]["dribble_outcome"] == "Incomplete"


def test_acciones_defensivas_y_presion():
    df = mapear(
        evento("interception"),
        evento("clearance", id=2),
        evento("shot_block", id=3),
        evento("pressing_attempt", id=4),
        evento("infraction", id=5),
        evento("other", ["recovery"], id=6),
    )
    assert df["type"].tolist() == [
        "Interception",
        "Clearance",
        "Block",
        "Pressure",
        "Foul Committed",
        "Ball Recovery",
    ]


def test_eventos_sin_equivalente_se_descartan():
    df = mapear(evento("game_interruption"), evento("pass", id=2, **{"pass": {"accurate": True}}))
    assert len(df) == 1
    assert df.iloc[0]["type"] == "Pass"


def test_payload_vacio_o_corrupto_no_revienta():
    assert WyscoutProvider._map_events({}, 1).empty
    assert WyscoutProvider._map_events({"events": None}, 1).empty
    assert WyscoutProvider._map_events({"events": ["basura", None]}, 1).empty


def test_el_esquema_resultante_alimenta_las_metricas():
    """La prueba que importa: lo mapeado se puede analizar sin tocar metrics."""
    eventos = [
        evento(
            "pass",
            id=i,
            x=25,
            y=50,
            **{"pass": {"accurate": True, "endLocation": {"x": 75, "y": 50}}},
        )
        for i in range(1, 6)
    ]
    eventos.append(evento("shot", id=20, x=90, y=50, shot={"xg": 0.4, "isGoal": True}))
    eventos.append(evento("interception", id=21, x=30, y=50))
    df = mapear(*eventos)

    minutos = pd.DataFrame(
        [
            {
                "player": "Jugadora Test",
                "nickname": "Test",
                "team": "Equipo A",
                "minutes": 90.0,
                "lineup_position": "Centre Forward",
            }
        ]
    )
    tabla = metrics.player_metrics(df, minutos, min_minutes=0)
    fila = tabla.iloc[0]
    assert fila["npxg"] == pytest.approx(0.4)
    assert fila["passes_cmp"] == 5
    assert fila["prog_passes"] == 5  # 25%->75% del campo es progresivo
    assert fila["interceptions"] == 1
    assert fila["position_group"] == "FW"


def test_minutos_desde_alineaciones():
    raw = {
        "teams": {
            "1": {
                "team": {"name": "Equipo A"},
                "formation": {
                    "lineup": [
                        {"name": "Titular Completa", "shortName": "T. Completa"},
                        {"name": "Titular Sustituida", "shortName": "T. Sustituida"},
                    ],
                    "bench": [
                        {"name": "Suplente Entra", "shortName": "S. Entra"},
                        {"name": "Suplente Sin Jugar", "shortName": "S. Sin Jugar"},
                    ],
                    "substitutions": [
                        {
                            "minute": 60,
                            "playerOut": {"name": "Titular Sustituida"},
                            "playerIn": {"name": "Suplente Entra"},
                        }
                    ],
                },
            }
        }
    }
    filas = WyscoutProvider._map_formations(raw, match_id=1, end_minute=94.0)
    minutos = {f["player"]: f["minutes"] for f in filas}
    assert minutos["Titular Completa"] == pytest.approx(94.0)
    assert minutos["Titular Sustituida"] == pytest.approx(60.0)
    assert minutos["Suplente Entra"] == pytest.approx(34.0)
    assert "Suplente Sin Jugar" not in minutos  # no llegó a jugar


def test_sin_credenciales_el_proveedor_avisa(monkeypatch):
    monkeypatch.delenv("WYSCOUT_CLIENT_ID", raising=False)
    monkeypatch.delenv("WYSCOUT_CLIENT_SECRET", raising=False)
    p = WyscoutProvider()
    assert not p.available()
    with pytest.raises(NotImplementedError):
        p.competitions()
    with pytest.raises(NotImplementedError):
        p.events(1, 1)
    with pytest.raises(NotImplementedError):
        p.minutes_played(1, 1, pd.DataFrame({"period": [], "minute": [], "match_id": []}))


def test_xy_tolera_coordenadas_ausentes():
    from futbol_analytics.providers.wyscout import _xy

    assert _xy(None) is None
    assert _xy({"x": None, "y": 5}) is None
    assert _xy({"x": 100, "y": 100}) == [120.0, 80.0]  # esquina opuesta
    assert not np.isnan(_xy({"x": 0, "y": 0})).any()
