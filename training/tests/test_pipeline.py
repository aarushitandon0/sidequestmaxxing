"""Data pipeline (P14) end to end with the free backends: contexts → teacher → filter."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import filter as filt
import gen_teacher
import make_contexts
import make_recap_examples
import prompts_extra
import records
from common import read_jsonl

from app.prompts import load_prompt
from app.validators.core import validate_quest


def rows(path: Path) -> list[dict[str, Any]]:
    return list(read_jsonl(path))


def test_contexts_are_deterministic_and_area_split(ctx_dir: Path, tmp_path: Path) -> None:
    again = tmp_path / "again"
    make_contexts.main(["--synthetic", "--scale", "0.1", "--out", str(again)])
    for split in ("train", "val", "test"):
        assert (ctx_dir / f"{split}.jsonl").read_text(encoding="utf-8") == (
            again / f"{split}.jsonl"
        ).read_text(encoding="utf-8")
    areas = {s: {r["area"] for r in rows(ctx_dir / f"{s}.jsonl")} for s in ("train", "val", "test")}
    assert not areas["train"] & areas["test"]
    assert not areas["train"] & areas["val"]
    places = {
        s: {c["id"] for r in rows(ctx_dir / f"{s}.jsonl") for c in r["input"]["candidates"]}
        for s in ("train", "test")
    }
    assert not places["train"] & places["test"], "test places must be unseen in training"


def test_edge_case_mix(ctx_dir: Path) -> None:
    train = rows(ctx_dir / "train.jsonl")
    assert len(train) == 300
    empty = sum(not r["input"]["candidates"] for r in train) / len(train)
    indoor = sum(r["input"]["context"]["indoor_only"] for r in train) / len(train)
    assert 0.04 <= empty <= 0.13
    assert 0.05 <= indoor <= 0.16
    for r in train:  # candidates already pass the Scout's safety filter
        assert len(r["input"]["candidates"]) <= 8
        if r["input"]["context"]["indoor_only"]:
            assert all(c["indoor"] for c in r["input"]["candidates"])


def test_messages_use_production_prompt(ctx_dir: Path) -> None:
    rec = rows(ctx_dir / "train.jsonl")[0]
    sys_msg, user = records.messages(rec)
    assert sys_msg["content"] == load_prompt("quest_master.system.txt").text
    assert json.loads(user["content"])["persona"] == rec["input"]["persona"]


def test_fewshot_examples_pass_production_validators() -> None:
    for ex in prompts_extra.fewshot_examples():
        rec = {"input": ex["input"]}
        res = validate_quest(
            ex["output"], records.validation_context(rec), records.to_input(rec).candidates
        )
        assert res.ok, res.failures
    assert len(prompts_extra.fewshot_messages()) == 6


def test_paid_runs_are_gated(ctx_dir: Path, tmp_path: Path) -> None:
    args = ["--contexts", str(ctx_dir), "--out", str(tmp_path), "--all"]
    assert gen_teacher.main(args) == 2  # > 20 contexts on Tinker without approval
    assert gen_teacher.main([*args, "--i-approve-cost"]) == 2  # prices not filled in
    assert gen_teacher.main([*args, "--estimate"]) == 0


def test_filter_keeps_only_valid_balanced_rows(ctx_dir: Path, tmp_path: Path) -> None:
    teacher = tmp_path / "teacher"
    gen_teacher.main(
        [
            "--contexts",
            str(ctx_dir),
            "--out",
            str(teacher),
            "--backend",
            "fallback",
            "--limit",
            "300",
        ]
    )
    samples = rows(teacher / "train.fallback.jsonl")
    # Corrupt some samples the way a real teacher might fail.
    samples[0]["raw"] = "Sure! Here is your quest: {not json"
    samples[2]["raw"] = json.dumps({**json.loads(samples[2]["raw"]), "xp": 999})
    samples[4]["raw"] = json.dumps({**json.loads(samples[4]["raw"]), "place_id": "node/invented"})
    samples[6] = {"context_id": samples[6]["context_id"], "error": "TimeoutError"}
    bad = tmp_path / "bad.jsonl"
    bad.write_text("".join(json.dumps(s) + "\n" for s in samples))

    out = tmp_path / "sft"
    st = __import__("asyncio").run(
        filt.run(
            filt.argparse.Namespace(
                split="train",
                teacher=bad,
                contexts=ctx_dir,
                out=out,
                embedder="hash",
                max_per_context=1,
            )
        )
    )
    assert st["rejection_reasons"]["V1"] >= 2
    assert st["rejection_reasons"]["V2"] >= 1
    assert st["rejection_reasons"]["teacher_TimeoutError"] == 1
    kept = rows(out / "train.jsonl")
    assert kept and len(kept) == st["kept"]
    contexts = {r["id"]: r for r in rows(ctx_dir / "train.jsonl")}
    prod = load_prompt("quest_master.system.txt").text
    for row in kept:
        system, _user, assistant = row["messages"]
        assert system["content"] == prod
        rec = contexts[row["context_id"]]
        res = validate_quest(
            assistant["content"], records.validation_context(rec), records.to_input(rec).candidates
        )
        assert res.ok
    cats = Counter(r["meta"]["category"] for r in kept)
    before_cap = len(kept) + st["dropped"]["category_cap"] + st["dropped"]["persona_cap"]
    assert max(cats.values()) <= -(-1.6 * before_cap // 7)  # ceil: no category over its cap


def test_recap_examples(tmp_path: Path) -> None:
    assert make_recap_examples.main(["--synthetic", "--out", str(tmp_path)]) == 0
    train = rows(tmp_path / "train.jsonl")
    assert len(train) == 380
    assert train[0]["messages"][0]["content"] == load_prompt("chronicler.system.txt").text
