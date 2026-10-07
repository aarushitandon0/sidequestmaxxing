"""Embedders for dedupe/diversity. Production uses fastembed BGE-small (same as the API);
`HashEmbedder` is a deterministic bag-of-words stand-in for dry runs/tests only (no model
download). Every report records which one was used.
"""

import hashlib
import math
import re

import common  # noqa: F401

from app.services.embeddings import Embedder, get_embedder

DIM = 384
_WORD = re.compile(r"[a-z0-9']+")


class HashEmbedder:
    name = "hash-bow-384 (dry-run only)"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * DIM
            for w in _WORD.findall(t.lower()):
                h = int.from_bytes(hashlib.blake2b(w.encode(), digest_size=4).digest(), "big")
                v[h % DIM] += 1.0 if h & 1 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


def make_embedder(kind: str, model_name: str = "BAAI/bge-small-en-v1.5") -> tuple[Embedder, str]:
    if kind == "hash":
        return HashEmbedder(), HashEmbedder.name
    return get_embedder(model_name), model_name
