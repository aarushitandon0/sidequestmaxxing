# MASTERSPEC.md — Sidequestmaxxing

> **Status:** v1.0 (draft for build) · **Owner:** Aarushi · **Challenge:** DEV "Touch Grass" (open-source AI)
> **Rule:** This file is the single source of truth. If code and spec disagree, fix the code or change this file in the same commit. Never let them drift.

---

## 0. How to read this document

- `MUST` / `MUST NOT` = non-negotiable. `SHOULD` = default unless a reason is written down. `MAY` = optional/stretch.
- Items tagged **[VERIFY]** are things I could not confirm from docs while writing this spec. Claude Code (or you) must check the current docs before relying on them. They are collected in section 15.
- Priorities: **P0** = demo dies without it. **P1** = needed to win. **P2** = stretch.

---

## 1. Product

### 1.1 One-liner
Sidequestmaxxing turns your real neighbourhood into a game: an open-source "Dungeon Master" writes personalised real-world side quests, **talks to you through your earbuds**, and only asks for the screen again to verify and reward you.

### 1.2 Problem
Most "outdoor" apps are maps you stare at. The challenge theme says the screen should be the *shortest part* of the experience. So the product is designed backwards: **minimum screen time, maximum time outside**.

### 1.3 Core loop (the whole product in 6 steps)
1. **Open** (≈20 s): app reads context (time, weather, daylight, your free minutes, mood, interests).
2. **Quest**: the Dungeon Master proposes one quest grounded in a real nearby place.
3. **Brief**: the DM *speaks* the briefing (ElevenLabs voice; browser speech as fallback).
4. **Walk Mode**: the screen goes dark/minimal. You go live the quest.
5. **Verify**: take one photo; an on-device Gemma model checks it. The photo never leaves the phone.
6. **Reward**: XP, skill-tree level-ups, and a weekly auto-written "Chronicle" of your adventures.

### 1.4 Non-goals (MUST NOT build)
- No accounts/passwords/social feed/chat. (Anonymous device ID only.)
- No location history storage. No raw GPS stored server-side.
- No quests that require driving, night-time isolated travel, private property, water/heights/climbing, or approaching strangers.
- No payment, ads, or in-app purchases.
- No multiplayer in P0/P1. (Squads = P2.)

### 1.5 Dungeon Master personas (user-selectable)
| id | Voice |
|----|-------|
| `chill` | Calm, friendly, a bit funny |
| `dramatic` | Over-the-top fantasy narrator |
| `nature_nerd` | Delighted by trees, birds, geology facts |
| `sarcastic` | Dry humour, never mean, never about the user's body/identity |

### 1.6 Success metrics (these become the numbers in the post)
Collect and report **real** numbers only. Never invent or round up.
- Quests completed in field tests, total minutes outside.
- **Screen share**: `screen_visible_seconds / quest_elapsed_seconds` per quest (target median < 10%).
- Fine-tune vs baseline deltas (section 10).
- Latency p50/p95 and estimated cost per quest on Render.
- Number of friends/testers who completed ≥ 1 quest (even 3–5 is a great story).
- Source of the field numbers (P21): the app logs one row per finished quest **in the browser
  only** (no coordinates, no place names), the player exports it as CSV from `/settings/export`,
  and `scripts/summarize_field.py` turns the CSV(s) into `evals/field.md`. Field numbers in the
  README/post must come from that file, never from a hand count.

---

## 2. Open-source strategy and partner strategy

### 2.1 What is open and why it matters (the writing spine)
| Open piece | Role | Honest "why open won" argument |
|---|---|---|
| Open-weight base model (Qwen3 small, Apache-2.0 **[VERIFY exact model + license]**) fine-tuned via Tinker | Quest Master + Chronicler | We *changed the model's behaviour* (personality, schema, safety, grounding) with LoRA and **measured** the improvement; a closed API can't be tuned or served the same way. |
| `llama.cpp` server | Inference runtime | Runs on a plain CPU instance; same binary runs on a laptop. Constrained JSON decoding (grammar). |
| Gemma 3n (open weights) in the browser | Photo verification | Photos stay on-device. Privacy is architectural, not a promise. |
| OpenStreetMap + Overpass + Open-Meteo | World data + weather | Open data, no API key, no per-call cost. |
| BGE-small embeddings (open) via fastembed | Semantic place search | Runs on CPU, no embedding API bill. |

### 2.2 Closed/hosted pieces (be upfront about these in the post)
Render (hosting), MongoDB Atlas (data), ElevenLabs (voice), Sentry (tracing), Tinker (training service). Rules:
- The **core intelligence is open-weight and exportable** (we download the tuned weights).
- Every closed dependency has a **fallback** (section 2.4).
- The post MUST say which pieces are not open. Honesty is a writing-quality signal.

### 2.3 Prize mapping (what we must *demonstrate* for each)
| Category | Our use | Evidence to include in the post |
|---|---|---|
| **Render** | Whole stack on Render: static PWA + FastAPI + **private service running llama.cpp (AI runtime)** with persistent disk, via `render.yaml` Blueprint | Architecture diagram, `render.yaml`, screenshot of 3 services, latency numbers |
| **Tinker** | LoRA fine-tune of a small open model into the Dungeon Master | Baseline-vs-tuned table on a held-out set (validity, grounding, safety, diversity, latency/cost) |
| **Gemma** | Gemma 3n multimodal in the browser verifies photos locally | Demo clip, accuracy on a small labelled photo set, privacy statement |
| **ElevenLabs** | Spoken DM briefing so you can put the phone away | Demo clip, count of voice-first quests, char budget policy |
| **MongoDB Atlas** | Atlas Vector Search over places + per-device quest memory | Index definitions, "avoid repeats" before/after example |
| **Sentry** | Agent tracing across Scout → Quest Master → validators, latency/tokens | Trace screenshots + one real bug found/fixed using traces |
| **DevRelay / session sharing** (optional) | Saved agent session embedded in post | Link/embed |

