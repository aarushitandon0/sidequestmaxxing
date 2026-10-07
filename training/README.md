# training/ — Quest Master fine-tune (MASTERSPEC §10)

Everything here imports production code from `apps/api` (validators, prompt builders, schemas),
so training data, serving and evaluation can't drift. Run from the repo root with the API venv:

```bash
source apps/api/.venv/bin/activate
pip install -r training/requirements.txt         # tinker + tinker-cookbook (only for paid steps)
python -m pytest -q training/tests                # pipeline tests (free backends, no network)
```

## Pipeline

| Step | Command | Costs money? |
|---|---|---|
| 1. Export places | `python training/dump_places.py` (needs `MONGODB_URI`) | no |
| 2. Contexts (3000/100/120, area split) | `python training/make_contexts.py` | no |
| 3. Teacher estimate | `python training/gen_teacher.py --split train --all --estimate` | no |
| 4. Teacher dry run (20) | `python training/gen_teacher.py --split train --limit 20` | yes, cents |
| 5. Filter + stats | `python training/filter.py --split train --teacher data/teacher/train.tinker.jsonl` | no |
| 6. Full teacher run | `… --all --i-approve-cost` (refuses until prices are filled in `configs/teacher.json`) | **yes** |
| 7. Recap examples | `python training/make_recap_examples.py --backend tinker --limit 20` | yes |
| 8. SFT plan | `python training/train_sft.py --smoke` (prints rows/tokens, trains nothing) | no |
| 9. SFT smoke run | `python training/train_sft.py --smoke --go` (200 rows, 1 epoch, 1 LR) — show metrics, then decide | **yes**, ≈ $0.10 |
| 10. SFT sweep | `python training/train_sft.py --go` (3 LRs x 3 epochs, best by val pass-rate) | **yes**, ≈ $13 |
| 11. Eval, one arm per served model | `python training/eval.py run --arm baseline\|tuned --base-url … --label <served model id>` | no (your server) |
| 12. Eval report + voice judge | `python training/eval.py report --judge-url … --judge-model … --judge-family llama` | judge calls, if hosted |

Dry runs without Atlas or Tinker: add `--synthetic` to steps 2/7, `--backend fallback` to step
4, `--embedder hash` to step 5, and `--mock` / `--mock-judge --embedder hash` to steps 11/12
(written to `training/data/eval_dry_run/`, never to `evals/`). Their outputs are labelled and must not be used for training.

Generated data lands in `training/data/` (gitignored). Run metadata (configs, seeds, git rev,
counts, prompt hashes — never secrets) lands in `training/runs/` and is committed.

## Decisions (see docs/DECISIONS.md D-55…)

- **Base model:** Tinker's current lineup no longer lists Qwen3-1.7B, Qwen3-4B-Instruct-2507 or
  Llama-3.2 (checked in tinker-cookbook's model list). The smallest live model is
  `Qwen/Qwen3.5-4B` (dense, hybrid thinking + vision, Apache-2.0 **[VERIFY]**); llama.cpp master
  supports its architecture (`qwen35`). Next size up: `Qwen/Qwen3-8B`, `Qwen/Qwen3.5-9B`.
- **Teacher:** `Qwen/Qwen3.5-397B-A17B` via Tinker sampling — Apache-2.0 **[VERIFY]**, which
  places no restriction on training other models.
- **Thinking off everywhere:** sampling and SFT use the cookbook's `*_disable_thinking`
  renderer; serving sends `enable_thinking: false`. **[VERIFY]** that llama.cpp's Jinja template
  for Qwen3.5 with thinking off renders the same tokens as the cookbook renderer before
  trusting eval numbers (P16 compares outputs on the same prompts).
- Configs are JSON (`configs/*.json`) — no YAML dependency.

## Cost estimate (computed 2026-10-07 — prices from search summaries, **[VERIFY]** on
https://tinker-docs.thinkingmachines.ai/tinker/models/ before approving)

Token counts are measured from the real prompts (≈ 2,600 teacher-prompt tokens per context
including the 3 worked examples; ≈ 700 tokens per SFT example).

| Item | Tokens | Price (USD / M tok) | Estimate |
|---|---|---|---|
| Teacher prefill, 3,100 contexts + 400 recaps | ≈ 8.3 M | Qwen3.5-397B prefill: **unknown** | 8.3 × P |
| Teacher sampling, 2 samples/context + recaps | ≈ 1.6 M | ≈ 5.00 (search summary) | ≈ $8 |
| SFT Qwen3.5-4B, ~2,900 ex × 3 epochs × 3 LRs | ≈ 18 M | 0.737 train (search summary) | ≈ $13 |
| SFT smoke run (200 ex, 1 epoch) | ≈ 0.14 M | 0.737 | ≈ $0.10 |
| Val sampling during SFT (100 ctx × 3 epochs × 3 LRs) | ≈ 0.7 M | 0.33 prefill / 1.005 sample | < $1 |
| Checkpoint storage | a few GB | 0.10 / GB-month | < $1 / month |

If teacher prefill were priced like sampling ($5/M), the teacher would cost ≈ $50 and the
whole plan ≈ $65; the real number is lower if prefill is cheaper. Cut options: 1 sample per
context (halves teacher sampling), a single LR, or a cheaper teacher (`Qwen/Qwen3.6-35B-A3B`).
