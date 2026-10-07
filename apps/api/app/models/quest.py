"""Quest schemas (MASTERSPEC §6.2).

`QuestDraft` holds ONLY the fields the LLM (or fallback engine) may write. It forbids extra
keys, so an LLM that tries to set xp/rarity/id fails V1. `Quest` adds server-owned fields.
"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import Category, Rarity, VerificationMethod


class QuestVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: VerificationMethod
    photo_prompt: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _photo_needs_prompt(self) -> Self:
        if self.method == "photo" and not (self.photo_prompt and self.photo_prompt.strip()):
            raise ValueError("photo verification requires a photo_prompt")
        return self


class QuestDraft(BaseModel):
    """LLM-owned fields only."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=3, max_length=60)
    category: Category
    briefing: str = Field(min_length=40, max_length=360)
    objective: str = Field(min_length=5, max_length=140)
    place_id: str | None = None
    est_minutes: int = Field(ge=5, le=180)
    verification: QuestVerification
    safety_note: str = Field(min_length=1, max_length=140)
    off_screen_tip: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _placeless_methods(self) -> Self:
        if self.place_id is None and self.verification.method == "checkin":
            raise ValueError("place-less quests must use photo or honor verification")
        return self


class PlaceRef(BaseModel):
    id: str
    name: str
    lat: float
    lng: float


class Quest(QuestDraft):
    """Full quest as returned to the client. Server fills id/rarity/xp/distance/place."""

    id: str
    rarity: Rarity
    xp: int = Field(ge=0)
    distance_m: int | None = None
    place: PlaceRef | None = None


def llm_json_schema() -> dict[str, Any]:
    """JSON schema for constrained decoding of LLM output (server-owned fields excluded).

    Every property is marked required (nullable ones stay nullable), so the grammar makes the
    model write `place_id: null` explicitly instead of silently omitting it.
    """
    schema = QuestDraft.model_json_schema()
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if "properties" in obj:
            obj["required"] = list(obj["properties"])
    return schema
