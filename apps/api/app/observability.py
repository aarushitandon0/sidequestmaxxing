"""Sentry setup with PII scrubbing (MASTERSPEC §9.3, §13).

Scrubs coordinate-like keys anywhere in the event, hashes device ids, drops query strings
and request bodies. Spans helper keeps agents free of Sentry boilerplate.
"""

import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sentry_sdk

from app.config import Settings
from app.deps import DEVICE_HEADER

SCRUBBED = "[scrubbed]"
_COORD_KEYS = {"lat", "lng", "lon", "latitude", "longitude", "coordinates", "checkin", "loc"}
_DEVICE_KEYS = {"device_id", DEVICE_HEADER.lower()}
_TEXT_KEYS = {"note", "interests", "seen", "query_string", "data", "cookies"}
_COORD_PAIR = re.compile(r"-?\d{1,3}\.\d{2,}\s*,\s*-?\d{1,3}\.\d{2,}")


def hash_device_id(device_id: str) -> str:
    return "dev_" + hashlib.sha256(device_id.encode()).hexdigest()[:16]


def _scrub(value: Any, key: str | None = None) -> Any:
    k = key.lower() if isinstance(key, str) else None
    if k in _COORD_KEYS or k in _TEXT_KEYS:
        return SCRUBBED
    if k in _DEVICE_KEYS and isinstance(value, str):
        return hash_device_id(value)
    if isinstance(value, dict):
        return {kk: _scrub(vv, kk) for kk, vv in value.items()}
    if isinstance(value, list):
        # Header lists in Sentry events are [[name, value], ...].
        if all(isinstance(i, list | tuple) and len(i) == 2 for i in value) and value:
            return [[n, _scrub(v, n if isinstance(n, str) else None)] for n, v in value]
        return [_scrub(i) for i in value]
    if isinstance(value, str):
        return _COORD_PAIR.sub(SCRUBBED, value)
    return value


def scrub_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    scrubbed: dict[str, Any] = _scrub(event)
    request = scrubbed.get("request")
    if isinstance(request, dict) and isinstance(request.get("url"), str):
        request["url"] = request["url"].split("?", 1)[0]
    return scrubbed


def init_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=settings.git_sha,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=scrub_event,  # type: ignore[arg-type]
        before_send_transaction=scrub_event,  # type: ignore[arg-type]
    )
    return True


@contextmanager
def span(op: str, name: str | None = None, **data: Any) -> Iterator[Any]:
    """One Sentry span per agent step; a no-op when Sentry isn't initialised."""
    with sentry_sdk.start_span(op=op, name=name or op) as s:
        for key, value in data.items():
            s.set_data(key, value)
        yield s
