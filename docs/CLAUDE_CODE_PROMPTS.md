# CLAUDE_CODE_PROMPTS.md — Build Sidequestmaxxing with Claude Code

How to use this file: paste **one prompt at a time**, in order. Each prompt is a vertical slice with acceptance criteria. After each: run the tests, read the diff, commit, then `/clear` (or start a fresh session) before the next. Gates (G0–G4) are in `PROJECTPLAN.md`.

## 0. Before the first prompt

```bash
mkdir sidequestmaxxing && cd sidequestmaxxing
git init
mkdir -p docs prompts apps/web apps/api services/llm training scripts evals
# copy MASTERSPEC.md, PROJECTPLAN.md, CLAUDE.md into the repo root
# copy DEVRELAY.md and CLAUDE_CODE_PROMPTS.md into docs/
printf ".env\n.env.*\n!.env.example\nnode_modules/\n.venv/\n__pycache__/\ndist/\n*.gguf\n.DS_Store\n" > .gitignore
git add -A && git commit -m "docs: add master spec, plan, and claude instructions"
claude        # start Claude Code in the repo root; press Shift+Tab to enter Plan Mode
```

Working tips:
- Start each task in **Plan Mode**; approve the plan before edits.
- Never paste secrets. Put them in `.env` yourself; tell Claude only the variable *names*.
- End each session with the **Session-close prompt** (section U1).
- If Claude goes off-spec, use **U3 (spec drift check)**.

---

## P0 — Orientation (read-only)

```
Read CLAUDE.md, MASTERSPEC.md and PROJECTPLAN.md fully. Do not write code yet.

Produce:
1. A 10-line summary of the product and the architecture in your own words.
2. A list of every item tagged [VERIFY] in MASTERSPEC.md, grouped by service, with the official documentation URL you will check for each.
3. Any contradictions, ambiguities, or risky assumptions you notice in the spec (be critical; cite section numbers).
4. A proposed order of work for Day 1 and Day 2 from PROJECTPLAN.md, with estimated effort per task.
Then create docs/DECISIONS.md with sections: Open Questions, Decisions, Verified Facts. Put the [VERIFY] list under Open Questions. Do not resolve them yet.
```

## P1 — Scaffold + deployable skeleton (Day 1)

```
Plan first, then implement. Task: scaffold the monorepo per CLAUDE.md "Repo layout" and get a walking skeleton deployable on Render.

Requirements:
- apps/api: FastAPI app with GET /healthz returning {"status":"ok","db":"unknown","llm":"unknown"}; pydantic-settings config; requirements.txt with pinned versions; pytest with one health test; ruff config.
- apps/web: Vite + React + TypeScript + Tailwind + React Router + TanStack Query + vite-plugin-pwa; a Home page that calls the API /healthz via VITE_API_BASE_URL and shows status; manifest + placeholder icons.
- apps/api/Dockerfile exactly as MASTERSPEC §12.4 (context = repo root; copy /prompts; non-root user; PORT-aware CMD). Preload the fastembed model at build time later (leave a TODO).
- services/llm/Dockerfile + entrypoint.sh per MASTERSPEC §12.3. Before finalizing, verify the llama.cpp server image name, binary path and flags in the official README and tell me what you changed.
- render.yaml per MASTERSPEC §12.2. Verify every field name against https://render.com/docs/blueprint-spec and fix what's wrong.
- .env.example with placeholder values for every env var in the spec (no real secrets).
- scripts/smoke_test.sh that curls /healthz on API_BASE_URL.

Acceptance: pytest passes; `npm run build` passes; `docker build -f apps/api/Dockerfile .` succeeds from repo root; render.yaml validates (use Render's documented validation method if available). Write the manual steps I must do in the Render dashboard (connect repo, set secrets, first deploy) to docs/DEPLOY.md. Do NOT deploy or spend money yourself. Stop after summarizing.
```

## P2 — API foundation