> Priority if time runs short: **Render > Gemma > Tinker > ElevenLabs > MongoDB > Sentry**. (Render hosts everything; Gemma+Tinker are the "open" proof; the rest are cheap add-ons.) Confirm in the official prize rules whether one project may win several categories **[VERIFY]**.

### 2.4 Fallback matrix (the demo MUST NOT die because one vendor fails)
| Dependency | Failure | Fallback |
|---|---|---|
| llama.cpp service down / slow | timeout > 25 s or HTTP error | **Deterministic template quest engine** (`fallback_engine.py`) generating valid quests from the same candidates |
| ElevenLabs down / budget hit | HTTP error / budget exceeded | Browser `speechSynthesis` |
| Gemma in browser unsupported (no WebGPU, low RAM, model not downloaded) | feature detect fails | **Check-in verification** (geolocation within 300 m) or **Honor mode** (50% XP) |
| Overpass API slow | timeout | Use cached `places` in Atlas; ship a seed snapshot for the demo city |
| Atlas unreachable | connect error | API returns 503 with friendly message; demo uses recorded video as insurance |
| Open-Meteo down | error | Omit weather; context says `weather: unknown` |

---

## 3. Architecture

```
 ┌───────────────────────────── Phone / Laptop browser (PWA) ─────────────────────────────┐
 │ React UI  ── Walk Mode (screen-light)  ── Camera ──► Gemma 3n (MediaPipe, WebGPU)      │
 │   │  screen-time tracker (Page Visibility)             └─► {match, confidence, seen}   │
 └───┼─────────────────────────────────────────────────────────────────────────────────────┘
     │ HTTPS (X-Device-Id)
 ┌───▼──────────────────────────  Render  ──────────────────────────────────────────────────┐
 │  sqm-web (static)      sqm-api (FastAPI, Docker)                 sqm-llm (private svc)    │
 │                        ├─ Context Builder (time, Open-Meteo)     llama.cpp llama-server   │
 │                        ├─ Scout (Atlas Vector Search + OSM)  ──► fine-tuned GGUF on disk  │
 │                        ├─ Quest Master client (JSON schema)  ◄── /v1/chat/completions     │
 │                        ├─ Validators + safety lint + fallback                              │
 │                        ├─ XP/Profile/Memory                                                │
 │                        ├─ Chronicler (weekly recap)                                        │
 │                        └─ TTS proxy ──► ElevenLabs                                         │
 └─────────────┬──────────────────────────────────────────────────────────────────┬─────────┘
               │                                                                    │
        MongoDB Atlas (places+vectors, quests, completions, memories)         Sentry (traces)
```

### 3.1 Sequence: Generate quest
1. Client → `POST /v1/quests/generate` with coarse location (lat/lng rounded to 3 decimals), minutes, radius, mood, interests, persona.
2. API **Context Builder** adds local time, daylight window, weather (Open-Meteo).
3. **Scout**: compute `cell5` geohashes (centre + 8 neighbours) → Atlas `$vectorSearch` on `places` with filter `cell5 ∈ cells`, query vector = embedding of `sanitized interests + a fixed mood phrase` (recent categories are *not* embedded — "avoid X" would pull results toward X; diversity is handled by the memory check and a max-3-per-kind cap instead). Post-filter by haversine distance ≤ radius and by safety/time rules (indoor-only, daylight for daylight-only places, round-trip walk + 10 min ≤ minutes available) → top 8 **candidates**.
4. **Memory check**: `$vectorSearch` on `memories` (filter `device_id`) to find recently similar quests; drop candidates/themes seen in the last 14 days.
5. **Quest Master**: call sqm-llm with system prompt + context JSON + candidates; constrained to JSON schema.
6. **Validators** (section 7.4). On failure → one retry with the failure reasons appended; on second failure → fallback engine.
7. Server assigns `id`, `rarity`, `xp` (never the LLM). Save to `quests`. Return.

### 3.2 Sequence: Verify + complete
1. Client runs Gemma locally on the photo → `{match, confidence, seen}`.
2. Client → `POST /v1/quests/{id}/complete` with verification result (no photo), `screen_seconds`, `elapsed_seconds`, optional coarse check-in.
3. Server validates (state machine, time bounds, proximity if provided), computes XP, writes `completions`, upserts `memories`, updates `users.skills`.
4. Return `{xp_awarded, level_ups[], streak}`.

### 3.3 Sequence: Weekly Chronicle
`POST /v1/recap/weekly` → gather last 7 days completions (the 7 local days ending today, by `local_date`) → Chronicler prompt → validators R1–R7 (one retry) → facts-only template on failure → 180–260 word story + 3 stats (always server-computed) → store in `recaps`, one per (device, `week_start`); a repeat call returns the stored recap unless the week's completions changed → return (optionally spoken via `/v1/tts` kind `recap`). An empty week returns `source: "empty"` and stores nothing.

---

## 4. Tech stack (pin versions at scaffold time; record in lockfiles)

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React 18 + Vite + TypeScript, Tailwind, `vite-plugin-pwa`, React Router, TanStack Query, Leaflet (OSM tiles, attribution required) | Static build on Render |
| On-device AI | `@mediapipe/tasks-genai` with **Gemma-3n E2B** (`.litertlm` web build) | MediaPipe LLM Inference is in **maintenance-only mode** per Google docs; still works for Gemma-3n **[VERIFY]**. Requires WebGPU. |
| API | Python 3.12, FastAPI, Pydantic v2, `httpx`, `motor` or `pymongo` async, `slowapi`, `sentry-sdk`, `fastembed`, `pygeohash` | Docker on Render |
| Inference | `llama.cpp` server image, GGUF Q4_K_M | Private service + disk |
| Training | Tinker Python SDK + Tinker Cookbook (docs: tinker-docs.thinkingmachines.ai) | **Read docs first; do not guess the API.** |
| DB | MongoDB Atlas (M0 free tier) with Vector Search | **[VERIFY]** vector search availability on tier |
| Voice | ElevenLabs TTS (`eleven_flash_v2_5` or current low-latency model) | Endpoint verified from the official SDK (D-54); model limits **[VERIFY]** |
| Observability | Sentry (backend + frontend) with `gen_ai.*` spans | **[VERIFY]** span op names |
| Data | OSM via Overpass; weather via Open-Meteo | Respect usage policies; cache aggressively |

