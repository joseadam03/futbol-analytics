"""Proveedor StatsBomb open data, con caché local en data/cache/."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
from statsbombpy import sb

from .base import Provider

# statsbombpy avisa en cada llamada de que se usan open data sin credenciales
warnings.filterwarnings("ignore", module="statsbombpy")

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache"


def _clock_to_min(clock: str) -> float:
    mm, ss = clock.split(":")
    return int(mm) + int(ss) / 60


class StatsBombProvider(Provider):
    name = "StatsBomb (open data)"

    def competitions(self) -> pd.DataFrame:
        return sb.competitions()

    def matches(self, competition_id: int, season_id: int) -> pd.DataFrame:
        return sb.matches(competition_id=competition_id, season_id=season_id)

    def events(self, competition_id: int, season_id: int, refresh: bool = False) -> pd.DataFrame:
        cache = CACHE_DIR / f"events_{competition_id}_{season_id}.pkl"
        if cache.exists() and not refresh:
            return pd.read_pickle(cache)

        match_ids = self.matches(competition_id, season_id)["match_id"].tolist()
        frames = []
        for i, match_id in enumerate(match_ids, 1):
            df = sb.events(match_id=match_id)
            df["match_id"] = match_id
            frames.append(df)
            print(f"  eventos {i}/{len(match_ids)} (partido {match_id})", flush=True)

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
            lineups = sb.lineups(match_id=match_id)
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
                    rows.append(
                        {
                            "player": p["player_name"],
                            "nickname": p.get("player_nickname") or p["player_name"],
                            "team": team,
                            "match_id": match_id,
                            "minutes": mins,
                            "lineup_position": positions[0]["position"],
                        }
                    )
            print(f"  alineaciones {i}/{len(match_ids)}", flush=True)

        per_match = pd.DataFrame(rows)
        out = (
            per_match.groupby(["player", "team"], as_index=False)
            .agg(
                nickname=("nickname", "first"),
                minutes=("minutes", "sum"),
                lineup_position=("lineup_position", "first"),
            )
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        out.to_pickle(cache)
        return out
