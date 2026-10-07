"""Quest Master (MASTERSPEC §7.3): ask the open-weight model for ONE quest, validate it.

Flow: call → validators V1-V12 → on failure one retry with the failure reasons appended →
on second failure (or any LLM error/timeout) the deterministic fallback engine (§7.5).
The model only writes creative fields; ids, rarity and XP are added later by the server.

`build_user_message` is also used by the training data generator, so serving and training
see byte-identical system prompts AND the same user-message format.
"""

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.fallback_engine import FallbackInput, generate_fallback_quest
from app.models.context import QuestContext
from app.models.enums import Category, Mood, Persona
from app.models.quest import QuestDraft, llm_json_schema
from app.observability import span
from app.prompts import quest_master_system
from app.services.embeddings import Embedder
from app.services.llm_client import LLMClient, LLMError, LLMResponse
from app.services.places_repo import Candidate
from app.validators.core import (
    ValidationContext,
    ValidationResult,
    quest_memory_text,
    validate_quest,
)

log = logging.getLogger("sqm.quest_master")

FALLBACK_MODEL = "fallback-engine@v1"
Source = Literal["llm", "fallback"]


@dataclass(frozen=True)
class QuestMasterInput:
    context: QuestContext
    persona: Persona
    mood: Mood
    interests: Sequence[str]
    minutes_available: int
    candidates: Sequence[Candidate]
    recent_categories: Sequence[Category] = ()
    recent_embeddings: Sequence[Sequence[float]] = ()
    seed: int = 0  # fallback engine variety

    def validation_context(self) -> ValidationContext:
        return ValidationContext(
            minutes_available=self.minutes_available,
            indoor_only=self.context.indoor_only,
            daylight_minutes_left=self.context.daylight_minutes_left,
        )


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class QuestMasterResult:
    quest: QuestDraft
    source: Source
    model: str
    latency_ms: int  # time spent waiting on the LLM (0 when it was never called)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    retries: int = 0
    validator_failures: list[str] = field(default_factory=list)  # ids, all attempts
    fallback_reason: str | None = None


class LLMUnavailableError(Exception):
    """Raised only when FALLBACK_ON_LLM_ERROR=false (debug/eval); production falls back."""


# --- prompt building ---------------------------------------------------------------------------


def context_payload(ctx: QuestContext) -> dict[str, Any]:
    return {
        "local_time": ctx.local_time.strftime("%H:%M"),
        "part_of_day": ctx.part_of_day,
        "weekday": ctx.weekday,
        "daylight_minutes_left": ctx.daylight_minutes_left,
        "weather": {
            "summary": ctx.weather.summary,
            "temp_c": ctx.weather.temp_c,
            "precip_prob": ctx.weather.precip_prob,
        },
        "indoor_only": ctx.indoor_only,
    }


def candidate_payload(c: Candidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "kind": c.kind,
        "distance_m": c.distance_m,
        "tags_summary": c.tags_summary,
        "indoor": c.indoor,
        "needs_daylight": c.needs_daylight,
    }


def build_user_message(inp: QuestMasterInput) -> str:
    """The §7.3 user message. Interests are already sanitized keywords (never raw text)."""
    payload = {
        "context": context_payload(inp.context),
        "persona": inp.persona,
        "mood": inp.mood,
        "interests": list(inp.interests),
        "minutes_available": inp.minutes_available,
        "recent_categories": list(inp.recent_categories),
        "candidates": [candidate_payload(c) for c in inp.candidates],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_messages(inp: QuestMasterInput) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": quest_master_system().text},
        {"role": "user", "content": build_user_message(inp)},
    ]


def retry_message(result: ValidationResult) -> str:
    reasons = "\n".join(f"- {f.id}: {f.reason}" for f in result.failures)
    return f"Your quest failed these checks:\n{reasons}\nWrite a corrected quest. Output JSON only."


# --- output parsing ----------------------------------------------------------------------------

_THINK = re.compile(r"<think>.*?</think>", flags=re.DOTALL)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def extract_json_text(content: str) -> str:
    """Tolerate reasoning blocks / code fences (unconstrained local models). V1 still decides."""
    text = _FENCE.sub("", _THINK.sub("", content).strip()).strip()
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        return text[start : end + 1] if 0 <= start < end else text


# --- orchestration -----------------------------------------------------------------------------


