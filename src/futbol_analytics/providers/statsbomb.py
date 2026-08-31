"""Proveedor StatsBomb open data, con caché local en data/cache/."""

from __future__ import annotations

import logging
import warnings

import pandas as pd
import requests
from statsbombpy import sb

from ..paths import CACHE_DIR
from .base import Provider

# statsbombpy avisa en cada llamada de que se usan open data sin credenciales
warnings.filterwarnings("ignore", module="statsbombpy")

log = logging.getLogger(__name__)


def _clock_to_min(clock: str) -> float:
    mm, ss = clock.split(":")
    return int(mm) + int(ss) / 60


class StatsBombProvider(Provider):
    name = "StatsBomb (open data)"

    def competitions(self) -> pd.DataFrame:
        return sb.competitions()

    def has_cached(self, competition_id: int, season_id: int) -> bool:
        return (CACHE_DIR / f"events_{competition_id}_{season_id}.pkl").exists()

    def matches(self, competition_id: int, season_id: int) -> pd.DataFrame:
        return sb.matches(competition_id=competition_id, season_id=season_id)

    def events(self, competition_id: int, season_id: int, refresh: bool = False) -> pd.DataFrame:
        cache = CACHE_DIR / f"events_{competition_id}_{season_id}.pkl"
        if cache.exists() and not refresh:
            return pd.read_pickle(cache)

        match_ids = self.matches(competition_id, season_id)["match_id"].tolist()
        frames = []
        for i, match_id in enumerate(match_ids, 1):
            try:
                df = sb.events(match_id=match_id)
            except requests.exceptions.HTTPError as exc:
                # hueco puntual en los open data (fichero ausente/corrupto para
                # este partido): mejor perder un partido que tumbar la competición entera.
                log.warning("eventos no disponibles para el partido %s: %s", match_id, exc)
                continue
            df["match_id"] = match_id
            frames.append(df)
            log.info("eventos %d/%d (partido %s)", i, len(match_ids), match_id)

        if not frames:
            raise RuntimeError(f"ningún partido con eventos disponibles en {competition_id}/{season_id}")
        all_events = pd.concat(frames, ignore_index=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        all_events.to_pickle(cache)
        return all_events

    def minutes_played(
        self,
        competition_id: int,
        season_id: int,
        events_df: pd.DataFrame,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Minutos por jugador desde las alineaciones oficiales (sin periodo 5)."""
        cache = CACHE_DIR / f"minutes_{competition_id}_{season_id}_v2.pkl"
        if cache.exists() and not refresh:
            return pd.read_pickle(cache)

        in_play = events_df[events_df["period"] <= 4]
        end_minute = in_play.groupby("match_id")["minute"].max() + 1

        match_ids = events_df["match_id"].unique().tolist()
        rows = []
        for i, match_id in enumerate(match_ids, 1):
            try:
                lineups = sb.lineups(match_id=match_id)
            except requests.exceptions.HTTPError as exc:
                # mismo hueco puntual que en events(): un partido sin alineación
                # publicada no debe tumbar los minutos de toda la competición.
                log.warning("alineación no disponible para el partido %s: %s", match_id, exc)
                continue
            end = float(end_minute.get(match_id, 95))
            for team, lineup in lineups.items():
                for _, p in lineup.iterrows():
                    positions = p.get("positions") or []
                    if not positions:
                        continue
                    mins = 0.0
                    for pos in positions:
                        start = _clock_to_min(pos["from"])
                        stop = _clock_to_min(pos["to"]) if pos.get("to") else end
                        mins += max(0.0, stop - start)
                    nick = p.get("player_nickname")
                    rows.append(
                        {
                            "player": p["player_name"],
                            "nickname": nick if isinstance(nick, str) and nick else p["player_name"],
                            "team": team,
                            "match_id": match_id,
                            "minutes": mins,
                            "lineup_position": positions[0]["position"],
                        }
                    )
            log.info("alineaciones %d/%d", i, len(match_ids))

        if not rows:
            raise RuntimeError(f"ninguna alineación disponible en {competition_id}/{season_id}")
        per_match = pd.DataFrame(rows)
        out = per_match.groupby(["player", "team"], as_index=False).agg(
            nickname=("nickname", "first"),
            minutes=("minutes", "sum"),
            lineup_position=("lineup_position", "first"),
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        out.to_pickle(cache)
        return out
