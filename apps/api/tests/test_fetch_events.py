"""scripts/fetch_events.py (P23): doc shape, quota guard and funnel report.

The module is imported in-process (it is a repo-root script that imports `app`), and only its
pure helpers plus the argument handling are exercised. `main`'s network path is never run:
no test in this repo makes a live SerpApi call.
"""

import importlib.util
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from app.models.event import SerpEvent
from app.services.embeddings import EMBEDDING_DIM
from app.services.geo import cell5
from app.services.geocode import Resolved

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"

NOW = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)
WINDOW = (
    datetime(2026, 10, 11, 1, 30, tzinfo=UTC),
    datetime(2026, 10, 11, 4, 0, tzinfo=UTC),
)
VEC = [0.1] * EMBEDDING_DIM
TAGS = "event=heritage walk; when=sat oct 11 7 00 am; venue=Shaniwar Wada"

EV = SerpEvent(
    title="Heritage Walk at Shaniwar Wada",
    venue_name="Shaniwar Wada",
    address=["Shaniwar Peth, Pune"],
    url="https://example.invalid/walk",
    when_text="Sat, Oct 11, 7:00 AM",
    start_date="Oct 11",
    description="A long untrusted description that must never reach the stored document.",
)

OUTDOOR = Resolved(
    lat=18.519,
    lng=73.855,
    kind="heritage",
    indoor=False,
    place_id="node/123456",
    geocode="place_match",
)
INDOOR = OUTDOOR.model_copy(update={"indoor": True, "kind": "museum"})


def _load() -> ModuleType:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("fetch_events", SCRIPTS / "fetch_events.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch_events = _load()
build_event_doc = fetch_events.build_event_doc
funnel_report = fetch_events.funnel_report
main = fetch_events.main


def test_doc_id_is_content_derived_and_stable() -> None:
    a = build_event_doc(EV, WINDOW, OUTDOOR, TAGS, VEC, NOW)
    b = build_event_doc(EV, WINDOW, OUTDOOR, TAGS, VEC, LATER)
    assert a["_id"] == b["_id"]
    assert a["_id"].startswith("serp/")


def test_doc_id_differs_for_a_different_event() -> None:
    other = EV.model_copy(update={"title": "Nature Walk at Pashan Lake"})
    a = build_event_doc(EV, WINDOW, OUTDOOR, TAGS, VEC, NOW)
    b = build_event_doc(other, WINDOW, OUTDOOR, TAGS, VEC, NOW)
    assert a["_id"] != b["_id"]


def test_doc_never_contains_a_description_field() -> None:
    doc = build_event_doc(EV, WINDOW, OUTDOOR, TAGS, VEC, NOW)
    assert "description" not in doc
    assert EV.description not in repr(doc)


def test_doc_sets_needs_daylight_from_indoor() -> None:
    outdoor = build_event_doc(EV, WINDOW, OUTDOOR, TAGS, VEC, NOW)
    indoor = build_event_doc(EV, WINDOW, INDOOR, TAGS, VEC, NOW)
    assert outdoor["needs_daylight"] is True
    assert outdoor["indoor"] is False
    assert indoor["needs_daylight"] is False
    assert indoor["indoor"] is True


def test_doc_has_cell5_and_geojson_point_lng_lat_order() -> None:
    doc = build_event_doc(EV, WINDOW, OUTDOOR, TAGS, VEC, NOW)
    assert doc["loc"]["type"] == "Point"
    assert doc["loc"]["coordinates"] == [OUTDOOR.lng, OUTDOOR.lat]
    assert doc["cell5"] == cell5(OUTDOOR.lat, OUTDOOR.lng)


def test_doc_validates_as_an_event_doc() -> None:
    from app.models.event import EventDoc

    doc = build_event_doc(EV, WINDOW, OUTDOOR, TAGS, VEC, NOW)
    parsed = EventDoc.model_validate(doc)
    assert parsed.starts_at == WINDOW[0]
    assert parsed.ends_at == WINDOW[1]
    assert parsed.url == "https://example.invalid/walk"
    assert parsed.place_id == "node/123456"
    assert parsed.geocode == "place_match"
    assert parsed.source == "serpapi"


def test_max_searches_caps_the_query_list() -> None:
    assert main(["--city", "pune", "--max-searches", "0", "--dry-run", "--from-cache"]) == 0


def test_missing_api_key_exits_two_without_a_live_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Neutralise the .env read first: a developer's real key must not turn this into a
    # live SerpApi call. No test in this repo touches the network.
    monkeypatch.setattr(fetch_events, "load_env_file", lambda *a, **k: None)
    monkeypatch.setattr(fetch_events, "fetch_serpapi", _never_called)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    assert main(["--city", "pune", "--dry-run"]) == 2


def _never_called(*args: object, **kwargs: object) -> dict[str, object]:
    raise AssertionError("no test may make a live SerpApi call")


def test_load_env_file_does_not_override_the_real_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\nSERPAPI_API_KEY=from-file\nEVENTS_CITY=Nagpur\n\n", encoding="utf-8"
    )
    monkeypatch.setenv("SERPAPI_API_KEY", "from-environment")
    monkeypatch.delenv("EVENTS_CITY", raising=False)
    fetch_events.load_env_file(env)
    assert os.environ["SERPAPI_API_KEY"] == "from-environment"
    assert os.environ["EVENTS_CITY"] == "Nagpur"


