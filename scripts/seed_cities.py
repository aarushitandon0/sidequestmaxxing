"""Seed `places` for several cities in one polite run (P24).

Why this exists: `places` is filled offline, and nothing fetches OSM on a request path, so a
player outside a seeded bounding box gets zero candidates from the Scout — every time, by
design (docs/DECISIONS.md D-84). More seeded cities is the cheap half of the fix; the quest
library in `app/agents/templates.py` is the other half.

Usage (repo root, API venv):
    python scripts/seed_cities.py --dry-run             # fetch + count, no DB writes
    python scripts/seed_cities.py                       # fetch + embed + upsert all cities
    python scripts/seed_cities.py --only pune london    # just these
    python scripts/seed_cities.py --from-cache          # re-run on cached payloads, no network

This is a thin loop over `seed_places.main`, so caching, parsing, embedding and the upsert all
stay in one place. Embedding is local (fastembed, CPU) and costs nothing but time.

Fair use: ONE Overpass request per city, strictly sequential, with a delay between them and a
descriptive User-Agent. Overpass is free and volunteer-run; do not parallelise this.
Data (c) OpenStreetMap contributors (ODbL).

The boxes below are approximate central boxes, not administrative boundaries — a bbox only has
to cover the walkable core. The place count each one prints is the real check: a city coming
back with very few named places wants a wider box, and the script says so.
"""

import argparse
import logging
import sys
import time

import _bootstrap  # noqa: F401  (puts apps/api on sys.path)
import seed_places

log = logging.getLogger("seed_cities")

#: city -> "S,W,N,E". Ordered with the demo city first.
CITIES: dict[str, str] = {
    "pune": "18.45,73.75,18.60,73.95",
    "mumbai": "18.90,72.77,19.27,72.98",
    "delhi": "28.52,77.10,28.70,77.30",
    "bengaluru": "12.89,77.52,13.05,77.70",
    "london": "51.44,-0.25,51.58,0.02",
    "new-york": "40.68,-74.03,40.82,-73.90",
    "san-francisco": "37.73,-122.52,37.81,-122.38",
    "berlin": "52.46,13.30,52.56,13.47",
    "toronto": "43.62,-79.47,43.72,-79.32",
    "sydney": "-33.92,151.15,-33.82,151.28",
    "singapore": "1.25,103.78,1.40,103.90",
    "dubai": "25.17,55.20,25.30,55.35",
}

DEFAULT_DELAY_S = 15.0  # 5s earned a 429 from the public instance


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", metavar="CITY", help=f"subset of {sorted(CITIES)}")
    parser.add_argument("--dry-run", action="store_true", help="fetch and count, no DB writes")
    parser.add_argument("--from-cache", action="store_true", help="no network; reuse data/*.json")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_S)
    parser.add_argument("--overpass-url", default=None)
    args = parser.parse_args(argv)

    chosen = list(CITIES)
    if args.only:
        unknown = [c for c in args.only if c not in CITIES]
        if unknown:
            log.error("unknown cities: %s (known: %s)", unknown, sorted(CITIES))
            return 2
        chosen = [c for c in CITIES if c in args.only]

    failed: list[str] = []
    for i, city in enumerate(chosen):
        log.info("")
        log.info("--- %s (%d/%d) ---", city, i + 1, len(chosen))
        # `--bbox=-33.92,...` and not `--bbox -33.92,...`: argparse reads a leading
        # minus as the next flag, which is how Sydney broke the first run.
        call = ["--city", city, f"--bbox={CITIES[city]}"]
        if args.dry_run:
            call.append("--dry-run")
        if args.from_cache:
            call.append("--from-cache")
        if args.overpass_url:
            call += ["--overpass-url", args.overpass_url]
        try:
            code = seed_places.main(call)
        except SystemExit as exc:  # argparse bails this way; it is not an Exception
            log.error("%s rejected its arguments (exit %s)", city, exc.code)
            failed.append(city)
            continue
        except Exception as exc:  # one bad city must not lose the other eleven
            log.error("%s failed: %s: %s", city, type(exc).__name__, exc)
            failed.append(city)
            continue
        if code != 0:
            log.error("%s exited %d", city, code)
            failed.append(city)
        # Be a good Overpass citizen: space the requests out, but not after the last one
        # and not when nothing was fetched.
        if not args.from_cache and i < len(chosen) - 1:
            time.sleep(args.delay)

    log.info("")
    log.info("seeded %d/%d cities", len(chosen) - len(failed), len(chosen))
    if failed:
        log.error("failed: %s — re-run with --only %s", failed, " ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
