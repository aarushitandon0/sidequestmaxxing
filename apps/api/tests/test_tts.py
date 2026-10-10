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
from app.models.enums import PERSONAS
from app.services.tts import (
    PERSONA_STYLE,
    ElevenLabsClient,
    build_tts_client,
    reserve_chars,
    tts_text,
    usage_id,
)
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


PERSONA_VOICES = {
    "chill": "voice-chill",
    "dramatic": "voice-dramatic",
    "nature_nerd": "voice-nature",
    "sarcastic": "voice-sarcastic",
}


def eleven(handler: Any, *, persona_voices: dict[str, str] | None = None) -> ElevenLabsClient:
    http = httpx.AsyncClient(
        base_url="https://api.elevenlabs.test", transport=httpx.MockTransport(handler)
    )
    return ElevenLabsClient(
        "test-key-not-real",
        "voice123",
        http=http,
        persona_voice_ids=persona_voices,  # type: ignore[arg-type]
    )


class Harness:
    def __init__(
        self,
        handler: Any = None,
        *,
        budget: int = 20000,
        configured: bool = True,
        persona: str | None = None,
        device_persona: str | None = None,
        persona_voices: dict[str, str] | None = None,
    ) -> None:
        self.device = str(uuid.uuid4())
        self.calls: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            return (handler or ok)(request)

        quest_doc: dict[str, Any] = {
            "_id": QUEST_ID,
            "device_id": self.device,
            "status": "accepted",
            "quest": QUEST,
        }
        if persona is not None:
            quest_doc["persona"] = persona
        users = MemCollection()
        if device_persona is not None:
            users.docs.append({"_id": self.device, "persona": device_persona})
        self.db = FakeDB(
            quests=MemCollection([quest_doc]),
            usage=MemCollection(),
            users=users,
        )
        app = create_app(Settings(env="test", tts_daily_char_budget=budget))
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_tts_client] = (
            (lambda: eleven(record, persona_voices=persona_voices))
            if configured
            else (lambda: None)
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
    assert json.loads(call.content) == {
        "text": BRIEFING,
        "model_id": "eleven_flash_v2_5",
        "voice_settings": PERSONA_STYLE["chill"].as_settings(),
    }
    assert h.used == len(BRIEFING)


# ---------------------------------------------------------------- one voice per Dungeon Master


@pytest.mark.parametrize("persona", list(PERSONAS))
def test_each_persona_gets_its_own_voice_and_delivery(persona: str) -> None:
    h = Harness(persona=persona, persona_voices=PERSONA_VOICES)
    assert h.post().status_code == 200
    [call] = h.calls
    assert call.url.path == f"/v1/text-to-speech/{PERSONA_VOICES[persona]}/stream"
    assert json.loads(call.content)["voice_settings"] == PERSONA_STYLE[persona].as_settings()


def test_personas_do_not_all_sound_the_same() -> None:
    """The four Dungeon Masters must differ even on a single shared voice id."""
    settings = [tuple(sorted(PERSONA_STYLE[p].as_settings().items())) for p in PERSONAS]
    assert len(set(settings)) == len(PERSONAS)
    assert set(PERSONA_STYLE) == set(PERSONAS)


def test_persona_falls_back_to_the_devices_current_dungeon_master() -> None:
    """Quests stored before personas were saved: use the device's persona."""
    h = Harness(device_persona="dramatic", persona_voices=PERSONA_VOICES)
    assert h.post().status_code == 200
    assert h.calls[0].url.path == "/v1/text-to-speech/voice-dramatic/stream"


def test_unconfigured_persona_voice_uses_the_shared_voice_id() -> None:
    h = Harness(persona="sarcastic", persona_voices={"chill": "voice-chill"})
    assert h.post().status_code == 200
    assert h.calls[0].url.path == "/v1/text-to-speech/voice123/stream"
    assert (
        json.loads(h.calls[0].content)["voice_settings"] == PERSONA_STYLE["sarcastic"].as_settings()
    )


def test_build_tts_client_needs_a_key_and_at_least_one_voice() -> None:
    assert build_tts_client(None, "v1", "m", "f", 1.0) is None
    assert build_tts_client("k", None, "m", "f", 1.0) is None
    only_persona = build_tts_client("k", None, "m", "f", 1.0, {"dramatic": "voice-dramatic"})
    assert only_persona is not None
    assert only_persona.voice_for("dramatic") == "voice-dramatic"
    assert only_persona.voice_for("chill") == "voice-dramatic"


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
