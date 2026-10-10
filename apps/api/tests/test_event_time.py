"""Google event date strings → UTC windows, and the daylight overlap filter."""

from datetime import UTC, date, datetime

from app.services.event_time import DEFAULT_DURATION_MIN, overlaps_daylight, parse_event_window

TODAY = date(2026, 10, 11)


def test_parses_date_with_explicit_time_range() -> None:
    w = parse_event_window("Oct 11", "Sat, Oct 11, 7:00 – 9:30 AM", today=TODAY, tz_offset_min=330)
    assert w == (
        datetime(2026, 10, 11, 1, 30, tzinfo=UTC),
        datetime(2026, 10, 11, 4, 0, tzinfo=UTC),
    )


def test_yearless_string_assumes_current_year_not_1900() -> None:
    w = parse_event_window("Oct 11", "Sat, Oct 11, 7:00 AM", today=TODAY, tz_offset_min=330)
    assert w is not None
    assert w[0].year == 2026


def test_yearless_december_date_in_january_rolls_to_next_year() -> None:
    w = parse_event_window(
        "Dec 28", "Sun, Dec 28, 9:00 AM", today=date(2027, 1, 2), tz_offset_min=330
    )
    assert w is not None
    assert (w[0].year, w[0].month) == (2026, 12)


def test_start_only_gets_default_two_hour_duration() -> None:
    w = parse_event_window("Oct 11", "Sat, Oct 11, 7:00 AM", today=TODAY, tz_offset_min=330)
    assert w is not None
    starts, ends = w
    assert (ends - starts).total_seconds() == DEFAULT_DURATION_MIN * 60


def test_unparseable_returns_none() -> None:
    assert (
        parse_event_window("", "every other Thursday-ish", today=TODAY, tz_offset_min=330) is None
    )


def test_daytime_event_overlaps_daylight_in_pune() -> None:
    assert overlaps_daylight(
        datetime(2026, 10, 11, 1, 30, tzinfo=UTC),
        datetime(2026, 10, 11, 4, 0, tzinfo=UTC),
        18.52,
        73.86,
    )


def test_late_night_event_does_not_overlap_daylight() -> None:
    assert not overlaps_daylight(
        datetime(2026, 10, 11, 17, 0, tzinfo=UTC),
        datetime(2026, 10, 11, 19, 0, tzinfo=UTC),
        18.52,
        73.86,
    )
