#!/usr/bin/env bash
# Smoke test against a running API. Usage: API_BASE_URL=https://sqm-api.onrender.com bash scripts/smoke_test.sh
set -euo pipefail
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

echo "GET ${API_BASE_URL}/healthz"
body="$(curl -fsS --max-time 20 "${API_BASE_URL}/healthz")"
echo "$body"
echo "$body" | grep -q '"status":"ok"' || { echo "healthz not ok" >&2; exit 1; }
echo "smoke test passed"
