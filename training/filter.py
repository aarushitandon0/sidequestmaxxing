"""Filter teacher samples with the PRODUCTION validators, dedupe, balance (MASTERSPEC §10.3).

  python training/filter.py --split train --teacher data/teacher/train.tinker.jsonl
  python training/filter.py --split train --teacher … --embedder hash      # dry run, no model

Keeps samples passing V1-V11 (V12 needs a player's history, so it doesn't apply), drops
near-duplicates (cosine > 0.92 within the same persona), caps over-represented categories
and personas, and writes SFT rows in the exact production chat format:
  [system = prompts/quest_master.system.txt, user = production JSON, assistant = quest JSON]
Stats (counts per persona/category/rarity, rejection reasons) → training/runs/.
"""

import argparse
import asyncio
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from common import DATA, load_config, read_jsonl, rng, save_run_metadata, utc_stamp, write_jsonl
from embed import make_embedder
from records import messages, to_input, validation_context

from app.agents.quest_master import extract_json_text
from app.models.quest import QuestDraft
from app.services.embeddings import cosine
from app.services.game import rarity_for
from app.validators.core import quest_memory_text, validate_quest

CONFIG = Path(__file__).parent / "configs" / "data.json"
CATEGORY_CAP = 1.6  # max share = CAP x (1 / 7)
PERSONA_CAP = 1.3  # max share = CAP x (1 / 4)


def canonical(q: QuestDraft) -> str:
    """Assistant target: compact JSON in schema field order (what grammar decoding emits)."""
    return json.dumps(q.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def check(sample: dict[str, Any], record: dict[str, Any]) -> tuple[QuestDraft | None, list[str]]:
    if "error" in sample:
        return None, [f"teacher_{sample['error']}"]
    inp = to_input(record)
    res = validate_quest(
        extract_json_text(sample["raw"]), validation_context(record), inp.candidates
    )
    return (res.quest, []) if res.ok else (None, res.failure_ids)


def distance_of(q: QuestDraft, record: dict[str, Any]) -> int | None:
    for c in record["input"]["candidates"]:
        if c["id"] == q.place_id:
            return int(c["distance_m"])
    return None


def cap_shares(
    rows: list[dict[str, Any]], key: str, cap: float, k: int, seed: int
) -> tuple[list[dict[str, Any]], int]:
    if not rows:
        return rows, 0
    limit = math.ceil(cap * len(rows) / k)
    order = sorted(rows, key=lambda r: rng(seed, "balance", key, r["id"]).random())
    seen: Counter[str] = Counter()
    kept = []
    for r in order:
        if seen[r["meta"][key]] < limit:
            kept.append(r)
            seen[r["meta"][key]] += 1
    kept.sort(key=lambda r: r["id"])
    return kept, len(rows) - len(kept)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_config(CONFIG)
    contexts = {r["id"]: r for r in read_jsonl(args.contexts / f"{args.split}.jsonl")}
    samples = list(read_jsonl(args.teacher))
    reasons: Counter[str] = Counter()
    passed: list[tuple[dict[str, Any], QuestDraft, dict[str, Any]]] = []
    for s in samples:
        record = contexts.get(s["context_id"])
        if record is None:
            reasons["unknown_context"] += 1
            continue
        quest, fails = check(s, record)
        if quest is None:
            reasons.update(fails)
            continue
        passed.append((s, quest, record))

    embedder, embedder_name = make_embedder(args.embedder)
    texts = [quest_memory_text(q, None) for _, q, _ in passed]
    vectors = await embedder.embed(texts) if texts else []

    kept: list[dict[str, Any]] = []
    kept_vecs: dict[str, list[list[float]]] = defaultdict(list)
    per_context: Counter[str] = Counter()
    dup = over_context = 0
    for (s, q, record), vec in zip(passed, vectors, strict=True):
        persona = record["input"]["persona"]
        if per_context[record["id"]] >= args.max_per_context:
            over_context += 1
            continue
        if any(cosine(vec, v) > cfg["dedupe_cosine"] for v in kept_vecs[persona]):
            dup += 1
            continue
        kept_vecs[persona].append(vec)
        per_context[record["id"]] += 1
        msgs = messages(record)
        kept.append({
            "id": f"{record['id']}-s{s.get('sample', 0)}",
            "context_id": record["id"],
            "messages": [*msgs, {"role": "assistant", "content": canonical(q)}],
            "meta": {"persona": persona, "category": q.category,
                     "rarity": rarity_for(q.est_minutes, distance_of(q, record)),
                     "placeless": q.place_id is None, "method": q.verification.method,
                     "indoor_only": record["input"]["context"]["indoor_only"]},
        })  # fmt: skip

    seed = cfg["seed"]
    kept, cat_drop = cap_shares(kept, "category", CATEGORY_CAP, 7, seed)
    kept, per_drop = cap_shares(kept, "persona", PERSONA_CAP, 4, seed)
    out = args.out / f"{args.split}.jsonl"
    write_jsonl(out, kept)

    def count(key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(r["meta"][key]) for r in kept).items()))

    return {
        "split": args.split, "teacher_file": str(args.teacher), "embedder": embedder_name,
        "samples": len(samples), "passed_validators": len(passed), "kept": len(kept),
        "pass_rate": round(len(passed) / len(samples), 3) if samples else 0.0,
        "dropped": {"duplicate": dup, "extra_per_context": over_context,
                    "category_cap": cat_drop, "persona_cap": per_drop},
        "rejection_reasons": dict(reasons.most_common()),
        "by_persona": count("persona"), "by_category": count("category"),
        "by_rarity": count("rarity"), "by_method": count("method"),
        "placeless": sum(r["meta"]["placeless"] for r in kept), "out": str(out),
    }  # fmt: skip


def print_stats(st: dict[str, Any]) -> None:
    print(f"\n## Filter stats — {st['split']} ({st['embedder']})")
    print(f"samples {st['samples']} → passed V1-V11 {st['passed_validators']} "
          f"({st['pass_rate']:.1%}) → kept {st['kept']}")  # fmt: skip
    for section in (
        "dropped",
        "rejection_reasons",
        "by_persona",
        "by_category",
        "by_rarity",
        "by_method",
    ):
        print(f"\n| {section} | n |\n|---|---|")
        for k, v in st[section].items():
            print(f"| {k} | {v} |")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--split", default="train", choices=["train", "val"])
    ap.add_argument("--teacher", type=Path, required=True, help="gen_teacher.py output")
    ap.add_argument("--contexts", type=Path, default=DATA / "contexts")
    ap.add_argument("--out", type=Path, default=DATA / "sft")
    ap.add_argument("--embedder", choices=["bge", "hash"], default="bge")
    ap.add_argument("--max-per-context", type=int, default=1)
    args = ap.parse_args(argv)
    stats = asyncio.run(run(args))
    print_stats(stats)
    save_run_metadata(f"filter_{args.split}_{utc_stamp()}", {"stage": "filter", **stats})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
