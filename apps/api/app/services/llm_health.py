"""Liveness probe for the llama.cpp service (GET /health)."""

import httpx


async def llm_status(base_url: str | None, timeout_s: float = 2.0) -> str:
    if not base_url:
        return "unknown"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            res = await client.get(f"{base_url}/health")
    except httpx.HTTPError:
        return "down"
    return "ok" if res.status_code == 200 else "down"