```
Plan first. Implement the API foundation per MASTERSPEC §4, §6, §9.4, §13.

- app/{main.py,config.py,deps.py,routers/,agents/,validators/,services/,models/,prompts.py}
- Pydantic models for Quest, QuestRequest, CompletionRequest, Profile, Settings exactly per §6 (with the LLM-owned vs server-owned field split).
- Middleware/deps: X-Device-Id validation (uuid4), CORS limited to WEB_ORIGIN, body size limit 32 KB, slowapi rate limits per §6.5, structured logging without PII.
- Input sanitizer for interests/mood/persona with table-driven tests (including prompt-injection strings like "ignore previous instructions", very long strings, unicode tricks).
- Sentry init with before_send scrubber (coordinates, device id hashed). DSN optional in dev.
- Error format {"error":{"code","message"}}.

Acceptance: pytest covers sanitizer, device-id validation, rate limit, error format. mypy/ruff clean. No endpoints beyond /healthz yet. Stop after summary.
```

## P3 — Atlas: collections, indexes, seed places

```
Plan first. Implement MongoDB Atlas data layer per MASTERSPEC §5 and seeding per §7.2.

1. app/services/db.py: async Mongo client (motor or pymongo async — pick one, justify briefly), health check used by /healthz.
2. scripts/create_indexes.py: creates collections, 2dsphere index, TTL index on memories, unique indexes, and the Atlas Vector Search indexes places_vec and memories_vec (per §5.1/§5.5). Verify in the official Atlas docs how to create vector search indexes programmatically with the current driver and whether $in filters are supported in $vectorSearch; report findings in docs/DECISIONS.md.
3. app/services/embeddings.py: fastembed with BAAI/bge-small-en-v1.5 (384 dims); lazy singleton; batch API; unit test with a tiny fixture. Update apps/api/Dockerfile to pre-download the model at build time into a cache path inside the image.
4. scripts/seed_places.py --bbox "S,W,N,E" --city NAME: query Overpass for the kinds in §7.2 (require name; exclude access=private|no), map to the `places` schema (kind, indoor, needs_daylight, cell5 via pygeohash, text, embedding), upsert idempotently, cache raw Overpass JSON to data/overpass_<city>.json (gitignored except a small committed sample), obey Overpass fair-use (single request or polite sleep, a descriptive User-Agent).
5. GET /v1/places/near?lat&lng&radius_m&q= : $vectorSearch with filter cell5 ∈ {center + 8 neighbours}, then haversine post-filter, returns ≤ 8 candidates. Include unit tests for geohash neighbours and haversine, and a mocked-DB test of the route.

Acceptance: with my MONGODB_URI in .env, running the scripts creates indexes and seeds ≥ 150 places for the bbox I give you; /v1/places/near?q=birds returns plausible results. Don't print the URI. Stop after summary with exact commands I should run.
```

## P4 — Validators + fallback engine (safety core)

```
Plan first. Implement MASTERSPEC §7.4 (validators V1–V12), §7.5 (fallback engine) and §9.2 (banned-term lint) as pure, heavily tested modules in apps/api/app/validators and app/agents/fallback_engine.py.

- validators.validate_quest(quest, ctx, candidates, recent_quests) -> ValidationResult(ok, failures[{id,reason}]).
- Table-driven tests: ≥ 6 positive and ≥ 6 negative cases per validator; include tricky cases (e.g., "climb the stairs at the museum" allowed vs "climb the rock face" rejected; photo prompts mentioning "people", "kids", "faces", "selfie"; URLs/emails/phones in strings; dusk with needs_daylight place; indoor_only).
- Fallback engine: templates for each place kind × category × persona, deterministic given a seed; must produce a valid quest for any context, including zero candidates (place-less quests).
- Property test: 500 random contexts → fallback always passes V1–V11.
- Also write the safety red-team fixture file apps/api/tests/redteam_cases.json with ≥ 40 adversarial contexts (dangerous interests, night, storms, injection strings) and a test asserting nothing unsafe passes.

Acceptance: all tests pass; coverage report for validators ≥ 95%. Do not weaken lint rules to make tests pass—if a rule is too strict, propose a change and ask me. Stop after summary.
```

## P5 — Context Builder + Scout

```
Plan first. Implement MASTERSPEC §7.1 Context Builder and §7.2 Scout.

- Context Builder: local part_of_day/weekday from local_time_iso, daylight window and weather from Open-Meteo (verify the current endpoint and params in their docs; no API key), 5-min in-memory cache per rounded location, 3 s timeout, graceful fallback to weather "unknown". Compute indoor_only and daylight_minutes_left per spec.
- Scout: combines vector search + haversine + safety/time filters + memory-based diversity. Query text = interests + mood + categories to avoid. Return ≤ 8 candidates with fields per spec. Memory check against `memories` via $vectorSearch filtered by device_id (stub until completions exist, but code path + tests with mocks).
- Each function gets a Sentry span (context.build, scout.search, memory.check).

Acceptance: unit tests with mocked Open-Meteo and mocked Mongo; edge cases: no candidates, all candidates outdoors during a storm, dusk. Stop after summary.
```

