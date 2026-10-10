"""Request dependencies."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.errors import ApiError, db_unavailable
from app.services.db import Doc, get_database
from app.services.embeddings import Embedder, get_embedder
from app.services.llm_client import LLMClient
from app.services.tts import ElevenLabsClient, build_tts_client
from app.services.weather import WeatherClient, get_weather_client

DEVICE_HEADER = "X-Device-Id"


def parse_device_id(raw: str | None) -> str | None:
    """Return the canonical uuid4 string, or None if missing/invalid."""
    if not raw:
        return None
    try:
        value = uuid.UUID(raw.strip())
    except ValueError:
        return None
    if value.version != 4:
        return None
    return str(value)


async def get_device_id(
    x_device_id: Annotated[str | None, Header(alias=DEVICE_HEADER)] = None,
) -> str:
    device_id = parse_device_id(x_device_id)
    if device_id is None:
        raise ApiError(400, "invalid_device_id", f"{DEVICE_HEADER} must be a random UUID v4.")
    return device_id


DeviceId = Annotated[str, Depends(get_device_id)]


async def get_db(request: Request) -> AsyncDatabase[Doc]:
    """Database handle; 503 with a friendly message when Atlas isn't configured."""
    db = get_database(request.app.state.settings)
    if db is None:
        raise db_unavailable()
    return db


async def get_embedder_dep(request: Request) -> Embedder:
    return get_embedder(request.app.state.settings.embedding_model)


async def get_weather_client_dep() -> WeatherClient:
    return get_weather_client()


async def get_llm_client(request: Request) -> LLMClient | None:
    """One client per app; None when no LLM URL is configured (→ fallback engine)."""
    state = request.app.state
    if not hasattr(state, "llm_client"):
        settings = state.settings
        state.llm_client = (
            LLMClient(settings.llm_url, model=settings.llm_model, timeout_s=settings.llm_timeout_s)
            if settings.llm_url
            else None
        )
    client: LLMClient | None = state.llm_client
    return client


async def get_tts_client(request: Request) -> ElevenLabsClient | None:
    """One ElevenLabs client per app; None when the key/voice aren't configured."""
    state = request.app.state
    if not hasattr(state, "tts_client"):
        s = state.settings
        state.tts_client = build_tts_client(
            s.elevenlabs_api_key, s.elevenlabs_voice_id, s.elevenlabs_model_id,
            s.elevenlabs_output_format, s.tts_timeout_s, s.persona_voice_ids,
        )  # fmt: skip
    client: ElevenLabsClient | None = state.tts_client
    return client


def utc_now() -> datetime:
    """Server clock as a dependency so tests can pin it (daylight rules, expiry)."""
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(utc_now)]
