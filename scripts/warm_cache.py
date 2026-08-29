"""Precalienta la caché de datos: descarga y cachea una competición entera.

Útil antes de una demo o al construir un despliegue: la primera carga de
una competición tarda varios minutos y con la caché caliente es
instantánea.

Uso:
    python scripts/warm_cache.py                        # Mundial 2022
    python scripts/warm_cache.py --competition 72 --season 107
"""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

from futbol_analytics.providers import get_provider


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="  %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="statsbomb", help="Proveedor de datos")
    parser.add_argument("--competition", type=int, default=43, help="competition_id")
    parser.add_argument("--season", type=int, default=106, help="season_id")
    args = parser.parse_args()

    provider = get_provider(args.provider)
    print(f"Descargando eventos ({args.provider}, {args.competition}/{args.season})...")
    events = provider.events(args.competition, args.season)
    print("Calculando minutos jugados...")
    provider.minutes_played(args.competition, args.season, events)
    print(f"Listo: {len(events)} eventos en caché. La app cargará al instante.")


if __name__ == "__main__":
    main()
