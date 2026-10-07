"""Eval harness: baseline vs tuned on the 120 held-out contexts (MASTERSPEC §10.6, P16).

Two steps, because the two arms are usually served one after the other from the same box:

  # 1. run one arm against the SERVED model (repeat for the other arm after swapping GGUFs)
  python training/eval.py run --arm baseline --base-url http://localhost:8080 --label <model id>
  python training/eval.py run --arm tuned    --base-url http://localhost:8080 --label <model id>
  # 2. score both arms, LLM-judge voice, write evals/results.{json,md} + evals/human_pairs.csv
  python training/eval.py report --judge-url <openai-compatible url> --judge-model <id> \
      --judge-family llama --tuned-family qwen

  # dry run, no server and no money: mock endpoint + mock judge, writes to training/data/
  python training/eval.py run --arm baseline --mock --label mock-base
  python training/eval.py run --arm tuned --mock --label mock-tuned
  python training/eval.py report --mock-judge

Arms: baseline = base model + long teacher prompt + 3 few-shot examples; tuned = short
production prompt, zero-shot. Each context runs WITHOUT grammar (headline numbers) and WITH the
production JSON-schema constraint (what ships). `run` refuses to start if the endpoint's
reported model id doesn't match --label. Seeded: the same seed gives the same request stream.
"""

import argparse
import asyncio
import csv
import itertools
import json
import os
import statistics
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx

from common import DATA, EVALS, git_rev, read_jsonl, rng, utc_stamp, write_jsonl
from embed import make_embedder
from prompts_extra import teacher_messages
from records import fallback_input, messages, to_input, validation_context

from app.agents.fallback_engine import generate_fallback_quest
from app.agents.quest_master import extract_json_text
from app.models.quest import llm_json_schema
from app.services.embeddings import cosine
from app.services.llm_client import LLMError, build_payload, parse_response
from app.validators.core import ValidationResult, validate_quest

ARMS = ("baseline", "tuned")
MODES = ("raw", "grammar")  # raw = no grammar-constrained decoding (headline)
DRY_DIR = DATA / "eval_dry_run"  # mock outputs never land in evals/
CONSTRAINT = {"V3", "V9", "V10"}
SAFETY = {"V4", "V5", "V6", "V8"}
JUDGE_PROMPT = (
    "You compare two side-quest cards written for the same player and neighbourhood. "
    "Judge VOICE only: vivid, playful game-master tone, specific to the place, concise and "
    "clear. Ignore JSON formatting. Reply with exactly one letter: A or B."
)
Responder = Callable[[str, dict[str, Any]], dict[str, Any]]


# ---------------------------------------------------------------- run


def arm_messages(arm: str, record: dict[str, Any]) -> list[dict[str, str]]:
    return teacher_messages(record) if arm == "baseline" else messages(record)


def served_ids(body: object) -> set[str]:
    """Model ids from /v1/models (llama.cpp: `data[].id`, plus `models[].name|model`)."""
    ids: set[str] = set()
    if isinstance(body, dict):
        for key, fields in (("data", ("id",)), ("models", ("name", "model"))):
            for m in body.get(key) or []:
                if isinstance(m, dict):
                    ids |= {str(m[f]) for f in fields if m.get(f)}
    return ids | {Path(i).name for i in ids}


def identity_matches(label: str, ids: set[str]) -> bool:
    return label in ids or Path(label).name in ids


def mock_transport(label: str, arm: str, seed: int) -> httpx.MockTransport:
    """Dry-run endpoint: fallback-engine quests with seeded corruption (V1/V2/V3 failures)."""
    by_user: dict[str, dict[str, Any]] = {}

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": label}]})
        body = json.loads(req.content)
        user = body["messages"][-1]["content"]
        record = by_user[user]
        r = rng(seed, "mock", arm, record["id"], body.get("seed"))
        q = generate_fallback_quest(fallback_input(record, seed=r.randrange(10**6)))
        quest = q.model_dump(mode="json")
        roll, bad = r.random(), 0.25 if arm == "baseline" else 0.08
        if "response_format" not in body and roll < bad / 2:
            content = json.dumps(quest)[:-12]  # truncated JSON → V1
        elif roll < bad:
            quest["est_minutes"] = 999  # → V3
            content = json.dumps(quest)
        else:
            content = json.dumps(quest)
        n_prompt = sum(len(m["content"]) for m in body["messages"]) // 4
        return httpx.Response(200, json={
            "model": label, "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": n_prompt, "completion_tokens": len(content) // 4},
            "timings": {"predicted_per_second": round(20 + 10 * r.random(), 2)},
        })  # fmt: skip

    transport = httpx.MockTransport(respond)
    transport.by_user = by_user  # type: ignore[attr-defined]
    return transport