## P6 — LLM service + Quest Master client (Gate G1)

```
Plan first. Implement the inference path.

1. Prompts: create prompts/quest_master.system.txt exactly per MASTERSPEC §7.3, plus a Python loader (app/prompts.py) that exposes the text and a SHA-256; add a test asserting the hash matches a committed value in prompts/HASHES.txt (so training and serving can't drift).
2. app/agents/quest_master.py: build the user message JSON; call the llama.cpp server at http://{LLM_HOSTPORT}/v1/chat/completions with temperature 0.8, top_p 0.95, max_tokens 380, and JSON-schema-constrained decoding. Read the current llama.cpp server README to find the correct schema/grammar parameter and chat-template behaviour for the chosen model; document in DECISIONS.md. Timeout 25 s; one retry with validator failure reasons appended; then fallback engine. Return (quest, source, model, latency_ms, token_usage).
3. Make the client usable with a local llama.cpp or Ollama-compatible endpoint via LLM_BASE_URL override for local dev.
4. Tests with a mocked LLM: valid JSON; invalid JSON; schema-valid but unsafe; timeout; retry success; double failure → fallback.
5. Write scripts/bench_llm.py: sends N contexts sequentially and reports p50/p95 latency and tokens/s — this is for Gate G1.

Acceptance: all mocked tests pass. Then give me exact steps to (a) pick a base GGUF to test, (b) deploy sqm-llm on Render, (c) run bench_llm.py against it and record numbers in DECISIONS.md. Do not choose the final model yourself; present options with memory math and ask me. Stop after summary.
```

## P7 — /v1/quests/generate orchestration

```
Plan first. Implement POST /v1/quests/generate, /accept, /skip per MASTERSPEC §3.1, §6.

- Orchestrate: sanitize → Context Builder → Scout → Quest Master → validators → server fields (id, rarity, xp preview, distance, hydrated place) → save to `quests` → return.
- Rarity and xp preview computed by server code from §8 only (LLM never sets them). Unit-test rarity thresholds.
- Statuses and expiry (quests expire after 6 h). /accept sets accepted_at; /skip records skip for memory.
- Must succeed in < 3 s when the LLM is unreachable (fallback path). Add a test that proves it.
- Sentry transaction named quests.generate with child spans per MASTERSPEC §13 and tags source/retry/validator_failures.
- scripts/smoke_test.sh extended to call generate with a sample request.

Acceptance: contract tests with mocked LLM/Mongo; manual curl example in docs/DEPLOY.md. Stop after summary.
```

## P8 — Frontend foundation + onboarding

```
Plan first. Read the frontend-design skill if available, then implement MASTERSPEC §11 foundations.

- Design tokens (colors, type, spacing), a warm outdoorsy playful RPG look — not a generic purple-gradient AI look. Propose 2 visual directions in text first; wait for my pick.
- Routes: /, /onboarding, /quest, /walk, /verify, /reward, /profile, /chronicle, /settings.
- API client with typed responses (generate types from the spec's schemas), device-id creation (uuid v4 in localStorage), TanStack Query hooks, error boundary, offline banner.
- Onboarding (≤ 3 taps): persona, interests chips, radius, safety acknowledgement ("tell someone where you're going"), voice toggle.
- PWA: installable, offline shell, update prompt.
- Accessibility baseline and reduced-motion handling.

Acceptance: `npm run build/test/lint/typecheck` pass; Lighthouse PWA + accessibility ≥ 90 on the Home page (report the numbers you actually measure). Stop after summary with screenshots instructions.
```

## P8b - Scrollytelling story page

