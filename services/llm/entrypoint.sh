#!/bin/sh
# Downloads the GGUF once onto the persistent disk, then starts llama-server.
set -eu

MODEL_DIR="${MODEL_DIR:-/data/models}"
MODEL_PATH="${MODEL_DIR}/${MODEL_FILE:-quest.gguf}"
mkdir -p "$MODEL_DIR"

verify() {  # $1 = file; no-op when MODEL_SHA256 is empty (any GGUF before the tuned one)
  [ -z "${MODEL_SHA256:-}" ] && return 0
  echo "${MODEL_SHA256}  $1" | sha256sum -c -
}

if [ ! -s "$MODEL_PATH" ]; then
  if [ -z "${MODEL_URL:-}" ]; then
    echo "MODEL_URL is not set and no model on disk at $MODEL_PATH" >&2
    exit 1
  fi
  echo "Downloading model to $MODEL_PATH ..."
  curl -fL --retry 5 --retry-delay 5 -o "${MODEL_PATH}.part" "$MODEL_URL"
  # Check before moving into place, so a bad download never becomes the served model.
  verify "${MODEL_PATH}.part" || {
    echo "Downloaded model does not match MODEL_SHA256; deleting it." >&2
    rm -f "${MODEL_PATH}.part"
    exit 1
  }
  mv "${MODEL_PATH}.part" "$MODEL_PATH"
fi

# Every boot: also catches a new MODEL_SHA256 (new model) while the old file is still on disk.
verify "$MODEL_PATH" || {
  echo "Model checksum mismatch; deleting so the next boot re-downloads from MODEL_URL." >&2
  rm -f "$MODEL_PATH"
  exit 1
}

exec /app/llama-server -m "$MODEL_PATH" --host 0.0.0.0 --port "${PORT:-10000}" \
  -c "${CTX_SIZE:-2048}" -np "${PARALLEL:-1}" --threads "${THREADS:-$(nproc)}"
