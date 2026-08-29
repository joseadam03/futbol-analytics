"""Genera el informe completo de un jugador: radar, mapas y similares.

Uso:
    python scripts/player_report.py --player "Messi"
    python scripts/player_report.py --player "Bellingham" --competition 43 --season 106

Por defecto usa el Mundial 2022 (competition 43, season 106). La primera
ejecución descarga y cachea los datos (~3-5 min); las siguientes son
instantáneas.
"""

from __future__ import annotations

import argparse
import unicodedata
from pathlib import Path

from futbol_analytics import metrics, similarity, viz
from futbol_analytics.providers import get_provider

ROOT = Path(__file__).resolve().parents[1]


def slugify(name: str) -> str:
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "_".join(norm.split())


def find_player(names: list[str], query: str) -> str:
    q = query.lower()
    hits = sorted({n for n in names if q in n.lower()})
    if not hits:
        raise SystemExit(f"No hay ningún jugador que contenga '{query}'.")
    if len(hits) > 1:
        listado = "\n  - ".join(hits)
        raise SystemExit(f"Varios jugadores coinciden con '{query}':\n  - {listado}")
    return hits[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player", required=True, help="Nombre (o parte) del jugador")
    parser.add_argument("--competition", type=int, default=43, help="competition_id de StatsBomb")
    parser.add_argument("--season", type=int, default=106, help="season_id de StatsBomb")
    parser.add_argument("--min-minutes", type=float, default=180, help="Mínimo de minutos para percentiles")
    parser.add_argument("--refresh", action="store_true", help="Ignorar caché y volver a descargar")
    args = parser.parse_args()

    provider = get_provider("statsbomb")
    comps = provider.competitions()
    row = comps[
        (comps["competition_id"] == args.competition) & (comps["season_id"] == args.season)
    ]
    if row.empty:
        raise SystemExit("Esa competición/temporada no está en los open data de StatsBomb.")
    comp_label = f"{row.iloc[0]['competition_name']} {row.iloc[0]['season_name']}"

    print(f"Cargando eventos de {comp_label}...")
    events = provider.events(args.competition, args.season, refresh=args.refresh)
    print("Calculando minutos jugados...")
    minutes = provider.minutes_played(args.competition, args.season, events, refresh=args.refresh)

    table = metrics.player_metrics(events, minutes, min_minutes=args.min_minutes)
    pct_cols = [f"{m}_p90" for m in metrics.COUNT_METRICS] + ["pass_pct", "npxg_per_shot"]
    table = metrics.percentiles(table, pct_cols)

    player = find_player(table["player"].tolist(), args.player)
    prow = table[table["player"] == player].iloc[0]

    out_dir = ROOT / "output" / slugify(player)
    print(f"\nJugador: {player} ({prow['team']}, {prow['primary_position']}, {prow['minutes']:.0f} min)")
    print(f"Generando informe en {out_dir}\n")

    viz.save(viz.radar_chart(prow, comp_label), out_dir / "radar.png")
    viz.save(viz.touch_heatmap(events, player, comp_label), out_dir / "mapa_calor.png")
    viz.save(viz.pass_map(events, player, comp_label), out_dir / "mapa_pases.png")
    viz.save(viz.shot_map(events, player, comp_label), out_dir / "mapa_tiros.png")

    sims = similarity.similar_players(table, player)
    sims.to_csv(out_dir / "similares.csv", index=False)
    table.to_csv(ROOT / "output" / "metricas_competicion.csv", index=False)

    resumen = [
        ("Minutos", f"{prow['minutes']:.0f}"),
        ("npxG/90", f"{prow['npxg_p90']:.2f} (p{prow['npxg_p90_pct']:.0f})"),
        ("xA/90", f"{prow['xa_p90']:.2f} (p{prow['xa_p90_pct']:.0f})"),
        ("Pases prog./90", f"{prow['prog_passes_p90']:.2f} (p{prow['prog_passes_p90_pct']:.0f})"),
        ("Conducc. prog./90", f"{prow['prog_carries_p90']:.2f} (p{prow['prog_carries_p90_pct']:.0f})"),
        ("Regates/90", f"{prow['dribbles_cmp_p90']:.2f} (p{prow['dribbles_cmp_p90_pct']:.0f})"),
        ("Presiones/90", f"{prow['pressures_p90']:.2f} (p{prow['pressures_p90_pct']:.0f})"),
        ("PAdj Entr+Int/90", f"{prow['padj_tack_int_p90']:.2f} (p{prow['padj_tack_int_p90_pct']:.0f})"),
    ]
    ancho = max(len(k) for k, _ in resumen)
    print(f"Resumen per-90 (percentil vs. {prow['position_group']}):")
    for k, v in resumen:
        print(f"  {k:<{ancho}}  {v}")

    print("\nJugadores con perfil más similar:")
    for _, s in sims.head(5).iterrows():
        print(f"  {s['similarity']:.3f}  {s['player']} ({s['team']}, {s['primary_position']})")

    print(f"\nListo. Gráficos en {out_dir}")


if __name__ == "__main__":
    main()
