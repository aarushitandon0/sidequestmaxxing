"""Verify each seeded city the way the Scout sees it (P24).

A place count from the seed script only proves Overpass answered. This proves the Scout will
find something for a player standing at that city centre, because it counts exactly what
`search_places` pre-filters on: the 3x3 geohash-5 block around the point (`cells_around`).

Usage (repo root, API venv):
    python scripts/check_cities.py

Exits non-zero if any city in the web app's picker has no places behind it — the failure mode
docs/DECISIONS.md D-94 warns about, where the UI promises real places and delivers none.
"""

import logging
import sys
from typing import Any

import _bootstrap  # noqa: F401  (puts apps/api on sys.path)
from pymongo import MongoClient
from seed_cities import CITIES

from app.config import Settings
from app.services.geo import cells_around
from app.services.osm import parse_bbox

log = logging.getLogger("check_cities")

#: Below this, a city is seeded too thinly to reliably produce a place-based quest.
THIN = 50


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()
    if not settings.mongodb_uri:
        log.error("MONGODB_URI is not set (run from the repo root so .env is found)")
        return 2

    client: MongoClient[dict[str, Any]] = MongoClient(
        settings.mongodb_uri, appname="sqm-scripts", serverSelectionTimeoutMS=10000
    )
    try:
        places = client[settings.mongodb_db]["places"]
        total = places.count_documents({})
        log.info("%d places in the collection", total)
        log.info("")
        log.info("%-16s %8s  %s", "city", "in cells", "kinds at the centre")

        empty: list[str] = []
        thin: list[str] = []
        for city, raw in CITIES.items():
            south, west, north, east = parse_bbox(raw)
            lat, lng = (south + north) / 2, (west + east) / 2
            cells = cells_around(lat, lng)
            count = places.count_documents({"cell5": {"$in": cells}})
            kinds = sorted(places.distinct("kind", {"cell5": {"$in": cells}}))
            log.info("%-16s %8d  %s", city, count, ", ".join(kinds) or "-")
            if count == 0:
                empty.append(city)
            elif count < THIN:
                thin.append(city)

        log.info("")
        if thin:
            log.warning("thin (<%d places at the centre): %s", THIN, thin)
        if empty:
            log.error("NO places at the centre of: %s", empty)
            log.error("remove these from SEEDED_CITIES in apps/web/src/lib/cities.ts, or seed them")
            return 1
        log.info("every city in the picker has places behind it")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
