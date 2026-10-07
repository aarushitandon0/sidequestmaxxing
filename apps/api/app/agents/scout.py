"""Scout (MASTERSPEC §7.2, §3.1 steps 3-4): find ≤ 8 safe, reachable, fresh candidates.

1. Embed a query built from sanitized interests + a mood phrase.
2. Atlas $vectorSearch in the 3x3 geohash-5 block, haversine post-filter by radius.
3. Safety/time filters: indoor-only weather, daylight for daylight-only places, walkable in time.
4. Memory check: drop places visited in the last 14 days; report recent categories.
5. Diversity: at most 3 candidates per place kind.
Never raises on DB trouble: the quest pipeline can still run place-less via the fallback engine.
"""

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.agents.fallback_engine import WALK_M_PER_MIN
from app.models.context import QuestContext
from app.models.enums import Category, Mood
from app.models.requests import QuestRequest
from app.observability import span
from app.services.db import Doc
from app.services.embeddings import Embedder
from app.services.memories_repo import Memory, recent_similar_memories
from app.services.places_repo import MAX_CANDIDATES, Candidate, search_places
from app.validators.core import daylight_ok

log = logging.getLogger("sqm.scout")

MAX_PER_KIND = 3
MIN_ACTIVITY_MIN = 10  # shortest on-site activity we template for

MOOD_PHRASES: dict[Mood, str] = {
    "curious": "history heritage museum art something new to discover",
    "tired": "short easy calm spot bench cafe nearby",
    "restless": "open space walking trail park to move around",
    "social": "lively market cafe place to go with a friend",
    "calm": "quiet peaceful garden nature calm",
    "adventurous": "viewpoint hill trail nature reserve explore",
}


@dataclass
class ScoutResult:
    candidates: list[Candidate]
    query_text: str
    query_vector: list[float]
    recent_categories: list[Category] = field(default_factory=list)
    recent_place_ids: list[str] = field(default_factory=list)
    recent_embeddings: list[list[float]] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)  # reason → count (for traces)


def build_query_text(interests: Sequence[str], mood: Mood) -> str:
    """Only sanitized keywords and fixed phrases; never raw user text."""
    parts = [*interests, MOOD_PHRASES[mood]]
    return " ".join(p for p in parts if p)


def min_quest_minutes(distance_m: int) -> int:
    return round(2 * distance_m / WALK_M_PER_MIN) + MIN_ACTIVITY_MIN


def safety_filter(
    candidates: Sequence[Candidate], ctx: QuestContext, minutes_available: int
) -> tuple[list[Candidate], Counter[str]]:
    kept: list[Candidate] = []
    dropped: Counter[str] = Counter()
    for c in candidates:
        est = min_quest_minutes(c.distance_m)
        if ctx.indoor_only and not c.indoor:
            dropped["indoor_only"] += 1
        elif c.needs_daylight and not daylight_ok(est, ctx.daylight_minutes_left):
            dropped["daylight"] += 1
        elif est > minutes_available:
            dropped["too_far"] += 1
        else:
            kept.append(c)
    return kept, dropped


def diversify(candidates: Sequence[Candidate], limit: int = MAX_CANDIDATES) -> list[Candidate]:
    per_kind: Counter[str] = Counter()
    out: list[Candidate] = []
    for c in candidates:  # already ranked by vector score
        if per_kind[c.kind] < MAX_PER_KIND:
            out.append(c)
            per_kind[c.kind] += 1
        if len(out) == limit:
            break
    return out


async def memory_check(
    db: AsyncDatabase[Doc], query_vector: list[float], device_id: str, now: datetime
) -> list[Memory]:
    with span("memory.check") as s:
        try:
            memories = await recent_similar_memories(db, query_vector, device_id, now)
        except PyMongoError as exc:
            log.warning("memory check failed", extra={"error_type": type(exc).__name__})
            s.set_data("error", type(exc).__name__)
            return []
        s.set_data("memories", len(memories))
        return memories


async def scout(
    req: QuestRequest,
    ctx: QuestContext,
    device_id: str,
    db: AsyncDatabase[Doc] | None,
    embedder: Embedder,
    now: datetime | None = None,
) -> ScoutResult:
    now = now or datetime.now(UTC)
    query_text = build_query_text(req.interests, req.mood)
    [query_vector] = await embedder.embed([query_text])
    result = ScoutResult(candidates=[], query_text=query_text, query_vector=query_vector)
    if db is None:
        return result

    with span("scout.search") as s:
        try:
            found = await search_places(db, query_vector, req.lat, req.lng, req.radius_m)
        except PyMongoError as exc:
            log.warning("place search failed", extra={"error_type": type(exc).__name__})
            s.set_data("error", type(exc).__name__)
            found = []
        safe, dropped = safety_filter(found, ctx, req.minutes_available)

        memories = await memory_check(db, query_vector, device_id, now)
        seen_places = {m.place_id for m in memories if m.place_id}
        fresh = [c for c in safe if c.id not in seen_places]
        dropped["recently_visited"] += len(safe) - len(fresh)

        result.candidates = diversify(fresh)
        result.recent_place_ids = sorted(seen_places)
        result.recent_categories = list(dict.fromkeys(m.category for m in memories if m.category))
        result.recent_embeddings = [m.embedding for m in memories if m.embedding]
        result.dropped = dict(dropped)
        s.set_data("found", len(found))
        s.set_data("candidates", len(result.candidates))
        s.set_data("dropped", result.dropped)
    return result
