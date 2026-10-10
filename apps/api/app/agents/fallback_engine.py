"""Deterministic template quest engine (MASTERSPEC §7.5).

Used when the LLM is down, slow, or fails validation twice. Given the same inputs and seed it
returns the same quest, and every quest it returns passes V1-V11 (property-tested). It never
raises: if no candidate fits, it falls back to a place-less quest.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.agents.templates import ANYWHERE_TEMPLATES, PLACE_TEMPLATES, Template
from app.models.enums import CATEGORIES, Category, Mood, Persona
from app.models.quest import QuestDraft, QuestVerification
from app.services.places_repo import Candidate
from app.validators.core import ValidationContext, daylight_ok, validate_quest

WALK_M_PER_MIN = 75  # relaxed walking pace


@dataclass(frozen=True)
class FallbackInput:
    minutes_available: int
    persona: Persona = "chill"
    mood: Mood = "curious"
    interests: Sequence[str] = ()
    candidates: Sequence[Candidate] = ()
    recent_categories: Sequence[Category] = ()
    indoor_only: bool = False
    daylight_minutes_left: int | None = None
    now: datetime | None = None  # the player's clock; without it V13 cannot run here (P23)
    seed: int = 0

    def validation_context(self) -> ValidationContext:
        return ValidationContext(
            minutes_available=self.minutes_available,
            indoor_only=self.indoor_only,
            daylight_minutes_left=self.daylight_minutes_left,
            now=self.now,
        )


_OPENERS: dict[Persona, tuple[str, ...]] = {
    "chill": ("Okay, easy one.", "No rush today.", "Here's a gentle one."),
    "dramatic": ("Hear me, adventurer!", "A quest has risen!", "The realm calls your name!"),
    "nature_nerd": ("Oh, this is a good one.", "Nature has plans for you.", "Field notes time."),
    "sarcastic": ("Bold move, leaving the couch.", "Brace yourself: fresh air.", "Big day, huh?"),
}
_CLOSERS: dict[Persona, tuple[str, ...]] = {
    "chill": ("Take it easy.", "Enjoy the walk.", "Report back when you're done."),
    "dramatic": ("Return victorious!", "Glory awaits!", "Go now, and be legend."),
    "nature_nerd": ("Notice the small stuff.", "Look closely, it's all alive.", "Happy noticing."),
    "sarcastic": ("I'll pretend not to be impressed.", "Try to enjoy it.", "Go on, I'll wait."),
}
_SAFETY_NOTES: tuple[str, ...] = (
    "Stick to public paths and tell someone where you are going.",
    "Stay on marked paths, keep to busy areas, and head home before dark.",
    "Use pedestrian crossings, stay aware of traffic, and keep to public spaces.",
    "Carry water, stay in well-lit public areas, and listen to your body.",
)
_OFF_SCREEN_TIPS: tuple[str, ...] = (
    "Phone in your pocket until the quest is done.",
    "Put the phone away; the quest is out there, not on the screen.",
    "Screen off. Eyes up. You've got this.",
)


def _travel_minutes(distance_m: int) -> int:
    return round(2 * distance_m / WALK_M_PER_MIN)  # there and back


def _place_usable(c: Candidate, inp: FallbackInput, est: int) -> bool:
    if inp.indoor_only and not c.indoor:
        return False
    if c.needs_daylight and not daylight_ok(est, inp.daylight_minutes_left):
        return False
    return 5 <= est <= inp.minutes_available


def _category_order(inp: FallbackInput, rng: random.Random) -> list[Category]:
    fresh = [c for c in CATEGORIES if c not in inp.recent_categories]
    stale = [c for c in CATEGORIES if c in inp.recent_categories]
    rng.shuffle(fresh)
    rng.shuffle(stale)
    return fresh + stale


def _template_fits(t: Template, inp: FallbackInput) -> bool:
    """Time-of-day and free-slot gates (P24).

    A sunrise quest offered at 6 pm, or a 90-minute class squeezed into a 20-minute slot, is
    a quest nobody can do. Without a clock the hour window cannot be checked, so those
    templates sit this one out rather than guess.
    """
    if t.min_minutes and inp.minutes_available < t.min_minutes:
        return False
    if t.hours is not None:
        if inp.now is None:
            return False
        start, end = t.hours
        if not start <= inp.now.hour < end:
            return False
    return True


def _compose(t: Template, name: str | None, inp: FallbackInput, rng: random.Random, est: int,
             place_id: str | None) -> QuestDraft:  # fmt: skip
    fill = {"name": name or ""}
    opener = rng.choice(_OPENERS[inp.persona])
    closer = rng.choice(_CLOSERS[inp.persona])
    briefing = f"{opener} {t.core.format(**fill)} {closer}"
    if len(briefing) > 360:
        briefing = t.core.format(**fill)
    method = t.method if place_id or t.method != "checkin" else "honor"
    return QuestDraft(
        title=t.title.format(**fill)[:60].strip(),
        category=t.category,
        briefing=briefing,
        objective=t.objective.format(**fill)[:140].strip(),
        place_id=place_id,
        est_minutes=est,
        verification=QuestVerification(
            method=method,
            photo_prompt=t.photo_prompt.format(**fill)[:100]
            if method == "photo" and t.photo_prompt
            else None,
        ),
        safety_note=t.safety_note or rng.choice(_SAFETY_NOTES),
        off_screen_tip=rng.choice(_OFF_SCREEN_TIPS),
    )  # fmt: skip


def _passes(q: QuestDraft, inp: FallbackInput, candidates: Sequence[Candidate]) -> bool:
    return validate_quest(q, inp.validation_context(), candidates).ok


def generate_fallback_quest(inp: FallbackInput) -> QuestDraft:
    rng = random.Random(inp.seed)
    order = _category_order(inp, rng)
    # Events first, then nearest. `merge_candidates` already ordered events ahead of places
    # on purpose, and sorting on distance alone threw that away, so a live happening could
    # never be chosen while the LLM was down - the feature vanished exactly when the
    # fallback mattered. Usability is still checked per candidate below, so an event that is
    # too far or too late simply loses to a place rather than blocking one.
    candidates = sorted(inp.candidates, key=lambda c: (c.happening is None, c.distance_m))

    # 1) Place-based quests, freshest category first, nearest place first.
    for category in order:
        templates = [
            t for t in PLACE_TEMPLATES if t.category == category and _template_fits(t, inp)
        ]
        rng.shuffle(templates)
        for t in templates:
            for c in candidates:
                if c.kind not in t.kinds:
                    continue
                est = max(5, _travel_minutes(c.distance_m) + t.activity_min)
                if not _place_usable(c, inp, est):
                    continue
                q = _compose(t, c.name, inp, rng, est, c.id)
                if _passes(q, inp, candidates):  # e.g. a place name tripping the lint
                    return q

    # 2) Anywhere quests: no place needed, so this is the path outside a seeded city (P24).
    for category in order:
        anywhere = [
            t
            for t in ANYWHERE_TEMPLATES
            if t.category == category
            and _template_fits(t, inp)
            and (t.indoor or not inp.indoor_only)
        ]
        rng.shuffle(anywhere)  # 40-odd templates now: without this the first one always won
        for t in anywhere:
            est = min(t.activity_min, inp.minutes_available)
            q = _compose(t, None, inp, rng, max(5, est), None)
            if _passes(q, inp, candidates):
                return q

    # 3) Last resort: always valid, always indoor-safe.
    return _compose(
        next(t for t in ANYWHERE_TEMPLATES if t.title == "Window Listening"),
        None, inp, rng, 10, None,
    )  # fmt: skip
