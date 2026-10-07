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
- **A3 Legendary rarity:** "only offered if user opts in big quest day", but the request schema has no opt-in field. [P7: add optional `big_quest_day: bool = false` → needs approval since it changes the API contract.]
- **A4 indoor_only daylight rule (§7.1):** uses "est window", which isn't known at context time. [Use `minutes_available + 30` as the window, matching §9.1.]
- **A5 Banned-term lint (§9.2) needs word boundaries:** naive substring matching rejects "diverse" (dive), "driveway"/"drive-in" (drive), "the edge of the park" (edge of). [Word-boundary regexes; `drive` matched as a verb form (`drive`, `driving`, `drove`) but "driveway" allowed; `edge of` kept as written — it's strict but safe. Tests document each.]
- **A6 V12 (near-duplicate) is not pure** — it needs embeddings. [Validator takes precomputed vectors; the caller embeds.]
- **A7 `DELETE /v1/profile`** appears in §9.3 but not the §6.1 table. [Treat as part of the contract; implement in P10.]
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

---

## Verified Facts

| Date | Fact | Source |
|---|---|---|
| 2026-10-07 | llama.cpp server image `ghcr.io/ggml-org/llama.cpp:server`; binary at `/app/llama-server` (WORKDIR `/app`, `ENTRYPOINT ["/app/llama-server"]`); base stage installs `libgomp1 curl`; healthcheck `GET /health`. | https://github.com/ggml-org/llama.cpp/blob/master/.devops/cpu.Dockerfile |
| 2026-10-07 | llama.cpp flags `-m`, `--host`, `--port`, `-c/--ctx-size`, `-np/--parallel`, `--threads`, `--jinja` (on by default). JSON constraint on `/v1/chat/completions`: `"response_format": {"type": "json_schema", "schema": {...}}` (or `{"type":"json_object"}`). `GET /health` → 200 `{"status":"ok"}`, 503 while loading. | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md |
| 2026-10-07 | Render Blueprint: static site = `type: web` + `runtime: static` + `staticPublishPath`, with `headers` and `routes`; Docker = `dockerfilePath`, `dockerContext`, `dockerCommand`; private service = `type: pserv`; `fromService` properties `host`, `hostport` (also `envVarKey`); `disk` = `name`, `mountPath`, `sizeGB`; `env` is deprecated (use `runtime`); `render blueprints validate` needs Render CLI ≥ 2.7.0; JSON schema at https://render.com/schema/render.yaml.json. | Render's official skill pack: https://github.com/render-oss/skills/tree/main/skills/render-blueprints (render.com itself blocked from the build container) |
| 2026-10-07 | Atlas `$vectorSearch` pre-filter supports `$eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $exists, $and, $or, $not`; fields used in `filter` must be indexed as `type: "filter"`. Vector Search indexes can be created on M0. | Web search summary of https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/ — **re-check on the page** (blocked from container) |
| 2026-10-07 | Open-Meteo `GET https://api.open-meteo.com/v1/forecast` with `latitude`, `longitude`, `current=…`, `hourly=…`, `daily=sunrise,sunset,…`, `timezone=auto`, `forecast_days`; no API key for non-commercial use. | Web search summary of https://open-meteo.com/en/docs — **re-check** (blocked from container) |
| 2026-10-07 | Latest PyPI versions at scaffold: fastapi 0.142.2, pydantic 2.13.5, pydantic-settings 2.15.0, httpx 0.28.1, pymongo 4.18.2, slowapi 0.1.10, sentry-sdk 2.71.0, fastembed 0.8.1, pygeohash 3.5.1, uvicorn 0.54.0. | `pip install` in the build container |

---

## Build-environment notes (cloud session 2026-10-07)
Blocked by the egress policy: `devrelay.com`, `render.com`, `mongodb.com`, `open-meteo.com` / `api.open-meteo.com`, `overpass-api.de`, `huggingface.co` (so the fastembed model can't be downloaded here — embedding tests use a fake embedder; `docker build` of the API must run on Render or locally). PyPI and npm are reachable.
