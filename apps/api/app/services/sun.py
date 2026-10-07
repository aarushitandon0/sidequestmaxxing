"""Offline sunrise/sunset (NOAA general solar position approximation).

Fallback for when Open-Meteo is unreachable, so daylight rules never depend on a vendor.
Accuracy is a few minutes at mid/low latitudes, which is plenty with a 30-minute buffer.
"""

import math
from datetime import UTC, date, datetime, timedelta

_ZENITH_DEG = 90.833  # includes refraction + solar disc radius


def sun_times(lat: float, lng: float, day: date) -> tuple[datetime | None, datetime | None]:
    """(sunrise, sunset) in UTC for the UTC calendar `day`. (None, None) = polar day/night."""
    doy = day.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (doy - 1)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    phi = math.radians(lat)
    cos_ha = math.cos(math.radians(_ZENITH_DEG)) / (math.cos(phi) * math.cos(decl)) - math.tan(
        phi
    ) * math.tan(decl)
    if cos_ha > 1 or cos_ha < -1:
        return None, None
    ha = math.degrees(math.acos(cos_ha))
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    sunrise_min = 720 - 4 * (lng + ha) - eqtime
    sunset_min = 720 - 4 * (lng - ha) - eqtime
    return midnight + timedelta(minutes=sunrise_min), midnight + timedelta(minutes=sunset_min)


def is_polar_day(lat: float, day: date) -> bool:
    """True when the sun never sets (only meaningful when sun_times returns None)."""
    north_summer = 80 <= day.timetuple().tm_yday <= 266
    return (lat > 0) == north_summer


def daylight_window(
    lat: float, lng: float, now: datetime
) -> tuple[datetime | None, datetime | None, int]:
    """(sunrise, sunset, minutes_of_daylight_left) for the local day containing `now`."""
    now_utc = now.astimezone(UTC)
    # The local day can straddle two UTC days; check yesterday/today/tomorrow and pick the
    # window that contains or follows `now`.
    for offset in (-1, 0, 1):
        rise, sset = sun_times(lat, lng, (now_utc + timedelta(days=offset)).date())
        if rise is None or sset is None:
            if offset == 0:
                left = 24 * 60 if is_polar_day(lat, now_utc.date()) else 0
                return None, None, left
            continue
        if rise <= now_utc < sset:
            return rise, sset, int((sset - now_utc).total_seconds() // 60)
        if now_utc < rise:
            return rise, sset, 0
    return None, None, 0
