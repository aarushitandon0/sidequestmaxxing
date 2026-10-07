"""Profile schemas (MASTERSPEC §5.4, §6.1)."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Category, Persona, VerificationMethod


class UserSettings(BaseModel):
    safe_mode: bool = True
    voice: bool = True


class RecentCompletion(BaseModel):
    quest_id: str
    completed_at: datetime
    category: Category
    xp_awarded: int
    verification_method: VerificationMethod
    place_name: str | None = None


class Profile(BaseModel):
    persona: Persona = "chill"
    interests: list[str] = Field(default_factory=list)
    default_radius_m: int = 2500
    skills: dict[Category, int] = Field(default_factory=dict)
    total_xp: int = 0
    level: int = 0
    streak_days: int = 0
    settings: UserSettings = Field(default_factory=UserSettings)
    recent: list[RecentCompletion] = Field(default_factory=list)
