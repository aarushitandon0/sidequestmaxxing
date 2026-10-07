import uuid

import pytest

from app.config import Settings
from app.ratelimit import limiter


@pytest.fixture
def settings() -> Settings:
    return Settings(env="test", web_origin="https://web.example", sentry_dsn=None)


@pytest.fixture
def device_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def _reset_limiter() -> None:
    limiter.reset()
