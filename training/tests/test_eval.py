"""Eval harness (P16) with the mock endpoint + mock judge: complete report, identity check."""

import csv
import json
from pathlib import Path

import pytest

import eval as harness


@pytest.fixture
def dry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(harness, "DRY_DIR", tmp_path / "dry")
    return tmp_path / "dry"


def run(ctx: Path, *argv: str) -> int:
    return harness.main(["--contexts", str(ctx), *argv])


def full_dry_run(ctx: Path) -> dict:
    for arm, label in (("baseline", "mock-base"), ("tuned", "mock-tuned")):
        assert run(ctx, "run", "--arm", arm, "--mock", "--label", label,
                   "--diversity-contexts", "3", "--diversity-samples", "4") == 0  # fmt: skip
    assert run(ctx, "report", "--mock-judge", "--embedder", "hash") == 0
    return json.loads((harness.DRY_DIR / "results.json").read_text(encoding="utf-8"))


def test_dry_run_writes_complete_report(ctx_dir: Path, dry: Path) -> None:
    res = full_dry_run(ctx_dir)
    assert res["dry_run"] is True
    labels = [m["label"] for m in res["metrics"]]
    for needed in ("JSON validity", "Full pass", "Full pass (with grammar, shipped)",
                   "Diversity (pairwise distance)", "Prompt tokens", "Latency p95 (grammar)"):  # fmt: skip
        assert needed in labels
    full = next(m for m in res["metrics"] if m["label"] == "Full pass")
    assert isinstance(full["baseline"], float) and isinstance(full["tuned"], float)
    # baseline uses the few-shot prompt → much longer prompts than tuned
    tok = next(m for m in res["metrics"] if m["label"] == "Prompt tokens")
    assert tok["baseline"] > 2 * tok["tuned"]
    md = (dry / "results.md").read_text(encoding="utf-8")
    assert "DRY RUN" in md and "5 worst" in md and "Judge bias" in md
    assert "{" not in md.split("## Voice")[0].replace('{"', "")  # no unformatted placeholders
    assert (dry / "human_pairs.csv").exists()


def test_reproducible(ctx_dir: Path, dry: Path) -> None:
    def quality(res: dict) -> list:  # wall-clock latency is the one thing a seed can't fix
        return [m for m in res["metrics"] if "Latency" not in m["label"]]

    assert quality(full_dry_run(ctx_dir)) == quality(full_dry_run(ctx_dir))


def test_refuses_on_identity_mismatch(
    ctx_dir: Path, dry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = harness.mock_transport
    monkeypatch.setattr(
        harness, "mock_transport", lambda _label, arm, seed: real("other-model", arm, seed)
    )
    with pytest.raises(SystemExit, match="refusing to run"):
        run(ctx_dir, "run", "--arm", "tuned", "--mock", "--label", "my-tuned")


def test_served_ids_accepts_paths() -> None:
    ids = harness.served_ids({"data": [{"id": "/data/models/quest.gguf"}]})
    assert harness.identity_matches("quest.gguf", ids)
    assert not harness.identity_matches("base.gguf", ids)


def test_judge_must_be_other_family(ctx_dir: Path, dry: Path) -> None:
    full_dry_run(ctx_dir)
    with pytest.raises(SystemExit, match="different model family"):
        harness.main(["--contexts", str(ctx_dir), "--out", str(dry), "report", "--raw", str(dry),
            "--embedder", "hash",
            "--judge-url", "http://judge", "--judge-model", "x", "--judge-family", "Qwen"])  # fmt: skip


def test_human_ratings_are_read_back(ctx_dir: Path, dry: Path) -> None:
    full_dry_run(ctx_dir)
    path = dry / "human_pairs.csv"
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and {"pair_id", "quest_A", "quest_B", "preferred"} <= set(rows[0])
    for r in rows:
        r["preferred"] = "A"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    assert run(ctx_dir, "report", "--mock-judge", "--embedder", "hash") == 0
    human = json.loads((dry / "results.json").read_text(encoding="utf-8"))["voice"]["human"]
    assert human["rated"] == len(rows) and human["tuned_win_rate"] is not None
