"""Verifica el mapeo de Wyscout contra un partido real.

El mapeo de `providers/wyscout.py` está escrito contra el esquema
documentado de la API v3 y cubierto por tests con payloads sintéticos, pero
nadie lo ha ejecutado nunca sobre datos de verdad. Este script es esa
verificación, reducida a un comando: descarga un partido, lo mapea y dice
exactamente qué encaja y qué no.

Uso (con WYSCOUT_CLIENT_ID / WYSCOUT_CLIENT_SECRET en el entorno o en .env):

    python scripts/verify_wyscout.py --season 12345          # primer partido
    python scripts/verify_wyscout.py --match 5555555         # uno concreto
    python scripts/verify_wyscout.py --season 12345 --json informe.json

Qué revisa:
- **Tipos sin mapear**: los `primaryType` que se descartan y cuántos son.
  Si aquí aparece algo frecuente, falta una entrada en TYPE_MAP.
- **Cobertura de campos**: qué porcentaje de cada columna del esquema común
  llega con valor. Un pase sin destino o un tiro sin xG delatan un nombre
  de campo cambiado.
- **Rangos de coordenadas**: deben caer en 0-120 x 0-80 tras la conversión.
  Fuera de rango = la API ya no manda porcentajes.
- **Coherencia del esquema**: que las métricas se puedan calcular encima.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from dotenv import load_dotenv

from futbol_analytics import metrics
from futbol_analytics.providers.wyscout import TYPE_MAP, WyscoutProvider

# columnas del esquema común y si su ausencia total es sospechosa
CAMPOS_CLAVE = {
    "type": True,
    "location": True,
    "team": True,
    "player": True,
    "period": True,
    "pass_end_location": True,
    "pass_outcome": False,
    "pass_type": False,
    "shot_statsbomb_xg": True,
    "shot_outcome": True,
    "carry_end_location": False,
    "duel_type": False,
    "possession": True,
}


def _tipos_sin_mapear(raw: dict) -> Counter:
    """primaryType presentes en el payload que el mapeo descarta."""
    contador: Counter = Counter()
    for ev in raw.get("events") or []:
        if not isinstance(ev, dict):
            continue
        primario = str((ev.get("type") or {}).get("primary") or "")
        if primario and primario not in TYPE_MAP:
            contador[primario] += 1
    return contador


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, help="season_id del que tomar el primer partido")
    parser.add_argument("--match", type=int, help="match_id concreto a verificar")
    parser.add_argument("--json", help="Guardar el informe en este fichero JSON")
    args = parser.parse_args()

    if not args.season and not args.match:
        raise SystemExit("Indica --season o --match.")

    provider = WyscoutProvider()
    if not provider.available():
        raise SystemExit(
            "Faltan credenciales: define WYSCOUT_CLIENT_ID y WYSCOUT_CLIENT_SECRET "
            "(en el entorno o en un fichero .env). Copia .env.example para empezar."
        )

    match_id = args.match
    if match_id is None:
        ids = provider._season_matches(args.season)
        if not ids:
            raise SystemExit(f"La temporada {args.season} no devolvió partidos.")
        match_id = int(ids[0])

    print(f"Descargando el partido {match_id}...")
    raw = provider._get(f"/matches/{match_id}/events")
    n_crudos = len(raw.get("events") or [])
    df = provider._map_events(raw, match_id)

    informe: dict = {
        "match_id": match_id,
        "eventos_api": n_crudos,
        "eventos_mapeados": int(len(df)),
        "descartados": int(n_crudos - len(df)),
    }
    print(f"\nEventos: {n_crudos} en la API -> {len(df)} mapeados ({informe['descartados']} descartados)")

    sin_mapear = _tipos_sin_mapear(raw)
    informe["tipos_sin_mapear"] = dict(sin_mapear)
    if sin_mapear:
        print("\nTipos sin mapear (añádelos a TYPE_MAP si son relevantes):")
        for tipo, n in sin_mapear.most_common(15):
            print(f"  {tipo:28s} {n:5d}")
    else:
        print("\nTodos los primaryType del partido están contemplados.")

    print("\nCobertura de campos del esquema común:")
    cobertura: dict[str, float | None] = {}
    problemas = []
    for campo, exigido in CAMPOS_CLAVE.items():
        if campo not in df.columns:
            cobertura[campo] = None
            problemas.append(f"falta la columna {campo}")
            print(f"  {campo:22s} AUSENTE")
            continue
        pct = 100 * float(df[campo].notna().mean()) if len(df) else 0.0
        cobertura[campo] = round(pct, 1)
        marca = ""
        if exigido and pct == 0.0:
            marca = "  <-- vacío del todo, revisa el nombre del campo"
            problemas.append(f"{campo} llega siempre vacío")
        print(f"  {campo:22s} {pct:5.1f} %{marca}")
    informe["cobertura"] = cobertura

    print("\nRangos de coordenadas (deben ser 0-120 x 0-80):")
    locs = df["location"].dropna() if "location" in df.columns else []
    if len(locs):
        xs = [p[0] for p in locs]
        ys = [p[1] for p in locs]
        informe["x_range"] = [round(min(xs), 1), round(max(xs), 1)]
        informe["y_range"] = [round(min(ys), 1), round(max(ys), 1)]
        print(f"  x: {min(xs):.1f} a {max(xs):.1f}")
        print(f"  y: {min(ys):.1f} a {max(ys):.1f}")
        if max(xs) > 120.5 or max(ys) > 80.5 or min(xs) < 0 or min(ys) < 0:
            problemas.append("coordenadas fuera de rango: ¿ya no vienen en porcentaje?")
            print("  <-- fuera de rango: revisa X_SCALE / Y_SCALE")
    else:
        problemas.append("ningún evento trae localización")
        print("  sin coordenadas")

    print("\nComprobación de tiros:")
    tiros = df[df["type"] == "Shot"] if "type" in df.columns else df.iloc[:0]
    informe["tiros"] = int(len(tiros))
    informe["tiros_con_xg"] = int(tiros["shot_statsbomb_xg"].notna().sum()) if len(tiros) else 0
    informe["tiros_con_pase_clave"] = int(tiros["shot_key_pass_id"].notna().sum()) if len(tiros) else 0
    print(
        f"  {len(tiros)} tiros | {informe['tiros_con_xg']} con xG | "
        f"{informe['tiros_con_pase_clave']} enlazados a su pase clave"
    )
    if len(tiros) and informe["tiros_con_pase_clave"] == 0:
        problemas.append("ningún tiro se enlazó con su pase clave (revisa possession.id)")

    print("\nLas métricas se calculan sobre lo mapeado:")
    try:
        minutos = provider._map_formations(
            provider._get(f"/matches/{match_id}/formations"),
            match_id,
            float(df[df["period"] <= 4]["minute"].max() or 95) + 1,
        )
        import pandas as pd

        per_match = pd.DataFrame(minutos)
        mins = per_match.groupby(["player", "team"], as_index=False).agg(
            nickname=("nickname", "first"),
            minutes=("minutes", "sum"),
            lineup_position=("lineup_position", "first"),
        )
        tabla = metrics.player_metrics(df, mins, min_minutes=0)
        informe["jugadores"] = int(len(tabla))
        informe["minutos_totales"] = round(float(mins["minutes"].sum()), 1)
        print(f"  {len(tabla)} jugadores | {mins['minutes'].sum():.0f} minutos repartidos")
        if len(tabla):
            top = tabla.nlargest(3, "npxg")[["player", "team", "npxg", "passes_cmp"]]
            print(top.to_string(index=False))
        if not 1500 < mins["minutes"].sum() < 2600:
            problemas.append(
                f"los minutos totales ({mins['minutes'].sum():.0f}) no cuadran con un "
                "partido de 22 jugadores (~1980); revisa _map_formations"
            )
    except Exception as exc:  # el objetivo es diagnosticar, no petar
        problemas.append(f"fallo al calcular métricas: {type(exc).__name__}: {exc}")
        print(f"  ERROR: {type(exc).__name__}: {exc}")

    informe["problemas"] = problemas
    print("\n" + "=" * 60)
    if problemas:
        print(f"{len(problemas)} cosa(s) que revisar:")
        for p in problemas:
            print(f"  - {p}")
    else:
        print("Sin incidencias: el mapeo encaja con los datos reales.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(informe, fh, ensure_ascii=False, indent=2)
        print(f"\nInforme guardado en {args.json}")

    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
