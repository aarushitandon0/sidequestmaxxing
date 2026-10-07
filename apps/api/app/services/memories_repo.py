"""Per-device quest memory lookups (MASTERSPEC §3.1 step 4, §5.5)."""

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from app.models.enums import Category
from app.services.indexes import MEMORIES_VECTOR_INDEX

Doc = dict[str, Any]
MEMORY_WINDOW = timedelta(days=14)


class Memory(BaseModel):
    category: Category | None = None
    place_id: str | None = None
    ts: datetime | None = None
    embedding: list[float] | None = None
    score: float | None = None


def build_memories_pipeline(
    query_vector: list[float], device_id: str, since: datetime, limit: int = 20
) -> list[Doc]:
    return [
        {
            "$vectorSearch": {
                "index": MEMORIES_VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": limit * 5,
                "limit": limit,
                "filter": {"$and": [{"device_id": {"$eq": device_id}}, {"ts": {"$gte": since}}]},
            }
        },
        {
            "$project": {
                "_id": 0,
                "category": 1,
                "place_id": 1,
                "ts": 1,
                "embedding": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]


async def recent_similar_memories(
    db: AsyncDatabase[Doc], query_vector: list[float], device_id: str, now: datetime
) -> list[Memory]:
    pipeline = build_memories_pipeline(query_vector, device_id, now - MEMORY_WINDOW)
    cursor = await db["memories"].aggregate(pipeline)
    docs: list[Doc] = await cursor.to_list(length=None)
    return [Memory.model_validate(d) for d in docs]
