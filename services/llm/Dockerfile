# llama.cpp server (verified 2026-10-07: image stage "server" ships /app/llama-server,
# and the base stage already installs curl + libgomp1). See docs/DECISIONS.md.
FROM ghcr.io/ggml-org/llama.cpp:server
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
