"""Estadísticas de temporada vía Sportmonks (fuera del contrato Provider).

Sportmonks da algo genuinamente distinto a StatsBomb/Wyscout: su endpoint
de eventos (`/fixtures/{id}?include=events`) es un *timeline* de incidencias
(goles, tarjetas, cambios) — verificado con datos reales: 18 eventos en todo
un partido, ninguno con coordenadas. No sirve para radares, mapas de calor
ni el modelo de xG, que necesitan saber dónde ocurrió cada toque de balón.

Lo que sí trae, y verificado también con datos reales (Franculino Djú,
Superliga danesa, 4 temporadas), son **estadísticas de temporada por
jugador**: goles, asistencias, minutos, apariciones, tarjetas... Eso es
justo lo que le falta a la ficha de un jugador fuera de los open data —
hoy solo tiene biografía de TheSportsDB, ni un número de rendimiento.

Por eso este módulo vive fuera de `providers/`: no implementa `events()`
(no hay eventos con coordenadas que mapear), así que forzarlo al contrato
`Provider` sería fingir una cobertura que no existe. Es un servicio de
ficha, como `tsdb.py`, no un proveedor de datos de partido.

Esquema verificado en `/players/{id}?include=statistics.details.type`:
cada jugador trae un bloque de estadísticas por (equipo, temporada), y
cada bloque una lista de `details` con `type.name` (p. ej. "Goals",
"Minutes Played") y `value` (un dict, normalmente con clave "total").
"""

from __future__ import annotations

import json
import logging
import os

import requests

from .paths import CACHE_DIR

log = logging.getLogger(__name__)

API_BASE = "https://api.sportmonks.com/v3/football"
CACHE_FILE = CACHE_DIR / "sportmonks_players.json"
TIMEOUT = 15

# nombre de la estadística (tal y como la nombra Sportmonks) -> clave interna
STAT_MAP = {
    "Goals": "goals",
    "Assists": "assists",
    "Minutes Played": "minutes",
    "Appearances": "appearances",
    "Lineups": "lineups",
    "Yellowcards": "yellow_cards",
    "Redcards": "red_cards",
    "Goals Conceded": "goals_conceded",
    "Cleansheets": "clean_sheets",
}
STAT_LABELS = {
    "goals": "Goles",
    "assists": "Asistencias",
    "minutes": "Minutos",
    "appearances": "Apariciones",
    "lineups": "Titularidades",
    "yellow_cards": "Tarjetas amarillas",
    "red_cards": "Tarjetas rojas",
    "goals_conceded": "Goles encajados",
    "clean_sheets": "Porterías a cero",
}


class ServiceUnavailable(RuntimeError):
    """La API no responde, o rechaza la petición (token inválido, plan sin acceso)."""


def available() -> bool:
    return bool(os.environ.get("SPORTMONKS_API_TOKEN"))


def _get(path: str, **params) -> dict:
    token = os.environ.get("SPORTMONKS_API_TOKEN", "")
    if not token:
        raise ServiceUnavailable("Falta SPORTMONKS_API_TOKEN")
    params["api_token"] = token
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ServiceUnavailable(f"error de red: {exc}") from exc
    if resp.status_code != 200:
        raise ServiceUnavailable(f"HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ServiceUnavailable("el cuerpo no es JSON") from exc


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
        pass  # sin caché en disco el servicio sigue funcionando


def search_players(name: str) -> list[dict]:
    """Jugadores cuyo nombre casa con la búsqueda (fichas mínimas, sin estadísticas)."""
    data = _get(f"/players/search/{name}")
    candidatos = data.get("data") or []
    if not isinstance(candidatos, list):
        return []
    return [
        {
            "id": c.get("id"),
            "nombre": c.get("display_name") or c.get("name"),
            "nacimiento": c.get("date_of_birth"),
            "foto": c.get("image_path"),
        }
        for c in candidatos
        if isinstance(c, dict) and c.get("id") is not None
    ]


def _stat_value(detalle: dict) -> float | None:
    valor = detalle.get("value")
    if isinstance(valor, dict):
        total = valor.get("total")
        return float(total) if isinstance(total, (int, float)) else None
    return float(valor) if isinstance(valor, (int, float)) else None


def _extract_seasons_from_payload(data: dict) -> list[dict]:
    """Parsea la respuesta de /players/{id} a filas por (equipo, temporada).

    Separado de la llamada HTTP para poder testear el parseo con payloads
    sintéticos sin red.
    """
    ficha = data.get("data") or {}
    bloques = ficha.get("statistics") or []
    if not isinstance(bloques, list):
        return []

    filas = []
    for bloque in bloques:
        if not isinstance(bloque, dict):
            continue
        temporada = bloque.get("season") or {}
        fila: dict = {
            "season_id": bloque.get("season_id"),
            "season_name": temporada.get("name") or str(bloque.get("season_id", "")),
            "team_id": bloque.get("team_id"),
        }
        for detalle in bloque.get("details") or []:
            if not isinstance(detalle, dict):
                continue
            nombre = (detalle.get("type") or {}).get("name")
            clave = STAT_MAP.get(nombre) if isinstance(nombre, str) else None
            if clave:
                fila[clave] = _stat_value(detalle)
        filas.append(fila)
    return filas


def player_seasons(player_id: int) -> list[dict]:
    """Estadísticas por temporada de un jugador: una fila por (equipo, temporada)."""
    data = _get(f"/players/{player_id}", include="statistics.details.type;statistics.season")
    return _extract_seasons_from_payload(data)


def player_ficha(name: str) -> dict | None:
    """Ficha con estadísticas de temporada del primer jugador que case con `name`.

    Cachea por nombre de búsqueda: una respuesta válida (con o sin
    temporadas) se guarda; un fallo transitorio no se cachea, para
    reintentarlo en otra ejecución.
    """
    cache = _load_cache()
    if name in cache:
        return cache[name]

    candidatos = search_players(name)
    if not candidatos:
        cache[name] = None
        _save_cache(cache)
        return None

    jugador = candidatos[0]
    temporadas = player_seasons(int(jugador["id"]))
    ficha = {**jugador, "temporadas": temporadas}
    cache[name] = ficha
    _save_cache(cache)
    return ficha
