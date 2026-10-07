"""ElevenLabs text-to-speech proxy (MASTERSPEC §6.1, §6.5, §2.4).

The server picks the text (a quest's own briefing/hint) — clients never send text. Text is
never logged. The API key stays server-side. Endpoint shape verified against the official
elevenlabs-python SDK (see docs/DECISIONS.md D-54).
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import httpx
from pymongo.asynchronous.database import AsyncDatabase

from app.services.db import Doc

log = logging.getLogger("sqm.tts")

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
MAX_TTS_CHARS = 600
TtsKind = Literal["briefing", "hint"]


class TtsUnavailableError(Exception):
    """ElevenLabs can't serve this request (not configured, auth, rate limit, timeout, 5xx).

    `reason` is a short machine code for logs/metrics; never contains quest text.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def tts_text(quest: Doc, kind: TtsKind) -> str:
    """The words to speak, taken only from the stored quest."""
    if kind == "briefing":
        return str(quest["briefing"])
    # "hint": a short spoken reminder for Walk Mode — objective + the off-screen tip.
    return f"{quest['objective']} {quest['off_screen_tip']}".strip()


# ---------------------------------------------------------------- daily character budget


def usage_id(now: datetime, utc_offset_min: int = 0) -> str:
    return f"tts:{(now + timedelta(minutes=utc_offset_min)).date().isoformat()}"


async def reserve_chars(db: AsyncDatabase[Doc], now: datetime, chars: int, budget: int) -> bool:
    """Atomically take `chars` from today's global budget. False when it would be exceeded."""
    if chars > budget:
        return False
    key = usage_id(now)
    usage = db["usage"]
    await usage.update_one({"_id": key}, {"$setOnInsert": {"chars": 0}}, upsert=True)
    taken = await usage.find_one_and_update(
        {"_id": key, "chars": {"$lte": budget - chars}}, {"$inc": {"chars": chars}}
    )
    return taken is not None


async def refund_chars(db: AsyncDatabase[Doc], now: datetime, chars: int) -> None:
    """Give characters back when ElevenLabs didn't produce audio (best-effort)."""
    await db["usage"].update_one({"_id": usage_id(now)}, {"$inc": {"chars": -chars}})


# ---------------------------------------------------------------- ElevenLabs client


@dataclass
class AudioStream:
    """First chunk already received (so errors surface before we answer 200) + the rest."""

    first: bytes
    rest: AsyncIterator[bytes]
    close: "CloseFn"


class CloseFn:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def __call__(self) -> None:
        await self._response.aclose()


class ElevenLabsClient:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        *,
        model_id: str = "eleven_flash_v2_5",
        output_format: str = "mp3_44100_64",
        timeout_s: float = 10.0,
        http: httpx.AsyncClient | None = None,
        base_url: str = ELEVENLABS_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format
        self._http = http or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(timeout_s, connect=3.0)
        )

    async def stream(self, text: str) -> AudioStream:
        """POST /v1/text-to-speech/{voice_id}/stream → audio/mpeg chunks.

        Raises TtsUnavailableError for any failure before the first audio byte.
        """
        request = self._http.build_request(
            "POST",
            f"/v1/text-to-speech/{self.voice_id}/stream",
            params={"output_format": self.output_format},
            headers={"xi-api-key": self._api_key, "Accept": "audio/mpeg"},
            json={"text": text, "model_id": self.model_id},
        )
        try:
            response = await self._http.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise TtsUnavailableError("timeout") from exc
        except httpx.HTTPError as exc:
            raise TtsUnavailableError("transport") from exc

        if response.status_code != 200:
            await response.aclose()
            reason = {401: "auth", 403: "auth", 429: "rate_limited"}.get(
                response.status_code, f"http_{response.status_code}"
            )
            raise TtsUnavailableError(reason)

        chunks = response.aiter_bytes()
        try:
            first = b""
            while not first:
                first = await anext(chunks)
        except StopAsyncIteration as exc:
            await response.aclose()
            raise TtsUnavailableError("empty") from exc
        except httpx.HTTPError as exc:
            await response.aclose()
            raise TtsUnavailableError("transport") from exc
        return AudioStream(first=first, rest=chunks, close=CloseFn(response))


def build_tts_client(
    api_key: str | None, voice_id: str | None, model_id: str, output_format: str, timeout_s: float
) -> ElevenLabsClient | None:
    if not api_key or not voice_id:
        return None
    return ElevenLabsClient(
        api_key, voice_id, model_id=model_id, output_format=output_format, timeout_s=timeout_s
    )
