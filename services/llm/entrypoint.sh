#!/bin/sh
# Downloads the GGUF once onto the persistent disk, then starts llama-server.
set -eu

MODEL_DIR="${MODEL_DIR:-/data/models}"
MODEL_PATH="${MODEL_DIR}/${MODEL_FILE:-quest.gguf}"
mkdir -p "$MODEL_DIR"

if [ ! -s "$MODEL_PATH" ]; then
  if [ -z "${MODEL_URL:-}" ]; then
    echo "MODEL_URL is not set and no model on disk at $MODEL_PATH" >&2
    exit 1
  fi
  echo "Downloading model to $MODEL_PATH ..."
  curl -fL --retry 5 --retry-delay 5 -o "${MODEL_PATH}.part" "$MODEL_URL"
  mv "${MODEL_PATH}.part" "$MODEL_PATH"
fi

if [ -n "${MODEL_SHA256:-}" ]; then
  echo "${MODEL_SHA256}  ${MODEL_PATH}" | sha256sum -c - || {
    echo "Model checksum mismatch; deleting so the next boot re-downloads." >&2
    rm -f "$MODEL_PATH"
    exit 1
  }
fi

exec /app/llama-server -m "$MODEL_PATH" --host 0.0.0.0 --port "${PORT:-10000}" \
  -c "${CTX_SIZE:-2048}" -np "${PARALLEL:-1}" --threads "${THREADS:-$(nproc)}"