---

## 5. Data model (MongoDB)

Database: `sqm`. All timestamps UTC ISO-8601 (`datetime` in Mongo).

### 5.1 `places`
```json
{
  "_id": "node/123456",
  "name": "Vetal Tekdi Viewpoint",
  "kind": "viewpoint|park|garden|nature_reserve|peak|water|heritage|artwork|market|cafe|museum|library|temple|other",
  "tags_summary": "tourism=viewpoint; ele=...",
  "loc": {"type": "Point", "coordinates": [lng, lat]},
  "cell5": "tek3r",
  "indoor": false,
  "needs_daylight": true,
  "text": "Vetal Tekdi Viewpoint — viewpoint — hill, scenic",
  "embedding": [384 floats],
  "source": "osm",
  "fetched_at": "2026-10-07T00:00:00Z"
}
```
Indexes:
- 2dsphere on `loc`.
- **Atlas Vector Search index `places_vec`**:
```json
{"fields":[
  {"type":"vector","path":"embedding","numDimensions":384,"similarity":"cosine"},
  {"type":"filter","path":"cell5"},
  {"type":"filter","path":"kind"}
]}
```

### 5.2 `quests`
`{_id, device_id, created_at, request_digest (hash of non-location request fields), quest{…schema 6.2…}, source: "llm"|"fallback", model: "name@sha", status: "offered|accepted|completed|skipped|expired", accepted_at, skipped_at?, expires_at}`. Offered quests expire 6 h after creation.
Index: `(device_id, created_at desc)`.

### 5.3 `completions`
`{_id, device_id, quest_id, completed_at, local_date, verification{method, match, confidence, seen}, elapsed_seconds, screen_seconds, screen_share, within_radius: bool|null, xp_awarded, category, place_id, place_name, title, note, result{…completion response…}}`
Index: `(device_id, completed_at desc)`; unique `(quest_id)`.

### 5.4 `users` (anonymous devices)
`{_id: device_id, created_at, persona, interests[], default_radius_m, skills{category: xp}, total_xp, streak_days, last_completed_date (local YYYY-MM-DD), utc_offset_min, settings{safe_mode: true, voice: true}}`

### 5.5 `memories`
`{_id: quest_id, device_id, ts, text, category, place_id, embedding[384], kind: "completed"|"skipped"}`
**Atlas Vector Search index `memories_vec`**: vector(384, cosine) + filters `device_id`, `ts` (so the memory check can pre-filter to the last 14 days).
TTL: delete after 90 days (index on `ts`, `expireAfterSeconds`).

### 5.6 `recaps`, `usage`
`recaps`: `{_id, device_id, week_start, text, stats, created_at}`.
`usage`: `{_id: "tts:YYYY-MM-DD", chars: int}` for the ElevenLabs budget guard.

---

## 6. API contract

Base: `/v1`. JSON only (except TTS audio). Header `X-Device-Id: <uuid v4>` required on all but `/healthz`. Errors: `{"error": {"code": "string", "message": "human readable"}}`.

### 6.1 Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness (+ `llm: ok|down`, `db: ok|down`) — no secrets |
| POST | `/v1/quests/generate` | Create a quest (response header `X-Quest-Source: llm\|fallback`, exposed via CORS, so a field test can count fallback quests; **not** part of the quest body) |
| POST | `/v1/quests/{id}/accept` | Start quest (sets timer, `accepted_at`) |
| POST | `/v1/quests/{id}/complete` | Submit verification result |
| POST | `/v1/quests/{id}/skip` | Skip (no penalty; used for memory) |
| GET | `/v1/profile` | XP, skills, streak, recent completions |
| PUT | `/v1/profile/settings` | persona, interests, radius, voice |
| DELETE | `/v1/profile` | Delete all data for this device (204) |
| POST | `/v1/recap/weekly` | Generate/fetch weekly Chronicle |
| POST | `/v1/tts` | `{quest_id, kind: "briefing"\|"hint"}` or `{recap_id, kind: "recap"}` → proxy to ElevenLabs → `audio/mpeg` (text taken from the stored quest/recap of this device, never from the client) |
| GET | `/v1/places/near` | (debug/demo) candidate places for a point |

### 6.2 Quest schema (the LLM outputs only fields marked 🤖; server fills the rest)
```json
{
  "id": "uuid",                       // server
  "title": "string (≤60)",            // 🤖
  "category": "explorer|naturalist|social|foodie|creative|fitness|mindful", // 🤖
  "briefing": "string (40–360 chars, 2nd person, spoken-friendly)",         // 🤖
  "objective": "string (≤140, ONE concrete action)",                        // 🤖
  "place_id": "string|null (must be in candidates)",                        // 🤖
  "est_minutes": "int 5..180",                                              // 🤖
  "verification": {"method":"photo|checkin|honor","photo_prompt":"string|null (≤100)"}, // 🤖
  "safety_note": "string (≤140, required)",                                 // 🤖
  "off_screen_tip": "string (≤100)",                                        // 🤖
  "rarity": "common|rare|legendary",  // server
  "xp": "int",                        // server
  "distance_m": "int|null",           // server (from place)
  "place": {"id":"","name":"","lat":0,"lng":0} // server (hydrated)
}
```
Rules: `verification.method="photo"` ⇒ `photo_prompt` non-null and **never about people/faces**. `place_id=null` ⇒ method ∈ {`photo`,`honor`}.

