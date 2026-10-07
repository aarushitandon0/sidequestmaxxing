"""`quests` collection access (MASTERSPEC §5.2). One document per offered quest.

Never stores user coordinates: `request_digest` hashes only non-location request fields.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Literal

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.models.quest import Quest
from app.models.requests import QuestRequest

Doc = dict[str, Any]
QuestStatus = Literal["offered", "accepted", "completed", "skipped", "expired"]
QUEST_TTL = timedelta(hours=6)


def request_digest(req: QuestRequest) -> str:
    """Identifies a request shape for debugging/eval without any location data."""
    shape = {
        "minutes_available": req.minutes_available,
        "radius_m": req.radius_m,
        "mood": req.mood,
        "interests": req.interests,
        "persona": req.persona,
        "mode": req.mode,
    }
    raw = json.dumps(shape, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def utc_offset_minutes(req: QuestRequest) -> int:
    offset = req.local_time_iso.utcoffset()
    return round(offset.total_seconds() / 60) if offset is not None else 0


def new_quest_doc(
    quest: Quest,
    device_id: str,
    req: QuestRequest,
    *,
    source: str,
    model: str,
    now: datetime,
) -> Doc:
    return {
        "_id": quest.id,
        "device_id": device_id,
        "created_at": now,
        "request_digest": request_digest(req),
        "quest": quest.model_dump(mode="json"),
        "source": source,
        "model": model,
        "status": "offered",
        "accepted_at": None,
        "expires_at": now + QUEST_TTL,
        # The player's UTC offset (minutes), so completion can find their local date for
        # streaks and the daily XP cap without asking for location or time again.
        "utc_offset_min": utc_offset_minutes(req),
    }


async def insert_quest(db: AsyncDatabase[Doc], doc: Doc) -> None:
    await db["quests"].insert_one(doc)


async def get_quest(db: AsyncDatabase[Doc], quest_id: str, device_id: str) -> Doc | None:
    """A quest owned by this device (other devices' quests look like 404s)."""
    doc: Doc | None = await db["quests"].find_one({"_id": quest_id, "device_id": device_id})
    return doc


async def transition(
    db: AsyncDatabase[Doc],
    quest_id: str,
    device_id: str,
    from_statuses: list[QuestStatus],
    updates: Doc,
) -> Doc | None:
    """Atomic compare-and-set on status. Returns the updated doc, or None if the state moved."""
    doc: Doc | None = await db["quests"].find_one_and_update(
        {"_id": quest_id, "device_id": device_id, "status": {"$in": from_statuses}},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    return doc
