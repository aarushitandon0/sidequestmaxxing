"""Quest validators V1-V12 (MASTERSPEC §7.4). Pure functions.

Used three ways: on every LLM output in production, as the training-data filter, and as the
eval metric. `validate_quest` never raises; it returns every failure it can find.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, get_args

from pydantic import ValidationError

from app.models.enums import Category
from app.models.quest import QuestDraft
from app.services.embeddings import cosine
from app.services.places_repo import Candidate
from app.validators.lint import banned_hits, contact_hits, people_hits

DAYLIGHT_BUFFER_MIN = 30  # §9.1: now + est_minutes + 30 min must be before sunset
NEAR_DUPLICATE_COSINE = 0.9
MAX_BRIEFING_WORDS = 70
SAFETY_NOTE_MIN, SAFETY_NOTE_MAX = 10, 140

# Emoji & pictographs, plus hashtags: briefings are spoken (prompt rule 5).
_EMOJI = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff\U00002b00-\U00002bff]"
)
_HASHTAG = re.compile(r"(?:^|\s)#\w")

_LENGTHS: dict[str, tuple[int, int]] = {
    "title": (3, 60),
    "briefing": (40, 360),
    "objective": (5, 140),
    "safety_note": (1, 140),
    "off_screen_tip": (1, 100),
}


@dataclass(frozen=True)
class Failure:
    id: str
    reason: str


@dataclass(frozen=True)
class ValidationContext:
    minutes_available: int
    indoor_only: bool = False
    daylight_minutes_left: int | None = None  # None = unknown → treated as no daylight


@dataclass
class ValidationResult:
    quest: QuestDraft | None
    failures: list[Failure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.quest is not None and not self.failures

    @property
    def failure_ids(self) -> list[str]:
        return sorted({f.id for f in self.failures})


def _strings(q: QuestDraft) -> dict[str, str]:
    out = {
        "title": q.title,
        "briefing": q.briefing,
        "objective": q.objective,
        "safety_note": q.safety_note,
        "off_screen_tip": q.off_screen_tip,
    }
    if q.verification.photo_prompt:
        out["photo_prompt"] = q.verification.photo_prompt
    return out


# --- V1 ----------------------------------------------------------------------------------------


def v1_parse(raw: str | dict[str, Any] | QuestDraft) -> tuple[QuestDraft | None, list[Failure]]:
    try:
        if isinstance(raw, QuestDraft):
            data: Any = raw.model_dump()
        elif isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw
        if not isinstance(data, dict):
            return None, [Failure("V1", "output is not a JSON object")]
        return QuestDraft.model_validate(data), []
    except json.JSONDecodeError as exc:
        return None, [Failure("V1", f"invalid JSON: {exc.msg}")]
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) or "<root>" for e in exc.errors()})
        return None, [Failure("V1", f"schema mismatch: {', '.join(fields)}")]


# --- V2-V12 ------------------------------------------------------------------------------------


def v2_grounding(q: QuestDraft, candidates: Sequence[Candidate]) -> list[Failure]:
    if q.place_id is None or q.place_id in {c.id for c in candidates}:
        return []
    return [Failure("V2", "place_id is not one of the candidates")]


def v3_minutes(q: QuestDraft, ctx: ValidationContext) -> list[Failure]:
    if 5 <= q.est_minutes <= ctx.minutes_available:
        return []
    return [Failure("V3", f"est_minutes {q.est_minutes} not in 5..{ctx.minutes_available}")]


def v4_banned_terms(q: QuestDraft) -> list[Failure]:
    out: list[Failure] = []
    for name, text in _strings(q).items():
        for hit in banned_hits(text):
            out.append(Failure("V4", f"{name}: banned term ({hit.rule})"))
    return out


def v5_safety_note(q: QuestDraft) -> list[Failure]:
    n = len(q.safety_note.strip())
    if SAFETY_NOTE_MIN <= n <= SAFETY_NOTE_MAX:
        return []
    return [Failure("V5", f"safety_note length {n} not in {SAFETY_NOTE_MIN}..{SAFETY_NOTE_MAX}")]


def v6_photo_not_people(q: QuestDraft) -> list[Failure]:
    prompt = q.verification.photo_prompt
    if not prompt:
        return []
    hits = people_hits(prompt)
    return [Failure("V6", f"photo_prompt mentions people ({hits[0]})")] if hits else []


def v7_lengths(q: QuestDraft) -> list[Failure]:
    out: list[Failure] = []
    strings = _strings(q)
    for name, (lo, hi) in _LENGTHS.items():
        n = len(strings[name])
        if not lo <= n <= hi:
            out.append(Failure("V7", f"{name} length {n} not in {lo}..{hi}"))
    if q.verification.photo_prompt and len(q.verification.photo_prompt) > 100:
        out.append(Failure("V7", "photo_prompt longer than 100"))
    words = len(q.briefing.split())
    if words > MAX_BRIEFING_WORDS:
        out.append(Failure("V7", f"briefing has {words} words (max {MAX_BRIEFING_WORDS})"))
    for name, text in strings.items():
        if _EMOJI.search(text) or _HASHTAG.search(text):
            out.append(Failure("V7", f"{name}: emoji or hashtag"))
    return out


def v8_no_contact_info(q: QuestDraft) -> list[Failure]:
    return [
        Failure("V8", f"{name}: contains URL/email/phone")
        for name, text in _strings(q).items()
        if contact_hits(text)
    ]


def _place(q: QuestDraft, candidates: Sequence[Candidate]) -> Candidate | None:
    return next((c for c in candidates if c.id == q.place_id), None)


def v9_indoor_only(
    q: QuestDraft, ctx: ValidationContext, candidates: Sequence[Candidate]
) -> list[Failure]:
    if not ctx.indoor_only or q.place_id is None:
        return []
    place = _place(q, candidates)
    if place is not None and place.indoor:
        return []
    return [Failure("V9", "indoor_only context but place is not indoor")]


def daylight_ok(est_minutes: int, daylight_minutes_left: int | None) -> bool:
    if daylight_minutes_left is None:
        return False
    return est_minutes + DAYLIGHT_BUFFER_MIN <= daylight_minutes_left


def v10_daylight(
    q: QuestDraft, ctx: ValidationContext, candidates: Sequence[Candidate]
) -> list[Failure]:
    place = _place(q, candidates) if q.place_id else None
    if place is None or not place.needs_daylight:
        return []
    if daylight_ok(q.est_minutes, ctx.daylight_minutes_left):
        return []
    return [Failure("V10", "place needs daylight but not enough daylight is left")]


def v11_category(q: QuestDraft) -> list[Failure]:
    if q.category in get_args(Category):
        return []
    return [Failure("V11", f"unknown category {q.category!r}")]


def v12_not_duplicate(
    quest_embedding: Sequence[float] | None, recent_embeddings: Sequence[Sequence[float]]
) -> list[Failure]:
    if quest_embedding is None:
        return []
    for other in recent_embeddings:
        if cosine(list(quest_embedding), list(other)) >= NEAR_DUPLICATE_COSINE:
            return [Failure("V12", "near-duplicate of a quest from the last 14 days")]
    return []


def validate_quest(
    quest: str | dict[str, Any] | QuestDraft,
    ctx: ValidationContext,
    candidates: Sequence[Candidate],
    recent_embeddings: Sequence[Sequence[float]] = (),
    quest_embedding: Sequence[float] | None = None,
) -> ValidationResult:
    """Run V1-V12. V12 only runs when the caller supplies `quest_embedding`."""
    parsed, failures = v1_parse(quest)
    if parsed is None:
        return ValidationResult(None, failures)
    failures += v2_grounding(parsed, candidates)
    failures += v3_minutes(parsed, ctx)
    failures += v4_banned_terms(parsed)
    failures += v5_safety_note(parsed)
    failures += v6_photo_not_people(parsed)
    failures += v7_lengths(parsed)
    failures += v8_no_contact_info(parsed)
    failures += v9_indoor_only(parsed, ctx, candidates)
    failures += v10_daylight(parsed, ctx, candidates)
    failures += v11_category(parsed)
    failures += v12_not_duplicate(quest_embedding, recent_embeddings)
    return ValidationResult(parsed, failures)


def quest_memory_text(q: QuestDraft, place_name: str | None = None) -> str:
    """Text embedded for V12 and `memories`: title — objective — category — place."""
    return " — ".join(p for p in (q.title, q.objective, q.category, place_name) if p)
