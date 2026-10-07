"""Context Builder (MASTERSPEC §7.1). Deterministic; weather is best-effort.

Daylight comes from Open-Meteo when available, else from the offline solar calculation, so the
daylight safety rules (§9.1, V10) never depend on a vendor being up.
"""

from datetime import UTC, datetime

from app.models.context import PartOfDay, QuestContext, Weather
from app.models.requests import QuestRequest
from app.observability import span
from app.services.sun import daylight_window
from app.services.weather import WeatherClient
from app.validators.core import DAYLIGHT_BUFFER_MIN

PRECIP_INDOOR_PCT = 70
HEAT_INDOOR_C = 38.0
MIN_QUEST_MIN = 5


def part_of_day(hour: int) -> PartOfDay:
    if 5 <= hour < 8:
        return "early_morning"
    if 8 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 20:
        return "evening"
    return "night"


def indoor_reasons(weather: Weather, daylight_minutes_left: int) -> list[str]:
    reasons: list[str] = []
    if weather.thunderstorm:
        reasons.append("thunderstorm")
    if weather.precip_prob is not None and weather.precip_prob >= PRECIP_INDOOR_PCT:
        reasons.append("rain likely")
    if weather.temp_c is not None and weather.temp_c >= HEAT_INDOOR_C:
        reasons.append("extreme heat")
    if daylight_minutes_left < MIN_QUEST_MIN + DAYLIGHT_BUFFER_MIN:
        reasons.append("dark")
    return reasons


async def build_context(
    req: QuestRequest, weather_client: WeatherClient, now: datetime | None = None
) -> QuestContext:
    local_now = req.local_time_iso if now is None else now.astimezone(req.local_time_iso.tzinfo)
    with span("context.build") as s:
        forecast = await weather_client.forecast(
            req.lat, req.lng, local_now.astimezone(UTC), req.minutes_available
        )
        weather = forecast.weather if forecast else Weather()

        sunrise, sunset, left = daylight_window(req.lat, req.lng, local_now)
        if forecast and forecast.sunrise and forecast.sunset:
            now_utc = local_now.astimezone(UTC)
            sunrise, sunset = forecast.sunrise, forecast.sunset
            in_day = sunrise <= now_utc < sunset
            left = int((sunset - now_utc).total_seconds() // 60) if in_day else 0

        reasons = indoor_reasons(weather, left)
        s.set_data("weather_source", "open-meteo" if forecast else "none")
        s.set_data("indoor_only", bool(reasons))
        return QuestContext(
            local_time=local_now,
            part_of_day=part_of_day(local_now.hour),
            weekday=local_now.strftime("%A"),
            sunrise=sunrise,
            sunset=sunset,
            daylight_minutes_left=max(0, left),
            weather=weather,
            indoor_only=bool(reasons),
            indoor_reasons=reasons,
        )
