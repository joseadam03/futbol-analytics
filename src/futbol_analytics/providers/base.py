"""Contrato común de proveedores de datos.

Todo proveedor debe entregar los datos normalizados al esquema de eventos
común (basado en el de StatsBomb), que es el que consumen `metrics` y `viz`:

- Columnas mínimas de eventos: `match_id`, `period`, `minute`, `team`,
  `player`, `position`, `type`, `location`, `pass_end_location`,
  `pass_outcome`, `pass_type`, `pass_goal_assist`, `pass_shot_assist`,
  `carry_end_location`, `dribble_outcome`, `duel_type`, `shot_type`,
  `shot_outcome`, `shot_statsbomb_xg`, `shot_key_pass_id`, `id`.
- Minutos: `player`, `team`, `minutes`, `lineup_position`.

Añadir un proveedor nuevo = implementar esta clase y registrarlo en
`providers/__init__.py`. Nada más cambia.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Provider(ABC):
    """Fuente de datos de eventos de fútbol."""

    name: str

    def available(self) -> bool:
        """Si el proveedor puede usarse ahora mismo (credenciales, etc.)."""
        return True

    def has_cached(self, competition_id: int, season_id: int) -> bool:
        """Si los eventos de esa competición ya están en la caché local.

        Sirve para ofrecer pools multi-competición sin disparar descargas
        largas por sorpresa; por defecto, no hay caché.
        """
        return False

    @abstractmethod
    def competitions(self) -> pd.DataFrame:
        """Competiciones/temporadas disponibles (competition_id, season_id, nombres)."""

    @abstractmethod
    def events(self, competition_id: int, season_id: int, refresh: bool = False) -> pd.DataFrame:
        """Eventos de toda la competición, en el esquema común."""

    @abstractmethod
    def minutes_played(
        self,
        competition_id: int,
        season_id: int,
        events_df: pd.DataFrame,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Minutos jugados por jugador."""
