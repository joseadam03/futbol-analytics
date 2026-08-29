"""Fotos de jugadores vía TheSportsDB, con caché en disco.

Busca por el apodo del jugador (p. ej. "Lionel Messi") y cachea el
resultado. Si no hay foto o el servicio no responde (red, Cloudflare),
devuelve None y la interfaz lo maneja sin romper nada.
"""

from __future__ import annotations

import json

from . import paths, tsdb

CACHE_FILE = paths.CACHE_DIR / "photos.json"


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


def photo_url(name: str) -> str | None:
    """URL de la foto (recorte transparente si existe) o None."""
    cache = _load_cache()
    if name in cache:
        return cache[name]

    try:
        fichas = tsdb.search_players(name)
    except tsdb.ServiceUnavailable:
        return None  # fallo transitorio: no cachear, se reintentará

    url = next((f["foto"] for f in fichas if f["foto"]), None)
    cache[name] = url  # una respuesta válida sin foto sí se cachea
    _save_cache(cache)
    return url
