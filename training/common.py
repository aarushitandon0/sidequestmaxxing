"""Shared helpers for the training pipeline (MASTERSPEC §10).

Every script here imports production code from apps/api (validators, prompt builders,
schemas) so training, serving and evaluation can never drift apart.
"""

import hashlib
import json
import os
import random
import subprocess
import sys
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
API_DIR = REPO / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

TRAINING = REPO / "training"
DATA = TRAINING / "data"  # gitignored: generated datasets
# committed: run metadata, stats, RUNS.md (tests point SQM_RUNS_DIR at a temp dir)
RUNS = Path(os.environ.get("SQM_RUNS_DIR", TRAINING / "runs"))
EVALS = REPO / "evals"

SPLITS = ("train", "val", "test")


def rng(seed: int, *salt: object) -> random.Random:
    """Independent, reproducible stream per (seed, salt...)."""
    key = "|".join(str(s) for s in (seed, *salt)).encode()
    seed_int = int.from_bytes(hashlib.sha256(key).digest()[:8], "big")
    return random.Random(seed_int)  # noqa: S311 — reproducible data, not crypto


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            n += 1
    return n


def load_config(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def git_rev() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 — git from PATH
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def save_run_metadata(name: str, payload: dict[str, Any]) -> Path:
    """training/runs/<name>.json — config, seeds, git rev, counts. Never secrets."""
    RUNS.mkdir(parents=True, exist_ok=True)
    path = RUNS / f"{name}.json"
    body = {"git_rev": git_rev(), "written_at": datetime.now(UTC).isoformat(), **payload}
    path.write_text(
        json.dumps(body, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return path


def append_runs_md(line: str) -> None:
    """Append one row/paragraph to training/runs/RUNS.md (the post's training log)."""
    RUNS.mkdir(parents=True, exist_ok=True)
    path = RUNS / "RUNS.md"
    if not path.exists():
        path.write_text(
            "# Training runs\n\nWritten by the training scripts — do not hand-edit numbers.\n\n",
            encoding="utf-8",
        )
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")
