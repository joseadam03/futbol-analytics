"""Proveedor Wyscout (API v3 de Hudl): mapeo completo al esquema común.

Estado: la autenticación, la paginación, la caché y **el mapeo de eventos**
están implementados. Falta lo único que no se puede hacer sin acceso: haber
ejecutado esto contra la API real. El mapeo está escrito contra el esquema
documentado de la v3 (`apidocs.wyscout.com`) y cubierto por tests con
payloads sintéticos que reproducen esa forma; cuando lleguen credenciales,
lo que toca es contrastar los nombres de campo con un partido real y ajustar
las constantes de traducción de abajo, no reescribir la lógica.

Para activarlo:
1. Contratar acceso a la API (https://www.hudl.com/products/wyscout) y definir
   `WYSCOUT_CLIENT_ID` / `WYSCOUT_CLIENT_SECRET` (autenticación básica de la v3),
   o dárselas solo a un usuario del login opcional (`wyscout_client_id` /
   `wyscout_client_secret` en su entrada de `config.yaml`; ver auth.py) para
   no compartirlas con el resto de cuentas.
2. Seleccionar el proveedor "Wyscout" en la barra lateral de la app.

Decisiones del mapeo, para que se puedan discutir:
- Las coordenadas de Wyscout van en porcentaje (0-100) del campo; se llevan a
  unidades StatsBomb multiplicando por 1.2 (x) y 0.8 (y).
- El xG propio de Wyscout (`shot.xg`) se vuelca en `shot_statsbomb_xg`, que en
  el esquema común funciona como "xG del proveedor".
- Wyscout no trae `shot_key_pass_id`: se reconstruye enlazando cada tiro con el
  último pase del mismo equipo dentro de la misma posesión.
- `pass.accurate` es el equivalente de `pass_outcome` (NaN si el pase llegó,
  "Incomplete" si no), que es como lo consumen `metrics` y `viz`.
"""

from __future__ import annotations

import os
from contextvars import ContextVar

import numpy as np
import pandas as pd
import requests

from ..paths import CACHE_DIR
from .base import Provider

API_BASE = "https://apirest.wyscout.com/v3"

# Credenciales del usuario logueado para esta sesión (ver auth.py). Un
# ContextVar y no os.environ: streamlit sirve varias sesiones concurrentes en
# el mismo proceso, y escribir en el entorno filtraría la clave de un usuario
# a las peticiones de otro.
_CREDENTIALS: ContextVar[tuple[str, str] | None] = ContextVar("wyscout_credentials", default=None)


def set_session_credentials(client_id: str, client_secret: str) -> None:
    _CREDENTIALS.set((client_id, client_secret))


_MSG = (
    "El proveedor Wyscout requiere credenciales de la API de Hudl/Wyscout "
    "(variables WYSCOUT_CLIENT_ID y WYSCOUT_CLIENT_SECRET)."
)

# Wyscout mide el campo en porcentaje; StatsBomb, en 120x80.
X_SCALE, Y_SCALE = 1.2, 0.8

PERIOD_MAP = {"1H": 1, "2H": 2, "E1": 3, "E2": 4, "P": 5}

# primaryType de Wyscout -> type del esquema común
TYPE_MAP = {
    "pass": "Pass",
    "smart_pass": "Pass",
    "cross": "Pass",
    "shot": "Shot",
    "interception": "Interception",
    "clearance": "Clearance",
    "shot_block": "Block",
    "touch": "Carry",
    "acceleration": "Carry",
    "infraction": "Foul Committed",
    "pressing_attempt": "Pressure",
    "duel": "Duel",
}
# secondaryTypes que marcan balón parado, en el vocabulario del esquema común
SET_PIECE_MAP = {
    "corner": "Corner",
    "free_kick": "Free Kick",
    "free_kick_cross": "Free Kick",
    "throw_in": "Throw-in",
    "goal_kick": "Goal Kick",
    "kick_off": "Kick Off",
}
TACKLE_TYPES = {"sliding_tackle", "defensive_duel", "ground_defending_duel"}
RECOVERY_TYPES = {"recovery", "counterpressing_recovery"}
BODY_PART_MAP = {"head": "Head", "head_or_other": "Head"}
CARRY_MIN_LENGTH = 5.0  # unidades StatsBomb: por debajo es ruido, no conducción


def _xy(loc: dict | None) -> list[float] | None:
    """Coordenada de Wyscout (% del campo) a unidades StatsBomb."""
    if not isinstance(loc, dict):
        return None
    x, y = loc.get("x"), loc.get("y")
    if x is None or y is None:
        return None
    return [float(x) * X_SCALE, float(y) * Y_SCALE]


