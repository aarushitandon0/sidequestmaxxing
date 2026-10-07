# PROJECTPLAN.md — Sidequestmaxxing

> Companion to `MASTERSPEC.md` (the *what*). This file is the *when/how*: schedule, gates, risks, post outline, submission checklist.
> **Day 0 task #1:** find the real deadline (ask DevRelay: "What's the submission deadline for the current DEV Touch Grass challenge, and what does the submission need?"). Then compress or stretch the 7-day plan below. Today's reference date: 2026-10-07.

---

## 1. Strategy in one paragraph

Writing quality is the most heavily weighted criterion, then theme relevance, creativity, technical execution. So: **build a small, real, polished loop; go outside and use it; measure honestly; write a great story.** The tech stack is chosen to produce *evidence* for the post: Tinker gives a measured improvement, Gemma gives a privacy claim you can prove, Render gives a clean deployable architecture, ElevenLabs makes the "phone in pocket" promise real, Atlas makes quests personal, Sentry shows the work.

## 2. Scope tiers

| Tier | Contents | Rule |
|---|---|---|
| **P0 (must demo)** | Deployed on Render (web+api+llm); quest generation (LLM + fallback); places via Atlas vector search; Walk Mode; completion + XP; voice briefing (ElevenLabs or browser fallback); 3 real outdoor runs | Without these there is no project |
| **P1 (must to win)** | Tinker fine-tune with honest eval; Gemma on-device photo verification; Chronicle; Sentry traces; screen-share metric; polished UI; strong post | These create the "open-source mattered" proof |
| **P2 (stretch)** | Local `docker compose` mode (fully on laptop); squads/co-op quests; map view; RL stage on validators; Temporal/Mastra | Only after P1 is done and the post draft exists |

## 3. Decision gates (stop and decide; write the result in the Decisions Log, section 9)

| Gate | When | Question | If NO |
|---|---|---|---|
| **G0** | Day 0 | Do we have access to Render paid plan/credits, Atlas, Tinker, ElevenLabs, Sentry? | Drop the category; do not block the build. Tinker missing → fine-tune elsewhere (Unsloth/Colab) and drop the Tinker prize claim |
| **G1** | Day 2 | Which model size runs at p50 ≤ 15 s on the chosen Render plan with ≥ 1 GB RAM headroom? | Smaller model or bigger plan; if neither, ship fallback-first with LLM as enhancement |
| **G2** | Day 2–3 (time-box 3 h) | Does Gemma-3n verify photos on a real phone/laptop in the browser acceptably? | Ship check-in/honor modes; keep Gemma as "desktop beta"; adjust claims |
| **G3** | Day 4 | Did tuned beat baseline by ≥ 10 pts on Full pass (raw decoding)? Does the quantized GGUF still win? | Report honestly; keep best model; consider prompt-only baseline as the shipped model |
| **G4** | Day 6 | Feature freeze: is P0+P1 demoable end-to-end? | Cut P1 items in the order in section 7 |

## 4. 7-day schedule

> Each day ends with: commit, deploy to Render, update `docs/DECISIONS.md`, save the Claude Code session via DevRelay (see DEVRELAY.md).

### Day 0 — Setup (≈ 2–3 h)
- [ ] Create accounts/keys: Render, MongoDB Atlas (M0 cluster, DB `sqm`), Tinker, ElevenLabs, Sentry (backend+frontend projects), Hugging Face (token; accept Gemma + chosen model terms), GitHub repo (public).
- [ ] Install DevRelay and Claude Code; verify (DEVRELAY.md).
- [ ] Check challenge deadline/rules and DevRelay sponsor offers (Render, ElevenLabs, MongoDB credits).
- [ ] Put `MASTERSPEC.md`, `PROJECTPLAN.md`, `CLAUDE.md` in repo root; `docs/` for the rest.
- [ ] Choose demo city + bounding box (your own city is ideal; you must be able to test outdoors there).
- **Done when:** repo exists with docs, all keys stored in a password manager (not in chat), `.env.example` drafted.

