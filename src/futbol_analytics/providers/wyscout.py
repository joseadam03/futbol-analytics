"""Proveedor Wyscout (API v3 de Hudl) — esqueleto funcional pendiente de credenciales.

Para activarlo:
1. Contratar acceso a la API de Wyscout (https://www.hudl.com/products/wyscout)
   y definir las variables de entorno `WYSCOUT_CLIENT_ID` y `WYSCOUT_CLIENT_SECRET`
   (autenticación básica de la API v3).
2. Completar `_map_events`: el mapeo de los eventos de Wyscout al esquema común
   documentado en `base.py`. La estructura de autenticación, paginación, caché y
   endpoints ya está implementada abajo.

Notas del mapeo (v3):
- Los eventos llegan en `GET /matches/{wyId}/events` con `primaryType` y
  `secondaryTypes`; las coordenadas van en porcentaje (0-100) del campo →
  convertir a las unidades StatsBomb: x*1.2, y*0.8.
- El xG propio de Wyscout (campo `shot.xg`) se vuelca en `shot_statsbomb_xg`
  (la columna funciona como "xG del proveedor").
- `pass.accurate` → `pass_outcome` (NaN si preciso, "Incomplete" si no).
- Las asistencias de tiro se reconstruyen enlazando el pase con el tiro
  siguiente de la misma posesión (`possession.id`), porque Wyscout no trae
  `shot_key_pass_id`.
"""

from __future__ import annotations

import os

import pandas as pd
import requests

from ..paths import CACHE_DIR
from .base import Provider

API_BASE = "https://apirest.wyscout.com/v3"

_MSG = (
    "El proveedor Wyscout requiere credenciales de la API de Hudl/Wyscout "
    "(variables WYSCOUT_CLIENT_ID y WYSCOUT_CLIENT_SECRET) y completar el "
    "mapeo de eventos (_map_events). Autenticación, endpoints y caché ya "
    "están implementados."
)


class WyscoutProvider(Provider):
    name = "Wyscout"

    def __init__(self) -> None:
        self._auth = (
            os.environ.get("WYSCOUT_CLIENT_ID", ""),
            os.environ.get("WYSCOUT_CLIENT_SECRET", ""),
        )

    def available(self) -> bool:
        return bool(self._auth[0] and self._auth[1])

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
        """Convierte los eventos de Wyscout al esquema común (ver base.py).

        TODO (requiere credenciales para verificar el payload real):
        - primaryType 'pass'      -> type='Pass', pass_end_location, pass_outcome
        - primaryType 'shot'      -> type='Shot', shot.xg -> shot_statsbomb_xg
        - primaryType 'duel' + secondaryTypes 'defensive_duel'/'sliding_tackle'
                                  -> duel_type='Tackle'
        - primaryType 'interception' -> type='Interception'
        - primaryType 'touch'/'acceleration' con desplazamiento -> type='Carry'
        - infraction              -> type='Foul Committed'
        - coordenadas % -> unidades StatsBomb (x*1.2, y*0.8)
        - reconstruir shot_key_pass_id por posesión compartida
        """
        raise NotImplementedError(_MSG)

    def minutes_played(
        self,
        competition_id: int,
        season_id: int,
        events_df: pd.DataFrame,
        refresh: bool = False,
    ) -> pd.DataFrame:
        if not self.available():
            raise NotImplementedError(_MSG)
        # GET /matches/{wyId}/formations trae titulares, cambios y minutos.
        raise NotImplementedError(_MSG)
