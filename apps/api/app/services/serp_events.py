"""SerpApi `google_events` payloads to safe, filtered events (P23 spec section 5.1, section 6).

Pure functions, no I/O: `scripts/fetch_events.py` does the fetching. Event titles and
descriptions are third-party free text from the open web, so everything that could reach a
prompt goes through the same hardened sanitizers OSM place names use (MASTERSPEC section 9.3),
at ingest, not at request time.
"""

import re
from typing import Any

from pydantic import ValidationError

from app.models.event import SerpEvent
from app.sanitize import MAX_TAGS_SUMMARY_LEN, sanitize_place_name, sanitize_tags_summary
from app.validators.lint import banned_hits

#: The `event=` fragment is a label, not the whole title: the full title lives in `name`.
MAX_EVENT_FRAGMENT_LEN = 24

# Words no fragment should end on once it has been truncated mid-phrase.
_TRAILING_CONNECTORS = frozenset(
    {"at", "in", "on", "of", "the", "a", "an", "and", "or", "for", "to", "with", "by", "from"}
)

# Money-ish text in a title or description. A quest must never require buying anything
# (MASTERSPEC section 1.4), so anything that smells of a price drops the event.
_PRICE = re.compile(
    r"₹|\brs\.?\b|\binr\b|\$|\bfrom \d|\bprice\b|\btickets?\b|\bentry fee\b", re.IGNORECASE
)


def _sub_dict(entry: dict[str, Any], key: str) -> dict[str, Any]:
    value = entry.get(key)
    return value if isinstance(value, dict) else {}


def parse_events(payload: dict[str, Any]) -> list[SerpEvent]:
    """Typed events from a SerpApi payload. Never raises: bad entries are skipped.

    A missing `events_results` means an exhausted quota or a query with no hits, which is a
    zero-event run, not an error (spec section 13).
    """
    out: list[SerpEvent] = []
    for entry in payload.get("events_results") or []:
        if not isinstance(entry, dict):
            continue
        date = _sub_dict(entry, "date")
        venue = _sub_dict(entry, "venue")
        address = entry.get("address")
        try:
            out.append(
                SerpEvent.model_validate(
                    {
                        "title": entry.get("title"),  # None fails validation, entry is skipped
                        "venue_name": venue.get("name") or "",
                        "address": [str(a) for a in address] if isinstance(address, list) else [],
                        "url": entry.get("link"),
                        "when_text": date.get("when") or "",
                        "start_date": date.get("start_date") or "",
                        "description": entry.get("description") or "",
                    }
                )
            )
        except ValidationError:
            continue
    return out


def sanitize_event(e: SerpEvent) -> SerpEvent:
    """A copy whose prompt-reachable strings are safe. `description` is never stored."""
    return e.model_copy(
        update={
            "title": sanitize_place_name(e.title),
            "venue_name": sanitize_place_name(e.venue_name) if e.venue_name else "",
            "when_text": sanitize_tags_summary(e.when_text),
        }
    )


def banned_terms_hit(e: SerpEvent) -> str | None:
    """The first V4 rule id that the title or description trips, else None."""
    hits = banned_hits(f"{e.title} {e.description}")
    return hits[0].rule if hits else None


def is_ticketed(payload_entry: dict[str, Any], e: SerpEvent) -> bool:
    """True when the listing sells admission, or reads like it does."""
    ticket_info = payload_entry.get("ticket_info")
    if isinstance(ticket_info, list):
        for info in ticket_info:
            link_type = info.get("link_type") if isinstance(info, dict) else None
            if isinstance(link_type, str) and "ticket" in link_type.lower():
                return True
    return bool(_PRICE.search(f"{e.title} {e.description}"))


def _fragment(key: str, value: str, max_value_len: int | None = None) -> str | None:
    value = re.sub(r"[:,]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if max_value_len is not None and len(value) > max_value_len:
        words = value[:max_value_len].split(" ")[:-1] or value[:max_value_len].split(" ")
        while words and words[-1].lower() in _TRAILING_CONNECTORS:
            words.pop()
        value = " ".join(words)
    return f"{key}={value}" if value else None


def event_tags_summary(e: SerpEvent, place_kind: str | None) -> str:
    """The freeform channel the model already reads (`leisure=park`), carrying the event.

    Fragments are assembled whole and dropped whole, so the 80-char cap can never cut
    `venue=Shaniwar Wada` down to something that reads as a different claim.
    """
    fragments = [
        _fragment("event", e.title.lower(), MAX_EVENT_FRAGMENT_LEN),
        _fragment("when", e.when_text.lower()),
        _fragment("venue", e.venue_name),
    ]
    if place_kind:
        fragments.append(_fragment("kind", place_kind))

    out = ""
    for fragment in (f for f in fragments if f):
        candidate = f"{out}; {fragment}" if out else fragment
        if len(candidate) <= MAX_TAGS_SUMMARY_LEN:
            out = candidate
    return sanitize_tags_summary(out)
