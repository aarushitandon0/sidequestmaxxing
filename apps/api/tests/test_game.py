from datetime import date

import pytest

from app.services.game import (
    DAILY_XP_CAP,
    QUEST_XP_CAP,
    apply_daily_cap,
    category_level,
    current_streak,
    next_streak,
    overall_level,
    quest_xp,
    rarity_for,
    title_for,
    xp_preview,
)


@pytest.mark.parametrize(
    ("est", "distance", "expected"),
    [
        (30, 1500, "common"),   # both at the common bound
        (30, None, "common"),   # place-less counts as 0 m
        (31, 100, "rare"),      # one minute over
        (10, 1501, "rare"),     # one metre over
        (120, 6000, "rare"),    # both at the rare bound
        (121, 100, "legendary"),
        (60, 6001, "legendary"),
        (5, 0, "common"),
    ],
)  # fmt: skip
def test_rarity_thresholds(est: int, distance: int | None, expected: str) -> None:
    assert rarity_for(est, distance) == expected


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        # base = est*2
        (dict(est_minutes=30, rarity="common", method="photo"), 60),
        (dict(est_minutes=30, rarity="rare", method="photo"), 90),           # x1.5
        (dict(est_minutes=30, rarity="legendary", method="photo"), 180),     # x3
        (dict(est_minutes=30, rarity="common", method="checkin"), 48),       # x0.8
        (dict(est_minutes=30, rarity="common", method="honor"), 30),         # x0.5
        (dict(est_minutes=30, rarity="common", method="photo", within_radius=False), 30),
        (dict(est_minutes=30, rarity="common", method="photo", within_radius=True), 60),
        (dict(est_minutes=30, rarity="common", method="photo", screen_share=0.04), 72),   # x1.2
        (dict(est_minutes=30, rarity="common", method="photo", screen_share=0.10), 60),   # not < 0.10
        (dict(est_minutes=30, rarity="common", method="photo", streak_days=3), 66),       # x1.1
        (dict(est_minutes=30, rarity="common", method="photo", streak_days=2), 60),
        # all modifiers: 60 * 1.5 * 0.8 * 0.5 * 1.2 * 1.1 = 47.52 -> 48
        (dict(est_minutes=30, rarity="rare", method="checkin", within_radius=False,
              screen_share=0.0, streak_days=9), 48),
        # exact half rounds up: 5*2*0.5*... 25 min honor rare = 50*1.5*0.5 = 37.5 -> 38
        (dict(est_minutes=25, rarity="rare", method="honor"), 38),
        # 36*2*1.5*0.8*1.2 = 103.68 -> 104
        (dict(est_minutes=36, rarity="rare", method="checkin", screen_share=0.01), 104),
        # cap
        (dict(est_minutes=180, rarity="legendary", method="photo"), QUEST_XP_CAP),
        (dict(est_minutes=120, rarity="rare", method="photo", screen_share=0.0,
              streak_days=5), QUEST_XP_CAP),  # 360*1.2*1.1 = 475.2 -> 400
    ],
)  # fmt: skip
def test_quest_xp_table(kw: dict, expected: int) -> None:
    assert quest_xp(**kw) == expected


def test_xp_preview_has_no_bonuses() -> None:
    assert xp_preview(30, "common", "photo") == 60
    assert xp_preview(20, "common", "honor") == 20


@pytest.mark.parametrize(
    ("xp", "already", "expected"),
    [(100, 0, 100), (100, 750, 50), (100, 800, 0), (100, 900, 0), (DAILY_XP_CAP, 0, 800)],
)
def test_daily_cap(xp: int, already: int, expected: int) -> None:
    assert apply_daily_cap(xp, already) == expected


@pytest.mark.parametrize(
    ("xp", "level"), [(0, 0), (39, 0), (40, 1), (159, 1), (160, 2), (360, 3), (1000, 5)]
)
def test_category_level(xp: int, level: int) -> None:
    assert category_level(xp) == level


@pytest.mark.parametrize(("xp", "level"), [(0, 0), (119, 0), (120, 1), (480, 2), (1080, 3)])
def test_overall_level(xp: int, level: int) -> None:
    assert overall_level(xp) == level


def test_level_matches_float_formula_everywhere() -> None:
    import math

    for xp in range(0, 20000, 7):
        assert category_level(xp) == math.floor(math.sqrt(xp / 40))
        assert overall_level(xp) == math.floor(math.sqrt(xp / 120))


TODAY = date(2026, 10, 7)


@pytest.mark.parametrize(
    ("streak", "last", "expected"),
    [
        (0, None, 1),
        (4, date(2026, 10, 6), 5),   # yesterday → +1
        (4, TODAY, 4),               # second quest today → unchanged
        (0, TODAY, 1),
        (4, date(2026, 10, 5), 1),   # missed a day → reset
    ],
)  # fmt: skip
def test_next_streak(streak: int, last: date | None, expected: int) -> None:
    assert next_streak(streak, last, TODAY) == expected


def test_current_streak_expires_after_a_missed_day() -> None:
    assert current_streak(4, date(2026, 10, 6), TODAY) == 4
    assert current_streak(4, TODAY, TODAY) == 4
    assert current_streak(4, date(2026, 10, 5), TODAY) == 0
    assert current_streak(4, None, TODAY) == 0


def test_titles() -> None:
    assert title_for("naturalist", 3) == "Leaf Whisperer"  # MASTERSPEC §8 example
    assert title_for("explorer", 0) is None
    assert title_for("mindful", 99) == "Zen Oracle"
