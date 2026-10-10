# CLAUDE.md — Sidequestmaxxing

You are helping build **Sidequestmaxxing**: an open-source-AI game that turns the user's neighbourhood into side quests and gets them off the screen. Built for the DEV "Touch Grass" challenge. Deployed on **Render**.

## Source of truth (read before coding)
1. `MASTERSPEC.md` — requirements, schemas, API, safety, training/eval. **Authoritative.**
2. `PROJECTPLAN.md` — schedule, gates, risks, cut order.
3. This file — how to work in this repo.
If these conflict with what the user says in chat, follow the user, then **update the docs in the same commit** so they never drift. If something in `MASTERSPEC.md` is tagged **[VERIFY]**, check the current official docs (web search/fetch) before relying on it and note the answer in `docs/DECISIONS.md`.

## Repo layout
```
apps/web/        React + Vite + TS PWA (Tailwind, TanStack Query, Leaflet)
apps/api/        FastAPI service (Python 3.12)
services/llm/    llama.cpp server Dockerfile + entrypoint (Render private service)
prompts/         ONE source of truth for prompts (used by api, web, training)
training/        Tinker data gen, filters, SFT, eval harness, export notes
scripts/         seed_places.py, create_indexes.py, smoke_test.sh, scan_secrets.py
evals/           generated results (never hand-edit numbers)
docs/            DECISIONS.md, DEVRELAY.md, CLAUDE_CODE_PROMPTS.md, SECURITY.md, TRACES.md
render.yaml      Render Blueprint (web + api + llm)
```

## Commands (keep these working; update here if they change)
```
# API
cd apps/api && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt
pytest -q                                   # unit + contract tests (ruff check . ; mypy)
uvicorn app.main:app --reload --port 8000

# Web
cd apps/web && npm ci
npm run dev | npm run build | npm run test | npm run lint | npm run typecheck
npm run e2e                                 # Playwright (pre-installed Chromium; mocked API, fake verifier build)
npm run check:csp                           # render.yaml CSP vs the real dist/ in Chromium (needs npm run build first)

# Data / infra
python scripts/create_indexes.py            # collections + Atlas vector indexes
python scripts/seed_places.py --bbox "<S,W,N,E>" --city "<name>"
python scripts/seed_cities.py --dry-run         # all seeded cities: fetch + count, no writes
python scripts/seed_cities.py --only pune london --from-cache   # re-seed from cached payloads
python scripts/check_cities.py                  # every picker city has places the Scout can find
python scripts/fetch_events.py --city "Pune, Maharashtra, India" --dry-run   # live events: funnel only, no writes
python scripts/fetch_events.py --city "Pune, Maharashtra, India" --from-cache  # re-run the filters on the cached payload (no SerpApi call)
bash scripts/smoke_test.sh                  # hits healthz + generate against API_BASE_URL
python scripts/bench_llm.py --base-url http://localhost:8080 --n 20   # gate G1 latency → evals/
python scripts/scan_secrets.py              # secret scan: tracked files + every commit
python scripts/scan_secrets.py --tree       # working tree only (fast)
python scripts/summarize_field.py <csv...>  # field-test CSV (/settings/export) → evals/field.md

# Training (repo root, API venv; see training/README.md)
python -m pytest -q training/tests        # pipeline tests, free backends
python training/make_contexts.py --synthetic --scale 0.05   # dry run, no Atlas
python training/export_model.py <download|merge|gguf|sha|card|publish> --run <run>   # P17; plan-only without --go (docs/MODEL_EXPORT.md)
python training/eval.py run --arm tuned --mock --label m && python training/eval.py run --arm baseline --mock --label b && python training/eval.py report --mock-judge --embedder hash   # eval dry run
```

## Working agreement
- **Plan first.** For any task touching more than 2 files, write a short plan (files, steps, risks) and wait for approval before editing. Use Plan Mode.
- **Small vertical slices.** One task per session. Finish → run tests → commit → stop. Don't start the next task unprompted.
- **Never guess an API.** For Tinker, Render Blueprint fields, MediaPipe, llama.cpp flags, ElevenLabs, Atlas Vector Search, Sentry: read the current official docs first. If you can't verify, say so and add it to `docs/DECISIONS.md` as an open question.
- **Be honest in docs and numbers.** Never invent metrics, benchmarks, or results. Evaluation numbers must come from scripts that write to `evals/`.
- **Ask before:** adding dependencies beyond the stack in MASTERSPEC §4, changing the data model or API contract, changing prompts (they affect training), deleting files, running anything that spends money (Tinker training runs, bulk TTS, large Overpass pulls), or touching `render.yaml` env/plan values.
- **Do not** add auth, user accounts, social features, payments, or analytics trackers.

