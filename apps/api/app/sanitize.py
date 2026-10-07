"""Input sanitizers. Free text never goes straight into a prompt (MASTERSPEC §6.3, §9.3).

Interests are reduced to short keyword phrases: NFKC-normalised, lower-cased, only letters,
digits, spaces and '-', ≤ 24 chars. Items that look like instructions to a model are dropped.
"""

import re
import unicodedata

MAX_INTERESTS = 6
MAX_INTEREST_LEN = 24

# Phrases that indicate an attempt to talk to the model rather than describe a hobby.
_INJECTION_MARKERS = re.compile(
    r"\b(ignore|disregard|forget|override|bypass|jailbreak|pretend|instruction|instructions|"
    r"prompt|system|assistant|developer|roleplay|act as|you are|output|json|schema|token|"
    r"previous|above|admin|sudo)\b"
)
_ALLOWED = re.compile(r"[^\w\s-]", flags=re.UNICODE)
_WS = re.compile(r"\s+")


def _strip_invisible(text: str) -> str:
    """Whitespace → space; drop other control/format chars (zero-width, bidi overrides)."""
    return "".join(
        " " if ch.isspace() else ch
        for ch in text
        if ch.isspace() or unicodedata.category(ch)[0] != "C"
    )


def clean_phrase(raw: str, max_len: int) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = _strip_invisible(text).lower()
    text = _ALLOWED.sub(" ", text).replace("_", " ")
    text = _WS.sub(" ", text).strip(" -")
    return text[:max_len].strip(" -")


def sanitize_interest(raw: str) -> str | None:
    """Return a safe keyword phrase, or None if nothing usable (or it looks like an injection)."""
    text = clean_phrase(raw, max_len=64)
    if not text or _INJECTION_MARKERS.search(text):
        return None
    text = text[:MAX_INTEREST_LEN].strip(" -")
    return text or None


def sanitize_interests(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        clean = sanitize_interest(item)
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
        if len(out) == MAX_INTERESTS:
            break
    return out


def sanitize_note(raw: str, max_len: int = 200) -> str:
    """Notes are stored, never prompted. Still strip invisible chars and clamp length."""
    text = _strip_invisible(unicodedata.normalize("NFKC", raw))
    return _WS.sub(" ", text).strip()[:max_len]


def round_coord(value: float) -> float:
    """~110 m precision (MASTERSPEC §9.3)."""
    return round(value, 3)
