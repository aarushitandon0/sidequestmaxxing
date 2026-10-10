"""Google event date strings -> UTC windows, plus the daylight overlap filter.

SerpApi's `google_events` results carry human date strings in venue-local time
("Sat, Oct 11, 7:00 - 9:30 AM"), often with no year. Parsing is deliberately
regex-driven over the handful of shapes Google emits: an unrecognized string
returns `None` rather than a plausible-but-wrong datetime that would silently
place a quest on the wrong day.
"""

import calendar
import re
from datetime import UTC, date, datetime, timedelta

from app.services.sun import daylight_window, is_polar_day

DEFAULT_DURATION_MIN = 120
"""Assumed length of an event whose listing gives only a start time."""

MAX_DURATION_MIN = 12 * 60
"""Longest window we will believe. Anything longer means we read the string wrong."""

_MONTHS: dict[str, int] = {
    name.lower(): number for number, name in enumerate(calendar.month_abbr) if number
}
_MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_name) if number})

_DATE_RE = re.compile(
    r"\b(?P<mon>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2})(?:\s*,\s*(?P<year>\d{4}))?\b"
)
# `gl=in` prints the day first ("11 Oct"). Tried only after the month-first form, so a
# plain "Oct 11" is never re-read as day 11 of a month named "11".
_DATE_DMY_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3,9})\.?(?:\s*,?\s*(?P<year>\d{4}))?\b"
)
# A time needs a meridiem (Google always prints one); the first half of a range may
# borrow it from the second ("7:00 - 9:30 AM").
# Hyphen first so it is a literal inside the character class; the rest are the
# typographic dashes Google uses between a start and an end time.
_DASH = "[-{}]".format(
    "".join(chr(c) for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212))
)
_TIME_RANGE_RE = re.compile(
    r"\b(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<ap1>[ap]\.?m\.?)?"
    rf"\s*{_DASH}\s*"
    r"(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<ap2>[ap]\.?m\.?)\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap]\.?m\.?)\b", re.IGNORECASE)

_YEAR_CANDIDATE_OFFSETS = (-1, 0, 1)


def _to_24h(hour: int, meridiem: str | None) -> int | None:
    if meridiem is None:
        return hour if 0 <= hour <= 23 else None
    if not 1 <= hour <= 12:
        return None
    is_pm = meridiem.lower().startswith("p")
    if hour == 12:
        return 12 if is_pm else 0
    return hour + 12 if is_pm else hour


def _date_match(text: str) -> re.Match[str] | None:
    """The leftmost `<Month> <D>` or `<D> <Month>` whose month is a real month name.

    Both readings are tried and the leftmost wins, because each pattern can match noise
    inside the other's string: `"11 Oct 5:00 PM"` offers `Oct 5` to the month-first
    pattern, and `"7:00 - 9:30 AM"` offers `30 AM` to the day-first one. A day followed
    by `:` is a clock time, never a day of the month.
    """
    candidates = [
        match
        for pattern in (_DATE_RE, _DATE_DMY_RE)
        for match in pattern.finditer(text)
        if _MONTHS.get(match["mon"].lower()) is not None
        and not text[match.end("day") : match.end("day") + 1] == ":"
    ]
    return min(candidates, key=lambda m: m.start()) if candidates else None


def _parse_date(text: str, today: date) -> date | None:
    """First `<Month> <D>` or `<D> <Month>` in `text`, with the year inferred when absent."""
    match = _date_match(text)
    if match is None:
        return None
    month = _MONTHS[match["mon"].lower()]
    day = int(match["day"])
    if match["year"] is not None:
        try:
            return date(int(match["year"]), month, day)
        except ValueError:
            return None
    # No year: pick the candidate nearest `today`, so a December listing read in
    # January resolves backward to the December just gone rather than forward.
    best: date | None = None
    for offset in _YEAR_CANDIDATE_OFFSETS:
        try:
            candidate = date(today.year + offset, month, day)
        except ValueError:
            continue
        if best is None or abs((candidate - today).days) < abs((best - today).days):
            best = candidate
    return best


def _parse_times(text: str) -> tuple[tuple[int, int], tuple[int, int] | None] | None:
    """((start_h, start_m), (end_h, end_m) | None) in local 24h time."""
    span = _TIME_RANGE_RE.search(text)
    if span is not None:
        borrowed = span["ap1"] is None
        start_h = _to_24h(int(span["h1"]), span["ap1"] or span["ap2"])
        end_h = _to_24h(int(span["h2"]), span["ap2"])
        if start_h is None or end_h is None:
            return None
        if borrowed and start_h > end_h:
            # "11:00 - 1:00 PM" is 11:00-13:00: the start borrowed the wrong meridiem.
            start_h = (start_h + 12) % 24
        return (start_h, int(span["m1"] or 0)), (end_h, int(span["m2"] or 0))
    one = _TIME_RE.search(text)
    if one is None:
        return None
    hour = _to_24h(int(one["h"]), one["ap"])
    if hour is None:
        return None
    return (hour, int(one["m"] or 0)), None


def parse_event_window(
    start_date: str,
    when_text: str,
    *,
    today: date,
    tz_offset_min: int,
) -> tuple[datetime, datetime] | None:
    """UTC `(starts_at, ends_at)` for a Google event, or `None` if unparseable.

    `start_date` ("Oct 11") and `when_text` ("Sat, Oct 11, 7:00 - 9:30 AM") are both
    venue-local; `tz_offset_min` is the venue's offset from UTC in minutes (330 for Pune).
    """
    day = _parse_date(when_text, today) or _parse_date(start_date, today)
    if day is None:
        return None
    times = _parse_times(when_text) or _parse_times(start_date)
    start_hm, end_hm = times if times is not None else ((0, 0), None)
    offset = timedelta(minutes=tz_offset_min)
    starts_at = datetime(day.year, day.month, day.day, *start_hm, tzinfo=UTC) - offset
    if end_hm is None:
        return starts_at, starts_at + timedelta(minutes=DEFAULT_DURATION_MIN)
    ends_at = datetime(day.year, day.month, day.day, *end_hm, tzinfo=UTC) - offset
    if ends_at <= starts_at:
        # An overnight range ("9:00 PM - 1:00 AM") ends on the following local day.
        ends_at += timedelta(days=1)
    if ends_at - starts_at > timedelta(minutes=MAX_DURATION_MIN):
        # A window this long means the string was misread; refusing beats a wrong datetime.
        return None
    return starts_at, ends_at


def overlaps_daylight(starts_at: datetime, ends_at: datetime, lat: float, lng: float) -> bool:
    """True when any part of the event falls between sunrise and sunset at the venue."""
    sunrise, sunset, _ = daylight_window(lat, lng, starts_at)
    if sunrise is None or sunset is None:
        # Polar day/night: the sun either never sets or never rises.
        return is_polar_day(lat, starts_at.astimezone(UTC).date())
    return starts_at < sunset and ends_at > sunrise
