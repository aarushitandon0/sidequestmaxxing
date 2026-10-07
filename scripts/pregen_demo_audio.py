"""Pre-generate ElevenLabs audio for a few fixed demo lines (P13).

Writes apps/web/public/demo-audio/<slug>.mp3 and manifest.json ({"clips": {sha256(text): file}}).
The web app plays a clip when the text it is about to speak matches a hash exactly, so the
demo never depends on the live TTS budget or network.

THIS SPENDS ELEVENLABS CREDITS (eleven_flash_v2_5: ~0.5 credit per character). Run it yourself:
  python scripts/pregen_demo_audio.py --dry-run     # shows texts, char count; no network
  python scripts/pregen_demo_audio.py --yes      # needs ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

Every text must pass the production banned-term lint (V4) first. Text and key are never printed
beyond the slug and character counts.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401  (puts apps/api on sys.path)
from app.config import get_settings
from app.services.tts import MAX_TTS_CHARS, ElevenLabsClient, TtsUnavailableError
from app.validators.lint import banned_hits

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO / "scripts" / "demo_quests.json"
OUT_DIR = REPO / "apps" / "web" / "public" / "demo-audio"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_clips(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    clips: list[dict[str, str]] = data["clips"]
    for c in clips:
        if not c["slug"].replace("-", "").isalnum():
            raise SystemExit(f"bad slug {c['slug']!r}: letters, digits and '-' only")
        if len(c["text"]) > MAX_TTS_CHARS:
            raise SystemExit(f"{c['slug']}: {len(c['text'])} chars > {MAX_TTS_CHARS}")
        hits = banned_hits(c["text"])
        if hits:
            raise SystemExit(f"{c['slug']}: fails the V4 lint ({', '.join(h.rule for h in hits)})")
    return clips


async def synthesize(client: ElevenLabsClient, text: str) -> bytes:
    stream = await client.stream(text)
    parts = [stream.first]
    try:
        async for chunk in stream.rest:
            parts.append(chunk)
    finally:
        await stream.close()
    return b"".join(parts)


async def main() -> int:
    fmt = argparse.RawDescriptionHelpFormatter
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=fmt)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--dry-run", action="store_true", help="validate and count characters only")
    ap.add_argument("--yes", action="store_true", help="confirm spending ElevenLabs credits")
    args = ap.parse_args()

    clips = load_clips(args.input)
    total = sum(len(c["text"]) for c in clips)
    for c in clips:
        print(f"  {c['slug']}: {len(c['text'])} chars")
    print(f"{len(clips)} clips, {total} characters (≈{total / 2:.0f} credits on eleven_flash_v2_5)")
    if args.dry_run:
        return 0
    if not args.yes:
        print("Refusing to spend credits without --yes.", file=sys.stderr)
        return 2

    s = get_settings()
    if not s.elevenlabs_api_key or not s.elevenlabs_voice_id:
        print("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID must be set.", file=sys.stderr)
        return 2
    client = ElevenLabsClient(
        s.elevenlabs_api_key,
        s.elevenlabs_voice_id,
        model_id=s.elevenlabs_model_id,
        output_format=s.elevenlabs_output_format,
        timeout_s=30,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"clips": {}}
    for c in clips:
        try:
            audio = await synthesize(client, c["text"])
        except TtsUnavailableError as exc:
            print(f"{c['slug']}: failed ({exc.reason})", file=sys.stderr)
            return 1
        file = f"{c['slug']}.mp3"
        (args.out / file).write_bytes(audio)
        manifest["clips"][text_hash(c["text"])] = file
        print(f"  wrote {file} ({len(audio)} bytes)")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"updated {manifest_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
