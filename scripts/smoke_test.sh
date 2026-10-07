#!/usr/bin/env bash
# Smoke test against a running API: healthz, then a real quest generate + accept + skip.
# Usage: API_BASE_URL=https://sqm-api.onrender.com bash scripts/smoke_test.sh
# Optional: SMOKE_LAT / SMOKE_LNG (default: Pune centre, the spec's example city).
set -euo pipefail
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
LAT="${SMOKE_LAT:-18.520}"
LNG="${SMOKE_LNG:-73.856}"

echo "GET ${API_BASE_URL}/healthz"
body="$(curl -fsS --max-time 20 "${API_BASE_URL}/healthz")"
echo "$body"
echo "$body" | grep -q '"status":"ok"' || { echo "healthz not ok" >&2; exit 1; }

# A random v4 device id and the local time with UTC offset (portable: python3 instead of date).
DEVICE_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
LOCAL_TIME="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"

echo "POST ${API_BASE_URL}/v1/quests/generate"
quest="$(curl -fsS --max-time 60 -X POST "${API_BASE_URL}/v1/quests/generate" \
  -H 'Content-Type: application/json' -H "X-Device-Id: ${DEVICE_ID}" \
  -d "{\"lat\":${LAT},\"lng\":${LNG},\"minutes_available\":45,\"radius_m\":2500,\"mood\":\"curious\",\"interests\":[\"birds\",\"history\"],\"persona\":\"chill\",\"mode\":\"walk\",\"local_time_iso\":\"${LOCAL_TIME}\"}")"
echo "$quest"
QUEST_ID="$(printf '%s' "$quest" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
printf '%s' "$quest" | python3 -c 'import json,sys; q=json.load(sys.stdin); assert q["safety_note"] and q["rarity"] and q["xp"] >= 0, q'

echo "POST /v1/quests/${QUEST_ID}/accept"
curl -fsS --max-time 20 -X POST "${API_BASE_URL}/v1/quests/${QUEST_ID}/accept" -H "X-Device-Id: ${DEVICE_ID}"; echo
echo "POST /v1/quests/${QUEST_ID}/skip"
curl -fsS --max-time 20 -X POST "${API_BASE_URL}/v1/quests/${QUEST_ID}/skip" -H "X-Device-Id: ${DEVICE_ID}"; echo
echo "smoke test passed"
