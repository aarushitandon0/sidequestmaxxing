# Gemma verifier spike — labelled photo set (P11, gate G2)

Photos are **not committed** (they're yours and may show your neighbourhood). Keep them on your machine.

## What to collect (≥ 30 photos, take them yourself, outdoors and indoors)
| Group | Count | Example `photo_prompt`s |
|---|---|---|
| Positives — the photo shows the prompt | ≥ 18 | `three different leaves side by side`, `a plaque or carved detail`, `an interesting door`, `the view from a hilltop`, `a colourful flower or leaf`, `your sketch of a detail` |
| Hard negatives — same scene type, wrong subject | ≥ 8 | prompt `an interesting door`, photo of a plain wall; prompt `a plaque`, photo of a tree trunk |
| Easy negatives — unrelated | ≥ 4 | prompt `a flower`, photo of a keyboard |
Include a few blurry, dark (dusk) and tilted shots. **No people or faces** (V6 forbids people prompts, and we don't want their photos either).

## File naming
`<pos|neg>__<photo-prompt-with-dashes>__<anything>.jpg`, e.g. `pos__three-different-leaves-side-by-side__01.jpg`, `neg__an-interesting-door__plain-wall.jpg`.

## Running
1. `npm run dev` in `apps/web`, open `http://localhost:5173/spike/gemma` in Chrome with WebGPU (desktop first, then your phone on the same network via `npm run dev -- --host`).
2. Install the model (configured `VITE_GEMMA_MODEL_URL` or “Use a model file I already have”).
3. Pick all photos → wait → **Download results JSON** (saved locally).
4. `node --experimental-strip-types spike/score.ts ~/Downloads/gemma_spike_results.json` → writes `evals/gemma_spike_<ts>.json` with precision / recall / accuracy / p50 / p95 latency.
5. Record the numbers (with device + browser) in `docs/DECISIONS.md` under Gate G2. Memory: Chrome Task Manager (Shift+Esc) → the tab's memory footprint during inference.