def _dist(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    return float(np.hypot(b[0] - a[0], b[1] - a[1]))


class WyscoutProvider(Provider):
    name = "Wyscout"

    def __init__(self) -> None:
        self._auth = _CREDENTIALS.get() or (
            os.environ.get("WYSCOUT_CLIENT_ID", ""),
            os.environ.get("WYSCOUT_CLIENT_SECRET", ""),
        )

    def available(self) -> bool:
        return bool(self._auth[0] and self._auth[1])

    def has_cached(self, competition_id: int, season_id: int) -> bool:
        return (CACHE_DIR / f"wyscout_events_{competition_id}_{season_id}.pkl").exists()

    def _get(self, path: str, **params) -> dict:
        resp = requests.get(f"{API_BASE}{path}", auth=self._auth, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def competitions(self) -> pd.DataFrame:
        if not self.available():
            raise NotImplementedError(_MSG)
        data = self._get("/competitions", areaId="")  # todas las áreas contratadas
        rows = [
            {
                "competition_id": c["wyId"],
                "season_id": c.get("currentSeasonId"),
                "competition_name": c["name"],
                "season_name": str(c.get("currentSeasonId", "")),
            }
            for c in data.get("competitions", [])
        ]
        return pd.DataFrame(rows)

    def _season_matches(self, season_id: int) -> list[int]:
        data = self._get(f"/seasons/{season_id}/matches")
        return [m["matchId"] for m in data.get("matches", [])]

    def matches(self, competition_id: int, season_id: int) -> pd.DataFrame:
        if not self.available():
            raise NotImplementedError(_MSG)
        data = self._get(f"/seasons/{season_id}/matches")
        return pd.DataFrame(
            [
                {
                    "match_id": m.get("matchId"),
                    "match_date": m.get("date"),
                    "match_week": m.get("gameweek"),
                    "home_team": (m.get("home") or {}).get("name"),
                    "away_team": (m.get("away") or {}).get("name"),
                }
                for m in data.get("matches", [])
            ]
        )

    def events(self, competition_id: int, season_id: int, refresh: bool = False) -> pd.DataFrame:
        if not self.available():
            raise NotImplementedError(_MSG)
        cache = CACHE_DIR / f"wyscout_events_{competition_id}_{season_id}.pkl"
        if cache.exists() and not refresh:
            return pd.read_pickle(cache)

        frames = []
        for match_id in self._season_matches(season_id):
            raw = self._get(f"/matches/{match_id}/events")
            frames.append(self._map_events(raw, match_id))
        all_events = pd.concat(frames, ignore_index=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        all_events.to_pickle(cache)
        return all_events

    @staticmethod
    def _map_events(raw: dict, match_id: int) -> pd.DataFrame:
        """Convierte los eventos de un partido al esquema común (ver base.py)."""
        rows: list[dict] = []
        # último pase por posesión, para reconstruir shot_key_pass_id
        ultimo_pase: dict[tuple, str] = {}

        for ev in raw.get("events") or []:
            if not isinstance(ev, dict):
                continue
            tipos = ev.get("type") or {}
            # a texto desde el principio: un payload raro no debe romper las búsquedas
            primario = str(tipos.get("primary") or "")
            secundarios = {str(s) for s in (tipos.get("secondary") or [])}

            loc = _xy(ev.get("location"))
            equipo = (ev.get("team") or {}).get("name")
            jugador = (ev.get("player") or {}).get("name")
            posesion = (ev.get("possession") or {}).get("id")
            ev_id = str(ev.get("id"))

            fila = {
                "id": ev_id,
                "match_id": match_id,
                "period": PERIOD_MAP.get(str(ev.get("matchPeriod") or ""), 1),
                "minute": ev.get("minute"),
                "team": equipo,
                "player": jugador,
                "position": (ev.get("position") or {}).get("name"),
                "type": TYPE_MAP.get(primario),
                "location": loc,
                "possession": posesion,
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
                "shot_body_part": None,
                "ball_recovery_recovery_failure": None,
            }

            pase = ev.get("pass") or {}
            tiro = ev.get("shot") or {}
            carry = ev.get("carry") or {}

            if fila["type"] == "Pass":
                fila["pass_end_location"] = _xy(pase.get("endLocation"))
                # accurate=False -> incompleto; el esquema común usa NaN para el acierto
                fila["pass_outcome"] = None if pase.get("accurate", True) else "Incomplete"
                for clave, nombre in SET_PIECE_MAP.items():
                    if clave in secundarios:
                        fila["pass_type"] = nombre
                        break
                if "assist" in secundarios or "goal_assist" in secundarios:
                    fila["pass_goal_assist"] = True
                if "shot_assist" in secundarios or "key_pass" in secundarios:
                    fila["pass_shot_assist"] = True
                if posesion is not None and pase.get("accurate", True):
                    ultimo_pase[(equipo, posesion)] = ev_id

            elif fila["type"] == "Shot":
                fila["shot_statsbomb_xg"] = tiro.get("xg")
                fila["shot_outcome"] = "Goal" if tiro.get("isGoal") else "Off T"
                es_penalti = primario == "penalty" or "penalty" in secundarios
                fila["shot_type"] = "Penalty" if es_penalti else "Open Play"
                fila["shot_body_part"] = BODY_PART_MAP.get(str(tiro.get("bodyPart") or ""), "Right Foot")
                if posesion is not None:
                    fila["shot_key_pass_id"] = ultimo_pase.get((equipo, posesion))

            elif fila["type"] == "Carry":
                fin = _xy(carry.get("endLocation")) or _xy(ev.get("endLocation"))
                # sin desplazamiento apreciable es un toque, no una conducción
                if fin and _dist(loc, fin) >= CARRY_MIN_LENGTH:
                    fila["carry_end_location"] = fin
                else:
                    fila["type"] = "Ball Receipt*"

            elif fila["type"] == "Duel":
                if secundarios & TACKLE_TYPES:
                    fila["duel_type"] = "Tackle"
                if "dribble" in secundarios or "take_on" in secundarios:
                    fila["type"] = "Dribble"
                    ganado = (ev.get("groundDuel") or {}).get("keptPossession")
                    fila["dribble_outcome"] = "Complete" if ganado else "Incomplete"

            if primario in {"penalty", "free_kick_shot"} and fila["type"] is None:
                fila["type"] = "Shot"
                fila["shot_statsbomb_xg"] = tiro.get("xg")
                fila["shot_outcome"] = "Goal" if tiro.get("isGoal") else "Off T"
                fila["shot_type"] = "Penalty" if primario == "penalty" else "Free Kick"

            if secundarios & RECOVERY_TYPES and fila["type"] is None:
                fila["type"] = "Ball Recovery"

            if fila["type"] is None:
                continue  # evento sin equivalente en el esquema común

            rows.append(fila)

        return pd.DataFrame(rows)

    def minutes_played(
        self,
        competition_id: int,
        season_id: int,
        events_df: pd.DataFrame,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Minutos por jugador desde las alineaciones oficiales de cada partido."""
        if not self.available():
            raise NotImplementedError(_MSG)
        cache = CACHE_DIR / f"wyscout_minutes_{competition_id}_{season_id}.pkl"
        if cache.exists() and not refresh:
            return pd.read_pickle(cache)

        fin = events_df[events_df["period"] <= 4].groupby("match_id")["minute"].max() + 1
        rows = []
        for match_id in events_df["match_id"].unique().tolist():
            raw = self._get(f"/matches/{int(match_id)}/formations")
            rows += self._map_formations(raw, int(match_id), float(fin.get(match_id, 95)))

        per_match = pd.DataFrame(rows)
        out = per_match.groupby(["player", "team"], as_index=False).agg(
            nickname=("nickname", "first"),
            minutes=("minutes", "sum"),
            lineup_position=("lineup_position", "first"),
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        out.to_pickle(cache)
        return out

    @staticmethod
    def _map_formations(raw: dict, match_id: int, end_minute: float) -> list[dict]:
        """Minutos por jugador de un partido, desde `/matches/{id}/formations`.

        Cada equipo trae sus titulares y la lista de sustituciones con el minuto;
        un titular que no sale juega hasta el final, y un suplente que entra,
        desde su minuto de entrada.
        """
        filas = []
        equipos = raw.get("teams") or {}
        for team_id, datos in equipos.items():
            nombre_equipo = (datos.get("team") or {}).get("name") or str(team_id)
            formacion = datos.get("formation") or {}

            salidas: dict[str, float] = {}
            entradas: dict[str, float] = {}
            info: dict[str, dict] = {}
            for sub in formacion.get("substitutions") or []:
                minuto = float(sub.get("minute", end_minute))
                fuera = sub.get("playerOut") or {}
                dentro = sub.get("playerIn") or {}
                if fuera.get("name"):
                    salidas[fuera["name"]] = minuto
                    info.setdefault(fuera["name"], fuera)
                if dentro.get("name"):
                    entradas[dentro["name"]] = minuto
                    info.setdefault(dentro["name"], dentro)

            for jugador in formacion.get("lineup") or []:
                nombre = (jugador or {}).get("name")
                if nombre:
                    info.setdefault(nombre, jugador)
                    entradas.setdefault(nombre, 0.0)
            for jugador in formacion.get("bench") or []:
                nombre = (jugador or {}).get("name")
                if nombre:
                    info.setdefault(nombre, jugador)

            for nombre, datos_jugador in info.items():
                if nombre not in entradas:
                    continue  # suplente que no llegó a jugar
                desde = entradas[nombre]
                hasta = salidas.get(nombre, end_minute)
                filas.append(
                    {
                        "player": nombre,
                        "nickname": datos_jugador.get("shortName") or nombre,
                        "team": nombre_equipo,
                        "match_id": match_id,
                        "minutes": max(0.0, hasta - desde),
                        "lineup_position": (datos_jugador.get("position") or {}).get("name")
                        if isinstance(datos_jugador.get("position"), dict)
                        else datos_jugador.get("position"),
                    }
                )
        return filas
