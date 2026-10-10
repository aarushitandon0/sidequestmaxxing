# DEPLOY.md — Deploying Sidequestmaxxing to Render

> Nothing here is automated. Claude never deploys or spends money; you do these steps in the Render dashboard.
> **Cost note: the blueprint as committed costs nothing** (D-97). `sqm-web` is a static site, which
> Render documents as free; `sqm-api` runs on `plan: free`; `sqm-llm` is commented out, because
> Render's free plan covers neither private services nor persistent disks. Mongo Atlas stays on M0.
> Read §0b before you rely on that, then check https://render.com/pricing and any sponsor credit
> (PROJECTPLAN gate G0) before changing a single `plan:` value.

## 0b. What "free" costs you instead

Free is real, but it is not free of consequences. Three, in the order they will bite:

1. **Cold starts.** A free web service spins down after 15 minutes without traffic and takes
   about a minute to wake. A judge or playtester opening the app cold gets a minute of nothing
   and reads it as broken. This is the single biggest risk to a demo.
2. **750 instance-hours per workspace per calendar month.** An always-on month needs ~720, so
   keeping `sqm-api` warm with a ping consumes essentially the whole allowance and leaves no
   room for a second service. Run out and free services are suspended until the next month.
3. **No LLM.** With `sqm-llm` undeployed there is no `LLM_HOSTPORT`, so `Settings.llm_url` is
   `None` and every quest comes from the fallback engine. That is a supported state, not a
   broken one (MASTERSPEC §2.4, CLAUDE.md invariant 5) — `/healthz` reports the LLM as
   `unknown` and `X-Quest-Source` reads `fallback`. Say so honestly in the README and the post:
   the tuned model is in the repo and the eval harness, not in the live demo.

Free instances are 512 MB RAM / 0.1 CPU. The API fits — it loads no model in-process and needs
no disk. If you later want the LLM or always-on behaviour, `plan: starter` is about $7/mo per
service; state the cost and decide deliberately.

## 0. Before the first deploy
1. Push this repo to GitHub (public).
2. Have these ready in a password manager (never paste them into a chat/agent session):
   `MONGODB_URI`, `SENTRY_DSN` (backend), `VITE_SENTRY_DSN` (frontend, optional), `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`. (`MODEL_URL` is only needed if you uncomment `sqm-llm` — a public GGUF URL; any small instruct GGUF works until the tuned model exists.)
   Also confirm Atlas has a **free FTS index slot** before you start: an M0 cluster allows 3 across all databases, and without `events_vec` the live-events section renders empty with no error anywhere (D-82).
3. Optional but recommended: validate the Blueprint locally with the Render CLI (≥ 2.7.0):
   ```bash
   render blueprints validate
   ```

## 1. Create the Blueprint
1. Render dashboard → **New** → **Blueprint** → connect the GitHub repo → branch `main`.
2. Render reads `render.yaml` and proposes **2** services: `sqm-web` (static) and `sqm-api`
   (Docker web service, `plan: free`). `sqm-llm` is commented out — see §0b.
3. It will prompt for every `sync: false` variable. Fill:
   - `sqm-api`: `MONGODB_URI`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `SENTRY_DSN` (empty is OK for now).
   - `sqm-web`: `VITE_SENTRY_DSN`, `VITE_GEMMA_MODEL_URL` (both may be empty).
4. Click **Apply**. Nothing downloads a model, so the first boot is just the Docker build.
   If you uncommented `sqm-llm`, it is a third service and its first boot pulls the GGUF to the
   disk (can take minutes) — and it cannot be on the free plan.

## 2. Fix the URL-suffix gotcha (MASTERSPEC §12.2 #1)
If Render appended a suffix to service names, the hard-coded URLs in `render.yaml` are wrong.
1. Copy the real public URLs from the dashboard (e.g. `https://sqm-api-abcd.onrender.com`).
2. Set `sqm-web` → `VITE_API_BASE_URL` = real API URL; set `sqm-api` → `WEB_ORIGIN` = real web URL.
3. Update the same values in `render.yaml` and commit, so the Blueprint stays the source of truth.
4. Redeploy both (`sqm-web` needs a rebuild because Vite inlines env at build time).

