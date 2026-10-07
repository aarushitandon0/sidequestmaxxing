"""Export the seeded `places` collection to data/places.jsonl for make_contexts.py.

  python training/dump_places.py            # uses MONGODB_URI / MONGODB_DB from .env

Places are public OpenStreetMap features (no user data). Embeddings are not exported.
"""

import argparse
from pathlib import Path

from pymongo import MongoClient

from common import DATA, write_jsonl
from make_contexts import place_to_row

from app.config import get_settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DATA / "places.jsonl")
    args = ap.parse_args(argv)
    s = get_settings()
    if not s.mongodb_uri:
        raise SystemExit("MONGODB_URI is not set.")
    client: MongoClient[dict[str, object]] = MongoClient(
        s.mongodb_uri, serverSelectionTimeoutMS=8000
    )
    try:
        docs = client[s.mongodb_db]["places"].find({}, {"embedding": 0, "text": 0})
        n = write_jsonl(args.out, (place_to_row(d) for d in docs))
    finally:
        client.close()
    print(f"wrote {n} places → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
