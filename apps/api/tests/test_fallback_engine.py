"""Fallback engine: deterministic, always valid (V1-V11), sensible choices."""

import random

import pytest

from app.agents.fallback_engine import FallbackInput, generate_fallback_quest
from app.models.enums import CATEGORIES, MOODS, PERSONAS, PLACE_KINDS
from app.services.places_repo import Candidate
from app.validators import validate_quest
from tests.quest_factory import LIT_PARK, MUSEUM, PARK

NAMES = [
    "Banyan Park", "Old Fort Gate", "Corner Cafe", "City Museum", "Hill Viewpoint",
    "Cliff Garden", "Swimming Tank Park", "Drunken Tree Cafe", "www.cafe.com Cafe",
    "Riverside Walk", "Edge of Town Lake", "Market Square", "Ganesh Temple", "Lotus Library",
]  # fmt: skip


def random_input(rng: random.Random) -> FallbackInput:
    candidates = []
    for i in range(rng.randint(0, 8)):
        kind = rng.choice(PLACE_KINDS)
        indoor = kind in ("museum", "library", "cafe") or rng.random() < 0.1
        candidates.append(
            Candidate(
                id=f"node/{i}",
                name=rng.choice(NAMES),
                kind=kind,
                distance_m=rng.randint(30, 6000),
                indoor=indoor,
                needs_daylight=(not indoor) and rng.random() < 0.8,
                lat=18.5,
                lng=73.8,
            )
        )
    return FallbackInput(
        minutes_available=rng.randint(10, 180),
        persona=rng.choice(PERSONAS),
        mood=rng.choice(MOODS),
        candidates=candidates,
        recent_categories=rng.sample(CATEGORIES, rng.randint(0, 7)),
        indoor_only=rng.random() < 0.25,
        daylight_minutes_left=rng.choice([None, 0, 10, 45, 90, 300, 700]),
        seed=rng.randint(0, 10**9),
    )


def test_property_500_random_contexts_always_pass_v1_to_v11() -> None:
    rng = random.Random(20261007)
    sources = {"place": 0, "placeless": 0}
    for _ in range(500):
        inp = random_input(rng)
        q = generate_fallback_quest(inp)
        result = validate_quest(q, inp.validation_context(), inp.candidates)
        assert result.ok, (inp, q, result.failures)
        sources["place" if q.place_id else "placeless"] += 1
    # Both paths get exercised.
    assert sources["place"] > 50 and sources["placeless"] > 50


def test_deterministic_for_same_seed() -> None:
    inp = FallbackInput(minutes_available=60, candidates=[PARK, MUSEUM], daylight_minutes_left=300,
                        seed=42)  # fmt: skip
    assert generate_fallback_quest(inp) == generate_fallback_quest(inp)


def test_zero_candidates_gives_placeless_quest() -> None:
    q = generate_fallback_quest(FallbackInput(minutes_available=30, seed=1))
    assert q.place_id is None
    assert q.verification.method in ("photo", "honor")


def test_indoor_only_picks_indoor_place_or_placeless() -> None:
    for seed in range(30):
        inp = FallbackInput(minutes_available=120, candidates=[PARK, MUSEUM, LIT_PARK],
                            indoor_only=True, daylight_minutes_left=300, seed=seed)  # fmt: skip
        q = generate_fallback_quest(inp)
        assert q.place_id in (None, MUSEUM.id)


def test_dusk_avoids_daylight_places() -> None:
    for seed in range(30):
        inp = FallbackInput(minutes_available=120, candidates=[PARK], daylight_minutes_left=20,
                            seed=seed)  # fmt: skip
        assert generate_fallback_quest(inp).place_id is None


def test_storm_with_only_outdoor_candidates() -> None:
    inp = FallbackInput(minutes_available=60, candidates=[PARK, LIT_PARK], indoor_only=True,
                        daylight_minutes_left=300, seed=3)  # fmt: skip
    q = generate_fallback_quest(inp)
    assert q.place_id is None


def test_prefers_categories_not_done_recently() -> None:
    recent = [c for c in CATEGORIES if c != "explorer"]
    view = Candidate(id="node/v", name="Hill Viewpoint", kind="viewpoint", distance_m=300,
                     lat=18.5, lng=73.8)  # fmt: skip
    inp = FallbackInput(minutes_available=60, candidates=[view], recent_categories=recent,
                        daylight_minutes_left=300, seed=5)  # fmt: skip
    assert generate_fallback_quest(inp).category == "explorer"


def test_skips_place_whose_name_trips_the_lint() -> None:
    cliff = Candidate(id="node/c", name="Cliff Garden", kind="garden", distance_m=100, lat=18.5,
                      lng=73.8)  # fmt: skip
    for seed in range(20):
        inp = FallbackInput(minutes_available=60, candidates=[cliff], daylight_minutes_left=300,
                            seed=seed)  # fmt: skip
        q = generate_fallback_quest(inp)
        assert q.place_id is None
        assert "cliff" not in q.model_dump_json().lower()


def test_far_place_skipped_when_short_on_time() -> None:
    far = PARK.model_copy(update={"distance_m": 5000})  # ~133 min round trip
    inp = FallbackInput(minutes_available=30, candidates=[far], daylight_minutes_left=600, seed=1)
    assert generate_fallback_quest(inp).place_id is None


@pytest.mark.parametrize("persona", PERSONAS)
def test_persona_voice_changes_briefing(persona: str) -> None:
    inp = FallbackInput(minutes_available=60, candidates=[MUSEUM], persona=persona,  # type: ignore[arg-type]
                        daylight_minutes_left=300, seed=7)  # fmt: skip
    q = generate_fallback_quest(inp)
    from app.agents.fallback_engine import _OPENERS

    assert any(q.briefing.startswith(o) for o in _OPENERS[persona])  # type: ignore[index]