async def post_chat(
    client: httpx.AsyncClient, base_url: str, payload: dict[str, Any]
) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        res = await client.post(f"{base_url}/v1/chat/completions", json=payload)
    except httpx.TimeoutException:
        return {"error": "timeout"}
    except httpx.TransportError:
        return {"error": "connection"}
    latency_ms = round((time.perf_counter() - start) * 1000)
    if res.status_code != 200:
        return {"error": f"http_{res.status_code}"}
    try:
        r = parse_response(res.json(), latency_ms)
    except (ValueError, LLMError):
        return {"error": "bad_response"}
    return {
        "raw": r.content, "model": r.model, "latency_ms": r.latency_ms,
        "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
        "tokens_per_s": r.tokens_per_s,
    }  # fmt: skip


async def run_arm(args: argparse.Namespace) -> Path:
    records = list(read_jsonl(args.contexts / "test.jsonl"))[: args.limit]
    transport = mock_transport(args.label, args.arm, args.seed) if args.mock else None
    base_url = "http://mock" if args.mock else args.base_url.rstrip("/")
    timeout = httpx.Timeout(args.timeout, connect=5.0)
    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        res = await client.get(f"{base_url}/v1/models")
        ids = served_ids(res.json()) if res.status_code == 200 else set()
        if not identity_matches(args.label, ids):
            raise SystemExit(
                f"refusing to run: served model {sorted(ids) or '?'} != {args.label!r}"
            )
        diversity_ids = {
            r["id"]
            for r in sorted(records, key=lambda r: rng(args.seed, "div", r["id"]).random())[
                : args.diversity_contexts
            ]
        }
        jobs = [(r, m, 0) for r in records for m in MODES]
        jobs += [
            (r, "raw", s)
            for r in records
            if r["id"] in diversity_ids
            for s in range(1, args.diversity_samples)
        ]
        for i, (record, mode, sample) in enumerate(jobs):
            msgs = arm_messages(args.arm, record)
            if transport is not None:
                transport.by_user[msgs[-1]["content"]] = record  # type: ignore[attr-defined]
            payload = build_payload(msgs, llm_json_schema() if mode == "grammar" else None, "quest")
            payload["seed"] = rng(args.seed, record["id"], mode, sample).randrange(2**31)
            out = await post_chat(client, base_url, payload)
            if "model" in out and not identity_matches(args.label, {out["model"]}):
                raise SystemExit(f"model changed mid-run: {out['model']!r} != {args.label!r}")
            rows.append({
                "context_id": record["id"], "arm": args.arm, "mode": mode, "sample": sample, **out,
            })  # fmt: skip
            if (i + 1) % 20 == 0 or i + 1 == len(jobs):
                print(f"[{args.arm}] {i + 1}/{len(jobs)}")
    out_dir = DRY_DIR if args.mock else args.out
    path = out_dir / "raw" / f"{args.arm}.jsonl"
    write_jsonl(path, rows)
    meta = {
        "arm": args.arm, "label": args.label, "served_ids": sorted(ids), "seed": args.seed,
        "contexts": len(records), "mock": args.mock, "git_rev": git_rev(), "run_at": utc_stamp(),
        "diversity_contexts": len(diversity_ids), "diversity_samples": args.diversity_samples,
    }  # fmt: skip
    (out_dir / "raw" / f"{args.arm}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {path}")
    return path


# ---------------------------------------------------------------- scoring


