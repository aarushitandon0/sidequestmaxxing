"""`events` vector search, its time window, and the 3-of-8 merge into the candidate pool."""

from datetime import UTC, datetime, timedelta

from pymongo.errors import OperationFailure

from app.services.embeddings import EMBEDDING_DIM
from app.services.events_repo import (
    MAX_EVENT_CANDIDATES,
    build_events_pipeline,
    merge_candidates,
    search_events,
    to_event_candidate,
)
from app.services.indexes import EVENTS_VECTOR_INDEX
from app.services.places_repo import MAX_CANDIDATES, Candidate
from tests.fakes import Doc, FakeCursor, _matches

NOW = datetime(2026, 10, 11, 4, 0, tzinfo=UTC)
UNTIL = NOW + timedelta(minutes=60)
LAT, LNG = 18.520, 73.856
VEC = [1.0] + [0.0] * (EMBEDDING_DIM - 1)


def event_doc(
    eid: str,
    name: str,
    *,
    starts_at: datetime,
    ends_at: datetime,
    lat: float = LAT + 0.001,
    lng: float = LNG,
    kind: str = "heritage",
    indoor: bool = False,
    needs_daylight: bool = True,
) -> Doc:
    return {
        "_id": eid,
        "name": name,
        "kind": kind,
        "tags_summary": "event=heritage walk; venue=Shaniwar Wada",
        "loc": {"type": "Point", "coordinates": [lng, lat]},
        "cell5": "tek3r",
        "indoor": indoor,
        "needs_daylight": needs_daylight,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "when_text": "Sat, Oct 11, 7:00 AM",
        "url": "https://example.invalid/walk",
        "score": 0.95,
    }


class MatchingEvents:
    """An `events` collection that applies both the vector filter and the `$match` stage."""

    def __init__(self, docs: list[Doc], *, fail: Exception | None = None) -> None:
        self.docs = docs
        self.fail = fail

    async def aggregate(self, pipeline: list[Doc]) -> FakeCursor:
        if self.fail is not None:
            raise self.fail
        hits = [dict(d) for d in self.docs if _matches(d, pipeline[0]["$vectorSearch"]["filter"])]
        for stage in pipeline:
            if "$match" in stage:
                hits = [d for d in hits if _matches(d, stage["$match"])]
        return FakeCursor(hits)


class EventsDB:
    def __init__(self, events: MatchingEvents) -> None:
        self.events = events

    def __getitem__(self, name: str) -> MatchingEvents:
        assert name == "events"
        return self.events


def _candidate(cid: str, kind: str = "park") -> Candidate:
    return Candidate(id=cid, name=cid, kind=kind, distance_m=100, lat=LAT, lng=LNG)


# --- pipeline -------------------------------------------------------------------------------


def test_pipeline_filters_cells_and_time_window() -> None:
    stages = build_events_pipeline(VEC, ["tek3r"], NOW, UNTIL)
    assert stages[0]["$vectorSearch"]["index"] == EVENTS_VECTOR_INDEX
    assert stages[0]["$vectorSearch"]["filter"] == {"cell5": {"$in": ["tek3r"]}}
    match = next(s["$match"] for s in stages if "$match" in s)
    assert match["ends_at"]["$gte"] == NOW
    assert match["starts_at"]["$lte"] == UNTIL


def test_pipeline_projects_no_embedding() -> None:
    stages = build_events_pipeline(VEC, ["tek3r"], NOW, UNTIL)
    project = next(s["$project"] for s in stages if "$project" in s)
    assert "embedding" not in project


# --- to_event_candidate ---------------------------------------------------------------------


def test_to_event_candidate_carries_the_event_through_tags_summary() -> None:
    doc = event_doc("serp/abc", "Heritage Walk", starts_at=NOW, ends_at=UNTIL)
    c = to_event_candidate(doc, LAT, LNG)
    assert c.id == "serp/abc"
    assert c.name == "Heritage Walk"
    assert c.tags_summary == doc["tags_summary"]
    assert c.kind == "heritage"
    assert c.distance_m > 0
    assert (c.lat, c.lng) == (doc["loc"]["coordinates"][1], doc["loc"]["coordinates"][0])


