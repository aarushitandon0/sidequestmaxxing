"""POST /v1/tts — spoken briefings via ElevenLabs (MASTERSPEC §6.1, §6.5).

Any non-200 answer tells the client to use the browser's speechSynthesis with the same text
(fallback matrix §2.4); the text itself is always on screen.
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.deps import DeviceId, Now, get_db, get_tts_client
from app.errors import ApiError, db_unavailable
from app.observability import span
from app.ratelimit import TTS_LIMIT, limiter
from app.services.db import Doc
from app.services.quests_repo import get_quest
from app.services.tts import (
    MAX_TTS_CHARS,
    AudioStream,
    ElevenLabsClient,
    TtsKind,
    TtsUnavailableError,
    refund_chars,
    reserve_chars,
    tts_text,
)

log = logging.getLogger("sqm.tts")
router = APIRouter(prefix="/v1", tags=["tts"])

Db = Annotated[AsyncDatabase[Doc], Depends(get_db)]


class TtsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quest_id: str = Field(min_length=1, max_length=64)
    kind: TtsKind = "briefing"


def unavailable() -> ApiError:
    message = "The Dungeon Master's voice is resting. Reading it aloud locally."
    return ApiError(503, "tts_unavailable", message)


async def _audio(stream: AudioStream) -> AsyncIterator[bytes]:
    try:
        yield stream.first
        async for chunk in stream.rest:
            yield chunk
    finally:
        await stream.close()


@router.post(
    "/tts",
    response_class=StreamingResponse,
    responses={200: {"content": {"audio/mpeg": {}}, "description": "Spoken audio (MP3)"}},
)
@limiter.limit(TTS_LIMIT)
async def tts(
    request: Request,
    body: TtsRequest,
    device_id: DeviceId,
    db: Db,
    client: Annotated[ElevenLabsClient | None, Depends(get_tts_client)],
    now: Now,
) -> StreamingResponse:
    try:
        doc = await get_quest(db, body.quest_id, device_id)
    except PyMongoError as exc:
        raise db_unavailable() from exc
    if doc is None:
        raise ApiError(404, "quest_not_found", "That quest isn't in your quest log.")

    text = tts_text(doc["quest"], body.kind)
    if len(text) > MAX_TTS_CHARS:
        raise ApiError(422, "tts_too_long", "That's a lot of words. Reading it aloud locally.")
    if client is None:
        raise unavailable()

    budget = request.app.state.settings.tts_daily_char_budget
    try:
        if not await reserve_chars(db, now, len(text), budget):
            message = "Today's voice budget is spent. Reading it aloud locally."
            raise ApiError(429, "tts_budget_exceeded", message)
    except PyMongoError as exc:
        raise db_unavailable() from exc

    op_name = f"tts {client.model_id}"
    with span("tts.elevenlabs", name=op_name, chars=len(text), kind=body.kind) as s:
        try:
            stream = await client.stream(text)
        except TtsUnavailableError as exc:
            s.set_data("error", exc.reason)
            log.warning("tts unavailable", extra={"reason": exc.reason})
            try:
                await refund_chars(db, now, len(text))
            except PyMongoError:
                log.warning("tts refund failed")
            raise unavailable() from exc

    return StreamingResponse(
        _audio(stream),
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )
