"""ElevenLabs text-to-speech proxy (MASTERSPEC §6.1, §6.5, §2.4).

The server picks the text (a quest's own briefing/hint) — clients never send text. Text is
never logged. The API key stays server-side. Endpoint shape verified against the official
elevenlabs-python SDK (see docs/DECISIONS.md D-54).
"""

import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import httpx
from pymongo.asynchronous.database import AsyncDatabase

from app.models.enums import Persona
from app.services.db import Doc

log = logging.getLogger("sqm.tts")

ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"
MAX_TTS_CHARS = 600
# A 180-260 word chronicle is ~1.1-1.7k chars; still bounded by the daily char budget (D-61).
MAX_RECAP_TTS_CHARS = 1800
TtsKind = Literal["briefing", "hint", "recap"]
QuestTtsKind = Literal["briefing", "hint"]


# ---------------------------------------------------------------- one voice per Dungeon Master


@dataclass(frozen=True)
class VoiceStyle:
    """Per-persona delivery, sent as `voice_settings` on each request.

    Field names, defaults and meanings per the official TTS reference (D-99): lower
    `stability` widens the emotional range, `style` exaggerates the voice's own character,
    `speed` < 1 slows the read. These make the four Dungeon Masters sound like four
    different people even when they share one voice id.
    """

    stability: float
    style: float
    speed: float
    similarity_boost: float = 0.75

    def as_settings(self) -> dict[str, float | bool]:
        return {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "speed": self.speed,
            "use_speaker_boost": True,
        }


PERSONA_STYLE: dict[Persona, VoiceStyle] = {
    # Calm and friendly: steady, barely styled, a touch under natural pace.
    "chill": VoiceStyle(stability=0.55, style=0.15, speed=0.97),
    # Over-the-top narrator: unstable on purpose, heavy style, slow and weighty.
    "dramatic": VoiceStyle(stability=0.22, style=0.75, speed=0.9),
    # Delighted by birds and rocks: bright, quick, expressive.
    "nature_nerd": VoiceStyle(stability=0.38, style=0.5, speed=1.07),
    # Dry humour: flat-ish and brisk, with just enough colour to land the joke.
    "sarcastic": VoiceStyle(stability=0.6, style=0.4, speed=1.02),
}


def as_persona(value: str | None) -> Persona:
    """A known persona, or the chill one for anything unrecognised."""
    return value if value in PERSONA_STYLE else "chill"


def voice_style(persona: str | None) -> VoiceStyle:
    """The delivery for this persona; the chill one for anything unknown."""
    return PERSONA_STYLE[as_persona(persona)]


class TtsUnavailableError(Exception):
    """ElevenLabs can't serve this request (not configured, auth, rate limit, timeout, 5xx).

    `reason` is a short machine code for logs/metrics; never contains quest text.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def tts_text(quest: Doc, kind: QuestTtsKind) -> str:
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
        persona_voice_ids: Mapping[Persona, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self.voice_id = voice_id
        self.persona_voice_ids = dict(persona_voice_ids or {})
        self.model_id = model_id
        self.output_format = output_format
        self._http = http or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(timeout_s, connect=3.0)
        )

    def voice_for(self, persona: str | None) -> str:
        """This persona's own voice id, or the shared default when none is configured."""
        return self.persona_voice_ids.get(as_persona(persona)) or self.voice_id

    async def stream(self, text: str, persona: str | None = None) -> AudioStream:
        """POST /v1/text-to-speech/{voice_id}/stream → audio/mpeg chunks.

        The persona picks both the voice id and the `voice_settings` delivery.
        Raises TtsUnavailableError for any failure before the first audio byte.
        """
        request = self._http.build_request(
            "POST",
            f"/v1/text-to-speech/{self.voice_for(persona)}/stream",
            params={"output_format": self.output_format},
            headers={"xi-api-key": self._api_key, "Accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": self.model_id,
                "voice_settings": voice_style(persona).as_settings(),
            },
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
    api_key: str | None,
    voice_id: str | None,
    model_id: str,
    output_format: str,
    timeout_s: float,
    persona_voice_ids: Mapping[Persona, str] | None = None,
) -> ElevenLabsClient | None:
    """None when no voice is configured at all — the client then uses the browser voice."""
    personas = dict(persona_voice_ids or {})
    if not api_key or not (voice_id or personas):
        return None
    return ElevenLabsClient(
        api_key,
        voice_id or next(iter(personas.values())),
        model_id=model_id,
        output_format=output_format,
        timeout_s=timeout_s,
        persona_voice_ids=personas,
    )
