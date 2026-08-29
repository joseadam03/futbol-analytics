"""Proveedor Wyscout — preparado, pendiente de credenciales.

La API de Wyscout (Hudl) es de pago. Cuando haya credenciales, implementar:

1. Autenticación (API v3, básica con client_id/secret vía variables de
   entorno `WYSCOUT_CLIENT_ID` / `WYSCOUT_CLIENT_SECRET`).
2. Descarga de eventos por partido y mapeo al esquema común documentado en
   `base.py` (los nombres de evento de Wyscout difieren: p. ej. su
   `infraction`/`duel` no separa entradas igual que StatsBomb, y su xG es
   propio — mapear a `shot_statsbomb_xg` como columna de xG genérica).
3. Caché local idéntico al de StatsBomb.

`metrics`, `similarity` y `viz` no necesitan ningún cambio: consumen el
esquema común.
"""

from __future__ import annotations

import os

import pandas as pd

from .base import Provider

_MSG = (
    "El proveedor Wyscout requiere credenciales de la API de Hudl/Wyscout "
    "(variables WYSCOUT_CLIENT_ID y WYSCOUT_CLIENT_SECRET). "
    "La interfaz está lista; falta implementar el mapeo de eventos."
)


class WyscoutProvider(Provider):
    name = "Wyscout"

    def available(self) -> bool:
        return bool(os.environ.get("WYSCOUT_CLIENT_ID"))

    def competitions(self) -> pd.DataFrame:
        raise NotImplementedError(_MSG)

    def events(self, competition_id: int, season_id: int, refresh: bool = False) -> pd.DataFrame:
        raise NotImplementedError(_MSG)

    def minutes_played(
        self,
        competition_id: int,
        season_id: int,
        events_df: pd.DataFrame,
        refresh: bool = False,
    ) -> pd.DataFrame:
        raise NotImplementedError(_MSG)
