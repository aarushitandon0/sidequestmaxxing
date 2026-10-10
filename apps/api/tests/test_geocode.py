"""Venue coordinate resolution: tier-1 OSM place match, then tier-2 Nominatim."""

from typing import Any

import httpx

from app.services.embeddings import EMBEDDING_DIM
from app.services.geo import cell5
from app.services.geocode import (
    VENUE_MATCH_COSINE,
    geocode_query,
    match_place,
    nominatim_lookup,
    within_bbox,
)
from tests.fakes import Doc, FakeCursor, _matches, place_doc

PUNE_BBOX = (18.43, 73.73, 18.63, 73.99)
URL = "https://nominatim.example.invalid/search"
VECTOR = [1.0] + [0.0] * (EMBEDDING_DIM - 1)


class VecPlaces:
    """A `places` collection that honours the `$vectorSearch` cell filter and scores hits."""

    def __init__(self, docs: list[Doc], *, score: float = 0.99) -> None:
        self.docs = docs
        self.score = score

    async def find_one(self, flt: Doc, *a: Any, **kw: Any) -> Doc | None:
        return next((dict(d) for d in self.docs if _matches(d, flt)), None)

    async def aggregate(self, pipeline: list[Doc]) -> FakeCursor:
        flt = pipeline[0]["$vectorSearch"]["filter"]
        hits = [dict(d) | {"score": self.score} for d in self.docs if _matches(d, flt)]
        return FakeCursor(hits)


class OneCollectionDB:
    def __init__(self, places: VecPlaces) -> None:
        self.places = places

    def __getitem__(self, name: str) -> VecPlaces:
        assert name == "places"
        return self.places


def _pune_place(pid: str, name: str, kind: str, **extra: Any) -> Doc:
    lat, lng = 18.52, 73.86
    doc = place_doc(pid, name, kind, lat, lng, **extra)
    doc["cell5"] = cell5(lat, lng)
    doc["embedding"] = VECTOR
    return doc


def _db(docs: list[Doc], *, score: float = 0.99) -> OneCollectionDB:
    return OneCollectionDB(VecPlaces(docs, score=score))


def fake_nominatim(*, lat: float, lng: float) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[{"lat": str(lat), "lon": str(lng), "display_name": "somewhere"}]
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_exact_name_match_wins_and_inherits_place_fields() -> None:
    db = _db([_pune_place("node/123456", "Shaniwar Wada", "heritage", indoor=False)])
    r = await match_place(db, "Shaniwar Wada", VECTOR, 18.52, 73.86)
    assert r is not None
    assert r.geocode == "place_match"
    assert r.place_id == "node/123456"
    assert r.kind == "heritage"
    assert r.indoor is False
    assert (r.lat, r.lng) == (18.52, 73.86)


async def test_exact_name_match_is_case_and_whitespace_insensitive() -> None:
    db = _db([_pune_place("node/1", "Shaniwar Wada", "heritage")])
    r = await match_place(db, "  shaniwar   wada ", VECTOR, 18.52, 73.86)
    assert r is not None
    assert r.place_id == "node/1"


async def test_vector_match_below_threshold_is_rejected() -> None:
    db = _db([_pune_place("node/2", "Some Hall", "other")], score=VENUE_MATCH_COSINE - 0.01)
    assert await match_place(db, "Totally Different Venue", VECTOR, 18.52, 73.86) is None


async def test_vector_match_at_threshold_is_accepted() -> None:
    db = _db([_pune_place("node/2", "Some Hall", "other")], score=VENUE_MATCH_COSINE)
    r = await match_place(db, "Totally Different Venue", VECTOR, 18.52, 73.86)
    assert r is not None
    assert r.geocode == "place_match"


async def test_match_is_restricted_to_nearby_cells() -> None:
    mumbai = place_doc("node/9", "Town Hall", "heritage", 19.07, 72.87)
    mumbai["cell5"] = cell5(19.07, 72.87)
    mumbai["embedding"] = VECTOR
    db = _db([mumbai])
    assert await match_place(db, "Town Hall", VECTOR, 18.52, 73.86) is None


