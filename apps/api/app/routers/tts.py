"""POST /v1/tts — spoken briefings via ElevenLabs (MASTERSPEC §6.1, §6.5).

Any non-200 answer tells the client to use the browser's speechSynthesis with the same text
(fallback matrix §2.4); the text itself is always on screen.
"""

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.deps import DeviceId, Now, get_db, get_tts_client
from app.errors import ApiError, db_unavailable
from app.models.enums import PERSONAS, Persona
from app.observability import span
from app.ratelimit import TTS_LIMIT, limiter
from app.services.db import Doc
from app.services.quests_repo import get_quest
from app.services.recaps import device_persona, get_recap
from app.services.tts import (
    MAX_RECAP_TTS_CHARS,
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
    """`quest_id` for briefing/hint, `recap_id` for recap. Never any text."""

    model_config = ConfigDict(extra="forbid")

    quest_id: str | None = Field(default=None, min_length=1, max_length=64)
    recap_id: str | None = Field(default=None, min_length=1, max_length=64)
    kind: TtsKind = "briefing"

    @model_validator(mode="after")
    def _one_target(self) -> "TtsRequest":
        if self.kind == "recap":
            if self.recap_id is None or self.quest_id is not None:
                raise ValueError("kind 'recap' takes recap_id only")
        elif self.quest_id is None or self.recap_id is not None:
            raise ValueError("kind 'briefing'/'hint' takes quest_id only")
        return self


async def _text_for(
    db: AsyncDatabase[Doc], body: TtsRequest, device_id: str
) -> tuple[str, Persona]:
    """The words to speak and who speaks them, both read server-side from this device's data."""
    if body.kind == "recap":
        assert body.recap_id is not None
        recap = await get_recap(db, device_id, body.recap_id)
        if recap is None:
            raise ApiError(404, "recap_not_found", "That chronicle isn't in your quest log.")
        recap_persona, _ = await device_persona(db, device_id)
        return str(recap["text"]), recap_persona
    assert body.quest_id is not None
    doc = await get_quest(db, body.quest_id, device_id)
    if doc is None:
        raise ApiError(404, "quest_not_found", "That quest isn't in your quest log.")
    # Quests written before personas were stored (and any stray value) fall back to the
    # device's current Dungeon Master.
    stored = doc.get("persona")
    persona: Persona = stored if stored in PERSONAS else (await device_persona(db, device_id))[0]
    return tts_text(doc["quest"], body.kind), persona


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
        text, persona = await _text_for(db, body, device_id)
    except PyMongoError as exc:
        raise db_unavailable() from exc

    limit = MAX_RECAP_TTS_CHARS if body.kind == "recap" else MAX_TTS_CHARS
    if len(text) > limit:
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
    with span(
        "tts.elevenlabs", name=op_name, chars=len(text), kind=body.kind, persona=persona
    ) as s:
        try:
            stream = await client.stream(text, persona)
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
