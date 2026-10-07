"""Profile endpoints: GET /v1/profile, PUT /v1/profile/settings, DELETE /v1/profile.

DELETE removes every document tied to the device id (MASTERSPEC §9.3 "Delete my data").
"""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.deps import DeviceId, Now, get_db
from app.errors import db_unavailable
from app.models.enums import CATEGORIES, Category
from app.models.profile import Profile, RecentCompletion, SkillProgress, UserSettings
from app.models.requests import SettingsUpdate
from app.ratelimit import limiter
from app.services.completion import default_user, local_date
from app.services.db import Doc
from app.services.game import (
    category_level,
    category_xp_for_level,
    current_streak,
    overall_level,
    overall_xp_for_level,
    title_for,
)

router = APIRouter(prefix="/v1/profile", tags=["profile"])
Db = Annotated[AsyncDatabase[Doc], Depends(get_db)]
RECENT_LIMIT = 20
DEVICE_COLLECTIONS = ("quests", "completions", "memories", "recaps")


def _recent(doc: Doc) -> RecentCompletion:
    return RecentCompletion(
        quest_id=doc["quest_id"],
        completed_at=doc["completed_at"],
        title=doc.get("title"),
        category=doc["category"],
        xp_awarded=int(doc.get("xp_awarded", 0)),
        verification_method=(doc.get("verification") or {}).get("method", "honor"),
        place_name=doc.get("place_name"),
        minutes_outside=round(int(doc.get("elapsed_seconds", 0)) / 60),
        screen_share=doc.get("screen_share"),
    )


def build_profile(user: Doc, recent: list[Doc], completed: int, now: datetime) -> Profile:
    skills_xp: dict[str, int] = dict(user.get("skills") or {})
    skills: dict[Category, SkillProgress] = {}
    for c in CATEGORIES:
        xp = int(skills_xp.get(c, 0))
        lvl = category_level(xp)
        skills[c] = SkillProgress(xp=xp, level=lvl, title=title_for(c, lvl),
                                  next_level_xp=category_xp_for_level(lvl + 1))  # fmt: skip
    total = int(user.get("total_xp", 0))
    level = overall_level(total)
    last = user.get("last_completed_date")
    today = local_date(now, int(user.get("utc_offset_min", 0)))
    return Profile(
        persona=user.get("persona", "chill"),
        interests=list(user.get("interests") or []),
        default_radius_m=int(user.get("default_radius_m", 2500)),
        skills=skills,
        total_xp=total,
        level=level,
        next_level_xp=overall_xp_for_level(level + 1),
        streak_days=current_streak(
            int(user.get("streak_days", 0)),
            date.fromisoformat(last) if isinstance(last, str) else None,
            today,
        ),
        quests_completed=completed,
        settings=UserSettings.model_validate(user.get("settings") or {}),
        recent=[_recent(d) for d in recent],
    )


async def _load(db: AsyncDatabase[Doc], device_id: str, now: datetime) -> Profile:
    user = await db["users"].find_one({"_id": device_id}) or default_user(device_id, now)
    cursor = db["completions"].find({"device_id": device_id}).sort("completed_at", -1)
    recent = await cursor.limit(RECENT_LIMIT).to_list(length=None)
    completed = await db["completions"].count_documents({"device_id": device_id})
    return build_profile(user, recent, completed, now)


@router.get("", response_model=Profile)
@limiter.limit("60/minute")
async def get_profile(request: Request, device_id: DeviceId, db: Db, now: Now) -> Profile:
    try:
        return await _load(db, device_id, now)
    except PyMongoError as exc:
        raise db_unavailable() from exc


@router.put("/settings", response_model=Profile)
@limiter.limit("30/minute")
async def put_settings(
    request: Request, body: SettingsUpdate, device_id: DeviceId, db: Db, now: Now
) -> Profile:
    try:
        user = await db["users"].find_one({"_id": device_id}) or default_user(device_id, now)
        updates: dict[str, Any] = body.model_dump(exclude_none=True)
        settings = dict(user.get("settings") or {})
        for key in ("voice", "safe_mode"):
            if key in updates:
                settings[key] = updates.pop(key)
        user.update(updates)
        user["settings"] = settings
        fields = {k: v for k, v in user.items() if k != "_id"}
        await db["users"].update_one({"_id": device_id}, {"$set": fields}, upsert=True)
        return await _load(db, device_id, now)
    except PyMongoError as exc:
        raise db_unavailable() from exc


@router.delete("", status_code=204)
@limiter.limit("10/minute")
async def delete_profile(request: Request, device_id: DeviceId, db: Db) -> Response:
    """Removes the user doc and every quest, completion, memory and recap for this device."""
    try:
        await db["users"].delete_many({"_id": device_id})
        for name in DEVICE_COLLECTIONS:
            await db[name].delete_many({"device_id": device_id})
    except PyMongoError as exc:
        raise db_unavailable() from exc
    return Response(status_code=204)