def test_to_event_candidate_keeps_indoor_and_daylight_flags() -> None:
    doc = event_doc(
        "serp/in", "Indoor Talk", starts_at=NOW, ends_at=UNTIL, indoor=True, needs_daylight=False
    )
    c = to_event_candidate(doc, LAT, LNG)
    assert c.indoor is True
    assert c.needs_daylight is False


# --- search_events --------------------------------------------------------------------------


async def test_live_event_is_returned() -> None:
    doc = event_doc("serp/live", "Live Walk", starts_at=NOW - timedelta(minutes=20), ends_at=UNTIL)
    db = EventsDB(MatchingEvents([doc]))
    out = await search_events(db, VEC, LAT, LNG, 2500, now=NOW, minutes_available=60)
    assert [c.id for c in out] == ["serp/live"]


async def test_all_documents_expired_yields_no_candidates() -> None:
    """The TTL sweep is asynchronous, so the time `$match` must exclude expired documents."""
    past = [
        event_doc(
            "serp/old1",
            "Yesterday",
            starts_at=NOW - timedelta(days=1, hours=2),
            ends_at=NOW - timedelta(days=1),
        ),
        event_doc(
            "serp/old2",
            "An hour ago",
            starts_at=NOW - timedelta(hours=3),
            ends_at=NOW - timedelta(hours=1),
        ),
    ]
    db = EventsDB(MatchingEvents(past))
    assert await search_events(db, VEC, LAT, LNG, 2500, now=NOW, minutes_available=60) == []


async def test_event_starting_after_the_window_is_excluded() -> None:
    doc = event_doc(
        "serp/later",
        "Tonight",
        starts_at=NOW + timedelta(hours=5),
        ends_at=NOW + timedelta(hours=7),
    )
    db = EventsDB(MatchingEvents([doc]))
    assert await search_events(db, VEC, LAT, LNG, 2500, now=NOW, minutes_available=60) == []


async def test_event_outside_the_radius_is_excluded() -> None:
    doc = event_doc("serp/far", "Far Walk", starts_at=NOW, ends_at=UNTIL, lat=LAT + 0.05, lng=LNG)
    db = EventsDB(MatchingEvents([doc]))
    assert await search_events(db, VEC, LAT, LNG, 2500, now=NOW, minutes_available=60) == []


async def test_pymongo_error_is_isolated_and_returns_empty() -> None:
    db = EventsDB(MatchingEvents([], fail=OperationFailure("no such index")))
    assert await search_events(db, VEC, LAT, LNG, 2500, now=NOW, minutes_available=60) == []


# --- merge_candidates -----------------------------------------------------------------------


def test_merge_caps_events_at_three_of_eight() -> None:
    events = [_candidate(f"serp/{i}", "heritage") for i in range(6)]
    places = [_candidate(f"p/{i}") for i in range(8)]
    merged = merge_candidates(events, places)
    assert sum(1 for c in merged if c.id.startswith("serp/")) == MAX_EVENT_CANDIDATES
    assert len(merged) == MAX_CANDIDATES


def test_merge_with_no_events_is_unchanged_place_list() -> None:
    places = [_candidate(f"p/{i}") for i in range(8)]
    assert merge_candidates([], places) == places


def test_merge_with_few_places_still_returns_available_events() -> None:
    merged = merge_candidates([_candidate("serp/1"), _candidate("serp/2")], [_candidate("p/1")])
    assert len(merged) == 3


def test_merge_puts_events_first_so_diversify_cannot_starve_them() -> None:
    merged = merge_candidates([_candidate("serp/1")], [_candidate(f"p/{i}") for i in range(8)])
    assert merged[0].id == "serp/1"
    assert len(merged) == MAX_CANDIDATES


def test_merge_respects_an_explicit_limit() -> None:
    events = [_candidate(f"serp/{i}") for i in range(3)]
    places = [_candidate(f"p/{i}") for i in range(8)]
    merged = merge_candidates(events, places, limit=4)
    assert len(merged) == 4
    assert sum(1 for c in merged if c.id.startswith("serp/")) == 3


def test_merge_does_not_mutate_its_inputs() -> None:
    events = [_candidate("serp/1")]
    places = [_candidate("p/1")]
    merge_candidates(events, places)
    assert len(events) == 1
    assert len(places) == 1
