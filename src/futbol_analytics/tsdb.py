"""Cliente de TheSportsDB (API gratuita, uso no comercial).

Es el único servicio externo de la app que sirve detrás de Cloudflare:
todas las peticiones pasan por aquí, con validación estricta de la
respuesta (un challenge o un rate limit devuelven HTML, no JSON) y un
circuito de corte que deja de insistir cuando el servicio no responde.
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.thesportsdb.com/api/v1/json/3/searchplayers.php"
TEAM_SEARCH_URL = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"

# Cloudflare suele retar al User-Agent por defecto de python-requests;
# nos identificamos como aplicación.
HEADERS = {
    "User-Agent": "futbol-analytics/0.1 (+https://github.com/joseadam03/futbol-analytics)",
    "Accept": "application/json",
}
TIMEOUT = 6

# Sin este corte, una vista que pide 10 fotos seguidas encadena 10
# timeouts de 6 s con el servicio caído y la interfaz parece colgada.
_MAX_CONSECUTIVE_FAILURES = 2
_consecutive_failures = 0


class ServiceUnavailable(RuntimeError):
    """El servicio no responde: caída, rate limit o challenge de Cloudflare."""


def _get_json(url: str, params: dict) -> dict:
    global _consecutive_failures

    if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        raise ServiceUnavailable("circuito abierto tras fallos consecutivos")

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        _consecutive_failures += 1
        raise ServiceUnavailable(f"error de red: {exc}") from exc

    # Cloudflare responde a los bloqueos con 403/429/503 y una página HTML.
    if resp.status_code != 200:
        _consecutive_failures += 1
        raise ServiceUnavailable(f"HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        _consecutive_failures += 1
        raise ServiceUnavailable("el cuerpo no es JSON (¿challenge de Cloudflare?)") from exc
    if not isinstance(payload, dict):
        _consecutive_failures += 1
        raise ServiceUnavailable("estructura JSON inesperada")

    _consecutive_failures = 0
    return payload


def search_players(name: str) -> list[dict]:
    """Fichas de los futbolistas que casan con el nombre buscado.

    Devuelve una lista (posiblemente vacía) de fichas normalizadas.
    Lanza ServiceUnavailable si el servicio está caído o bloqueando;
    el llamante decide si degradar en silencio o avisar al usuario.
    """
    payload = _get_json(SEARCH_URL, {"p": name})
    players = payload.get("player") or []
    if not isinstance(players, list):
        log.warning("respuesta inesperada de TheSportsDB para %r", name)
        return []

    fichas = []
    for p in players:
        if not isinstance(p, dict) or p.get("strSport") != "Soccer":
            continue
        fichas.append(
            {
                "nombre": p.get("strPlayer"),
                "equipo": p.get("strTeam"),
                "posicion": p.get("strPosition"),
                "nacionalidad": p.get("strNationality"),
                "nacimiento": p.get("dateBorn"),
                "lugar_nacimiento": p.get("strBirthLocation"),
                "altura": p.get("strHeight"),
                "estado": p.get("strStatus"),
                "descripcion": p.get("strDescriptionEN"),
                "foto": p.get("strCutout") or p.get("strThumb"),
            }
        )
    return fichas


def search_teams(name: str) -> list[dict]:
    """Equipos que casan con el nombre buscado, con su escudo si existe.

    Devuelve una lista (posiblemente vacía) de fichas normalizadas.
    Lanza ServiceUnavailable si el servicio está caído o bloqueando;
    el llamante decide si degradar en silencio o avisar al usuario.
    """
    payload = _get_json(TEAM_SEARCH_URL, {"t": name})
    equipos = payload.get("teams") or []
    if not isinstance(equipos, list):
        log.warning("respuesta inesperada de TheSportsDB para equipo %r", name)
        return []

    fichas = []
    for t in equipos:
        if not isinstance(t, dict) or t.get("strSport") != "Soccer":
            continue
        fichas.append(
            {
                "nombre": t.get("strTeam"),
                "escudo": t.get("strTeamBadge") or t.get("strBadge"),
            }
        )
    return fichas
