"""Collection + index definitions (MASTERSPEC §5). Used by scripts/create_indexes.py."""

from typing import Any

from pymongo import ASCENDING, DESCENDING, GEOSPHERE, IndexModel

from app.services.embeddings import EMBEDDING_DIM

PLACES_VECTOR_INDEX = "places_vec"
MEMORIES_VECTOR_INDEX = "memories_vec"
EVENTS_VECTOR_INDEX = "events_vec"
MEMORY_TTL_SECONDS = 90 * 24 * 3600

COLLECTIONS = (
    "places",
    "quests",
    "completions",
    "users",
    "memories",
    "recaps",
    "usage",
    "events",
)

REGULAR_INDEXES: dict[str, list[IndexModel]] = {
    "places": [
        IndexModel([("loc", GEOSPHERE)], name="loc_2dsphere"),
        IndexModel([("cell5", ASCENDING)], name="cell5"),
    ],
    "quests": [
        IndexModel([("device_id", ASCENDING), ("created_at", DESCENDING)], name="device_created"),
    ],
    "completions": [
        IndexModel(
            [("device_id", ASCENDING), ("completed_at", DESCENDING)], name="device_completed"
        ),
        IndexModel([("quest_id", ASCENDING)], name="quest_unique", unique=True),
    ],
    "memories": [
        IndexModel([("ts", ASCENDING)], name="ts_ttl", expireAfterSeconds=MEMORY_TTL_SECONDS),
        IndexModel([("device_id", ASCENDING), ("ts", DESCENDING)], name="device_ts"),
    ],
    "events": [
        IndexModel([("loc", GEOSPHERE)], name="loc_2dsphere"),
        IndexModel([("cell5", ASCENDING)], name="cell5"),
        # Events delete themselves once they are over, so staleness self-corrects (P23 §4).
        IndexModel([("ends_at", ASCENDING)], name="ends_at_ttl", expireAfterSeconds=0),
    ],
    "recaps": [
        IndexModel(
            [("device_id", ASCENDING), ("week_start", ASCENDING)], name="device_week", unique=True
        ),
    ],
}


def _vector(filters: list[str]) -> dict[str, Any]:
    return {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": EMBEDDING_DIM,
                "similarity": "cosine",
            },
            *({"type": "filter", "path": f} for f in filters),
        ]
    }


VECTOR_INDEXES: dict[str, tuple[str, dict[str, Any]]] = {
    "places": (PLACES_VECTOR_INDEX, _vector(["cell5", "kind"])),
    "memories": (MEMORIES_VECTOR_INDEX, _vector(["device_id", "ts"])),
    # `ends_at` is deliberately not a filter path: the time window is a `$match` stage
    # after $vectorSearch (P23 spec §4).
    "events": (EVENTS_VECTOR_INDEX, _vector(["cell5", "kind"])),
}