```
Plan first. Read the frontend-design skill if available, then implement MASTERSPEC section 11.4 (Scrollytelling story page).

- Route /story, and make / render it as the public landing (the working app stays at /quest, /walk, etc.; the Quest Board moves to /home). Update routes and the PWA start_url accordingly.
- Build the 9 scenes with sticky stages, an IntersectionObserver-driven --progress CSS variable per scene, and CSS scroll-driven animations where supported. No new animation library unless you justify it in writing and I approve.
- Art: inline SVG and CSS only (skyline/trees, route line drawing via stroke-dashoffset, phone outline, 7-branch skill tree). Propose 2 visual directions in text first and wait for my pick.
- Receipts scene reads evals/results.json and evals/field.md at build time via a small script (scripts/build_story_data.ts) that emits src/story/data.json; hide the scene when files are missing. No hand-typed numbers anywhere.
- prefers-reduced-motion: static stacked layout with final states visible. Skip link, semantic headings, alt text, audio captions.
- Perf: story-route JS <= 120 KB gzipped beyond the shell; animate only transform/opacity; report a measured Lighthouse performance score and a note on mid-range Android behaviour.
- Tests: component test that the Receipts scene hides with no data; a Playwright test that all scenes are reachable and that reduced-motion mode renders them statically.

Stop after summary with screenshots instructions.
```

## P9 — Quest flow + Walk Mode + screen-time

```
Plan first. Implement the core loop UI.

- Home → "Get a quest" → loading state ("The Dungeon Master is thinking…") → Quest Card (title, chips, briefing, objective, minutes, safety note; buttons Listen/Accept/Reroll(max 3/day)/Skip).
- Quest lifecycle state machine (idle → offered → accepted → verifying → completed) persisted to localStorage so it survives reloads and offline.
- Walk Mode: near-black minimal UI, elapsed timer (computed from accepted_at timestamp, so it survives backgrounding), big "I'm back" button, "Stop quest" link, repeat-audio button. Do NOT use wake lock.
- Screen-time tracker using the Page Visibility API: accumulate visible seconds between accept and complete; unit-test with fake timers and visibility events.
- Reward screen shows "Your screen was on for X% of this quest" (computed, never fabricated).
- All states: loading, error, offline, rate-limited, permission denied.

Acceptance: component tests for Quest Card and Walk Mode; a Playwright smoke test of generate → accept → walk → back using a mocked API. Stop after summary.
```

## P10 — Completion, XP, profile, memory

```
Plan first. Implement POST /v1/quests/{id}/complete, GET /v1/profile, PUT /v1/profile/settings, DELETE /v1/profile per MASTERSPEC §3.2, §6.4, §8.

- Server-side validation rules exactly as §6.4 (state machine, min elapsed, confidence ≥ 0.6, checkin distance ≤ 350 m halves XP, idempotency).
- XP calculator as a pure function with table-driven tests covering every multiplier and the cap; levels and streak logic (use the user's local date from request offset; document the approach).
- Write `completions`, upsert `memories` (embedding of "title — objective — category — place name"), update users.skills/total_xp/streak.
- DELETE /v1/profile removes all data for the device.
- Frontend: Reward screen with XP + level-ups, Profile with 7-category skill tree, Delete-my-data button.

Acceptance: tests pass; manually completing a fallback quest yields the exact XP the calculator predicts. Stop after summary.
```

## P11 — Gemma on-device verifier spike (Gate G2, time-box 3 hours)

```
Plan first. This is a time-boxed SPIKE on a separate branch (spike/gemma-verifier). Goal: decide if Gemma-3n can verify photos in the browser well enough to ship.

1. Read the current official docs for MediaPipe LLM Inference on Web and the Gemma-3n model cards. Report: required browser/WebGPU support, model file names/sizes, how the model is obtained (gated on Hugging Face? license acceptance?), and whether MediaPipe LLM Inference being in maintenance-only mode affects us. Propose 2 options for hosting/serving the model file and recommend one (do not upload anything).
2. Build a minimal page (apps/web/src/spike/GemmaVerify.tsx) that: feature-detects WebGPU, loads the model from VITE_GEMMA_MODEL_URL with progress UI and caching, takes a camera/file image, runs the prompt in prompts/verifier.gemma.txt, parses JSON robustly (model may add text; extract the first JSON object; default match=false on parse failure).
3. Create apps/web/spike/fixtures/ README describing the labelled photo set I should collect (≥ 30 photos incl. negatives) and a script to compute precision/recall/accuracy and latency per image.
4. Report honestly: works / works on desktop only / not viable, with measured load time, per-image latency, memory use if measurable.

Do not merge into main. Stop after the report and a recommendation for Gate G2.
```

