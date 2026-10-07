"""FastAPI entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.deps import DEVICE_HEADER
from app.errors import install_error_handlers
from app.logging_setup import configure_logging
from app.middleware import AccessLogMiddleware, BodySizeLimitMiddleware
from app.observability import init_sentry
from app.ratelimit import limiter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    init_sentry(settings)

    app = FastAPI(title="Sidequestmaxxing API", version=settings.git_sha)
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
        return {"status": "ok", "db": "unknown", "llm": "unknown"}

    return app


app = create_app()
