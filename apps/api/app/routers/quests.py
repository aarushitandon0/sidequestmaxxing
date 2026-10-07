"""Quest endpoints: generate, accept, skip (MASTERSPEC §6.1, §3.1). Complete lives in P10."""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.agents.quest_master import LLMUnavailableError
from app.deps import (
    DeviceId,
    Now,
    get_db,
    get_embedder_dep,
    get_llm_client,
    get_weather_client_dep,
)
from app.errors import ApiError, db_unavailable
from app.models.quest import Quest, QuestDraft
from app.models.requests import QuestRequest
from app.ratelimit import GENERATE_LIMIT, QUEST_ACTION_LIMIT, limiter
from app.services.db import Doc
from app.services.embeddings import Embedder
from app.services.llm_client import LLMClient
from app.services.memories_repo import upsert_memory
from app.services.quest_flow import GenerateDeps, generate_quest
from app.services.quests_repo import QuestStatus, get_quest, transition
from app.services.weather import WeatherClient
from app.validators.core import quest_memory_text

log = logging.getLogger("sqm.quests")
router = APIRouter(prefix="/v1/quests", tags=["quests"])

Db = Annotated[AsyncDatabase[Doc], Depends(get_db)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder_dep)]


class QuestState(BaseModel):
    id: str
    status: QuestStatus
    accepted_at: datetime | None = None
    expires_at: datetime


def _state(doc: Doc) -> QuestState:
    return QuestState(
        id=doc["_id"],
        status=doc["status"],
        accepted_at=doc.get("accepted_at"),
        expires_at=doc["expires_at"],
    )


def not_found() -> ApiError:
    return ApiError(404, "quest_not_found", "That quest isn't in your quest log.")


def wrong_state(status: str) -> ApiError:
    return ApiError(409, "invalid_quest_state", f"This quest is already {status}.")


async def _load(db: AsyncDatabase[Doc], quest_id: str, device_id: str) -> Doc:
    try:
        doc = await get_quest(db, quest_id, device_id)
    except PyMongoError as exc:
        raise db_unavailable() from exc
    if doc is None:
        raise not_found()
    return doc


async def _move(
    db: AsyncDatabase[Doc],
    quest_id: str,
    device_id: str,
    from_statuses: list[QuestStatus],
    updates: dict[str, Any],
) -> Doc | None:
    try:
        return await transition(db, quest_id, device_id, from_statuses, updates)
    except PyMongoError as exc:
        raise db_unavailable() from exc


@router.post("/generate", response_model=Quest)
@limiter.limit(GENERATE_LIMIT)
async def generate(
    request: Request,
    body: QuestRequest,
    device_id: DeviceId,
    db: Db,
    embedder: EmbedderDep,
    weather: Annotated[WeatherClient, Depends(get_weather_client_dep)],
    llm: Annotated[LLMClient | None, Depends(get_llm_client)],
    now: Now,
) -> Quest:
    deps = GenerateDeps(
        db=db,
        embedder=embedder,
        weather=weather,
        llm=llm,
        fallback_on_llm_error=request.app.state.settings.fallback_on_llm_error,
    )
    try:
        return await generate_quest(body, device_id, deps, now=now)
    except LLMUnavailableError as exc:
        raise ApiError(503, "llm_unavailable", "The Dungeon Master is resting.") from exc


@router.post("/{quest_id}/accept", response_model=QuestState)
@limiter.limit(QUEST_ACTION_LIMIT)
async def accept(
    request: Request, quest_id: str, device_id: DeviceId, db: Db, now: Now
) -> QuestState:
    doc = await _load(db, quest_id, device_id)
    if doc["status"] == "accepted":
        return _state(doc)  # idempotent: keep the original accepted_at (timer source)
    if doc["status"] != "offered":
        raise wrong_state(doc["status"])
    if now >= doc["expires_at"]:
        await _move(db, quest_id, device_id, ["offered"], {"status": "expired"})
        raise ApiError(409, "quest_expired", "This quest expired. Ask for a fresh one.")
    moved = await _move(db, quest_id, device_id, ["offered"], {"status": "accepted",
                                                                 "accepted_at": now})  # fmt: skip
    if moved is None:  # raced with another request; report the state that won
        doc = await _load(db, quest_id, device_id)
        if doc["status"] == "accepted":
            return _state(doc)
        raise wrong_state(doc["status"])
    return _state(moved)


@router.post("/{quest_id}/skip", response_model=QuestState)
@limiter.limit(QUEST_ACTION_LIMIT)
async def skip(
    request: Request,
    quest_id: str,
    device_id: DeviceId,
    db: Db,
    embedder: EmbedderDep,
    now: Now,
) -> QuestState:
    """No penalty. Records a memory so the same place/theme isn't offered again for 14 days."""
    doc = await _load(db, quest_id, device_id)
    if doc["status"] == "skipped":
        return _state(doc)
    if doc["status"] not in ("offered", "accepted"):
        raise wrong_state(doc["status"])
    moved = await _move(db, quest_id, device_id, ["offered", "accepted"],
                        {"status": "skipped", "skipped_at": now})  # fmt: skip
    if moved is None:
        doc = await _load(db, quest_id, device_id)
        if doc["status"] == "skipped":
            return _state(doc)
        raise wrong_state(doc["status"])

    quest = moved["quest"]
    draft = QuestDraft.model_validate({k: quest[k] for k in QuestDraft.model_fields})
    place = quest.get("place") or {}
    text = quest_memory_text(draft, place.get("name"))
    try:
        [vector] = await embedder.embed([text])
        await upsert_memory(db, quest_id=quest_id, device_id=device_id, ts=now, text=text,
                            category=draft.category, place_id=draft.place_id, embedding=vector,
                            kind="skipped")  # fmt: skip
    except PyMongoError as exc:  # memory is best-effort; the skip itself succeeded
        log.warning("skip memory failed", extra={"error_type": type(exc).__name__})
    return _state(moved)
