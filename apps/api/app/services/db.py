"""MongoDB access via PyMongo's native async API (AsyncMongoClient). See DECISIONS D-4."""

import logging
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.config import Settings

log = logging.getLogger("sqm.db")

Doc = dict[str, Any]

_client: AsyncMongoClient[Doc] | None = None


def get_client(settings: Settings) -> AsyncMongoClient[Doc] | None:
    """Lazily create one client per process; None when MONGODB_URI isn't configured."""
    global _client
    if _client is None and settings.mongodb_uri:
        _client = AsyncMongoClient(
            settings.mongodb_uri,
            appname="sqm-api",
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            tz_aware=True,
        )
    return _client


def get_database(settings: Settings) -> AsyncDatabase[Doc] | None:
    client = get_client(settings)
    return client[settings.mongodb_db] if client is not None else None


async def ping(db: AsyncDatabase[Doc] | None) -> str:
    """'ok' | 'down' | 'unknown' (not configured). Never raises."""
    if db is None:
        return "unknown"
    try:
        await db.command("ping")
    except PyMongoError as exc:
        log.warning("db ping failed", extra={"error_type": type(exc).__name__})
        return "down"
    return "ok"


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
