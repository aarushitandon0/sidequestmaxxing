"""Request schemas (MASTERSPEC §6.3, §6.4, profile settings)."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Mood, Persona, TravelMode, VerificationMethod
from app.sanitize import MAX_INTERESTS, round_coord, sanitize_interests, sanitize_note


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Coords(_Strict):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

    @field_validator("lat", "lng")
    @classmethod
    def _round(cls, v: float) -> float:
        return round_coord(v)


class QuestRequest(Coords):
    minutes_available: int = Field(ge=10, le=180)
    radius_m: int = Field(ge=300, le=6000)
    mood: Mood
    interests: list[str] = Field(default_factory=list, max_length=MAX_INTERESTS)
    persona: Persona = "chill"
    mode: TravelMode = "walk"
    local_time_iso: AwareDatetime

    @field_validator("interests", mode="before")
    @classmethod
    def _cap_raw(cls, v: object) -> object:
        # Reject absurd payloads early; per-item cleaning happens below.
        if isinstance(v, list) and any(not isinstance(i, str) or len(i) > 200 for i in v):
            raise ValueError("interests must be short strings")
        return v

    @field_validator("interests")
    @classmethod
    def _sanitize(cls, v: list[str]) -> list[str]:
        return sanitize_interests(v)


class VerificationResult(_Strict):
    method: VerificationMethod
    match: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    seen: str | None = Field(default=None, max_length=120)

    @field_validator("seen")
    @classmethod
    def _clean_seen(cls, v: str | None) -> str | None:
        return sanitize_note(v, 120) if v is not None else None


class CompletionRequest(_Strict):
    verification: VerificationResult
    elapsed_seconds: int = Field(ge=0, le=24 * 3600)
    screen_seconds: int = Field(ge=0, le=24 * 3600)
    checkin: Coords | None = None
    note: str | None = Field(default=None, max_length=200)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str | None) -> str | None:
        return sanitize_note(v) if v is not None else None


class SettingsUpdate(_Strict):
    persona: Persona | None = None
    interests: list[str] | None = Field(default=None, max_length=MAX_INTERESTS)
    default_radius_m: int | None = Field(default=None, ge=300, le=6000)
    voice: bool | None = None
    safe_mode: bool | None = None

    @field_validator("interests")
    @classmethod
    def _sanitize(cls, v: list[str] | None) -> list[str] | None:
        return sanitize_interests(v) if v is not None else None


__all__ = [
    "CompletionRequest",
    "Coords",
    "QuestRequest",
    "SettingsUpdate",
    "VerificationResult",
]
