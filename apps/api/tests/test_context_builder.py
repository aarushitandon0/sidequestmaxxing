from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from app.agents.context_builder import build_context, indoor_reasons, part_of_day
from app.models.context import Weather
from app.models.requests import QuestRequest
from app.services.weather import WeatherClient, parse_forecast

IST = timezone(timedelta(hours=5, minutes=30))
NOW_LOCAL = datetime(2026, 10, 7, 15, 0, tzinfo=IST)  # 09:30 UTC
NOW_UTC = NOW_LOCAL.astimezone(UTC)
SUNRISE = datetime(2026, 10, 7, 0, 55, tzinfo=UTC)
SUNSET = datetime(2026, 10, 7, 12, 45, tzinfo=UTC)  # 18:15 IST


def payload(code: int = 1, temp: float = 29.0, probs: list[int] | None = None) -> dict[str, Any]:
    base = int(datetime(2026, 10, 7, tzinfo=UTC).timestamp())
    probs = probs if probs is not None else [10] * 48
    return {
        "current": {"time": int(NOW_UTC.timestamp()), "temperature_2m": temp, "weather_code": code},
        "hourly": {
            "time": [base + 3600 * i for i in range(48)],
            "precipitation_probability": probs,
        },
        "daily": {
            "time": [base, base + 86400],
            "sunrise": [int(SUNRISE.timestamp()), int(SUNRISE.timestamp()) + 86400],
            "sunset": [int(SUNSET.timestamp()), int(SUNSET.timestamp()) + 86400],
        },
    }


def req(**kw: Any) -> QuestRequest:
    data: dict[str, Any] = {
        "lat": 18.52, "lng": 73.856, "minutes_available": 60, "radius_m": 2500,
        "mood": "curious", "interests": ["birds"], "local_time_iso": NOW_LOCAL.isoformat(),
    }  # fmt: skip
    data.update(kw)
    return QuestRequest.model_validate(data)


class Recorder:
    def __init__(self, handler: Any) -> None:
        self.calls: list[httpx.Request] = []
        self.handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        result: httpx.Response = self.handler(request)
        return result


def client_for(handler: Any) -> tuple[WeatherClient, Recorder]:
    rec = Recorder(handler)
    return WeatherClient(httpx.AsyncClient(transport=httpx.MockTransport(rec))), rec


# --- pure helpers --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hour", "part"),
    [(4, "night"), (5, "early_morning"), (9, "morning"), (12, "afternoon"), (17, "evening"),
     (19, "evening"), (20, "night"), (23, "night")],
)  # fmt: skip
def test_part_of_day(hour: int, part: str) -> None:
    assert part_of_day(hour) == part


@pytest.mark.parametrize(
    ("weather", "daylight", "reasons"),
    [
        (Weather(), 300, []),
        (Weather(thunderstorm=True), 300, ["thunderstorm"]),
        (Weather(precip_prob=70), 300, ["rain likely"]),
        (Weather(precip_prob=69), 300, []),
        (Weather(temp_c=38.0), 300, ["extreme heat"]),
        (Weather(temp_c=37.9), 300, []),
        (Weather(), 34, ["dark"]),
        (Weather(), 35, []),
        (Weather(thunderstorm=True, temp_c=40), 0, ["thunderstorm", "extreme heat", "dark"]),
    ],
)
def test_indoor_reasons(weather: Weather, daylight: int, reasons: list[str]) -> None:
    assert indoor_reasons(weather, daylight) == reasons


def test_parse_forecast_takes_worst_precip_in_window() -> None:
    probs = [10] * 48
    probs[10] = 80  # 10:00-11:00 UTC, inside a 60 min window from 09:30
    probs[12] = 95  # 12:00 UTC, outside the window
    f = parse_forecast(payload(probs=probs), NOW_UTC, 60)
    assert f.weather.precip_prob == 80
    assert f.weather.summary == "mainly clear"
    assert (f.sunrise, f.sunset) == (SUNRISE, SUNSET)


def test_parse_forecast_handles_empty_payload() -> None:
    f = parse_forecast({}, NOW_UTC, 60)
    assert f.weather == Weather()
    assert f.sunrise is None


# --- context builder -----------------------------------------------------------------------------


async def test_clear_afternoon() -> None:
    wc, rec = client_for(lambda r: httpx.Response(200, json=payload()))
    ctx = await build_context(req(), wc)
    assert ctx.part_of_day == "afternoon" and ctx.weekday == "Wednesday"
    assert ctx.daylight_minutes_left == 195  # 09:30 → 12:45 UTC
    assert ctx.indoor_only is False
    assert ctx.weather.temp_c == 29.0
    params = rec.calls[0].url.params
    assert params["timeformat"] == "unixtime" and params["latitude"] == "18.52"
    assert "precipitation_probability" in params["hourly"]


async def test_thunderstorm_forces_indoor() -> None:
    wc, _ = client_for(lambda r: httpx.Response(200, json=payload(code=95)))
    ctx = await build_context(req(), wc)
    assert ctx.indoor_only and ctx.indoor_reasons == ["thunderstorm"]
    assert ctx.weather.summary == "thunderstorm"


async def test_heat_forces_indoor() -> None:
    wc, _ = client_for(lambda r: httpx.Response(200, json=payload(temp=41)))
    assert (await build_context(req(), wc)).indoor_reasons == ["extreme heat"]


async def test_dusk_sets_dark_reason() -> None:
    wc, _ = client_for(lambda r: httpx.Response(200, json=payload()))
    dusk = datetime(2026, 10, 7, 17, 50, tzinfo=IST)  # 25 min before sunset
    ctx = await build_context(req(local_time_iso=dusk.isoformat()), wc)
    assert ctx.daylight_minutes_left == 25
    assert ctx.indoor_reasons == ["dark"]


async def test_night_has_zero_daylight() -> None:
    wc, _ = client_for(lambda r: httpx.Response(200, json=payload()))
    night = datetime(2026, 10, 7, 22, 0, tzinfo=IST)
    ctx = await build_context(req(local_time_iso=night.isoformat()), wc)
    assert ctx.daylight_minutes_left == 0 and ctx.part_of_day == "night" and ctx.indoor_only


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, text="<html>oops</html>"),
        lambda r: (_ for _ in ()).throw(httpx.ConnectTimeout("slow")),
    ],
)
async def test_open_meteo_down_falls_back_to_unknown_weather_and_solar_calc(handler: Any) -> None:
    wc, _ = client_for(handler)
    ctx = await build_context(req(), wc)
    assert ctx.weather == Weather()
    assert ctx.sunset is not None  # offline solar calculation
    assert 150 < ctx.daylight_minutes_left < 240
    assert ctx.indoor_only is False


async def test_cache_reuses_response_for_nearby_points() -> None:
    wc, rec = client_for(lambda r: httpx.Response(200, json=payload()))
    await build_context(req(lat=18.521, lng=73.856), wc)
    await build_context(req(lat=18.523, lng=73.857), wc)  # same 0.01° cell
    assert len(rec.calls) == 1
    await build_context(req(lat=18.60, lng=73.856), wc)
    assert len(rec.calls) == 2
