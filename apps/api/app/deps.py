"""Request dependencies."""

import uuid
from typing import Annotated

from fastapi import Depends, Header

from app.errors import ApiError

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