async def test_nominatim_result_outside_bbox_is_rejected() -> None:
    async with fake_nominatim(lat=19.07, lng=72.87) as client:
        assert await nominatim_lookup(client, URL, "Town Hall Pune", PUNE_BBOX) is None


async def test_nominatim_result_inside_bbox_is_accepted() -> None:
    async with fake_nominatim(lat=18.52, lng=73.86) as client:
        r = await nominatim_lookup(client, URL, "Shaniwar Wada Pune", PUNE_BBOX)
    assert r is not None
    assert r.geocode == "nominatim"
    assert r.kind == "other"
    assert r.indoor is False
    assert r.place_id is None


async def test_nominatim_sends_fair_use_headers_and_params() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"lat": "18.52", "lon": "73.86"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await nominatim_lookup(client, URL, "Shaniwar Wada Pune", PUNE_BBOX)

    assert len(seen) == 1
    assert "Sidequestmaxxing" in seen[0].headers["User-Agent"]
    params = seen[0].url.params
    assert params["format"] == "jsonv2"
    assert params["limit"] == "1"
    assert params["countrycodes"] == "in"
    assert params["q"] == "Shaniwar Wada Pune"


async def test_nominatim_empty_result_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await nominatim_lookup(client, URL, "nowhere", PUNE_BBOX) is None


async def test_nominatim_http_error_returns_none_not_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nominatim is down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await nominatim_lookup(client, URL, "x", PUNE_BBOX) is None


async def test_nominatim_bad_payload_returns_none_not_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"lat": "not-a-number", "lon": "73.86"}])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await nominatim_lookup(client, URL, "x", PUNE_BBOX) is None


def test_within_bbox_boundaries() -> None:
    assert within_bbox(18.43, 73.73, PUNE_BBOX)
    assert within_bbox(18.63, 73.99, PUNE_BBOX)
    assert not within_bbox(18.42, 73.86, PUNE_BBOX)
    assert not within_bbox(18.52, 74.01, PUNE_BBOX)


# --- geocode query building ------------------------------------------------------------------


def test_query_does_not_repeat_a_venue_that_came_from_the_address() -> None:
    """The Google Search shape sets `venue_name` to `address[0]`; repeating it misses."""
    q = geocode_query(
        venue_name="Pashan Lake",
        title="Morning Nature Walk",
        address=["Pashan Lake", "Pashan"],
        city="Pune",
    )
    assert q == "Pashan Lake, Pashan, Pune"


def test_query_appends_the_city_once() -> None:
    q = geocode_query(
        venue_name="Shaniwar Wada", title="Heritage Walk", address=["Shaniwar Peth"], city="Pune"
    )
    assert q == "Shaniwar Wada, Shaniwar Peth, Pune"


def test_query_does_not_duplicate_a_city_already_in_the_address() -> None:
    q = geocode_query(
        venue_name="Shaniwar Wada",
        title="Heritage Walk",
        address=["Shaniwar Peth", "Pune, Maharashtra"],
        city="Pune, Maharashtra, India",
    )
    assert q.lower().count("maharashtra") == 1


def test_query_falls_back_to_the_title_when_there_is_no_venue() -> None:
    q = geocode_query(venue_name="", title="Heritage Walk", address=[], city="Pune")
    assert q == "Heritage Walk, Pune"


def test_query_dedupes_case_insensitively() -> None:
    q = geocode_query(
        venue_name="pashan lake", title="Walk", address=["Pashan Lake", "Pashan"], city="Pune"
    )
    assert q.lower().count("pashan lake") == 1


def test_query_does_not_repeat_a_city_already_inside_the_venue_name() -> None:
    """Google writes the city into the venue line ("The Box Hub, Pune")."""
    q = geocode_query(
        venue_name="The Box Hub, Pune",
        title="Sakharam ka Ghar",
        address=["The Box Hub, Pune", "Pune"],
        city="Pune, Maharashtra, India",
    )
    assert q == "The Box Hub, Pune, Maharashtra, India"
    assert q.lower().count("pune") == 1