def test_load_env_file_tolerates_a_missing_file(tmp_path: Path) -> None:
    fetch_events.load_env_file(tmp_path / "nope.env")  # must not raise


def test_default_max_searches_matches_the_query_list() -> None:
    assert fetch_events.DEFAULT_MAX_SEARCHES == len(fetch_events.QUERIES)
    assert fetch_events.QUERIES == (
        "events in Pune",
        "workshops in Pune",
        "heritage walk Pune",
        "nature walk Pune",
    )


def test_funnel_report_lists_every_stage() -> None:
    text = funnel_report(
        Counter(
            {
                "parsed": 5,
                "banned": 1,
                "ticketed": 1,
                "no_time": 0,
                "night": 0,
                "no_coords": 1,
                "upserted": 2,
            }
        )
    )
    for stage in ("parsed", "banned", "ticketed", "no_coords", "upserted"):
        assert stage in text


def test_funnel_report_includes_stages_absent_from_the_counter() -> None:
    text = funnel_report(Counter())
    for stage in fetch_events.FUNNEL_STAGES:
        assert stage in text


def test_http_loggers_are_silenced_so_the_api_key_cannot_be_logged() -> None:
    """httpx's INFO logger prints the full URL, and ours carries `api_key` as a param."""
    import logging

    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.INFO)
    fetch_events.silence_http_loggers()
    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).level >= logging.WARNING


def test_serpapi_error_reports_the_api_message_not_the_url() -> None:
    import httpx as _httpx

    res = _httpx.Response(
        400,
        json={"error": "Unsupported `pune` location parameter."},
        request=_httpx.Request("GET", "https://serpapi.com/search?api_key=SECRET"),
    )
    message = fetch_events._serpapi_error(res)
    assert "Unsupported" in message
    assert "SECRET" not in message
    assert "api_key" not in message


def test_serpapi_error_falls_back_to_the_status_on_a_non_json_body() -> None:
    import httpx as _httpx

    res = _httpx.Response(
        502,
        text="<html>gateway</html>",
        request=_httpx.Request("GET", "https://serpapi.com/search?api_key=SECRET"),
    )
    assert fetch_events._serpapi_error(res) == "HTTP 502"


# --- review fix pass ------------------------------------------------------------------------


class _StubEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in texts]


def test_raw_entry_pairs_with_its_event_despite_whitespace_in_the_title() -> None:
    """`SerpEvent` strips titles, so the raw lookup must strip too or `ticket_info` is lost."""
    payload = {
        "events_results": [
            {
                "title": "Pottery Workshop\n",
                "date": {"when": "Sat, Oct 11, 7:00 AM"},
                "ticket_info": [{"link_type": "tickets"}],
            }
        ]
    }
    pairs = fetch_events._pair_with_raw(payload)
    assert len(pairs) == 1
    raw, event = pairs[0]
    assert event.title == "Pottery Workshop"
    assert raw.get("ticket_info")


async def test_a_document_that_is_not_a_valid_event_doc_is_dropped_before_upsert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts: Counter[str] = Counter()

    async def _resolve(*args: object, **kwargs: object) -> Resolved:
        return OUTDOOR.model_copy(update={"kind": "concert_hall"})

    monkeypatch.setattr(fetch_events, "_resolve", _resolve)
    doc = await fetch_events._keep_or_count(
        raw={},
        event=EV,
        counts=counts,
        embedder=_StubEmbedder(),
        db=None,
        geo_client=None,
        centre=(18.52, 73.85),
        bbox=(18.4, 73.7, 18.6, 73.9),
        nominatim_url="http://nominatim.invalid/search",
        city="Pune",
        today=NOW.date(),
        now=NOW,
    )
    assert doc is None
    assert counts["invalid"] == 1


async def test_a_valid_event_still_produces_a_document(monkeypatch: pytest.MonkeyPatch) -> None:
    counts: Counter[str] = Counter()

    async def _resolve(*args: object, **kwargs: object) -> Resolved:
        return OUTDOOR

    monkeypatch.setattr(fetch_events, "_resolve", _resolve)
    doc = await fetch_events._keep_or_count(
        raw={},
        event=EV,
        counts=counts,
        embedder=_StubEmbedder(),
        db=None,
        geo_client=None,
        centre=(18.52, 73.85),
        bbox=(18.4, 73.7, 18.6, 73.9),
        nominatim_url="http://nominatim.invalid/search",
        city="Pune",
        today=NOW.date(),
        now=NOW,
    )
    assert doc is not None
    assert counts["invalid"] == 0
