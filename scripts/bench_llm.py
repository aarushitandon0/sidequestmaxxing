"""Gate G1 benchmark: latency and throughput of the Quest Master model on the real server.

Sends N synthetic contexts SEQUENTIALLY (the server runs `-np 1`) with the exact production
system prompt, user-message format, sampling params and JSON-schema constraint. Reports
p50/p95 end-to-end latency, tokens/s and validator pass rate, and writes a JSON report to
evals/ (numbers in docs must come from these files — never hand-typed).

Usage (from the repo root, API venv active):
  python scripts/bench_llm.py --base-url http://localhost:8080 --n 20
  python scripts/bench_llm.py --n 30          # uses LLM_BASE_URL / LLM_HOSTPORT from .env
This makes real LLM calls against YOUR server; it does not call any paid API.
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import _bootstrap  # noqa: F401  (puts apps/api on sys.path)

from app.agents.quest_master import QuestMasterInput, build_messages, extract_json_text
from app.config import get_settings
from app.models.context import QuestContext, Weather
from app.models.enums import MOODS, PERSONAS
from app.models.quest import llm_json_schema
from app.services.llm_client import LLMClient, LLMError
from app.services.places_repo import Candidate
from app.validators.core import validate_quest

REPO = Path(__file__).resolve().parents[1]

# Synthetic but realistic candidate pool (names are generic on purpose).
POOL = [
    Candidate(id="way/101", name="Riverside Park", kind="park", distance_m=650, lat=0, lng=0),
    Candidate(id="node/102", name="Old Stone Bridge", kind="heritage", distance_m=900, lat=0,
              lng=0),
    Candidate(id="way/103", name="City Museum", kind="museum", distance_m=1200, lat=0, lng=0,
              indoor=True, needs_daylight=False),
    Candidate(id="node/104", name="Hilltop Viewpoint", kind="viewpoint", distance_m=1400, lat=0,
              lng=0),
    Candidate(id="node/105", name="Corner Cafe", kind="cafe", distance_m=300, lat=0, lng=0,
              indoor=True, needs_daylight=False),
    Candidate(id="way/106", name="Rose Garden", kind="garden", distance_m=800, lat=0, lng=0),
    Candidate(id="node/107", name="Mural Wall", kind="artwork", distance_m=500, lat=0, lng=0),
    Candidate(id="way/108", name="Weekend Market", kind="market", distance_m=1000, lat=0, lng=0),
    Candidate(id="way/109", name="Public Library", kind="library", distance_m=700, lat=0, lng=0,
              indoor=True, needs_daylight=False),
]  # fmt: skip
INTERESTS = ["birds", "history", "street food", "sketching", "trees", "architecture", "running"]


def make_input(rng: random.Random) -> QuestMasterInput:
    indoor_only = rng.random() < 0.1
    empty = rng.random() < 0.08
    hour = rng.randint(7, 18)
    local = datetime(2026, 10, 7, hour, rng.choice([0, 15, 30, 45]), tzinfo=UTC)
    context = QuestContext(
        local_time=local,
        part_of_day="morning" if hour < 12 else "afternoon" if hour < 17 else "evening",
        weekday=local.strftime("%A"),
        sunset=local.replace(hour=18, minute=30),
        daylight_minutes_left=max(0, int((local.replace(hour=18, minute=30) - local)
                                         / timedelta(minutes=1))),
        weather=Weather(summary=rng.choice(["clear", "cloudy", "light rain"]),
                        temp_c=rng.choice([18.0, 24.0, 31.0]), precip_prob=rng.choice([0, 20, 75])),
        indoor_only=indoor_only,
    )  # fmt: skip
    candidates = [] if empty else rng.sample(POOL, k=rng.randint(3, 8))
    return QuestMasterInput(
        context=context,
        persona=rng.choice(PERSONAS),
        mood=rng.choice(MOODS),
        interests=rng.sample(INTERESTS, k=rng.randint(0, 3)),
        minutes_available=rng.choice([30, 45, 60, 90]),
        candidates=candidates,
        recent_categories=rng.sample(["explorer", "naturalist", "foodie"], k=rng.randint(0, 2)),
    )


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    base_url = args.base_url or settings.llm_url
    if not base_url:
        print("No LLM URL: pass --base-url or set LLM_BASE_URL / LLM_HOSTPORT.", file=sys.stderr)
        return 2
    client = LLMClient(base_url, model=args.model or settings.llm_model, timeout_s=args.timeout)
    schema = None if args.no_schema else llm_json_schema()
    rng = random.Random(args.seed)  # noqa: S311  (reproducible sampling, not security)

    rows: list[dict[str, object]] = []
    for i in range(args.n):
        inp = make_input(rng)
        try:
            res = await client.chat(build_messages(inp), schema)
        except LLMError as exc:
            rows.append({"i": i, "error": exc.kind})
            print(f"[{i + 1}/{args.n}] error: {exc.kind}")
            continue
        verdict = validate_quest(extract_json_text(res.content), inp.validation_context(),
                                 inp.candidates)  # fmt: skip
        rows.append({
            "i": i, "latency_ms": res.latency_ms, "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens, "tokens_per_s": res.tokens_per_s,
            "valid": verdict.ok, "failures": verdict.failure_ids, "model": res.model,
        })  # fmt: skip
        print(f"[{i + 1}/{args.n}] {res.latency_ms} ms, "
              f"{res.completion_tokens} tok, valid={verdict.ok} {verdict.failure_ids}")  # fmt: skip

    ok = [r for r in rows if "error" not in r]
    lat = [float(r["latency_ms"]) for r in ok]  # type: ignore[arg-type]
    tps = [float(r["tokens_per_s"]) for r in ok if r["tokens_per_s"]]  # type: ignore[arg-type]
    summary = {
        "requests": len(rows),
        "errors": len(rows) - len(ok),
        "latency_ms_p50": round(percentile(lat, 0.5)) if lat else None,
        "latency_ms_p95": round(percentile(lat, 0.95)) if lat else None,
        "tokens_per_s_mean": round(statistics.mean(tps), 2) if tps else None,
        "prompt_tokens_mean": round(statistics.mean(
            [float(r["prompt_tokens"]) for r in ok if r["prompt_tokens"]]  # type: ignore[arg-type]
        ), 1) if ok else None,
        "validator_pass_rate": (
            round(sum(bool(r["valid"]) for r in ok) / len(ok), 3) if ok else None
        ),
    }  # fmt: skip
    report = {
        "kind": "bench_llm",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "target": args.label or "unlabelled",  # e.g. "render-pro qwen3-4b q4_k_m"
        "model": ok[0]["model"] if ok else None,
        "schema_constrained": schema is not None,
        "seed": args.seed,
        "summary": summary,
        "rows": rows,
    }
    out = (
        Path(args.out)
        if args.out
        else (REPO / "evals" / f"bench_llm_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--base-url", help="e.g. http://localhost:8080 (default: settings)")
    p.add_argument("--model", help="`model` field (default: LLM_MODEL)")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--timeout", type=float, default=60.0, help="per request, seconds")
    p.add_argument("--no-schema", action="store_true", help="unconstrained decoding")
    p.add_argument("--label", help="free label for the report, e.g. plan + model")
    p.add_argument("--out", help="output path (default evals/bench_llm_<ts>.json)")
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
