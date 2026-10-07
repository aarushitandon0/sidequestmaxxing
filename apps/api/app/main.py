"""FastAPI entrypoint."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.deps import DEVICE_HEADER
from app.errors import install_error_handlers
from app.logging_setup import configure_logging
from app.middleware import AccessLogMiddleware, BodySizeLimitMiddleware
from app.observability import init_sentry
from app.ratelimit import limiter
from app.routers import places, profile, quests
from app.services.db import close_client, get_database, ping
from app.services.llm_health import llm_status


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_client()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    init_sentry(settings)

    app = FastAPI(title="Sidequestmaxxing API", version=settings.git_sha, lifespan=lifespan)
    app.state.settings = settings
    app.state.limiter = limiter
    install_error_handlers(app)

    # Order: last added runs first. Body limit must wrap everything.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", DEVICE_HEADER],
        max_age=600,
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        db_state, llm_state = await asyncio.gather(
            ping(get_database(settings)), llm_status(settings.llm_url)
        )
        return {"status": "ok", "db": db_state, "llm": llm_state}

    app.include_router(places.router)
    app.include_router(quests.router)
    app.include_router(profile.router)
    return app


app = create_app()