## Non-negotiable invariants
1. **Safety:** quests only at public places; run validators V1–V12 on every LLM output; fallback engine on failure; `safety_note` always present. Never weaken banned-term lint or red-team tests to make a test pass.
2. **Privacy:** never store raw user coordinates or photos; no image upload endpoint; round coordinates to 3 decimals; scrub PII from logs/Sentry; free-text never goes straight into a prompt (sanitize or enum).
3. **Server-authoritative game logic:** the LLM never decides XP, rarity, or ids.
4. **Prompt single source:** prompts live in `/prompts`; training and serving must use byte-identical system prompts (hash test exists).
5. **Resilience:** every external dependency has a fallback (MASTERSPEC §2.4). `/v1/quests/generate` must succeed with the LLM service down.
6. **Secrets:** never commit secrets or print them in logs/output. Use env vars; `.env` is gitignored; keep `.env.example` current. If you see a secret in a file, stop and tell the user.
7. **Claims:** README/post claims must map to artifacts in the claims ledger (PROJECTPLAN §8.3).

## Code conventions
**Python (api/training/scripts)**
- Type hints everywhere; Pydantic v2 models for all request/response/LLM schemas; `async` I/O; `httpx` with explicit timeouts; no bare `except`.
- Structure: `app/{main.py,config.py,deps.py,routers/,agents/,validators/,services/,models/,prompts.py}`. Agents are plain functions with typed inputs/outputs and one Sentry span each. No agent frameworks.
- Config via `pydantic-settings` (env only). Fail fast on missing required env in production.
- Logging: structured, no PII. Use `logging`, not `print`.
- Tests: `pytest`, `pytest-asyncio`; mock LLM/Mongo/HTTP; table-driven validator tests; property tests where cheap.
- Format/lint: `ruff` (+ `ruff format`), `mypy --strict` on `app/` if feasible.

**TypeScript (web)**
- `strict` mode; no `any` without a comment; functional components + hooks; server state via TanStack Query; small components; colocate tests.
- Accessibility: semantic HTML, labels, focus states, ≥44 px targets, `prefers-reduced-motion`, text alternative for all audio.
- State machine for quest lifecycle (`idle → offered → accepted → verifying → completed`); persist active quest locally so Walk Mode survives reloads/offline.
- No secrets in the bundle. Env via `import.meta.env.VITE_*` only for public values.
- Permissions (camera/geolocation) requested just-in-time with a plain-language reason and a working fallback when denied.
- Design: warm, outdoorsy, playful RPG — avoid generic purple-gradient AI aesthetics. Use the `frontend-design` skill if available.

**Training (Tinker)**
- Scripts are reproducible: fixed seeds, config in YAML/JSON, run metadata saved to `training/runs/`.
- All dataset filtering uses the same validators as production (`apps/api/app/validators`).
- Evaluate the **exact quantized GGUF** that Render serves.

## Definition of done (every task)
- [ ] Matches MASTERSPEC (or spec updated in same commit).
- [ ] Tests added/updated and passing (`pytest -q`, `npm run test`, lint, typecheck).
- [ ] Works with the LLM service stopped (where relevant).
- [ ] No secrets, no PII in logs, no new dependency without approval.
- [ ] Docs/commands updated if behaviour changed.
- [ ] Conventional commit message (`feat:`, `fix:`, `docs:`, `chore:`, `test:`), one logical change per commit.
- [ ] Short summary to the user: what changed, how to run/verify, what's next, open questions.

## Render notes
- Services: `sqm-web` (static), `sqm-api` (Docker, context = repo root), `sqm-llm` (private service + disk at `/data`).
- After the first deploy, copy actual `onrender.com` URLs into `VITE_API_BASE_URL` and `WEB_ORIGIN` (names may get suffixes).
- Don't run the LLM or API on free instances for the demo (spin-down, no disk).
- Before changing plan sizes, state the cost implication and ask.

## Session hygiene (DevRelay)
- Sessions may be saved and **published** with the post. Never paste real keys/tokens into the chat. Refer to env var names only.
- Keep prompts specific and outcomes explicit; summarize decisions at the end of each session in `docs/DECISIONS.md`.
- Don't publish, submit, register, or claim sponsor offers through DevRelay without explicit user confirmation in chat.

## When stuck
State what you tried, what you observed (exact error), and 2–3 options with trade-offs. Do not silently work around a spec requirement. Prefer the simplest design that satisfies MASTERSPEC and is demoable.
