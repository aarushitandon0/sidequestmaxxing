"""slowapi rate limits (MASTERSPEC §6.5). Keyed per device, falling back to client IP."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.deps import DEVICE_HEADER, parse_device_id

GENERATE_LIMIT = "6/minute;30/day"
COMPLETE_LIMIT = "10/minute"
TTS_LIMIT = "20/hour"


def device_or_ip(request: Request) -> str:
    device_id = parse_device_id(request.headers.get(DEVICE_HEADER))
    return f"dev:{device_id}" if device_id else f"ip:{get_remote_address(request)}"


def build_limiter(enabled: bool = True) -> Limiter:
    # In-memory storage: fine for a single sqm-api instance. Revisit if we scale out.
    return Limiter(key_func=device_or_ip, enabled=enabled, headers_enabled=False)


limiter = build_limiter()
