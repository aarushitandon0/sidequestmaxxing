from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.services.sun import daylight_window, sun_times

IST = timezone(timedelta(hours=5, minutes=30))


def _minutes(dt: datetime) -> float:
    return dt.hour * 60 + dt.minute + dt.second / 60


def test_equator_equinox_is_about_twelve_hours() -> None:
    rise, sset = sun_times(0.0, 0.0, date(2026, 3, 20))
    assert rise is not None and sset is not None
    # Sunrise ~06:00 UTC, sunset ~18:10 UTC (refraction makes the day slightly > 12 h).
    assert _minutes(rise) == pytest.approx(6 * 60 + 4, abs=10)
    assert _minutes(sset) == pytest.approx(18 * 60 + 10, abs=10)
    assert (sset - rise) > timedelta(hours=12)


def test_pune_october_order_of_magnitude() -> None:
    # Pune (18.52N, 73.86E) on 7 Oct: sunrise ≈ 06:2x IST, sunset ≈ 18:1x IST.
    rise, sset = sun_times(18.52, 73.86, date(2026, 10, 7))
    assert rise is not None and sset is not None
    assert 6 * 60 + 5 <= _minutes(rise.astimezone(IST)) <= 6 * 60 + 40
    assert 17 * 60 + 55 <= _minutes(sset.astimezone(IST)) <= 18 * 60 + 35


def test_polar_cases() -> None:
    assert sun_times(80.0, 0.0, date(2026, 6, 21)) == (None, None)
    assert daylight_window(80.0, 0.0, datetime(2026, 6, 21, 12, tzinfo=UTC))[2] == 24 * 60
    assert daylight_window(80.0, 0.0, datetime(2026, 12, 21, 12, tzinfo=UTC))[2] == 0


@pytest.mark.parametrize(
    ("local", "expect_zero"),
    [
        (datetime(2026, 10, 7, 5, 0, tzinfo=IST), True),  # before sunrise
        (datetime(2026, 10, 7, 12, 0, tzinfo=IST), False),
        (datetime(2026, 10, 7, 17, 30, tzinfo=IST), False),
        (datetime(2026, 10, 7, 21, 0, tzinfo=IST), True),  # after sunset
        (datetime(2026, 10, 7, 23, 59, tzinfo=IST), True),
    ],
)
def test_daylight_window_pune(local: datetime, expect_zero: bool) -> None:
    _, _, left = daylight_window(18.52, 73.86, local)
    assert (left == 0) is expect_zero
    if not expect_zero:
        assert 0 < left < 13 * 60


def test_daylight_left_at_noon_pune_is_about_six_hours() -> None:
    _, sset, left = daylight_window(18.52, 73.86, datetime(2026, 10, 7, 12, 0, tzinfo=IST))
    assert sset is not None
    assert left == pytest.approx(6 * 60 + 15, abs=25)


def test_western_hemisphere_evening_crosses_utc_midnight() -> None:
    # San Francisco 17:00 PDT = 00:00 UTC next day; sun still up.
    pdt = timezone(timedelta(hours=-7))
    _, _, left = daylight_window(37.77, -122.42, datetime(2026, 6, 21, 17, 0, tzinfo=pdt))
    assert 100 < left < 240