### Day 1 — Walking skeleton, deployed
- [ ] Scaffold monorepo (`apps/web`, `apps/api`, `services/llm`, `prompts`, `training`, `scripts`).
- [ ] API: `/healthz`, config, Pydantic models, Sentry init, CORS, rate limits.
- [ ] Web: PWA shell, routing, API client, design tokens, Home screen.
- [ ] `render.yaml` with web + api (llm placeholder). **Deploy to Render today.** Fix URL suffix gotcha.
- [ ] Atlas: connect, create collections/indexes; seed script fetches OSM places for the demo bbox, embeds, upserts; create vector index.
- **Done when:** the public Render URL loads the PWA, calls `/healthz`, and `/v1/places/near` returns real places.

### Day 2 — Quest engine (deterministic first) + LLM service
- [ ] Context Builder, Scout, validators V1–V12 (unit-tested), fallback engine.
- [ ] `/v1/quests/generate` end-to-end using fallback engine only. Frontend Quest Card + Accept.
- [ ] `sqm-llm` private service with a **base** instruct GGUF; Quest Master client with JSON schema; retry + fallback wiring. Measure latency → **Gate G1**.
- [ ] Start **Gemma spike (time-boxed 3 h)** in a separate branch → **Gate G2**.
- **Done when:** generating a real quest works with LLM on, and with the LLM service stopped.

### Day 3 — Training data + frontend core
- [ ] `training/`: make_contexts, gen_teacher, filter, dataset stats. Launch SFT on Tinker (long-running — do other work meanwhile).
- [ ] Frontend: Walk Mode, screen-time tracker, accept/complete flow, profile + XP.
- [ ] `/accept`, `/complete`, XP calculator, `memories` upsert and memory-aware Scout.
- **Done when:** a full fake-verified quest loop works on a phone against the deployed API.

### Day 4 — Eval, export, deploy tuned model
- [ ] Run eval harness: baseline vs tuned (raw decoding) on the 120 test contexts; also with grammar.
- [ ] Merge → GGUF → quantize → upload to HF → set `MODEL_URL` → redeploy `sqm-llm` → re-run eval **on the served quantized model** → **Gate G3**.
- [ ] Integrate Gemma verifier (if G2 passed) behind opt-in.
- **Done when:** `evals/results.md` has real numbers and the fine-tuned model is serving.

### Day 5 — Voice, Chronicle, polish
- [ ] ElevenLabs `/v1/tts` proxy + budget guard + client cache + browser fallback; "Listen" buttons; demo audio pre-generated.
- [ ] Chronicler endpoint + screen.
- [ ] Skill tree UI, reward animation, safety copy, empty/error states, PWA install polish.
- [ ] Scrollytelling story page (prompt P8b); build the shell on Day 3-4, wire real eval/field data on Day 6.
- [ ] Sentry spans complete; capture trace screenshots.
- **Done when:** a tester can complete a quest using mostly audio.

### Day 6 — Go outside (the most important day) + freeze
- [ ] Field test: do ≥ 3 real quests yourself, ideally 3–5 friends do 1 each. Record screen-share numbers and any failures/photos/video (with consent).
- [ ] Fix top 5 issues found outside. **Feature freeze (Gate G4).**
- [ ] Red-team safety set run; `pip-audit`/`npm audit`; remove secrets from history; README with run instructions.
- [ ] Record demo video (60–90 s) + take screenshots (Render, Atlas, Sentry, Tinker).
- **Done when:** you have real photos/numbers and a working deployed URL.

### Day 7 — Write and submit
- [ ] Draft the post using DevRelay (as a DEV draft), edit heavily in your own voice.
- [ ] Embed saved agent session(s). Add diagrams, tables, results, honest limitations, run-it-yourself section.
- [ ] Proofread (read aloud). Check all links, images, alt text, tags.
- [ ] Submit via the official flow; enter the partner categories you truly used.
- [ ] Buffer: ≥ 3 h for surprises.

