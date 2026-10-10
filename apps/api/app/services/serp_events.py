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


_BARE_TIME = re.compile(r"^(?P<h>\d{1,2})(?::(?P<m>\d{2}))?$")


def _with_meridiem(time_text: str) -> str:
    """A bare `H[:MM]` gets an explicit meridiem; anything else is returned untouched.

    The Google Search events pack prints venue-local time with no AM/PM (`"5:00"`), and
    `event_time` refuses a time it cannot read, so the assumption is made here once, at the
    ingest boundary, rather than hidden in the parser. Hours 1-11 are read as PM because
    these listings are overwhelmingly evening shows; 12 is noon. A morning event mislabelled
    this way fails the daylight filter and is dropped, which is the safe direction.
    """
    match = _BARE_TIME.match(time_text.strip())
    if match is None:
        return time_text
    hour = int(match["h"])
    if not 1 <= hour <= 12:
        return time_text
    return f"{hour}:{match['m'] or '00'} PM"


def _date_and_when(entry: dict[str, Any]) -> tuple[str, str]:
    """`(start_date, when_text)` from either entry shape.

    Legacy `google_events` nested both under `date`; the Google Search events pack gives a
    bare `date` string and a separate `time`.
    """
    date_value = entry.get("date")
    if isinstance(date_value, dict):
        return str(date_value.get("start_date") or ""), str(date_value.get("when") or "")
    start_date = str(date_value or "").strip()
    time_text = _with_meridiem(str(entry.get("time") or "").strip())
    when_text = " ".join(part for part in (start_date, time_text) if part)
    return start_date, when_text


def parse_events(payload: dict[str, Any]) -> list[SerpEvent]:
    """Typed events from a SerpApi payload. Never raises: bad entries are skipped.

    A missing `events_results` means an exhausted quota or a query with no hits, which is a
    zero-event run, not an error (spec section 13).
    """
    out: list[SerpEvent] = []
    for entry in payload.get("events_results") or []:
        if not isinstance(entry, dict):
            continue
        venue = _sub_dict(entry, "venue")
        address = entry.get("address")
        address_lines = [str(a) for a in address] if isinstance(address, list) else []
        start_date, when_text = _date_and_when(entry)
        try:
            out.append(
                SerpEvent.model_validate(
                    {
                        "title": entry.get("title"),  # None fails validation, entry is skipped
                        # No `venue` object in the Google Search shape: its first address
                        # line is the venue ("Balagandharv Rang Mandir", "Shivajinagar").
                        "venue_name": venue.get("name") or next(iter(address_lines), ""),
                        "address": address_lines,
                        "url": entry.get("link"),
                        "when_text": when_text,
                        "start_date": start_date,
                        "description": entry.get("description") or "",
                    }
                )
            )
        except ValidationError:
            continue
    return out


def safe_listing_url(url: str | None) -> str | None:
    """`url` when it is a plain http(s) link, else None.

    The listing URL is third-party text that the web app renders as an `href`, so a
    `javascript:` or `data:` scheme would be one tap from running script in our own origin.
    """
    if not url:
        return None
    return url if re.match(r"^https?://", url.strip(), re.IGNORECASE) else None


def sanitize_event(e: SerpEvent) -> SerpEvent:
    """A copy whose prompt-reachable strings are safe. `description` is never stored."""
    return e.model_copy(
        update={
            "title": sanitize_place_name(e.title),
            "venue_name": sanitize_place_name(e.venue_name) if e.venue_name else "",
            "when_text": sanitize_tags_summary(e.when_text),
            "url": safe_listing_url(e.url),
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
    # `;` and `=` are the separators of this channel: a value carrying them could forge a
    # field the model reads ("when=... ; kind=temple"), so they go the way of `:` and `,`.
    value = re.sub(r"[:,;=]", " ", value)
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
