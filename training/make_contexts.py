"""Sample Quest Master contexts for training/eval (MASTERSPEC §10.3 step 1).

Places come from the seeded `places` export (training/dump_places.py → data/places.jsonl).
Places are split by AREA (geohash-5 cell) so val/test places are never seen in training.
Edge mix: ~8% empty-candidate contexts, ~10% indoor_only contexts. Deterministic for a seed.

  python training/make_contexts.py                       # data/places.jsonl → data/contexts/
  python training/make_contexts.py --synthetic --scale 0.05   # pipeline dry run, no Atlas

`--synthetic` invents generic places for testing the pipeline only; its output is labelled
synthetic in the run metadata and must never be used for a real training run.
"""

import argparse
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from common import DATA, SPLITS, load_config, read_jsonl, rng, save_run_metadata, write_jsonl

from app.agents.context_builder import indoor_reasons, part_of_day
from app.agents.scout import diversify, safety_filter
from app.models.context import QuestContext, Weather
from app.models.enums import CATEGORIES, MOODS, PERSONAS
from app.services.geo import cell5, haversine_m
from app.services.places_repo import Candidate

CONFIG = Path(__file__).parent / "configs" / "data.json"
IST = timezone(timedelta(hours=5, minutes=30))

# Same keyword list the app offers (apps/web/src/lib/prefs.ts) — already "sanitized" form.
INTERESTS = ["birds", "trees", "history", "street food", "architecture", "art", "sketching",
             "coffee", "markets", "running", "quiet spots", "geology"]  # fmt: skip

WEATHER: list[tuple[str, float, int, int | None, bool]] = [
    # summary, weight, temp_c, precip %, thunderstorm
    ("clear sky", 0.30, 27, 5, False),
    ("partly cloudy", 0.25, 25, 15, False),
    ("overcast", 0.15, 23, 30, False),
    ("light drizzle", 0.10, 22, 55, False),
    ("rain", 0.08, 21, 85, False),
    ("thunderstorm", 0.04, 24, 90, True),
    ("hot and sunny", 0.05, 39, 0, False),
    ("unknown", 0.03, 0, None, False),
]


def place_to_row(doc: dict[str, Any]) -> dict[str, Any]:
    lng, lat = doc["loc"]["coordinates"]
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "kind": doc["kind"],
        "lat": float(lat),
        "lng": float(lng),
        "tags_summary": doc.get("tags_summary", ""),
        "indoor": bool(doc.get("indoor", False)),
        "needs_daylight": bool(doc.get("needs_daylight", True)),
        "cell5": doc.get("cell5") or cell5(float(lat), float(lng)),
    }


SYN_KINDS = [
    ("park", "Park", False), ("garden", "Garden", False), ("viewpoint", "Viewpoint", False),
    ("heritage", "Old Gate", False), ("artwork", "Mural", False), ("market", "Market", False),
    ("cafe", "Cafe", True), ("museum", "Museum", True), ("library", "Library", True),
    ("temple", "Temple", False), ("water", "Lake", False), ("peak", "Hill", False),
]  # fmt: skip
SYN_NAMES = ["Banyan", "Riverside", "Old Town", "Hilltop", "Lotus", "Maple", "Sunset", "Lantern",
             "Stonebridge", "Peacock", "Cedar", "Monsoon", "Harbor", "Willow", "Kite"]  # fmt: skip


