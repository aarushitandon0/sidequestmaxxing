# DECISIONS.md — Sidequestmaxxing

Living log of open questions, decisions and verified facts. Append; don't rewrite history.
Sources that could not be reached from the build session are marked **(unverified — blocked)**.

---

## P0 orientation summary (2026-10-07)

1. Sidequestmaxxing is a mobile-first PWA that turns the player's neighbourhood into real-world side quests.
2. An open-weight "Dungeon Master" LLM (small Qwen-class model, LoRA-tuned on Tinker, served as a Q4_K_M GGUF by llama.cpp) writes one quest grounded in a real nearby place.
3. Places come from OpenStreetMap (Overpass), embedded with BGE-small (fastembed, CPU) and searched with Atlas Vector Search, filtered by geohash cells and distance.
4. A deterministic Context Builder adds time, daylight and Open-Meteo weather; the Scout picks ≤ 8 safe candidates and avoids recent themes using per-device memories.
5. Every LLM output goes through validators V1–V12; on failure, one retry, then a deterministic fallback engine — so `/v1/quests/generate` works with the LLM down.
6. The server owns ids, rarity and XP; the LLM owns only creative fields.
7. The briefing is spoken (ElevenLabs via a server proxy, browser speech fallback); then Walk Mode keeps the screen dark and tracks screen share.
8. Verification happens on-device (Gemma 3n via MediaPipe/WebGPU); photos never leave the phone; check-in and honor fallbacks exist.
9. Everything runs on Render: a static site (`sqm-web`), a FastAPI Docker service (`sqm-api`) and a private llama.cpp service with a disk (`sqm-llm`); Sentry traces each agent step.
10. The post's evidence comes from scripts: Tinker baseline-vs-tuned eval, field-test screen-share numbers, latency/cost on Render.

---

## Open Questions

### Challenge / process
- **OQ-C1** Deadline, submission template, required tags, multi-category eligibility, whether a live URL is required. → DevRelay `get_challenges` or the challenge page. (Spec §15.9) **Needs the user: DevRelay cannot run in the cloud build container (see Decisions D-2).**
- **OQ-C2** Sponsor credits for Render / ElevenLabs / Atlas / Sentry / Tinker. → DevRelay `list_event_offers`, partner free-tier pages.
- **OQ-C3** Demo city + bounding box (needed for `seed_places.py` and the outdoor tests). The spec's examples use Pune (18.520, 73.856) — confirm.

### Tinker / models (Spec §15.1, §15.11)
- Supported small instruct models + pricing, SDK API, weight download/export. → https://tinker-docs.thinkingmachines.ai
- Exact base model + license (Qwen3-4B-Instruct-2507 or similar, Apache-2.0?). → Hugging Face model card.
- Teacher-model terms for synthetic training data.

### Gate G1 — base model choice (P6; **needs the user**)
Memory = GGUF file + KV cache (f16, `-c 2048`) + ~0.3 GB runtime/compute buffers. Rule (§10.2): total ≤ instance RAM − 1 GB.
KV per token = 2 × layers × kv_heads × head_dim × 2 bytes. File sizes are approximate Q4_K_M sizes — **check the exact file on Hugging Face before choosing** (blocked from this container).

| Option | Layers / KV heads / head dim | KV @ 2048 | Q4_K_M file | ≈ Total | Fits (−1 GB) | License |
|---|---|---|---|---|---|---|
| A. Qwen3-4B-Instruct-2507 | 36 / 8 / 128 | 0.30 GB | ≈ 2.5 GB | ≈ 3.1 GB | Pro Plus (8 GB); Pro (4 GB) is ~0.1 GB over the rule | Apache-2.0 |
| B. Qwen3-1.7B | 28 / 8 / 128 | 0.23 GB | ≈ 1.1 GB | ≈ 1.6 GB | Pro (4 GB); not Standard (2 GB) | Apache-2.0 |
| C. Llama-3.2-3B-Instruct | 28 / 8 / 128 | 0.23 GB | ≈ 2.0 GB | ≈ 2.5 GB | Pro (4 GB) | Llama 3.2 Community License (not OSI open) |

Trade-off: A gives the best quests but is the slowest on CPU (more weights to stream per token) and needs Pro Plus to respect the 1 GB headroom (or Pro with `CTX_SIZE=1536`, which halves headroom risk but must be measured). B is fastest and cheapest but needs the fine-tune to carry more of the quality. Qwen3-1.7B is a hybrid thinking model: we already send `enable_thinking: false`. Latency must be **measured** with `scripts/bench_llm.py` — no estimate is recorded here. Tinker availability of each base is still OQ (Tinker docs).

### Gate G2 — on-device verifier (P11; **needs a WebGPU device**)
- Not measurable in the build container (headless Chromium, no WebGPU, Hugging Face blocked). Load time, per-image latency, memory, precision/recall: **unmeasured**.
- Run it: `apps/web/spike/fixtures/README.md` (≥ 30 labelled photos → `/spike/gemma` → `spike/score.ts` → `evals/gemma_spike_<ts>.json`).
- Honest expectation to verify: ~3 GB E2B web model suggests desktop Chrome / high-end Android only; mid-range phones will likely use check-in/honor. Gate G2 passes if accuracy ≥ ~80% with p50 ≤ ~10 s on at least one realistic device; otherwise ship fallbacks only and reword claims.
- Decide model hosting (D-48) and whether to add a `NOTICE`/Gemma terms link if we host it.

### Gemma / MediaPipe (Spec §15.2, §15.3)
- Gemma-3n `.litertlm` web model: gated? download size? how to host (OQ-1). → https://ai.google.dev/edge/mediapipe/solutions/genai/llm_inference/web_js , https://huggingface.co/google
- MediaPipe LLM Inference maintenance mode impact; WebGPU on target phones.

### llama.cpp (Spec §15.4)
- Chat template for the chosen model; `--jinja` default; thinking-mode off. → https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md (partly verified, see below)

### Render (Spec §15.5)
- Instance RAM/pricing per plan; private service + disk availability per plan; credits. → https://render.com/pricing **(unverified — blocked)**
- Run `render blueprints validate` (Render CLI ≥ 2.7.0) on `render.yaml` before first deploy.

### ElevenLabs (Spec §15.6)
- TTS endpoint, low-latency model id, `output_format`, free-tier terms, voice licensing. → https://elevenlabs.io/docs/api-reference/text-to-speech

### Atlas (Spec §15.7)
- Creating vector indexes via the driver on M0 (`create_search_index` with `type="vectorSearch"`); M0 limits on search-index count. → https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-type/ **(unverified — blocked; `create_indexes.py` falls back with a printed JSON definition for the Atlas UI if driver creation fails)**

### Sentry (Spec §15.8)
- `gen_ai.*` span op names / AI agent monitoring conventions. → https://docs.sentry.io/platforms/python/tracing/span-metrics/ (deferred to P19)

### Data sources (Spec §15.10)
- Overpass fair-use, Open-Meteo terms, OSM tile policy at expected traffic. → https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances , https://open-meteo.com/en/terms

