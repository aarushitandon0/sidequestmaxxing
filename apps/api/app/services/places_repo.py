"""Place search: Atlas $vectorSearch pre-filtered by geohash cells, then haversine post-filter."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.models.enums import PlaceKind
from app.models.quest import Happening
from app.services.geo import cells_around, haversine_m
from app.services.indexes import PLACES_VECTOR_INDEX

Doc = dict[str, Any]
MAX_CANDIDATES = 8


class Candidate(BaseModel):
    """What the Scout hands to the Quest Master (MASTERSPEC §7.2)."""

    id: str
    name: str
    kind: PlaceKind
    distance_m: int
    tags_summary: str = ""
    indoor: bool = False
    needs_daylight: bool = True
    lat: float
    lng: float
    score: float | None = None
    event_window: tuple[datetime, datetime] | None = None
    """`(starts_at, ends_at)` in UTC for a live event; `None` for an ordinary place (P23)."""
    happening: Happening | None = None
    """The event this candidate is, for `hydrate` to copy onto the response; `None` for places."""


def build_places_pipeline(
    query_vector: list[float],
    cells: list[str],
    *,
    limit: int = 40,
    num_candidates: int = 200,
    kinds: list[str] | None = None,
) -> list[Doc]:
    vector_filter: Doc = {"cell5": {"$in": cells}}
    if kinds:
        vector_filter = {"$and": [vector_filter, {"kind": {"$in": kinds}}]}
    return [
        {
            "$vectorSearch": {
                "index": PLACES_VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": num_candidates,
                "limit": limit,
                "filter": vector_filter,
            }
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
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]


def to_candidate(doc: Doc, lat: float, lng: float) -> Candidate:
    plng, plat = doc["loc"]["coordinates"]
    return Candidate(
        id=str(doc["_id"]),
        name=doc["name"],
        kind=doc.get("kind", "other"),
        distance_m=round(haversine_m(lat, lng, plat, plng)),
        tags_summary=doc.get("tags_summary", ""),
        indoor=bool(doc.get("indoor", False)),
        needs_daylight=bool(doc.get("needs_daylight", True)),
        lat=plat,
        lng=plng,
        score=doc.get("score"),
    )


async def search_places(
    db: AsyncDatabase[Doc],
    query_vector: list[float],
    lat: float,
    lng: float,
    radius_m: int,
    *,
    kinds: list[str] | None = None,
    limit: int = 40,
) -> list[Candidate]:
    """Vector-ranked places within `radius_m`, best first. Not yet safety/time filtered."""
    pipeline = build_places_pipeline(query_vector, cells_around(lat, lng), kinds=kinds, limit=limit)
    cursor = await db["places"].aggregate(pipeline)
    docs: list[Doc] = await cursor.to_list(length=None)
    candidates = [to_candidate(d, lat, lng) for d in docs]
    return [c for c in candidates if c.distance_m <= radius_m]
