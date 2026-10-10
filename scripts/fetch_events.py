"""Fetch live Pune happenings from SerpApi `google_events`, filter, geocode, upsert (P23).

Usage (repo root):
    python scripts/fetch_events.py --city pune --dry-run         # funnel report, no DB writes
    python scripts/fetch_events.py --city pune                   # upsert into `events`
    python scripts/fetch_events.py --city pune --from-cache      # reuse today's cached payloads
    python scripts/fetch_events.py --city pune --no-geocode      # tier-1 place match only

Offline only: nothing here runs on a request path. `SERPAPI_API_KEY` is read from the
environment by this script alone and is deliberately absent from `apps/api/app/config.py`
and `render.yaml`. The key is never logged, and neither is a request URL, which carries it
as a query parameter.

Fair use: at most `--max-searches` SerpApi searches per run (default 4, one per query), raw
responses cached locally, and at most one Nominatim lookup per unresolved venue.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import _bootstrap
import httpx
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError

from app.config import Settings
from app.models.event import SerpEvent
from app.services.embeddings import FastEmbedder
from app.services.event_time import overlaps_daylight, parse_event_window
from app.services.geo import cell5
from app.services.geocode import Resolved, match_place, nominatim_lookup
from app.services.serp_events import (
    banned_terms_hit,
    event_tags_summary,
    is_ticketed,
    parse_events,
    sanitize_event,
)

log = logging.getLogger("fetch_events")
DATA_DIR = _bootstrap.REPO_ROOT / "data"

QUERIES: tuple[str, ...] = (
    "events in Pune",
    "workshops in Pune",
    "heritage walk Pune",
    "nature walk Pune",
)
DEFAULT_MAX_SEARCHES = 4

DEFAULT_SERPAPI_BASE_URL = "https://serpapi.com/search"
SERPAPI_ENGINE = "google"
"""`google_events` was deprecated (SerpApi changelog 2026-08-24); the events pack now rides
in `events_results` on the plain Google Search engine. See `fetch_serpapi`."""
DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_BBOX = "18.43,73.73,18.63,73.99"
PUNE_TZ_OFFSET_MIN = 330

FUNNEL_STAGES: tuple[str, ...] = (
    "fetched",
    "parsed",
    "banned",
    "ticketed",
    "no_time",
    "night",
    "no_coords",
    "kept",
    "upserted",
)

_SERP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class SerpApiError(RuntimeError):
    """A SerpApi failure, carrying only SerpApi's own message - never the request URL."""


