"""One serialisable context record ↔ the production Quest Master input.

A record is what make_contexts.py writes and every later stage reads:
{"id", "split", "area", "input": {context, persona, mood, interests, minutes_available,
recent_categories, candidates}}. `messages()` uses the production prompt builder, so the
training chat is byte-identical to what the API sends at serving time.
"""

from typing import Any

import common  # noqa: F401  (puts apps/api on sys.path)

from app.agents.fallback_engine import FallbackInput
from app.agents.quest_master import QuestMasterInput, build_messages
from app.models.context import QuestContext
from app.services.places_repo import Candidate
from app.validators.core import ValidationContext


def to_input(record: dict[str, Any]) -> QuestMasterInput:
    i = record["input"]
    return QuestMasterInput(
        context=QuestContext.model_validate(i["context"]),
        persona=i["persona"],
        mood=i["mood"],
        interests=tuple(i["interests"]),
        minutes_available=i["minutes_available"],
        candidates=tuple(Candidate.model_validate(c) for c in i["candidates"]),
        recent_categories=tuple(i["recent_categories"]),
    )


def validation_context(record: dict[str, Any]) -> ValidationContext:
    return to_input(record).validation_context()


def messages(record: dict[str, Any]) -> list[dict[str, str]]:
    """[system (production prompt), user (production JSON format)]."""
    return build_messages(to_input(record))


def fallback_input(record: dict[str, Any], seed: int = 0) -> FallbackInput:
    inp = to_input(record)
    return FallbackInput(
        minutes_available=inp.minutes_available,
        persona=inp.persona,
        mood=inp.mood,
        interests=inp.interests,
        candidates=inp.candidates,
        recent_categories=inp.recent_categories,
        indoor_only=inp.context.indoor_only,
        daylight_minutes_left=inp.context.daylight_minutes_left,
        seed=seed,
    )