## P12 — Verifier integration (only if G2 passed; otherwise implement fallbacks only)

```
Plan first. Integrate verification per MASTERSPEC §7.6 and §2.4.

- Verify screen: camera capture (just-in-time permission), "Checking on your device…" state, result with retake / claim.
- Opt-in "Install on-device verifier" with size warning, progress, resumable/cached download; never blocks the app.
- Fallback chain: Gemma → check-in (geolocation within 300 m) → honor mode (50% XP). Clear UI for each.
- Confirm in code AND a test that no image data is ever sent over the network (no multipart/base64 in any request; assert API client has no such method).
- Add an "airplane mode" explainer in the UI copy: verification works offline.

Acceptance: component tests with a mocked verifier; manual checklist in docs/DEPLOY.md for the airplane-mode test. Stop after summary.
```

## P13 — ElevenLabs voice + browser fallback

```
Plan first. Implement MASTERSPEC §6.5 /v1/tts and the client audio layer.

- Verify in the official ElevenLabs docs: TTS endpoint, current low-latency model id, output_format options, and the free-tier/hackathon usage terms; record in DECISIONS.md.
- POST /v1/tts {quest_id, kind: "briefing"|"hint"} → server fetches the quest text for that device (never accept arbitrary text from the client), enforces max 600 chars, per-device 20/hour, and a global daily character budget stored in the `usage` collection (TTS_DAILY_CHAR_BUDGET). Stream audio/mpeg. Never log text. Never expose the key.
- Client: "Listen" buttons; cache audio per quest id in Cache Storage/IndexedDB; on any error or budget exceeded → browser speechSynthesis with the same text. Always show the text.
- Pre-generate audio for 3 demo quests as static files in apps/web/public/demo-audio/ via a script (scripts/pregen_demo_audio.py) that I run manually.

Acceptance: tests with mocked ElevenLabs (success, 401, 429, timeout, budget exceeded); fallback path tested. Stop after summary.
```

## P14 — Training data pipeline (Tinker) — Day 3

```
Plan first. Implement MASTERSPEC §10.3 in training/.

IMPORTANT: Read the current Tinker docs (tinker-docs.thinkingmachines.ai) and the Tinker Cookbook before writing any Tinker code. Do not guess the SDK. Report which small instruct models are currently supported and their pricing; recommend 2 candidates for Gate G1 (consider license, GGUF/llama.cpp support, CPU latency).

Build:
1. training/make_contexts.py: sample contexts from the seeded `places` export (dump with a script) with area-based train/val/test split (3000/100/120) and the edge-case mix in §10.3; deterministic seed; writes JSONL.
2. training/gen_teacher.py: generate target quests with the strongest open-weight teacher available via Tinker sampling (or another open model I approve). Use the production system prompt (prompts/quest_master.system.txt) in the training format. Record teacher identity and settings in training/runs/RUNS.md. Check the teacher model's terms regarding training other models; report.
3. training/filter.py: filter with the production validators (import from apps/api/app/validators), dedupe by embedding similarity, balance categories/personas/rarity; print dataset stats.
4. training/make_recap_examples.py for the Chronicler (~400 examples) with recap validators.
5. Dry run on 20 examples only. Do NOT launch any paid generation or training at scale until I approve the cost estimate you present.

Acceptance: unit tests for filters; a stats report (counts per persona/category/rarity, rejection reasons). Stop after summary and the cost estimate.
```

## P15 — Tinker SFT run

```
Plan first. After I approve the cost estimate: implement training/train_sft.py using the Tinker SDK/Cookbook patterns you verified in the docs.

- Config in training/configs/sft.yaml (base model string, LoRA rank, learning rate, epochs, batch size, seed). Start from Cookbook defaults; support an LR sweep of 3 values.
- Log run IDs and metrics to training/runs/RUNS.md automatically.
- Track val loss and validator pass-rate on val samples generated by the checkpoint.
- Save the best checkpoint/adapter reference. Document exactly how to download the weights per the docs.

Do not start a run until I say "go". When I do, run the smallest sensible run first (small data subset, 1 epoch) to validate the pipeline, show me the metrics, and wait. Stop after summary.
```

## P16 — Eval harness (baseline vs tuned) — this makes or breaks the Tinker claim

