"""Weekly Chronicle data access (MASTERSPEC §3.3, §5.6).

Window = the 7 local days ending today (by each completion's stored `local_date`).
One `recaps` doc per (device, week_start): a repeat call returns the stored recap unless the
set of completions changed since, in which case it is rewritten (same week_start).
"""

import logging
from datetime import date, datetime, timedelta

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.models.enums import Persona
from app.services.db import Doc
from app.validators.recap import RecapCompletion

log = logging.getLogger("sqm.recaps")

WINDOW_DAYS = 7
MAX_RECAP_COMPLETIONS = 40  # cap prompt size; a real week is far below this


def window(today: date) -> tuple[date, date]:
    return today - timedelta(days=WINDOW_DAYS - 1), today


def week_label(start: date, end: date) -> str:
    return f"{start.strftime('%b')} {start.day} - {end.strftime('%b')} {end.day}"


async def week_completions(db: AsyncDatabase[Doc], device_id: str, start: date) -> list[Doc]:
    cursor = (
        db["completions"]
        .find({"device_id": device_id, "local_date": {"$gte": start.isoformat()}})
        .sort("completed_at", 1)
    )
    docs: list[Doc] = await cursor.limit(MAX_RECAP_COMPLETIONS).to_list(length=None)
    return docs


def to_recap_completion(doc: Doc) -> RecapCompletion:
    day = ""
    if isinstance(doc.get("local_date"), str):
        day = date.fromisoformat(doc["local_date"]).strftime("%A")
    return RecapCompletion(
        title=str(doc.get("title") or "A side quest"),
        category=doc["category"],
        place_name=doc.get("place_name") or None,
        minutes_outside=round(int(doc.get("elapsed_seconds", 0)) / 60),
        day=day,
    )


def completion_ids(docs: list[Doc]) -> list[str]:
    return sorted(str(d["quest_id"]) for d in docs)


async def find_recap(db: AsyncDatabase[Doc], device_id: str, start: date) -> Doc | None:
    return await db["recaps"].find_one({"device_id": device_id, "week_start": start.isoformat()})


async def save_recap(db: AsyncDatabase[Doc], doc: Doc) -> None:
    """Replace this week's recap. A new `_id` per text, so cached audio is never stale.

    The unique (device_id, week_start) index keeps one recap per week; if a concurrent call
    stored one first, we keep theirs.
    """
    await db["recaps"].delete_many({"device_id": doc["device_id"], "week_start": doc["week_start"]})
    try:
        await db["recaps"].insert_one(doc)
    except DuplicateKeyError:
        log.info("recap already stored by a concurrent request")


async def get_recap(db: AsyncDatabase[Doc], device_id: str, recap_id: str) -> Doc | None:
    return await db["recaps"].find_one({"_id": recap_id, "device_id": device_id})


async def device_persona(db: AsyncDatabase[Doc], device_id: str) -> tuple[Persona, int]:
    user = await db["users"].find_one({"_id": device_id}) or {}
    return user.get("persona", "chill"), int(user.get("utc_offset_min", 0))


def stored_at(doc: Doc) -> datetime | None:
    value = doc.get("created_at")
    return value if isinstance(value, datetime) else None
