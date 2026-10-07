"""Text embeddings with fastembed (BAAI/bge-small-en-v1.5, 384-d, CPU). Lazy singleton."""

import asyncio
import os
import threading
from typing import Protocol

EMBEDDING_DIM = 384


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    """Loads the ONNX model on first use (the Docker image pre-downloads it)."""

    def __init__(self, model_name: str, batch_size: int = 64) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: object | None = None
        self._lock = threading.Lock()

    def _load(self) -> object:
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(
                    model_name=self.model_name, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH")
                )
        return self._model

    def embed_sync(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.embed(texts, batch_size=self.batch_size)  # type: ignore[attr-defined]
        return [[float(x) for x in v] for v in vectors]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # ONNX inference is CPU-bound; keep the event loop free.
        return await asyncio.to_thread(self.embed_sync, texts)


_embedder: FastEmbedder | None = None


def get_embedder(model_name: str) -> FastEmbedder:
    global _embedder
    if _embedder is None or _embedder.model_name != model_name:
        _embedder = FastEmbedder(model_name)
    return _embedder


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0
