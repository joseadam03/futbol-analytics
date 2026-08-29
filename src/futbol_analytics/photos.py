"""Fotos de jugadores vía TheSportsDB (API gratuita, uso no comercial).

Busca por el apodo del jugador (p. ej. "Lionel Messi") y cachea el
resultado en disco. Si no hay foto, falla la red o Cloudflare intercepta
la petición (rate limit / challenge devuelven HTML en vez de JSON),
devuelve None y la interfaz lo maneja sin romper nada.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

API = "https://www.thesportsdb.com/api/v1/json/3/searchplayers.php"
CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "cache" / "photos.json"

# TheSportsDB sirve detrás de Cloudflare, que suele retar al User-Agent
# por defecto de python-requests; nos identificamos como aplicación.
HEADERS = {
    "User-Agent": "futbol-analytics/0.1 (+https://github.com/joseadam03/futbol-analytics)",
    "Accept": "application/json",
}
TIMEOUT = 6

# Circuito de corte: si la API no responde (caída, rate limit, challenge),
# dejamos de insistir el resto del proceso. Sin esto, una tabla de 10
# similares encadena 10 timeouts de 6 s y la interfaz parece colgada.
_MAX_CONSECUTIVE_FAILURES = 2
_consecutive_failures = 0


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


def _fetch(name: str) -> tuple[str | None, bool]:
    """Devuelve (url, respuesta_valida).

    respuesta_valida=False marca un fallo transitorio (red, bloqueo de
    Cloudflare, cuerpo inesperado): no se cachea, para reintentarlo en
    otra ejecución. Una respuesta válida sin foto sí se cachea como None.
    """
    try:
        resp = requests.get(API, params={"p": name}, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None, False
    # Cloudflare responde a los bloqueos con 403/429/503 y una página HTML.
    if resp.status_code != 200:
        return None, False
    try:
        payload = resp.json()
    except ValueError:
        return None, False
    if not isinstance(payload, dict):
        return None, False
    players = payload.get("player") or []
    if not isinstance(players, list):
        return None, False
    for p in players:
        if not isinstance(p, dict) or p.get("strSport") != "Soccer":
            continue
        candidate = p.get("strCutout") or p.get("strThumb")
        if candidate:
            return candidate, True
    return None, True


def photo_url(name: str) -> str | None:
    """URL de la foto (recorte transparente si existe) o None."""
    global _consecutive_failures

    cache = _load_cache()
    if name in cache:
        return cache[name]

    if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        return None

    url, valid = _fetch(name)
    if not valid:
        _consecutive_failures += 1
        return None

    _consecutive_failures = 0
    cache[name] = url
    _save_cache(cache)
    return url
