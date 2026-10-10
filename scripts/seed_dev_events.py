"""Seed a few obviously-fake `events` documents for local development (P23).

Why this exists: the live SerpApi feed for Pune returns almost entirely indoor evening
ticketed entertainment, which the safety funnel correctly rejects, so a developer can run
the real pipeline end to end and still never see a happening. This script fabricates the
missing case - a daytime outdoor event at a place already in `places` - so the read path
(`search_events` -> Scout merge -> V13 -> the quest card's timing chip) can be exercised.

Not production data and not a benchmark. Every document is written with `source="dev-seed"`
and an `_id` under `dev/`, so it is trivially distinguishable from a real `serp/` document
and can be removed with `--clear`. Never claim a metric or a demo result from these.

Usage (repo root, API venv):
    python scripts/seed_dev_events.py --list-places   # candidate anchor places
    python scripts/seed_dev_events.py                 # upsert the dev events
    python scripts/seed_dev_events.py --clear         # remove every dev-seed event
"""

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import _bootstrap  # noqa: F401
from pymongo import AsyncMongoClient, UpdateOne

from app.config import Settings
from app.models.event import EventDoc
from app.services.embeddings import FastEmbedder
from app.services.event_time import overlaps_daylight

log = logging.getLogger("seed_dev_events")

DEV_SOURCE = "dev-seed"
DEV_ID_PREFIX = "dev/"

#: `(id suffix, event title, when_text, offset from now, duration, prefer this place kind)`.
#:
#: `minutes_available` caps at 180, and `search_events` only returns events whose window
#: overlaps `[now, now + minutes_available]`, so an event more than 3 hours out can never
#: surface. Everything here therefore starts within the next couple of hours.
#:
#: The first anchors to an indoor place so it is visible at any hour; an outdoor event needs
#: daylight and is correctly invisible at night, which makes it useless for a late test.
PLAN: tuple[tuple[str, str, str, timedelta, timedelta, str], ...] = (
    (
        "now-indoor",
        "Museum Late Opening Tour",
        "on now",
        timedelta(minutes=-20),
        timedelta(hours=3),
        "museum",
    ),
    (
        "soon-park",
        "Birdwatching Meetup",
        "starting soon",
        timedelta(minutes=30),
        timedelta(hours=2),
        "park",
    ),
    (
        "soon-water",
        "Lakeside Cleanup Drive",
        "starting soon",
        timedelta(minutes=45),
        timedelta(hours=2),
        "water",
    ),
)


async def pick_place(db: Any, kind: str) -> dict[str, Any] | None:
    """A named, seeded place of `kind` to anchor an event to."""
    return await db["places"].find_one({"kind": kind, "name": {"$ne": ""}})


def build_doc(
    place: dict[str, Any],
    suffix: str,
    title: str,
    when_text: str,
    window: tuple[datetime, datetime],
    embedding: list[float],
    now: datetime,
) -> dict[str, Any]:
    starts_at, ends_at = window
    venue = str(place["name"])
    tags = f"event={title.lower()[:24].strip()}; when={when_text}; venue={venue}"
    return {
        "_id": f"{DEV_ID_PREFIX}{suffix}",
        "name": title,
        "kind": str(place.get("kind", "other")),
        "venue_name": venue,
        "tags_summary": tags[:80],
        "loc": place["loc"],
        "cell5": place["cell5"],
        "indoor": bool(place.get("indoor", False)),
        "needs_daylight": not bool(place.get("indoor", False)),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "when_text": when_text,
        "url": None,
        "place_id": str(place["_id"]),
        "geocode": "place_match",
        "text": f"{title}. {venue}. {tags}",
        "embedding": embedding,
        "source": DEV_SOURCE,
        "fetched_at": now,
    }


async def run(clear: bool, list_places: bool) -> int:
    settings = Settings()
    if not settings.mongodb_uri:
        log.error("MONGODB_URI is not set")
        return 2
    client: Any = AsyncMongoClient(
        settings.mongodb_uri, appname="sqm-scripts", serverSelectionTimeoutMS=10000
    )
    db = client[settings.mongodb_db]
    now = datetime.now(UTC)
    try:
        if clear:
            result = await db["events"].delete_many({"source": DEV_SOURCE})
            log.info("removed %d dev-seed events", result.deleted_count)
            return 0

        if list_places:
            for kind in sorted({p[5] for p in PLAN}):
                place = await pick_place(db, kind)
                log.info("%-10s -> %s", kind, place["name"] if place else "NONE SEEDED")
            return 0

        embedder = FastEmbedder(settings.embedding_model)
        docs: list[dict[str, Any]] = []
        for suffix, title, when_text, offset, duration, kind in PLAN:
            place = await pick_place(db, kind)
            if place is None:
                log.warning("no %r place seeded; skipping %s", kind, suffix)
                continue
            starts_at = now + offset
            window = (starts_at, starts_at + duration)
            lng, lat = place["loc"]["coordinates"]
            outdoor = not bool(place.get("indoor", False))
            daylight = overlaps_daylight(window[0], window[1], lat, lng)
            text = f"{title}. {place['name']}."
            doc = build_doc(
                place, suffix, title, when_text, window, (await embedder.embed([text]))[0], now
            )
            EventDoc.model_validate(doc)  # same gate the real pipeline uses
            docs.append(doc)
            log.info(
                "%-14s %-34s at %-26s %s",
                suffix,
                title,
                place["name"][:26],
                "visible now" if not outdoor or daylight else "waits for daylight",
            )

        if not docs:
            log.error("nothing to seed; run seed_places.py first")
            return 1
        await db["events"].bulk_write(
            [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in docs], ordered=False
        )
        log.info("upserted %d dev-seed events (remove with --clear)", len(docs))
    finally:
        await client.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clear", action="store_true", help="delete every dev-seed event")
    parser.add_argument("--list-places", action="store_true", help="show anchor places only")
    args = parser.parse_args(argv)
    return asyncio.run(run(args.clear, args.list_places))


if __name__ == "__main__":
    sys.exit(main())
