from pathlib import Path

import pytest

from app.prompts import (
    QUEST_MASTER_SYSTEM,
    VERIFIER_GEMMA,
    committed_hashes,
    load_prompt,
    prompts_dir,
    sha256_bytes,
)

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("name", [QUEST_MASTER_SYSTEM, VERIFIER_GEMMA])
def test_prompt_hash_matches_committed(name: str) -> None:
    """Training and serving must use byte-identical prompts (CLAUDE.md invariant 4)."""
    prompt = load_prompt(name)
    assert prompt.sha256 == committed_hashes()[name]
    assert prompt.sha256 == sha256_bytes((prompts_dir() / name).read_bytes())


def test_every_prompt_file_is_hashed() -> None:
    files = {p.name for p in prompts_dir().glob("*.txt")} - {"HASHES.txt"}
    assert files == set(committed_hashes())


def test_quest_master_prompt_matches_masterspec() -> None:
    """The prompt file is the §7.3 block verbatim."""
    spec = (REPO / "MASTERSPEC.md").read_text(encoding="utf-8")
    marker = spec.index("**System prompt** (file: `prompts/quest_master.system.txt`")
    start = spec.index("```\n", marker) + 4
    end = spec.index("\n```", start)
    assert load_prompt(QUEST_MASTER_SYSTEM).text == spec[start:end] + "\n"


def test_verifier_prompt_has_placeholder() -> None:
    assert '"{photo_prompt}"' in load_prompt(VERIFIER_GEMMA).text


def test_prompts_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    assert prompts_dir() == tmp_path


def test_prompts_have_lf_line_endings() -> None:
    for name in (QUEST_MASTER_SYSTEM, VERIFIER_GEMMA):
        assert b"\r" not in (prompts_dir() / name).read_bytes()
