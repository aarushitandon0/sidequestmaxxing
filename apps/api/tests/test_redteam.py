"""Safety red-team (MASTERSPEC §14.1): ≥ 40 adversarial cases, 0 unsafe quests pass."""

import json
import re
import zlib
from pathlib import Path
from typing import Any

import pytest

from app.agents.fallback_engine import FallbackInput, generate_fallback_quest
from app.sanitize import _INJECTION_MARKERS, sanitize_interests
from app.services.places_repo import Candidate
from app.validators import ValidationContext, banned_hits, validate_quest
from tests.quest_factory import CANDIDATES

CASES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "redteam_cases.json").read_text(encoding="utf-8")
)["cases"]


def test_redteam_has_at_least_40_cases() -> None:
    assert len(CASES) >= 40
    assert len({c["id"] for c in CASES}) == len(CASES)


def _setup(case: dict[str, Any]) -> tuple[ValidationContext, list[Candidate]]:
    ctx = ValidationContext(
        minutes_available=case["request"]["minutes_available"],
        indoor_only=case["context"]["indoor_only"],
        daylight_minutes_left=case["context"]["daylight_minutes_left"],
    )
    extra = [Candidate.model_validate(c) for c in case["candidates"] or []]
    return ctx, [*CANDIDATES, *extra]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_adversarial_llm_output_is_rejected(case: dict[str, Any]) -> None:
    ctx, candidates = _setup(case)
    result = validate_quest(case["llm_output"], ctx, candidates)
    assert not result.ok, f"{case['id']} passed validators: {case['llm_output']}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_fallback_for_adversarial_context_is_safe(case: dict[str, Any]) -> None:
    ctx, candidates = _setup(case)
    interests = sanitize_interests(case["request"]["interests"])
    q = generate_fallback_quest(
        FallbackInput(
            minutes_available=ctx.minutes_available,
            mood=case["request"]["mood"],
            interests=interests,
            candidates=candidates,
            indoor_only=ctx.indoor_only,
            daylight_minutes_left=ctx.daylight_minutes_left,
            seed=zlib.crc32(case["id"].encode()),
        )
    )
    assert validate_quest(q, ctx, candidates).ok
    for text in (q.title, q.briefing, q.objective, q.safety_note, q.off_screen_tip):
        assert banned_hits(text) == []


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["id"].startswith("inj-")], ids=lambda c: c["id"]
)
def test_injection_interests_are_reduced_to_plain_keywords(case: dict[str, Any]) -> None:
    for clean in sanitize_interests(case["request"]["interests"]):
        assert re.fullmatch(r"[\w -]{1,24}", clean), clean
        assert not _INJECTION_MARKERS.search(clean)
