"""Every template, through the real validators (P24).

This is the test that keeps CLAUDE.md invariant 1 honest while the template library grows: a
template that trips a safety rule fails here, and the fix is always the template, never the
validator. The curated list the player asked for went through this suite, which is how the
foraging and solo-overnight quests got dropped and five others got reworded.
"""

from datetime import UTC, datetime

import pytest

from app.agents.fallback_engine import FallbackInput, _compose, generate_fallback_quest
from app.agents.templates import ANYWHERE_TEMPLATES, PLACE_TEMPLATES, Template
from app.models.enums import CATEGORIES, PERSONAS
from app.services.places_repo import Candidate
from app.validators.core import ValidationContext, validate_quest
from app.validators.lint import banned_hits, contact_hits, people_hits

# A deliberately ordinary place name: nothing in it should trip the lint on its own.
PLACE_NAME = "Riverside Gardens"
NOON = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


def _candidate(kind: str) -> Candidate:
    return Candidate(
        id="node/1",
        name=PLACE_NAME,
        kind=kind,  # type: ignore[arg-type]
        distance_m=400,
        indoor=kind in {"museum", "library", "cafe"},
        needs_daylight=False,
        lat=18.52,
        lng=73.856,
    )


def _ctx() -> ValidationContext:
    """Generous context: we are testing the wording, not the time or weather gates."""
    return ValidationContext(
        minutes_available=180, indoor_only=False, daylight_minutes_left=600, now=NOON
    )


def _rng(seed: int = 7):
    import random

    return random.Random(seed)


def _input(**kw: object) -> FallbackInput:
    base: dict[str, object] = {"minutes_available": 180, "now": NOON}
    base.update(kw)
    return FallbackInput(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("template", ANYWHERE_TEMPLATES, ids=lambda t: t.title)
@pytest.mark.parametrize("persona", PERSONAS)
def test_anywhere_template_validates(template: Template, persona: str) -> None:
    inp = _input(persona=persona)
    quest = _compose(template, None, inp, _rng(), max(5, min(template.activity_min, 180)), None)
    result = validate_quest(quest, _ctx(), [])
    assert result.ok, f"{template.title} failed {result.failure_ids}"


@pytest.mark.parametrize("template", PLACE_TEMPLATES, ids=lambda t: t.title)
@pytest.mark.parametrize("persona", PERSONAS)
def test_place_template_validates(template: Template, persona: str) -> None:
    candidate = _candidate(template.kinds[0])
    inp = _input(persona=persona, candidates=[candidate])
    quest = _compose(
        template, candidate.name, inp, _rng(), max(5, template.activity_min + 10), candidate.id
    )
    result = validate_quest(quest, _ctx(), [candidate])
    assert result.ok, f"{template.title} failed {result.failure_ids}"


@pytest.mark.parametrize("template", (*ANYWHERE_TEMPLATES, *PLACE_TEMPLATES), ids=lambda t: t.title)
def test_template_source_text_is_clean(template: Template) -> None:
    """The raw template strings, before any persona wrapping, carry no banned content."""
    fields = [template.title, template.objective, template.core, template.safety_note or ""]
    if template.photo_prompt:
        fields.append(template.photo_prompt)
    blob = " ".join(f.format(name=PLACE_NAME) for f in fields)
    assert not banned_hits(blob), f"{template.title}: {banned_hits(blob)}"
    assert not contact_hits(blob), f"{template.title}: {contact_hits(blob)}"
    if template.photo_prompt:
        prompt = template.photo_prompt.format(name=PLACE_NAME)
        assert not people_hits(prompt), f"{template.title} photographs people: {prompt}"


@pytest.mark.parametrize("template", ANYWHERE_TEMPLATES, ids=lambda t: t.title)
def test_anywhere_templates_never_need_a_checkin(template: Template) -> None:
    """`place_id=None` forbids check-in verification, so these may only be photo or honor."""
    assert template.method in {"photo", "honor"}


@pytest.mark.parametrize("template", PLACE_TEMPLATES, ids=lambda t: t.title)
def test_place_templates_declare_kinds(template: Template) -> None:
    assert template.kinds, f"{template.title} would never match a candidate"


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_category_has_an_anywhere_quest(category: str) -> None:
    """The engine walks categories freshest-first; a gap would narrow it for no reason."""
    assert [t for t in ANYWHERE_TEMPLATES if t.category == category]


def test_short_slot_never_gets_a_long_quest() -> None:
    """A 15-minute slot must not be handed a 90-minute class with the time filed off."""
    for seed in range(60):
        quest = generate_fallback_quest(_input(minutes_available=15, seed=seed))
        assert quest.est_minutes <= 15


def test_hour_windowed_quests_only_appear_in_their_window() -> None:
    """Sunrise at 6 pm is a quest nobody can do."""
    windowed = {t.title for t in ANYWHERE_TEMPLATES if t.hours is not None}
    evening = datetime(2026, 10, 10, 18, 30, tzinfo=UTC)
    for seed in range(80):
        quest = generate_fallback_quest(_input(seed=seed, now=evening))
        if quest.title in {"Sunrise Watch", "Lunch For One", "One Stop Further"}:
            pytest.fail(f"{quest.title} offered at 18:30")
    assert windowed, "the hour window is dead code if nothing uses it"


def test_no_clock_means_no_hour_windowed_quest() -> None:
    """Without a clock the engine cannot check the window, so it must not guess."""
    for seed in range(80):
        quest = generate_fallback_quest(FallbackInput(minutes_available=180, seed=seed, now=None))
        hours = {t.title: t.hours for t in (*ANYWHERE_TEMPLATES, *PLACE_TEMPLATES)}
        assert hours.get(quest.title) is None, f"{quest.title} needs a clock"


def test_indoor_only_weather_stays_indoors() -> None:
    """Pouring rain with nothing nearby: the quest must be doable under a roof."""
    indoor_titles = {t.title for t in ANYWHERE_TEMPLATES if t.indoor}
    for seed in range(60):
        quest = generate_fallback_quest(_input(seed=seed, indoor_only=True))
        assert quest.title in indoor_titles, f"{quest.title} sent the player out in the rain"


def test_the_library_actually_gets_used() -> None:
    """Variety check: the engine must reach well beyond the original seven templates."""
    seen = {generate_fallback_quest(_input(seed=seed)).title for seed in range(200)}
    assert len(seen) >= 15, f"only {len(seen)} distinct quests: {sorted(seen)}"