## 3. Smoke test
```bash
API_BASE_URL=https://<your-sqm-api>.onrender.com bash scripts/smoke_test.sh
```
Expected: `{"status":"ok", ...}` and "smoke test passed". Then open the `sqm-web` URL: the Home page shows "Dungeon status" pills.

## 3b. Generate a quest by hand (after P7)
```bash
DEV=$(python3 -c 'import uuid; print(uuid.uuid4())')
curl -sS -X POST "$API_BASE_URL/v1/quests/generate" \
  -H 'Content-Type: application/json' -H "X-Device-Id: $DEV" \
  -d '{"lat":18.520,"lng":73.856,"minutes_available":45,"radius_m":2500,"mood":"curious",
       "interests":["birds","history"],"persona":"chill","mode":"walk",
       "local_time_iso":"2026-10-07T17:30:00+05:30"}'
# then, with the returned id:
curl -sS -X POST "$API_BASE_URL/v1/quests/<id>/accept" -H "X-Device-Id: $DEV"
curl -sS -X POST "$API_BASE_URL/v1/quests/<id>/skip"   -H "X-Device-Id: $DEV"
```
On the free path there is no `sqm-llm`, so this **is** the fallback path: expect a valid quest with
`X-Quest-Source: fallback` and a stored doc with `source: "fallback"`. If you have deployed the LLM,
prove the fallback by suspending `sqm-llm` in the dashboard and running generate again — it still
returns a valid quest.

