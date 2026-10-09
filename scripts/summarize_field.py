"""Summarize field-test CSVs exported from /settings/export into evals/field.md (P21).

The app logs one row per finished quest in the browser (no coordinates, no place names) and
exports it as CSV. This reads one or more of those files and reports the only numbers the
write-up is allowed to claim about real use: how many quests, how many minutes outside, how
much of that time the screen was awake, how often the voice was on, and how often the quest
came from the fallback engine instead of the model.

Nothing here invents or interpolates: a column that is missing or unparseable is reported as
such and left out of the denominator it belongs to.

Usage (from the repo root):
  python scripts/summarize_field.py field.csv                 # prints + writes evals/field.md
  python scripts/summarize_field.py a.csv b.csv --out /tmp/f.md
  python scripts/summarize_field.py field.csv --dry-run       # print only, write nothing
"""

import argparse
import csv
import statistics
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "evals" / "field.md"

REQUIRED = ["date", "category", "elapsed_seconds"]
TRUE = {"true", "1", "yes", "y"}
FALSE = {"false", "0", "no", "n"}


@dataclass
class Rows:
    """Parsed rows plus everything that was dropped, so nothing disappears silently."""

    rows: list[dict[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def num(value: str | None) -> float | None:
    try:
        return float((value or "").strip())
    except ValueError:
        return None


def flag(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    return None


def read_csvs(paths: Sequence[Path]) -> Rows:
    out = Rows()
    seen: set[tuple[str, ...]] = set()
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
            if missing:
                raise SystemExit(f"{path}: missing required column(s): {', '.join(missing)}")
            for n, row in enumerate(reader, start=2):
                if not any((v or "").strip() for v in row.values()):
                    continue
                if num(row.get("elapsed_seconds")) is None:
                    out.skipped.append(f"{path.name}:{n} (no elapsed_seconds)")
                    continue
                # Two exports of the same log overlap; the same quest must count once.
                key = tuple((row.get(c) or "") for c in REQUIRED)
                if key in seen:
                    out.skipped.append(f"{path.name}:{n} (duplicate of an earlier row)")
                    continue
                seen.add(key)
                out.rows.append(row)
    return out


def share_of(row: dict[str, str]) -> float | None:
    """Screen share: the exported column, else screen/elapsed when both are present."""
    direct = num(row.get("screen_share"))
    if direct is not None and 0 <= direct <= 1:
        return direct
    screen, elapsed = num(row.get("screen_seconds")), num(row.get("elapsed_seconds"))
    if screen is None or not elapsed:
        return None
    return min(screen / elapsed, 1.0)


def minutes_of(row: dict[str, str]) -> float:
    return (num(row.get("elapsed_seconds")) or 0) / 60


def r0(x: float) -> int:
    """Half-up rounding: a published 4.5% reads as 5%, not as Python's banker's 4%."""
    return int(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def pct(part: int, whole: int) -> str:
    return "-" if not whole else f"{r0(100 * part / whole)}%"


def quantile(values: list[float], q: float) -> float:
    """Nearest-rank quantile - honest on the 5-20 rows a field test actually produces."""
    s = sorted(values)
    if not s:
        return 0.0
    if q <= 0.5:
        return statistics.median(s)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[idx]


def summarize(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    n = len(rows)
    shares = [s for s in (share_of(r) for r in rows) if s is not None]
    voice = [v for v in (flag(r.get("voice")) for r in rows) if v is not None]
    sources = [(r.get("source") or "").strip().lower() for r in rows]
    known = [s for s in sources if s in {"llm", "fallback"}]
    days = {(r.get("date") or "").strip() for r in rows} - {""}

    table: list[tuple[str, str]] = [
        ("Quests completed", str(n)),
        ("Days with a quest", str(len(days))),
        ("Minutes outside", str(r0(sum(minutes_of(r) for r in rows)))),
        ("Median quest length", f"{r0(quantile([minutes_of(r) for r in rows], 0.5))} min"),
    ]

    est = [num(r.get("est_minutes")) for r in rows]
    rated = [(r, e) for r, e in zip(rows, est, strict=True) if e]
    if rated:
        over = sum(1 for r, e in rated if e is not None and minutes_of(r) > e)
        table.append(("Ran over the estimate", pct(over, len(rated))))

    if shares:
        table += [
            ("Median screen share", f"{r0(100 * quantile(shares, 0.5))}%"),
            ("p90 screen share", f"{r0(100 * quantile(shares, 0.9))}%"),
            ("Quests under 10% screen", pct(sum(1 for s in shares if s < 0.10), len(shares))),
        ]
    if voice:
        table.append(("Voice on", pct(sum(1 for v in voice if v), len(voice))))
    if known:
        fallbacks = sum(1 for s in known if s == "fallback")
        table.append(("Fallback quests (no model)", pct(fallbacks, len(known))))

    methods = [(r.get("verification_method") or "").strip() for r in rows]
    for method in ("photo", "checkin", "honor"):
        if method in methods:
            table.append((f"Verified by {method}", pct(methods.count(method), n)))
    return table


def render(
    table: Iterable[tuple[str, str]], sources: Sequence[Path], skipped: Sequence[str]
) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    names = ", ".join(p.name for p in sources)
    lines = [
        "# Field test",
        "",
        "<!-- Generated by scripts/summarize_field.py - do not hand-edit (CLAUDE.md). -->",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        *[f"| {label} | {value} |" for label, value in table],
        "",
        f"Source: {names}, exported from /settings/export; summarized {stamp}.",
        "",
        "Screen share is visible screen seconds / quest seconds, measured by the Page",
        "Visibility API between accept and complete. No coordinates are recorded.",
    ]
    if skipped:
        shown = "; ".join(skipped[:5])
        more = ", ..." if len(skipped) > 5 else ""
        lines += ["", f"Rows skipped: {len(skipped)} ({shown}{more})"]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("csv", nargs="+", type=Path, help="CSV file(s) from /settings/export")
    ap.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="markdown output (default: evals/field.md)"
    )
    ap.add_argument("--dry-run", action="store_true", help="print the summary, write nothing")
    args = ap.parse_args(argv)

    absent = [p for p in args.csv if not p.is_file()]
    if absent:
        print(f"No such file: {', '.join(str(p) for p in absent)}", file=sys.stderr)
        return 2

    parsed = read_csvs(args.csv)
    if not parsed.rows:
        print("No usable rows - nothing written.", file=sys.stderr)
        return 1

    table = summarize(parsed.rows)
    width = max(len(label) for label, _ in table)
    for label, value in table:
        print(f"{label.ljust(width)}  {value}")
    for s in parsed.skipped:
        print(f"skipped {s}", file=sys.stderr)

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(table, args.csv, parsed.skipped), encoding="utf-8")
    out = args.out.relative_to(REPO) if args.out.is_relative_to(REPO) else args.out
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
