"""Chronicler input format + deterministic fallback recap (MASTERSPEC §7.7).

The user-message builder is shared by training (make_recap_examples.py) and the
/v1/recap/weekly endpoint, so both see the same format. `run_chronicler` mirrors the Quest
Master: call → validators R1-R7 → one retry with the failure reasons → deterministic
facts-only fallback on a second failure or any LLM error. Never raises.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.quest_master import extract_json_text
from app.models.enums import CATEGORIES, Persona
from app.observability import span
from app.prompts import load_prompt
from app.services.llm_client import LLMClient, LLMError
from app.validators.recap import (
    MAX_WORDS,
    MIN_WORDS,
    RecapCompletion,
    RecapDraft,
    RecapResult,
    expected_stats,
    validate_recap,
    word_count,
)

log = logging.getLogger("sqm.chronicler")

FALLBACK_MODEL = "recap-template@v1"
RECAP_MAX_TOKENS = 700  # 260 words ≈ 350 tokens + JSON; the quest cap (380) would truncate
RecapSource = Literal["llm", "fallback"]

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


# --- LLM path (P18) ----------------------------------------------------------------------------


def recap_json_schema() -> dict[str, Any]:
    """Grammar for llama.cpp `response_format`; R1-R7 still decide."""
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "stats": {
                "type": "object",
                "properties": {
                    "quests": {"type": "integer", "minimum": 0},
                    "minutes": {"type": "integer", "minimum": 0},
                    "top_category": {"enum": [*CATEGORIES, None]},
                },
                "required": ["quests", "minutes", "top_category"],
                "additionalProperties": False,
            },
        },
        "required": ["text", "stats"],
        "additionalProperties": False,
    }


@dataclass
class ChroniclerResult:
    recap: RecapDraft
    source: RecapSource
    model: str
    retries: int = 0
    validator_failures: list[str] = field(default_factory=list)
    fallback_reason: str | None = None


def recap_retry_message(result: RecapResult) -> str:
    reasons = "; ".join(f"{fid}: {detail}" for fid, detail in result.failures)
    return (
        f"That chronicle broke the rules ({reasons}). Write it again as JSON only: "
        f"{MIN_WORDS}-{MAX_WORDS} words, only places from COMPLETIONS, exact stats."
    )


def _fallback(inp: RecapInput, reason: str) -> ChroniclerResult:
    with span("fallback", reason=reason):
        return ChroniclerResult(fallback_recap(inp), "fallback", FALLBACK_MODEL,
                                fallback_reason=reason)  # fmt: skip


async def run_chronicler(inp: RecapInput, client: LLMClient | None) -> ChroniclerResult:
    """Never raises. Requires ≥ 1 completion (the endpoint handles empty weeks)."""
    if client is None:
        return _fallback(inp, "llm_not_configured")
    messages = build_recap_messages(inp)
    failures: list[str] = []
    for attempt in range(2):
        try:
            with span("gen_ai.chat", name=f"chat {client.model}") as s:
                s.set_data("gen_ai.request.model", client.model)
                s.set_data("attempt", attempt)
                res = await client.chat(
                    messages, recap_json_schema(), max_tokens=RECAP_MAX_TOKENS, schema_name="recap"
                )
                s.set_data("gen_ai.usage.input_tokens", res.prompt_tokens)
                s.set_data("gen_ai.usage.output_tokens", res.completion_tokens)
        except LLMError as exc:
            log.warning("recap llm call failed", extra={"kind": exc.kind, "attempt": attempt})
            out = _fallback(inp, f"llm_{exc.kind}")
            out.retries, out.validator_failures = attempt, failures
            return out
        with span("validators") as s:
            result = validate_recap(extract_json_text(res.content), inp.completions)
            s.set_data("ok", result.ok)
            s.set_data("failures", result.failure_ids)
        if result.ok and result.recap is not None:
            return ChroniclerResult(result.recap, "llm", res.model, attempt, failures)
        failures.extend(result.failure_ids)
        log.info("llm recap rejected", extra={"failures": result.failure_ids, "attempt": attempt})
        messages = [
            *messages,
            {"role": "assistant", "content": res.content},
            {"role": "user", "content": recap_retry_message(result)},
        ]
    out = _fallback(inp, "validation_failed_twice")
    out.retries, out.validator_failures = 1, failures
    return out