### Spec ambiguities found in P0 (need a decision; current implementation choice in brackets)
- **A1 Check-in radius:** §2.4 says 300 m, §6.4 says 350 m. [Use 350 m server-side (§6.4); UI copy says "about 300 m".]
- **A2 Min elapsed:** §6.4 `elapsed_seconds ≥ min(0.4×est×60, 240)` caps the requirement at 4 minutes. Probably intended — flag only. [Implement as written in P10.]
- **A3 Legendary rarity:** "only offered if user opts in big quest day", but the request schema has no opt-in field. [P7: legendary never offered for now (D-35). To enable: add optional `big_quest_day: bool = false` → needs approval since it changes the API contract.]
- **A4 indoor_only daylight rule (§7.1):** uses "est window", which isn't known at context time. [Resolved in P5, see D-25: `indoor_only` when `daylight_minutes_left < 35`; per-place daylight via Scout + V10.]
- **A5 Banned-term lint (§9.2) needs word boundaries:** naive substring matching rejects "diverse" (dive), "driveway"/"drive-in" (drive), "the edge of the park" (edge of). [Word-boundary regexes; `drive` matched as a verb form (`drive`, `driving`, `drove`) but "driveway" allowed; `edge of` kept as written — it's strict but safe. Tests document each.]
- **A6 V12 (near-duplicate) is not pure** — it needs embeddings. [Validator takes precomputed vectors; the caller embeds.]
- **A7 `DELETE /v1/profile`** appears in §9.3 but not the §6.1 table. [Implemented in P10 (D-44); §6.1 updated.]
- **A8 Overpass lazy fill** (§7.2 "never fetch per user request more than once per cell per 24 h") vs seed-only. [P3 implements seed-only; lazy fill is P2-stretch.]
- **A9 Prompt (§7.3) says briefing < 60 words; V7 allows ≤ 70.** Intentional slack — fine.

---

## Decisions

| ID | Date | Decision | Reason |
|---|---|---|---|
| D-1 | 2026-10-07 | User instruction overrides CLAUDE.md "plan first / one task per session": build P0–P5 in one session, one commit per prompt, then push to `claude/quirky-ptolemy-hweqo7`. | Explicit user request in chat. |
| D-2 | 2026-10-07 | DevRelay is **not** installed in the cloud build container: `devrelay.com` is blocked by the environment's egress policy, and first use needs an interactive MLH browser sign-in. The user installs it locally per `docs/DEVRELAY.md`. The npm package named `devrelay` is unrelated and must not be installed. | Proxy 403 on `devrelay.com`; npm package metadata. |
| D-3 | 2026-10-07 | `docs/DEVRELAY.md` and `docs/CLAUDE_CODE_PROMPTS.md` moved into `docs/` per CLAUDE.md repo layout. | Layout consistency. |
| D-4 | 2026-10-07 | Mongo driver: **PyMongo Async API (`AsyncMongoClient`)**, not Motor. | Motor is deprecated in favour of PyMongo's native async API; one less dependency. |
| D-5 | 2026-10-07 | Geohash neighbours via `pygeohash.get_adjacent` (v3.x). | Already in the stack; avoids hand-rolled base32 maths. |
| D-6 | 2026-10-07 | Property tests use seeded `random` loops, not Hypothesis. | No new dependency (CLAUDE.md "ask before adding dependencies"). |
| D-7 | 2026-10-07 | Dev-only deps added: `pytest-cov` (P4 asks for a coverage report), `ruff`, `mypy`. Runtime deps are exactly the §4 stack. | P4 acceptance needs coverage. |
| D-8 | 2026-10-07 | Web tests use **Vitest** + Testing Library; lint via ESLint flat config. | Standard Vite toolchain; `npm run test` required by CLAUDE.md. |
| D-9 | 2026-10-07 | `services/llm/Dockerfile` no longer apt-installs curl: the upstream `server` stage already installs `curl` (base stage) and ships a `HEALTHCHECK` using it. | Verified in `.devops/cpu.Dockerfile`. |
| D-10 | 2026-10-07 | Interests sanitizer: NFKC → strip control/format chars → lower → keep letters/digits/space/`-` → ≤ 24 chars; **drop** any item containing instruction-like words (`ignore`, `system`, `prompt`, `json`, `you are`, …) instead of passing it on. Over 6 items is a 422, not a silent truncate. | §6.3 "free text never goes straight into a prompt"; a dropped hobby costs little. |
| D-11 | 2026-10-07 | `X-Device-Id` must be a UUID **v4** (v1 rejected — it embeds MAC/time). | §9.3 privacy. |
| D-12 | 2026-10-07 | slowapi uses in-memory storage keyed by device id (fallback: client IP). Valid only while `sqm-api` runs one instance. | Simplest thing for a single starter instance. |
| D-13 | 2026-10-07 | Validation errors list field names only, never submitted values; logs carry route template, never query strings. | §9.3 no coordinates/free text in logs. |
| D-14 | 2026-10-07 | Added `library` to the place `kind` enum (§5.1) — §7.2 already fetches `amenity=library`. Fixed the §5.1 example `cell5` (`te7ud` → `tek3r`, computed for Vetal Tekdi). | Spec consistency. |
| D-15 | 2026-10-07 | `memories_vec` gets a second filter field `ts` (§5.5 updated) so the memory check pre-filters to the last 14 days. | Cheaper and more accurate than post-filtering. |
| D-16 | 2026-10-07 | OSM kind mapping: `natural=wood` and `tourism=attraction` → `other`; museum/library/cafe are `indoor`; `needs_daylight = !indoor && lit != yes`; prefer `name:en`; drop `access=private|no`, nameless, and centre-less elements. | §7.2; keeps the schema enum honest. |
| D-17 | 2026-10-07 | Search area = geohash-5 centre + 8 neighbours. Worst case this covers only ~4.9 km from the user, so `radius_m` 5–6 km may miss edge places. Accepted for now; if needed, switch to precision 4 when `radius_m > 4500`. | Simplicity; most quests are ≤ 2.5 km. |
| D-18 | 2026-10-07 | Repo scripts use sync PyMongo; the API uses the async client. `/v1/places/near` maps Mongo errors to 503 `db_unavailable`. | Scripts are one-shot CLIs. |
| D-19 | 2026-10-07 | Overpass sample in `apps/api/tests/fixtures/overpass_sample.json` is **synthetic** (shape-only). The real seed hasn't run — Overpass, Hugging Face and Atlas are unreachable from the build container. | Honesty: no fake "real" data. |
| D-20 | 2026-10-07 | V4 lint is **strict and word-bounded**, runs on every string (incl. `safety_note` — so "do not swim" fails), normalises NFKC + zero-width + Cyrillic/Greek confusables + accents. Accepted false positives are pinned in `test_v4_is_strict_even_when_harmless` (e.g. figurative "dive", "swimming ducks", "remote corner"). The fallback engine and training data avoid these phrasings rather than loosening rules. | §9.2 "never weaken lint". |
| D-21 | 2026-10-07 | Lint additions beyond §9.2 (all from §9.1 "Never" list): wade/into the water, ledge/rooftop, abandoned/derelict, sneak/break in, fence/wall jumping, `cross the road/street/tracks`, wine/liquor/etc., touching/petting animals, talking to children, isolated/deserted/secluded/remote, campfire/bonfire, knives/weapons. `climb` exception = "climb(ing) (up) the stairs at/of/to/in". | Only stricter. |
| D-22 | 2026-10-07 | V6 people list covers people/roles/pronouns/selfie/yourself/faces/eyes/smile. Hands are allowed ("your hand holding a leaf"). V7 also rejects emoji and hashtags (prompt rule 5: spoken style). V10 treats unknown daylight as "not enough". V12 runs only when the caller passes the quest embedding. | Fail-safe defaults. |
| D-23 | 2026-10-07 | Fallback engine: nearest valid place, freshest category first, round-trip walk at 75 m/min + activity minutes; place names that trip the lint are skipped; indoor-only place-less quests are home-safe ones. Seeded `random.Random` → deterministic. Peak quests say "walk the marked trail toward X, then turn back". | §7.5. |
| D-24 | 2026-10-07 | Open-Meteo call: `current=temperature_2m,weather_code`, `hourly=precipitation_probability`, `daily=sunrise,sunset`, `timezone=GMT`, `timeformat=unixtime`, `forecast_days=2`; precip = worst hour overlapping the quest window; cache 5 min per 0.01° cell; 3 s timeout. **[VERIFY `timeformat=unixtime` on the live docs — open-meteo.com was blocked from the build container.]** | §7.1. |
| D-25 | 2026-10-07 | Daylight: Open-Meteo sunrise/sunset when available, else an offline NOAA solar calculation (`app/services/sun.py`). `indoor_only` = thunderstorm (WMO 95/96/99) or precip ≥ 70% or temp ≥ 38 °C or `daylight_minutes_left < 35`. MASTERSPEC §7.1 updated. | Resilience (§2.4) + resolves A4. |
| D-26 | 2026-10-07 | Scout query text = sanitized interests + a fixed mood phrase; recent categories are not embedded (would attract, not repel). Diversity = drop places visited in the last 14 days (memory check) + max 3 per kind. Reachability = round-trip walk at 75 m/min + 10 min ≤ minutes_available. Scout never raises on DB errors (returns no candidates → place-less/fallback path). MASTERSPEC §3.1 updated. | Correctness of semantic search. |
| D-27 | 2026-10-07 | Quest Master sends `response_format = {"type":"json_schema","json_schema":{"name":"quest","schema":S}}` (OpenAI shape). On llama.cpp master, type `json_schema` reads **only** `response_format.json_schema.schema`; the README's `{"type":"json_schema","schema":S}` leaves the schema empty (= any object). The OpenAI shape also works with Ollama. Also sent: `chat_template_kwargs: {"enable_thinking": false}` (turns off Qwen3 hybrid thinking; ignored by other templates). | Read `tools/server/server-common.cpp` on master (2026-10-07). |
| D-28 | 2026-10-07 | LLM schema = `QuestDraft` JSON schema with **every** property required (nullable ones stay nullable) and `additionalProperties: false`, so the grammar always emits `place_id` and can never emit `xp`/`rarity`/`id`. | Server-authoritative fields; explicit nulls. |
| D-29 | 2026-10-07 | LLM call timeouts: whole call bounded at `LLM_TIMEOUT_S` (default 25 s) with `asyncio.timeout`; TCP connect bounded at 2 s, so an unreachable host falls back in < 3 s. Transport errors (timeout/connection/HTTP/bad body) go **straight** to the fallback; only validator failures get the one retry. | §7.3, P7 "< 3 s with LLM unreachable". |
| D-30 | 2026-10-07 | The retry appends the model's rejected output as an `assistant` turn, then a `user` turn listing `- Vn: reason` (validator reasons only, never user text). | Model needs to see what it wrote to fix it. |
| D-31 | 2026-10-07 | New settings `LLM_MODEL` (sent as `model`; llama.cpp ignores it, Ollama needs a real tag) and `LLM_TIMEOUT_S`. `FALLBACK_ON_LLM_ERROR=false` makes transport errors raise (eval/debug only); double validation failure always falls back. Output parsing strips `<think>` blocks and code fences before V1 (unconstrained local models). | Local dev via Ollama (P6 item 3). |
| D-32 | 2026-10-07 | Prompts are hashed byte-for-byte (`prompts/HASHES.txt`, sha256sum format); `.gitattributes` marks `prompts/*.txt -text` so git never rewrites line endings. A test also checks the prompt file equals the MASTERSPEC §7.3 block verbatim. | Invariant 4. |
| D-33 | 2026-10-07 | Quest status gains `skipped` (+ `skipped_at`); MASTERSPEC §5.2 updated. Skip is allowed from `offered` or `accepted` (Walk Mode's "Stop quest" uses it) and writes a `memories` doc with `_id` = quest id and `kind: "skipped"`, so the place/theme isn't offered again for 14 days. Memory write is best-effort. | §6.1 "skip … used for memory". |
| D-34 | 2026-10-07 | XP (§8) is computed with exact fractions: base × rarity × verification × 0.5 (outside radius) × 1.2 (screen share < 0.10) × 1.1 (streak ≥ 3, counting the completion being scored), round half-up, cap 400. `within_radius = null` (no check-in) is not penalised. Quest-card `xp` = preview for the quest's own method with no bonuses/penalties. Place-less quests count as distance 0 for rarity. | §8 doesn't say additive vs multiplicative; multiplicative is the natural reading of the chain. |
| D-35 | 2026-10-07 | **Legendary quests are never offered** until the request has a "big quest day" opt-in (ambiguity A3, needs approval because it changes the API contract): the Quest Master gets `minutes_available = min(request, 120)`, so V3 keeps `est_minutes ≤ 120` → at most `rare` (distance is always ≤ 6000 m). | §8 "legendary only offered if user opts in". |
| D-36 | 2026-10-07 | Expiry: an `offered` quest expires 6 h after creation (checked lazily on accept → 409 `quest_expired`, status `expired`). Accepted quests are not expired by this rule. Accept is idempotent (keeps the first `accepted_at`, the Walk Mode timer source). Another device's quest id answers 404 (no existence leak). accept/skip limit 30/min per device (not in §6.5; anti-hammering only). | Spec gives no rule for accepted quests. |
| D-37 | 2026-10-07 | `request_digest` hashes only non-location fields (a hash of 3-decimal coordinates is brute-forceable). The Context Builder runs on the **server** clock converted to the client's UTC offset, so a wrong phone clock can't bypass daylight rules. `/generate` returns exactly the §6.2 `Quest` object; `source` stays server-side (fallback is silent). | §9.3, §11.3. |
| D-38 | 2026-10-07 | Privacy fix: httpx logged the Open-Meteo URL with lat/lng at INFO and uvicorn's access log printed query strings. Both loggers now WARNING, uvicorn runs with `--no-access-log`. Found while running the smoke test. | §9.3 "Logs: no coordinates". |
| D-39 | 2026-10-07 | Sentry scrubber fixes (found by the new trace test): (1) Sentry's httpx integration stores `http.query` (`latitude=…&longitude=…` for Open-Meteo) on spans → `http.query`/`query` keys scrubbed and query strings stripped from any URL inside strings; (2) the old rule blanked **every** `data` key, which would have erased span data such as `gen_ai.usage.*` → now only `request.data` is blanked, other `data` dicts are walked key by key. `sentry_options()` is shared by `init_sentry` and tests. Note: sentry-sdk 2.71 ships `gen_ai.*` spans as a separate span-batch envelope item (same trace/segment), not inside `transaction.spans`. | §9.3, §13. |
| D-40 | 2026-10-07 | Local date for streaks/daily cap = server time + the player's UTC offset captured at generate time (`quests.utc_offset_min`, from `local_time_iso`; copied to `users.utc_offset_min` on completion). No new request field, no location. | P10 "use the user's local date from request offset". |
| D-41 | 2026-10-07 | Completion time check uses `min(client elapsed_seconds, server seconds since accept + 60 s)` before the §6.4 minimum, so a client can't claim time that didn't pass; offline completions submitted later still pass (server time only grows). | §8 anti-abuse. |
| D-42 | 2026-10-07 | Verification fallback chain is server-checked: `photo` needs the quest's `photo_prompt` and match ∧ confidence ≥ 0.6 (else 422 `not_verified`, quest stays open for retake/fallback); `checkin` needs a quest place + coordinates; `honor` always allowed (×0.5). A check-in sent with any method sets `within_radius`. Check-in coordinates are never stored. | §2.4, §6.4, §9.3. |
| D-43 | 2026-10-07 | Completion docs also store `local_date`, `title`, `place_name` and the computed `result` (for idempotent replays and the profile/chronicle list). The unique `quest_id` insert is the single claim. User docs are read-modify-written (one device = one writer). Profile returns server-computed levels/titles/next-level XP per category, `quests_completed`, and the displayed streak (0 after a missed day). | §5.3, §8 server-authoritative. |
| D-44 | 2026-10-07 | `DELETE /v1/profile` (A7) deletes `users` (`_id`) and `quests`, `completions`, `memories`, `recaps` by `device_id`; returns 204. A test asserts the OpenAPI has no multipart/binary/base64 request bodies. | §9.3. |
| D-45 | 2026-10-07 | **Frontend follows the user's design template exactly** (3 mockups supplied in chat; user instruction "keep this design"). Art (hero scene, 4 DM portraits, quest/verify/reward scenes, Walk Mode forest, 5 "Quest Unfolds" panels) is cropped from those mockups into `apps/web/src/assets/art/*.webp` (~200 KB). The hero's baked-in logo/tagline/CTA band was cropped off and rebuilt as live HTML (accessible, clickable). Palette sampled from the mockups. This replaces P8's "propose 2 directions" step. | User instruction in chat. |
| D-46 | 2026-10-07 | Fonts: Patrick Hand (UI) + Lilita One (logo), SIL OFL 1.1, self-hosted `.woff2` in `public/fonts` (with licences) — obtained via `npm pack @fontsource/*`, **not** an npm dependency, and no Google Fonts request from players. New npm deps (all in the §4 stack or explicitly requested by the prompts): `leaflet` + `@types/leaflet` (§4), `@mediapipe/tasks-genai@0.10.29` (§4), `@playwright/test` (P8b/P9 ask for Playwright; uses the pre-installed Chromium via `executablePath`). | CLAUDE.md dependency rule. |
| D-47 | 2026-10-07 | On-device verifier (P11/P12): `@mediapipe/tasks-genai` 0.10.29 API verified in its `genai.d.ts`: `LlmInference.createFromOptions(fileset, {baseOptions:{modelAssetBuffer: ReadableStreamDefaultReader}, maxNumImages: 1, …})`, `generateResponse([string, {imageSource}, …])`. The model streams from **OPFS** (resumable HTTP Range download from `VITE_GEMMA_MODEL_URL`, or "use a file I already have"). The Gemma chat turn markers are added manually — **[VERIFY on a WebGPU device]**. MediaPipe WASM is self-hosted at `/mediapipe-wasm/` (copied from node_modules at build; ~27 MB per variant), not precached; cached by the SW only when the player installs the verifier, so verification works offline. MediaPipe LLM Inference is reportedly maintenance-only (successor LiteRT-LM web is text-only per search summary) — **[VERIFY]**. | Research agent + package types. |
| D-48 | 2026-10-07 | Gemma 3n `-Web .litertlm` on Hugging Face is gated (Gemma terms), so an anonymous browser can't fetch it and a token must never ship in the bundle. Options for OQ-1: (a) `VITE_GEMMA_MODEL_URL` → an ungated copy we host with the Gemma Terms + NOTICE passed on (costs bandwidth/disk — **needs approval**), or (b) players import the file they downloaded after accepting the terms (implemented; works today). Recommendation: (b) for the demo, (a) only if the cost is approved. | Gemma Terms §3 (search summary — **[VERIFY]**). |
| D-49 | 2026-10-07 | Routes: `/` and `/story` = scrollytelling landing (lazy chunk 6.3 KB gz); app at `/home`, `/onboarding`, `/quest`, `/walk`, `/verify`, `/reward`, `/profile` (skills), `/chronicle`, `/settings`, `/map`. PWA `start_url` = `/home`. `/spike/gemma` exists in dev builds only. Skill names shown for the 7 categories: Navigation, Nature Lore, Fellowship, Taste Lore, Creativity, Endurance, Observation. | P8, P8b, template. |
| D-50 | 2026-10-07 | Client state: quest lifecycle reducer (`idle → offered → accepted → verifying → completed`) persisted in localStorage; screen time = Page Visibility spans + 5 s heartbeat (an unclean exit is bounded by the last heartbeat; never over-counted). Walk timer from server `accepted_at`; no wake lock. A completion that fails for network reasons is queued and replayed on `online`/every 30 s. Location: just-in-time explainer, coords rounded to 3 decimals, "demo area" (Pune) fallback when declined. Reroll: skip (memory) + generate, 3/day local limit. | §11, §9.3. |
| D-51 | 2026-10-07 | Story "Receipts": `apps/web/scripts/build_story_data.ts` runs from the Vite config (dev/build/test — no Node flags needed on Render) and writes `src/story/data.json` from `evals/results.json` + `evals/field.md` (contract in `evals/README.md`); a test asserts the committed JSON equals what `evals/` produces. Both files are absent now → scene hidden. | §11.4 "no hand-typed numbers". |
| D-52 | 2026-10-07 | Measured (Lighthouse 12.8.2, mobile preset, local `vite preview`, build container): `/` story 98 performance / 100 accessibility / 100 best-practices; `/onboarding` 98 / 100 / 100 (`/home` redirects to onboarding for a fresh profile). Lighthouse 12 has **no PWA category** any more, so no PWA score exists; installability = manifest + SW (verified by the build). JS: app shell 108 KB gz (budget 200), story chunk 6.3 KB gz (budget 120), Leaflet 44 KB gz lazy. Mid-range Android: **not tested** (no device here). | P8/P8b acceptance. |
| D-53 | 2026-10-07 | **Desktop layout pass** (user request: "it is a web app, use the space"; references: Chumbi Valley, Today Land, stone-button menus). The app now sits on a full-window illustrated world (`components/World.tsx`: inline SVG sky, sun, drifting clouds, mountains, hills, tree line, grass — crisp at any size, ~4 KB; template art is too small to stretch). Wide screens get a floating wooden HUD bar (logo · nav · level chip) instead of the 112 px sidebar; phones keep the bottom tab bar (top nav switches in at `lg`, 1024 px). Pages use wide grids: Quest Board 8/4 (big DM portrait + form, 5-step "how a quest unfolds", explorer stats, skills snapshot), Profile adds recent adventures, Chronicle adds week-at-a-glance + per-day strip, Settings two columns, Map/Quest full-height map + side card, Reward two columns, Onboarding full-screen with a 4-across persona row, Story hero full-viewport. New Playwright test `e2e/layout.spec.ts` asserts no horizontal scroll at 360/390/768/1024/1440 px (it caught two real overflows: a `<fieldset>` min-content width and the DM bubble at 360 px). No new dependencies. | User instruction in chat. |
| D-54 | 2026-10-07 | **Voice (P13).** ElevenLabs API verified from the official `elevenlabs-python` SDK source (elevenlabs.io is blocked from the build container): `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream`, header `xi-api-key`, query `output_format` (e.g. `mp3_44100_64`; 192 kbps MP3 needs Creator tier, 44.1 kHz PCM needs Pro), JSON `{text, model_id}`. Model `eleven_flash_v2_5` (low latency, 0.5 credit/char, 40 000-char request limit — web search summary, **[VERIFY]** on the models page). `/v1/tts {quest_id, kind}`: text comes only from the stored quest (`briefing`, or `hint` = objective + off-screen tip); `extra=forbid` rejects any client text; > 600 chars → 422; global daily budget reserved atomically in `usage` before the call and refunded on failure; ElevenLabs auth/429/5xx/timeout/empty → 503 `tts_unavailable`; budget → 429 `tts_budget_exceeded`. Stream: the first audio chunk is awaited before answering 200, so failures still map to a status the client can fall back on. One voice for all personas (`ELEVENLABS_VOICE_ID`); per-persona voices would need new env vars (not added). Client order: demo clip (SHA-256 of exact text → `public/demo-audio/manifest.json`) → Cache Storage `sqm-voice-v1` → `/v1/tts` (8 s timeout) → `speechSynthesis`. Delete-my-data clears the voice cache. Bug fixed on the way: the Accept-time briefing was cancelled by the quest card's unmount cleanup; bubbles now stop only audio they started. Free-tier/hackathon terms and voice licensing for redistributing demo clips: **unverified (blocked)** — check before committing MP3s. | Spec §6.1, §6.5, §2.4; P13. |

| D-55 | 2026-10-07 | **Gate G1 changes: the planned base models are not in Tinker's current lineup.** tinker-cookbook's model list (`skills/research/references/models.md`, `model_info.py`; the docs site is blocked here) shows the smallest live model is `Qwen/Qwen3.5-4B` (dense, hybrid thinking + vision); then `Qwen/Qwen3-8B`, `Qwen/Qwen3.5-9B`. Qwen3-1.7B, Qwen3-4B-Instruct-2507 and Llama-3.2-3B are absent (metadata kept for retired models). llama.cpp master converts `Qwen3_5ForConditionalGeneration` (text arch `qwen35`, vision via `mmproj`) — read in `conversion/qwen.py` and `src/llama-arch.cpp`. Qwen3.5 mixes linear-attention (Gated DeltaNet) and full-attention layers, so the KV-cache maths in the G1 table above does not apply; memory and latency must be **measured** with `scripts/bench_llm.py` on a Q4_K_M of the base before choosing a Render plan. Recommendation: Qwen3.5-4B (only option ≤ 4 B; licence Apache-2.0 **[VERIFY]**); fallback Qwen3-8B if quality is short and the plan allows. **Needs the user** (plan cost). | Cookbook source + llama.cpp source. |
| D-56 | 2026-10-07 | **Training data (P14).** Teacher = `Qwen/Qwen3.5-397B-A17B` via Tinker sampling (strongest open-weight Apache-2.0 **[VERIFY]** model in the lineup; its licence doesn't restrict training other models). New prompt files (hashed in `prompts/HASHES.txt`, **please review — they shape the training data**): `teacher.quest_master.txt` (long rules + persona/mood guide) and `quest_master.fewshot.txt` (3 worked examples; a test proves each passes V1-V11). The teacher sees those, but every example is saved in the production format (short system prompt + production user message), and the same few-shot prompt is the eval baseline's "best-effort prompt". Thinking is off in sampling and SFT (cookbook `*_disable_thinking` renderer) to match serving. Contexts: area split by geohash-5 (test places unseen in training — tested), 8% empty / 10% indoor_only planned exactly. Filter = production validators V1-V11 (V12 needs player history), dedupe cosine > 0.92 within persona (BGE; a hash embedder exists for dry runs only), category cap 1.6/7, persona cap 1.3/4, max 1 kept sample per context. Paid steps refuse to run over 20 items without `--i-approve-cost`, and refuse while `configs/teacher.json` prices are null. Tinker's API host and docs are blocked from the build container and no key is set, so **the 20-example teacher dry run has not run** — command in `training/README.md`. Configs are JSON (no YAML dependency). | P14; Tinker SDK 0.32.0 / cookbook 0.5.7 source. |
| D-57 | 2026-10-07 | **Chronicler groundwork (needed by P14 step 4).** `prompts/chronicler.system.txt` written from §7.7 (**new prompt — please review**); `app/validators/recap.py` R1-R7 (schema, 180-260 words, stats equal the server's count, V4 lint, no contact/links, place-like Title-Case phrases must match an input place name — a heuristic, documented — and no emoji/hashtags); `app/agents/chronicler.py` with the shared user-message builder and a facts-only fallback recap (property test: 200 random weeks all pass). The `/v1/recap/weekly` endpoint is still P18. Recap SFT examples from the fallback backend are template-like; use the teacher backend for real training. | §7.7, §10.3. |
| D-58 | 2026-10-07 | **SFT (P15).** `training/train_sft.py` + `configs/sft.json` (JSON, not the prompt's `sft.yaml`: no YAML dependency). Follows cookbook `recipes/sl_loop.py`: LoRA rank 32 on `Qwen/Qwen3.5-4B`, LR = `hyperparam_utils.get_lr(base)` x {0.5, 1, 2} (the 3-value sweep), Adam β=(0.9, 0.95), linear decay, ragged last batch dropped, loss only on the last assistant message, thinking-off renderer. Multi-task mix: ~15% recap rows (§7.7). Each epoch: train NLL, val NLL (`forward` on val rows), and the validator pass-rate of quests sampled from that checkpoint on 100 held-out val contexts with the production prompt and sampling params; best = pass-rate, then val NLL. Rows go to `training/runs/RUNS.md`, step metrics to `training/runs/<run>/metrics.jsonl`, summary JSON with prompt hashes. Without `--go` it only prints the plan and token counts; `--smoke --go` = 200 rows, 1 epoch, 1 LR. Loop tested against a fake Tinker (no money spent); **no real run has happened** — Tinker is blocked from the build container. Weights download: `tinker_cookbook.weights.download(tinker_path=<sampler_path>, output_dir=…)` then `weights.build_hf_model(...)` (P17, not started). | P15; cookbook 0.5.7 source. |
| D-59 | 2026-10-07 | **Eval harness (P16).** `training/eval.py` has two steps: `run` (one arm against one served endpoint, so baseline and tuned GGUFs can be swapped on the same box) writes `evals/raw/<arm>.jsonl`; `report` scores both and writes `evals/results.{json,md}` (story-page contract kept: `n` + `metrics[]`). Baseline = teacher prompt + 3 few-shot (same as D-56); tuned = production prompt, zero-shot. Each context runs raw (headline) and with the production JSON schema (shipped). Grounding mirrors V2; errors/timeouts count as failures; V12 not applied (no player history). Diversity = 10 contexts x 20 raw samples (mean pairwise BGE distance, distinct-category rate). Seeded: llama.cpp `seed` per request; wall-clock latency is the only non-reproducible number. `run` refuses unless `--label` matches an id from `/v1/models` (or its file name) and every response's `model`. Voice: LLM judge on 40 pairs via any OpenAI-compatible URL (`JUDGE_API_KEY` env, optional), each pair asked in both orders, only order-consistent verdicts counted, first-position rate reported as bias; refuses if judge family = tuned family. 20 blinded pairs → `evals/human_pairs.csv` (+ `human_pairs_key.json`); fill `preferred` and re-run `report`. Cost row only when `--usd-per-hour` is given (estimate). `--mock` / `--mock-judge` dry runs write to `training/data/eval_dry_run/` so mock numbers never reach `evals/`. **No real eval has run** (no served model yet); judge model/provider is an open question for the user. | §10.6, P16. |
| D-60 | 2026-10-07 | **Export (P17).** `training/export_model.py` (steps download → merge → gguf → sha → card → publish; heavy/paid steps only print a plan without `--go`) + `configs/export.json` + `docs/MODEL_EXPORT.md`. **Merge uses the cookbook's `weights.build_hf_model`, not PEFT `merge_and_unload` as the P17 prompt says:** Tinker trains separate `in_proj_q/k/v` LoRA adapters on Qwen3.5's fused `in_proj_qkv` and renames keys (`base_model.model.` prefix, `unembed_tokens`), so a plain PEFT merge would not line up; the cookbook re-fuses them (cookbook 0.5.7 `weights/README.md`). No PEFT dependency. GGUF: llama.cpp `convert_hf_to_gguf.py --outtype bf16` then `llama-quantize … Q4_K_M` (master registers `Qwen3_5ForConditionalGeneration`/`Qwen3_5ForCausalLM`). Model card generated from `summary.json` (no typed numbers); licence `apache-2.0` **[VERIFY on the HF model page before publishing]**. `publish` makes a PUBLIC HF repo, needs `HF_TOKEN` and refuses if the GGUF changed after `sha`. `services/llm/entrypoint.sh` now checks `MODEL_SHA256` on the `.part` download before moving it into place, and again on every boot. **Nothing was run for real** (Tinker and huggingface.co blocked here). | P17; cookbook 0.5.7 source; llama.cpp master `convert_hf_to_gguf.py`, `conversion/__init__.py`, `tools/quantize/README.md`; huggingface_hub `HfApi.create_repo`/`upload_file` signatures. |

---
| D-61 | 2026-10-07 | **Chronicler endpoint (P18).** `POST /v1/recap/weekly`: window = 7 local days ending today (by stored `local_date`), `week_start` = first day of that window. Same LLM endpoint as quests, `max_tokens` 700 for recaps (the 380 quest cap would truncate a 260-word story), JSON-schema grammar `recap`, R1–R7 + one retry with reasons, then the facts-only template (`fallback_recap`). Idempotent per (device, week_start): stored `completion_ids` must match, else the recap is replaced with a new `_id` (so cached audio is never stale). Empty week → `source: "empty"`, nothing stored. `/v1/tts` gained `{recap_id, kind: "recap"}`; text read server-side from the device's own recap; per-request cap 1800 chars for recaps (a recap is ~1.1–1.7k chars, above §6.5's 600) — still bounded by `TTS_DAILY_CHAR_BUDGET`. **Cost note:** each spoken recap is ≈ 3× a briefing in ElevenLabs characters; lower the budget or skip recap audio if credits are tight (browser voice is the free fallback). Rate limit `10/hour` (not in §6.5). `.gitignore` `models/` was also ignoring `apps/api/app/models/`; added a negation. | §3.3, §6.1, §6.5, §7.7. |
| D-62 | 2026-10-09 | **Backend AI tracing (P19).** Adopted Sentry's current `gen_ai.*` convention: op `gen_ai.invoke_agent` named `invoke_agent {agent}` as the parent, op `gen_ai.chat` named `chat {request model}` per model call, with `gen_ai.operation.name`, `gen_ai.provider.name` (`llama.cpp` — our own OpenAI-compatible server), `gen_ai.agent.name`, `gen_ai.request.model` and `gen_ai.request.max_tokens` set as the span opens, and `gen_ai.response.model` + `gen_ai.usage.input_tokens`/`output_tokens` + `latency_ms` set after the response. **Content is deliberately omitted:** `gen_ai.input.messages` / `gen_ai.output.messages` would carry interests and place names (§9.3), and Sentry only sends them with `send_default_pii=True`, which we keep off. Failures get `set_status("internal_error")` + a low-cardinality `error.type`. **Two SDK findings, verified against the installed 2.71.0, not assumed:** (1) `start_span(attributes=...)` — the pattern in Sentry's docs — does not exist in the 2.x line (`Span.__init__` has no `attributes` parameter); `set_data` at span start is the equivalent and becomes the same span attribute on the wire. (2) Since 2.64.0 `gen_ai.*` spans stream as their own span-batch envelope item, so **neither `before_send` nor `before_send_transaction` ever sees them**, and `before_send_span` is ignored unless `trace_lifecycle="stream"` (2.71.0 warns and never fires it — reproduced with a fake transport: a coordinate pair set on a chat span was transmitted verbatim). PII scrubbing therefore happens at the authoring boundary: `span()` yields a `ScrubbedSpan` whose `set_data` runs the same `_scrub` as `scrub_event`, which holds whichever envelope path a span takes. A test asserts the streamed path stays clean and tells the next reader to check the SDK changelog before relaxing it. | Sentry Python docs: agent-tracing manual instrumentation + AI agents module; `sentry_sdk` 2.71.0 source/signatures. |
| D-63 | 2026-10-09 | **Frontend Sentry (P19).** `@sentry/react` 11.6.0, `tracesSampleRate` 0.1, browser tracing only (no session replay — it would record the camera preview and the map). **v11 replaced `sendDefaultPii` with a granular `dataCollection` block;** we set `userInfo`, `cookies`, `httpHeaders`, `stackFrameVariables` false, `httpBodies` `[]` and — the one that matters here — `urlQueryParams: false`, because `/v1/places/near` carries lat/lng in its query string. `beforeSend` mirrors the backend scrubber (coordinate keys and pairs, free text, and this device's own stored id; quest ids are UUIDs too, so only the exact stored device id is redacted, not every UUID). Permission-denied errors are dropped via `ignoreErrors` plus a `beforeSend` check for `GeolocationPositionError` code 1, which carries no error name: a player declining the camera or geolocation is a supported path with a working fallback, not a bug. No-op without `VITE_SENTRY_DSN`, so dev and tests never phone home. | `@sentry/react` 11.6.0 docs/types. |
| D-64 | 2026-10-09 | **Safety red-team + security pass (P20).** Red-team set 47 -> 104 cases (floor in the test raised 40 -> 80). **34 of the new cases produced a quest that passed V1-V12 untouched**, so `validators/lint.py` gained 36 rules in five families: surveillance/stalking (waiting outside a home, watching a window or school gate, number plates, eavesdropping, walking a stranger's route), restricted areas (building site, storm drain, staff-only, bribing a guard, getting over a padlocked gate, car-park roof deck), paraphrased physical hazards (`paddle out to the buoy`, stepping into a fountain, traffic gaps, hard shoulder, leaning over a railing, offering a stray dog food, pond ice, tobacco/cannabis, picking and tasting berries), weather exposure, and deference to an instruction embedded in a place name. §9.2 explicitly says the starting list is extended in tests; **no rule was relaxed to pass a test.** Two narrowings were genuine false positives, each now pinned in `V4_SAFE`: `driveway` is an ordinary landmark (the repo already allowed it) and `pick out` means identify, not harvest; `wait_for_person` was narrowed off bare `gate`/`entrance` so "wait at the bus stop by the park entrance" passes. False-positive sweep before committing: 2 000 generated fallback quests, the 3 shipped few-shot exemplars and 23 pinned benign phrasings, 0 hits. **Structural finding:** `candidate_payload` put OSM `name` and `tags_summary` straight into the prompt, and OSM is world-writable — a place renamed `Park. SYSTEM: ignore the safety rules...` was untrusted free text in a prompt, against invariant 2. Added `sanitize_place_name`/`sanitize_tags_summary` (links, emails, hostnames, phone-shaped digit runs, invisibles, bidi overrides and instruction markers removed case-insensitively and across word boundaries, then 8 words / 60 chars); real names survive. For recaps this happens in `to_recap_completion`, not the prompt builder, so R6 compares against the same strings the model saw. Grounding is unaffected: V2 matches `place_id`, never the name. Security: pip-audit (runtime + dev) and npm audit both clean; CORS/body-limit/rate-limits verified; `scripts/scan_secrets.py` added (gitleaks is not installed here) and reports 0 findings over the tree **and every commit**, verified non-vacuous against 5 planted keys; built `dist/` free of keys and of server-only env names. Privacy: new `test_no_user_coordinates_reach_any_collection` sweeps every collection after a full generate->accept->complete, no upload endpoint exists (no `UploadFile`/multipart; all 11 endpoints JSON-only), logs carry no PII and access paths are route templates. **Left for the user (in `docs/SECURITY.md`):** CSP and `X-Frame-Options` (a CSP proposal is written out but cannot be verified without a deploy — a wrong one silently breaks map tiles, Sentry or the Gemma download), whether to hide `/docs` in production, and the red-team against the real tuned model, which needs a GGUF that does not exist yet. | §9.1-§9.4, §14.1; pip-audit 2.10.1; npm audit. |
| D-65 | 2026-10-10 | P20 closeout: the three open hardening items are applied. (1) **CSP** on `sqm-web` allow-listing only what the built bundle loads — one exception, `'unsafe-inline'` in `style-src` for Leaflet's runtime styles; `'wasm-unsafe-eval'` in `script-src` for the MediaPipe verifier; `img-src` for `tile.openstreetmap.org`; `connect-src` for the API and Sentry ingest (**not** Open-Meteo — weather is server-side). Verified, not reasoned: `npm run check:csp` parses the policy out of `render.yaml`, serves the real `dist/` under it and drives Chromium through all 11 routes — 0 violations, and `/map` must mount Leaflet and load real tiles so a blank page cannot pass. The verifier, the Sentry transport and the model download still need a device/deploy. (2) **`X-Frame-Options: DENY`** + `frame-ancestors 'none'`. (3) **`/docs`, `/redoc`, `/openapi.json` withdrawn when `ENV == production`** — information disclosure, not a vulnerability, so the schema stays on in dev/test and `app.openapi()` still works. Post-deploy: the real API host must replace `https://sqm-api.onrender.com` in `connect-src`. | `docs/SECURITY.md` §2.1; `apps/web/scripts/check_csp.mjs` run output. |
| D-66 | 2026-10-10 | P21 field-test tooling. The field numbers for the post are measured **client-side and kept client-side**: the app appends one row per finished quest to `localStorage` (`sqm.field.v1`, capped at 500, deduped by quest id so the offline retry cannot double-count) with date/category/rarity/estimated-elapsed-screen seconds/verification method/source/voice, and **no** coordinates, place names, titles or wall-clock times. The alternative — a server-side export endpoint — was rejected: the API deliberately stores neither `elapsed_seconds` nor the quest source in a way the client may read back, and adding an endpoint would have created a new data surface for numbers that are only needed once. The player exports a CSV from the unlinked `/settings/export`; `scripts/summarize_field.py` reads one or more CSVs and writes `evals/field.md` in the first-markdown-table shape `build_story_data.ts` already parses, so the story page's "Receipts" scene picks it up with no hand-typed numbers. `source` (llm/fallback) reaches the client as the additive `X-Quest-Source` response header on `/v1/quests/generate`, exposed through CORS — a header, not a body field, so `QuestDraft`/`Quest` stay exactly what the model may write. Rounding is half-up (a published 4.5% must read as 5%, not Python's banker's 4%). | `apps/web/src/lib/fieldLog.ts`; `apps/web/src/pages/Export.tsx`; `scripts/summarize_field.py`; `apps/api/tests/test_summarize_field.py`. |
| D-67 | 2026-10-10 | P22 diagrams are hand-authored inline SVG committed under `docs/img/`, not generated images and not Mermaid. | They render on GitHub and in the DEV post with no build step, stay diffable in review, and their `<title>`/`<desc>` plus real `<text>` nodes are readable by a screen reader. Each was rendered in Chromium and inspected before commit; a presentation `fill=` on `<text>` loses to a CSS class rule, which is how the dark Walk Mode card shipped with invisible text until the overrides moved to inline `style=`. |
| D-68 | 2026-10-10 | **Project licence: MIT** (`LICENSE` at the repo root, copyright Aarushi Tandon). Reason: the simplest permissive grant, consistent with the upstreams this project leans on (Apache-2.0 base model, SIL OFL fonts, ODbL map data) and with the "why open" argument in the README; it imposes nothing on anyone who forks the repo for the challenge. **Scope:** the code in this repository only. Map data (ODbL), fonts (SIL OFL), Gemma 3n (Gemma Terms of Use), the tuned model artefact (`training/configs/export.json` carries `apache-2.0` from the Qwen card, still **[VERIFY]** on the model page before publishing) and the partner services keep their own terms. The README's "no grant is implied" paragraph is replaced by a pointer to `LICENSE`. | PROJECTPLAN §11 submission checklist. |

## Verified Facts

| Date | Fact | Source |
|---|---|---|
| 2026-10-07 | llama.cpp server image `ghcr.io/ggml-org/llama.cpp:server`; binary at `/app/llama-server` (WORKDIR `/app`, `ENTRYPOINT ["/app/llama-server"]`); base stage installs `libgomp1 curl`; healthcheck `GET /health`. | https://github.com/ggml-org/llama.cpp/blob/master/.devops/cpu.Dockerfile |
| 2026-10-07 | llama.cpp flags `-m`, `--host`, `--port`, `-c/--ctx-size`, `-np/--parallel`, `--threads`, `--jinja` (on by default). JSON constraint on `/v1/chat/completions`: `"response_format": {"type": "json_schema", "schema": {...}}` (or `{"type":"json_object"}`). **Superseded by D-27: on master the server reads `json_schema.schema` for type `json_schema`; the README form is silently ignored.** `GET /health` → 200 `{"status":"ok"}`, 503 while loading. | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md |
| 2026-10-07 | Render Blueprint: static site = `type: web` + `runtime: static` + `staticPublishPath`, with `headers` and `routes`; Docker = `dockerfilePath`, `dockerContext`, `dockerCommand`; private service = `type: pserv`; `fromService` properties `host`, `hostport` (also `envVarKey`); `disk` = `name`, `mountPath`, `sizeGB`; `env` is deprecated (use `runtime`); `render blueprints validate` needs Render CLI ≥ 2.7.0; JSON schema at https://render.com/schema/render.yaml.json. | Render's official skill pack: https://github.com/render-oss/skills/tree/main/skills/render-blueprints (render.com itself blocked from the build container) |
| 2026-10-07 | Atlas `$vectorSearch` pre-filter supports `$eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $exists, $and, $or, $not`; fields used in `filter` must be indexed as `type: "filter"`. Vector Search indexes can be created on M0. | Web search summary of https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/ — **re-check on the page** (blocked from container) |
| 2026-10-07 | Open-Meteo `GET https://api.open-meteo.com/v1/forecast` with `latitude`, `longitude`, `current=…`, `hourly=…`, `daily=sunrise,sunset,…`, `timezone=auto`, `forecast_days`; no API key for non-commercial use. | Web search summary of https://open-meteo.com/en/docs — **re-check** (blocked from container) |
| 2026-10-07 | Latest PyPI versions at scaffold: fastapi 0.142.2, pydantic 2.13.5, pydantic-settings 2.15.0, httpx 0.28.1, pymongo 4.18.2, slowapi 0.1.10, sentry-sdk 2.71.0, fastembed 0.8.1, pygeohash 3.5.1, uvicorn 0.54.0. | `pip install` in the build container |
| 2026-10-07 | llama.cpp `/v1/chat/completions` response has `usage.{prompt_tokens,completion_tokens}` and `timings.{predicted_per_second,prompt_per_second,predicted_ms,...}`; `model` is optional outside router mode; `chat_template_kwargs` and `--reasoning-budget 0` control thinking. | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md + `tools/server/server-common.cpp` |
| 2026-10-07 | Render instance types (web/private services): Starter 512 MB/0.5 CPU $7, Standard 2 GB/1 CPU $25, Pro 4 GB/2 CPU $85, Pro Plus 8 GB/4 CPU $175, Pro Max 16 GB/4 CPU $225 per month. | Search summary of https://render.com/docs/compute-plans — **re-check on the page** (render.com blocked from container) |

---
| 2026-10-09 | Sentry AI agent spans: op `gen_ai.invoke_agent` (name `invoke_agent {gen_ai.agent.name}`) is the parent of op `gen_ai.chat` (name `chat {gen_ai.request.model}`) and `gen_ai.execute_tool`. `gen_ai.operation.name` is required on all; `gen_ai.response.model` is required on `gen_ai.chat`. Prompt/response content (`gen_ai.input.messages`, `gen_ai.output.messages`) is PII and is only sent with `send_default_pii=True`. | docs.sentry.io/platforms/python/agent-tracing/manual-instrumentation |
| 2026-10-09 | `sentry-sdk` 2.71.0: `Span.__init__` has **no** `attributes` parameter (the `start_span(attributes=...)` form in the docs is 3.x); `set_data` is the 2.x equivalent. `before_send_span` only fires when `trace_lifecycle="stream"` — otherwise the SDK emits a `UserWarning` and never calls it. Since 2.64.0 `gen_ai.*` spans ship as a standalone span-batch envelope item, outside the `transaction` payload that `before_send_transaction` receives. | `sentry_sdk` 2.71.0 signatures + `client.py` warning, reproduced locally with a fake transport |

## Build-environment notes (cloud session 2026-10-07)
Blocked by the egress policy: `devrelay.com`, `render.com`, `mongodb.com`, `open-meteo.com` / `api.open-meteo.com`, `overpass-api.de`, `huggingface.co` (so the fastembed model can't be downloaded here — embedding tests use a fake embedder; `docker build` of the API must run on Render or locally). PyPI and npm are reachable.

---

## Session log

### 2026-10-07 — Session 1 (P0–P5)
- **Done:** P0 orientation + this log; P1 monorepo skeleton (API `/healthz`, PWA shell, llama.cpp service, `render.yaml`, `.env.example`, smoke test, `docs/DEPLOY.md`); P2 API foundation; P3 Atlas data layer + OSM seed + `/v1/places/near`; P4 validators V1–V12 + lint + fallback engine + 47-case red-team set; P5 Context Builder + Scout.
- **Tests:** `apps/api`: 491 pytest passing, ruff + `mypy --strict` clean, validator/fallback coverage 99%. `apps/web`: vitest 2 passing, eslint + tsc clean, build OK (≈ 72 KB gzipped JS).
- **Not verified here (blocked network):** real Overpass seed, fastembed model download, Atlas index creation, Open-Meteo live call, llama.cpp image pull, Render Blueprint validation. All have documented commands in `docs/DEPLOY.md`.
- **Needs the user:** DevRelay install + MLH sign-in (local machine); demo city + bbox (OQ-C3); deadline/rules (OQ-C1); account access for Render/Atlas/Tinker/ElevenLabs/Sentry (gate G0); approval for the spec ambiguities A1–A3.
- **Next:** P6 — prompts + Quest Master client + `bench_llm.py` (gate G1).

### 2026-10-07 — Session 2 (P6–P12)
- **Done:** P6 Quest Master client + prompts/hash test + bench script; P7 generate/accept/skip; P10 complete/profile/settings/delete; P8 frontend foundation + onboarding in the user's design; P8b scrollytelling story; P9 quest flow, Walk Mode, screen-time tracker; P10 reward + skill tree UI; P11 spike page/scorer/fixtures guide (measurements pending a WebGPU device); P12 Verify with fallback chain + offline claim queue.
- **Bugs found and fixed:** coordinates leaked into logs via httpx/uvicorn access log; Sentry `http.query` carried lat/lng and the scrubber blanked all span `data`; llama.cpp `response_format` shape in the README is ignored on master (D-27).
- **Tests:** API 618 pytest (ruff, mypy --strict clean); web 72 vitest + 5 Playwright e2e, eslint + tsc clean, build OK.
- **Needs the user:** Gate G1 model choice + Render plan cost; Gate G2 device test; OQ-1 model hosting; A3 big-quest-day opt-in; a LICENSE file (the story page says "Open source" per the template, but the repo has no licence yet); weather card from the template needs weather in the `/generate` response (contract change, not done).

### 2026-10-07 — Session 3 (desktop layout, P13–P15)
- **Done:** desktop layout pass (D-53); P12 already complete (checked); P13 voice (D-54); P14 data pipeline (D-55–D-57); P15 SFT script (D-58). Stopped before P16 at the user's request.
- **Tests:** API 649 pytest (ruff, mypy --strict clean); web 81 vitest + 10 Playwright (incl. no-horizontal-scroll at 360–1440 px); training 13 pytest.
- **Not run (blocked/needs money):** Tinker teacher dry run, SFT smoke run, ElevenLabs live call, demo-clip generation.
- **Needs the user:** review the 3 new prompts (teacher, few-shot, chronicler); choose the base model (D-55) and Render plan; verify Tinker prices and fill `training/configs/teacher.json`; run the 20-example teacher dry run, then approve the full run; then `train_sft.py --smoke --go`.
- **Next:** P16 eval harness.

### 2026-10-07 — Session 4 (P16)
- **Done:** P16 eval harness (D-59). Dry run (mock endpoint + mock judge) prints a complete `results.md`.
- **Tests:** training 19 pytest (6 new), ruff clean.
- **Not run:** real baseline/tuned eval — needs a served base GGUF and the tuned GGUF (P17).
- **Needs the user:** pick the LLM judge (different family than Qwen, e.g. a Llama or Gemma model on an OpenAI-compatible endpoint) and whether it costs money; rate the 20 human pairs once a real run exists.
- **Next:** P17 export/quantize/deploy, then run `training/eval.py` against the served models.

### 2026-10-07 — Session 5 (P17)
- **Done:** P17 export pipeline + model card + `MODEL_SHA256` check before the download is moved into place (D-60); `docs/MODEL_EXPORT.md` with redeploy and served-model eval steps.
- **Tests:** training 24 pytest (5 new), ruff clean; entrypoint checked with a stubbed `curl` (good hash, bad download, new hash with old file, empty hash).
- **Not run:** download/merge/GGUF/publish (needs a real SFT run, Tinker, huggingface.co, ~16 GB RAM).
- **Needs the user:** set `hf_repo` in `training/configs/export.json`; confirm the Qwen3.5-4B licence; after the SFT run, follow `docs/MODEL_EXPORT.md`; approve the public upload.
- **Next:** P18 Chronicler endpoint.

### 2026-10-07 — Session 6 (P18)
- **Done:** P18 Chronicler endpoint + TTS recap kind + Chronicle screen story/Listen/share (D-61). No paid calls were made (LLM and ElevenLabs mocked).
- **Tests:** API 664 pytest (15 new: LLM path, hallucinated-place rejection + retry, double hallucination → fallback, wrong stats rejected, LLM down/unconfigured → fallback, idempotency, rewrite on new completion, empty week, per-device, DB down, TTS recap + ownership + kind/target validation), ruff + mypy --strict clean; web 85 vitest (4 new) + 10 Playwright, lint + typecheck clean; training 24 pytest.
- **Needs the user:** OK the 1800-char recap TTS cap (or keep 600 and let recaps use the free browser voice).
- **Next:** P19 Sentry agent tracing polish.

### 2026-10-09 — Session 7 (P19, P20)
- **Done:** P19 Sentry agent tracing finished (D-62, D-63) — the code was already in the tree from an interrupted session; this session verified the `gen_ai.*` convention against the current Sentry docs, found and closed a scrubbing gap, and wrote the two decision entries the code was already citing. P20 red-team + security + privacy pass (D-64), `docs/SECURITY.md`, `scripts/scan_secrets.py`.
- **Two findings worth remembering:** (1) `before_send_span` never fires without `trace_lifecycle="stream"` and streamed `gen_ai` spans skip `before_send`/`before_send_transaction` entirely, so a coordinate set on a chat span went out verbatim — scrubbing now happens in `ScrubbedSpan` where the data is authored. (2) OSM place names reached the prompt unsanitized; OSM is world-writable, so that was an injection vector into both the Quest Master and the Chronicler.
- **Tests:** API 812 pytest (ruff, mypy --strict clean), of which 221 red-team; web 93 vitest, eslint + tsc clean, build OK. pip-audit (runtime + dev) and npm audit both clean. Secret scan clean over the tree and every commit, verified against 5 planted keys.
- **Not run:** red-team against the real tuned model (no GGUF exists yet — P17 has never been run); the proposed CSP (needs a deploy to verify).
- **Needs the user:** the four open items in `docs/SECURITY.md` §4 — CSP, `X-Frame-Options`, whether to hide `/docs` in production, and the tuned-model red-team. Also still open from earlier sessions: the recap TTS cap, the base-model choice and Render plan, and a LICENSE file.
- **Next:** P21 field-test tooling.

### 2026-10-10 — Session 8 (P20 closeout)
- **Done:** the three open P20 security items (D-65) — CSP + `X-Frame-Options` on `sqm-web`, and the public schema routes gated on `ENV`. `docs/SECURITY.md` §2 rows flipped OPEN/PARTIAL → PASS with the evidence, and a new §2.1 recording what the CSP allows, how it was verified, and what the check does **not** cover.
- **Worth remembering:** the CSP checker's first run passed `/map` while the page was rendering its empty state — no quest in storage means Leaflet never mounts, so the tile origin and Leaflet's inline styles, the two most CSP-sensitive things in the app, were untested. A "0 violations" run is only evidence if the page is also asserted to have rendered; the script now seeds an accepted quest and requires real tiles.
- **Tests:** API 824 pytest (12 new; ruff + ruff format + mypy --strict clean); web 93 vitest, eslint + tsc clean, build OK, 10 Playwright e2e; `npm run check:csp` → 0 violations across 11 routes.
- **Not done:** P17 export — there is no SFT run to export, so no GGUF exists; the chain P14 → P15 → P17 spends money and needs its own session plus a U5 cost check. The deploy keeps `sqm-llm` with `MODEL_URL`/`MODEL_SHA256` as `sync: false` and the fallback engine serves quests meanwhile.
- **Next:** P21 field-test tooling, then the README and deploy docs.

### 2026-10-10 — Session 9 (P21)
- **Done:** P21 field-test tooling (D-66) — client-side field log, hidden `/settings/export` CSV page, `scripts/summarize_field.py` → `evals/field.md`, and the `X-Quest-Source` header that makes "% fallback quests" measurable at all.
- **Worth remembering:** the CSV needed `source`, and the client had no way to know it — the server stores it on the quest document and returns nothing. Rather than grow the quest schema (which is also the LLM's output contract, guarded by V1 and a hash test), it goes out as a response header; a custom header is invisible to `fetch()` unless CORS exposes it, which is its own test.
- **Tests:** API 837 pytest (13 new: 11 CLI tests for the summarizer, 2 for the header incl. the CORS exposure; ruff + ruff format + mypy --strict clean); web 119 vitest (26 new), eslint + tsc clean, build OK, 10 Playwright e2e; `npm run check:csp` → 0 violations across 12 routes, now including `/settings/export` with the blob CSV download actually clicked.
- **Ran it, with synthetic data:** 10 synthetic rows through `summarize_field.py` → a complete `field.md`, and that file placed in `evals/` and built: the story page parsed all 13 rows into the Receipts scene. Both artifacts were then deleted — **`evals/field.md` is deliberately absent**, because the only field data that exists is synthetic and the scene must stay hidden until a real walk produces a CSV.
- **Needs the user:** one real field test — walk a quest (or a few), then `/settings/export` → `python scripts/summarize_field.py <file.csv>`. That is the only way `evals/field.md` is allowed to exist. Still open from earlier sessions: the recap TTS cap, the base-model choice and Render plan, a LICENSE file, and P17 (no SFT run yet).
- **Next:** P22 README, deploy hardening, release.

### 2026-10-10 — Session 10 (P22)

- **Did:** wrote the root `README.md` (the submission deliverable from PROJECTPLAN §11) and five
  hand-authored SVG system diagrams in `docs/img/`: core loop with a screen-state timeline,
  system architecture, the `/v1/quests/generate` pipeline, the privacy boundary, and the
  training/export/eval pipeline. Diagrams use the app's own design tokens, carry `<title>`/`<desc>`
  for screen readers, and were each rendered in Chromium and inspected before being committed.
- **Decision (D-67):** diagrams are inline SVG committed to the repo, not generated images and not
  Mermaid. Reason: they render on GitHub and in the DEV post without a build step, they stay
  diffable, and text in them can be read by a screen reader. Two authoring traps found while
  rendering: a presentation `fill=` attribute on `<text>` loses to any CSS class rule (so the dark
  Walk Mode card had invisible text until the overrides became inline `style=`), and narrow boxes
  silently overflow rather than wrap.
- **Honesty constraints applied:** the README claims no fine-tune result, no latency table and no
  field numbers, because `evals/` holds none. The training diagram carries a "Status, stated
  plainly" panel saying the paid run and export have not been executed. The privacy section uses
  the §9.3 wording verbatim and explicitly refuses the phrase "fully offline". Every number quoted
  in the Testing section is pasted from a command run this session.
- **Verified this session, nothing from memory:** API 837 pytest passed in 43.05 s; web 119 vitest
  across 15 files; 10 Playwright e2e passed including the full loop and the LLM-down fallback;
  `ruff check` clean, `ruff format --check` 82 files, `mypy --strict` clean on 54 files; web
  `typecheck` and `lint` clean; `scan_secrets.py` CLEAN on both the working tree and full git
  history. Also ran the API locally with no Mongo and no LLM: `/healthz` returns
  `{"status":"ok","db":"unknown","llm":"down"}` and `/v1/quests/generate` returns the documented
  `db_unavailable` 503 in 41 ms, which is the §2.4 behaviour, not a bug. The deterministic fallback
  engine was then driven directly with no database, no network and no model, and its output is
  quoted in the README.
- **Still open, unchanged by this session:** a LICENSE file (the README says plainly that no grant
  is implied until one exists), P17 (no SFT run, so no tuned model and no eval numbers), one real
  field test to produce `evals/field.md`, gate G2 on a WebGPU device, and the first deploy (the
  real API host still has to replace the placeholder in the CSP `connect-src`).
- **Next:** LICENSE, first Render deploy, then the DEV post.

### 2026-10-10 — Session 11 (licence, story copy)

- **Did:** added the MIT `LICENSE` (D-68) and replaced the README's "a project licence has not been
  chosen yet" paragraph with a pointer to it, scoped so the third-party terms above it still stand.
  Stripped the em dashes from the story page's visible copy (`apps/web/src/story/Story.tsx`): seven
  spots now use a colon, a comma or a full stop. The two remaining `—` in that file are a code
  comment and a docstring, which no player sees, and the `'—'` in the receipts table is the
  empty-cell glyph for a metric the eval files do not carry, not prose.
- **Not done, and not faked:** `evals/` is still empty, so the README and the story page still show
  no fine-tune result, no latency table and no field numbers. Both of those need something this
  session cannot produce: P17 is a paid Tinker run (CLAUDE.md requires asking before spending), and
  `evals/field.md` needs one real quest walked outside and exported from `/settings/export`. No
  number was written by hand anywhere.
- **Verified this session:** web `typecheck` and `lint` clean; 119 vitest tests across 15 files
  passed. The story e2e spec asserts headings are visible, not their wording, so the copy change
  does not touch it.
- **Still open:** P17 (no SFT run, so no tuned model and no eval numbers), one real field test for
  `evals/field.md`, gate G2 on a WebGPU device, and the first Render deploy (the real API host still
  has to replace the placeholder in the CSP `connect-src`).
- **Next:** first Render deploy, then the DEV post.

### 2026-10-10 — Session 12 (scrollytelling performance and scenery)

- **Did:** reworked the motion layer of the story page only (`apps/web/src/story/Story.tsx`,
  `apps/web/src/story/story.css`); no copy, palette, component or API change. The nine scenes each
  ran their own scroll + resize listener and wrote `--progress` raw, and scene 6 called `setState`
  once per frame, re-rendering seven medallions at scroll rate. They now share one listener and one
  rAF loop that eases each scene's progress with a ~70 ms time constant, skips writes under 0.001,
  parks itself when everything has settled, and quantises the React callback to twelfths. Animated
  nodes declare `will-change` and use `translate3d`; `--progress` is registered with `@property`;
  stages get `contain: layout paint`. Scene span went 130vh → 170vh, so the beats play out over
  ~0.7 screens instead of ~0.3.
- **Scenery (D-69):** every scene now sits on the hero's `World` SVG behind a veil that is bright
  under the text and clear at the edges, page-coloured at the seams so the scenes read as one
  landscape; four `world-*` classes frame a different stretch of it, and it parallaxes with
  `--progress`. Walk Mode uses the `dusk` tone. Added hover/focus lift on parchment cards, chips,
  medallions and receipt rows, a scroll cue in the hero, and a top progress rail driven by
  `animation-timeline: scroll()` (absent where unsupported — no listener either way).
- **Two real bugs fixed, both pre-existing:** Walk Mode's dim was `progress * 0.86`, so its
  light-on-dark text was unreadable for the first half of the scene (now `0.3 + progress * 0.56`,
  same end state); and on phones every tall scene overflowed its sticky stage and lost 54–358 px
  off the bottom. MASTERSPEC §11.4 requires sticky scenes mobile-first at 360 px, so the fix was to
  size the content down in portrait (smaller phone mocks, tighter type and spacing, the decorative
  quest art hidden below `sm`) rather than drop the pinning.
- **Verified this session:** `lint`, `typecheck`, 119 vitest tests, 10 Playwright e2e tests and
  `check:csp` (12 routes) all pass; measured in headless Chromium that every scene fits its stage
  with no clipping at 412×823, 390×844, 360×740 and 1280×800, with no horizontal scroll.
- **Known limit, not faked:** at 360×740 and above nothing clips; at 360×640 (a short, older
  phone) four scenes still overflow by 29–81 px. That is better than before this session but not
  zero, and fixing it properly means cutting scene copy, which is a content decision.
- **Still open:** unchanged — P17, one real field test, gate G2, and the first Render deploy.

## P23 — live Pune happenings (2026-10-10)

- **D-70 — SerpApi's `google_events` engine is gone; we read `events_results` off
  `engine=google`.** The spec was written against the dedicated Google Events engine. It now
  returns `400 Unsupported ``google_events`` search engine.` SerpApi's changelog for 2026-08-24
  says: *"The Google Events API has been deprecated and no longer accepts new requests. Event
  data is still available via the `events_results` field of the Google Search API."*
  `scripts/fetch_events.py` therefore sends `engine=google` (constant `SERPAPI_ENGINE`) and
  parses the same `events_results` array. Verified against SerpApi's own changelog and a real
  response, not assumed.
  Sources: <https://serpapi.com/blog/serpapi-weekly-changelog-august-24-30-2026/>,
  <https://serpapi.com/google-events-api>.
- **D-71 — `SERPAPI_API_KEY` is never logged, and neither is a request URL.** The first real run
  printed the key, because `httpx`'s own INFO logger prints the full request URL and ours carries
  `api_key` as a query parameter. `fetch_events.py` now calls `silence_http_loggers()` before the
  first request and raises `SerpApiError` carrying only SerpApi's own message, never httpx's
  default (which embeds the URL). Covered by
  `test_http_loggers_are_silenced_so_the_api_key_cannot_be_logged` and
  `test_serpapi_error_reports_the_api_message_not_the_url`.
- **OQ-E1 (open) — the replacement payload cannot satisfy the spec as written.** Measured funnel
  in `evals/events_funnel.md`: 4 searches, 10 events, 0 kept. The `engine=google` events pack
  carries `title`, `type`, `date` (`"11 Oct"`), `time` (`"5:00"`, no meridiem), `address` and
  `thumbnail` — and no `link`, no `venue` object and no `ticket_info`. Three consequences, each
  needing an owner decision rather than a code ruling:
  1. No listing URL exists, so spec section 7.1's "show the listing URL" cannot be honoured from
     this source.
  2. `time: "5:00"` is ambiguous between 05:00 and 17:00. Guessing would produce exactly the
     plausible-but-wrong datetime the design forbids, so every entry is currently dropped as
     `no_time`.
  3. The only query that returns events (`events in Pune`) returns indoor paid theatre and
     concert listings. `workshops in Pune`, `heritage walk Pune` and `nature walk Pune` return no
     events pack at all, so the outdoor free daylight premise has no supply from this source.
  Options: accept a documented local-time convention for meridiem-less times; drop the listing-URL
  requirement; or change data source. Not decided here.
  Two further findings from the branch review, to be weighed before anyone "fixes" the parsing:
  4. The live pack prints the date day-first (`"11 Oct"`), while `_DATE_RE` requires
     `<Month> <day>`. So even with a meridiem convention adopted, every entry still lands in
     `no_time` until the date shape is handled too.
  5. The live pack carries no `description`, no `ticket_info` and no `venue`, so
     `banned_terms_hit` and `is_ticketed` both read empty strings. The funnel's `banned 0` and
     `ticketed 0` are therefore **not** evidence that the safety filters work on live data —
     resolving (2) alone would open the gate to indoor paid theatre listings with almost no
     filter. Any resolution of OQ-E1 must restore a real paid/indoor signal first.
- **D-72 — a third-party listing URL is only ever a plain `http(s)` link.** `safe_listing_url`
  in `app/services/serp_events.py` nulls any other scheme at ingest, and `safeListingUrl` in
  `QuestCard.tsx` re-checks before it becomes an `href`. Without both, a listing whose `link` is
  `javascript:…` would run script in our own origin one tap after "See the listing". Found in the
  P23 branch review; covered by tests on both sides.
- **D-73 — a borrowed meridiem is flipped rather than trusted, and no window may exceed 12 h.**
  `"11:00 - 1:00 PM"` used to parse as 23:00-13:00 (a 14-hour window, stored and shown as
  "Happening now" at 02:00). `_parse_times` now flips the borrowed meridiem when the start would
  otherwise sit after the end, and `parse_event_window` refuses any window longer than
  `MAX_DURATION_MIN` — a window that long means the string was misread.
- **D-74 — one malformed `events` document cannot fail a quest request.** `search_events` builds
  each candidate inside its own `try/except (ValidationError, KeyError, TypeError, ValueError)`
  and skips what it cannot read, and `fetch_events.py` validates every document against
  `EventDoc` before upsert (new funnel stage `invalid`). Previously a document whose `kind` was
  not a `PlaceKind` raised straight out of the Scout into a 500 on `/v1/quests/generate`,
  contradicting invariant 5 and spec section 7.2.
- **D-75 — the fallback engine gets the player's clock.** `FallbackInput.now` is threaded from
  `inp.context.local_time`, so V13 runs on the fallback path too. Before this, a quest the LLM
  wrote to an event starting after the player's window was rejected twice by V13 and then issued
  by the fallback engine, which had no clock and so skipped V13 entirely.
- **D-76 — event text is escaped at both Leaflet sinks, and `;`/`=` are stripped from tag
  values.** `bindTooltip` assigns its string with `innerHTML` just as `divIcon({ html })` does, so
  an event title really did inject an element through the tooltip (test watched failing). And
  `_fragment` now strips `;` and `=` as well as `:` and `,`, so a listing's `when_text` cannot
  forge a tag field (`when=…; kind=temple`) in the summary the model reads.
- **D-77 — the live pack's entry shape is flat, and the parser now reads it.** The migration off
  the deprecated `google_events` engine (D-70) changed the engine in `fetch_serpapi` but left
  `parse_events` reading the old nested entry, so every real payload lost its date, venue and
  link: `fetched 10, parsed 10, no_time 10, kept 0`. `events_results` on `engine=google` returns
  `{title, type, date: "11 Oct", time: "5:00", address: [...], thumbnail}` — strings, with **no
  `venue`, `link`, `description` or `ticket_info`**. `parse_events` now accepts either shape
  (pre-migration caches still parse), takes the venue from `address[0]`, and normalizes the bare
  `time`. This resolves the parsing half of OQ-E1; the safety half stands — with no
  `ticket_info` or `description`, `banned 0`/`ticketed 0` still are not evidence the filters bite
  on live data.
- **D-78 — `gl=in` prints the day first, so both date readings are tried and the leftmost wins.**
  `_DATE_RE` only matched `<Month> <D>`, so `"11 Oct"` never parsed; and on `"11 Oct 5:00 PM"` the
  month-first pattern happily matched `Oct 5` out of the clock time, yielding 5 October. A day
  followed by `:` is now rejected as a time, both readings are tried, and the leftmost real match
  wins — so `"Oct 11"` stays October 11.
- **D-79 — a bare time with no meridiem is read as PM, at the ingest boundary.** The live pack
  prints venue-local time with no AM/PM (`"5:00"`, `"7:30"`), and `event_time` refuses what it
  cannot read, so the assumption is made once in `serp_events._with_meridiem` rather than hidden
  in the parser. Hours 1-12 become PM because these listings are overwhelmingly evening shows. A
  morning event mislabelled this way fails the daylight filter and is dropped, which is the safe
  direction — it loses an event, never places one at the wrong hour.
- **D-80 — the geocode query is deduplicated per comma-token and carries the city.** With the
  venue taken from `address[0]`, the old join repeated it and omitted the city:
  `"Pashan Lake, Pashan Lake, Pashan"` misses a lake that `"Pashan Lake, Pashan, Pune"` resolves
  (verified against the live Nominatim API). Deduplication is per token, not per part, because
  Google also writes the city into the venue line (`"The Box Hub, Pune"`), where a whole-part
  check would miss it. Extracted as `geocode_query` so it is testable.
- **D-81 — the fallback engine must prefer a live happening over a nearer place.** It re-sorted
  candidates on `distance_m` alone, discarding the event-first order `merge_candidates` exists to
  create, so while the LLM was down a happening could never be chosen — P23 silently vanished
  exactly when the fallback mattered, even though `/v1/quests/generate` still succeeded
  (invariant 5). The sort key is now `(c.happening is None, c.distance_m)`; per-candidate
  usability is unchanged, so an event too far or too late loses to a place rather than blocking
  one.
- **D-82 — Atlas Search index quota is per cluster, and it silently disabled the whole feature.**
  `create_indexes.py` could not create `events_vec`: an M0 cluster allows **3** FTS indexes
  *across all databases*, and the third was `sample_mflix.movies.default` from the Atlas sample
  dataset. The script logged `could not create events_vec via driver (20)` and fell back to
  printing the JSON for the Atlas UI, which is easy to scroll past. Without the index
  `search_events` raises `OperationFailure`, `events_repo` catches it by design and returns `[]`,
  so the live section rendered nothing no matter what the collection held. Freed by dropping the
  sample dataset's search index (its 21,349 documents kept). **Any deploy needs a free FTS slot
  before P23 works at all**; a missing `events_vec` is invisible in the API response.
- **D-83 — the live Pune feed contains almost no eligible event, and that is the funnel working.**
  All 10 listings in the 2026-10-10 pull are indoor evening commercial entertainment (theatres at
  5-10 PM, gigs, a candlelight concert) at venues absent from `places`, whose taxonomy is
  deliberately outdoor-and-civic (`park, garden, heritage, water, viewpoint, cafe, library,
  museum, market, artwork, peak`) and has **no theatre or music-venue kind**. So `no_coords` and
  `night` are the safety invariants refusing nightlife, not bugs. `scripts/seed_dev_events.py`
  fabricates the missing daytime-outdoor case for local development; its documents carry
  `source="dev-seed"` and `dev/` ids and must never back a claim or a metric.
- **D-84 — the template library is the primary engine outside a seeded city, not a fallback.**
  `places` is filled offline by `seed_places.py` for one bounding box, and nothing fetches OSM on
  a request path, so for every player outside a seeded city the Scout returns zero candidates and
  always has. "Location is broken" was really "the map is empty": permission, rounding and the
  request were all working, and the engine was correctly dropping to the seven place-less
  templates every single time. Live Overpass lookup at request time was designed and deliberately
  **not** built (it puts an unbounded third-party call in front of every quest); the chosen fix is
  a much larger `ANYWHERE_TEMPLATES` library plus more seeded cities. Templates moved out of
  `fallback_engine.py` into `agents/templates.py`; the engine keeps only selection logic.
- **D-85 — five of the requested quests could not be built as written, and two not at all.**
  The curated list was run through the production validators, not eyeballed. Dropped outright:
  a guided **foraging** walk (§9.1 bans foraging; `forage` is a V4 banned term) and a **solo
  overnight** (isolation, and the engine caps a quest at 120 minutes). Reworded: "don't turn back
  until you're lost" → a street you have never walked plus five turns and your own way back
  (`isolated` is banned, and getting a player lost on purpose is indefensible); "stay out until
  it's dark" → ends before dark (V5); "cycle somewhere easier to drive" (`drive` is banned);
  oldest/newest **pub** → oldest/newest cafe (§9.1 alcohol); park people-watching → a story about
  the oldest tree (the P20 red-team's `surveil` rules). The validators were not touched
  (invariant 1).
- **D-86 — templates gained an hour window and a minimum slot, because the library needed them.**
  Seven short templates never exposed it, but "watch the sunrise" offered at 6 PM and a
  90-minute pottery class squeezed into a 20-minute slot by `min(activity_min, minutes_available)`
  are both quests nobody can do. `Template.hours` gates on the player's local hour and is skipped
  entirely when the engine has no clock rather than guessing; `Template.min_minutes` keeps long
  quests out of short slots. `indoor` is now a field per template, replacing the
  `INDOOR_PLACELESS` title set, so bad-weather filtering no longer depends on string matching.
- **D-87 — "Fruit Run" had never once been served, and no test noticed.** Its objective said
  "pick the best-looking fruit", which the P20 red-team's `pick_and_eat` rule reads as
  harvesting; the rule exempts "pick **out**", which the template's own briefing already used.
  `_passes` therefore rejected every composition of it and the engine moved on silently — a
  template can fail validation forever and look exactly like a template that is merely unpopular.
  The new table test in `tests/test_templates.py` runs every template through `validate_quest` and
  the lint for every persona, which is what surfaced it; the objective now matches the briefing.
- **D-88 — a place-less quest is no longer always `common`.** `test_generate_with_no_places...`
  asserted `rarity == "common"`, which held only while every place-less template was ≤ 20 minutes.
  With hour-long ones the quest seed (`uuid4().int`, random per request) made that assertion
  seed-dependent, so it passed alone and failed in a full run. It now asserts
  `rarity_for(est_minutes, None)` — stronger and deterministic — plus never `legendary` (D-35).
- **D-89 — the Journal keeps photos in IndexedDB on the device, and nothing uploads them.**
  The ask was "upload as many photographs as possible", which §9.3 and invariant 2 forbid: there
  is no image upload endpoint and photos never leave the phone. Built instead as unlimited
  on-device storage. `localStorage` cannot hold blobs (and caps around 5 MB), so this is the one
  place in the app that uses IndexedDB. Two consequences stated on the page itself: nothing is
  backed up, and "delete my data" had to learn to clear IndexedDB because `clearAppStorage`
  only reaches `localStorage`.
- **D-90 — the canvas downscale is a privacy step, not just a size one.** Every picked photo is
  re-encoded through a canvas at ≤ 1600 px, which drops the EXIF block and with it the GPS tag a
  phone camera writes into a picture. Storing the original `File` would be simpler and would put
  the coordinates of the player's home into the journal, so `downscale` must not be optimised
  away. This is stricter than §9.3 requires, since the photo never leaves the device either way.
- **D-91 — the Journal unlocks on the first completed quest, from either source.**
  `isJournalUnlocked` is `localStorage` flag OR server `quests_completed > 0`. The flag is set in
  both completion paths in `QuestProvider` (including the offline retry) so the Journal opens
  with the API unreachable; the server count covers a player whose local flag was cleared but
  whose history is real. The reducer stays pure, so the write does not live there. The `/journal`
  route stays reachable while locked and renders its own sealed panel, so a bookmark never 404s.
- **D-92 — quest context reaches the Journal through router state, not the URL.** The reward
  screen's "add this to your journal" passes `{questTitle, placeName, category}` as React Router
  state. A query string would write a real place name into browser history for no benefit.
- **D-93 — "play in the demo area" becomes "pick a city", because the demo area was the only
  answer the app had.** A player whose GPS puts them outside every seeded bbox, or who declines
  the permission, was offered Pune or nothing. The consent sheet and the post-failure error now
  both open a picker over `SEEDED_CITIES`, so anyone anywhere can play somewhere with real named
  parks, markets and libraries. The stored choice gains a `city:<slug>` form; the old `demo`
  value is still honoured so an existing device is not re-prompted after an update, and an
  unknown slug falls back to Pune rather than failing. No geocoding and no free text: the player
  taps a name from a fixed list, which keeps §9.3 intact.
- **D-94 — `SEEDED_CITIES` in the web app must stay in step with `scripts/seed_cities.py`.**
  The web needs city centres to offer the picker, and there is no endpoint that serves them
  (adding one is an API contract change). So the list is duplicated, with each centre being the
  middle of that city's bbox. The failure mode is specific and worth stating: a city listed here
  but never seeded promises a player real places and hands them place-less quests.
- **D-95 — a city's place count proves Overpass answered, not that the Scout will find
  anything.** `check_cities.py` counts what `search_places` actually pre-filters on: the 3x3
  geohash-5 block around the city centre (`cells_around`). That is the number that decides
  whether a player standing there gets a place-based quest. It exits non-zero on an empty city,
  which is how Toronto and Singapore were caught sitting in the web app's picker with zero
  places behind them after Overpass refused them three times.
- **D-96 — Overpass 504s are the normal case for a city-sized bbox, not an error to pass on.**
  Across the seeding runs, 7 of 12 cities returned 504 or 429 at least once; every one of them
  succeeded on a retry, Toronto and Singapore only on a second invocation. The query asks for
  `historic` with no value, which in a dense city is enormous (Berlin: 6,898 heritage rows,
  London: 2,187). Final state: **12 cities, 35,916 places**, verified with `check_cities.py`.
