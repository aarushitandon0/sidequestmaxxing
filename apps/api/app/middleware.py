"""ASGI middleware: request body size limit + PII-free access log."""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 32 * 1024
log = logging.getLogger("sqm.access")


async def _send_413(send: Send) -> None:
    body = b'{"error":{"code":"payload_too_large","message":"Request body too large."}}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    """Rejects bodies over `max_bytes`, by Content-Length or by counting streamed chunks."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    too_big = int(value) > self.max_bytes
                except ValueError:
                    too_big = True
                if too_big:
                    await _send_413(send)
                    return

        received = 0
        exceeded = False

        async def limited_receive() -> Message:
            # Frameworks may swallow exceptions raised while reading the body, so we flag the
            # overflow, hand the app an empty final chunk and replace whatever it responds.
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message: Message) -> None:
            if not exceeded:
                await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        finally:
            if exceeded:
                await _send_413(send)


class AccessLogMiddleware:
    """Logs method, route path, status and latency. Never query strings (they carry lat/lng)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", None) or "<unmatched>"
            log.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
