"""Chronicler (weekly recap) SFT examples (MASTERSPEC §10.3 step 4, §7.7).

  python training/make_recap_examples.py --backend fallback          # free, deterministic
  python training/make_recap_examples.py --backend tinker --limit 20 # teacher dry run
  python training/make_recap_examples.py --backend tinker --all --i-approve-cost

Synthetic week logs are built from the same places export as the quest contexts (train-area
places for train, val-area places for val). Every recap is filtered with the production recap
validators R1-R7 and saved in the production chat format (prompts/chronicler.system.txt).
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from common import DATA, load_config, read_jsonl, rng, save_run_metadata, utc_stamp, write_jsonl
from make_contexts import synthetic_places

from app.agents.chronicler import RecapInput, build_recap_messages, fallback_recap
from app.agents.quest_master import extract_json_text
from app.models.enums import CATEGORIES, PERSONAS
from app.validators.recap import RecapCompletion, validate_recap

CONFIG = Path(__file__).parent / "configs" / "data.json"
TEACHER = Path(__file__).parent / "configs" / "teacher.json"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TITLE_WORDS = {
    "explorer": ["Hidden Corner Hunt", "The Long Way Round", "Map Edge Mystery"],
    "naturalist": ["Three-Bark Survey", "Bird Roll Call", "Leaf Detective"],
    "social": ["Bench With a View", "Friend Route", "Shared Spot Scout"],
    "foodie": ["Snack Cartographer", "Chai Stop Quest", "Market Taste Trail"],
    "creative": ["Five-Minute Sketch", "Shape Collector", "Keeper of Forgotten Things"],
    "fitness": ["Loop of Legends", "Stairway Challenge", "Brisk Circuit"],
    "mindful": ["Quiet Minutes", "Sky Watch", "Sound Map"],
}
WEEKS = ["Mar 2 - Mar 8", "Apr 6 - Apr 12", "Jun 1 - Jun 7", "Aug 10 - Aug 16", "Oct 1 - Oct 7"]


def week_log(r: Any, places: list[dict[str, Any]]) -> RecapInput:
    n = r.choices(range(1, 9), weights=[10, 14, 16, 16, 14, 12, 10, 8])[0]
    days = sorted(r.sample(range(7), min(n, 7))) + [r.randrange(7) for _ in range(max(0, n - 7))]
    comps = []
    for d in sorted(days):
        cat = r.choice(CATEGORIES)
        place = r.choice(places) if r.random() > 0.12 else None
        comps.append(RecapCompletion(
            title=r.choice(TITLE_WORDS[cat]), category=cat,
            place_name=place["name"] if place else None,
            minutes_outside=r.randint(8, 95), day=DAYS[d],
        ))  # fmt: skip
    return RecapInput(persona=r.choice(PERSONAS), week=r.choice(WEEKS), completions=comps)


def as_record(i: int, split: str, inp: RecapInput) -> dict[str, Any]:
    return {"id": f"recap-{split}-{i:04d}", "persona": inp.persona, "week": inp.week,
            "completions": [c.__dict__ for c in inp.completions]}  # fmt: skip


def from_record(rec: dict[str, Any]) -> RecapInput:
    return RecapInput(
        rec["persona"], rec["week"], [RecapCompletion(**c) for c in rec["completions"]]
    )


async def teacher_texts(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> list[str | None]:
    from tinker_backend import SampleSettings, TinkerChat

    chat = TinkerChat(cfg["model_name"])
    s = SampleSettings(temperature=0.8, top_p=0.95, max_tokens=700)
    sem = asyncio.Semaphore(cfg["concurrency"])

    async def one(rec: dict[str, Any]) -> str | None:
        async with sem:
            try:
                return str(
                    (await chat.chat(build_recap_messages(from_record(rec)), 1, s))[0]["text"]
                )
            except Exception:
                return None

    return list(await asyncio.gather(*(one(r) for r in rows)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--places", type=Path, default=DATA / "places.jsonl")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--out", type=Path, default=DATA / "sft_recap")
    ap.add_argument("--backend", choices=["fallback", "tinker"], default="fallback")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--i-approve-cost", action="store_true")
    args = ap.parse_args(argv)

    cfg, tcfg = load_config(CONFIG), load_config(TEACHER)
    seed = cfg["seed"]
    if args.synthetic or not args.places.exists():
        if not args.synthetic:
            print(f"{args.places} not found — run training/dump_places.py or pass --synthetic.",
                  file=sys.stderr)  # fmt: skip
            return 2
        places = synthetic_places(seed)
    else:
        places = list(read_jsonl(args.places))

    stats: dict[str, Any] = {"backend": args.backend}
    for split, n in cfg["recap"].items():
        r = rng(seed, "recap", split)
        rows = [as_record(i, split, week_log(r, places)) for i in range(n)]
        if not args.all and args.backend == "tinker":
            rows = rows[: args.limit]
        if args.backend == "tinker" and len(rows) > 20 and not args.i_approve_cost:
            print("Refusing a paid run over 20 recaps without --i-approve-cost.", file=sys.stderr)
            return 2
        if args.backend == "tinker":
            texts = asyncio.run(teacher_texts(rows, tcfg))
        else:
            texts = [json.dumps(fallback_recap(from_record(x)).model_dump()) for x in rows]
        kept, reasons = [], Counter[str]()
        for rec, raw in zip(rows, texts, strict=True):
            if raw is None:
                reasons["teacher_error"] += 1
                continue
            inp = from_record(rec)
            res = validate_recap(extract_json_text(raw), inp.completions)
            if not res.ok or res.recap is None:
                reasons.update(res.failure_ids)
                continue
            answer = json.dumps(
                res.recap.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
            )
            msgs = [*build_recap_messages(inp), {"role": "assistant", "content": answer}]
            meta = {"persona": inp.persona, "quests": len(inp.completions)}
            kept.append({"id": rec["id"], "task": "recap", "messages": msgs, "meta": meta})
        write_jsonl(args.out / f"{split}.jsonl", kept)
        stats[split] = {"generated": len(rows), "kept": len(kept), "rejections": dict(reasons)}
        print(f"{split}: {stats[split]}")
    save_run_metadata(
        f"recap_{args.backend}_{utc_stamp()}", {"stage": "make_recap_examples", **stats}
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
