"""Weekly Chronicle response (MASTERSPEC §3.3, §5.6, §7.7)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.validators.recap import RecapStats

RecapSourceOut = Literal["llm", "fallback", "empty"]


class WeeklyRecap(BaseModel):
    id: str | None  # None for an empty week (nothing stored, nothing to speak)
    week_start: date  # first local day of the 7-day window
    week_end: date  # today (local)
    text: str
    stats: RecapStats
    source: RecapSourceOut
    created_at: datetime | None
