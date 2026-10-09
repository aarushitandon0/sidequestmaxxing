import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.geo import cell5
from app.services.osm import classify, overpass_query, parse_bbox, places_from_overpass

NOW = datetime(2026, 10, 7, tzinfo=UTC)
SAMPLE = json.loads(
    (Path(__file__).parent / "fixtures" / "overpass_sample.json").read_text(encoding="utf-8")
)


def _by_id() -> dict[str, dict[str, object]]:
    return {p["_id"]: p for p in places_from_overpass(SAMPLE, NOW)}


def test_maps_and_filters_sample() -> None:
    places = _by_id()
    # Kept: viewpoint, park, museum, cafe, memorial, library. Dropped: nameless cafe,
    # private garden, centre-less relation, bakery, access=no wood, duplicate node/1.
    assert set(places) == {"node/1", "way/2", "way/3", "node/4", "node/7", "node/10"}


def test_place_fields() -> None:
    p = _by_id()
    view = p["node/1"]
    assert view["kind"] == "viewpoint"
    assert view["loc"] == {"type": "Point", "coordinates": [73.8202, 18.5301]}
    assert view["cell5"] == cell5(18.5301, 73.8202)
    assert view["indoor"] is False and view["needs_daylight"] is True
    assert view["source"] == "osm" and view["fetched_at"] == NOW
    assert p["way/2"]["needs_daylight"] is False  # lit=yes
    assert p["way/3"]["indoor"] is True and p["way/3"]["needs_daylight"] is False
    assert p["node/7"]["kind"] == "heritage"
    assert "Stone memorial" in str(p["node/7"]["text"])
    assert p["node/10"]["name"] == "Public Library EN"  # prefers name:en
    assert "cuisine=coffee_shop" in str(p["node/4"]["tags_summary"])
    assert "coffee shop" in str(p["node/4"]["text"])


@pytest.mark.parametrize(
    ("tags", "kind"),
    [
        ({"tourism": "museum", "historic": "castle"}, "museum"),  # indoor wins over historic
        ({"leisure": "park"}, "park"),
        ({"historic": "yes"}, "heritage"),
        ({"natural": "peak"}, "peak"),
        ({"amenity": "marketplace"}, "market"),
        ({"tourism": "attraction"}, "other"),
        ({"shop": "mall"}, None),
    ],
)
def test_classify(tags: dict[str, str], kind: str | None) -> None:
    assert classify(tags) == kind


def test_parse_bbox() -> None:
    assert parse_bbox("18.45,73.75,18.60,73.95") == (18.45, 73.75, 18.60, 73.95)
    for bad in ("1,2,3", "18.6,73.75,18.45,73.95", "a,b,c,d", "0,0,91,1"):
        with pytest.raises(ValueError):
            parse_bbox(bad)


def test_overpass_query_mentions_all_kinds_and_bbox() -> None:
    q = overpass_query((1.0, 2.0, 3.0, 4.0))
    assert "(1.0,2.0,3.0,4.0)" in q
    for needle in (
        "park|garden|nature_reserve",
        "peak|water|wood",
        "museum",
        "historic",
        "marketplace|cafe|library",
        "out center tags",
    ):
        assert needle in q
