"""Live-event search: `$vectorSearch` over `events`, time-windowed, merged into the pool.

Events are a bonus candidate source, never a required one: every failure here degrades to an
ordinary place quest (MASTERSPEC section 2.4). They ride into the model through the existing
freeform `tags_summary` field, so no prompt changes — `prompts/quest_master.system.txt` is
untouched by this feature.
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.services.db import Doc
from app.services.geo import cells_around, haversine_m
from app.services.indexes import EVENTS_VECTOR_INDEX
from app.services.places_repo import MAX_CANDIDATES, Candidate

log = logging.getLogger("sqm.events")

MAX_EVENT_CANDIDATES = 3
"""At most 3 of the 8 candidate slots may be events, so a quiet day still gets place quests."""


def build_events_pipeline(
    query_vector: list[float],
    cells: list[str],
    now: datetime,
    until: datetime,
    *,
    limit: int = 20,
    num_candidates: int = 100,
) -> list[Doc]:
    """Vector search in the nearby cells, then keep only events joinable in `[now, until]`.

    The `$match` is not redundant with the TTL index: Mongo's TTL sweep runs on its own
    schedule, so expired documents can still be present and must be excluded here.
    """
    return [
        {
            "$vectorSearch": {
                "index": EVENTS_VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": num_candidates,
                "limit": limit,
                "filter": {"cell5": {"$in": cells}},
            }
        },
        {
            "$addFields": {"score": {"$meta": "vectorSearchScore"}},
        },
        {
            # Overlap, not containment: an event that began 20 minutes ago is still joinable.
            "$match": {"ends_at": {"$gte": now}, "starts_at": {"$lte": until}},
        },
        {
            "$project": {
                "_id": 1,
                "name": 1,
                "kind": 1,
                "tags_summary": 1,
                "indoor": 1,
                "needs_daylight": 1,
                "loc": 1,
                "starts_at": 1,
                "ends_at": 1,
                "when_text": 1,
                "url": 1,
                "score": 1,
            }
        },
    ]


def to_event_candidate(doc: Doc, lat: float, lng: float) -> Candidate:
    """An `events` document as a Scout candidate, indistinguishable in shape from a place."""
    elng, elat = doc["loc"]["coordinates"]
    return Candidate(
        id=str(doc["_id"]),
        name=doc["name"],
        kind=doc.get("kind", "other"),
        distance_m=round(haversine_m(lat, lng, elat, elng)),
        tags_summary=doc.get("tags_summary", ""),
        indoor=bool(doc.get("indoor", False)),
        needs_daylight=bool(doc.get("needs_daylight", True)),
        lat=elat,
        lng=elng,
        score=doc.get("score"),
        event_window=(doc["starts_at"], doc["ends_at"]),
    )


async def search_events(
    db: AsyncDatabase[Doc],
    query_vector: list[float],
    lat: float,
    lng: float,
    radius_m: int,
    *,
    now: datetime,
    minutes_available: int,
) -> list[Candidate]:
    """Events joinable from here within the player's window. Never raises on DB trouble."""
    until = now + timedelta(minutes=minutes_available)
    pipeline = build_events_pipeline(query_vector, cells_around(lat, lng), now, until)
    try:
        cursor = await db["events"].aggregate(pipeline)
        docs: list[Doc] = await cursor.to_list(length=None)
    except PyMongoError as exc:
        log.warning("event search failed", extra={"error_type": type(exc).__name__})
        return []
    candidates = [to_event_candidate(d, lat, lng) for d in docs]
    return [c for c in candidates if c.distance_m <= radius_m]


def merge_candidates(
    events: Sequence[Candidate],
    places: Sequence[Candidate],
    limit: int = MAX_CANDIDATES,
) -> list[Candidate]:
    """Up to `MAX_EVENT_CANDIDATES` events first, then places, to `limit` in all.

    Events lead so that `diversify`'s per-kind cap cannot starve them: a live happening is
    the rarer thing and the whole point of the feature.
    """
    kept_events = list(events[:MAX_EVENT_CANDIDATES])
    room = max(limit - len(kept_events), 0)
    return kept_events[:limit] + list(places[:room])
