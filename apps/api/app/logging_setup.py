"""Structured JSON logging. Callers must not put PII (coords, device ids, free text) in logs."""

import json
import logging
from datetime import UTC, datetime

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

# Third-party loggers that would print request URLs, which carry coordinates
# (Open-Meteo query, /v1/places/near?lat=..). Our AccessLogMiddleware logs route templates only.
QUIET_LOGGERS = ("httpx", "httpcore", "uvicorn.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