def synthetic_places(seed: int, areas: int = 40, per_area: int = 16) -> list[dict[str, Any]]:
    """Generic made-up places spread over `areas` geohash-5 cells (pipeline tests only)."""
    r = rng(seed, "synthetic-places")
    out: list[dict[str, Any]] = []
    for a in range(areas):
        clat, clng = 18.35 + (a // 8) * 0.06, 73.65 + (a % 8) * 0.06
        for j in range(per_area):
            kind, noun, indoor = r.choice(SYN_KINDS)
            lat, lng = clat + r.uniform(-0.015, 0.015), clng + r.uniform(-0.015, 0.015)
            out.append({
                "id": f"syn/{a}-{j}", "name": f"{r.choice(SYN_NAMES)} {noun}", "kind": kind,
                "lat": round(lat, 5), "lng": round(lng, 5), "tags_summary": "synthetic",
                "indoor": indoor, "needs_daylight": not indoor, "cell5": cell5(lat, lng),
            })  # fmt: skip
    return out


def assign_splits(cells: list[str], seed: int, fractions: dict[str, float]) -> dict[str, str]:
    """Deterministic area → split. Each split gets at least one cell when possible."""
    ordered = sorted(cells, key=lambda c: rng(seed, "cell", c).random())
    n = len(ordered)
    n_test = max(1, round(n * fractions["test"])) if n >= 3 else 0
    n_val = max(1, round(n * fractions["val"])) if n >= 3 else 0
    out: dict[str, str] = {}
    for i, c in enumerate(ordered):
        out[c] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return out


def sample_weather(r: Any, force_indoor: bool) -> Weather:
    if force_indoor and r.random() < 0.85:
        summary, _, temp, precip, storm = r.choice([w for w in WEATHER if w[3] and w[3] >= 70])
    else:
        summary, _, temp, precip, storm = r.choices(WEATHER, weights=[w[1] for w in WEATHER])[0]
    if summary == "unknown":
        return Weather()
    return Weather(summary=summary, temp_c=float(temp + r.randint(-3, 3)), precip_prob=precip,
                   thunderstorm=storm)  # fmt: skip


def sample_context(r: Any, force_indoor: bool) -> QuestContext:
    day = datetime(2026, 3, 1, tzinfo=IST) + timedelta(days=r.randint(0, 240))
    sunrise = day.replace(hour=6, minute=10) + timedelta(minutes=r.randint(-20, 30))
    sunset = day.replace(hour=18, minute=35) + timedelta(minutes=r.randint(-25, 30))
    if force_indoor and r.random() < 0.3:
        hour = r.choice([18, 19, 20])  # dark → indoor_only via daylight
    else:
        hour = r.choices(range(6, 20), weights=[2, 4, 6, 7, 7, 6, 5, 6, 7, 7, 6, 5, 3, 2])[0]
    now = day.replace(hour=hour, minute=r.choice([0, 10, 20, 30, 40, 50]))
    left = max(0, int((sunset - now).total_seconds() // 60)) if sunrise <= now else 0
    weather = sample_weather(r, force_indoor)
    reasons = indoor_reasons(weather, left)
    return QuestContext(
        local_time=now, part_of_day=part_of_day(now.hour), weekday=now.strftime("%A"),
        sunrise=sunrise, sunset=sunset, daylight_minutes_left=left, weather=weather,
        indoor_only=bool(reasons), indoor_reasons=reasons,
    )  # fmt: skip


def candidates_for(r: Any, places: list[dict[str, Any]], anchor: dict[str, Any], radius: int,
                   ctx: QuestContext, minutes: int, limit: int) -> list[Candidate]:  # fmt: skip
    # A user point near the anchor (never stored: only distances leave this function).
    bearing, dist = r.uniform(0, 2 * math.pi), r.uniform(150, min(radius, 2500))
    ulat = anchor["lat"] + (dist * math.cos(bearing)) / 111_320
    ulng = anchor["lng"] + (dist * math.sin(bearing)) / (111_320 * math.cos(math.radians(ulat)))
    near: list[Candidate] = []
    for p in places:
        d = haversine_m(ulat, ulng, p["lat"], p["lng"])
        if d <= radius:
            near.append(Candidate(
                id=p["id"], name=p["name"], kind=p["kind"], distance_m=int(d),
                tags_summary=p["tags_summary"], indoor=p["indoor"],
                needs_daylight=p["needs_daylight"], lat=round(p["lat"], 3), lng=round(p["lng"], 3),
                score=round(r.uniform(0.55, 0.95), 3),
            ))  # fmt: skip
    near.sort(key=lambda c: c.score or 0, reverse=True)  # stands in for vector rank
    kept, _ = safety_filter(near, ctx, minutes)
    return diversify(kept, limit)


def make_split(split: str, n: int, places: list[dict[str, Any]], cfg: dict[str, Any],
               seed: int) -> list[dict[str, Any]]:  # fmt: skip
    r = rng(seed, "contexts", split)
    out: list[dict[str, Any]] = []
    attempts = 0
    while len(out) < n and attempts < n * 20:
        attempts += 1
        force_empty = r.random() < cfg["empty_candidates_rate"]
        want_indoor = r.random() < cfg["indoor_only_rate"]
        ctx = sample_context(r, want_indoor)
        for _ in range(50):  # resample until the indoor_only flag matches the planned mix
            if ctx.indoor_only == want_indoor:
                break
            ctx = sample_context(r, want_indoor)
        else:
            continue
        minutes = r.choice(cfg["minutes_options"])
        radius = r.choice(cfg["radius_options"])
        anchor = r.choice(places)
        cands = [] if force_empty else candidates_for(r, places, anchor, radius, ctx, minutes,
                                                      cfg["max_candidates"])  # fmt: skip
        if not force_empty and not cands:
            continue  # empties come only from the planned 8%
        out.append({
            "id": f"{split}-{len(out):05d}",
            "split": split,
            "area": anchor["cell5"],
            "input": {
                "context": ctx.model_dump(mode="json"),
                "persona": r.choice(PERSONAS),
                "mood": r.choice(MOODS),
                "interests": r.sample(INTERESTS, r.choice([0, 0, 1, 2, 2, 3])),
                "minutes_available": minutes,
                "recent_categories": r.sample(list(CATEGORIES), r.choice([0, 1, 1, 2, 3])),
                "candidates": [c.model_dump(mode="json") for c in cands],
            },
        })  # fmt: skip
    if len(out) < n:
        raise SystemExit(f"{split}: only {len(out)}/{n} contexts — not enough places in this split")
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    return {
        "n": len(rows),
        "empty_candidates": round(sum(not r["input"]["candidates"] for r in rows) / n, 3),
        "indoor_only": round(sum(r["input"]["context"]["indoor_only"] for r in rows) / n, 3),
        "areas": len({r["area"] for r in rows}),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--places", type=Path, default=DATA / "places.jsonl")
    ap.add_argument("--out", type=Path, default=DATA / "contexts")
    ap.add_argument("--synthetic", action="store_true", help="made-up places (pipeline tests only)")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply split counts (dry runs)")
    ap.add_argument("--seed", type=int)
    args = ap.parse_args(argv)

    cfg = load_config(CONFIG)
    seed = args.seed if args.seed is not None else cfg["seed"]
    if args.synthetic:
        places = synthetic_places(seed)
    elif args.places.exists():
        places = [place_to_row(d) if "loc" in d else d for d in read_jsonl(args.places)]
    else:
        print(f"{args.places} not found — run training/dump_places.py (or use --synthetic).",
              file=sys.stderr)  # fmt: skip
        return 2

    by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in places:
        by_cell[p["cell5"]].append(p)
    split_of = assign_splits(list(by_cell), seed, cfg["split_fractions"])
    stats: dict[str, Any] = {}
    for split in SPLITS:
        pool = [p for c, ps in by_cell.items() if split_of[c] == split for p in ps]
        n = max(1, round(cfg["counts"][split] * args.scale))
        if not pool:
            raise SystemExit(f"no places for split {split}: need more areas")
        rows = make_split(split, n, pool, cfg, seed)
        write_jsonl(args.out / f"{split}.jsonl", rows)
        stats[split] = {**summarize(rows), "places": len(pool)}
        print(f"{split}: {stats[split]}")

    save_run_metadata(f"contexts_{'synthetic' if args.synthetic else 'osm'}", {
        "stage": "make_contexts", "seed": seed, "synthetic": args.synthetic, "scale": args.scale,
        "places": len(places), "areas": len(by_cell), "splits": stats,
    })  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
