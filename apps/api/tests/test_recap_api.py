"""POST /v1/recap/weekly and TTS kind "recap" (MASTERSPEC §3.3, §7.7) with mocked LLM/Mongo."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.agents.chronicler import RECAP_MAX_TOKENS
from app.config import Settings
from app.deps import get_db, get_llm_client, get_tts_client, utc_now
from app.main import create_app
from app.services.llm_client import LLMClient
from app.services.recaps import week_label, window
from app.services.tts import ElevenLabsClient
from app.validators.recap import RecapCompletion, validate_recap
from tests.fakes import FakeDB, MemCollection
from tests.test_quests_api import llm_handler

NOW = datetime(2026, 10, 7, 9, 30, tzinfo=UTC)  # a Wednesday
TODAY = NOW.date()


def completion(n: int, days_ago: int, category: str, place: str | None, minutes: int) -> Any:
    return {
        "_id": f"c{n}",
        "quest_id": f"q{n}",
        "completed_at": NOW - timedelta(days=days_ago),
        "local_date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "category": category,
        "title": f"Quest {n}",
        "place_name": place,
        "elapsed_seconds": minutes * 60,
        "xp_awarded": 30,
    }


def llm_text(n: int = 200, base: str = "You walked to Kamala Garden and looked closely.") -> str:
    out = base.split()
    while len(out) < n:
        out.append("outside")
    return " ".join(out[:n])


GOOD_STATS = {"quests": 2, "minutes": 60, "top_category": "naturalist"}


def llm_recap(text: str | None = None, **stats: Any) -> str:
    return json.dumps({"text": text or llm_text(), "stats": {**GOOD_STATS, **stats}})


class Harness:
    def __init__(self, llm: LLMClient | None = None, docs: list[Any] | None = None) -> None:
        self.device = str(uuid.uuid4())
        rows = docs if docs is not None else [
            completion(1, 1, "naturalist", "Kamala Garden", 35),
            completion(2, 3, "naturalist", None, 25),
            completion(3, 9, "foodie", "Old Market", 40),  # outside the 7-day window
        ]  # fmt: skip
        self.db = FakeDB(
            users=MemCollection([{"_id": self.device, "persona": "dramatic", "utc_offset_min": 0}]),
            completions=MemCollection([{**d, "device_id": self.device} for d in rows]),
            recaps=MemCollection(),
            usage=MemCollection(),
        )
        self.tts_calls: list[httpx.Request] = []
        app = create_app(Settings(env="test"))
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_llm_client] = lambda: llm
        app.dependency_overrides[get_tts_client] = lambda: ElevenLabsClient(
            "test-key-not-real", "voice123", http=httpx.AsyncClient(
                base_url="https://api.elevenlabs.test", transport=httpx.MockTransport(self._tts)
            ),
        )  # fmt: skip
        app.dependency_overrides[utc_now] = lambda: NOW
        self.client = TestClient(app)

    def _tts(self, request: httpx.Request) -> httpx.Response:
        self.tts_calls.append(request)
        return httpx.Response(200, content=b"ID3fake" * 10, headers={"Content-Type": "audio/mpeg"})

    def recap(self, device: str | None = None) -> httpx.Response:
        return self.client.post("/v1/recap/weekly", headers={"X-Device-Id": device or self.device})

    def tts(self, body: dict[str, Any], device: str | None = None) -> httpx.Response:
        return self.client.post(
            "/v1/tts", json=body, headers={"X-Device-Id": device or self.device}
        )


def mock_llm(*contents: str) -> tuple[LLMClient, Any]:
    handler = llm_handler(*contents)
    return LLMClient("http://llm.test", transport=httpx.MockTransport(handler)), handler


def week_inputs() -> list[RecapCompletion]:
    return [
        RecapCompletion("Quest 2", "naturalist", None, 25, ""),
        RecapCompletion("Quest 1", "naturalist", "Kamala Garden", 35, ""),
    ]


def test_window_and_label() -> None:
    start, end = window(TODAY)
    assert (end - start).days == 6
    assert week_label(start, end) == "Oct 1 - Oct 7"


def test_llm_recap_is_validated_stored_and_uses_the_week_only() -> None:
    llm, handler = mock_llm(llm_recap())
    h = Harness(llm)
    res = h.recap()
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "llm" and body["stats"] == GOOD_STATS
    assert (body["week_start"], body["week_end"]) == ("2026-10-01", "2026-10-07")
    [doc] = h.db["recaps"].docs
    assert doc["_id"] == body["id"] and doc["completion_ids"] == ["q1", "q2"]
    sent = handler.calls[0]
    assert sent["max_tokens"] == RECAP_MAX_TOKENS
    assert sent["response_format"]["json_schema"]["name"] == "recap"
    user = json.loads(sent["messages"][1]["content"])
    assert user["persona"] == "dramatic" and user["week"] == "Oct 1 - Oct 7"
    assert [c["title"] for c in user["completions"]] == ["Quest 2", "Quest 1"]  # oldest first
    assert "Old Market" not in sent["messages"][1]["content"]  # 9 days ago: not this week


def test_hallucinated_place_is_rejected_then_retried() -> None:
    fake = llm_text(base="You walked to Kamala Garden and then to Riverside Botanical Garden.")
    llm, handler = mock_llm(llm_recap(fake), llm_recap())
    body = Harness(llm).recap().json()
    assert body["source"] == "llm"
    assert "Riverside Botanical Garden" in handler.calls[1]["messages"][-1]["content"]
    assert "R6" in handler.calls[1]["messages"][-1]["content"]


def test_two_hallucinations_fall_back_to_the_template() -> None:
    fake = llm_text(base="You walked to Kamala Garden and then to Riverside Botanical Garden.")
    llm, _ = mock_llm(llm_recap(fake), llm_recap(fake))
    h = Harness(llm)
    body = h.recap().json()
    assert body["source"] == "fallback"
    assert "Riverside" not in body["text"]
    assert validate_recap({"text": body["text"], "stats": body["stats"]}, week_inputs()).ok
    [doc] = h.db["recaps"].docs
    assert doc["fallback_reason"] == "validation_failed_twice" and "R6" in doc["validator_failures"]


def test_wrong_stats_from_llm_never_reach_the_user() -> None:
    llm, _ = mock_llm(llm_recap(quests=9), llm_recap(minutes=999))
    body = Harness(llm).recap().json()
    assert body["source"] == "fallback" and body["stats"] == GOOD_STATS


def test_llm_down_uses_fallback_recap() -> None:
    llm = LLMClient("http://llm.test", transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    h = Harness(llm)
    body = h.recap().json()
    assert body["source"] == "fallback" and body["stats"] == GOOD_STATS
    assert "Kamala Garden" in body["text"]
    assert h.db["recaps"].docs[0]["fallback_reason"] == "llm_http"


def test_no_llm_configured_uses_fallback_recap() -> None:
    body = Harness(None).recap().json()
    assert body["source"] == "fallback" and 180 <= len(body["text"].split()) <= 260


def test_same_week_same_completions_is_idempotent() -> None:
    llm, handler = mock_llm(llm_recap())
    h = Harness(llm)
    first, second = h.recap().json(), h.recap().json()
    assert first == second and len(handler.calls) == 1 and len(h.db["recaps"].docs) == 1


def test_new_completion_rewrites_this_weeks_recap() -> None:
    h = Harness(None)
    first = h.recap().json()
    h.db["completions"].docs.append(
        {**completion(4, 0, "mindful", "Lotus Park", 10), "device_id": h.device}
    )
    second = h.recap().json()
    assert second["id"] != first["id"] and second["stats"]["quests"] == 3
    assert [d["_id"] for d in h.db["recaps"].docs] == [second["id"]]


def test_empty_week_returns_placeholder_and_stores_nothing() -> None:
    h = Harness(None, docs=[completion(3, 9, "foodie", "Old Market", 40)])
    body = h.recap().json()
    assert body["source"] == "empty" and body["id"] is None
    assert body["stats"] == {"quests": 0, "minutes": 0, "top_category": None}
    assert h.db["recaps"].docs == []


def test_recap_is_per_device() -> None:
    h = Harness(None)
    other = h.recap(device=str(uuid.uuid4())).json()
    assert other["source"] == "empty"


def test_recap_db_down_is_503() -> None:
    h = Harness(None)
    h.db.collections["completions"] = MemCollection(fail=PyMongoError("down"))
    assert h.recap().status_code == 503


def test_tts_recap_reads_stored_text_server_side() -> None:
    h = Harness(None)
    recap = h.recap().json()
    res = h.tts({"recap_id": recap["id"], "kind": "recap"})
    assert res.status_code == 200 and res.headers["content-type"] == "audio/mpeg"
    assert json.loads(h.tts_calls[0].content)["text"] == recap["text"]


def test_tts_recap_of_another_device_is_404() -> None:
    h = Harness(None)
    recap = h.recap().json()
    res = h.tts({"recap_id": recap["id"], "kind": "recap"}, device=str(uuid.uuid4()))
    assert res.status_code == 404 and res.json()["error"]["code"] == "recap_not_found"
    assert h.tts_calls == []


def test_tts_target_must_match_kind() -> None:
    h = Harness(None)
    for body in (
        {"kind": "recap"},
        {"kind": "recap", "quest_id": "q1"},
        {"kind": "briefing", "recap_id": "r1"},
        {"kind": "recap", "recap_id": "r1", "text": "say this"},
    ):
        assert h.tts(body).status_code == 422, body
