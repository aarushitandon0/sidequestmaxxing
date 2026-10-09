import pytest

from app.observability import SCRUBBED, ScrubbedSpan, hash_device_id, scrub_event


def test_scrub_event_removes_coordinates_text_and_hashes_device() -> None:
    device = "3f1c6c3e-1b7a-4f7e-9d7a-2b0c1d2e3f40"
    event = {
        "request": {
            "url": "https://api.example/v1/places/near?lat=18.52&lng=73.85",
            "query_string": "lat=18.52&lng=73.85",
            "headers": [["X-Device-Id", device], ["Accept", "application/json"]],
            "data": {"lat": 18.52, "note": "my house"},
        },
        "extra": {"checkin": {"lat": 1, "lng": 2}, "device_id": device, "ok": "fine"},
        "exception": {"values": [{"value": "bad point 18.520,73.856 here"}]},
    }
    out = scrub_event(event)
    assert out["request"]["url"] == "https://api.example/v1/places/near"
    assert out["request"]["query_string"] == SCRUBBED
    assert out["request"]["headers"][0] == ["X-Device-Id", hash_device_id(device)]
    assert out["request"]["headers"][1] == ["Accept", "application/json"]
    assert out["request"]["data"] == SCRUBBED
    assert out["extra"]["checkin"] == SCRUBBED
    assert out["extra"]["device_id"] == hash_device_id(device)
    assert out["extra"]["ok"] == "fine"
    assert "18.520" not in out["exception"]["values"][0]["value"]
    assert device not in str(out)


def test_scrubbing_keeps_the_gen_ai_attributes() -> None:
    """The scrubber walks span data; token counts and model names must survive it (D-62)."""
    event = {
        "spans": [
            {
                "op": "gen_ai.chat",
                "description": "chat quest",
                "data": {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "llama.cpp",
                    "gen_ai.request.model": "quest",
                    "gen_ai.response.model": "tuned.gguf",
                    "gen_ai.usage.input_tokens": 400,
                    "gen_ai.usage.output_tokens": 120,
                    "latency_ms": 812,
                },
            }
        ]
    }
    data = scrub_event(event)["spans"][0]["data"]
    assert data["gen_ai.usage.input_tokens"] == 400
    assert data["gen_ai.usage.output_tokens"] == 120
    assert data["gen_ai.response.model"] == "tuned.gguf"
    assert data["gen_ai.provider.name"] == "llama.cpp"
    assert data["latency_ms"] == 812


def test_hash_device_id_is_stable_and_short() -> None:
    assert hash_device_id("a") == hash_device_id("a")
    assert len(hash_device_id("a")) == 20


def test_url_logging_third_parties_are_quiet(caplog: pytest.LogCaptureFixture) -> None:
    """httpx/uvicorn INFO logs include query strings with lat/lng (MASTERSPEC §9.3)."""
    import logging

    from app.logging_setup import QUIET_LOGGERS, configure_logging

    configure_logging()
    for name in QUIET_LOGGERS:
        assert not logging.getLogger(name).isEnabledFor(logging.INFO), name
    logging.getLogger("httpx").info("HTTP Request: GET https://x/?latitude=18.52&longitude=73.85")
    assert "latitude" not in caplog.text


def test_scrub_strips_query_strings_from_span_data_and_descriptions() -> None:
    """Sentry's httpx integration records `http.query` on outgoing spans (Open-Meteo has lat/lng)."""
    event = {
        "spans": [
            {
                "description": "GET https://api.open-meteo.com/v1/forecast?latitude=18.52&longitude=73.86",
                "data": {"http.query": "latitude=18.52&longitude=73.86", "url": "https://x/y"},
            }
        ],
        "breadcrumbs": {"values": [{"data": {"url": "https://h/p?lat=18.52&lng=73.85"}}]},
    }
    out = scrub_event(event)
    assert "18.52" not in str(out)
    assert out["spans"][0]["description"] == "GET https://api.open-meteo.com/v1/forecast"


def test_scrubbed_span_cleans_data_at_the_authoring_boundary() -> None:
    """`span()` must scrub itself: no `before_send*` hook sees a streamed gen_ai span (D-62)."""

    class FakeSpan:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}
            self.status: str | None = None

        def set_data(self, key: str, value: object) -> None:
            self.data[key] = value

        def set_status(self, status: str) -> None:
            self.status = status

    raw = FakeSpan()
    s = ScrubbedSpan(raw)
    s.set_data("lat", 18.5204)
    s.set_data("interests", "coffee near my flat")
    s.set_data("note", "front door code 1234")
    s.set_data("device_id", "3f1c6c3e-1b7a-4f7e-9d7a-2b0c1d2e3f40")
    s.set_data("prompt_echo", "walk to 18.5204,73.8567 and look")
    s.set_data("url", "http://llm.internal/completion?lat=18.52&lng=73.85")
    s.set_data("gen_ai.usage.input_tokens", 400)
    s.set_status("internal_error")

    assert raw.data["lat"] == SCRUBBED
    assert raw.data["interests"] == SCRUBBED
    assert raw.data["note"] == SCRUBBED
    assert raw.data["device_id"] == hash_device_id("3f1c6c3e-1b7a-4f7e-9d7a-2b0c1d2e3f40")
    assert "18.5204" not in str(raw.data["prompt_echo"])
    assert raw.data["url"] == "http://llm.internal/completion"
    assert raw.data["gen_ai.usage.input_tokens"] == 400  # numbers survive
    assert raw.status == "internal_error"
