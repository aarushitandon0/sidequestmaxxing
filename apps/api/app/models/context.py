"""Context Builder output (MASTERSPEC §7.1)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PartOfDay = Literal["early_morning", "morning", "afternoon", "evening", "night"]


class Weather(BaseModel):
    summary: str = "unknown"
    temp_c: float | None = None
    precip_prob: int | None = Field(default=None, ge=0, le=100)
    code: int | None = None
    thunderstorm: bool = False


class QuestContext(BaseModel):
    local_time: datetime
    part_of_day: PartOfDay
    weekday: str
    sunrise: datetime | None = None
    sunset: datetime | None = None
    daylight_minutes_left: int = Field(ge=0)  # 0 when it's already dark
    weather: Weather = Field(default_factory=Weather)
    indoor_only: bool = False
    indoor_reasons: list[str] = Field(default_factory=list)
