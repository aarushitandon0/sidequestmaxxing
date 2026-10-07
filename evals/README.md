# evals/

Generated results only — **never hand-edit numbers** (CLAUDE.md). Files here are written by scripts:

| File | Written by | Used by |
|---|---|---|
| `bench_llm_<ts>.json` | `scripts/bench_llm.py` (gate G1) | DECISIONS / post latency table |
| `results.json` | eval harness (P16) | story page "Receipts" scene |
| `field.md` | field-test tooling (P21) | story page "Receipts" scene |

Story page contract (`apps/web/scripts/build_story_data.ts`):
- `results.json`: `{"n": <held-out size>, "metrics": [{"label": str, "baseline": num|str|null, "tuned": num|str|null, "unit"?: str}]}`
- `field.md`: the first markdown table; column 1 = label, column 2 = value.
If a file is missing or doesn't match, its part of the scene is hidden.
