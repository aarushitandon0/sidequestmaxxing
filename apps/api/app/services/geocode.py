"""Resolve an event venue to coordinates, in two tiers (P23 spec section 5).

Tier 1 matches the venue against the OSM places we already seeded: free, offline, and the
only tier allowed to claim a real `kind`/`indoor`. Tier 2 asks Nominatim, under its fair-use
terms, and is always offline (the fetch script), never on a request path. There is no tier 3:
an unresolvable venue is dropped, because events are a bonus candidate source and never
required.
"""

import logging
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.services.embeddings import cosine
from app.services.geo import cells_around
from app.services.indexes import PLACES_VECTOR_INDEX

logger = logging.getLogger(__name__)

Doc = dict[str, Any]

VENUE_MATCH_COSINE = 0.90
"""Minimum vector score for a tier-1 venue match. Below it, the venue is not that place."""

NOMINATIM_USER_AGENT = "Sidequestmaxxing/0.1 (open-source hackathon project; one-off seed script)"
NOMINATIM_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_VECTOR_LIMIT = 20
_NUM_CANDIDATES = 200
_WS_RE = re.compile(r"\s+")


class Resolved(BaseModel):
    """Where an event actually is, and how confident we are about the place metadata."""

    lat: float
    lng: float
    kind: str
    indoor: bool
    place_id: str | None
    geocode: Literal["place_match", "nominatim"]


def within_bbox(lat: float, lng: float, bbox: tuple[float, float, float, float]) -> bool:
    """`bbox` is `(south, west, north, east)`, matching `app.services.osm.BBox`. Inclusive."""
    south, west, north, east = bbox
    return south <= lat <= north and west <= lng <= east


def _norm_name(name: str) -> str:
    return _WS_RE.sub(" ", name).strip().casefold()


def geocode_query(*, venue_name: str, title: str, address: list[str], city: str) -> str:
    """The Nominatim `q` for an event: venue, then address lines, then the city.

    Parts are deduplicated case-insensitively because the Google Search events pack has no
    `venue` object and the venue is taken from `address[0]`, so a naive join repeats it -
    and `"Pashan Lake, Pashan Lake, Pashan"` misses a lake that `"Pashan Lake, Pashan, Pune"`
    finds. The city is appended for the same reason: without it Nominatim misses venues that
    resolve cleanly with it.
    """
    # Deduplication is per comma-separated token, not per part, because the repetition shows
    # up at both levels: the venue repeats `address[0]` wholesale, and Google also writes the
    # city into the venue line ("The Box Hub, Pune") where a whole-part check would miss it.
    tokens: list[str] = []
    seen: set[str] = set()
    for part in (venue_name or title, *address, city):
        for token in part.split(","):
            token = _WS_RE.sub(" ", token).strip()
            if not token or token.casefold() in seen:
                continue
            seen.add(token.casefold())
            tokens.append(token)
    return ", ".join(tokens)


def _resolved_from_place(doc: Doc) -> Resolved:
    lng, lat = doc["loc"]["coordinates"]
    return Resolved(
        lat=lat,
        lng=lng,
        kind=str(doc.get("kind", "other")),
        indoor=bool(doc.get("indoor", False)),
        place_id=str(doc["_id"]),
        geocode="place_match",
    )


async def match_place(
    db: AsyncDatabase[Doc],
    venue_name: str,
    venue_vector: list[float],
    lat: float,
    lng: float,
) -> Resolved | None:
    """Tier 1: the venue as an already-seeded OSM place, or `None`.

    Pinning the search to `cells_around(lat, lng)` is what keeps a Mumbai venue of the same
    name out of a Pune quest.
    """
    cells = cells_around(lat, lng)
    wanted = _norm_name(venue_name)
    if not wanted:
        return None

    exact = await db["places"].find_one({"name": venue_name, "cell5": {"$in": cells}})
    if exact is not None:
        return _resolved_from_place(exact)

    cursor = await db["places"].aggregate(_build_venue_pipeline(venue_vector, cells))
    docs: list[Doc] = await cursor.to_list(length=None)
    if not docs:
        return None

    # A normalized-name hit inside the pinned cells is a match whatever its vector score:
    # "  shaniwar   wada " is the same venue as "Shaniwar Wada".
    for doc in docs:
        if _norm_name(str(doc.get("name", ""))) == wanted:
            return _resolved_from_place(doc)

    best = max(docs, key=lambda d: _score_of(d, venue_vector))
    if _score_of(best, venue_vector) < VENUE_MATCH_COSINE:
        return None
    return _resolved_from_place(best)


def _build_venue_pipeline(venue_vector: list[float], cells: list[str]) -> list[Doc]:
    return [
        {
            "$vectorSearch": {
                "index": PLACES_VECTOR_INDEX,
                "path": "embedding",
                "queryVector": venue_vector,
                "numCandidates": _NUM_CANDIDATES,
                "limit": _VECTOR_LIMIT,
                "filter": {"cell5": {"$in": cells}},
            }
        },
        {
            "$project": {
                "_id": 1,
                "name": 1,
                "kind": 1,
                "indoor": 1,
                "loc": 1,
                "embedding": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]


def _score_of(doc: Doc, venue_vector: list[float]) -> float:
    """The `$vectorSearch` score, or a direct cosine when a caller hands us raw docs."""
    score = doc.get("score")
    if isinstance(score, int | float):
        return float(score)
    embedding = doc.get("embedding")
    if isinstance(embedding, list) and len(embedding) == len(venue_vector):
        return cosine(venue_vector, embedding)
    return 0.0


async def nominatim_lookup(
    client: httpx.AsyncClient,
    url: str,
    query: str,
    bbox: tuple[float, float, float, float],
) -> Resolved | None:
    """Tier 2: one Nominatim search, bbox-guarded. Returns `None` on any failure.

    A geocode failure must never propagate: the caller drops the event and moves on. Results
    get `kind="other"` and `indoor=False` — the safe defaults — because only a tier-1 match
    may claim a real kind.
    """
    try:
        response = await client.get(
            url,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "in",
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
            timeout=NOMINATIM_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()
        if not isinstance(results, list) or not results:
            logger.info("nominatim: no result")
            return None
        hit = results[0]
        lat = float(hit["lat"])
        lng = float(hit["lon"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("nominatim lookup failed: %s", type(exc).__name__)
        return None

    if not within_bbox(lat, lng, bbox):
        logger.info("nominatim: result outside the demo bbox, rejected")
        return None
    return Resolved(
        lat=lat, lng=lng, kind="other", indoor=False, place_id=None, geocode="nominatim"
    )