def slug(city: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-") or "city"


def load_env_file(path: Path | None = None) -> None:
    """Populate `os.environ` from the repo-root `.env`, without overriding a real env var.

    `Settings` already reads `.env` for the API's own fields, but `SERPAPI_API_KEY` is
    deliberately not a `Settings` field, so this script reads the file itself. Values are
    never logged. A missing or unreadable `.env` is not an error — the key may come from the
    real environment instead.
    """
    env_path = path or _bootstrap.REPO_ROOT / ".env"
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value:
            os.environ.setdefault(key, value)


def parse_bbox_arg(text: str) -> tuple[float, float, float, float]:
    """`"S,W,N,E"` -> `(south, west, north, east)`."""
    parts = [float(p) for p in text.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be S,W,N,E")
    south, west, north, east = parts
    return south, west, north, east


def funnel_report(counts: Counter[str]) -> str:
    """One line per stage, always every stage, so a zero is visible rather than missing."""
    rows = [f"  {stage:<10} {counts.get(stage, 0)}" for stage in FUNNEL_STAGES]
    return "events funnel:\n" + "\n".join(rows)


def build_event_doc(
    e: SerpEvent,
    window: tuple[datetime, datetime],
    resolved: Resolved,
    tags: str,
    embedding: list[float],
    now: datetime,
) -> dict[str, Any]:
    """An `events` document. `description` is not a field here and never will be (spec section 6).

    `_id` is derived from the listing's content, so a re-fetch updates the same document
    rather than duplicating it.
    """
    digest = hashlib.sha1(
        f"{e.title}|{e.venue_name}|{e.start_date}".encode(), usedforsecurity=False
    ).hexdigest()[:16]
    starts_at, ends_at = window
    return {
        "_id": f"serp/{digest}",
        "name": e.title,
        "kind": resolved.kind,
        "venue_name": e.venue_name,
        "tags_summary": tags,
        "loc": {"type": "Point", "coordinates": [resolved.lng, resolved.lat]},
        "cell5": cell5(resolved.lat, resolved.lng),
        "indoor": resolved.indoor,
        "needs_daylight": not resolved.indoor,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "when_text": e.when_text,
        "url": e.url,
        "place_id": resolved.place_id,
        "geocode": resolved.geocode,
        "text": f"{e.title}. {e.venue_name}. {tags}".strip(),
        "embedding": embedding,
        "source": "serpapi",
        "fetched_at": now,
    }


def silence_http_loggers() -> None:
    """Stop httpx/httpcore logging request URLs.

    `httpx`'s INFO logger prints the full URL, and ours carries `api_key` as a query
    parameter, so leaving it at INFO would write the secret into the terminal and any CI log.
    This is the one thing that must happen before the first request.
    """
    for name in ("httpx", "httpcore", "httpcore.http11", "httpcore.connection"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _serpapi_error(res: httpx.Response) -> str:
    """SerpApi's own error string, which never contains the key. Falls back to the status."""
    try:
        body = res.json()
    except ValueError:
        return f"HTTP {res.status_code}"
    message = body.get("error") if isinstance(body, dict) else None
    return str(message) if message else f"HTTP {res.status_code}"


def fetch_serpapi(base_url: str, api_key: str, query: str, city: str) -> dict[str, Any]:
    """One Google search, read for its events pack. Never logs the key.

    SerpApi's dedicated `google_events` engine was deprecated in its 2026-08-24 changelog
    ("The Google Events API has been deprecated and no longer accepts new requests. Event data
    is still available via the `events_results` field of the Google Search API"), so this asks
    `engine=google` and reads the same `events_results` array `parse_events` already expects.
    """
    params = {
        "engine": SERPAPI_ENGINE,
        "q": query,
        "location": city,
        "hl": "en",
        "gl": "in",
        "api_key": api_key,
    }
    with httpx.Client(timeout=_SERP_TIMEOUT) as client:
        res = client.get(base_url, params=params)
        if res.is_error:
            # Never let httpx format the message: its default includes the full URL.
            raise SerpApiError(_serpapi_error(res))
        payload: dict[str, Any] = res.json()
    return payload


def _load_cache(path: Path) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


async def _resolve(
    db: Any,
    client: httpx.AsyncClient | None,
    e: SerpEvent,
    venue_vector: list[float],
    centre: tuple[float, float],
    bbox: tuple[float, float, float, float],
    nominatim_url: str,
) -> Resolved | None:
    """Tier 1, then tier 2. There is no tier 3: an unresolvable venue is dropped."""
    lat, lng = centre
    if db is not None and e.venue_name:
        try:
            hit = await match_place(db, e.venue_name, venue_vector, lat, lng)
        except PyMongoError as exc:
            # An unreachable `places` collection costs us tier 1, not the whole run.
            log.warning("tier-1 place match unavailable: %s", type(exc).__name__)
        else:
            if hit is not None:
                return hit
    if client is None:
        return None
    query = ", ".join(part for part in (e.venue_name or e.title, *e.address) if part)
    return await nominatim_lookup(client, nominatim_url, query, bbox)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    silence_http_loggers()
    load_env_file()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", default=os.environ.get("EVENTS_CITY", "Pune"))
    parser.add_argument("--bbox", default=os.environ.get("EVENTS_BBOX", DEFAULT_BBOX))
    parser.add_argument("--max-searches", type=int, default=DEFAULT_MAX_SEARCHES)
    parser.add_argument("--from-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-geocode", action="store_true", help="tier-1 place match only")
    args = parser.parse_args(argv)

    settings = Settings()
    now = datetime.now(UTC)
    bbox = parse_bbox_arg(args.bbox)
    # Slice before the first request: the cap is a quota guard, not a post-filter.
    queries = QUERIES[: max(args.max_searches, 0)]
    cache = DATA_DIR / f"serpapi_{slug(args.city)}_{now.date().isoformat()}.json"

    payloads: dict[str, dict[str, Any]] = {}
    if queries and args.from_cache:
        if not cache.exists():
            log.error("no cache at %s", cache)
            return 2
        payloads = _load_cache(cache)
    elif queries:
        api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
        if not api_key:
            log.error("SERPAPI_API_KEY is not set (put it in .env; it is never committed)")
            return 2
        base_url = os.environ.get("SERPAPI_BASE_URL", DEFAULT_SERPAPI_BASE_URL)
        for query in queries:
            log.info("searching SerpApi (engine=google, events pack): %r", query)
            try:
                payloads[query] = fetch_serpapi(base_url, api_key, query, args.city)
            except (SerpApiError, httpx.HTTPError) as exc:
                detail = str(exc) if isinstance(exc, SerpApiError) else type(exc).__name__
                log.warning("SerpApi search failed: %s; continuing", detail)
        if payloads:
            DATA_DIR.mkdir(exist_ok=True)
            cache.write_text(json.dumps(payloads), encoding="utf-8")
            log.info("cached raw responses -> %s", cache.relative_to(_bootstrap.REPO_ROOT))

    return asyncio.run(
        _run(
            settings=settings,
            payloads=payloads,
            now=now,
            bbox=bbox,
            centre=((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2),
            dry_run=args.dry_run,
            no_geocode=args.no_geocode,
        )
    )


def _pair_with_raw(payload: dict[str, Any]) -> list[tuple[dict[str, Any], SerpEvent]]:
    """Each parsed event beside its raw entry, so `ticket_info` stays reachable."""
    raw_entries = [r for r in payload.get("events_results") or [] if isinstance(r, dict)]
    by_title = {str(r.get("title")): r for r in raw_entries if r.get("title")}
    return [(by_title.get(event.title, {}), event) for event in parse_events(payload)]


async def _keep_or_count(
    *,
    raw: dict[str, Any],
    event: SerpEvent,
    counts: Counter[str],
    embedder: FastEmbedder,
    db: Any,
    geo_client: httpx.AsyncClient | None,
    centre: tuple[float, float],
    bbox: tuple[float, float, float, float],
    nominatim_url: str,
    today: date,
    now: datetime,
) -> dict[str, Any] | None:
    """One event through the safety funnel. Returns its document, or None with a count bumped."""
    event = sanitize_event(event)
    if banned_terms_hit(event) is not None:
        counts["banned"] += 1
        return None
    if is_ticketed(raw, event):
        counts["ticketed"] += 1
        return None
    window = parse_event_window(
        event.start_date, event.when_text, today=today, tz_offset_min=PUNE_TZ_OFFSET_MIN
    )
    if window is None:
        counts["no_time"] += 1
        return None
    venue_vector = (await embedder.embed([event.venue_name or event.title]))[0]
    resolved = await _resolve(db, geo_client, event, venue_vector, centre, bbox, nominatim_url)
    if resolved is None:
        counts["no_coords"] += 1
        return None
    if not resolved.indoor and not overlaps_daylight(
        window[0], window[1], resolved.lat, resolved.lng
    ):
        counts["night"] += 1
        return None
    # Only a tier-1 match may claim a real kind, so only then does `kind=` reach the model.
    tags = event_tags_summary(event, resolved.kind if resolved.place_id else None)
    text = f"{event.title}. {event.venue_name}. {tags}".strip()
    embedding = (await embedder.embed([text]))[0]
    return build_event_doc(event, window, resolved, tags, embedding, now)


async def _run(
    *,
    settings: Settings,
    payloads: dict[str, dict[str, Any]],
    now: datetime,
    bbox: tuple[float, float, float, float],
    centre: tuple[float, float],
    dry_run: bool,
    no_geocode: bool,
) -> int:
    counts: Counter[str] = Counter()
    entries: list[tuple[dict[str, Any], SerpEvent]] = []
    for payload in payloads.values():
        counts["fetched"] += len(payload.get("events_results") or [])
        entries.extend(_pair_with_raw(payload))
    counts["parsed"] = len(entries)

    embedder = FastEmbedder(settings.embedding_model)
    nominatim_url = os.environ.get("NOMINATIM_URL", DEFAULT_NOMINATIM_URL)
    geo_client = None if no_geocode else httpx.AsyncClient()
    kept: dict[str, dict[str, Any]] = {}
    async_client: Any = None
    db: Any = None
    if settings.mongodb_uri:
        from pymongo import AsyncMongoClient

        async_client = AsyncMongoClient(
            settings.mongodb_uri, appname="sqm-scripts", serverSelectionTimeoutMS=10000
        )
        db = async_client[settings.mongodb_db]

    try:
        for raw, event in entries:
            doc = await _keep_or_count(
                raw=raw,
                event=event,
                counts=counts,
                embedder=embedder,
                db=db,
                geo_client=geo_client,
                centre=centre,
                bbox=bbox,
                nominatim_url=nominatim_url,
                today=now.date(),
                now=now,
            )
            if doc is not None:
                kept[doc["_id"]] = doc  # content-derived id de-duplicates across queries
    finally:
        if geo_client is not None:
            await geo_client.aclose()
        if async_client is not None:
            await async_client.close()

    counts["kept"] = len(kept)

    if dry_run:
        log.info("%s", funnel_report(counts))
        return 0
    if not settings.mongodb_uri:
        log.error("MONGODB_URI is not set")
        return 2
    if not kept:
        log.info("%s", funnel_report(counts))
        log.info("nothing to upsert")
        return 0

    mongo: MongoClient[dict[str, Any]] = MongoClient(
        settings.mongodb_uri, appname="sqm-scripts", serverSelectionTimeoutMS=10000
    )
    try:
        ops = [UpdateOne({"_id": d["_id"]}, {"$set": d}, upsert=True) for d in kept.values()]
        result = mongo[settings.mongodb_db]["events"].bulk_write(ops, ordered=False)
        counts["upserted"] = result.upserted_count + result.modified_count
    except PyMongoError as exc:
        log.error("MongoDB error: %s", type(exc).__name__)
        return 1
    finally:
        mongo.close()
    log.info("%s", funnel_report(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