def score(row: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Per-output metric flags. Transport errors count as failures everywhere."""
    if "error" in row:
        return {"parsed": False, "fails": [f"error:{row['error']}"], "full": False}
    inp = to_input(record)
    res: ValidationResult = validate_quest(
        extract_json_text(row["raw"]), validation_context(record), inp.candidates
    )
    fails = res.failure_ids
    q = res.quest
    out: dict[str, Any] = {"parsed": q is not None, "fails": fails, "full": res.ok}
    if q is not None:
        ids = {c.id for c in inp.candidates}
        out |= {
            "has_candidates": bool(ids),
            "grounded": "V2" not in fails if ids else q.place_id is None,
            "constraints": not CONSTRAINT & set(fails),
            "safe": not SAFETY & set(fails),
            "category": q.category,
            "text": f"{q.title}. {q.briefing} {q.objective}",
        }
    return out


def pct(flags: Sequence[bool]) -> float | None:
    return round(100 * sum(flags) / len(flags), 1) if flags else None


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def mean(values: Sequence[float]) -> float | None:
    return round(statistics.mean(values), 2) if values else None


def mode_metrics(rows: list[dict[str, Any]], scores: list[dict[str, Any]]) -> dict[str, Any]:
    with_c = [s for s in scores if s["parsed"] and s["has_candidates"]]
    without_c = [s for s in scores if s["parsed"] and not s["has_candidates"]]
    n_with = sum(bool(s.get("has_candidates", True)) for s in scores)
    ok = [r for r in rows if "error" not in r]
    lat = [float(r["latency_ms"]) for r in ok]
    return {
        "n": len(scores),
        "errors": len(rows) - len(ok),
        "json_validity": pct([s["parsed"] for s in scores]),
        # errors and unparsable outputs count as ungrounded (denominator = all of that kind)
        "grounding_with_candidates": pct(
            [s["grounded"] for s in with_c] + [False] * (n_with - len(with_c))
        ),
        "grounding_null_when_none": pct([s["grounded"] for s in without_c]),
        "constraint_adherence": pct([s.get("constraints", False) for s in scores]),
        "safety_lint": pct([s.get("safe", False) for s in scores]),
        "full_pass": pct([s["full"] for s in scores]),
        "prompt_tokens_mean": mean([float(r["prompt_tokens"]) for r in ok if r["prompt_tokens"]]),
        "latency_ms_p50": percentile(lat, 0.5),
        "latency_ms_p95": percentile(lat, 0.95),
        "tokens_per_s_mean": mean([float(r["tokens_per_s"]) for r in ok if r["tokens_per_s"]]),
        "failure_counts": dict(Counter(f for s in scores for f in s["fails"]).most_common()),
    }


async def diversity(
    rows: list[dict[str, Any]], scores: list[dict[str, Any]], embedder: Any
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r, s in zip(rows, scores, strict=True):
        if r["mode"] == "raw" and s["parsed"]:
            groups.setdefault(r["context_id"], []).append(s)
    groups = {k: v for k, v in groups.items() if len(v) > 1}
    dists, cat_rates = [], []
    for g in groups.values():
        vecs = await embedder.embed([s["text"] for s in g])
        pairs = list(itertools.combinations(vecs, 2))
        dists.append(statistics.mean(1 - cosine(a, b) for a, b in pairs))
        cat_rates.append(len({s["category"] for s in g}) / len(g))
    return {
        "contexts": len(groups),
        "mean_pairwise_distance": mean(dists),
        "distinct_category_rate": mean(cat_rates),
    }


# ---------------------------------------------------------------- voice


def judge_pairs(
    data: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]], seed: int, n: int
) -> list[dict[str, Any]]:
    """Headline (raw) outputs where both arms parsed, same context; seeded sample."""
    base = {
        r["context_id"]: (r, s)
        for r, s in data["baseline"]
        if r["mode"] == "raw" and r["sample"] == 0
    }
    pairs = []
    for r, s in data["tuned"]:
        if r["mode"] == "raw" and r["sample"] == 0 and s["parsed"]:
            b = base.get(r["context_id"])
            if b and b[1]["parsed"]:
                pairs.append(
                    {"context_id": r["context_id"], "baseline": b[1]["text"], "tuned": s["text"]}
                )
    pairs.sort(key=lambda p: rng(seed, "pairs", p["context_id"]).random())
    return pairs[:n]


async def ask_judge(
    args: argparse.Namespace, client: httpx.AsyncClient, a: str, b: str, key: str
) -> str | None:
    if args.mock_judge:  # dry run only: seeded coin
        return "A" if rng(args.seed, "judge", key).random() < 0.5 else "B"
    payload = {
        "model": args.judge_model, "temperature": 0, "max_tokens": 3,
        "messages": [{"role": "system", "content": JUDGE_PROMPT},
                     {"role": "user", "content": f"Quest A:\n{a}\n\nQuest B:\n{b}"}],
    }  # fmt: skip
    headers = (
        {"Authorization": f"Bearer {os.environ['JUDGE_API_KEY']}"}
        if os.environ.get("JUDGE_API_KEY")
        else {}
    )
    try:
        res = await client.post(
            f"{args.judge_url.rstrip('/')}/v1/chat/completions", json=payload, headers=headers
        )
        text = str(res.json()["choices"][0]["message"]["content"]).strip().upper()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None
    return text[0] if text[:1] in ("A", "B") else None


async def voice(args: argparse.Namespace, pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Each pair judged in BOTH orders; only order-consistent verdicts count (position bias)."""
    wins = Counter[str]()
    first_pos = consistent = asked = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        for p in pairs:
            v1 = await ask_judge(args, client, p["baseline"], p["tuned"], p["context_id"] + "|bt")
            v2 = await ask_judge(args, client, p["tuned"], p["baseline"], p["context_id"] + "|tb")
            if v1 is None or v2 is None:
                continue
            asked += 1
            first_pos += (v1 == "A") + (v2 == "A")
            pick1 = "baseline" if v1 == "A" else "tuned"
            pick2 = "tuned" if v2 == "A" else "baseline"
            if pick1 == pick2:
                consistent += 1
                wins[pick1] += 1
    return {
        "judge": "MOCK (seeded coin, dry run)" if args.mock_judge else args.judge_model,
        "judge_family": "mock" if args.mock_judge else args.judge_family,
        "pairs": asked,
        "order_consistent": consistent,
        "tuned_win_rate": pct([True] * wins["tuned"] + [False] * wins["baseline"]),
        "first_position_rate": round(100 * first_pos / (2 * asked), 1) if asked else None,
    }


def human_pairs(
    args: argparse.Namespace, pairs: list[dict[str, Any]], out_dir: Path
) -> dict[str, Any]:
    """Write 20 blinded pairs for hand rating, or read the ratings back if already filled."""
    csv_path, key_path = out_dir / "human_pairs.csv", out_dir / "human_pairs_key.json"
    if csv_path.exists() and key_path.exists():
        key = json.loads(key_path.read_text())
        with csv_path.open(encoding="utf-8") as f:
            rated = [
                r for r in csv.DictReader(f) if r.get("preferred", "").strip().upper() in ("A", "B")
            ]
        if rated:
            tuned = [key[r["pair_id"]][r["preferred"].strip().upper()] == "tuned" for r in rated]
            return {"rated": len(rated), "tuned_win_rate": pct(tuned), "csv": str(csv_path)}
    key, lines = {}, []
    for i, p in enumerate(pairs[:20]):
        flip = rng(args.seed, "human", p["context_id"]).random() < 0.5
        a, b = ("tuned", "baseline") if flip else ("baseline", "tuned")
        key[f"p{i:02d}"] = {"A": a, "B": b}
        lines.append({"pair_id": f"p{i:02d}", "quest_A": p[a], "quest_B": p[b], "preferred": ""})
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["pair_id", "quest_A", "quest_B", "preferred"])
        w.writeheader()
        w.writerows(lines)
    key_path.write_text(json.dumps(key, indent=2) + "\n")
    return {"rated": 0, "tuned_win_rate": None, "csv": str(csv_path)}


