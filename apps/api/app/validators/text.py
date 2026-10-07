"""Text normalisation used by every lint so look-alike tricks can't slip past."""

import re
import unicodedata

# Common Cyrillic/Greek look-alikes → Latin. Enough to stop "сliff" (Cyrillic с) style evasion.
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
        "ј": "j", "ѕ": "s", "ԁ": "d", "ɡ": "g", "һ": "h", "ӏ": "l", "ո": "n", "ν": "v",
        "α": "a", "ο": "o", "ρ": "p", "τ": "t", "ι": "i", "κ": "k", "μ": "m", "ε": "e",
        "А": "a", "В": "b", "Е": "e", "К": "k", "М": "m", "Н": "h", "О": "o", "Р": "p",
        "С": "c", "Т": "t", "Х": "x", "Ү": "y",
    }
)  # fmt: skip
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(
        " " if ch.isspace() else ch
        for ch in text
        if ch.isspace() or unicodedata.category(ch)[0] != "C"
    )
    text = text.translate(_CONFUSABLES).lower()
    # Drop combining marks so "clímb" == "climb".
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))
    return _WS.sub(" ", text).strip()
