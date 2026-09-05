"""Escudos de equipo vía TheSportsDB, con caché en disco.

Mismo patrón que `photos.py` pero para equipos en vez de jugadores: busca
por el nombre del equipo y cachea la URL del escudo. Sin escudo o con el
servicio caído (red, Cloudflare), devuelve None y el informe se genera
igual, sin él.
"""

from __future__ import annotations

import json

from . import paths, tsdb

CACHE_FILE = paths.CACHE_DIR / "crests.json"


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError:
        pass  # sin caché en disco la app sigue funcionando


def crest_url(team: str) -> str | None:
    """URL del escudo del equipo, o None si no se encuentra o el servicio falla."""
    cache = _load_cache()
    if team in cache:
        return cache[team]

    try:
        equipos = tsdb.search_teams(team)
    except tsdb.ServiceUnavailable:
        return None  # fallo transitorio: no cachear, se reintentará

    url = next((e["escudo"] for e in equipos if e["escudo"]), None)
    cache[team] = url  # una respuesta válida sin escudo sí se cachea
    _save_cache(cache)
    return url