async def _validate(
    content: str, inp: QuestMasterInput, embedder: Embedder | None
) -> ValidationResult:
    with span("validators") as s:
        ctx = inp.validation_context()
        result = validate_quest(extract_json_text(content), ctx, inp.candidates)
        if result.ok and result.quest and embedder is not None and inp.recent_embeddings:
            place = next((c for c in inp.candidates if c.id == result.quest.place_id), None)
            text = quest_memory_text(result.quest, place.name if place else None)
            [vector] = await embedder.embed([text])
            result = validate_quest(
                result.quest, ctx, inp.candidates, inp.recent_embeddings, quest_embedding=vector
            )
        s.set_data("ok", result.ok)
        s.set_data("failures", result.failure_ids)
        return result


async def _call(client: LLMClient, messages: list[dict[str, str]], attempt: int) -> LLMResponse:
    with span("gen_ai.chat", name=f"chat {client.model}") as s:
        s.set_data("gen_ai.request.model", client.model)
        s.set_data("attempt", attempt)
        res = await client.chat(messages, llm_json_schema())
        s.set_data("gen_ai.response.model", res.model)
        s.set_data("gen_ai.usage.input_tokens", res.prompt_tokens)
        s.set_data("gen_ai.usage.output_tokens", res.completion_tokens)
        s.set_data("latency_ms", res.latency_ms)
        return res


@dataclass
class _Attempts:
    """What the LLM attempts cost, carried into whichever result we return."""

    model: str
    latency_ms: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    retries: int = 0
    validator_failures: list[str] = field(default_factory=list)

    def result(self, quest: QuestDraft, source: Source, reason: str | None) -> QuestMasterResult:
        return QuestMasterResult(
            quest=quest,
            source=source,
            model=FALLBACK_MODEL if source == "fallback" else self.model,
            latency_ms=self.latency_ms,
            token_usage=self.token_usage,
            retries=self.retries,
            validator_failures=self.validator_failures,
            fallback_reason=reason,
        )


def fallback_result(
    inp: QuestMasterInput, reason: str, attempts: _Attempts | None = None
) -> QuestMasterResult:
    with span("fallback") as s:
        s.set_data("reason", reason)
        quest = generate_fallback_quest(
            FallbackInput(
                minutes_available=inp.minutes_available,
                persona=inp.persona,
                mood=inp.mood,
                interests=tuple(inp.interests),
                candidates=tuple(inp.candidates),
                recent_categories=tuple(inp.recent_categories),
                indoor_only=inp.context.indoor_only,
                daylight_minutes_left=inp.context.daylight_minutes_left,
                seed=inp.seed,
            )
        )
    return (attempts or _Attempts(model=FALLBACK_MODEL)).result(quest, "fallback", reason)


async def run_quest_master(
    inp: QuestMasterInput,
    client: LLMClient | None,
    embedder: Embedder | None = None,
    *,
    fallback_on_error: bool = True,
) -> QuestMasterResult:
    """Never raises (unless fallback_on_error=False and the LLM transport fails)."""
    if client is None:
        return fallback_result(inp, "llm_not_configured")

    messages = build_messages(inp)
    attempts = _Attempts(model=client.model)
    for attempt in range(2):
        attempts.retries = attempt
        try:
            res = await _call(client, messages, attempt)
        except LLMError as exc:
            log.warning("llm call failed", extra={"kind": exc.kind, "attempt": attempt})
            if not fallback_on_error:
                raise LLMUnavailableError(exc.kind) from exc
            return fallback_result(inp, f"llm_{exc.kind}", attempts)

        attempts.model = res.model
        attempts.latency_ms += res.latency_ms
        attempts.token_usage.prompt_tokens += res.prompt_tokens or 0
        attempts.token_usage.completion_tokens += res.completion_tokens or 0
        result = await _validate(res.content, inp, embedder)
        if result.ok and result.quest is not None:
            return attempts.result(result.quest, "llm", None)

        attempts.validator_failures.extend(result.failure_ids)
        log.info("llm quest rejected", extra={"failures": result.failure_ids, "attempt": attempt})
        messages = [
            *messages,
            {"role": "assistant", "content": res.content},
            {"role": "user", "content": retry_message(result)},
        ]
    return fallback_result(inp, "validation_failed_twice", attempts)