## 5. Task acceptance criteria (excerpt; the full list lives in MASTERSPEC §14)

| Task | Acceptance |
|---|---|
| Seed places | ≥ 150 named places in demo bbox; vector search returns relevant results for "birds", "history", "street food" |
| Fallback engine | 100 random contexts → 100 valid quests; 0 validator failures |
| LLM client | Invalid JSON/timeout never surfaces as an error to the user |
| Walk Mode | Works offline after quest loaded; elapsed time survives app backgrounding |
| Complete endpoint | Idempotent; rejects early completion; XP matches table |
| Gemma verifier | On the labelled test set (≥ 30 photos incl. negatives): report precision/recall honestly |
| TTS | Budget guard stops at limit; browser fallback works; no key in browser bundle |
| Eval | `evals/results.md` generated by script, reproducible, includes failure examples |

## 6. Risk register

| # | Risk | Likelihood | Impact | Mitigation | Trigger → action |
|---|---|---|---|---|---|
| R1 | CPU inference too slow on Render | Med | High | Smaller model; shorter outputs; `max_tokens 380`; prefetch quest on app open; fallback engine | G1 fail → smaller model/bigger plan |
| R2 | Gemma-3n in-browser fails on phones | **High** | Med | Time-boxed spike; opt-in; check-in/honor fallback; position as "desktop/high-end beta" | G2 fail → keep as optional |
| R3 | No Tinker access/credits | Med | Med | Check Day 0; fallback to Unsloth/Colab (lose Tinker prize) | G0 |
| R4 | Fine-tune doesn't beat baseline | Med | Med | Strong validators in data filter; improve data before tuning more; report honestly | G3 |
| R5 | Render cost/disk requirement | Med | Med | Check pricing/credits Day 0; delete idle services after judging | G0 |
| R6 | Overpass rate limiting | Low | Med | Seed once, cache per cell, commit a snapshot JSON | — |
| R7 | Safety incident / bad quest | Low | **Severe** | Validators, banned lint, red-team tests, public places only, safety_note, stop button | any failing red-team case blocks release |
| R8 | ElevenLabs credits burn | Med | Low | Per-device + global budget, pre-generated demo audio, browser fallback | budget ≥ 80% → disable |
| R9 | Secrets leaked in repo/session | Low | High | `.env` gitignored, never paste keys in Claude sessions, secret scan before publish | rotate keys immediately |
| R10 | Run out of time | **High** | High | Walking skeleton Day 1; cut order (section 7) | G4 |
| R11 | Weather/ability to go outside on test day | Med | Med | Indoor-capable quests (museum/market/library), do field tests on 2 different days | — |
| R12 | Claims in post exceed evidence | Med | **High** (writing score, trust) | "Claims ledger" (section 8.3): every claim maps to an artifact | before submit |

## 7. Cut order if time runs out (cut from the top first)
1. Squads / map / RL stage / local compose (P2)
2. Legendary quests, reroll limits, titles flavour
3. Chronicle voice (keep text)
4. Gemma verifier (fall back to check-in/honor; reword claims)
5. Sentry frontend (keep backend traces)
6. Memory-aware repeats (keep simple recent-category filter)
**Never cut:** Render deployment, fallback engine, safety validators, real outdoor testing, honest eval, the post.

## 8. The post (this is 40%+ of the score)

### 8.1 Working title ideas
- "I built a Dungeon Master that makes me leave the house (and it runs on a CPU)"
- "Sidequestmaxxing: open-weight AI that gets out of your way so you can go outside"

