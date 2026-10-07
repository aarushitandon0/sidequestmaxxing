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

## 4. Atlas setup (after P3)
```bash
cd apps/api && source .venv/bin/activate
python ../../scripts/create_indexes.py
python ../../scripts/seed_places.py --bbox "<S,W,N,E>" --city "<name>"
```
(Run locally with `MONGODB_URI` in your `.env`. In Atlas → Network Access, allow your IP and Render's outbound IPs, or 0.0.0.0/0 for the contest with a strong password.)

## 5. After judging
Suspend or delete `sqm-llm` and `sqm-api` (and the disk) to stop charges.

## Known limits of the build container (2026-10-07)
- `docker build -f apps/api/Dockerfile .` was verified up to the embedding-preload step (the build container can't reach Hugging Face); the image starts and `/healthz` returns ok as a non-root user. The full build must run on Render or your machine.
- `services/llm` image could not be pulled here (ghcr blob storage blocked); verify with `docker build services/llm` locally.
