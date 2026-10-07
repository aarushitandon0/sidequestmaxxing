"""OpenAI-compatible chat client for the llama.cpp server (or Ollama via LLM_BASE_URL).

Request shape checked against llama.cpp master (tools/server/server-common.cpp, 2026-10-07):
`response_format = {"type": "json_schema", "json_schema": {"schema": ...}}` is what the server
actually reads for type "json_schema" (see DECISIONS D-27). `chat_template_kwargs.enable_thinking
= false` turns off reasoning for hybrid-thinking templates and is ignored by others.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

LLMErrorKind = Literal["timeout", "connection", "http", "bad_response"]

TEMPERATURE = 0.8
TOP_P = 0.95
MAX_TOKENS = 380
CONNECT_TIMEOUT_S = 2.0  # an unreachable host must fail fast so the fallback stays < 3 s


class LLMError(Exception):
    def __init__(self, kind: LLMErrorKind, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    tokens_per_s: float | None  # llama.cpp `timings.predicted_per_second` when present


def build_payload(
    messages: list[dict[str, str]],
    schema: dict[str, Any] | None,
    model: str,
    *,
    max_tokens: int = MAX_TOKENS,
    schema_name: str = "quest",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "max_tokens": max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema},
        }
    return payload


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def parse_response(body: object, latency_ms: int) -> LLMResponse:
    if not isinstance(body, dict):
        raise LLMError("bad_response", "body is not an object")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("bad_response", "no choices[0].message.content") from exc
    if not isinstance(content, str):
        raise LLMError("bad_response", "content is not a string")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    timings = body.get("timings") if isinstance(body.get("timings"), dict) else {}
    assert isinstance(usage, dict) and isinstance(timings, dict)
    completion = _int_or_none(usage.get("completion_tokens"))
    tps = timings.get("predicted_per_second")
    if not isinstance(tps, int | float):
        tps = completion / (latency_ms / 1000) if completion and latency_ms > 0 else None
    return LLMResponse(
        content=content,
        model=str(body.get("model") or "unknown"),
        prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
        completion_tokens=completion,
        latency_ms=latency_ms,
        tokens_per_s=float(tps) if tps is not None else None,
    )


class LLMClient:
    def __init__(
        self,
        base_url: str,
        *,
        model: str = "quest",
        timeout_s: float = 25.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.timeout = httpx.Timeout(timeout_s, connect=min(CONNECT_TIMEOUT_S, timeout_s))
        self._transport = transport

    async def chat(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any] | None = None,
        *,
        max_tokens: int = MAX_TOKENS,
        schema_name: str = "quest",
    ) -> LLMResponse:
        payload = build_payload(
            messages, schema, self.model, max_tokens=max_tokens, schema_name=schema_name
        )
        start = time.perf_counter()
        try:
            # httpx timeouts are per network operation; asyncio.timeout bounds the whole call.
            async with asyncio.timeout(self.timeout_s):
                async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as c:
                    res = await c.post(f"{self.base_url}/v1/chat/completions", json=payload)
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise LLMError("timeout", type(exc).__name__) from exc
        except httpx.TransportError as exc:
            raise LLMError("connection", type(exc).__name__) from exc
        latency_ms = round((time.perf_counter() - start) * 1000)
        if res.status_code != 200:
            raise LLMError("http", str(res.status_code))
        try:
            body = res.json()
        except ValueError as exc:
            raise LLMError("bad_response", "non-JSON body") from exc
        return parse_response(body, latency_ms)
