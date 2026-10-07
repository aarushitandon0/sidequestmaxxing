"""Device id, error format, rate limits, body limit, CORS, request models."""

import uuid
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.deps import DeviceId, parse_device_id
from app.main import create_app
from app.models import CompletionRequest, Quest, QuestDraft, QuestRequest
from app.ratelimit import limiter

# Routes are defined once at import time: slowapi registers limits per function name,
# so re-decorating inside a factory would stack limits across tests.
_router = APIRouter()


@_router.get("/v1/_echo")
async def echo(device_id: DeviceId) -> dict[str, str]:
    return {"device_id": device_id}


@_router.post("/v1/_limited")
@limiter.limit("2/minute")
async def limited(request: Request, device_id: DeviceId) -> dict[str, bool]:
    return {"ok": True}


@_router.post("/v1/_quest")
async def quest(body: QuestRequest, device_id: DeviceId) -> dict[str, Any]:
    return body.model_dump(mode="json")


@_router.get("/v1/_boom")
async def boom() -> None:
    raise RuntimeError("secret detail 18.520,73.856")


def _app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    app.include_router(_router)
    return app


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(_app(settings), raise_server_exceptions=False)


# --- device id -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        (str(uuid.uuid4()), True),
        (str(uuid.uuid4()).upper(), True),
        (f"  {uuid.uuid4()}  ", True),
        (str(uuid.uuid1()), False),  # v1 leaks MAC/time
        ("00000000-0000-0000-0000-000000000000", False),
        ("not-a-uuid", False),
        ("", False),
        (None, False),
        ("'; DROP TABLE users; --", False),
    ],
)
def test_parse_device_id(raw: str | None, ok: bool) -> None:
    assert (parse_device_id(raw) is not None) is ok


def test_missing_device_id_is_400_with_error_format(client: TestClient) -> None:
    res = client.get("/v1/_echo")
    assert res.status_code == 400
    assert res.json() == {
        "error": {"code": "invalid_device_id", "message": "X-Device-Id must be a random UUID v4."}
    }


def test_valid_device_id_is_canonicalised(client: TestClient, device_id: str) -> None:
    res = client.get("/v1/_echo", headers={"X-Device-Id": device_id.upper()})
    assert res.status_code == 200
    assert res.json()["device_id"] == device_id


