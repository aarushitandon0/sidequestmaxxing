# evals/

Generated results only — **never hand-edit numbers** (CLAUDE.md). Files here are written by scripts:

| File | Written by | Used by |
|---|---|---|
| `bench_llm_<ts>.json` | `scripts/bench_llm.py` (gate G1) | DECISIONS / post latency table |
| `results.json`, `results.md` | `training/eval.py report` (P16) | story page "Receipts" scene, post |
| `raw/<arm>.jsonl`, `raw/<arm>.meta.json` | `training/eval.py run` | input to `report` |
| `human_pairs.csv` (+ `_key.json`) | `training/eval.py report` | you fill `preferred` (A/B); re-run `report` |
| `field.md` | field-test tooling (P21) | story page "Receipts" scene |

Story page contract (`apps/web/scripts/build_story_data.ts`):
- `results.json`: `{"n": <held-out size>, "metrics": [{"label": str, "baseline": num|str|null, "tuned": num|str|null, "unit"?: str}]}`
- `field.md`: the first markdown table; column 1 = label, column 2 = value.
If a file is missing or doesn't match, its part of the scene is hidden.