### 6.3 `POST /v1/quests/generate` request
```json
{
  "lat": 18.520, "lng": 73.856,        // rounded to 3 decimals client-side; server re-rounds
  "minutes_available": 45,
  "radius_m": 2500,
  "mood": "curious|tired|restless|social|calm|adventurous",
  "interests": ["birds","street food","history"],   // ≤ 6 items, each ≤ 24 chars
  "persona": "chill|dramatic|nature_nerd|sarcastic",
  "mode": "walk|transit_ok",
  "local_time_iso": "2026-10-07T17:30:00+05:30"
}
```
Validation: lat/lng in range; minutes 10–180; radius 300–6000; `interests` sanitized (letters, digits, spaces, `-`); mood from enum. **Free text never goes straight into a prompt** (prompt-injection control).

### 6.4 `POST /v1/quests/{id}/complete` request
```json
{
  "verification": {"method":"photo","match":true,"confidence":0.82,"seen":"a banyan tree with a signboard"},
  "elapsed_seconds": 2400,
  "screen_seconds": 140,
  "checkin": {"lat":18.521,"lng":73.855},   // optional, rounded
  "note": "optional ≤ 200 chars"
}
```
Server checks: quest belongs to device; state is `accepted`; `elapsed_seconds ≥ min(0.4×est_minutes×60, 240)`; `match=true && confidence≥0.6` for photo; if `checkin` present and quest has place → distance ≤ 350 m else `within_radius=false` (XP × 0.5). Idempotent on `quest_id`.

### 6.5 Rate limits (slowapi)
- generate: 6/min and 30/day per device.
- complete: 10/min.
- tts: 20/hour per device + global daily char budget (`TTS_DAILY_CHAR_BUDGET`). Max 600 chars per request (1800 for kind `recap`, D-61).
- recap: 10/hour per device (a cache hit is a read; a miss is one LLM call).

---

## 7. Agents

> Keep it **simple and debuggable**: plain Python functions with typed inputs/outputs and one Sentry span each. Do **not** add an agent framework unless a measured need appears.

### 7.1 Context Builder (deterministic)
Inputs: request. Outputs: `{part_of_day, weekday, daylight_minutes_left, weather{summary,temp_c,precip_prob}, indoor_only: bool}`.
Rules: `indoor_only=true` if thunderstorm, precip_prob ≥ 70% (worst hour in the quest window), temp ≥ 38 °C, or `daylight_minutes_left < 35` (no daylight quest can fit: 5 min + 30 min buffer). Per-place daylight ("`est + 30 ≤ daylight_minutes_left` for daylight-only places") is enforced by the Scout filter and V10. Sunrise/sunset come from Open-Meteo, with an offline solar calculation as fallback so daylight rules never depend on a vendor.

### 7.2 Scout (deterministic + vector search)
Described in 3.1. Output ≤ 8 candidates: `{id,name,kind,distance_m,tags_summary,indoor,needs_daylight}`.
If `< 1` candidate → LLM must still produce a place-less quest (`place_id=null`) or the fallback engine does.
Overpass fetch (seed script + lazy fill): kinds from `leisure=park|garden|nature_reserve`, `natural=peak|water|wood`, `tourism=viewpoint|artwork|attraction|museum`, `historic=*`, `amenity=marketplace|cafe|library`. Require `name`. Exclude `access=private|no`. Cache by `cell5`; **respect Overpass fair-use**; never fetch per user request more than once per cell per 24 h.

### 7.3 Quest Master (fine-tuned LLM)

**System prompt** (file: `prompts/quest_master.system.txt`; MUST be byte-identical in training and serving — enforce with a hash test):
```
You are the Dungeon Master of Sidequestmaxxing, a game played in the real world.
Write exactly ONE side quest as a single JSON object that matches the schema. Output JSON only.
Rules:
1. place_id must be copied from CANDIDATES or be null. Never invent places.
2. The objective is ONE concrete, safe, legal action doable within est_minutes.
3. The quest must keep the phone in the pocket. The only allowed phone use is one proof photo.
4. Respect SAFETY: public places only; daylight rules; no traffic, water, heights, climbing, private property,
   wild-food or wildlife contact, alcohol, or approaching/photographing strangers. Photo prompts never target people.
5. Match the persona voice. Keep briefing under 60 words, spoken style, no emojis, no hashtags.
6. Prefer categories the player has not done recently (see RECENT_CATEGORIES).
7. If CONTEXT.indoor_only is true, choose an indoor or covered place or a place-less quest.
8. Always include a short safety_note.
```
**User message**: a JSON object `{"context":{…}, "persona":"…", "mood":"…", "interests":[…], "minutes_available":45, "recent_categories":[…], "candidates":[…]}`.
**Call**: `POST http://${LLM_HOSTPORT}/v1/chat/completions` with `temperature 0.8`, `top_p 0.95`, `max_tokens 380`, JSON-schema-constrained decoding. Resolved (DECISIONS D-27): `response_format: {"type":"json_schema","json_schema":{"name":"quest","schema":<QuestDraft schema>}}` plus `chat_template_kwargs: {"enable_thinking": false}`.
Timeout 25 s. One retry with failure reasons appended as an extra user message.

### 7.4 Validators (pure functions; unit-tested; also used as the training filter and eval metric)
| id | Check |
|---|---|
| V1 | Parses as JSON and matches Pydantic schema |
| V2 | `place_id` ∈ candidates or null |
| V3 | `est_minutes` ≤ `minutes_available` and ≥ 5 |
| V4 | Banned-term lint on all strings (see 9.2) |
| V5 | `safety_note` present, 10–140 chars |
| V6 | Photo prompt not about people (regex + keyword list) |
| V7 | Lengths within bounds; briefing word count ≤ 70 |
| V8 | No URL, phone number, or email in any string |
| V9 | If `indoor_only` then place is indoor or null |
| V10 | If place `needs_daylight` and daylight insufficient → reject |
| V11 | Category ∈ enum |
| V12 | Not near-duplicate of a quest in last 14 days (embedding cosine < 0.9) |

