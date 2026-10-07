"""Prompt loader. `/prompts` is the single source of truth for API, web and training.

Prompts are read as raw bytes and sent verbatim; the SHA-256 of those bytes must match the
committed value in `prompts/HASHES.txt` (hash test), so training and serving can't drift.
Set PROMPTS_DIR to override the location (the Docker image uses /prompts).
"""

import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

QUEST_MASTER_SYSTEM = "quest_master.system.txt"
VERIFIER_GEMMA = "verifier.gemma.txt"
HASHES_FILE = "HASHES.txt"


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    sha256: str


def prompts_dir() -> Path:
    override = os.environ.get("PROMPTS_DIR")
    if override:
        return Path(override)
    # apps/api/app/prompts.py → repo root is three levels above `app/`.
    return Path(__file__).resolve().parents[3] / "prompts"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache
def load_prompt(name: str) -> Prompt:
    raw = (prompts_dir() / name).read_bytes()
    return Prompt(name=name, text=raw.decode("utf-8"), sha256=sha256_bytes(raw))


def committed_hashes() -> dict[str, str]:
    """Parse `HASHES.txt` (sha256sum format; '#' comments allowed)."""
    out: dict[str, str] = {}
    for line in (prompts_dir() / HASHES_FILE).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, filename = line.partition("  ")
        out[filename.strip()] = digest.strip()
    return out


def quest_master_system() -> Prompt:
    return load_prompt(QUEST_MASTER_SYSTEM)