## 4. Atlas setup (after P3)
```bash
# from the repo root, using the API virtualenv; MONGODB_URI in ./.env
source apps/api/.venv/bin/activate
python scripts/create_indexes.py
python scripts/seed_places.py --bbox "<S,W,N,E>" --city "<name>" --dry-run   # check counts first
python scripts/seed_places.py --city "<name>" --from-cache                   # embed + upsert, no 2nd Overpass call
```
Then check: `curl -H "X-Device-Id: $(python -c 'import uuid;print(uuid.uuid4())')" "$API_BASE_URL/v1/places/near?lat=<lat>&lng=<lng>&q=birds"`.
Vector indexes build asynchronously in Atlas — wait until they show "READY" before testing.
(Run locally with `MONGODB_URI` in your `.env`. In Atlas → Network Access, allow your IP and Render's outbound IPs, or 0.0.0.0/0 for the contest with a strong password.)

## 4b. Gate G1 — pick, deploy and benchmark the base model (P6)
Read the model options + memory math in `docs/DECISIONS.md` ("Gate G1"). You choose; nothing here spends money until you click.
1. **Pick a base GGUF to test.** On Hugging Face, open the official (or a well-known quantizer's) GGUF repo for your choice, pick the `Q4_K_M` file, note its exact size and copy its `resolve/main/...gguf` URL. Optional: copy its SHA-256 from the file page.
2. **Try it locally first (free):**
   ```bash
   docker run --rm -p 8080:8080 -v "$PWD/models:/models" ghcr.io/ggml-org/llama.cpp:server \
     -m /models/<file>.gguf --host 0.0.0.0 --port 8080 -c 2048 -np 1
   python scripts/bench_llm.py --base-url http://localhost:8080 --n 10 --label "laptop <model>"
   ```
   (or with Ollama: `LLM_BASE_URL=http://localhost:11434 LLM_MODEL=<tag> python scripts/bench_llm.py --n 10`)
3. **Deploy `sqm-llm` on Render.** This leaves the free path: uncomment the `sqm-llm` block at the
   bottom of `render.yaml` and restore the `LLM_HOSTPORT` `fromService` entry on `sqm-api`. A
   private service with a disk **cannot** be on the free plan, so pick the plan the memory table
   says fits (**ask/confirm cost first**; edit `plan:` in `render.yaml` in the same commit), set
   `MODEL_URL` (and `MODEL_SHA256` if known), and wait for the first boot to finish downloading;
   logs end with the server listening.
4. **Benchmark on Render.** `sqm-llm` is private, so run the bench from `sqm-api` (the image ships the script). Dashboard → `sqm-api` → **Shell**:
   ```bash
   cd /srv && PYTHONPATH=/srv python scripts/bench_llm.py --n 20 --label "render-<plan> <model>"
   ```
   It uses `LLM_HOSTPORT` automatically and writes `/srv/evals/bench_llm_<ts>.json` (ephemeral) — copy the printed JSON summary + the file into the repo's `evals/` and commit it.
5. **Record** the printed p50/p95 and tokens/s in `docs/DECISIONS.md` ("Gate G1") with the JSON file name. Gate passes if p50 ≤ 15 s (MASTERSPEC §10.2) and memory leaves ≥ 1 GB headroom (Render **Metrics** tab).

## 4c. Web app notes (after P8–P12)
- The static build includes the MediaPipe WASM under `/mediapipe-wasm/` (~54 MB for both variants; a player downloads only one, and only after installing the verifier).
- `VITE_GEMMA_MODEL_URL` (optional) must be an **ungated** URL you're allowed to serve (D-48). Leave it empty and players can import the model file in Settings → Photo checks.
- Leaflet loads OSM tiles from `tile.openstreetmap.org` (attribution shown). Heavy traffic needs a tile provider per the OSM tile policy.

## 4d. Manual check: airplane mode (photo never uploaded)
1. On a WebGPU-capable phone/laptop: Settings → Photo checks → install the checker (Wi-Fi). Wait for "installed".
2. Get a quest with a photo proof → Accept → I'm back.
3. Turn on **airplane mode**. Take the photo → "Checking on your device…" → "Match found!" (proves no network was needed).
4. Tap **Claim reward** → screen says "Verified — saved on your phone… claimed as soon as you're back online".
5. Optional proof for the post: desktop Chrome DevTools → Network (filter `Fetch/XHR`, "Preserve log"), repeat 3–4 online: the only request is `POST /v1/quests/{id}/complete` with a JSON body of `verification`, `elapsed_seconds`, `screen_seconds` — no image. Screenshot it for the claims ledger.
6. Turn airplane mode off → within seconds the reward screen appears (queued claim replayed).

## 4e. Voice (P13)
- Set `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` on `sqm-api` (Render dashboard → Environment; never in the repo). Without them `/v1/tts` answers 503 and the app uses the browser voice — nothing breaks.
- `TTS_DAILY_CHAR_BUDGET` caps characters per UTC day across all players (stored in `usage`, `_id: "tts:YYYY-MM-DD"`); per device 20 requests/hour. At ~0.5 credit/char (Flash), 20 000 chars ≈ 10 000 credits/day — check your plan's monthly credits and lower it if needed.
- Demo clips (optional, spends credits once): edit `scripts/demo_quests.json` (copy briefings verbatim — clips match by exact text), then `python scripts/pregen_demo_audio.py --dry-run`, then `--yes`. Commit `apps/web/public/demo-audio/*.mp3` + `manifest.json` only if the voice's licence allows redistribution.
- Manual check: accept a quest with voice on → audio plays; repeat it in Walk Mode with airplane mode on → plays from the device cache; with the key removed → browser voice reads the same text.

## 5. After judging
Suspend or delete `sqm-llm` and `sqm-api` (and the disk) to stop charges.

## Known limits of the build container (2026-10-07)
- `docker build -f apps/api/Dockerfile .` was verified up to the embedding-preload step (the build container can't reach Hugging Face); the image starts and `/healthz` returns ok as a non-root user. The full build must run on Render or your machine.
- `services/llm` image could not be pulled here (ghcr blob storage blocked); verify with `docker build services/llm` locally.
