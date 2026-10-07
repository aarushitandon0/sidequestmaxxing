"""Open-Meteo forecast client (no API key). 3 s timeout, 5-minute cache per ~1 km cell.

Endpoint/params from https://open-meteo.com/en/docs (re-check: the docs site was blocked from
the build container, see docs/DECISIONS.md). Uses `timeformat=unixtime` so no timezone parsing.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.models.context import Weather

log = logging.getLogger("sqm.weather")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_S = 300
CACHE_MAX = 2048

# WMO weather interpretation codes → short spoken-friendly summary.
_WMO: dict[int, str] = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle",
    57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "rain showers", 81: "rain showers", 82: "violent rain showers", 85: "snow showers",
    86: "snow showers", 95: "thunderstorm", 96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}  # fmt: skip
THUNDERSTORM_CODES = frozenset({95, 96, 99})


@dataclass(frozen=True)
class Forecast:
    weather: Weather
    sunrise: datetime | None
    sunset: datetime | None


def _cache_key(lat: float, lng: float) -> tuple[float, float]:
    return round(lat, 2), round(lng, 2)


def _utc(ts: Any) -> datetime | None:
    return datetime.fromtimestamp(int(ts), UTC) if isinstance(ts, int | float) else None


def parse_forecast(payload: dict[str, Any], now: datetime, window_min: int) -> Forecast:
    current = payload.get("current") or {}
    code = current.get("weather_code")
    code = int(code) if isinstance(code, int | float) else None
    temp = current.get("temperature_2m")

    # Worst precipitation probability over the quest window (hourly slots).
    precip: int | None = None
    hourly = payload.get("hourly") or {}
    times, probs = hourly.get("time") or [], hourly.get("precipitation_probability") or []
    now_ts, end_ts = now.timestamp(), now.timestamp() + window_min * 60
    for ts, p in zip(times, probs, strict=False):
        if p is None or not isinstance(ts, int | float):
            continue
        if ts + 3600 > now_ts and ts <= end_ts:
            precip = max(precip or 0, int(p))

    # Today's sunrise/sunset: the pair whose sunset is still ahead, else the last pair.
    daily = payload.get("daily") or {}
    rises, sets = daily.get("sunrise") or [], daily.get("sunset") or []
    sunrise = sunset = None
    for r, s in zip(rises, sets, strict=False):
        sunrise, sunset = _utc(r), _utc(s)
        if sunset and sunset > now:
            break

    weather = Weather(
        summary=_WMO.get(code, "unknown") if code is not None else "unknown",
        temp_c=float(temp) if isinstance(temp, int | float) else None,
        precip_prob=precip,
        code=code,
        thunderstorm=code in THUNDERSTORM_CODES,
    )
    return Forecast(weather, sunrise, sunset)


class WeatherClient:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        base_url: str = OPEN_METEO_URL,
        timeout_s: float = 3.0,
    ) -> None:
        self._client = client
        self.base_url = base_url
        self.timeout = httpx.Timeout(timeout_s)
        self._cache: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}

    async def _get(self, lat: float, lng: float) -> dict[str, Any]:
        params: dict[str, str | float | int] = {
            "latitude": lat,
            "longitude": lng,
            "current": "temperature_2m,weather_code",
            "hourly": "precipitation_probability",
            "daily": "sunrise,sunset",
            "timezone": "GMT",
            "timeformat": "unixtime",
            "forecast_days": 2,
        }
        if self._client is not None:
            res = await self._client.get(self.base_url, params=params, timeout=self.timeout)
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(self.base_url, params=params)
        res.raise_for_status()
        data: dict[str, Any] = res.json()
        return data

    async def forecast(
        self, lat: float, lng: float, now: datetime, window_min: int
    ) -> Forecast | None:
        """None when Open-Meteo is unreachable or returns junk (caller degrades gracefully)."""
        key = _cache_key(lat, lng)
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            payload = hit[1]
        else:
            try:
                payload = await self._get(*key)
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("open-meteo unavailable", extra={"error_type": type(exc).__name__})
                return None
            if len(self._cache) >= CACHE_MAX:
                self._cache.clear()
            self._cache[key] = (time.monotonic(), payload)
        try:
            return parse_forecast(payload, now, window_min)
        except (TypeError, ValueError) as exc:
            log.warning("open-meteo payload unparsable", extra={"error_type": type(exc).__name__})
            return None


_default_client: WeatherClient | None = None


def get_weather_client() -> WeatherClient:
    global _default_client
    if _default_client is None:
        _default_client = WeatherClient()
    return _default_client
