"""FastAPI entrypoint."""

from fastapi import FastAPI

from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Sidequestmaxxing API", version=settings.git_sha)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "db": "unknown", "llm": "unknown"}

    return app


app = create_app()
