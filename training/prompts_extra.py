"""Teacher / baseline prompts (P14, P16). Production prompt stays in app.prompts.

- Teacher (data generation) and the eval BASELINE arm both use the long, detailed
  `teacher.quest_master.txt` plus the 3 examples in `quest_master.fewshot.txt`.
- The TUNED arm and serving use the short production prompt, zero-shot.
All three files are hashed in prompts/HASHES.txt.
"""

import json
from typing import Any

import common  # noqa: F401
from records import to_input

from app.agents.quest_master import build_user_message
from app.prompts import load_prompt

TEACHER_SYSTEM = "teacher.quest_master.txt"
FEWSHOT = "quest_master.fewshot.txt"


def fewshot_examples() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(load_prompt(FEWSHOT).text)
    return data


def fewshot_messages() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for ex in fewshot_examples():
        user = build_user_message(to_input({"input": ex["input"]}))
        out += [
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)},
        ]
    return out


def teacher_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    """Long instructions + 3 worked examples + the production-format user message."""
    return [
        {"role": "system", "content": load_prompt(TEACHER_SYSTEM).text},
        *fewshot_messages(),
        {"role": "user", "content": build_user_message(to_input(record))},
    ]
