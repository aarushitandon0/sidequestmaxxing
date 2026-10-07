"""Request dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.errors import ApiError, db_unavailable
from app.services.db import Doc, get_database
from app.services.embeddings import Embedder, get_embedder

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
