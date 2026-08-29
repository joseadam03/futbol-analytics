"""Fotos de jugadores vía TheSportsDB (API gratuita, uso no comercial).

Busca por el apodo del jugador (p. ej. "Lionel Messi") y cachea el
resultado en disco. Si no hay foto o falla la red, devuelve None y la
interfaz lo maneja sin romper nada.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

API = "https://www.thesportsdb.com/api/v1/json/3/searchplayers.php"
CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "cache" / "photos.json"


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def photo_url(name: str) -> str | None:
    """URL de la foto (recorte transparente si existe) o None."""
    cache = _load_cache()
    if name in cache:
        return cache[name]

    url = None
    try:
        resp = requests.get(API, params={"p": name}, timeout=6)
        players = (resp.json() or {}).get("player") or []
        for p in players:
            if p.get("strSport") != "Soccer":
                continue
            candidate = p.get("strCutout") or p.get("strThumb")
            if candidate:
                url = candidate
                break
    except (requests.RequestException, ValueError):
        return None  # fallo transitorio: no cachear

    cache[name] = url
    _save_cache(cache)
    return url
