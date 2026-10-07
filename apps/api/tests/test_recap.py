"""Chronicler validators R1-R7 and the facts-only fallback recap (MASTERSPEC §7.7)."""

import json
import random

import pytest

from app.agents.chronicler import (
    RecapInput,
    build_recap_messages,
    build_recap_user_message,
    fallback_recap,
)
from app.models.enums import CATEGORIES, PERSONAS
from app.prompts import committed_hashes, load_prompt
from app.validators.recap import (
    RecapCompletion,
    expected_stats,
    place_mentions,
    validate_recap,
    word_count,
)

WEEK = [
    RecapCompletion("The Three-Bark Survey", "naturalist", "Kamala Garden", 35, "Monday"),
    RecapCompletion(
        "Keeper of Forgotten Things", "creative", "City Heritage Museum", 50, "Wednesday"
    ),
    RecapCompletion("Window of Opportunity", "mindful", None, 10, "Thursday"),
    RecapCompletion("Leaf Detective", "naturalist", "Lotus Park", 25, "Saturday"),
]


def recap(text: str, **stats: object) -> str:
    s = expected_stats(WEEK).model_dump()
    s.update(stats)
    return json.dumps({"text": text, "stats": s})


def words(n: int, base: str = "You walked to Kamala Garden and looked closely.") -> str:
    out = base.split()
    while len(out) < n:
        out.append("outside")
    return " ".join(out[:n])


def test_expected_stats() -> None:
    s = expected_stats(WEEK)
    assert (s.quests, s.minutes, s.top_category) == (4, 120, "naturalist")
    assert expected_stats([]).top_category is None


def test_valid_recap_passes() -> None:
    assert validate_recap(recap(words(200)), WEEK).ok


@pytest.mark.parametrize(
    ("raw", "rule"),
    [
        ("not json", "R1"),
        (json.dumps({"text": "x", "stats": {"quests": 1}}), "R1"),
        (recap(words(120)), "R2"),
        (recap(words(300)), "R2"),
        (recap(words(200), quests=9), "R3"),
        (recap(words(200), top_category="foodie"), "R3"),
        (recap(words(200, "You swim at Kamala Garden then relax.")), "R4"),
        (recap(words(200, "Visit https://example.com after Kamala Garden.")), "R5"),
        (recap(words(200, "You also found Shaniwar Wada and the Old Stone Bridge.")), "R6"),
        (recap(words(200, "Great week at Kamala Garden #outside")), "R7"),
    ],
)
def test_recap_failures(raw: str, rule: str) -> None:
    assert rule in validate_recap(raw, WEEK).failure_ids


def test_place_mentions_match_input_names_case_insensitively() -> None:
    text = "Then Lotus Park surprised you, and the City Heritage Museum too."
    assert place_mentions(text) == ["Then Lotus Park", "City Heritage Museum"]
    assert validate_recap(recap(words(200, text)), WEEK).failure_ids == []


def test_fallback_recap_always_valid() -> None:
    r = random.Random(3)
    for i in range(200):
        n = r.randint(1, 12)
        week = [
            RecapCompletion(f"Quest {j}", r.choice(CATEGORIES), r.choice([None, f"Banyan Park {j}"]),
                            r.randint(5, 120), r.choice(["Monday", "Friday", ""]))
            for j in range(n)
        ]  # fmt: skip
        inp = RecapInput(r.choice(PERSONAS), "Oct 1 – Oct 7", week)
        draft = fallback_recap(inp)
        res = validate_recap(draft.model_dump(), week)
        assert res.ok, (i, res.failures, word_count(draft.text))


def test_messages_use_the_hashed_chronicler_prompt() -> None:
    inp = RecapInput("chill", "Oct 1 – Oct 7", WEEK)
    msgs = build_recap_messages(inp)
    assert msgs[0]["content"] == load_prompt("chronicler.system.txt").text
    assert (
        load_prompt("chronicler.system.txt").sha256 == committed_hashes()["chronicler.system.txt"]
    )
    assert (
        json.loads(build_recap_user_message(inp))["completions"][0]["place_name"] == "Kamala Garden"
    )
