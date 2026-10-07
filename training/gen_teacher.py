"""Generate target quests with an open-weight TEACHER via Tinker (MASTERSPEC §10.3 step 2).

  python training/gen_teacher.py --split train --limit 20 --estimate     # cost estimate only
  python training/gen_teacher.py --split train --limit 20                # dry run: 20 contexts
  python training/gen_teacher.py --split train --all --i-approve-cost    # full run (PAID)
  python training/gen_teacher.py --backend fallback --split train --limit 50   # no Tinker

The teacher sees the long instructions + 3 worked examples (prompts/teacher.*), but every
example is SAVED in the production chat format (short system prompt + production user
message) — that is what the student learns. Teacher identity/settings → training/runs/.
`--backend fallback` uses the deterministic fallback engine (pipeline tests; not for training).
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from common import (
    DATA,
    append_runs_md,
    load_config,
    read_jsonl,
    save_run_metadata,
    utc_stamp,
    write_jsonl,
)
from prompts_extra import teacher_messages
from records import fallback_input

from app.agents.fallback_engine import generate_fallback_quest
from app.prompts import committed_hashes

CONFIG = Path(__file__).parent / "configs" / "teacher.json"
DRY_RUN_LIMIT = 20


CHARS_PER_TOKEN = 3.5  # rough for English+JSON; the real count comes back from Tinker


def approx_prompt_tokens(rows: list[dict[str, Any]]) -> int:
    return round(
        sum(len(m["content"]) for r in rows for m in teacher_messages(r)) / CHARS_PER_TOKEN
    )


def estimate(cfg: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    k = cfg["samples_per_context"]
    n_contexts = len(rows)
    prefill = approx_prompt_tokens(rows)  # one prompt per context (its n samples share it)
    sample = n_contexts * k * cfg["est_completion_tokens"]
    price = cfg["price_per_mtok"]
    usd = None
    if isinstance(price.get("prefill"), int | float) and isinstance(
        price.get("sample"), int | float
    ):
        usd = round(prefill / 1e6 * price["prefill"] + sample / 1e6 * price["sample"], 2)
    return {
        "contexts": n_contexts,
        "samples": n_contexts * k,
        "prefill_tokens": prefill,
        "sample_tokens": sample,
        "usd_estimate": usd,
    }


async def run_tinker(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    from tinker_backend import SampleSettings, TinkerChat

    chat = TinkerChat(cfg["model_name"])
    settings = SampleSettings(cfg["temperature"], cfg["top_p"], cfg["max_tokens"])
    sem = asyncio.Semaphore(cfg["concurrency"])
    out: list[dict[str, Any]] = []

    async def one(row: dict[str, Any]) -> None:
        async with sem:
            try:
                samples = await chat.chat(
                    teacher_messages(row), cfg["samples_per_context"], settings
                )
            except Exception as exc:
                out.append({"context_id": row["id"], "error": type(exc).__name__})
                return
        for j, smp in enumerate(samples):
            out.append(
                {
                    "context_id": row["id"],
                    "sample": j,
                    "raw": smp["text"],
                    "prompt_tokens": smp["prompt_tokens"],
                    "completion_tokens": smp["completion_tokens"],
                }
            )

    await asyncio.gather(*(one(r) for r in rows))
    out.sort(key=lambda x: (x["context_id"], x.get("sample", -1)))
    print(f"renderer: {chat.renderer_name}")
    return out


def run_fallback(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        for j in range(cfg["samples_per_context"]):
            q = generate_fallback_quest(fallback_input(row, seed=j))
            raw = json.dumps(q.model_dump(mode="json"), ensure_ascii=False)
            out.append({"context_id": row["id"], "sample": j, "raw": raw})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--split", default="train", choices=["train", "val"])
    ap.add_argument("--contexts", type=Path, default=DATA / "contexts")
    ap.add_argument("--out", type=Path, default=DATA / "teacher")
    ap.add_argument("--limit", type=int, default=DRY_RUN_LIMIT)
    ap.add_argument("--all", action="store_true", help="every context in the split")
    ap.add_argument("--backend", choices=["tinker", "fallback"], default="tinker")
    ap.add_argument("--estimate", action="store_true", help="print the cost estimate and exit")
    ap.add_argument(
        "--i-approve-cost",
        action="store_true",
        help="required for more than 20 contexts on the paid backend",
    )
    args = ap.parse_args(argv)

    cfg = load_config(CONFIG)
    rows = list(read_jsonl(args.contexts / f"{args.split}.jsonl"))
    if not args.all:
        rows = rows[: args.limit]
    est = estimate(cfg, rows)
    print(f"teacher={cfg['model_name']} backend={args.backend} estimate={est}")
    if args.estimate:
        return 0
    if args.backend == "tinker" and len(rows) > DRY_RUN_LIMIT:
        if not args.i_approve_cost:
            print(
                f"Refusing a paid run over {DRY_RUN_LIMIT} contexts without --i-approve-cost.",
                file=sys.stderr,
            )
            return 2
        if est["usd_estimate"] is None:
            print(
                "Fill price_per_mtok in configs/teacher.json (from Tinker's pricing page) first.",
                file=sys.stderr,
            )
            return 2

    samples = (
        asyncio.run(run_tinker(rows, cfg)) if args.backend == "tinker" else run_fallback(rows, cfg)
    )
    path = args.out / f"{args.split}.{args.backend}.jsonl"
    write_jsonl(path, samples)
    errors = sum("error" in s for s in samples)
    print(f"wrote {len(samples)} samples ({errors} errors) → {path}")
    name = f"teacher_{args.split}_{args.backend}_{utc_stamp()}"
    meta = {
        "stage": "gen_teacher",
        "backend": args.backend,
        "split": args.split,
        "contexts": len(rows),
        "samples": len(samples),
        "errors": errors,
        "estimate": est,
        "teacher": {
            k: cfg[k]
            for k in (
                "model_name",
                "license",
                "temperature",
                "top_p",
                "max_tokens",
                "samples_per_context",
            )
        },
        "prompt_hashes": committed_hashes(),
    }
    save_run_metadata(name, meta)
    if args.backend == "tinker":
        append_runs_md(
            f"- `{name}`: teacher `{cfg['model_name']}` on {len(rows)} {args.split} "
            f"contexts → {len(samples)} samples, {errors} errors."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
