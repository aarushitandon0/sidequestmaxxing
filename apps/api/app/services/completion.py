"""Quest completion (MASTERSPEC §3.2, §6.4, §8): validate, score, persist.

Server rules (§6.4): the quest belongs to the device; it is `accepted`; elapsed time is at
least min(0.4 * est_minutes * 60, 240) s; photo needs match=true and confidence ≥ 0.6; a
check-in more than 350 m from the place sets within_radius=false (XP x 0.5). Idempotent on
quest_id: the unique `completions.quest_id` index makes the insert the single claim, and a
repeat call returns the stored result.

Anti-cheat on time: elapsed counts as min(client elapsed, server time since accept + 60 s),
so a client can't claim more time than really passed (DECISIONS D-41).
Never stores the check-in coordinates: only the `within_radius` boolean.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.errors import ApiError
from app.models.enums import CATEGORIES, Category, Rarity
from app.models.profile import CompletionResult, LevelUp
from app.models.quest import QuestDraft
from app.models.requests import CompletionRequest
from app.services.db import Doc
from app.services.embeddings import Embedder
from app.services.game import (
    apply_daily_cap,
    category_level,
    next_streak,
    overall_level,
    quest_xp,
    title_for,
)
from app.services.geo import haversine_m
from app.services.memories_repo import upsert_memory
from app.validators.core import quest_memory_text

log = logging.getLogger("sqm.complete")

MIN_CONFIDENCE = 0.6
CHECKIN_RADIUS_M = 350
MIN_ELAPSED_CAP_S = 240
MIN_ELAPSED_FRACTION = 0.4
CLOCK_SLACK_S = 60


def min_elapsed_seconds(est_minutes: int) -> int:
    return int(min(MIN_ELAPSED_FRACTION * est_minutes * 60, MIN_ELAPSED_CAP_S))


def local_date(now: datetime, utc_offset_min: int) -> date:
    return (now.astimezone(UTC) + timedelta(minutes=utc_offset_min)).date()


@dataclass(frozen=True)
class Scored:
    method: str
    within_radius: bool | None
    elapsed_seconds: int
    screen_share: float | None


def check_and_score(quest_doc: Doc, body: CompletionRequest, now: datetime) -> Scored:
    """Pure validation of a completion against its quest. Raises ApiError on rejection."""
    quest: dict[str, Any] = quest_doc["quest"]
    v = body.verification
    place = quest.get("place")
    photo_prompt = (quest.get("verification") or {}).get("photo_prompt")

    accepted_at: datetime | None = quest_doc.get("accepted_at")
    server_elapsed = (now - accepted_at).total_seconds() if accepted_at else 0
    elapsed = int(min(body.elapsed_seconds, max(0.0, server_elapsed) + CLOCK_SLACK_S))
    if elapsed < min_elapsed_seconds(int(quest["est_minutes"])):
        raise ApiError(422, "quest_too_short", "That was quick! Give the quest a bit more time.")

    if v.method == "photo":
        if not photo_prompt:
            raise ApiError(422, "method_not_allowed", "This quest has no photo check.")
        if not (v.match is True and v.confidence is not None and v.confidence >= MIN_CONFIDENCE):
            raise ApiError(422, "not_verified", "The photo didn't match. Retake it or check in.")
    if v.method == "checkin" and (place is None or body.checkin is None):
        raise ApiError(422, "method_not_allowed", "Check-in needs a quest place and your check-in.")

    within_radius: bool | None = None
    if body.checkin is not None and place is not None:
        d = haversine_m(body.checkin.lat, body.checkin.lng, place["lat"], place["lng"])
        within_radius = d <= CHECKIN_RADIUS_M

    screen_share = min(1.0, body.screen_seconds / elapsed) if elapsed > 0 else None
    return Scored(v.method, within_radius, elapsed, screen_share)


def _level_ups(
    category: Category, old_cat_xp: int, new_cat_xp: int, old_total: int, new_total: int
) -> list[LevelUp]:
    ups: list[LevelUp] = []
    a, b = category_level(old_cat_xp), category_level(new_cat_xp)
    if b > a:
        ups.append(LevelUp(kind="category", category=category, from_level=a, to_level=b,
                           title=title_for(category, b)))  # fmt: skip
    a, b = overall_level(old_total), overall_level(new_total)
    if b > a:
        ups.append(LevelUp(kind="overall", from_level=a, to_level=b))
    return ups


def default_user(device_id: str, now: datetime) -> Doc:
    return {
        "_id": device_id,
        "created_at": now,
        "persona": "chill",
        "interests": [],
        "default_radius_m": 2500,
        "skills": {c: 0 for c in CATEGORIES},
        "total_xp": 0,
        "streak_days": 0,
        "last_completed_date": None,
        "settings": {"safe_mode": True, "voice": True},
    }


async def complete_quest(
    db: AsyncDatabase[Doc],
    embedder: Embedder,
    device_id: str,
    quest_id: str,
    body: CompletionRequest,
    now: datetime,
) -> CompletionResult:
    existing = await db["completions"].find_one({"quest_id": quest_id, "device_id": device_id})
    if existing is not None:
        return CompletionResult.model_validate(existing["result"])

    quest_doc = await db["quests"].find_one({"_id": quest_id, "device_id": device_id})
    if quest_doc is None:
        raise ApiError(404, "quest_not_found", "That quest isn't in your quest log.")
    if quest_doc["status"] != "accepted":
        raise ApiError(409, "invalid_quest_state", f"This quest is {quest_doc['status']}.")

    scored = check_and_score(quest_doc, body, now)
    quest: dict[str, Any] = quest_doc["quest"]
    category: Category = quest["category"]
    rarity: Rarity = quest["rarity"]
    offset = int(quest_doc.get("utc_offset_min", 0))
    today = local_date(now, offset)

    user = await db["users"].find_one({"_id": device_id}) or default_user(device_id, now)
    last = user.get("last_completed_date")
    last_date = date.fromisoformat(last) if isinstance(last, str) else None
    streak = next_streak(int(user.get("streak_days", 0)), last_date, today)

    raw_xp = quest_xp(
        int(quest["est_minutes"]),
        rarity,
        scored.method,  # type: ignore[arg-type]
        within_radius=scored.within_radius,
        screen_share=scored.screen_share,
        streak_days=streak,
    )
    today_docs = (
        await db["completions"]
        .find({"device_id": device_id, "local_date": today.isoformat()})
        .to_list(length=None)
    )
    already_today = sum(int(d.get("xp_awarded", 0)) for d in today_docs)
    xp = apply_daily_cap(raw_xp, already_today)

    skills: dict[str, int] = {str(c): 0 for c in CATEGORIES}
    skills.update(user.get("skills") or {})
    old_cat, old_total = skills[category], int(user.get("total_xp", 0))
    skills[category] = old_cat + xp
    new_total = old_total + xp

    result = CompletionResult(
        quest_id=quest_id,
        xp_awarded=xp,
        level_ups=_level_ups(category, old_cat, skills[category], old_total, new_total),
        streak=streak,
        total_xp=new_total,
        level=overall_level(new_total),
        within_radius=scored.within_radius,
        screen_share=round(scored.screen_share, 4) if scored.screen_share is not None else None,
        daily_cap_reached=xp < raw_xp,
    )
    place = quest.get("place") or {}
    completion = {
        "_id": str(uuid.uuid4()),
        "device_id": device_id,
        "quest_id": quest_id,
        "completed_at": now,
        "local_date": today.isoformat(),
        "verification": body.verification.model_dump(),
        "elapsed_seconds": scored.elapsed_seconds,
        "screen_seconds": body.screen_seconds,
        "screen_share": result.screen_share,
        "within_radius": scored.within_radius,
        "xp_awarded": xp,
        "category": category,
        "place_id": quest.get("place_id"),
        "place_name": place.get("name"),
        "title": quest.get("title"),
        "note": body.note,
        "result": result.model_dump(mode="json"),
    }
    try:
        await db["completions"].insert_one(completion)  # the single claim (unique quest_id)
    except DuplicateKeyError:
        existing = await db["completions"].find_one({"quest_id": quest_id})
        if existing is None or existing.get("device_id") != device_id:
            raise ApiError(409, "invalid_quest_state", "This quest is already done.") from None
        return CompletionResult.model_validate(existing["result"])

    await db["quests"].update_one(
        {"_id": quest_id, "device_id": device_id},
        {"$set": {"status": "completed", "completed_at": now}},
    )
    await db["users"].update_one(
        {"_id": device_id},
        {
            "$set": {
                "skills": skills,
                "total_xp": new_total,
                "streak_days": streak,
                "last_completed_date": today.isoformat(),
                "utc_offset_min": offset,
            },
            "$setOnInsert": {
                k: v
                for k, v in default_user(device_id, now).items()
                if k not in {"_id", "skills", "total_xp", "streak_days", "last_completed_date"}
            },
        },
        upsert=True,
    )
    draft = QuestDraft.model_validate({k: quest[k] for k in QuestDraft.model_fields})
    text = quest_memory_text(draft, place.get("name"))
    [vector] = await embedder.embed([text])
    await upsert_memory(db, quest_id=quest_id, device_id=device_id, ts=now, text=text,
                        category=category, place_id=draft.place_id, embedding=vector,
                        kind="completed")  # fmt: skip
    log.info("quest completed", extra={"xp": xp, "method": scored.method,
                                       "within_radius": scored.within_radius})  # fmt: skip
    return result
