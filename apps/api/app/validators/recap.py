"""Chronicler (weekly recap) validators (MASTERSPEC §7.7). Pure functions.

Used as the training-data filter and by /v1/recap/weekly:
  R1 parses as {"text": str, "stats": {...}} · R2 180-260 words · R3 stats match the input
  R4 banned-term lint (V4 rules) · R5 no contact info / links · R6 named places come from the
  input (heuristic: Title-Case phrases ending in a place noun must match an input place name)
  R7 no emoji / hashtags.
"""

import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.enums import CATEGORIES, Category
from app.validators.lint import banned_hits, contact_hits

MIN_WORDS, MAX_WORDS = 180, 260
_EMOJI = re.compile("[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff]")
_HASHTAG = re.compile(r"(?:^|\s)#\w")
PLACE_NOUNS = (
    "Park|Garden|Gardens|Museum|Library|Temple|Market|Cafe|Café|Lake|Hill|Tekdi|Gate|Bridge|"
    "Fort|Square|Viewpoint|Reserve|Ghat|Chowk|Mandir|Peth|Wada|Hall|Gallery|Tower|Pond|River"
)
_APOS = "'\u2019"  # straight and curly apostrophes
_PLACE_LIKE = re.compile(rf"\b((?:[A-Z][\w{_APOS}.-]*\s+){{0,4}}(?:{PLACE_NOUNS}))\b")


class RecapStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quests: int = Field(ge=0)
    minutes: int = Field(ge=0)
    top_category: Category | None


class RecapDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2400)
    stats: RecapStats


@dataclass(frozen=True)
class RecapCompletion:
    title: str
    category: Category
    place_name: str | None
    minutes_outside: int
    day: str = ""


@dataclass
class RecapResult:
    recap: RecapDraft | None
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.recap is not None and not self.failures

    @property
    def failure_ids(self) -> list[str]:
        return sorted({f[0] for f in self.failures})


def expected_stats(completions: Sequence[RecapCompletion]) -> RecapStats:
    counts: Counter[Category] = Counter(c.category for c in completions)

    def rank(c: Category) -> tuple[int, int]:
        return counts[c], -CATEGORIES.index(c)

    top: Category | None = None
    if counts:
        best: Category = max(CATEGORIES, key=rank)
        top = best
    return RecapStats(
        quests=len(completions),
        minutes=sum(c.minutes_outside for c in completions),
        top_category=top,
    )


def word_count(text: str) -> int:
    return len(re.findall(rf"\b[\w{_APOS}-]+\b", text))


def place_mentions(text: str) -> list[str]:
    return [m.group(1).strip() for m in _PLACE_LIKE.finditer(text)]


def validate_recap(
    raw: str | dict[str, Any], completions: Sequence[RecapCompletion]
) -> RecapResult:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        recap = RecapDraft.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        return RecapResult(None, [("R1", type(exc).__name__)])
    fails: list[tuple[str, str]] = []
    n = word_count(recap.text)
    if not MIN_WORDS <= n <= MAX_WORDS:
        fails.append(("R2", f"{n} words (need {MIN_WORDS}-{MAX_WORDS})"))
    if recap.stats != expected_stats(completions):
        fails.append(("R3", "stats don't match the completions"))
    for hit in banned_hits(recap.text):
        fails.append(("R4", hit.rule))
    if contact_hits(recap.text):
        fails.append(("R5", "contact info or link"))
    known = [c.place_name.lower() for c in completions if c.place_name]
    known += [c.title.lower() for c in completions]
    for mention in place_mentions(recap.text):
        m = mention.lower()
        if not any(m in k or k.endswith(m) or m.endswith(k) for k in known):
            fails.append(("R6", f"unknown place: {mention}"))
    if _EMOJI.search(recap.text) or _HASHTAG.search(recap.text):
        fails.append(("R7", "emoji or hashtag"))
    return RecapResult(recap, fails)
