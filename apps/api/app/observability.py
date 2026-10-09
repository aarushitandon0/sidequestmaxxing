"""Sentry setup with PII scrubbing (MASTERSPEC §9.3, §13).

Scrubs coordinate-like keys anywhere in the event, hashes device ids, drops query strings
and request bodies. Spans helper keeps agents free of Sentry boilerplate.

AI spans follow Sentry's current `gen_ai.*` convention (verified 2026-10-09, DECISIONS D-62):
op `gen_ai.chat` named `chat {model}` under op `gen_ai.invoke_agent` named `invoke_agent {name}`,
with `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.agent.name` and
`gen_ai.request.model` set at span start so head-based sampling can see them. Prompt and response
*content* is never attached (`gen_ai.input.messages` / `gen_ai.output.messages`): it carries
interests and place names (§9.3).

Span data is scrubbed by `ScrubbedSpan` as it is authored, not by a `before_send*` hook — see
that class for why neither hook can see a streamed `gen_ai` span.
"""

import hashlib
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import sentry_sdk

from app.config import Settings
from app.deps import DEVICE_HEADER

SCRUBBED = "[scrubbed]"

# --- gen_ai.* convention (DECISIONS D-62) ------------------------------------------------------
OP_CHAT = "gen_ai.chat"
OP_INVOKE_AGENT = "gen_ai.invoke_agent"
# The provider behind every call: our own llama.cpp server (OpenAI-compatible endpoint).
PROVIDER = "llama.cpp"
ATTR_OPERATION = "gen_ai.operation.name"
ATTR_PROVIDER = "gen_ai.provider.name"
ATTR_AGENT = "gen_ai.agent.name"
ATTR_REQUEST_MODEL = "gen_ai.request.model"
ATTR_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
ATTR_RESPONSE_MODEL = "gen_ai.response.model"
ATTR_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

_COORD_KEYS = {"lat", "lng", "lon", "latitude", "longitude", "coordinates", "checkin", "loc"}
_DEVICE_KEYS = {"device_id", DEVICE_HEADER.lower()}
# Note: span/breadcrumb "data" dicts are walked (not blanked) so token counts survive;
# only the request body (`request.data`) is dropped wholesale in scrub_event.
_TEXT_KEYS = {"note", "interests", "seen", "query_string", "cookies", "http.query", "query"}
_COORD_PAIR = re.compile(r"-?\d{1,3}\.\d{2,}\s*,\s*-?\d{1,3}\.\d{2,}")
# Query strings inside any URL-ish string (span descriptions, breadcrumbs): they carry lat/lng.
_URL_QUERY = re.compile(r"(https?://[^\s?#]+)\?[^\s#]*")


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
        return _COORD_PAIR.sub(SCRUBBED, _URL_QUERY.sub(r"\1", value))
    return value


def scrub_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    scrubbed: dict[str, Any] = _scrub(event)
    request = scrubbed.get("request")
    if isinstance(request, dict):
        if isinstance(request.get("url"), str):
            request["url"] = request["url"].split("?", 1)[0]
        if "data" in request:
            request["data"] = SCRUBBED
    return scrubbed


def sentry_options(settings: Settings) -> dict[str, Any]:
    return {
        "dsn": settings.sentry_dsn,
        "environment": settings.env,
        "release": settings.git_sha,
        "traces_sample_rate": settings.sentry_traces_sample_rate,
        "send_default_pii": False,
        "max_request_body_size": "never",
        "before_send": scrub_event,
        "before_send_transaction": scrub_event,
    }


def init_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(**sentry_options(settings))
    return True


class ScrubbedSpan:
    """A span whose `set_data` scrubs before the value ever reaches the SDK.

    `before_send`/`before_send_transaction` cannot be relied on for this. Since SDK 2.64.0
    `gen_ai.*` spans are streamed as their own span-batch envelope item rather than nested in
    the transaction payload, so neither hook sees them, and `before_send_span` is ignored
    unless `trace_lifecycle="stream"` (verified against 2.71.0 — it warns and never fires;
    D-62). Scrubbing where the data is authored holds whichever path the span takes.
    """

    __slots__ = ("_span",)

    def __init__(self, span: Any) -> None:
        self._span = span

    def set_data(self, key: str, value: Any) -> None:
        self._span.set_data(key, _scrub(value, key))

    def set_status(self, status: str) -> None:
        self._span.set_status(status)

    def set_tag(self, key: str, value: Any) -> None:
        self._span.set_tag(key, _scrub(value, key))


@contextmanager
def span(op: str, name: str | None = None, **data: Any) -> Iterator[ScrubbedSpan]:
    """One Sentry span per agent step; a no-op when Sentry isn't initialised."""
    with sentry_sdk.start_span(op=op, name=name or op) as s:
        scrubbed = ScrubbedSpan(s)
        for key, value in data.items():
            scrubbed.set_data(key, value)
        yield scrubbed


@contextmanager
def agent_span(agent: str) -> Iterator[ScrubbedSpan]:
    """Parent span for one agent run, so Sentry's AI Agents view groups the chat spans."""
    with span(
        OP_INVOKE_AGENT,
        f"invoke_agent {agent}",
        **{ATTR_OPERATION: "invoke_agent", ATTR_PROVIDER: PROVIDER, ATTR_AGENT: agent},
    ) as s:
        yield s


@contextmanager
def chat_span(model: str, *, agent: str, max_tokens: int, attempt: int) -> Iterator[ScrubbedSpan]:
    """One model call.

    Everything known before the call is set as the span opens, so a sampler sees it; the SDK
    we pin (2.71.0) has no `start_span(attributes=...)` — that arrived in the 3.x line — and
    `set_data` is what becomes a span attribute on the wire either way (D-62).
    """
    with span(
        OP_CHAT,
        f"chat {model}",
        **{
            ATTR_OPERATION: "chat",
            ATTR_PROVIDER: PROVIDER,
            ATTR_AGENT: agent,
            ATTR_REQUEST_MODEL: model,
            ATTR_REQUEST_MAX_TOKENS: max_tokens,
            "attempt": attempt,
        },
    ) as s:
        yield s


def name_transaction(name: str) -> None:
    """One named transaction per traced endpoint (MASTERSPEC §13)."""
    sentry_sdk.get_current_scope().set_transaction_name(name)


def tag_outcome(source: str, retries: int, validator_failures: Sequence[str] = ()) -> None:
    """The three tags every /generate and /recap transaction carries (MASTERSPEC §13)."""
    sentry_sdk.set_tag("source", source)
    sentry_sdk.set_tag("retry", str(retries))
    sentry_sdk.set_tag("validator_failures", ",".join(validator_failures) or "none")


def mark_span_error(s: ScrubbedSpan | None, error_type: str) -> None:
    """Sentry wants an error status plus a low-cardinality `error.type` on a failed AI span."""
    if s is None:
        return
    s.set_status("internal_error")
    s.set_data("error.type", error_type)