### 7.5 Fallback engine (P0, deterministic)
Templates per `kind` × `category` with persona-flavoured phrasing; always passes V1–V11. Used when LLM fails, times out, or fails validation twice. Marked `source:"fallback"` and shown to nobody as an error.

### 7.6 Verifier (on-device Gemma)
**Prompt** (`prompts/verifier.gemma.txt`):
```
You are a strict photo checker. Task: decide if this photo shows: "{photo_prompt}".
Reply with JSON only: {"match": true|false, "confidence": 0.0-1.0, "seen": "<=12 words describing the main subject"}
If unsure, set match=false.
```
Accept if `match && confidence ≥ 0.6`. The model is stored in OPFS (resumable download from `VITE_GEMMA_MODEL_URL`, or imported from a file the player downloaded after accepting the Gemma terms — D-47/D-48). Load model only after explicit user opt-in (large download; Wi-Fi advisory); cache in browser storage; show progress; never block the rest of the app.
**Honesty note (put in post):** client-side verification can be spoofed. This is a single-player game, so that's acceptable; say so.

### 7.7 Chronicler
Same fine-tuned model (multi-task SFT: ~85% quest, ~15% recap). **System prompt** (`prompts/chronicler.system.txt`): write a 180–260 word second-person chronicle of the week from the completions list; use only facts provided; no invented places or events; end with one suggested sidequest *theme* for next week (not a specific place). Output JSON `{"text":"…","stats":{"quests":n,"minutes":n,"top_category":"…"}}`. Validators: word range, every named place appears in input, banned-term lint.

---

## 8. Game design rules (server-authoritative)

- **Rarity** (server): `common` if `est_minutes ≤ 30` and distance ≤ 1500 m; `rare` if `est_minutes ≤ 120` and distance ≤ 6000 m; else `legendary` (only offered if user opts in "big quest day").
- **XP**: `base = est_minutes × 2` → `× rarity (1 / 1.5 / 3)` → `× verification (photo 1.0 / checkin 0.8 / honor 0.5)` → `× 0.5 if within_radius=false` → `+20% if screen_share < 0.10` → `+10% if streak ≥ 3 days`. Round to int. Cap per quest 400.
- **Levels**: per-category `level = floor(sqrt(xp / 40))`; overall level = floor(sqrt(total_xp / 120)).
- **Titles** (flavour): e.g. Naturalist L3 "Leaf Whisperer"; keep a static table in code.
- **Streak**: consecutive local days with ≥ 1 completion.
- **Anti-abuse**: one completion per quest; min elapsed time; daily XP cap 800; generate rate limits.

---

## 9. Safety and privacy

### 9.1 Safety principles (MUST)
- Quests only in **public** places; never instruct entry to private property or restricted areas.
- Daylight-first: if `now + est_minutes + 30 min > sunset`, only indoor/lit public places.
- Heat/rain/storm → indoor or reschedule suggestion.
- Never: traffic crossing instructions, swimming/water edges, climbing/heights, foraging/eating wild plants, touching/feeding wildlife, alcohol, fireworks, drones, following or photographing strangers, talking to children, or going somewhere isolated.
- Always show `safety_note`, and show a persistent "Tell someone where you're going" tip on first run. A "stop quest" button is always visible.
- App states it is **not** an emergency or navigation tool.

### 9.2 Banned-term lint (V4) — starting list (extend in tests)
`swim`, `dive`, `climb` (except "climb the stairs at"), `cliff`, `edge of`, `trespass`, `private property`, `gate` + `jump`, `cross the highway`, `drive`, `drunk`, `alcohol`, `beer`, `forage`, `eat the wild`, `mushroom` (as food), `feed the` (animals), `strangers`/`stranger` in photo prompts, `follow someone`, `at night alone`, `midnight`, `fireworks`, `drone`.

### 9.3 Privacy (MUST)
- Client sends coordinates rounded to 3 decimals (~110 m). Server **does not store** user coordinates; it stores only `within_radius` booleans and place IDs.
- Photos never leave the device. API has no upload endpoint for images.
- `X-Device-Id` is a random UUID; no email, no name. "Delete my data" button → `DELETE /v1/profile`.
- Logs: no coordinates, no free text; Sentry `send_default_pii=False`, scrub `lat/lng`, `X-Device-Id` hashed.
- Field-test log (P21): kept in `localStorage` on the player's own device, capped at 500 rows, never sent anywhere. It holds date (local, no time), category, rarity, estimated/elapsed/screen seconds, verification method, quest source and the voice flag — **no coordinates, no place names, no titles, no photos**. Exported only by a deliberate tap on `/settings/export`; clearable there and wiped by `clearAppStorage()` on "delete my data".
- Be accurate in claims: **"photos and exact movements stay on your device; the server sees an approximate area to find nearby places."** Do NOT claim "fully offline" for the Render deployment.

### 9.4 Security (MUST)
- Secrets only in Render env vars / local `.env` (gitignored). `.env.example` committed with placeholders.
- CORS restricted to `WEB_ORIGIN`. Pydantic validation everywhere. Request body size limit 32 KB.
- ElevenLabs/Mongo/Sentry keys never exposed to the browser.
- Dependency pinning and `pip-audit`/`npm audit` run once before submission.
- **Never paste real secrets into an AI coding session** (DevRelay transcripts can be shared publicly).

---

## 10. Model training and evaluation (Tinker)

### 10.1 Goal
A small open model that, *without* needing a giant prompt, reliably emits valid, grounded, safe, varied, voice-consistent quests — and runs on a CPU instance.

