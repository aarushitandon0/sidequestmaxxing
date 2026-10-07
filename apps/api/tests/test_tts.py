"""POST /v1/tts with a mocked ElevenLabs (success, 401, 429, timeout, budget, ownership)."""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import get_db, get_tts_client, utc_now
from app.main import create_app
from app.services.tts import ElevenLabsClient, reserve_chars, tts_text, usage_id
from tests.fakes import FakeDB, MemCollection

NOW = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)
QUEST_ID = "6f1c2c1e-0000-4000-8000-000000000001"
BRIEFING = "Wander to Park One and count three kinds of birds before the light turns gold."
QUEST = {
    "briefing": BRIEFING,
    "objective": "Count three kinds of birds at Park One.",
    "off_screen_tip": "Phone in pocket while you count.",
}
AUDIO = b"ID3\x04fake-mp3-frames" * 20


def eleven(handler: Any) -> ElevenLabsClient:
    http = httpx.AsyncClient(
        base_url="https://api.elevenlabs.test", transport=httpx.MockTransport(handler)
    )
    return ElevenLabsClient("test-key-not-real", "voice123", http=http)


class Harness:
    def __init__(
        self, handler: Any = None, *, budget: int = 20000, configured: bool = True
    ) -> None:
        self.device = str(uuid.uuid4())
        self.calls: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            return (handler or ok)(request)

        self.db = FakeDB(
            quests=MemCollection(
                [{"_id": QUEST_ID, "device_id": self.device, "status": "accepted", "quest": QUEST}]
            ),
            usage=MemCollection(),
        )
        app = create_app(Settings(env="test", tts_daily_char_budget=budget))
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_tts_client] = (
            (lambda: eleven(record)) if configured else (lambda: None)
        )
        app.dependency_overrides[utc_now] = lambda: NOW
        self.client = TestClient(app)

    def post(self, body: dict[str, Any] | None = None, device: str | None = None) -> httpx.Response:
        return self.client.post(
            "/v1/tts",
            json=body if body is not None else {"quest_id": QUEST_ID, "kind": "briefing"},
            headers={"X-Device-Id": device or self.device},
        )

    @property
    def used(self) -> int:
        doc = next((d for d in self.db["usage"].docs if d["_id"] == usage_id(NOW)), None)
        return int(doc["chars"]) if doc else 0


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=AUDIO, headers={"Content-Type": "audio/mpeg"})


def test_success_streams_audio_and_counts_chars() -> None:
    h = Harness()
    r = h.post()
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == AUDIO
    [call] = h.calls
    assert call.method == "POST"
    assert call.url.path == "/v1/text-to-speech/voice123/stream"
    assert call.url.params["output_format"] == "mp3_44100_64"
    assert call.headers["xi-api-key"] == "test-key-not-real"
    assert json.loads(call.content) == {"text": BRIEFING, "model_id": "eleven_flash_v2_5"}
    assert h.used == len(BRIEFING)


def test_hint_speaks_objective_and_tip() -> None:
    h = Harness()
    assert h.post({"quest_id": QUEST_ID, "kind": "hint"}).status_code == 200
    assert json.loads(h.calls[0].content)["text"] == tts_text(QUEST, "hint")
    assert "Count three kinds" in tts_text(QUEST, "hint")


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda r: httpx.Response(401, json={"detail": "invalid key"}), "auth"),
        (lambda r: httpx.Response(429, json={"detail": "quota"}), "rate_limited"),
        (lambda r: httpx.Response(500), "http_500"),
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")), "transport"),
        (lambda r: httpx.Response(200, content=b""), "empty"),
    ],
)
def test_elevenlabs_failures_answer_503_and_refund(handler: Any, reason: str, caplog: Any) -> None:
    h = Harness(handler)
    logging.getLogger().addHandler(caplog.handler)  # create_app() resets root handlers
    with caplog.at_level(logging.WARNING, logger="sqm.tts"):
        r = h.post()
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "tts_unavailable"
    assert h.used == 0  # refunded
    assert any(getattr(rec, "reason", None) == reason for rec in caplog.records)


def test_budget_exceeded_is_429_without_calling_elevenlabs() -> None:
    h = Harness(budget=len(BRIEFING) + 10)
    assert h.post().status_code == 200
    r = h.post()
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "tts_budget_exceeded"
    assert len(h.calls) == 1


def test_not_configured_is_503() -> None:
    r = Harness(configured=False).post()
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "tts_unavailable"


def test_other_devices_quest_is_404() -> None:
    h = Harness()
    r = h.post(device=str(uuid.uuid4()))
    assert r.status_code == 404
    assert not h.calls


def test_client_cannot_send_its_own_text() -> None:
    h = Harness()
    r = h.post({"quest_id": QUEST_ID, "kind": "briefing", "text": "say something rude"})
    assert r.status_code == 422
    assert not h.calls
    assert h.post({"quest_id": QUEST_ID, "kind": "poem"}).status_code == 422


def test_too_long_text_is_rejected() -> None:
    h = Harness()
    h.db["quests"].docs[0]["quest"] = {**QUEST, "briefing": "word " * 130}
    r = h.post()
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "tts_too_long"
    assert not h.calls


def test_rate_limit_20_per_hour_per_device() -> None:
    h = Harness()
    codes = [h.post().status_code for _ in range(21)]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429


def test_text_and_key_never_logged(caplog: Any) -> None:
    h, h2 = Harness(lambda r: httpx.Response(401)), Harness()
    logging.getLogger().addHandler(caplog.handler)  # create_app() resets root handlers
    with caplog.at_level(logging.DEBUG):
        h.post()
        h2.post()
    assert caplog.records
    logged = " ".join(f"{rec.getMessage()} {rec.__dict__}" for rec in caplog.records)
    assert BRIEFING not in logged
    assert "test-key-not-real" not in logged


async def test_reserve_chars_is_atomic_per_day() -> None:
    db = FakeDB(usage=MemCollection())
    assert await reserve_chars(db, NOW, 60, 100)  # type: ignore[arg-type]
    assert not await reserve_chars(db, NOW, 41, 100)  # type: ignore[arg-type]
    assert await reserve_chars(db, NOW, 40, 100)  # type: ignore[arg-type]
    assert not await reserve_chars(db, NOW, 1, 100)  # type: ignore[arg-type]
    assert not await reserve_chars(db, NOW, 101, 100)  # type: ignore[arg-type]