### 8.2 Structure (aim 1,400–2,000 words; scannable; honest)
1. **Hook (real moment):** one specific outdoor anecdote from field testing (what the DM asked, what happened, what you noticed). Open with the story, not the tech.
2. **The idea in 3 sentences + 20-second demo GIF/video.**
3. **The rule that shaped everything:** "the screen must be the shortest part." Show the screen-share numbers.
4. **How it works:** one architecture diagram; 3 short paragraphs (quest generation, voice, on-device verification).
5. **Why open mattered (the proof section):** a compact table — claim → evidence:
   - *Behaviour changed by tuning* → Tinker baseline-vs-tuned table.
   - *Privacy by architecture* → photo never uploaded (airplane-mode test), what the server does see.
   - *Swap/serve anywhere* → same GGUF on Render CPU; (if P2) on laptop.
   - *Cost* → measured tokens/s, estimated $/quest (labelled estimate).
   - *Open data* → OSM/Open-Meteo, no per-call fees.
6. **Where closed tools helped (and fallbacks):** Render, Atlas, ElevenLabs, Sentry. Name them as partners used, with one concrete benefit each.
7. **What went wrong:** 2–3 honest failures (e.g., Gemma on a phone, a weird quest the validators caught, a Sentry trace that revealed a bug).
8. **Safety and privacy decisions:** short, concrete.
9. **Results from the field:** n quests, minutes outside, median screen share, tester quotes (with permission).
10. **Run it yourself:** repo link, `render.yaml` deploy button, env vars list.
11. **Show your work:** embedded DevRelay agent session(s) and a few prompts that mattered.
12. **What's next.**

### 8.3 Claims ledger (fill before writing; delete any claim without an artifact)
| Claim | Artifact (file/screenshot/trace/link) | Verified on (date) |
|---|---|---|
| Tuned model beats baseline by X pts | `evals/results.md` | |
| Photos never leave the device | network log screenshot + code ref | |
| Runs on CPU on Render | latency table + Render screenshot | |
| Median screen share Y% | `evals/field.csv` | |
| Voice quest works with phone in pocket | video | |

### 8.4 Writing rules
- First person, specific, no hype words ("revolutionary", "seamless").
- Every number has a source. Say "n=…" and label estimates.
- Short paragraphs, descriptive headings, alt text on images, code blocks only where they teach.
- Use DevRelay to produce the *draft*; then rewrite in your own voice. Keep the AI-assisted disclosure DevRelay adds.
- Required: explain **why open innovation matters for this build** (the prompt asks for it) — and where open worked **better than** a closed approach, plus where it didn't.

### 8.5 Required tags/format
Follow the challenge template exactly **[VERIFY from the challenge page]** (title format, tags, category callouts for partners used, cover image).

## 9. Decisions log (append as you decide)
| Date | Decision | Reason | Evidence |
|---|---|---|---|
| | Demo city/bbox | | |
| | Base model + size (G1) | | |
| | Gemma hosting approach (OQ-1) | | |
| | Voice id/model | | |

## 10. Demo script (90 seconds)
1. (0–10 s) Phone in hand, open PWA, tap **Get a quest**.
2. (10–25 s) DM voice speaks the quest; show quest card briefly; **Accept**; phone into pocket.
3. (25–55 s) B-roll outside doing the quest.
4. (55–70 s) Photo → "Checking on your device" (airplane-mode badge) → reward screen with **"screen on for 4%"**.
5. (70–85 s) Cut to Sentry trace + Render dashboard + eval table (3 seconds each).
6. (85–90 s) Tagline: **"Your city is the game. Your phone is just the quest log."**

## 11. Submission checklist
- [ ] Public repo with README (what, why open, architecture, run locally, deploy to Render, env vars, safety/privacy notes, license).
- [ ] Deployed URL working (3 Render services healthy).
- [ ] Post published with required tags; partner categories entered only where genuinely used.
- [ ] Agent session(s) embedded/linked; no secrets inside (reviewed).
- [ ] Demo video + screenshots with alt text.
- [ ] Claims ledger fully verified.
- [ ] Keys rotated if ever exposed; budgets/limits set on ElevenLabs and Atlas.
- [ ] After judging: pause/delete paid Render services to stop charges.
