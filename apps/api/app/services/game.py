"""Game rules (MASTERSPEC §8). Pure functions; the server is the only authority for these.

Interpretation choices (DECISIONS D-34):
- XP bonuses are applied multiplicatively in spec order: x1.2 (screen share < 10%), then
  x1.1 (streak ≥ 3 days, counting the completion being scored). Then round half-up, cap 400.
- A place-less quest has distance 0 for rarity.
"""

import math
from datetime import date, timedelta
from fractions import Fraction
from typing import Final

from app.models.enums import Category, Rarity, VerificationMethod

XP_PER_MINUTE: Final = 2
# Exact fractions so half-up rounding is never off by float error (e.g. 86.4 vs 86.39999).
RARITY_MULTIPLIER: Final[dict[Rarity, Fraction]] = {
    "common": Fraction(1),
    "rare": Fraction(3, 2),
    "legendary": Fraction(3),
}
VERIFICATION_MULTIPLIER: Final[dict[VerificationMethod, Fraction]] = {
    "photo": Fraction(1),
    "checkin": Fraction(4, 5),
    "honor": Fraction(1, 2),
}
OUTSIDE_RADIUS_MULTIPLIER: Final = Fraction(1, 2)
LOW_SCREEN_SHARE: Final = 0.10
LOW_SCREEN_BONUS: Final = Fraction(6, 5)
STREAK_DAYS_FOR_BONUS: Final = 3
STREAK_BONUS: Final = Fraction(11, 10)
QUEST_XP_CAP: Final = 400
DAILY_XP_CAP: Final = 800

COMMON_MAX_MINUTES, COMMON_MAX_DISTANCE_M = 30, 1500
RARE_MAX_MINUTES, RARE_MAX_DISTANCE_M = 120, 6000


def rarity_for(est_minutes: int, distance_m: int | None) -> Rarity:
    distance = distance_m or 0
    if est_minutes <= COMMON_MAX_MINUTES and distance <= COMMON_MAX_DISTANCE_M:
        return "common"
    if est_minutes <= RARE_MAX_MINUTES and distance <= RARE_MAX_DISTANCE_M:
        return "rare"
    return "legendary"


def _round_half_up(x: Fraction) -> int:
    return math.floor(x + Fraction(1, 2))


def quest_xp(
    est_minutes: int,
    rarity: Rarity,
    method: VerificationMethod,
    *,
    within_radius: bool | None = None,
    screen_share: float | None = None,
    streak_days: int = 0,
) -> int:
    """XP for one quest. `within_radius=None` (no check-in) is not penalised."""
    xp = Fraction(est_minutes * XP_PER_MINUTE)
    xp *= RARITY_MULTIPLIER[rarity]
    xp *= VERIFICATION_MULTIPLIER[method]
    if within_radius is False:
        xp *= OUTSIDE_RADIUS_MULTIPLIER
    if screen_share is not None and screen_share < LOW_SCREEN_SHARE:
        xp *= LOW_SCREEN_BONUS
    if streak_days >= STREAK_DAYS_FOR_BONUS:
        xp *= STREAK_BONUS
    return min(QUEST_XP_CAP, _round_half_up(xp))


def xp_preview(est_minutes: int, rarity: Rarity, method: VerificationMethod) -> int:
    """What the quest card shows: base XP for the quest's own method, no bonuses/penalties."""
    return quest_xp(est_minutes, rarity, method)


def apply_daily_cap(xp: int, already_today: int) -> int:
    return max(0, min(xp, DAILY_XP_CAP - already_today))


def category_level(xp: int) -> int:
    return math.isqrt(max(0, xp) // 40)  # == floor(sqrt(xp / 40)) for integers


def overall_level(total_xp: int) -> int:
    return math.isqrt(max(0, total_xp) // 120)


def next_streak(streak_days: int, last_completed: date | None, today: date) -> int:
    """Consecutive local days with ≥ 1 completion, after completing a quest `today`."""
    if last_completed == today:
        return max(1, streak_days)
    if last_completed == today - timedelta(days=1):
        return streak_days + 1
    return 1


def current_streak(streak_days: int, last_completed: date | None, today: date) -> int:
    """Streak as displayed today: still alive if the last completion was today or yesterday."""
    if last_completed is not None and today - last_completed <= timedelta(days=1):
        return streak_days
    return 0


# Flavour titles per category and level (static table; level 0 = no title).
TITLES: Final[dict[Category, tuple[str, ...]]] = {
    "explorer": ("Wanderer", "Pathfinder", "Trailblazer", "Cartographer", "Legend of the Map"),
    "naturalist": ("Sprout", "Leaf Spotter", "Leaf Whisperer", "Grove Keeper", "Forest Sage"),
    "social": ("Friendly Face", "Story Swapper", "Town Crier", "Guild Host", "Heart of the Realm"),
    "foodie": ("Snack Scout", "Taste Seeker", "Market Hunter", "Flavour Knight", "Feast Master"),
    "creative": ("Doodler", "Sketcher", "Bard", "Muse", "Grand Artificer"),
    "fitness": ("Stroller", "Strider", "Trail Runner", "Iron Legs", "Peak Champion"),
    "mindful": ("Listener", "Calm Seeker", "Quiet Monk", "Stillwater", "Zen Oracle"),
}


def title_for(category: Category, level: int) -> str | None:
    if level <= 0:
        return None
    titles = TITLES[category]
    return titles[min(level, len(titles)) - 1]
