"""Proveedor de demostración: una liga sintética, determinista y sin red.

Sirve para dos cosas:
- los tests de interfaz (AppTest) renderizan la app completa en segundos, y
- un modo demo (`FUTBOL_ANALYTICS_FAKE=1`) para enseñar la app sin esperar
  a la primera descarga de datos reales.

Los eventos respetan el esquema común de `base.py` y tienen la textura
mínima que consumen métricas y visualizaciones: pases con destino y
progresión, conducciones, tiros con xG (y pases clave enlazados), presión,
acciones defensivas y posiciones por rol. Dos equipos con estilos opuestos
para que Equipos y Encaje tengan algo que contar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Provider

# (posición, perfil de volumen por partido)
_PLANTILLA = [
    ("Goalkeeper", dict(passes=25, prog=0.05, carries=3, shots=0.0, press=1, defe=3, dribbles=0)),
    ("Right Center Back", dict(passes=55, prog=0.12, carries=12, shots=0.3, press=6, defe=14, dribbles=0)),
    ("Left Center Back", dict(passes=55, prog=0.12, carries=12, shots=0.3, press=6, defe=14, dribbles=0)),
    ("Right Back", dict(passes=45, prog=0.18, carries=18, shots=0.5, press=10, defe=10, dribbles=2)),
    ("Left Back", dict(passes=45, prog=0.18, carries=18, shots=0.5, press=10, defe=10, dribbles=2)),
    (
        "Center Defensive Midfield",
        dict(passes=60, prog=0.15, carries=14, shots=0.8, press=14, defe=12, dribbles=1),
    ),
    ("Left Center Midfield", dict(passes=55, prog=0.2, carries=16, shots=1.2, press=12, defe=8, dribbles=2)),
    (
        "Center Attacking Midfield",
        dict(passes=45, prog=0.25, carries=18, shots=2.0, press=10, defe=4, dribbles=3),
    ),
    ("Right Wing", dict(passes=30, prog=0.3, carries=22, shots=2.2, press=9, defe=3, dribbles=5)),
    ("Left Wing", dict(passes=30, prog=0.3, carries=22, shots=2.2, press=9, defe=3, dribbles=5)),
    ("Center Forward", dict(passes=22, prog=0.15, carries=12, shots=3.2, press=8, defe=2, dribbles=2)),
]

# estilo por equipo: multiplicadores sobre pases y presión
_EQUIPOS = {
    "Atlético Píxel": dict(passes=1.3, press=1.4),  # posesivo y presionante
    "Real Vector": dict(passes=0.8, press=0.7),  # directo y replegado
}

_MATCHES = 2


class FakeProvider(Provider):
    name = "Demo (liga sintética)"

    def competitions(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "competition_id": 1,
                    "season_id": 1,
                    "competition_name": "Liga Demo",
                    "season_name": "2025/2026",
                }
            ]
        )

    def events(self, competition_id: int, season_id: int, refresh: bool = False) -> pd.DataFrame:
        rng = np.random.default_rng(7)
        rows: list[dict] = []
        next_id = iter(range(1, 10_000_000))
        next_possession = iter(range(1, 10_000_000))

        def evento(**kw) -> dict:
            base = {
                "id": str(next(next_id)),
                "match_id": 1,
                "period": 1,
                "minute": int(rng.integers(0, 90)),
                "team": None,
                "player": None,
                "position": None,
                "type": None,
                "location": None,
                "pass_end_location": None,
                "pass_outcome": None,
                "pass_type": None,
                "pass_goal_assist": None,
                "pass_shot_assist": None,
                "carry_end_location": None,
                "dribble_outcome": None,
                "duel_type": None,
                "shot_type": None,
                "shot_outcome": None,
                "shot_statsbomb_xg": None,
                "shot_key_pass_id": None,
                "ball_recovery_recovery_failure": None,
                "shot_body_part": None,
                "possession": None,
            }
            base.update(kw)
            rows.append(base)
            return base

        def punto(x_centro: float, amplitud: float = 18.0) -> list[float]:
            x = float(np.clip(rng.normal(x_centro, amplitud), 1.0, 119.0))
            y = float(np.clip(rng.normal(40.0, 16.0), 1.0, 79.0))
            return [x, y]

        for match_id in range(1, _MATCHES + 1):
            for equipo, estilo in _EQUIPOS.items():
                for i, (posicion, perfil) in enumerate(_PLANTILLA, 1):
                    jugador = f"{equipo.split()[-1]} {i:02d}"
                    comun = {
                        "match_id": match_id,
                        "team": equipo,
                        "player": jugador,
                        "position": posicion,
                        "possession": next(next_possession),
                    }
                    x_base = 25.0 + 7.0 * i  # los de arriba juegan más adelante

                    n_passes = int(perfil["passes"] * estilo["passes"])
                    for _ in range(n_passes):
                        origen = punto(x_base)
                        progresivo = rng.random() < perfil["prog"]
                        destino = (
                            [min(origen[0] + rng.uniform(20, 40), 119.0), origen[1]]
                            if progresivo
                            else [origen[0] + rng.uniform(-5, 8), origen[1] + rng.uniform(-8, 8)]
                        )
                        completado = rng.random() < 0.82
                        evento(
                            **comun,
                            type="Pass",
                            location=origen,
                            pass_end_location=destino,
                            pass_outcome=None if completado else "Incomplete",
                        )

                    for _ in range(int(perfil["carries"])):
                        origen = punto(x_base)
                        evento(
                            **comun,
                            type="Carry",
                            location=origen,
                            carry_end_location=[min(origen[0] + rng.uniform(3, 25), 119.0), origen[1]],
                        )

                    n_shots = int(rng.poisson(perfil["shots"]))
                    for _ in range(n_shots):
                        origen = punto(106.0, 8.0)
                        xg_tiro = float(np.clip(rng.beta(2, 8), 0.02, 0.9))
                        clave = None
                        if rng.random() < 0.5:
                            pase = evento(
                                **comun,
                                type="Pass",
                                location=punto(95.0, 10.0),
                                pass_end_location=origen,
                                pass_shot_assist=True,
                            )
                            clave = pase["id"]
                        evento(
                            **comun,
                            type="Shot",
                            location=origen,
                            shot_type="Open Play",
                            shot_outcome="Goal" if rng.random() < xg_tiro else "Off T",
                            shot_statsbomb_xg=xg_tiro,
                            shot_key_pass_id=clave,
                            shot_body_part="Head" if rng.random() < 0.15 else "Right Foot",
                        )

                    for _ in range(int(perfil["press"] * estilo["press"])):
                        evento(**comun, type="Pressure", location=punto(60.0))
                    for _ in range(int(perfil["defe"])):
                        tipo = rng.choice(["Interception", "Duel", "Ball Recovery", "Block", "Clearance"])
                        extra = {"duel_type": "Tackle"} if tipo == "Duel" else {}
                        evento(**comun, type=str(tipo), location=punto(35.0), **extra)
                    for _ in range(int(perfil["dribbles"])):
                        evento(
                            **comun,
                            type="Dribble",
                            location=punto(80.0),
                            dribble_outcome="Complete" if rng.random() < 0.6 else "Incomplete",
                        )

        return pd.DataFrame(rows)

    def minutes_played(
        self,
        competition_id: int,
        season_id: int,
        events_df: pd.DataFrame,
        refresh: bool = False,
    ) -> pd.DataFrame:
        rows = []
        for equipo in _EQUIPOS:
            for i, (posicion, _) in enumerate(_PLANTILLA, 1):
                jugador = f"{equipo.split()[-1]} {i:02d}"
                rows.append(
                    {
                        "player": jugador,
                        "nickname": jugador,
                        "team": equipo,
                        "minutes": 90.0 * _MATCHES,
                        "lineup_position": posicion,
                    }
                )
        return pd.DataFrame(rows)
