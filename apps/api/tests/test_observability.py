import pytest

from app.observability import SCRUBBED, hash_device_id, scrub_event


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