```
Plan first. Implement MASTERSPEC §10.6 as training/eval.py, writing evals/results.json and evals/results.md.

- Inputs: endpoint URL + model label. Runs the 120 test contexts with: (A) baseline = base model, same quantization, best-effort prompt with 3 few-shot examples; (B) tuned = zero-shot with the short production system prompt. Run both WITHOUT grammar-constrained decoding for headline numbers, and WITH grammar for the shipped config.
- Metrics exactly as the table: JSON validity, grounding, constraint adherence, safety lint, Full pass, diversity (embedding-based), prompt tokens, latency (p50/p95), tokens/s.
- Voice preference: implement an LLM-judge pairwise comparison using a different model family than the tuned model; also output 20 random pairs to evals/human_pairs.csv for me to rate by hand. Report both and note judge bias.
- Print 5 best and 5 worst failure examples per arm.
- The script must be reproducible (seeded) and must refuse to run if the served model's reported identity doesn't match the label I pass.

Acceptance: a dry run against any local/mock endpoint prints a complete results.md with placeholder-free structure; no number is ever hand-typed. Stop after summary.
```

## P17 — Export, quantize, deploy tuned model (Gate G3)

```
Plan first. Write docs/MODEL_EXPORT.md and scripts to: download the tuned adapter (per verified Tinker docs) → merge into the base with PEFT merge_and_unload → save safetensors → convert with llama.cpp convert_hf_to_gguf.py → quantize Q4_K_M → upload to a PUBLIC Hugging Face repo with a model card (base model + license, training summary, link to repo, intended use, limitations) → compute SHA-256 → set MODEL_URL/MODEL_SHA256 for sqm-llm.

Do not run anything that uploads or spends money without my approval. Add MODEL_SHA256 verification to services/llm/entrypoint.sh. Then give me the exact steps to redeploy sqm-llm and re-run training/eval.py against the SERVED quantized model so results reflect what ships. Stop after summary.
```

## P18 — Chronicler (weekly recap)

```
Plan first. Implement MASTERSPEC §7.7 and §3.3.

- prompts/chronicler.system.txt per spec (+ hash file update).
- POST /v1/recap/weekly: gather last 7 days of completions; call the LLM (same endpoint); validate (word range 180–260, all named places must appear in input, banned lint, JSON schema); on failure, deterministic template recap from stats.
- Store in `recaps`; idempotent per week.
- Frontend Chronicle screen with Listen button (uses /v1/tts with kind "recap" — extend TTS endpoint to read recap text server-side), plain-text share.

Acceptance: tests including hallucinated-place rejection and fallback recap. Stop after summary.
```

## P19 — Sentry agent tracing polish

```
Plan first. Complete MASTERSPEC §13.

- Verify the current Sentry conventions for AI/agent monitoring (span ops/attributes such as gen_ai.*) and adopt them; document in DECISIONS.md.
- Ensure every /generate and /recap trace shows: context.build, scout.search, memory.check, llm.call (model, input/output tokens, latency), validators (failure ids), fallback; tags source/retry.
- Frontend @sentry/react with low sampling and PII off; filter out permission-denied noise.
- Add a README section "How I debugged with traces" as a template; I will fill in the real story after I see a real trace.
- Add a test that Sentry before_send scrubs lat/lng and device ids.

Acceptance: local run with a test DSN (mock transport) shows expected spans in a unit test. Stop after summary.
```

## P20 — Safety red-team + security pass

```
Plan first. Run an adversarial review.

1. Expand apps/api/tests/redteam_cases.json to ≥ 80 cases (dangerous interests, stalking-like prompts, night/isolated, weather extremes, prompt injections in interests and in place names from OSM, extremely long names, unicode confusables). Run the full pipeline with the mocked LLM returning adversarial outputs AND with the real tuned model if available; report any unsafe quest that passes validators and fix the validators (do not weaken them).
2. Security checklist: CORS, body limits, rate limits, dependency audit (pip-audit, npm audit), secret scan of the repo and git history (e.g., gitleaks if available), headers on the static site, no keys in the bundle (grep the build output for key-like strings).
3. Privacy checklist per MASTERSPEC §9.3: confirm no raw coordinates stored; no image endpoints; logs scrubbed. Write results to docs/SECURITY.md as a table (item, evidence, status).

Stop after summary with anything that needs my decision.
```

## P21 — Field-test tooling

