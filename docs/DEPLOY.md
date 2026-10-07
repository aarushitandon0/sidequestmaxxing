# DEPLOY.md — Deploying Sidequestmaxxing to Render

> Nothing here is automated. Claude never deploys or spends money; you do these steps in the Render dashboard.
> Cost note: `sqm-api` (starter) and `sqm-llm` (standard + 10 GB disk) are **paid** instances. Check https://render.com/pricing and any sponsor credit first (PROJECTPLAN gate G0). `sqm-web` (static) is free.

## 0. Before the first deploy
1. Push this repo to GitHub (public).
2. Have these ready in a password manager (never paste them into a chat/agent session):
   `MONGODB_URI`, `SENTRY_DSN` (backend), `VITE_SENTRY_DSN` (frontend, optional), `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `MODEL_URL` (a public GGUF URL; any small instruct GGUF works until the tuned model exists).
3. Optional but recommended: validate the Blueprint locally with the Render CLI (≥ 2.7.0):
   ```bash
   render blueprints validate
   ```

## 1. Create the Blueprint
1. Render dashboard → **New** → **Blueprint** → connect the GitHub repo → branch `main`.
2. Render reads `render.yaml` and proposes 3 services: `sqm-web` (static), `sqm-api` (Docker web service), `sqm-llm` (private service + disk `models` at `/data`).
3. It will prompt for every `sync: false` variable. Fill:
   - `sqm-api`: `MONGODB_URI`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `SENTRY_DSN` (empty is OK for now).
   - `sqm-llm`: `MODEL_URL` (required), `MODEL_SHA256` (empty until the final model).
   - `sqm-web`: `VITE_SENTRY_DSN`, `VITE_GEMMA_MODEL_URL` (both may be empty).
4. Click **Apply**. First `sqm-llm` boot downloads the model to the disk (can take minutes).

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
To prove the fallback: suspend `sqm-llm` in the dashboard and run generate again — it still returns a valid quest (the stored doc has `source: "fallback"`).

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
3. **Deploy `sqm-llm` on Render.** In the Blueprint, set `sqm-llm` → `MODEL_URL` (and `MODEL_SHA256` if known). Set the plan to what the memory table says fits (**ask/confirm cost first**; edit `plan:` in `render.yaml` in the same commit). Wait for the first boot to finish downloading; logs end with the server listening.
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

## 5. After judging
Suspend or delete `sqm-llm` and `sqm-api` (and the disk) to stop charges.

## Known limits of the build container (2026-10-07)
- `docker build -f apps/api/Dockerfile .` was verified up to the embedding-preload step (the build container can't reach Hugging Face); the image starts and `/healthz` returns ok as a non-root user. The full build must run on Render or your machine.
- `services/llm` image could not be pulled here (ghcr blob storage blocked); verify with `docker build services/llm` locally.
