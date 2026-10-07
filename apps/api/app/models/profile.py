"""Profile and completion schemas (MASTERSPEC §5.3, §5.4, §6.1, §8)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import Category, Persona, VerificationMethod


class UserSettings(BaseModel):
    safe_mode: bool = True
    voice: bool = True


class RecentCompletion(BaseModel):
    quest_id: str
    completed_at: datetime
    title: str | None = None
    category: Category
    xp_awarded: int
    verification_method: VerificationMethod
    place_name: str | None = None
    minutes_outside: int = 0
    screen_share: float | None = None


class SkillProgress(BaseModel):
    xp: int = 0
    level: int = 0
    title: str | None = None
    next_level_xp: int  # total category XP needed for the next level


class Profile(BaseModel):
    persona: Persona = "chill"
    interests: list[str] = Field(default_factory=list)
    default_radius_m: int = 2500
    skills: dict[Category, SkillProgress]
    total_xp: int = 0
    level: int = 0
    next_level_xp: int = 120
    streak_days: int = 0
    quests_completed: int = 0
    settings: UserSettings = Field(default_factory=UserSettings)
    recent: list[RecentCompletion] = Field(default_factory=list)


class LevelUp(BaseModel):
    kind: Literal["category", "overall"]
    category: Category | None = None
    from_level: int
    to_level: int
    title: str | None = None


class CompletionResult(BaseModel):
    quest_id: str
    xp_awarded: int
    level_ups: list[LevelUp] = Field(default_factory=list)
    streak: int
    total_xp: int
    level: int
    within_radius: bool | None = None
    screen_share: float | None = None
    daily_cap_reached: bool = False
