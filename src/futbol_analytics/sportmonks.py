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

También trae traspasos reales ya cerrados —no una estimación de valor de
mercado, un hecho verificable— vía `include=transfers.fromTeam;transfers.toTeam`
(esquema verificado con el mismo jugador: Franculino Djú, Benfica U23 ->
Midtjylland en 2023 sin importe público, Midtjylland -> Trabzonspor en 2026
por 17M). `amount` es `None` cuando el importe no es público; cuando lo es,
se asume EUR (no confirmado en la documentación, pero es el estándar del
sector y de un proveedor europeo).
"""

from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar

import requests

from .paths import CACHE_DIR

log = logging.getLogger(__name__)

API_BASE = "https://api.sportmonks.com/v3/football"
CACHE_FILE = CACHE_DIR / "sportmonks_players.json"
TIMEOUT = 15

# Token del usuario logueado para esta sesión (ver auth.py). Un ContextVar y
# no os.environ: streamlit sirve varias sesiones concurrentes en el mismo
# proceso, y escribir en el entorno filtraría el token de un usuario a las
# peticiones de otro — mismo patrón que providers/statsbomb.py. Sin token de
# sesión, cae a SPORTMONKS_API_TOKEN (el del .env de todo el despliegue).
_TOKEN: ContextVar[str | None] = ContextVar("sportmonks_token", default=None)


def set_session_credentials(token: str) -> None:
    _TOKEN.set(token)


def _token() -> str:
    return _TOKEN.get() or os.environ.get("SPORTMONKS_API_TOKEN", "")


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
    return bool(_token())


def _get(path: str, **params) -> dict:
    token = _token()
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


def _team_name(transfer: dict, prefix: str) -> str | None:
    """Nombre del equipo origen/destino de un traspaso, tolerando ambas grafías del include."""
    bloque = transfer.get(f"{prefix}Team") or transfer.get(f"{prefix}team")
    nombre = bloque.get("name") if isinstance(bloque, dict) else None
    return nombre if isinstance(nombre, str) else None


def _extract_transfers_from_payload(data: dict) -> list[dict]:
    """Parsea la respuesta de /players/{id}?include=transfers.fromTeam;transfers.toTeam.

    Traspasos reales ya cerrados, no una estimación de valor de mercado.
    `importe` es None cuando el dato no es público (no se inventa un número).
    """
    ficha = data.get("data") or {}
    traspasos = ficha.get("transfers") or []
    if not isinstance(traspasos, list):
        return []

    filas = []
    for t in traspasos:
        if not isinstance(t, dict):
            continue
        filas.append(
            {
                "fecha": t.get("date"),
                "origen": _team_name(t, "from"),
                "destino": _team_name(t, "to"),
                "importe": t.get("amount"),
            }
        )
    return filas


def player_transfers(player_id: int) -> list[dict]:
    """Traspasos reales ya cerrados de un jugador, con importe cuando es público."""
    data = _get(f"/players/{player_id}", include="transfers.fromTeam;transfers.toTeam")
    return _extract_transfers_from_payload(data)


def player_bio(name: str) -> dict | None:
    """Altura y pie preferido del primer jugador que case con `name` —
    complementa a tsdb.py cuando TheSportsDB no trae esos campos (pasa
    a menudo con la altura, y el pie preferido no está en ninguna ficha
    de TheSportsDB). `height` es un campo directo del jugador (en cm),
    verificado en la documentación de Sportmonks; el pie preferido vive
    en el include `metadata`, así que se busca por tipo cuyo nombre
    contenga "foot" en vez de una clave exacta — no hay token de prueba
    en este entorno para verificar la respuesta real contra un jugador
    con ese dato relleno.
    """
    candidatos = search_players(name)
    if not candidatos:
        return None
    player_id = int(candidatos[0]["id"])
    data = _get(f"/players/{player_id}", include="metadata.type")
    ficha = data.get("data") or {}
    altura = ficha.get("height")
    pie = None
    for m in ficha.get("metadata") or []:
        if not isinstance(m, dict):
            continue
        tipo = (m.get("type") or {}).get("name")
        if isinstance(tipo, str) and "foot" in tipo.lower():
            pie = m.get("values") or m.get("value")
            break
    return {
        "altura": f"{altura:.0f} cm" if isinstance(altura, (int, float)) else None,
        "pie": str(pie).capitalize() if isinstance(pie, str) and pie else None,
    }


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
    player_id = int(jugador["id"])
    temporadas = player_seasons(player_id)
    traspasos = player_transfers(player_id)
    ficha = {**jugador, "temporadas": temporadas, "traspasos": traspasos}
    cache[name] = ficha
    _save_cache(cache)
    return ficha