# ---------------------------------------------------------------- report


def examples(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """5 best (full pass, shortest first) and 5 worst (most failure ids) headline outputs."""
    head = [(r, s) for r, s in pairs if r["mode"] == "raw" and r["sample"] == 0]
    best = sorted(
        (p for p in head if p[1]["full"]), key=lambda p: (len(p[0]["raw"]), p[0]["context_id"])
    )
    worst = sorted(
        (p for p in head if not p[1]["full"]),
        key=lambda p: (-len(p[1]["fails"]), p[0]["context_id"]),
    )

    def view(p: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
        return {"context_id": p[0]["context_id"], "fails": p[1]["fails"],
                "output": str(p[0].get("raw", p[0].get("error", "")))[:600]}  # fmt: skip

    return {"best": [view(p) for p in best[:5]], "worst": [view(p) for p in worst[:5]]}


TABLE: list[tuple[str, str, str | None]] = [  # MASTERSPEC §10.6 table: label, path, unit
    ("JSON validity", "raw.json_validity", "%"),
    ("Grounding (valid place_id)", "raw.grounding_with_candidates", "%"),
    ("Grounding (null when none)", "raw.grounding_null_when_none", "%"),
    ("Constraint adherence", "raw.constraint_adherence", "%"),
    ("Safety lint", "raw.safety_lint", "%"),
    ("Full pass", "raw.full_pass", "%"),
    ("Full pass (with grammar, shipped)", "grammar.full_pass", "%"),
    ("Diversity (pairwise distance)", "diversity.mean_pairwise_distance", None),
    ("Distinct-category rate", "diversity.distinct_category_rate", None),
    ("Prompt tokens", "raw.prompt_tokens_mean", "tok"),
    ("Latency p50 (grammar)", "grammar.latency_ms_p50", "ms"),
    ("Latency p95 (grammar)", "grammar.latency_ms_p95", "ms"),
    ("Tokens/s (grammar)", "grammar.tokens_per_s_mean", "tok/s"),
    ("Est. cost per 1k quests", "cost.usd_per_1k_quests", "USD"),
]


def lookup(d: dict[str, Any], path: str) -> Any:
    for part in path.split("."):
        d = d.get(part) if isinstance(d, dict) else None  # type: ignore[assignment]
    return d


async def report(args: argparse.Namespace) -> dict[str, Any]:
    src = DRY_DIR if args.mock_judge and args.raw is None else (args.raw or args.out)
    out_dir = DRY_DIR if src == DRY_DIR else args.out
    contexts = {r["id"]: r for r in read_jsonl(args.contexts / "test.jsonl")}
    embedder, embedder_name = make_embedder(args.embedder)
    arms: dict[str, Any] = {}
    scored: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for arm in ARMS:
        rows = list(read_jsonl(src / "raw" / f"{arm}.jsonl"))
        meta = json.loads((src / "raw" / f"{arm}.meta.json").read_text())
        pairs = [(r, score(r, contexts[r["context_id"]])) for r in rows]
        scored[arm] = pairs
        arms[arm] = {"label": meta["label"], "mock": meta["mock"], "seed": meta["seed"]}
        for mode in MODES:
            sel = [(r, s) for r, s in pairs if r["mode"] == mode and r["sample"] == 0]
            arms[arm][mode] = mode_metrics([r for r, _ in sel], [s for _, s in sel])
        div = [(r, s) for r, s in pairs if r["mode"] == "raw"]
        arms[arm]["diversity"] = await diversity([r for r, _ in div], [s for _, s in div], embedder)
        qph = (
            3_600_000 / arms[arm]["grammar"]["latency_ms_p50"]
            if arms[arm]["grammar"]["latency_ms_p50"]
            else None
        )
        per_1k = round(1000 * args.usd_per_hour / qph, 3) if qph and args.usd_per_hour else None
        arms[arm]["cost"] = {
            "usd_per_hour": args.usd_per_hour,
            "quests_per_hour_est": round(qph, 1) if qph else None,
            "usd_per_1k_quests": per_1k,
        }
        arms[arm]["examples"] = examples(pairs)
    vpairs = judge_pairs(scored, args.seed, args.judge_pairs)
    if not args.mock_judge and not args.judge_url:
        judged: dict[str, Any] = {"judge": None, "note": "no --judge-url given; voice not judged"}
    else:
        if not args.mock_judge and args.judge_family.lower() == args.tuned_family.lower():
            raise SystemExit("judge must be a different model family than the tuned model")
        judged = await voice(args, vpairs)
    human = human_pairs(args, vpairs, out_dir)
    b, t = arms["baseline"], arms["tuned"]
    delta = (t["raw"]["full_pass"] or 0) - (b["raw"]["full_pass"] or 0)
    results = {
        "kind": "eval_baseline_vs_tuned",
        "dry_run": bool(b["mock"] or t["mock"] or args.mock_judge),
        "n": len({r["context_id"] for r, _ in scored["tuned"]}),
        "created_at": utc_stamp(), "git_rev": git_rev(), "embedder": embedder_name,
        "metrics": [
            {"label": label, "baseline": lookup(b, path), "tuned": lookup(t, path)}
            | ({"unit": u} if u else {})
            for label, path, u in TABLE
        ],
        "voice": {"llm_judge": judged, "human": human},
        "full_pass_delta_points": round(delta, 1),
        "claim_improvement": delta >= 10,
        "arms": arms,
    }  # fmt: skip
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    (out_dir / "results.md").write_text(render_md(results))
    print(render_md(results))
    print(f"wrote {out_dir / 'results.json'}")
    return results


def clip(text: str) -> str:
    return text[:240].replace("`", "'")


def fmt(v: Any, unit: str | None = None) -> str:
    if v is None:
        return "n/a"
    return f"{v}{' ' + unit if unit and unit != '%' else '%' if unit else ''}"


def render_md(r: dict[str, Any]) -> str:
    a, j, h = r["arms"], r["voice"]["llm_judge"], r["voice"]["human"]
    out = ["# Eval: baseline vs tuned (MASTERSPEC §10.6)", ""]
    if r["dry_run"]:
        out += ["> **DRY RUN — mock endpoint and/or mock judge. These numbers mean nothing.**", ""]
    out += [
        f"Generated by `training/eval.py` at {r['created_at']} (git {r['git_rev']}). "
        f"n = {r['n']} held-out contexts. Do not hand-edit.",
        "",
        f"- Baseline: `{a['baseline']['label']}` — base model, long prompt + 3 few-shot examples",
        f"- Tuned: `{a['tuned']['label']}` — short production prompt, zero-shot",
        "- Headline rows use raw decoding (no grammar); rows marked grammar use the shipped "
        "JSON-schema constraint. Errors/timeouts count as failures.",
        "",
        "| Metric | Baseline | Tuned |",
        "|---|---|---|",
    ]
    out += [
        f"| {m['label']} | {fmt(m['baseline'], m.get('unit'))} | {fmt(m['tuned'], m.get('unit'))} |"
        for m in r["metrics"]
    ]
    out += [
        "",
        f"**Full pass delta (raw): {r['full_pass_delta_points']:+} points** — "
        + ("meets" if r["claim_improvement"] else "does NOT meet")
        + " the ≥ 10-point bar for claiming improvement.",
        "",
        "## Voice",
        "",
    ]
    if j.get("judge"):
        out += [
            f"- LLM judge `{j['judge']}` (family: {j['judge_family']}), {j['pairs']} pairs "
            f"judged in both orders, {j['order_consistent']} order-consistent; tuned wins "
            f"{fmt(j['tuned_win_rate'], '%')} of consistent verdicts.",
            f"- Judge bias: picked the first position {fmt(j['first_position_rate'], '%')} of the "
            "time (50% = no position bias). LLM judges also tend to favour longer and "
            "same-family text; treat this as a weak signal next to the human rating.",
        ]
    else:
        out += [f"- LLM judge: {j['note']}."]
    out += [
        f"- Human: {h['rated']} pairs rated"
        + (
            f", tuned preferred {fmt(h['tuned_win_rate'], '%')}."
            if h["rated"]
            else f" — fill `preferred` (A/B) in `{Path(h['csv']).name}`, then re-run `report`."
        ),
        "",
    ]  # fmt: skip
    for arm in ARMS:
        ex = a[arm]["examples"]
        out += [
            f"## {arm.title()}: failure counts (raw)",
            "",
            f"`{json.dumps(a[arm]['raw']['failure_counts'])}`",
            "",
        ]
        for kind in ("best", "worst"):
            out += [f"### {arm.title()}: 5 {kind}", ""]
            out += [
                f"- `{e['context_id']}` {e['fails'] or 'pass'}: `{clip(e['output'])}`"
                for e in ex[kind]
            ] or ["- (none)"]
            out += [""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--contexts", type=Path, default=DATA / "contexts")
    ap.add_argument("--out", type=Path, default=EVALS)
    ap.add_argument("--seed", type=int, default=16)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one arm against an endpoint")
    r.add_argument("--arm", choices=ARMS, required=True)
    r.add_argument(
        "--label", required=True, help="expected served model id; run refuses on mismatch"
    )
    r.add_argument("--base-url", default="")
    r.add_argument("--mock", action="store_true", help="dry run against a built-in mock endpoint")
    r.add_argument("--limit", type=int, default=120)
    r.add_argument("--timeout", type=float, default=120.0)
    r.add_argument("--diversity-contexts", type=int, default=10)
    r.add_argument("--diversity-samples", type=int, default=20)
    p = sub.add_parser("report", help="score both arms and write results")
    p.add_argument("--raw", type=Path, help="dir containing raw/ (default: --out)")
    p.add_argument("--embedder", choices=["bge", "hash"], default="bge")
    p.add_argument("--judge-url", default="")
    p.add_argument("--judge-model", default="")
    p.add_argument("--judge-family", default="", help="e.g. llama; must differ from --tuned-family")
    p.add_argument("--tuned-family", default="qwen")
    p.add_argument("--judge-pairs", type=int, default=40)
    p.add_argument("--mock-judge", action="store_true", help="seeded coin; dry run only")
    p.add_argument("--usd-per-hour", type=float, default=0.0, help="instance price (cost estimate)")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        if not args.mock and not args.base_url:
            ap.error("--base-url is required unless --mock")
        asyncio.run(run_arm(args))
    else:
        asyncio.run(report(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
