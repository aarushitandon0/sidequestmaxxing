"""Deterministic template quest engine (MASTERSPEC §7.5).

Used when the LLM is down, slow, or fails validation twice. Given the same inputs and seed it
returns the same quest, and every quest it returns passes V1-V11 (property-tested). It never
raises: if no candidate fits, it falls back to a place-less quest.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import CATEGORIES, Category, Mood, Persona, PlaceKind
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


@dataclass(frozen=True)
class Template:
    category: Category
    title: str  # {name} available
    objective: str  # {name}
    core: str  # one or two spoken sentences; {name}
    activity_min: int
    method: str  # "photo" | "checkin" | "honor"
    photo_prompt: str | None = None  # {name}
    kinds: tuple[PlaceKind, ...] = field(default_factory=tuple)


_OUTDOOR_GREEN: tuple[PlaceKind, ...] = ("park", "garden", "nature_reserve", "other")

PLACE_TEMPLATES: tuple[Template, ...] = (
    # Viewpoints
    Template("explorer", "The Lookout at {name}", "Walk to {name} and find the spot with the widest view.",
             "Your destination is {name}. Find the spot with the widest view and name three landmarks you can see.",
             15, "photo", "the view from {name}", ("viewpoint",)),
    Template("mindful", "Stillness at {name}", "Sit at {name} for five quiet minutes and count distant sounds.",
             "Head to {name}, sit somewhere comfortable, and spend five quiet minutes counting the distant sounds.",
             15, "checkin", None, ("viewpoint",)),
    # Green spaces
    Template("naturalist", "Leaf Hunt at {name}", "Find three different leaf shapes at {name}.",
             "Make your way to {name} and find three leaves with completely different shapes. Bonus points for a weird one.",
             20, "photo", "three different leaves side by side", _OUTDOOR_GREEN),
    Template("fitness", "Laps of {name}", "Walk two full laps of the main path at {name}.",
             "Get to {name} and walk two full laps of the main path at a pace that warms you up.",
             20, "checkin", None, _OUTDOOR_GREEN),
    Template("mindful", "Bench Time at {name}", "Sit on a bench at {name} and listen for three different bird calls.",
             "Find a bench at {name}, settle in, and listen until you can tell apart three different bird calls.",
             15, "checkin", None, _OUTDOOR_GREEN),
    Template("creative", "Colour Quest at {name}", "Find five different colours in nature at {name}.",
             "At {name}, look for five different natural colours: flowers, bark, moss, sky, anything.",
             15, "photo", "a colourful flower or leaf", _OUTDOOR_GREEN),
    # Water (always from the path)
    Template("naturalist", "Water Watch at {name}", "From the main path at {name}, spot two kinds of birds.",
             "Walk to {name}, stay on the main path, and spot two different kinds of birds.",
             20, "checkin", None, ("water",)),
    # Peaks
    Template("fitness", "Trail toward {name}", "Walk the marked trail toward {name} for ten minutes, then turn back.",
             "Follow the marked trail toward {name} for ten minutes, enjoy the view, then turn back the way you came.",
             25, "checkin", None, ("peak",)),
    # Heritage and art
    Template("explorer", "The Story of {name}", "Find {name} and read its plaque or inscription.",
             "Track down {name} and read its plaque or inscription. Remember one fact to tell someone later.",
             15, "photo", "a plaque or carved detail at {name}", ("heritage",)),
    Template("creative", "Sketch {name}", "Sketch one detail of {name} in under five minutes.",
             "Go to {name}, pick one small detail, and sketch it in under five minutes. Wobbly lines welcome.",
             15, "photo", "your sketch of a detail at {name}", ("heritage", "artwork")),
    Template("creative", "Poem for {name}", "Find {name} and write a three-line poem about it.",
             "Find {name}, look at it for a full minute, then write a three-line poem about what it makes you feel.",
             15, "photo", "the artwork {name}", ("artwork",)),
    # Markets and cafes
    Template("foodie", "New Taste at {name}", "Visit {name} and try one snack you have never had.",
             "Head to {name} and try one snack you have never had before. Rate it out of ten.",
             20, "photo", "your new snack at {name}", ("market",)),
    Template("social", "Fruit Run at {name}", "Bring a friend to {name} and pick the best-looking fruit together.",
             "Bring a friend or family member to {name} and pick out the best-looking fruit together.",
             20, "photo", "the fruit you picked at {name}", ("market",)),
    Template("foodie", "Mystery Order at {name}", "Order a drink you have never tried at {name}.",
             "Walk to {name} and order a drink you have never tried. Sip it slowly, no screen allowed.",
             20, "checkin", None, ("cafe",)),
    Template("social", "Story Swap at {name}", "Take a friend to {name} and swap one good story each.",
             "Invite a friend or family member to {name} and swap one good story each over a drink.",
             30, "checkin", None, ("cafe",)),
    # Indoor culture
    Template("explorer", "Oldest Thing at {name}", "Find the oldest object on display at {name}.",
             "Visit {name} and hunt for the oldest object on display. Remember what it is and how old.",
             30, "checkin", None, ("museum",)),
    Template("creative", "Gallery Eye at {name}", "Pick one exhibit at {name} and describe it in three words.",
             "Wander {name}, choose one exhibit that grabs you, and describe it in exactly three words.",
             25, "checkin", None, ("museum",)),
    Template("mindful", "Quiet Pages at {name}", "Read one page of a book about local history at {name}.",
             "Go to {name}, find a book about local history, and read one page somewhere quiet.",
             20, "checkin", None, ("library",)),
    Template("mindful", "Courtyard Calm at {name}", "Sit quietly in the courtyard at {name} for five minutes.",
             "Visit {name}, be respectful, and sit quietly in the courtyard for five minutes, just noticing.",
             15, "checkin", None, ("temple",)),
)  # fmt: skip

PLACELESS_TEMPLATES: tuple[Template, ...] = (
    Template("naturalist", "Street Botanist", "Find three different leaf shapes on your street.",
             "Step outside and find three leaves with different shapes within a short walk of your door.",
             15, "photo", "three different leaves side by side"),
    Template("explorer", "Door Detective", "Find the most interesting door within a ten-minute walk.",
             "Take a slow walk around your block and find the most interesting door you can.",
             20, "photo", "an interesting door"),
    Template("creative", "Sky Sketch", "Look up and sketch the shape of one cloud.",
             "Find a comfortable spot with a view of the sky and sketch the shape of one cloud in a few lines.",
             10, "photo", "your cloud sketch"),
    Template("mindful", "Window Listening", "Sit by a window for ten minutes and count different sounds.",
             "Sit by a window, close your eyes, and count how many different sounds you can hear in ten minutes.",
             10, "honor"),
    Template("fitness", "Block Loop", "Walk one brisk loop around your block.",
             "Lace up and walk one brisk loop around your block. Notice one thing you never saw before.",
             15, "honor"),
    Template("foodie", "Kitchen Experiment", "Make a snack using one ingredient you rarely use.",
             "Raid the kitchen and make a simple snack with one ingredient you rarely use. Taste test required.",
             20, "photo", "your homemade snack on a plate"),
    Template("social", "Postcard Mission", "Write a short note to a friend and deliver or post it.",
             "Write a short handwritten note to a friend or family member, then deliver it or drop it in a postbox.",
             20, "honor"),
)  # fmt: skip

INDOOR_PLACELESS: frozenset[str] = frozenset(
    {"Sky Sketch", "Window Listening", "Kitchen Experiment"}
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
            photo_prompt=t.photo_prompt.format(**fill)[:100] if method == "photo" and t.photo_prompt else None,
        ),
        safety_note=rng.choice(_SAFETY_NOTES),
        off_screen_tip=rng.choice(_OFF_SCREEN_TIPS),
    )  # fmt: skip


def _passes(q: QuestDraft, inp: FallbackInput, candidates: Sequence[Candidate]) -> bool:
    return validate_quest(q, inp.validation_context(), candidates).ok


def generate_fallback_quest(inp: FallbackInput) -> QuestDraft:
    rng = random.Random(inp.seed)
    order = _category_order(inp, rng)
    candidates = sorted(inp.candidates, key=lambda c: c.distance_m)

    # 1) Place-based quests, freshest category first, nearest place first.
    for category in order:
        templates = [t for t in PLACE_TEMPLATES if t.category == category]
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

    # 2) Place-less quests.
    for category in order:
        for t in [t for t in PLACELESS_TEMPLATES if t.category == category]:
            if inp.indoor_only and t.title not in INDOOR_PLACELESS:
                continue
            est = min(t.activity_min, inp.minutes_available)
            q = _compose(t, None, inp, rng, max(5, est), None)
            if _passes(q, inp, candidates):
                return q

    # 3) Last resort: always valid, always indoor-safe.
    return _compose(
        next(t for t in PLACELESS_TEMPLATES if t.title == "Window Listening"),
        None, inp, rng, 10, None,
    )  # fmt: skip
