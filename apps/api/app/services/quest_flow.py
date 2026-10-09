"""Quest generation orchestration (MASTERSPEC §3.1, P7).

sanitize (request model) → Context Builder → Scout → Quest Master (→ validators → retry →
fallback) → server fields (id, rarity, xp preview, distance, hydrated place) → save → return.

Rarity/XP are computed here from §8 only; the model never sets them. Without a "big quest
day" opt-in in the request contract, legendary quests are never offered: quests are capped
at the rare-tier 120 minutes (DECISIONS D-35, ambiguity A3).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.agents.context_builder import build_context
from app.agents.quest_master import QuestMasterInput, Source, run_quest_master
from app.agents.scout import scout
from app.errors import db_unavailable
from app.models.quest import PlaceRef, Quest, QuestDraft
from app.models.requests import QuestRequest
from app.observability import name_transaction, tag_outcome
from app.services.db import Doc
from app.services.embeddings import Embedder
from app.services.game import RARE_MAX_MINUTES, rarity_for, xp_preview
from app.services.llm_client import LLMClient
from app.services.places_repo import Candidate
from app.services.quests_repo import insert_quest, new_quest_doc
from app.services.weather import WeatherClient

log = logging.getLogger("sqm.quests")

#: Response header on POST /v1/quests/generate: "llm" or "fallback" (MASTERSPEC §6.1).
QUEST_SOURCE_HEADER = "X-Quest-Source"


@dataclass(frozen=True)
class Generated:
    """A generated quest plus how it was produced.

    `source` is server-only bookkeeping, not part of the quest schema: the router returns it
    as the `X-Quest-Source` response header so a field test can count fallback quests
    (MASTERSPEC §6.1) without the client ever seeing model internals.
    """

    quest: Quest
    source: Source


@dataclass(frozen=True)
class GenerateDeps:
    db: AsyncDatabase[Doc]
    embedder: Embedder
    weather: WeatherClient
    llm: LLMClient | None
    fallback_on_llm_error: bool = True


def hydrate(draft: QuestDraft, candidates: list[Candidate], quest_id: str) -> Quest:
    place = next((c for c in candidates if c.id == draft.place_id), None)
    distance = place.distance_m if place else None
    rarity = rarity_for(draft.est_minutes, distance)
    return Quest(
        **draft.model_dump(),
        id=quest_id,
        rarity=rarity,
        xp=xp_preview(draft.est_minutes, rarity, draft.verification.method),
        distance_m=distance,
        place=PlaceRef(id=place.id, name=place.name, lat=place.lat, lng=place.lng)
        if place
        else None,
    )


async def generate_quest(
    req: QuestRequest, device_id: str, deps: GenerateDeps, now: datetime | None = None
) -> Generated:
    now = now or datetime.now(UTC)
    name_transaction("quests.generate")

    # Server clock in the player's UTC offset: daylight rules never trust the client clock.
    ctx = await build_context(req, deps.weather, now=now)
    found = await scout(req, ctx, device_id, deps.db, deps.embedder, now=now)

    quest_id = str(uuid.uuid4())
    result = await run_quest_master(
        QuestMasterInput(
            context=ctx,
            persona=req.persona,
            mood=req.mood,
            interests=req.interests,
            minutes_available=min(req.minutes_available, RARE_MAX_MINUTES),
            candidates=found.candidates,
            recent_categories=found.recent_categories,
            recent_embeddings=found.recent_embeddings,
            seed=uuid.UUID(quest_id).int % (2**31),
        ),
        deps.llm,
        deps.embedder,
        fallback_on_error=deps.fallback_on_llm_error,
    )
    quest = hydrate(result.quest, found.candidates, quest_id)

    tag_outcome(result.source, result.retries, result.validator_failures)
    log.info(
        "quest generated",
        extra={
            "source": result.source,
            "retries": result.retries,
            "validator_failures": result.validator_failures,
            "fallback_reason": result.fallback_reason,
            "llm_latency_ms": result.latency_ms,
            "candidates": len(found.candidates),
        },
    )

    doc = new_quest_doc(quest, device_id, req, source=result.source, model=result.model, now=now)
    try:
        await insert_quest(deps.db, doc)
    except PyMongoError as exc:
        log.warning("quest save failed", extra={"error_type": type(exc).__name__})
        raise db_unavailable() from exc
    return Generated(quest=quest, source=result.source)
