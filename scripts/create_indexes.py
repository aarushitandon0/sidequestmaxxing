"""Create collections, regular indexes and Atlas Vector Search indexes (MASTERSPEC §5).

Usage (repo root, MONGODB_URI in .env or the environment):
    python scripts/create_indexes.py
Idempotent. Never prints the connection string.
"""

import json
import logging
import sys

import _bootstrap  # noqa: F401  (sys.path side effect)
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import SearchIndexModel

from app.config import Settings
from app.services.indexes import COLLECTIONS, REGULAR_INDEXES, VECTOR_INDEXES

log = logging.getLogger("create_indexes")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()
    if not settings.mongodb_uri:
        log.error("MONGODB_URI is not set (put it in .env; don't paste it into chats).")
        return 2

    client: MongoClient[dict[str, object]] = MongoClient(
        settings.mongodb_uri, appname="sqm-scripts", serverSelectionTimeoutMS=10000
    )
    db = client[settings.mongodb_db]
    try:
        existing = set(db.list_collection_names())
        for name in COLLECTIONS:
            if name not in existing:
                db.create_collection(name)
                log.info("created collection %s", name)

        for coll, models in REGULAR_INDEXES.items():
            names = db[coll].create_indexes(models)
            log.info("indexes on %s: %s", coll, ", ".join(names))

        manual: list[str] = []
        for coll, (index_name, definition) in VECTOR_INDEXES.items():
            current = {i["name"] for i in db[coll].list_search_indexes()}
            try:
                if index_name in current:
                    db[coll].update_search_index(index_name, definition)
                    log.info("updated vector index %s.%s", coll, index_name)
                else:
                    db[coll].create_search_index(
                        SearchIndexModel(
                            definition=definition, name=index_name, type="vectorSearch"
                        )
                    )
                    log.info("created vector index %s.%s (builds async in Atlas)", coll, index_name)
            except OperationFailure as exc:
                log.warning("could not create %s via driver (%s)", index_name, exc.code)
                manual.append(f"{coll}.{index_name}:\n{json.dumps(definition, indent=2)}")

        if manual:
            log.warning(
                "Create these in Atlas UI → Search & Vector Search → JSON editor:\n%s",
                "\n\n".join(manual),
            )
    except PyMongoError as exc:
        log.error("MongoDB error: %s", type(exc).__name__)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
