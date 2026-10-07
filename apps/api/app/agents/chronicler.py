"""Chronicler input format + deterministic fallback recap (MASTERSPEC §7.7).

The user-message builder is shared by training (make_recap_examples.py) and, later, the
/v1/recap/weekly endpoint (P18), so both see the same format. The fallback writes a plain,
always-valid chronicle from the facts alone when the model is unavailable.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from app.models.enums import Persona
from app.prompts import load_prompt
from app.validators.recap import RecapCompletion, RecapDraft, expected_stats, word_count

CHRONICLER_SYSTEM = "chronicler.system.txt"

CATEGORY_WORDS = {
    "explorer": "exploring", "naturalist": "noticing nature", "social": "sharing places",
    "foodie": "tasting the neighbourhood", "creative": "making things", "fitness": "moving",
    "mindful": "slowing down",
}  # fmt: skip
NEXT_THEME = {
    "explorer": "a week of quiet corners you have never noticed",
    "naturalist": "a week of looking up: trees, roofs and skies",
    "social": "a week of places worth showing a friend",
    "foodie": "a week of small local flavours",
    "creative": "a week of sketching what you see",
    "fitness": "a week of slightly longer walks",
    "mindful": "a week of five quiet minutes outside each day",
}


@dataclass(frozen=True)
class RecapInput:
    persona: Persona
    week: str  # e.g. "Oct 1 - Oct 7"
    completions: Sequence[RecapCompletion]


def build_recap_user_message(inp: RecapInput) -> str:
    payload = {
        "persona": inp.persona,
        "week": inp.week,
        "completions": [
            {"day": c.day, "title": c.title, "category": c.category, "place_name": c.place_name,
             "minutes_outside": c.minutes_outside}
            for c in inp.completions
        ],
    }  # fmt: skip
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_recap_messages(inp: RecapInput) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": load_prompt(CHRONICLER_SYSTEM).text},
        {"role": "user", "content": build_recap_user_message(inp)},
    ]


def fallback_recap(inp: RecapInput) -> RecapDraft:
    """Facts-only chronicle that always passes R1-R7 (requires ≥ 1 completion)."""
    stats = expected_stats(inp.completions)
    top = stats.top_category or "explorer"
    s = "" if stats.quests == 1 else "s"
    lines = [
        f"Here is your chronicle for {inp.week}.",
        f"You completed {stats.quests} side quest{s} and spent {stats.minutes} minutes outside,"
        " away from the screen.",
    ]
    for c in inp.completions:
        where = f" at {c.place_name}" if c.place_name else " right where you were"
        when = f"On {c.day}, you" if c.day else "You"
        lines.append(f"{when} took on {c.title}{where} and stayed out for {c.minutes_outside}"
                     " minutes.")  # fmt: skip
    lines.append(f"Most of your week was about {CATEGORY_WORDS[top]}, and it shows.")
    filler = [
        "Every quest started the same way: a short briefing, then the phone went back in your"
        " pocket.",
        "That is the whole trick of this game. The map is not the adventure, the walk is.",
        "Small steps add up. Each minute outside is a minute you chose the real world over a feed.",
        "Some quests were quick and some took longer, and both kinds count.",
        "You noticed things most people walk past without a second look.",
        "The neighbourhood did not change this week, but the way you move through it did.",
        "Keep the same rhythm: short, safe, curious trips in daylight, and tell someone where"
        " you are going.",
        "There is no leaderboard here, only the next corner you have not looked at yet.",
        "Rest days are part of the adventure too, so take them when you need them.",
        "Your skills grew a little with every quest, and they will keep growing.",
        "If a week feels busy, even ten minutes outside is a real quest.",
        "The best stories in this chronicle are the ones you lived, not the ones you scrolled.",
    ]
    ending = f"For next week, try a theme: {NEXT_THEME[top]}."
    i = 0
    while word_count(" ".join([*lines, ending])) < 185 and i < len(filler):
        lines.append(filler[i])
        i += 1
    while word_count(" ".join([*lines, ending])) > 255 and len(lines) > 3:
        lines.pop(2)  # very long weeks: drop per-quest lines, keep the totals
    return RecapDraft(text=" ".join([*lines, ending]), stats=stats)