### 10.2 Model selection (decision gate G1)
Candidates (must appear in Tinker's current "Models & Pricing" list): ~~`Qwen3-4B-Instruct-2507`, `Qwen3-1.7B`, `Llama-3.2-3B`~~ are no longer in the lineup (DECISIONS D-55); smallest available is `Qwen3.5-4B`, then `Qwen3-8B` / `Qwen3.5-9B`. Choose the largest that meets: Q4_K_M GGUF file + KV cache + runtime ≤ (instance RAM − 1 GB), and p50 generation latency ≤ 15 s on the chosen Render plan. Prefer Apache-2.0 licensed models. Disable "thinking" mode (use an instruct variant or template flag).
Gemma is **not** the fine-tune target (Tinker lists Qwen/Llama families **[VERIFY]**); Gemma is used on-device for vision.

### 10.3 Data (synthetic, programmatic, validator-filtered)
1. **Context generator** (`training/make_contexts.py`): sample from real seeded places (Atlas export) × random `{time, weather, minutes, radius, mood, interests, persona, recent_categories}`; include 8% empty-candidate cases and 10% `indoor_only` cases. Split places by *area* so test places are unseen: train/val/test = 3000 / 100 / 120 contexts.
2. **Teacher generation** (`training/gen_teacher.py`): use the strongest *open-weight* model available through Tinker sampling (or another open model) with a long, detailed instruction prompt + few-shot. Record teacher identity for the post. **MUST NOT** use outputs from models whose terms forbid training other models; check terms **[VERIFY]**.
3. **Filter**: keep only samples passing V1–V11; dedupe (embedding cosine > 0.92 within same persona); balance categories/rarity/persona. Target 2,000–3,000 clean examples after filtering.
4. **Recap examples**: ~400 synthetic week-logs → Chronicler outputs, filtered by recap validators.
5. Store dataset as JSONL chat format with the exact production system prompt. Publish the dataset script (not necessarily the data) in the repo.

### 10.4 Training
- LoRA SFT via Tinker; start from Cookbook defaults, sweep learning rate over 3 values; 2–3 epochs; keep best by val metric (validator pass-rate + loss).
- **Stretch (P2):** short RL/rejection-sampling round using validators as reward.
- Save run IDs/config in `training/runs/RUNS.md` (for the post).

### 10.5 Export (decision gate G3)
Download adapter → merge into base (PEFT `merge_and_unload`) → HF safetensors → `convert_hf_to_gguf.py` → quantize `Q4_K_M` → upload to a **public** Hugging Face repo → set `MODEL_URL`. **Evaluate the exact quantized GGUF that Render serves**, not only the full-precision model. **[VERIFY]** Tinker's weight-download/export procedure in docs.

### 10.6 Evaluation protocol (the heart of the Tinker prize and the post)
Held-out 120 contexts. Run **baseline** (same base model, same Q4_K_M quantization, best-effort prompt with 3 few-shot examples, **no fine-tune**) vs **tuned** (zero-shot with short system prompt). Run both **without** grammar-constrained decoding for the headline numbers (so we measure model quality), and also report *with* grammar (what ships).

| Metric | Definition |
|---|---|
| JSON validity | % passing V1 (raw decoding) |
| Grounding | % with place_id valid (V2) when candidates exist; % correctly null when none |
| Constraint adherence | % passing V3, V9, V10 |
| Safety lint | % passing V4–V6, V8 |
| Full pass | % passing V1–V11 |
| Diversity | mean pairwise embedding distance across 20 samples/context subset; distinct-category rate |
| Voice | blind pairwise preference (n≥40) by LLM-judge using a *different* model family **and** human rating on 20 pairs; report both, note judge bias |
| Latency | tokens/s and p50/p95 end-to-end on the Render instance |
| Cost | `$ per hour ÷ quests per hour` at measured throughput (label as estimate) |
| Prompt length | tokens per request (baseline few-shot vs tuned) |

**Acceptance for claiming improvement:** tuned ≥ baseline on Full pass by ≥ 10 absolute points, or a clear win on latency/cost at equal quality. Report negative results honestly.

---

## 11. Frontend spec

### 11.1 Screens
1. **Onboarding** (≤ 3 taps): persona, interests (chips), default radius, safety acknowledgement, voice on/off, optional "install verifier".
2. **Home / Quest Board**: big "Get a quest" button; current quest card; streak; level.
3. **Quest Card**: title, category/rarity chips, briefing, objective, estimated minutes, safety note, buttons: **Listen**, **Accept**, **Reroll** (max 3/day), **Skip**.
4. **Walk Mode** (the signature screen): near-black minimal UI, large elapsed time, one big **"I'm back"** button, "Stop quest" link, optional repeat-audio. Does not keep the screen awake. Plays audio hints.
5. **Verify**: camera capture → "Checking on your device…" → result → **Claim reward** (or retake / use check-in / honor).
6. **Reward**: XP animation (≤ 1.5 s), level-ups, screen-share stat ("Your screen was on for 4% of this quest").
7. **Profile / Skill Tree**: 7 categories with levels; recent quests; settings; delete data.
8. **Chronicle**: weekly story; Listen button; share as text.
9. **Map (optional)**: Leaflet with the quest place pin; OSM attribution.

Routes (D-49): `/` and `/story` landing; app at `/home`, `/onboarding`, `/quest`, `/walk`, `/verify`, `/reward`, `/profile`, `/chronicle`, `/settings`, `/map`; plus the hidden `/settings/export` (field-test CSV, P21 — reachable by URL only, never linked); PWA `start_url` `/home`. Visual design = the project design template (D-45).

### 11.2 Non-functional
- Installable PWA, manifest, icons, offline shell. Quest data cached after generation so Walk Mode works with no signal.
- Mobile-first (360 px), touch targets ≥ 44 px, WCAG AA contrast, visible focus, `prefers-reduced-motion` respected, audio always has a text equivalent.
- Camera/geolocation permissions requested **just in time** with a plain-language reason; every permission-denied path has a working alternative.
- Screen-time tracker: Page Visibility API; sum visible seconds between accept and complete; send `screen_seconds`.
- Performance: first load < 200 KB JS gzipped excluding the optional model; model download is opt-in, resumable, cached.
- Design tone: warm, outdoorsy, playful RPG; avoid generic purple-gradient AI look. Use the `frontend-design` skill if available.

### 11.3 States to implement everywhere
loading, empty, error (friendly), offline, permission denied, LLM-fallback (silent), rate-limited.

### 11.4 Scrollytelling story page (route `/story`, also the public landing at `/`)

**Purpose:** the first thing judges and readers see. It tells the product story as a scroll-driven narrative and links into the real app. The working app (Quest Board, Walk Mode, Verify) stays a normal minimal-screen UI; **do not make the in-quest experience scroll-driven** (that would contradict "screen is the shortest part").

**Scenes (one pinned/sticky stage per scene, 100-140 vh of scroll each):**
1. **Hero** - "Your city is the game." Slow parallax skyline/trees; one CTA to `/onboarding`.
2. **The problem** - a feed scrolls; a "screen time" bar fills. Caption: the theme rule, "the screen must be the shortest part".
3. **The Dungeon Master** - quest card types in beat by beat; a Listen button plays a pre-generated demo clip (`public/demo-audio/`).
4. **Walk Mode** - the UI fades to near-black as you scroll; an SVG route line draws itself (stroke-dashoffset) across a stylised map; pins pop.
5. **Verified on your device** - a photo slides into a phone outline; an "upload" arrow is shown blocked; caption states what the server does and does not see (MASTERSPEC 9.3 wording only).
6. **Skill tree** - 7 branches grow with scroll; levels count up.
7. **Receipts** - tuned vs baseline table and field stats, **rendered from `evals/results.json` and `evals/field.md` data at build time**. If a file is missing, the scene is hidden. No hand-typed numbers.
8. **Open vs closed** - honest two-column list of what is open and what is hosted (MASTERSPEC 2.1/2.2).
9. **Try it** - CTA, repo link, Render deploy link, credits (OSM attribution, models + licenses, partners used).

**Implementation rules:**
- Progressive enhancement: sticky stages + `IntersectionObserver` drive a `--progress` CSS variable per scene; use CSS scroll-driven animations (`animation-timeline`) only where supported, with the observer path as fallback. **No new animation library without approval** (CLAUDE.md); if one is proposed, justify the size.
- `prefers-reduced-motion`: render every scene as a static, stacked section with the final state visible; no parallax.
- Content must be fully readable with JS animation disabled; real headings, a skip link, alt text, captions for all audio.
- Perf budget: story route JS <= 120 KB gzipped on top of the shell; art is inline SVG/CSS (no autoplay video, no large images); test on a mid-range Android; keep scroll at 60 fps (animate only `transform`/`opacity`).
- Mobile-first; scenes must work in portrait at 360 px.
- Never show a claim on this page that is not in the claims ledger (PROJECTPLAN 8.3).

---

## 12. Render deployment

### 12.1 Services
| Service | Type | Notes |
|---|---|---|
| `sqm-web` | Static site | Build from repo root; SPA rewrite; security headers |
| `sqm-api` | Web service (Docker) | Docker context = repo root so `/prompts` is available |
| `sqm-llm` | **Private service** (Docker) + persistent disk | llama.cpp server; model downloaded once to `/data` |

### 12.2 `render.yaml` (starting point — **[VERIFY]** field names against the Blueprint spec at https://render.com/docs/blueprint-spec before first deploy)
```yaml
services:
  - type: web
    name: sqm-web
    runtime: static
    buildCommand: cd apps/web && npm ci && npm run build
    staticPublishPath: ./apps/web/dist
    headers:
      - path: /sw.js
        name: Cache-Control
        value: no-cache
      - path: /*
        name: X-Content-Type-Options
        value: nosniff
      - path: /*
        name: Permissions-Policy
        value: camera=(self), geolocation=(self), microphone=()
    routes:
      - type: rewrite
        source: /*
        destination: /index.html
    envVars:
      - key: VITE_API_BASE_URL
        value: https://sqm-api.onrender.com
      - key: VITE_SENTRY_DSN
        sync: false
      - key: VITE_GEMMA_MODEL_URL
        sync: false

  - type: web
    name: sqm-api
    runtime: docker
    dockerfilePath: ./apps/api/Dockerfile
    dockerContext: .
    plan: starter
    healthCheckPath: /healthz
    envVars:
      - key: ENV
        value: production
      - key: WEB_ORIGIN
        value: https://sqm-web.onrender.com
      - key: LLM_HOSTPORT
        fromService:
          type: pserv
          name: sqm-llm
          property: hostport
      - key: MONGODB_URI
        sync: false
      - key: MONGODB_DB
        value: sqm
      - key: ELEVENLABS_API_KEY
        sync: false
      - key: ELEVENLABS_VOICE_ID
        sync: false
      - key: SENTRY_DSN
        sync: false
      - key: TTS_DAILY_CHAR_BUDGET
        value: "20000"
      - key: FALLBACK_ON_LLM_ERROR
        value: "true"

  - type: pserv
    name: sqm-llm
    runtime: docker
    dockerfilePath: ./services/llm/Dockerfile
    dockerContext: ./services/llm
    plan: standard        # CHANGE after gate G1 (RAM must fit model + 1 GB headroom)
    disk:
      name: models
      mountPath: /data
      sizeGB: 10
    envVars:
      - key: MODEL_URL
        sync: false
      - key: MODEL_FILE
        value: quest.gguf
      - key: CTX_SIZE
        value: "2048"
```
**Known gotchas (read before deploying):**
1. If `sqm-web`/`sqm-api` names are taken, Render appends a suffix. After first deploy, **copy the real URLs** into `VITE_API_BASE_URL` and `WEB_ORIGIN` and redeploy both.
2. `LLM_HOSTPORT` is `host:port`; the API builds `http://$LLM_HOSTPORT`. Do not hard-code a port.
3. Persistent disks and private services require a paid plan. Check current pricing and any sponsor credit **before** committing **[VERIFY]**. Ask DevRelay for offers (see docs/DEVRELAY.md).
4. Check instance RAM on the current pricing page. A 4B Q4_K_M model needs roughly 3 GB plus KV cache; do **not** guess — measure at gate G1.
5. `fastembed` + FastAPI may exceed a 512 MB instance; if OOM, upgrade `sqm-api` one tier.
6. Free instances spin down and have no disks — do not use them for `sqm-llm`/`sqm-api` during the demo.

### 12.3 `services/llm` files
`Dockerfile`:
```dockerfile
FROM ghcr.io/ggml-org/llama.cpp:server
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```
`entrypoint.sh`:
```sh
#!/bin/sh
set -eu
mkdir -p /data/models
MODEL_PATH="/data/models/${MODEL_FILE:-quest.gguf}"
if [ ! -s "$MODEL_PATH" ]; then
  echo "Downloading model from MODEL_URL ..."
  curl -fL --retry 5 --retry-delay 5 -o "${MODEL_PATH}.part" "$MODEL_URL"
  mv "${MODEL_PATH}.part" "$MODEL_PATH"
fi
exec /app/llama-server -m "$MODEL_PATH" --host 0.0.0.0 --port "${PORT:-10000}" \
  -c "${CTX_SIZE:-2048}" -np 1 --threads "$(nproc)"
```
**[VERIFY]** image tag, binary path (`/app/llama-server`), and flag names against the current llama.cpp server README. Add a model checksum check (`MODEL_SHA256`) once the model is final.

### 12.4 `apps/api/Dockerfile` (key points)
Python 3.12-slim; copy `apps/api/requirements.txt`, install; **pre-download the embedding model at build** (set `FASTEMBED_CACHE_PATH` to a path inside the image); copy `apps/api/app` and `/prompts`; `CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}`; run as non-root user.

---

## 13. Observability (Sentry)

- Backend: `sentry_sdk.init(dsn, traces_sample_rate=1.0 for the contest, send_default_pii=False, environment=ENV, release=GIT_SHA)`. Add before-send scrubber for coordinates/device IDs.
- One transaction per `/generate`. Child spans: `context.build`, `scout.search`, `memory.check`, `llm.call` (op `gen_ai.chat` or current convention **[VERIFY]**, attributes: model name, input/output tokens, latency), `validators`, `fallback`.
- Tag spans with `source=llm|fallback`, `retry=0|1`, `validator_failures=[ids]`.
- Frontend: `@sentry/react` with `tracesSampleRate` low; ignore camera-permission noise.
- Deliverable: screenshot of one full trace + one story ("traces showed V10 failing at dusk → fixed Scout filter").

---

## 14. Testing and acceptance

### 14.1 Automated (MUST pass in CI/local before each milestone)
- Unit: every validator (positive + negative cases), XP calculator, rarity rules, geohash neighbours, haversine, prompt-hash equality, input sanitizer.
- API: contract tests with a mocked LLM (valid, invalid JSON, timeout) and mocked Mongo (or a local Atlas container).
- Fallback: with LLM unreachable, `/generate` still returns a valid quest in < 3 s.
- Safety red-team set: ≥ 40 adversarial contexts/interests (e.g., "cliff jumping", "night alone", prompt-injection strings) → 0 unsafe quests pass validators.
- Frontend: component tests for Quest Card and Walk Mode; one Playwright smoke test (generate → accept → complete with mocked verifier).

### 14.2 Manual acceptance (demo day checklist)
- [ ] Fresh phone, install PWA, onboarding < 60 s.
- [ ] Generate a quest at a real location in < 20 s (p50).
- [ ] Voice briefing plays; screen can be locked/pocketed after Accept; returning shows elapsed time.
- [ ] Photo verification works on-device; airplane-mode test proves the photo isn't uploaded (verification result still submits when back online).
- [ ] Kill `sqm-llm` → quest still generates (fallback).
- [ ] 3 real quests completed outdoors, with real screen-share numbers.
- [ ] Sentry shows traces. Atlas shows data. Render shows 3 healthy services.

---

## 15. Verify-before-build list (I could not confirm these)

1. Tinker: access/credits, exact supported small models, SDK API, weight download/export steps.
2. Whether Gemma-3n `.litertlm` web models are publicly downloadable or gated on Hugging Face (license acceptance); how we host/serve the ~GB file (**decision OQ-1**: user supplies via `VITE_GEMMA_MODEL_URL` from a repo that carries Gemma terms, or serve with HTTP Range from the `sqm-llm` disk).
3. MediaPipe LLM Inference (maintenance-only) still supports Gemma-3n on current Chrome/Android; WebGPU availability on target phones.
4. llama.cpp server: image name/tag, binary path, schema/grammar parameter, chat template for the chosen model.
5. Render: Blueprint field names (`dockerContext`, `dockerfilePath`, `property: hostport`, `headers`, `routes`), instance RAM/pricing, private service + disk availability, sponsor credits.
6. ElevenLabs: endpoint, model id, `output_format`, free-tier limits/terms for hackathon use, voice licensing.
7. Atlas: Vector Search on free tier, `$in` filters in `$vectorSearch`, index creation via driver/CLI.
8. Sentry: `gen_ai` span operation names and dashboard for AI agent monitoring.
9. Challenge rules: deadline, submission format (DEV post tags/template), multi-category eligibility, whether a live demo URL is required.
10. Overpass/Open-Meteo/OSM tile usage policies for the expected traffic.
11. Teacher-model terms for generating training data.

Resolve each item by reading primary docs; record the answer under "Decisions log" in PROJECTPLAN.md.

---

## 16. Glossary
- **Sidequest maxxing**: deliberately collecting many small, unusual real-life experiences outside your routine.
- **DM**: the Dungeon Master (our quest-writing model).
- **Cell5**: geohash precision-5 cell (~5 km × 5 km).
- **Walk Mode**: minimal-screen state while a quest is active.
- **Screen share**: visible-screen seconds ÷ quest seconds.