```
Plan first. Add a minimal, privacy-preserving way to record field-test results for the post.

- A hidden /settings/export page that downloads a CSV of MY completions only: date, category, rarity, est_minutes, elapsed_seconds, screen_seconds, screen_share, verification_method, source (llm/fallback). No coordinates.
- scripts/summarize_field.py: reads CSV(s) → prints n quests, total minutes outside, median/p90 screen share, % voice-first (if tracked), % fallback quests.
- Writes evals/field.md.

Acceptance: test with synthetic CSV. Stop after summary.
```

## P22 — README, deploy hardening, release

```
Plan first. Produce the public README.md and finalize deployment docs.

- README: what/why-open (use only claims in the claims ledger; leave TODO markers for unverified ones), architecture diagram (Mermaid), quickstart (local), deploy to Render (button + env var table), safety/privacy summary, honest limitations, license, credits (OSM attribution, Open-Meteo, models + licenses, partners used).
- docs/DEPLOY.md final: step-by-step, env vars, post-deploy URL fixups, smoke test, cost notes, how to pause/delete services after judging.
- Verify `render.yaml` once more against the Blueprint spec; run smoke tests against the deployed URLs and report results.
- Check licenses of all dependencies/models used and list them in docs/LICENSES.md.

Do not commit anything containing secrets. Stop after summary.
```

## P23 — Post drafting with DevRelay (Day 7)

```
Using DevRelay, create a DEV draft (published: false) for the Touch Grass challenge. Inputs: PROJECTPLAN.md §8 (structure, claims ledger, writing rules), evals/results.md, evals/field.md, README.md, docs/DECISIONS.md. Rules: use only claims backed by an artifact; label estimates; include honest failures and what's closed vs open; explain why open innovation mattered and where it beat a closed approach AND where it didn't; embed my saved agent sessions; mark AI-assisted. Show me the full draft here. Do not publish, enter, or submit anything.
```

---

## Utility prompts

**U1 — Session close (use at the end of every session)**
```
Close this session: (1) run the full test suite and report; (2) list files changed and why; (3) append decisions, verified facts and open questions to docs/DECISIONS.md; (4) update CLAUDE.md commands if any changed; (5) suggest the commit message(s); (6) tell me the next task from PROJECTPLAN.md. Then, using DevRelay, save this agent session and give me the link. Do not publish anything.
```

**U2 — Debug with evidence**
```
Debug this issue. First reproduce it and show the exact error/trace. List 3 hypotheses ranked by likelihood with a cheap test for each. Check the Sentry trace/logs if available. Make the smallest fix, add a regression test, and explain the root cause in 3 sentences. Don't refactor unrelated code.
Issue: <paste the error without secrets>
```

**U3 — Spec drift check**
```
Compare the current code against MASTERSPEC.md section by section (§5 data model, §6 API, §7 agents, §8 game rules, §9 safety/privacy, §12 Render). Output a table: requirement → status (match / drift / missing) → file:line evidence. Do not change anything. Then propose, for each drift, whether the code or the spec should change and why.
```

**U4 — Claims audit (run before submitting)**
```
Audit every factual claim in README.md and the draft post against the repo. For each claim: quote it, point to the artifact (file, eval output, screenshot name, trace) that supports it, or mark UNSUPPORTED. Flag any number that doesn't match evals/. Flag wording that implies "fully offline", "no server sees your data", or "open-source stack" where closed services are involved. Output a table and a list of required edits.
```

**U5 — Cost check (before any spend)**
```
Before running anything paid, list: each billable action (Tinker generation/training, ElevenLabs characters, Render instance-hours/disk, Atlas tier), the estimated quantity, the estimated cost using CURRENT official pricing pages (cite them), and the cheaper alternative. Wait for my approval.
```

**U6 — Review my diff like a skeptical senior engineer**
```
Review the staged diff. Look for: spec violations, safety/privacy regressions, missing tests, hidden coupling, error handling gaps, accessibility issues, secrets, and anything that would break when the LLM service is down. Rank findings by severity. Don't fix until I choose which ones.
```

**U7 — Last-mile polish for the demo**
```
Do a demo-readiness pass on the deployed app: list the exact click path for the 90-second demo (PROJECTPLAN §10), time each step, identify the slowest step and the three most likely failure points, and propose fixes (prefetching, cached demo quest, pre-generated audio). Implement only the fixes I approve.
```
