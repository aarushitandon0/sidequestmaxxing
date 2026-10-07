"""GET /v1/places/near — debug/demo view of candidate places (MASTERSPEC §6.1)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.deps import DeviceId, get_db, get_embedder_dep
from app.errors import db_unavailable
from app.ratelimit import limiter
from app.sanitize import clean_phrase, round_coord
from app.services.db import Doc
from app.services.embeddings import Embedder
from app.services.places_repo import MAX_CANDIDATES, Candidate, search_places

log = logging.getLogger("sqm.places")
router = APIRouter(prefix="/v1/places", tags=["places"])

DEFAULT_QUERY = "interesting public place to explore outdoors"


@router.get("/near", response_model=list[Candidate])
@limiter.limit("30/minute")
async def places_near(
    request: Request,
    device_id: DeviceId,
    db: Annotated[AsyncDatabase[Doc], Depends(get_db)],
    embedder: Annotated[Embedder, Depends(get_embedder_dep)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_m: Annotated[int, Query(ge=300, le=6000)] = 2500,
    q: Annotated[str, Query(max_length=100)] = "",
) -> list[Candidate]:
    lat, lng = round_coord(lat), round_coord(lng)
    text = clean_phrase(q, 64) or DEFAULT_QUERY
    [vector] = await embedder.embed([text])
    try:
        found = await search_places(db, vector, lat, lng, radius_m)
    except PyMongoError as exc:
        log.warning("place search failed", extra={"error_type": type(exc).__name__})
        raise db_unavailable() from exc
    return found[:MAX_CANDIDATES]
