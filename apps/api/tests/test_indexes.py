"""Collection and index definitions for `events` (MASTERSPEC §5, P23 spec §4)."""

from app.services.indexes import (
    COLLECTIONS,
    EVENTS_VECTOR_INDEX,
    REGULAR_INDEXES,
    VECTOR_INDEXES,
)


def test_events_collection_registered() -> None:
    assert "events" in COLLECTIONS


def test_events_has_geo_and_ttl_indexes() -> None:
    names = {m.document["name"] for m in REGULAR_INDEXES["events"]}
    assert {"loc_2dsphere", "cell5", "ends_at_ttl"} <= names
    ttl = next(m for m in REGULAR_INDEXES["events"] if m.document["name"] == "ends_at_ttl")
    assert ttl.document["expireAfterSeconds"] == 0


def test_events_vector_index_filters_cell5_and_kind() -> None:
    name, definition = VECTOR_INDEXES["events"]
    assert name == EVENTS_VECTOR_INDEX == "events_vec"
    paths = {f["path"] for f in definition["fields"] if f["type"] == "filter"}
    assert paths == {"cell5", "kind"}
    vector = next(f for f in definition["fields"] if f["type"] == "vector")
    assert vector["numDimensions"] == 384 and vector["similarity"] == "cosine"
