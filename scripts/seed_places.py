"""Seed `places` from OpenStreetMap via Overpass, embed, upsert (MASTERSPEC §7.2).

Usage (repo root):
    python scripts/seed_places.py --bbox "18.45,73.75,18.60,73.95" --city pune
    python scripts/seed_places.py --city pune --from-cache      # reuse data/overpass_pune.json
    python scripts/seed_places.py --bbox ... --city pune --dry-run   # no DB writes

Fair use: ONE Overpass request per run, descriptive User-Agent, raw response cached locally.
Data © OpenStreetMap contributors (ODbL).
"""

import argparse
import json
import logging
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import _bootstrap
import httpx
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError

from app.config import Settings
from app.services.embeddings import FastEmbedder
from app.services.osm import overpass_query, parse_bbox, places_from_overpass

log = logging.getLogger("seed_places")
DATA_DIR = _bootstrap.REPO_ROOT / "data"
DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "Sidequestmaxxing/0.1 (open-source hackathon project; one-off seed script)"


def slug(city: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-") or "city"


def fetch_overpass(url: str, query: str) -> dict[str, Any]:
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=15.0)) as client:
        res = client.post(url, data={"data": query}, headers={"User-Agent": USER_AGENT})
        res.raise_for_status()
        payload: dict[str, Any] = res.json()
    return payload


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", help="S,W,N,E")
    parser.add_argument("--city", required=True)
    parser.add_argument("--from-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overpass-url", default=None)
    args = parser.parse_args(argv)

    settings = Settings()
    cache = DATA_DIR / f"overpass_{slug(args.city)}.json"

    if args.from_cache:
        if not cache.exists():
            log.error("no cache at %s", cache)
            return 2
        payload = json.loads(cache.read_text())
    else:
        if not args.bbox:
            log.error("--bbox is required unless --from-cache")
            return 2
        bbox = parse_bbox(args.bbox)
        url = args.overpass_url or DEFAULT_OVERPASS
        log.info("querying Overpass once for bbox %s ...", bbox)
        payload = fetch_overpass(url, overpass_query(bbox))
        DATA_DIR.mkdir(exist_ok=True)
        cache.write_text(json.dumps(payload))
        log.info("cached raw response → %s", cache.relative_to(_bootstrap.REPO_ROOT))

    places = places_from_overpass(payload, fetched_at=datetime.now(UTC))
    kinds = Counter(p["kind"] for p in places)
    log.info("%d named public places: %s", len(places), dict(kinds.most_common()))
    if len(places) < 150:
        log.warning("fewer than 150 places (PROJECTPLAN §5 target); consider a larger bbox")

    if args.dry_run:
        return 0
    if not settings.mongodb_uri:
        log.error("MONGODB_URI is not set")
        return 2

    log.info("embedding %d texts with %s ...", len(places), settings.embedding_model)
    vectors = FastEmbedder(settings.embedding_model).embed_sync([p["text"] for p in places])
    for place, vector in zip(places, vectors, strict=True):
        place["embedding"] = vector

    client: MongoClient[dict[str, Any]] = MongoClient(
        settings.mongodb_uri, appname="sqm-scripts", serverSelectionTimeoutMS=10000
    )
    try:
        ops = [UpdateOne({"_id": p["_id"]}, {"$set": p}, upsert=True) for p in places]
        result = client[settings.mongodb_db]["places"].bulk_write(ops, ordered=False)
        log.info("upserted=%d modified=%d", result.upserted_count, result.modified_count)
    except PyMongoError as exc:
        log.error("MongoDB error: %s", type(exc).__name__)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