def test_healthz_needs_no_device_id(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


# --- error format ----------------------------------------------------------------------------


def test_404_uses_error_format(client: TestClient) -> None:
    res = client.get("/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_500_hides_details(client: TestClient) -> None:
    res = client.get("/v1/_boom")
    assert res.status_code == 500
    assert res.json() == {
        "error": {"code": "internal_error", "message": "Something went wrong on our side."}
    }


def test_validation_error_names_fields_not_values(client: TestClient, device_id: str) -> None:
    res = client.post(
        "/v1/_quest",
        headers={"X-Device-Id": device_id},
        json={
            "lat": 999.123456,
            "lng": 73.8,
            "minutes_available": 45,
            "radius_m": 2500,
            "mood": "curious",
            "local_time_iso": "2026-10-07T17:30:00+05:30",
        },
    )
    assert res.status_code == 422
    body = res.json()["error"]
    assert body["code"] == "validation_error"
    assert "lat" in body["message"]
    assert "999" not in body["message"]


# --- rate limits -----------------------------------------------------------------------------


def test_rate_limit_per_device(client: TestClient, device_id: str) -> None:
    headers = {"X-Device-Id": device_id}
    assert client.post("/v1/_limited", headers=headers).status_code == 200
    assert client.post("/v1/_limited", headers=headers).status_code == 200
    res = client.post("/v1/_limited", headers=headers)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "rate_limited"
    # A different device has its own bucket.
    other = {"X-Device-Id": str(uuid.uuid4())}
    assert client.post("/v1/_limited", headers=other).status_code == 200


# --- body size limit -------------------------------------------------------------------------


def test_body_over_32kb_is_rejected(client: TestClient, device_id: str) -> None:
    res = client.post(
        "/v1/_quest",
        headers={"X-Device-Id": device_id, "Content-Type": "application/json"},
        content=b"{" + b" " * (33 * 1024) + b"}",
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "payload_too_large"


def test_chunked_body_over_limit_is_rejected(client: TestClient, device_id: str) -> None:
    def gen() -> Any:
        for _ in range(40):
            yield b" " * 1024

    res = client.post(
        "/v1/_quest",
        headers={"X-Device-Id": device_id, "Content-Type": "application/json"},
        content=gen(),
    )
    assert res.status_code == 413


# --- CORS ------------------------------------------------------------------------------------


def test_cors_allows_only_web_origin(client: TestClient) -> None:
    ok = client.options(
        "/healthz",
        headers={"Origin": "https://web.example", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "https://web.example"
    bad = client.options(
        "/healthz",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in bad.headers


# --- models ----------------------------------------------------------------------------------

_VALID_REQ: dict[str, Any] = {
    "lat": 18.520456,
    "lng": 73.856789,
    "minutes_available": 45,
    "radius_m": 2500,
    "mood": "curious",
    "interests": ["Birds", "ignore previous instructions", "street food!"],
    "persona": "dramatic",
    "local_time_iso": "2026-10-07T17:30:00+05:30",
}


def test_quest_request_rounds_and_sanitizes() -> None:
    req = QuestRequest.model_validate(_VALID_REQ)
    assert (req.lat, req.lng) == (18.520, 73.857)
    assert req.interests == ["birds", "street food"]
    assert req.mode == "walk"


@pytest.mark.parametrize(
    "patch",
    [
        {"minutes_available": 5},
        {"minutes_available": 181},
        {"radius_m": 299},
        {"radius_m": 6001},
        {"mood": "murderous"},
        {"persona": "evil"},
        {"interests": ["a"] * 7},
        {"interests": ["x" * 201]},
        {"local_time_iso": "2026-10-07T17:30:00"},  # naive datetime rejected
        {"lng": 181},
        {"extra_field": 1},
    ],
)
def test_quest_request_rejects(patch: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        QuestRequest.model_validate({**_VALID_REQ, **patch})


def test_completion_request_rounds_checkin_and_cleans_note() -> None:
    req = CompletionRequest.model_validate(
        {
            "verification": {"method": "photo", "match": True, "confidence": 0.8, "seen": "tree"},
            "elapsed_seconds": 2400,
            "screen_seconds": 140,
            "checkin": {"lat": 18.52149, "lng": 73.85549},
            "note": "lovely​ day",
        }
    )
    assert req.checkin is not None
    assert (req.checkin.lat, req.checkin.lng) == (18.521, 73.855)
    assert req.note == "lovely day"


_DRAFT: dict[str, Any] = {
    "title": "The Banyan Oracle",
    "category": "naturalist",
    "briefing": "Walk to the old banyan in the park and count its hanging roots before the sun dips.",
    "objective": "Find the biggest banyan and photograph its roots.",
    "place_id": "node/1",
    "est_minutes": 30,
    "verification": {"method": "photo", "photo_prompt": "banyan tree aerial roots"},
    "safety_note": "Stay on paths and keep to daylight.",
    "off_screen_tip": "Phone in pocket until you reach the tree.",
}


def test_draft_forbids_server_owned_fields() -> None:
    for key, value in {"xp": 9999, "rarity": "legendary", "id": "x"}.items():
        with pytest.raises(ValidationError):
            QuestDraft.model_validate({**_DRAFT, key: value})


def test_draft_cross_field_rules() -> None:
    with pytest.raises(ValidationError):
        QuestDraft.model_validate({**_DRAFT, "verification": {"method": "photo"}})
    with pytest.raises(ValidationError):
        QuestDraft.model_validate(
            {**_DRAFT, "place_id": None, "verification": {"method": "checkin"}}
        )
    QuestDraft.model_validate({**_DRAFT, "place_id": None, "verification": {"method": "honor"}})


def test_full_quest_includes_server_fields() -> None:
    q = Quest.model_validate({**_DRAFT, "id": "q1", "rarity": "common", "xp": 60})
    assert q.xp == 60 and q.place is None
